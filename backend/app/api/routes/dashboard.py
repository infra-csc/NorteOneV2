from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func as sa_func
from typing import Optional
from datetime import date, timedelta, datetime as _datetime
_CURRENT_YEAR = _datetime.now().year
import threading
import time as _time
from ...core.database import get_db
from ...core.security import is_user_admin, require_permission
from ...models.dimensoes import DimProjeto
from ...models.cadastro_evento import CadastroEvento, CadastroKitProduto, CadastroKitProdutoItem
from ...models.user import Usuario
from ...models.perfil_acesso import PerfilPermissaoCampo
from decimal import Decimal

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])
_FILTROS_CACHE_TTL = 300
_filtros_cache = {"data": None, "ts": 0.0}
_filtros_cache_lock = threading.Lock()


def decimal_to_float(val):
    if isinstance(val, Decimal):
        return float(val)
    return val or 0


def _date_range_for_filters(ano=None, mes=None):
    if not ano:
        return None, None
    start_month = int(mes or 1)
    start = date(int(ano), start_month, 1)
    if mes:
        if start_month == 12:
            end = date(int(ano) + 1, 1, 1)
        else:
            end = date(int(ano), start_month + 1, 1)
    else:
        end = date(int(ano) + 1, 1, 1)
    return start, end


def user_can_view_campo(db: Session, user: Usuario, entidade: str, campo: str) -> bool:
    if is_user_admin(user):
        return True
    if not user.perfil_acesso_id:
        return False
    record = db.query(PerfilPermissaoCampo).filter(
        PerfilPermissaoCampo.perfil_acesso_id == user.perfil_acesso_id,
        PerfilPermissaoCampo.entidade == entidade,
        PerfilPermissaoCampo.campo == campo,
    ).first()
    if record is None:
        return False
    return record.pode_visualizar


@router.get("/filtros")
def get_filtros(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("dashboard", "pode_visualizar"))
):
    now = _time.time()
    with _filtros_cache_lock:
        cached = _filtros_cache["data"]
        if cached is not None and (now - _filtros_cache["ts"]) < _FILTROS_CACHE_TTL:
            return cached

    from datetime import datetime as _dt
    _cur_year = _dt.now().year
    rows = (
        db.query(
            DimProjeto.id,
            DimProjeto.evento,
            DimProjeto.data_evento,
            DimProjeto.produto,
            DimProjeto.tipo_evento,
            DimProjeto.modalidade,
            DimProjeto.cidade,
        )
        .order_by(DimProjeto.evento)
        .all()
    )
    anos = sorted({r.data_evento.year for r in rows if r.data_evento}, reverse=True) or [_cur_year]
    produtos = sorted({r.produto for r in rows if r.produto})
    tipos_evento = sorted({r.tipo_evento for r in rows if r.tipo_evento})
    modalidades = sorted({r.modalidade for r in rows if r.modalidade})
    cidades = sorted({r.cidade for r in rows if r.cidade})
    meses = [
        {"value": 1, "label": "Janeiro"},
        {"value": 2, "label": "Fevereiro"},
        {"value": 3, "label": "Março"},
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

    result = {
        "anos": [{"value": int(ano), "label": str(int(ano))} for ano in anos],
        "meses": meses,
        "produtos": [{"value": produto, "label": produto} for produto in produtos],
        "tipos_evento": [{"value": tipo, "label": tipo} for tipo in tipos_evento],
        "projetos": [{"value": r.id, "label": r.evento} for r in rows],
        "modalidades": [{"value": modalidade, "label": modalidade} for modalidade in modalidades],
        "cidades": [{"value": cidade, "label": cidade} for cidade in cidades]
    }
    with _filtros_cache_lock:
        _filtros_cache["data"] = result
        _filtros_cache["ts"] = now
    return result


def build_project_filter(db, ano=None, mes=None, produto=None, tipo_evento=None,
                         projeto_id=None, modalidade=None, cidade=None):
    query = db.query(DimProjeto)
    start_date, end_date = _date_range_for_filters(ano, mes)
    if start_date and end_date:
        query = query.filter(
            DimProjeto.data_evento >= start_date,
            DimProjeto.data_evento < end_date,
        )
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
    if not projeto_ids:
        return {}
    cadastros = db.query(CadastroEvento).filter(
        CadastroEvento.projeto_id.in_(projeto_ids),
        CadastroEvento.deleted_at == None
    ).all()
    return {c.projeto_id: c for c in cadastros}


def get_kit_costs_map(db, cadastro_ids):
    if not cadastro_ids:
        return {}
    rows = db.query(
        CadastroKitProduto.cadastro_id,
        sa_func.sum(CadastroKitProdutoItem.valor_unitario).label("custo_total")
    ).join(
        CadastroKitProdutoItem, CadastroKitProdutoItem.kit_produto_id == CadastroKitProduto.id
    ).filter(
        CadastroKitProduto.cadastro_id.in_(cadastro_ids)
    ).group_by(CadastroKitProduto.cadastro_id).all()
    return {r.cadastro_id: float(r.custo_total or 0) for r in rows}


def compute_event_metrics(projetos, cadastros_map, kit_costs_map=None):
    events = []
    for p in projetos:
        cadastro = cadastros_map.get(p.id)

        atletas_site = int(cadastro.atletas_site_pago or 0) if cadastro else 0
        atletas_grupos = int(cadastro.atletas_grupos_pago or 0) if cadastro else 0
        atletas_cortesia = int(cadastro.atletas_cortesia or 0) if cadastro else 0
        atletas_total = atletas_site + atletas_grupos + atletas_cortesia

        if atletas_total == 0:
            atletas_total = int(p.capacidade_maxima or 0)

        tkt_site = decimal_to_float(cadastro.atletas_site_tkt_medio) if cadastro else 0
        tkt_grupos = decimal_to_float(cadastro.atletas_grupos_tkt_medio) if cadastro else 0

        tkt_medio = 0
        if atletas_site > 0 and atletas_grupos > 0:
            tkt_medio = ((tkt_site * atletas_site) + (tkt_grupos * atletas_grupos)) / (atletas_site + atletas_grupos)
        elif atletas_site > 0:
            tkt_medio = tkt_site
        elif atletas_grupos > 0:
            tkt_medio = tkt_grupos

        capacidade = int(p.capacidade_maxima or 0)
        if capacidade == 0 and cadastro:
            capacidade = int(cadastro.capacidade_maxima or 0)

        taxa_ocupacao = round((atletas_total / capacidade * 100), 1) if capacidade > 0 else 0

        status = (cadastro.status if cadastro else p.status) or "Em andamento"

        custo_kit = 0
        if kit_costs_map and cadastro:
            custo_kit = kit_costs_map.get(cadastro.id, 0)

        receita_projetada = round(atletas_total * tkt_medio, 2) if atletas_total > 0 and tkt_medio > 0 else 0
        margem_liquida = round(tkt_medio - custo_kit, 2) if tkt_medio > 0 else 0
        percentual_margem = round((margem_liquida / tkt_medio * 100), 1) if tkt_medio > 0 else 0

        events.append({
            "id": p.id,
            "evento": p.evento,
            "codigo": p.codigo,
            "data_evento": p.data_evento,
            "cidade": p.cidade or "N/D",
            "estado": p.estado or "N/D",
            "modalidade": p.modalidade or "N/D",
            "produto": p.produto or "N/D",
            "tipo_evento": p.tipo_evento or "N/D",
            "status": status,
            "capacidade": capacidade,
            "atletas_orcado": atletas_total,
            "atletas_site": atletas_site,
            "atletas_grupos": atletas_grupos,
            "atletas_cortesia": atletas_cortesia,
            "ticket_medio": round(tkt_medio, 2),
            "taxa_ocupacao": taxa_ocupacao,
            "custo_kit": round(custo_kit, 2),
            "receita_projetada": receita_projetada,
            "margem_liquida": margem_liquida,
            "percentual_margem": percentual_margem,
        })
    return events


NOME_MES = ["", "Jan", "Fev", "Mar", "Abr", "Mai", "Jun",
            "Jul", "Ago", "Set", "Out", "Nov", "Dez"]


@router.get("/resumo-geral")
def get_resumo_geral(
    ano: int = _CURRENT_YEAR,
    mes: Optional[int] = Query(None),
    produto: Optional[str] = Query(None),
    tipo_evento: Optional[str] = Query(None),
    projeto_id: Optional[int] = Query(None),
    modalidade: Optional[str] = Query(None),
    cidade: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("dashboard", "pode_visualizar"))
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


@router.get("/operacional")
def get_dashboard_operacional(
    ano: int = _CURRENT_YEAR,
    mes: Optional[int] = Query(None),
    produto: Optional[str] = Query(None),
    modalidade: Optional[str] = Query(None),
    cidade: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("dashboard", "pode_visualizar"))
):
    from .marketing import (
        fetch_isc_pricing_data, _build_sku_to_grupo_map, _get_isc_settings,
        calculate_isc_components, calculate_isc, get_isc_status,
        get_meta_from_cadastro, get_meta_orcada, calculate_d_minus,
        get_dias_encerramento, get_data_regime, normalize_sku,
        _get_snapshot_metrics_for_grupo, today_brazil
    )
    from sqlalchemy import case as sa_case, or_, and_
    from ...models.vendas_snapshot import VendasDiariaSnapshot
    from ...models.projecao import ProjecaoInscritos

    projetos = build_project_filter(db, ano=ano, mes=mes, produto=produto, modalidade=modalidade, cidade=cidade)
    projeto_ids = [p.id for p in projetos]
    cadastros_map = get_all_cadastros_map(db, projeto_ids)

    # --- Sum projected registrations per cadastro_evento.id (with per-area breakdown) ---
    projecoes_por_cadastro: dict = {}
    projecoes_por_area_detail: dict = {}   # {evento_id: [{area: nome, quantidade: int}, ...]}
    projecoes_site_por_cadastro: dict = {}  # {evento_id: int} — only "Site" area
    cadastro_ids_for_proj = [c.id for c in cadastros_map.values()]
    if cadastro_ids_for_proj:
        try:
            from ...models.projecao import AreaProjecao as AreaProjecaoModel
            proj_area_rows = db.query(
                ProjecaoInscritos.evento_id,
                AreaProjecaoModel.nome.label("area_nome"),
                sa_func.coalesce(sa_func.sum(ProjecaoInscritos.quantidade), 0).label("total"),
            ).join(
                AreaProjecaoModel, ProjecaoInscritos.area_projecao_id == AreaProjecaoModel.id
            ).filter(
                ProjecaoInscritos.evento_id.in_(cadastro_ids_for_proj),
                ProjecaoInscritos.deleted_at.is_(None),
            ).group_by(ProjecaoInscritos.evento_id, AreaProjecaoModel.nome).all()
            for r in proj_area_rows:
                eid = r.evento_id
                qty = int(r.total or 0)
                projecoes_por_cadastro[eid] = projecoes_por_cadastro.get(eid, 0) + qty
                if eid not in projecoes_por_area_detail:
                    projecoes_por_area_detail[eid] = []
                projecoes_por_area_detail[eid].append({"area": r.area_nome, "quantidade": qty})
                if r.area_nome == "Site":
                    projecoes_site_por_cadastro[eid] = qty
        except Exception:
            projecoes_por_cadastro = {}
            projecoes_por_area_detail = {}
            projecoes_site_por_cadastro = {}

    isc_cfg = _get_isc_settings(db)
    isc_data = fetch_isc_pricing_data(db=db, force_refresh=False)
    sku_to_grupo = _build_sku_to_grupo_map(db, ano)

    today = today_brazil()
    yesterday = today - timedelta(days=1)
    window_end = today + timedelta(days=28)

    # --- Per-grupo daily snapshot rollup (hoje/ontem/total) for the inscrições table ---
    # Restricted to grupos relevant to the filtered projetos and to the dashboard's `ano`
    # (matches the pattern used by snapshot_service.get_isc_totals_from_snapshot).
    grupos_relevantes: set = set()
    for _p in projetos:
        _sku_raw = str(_p.codigo) if _p.codigo else None
        _sku_norm = normalize_sku(_sku_raw) if _sku_raw else None
        _g = sku_to_grupo.get(_sku_norm) if _sku_norm else None
        if _g:
            grupos_relevantes.add(_g)

    snapshot_grupo_map: dict = {}
    if grupos_relevantes:
        try:
            year_end = date(ano + 1, 1, 1)
            presale_start = date(ano - 1, 9, 1)
            snap_rows = db.query(
                VendasDiariaSnapshot.evento_grupo,
                sa_func.sum(sa_case(
                    (VendasDiariaSnapshot.data_venda == today, VendasDiariaSnapshot.quantidade), else_=0
                )).label("hoje"),
                sa_func.sum(sa_case(
                    (VendasDiariaSnapshot.data_venda == yesterday, VendasDiariaSnapshot.quantidade), else_=0
                )).label("ontem"),
                sa_func.sum(VendasDiariaSnapshot.quantidade).label("total"),
            ).filter(
                VendasDiariaSnapshot.evento_grupo.in_(grupos_relevantes),
                # Mesma semântica do helper _ano_filter_for_snapshot: ano
                # preenchido deve bater exatamente; legado NULL só dentro da
                # janela pré-venda + ano. Evita somar edições diferentes do
                # mesmo grupo (regressão de duplicação reportada).
                or_(
                    VendasDiariaSnapshot.ano == ano,
                    and_(
                        VendasDiariaSnapshot.ano.is_(None),
                        VendasDiariaSnapshot.data_venda >= presale_start,
                        VendasDiariaSnapshot.data_venda <  year_end,
                    )
                )
            ).group_by(VendasDiariaSnapshot.evento_grupo).all()
            for r in snap_rows:
                snapshot_grupo_map[r.evento_grupo] = {
                    "hoje": int(r.hoje or 0),
                    "ontem": int(r.ontem or 0),
                    "total": int(r.total or 0),
                }
        except Exception:
            snapshot_grupo_map = {}

    tabela_eventos: list = []

    total_atletas_orcado = 0
    total_atletas_confirmados = 0
    total_capacidade = 0
    total_eventos = len(projetos)

    isc_acelerando = 0
    isc_estavel = 0
    isc_desacelerando = 0

    upcoming_events = []
    baixa_ocupacao = []
    sellout_candidates = []
    top_por_velocity = []
    atletas_por_modalidade: dict = {}

    for p in projetos:
        cadastro = cadastros_map.get(p.id)
        projeto_codigo = str(p.codigo) if p.codigo else None

        # Capacidade = Total Geral de Atletas do cadastro (site + grupos + cortesia + appai)
        if cadastro:
            cap = (
                int(cadastro.atletas_site_pago or 0) +
                int(cadastro.atletas_grupos_pago or 0) +
                int(cadastro.atletas_cortesia or 0) +
                int(getattr(cadastro, "atletas_appai_pago", 0) or 0)
            )
        else:
            cap = get_meta_orcada(db, p.id)
        total_capacidade += cap

        sku_norm = normalize_sku(projeto_codigo) if projeto_codigo else None
        grupo_nome = sku_to_grupo.get(sku_norm) if sku_norm else None

        dias_enc = get_dias_encerramento(db, projeto_id=p.id, cadastro=cadastro)
        d_minus_inscricoes = calculate_d_minus(p.data_evento, dias_encerramento=dias_enc) if p.data_evento else 0
        regime = get_data_regime(p.data_evento, dias_enc) if p.data_evento else "live"

        current_sales = 0
        m7d = 0.0
        m14d = 0.0
        m30d = 0.0

        if regime == "consolidated" and grupo_nome:
            snap = _get_snapshot_metrics_for_grupo(db, grupo_nome, ano=ano)
            if snap:
                current_sales = snap.get("qtd_site", 0)
        else:
            if sku_norm and sku_norm in isc_data:
                current_sales = isc_data[sku_norm].get("qtd_site", 0)
                m7d = isc_data[sku_norm].get("media_7d", 0.0)
                m14d = isc_data[sku_norm].get("media_14d", 0.0)
                m30d = isc_data[sku_norm].get("media_30d", 0.0)

        # Projeção cadastrada manualmente para este evento
        proj_cadastro = int(projecoes_por_cadastro.get(cadastro.id, 0)) if cadastro else 0

        total_atletas_orcado += current_sales
        if cadastro:
            total_atletas_confirmados += (
                int(cadastro.atletas_site_pago or 0) +
                int(cadastro.atletas_grupos_pago or 0) +
                int(cadastro.atletas_cortesia or 0)
            )

        # Ocupação = (Inscritos Site reais + Projeção) / Total Geral de Atletas do cadastro
        ocupacao_numerador = current_sales + proj_cadastro
        taxa_ocupacao = round((ocupacao_numerador / cap * 100), 1) if cap > 0 else 0

        # Ocupação da tabela "Inscrições por Evento" = Inscritos Site / Qtd Site (Site Pago do cadastro)
        qtd_site = int(cadastro.atletas_site_pago or 0) if cadastro else 0
        taxa_ocupacao_site = round((current_sales / qtd_site * 100), 1) if qtd_site > 0 else 0

        isc_components = calculate_isc_components(
            current_sales, cap, d_minus_inscricoes,
            media_7d=m7d, media_14d=m14d, media_30d=m30d,
            hist_pattern=None, registration_close_date=None
        )
        isc_val = calculate_isc(isc_components, isc_cfg["ia730Weight"], isc_cfg["curvaDWeight"], isc_cfg["rolling14dWeight"])
        isc_status = get_isc_status(isc_val, isc_cfg["greenThreshold"], isc_cfg["yellowThreshold"])

        if d_minus_inscricoes > 0:
            if isc_status == "accelerating":
                isc_acelerando += 1
            elif isc_status == "stable":
                isc_estavel += 1
            else:
                isc_desacelerando += 1

        nome_evento = (str(cadastro.nome) if cadastro and cadastro.nome else None) or (str(p.evento) if p.evento else f"Evento {p.id}")
        cidade = str(cadastro.localizacao_evento) if cadastro and cadastro.localizacao_evento else (str(p.cidade) if p.cidade else "N/D")

        if p.data_evento and today <= p.data_evento <= window_end:
            upcoming_events.append({
                "evento": nome_evento,
                "data_evento": p.data_evento.isoformat(),
                "cidade": cidade,
                "taxa_ocupacao": taxa_ocupacao,
                "isc": round(isc_val, 3),
                "isc_status": isc_status,
                "atletas_orcado": current_sales,
                "capacidade": cap,
                "dias_para_evento": (p.data_evento - today).days,
            })

        if d_minus_inscricoes > 0:
            if taxa_ocupacao < 50 and cap > 0:
                baixa_ocupacao.append({
                    "evento": nome_evento,
                    "taxa_ocupacao": taxa_ocupacao,
                    "isc_status": isc_status,
                    "cidade": cidade,
                    "atletas_orcado": current_sales,
                    "capacidade": cap,
                })

            if taxa_ocupacao >= 80 and cap > 0:
                sellout_candidates.append({
                    "evento": nome_evento,
                    "taxa_ocupacao": taxa_ocupacao,
                    "isc_status": isc_status,
                    "cidade": cidade,
                    "atletas_orcado": current_sales,
                    "capacidade": cap,
                    "vagas_restantes": cap - current_sales,
                })

            top_por_velocity.append({
                "evento": nome_evento,
                "rolling14d": round(m14d, 1),
                "taxa_ocupacao": taxa_ocupacao,
                "isc_status": isc_status,
                "atletas_orcado": current_sales,
            })

        mod = (str(cadastro.modalidade) if cadastro and cadastro.modalidade else None) or (str(p.modalidade) if p.modalidade else "N/D")
        if mod not in atletas_por_modalidade:
            atletas_por_modalidade[mod] = {"modalidade": mod, "atletas": 0, "eventos": 0}
        atletas_por_modalidade[mod]["atletas"] += current_sales
        atletas_por_modalidade[mod]["eventos"] += 1

        # --- Build the inscrições table row (Dash ISC numbers on the home dashboard) ---
        snap_metrics = snapshot_grupo_map.get(grupo_nome) if grupo_nome else None
        inscritos_total = (snap_metrics or {}).get("total", 0) if snap_metrics else current_sales
        # Garantir consistência: total nunca menor que current_sales calculado acima
        if current_sales and inscritos_total < current_sales:
            inscritos_total = current_sales
        inscritos_hoje = (snap_metrics or {}).get("hoje", 0) if snap_metrics else 0
        inscritos_ontem = (snap_metrics or {}).get("ontem", 0) if snap_metrics else 0

        produto_nome = (str(cadastro.produto) if cadastro and getattr(cadastro, "produto", None) else None) or (str(p.produto) if p.produto else "N/D")

        inscritos_projetados = proj_cadastro
        inscritos_total_int = int(inscritos_total or 0)
        total_geral = inscritos_total_int + inscritos_projetados
        cadastro_id_for_proj = cadastro.id if cadastro else None
        inscritos_projetados_site = int(projecoes_site_por_cadastro.get(cadastro_id_for_proj, 0)) if cadastro_id_for_proj else 0
        projecoes_por_area = projecoes_por_area_detail.get(cadastro_id_for_proj, []) if cadastro_id_for_proj else []

        tabela_eventos.append({
            "id": p.id,
            "evento": nome_evento,
            "cidade": cidade,
            "modalidade": mod,
            "produto": produto_nome,
            "data_evento": p.data_evento.isoformat() if p.data_evento else None,
            "dias_para_evento": (p.data_evento - today).days if p.data_evento else None,
            "inscritos_total": inscritos_total_int,
            "inscritos_projetados": inscritos_projetados,
            "inscritos_projetados_site": inscritos_projetados_site,
            "projecoes_por_area": projecoes_por_area,
            "total_geral": total_geral,
            "inscritos_hoje": int(inscritos_hoje or 0),
            "inscritos_ontem": int(inscritos_ontem or 0),
            "media_7d": round(m7d or 0.0, 1),
            "media_14d": round(m14d or 0.0, 1),
            "isc_status": isc_status,
            "taxa_ocupacao": taxa_ocupacao_site,
            "capacidade": cap,
        })

    upcoming_events.sort(key=lambda x: x["dias_para_evento"])
    baixa_ocupacao.sort(key=lambda x: x["taxa_ocupacao"])
    sellout_candidates.sort(key=lambda x: x["taxa_ocupacao"], reverse=True)
    top_por_velocity.sort(key=lambda x: x["rolling14d"], reverse=True)
    modalidade_list = sorted(atletas_por_modalidade.values(), key=lambda x: x["atletas"], reverse=True)

    taxa_ocupacao_media = round((total_atletas_orcado / total_capacidade * 100), 1) if total_capacidade > 0 else 0

    progresso_atletas = round(total_atletas_confirmados / total_atletas_orcado * 100, 1) if total_atletas_orcado > 0 else 0

    return {
        "kpis": {
            "total_atletas_orcado": total_atletas_orcado,
            "total_atletas_confirmados": total_atletas_confirmados,
            "progresso_atletas_pct": progresso_atletas,
            "total_eventos": total_eventos,
            "isc_acelerando": isc_acelerando,
            "isc_estavel": isc_estavel,
            "isc_desacelerando": isc_desacelerando,
            "taxa_ocupacao_media": taxa_ocupacao_media,
            "total_capacidade": total_capacidade,
            "candidatos_sellout": len(sellout_candidates),
        },
        "proximos_eventos": upcoming_events[:8],
        "alertas_ocupacao": baixa_ocupacao[:5],
        "candidatos_sellout": sellout_candidates[:5],
        "top_por_velocity": top_por_velocity[:8],
        "distribuicao_modalidade": modalidade_list,
        "tabela_eventos": tabela_eventos,
    }


@router.get("/financeiro")
def get_dashboard_financeiro(
    ano: int = _CURRENT_YEAR,
    mes: Optional[int] = Query(None),
    produto: Optional[str] = Query(None),
    modalidade: Optional[str] = Query(None),
    cidade: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("dashboard", "pode_visualizar"))
):
    if not user_can_view_campo(db, current_user, "dashboard", "dados_financeiros"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permissão insuficiente para visualizar dados financeiros do dashboard"
        )

    from .marketing import (
        fetch_isc_pricing_data, _build_sku_to_grupo_map, _get_isc_settings,
        calculate_isc_components, calculate_isc, get_isc_status,
        get_meta_from_cadastro, calculate_d_minus, get_dias_encerramento,
        get_data_regime, normalize_sku, _get_snapshot_metrics_for_grupo
    )

    projetos = build_project_filter(db, ano=ano, mes=mes, produto=produto, modalidade=modalidade, cidade=cidade)
    projeto_ids = [p.id for p in projetos]
    cadastros_map = get_all_cadastros_map(db, projeto_ids)

    cadastro_ids = [c.id for c in cadastros_map.values()]
    kit_costs_map = get_kit_costs_map(db, cadastro_ids)

    isc_cfg = _get_isc_settings(db)
    isc_data = fetch_isc_pricing_data(db=db, force_refresh=False)
    sku_to_grupo = _build_sku_to_grupo_map(db, ano)

    events = compute_event_metrics(projetos, cadastros_map, kit_costs_map)

    isc_status_map: dict = {}
    for p in projetos:
        projeto_codigo = str(p.codigo) if p.codigo else None
        sku_norm = normalize_sku(projeto_codigo) if projeto_codigo else None
        grupo_nome = sku_to_grupo.get(sku_norm) if sku_norm else None
        cadastro = cadastros_map.get(p.id)
        cap = get_meta_from_cadastro(cadastro) if cadastro else 0
        dias_enc = get_dias_encerramento(db, projeto_id=p.id, cadastro=cadastro)
        d_minus_inscricoes = calculate_d_minus(p.data_evento, dias_encerramento=dias_enc) if p.data_evento else 0
        regime = get_data_regime(p.data_evento, dias_enc) if p.data_evento else "live"

        current_sales = 0
        m7d = m14d = m30d = 0.0
        if regime == "consolidated" and grupo_nome:
            snap = _get_snapshot_metrics_for_grupo(db, grupo_nome, ano=ano)
            if snap:
                current_sales = snap.get("qtd_site", 0)
        else:
            if sku_norm and sku_norm in isc_data:
                current_sales = isc_data[sku_norm].get("qtd_site", 0)
                m7d = isc_data[sku_norm].get("media_7d", 0.0)
                m14d = isc_data[sku_norm].get("media_14d", 0.0)
                m30d = isc_data[sku_norm].get("media_30d", 0.0)

        if current_sales == 0 and cadastro:
            current_sales = int(cadastro.atletas_site_pago or 0) + int(cadastro.atletas_grupos_pago or 0) + int(cadastro.atletas_cortesia or 0)

        isc_comps = calculate_isc_components(
            current_sales, cap or 1, d_minus_inscricoes,
            media_7d=m7d, media_14d=m14d, media_30d=m30d,
            hist_pattern=None, registration_close_date=None
        )
        isc_val = calculate_isc(isc_comps, isc_cfg["ia730Weight"], isc_cfg["curvaDWeight"], isc_cfg["rolling14dWeight"])
        isc_status_map[p.id] = get_isc_status(isc_val, isc_cfg["greenThreshold"], isc_cfg["yellowThreshold"])

    for e in events:
        e["isc_status"] = isc_status_map.get(e["id"], "stable")

    total_receita_projetada = sum(e["receita_projetada"] for e in events)

    total_atletas_orcado = sum(e["atletas_orcado"] for e in events)
    total_atletas_confirmados_site = sum(e["atletas_site"] for e in events)
    total_atletas_confirmados = sum(e["atletas_site"] + e["atletas_grupos"] + e["atletas_cortesia"] for e in events)

    total_receita_orcada = sum(
        (e["atletas_orcado"] * decimal_to_float(cadastros_map[e["id"]].atletas_site_tkt_medio)
         if e["id"] in cadastros_map and cadastros_map[e["id"]].atletas_site_tkt_medio else 0)
        for e in events
    )
    total_ticket_realizado = sum(e["ticket_medio"] for e in events if e["ticket_medio"] > 0)
    total_ticket_planejado = sum(
        decimal_to_float(cadastros_map[e["id"]].atletas_site_tkt_medio)
        for e in events
        if e["id"] in cadastros_map and cadastros_map[e["id"]].atletas_site_tkt_medio
    )
    count_com_ticket = sum(1 for e in events if e["ticket_medio"] > 0)
    count_com_tkt_plan = sum(1 for e in events if e["id"] in cadastros_map and cadastros_map[e["id"]].atletas_site_tkt_medio)

    ticket_medio_realizado = round(total_ticket_realizado / count_com_ticket, 2) if count_com_ticket else 0
    ticket_medio_planejado = round(total_ticket_planejado / count_com_tkt_plan, 2) if count_com_tkt_plan else 0

    eventos_com_margem = [e for e in events if e["ticket_medio"] > 0 and e["custo_kit"] > 0]
    margem_media = round(
        sum(e["margem_liquida"] for e in eventos_com_margem) / len(eventos_com_margem), 2
    ) if eventos_com_margem else 0
    percentual_margem_media = round(
        sum(e["percentual_margem"] for e in eventos_com_margem) / len(eventos_com_margem), 1
    ) if eventos_com_margem else 0

    eventos_em_risco = [
        {
            "evento": e["evento"],
            "taxa_ocupacao": e["taxa_ocupacao"],
            "receita_projetada": e["receita_projetada"],
            "isc_status": e["isc_status"],
            "cidade": e["cidade"],
        }
        for e in events
        if e["isc_status"] == "decelerating" and e["receita_projetada"] > 0
    ]
    eventos_em_risco.sort(key=lambda x: x["receita_projetada"], reverse=True)
    receita_em_risco = sum(e["receita_projetada"] for e in eventos_em_risco)

    oportunidades_yield = [
        {
            "evento": e["evento"],
            "taxa_ocupacao": e["taxa_ocupacao"],
            "ticket_medio": e["ticket_medio"],
            "vagas_restantes": e["capacidade"] - e["atletas_orcado"],
            "receita_projetada": e["receita_projetada"],
            "isc_status": e["isc_status"],
        }
        for e in events
        if e["isc_status"] == "accelerating"
        and e["capacidade"] > 0
        and (e["capacidade"] - e["atletas_orcado"]) / e["capacidade"] >= 0.10
        and e["ticket_medio"] > 0
    ]
    oportunidades_yield.sort(key=lambda x: x["taxa_ocupacao"], reverse=True)

    margem_por_modalidade = {}
    for e in events:
        mod = e["modalidade"]
        if mod not in margem_por_modalidade:
            margem_por_modalidade[mod] = {
                "modalidade": mod,
                "receita_projetada": 0,
                "margem_sum": 0,
                "margem_count": 0,
                "eventos": 0,
            }
        margem_por_modalidade[mod]["receita_projetada"] += e["receita_projetada"]
        margem_por_modalidade[mod]["eventos"] += 1
        if e["ticket_medio"] > 0 and e["custo_kit"] > 0:
            margem_por_modalidade[mod]["margem_sum"] += e["margem_liquida"]
            margem_por_modalidade[mod]["margem_count"] += 1

    margem_por_modalidade_list = []
    for v in margem_por_modalidade.values():
        margem_avg = round(v["margem_sum"] / v["margem_count"], 2) if v["margem_count"] > 0 else None
        margem_por_modalidade_list.append({
            "modalidade": v["modalidade"],
            "receita_projetada": round(v["receita_projetada"], 2),
            "margem_media": margem_avg,
            "eventos": v["eventos"],
        })
    margem_por_modalidade_list.sort(key=lambda x: x["receita_projetada"], reverse=True)

    receita_por_produto = {}
    for e in events:
        prod = e["produto"]
        if prod not in receita_por_produto:
            receita_por_produto[prod] = {"produto": prod, "receita_projetada": 0, "atletas": 0, "ticket_medio_sum": 0, "ticket_count": 0}
        receita_por_produto[prod]["receita_projetada"] += e["receita_projetada"]
        receita_por_produto[prod]["atletas"] += e["atletas_orcado"]
        if e["ticket_medio"] > 0:
            receita_por_produto[prod]["ticket_medio_sum"] += e["ticket_medio"]
            receita_por_produto[prod]["ticket_count"] += 1

    receita_por_produto_list = []
    for v in receita_por_produto.values():
        ticket_avg = round(v["ticket_medio_sum"] / v["ticket_count"], 2) if v["ticket_count"] > 0 else 0
        receita_por_produto_list.append({
            "produto": v["produto"],
            "receita_projetada": round(v["receita_projetada"], 2),
            "atletas": v["atletas"],
            "ticket_medio": ticket_avg,
        })
    receita_por_produto_list.sort(key=lambda x: x["receita_projetada"], reverse=True)

    return {
        "kpis": {
            "receita_total_projetada": round(total_receita_projetada, 2),
            "receita_total_orcada": round(total_receita_orcada, 2),
            "variacao_receita": round(total_receita_projetada - total_receita_orcada, 2),
            "ticket_medio_realizado": ticket_medio_realizado,
            "ticket_medio_planejado": ticket_medio_planejado,
            "variacao_ticket": round(ticket_medio_realizado - ticket_medio_planejado, 2),
            "ticket_medio_geral": ticket_medio_realizado,
            "margem_media_liquida": margem_media,
            "percentual_margem_media": percentual_margem_media,
            "receita_em_risco": round(receita_em_risco, 2),
            "total_oportunidades_yield": len(oportunidades_yield),
            "atletas_orcado_total": total_atletas_orcado,
            "atletas_confirmados_total": total_atletas_confirmados,
            "atletas_site_total": total_atletas_confirmados_site,
        },
        "eventos_em_risco": eventos_em_risco[:5],
        "oportunidades_yield": oportunidades_yield[:5],
        "margem_por_modalidade": margem_por_modalidade_list,
        "receita_por_produto": receita_por_produto_list,
    }


NOME_MES_FULL = ["", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
                  "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]


@router.get("/relatorio-financeiro")
def get_relatorio_financeiro(
    ano: int = _CURRENT_YEAR,
    mes: Optional[int] = Query(None),
    produto: Optional[str] = Query(None),
    modalidade: Optional[str] = Query(None),
    cidade: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("dashboard", "pode_visualizar"))
):
    if not user_can_view_campo(db, current_user, "dashboard", "dados_financeiros"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permissão insuficiente para visualizar dados financeiros do dashboard"
        )

    from .marketing import (
        get_marketing_events as _isc_get_marketing_events,
        _build_sku_to_grupo_map as _isc_build_sku_to_grupo_map,
        normalize_sku as _isc_normalize_sku,
    )

    projetos = build_project_filter(db, ano=ano, mes=mes, produto=produto, modalidade=modalidade, cidade=cidade)
    projeto_ids = [p.id for p in projetos]
    projetos_by_id = {p.id: p for p in projetos}
    cadastros_map = get_all_cadastros_map(db, projeto_ids)

    # Busca dados do pipeline ISC para garantir que os números (atletas, receita,
    # margens) batam com os exibidos no Dash ISC. Usa o caminho de cache do
    # próprio endpoint (current_user real => SWR + cache); em caso de "preparing"
    # ou falha, faz fallback para o cálculo orçado a partir do cadastro.
    isc_eventos: list = []
    try:
        isc_response = _isc_get_marketing_events(
            ano=ano, status=None, categoria=None, busca=None,
            force_refresh=False, db=db, current_user=current_user, response=None,
        )
        if isinstance(isc_response, dict):
            isc_eventos = isc_response.get("eventos", []) or []
        else:
            try:
                isc_eventos = [e.model_dump(mode="json") for e in isc_response.eventos]
            except Exception:
                isc_eventos = []
    except Exception:
        isc_eventos = []

    isc_by_projeto_id: dict = {}
    isc_by_grupo_nome: dict = {}
    for ev in isc_eventos:
        ev_id = str(ev.get("id") or "") if isinstance(ev, dict) else ""
        if ev_id.startswith("grp_"):
            isc_by_grupo_nome[ev_id[4:]] = ev
        else:
            try:
                isc_by_projeto_id[int(ev_id)] = ev
            except (TypeError, ValueError):
                pass

    # Pré-carrega margem realizada por evento a partir do EventoDetailSnapshot,
    # usando a MESMA fórmula do Dash ISC (EventDetail): Σ(margemTotal por linha
    # de kit não-CONSOLIDADO em margemPorKit). Isso garante que a coluna
    # "Margem Realizada" da tabela 'Resultado por Mês e Evento' bata exatamente
    # com o card "Margem Realizada" do detalhe de cada evento.
    # Sem essa leitura, o backend cai no caminho margemRealizadaKitsTotal do
    # endpoint da lista, que usa receita do snapshot diário (não a receita por
    # bundle do Magento) e aplica fallback de custo básico para vendas não
    # mapeadas — divergindo dos números do Dash ISC.
    margem_kits_by_eid: dict[str, float] = {}
    try:
        from ...models.evento_detail_snapshot import EventoDetailSnapshot as _EDS_dash
        _eds_rows = (
            db.query(_EDS_dash.evento_id, _EDS_dash.payload)
            .filter(_EDS_dash.ano == ano)
            .all()
        )
        for _eid, _payload in _eds_rows:
            # Isolamos o parsing de cada snapshot para que um payload malformado
            # de um evento não desabilite o override de todos os outros.
            try:
                if not isinstance(_payload, dict):
                    continue
                _evt = _payload.get("evento")
                if not isinstance(_evt, dict):
                    continue
                _mpk = _evt.get("margemPorKit")
                if not isinstance(_mpk, list) or not _mpk:
                    continue
                _rows_real = [
                    r for r in _mpk
                    if isinstance(r, dict) and r.get("tipoKit") != "CONSOLIDADO"
                ]
                if not _rows_real:
                    continue
                # Mesmo gate do EventDetail.tsx (linha ~1057):
                #   _kitRowsRealizado.length > 0 && _kitTotalQtd > 0
                _qtd_total = sum(int(r.get("qtd") or 0) for r in _rows_real)
                if _qtd_total <= 0:
                    continue
                # Soma sem arredondamento intermediário — o frontend formata
                # no momento da renderização (Σ margemTotal por linha não-CONSOLIDADO).
                _margem_sum = sum(float(r.get("margemTotal") or 0) for r in _rows_real)
                margem_kits_by_eid[str(_eid)] = _margem_sum
            except Exception:
                continue
    except Exception:
        # Fallback silencioso para o caminho original em caso de falha global
        # (ex.: tabela ainda não existe em ambientes recém-migrados).
        margem_kits_by_eid = {}

    sku_to_grupo: dict = {}
    try:
        sku_to_grupo = _isc_build_sku_to_grupo_map(db, ano)
    except Exception:
        sku_to_grupo = {}

    grupo_to_projeto_ids: dict[str, list[int]] = {}
    standalone_projeto_ids: list[int] = []
    for p in projetos:
        sku_norm = _isc_normalize_sku(str(p.codigo)) if p.codigo else None
        grupo_nome = sku_to_grupo.get(sku_norm) if sku_norm else None
        if grupo_nome and grupo_nome in isc_by_grupo_nome:
            grupo_to_projeto_ids.setdefault(grupo_nome, []).append(p.id)
        else:
            standalone_projeto_ids.append(p.id)

    cadastro_ids = [c.id for c in cadastros_map.values()]
    kit_costs_map = get_kit_costs_map(db, cadastro_ids) if cadastro_ids else {}

    rows_data: list = []  # (data_evento, evento_row, receita_orcada)

    def _row_from_isc(ev: dict, data_ev, fallback_id: int, fallback_nome: str | None,
                       eds_eid: str | None = None) -> tuple:
        atletas = int(ev.get("currentSales") or 0)
        current_receita = float(ev.get("currentReceita") or 0)
        receita_orcada = float(ev.get("receitaOrcadaTotal") or 0)
        margem_orcada = float(ev.get("margemOrcadaTotal") or 0)
        # Prioridade da margem realizada (mesma fórmula do Dash ISC):
        # 1) Σ(margemTotal por linha de kit não-CONSOLIDADO) lido do
        #    EventoDetailSnapshot — fonte idêntica à do card "Margem Realizada"
        #    no detalhe do evento. Garante paridade visual exata.
        # 2) margemRealizadaKitsTotal do endpoint da lista (cálculo do backend
        #    com receita do snapshot diário e fallback de custo básico).
        # 3) margemRealizadaTotal (custo médio × inscritos), última opção.
        _margem_eds = margem_kits_by_eid.get(eds_eid) if eds_eid else None
        _margem_kits = ev.get("margemRealizadaKitsTotal")
        if _margem_eds is not None:
            margem_realizada = float(_margem_eds)
        elif _margem_kits is not None:
            margem_realizada = float(_margem_kits)
        else:
            margem_realizada = float(ev.get("margemRealizadaTotal") or 0)
        margem_orcada_pct = float(ev.get("margemOrcadaPct") or 0)
        margem_realizada_pct = float(ev.get("margemRealizadaPct") or 0)
        ticket_medio = float(ev.get("averageTicket") or 0)

        nome = ev.get("name") or fallback_nome or f"Evento {fallback_id}"
        evento_row = {
            "id_evento": fallback_id,
            "evento_id": eds_eid,
            "nome_evento": nome,
            "data_evento": data_ev.isoformat(),
            "receita_realizada": round(current_receita, 2),
            "ticket_medio": round(ticket_medio, 2),
            "margem_orcada": round(margem_orcada, 2),
            "margem_orcada_pct": margem_orcada_pct,
            "margem_realizada": round(margem_realizada, 2),
            "margem_realizada_pct": margem_realizada_pct,
            "atletas": atletas,
        }
        return evento_row, round(receita_orcada, 2)

    def _row_from_cadastro(p, cadastro, data_ev) -> tuple:
        # Fallback orçado quando o pipeline ISC não tem dado (ex: preparing).
        atletas_site = int(cadastro.atletas_site_pago or 0) if cadastro else 0
        atletas_grupos = int(cadastro.atletas_grupos_pago or 0) if cadastro else 0
        atletas_cortesia = int(cadastro.atletas_cortesia or 0) if cadastro else 0
        atletas_total = atletas_site + atletas_grupos + atletas_cortesia
        if atletas_total == 0:
            atletas_total = int(p.capacidade_maxima or 0)

        tkt_site = decimal_to_float(cadastro.atletas_site_tkt_medio) if cadastro else 0
        tkt_grupos = decimal_to_float(cadastro.atletas_grupos_tkt_medio) if cadastro else 0
        tkt_medio = 0.0
        if atletas_site > 0 and atletas_grupos > 0:
            tkt_medio = ((tkt_site * atletas_site) + (tkt_grupos * atletas_grupos)) / (atletas_site + atletas_grupos)
        elif atletas_site > 0:
            tkt_medio = tkt_site
        elif atletas_grupos > 0:
            tkt_medio = tkt_grupos

        custo_kit_unit = float(kit_costs_map.get(cadastro.id, 0)) if cadastro else 0.0
        receita_orcada = round(atletas_total * tkt_site, 2) if tkt_site > 0 else 0.0
        custo_kit_total = round(custo_kit_unit * atletas_total, 2) if atletas_total > 0 else 0.0
        margem_orcada = round(receita_orcada - custo_kit_total, 2)
        margem_orcada_pct = round((margem_orcada / receita_orcada * 100), 1) if receita_orcada > 0 else 0.0

        nome = (str(cadastro.nome) if cadastro and cadastro.nome else None) or p.evento or f"Evento {p.id}"
        evento_row = {
            "id_evento": p.id,
            "nome_evento": nome,
            "data_evento": data_ev.isoformat(),
            "receita_realizada": 0.0,
            "ticket_medio": round(tkt_medio, 2),
            "margem_orcada": margem_orcada,
            "margem_orcada_pct": margem_orcada_pct,
            "margem_realizada": 0.0,
            "margem_realizada_pct": 0.0,
            "atletas": 0,
        }
        return evento_row, receita_orcada

    # Linhas de grupos ISC (uma linha por grupo agregando seus projetos filtrados)
    for grupo_nome, pids in grupo_to_projeto_ids.items():
        ev = isc_by_grupo_nome[grupo_nome]
        data_ev = None
        date_str = ev.get("date") if isinstance(ev, dict) else None
        if date_str:
            try:
                data_ev = date.fromisoformat(date_str)
            except Exception:
                data_ev = None
        if data_ev is None:
            for pid in pids:
                pp = projetos_by_id.get(pid)
                if pp and pp.data_evento:
                    data_ev = pp.data_evento
                    break
        if data_ev is None:
            continue

        # Reaplica o filtro de mes ao grupo (caso a data do grupo difira da do projeto)
        if mes is not None and data_ev.month != mes:
            continue

        first_pid = min(pids)
        first_p = projetos_by_id.get(first_pid)
        fallback_nome = (
            str(cadastros_map.get(first_pid).nome)
            if cadastros_map.get(first_pid) and cadastros_map.get(first_pid).nome
            else (first_p.evento if first_p else None)
        )
        row, receita_orcada = _row_from_isc(
            ev, data_ev, first_pid, fallback_nome, eds_eid=f"grp_{grupo_nome}"
        )
        rows_data.append((data_ev, row, receita_orcada))

    # Linhas de projetos standalone (1 projeto = 1 linha)
    for pid in standalone_projeto_ids:
        p = projetos_by_id.get(pid)
        if p is None or p.data_evento is None:
            continue
        data_ev = p.data_evento
        cadastro = cadastros_map.get(pid)
        ev = isc_by_projeto_id.get(pid)
        if ev is not None:
            fallback_nome = (
                str(cadastro.nome) if cadastro and cadastro.nome else p.evento
            )
            row, receita_orcada = _row_from_isc(
                ev, data_ev, pid, fallback_nome, eds_eid=str(pid)
            )
        else:
            # Sem dado ISC: usa fallback orçado (atletas/receita realizada = 0)
            row, receita_orcada = _row_from_cadastro(p, cadastro, data_ev)
        rows_data.append((data_ev, row, receita_orcada))

    meses_dict: dict = {}
    for data_ev, evento_row, receita_orcada in rows_data:
        mes_num = data_ev.month
        ano_num = data_ev.year
        mes_key = f"{ano_num}-{mes_num:02d}"
        mes_label = f"{NOME_MES_FULL[mes_num]} {ano_num}"

        if mes_key not in meses_dict:
            meses_dict[mes_key] = {
                "mes_key": mes_key,
                "mes_num": mes_num,
                "ano_num": ano_num,
                "mes_label": mes_label,
                "eventos": [],
                "receita_orcada_total": 0.0,
                "receita_liquida": 0.0,
                "margem_orcada_total": 0.0,
                "margem_realizada_total": 0.0,
                "n_eventos": 0,
            }

        meses_dict[mes_key]["eventos"].append(evento_row)
        meses_dict[mes_key]["receita_orcada_total"] += receita_orcada
        meses_dict[mes_key]["receita_liquida"] += evento_row["receita_realizada"]
        meses_dict[mes_key]["margem_orcada_total"] += evento_row["margem_orcada"]
        meses_dict[mes_key]["margem_realizada_total"] += evento_row["margem_realizada"]
        meses_dict[mes_key]["n_eventos"] += 1

    meses_list = sorted(meses_dict.values(), key=lambda x: (x["ano_num"], x["mes_num"]))

    for m in meses_list:
        m["receita_orcada_total"] = round(m["receita_orcada_total"], 2)
        m["receita_liquida"] = round(m["receita_liquida"], 2)
        m["margem_orcada_total"] = round(m["margem_orcada_total"], 2)
        m["margem_orcada_pct"] = round(
            (m["margem_orcada_total"] / m["receita_orcada_total"] * 100), 1
        ) if m["receita_orcada_total"] > 0 else 0
        m["margem_realizada_total"] = round(m["margem_realizada_total"], 2)
        m["margem_realizada_pct"] = round(
            (m["margem_realizada_total"] / m["receita_liquida"] * 100), 1
        ) if m["receita_liquida"] > 0 else 0
        m["eventos"].sort(key=lambda x: x["data_evento"])

    return {"meses": meses_list}


@router.get("/consolidado")
def get_dashboard_consolidado(
    ano: int = _CURRENT_YEAR,
    mes: Optional[int] = Query(None),
    produto: Optional[str] = Query(None),
    tipo_evento: Optional[str] = Query(None),
    projeto_id: Optional[int] = Query(None),
    modalidade: Optional[str] = Query(None),
    cidade: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("dashboard", "pode_visualizar"))
):
    projetos = build_project_filter(db, ano, mes, produto, tipo_evento, projeto_id, modalidade, cidade)
    projeto_ids = [p.id for p in projetos]
    cadastros_map = get_all_cadastros_map(db, projeto_ids) if projeto_ids else {}
    events = compute_event_metrics(projetos, cadastros_map)

    total_atletas_orcado = sum(e["atletas_orcado"] for e in events)
    eventos_com_ticket = [e for e in events if e["ticket_medio"] > 0]
    ticket_medio_geral = round(
        sum(e["ticket_medio"] for e in eventos_com_ticket) / len(eventos_com_ticket), 2
    ) if eventos_com_ticket else 0
    total_capacidade = sum(e["capacidade"] for e in events)
    total_eventos = len(events)
    eventos_realizados = sum(1 for e in events if e["status"].lower() in ["concluido", "concluído", "realizado"])
    eventos_planejados = total_eventos - eventos_realizados
    taxa_ocupacao_media = round((total_atletas_orcado / total_capacidade * 100), 1) if total_capacidade > 0 else 0

    eventos_por_modalidade = {}
    eventos_por_cidade = {}
    eventos_por_estado = {}
    eventos_por_mes = {}
    eventos_por_produto = {}

    for e in events:
        mod = e["modalidade"]
        eventos_por_modalidade[mod] = eventos_por_modalidade.get(mod, 0) + 1

        cid = e["cidade"]
        eventos_por_cidade[cid] = eventos_por_cidade.get(cid, 0) + 1

        est = e["estado"]
        eventos_por_estado[est] = eventos_por_estado.get(est, 0) + 1

        d = e["data_evento"]
        if d:
            mes_num = d.month
            mes_label = NOME_MES[mes_num] if 0 < mes_num <= 12 else "N/D"
            if mes_label != "N/D":
                if mes_label not in eventos_por_mes:
                    eventos_por_mes[mes_label] = {"mes": mes_label, "mes_num": mes_num, "orcado": 0, "eventos": 0}
                eventos_por_mes[mes_label]["orcado"] += e["atletas_orcado"]
                eventos_por_mes[mes_label]["eventos"] += 1

        prod = e["produto"]
        if prod not in eventos_por_produto:
            eventos_por_produto[prod] = {"produto": prod, "ticket_medio_sum": 0, "ticket_medio_count": 0, "atletas": 0, "eventos": 0}
        eventos_por_produto[prod]["atletas"] += e["atletas_orcado"]
        eventos_por_produto[prod]["eventos"] += 1
        if e["ticket_medio"] > 0:
            eventos_por_produto[prod]["ticket_medio_sum"] += e["ticket_medio"]
            eventos_por_produto[prod]["ticket_medio_count"] += 1

    tabela_detalhada = [
        {
            "id": e["id"],
            "evento": e["evento"],
            "codigo": e["codigo"],
            "data_evento": e["data_evento"].isoformat() if e["data_evento"] else None,
            "cidade": e["cidade"],
            "estado": e["estado"],
            "modalidade": e["modalidade"],
            "produto": e["produto"],
            "tipo_evento": e["tipo_evento"],
            "status": e["status"],
            "capacidade": e["capacidade"],
            "atletas_orcado": e["atletas_orcado"],
            "atletas_site": e["atletas_site"],
            "atletas_grupos": e["atletas_grupos"],
            "atletas_cortesia": e["atletas_cortesia"],
            "ticket_medio": e["ticket_medio"],
            "taxa_ocupacao": e["taxa_ocupacao"],
        }
        for e in events
    ]

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


@router.get("/inscricoes-diarias")
def get_inscricoes_diarias(
    ano: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("dashboard", "pode_visualizar"))
):
    from ...models.vendas_snapshot import VendasDiariaSnapshot
    from ...models.dimensoes import SkuMapping
    from .marketing import today_brazil
    from sqlalchemy import or_, and_, desc

    today = today_brazil()
    date_start = today - timedelta(days=9)
    prev_end = date_start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=9)

    def ano_filter(date_from, date_to):
        base = [
            VendasDiariaSnapshot.data_venda >= date_from,
            VendasDiariaSnapshot.data_venda <= date_to,
        ]
        if ano:
            base.append(or_(
                VendasDiariaSnapshot.ano == ano,
                VendasDiariaSnapshot.ano.is_(None),
            ))
        return base

    daily_rows = (
        db.query(
            VendasDiariaSnapshot.data_venda,
            sa_func.sum(VendasDiariaSnapshot.quantidade).label("total"),
        )
        .filter(*ano_filter(date_start, today))
        .group_by(VendasDiariaSnapshot.data_venda)
        .order_by(VendasDiariaSnapshot.data_venda)
        .all()
    )

    daily_map = {r.data_venda: int(r.total or 0) for r in daily_rows}
    diario = []
    for i in range(10):
        d = date_start + timedelta(days=i)
        diario.append({
            "data": d.isoformat(),
            "total": daily_map.get(d, 0),
        })

    top_rows = (
        db.query(
            VendasDiariaSnapshot.evento_grupo,
            sa_func.sum(VendasDiariaSnapshot.quantidade).label("total_periodo"),
        )
        .filter(*ano_filter(date_start, today))
        .group_by(VendasDiariaSnapshot.evento_grupo)
        .order_by(desc(sa_func.sum(VendasDiariaSnapshot.quantidade)))
        .limit(10)
        .all()
    )

    grupo_nomes_set = {r.evento_grupo for r in top_rows}

    nome_map: dict = {}
    if grupo_nomes_set:
        mapping_rows = (
            db.query(SkuMapping.evento_grupo, SkuMapping.nome_evento)
            .filter(
                SkuMapping.evento_grupo.in_(grupo_nomes_set),
                SkuMapping.ativo == True,
            )
            .distinct(SkuMapping.evento_grupo)
            .all()
        )
        for m in mapping_rows:
            if m.evento_grupo and m.nome_evento and m.evento_grupo not in nome_map:
                nome_map[m.evento_grupo] = m.nome_evento

    prev_map: dict = {}
    if grupo_nomes_set:
        prev_rows = (
            db.query(
                VendasDiariaSnapshot.evento_grupo,
                sa_func.sum(VendasDiariaSnapshot.quantidade).label("total_prev"),
            )
            .filter(
                *ano_filter(prev_start, prev_end),
                VendasDiariaSnapshot.evento_grupo.in_(grupo_nomes_set),
            )
            .group_by(VendasDiariaSnapshot.evento_grupo)
            .all()
        )
        prev_map = {r.evento_grupo: int(r.total_prev or 0) for r in prev_rows}

    top10 = []
    for r in top_rows:
        total = int(r.total_periodo or 0)
        prev = prev_map.get(r.evento_grupo, 0)
        top10.append({
            "evento_grupo": r.evento_grupo,
            "nome": nome_map.get(r.evento_grupo, r.evento_grupo),
            "total_periodo": total,
            "total_periodo_anterior": prev,
            "variacao": total - prev,
        })

    return {
        "periodo": {
            "inicio": date_start.isoformat(),
            "fim": today.isoformat(),
        },
        "diario": diario,
        "top10": top10,
    }
