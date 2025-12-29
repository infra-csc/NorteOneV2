from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List
from ...core.database import get_db
from ...core.security import get_current_user, require_roles
from ...models.fatos import FatoAtletas
from ...models.dimensoes import DimProjeto, DimCategoriaAtleta
from ...models.user import Usuario
from ...schemas.fatos import AtletasCreate, AtletasUpdate, AtletasResponse

router = APIRouter(prefix="/atletas", tags=["Atletas"])

@router.get("/", response_model=List[AtletasResponse])
async def list_atletas(
    skip: int = 0,
    limit: int = 100,
    projeto_id: int = None,
    categoria_id: int = None,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    query = db.query(FatoAtletas)
    
    if projeto_id:
        query = query.filter(FatoAtletas.projeto_id == projeto_id)
    if categoria_id:
        query = query.filter(FatoAtletas.categoria_atleta_id == categoria_id)
    
    atletas = query.offset(skip).limit(limit).all()
    return atletas

@router.post("/", response_model=AtletasResponse)
async def create_atleta(
    atleta: AtletasCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_roles(["ADMIN", "ANALISTA", "GESTOR"]))
):
    db_atleta = FatoAtletas(**atleta.model_dump(), created_by=current_user.id)
    db.add(db_atleta)
    db.commit()
    db.refresh(db_atleta)
    return db_atleta

@router.get("/resumo")
async def get_resumo_atletas(
    projeto_id: int = None,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    query = db.query(
        func.sum(FatoAtletas.qtd_atletas_orcado).label('total_orcado'),
        func.sum(FatoAtletas.qtd_atletas_projetado).label('total_projetado'),
        func.sum(FatoAtletas.qtd_atletas_realizado).label('total_realizado'),
        func.sum(FatoAtletas.qtd_atletas_orcado * FatoAtletas.valor_inscricao_unitario).label('receita_orcada'),
        func.sum(FatoAtletas.qtd_atletas_realizado * FatoAtletas.valor_inscricao_unitario).label('receita_realizada'),
        func.sum(FatoAtletas.qtd_atletas_orcado * FatoAtletas.custo_kit_unitario_orcado).label('custo_kit_orcado'),
        func.sum(FatoAtletas.qtd_atletas_realizado * FatoAtletas.custo_kit_unitario_realizado).label('custo_kit_realizado')
    )
    
    if projeto_id:
        query = query.filter(FatoAtletas.projeto_id == projeto_id)
    
    resultado = query.first()
    
    total_orcado = resultado.total_orcado or 0
    total_realizado = resultado.total_realizado or 0
    variacao = 0
    if total_orcado > 0:
        variacao = ((total_realizado - total_orcado) / total_orcado) * 100
    
    return {
        "total_atletas_orcado": total_orcado,
        "total_atletas_projetado": resultado.total_projetado or 0,
        "total_atletas_realizado": total_realizado,
        "variacao_percentual": round(variacao, 2),
        "receita_orcada": float(resultado.receita_orcada or 0),
        "receita_realizada": float(resultado.receita_realizada or 0),
        "custo_kit_orcado": float(resultado.custo_kit_orcado or 0),
        "custo_kit_realizado": float(resultado.custo_kit_realizado or 0)
    }

@router.get("/por-projeto")
async def get_atletas_por_projeto(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    dados = db.query(
        DimProjeto.codigo,
        DimProjeto.evento,
        func.sum(FatoAtletas.qtd_atletas_orcado).label('orcado'),
        func.sum(FatoAtletas.qtd_atletas_projetado).label('projetado'),
        func.sum(FatoAtletas.qtd_atletas_realizado).label('realizado')
    ).join(
        DimProjeto, FatoAtletas.projeto_id == DimProjeto.id
    ).group_by(DimProjeto.id, DimProjeto.codigo, DimProjeto.evento).all()
    
    return [
        {
            "codigo": d.codigo,
            "evento": d.evento,
            "orcado": d.orcado or 0,
            "projetado": d.projetado or 0,
            "realizado": d.realizado or 0
        }
        for d in dados
    ]

@router.get("/por-modalidade")
async def get_atletas_por_modalidade(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    dados = db.query(
        DimCategoriaAtleta.modalidade,
        func.sum(FatoAtletas.qtd_atletas_realizado).label('total')
    ).join(
        DimCategoriaAtleta, FatoAtletas.categoria_atleta_id == DimCategoriaAtleta.id
    ).group_by(DimCategoriaAtleta.modalidade).all()
    
    return [
        {"modalidade": d.modalidade or "Não definida", "total": d.total or 0}
        for d in dados
    ]

@router.put("/{atleta_id}", response_model=AtletasResponse)
async def update_atleta(
    atleta_id: int,
    atleta_update: AtletasUpdate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_roles(["ADMIN", "ANALISTA", "GESTOR"]))
):
    atleta = db.query(FatoAtletas).filter(FatoAtletas.id == atleta_id).first()
    if not atleta:
        raise HTTPException(status_code=404, detail="Registro não encontrado")
    
    for field, value in atleta_update.model_dump(exclude_unset=True).items():
        setattr(atleta, field, value)
    
    db.commit()
    db.refresh(atleta)
    return atleta

@router.delete("/{atleta_id}")
async def delete_atleta(
    atleta_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_roles(["ADMIN"]))
):
    atleta = db.query(FatoAtletas).filter(FatoAtletas.id == atleta_id).first()
    if not atleta:
        raise HTTPException(status_code=404, detail="Registro não encontrado")
    
    db.delete(atleta)
    db.commit()
    return {"message": "Registro excluído"}
