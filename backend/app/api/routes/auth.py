import logging
import secrets
import urllib.parse
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import timedelta, datetime
from ...core.database import get_db
from ...core.security import (
    verify_password,
    create_access_token,
    decode_token,
    get_current_user,
    invalidate_user_sessions,
)
from ...core.config import settings
from ...models.user import Usuario
from ...models.user_session import UserSession
from ...schemas.auth import Token, UserResponse
from fastapi.security import OAuth2PasswordBearer

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Autenticação"])

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

MAX_SESSIONS_PER_USER = 3


def _issue_session_token(user: Usuario, db: Session) -> str:
    """Cria o JWT da aplicação + registro de sessão (jti), respeitando o limite
    de sessões por usuário. Compartilhado pelo login local e pelo SSO."""
    expires_delta = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": str(user.id)},
        expires_delta=expires_delta,
    )
    payload = decode_token(access_token)
    jti = payload.get("jti")
    expires_at = datetime.utcfromtimestamp(payload.get("exp"))

    existing_sessions = (
        db.query(UserSession)
        .filter(UserSession.user_id == user.id)
        .order_by(UserSession.created_at.asc())
        .all()
    )
    if len(existing_sessions) >= MAX_SESSIONS_PER_USER:
        oldest_to_remove = existing_sessions[: len(existing_sessions) - MAX_SESSIONS_PER_USER + 1]
        for s in oldest_to_remove:
            db.delete(s)

    db.add(UserSession(user_id=user.id, jti=jti, expires_at=expires_at))
    db.commit()
    return access_token


def _public_base_url(request: Request) -> str:
    """Origem pública da aplicação (scheme://host). Atrás do proxy/Vite o
    `request.base_url` resolve para o host interno (ex.: localhost:8000), então
    quando MS_REDIRECT_URI está configurado derivamos a origem dele — é a mesma
    origem pública que a Microsoft usa para devolver o browser."""
    configured = (settings.MS_REDIRECT_URI or "").strip()
    if configured:
        parts = urllib.parse.urlsplit(configured)
        if parts.scheme and parts.netloc:
            return f"{parts.scheme}://{parts.netloc}"
    return str(request.base_url).rstrip("/")


def _ms_redirect_uri(request: Request) -> str:
    """URL do callback do SSO. Usa MS_REDIRECT_URI quando configurado; caso
    contrário deriva do host da requisição. Deve bater EXATAMENTE com o Redirect
    URI cadastrado no portal Azure."""
    configured = (settings.MS_REDIRECT_URI or "").strip()
    if configured:
        return configured
    base = str(request.base_url).rstrip("/")
    return f"{base}/api/auth/microsoft/callback"


def _frontend_redirect(request: Request, *, token: str = "", error: str = "") -> RedirectResponse:
    """Redireciona o browser de volta ao frontend. Em sucesso, o token vai no
    fragmento (#token=...) para não cair em logs de servidor/proxy; em erro,
    como query (?sso_error=...)."""
    base = _public_base_url(request)
    path = settings.MS_FRONTEND_REDIRECT_PATH or "/auth/microsoft/callback"
    if token:
        return RedirectResponse(url=f"{base}{path}#token={urllib.parse.quote(token)}", status_code=302)
    msg = urllib.parse.quote(error or "Falha no login com a Microsoft.")
    return RedirectResponse(url=f"{base}{path}?sso_error={msg}", status_code=302)


@router.post("/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(Usuario).filter(Usuario.email == form_data.username).first()
    # Contas gerenciadas pela Microsoft NUNCA autenticam por senha local, mesmo
    # que ainda tenham senha_hash residual — assim a desprovisão no diretório
    # (desativar/remover) não pode ser contornada por login local.
    # EXCEÇÃO: contas break-glass (permite_login_local=True) podem autenticar por
    # senha mesmo sendo gerenciadas pelo diretório — acesso de emergência.
    if user and user.auth_provider == "microsoft" and not user.permite_login_local:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Esta conta usa login Microsoft. Use \"Entrar com Microsoft\".",
            headers={"WWW-Authenticate": "Bearer"},
        )
    # Contas SSO (sem senha local) não autenticam por este endpoint.
    if not user or not user.senha_hash or not verify_password(form_data.password, user.senha_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email ou senha incorretos",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.ativo:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuário inativo",
        )

    access_token = _issue_session_token(user, db)
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/microsoft/status")
def microsoft_sso_status():
    """Informa ao frontend se o login Microsoft está disponível (credenciais
    configuradas), para exibir ou não o botão."""
    from ...services.ms_auth_service import sso_configured
    return {"enabled": sso_configured()}


# Cookie que ancora o `state` ao navegador que iniciou o login (defesa contra
# login-CSRF / session fixation). É comparado ao `state` devolvido pela
# Microsoft no callback (double-submit), além da checagem server-side de uso
# único/expiração.
_SSO_STATE_COOKIE = "ms_sso_state"
_SSO_COOKIE_PATH = "/api/auth/microsoft"


@router.get("/microsoft/login")
def microsoft_login(request: Request):
    """Inicia o Authorization Code Flow: redireciona o browser à Microsoft."""
    from ...services.ms_auth_service import sso_configured, issue_state, build_authorize_url, MSAuthError
    if not sso_configured():
        raise HTTPException(status_code=503, detail="Login Microsoft não está configurado.")
    try:
        state = issue_state()
        url = build_authorize_url(_ms_redirect_uri(request), state)
    except MSAuthError as exc:
        logger.warning("[SSO] Falha ao montar URL de autorização: %s", exc)
        raise HTTPException(status_code=503, detail="Login Microsoft indisponível no momento.")
    resp = RedirectResponse(url=url, status_code=302)
    resp.set_cookie(
        key=_SSO_STATE_COOKIE,
        value=state,
        max_age=600,
        httponly=True,
        secure=True,
        samesite="lax",
        path=_SSO_COOKIE_PATH,
    )
    return resp


@router.get("/microsoft/callback")
def microsoft_callback(
    request: Request,
    code: str = "",
    state: str = "",
    error: str = "",
    error_description: str = "",
    db: Session = Depends(get_db),
):
    """Callback do SSO: valida o state, troca o código, provisiona/encontra o
    usuário, emite o token da aplicação e redireciona ao frontend."""
    from ...services.ms_auth_service import (
        consume_state, exchange_code_for_claims, extract_identity, MSAuthError,
    )
    from ...services.ms_directory_sync import find_or_provision_user

    def _clear_state_cookie(resp):
        resp.delete_cookie(_SSO_STATE_COOKIE, path=_SSO_COOKIE_PATH)
        return resp

    if error:
        logger.warning("[SSO] Erro retornado pela Microsoft: %s (%s)", error, error_description)
        return _clear_state_cookie(_frontend_redirect(request, error="Login com a Microsoft cancelado ou negado."))

    # Defesa contra login-CSRF: o `state` devolvido pela Microsoft precisa bater
    # com o cookie gravado no navegador que iniciou o login (double-submit), além
    # de ser válido server-side (uso único + expiração).
    cookie_state = request.cookies.get(_SSO_STATE_COOKIE, "")
    if not state or not cookie_state or not secrets.compare_digest(state, cookie_state):
        logger.warning("[SSO] State do callback não corresponde ao cookie de origem.")
        return _clear_state_cookie(_frontend_redirect(request, error="Sessão de login inválida. Tente novamente."))

    if not consume_state(state):
        return _clear_state_cookie(_frontend_redirect(request, error="Sessão de login expirada. Tente novamente."))

    if not code:
        return _clear_state_cookie(_frontend_redirect(request, error="Código de autorização ausente."))

    try:
        claims = exchange_code_for_claims(code, _ms_redirect_uri(request))
        ms_oid, email, nome = extract_identity(claims)
    except MSAuthError as exc:
        return _clear_state_cookie(_frontend_redirect(request, error=str(exc)))

    user = find_or_provision_user(db, ms_oid, email, nome)
    db.commit()
    db.refresh(user)

    if not user.ativo:
        return _clear_state_cookie(_frontend_redirect(request, error="Sua conta está inativa. Procure um administrador."))

    access_token = _issue_session_token(user, db)
    return _clear_state_cookie(_frontend_redirect(request, token=access_token))


@router.post("/logout")
def logout(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
):
    try:
        payload = decode_token(token)
        jti = payload.get("jti")
        if jti:
            db.query(UserSession).filter(UserSession.jti == jti).delete()
            db.commit()
    except HTTPException:
        pass
    return {"message": "Logout realizado com sucesso"}


@router.get("/me", response_model=UserResponse)
def get_me(current_user: Usuario = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "email": current_user.email,
        "nome": current_user.nome,
        "perfil_acesso_id": current_user.perfil_acesso_id,
        "perfil_acesso_nome": current_user.perfil_acesso_rel.nome if current_user.perfil_acesso_rel else None,
        "is_admin": current_user.perfil_acesso_rel.is_admin if current_user.perfil_acesso_rel else False,
        "centro_custo_id": current_user.centro_custo_id,
        "auth_provider": current_user.auth_provider,
        "ativo": current_user.ativo,
        "recebe_alertas_corte": current_user.recebe_alertas_corte or False,
        "recebe_insights_nori": current_user.recebe_insights_nori or False,
        "foto_perfil": current_user.foto_perfil,
    }
