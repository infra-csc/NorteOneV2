from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List
from ...core.database import get_db
from ...core.security import get_current_user, require_permission, is_user_admin
from ...models.fatos import FatoRealizado
from ...models.dimensoes import DimTempo, DimConta
from ...models.user import Usuario
from ...schemas.fatos import RealizadoCreate, RealizadoResponse

router = APIRouter(prefix="/realizado", tags=["Realizado"])

@router.get("/", response_model=List[RealizadoResponse])
def list_realizados(
    skip: int = 0,
    limit: int = 100,
    centro_custo_id: int = None,
    projeto_id: int = None,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    query = db.query(FatoRealizado)
    
    if not is_user_admin(current_user) and current_user.centro_custo_id:
        query = query.filter(FatoRealizado.centro_custo_id == current_user.centro_custo_id)
    elif centro_custo_id:
        query = query.filter(FatoRealizado.centro_custo_id == centro_custo_id)
    
    if projeto_id:
        query = query.filter(FatoRealizado.projeto_id == projeto_id)
    
    realizados = query.offset(skip).limit(limit).all()
    return realizados

@router.post("/", response_model=RealizadoResponse)
def create_realizado(
    realizado: RealizadoCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("orcamento", "pode_criar"))
):
    db_realizado = FatoRealizado(**realizado.model_dump())
    db.add(db_realizado)
    db.commit()
    db.refresh(db_realizado)
    return db_realizado

@router.get("/resumo")
def get_resumo_realizado(
    ano: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    receitas = db.query(func.sum(FatoRealizado.valor_realizado)).join(
        DimConta, FatoRealizado.conta_id == DimConta.id
    ).join(
        DimTempo, FatoRealizado.tempo_id == DimTempo.id
    ).filter(
        DimTempo.ano == ano,
        DimConta.tipo == 'RECEITA'
    ).scalar() or 0

    despesas = db.query(func.sum(FatoRealizado.valor_realizado)).join(
        DimConta, FatoRealizado.conta_id == DimConta.id
    ).join(
        DimTempo, FatoRealizado.tempo_id == DimTempo.id
    ).filter(
        DimTempo.ano == ano,
        DimConta.tipo == 'DESPESA'
    ).scalar() or 0

    return {
        "ano": ano,
        "total_receitas": float(receitas),
        "total_despesas": float(despesas),
        "resultado": float(receitas) - float(despesas)
    }

@router.delete("/{realizado_id}")
def delete_realizado(
    realizado_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("orcamento", "pode_deletar"))
):
    realizado = db.query(FatoRealizado).filter(FatoRealizado.id == realizado_id).first()
    if not realizado:
        raise HTTPException(status_code=404, detail="Registro não encontrado")
    
    db.delete(realizado)
    db.commit()
    return {"message": "Registro excluído"}
