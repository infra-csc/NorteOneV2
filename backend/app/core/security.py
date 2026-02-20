from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from .config import settings
from .database import get_db

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))

def get_password_hash(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

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

async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    from ..models.user import Usuario
    from sqlalchemy.orm import joinedload
    payload = decode_token(token)
    user_id_str = payload.get("sub")
    if user_id_str is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalido",
        )
    user_id = int(user_id_str)
    user = db.query(Usuario).options(joinedload(Usuario.perfil_acesso_rel)).filter(Usuario.id == user_id).first()
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
    return user

def is_user_admin(user) -> bool:
    return user.perfil_acesso_rel is not None and user.perfil_acesso_rel.is_admin

def require_admin():
    async def admin_checker(current_user = Depends(get_current_user)):
        if not is_user_admin(current_user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permissao insuficiente - requer perfil administrador",
            )
        return current_user
    return admin_checker

def require_permission(modulo: str, permissao: str = "pode_visualizar"):
    async def permission_checker(current_user = Depends(get_current_user)):
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
    async def role_checker(current_user = Depends(get_current_user)):
        if is_user_admin(current_user):
            return current_user
        if "ADMIN" in allowed_roles and len(allowed_roles) == 1:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permissao insuficiente - requer perfil administrador",
            )
        return current_user
    return role_checker
