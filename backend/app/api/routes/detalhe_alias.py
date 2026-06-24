"""CRUD de Padrões de Dimensão para o Detalhamento de Eventos.

Permite que administradores configurem regras de renomeação e agrupamento
de valores brutos das dimensões (kit, modalidade, pelotao, etc.) exibidos
na tela de Detalhamento de Eventos.

Permissão requerida: admin_detalhe_alias
  - pode_visualizar → GET (listar)
  - pode_editar     → POST, PUT, DELETE, /test
"""

import re
import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import Usuario
from app.models.perfil_acesso import PerfilAcesso, PerfilPermissao
from app.models.detalhe_dimensao_alias import DetalheDimensaoAlias
from app.schemas.detalhe_dimensao_alias import (
    DetalheDimensaoAliasCreate,
    DetalheDimensaoAliasUpdate,
    DetalheDimensaoAliasResponse,
    TestPatternRequest,
    TestPatternResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/detalhe-alias", tags=["Detalhe Dimensao Alias"])

_MODULO = "admin_detalhe_alias"


def _check_view(user: Usuario, db: Session) -> None:
    perfil = db.query(PerfilAcesso).filter(PerfilAcesso.id == user.perfil_acesso_id).first()
    if perfil and perfil.is_admin:
        return
    perm = db.query(PerfilPermissao).filter(
        PerfilPermissao.perfil_acesso_id == user.perfil_acesso_id,
        PerfilPermissao.modulo == _MODULO,
        PerfilPermissao.pode_visualizar == True,
    ).first()
    if not perm:
        raise HTTPException(403, "Sem permissão para visualizar Padrões de Dimensão")


def _check_edit(user: Usuario, db: Session) -> None:
    perfil = db.query(PerfilAcesso).filter(PerfilAcesso.id == user.perfil_acesso_id).first()
    if perfil and perfil.is_admin:
        return
    perm = db.query(PerfilPermissao).filter(
        PerfilPermissao.perfil_acesso_id == user.perfil_acesso_id,
        PerfilPermissao.modulo == _MODULO,
        PerfilPermissao.pode_editar == True,
    ).first()
    if not perm:
        raise HTTPException(403, "Sem permissão para editar Padrões de Dimensão")


@router.get("/", response_model=List[DetalheDimensaoAliasResponse])
def listar_aliases(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    _check_view(current_user, db)
    return (
        db.query(DetalheDimensaoAlias)
        .order_by(DetalheDimensaoAlias.dimensao, DetalheDimensaoAlias.ordem, DetalheDimensaoAlias.id)
        .all()
    )


@router.post("/", response_model=DetalheDimensaoAliasResponse, status_code=201)
def criar_alias(
    body: DetalheDimensaoAliasCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    _check_edit(current_user, db)
    if body.is_regex:
        try:
            re.compile(body.pattern)
        except re.error as e:
            raise HTTPException(422, f"Regex inválido: {e}")
    alias = DetalheDimensaoAlias(**body.model_dump())
    db.add(alias)
    db.commit()
    db.refresh(alias)
    _invalidate_alias_cache()
    logger.info(f"[DimensaoAlias] Criado id={alias.id} dim={alias.dimensao} pattern={alias.pattern!r}")
    return alias


@router.put("/{alias_id}", response_model=DetalheDimensaoAliasResponse)
def atualizar_alias(
    alias_id: int,
    body: DetalheDimensaoAliasUpdate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    _check_edit(current_user, db)
    alias = db.query(DetalheDimensaoAlias).filter(DetalheDimensaoAlias.id == alias_id).first()
    if not alias:
        raise HTTPException(404, "Padrão não encontrado")
    data = body.model_dump(exclude_unset=True)
    is_regex = data.get("is_regex", alias.is_regex)
    pattern = data.get("pattern", alias.pattern)
    if is_regex:
        try:
            re.compile(pattern)
        except re.error as e:
            raise HTTPException(422, f"Regex inválido: {e}")
    for field, value in data.items():
        setattr(alias, field, value)
    db.commit()
    db.refresh(alias)
    _invalidate_alias_cache()
    logger.info(f"[DimensaoAlias] Atualizado id={alias_id}")
    return alias


@router.delete("/{alias_id}", status_code=204)
def deletar_alias(
    alias_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    _check_edit(current_user, db)
    alias = db.query(DetalheDimensaoAlias).filter(DetalheDimensaoAlias.id == alias_id).first()
    if not alias:
        raise HTTPException(404, "Padrão não encontrado")
    db.delete(alias)
    db.commit()
    _invalidate_alias_cache()
    logger.info(f"[DimensaoAlias] Removido id={alias_id}")


@router.post("/test", response_model=TestPatternResponse)
def testar_padrao(
    body: TestPatternRequest,
    current_user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _check_edit(current_user, db)
    original = body.sample
    try:
        if body.is_regex:
            compiled = re.compile(body.pattern)
            result = compiled.sub(body.substituicao, original)
        else:
            result = body.substituicao if original.strip().lower() == body.pattern.strip().lower() else original
        casou = result != original
        return TestPatternResponse(original=original, resultado=result, casou=casou)
    except re.error as e:
        return TestPatternResponse(original=original, resultado=original, casou=False, erro=str(e))


# ---------------------------------------------------------------------------
# Cache invalidation — chamado sempre que um alias é criado/editado/deletado.
# O serviço de detalhe lê o cache com TTL; invalidar força re-leitura.
# ---------------------------------------------------------------------------
def _invalidate_alias_cache() -> None:
    try:
        from app.services.detalhe_eventos_service import invalidate_alias_cache
        invalidate_alias_cache()
    except Exception:
        pass
