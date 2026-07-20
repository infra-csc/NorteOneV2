import uuid
from datetime import datetime, timedelta
from typing import Optional
import jwt
from jwt.exceptions import InvalidTokenError as JWTError
import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from .config import settings
from .database import get_db_auth

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

_secret_key_stripped = settings.SECRET_KEY.strip()
if not _secret_key_stripped:
    raise RuntimeError(
        "SESSION_SECRET environment variable is not set or is empty. "
        "The application cannot start without a strong JWT signing secret. "
        "Set SESSION_SECRET to a long, random string before running the server."
    )
if len(_secret_key_stripped) < 32:
    raise RuntimeError(
        f"SESSION_SECRET is too short ({len(_secret_key_stripped)} characters). "
        "A minimum of 32 characters is required for HS256 signing security. "
        "Generate a strong random secret and set it in SESSION_SECRET."
    )


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


def get_password_hash(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "jti": str(uuid.uuid4())})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalido",
            headers={"WWW-Authenticate": "Bearer"},
        )


def invalidate_user_sessions(user_id: int, db: Session) -> int:
    """Deleta todas as sessões ativas de um usuário. Retorna a quantidade removida."""
    from ..models.user_session import UserSession
    deleted = db.query(UserSession).filter(UserSession.user_id == user_id).delete()
    db.commit()
    return deleted


_ACTIVITY_THROTTLE_SECONDS = 60


async def get_current_user(token: str = Depends(oauth2_scheme)):
    """Valida o token e carrega o usuário usando o pool DEDICADO de auth.

    A sessão é aberta e fechada AQUI DENTRO (não via Depends) para que a
    conexão volte ao pool imediatamente após a validação — nunca fica presa
    durante a requisição inteira. O usuário retornado é DESANEXADO (detached):
    todos os atributos e relações necessários (perfil_acesso_rel, permissoes,
    permissoes_campo) são carregados de forma eager antes do close. Endpoints
    que precisem GRAVAR no usuário devem recarregá-lo na própria sessão
    (ex.: db.get(Usuario, current_user.id))."""
    from ..models.user import Usuario
    from ..models.user_session import UserSession
    from ..models.perfil_acesso import PerfilAcesso
    from sqlalchemy.orm import joinedload, selectinload
    from .database import SessionLocalAuth

    payload = decode_token(token)

    user_id_str = payload.get("sub")
    if user_id_str is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalido",
        )

    jti = payload.get("jti")
    if jti is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sessão expirada. Faça login novamente.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if SessionLocalAuth is None:
        raise HTTPException(status_code=500, detail="Banco de dados não configurado")

    db = SessionLocalAuth()
    try:
        session = db.query(UserSession).filter(UserSession.jti == jti).first()
        if session is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Sessão encerrada. Faça login novamente.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        user_id = int(user_id_str)
        user = (
            db.query(Usuario)
            .options(
                joinedload(Usuario.perfil_acesso_rel).selectinload(PerfilAcesso.permissoes),
                joinedload(Usuario.perfil_acesso_rel).selectinload(PerfilAcesso.permissoes_campo),
            )
            .filter(Usuario.id == user_id)
            .first()
        )
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Usuario nao encontrado",
            )
        if not user.ativo:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Usuario inativo",
            )

        now = datetime.utcnow()
        if user.last_activity is None or (now - user.last_activity).total_seconds() > _ACTIVITY_THROTTLE_SECONDS:
            try:
                user.last_activity = now
                db.commit()
            except Exception:
                db.rollback()

        # Desanexa com atributos/relacões carregados — a conexão volta ao pool
        # imediatamente e o objeto segue legível pelo resto da requisição.
        db.expunge(user)
        return user
    finally:
        db.close()


def is_user_admin(user) -> bool:
    return user.perfil_acesso_rel is not None and user.perfil_acesso_rel.is_admin


def require_admin():
    async def admin_checker(current_user=Depends(get_current_user)):
        if not is_user_admin(current_user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permissao insuficiente - requer perfil administrador",
            )
        return current_user

    return admin_checker


def require_permission(modulo: str, permissao: str = "pode_visualizar"):
    async def permission_checker(current_user=Depends(get_current_user)):
        if is_user_admin(current_user):
            return current_user
        if not current_user.perfil_acesso_rel:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permissao insuficiente - sem perfil de acesso",
            )
        for perm in current_user.perfil_acesso_rel.permissoes:
            if perm.modulo == modulo and getattr(perm, permissao, False):
                return current_user
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permissao insuficiente para {modulo}",
        )

    return permission_checker


def require_roles(allowed_roles: list):
    async def role_checker(current_user=Depends(get_current_user)):
        if is_user_admin(current_user):
            return current_user
        if "ADMIN" in allowed_roles and len(allowed_roles) == 1:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permissao insuficiente - requer perfil administrador",
            )
        return current_user

    return role_checker
