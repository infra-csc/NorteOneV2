from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func as sa_func
from typing import List
from ...core.database import get_db
from ...core.security import require_permission, get_current_user, is_user_admin
from ...models.perfil_acesso import PerfilAcesso, PerfilPermissao
from ...models.user import Usuario
from ...schemas.perfil_acesso import (
    PerfilAcessoCreate, PerfilAcessoUpdate, PerfilAcessoResponse,
    PerfilAcessoListResponse, ModuloInfo, MODULOS_SISTEMA,
    UserPermissoesResponse, CAMPOS_EVENTOS, PermissaoCampoBase,
    PermissaoCampoResponse, CampoEventoInfo
)
from ...models.perfil_acesso import PerfilPermissaoCampo

router = APIRouter(prefix="/perfis-acesso", tags=["Perfis de Acesso"])


@router.get("/modulos", response_model=List[ModuloInfo])
def list_modulos(current_user: Usuario = Depends(get_current_user)):
    return MODULOS_SISTEMA


@router.get("/campos-eventos", response_model=List[CampoEventoInfo])
def list_campos_eventos(current_user: Usuario = Depends(get_current_user)):
    return CAMPOS_EVENTOS


@router.get("/", response_model=List[PerfilAcessoListResponse])
def list_perfis(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("admin_perfis_acesso", "pode_visualizar"))
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
            is_admin=perfil.is_admin,
            ativo=perfil.ativo,
            total_usuarios=total or 0
        ))
    return result


@router.get("/{perfil_id}", response_model=PerfilAcessoResponse)
def get_perfil(
    perfil_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("admin_perfis_acesso", "pode_visualizar"))
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
    current_user: Usuario = Depends(require_permission("admin_perfis_acesso", "pode_criar"))
):
    if data.is_admin and not is_user_admin(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Apenas administradores podem criar perfis com privilégio de administrador"
        )

    existing = db.query(PerfilAcesso).filter(PerfilAcesso.nome == data.nome).first()
    if existing:
        raise HTTPException(status_code=400, detail="Já existe um perfil com este nome")

    perfil = PerfilAcesso(nome=data.nome, descricao=data.descricao, is_admin=data.is_admin)
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
    current_user: Usuario = Depends(require_permission("admin_perfis_acesso", "pode_editar"))
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

    if data.is_admin is not None and data.is_admin != perfil.is_admin:
        if not is_user_admin(current_user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Apenas administradores podem alterar o privilégio de administrador"
            )
        perfil.is_admin = data.is_admin

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
    current_user: Usuario = Depends(require_permission("admin_perfis_acesso", "pode_deletar"))
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


@router.get("/{perfil_id}/permissoes-campo", response_model=List[PermissaoCampoResponse])
def get_permissoes_campo(
    perfil_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("admin_perfis_acesso", "pode_visualizar"))
):
    return db.query(PerfilPermissaoCampo).filter(
        PerfilPermissaoCampo.perfil_acesso_id == perfil_id
    ).all()


@router.put("/{perfil_id}/permissoes-campo")
def update_permissoes_campo(
    perfil_id: int,
    data: List[PermissaoCampoBase],
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("admin_perfis_acesso", "pode_editar"))
):
    perfil = db.query(PerfilAcesso).filter(PerfilAcesso.id == perfil_id).first()
    if not perfil:
        raise HTTPException(status_code=404, detail="Perfil não encontrado")

    db.query(PerfilPermissaoCampo).filter(
        PerfilPermissaoCampo.perfil_acesso_id == perfil_id
    ).delete()

    for perm in data:
        db_perm = PerfilPermissaoCampo(
            perfil_acesso_id=perfil_id,
            entidade=perm.entidade,
            campo=perm.campo,
            pode_visualizar=perm.pode_visualizar,
            pode_editar=perm.pode_editar,
        )
        db.add(db_perm)

    db.commit()
    return {"message": "Permissões de campo atualizadas com sucesso"}


@router.get("/me/permissoes", response_model=UserPermissoesResponse)
def get_my_permissions(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    if is_user_admin(current_user):
        all_perms = {}
        for mod in MODULOS_SISTEMA:
            all_perms[mod["key"]] = {
                "pode_visualizar": True,
                "pode_criar": True,
                "pode_editar": True,
                "pode_deletar": True,
            }
        all_campos = {}
        for campo in CAMPOS_EVENTOS:
            all_campos[campo["key"]] = {
                "pode_visualizar": True,
                "pode_editar": True,
            }
        return UserPermissoesResponse(
            perfil_acesso_id=current_user.perfil_acesso_id,
            perfil_acesso_nome=current_user.perfil_acesso_rel.nome if current_user.perfil_acesso_rel else "Administrador",
            is_admin=True,
            permissoes=all_perms,
            permissoes_campo={"eventos": all_campos},
        )

    if not current_user.perfil_acesso_id:
        return UserPermissoesResponse(
            is_admin=False,
            permissoes={},
            permissoes_campo={},
        )

    perfil = db.query(PerfilAcesso).options(
        joinedload(PerfilAcesso.permissoes),
        joinedload(PerfilAcesso.permissoes_campo)
    ).filter(PerfilAcesso.id == current_user.perfil_acesso_id).first()

    if not perfil:
        return UserPermissoesResponse(
            is_admin=False,
            permissoes={},
            permissoes_campo={},
        )

    perms = {}
    for p in perfil.permissoes:
        perms[p.modulo] = {
            "pode_visualizar": p.pode_visualizar,
            "pode_criar": p.pode_criar,
            "pode_editar": p.pode_editar,
            "pode_deletar": p.pode_deletar,
        }

    campos = {}
    for pc in perfil.permissoes_campo:
        if pc.entidade not in campos:
            campos[pc.entidade] = {}
        campos[pc.entidade][pc.campo] = {
            "pode_visualizar": pc.pode_visualizar,
            "pode_editar": pc.pode_editar,
        }

    return UserPermissoesResponse(
        perfil_acesso_id=perfil.id,
        perfil_acesso_nome=perfil.nome,
        is_admin=False,
        permissoes=perms,
        permissoes_campo=campos,
    )
