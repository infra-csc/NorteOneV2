from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List
from ...core.database import get_db
from ...core.security import get_current_user, require_permission, is_user_admin
from ...models.fatos import FatoProjecao
from ...models.dimensoes import DimTempo, DimConta
from ...models.user import Usuario
from ...schemas.fatos import ProjecaoCreate, ProjecaoUpdate, ProjecaoResponse

router = APIRouter(prefix="/projecao", tags=["Projeções"])

@router.get("/", response_model=List[ProjecaoResponse])
def list_projecoes(
    skip: int = 0,
    limit: int = 100,
    centro_custo_id: int = None,
    projeto_id: int = None,
    status: str = None,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    query = db.query(FatoProjecao)
    
    if not is_user_admin(current_user) and current_user.centro_custo_id:
        query = query.filter(FatoProjecao.centro_custo_id == current_user.centro_custo_id)
    elif centro_custo_id:
        query = query.filter(FatoProjecao.centro_custo_id == centro_custo_id)
    
    if projeto_id:
        query = query.filter(FatoProjecao.projeto_id == projeto_id)
    if status:
        query = query.filter(FatoProjecao.status == status)
    
    projecoes = query.offset(skip).limit(limit).all()
    return projecoes

@router.post("/", response_model=ProjecaoResponse)
def create_projecao(
    projecao: ProjecaoCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("orcamento", "pode_criar"))
):
    if not is_user_admin(current_user) and current_user.centro_custo_id:
        if projecao.centro_custo_id != current_user.centro_custo_id:
            raise HTTPException(status_code=403, detail="Sem permissão para este centro de custo")
    
    db_projecao = FatoProjecao(**projecao.model_dump(), created_by=current_user.id)
    db.add(db_projecao)
    db.commit()
    db.refresh(db_projecao)
    return db_projecao

@router.put("/{projecao_id}", response_model=ProjecaoResponse)
def update_projecao(
    projecao_id: int,
    projecao_update: ProjecaoUpdate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("orcamento", "pode_editar"))
):
    projecao = db.query(FatoProjecao).filter(FatoProjecao.id == projecao_id).first()
    if not projecao:
        raise HTTPException(status_code=404, detail="Projeção não encontrada")
    
    if not is_user_admin(current_user) and current_user.centro_custo_id and projecao.centro_custo_id != current_user.centro_custo_id:
        raise HTTPException(status_code=403, detail="Sem permissão")
    
    for field, value in projecao_update.model_dump(exclude_unset=True).items():
        setattr(projecao, field, value)
    
    db.commit()
    db.refresh(projecao)
    return projecao

@router.post("/{projecao_id}/aprovar", response_model=ProjecaoResponse)
def aprovar_projecao(
    projecao_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("orcamento", "pode_criar"))
):
    projecao = db.query(FatoProjecao).filter(FatoProjecao.id == projecao_id).first()
    if not projecao:
        raise HTTPException(status_code=404, detail="Projeção não encontrada")
    
    projecao.status = "APROVADO"
    projecao.approved_by = current_user.id
    db.commit()
    db.refresh(projecao)
    return projecao

@router.post("/{projecao_id}/rejeitar", response_model=ProjecaoResponse)
def rejeitar_projecao(
    projecao_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("orcamento", "pode_deletar"))
):
    projecao = db.query(FatoProjecao).filter(FatoProjecao.id == projecao_id).first()
    if not projecao:
        raise HTTPException(status_code=404, detail="Projeção não encontrada")
    
    projecao.status = "REJEITADO"
    projecao.approved_by = current_user.id
    db.commit()
    db.refresh(projecao)
    return projecao
