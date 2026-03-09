from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import distinct, extract
from typing import Optional
from ...core.database import get_db
from ...core.security import get_current_user
from ...models.dimensoes import DimTempo, DimProjeto
from ...models.cadastro_evento import CadastroEvento
from ...models.user import Usuario
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


def decimal_to_float(val):
    if isinstance(val, Decimal):
        return float(val)
    return val or 0


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


def build_project_filter(db, ano=None, mes=None, produto=None, tipo_evento=None,
                         projeto_id=None, modalidade=None, cidade=None):
    query = db.query(DimProjeto)
    if ano:
        query = query.filter(extract('year', DimProjeto.data_evento) == ano)
    if mes:
        query = query.filter(extract('month', DimProjeto.data_evento) == mes)
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
    return query.all()


def get_all_cadastros_map(db, projeto_ids):
    cadastros = db.query(CadastroEvento).filter(
        CadastroEvento.projeto_id.in_(projeto_ids)
    ).all()
    return {c.projeto_id: c for c in cadastros}


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


NOME_MES = ["", "Jan", "Fev", "Mar", "Abr", "Mai", "Jun",
            "Jul", "Ago", "Set", "Out", "Nov", "Dez"]


@router.get("/consolidado")
def get_dashboard_consolidado(
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
    projetos = build_project_filter(db, ano, mes, produto, tipo_evento, projeto_id, modalidade, cidade)
    projeto_ids = [p.id for p in projetos]
    cadastros_map = get_all_cadastros_map(db, projeto_ids) if projeto_ids else {}

    total_atletas_orcado = 0
    total_ticket_medio_sum = 0
    total_ticket_medio_count = 0
    total_capacidade = 0
    total_eventos = len(projetos)
    eventos_realizados = 0
    eventos_planejados = 0

    eventos_por_modalidade = {}
    eventos_por_cidade = {}
    eventos_por_estado = {}
    eventos_por_mes = {}
    eventos_por_produto = {}
    tabela_detalhada = []

    for p in projetos:
        cadastro = cadastros_map.get(p.id)

        atletas_orcado_site = int(cadastro.atletas_site_pago or 0) if cadastro else 0
        atletas_orcado_grupos = int(cadastro.atletas_grupos_pago or 0) if cadastro else 0
        atletas_cortesia = int(cadastro.atletas_cortesia or 0) if cadastro else 0
        atletas_orcado = atletas_orcado_site + atletas_orcado_grupos + atletas_cortesia

        if atletas_orcado == 0:
            atletas_orcado = int(p.capacidade_maxima or 0)

        tkt_medio_site = decimal_to_float(cadastro.atletas_site_tkt_medio) if cadastro else 0
        tkt_medio_grupos = decimal_to_float(cadastro.atletas_grupos_tkt_medio) if cadastro else 0

        tkt_medio = 0
        if atletas_orcado_site > 0 and atletas_orcado_grupos > 0:
            total_val = (tkt_medio_site * atletas_orcado_site) + (tkt_medio_grupos * atletas_orcado_grupos)
            total_qtd = atletas_orcado_site + atletas_orcado_grupos
            tkt_medio = total_val / total_qtd if total_qtd > 0 else 0
        elif atletas_orcado_site > 0:
            tkt_medio = tkt_medio_site
        elif atletas_orcado_grupos > 0:
            tkt_medio = tkt_medio_grupos

        capacidade = int(p.capacidade_maxima or 0)
        if capacidade == 0 and cadastro:
            capacidade = int(cadastro.capacidade_maxima or 0)

        status_evento = (cadastro.status if cadastro else p.status) or "Em andamento"
        is_realizado = status_evento.lower() in ['concluido', 'concluído', 'realizado']
        if is_realizado:
            eventos_realizados += 1
        else:
            eventos_planejados += 1

        total_atletas_orcado += atletas_orcado
        total_capacidade += capacidade

        if tkt_medio > 0:
            total_ticket_medio_sum += tkt_medio
            total_ticket_medio_count += 1

        mes_evento = p.data_evento.month if p.data_evento else 0
        mes_label = NOME_MES[mes_evento] if 0 < mes_evento <= 12 else "N/D"

        mod = p.modalidade or "N/D"
        eventos_por_modalidade[mod] = eventos_por_modalidade.get(mod, 0) + 1

        cid = p.cidade or "N/D"
        eventos_por_cidade[cid] = eventos_por_cidade.get(cid, 0) + 1

        est = p.estado or "N/D"
        eventos_por_estado[est] = eventos_por_estado.get(est, 0) + 1

        if mes_label != "N/D":
            if mes_label not in eventos_por_mes:
                eventos_por_mes[mes_label] = {"mes": mes_label, "mes_num": mes_evento, "orcado": 0, "eventos": 0}
            eventos_por_mes[mes_label]["orcado"] += atletas_orcado
            eventos_por_mes[mes_label]["eventos"] += 1

        prod = p.produto or "N/D"
        if prod not in eventos_por_produto:
            eventos_por_produto[prod] = {"produto": prod, "ticket_medio_sum": 0, "ticket_medio_count": 0, "atletas": 0, "eventos": 0}
        eventos_por_produto[prod]["atletas"] += atletas_orcado
        eventos_por_produto[prod]["eventos"] += 1
        if tkt_medio > 0:
            eventos_por_produto[prod]["ticket_medio_sum"] += tkt_medio
            eventos_por_produto[prod]["ticket_medio_count"] += 1

        taxa_ocupacao = round((atletas_orcado / capacidade * 100), 1) if capacidade > 0 else 0

        tabela_detalhada.append({
            "id": p.id,
            "evento": p.evento,
            "codigo": p.codigo,
            "data_evento": p.data_evento.isoformat() if p.data_evento else None,
            "cidade": p.cidade or "N/D",
            "estado": p.estado or "N/D",
            "modalidade": p.modalidade or "N/D",
            "produto": p.produto or "N/D",
            "tipo_evento": p.tipo_evento or "N/D",
            "status": status_evento,
            "capacidade": capacidade,
            "atletas_orcado": atletas_orcado,
            "atletas_site": atletas_orcado_site,
            "atletas_grupos": atletas_orcado_grupos,
            "atletas_cortesia": atletas_cortesia,
            "ticket_medio": round(tkt_medio, 2),
            "taxa_ocupacao": taxa_ocupacao,
        })

    ticket_medio_geral = round(total_ticket_medio_sum / total_ticket_medio_count, 2) if total_ticket_medio_count > 0 else 0
    taxa_ocupacao_media = round((total_atletas_orcado / total_capacidade * 100), 1) if total_capacidade > 0 else 0

    evolucao_mensal = sorted(eventos_por_mes.values(), key=lambda x: x["mes_num"])

    atletas_por_modalidade = [
        {"modalidade": k, "quantidade": v}
        for k, v in sorted(eventos_por_modalidade.items(), key=lambda x: x[1], reverse=True)
    ]

    top_eventos = sorted(tabela_detalhada, key=lambda x: x["atletas_orcado"], reverse=True)[:10]

    distribuicao_geografica = [
        {"cidade": k, "quantidade": v}
        for k, v in sorted(eventos_por_cidade.items(), key=lambda x: x[1], reverse=True)
    ][:15]

    distribuicao_estado = [
        {"estado": k, "quantidade": v}
        for k, v in sorted(eventos_por_estado.items(), key=lambda x: x[1], reverse=True)
    ]

    taxa_ocupacao_eventos = sorted(
        [{"evento": e["evento"], "taxa": e["taxa_ocupacao"], "atletas": e["atletas_orcado"], "capacidade": e["capacidade"]}
         for e in tabela_detalhada if e["capacidade"] > 0],
        key=lambda x: x["taxa"], reverse=True
    )

    ticket_medio_por_produto = [
        {
            "produto": v["produto"],
            "ticket_medio": round(v["ticket_medio_sum"] / v["ticket_medio_count"], 2) if v["ticket_medio_count"] > 0 else 0,
            "atletas": v["atletas"],
            "eventos": v["eventos"]
        }
        for v in eventos_por_produto.values()
        if v["ticket_medio_count"] > 0
    ]
    ticket_medio_por_produto.sort(key=lambda x: x["ticket_medio"], reverse=True)

    evento_destaque = max(tabela_detalhada, key=lambda x: x["atletas_orcado"]) if tabela_detalhada else None
    eventos_alerta = [e for e in tabela_detalhada if e["taxa_ocupacao"] < 50 and e["capacidade"] > 0]
    eventos_alerta.sort(key=lambda x: x["taxa_ocupacao"])

    return {
        "kpis": {
            "total_atletas_orcado": total_atletas_orcado,
            "total_eventos": total_eventos,
            "eventos_realizados": eventos_realizados,
            "eventos_planejados": eventos_planejados,
            "ticket_medio": ticket_medio_geral,
            "taxa_ocupacao_media": taxa_ocupacao_media,
            "total_capacidade": total_capacidade,
        },
        "evolucao_mensal": evolucao_mensal,
        "atletas_por_modalidade": atletas_por_modalidade,
        "top_eventos": [
            {"evento": e["evento"], "atletas": e["atletas_orcado"], "capacidade": e["capacidade"], "taxa_ocupacao": e["taxa_ocupacao"]}
            for e in top_eventos
        ],
        "distribuicao_geografica": distribuicao_geografica,
        "distribuicao_estado": distribuicao_estado,
        "taxa_ocupacao_eventos": taxa_ocupacao_eventos[:15],
        "ticket_medio_por_produto": ticket_medio_por_produto,
        "tabela_detalhada": tabela_detalhada,
        "insights": {
            "evento_destaque": {
                "evento": evento_destaque["evento"],
                "atletas": evento_destaque["atletas_orcado"],
                "cidade": evento_destaque["cidade"],
            } if evento_destaque else None,
            "eventos_alerta": [
                {"evento": e["evento"], "taxa_ocupacao": e["taxa_ocupacao"], "cidade": e["cidade"]}
                for e in eventos_alerta[:5]
            ],
            "total_modalidades": len(eventos_por_modalidade),
            "total_cidades": len(eventos_por_cidade),
        }
    }
