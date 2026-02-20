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
    perfil: str = "VISUALIZADOR"
    perfil_acesso_id: Optional[int] = None
    centro_custo_id: Optional[int] = None

class UserUpdate(BaseModel):
    nome: Optional[str] = None
    perfil: Optional[str] = None
    perfil_acesso_id: Optional[int] = None
    centro_custo_id: Optional[int] = None
    ativo: Optional[bool] = None
    password: Optional[str] = None

class UserResponse(BaseModel):
    id: int
    email: str
    nome: str
    perfil: str
    perfil_acesso_id: Optional[int] = None
    centro_custo_id: Optional[int] = None
    ativo: bool
    
    class Config:
        from_attributes = True
