from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from typing import List
from ...core.database import get_db
from ...core.security import get_password_hash, require_permission, invalidate_user_sessions
from ...models.user import Usuario
from ...schemas.auth import UserCreate, UserUpdate, UserResponse

router = APIRouter(prefix="/users", tags=["Usuários"])


def _user_to_response(user: Usuario) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "nome": user.nome,
        "perfil_acesso_id": user.perfil_acesso_id,
        "perfil_acesso_nome": user.perfil_acesso_rel.nome if user.perfil_acesso_rel else None,
        "is_admin": user.perfil_acesso_rel.is_admin if user.perfil_acesso_rel else False,
        "centro_custo_id": user.centro_custo_id,
        "ativo": user.ativo,
        "recebe_alertas_corte": user.recebe_alertas_corte or False,
        "recebe_insights_nori": user.recebe_insights_nori or False,
    }


@router.get("/", response_model=List[UserResponse])
def list_users(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("admin_usuarios", "pode_visualizar")),
):
    users = db.query(Usuario).options(joinedload(Usuario.perfil_acesso_rel)).offset(skip).limit(limit).all()
    return [_user_to_response(u) for u in users]


@router.post("/", response_model=UserResponse)
def create_user(
    user: UserCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("admin_usuarios", "pode_criar")),
):
    existing = db.query(Usuario).filter(Usuario.email == user.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email já cadastrado")

    db_user = Usuario(
        email=user.email,
        nome=user.nome,
        senha_hash=get_password_hash(user.password),
        perfil_acesso_id=user.perfil_acesso_id,
        centro_custo_id=user.centro_custo_id,
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    db_user = db.query(Usuario).options(joinedload(Usuario.perfil_acesso_rel)).filter(Usuario.id == db_user.id).first()
    return _user_to_response(db_user)


@router.get("/{user_id}", response_model=UserResponse)
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("admin_usuarios", "pode_visualizar")),
):
    user = db.query(Usuario).options(joinedload(Usuario.perfil_acesso_rel)).filter(Usuario.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    return _user_to_response(user)


@router.put("/{user_id}", response_model=UserResponse)
def update_user(
    user_id: int,
    user_update: UserUpdate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("admin_usuarios", "pode_editar")),
):
    user = db.query(Usuario).filter(Usuario.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    update_data = user_update.model_dump(exclude_unset=True)

    if "password" in update_data and update_data["password"]:
        user.senha_hash = get_password_hash(update_data["password"])
        del update_data["password"]

    was_active = user.ativo
    for field, value in update_data.items():
        setattr(user, field, value)

    if was_active and not user.ativo:
        invalidate_user_sessions(user_id, db)

    db.commit()
    db.refresh(user)
    user = db.query(Usuario).options(joinedload(Usuario.perfil_acesso_rel)).filter(Usuario.id == user.id).first()
    return _user_to_response(user)


@router.delete("/{user_id}")
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("admin_usuarios", "pode_deletar")),
):
    user = db.query(Usuario).filter(Usuario.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    user.ativo = False
    invalidate_user_sessions(user_id, db)
    db.commit()
    return {"message": "Usuário desativado"}
