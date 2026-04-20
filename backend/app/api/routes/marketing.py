import os
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session
from sqlalchemy import text, bindparam, func
from typing import Optional, List
from pydantic import BaseModel
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo
from ...core.database import get_db
from ...core import database as db_module
from ...core.security import get_current_user, require_admin
from ...models.dimensoes import DimProjeto, SkuMapping, EventoGrupo as EventoGrupoModel, MarketingSettings
from ...models.user import Usuario
from ...models.cadastro_evento import CadastroEvento, CadastroKitProduto, CadastroKitProdutoItem, CadastroFaixaPrecoSite
from .inscricoes_consolidado import normalize_sku
import logging
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

_TZ_BRAZIL = ZoneInfo("America/Sao_Paulo")

def today_brazil() -> date:
    """Returns the current date in Brazil's timezone (America/Sao_Paulo = UTC-3).
    Using date.today() on a UTC server causes off-by-one errors for D- calculations
    after 21:00 UTC (18:00 BRT), because the server has already ticked to the next day.
    """
    return datetime.now(_TZ_BRAZIL).date()

_rolling_avg_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="mkt_io")

_cadastro_cache: dict = {}

def invalidate_cadastro_caches(projeto_id: int):
    """Limpa caches relacionados a um cadastro de evento específico.
    Deve ser chamado sempre que atletas_site_pago ou outros campos críticos forem atualizados.
    """
    if projeto_id in _cadastro_cache:
        del _cadastro_cache[projeto_id]
    try:
        from ...core.cache import event_detail_cache, eventos_list_cache, curva_cache
        event_detail_cache.invalidate()
        eventos_list_cache.invalidate()
        curva_cache.invalidate()
    except Exception:
        pass

import threading as _threading
_warmup_daily_cache: dict = {}
_warmup_daily_cache_lock = _threading.Lock()
_warmup_thread_ids: set = set()
_warmup_thread_ids_lock = _threading.Lock()

def register_warmup_thread(thread_id: int):
    with _warmup_thread_ids_lock:
        _warmup_thread_ids.add(thread_id)

def unregister_warmup_thread(thread_id: int):
    with _warmup_thread_ids_lock:
        _warmup_thread_ids.discard(thread_id)

def _is_warmup_thread() -> bool:
    with _warmup_thread_ids_lock:
        return _threading.current_thread().ident in _warmup_thread_ids

def set_warmup_daily_cache(ativo_grouped: dict, magento_grouped: dict,
                           cat_ativo_grouped: Optional[dict] = None, cat_magento_grouped: Optional[dict] = None):
    with _warmup_daily_cache_lock:
        _warmup_daily_cache.clear()
        if ativo_grouped:
            _warmup_daily_cache["ativo"] = ativo_grouped
        if magento_grouped:
            _warmup_daily_cache["magento"] = magento_grouped
        if cat_ativo_grouped:
            _warmup_daily_cache["cat_ativo"] = cat_ativo_grouped
        if cat_magento_grouped:
            _warmup_daily_cache["cat_magento"] = cat_magento_grouped

def clear_warmup_daily_cache():
    with _warmup_daily_cache_lock:
        _warmup_daily_cache.clear()
    with _warmup_thread_ids_lock:
        _warmup_thread_ids.clear()


def _wq_sku_mappings_by_grupo(db: Session, grupo_nome: str, anos: list):
    if _is_warmup_thread():
        from app.core.cache import get_warmup_sku_mappings_by_grupo
        cached = get_warmup_sku_mappings_by_grupo(grupo_nome, anos)
        if cached is not None:
            return cached
    return db.query(SkuMapping).filter(
        SkuMapping.evento_grupo == grupo_nome,
        SkuMapping.ano.in_(anos),
        SkuMapping.ativo == True
    ).all()


def _wq_sku_mappings_by_grupo_single_year(db: Session, grupo_nome: str, ano: int):
    if _is_warmup_thread():
        from app.core.cache import get_warmup_sku_mappings_by_grupo
        cached = get_warmup_sku_mappings_by_grupo(grupo_nome, [ano])
        if cached is not None:
            return cached
    return db.query(SkuMapping).filter(
        SkuMapping.evento_grupo == grupo_nome,
        SkuMapping.ano == ano,
        SkuMapping.ativo == True
    ).all()


def _wq_sku_mappings_by_sku(db: Session, sku: str, anos: Optional[list] = None):
    if _is_warmup_thread():
        from app.core.cache import get_warmup_sku_mappings_by_sku
        cached = get_warmup_sku_mappings_by_sku(sku, anos)
        if cached is not None:
            return cached
    q = db.query(SkuMapping).filter(
        SkuMapping.sku == sku.upper().strip(),
        SkuMapping.ativo == True
    )
    if anos:
        q = q.filter(SkuMapping.ano.in_(anos))
    return q.all()


def _wq_sku_mappings_by_skus(db: Session, skus: list, anos: Optional[list] = None):
    if _is_warmup_thread():
        from app.core.cache import get_warmup_sku_mappings_by_sku
        result = []
        for s in skus:
            cached = get_warmup_sku_mappings_by_sku(s, anos)
            if cached is not None:
                result.extend(cached)
            else:
                return None
        return result
    q = db.query(SkuMapping).filter(
        SkuMapping.sku.in_([s.upper().strip() for s in skus]),
        SkuMapping.ativo == True
    )
    if anos:
        q = q.filter(SkuMapping.ano.in_(anos))
    return q.all()


def _wq_dim_projeto_by_id(db: Session, projeto_id: int):
    if _is_warmup_thread():
        from app.core.cache import get_warmup_dim_projeto_by_id
        cached = get_warmup_dim_projeto_by_id(projeto_id)
        if cached is not None:
            return cached
    return db.query(DimProjeto).filter(DimProjeto.id == projeto_id).first()


def _wq_dim_projetos_by_codigos(db: Session, codigos: list):
    if _is_warmup_thread():
        from app.core.cache import get_warmup_dim_projetos_by_codigos
        cached = get_warmup_dim_projetos_by_codigos(codigos)
        if cached is not None:
            return cached
    return db.query(DimProjeto).filter(DimProjeto.codigo.in_(codigos)).all() if codigos else []


def _wq_cadastro_by_projeto_id(db: Session, projeto_id: int):
    if _is_warmup_thread():
        from app.core.cache import get_warmup_cadastro_by_projeto_id
        cached = get_warmup_cadastro_by_projeto_id(projeto_id)
        if cached is not None:
            return cached
    return db.query(CadastroEvento).filter(CadastroEvento.projeto_id == projeto_id).first()


def _wq_all_dim_projetos(db: Session):
    if _is_warmup_thread():
        from app.core.cache import get_warmup_all_dim_projetos
        cached = get_warmup_all_dim_projetos()
        if cached is not None:
            return cached
    return db.query(DimProjeto).all()

def get_meta_orcada(db: Session, projeto_id: int) -> int:
    if projeto_id in _cadastro_cache:
        return _cadastro_cache[projeto_id]
    cadastro = _wq_cadastro_by_projeto_id(db, projeto_id)
    if cadastro and cadastro.atletas_site_pago and cadastro.atletas_site_pago > 0:
        _cadastro_cache[projeto_id] = int(cadastro.atletas_site_pago)
        return int(cadastro.atletas_site_pago)
    _cadastro_cache[projeto_id] = 0
    return 0

def get_meta_from_cadastro(cadastro: CadastroEvento) -> int:
    if cadastro.atletas_site_pago and cadastro.atletas_site_pago > 0:
        return int(cadastro.atletas_site_pago)
    return 0

def get_meta_orcada_projetos(db: Session, projetos: list) -> int:
    total = 0
    for p in projetos:
        total += get_meta_orcada(db, p.id)
    return total


def fetch_daily_sales_ativo(id_evento: str, start_date: date, end_date: date) -> dict:
    """
    Busca vendas diárias do Ativo para um evento específico dentro de um período.
    Retorna um dicionário {data: quantidade_vendida}
    """
    if db_module.engine_ssh is None:
        return {}
    
    try:
        query = text("""
        SELECT 
            DATE(c.dt_pedido) AS data_venda,
            COUNT(a.id_pedido_evento) AS quantidade
        FROM sa_pedido_evento AS a
        INNER JOIN sa_evento AS b ON b.id_evento = a.id_evento
        INNER JOIN sa_pedido AS c ON c.id_pedido = a.id_pedido
        WHERE 
            b.id_evento = :id_evento
            AND c.fl_local_inscricao = '1'
            AND c.id_pedido_status IN (1, 2)
            AND (b.id_campanha_salesforce IS NULL OR b.id_campanha_salesforce NOT LIKE '701d0000000%')
            AND DATE(c.dt_pedido) >= :start_date
            AND DATE(c.dt_pedido) <= :end_date
        GROUP BY DATE(c.dt_pedido)
        ORDER BY data_venda
        """)
        
        with db_module.engine_ssh.connect() as conn:
            result = conn.execute(query, {"id_evento": id_evento, "start_date": start_date.isoformat(), "end_date": end_date.isoformat()})
            rows = result.fetchall()
            
        daily_sales = {}
        for row in rows:
            data_venda = row[0]
            quantidade = row[1]
            if isinstance(data_venda, str):
                data_venda = datetime.strptime(data_venda, '%Y-%m-%d').date()
            daily_sales[data_venda] = quantidade
            
        return daily_sales
    except Exception as e:
        logger.error(f"Erro ao buscar vendas diárias do Ativo: {e}")
        return {}


def get_id_evento_from_projeto(db: Session, projeto_id: int) -> Optional[str]:
    projeto = _wq_dim_projeto_by_id(db, projeto_id)
    if not projeto or not projeto.codigo:
        return None
    
    sku = projeto.codigo.upper().strip()
    
    mappings = _wq_sku_mappings_by_sku(db, sku)
    for m in mappings:
        if m.fonte == 'ATIVO' and m.id_externo:
            return str(m.id_externo)
    return None


def _calculate_action_impact_from_warmup_cache(acao, projeto) -> dict:
    if not acao.data_acao or not projeto or not projeto.codigo:
        return {"vendas_antes": None, "vendas_depois": None, "impacto_percentual": None}

    data_acao = acao.data_acao
    if isinstance(data_acao, datetime):
        data_acao = data_acao.date()

    start_before = data_acao - timedelta(days=7)
    end_before = data_acao - timedelta(days=1)
    start_after = data_acao + timedelta(days=1)
    end_after = data_acao + timedelta(days=7)

    today = today_brazil()
    if end_after > today:
        return {"vendas_antes": None, "vendas_depois": None, "impacto_percentual": None,
                "status": "aguardando_dados"}

    sku = projeto.codigo.upper().strip()
    from app.core.cache import get_warmup_sku_mappings_by_sku
    all_sku_maps = get_warmup_sku_mappings_by_sku(sku)
    if not all_sku_maps:
        return {"vendas_antes": None, "vendas_depois": None, "impacto_percentual": None}

    ano = data_acao.year if isinstance(data_acao, date) else acao.data_acao.year if acao.data_acao else today_brazil().year
    sku_maps = [m for m in all_sku_maps if getattr(m, 'ano', None) == ano and getattr(m, 'ativo', False)]
    if not sku_maps:
        sku_maps = [m for m in all_sku_maps if getattr(m, 'ativo', False)]

    ativo_ids = [str(m.id_externo) for m in sku_maps if getattr(m, 'fonte', '') == 'ATIVO' and m.id_externo]
    magento_ids = [str(m.id_externo) for m in sku_maps if getattr(m, 'fonte', '') == 'MAGENTO' and m.id_externo]

    if not ativo_ids and not magento_ids:
        return {"vendas_antes": None, "vendas_depois": None, "impacto_percentual": None}

    all_daily = []
    if ativo_ids:
        all_daily.extend(_fetch_daily_sales_ativo_by_ids(ativo_ids))
    if magento_ids:
        all_daily.extend(_fetch_daily_sales_magento_by_ids(magento_ids))

    vendas_antes = 0
    vendas_depois = 0
    for row in all_daily:
        try:
            dia = date.fromisoformat(row["dia"]) if isinstance(row["dia"], str) else row["dia"]
        except (ValueError, KeyError):
            continue
        if start_before <= dia <= end_before:
            vendas_antes += row.get("qtd", 0)
        elif start_after <= dia <= end_after:
            vendas_depois += row.get("qtd", 0)

    if vendas_antes > 0:
        impacto_percentual = ((vendas_depois - vendas_antes) / vendas_antes) * 100
    elif vendas_depois > 0:
        impacto_percentual = 100.0
    else:
        impacto_percentual = 0.0

    return {
        "vendas_antes": vendas_antes,
        "vendas_depois": vendas_depois,
        "impacto_percentual": round(impacto_percentual, 1)
    }


def calculate_action_impact(db: Session, acao) -> dict:
    if not acao.data_acao:
        return {"vendas_antes": None, "vendas_depois": None, "impacto_percentual": None}

    projeto = _wq_dim_projeto_by_id(db, acao.projeto_id)
    if not projeto or not projeto.codigo:
        return {"vendas_antes": None, "vendas_depois": None, "impacto_percentual": None}

    if _is_warmup_thread():
        return _calculate_action_impact_from_warmup_cache(acao, projeto)

    sku = projeto.codigo.upper().strip()
    mappings = _wq_sku_mappings_by_sku(db, sku)
    if not mappings:
        return {"vendas_antes": None, "vendas_depois": None, "impacto_percentual": None}

    data_acao = acao.data_acao
    if isinstance(data_acao, datetime):
        data_acao = data_acao.date()

    start_before = data_acao - timedelta(days=7)
    end_before = data_acao - timedelta(days=1)
    start_after = data_acao + timedelta(days=1)
    end_after = data_acao + timedelta(days=7)

    today = today_brazil()
    if end_after > today:
        return {"vendas_antes": None, "vendas_depois": None, "impacto_percentual": None,
                "status": "aguardando_dados"}

    ano = data_acao.year
    sku_maps = [m for m in mappings if getattr(m, 'ano', None) == ano and getattr(m, 'ativo', False)]
    if not sku_maps:
        sku_maps = [m for m in mappings if getattr(m, 'ativo', False)]

    ativo_ids = [str(m.id_externo) for m in sku_maps if getattr(m, 'fonte', '') == 'ATIVO' and m.id_externo]
    magento_ids = [str(m.id_externo) for m in sku_maps if getattr(m, 'fonte', '') == 'MAGENTO' and m.id_externo]

    if not ativo_ids and not magento_ids:
        return {"vendas_antes": None, "vendas_depois": None, "impacto_percentual": None}

    all_daily = []
    if ativo_ids:
        all_daily.extend(_fetch_daily_sales_ativo_by_ids(ativo_ids))
    if magento_ids:
        _cort = _get_cortesia_magento_ids(db)
        _mag_cort = set(magento_ids) & _cort if _cort else None
        all_daily.extend(_fetch_daily_sales_magento_by_ids(magento_ids, cortesia_magento_ids=_mag_cort if _mag_cort else None))

    vendas_antes = 0
    vendas_depois = 0
    for row in all_daily:
        try:
            dia = date.fromisoformat(row["dia"]) if isinstance(row["dia"], str) else row["dia"]
        except (ValueError, KeyError):
            continue
        if start_before <= dia <= end_before:
            vendas_antes += row.get("qtd", 0)
        elif start_after <= dia <= end_after:
            vendas_depois += row.get("qtd", 0)

    if vendas_antes > 0:
        impacto_percentual = ((vendas_depois - vendas_antes) / vendas_antes) * 100
    elif vendas_depois > 0:
        impacto_percentual = 100.0
    else:
        impacto_percentual = 0.0

    return {
        "vendas_antes": vendas_antes,
        "vendas_depois": vendas_depois,
        "impacto_percentual": round(impacto_percentual, 1)
    }

_ticket_atual_cache: dict = {}
_ticket_atual_cache_lock = _threading.Lock()

def clear_ticket_atual_cache():
    with _ticket_atual_cache_lock:
        _ticket_atual_cache.clear()

def _fetch_ticket_atual_map(db: Session) -> dict:
    from ...models.kit_config import KitConfig
    from ...models.cadastro_evento import CadastroEvento
    from ..routes.kit_config import MAGENTO_KITS_QUERY

    all_configs = db.query(KitConfig).filter(KitConfig.id_evento.isnot(None)).all()
    if not all_configs:
        return {}

    if db_module.engine_magento is None:
        return {}

    try:
        with db_module.engine_magento.connect() as conn:
            result = conn.execute(text(MAGENTO_KITS_QUERY))
            rows = result.fetchall()
            columns = list(result.keys())
    except Exception as e:
        logger.error(f"Erro ao buscar ticket_atual do Magento: {e}")
        return {}

    bundle_data: dict = {}
    for row in rows:
        row_dict = dict(zip(columns, row))
        bundle_id = int(row_dict["bundle_entity_id"])
        sp = float(row_dict["special_price"]) if row_dict.get("special_price") is not None else None
        price_val = float(row_dict["price"]) if row_dict.get("price") is not None else None
        sp_base = sp if sp is not None else price_val
        status_kit = row_dict.get("status_kit")
        nome_kit = row_dict.get("nome_kit")
        bundle_data[bundle_id] = {"sp_base": sp_base, "status_kit": status_kit, "nome_kit": nome_kit}

    # Separate basic configs and promo configs per event
    # promo_principal_by_evento: explicit flag takes top priority
    # promo_by_evento: fallback detection via tipo_kit containing "promo"
    basico_by_evento: dict = {}
    promo_principal_by_evento: dict = {}
    promo_by_evento: dict = {}
    for cfg in all_configs:
        evt_key = str(cfg.id_evento)
        if cfg.is_kit_basico:
            basico_by_evento[evt_key] = cfg
        if getattr(cfg, 'is_promo_principal', False):
            promo_principal_by_evento[evt_key] = cfg
        elif cfg.tipo_kit and 'promo' in cfg.tipo_kit.lower():
            promo_by_evento.setdefault(evt_key, []).append(cfg)

    # Compute final ticket per event:
    # 1. Explicit promo principal flag (is_promo_principal) → highest priority
    # 2. Active kit with tipo_kit containing "promo" → second priority
    # 3. Basic kit (is_kit_basico) → fallback
    evento_tickets: dict = {}  # evt_key -> {"value": float, "nome_kit": str}
    all_evt_keys = set(basico_by_evento.keys()) | set(promo_principal_by_evento.keys()) | set(promo_by_evento.keys())
    for evt_key in all_evt_keys:
        ticket_final = None
        nome_kit_final = None

        # 1. Explicit promo principal
        promo_principal_cfg = promo_principal_by_evento.get(evt_key)
        if promo_principal_cfg:
            bd = bundle_data.get(promo_principal_cfg.bundle_entity_id)
            if bd and bd.get("sp_base") is not None:
                ticket_final = round(bd["sp_base"] * promo_principal_cfg.multiplicador, 2)
                nome_kit_final = bd.get("nome_kit")

        # 2. Fallback: active kit whose tipo_kit contains "promo"
        if ticket_final is None:
            promo_configs = promo_by_evento.get(evt_key, [])
            for promo_cfg in promo_configs:
                bd = bundle_data.get(promo_cfg.bundle_entity_id)
                if bd and bd.get("status_kit") == "ativo" and bd.get("sp_base") is not None:
                    ticket_final = round(bd["sp_base"] * promo_cfg.multiplicador, 2)
                    nome_kit_final = bd.get("nome_kit")
                    break

        # 3. Fallback: basic kit
        if ticket_final is None:
            basico_cfg = basico_by_evento.get(evt_key)
            if basico_cfg:
                bd = bundle_data.get(basico_cfg.bundle_entity_id)
                if bd and bd.get("sp_base") is not None:
                    ticket_final = round(bd["sp_base"] * basico_cfg.multiplicador, 2)
                    nome_kit_final = bd.get("nome_kit")

        if ticket_final is not None:
            evento_tickets[evt_key] = {"value": ticket_final, "nome_kit": nome_kit_final}

    if not evento_tickets:
        return {}

    magento_evt_ids = [int(k) for k in evento_tickets.keys() if k.isdigit()]
    magento_sms = db.query(SkuMapping.sku, SkuMapping.id_externo).filter(
        SkuMapping.fonte == 'MAGENTO',
        SkuMapping.ativo == True,
        SkuMapping.id_externo.in_(magento_evt_ids),
    ).all()
    evt_id_to_sku = {str(sm.id_externo): sm.sku for sm in magento_sms}

    matched_skus = list(evt_id_to_sku.values())
    if not matched_skus:
        return {}

    cad_rows = db.query(CadastroEvento.projeto_id, CadastroEvento.sku).filter(
        CadastroEvento.sku.in_(matched_skus),
        CadastroEvento.projeto_id.isnot(None),
    ).all()
    sku_to_projeto = {c.sku: c.projeto_id for c in cad_rows}

    projeto_tickets: dict = {}
    for evt_id, ticket_data in evento_tickets.items():
        sku = evt_id_to_sku.get(evt_id)
        if sku:
            pid = sku_to_projeto.get(sku)
            if pid:
                projeto_tickets[pid] = ticket_data

    return projeto_tickets




def _get_ticket_atual_map(db: Session) -> dict:
    with _ticket_atual_cache_lock:
        if _ticket_atual_cache:
            return dict(_ticket_atual_cache)

    result = _fetch_ticket_atual_map(db)
    with _ticket_atual_cache_lock:
        _ticket_atual_cache.clear()
        _ticket_atual_cache.update(result)
    return result


def _get_ticket_atual_for_event(ticket_map: dict, projeto_ids) -> float:
    if not ticket_map:
        return 0.0

    if not isinstance(projeto_ids, list):
        projeto_ids = [projeto_ids] if projeto_ids is not None else []

    for pid in projeto_ids:
        if pid is not None and pid in ticket_map:
            val = ticket_map[pid]
            if isinstance(val, dict):
                return val.get("value", 0.0) or 0.0
            return float(val) if val is not None else 0.0

    return 0.0


def _get_ticket_atual_kit_nome_for_event(ticket_map: dict, projeto_ids) -> Optional[str]:
    if not ticket_map:
        return None

    if not isinstance(projeto_ids, list):
        projeto_ids = [projeto_ids] if projeto_ids is not None else []

    for pid in projeto_ids:
        if pid is not None and pid in ticket_map:
            val = ticket_map[pid]
            if isinstance(val, dict):
                return val.get("nome_kit")
            return None

    return None


def _get_faixas_preco_site_for_projeto_ids(db: Session, projeto_ids: list) -> dict:
    """Returns faixas_preco_site aggregated across all cadastros for the given project IDs."""
    if not projeto_ids:
        return {"kit_basico": [], "kit_participacao": []}
    cadastros = db.query(CadastroEvento.id).filter(CadastroEvento.projeto_id.in_(projeto_ids)).all()
    cadastro_ids = [c.id for c in cadastros]
    if not cadastro_ids:
        return {"kit_basico": [], "kit_participacao": []}
    faixas = db.query(CadastroFaixaPrecoSite).filter(
        CadastroFaixaPrecoSite.cadastro_id.in_(cadastro_ids)
    ).order_by(CadastroFaixaPrecoSite.faixa).all()
    kit_basico = [
        {"faixa": f.faixa, "qtd": f.qtd or 0, "tkt_medio": float(f.tkt_medio or 0), "total": float(f.total or 0)}
        for f in faixas if f.tipo_kit == "kit_basico" and (f.qtd or 0) > 0
    ]
    kit_participacao = [
        {"faixa": f.faixa, "qtd": f.qtd or 0, "tkt_medio": float(f.tkt_medio or 0), "total": float(f.total or 0)}
        for f in faixas if f.tipo_kit == "kit_participacao" and (f.qtd or 0) > 0
    ]
    return {"kit_basico": kit_basico, "kit_participacao": kit_participacao}


router = APIRouter(prefix="/marketing", tags=["Marketing ISC"])

class ISCComponents(BaseModel):
    ia730: float
    curvaDPercent: float
    rolling14d: float
    tipoCurva: str = "linear"
    fonteCurva: Optional[str] = None
    anoReferencia: Optional[int] = None

class CommercialAction(BaseModel):
    id: str
    date: str
    type: str
    description: str
    impact: Optional[str] = None

class ActiveActionInfo(BaseModel):
    id: int
    tipo: str
    descricao: str
    data_acao: str
    dias_restantes: int

class PlaybookEntry(BaseModel):
    letter: str
    name: str
    stage: str
    stageName: str
    iscLabel: str
    iscState: Optional[str] = None
    objective: str
    narrative: str
    actions: List[str]
    kpis: List[str]
    cutoffs: List[str]

class MarketingEvent(BaseModel):
    id: str
    name: str
    date: str
    location: str
    category: str
    totalCapacity: int
    currentSales: int
    salesGoal: int
    averageTicket: float
    budgetTicket: float = 0.0
    dMinus: int
    dMinusInscricoes: int
    isc: float
    iscComponents: ISCComponents
    iscStatus: str
    suggestedAction: PlaybookEntry
    lastAction: Optional[CommercialAction] = None
    activeAction: Optional[ActiveActionInfo] = None
    isActive: bool
    sku: Optional[str] = None
    kitCostPerUnit: float = 0.0
    receitaOrcadaTotal: float = 0.0
    currentReceita: float = 0.0
    margemOrcadaUnit: float = 0.0
    margemOrcadaTotal: float = 0.0
    margemOrcadaPct: float = 0.0
    margemRealizadaUnit: float = 0.0
    margemRealizadaTotal: float = 0.0
    margemRealizadaPct: float = 0.0
    margemRealizacaoRate: float = 0.0
    ticketAtual: float = 0.0
    ticketKitNome: Optional[str] = None
    margemPorKit: Optional[List[dict]] = None
    margemAvisos: Optional[List[str]] = None
    consistencyWarning: Optional[dict] = None
    detalheVendasPorKit: Optional[List[dict]] = None
    detalheVendasAtivoKit: Optional[List[dict]] = None
    kitQueryFailed: bool = False
    dataRegime: Optional[str] = None
    incluirCortesias: bool = False

class DashboardSummary(BaseModel):
    totalActiveEvents: int
    eventsGreen: int
    eventsYellow: int
    eventsRed: int

class MarketingEventsResponse(BaseModel):
    status: str
    eventos: List[MarketingEvent]
    resumo: DashboardSummary
    categorias: List[str]
    ultima_atualizacao: str
    avisos: List[str] = []

_isc_settings_cache: dict = {"value": None, "ts": 0}
_ISC_SETTINGS_TTL = 60

_DEFAULT_ISC_SETTINGS = {
    "ia730Weight": 20.0,
    "curvaDWeight": 40.0,
    "rolling14dWeight": 40.0,
    "greenThreshold": 1.10,
    "yellowThreshold": 0.90,
    "criticalWindowStart": 45,
    "criticalWindowEnd": 40,
    "promotionDeadline": 40,
}

def _get_isc_settings(db: Session) -> dict:
    import time
    now = time.time()
    if _isc_settings_cache["value"] is not None and (now - _isc_settings_cache["ts"]) < _ISC_SETTINGS_TTL:
        return _isc_settings_cache["value"]
    try:
        setting = db.query(MarketingSettings).filter(MarketingSettings.key == "isc_parameters").first()
        if setting and setting.value:
            merged = {**_DEFAULT_ISC_SETTINGS, **setting.value}
            _isc_settings_cache["value"] = merged
            _isc_settings_cache["ts"] = now
            return merged
    except Exception:
        pass
    _isc_settings_cache["value"] = _DEFAULT_ISC_SETTINGS
    _isc_settings_cache["ts"] = now
    return _DEFAULT_ISC_SETTINGS

def get_isc_status(isc: float, green_threshold: float = 1.10, yellow_threshold: float = 0.90) -> str:
    if isc > green_threshold:
        return "accelerating"
    if isc >= yellow_threshold:
        return "stable"
    return "decelerating"

_PLAYBOOK: dict = {
    # (stage_key, isc_key) -> PlaybookEntry dict
    ("analitico", "forte"): {
        "letter": "A1", "name": "Subida Micro / Âncora de Valor",
        "stage": "analitico", "stageName": "D-90 → D-50 | Analítico",
        "iscLabel": "ISC Forte (>1,12)",
        "objective": "Fixar percepção de valor cedo sem gerar rejeição.",
        "narrative": "\"Quem se antecipa, vive a experiência completa.\"",
        "actions": ["Subir +R$2 a +R$3", "Conteúdo de experiência (vibe, percurso)", "Prova social leve e orgânica", "Zero urgência / zero cupom"],
        "kpis": ["Rolling 14 estável ou crescente"],
        "cutoffs": ["D-65", "D-50"],
    },
    ("analitico", "estavel"): {
        "letter": "A2", "name": "Consolidação de Narrativa",
        "stage": "analitico", "stageName": "D-90 → D-50 | Analítico",
        "iscLabel": "ISC Estável (0,90–1,12)",
        "objective": "Construir desejo antes de mexer em preço.",
        "narrative": "\"Esse é o evento que representa a cidade / comunidade.\"",
        "actions": ["Conteúdo de cultura, percurso e pertencimento", "Ativação com assessorias", "Presença consistente nos canais"],
        "kpis": ["IA 7/30 > 1,00"],
        "cutoffs": ["D-65", "D-50"],
    },
    ("analitico", "fraco"): {
        "letter": "A3", "name": "Socorro Precoce (sem desconto público)",
        "stage": "analitico", "stageName": "D-90 → D-50 | Analítico",
        "iscLabel": "ISC Fraco (<0,90)",
        "objective": "Reativar demanda sem educar o público a esperar desconto.",
        "narrative": "\"Você faz parte desse movimento.\"",
        "actions": ["Ativação com grupos / assessorias locais", "Embaixadores reais", "Incentivo privado (CRM / grupos)"],
        "kpis": ["IA 7/30 reage (>1,00)"],
        "cutoffs": ["D-65", "D-50"],
    },
    ("estrategico", "forte"): {
        "letter": "E1", "name": "Confirmação de Valor / Escala Moderada",
        "stage": "estrategico", "stageName": "D-50 → D-32 | Estratégico",
        "iscLabel": "ISC Forte (>1,12)",
        "objective": "Consolidar evento como premium e preparar rentabilização.",
        "narrative": "\"Esse é o evento referência. Quem corre, corre aqui.\"",
        "actions": ["Subir +R$4 a +R$8", "Prova social forte (vídeo, depoimentos)", "Amplificação com assessorias"],
        "kpis": ["Rolling 14 mantém ou sobe"],
        "cutoffs": ["D-45", "D-35"],
    },
    ("estrategico", "estavel"): {
        "letter": "E2", "name": "Ajuste Fino (sem preço)",
        "stage": "estrategico", "stageName": "D-50 → D-32 | Estratégico",
        "iscLabel": "ISC Estável (0,90–1,12)",
        "objective": "Melhorar conversão antes de mexer no preço.",
        "narrative": "\"Você está no momento certo para decidir.\"",
        "actions": ["Ajuste de mídia (segmentação)", "Otimização de copy e criativos", "Melhorias no site / checkout"],
        "kpis": ["IA 7/30 > 1,05"],
        "cutoffs": ["D-45", "D-35"],
    },
    ("estrategico", "fraco"): {
        "letter": "E3", "name": "Promoção Privada Controlada (última janela)",
        "stage": "estrategico", "stageName": "D-50 → D-32 | Estratégico",
        "iscLabel": "ISC Fraco (<0,90)",
        "objective": "Destravar vendas rápido sem quebrar percepção de valor.",
        "narrative": "\"Condição especial para quem está próximo do movimento.\"",
        "actions": ["Cupom privado (CRM / grupos / assessorias)", "Janela curta (24–72h)", "Nunca público", "Execução preferencial entre D-45 e D-40"],
        "kpis": ["IA 7/30 sobe forte em 48h"],
        "cutoffs": ["D-45", "D-35"],
    },
    ("operacional", "forte"): {
        "letter": "O1", "name": "Rentabilização Máxima",
        "stage": "operacional", "stageName": "D-32 → D-0 | Operacional",
        "iscLabel": "ISC Forte (>1,12)",
        "objective": "Maximizar margem (inclusive acima da meta).",
        "narrative": "\"Últimas vagas. Quem decidiu, já garantiu.\"",
        "actions": ["Subir +R$8 até +R$20", "Comunicação de escassez real", "Urgência legítima"],
        "kpis": ["Ticket Atual sobe sem queda relevante de volume"],
        "cutoffs": ["D-30", "D-15"],
    },
    ("operacional", "estavel"): {
        "letter": "O2", "name": "Conversão Final",
        "stage": "operacional", "stageName": "D-32 → D-0 | Operacional",
        "iscLabel": "ISC Estável (0,90–1,12)",
        "objective": "Converter indecisos sem distorcer preço.",
        "narrative": "\"Ainda dá tempo. Esse é o momento.\"",
        "actions": ["Remarketing forte", "Melhorias de conversão (checkout)", "Bundles (kit premium, experiência)"],
        "kpis": ["Taxa de conversão sobe"],
        "cutoffs": ["D-30", "D-15"],
    },
    ("operacional", "fraco"): {
        "letter": "O3", "name": "Giro Final Controlado (sem desconto aberto)",
        "stage": "operacional", "stageName": "D-32 → D-0 | Operacional",
        "iscLabel": "ISC Fraco (<0,90)",
        "objective": "Fechar volume sem destruir posicionamento.",
        "narrative": "\"Seu grupo estará lá. Não fique de fora.\"",
        "actions": ["Ação com grupos / empresas / assessorias", "Incentivos direcionados (não públicos)", "Foco em pertencimento"],
        "kpis": ["Volume sobe sem colapsar Ticket Atual"],
        "cutoffs": ["D-30", "D-15"],
    },
}

def get_suggested_action(isc: float, d_minus: int, green_threshold: float = 1.10, yellow_threshold: float = 0.90, promotion_deadline: int = 40) -> dict:
    status = get_isc_status(isc, green_threshold, yellow_threshold)
    
    if d_minus >= 50:
        stage_key = "analitico"
    elif d_minus >= 32:
        stage_key = "estrategico"
    else:
        stage_key = "operacional"

    if status == "accelerating":
        isc_key = "forte"
    elif status == "stable":
        isc_key = "estavel"
    else:
        isc_key = "fraco"

    entry = dict(_PLAYBOOK[(stage_key, isc_key)])
    # iscState is used by the frontend for color-coding; "estável" uses accent to match TS type
    entry["iscState"] = "forte" if isc_key == "forte" else ("estável" if isc_key == "estavel" else "fraco")
    return entry

def get_active_actions_for_projects(db: Session, projeto_ids: list) -> dict:
    """
    Retorna ações comerciais ativas (criadas nos últimos 7 dias) para uma lista de projeto_ids.
    Retorna um dict {projeto_id: ActiveActionInfo}
    """
    from ...models.dimensoes import AcaoComercial
    if not projeto_ids:
        return {}
    
    today = today_brazil()
    cutoff = today - timedelta(days=7)
    
    acoes = db.query(AcaoComercial).filter(
        AcaoComercial.projeto_id.in_(projeto_ids),
        AcaoComercial.data_acao >= cutoff
    ).order_by(AcaoComercial.data_acao.desc()).all()
    
    result = {}
    for a in acoes:
        if a.projeto_id not in result:
            data_acao = a.data_acao
            if isinstance(data_acao, datetime):
                data_acao = data_acao.date()
            dias_restantes = max(0, 7 - (today - data_acao).days)
            result[a.projeto_id] = ActiveActionInfo(
                id=a.id,
                tipo=a.tipo,
                descricao=a.descricao,
                data_acao=data_acao.isoformat(),
                dias_restantes=dias_restantes
            )
    return result


def check_duplicate_action(db: Session, projeto_id: int, tipo: str) -> dict:
    """
    Verifica se já existe uma ação do mesmo tipo para o projeto nos últimos 7 dias.
    Retorna None se não há duplicata, ou um dict com info da ação existente.
    """
    from ...models.dimensoes import AcaoComercial
    
    today = today_brazil()
    cutoff = today - timedelta(days=7)
    
    existing = db.query(AcaoComercial).filter(
        AcaoComercial.projeto_id == projeto_id,
        AcaoComercial.tipo == tipo,
        AcaoComercial.data_acao >= cutoff
    ).order_by(AcaoComercial.data_acao.desc()).first()
    
    if existing:
        data_acao = existing.data_acao
        if isinstance(data_acao, datetime):
            data_acao = data_acao.date()
        dias_restantes = max(0, 7 - (today - data_acao).days)
        return {
            "id": existing.id,
            "tipo": existing.tipo,
            "descricao": existing.descricao,
            "data_acao": data_acao.isoformat(),
            "dias_restantes": dias_restantes
        }
    return None


def get_dias_encerramento(db: Session, projeto_id: Optional[int] = None, cadastro: Optional[object] = None) -> int:
    if cadastro is not None:
        val = getattr(cadastro, 'dias_encerramento_inscricao', None)
        if val is not None:
            return val
        return 2
    if projeto_id is not None:
        try:
            cad = db.query(CadastroEvento).filter(CadastroEvento.projeto_id == projeto_id).first()
            if cad and cad.dias_encerramento_inscricao is not None:
                return cad.dias_encerramento_inscricao
        except Exception:
            pass
    return 2

def calculate_d_minus(event_date: date, reference_year: Optional[int] = None, dias_encerramento: int = 2) -> int:
    if not event_date:
        return 0
    registration_close = event_date - timedelta(days=dias_encerramento)
    today = today_brazil()
    if reference_year is not None and reference_year != today.year:
        try:
            today = today.replace(year=reference_year)
        except ValueError:
            today = today.replace(year=reference_year, day=28)
    delta = (registration_close - today).days
    return max(0, delta)


def get_event_regime(d_minus_raw: int) -> str:
    """
    Centralized function to determine data regime from raw (unclamped) D-.
    d_minus_raw = (registration_close - today).days, can be negative for past events.
    - 'consolidated' (D- < -1): event ended, use snapshot data only, no live queries
    - 'hybrid' (-1 ≤ D- ≤ 3): event is happening now or just ended, snapshot + live today
    - 'live' (D- > 3): upcoming event, full live queries as normal
    """
    if d_minus_raw < -1:
        return "consolidated"
    if d_minus_raw <= 3:
        return "hybrid"
    return "live"


def get_data_regime(event_date, dias_encerramento: int = 2) -> str:
    """Convenience wrapper: computes raw D- from event_date and delegates to get_event_regime."""
    if not event_date:
        return "live"
    registration_close = event_date - timedelta(days=dias_encerramento)
    real_d_minus = (registration_close - today_brazil()).days
    return get_event_regime(real_d_minus)


def _get_snapshot_metrics_for_grupo(db: Session, grupo_nome: str) -> Optional[dict]:
    """
    Returns ISC-like metrics from snapshot data for a consolidated event group.
    Returns None if no snapshot data exists (caller should fall back to live data).
    """
    try:
        from ...services.snapshot_service import get_snapshot_vendas_com_receita
        rows = get_snapshot_vendas_com_receita(db, grupo_nome)
        if not rows:
            return None
        total_qtd = sum(r['qtd'] for r in rows)
        total_receita = sum(r['receita'] for r in rows)
        return {
            'qtd_site': total_qtd,
            'inscricao_liquida': total_receita,
            'receita_liquida_site': total_receita,
            'ticket_medio': round(total_receita / total_qtd, 2) if total_qtd > 0 else 0.0,
            'media_7d': 0.0,
            'media_14d': 0.0,
            'media_30d': 0.0,
        }
    except Exception as e:
        logger.warning(f"[Hybrid] Failed to get snapshot metrics for '{grupo_nome}': {e}")
        return None

def _interpolate_hist_pattern(hist_pattern: dict, d_minus: int) -> float:
    sorted_dms = sorted(hist_pattern.keys(), reverse=True)
    if d_minus in hist_pattern:
        return hist_pattern[d_minus]
    if d_minus >= sorted_dms[0]:
        return hist_pattern[sorted_dms[0]]
    if d_minus <= sorted_dms[-1]:
        return hist_pattern[sorted_dms[-1]]
    for i in range(len(sorted_dms) - 1):
        if sorted_dms[i] > d_minus > sorted_dms[i + 1]:
            upper_dm = sorted_dms[i]
            lower_dm = sorted_dms[i + 1]
            ratio = (upper_dm - d_minus) / (upper_dm - lower_dm) if upper_dm != lower_dm else 0
            return hist_pattern[upper_dm] + ratio * (hist_pattern[lower_dm] - hist_pattern[upper_dm])
    return hist_pattern.get(0, 1.0)


def calculate_isc_components(current_sales: int, sales_goal: int, d_minus: int, 
                              media_14d: Optional[float] = None, daily_sales_dict: Optional[dict] = None,
                              media_7d: Optional[float] = None, media_30d: Optional[float] = None,
                              hist_pattern: Optional[dict] = None,
                              registration_close_date=None,
                              curva_info: Optional[dict] = None) -> ISCComponents:
    """
    registration_close_date: date of last day registrations were open (event_date - dias_enc).
    When provided and d_minus < 0 (past event), all rolling windows are anchored to this date
    so components are frozen at their final state rather than collapsing to zero.
    """
    _ci = curva_info or {}
    if sales_goal == 0:
        return ISCComponents(ia730=1.0, curvaDPercent=1.0, rolling14d=1.0,
                             tipoCurva=_ci.get("tipo_curva", "linear"),
                             fonteCurva=_ci.get("fonte_curva"),
                             anoReferencia=_ci.get("ano_referencia"))
    
    if daily_sales_dict:
        daily_sales_dict = {(date.fromisoformat(k) if isinstance(k, str) else k): v for k, v in daily_sales_dict.items()}
    
    from datetime import timedelta

    # For past events, anchor calculations to the registration close date.
    # This freezes components at the state they were when the event ended.
    # NOTE: d_minus may arrive clamped to 0 for consolidated events (dMinusInscricoes=0),
    # so we also check registration_close_date to correctly identify past events.
    is_past_event = d_minus < 0 or (
        registration_close_date is not None and registration_close_date < today_brazil()
    )
    if is_past_event and registration_close_date is not None:
        anchor_date = registration_close_date - timedelta(days=1)
        d_minus_effective = 0  # treat as D-0 for curvaDPercent and rolling window
    else:
        anchor_date = today_brazil() - timedelta(days=1)
        d_minus_effective = d_minus

    if daily_sales_dict and len(daily_sales_dict) > 0:
        # For past events anchor to close date; for live events anchor to yesterday
        cutoff = anchor_date if is_past_event and registration_close_date else today_brazil()
        current_sales = sum(v for k, v in daily_sales_dict.items() if k <= cutoff)
    
    progress_percent = current_sales / sales_goal

    tipo_curva = "linear"
    if hist_pattern and len(hist_pattern) > 0:
        hist_max_dm = max(hist_pattern.keys())
        if d_minus_effective > hist_max_dm:
            # Current D-minus is beyond the historical data range (campaign hadn't started
            # that early in the reference year). Fall back to linear 90-day ramp so we
            # don't divide by a near-zero historical percentage and inflate the component.
            total_days = 90
            elapsed_days = max(1, total_days - d_minus_effective)
            expected_progress = max(elapsed_days / total_days, 0.01)
            curva_d_percent = progress_percent / expected_progress
        else:
            tipo_curva = "historico"
            expected_progress = _interpolate_hist_pattern(hist_pattern, d_minus_effective)
            if expected_progress <= 0:
                expected_progress = 0.01
            curva_d_percent = progress_percent / expected_progress
    else:
        total_days = 90
        elapsed_days = max(1, total_days - d_minus_effective)
        expected_progress = elapsed_days / total_days
        if expected_progress == 0:
            expected_progress = 0.01
        curva_d_percent = progress_percent / expected_progress

    real_7d = None
    real_14d = None
    real_30d = None
    sum_14d_raw = None
    if daily_sales_dict and len(daily_sales_dict) > 0:
        s7 = sum(daily_sales_dict.get(anchor_date - timedelta(days=i), 0) for i in range(7))
        s14 = sum(daily_sales_dict.get(anchor_date - timedelta(days=i), 0) for i in range(14))
        s30 = sum(daily_sales_dict.get(anchor_date - timedelta(days=i), 0) for i in range(30))
        sum_14d_raw = s14
        real_7d = s7 / 7.0
        real_14d = s14 / 14.0
        real_30d = s30 / 30.0

    effective_7d = real_7d if real_7d is not None else media_7d
    effective_14d = real_14d if real_14d is not None else media_14d
    effective_30d = real_30d if real_30d is not None else media_30d

    ia730_calculated = False
    if effective_7d is not None and effective_30d is not None:
        if effective_30d > 0:
            raw_ia730 = effective_7d / effective_30d
            # For past events, ia730=0 means zero sales in the 7-day window before
            # registration close — use curva_d_percent fallback so the indicator
            # never shows a misleading 0 when there IS historical sales activity.
            if raw_ia730 == 0 and is_past_event:
                ia730_calculated = False  # fall through to curva_d_percent
            else:
                ia730 = raw_ia730
                ia730_calculated = True
        elif effective_7d > 0:
            ia730 = 1.2
            ia730_calculated = True
    
    if not ia730_calculated:
        ia730 = curva_d_percent

    # Use d_minus_effective (clamped to 0 for past events) so expected window is meaningful
    d_minus_anchor = d_minus_effective + 1

    expected_14d_sales = None
    if hist_pattern and len(hist_pattern) > 0 and sales_goal > 0:
        expected_at_anchor = _interpolate_hist_pattern(hist_pattern, d_minus_anchor)
        expected_14d_ago = _interpolate_hist_pattern(hist_pattern, d_minus_anchor + 14)
        expected_14d_sales = (expected_at_anchor - expected_14d_ago) * sales_goal
    elif sales_goal > 0:
        total_days = 90
        expected_14d_sales = (14 / total_days) * sales_goal

    if expected_14d_sales is not None and expected_14d_sales > 0 and sum_14d_raw is not None:
        rolling14d = sum_14d_raw / expected_14d_sales
    elif effective_14d is not None and effective_14d > 0 and expected_14d_sales is not None and expected_14d_sales > 0:
        rolling14d = (effective_14d * 14) / expected_14d_sales
    else:
        rolling14d = (curva_d_percent + ia730) / 2
    
    if _ci.get("tipo_curva"):
        tipo_curva = _ci["tipo_curva"]

    return ISCComponents(
        ia730=round(ia730, 4),
        curvaDPercent=round(curva_d_percent, 4),
        rolling14d=round(rolling14d, 4),
        tipoCurva=tipo_curva,
        fonteCurva=_ci.get("fonte_curva"),
        anoReferencia=_ci.get("ano_referencia")
    )

_ISC_DESVIO_CAP = 0.30

def calculate_isc(components: ISCComponents, ia_weight: float = 20.0, curva_weight: float = 40.0, rolling_weight: float = 40.0) -> float:
    cap = _ISC_DESVIO_CAP
    d_ia = max(-cap, min(cap, components.ia730 - 1))
    d_curva = max(-cap, min(cap, components.curvaDPercent - 1))
    d_rolling = max(-cap, min(cap, components.rolling14d - 1))

    weighted = (curva_weight / 100) * d_curva + (rolling_weight / 100) * d_rolling + (ia_weight / 100) * d_ia
    isc = 1.0 + weighted
    return round(isc, 2)


def _fetch_previous_year_cumulative_pattern(db: Session, evento_grupo: str, ano: int) -> Optional[dict]:
    from ...services.snapshot_service import get_curva_historica_snapshot, save_curva_historica_snapshot
    prev_ano = ano - 1

    snapshot_pattern = get_curva_historica_snapshot(db, evento_grupo, prev_ano)
    if snapshot_pattern:
        logger.info(f"Using curva histórica snapshot for '{evento_grupo}' ano_ref={prev_ano}: {len(snapshot_pattern)} pontos D-minus")
        return snapshot_pattern

    prev_data_evento = _find_data_evento(db, evento_grupo, prev_ano)
    if not prev_data_evento:
        logger.info(f"No previous year event date found for '{evento_grupo}' ano={prev_ano}")
        return None

    prev_dias_enc = 2
    try:
        prev_proj = db.query(DimProjeto).filter(
            DimProjeto.data_evento == prev_data_evento
        ).first()
        if prev_proj:
            prev_dias_enc = get_dias_encerramento(db, projeto_id=prev_proj.id)
    except Exception:
        pass
    prev_data_inscricao = prev_data_evento - timedelta(days=prev_dias_enc)

    prev_mappings = _wq_sku_mappings_by_grupo_single_year(db, evento_grupo, prev_ano)

    if not prev_mappings:
        current_mappings = _wq_sku_mappings_by_grupo_single_year(db, evento_grupo, ano)
        prev_skus = list(set(m.sku for m in current_mappings if m.sku))
        if prev_skus:
            prev_mappings = _wq_sku_mappings_by_skus(db, prev_skus, [prev_ano])
            if prev_mappings is None:
                prev_mappings = []

    if not prev_mappings:
        logger.info(f"No SKU mappings found for '{evento_grupo}' ano={prev_ano}")
        return None

    prev_ativo_ids = []
    prev_magento_ids = []
    for m in prev_mappings:
        if m.id_externo:
            if m.fonte == 'ATIVO':
                prev_ativo_ids.append(str(m.id_externo))
            elif m.fonte == 'MAGENTO':
                prev_magento_ids.append(str(m.id_externo))

    prev_daily = {}
    if prev_ativo_ids:
        rows = _fetch_daily_sales_ativo_by_ids(list(set(prev_ativo_ids)))
        for row in rows:
            d = date.fromisoformat(row['dia']) if isinstance(row['dia'], str) else row['dia']
            prev_daily[d] = prev_daily.get(d, 0) + row['qtd']
    if prev_magento_ids:
        _cort = _get_cortesia_magento_ids(db)
        _mag_cort = set(prev_magento_ids) & _cort if _cort else None
        rows = _fetch_daily_sales_magento_by_ids(list(set(prev_magento_ids)), cortesia_magento_ids=_mag_cort if _mag_cort else None)
        for row in rows:
            d = date.fromisoformat(row['dia']) if isinstance(row['dia'], str) else row['dia']
            prev_daily[d] = prev_daily.get(d, 0) + row['qtd']

    if not prev_daily:
        logger.info(f"No sales data found for '{evento_grupo}' ano={prev_ano}")
        return None

    total_prev_sales = sum(prev_daily.values())
    if total_prev_sales == 0:
        return None

    d_minus_sales = {}
    for sale_date, qty in prev_daily.items():
        dm = (prev_data_inscricao - sale_date).days
        d_minus_sales[dm] = d_minus_sales.get(dm, 0) + qty

    d_minus_sales = {dm: qty for dm, qty in d_minus_sales.items() if dm >= 0}
    if not d_minus_sales:
        logger.info(f"No sales data with positive D- for '{evento_grupo}' ano={prev_ano}")
        return None

    max_dm = max(d_minus_sales.keys())
    min_dm = min(d_minus_sales.keys())

    cumulative = 0
    pattern = {}
    for dm in range(max_dm, min_dm - 1, -1):
        cumulative += d_minus_sales.get(dm, 0)
        pattern[dm] = cumulative / total_prev_sales

    if 0 not in pattern:
        pattern[0] = 1.0
    if min_dm > 0:
        for dm in range(min_dm - 1, -1, -1):
            pattern[dm] = 1.0

    logger.info(f"Built historical pattern for '{evento_grupo}' from ano={prev_ano} (inscricao D-): {len(prev_daily)} sale days, total={total_prev_sales}, D- range [{min_dm}, {max_dm}]")

    try:
        save_curva_historica_snapshot(db, evento_grupo, prev_ano, pattern, total_prev_sales)
    except Exception as e:
        logger.warning(f"Failed to save curva histórica snapshot for '{evento_grupo}': {e}")

    return pattern


def _resolve_hist_pattern(db: Session, evento_grupo: str, ano: int, estado: Optional[str] = None) -> tuple:
    """Resolve the best available historical curve for an event group using a fallback chain.
    
    Returns (pattern, curva_info) where curva_info is a dict with:
      - tipo_curva: 'historico' | 'circuito' | 'circuito_similar' | 'regional' | 'manual' | 'linear'
      - fonte_curva: name of the source grupo or region
      - ano_referencia: year the pattern data is from
    """
    from ...services.snapshot_service import get_curva_historica_snapshot
    from ...models.vendas_snapshot import CurvaHistoricaSnapshot
    prev_ano = ano - 1

    grupo_obj = db.query(EventoGrupoModel).filter(EventoGrupoModel.nome == evento_grupo).first()

    if grupo_obj and grupo_obj.curva_override:
        override_pattern = get_curva_historica_snapshot(db, grupo_obj.curva_override, prev_ano)
        if not override_pattern:
            override_pattern = _fetch_previous_year_cumulative_pattern(db, grupo_obj.curva_override, ano)
        if override_pattern:
            logger.info(f"[CurvaResolve] '{evento_grupo}' using manual override: '{grupo_obj.curva_override}'")
            return override_pattern, {
                "tipo_curva": "manual",
                "fonte_curva": grupo_obj.curva_override,
                "ano_referencia": prev_ano
            }

    own_pattern = _fetch_previous_year_cumulative_pattern(db, evento_grupo, ano)
    if own_pattern:
        return own_pattern, {
            "tipo_curva": "historico",
            "fonte_curva": evento_grupo,
            "ano_referencia": prev_ano
        }

    circuito = grupo_obj.circuito if grupo_obj else None
    cidade = grupo_obj.cidade_normalizada if grupo_obj else None

    if circuito and cidade:
        same_circuit_city = db.query(EventoGrupoModel).filter(
            EventoGrupoModel.circuito == circuito,
            EventoGrupoModel.cidade_normalizada == cidade,
            EventoGrupoModel.nome != evento_grupo,
            EventoGrupoModel.ativo == True
        ).all()
        for sibling in same_circuit_city:
            sib_pattern = get_curva_historica_snapshot(db, sibling.nome, prev_ano)
            if not sib_pattern:
                sib_pattern = _fetch_previous_year_cumulative_pattern(db, sibling.nome, ano)
            if sib_pattern:
                logger.info(f"[CurvaResolve] '{evento_grupo}' using circuit+city sibling: '{sibling.nome}'")
                return sib_pattern, {
                    "tipo_curva": "circuito",
                    "fonte_curva": sibling.nome,
                    "ano_referencia": prev_ano
                }

    if circuito:
        same_circuit = db.query(EventoGrupoModel).filter(
            EventoGrupoModel.circuito == circuito,
            EventoGrupoModel.nome != evento_grupo,
            EventoGrupoModel.ativo == True
        ).all()
        patterns_found = []
        source_names = []
        pattern_weights = []
        for sibling in same_circuit:
            sib_pattern = get_curva_historica_snapshot(db, sibling.nome, prev_ano)
            sib_weight = 0
            if sib_pattern:
                weight_row = db.query(CurvaHistoricaSnapshot.total_vendas_referencia).filter(
                    CurvaHistoricaSnapshot.evento_grupo == sibling.nome,
                    CurvaHistoricaSnapshot.ano_referencia == prev_ano
                ).first()
                sib_weight = weight_row[0] if weight_row and weight_row[0] else 0
            if not sib_pattern:
                sib_pattern = _fetch_previous_year_cumulative_pattern(db, sibling.nome, ano)
            if sib_pattern:
                patterns_found.append(sib_pattern)
                source_names.append(sibling.nome)
                pattern_weights.append(sib_weight if sib_weight > 0 else 1)

        if patterns_found:
            avg_pattern = _average_patterns(patterns_found, weights=pattern_weights)
            fonte_label = f"Média {circuito}" if len(patterns_found) > 1 else source_names[0]
            logger.info(f"[CurvaResolve] '{evento_grupo}' using circuit average from {len(patterns_found)} sibling(s): {source_names} (weights={pattern_weights})")
            return avg_pattern, {
                "tipo_curva": "circuito_similar",
                "fonte_curva": fonte_label,
                "ano_referencia": prev_ano
            }

    if estado:
        regional_grupos = db.query(EventoGrupoModel).join(
            SkuMapping, SkuMapping.evento_grupo == EventoGrupoModel.nome
        ).join(
            DimProjeto, DimProjeto.codigo == SkuMapping.sku
        ).filter(
            DimProjeto.estado == estado,
            EventoGrupoModel.nome != evento_grupo,
            EventoGrupoModel.ativo == True
        ).distinct().all()

        patterns_found = []
        pattern_weights = []
        for rg in regional_grupos:
            rg_pattern = get_curva_historica_snapshot(db, rg.nome, prev_ano)
            if rg_pattern:
                patterns_found.append(rg_pattern)
                weight_row = db.query(CurvaHistoricaSnapshot.total_vendas_referencia).filter(
                    CurvaHistoricaSnapshot.evento_grupo == rg.nome,
                    CurvaHistoricaSnapshot.ano_referencia == prev_ano
                ).first()
                pattern_weights.append(weight_row[0] if weight_row and weight_row[0] else 1)

        if len(patterns_found) >= 2:
            avg_pattern = _average_patterns(patterns_found, weights=pattern_weights)
            logger.info(f"[CurvaResolve] '{evento_grupo}' using regional average ({estado}): {len(patterns_found)} patterns")
            return avg_pattern, {
                "tipo_curva": "regional",
                "fonte_curva": estado,
                "ano_referencia": prev_ano
            }

    logger.info(f"[CurvaResolve] '{evento_grupo}' no fallback found, using linear")
    return None, {
        "tipo_curva": "linear",
        "fonte_curva": None,
        "ano_referencia": None
    }


def _average_patterns(patterns: list, weights: Optional[list] = None) -> dict:
    """Average multiple hist_pattern dicts into one, optionally weighted."""
    all_dms = set()
    for p in patterns:
        all_dms.update(p.keys())

    if weights and len(weights) == len(patterns) and sum(weights) > 0:
        total_weight = sum(weights)
        avg = {}
        for dm in all_dms:
            weighted_sum = 0.0
            for i, p in enumerate(patterns):
                if dm in p:
                    weighted_sum += p[dm] * weights[i]
                else:
                    val = _interpolate_hist_pattern(p, dm)
                    weighted_sum += val * weights[i]
            avg[dm] = weighted_sum / total_weight
    else:
        avg = {}
        for dm in all_dms:
            values = []
            for p in patterns:
                if dm in p:
                    values.append(p[dm])
                else:
                    val = _interpolate_hist_pattern(p, dm)
                    values.append(val)
            avg[dm] = sum(values) / len(values)

    if 0 not in avg:
        avg[0] = 1.0

    return avg


def fetch_real_daily_sales_for_projetos(db: Session, projetos: list, days_history: Optional[int] = None, sales_goal: int = 1000, ano: Optional[int] = None, evento_grupo: Optional[str] = None, data_evento: Optional[date] = None, preloaded_hist_pattern: object = "NOT_SET", data_evento_real: Optional[date] = None) -> list:
    from ...services.snapshot_service import get_snapshot_vendas
    
    today = today_brazil()
    if ano is None:
        ano = today.year
    
    all_skus = []
    for projeto in projetos:
        if hasattr(projeto, 'codigo') and projeto.codigo:
            all_skus.append(str(projeto.codigo).upper().strip())
    
    if not all_skus:
        return []
    
    ativo_ids = []
    magento_ids = []
    
    all_active_mappings = _wq_sku_mappings_by_skus(db, all_skus)
    if all_active_mappings is None:
        all_active_mappings = db.query(SkuMapping).filter(
            SkuMapping.sku.in_(all_skus),
            SkuMapping.ativo == True
        ).all()
    
    year_mappings = [m for m in all_active_mappings if m.ano == ano]
    if not year_mappings and all_active_mappings:
        available_years = sorted(set(m.ano for m in all_active_mappings if m.ano), reverse=True)
        if available_years:
            best_year = available_years[0]
            logger.info(f"No SkuMappings for SKUs {all_skus} in year {ano}, using year {best_year}")
            year_mappings = [m for m in all_active_mappings if m.ano == best_year]
    
    for m in year_mappings:
        if m.id_externo:
            if m.fonte == 'ATIVO':
                ativo_ids.append(str(m.id_externo))
            elif m.fonte == 'MAGENTO':
                magento_ids.append(str(m.id_externo))
    
    if not ativo_ids and not magento_ids:
        logger.warning(f"No SkuMappings found for SKUs {all_skus} in any year")
    
    all_daily = {}
    
    snapshot_used = False
    today_in_snapshot = False
    if evento_grupo:
        snapshot_data = get_snapshot_vendas(db, evento_grupo, data_fim=today)
        if snapshot_data:
            all_daily.update(snapshot_data)
            snapshot_used = True
            today_in_snapshot = today in snapshot_data
            logger.debug(f"Snapshot loaded for '{evento_grupo}': {len(snapshot_data)} days up to {today} (today_in_snapshot={today_in_snapshot})")

    if not snapshot_used:
        if ativo_ids:
            ativo_rows = _fetch_daily_sales_ativo_by_ids(list(set(ativo_ids)))
            for row in ativo_rows:
                d = date.fromisoformat(row['dia']) if isinstance(row['dia'], str) else row['dia']
                all_daily[d] = all_daily.get(d, 0) + row['qtd']
        
        if magento_ids:
            _cort = _get_cortesia_magento_ids(db)
            _mag_cort = set(magento_ids) & _cort if _cort else None
            magento_rows = _fetch_daily_sales_magento_by_ids(list(set(magento_ids)), cortesia_magento_ids=_mag_cort if _mag_cort else None)
            for row in magento_rows:
                d = date.fromisoformat(row['dia']) if isinstance(row['dia'], str) else row['dia']
                all_daily[d] = all_daily.get(d, 0) + row['qtd']
    else:
        event_already_happened = data_evento_real and data_evento_real < today
        if event_already_happened:
            logger.debug(f"Event '{evento_grupo}' already happened ({data_evento_real}), skipping today's live sales query")
        elif today_in_snapshot and all_daily.get(today, 0) > 0:
            logger.debug(f"Today's data already in snapshot for '{evento_grupo}' (qty={all_daily.get(today, 0)}), skipping live query")
        else:
            if ativo_ids:
                try:
                    today_sales = _fetch_today_sales_ativo_by_ids(list(set(ativo_ids)))
                    for d, qty in today_sales.items():
                        all_daily[d] = all_daily.get(d, 0) + qty
                except Exception as e:
                    logger.warning(f"Failed to fetch today's Ativo sales: {e}")
            if magento_ids:
                try:
                    _cort = _get_cortesia_magento_ids(db)
                    _mag_cort = set(magento_ids) & _cort if _cort else None
                    today_sales = _fetch_today_sales_magento_by_ids(list(set(magento_ids)), cortesia_magento_ids=_mag_cort if _mag_cort else None)
                    for d, qty in today_sales.items():
                        all_daily[d] = all_daily.get(d, 0) + qty
                except Exception as e:
                    logger.warning(f"Failed to fetch today's Magento sales: {e}")
    
    if not all_daily:
        if days_history:
            start_date = today - timedelta(days=days_history)
        else:
            start_date = today - timedelta(days=60)
        end_date = today
    else:
        earliest = min(all_daily.keys())
        latest_sale = max(all_daily.keys())
        if (today - latest_sale).days > 30:
            end_date = latest_sale
        else:
            end_date = today
        if days_history:
            start_date = max(earliest, end_date - timedelta(days=days_history))
        else:
            start_date = earliest

    # Cap end_date at the real event date if the event has already passed
    if data_evento_real and data_evento_real < today:
        end_date = min(end_date, data_evento_real)
    
    all_dates = [start_date + timedelta(days=i) for i in range((end_date - start_date).days + 1)]
    total_days = len(all_dates)

    hist_pattern = None
    if preloaded_hist_pattern != "NOT_SET":
        hist_pattern = preloaded_hist_pattern
    elif evento_grupo and data_evento:
        try:
            hist_pattern, _ = _resolve_hist_pattern(db, evento_grupo, ano)
        except Exception as e:
            logger.warning(f"Error fetching historical pattern for '{evento_grupo}': {e}")
    
    hist_known_dms = None
    hist_max_known = None
    hist_min_known = None
    if hist_pattern:
        hist_known_dms = sorted(hist_pattern.keys(), reverse=True)
        hist_max_known = hist_known_dms[0]
        hist_min_known = hist_known_dms[-1]

    cumulative_sales = 0
    cumulative_expected = 0
    result = []
    for d in all_dates:
        sales = all_daily.get(d, 0)
        cumulative_sales += sales

        if hist_pattern and data_evento and hist_known_dms:
            dm = (data_evento - d).days

            if dm in hist_pattern:
                pct = hist_pattern[dm]
            elif dm > hist_max_known:
                # Beyond the historical range: linearly extrapolate from 0% at D-90
                # to hist_pattern[hist_max_known] at D-hist_max_known so the expected
                # curve is populated even when the current campaign started earlier
                # than the reference year's campaign.
                anchor_pct = hist_pattern[hist_max_known]
                linear_ref = 90
                if dm >= linear_ref or linear_ref == hist_max_known:
                    pct = 0.0
                else:
                    pct = anchor_pct * (linear_ref - dm) / (linear_ref - hist_max_known)
                    pct = max(0.0, pct)
            elif dm <= hist_min_known:
                pct = hist_pattern[hist_min_known]
            else:
                pct = 0.0
                for i in range(len(hist_known_dms) - 1):
                    if hist_known_dms[i] >= dm >= hist_known_dms[i + 1]:
                        upper_dm = hist_known_dms[i]
                        lower_dm = hist_known_dms[i + 1]
                        ratio = (upper_dm - dm) / (upper_dm - lower_dm) if upper_dm != lower_dm else 0
                        pct = hist_pattern[upper_dm] + ratio * (hist_pattern[lower_dm] - hist_pattern[upper_dm])
                        break

            cumulative_expected = pct * sales_goal
            expected = cumulative_expected - (result[-1]['cumulativeExpected'] if result else 0)
            expected = max(0, expected)
        else:
            expected = sales_goal / total_days if total_days > 0 else 0
            cumulative_expected += expected

        dm = (data_evento - d).days if data_evento else None
        cum_exp_rounded = round(cumulative_expected, 1)
        dif = cumulative_sales - cum_exp_rounded
        ating_acum = round((cumulative_sales - cum_exp_rounded) / cum_exp_rounded * 100, 1) if cum_exp_rounded > 0 else 0.0
        expected_rounded = round(expected, 1)
        ating_diario = round((sales - expected_rounded) / expected_rounded * 100, 1) if expected_rounded > 0 else 0.0

        curva_pct = None
        if hist_pattern and data_evento and hist_known_dms:
            lookup_dm = (data_evento - d).days
            if lookup_dm in hist_pattern:
                curva_pct = round(hist_pattern[lookup_dm] * 100, 1)
            elif lookup_dm > hist_max_known:
                anchor_pct2 = hist_pattern[hist_max_known]
                linear_ref2 = 90
                if lookup_dm >= linear_ref2 or linear_ref2 == hist_max_known:
                    curva_pct = 0.0
                else:
                    extrapolated = anchor_pct2 * (linear_ref2 - lookup_dm) / (linear_ref2 - hist_max_known)
                    curva_pct = round(max(0.0, extrapolated) * 100, 1)
            elif lookup_dm <= hist_min_known:
                curva_pct = round(hist_pattern[hist_min_known] * 100, 1)
            else:
                for i in range(len(hist_known_dms) - 1):
                    if hist_known_dms[i] >= lookup_dm >= hist_known_dms[i + 1]:
                        upper_dm = hist_known_dms[i]
                        lower_dm = hist_known_dms[i + 1]
                        ratio = (upper_dm - lookup_dm) / (upper_dm - lower_dm) if upper_dm != lower_dm else 0
                        curva_pct = round((hist_pattern[upper_dm] + ratio * (hist_pattern[lower_dm] - hist_pattern[upper_dm])) * 100, 1)
                        break

        result.append({
            "date": d.isoformat(),
            "sales": sales,
            "expected": expected_rounded,
            "cumulativeSales": cumulative_sales,
            "cumulativeExpected": cum_exp_rounded,
            "dMinus": dm,
            "curvaAnoAnterior": curva_pct,
            "dif": round(dif, 1),
            "atingimentoAcumulado": ating_acum,
            "atingimentoDiario": ating_diario
        })
    
    result = normalize_daily_sales_outliers(result)

    return result


def normalize_daily_sales_outliers(daily_sales_list: list, window: int = 7, threshold: float = 2.0, spread: int = 3) -> list:
    import statistics

    n = len(daily_sales_list)
    if n < window:
        for item in daily_sales_list:
            item["normalizedSales"] = item["sales"]
            item["localMedian"] = None
            item["outlierLimit"] = None
            item["isOutlier"] = False
            item["excessRemoved"] = 0
            item["excessReceived"] = 0
        cum = 0
        for item in daily_sales_list:
            cum += item["normalizedSales"]
            item["cumulativeNormalized"] = cum
        return daily_sales_list

    raw_sales = [item["sales"] for item in daily_sales_list]
    normalized = list(raw_sales)

    non_zero = [s for s in raw_sales if s > 0]
    global_median = statistics.median(non_zero) if non_zero else 0
    min_threshold = max(global_median * 0.5, 5)

    local_medians = [None] * n
    outlier_limits = [None] * n
    is_outlier = [False] * n
    excess_removed = [0.0] * n
    excess_received = [0.0] * n

    for i in range(n):
        half = window // 2
        start = max(0, i - half)
        end = min(n, i + half + 1)
        local_window = raw_sales[start:end]
        if len(local_window) < 3:
            continue
        median_val = statistics.median(local_window)
        limit = max(median_val * threshold, min_threshold)
        local_medians[i] = round(median_val, 1)
        outlier_limits[i] = round(limit, 1)
        if raw_sales[i] > limit:
            excess = raw_sales[i] - limit
            normalized[i] = limit
            is_outlier[i] = True
            excess_removed[i] = excess
            spread_start = max(0, i - spread)
            spread_end = min(n, i + spread + 1)
            neighbors = [j for j in range(spread_start, spread_end) if j != i]
            if not neighbors:
                continue
            neighbor_sales = [max(raw_sales[j], 1) for j in neighbors]
            total_weight = sum(neighbor_sales)
            for idx, j in enumerate(neighbors):
                proportion = neighbor_sales[idx] / total_weight
                share = excess * proportion
                normalized[j] += share
                excess_received[j] += share

    cum = 0
    for i, item in enumerate(daily_sales_list):
        item["normalizedSales"] = round(normalized[i], 1)
        cum += normalized[i]
        item["cumulativeNormalized"] = round(cum, 1)
        item["localMedian"] = local_medians[i]
        item["outlierLimit"] = outlier_limits[i]
        item["isOutlier"] = is_outlier[i]
        item["excessRemoved"] = round(excess_removed[i], 1)
        item["excessReceived"] = round(excess_received[i], 1)

    return daily_sales_list


def get_kit_basico_cost(db: Session, projeto_id: int) -> float:
    """
    Busca o custo total do Kit Básico para um projeto.
    Soma os valores unitários de todos os itens do kit com nome 'Básico'.
    Retorna 50.0 como fallback se não encontrar.
    """
    try:
        cadastro = db.query(CadastroEvento).filter(
            CadastroEvento.projeto_id == projeto_id
        ).first()
        
        if not cadastro:
            return 50.0
        
        kit_basico = db.query(CadastroKitProduto).filter(
            CadastroKitProduto.cadastro_id == cadastro.id,
            CadastroKitProduto.kit.ilike('%básico%')
        ).first()
        
        if not kit_basico:
            kit_basico = db.query(CadastroKitProduto).filter(
                CadastroKitProduto.cadastro_id == cadastro.id,
                CadastroKitProduto.kit.ilike('%basico%')
            ).first()
        
        if not kit_basico:
            return 50.0
        
        itens = db.query(CadastroKitProdutoItem).filter(
            CadastroKitProdutoItem.kit_produto_id == kit_basico.id
        ).all()
        
        if not itens:
            return 50.0
        
        total = sum(float(item.valor_unitario or 0) for item in itens)
        return total if total > 0 else 50.0
        
    except Exception as e:
        logger.error(f"Erro ao buscar custo do Kit Básico para projeto {projeto_id}: {e}")
        return 50.0

def get_kit_basico_costs_batch(db: Session, projeto_ids: List[int]) -> dict:
    """
    Busca o custo do Kit Básico para vários projetos de uma vez.
    Retorna dict {projeto_id: custo}.
    """
    costs = {}
    
    try:
        cadastros = db.query(CadastroEvento).filter(
            CadastroEvento.projeto_id.in_(projeto_ids)
        ).all()
        
        cadastro_map = {c.projeto_id: c.id for c in cadastros}
        
        if not cadastro_map:
            return {pid: 50.0 for pid in projeto_ids}
        
        kits = db.query(CadastroKitProduto).filter(
            CadastroKitProduto.cadastro_id.in_(list(cadastro_map.values())),
            (CadastroKitProduto.kit.ilike('%básico%') | CadastroKitProduto.kit.ilike('%basico%'))
        ).all()
        
        kit_map = {}
        for kit in kits:
            for pid, cid in cadastro_map.items():
                if kit.cadastro_id == cid:
                    kit_map[pid] = kit.id
                    break
        
        if kit_map:
            itens = db.query(CadastroKitProdutoItem).filter(
                CadastroKitProdutoItem.kit_produto_id.in_(list(kit_map.values()))
            ).all()
            
            item_costs = {}
            for item in itens:
                if item.kit_produto_id not in item_costs:
                    item_costs[item.kit_produto_id] = 0
                item_costs[item.kit_produto_id] += float(item.valor_unitario or 0)
            
            for pid, kit_id in kit_map.items():
                costs[pid] = item_costs.get(kit_id, 50.0)
                if costs[pid] == 0:
                    costs[pid] = 50.0
        
        for pid in projeto_ids:
            if pid not in costs:
                costs[pid] = 50.0
                
    except Exception as e:
        logger.error(f"Erro ao buscar custos de Kit Básico em batch: {e}")
        costs = {pid: 50.0 for pid in projeto_ids}
    
    return costs


def get_kit_breakdown_for_projetos(db: Session, projeto_ids: List[int], ano: Optional[int] = None) -> dict:
    """
    Returns {projeto_id: [{tipoKit: str, custoKit: float|None}]} for ALL kit types
    registered in CadastroKitProduto for each projeto.
    Cost resolution: kit_config.custo_kit override (matched by tipo_kit == kit name) first,
    then sum of CadastroKitProdutoItem values.
    """
    from ...models.kit_config import KitConfig

    if not projeto_ids:
        return {}

    try:
        result: dict = {pid: [] for pid in projeto_ids}

        # Build KitConfig override map: tipo_kit (name) -> custo_kit
        # We fetch all kit configs that have custo_kit set and tipo_kit set
        override_map: dict = {}
        all_overrides = db.query(KitConfig).filter(
            KitConfig.tipo_kit.isnot(None),
            KitConfig.custo_kit.isnot(None),
        ).all()
        for ov in all_overrides:
            if ov.tipo_kit and ov.tipo_kit not in override_map:
                override_map[ov.tipo_kit] = float(ov.custo_kit)

        for pid in projeto_ids:
            cad = db.query(CadastroEvento).filter(CadastroEvento.projeto_id == pid).first()
            if not cad:
                continue

            kit_configs_db = db.query(CadastroKitProduto).filter(
                CadastroKitProduto.cadastro_id == cad.id
            ).all()
            if not kit_configs_db:
                continue

            kit_ids = [kc.id for kc in kit_configs_db]
            all_items = db.query(CadastroKitProdutoItem).filter(
                CadastroKitProdutoItem.kit_produto_id.in_(kit_ids)
            ).all()
            items_by_kit: dict = {}
            for item in all_items:
                items_by_kit.setdefault(item.kit_produto_id, []).append(item)

            for kc in kit_configs_db:
                kit_name = (kc.kit or '').strip()
                if not kit_name:
                    continue
                # Cost override from KitConfig takes priority
                if kit_name in override_map:
                    custo: float | None = override_map[kit_name]
                else:
                    cost_sum = sum(float(i.valor_unitario or 0) for i in items_by_kit.get(kc.id, []))
                    custo = round(cost_sum, 2) if cost_sum > 0 else None

                result[pid].append({
                    "tipoKit": kit_name,
                    "custoKit": round(custo, 2) if custo is not None else None,
                })

        return result

    except Exception as e:
        logger.error(f"Erro ao buscar kit breakdown para projetos: {e}")
        return {}


def _calc_margin_fields(budget_ticket: float, kit_cost: float, sales_goal: int,
                        avg_ticket: float, current_sales: int, current_receita: float) -> dict:
    has_budget = budget_ticket > 0 and kit_cost > 0
    has_sales = current_sales > 0 and avg_ticket > 0

    margem_orcada_unit = round(budget_ticket - kit_cost, 2) if has_budget else 0.0
    margem_orcada_total = round(margem_orcada_unit * sales_goal, 2) if has_budget else 0.0
    # Margem bruta orçada % = (ticket_orcado - custo_kit) / ticket_orcado
    margem_orcada_pct = round((margem_orcada_unit / budget_ticket) * 100, 1) if has_budget else 0.0

    margem_realizada_unit = round(avg_ticket - kit_cost, 2) if has_sales else 0.0
    margem_realizada_total = round(current_receita - (kit_cost * current_sales), 2) if has_sales else 0.0
    # Margem bruta realizada % = (ticket_medio - custo_kit) / ticket_medio
    margem_realizada_pct = round((margem_realizada_unit / avg_ticket) * 100, 1) if has_sales else 0.0

    # Taxa de realização da margem = quanto do total de margem orçada foi capturado até agora
    # Fórmula: margem_realizada_R$ / margem_orcada_R$ * 100
    # Indica o progresso financeiro real vs. o plano (ex: 45% = capturou 45% da margem total planejada)
    margem_realizacao_rate = 0.0
    if margem_orcada_total > 0 and has_sales:
        margem_realizacao_rate = round((margem_realizada_total / margem_orcada_total) * 100, 1)

    receita_orcada_total = round(budget_ticket * sales_goal, 2) if has_budget else 0.0

    return {
        "kitCostPerUnit": round(kit_cost, 2),
        "receitaOrcadaTotal": receita_orcada_total,
        "currentReceita": round(current_receita, 2) if has_sales else 0.0,
        "margemOrcadaUnit": margem_orcada_unit,
        "margemOrcadaTotal": margem_orcada_total,
        "margemOrcadaPct": margem_orcada_pct,
        "margemRealizadaUnit": margem_realizada_unit,
        "margemRealizadaTotal": margem_realizada_total,
        "margemRealizadaPct": margem_realizada_pct,
        "margemRealizacaoRate": margem_realizacao_rate,
    }


# Cache em memória para resultados de receita Magento por bundle.
# A revenue query (com join de filhos por nome) é lenta para eventos de alto volume.
# O dado de receita muda raramente dentro de uma sessão — TTL de 4h é suficiente.
_margem_rev_cache: dict = {}  # frozenset(bundle_ids) → (rev_by_bid: dict, timestamp: float)
_MARGEM_REV_TTL_SECONDS = 14400  # 4 horas

# Cache de falhas da revenue query: evita re-tentar o Magento repetidamente quando
# a query já falhou recentemente (ex: timeout). Após o cooldown, tenta novamente.
_margem_rev_failure_cache: dict = {}  # frozenset(bundle_ids) → timestamp da última falha
_MARGEM_REV_FAILURE_COOLDOWN_SECONDS = 1800  # 30 minutos


def _build_consistency_warning(total_isc: Optional[int], margem_por_kit: Optional[list]) -> Optional[dict]:
    """
    Compara total de inscrições do card ISC com a soma da tabela Margem por Tipo de Kit.
    Retorna um dict de aviso quando a diferença excede a tolerância (2% ou 20 inscrições).
    """
    try:
        if not margem_por_kit or not total_isc or total_isc <= 0:
            return None
        total_margem = sum(int(row.get("qtd", 0) or 0) for row in margem_por_kit)
        if total_margem <= 0:
            return None
        diff = total_isc - total_margem
        abs_diff = abs(diff)
        diff_pct = (abs_diff / total_isc) * 100 if total_isc else 0.0
        tolerance_abs = max(20, int(total_isc * 0.02))
        if abs_diff <= tolerance_abs:
            return None
        return {
            "totalIsc": int(total_isc),
            "totalMargem": int(total_margem),
            "diff": int(diff),
            "diffAbs": int(abs_diff),
            "diffPct": round(diff_pct, 2),
            "tolerance": int(tolerance_abs),
        }
    except Exception as _e:
        logger.warning(f"[Consistency] falha ao calcular aviso: {_e}")
        return None


def get_margem_por_kit(
    db: Session,
    projeto_ids: list,
    ano: Optional[int] = None,
    card_total_qty: Optional[int] = None,
    card_total_receita: Optional[float] = None,
    card_kit_cost_avg: Optional[float] = None,
    avisos_out: Optional[list] = None,
    force_refresh: bool = False,
    incluir_cortesias: bool = False,
) -> list:
    """Quebra de margem por tipo de kit via vendas Magento bundle."""
    from ...models.kit_config import KitConfig

    if not projeto_ids:
        return []

    try:
        # 1. Cadastro do Evento → Kits & Produtos serve APENAS como fonte de custo
        # por nome (auto-preenchimento). O nome dos kits exibidos e o custo final
        # vêm do KitConfig (mapeamento). Aqui só montamos um dicionário
        # {nome_kit -> custo_itens} para servir de fallback quando o KitConfig
        # não tiver custo_kit preenchido.
        kit_map: dict = {}
        cadastro_cost_by_name: dict = {}

        for pid in projeto_ids:
            cadastro = db.query(CadastroEvento).filter(CadastroEvento.projeto_id == pid).first()
            if not cadastro:
                continue

            kit_configs_db = db.query(CadastroKitProduto).filter(
                CadastroKitProduto.cadastro_id == cadastro.id
            ).all()
            if not kit_configs_db:
                continue

            kit_ids = [kc.id for kc in kit_configs_db]
            all_items = db.query(CadastroKitProdutoItem).filter(
                CadastroKitProdutoItem.kit_produto_id.in_(kit_ids)
            ).all()
            items_by_kit: dict = {}
            for item in all_items:
                items_by_kit.setdefault(item.kit_produto_id, []).append(item)

            for kc in kit_configs_db:
                kit_name = (kc.kit or "").strip()
                if not kit_name:
                    continue
                cost = sum(float(i.valor_unitario or 0) for i in items_by_kit.get(kc.id, []))
                # Se o mesmo nome aparece em múltiplos projetos, preserva o primeiro custo > 0.
                if kit_name not in cadastro_cost_by_name or (cost > 0 and cadastro_cost_by_name[kit_name] == 0):
                    cadastro_cost_by_name[kit_name] = cost

        # 2. SKU mappings filtrados por ano para evitar contaminação entre edições
        proj_by_id = {
            pid: db.query(DimProjeto).filter(DimProjeto.id == pid).first()
            for pid in projeto_ids
        }

        def _get_sku_maps(pid, fonte):
            proj = proj_by_id.get(pid)
            if not proj or not proj.codigo:
                return []
            sku = proj.codigo.upper().strip()
            q = db.query(SkuMapping).filter(
                SkuMapping.sku == sku,
                SkuMapping.fonte == fonte,
                SkuMapping.ativo == True,
            )
            if ano:
                q = q.filter(SkuMapping.ano == ano)
            return q.all()

        # 3. Magento: deduplicação de event IDs e bundle IDs entre todos os projetos
        seen_magento_events: set = set()
        seen_bundle_ids: set = set()
        global_bundle_tipo_map: dict = {}  # bundle_entity_id -> tipo_kit
        custo_kit_override: dict = {}  # tipo_kit -> custo manual (kit_config.custo_kit)

        for pid in projeto_ids:
            for sm in _get_sku_maps(pid, 'MAGENTO'):
                if not sm.id_externo:
                    continue
                try:
                    magento_event_int = int(sm.id_externo)
                except (ValueError, TypeError):
                    continue
                if magento_event_int in seen_magento_events:
                    continue
                seen_magento_events.add(magento_event_int)

                bundles = db.query(KitConfig).filter(
                    KitConfig.id_evento == magento_event_int,
                    KitConfig.tipo_kit.isnot(None)
                ).all()
                for b in bundles:
                    if b.tipo_kit and b.bundle_entity_id not in seen_bundle_ids:
                        seen_bundle_ids.add(b.bundle_entity_id)
                        global_bundle_tipo_map[b.bundle_entity_id] = b.tipo_kit
                        if b.custo_kit is not None:
                            custo_kit_override[b.tipo_kit] = float(b.custo_kit)

        # Seed kit_map com TODOS os tipo_kit do mapeamento (KitConfig), mesmo sem
        # vendas. Assim o card lista exatamente os kits que o admin configurou.
        # O custo vem do KitConfig.custo_kit; se nulo, cai no custo-por-nome do
        # cadastro do evento (soma dos itens). Se nenhuma fonte tem valor, custo=0.
        for _tipo_kit in set(global_bundle_tipo_map.values()):
            if not _tipo_kit or _tipo_kit in kit_map:
                continue
            _seed_cost = 0.0
            _seed_has_cost = False
            if _tipo_kit in custo_kit_override:
                _seed_cost = custo_kit_override[_tipo_kit]
                _seed_has_cost = True
            elif _tipo_kit in cadastro_cost_by_name:
                _seed_cost = cadastro_cost_by_name[_tipo_kit]
                _seed_has_cost = _seed_cost > 0
            kit_map[_tipo_kit] = {
                "custo": _seed_cost,
                "ativo_categoria": None,
                "qtd": 0,
                "receita": 0.0,
                "has_cost": _seed_has_cost,
            }

        import datetime as _dt
        _ano = ano if ano else _dt.datetime.now().year

        # Fetch ticket_atual (special_price) per tipo_kit from Magento
        tipo_kit_ticket_atual: dict = {}
        if global_bundle_tipo_map and db_module.engine_magento is not None:
            from ..routes.kit_config import MAGENTO_KITS_QUERY
            _bid_set = set(global_bundle_tipo_map.keys())
            _kcs_sp = db.query(KitConfig).filter(
                KitConfig.bundle_entity_id.in_(list(_bid_set))
            ).all()
            _kc_mult_by_bid = {k.bundle_entity_id: (k.multiplicador or 1) for k in _kcs_sp}
            try:
                with db_module.engine_magento.connect() as _conn_sp:
                    _mq_res = _conn_sp.execute(text(MAGENTO_KITS_QUERY))
                    _mq_rows = _mq_res.fetchall()
                    _mq_cols = list(_mq_res.keys())
                _sp_by_bid: dict = {}
                for _r in _mq_rows:
                    _d = dict(zip(_mq_cols, _r))
                    _bid_v = _d.get("bundle_entity_id")
                    if _bid_v is None:
                        continue
                    _bid_i = int(_bid_v)
                    if _bid_i not in _bid_set or _bid_i in _sp_by_bid:
                        continue
                    _sp_v = float(_d["special_price"]) if _d.get("special_price") is not None else None
                    if _sp_v is None:
                        _sp_v = float(_d["price"]) if _d.get("price") is not None else None
                    if _sp_v is not None:
                        _sp_by_bid[_bid_i] = _sp_v
                for _bid_k, _tipo_k in global_bundle_tipo_map.items():
                    _sp_k = _sp_by_bid.get(_bid_k)
                    _mc_k = _kc_mult_by_bid.get(_bid_k, 1)
                    if _sp_k is not None:
                        tipo_kit_ticket_atual[_tipo_k] = round(_sp_k * _mc_k, 2)
            except Exception as _e_sp:
                logger.warning(f"Erro ao buscar special_price por tipo de kit: {_e_sp}")

        _skip_cortesia_filter = bool(incluir_cortesias)

        if global_bundle_tipo_map and db_module.engine_magento is not None:
            bundle_ids = list(global_bundle_tipo_map.keys())
            # Cortesia filters are expressed as SQL-level boolean parameters so the
            # query strings remain static — no string concatenation or f-strings are
            # used inside text(), following SQLAlchemy best practices.
            # :skip_cortesia_filter = True  → OR short-circuits, clause is skipped
            # :skip_cortesia_filter = False → the filter condition is enforced
            _sql_count = (
                "SELECT /*+ MAX_EXECUTION_TIME(20000) */\n"
                "    soi_parent.product_id                  AS bundle_entity_id,\n"
                "    COUNT(DISTINCT soi_parent.item_id)     AS qtd\n"
                "FROM sales_order so\n"
                "INNER JOIN sales_order_item soi_parent\n"
                "       ON soi_parent.order_id     = so.entity_id\n"
                "      AND soi_parent.product_type = 'bundle'\n"
                "      AND soi_parent.product_id   IN :bundle_ids\n"
                "WHERE\n"
                "    so.created_at >= DATE_SUB(CURDATE(), INTERVAL 2 YEAR)\n"
                "AND so.status IN ('processing', 'complete', 'approved', 'aprovado_link', 'reembolso_parcial', 'closed', 'retirado')\n"
                "AND so.state != 'canceled'\n"
                "AND (:skip_cortesia_filter OR so.base_grand_total > 0)\n"
                "AND (:skip_cortesia_filter OR NOT (so.discount_description LIKE '%%CORTESIA%%' AND so.base_grand_total < 50))\n"
                "AND so.created_at < CURDATE() + INTERVAL 1 DAY\n"
                "AND (so.discount_description IS NULL OR so.discount_description NOT LIKE '%%GRUPOS%%')\n"
                "AND (so.coupon_code IS NULL OR so.coupon_code NOT LIKE 'GRUP%%')\n"
                "AND so.increment_id NOT REGEXP '-[0-9]'\n"
                "GROUP BY soi_parent.product_id"
            )
            magento_count_query = text(_sql_count).bindparams(
                bindparam("bundle_ids", expanding=True),
                skip_cortesia_filter=_skip_cortesia_filter,
            )

            # Query 2: receita — mesmo padrão de partida (sales_order com índice created_at)
            # + join filho para valor da distância/modalidade.
            # Timeout elevado para 55s: eventos de alto volume precisam de ~20-25s.
            # Resultado armazenado em cache em memória por 4h (_margem_rev_cache).
            # A segunda chamada (mesmos bundle_ids) é instantânea.
            _sql_bundle = (
                "SELECT /*+ MAX_EXECUTION_TIME(55000) */\n"
                "    soi_parent.product_id                                                              AS bundle_entity_id,\n"
                "    ROUND(SUM(soi_child.price - soi_child.discount_amount), 2)                        AS receita_liquida\n"
                "FROM sales_order so\n"
                "INNER JOIN sales_order_item soi_parent\n"
                "       ON soi_parent.order_id     = so.entity_id\n"
                "      AND soi_parent.product_type = 'bundle'\n"
                "      AND soi_parent.product_id   IN :bundle_ids\n"
                "INNER JOIN sales_order_item soi_child\n"
                "       ON soi_child.parent_item_id = soi_parent.item_id\n"
                "      AND soi_child.product_type   = 'simple'\n"
                "      AND (:skip_cortesia_filter OR (soi_child.price > 0 AND soi_child.price - soi_child.discount_amount > 0))\n"
                "      AND (\n"
                "            soi_child.name LIKE '%%Distância%%'\n"
                "         OR soi_child.name LIKE '%%Distancia%%'\n"
                "         OR soi_child.name LIKE '%%Distâncias%%'\n"
                "         OR soi_child.name LIKE '%%Modalidade%%'\n"
                "      )\n"
                "WHERE\n"
                "    so.created_at >= DATE_SUB(CURDATE(), INTERVAL 2 YEAR)\n"
                "AND so.status IN ('processing', 'complete', 'approved', 'aprovado_link', 'reembolso_parcial', 'closed', 'retirado')\n"
                "AND so.state != 'canceled'\n"
                "AND (:skip_cortesia_filter OR so.base_grand_total > 0)\n"
                "AND (:skip_cortesia_filter OR NOT (so.discount_description LIKE '%%CORTESIA%%' AND so.base_grand_total < 50))\n"
                "AND so.created_at < CURDATE() + INTERVAL 1 DAY\n"
                "AND (so.discount_description IS NULL OR so.discount_description NOT LIKE '%%GRUPOS%%')\n"
                "AND (so.coupon_code IS NULL OR so.coupon_code NOT LIKE 'GRUP%%')\n"
                "AND so.increment_id NOT REGEXP '-[0-9]'\n"
                "GROUP BY soi_parent.product_id"
            )
            magento_bundle_query = text(_sql_bundle).bindparams(
                bindparam("bundle_ids", expanding=True),
                skip_cortesia_filter=_skip_cortesia_filter,
            )

            import time as _time

            def _log_margem_magento_failed(e_exc, label="primary"):
                _aviso = "Dados do Magento indisponíveis — totais de inscrições e receita podem estar incompletos."
                if avisos_out is not None and _aviso not in avisos_out:
                    avisos_out.append(_aviso)
                try:
                    from app.services.health_alert_service import log_and_alert as _la
                    from ...models.dimensoes import DimProjeto as _DP
                    _pid = projeto_ids[0] if projeto_ids else None
                    _nome = None
                    if _pid:
                        try:
                            _proj = db.query(_DP).filter(_DP.id == _pid).first()
                            _nome = _proj.evento if _proj else None
                        except Exception:
                            pass
                    _evento_label = _nome or f"projeto_id={_pid}"
                    _la(
                        event_type="MARGEM_MAGENTO_FAILED",
                        severity="HIGH",
                        message=f"Falha na query Magento ({label}) — Margem por Kit: {_evento_label}: {type(e_exc).__name__}",
                        detail=str(e_exc)[:1000],
                    )
                except Exception as _ha_err:
                    logger.warning(f"[HealthAlert] Falha ao registrar MARGEM_MAGENTO_FAILED: {_ha_err}")

            # Executa count e receita como blocos independentes: se a receita falhar,
            # a contagem já calculada é preservada (evita perder qtd por timeout na receita).
            qtd_by_bid: dict = {}
            rev_by_bid: dict = {}

            # --- Query 1: Contagem de inscrições por bundle ---
            try:
                with db_module.engine_magento.connect() as conn:
                    _t0 = _time.monotonic()
                    count_result = conn.execute(magento_count_query, {"bundle_ids": bundle_ids})
                    for row in count_result.fetchall():
                        qtd_by_bid[int(row[0])] = int(row[1] or 0)
                    logger.info(f"[Margem] count_query: {len(bundle_ids)} bundles → {len(qtd_by_bid)} linhas em {_time.monotonic()-_t0:.2f}s")
            except Exception as e:
                logger.error(f"Erro ao buscar vendas Magento por bundle para margem: {e}")
                _log_margem_magento_failed(e, "count")

            # --- Query 2: Receita por bundle (join com itens-filho) ---
            # A join com soi_child por nome (LIKE) é lenta para eventos de alto volume
            # porque parent_item_id pode não ter índice no Magento 2.
            # Usamos cache em memória com TTL de 4h para evitar re-executar a cada request.
            _rev_cache_key = (frozenset(bundle_ids), incluir_cortesias)
            _now_mono = _time.monotonic()
            if force_refresh:
                _margem_rev_cache.pop(_rev_cache_key, None)
                _margem_rev_failure_cache.pop(_rev_cache_key, None)
            _cached = _margem_rev_cache.get(_rev_cache_key)
            _last_failure = _margem_rev_failure_cache.get(_rev_cache_key)
            if _cached and (_now_mono - _cached[1]) < _MARGEM_REV_TTL_SECONDS:
                rev_by_bid = dict(_cached[0])
                logger.info(f"[Margem] revenue_query cache HIT: {len(bundle_ids)} bundles → {len(rev_by_bid)} entradas (TTL restante: {int(_MARGEM_REV_TTL_SECONDS - (_now_mono - _cached[1]))}s)")
            else:
                # --- Tentar snapshot PostgreSQL antes do Magento ao vivo ---
                _snap_loaded = False
                if not force_refresh:
                    try:
                        from ...models.vendas_snapshot import MargemBundleRevSnapshot as _MBR
                        from datetime import timezone as _tz
                        _snap_rows = db.query(_MBR).filter(
                            _MBR.bundle_entity_id.in_(bundle_ids)
                        ).all()
                        if _snap_rows:
                            _SNAP_MAX_AGE_H = 25
                            _agora_utc = _time.time()
                            _oldest = min(
                                r.calculado_em.replace(tzinfo=_tz.utc).timestamp()
                                if r.calculado_em.tzinfo is None
                                else r.calculado_em.timestamp()
                                for r in _snap_rows
                            )
                            _snap_age_h = (_agora_utc - _oldest) / 3600
                            if _snap_age_h <= _SNAP_MAX_AGE_H:
                                rev_by_bid = {r.bundle_entity_id: float(r.receita_liquida) for r in _snap_rows}
                                _margem_rev_cache[_rev_cache_key] = (dict(rev_by_bid), _now_mono)
                                _margem_rev_failure_cache.pop(_rev_cache_key, None)
                                _snap_loaded = True
                                logger.info(f"[Margem] revenue_query SNAPSHOT HIT (PostgreSQL): {len(bundle_ids)} bundles → {len(rev_by_bid)} entradas (idade {_snap_age_h:.1f}h)")
                    except Exception as _snap_err:
                        logger.warning(f"[Margem] Erro ao ler margem_bundle_rev_snapshot: {_snap_err}")

                if not _snap_loaded:
                    if _last_failure and (_now_mono - _last_failure) < _MARGEM_REV_FAILURE_COOLDOWN_SECONDS:
                        _cooldown_restante = int(_MARGEM_REV_FAILURE_COOLDOWN_SECONDS - (_now_mono - _last_failure))
                        logger.info(f"[Margem] revenue_query SKIPPED (cooldown pós-falha ativo, {_cooldown_restante}s restantes): {len(bundle_ids)} bundles")
                        _aviso_cooldown = "Dados do Magento indisponíveis — totais de inscrições e receita podem estar incompletos."
                        if avisos_out is not None and _aviso_cooldown not in avisos_out:
                            avisos_out.append(_aviso_cooldown)
                    else:
                        try:
                            with db_module.engine_magento.connect() as conn:
                                _t1 = _time.monotonic()
                                rev_result = conn.execute(magento_bundle_query, {"bundle_ids": bundle_ids})
                                for row in rev_result.fetchall():
                                    rev_by_bid[int(row[0])] = float(row[1] or 0)
                                _elapsed = _time.monotonic() - _t1
                                logger.info(f"[Margem] revenue_query LIVE: {len(bundle_ids)} bundles → {len(rev_by_bid)} linhas em {_elapsed:.2f}s")
                                _margem_rev_cache[_rev_cache_key] = (dict(rev_by_bid), _time.monotonic())
                                _margem_rev_failure_cache.pop(_rev_cache_key, None)
                        except Exception as e:
                            logger.error(f"Erro ao buscar receita Magento por bundle para margem: {e}")
                            _margem_rev_failure_cache[_rev_cache_key] = _time.monotonic()
                            _log_margem_magento_failed(e, "revenue")

            # Consolida: usa qtd da query 1 + receita da query 2 (independentes)
            all_bids = set(qtd_by_bid.keys()) | set(rev_by_bid.keys())
            for bid in all_bids:
                qtd = qtd_by_bid.get(bid, 0)
                receita = rev_by_bid.get(bid, 0.0)
                tipo_kit = global_bundle_tipo_map.get(bid)
                if not tipo_kit:
                    continue
                if tipo_kit not in kit_map:
                    kit_map[tipo_kit] = {
                        "custo": 0.0,
                        "ativo_categoria": None,
                        "qtd": 0,
                        "receita": 0.0,
                        "has_cost": False,
                    }
                kit_map[tipo_kit]["qtd"] += qtd
                kit_map[tipo_kit]["receita"] += receita

        # Override custo pelo custo manual do kit_config quando definido.
        # Se o tipo não existe no kit_map (sem Cadastro e sem vendas), cria entrada
        # zerada para que o custo apareça na tabela mesmo sem inscrições.
        for tipo, custo_override in custo_kit_override.items():
            if tipo in kit_map:
                kit_map[tipo]["custo"] = custo_override
                kit_map[tipo]["has_cost"] = True
            else:
                kit_map[tipo] = {
                    "custo": custo_override,
                    "ativo_categoria": None,
                    "qtd": 0,
                    "receita": 0.0,
                    "has_cost": True,
                }

        # KitConfig.ativo_categoria is the authoritative (admin-controlled) mapping source.
        # It overrides any CadastroKitProduto.ativo_categoria that may have been set above.
        for bid, tipo_k in global_bundle_tipo_map.items():
            if tipo_k and tipo_k in kit_map:
                _kc_rec = db.query(KitConfig).filter(
                    KitConfig.bundle_entity_id == bid,
                    KitConfig.ativo_categoria.isnot(None),
                ).first()
                if _kc_rec and _kc_rec.ativo_categoria:
                    kit_map[tipo_k]["ativo_categoria"] = _kc_rec.ativo_categoria

        # 3.5 Fallback: quando algum kit ainda tem qtd=0 (tipo_kit não mapeado no KitConfig),
        # consolida vendas Magento agrupadas por nome do bundle e faz matching por nome
        # contra as chaves do kit_map (ex: "Kit Básico" está contido em "Kit Básico Bravus Race - Speed I")
        kits_sem_venda = [k for k, v in kit_map.items() if v["qtd"] == 0]
        if kits_sem_venda and seen_magento_events and db_module.engine_magento is not None:
            import time as _time  # may not have been imported if primary block was skipped

            try:
                _log_margem_magento_failed  # noqa: F821
            except NameError:
                def _log_margem_magento_failed(e_exc, label=""):
                    _aviso = "Dados do Magento indisponíveis — totais de inscrições e receita podem estar incompletos."
                    if avisos_out is not None and _aviso not in avisos_out:
                        avisos_out.append(_aviso)
            ev_ids_fb = list(seen_magento_events)

            # Estratégia do fallback: pré-busca os product_ids via cpev1 (tabela pequena,
            # bem indexada por attribute_id+store_id+value) e depois reutiliza as mesmas
            # queries eficientes do bloco primário — evita subconsulta correlacionada lenta.
            fb_bundle_ids: list = []
            try:
                _cpev1_q = text("""
SELECT DISTINCT entity_id
FROM   catalog_product_entity_varchar
WHERE  attribute_id = 321
AND    store_id     = 0
AND    value        IN :ev_ids_fb
""").bindparams(bindparam("ev_ids_fb", expanding=True))
                with db_module.engine_magento.connect() as _pid_conn:
                    _pid_rows = _pid_conn.execute(_cpev1_q, {"ev_ids_fb": ev_ids_fb}).fetchall()
                fb_bundle_ids = [int(r[0]) for r in _pid_rows]
                logger.info(f"[Margem] fallback cpev1 prefetch: {len(ev_ids_fb)} ev_ids → {len(fb_bundle_ids)} bundle_ids")

                # Exclui bundles que o usuário deflagou explicitamente no KitConfig
                # (linha existe com tipo_kit=NULL). Sem este filtro, o matching por
                # substring abaixo agrega bundles como "Kit Básico - 21k", "Kit Básico
                # - 42k" e "Kit Básico - 5k" em uma única linha "Kit Básico", mesmo
                # depois do usuário remover a flag.
                if fb_bundle_ids:
                    _deflagged_bids = {
                        r[0] for r in db.query(KitConfig.bundle_entity_id).filter(
                            KitConfig.bundle_entity_id.in_(fb_bundle_ids),
                            KitConfig.tipo_kit.is_(None),
                        ).all()
                    }
                    if _deflagged_bids:
                        _before = len(fb_bundle_ids)
                        fb_bundle_ids = [bid for bid in fb_bundle_ids if bid not in _deflagged_bids]
                        logger.info(f"[Margem] fallback: excluídos {_before - len(fb_bundle_ids)} bundles deflagados (tipo_kit=NULL no KitConfig)")
            except Exception as _cpev1_err:
                logger.warning(f"[Margem] fallback cpev1 prefetch falhou: {_cpev1_err}")

            if fb_bundle_ids:
                # Reutiliza o mesmo padrão das queries primárias, agrupando por nome do bundle
                fb_count_q = text(
                    "SELECT /*+ MAX_EXECUTION_TIME(55000) */\n"
                    "    soi_parent.name                        AS bundle_name,\n"
                    "    COUNT(DISTINCT soi_parent.item_id)     AS qtd\n"
                    "FROM sales_order so\n"
                    "INNER JOIN sales_order_item soi_parent\n"
                    "       ON soi_parent.order_id     = so.entity_id\n"
                    "      AND soi_parent.product_type = 'bundle'\n"
                    "      AND soi_parent.product_id   IN :fb_bundle_ids\n"
                    "WHERE\n"
                    "    so.created_at >= DATE_SUB(CURDATE(), INTERVAL 2 YEAR)\n"
                    "AND so.status IN ('processing', 'complete', 'approved', 'aprovado_link', 'reembolso_parcial', 'closed', 'retirado')\n"
                    "AND so.state != 'canceled'\n"
                    "AND (:skip_cortesia_filter OR so.base_grand_total > 0)\n"
                    "AND (:skip_cortesia_filter OR NOT (so.discount_description LIKE '%%CORTESIA%%' AND so.base_grand_total < 50))\n"
                    "AND so.created_at < CURDATE() + INTERVAL 1 DAY\n"
                    "AND (so.discount_description IS NULL OR so.discount_description NOT LIKE '%%GRUPOS%%')\n"
                    "AND (so.coupon_code IS NULL OR so.coupon_code NOT LIKE 'GRUP%%')\n"
                    "AND so.increment_id NOT REGEXP '-[0-9]'\n"
                    "GROUP BY soi_parent.name"
                ).bindparams(
                    bindparam("fb_bundle_ids", expanding=True),
                    skip_cortesia_filter=_skip_cortesia_filter,
                )

                fb_rev_q = text(
                    "SELECT /*+ MAX_EXECUTION_TIME(55000) */\n"
                    "    soi_parent.name                                                                    AS bundle_name,\n"
                    "    ROUND(SUM(soi_child.price - soi_child.discount_amount), 2)                        AS receita_liquida\n"
                    "FROM sales_order so\n"
                    "INNER JOIN sales_order_item soi_parent\n"
                    "       ON soi_parent.order_id     = so.entity_id\n"
                    "      AND soi_parent.product_type = 'bundle'\n"
                    "      AND soi_parent.product_id   IN :fb_bundle_ids\n"
                    "INNER JOIN sales_order_item soi_child\n"
                    "       ON soi_child.parent_item_id = soi_parent.item_id\n"
                    "      AND soi_child.product_type   = 'simple'\n"
                    "      AND (:skip_cortesia_filter OR (soi_child.price > 0 AND soi_child.price - soi_child.discount_amount > 0))\n"
                    "      AND (\n"
                    "            soi_child.name LIKE '%%Distância%%'\n"
                    "         OR soi_child.name LIKE '%%Distancia%%'\n"
                    "         OR soi_child.name LIKE '%%Distâncias%%'\n"
                    "         OR soi_child.name LIKE '%%Modalidade%%'\n"
                    "      )\n"
                    "WHERE\n"
                    "    so.created_at >= DATE_SUB(CURDATE(), INTERVAL 2 YEAR)\n"
                    "AND so.status IN ('processing', 'complete', 'approved', 'aprovado_link', 'reembolso_parcial', 'closed', 'retirado')\n"
                    "AND so.state != 'canceled'\n"
                    "AND (:skip_cortesia_filter OR so.base_grand_total > 0)\n"
                    "AND (:skip_cortesia_filter OR NOT (so.discount_description LIKE '%%CORTESIA%%' AND so.base_grand_total < 50))\n"
                    "AND so.created_at < CURDATE() + INTERVAL 1 DAY\n"
                    "AND (so.discount_description IS NULL OR so.discount_description NOT LIKE '%%GRUPOS%%')\n"
                    "AND (so.coupon_code IS NULL OR so.coupon_code NOT LIKE 'GRUP%%')\n"
                    "AND so.increment_id NOT REGEXP '-[0-9]'\n"
                    "GROUP BY soi_parent.name"
                ).bindparams(
                    bindparam("fb_bundle_ids", expanding=True),
                    skip_cortesia_filter=_skip_cortesia_filter,
                )

                fb_qtd_by_name: dict = {}
                fb_rev_by_name: dict = {}

                # Fallback count — bloco independente
                try:
                    with db_module.engine_magento.connect() as conn:
                        _t_fb0 = _time.monotonic()
                        for fb_row in conn.execute(fb_count_q, {"fb_bundle_ids": fb_bundle_ids}).fetchall():
                            fb_qtd_by_name[(fb_row[0] or "").strip()] = int(fb_row[1] or 0)
                        logger.info(f"[Margem] fallback count_query: {len(fb_bundle_ids)} bundles → {len(fb_qtd_by_name)} em {_time.monotonic()-_t_fb0:.2f}s")
                except Exception as e:
                    logger.error(f"Erro no fallback count Magento para margem: {e}")
                    _log_margem_magento_failed(e, "fallback-count")

                # Fallback receita — bloco independente (com cache em memória)
                _fb_rev_cache_key = (frozenset(fb_bundle_ids), incluir_cortesias)
                _now_mono_fb = _time.monotonic()
                _cached_fb = _margem_rev_cache.get(_fb_rev_cache_key)
                if _cached_fb and (_now_mono_fb - _cached_fb[1]) < _MARGEM_REV_TTL_SECONDS:
                    fb_rev_by_name = dict(_cached_fb[0])
                    logger.info(f"[Margem] fallback revenue_query cache HIT: {len(fb_bundle_ids)} bundles → {len(fb_rev_by_name)} entradas")
                else:
                    try:
                        with db_module.engine_magento.connect() as conn:
                            _t_fb1 = _time.monotonic()
                            for fb_row in conn.execute(fb_rev_q, {"fb_bundle_ids": fb_bundle_ids}).fetchall():
                                fb_rev_by_name[(fb_row[0] or "").strip()] = float(fb_row[1] or 0)
                            _elapsed_fb = _time.monotonic() - _t_fb1
                            logger.info(f"[Margem] fallback revenue_query: {len(fb_bundle_ids)} bundles → {len(fb_rev_by_name)} em {_elapsed_fb:.2f}s")
                            _margem_rev_cache[_fb_rev_cache_key] = (dict(fb_rev_by_name), _time.monotonic())
                    except Exception as e:
                        logger.error(f"Erro no fallback receita Magento para margem: {e}")
                        _log_margem_magento_failed(e, "fallback-revenue")

                # Combina e aplica apenas onde qtd ainda é 0
                all_fb_names = set(fb_qtd_by_name.keys()) | set(fb_rev_by_name.keys())
                fb_by_name: dict = {
                    bname: {
                        "qtd": fb_qtd_by_name.get(bname, 0),
                        "receita": fb_rev_by_name.get(bname, 0.0),
                    }
                    for bname in all_fb_names
                }
                # Para cada bundle, escolhe APENAS o kit mais específico (substring mais longa)
                # entre todos os kits do kit_map. Sem isso, um bundle como "Kit Básico - 21k"
                # acaba contado tanto no kit "Kit Básico - 21k" quanto no kit genérico "Kit Básico".
                _all_kit_names_lower = [(str(kn), str(kn).lower()) for kn in kit_map.keys()]
                _bundle_to_kit: dict = {}
                for bname in fb_by_name.keys():
                    bname_lower = str(bname).lower()
                    _best_kn = None
                    _best_len = -1
                    for _kn_orig, _kn_lower in _all_kit_names_lower:
                        if _kn_lower and _kn_lower in bname_lower and len(_kn_lower) > _best_len:
                            _best_kn = _kn_orig
                            _best_len = len(_kn_lower)
                    if _best_kn is not None:
                        _bundle_to_kit[bname] = _best_kn
                for kit_name in kits_sem_venda:
                    total_qtd = 0
                    total_rec = 0.0
                    for bname, bdata in fb_by_name.items():
                        if _bundle_to_kit.get(bname) == kit_name:
                            total_qtd += bdata["qtd"]
                            total_rec += bdata["receita"]
                    if total_qtd > 0 and kit_name in kit_map:
                        kit_map[kit_name]["qtd"]     = total_qtd
                        kit_map[kit_name]["receita"] = total_rec

        # 4.5 Suplementar: bundles no Magento (via atributo cpev1) que NÃO estão no KitConfig
        # têm inscrições contadas pelo card principal mas ignoradas pelo bloco primário.
        # O fallback acima só atualiza kits_sem_venda (qtd=0), então inscrições de bundles extras
        # cujos tipos de kit já têm dados são perdidas. Este bloco as recupera e acumula.
        if seen_magento_events and global_bundle_tipo_map and db_module.engine_magento is not None:
            _kc_bid_set = set(global_bundle_tipo_map.keys())
            # Bundles deflagados explicitamente pelo usuário (linha existe no
            # KitConfig com tipo_kit=NULL) também devem ser excluídos do bloco
            # suplementar, caso contrário o matching por substring abaixo
            # reagregaria as inscrições no kit que o usuário queria desclassificar.
            _deflagged_bid_set = {
                r[0] for r in db.query(KitConfig.bundle_entity_id).filter(
                    KitConfig.tipo_kit.is_(None)
                ).all()
            }
            _supp_extra_bids: list = []
            try:
                _cpev1_supp = text("""
SELECT DISTINCT entity_id
FROM   catalog_product_entity_varchar
WHERE  attribute_id = 321
AND    store_id     = 0
AND    value        IN :ev_ids
""").bindparams(bindparam("ev_ids", expanding=True))
                with db_module.engine_magento.connect() as _csupp:
                    _supp_extra_bids = [
                        int(r[0]) for r in
                        _csupp.execute(_cpev1_supp, {"ev_ids": list(seen_magento_events)}).fetchall()
                        if int(r[0]) not in _kc_bid_set and int(r[0]) not in _deflagged_bid_set
                    ]
                if _supp_extra_bids:
                    logger.info(f"[Margem] supplementary: {len(seen_magento_events)} ev_ids → {len(_supp_extra_bids)} bundles extras fora do KitConfig")
            except Exception as _e_supp0:
                logger.warning(f"[Margem] supplementary cpev1 prefetch falhou: {_e_supp0}")

            if _supp_extra_bids:
                import time as _time_supp
                _supp_cnt_q = text(
                    "SELECT /*+ MAX_EXECUTION_TIME(30000) */\n"
                    "    soi_parent.name                        AS bundle_name,\n"
                    "    COUNT(DISTINCT soi_parent.item_id)     AS qtd\n"
                    "FROM sales_order so\n"
                    "INNER JOIN sales_order_item soi_parent\n"
                    "       ON soi_parent.order_id     = so.entity_id\n"
                    "      AND soi_parent.product_type = 'bundle'\n"
                    "      AND soi_parent.product_id   IN :supp_bids\n"
                    "WHERE\n"
                    "    so.created_at >= DATE_SUB(CURDATE(), INTERVAL 2 YEAR)\n"
                    "AND so.status IN ('processing', 'complete', 'approved', 'aprovado_link', 'reembolso_parcial', 'closed', 'retirado')\n"
                    "AND so.state != 'canceled'\n"
                    "AND (:skip_cortesia_filter OR so.base_grand_total > 0)\n"
                    "AND (:skip_cortesia_filter OR NOT (so.discount_description LIKE '%%CORTESIA%%' AND so.base_grand_total < 50))\n"
                    "AND so.created_at < CURDATE() + INTERVAL 1 DAY\n"
                    "AND (so.discount_description IS NULL OR so.discount_description NOT LIKE '%%GRUPOS%%')\n"
                    "AND (so.coupon_code IS NULL OR so.coupon_code NOT LIKE 'GRUP%%')\n"
                    "AND so.increment_id NOT REGEXP '-[0-9]'\n"
                    "GROUP BY soi_parent.name"
                ).bindparams(
                    bindparam("supp_bids", expanding=True),
                    skip_cortesia_filter=_skip_cortesia_filter,
                )

                _supp_rev_q = text(
                    "SELECT /*+ MAX_EXECUTION_TIME(55000) */\n"
                    "    soi_parent.name                                                                    AS bundle_name,\n"
                    "    ROUND(SUM(soi_child.price - soi_child.discount_amount), 2)                        AS receita_liquida\n"
                    "FROM sales_order so\n"
                    "INNER JOIN sales_order_item soi_parent\n"
                    "       ON soi_parent.order_id     = so.entity_id\n"
                    "      AND soi_parent.product_type = 'bundle'\n"
                    "      AND soi_parent.product_id   IN :supp_bids\n"
                    "INNER JOIN sales_order_item soi_child\n"
                    "       ON soi_child.parent_item_id = soi_parent.item_id\n"
                    "      AND soi_child.product_type   = 'simple'\n"
                    "      AND (:skip_cortesia_filter OR (soi_child.price > 0 AND soi_child.price - soi_child.discount_amount > 0))\n"
                    "      AND (\n"
                    "            soi_child.name LIKE '%%Distância%%'\n"
                    "         OR soi_child.name LIKE '%%Distancia%%'\n"
                    "         OR soi_child.name LIKE '%%Distâncias%%'\n"
                    "         OR soi_child.name LIKE '%%Modalidade%%'\n"
                    "      )\n"
                    "WHERE\n"
                    "    so.created_at >= DATE_SUB(CURDATE(), INTERVAL 2 YEAR)\n"
                    "AND so.status IN ('processing', 'complete', 'approved', 'aprovado_link', 'reembolso_parcial', 'closed', 'retirado')\n"
                    "AND so.state != 'canceled'\n"
                    "AND (:skip_cortesia_filter OR so.base_grand_total > 0)\n"
                    "AND (:skip_cortesia_filter OR NOT (so.discount_description LIKE '%%CORTESIA%%' AND so.base_grand_total < 50))\n"
                    "AND so.created_at < CURDATE() + INTERVAL 1 DAY\n"
                    "AND (so.discount_description IS NULL OR so.discount_description NOT LIKE '%%GRUPOS%%')\n"
                    "AND (so.coupon_code IS NULL OR so.coupon_code NOT LIKE 'GRUP%%')\n"
                    "AND so.increment_id NOT REGEXP '-[0-9]'\n"
                    "GROUP BY soi_parent.name"
                ).bindparams(
                    bindparam("supp_bids", expanding=True),
                    skip_cortesia_filter=_skip_cortesia_filter,
                )

                _supp_qtd_by_name: dict = {}
                _supp_rev_by_name: dict = {}

                try:
                    _supp_t0 = _time_supp.monotonic()
                    with db_module.engine_magento.connect() as _csupp2:
                        for _sr in _csupp2.execute(_supp_cnt_q, {"supp_bids": _supp_extra_bids}).fetchall():
                            _supp_qtd_by_name[(_sr[0] or "").strip()] = int(_sr[1] or 0)
                    logger.info(f"[Margem] supplementary count: {len(_supp_extra_bids)} bundles extras → {sum(_supp_qtd_by_name.values())} inscrições em {_time_supp.monotonic()-_supp_t0:.2f}s")
                except Exception as _e_supp1:
                    logger.warning(f"[Margem] supplementary count query falhou: {_e_supp1}")

                _supp_rev_cache_key = (frozenset(_supp_extra_bids), incluir_cortesias)
                _cached_supp = _margem_rev_cache.get(_supp_rev_cache_key)
                if _cached_supp and (_time_supp.monotonic() - _cached_supp[1]) < _MARGEM_REV_TTL_SECONDS:
                    _supp_rev_by_name = dict(_cached_supp[0])
                else:
                    try:
                        _supp_t1 = _time_supp.monotonic()
                        with db_module.engine_magento.connect() as _csupp3:
                            for _sr2 in _csupp3.execute(_supp_rev_q, {"supp_bids": _supp_extra_bids}).fetchall():
                                _supp_rev_by_name[(_sr2[0] or "").strip()] = float(_sr2[1] or 0)
                        _margem_rev_cache[_supp_rev_cache_key] = (dict(_supp_rev_by_name), _time_supp.monotonic())
                        logger.info(f"[Margem] supplementary revenue: {len(_supp_extra_bids)} bundles extras → {len(_supp_rev_by_name)} em {_time_supp.monotonic()-_supp_t1:.2f}s")
                    except Exception as _e_supp2:
                        logger.warning(f"[Margem] supplementary revenue query falhou: {_e_supp2}")

                # Ordena pelos nomes de kit MAIS LONGOS primeiro, garantindo que
                # bundles como "Kit Básico - 21k Floripa" sejam atribuídos ao kit
                # específico "Kit Básico - 21k" e não ao kit genérico "Kit Básico".
                _kit_names_sorted_supp = sorted(kit_map.keys(), key=lambda k: -len(str(k)))
                for _sname, _sqtd in _supp_qtd_by_name.items():
                    if _sqtd <= 0:
                        continue
                    _sname_lower = str(_sname).lower()
                    _srec = _supp_rev_by_name.get(_sname, 0.0)
                    _matched = False
                    for _kit_nm in _kit_names_sorted_supp:
                        if str(_kit_nm).lower() in _sname_lower:
                            kit_map[_kit_nm]["qtd"]     += _sqtd
                            kit_map[_kit_nm]["receita"] += _srec
                            logger.info(f"[Margem] supplementary: +{_sqtd} inscrições de '{_sname}' → kit '{_kit_nm}'")
                            _matched = True
                            break
                    if not _matched:
                        logger.debug(f"[Margem] supplementary: bundle '{_sname}' sem correspondência no kit_map")

        # 5. Ativo: query por ds_categoria para os event IDs mapeados como fonte=ATIVO
        #    Todos os kits verificam o Ativo; a contribuição é somada ao Magento (ou zerado se não há match).
        ativo_event_ids: list = []
        for pid in projeto_ids:
            for sm in _get_sku_maps(pid, 'ATIVO'):
                if sm.id_externo:
                    try:
                        ativo_event_ids.append(int(sm.id_externo))
                    except (ValueError, TypeError):
                        pass

        if ativo_event_ids and db_module.engine_ssh is not None:
            try:
                _ativo_ids_unique = list(set(ativo_event_ids))
                # Build exact reverse lookup: ds_categoria_lower -> kit_name
                # Priority: (1) KitConfig.ativo_categoria (admin-set), (2) exact kit name match.
                _cat_to_kit: dict = {}
                for _kn, _kd in kit_map.items():
                    _ac = (_kd.get("ativo_categoria") or "").strip()
                    if _ac:
                        # ativo_categoria explicitly configured — supports comma-separated values
                        for _ac_part in _ac.split(","):
                            _ac_part = _ac_part.strip()
                            if _ac_part:
                                _cat_to_kit[_ac_part.lower()] = _kn
                    else:
                        # No explicit mapping: exact case-insensitive kit name fallback
                        _cat_to_kit.setdefault(str(_kn).lower(), _kn)

                _ativo_query = text("""
SELECT
    sub.id_evento,
    sub.ds_categoria,
    SUM(sub.qtd)            AS qtd,
    SUM(sub.receita_liquida) AS receita_liquida
FROM (
    SELECT
        b.id_evento,
        h.ds_categoria,
        CASE
            WHEN a.nr_preco = 0                    THEN 'Cortesia'
            WHEN h.ds_categoria LIKE '%%Grup%%'    THEN 'Grupos/B2B'
            WHEN h.ds_categoria LIKE '%%ortesia%%' THEN 'Cortesia'
            ELSE                                        'Site'
        END                                            AS canal,
        COUNT(DISTINCT a.id_pedido_evento)             AS qtd,
        SUM(a.nr_preco)
            - SUM(COALESCE(a.nr_desconto_individual, 0)) AS receita_liquida
    FROM sa_evento AS b
    INNER JOIN sa_pedido_evento AS a
        ON a.id_evento = b.id_evento
    INNER JOIN sa_pedido AS c
        ON c.id_pedido = a.id_pedido
        AND c.fl_local_inscricao = '1'
        AND c.id_pedido_status IN (1, 2)
        AND c.nr_total > 0
    LEFT JOIN sa_modalidade_categoria AS h
        ON h.id_categoria = a.id_categoria
    LEFT JOIN (
        SELECT e.id_cupom_desconto_item, f.en_cupom_classificacao
        FROM sa_cupom_desconto_item AS e
        INNER JOIN sa_cupom_desconto AS f
            ON f.id_cupom_desconto = e.id_cupom_desconto
    ) AS cupom
        ON cupom.id_cupom_desconto_item = a.id_cupom_individual
    WHERE
        b.id_evento IN :ativo_ids
        AND (b.id_campanha_salesforce IS NULL
             OR b.id_campanha_salesforce NOT LIKE '701d0000000%%')
        AND c.nr_total > 0
        AND (
            cupom.en_cupom_classificacao IS NULL
            OR cupom.en_cupom_classificacao NOT IN (
                'Funcionário',
                'Cortesia Faturada',
                'Grupos',
                'Coligados',
                'Eventos Terceiros'
            )
        )
    GROUP BY
        b.id_evento,
        h.ds_categoria,
        CASE
            WHEN a.nr_preco = 0               THEN 'Cortesia'
            WHEN h.ds_categoria LIKE '%%Grup%%' THEN 'Grupos/B2B'
            ELSE                                   'Site'
        END
) AS sub
WHERE sub.canal = 'Site'
GROUP BY sub.id_evento, sub.ds_categoria
""").bindparams(bindparam("ativo_ids", expanding=True))
                with db_module.engine_ssh.connect() as _conn_ativo:
                    _ativo_result = _conn_ativo.execute(_ativo_query, {"ativo_ids": _ativo_ids_unique})
                    _ativo_rows = _ativo_result.fetchall()

                for _ar in _ativo_rows:
                    # Unpack: id_evento, ds_categoria, qtd, receita_liquida
                    _a_evento = _ar[0]
                    _a_ds_cat = (_ar[1] or "").strip()
                    _a_qtd = int(_ar[2] or 0)
                    _a_rec = float(_ar[3] or 0)
                    if _a_qtd <= 0:
                        continue
                    # Match ds_categoria to kit name — exact case-insensitive only
                    _matched_kit = _cat_to_kit.get(_a_ds_cat.lower())
                    if not _matched_kit:
                        logger.debug(f"Ativo ds_categoria '{_a_ds_cat}' sem correspondência no kit_map")
                        continue
                    if _matched_kit not in kit_map:
                        kit_map[_matched_kit] = {
                            "custo": 0.0,
                            "ativo_categoria": _a_ds_cat,
                            "qtd": 0,
                            "receita": 0.0,
                            "has_cost": False,
                        }
                    kit_map[_matched_kit]["qtd"] += _a_qtd
                    kit_map[_matched_kit]["receita"] += _a_rec
            except Exception as _e_ativo:
                logger.warning(f"Erro ao buscar dados Ativo por categoria para margem: {_e_ativo}")
                _aviso_ativo = "Dados do Ativo indisponíveis — totais de inscrições e receita podem estar incompletos."
                if avisos_out is not None and _aviso_ativo not in avisos_out:
                    avisos_out.append(_aviso_ativo)
                try:
                    from app.services.health_alert_service import log_and_alert as _log_alert_ativo
                    _first_pid_ativo = projeto_ids[0] if projeto_ids else None
                    _log_alert_ativo(
                        event_type="MARGEM_ATIVO_FAILED",
                        severity="HIGH",
                        message=f"Falha ao buscar dados Ativo na Margem por Kit (projeto_id={_first_pid_ativo}): {type(_e_ativo).__name__}",
                        detail=str(_e_ativo)[:1000],
                    )
                except Exception as _ha_err_ativo:
                    logger.warning(f"[HealthAlert] Falha ao registrar MARGEM_ATIVO_FAILED: {_ha_err_ativo}")

        # 6. Build result list — inclui kits sem vendas (qtd=0) para visibilidade de custo
        if not kit_map:
            return []

        result_list = []
        total_qtd = 0
        total_receita = 0.0
        total_margem = 0.0

        for kit_name in sorted(kit_map.keys()):
            kdata = kit_map[kit_name]
            qtd = kdata["qtd"]
            receita = kdata["receita"]
            custo = kdata["custo"]
            has_cost = kdata.get("has_cost", True)
            ticket_medio = round(receita / qtd, 2) if qtd > 0 else 0.0
            margem_unit = round(ticket_medio - custo, 2) if qtd > 0 else None
            margem_total = round(receita - (custo * qtd), 2)

            result_list.append({
                "tipoKit": kit_name,
                "qtd": qtd,
                "receitaLiquida": round(receita, 2),
                "ticketMedio": ticket_medio,
                "ticketAtual": tipo_kit_ticket_atual.get(kit_name),
                "custoKit": round(custo, 2) if has_cost else None,
                "margemUnit": margem_unit,
                "margemTotal": margem_total,
            })

            total_qtd += qtd
            total_receita += receita
            total_margem += margem_total

        if result_list:
            # Linha consolidada usa os totais do card principal quando disponíveis,
            # garantindo consistência matemática com os valores exibidos na análise de margem.
            if card_total_qty is not None and card_total_receita is not None:
                c_qtd = card_total_qty
                c_receita = round(card_total_receita, 2)
                c_ticket = round(c_receita / c_qtd, 2) if c_qtd > 0 else 0.0
                c_custo_avg = card_kit_cost_avg or 0.0
                c_margem = round(c_receita - c_custo_avg * c_qtd, 2)
            else:
                c_qtd = total_qtd
                c_receita = round(total_receita, 2)
                c_ticket = round(c_receita / c_qtd, 2) if c_qtd > 0 else 0.0
                c_margem = round(total_margem, 2)
            result_list.append({
                "tipoKit": "CONSOLIDADO",
                "qtd": c_qtd,
                "receitaLiquida": c_receita,
                "ticketMedio": c_ticket,
                "ticketAtual": None,
                "custoKit": None,
                "margemUnit": None,
                "margemTotal": c_margem,
            })

        return result_list

    except Exception as e:
        logger.exception(f"Erro ao calcular margem por kit: {e}")
        return []


def get_detalhe_vendas_por_kit(
    db: Session,
    projeto_ids: list,
    ano: Optional[int] = None,
    incluir_cortesias: bool = False,
) -> Optional[list]:
    """Breakdown detalhado de vendas Magento por kit/canal/modalidade/distância.
    Returns [] when query succeeds but no data; returns None when query fails (timeout/error).
    """
    if not projeto_ids or db_module.engine_magento is None:
        return []

    import datetime as _dt
    _ano = ano if ano else _dt.datetime.now().year

    # Coleta event IDs do Magento via SkuMapping
    proj_by_id = {
        pid: db.query(DimProjeto).filter(DimProjeto.id == pid).first()
        for pid in projeto_ids
    }
    seen_evt: set = set()
    magento_event_ids: list = []
    for pid in projeto_ids:
        proj = proj_by_id.get(pid)
        if not proj or not proj.codigo:
            continue
        sku = proj.codigo.upper().strip()
        q = db.query(SkuMapping).filter(
            SkuMapping.sku == sku,
            SkuMapping.fonte == 'MAGENTO',
            SkuMapping.ativo == True,
        )
        if ano:
            q = q.filter(SkuMapping.ano == ano)
        for sm in q.all():
            if not sm.id_externo:
                continue
            try:
                eid = int(sm.id_externo)
            except (ValueError, TypeError):
                continue
            if eid not in seen_evt:
                seen_evt.add(eid)
                magento_event_ids.append(eid)

    if not magento_event_ids:
        return []

    _cort_ids = _get_cortesia_magento_ids(db) if incluir_cortesias else None
    detalhe_query = text(build_query_isc_magento_detalhe(magento_event_ids, _ano, cortesia_magento_ids=_cort_ids))

    try:
        with db_module.engine_magento.connect() as conn:
            result = conn.execute(detalhe_query)
            rows = []
            for row in result.fetchall():
                rows.append({
                    "kit":            row[2],
                    "tipoCategoria":  row[3],
                    "distancia":      row[4],
                    "canal":          row[5],
                    "loteAtual":      row[6],
                    "price":          float(row[7]) if row[7] is not None else None,
                    "specialPrice":   float(row[8]) if row[8] is not None else None,
                    "inscritos":      int(row[9] or 0),
                    "receitaBruta":   round(float(row[10] or 0), 2),
                    "receitaLiquida": round(float(row[11] or 0), 2),
                    "ticketMedio":    round(float(row[12]), 2) if row[12] else None,
                })
            return rows if rows else []
    except Exception as e:
        logger.error(f"Erro ao buscar detalhe de vendas por kit: {e}")
        return None


def build_query_isc_magento_detalhe(magento_event_ids: list, ano: int, cortesia_magento_ids: Optional[set] = None) -> str:
    """Returns SQL for detailed Magento sales by kit/canal/modalidade (V6).

    Returns rows grouped by: id_evento, evento, kit, tipo_categoria, distancia, canal, lote_atual, price, special_price.
    Columns (by index): 0=id_evento, 1=evento, 2=kit, 3=tipoCategoria, 4=distancia, 5=canal,
                        6=loteAtual, 7=price, 8=specialPrice, 9=inscritos,
                        10=receitaBruta, 11=receitaLiquida, 12=ticketMedio.
    """
    ids_str = ", ".join(str(int(i)) for i in magento_event_ids)
    cort_ids = cortesia_magento_ids or set()
    has_cortesia = bool(cort_ids & set(str(i) for i in magento_event_ids))
    if has_cortesia:
        cort_child_price = ""
    else:
        cort_child_price = "AND soi_child.price          > 0"
    return f"""
SELECT /*+ MAX_EXECUTION_TIME(300000) */
    cpev1.value                                                                         AS id_evento,
    cpev2.value                                                                         AS evento,
    soi_parent.name                                                                     AS kit,
    eaov_tipo.value                                                                     AS tipo_categoria,
    COALESCE(soi_child.name, 'Outras modalidades')                                      AS distancia,
    CASE
        WHEN so.base_grand_total = 0                                    THEN 'Cortesia'
        WHEN soi_child.price - soi_child.discount_amount = 0           THEN 'Cortesia'
        WHEN so.discount_description LIKE '%%GRUPOS%%'                  THEN 'Grupos/B2B'
        WHEN so.coupon_code LIKE 'GRUP%%'                               THEN 'Grupos/B2B'
        ELSE                                                                 'Site'
    END                                                                                 AS canal,
    lote_atual.lot_name                                                                 AS lote_atual,
    soi_prices.price                                                                    AS price,
    soi_prices.special_price                                                            AS special_price,
    COUNT(DISTINCT soi_parent.item_id)                                                  AS inscritos,
    SUM(CASE
        WHEN so.base_grand_total = 0                                    THEN 0
        ELSE soi_child.price
    END)                                                                                AS receita_bruta,
    SUM(CASE
        WHEN so.base_grand_total = 0                                    THEN 0
        ELSE soi_child.price - soi_child.discount_amount
    END)                                                                                AS receita_liquida,
    SUM(CASE
        WHEN so.base_grand_total = 0                                    THEN 0
        ELSE soi_child.price - soi_child.discount_amount
    END) / NULLIF(COUNT(DISTINCT CASE
        WHEN so.base_grand_total = 0                                    THEN NULL
        ELSE soi_parent.item_id
    END), 0)                                                                            AS ticket_medio

FROM sales_order so

JOIN sales_order_item soi_parent
       ON soi_parent.order_id     = so.entity_id
      AND soi_parent.product_type = 'bundle'

LEFT JOIN sales_order_item soi_child
       ON soi_child.parent_item_id = soi_parent.item_id
      AND soi_child.product_type   = 'simple'
      {cort_child_price}
      AND (
            soi_child.name LIKE '%%Distância%%'
         OR soi_child.name LIKE '%%Distancia%%'
         OR soi_child.name LIKE '%%Distâncias%%'
         OR soi_child.name LIKE '%%Modalidade%%'
      )

JOIN (
    SELECT cpev.entity_id, cpev.value
    FROM catalog_product_entity_varchar cpev
    JOIN catalog_product_entity cpe
          ON cpe.entity_id = cpev.entity_id
         AND cpe.type_id   = 'bundle'
    WHERE cpev.attribute_id = 321
      AND cpev.store_id     = 0
) AS cpev1 ON cpev1.entity_id = soi_parent.product_id

LEFT JOIN (
    SELECT entity_id, MIN(value) AS value
    FROM catalog_product_entity_varchar
    WHERE attribute_id = 73
      AND store_id     = 0
    GROUP BY entity_id
) AS cpev2 ON cpev2.entity_id = cpev1.value

JOIN (
    SELECT entity_id, MIN(value) AS value
    FROM catalog_product_entity_datetime
    WHERE attribute_id = 195
    GROUP BY entity_id
) AS cped ON cped.entity_id = cpev1.value

LEFT JOIN (
    SELECT attribute_id
    FROM eav_attribute
    WHERE attribute_code = 'tipo_categoria'
      AND entity_type_id = (
            SELECT entity_type_id FROM eav_entity_type
            WHERE entity_type_code = 'catalog_product'
      )
) AS attr_tipo ON 1 = 1
LEFT JOIN catalog_product_entity_int cpei_tipo
       ON cpei_tipo.entity_id    = soi_parent.product_id
      AND cpei_tipo.attribute_id = attr_tipo.attribute_id
LEFT JOIN eav_attribute_option_value eaov_tipo
       ON eaov_tipo.option_id = cpei_tipo.value

LEFT JOIN (
    SELECT lp.entity_id, lp.lot_name
    FROM catalog_product_entity_event_lot_price lp
    JOIN (
        SELECT entity_id, MAX(record_id) AS max_record_id
        FROM catalog_product_entity_event_lot_price
        GROUP BY entity_id
    ) lp_max
          ON lp_max.entity_id     = lp.entity_id
         AND lp_max.max_record_id = lp.record_id
) AS lote_atual ON lote_atual.entity_id = cpev1.value

LEFT JOIN (
    SELECT
        cpeos.parent_product_id,
        (
            MAX(CASE
                WHEN cpev_s.value LIKE '%%Distancia%%'
                  OR cpev_s.value LIKE '%%Distância%%'
                  OR cpev_s.value LIKE '%%Modalidade%%'
                THEN cpep.value ELSE NULL
            END)
            + COALESCE(MAX(CASE
                WHEN cpep.value > 0
                 AND cpev_s.value NOT LIKE '%%Distancia%%'
                 AND cpev_s.value NOT LIKE '%%Distância%%'
                 AND cpev_s.value NOT LIKE '%%Modalidade%%'
                 AND cpev_s.value NOT LIKE '%%Personaliz%%'
                 AND cpev_s.value NOT LIKE '%%Aceite%%'
                 AND cpev_s.value NOT LIKE '%%aceito%%'
                 AND cpev_s.value NOT LIKE '%%Treinão%%'
                 AND cpev_s.value NOT LIKE '%%Horário%%'
                 AND cpev_s.value NOT LIKE '%%Bateria%%'
                 AND cpev_s.value NOT LIKE '%%Doar%%'
                 AND cpev_s.value NOT LIKE '%%Tênis%%'
                 AND cpev_s.value NOT LIKE '%%Tenis%%'
                 AND cpev_s.value NOT LIKE '%%Bike%%'
                 AND cpev_s.value NOT LIKE '%%Biciclet%%'
                 AND cpev_s.value NOT LIKE '%%Festival%%'
                 AND cpev_s.value NOT LIKE '%%Bag%%'
                 AND cpev_s.value NOT LIKE '%%Inscrição%%'
                 AND cpev_s.value NOT LIKE '%%Declaro%%'
                 AND cpev_s.value NOT LIKE '%%Pochete%%'
                 AND cpev_s.value NOT LIKE '%%Tarifa%%'
                 AND cpev_s.value NOT LIKE '%%Skate%%'
                 AND cpev_s.value NOT LIKE '%%Obstáculo%%'
                 AND cpev_s.value NOT LIKE '%%Bravinhos%%'
                 AND cpev_s.value NOT LIKE '%%teste%%'
                 AND cpev_s.value NOT LIKE '%%Porta%%'
                 AND cpev_s.value NOT LIKE '%%Luva%%'
                 AND cpev_s.value NOT LIKE '%%Toalha%%'
                 AND cpev_s.value NOT LIKE '%%Corrida +%%'
                THEN cpep.value ELSE NULL
            END), 0)
        ) * COALESCE(mult.multiplicador, 1)             AS price,
        (
            MAX(CASE
                WHEN cpev_s.value LIKE '%%Distancia%%'
                  OR cpev_s.value LIKE '%%Distância%%'
                  OR cpev_s.value LIKE '%%Modalidade%%'
                THEN pi.final_price ELSE NULL
            END)
            + COALESCE(MAX(CASE
                WHEN pi.final_price > 0
                 AND cpev_s.value NOT LIKE '%%Distancia%%'
                 AND cpev_s.value NOT LIKE '%%Distância%%'
                 AND cpev_s.value NOT LIKE '%%Modalidade%%'
                 AND cpev_s.value NOT LIKE '%%Personaliz%%'
                 AND cpev_s.value NOT LIKE '%%Aceite%%'
                 AND cpev_s.value NOT LIKE '%%aceito%%'
                 AND cpev_s.value NOT LIKE '%%Treinão%%'
                 AND cpev_s.value NOT LIKE '%%Horário%%'
                 AND cpev_s.value NOT LIKE '%%Bateria%%'
                 AND cpev_s.value NOT LIKE '%%Doar%%'
                 AND cpev_s.value NOT LIKE '%%Tênis%%'
                 AND cpev_s.value NOT LIKE '%%Tenis%%'
                 AND cpev_s.value NOT LIKE '%%Bike%%'
                 AND cpev_s.value NOT LIKE '%%Biciclet%%'
                 AND cpev_s.value NOT LIKE '%%Festival%%'
                 AND cpev_s.value NOT LIKE '%%Bag%%'
                 AND cpev_s.value NOT LIKE '%%Inscrição%%'
                 AND cpev_s.value NOT LIKE '%%Declaro%%'
                 AND cpev_s.value NOT LIKE '%%Pochete%%'
                 AND cpev_s.value NOT LIKE '%%Tarifa%%'
                 AND cpev_s.value NOT LIKE '%%Skate%%'
                 AND cpev_s.value NOT LIKE '%%Obstáculo%%'
                 AND cpev_s.value NOT LIKE '%%Bravinhos%%'
                 AND cpev_s.value NOT LIKE '%%teste%%'
                 AND cpev_s.value NOT LIKE '%%Porta%%'
                 AND cpev_s.value NOT LIKE '%%Luva%%'
                 AND cpev_s.value NOT LIKE '%%Toalha%%'
                 AND cpev_s.value NOT LIKE '%%Corrida +%%'
                THEN pi.final_price ELSE NULL
            END), 0)
        ) * COALESCE(mult.multiplicador, 1)             AS special_price

    FROM catalog_product_bundle_selection cpeos
    JOIN catalog_product_bundle_option cpeo
          ON cpeo.option_id = cpeos.option_id
    LEFT JOIN catalog_product_entity_varchar cpev_s
          ON cpev_s.entity_id    = cpeos.product_id
         AND cpev_s.attribute_id = 73
         AND cpev_s.store_id     = 0
    LEFT JOIN catalog_product_entity_decimal cpep
          ON cpep.entity_id    = cpeos.product_id
         AND cpep.attribute_id = 77
    LEFT JOIN catalog_product_index_price pi
          ON pi.entity_id         = cpeos.product_id
         AND pi.website_id        = 1
         AND pi.customer_group_id = 0
    LEFT JOIN (
        SELECT
            cpe.entity_id,
            CASE cpei.value
                WHEN 1606 THEN 2 WHEN 1607 THEN 3 WHEN 1608 THEN 4
                WHEN 1609 THEN 2 WHEN 1700 THEN 2 WHEN 1701 THEN 4
                ELSE 1
            END                                         AS multiplicador
        FROM catalog_product_entity cpe
        JOIN catalog_product_entity_int cpei
              ON cpei.entity_id    = cpe.entity_id
             AND cpei.attribute_id = (
                    SELECT attribute_id FROM eav_attribute
                    WHERE attribute_code = 'tipo_categoria'
                      AND entity_type_id = (
                            SELECT entity_type_id FROM eav_entity_type
                            WHERE entity_type_code = 'catalog_product'
                      )
             )
        WHERE cpe.type_id = 'bundle'
    ) AS mult ON mult.entity_id = cpeo.parent_id
    GROUP BY cpeos.parent_product_id
) AS soi_prices ON soi_prices.parent_product_id = soi_parent.product_id

WHERE so.status IN ('processing', 'complete', 'approved', 'aprovado_link', 'reembolso_parcial', 'closed', 'retirado')
  AND so.state NOT IN ('canceled')
  AND so.increment_id   NOT REGEXP '-[0-9]'
  AND cpev1.value IN ({ids_str})
  AND cped.value >= MAKEDATE({ano}, 1)
  AND cped.value <  MAKEDATE({ano + 1}, 1)

GROUP BY
    cpev1.value,
    cpev2.value,
    soi_parent.name,
    eaov_tipo.value,
    COALESCE(soi_child.name, 'Outras modalidades'),
    CASE
        WHEN so.base_grand_total = 0                                    THEN 'Cortesia'
        WHEN soi_child.price - soi_child.discount_amount = 0           THEN 'Cortesia'
        WHEN so.discount_description LIKE '%%GRUPOS%%'                  THEN 'Grupos/B2B'
        WHEN so.coupon_code LIKE 'GRUP%%'                               THEN 'Grupos/B2B'
        ELSE                                                                 'Site'
    END,
    lote_atual.lot_name,
    soi_prices.price,
    soi_prices.special_price

ORDER BY
    cpev1.value,
    canal,
    inscritos DESC
"""


def build_query_isc_ativo_detalhe(ativo_event_ids: list, ano: int) -> str:
    """Returns SQL for detailed Ativo sales by modalidade/categoria/canal (CORAÇÃO EVENTO).

    Returns rows grouped by: id_evento, ds_evento, distancia, kit (categoria), canal.
    Columns: id_evento, evento, distancia, kit, canal, inscritos, receitaBruta, receitaLiquida, ticketMedio.
    """
    ids_str = ", ".join(str(int(i)) for i in ativo_event_ids)
    return f"""
SELECT /*+ MAX_EXECUTION_TIME(60000) */
    b.id_evento                                                                     AS id_evento,
    b.ds_evento                                                                     AS evento,
    m.ds_modalidade                                                                 AS distancia,
    h.ds_categoria                                                                  AS kit,
    CASE
        WHEN a.nr_preco = 0                                                                             THEN 'Cortesia'
        WHEN cupom.en_cupom_classificacao IN ('Funcionário', 'Cortesia Faturada', 'Coligados', 'Eventos Terceiros') THEN 'Cortesia'
        WHEN cupom.en_cupom_classificacao = 'Grupos'                                                    THEN 'Grupos/B2B'
        WHEN h.ds_categoria LIKE '%%Grup%%'                                                             THEN 'Grupos/B2B'
        ELSE                                                                                                  'Site'
    END                                                                             AS canal,
    COUNT(DISTINCT a.id_pedido_evento)                                              AS inscritos,
    SUM(a.nr_preco)                                                                 AS receita_bruta,
    SUM(a.nr_preco) - SUM(COALESCE(a.nr_desconto_individual, 0))                    AS receita_liquida,
    (SUM(a.nr_preco) - SUM(COALESCE(a.nr_desconto_individual, 0)))
        / NULLIF(COUNT(DISTINCT a.id_pedido_evento), 0)                             AS ticket_medio
FROM sa_evento AS b
INNER JOIN sa_pedido_evento AS a ON a.id_evento = b.id_evento
INNER JOIN sa_pedido AS c
    ON c.id_pedido = a.id_pedido
   AND c.fl_local_inscricao = '1'
   AND c.id_pedido_status IN (1, 2)
   AND c.nr_total > 0
LEFT JOIN sa_modalidade_categoria AS h ON h.id_categoria = a.id_categoria
LEFT JOIN sa_evento_modalidade AS m ON m.id_modalidade = a.id_modalidade AND m.id_evento = b.id_evento
LEFT JOIN (
    SELECT e.id_cupom_desconto_item, f.en_cupom_classificacao
    FROM sa_cupom_desconto_item AS e
    INNER JOIN sa_cupom_desconto AS f ON f.id_cupom_desconto = e.id_cupom_desconto
) AS cupom ON cupom.id_cupom_desconto_item = a.id_cupom_individual
WHERE b.id_evento IN ({ids_str})
  AND (b.id_campanha_salesforce IS NULL OR b.id_campanha_salesforce NOT LIKE '701d0000000%%')
  AND c.nr_total > 0
GROUP BY
    b.id_evento,
    b.ds_evento,
    m.id_modalidade,
    m.ds_modalidade,
    h.id_categoria,
    h.ds_categoria,
    CASE
        WHEN a.nr_preco = 0                                                                             THEN 'Cortesia'
        WHEN cupom.en_cupom_classificacao IN ('Funcionário', 'Cortesia Faturada', 'Coligados', 'Eventos Terceiros') THEN 'Cortesia'
        WHEN cupom.en_cupom_classificacao = 'Grupos'                                                    THEN 'Grupos/B2B'
        WHEN h.ds_categoria LIKE '%%Grup%%'                                                             THEN 'Grupos/B2B'
        ELSE                                                                                                  'Site'
    END
ORDER BY b.id_evento, canal, inscritos DESC
"""


def get_detalhe_vendas_ativo(
    db: Session,
    projeto_ids: list,
    ano: Optional[int] = None,
) -> list:
    """Breakdown detalhado de vendas Ativo por modalidade/categoria/canal (CORAÇÃO EVENTO)."""
    if not projeto_ids or db_module.engine_ssh is None:
        return []

    import datetime as _dt
    _ano = ano if ano else _dt.datetime.now().year

    seen_evt: set = set()
    ativo_event_ids: list = []
    for pid in projeto_ids:
        proj = db.query(DimProjeto).filter(DimProjeto.id == pid).first()
        if not proj or not proj.codigo:
            continue
        sku = proj.codigo.upper().strip()
        q = db.query(SkuMapping).filter(
            SkuMapping.sku == sku,
            SkuMapping.fonte == 'ATIVO',
            SkuMapping.ativo == True,
        )
        if ano:
            q = q.filter(SkuMapping.ano == ano)
        for sm in q.all():
            if not sm.id_externo:
                continue
            try:
                eid = int(sm.id_externo)
            except (ValueError, TypeError):
                continue
            if eid not in seen_evt:
                seen_evt.add(eid)
                ativo_event_ids.append(eid)

    if not ativo_event_ids:
        return []

    try:
        sql = text(build_query_isc_ativo_detalhe(ativo_event_ids, _ano))
        with db_module.engine_ssh.connect() as conn:
            result = conn.execute(sql)
            rows = []
            for row in result.fetchall():
                rows.append({
                    "kit":            row[3],
                    "tipoCategoria":  None,
                    "distancia":      row[2],
                    "canal":          row[4],
                    "loteAtual":      None,
                    "price":          None,
                    "specialPrice":   None,
                    "inscritos":      int(row[5] or 0),
                    "receitaBruta":   round(float(row[6] or 0), 2),
                    "receitaLiquida": round(float(row[7] or 0), 2),
                    "ticketMedio":    round(float(row[8]), 2) if row[8] else None,
                    "banco":          "Ativo",
                })
            return rows if rows else []
    except Exception as e:
        logger.error(f"Erro ao buscar detalhe de vendas Ativo: {e}")
        return []


_isc_cache = {}
_isc_cache_timestamp = None

from ...core.cache import isc_cache as _smart_isc_cache, event_detail_cache, daily_sales_cache, curva_cache, medias_cache, eventos_list_cache, CURRENT_YEAR_TTL

# Global set to track cache keys currently being refreshed in a SWR background thread.
# Prevents multiple concurrent threads for the same event when the recompute takes >16s
# and several requests arrive before the first thread finishes.
_swr_recompute_in_progress: set = set()

# Concurrent computation guard: prevents cache stampede when multiple requests hit
# the same uncached event simultaneously. Only one thread computes; others wait.
import threading as _threading_module
_event_computing_events: dict = {}   # cache_key -> threading.Event (set when done)
_event_computing_lock = _threading_module.Lock()

# Bump this when ISC calculation logic changes so old permanent cache entries
# are automatically detected as stale and recomputed in background (SWR pattern).
_DETAIL_CACHE_VERSION = "13"  # v13: margem por kit seed só do KitConfig; Cadastro é fallback de custo

def build_query_isc_ativo(excluded_ids: Optional[list] = None) -> str:
    excl_clause = ""
    if excluded_ids:
        ids_str = ", ".join(str(int(i)) for i in excluded_ids)
        excl_clause = f"        AND b.id_evento NOT IN ({ids_str})\n"
    return f"""
SELECT
    base.id_evento                                                           AS "ID Evento",
    base.ds_evento                                                           AS "Evento",
    base.qtd_site                                                            AS "Qtd Site",
    base.inscricao_liquida                                                   AS "Inscrição Líquida Site",
    base.inscricao_liquida / NULLIF(base.qtd_site, 0)                       AS "Ticket Médio Site",
    ROUND(base.qtd_30d / 30.0, 2)                                           AS "Média Diária 30d",
    ROUND(base.qtd_14d / 14.0, 2)                                           AS "Média Diária 14d",
    ROUND(base.qtd_7d  /  7.0, 2)                                           AS "Média Diária 7d"
FROM (
    SELECT
        b.id_evento,
        b.ds_evento,
        b.dt_evento,
        SUM(CASE
            WHEN a.nr_preco > 0
             AND (h.ds_categoria IS NULL OR h.ds_categoria NOT LIKE '%%GRUPOS%%')
            THEN 1 ELSE 0
        END)                                                                 AS qtd_site,

        SUM(CASE
            WHEN a.nr_preco > 0
             AND (h.ds_categoria IS NULL OR h.ds_categoria NOT LIKE '%%GRUPOS%%')
             AND c.dt_pedido >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
            THEN 1 ELSE 0
        END)                                                                 AS qtd_30d,

        SUM(CASE
            WHEN a.nr_preco > 0
             AND (h.ds_categoria IS NULL OR h.ds_categoria NOT LIKE '%%GRUPOS%%')
             AND c.dt_pedido >= DATE_SUB(CURDATE(), INTERVAL 14 DAY)
            THEN 1 ELSE 0
        END)                                                                 AS qtd_14d,

        SUM(CASE
            WHEN a.nr_preco > 0
             AND (h.ds_categoria IS NULL OR h.ds_categoria NOT LIKE '%%GRUPOS%%')
             AND c.dt_pedido >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)
            THEN 1 ELSE 0
        END)                                                                 AS qtd_7d,

        SUM(CASE
            WHEN a.nr_preco > 0
             AND (h.ds_categoria IS NULL OR h.ds_categoria NOT LIKE '%%GRUPOS%%')
            THEN
                GREATEST(0, a.nr_preco - COALESCE(a.nr_desconto_individual, 0))
            ELSE 0
        END)                                                                 AS inscricao_liquida

    FROM sa_evento AS b

    INNER JOIN sa_pedido_evento AS a
        ON a.id_evento = b.id_evento

    INNER JOIN sa_pedido AS c
        ON c.id_pedido = a.id_pedido
       AND c.fl_local_inscricao = '1'
       AND c.id_pedido_status IN (1, 2)
       AND c.nr_total > 0

    LEFT JOIN sa_modalidade_categoria AS h
        ON h.id_categoria = a.id_categoria

    LEFT JOIN (
        SELECT e.id_cupom_desconto_item, f.en_cupom_classificacao
        FROM sa_cupom_desconto_item AS e
        INNER JOIN sa_cupom_desconto AS f
            ON f.id_cupom_desconto = e.id_cupom_desconto
    ) AS cupom ON cupom.id_cupom_desconto_item = a.id_cupom_individual

    WHERE
        b.dt_evento >= MAKEDATE(YEAR(CURDATE()) - 1, 1)
        AND b.dt_evento <  MAKEDATE(YEAR(CURDATE()) + 1, 1)
        AND c.nr_total > 0
{excl_clause}
        AND (b.id_campanha_salesforce IS NULL
             OR b.id_campanha_salesforce NOT LIKE '701d0000000%%')

        AND (cupom.en_cupom_classificacao IS NULL
             OR cupom.en_cupom_classificacao NOT IN (
                 'Funcionário', 'Cortesia Faturada', 'Grupos', 'Coligados', 'Eventos Terceiros'
             ))

    GROUP BY
        b.id_evento,
        b.ds_evento,
        b.dt_evento
) AS base
ORDER BY base.id_evento;
"""


def build_query_isc_magento(excluded_ids: Optional[list] = None, cortesia_magento_ids: Optional[set] = None) -> str:
    excl_clause = ""
    if excluded_ids:
        ids_str = ", ".join(str(i) for i in excluded_ids)
        excl_clause = f"AND cpev1.value NOT IN ({ids_str})\n"
    cort_ids = cortesia_magento_ids or set()
    if cort_ids:
        safe_cort_ids = [str(int(i)) for i in cort_ids if str(i).isdigit()]
        cort_str = ", ".join(safe_cort_ids)
        cort_child_price = f"AND (cpev1.value IN ({cort_str}) OR soi_child.price > 0)"
        cort_grand_total = f"AND (cpev1.value IN ({cort_str}) OR so.base_grand_total > 0)"
        cort_cortesia_desc = f"AND (cpev1.value IN ({cort_str}) OR NOT (so.discount_description LIKE '%%CORTESIA%%' AND so.base_grand_total < 50))"
    else:
        cort_child_price = "AND soi_child.price > 0"
        cort_grand_total = "AND so.base_grand_total > 0"
        cort_cortesia_desc = "AND NOT (so.discount_description LIKE '%%CORTESIA%%' AND so.base_grand_total < 50)"
    return f"""
SELECT /*+ MAX_EXECUTION_TIME(300000) */
    cpev1.value                                                              AS "ID Evento",
    cpev2.value                                                              AS "Evento",

    COUNT(DISTINCT soi_parent.item_id)                                       AS "Qtd Site",

    ROUND(SUM(soi_child.price - soi_child.discount_amount), 2)              AS "Inscrição Líquida",

    ROUND(SUM(soi_child.price - soi_child.discount_amount)
          / NULLIF(COUNT(DISTINCT soi_parent.item_id), 0), 2)               AS "Ticket Médio",

    ROUND(COUNT(DISTINCT CASE
        WHEN so.created_at >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
        THEN soi_parent.item_id END) / 30.0, 2)                             AS "Média Diária 30d",

    ROUND(COUNT(DISTINCT CASE
        WHEN so.created_at >= DATE_SUB(CURDATE(), INTERVAL 14 DAY)
        THEN soi_parent.item_id END) / 14.0, 2)                             AS "Média Diária 14d",

    ROUND(COUNT(DISTINCT CASE
        WHEN so.created_at >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)
        THEN soi_parent.item_id END) / 7.0, 2)                              AS "Média Diária 7d"

FROM sales_order so
INNER JOIN sales_order_item soi_parent
       ON soi_parent.order_id     = so.entity_id
      AND soi_parent.product_type = 'bundle'
INNER JOIN sales_order_item soi_child
       ON soi_child.parent_item_id = soi_parent.item_id
      AND soi_child.product_type   = 'simple'
      AND (
            soi_child.name LIKE '%%Distância%%'
         OR soi_child.name LIKE '%%Distancia%%'
         OR soi_child.name LIKE '%%Distâncias%%'
         OR soi_child.name LIKE '%%Modalidade%%'
      )
INNER JOIN (
    SELECT entity_id, value
    FROM catalog_product_entity_varchar
    WHERE attribute_id = 321 AND store_id = 0
) AS cpev1 ON cpev1.entity_id = soi_parent.product_id
INNER JOIN (
    SELECT entity_id, MIN(value) AS value
    FROM catalog_product_entity_datetime
    WHERE attribute_id = 195
    GROUP BY entity_id
) AS cped ON cped.entity_id = cpev1.value
LEFT JOIN (
    SELECT entity_id, value
    FROM catalog_product_entity_varchar
    WHERE attribute_id = 73 AND store_id = 0
) AS cpev2 ON cpev2.entity_id = cpev1.value
WHERE
    so.status IN ('processing', 'complete', 'approved', 'aprovado_link', 'reembolso_parcial', 'closed', 'retirado')
AND so.state != 'canceled'
{cort_child_price}
{cort_grand_total}
{cort_cortesia_desc}
AND so.created_at < CURDATE() + INTERVAL 1 DAY
AND (so.discount_description IS NULL OR so.discount_description NOT LIKE '%%GRUPOS%%')
AND (so.coupon_code IS NULL OR so.coupon_code NOT LIKE 'GRUP%%')
AND so.increment_id NOT REGEXP '-[0-9]'
AND cped.value BETWEEN MAKEDATE(YEAR(CURDATE()) - 1, 1) AND MAKEDATE(YEAR(CURDATE()) + 1, 1) - INTERVAL 1 DAY
{excl_clause}
GROUP BY
    cpev1.value,
    cpev2.value

ORDER BY
    cpev1.value;
"""


def _parse_isc_row(row) -> dict:
    return {
        "id_evento": str(row[0]) if row[0] else None,
        "evento": str(row[1]) if row[1] else None,
        "qtd_site": int(row[2]) if row[2] else 0,
        "inscricao_liquida": float(row[3]) if row[3] else 0.0,
        "ticket_medio": float(row[4]) if row[4] else 0.0,
        "media_30d": float(row[5]) if row[5] else 0.0,
        "media_14d": float(row[6]) if row[6] else 0.0,
        "media_7d": float(row[7]) if row[7] else 0.0,
        "dias_ate_evento": 0,
        "fator_aceleracao": 0.0,
        "projecao_linear": 0.0,
        "projecao_ajustada": 0.0,
        "tendencia": "Sem histórico comparativo",
    }


def _fetch_with_retry(engine, query_builder, source_name, max_retries=1):
    import time as _time
    if engine is None:
        return {"error": f"Conexão {source_name} não configurada"}
    last_error = None
    for attempt in range(max_retries + 1):
        try:
            start = _time.time()
            query = query_builder()
            with engine.connect() as conn:
                result = conn.execute(text(query))
                rows = result.fetchall()
            elapsed = round(_time.time() - start, 2)
            logger.info(f"ISC {source_name}: {len(rows)} registros em {elapsed}s (tentativa {attempt + 1})")
            return [_parse_isc_row(row) for row in rows]
        except Exception as e:
            last_error = e
            elapsed = round(_time.time() - start, 2)
            logger.warning(f"ISC {source_name} falhou em {elapsed}s (tentativa {attempt + 1}/{max_retries + 1}): {type(e).__name__}: {e}")
            if attempt < max_retries:
                _time.sleep(2 * (attempt + 1))
    logger.error(f"ISC {source_name} falhou após {max_retries + 1} tentativas: {last_error}")
    return {"error": f"Timeout ou erro de conexão ({type(last_error).__name__})"}


def fetch_isc_data_ativo():
    return _fetch_with_retry(db_module.engine_ssh, build_query_isc_ativo, "Ativo")


def fetch_isc_data_magento(cortesia_magento_ids: Optional[set] = None):
    return _fetch_with_retry(db_module.engine_magento, lambda: build_query_isc_magento(cortesia_magento_ids=cortesia_magento_ids), "Magento")


_isc_warnings = []


def fetch_isc_pricing_data(db: Optional[Session] = None, force_refresh: bool = False) -> dict:
    """
    Reads ISC totals and rolling averages from vendas_diaria_snapshot (PostgreSQL).
    No MySQL queries in the read path — data comes from the background auto-sync.
    """
    global _isc_cache, _isc_cache_timestamp, _isc_warnings
    import time

    current_year = datetime.now().year
    smart_cache_key = f"{current_year}_isc"

    if not force_refresh:
        # stale_ok=False: once TTL (5 min) expires, force a fresh PostgreSQL read.
        # This is safe because get_isc_totals_from_snapshot is <5ms — no need for stale data.
        cached = _smart_isc_cache.get(smart_cache_key, stale_ok=False)
        if cached is not None:
            cache_info = _smart_isc_cache.get_info(smart_cache_key)
            logger.info(f"ISC cache HIT: key={smart_cache_key}, age={cache_info.get('age_seconds', '?')}s")
            return cached
        else:
            logger.info(f"ISC cache MISS: key={smart_cache_key}")
    else:
        logger.info(f"ISC cache BYPASS (force_refresh): key={smart_cache_key}")

    current_time = time.time()
    warnings = []

    # ---------------------------------------------------------------------------
    # STEP 1: Build grupo→SKU map and classify events by regime.
    #   consolidated_grupos: set of grupo names where regime == "consolidated"
    #   _isc_grupo_latest:    {grupo: latest event date (for dias_ate_evento)}
    #   consolidated_grupo_skus: {grupo: [normalized SKU strings]}
    # ---------------------------------------------------------------------------
    consolidated_grupos: set = set()
    consolidated_grupo_skus: dict = {}     # {grupo: [sku_norm, ...]}
    _isc_grupo_latest: dict = {}           # {grupo: latest event date}

    if db:
        try:
            from ...models.dimensoes import SkuMapping as _ISC_SM
            _isc_grupo_rows = db.query(
                _ISC_SM.evento_grupo, _ISC_SM.sku, _ISC_SM.data_evento,
            ).filter(
                _ISC_SM.evento_grupo != None,
                _ISC_SM.ativo == True,
                _ISC_SM.ano == current_year
            ).all()

            for _isc_row in _isc_grupo_rows:
                _gn = _isc_row.evento_grupo
                if not _gn:
                    continue
                if _isc_row.data_evento and (
                    _gn not in _isc_grupo_latest
                    or _isc_row.data_evento > _isc_grupo_latest[_gn]
                ):
                    _isc_grupo_latest[_gn] = _isc_row.data_evento
                if _gn not in consolidated_grupo_skus:
                    consolidated_grupo_skus[_gn] = []
                if _isc_row.sku:
                    _sn = normalize_sku(_isc_row.sku)
                    if _sn and _sn not in consolidated_grupo_skus[_gn]:
                        consolidated_grupo_skus[_gn].append(_sn)

            # Resolve missing event dates from dim_projeto using fuzzy-match
            # so regime classification works without manual date entry in SKU mappings.
            _grupos_sem_data = set(consolidated_grupo_skus.keys()) - set(_isc_grupo_latest.keys())
            if _grupos_sem_data:
                try:
                    _dp_all = _wq_all_dim_projetos(db)
                    _dp_yr = [p for p in _dp_all if p.data_evento and p.data_evento.year == current_year]
                    for _gn_nd in _grupos_sem_data:
                        _norm_gn = _normalize_name_for_match(_gn_nd)
                        _best_sc, _best_dt = 0.0, None
                        for _p in _dp_yr:
                            _pn = _normalize_name_for_match(_p.evento or "")
                            _gw = set(_norm_gn.split())
                            _pw = set(_pn.split())
                            if not _gw or not _pw:
                                continue
                            _sc = len(_gw & _pw) / max(len(_gw), len(_pw))
                            if _sc > _best_sc:
                                _best_sc = _sc
                                _best_dt = _p.data_evento
                        if _best_dt and _best_sc >= 0.5:
                            _isc_grupo_latest[_gn_nd] = _best_dt
                except Exception as _date_err:
                    logger.warning(f"[ISC] failed to resolve dates from dim_projeto: {_date_err}")

            # Classify by regime
            _live_count = 0
            for _gn, _evt_date in _isc_grupo_latest.items():
                _rc = _evt_date - timedelta(days=2)
                _raw_dm = (_rc - today_brazil()).days
                _regime = get_event_regime(_raw_dm)
                if _regime == "consolidated":
                    consolidated_grupos.add(_gn)
                else:
                    _live_count += 1

            logger.info(
                f"[ISC] Regime: {len(consolidated_grupos)} consolidated, "
                f"{_live_count} live/hybrid (total: {len(consolidated_grupo_skus)} grupos)"
            )
        except Exception as _cls_err:
            logger.warning(f"[ISC] Regime classification failed: {_cls_err}")

    # ---------------------------------------------------------------------------
    # STEP 2: Read ALL grupo metrics from PostgreSQL snapshot table (<5ms).
    # This replaces the previous MySQL Ativo + Magento queries entirely.
    # If a grupo has no snapshot rows, it gets zeros with a warning — the
    # background auto-sync will populate it within the next 30-min cycle.
    # ---------------------------------------------------------------------------
    snapshot_totals: dict = {}
    if db:
        try:
            from ...services.snapshot_service import get_isc_totals_from_snapshot
            snapshot_totals = get_isc_totals_from_snapshot(db, current_year)
            # Coverage check: warn about active grupos not yet in snapshot so ops team can
            # trigger a manual sync or verify SkuMapping completeness.
            mapped_grupos = set(consolidated_grupo_skus.keys())
            covered_grupos = set(snapshot_totals.keys())
            uncovered = mapped_grupos - covered_grupos
            if uncovered:
                logger.warning(
                    f"[ISC] {len(uncovered)}/{len(mapped_grupos)} grupos sem dados no snapshot "
                    f"(auto-sync não rodou ou sem vendas em {current_year}): {sorted(uncovered)}"
                )
            logger.info(
                f"[ISC] PostgreSQL snapshot: {len(snapshot_totals)} grupos com dados, "
                f"{len(mapped_grupos) - len(uncovered)}/{len(mapped_grupos)} mapeados cobertos"
            )
        except Exception as e:
            logger.error(f"[ISC] Erro ao ler snapshot PostgreSQL: {e}")
            warnings.append("⚠️ Erro ao ler dados do PostgreSQL. Dashboard pode exibir valores desatualizados.")

    # ---------------------------------------------------------------------------
    # STEP 3: Build all_data keyed by normalized SKU (same format as before).
    # Live/hybrid grupos get full metrics + projection math.
    # Consolidated grupos get snapshot totals with _regime='consolidated'.
    # ---------------------------------------------------------------------------
    all_data: dict = {}
    consolidated_totals: dict = {}   # {grupo: snap_metrics} — kept in output for callers

    for _gn, _skus in consolidated_grupo_skus.items():
        is_consolidated = _gn in consolidated_grupos
        snap = snapshot_totals.get(_gn)

        if not snap:
            if not is_consolidated:
                logger.warning(
                    f"[ISC] Grupo '{_gn}' sem dados no snapshot — "
                    f"auto-sync ainda não rodou ou grupo sem vendas no ano {current_year}"
                )
            snap = {
                "qtd_site": 0, "receita_liquida_site": 0.0, "inscricao_liquida": 0.0,
                "ticket_medio": 0.0, "media_7d": 0.0, "media_14d": 0.0, "media_30d": 0.0,
            }

        _evt_date = _isc_grupo_latest.get(_gn)
        dias_ate_evento = (_evt_date - today_brazil()).days if _evt_date else 0

        for _i, _sn in enumerate(_skus):
            if not _sn:
                continue
            if is_consolidated:
                all_data[_sn] = {
                    'qtd_site':            snap['qtd_site'] if _i == 0 else 0,
                    'inscricao_liquida':   snap['inscricao_liquida'] if _i == 0 else 0.0,
                    'media_30d': 0.0, 'media_14d': 0.0, 'media_7d': 0.0,
                    'dias_ate_evento': 0,
                    'evento_name':         _gn,
                    'ticket_medio':        snap.get('ticket_medio', 0.0) if _i == 0 else 0.0,
                    'fator_aceleracao':    0.0,
                    'projecao_linear':     snap['qtd_site'] if _i == 0 else 0,
                    'projecao_ajustada':   snap['qtd_site'] if _i == 0 else 0,
                    'projecao_final':      snap['qtd_site'] if _i == 0 else 0,
                    'tendencia':           'Consolidado',
                    'receita_liquida_site': snap['receita_liquida_site'] if _i == 0 else 0.0,
                    '_regime':             'consolidated',
                }
                if _i == 0:
                    consolidated_totals[_gn] = snap
            else:
                if _i == 0:
                    all_data[_sn] = {
                        'qtd_site':            snap['qtd_site'],
                        'inscricao_liquida':   snap['inscricao_liquida'],
                        'media_30d':           snap['media_30d'],
                        'media_14d':           snap['media_14d'],
                        'media_7d':            snap['media_7d'],
                        'dias_ate_evento':     dias_ate_evento,
                        'evento_name':         _gn,
                        'ticket_medio':        0.0,
                        'fator_aceleracao':    0.0,
                        'projecao_linear':     0.0,
                        'projecao_ajustada':   0.0,
                        'projecao_final':      0.0,
                        'tendencia':           'Sem histórico comparativo',
                        'receita_liquida_site': snap['receita_liquida_site'],
                    }
                else:
                    all_data[_sn] = {
                        'qtd_site': 0, 'inscricao_liquida': 0.0,
                        'media_30d': 0.0, 'media_14d': 0.0, 'media_7d': 0.0,
                        'dias_ate_evento': 0, 'evento_name': _gn,
                        'ticket_medio': 0.0, 'fator_aceleracao': 0.0,
                        'projecao_linear': 0.0, 'projecao_ajustada': 0.0,
                        'projecao_final': 0.0, 'tendencia': 'Sem histórico comparativo',
                        'receita_liquida_site': 0.0,
                    }

    # STEP 4: Compute projection metrics for live/hybrid events (same math as before).
    for sku, data in all_data.items():
        if data.get('_regime') == 'consolidated':
            continue
        qtd_site  = data['qtd_site']
        dias      = max(data['dias_ate_evento'], 0)
        media_14d = data['media_14d']
        media_7d  = data['media_7d']

        qtd_7d          = media_7d  * 7.0
        qtd_7d_anterior = media_14d * 14.0 - qtd_7d

        data['ticket_medio']        = round(data['inscricao_liquida'] / qtd_site, 2) if qtd_site > 0 else 0.0
        data['receita_liquida_site'] = data['inscricao_liquida']

        data['fator_aceleracao'] = round(qtd_7d / qtd_7d_anterior, 2) if qtd_7d_anterior > 0 else 0.0
        data['projecao_linear']  = round(qtd_site + media_14d * dias, 0)

        fator_clamped           = min(max(data['fator_aceleracao'] if data['fator_aceleracao'] > 0 else 1.0, 0.3), 2.5)
        data['projecao_ajustada'] = round(qtd_site + media_14d * fator_clamped * dias, 0)
        data['projecao_final']    = data['projecao_linear']

        if qtd_7d_anterior <= 0:
            data['tendencia'] = 'Sem histórico comparativo'
        elif data['fator_aceleracao'] >= 1.15:
            data['tendencia'] = 'Acelerando'
        elif data['fator_aceleracao'] >= 0.85:
            data['tendencia'] = 'Estável'
        else:
            data['tendencia'] = 'Desacelerando'

    all_data['_consolidated_totals'] = consolidated_totals

    if not warnings:
        logger.info(
            f"[ISC] PostgreSQL read OK: {len(all_data) - 1} SKUs "
            f"({len(consolidated_grupos)} consolidated, {len(snapshot_totals)} grupos com dados)"
        )

    _isc_cache = all_data
    _isc_cache_timestamp = current_time
    _isc_warnings = warnings
    _smart_isc_cache.set(smart_cache_key, all_data)
    return all_data


def get_isc_warnings() -> list:
    return _isc_warnings


_sales_cache = {}
_cache_timestamp = None

def fetch_consolidated_sales_by_skus(skus: List[str], ano: int, apenas_site: bool = False, db: Optional[Session] = None) -> dict:
    """
    Busca vendas consolidadas (Ativo + Magento) para uma lista de SKUs.
    Usa cache para evitar queries repetidas.
    Retorna dict com SKU normalizado como chave.
    
    Args:
        skus: Lista de SKUs para buscar
        ano: Ano do evento
        apenas_site: Se True, retorna apenas vendas do canal Site (excluindo Grupos e Cortesia).
                     Se False (default), retorna vendas totais (Site + Grupos + Cortesia).
        db: Sessão do banco para buscar mapeamentos de SKU (opcional mas recomendado).
    """
    global _sales_cache, _cache_timestamp
    from .inscricoes_consolidado import fetch_ativo_data, fetch_magento_data, get_sku_mappings_from_db, enrich_with_mappings
    import time
    
    sales_by_sku = {}
    
    if not skus:
        return sales_by_sku
    
    import copy
    
    skus_normalized = [normalize_sku(s) for s in skus]
    enriched = db is not None
    cache_key = f"{ano}_{'site' if apenas_site else 'total'}_{'enriched' if enriched else 'raw'}"
    
    current_time = time.time()
    cache_valid = _cache_timestamp and (current_time - _cache_timestamp) < 300
    
    if cache_valid and cache_key in _sales_cache:
        cached_data = _sales_cache[cache_key]
        for sku in skus_normalized:
            if sku in cached_data:
                sales_by_sku[sku] = cached_data[sku].copy()
        return sales_by_sku
    
    mappings = None
    if db:
        try:
            mappings = get_sku_mappings_from_db(db, ano)
        except Exception as e:
            logger.warning(f"Erro ao buscar mapeamentos SKU: {e}")
    
    all_sales = {}
    
    try:
        dados_ativo, error = fetch_ativo_data(ano)
        if dados_ativo:
            if mappings:
                dados_ativo = copy.deepcopy(dados_ativo)
                dados_ativo = enrich_with_mappings(dados_ativo, mappings, "ativo", ano)
            for row in dados_ativo:
                sku = normalize_sku(row.get('sku', '') or '')
                if sku:
                    if apenas_site:
                        qtd = int(row.get('qtd_site', 0) or 0)
                        valor = float(row.get('inscricao_liquida_site', 0) or 0)
                    else:
                        qtd = int(row.get('qtd_vendida', 0) or 0)
                        valor = float(row.get('inscricao_liquida', 0) or 0)
                    if sku in all_sales:
                        all_sales[sku]['qtd_ativo'] += qtd
                        all_sales[sku]['valor_ativo'] += valor
                    else:
                        all_sales[sku] = {
                            'qtd_ativo': qtd,
                            'valor_ativo': valor,
                            'qtd_magento': 0,
                            'valor_magento': 0
                        }
        else:
            logger.warning(f"Sem dados Ativo: {error}")
    except Exception as e:
        logger.error(f"Erro ao buscar dados Ativo: {e}")
    
    try:
        dados_magento, error = fetch_magento_data(ano)
        if dados_magento:
            if mappings:
                dados_magento = copy.deepcopy(dados_magento)
                dados_magento = enrich_with_mappings(dados_magento, mappings, "magento", ano)
            for row in dados_magento:
                sku = normalize_sku(row.get('sku', '') or '')
                if sku:
                    if apenas_site:
                        qtd = int(row.get('qtd_site', 0) or 0)
                        valor = float(row.get('inscricao_liquida_site', 0) or 0)
                    else:
                        qtd = int(row.get('qtd_vendida', 0) or 0)
                        valor = float(row.get('inscricao_liquida', 0) or 0)
                    if sku in all_sales:
                        all_sales[sku]['qtd_magento'] += qtd
                        all_sales[sku]['valor_magento'] += valor
                    else:
                        all_sales[sku] = {
                            'qtd_ativo': 0,
                            'valor_ativo': 0,
                            'qtd_magento': qtd,
                            'valor_magento': valor
                        }
        else:
            logger.warning(f"Sem dados Magento: {error}")
    except Exception as e:
        logger.error(f"Erro ao buscar dados Magento: {e}")
    
    _sales_cache[cache_key] = all_sales
    _cache_timestamp = current_time
    
    for sku in skus_normalized:
        if sku in all_sales:
            sales_by_sku[sku] = all_sales[sku].copy()
    
    return sales_by_sku


def _build_sku_to_grupo_map(db: Session, ano: int) -> dict:
    """
    Constrói mapeamento: SKU normalizado -> evento_grupo
    para o ano solicitado.
    """
    mappings = db.query(SkuMapping).filter(
        SkuMapping.ano == ano,
        SkuMapping.ativo == True,
        SkuMapping.evento_grupo.isnot(None),
        SkuMapping.evento_grupo != ''
    ).all()
    
    sku_to_grupo = {}
    for m in mappings:
        sku_norm = normalize_sku(m.sku)
        if sku_norm:
            sku_to_grupo[sku_norm] = m.evento_grupo
    return sku_to_grupo


def _aggregate_grupo_sales(sales_data: dict, sku_to_grupo: dict) -> dict:
    """
    Agrega vendas de múltiplos SKUs que pertencem ao mesmo evento_grupo.
    Retorna: {evento_grupo: {qtd_ativo, valor_ativo, qtd_magento, valor_magento}}
    """
    grupo_sales = {}
    for sku, sales in sales_data.items():
        grupo = sku_to_grupo.get(sku)
        if grupo is None:
            continue
        if grupo not in grupo_sales:
            grupo_sales[grupo] = {'qtd_ativo': 0, 'valor_ativo': 0.0, 'qtd_magento': 0, 'valor_magento': 0.0}
        grupo_sales[grupo]['qtd_ativo'] += sales.get('qtd_ativo', 0)
        grupo_sales[grupo]['valor_ativo'] += sales.get('valor_ativo', 0.0)
        grupo_sales[grupo]['qtd_magento'] += sales.get('qtd_magento', 0)
        grupo_sales[grupo]['valor_magento'] += sales.get('valor_magento', 0.0)
    return grupo_sales


@router.get("/playbook")
def get_playbook():
    """Retorna o playbook completo com todas as 9 entradas (3 estágios × 3 estados ISC)."""
    stages = [
        {"key": "analitico", "label": "D-90 → D-50", "sublabel": "Analítico", "description": "Fase de análise antecipada. Ações de percepção de valor e construção de demanda."},
        {"key": "estrategico", "label": "D-50 → D-32", "sublabel": "Estratégico", "description": "Fase de decisão estratégica. Janela para ajustes de preço ou promoções privadas."},
        {"key": "operacional", "label": "D-32 → D-0", "sublabel": "Operacional", "description": "Fase de execução final. Foco em conversão, escassez e fechamento de volume."},
    ]
    isc_states = [
        {"key": "forte", "label": "ISC Forte", "threshold": ">1,12", "color": "green"},
        {"key": "estavel", "label": "ISC Estável", "threshold": "0,90–1,12", "color": "yellow"},
        {"key": "fraco", "label": "ISC Fraco", "threshold": "<0,90", "color": "red"},
    ]
    entries = []
    for stage in stages:
        for isc in isc_states:
            entry = _PLAYBOOK.get((stage["key"], isc["key"]), {})
            entries.append({**entry, "stageInfo": stage, "iscInfo": isc})
    return {"stages": stages, "iscStates": isc_states, "entries": entries}

_CUTOFF_VALUES = [65, 50, 45, 35, 30, 15, 7]
_CUTOFF_ESTAGIO = {65: "analitico", 50: "analitico", 45: "estrategico", 35: "estrategico", 30: "operacional", 15: "operacional", 7: "final"}
_CUTOFF_ESTAGIO_LABEL = {65: "Analítico", 50: "Analítico", 45: "Estratégico", 35: "Estratégico", 30: "Operacional", 15: "Operacional", 7: "Final"}

def _match_cutoff_with_weekend(d_minus: int) -> int | None:
    if d_minus in _CUTOFF_VALUES:
        return d_minus
    today = today_brazil()
    weekday = today.weekday()
    if weekday == 4:
        if (d_minus - 1) in _CUTOFF_VALUES:
            return d_minus - 1
        if (d_minus - 2) in _CUTOFF_VALUES:
            return d_minus - 2
    return None

@router.get("/cutoff-alerts")
def get_cutoff_alerts(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Retorna eventos cujo D-Inscrição está exatamente em um ponto de corte estratégico.
    Na sexta-feira, antecipa pontos de corte que cairiam no sábado ou domingo."""
    ano = datetime.now().year
    cache_key = f"{ano}_active_all_"
    cached, _ = eventos_list_cache.get_or_revalidate(cache_key, refresh_fn=None)
    if cached is None:
        cache_key2 = f"{ano}_all_all_"
        cached, _ = eventos_list_cache.get_or_revalidate(cache_key2, refresh_fn=None)
    # Cache miss (e.g., right after a dash refresh invalidated it): compute the
    # eventos list inline so the Nori cutoff alerts don't temporarily disappear.
    if cached is None:
        try:
            cached = get_marketing_events(
                ano=ano, status=None, categoria=None, busca=None,
                force_refresh=False, db=db, current_user=current_user, response=None,
            )
        except Exception as _e_recompute:
            logger.warning(f"[CutoffAlerts] fallback recompute falhou: {_e_recompute}")
            cached = None
    eventos = cached.get("eventos", []) if cached else []
    alerts = []
    for ev in eventos:
        d = ev.get("dMinusInscricoes") if isinstance(ev, dict) else getattr(ev, "dMinusInscricoes", None)
        matched_cutoff = _match_cutoff_with_weekend(d) if d is not None else None
        if matched_cutoff is not None:
            ev_id = ev.get("id") if isinstance(ev, dict) else getattr(ev, "id", None)
            ev_name = ev.get("name") if isinstance(ev, dict) else getattr(ev, "name", None)
            ev_cat = ev.get("category") if isinstance(ev, dict) else getattr(ev, "category", None)
            ev_isc = ev.get("isc") if isinstance(ev, dict) else getattr(ev, "isc", None)
            ev_isc_status = ev.get("iscStatus") if isinstance(ev, dict) else getattr(ev, "iscStatus", None)
            antecipado = matched_cutoff != d
            alerts.append({
                "id": ev_id,
                "name": ev_name,
                "category": ev_cat,
                "dMinusInscricoes": d,
                "ponto_corte": f"D-{matched_cutoff}",
                "estagio": _CUTOFF_ESTAGIO.get(matched_cutoff, ""),
                "estagio_label": _CUTOFF_ESTAGIO_LABEL.get(matched_cutoff, ""),
                "isc": round(ev_isc, 2) if ev_isc is not None else None,
                "iscStatus": ev_isc_status,
                "antecipado": antecipado,
            })
    alerts.sort(key=lambda x: x["dMinusInscricoes"])

    # Enriquecer alerts com flag de ação registrada consultando acoes_comerciais via SkuMapping
    if alerts:
        from ...models.dimensoes import AcaoComercial
        from .inscricoes_consolidado import normalize_sku as _norm_sku
        cutoff_pcs = [f"D-{v}" for v in _CUTOFF_VALUES]

        # Buscar ações para os ponto_corte conhecidos com o codigo do projeto
        acoes_rows = (
            db.query(AcaoComercial.ponto_corte, DimProjeto.id, DimProjeto.codigo)
            .join(DimProjeto, AcaoComercial.projeto_id == DimProjeto.id)
            .filter(AcaoComercial.ponto_corte.in_(cutoff_pcs))
            .all()
        )

        if acoes_rows:
            # Coletar codigos brutos para filtrar SkuMapping via SQL
            raw_codigos = {str(r.codigo) for r in acoes_rows if r.codigo}
            sm_rows = (
                db.query(SkuMapping.sku, SkuMapping.evento_grupo)
                .filter(SkuMapping.sku.in_(raw_codigos), SkuMapping.evento_grupo != None)
                .all()
            )
            # Chave normalizada -> grupo (mesmo padrão usado no eventos list)
            sku_to_grupo = {_norm_sku(r.sku): r.evento_grupo for r in sm_rows}

            # Construir set de chaves {ev_id|ponto_corte}
            action_keys: set = set()
            for a in acoes_rows:
                pc = a.ponto_corte
                sku_n = _norm_sku(str(a.codigo)) if a.codigo else None
                grupo = sku_to_grupo.get(sku_n) if sku_n else None
                if grupo:
                    action_keys.add(f"grp_{grupo}|{pc}")
                else:
                    action_keys.add(f"{a.id}|{pc}")

            for alert in alerts:
                key = f"{alert['id']}|{alert['ponto_corte']}"
                alert["acao_definida"] = key in action_keys
        else:
            for alert in alerts:
                alert["acao_definida"] = False

    return {"alerts": alerts, "total": len(alerts)}


@router.get("/eventos", response_model=MarketingEventsResponse)
def get_marketing_events(
    ano: int = Query(default=None, description="Ano dos eventos"),
    status: Optional[str] = Query(None, description="Filtrar por status: active, closed, all"),
    categoria: Optional[str] = Query(None, description="Filtrar por categoria/modalidade"),
    busca: Optional[str] = Query(None, description="Buscar por nome do evento"),
    force_refresh: bool = Query(default=False, description="Forçar atualização dos dados ignorando cache"),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
    response: Response = None
):
    """
    Retorna eventos para o Dashboard ISC com dados consolidados de vendas
    dos bancos Ativo e Magento.
    Agrupa projetos por EventoGrupo quando disponível.
    """
    if ano is None:
        ano = datetime.now().year

    cache_key = f"{ano}_{status or 'all'}_{categoria or 'all'}_{busca or ''}"

    # Caminho de usuário: nunca recomputa síncrono. force_refresh=True de um
    # usuário é tratado como "serve cache + bg refresh" — mesma semântica SWR.
    # Apenas chamadas internas (current_user=None) executam o caminho lento.
    _is_internal_call = current_user is None
    _user_force_refresh = force_refresh and not _is_internal_call

    def _swr_refresh():
        from ...core.database import SessionLocal
        _db = SessionLocal()
        try:
            get_marketing_events(
                ano=ano, status=status, categoria=categoria, busca=busca,
                force_refresh=True, db=_db, current_user=None,
            )
        finally:
            _db.close()

    def _kick_bg_refresh():
        """Dispara refresh em background, deduplicado por cache_key."""
        _bg_key = f"eventos_list:{cache_key}"
        if _bg_key in _swr_recompute_in_progress:
            return
        _swr_recompute_in_progress.add(_bg_key)
        def _runner():
            try:
                _swr_refresh()
            except Exception as _e:
                logger.warning(f"[EventosList] bg refresh '{cache_key}' falhou: {_e}")
            finally:
                _swr_recompute_in_progress.discard(_bg_key)
        try:
            import threading as _list_threading
            _list_threading.Thread(target=_runner, daemon=True).start()
        except Exception:
            _swr_recompute_in_progress.discard(_bg_key)

    if not _is_internal_call:
        # Usuário: sempre tenta cache primeiro.
        cached, is_stale = eventos_list_cache.get_or_revalidate(
            cache_key,
            refresh_fn=_swr_refresh if not _user_force_refresh else None,
        )
        if _user_force_refresh:
            _kick_bg_refresh()
        if cached is not None:
            from app.core.cache import get_last_full_refresh as _glf_eventos
            _lfr_ev = _glf_eventos()
            if _lfr_ev:
                cached = dict(cached)
                cached["ultima_atualizacao"] = datetime.fromtimestamp(
                    _lfr_ev, tz=ZoneInfo('America/Sao_Paulo')
                ).isoformat()
            if response is not None:
                response.headers["X-Data-Stale"] = "true" if (is_stale or _user_force_refresh) else "false"
            return cached
        # Sem cache: dispara refresh em background (deduplicado) e retorna
        # preparing imediatamente. O frontend faz polling até o cache popular.
        _kick_bg_refresh()
        if response is not None:
            response.headers["X-Data-Preparing"] = "true"
            response.headers["X-Data-Stale"] = "true"
        return {
            "status": "preparing",
            "eventos": [],
            "resumo": {
                "totalActiveEvents": 0,
                "eventsGreen": 0,
                "eventsYellow": 0,
                "eventsRed": 0,
            },
            "categorias": [],
            "ultima_atualizacao": datetime.now(ZoneInfo('America/Sao_Paulo')).isoformat(),
            "avisos": ["Estamos preparando os eventos. Em alguns segundos a lista aparece aqui."],
        }
    # Caminho interno (warmup/SWR): executa o caminho completo abaixo.
    
    isc_cfg = _get_isc_settings(db)
    
    cadastro_query = db.query(CadastroEvento)
    if categoria and categoria != 'all':
        cadastro_query = cadastro_query.filter(CadastroEvento.modalidade == categoria)
    if busca:
        cadastro_query = cadastro_query.filter(CadastroEvento.nome.ilike(f'%{busca}%'))
    cadastros = cadastro_query.all()
    
    cadastro_by_projeto_id = {}
    for cad in cadastros:
        if cad.projeto_id:
            cadastro_by_projeto_id[cad.projeto_id] = cad
    
    projeto_ids = [cad.projeto_id for cad in cadastros if cad.projeto_id]
    projetos = db.query(DimProjeto).filter(DimProjeto.id.in_(projeto_ids)).all() if projeto_ids else []
    
    from ...core.cache import is_full_refresh_in_progress as _is_refreshing
    isc_force = force_refresh and not _is_refreshing()
    isc_data = fetch_isc_pricing_data(db=db, force_refresh=isc_force)
    
    sku_to_grupo = _build_sku_to_grupo_map(db, ano)
    
    grupo_names_set = set(sku_to_grupo.values())
    grupo_details = {}
    if grupo_names_set:
        grupo_list = db.query(EventoGrupoModel).filter(
            EventoGrupoModel.nome.in_(list(grupo_names_set)),
            EventoGrupoModel.ativo == True
        ).all()
        for g in grupo_list:
            grupo_details[g.nome] = g
    
    grupo_projetos = {}
    standalone_projetos = []
    
    for projeto in projetos:
        projeto_codigo = str(projeto.codigo) if projeto.codigo else None
        if not projeto_codigo:
            continue
        
        sku_norm = normalize_sku(projeto_codigo)
        grupo_nome = sku_to_grupo.get(sku_norm)
        
        if grupo_nome and grupo_nome in grupo_details:
            if grupo_nome not in grupo_projetos:
                grupo_projetos[grupo_nome] = []
            grupo_projetos[grupo_nome].append(projeto)
        else:
            standalone_projetos.append(projeto)
    
    eventos = []
    categorias_set: set[str] = set()
    events_green = 0
    events_yellow = 0
    events_red = 0
    active_count = 0
    
    all_projeto_ids = []
    for proj_list in grupo_projetos.values():
        all_projeto_ids.extend([p.id for p in proj_list])
    all_projeto_ids.extend([p.id for p in standalone_projetos])
    
    active_actions_map = get_active_actions_for_projects(db, all_projeto_ids)
    kit_costs_batch = get_kit_basico_costs_batch(db, all_projeto_ids) if all_projeto_ids else {}
    ticket_atual_map = _get_ticket_atual_map(db)

    all_grupo_names_for_hist = set(grupo_projetos.keys())
    for projeto in standalone_projetos:
        sku_n = normalize_sku(str(projeto.codigo)) if projeto.codigo else None
        if sku_n:
            eg = sku_to_grupo.get(sku_n)
            if eg:
                all_grupo_names_for_hist.add(eg)
    hist_patterns_prefetch, curva_info_prefetch = _prefetch_all_historical_patterns(db, list(all_grupo_names_for_hist), ano)

    for grupo_nome, proj_list in grupo_projetos.items():
        grupo = grupo_details[grupo_nome]
        
        total_capacity = 0
        for p in proj_list:
            cad = cadastro_by_projeto_id.get(p.id)
            if cad:
                total_capacity += get_meta_from_cadastro(cad)
            else:
                total_capacity += get_meta_orcada(db, p.id)
        
        latest_date = None
        rep_projeto = proj_list[0]
        rep_cadastro = cadastro_by_projeto_id.get(rep_projeto.id)
        
        for p in proj_list:
            if p.data_evento:
                if latest_date is None or p.data_evento > latest_date:
                    latest_date = p.data_evento
                    rep_projeto = p
                    rep_cadastro = cadastro_by_projeto_id.get(p.id)
        
        projeto_data_evento = latest_date or rep_projeto.data_evento
        dias_enc = get_dias_encerramento(db, projeto_id=rep_projeto.id, cadastro=rep_cadastro) if rep_projeto else 2
        d_minus_inscricoes = calculate_d_minus(projeto_data_evento, dias_encerramento=dias_enc) if projeto_data_evento else 0
        d_minus = calculate_d_minus(projeto_data_evento, dias_encerramento=0) if projeto_data_evento else 0
        is_active = d_minus_inscricoes > 0
        grupo_regime = get_data_regime(projeto_data_evento, dias_enc) if projeto_data_evento else "live"
        
        if status == 'active' and not is_active:
            continue
        if status == 'closed' and is_active:
            continue
        
        current_sales = 0
        current_receita = 0.0
        grupo_m7d = 0.0
        grupo_m14d = 0.0
        grupo_m30d = 0.0

        if grupo_regime == "consolidated":
            _ct = isc_data.get('_consolidated_totals', {}).get(grupo_nome)
            if _ct is not None:
                current_sales = _ct['qtd_site']
                current_receita = _ct['receita_liquida_site']
            else:
                snap = _get_snapshot_metrics_for_grupo(db, grupo_nome)
                if snap is not None:
                    current_sales = snap['qtd_site']
                    current_receita = snap['receita_liquida_site']
                else:
                    seen_grupo_norms_c = set()
                    for p in proj_list:
                        p_sku = normalize_sku(str(p.codigo)) if p.codigo else None
                        if p_sku and p_sku not in seen_grupo_norms_c and p_sku in isc_data:
                            seen_grupo_norms_c.add(p_sku)
                            current_sales += isc_data[p_sku].get('qtd_site', 0)
                            current_receita += isc_data[p_sku].get('receita_liquida_site', 0.0)
        else:
            seen_grupo_norms = set()
            for p in proj_list:
                p_sku = normalize_sku(str(p.codigo)) if p.codigo else None
                if p_sku and p_sku not in seen_grupo_norms and p_sku in isc_data:
                    seen_grupo_norms.add(p_sku)
                    current_sales += isc_data[p_sku].get('qtd_site', 0)
                    current_receita += isc_data[p_sku].get('receita_liquida_site', 0.0)
                    grupo_m7d += isc_data[p_sku].get('media_7d', 0.0)
                    grupo_m14d += isc_data[p_sku].get('media_14d', 0.0)
                    grupo_m30d += isc_data[p_sku].get('media_30d', 0.0)

        sales_goal = total_capacity
        avg_ticket = round(current_receita / current_sales, 2) if current_sales > 0 else 0.0

        budget_ticket_total_receita = 0.0
        budget_ticket_total_qtd = 0
        for p in proj_list:
            cad_bt = cadastro_by_projeto_id.get(p.id)
            if cad_bt and cad_bt.atletas_site_tkt_medio and cad_bt.atletas_site_pago:
                budget_ticket_total_receita += float(cad_bt.atletas_site_tkt_medio) * int(cad_bt.atletas_site_pago)
                budget_ticket_total_qtd += int(cad_bt.atletas_site_pago)
        budget_ticket = round(budget_ticket_total_receita / budget_ticket_total_qtd, 2) if budget_ticket_total_qtd > 0 else 0.0

        grupo_hist_pattern = hist_patterns_prefetch.get(grupo_nome)
        grupo_curva_info = curva_info_prefetch.get(grupo_nome, {"tipo_curva": "linear", "fonte_curva": None, "ano_referencia": None})
        grupo_reg_close = (projeto_data_evento - timedelta(days=dias_enc)) if projeto_data_evento else None

        isc_components = calculate_isc_components(
            current_sales, sales_goal, d_minus_inscricoes,
            media_7d=grupo_m7d,
            media_14d=grupo_m14d,
            media_30d=grupo_m30d,
            hist_pattern=grupo_hist_pattern,
            registration_close_date=grupo_reg_close,
            curva_info=grupo_curva_info
        )
        isc = calculate_isc(isc_components, isc_cfg["ia730Weight"], isc_cfg["curvaDWeight"], isc_cfg["rolling14dWeight"])
        isc_status = get_isc_status(isc, isc_cfg["greenThreshold"], isc_cfg["yellowThreshold"])
        suggested_action = get_suggested_action(isc, d_minus_inscricoes, isc_cfg["greenThreshold"], isc_cfg["yellowThreshold"], isc_cfg["promotionDeadline"])
        
        if is_active:
            active_count += 1
            if isc_status == 'accelerating':
                events_green += 1
            elif isc_status == 'stable':
                events_yellow += 1
            else:
                events_red += 1
        
        grupo_modalidade = str(rep_cadastro.modalidade) if rep_cadastro and rep_cadastro.modalidade else (str(rep_projeto.modalidade) if rep_projeto.modalidade else None)
        if grupo_modalidade:
            categorias_set.add(grupo_modalidade)
        
        grupo_location = str(rep_cadastro.localizacao_evento) if rep_cadastro and rep_cadastro.localizacao_evento else (str(rep_projeto.cidade) if rep_projeto.cidade else None)
        
        skus_list = [str(p.codigo) for p in proj_list if p.codigo]
        
        grupo_active_action = None
        for p in proj_list:
            if p.id in active_actions_map:
                grupo_active_action = active_actions_map[p.id]
                break
        
        grupo_kit_weighted_num = 0.0
        grupo_kit_weighted_den = 0
        for p in proj_list:
            p_cad = cadastro_by_projeto_id.get(p.id)
            p_cap = get_meta_from_cadastro(p_cad) if p_cad else get_meta_orcada(db, p.id)
            p_kc = kit_costs_batch.get(p.id, 50.0)
            grupo_kit_weighted_num += p_kc * p_cap
            grupo_kit_weighted_den += p_cap
        grupo_kit_cost_avg = (grupo_kit_weighted_num / grupo_kit_weighted_den) if grupo_kit_weighted_den > 0 else 50.0
        grupo_margin = _calc_margin_fields(budget_ticket, grupo_kit_cost_avg, sales_goal,
                                            avg_ticket, current_sales, current_receita)
        
        grupo_ticket_atual = _get_ticket_atual_for_event(ticket_atual_map, [p.id for p in proj_list])
        grupo_ticket_kit_nome = _get_ticket_atual_kit_nome_for_event(ticket_atual_map, [p.id for p in proj_list])
        
        evento = MarketingEvent(
            id=f"grp_{grupo_nome}",
            name=grupo.nome,
            date=projeto_data_evento.isoformat() if projeto_data_evento else "",
            location=grupo_location or "Não definido",
            category=grupo_modalidade or "Corrida",
            totalCapacity=sales_goal,
            currentSales=current_sales,
            salesGoal=sales_goal,
            averageTicket=round(avg_ticket, 2),
            budgetTicket=budget_ticket,
            dMinus=d_minus,
            dMinusInscricoes=d_minus_inscricoes,
            isc=isc,
            iscComponents=isc_components,
            iscStatus=isc_status,
            suggestedAction=suggested_action,
            activeAction=grupo_active_action,
            isActive=is_active,
            sku=",".join(skus_list),
            ticketAtual=grupo_ticket_atual,
            ticketKitNome=grupo_ticket_kit_nome,
            dataRegime=grupo_regime,
            incluirCortesias=bool(getattr(grupo, 'incluir_cortesias', False)),
            **grupo_margin
        )
        eventos.append(evento)
    
    for projeto in standalone_projetos:
        projeto_codigo = str(projeto.codigo) if projeto.codigo else None
        if not projeto_codigo:
            continue
        
        cad = cadastro_by_projeto_id.get(projeto.id)
        sku = projeto_codigo
        projeto_data_evento = projeto.data_evento
        dias_enc = get_dias_encerramento(db, projeto_id=projeto.id, cadastro=cad)
        d_minus_inscricoes = calculate_d_minus(projeto_data_evento, dias_encerramento=dias_enc) if projeto_data_evento else 0
        d_minus = calculate_d_minus(projeto_data_evento, dias_encerramento=0) if projeto_data_evento else 0
        is_active = d_minus_inscricoes > 0
        standalone_regime = get_data_regime(projeto_data_evento, dias_enc) if projeto_data_evento else "live"
        
        if status == 'active' and not is_active:
            continue
        if status == 'closed' and is_active:
            continue
        
        sku_norm = normalize_sku(sku)
        standalone_eg = sku_to_grupo.get(normalize_sku(sku))

        if standalone_regime == "consolidated":
            snap_eg = standalone_eg or sku_norm
            snap = _get_snapshot_metrics_for_grupo(db, snap_eg)
            if snap is not None:
                current_sales = snap['qtd_site']
                current_receita = snap['receita_liquida_site']
                standalone_m7d = 0.0
                standalone_m14d = 0.0
                standalone_m30d = 0.0
            else:
                sales_info = isc_data.get(sku_norm, {})
                current_sales = sales_info.get('qtd_site', 0)
                current_receita = sales_info.get('receita_liquida_site', 0.0)
                standalone_m7d = 0.0
                standalone_m14d = 0.0
                standalone_m30d = 0.0
        else:
            sales_info = isc_data.get(sku_norm, {})
            current_sales = sales_info.get('qtd_site', 0)
            current_receita = sales_info.get('receita_liquida_site', 0.0)
            standalone_m7d = sales_info.get('media_7d', 0.0)
            standalone_m14d = sales_info.get('media_14d', 0.0)
            standalone_m30d = sales_info.get('media_30d', 0.0)
        
        sales_goal = get_meta_from_cadastro(cad) if cad else get_meta_orcada(db, projeto.id)
        avg_ticket = round(current_receita / current_sales, 2) if current_sales > 0 else 0.0
        standalone_budget_ticket = round(float(cad.atletas_site_tkt_medio), 2) if cad and cad.atletas_site_tkt_medio and cad.atletas_site_pago and cad.atletas_site_pago > 0 else 0.0
        
        standalone_hist = hist_patterns_prefetch.get(standalone_eg) if standalone_eg else None
        standalone_curva_info = curva_info_prefetch.get(standalone_eg, {"tipo_curva": "linear", "fonte_curva": None, "ano_referencia": None}) if standalone_eg else {"tipo_curva": "linear", "fonte_curva": None, "ano_referencia": None}
        standalone_reg_close = (projeto_data_evento - timedelta(days=dias_enc)) if projeto_data_evento else None

        isc_components = calculate_isc_components(
            current_sales, sales_goal, d_minus_inscricoes,
            media_7d=standalone_m7d,
            media_14d=standalone_m14d,
            media_30d=standalone_m30d,
            hist_pattern=standalone_hist,
            registration_close_date=standalone_reg_close,
            curva_info=standalone_curva_info
        )
        isc = calculate_isc(isc_components, isc_cfg["ia730Weight"], isc_cfg["curvaDWeight"], isc_cfg["rolling14dWeight"])
        isc_status = get_isc_status(isc, isc_cfg["greenThreshold"], isc_cfg["yellowThreshold"])
        suggested_action = get_suggested_action(isc, d_minus_inscricoes, isc_cfg["greenThreshold"], isc_cfg["yellowThreshold"], isc_cfg["promotionDeadline"])
        
        if is_active:
            active_count += 1
            if isc_status == 'accelerating':
                events_green += 1
            elif isc_status == 'stable':
                events_yellow += 1
            else:
                events_red += 1
        
        evento_modalidade = str(cad.modalidade) if cad and cad.modalidade else (str(projeto.modalidade) if projeto.modalidade else None)
        if evento_modalidade:
            categorias_set.add(evento_modalidade)
        
        evento_location = str(cad.localizacao_evento) if cad and cad.localizacao_evento else (str(projeto.cidade) if projeto.cidade else None)
        evento_nome = str(cad.nome) if cad and cad.nome else (str(projeto.evento) if projeto.evento else "Evento sem nome")
        
        standalone_active_action = active_actions_map.get(projeto.id)
        
        standalone_kit_cost = kit_costs_batch.get(projeto.id, 50.0)
        standalone_margin = _calc_margin_fields(standalone_budget_ticket, standalone_kit_cost, sales_goal,
                                                 avg_ticket, current_sales, current_receita)
        
        standalone_ticket_atual = _get_ticket_atual_for_event(ticket_atual_map, projeto.id)
        standalone_ticket_kit_nome = _get_ticket_atual_kit_nome_for_event(ticket_atual_map, projeto.id)
        
        evento = MarketingEvent(
            id=str(projeto.id),
            name=evento_nome,
            date=projeto_data_evento.isoformat() if projeto_data_evento else "",
            location=evento_location or "Não definido",
            category=evento_modalidade or "Corrida",
            totalCapacity=sales_goal,
            currentSales=current_sales,
            salesGoal=sales_goal,
            averageTicket=round(avg_ticket, 2),
            budgetTicket=standalone_budget_ticket,
            dMinus=d_minus,
            dMinusInscricoes=d_minus_inscricoes,
            isc=isc,
            iscComponents=isc_components,
            iscStatus=isc_status,
            suggestedAction=suggested_action,
            activeAction=standalone_active_action,
            isActive=is_active,
            sku=sku,
            ticketAtual=standalone_ticket_atual,
            ticketKitNome=standalone_ticket_kit_nome,
            dataRegime=standalone_regime,
            incluirCortesias=bool(getattr(projeto, 'incluir_cortesias', False)),
            **standalone_margin
        )
        eventos.append(evento)
    
    eventos.sort(key=lambda e: (not e.isActive, e.dMinus))
    
    resumo = DashboardSummary(
        totalActiveEvents=active_count,
        eventsGreen=events_green,
        eventsYellow=events_yellow,
        eventsRed=events_red
    )
    
    from app.core.cache import get_last_full_refresh as _eventos_get_lfr
    _eventos_lfr = _eventos_get_lfr()
    _eventos_ts = (
        datetime.fromtimestamp(_eventos_lfr, tz=ZoneInfo('America/Sao_Paulo')).isoformat()
        if _eventos_lfr
        else datetime.now(ZoneInfo('America/Sao_Paulo')).isoformat()
    )
    result = MarketingEventsResponse(
        status="success",
        eventos=eventos,
        resumo=resumo,
        categorias=sorted(list(categorias_set)),
        ultima_atualizacao=_eventos_ts,
        avisos=get_isc_warnings()
    )
    eventos_list_cache.set(cache_key, result.model_dump(mode="json"))
    if response is not None:
        response.headers["X-Data-Stale"] = "false"
    return result


@router.get("/resumo")
def get_marketing_summary(
    ano: int = Query(default=None, description="Ano dos eventos"),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    """
    Retorna apenas o resumo do Dashboard ISC (contagem por zona).
    """
    response = get_marketing_events(ano=ano, db=db, current_user=current_user)
    return {
        "status": "success",
        "resumo": response.resumo,
        "ultima_atualizacao": response.ultima_atualizacao
    }


@router.get("/eventos/{evento_id}/medias-vendas")
def get_sales_averages(
    evento_id: str,
    periodo: int = Query(default=30, description="Período em dias para calcular médias (7, 14, 30, 60, 90)"),
    ano: int = Query(default=None, description="Ano do evento"),
    force_refresh: bool = Query(default=False, description="Forçar atualização dos dados ignorando cache"),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
    response: Response = None
):
    from datetime import timedelta
    
    today = today_brazil()
    if ano is None:
        ano = today.year
    
    medias_cache_key = f"{ano}_{evento_id}_{periodo}_medias"
    if not force_refresh:
        def _swr_medias_refresh():
            from ...core.database import SessionLocal
            _db = SessionLocal()
            try:
                get_sales_averages(evento_id=evento_id, periodo=periodo, ano=ano, force_refresh=True, db=_db, current_user=None)
            finally:
                _db.close()

        cached_medias, is_stale = medias_cache.get_or_revalidate(medias_cache_key, refresh_fn=_swr_medias_refresh)
        if cached_medias is not None:
            if response is not None:
                response.headers["X-Data-Stale"] = "true" if is_stale else "false"
            return cached_medias
    
    is_consolidated = evento_id.startswith('grp_')
    
    all_skus = []
    
    if is_consolidated:
        grupo_nome = evento_id.replace('grp_', '')
        mappings = _wq_sku_mappings_by_grupo_single_year(db, grupo_nome, ano)
        if not mappings:
            mappings = _wq_sku_mappings_by_grupo(db, grupo_nome, [ano])
            if not mappings:
                from app.core.cache import get_warmup_sku_mappings_by_grupo
                if _is_warmup_thread():
                    all_grupo_mappings = get_warmup_sku_mappings_by_grupo(grupo_nome, list(range(2020, ano+1)))
                else:
                    all_grupo_mappings = db.query(SkuMapping).filter(
                        SkuMapping.evento_grupo == grupo_nome,
                        SkuMapping.ativo == True
                    ).all()
                if all_grupo_mappings:
                    best_year = max(m.ano for m in all_grupo_mappings if m.ano)
                    mappings = [m for m in all_grupo_mappings if m.ano == best_year]
        all_skus = list(set(m.sku.upper().strip() for m in mappings if m.sku))
    else:
        try:
            projeto_id = int(evento_id)
            projeto = _wq_dim_projeto_by_id(db, projeto_id)
            if projeto and projeto.codigo:
                all_skus = [str(projeto.codigo).upper().strip()]
        except ValueError:
            raise HTTPException(status_code=400, detail="ID do evento inválido")
    
    if not all_skus:
        raise HTTPException(status_code=404, detail="Evento não encontrado")
    
    ativo_ids = []
    magento_ids = []
    
    all_active_mappings = _wq_sku_mappings_by_skus(db, all_skus)
    if all_active_mappings is None:
        all_active_mappings = db.query(SkuMapping).filter(
            SkuMapping.sku.in_(all_skus),
            SkuMapping.ativo == True
        ).all()
    
    year_mappings = [m for m in all_active_mappings if m.ano == ano]
    if not year_mappings and all_active_mappings:
        available_years = sorted(set(m.ano for m in all_active_mappings if m.ano), reverse=True)
        if available_years:
            year_mappings = [m for m in all_active_mappings if m.ano == available_years[0]]
    
    for m in year_mappings:
        if m.id_externo:
            if m.fonte == 'ATIVO':
                ativo_ids.append(str(m.id_externo))
            elif m.fonte == 'MAGENTO':
                magento_ids.append(str(m.id_externo))
    
    all_raw_sales = {}
    
    if ativo_ids:
        ativo_rows = _fetch_daily_sales_ativo_by_ids(list(set(ativo_ids)))
        for row in ativo_rows:
            d = date.fromisoformat(row['dia']) if isinstance(row['dia'], str) else row['dia']
            all_raw_sales[d] = all_raw_sales.get(d, 0) + row['qtd']
    
    if magento_ids:
        _cort_avg = _get_cortesia_magento_ids(db)
        _mag_cort_avg = set(magento_ids) & _cort_avg if _cort_avg else None
        magento_rows = _fetch_daily_sales_magento_by_ids(list(set(magento_ids)), cortesia_magento_ids=_mag_cort_avg if _mag_cort_avg else None)
        for row in magento_rows:
            d = date.fromisoformat(row['dia']) if isinstance(row['dia'], str) else row['dia']
            all_raw_sales[d] = all_raw_sales.get(d, 0) + row['qtd']
    
    if all_raw_sales:
        latest_sale = max(all_raw_sales.keys())
        if (today - latest_sale).days > 30:
            ref_date = latest_sale
        else:
            ref_date = today
    else:
        ref_date = today
    
    start_date = ref_date - timedelta(days=periodo)
    all_daily_sales = {d: v for d, v in all_raw_sales.items() if d > start_date and d <= ref_date}
    
    sorted_dates = sorted(all_daily_sales.keys())
    daily_data = [{"date": d.isoformat(), "sales": all_daily_sales[d]} for d in sorted_dates]
    
    total_sales = sum(all_daily_sales.values())
    media_geral = round(total_sales / periodo, 1) if periodo > 0 else 0
    
    sub_periods_map = {
        7:  [7],
        14: [7, 14],
        30: [7, 14, 30],
        60: [7, 30, 60],
        90: [7, 30, 90],
    }
    sub_periods = sub_periods_map.get(periodo, [7, 14, 30])
    
    medias_list = []
    for p in sub_periods:
        cutoff = ref_date - timedelta(days=p)
        sales_in_period = sum(v for d, v in all_daily_sales.items() if d > cutoff)
        medias_list.append({
            "periodo": p,
            "label": f"{p}d",
            "media": round(sales_in_period / p, 1),
            "total": sales_in_period,
            "dias": p,
        })
    
    tendencia_data = []
    if len(sorted_dates) >= 7:
        window = 7
        for i in range(window - 1, len(sorted_dates)):
            window_dates = sorted_dates[max(0, i - window + 1):i + 1]
            window_sales = sum(all_daily_sales[d] for d in window_dates)
            media_movel = round(window_sales / len(window_dates), 1)
            tendencia_data.append({
                "date": sorted_dates[i].isoformat(),
                "media_movel_7d": media_movel,
                "vendas": all_daily_sales[sorted_dates[i]]
            })
    
    medias_result = {
        "status": "success",
        "periodo_dias": periodo,
        "media_geral": media_geral,
        "total_vendas": total_sales,
        "dias_com_dados": len(sorted_dates),
        "medias": medias_list,
        "vendas_diarias": daily_data,
        "tendencia": tendencia_data
    }
    medias_cache.set(medias_cache_key, medias_result)
    return medias_result


@router.get("/eventos/{evento_id}/curva-snapshot")
def get_curva_snapshot(
    evento_id: str,
    ano: int = Query(default=None, description="Ano do evento"),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    """
    Retorna os dados da curva histórica snapshot (ano anterior) para um evento,
    incluindo as quantidades de meta calculadas a partir do percentual e da meta atual.
    """
    from ...services.snapshot_service import get_curva_historica_snapshot

    if ano is None:
        ano = datetime.now().year

    is_grouped = evento_id.startswith("grp_")

    if is_grouped:
        grupo_nome = evento_id.replace("grp_", "")
        grupo = db.query(EventoGrupoModel).filter(EventoGrupoModel.nome == grupo_nome).first()
        if not grupo:
            raise HTTPException(status_code=404, detail="Grupo de evento não encontrado")
        mappings = _wq_sku_mappings_by_grupo_single_year(db, grupo_nome, ano)
        proj_skus = list(set(m.sku for m in mappings))
        projetos_q = _wq_dim_projetos_by_codigos(db, proj_skus)
        sales_goal = get_meta_orcada_projetos(db, projetos_q)
        evento_grupo = grupo_nome
    else:
        projeto = _wq_dim_projeto_by_id(db, int(evento_id))
        if not projeto:
            raise HTTPException(status_code=404, detail="Evento não encontrado")
        sales_goal = get_meta_orcada(db, projeto.id)
        evento_grupo = None
        sku = str(projeto.codigo) if projeto.codigo else None
        if sku:
            standalone_mappings = _wq_sku_mappings_by_sku(db, sku)
            for sm in standalone_mappings:
                if sm.evento_grupo and sm.evento_grupo.strip():
                    evento_grupo = sm.evento_grupo
                    break

    if not evento_grupo:
        raise HTTPException(status_code=404, detail="Evento sem grupo configurado")

    prev_ano = ano - 1
    pattern = get_curva_historica_snapshot(db, evento_grupo, prev_ano)

    if not pattern:
        return {
            "status": "success",
            "evento_grupo": evento_grupo,
            "ano_referencia": prev_ano,
            "sales_goal": sales_goal,
            "data": [],
            "message": f"Sem dados de curva histórica para {prev_ano}"
        }

    sorted_dms = sorted(pattern.keys(), reverse=True)
    rows = []
    prev_pct = 0.0
    for i, dm in enumerate(sorted_dms):
        pct_acum = pattern[dm]
        pct_dia = pct_acum - prev_pct
        meta_acumulado = round(pct_acum * sales_goal)
        meta_dia = round(pct_dia * sales_goal)
        rows.append({
            "d_minus": dm,
            "percentual_acumulado": round(pct_acum * 100, 2),
            "percentual_dia": round(pct_dia * 100, 2),
            "meta_acumulado": meta_acumulado,
            "meta_dia": meta_dia,
        })
        prev_pct = pct_acum

    return {
        "status": "success",
        "evento_grupo": evento_grupo,
        "ano_referencia": prev_ano,
        "sales_goal": sales_goal,
        "data": rows
    }


@router.get("/eventos/{evento_id}/simulacao")
def get_event_simulation(
    evento_id: str,
    ano: int = Query(default=None, description="Ano do evento"),
    force_refresh: bool = Query(default=False, description="Forçar atualização"),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    from datetime import timedelta
    today = today_brazil()
    if ano is None:
        ano = today.year

    is_consolidated = evento_id.startswith('grp_')

    all_skus = []
    projetos = []
    if is_consolidated:
        grupo_nome = evento_id.replace('grp_', '')
        mappings = db.query(SkuMapping).filter(
            SkuMapping.evento_grupo == grupo_nome,
            SkuMapping.ano == ano,
            SkuMapping.ativo == True
        ).all()
        if not mappings:
            mappings = db.query(SkuMapping).filter(
                SkuMapping.evento_grupo == grupo_nome,
                SkuMapping.ativo == True
            ).all()
            if mappings:
                best_year = max(m.ano for m in mappings if m.ano)
                mappings = [m for m in mappings if m.ano == best_year]
        all_skus = list(set(m.sku.upper().strip() for m in mappings if m.sku))
        projetos = db.query(DimProjeto).filter(DimProjeto.codigo.in_(all_skus)).all() if all_skus else []
    else:
        try:
            projeto_id_int = int(evento_id)
            projeto = db.query(DimProjeto).filter(DimProjeto.id == projeto_id_int).first()
            if projeto:
                projetos = [projeto]
                if projeto.codigo:
                    all_skus = [str(projeto.codigo).upper().strip()]
        except ValueError:
            raise HTTPException(status_code=400, detail="ID do evento inválido")

    if not all_skus:
        raise HTTPException(status_code=404, detail="Evento não encontrado")

    data_evento = None
    for p in projetos:
        if p.data_evento:
            if data_evento is None or p.data_evento > data_evento:
                data_evento = p.data_evento

    # Use D-Inscrição (registration close date) — same reference used by Dashboard and ISC.
    # get_dias_encerramento reads dias_encerramento_inscricao from CadastroEvento (default 2).
    dias_enc_sim = get_dias_encerramento(db, projeto_id=projetos[0].id) if projetos else 2
    dias_ate_evento = calculate_d_minus(data_evento, dias_encerramento=dias_enc_sim) if data_evento else 0

    meta_orcada = get_meta_orcada_projetos(db, projetos)

    budget_ticket_total_receita = 0.0
    budget_ticket_total_qtd = 0
    for p in projetos:
        cad = db.query(CadastroEvento).filter(CadastroEvento.projeto_id == p.id).first()
        if cad and cad.atletas_site_tkt_medio and cad.atletas_site_pago and cad.atletas_site_pago > 0:
            budget_ticket_total_receita += float(cad.atletas_site_tkt_medio) * int(cad.atletas_site_pago)
            budget_ticket_total_qtd += int(cad.atletas_site_pago)
    ticket_medio_orcado = round(budget_ticket_total_receita / budget_ticket_total_qtd, 2) if budget_ticket_total_qtd > 0 else 0.0

    all_active_mappings = db.query(SkuMapping).filter(
        SkuMapping.sku.in_(all_skus),
        SkuMapping.ativo == True
    ).all()
    year_mappings = [m for m in all_active_mappings if m.ano == ano]
    if not year_mappings and all_active_mappings:
        available_years = sorted(set(m.ano for m in all_active_mappings if m.ano), reverse=True)
        if available_years:
            year_mappings = [m for m in all_active_mappings if m.ano == available_years[0]]

    ativo_ids = []
    magento_ids = []
    for m in year_mappings:
        if m.id_externo:
            if m.fonte == 'ATIVO':
                ativo_ids.append(str(m.id_externo))
            elif m.fonte == 'MAGENTO':
                magento_ids.append(str(m.id_externo))

    # Determine evento_grupo for snapshot lookup (same source used by Dashboard)
    evento_grupo_sim = None
    if is_consolidated:
        evento_grupo_sim = grupo_nome
    else:
        # Try to get evento_grupo from the mappings
        for m in year_mappings:
            if m.evento_grupo:
                evento_grupo_sim = m.evento_grupo
                break

    all_raw_sales = {}
    all_raw_receita = {}

    # Priority 1: use the snapshot table (same source as Dashboard)
    snapshot_used_sim = False
    if evento_grupo_sim:
        from ...services.snapshot_service import get_snapshot_vendas_com_receita
        snap_rows = get_snapshot_vendas_com_receita(db, evento_grupo_sim)
        if snap_rows:
            snapshot_used_sim = True
            for row in snap_rows:
                d = date.fromisoformat(row['dia']) if isinstance(row['dia'], str) else row['dia']
                all_raw_sales[d] = all_raw_sales.get(d, 0) + row['qtd']
                all_raw_receita[d] = all_raw_receita.get(d, 0) + row.get('receita', 0)

    # If snapshot was used, also fetch today's live data if today is not already covered.
    # We estimate today's revenue using the snapshot ticket_medio so that total_receita
    # stays proportional to total_vendas (same ratio used by the Dashboard event detail).
    if snapshot_used_sim:
        event_already_happened = data_evento and data_evento < today
        today_in_snap = today in all_raw_sales
        if not event_already_happened and not today_in_snap:
            # Compute snapshot ticket_medio to estimate today's revenue
            snap_qty_total = sum(all_raw_sales.values())
            snap_receita_total = sum(all_raw_receita.values())
            snap_ticket_medio = (snap_receita_total / snap_qty_total) if snap_qty_total > 0 else 0.0

            today_live_qty = 0
            if ativo_ids:
                try:
                    today_sales = _fetch_today_sales_ativo_by_ids(list(set(ativo_ids)))
                    for d, qty in today_sales.items():
                        all_raw_sales[d] = all_raw_sales.get(d, 0) + qty
                        today_live_qty += qty
                except Exception as e:
                    logger.warning(f"[Simulacao] Failed to fetch today's Ativo sales: {e}")
            if magento_ids:
                try:
                    _cort = _get_cortesia_magento_ids(db)
                    _mag_cort = set(magento_ids) & _cort if _cort else None
                    today_sales = _fetch_today_sales_magento_by_ids(list(set(magento_ids)), cortesia_magento_ids=_mag_cort if _mag_cort else None)
                    for d, qty in today_sales.items():
                        all_raw_sales[d] = all_raw_sales.get(d, 0) + qty
                        today_live_qty += qty
                except Exception as e:
                    logger.warning(f"[Simulacao] Failed to fetch today's Magento sales: {e}")

            # Estimate today's revenue using the snapshot ticket_medio so the ticket
            # and margem remain consistent with the Dashboard (no artificial dilution)
            if today_live_qty > 0 and snap_ticket_medio > 0:
                all_raw_receita[today] = all_raw_receita.get(today, 0.0) + today_live_qty * snap_ticket_medio

    # Priority 2 (fallback): query external sources directly when no snapshot exists
    if not snapshot_used_sim:
        if ativo_ids:
            ativo_rows = _fetch_daily_sales_ativo_by_ids(list(set(ativo_ids)))
            for row in ativo_rows:
                d = date.fromisoformat(row['dia']) if isinstance(row['dia'], str) else row['dia']
                all_raw_sales[d] = all_raw_sales.get(d, 0) + row['qtd']
                all_raw_receita[d] = all_raw_receita.get(d, 0) + row.get('receita', 0)

    if not snapshot_used_sim and magento_ids:
        _cort = _get_cortesia_magento_ids(db)
        _mag_cort = set(magento_ids) & _cort if _cort else None
        magento_rows = _fetch_daily_sales_magento_by_ids(list(set(magento_ids)), cortesia_magento_ids=_mag_cort if _mag_cort else None)
        for row in magento_rows:
            d = date.fromisoformat(row['dia']) if isinstance(row['dia'], str) else row['dia']
            all_raw_sales[d] = all_raw_sales.get(d, 0) + row['qtd']
            all_raw_receita[d] = all_raw_receita.get(d, 0) + row.get('receita', 0)

    total_vendas = sum(all_raw_sales.values())
    total_receita = round(sum(all_raw_receita.values()), 2)

    # ── Align with Dashboard event detail: use ISC cache as the authoritative source
    # for current totals on live/hybrid events (same logic as get_marketing_event_by_id).
    # For consolidated events (dias_ate_evento <= 0) snapshot is already authoritative.
    if evento_grupo_sim and dias_ate_evento > 0:
        try:
            _isc_sim = fetch_isc_pricing_data(db=db)
            _isc_receita_sim = 0.0
            _isc_qtd_sim = 0
            _seen_norms_sim: set = set()
            for _sku_sim in all_skus:
                _norm_sim = normalize_sku(_sku_sim)
                if _norm_sim in _seen_norms_sim:
                    continue
                _seen_norms_sim.add(_norm_sim)
                _info_sim = _isc_sim.get(_norm_sim, {})
                _isc_receita_sim += _info_sim.get('receita_liquida_site', 0.0)
                _isc_qtd_sim += _info_sim.get('qtd_site', 0)
            if _isc_qtd_sim > 0:
                total_receita = round(_isc_receita_sim, 2)
                if _isc_qtd_sim > total_vendas:
                    total_vendas = _isc_qtd_sim
        except Exception as _e_sim:
            logger.warning(f"[Simulacao] ISC alignment failed, using snapshot totals: {_e_sim}")

    ticket_medio_atual = round(total_receita / total_vendas, 2) if total_vendas > 0 else 0.0

    sorted_dates = sorted(all_raw_sales.keys())

    media_7d = 0.0
    media_14d = 0.0
    media_30d = 0.0
    if sorted_dates:
        for window, attr_name in [(7, 'media_7d'), (14, 'media_14d'), (30, 'media_30d')]:
            cutoff = today - timedelta(days=window)
            sales_in = sum(v for d, v in all_raw_sales.items() if d > cutoff and d < today)
            if attr_name == 'media_7d':
                media_7d = round(sales_in / window, 1)
            elif attr_name == 'media_14d':
                media_14d = round(sales_in / window, 1)
            else:
                media_30d = round(sales_in / window, 1)

    primeiro_dia_venda = sorted_dates[0] if sorted_dates else today
    dias_em_venda = (today - primeiro_dia_venda).days + 1
    media_historica = round(total_vendas / dias_em_venda, 1) if dias_em_venda > 0 else 0.0

    receita_7d = sum(v for d, v in all_raw_receita.items() if d > today - timedelta(days=7) and d <= today)
    vendas_7d = sum(v for d, v in all_raw_sales.items() if d > today - timedelta(days=7) and d <= today)
    ticket_7d = round(receita_7d / vendas_7d, 2) if vendas_7d > 0 else ticket_medio_atual

    cenarios = {}
    if dias_ate_evento > 0:
        taxas_base = sorted([media_7d, media_14d, media_30d])
        for nome, taxa in [("pessimista", taxas_base[0] * 0.85), ("realista", taxas_base[1]), ("otimista", taxas_base[2] * 1.15)]:
            proj_vendas = total_vendas + round(taxa * dias_ate_evento)
            proj_receita = total_receita + round(taxa * dias_ate_evento * ticket_7d, 2)
            pct_meta = round(proj_vendas / meta_orcada * 100, 1) if meta_orcada > 0 else 0
            cenarios[nome] = {
                "vendas_projetadas": proj_vendas,
                "receita_projetada": proj_receita,
                "ticket_medio_projetado": round(proj_receita / proj_vendas, 2) if proj_vendas > 0 else 0,
                "ritmo_diario": round(taxa, 1),
                "pct_meta": pct_meta,
                "vendas_restantes": max(0, proj_vendas - total_vendas),
            }
    else:
        cenarios = {
            "pessimista": {"vendas_projetadas": total_vendas, "receita_projetada": total_receita, "ticket_medio_projetado": ticket_medio_atual, "ritmo_diario": 0, "pct_meta": round(total_vendas / meta_orcada * 100, 1) if meta_orcada > 0 else 0, "vendas_restantes": 0},
            "realista": {"vendas_projetadas": total_vendas, "receita_projetada": total_receita, "ticket_medio_projetado": ticket_medio_atual, "ritmo_diario": 0, "pct_meta": round(total_vendas / meta_orcada * 100, 1) if meta_orcada > 0 else 0, "vendas_restantes": 0},
            "otimista": {"vendas_projetadas": total_vendas, "receita_projetada": total_receita, "ticket_medio_projetado": ticket_medio_atual, "ritmo_diario": 0, "pct_meta": round(total_vendas / meta_orcada * 100, 1) if meta_orcada > 0 else 0, "vendas_restantes": 0},
        }

    vendas_por_dia = []
    if sorted_dates and dias_ate_evento > 0:
        for d in sorted_dates:
            vendas_por_dia.append({"date": d.isoformat(), "vendas": all_raw_sales[d], "receita": round(all_raw_receita.get(d, 0), 2)})

    ritmo_necessario = round((meta_orcada - total_vendas) / dias_ate_evento, 1) if dias_ate_evento > 0 and meta_orcada > 0 else 0
    receita_orcada = round(meta_orcada * ticket_medio_orcado, 2) if ticket_medio_orcado > 0 else 0
    gap_vendas = max(0, meta_orcada - total_vendas)
    gap_receita = round(max(0, receita_orcada - total_receita), 2)

    # Custo de kit e margem
    projeto_ids_list = [p.id for p in projetos]
    kit_costs = get_kit_basico_costs_batch(db, projeto_ids_list)
    custo_kit = round(sum(kit_costs.values()) / len(kit_costs), 2) if kit_costs else 50.0

    margem_unit_atual = round(ticket_medio_atual - custo_kit, 2) if ticket_medio_atual > 0 else 0.0
    margem_total_atual = round(total_receita - custo_kit * total_vendas, 2) if total_vendas > 0 else 0.0
    margem_pct_atual = round((margem_unit_atual / ticket_medio_atual) * 100, 1) if ticket_medio_atual > 0 else 0.0

    margem_orcada_unit = round(ticket_medio_orcado - custo_kit, 2) if ticket_medio_orcado > 0 else 0.0
    margem_orcada_total = round(margem_orcada_unit * meta_orcada, 2) if meta_orcada > 0 and ticket_medio_orcado > 0 else 0.0

    # Enrich cenários with margin data
    for nome in cenarios:
        c = cenarios[nome]
        pv = c["vendas_projetadas"]
        pr = c["receita_projetada"]
        c["margem_projetada_unit"] = round(ticket_7d - custo_kit, 2)
        c["margem_projetada_total"] = round(pr - custo_kit * pv, 2) if pv > 0 else 0.0
        c["margem_projetada_pct"] = round(((ticket_7d - custo_kit) / ticket_7d) * 100, 1) if ticket_7d > 0 else 0.0

    return {
        "status": "success",
        "evento": {
            "data_evento": data_evento.isoformat() if data_evento else None,
            "dias_ate_evento": dias_ate_evento,
            "meta_orcada": meta_orcada,
            "ticket_medio_orcado": ticket_medio_orcado,
            "receita_orcada": receita_orcada,
            "custo_kit": custo_kit,
            "margem_orcada_unit": margem_orcada_unit,
            "margem_orcada_total": margem_orcada_total,
        },
        "atual": {
            "total_vendas": total_vendas,
            "total_receita": total_receita,
            "ticket_medio": ticket_medio_atual,
            "ticket_medio_7d": ticket_7d,
            "pct_meta": round(total_vendas / meta_orcada * 100, 1) if meta_orcada > 0 else 0,
            "media_7d": media_7d,
            "media_14d": media_14d,
            "media_30d": media_30d,
            "media_historica": media_historica,
            "dias_em_venda": dias_em_venda,
            "ritmo_necessario": ritmo_necessario,
            "gap_vendas": gap_vendas,
            "custo_kit": custo_kit,
            "margem_unit": margem_unit_atual,
            "margem_total": margem_total_atual,
            "margem_pct": margem_pct_atual,
            "gap_receita": gap_receita,
        },
        "cenarios": cenarios,
        "vendas_diarias": vendas_por_dia,
    }


@router.get("/check-duplicate-action/{projeto_id}")
def check_duplicate_action_endpoint(
    projeto_id: int,
    tipo: str = Query(..., description="Tipo da ação"),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    """Verifica se já existe uma ação duplicada do mesmo tipo nos últimos 7 dias"""
    duplicate = check_duplicate_action(db, projeto_id, tipo)
    return {
        "status": "success",
        "has_duplicate": duplicate is not None,
        "existing_action": duplicate
    }


def _fetch_monthly_sales_ativo(ano_atual: int, ano_anterior: int) -> list:
    if db_module.engine_ssh is None:
        return []
    try:
        query = """
SELECT /*+ MAX_EXECUTION_TIME(90000) */
    YEAR(c.dt_pedido) AS ano,
    MONTH(c.dt_pedido) AS mes,
    COUNT(CASE WHEN (f.en_cupom_classificacao IS NULL
              OR f.en_cupom_classificacao NOT IN ('Funcionário', 'Cortesia Faturada', 'Grupos', 'Coligados', 'Eventos Terceiros'))
        AND (h.ds_categoria IS NULL OR (h.ds_categoria NOT LIKE '%%GRUPOS%%' AND h.ds_categoria NOT LIKE '%%ortesia%%'))
        AND c.nr_total > 0 THEN 1 END) AS qtd,
    SUM(CASE WHEN (f.en_cupom_classificacao IS NULL
              OR f.en_cupom_classificacao NOT IN ('Funcionário', 'Cortesia Faturada', 'Grupos', 'Coligados', 'Eventos Terceiros'))
        AND (h.ds_categoria IS NULL OR (h.ds_categoria NOT LIKE '%%GRUPOS%%' AND h.ds_categoria NOT LIKE '%%ortesia%%'))
        AND c.nr_total > 0 THEN 
        GREATEST(a.nr_preco - COALESCE(a.nr_desconto_individual, 0), 0)
    ELSE 0 END) AS receita
FROM sa_pedido_evento AS a
INNER JOIN sa_evento AS b ON b.id_evento = a.id_evento
INNER JOIN sa_pedido AS c ON c.id_pedido = a.id_pedido
LEFT JOIN sa_modalidade_categoria AS h ON a.id_categoria = h.id_categoria
LEFT JOIN sa_cupom_desconto_item AS e ON e.id_cupom_desconto_item = a.id_cupom_individual
LEFT JOIN sa_cupom_desconto AS f ON f.id_cupom_desconto = e.id_cupom_desconto
WHERE 
    c.fl_local_inscricao = '1'
    AND c.id_pedido_status IN (1, 2)
    AND (b.id_campanha_salesforce IS NULL OR b.id_campanha_salesforce NOT LIKE '701d0000000%%')
    AND YEAR(c.dt_pedido) IN (:ano_atual, :ano_anterior)
GROUP BY YEAR(c.dt_pedido), MONTH(c.dt_pedido)
ORDER BY ano, mes
"""
        with db_module.engine_ssh.connect() as conn:
            result = conn.execute(text(query), {"ano_atual": ano_atual, "ano_anterior": ano_anterior})
            return [{"ano": int(r[0]), "mes": int(r[1]), "qtd": int(r[2] or 0), "receita": float(r[3] or 0)} for r in result.fetchall()]
    except Exception as e:
        logger.error(f"Erro monthly sales Ativo: {e}")
        return []


def _fetch_monthly_sales_magento(ano_atual: int, ano_anterior: int) -> list:
    if db_module.engine_magento is None:
        return []
    try:
        query = """
SELECT
    YEAR(so.created_at) AS ano,
    MONTH(so.created_at) AS mes,
    COUNT(CASE WHEN (so.discount_description IS NULL OR so.discount_description NOT LIKE '%%GRUPOS%%') 
        AND so.base_grand_total > 0 THEN 1 END) AS qtd,
    SUM(CASE WHEN (so.discount_description IS NULL OR so.discount_description NOT LIKE '%%GRUPOS%%') THEN
        (soi.price - CASE WHEN soi.price = 0 THEN 0
            WHEN soi.name LIKE '%%plus%%' THEN 69.00
            WHEN soi.name LIKE '%%super%%' THEN 269.00
            WHEN soi.name LIKE '%%vip%%' THEN 199.99
            ELSE 0 END
        + COALESCE(so.base_discount_invoiced, 0) * (soi.price / NULLIF(so.base_subtotal, 1))
        - CASE WHEN cg.customer_group_id = 4 THEN 0
            WHEN COALESCE(soiaa.price, 0) = 14.90 AND cg.customer_group_id IN (0, 1, 2, 3, 5, 7) THEN 14.90
            ELSE 0 END)
    ELSE 0 END) AS receita
FROM sales_order AS so
LEFT JOIN sales_order_item AS soi ON soi.order_id = so.entity_id
LEFT JOIN customer_group AS cg ON cg.customer_group_id = so.customer_group_id
LEFT JOIN (SELECT parent_item_id, MAX(price) AS price FROM sales_order_item WHERE name LIKE '%%persona%%' GROUP BY parent_item_id) AS soiaa ON soiaa.parent_item_id = soi.item_id
WHERE
    YEAR(so.created_at) IN (:ano_atual, :ano_anterior)
    AND so.increment_id NOT LIKE "%%-1%%"
    AND so.increment_id NOT LIKE "%%-2%%"
    AND so.increment_id NOT LIKE "%%-3%%"
    AND so.increment_id NOT LIKE "%%-4%%"
    AND so.increment_id NOT LIKE "%%-5%%"
    AND so.increment_id NOT LIKE "%%-6%%"
    AND so.increment_id NOT LIKE "%%-7%%"
    AND so.increment_id NOT LIKE "%%-8%%"
    AND so.increment_id NOT LIKE "%%-9%%"
    AND so.increment_id NOT LIKE "%%-10%%"
    AND so.increment_id NOT LIKE "%%-11%%"
    AND so.increment_id NOT LIKE "%%-12%%"
    AND so.increment_id NOT LIKE "%%-13%%"
    AND so.increment_id NOT LIKE "%%-14%%"
    AND so.increment_id NOT LIKE "%%-15%%"
    AND so.increment_id NOT LIKE "%%-16%%"
    AND so.status IN ('Processing', 'Complete', 'approved')
    AND soi.product_type = 'Bundle'
GROUP BY YEAR(so.created_at), MONTH(so.created_at)
ORDER BY ano, mes
"""
        with db_module.engine_magento.connect() as conn:
            result = conn.execute(text(query), {"ano_atual": ano_atual, "ano_anterior": ano_anterior})
            return [{"ano": int(r[0]), "mes": int(r[1]), "qtd": int(r[2] or 0), "receita": float(r[3] or 0)} for r in result.fetchall()]
    except Exception as e:
        logger.error(f"Erro monthly sales Magento: {e}")
        return []


_curva_cache = {}
_curva_cache_timestamp = None


@router.get("/curva-comparativa")
def get_curva_comparativa(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    global _curva_cache, _curva_cache_timestamp
    import time

    current_time = time.time()
    cache_valid = _curva_cache_timestamp and (current_time - _curva_cache_timestamp) < 300

    if cache_valid and _curva_cache:
        return _curva_cache

    ano_atual = datetime.now().year
    ano_anterior = ano_atual - 1

    meses_labels = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]

    future_ativo = _rolling_avg_executor.submit(_fetch_monthly_sales_ativo, ano_atual, ano_anterior)
    future_magento = _rolling_avg_executor.submit(_fetch_monthly_sales_magento, ano_atual, ano_anterior)

    try:
        dados_ativo = future_ativo.result(timeout=60)
    except Exception as e:
        logger.error(f"Curva comparativa Ativo timeout: {e}")
        dados_ativo = []

    try:
        dados_magento = future_magento.result(timeout=60)
    except Exception as e:
        logger.error(f"Curva comparativa Magento timeout: {e}")
        dados_magento = []

    monthly = {}
    for m in range(1, 13):
        monthly[m] = {
            "mes": meses_labels[m - 1],
            f"vendas_{ano_atual}": 0,
            f"vendas_{ano_anterior}": 0,
            f"receita_{ano_atual}": 0.0,
            f"receita_{ano_anterior}": 0.0,
        }

    for row in dados_ativo + dados_magento:
        m = row["mes"]
        a = row["ano"]
        if 1 <= m <= 12:
            if a == ano_atual:
                monthly[m][f"vendas_{ano_atual}"] += row["qtd"]
                monthly[m][f"receita_{ano_atual}"] += row["receita"]
            elif a == ano_anterior:
                monthly[m][f"vendas_{ano_anterior}"] += row["qtd"]
                monthly[m][f"receita_{ano_anterior}"] += row["receita"]

    data = []
    acum_atual = 0
    acum_anterior = 0
    acum_receita_atual = 0.0
    acum_receita_anterior = 0.0
    for m in range(1, 13):
        entry = monthly[m]
        acum_atual += entry[f"vendas_{ano_atual}"]
        acum_anterior += entry[f"vendas_{ano_anterior}"]
        acum_receita_atual += entry[f"receita_{ano_atual}"]
        acum_receita_anterior += entry[f"receita_{ano_anterior}"]
        entry[f"receita_{ano_atual}"] = round(entry[f"receita_{ano_atual}"], 2)
        entry[f"receita_{ano_anterior}"] = round(entry[f"receita_{ano_anterior}"], 2)
        entry[f"acumulado_{ano_atual}"] = acum_atual
        entry[f"acumulado_{ano_anterior}"] = acum_anterior
        entry[f"acumulado_receita_{ano_atual}"] = round(acum_receita_atual, 2)
        entry[f"acumulado_receita_{ano_anterior}"] = round(acum_receita_anterior, 2)
        data.append(entry)

    result = {
        "status": "success",
        "ano_atual": ano_atual,
        "ano_anterior": ano_anterior,
        "data": data,
        "ultima_atualizacao": datetime.now(ZoneInfo('America/Sao_Paulo')).isoformat()
    }

    _curva_cache = result
    _curva_cache_timestamp = current_time
    return result


def _sanitize_skus(skus: list) -> list:
    import re
    return [re.sub(r"[^a-zA-Z0-9_\-]", "", str(s)) for s in skus if s]


def _fetch_monthly_sales_ativo_by_ids(id_eventos: list) -> list:
    if db_module.engine_ssh is None or not id_eventos:
        return []
    try:
        safe_ids = [int(i) for i in id_eventos if str(i).isdigit()]
        if not safe_ids:
            return []
        query = text("""
SELECT /*+ MAX_EXECUTION_TIME(90000) */
    MONTH(c.dt_pedido) AS mes,
    COUNT(CASE WHEN (f.en_cupom_classificacao IS NULL
              OR f.en_cupom_classificacao NOT IN ('Funcionário', 'Cortesia Faturada', 'Grupos', 'Coligados', 'Eventos Terceiros'))
        AND (h.ds_categoria IS NULL OR (h.ds_categoria NOT LIKE '%%GRUPOS%%' AND h.ds_categoria NOT LIKE '%%ortesia%%'))
        AND c.nr_total > 0 THEN 1 END) AS qtd,
    SUM(CASE WHEN (f.en_cupom_classificacao IS NULL
              OR f.en_cupom_classificacao NOT IN ('Funcionário', 'Cortesia Faturada', 'Grupos', 'Coligados', 'Eventos Terceiros'))
        AND (h.ds_categoria IS NULL OR (h.ds_categoria NOT LIKE '%%GRUPOS%%' AND h.ds_categoria NOT LIKE '%%ortesia%%'))
        AND c.nr_total > 0 THEN 
        GREATEST(a.nr_preco - COALESCE(a.nr_desconto_individual, 0), 0)
    ELSE 0 END) AS receita
FROM sa_pedido_evento AS a
INNER JOIN sa_evento AS b ON b.id_evento = a.id_evento
INNER JOIN sa_pedido AS c ON c.id_pedido = a.id_pedido
LEFT JOIN sa_modalidade_categoria AS h ON a.id_categoria = h.id_categoria
LEFT JOIN sa_cupom_desconto_item AS e ON e.id_cupom_desconto_item = a.id_cupom_individual
LEFT JOIN sa_cupom_desconto AS f ON f.id_cupom_desconto = e.id_cupom_desconto
WHERE 
    c.fl_local_inscricao = '1'
    AND c.id_pedido_status IN (1, 2)
    AND (b.id_campanha_salesforce IS NULL OR b.id_campanha_salesforce NOT LIKE '701d0000000%%')
    AND b.id_evento IN :id_eventos
GROUP BY MONTH(c.dt_pedido)
ORDER BY mes
""").bindparams(bindparam("id_eventos", expanding=True))
        with db_module.engine_ssh.connect() as conn:
            result = conn.execute(query, {"id_eventos": safe_ids})
            return [{"mes": int(r[0]), "qtd": int(r[1] or 0), "receita": float(r[2] or 0)} for r in result.fetchall()]
    except Exception as e:
        logger.error(f"Erro monthly sales Ativo by IDs: {e}")
        return []


def _fetch_monthly_sales_magento_by_ids(magento_event_ids: list) -> list:
    if db_module.engine_magento is None or not magento_event_ids:
        return []
    try:
        safe_ids = [int(i) for i in magento_event_ids if str(i).isdigit()]
        if not safe_ids:
            return []
        query = text("""
SELECT
    MONTH(so.created_at) AS mes,
    COUNT(CASE WHEN so.base_grand_total > 0
        AND NOT (so.discount_description LIKE '%%CORTESIA%%' AND so.base_grand_total < 50)
        AND (so.discount_description IS NULL OR so.discount_description NOT LIKE '%%GRUPOS%%')
        AND (so.coupon_code IS NULL OR so.coupon_code NOT LIKE 'GRUP%%')
        THEN 1 END) AS qtd,
    SUM(CASE WHEN so.base_grand_total > 0
        AND NOT (so.discount_description LIKE '%%CORTESIA%%' AND so.base_grand_total < 50)
        AND (so.discount_description IS NULL OR so.discount_description NOT LIKE '%%GRUPOS%%')
        AND (so.coupon_code IS NULL OR so.coupon_code NOT LIKE 'GRUP%%') THEN
        (soi.price - CASE WHEN soi.price = 0 THEN 0
            WHEN soi.name LIKE '%%plus%%' THEN 69.00
            WHEN soi.name LIKE '%%super%%' THEN 269.00
            WHEN soi.name LIKE '%%vip%%' THEN 199.99
            ELSE 0 END
        + COALESCE(so.base_discount_invoiced, 0) * (soi.price / NULLIF(so.base_subtotal, 1))
        - CASE WHEN cg.customer_group_id = 4 THEN 0
            WHEN COALESCE(soiaa.price, 0) = 14.90 AND cg.customer_group_id IN (0, 1, 2, 3, 5, 7) THEN 14.90
            ELSE 0 END)
    ELSE 0 END) AS receita
FROM sales_order AS so
INNER JOIN sales_order_item AS soi ON soi.order_id = so.entity_id AND soi.product_type = 'bundle'
INNER JOIN catalog_product_entity_varchar cpev1
       ON cpev1.entity_id = soi.product_id AND cpev1.attribute_id = 321 AND cpev1.store_id = 0
LEFT JOIN customer_group AS cg ON cg.customer_group_id = so.customer_group_id
LEFT JOIN (SELECT parent_item_id, MAX(price) AS price FROM sales_order_item WHERE name LIKE '%%persona%%' GROUP BY parent_item_id) AS soiaa ON soiaa.parent_item_id = soi.item_id
WHERE
    so.increment_id NOT REGEXP '-[0-9]'
    AND so.status IN ('processing', 'complete', 'approved', 'aprovado_link', 'reembolso_parcial', 'closed', 'retirado')
    AND so.state != 'canceled'
    AND cpev1.value IN :magento_event_ids
GROUP BY MONTH(so.created_at)
ORDER BY mes
""").bindparams(bindparam("magento_event_ids", expanding=True))
        with db_module.engine_magento.connect() as conn:
            result = conn.execute(query, {"magento_event_ids": safe_ids})
            return [{"mes": int(r[0]), "qtd": int(r[1] or 0), "receita": float(r[2] or 0)} for r in result.fetchall()]
    except Exception as e:
        logger.error(f"Erro monthly sales Magento by IDs: {e}")
        return []


def _fetch_daily_sales_ativo_by_ids_grouped(id_eventos: list) -> dict:
    if not id_eventos:
        return {}
    if _is_warmup_thread():
        with _warmup_daily_cache_lock:
            ativo_cache = _warmup_daily_cache.get("ativo")
        if ativo_cache is not None:
            safe_ids = [str(int(i)) for i in id_eventos if str(i).isdigit()]
            result = {}
            for eid in safe_ids:
                if eid in ativo_cache:
                    result[eid] = dict(ativo_cache[eid])
            if result:
                return result
    if db_module.engine_ssh is None:
        return {}
    try:
        safe_ids = [str(int(i)) for i in id_eventos if str(i).isdigit()]
        if not safe_ids:
            return {}
        query = text("""
SELECT /*+ MAX_EXECUTION_TIME(90000) */
    sub.id_evento,
    sub.dia,
    SUM(sub.qtd) AS qtd
FROM (
    SELECT
        b.id_evento,
        DATE(c.dt_pedido) AS dia,
        CASE
            WHEN cupom.en_cupom_classificacao IN (
                     'Funcionário', 'Cortesia Faturada',
                     'Coligados', 'Eventos Terceiros'
                 )                                                     THEN 'Cortesia'
            WHEN cupom.en_cupom_classificacao = 'Grupos'               THEN 'Grupos/B2B'
            WHEN h.ds_categoria LIKE '%%Grup%%'                        THEN 'Grupos/B2B'
            ELSE                                                           'Site'
        END AS canal,
        COUNT(DISTINCT a.id_pedido_evento) AS qtd
    FROM sa_pedido_evento AS a
    INNER JOIN sa_evento AS b ON b.id_evento = a.id_evento
    INNER JOIN sa_pedido AS c
        ON c.id_pedido = a.id_pedido
       AND c.fl_local_inscricao = '1'
       AND c.id_pedido_status IN (1, 2)
    LEFT JOIN sa_modalidade_categoria AS h ON h.id_categoria = a.id_categoria
    LEFT JOIN (
        SELECT e.id_cupom_desconto_item, f.en_cupom_classificacao
        FROM sa_cupom_desconto_item AS e
        INNER JOIN sa_cupom_desconto AS f ON f.id_cupom_desconto = e.id_cupom_desconto
    ) AS cupom ON cupom.id_cupom_desconto_item = a.id_cupom_individual
    WHERE
        (b.id_campanha_salesforce IS NULL OR b.id_campanha_salesforce NOT LIKE '701d0000000%%')
        AND b.id_evento IN :id_eventos
        AND c.dt_pedido < CURDATE() + INTERVAL 1 DAY
    GROUP BY b.id_evento, DATE(c.dt_pedido),
             CASE WHEN cupom.en_cupom_classificacao IN ('Funcionário', 'Cortesia Faturada', 'Coligados', 'Eventos Terceiros') THEN 'Cortesia'
                  WHEN cupom.en_cupom_classificacao = 'Grupos' THEN 'Grupos/B2B'
                  WHEN h.ds_categoria LIKE '%%Grup%%' THEN 'Grupos/B2B'
                  ELSE 'Site' END
) AS sub
WHERE sub.canal = 'Site'
GROUP BY sub.id_evento, sub.dia
ORDER BY sub.id_evento, sub.dia
""").bindparams(bindparam("id_eventos", expanding=True))
        with db_module.engine_ssh.connect() as conn:
            result = conn.execute(query, {"id_eventos": [int(i) for i in safe_ids]})
            grouped = {}
            for r in result.fetchall():
                eid = str(r[0])
                d_str = str(r[1])
                qtd = int(r[2] or 0)
                if eid not in grouped:
                    grouped[eid] = {}
                d = date.fromisoformat(d_str)
                grouped[eid][d] = grouped[eid].get(d, 0) + qtd
            return grouped
    except Exception as e:
        logger.error(f"Erro daily sales Ativo grouped: {e}")
        return {}


def _fetch_daily_sales_magento_by_ids_grouped(magento_event_ids: list, cortesia_magento_ids: Optional[set] = None) -> dict:
    if not magento_event_ids:
        return {}
    cort_ids = cortesia_magento_ids or set()
    if not cort_ids and _is_warmup_thread():
        with _warmup_daily_cache_lock:
            magento_cache = _warmup_daily_cache.get("magento")
        if magento_cache is not None:
            safe_ids = [str(int(i)) for i in magento_event_ids if str(i).isdigit()]
            result = {}
            for lid in safe_ids:
                if lid in magento_cache:
                    result[lid] = dict(magento_cache[lid])
            if result:
                return result
    if db_module.engine_magento is None:
        return {}
    try:
        safe_ids = [int(i) for i in magento_event_ids if str(i).isdigit()]
        if not safe_ids:
            return {}
        if cort_ids:
            safe_cort_ids = [int(i) for i in cort_ids if str(i).isdigit()]
            _cort_cond = """CASE WHEN (cpev1.value IN :cort_ids
        AND (so.discount_description IS NULL OR so.discount_description NOT LIKE '%%GRUPOS%%')
        AND (so.coupon_code IS NULL OR so.coupon_code NOT LIKE 'GRUP%%'))
        OR (so.base_grand_total > 0
        AND NOT (so.discount_description LIKE '%%CORTESIA%%' AND so.base_grand_total < 50)
        AND (so.discount_description IS NULL OR so.discount_description NOT LIKE '%%GRUPOS%%')
        AND (so.coupon_code IS NULL OR so.coupon_code NOT LIKE 'GRUP%%'))
        THEN 1 END"""
        else:
            safe_cort_ids = None
            _cort_cond = """CASE WHEN so.base_grand_total > 0
        AND NOT (so.discount_description LIKE '%%CORTESIA%%' AND so.base_grand_total < 50)
        AND (so.discount_description IS NULL OR so.discount_description NOT LIKE '%%GRUPOS%%')
        AND (so.coupon_code IS NULL OR so.coupon_code NOT LIKE 'GRUP%%')
        THEN 1 END"""
        query = text(f"""
SELECT /*+ MAX_EXECUTION_TIME(90000) */
    cpev1.value AS id_evento,
    DATE(so.created_at) AS dia,
    COUNT({_cort_cond}) AS qtd
FROM sales_order so
INNER JOIN sales_order_item soi_parent
       ON soi_parent.order_id     = so.entity_id
      AND soi_parent.product_type = 'bundle'
INNER JOIN catalog_product_entity_varchar cpev1
       ON cpev1.entity_id    = soi_parent.product_id
      AND cpev1.attribute_id = 321
      AND cpev1.store_id     = 0
WHERE
    so.status IN ('processing', 'complete', 'approved', 'aprovado_link', 'reembolso_parcial', 'closed', 'retirado')
    AND so.state != 'canceled'
    AND cpev1.value IN :magento_event_ids
    AND so.increment_id NOT REGEXP '-[0-9]'
    AND so.created_at < CURDATE() + INTERVAL 1 DAY
GROUP BY cpev1.value, DATE(so.created_at)
ORDER BY cpev1.value, dia
""")
        if safe_cort_ids is not None:
            query = query.bindparams(
                bindparam("magento_event_ids", expanding=True),
                bindparam("cort_ids", expanding=True),
            )
            exec_params = {"magento_event_ids": safe_ids, "cort_ids": safe_cort_ids}
        else:
            query = query.bindparams(bindparam("magento_event_ids", expanding=True))
            exec_params = {"magento_event_ids": safe_ids}
        with db_module.engine_magento.connect() as conn:
            result = conn.execute(query, exec_params)
            grouped = {}
            for r in result.fetchall():
                lid = str(r[0])
                d_str = str(r[1])
                qtd = int(r[2] or 0)
                if lid not in grouped:
                    grouped[lid] = {}
                d = date.fromisoformat(d_str)
                grouped[lid][d] = grouped[lid].get(d, 0) + qtd
            return grouped
    except Exception as e:
        logger.error(f"Erro daily sales Magento grouped: {e}")
        return {}


def _fetch_daily_sales_ativo_by_ids(id_eventos: list) -> list:
    if not id_eventos:
        return []
    if _is_warmup_thread():
        with _warmup_daily_cache_lock:
            ativo_cache = _warmup_daily_cache.get("ativo")
        if ativo_cache is not None:
            safe_ids = [str(int(i)) for i in id_eventos if str(i).isdigit()]
            combined = {}
            for eid in safe_ids:
                if eid in ativo_cache:
                    for d, qtd in ativo_cache[eid].items():
                        combined[d] = combined.get(d, 0) + qtd
            if combined:
                return [{"dia": d.isoformat() if hasattr(d, 'isoformat') else str(d), "qtd": qtd, "receita": 0} for d, qtd in sorted(combined.items())]
    if db_module.engine_ssh is None:
        return []
    try:
        safe_ids = [int(i) for i in id_eventos if str(i).isdigit()]
        if not safe_ids:
            return []
        query = text("""
SELECT /*+ MAX_EXECUTION_TIME(90000) */
    sub.dia,
    SUM(sub.qtd)     AS qtd,
    SUM(sub.receita) AS receita
FROM (
    SELECT
        DATE(c.dt_pedido) AS dia,
        CASE
            WHEN cupom.en_cupom_classificacao IN (
                     'Funcionário', 'Cortesia Faturada',
                     'Coligados', 'Eventos Terceiros'
                 )                                                     THEN 'Cortesia'
            WHEN cupom.en_cupom_classificacao = 'Grupos'               THEN 'Grupos/B2B'
            WHEN h.ds_categoria LIKE '%%Grup%%'                        THEN 'Grupos/B2B'
            ELSE                                                           'Site'
        END AS canal,
        COUNT(DISTINCT a.id_pedido_evento) AS qtd,
        SUM(GREATEST(
            CASE
                WHEN cupom.en_cupom_classificacao IN (
                         'Funcionário', 'Cortesia Faturada', 'Coligados', 'Eventos Terceiros'
                     ) THEN 0
                ELSE a.nr_preco - COALESCE(a.nr_desconto_individual, 0)
            END
        , 0)) AS receita
    FROM sa_pedido_evento AS a
    INNER JOIN sa_evento AS b ON b.id_evento = a.id_evento
    INNER JOIN sa_pedido AS c
        ON c.id_pedido = a.id_pedido
       AND c.fl_local_inscricao = '1'
       AND c.id_pedido_status IN (1, 2)
    LEFT JOIN sa_modalidade_categoria AS h ON h.id_categoria = a.id_categoria
    LEFT JOIN (
        SELECT e.id_cupom_desconto_item, f.en_cupom_classificacao
        FROM sa_cupom_desconto_item AS e
        INNER JOIN sa_cupom_desconto AS f ON f.id_cupom_desconto = e.id_cupom_desconto
    ) AS cupom ON cupom.id_cupom_desconto_item = a.id_cupom_individual
    WHERE
        b.id_evento IN :id_eventos
        AND (b.id_campanha_salesforce IS NULL OR b.id_campanha_salesforce NOT LIKE '701d0000000%%')
        AND c.dt_pedido < CURDATE() + INTERVAL 1 DAY
    GROUP BY DATE(c.dt_pedido),
             CASE WHEN cupom.en_cupom_classificacao IN ('Funcionário', 'Cortesia Faturada', 'Coligados', 'Eventos Terceiros') THEN 'Cortesia'
                  WHEN cupom.en_cupom_classificacao = 'Grupos' THEN 'Grupos/B2B'
                  WHEN h.ds_categoria LIKE '%%Grup%%' THEN 'Grupos/B2B'
                  ELSE 'Site' END
) AS sub
WHERE sub.canal = 'Site'
GROUP BY sub.dia
ORDER BY sub.dia
""").bindparams(bindparam("id_eventos", expanding=True))
        with db_module.engine_ssh.connect() as conn:
            result = conn.execute(query, {"id_eventos": safe_ids})
            return [{"dia": str(r[0]), "qtd": int(r[1] or 0), "receita": float(r[2] or 0)} for r in result.fetchall()]
    except Exception as e:
        logger.error(f"Erro daily sales Ativo by IDs: {e}")
        return []


def _fetch_today_sales_ativo_by_ids(id_eventos: list) -> dict:
    if not id_eventos or db_module.engine_ssh is None:
        return {}
    try:
        safe_ids = [int(i) for i in id_eventos if str(i).isdigit()]
        if not safe_ids:
            return {}
        query = text("""
SELECT /*+ MAX_EXECUTION_TIME(30000) */
    sub.dia,
    SUM(sub.qtd) AS qtd
FROM (
    SELECT
        DATE(c.dt_pedido) AS dia,
        CASE
            WHEN cupom.en_cupom_classificacao IN (
                     'Funcionário', 'Cortesia Faturada',
                     'Coligados', 'Eventos Terceiros'
                 )                                                     THEN 'Cortesia'
            WHEN cupom.en_cupom_classificacao = 'Grupos'               THEN 'Grupos/B2B'
            WHEN h.ds_categoria LIKE '%%Grup%%'                        THEN 'Grupos/B2B'
            ELSE                                                           'Site'
        END AS canal,
        COUNT(DISTINCT a.id_pedido_evento) AS qtd
    FROM sa_pedido_evento AS a
    INNER JOIN sa_evento AS b ON b.id_evento = a.id_evento
    INNER JOIN sa_pedido AS c
        ON c.id_pedido = a.id_pedido
       AND c.fl_local_inscricao = '1'
       AND c.id_pedido_status IN (1, 2)
    LEFT JOIN sa_modalidade_categoria AS h ON h.id_categoria = a.id_categoria
    LEFT JOIN (
        SELECT e.id_cupom_desconto_item, f.en_cupom_classificacao
        FROM sa_cupom_desconto_item AS e
        INNER JOIN sa_cupom_desconto AS f ON f.id_cupom_desconto = e.id_cupom_desconto
    ) AS cupom ON cupom.id_cupom_desconto_item = a.id_cupom_individual
    WHERE
        b.id_evento IN :id_eventos
        AND (b.id_campanha_salesforce IS NULL OR b.id_campanha_salesforce NOT LIKE '701d0000000%%')
        AND DATE(c.dt_pedido) = CURDATE()
    GROUP BY DATE(c.dt_pedido),
             CASE WHEN cupom.en_cupom_classificacao IN ('Funcionário', 'Cortesia Faturada', 'Coligados', 'Eventos Terceiros') THEN 'Cortesia'
                  WHEN cupom.en_cupom_classificacao = 'Grupos' THEN 'Grupos/B2B'
                  WHEN h.ds_categoria LIKE '%%Grup%%' THEN 'Grupos/B2B'
                  ELSE 'Site' END
) AS sub
WHERE sub.canal = 'Site'
GROUP BY sub.dia
""").bindparams(bindparam("id_eventos", expanding=True))
        with db_module.engine_ssh.connect() as conn:
            result = conn.execute(query, {"id_eventos": safe_ids})
            rows = result.fetchall()
            daily = {}
            for r in rows:
                d = date.fromisoformat(str(r[0])) if isinstance(r[0], str) else r[0]
                daily[d] = daily.get(d, 0) + int(r[1] or 0)
            return daily
    except Exception as e:
        logger.error(f"Erro today sales Ativo by IDs: {e}")
        return {}


def _fetch_today_sales_magento_by_ids(magento_event_ids: list, cortesia_magento_ids: Optional[set] = None) -> dict:
    if not magento_event_ids or db_module.engine_magento is None:
        return {}
    try:
        safe_ids = [str(int(i)) for i in magento_event_ids if str(i).isdigit()]
        if not safe_ids:
            return {}
        cort_ids = cortesia_magento_ids or set()
        if cort_ids:
            safe_cort_ids = [str(int(i)) for i in cort_ids if str(i).isdigit()]
            cort_str = ", ".join(safe_cort_ids)
            _cort_cond = f"""CASE WHEN (cpev1.value IN ({cort_str})
        AND (so.discount_description IS NULL OR so.discount_description NOT LIKE '%%GRUPOS%%')
        AND (so.coupon_code IS NULL OR so.coupon_code NOT LIKE 'GRUP%%'))
        OR (so.base_grand_total > 0
        AND NOT (so.discount_description LIKE '%%CORTESIA%%' AND so.base_grand_total < 50)
        AND (so.discount_description IS NULL OR so.discount_description NOT LIKE '%%GRUPOS%%')
        AND (so.coupon_code IS NULL OR so.coupon_code NOT LIKE 'GRUP%%')
        AND soi.price > 0) THEN 1 END"""
        else:
            _cort_cond = """CASE WHEN so.base_grand_total > 0
        AND NOT (so.discount_description LIKE '%%CORTESIA%%' AND so.base_grand_total < 50)
        AND (so.discount_description IS NULL OR so.discount_description NOT LIKE '%%GRUPOS%%')
        AND (so.coupon_code IS NULL OR so.coupon_code NOT LIKE 'GRUP%%')
        AND soi.price > 0 THEN 1 END"""
        query = text(f"""
SELECT /*+ MAX_EXECUTION_TIME(30000) */
    DATE(so.created_at) AS dia,
    COUNT({_cort_cond}) AS qtd
FROM sales_order so
INNER JOIN sales_order_item soi
       ON soi.order_id = so.entity_id
      AND soi.product_type = 'bundle'
INNER JOIN catalog_product_entity_varchar cpev1
       ON cpev1.entity_id = soi.product_id
      AND cpev1.attribute_id = 321
      AND cpev1.store_id = 0
WHERE
    so.status IN ('processing', 'complete', 'approved', 'aprovado_link', 'reembolso_parcial', 'closed', 'retirado')
    AND so.state != 'canceled'
    AND cpev1.value IN :magento_event_ids
    AND so.increment_id NOT REGEXP '-[0-9]'
    AND DATE(so.created_at) = CURDATE()
GROUP BY DATE(so.created_at)
""").bindparams(bindparam("magento_event_ids", expanding=True))
        with db_module.engine_magento.connect() as conn:
            result = conn.execute(query, {"magento_event_ids": safe_ids})
            rows = result.fetchall()
            daily = {}
            for r in rows:
                d = date.fromisoformat(str(r[0])) if isinstance(r[0], str) else r[0]
                daily[d] = daily.get(d, 0) + int(r[1] or 0)
            return daily
    except Exception as e:
        logger.error(f"Erro today sales Magento by IDs: {e}")
        return {}


def _fetch_today_sales_ativo_grouped(id_eventos: list) -> dict:
    """
    Single-query batch for today's Ativo sales grouped by id_evento.
    Returns {str(id_evento): {"qtd": int, "receita": float}}.
    """
    if not id_eventos or db_module.engine_ssh is None:
        return {}
    try:
        safe_ids = [int(i) for i in id_eventos if str(i).isdigit()]
        if not safe_ids:
            return {}
        query = text("""
SELECT /*+ MAX_EXECUTION_TIME(30000) */
    sub.id_evento,
    SUM(sub.qtd)     AS qtd,
    SUM(sub.receita) AS receita
FROM (
    SELECT
        b.id_evento,
        CASE
            WHEN a.nr_preco = 0                                        THEN 'Cortesia'
            WHEN cupom.en_cupom_classificacao IN (
                     'Funcionário', 'Cortesia Faturada',
                     'Coligados', 'Eventos Terceiros'
                 )                                                     THEN 'Cortesia'
            WHEN cupom.en_cupom_classificacao = 'Grupos'               THEN 'Grupos/B2B'
            WHEN h.ds_categoria LIKE '%%Grup%%'                        THEN 'Grupos/B2B'
            ELSE                                                           'Site'
        END AS canal,
        COUNT(DISTINCT a.id_pedido_evento) AS qtd,
        SUM(GREATEST(
            CASE
                WHEN a.nr_preco = 0 OR cupom.en_cupom_classificacao IN (
                         'Funcionário', 'Cortesia Faturada', 'Coligados', 'Eventos Terceiros'
                     ) THEN 0
                ELSE a.nr_preco - COALESCE(a.nr_desconto_individual, 0)
            END
        , 0)) AS receita
    FROM sa_pedido_evento AS a
    INNER JOIN sa_evento AS b ON b.id_evento = a.id_evento
    INNER JOIN sa_pedido AS c
        ON c.id_pedido = a.id_pedido
       AND c.fl_local_inscricao = '1'
       AND c.id_pedido_status IN (1, 2)
    LEFT JOIN sa_modalidade_categoria AS h ON h.id_categoria = a.id_categoria
    LEFT JOIN (
        SELECT e.id_cupom_desconto_item, f.en_cupom_classificacao
        FROM sa_cupom_desconto_item AS e
        INNER JOIN sa_cupom_desconto AS f ON f.id_cupom_desconto = e.id_cupom_desconto
    ) AS cupom ON cupom.id_cupom_desconto_item = a.id_cupom_individual
    WHERE
        b.id_evento IN :id_eventos
        AND (b.id_campanha_salesforce IS NULL OR b.id_campanha_salesforce NOT LIKE '701d0000000%%')
        AND DATE(c.dt_pedido) = CURDATE()
    GROUP BY b.id_evento,
             CASE WHEN a.nr_preco = 0 THEN 'Cortesia'
                  WHEN cupom.en_cupom_classificacao IN ('Funcionário', 'Cortesia Faturada', 'Coligados', 'Eventos Terceiros') THEN 'Cortesia'
                  WHEN cupom.en_cupom_classificacao = 'Grupos' THEN 'Grupos/B2B'
                  WHEN h.ds_categoria LIKE '%%Grup%%' THEN 'Grupos/B2B'
                  ELSE 'Site' END
) AS sub
WHERE sub.canal = 'Site'
GROUP BY sub.id_evento
""").bindparams(bindparam("id_eventos", expanding=True))
        with db_module.engine_ssh.connect() as conn:
            result = conn.execute(query, {"id_eventos": safe_ids})
            grouped = {}
            for r in result.fetchall():
                grouped[str(r[0])] = {"qtd": int(r[1] or 0), "receita": float(r[2] or 0.0)}
            return grouped
    except Exception as e:
        logger.error(f"Erro today sales Ativo grouped: {e}")
        return {}


def _fetch_today_sales_magento_grouped(magento_event_ids: list, cortesia_magento_ids: Optional[set] = None) -> dict:
    """
    Single-query batch for today's Magento sales grouped by id_evento.
    Returns {str(id_evento): {"qtd": int, "receita": float}}.
    Uses the same revenue formula as _fetch_daily_sales_magento_by_ids
    (kit-type adjustments + persona discount + group filter) for consistency.
    """
    if not magento_event_ids or db_module.engine_magento is None:
        return {}
    try:
        safe_ids = [str(int(i)) for i in magento_event_ids if str(i).isdigit()]
        if not safe_ids:
            return {}
        cort_ids = cortesia_magento_ids or set()
        if cort_ids:
            safe_cort_ids = [str(int(i)) for i in cort_ids if str(i).isdigit()]
            cort_str = ", ".join(safe_cort_ids)
            cort_qtd_cond = f"""CASE WHEN (cpev1.value IN ({cort_str})
        AND (so.discount_description IS NULL OR so.discount_description NOT LIKE '%%GRUPOS%%')
        AND (so.coupon_code IS NULL OR so.coupon_code NOT LIKE 'GRUP%%'))
        OR (so.base_grand_total > 0
        AND NOT (so.discount_description LIKE '%%CORTESIA%%' AND so.base_grand_total < 50)
        AND (so.discount_description IS NULL OR so.discount_description NOT LIKE '%%GRUPOS%%')
        AND (so.coupon_code IS NULL OR so.coupon_code NOT LIKE 'GRUP%%')
        AND soi.price > 0) THEN 1 END"""
            cort_rev_cond = f"""CASE WHEN (cpev1.value IN ({cort_str})
        AND (so.discount_description IS NULL OR so.discount_description NOT LIKE '%%GRUPOS%%')
        AND (so.coupon_code IS NULL OR so.coupon_code NOT LIKE 'GRUP%%'))
        OR (so.base_grand_total > 0
        AND NOT (so.discount_description LIKE '%%CORTESIA%%' AND so.base_grand_total < 50)
        AND (so.discount_description IS NULL OR so.discount_description NOT LIKE '%%GRUPOS%%')
        AND (so.coupon_code IS NULL OR so.coupon_code NOT LIKE 'GRUP%%')
        AND soi.price > 0) THEN"""
        else:
            cort_qtd_cond = """CASE WHEN so.base_grand_total > 0
        AND NOT (so.discount_description LIKE '%%CORTESIA%%' AND so.base_grand_total < 50)
        AND (so.discount_description IS NULL OR so.discount_description NOT LIKE '%%GRUPOS%%')
        AND (so.coupon_code IS NULL OR so.coupon_code NOT LIKE 'GRUP%%')
        AND soi.price > 0 THEN 1 END"""
            cort_rev_cond = """CASE WHEN so.base_grand_total > 0
        AND NOT (so.discount_description LIKE '%%CORTESIA%%' AND so.base_grand_total < 50)
        AND (so.discount_description IS NULL OR so.discount_description NOT LIKE '%%GRUPOS%%')
        AND (so.coupon_code IS NULL OR so.coupon_code NOT LIKE 'GRUP%%')
        AND soi.price > 0 THEN"""
        query = text(f"""
SELECT /*+ MAX_EXECUTION_TIME(30000) */
    cpev1.value AS id_evento,
    COUNT({cort_qtd_cond}) AS qtd,
    SUM({cort_rev_cond}
        soi.price
        - CASE WHEN soi.price = 0 THEN 0
            WHEN soi.name LIKE '%%plus%%' THEN 69.00
            WHEN soi.name LIKE '%%super%%' THEN 269.00
            WHEN soi.name LIKE '%%vip%%' THEN 199.99
            ELSE 0 END
        + COALESCE(so.base_discount_invoiced, 0) * (soi.price / NULLIF(so.base_subtotal, 1))
        - CASE WHEN cg.customer_group_id = 4 THEN 0
            WHEN COALESCE(soiaa.price, 0) = 14.90 AND cg.customer_group_id IN (0, 1, 2, 3, 5, 7) THEN 14.90
            ELSE 0 END
    ELSE 0 END) AS receita
FROM sales_order so
INNER JOIN sales_order_item soi
       ON soi.order_id = so.entity_id
      AND soi.product_type = 'bundle'
INNER JOIN catalog_product_entity_varchar cpev1
       ON cpev1.entity_id = soi.product_id
      AND cpev1.attribute_id = 321
      AND cpev1.store_id = 0
LEFT JOIN customer_group cg
       ON cg.customer_group_id = so.customer_group_id
LEFT JOIN (
    SELECT parent_item_id, MAX(price) AS price FROM sales_order_item WHERE name LIKE '%%persona%%' GROUP BY parent_item_id
) AS soiaa ON soiaa.parent_item_id = soi.item_id
WHERE
    so.status IN ('processing', 'complete', 'approved', 'aprovado_link', 'reembolso_parcial', 'closed', 'retirado')
    AND so.state != 'canceled'
    AND cpev1.value IN :magento_event_ids
    AND so.increment_id NOT REGEXP '-[0-9]'
    AND DATE(so.created_at) = CURDATE()
GROUP BY cpev1.value
""").bindparams(bindparam("magento_event_ids", expanding=True))
        with db_module.engine_magento.connect() as conn:
            result = conn.execute(query, {"magento_event_ids": safe_ids})
            grouped = {}
            for r in result.fetchall():
                grouped[str(r[0])] = {"qtd": int(r[1] or 0), "receita": float(r[2] or 0.0)}
            return grouped
    except Exception as e:
        logger.error(f"Erro today sales Magento grouped: {e}")
        return {}


def _fetch_daily_sales_magento_by_ids(magento_event_ids: list, cortesia_magento_ids: Optional[set] = None) -> list:
    if not magento_event_ids:
        return []
    cort_ids = cortesia_magento_ids or set()
    if not cort_ids and _is_warmup_thread():
        with _warmup_daily_cache_lock:
            magento_cache = _warmup_daily_cache.get("magento")
        if magento_cache is not None:
            safe_ids = [str(int(i)) for i in magento_event_ids if str(i).isdigit()]
            combined = {}
            for lid in safe_ids:
                if lid in magento_cache:
                    for d, qtd in magento_cache[lid].items():
                        combined[d] = combined.get(d, 0) + qtd
            if combined:
                return [{"dia": d.isoformat() if hasattr(d, 'isoformat') else str(d), "qtd": qtd, "receita": 0} for d, qtd in sorted(combined.items())]
    if db_module.engine_magento is None:
        return []
    try:
        safe_ids = [str(int(i)) for i in magento_event_ids if str(i).isdigit()]
        if not safe_ids:
            return []
        if cort_ids:
            safe_cort_ids = [str(int(i)) for i in cort_ids if str(i).isdigit()]
            _cort_qtd_cond = """CASE WHEN (cpev1.value IN :cort_ids
        AND (so.discount_description IS NULL OR so.discount_description NOT LIKE '%%GRUPOS%%')
        AND (so.coupon_code IS NULL OR so.coupon_code NOT LIKE 'GRUP%%'))
        OR (so.base_grand_total > 0
        AND NOT (so.discount_description LIKE '%%CORTESIA%%' AND so.base_grand_total < 50)
        AND (so.discount_description IS NULL OR so.discount_description NOT LIKE '%%GRUPOS%%')
        AND (so.coupon_code IS NULL OR so.coupon_code NOT LIKE 'GRUP%%')
        AND soi.price > 0) THEN 1 END"""
            _cort_rev_cond = """CASE WHEN (cpev1.value IN :cort_ids
        AND (so.discount_description IS NULL OR so.discount_description NOT LIKE '%%GRUPOS%%')
        AND (so.coupon_code IS NULL OR so.coupon_code NOT LIKE 'GRUP%%'))
        OR (so.base_grand_total > 0
        AND NOT (so.discount_description LIKE '%%CORTESIA%%' AND so.base_grand_total < 50)
        AND (so.discount_description IS NULL OR so.discount_description NOT LIKE '%%GRUPOS%%')
        AND (so.coupon_code IS NULL OR so.coupon_code NOT LIKE 'GRUP%%')
        AND soi.price > 0) THEN"""
        else:
            _cort_qtd_cond = """CASE WHEN so.base_grand_total > 0
        AND NOT (so.discount_description LIKE '%%CORTESIA%%' AND so.base_grand_total < 50)
        AND (so.discount_description IS NULL OR so.discount_description NOT LIKE '%%GRUPOS%%')
        AND (so.coupon_code IS NULL OR so.coupon_code NOT LIKE 'GRUP%%')
        AND soi.price > 0 THEN 1 END"""
            _cort_rev_cond = """CASE WHEN so.base_grand_total > 0
        AND NOT (so.discount_description LIKE '%%CORTESIA%%' AND so.base_grand_total < 50)
        AND (so.discount_description IS NULL OR so.discount_description NOT LIKE '%%GRUPOS%%')
        AND (so.coupon_code IS NULL OR so.coupon_code NOT LIKE 'GRUP%%')
        AND soi.price > 0 THEN"""
        query = text(f"""
SELECT /*+ MAX_EXECUTION_TIME(90000) */
    DATE(so.created_at) AS dia,
    COUNT({_cort_qtd_cond}) AS qtd,
    SUM({_cort_rev_cond}
        soi.price
        - CASE WHEN soi.price = 0 THEN 0
            WHEN soi.name LIKE '%%plus%%' THEN 69.00
            WHEN soi.name LIKE '%%super%%' THEN 269.00
            WHEN soi.name LIKE '%%vip%%' THEN 199.99
            ELSE 0 END
        + COALESCE(so.base_discount_invoiced, 0) * (soi.price / NULLIF(so.base_subtotal, 1))
        - CASE WHEN cg.customer_group_id = 4 THEN 0
            WHEN COALESCE(soiaa.price, 0) = 14.90 AND cg.customer_group_id IN (0, 1, 2, 3, 5, 7) THEN 14.90
            ELSE 0 END
    ELSE 0 END) AS receita
FROM sales_order so
INNER JOIN sales_order_item soi
       ON soi.order_id = so.entity_id
      AND soi.product_type = 'bundle'
INNER JOIN catalog_product_entity_varchar cpev1
       ON cpev1.entity_id = soi.product_id
      AND cpev1.attribute_id = 321
      AND cpev1.store_id = 0
LEFT JOIN customer_group cg
       ON cg.customer_group_id = so.customer_group_id
LEFT JOIN (
    SELECT parent_item_id, MAX(price) AS price FROM sales_order_item WHERE name LIKE '%%persona%%' GROUP BY parent_item_id
) AS soiaa ON soiaa.parent_item_id = soi.item_id
WHERE
    so.status IN ('processing', 'complete', 'approved', 'aprovado_link', 'reembolso_parcial', 'closed', 'retirado')
    AND so.state != 'canceled'
    AND cpev1.value IN :magento_event_ids
    AND so.increment_id NOT REGEXP '-[0-9]'
    AND so.created_at < CURDATE() + INTERVAL 1 DAY
GROUP BY DATE(so.created_at)
ORDER BY dia
""")
        bp = [bindparam("magento_event_ids", expanding=True)]
        params = {"magento_event_ids": safe_ids}
        if cort_ids:
            bp.append(bindparam("cort_ids", expanding=True))
            params["cort_ids"] = safe_cort_ids
        query = query.bindparams(*bp)
        with db_module.engine_magento.connect() as conn:
            result = conn.execute(query, params)
            return [{"dia": str(r[0]), "qtd": int(r[1] or 0), "receita": float(r[2] or 0)} for r in result.fetchall()]
    except Exception as e:
        logger.error(f"Erro daily sales Magento by IDs: {e}")
        return []


def _fetch_category_sales_ativo_by_ids(id_eventos: list) -> list:
    if not id_eventos:
        return []
    if _is_warmup_thread():
        with _warmup_daily_cache_lock:
            cat_cache = _warmup_daily_cache.get("cat_ativo")
        if cat_cache is not None:
            safe_ids = [str(int(i)) for i in id_eventos if str(i).isdigit()]
            combined = {}
            for eid in safe_ids:
                if eid in cat_cache:
                    for cat, qtd in cat_cache[eid].items():
                        combined[cat] = combined.get(cat, 0) + qtd
            if combined:
                return [{"categoria": cat, "qtd": qtd} for cat, qtd in sorted(combined.items(), key=lambda x: -x[1])]
    if db_module.engine_ssh is None:
        return []
    try:
        safe_ids = [str(int(i)) for i in id_eventos if str(i).isdigit()]
        if not safe_ids:
            return []
        query = text("""
SELECT /*+ MAX_EXECUTION_TIME(90000) */
    h.ds_categoria AS categoria,
    COUNT(CASE WHEN (f.en_cupom_classificacao IS NULL
              OR f.en_cupom_classificacao NOT IN ('Funcionário', 'Cortesia Faturada', 'Grupos', 'Coligados', 'Eventos Terceiros'))
        AND (h.ds_categoria IS NULL OR (h.ds_categoria NOT LIKE '%%GRUPOS%%' AND h.ds_categoria NOT LIKE '%%ortesia%%'))
        AND c.nr_total > 0 THEN 1 END) AS qtd
FROM sa_pedido_evento AS a
INNER JOIN sa_evento AS b ON b.id_evento = a.id_evento
INNER JOIN sa_pedido AS c ON c.id_pedido = a.id_pedido
LEFT JOIN sa_modalidade_categoria AS h ON a.id_categoria = h.id_categoria
LEFT JOIN sa_cupom_desconto_item AS e ON e.id_cupom_desconto_item = a.id_cupom_individual
LEFT JOIN sa_cupom_desconto AS f ON f.id_cupom_desconto = e.id_cupom_desconto
WHERE 
    c.fl_local_inscricao = '1'
    AND c.id_pedido_status IN (1, 2)
    AND (b.id_campanha_salesforce IS NULL OR b.id_campanha_salesforce NOT LIKE '701d0000000%%')
    AND b.id_evento IN :id_eventos
GROUP BY h.ds_categoria
ORDER BY qtd DESC
""").bindparams(bindparam("id_eventos", expanding=True))
        with db_module.engine_ssh.connect() as conn:
            result = conn.execute(query, {"id_eventos": safe_ids})
            return [{"categoria": str(r[0] or "Sem categoria"), "qtd": int(r[1] or 0)} for r in result.fetchall()]
    except Exception as e:
        logger.error(f"Erro category sales Ativo by IDs: {e}")
        return []


def _fetch_category_sales_ativo_by_ids_grouped(id_eventos: list) -> dict:
    if db_module.engine_ssh is None or not id_eventos:
        return {}
    try:
        safe_ids = [str(int(i)) for i in id_eventos if str(i).isdigit()]
        if not safe_ids:
            return {}
        query = text("""
SELECT /*+ MAX_EXECUTION_TIME(90000) */
    b.id_evento,
    h.ds_categoria AS categoria,
    COUNT(CASE WHEN (f.en_cupom_classificacao IS NULL
              OR f.en_cupom_classificacao NOT IN ('Funcionário', 'Cortesia Faturada', 'Grupos', 'Coligados', 'Eventos Terceiros'))
        AND (h.ds_categoria IS NULL OR (h.ds_categoria NOT LIKE '%%GRUPOS%%' AND h.ds_categoria NOT LIKE '%%ortesia%%'))
        AND c.nr_total > 0 THEN 1 END) AS qtd
FROM sa_pedido_evento AS a
INNER JOIN sa_evento AS b ON b.id_evento = a.id_evento
INNER JOIN sa_pedido AS c ON c.id_pedido = a.id_pedido
LEFT JOIN sa_modalidade_categoria AS h ON a.id_categoria = h.id_categoria
LEFT JOIN sa_cupom_desconto_item AS e ON e.id_cupom_desconto_item = a.id_cupom_individual
LEFT JOIN sa_cupom_desconto AS f ON f.id_cupom_desconto = e.id_cupom_desconto
WHERE 
    c.fl_local_inscricao = '1'
    AND c.id_pedido_status IN (1, 2)
    AND (b.id_campanha_salesforce IS NULL OR b.id_campanha_salesforce NOT LIKE '701d0000000%%')
    AND b.id_evento IN :id_eventos
GROUP BY b.id_evento, h.ds_categoria
ORDER BY b.id_evento, qtd DESC
""").bindparams(bindparam("id_eventos", expanding=True))
        with db_module.engine_ssh.connect() as conn:
            result = conn.execute(query, {"id_eventos": [int(i) for i in safe_ids]})
            grouped = {}
            for r in result.fetchall():
                eid = str(r[0])
                cat = str(r[1] or "Sem categoria")
                qtd = int(r[2] or 0)
                if eid not in grouped:
                    grouped[eid] = {}
                grouped[eid][cat] = grouped[eid].get(cat, 0) + qtd
            return grouped
    except Exception as e:
        logger.error(f"Erro category sales Ativo grouped: {e}")
        return {}


def _fetch_category_sales_magento_by_ids_grouped(magento_event_ids: list) -> dict:
    if db_module.engine_magento is None or not magento_event_ids:
        return {}
    try:
        safe_ids = [int(i) for i in magento_event_ids if str(i).isdigit()]
        if not safe_ids:
            return {}
        query = text("""
SELECT
    cpev1.value AS event_id,
    soi.name AS categoria,
    COUNT(CASE WHEN so.base_grand_total > 0
        AND NOT (so.discount_description LIKE '%%CORTESIA%%' AND so.base_grand_total < 50)
        AND (so.discount_description IS NULL OR so.discount_description NOT LIKE '%%GRUPOS%%')
        AND (so.coupon_code IS NULL OR so.coupon_code NOT LIKE 'GRUP%%')
        AND soi.price > 0 THEN 1 END) AS qtd
FROM sales_order AS so
INNER JOIN sales_order_item AS soi ON soi.order_id = so.entity_id AND soi.product_type = 'bundle'
INNER JOIN catalog_product_entity_varchar cpev1 ON cpev1.entity_id = soi.product_id AND cpev1.attribute_id = 321 AND cpev1.store_id = 0
LEFT JOIN customer_group AS cg ON cg.customer_group_id = so.customer_group_id
WHERE
    so.increment_id NOT REGEXP '-[0-9]'
    AND so.status IN ('processing', 'complete', 'approved', 'aprovado_link', 'reembolso_parcial', 'closed', 'retirado')
    AND so.state != 'canceled'
    AND cpev1.value IN :magento_event_ids
GROUP BY cpev1.value, soi.name
ORDER BY cpev1.value, qtd DESC
""").bindparams(bindparam("magento_event_ids", expanding=True))
        with db_module.engine_magento.connect() as conn:
            result = conn.execute(query, {"magento_event_ids": safe_ids})
            grouped = {}
            for r in result.fetchall():
                lid = str(r[0])
                cat = str(r[1] or "Sem categoria")
                qtd = int(r[2] or 0)
                if lid not in grouped:
                    grouped[lid] = {}
                grouped[lid][cat] = grouped[lid].get(cat, 0) + qtd
            return grouped
    except Exception as e:
        logger.error(f"Erro category sales Magento grouped: {e}")
        return {}


def _fetch_category_sales_magento_by_ids(magento_event_ids: list) -> list:
    if not magento_event_ids:
        return []
    if _is_warmup_thread():
        with _warmup_daily_cache_lock:
            cat_cache = _warmup_daily_cache.get("cat_magento")
        if cat_cache is not None:
            safe_ids = [str(int(i)) for i in magento_event_ids if str(i).isdigit()]
            combined = {}
            for lid in safe_ids:
                if lid in cat_cache:
                    for cat, qtd in cat_cache[lid].items():
                        combined[cat] = combined.get(cat, 0) + qtd
            if combined:
                return [{"categoria": cat, "qtd": qtd} for cat, qtd in sorted(combined.items(), key=lambda x: -x[1])]
    if db_module.engine_magento is None:
        return []
    try:
        safe_ids = [int(i) for i in magento_event_ids if str(i).isdigit()]
        if not safe_ids:
            return []
        query = text("""
SELECT
    soi.name AS categoria,
    COUNT(CASE WHEN so.base_grand_total > 0
        AND NOT (so.discount_description LIKE '%%CORTESIA%%' AND so.base_grand_total < 50)
        AND (so.discount_description IS NULL OR so.discount_description NOT LIKE '%%GRUPOS%%')
        AND (so.coupon_code IS NULL OR so.coupon_code NOT LIKE 'GRUP%%')
        THEN 1 END) AS qtd
FROM sales_order AS so
INNER JOIN sales_order_item AS soi ON soi.order_id = so.entity_id AND soi.product_type = 'bundle'
INNER JOIN catalog_product_entity_varchar cpev1
       ON cpev1.entity_id = soi.product_id AND cpev1.attribute_id = 321 AND cpev1.store_id = 0
LEFT JOIN customer_group AS cg ON cg.customer_group_id = so.customer_group_id
WHERE
    so.increment_id NOT REGEXP '-[0-9]'
    AND so.status IN ('processing', 'complete', 'approved', 'aprovado_link', 'reembolso_parcial', 'closed', 'retirado')
    AND so.state != 'canceled'
    AND cpev1.value IN :magento_event_ids
GROUP BY soi.name
ORDER BY qtd DESC
""").bindparams(bindparam("magento_event_ids", expanding=True))
        with db_module.engine_magento.connect() as conn:
            result = conn.execute(query, {"magento_event_ids": safe_ids})
            return [{"categoria": str(r[0] or "Sem categoria"), "qtd": int(r[1] or 0)} for r in result.fetchall()]
    except Exception as e:
        logger.error(f"Erro category sales Magento by IDs: {e}")
        return []


import re as _re
import unicodedata as _unicodedata

def _normalize_name_for_match(name: str) -> str:
    s = _unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode('ascii')
    s = _re.sub(r'\d{4}', '', s)
    s = _re.sub(r'\s*-\s*', ' ', s)
    s = _re.sub(r'\s+\d+$', '', s.strip())
    s = _re.sub(r'\s+', ' ', s).strip().lower()
    return s

_hist_pattern_cache: dict = {}
_hist_curva_info_cache: dict = {}
_hist_pattern_cache_lock = _threading.Lock()

def _prefetch_all_historical_patterns(db: Session, grupo_names: list, ano: int) -> tuple:
    from ...models.dimensoes import SkuMapping
    prev_ano = ano - 1
    all_requested_names = list(grupo_names)
    if not grupo_names:
        return {}, {}

    cache_key = f"{ano}_hist_patterns"
    with _hist_pattern_cache_lock:
        cached = _hist_pattern_cache.get(cache_key)
    if cached is not None:
        filtered = {g: cached[g] for g in grupo_names if g in cached}
        uncached = [g for g in grupo_names if g not in cached]
        cached_ci = _hist_curva_info_cache.get(cache_key, {})
        if not uncached:
            curva_info_map = {gn: cached_ci.get(gn, {"tipo_curva": "historico", "fonte_curva": gn, "ano_referencia": prev_ano}) for gn in filtered}
            missing_from_cache = [g for g in all_requested_names if g not in filtered]
            mc_estado_map = {}
            for gn in missing_from_cache:
                estado_row = db.query(DimProjeto.estado).join(
                    SkuMapping, SkuMapping.sku == DimProjeto.codigo
                ).filter(
                    SkuMapping.evento_grupo == gn,
                    DimProjeto.estado.isnot(None)
                ).first()
                if estado_row:
                    mc_estado_map[gn] = estado_row[0]
            for gn in missing_from_cache:
                try:
                    estado = mc_estado_map.get(gn)
                    fb_pattern, fb_info = _resolve_hist_pattern(db, gn, ano, estado=estado)
                    if fb_pattern:
                        filtered[gn] = fb_pattern
                    curva_info_map[gn] = fb_info
                except Exception:
                    curva_info_map[gn] = {"tipo_curva": "linear", "fonte_curva": None, "ano_referencia": None}
            return filtered, curva_info_map
        grupo_names = uncached

    grupo_data_evento = {}
    grupo_mappings_map = {}
    all_prev_ativo_ids = []
    all_prev_magento_ids = []
    grupo_id_map = {}

    for grupo_nome in grupo_names:
        prev_data_evento = _find_data_evento(db, grupo_nome, prev_ano)
        if not prev_data_evento:
            continue
        grupo_data_evento[grupo_nome] = prev_data_evento

        prev_mappings = db.query(SkuMapping).filter(
            SkuMapping.evento_grupo == grupo_nome,
            SkuMapping.ano == prev_ano,
            SkuMapping.ativo == True
        ).all()

        if not prev_mappings:
            prev_skus_from_current = db.query(SkuMapping.sku).filter(
                SkuMapping.evento_grupo == grupo_nome,
                SkuMapping.ano == ano,
                SkuMapping.ativo == True
            ).distinct().all()
            prev_skus = [s[0] for s in prev_skus_from_current]
            if prev_skus:
                prev_mappings = db.query(SkuMapping).filter(
                    SkuMapping.sku.in_(prev_skus),
                    SkuMapping.ano == prev_ano,
                    SkuMapping.ativo == True
                ).all()

        if not prev_mappings:
            continue

        ativo_ids = []
        magento_ids = []
        for m in prev_mappings:
            if m.id_externo:
                ext_id = str(m.id_externo)
                if m.fonte == 'ATIVO':
                    ativo_ids.append(ext_id)
                    all_prev_ativo_ids.append(ext_id)
                    if ext_id not in grupo_id_map:
                        grupo_id_map[ext_id] = []
                    grupo_id_map[ext_id].append(('ATIVO', grupo_nome))
                elif m.fonte == 'MAGENTO':
                    magento_ids.append(ext_id)
                    all_prev_magento_ids.append(ext_id)
                    if ext_id not in grupo_id_map:
                        grupo_id_map[ext_id] = []
                    grupo_id_map[ext_id].append(('MAGENTO', grupo_nome))

        grupo_mappings_map[grupo_nome] = {'ativo': ativo_ids, 'magento': magento_ids}

    ativo_grouped = {}
    if all_prev_ativo_ids:
        try:
            ativo_grouped = _fetch_daily_sales_ativo_by_ids_grouped(list(set(all_prev_ativo_ids)))
        except Exception as e:
            logger.error(f"Batch historical Ativo fetch error: {e}")

    magento_grouped = {}
    if all_prev_magento_ids:
        try:
            _cort_batch = _get_cortesia_magento_ids(db)
            _mag_cort_batch = set(all_prev_magento_ids) & _cort_batch if _cort_batch else None
            magento_grouped = _fetch_daily_sales_magento_by_ids_grouped(list(set(all_prev_magento_ids)), cortesia_magento_ids=_mag_cort_batch if _mag_cort_batch else None)
        except Exception as e:
            logger.error(f"Batch historical Magento fetch error: {e}")

    result = {}
    for grupo_nome in grupo_names:
        if grupo_nome not in grupo_data_evento or grupo_nome not in grupo_mappings_map:
            continue

        prev_data_evento = grupo_data_evento[grupo_nome]
        ids_info = grupo_mappings_map[grupo_nome]

        prev_dias_enc = 2
        try:
            prev_proj = db.query(DimProjeto).filter(
                DimProjeto.data_evento == prev_data_evento
            ).first()
            if prev_proj:
                prev_dias_enc = get_dias_encerramento(db, projeto_id=prev_proj.id)
        except Exception:
            pass
        prev_data_inscricao = prev_data_evento - timedelta(days=prev_dias_enc)

        prev_daily = {}
        for eid in ids_info['ativo']:
            if eid in ativo_grouped:
                for d, qtd in ativo_grouped[eid].items():
                    prev_daily[d] = prev_daily.get(d, 0) + qtd
        for lid in ids_info['magento']:
            if lid in magento_grouped:
                for d, qtd in magento_grouped[lid].items():
                    prev_daily[d] = prev_daily.get(d, 0) + qtd

        if not prev_daily:
            continue

        total_prev_sales = sum(prev_daily.values())
        if total_prev_sales == 0:
            continue

        d_minus_sales = {}
        for sale_date, qty in prev_daily.items():
            dm = (prev_data_inscricao - sale_date).days
            d_minus_sales[dm] = d_minus_sales.get(dm, 0) + qty

        d_minus_sales = {dm: qty for dm, qty in d_minus_sales.items() if dm >= 0}
        if not d_minus_sales:
            continue

        max_dm = max(d_minus_sales.keys())
        min_dm = min(d_minus_sales.keys())

        cumulative = 0
        pattern = {}
        for dm in range(max_dm, min_dm - 1, -1):
            cumulative += d_minus_sales.get(dm, 0)
            pattern[dm] = cumulative / total_prev_sales

        if 0 not in pattern:
            pattern[0] = 1.0
        if min_dm > 0:
            for dm in range(min_dm - 1, -1, -1):
                pattern[dm] = 1.0

        logger.info(f"Batch: Built historical pattern for '{grupo_nome}' from ano={prev_ano}: {len(prev_daily)} sale days, total={total_prev_sales}, D- range [{min_dm}, {max_dm}]")
        result[grupo_nome] = pattern

    curva_info_map = {}
    for gn in list(result.keys()):
        curva_info_map[gn] = {
            "tipo_curva": "historico",
            "fonte_curva": gn,
            "ano_referencia": prev_ano
        }

    missing = [g for g in all_requested_names if g not in result]
    missing_estado_map = {}
    if missing:
        for gn in missing:
            estado_row = db.query(DimProjeto.estado).join(
                SkuMapping, SkuMapping.sku == DimProjeto.codigo
            ).filter(
                SkuMapping.evento_grupo == gn,
                DimProjeto.estado.isnot(None)
            ).first()
            if estado_row:
                missing_estado_map[gn] = estado_row[0]
    for gn in missing:
        try:
            estado = missing_estado_map.get(gn)
            fb_pattern, fb_info = _resolve_hist_pattern(db, gn, ano, estado=estado)
            if fb_pattern:
                result[gn] = fb_pattern
                curva_info_map[gn] = fb_info
            else:
                curva_info_map[gn] = fb_info
        except Exception as e:
            logger.warning(f"Fallback resolution failed for '{gn}': {e}")
            curva_info_map[gn] = {"tipo_curva": "linear", "fonte_curva": None, "ano_referencia": None}

    with _hist_pattern_cache_lock:
        if cache_key not in _hist_pattern_cache:
            _hist_pattern_cache[cache_key] = {}
        _hist_pattern_cache[cache_key].update(result)
        if cache_key not in _hist_curva_info_cache:
            _hist_curva_info_cache[cache_key] = {}
        _hist_curva_info_cache[cache_key].update(curva_info_map)

    if cached is not None:
        result.update(filtered)
        cached_ci = _hist_curva_info_cache.get(cache_key, {})
        for gn in filtered:
            if gn not in curva_info_map:
                curva_info_map[gn] = cached_ci.get(gn, {"tipo_curva": "historico", "fonte_curva": gn, "ano_referencia": prev_ano})

    return result, curva_info_map


def _find_data_evento(db: Session, evento_grupo: str, ano: int) -> Optional[date]:
    from ...models.dimensoes import SkuMapping
    ano_corrente = today_brazil().year

    sku_mapping_date = None
    mapping_with_date = db.query(SkuMapping).filter(
        SkuMapping.evento_grupo == evento_grupo,
        SkuMapping.ano == ano,
        SkuMapping.data_evento.isnot(None),
        SkuMapping.ativo == True
    ).first()
    if mapping_with_date:
        sku_mapping_date = mapping_with_date.data_evento
        if ano < ano_corrente:
            logger.info(f"Found data_evento in sku_mappings for '{evento_grupo}' ano={ano} (ano anterior): {sku_mapping_date}")
            return sku_mapping_date
        else:
            logger.debug(f"sku_mappings has data_evento={sku_mapping_date} for '{evento_grupo}' ano={ano}, but preferring dim_projeto/cadastro for current year")
    elif ano < ano_corrente:
        logger.info(f"No data_evento in sku_mappings for '{evento_grupo}' ano={ano} (ano anterior), falling back to dim_projeto")

    normalized_grupo = _normalize_name_for_match(evento_grupo)
    projetos = _wq_all_dim_projetos(db)
    projetos = [p for p in projetos if p.data_evento is not None]
    
    best_match = None
    best_score = 0
    
    for p in projetos:
        p_year = p.data_evento.year if p.data_evento else None
        if p_year != ano:
            continue
        normalized_proj = _normalize_name_for_match(p.evento or "")
        
        grupo_words = set(normalized_grupo.split())
        proj_words = set(normalized_proj.split())
        if not grupo_words or not proj_words:
            continue
        common = grupo_words & proj_words
        score = len(common) / max(len(grupo_words), len(proj_words))
        
        if score > best_score:
            best_score = score
            best_match = p
    
    if best_match and best_score >= 0.5:
        logger.info(f"Matched evento_grupo '{evento_grupo}' ano={ano} -> projeto '{best_match.evento}' data_evento={best_match.data_evento} (score={best_score:.2f})")
        return best_match.data_evento
    
    adj_best_match = None
    adj_best_score = 0
    adj_year_diff = None
    for p in projetos:
        p_year = p.data_evento.year
        if p_year == ano:
            continue
        normalized_proj = _normalize_name_for_match(p.evento or "")
        grupo_words = set(normalized_grupo.split())
        proj_words = set(normalized_proj.split())
        if not grupo_words or not proj_words:
            continue
        common = grupo_words & proj_words
        score = len(common) / max(len(grupo_words), len(proj_words))
        year_distance = abs(p_year - ano)
        if score > adj_best_score or (score == adj_best_score and adj_year_diff is not None and year_distance < adj_year_diff):
            adj_best_score = score
            adj_best_match = p
            adj_year_diff = year_distance

    if adj_best_match and adj_best_score >= 0.5:
        try:
            adjusted_date = adj_best_match.data_evento.replace(year=ano)
        except ValueError:
            month = adj_best_match.data_evento.month
            day = 28 if adj_best_match.data_evento.month == 2 else adj_best_match.data_evento.day
            adjusted_date = date(ano, month, day)

        if sku_mapping_date and abs((adjusted_date - sku_mapping_date).days) > 60:
            logger.warning(
                f"Estimated data_evento ({adjusted_date}) for '{evento_grupo}' ano={ano} differs by "
                f"{abs((adjusted_date - sku_mapping_date).days)} days from sku_mappings date ({sku_mapping_date}). "
                f"Using sku_mappings date as it is more reliable."
            )
            return sku_mapping_date

        logger.info(f"Estimated data_evento for '{evento_grupo}' ano={ano} from year {adj_best_match.data_evento.year} event '{adj_best_match.evento}': {adjusted_date}")
        return adjusted_date

    if sku_mapping_date:
        logger.info(f"No dim_projeto match for '{evento_grupo}' ano={ano}, using sku_mappings date: {sku_mapping_date}")
        return sku_mapping_date

    logger.warning(f"Could not match evento_grupo '{evento_grupo}' ano={ano} to any dim_projeto (best_score={best_score:.2f})")
    return None


_curva_evento_cache = {}
_curva_evento_cache_timestamp = {}


@router.get("/curva-comparativa/{evento_id}")
def get_curva_comparativa_evento(
    evento_id: str,
    ano: int = Query(default=None, description="Ano base para comparacao"),
    force_refresh: bool = Query(default=False, description="Forçar atualização dos dados ignorando cache"),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
    response: Response = None
):
    import time

    cache_key = f"{evento_id}_{ano}"
    current_time = time.time()
    
    smart_curva_key = f"{ano}_{evento_id}_curva"
    if not force_refresh:
        def _swr_curva_refresh():
            from ...core.database import SessionLocal
            _db = SessionLocal()
            try:
                get_curva_comparativa_evento(evento_id=evento_id, ano=ano, force_refresh=True, db=_db, current_user=None)
            finally:
                _db.close()

        cached_curva, is_stale = curva_cache.get_or_revalidate(smart_curva_key, refresh_fn=_swr_curva_refresh)
        if cached_curva is not None:
            cached_data = cached_curva.get("data", []) if isinstance(cached_curva, dict) else []
            if cached_data:
                if response is not None:
                    response.headers["X-Data-Stale"] = "true" if is_stale else "false"
                return cached_curva
            else:
                logger.warning(f"Discarding empty cached curva for key={smart_curva_key}, will recalculate")
                curva_cache.invalidate(smart_curva_key)

    is_grouped = evento_id.startswith("grp_")

    if is_grouped:
        grupo_nome = evento_id.replace("grp_", "")
        if ano is None:
            ano = datetime.now().year
        ano_anterior = ano - 1

        all_mappings = _wq_sku_mappings_by_grupo(db, grupo_nome, [ano, ano_anterior])
    else:
        projeto = _wq_dim_projeto_by_id(db, int(evento_id))
        if not projeto:
            raise HTTPException(status_code=404, detail="Evento nao encontrado")

        sku = str(projeto.codigo) if projeto.codigo else None
        if not sku:
            return {"status": "success", "ano_atual": datetime.now().year, "ano_anterior": datetime.now().year - 1, "data": [], "evento_nome": str(projeto.evento or "")}

        if ano is None:
            ano = projeto.data_evento.year if projeto.data_evento else datetime.now().year
        ano_anterior = ano - 1

        mapping_list = _wq_sku_mappings_by_sku(db, sku)
        mapping = mapping_list[0] if mapping_list else None

        if mapping and mapping.evento_grupo:
            all_mappings = _wq_sku_mappings_by_grupo(db, mapping.evento_grupo, [ano, ano_anterior])
        else:
            all_mappings = _wq_sku_mappings_by_sku(db, sku)
            if not all_mappings:
                all_mappings = []

    mappings_atual = [m for m in all_mappings if m.ano == ano]
    mappings_anterior = [m for m in all_mappings if m.ano == ano_anterior]

    ids_ativo_atual = list(set([m.id_externo for m in mappings_atual if m.fonte == 'ATIVO']))
    ids_magento_atual = list(set([m.id_externo for m in mappings_atual if m.fonte == 'MAGENTO']))
    ids_ativo_anterior = list(set([m.id_externo for m in mappings_anterior if m.fonte == 'ATIVO']))
    ids_magento_anterior = list(set([m.id_externo for m in mappings_anterior if m.fonte == 'MAGENTO']))

    all_ids = ids_ativo_atual + ids_magento_atual + ids_ativo_anterior + ids_magento_anterior
    if not all_ids:
        return {"status": "success", "ano_atual": ano, "ano_anterior": ano_anterior, "data": [], "evento_nome": ""}

    grupo_nome_for_match = grupo_nome if is_grouped else str(projeto.evento or "")
    data_evento_atual = _find_data_evento(db, grupo_nome_for_match, ano)
    data_evento_anterior = _find_data_evento(db, grupo_nome_for_match, ano_anterior)

    if not data_evento_atual and not data_evento_anterior:
        logger.warning(f"No data_evento found for {grupo_nome_for_match}, falling back to month-based")
        return _curva_comparativa_mensal_fallback(
            ids_ativo_atual, ids_magento_atual, ids_ativo_anterior, ids_magento_anterior,
            ano, ano_anterior, evento_id, is_grouped, projeto if not is_grouped else None
        )

    if data_evento_atual and not data_evento_anterior:
        ref_day_month = (data_evento_atual.month, data_evento_atual.day)
        data_evento_anterior = date(ano_anterior, ref_day_month[0], min(ref_day_month[1], 28))
        logger.info(f"No data_evento for {ano_anterior}, estimated from {ano}: {data_evento_anterior}")
    elif data_evento_anterior and not data_evento_atual:
        ref_day_month = (data_evento_anterior.month, data_evento_anterior.day)
        data_evento_atual = date(ano, ref_day_month[0], min(ref_day_month[1], 28))
        logger.info(f"No data_evento for {ano}, estimated from {ano_anterior}: {data_evento_atual}")

    _cort_curva = _get_cortesia_magento_ids(db)
    _mag_cort_atual = (set(ids_magento_atual) & _cort_curva) if _cort_curva and ids_magento_atual else None
    _mag_cort_anterior = (set(ids_magento_anterior) & _cort_curva) if _cort_curva and ids_magento_anterior else None

    is_warmup = _is_warmup_thread()
    if is_warmup:
        try:
            dados_ativo_atual = _fetch_daily_sales_ativo_by_ids(ids_ativo_atual)
        except Exception as e:
            logger.error(f"Curva comparativa daily Ativo atual error: {e}")
            dados_ativo_atual = []
        try:
            dados_magento_atual = _fetch_daily_sales_magento_by_ids(ids_magento_atual, cortesia_magento_ids=_mag_cort_atual if _mag_cort_atual else None)
        except Exception as e:
            logger.error(f"Curva comparativa daily Magento atual error: {e}")
            dados_magento_atual = []
        try:
            dados_ativo_anterior = _fetch_daily_sales_ativo_by_ids(ids_ativo_anterior)
        except Exception as e:
            logger.error(f"Curva comparativa daily Ativo anterior error: {e}")
            dados_ativo_anterior = []
        try:
            dados_magento_anterior = _fetch_daily_sales_magento_by_ids(ids_magento_anterior, cortesia_magento_ids=_mag_cort_anterior if _mag_cort_anterior else None)
        except Exception as e:
            logger.error(f"Curva comparativa daily Magento anterior error: {e}")
            dados_magento_anterior = []
    else:
        future_ativo_atual = _rolling_avg_executor.submit(_fetch_daily_sales_ativo_by_ids, ids_ativo_atual)
        future_magento_atual = _rolling_avg_executor.submit(_fetch_daily_sales_magento_by_ids, ids_magento_atual, cortesia_magento_ids=_mag_cort_atual if _mag_cort_atual else None)
        future_ativo_anterior = _rolling_avg_executor.submit(_fetch_daily_sales_ativo_by_ids, ids_ativo_anterior)
        future_magento_anterior = _rolling_avg_executor.submit(_fetch_daily_sales_magento_by_ids, ids_magento_anterior, cortesia_magento_ids=_mag_cort_anterior if _mag_cort_anterior else None)

        try:
            dados_ativo_atual = future_ativo_atual.result(timeout=60)
        except Exception as e:
            logger.error(f"Curva comparativa daily Ativo atual timeout: {e}")
            dados_ativo_atual = []
        try:
            dados_magento_atual = future_magento_atual.result(timeout=60)
        except Exception as e:
            logger.error(f"Curva comparativa daily Magento atual timeout: {e}")
            dados_magento_atual = []
        try:
            dados_ativo_anterior = future_ativo_anterior.result(timeout=60)
        except Exception as e:
            logger.error(f"Curva comparativa daily Ativo anterior timeout: {e}")
            dados_ativo_anterior = []
        try:
            dados_magento_anterior = future_magento_anterior.result(timeout=60)
        except Exception as e:
            logger.error(f"Curva comparativa daily Magento anterior timeout: {e}")
            dados_magento_anterior = []

    BUCKET_SIZE = 7

    def _build_daily_map(dados_list: list, data_evento_ref: Optional[date]) -> dict:
        daily = {}
        if not data_evento_ref:
            return daily
        for row in dados_list:
            try:
                dia = date.fromisoformat(row["dia"])
            except (ValueError, KeyError):
                continue
            dias_antes = (data_evento_ref - dia).days
            if dias_antes not in daily:
                daily[dias_antes] = {"qtd": 0, "receita": 0.0}
            daily[dias_antes]["qtd"] += row["qtd"]
            daily[dias_antes]["receita"] += row["receita"]
        return daily

    dias_enc_atual = 2
    if data_evento_atual:
        try:
            proj_atual = db.query(DimProjeto).filter(DimProjeto.data_evento == data_evento_atual).first()
            if proj_atual:
                dias_enc_atual = get_dias_encerramento(db, projeto_id=proj_atual.id)
        except Exception:
            pass
    dias_enc_anterior = 2
    if data_evento_anterior:
        try:
            proj_anterior = db.query(DimProjeto).filter(DimProjeto.data_evento == data_evento_anterior).first()
            if proj_anterior:
                dias_enc_anterior = get_dias_encerramento(db, projeto_id=proj_anterior.id)
        except Exception:
            pass
    data_insc_atual = data_evento_atual - timedelta(days=dias_enc_atual) if data_evento_atual else None
    data_insc_anterior = data_evento_anterior - timedelta(days=dias_enc_anterior) if data_evento_anterior else None

    daily_atual = _build_daily_map(dados_ativo_atual + dados_magento_atual, data_insc_atual)
    daily_anterior = _build_daily_map(dados_ativo_anterior + dados_magento_anterior, data_insc_anterior)

    all_dias = set(daily_atual.keys()) | set(daily_anterior.keys())
    if not all_dias:
        max_dias = 180
        min_dias = 0
    else:
        max_dias = max(all_dias)
        min_dias = min(all_dias)

    def _bucket_key_for(d: int) -> int:
        if d >= 0:
            return (d // BUCKET_SIZE) * BUCKET_SIZE
        return -((abs(d) // BUCKET_SIZE + 1) * BUCKET_SIZE)

    max_bucket = _bucket_key_for(max_dias)
    if max_bucket < max_dias:
        max_bucket += BUCKET_SIZE
    min_bucket = _bucket_key_for(min_dias) if min_dias < 0 else 0

    buckets = {}
    b = min_bucket
    while b <= max_bucket:
        if b < 0:
            label = f"D+{abs(b)}"
        elif b == 0:
            label = "D-0"
        else:
            label = f"D-{b}"
        buckets[b] = {
            "dias_antes": b,
            "label": label,
            f"vendas_{ano}": 0,
            f"vendas_{ano_anterior}": 0,
            f"receita_{ano}": 0.0,
            f"receita_{ano_anterior}": 0.0,
        }
        b += BUCKET_SIZE

    for dias, vals in daily_atual.items():
        bk = _bucket_key_for(dias)
        if bk in buckets:
            buckets[bk][f"vendas_{ano}"] += vals["qtd"]
            buckets[bk][f"receita_{ano}"] += vals["receita"]

    for dias, vals in daily_anterior.items():
        bk = _bucket_key_for(dias)
        if bk in buckets:
            buckets[bk][f"vendas_{ano_anterior}"] += vals["qtd"]
            buckets[bk][f"receita_{ano_anterior}"] += vals["receita"]

    hoje = today_brazil()
    dias_ate_evento_atual = (data_evento_atual - hoje).days if data_evento_atual else 0

    total_vendas_atual = sum(v["qtd"] for v in daily_atual.values())
    total_receita_atual = sum(v["receita"] for v in daily_atual.values())

    dias_com_vendas = sorted([d for d in daily_atual.keys() if daily_atual[d]["qtd"] > 0])
    if dias_com_vendas and dias_ate_evento_atual > 0:
        dias_recentes = [d for d in dias_com_vendas if d >= dias_ate_evento_atual and d <= dias_ate_evento_atual + 30]
        if not dias_recentes:
            dias_recentes = sorted(dias_com_vendas)[:30]
        
        window = min(14, len(dias_recentes))
        if window > 0:
            vendas_window = sum(daily_atual[d]["qtd"] for d in dias_recentes[:window])
            receita_window = sum(daily_atual[d]["receita"] for d in dias_recentes[:window])
            media_diaria_vendas = vendas_window / window
            media_diaria_receita = receita_window / window
        else:
            dias_total = len(dias_com_vendas)
            media_diaria_vendas = total_vendas_atual / max(1, dias_total)
            media_diaria_receita = total_receita_atual / max(1, dias_total)
    else:
        media_diaria_vendas = 0
        media_diaria_receita = 0.0

    sorted_keys = sorted(buckets.keys(), reverse=True)
    data = []
    acum_atual = 0
    acum_anterior = 0
    acum_receita_atual = 0.0
    acum_receita_anterior = 0.0
    for bk in sorted_keys:
        entry = buckets[bk]
        acum_atual += entry[f"vendas_{ano}"]
        acum_anterior += entry[f"vendas_{ano_anterior}"]
        acum_receita_atual += entry[f"receita_{ano}"]
        acum_receita_anterior += entry[f"receita_{ano_anterior}"]
        entry[f"receita_{ano}"] = round(entry[f"receita_{ano}"], 2)
        entry[f"receita_{ano_anterior}"] = round(entry[f"receita_{ano_anterior}"], 2)
        entry[f"acumulado_{ano}"] = acum_atual
        entry[f"acumulado_{ano_anterior}"] = acum_anterior
        entry[f"acumulado_receita_{ano}"] = round(acum_receita_atual, 2)
        entry[f"acumulado_receita_{ano_anterior}"] = round(acum_receita_anterior, 2)
        entry["is_projecao"] = False
        data.append(entry)

    if dias_ate_evento_atual > 0 and media_diaria_vendas > 0 and ano == datetime.now().year:
        last_real_idx = None
        for i, entry in enumerate(data):
            if entry[f"vendas_{ano}"] > 0:
                last_real_idx = i

        if last_real_idx is not None:
            acum_proj_vendas = data[last_real_idx][f"acumulado_{ano}"]
            acum_proj_receita = data[last_real_idx][f"acumulado_receita_{ano}"]

            data[last_real_idx][f"projecao_acumulado_{ano}"] = acum_proj_vendas
            data[last_real_idx][f"projecao_acumulado_receita_{ano}"] = acum_proj_receita

            for i in range(last_real_idx + 1, len(data)):
                proj_vendas_bucket = media_diaria_vendas * BUCKET_SIZE
                proj_receita_bucket = media_diaria_receita * BUCKET_SIZE
                acum_proj_vendas += proj_vendas_bucket
                acum_proj_receita += proj_receita_bucket
                data[i][f"projecao_acumulado_{ano}"] = round(acum_proj_vendas)
                data[i][f"projecao_acumulado_receita_{ano}"] = round(acum_proj_receita, 2)
                data[i]["is_projecao"] = True

    total_vendas_anterior = sum(entry[f"vendas_{ano_anterior}"] for entry in data)
    total_receita_anterior = sum(entry[f"receita_{ano_anterior}"] for entry in data)
    total_vendas_atual = sum(entry[f"vendas_{ano}"] for entry in data)
    total_receita_atual_sum = sum(entry[f"receita_{ano}"] for entry in data)

    for entry in data:
        acum_v = entry.get(f"acumulado_{ano}", 0)
        acum_v_ant = entry.get(f"acumulado_{ano_anterior}", 0)
        acum_r = entry.get(f"acumulado_receita_{ano}", 0)
        acum_r_ant = entry.get(f"acumulado_receita_{ano_anterior}", 0)
        entry[f"pct_meta_vendas_{ano}"] = round((acum_v / total_vendas_anterior * 100), 1) if total_vendas_anterior > 0 else 0
        entry[f"pct_meta_vendas_{ano_anterior}"] = round((acum_v_ant / total_vendas_anterior * 100), 1) if total_vendas_anterior > 0 else 0
        entry[f"pct_meta_receita_{ano}"] = round((acum_r / total_receita_anterior * 100), 1) if total_receita_anterior > 0 else 0
        entry[f"pct_meta_receita_{ano_anterior}"] = round((acum_r_ant / total_receita_anterior * 100), 1) if total_receita_anterior > 0 else 0

        proj_v = entry.get(f"projecao_acumulado_{ano}")
        proj_r = entry.get(f"projecao_acumulado_receita_{ano}")
        if proj_v is not None and total_vendas_anterior > 0:
            entry[f"pct_meta_projecao_vendas_{ano}"] = round((proj_v / total_vendas_anterior * 100), 1)
        if proj_r is not None and total_receita_anterior > 0:
            entry[f"pct_meta_projecao_receita_{ano}"] = round((proj_r / total_receita_anterior * 100), 1)

    ultimo_acum_vendas_atual = 0
    ultimo_acum_receita_atual = 0.0
    for entry in data:
        if not entry.get("is_projecao", False) and entry.get(f"acumulado_{ano}", 0) > 0:
            ultimo_acum_vendas_atual = entry[f"acumulado_{ano}"]
            ultimo_acum_receita_atual = entry[f"acumulado_receita_{ano}"]

    pct_atingido_vendas = round((ultimo_acum_vendas_atual / total_vendas_anterior * 100), 1) if total_vendas_anterior > 0 else 0
    pct_atingido_receita = round((ultimo_acum_receita_atual / total_receita_anterior * 100), 1) if total_receita_anterior > 0 else 0

    ultimo_acum_vendas_anterior_mesmo_d = 0
    ultimo_acum_receita_anterior_mesmo_d = 0.0
    if dias_ate_evento_atual > 0 and daily_anterior:
        for d_ant, vals in daily_anterior.items():
            if d_ant >= dias_ate_evento_atual:
                ultimo_acum_vendas_anterior_mesmo_d += vals["qtd"]
                ultimo_acum_receita_anterior_mesmo_d += vals["receita"]

    pct_anterior_vendas_mesmo_d = round((ultimo_acum_vendas_anterior_mesmo_d / total_vendas_anterior * 100), 1) if total_vendas_anterior > 0 else 0
    pct_anterior_receita_mesmo_d = round((ultimo_acum_receita_anterior_mesmo_d / total_receita_anterior * 100), 1) if total_receita_anterior > 0 else 0

    meta_orcada = 0
    try:
        if is_grouped:
            skus_atual = list(set([m.sku for m in mappings_atual if m.sku]))
            projetos_atual = db.query(DimProjeto).filter(DimProjeto.codigo.in_(skus_atual)).all() if skus_atual else []
        else:
            projetos_atual = [projeto] if projeto else []
        meta_orcada = get_meta_orcada_projetos(db, projetos_atual)
    except Exception as e:
        logger.warning(f"Could not fetch meta_orcada for curva comparativa: {e}")

    ritmo_diario_necessario_vendas = 0.0
    ritmo_diario_necessario_receita = 0.0
    meta_referencia = meta_orcada if meta_orcada > 0 else total_vendas_anterior
    if dias_ate_evento_atual > 0 and meta_referencia > 0:
        faltam_vendas = max(0, meta_referencia - ultimo_acum_vendas_atual)
        ritmo_diario_necessario_vendas = round(faltam_vendas / dias_ate_evento_atual, 1)
    if dias_ate_evento_atual > 0 and total_receita_anterior > 0:
        faltam_receita = max(0, total_receita_anterior - ultimo_acum_receita_atual)
        ritmo_diario_necessario_receita = round(faltam_receita / dias_ate_evento_atual, 2)

    variacao_mesmo_d_vendas = round(((ultimo_acum_vendas_atual - ultimo_acum_vendas_anterior_mesmo_d) / ultimo_acum_vendas_anterior_mesmo_d * 100), 1) if ultimo_acum_vendas_anterior_mesmo_d > 0 else 0
    variacao_mesmo_d_receita = round(((ultimo_acum_receita_atual - ultimo_acum_receita_anterior_mesmo_d) / ultimo_acum_receita_anterior_mesmo_d * 100), 1) if ultimo_acum_receita_anterior_mesmo_d > 0 else 0

    evento_nome = ""
    if is_grouped:
        evento_nome = evento_id.replace("grp_", "")
    else:
        evento_nome = str(projeto.evento or "")

    result = {
        "status": "success",
        "modo": "dias_antes_evento",
        "ano_atual": ano,
        "ano_anterior": ano_anterior,
        "data_evento_atual": str(data_evento_atual) if data_evento_atual else None,
        "data_evento_anterior": str(data_evento_anterior) if data_evento_anterior else None,
        "data": data,
        "evento_nome": evento_nome,
        "media_diaria_vendas": round(media_diaria_vendas, 2),
        "media_diaria_receita": round(media_diaria_receita, 2),
        "ultima_atualizacao": datetime.now(ZoneInfo('America/Sao_Paulo')).isoformat(),
        "meta": {
            "total_vendas_anterior": total_vendas_anterior,
            "total_receita_anterior": round(total_receita_anterior, 2),
            "total_vendas_atual": total_vendas_atual,
            "total_receita_atual": round(total_receita_atual_sum, 2),
            "pct_atingido_vendas": pct_atingido_vendas,
            "pct_atingido_receita": pct_atingido_receita,
            "diff_pp_vendas": round(pct_atingido_vendas - pct_anterior_vendas_mesmo_d, 1),
            "diff_pp_receita": round(pct_atingido_receita - pct_anterior_receita_mesmo_d, 1),
            "pct_anterior_vendas_mesmo_d": pct_anterior_vendas_mesmo_d,
            "pct_anterior_receita_mesmo_d": pct_anterior_receita_mesmo_d,
            "ultimo_acum_vendas_anterior_mesmo_d": ultimo_acum_vendas_anterior_mesmo_d,
            "ultimo_acum_receita_anterior_mesmo_d": round(ultimo_acum_receita_anterior_mesmo_d, 2),
            "meta_orcada": meta_orcada,
            "dias_ate_evento": dias_ate_evento_atual,
            "ritmo_diario_necessario_vendas": ritmo_diario_necessario_vendas,
            "ritmo_diario_necessario_receita": ritmo_diario_necessario_receita,
            "variacao_mesmo_d_vendas": variacao_mesmo_d_vendas,
            "variacao_mesmo_d_receita": variacao_mesmo_d_receita,
        }
    }

    _curva_evento_cache[cache_key] = result
    _curva_evento_cache_timestamp[cache_key] = current_time
    curva_cache.set(smart_curva_key, result)
    return result


@router.get("/eventos/{evento_id}/insights")
def get_evento_insights(
    evento_id: str,
    ano: int = Query(default=None, description="Ano base para comparacao"),
    force_refresh: bool = Query(default=False, description="Forçar atualização dos dados ignorando cache"),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
    response: Response = None
):
    smart_insights_key = f"{ano}_{evento_id}_insights"
    if not force_refresh:
        def _swr_insights_refresh():
            from ...core.database import SessionLocal
            _db = SessionLocal()
            try:
                get_evento_insights(evento_id=evento_id, ano=ano, force_refresh=True, db=_db, current_user=None)
            finally:
                _db.close()

        cached, is_stale = curva_cache.get_or_revalidate(smart_insights_key, refresh_fn=_swr_insights_refresh)
        if cached is not None:
            if response is not None:
                response.headers["X-Data-Stale"] = "true" if is_stale else "false"
            return cached

    is_grouped = evento_id.startswith("grp_")

    if is_grouped:
        grupo_nome = evento_id.replace("grp_", "")
        if ano is None:
            ano = datetime.now().year
        ano_anterior = ano - 1

        all_mappings = _wq_sku_mappings_by_grupo(db, grupo_nome, [ano, ano_anterior])
    else:
        projeto = _wq_dim_projeto_by_id(db, int(evento_id))
        if not projeto:
            raise HTTPException(status_code=404, detail="Evento nao encontrado")

        sku = str(projeto.codigo) if projeto.codigo else None
        if not sku:
            return {"status": "success", "ano_atual": datetime.now().year, "ano_anterior": datetime.now().year - 1, "evento_nome": str(projeto.evento or ""), "indice_aceleracao": [], "pace_diario": [], "projecao_fechamento": {}, "janela_acao": {}, "ticket_medio": [], "mix_categorias": {"atual": [], "anterior": []}, "ultima_atualizacao": datetime.now(ZoneInfo('America/Sao_Paulo')).isoformat()}

        if ano is None:
            ano = projeto.data_evento.year if projeto.data_evento else datetime.now().year
        ano_anterior = ano - 1

        mapping_list = _wq_sku_mappings_by_sku(db, sku)
        mapping = mapping_list[0] if mapping_list else None

        if mapping and mapping.evento_grupo:
            all_mappings = _wq_sku_mappings_by_grupo(db, mapping.evento_grupo, [ano, ano_anterior])
        else:
            all_mappings = _wq_sku_mappings_by_sku(db, sku)
            if not all_mappings:
                all_mappings = []

    mappings_atual = [m for m in all_mappings if m.ano == ano]
    mappings_anterior = [m for m in all_mappings if m.ano == ano_anterior]

    ids_ativo_atual = list(set([m.id_externo for m in mappings_atual if m.fonte == 'ATIVO']))
    ids_magento_atual = list(set([m.id_externo for m in mappings_atual if m.fonte == 'MAGENTO']))
    ids_ativo_anterior = list(set([m.id_externo for m in mappings_anterior if m.fonte == 'ATIVO']))
    ids_magento_anterior = list(set([m.id_externo for m in mappings_anterior if m.fonte == 'MAGENTO']))

    all_ids = ids_ativo_atual + ids_magento_atual + ids_ativo_anterior + ids_magento_anterior
    if not all_ids:
        return {"status": "success", "ano_atual": ano, "ano_anterior": ano_anterior, "evento_nome": "", "indice_aceleracao": [], "pace_diario": [], "projecao_fechamento": {}, "janela_acao": {}, "ticket_medio": [], "mix_categorias": {"atual": [], "anterior": []}, "ultima_atualizacao": datetime.now(ZoneInfo('America/Sao_Paulo')).isoformat()}

    grupo_nome_for_match = grupo_nome if is_grouped else str(projeto.evento or "")
    data_evento_atual = _find_data_evento(db, grupo_nome_for_match, ano)
    data_evento_anterior = _find_data_evento(db, grupo_nome_for_match, ano_anterior)

    if data_evento_atual and not data_evento_anterior:
        ref_day_month = (data_evento_atual.month, data_evento_atual.day)
        data_evento_anterior = date(ano_anterior, ref_day_month[0], min(ref_day_month[1], 28))
    elif data_evento_anterior and not data_evento_atual:
        ref_day_month = (data_evento_anterior.month, data_evento_anterior.day)
        data_evento_atual = date(ano, ref_day_month[0], min(ref_day_month[1], 28))

    _cort_insights = _get_cortesia_magento_ids(db)
    _mag_cort_atual_ins = (set(ids_magento_atual) & _cort_insights) if _cort_insights and ids_magento_atual else None
    _mag_cort_anterior_ins = (set(ids_magento_anterior) & _cort_insights) if _cort_insights and ids_magento_anterior else None

    is_warmup = _is_warmup_thread()
    if is_warmup:
        try:
            dados_ativo_atual = _fetch_daily_sales_ativo_by_ids(ids_ativo_atual)
        except Exception as e:
            logger.error(f"Insights daily Ativo atual error: {e}")
            dados_ativo_atual = []
        try:
            dados_magento_atual = _fetch_daily_sales_magento_by_ids(ids_magento_atual, cortesia_magento_ids=_mag_cort_atual_ins if _mag_cort_atual_ins else None)
        except Exception as e:
            logger.error(f"Insights daily Magento atual error: {e}")
            dados_magento_atual = []
        try:
            dados_ativo_anterior = _fetch_daily_sales_ativo_by_ids(ids_ativo_anterior)
        except Exception as e:
            logger.error(f"Insights daily Ativo anterior error: {e}")
            dados_ativo_anterior = []
        try:
            dados_magento_anterior = _fetch_daily_sales_magento_by_ids(ids_magento_anterior, cortesia_magento_ids=_mag_cort_anterior_ins if _mag_cort_anterior_ins else None)
        except Exception as e:
            logger.error(f"Insights daily Magento anterior error: {e}")
            dados_magento_anterior = []
        try:
            cat_ativo_atual = _fetch_category_sales_ativo_by_ids(ids_ativo_atual)
        except Exception:
            cat_ativo_atual = []
        try:
            cat_magento_atual = _fetch_category_sales_magento_by_ids(ids_magento_atual)
        except Exception:
            cat_magento_atual = []
        try:
            cat_ativo_anterior = _fetch_category_sales_ativo_by_ids(ids_ativo_anterior)
        except Exception:
            cat_ativo_anterior = []
        try:
            cat_magento_anterior = _fetch_category_sales_magento_by_ids(ids_magento_anterior)
        except Exception:
            cat_magento_anterior = []
    else:
        future_ativo_atual = _rolling_avg_executor.submit(_fetch_daily_sales_ativo_by_ids, ids_ativo_atual)
        future_magento_atual = _rolling_avg_executor.submit(_fetch_daily_sales_magento_by_ids, ids_magento_atual, cortesia_magento_ids=_mag_cort_atual_ins if _mag_cort_atual_ins else None)
        future_ativo_anterior = _rolling_avg_executor.submit(_fetch_daily_sales_ativo_by_ids, ids_ativo_anterior)
        future_magento_anterior = _rolling_avg_executor.submit(_fetch_daily_sales_magento_by_ids, ids_magento_anterior, cortesia_magento_ids=_mag_cort_anterior_ins if _mag_cort_anterior_ins else None)
        future_cat_ativo_atual = _rolling_avg_executor.submit(_fetch_category_sales_ativo_by_ids, ids_ativo_atual)
        future_cat_magento_atual = _rolling_avg_executor.submit(_fetch_category_sales_magento_by_ids, ids_magento_atual)
        future_cat_ativo_anterior = _rolling_avg_executor.submit(_fetch_category_sales_ativo_by_ids, ids_ativo_anterior)
        future_cat_magento_anterior = _rolling_avg_executor.submit(_fetch_category_sales_magento_by_ids, ids_magento_anterior)

        try:
            dados_ativo_atual = future_ativo_atual.result(timeout=60)
        except Exception as e:
            logger.error(f"Insights daily Ativo atual timeout: {e}")
            dados_ativo_atual = []
        try:
            dados_magento_atual = future_magento_atual.result(timeout=60)
        except Exception as e:
            logger.error(f"Insights daily Magento atual timeout: {e}")
            dados_magento_atual = []
        try:
            dados_ativo_anterior = future_ativo_anterior.result(timeout=60)
        except Exception as e:
            logger.error(f"Insights daily Ativo anterior timeout: {e}")
            dados_ativo_anterior = []
        try:
            dados_magento_anterior = future_magento_anterior.result(timeout=60)
        except Exception as e:
            logger.error(f"Insights daily Magento anterior timeout: {e}")
            dados_magento_anterior = []
        try:
            cat_ativo_atual = future_cat_ativo_atual.result(timeout=60)
        except Exception:
            cat_ativo_atual = []
        try:
            cat_magento_atual = future_cat_magento_atual.result(timeout=60)
        except Exception:
            cat_magento_atual = []
        try:
            cat_ativo_anterior = future_cat_ativo_anterior.result(timeout=60)
        except Exception:
            cat_ativo_anterior = []
        try:
            cat_magento_anterior = future_cat_magento_anterior.result(timeout=60)
        except Exception:
            cat_magento_anterior = []

    BUCKET_SIZE = 7

    def _build_daily_map_insights(dados_list: list, data_evento_ref: Optional[date]) -> dict:
        daily = {}
        if not data_evento_ref:
            return daily
        for row in dados_list:
            try:
                dia = date.fromisoformat(row["dia"])
            except (ValueError, KeyError):
                continue
            dias_antes = (data_evento_ref - dia).days
            if dias_antes not in daily:
                daily[dias_antes] = {"qtd": 0, "receita": 0.0}
            daily[dias_antes]["qtd"] += row["qtd"]
            daily[dias_antes]["receita"] += row["receita"]
        return daily

    dias_enc_atual_ins = 2
    if data_evento_atual:
        try:
            proj_atual_ins = db.query(DimProjeto).filter(DimProjeto.data_evento == data_evento_atual).first()
            if proj_atual_ins:
                dias_enc_atual_ins = get_dias_encerramento(db, projeto_id=proj_atual_ins.id)
        except Exception:
            pass
    dias_enc_anterior_ins = 2
    if data_evento_anterior:
        try:
            proj_anterior_ins = db.query(DimProjeto).filter(DimProjeto.data_evento == data_evento_anterior).first()
            if proj_anterior_ins:
                dias_enc_anterior_ins = get_dias_encerramento(db, projeto_id=proj_anterior_ins.id)
        except Exception:
            pass
    data_insc_atual_ins = data_evento_atual - timedelta(days=dias_enc_atual_ins) if data_evento_atual else None
    data_insc_anterior_ins = data_evento_anterior - timedelta(days=dias_enc_anterior_ins) if data_evento_anterior else None

    daily_atual = _build_daily_map_insights(dados_ativo_atual + dados_magento_atual, data_insc_atual_ins)
    daily_anterior = _build_daily_map_insights(dados_ativo_anterior + dados_magento_anterior, data_insc_anterior_ins)

    all_dias = set(daily_atual.keys()) | set(daily_anterior.keys())
    if not all_dias:
        max_dias = 180
    else:
        max_dias = max(all_dias)

    def _bucket_key(d: int) -> int:
        if d >= 0:
            return (d // BUCKET_SIZE) * BUCKET_SIZE
        return -((abs(d) // BUCKET_SIZE + 1) * BUCKET_SIZE)

    max_bucket = _bucket_key(max_dias)
    if max_bucket < max_dias:
        max_bucket += BUCKET_SIZE

    bucket_keys_set = set()
    b = 0
    while b <= max_bucket:
        bucket_keys_set.add(b)
        b += BUCKET_SIZE

    sorted_bucket_keys = sorted(bucket_keys_set, reverse=True)

    bucket_data_atual = {}
    bucket_data_anterior = {}
    for bk in sorted_bucket_keys:
        bucket_data_atual[bk] = {"qtd": 0, "receita": 0.0}
        bucket_data_anterior[bk] = {"qtd": 0, "receita": 0.0}

    for dias, vals in daily_atual.items():
        bk = _bucket_key(dias)
        if bk in bucket_data_atual:
            bucket_data_atual[bk]["qtd"] += vals["qtd"]
            bucket_data_atual[bk]["receita"] += vals["receita"]

    for dias, vals in daily_anterior.items():
        bk = _bucket_key(dias)
        if bk in bucket_data_anterior:
            bucket_data_anterior[bk]["qtd"] += vals["qtd"]
            bucket_data_anterior[bk]["receita"] += vals["receita"]

    def _calc_rolling_avg(daily_map: dict, d_minus: int, window: int) -> float:
        total = 0
        for d in range(d_minus, d_minus + window):
            if d in daily_map:
                total += daily_map[d]["qtd"]
        return total / window

    hoje = today_brazil()
    dias_ate_evento_atual = (data_evento_atual - hoje).days if data_evento_atual else 0
    d_minus_atual = max(0, dias_ate_evento_atual)

    indice_aceleracao = []
    max_d_daily = max_dias if max_dias > 0 else 180
    for d in range(max_d_daily, -1, -1):
        label = f"D-{d}"

        atual_alcancado = d >= d_minus_atual
        if atual_alcancado:
            ma7_atual = _calc_rolling_avg(daily_atual, d, 7)
            ma30_atual = _calc_rolling_avg(daily_atual, d, 30)
            ia_atual = round(ma7_atual / ma30_atual, 2) if (ma7_atual >= 1 and ma30_atual >= 1) else None
        else:
            ia_atual = None

        ma7_ant = _calc_rolling_avg(daily_anterior, d, 7)
        ma30_ant = _calc_rolling_avg(daily_anterior, d, 30)
        ia_ant = round(ma7_ant / ma30_ant, 2) if (ma7_ant >= 1 and ma30_ant >= 1) else None
        indice_aceleracao.append({"d_minus": d, "label": label, "ia_atual": ia_atual, "ia_anterior": ia_ant})

    pace_diario = []
    for bk in sorted_bucket_keys:
        label = f"D-{bk}" if bk >= 0 else f"D+{abs(bk)}"
        atual_alcancado = bk >= d_minus_atual
        pace_at = round(bucket_data_atual[bk]["qtd"] / BUCKET_SIZE, 2) if (BUCKET_SIZE > 0 and atual_alcancado) else None
        pace_ant = round(bucket_data_anterior[bk]["qtd"] / BUCKET_SIZE, 2) if BUCKET_SIZE > 0 else None
        pace_diario.append({"d_minus": bk, "label": label, "pace_atual": pace_at, "pace_anterior": pace_ant})

    ticket_medio = []
    acum_q_at = 0
    acum_r_at = 0.0
    acum_q_ant = 0
    acum_r_ant = 0.0
    for d in range(max_d_daily, -1, -1):
        label = f"D-{d}"
        atual_alcancado = d >= d_minus_atual
        if d in daily_anterior:
            acum_q_ant += daily_anterior[d]["qtd"]
            acum_r_ant += daily_anterior[d]["receita"]
        if atual_alcancado and d in daily_atual:
            acum_q_at += daily_atual[d]["qtd"]
            acum_r_at += daily_atual[d]["receita"]
        ticket_at = round(acum_r_at / acum_q_at, 2) if (acum_q_at > 0 and atual_alcancado) else None
        ticket_ant = round(acum_r_ant / acum_q_ant, 2) if acum_q_ant > 0 else None
        ticket_medio.append({"d_minus": d, "label": label, "ticket_atual": ticket_at, "ticket_anterior": ticket_ant})

    total_vendas_atual = sum(v["qtd"] for v in daily_atual.values())
    total_receita_atual = sum(v["receita"] for v in daily_atual.values())
    total_vendas_anterior = sum(v["qtd"] for v in daily_anterior.values())
    total_receita_anterior = sum(v["receita"] for v in daily_anterior.values())

    dias_ate_evento = dias_ate_evento_atual

    if dias_ate_evento > 0:
        total_qtd_14 = 0
        total_rec_14 = 0.0
        for dd in range(d_minus_atual, d_minus_atual + 14):
            if dd in daily_atual:
                total_qtd_14 += daily_atual[dd]["qtd"]
                total_rec_14 += daily_atual[dd]["receita"]
        media_diaria_14d = total_qtd_14 / 14
        media_receita_14d = total_rec_14 / 14
    else:
        media_diaria_14d = 0
        media_receita_14d = 0.0

    projecao_inscricoes = round(total_vendas_atual + media_diaria_14d * max(0, dias_ate_evento))
    projecao_receita = round(total_receita_atual + media_receita_14d * max(0, dias_ate_evento), 2)
    pct_vs_anterior = round(projecao_inscricoes / total_vendas_anterior * 100, 1) if total_vendas_anterior > 0 else 0.0

    projecao_fechamento = {
        "projecao_inscricoes": projecao_inscricoes,
        "projecao_receita": projecao_receita,
        "total_anterior": total_vendas_anterior,
        "receita_anterior": round(total_receita_anterior, 2),
        "pct_vs_anterior": pct_vs_anterior,
        "media_diaria_atual": round(media_diaria_14d, 2),
        "dias_restantes": max(0, dias_ate_evento)
    }

    dentro_d40 = 0 < dias_ate_evento <= 40
    meta_total = total_vendas_anterior if total_vendas_anterior > 0 else 1
    pct_atingido = round(total_vendas_atual / meta_total * 100, 1)
    deficit_superavit = total_vendas_atual - meta_total
    pace_necessario = round((meta_total - total_vendas_atual) / max(1, dias_ate_evento), 2) if dias_ate_evento > 0 else 0
    pace_atual_val = round(media_diaria_14d, 2)

    if total_vendas_atual >= meta_total:
        status_janela = "Acima do esperado"
    elif pace_atual_val >= pace_necessario and pace_necessario > 0:
        status_janela = "Em ritmo"
    else:
        status_janela = "Ação necessária"

    janela_acao = {
        "dias_ate_evento": max(0, dias_ate_evento),
        "dentro_d40": dentro_d40,
        "vendas_acumuladas": total_vendas_atual,
        "meta_total": meta_total,
        "pct_atingido": pct_atingido,
        "pace_necessario": pace_necessario,
        "pace_atual": pace_atual_val,
        "status": status_janela,
        "deficit_superavit": deficit_superavit
    }

    def _merge_categories(cat_list_a: list, cat_list_b: list) -> list:
        merged = {}
        for item in cat_list_a + cat_list_b:
            cat = item["categoria"]
            merged[cat] = merged.get(cat, 0) + item["qtd"]
        total = sum(merged.values())
        result = []
        for cat, qtd in sorted(merged.items(), key=lambda x: x[1], reverse=True):
            pct = round(qtd / total * 100, 1) if total > 0 else 0.0
            result.append({"categoria": cat, "qtd": qtd, "pct": pct})
        return result

    mix_atual = _merge_categories(cat_ativo_atual, cat_magento_atual)
    mix_anterior = _merge_categories(cat_ativo_anterior, cat_magento_anterior)

    evento_nome = ""
    if is_grouped:
        evento_nome = evento_id.replace("grp_", "")
    else:
        evento_nome = str(projeto.evento or "")

    result = {
        "status": "success",
        "ano_atual": ano,
        "ano_anterior": ano_anterior,
        "evento_nome": evento_nome,
        "data_evento_atual": str(data_evento_atual) if data_evento_atual else None,
        "data_evento_anterior": str(data_evento_anterior) if data_evento_anterior else None,
        "indice_aceleracao": indice_aceleracao,
        "pace_diario": pace_diario,
        "projecao_fechamento": projecao_fechamento,
        "janela_acao": janela_acao,
        "ticket_medio": ticket_medio,
        "mix_categorias": {
            "atual": mix_atual,
            "anterior": mix_anterior
        },
        "ultima_atualizacao": datetime.now(ZoneInfo('America/Sao_Paulo')).isoformat()
    }

    curva_cache.set(smart_insights_key, result)
    return result


def _curva_comparativa_mensal_fallback(
    ids_ativo_atual, ids_magento_atual, ids_ativo_anterior, ids_magento_anterior,
    ano, ano_anterior, evento_id, is_grouped, projeto=None
):
    future_ativo_atual = _rolling_avg_executor.submit(_fetch_monthly_sales_ativo_by_ids, ids_ativo_atual)
    future_magento_atual = _rolling_avg_executor.submit(_fetch_monthly_sales_magento_by_ids, ids_magento_atual)
    future_ativo_anterior = _rolling_avg_executor.submit(_fetch_monthly_sales_ativo_by_ids, ids_ativo_anterior)
    future_magento_anterior = _rolling_avg_executor.submit(_fetch_monthly_sales_magento_by_ids, ids_magento_anterior)

    try:
        dados_ativo_atual = future_ativo_atual.result(timeout=60)
    except Exception:
        dados_ativo_atual = []
    try:
        dados_magento_atual = future_magento_atual.result(timeout=60)
    except Exception:
        dados_magento_atual = []
    try:
        dados_ativo_anterior = future_ativo_anterior.result(timeout=60)
    except Exception:
        dados_ativo_anterior = []
    try:
        dados_magento_anterior = future_magento_anterior.result(timeout=60)
    except Exception:
        dados_magento_anterior = []

    meses_labels = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]
    monthly = {}
    for m in range(1, 13):
        monthly[m] = {
            "mes": meses_labels[m - 1],
            f"vendas_{ano}": 0,
            f"vendas_{ano_anterior}": 0,
            f"receita_{ano}": 0.0,
            f"receita_{ano_anterior}": 0.0,
        }
    for row in dados_ativo_atual + dados_magento_atual:
        m = row["mes"]
        if 1 <= m <= 12:
            monthly[m][f"vendas_{ano}"] += row["qtd"]
            monthly[m][f"receita_{ano}"] += row["receita"]
    for row in dados_ativo_anterior + dados_magento_anterior:
        m = row["mes"]
        if 1 <= m <= 12:
            monthly[m][f"vendas_{ano_anterior}"] += row["qtd"]
            monthly[m][f"receita_{ano_anterior}"] += row["receita"]
    data = []
    acum_atual = 0
    acum_anterior = 0
    acum_receita_atual = 0.0
    acum_receita_anterior = 0.0
    for m in range(1, 13):
        entry = monthly[m]
        acum_atual += entry[f"vendas_{ano}"]
        acum_anterior += entry[f"vendas_{ano_anterior}"]
        acum_receita_atual += entry[f"receita_{ano}"]
        acum_receita_anterior += entry[f"receita_{ano_anterior}"]
        entry[f"receita_{ano}"] = round(entry[f"receita_{ano}"], 2)
        entry[f"receita_{ano_anterior}"] = round(entry[f"receita_{ano_anterior}"], 2)
        entry[f"acumulado_{ano}"] = acum_atual
        entry[f"acumulado_{ano_anterior}"] = acum_anterior
        entry[f"acumulado_receita_{ano}"] = round(acum_receita_atual, 2)
        entry[f"acumulado_receita_{ano_anterior}"] = round(acum_receita_anterior, 2)
        data.append(entry)
    evento_nome = evento_id.replace("grp_", "") if is_grouped else str(projeto.evento or "")
    return {
        "status": "success",
        "modo": "mensal",
        "ano_atual": ano,
        "ano_anterior": ano_anterior,
        "data": data,
        "evento_nome": evento_nome,
        "ultima_atualizacao": datetime.now(ZoneInfo('America/Sao_Paulo')).isoformat()
    }


def _fetch_commercial_actions_from_db(db: Session, projeto_ids: list) -> list:
    """Always reads fresh from DB — never cached. Returns formatted commercial actions list."""
    if not projeto_ids:
        return []
    from ...models.dimensoes import AcaoComercial
    tipo_map = {
        'AUMENTO_PRECO': 'price_increase', 'REDUCAO_PRECO': 'price_decrease',
        'PROMOCAO': 'promotion', 'CAMPANHA': 'campaign', 'COMUNICACAO': 'communication',
        'NENHUMA_ACAO': 'communication', 'OUTROS': 'communication',
    }
    acoes = db.query(AcaoComercial).filter(
        AcaoComercial.projeto_id.in_(projeto_ids)
    ).order_by(AcaoComercial.data_acao.desc()).all()
    result = []
    for a in acoes:
        impacto = calculate_action_impact(db, a)
        ip = impacto.get("impacto_percentual")
        impact_str = (f"+{ip}%" if ip and ip > 0 else f"{ip}%") if ip is not None else None
        result.append({
            "id": str(a.id),
            "tipo": a.tipo,
            "type": tipo_map.get(a.tipo, 'communication'),
            "description": a.descricao,
            "date": a.data_acao.isoformat() if a.data_acao else None,
            "impact": impact_str,
            "vendas_antes": impacto.get("vendas_antes"),
            "vendas_depois": impacto.get("vendas_depois"),
            "impacto_percentual": ip,
            "status_impacto": impacto.get("status", "calculado") if ip is not None else "aguardando_dados",
            "ponto_corte": a.ponto_corte,
            "estagio": a.estagio,
            "snapshot_isc": float(a.snapshot_isc) if a.snapshot_isc is not None else None,
            "snapshot_isc_state": a.snapshot_isc_state,
            "snapshot_d_minus": a.snapshot_d_minus,
            "snapshot_ia730": float(a.snapshot_ia730) if a.snapshot_ia730 is not None else None,
            "snapshot_rolling14d": float(a.snapshot_rolling14d) if a.snapshot_rolling14d is not None else None,
            "snapshot_curva_percent": float(a.snapshot_curva_percent) if a.snapshot_curva_percent is not None else None,
            "snapshot_vendas_acumuladas": a.snapshot_vendas_acumuladas,
            "snapshot_playbook_letter": a.snapshot_playbook_letter,
        })
    return result


_cortesia_cache_result: set = set()
_cortesia_cache_ts: float = 0.0
_CORTESIA_CACHE_TTL: float = 60.0

def _get_cortesia_magento_ids(db: Session) -> set:
    """Return set of Magento event IDs (as strings) whose projeto/grupo has incluir_cortesias=True.
    
    Results are memoized for 60s to avoid repeated DB round-trips in hot paths.
    """
    global _cortesia_cache_result, _cortesia_cache_ts
    import time as _time
    now = _time.monotonic()
    if _cortesia_cache_result and (now - _cortesia_cache_ts) < _CORTESIA_CACHE_TTL:
        return _cortesia_cache_result

    cortesia_ids: set = set()
    proj_cortesia = db.query(DimProjeto).filter(DimProjeto.incluir_cortesias == True).all()
    proj_skus = set()
    for proj in proj_cortesia:
        if proj.codigo:
            proj_skus.add(proj.codigo.upper().strip())
    if proj_skus:
        mappings = db.query(SkuMapping).filter(
            SkuMapping.sku.in_(proj_skus),
            SkuMapping.fonte == 'MAGENTO',
            SkuMapping.ativo == True,
        ).all()
        for sm in mappings:
            if sm.id_externo:
                cortesia_ids.add(str(sm.id_externo))

    grupos_cortesia = db.query(EventoGrupoModel).filter(EventoGrupoModel.incluir_cortesias == True).all()
    if grupos_cortesia:
        grupo_nomes = [g.nome for g in grupos_cortesia]
        grupo_projs = db.query(DimProjeto).filter(DimProjeto.evento.in_(grupo_nomes)).all()
        grupo_proj_map: dict = {}
        for proj in grupo_projs:
            grupo_proj_map.setdefault(proj.evento, []).append(proj)

        grupo_skus = set()
        direct_grupo_nomes = []
        for grupo in grupos_cortesia:
            projs = grupo_proj_map.get(grupo.nome, [])
            if projs:
                for proj in projs:
                    if proj.codigo:
                        grupo_skus.add(proj.codigo.upper().strip())
            else:
                direct_grupo_nomes.append(grupo.nome)
        if grupo_skus:
            mappings = db.query(SkuMapping).filter(
                SkuMapping.sku.in_(grupo_skus),
                SkuMapping.fonte == 'MAGENTO',
                SkuMapping.ativo == True,
            ).all()
            for sm in mappings:
                if sm.id_externo:
                    cortesia_ids.add(str(sm.id_externo))
        if direct_grupo_nomes:
            mappings = db.query(SkuMapping).filter(
                SkuMapping.evento_grupo.in_(direct_grupo_nomes),
                SkuMapping.fonte == 'MAGENTO',
                SkuMapping.ativo == True,
            ).all()
            for sm in mappings:
                if sm.id_externo:
                    cortesia_ids.add(str(sm.id_externo))

    _cortesia_cache_result = cortesia_ids
    _cortesia_cache_ts = now
    return cortesia_ids

def _invalidate_cortesia_cache():
    global _cortesia_cache_result, _cortesia_cache_ts
    _cortesia_cache_result = set()
    _cortesia_cache_ts = 0.0


def _populate_cenarios_from_bundles(
    db: Session,
    bundle_to_cenario: dict,
    cenarios: dict,
    incluir_cortesias: bool = False,
) -> bool:
    """Populate cenarios dict with real sales data per bundle from Magento.

    First tries SkuMapping-based ISC lookup (legacy path). If no SkuMappings
    exist for bundles, falls back to direct Magento queries — using the same
    canonical filters as get_margem_por_kit (status set, state, GRUPOS, etc.).
    Returns True if data was populated.
    """
    from app.models.dimensoes import SkuMapping as _SM

    _sku_maps = db.query(_SM).filter(
        func.upper(_SM.fonte) == 'MAGENTO',
        _SM.id_externo.in_(list(bundle_to_cenario.keys())),
        _SM.ativo == True,
    ).all()
    _sku_to_cenario = {}
    for sm_row in _sku_maps:
        cenario_val = bundle_to_cenario.get(sm_row.id_externo)
        if cenario_val and sm_row.sku:
            _sku_to_cenario[normalize_sku(sm_row.sku)] = cenario_val

    if _sku_to_cenario:
        isc_data_cic = fetch_isc_pricing_data(db=db)
        for _sku_cic, _cenario_cic in _sku_to_cenario.items():
            _cic_info = isc_data_cic.get(_sku_cic, {})
            if _cic_info and _cenario_cic in cenarios:
                cenarios[_cenario_cic]["real_vendas"] = cenarios[_cenario_cic].get("real_vendas", 0) + _cic_info.get("qtd_site", 0)
                cenarios[_cenario_cic]["real_receita"] = round(cenarios[_cenario_cic].get("real_receita", 0) + _cic_info.get("receita_liquida_site", 0), 2)
        return True

    if not bundle_to_cenario or db_module.engine_magento is None:
        return False

    bundle_ids_int = [int(b) for b in bundle_to_cenario.keys()]

    # Cortesia filters use a SQL-level boolean parameter so query strings are static.
    # :skip_cortesia_filter = True  → OR short-circuits, filter is skipped
    # :skip_cortesia_filter = False → the filter condition is enforced
    _skip_cortesia_filter = bool(incluir_cortesias)

    _cic_count_q = text(
        "SELECT /*+ MAX_EXECUTION_TIME(20000) */\n"
        "    soi_parent.product_id AS bundle_id,\n"
        "    COUNT(DISTINCT soi_parent.item_id) AS qtd\n"
        "FROM sales_order so\n"
        "INNER JOIN sales_order_item soi_parent\n"
        "       ON soi_parent.order_id     = so.entity_id\n"
        "      AND soi_parent.product_type = 'bundle'\n"
        "      AND soi_parent.product_id   IN :bundle_ids\n"
        "WHERE\n"
        "    so.created_at >= DATE_SUB(CURDATE(), INTERVAL 2 YEAR)\n"
        "AND so.status IN ('processing', 'complete', 'approved', 'aprovado_link', 'reembolso_parcial', 'closed', 'retirado')\n"
        "AND so.state != 'canceled'\n"
        "AND (:skip_cortesia_filter OR so.base_grand_total > 0)\n"
        "AND (:skip_cortesia_filter OR NOT (so.discount_description LIKE '%%CORTESIA%%' AND so.base_grand_total < 50))\n"
        "AND so.created_at < CURDATE() + INTERVAL 1 DAY\n"
        "AND (so.discount_description IS NULL OR so.discount_description NOT LIKE '%%GRUPOS%%')\n"
        "AND (so.coupon_code IS NULL OR so.coupon_code NOT LIKE 'GRUP%%')\n"
        "AND so.increment_id NOT REGEXP '-[0-9]'\n"
        "GROUP BY soi_parent.product_id"
    ).bindparams(
        bindparam("bundle_ids", expanding=True),
        skip_cortesia_filter=_skip_cortesia_filter,
    )

    _cic_rev_q = text(
        "SELECT /*+ MAX_EXECUTION_TIME(55000) */\n"
        "    soi_parent.product_id AS bundle_id,\n"
        "    ROUND(SUM(soi_child.price - soi_child.discount_amount), 2) AS receita\n"
        "FROM sales_order so\n"
        "INNER JOIN sales_order_item soi_parent\n"
        "       ON soi_parent.order_id     = so.entity_id\n"
        "      AND soi_parent.product_type = 'bundle'\n"
        "      AND soi_parent.product_id   IN :bundle_ids\n"
        "INNER JOIN sales_order_item soi_child\n"
        "       ON soi_child.parent_item_id = soi_parent.item_id\n"
        "      AND soi_child.product_type   = 'simple'\n"
        "WHERE\n"
        "    so.created_at >= DATE_SUB(CURDATE(), INTERVAL 2 YEAR)\n"
        "AND so.status IN ('processing', 'complete', 'approved', 'aprovado_link', 'reembolso_parcial', 'closed', 'retirado')\n"
        "AND so.state != 'canceled'\n"
        "AND (:skip_cortesia_filter OR so.base_grand_total > 0)\n"
        "AND (:skip_cortesia_filter OR NOT (so.discount_description LIKE '%%CORTESIA%%' AND so.base_grand_total < 50))\n"
        "AND so.created_at < CURDATE() + INTERVAL 1 DAY\n"
        "AND (so.discount_description IS NULL OR so.discount_description NOT LIKE '%%GRUPOS%%')\n"
        "AND (so.coupon_code IS NULL OR so.coupon_code NOT LIKE 'GRUP%%')\n"
        "AND so.increment_id NOT REGEXP '-[0-9]'\n"
        "GROUP BY soi_parent.product_id"
    ).bindparams(
        bindparam("bundle_ids", expanding=True),
        skip_cortesia_filter=_skip_cortesia_filter,
    )

    try:
        with db_module.engine_magento.connect() as conn:
            count_rows = conn.execute(_cic_count_q, {"bundle_ids": bundle_ids_int}).mappings().all()
        for row in count_rows:
            bid = row['bundle_id']
            cen = bundle_to_cenario.get(bid) or bundle_to_cenario.get(str(bid))
            if cen and cen in cenarios:
                cenarios[cen]["real_vendas"] = cenarios[cen].get("real_vendas", 0) + int(row['qtd'] or 0)
        logger.info(f"[CenariosCiclismo] Magento count: {len(count_rows)} bundles")
    except Exception as e:
        logger.warning(f"[CenariosCiclismo] Magento count failed: {e}")
        return False

    try:
        with db_module.engine_magento.connect() as conn:
            rev_rows = conn.execute(_cic_rev_q, {"bundle_ids": bundle_ids_int}).mappings().all()
        for row in rev_rows:
            bid = row['bundle_id']
            cen = bundle_to_cenario.get(bid) or bundle_to_cenario.get(str(bid))
            if cen and cen in cenarios:
                cenarios[cen]["real_receita"] = round(cenarios[cen].get("real_receita", 0) + float(row['receita'] or 0), 2)
        logger.info(f"[CenariosCiclismo] Magento revenue: {len(rev_rows)} bundles")
        return len(count_rows) > 0
    except Exception as e:
        logger.warning(f"[CenariosCiclismo] Magento revenue failed: {e}")
        return len(count_rows) > 0


@router.patch("/eventos/{evento_id}/cortesias")
def toggle_cortesias(
    evento_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_admin()),
):
    from ...services.snapshot_service import consolidar_vendas_grupo as _consolidar
    from datetime import date as _date_cls

    is_grouped = evento_id.startswith("grp_")
    reconsolidate_grupos: list = []
    ano = _date_cls.today().year

    if is_grouped:
        grupo_nome = evento_id.replace("grp_", "")
        grupo = db.query(EventoGrupoModel).filter(EventoGrupoModel.nome == grupo_nome).first()
        if not grupo:
            raise HTTPException(status_code=404, detail="Grupo de evento não encontrado")
        grupo.incluir_cortesias = not grupo.incluir_cortesias
        db.commit()
        db.refresh(grupo)
        reconsolidate_grupos.append(grupo_nome)
        event_detail_cache.invalidate()
        eventos_list_cache.invalidate()
        result_flag = grupo.incluir_cortesias
    else:
        projeto = db.query(DimProjeto).filter(DimProjeto.id == int(evento_id)).first()
        if not projeto:
            raise HTTPException(status_code=404, detail="Projeto não encontrado")
        projeto.incluir_cortesias = not projeto.incluir_cortesias
        db.commit()
        db.refresh(projeto)
        if projeto.evento:
            reconsolidate_grupos.append(projeto.evento)
        event_detail_cache.invalidate()
        eventos_list_cache.invalidate()
        result_flag = projeto.incluir_cortesias

    _invalidate_cortesia_cache()

    def _reconsolidate_snapshot(grupos: list, year: int):
        try:
            from ...core.database import SessionLocal
            with SessionLocal() as snap_db:
                for g in grupos:
                    _consolidar(snap_db, g, year)
                    logger.info(f"[Cortesia Toggle] Reconsolidated snapshot for grupo='{g}', ano={year}")
            event_detail_cache.invalidate()
            eventos_list_cache.invalidate()
            logger.info("[Cortesia Toggle] Caches re-invalidated after snapshot reconsolidation")
        except Exception as e:
            logger.error(f"[Cortesia Toggle] Snapshot reconsolidation failed: {e}")

    if reconsolidate_grupos:
        background_tasks.add_task(_reconsolidate_snapshot, reconsolidate_grupos, ano)

    return {"incluirCortesias": result_flag}


@router.get("/eventos/{evento_id}")
def get_marketing_event_by_id(
    evento_id: str,
    ano: int = Query(default=None, description="Ano para evento consolidado"),
    force_refresh: bool = Query(default=False, description="Forçar atualização dos dados ignorando cache"),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
    response: Response = None
):
    """
    Retorna os dados de um evento específico pelo ID.
    Suporta IDs de EventoGrupo (prefixo 'grp_') e DimProjeto (número puro).
    """
    isc_cfg = _get_isc_settings(db)
    is_grouped = evento_id.startswith("grp_")

    # ── FAST PATH: snapshot persistente em PostgreSQL ──────────────────────────
    # Sobrevive a restarts do servidor e à invalidação do cache em memória.
    # O scheduler atualiza este snapshot a cada 30 min em background.
    # Resolve o `ano` efetivo aqui (mesma lógica usada nos branches abaixo)
    # para garantir que a chave de leitura/escrita seja consistente.
    if ano is not None:
        _ano_for_persist = ano
    elif is_grouped:
        _ano_for_persist = datetime.now().year
    else:
        try:
            _proj_for_year = _wq_dim_projeto_by_id(db, int(evento_id))
            _ano_for_persist = (_proj_for_year.data_evento.year
                                if _proj_for_year and _proj_for_year.data_evento
                                else datetime.now().year)
        except Exception:
            _ano_for_persist = datetime.now().year
    # Snapshot-first read. O recomputo "force_refresh=True" só faz bypass quando
    # disparado internamente (scheduler/warmup com current_user=None). Cliques de
    # usuário com force_refresh=True são tratados como pedido de refresh em
    # background: servimos snapshot+overlay imediatamente e enfileiramos recompute.
    _internal_recompute = force_refresh and current_user is None
    _user_refresh_request = force_refresh and current_user is not None
    _USE_SNAPSHOT_FIRST = os.getenv("USE_SNAPSHOT_FIRST_READ", "true").lower() not in ("0", "false", "no")
    if _USE_SNAPSHOT_FIRST and not _internal_recompute:
        try:
            from ...services.event_detail_snapshot_service import (
                get_persisted_detail as _gpd,
                apply_today_overlay as _apply_overlay,
            )
            _persisted = _gpd(db, evento_id, _ano_for_persist)
        except Exception:
            _persisted = None
        if _persisted is not None:
            from app.core.cache import (
                get_last_full_refresh as _gpd_lfr,
                get_last_sync_hoje as _gpd_lsh,
            )
            _gpd_lfr_ts = _gpd_lfr() or 0
            _gpd_lsh_ts = _gpd_lsh() or 0
            _gpd_comp = _persisted.get("computed_at")
            _gpd_comp_ts = _gpd_comp.timestamp() if _gpd_comp else 0
            _gpd_completed = _persisted.get("is_completed", False)
            _gpd_payload_version = (_persisted["payload"] or {}).get("_cache_version") if isinstance(_persisted["payload"], dict) else None
            _gpd_version_mismatch = _gpd_payload_version != _DETAIL_CACHE_VERSION
            # Safety guard: se a versão mudou, só servimos o snapshot se ele tem
            # as chaves essenciais que o frontend exige. Caso contrário caímos
            # para o caminho lento (mantém o comportamento seguro pré-refactor
            # quando há um bump de schema realmente incompatível).
            if _gpd_version_mismatch:
                _pl = _persisted["payload"] if isinstance(_persisted["payload"], dict) else {}
                _evt_chk = _pl.get("evento") if isinstance(_pl, dict) else None
                _has_essentials = (
                    isinstance(_evt_chk, dict)
                    and "currentSales" in _evt_chk
                    and "salesGoal" in _evt_chk
                    and isinstance(_pl.get("dailySales"), list)
                )
                if not _has_essentials:
                    logger.warning(
                        f"[Persist] '{_ano_for_persist}_{evento_id}' version mismatch "
                        f"({_gpd_payload_version} != {_DETAIL_CACHE_VERSION}) AND missing essential "
                        f"keys — bypassing snapshot, fallback ao recompute síncrono"
                    )
                    _persisted = None
        if _persisted is not None:
            # Stale se: (a) usuário pediu refresh, (b) versão do schema mudou,
            # (c) evento ativo e snapshot mais antigo que último warmup ou >30 min.
            _gpd_age = (datetime.now() - _gpd_comp.replace(tzinfo=None)).total_seconds() if _gpd_comp else 9999
            _gpd_stale = (
                _user_refresh_request
                or _gpd_version_mismatch
                or (
                    (not _gpd_completed)
                    and ((_gpd_lfr_ts and _gpd_comp_ts < _gpd_lfr_ts) or _gpd_age > 1800)
                )
            )
            _gpd_key = f"{_ano_for_persist}_{evento_id}_detail"
            if _gpd_stale and _gpd_key not in _swr_recompute_in_progress:
                _reason = (
                    "user refresh" if _user_refresh_request
                    else "version mismatch" if _gpd_version_mismatch
                    else f"age={_gpd_age:.0f}s"
                )
                logger.info(f"[Persist] '{_gpd_key}' stale ({_reason}) — serving snapshot+overlay + bg refresh")
                _swr_recompute_in_progress.add(_gpd_key)
                import threading as _gpd_threading
                def _gpd_bg():
                    from ...core.database import SessionLocal as _GPD_SL
                    _gpd_db = _GPD_SL()
                    try:
                        get_marketing_event_by_id(
                            evento_id=evento_id, ano=_ano_for_persist,
                            force_refresh=True, db=_gpd_db, current_user=None,
                        )
                    except Exception as _gpd_e:
                        logger.warning(f"[Persist] bg refresh '{_gpd_key}' failed: {_gpd_e}")
                    finally:
                        _gpd_db.close()
                        _swr_recompute_in_progress.discard(_gpd_key)
                _gpd_threading.Thread(target=_gpd_bg, daemon=True).start()
            _gpd_payload = _persisted["payload"] if isinstance(_persisted["payload"], dict) else {}
            # Aplica overlay de HOJE (currentSales, dailySales[hoje], averageTicket)
            try:
                _gpd_payload = _apply_overlay(db, _gpd_payload, evento_id)
            except Exception as _ov_e:
                logger.warning(f"[Persist] apply_today_overlay '{_gpd_key}' falhou: {_ov_e}")
            _gpd_result = dict(_gpd_payload)
            _gpd_result["ultima_atualizacao_completa"] = (
                datetime.fromtimestamp(_gpd_lfr_ts, tz=ZoneInfo('America/Sao_Paulo')).isoformat()
                if _gpd_lfr_ts else None
            )
            # snapshot computed_at (timestamp do recompute completo deste evento)
            if _gpd_comp:
                try:
                    _gpd_comp_aware = _gpd_comp if _gpd_comp.tzinfo else _gpd_comp.replace(tzinfo=ZoneInfo('America/Sao_Paulo'))
                    _gpd_result["snapshot_computed_at"] = _gpd_comp_aware.isoformat()
                except Exception:
                    pass
            _gpd_pids = [p["id"] for p in _gpd_result.get("projetos_vinculados", [])]
            if not _gpd_pids and not is_grouped:
                try:
                    _gpd_pids = [int(evento_id)]
                except (ValueError, TypeError):
                    pass
            _gpd_result["commercialActions"] = _fetch_commercial_actions_from_db(db, _gpd_pids)
            if response is not None:
                response.headers["X-Data-Stale"] = "true" if _gpd_stale else "false"
                if _gpd_version_mismatch:
                    response.headers["X-Schema-Stale"] = "true"
            return _gpd_result

    # ── NUNCA RECOMPUTAR SÍNCRONO PARA REQUEST DE USUÁRIO ─────────────────────
    # Se chegamos aqui via clique de usuário (current_user is not None) e o
    # snapshot não estava disponível (não existe ainda, ou foi descartado por
    # version mismatch sem chaves essenciais), enfileiramos um recompute em
    # background e retornamos um payload "preparing". O frontend mostra um
    # skeleton e fica fazendo polling. Apenas chamadas internas
    # (current_user=None: scheduler, warmup, SWR) seguem para o caminho lento.
    if (
        _USE_SNAPSHOT_FIRST
        and current_user is not None
        and not _internal_recompute
    ):
        _prep_key = f"{_ano_for_persist}_{evento_id}_detail"
        if _prep_key not in _swr_recompute_in_progress:
            _swr_recompute_in_progress.add(_prep_key)
            import threading as _prep_threading
            def _prep_bg():
                from ...core.database import SessionLocal as _PREP_SL
                _prep_db = _PREP_SL()
                try:
                    get_marketing_event_by_id(
                        evento_id=evento_id, ano=_ano_for_persist,
                        force_refresh=True, db=_prep_db, current_user=None,
                    )
                except Exception as _prep_e:
                    logger.warning(f"[Prepare] bg recompute '{_prep_key}' falhou: {_prep_e}")
                finally:
                    _prep_db.close()
                    _swr_recompute_in_progress.discard(_prep_key)
            _prep_threading.Thread(target=_prep_bg, daemon=True).start()
            logger.info(f"[Prepare] '{_prep_key}' sem snapshot — retornando preparing + bg recompute")
        else:
            logger.info(f"[Prepare] '{_prep_key}' sem snapshot — bg já em andamento, retornando preparing")
        if response is not None:
            response.headers["X-Data-Stale"] = "true"
            response.headers["X-Data-Preparing"] = "true"
        return {
            "status": "preparing",
            "evento_id": evento_id,
            "ano": _ano_for_persist,
            "message": "Estamos preparando este evento. Em alguns segundos os dados aparecem aqui.",
            "retry_after_seconds": 5,
        }

    def _swr_detail_refresh(_swr_key: str):
        from ...core.database import SessionLocal
        _db = SessionLocal()
        try:
            get_marketing_event_by_id(evento_id=evento_id, ano=ano, force_refresh=True, db=_db, current_user=None)
        finally:
            _db.close()
            _swr_recompute_in_progress.discard(_swr_key)

    if is_grouped:
        grupo_nome = evento_id.replace("grp_", "")
        grupo = db.query(EventoGrupoModel).filter(EventoGrupoModel.nome == grupo_nome).first()
        if not grupo:
            raise HTTPException(status_code=404, detail="Grupo de evento não encontrado")
        
        if ano is None:
            ano = datetime.now().year
        
        detail_cache_key = f"{ano}_{evento_id}_detail"
        if not force_refresh:
            cached_detail, is_stale = event_detail_cache.get_or_revalidate(detail_cache_key, refresh_fn=None)
            if cached_detail is not None:
                # Validate that cached data has a non-empty event date.
                # Entries cached before DimProjeto was synced may have date="" which
                # causes NaN/missing info on the frontend.
                # Strategy: return stale data immediately (avoids long blocking load)
                # and trigger a background refresh so the frontend re-fetches with
                # correct data in a few seconds (stale-while-revalidate pattern).
                _cached_evt = cached_detail.get("evento", {})
                _cached_date = (
                    _cached_evt.get("date", "") if isinstance(_cached_evt, dict)
                    else getattr(_cached_evt, "date", "")
                )
                # SWR trigger: recompute when _computed_at_date is missing or cache version is outdated.
                # Freshness is also owned by:
                #   (a) event_detail_cache.invalidate() called by sincronizar_hoje_batch after sync
                #   (b) SmartCache TTL-based SWR for natural expiry
                _cached_version = cached_detail.get("_cache_version")
                _needs_recompute = not _cached_date or _cached_version != _DETAIL_CACHE_VERSION
                if _needs_recompute:
                    if detail_cache_key not in _swr_recompute_in_progress:
                        reason = "empty date" if not _cached_date else f"version mismatch ({_cached_version} != {_DETAIL_CACHE_VERSION})"
                        logger.info(f"[Cache] event_detail '{detail_cache_key}' {reason} — serving stale + triggering background recompute")
                        _swr_recompute_in_progress.add(detail_cache_key)
                        import threading as _threading
                        _threading.Thread(target=_swr_detail_refresh, args=(detail_cache_key,), daemon=True).start()
                    else:
                        logger.info(f"[Cache] event_detail '{detail_cache_key}' SWR already in progress — skipping duplicate thread")
                    is_stale = True  # force stale header

                if response is not None:
                    response.headers["X-Data-Stale"] = "true" if is_stale else "false"
                # Always inject current ultima_atualizacao_completa so frontend can detect stale event caches
                from app.core.cache import get_last_full_refresh as _get_lfr
                _lfr_ts = _get_lfr()
                _lfr_str = (
                    datetime.fromtimestamp(_lfr_ts, tz=ZoneInfo('America/Sao_Paulo')).isoformat()
                    if _lfr_ts else None
                )
                result_hit = {k: v for k, v in cached_detail.items() if k != "__is_completed"}
                result_hit["ultima_atualizacao_completa"] = _lfr_str
                # Force cacheTime < systemRefresh so frontend's stale check triggers a silent re-fetch
                if _needs_recompute:
                    result_hit["ultima_atualizacao"] = "2000-01-01T00:00:00-03:00"
                # Always fetch commercial actions fresh (never from cache)
                _ca_pids = [p["id"] for p in result_hit.get("projetos_vinculados", [])]
                if not _ca_pids:
                    try:
                        _ca_pids = [int(evento_id)]
                    except (ValueError, TypeError):
                        pass
                result_hit["commercialActions"] = _fetch_commercial_actions_from_db(db, _ca_pids)
                return result_hit

        # Concurrent computation guard: if another request is already computing this
        # event detail, wait for it instead of launching a duplicate Magento query.
        _should_compute = True
        _wait_computing_event = None
        if not force_refresh:
            with _event_computing_lock:
                if detail_cache_key in _event_computing_events:
                    _wait_computing_event = _event_computing_events[detail_cache_key]
                else:
                    _compute_done_event = _threading_module.Event()
                    _event_computing_events[detail_cache_key] = _compute_done_event

        if _wait_computing_event is not None:
            logger.info(f"[Cache] event_detail '{detail_cache_key}' being computed by another thread — waiting (max 5min)")
            _wait_computing_event.wait(timeout=300)
            # Try cache now that the other thread finished
            _cached2, _ = event_detail_cache.get_or_revalidate(detail_cache_key, refresh_fn=None)
            if _cached2 is not None:
                from app.core.cache import get_last_full_refresh as _get_lfr2
                _lfr_ts2 = _get_lfr2()
                _lfr_str2 = datetime.fromtimestamp(_lfr_ts2, tz=ZoneInfo('America/Sao_Paulo')).isoformat() if _lfr_ts2 else None
                _res2 = {k: v for k, v in _cached2.items() if k != "__is_completed"}
                _res2["ultima_atualizacao_completa"] = _lfr_str2
                _ca_pids2 = [p["id"] for p in _res2.get("projetos_vinculados", [])]
                if not _ca_pids2:
                    try:
                        _ca_pids2 = [int(evento_id)]
                    except (ValueError, TypeError):
                        pass
                _res2["commercialActions"] = _fetch_commercial_actions_from_db(db, _ca_pids2)
                return _res2
            # Computing thread failed or timed out — fall through to compute ourselves
            with _event_computing_lock:
                if detail_cache_key not in _event_computing_events:
                    _compute_done_event = _threading_module.Event()
                    _event_computing_events[detail_cache_key] = _compute_done_event
            _should_compute = True

        mappings = _wq_sku_mappings_by_grupo_single_year(db, grupo_nome, ano)
        
        skus = [m.sku for m in mappings]
        
        proj_skus = list(set(m.sku for m in mappings))
        projetos_raw = _wq_dim_projetos_by_codigos(db, proj_skus)
        seen_proj_ids = set()
        projetos = []
        for p in projetos_raw:
            if p.id not in seen_proj_ids:
                seen_proj_ids.add(p.id)
                projetos.append(p)
        
        latest_date = None
        rep_projeto = projetos[0] if projetos else None
        for p in projetos:
            if p.data_evento:
                if latest_date is None or p.data_evento > latest_date:
                    latest_date = p.data_evento
                    rep_projeto = p
        
        total_capacity = get_meta_orcada_projetos(db, projetos)
        projeto_data_evento = latest_date
        dias_enc = get_dias_encerramento(db, projeto_id=rep_projeto.id) if rep_projeto else 2
        d_minus_inscricoes = calculate_d_minus(projeto_data_evento, reference_year=ano, dias_encerramento=dias_enc) if projeto_data_evento else 0
        d_minus = calculate_d_minus(projeto_data_evento, reference_year=ano, dias_encerramento=0) if projeto_data_evento else 0
        is_active = d_minus_inscricoes > 0 if ano == datetime.now().year else True
        sales_goal = total_capacity
        
        data_fim_inscricoes = projeto_data_evento - timedelta(days=dias_enc) if projeto_data_evento else None
        detail_regime = get_data_regime(projeto_data_evento, dias_enc) if projeto_data_evento else "live"
        
        detail_hist_pattern = None
        detail_curva_info = {"tipo_curva": "linear", "fonte_curva": None, "ano_referencia": None}
        _rep_estado = str(rep_projeto.estado) if rep_projeto and rep_projeto.estado else None
        try:
            detail_hist_pattern, detail_curva_info = _resolve_hist_pattern(db, grupo_nome, ano, estado=_rep_estado)
        except Exception:
            pass
        
        current_year = datetime.now().year
        if force_refresh and ano == current_year and detail_regime != "consolidated":
            _should_rebuild = True
            try:
                from ...models.vendas_snapshot import VendasDiariaSnapshot as _VDS
                _last_updated = db.query(func.max(_VDS.updated_at)).filter(
                    _VDS.evento_grupo == grupo_nome
                ).scalar()
                if _last_updated and (datetime.now() - _last_updated).total_seconds() < 600:
                    _should_rebuild = False
                    logger.info(f"Snapshot cooldown: '{grupo_nome}' atualizado há {(datetime.now() - _last_updated).total_seconds():.0f}s, pulando rebuild")
            except Exception:
                pass
            if _should_rebuild:
                try:
                    from ...services.snapshot_service import consolidar_vendas_grupo
                    consolidar_vendas_grupo(db, grupo_nome, ano)
                    logger.info(f"Snapshot reconstruído (force_refresh) para '{grupo_nome}' ano={ano}")
                except Exception as _e:
                    logger.warning(f"Falha ao reconstruir snapshot para '{grupo_nome}': {_e}")
        elif detail_regime == "consolidated" and ano == current_year:
            _existing_snap = _get_snapshot_metrics_for_grupo(db, grupo_nome)
            if not _existing_snap:
                logger.info(f"[Hybrid] Evento '{grupo_nome}' é consolidated sem snapshot — construindo")
                try:
                    from ...services.snapshot_service import consolidar_vendas_grupo
                    consolidar_vendas_grupo(db, grupo_nome, ano)
                    logger.info(f"Snapshot construído (consolidated, sem snapshot) para '{grupo_nome}' ano={ano}")
                except Exception as _e:
                    logger.warning(f"Falha ao construir snapshot consolidated para '{grupo_nome}': {_e}")
            else:
                logger.info(f"[Hybrid] Evento '{grupo_nome}' é consolidated — snapshot existente, pulando rebuild")

        daily_sales_list = fetch_real_daily_sales_for_projetos(db, projetos, sales_goal=sales_goal, ano=ano, evento_grupo=grupo_nome, data_evento=data_fim_inscricoes, preloaded_hist_pattern=detail_hist_pattern, data_evento_real=projeto_data_evento)
        daily_sales_dict = {date.fromisoformat(d['date']): d['sales'] for d in daily_sales_list}
        
        _today_detail = today_brazil()
        current_sales = 0
        if daily_sales_dict and len(daily_sales_dict) > 0:
            current_sales = sum(v for k, v in daily_sales_dict.items() if k <= _today_detail)
        
        if ano == current_year and detail_regime == "consolidated":
            snap = _get_snapshot_metrics_for_grupo(db, grupo_nome)
            if snap is not None:
                current_receita = snap['receita_liquida_site']
                if current_sales == 0:
                    current_sales = snap['qtd_site']
            else:
                isc_data = fetch_isc_pricing_data(db=db)
                current_receita = 0.0
                seen_norms = set()
                for s_sku in skus:
                    s_norm = normalize_sku(s_sku)
                    if s_norm in seen_norms:
                        continue
                    seen_norms.add(s_norm)
                    info = isc_data.get(s_norm, {})
                    current_receita += info.get('receita_liquida_site', 0.0)
            grupo_media_14d = 0.0
            grupo_media_7d = 0.0
            grupo_media_30d = 0.0
        elif ano == current_year:
            isc_data = fetch_isc_pricing_data(db=db)
            current_receita = 0.0
            current_sales_isc = 0  # from ISC cache, same source as list view
            grupo_media_14d = 0.0
            grupo_media_7d = 0.0
            grupo_media_30d = 0.0
            seen_norms = set()
            for s_sku in skus:
                s_norm = normalize_sku(s_sku)
                if s_norm in seen_norms:
                    continue
                seen_norms.add(s_norm)
                info = isc_data.get(s_norm, {})
                current_receita += info.get('receita_liquida_site', 0.0)
                current_sales_isc += info.get('qtd_site', 0)
                grupo_media_14d += info.get('media_14d', 0.0)
                grupo_media_7d += info.get('media_7d', 0.0)
                grupo_media_30d += info.get('media_30d', 0.0)
            # Align current_sales with ISC cache so ISC calc is identical to list view.
            # Take the higher value: ISC cache (snapshot-based, updated every 30 min) vs
            # daily_sales live query (which may include inscriptions made since last sync).
            # Using max() ensures new inscriptions made after the last auto-sync are visible.
            if current_sales_isc > current_sales:
                current_sales = current_sales_isc
        else:
            ativo_ids = [str(m.id_externo) for m in mappings if m.fonte == 'ATIVO' and m.id_externo]
            magento_ids = [str(m.id_externo) for m in mappings if m.fonte == 'MAGENTO' and m.id_externo]
            
            current_receita = 0.0
            
            if ativo_ids:
                ativo_rows = _fetch_daily_sales_ativo_by_ids(list(set(ativo_ids)))
                for row in ativo_rows:
                    current_receita += row.get('receita', 0.0)
            
            if magento_ids:
                _cort_det = _get_cortesia_magento_ids(db)
                _mag_cort_det = set(magento_ids) & _cort_det if _cort_det else None
                magento_rows = _fetch_daily_sales_magento_by_ids(list(set(magento_ids)), cortesia_magento_ids=_mag_cort_det if _mag_cort_det else None)
                for row in magento_rows:
                    current_receita += row.get('receita', 0.0)
            
            grupo_media_14d = 0.0
            grupo_media_7d = 0.0
            grupo_media_30d = 0.0
        
        avg_ticket = round(current_receita / current_sales, 2) if current_sales > 0 else 0.0
        
        detail_bt_total_receita = 0.0
        detail_bt_total_qtd = 0
        for p in projetos:
            detail_cad = _wq_cadastro_by_projeto_id(db, p.id)
            if detail_cad and detail_cad.atletas_site_tkt_medio and detail_cad.atletas_site_pago:
                detail_bt_total_receita += float(detail_cad.atletas_site_tkt_medio) * int(detail_cad.atletas_site_pago)
                detail_bt_total_qtd += int(detail_cad.atletas_site_pago)
        detail_budget_ticket = round(detail_bt_total_receita / detail_bt_total_qtd, 2) if detail_bt_total_qtd > 0 else 0.0
        
        # Use ISC cache medias for the ISC component calculation so that the
        # detail view produces the same ISC value as the list view (consistency).
        # daily_sales_dict is still included in the response payload for charts.
        _has_cache_medias = (grupo_media_14d > 0 or grupo_media_7d > 0)
        if _has_cache_medias:
            isc_components = calculate_isc_components(
                current_sales, sales_goal, d_minus_inscricoes,
                media_7d=grupo_media_7d if grupo_media_7d > 0 else None,
                media_14d=grupo_media_14d if grupo_media_14d > 0 else None,
                media_30d=grupo_media_30d if grupo_media_30d > 0 else None,
                hist_pattern=detail_hist_pattern,
                registration_close_date=data_fim_inscricoes,
                curva_info=detail_curva_info)
        else:
            isc_components = calculate_isc_components(current_sales, sales_goal, d_minus_inscricoes,
                                                       daily_sales_dict=daily_sales_dict,
                                                       hist_pattern=detail_hist_pattern,
                                                       registration_close_date=data_fim_inscricoes,
                                                       curva_info=detail_curva_info)
        isc = calculate_isc(isc_components, isc_cfg["ia730Weight"], isc_cfg["curvaDWeight"], isc_cfg["rolling14dWeight"])
        isc_status = get_isc_status(isc, isc_cfg["greenThreshold"], isc_cfg["yellowThreshold"])
        suggested_action = get_suggested_action(isc, d_minus_inscricoes, isc_cfg["greenThreshold"], isc_cfg["yellowThreshold"], isc_cfg["promotionDeadline"])
        
        projeto_modalidade = str(rep_projeto.modalidade) if rep_projeto and rep_projeto.modalidade else None
        projeto_cidade = str(rep_projeto.cidade) if rep_projeto and rep_projeto.cidade else None
        projeto_estado = str(rep_projeto.estado) if rep_projeto and rep_projeto.estado else None
        
        detail_kit_ids = [p.id for p in projetos]
        detail_kit_costs = get_kit_basico_costs_batch(db, detail_kit_ids) if detail_kit_ids else {}
        detail_kit_w_num = 0.0
        detail_kit_w_den = 0
        for p in projetos:
            p_cad_d = _wq_cadastro_by_projeto_id(db, p.id)
            p_cap_d = get_meta_from_cadastro(p_cad_d) if p_cad_d else get_meta_orcada(db, p.id)
            p_kc_d = detail_kit_costs.get(p.id, 50.0)
            detail_kit_w_num += p_kc_d * p_cap_d
            detail_kit_w_den += p_cap_d
        detail_kit_cost_avg = (detail_kit_w_num / detail_kit_w_den) if detail_kit_w_den > 0 else 50.0
        detail_margin = _calc_margin_fields(detail_budget_ticket, detail_kit_cost_avg, sales_goal,
                                             avg_ticket, current_sales, current_receita)
        
        detail_ticket_atual_map = _get_ticket_atual_map(db)
        detail_ticket_atual = _get_ticket_atual_for_event(detail_ticket_atual_map, [p.id for p in projetos])
        detail_ticket_kit_nome = _get_ticket_atual_kit_nome_for_event(detail_ticket_atual_map, [p.id for p in projetos])
        
        grupo_projeto_ids = [p.id for p in projetos]
        _grupo_incluir_cortesias = bool(getattr(grupo, 'incluir_cortesias', False))
        _detail_margem_avisos: list = []
        detail_margem_por_kit = get_margem_por_kit(
            db,
            grupo_projeto_ids,
            ano=ano,
            card_total_qty=current_sales,
            card_total_receita=current_receita,
            card_kit_cost_avg=detail_kit_cost_avg,
            avisos_out=_detail_margem_avisos,
            force_refresh=force_refresh,
            incluir_cortesias=_grupo_incluir_cortesias,
        )
        # Align currentSales with the kit table total so the card and the
        # "Margem por Tipo de Kit" table always display the same number of athletes.
        # The kit table counts only Magento bundles registered in KitConfig; the
        # snapshot/ISC-cache count is broader. ISC was already calculated above, so
        # changing current_sales here does NOT affect the displayed ISC value.
        _kit_rows_aligned = [r for r in (detail_margem_por_kit or []) if r.get('tipoKit') != 'CONSOLIDADO']
        _kit_total_qty_aligned = sum(int(r.get('qtd', 0) or 0) for r in _kit_rows_aligned)
        if _kit_total_qty_aligned > 0 and _kit_total_qty_aligned != current_sales:
            logger.info(
                f"[Detalhe] Alinhando currentSales '{grupo_nome}': {current_sales} → {_kit_total_qty_aligned} "
                f"(diff={current_sales - _kit_total_qty_aligned})"
            )
            current_sales = _kit_total_qty_aligned
            avg_ticket = round(current_receita / current_sales, 2) if current_sales > 0 else avg_ticket
            detail_margin = _calc_margin_fields(detail_budget_ticket, detail_kit_cost_avg, sales_goal,
                                                 avg_ticket, current_sales, current_receita)

        detail_consistency_warning = None  # aligned above; retained field for API compatibility
        detail_detalhe_vendas = []
        detail_kit_query_failed = False
        if detail_regime == "consolidated":
            detail_detalhe_ativo = []
        else:
            detail_detalhe_ativo = get_detalhe_vendas_ativo(db, grupo_projeto_ids, ano=ano)
        
        evento = MarketingEvent(
            id=evento_id,
            name=grupo.nome,
            date=projeto_data_evento.isoformat() if projeto_data_evento else "",
            location=projeto_cidade or projeto_estado or "Não definido",
            category=projeto_modalidade or "Corrida",
            totalCapacity=sales_goal,
            currentSales=current_sales,
            salesGoal=sales_goal,
            averageTicket=round(avg_ticket, 2),
            budgetTicket=detail_budget_ticket,
            dMinus=d_minus,
            dMinusInscricoes=d_minus_inscricoes,
            isc=isc,
            iscComponents=isc_components,
            iscStatus=isc_status,
            suggestedAction=suggested_action,
            isActive=is_active,
            sku=",".join(skus),
            ticketAtual=detail_ticket_atual,
            ticketKitNome=detail_ticket_kit_nome,
            margemPorKit=detail_margem_por_kit if detail_margem_por_kit else None,
            margemAvisos=_detail_margem_avisos if _detail_margem_avisos else None,
            consistencyWarning=detail_consistency_warning,
            kitQueryFailed=detail_kit_query_failed,
            detalheVendasPorKit=detail_detalhe_vendas if detail_detalhe_vendas else None,
            detalheVendasAtivoKit=detail_detalhe_ativo if detail_detalhe_ativo else None,
            dataRegime=detail_regime,
            incluirCortesias=_grupo_incluir_cortesias,
            **detail_margin
        )
        
        daily_sales = daily_sales_list
        
        from ...models.dimensoes import AcaoComercial
        commercial_actions = []
        projeto_ids = [p.id for p in projetos]
        if projeto_ids:
            acoes = db.query(AcaoComercial).filter(
                AcaoComercial.projeto_id.in_(projeto_ids)
            ).order_by(AcaoComercial.data_acao.desc()).all()
            
            for a in acoes:
                tipo_map = {
                    'AUMENTO_PRECO': 'price_increase',
                    'REDUCAO_PRECO': 'price_decrease',
                    'PROMOCAO': 'promotion',
                    'CAMPANHA': 'campaign',
                    'COMUNICACAO': 'communication'
                }
                impacto = calculate_action_impact(db, a)
                impacto_percentual = impacto.get("impacto_percentual")
                vendas_antes = impacto.get("vendas_antes")
                vendas_depois = impacto.get("vendas_depois")
                impact_str = f"+{impacto_percentual}%" if impacto_percentual and impacto_percentual > 0 else (f"{impacto_percentual}%" if impacto_percentual is not None else None)
                commercial_actions.append({
                    "id": str(a.id),
                    "type": tipo_map.get(a.tipo, 'communication'),
                    "description": a.descricao,
                    "date": a.data_acao.isoformat() if a.data_acao else None,
                    "impact": impact_str,
                    "vendas_antes": vendas_antes,
                    "vendas_depois": vendas_depois,
                    "impacto_percentual": impacto_percentual,
                    "status_impacto": impacto.get("status", "calculado") if impacto_percentual is not None else "aguardando_dados",
                    "ponto_corte": a.ponto_corte,
                    "estagio": a.estagio,
                    "snapshot_isc": float(a.snapshot_isc) if a.snapshot_isc is not None else None,
                    "snapshot_isc_state": a.snapshot_isc_state,
                    "snapshot_d_minus": a.snapshot_d_minus,
                    "snapshot_ia730": float(a.snapshot_ia730) if a.snapshot_ia730 is not None else None,
                    "snapshot_rolling14d": float(a.snapshot_rolling14d) if a.snapshot_rolling14d is not None else None,
                    "snapshot_curva_percent": float(a.snapshot_curva_percent) if a.snapshot_curva_percent is not None else None,
                    "snapshot_vendas_acumuladas": a.snapshot_vendas_acumuladas,
                    "snapshot_playbook_letter": a.snapshot_playbook_letter,
                })
        
        ano_anterior = ano - 1
        mappings_anterior = _wq_sku_mappings_by_grupo_single_year(db, grupo_nome, ano_anterior)
        
        comparacao_anual = None
        if mappings_anterior:
            skus_anterior = [m.sku for m in mappings_anterior]
            
            vendas_anterior = 0
            receita_anterior = 0.0
            
            if ano_anterior == current_year:
                isc_data_comp = fetch_isc_pricing_data(db=db) if ano != current_year else isc_data
                seen_norms_ant = set()
                for s_sku in skus_anterior:
                    s_norm = normalize_sku(s_sku)
                    if s_norm in seen_norms_ant:
                        continue
                    seen_norms_ant.add(s_norm)
                    info = isc_data_comp.get(s_norm, {})
                    vendas_anterior += info.get('qtd_site', 0)
                    receita_anterior += info.get('receita_liquida_site', 0.0)
            else:
                ant_ativo_ids = [str(m.id_externo) for m in mappings_anterior if m.fonte == 'ATIVO' and m.id_externo]
                ant_magento_ids = [str(m.id_externo) for m in mappings_anterior if m.fonte == 'MAGENTO' and m.id_externo]
                if ant_ativo_ids:
                    for row in _fetch_daily_sales_ativo_by_ids(list(set(ant_ativo_ids))):
                        vendas_anterior += row.get('qtd', 0)
                        receita_anterior += row.get('receita', 0.0)
                if ant_magento_ids:
                    _cort_ant = _get_cortesia_magento_ids(db)
                    _mag_cort_ant = set(ant_magento_ids) & _cort_ant if _cort_ant else None
                    for row in _fetch_daily_sales_magento_by_ids(list(set(ant_magento_ids)), cortesia_magento_ids=_mag_cort_ant if _mag_cort_ant else None):
                        vendas_anterior += row.get('qtd', 0)
                        receita_anterior += row.get('receita', 0.0)
            
            proj_skus_anterior = [m.sku for m in mappings_anterior]
            projetos_anterior = _wq_dim_projetos_by_codigos(db, proj_skus_anterior)
            
            cap_anterior = get_meta_orcada_projetos(db, projetos_anterior)
            meta_anterior = cap_anterior
            ticket_anterior = round(receita_anterior / vendas_anterior, 2) if vendas_anterior > 0 else 0.0
            
            variacao_vendas = ((current_sales - vendas_anterior) / vendas_anterior * 100) if vendas_anterior > 0 else None
            
            comparacao_anual = {
                "ano_atual": ano,
                "ano_anterior": ano_anterior,
                "atual": {
                    "vendas": current_sales,
                    "receita": round(current_receita, 2),
                    "meta": sales_goal,
                    "ticket_medio": round(avg_ticket, 2),
                    "ocupacao_pct": round(current_sales / sales_goal * 100, 1) if sales_goal > 0 else 0
                },
                "anterior": {
                    "vendas": vendas_anterior,
                    "receita": round(receita_anterior, 2),
                    "meta": meta_anterior,
                    "ticket_medio": round(ticket_anterior, 2),
                    "ocupacao_pct": round(vendas_anterior / meta_anterior * 100, 1) if meta_anterior > 0 else 0
                },
                "variacao": {
                    "vendas_pct": round(variacao_vendas, 1) if variacao_vendas is not None else None,
                    "receita_pct": round(((current_receita - receita_anterior) / receita_anterior * 100), 1) if receita_anterior > 0 else None
                }
            }
        
        all_grupo_mappings_for_anos = _wq_sku_mappings_by_grupo(db, grupo_nome, list(range(2018, ano + 2)))
        if all_grupo_mappings_for_anos:
            anos_set = sorted(set(m.ano for m in all_grupo_mappings_for_anos if m.ano), reverse=True)
            anos_disponiveis = [(a,) for a in anos_set]
        else:
            anos_disponiveis = db.query(SkuMapping.ano).filter(
                SkuMapping.evento_grupo == grupo_nome,
                SkuMapping.ativo == True
            ).distinct().order_by(SkuMapping.ano.desc()).all()
        
        _today_now = today_brazil()
        _event_is_past = bool(projeto_data_evento and projeto_data_evento < _today_now)
        from app.core.cache import get_last_full_refresh as _get_last_full_refresh
        _last_full_ts = _get_last_full_refresh()
        _last_full_str = (
            datetime.fromtimestamp(_last_full_ts, tz=ZoneInfo('America/Sao_Paulo')).isoformat()
            if _last_full_ts else None
        )
        _grupo_faixas_preco_site = _get_faixas_preco_site_for_projeto_ids(db, [p.id for p in projetos])

        grp_cenarios_ciclismo = None
        if projeto_modalidade and projeto_modalidade.lower() == 'ciclismo':
            grp_cad = _wq_cadastro_by_projeto_id(db, rep_projeto.id) if rep_projeto else None
            if grp_cad:
                grp_cenarios_ciclismo = {
                    "participacao": {
                        "orcado_pago": int(grp_cad.ciclismo_participacao_pago or 0),
                        "tkt_medio_orcado": 0,
                    },
                    "sem_bike": {
                        "orcado_pago": int(grp_cad.ciclismo_sem_bike_pago or 0),
                        "tkt_medio_orcado": float(grp_cad.ciclismo_sem_bike_tkt_medio or 0),
                    },
                    "com_bike": {
                        "orcado_pago": int(grp_cad.ciclismo_com_bike_pago or 0),
                        "tkt_medio_orcado": float(grp_cad.ciclismo_com_bike_tkt_medio or 0),
                    },
                }
                from app.models.kit_config import KitConfig as _KC
                from app.models.dimensoes import SkuMapping as _SM
                _grp_ext_ids = []
                for _gp in projetos:
                    _gp_sku = normalize_sku(str(_gp.codigo)) if _gp.codigo else None
                    if _gp_sku:
                        _gp_sm = db.query(_SM).filter(
                            func.upper(_SM.sku) == _gp_sku,
                            _SM.ativo == True,
                        ).all()
                        _grp_ext_ids.extend([str(sm_r.id_externo) for sm_r in _gp_sm if sm_r.id_externo])
                if _grp_ext_ids:
                    _grp_kits = db.query(_KC).filter(
                        _KC.id_evento.in_(_grp_ext_ids),
                        _KC.cenario_ciclismo.isnot(None),
                    ).all()
                else:
                    _grp_kits = []
                _grp_bundle_ids = {k.bundle_entity_id: k.cenario_ciclismo for k in _grp_kits}
                _grp_cenario_costs: dict = {}
                for _gk in _grp_kits:
                    _gcn = _gk.cenario_ciclismo
                    if _gcn and _gk.custo_kit is not None:
                        _grp_cenario_costs.setdefault(_gcn, []).append(float(_gk.custo_kit))
                for _gcn_key in grp_cenarios_ciclismo:
                    cost_vals = _grp_cenario_costs.get(_gcn_key, [])
                    grp_cenarios_ciclismo[_gcn_key]["custo_kit"] = round(sum(cost_vals) / len(cost_vals), 2) if cost_vals else 0
                if _grp_bundle_ids:
                    _grp_cic_populated = _populate_cenarios_from_bundles(
                        db, _grp_bundle_ids, grp_cenarios_ciclismo,
                        _grupo_incluir_cortesias,
                    )
                for _gcn in grp_cenarios_ciclismo:
                    _gcd = grp_cenarios_ciclismo[_gcn]
                    rv = _gcd.get("real_vendas", 0)
                    rr = _gcd.get("real_receita", 0)
                    _gcd.setdefault("real_vendas", 0)
                    _gcd.setdefault("real_receita", 0)
                    _gcd["real_tkt_medio"] = round(rr / rv, 2) if rv > 0 else 0
                    _gck_cost = _gcd.get("custo_kit", 0)
                    _gcd["margem_orcada"] = round((_gcd["tkt_medio_orcado"] - _gck_cost) * _gcd["orcado_pago"], 2) if _gcd["orcado_pago"] > 0 else 0
                    _gcd["margem_realizada"] = round(rr - (_gck_cost * rv), 2) if rv > 0 else 0

        grouped_result = {
            "status": "success",
            "evento": evento,
            "dailySales": daily_sales,
            # commercialActions intentionally excluded from cache — always fetched fresh per request
            "projetos_vinculados": [{"id": p.id, "nome": p.evento, "sku": p.codigo} for p in projetos],
            "comparacao_anual": comparacao_anual,
            "anos_disponiveis": [a[0] for a in anos_disponiveis],
            "faixas_preco_site": _grupo_faixas_preco_site,
            "cenarios_ciclismo": grp_cenarios_ciclismo,
            "ultima_atualizacao": datetime.now(ZoneInfo('America/Sao_Paulo')).isoformat(),
            "ultima_atualizacao_completa": _last_full_str,
            "avisos": get_isc_warnings(),
            "_cache_version": _DETAIL_CACHE_VERSION
        }
        if _event_is_past:
            grouped_result["__is_completed"] = True
            event_detail_cache.set_permanent(detail_cache_key, grouped_result)
            logger.info(f"Event '{grupo_nome}' ({projeto_data_evento}) cached permanently (completed event)")
        else:
            event_detail_cache.set(detail_cache_key, grouped_result)
        # Persiste em PostgreSQL para sobreviver a restarts e cache invalidations
        try:
            from ...services.event_detail_snapshot_service import save_persisted_detail as _spd
            _spd(db, evento_id, ano, grouped_result, data_evento=projeto_data_evento, is_completed=_event_is_past)
        except Exception as _spd_e:
            logger.warning(f"[Persist] save grouped '{evento_id}/{ano}' falhou: {_spd_e}")
        # Signal any waiting threads that computation is done
        with _event_computing_lock:
            _done_evt = _event_computing_events.pop(detail_cache_key, None)
        if _done_evt is not None:
            _done_evt.set()
        response_result = {k: v for k, v in grouped_result.items() if k != "__is_completed"}
        response_result["commercialActions"] = _fetch_commercial_actions_from_db(db, [p.id for p in projetos])
        return response_result
    
    projeto = _wq_dim_projeto_by_id(db, int(evento_id))
    
    if not projeto:
        raise HTTPException(status_code=404, detail="Evento não encontrado")
    
    projeto_codigo = str(projeto.codigo) if projeto.codigo else None
    sku = projeto_codigo
    projeto_data_evento = projeto.data_evento
    
    if ano is None:
        ano = projeto_data_evento.year if projeto_data_evento else datetime.now().year
    
    detail_standalone_cad = _wq_cadastro_by_projeto_id(db, projeto.id)
    dias_enc = get_dias_encerramento(db, projeto_id=projeto.id, cadastro=detail_standalone_cad)
    d_minus_inscricoes = calculate_d_minus(projeto_data_evento, reference_year=ano, dias_encerramento=dias_enc) if projeto_data_evento else 0
    d_minus = calculate_d_minus(projeto_data_evento, reference_year=ano, dias_encerramento=0) if projeto_data_evento else 0
    is_active = d_minus_inscricoes > 0 if ano == datetime.now().year else True
    standalone_detail_regime = get_data_regime(projeto_data_evento, dias_enc) if projeto_data_evento else "live"
    
    standalone_cache_key = f"{ano}_{evento_id}_detail"
    if not force_refresh:
        cached_standalone, is_stale = event_detail_cache.get_or_revalidate(standalone_cache_key, refresh_fn=None)
        if cached_standalone is not None:
            # Validate that cached data has a non-empty event date.
            _cached_evt_sa = cached_standalone.get("evento", {})
            _cached_date_sa = (
                _cached_evt_sa.get("date", "") if isinstance(_cached_evt_sa, dict)
                else getattr(_cached_evt_sa, "date", "")
            )
            # SWR trigger: recompute when _computed_at_date is missing or cache version is outdated.
            # Freshness is also owned by event_detail_cache.invalidate() (called after sync) + SmartCache TTL.
            _sa_cached_version = cached_standalone.get("_cache_version")
            _sa_needs_recompute = not _cached_date_sa or _sa_cached_version != _DETAIL_CACHE_VERSION
            if _sa_needs_recompute:
                if standalone_cache_key not in _swr_recompute_in_progress:
                    sa_reason = "empty date" if not _cached_date_sa else f"version mismatch ({_sa_cached_version} != {_DETAIL_CACHE_VERSION})"
                    logger.info(f"[Cache] standalone event_detail '{standalone_cache_key}' {sa_reason} — serving stale + triggering background recompute")
                    _swr_recompute_in_progress.add(standalone_cache_key)
                    import threading as _threading
                    _threading.Thread(target=_swr_detail_refresh, args=(standalone_cache_key,), daemon=True).start()
                else:
                    logger.info(f"[Cache] standalone event_detail '{standalone_cache_key}' SWR already in progress — skipping duplicate thread")
                is_stale = True
            if response is not None:
                response.headers["X-Data-Stale"] = "true" if is_stale else "false"
            result_sa = {k: v for k, v in cached_standalone.items() if k != "__is_completed"}
            if _sa_needs_recompute:
                result_sa["ultima_atualizacao"] = "2000-01-01T00:00:00-03:00"
            return result_sa
    
    standalone_evento_grupo = None
    if sku:
        standalone_mappings = _wq_sku_mappings_by_sku(db, sku)
        for sm in standalone_mappings:
            if sm.evento_grupo and sm.evento_grupo.strip():
                standalone_evento_grupo = sm.evento_grupo
                break

    if standalone_detail_regime == "consolidated":
        snap_key = standalone_evento_grupo or normalize_sku(sku or "")
        snap = _get_snapshot_metrics_for_grupo(db, snap_key) if snap_key else None
        if snap is not None:
            current_sales = snap['qtd_site']
            current_receita = snap['receita_liquida_site']
        else:
            isc_data_sa = fetch_isc_pricing_data(db=db)
            sales_info = isc_data_sa.get(normalize_sku(sku), {}) if sku else {}
            current_sales = sales_info.get('qtd_site', 0)
            current_receita = sales_info.get('receita_liquida_site', 0.0)
    else:
        isc_data_sa = fetch_isc_pricing_data(db=db)
        sales_info = isc_data_sa.get(normalize_sku(sku), {}) if sku else {}
        current_sales = sales_info.get('qtd_site', 0)
        current_receita = sales_info.get('receita_liquida_site', 0.0)
    
    sales_goal = get_meta_from_cadastro(detail_standalone_cad) if detail_standalone_cad else get_meta_orcada(db, projeto.id)
    avg_ticket = round(current_receita / current_sales, 2) if current_sales > 0 else 0.0
    detail_standalone_bt = round(float(detail_standalone_cad.atletas_site_tkt_medio), 2) if detail_standalone_cad and detail_standalone_cad.atletas_site_tkt_medio and detail_standalone_cad.atletas_site_pago and detail_standalone_cad.atletas_site_pago > 0 else 0.0

    data_fim_inscricoes_standalone = projeto_data_evento - timedelta(days=dias_enc) if projeto_data_evento else None

    if force_refresh and standalone_evento_grupo and ano == datetime.now().year and standalone_detail_regime != "consolidated":
        _should_rebuild_standalone = True
        try:
            from ...models.vendas_snapshot import VendasDiariaSnapshot as _VDS
            _last_updated_s = db.query(func.max(_VDS.updated_at)).filter(
                _VDS.evento_grupo == standalone_evento_grupo
            ).scalar()
            if _last_updated_s and (datetime.now() - _last_updated_s).total_seconds() < 600:
                _should_rebuild_standalone = False
                logger.info(f"Snapshot cooldown standalone: '{standalone_evento_grupo}' atualizado há {(datetime.now() - _last_updated_s).total_seconds():.0f}s, pulando rebuild")
        except Exception:
            pass
        if _should_rebuild_standalone:
            try:
                from ...services.snapshot_service import consolidar_vendas_grupo
                consolidar_vendas_grupo(db, standalone_evento_grupo, ano)
                logger.info(f"Snapshot reconstruído (force_refresh standalone) para '{standalone_evento_grupo}' ano={ano}")
            except Exception as _e:
                logger.warning(f"Falha ao reconstruir snapshot standalone para '{standalone_evento_grupo}': {_e}")
    elif standalone_detail_regime == "consolidated":
        logger.info(f"[Hybrid] Standalone evento {evento_id} é consolidated — pulando rebuild de snapshot")

    daily_sales_list = fetch_real_daily_sales_for_projetos(db, [projeto], sales_goal=sales_goal, ano=ano, evento_grupo=standalone_evento_grupo, data_evento=data_fim_inscricoes_standalone, data_evento_real=projeto_data_evento)
    daily_sales_dict = {date.fromisoformat(d['date']): d['sales'] for d in daily_sales_list}
    
    standalone_detail_hist = None
    standalone_detail_curva_info = {"tipo_curva": "linear", "fonte_curva": None, "ano_referencia": None}
    if standalone_evento_grupo:
        try:
            _sa_estado = str(projeto.estado) if projeto and projeto.estado else None
            standalone_detail_hist, standalone_detail_curva_info = _resolve_hist_pattern(db, standalone_evento_grupo, ano, estado=_sa_estado)
        except Exception:
            pass
    
    isc_components = calculate_isc_components(current_sales, sales_goal, d_minus_inscricoes,
                                               daily_sales_dict=daily_sales_dict,
                                               hist_pattern=standalone_detail_hist,
                                               registration_close_date=data_fim_inscricoes_standalone,
                                               curva_info=standalone_detail_curva_info)
    isc = calculate_isc(isc_components, isc_cfg["ia730Weight"], isc_cfg["curvaDWeight"], isc_cfg["rolling14dWeight"])
    isc_status = get_isc_status(isc, isc_cfg["greenThreshold"], isc_cfg["yellowThreshold"])
    suggested_action = get_suggested_action(isc, d_minus_inscricoes, isc_cfg["greenThreshold"], isc_cfg["yellowThreshold"], isc_cfg["promotionDeadline"])
    
    projeto_modalidade = str(projeto.modalidade) if projeto.modalidade else None
    projeto_cidade = str(projeto.cidade) if projeto.cidade else None
    projeto_estado = str(projeto.estado) if projeto.estado else None
    projeto_nome = str(projeto.evento) if projeto.evento else "Evento sem nome"
    projeto_limite = sales_goal
    
    detail_sa_kit_cost = get_kit_basico_cost(db, projeto.id)
    detail_sa_margin = _calc_margin_fields(detail_standalone_bt, detail_sa_kit_cost, sales_goal,
                                            avg_ticket, current_sales, current_receita)
    
    sa_ticket_atual_map = _get_ticket_atual_map(db)
    sa_detail_ticket_atual = _get_ticket_atual_for_event(sa_ticket_atual_map, projeto.id)
    sa_detail_ticket_kit_nome = _get_ticket_atual_kit_nome_for_event(sa_ticket_atual_map, projeto.id)
    
    _sa_incluir_cortesias = bool(getattr(projeto, 'incluir_cortesias', False))
    _sa_margem_avisos: list = []
    sa_margem_por_kit = get_margem_por_kit(
        db,
        [projeto.id],
        ano=ano,
        card_total_qty=current_sales,
        card_total_receita=current_receita,
        card_kit_cost_avg=detail_sa_kit_cost,
        avisos_out=_sa_margem_avisos,
        force_refresh=force_refresh,
        incluir_cortesias=_sa_incluir_cortesias,
    )
    # Align currentSales with the kit table total (same logic as consolidated group branch).
    _sa_kit_rows_aligned = [r for r in (sa_margem_por_kit or []) if r.get('tipoKit') != 'CONSOLIDADO']
    _sa_kit_total_qty_aligned = sum(int(r.get('qtd', 0) or 0) for r in _sa_kit_rows_aligned)
    if _sa_kit_total_qty_aligned > 0 and _sa_kit_total_qty_aligned != current_sales:
        logger.info(
            f"[Detalhe SA] Alinhando currentSales '{projeto_nome}': {current_sales} → {_sa_kit_total_qty_aligned} "
            f"(diff={current_sales - _sa_kit_total_qty_aligned})"
        )
        current_sales = _sa_kit_total_qty_aligned
        avg_ticket = round(current_receita / current_sales, 2) if current_sales > 0 else avg_ticket
        detail_sa_margin = _calc_margin_fields(detail_standalone_bt, detail_sa_kit_cost, sales_goal,
                                               avg_ticket, current_sales, current_receita)

    sa_detalhe_vendas = []
    sa_kit_query_failed = False
    if standalone_detail_regime == "consolidated":
        sa_detalhe_ativo = []
    else:
        sa_detalhe_ativo = get_detalhe_vendas_ativo(db, [projeto.id], ano=ano)
    
    evento = MarketingEvent(
        id=str(projeto.id),
        name=projeto_nome,
        date=projeto_data_evento.isoformat() if projeto_data_evento else "",
        location=projeto_cidade or projeto_estado or "Não definido",
        category=projeto_modalidade or "Corrida",
        totalCapacity=projeto_limite,
        currentSales=current_sales,
        salesGoal=sales_goal,
        averageTicket=round(avg_ticket, 2),
        budgetTicket=detail_standalone_bt,
        dMinus=d_minus,
        dMinusInscricoes=d_minus_inscricoes,
        isc=isc,
        iscComponents=isc_components,
        iscStatus=isc_status,
        suggestedAction=suggested_action,
        isActive=is_active,
        sku=sku,
        ticketAtual=sa_detail_ticket_atual,
        ticketKitNome=sa_detail_ticket_kit_nome,
        margemPorKit=sa_margem_por_kit if sa_margem_por_kit else None,
        margemAvisos=_sa_margem_avisos if _sa_margem_avisos else None,
        consistencyWarning=None,  # aligned above; retained field for API compatibility
        kitQueryFailed=sa_kit_query_failed,
        detalheVendasPorKit=sa_detalhe_vendas if sa_detalhe_vendas else None,
        detalheVendasAtivoKit=sa_detalhe_ativo if sa_detalhe_ativo else None,
        dataRegime=standalone_detail_regime,
        incluirCortesias=_sa_incluir_cortesias,
        **detail_sa_margin
    )
    
    daily_sales = daily_sales_list
    
    from ...models.dimensoes import AcaoComercial
    acoes = db.query(AcaoComercial).filter(
        AcaoComercial.projeto_id == int(evento_id)
    ).order_by(AcaoComercial.data_acao.desc()).all()
    
    commercial_actions = []
    for a in acoes:
        tipo_map = {
            'AUMENTO_PRECO': 'price_increase',
            'REDUCAO_PRECO': 'price_decrease',
            'PROMOCAO': 'promotion',
            'CAMPANHA': 'campaign',
            'COMUNICACAO': 'communication'
        }
        
        impacto = calculate_action_impact(db, a)
        impacto_percentual = impacto.get("impacto_percentual")
        vendas_antes = impacto.get("vendas_antes")
        vendas_depois = impacto.get("vendas_depois")
        
        if impacto_percentual is not None:
            if impacto_percentual > 0:
                impact_str = f"+{impacto_percentual}%"
            else:
                impact_str = f"{impacto_percentual}%"
        else:
            impact_str = None
        
        commercial_actions.append({
            "id": str(a.id),
            "type": tipo_map.get(a.tipo, 'communication'),
            "description": a.descricao,
            "date": a.data_acao.isoformat() if a.data_acao else None,
            "impact": impact_str,
            "vendas_antes": vendas_antes,
            "vendas_depois": vendas_depois,
            "impacto_percentual": impacto_percentual,
            "status_impacto": impacto.get("status", "calculado") if impacto_percentual is not None else "aguardando_dados",
            "ponto_corte": a.ponto_corte,
            "estagio": a.estagio,
            "snapshot_isc": float(a.snapshot_isc) if a.snapshot_isc is not None else None,
            "snapshot_isc_state": a.snapshot_isc_state,
            "snapshot_d_minus": a.snapshot_d_minus,
            "snapshot_ia730": float(a.snapshot_ia730) if a.snapshot_ia730 is not None else None,
            "snapshot_rolling14d": float(a.snapshot_rolling14d) if a.snapshot_rolling14d is not None else None,
            "snapshot_curva_percent": float(a.snapshot_curva_percent) if a.snapshot_curva_percent is not None else None,
            "snapshot_vendas_acumuladas": a.snapshot_vendas_acumuladas,
            "snapshot_playbook_letter": a.snapshot_playbook_letter,
        })
    
    _sa_faixas_preco_site = _get_faixas_preco_site_for_projeto_ids(db, [projeto.id])

    cenarios_ciclismo = None
    if projeto_modalidade and projeto_modalidade.lower() == 'ciclismo' and detail_standalone_cad:
        cenarios_ciclismo = {
            "participacao": {
                "orcado_pago": int(detail_standalone_cad.ciclismo_participacao_pago or 0),
                "tkt_medio_orcado": 0,
            },
            "sem_bike": {
                "orcado_pago": int(detail_standalone_cad.ciclismo_sem_bike_pago or 0),
                "tkt_medio_orcado": float(detail_standalone_cad.ciclismo_sem_bike_tkt_medio or 0),
            },
            "com_bike": {
                "orcado_pago": int(detail_standalone_cad.ciclismo_com_bike_pago or 0),
                "tkt_medio_orcado": float(detail_standalone_cad.ciclismo_com_bike_tkt_medio or 0),
            },
        }
        from app.models.kit_config import KitConfig as _KC
        from app.models.dimensoes import SkuMapping as _SM
        _proj_sku = normalize_sku(str(projeto.codigo)) if projeto.codigo else None
        _cic_ext_ids = []
        if _proj_sku:
            _cic_sm = db.query(_SM).filter(
                func.upper(_SM.sku) == _proj_sku,
                _SM.ativo == True,
            ).all()
            _cic_ext_ids = [str(sm_r.id_externo) for sm_r in _cic_sm if sm_r.id_externo]
        if _cic_ext_ids:
            _cic_kits = db.query(_KC).filter(
                _KC.id_evento.in_(_cic_ext_ids),
                _KC.cenario_ciclismo.isnot(None),
            ).all()
        else:
            _cic_kits = []
        _cic_bundle_to_kit = {k.bundle_entity_id: k for k in _cic_kits}
        _cic_bundle_ids = {k.bundle_entity_id: k.cenario_ciclismo for k in _cic_kits}
        _cic_cenario_costs: dict = {}
        for _ck in _cic_kits:
            _cn_val = _ck.cenario_ciclismo
            if _cn_val and _ck.custo_kit is not None:
                _cic_cenario_costs.setdefault(_cn_val, []).append(float(_ck.custo_kit))
        for _cn_key in cenarios_ciclismo:
            cost_vals = _cic_cenario_costs.get(_cn_key, [])
            cenarios_ciclismo[_cn_key]["custo_kit"] = round(sum(cost_vals) / len(cost_vals), 2) if cost_vals else 0
        if _cic_bundle_ids:
            _sa_cic_populated = _populate_cenarios_from_bundles(
                db, _cic_bundle_ids, cenarios_ciclismo,
                _sa_incluir_cortesias,
            )
        for _cn in cenarios_ciclismo:
            _cd = cenarios_ciclismo[_cn]
            rv = _cd.get("real_vendas", 0)
            rr = _cd.get("real_receita", 0)
            _cd.setdefault("real_vendas", 0)
            _cd.setdefault("real_receita", 0)
            _cd["real_tkt_medio"] = round(rr / rv, 2) if rv > 0 else 0
            _ck_cost = _cd.get("custo_kit", 0)
            _cd["margem_orcada"] = round((_cd["tkt_medio_orcado"] - _ck_cost) * _cd["orcado_pago"], 2) if _cd["orcado_pago"] > 0 else 0
            _cd["margem_realizada"] = round(rr - (_ck_cost * rv), 2) if rv > 0 else 0

    standalone_result = {
        "status": "success",
        "evento": evento,
        "dailySales": daily_sales,
        "faixas_preco_site": _sa_faixas_preco_site,
        "cenarios_ciclismo": cenarios_ciclismo,
        "ultima_atualizacao": datetime.now(ZoneInfo('America/Sao_Paulo')).isoformat(),
        "avisos": get_isc_warnings(),
        "_cache_version": _DETAIL_CACHE_VERSION
    }
    _sa_today = today_brazil()
    _sa_event_is_past = bool(projeto_data_evento and projeto_data_evento < _sa_today)
    if _sa_event_is_past:
        standalone_result["__is_completed"] = True
        event_detail_cache.set_permanent(standalone_cache_key, standalone_result)
        logger.info(f"Standalone event {evento_id} ({projeto_data_evento}) cached permanently (completed event)")
    else:
        event_detail_cache.set(standalone_cache_key, standalone_result)
    # Persiste em PostgreSQL para sobreviver a restarts e cache invalidations
    try:
        from ...services.event_detail_snapshot_service import save_persisted_detail as _spd_sa
        _spd_sa(db, evento_id, ano, standalone_result, data_evento=projeto_data_evento, is_completed=_sa_event_is_past)
    except Exception as _spd_sa_e:
        logger.warning(f"[Persist] save standalone '{evento_id}/{ano}' falhou: {_spd_sa_e}")
    sa_result = {k: v for k, v in standalone_result.items() if k != "__is_completed"}
    sa_result["commercialActions"] = _fetch_commercial_actions_from_db(db, [int(evento_id)])
    return sa_result


@router.post("/eventos/{evento_id}/atualizar-hoje")
def atualizar_vendas_hoje(
    evento_id: str,
    ano: Optional[int] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    """
    Atualização leve: busca apenas as vendas de HOJE (data atual) do Ativo e Magento
    para este evento, atualiza o snapshot e recalcula médias móveis.
    Não toca no ISC global nem em dados históricos.
    """
    from ...models.vendas_snapshot import VendasDiariaSnapshot as _VDS
    from sqlalchemy import func as _sa_func

    if ano is None:
        ano = today_brazil().year

    hoje = today_brazil()
    is_grouped = evento_id.startswith("grp_")

    # --- Collect IDs ---
    if is_grouped:
        grupo_nome = evento_id.replace("grp_", "")
        mappings = db.query(SkuMapping).filter(
            SkuMapping.evento_grupo == grupo_nome,
            SkuMapping.ano == ano,
            SkuMapping.ativo == True
        ).all()
    else:
        try:
            proj_id = int(evento_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="ID de evento inválido")
        projeto = db.query(DimProjeto).filter(DimProjeto.id == proj_id).first()
        if not projeto:
            raise HTTPException(status_code=404, detail="Evento não encontrado")
        grupo_nome = None
        _sku_raw = str(projeto.codigo) if projeto.codigo else None
        _sku_norm = normalize_sku(_sku_raw) if _sku_raw else None
        for _sku_q in filter(None, [_sku_raw, _sku_norm]):
            mappings = db.query(SkuMapping).filter(
                SkuMapping.sku == _sku_q,
                SkuMapping.ano == ano,
                SkuMapping.ativo == True
            ).all()
            if not mappings:
                mappings = db.query(SkuMapping).filter(
                    SkuMapping.sku == _sku_q,
                    SkuMapping.ativo == True
                ).order_by(SkuMapping.ano.desc()).all()
            if mappings:
                break

    if not mappings:
        raise HTTPException(status_code=404, detail="Nenhum SKU mapeado para este evento")

    ativo_ids = list(set(str(m.id_externo) for m in mappings if m.fonte == 'ATIVO' and m.id_externo))
    magento_ids = list(set(str(m.id_externo) for m in mappings if m.fonte == 'MAGENTO' and m.id_externo))

    if not grupo_nome and mappings:
        grupo_nome = next((m.evento_grupo for m in mappings if m.evento_grupo), None)

    if not grupo_nome:
        raise HTTPException(
            status_code=422,
            detail="Este evento não possui grupo mapeado. A atualização de hoje requer um grupo para persistir o snapshot."
        )

    # --- Fetch today's data from both sources (fast — date-filtered queries) ---
    hoje_ativo = 0
    hoje_magento = 0
    hoje_receita = 0.0

    if ativo_ids:
        try:
            ativo_today = _fetch_today_sales_ativo_grouped(ativo_ids)
            for _entry in ativo_today.values():
                hoje_ativo += _entry["qtd"]
                hoje_receita += _entry["receita"]
        except Exception as _e:
            logger.warning(f"atualizar-hoje: erro Ativo para {evento_id}: {_e}")

    if magento_ids:
        try:
            magento_today = _fetch_today_sales_magento_grouped(magento_ids)
            for _entry in magento_today.values():
                hoje_magento += _entry["qtd"]
                hoje_receita += _entry["receita"]
        except Exception as _e:
            logger.warning(f"atualizar-hoje: erro Magento para {evento_id}: {_e}")

    hoje_total = hoje_ativo + hoje_magento

    # --- Update snapshot for today ---
    _HOJE_FONTE = 'CONSOLIDADO'
    if grupo_nome:
        try:
            existing = db.query(_VDS).filter(
                _VDS.evento_grupo == grupo_nome,
                _VDS.fonte == _HOJE_FONTE,
                _VDS.data_venda == hoje,
            ).first()

            if existing:
                existing.quantidade = hoje_total
                existing.receita = hoje_receita
                existing.ano = ano
                existing.updated_at = datetime.now()
            else:
                new_row = _VDS(
                    evento_grupo=grupo_nome,
                    fonte=_HOJE_FONTE,
                    data_venda=hoje,
                    quantidade=hoje_total,
                    receita=hoje_receita,
                    ano=ano,
                    updated_at=datetime.now()
                )
                db.add(new_row)
            db.commit()
        except Exception as _e:
            logger.warning(f"atualizar-hoje: erro ao salvar snapshot para {grupo_nome}: {_e}")
            db.rollback()

    # --- Recalculate rolling averages from snapshot (no external DB) ---
    media_7d = 0.0
    media_14d = 0.0
    media_30d = 0.0
    total_acumulado = 0

    if grupo_nome:
        try:
            cutoff_30 = hoje - timedelta(days=30)
            snap_rows = db.query(_VDS).filter(
                _VDS.evento_grupo == grupo_nome,
                _VDS.data_venda >= cutoff_30,
                _VDS.data_venda <= hoje
            ).order_by(_VDS.data_venda).all()

            daily_map: dict = {}
            for r in snap_rows:
                daily_map[r.data_venda] = daily_map.get(r.data_venda, 0) + r.quantidade

            def _avg_last_n(n: int) -> float:
                cutoff = hoje - timedelta(days=n)
                total = sum(v for d, v in daily_map.items() if d >= cutoff and d <= hoje)
                return round(total / n, 2)

            media_7d = _avg_last_n(7)
            media_14d = _avg_last_n(14)
            media_30d = _avg_last_n(30)

            total_all = db.query(_sa_func.sum(_VDS.quantidade)).filter(
                _VDS.evento_grupo == grupo_nome,
            ).scalar() or 0
            total_acumulado = int(total_all)
        except Exception as _e:
            logger.warning(f"atualizar-hoje: erro ao recalcular médias para {grupo_nome}: {_e}")

    # Invalidate the eventos list cache so the main table shows fresh counts immediately,
    # and the ISC cache so projected totals reflect the new today-sync data.
    try:
        eventos_list_cache.invalidate()
        _smart_isc_cache.invalidate()
        logger.info(f"atualizar-hoje: eventos_list and ISC caches invalidated for {evento_id}")
    except Exception as _ci:
        logger.warning(f"atualizar-hoje: cache invalidation error: {_ci}")

    return {
        "status": "ok",
        "evento_id": evento_id,
        "data": hoje.isoformat(),
        "hoje_ativo": hoje_ativo,
        "hoje_magento": hoje_magento,
        "hoje_total": hoje_total,
        "media_7d": media_7d,
        "media_14d": media_14d,
        "media_30d": media_30d,
        "total_acumulado": total_acumulado,
        "ultima_atualizacao": datetime.now(ZoneInfo('America/Sao_Paulo')).isoformat()
    }


@router.post("/cache/refresh")
def refresh_cache(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    _smart_isc_cache.invalidate()
    event_detail_cache.invalidate()
    daily_sales_cache.invalidate()
    curva_cache.invalidate()
    medias_cache.invalidate()
    clear_warmup_daily_cache()
    clear_ticket_atual_cache()

    global _isc_cache, _isc_cache_timestamp, _sales_cache, _cache_timestamp
    _isc_cache = {}
    _isc_cache_timestamp = None
    _sales_cache = {}
    _cache_timestamp = None

    fetch_isc_pricing_data(db=db, force_refresh=True)

    cache_info = _smart_isc_cache.get_info(f"{datetime.now().year}_isc")

    return {
        "status": "success",
        "message": "Cache do ano atual atualizado com sucesso. Dados históricos preservados.",
        "cache_info": cache_info,
        "ultima_atualizacao": datetime.now(ZoneInfo('America/Sao_Paulo')).isoformat()
    }


@router.post("/cache/sync-hoje")
def sync_hoje_todos(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    """Sincroniza apenas os dados de HOJE do MySQL para o snapshot PostgreSQL de todos os
    eventos ativos, depois reconstrói o ISC cache. Muito mais rápido que o refresh completo."""
    from app.services.snapshot_service import sincronizar_hoje_batch

    try:
        synced = sincronizar_hoje_batch(db)
    except Exception as e:
        logger.error(f"sync-hoje: erro em sincronizar_hoje_batch: {e}")
        return {"status": "error", "message": str(e), "synced": 0}

    _smart_isc_cache.invalidate()
    eventos_list_cache.invalidate()

    try:
        fetch_isc_pricing_data(db=db, force_refresh=True)
    except Exception as e:
        logger.warning(f"sync-hoje: erro ao reconstruir ISC cache: {e}")

    return {
        "status": "ok",
        "synced": synced,
        "message": f"Dados de hoje sincronizados para {synced} grupos. Tabela principal atualizada.",
        "ultima_atualizacao": datetime.now(ZoneInfo('America/Sao_Paulo')).isoformat()
    }


@router.post("/cache/refresh-all")
def refresh_all_caches(
    current_user: Usuario = Depends(get_current_user)
):
    from app.core.cache import (
        is_full_refresh_in_progress,
        trigger_full_warmup_async,
        get_warmup_progress,
        is_full_refresh_pending,
    )

    # Sempre aceita o clique. Se já tem rodada em andamento, enfileira a próxima.
    result = trigger_full_warmup_async()
    now_iso = datetime.now(ZoneInfo('America/Sao_Paulo')).isoformat()
    progress = get_warmup_progress() if is_full_refresh_in_progress() else None

    if result == "queued":
        return {
            "status": "in_progress",
            "queued_next": True,
            "message": "Atualização em andamento — sua nova solicitação foi enfileirada e iniciará logo após.",
            "progress": progress,
            "ultima_atualizacao": now_iso,
        }
    if result == "started":
        return {
            "status": "started",
            "queued_next": is_full_refresh_pending(),
            "message": "Atualização completa iniciada em background.",
            "progress": progress,
            "ultima_atualizacao": now_iso,
        }
    return {
        "status": "error",
        "message": "Não foi possível iniciar a atualização (warmup não disponível).",
        "ultima_atualizacao": now_iso,
    }


@router.get("/debug/snapshot-grupo")
def debug_snapshot_grupo(
    grupo: str,
    ano: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """
    Diagnostic endpoint: returns a breakdown of vendas_diaria_snapshot rows
    for a specific grupo, grouped by calendar year and date range.
    Useful for identifying pre-sale orders or data contamination.
    """
    from app.models.vendas_snapshot import VendasDiariaSnapshot
    import datetime as _diag_dt

    _ano = ano or today_brazil().year

    rows = db.query(
        VendasDiariaSnapshot.data_venda,
        VendasDiariaSnapshot.quantidade,
        VendasDiariaSnapshot.receita,
        VendasDiariaSnapshot.ano,
        VendasDiariaSnapshot.fonte,
    ).filter(
        VendasDiariaSnapshot.evento_grupo == grupo,
    ).order_by(VendasDiariaSnapshot.data_venda).all()

    year_start      = _diag_dt.date(_ano, 1, 1)
    presale_start   = _diag_dt.date(_ano - 1, 9, 1)
    year_end        = _diag_dt.date(_ano + 1, 1, 1)

    in_year         = [r for r in rows if r.data_venda >= year_start and r.data_venda < year_end]
    presale         = [r for r in rows if r.data_venda >= presale_start and r.data_venda < year_start]
    before_presale  = [r for r in rows if r.data_venda < presale_start]
    after_year      = [r for r in rows if r.data_venda >= year_end]

    def _summarize(subset):
        return {
            "count_days": len(subset),
            "total_qtd": sum(r.quantidade or 0 for r in subset),
            "total_receita": round(sum(float(r.receita or 0) for r in subset), 2),
            "date_min": str(subset[0].data_venda) if subset else None,
            "date_max": str(subset[-1].data_venda) if subset else None,
            "rows": [{"data_venda": str(r.data_venda), "qtd": r.quantidade, "ano_col": r.ano, "fonte": r.fonte}
                     for r in subset],
        }

    isc_total = sum(r.quantidade or 0 for r in rows
                    if (r.ano == _ano) or (r.data_venda >= presale_start and r.data_venda < year_end))

    return {
        "grupo": grupo,
        "ano_consultado": _ano,
        "isc_total_atual": isc_total,
        "total_snapshot_sem_filtro": sum(r.quantidade or 0 for r in rows),
        "breakdown": {
            f"em_{_ano}": _summarize(in_year),
            f"pre_venda_{_ano - 1}_set_dez": _summarize(presale),
            f"antes_set_{_ano - 1}": _summarize(before_presale),
            f"depois_{_ano}": _summarize(after_year),
        },
        "by_ano_col": {
            str(yr): sum(r.quantidade or 0 for r in rows if r.ano == yr)
            for yr in sorted(set(r.ano for r in rows if r.ano is not None))
        },
    }


@router.get("/cache/status")
def get_cache_status(
    current_user: Usuario = Depends(get_current_user)
):
    import time as _cst_time
    from app.core.cache import get_last_full_refresh, get_last_sync_hoje, is_full_refresh_in_progress, get_warmup_progress, get_last_refresh_error, get_warmup_event_results, get_warmup_summary, get_gap_detection_result, get_known_tier1_ids

    current_year = datetime.now().year
    last_refresh = get_last_full_refresh()
    last_refresh_str = None
    if last_refresh:
        last_refresh_str = datetime.fromtimestamp(last_refresh, tz=ZoneInfo('America/Sao_Paulo')).isoformat()

    last_sync_hoje = get_last_sync_hoje()
    last_sync_hoje_str = None
    if last_sync_hoje:
        last_sync_hoje_str = datetime.fromtimestamp(last_sync_hoje, tz=ZoneInfo('America/Sao_Paulo')).isoformat()

    in_progress = is_full_refresh_in_progress()
    progress = get_warmup_progress() if in_progress else None
    last_error = get_last_refresh_error()
    warmup_summary = get_warmup_summary()
    warmup_results = get_warmup_event_results()
    gap_result = get_gap_detection_result()

    STALE_THRESHOLD = 25 * 3600
    now_ts = _cst_time.time()
    all_timestamps = event_detail_cache.get_all_timestamps()

    def _extract_event_id(cache_key: str) -> str:
        """Strip '{ano}_' prefix and '_detail' suffix from cache key to get event ID."""
        parts = cache_key.split("_", 1)
        raw = parts[1] if len(parts) == 2 else cache_key
        if raw.endswith("_detail"):
            raw = raw[:-7]
        return raw

    current_year_ages = {}
    for k, ts in all_timestamps.items():
        if not event_detail_cache._is_historical(k):
            current_year_ages[k] = now_ts - ts

    oldest_hours = round(max(current_year_ages.values()) / 3600, 1) if current_year_ages else None
    newest_hours = round(min(current_year_ages.values()) / 3600, 1) if current_year_ages else None
    stale_event_ids = [_extract_event_id(k) for k, age in current_year_ages.items() if age > STALE_THRESHOLD]

    known_tier1 = get_known_tier1_ids()
    missing_tier1 = []
    stale_tier1 = []
    for eid in known_tier1:
        key = f"{current_year}_{eid}_detail"
        ts = all_timestamps.get(key)
        if ts is None:
            missing_tier1.append(eid)
        elif (now_ts - ts) > STALE_THRESHOLD:
            stale_tier1.append(eid)

    return {
        "status": "success",
        "refresh_in_progress": in_progress,
        "progress": progress,
        "last_error": last_error,
        "ultima_atualizacao_completa": last_refresh_str,
        "last_sync_hoje": last_sync_hoje_str,
        "warmup_duration_seconds": warmup_summary.get("duration_seconds"),
        "warmup_completed_at": warmup_summary.get("completed_at"),
        "warmup_summary": warmup_summary,
        "warmup_results": warmup_results,
        "gap_detection": {
            **gap_result,
            "missing_tier1_events": missing_tier1,
            "stale_tier1_events": stale_tier1,
        },
        "missing_tier1_events": missing_tier1,
        "stale_tier1_events": stale_tier1,
        "oldest_event_detail_age_hours": oldest_hours,
        "newest_event_detail_age_hours": newest_hours,
        "stale_events": stale_event_ids,
        "caches": {
            "isc_pricing": _smart_isc_cache.get_info(f"{current_year}_isc"),
            "event_detail": {
                "entries": event_detail_cache.entry_count(),
                "historical": sum(1 for k in event_detail_cache.get_all_keys() if event_detail_cache._is_historical(k)),
                "current_year": sum(1 for k in event_detail_cache.get_all_keys() if not event_detail_cache._is_historical(k)),
                "oldest_event_detail_age_hours": oldest_hours,
                "newest_event_detail_age_hours": newest_hours,
                "stale_events": stale_event_ids,
            },
            "curva_comparativa": {
                "entries": curva_cache.entry_count(),
            },
            "medias_vendas": {
                "entries": medias_cache.entry_count(),
            }
        },
        "config": {
            "historical_ttl": "permanent",
            "current_year_ttl_seconds": CURRENT_YEAR_TTL,
            "auto_refresh_interval_seconds": 1800,
            "daily_refresh_time": "05:00 BRT"
        }
    }


class AcaoComercialCreate(BaseModel):
    projeto_id: int
    tipo: str
    descricao: str
    data_acao: date
    ponto_corte: Optional[str] = None
    estagio: Optional[str] = None
    snapshot_isc: Optional[float] = None
    snapshot_isc_state: Optional[str] = None
    snapshot_d_minus: Optional[int] = None
    snapshot_ia730: Optional[float] = None
    snapshot_rolling14d: Optional[float] = None
    snapshot_curva_percent: Optional[float] = None
    snapshot_vendas_acumuladas: Optional[int] = None
    snapshot_playbook_letter: Optional[str] = None

class AcaoComercialUpdate(BaseModel):
    tipo: Optional[str] = None
    descricao: Optional[str] = None
    data_acao: Optional[date] = None

class AcaoComercialResponse(BaseModel):
    id: int
    projeto_id: int
    tipo: str
    descricao: str
    data_acao: str
    impacto_percentual: Optional[float] = None
    vendas_antes: Optional[int] = None
    vendas_depois: Optional[int] = None
    ponto_corte: Optional[str] = None
    estagio: Optional[str] = None
    snapshot_isc: Optional[float] = None
    snapshot_isc_state: Optional[str] = None
    snapshot_d_minus: Optional[int] = None
    snapshot_ia730: Optional[float] = None
    snapshot_rolling14d: Optional[float] = None
    snapshot_curva_percent: Optional[float] = None
    snapshot_vendas_acumuladas: Optional[int] = None
    snapshot_playbook_letter: Optional[str] = None
    created_at: Optional[str] = None

    class Config:
        from_attributes = True


@router.get("/acoes-comerciais/{projeto_id}")
def get_acoes_comerciais(
    projeto_id: int,
    calcular_impacto: bool = Query(default=True, description="Calcular impacto em tempo real"),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    """Lista todas as ações comerciais de um projeto/evento com cálculo de impacto"""
    from ...models.dimensoes import AcaoComercial
    
    acoes = db.query(AcaoComercial).filter(
        AcaoComercial.projeto_id == projeto_id
    ).order_by(AcaoComercial.data_acao.desc()).all()
    
    acoes_list = []
    for a in acoes:
        acao_data = {
            "id": a.id,
            "projeto_id": a.projeto_id,
            "tipo": a.tipo,
            "descricao": a.descricao,
            "data_acao": a.data_acao.isoformat() if a.data_acao else None,
            "impacto_percentual": float(a.impacto_percentual) if a.impacto_percentual else None,
            "vendas_antes": a.vendas_antes,
            "vendas_depois": a.vendas_depois,
            "ponto_corte": a.ponto_corte,
            "estagio": a.estagio,
            "snapshot_isc": float(a.snapshot_isc) if a.snapshot_isc is not None else None,
            "snapshot_isc_state": a.snapshot_isc_state,
            "snapshot_d_minus": a.snapshot_d_minus,
            "snapshot_ia730": float(a.snapshot_ia730) if a.snapshot_ia730 is not None else None,
            "snapshot_rolling14d": float(a.snapshot_rolling14d) if a.snapshot_rolling14d is not None else None,
            "snapshot_curva_percent": float(a.snapshot_curva_percent) if a.snapshot_curva_percent is not None else None,
            "snapshot_vendas_acumuladas": a.snapshot_vendas_acumuladas,
            "snapshot_playbook_letter": a.snapshot_playbook_letter,
            "created_at": a.created_at.isoformat() if a.created_at else None
        }
        
        if calcular_impacto and a.data_acao:
            impacto = calculate_action_impact(db, a)
            acao_data["vendas_antes"] = impacto.get("vendas_antes")
            acao_data["vendas_depois"] = impacto.get("vendas_depois")
            acao_data["impacto_percentual"] = impacto.get("impacto_percentual")
            acao_data["status_impacto"] = impacto.get("status", "calculado")
        
        acoes_list.append(acao_data)
    
    return {
        "status": "success",
        "acoes": acoes_list
    }


@router.post("/acoes-comerciais")
def create_acao_comercial(
    acao: AcaoComercialCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    """Cria uma nova ação comercial vinculada ao ponto de corte e com snapshot dos dados ISC"""
    from ...models.dimensoes import AcaoComercial
    
    projeto = db.query(DimProjeto).filter(DimProjeto.id == acao.projeto_id).first()
    if not projeto:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")
    
    nova_acao = AcaoComercial(
        projeto_id=acao.projeto_id,
        tipo=acao.tipo,
        descricao=acao.descricao,
        data_acao=acao.data_acao,
        ponto_corte=acao.ponto_corte,
        estagio=acao.estagio,
        snapshot_isc=acao.snapshot_isc,
        snapshot_isc_state=acao.snapshot_isc_state,
        snapshot_d_minus=acao.snapshot_d_minus,
        snapshot_ia730=acao.snapshot_ia730,
        snapshot_rolling14d=acao.snapshot_rolling14d,
        snapshot_curva_percent=acao.snapshot_curva_percent,
        snapshot_vendas_acumuladas=acao.snapshot_vendas_acumuladas,
        snapshot_playbook_letter=acao.snapshot_playbook_letter,
    )
    
    db.add(nova_acao)
    db.commit()
    db.refresh(nova_acao)

    return {
        "status": "success",
        "message": "Ação comercial criada com sucesso",
        "acao": {
            "id": nova_acao.id,
            "projeto_id": nova_acao.projeto_id,
            "tipo": nova_acao.tipo,
            "descricao": nova_acao.descricao,
            "data_acao": nova_acao.data_acao.isoformat() if nova_acao.data_acao else None,
            "ponto_corte": nova_acao.ponto_corte,
            "estagio": nova_acao.estagio,
        }
    }


@router.put("/acoes-comerciais/{acao_id}")
def update_acao_comercial(
    acao_id: int,
    acao_update: AcaoComercialUpdate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    """Atualiza uma ação comercial existente"""
    from ...models.dimensoes import AcaoComercial
    
    acao = db.query(AcaoComercial).filter(AcaoComercial.id == acao_id).first()
    if not acao:
        raise HTTPException(status_code=404, detail="Ação comercial não encontrada")
    
    if acao_update.tipo is not None:
        acao.tipo = acao_update.tipo
    if acao_update.descricao is not None:
        acao.descricao = acao_update.descricao
    if acao_update.data_acao is not None:
        acao.data_acao = acao_update.data_acao
    
    db.commit()
    db.refresh(acao)
    
    return {
        "status": "success",
        "message": "Ação comercial atualizada com sucesso",
        "acao": {
            "id": acao.id,
            "projeto_id": acao.projeto_id,
            "tipo": acao.tipo,
            "descricao": acao.descricao,
            "data_acao": acao.data_acao.isoformat() if acao.data_acao else None
        }
    }


@router.delete("/acoes-comerciais/{acao_id}")
def delete_acao_comercial(
    acao_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    """Remove uma ação comercial"""
    from ...models.dimensoes import AcaoComercial
    
    acao = db.query(AcaoComercial).filter(AcaoComercial.id == acao_id).first()
    if not acao:
        raise HTTPException(status_code=404, detail="Ação comercial não encontrada")
    
    db.delete(acao)
    db.commit()

    return {
        "status": "success",
        "message": "Ação comercial removida com sucesso"
    }


class PricingMetrics(BaseModel):
    rollingIndex: float
    rollingAvg14d: float
    rollingAvg14dLastYear: float
    paceRequired: float
    ied: float
    projection: float
    paceSeguranca: float
    fem: float
    ia: float

class ElasticityScenario(BaseModel):
    priceIncrease: float
    newPrice: float
    newMargin: float
    acceptableVolumeDrop: float
    minPace: float

class PricingDecision(BaseModel):
    action: str
    reason: str
    confidence: str

class KitBreakdownItem(BaseModel):
    tipoKit: str
    custoKit: Optional[float] = None

class PricingEvent(BaseModel):
    id: str
    name: str
    date: str
    location: str
    category: str
    totalCapacity: int
    currentSales: int
    salesGoal: int
    averageTicket: float
    kitCost: float
    dMinus: int
    isActive: bool
    sku: Optional[str] = None
    pricingMetrics: PricingMetrics
    elasticityScenarios: List[ElasticityScenario]
    decision: PricingDecision
    iscStatus: str
    kitBreakdown: Optional[List[KitBreakdownItem]] = None

class PricingSummary(BaseModel):
    totalEvents: int
    eventsToIncrease: int
    eventsToMaintain: int
    eventsToDecrease: int

class PricingEventsResponse(BaseModel):
    status: str
    eventos: List[PricingEvent]
    resumo: PricingSummary
    categorias: List[str]
    ultima_atualizacao: str
    avisos: List[str] = []


def calculate_pricing_metrics(
    current_sales: int, 
    sales_goal: int, 
    d_minus: int, 
    average_ticket: float,
    kit_cost: float,
    total_capacity: int,
    rolling_avg_14d_real: Optional[float] = None,
    rolling_avg_14d_last_year: float = 0.0
) -> PricingMetrics:
    if d_minus <= 0:
        d_minus = 1
    
    total_days = 90
    elapsed_days = max(1, total_days - d_minus)
    inscricoes_restantes = max(1, sales_goal - current_sales)
    
    if rolling_avg_14d_real is not None:
        rolling_avg_14d = rolling_avg_14d_real
    else:
        if elapsed_days > 14:
            rolling_avg_14d = current_sales / elapsed_days
        else:
            rolling_avg_14d = current_sales / max(1, elapsed_days)
    
    pace_required = inscricoes_restantes / max(1, d_minus)
    
    if pace_required > 0:
        rolling_index = rolling_avg_14d / pace_required
    else:
        rolling_index = 2.0
    
    if rolling_avg_14d > 0 and sales_goal > 0:
        projection = current_sales + (rolling_avg_14d * d_minus)
    elif elapsed_days > 0 and sales_goal > 0:
        projection = (current_sales / elapsed_days) * total_days
    else:
        projection = current_sales
    
    expected_daily = sales_goal / max(1, total_days)
    if expected_daily > 0:
        ia = rolling_avg_14d / expected_daily
    else:
        ia = 1.0
    
    if sales_goal > 0:
        ied = projection / sales_goal
    else:
        ied = 1.0
    
    current_margin = average_ticket - kit_cost
    new_margin = (average_ticket * 1.10) - kit_cost
    
    if new_margin > 0:
        fem = current_margin / new_margin
    else:
        fem = 1.0
    
    pace_seguranca = rolling_avg_14d * fem
    
    return PricingMetrics(
        rollingIndex=round(rolling_index, 2),
        rollingAvg14d=round(rolling_avg_14d, 2),
        rollingAvg14dLastYear=round(rolling_avg_14d_last_year, 2),
        paceRequired=round(pace_required, 2),
        ied=round(ied, 2),
        projection=round(projection, 0),
        paceSeguranca=round(pace_seguranca, 2),
        fem=round(fem, 3),
        ia=round(ia, 2)
    )


def calculate_elasticity_scenarios(
    average_ticket: float,
    kit_cost: float,
    rolling_avg_14d: float
) -> List[ElasticityScenario]:
    """
    Calcula cenários de elasticidade para diferentes aumentos de preço.
    Mostra a queda de volume aceitável para cada cenário.
    """
    scenarios = []
    increases = [5, 10, 15, 20]
    
    current_margin = average_ticket - kit_cost
    
    for inc in increases:
        new_price = average_ticket * (1 + inc / 100)
        new_margin = new_price - kit_cost
        
        if current_margin > 0 and new_margin > 0:
            fem = current_margin / new_margin
            acceptable_drop = (1 - fem) * 100
            min_pace = rolling_avg_14d * fem
        else:
            acceptable_drop = 0
            min_pace = rolling_avg_14d
        
        scenarios.append(ElasticityScenario(
            priceIncrease=inc,
            newPrice=round(new_price, 2),
            newMargin=round(new_margin, 2),
            acceptableVolumeDrop=round(acceptable_drop, 1),
            minPace=round(min_pace, 2)
        ))
    
    return scenarios


def get_pricing_decision(
    metrics: PricingMetrics,
    d_minus: int
) -> PricingDecision:
    """
    Determina a decisão de pricing baseada na matriz do documento:
    
    | IA (Aceleração) | Projeção vs Meta | Ação Recomendada |
    |-----------------|------------------|------------------|
    | Alto (> 1.2)    | Projeção > Meta  | Subir Preço Agora |
    | Estável (1.0)   | Projeção > Meta  | Subir Gradual |
    | Caindo (< 0.9)  | Projeção > Meta  | Manter / Focar Volume |
    """
    ia = metrics.ia
    ied = metrics.ied
    rolling_index = metrics.rollingIndex
    
    if ia > 1.2 and ied > 1.0:
        return PricingDecision(
            action="increase_now",
            reason=f"IA alto ({ia:.2f}) e projeção acima da meta (IED {ied:.2f}). Demanda inelástica detectada.",
            confidence="high"
        )
    
    if ia >= 0.95 and ia <= 1.2 and ied > 1.0:
        return PricingDecision(
            action="increase_gradual",
            reason=f"IA estável ({ia:.2f}) com projeção acima da meta. Capture margem nos próximos lotes.",
            confidence="medium"
        )
    
    if ia < 0.9 and ied > 1.0:
        return PricingDecision(
            action="maintain",
            reason=f"IA em queda ({ia:.2f}), mas projeção ainda acima da meta. Priorize volume.",
            confidence="medium"
        )
    
    if rolling_index > 1.3 and ied > 1.1:
        return PricingDecision(
            action="increase_now",
            reason=f"Rolling Index muito alto ({rolling_index:.2f}). Ritmo excelente para sell-out.",
            confidence="high"
        )
    
    if ied < 0.9 or rolling_index < 0.8:
        if d_minus >= 40:
            return PricingDecision(
                action="decrease",
                reason=f"Vendas abaixo do esperado (IED {ied:.2f}). Janela aberta para promoção.",
                confidence="medium"
            )
        else:
            return PricingDecision(
                action="maintain",
                reason=f"Vendas fracas, mas fora da janela de promoção (D-{d_minus}).",
                confidence="low"
            )
    
    return PricingDecision(
        action="maintain",
        reason="Métricas dentro do esperado. Continue monitorando.",
        confidence="medium"
    )


@router.get("/pricing", response_model=PricingEventsResponse)
def get_pricing_analysis(
    ano: int = Query(default=None, description="Ano dos eventos"),
    status: Optional[str] = Query(None, description="Filtrar por status: active, closed, all"),
    categoria: Optional[str] = Query(None, description="Filtrar por categoria/modalidade"),
    busca: Optional[str] = Query(None, description="Buscar por nome do evento"),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    """
    Retorna análise de pricing avançada para eventos.
    Inclui Rolling Index, IED, Pace de Segurança e matriz de elasticidade.
    """
    if ano is None:
        ano = datetime.now().year
    
    isc_cfg = _get_isc_settings(db)
    
    cadastro_query = db.query(CadastroEvento)
    if categoria and categoria != 'all':
        cadastro_query = cadastro_query.filter(CadastroEvento.modalidade == categoria)
    if busca:
        cadastro_query = cadastro_query.filter(CadastroEvento.nome.ilike(f'%{busca}%'))
    cadastros = cadastro_query.all()
    
    cadastro_by_projeto_id = {}
    for cad in cadastros:
        if cad.projeto_id:
            cadastro_by_projeto_id[cad.projeto_id] = cad
    
    projeto_ids = [cad.projeto_id for cad in cadastros if cad.projeto_id]
    projetos = db.query(DimProjeto).filter(DimProjeto.id.in_(projeto_ids)).all() if projeto_ids else []
    
    isc_data = fetch_isc_pricing_data(db=db)
    
    kit_costs = get_kit_basico_costs_batch(db, projeto_ids)
    kit_breakdowns = get_kit_breakdown_for_projetos(db, projeto_ids, ano)

    sku_to_grupo = _build_sku_to_grupo_map(db, ano)
    
    grupo_names_set = set(sku_to_grupo.values())
    grupo_details = {}
    if grupo_names_set:
        grupo_list = db.query(EventoGrupoModel).filter(
            EventoGrupoModel.nome.in_(list(grupo_names_set)),
            EventoGrupoModel.ativo == True
        ).all()
        for g in grupo_list:
            grupo_details[g.nome] = g
    
    grupo_projetos = {}
    standalone_projetos = []
    
    for projeto in projetos:
        projeto_codigo = str(projeto.codigo) if projeto.codigo else None
        if not projeto_codigo:
            continue
        sku_norm = normalize_sku(projeto_codigo)
        grupo_nome = sku_to_grupo.get(sku_norm)
        if grupo_nome and grupo_nome in grupo_details:
            if grupo_nome not in grupo_projetos:
                grupo_projetos[grupo_nome] = []
            grupo_projetos[grupo_nome].append(projeto)
        else:
            standalone_projetos.append(projeto)
    
    eventos = []
    categorias_set: set[str] = set()
    events_increase = 0
    events_maintain = 0
    events_decrease = 0

    for grupo_nome, proj_list in grupo_projetos.items():
        grupo = grupo_details[grupo_nome]
        
        latest_date = None
        rep_projeto = proj_list[0]
        rep_cadastro = cadastro_by_projeto_id.get(rep_projeto.id)
        total_kit_cost = 0.0
        kit_count = 0
        
        for p in proj_list:
            if p.data_evento:
                if latest_date is None or p.data_evento > latest_date:
                    latest_date = p.data_evento
                    rep_projeto = p
                    rep_cadastro = cadastro_by_projeto_id.get(p.id)
            kc = kit_costs.get(p.id, 50.0)
            total_kit_cost += kc
            kit_count += 1
        
        total_capacity = 0
        for p in proj_list:
            cad = cadastro_by_projeto_id.get(p.id)
            if cad:
                total_capacity += get_meta_from_cadastro(cad)
            else:
                total_capacity += get_meta_orcada(db, p.id)
        
        projeto_data_evento = latest_date or rep_projeto.data_evento
        dias_enc = get_dias_encerramento(db, projeto_id=rep_projeto.id, cadastro=rep_cadastro) if rep_projeto else 2
        d_minus_inscricoes = calculate_d_minus(projeto_data_evento, dias_encerramento=dias_enc) if projeto_data_evento else 0
        d_minus = calculate_d_minus(projeto_data_evento, dias_encerramento=0) if projeto_data_evento else 0
        is_active = d_minus_inscricoes > 0
        
        if status == 'active' and not is_active:
            continue
        if status == 'closed' and is_active:
            continue
        
        grupo_modalidade = str(rep_cadastro.modalidade) if rep_cadastro and rep_cadastro.modalidade else (rep_projeto.modalidade or 'OUTROS')
        categorias_set.add(grupo_modalidade)
        
        current_sales = 0
        current_receita = 0.0
        combined_rolling_14d = 0.0
        combined_rolling_14d_ly = 0.0
        combined_m7d = 0.0
        combined_m30d = 0.0
        seen_pricing_norms = set()
        for p in proj_list:
            p_sku = normalize_sku(str(p.codigo)) if p.codigo else None
            if p_sku and p_sku not in seen_pricing_norms and p_sku in isc_data:
                seen_pricing_norms.add(p_sku)
                current_sales += isc_data[p_sku].get('qtd_site', 0)
                current_receita += isc_data[p_sku].get('receita_liquida_site', 0.0)
                combined_rolling_14d += isc_data[p_sku].get('media_14d', 0.0)
                combined_rolling_14d_ly += isc_data[p_sku].get('media_14d_ano_passado', 0.0)
                combined_m7d += isc_data[p_sku].get('media_7d', 0.0)
                combined_m30d += isc_data[p_sku].get('media_30d', 0.0)
        
        average_ticket = round(current_receita / current_sales, 2) if current_sales > 0 else 0.0
        sales_goal = total_capacity
        kit_cost = total_kit_cost / kit_count if kit_count > 0 else 50.0
        
        all_skus = [str(p.codigo) for p in proj_list if p.codigo]
        
        grupo_location = str(rep_cadastro.localizacao_evento) if rep_cadastro and rep_cadastro.localizacao_evento else (rep_projeto.cidade or "Local não definido")
        
        pricing_metrics = calculate_pricing_metrics(
            current_sales=current_sales,
            sales_goal=sales_goal,
            d_minus=d_minus,
            average_ticket=average_ticket,
            kit_cost=kit_cost,
            total_capacity=total_capacity if total_capacity > 0 else sales_goal if sales_goal > 0 else 10000,
            rolling_avg_14d_real=combined_rolling_14d,
            rolling_avg_14d_last_year=combined_rolling_14d_ly
        )
        
        elasticity_scenarios = calculate_elasticity_scenarios(
            average_ticket=average_ticket,
            kit_cost=kit_cost,
            rolling_avg_14d=pricing_metrics.rollingAvg14d
        )
        
        decision = get_pricing_decision(pricing_metrics, d_minus)
        
        if decision.action in ['increase_now', 'increase_gradual']:
            events_increase += 1
        elif decision.action == 'decrease':
            events_decrease += 1
        else:
            events_maintain += 1
        
        pricing_hist_pattern = None
        pricing_curva_info = {"tipo_curva": "linear", "fonte_curva": None, "ano_referencia": None}
        try:
            pricing_hist_pattern, pricing_curva_info = _resolve_hist_pattern(db, grupo_nome, ano)
        except Exception:
            pass

        pricing_grupo_reg_close = (projeto_data_evento - timedelta(days=dias_enc)) if projeto_data_evento else None
        isc_components = calculate_isc_components(
            current_sales, sales_goal, d_minus,
            media_7d=combined_m7d,
            media_14d=combined_rolling_14d,
            media_30d=combined_m30d,
            hist_pattern=pricing_hist_pattern,
            registration_close_date=pricing_grupo_reg_close,
            curva_info=pricing_curva_info
        )
        isc = calculate_isc(isc_components, isc_cfg["ia730Weight"], isc_cfg["curvaDWeight"], isc_cfg["rolling14dWeight"])
        isc_status = get_isc_status(isc, isc_cfg["greenThreshold"], isc_cfg["yellowThreshold"])
        
        # Merge kit breakdown from all projetos in the group (unique by tipoKit)
        grupo_breakdown_map: dict = {}
        for p in proj_list:
            for item in kit_breakdowns.get(p.id, []):
                if item["tipoKit"] not in grupo_breakdown_map:
                    grupo_breakdown_map[item["tipoKit"]] = item["custoKit"]
        grupo_kit_breakdown = (
            [KitBreakdownItem(tipoKit=t, custoKit=c) for t, c in grupo_breakdown_map.items()]
            if grupo_breakdown_map else None
        )

        evento = PricingEvent(
            id=f"grp_{grupo_nome}",
            name=grupo.nome,
            date=projeto_data_evento.isoformat() if projeto_data_evento else "",
            location=grupo_location,
            category=grupo_modalidade,
            totalCapacity=total_capacity,
            currentSales=current_sales,
            salesGoal=sales_goal,
            averageTicket=round(average_ticket, 2),
            kitCost=round(kit_cost, 2),
            dMinus=d_minus,
            isActive=is_active,
            sku=",".join(all_skus),
            pricingMetrics=pricing_metrics,
            elasticityScenarios=elasticity_scenarios,
            decision=decision,
            iscStatus=isc_status,
            kitBreakdown=grupo_kit_breakdown,
        )
        eventos.append(evento)
    
    for projeto in standalone_projetos:
        projeto_codigo = str(projeto.codigo) if projeto.codigo else None
        if not projeto_codigo:
            continue
        
        cad = cadastro_by_projeto_id.get(projeto.id)
        sku = projeto_codigo
        sku_normalized = normalize_sku(sku)
        projeto_data_evento = projeto.data_evento
        dias_enc = get_dias_encerramento(db, projeto_id=projeto.id, cadastro=cad)
        d_minus_inscricoes = calculate_d_minus(projeto_data_evento, dias_encerramento=dias_enc) if projeto_data_evento else 0
        d_minus = calculate_d_minus(projeto_data_evento, dias_encerramento=0) if projeto_data_evento else 0
        is_active = d_minus_inscricoes > 0
        
        if status == 'active' and not is_active:
            continue
        if status == 'closed' and is_active:
            continue
        
        modalidade = str(cad.modalidade) if cad and cad.modalidade else (projeto.modalidade or 'OUTROS')
        categorias_set.add(modalidade)
        
        sales_info = isc_data.get(sku_normalized, {})
        current_sales = sales_info.get('qtd_site', 0)
        current_receita = sales_info.get('receita_liquida_site', 0.0)
        
        average_ticket = round(current_receita / current_sales, 2) if current_sales > 0 else 0.0
        sales_goal = get_meta_from_cadastro(cad) if cad else get_meta_orcada(db, projeto.id)
        total_capacity = sales_goal
        
        kit_cost = kit_costs.get(projeto.id, 50.0)
        
        rolling_avg_14d_real = sales_info.get('media_14d', None)
        rolling_avg_14d_last_year = sales_info.get('media_14d_ano_passado', 0.0)
        
        evento_location = str(cad.localizacao_evento) if cad and cad.localizacao_evento else (projeto.cidade or "Local não definido")
        evento_nome = str(cad.nome) if cad and cad.nome else (projeto.evento or f"Evento {sku}")
        
        pricing_metrics = calculate_pricing_metrics(
            current_sales=current_sales,
            sales_goal=sales_goal,
            d_minus=d_minus,
            average_ticket=average_ticket,
            kit_cost=kit_cost,
            total_capacity=total_capacity,
            rolling_avg_14d_real=rolling_avg_14d_real if rolling_avg_14d_real is not None else None,
            rolling_avg_14d_last_year=rolling_avg_14d_last_year
        )
        
        elasticity_scenarios = calculate_elasticity_scenarios(
            average_ticket=average_ticket,
            kit_cost=kit_cost,
            rolling_avg_14d=pricing_metrics.rollingAvg14d
        )
        
        decision = get_pricing_decision(pricing_metrics, d_minus)
        
        if decision.action in ['increase_now', 'increase_gradual']:
            events_increase += 1
        elif decision.action == 'decrease':
            events_decrease += 1
        else:
            events_maintain += 1
        
        standalone_pricing_eg = None
        standalone_pricing_eg_mapping = db.query(SkuMapping).filter(
            SkuMapping.sku == sku, SkuMapping.evento_grupo.isnot(None), SkuMapping.evento_grupo != '', SkuMapping.ativo == True
        ).first()
        if standalone_pricing_eg_mapping:
            standalone_pricing_eg = standalone_pricing_eg_mapping.evento_grupo

        standalone_pricing_hist = None
        standalone_pricing_curva_info = {"tipo_curva": "linear", "fonte_curva": None, "ano_referencia": None}
        if standalone_pricing_eg:
            try:
                standalone_pricing_hist, standalone_pricing_curva_info = _resolve_hist_pattern(db, standalone_pricing_eg, ano)
            except Exception:
                pass

        standalone_sales_info = isc_data.get(sku_normalized, {})
        standalone_m7d = standalone_sales_info.get('media_7d', 0.0)
        standalone_rolling_14d = standalone_sales_info.get('media_14d', 0.0)
        standalone_m30d = standalone_sales_info.get('media_30d', 0.0)

        pricing_standalone_reg_close = (projeto_data_evento - timedelta(days=dias_enc)) if projeto_data_evento else None
        isc_components = calculate_isc_components(
            current_sales, sales_goal, d_minus,
            media_7d=standalone_m7d,
            media_14d=standalone_rolling_14d,
            media_30d=standalone_m30d,
            hist_pattern=standalone_pricing_hist,
            registration_close_date=pricing_standalone_reg_close,
            curva_info=standalone_pricing_curva_info
        )
        isc = calculate_isc(isc_components, isc_cfg["ia730Weight"], isc_cfg["curvaDWeight"], isc_cfg["rolling14dWeight"])
        isc_status = get_isc_status(isc, isc_cfg["greenThreshold"], isc_cfg["yellowThreshold"])
        
        standalone_bd_raw = kit_breakdowns.get(projeto.id, [])
        standalone_kit_breakdown = (
            [KitBreakdownItem(tipoKit=i["tipoKit"], custoKit=i["custoKit"]) for i in standalone_bd_raw]
            if standalone_bd_raw else None
        )

        evento = PricingEvent(
            id=sku,
            name=evento_nome,
            date=projeto_data_evento.isoformat() if projeto_data_evento else "",
            location=evento_location,
            category=modalidade,
            totalCapacity=total_capacity,
            currentSales=current_sales,
            salesGoal=sales_goal,
            averageTicket=round(average_ticket, 2),
            kitCost=kit_cost,
            dMinus=d_minus,
            isActive=is_active,
            sku=sku,
            pricingMetrics=pricing_metrics,
            elasticityScenarios=elasticity_scenarios,
            decision=decision,
            iscStatus=isc_status,
            kitBreakdown=standalone_kit_breakdown,
        )
        
        eventos.append(evento)
    
    if status == 'active':
        eventos = [e for e in eventos if e.isActive]
    
    eventos.sort(key=lambda x: (-1 if x.decision.action == 'increase_now' else 0 if x.decision.action == 'increase_gradual' else 1, -x.pricingMetrics.ied))
    
    resumo = PricingSummary(
        totalEvents=len([e for e in eventos if e.isActive]),
        eventsToIncrease=events_increase,
        eventsToMaintain=events_maintain,
        eventsToDecrease=events_decrease
    )
    
    return PricingEventsResponse(
        status="success",
        eventos=eventos,
        resumo=resumo,
        categorias=sorted(list(categorias_set)),
        ultima_atualizacao=datetime.now(ZoneInfo("America/Sao_Paulo")).isoformat(),
        avisos=get_isc_warnings()
    )


@router.get("/settings/{key}")
def get_marketing_setting(key: str, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    setting = db.query(MarketingSettings).filter(MarketingSettings.key == key).first()
    if setting:
        return {"status": "success", "key": key, "value": setting.value}
    return {"status": "success", "key": key, "value": None}


@router.put("/settings/{key}")
def update_marketing_setting(key: str, body: dict, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    setting = db.query(MarketingSettings).filter(MarketingSettings.key == key).first()
    if setting:
        setting.value = body.get("value", {})
    else:
        setting = MarketingSettings(key=key, value=body.get("value", {}))
        db.add(setting)
    db.commit()
    if key == "isc_parameters":
        _isc_settings_cache["value"] = None
        _isc_settings_cache["ts"] = 0
        _smart_isc_cache.invalidate()
        event_detail_cache.invalidate()
        eventos_list_cache.invalidate()
    return {"status": "success", "key": key, "value": setting.value}


@router.get("/diagnostico-inscricoes")
def diagnostico_inscricoes(
    ativo_id: int,
    magento_id: str,
    current_user: Usuario = Depends(get_current_user)
):
    """
    Endpoint de diagnóstico para investigar discrepâncias entre o sistema e controles externos.
    Executa múltiplas variações de queries para isolar o filtro causador da diferença.
    """
    result = {"ativo_id": ativo_id, "magento_id": magento_id, "ativo": {}, "magento": {}}

    cupom_join = """
        LEFT JOIN (
            SELECT e.id_cupom_desconto_item, f.en_cupom_classificacao
            FROM sa_cupom_desconto_item AS e
            INNER JOIN sa_cupom_desconto AS f ON f.id_cupom_desconto = e.id_cupom_desconto
        ) AS cupom ON cupom.id_cupom_desconto_item = a.id_cupom_individual
        LEFT JOIN sa_modalidade_categoria AS h ON h.id_categoria = a.id_categoria
    """

    canal_case = """
        CASE
            WHEN a.nr_preco = 0 THEN 'Cortesia'
            WHEN cupom.en_cupom_classificacao IN ('Funcionário','Cortesia Faturada','Coligados','Eventos Terceiros') THEN 'Cortesia'
            WHEN cupom.en_cupom_classificacao = 'Grupos' THEN 'Grupos/B2B'
            WHEN h.ds_categoria LIKE '%%Grup%%' THEN 'Grupos/B2B'
            ELSE 'Site'
        END
    """

    sf_filter = "AND (b.id_campanha_salesforce IS NULL OR b.id_campanha_salesforce NOT LIKE '701d0000000%%')"

    if db_module.engine_ssh is None:
        result["ativo"]["error"] = "engine_ssh not available"
    else:
        try:
            with db_module.engine_ssh.connect() as conn:
                scenarios = [
                    ("A1_site_fl1_status12", "fl_local_inscricao = '1' AND c.id_pedido_status IN (1, 2)", "Site"),
                    ("A2_site_nofl_status12", "c.id_pedido_status IN (1, 2)", "Site"),
                    ("A3_site_fl1_status123", "fl_local_inscricao = '1' AND c.id_pedido_status IN (1, 2, 3)", "Site"),
                    ("A4_site_nofl_status123", "c.id_pedido_status IN (1, 2, 3)", "Site"),
                    ("A5_todos_canais_fl1_status12", "fl_local_inscricao = '1' AND c.id_pedido_status IN (1, 2)", None),
                    ("A6_todos_canais_nofl_status12", "c.id_pedido_status IN (1, 2)", None),
                    ("A7_todos_canais_nofl_status123", "c.id_pedido_status IN (1, 2, 3)", None),
                ]
                for name, pedido_filter, canal_filter in scenarios:
                    canal_clause = f"AND {canal_case} = 'Site'" if canal_filter == "Site" else ""
                    # All interpolated fragments (canal_case, cupom_join, sf_filter,
                    # pedido_filter, canal_clause) are hardcoded SQL constants defined
                    # above — none originate from user input. Only :eid (ativo_id) is
                    # user-supplied and is passed as a named parameter below.
                    sql_scenario = (
                        "SELECT COUNT(DISTINCT a.id_pedido_evento) AS total\n"
                        "FROM sa_pedido_evento AS a\n"
                        "INNER JOIN sa_evento AS b ON b.id_evento = a.id_evento\n"
                        f"INNER JOIN sa_pedido AS c ON c.id_pedido = a.id_pedido AND {pedido_filter}\n"
                        f"{cupom_join}\n"
                        f"WHERE b.id_evento = :eid {sf_filter} {canal_clause}\n"
                    )
                    q = text(sql_scenario)
                    r = conn.execute(q, {"eid": ativo_id}).scalar()
                    result["ativo"][name] = int(r or 0)

                # Breakdown por status e fl_local (sem filtro de canal para ver tudo)
                # All interpolated fragments are hardcoded SQL constants; :eid is the
                # only user-supplied value and is passed as a named parameter.
                sql_breakdown = (
                    "SELECT c.id_pedido_status, c.fl_local_inscricao,\n"
                    f"       {canal_case} AS canal,\n"
                    "       COUNT(DISTINCT a.id_pedido_evento) AS cnt\n"
                    "FROM sa_pedido_evento AS a\n"
                    "INNER JOIN sa_evento AS b ON b.id_evento = a.id_evento\n"
                    "INNER JOIN sa_pedido AS c ON c.id_pedido = a.id_pedido\n"
                    f"{cupom_join}\n"
                    f"WHERE b.id_evento = :eid {sf_filter}\n"
                    f"GROUP BY c.id_pedido_status, c.fl_local_inscricao, {canal_case}\n"
                    f"ORDER BY c.id_pedido_status, c.fl_local_inscricao, canal\n"
                )
                q_breakdown = text(sql_breakdown)
                rows = conn.execute(q_breakdown, {"eid": ativo_id}).fetchall()
                result["ativo"]["breakdown"] = [
                    {"status": r[0], "fl_local": r[1], "canal": r[2], "cnt": int(r[3])}
                    for r in rows
                ]
        except Exception as e:
            result["ativo"]["error"] = str(e)

    if db_module.engine_magento is None:
        result["magento"]["error"] = "engine_magento not available"
    else:
        try:
            safe_mid = str(int(magento_id))
            with db_module.engine_magento.connect() as conn:
                # M1 - query atual (com todos os filtros)
                q_m1 = text("""
SELECT
    COUNT(CASE WHEN so.base_grand_total > 0
        AND NOT (so.discount_description LIKE '%%CORTESIA%%' AND so.base_grand_total < 50)
        AND (so.discount_description IS NULL OR so.discount_description NOT LIKE '%%GRUPOS%%')
        AND (so.coupon_code IS NULL OR so.coupon_code NOT LIKE 'GRUP%%')
        AND soi.price > 0 THEN 1 END) AS qtd_site,
    COUNT(soi.item_id) AS qtd_total_bundle,
    COUNT(CASE WHEN so.base_grand_total > 0 THEN 1 END) AS qtd_grand_total_pos,
    COUNT(CASE WHEN soi.price > 0 THEN 1 END) AS qtd_price_pos
FROM sales_order so
INNER JOIN sales_order_item soi
       ON soi.order_id = so.entity_id AND soi.product_type = 'bundle'
INNER JOIN catalog_product_entity_varchar cpev1
       ON cpev1.entity_id = soi.product_id AND cpev1.attribute_id = 321 AND cpev1.store_id = 0
WHERE so.status IN ('processing', 'complete', 'approved', 'aprovado_link', 'reembolso_parcial', 'closed', 'retirado')
  AND so.state != 'canceled'
  AND cpev1.value = :mid
  AND so.increment_id NOT REGEXP '-[0-9]'
  AND so.created_at < CURDATE() + INTERVAL 1 DAY
""")
                r_m1 = conn.execute(q_m1, {"mid": safe_mid}).fetchone()
                result["magento"]["M1_atual"] = {
                    "qtd_site": int(r_m1[0] or 0),
                    "qtd_total_bundle": int(r_m1[1] or 0),
                    "qtd_grand_total_pos": int(r_m1[2] or 0),
                    "qtd_price_pos": int(r_m1[3] or 0),
                }

                # M2 - sem filtro de cortesia/grupos no CASE (todos os válidos por status)
                q_m2 = text("""
SELECT COUNT(soi.item_id) AS qtd_all_status
FROM sales_order so
INNER JOIN sales_order_item soi
       ON soi.order_id = so.entity_id AND soi.product_type = 'bundle'
INNER JOIN catalog_product_entity_varchar cpev1
       ON cpev1.entity_id = soi.product_id AND cpev1.attribute_id = 321 AND cpev1.store_id = 0
WHERE so.status IN ('processing', 'complete', 'approved', 'aprovado_link', 'reembolso_parcial', 'pending_payment')
  AND so.state != 'canceled'
  AND cpev1.value = :mid
  AND so.increment_id NOT REGEXP '-[0-9]'
  AND so.created_at < CURDATE() + INTERVAL 1 DAY
""")
                r_m2 = conn.execute(q_m2, {"mid": safe_mid}).scalar()
                result["magento"]["M2_all_statuses"] = int(r_m2 or 0)

                # M3 - breakdown por status Magento
                q_m3 = text("""
SELECT so.status, COUNT(soi.item_id) AS cnt
FROM sales_order so
INNER JOIN sales_order_item soi
       ON soi.order_id = so.entity_id AND soi.product_type = 'bundle'
INNER JOIN catalog_product_entity_varchar cpev1
       ON cpev1.entity_id = soi.product_id AND cpev1.attribute_id = 321 AND cpev1.store_id = 0
WHERE cpev1.value = :mid
  AND so.state != 'canceled'
  AND so.increment_id NOT REGEXP '-[0-9]'
  AND so.created_at < CURDATE() + INTERVAL 1 DAY
GROUP BY so.status
ORDER BY cnt DESC
""")
                rows_m3 = conn.execute(q_m3, {"mid": safe_mid}).fetchall()
                result["magento"]["M3_breakdown_status"] = [
                    {"status": r[0], "cnt": int(r[1])} for r in rows_m3
                ]

                # M4 - sem filtro increment_id (inclui sub-pedidos com hífen)
                q_m4 = text("""
SELECT COUNT(soi.item_id) AS qtd_com_subpedidos
FROM sales_order so
INNER JOIN sales_order_item soi
       ON soi.order_id = so.entity_id AND soi.product_type = 'bundle'
INNER JOIN catalog_product_entity_varchar cpev1
       ON cpev1.entity_id = soi.product_id AND cpev1.attribute_id = 321 AND cpev1.store_id = 0
WHERE so.status IN ('processing', 'complete', 'approved', 'aprovado_link', 'reembolso_parcial', 'closed', 'retirado')
  AND so.state != 'canceled'
  AND cpev1.value = :mid
  AND so.created_at < CURDATE() + INTERVAL 1 DAY
""")
                r_m4 = conn.execute(q_m4, {"mid": safe_mid}).scalar()
                result["magento"]["M4_sem_regexp_filter"] = int(r_m4 or 0)
                # M5 - breakdown do que está sendo filtrado (cortesia vs grupos vs preco_zero)
                q_m5 = text("""
SELECT
    SUM(CASE WHEN soi.price = 0 THEN 1 ELSE 0 END) AS excluidos_price_zero,
    SUM(CASE WHEN soi.price > 0 AND so.base_grand_total = 0 THEN 1 ELSE 0 END) AS excluidos_grand_total_zero,
    SUM(CASE WHEN soi.price > 0 AND so.base_grand_total > 0
        AND (so.discount_description LIKE '%%CORTESIA%%' AND so.base_grand_total < 50) THEN 1 ELSE 0 END) AS excluidos_cortesia_barato,
    SUM(CASE WHEN soi.price > 0 AND so.base_grand_total > 0
        AND NOT (so.discount_description LIKE '%%CORTESIA%%' AND so.base_grand_total < 50)
        AND (so.discount_description LIKE '%%GRUPOS%%') THEN 1 ELSE 0 END) AS excluidos_desc_grupos,
    SUM(CASE WHEN soi.price > 0 AND so.base_grand_total > 0
        AND NOT (so.discount_description LIKE '%%CORTESIA%%' AND so.base_grand_total < 50)
        AND (so.discount_description IS NULL OR so.discount_description NOT LIKE '%%GRUPOS%%')
        AND (so.coupon_code LIKE 'GRUP%%') THEN 1 ELSE 0 END) AS excluidos_cupom_grupos,
    SUM(CASE WHEN soi.price > 0 AND so.base_grand_total > 0
        AND NOT (so.discount_description LIKE '%%CORTESIA%%' AND so.base_grand_total < 50)
        AND (so.discount_description IS NULL OR so.discount_description NOT LIKE '%%GRUPOS%%')
        AND (so.coupon_code IS NULL OR so.coupon_code NOT LIKE 'GRUP%%') THEN 1 ELSE 0 END) AS incluidos_site
FROM sales_order so
INNER JOIN sales_order_item soi
       ON soi.order_id = so.entity_id AND soi.product_type = 'bundle'
INNER JOIN catalog_product_entity_varchar cpev1
       ON cpev1.entity_id = soi.product_id AND cpev1.attribute_id = 321 AND cpev1.store_id = 0
WHERE so.status IN ('processing', 'complete', 'approved', 'aprovado_link', 'reembolso_parcial', 'closed', 'retirado')
  AND so.state != 'canceled'
  AND cpev1.value = :mid
  AND so.increment_id NOT REGEXP '-[0-9]'
  AND so.created_at < CURDATE() + INTERVAL 1 DAY
""")
                r_m5 = conn.execute(q_m5, {"mid": safe_mid}).fetchone()
                result["magento"]["M5_exclusao_breakdown"] = {
                    "excluidos_price_zero": int(r_m5[0] or 0),
                    "excluidos_grand_total_zero": int(r_m5[1] or 0),
                    "excluidos_cortesia_barato": int(r_m5[2] or 0),
                    "excluidos_desc_grupos": int(r_m5[3] or 0),
                    "excluidos_cupom_grupos": int(r_m5[4] or 0),
                    "incluidos_site": int(r_m5[5] or 0),
                }

                # M6 - amostras dos pedidos excluidos por discount_description GRUPOS
                q_m6 = text("""
SELECT so.increment_id, so.discount_description, so.coupon_code, so.base_grand_total, soi.price, soi.name
FROM sales_order so
INNER JOIN sales_order_item soi
       ON soi.order_id = so.entity_id AND soi.product_type = 'bundle'
INNER JOIN catalog_product_entity_varchar cpev1
       ON cpev1.entity_id = soi.product_id AND cpev1.attribute_id = 321 AND cpev1.store_id = 0
WHERE so.status IN ('processing', 'complete', 'approved', 'aprovado_link', 'reembolso_parcial', 'closed', 'retirado')
  AND so.state != 'canceled'
  AND cpev1.value = :mid
  AND so.increment_id NOT REGEXP '-[0-9]'
  AND so.created_at < CURDATE() + INTERVAL 1 DAY
  AND soi.price > 0
  AND so.base_grand_total > 0
  AND NOT (so.discount_description LIKE '%%CORTESIA%%' AND so.base_grand_total < 50)
  AND so.discount_description LIKE '%%GRUPOS%%'
LIMIT 10
""")
                rows_m6 = conn.execute(q_m6, {"mid": safe_mid}).fetchall()
                result["magento"]["M6_amostras_excluidos_desc_grupos"] = [
                    {
                        "increment_id": r[0],
                        "discount_description": r[1],
                        "coupon_code": r[2],
                        "base_grand_total": float(r[3] or 0),
                        "soi_price": float(r[4] or 0),
                        "item_name": r[5],
                    }
                    for r in rows_m6
                ]

                # M7 - amostras dos pedidos excluidos por coupon_code GRUP%
                q_m7 = text("""
SELECT so.increment_id, so.discount_description, so.coupon_code, so.base_grand_total, soi.price
FROM sales_order so
INNER JOIN sales_order_item soi
       ON soi.order_id = so.entity_id AND soi.product_type = 'bundle'
INNER JOIN catalog_product_entity_varchar cpev1
       ON cpev1.entity_id = soi.product_id AND cpev1.attribute_id = 321 AND cpev1.store_id = 0
WHERE so.status IN ('processing', 'complete', 'approved', 'aprovado_link', 'reembolso_parcial', 'closed', 'retirado')
  AND so.state != 'canceled'
  AND cpev1.value = :mid
  AND so.increment_id NOT REGEXP '-[0-9]'
  AND so.created_at < CURDATE() + INTERVAL 1 DAY
  AND soi.price > 0
  AND so.base_grand_total > 0
  AND NOT (so.discount_description LIKE '%%CORTESIA%%' AND so.base_grand_total < 50)
  AND (so.discount_description IS NULL OR so.discount_description NOT LIKE '%%GRUPOS%%')
  AND so.coupon_code LIKE 'GRUP%%'
LIMIT 10
""")
                rows_m7 = conn.execute(q_m7, {"mid": safe_mid}).fetchall()
                result["magento"]["M7_amostras_excluidos_cupom_grupos"] = [
                    {
                        "increment_id": r[0],
                        "discount_description": r[1],
                        "coupon_code": r[2],
                        "base_grand_total": float(r[3] or 0),
                        "soi_price": float(r[4] or 0),
                    }
                    for r in rows_m7
                ]

                # M8 - amostras dos 169 com grand_total=0 mas soi.price>0
                # (para entender se são cortesia, grupos ou site com desconto 100%)
                q_m8 = text("""
SELECT so.increment_id, so.discount_description, so.coupon_code,
       so.base_grand_total, soi.price, soi.name,
       so.customer_email
FROM sales_order so
INNER JOIN sales_order_item soi
       ON soi.order_id = so.entity_id AND soi.product_type = 'bundle'
INNER JOIN catalog_product_entity_varchar cpev1
       ON cpev1.entity_id = soi.product_id AND cpev1.attribute_id = 321 AND cpev1.store_id = 0
WHERE so.status IN ('processing', 'complete', 'approved', 'aprovado_link', 'reembolso_parcial', 'closed', 'retirado')
  AND so.state != 'canceled'
  AND cpev1.value = :mid
  AND so.increment_id NOT REGEXP '-[0-9]'
  AND so.created_at < CURDATE() + INTERVAL 1 DAY
  AND soi.price > 0
  AND so.base_grand_total = 0
LIMIT 20
""")
                rows_m8 = conn.execute(q_m8, {"mid": safe_mid}).fetchall()
                result["magento"]["M8_amostras_grand_total_zero"] = [
                    {
                        "increment_id": r[0],
                        "discount_description": r[1],
                        "coupon_code": r[2],
                        "base_grand_total": float(r[3] or 0),
                        "soi_price": float(r[4] or 0),
                        "item_name": r[5],
                        "email": (r[6] or "")[:30],
                    }
                    for r in rows_m8
                ]

                # M9 - breakdown do grand_total=0 por discount_description pattern
                q_m9 = text("""
SELECT
    CASE
        WHEN so.discount_description LIKE '%%CORTESIA%%' THEN 'CORTESIA'
        WHEN so.discount_description LIKE '%%GRUPOS%%' THEN 'GRUPOS'
        WHEN so.coupon_code LIKE 'GRUP%%' THEN 'CUPOM_GRUP'
        WHEN so.coupon_code LIKE '%%CORTESIA%%' THEN 'CUPOM_CORTESIA'
        WHEN so.discount_description IS NULL AND so.coupon_code IS NULL THEN 'SEM_DESC_SEM_CUPOM'
        ELSE CONCAT('outros_desc:', COALESCE(LEFT(so.discount_description,30),'NULL'))
    END AS categoria,
    COUNT(*) AS cnt
FROM sales_order so
INNER JOIN sales_order_item soi
       ON soi.order_id = so.entity_id AND soi.product_type = 'bundle'
INNER JOIN catalog_product_entity_varchar cpev1
       ON cpev1.entity_id = soi.product_id AND cpev1.attribute_id = 321 AND cpev1.store_id = 0
WHERE so.status IN ('processing', 'complete', 'approved', 'aprovado_link', 'reembolso_parcial', 'closed', 'retirado')
  AND so.state != 'canceled'
  AND cpev1.value = :mid
  AND so.increment_id NOT REGEXP '-[0-9]'
  AND so.created_at < CURDATE() + INTERVAL 1 DAY
  AND soi.price > 0
  AND so.base_grand_total = 0
GROUP BY categoria
ORDER BY cnt DESC
""")
                rows_m9 = conn.execute(q_m9, {"mid": safe_mid}).fetchall()
                result["magento"]["M9_grand_total_zero_por_categoria"] = [
                    {"categoria": r[0], "cnt": int(r[1])} for r in rows_m9
                ]

                # M10 - quantidade de CORTESIA com grand_total >= 50 (incluídas na nossa query mas talvez excluídas no controle externo)
                q_m10 = text("""
SELECT
    COUNT(*) AS cortesia_com_total_alto,
    MIN(so.base_grand_total) AS min_total,
    MAX(so.base_grand_total) AS max_total
FROM sales_order so
INNER JOIN sales_order_item soi
       ON soi.order_id = so.entity_id AND soi.product_type = 'bundle'
INNER JOIN catalog_product_entity_varchar cpev1
       ON cpev1.entity_id = soi.product_id AND cpev1.attribute_id = 321 AND cpev1.store_id = 0
WHERE so.status IN ('processing', 'complete', 'approved', 'aprovado_link', 'reembolso_parcial', 'closed', 'retirado')
  AND so.state != 'canceled'
  AND cpev1.value = :mid
  AND so.increment_id NOT REGEXP '-[0-9]'
  AND so.created_at < CURDATE() + INTERVAL 1 DAY
  AND soi.price > 0
  AND so.base_grand_total > 0
  AND so.discount_description LIKE '%%CORTESIA%%'
""")
                r_m10 = conn.execute(q_m10, {"mid": safe_mid}).fetchone()
                result["magento"]["M10_cortesia_grand_total_alto"] = {
                    "count": int(r_m10[0] or 0),
                    "min_total": float(r_m10[1] or 0),
                    "max_total": float(r_m10[2] or 0),
                }

                # M11 - query simples sem filtros de cortesia/grupos (apenas price > 0 e grand_total > 0)
                # Para ver se o controle externo conta de forma mais simples
                q_m11 = text("""
SELECT COUNT(*) AS qtd_sem_filtros_desc
FROM sales_order so
INNER JOIN sales_order_item soi
       ON soi.order_id = so.entity_id AND soi.product_type = 'bundle'
INNER JOIN catalog_product_entity_varchar cpev1
       ON cpev1.entity_id = soi.product_id AND cpev1.attribute_id = 321 AND cpev1.store_id = 0
WHERE so.status IN ('processing', 'complete', 'approved', 'aprovado_link', 'reembolso_parcial', 'closed', 'retirado')
  AND so.state != 'canceled'
  AND cpev1.value = :mid
  AND so.increment_id NOT REGEXP '-[0-9]'
  AND so.created_at < CURDATE() + INTERVAL 1 DAY
  AND soi.price > 0
  AND so.base_grand_total > 0
""")
                r_m11 = conn.execute(q_m11, {"mid": safe_mid}).scalar()
                result["magento"]["M11_sem_filtros_desc_coupon"] = int(r_m11 or 0)

                # M12 - breakdown por discount_description das ordens com grand_total > 0 e price > 0
                # (incluindo CORTESIA e GRUPOS para ver exatamente o que está sendo contado)
                q_m12 = text("""
SELECT
    CASE
        WHEN so.discount_description IS NULL AND so.coupon_code IS NULL THEN 'SEM_DESCONTO'
        WHEN so.discount_description LIKE '%%CORTESIA%%' THEN 'CORTESIA'
        WHEN so.discount_description LIKE '%%GRUPOS%%' THEN 'GRUPOS'
        WHEN so.coupon_code LIKE 'GRUP%%' THEN 'CUPOM_GRUPO'
        ELSE 'OUTROS_DESC'
    END AS categoria,
    COUNT(*) AS cnt
FROM sales_order so
INNER JOIN sales_order_item soi
       ON soi.order_id = so.entity_id AND soi.product_type = 'bundle'
INNER JOIN catalog_product_entity_varchar cpev1
       ON cpev1.entity_id = soi.product_id AND cpev1.attribute_id = 321 AND cpev1.store_id = 0
WHERE so.status IN ('processing', 'complete', 'approved', 'aprovado_link', 'reembolso_parcial', 'closed', 'retirado')
  AND so.state != 'canceled'
  AND cpev1.value = :mid
  AND so.increment_id NOT REGEXP '-[0-9]'
  AND so.created_at < CURDATE() + INTERVAL 1 DAY
  AND soi.price > 0
  AND so.base_grand_total > 0
GROUP BY categoria
ORDER BY cnt DESC
""")
                rows_m12 = conn.execute(q_m12, {"mid": safe_mid}).fetchall()
                result["magento"]["M12_breakdown_com_grand_total_pos"] = [
                    {"categoria": r[0], "cnt": int(r[1])} for r in rows_m12
                ]

                # M13 - query usando a lógica do controle externo:
                # Cortesia = soi_child.price - soi_child.discount_amount = 0
                # Usa MAX(soi_child.price - soi_child.discount_amount) por bundle
                # para evitar multiplicar linhas com múltiplos filhos
                q_m13 = text("""
SELECT
    SUM(CASE
        WHEN child_agg.net_price > 0
            AND (so.discount_description IS NULL OR so.discount_description NOT LIKE '%%GRUPOS%%')
            AND (so.coupon_code IS NULL OR so.coupon_code NOT LIKE 'GRUP%%')
        THEN 1 ELSE 0 END) AS qtd_site_logica_externa,
    SUM(CASE WHEN child_agg.net_price = 0 THEN 1 ELSE 0 END) AS cortesia_child_zero,
    SUM(CASE WHEN so.discount_description LIKE '%%GRUPOS%%' THEN 1 ELSE 0 END) AS excluidos_grupos_desc,
    SUM(CASE WHEN so.coupon_code LIKE 'GRUP%%' THEN 1 ELSE 0 END) AS excluidos_cupom_grupo,
    COUNT(*) AS total_bundles
FROM sales_order so
INNER JOIN sales_order_item soi
       ON soi.order_id = so.entity_id AND soi.product_type = 'bundle'
INNER JOIN catalog_product_entity_varchar cpev1
       ON cpev1.entity_id = soi.product_id AND cpev1.attribute_id = 321 AND cpev1.store_id = 0
LEFT JOIN (
    SELECT parent_item_id,
           MAX(price - COALESCE(discount_amount, 0)) AS net_price
    FROM sales_order_item
    WHERE product_type != 'bundle'
    GROUP BY parent_item_id
) AS child_agg ON child_agg.parent_item_id = soi.item_id
WHERE so.status IN ('processing', 'complete', 'approved', 'aprovado_link', 'reembolso_parcial', 'closed', 'retirado')
  AND so.state != 'canceled'
  AND cpev1.value = :mid
  AND so.increment_id NOT REGEXP '-[0-9]'
  AND so.created_at < CURDATE() + INTERVAL 1 DAY
""")
                r_m13 = conn.execute(q_m13, {"mid": safe_mid}).fetchone()
                result["magento"]["M13_logica_externa_child"] = {
                    "qtd_site": int(r_m13[0] or 0),
                    "cortesia_child_zero": int(r_m13[1] or 0),
                    "excluidos_grupos_desc": int(r_m13[2] or 0),
                    "excluidos_cupom_grupo": int(r_m13[3] or 0),
                    "total_com_child": int(r_m13[4] or 0),
                }

                # M14 - lógica EXATA do controle externo do usuário:
                # - JOIN soi com price > 0 (bundle)
                # - JOIN soi_child com product_type='simple', price > 0, nome Distância/Modalidade
                # - CASE: cortesia = grand_total=0 AND child net=0; Grupos = desc/coupon; Else Site
                q_m14 = text("""
SELECT
    COUNT(CASE
        WHEN NOT (so.base_grand_total = 0 AND (soi_child.price - soi_child.discount_amount) = 0)
            AND (so.discount_description IS NULL OR so.discount_description NOT LIKE '%%GRUPOS%%')
            AND (so.coupon_code IS NULL OR so.coupon_code NOT LIKE 'GRUP%%')
        THEN 1 END) AS qtd_site,
    COUNT(CASE
        WHEN so.base_grand_total = 0 AND (soi_child.price - soi_child.discount_amount) = 0
        THEN 1 END) AS cortesia,
    COUNT(CASE
        WHEN NOT (so.base_grand_total = 0 AND (soi_child.price - soi_child.discount_amount) = 0)
            AND (so.discount_description LIKE '%%GRUPOS%%' OR so.coupon_code LIKE 'GRUP%%')
        THEN 1 END) AS grupos,
    COUNT(*) AS total
FROM sales_order so
JOIN sales_order_item soi
    ON soi.order_id = so.entity_id
    AND soi.product_type = 'bundle'
    AND soi.price > 0
JOIN catalog_product_entity_varchar cpev1
    ON cpev1.entity_id = soi.product_id
    AND cpev1.attribute_id = 321
    AND cpev1.store_id = 0
    AND cpev1.value = :mid
JOIN sales_order_item soi_child
    ON soi_child.parent_item_id = soi.item_id
    AND soi_child.product_type = 'simple'
    AND soi_child.price > 0
    AND (
        soi_child.name LIKE '%%Distância%%'
     OR soi_child.name LIKE '%%Distancia%%'
     OR soi_child.name LIKE '%%Distâncias%%'
     OR soi_child.name LIKE '%%Modalidade%%'
    )
WHERE so.status IN ('processing', 'complete', 'approved', 'aprovado_link', 'reembolso_parcial', 'closed', 'retirado')
  AND so.state NOT IN ('canceled')
  AND so.increment_id NOT REGEXP '-[0-9]'
  AND so.created_at < CURDATE() + INTERVAL 1 DAY
""")
                r_m14 = conn.execute(q_m14, {"mid": safe_mid}).fetchone()
                result["magento"]["M14_logica_exata_externa"] = {
                    "qtd_site": int(r_m14[0] or 0),
                    "cortesia": int(r_m14[1] or 0),
                    "grupos": int(r_m14[2] or 0),
                    "total": int(r_m14[3] or 0),
                }


        except Exception as e:
            result["magento"]["error"] = str(e)

    return result
