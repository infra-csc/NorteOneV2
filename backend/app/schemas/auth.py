from pydantic import BaseModel, EmailStr
from typing import Optional

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    user_id: Optional[int] = None

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class UserCreate(BaseModel):
    email: EmailStr
    nome: str
    password: str
    perfil_acesso_id: Optional[int] = None
    centro_custo_id: Optional[int] = None

class UserUpdate(BaseModel):
    nome: Optional[str] = None
    perfil_acesso_id: Optional[int] = None
    centro_custo_id: Optional[int] = None
    ativo: Optional[bool] = None
    password: Optional[str] = None
    recebe_alertas_corte: Optional[bool] = None
    recebe_insights_nori: Optional[bool] = None
    permite_login_local: Optional[bool] = None

class UserResponse(BaseModel):
    id: int
    email: str
    nome: str
    perfil_acesso_id: Optional[int] = None
    perfil_acesso_nome: Optional[str] = None
    is_admin: bool = False
    centro_custo_id: Optional[int] = None
    ativo: bool
    auth_provider: str = "local"
    recebe_alertas_corte: bool = False
    recebe_insights_nori: bool = False
    permite_login_local: bool = False
    foto_perfil: Optional[str] = None

    class Config:
        from_attributes = True
