from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List
import pandas as pd
import io
from ...core.database import get_db
from ...core.security import get_current_user, require_roles
from ...models.fatos import FatoOrcamento
from ...models.dimensoes import DimTempo, DimCentroCusto, DimConta, DimProjeto
from ...models.user import Usuario
from ...schemas.fatos import OrcamentoCreate, OrcamentoUpdate, OrcamentoResponse

router = APIRouter(prefix="/orcamento", tags=["Orçamento"])

@router.get("/", response_model=List[OrcamentoResponse])
def list_orcamentos(
    skip: int = 0,
    limit: int = 100,
    ano: int = None,
    centro_custo_id: int = None,
    projeto_id: int = None,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    query = db.query(FatoOrcamento)
    if ano:
        query = query.filter(FatoOrcamento.ano_referencia == ano)
    if centro_custo_id:
        query = query.filter(FatoOrcamento.centro_custo_id == centro_custo_id)
    if projeto_id:
        query = query.filter(FatoOrcamento.projeto_id == projeto_id)
    orcamentos = query.offset(skip).limit(limit).all()
    return orcamentos

@router.post("/", response_model=OrcamentoResponse)
def create_orcamento(
    orcamento: OrcamentoCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_roles(["ADMIN", "ANALISTA", "GESTOR"]))
):
    db_orcamento = FatoOrcamento(**orcamento.model_dump(), created_by=current_user.id)
    db.add(db_orcamento)
    db.commit()
    db.refresh(db_orcamento)
    return db_orcamento

@router.get("/resumo")
def get_resumo_orcamento(
    ano: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    receitas = db.query(func.sum(FatoOrcamento.valor_orcado)).join(
        DimConta, FatoOrcamento.conta_id == DimConta.id
    ).filter(
        FatoOrcamento.ano_referencia == ano,
        DimConta.tipo == 'RECEITA'
    ).scalar() or 0

    despesas = db.query(func.sum(FatoOrcamento.valor_orcado)).join(
        DimConta, FatoOrcamento.conta_id == DimConta.id
    ).filter(
        FatoOrcamento.ano_referencia == ano,
        DimConta.tipo == 'DESPESA'
    ).scalar() or 0

    return {
        "ano": ano,
        "total_receitas": float(receitas),
        "total_despesas": float(despesas),
        "resultado": float(receitas) - float(despesas)
    }

@router.get("/por-mes")
def get_orcamento_por_mes(
    ano: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    dados = db.query(
        DimTempo.mes,
        DimConta.tipo,
        func.sum(FatoOrcamento.valor_orcado).label('total')
    ).join(
        DimTempo, FatoOrcamento.tempo_id == DimTempo.id
    ).join(
        DimConta, FatoOrcamento.conta_id == DimConta.id
    ).filter(
        FatoOrcamento.ano_referencia == ano
    ).group_by(DimTempo.mes, DimConta.tipo).all()
    
    resultado = {}
    for mes, tipo, total in dados:
        if mes not in resultado:
            resultado[mes] = {"mes": mes, "receitas": 0, "despesas": 0}
        if tipo == 'RECEITA':
            resultado[mes]["receitas"] = float(total)
        else:
            resultado[mes]["despesas"] = float(total)
    
    return list(resultado.values())

@router.put("/{orcamento_id}", response_model=OrcamentoResponse)
def update_orcamento(
    orcamento_id: int,
    orcamento_update: OrcamentoUpdate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_roles(["ADMIN", "ANALISTA", "GESTOR"]))
):
    orcamento = db.query(FatoOrcamento).filter(FatoOrcamento.id == orcamento_id).first()
    if not orcamento:
        raise HTTPException(status_code=404, detail="Orçamento não encontrado")
    
    for field, value in orcamento_update.model_dump(exclude_unset=True).items():
        setattr(orcamento, field, value)
    
    db.commit()
    db.refresh(orcamento)
    return orcamento

@router.delete("/{orcamento_id}")
def delete_orcamento(
    orcamento_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_roles(["ADMIN"]))
):
    orcamento = db.query(FatoOrcamento).filter(FatoOrcamento.id == orcamento_id).first()
    if not orcamento:
        raise HTTPException(status_code=404, detail="Orçamento não encontrado")
    
    db.delete(orcamento)
    db.commit()
    return {"message": "Orçamento excluído"}
