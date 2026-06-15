"""
Envio de e-mail via Microsoft Graph API (OAuth2 client_credentials).

Credenciais lidas de variáveis de ambiente:
  MS_TENANT_ID      — ID do diretório Azure AD
  MS_CLIENT_ID      — Application (client) ID do App Registration
  MS_CLIENT_SECRET  — Client Secret do App Registration
  MS_SENDER_EMAIL   — Caixa de e-mail remetente (precisa de permissão Mail.Send)

O token OAuth2 é cacheado em memória e renovado automaticamente antes do vencimento.
Nunca logamos nem persistimos credenciais ou tokens.
"""
import os
import time
import logging
import threading
from typing import Optional

import requests

logger = logging.getLogger(__name__)

_GRAPH_TOKEN_URL = "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
_GRAPH_SEND_URL = "https://graph.microsoft.com/v1.0/users/{sender}/sendMail"

_TOKEN_REFRESH_MARGIN_SEC = 120


class EmailError(Exception):
    """Falha ao enviar e-mail (credenciais ausentes ou erro da API)."""


# ── Cache de token em memória ─────────────────────────────────────────────────
_token_lock = threading.Lock()
_cached_token: Optional[str] = None
_token_expires_at: float = 0.0


def _get_ms_credentials() -> tuple[str, str, str, str]:
    """Retorna (tenant_id, client_id, client_secret, sender_email). Levanta EmailError se faltar."""
    tenant_id = os.environ.get("MS_TENANT_ID", "").strip()
    client_id = os.environ.get("MS_CLIENT_ID", "").strip()
    client_secret = os.environ.get("MS_CLIENT_SECRET", "").strip()
    sender_email = os.environ.get("MS_SENDER_EMAIL", "").strip()

    missing = [k for k, v in [
        ("MS_TENANT_ID", tenant_id),
        ("MS_CLIENT_ID", client_id),
        ("MS_CLIENT_SECRET", client_secret),
        ("MS_SENDER_EMAIL", sender_email),
    ] if not v]

    if missing:
        raise EmailError(
            f"Credenciais Microsoft Graph ausentes: {', '.join(missing)}. "
            "Configure as variáveis de ambiente no Replit Secrets."
        )
    return tenant_id, client_id, client_secret, sender_email


def _acquire_token() -> str:
    """Retorna um access token válido, usando cache quando possível."""
    global _cached_token, _token_expires_at

    with _token_lock:
        now = time.time()
        if _cached_token and now < (_token_expires_at - _TOKEN_REFRESH_MARGIN_SEC):
            return _cached_token

        tenant_id, client_id, client_secret, _ = _get_ms_credentials()

        url = _GRAPH_TOKEN_URL.format(tenant_id=tenant_id)
        try:
            resp = requests.post(
                url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "scope": "https://graph.microsoft.com/.default",
                },
                timeout=15,
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise EmailError(f"Falha ao obter token Microsoft Graph: {exc}") from exc

        data = resp.json()
        token = data.get("access_token")
        if not token:
            raise EmailError(
                f"Resposta de token sem access_token: {str(data)[:200]}"
            )

        expires_in = int(data.get("expires_in", 3600))
        _cached_token = token
        _token_expires_at = now + expires_in
        logger.debug("[EmailService] Token Microsoft Graph renovado (expira em %ds)", expires_in)
        return token


def send_email(
    to_email: str,
    subject: str,
    html: Optional[str] = None,
    text: Optional[str] = None,
    *,
    credentials=None,
    to_name: Optional[str] = None,
) -> None:
    """Envia um e-mail via Microsoft Graph API.

    O parâmetro `credentials` existe apenas para compatibilidade de interface
    com o código legado — é ignorado; as credenciais vêm sempre das variáveis
    de ambiente.
    """
    if not to_email:
        raise EmailError("Destinatário (to_email) vazio.")
    if not html and not text:
        raise EmailError("E-mail sem conteúdo (html/text).")

    _, _, _, sender_email = _get_ms_credentials()
    token = _acquire_token()

    body_content = html if html else text
    body_type = "HTML" if html else "Text"

    to_recipient: dict = {"emailAddress": {"address": to_email}}
    if to_name:
        to_recipient["emailAddress"]["name"] = to_name

    payload = {
        "message": {
            "subject": subject,
            "body": {
                "contentType": body_type,
                "content": body_content,
            },
            "toRecipients": [to_recipient],
        },
        "saveToSentItems": False,
    }

    url = _GRAPH_SEND_URL.format(sender=sender_email)
    try:
        resp = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=20,
        )
    except requests.RequestException as exc:
        raise EmailError(f"Falha de rede ao enviar e-mail: {exc}") from exc

    if resp.status_code == 401:
        # Token inválido/expirado: invalida cache e relança para retry no caller
        with _token_lock:
            global _cached_token, _token_expires_at
            _cached_token = None
            _token_expires_at = 0.0
        raise EmailError(
            f"Microsoft Graph retornou 401 (token inválido). "
            "Verifique as credenciais e permissões do App Registration."
        )

    if resp.status_code >= 300:
        raise EmailError(
            f"Microsoft Graph retornou {resp.status_code}: {resp.text[:500]}"
        )
