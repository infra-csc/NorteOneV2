from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import distinct, extract, func as sa_func
from typing import Optional
from datetime import date, timedelta, datetime as _datetime
_CURRENT_YEAR = _datetime.now().year
from ...core.database import get_db
from ...core.security import get_current_user, is_user_admin
from ...models.dimensoes import DimProjeto
from ...models.cadastro_evento import CadastroEvento, CadastroKitProduto, CadastroKitProdutoItem
from ...models.user import Usuario
from ...models.perfil_acesso import PerfilPermissaoCampo
from decimal import Decimal

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


def decimal_to_float(val):
    if isinstance(val, Decimal):
        return float(val)
    return val or 0


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
    current_user: Usuario = Depends(get_current_user)
):
    from datetime import datetime as _dt
    _cur_year = _dt.now().year
    anos_raw = (
        db.query(distinct(extract('year', DimProjeto.data_evento)))
        .filter(DimProjeto.data_evento != None)
        .order_by(extract('year', DimProjeto.data_evento).desc())
        .all()
    )
    anos = anos_raw or [(_cur_year,)]
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

    produtos = db.query(distinct(DimProjeto.produto)).filter(DimProjeto.produto != None).all()
    tipos_evento = db.query(distinct(DimProjeto.tipo_evento)).filter(DimProjeto.tipo_evento != None).all()
    projetos = db.query(DimProjeto.id, DimProjeto.evento).all()
    modalidades = db.query(distinct(DimProjeto.modalidade)).filter(DimProjeto.modalidade != None).all()
    cidades = db.query(distinct(DimProjeto.cidade)).filter(DimProjeto.cidade != None).all()

    return {
        "anos": [{"value": int(a[0]), "label": str(int(a[0]))} for a in anos],
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


@router.get("/operacional")
def get_dashboard_operacional(
    ano: int = _CURRENT_YEAR,
    mes: Optional[int] = Query(None),
    produto: Optional[str] = Query(None),
    modalidade: Optional[str] = Query(None),
    cidade: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
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

    # --- Sum projected registrations per cadastro_evento.id ---
    projecoes_por_cadastro: dict = {}
    cadastro_ids_for_proj = [c.id for c in cadastros_map.values()]
    if cadastro_ids_for_proj:
        try:
            proj_rows = db.query(
                ProjecaoInscritos.evento_id,
                sa_func.coalesce(sa_func.sum(ProjecaoInscritos.quantidade), 0).label("total"),
            ).filter(
                ProjecaoInscritos.evento_id.in_(cadastro_ids_for_proj),
                ProjecaoInscritos.deleted_at.is_(None),
            ).group_by(ProjecaoInscritos.evento_id).all()
            for r in proj_rows:
                projecoes_por_cadastro[r.evento_id] = int(r.total or 0)
        except Exception:
            projecoes_por_cadastro = {}

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
                or_(
                    VendasDiariaSnapshot.ano == ano,
                    and_(
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
            snap = _get_snapshot_metrics_for_grupo(db, grupo_nome)
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
            "total_geral": total_geral,
            "inscritos_hoje": int(inscritos_hoje or 0),
            "inscritos_ontem": int(inscritos_ontem or 0),
            "media_7d": round(m7d or 0.0, 1),
            "media_14d": round(m14d or 0.0, 1),
            "isc_status": isc_status,
            "taxa_ocupacao": taxa_ocupacao,
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
    current_user: Usuario = Depends(get_current_user)
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
            snap = _get_snapshot_metrics_for_grupo(db, grupo_nome)
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
    current_user: Usuario = Depends(get_current_user)
):
    if not user_can_view_campo(db, current_user, "dashboard", "dados_financeiros"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permissão insuficiente para visualizar dados financeiros do dashboard"
        )

    projetos = build_project_filter(db, ano=ano, mes=mes, produto=produto, modalidade=modalidade, cidade=cidade)
    projeto_ids = [p.id for p in projetos]
    cadastros_map = get_all_cadastros_map(db, projeto_ids)
    cadastro_ids = [c.id for c in cadastros_map.values()]
    kit_costs_map = get_kit_costs_map(db, cadastro_ids)

    events = compute_event_metrics(projetos, cadastros_map, kit_costs_map)

    projetos_by_id = {p.id: p for p in projetos}

    meses_dict: dict = {}

    for e in events:
        projeto = projetos_by_id.get(e["id"])
        data_ev = e.get("data_evento") or (projeto.data_evento if projeto else None)

        if data_ev is None:
            continue

        mes_num = data_ev.month
        ano_num = data_ev.year
        mes_key = f"{ano_num}-{mes_num:02d}"
        mes_label = f"{NOME_MES_FULL[mes_num]} {ano_num}"

        cadastro = cadastros_map.get(e["id"])
        ticket_planejado = decimal_to_float(cadastro.atletas_site_tkt_medio) if cadastro else 0
        atletas_total = e["atletas_orcado"]

        receita_orcada = round(atletas_total * ticket_planejado, 2) if ticket_planejado > 0 else 0
        receita_realizada = e["receita_projetada"]
        custo_kit_unit = e["custo_kit"]
        custo_kit_total = round(custo_kit_unit * atletas_total, 2) if atletas_total > 0 else 0

        margem_orcada = round(receita_orcada - custo_kit_total, 2)
        margem_orcada_pct = round((margem_orcada / receita_orcada * 100), 1) if receita_orcada > 0 else 0

        margem_realizada = round(receita_realizada - custo_kit_total, 2)
        margem_realizada_pct = round((margem_realizada / receita_realizada * 100), 1) if receita_realizada > 0 else 0

        evento_row = {
            "id_evento": e["id"],
            "nome_evento": (str(cadastro.nome) if cadastro and cadastro.nome else None) or e.get("evento") or f"Evento {e['id']}",
            "data_evento": data_ev.isoformat(),
            "receita_realizada": receita_realizada,
            "ticket_medio": e["ticket_medio"],
            "margem_orcada": margem_orcada,
            "margem_orcada_pct": margem_orcada_pct,
            "margem_realizada": margem_realizada,
            "margem_realizada_pct": margem_realizada_pct,
            "atletas": atletas_total,
        }

        if mes_key not in meses_dict:
            meses_dict[mes_key] = {
                "mes_key": mes_key,
                "mes_num": mes_num,
                "ano_num": ano_num,
                "mes_label": mes_label,
                "eventos": [],
                "receita_orcada_total": 0,
                "receita_liquida": 0,
                "margem_orcada_total": 0,
                "margem_realizada_total": 0,
                "n_eventos": 0,
            }

        meses_dict[mes_key]["eventos"].append(evento_row)
        meses_dict[mes_key]["receita_orcada_total"] += receita_orcada
        meses_dict[mes_key]["receita_liquida"] += receita_realizada
        meses_dict[mes_key]["margem_orcada_total"] += margem_orcada
        meses_dict[mes_key]["margem_realizada_total"] += margem_realizada
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
    current_user: Usuario = Depends(get_current_user)
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
