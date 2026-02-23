from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from ...core.database import get_db
from ...core.security import get_current_user, require_permission
from ...models.fatos import FatoAtletasMetricas, FatoAtletasCanais
from ...models.dimensoes import DimProjeto, DimCategoriaAtleta
from ...models.user import Usuario
from ...schemas.fatos import AtletasMetricasCreate, AtletasMetricasUpdate, AtletasMetricasResponse

router = APIRouter(prefix="/atletas", tags=["Atletas"])

@router.get("/", response_model=List[AtletasMetricasResponse])
def list_atletas(
    skip: int = 0,
    limit: int = 100,
    projeto_id: Optional[int] = Query(None, description="Filtrar por projeto"),
    categoria_id: Optional[int] = Query(None, description="Filtrar por categoria de atleta"),
    cenario: Optional[str] = Query(None, description="Filtrar por cenário: ORCADO, PROJETADO, REALIZADO"),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    query = db.query(FatoAtletasMetricas)
    
    if projeto_id:
        query = query.filter(FatoAtletasMetricas.projeto_id == projeto_id)
    if categoria_id:
        query = query.filter(FatoAtletasMetricas.categoria_atleta_id == categoria_id)
    if cenario:
        query = query.filter(FatoAtletasMetricas.cenario == cenario)
    
    atletas = query.offset(skip).limit(limit).all()
    return atletas

@router.post("/", response_model=AtletasMetricasResponse)
def create_atleta(
    atleta: AtletasMetricasCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("atletas", "pode_criar"))
):
    projeto = db.query(DimProjeto).filter(DimProjeto.id == atleta.projeto_id).first()
    if not projeto:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")
    
    db_atleta = FatoAtletasMetricas(**atleta.model_dump(), created_by=current_user.id)
    db.add(db_atleta)
    db.commit()
    db.refresh(db_atleta)
    return db_atleta

@router.get("/resumo")
def get_resumo_atletas(
    projeto_id: Optional[int] = Query(None, description="Filtrar por projeto"),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    orcado_query = db.query(func.sum(FatoAtletasMetricas.qtd_atletas)).filter(
        FatoAtletasMetricas.cenario == 'ORCADO'
    )
    projetado_query = db.query(func.sum(FatoAtletasMetricas.qtd_atletas)).filter(
        FatoAtletasMetricas.cenario == 'PROJETADO'
    )
    realizado_query = db.query(func.sum(FatoAtletasMetricas.qtd_atletas)).filter(
        FatoAtletasMetricas.cenario == 'REALIZADO'
    )
    
    inscricao_orcada_query = db.query(func.sum(FatoAtletasMetricas.qtd_atletas * FatoAtletasMetricas.inscricao)).filter(
        FatoAtletasMetricas.cenario == 'ORCADO'
    )
    inscricao_realizada_query = db.query(func.sum(FatoAtletasMetricas.qtd_atletas * FatoAtletasMetricas.inscricao)).filter(
        FatoAtletasMetricas.cenario == 'REALIZADO'
    )
    custo_kit_orcado_query = db.query(func.sum(FatoAtletasMetricas.qtd_atletas * FatoAtletasMetricas.custo_kit_unitario)).filter(
        FatoAtletasMetricas.cenario == 'ORCADO'
    )
    custo_kit_realizado_query = db.query(func.sum(FatoAtletasMetricas.qtd_atletas * FatoAtletasMetricas.custo_kit_unitario)).filter(
        FatoAtletasMetricas.cenario == 'REALIZADO'
    )
    
    if projeto_id:
        orcado_query = orcado_query.filter(FatoAtletasMetricas.projeto_id == projeto_id)
        projetado_query = projetado_query.filter(FatoAtletasMetricas.projeto_id == projeto_id)
        realizado_query = realizado_query.filter(FatoAtletasMetricas.projeto_id == projeto_id)
        inscricao_orcada_query = inscricao_orcada_query.filter(FatoAtletasMetricas.projeto_id == projeto_id)
        inscricao_realizada_query = inscricao_realizada_query.filter(FatoAtletasMetricas.projeto_id == projeto_id)
        custo_kit_orcado_query = custo_kit_orcado_query.filter(FatoAtletasMetricas.projeto_id == projeto_id)
        custo_kit_realizado_query = custo_kit_realizado_query.filter(FatoAtletasMetricas.projeto_id == projeto_id)
    
    total_orcado = orcado_query.scalar() or 0
    total_projetado = projetado_query.scalar() or 0
    total_realizado = realizado_query.scalar() or 0
    receita_orcada = inscricao_orcada_query.scalar() or 0
    receita_realizada = inscricao_realizada_query.scalar() or 0
    custo_kit_orcado = custo_kit_orcado_query.scalar() or 0
    custo_kit_realizado = custo_kit_realizado_query.scalar() or 0
    
    variacao = 0
    if total_orcado > 0:
        variacao = ((total_realizado - total_orcado) / total_orcado) * 100
    
    return {
        "total_atletas_orcado": total_orcado,
        "total_atletas_projetado": total_projetado,
        "total_atletas_realizado": total_realizado,
        "variacao_percentual": round(variacao, 2),
        "receita_orcada": float(receita_orcada),
        "receita_realizada": float(receita_realizada),
        "custo_kit_orcado": float(custo_kit_orcado),
        "custo_kit_realizado": float(custo_kit_realizado)
    }

@router.get("/por-projeto")
def get_atletas_por_projeto(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    dados = db.query(
        DimProjeto.codigo,
        DimProjeto.evento,
        FatoAtletasMetricas.cenario,
        func.sum(FatoAtletasMetricas.qtd_atletas).label('total')
    ).join(
        DimProjeto, FatoAtletasMetricas.projeto_id == DimProjeto.id
    ).group_by(DimProjeto.id, DimProjeto.codigo, DimProjeto.evento, FatoAtletasMetricas.cenario).all()
    
    projetos_dict = {}
    for d in dados:
        key = (d.codigo, d.evento)
        if key not in projetos_dict:
            projetos_dict[key] = {"codigo": d.codigo, "evento": d.evento, "orcado": 0, "projetado": 0, "realizado": 0}
        
        if d.cenario == 'ORCADO':
            projetos_dict[key]["orcado"] = d.total or 0
        elif d.cenario == 'PROJETADO':
            projetos_dict[key]["projetado"] = d.total or 0
        elif d.cenario == 'REALIZADO':
            projetos_dict[key]["realizado"] = d.total or 0
    
    return list(projetos_dict.values())

@router.get("/por-modalidade")
def get_atletas_por_modalidade(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    dados = db.query(
        DimCategoriaAtleta.modalidade,
        func.sum(FatoAtletasMetricas.qtd_atletas).label('total')
    ).join(
        DimCategoriaAtleta, FatoAtletasMetricas.categoria_atleta_id == DimCategoriaAtleta.id
    ).filter(FatoAtletasMetricas.cenario == 'REALIZADO'
    ).group_by(DimCategoriaAtleta.modalidade).all()
    
    return [
        {"modalidade": d.modalidade or "Não definida", "total": d.total or 0}
        for d in dados
    ]

@router.put("/{atleta_id}", response_model=AtletasMetricasResponse)
def update_atleta(
    atleta_id: int,
    atleta_update: AtletasMetricasUpdate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("atletas", "pode_editar"))
):
    atleta = db.query(FatoAtletasMetricas).filter(FatoAtletasMetricas.id == atleta_id).first()
    if not atleta:
        raise HTTPException(status_code=404, detail="Registro não encontrado")
    
    for field, value in atleta_update.model_dump(exclude_unset=True).items():
        setattr(atleta, field, value)
    
    db.commit()
    db.refresh(atleta)
    return atleta

@router.delete("/{atleta_id}")
def delete_atleta(
    atleta_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("atletas", "pode_deletar"))
):
    atleta = db.query(FatoAtletasMetricas).filter(FatoAtletasMetricas.id == atleta_id).first()
    if not atleta:
        raise HTTPException(status_code=404, detail="Registro não encontrado")
    
    db.delete(atleta)
    db.commit()
    return {"message": "Registro excluído"}
