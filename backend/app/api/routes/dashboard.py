from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, distinct
from typing import Optional
from ...core.database import get_db
from ...core.security import get_current_user
from ...models.fatos import FatoOrcamento, FatoProjecao, FatoRealizado, FatoAtletasMetricas, FatoAtletasCanais
from ...models.dimensoes import DimTempo, DimConta, DimProjeto, DimCategoriaAtleta
from ...models.user import Usuario

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])

@router.get("/filtros")
async def get_filtros(
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
async def get_resumo_geral(
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
    projeto_ids = get_projeto_ids_for_filters(db, produto, tipo_evento, projeto_id, modalidade, cidade)
    
    orc_receita_query = db.query(func.sum(FatoOrcamento.valor_orcado)).join(
        DimConta, FatoOrcamento.conta_id == DimConta.id
    ).filter(FatoOrcamento.ano_referencia == ano, DimConta.tipo == 'RECEITA')
    
    orc_despesa_query = db.query(func.sum(FatoOrcamento.valor_orcado)).join(
        DimConta, FatoOrcamento.conta_id == DimConta.id
    ).filter(FatoOrcamento.ano_referencia == ano, DimConta.tipo == 'DESPESA')
    
    if mes:
        orc_receita_query = orc_receita_query.join(DimTempo, FatoOrcamento.tempo_id == DimTempo.id).filter(DimTempo.mes == mes)
        orc_despesa_query = orc_despesa_query.join(DimTempo, FatoOrcamento.tempo_id == DimTempo.id).filter(DimTempo.mes == mes)
    
    if projeto_ids is not None:
        orc_receita_query = orc_receita_query.filter(FatoOrcamento.projeto_id.in_(projeto_ids))
        orc_despesa_query = orc_despesa_query.filter(FatoOrcamento.projeto_id.in_(projeto_ids))
    
    orcado_receita = orc_receita_query.scalar() or 0
    orcado_despesa = orc_despesa_query.scalar() or 0

    proj_receita_query = db.query(func.sum(FatoProjecao.valor_projetado)).join(
        DimConta, FatoProjecao.conta_id == DimConta.id
    ).join(DimTempo, FatoProjecao.tempo_id == DimTempo.id).filter(DimTempo.ano == ano, DimConta.tipo == 'RECEITA')
    
    proj_despesa_query = db.query(func.sum(FatoProjecao.valor_projetado)).join(
        DimConta, FatoProjecao.conta_id == DimConta.id
    ).join(DimTempo, FatoProjecao.tempo_id == DimTempo.id).filter(DimTempo.ano == ano, DimConta.tipo == 'DESPESA')
    
    if mes:
        proj_receita_query = proj_receita_query.filter(DimTempo.mes == mes)
        proj_despesa_query = proj_despesa_query.filter(DimTempo.mes == mes)
    
    if projeto_ids is not None:
        proj_receita_query = proj_receita_query.filter(FatoProjecao.projeto_id.in_(projeto_ids))
        proj_despesa_query = proj_despesa_query.filter(FatoProjecao.projeto_id.in_(projeto_ids))
    
    projetado_receita = proj_receita_query.scalar() or 0
    projetado_despesa = proj_despesa_query.scalar() or 0

    real_receita_query = db.query(func.sum(FatoRealizado.valor_realizado)).join(
        DimConta, FatoRealizado.conta_id == DimConta.id
    ).join(DimTempo, FatoRealizado.tempo_id == DimTempo.id).filter(DimTempo.ano == ano, DimConta.tipo == 'RECEITA')
    
    real_despesa_query = db.query(func.sum(FatoRealizado.valor_realizado)).join(
        DimConta, FatoRealizado.conta_id == DimConta.id
    ).join(DimTempo, FatoRealizado.tempo_id == DimTempo.id).filter(DimTempo.ano == ano, DimConta.tipo == 'DESPESA')
    
    if mes:
        real_receita_query = real_receita_query.filter(DimTempo.mes == mes)
        real_despesa_query = real_despesa_query.filter(DimTempo.mes == mes)
    
    if projeto_ids is not None:
        real_receita_query = real_receita_query.filter(FatoRealizado.projeto_id.in_(projeto_ids))
        real_despesa_query = real_despesa_query.filter(FatoRealizado.projeto_id.in_(projeto_ids))
    
    realizado_receita = real_receita_query.scalar() or 0
    realizado_despesa = real_despesa_query.scalar() or 0

    atletas_orcado_query = db.query(func.sum(FatoAtletasMetricas.qtd_atletas)).filter(
        FatoAtletasMetricas.cenario == 'ORCADO'
    )
    atletas_projetado_query = db.query(func.sum(FatoAtletasMetricas.qtd_atletas)).filter(
        FatoAtletasMetricas.cenario == 'PROJETADO'
    )
    atletas_realizado_query = db.query(func.sum(FatoAtletasMetricas.qtd_atletas)).filter(
        FatoAtletasMetricas.cenario == 'REALIZADO'
    )
    
    if projeto_ids is not None:
        atletas_orcado_query = atletas_orcado_query.filter(FatoAtletasMetricas.projeto_id.in_(projeto_ids))
        atletas_projetado_query = atletas_projetado_query.filter(FatoAtletasMetricas.projeto_id.in_(projeto_ids))
        atletas_realizado_query = atletas_realizado_query.filter(FatoAtletasMetricas.projeto_id.in_(projeto_ids))
    
    atletas_orcado = atletas_orcado_query.scalar() or 0
    atletas_projetado = atletas_projetado_query.scalar() or 0
    atletas_realizado = atletas_realizado_query.scalar() or 0

    total_orcado = float(orcado_receita) - float(orcado_despesa)
    total_realizado = float(realizado_receita) - float(realizado_despesa)
    variacao = 0
    if total_orcado != 0:
        variacao = ((total_realizado - total_orcado) / abs(total_orcado)) * 100

    return {
        "ano": ano,
        "financeiro": {
            "orcado_receita": float(orcado_receita),
            "orcado_despesa": float(orcado_despesa),
            "orcado_resultado": total_orcado,
            "projetado_receita": float(projetado_receita),
            "projetado_despesa": float(projetado_despesa),
            "projetado_resultado": float(projetado_receita) - float(projetado_despesa),
            "realizado_receita": float(realizado_receita),
            "realizado_despesa": float(realizado_despesa),
            "realizado_resultado": total_realizado,
            "variacao_percentual": round(variacao, 2)
        },
        "atletas": {
            "total_orcado": atletas_orcado,
            "total_projetado": atletas_projetado,
            "total_realizado": atletas_realizado
        }
    }

@router.get("/evolucao-mensal")
async def get_evolucao_mensal(
    ano: int = 2025,
    produto: Optional[str] = Query(None),
    tipo_evento: Optional[str] = Query(None),
    projeto_id: Optional[int] = Query(None),
    modalidade: Optional[str] = Query(None),
    cidade: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    projeto_ids = get_projeto_ids_for_filters(db, produto, tipo_evento, projeto_id, modalidade, cidade)
    
    orc_query = db.query(
        DimTempo.mes,
        func.sum(FatoOrcamento.valor_orcado).label('total')
    ).join(DimTempo, FatoOrcamento.tempo_id == DimTempo.id).filter(FatoOrcamento.ano_referencia == ano)
    
    if projeto_ids is not None:
        orc_query = orc_query.filter(FatoOrcamento.projeto_id.in_(projeto_ids))
    
    orcado = orc_query.group_by(DimTempo.mes).all()

    real_query = db.query(
        DimTempo.mes,
        func.sum(FatoRealizado.valor_realizado).label('total')
    ).join(DimTempo, FatoRealizado.tempo_id == DimTempo.id).filter(DimTempo.ano == ano)
    
    if projeto_ids is not None:
        real_query = real_query.filter(FatoRealizado.projeto_id.in_(projeto_ids))
    
    realizado = real_query.group_by(DimTempo.mes).all()

    orcado_dict = {o.mes: float(o.total) for o in orcado}
    realizado_dict = {r.mes: float(r.total) for r in realizado}

    meses = ['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez']
    resultado = []
    for i in range(1, 13):
        resultado.append({
            "mes": meses[i-1],
            "orcado": orcado_dict.get(i, 0),
            "realizado": realizado_dict.get(i, 0)
        })
    
    return resultado

@router.get("/distribuicao-tipo")
async def get_distribuicao_tipo(
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
    projeto_ids = get_projeto_ids_for_filters(db, produto, tipo_evento, projeto_id, modalidade, cidade)
    
    query = db.query(
        DimConta.tipo,
        func.sum(FatoRealizado.valor_realizado).label('total')
    ).join(DimConta, FatoRealizado.conta_id == DimConta.id
    ).join(DimTempo, FatoRealizado.tempo_id == DimTempo.id
    ).filter(DimTempo.ano == ano)
    
    if mes:
        query = query.filter(DimTempo.mes == mes)
    
    if projeto_ids is not None:
        query = query.filter(FatoRealizado.projeto_id.in_(projeto_ids))
    
    dados = query.group_by(DimConta.tipo).all()

    return [{"tipo": d.tipo, "total": float(d.total)} for d in dados]

@router.get("/atletas-por-modalidade")
async def get_atletas_por_modalidade(
    produto: Optional[str] = Query(None),
    tipo_evento: Optional[str] = Query(None),
    projeto_id: Optional[int] = Query(None),
    modalidade: Optional[str] = Query(None),
    cidade: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    projeto_ids = get_projeto_ids_for_filters(db, produto, tipo_evento, projeto_id, modalidade, cidade)
    
    query = db.query(
        DimCategoriaAtleta.modalidade,
        func.sum(FatoAtletasMetricas.qtd_atletas).label('total')
    ).join(DimCategoriaAtleta, FatoAtletasMetricas.categoria_atleta_id == DimCategoriaAtleta.id
    ).filter(FatoAtletasMetricas.cenario == 'REALIZADO')
    
    if projeto_ids is not None:
        query = query.filter(FatoAtletasMetricas.projeto_id.in_(projeto_ids))
    
    dados = query.group_by(DimCategoriaAtleta.modalidade).all()

    return [{"modalidade": d.modalidade or "Nao definida", "total": d.total or 0} for d in dados]

@router.get("/atletas-por-projeto")
async def get_atletas_por_projeto(
    produto: Optional[str] = Query(None),
    tipo_evento: Optional[str] = Query(None),
    projeto_id: Optional[int] = Query(None),
    modalidade: Optional[str] = Query(None),
    cidade: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    projeto_ids = get_projeto_ids_for_filters(db, produto, tipo_evento, projeto_id, modalidade, cidade)
    
    query = db.query(
        DimProjeto.evento,
        FatoAtletasMetricas.cenario,
        func.sum(FatoAtletasMetricas.qtd_atletas).label('total')
    ).join(DimProjeto, FatoAtletasMetricas.projeto_id == DimProjeto.id)
    
    if projeto_ids is not None:
        query = query.filter(FatoAtletasMetricas.projeto_id.in_(projeto_ids))
    
    dados = query.group_by(DimProjeto.id, DimProjeto.evento, FatoAtletasMetricas.cenario).all()

    projetos_dict = {}
    for d in dados:
        if d.evento not in projetos_dict:
            projetos_dict[d.evento] = {"evento": d.evento, "orcado": 0, "projetado": 0, "realizado": 0}
        
        if d.cenario == 'ORCADO':
            projetos_dict[d.evento]["orcado"] = d.total or 0
        elif d.cenario == 'PROJETADO':
            projetos_dict[d.evento]["projetado"] = d.total or 0
        elif d.cenario == 'REALIZADO':
            projetos_dict[d.evento]["realizado"] = d.total or 0

    return list(projetos_dict.values())
