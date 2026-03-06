from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import text, bindparam
from typing import Optional, List
from pydantic import BaseModel
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo
from ...core.database import get_db, engine_ativo, engine_ssh
from ...core import database as db_module
from ...core.security import get_current_user
from ...models.dimensoes import DimProjeto, EventoConsolidado, SkuMapping, EventoGrupo as EventoGrupoModel, MarketingSettings
from ...models.user import Usuario
from ...models.cadastro_evento import CadastroEvento, CadastroKitProduto, CadastroKitProdutoItem
from .inscricoes_consolidado import normalize_sku
import logging
import asyncio
from concurrent.futures import ThreadPoolExecutor
import httpx

logger = logging.getLogger(__name__)

_cadastro_cache: dict = {}

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
                           cat_ativo_grouped: dict = None, cat_magento_grouped: dict = None):
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


def _wq_sku_mappings_by_sku(db: Session, sku: str, anos: list = None):
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


def _wq_sku_mappings_by_skus(db: Session, skus: list, anos: list = None):
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
    projeto = _wq_dim_projeto_by_id(db, projeto_id)
    fallback = int(projeto.capacidade_maxima) if projeto and projeto.capacidade_maxima else 1000
    _cadastro_cache[projeto_id] = fallback
    return fallback

def get_meta_from_cadastro(cadastro: CadastroEvento) -> int:
    if cadastro.atletas_site_pago and cadastro.atletas_site_pago > 0:
        return int(cadastro.atletas_site_pago)
    return int(cadastro.capacidade_maxima) if cadastro.capacidade_maxima else 1000

def get_meta_orcada_projetos(db: Session, projetos: list) -> int:
    total = 0
    for p in projetos:
        total += get_meta_orcada(db, p.id)
    return total if total > 0 else 1000


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
            AND b.id_campanha_salesforce NOT LIKE '701d0000000%'
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


def fetch_daily_sales_magento(location_id: str, start_date: date, end_date: date) -> dict:
    """
    Busca vendas diárias do Magento para um evento específico (por location_id) dentro de um período.
    Retorna um dicionário {data: quantidade_vendida}
    Usa os mesmos filtros da query build_query_magento para consistência.
    """
    if db_module.engine_magento is None:
        return {}
    
    try:
        query = """
        SELECT 
            DATE(so.created_at) AS data_venda,
            COUNT(soi.item_id) AS quantidade
        FROM sales_order AS so
        LEFT JOIN sales_order_item AS soi ON soi.order_id = so.entity_id
        LEFT JOIN webpos_location AS wl ON so.location_pickup_id = wl.location_id
        WHERE 
            wl.location_id = :location_id
            AND so.status IN ('Processing', 'Complete', 'approved')
            AND soi.product_type = 'Bundle'
            AND DATE(so.created_at) >= :start_date
            AND DATE(so.created_at) <= :end_date
            AND so.increment_id NOT LIKE '%-1%'
            AND so.increment_id NOT LIKE '%-2%'
            AND so.increment_id NOT LIKE '%-3%'
            AND so.increment_id NOT LIKE '%-4%'
            AND so.increment_id NOT LIKE '%-5%'
            AND so.increment_id NOT LIKE '%-6%'
            AND so.increment_id NOT LIKE '%-7%'
            AND so.increment_id NOT LIKE '%-8%'
            AND so.increment_id NOT LIKE '%-9%'
            AND so.increment_id NOT LIKE '%-10%'
            AND so.increment_id NOT LIKE '%-11%'
            AND so.increment_id NOT LIKE '%-12%'
            AND so.increment_id NOT LIKE '%-13%'
            AND so.increment_id NOT LIKE '%-14%'
            AND so.increment_id NOT LIKE '%-15%'
            AND so.increment_id NOT LIKE '%-16%'
            AND so.increment_id NOT LIKE '%-17%'
        GROUP BY DATE(so.created_at)
        ORDER BY data_venda
        """
        params = {
            "location_id": location_id,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        }
        
        with db_module.engine_magento.connect() as conn:
            result = conn.execute(text(query), params)
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
        logger.error(f"Erro ao buscar vendas diárias do Magento: {e}")
        return {}


def get_location_id_from_sku(db: Session, sku: str) -> Optional[str]:
    mappings = _wq_sku_mappings_by_sku(db, sku)
    for m in mappings:
        if m.fonte == 'MAGENTO' and m.id_externo:
            return str(m.id_externo)
    return None


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

    today = date.today()
    if end_after > today:
        return {"vendas_antes": None, "vendas_depois": None, "impacto_percentual": None,
                "status": "aguardando_dados"}

    sku = projeto.codigo.upper().strip()
    from app.core.cache import get_warmup_sku_mappings_by_sku
    all_sku_maps = get_warmup_sku_mappings_by_sku(sku)
    if not all_sku_maps:
        return {"vendas_antes": None, "vendas_depois": None, "impacto_percentual": None}

    ano = data_acao.year if isinstance(data_acao, date) else acao.data_acao.year if acao.data_acao else date.today().year
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
    id_evento = get_id_evento_from_projeto(db, acao.projeto_id)
    location_id = get_location_id_from_sku(db, sku)
    
    if not id_evento and not location_id:
        return {"vendas_antes": None, "vendas_depois": None, "impacto_percentual": None}
    
    data_acao = acao.data_acao
    if isinstance(data_acao, datetime):
        data_acao = data_acao.date()
    
    start_before = data_acao - timedelta(days=7)
    end_before = data_acao - timedelta(days=1)
    
    start_after = data_acao + timedelta(days=1)
    end_after = data_acao + timedelta(days=7)
    
    today = date.today()
    if end_after > today:
        return {"vendas_antes": None, "vendas_depois": None, "impacto_percentual": None, 
                "status": "aguardando_dados"}
    
    sales_before_ativo = fetch_daily_sales_ativo(id_evento, start_before, end_before) if id_evento else {}
    sales_after_ativo = fetch_daily_sales_ativo(id_evento, start_after, end_after) if id_evento else {}
    
    sales_before_magento = fetch_daily_sales_magento(location_id, start_before, end_before) if location_id else {}
    sales_after_magento = fetch_daily_sales_magento(location_id, start_after, end_after) if location_id else {}
    
    vendas_antes_ativo = sum(sales_before_ativo.values()) if sales_before_ativo else 0
    vendas_depois_ativo = sum(sales_after_ativo.values()) if sales_after_ativo else 0
    vendas_antes_magento = sum(sales_before_magento.values()) if sales_before_magento else 0
    vendas_depois_magento = sum(sales_after_magento.values()) if sales_after_magento else 0
    
    vendas_antes = vendas_antes_ativo + vendas_antes_magento
    vendas_depois = vendas_depois_ativo + vendas_depois_magento
    
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

router = APIRouter(prefix="/marketing", tags=["Marketing ISC"])

class ISCComponents(BaseModel):
    ia730: float
    curvaDPercent: float
    rolling14d: float

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
    suggestedAction: str
    lastAction: Optional[CommercialAction] = None
    activeAction: Optional[ActiveActionInfo] = None
    isActive: bool
    sku: Optional[str] = None
    kitCostPerUnit: float = 0.0
    margemOrcadaUnit: float = 0.0
    margemOrcadaTotal: float = 0.0
    margemOrcadaPct: float = 0.0
    margemRealizadaUnit: float = 0.0
    margemRealizadaTotal: float = 0.0
    margemRealizadaPct: float = 0.0

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

def get_suggested_action(isc: float, d_minus: int, green_threshold: float = 1.10, yellow_threshold: float = 0.90, promotion_deadline: int = 40) -> str:
    status = get_isc_status(isc, green_threshold, yellow_threshold)
    
    if status == "accelerating":
        return "Evento forte. Considere ajuste de preço para cima."
    
    if status == "stable":
        if d_minus >= promotion_deadline:
            return "Evento estável. Monitore e reforce comunicação."
        return "Evento estável. Apenas ajustes de comunicação."
    
    if d_minus >= promotion_deadline:
        return "Evento fraco. Janela aberta para ação promocional."
    
    return "⚠️ Evento fraco, mas fora da janela de promoção. Apenas reforço de comunicação."

def get_active_actions_for_projects(db: Session, projeto_ids: list) -> dict:
    """
    Retorna ações comerciais ativas (criadas nos últimos 7 dias) para uma lista de projeto_ids.
    Retorna um dict {projeto_id: ActiveActionInfo}
    """
    from ...models.dimensoes import AcaoComercial
    if not projeto_ids:
        return {}
    
    today = date.today()
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
    
    today = date.today()
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


def get_dias_encerramento(db: Session, projeto_id: int = None, cadastro: object = None) -> int:
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

def calculate_d_minus(event_date: date, reference_year: int = None, dias_encerramento: int = 2) -> int:
    if not event_date:
        return 0
    registration_close = event_date - timedelta(days=dias_encerramento)
    today = date.today()
    if reference_year is not None and reference_year != today.year:
        try:
            today = today.replace(year=reference_year)
        except ValueError:
            today = today.replace(year=reference_year, day=28)
    delta = (registration_close - today).days
    return max(0, delta)

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
                              media_14d: float = None, daily_sales_dict: dict = None,
                              media_7d: float = None, media_30d: float = None,
                              hist_pattern: dict = None) -> ISCComponents:
    if sales_goal == 0:
        return ISCComponents(ia730=1.0, curvaDPercent=1.0, rolling14d=1.0)
    
    if daily_sales_dict:
        daily_sales_dict = {(date.fromisoformat(k) if isinstance(k, str) else k): v for k, v in daily_sales_dict.items()}
    
    from datetime import timedelta
    yesterday = date.today() - timedelta(days=1)
    if daily_sales_dict and len(daily_sales_dict) > 0:
        current_sales = sum(v for k, v in daily_sales_dict.items() if k <= yesterday)
    
    progress_percent = current_sales / sales_goal

    if hist_pattern and len(hist_pattern) > 0:
        expected_progress = _interpolate_hist_pattern(hist_pattern, d_minus)
        if expected_progress <= 0:
            expected_progress = 0.01
        curva_d_percent = progress_percent / expected_progress
    else:
        total_days = 90
        elapsed_days = max(1, total_days - d_minus)
        expected_progress = elapsed_days / total_days
        if expected_progress == 0:
            expected_progress = 0.01
        curva_d_percent = progress_percent / expected_progress

    real_7d = None
    real_14d = None
    real_30d = None
    sum_14d_raw = None
    if daily_sales_dict and len(daily_sales_dict) > 0:
        s7 = sum(daily_sales_dict.get(yesterday - timedelta(days=i), 0) for i in range(7))
        s14 = sum(daily_sales_dict.get(yesterday - timedelta(days=i), 0) for i in range(14))
        s30 = sum(daily_sales_dict.get(yesterday - timedelta(days=i), 0) for i in range(30))
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
            ia730 = effective_7d / effective_30d
            ia730_calculated = True
        elif effective_7d > 0:
            ia730 = 1.2
            ia730_calculated = True
    
    if not ia730_calculated:
        ia730 = curva_d_percent

    d_minus_yesterday = d_minus + 1

    expected_14d_sales = None
    if hist_pattern and len(hist_pattern) > 0 and sales_goal > 0:
        expected_at_yesterday = _interpolate_hist_pattern(hist_pattern, d_minus_yesterday)
        expected_14d_ago = _interpolate_hist_pattern(hist_pattern, d_minus_yesterday + 14)
        expected_14d_sales = (expected_at_yesterday - expected_14d_ago) * sales_goal
    elif sales_goal > 0:
        total_days = 90
        expected_14d_sales = (14 / total_days) * sales_goal

    if expected_14d_sales is not None and expected_14d_sales > 0 and sum_14d_raw is not None:
        rolling14d = sum_14d_raw / expected_14d_sales
    elif effective_14d is not None and effective_14d > 0 and expected_14d_sales is not None and expected_14d_sales > 0:
        rolling14d = (effective_14d * 14) / expected_14d_sales
    else:
        rolling14d = (curva_d_percent + ia730) / 2
    
    return ISCComponents(
        ia730=round(ia730, 4),
        curvaDPercent=round(curva_d_percent, 4),
        rolling14d=round(rolling14d, 4)
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
    from datetime import timedelta
    from ...models.dimensoes import SkuMapping
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
        rows = _fetch_daily_sales_magento_by_ids(list(set(prev_magento_ids)))
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


def fetch_real_daily_sales_for_projetos(db: Session, projetos: list, days_history: int = None, sales_goal: int = 1000, ano: int = None, evento_grupo: str = None, data_evento: date = None, preloaded_hist_pattern: object = "NOT_SET") -> list:
    from datetime import timedelta
    from ...models.dimensoes import SkuMapping
    from ...services.snapshot_service import get_snapshot_vendas, get_latest_snapshot_date
    
    today = date.today()
    yesterday = today - timedelta(days=1)
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
    if evento_grupo:
        snapshot_data = get_snapshot_vendas(db, evento_grupo, data_fim=yesterday)
        if snapshot_data:
            all_daily.update(snapshot_data)
            snapshot_used = True
            logger.debug(f"Snapshot loaded for '{evento_grupo}': {len(snapshot_data)} days up to {yesterday}")

    if not snapshot_used:
        if ativo_ids:
            ativo_rows = _fetch_daily_sales_ativo_by_ids(list(set(ativo_ids)))
            for row in ativo_rows:
                d = date.fromisoformat(row['dia']) if isinstance(row['dia'], str) else row['dia']
                all_daily[d] = all_daily.get(d, 0) + row['qtd']
        
        if magento_ids:
            magento_rows = _fetch_daily_sales_magento_by_ids(list(set(magento_ids)))
            for row in magento_rows:
                d = date.fromisoformat(row['dia']) if isinstance(row['dia'], str) else row['dia']
                all_daily[d] = all_daily.get(d, 0) + row['qtd']
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
                today_sales = _fetch_today_sales_magento_by_ids(list(set(magento_ids)))
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
    
    all_dates = [start_date + timedelta(days=i) for i in range((end_date - start_date).days + 1)]
    total_days = len(all_dates)

    hist_pattern = None
    if preloaded_hist_pattern != "NOT_SET":
        hist_pattern = preloaded_hist_pattern
    elif evento_grupo and data_evento:
        try:
            hist_pattern = _fetch_previous_year_cumulative_pattern(db, evento_grupo, ano)
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
                pct = 0.0
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
                curva_pct = 0.0
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
    
    return result


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


def _calc_margin_fields(budget_ticket: float, kit_cost: float, sales_goal: int,
                        avg_ticket: float, current_sales: int, current_receita: float) -> dict:
    has_budget = budget_ticket > 0 and kit_cost > 0
    has_sales = current_sales > 0 and avg_ticket > 0

    margem_orcada_unit = round(budget_ticket - kit_cost, 2) if has_budget else 0.0
    margem_orcada_total = round(margem_orcada_unit * sales_goal, 2) if has_budget else 0.0
    margem_orcada_pct = round((margem_orcada_unit / budget_ticket) * 100, 1) if has_budget else 0.0

    margem_realizada_unit = round(avg_ticket - kit_cost, 2) if has_sales else 0.0
    margem_realizada_total = round(current_receita - (kit_cost * current_sales), 2) if has_sales else 0.0
    margem_realizada_pct = round((margem_realizada_unit / avg_ticket) * 100, 1) if has_sales else 0.0

    return {
        "kitCostPerUnit": round(kit_cost, 2),
        "margemOrcadaUnit": margem_orcada_unit,
        "margemOrcadaTotal": margem_orcada_total,
        "margemOrcadaPct": margem_orcada_pct,
        "margemRealizadaUnit": margem_realizada_unit,
        "margemRealizadaTotal": margem_realizada_total,
        "margemRealizadaPct": margem_realizada_pct,
    }


_isc_cache = {}
_isc_cache_timestamp = None

from ...core.cache import isc_cache as _smart_isc_cache, event_detail_cache, daily_sales_cache, curva_cache, medias_cache, eventos_list_cache, cache_scheduler, CURRENT_YEAR_TTL

def build_query_isc_ativo() -> str:
    return """
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
            WHEN (f.en_cupom_classificacao IS NULL OR NOT f.en_cupom_classificacao)
             AND h.ds_categoria NOT LIKE '%%Grup%%'
             AND c.nr_total > 0 THEN 1 ELSE 0
        END)                                                                 AS qtd_site,

        SUM(CASE
            WHEN (f.en_cupom_classificacao IS NULL OR NOT f.en_cupom_classificacao)
             AND h.ds_categoria NOT LIKE '%%Grup%%'
             AND c.nr_total > 0
             AND c.dt_pedido >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
            THEN 1 ELSE 0
        END)                                                                 AS qtd_30d,

        SUM(CASE
            WHEN (f.en_cupom_classificacao IS NULL OR NOT f.en_cupom_classificacao)
             AND h.ds_categoria NOT LIKE '%%Grup%%'
             AND c.nr_total > 0
             AND c.dt_pedido >= DATE_SUB(CURDATE(), INTERVAL 14 DAY)
            THEN 1 ELSE 0
        END)                                                                 AS qtd_14d,

        SUM(CASE
            WHEN (f.en_cupom_classificacao IS NULL OR NOT f.en_cupom_classificacao)
             AND h.ds_categoria NOT LIKE '%%Grup%%'
             AND c.nr_total > 0
             AND c.dt_pedido >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)
            THEN 1 ELSE 0
        END)                                                                 AS qtd_7d,

        SUM(CASE
            WHEN (f.en_cupom_classificacao IS NULL OR NOT f.en_cupom_classificacao)
             AND h.ds_categoria NOT LIKE '%%Grup%%'
             AND c.nr_total > 0
            THEN
                GREATEST(0, a.nr_preco
                    - COALESCE(a.nr_desconto_individual, 0)
                    - COALESCE(h.vl_kit, 0))
            ELSE 0
        END)                                                                 AS inscricao_liquida

    FROM sa_evento AS b

    INNER JOIN sa_pedido_evento AS a
        ON a.id_evento = b.id_evento

    INNER JOIN sa_pedido AS c
        ON c.id_pedido = a.id_pedido
       AND c.fl_local_inscricao = '1'
       AND c.id_pedido_status IN (1, 2)

    LEFT JOIN sa_modalidade_categoria AS h
        ON h.id_categoria = a.id_categoria

    LEFT JOIN sa_cupom_desconto_item AS e
        ON e.id_cupom_desconto_item = a.id_cupom_individual

    LEFT JOIN sa_cupom_desconto AS f
        ON f.id_cupom_desconto = e.id_cupom_desconto

    WHERE
        b.dt_evento >= MAKEDATE(YEAR(CURDATE()) - 1, 1)
        AND b.dt_evento <  MAKEDATE(YEAR(CURDATE()) + 1, 1)
        AND c.dt_pedido < CURDATE()

        AND (b.id_campanha_salesforce IS NULL
             OR b.id_campanha_salesforce NOT LIKE '701d0000000%%')

    GROUP BY
        b.id_evento,
        b.ds_evento,
        b.dt_evento
) AS base
ORDER BY base.id_evento;
"""


def build_query_isc_magento() -> str:
    return """
SELECT
    cpev1.value                                                              AS "ID Evento",
    cpev2.value                                                              AS "Evento",

    COUNT(DISTINCT soi.item_id)                                              AS "Qtd Site",

    ROUND(SUM(
        CASE
            WHEN soi.price = 0 THEN 0
            ELSE CASE
                WHEN soi.name LIKE '%%plus%%'  THEN soi.price - 69.00
                WHEN soi.name LIKE '%%vip%%'   THEN soi.price - 199.99
                WHEN soi.name LIKE '%%super%%' THEN soi.price - 269.00
                ELSE soi.price
            END
            + COALESCE(so.discount_amount, 0) * (soi.price / NULLIF(so.base_subtotal, 0))
            - CASE
                WHEN cg.customer_group_id = 4 THEN 0
                WHEN soiaa.price = 14.90
                 AND cg.customer_group_id IN (0, 1, 2, 3, 5, 7) THEN 14.90
                ELSE 0
              END
        END
    ), 2)                                                                    AS "Inscrição Líquida",

    ROUND(SUM(
        CASE
            WHEN soi.price = 0 THEN 0
            ELSE CASE
                WHEN soi.name LIKE '%%plus%%'  THEN soi.price - 69.00
                WHEN soi.name LIKE '%%vip%%'   THEN soi.price - 199.99
                WHEN soi.name LIKE '%%super%%' THEN soi.price - 269.00
                ELSE soi.price
            END
            + COALESCE(so.discount_amount, 0) * (soi.price / NULLIF(so.base_subtotal, 0))
            - CASE
                WHEN cg.customer_group_id = 4 THEN 0
                WHEN soiaa.price = 14.90
                 AND cg.customer_group_id IN (0, 1, 2, 3, 5, 7) THEN 14.90
                ELSE 0
              END
        END
    ) / NULLIF(COUNT(DISTINCT soi.item_id), 0), 2)                          AS "Ticket Médio",

    ROUND(COUNT(DISTINCT CASE
        WHEN so.created_at >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
        THEN soi.item_id END) / 30.0, 2)                                    AS "Média Diária 30d",

    ROUND(COUNT(DISTINCT CASE
        WHEN so.created_at >= DATE_SUB(CURDATE(), INTERVAL 14 DAY)
        THEN soi.item_id END) / 14.0, 2)                                    AS "Média Diária 14d",

    ROUND(COUNT(DISTINCT CASE
        WHEN so.created_at >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)
        THEN soi.item_id END) / 7.0, 2)                                     AS "Média Diária 7d"

FROM sales_order so
LEFT JOIN sales_order_item soi
       ON soi.order_id = so.entity_id
      AND soi.product_type = 'bundle'
LEFT JOIN catalog_product_entity_varchar cpev1
       ON cpev1.entity_id = soi.product_id
      AND cpev1.attribute_id = 321
LEFT JOIN catalog_product_entity_varchar cpev2
       ON cpev2.entity_id = cpev1.value
      AND cpev2.attribute_id = 73
LEFT JOIN catalog_product_entity_datetime cped
       ON cped.entity_id = cpev1.value
      AND cped.attribute_id = 195
LEFT JOIN (
    SELECT * FROM sales_order_item WHERE name LIKE '%%persona%%'
) AS soiaa ON soiaa.parent_item_id = soi.item_id
LEFT JOIN customer_group AS cg
       ON cg.customer_group_id = so.customer_group_id
WHERE
    so.status IN ('processing', 'complete', 'approved', 'aprovado_link', 'reembolso_parcial')
AND soi.price > 0
AND so.base_grand_total > 0
AND so.created_at < CURDATE()
AND (so.discount_description IS NULL OR so.discount_description NOT LIKE '%%Grup%%')
AND so.increment_id NOT LIKE '%%-1%%'
AND so.increment_id NOT LIKE '%%-2%%'
AND so.increment_id NOT LIKE '%%-3%%'
AND so.increment_id NOT LIKE '%%-4%%'
AND so.increment_id NOT LIKE '%%-5%%'
AND so.increment_id NOT LIKE '%%-6%%'
AND so.increment_id NOT LIKE '%%-7%%'
AND so.increment_id NOT LIKE '%%-8%%'
AND so.increment_id NOT LIKE '%%-9%%'
AND so.increment_id NOT LIKE '%%-10%%'
AND so.increment_id NOT LIKE '%%-11%%'
AND so.increment_id NOT LIKE '%%-12%%'
AND so.increment_id NOT LIKE '%%-13%%'
AND so.increment_id NOT LIKE '%%-14%%'
AND so.increment_id NOT LIKE '%%-15%%'
AND so.increment_id NOT LIKE '%%-16%%'
AND so.increment_id NOT LIKE '%%-17%%'
AND YEAR(cped.value) IN (YEAR(CURDATE()), YEAR(CURDATE()) - 1)

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


def fetch_isc_data_magento():
    return _fetch_with_retry(db_module.engine_magento, build_query_isc_magento, "Magento")


_isc_warnings = []

def fetch_isc_pricing_data(db: Session = None, force_refresh: bool = False) -> dict:
    global _isc_cache, _isc_cache_timestamp, _isc_warnings
    import time

    current_year = datetime.now().year
    smart_cache_key = f"{current_year}_isc"
    
    if not force_refresh:
        cached = _smart_isc_cache.get(smart_cache_key)
        if cached is not None:
            cache_info = _smart_isc_cache.get_info(smart_cache_key)
            logger.info(f"ISC cache HIT: key={smart_cache_key}, age={cache_info.get('age_seconds', '?')}s")
            return cached
        else:
            logger.info(f"ISC cache MISS: key={smart_cache_key}")
    else:
        logger.info(f"ISC cache BYPASS (force_refresh): key={smart_cache_key}")

    current_time = time.time()

    from .inscricoes_consolidado import get_sku_mappings_from_db, enrich_with_mappings

    warnings = []

    mappings = None
    if db:
        try:
            mappings = get_sku_mappings_from_db(db)
        except Exception as e:
            logger.warning(f"Erro ao buscar mapeamentos SKU para ISC: {e}")

    all_data = {}

    future_ativo = _rolling_avg_executor.submit(fetch_isc_data_ativo)
    future_magento = _rolling_avg_executor.submit(fetch_isc_data_magento)

    try:
        dados_ativo = future_ativo.result(timeout=120)
    except Exception as e:
        logger.error(f"Erro ISC Ativo (executor): {e}")
        dados_ativo = []
        warnings.append("Falha ao buscar dados do banco Ativo: timeout ou erro de conexão. Os dados exibidos contêm apenas inscrições do Magento.")

    try:
        dados_magento = future_magento.result(timeout=120)
    except Exception as e:
        logger.error(f"Erro ISC Magento (executor): {e}")
        dados_magento = []
        warnings.append("Falha ao buscar dados do banco Magento: timeout ou erro de conexão. Os dados exibidos contêm apenas inscrições do Ativo.")

    if isinstance(dados_ativo, dict) and 'error' in dados_ativo:
        warnings.append(f"Erro no banco Ativo: {dados_ativo['error']}. Os dados exibidos contêm apenas inscrições do Magento.")
        dados_ativo = []

    if isinstance(dados_magento, dict) and 'error' in dados_magento:
        warnings.append(f"Erro no banco Magento: {dados_magento['error']}. Os dados exibidos contêm apenas inscrições do Ativo.")
        dados_magento = []

    if not dados_ativo and not dados_magento:
        warnings.append("Nenhuma fonte de dados retornou resultados. Verifique a conectividade com os bancos de dados.")

    if mappings and dados_ativo:
        import copy
        dados_ativo = copy.deepcopy(dados_ativo)
        dados_ativo = enrich_with_mappings(dados_ativo, mappings, "ativo", datetime.now().year)

    def _aggregate_isc_row(all_data: dict, sku: str, row: dict):
        if sku in all_data:
            all_data[sku]['qtd_site'] += row.get('qtd_site', 0)
            all_data[sku]['inscricao_liquida'] += row.get('inscricao_liquida', 0.0)
            all_data[sku]['media_30d'] += row.get('media_30d', 0.0)
            all_data[sku]['media_14d'] += row.get('media_14d', 0.0)
            all_data[sku]['media_7d'] += row.get('media_7d', 0.0)
        else:
            all_data[sku] = {
                'qtd_site': row.get('qtd_site', 0),
                'inscricao_liquida': row.get('inscricao_liquida', 0.0),
                'media_30d': row.get('media_30d', 0.0),
                'media_14d': row.get('media_14d', 0.0),
                'media_7d': row.get('media_7d', 0.0),
                'dias_ate_evento': row.get('dias_ate_evento', 0),
                'evento_name': row.get('evento', ''),
                'ticket_medio': 0.0,
                'fator_aceleracao': 0.0,
                'projecao_linear': 0.0,
                'projecao_ajustada': 0.0,
                'projecao_final': 0.0,
                'tendencia': 'Sem histórico comparativo',
                'receita_liquida_site': row.get('inscricao_liquida', 0.0),
            }

    for row in dados_ativo:
        sku = normalize_sku(row.get('sku', '') or '')
        if not sku:
            continue
        _aggregate_isc_row(all_data, sku, row)

    if mappings and dados_magento:
        import copy
        dados_magento = copy.deepcopy(dados_magento)
        dados_magento = enrich_with_mappings(dados_magento, mappings, "magento", datetime.now().year)

    for row in dados_magento:
        sku = normalize_sku(row.get('sku', '') or '')
        if not sku:
            continue
        _aggregate_isc_row(all_data, sku, row)

    for sku, data in all_data.items():
        qtd_site = data['qtd_site']
        dias = max(data['dias_ate_evento'], 0)
        media_14d = data['media_14d']
        media_7d = data['media_7d']

        qtd_7d = media_7d * 7.0
        qtd_7d_anterior = media_14d * 14.0 - qtd_7d

        data['ticket_medio'] = round(data['inscricao_liquida'] / qtd_site, 2) if qtd_site > 0 else 0.0

        data['receita_liquida_site'] = data['inscricao_liquida']

        if qtd_7d_anterior > 0:
            data['fator_aceleracao'] = round(qtd_7d / qtd_7d_anterior, 2)
        else:
            data['fator_aceleracao'] = 0.0

        data['projecao_linear'] = round(qtd_site + media_14d * dias, 0)

        fator = data['fator_aceleracao'] if data['fator_aceleracao'] > 0 else 1.0
        fator_clamped = min(max(fator, 0.3), 2.5)
        data['projecao_ajustada'] = round(qtd_site + media_14d * fator_clamped * dias, 0)

        data['projecao_final'] = data['projecao_linear']

        if qtd_7d_anterior <= 0:
            data['tendencia'] = 'Sem histórico comparativo'
        elif data['fator_aceleracao'] >= 1.15:
            data['tendencia'] = 'Acelerando'
        elif data['fator_aceleracao'] >= 0.85:
            data['tendencia'] = 'Estável'
        else:
            data['tendencia'] = 'Desacelerando'

    fontes = []
    if dados_ativo:
        fontes.append("Ativo")
    if dados_magento:
        fontes.append("Magento")
    if fontes and not warnings:
        logger.info(f"ISC/Pricing data consolidado: {len(all_data)} SKUs (fontes: {', '.join(fontes)})")

    _isc_cache = all_data
    _isc_cache_timestamp = current_time
    _isc_warnings = warnings
    
    _smart_isc_cache.set(smart_cache_key, all_data)

    return all_data


def get_isc_warnings() -> list:
    return _isc_warnings


_sales_cache = {}
_cache_timestamp = None

def fetch_consolidated_sales_by_skus(skus: List[str], ano: int, apenas_site: bool = False, db: Session = None) -> dict:
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


@router.get("/eventos", response_model=MarketingEventsResponse)
def get_marketing_events(
    ano: int = Query(default=None, description="Ano dos eventos"),
    status: Optional[str] = Query(None, description="Filtrar por status: active, closed, all"),
    categoria: Optional[str] = Query(None, description="Filtrar por categoria/modalidade"),
    busca: Optional[str] = Query(None, description="Buscar por nome do evento"),
    force_refresh: bool = Query(default=False, description="Forçar atualização dos dados ignorando cache"),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    """
    Retorna eventos para o Dashboard ISC com dados consolidados de vendas
    dos bancos Ativo e Magento.
    Agrupa projetos por EventoGrupo quando disponível.
    """
    if ano is None:
        ano = datetime.now().year
    
    cache_key = f"{ano}_{status or 'all'}_{categoria or 'all'}_{busca or ''}"
    if not force_refresh:
        cached = eventos_list_cache.get(cache_key)
        if cached is not None:
            return cached
    
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
    
    isc_data = fetch_isc_pricing_data(db=db, force_refresh=force_refresh)
    
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
    
    all_projetos_flat = []
    for proj_list in grupo_projetos.values():
        all_projetos_flat.extend(proj_list)
    all_projetos_flat.extend(standalone_projetos)
    sku_daily_prefetch = _prefetch_all_daily_sales(db, all_projetos_flat, ano)
    
    all_grupo_names_for_hist = set(grupo_projetos.keys())
    for projeto in standalone_projetos:
        sku_n = normalize_sku(str(projeto.codigo)) if projeto.codigo else None
        if sku_n:
            eg = sku_to_grupo.get(sku_n)
            if eg:
                all_grupo_names_for_hist.add(eg)
    hist_patterns_prefetch = _prefetch_all_historical_patterns(db, list(all_grupo_names_for_hist), ano)
    
    for grupo_nome, proj_list in grupo_projetos.items():
        grupo = grupo_details[grupo_nome]
        
        total_capacity = 0
        for p in proj_list:
            cad = cadastro_by_projeto_id.get(p.id)
            if cad:
                total_capacity += get_meta_from_cadastro(cad)
            else:
                total_capacity += get_meta_orcada(db, p.id)
        if total_capacity <= 0:
            total_capacity = 1000
        
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
        
        if status == 'active' and not is_active:
            continue
        if status == 'closed' and is_active:
            continue
        
        current_sales = 0
        current_receita = 0.0
        seen_grupo_norms = set()
        for p in proj_list:
            p_sku = normalize_sku(str(p.codigo)) if p.codigo else None
            if p_sku and p_sku not in seen_grupo_norms and p_sku in isc_data:
                seen_grupo_norms.add(p_sku)
                current_sales += isc_data[p_sku].get('qtd_site', 0)
                current_receita += isc_data[p_sku].get('receita_liquida_site', 0.0)
        
        sales_goal = total_capacity if total_capacity > 0 else 1000
        avg_ticket = round(current_receita / current_sales, 2) if current_sales > 0 else 0.0
        
        budget_ticket_total_receita = 0.0
        budget_ticket_total_qtd = 0
        for p in proj_list:
            cad_bt = cadastro_by_projeto_id.get(p.id)
            if cad_bt and cad_bt.atletas_site_tkt_medio and cad_bt.atletas_site_pago:
                budget_ticket_total_receita += float(cad_bt.atletas_site_tkt_medio) * int(cad_bt.atletas_site_pago)
                budget_ticket_total_qtd += int(cad_bt.atletas_site_pago)
        budget_ticket = round(budget_ticket_total_receita / budget_ticket_total_qtd, 2) if budget_ticket_total_qtd > 0 else 0.0
        
        grupo_daily_sales_dict = _build_grupo_daily_dict(sku_daily_prefetch, proj_list)
        
        from datetime import timedelta
        _yesterday = date.today() - timedelta(days=1)
        if grupo_daily_sales_dict and len(grupo_daily_sales_dict) > 0:
            current_sales = sum(v for k, v in grupo_daily_sales_dict.items() if k <= _yesterday)
            avg_ticket = round(current_receita / current_sales, 2) if current_sales > 0 else 0.0
        
        grupo_hist_pattern = hist_patterns_prefetch.get(grupo_nome)
        
        isc_components = calculate_isc_components(current_sales, sales_goal, d_minus_inscricoes,
                                                   daily_sales_dict=grupo_daily_sales_dict,
                                                   hist_pattern=grupo_hist_pattern)
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
        
        if status == 'active' and not is_active:
            continue
        if status == 'closed' and is_active:
            continue
        
        sku_norm = normalize_sku(sku)
        sales_info = isc_data.get(sku_norm, {})
        current_sales = sales_info.get('qtd_site', 0)
        current_receita = sales_info.get('receita_liquida_site', 0.0)
        
        sales_goal = get_meta_from_cadastro(cad) if cad else get_meta_orcada(db, projeto.id)
        avg_ticket = round(current_receita / current_sales, 2) if current_sales > 0 else 0.0
        standalone_budget_ticket = round(float(cad.atletas_site_tkt_medio), 2) if cad and cad.atletas_site_tkt_medio and cad.atletas_site_pago and cad.atletas_site_pago > 0 else 0.0
        
        standalone_eg = sku_to_grupo.get(normalize_sku(sku))
        
        standalone_daily_dict = _build_grupo_daily_dict(sku_daily_prefetch, [projeto])
        
        if standalone_daily_dict and len(standalone_daily_dict) > 0:
            current_sales = sum(v for k, v in standalone_daily_dict.items() if k <= _yesterday)
            avg_ticket = round(current_receita / current_sales, 2) if current_sales > 0 else 0.0
        
        standalone_hist = hist_patterns_prefetch.get(standalone_eg) if standalone_eg else None
        
        isc_components = calculate_isc_components(current_sales, sales_goal, d_minus_inscricoes,
                                                   daily_sales_dict=standalone_daily_dict,
                                                   hist_pattern=standalone_hist)
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
    
    result = MarketingEventsResponse(
        status="success",
        eventos=eventos,
        resumo=resumo,
        categorias=sorted(list(categorias_set)),
        ultima_atualizacao=datetime.now(ZoneInfo('America/Sao_Paulo')).isoformat(),
        avisos=get_isc_warnings()
    )
    eventos_list_cache.set(cache_key, result.model_dump(mode="json"))
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
    current_user: Usuario = Depends(get_current_user)
):
    from datetime import timedelta
    
    today = date.today()
    if ano is None:
        ano = today.year
    
    medias_cache_key = f"{ano}_{evento_id}_{periodo}_medias"
    if not force_refresh:
        cached_medias = medias_cache.get(medias_cache_key)
        if cached_medias is not None:
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
        magento_rows = _fetch_daily_sales_magento_by_ids(list(set(magento_ids)))
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


@router.get("/eventos/{evento_id}/simulacao")
def get_event_simulation(
    evento_id: str,
    ano: int = Query(default=None, description="Ano do evento"),
    force_refresh: bool = Query(default=False, description="Forçar atualização"),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    from datetime import timedelta
    today = date.today()
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
    dias_ate_evento = (data_evento - today).days if data_evento else 0

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

    all_raw_sales = {}
    all_raw_receita = {}

    if ativo_ids:
        ativo_rows = _fetch_daily_sales_ativo_by_ids(list(set(ativo_ids)))
        for row in ativo_rows:
            d = date.fromisoformat(row['dia']) if isinstance(row['dia'], str) else row['dia']
            all_raw_sales[d] = all_raw_sales.get(d, 0) + row['qtd']
            all_raw_receita[d] = all_raw_receita.get(d, 0) + row.get('receita', 0)

    if magento_ids:
        magento_rows = _fetch_daily_sales_magento_by_ids(list(set(magento_ids)))
        for row in magento_rows:
            d = date.fromisoformat(row['dia']) if isinstance(row['dia'], str) else row['dia']
            all_raw_sales[d] = all_raw_sales.get(d, 0) + row['qtd']
            all_raw_receita[d] = all_raw_receita.get(d, 0) + row.get('receita', 0)

    total_vendas = sum(all_raw_sales.values())
    total_receita = round(sum(all_raw_receita.values()), 2)
    ticket_medio_atual = round(total_receita / total_vendas, 2) if total_vendas > 0 else 0.0

    sorted_dates = sorted(all_raw_sales.keys())

    media_7d = 0.0
    media_14d = 0.0
    media_30d = 0.0
    if sorted_dates:
        for window, attr_name in [(7, 'media_7d'), (14, 'media_14d'), (30, 'media_30d')]:
            cutoff = today - timedelta(days=window)
            sales_in = sum(v for d, v in all_raw_sales.items() if d > cutoff and d <= today)
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

    return {
        "status": "success",
        "evento": {
            "data_evento": data_evento.isoformat() if data_evento else None,
            "dias_ate_evento": dias_ate_evento,
            "meta_orcada": meta_orcada,
            "ticket_medio_orcado": ticket_medio_orcado,
            "receita_orcada": receita_orcada,
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
    COUNT(CASE WHEN (f.en_cupom_classificacao IS NULL OR NOT f.en_cupom_classificacao)
        AND (h.ds_categoria IS NULL OR h.ds_categoria NOT LIKE '%%Grup%%')
        AND c.nr_total > 0 THEN 1 END) AS qtd,
    SUM(CASE WHEN (f.en_cupom_classificacao IS NULL OR NOT f.en_cupom_classificacao)
        AND (h.ds_categoria IS NULL OR h.ds_categoria NOT LIKE '%%Grup%%')
        AND c.nr_total > 0 THEN 
        GREATEST(a.nr_preco - COALESCE(a.nr_desconto_individual, 0) - COALESCE(h.vl_kit, 0), 0)
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
    AND b.id_campanha_salesforce NOT LIKE '701d0000000%%'
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
    COUNT(CASE WHEN (so.discount_description IS NULL OR so.discount_description NOT LIKE '%%Grup%%') 
        AND so.base_grand_total > 0 THEN 1 END) AS qtd,
    SUM(CASE WHEN (so.discount_description IS NULL OR so.discount_description NOT LIKE '%%Grup%%') THEN
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
LEFT JOIN webpos_location AS wl ON so.location_pickup_id = wl.location_id
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
    COUNT(CASE WHEN (f.en_cupom_classificacao IS NULL OR NOT f.en_cupom_classificacao)
        AND (h.ds_categoria IS NULL OR h.ds_categoria NOT LIKE '%%Grup%%')
        AND c.nr_total > 0 THEN 1 END) AS qtd,
    SUM(CASE WHEN (f.en_cupom_classificacao IS NULL OR NOT f.en_cupom_classificacao)
        AND (h.ds_categoria IS NULL OR h.ds_categoria NOT LIKE '%%Grup%%')
        AND c.nr_total > 0 THEN 
        GREATEST(a.nr_preco - COALESCE(a.nr_desconto_individual, 0) - COALESCE(h.vl_kit, 0), 0)
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
    AND b.id_campanha_salesforce NOT LIKE '701d0000000%%'
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


def _fetch_monthly_sales_magento_by_ids(location_ids: list) -> list:
    if db_module.engine_magento is None or not location_ids:
        return []
    try:
        safe_ids = [int(i) for i in location_ids if str(i).isdigit()]
        if not safe_ids:
            return []
        query = text("""
SELECT
    MONTH(so.created_at) AS mes,
    COUNT(CASE WHEN (so.discount_description IS NULL OR so.discount_description NOT LIKE '%%Grup%%') 
        AND so.base_grand_total > 0 THEN 1 END) AS qtd,
    SUM(CASE WHEN (so.discount_description IS NULL OR so.discount_description NOT LIKE '%%Grup%%') THEN
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
    so.increment_id NOT REGEXP '-[0-9]+$'
    AND so.status IN ('Processing', 'Complete', 'approved')
    AND soi.product_type = 'Bundle'
    AND so.location_pickup_id IN :location_ids
GROUP BY MONTH(so.created_at)
ORDER BY mes
""").bindparams(bindparam("location_ids", expanding=True))
        with db_module.engine_magento.connect() as conn:
            result = conn.execute(query, {"location_ids": safe_ids})
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
    b.id_evento,
    DATE(c.dt_pedido) AS dia,
    COUNT(CASE WHEN (f.en_cupom_classificacao IS NULL OR NOT f.en_cupom_classificacao)
        AND (h.ds_categoria IS NULL OR h.ds_categoria NOT LIKE '%%Grup%%')
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
    AND b.id_campanha_salesforce NOT LIKE '701d0000000%%'
    AND b.id_evento IN :id_eventos
    AND c.dt_pedido < CURDATE()
GROUP BY b.id_evento, DATE(c.dt_pedido)
ORDER BY b.id_evento, dia
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


def _fetch_daily_sales_magento_by_ids_grouped(location_ids: list) -> dict:
    if not location_ids:
        return {}
    if _is_warmup_thread():
        with _warmup_daily_cache_lock:
            magento_cache = _warmup_daily_cache.get("magento")
        if magento_cache is not None:
            safe_ids = [str(int(i)) for i in location_ids if str(i).isdigit()]
            result = {}
            for lid in safe_ids:
                if lid in magento_cache:
                    result[lid] = dict(magento_cache[lid])
            if result:
                return result
    if db_module.engine_magento is None:
        return {}
    try:
        safe_ids = [int(i) for i in location_ids if str(i).isdigit()]
        if not safe_ids:
            return {}
        query = text("""
SELECT /*+ MAX_EXECUTION_TIME(90000) */
    cpev1.value AS location_id,
    DATE(so.created_at) AS dia,
    COUNT(CASE WHEN (so.discount_description IS NULL OR so.discount_description NOT LIKE '%%Grup%%') 
        AND so.base_grand_total > 0 THEN 1 END) AS qtd
FROM sales_order so
LEFT JOIN sales_order_item soi
       ON soi.order_id = so.entity_id
      AND soi.product_type = 'bundle'
LEFT JOIN catalog_product_entity_varchar cpev1
       ON cpev1.entity_id = soi.product_id
      AND cpev1.attribute_id = 321
WHERE
    so.status IN ('processing', 'complete', 'approved', 'aprovado_link', 'reembolso_parcial')
    AND cpev1.value IN :location_ids
    AND so.increment_id NOT REGEXP '-[0-9]+$'
    AND so.created_at < CURDATE()
GROUP BY cpev1.value, DATE(so.created_at)
ORDER BY cpev1.value, dia
""").bindparams(bindparam("location_ids", expanding=True))
        with db_module.engine_magento.connect() as conn:
            result = conn.execute(query, {"location_ids": safe_ids})
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


def _prefetch_all_daily_sales(db: Session, all_projetos: list, ano: int) -> dict:
    cache_key = f"{ano}_prefetch_daily"
    cached = daily_sales_cache.get(cache_key)
    if cached is not None:
        return cached
    
    from ...models.dimensoes import SkuMapping
    
    all_skus = []
    sku_to_projetos = {}
    for p in all_projetos:
        if hasattr(p, 'codigo') and p.codigo:
            sku = str(p.codigo).upper().strip()
            all_skus.append(sku)
            if sku not in sku_to_projetos:
                sku_to_projetos[sku] = []
            sku_to_projetos[sku].append(p)
    
    if not all_skus:
        return {}
    
    all_active_mappings = db.query(SkuMapping).filter(
        SkuMapping.sku.in_(list(set(all_skus))),
        SkuMapping.ativo == True
    ).all()
    
    year_mappings = [m for m in all_active_mappings if m.ano == ano]
    if not year_mappings and all_active_mappings:
        available_years = sorted(set(m.ano for m in all_active_mappings if m.ano), reverse=True)
        if available_years:
            year_mappings = [m for m in all_active_mappings if m.ano == available_years[0]]
    
    ativo_ids = []
    magento_ids = []
    id_to_sku = {}
    
    for m in year_mappings:
        if m.id_externo:
            ext_id = str(m.id_externo)
            sku = m.sku.upper().strip()
            if m.fonte == 'ATIVO':
                ativo_ids.append(ext_id)
                if ext_id not in id_to_sku:
                    id_to_sku[ext_id] = set()
                id_to_sku[ext_id].add(sku)
            elif m.fonte == 'MAGENTO':
                magento_ids.append(ext_id)
                if ext_id not in id_to_sku:
                    id_to_sku[ext_id] = set()
                id_to_sku[ext_id].add(sku)
    
    sku_daily = {}
    
    if ativo_ids:
        ativo_grouped = _fetch_daily_sales_ativo_by_ids_grouped(list(set(ativo_ids)))
        for ext_id, daily in ativo_grouped.items():
            for sku in id_to_sku.get(ext_id, []):
                if sku not in sku_daily:
                    sku_daily[sku] = {}
                for d, qtd in daily.items():
                    sku_daily[sku][d] = sku_daily[sku].get(d, 0) + qtd
    
    if magento_ids:
        magento_grouped = _fetch_daily_sales_magento_by_ids_grouped(list(set(magento_ids)))
        for ext_id, daily in magento_grouped.items():
            for sku in id_to_sku.get(ext_id, []):
                if sku not in sku_daily:
                    sku_daily[sku] = {}
                for d, qtd in daily.items():
                    sku_daily[sku][d] = sku_daily[sku].get(d, 0) + qtd
    
    daily_sales_cache.set(cache_key, sku_daily)
    
    return sku_daily


def _build_grupo_daily_dict(sku_daily: dict, proj_list: list) -> dict:
    combined = {}
    seen = set()
    for p in proj_list:
        if hasattr(p, 'codigo') and p.codigo:
            sku = str(p.codigo).upper().strip()
            if sku in seen:
                continue
            seen.add(sku)
            for d, qtd in sku_daily.get(sku, {}).items():
                d_key = date.fromisoformat(d) if isinstance(d, str) else d
                combined[d_key] = combined.get(d_key, 0) + qtd
    return combined


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
    DATE(c.dt_pedido) AS dia,
    COUNT(CASE WHEN (f.en_cupom_classificacao IS NULL OR NOT f.en_cupom_classificacao)
        AND (h.ds_categoria IS NULL OR h.ds_categoria NOT LIKE '%%Grup%%')
        AND c.nr_total > 0 THEN 1 END) AS qtd,
    SUM(CASE WHEN (f.en_cupom_classificacao IS NULL OR NOT f.en_cupom_classificacao)
        AND (h.ds_categoria IS NULL OR h.ds_categoria NOT LIKE '%%Grup%%')
        AND c.nr_total > 0 THEN 
        GREATEST(a.nr_preco - COALESCE(a.nr_desconto_individual, 0) - COALESCE(h.vl_kit, 0), 0)
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
    AND b.id_campanha_salesforce NOT LIKE '701d0000000%%'
    AND b.id_evento IN :id_eventos
    AND c.dt_pedido < CURDATE()
GROUP BY DATE(c.dt_pedido)
ORDER BY dia
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
    DATE(c.dt_pedido) AS dia,
    COUNT(CASE WHEN (f.en_cupom_classificacao IS NULL OR NOT f.en_cupom_classificacao)
        AND (h.ds_categoria IS NULL OR h.ds_categoria NOT LIKE '%%Grup%%')
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
    AND b.id_campanha_salesforce NOT LIKE '701d0000000%%'
    AND b.id_evento IN :id_eventos
    AND DATE(c.dt_pedido) = CURDATE()
GROUP BY DATE(c.dt_pedido)
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


def _fetch_today_sales_magento_by_ids(location_ids: list) -> dict:
    if not location_ids or db_module.engine_magento is None:
        return {}
    try:
        safe_ids = [str(int(i)) for i in location_ids if str(i).isdigit()]
        if not safe_ids:
            return {}
        query = text("""
SELECT /*+ MAX_EXECUTION_TIME(30000) */
    DATE(so.created_at) AS dia,
    COUNT(CASE WHEN (so.discount_description IS NULL OR so.discount_description NOT LIKE '%%Grup%%') 
        AND so.base_grand_total > 0 THEN 1 END) AS qtd
FROM sales_order so
LEFT JOIN sales_order_item soi
       ON soi.order_id = so.entity_id
      AND soi.product_type = 'bundle'
LEFT JOIN catalog_product_entity_varchar cpev1
       ON cpev1.entity_id = soi.product_id
      AND cpev1.attribute_id = 321
WHERE
    so.status IN ('processing', 'complete', 'approved', 'aprovado_link', 'reembolso_parcial')
    AND cpev1.value IN :location_ids
    AND so.increment_id NOT REGEXP '-[0-9]+$'
    AND DATE(so.created_at) = CURDATE()
GROUP BY DATE(so.created_at)
""").bindparams(bindparam("location_ids", expanding=True))
        with db_module.engine_magento.connect() as conn:
            result = conn.execute(query, {"location_ids": safe_ids})
            rows = result.fetchall()
            daily = {}
            for r in rows:
                d = date.fromisoformat(str(r[0])) if isinstance(r[0], str) else r[0]
                daily[d] = daily.get(d, 0) + int(r[1] or 0)
            return daily
    except Exception as e:
        logger.error(f"Erro today sales Magento by IDs: {e}")
        return {}


def _fetch_daily_sales_magento_by_ids(location_ids: list) -> list:
    if not location_ids:
        return []
    if _is_warmup_thread():
        with _warmup_daily_cache_lock:
            magento_cache = _warmup_daily_cache.get("magento")
        if magento_cache is not None:
            safe_ids = [str(int(i)) for i in location_ids if str(i).isdigit()]
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
        safe_ids = [str(int(i)) for i in location_ids if str(i).isdigit()]
        if not safe_ids:
            return []
        query = text("""
SELECT /*+ MAX_EXECUTION_TIME(90000) */
    DATE(so.created_at) AS dia,
    COUNT(CASE WHEN (so.discount_description IS NULL OR so.discount_description NOT LIKE '%%Grup%%') 
        AND so.base_grand_total > 0 THEN 1 END) AS qtd,
    SUM(CASE WHEN (so.discount_description IS NULL OR so.discount_description NOT LIKE '%%Grup%%') THEN
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
LEFT JOIN sales_order_item soi
       ON soi.order_id = so.entity_id
      AND soi.product_type = 'bundle'
LEFT JOIN catalog_product_entity_varchar cpev1
       ON cpev1.entity_id = soi.product_id
      AND cpev1.attribute_id = 321
LEFT JOIN customer_group cg
       ON cg.customer_group_id = so.customer_group_id
LEFT JOIN (
    SELECT * FROM sales_order_item WHERE name LIKE '%%persona%%'
) AS soiaa ON soiaa.parent_item_id = soi.item_id
WHERE
    so.status IN ('processing', 'complete', 'approved', 'aprovado_link', 'reembolso_parcial')
    AND cpev1.value IN :location_ids
    AND so.increment_id NOT REGEXP '-[0-9]+$'
    AND so.created_at < CURDATE()
GROUP BY DATE(so.created_at)
ORDER BY dia
""").bindparams(bindparam("location_ids", expanding=True))
        with db_module.engine_magento.connect() as conn:
            result = conn.execute(query, {"location_ids": safe_ids})
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
    COUNT(CASE WHEN (f.en_cupom_classificacao IS NULL OR NOT f.en_cupom_classificacao)
        AND (h.ds_categoria IS NULL OR h.ds_categoria NOT LIKE '%%Grup%%')
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
    AND b.id_campanha_salesforce NOT LIKE '701d0000000%%'
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
    COUNT(CASE WHEN (f.en_cupom_classificacao IS NULL OR NOT f.en_cupom_classificacao)
        AND (h.ds_categoria IS NULL OR h.ds_categoria NOT LIKE '%%Grup%%')
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
    AND b.id_campanha_salesforce NOT LIKE '701d0000000%%'
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


def _fetch_category_sales_magento_by_ids_grouped(location_ids: list) -> dict:
    if db_module.engine_magento is None or not location_ids:
        return {}
    try:
        safe_ids = [int(i) for i in location_ids if str(i).isdigit()]
        if not safe_ids:
            return {}
        query = text("""
SELECT
    cpev1.value AS location_id,
    soi.name AS categoria,
    COUNT(CASE WHEN (so.discount_description IS NULL OR so.discount_description NOT LIKE '%%Grup%%') 
        AND so.base_grand_total > 0 THEN 1 END) AS qtd
FROM sales_order AS so
LEFT JOIN sales_order_item AS soi ON soi.order_id = so.entity_id AND soi.product_type = 'bundle'
LEFT JOIN catalog_product_entity_varchar cpev1 ON cpev1.entity_id = soi.product_id AND cpev1.attribute_id = 321
LEFT JOIN customer_group AS cg ON cg.customer_group_id = so.customer_group_id
WHERE
    so.increment_id NOT REGEXP '-[0-9]+$'
    AND so.status IN ('processing', 'complete', 'approved', 'aprovado_link', 'reembolso_parcial')
    AND cpev1.value IN :location_ids
GROUP BY cpev1.value, soi.name
ORDER BY cpev1.value, qtd DESC
""").bindparams(bindparam("location_ids", expanding=True))
        with db_module.engine_magento.connect() as conn:
            result = conn.execute(query, {"location_ids": safe_ids})
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


def _fetch_category_sales_magento_by_ids(location_ids: list) -> list:
    if not location_ids:
        return []
    if _is_warmup_thread():
        with _warmup_daily_cache_lock:
            cat_cache = _warmup_daily_cache.get("cat_magento")
        if cat_cache is not None:
            safe_ids = [str(int(i)) for i in location_ids if str(i).isdigit()]
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
        safe_ids = [int(i) for i in location_ids if str(i).isdigit()]
        if not safe_ids:
            return []
        query = text("""
SELECT
    soi.name AS categoria,
    COUNT(CASE WHEN (so.discount_description IS NULL OR so.discount_description NOT LIKE '%%Grup%%') 
        AND so.base_grand_total > 0 THEN 1 END) AS qtd
FROM sales_order AS so
LEFT JOIN sales_order_item AS soi ON soi.order_id = so.entity_id
LEFT JOIN customer_group AS cg ON cg.customer_group_id = so.customer_group_id
WHERE
    so.increment_id NOT LIKE "%%-1%%"
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
    AND so.location_pickup_id IN :location_ids
GROUP BY soi.name
ORDER BY qtd DESC
""").bindparams(bindparam("location_ids", expanding=True))
        with db_module.engine_magento.connect() as conn:
            result = conn.execute(query, {"location_ids": safe_ids})
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

def _prefetch_all_historical_patterns(db: Session, grupo_names: list, ano: int) -> dict:
    from ...models.dimensoes import SkuMapping
    prev_ano = ano - 1
    if not grupo_names:
        return {}

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
            magento_grouped = _fetch_daily_sales_magento_by_ids_grouped(list(set(all_prev_magento_ids)))
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

    return result


def _find_data_evento(db: Session, evento_grupo: str, ano: int) -> Optional[date]:
    from ...models.dimensoes import SkuMapping
    ano_corrente = date.today().year
    if ano < ano_corrente:
        mapping_with_date = db.query(SkuMapping).filter(
            SkuMapping.evento_grupo == evento_grupo,
            SkuMapping.ano == ano,
            SkuMapping.data_evento != None,
            SkuMapping.ativo == True
        ).first()
        if mapping_with_date:
            logger.info(f"Found data_evento in sku_mappings for '{evento_grupo}' ano={ano} (ano anterior): {mapping_with_date.data_evento}")
            return mapping_with_date.data_evento
    else:
        logger.debug(f"Skipping sku_mappings.data_evento for '{evento_grupo}' ano={ano} (ano corrente={ano_corrente}), usando dim_projeto/cadastro")

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
            logger.info(f"Estimated data_evento for '{evento_grupo}' ano={ano} from year {adj_best_match.data_evento.year} event '{adj_best_match.evento}': {adjusted_date}")
            return adjusted_date
        except ValueError:
            month = adj_best_match.data_evento.month
            day = 28 if adj_best_match.data_evento.month == 2 else adj_best_match.data_evento.day
            adjusted_date = date(ano, month, day)
            logger.info(f"Estimated data_evento for '{evento_grupo}' ano={ano} (adjusted for leap year): {adjusted_date}")
            return adjusted_date

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
    current_user: Usuario = Depends(get_current_user)
):
    import time

    cache_key = f"{evento_id}_{ano}"
    current_time = time.time()
    
    smart_curva_key = f"{ano}_{evento_id}_curva"
    if not force_refresh:
        cached_curva = curva_cache.get(smart_curva_key)
        if cached_curva is not None:
            return cached_curva

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

    is_warmup = _is_warmup_thread()
    if is_warmup:
        try:
            dados_ativo_atual = _fetch_daily_sales_ativo_by_ids(ids_ativo_atual)
        except Exception as e:
            logger.error(f"Curva comparativa daily Ativo atual error: {e}")
            dados_ativo_atual = []
        try:
            dados_magento_atual = _fetch_daily_sales_magento_by_ids(ids_magento_atual)
        except Exception as e:
            logger.error(f"Curva comparativa daily Magento atual error: {e}")
            dados_magento_atual = []
        try:
            dados_ativo_anterior = _fetch_daily_sales_ativo_by_ids(ids_ativo_anterior)
        except Exception as e:
            logger.error(f"Curva comparativa daily Ativo anterior error: {e}")
            dados_ativo_anterior = []
        try:
            dados_magento_anterior = _fetch_daily_sales_magento_by_ids(ids_magento_anterior)
        except Exception as e:
            logger.error(f"Curva comparativa daily Magento anterior error: {e}")
            dados_magento_anterior = []
    else:
        future_ativo_atual = _rolling_avg_executor.submit(_fetch_daily_sales_ativo_by_ids, ids_ativo_atual)
        future_magento_atual = _rolling_avg_executor.submit(_fetch_daily_sales_magento_by_ids, ids_magento_atual)
        future_ativo_anterior = _rolling_avg_executor.submit(_fetch_daily_sales_ativo_by_ids, ids_ativo_anterior)
        future_magento_anterior = _rolling_avg_executor.submit(_fetch_daily_sales_magento_by_ids, ids_magento_anterior)

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

    hoje = date.today()
    dias_ate_evento_atual = (data_evento_atual - hoje).days if data_evento_atual else 0
    d_minus_bucket_atual = _bucket_key_for(dias_ate_evento_atual) if dias_ate_evento_atual > 0 else 0

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
    current_user: Usuario = Depends(get_current_user)
):
    smart_insights_key = f"{ano}_{evento_id}_insights"
    if not force_refresh:
        cached = curva_cache.get(smart_insights_key)
        if cached is not None:
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

    is_warmup = _is_warmup_thread()
    if is_warmup:
        try:
            dados_ativo_atual = _fetch_daily_sales_ativo_by_ids(ids_ativo_atual)
        except Exception as e:
            logger.error(f"Insights daily Ativo atual error: {e}")
            dados_ativo_atual = []
        try:
            dados_magento_atual = _fetch_daily_sales_magento_by_ids(ids_magento_atual)
        except Exception as e:
            logger.error(f"Insights daily Magento atual error: {e}")
            dados_magento_atual = []
        try:
            dados_ativo_anterior = _fetch_daily_sales_ativo_by_ids(ids_ativo_anterior)
        except Exception as e:
            logger.error(f"Insights daily Ativo anterior error: {e}")
            dados_ativo_anterior = []
        try:
            dados_magento_anterior = _fetch_daily_sales_magento_by_ids(ids_magento_anterior)
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
        future_magento_atual = _rolling_avg_executor.submit(_fetch_daily_sales_magento_by_ids, ids_magento_atual)
        future_ativo_anterior = _rolling_avg_executor.submit(_fetch_daily_sales_ativo_by_ids, ids_ativo_anterior)
        future_magento_anterior = _rolling_avg_executor.submit(_fetch_daily_sales_magento_by_ids, ids_magento_anterior)
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
        min_dias = 0
    else:
        max_dias = max(all_dias)
        min_dias = min(d for d in all_dias if d >= 0) if any(d >= 0 for d in all_dias) else 0

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

    hoje = date.today()
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


@router.get("/eventos/{evento_id}")
def get_marketing_event_by_id(
    evento_id: str,
    ano: int = Query(default=None, description="Ano para evento consolidado"),
    force_refresh: bool = Query(default=False, description="Forçar atualização dos dados ignorando cache"),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    """
    Retorna os dados de um evento específico pelo ID.
    Suporta IDs de EventoGrupo (prefixo 'grp_') e DimProjeto (número puro).
    """
    isc_cfg = _get_isc_settings(db)
    is_grouped = evento_id.startswith("grp_")
    
    if is_grouped:
        grupo_nome = evento_id.replace("grp_", "")
        grupo = db.query(EventoGrupoModel).filter(EventoGrupoModel.nome == grupo_nome).first()
        if not grupo:
            raise HTTPException(status_code=404, detail="Grupo de evento não encontrado")
        
        if ano is None:
            ano = datetime.now().year
        
        detail_cache_key = f"{ano}_{evento_id}_detail"
        if not force_refresh:
            cached_detail = event_detail_cache.get(detail_cache_key)
            if cached_detail is not None:
                return cached_detail
        
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
        
        detail_hist_pattern = None
        try:
            detail_hist_pattern = _fetch_previous_year_cumulative_pattern(db, grupo_nome, ano)
        except Exception:
            pass
        
        daily_sales_list = fetch_real_daily_sales_for_projetos(db, projetos, sales_goal=sales_goal, ano=ano, evento_grupo=grupo_nome, data_evento=data_fim_inscricoes, preloaded_hist_pattern=detail_hist_pattern)
        daily_sales_dict = {date.fromisoformat(d['date']): d['sales'] for d in daily_sales_list}
        
        _yesterday_detail = date.today() - timedelta(days=1)
        current_sales = 0
        if daily_sales_dict and len(daily_sales_dict) > 0:
            current_sales = sum(v for k, v in daily_sales_dict.items() if k <= _yesterday_detail)
        
        current_year = datetime.now().year
        if ano == current_year:
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
            seen_media_norms = set()
            for s_sku in skus:
                s_norm = normalize_sku(s_sku)
                if s_norm in seen_media_norms:
                    continue
                seen_media_norms.add(s_norm)
                info = isc_data.get(s_norm, {})
                grupo_media_14d += info.get('media_14d', 0.0)
                grupo_media_7d += info.get('media_7d', 0.0)
                grupo_media_30d += info.get('media_30d', 0.0)
        else:
            ativo_ids = [str(m.id_externo) for m in mappings if m.fonte == 'ATIVO' and m.id_externo]
            magento_ids = [str(m.id_externo) for m in mappings if m.fonte == 'MAGENTO' and m.id_externo]
            
            current_receita = 0.0
            
            if ativo_ids:
                ativo_rows = _fetch_daily_sales_ativo_by_ids(list(set(ativo_ids)))
                for row in ativo_rows:
                    current_receita += row.get('receita', 0.0)
            
            if magento_ids:
                magento_rows = _fetch_daily_sales_magento_by_ids(list(set(magento_ids)))
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
        
        isc_components = calculate_isc_components(current_sales, sales_goal, d_minus_inscricoes,
                                                   daily_sales_dict=daily_sales_dict,
                                                   hist_pattern=detail_hist_pattern)
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
                    "status_impacto": impacto.get("status", "calculado") if impacto_percentual is not None else "aguardando_dados"
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
                    for row in _fetch_daily_sales_magento_by_ids(list(set(ant_magento_ids))):
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
        
        grouped_result = {
            "status": "success",
            "evento": evento,
            "dailySales": daily_sales,
            "commercialActions": commercial_actions,
            "projetos_vinculados": [{"id": p.id, "nome": p.evento, "sku": p.codigo} for p in projetos],
            "comparacao_anual": comparacao_anual,
            "anos_disponiveis": [a[0] for a in anos_disponiveis],
            "ultima_atualizacao": datetime.now(ZoneInfo('America/Sao_Paulo')).isoformat(),
            "avisos": get_isc_warnings()
        }
        event_detail_cache.set(detail_cache_key, grouped_result)
        return grouped_result
    
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
    
    standalone_cache_key = f"{ano}_{evento_id}_detail"
    if not force_refresh:
        cached_standalone = event_detail_cache.get(standalone_cache_key)
        if cached_standalone is not None:
            return cached_standalone
    
    isc_data = fetch_isc_pricing_data(db=db)
    
    sales_info = isc_data.get(normalize_sku(sku), {}) if sku else {}
    current_sales = sales_info.get('qtd_site', 0)
    current_receita = sales_info.get('receita_liquida_site', 0.0)
    
    sales_goal = get_meta_orcada(db, projeto.id)
    avg_ticket = round(current_receita / current_sales, 2) if current_sales > 0 else 0.0
    detail_standalone_bt = round(float(detail_standalone_cad.atletas_site_tkt_medio), 2) if detail_standalone_cad and detail_standalone_cad.atletas_site_tkt_medio and detail_standalone_cad.atletas_site_pago and detail_standalone_cad.atletas_site_pago > 0 else 0.0
    
    standalone_evento_grupo = None
    if sku:
        standalone_mappings = _wq_sku_mappings_by_sku(db, sku)
        for sm in standalone_mappings:
            if sm.evento_grupo and sm.evento_grupo.strip():
                standalone_evento_grupo = sm.evento_grupo
                break

    data_fim_inscricoes_standalone = projeto_data_evento - timedelta(days=dias_enc) if projeto_data_evento else None
    daily_sales_list = fetch_real_daily_sales_for_projetos(db, [projeto], sales_goal=sales_goal, ano=ano, evento_grupo=standalone_evento_grupo, data_evento=data_fim_inscricoes_standalone)
    daily_sales_dict = {date.fromisoformat(d['date']): d['sales'] for d in daily_sales_list}
    
    standalone_media_14d = sales_info.get('media_14d', 0.0)
    
    standalone_detail_hist = None
    if standalone_evento_grupo:
        try:
            standalone_detail_hist = _fetch_previous_year_cumulative_pattern(db, standalone_evento_grupo, ano)
        except Exception:
            pass
    
    isc_components = calculate_isc_components(current_sales, sales_goal, d_minus_inscricoes,
                                               daily_sales_dict=daily_sales_dict,
                                               hist_pattern=standalone_detail_hist)
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
            "status_impacto": impacto.get("status", "calculado") if impacto_percentual is not None else "aguardando_dados"
        })
    
    standalone_result = {
        "status": "success",
        "evento": evento,
        "dailySales": daily_sales,
        "commercialActions": commercial_actions,
        "ultima_atualizacao": datetime.now(ZoneInfo('America/Sao_Paulo')).isoformat(),
        "avisos": get_isc_warnings()
    }
    event_detail_cache.set(standalone_cache_key, standalone_result)
    return standalone_result


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


@router.post("/cache/refresh-all")
def refresh_all_caches(
    current_user: Usuario = Depends(get_current_user)
):
    from app.core.cache import is_full_refresh_in_progress, trigger_full_warmup_async

    if is_full_refresh_in_progress():
        return {
            "status": "in_progress",
            "message": "Uma atualização completa já está em andamento. Aguarde.",
            "ultima_atualizacao": datetime.now(ZoneInfo('America/Sao_Paulo')).isoformat()
        }

    started = trigger_full_warmup_async()
    if not started:
        return {
            "status": "error",
            "message": "Não foi possível iniciar a atualização."
        }

    return {
        "status": "started",
        "message": "Atualização completa de todos os caches iniciada em background. Os dados serão atualizados em alguns minutos.",
        "ultima_atualizacao": datetime.now(ZoneInfo('America/Sao_Paulo')).isoformat()
    }


@router.get("/cache/status")
def get_cache_status(
    current_user: Usuario = Depends(get_current_user)
):
    from app.core.cache import get_last_full_refresh, is_full_refresh_in_progress, get_warmup_progress, get_last_refresh_error

    current_year = datetime.now().year
    last_refresh = get_last_full_refresh()
    last_refresh_str = None
    if last_refresh:
        last_refresh_str = datetime.fromtimestamp(last_refresh, tz=ZoneInfo('America/Sao_Paulo')).isoformat()

    in_progress = is_full_refresh_in_progress()
    progress = get_warmup_progress() if in_progress else None
    last_error = get_last_refresh_error()

    return {
        "status": "success",
        "refresh_in_progress": in_progress,
        "progress": progress,
        "last_error": last_error,
        "ultima_atualizacao_completa": last_refresh_str,
        "caches": {
            "isc_pricing": _smart_isc_cache.get_info(f"{current_year}_isc"),
            "event_detail": {
                "entries": event_detail_cache.entry_count(),
                "historical": sum(1 for k in event_detail_cache.get_all_keys() if event_detail_cache._is_historical(k)),
                "current_year": sum(1 for k in event_detail_cache.get_all_keys() if not event_detail_cache._is_historical(k))
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
            "daily_refresh_time": "07:00 BRT"
        }
    }


class AcaoComercialCreate(BaseModel):
    projeto_id: int
    tipo: str
    descricao: str
    data_acao: date

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
    """Cria uma nova ação comercial com validação de duplicidade (7 dias)"""
    from ...models.dimensoes import AcaoComercial
    
    projeto = db.query(DimProjeto).filter(DimProjeto.id == acao.projeto_id).first()
    if not projeto:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")
    
    duplicate = check_duplicate_action(db, acao.projeto_id, acao.tipo)
    if duplicate:
        tipo_labels = {
            'PROMOCAO': 'Promoção',
            'AUMENTO_PRECO': 'Aumento de Preço',
            'REDUCAO_PRECO': 'Redução de Preço',
            'CAMPANHA': 'Campanha',
            'COMUNICACAO': 'Comunicação'
        }
        tipo_label = tipo_labels.get(acao.tipo, acao.tipo)
        raise HTTPException(
            status_code=409,
            detail={
                "message": f"Já existe uma ação de '{tipo_label}' ativa para este evento. "
                           f"A ação '{duplicate['descricao']}' foi criada em {duplicate['data_acao']} "
                           f"e ainda está ativa por mais {duplicate['dias_restantes']} dia(s).",
                "existing_action": duplicate
            }
        )
    
    nova_acao = AcaoComercial(
        projeto_id=acao.projeto_id,
        tipo=acao.tipo,
        descricao=acao.descricao,
        data_acao=acao.data_acao
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
            "data_acao": nova_acao.data_acao.isoformat() if nova_acao.data_acao else None
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


_rolling_avg_cache = {}
_rolling_avg_cache_timestamp = None

def fetch_rolling_avg_ativo() -> dict:
    if db_module.engine_ssh is None:
        return {}
    
    _id_evento_to_sku = {
        '40048': 'CDE26PL1', '40145': 'CDE26RP1', '39969': 'CDE26RJ1',
        '40120': 'CDE26FL1', '39996': 'CDE26PA1', '39964': 'CDE26SP1',
        '40052': 'CDE26AN1', '39974': 'CDE26BH1', '39970': 'CDE26BS1',
        '40001': 'CDE26CP1', '39986': 'CDE26RC1', '40010': 'CDE26BL1',
        '39980': 'CDE26FT1', '40149': 'CDE26SJ1', '39994': 'CDE26CT1',
        '40157': 'CDE26TS1', '40015': 'CDE26VT1', '40144': 'CDE26MN4',
        '40142': 'CDE26MN2', '40143': 'CDE26MN3', '39990': 'CDE26SV1',
        '40075': 'TBT26ST1', '40108': 'NRU26RF1', '40073': 'BRV26SP4',
        '39999': 'CDE26PA2', '39971': 'CDE26RJ2', '40122': 'CDE26FL3',
        '40121': 'CDE26FL2', '40076': 'TBT26ST2', '40049': 'CDE26PL2',
        '40158': 'CDE26TS2', '40072': 'BRV26SP2', '40150': 'CDE26SJ2',
        '40151': 'CDE26SJ3', '40146': 'CDE26RP2', '40053': 'CDE26AN2',
        '40003': 'CDE26CP2', '39987': 'CDE26RC2', '39965': 'CDE26SP2',
        '39975': 'CDE26BS2', '39982': 'CDE26FT2', '40107': 'NRU26CW1',
        '40074': 'BRV26SJ1', '39995': 'CDE26CT2', '40016': 'CDE26VT2',
        '39991': 'CDE26SV2', '40011': 'CDE26BL2', '40148': 'CDE26RP4',
        '40147': 'CDE26RP3', '39978': 'CDE26BH2', '40070': 'AQA26RJ2',
        '40050': 'CDE26PL3', '40054': 'CDE26AN3', '40005': 'CDE26CP3',
        '39983': 'CDE26FT3', '39976': 'CDE26BS3', '40017': 'CDE26VT3',
        '39988': 'CDE26RC3', '39966': 'CDE26SP3', '39997': 'CDE26CT3',
        '40159': 'CDE26TS3', '39992': 'CDE26SV3', '40012': 'CDE26BL3',
        '40077': 'TBT26ST3', '39972': 'CDE26RJ3', '40000': 'CDE26PA3',
        '40113': 'NRU26FT1', '40109': 'NRU26SV1', '40081': 'NRU26RJ2',
        '40112': 'NRU26BS1', '40063': 'NRU26SP3', '40123': 'CDE26FL4',
        '40105': 'NRU26PA1', '39973': 'CDE26RJ4', '40047': 'CDE26PL4',
        '40160': 'CDE26TS4', '40055': 'CDE26AN4', '39967': 'CDE26SP4',
        '40078': 'TBT26ST4', '40152': 'CDE26SJ4', '39998': 'CDE26CT4',
        '39985': 'CDE26FT4', '39993': 'CDE26SV4', '40014': 'CDE26BL4',
        '39984': 'CDE26BH4', '39977': 'CDE26BS4', '40002': 'CDE26PA4',
        '40004': 'CDE26CP4', '40018': 'CDE26VT4', '39989': 'CDE26RC4',
    }
    
    try:
        query = """
        SELECT /*+ MAX_EXECUTION_TIME(45000) */
            b.id_evento,
            b.id_campanha_salesforce,
            COUNT(DISTINCT CASE 
                WHEN DATE(p.dt_pedido) BETWEEN DATE_SUB(CURDATE(), INTERVAL 14 DAY) AND CURDATE()
                THEN pe.id_pedido_evento 
            END) / 14 AS media_14d_atual,
            COUNT(DISTINCT CASE 
                WHEN DATE(p.dt_pedido) BETWEEN DATE_SUB(DATE_SUB(CURDATE(), INTERVAL 1 YEAR), INTERVAL 14 DAY) 
                                           AND DATE_SUB(CURDATE(), INTERVAL 1 YEAR)
                THEN pe.id_pedido_evento 
            END) / 14 AS media_14d_ano_passado
        FROM sa_pedido_evento AS pe
        INNER JOIN sa_evento AS b ON b.id_evento = pe.id_evento
        INNER JOIN sa_pedido AS p ON p.id_pedido = pe.id_pedido
        LEFT JOIN sa_modalidade_categoria AS mc ON pe.id_categoria = mc.id_categoria
        LEFT JOIN sa_cupom_desconto_item AS cdi ON cdi.id_cupom_desconto_item = pe.id_cupom_individual
        LEFT JOIN sa_cupom_desconto AS cd ON cd.id_cupom_desconto = cdi.id_cupom_desconto
        WHERE 
            YEAR(b.dt_evento) IN (YEAR(CURDATE()), YEAR(CURDATE()) - 1)
            AND p.id_pedido_status = 2
            AND (b.id_campanha_salesforce NOT LIKE '701d0000000%%' OR b.id_campanha_salesforce IS NULL)
            AND (cd.en_cupom_classificacao IS NULL OR NOT cd.en_cupom_classificacao OR mc.ds_categoria NOT LIKE '%%Grup%%')
            AND p.nr_total > 0
            AND (
                DATE(p.dt_pedido) BETWEEN DATE_SUB(CURDATE(), INTERVAL 14 DAY) AND CURDATE()
                OR DATE(p.dt_pedido) BETWEEN DATE_SUB(DATE_SUB(CURDATE(), INTERVAL 1 YEAR), INTERVAL 14 DAY) 
                                         AND DATE_SUB(CURDATE(), INTERVAL 1 YEAR)
            )
        GROUP BY b.id_evento, b.id_campanha_salesforce
        """
        
        with db_module.engine_ssh.connect() as conn:
            result = conn.execute(text(query))
            rows = result.fetchall()
            columns = result.keys()
            
            data = {}
            for row in rows:
                row_dict = dict(zip(columns, row))
                id_evento = str(row_dict.get('id_evento', '') or '')
                sku = _id_evento_to_sku.get(id_evento)
                if not sku:
                    sku = str(row_dict.get('id_campanha_salesforce', '') or '')
                sku = normalize_sku(sku)
                if sku:
                    data[sku] = {
                        'media_14d_atual': float(row_dict.get('media_14d_atual', 0) or 0),
                        'media_14d_ano_passado': float(row_dict.get('media_14d_ano_passado', 0) or 0),
                    }
            return data
    except Exception as e:
        logger.error(f"Erro ao buscar rolling avg Ativo: {e}")
        return {}


def fetch_rolling_avg_magento() -> dict:
    if db_module.engine_magento is None:
        return {}
    
    _location_to_sku = {
        '587': 'CPLIE26SP1', '612': 'BLU26RJ1', '539': 'CDE26PL4',
        '536': 'CDE26PL1', '560': 'CDE26TS4', '559': 'CDE26TS3',
        '558': 'CDE26TS2', '537': 'CDE26PL2', '557': 'CDE26TS1',
        '510': 'NRU26PA1', '438': 'CDE26RJ4', '437': 'CDE26RJ3',
        '436': 'CDE26RJ2', '462': 'CDE26SV4', '464': 'CDE26SV3',
        '463': 'CDE26SV2', '469': 'CDE26CP4', '470': 'CDE26CP3',
        '471': 'CDE26CP2', '441': 'CDE26SP2', '443': 'CDE26SP4',
        '455': 'CDE26FT4', '454': 'CDE26FT3', '453': 'CDE26FT2',
        '466': 'CDE26CT2', '518': 'NRU26FT1', '513': 'NRU26VT1',
        '446': 'CDE26BS3', '444': 'CDE26BS2', '449': 'CDE26BH2',
        '473': 'CDE26PA4', '474': 'CDE26PA3', '475': 'CDE26PA2',
        '468': 'CDE26CT4', '467': 'CDE26CT3', '447': 'CDE26BS4',
        '544': 'GPW26SP11', '442': 'CDE26SP3', '451': 'CDE26BH4',
        '519': 'NRU26SV1', '516': 'NRU26BS1', '515': 'NRU26RF1',
        '521': 'NRU26CP1', '491': 'BRV26SP1', '512': 'NRU26CW1',
        '481': 'NRU26SP3', '492': 'BRV26SP4',
    }
    
    try:
        query = """
        SELECT /*+ MAX_EXECUTION_TIME(45000) */
            wl.location_id,
            d.sku AS product_sku,
            COUNT(DISTINCT CASE 
                WHEN DATE(so.created_at) BETWEEN DATE_SUB(CURDATE(), INTERVAL 14 DAY) AND CURDATE()
                THEN so.entity_id 
            END) / 14 AS media_14d_atual,
            COUNT(DISTINCT CASE 
                WHEN DATE(so.created_at) BETWEEN DATE_SUB(DATE_SUB(CURDATE(), INTERVAL 1 YEAR), INTERVAL 14 DAY) 
                                              AND DATE_SUB(CURDATE(), INTERVAL 1 YEAR)
                THEN so.entity_id 
            END) / 14 AS media_14d_ano_passado
        FROM sales_order AS so
        INNER JOIN sales_order_item AS soi ON soi.order_id = so.entity_id  
        INNER JOIN webpos_location AS wl ON so.location_pickup_id = wl.location_id
        LEFT JOIN catalog_product_entity_varchar AS pai ON pai.entity_id = soi.product_id AND pai.attribute_id = 321
        LEFT JOIN catalog_product_entity AS d ON pai.value = d.entity_id
        WHERE
            YEAR(wl.final_date) IN (YEAR(CURDATE()), YEAR(CURDATE()) - 1)
            AND so.increment_id NOT LIKE '%-1%'
            AND so.increment_id NOT LIKE '%-2%'
            AND so.increment_id NOT LIKE '%-3%'
            AND so.increment_id NOT LIKE '%-4%'
            AND so.increment_id NOT LIKE '%-5%'
            AND so.increment_id NOT LIKE '%-6%'
            AND so.increment_id NOT LIKE '%-7%'
            AND so.increment_id NOT LIKE '%-8%'
            AND so.increment_id NOT LIKE '%-9%'
            AND so.increment_id NOT LIKE '%-10%'
            AND so.increment_id NOT LIKE '%-11%'
            AND so.increment_id NOT LIKE '%-12%'
            AND so.increment_id NOT LIKE '%-13%'
            AND so.increment_id NOT LIKE '%-14%'
            AND so.increment_id NOT LIKE '%-15%'
            AND so.increment_id NOT LIKE '%-16%'
            AND so.increment_id NOT LIKE '%-17%'
            AND so.status IN ('Processing', 'Complete', 'approved')
            AND soi.product_type = 'Bundle'
            AND (so.discount_description IS NULL OR so.discount_description NOT LIKE '%Grup%')
            AND so.base_grand_total > 0
            AND (
                DATE(so.created_at) BETWEEN DATE_SUB(CURDATE(), INTERVAL 14 DAY) AND CURDATE()
                OR DATE(so.created_at) BETWEEN DATE_SUB(DATE_SUB(CURDATE(), INTERVAL 1 YEAR), INTERVAL 14 DAY) 
                                            AND DATE_SUB(CURDATE(), INTERVAL 1 YEAR)
            )
        GROUP BY wl.location_id, d.sku
        """
        
        with db_module.engine_magento.connect() as conn:
            result = conn.execute(text(query))
            rows = result.fetchall()
            columns = result.keys()
            
            data = {}
            for row in rows:
                row_dict = dict(zip(columns, row))
                location_id = str(row_dict.get('location_id', '') or '')
                sku = _location_to_sku.get(location_id, '')
                if not sku:
                    sku = str(row_dict.get('product_sku', '') or '')
                sku = normalize_sku(sku)
                if sku:
                    media_atual = float(row_dict.get('media_14d_atual', 0) or 0)
                    media_passado = float(row_dict.get('media_14d_ano_passado', 0) or 0)
                    if sku in data:
                        data[sku]['media_14d_atual'] += media_atual
                        data[sku]['media_14d_ano_passado'] += media_passado
                    else:
                        data[sku] = {
                            'media_14d_atual': media_atual,
                            'media_14d_ano_passado': media_passado,
                        }
            return data
    except Exception as e:
        logger.error(f"Erro ao buscar rolling avg Magento: {e}")
        return {}


_rolling_avg_executor = ThreadPoolExecutor(max_workers=4)

def fetch_consolidated_rolling_averages() -> dict:
    global _rolling_avg_cache, _rolling_avg_cache_timestamp
    import time
    
    cache_valid = (_rolling_avg_cache_timestamp is not None and 
                   time.time() - _rolling_avg_cache_timestamp < 300)
    
    if cache_valid and _rolling_avg_cache:
        return _rolling_avg_cache
    
    consolidated = {}
    
    future_ativo = _rolling_avg_executor.submit(fetch_rolling_avg_ativo)
    future_magento = _rolling_avg_executor.submit(fetch_rolling_avg_magento)
    
    try:
        ativo_data = future_ativo.result(timeout=30)
    except Exception as e:
        logger.error(f"Timeout ou erro ao buscar rolling avg Ativo: {e}")
        ativo_data = {}
    
    try:
        magento_data = future_magento.result(timeout=60)
    except Exception as e:
        logger.error(f"Timeout ou erro ao buscar rolling avg Magento: {e}")
        magento_data = {}
    
    for sku, values in ativo_data.items():
        consolidated[sku] = {
            'media_14d_atual': values.get('media_14d_atual', 0),
            'media_14d_ano_passado': values.get('media_14d_ano_passado', 0),
        }
    
    for sku, values in magento_data.items():
        if sku in consolidated:
            consolidated[sku]['media_14d_atual'] += values.get('media_14d_atual', 0)
            consolidated[sku]['media_14d_ano_passado'] += values.get('media_14d_ano_passado', 0)
        else:
            consolidated[sku] = {
                'media_14d_atual': values.get('media_14d_atual', 0),
                'media_14d_ano_passado': values.get('media_14d_ano_passado', 0),
            }
    
    _rolling_avg_cache = consolidated
    _rolling_avg_cache_timestamp = time.time()
    
    logger.info(f"Rolling averages consolidados: {len(consolidated)} SKUs")
    return consolidated


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
    rolling_avg_14d_real: float = None,
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
    
    pricing_all_projetos = []
    for proj_list in grupo_projetos.values():
        pricing_all_projetos.extend(proj_list)
    pricing_all_projetos.extend(standalone_projetos)
    pricing_sku_daily = _prefetch_all_daily_sales(db, pricing_all_projetos, ano)
    
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
        if total_capacity <= 0:
            total_capacity = 1000
        
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
        sales_goal = total_capacity if total_capacity > 0 else 1000
        kit_cost = total_kit_cost / kit_count if kit_count > 0 else 50.0
        
        all_skus = [str(p.codigo) for p in proj_list if p.codigo]
        
        grupo_location = str(rep_cadastro.localizacao_evento) if rep_cadastro and rep_cadastro.localizacao_evento else (rep_projeto.cidade or "Local não definido")
        
        pricing_metrics = calculate_pricing_metrics(
            current_sales=current_sales,
            sales_goal=sales_goal,
            d_minus=d_minus,
            average_ticket=average_ticket,
            kit_cost=kit_cost,
            total_capacity=total_capacity if total_capacity > 0 else 10000,
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
        
        pricing_daily_dict = _build_grupo_daily_dict(pricing_sku_daily, proj_list)
        
        pricing_hist_pattern = None
        try:
            pricing_hist_pattern = _fetch_previous_year_cumulative_pattern(db, grupo_nome, ano)
        except Exception:
            pass
        
        isc_components = calculate_isc_components(current_sales, sales_goal, d_minus,
                                                   daily_sales_dict=pricing_daily_dict,
                                                   hist_pattern=pricing_hist_pattern)
        isc = calculate_isc(isc_components, isc_cfg["ia730Weight"], isc_cfg["curvaDWeight"], isc_cfg["rolling14dWeight"])
        isc_status = get_isc_status(isc, isc_cfg["greenThreshold"], isc_cfg["yellowThreshold"])
        
        evento = PricingEvent(
            id=f"grp_{grupo_nome}",
            name=grupo.nome,
            date=projeto_data_evento.isoformat() if projeto_data_evento else "",
            location=grupo_location,
            category=grupo_modalidade,
            totalCapacity=total_capacity if total_capacity > 0 else 10000,
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
            iscStatus=isc_status
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
        
        standalone_pricing_daily_dict = _build_grupo_daily_dict(pricing_sku_daily, [projeto])
        
        _yesterday_pricing = date.today() - timedelta(days=1)
        if standalone_pricing_daily_dict and len(standalone_pricing_daily_dict) > 0:
            current_sales = sum(v for k, v in standalone_pricing_daily_dict.items() if k <= _yesterday_pricing)
            average_ticket = round(current_receita / current_sales, 2) if current_sales > 0 else 0.0
        
        standalone_pricing_hist = None
        if standalone_pricing_eg:
            try:
                standalone_pricing_hist = _fetch_previous_year_cumulative_pattern(db, standalone_pricing_eg, ano)
            except Exception:
                pass
        
        isc_components = calculate_isc_components(current_sales, sales_goal, d_minus,
                                                   daily_sales_dict=standalone_pricing_daily_dict,
                                                   hist_pattern=standalone_pricing_hist)
        isc = calculate_isc(isc_components, isc_cfg["ia730Weight"], isc_cfg["curvaDWeight"], isc_cfg["rolling14dWeight"])
        isc_status = get_isc_status(isc, isc_cfg["greenThreshold"], isc_cfg["yellowThreshold"])
        
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
            iscStatus=isc_status
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
    return {"status": "success", "key": key, "value": setting.value}
