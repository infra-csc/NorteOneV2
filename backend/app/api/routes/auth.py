from fastapi import APIRouter, Depends, HTTPException, status
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

router = APIRouter(prefix="/auth", tags=["Autenticação"])

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

MAX_SESSIONS_PER_USER = 3


@router.post("/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(Usuario).filter(Usuario.email == form_data.username).first()
    if not user or not verify_password(form_data.password, user.senha_hash):
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

    db.add(
        UserSession(
            user_id=user.id,
            jti=jti,
            expires_at=expires_at,
        )
    )
    db.commit()

    return {"access_token": access_token, "token_type": "bearer"}


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
        "ativo": current_user.ativo,
        "recebe_alertas_corte": current_user.recebe_alertas_corte or False,
        "recebe_insights_nori": current_user.recebe_insights_nori or False,
        "foto_perfil": current_user.foto_perfil,
    }
