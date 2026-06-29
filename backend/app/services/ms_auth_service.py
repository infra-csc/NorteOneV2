"""
Microsoft Entra ID (Azure AD) — Single Sign-On (Authorization Code Flow) e
acesso ao diretório de usuários via Microsoft Graph.

Diferente do `email_service` (que usa o fluxo *client_credentials* — app sem
usuário — para enviar e-mail), aqui temos dois fluxos:

  1. SSO delegado (Authorization Code Flow): o usuário faz login na Microsoft,
     o browser volta com um `code`, e o backend troca esse `code` por um
     `id_token` (identidade do usuário) num canal servidor-a-servidor.

  2. Listagem de diretório (client_credentials + Graph /users): usado pelo job
     de sincronização para descobrir/desativar contas.

Reutiliza as credenciais MS_TENANT_ID / MS_CLIENT_ID / MS_CLIENT_SECRET já
configuradas. Nunca logamos nem persistimos tokens.
"""
import time
import logging
import secrets
import threading
import urllib.parse
from typing import Optional

import jwt
import requests

from ..core.config import settings

logger = logging.getLogger(__name__)

_AUTHORITY = "https://login.microsoftonline.com/{tenant_id}"
_AUTHORIZE_PATH = "/oauth2/v2.0/authorize"
_TOKEN_PATH = "/oauth2/v2.0/token"
_JWKS_URL = "https://login.microsoftonline.com/{tenant_id}/discovery/v2.0/keys"
_GRAPH_USERS_URL = "https://graph.microsoft.com/v1.0/users"

# Escopos delegados mínimos para identificar o usuário no SSO.
_SSO_SCOPES = "openid profile email User.Read"

_TOKEN_REFRESH_MARGIN_SEC = 120


class MSAuthError(Exception):
    """Falha no fluxo de autenticação/diretório Microsoft."""


# ── State CSRF (anti-forgery) para o Authorization Code Flow ──────────────────
# Guarda os states emitidos com expiração curta; o callback precisa apresentar
# um state válido e ainda não usado. Em memória (suficiente: o fluxo é de poucos
# segundos e o state é single-use).
_state_lock = threading.Lock()
_pending_states: dict[str, float] = {}
_STATE_TTL_SEC = 600


def _get_credentials() -> tuple[str, str, str]:
    tenant_id = (settings.MS_TENANT_ID or "").strip()
    client_id = (settings.MS_CLIENT_ID or "").strip()
    client_secret = (settings.MS_CLIENT_SECRET or "").strip()
    missing = [k for k, v in [
        ("MS_TENANT_ID", tenant_id),
        ("MS_CLIENT_ID", client_id),
        ("MS_CLIENT_SECRET", client_secret),
    ] if not v]
    if missing:
        raise MSAuthError(
            f"Credenciais Microsoft ausentes: {', '.join(missing)}. "
            "Configure as variáveis de ambiente."
        )
    return tenant_id, client_id, client_secret


def sso_configured() -> bool:
    """True quando há credenciais suficientes para oferecer o login Microsoft."""
    try:
        _get_credentials()
        return True
    except MSAuthError:
        return False


def issue_state() -> str:
    """Gera um state anti-CSRF de uso único, com expiração."""
    state = secrets.token_urlsafe(32)
    now = time.time()
    with _state_lock:
        # Limpeza preguiçosa de states expirados.
        expired = [s for s, ts in _pending_states.items() if now - ts > _STATE_TTL_SEC]
        for s in expired:
            _pending_states.pop(s, None)
        _pending_states[state] = now
    return state


def consume_state(state: Optional[str]) -> bool:
    """Valida e invalida (single-use) um state. Retorna True se era válido."""
    if not state:
        return False
    now = time.time()
    with _state_lock:
        ts = _pending_states.pop(state, None)
    return ts is not None and (now - ts) <= _STATE_TTL_SEC


def build_authorize_url(redirect_uri: str, state: str) -> str:
    """Monta a URL de autorização para redirecionar o browser à Microsoft."""
    tenant_id, client_id, _ = _get_credentials()
    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "response_mode": "query",
        "scope": _SSO_SCOPES,
        "state": state,
        # Garante seleção de conta — evita login silencioso indesejado.
        "prompt": "select_account",
    }
    base = _AUTHORITY.format(tenant_id=tenant_id) + _AUTHORIZE_PATH
    return f"{base}?{urllib.parse.urlencode(params)}"


def exchange_code_for_claims(code: str, redirect_uri: str) -> dict:
    """Troca o authorization code por tokens e retorna os claims do id_token
    (validados via JWKS). Levanta MSAuthError em qualquer falha.
    """
    tenant_id, client_id, client_secret = _get_credentials()
    token_url = _AUTHORITY.format(tenant_id=tenant_id) + _TOKEN_PATH
    try:
        resp = requests.post(
            token_url,
            data={
                "grant_type": "authorization_code",
                "client_id": client_id,
                "client_secret": client_secret,
                "code": code,
                "redirect_uri": redirect_uri,
                "scope": _SSO_SCOPES,
            },
            timeout=15,
        )
    except requests.RequestException as exc:
        raise MSAuthError(f"Falha de rede ao trocar código por token: {exc}") from exc

    if resp.status_code != 200:
        # Não vazar corpo bruto da resposta ao usuário; apenas logar resumido.
        try:
            err = resp.json().get("error", "")
        except Exception:
            err = ""
        logger.warning("[MSAuth] Troca de código falhou (status=%s, error=%s)", resp.status_code, err)
        raise MSAuthError("Não foi possível concluir o login com a Microsoft.")

    id_token = (resp.json() or {}).get("id_token")
    if not id_token:
        raise MSAuthError("Resposta da Microsoft não trouxe id_token.")

    return _validate_id_token(id_token, client_id, tenant_id)


def _validate_id_token(id_token: str, client_id: str, tenant_id: str) -> dict:
    """Valida assinatura (JWKS), audiência e emissor do id_token."""
    try:
        jwks_client = jwt.PyJWKClient(_JWKS_URL.format(tenant_id=tenant_id))
        signing_key = jwks_client.get_signing_key_from_jwt(id_token)
        claims = jwt.decode(
            id_token,
            signing_key.key,
            algorithms=["RS256"],
            audience=client_id,
            options={"verify_exp": True},
        )
    except Exception as exc:
        logger.warning("[MSAuth] Validação do id_token falhou: %s", exc)
        raise MSAuthError("Token de identidade inválido.") from exc

    # Emissor precisa ser do tenant esperado (defesa adicional além de aud).
    iss = claims.get("iss", "")
    if tenant_id not in iss:
        logger.warning("[MSAuth] Emissor inesperado no id_token: %s", iss)
        raise MSAuthError("Emissor do token de identidade inválido.")

    return claims


def extract_identity(claims: dict) -> tuple[str, str, str]:
    """Extrai (ms_oid, email, nome) dos claims do id_token.

    O e-mail pode vir em `email`, `preferred_username` ou `upn`. Levanta
    MSAuthError se faltar oid ou e-mail.
    """
    oid = claims.get("oid") or claims.get("sub")
    email = (
        claims.get("email")
        or claims.get("preferred_username")
        or claims.get("upn")
        or ""
    ).strip().lower()
    nome = (claims.get("name") or email or "Usuário Microsoft").strip()
    if not oid:
        raise MSAuthError("Token de identidade sem identificador de objeto (oid).")
    if not email:
        raise MSAuthError("Token de identidade sem e-mail.")
    return str(oid), email, nome


# ── Acesso ao diretório (app-only / client_credentials) ───────────────────────
_dir_token_lock = threading.Lock()
_dir_cached_token: Optional[str] = None
_dir_token_expires_at: float = 0.0


def _acquire_directory_token() -> str:
    """Token app-only (client_credentials) para chamar o Graph /users."""
    global _dir_cached_token, _dir_token_expires_at
    with _dir_token_lock:
        now = time.time()
        if _dir_cached_token and now < (_dir_token_expires_at - _TOKEN_REFRESH_MARGIN_SEC):
            return _dir_cached_token

        tenant_id, client_id, client_secret = _get_credentials()
        token_url = _AUTHORITY.format(tenant_id=tenant_id) + _TOKEN_PATH
        try:
            resp = requests.post(
                token_url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "scope": "https://graph.microsoft.com/.default",
                },
                timeout=15,
            )
        except requests.RequestException as exc:
            raise MSAuthError(f"Falha de rede ao obter token de diretório: {exc}") from exc

        if resp.status_code != 200:
            try:
                err = resp.json().get("error", "")
            except Exception:
                err = ""
            raise MSAuthError(f"Falha ao obter token de diretório (status={resp.status_code}, error={err}).")

        body = resp.json() or {}
        token = body.get("access_token")
        if not token:
            raise MSAuthError("Resposta de token de diretório sem access_token.")
        _dir_cached_token = token
        _dir_token_expires_at = now + int(body.get("expires_in", 3600))
        return token


def list_directory_users() -> list[dict]:
    """Lista TODOS os usuários do diretório (paginado).

    Retorna dicts com: id (oid), mail/userPrincipalName, displayName,
    accountEnabled. A fonte da verdade de "ativo" é o `accountEnabled` do
    diretório.
    """
    token = _acquire_directory_token()
    headers = {"Authorization": f"Bearer {token}"}
    select = "id,displayName,mail,userPrincipalName,accountEnabled"
    url = f"{_GRAPH_USERS_URL}?$select={select}&$top=999"
    users: list[dict] = []
    page = 0
    while url:
        page += 1
        try:
            resp = requests.get(url, headers=headers, timeout=30)
        except requests.RequestException as exc:
            raise MSAuthError(f"Falha de rede ao listar diretório (página {page}): {exc}") from exc
        if resp.status_code != 200:
            try:
                err = resp.json().get("error", {})
            except Exception:
                err = {}
            raise MSAuthError(
                f"Falha ao listar diretório (status={resp.status_code}, error={err}). "
                "Verifique a permissão de aplicação User.Read.All com consentimento de admin."
            )
        body = resp.json() or {}
        users.extend(body.get("value", []) or [])
        url = body.get("@odata.nextLink")
        if page > 200:  # cinto de segurança contra loop de paginação
            logger.warning("[MSAuth] Paginação de diretório excedeu 200 páginas — interrompendo.")
            break
    return users
