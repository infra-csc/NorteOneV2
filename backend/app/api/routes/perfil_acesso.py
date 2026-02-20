from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func as sa_func
from typing import List
from ...core.database import get_db
from ...core.security import require_roles, get_current_user
from ...models.perfil_acesso import PerfilAcesso, PerfilPermissao
from ...models.user import Usuario
from ...schemas.perfil_acesso import (
    PerfilAcessoCreate, PerfilAcessoUpdate, PerfilAcessoResponse,
    PerfilAcessoListResponse, ModuloInfo, MODULOS_SISTEMA,
    UserPermissoesResponse
)

router = APIRouter(prefix="/perfis-acesso", tags=["Perfis de Acesso"])


@router.get("/modulos", response_model=List[ModuloInfo])
def list_modulos(current_user: Usuario = Depends(get_current_user)):
    return MODULOS_SISTEMA


@router.get("/", response_model=List[PerfilAcessoListResponse])
def list_perfis(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_roles(["ADMIN"]))
):
    perfis = db.query(PerfilAcesso).filter(PerfilAcesso.ativo == True).all()
    result = []
    for perfil in perfis:
        total = db.query(sa_func.count(Usuario.id)).filter(
            Usuario.perfil_acesso_id == perfil.id,
            Usuario.ativo == True
        ).scalar()
        result.append(PerfilAcessoListResponse(
            id=perfil.id,
            nome=perfil.nome,
            descricao=perfil.descricao,
            is_sistema=perfil.is_sistema,
            ativo=perfil.ativo,
            total_usuarios=total or 0
        ))
    return result


@router.get("/{perfil_id}", response_model=PerfilAcessoResponse)
def get_perfil(
    perfil_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_roles(["ADMIN"]))
):
    perfil = db.query(PerfilAcesso).options(
        joinedload(PerfilAcesso.permissoes)
    ).filter(PerfilAcesso.id == perfil_id).first()
    if not perfil:
        raise HTTPException(status_code=404, detail="Perfil não encontrado")
    return perfil


@router.post("/", response_model=PerfilAcessoResponse, status_code=201)
def create_perfil(
    data: PerfilAcessoCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_roles(["ADMIN"]))
):
    existing = db.query(PerfilAcesso).filter(PerfilAcesso.nome == data.nome).first()
    if existing:
        raise HTTPException(status_code=400, detail="Já existe um perfil com este nome")

    perfil = PerfilAcesso(nome=data.nome, descricao=data.descricao)
    db.add(perfil)
    db.flush()

    for perm in data.permissoes:
        db_perm = PerfilPermissao(
            perfil_acesso_id=perfil.id,
            modulo=perm.modulo,
            pode_visualizar=perm.pode_visualizar,
            pode_criar=perm.pode_criar,
            pode_editar=perm.pode_editar,
            pode_deletar=perm.pode_deletar,
        )
        db.add(db_perm)

    db.commit()
    db.refresh(perfil)
    return db.query(PerfilAcesso).options(
        joinedload(PerfilAcesso.permissoes)
    ).filter(PerfilAcesso.id == perfil.id).first()


@router.put("/{perfil_id}", response_model=PerfilAcessoResponse)
def update_perfil(
    perfil_id: int,
    data: PerfilAcessoUpdate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_roles(["ADMIN"]))
):
    perfil = db.query(PerfilAcesso).filter(PerfilAcesso.id == perfil_id).first()
    if not perfil:
        raise HTTPException(status_code=404, detail="Perfil não encontrado")

    if data.nome is not None:
        existing = db.query(PerfilAcesso).filter(
            PerfilAcesso.nome == data.nome,
            PerfilAcesso.id != perfil_id
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail="Já existe um perfil com este nome")
        perfil.nome = data.nome

    if data.descricao is not None:
        perfil.descricao = data.descricao

    if data.ativo is not None:
        perfil.ativo = data.ativo

    if data.permissoes is not None:
        db.query(PerfilPermissao).filter(
            PerfilPermissao.perfil_acesso_id == perfil_id
        ).delete()

        for perm in data.permissoes:
            db_perm = PerfilPermissao(
                perfil_acesso_id=perfil.id,
                modulo=perm.modulo,
                pode_visualizar=perm.pode_visualizar,
                pode_criar=perm.pode_criar,
                pode_editar=perm.pode_editar,
                pode_deletar=perm.pode_deletar,
            )
            db.add(db_perm)

    db.commit()
    return db.query(PerfilAcesso).options(
        joinedload(PerfilAcesso.permissoes)
    ).filter(PerfilAcesso.id == perfil.id).first()


@router.delete("/{perfil_id}")
def delete_perfil(
    perfil_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_roles(["ADMIN"]))
):
    perfil = db.query(PerfilAcesso).filter(PerfilAcesso.id == perfil_id).first()
    if not perfil:
        raise HTTPException(status_code=404, detail="Perfil não encontrado")

    if perfil.is_sistema:
        raise HTTPException(status_code=400, detail="Perfis de sistema não podem ser excluídos")

    users_count = db.query(sa_func.count(Usuario.id)).filter(
        Usuario.perfil_acesso_id == perfil_id,
        Usuario.ativo == True
    ).scalar()
    if users_count and users_count > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Este perfil possui {users_count} usuário(s) vinculado(s). Reatribua-os antes de excluir."
        )

    perfil.ativo = False
    db.commit()
    return {"message": "Perfil desativado com sucesso"}


@router.get("/me/permissoes", response_model=UserPermissoesResponse)
def get_my_permissions(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    if current_user.perfil == 'ADMIN':
        all_perms = {}
        for mod in MODULOS_SISTEMA:
            all_perms[mod["key"]] = {
                "pode_visualizar": True,
                "pode_criar": True,
                "pode_editar": True,
                "pode_deletar": True,
            }
        return UserPermissoesResponse(
            perfil_acesso_id=current_user.perfil_acesso_id,
            perfil_acesso_nome="ADMIN",
            perfil=current_user.perfil,
            permissoes=all_perms,
        )

    if not current_user.perfil_acesso_id:
        return UserPermissoesResponse(
            perfil=current_user.perfil,
            permissoes={},
        )

    perfil = db.query(PerfilAcesso).options(
        joinedload(PerfilAcesso.permissoes)
    ).filter(PerfilAcesso.id == current_user.perfil_acesso_id).first()

    if not perfil:
        return UserPermissoesResponse(
            perfil=current_user.perfil,
            permissoes={},
        )

    perms = {}
    for p in perfil.permissoes:
        perms[p.modulo] = {
            "pode_visualizar": p.pode_visualizar,
            "pode_criar": p.pode_criar,
            "pode_editar": p.pode_editar,
            "pode_deletar": p.pode_deletar,
        }

    return UserPermissoesResponse(
        perfil_acesso_id=perfil.id,
        perfil_acesso_nome=perfil.nome,
        perfil=current_user.perfil,
        permissoes=perms,
    )
