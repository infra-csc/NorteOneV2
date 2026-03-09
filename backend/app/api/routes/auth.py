from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import timedelta
from ...core.database import get_db
from ...core.security import verify_password, create_access_token, get_current_user
from ...core.config import settings
from ...models.user import Usuario
from ...schemas.auth import Token, UserResponse

router = APIRouter(prefix="/auth", tags=["Autenticação"])

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
    access_token = create_access_token(
        data={"sub": str(user.id)},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    return {"access_token": access_token, "token_type": "bearer"}

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
    }
