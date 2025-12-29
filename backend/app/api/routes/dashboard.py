from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from ...core.database import get_db
from ...core.security import get_current_user
from ...models.fatos import FatoOrcamento, FatoProjecao, FatoRealizado, FatoAtletas
from ...models.dimensoes import DimTempo, DimConta, DimProjeto, DimCategoriaAtleta
from ...models.user import Usuario

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])

@router.get("/resumo-geral")
async def get_resumo_geral(
    ano: int = 2025,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    orcado_receita = db.query(func.sum(FatoOrcamento.valor_orcado)).join(
        DimConta, FatoOrcamento.conta_id == DimConta.id
    ).filter(
        FatoOrcamento.ano_referencia == ano,
        DimConta.tipo == 'RECEITA'
    ).scalar() or 0

    orcado_despesa = db.query(func.sum(FatoOrcamento.valor_orcado)).join(
        DimConta, FatoOrcamento.conta_id == DimConta.id
    ).filter(
        FatoOrcamento.ano_referencia == ano,
        DimConta.tipo == 'DESPESA'
    ).scalar() or 0

    projetado_receita = db.query(func.sum(FatoProjecao.valor_projetado)).join(
        DimConta, FatoProjecao.conta_id == DimConta.id
    ).join(
        DimTempo, FatoProjecao.tempo_id == DimTempo.id
    ).filter(
        DimTempo.ano == ano,
        DimConta.tipo == 'RECEITA'
    ).scalar() or 0

    projetado_despesa = db.query(func.sum(FatoProjecao.valor_projetado)).join(
        DimConta, FatoProjecao.conta_id == DimConta.id
    ).join(
        DimTempo, FatoProjecao.tempo_id == DimTempo.id
    ).filter(
        DimTempo.ano == ano,
        DimConta.tipo == 'DESPESA'
    ).scalar() or 0

    realizado_receita = db.query(func.sum(FatoRealizado.valor_realizado)).join(
        DimConta, FatoRealizado.conta_id == DimConta.id
    ).join(
        DimTempo, FatoRealizado.tempo_id == DimTempo.id
    ).filter(
        DimTempo.ano == ano,
        DimConta.tipo == 'RECEITA'
    ).scalar() or 0

    realizado_despesa = db.query(func.sum(FatoRealizado.valor_realizado)).join(
        DimConta, FatoRealizado.conta_id == DimConta.id
    ).join(
        DimTempo, FatoRealizado.tempo_id == DimTempo.id
    ).filter(
        DimTempo.ano == ano,
        DimConta.tipo == 'DESPESA'
    ).scalar() or 0

    atletas_resumo = db.query(
        func.sum(FatoAtletas.qtd_atletas_orcado).label('orcado'),
        func.sum(FatoAtletas.qtd_atletas_projetado).label('projetado'),
        func.sum(FatoAtletas.qtd_atletas_realizado).label('realizado')
    ).first()

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
            "total_orcado": atletas_resumo.orcado or 0,
            "total_projetado": atletas_resumo.projetado or 0,
            "total_realizado": atletas_resumo.realizado or 0
        }
    }

@router.get("/evolucao-mensal")
async def get_evolucao_mensal(
    ano: int = 2025,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    orcado = db.query(
        DimTempo.mes,
        func.sum(FatoOrcamento.valor_orcado).label('total')
    ).join(
        DimTempo, FatoOrcamento.tempo_id == DimTempo.id
    ).filter(
        FatoOrcamento.ano_referencia == ano
    ).group_by(DimTempo.mes).all()

    realizado = db.query(
        DimTempo.mes,
        func.sum(FatoRealizado.valor_realizado).label('total')
    ).join(
        DimTempo, FatoRealizado.tempo_id == DimTempo.id
    ).filter(
        DimTempo.ano == ano
    ).group_by(DimTempo.mes).all()

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
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    dados = db.query(
        DimConta.tipo,
        func.sum(FatoRealizado.valor_realizado).label('total')
    ).join(
        DimConta, FatoRealizado.conta_id == DimConta.id
    ).join(
        DimTempo, FatoRealizado.tempo_id == DimTempo.id
    ).filter(
        DimTempo.ano == ano
    ).group_by(DimConta.tipo).all()

    return [{"tipo": d.tipo, "total": float(d.total)} for d in dados]

@router.get("/atletas-por-modalidade")
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

    return [{"modalidade": d.modalidade or "Não definida", "total": d.total or 0} for d in dados]

@router.get("/atletas-por-projeto")
async def get_atletas_por_projeto(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    dados = db.query(
        DimProjeto.evento,
        func.sum(FatoAtletas.qtd_atletas_orcado).label('orcado'),
        func.sum(FatoAtletas.qtd_atletas_projetado).label('projetado'),
        func.sum(FatoAtletas.qtd_atletas_realizado).label('realizado')
    ).join(
        DimProjeto, FatoAtletas.projeto_id == DimProjeto.id
    ).group_by(DimProjeto.id, DimProjeto.evento).all()

    return [
        {
            "evento": d.evento,
            "orcado": d.orcado or 0,
            "projetado": d.projetado or 0,
            "realizado": d.realizado or 0
        }
        for d in dados
    ]
