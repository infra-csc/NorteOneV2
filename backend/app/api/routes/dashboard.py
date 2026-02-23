from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, distinct
from typing import Optional
from ...core.database import get_db
from ...core.security import get_current_user
from ...models.dimensoes import DimTempo, DimProjeto, DimCategoriaAtleta
from ...models.user import Usuario

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])

@router.get("/filtros")
def get_filtros(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    anos = db.query(distinct(DimTempo.ano)).order_by(DimTempo.ano.desc()).all()
    meses = [
        {"value": 1, "label": "Janeiro"},
        {"value": 2, "label": "Fevereiro"},
        {"value": 3, "label": "Marco"},
        {"value": 4, "label": "Abril"},
        {"value": 5, "label": "Maio"},
        {"value": 6, "label": "Junho"},
        {"value": 7, "label": "Julho"},
        {"value": 8, "label": "Agosto"},
        {"value": 9, "label": "Setembro"},
        {"value": 10, "label": "Outubro"},
        {"value": 11, "label": "Novembro"},
        {"value": 12, "label": "Dezembro"},
    ]
    
    produtos = db.query(distinct(DimProjeto.produto)).filter(DimProjeto.produto != None).all()
    tipos_evento = db.query(distinct(DimProjeto.tipo_evento)).filter(DimProjeto.tipo_evento != None).all()
    projetos = db.query(DimProjeto.id, DimProjeto.evento).all()
    modalidades = db.query(distinct(DimProjeto.modalidade)).filter(DimProjeto.modalidade != None).all()
    cidades = db.query(distinct(DimProjeto.cidade)).filter(DimProjeto.cidade != None).all()
    
    return {
        "anos": [{"value": a[0], "label": str(a[0])} for a in anos] or [{"value": 2025, "label": "2025"}],
        "meses": meses,
        "produtos": [{"value": p[0], "label": p[0]} for p in produtos],
        "tipos_evento": [{"value": t[0], "label": t[0]} for t in tipos_evento],
        "projetos": [{"value": p.id, "label": p.evento} for p in projetos],
        "modalidades": [{"value": m[0], "label": m[0]} for m in modalidades],
        "cidades": [{"value": c[0], "label": c[0]} for c in cidades]
    }

def get_projeto_ids_for_filters(db: Session, produto: str = None, tipo_evento: str = None, 
                                  projeto_id: int = None, modalidade: str = None, cidade: str = None):
    if not any([produto, tipo_evento, projeto_id, modalidade, cidade]):
        return None
    
    query = db.query(DimProjeto.id)
    if produto:
        query = query.filter(DimProjeto.produto == produto)
    if tipo_evento:
        query = query.filter(DimProjeto.tipo_evento == tipo_evento)
    if projeto_id:
        query = query.filter(DimProjeto.id == projeto_id)
    if modalidade:
        query = query.filter(DimProjeto.modalidade == modalidade)
    if cidade:
        query = query.filter(DimProjeto.cidade == cidade)
    
    return [p.id for p in query.all()]

@router.get("/resumo-geral")
def get_resumo_geral(
    ano: int = 2025,
    mes: Optional[int] = Query(None),
    produto: Optional[str] = Query(None),
    tipo_evento: Optional[str] = Query(None),
    projeto_id: Optional[int] = Query(None),
    modalidade: Optional[str] = Query(None),
    cidade: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    return {
        "ano": ano,
        "financeiro": {
            "orcado_receita": 0, "orcado_despesa": 0, "orcado_resultado": 0,
            "projetado_receita": 0, "projetado_despesa": 0, "projetado_resultado": 0,
            "realizado_receita": 0, "realizado_despesa": 0, "realizado_resultado": 0,
            "variacao_percentual": 0
        },
        "atletas": {"total_orcado": 0, "total_projetado": 0, "total_realizado": 0}
    }
