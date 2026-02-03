from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional, List
from pydantic import BaseModel
from datetime import datetime, date, timedelta
from ...core.database import get_db, engine_ativo, engine_ssh
from ...core import database as db_module
from ...core.security import get_current_user
from ...models.dimensoes import DimProjeto
from ...models.user import Usuario
from .inscricoes_consolidado import normalize_sku
import logging
import asyncio
from concurrent.futures import ThreadPoolExecutor
import httpx

logger = logging.getLogger(__name__)


def fetch_daily_sales_ativo(id_evento: str, start_date: date, end_date: date) -> dict:
    """
    Busca vendas diárias do Ativo para um evento específico dentro de um período.
    Retorna um dicionário {data: quantidade_vendida}
    """
    if db_module.engine_ssh is None:
        return {}
    
    try:
        query = f"""
        SELECT 
            DATE(c.dt_cadastro) AS data_venda,
            COUNT(a.id_pedido_evento) AS quantidade
        FROM sa_pedido_evento AS a
        INNER JOIN sa_evento AS b ON b.id_evento = a.id_evento
        INNER JOIN sa_pedido AS c ON c.id_pedido = a.id_pedido
        WHERE 
            b.id_evento = '{id_evento}'
            AND c.id_pedido_status = 2
            AND DATE(c.dt_cadastro) >= '{start_date.isoformat()}'
            AND DATE(c.dt_cadastro) <= '{end_date.isoformat()}'
        GROUP BY DATE(c.dt_cadastro)
        ORDER BY data_venda
        """
        
        with db_module.engine_ssh.connect() as conn:
            result = conn.execute(text(query))
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
        query = f"""
        SELECT 
            DATE(so.created_at) AS data_venda,
            COUNT(soi.item_id) AS quantidade
        FROM sales_order AS so
        LEFT JOIN sales_order_item AS soi ON soi.order_id = so.entity_id
        LEFT JOIN webpos_location AS wl ON so.location_pickup_id = wl.location_id
        WHERE 
            wl.location_id = '{location_id}'
            AND so.status IN ('Processing', 'Complete', 'approved')
            AND soi.product_type = 'Bundle'
            AND DATE(so.created_at) >= '{start_date.isoformat()}'
            AND DATE(so.created_at) <= '{end_date.isoformat()}'
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
        
        with db_module.engine_magento.connect() as conn:
            result = conn.execute(text(query))
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


def get_location_id_from_sku(sku: str) -> Optional[str]:
    """
    Obtém o location_id do Magento a partir do SKU.
    Mapeamento completo baseado na query build_query_magento em inscricoes_consolidado.py.
    """
    sku_to_location_id = {
        'CPLIE26SP1': '587', 'BLU26RJ1': '612', 'CDE26PL4': '539',
        'CDE26PL1': '536', 'CDE26TS4': '560', 'CDE26TS3': '559',
        'CDE26TS2': '558', 'CDE26PL2': '537', 'CDE26TS1': '557',
        'NRU26PA1': '510', 'CDE26RJ4': '438', 'CDE26RJ3': '437',
        'CDE26RJ2': '436', 'CDE26SV4': '462', 'CDE26SV3': '464',
        'CDE26SV2': '463', 'CDE26CP4': '469', 'CDE26CP3': '470',
        'CDE26CP2': '471', 'CDE26SP2': '441', 'CDE26SP4': '443',
        'CDE26FT4': '455', 'CDE26FT3': '454', 'CDE26FT2': '453',
        'CDE26CT2': '466', 'NRU26FT1': '518', 'NRU26VT1': '513',
        'CDE26BS3': '446', 'CDE26BS2': '444', 'CDE26BH2': '449',
        'CDE26PA4': '473', 'CDE26PA3': '474', 'CDE26PA2': '475',
        'CDE26CT4': '468', 'CDE26CT3': '467', 'CDE26BS4': '447',
        'GPW26SP11': '544', 'CDE26SP3': '442', 'CDE26BH4': '451',
        'NRU26SV1': '519', 'NRU26BS1': '516', 'NRU26RF1': '515',
        'NRU26CP1': '521', 'BRV26SP1': '491', 'NRU26CW1': '512',
        'NRU26SP3': '481', 'BRV26SP4': '492',
        'CDE26RJ1': '435', 'CDE26SP1': '440', 'CDE26BS1': '443',
        'CDE26BH1': '448', 'CDE26FT1': '452', 'CDE26SV1': '461',
        'CDE26CT1': '465', 'CDE26CP1': '472', 'CDE26PA1': '476',
        'CDE26VT1': '477', 'CDE26VT2': '478', 'CDE26VT3': '479',
        'CDE26VT4': '480', 'CDE26AN1': '482', 'CDE26AN2': '483',
        'CDE26AN3': '484', 'CDE26AN4': '485', 'CDE26RC1': '486',
        'CDE26RC2': '487', 'CDE26RC3': '488', 'CDE26RC4': '489',
        'CDE26BL1': '493', 'CDE26BL2': '494', 'CDE26BL3': '495',
        'CDE26BL4': '496', 'CDE26FL1': '497', 'CDE26FL2': '498',
        'CDE26FL3': '499', 'CDE26FL4': '500', 'CDE26RP1': '501',
        'CDE26RP2': '502', 'CDE26RP3': '503', 'CDE26RP4': '504',
        'CDE26SJ1': '505', 'CDE26SJ2': '506', 'CDE26SJ3': '507',
        'CDE26SJ4': '508', 'NRU26RJ1': '509', 'NRU26RJ2': '511',
        'TBT26ST1': '520', 'TBT26ST2': '522', 'TBT26ST3': '523',
        'TBT26ST4': '524', 'BRV26SP2': '525', 'BRV26SJ1': '526',
    }
    
    return sku_to_location_id.get(sku.upper().strip())


def get_id_evento_from_projeto(db: Session, projeto_id: int) -> Optional[str]:
    """
    Obtém o id_evento do Ativo a partir do projeto (via codigo/SKU).
    """
    projeto = db.query(DimProjeto).filter(DimProjeto.id == projeto_id).first()
    if not projeto or not projeto.codigo:
        return None
    
    sku = projeto.codigo.upper().strip()
    
    sku_to_id_evento = {
        'CDE26PL1': '40048', 'CDE26RP1': '40145', 'CDE26RJ1': '39969',
        'CDE26FL1': '40120', 'CDE26PA1': '39996', 'CDE26SP1': '39964',
        'CDE26AN1': '40052', 'CDE26BH1': '39974', 'CDE26BS1': '39970',
        'CDE26CP1': '40001', 'CDE26RC1': '39986', 'CDE26BL1': '40010',
        'CDE26FT1': '39980', 'CDE26SJ1': '40149', 'CDE26CT1': '39994',
        'CDE26TS1': '40157', 'CDE26VT1': '40015', 'CDE26MN4': '40144',
        'CDE26MN2': '40142', 'CDE26MN3': '40143', 'CDE26SV1': '39990',
        'TBT26ST1': '40075', 'NRU26RF1': '40108', 'BRV26SP4': '40073',
        'CDE26PA2': '39999', 'CDE26RJ2': '39971', 'CDE26FL3': '40122',
        'CDE26FL2': '40121', 'TBT26ST2': '40076', 'CDE26PL2': '40049',
        'CDE26TS2': '40158', 'BRV26SP2': '40072', 'CDE26SJ2': '40150',
        'CDE26SJ3': '40151', 'CDE26RP2': '40146', 'CDE26AN2': '40053',
        'CDE26CP2': '40003', 'CDE26RC2': '39987', 'CDE26SP2': '39965',
        'CDE26BS2': '39975', 'CDE26FT2': '39982', 'NRU26CW1': '40107',
        'BRV26SJ1': '40074', 'CDE26CT2': '39995', 'CDE26VT2': '40016',
        'CDE26SV2': '39991', 'CDE26BL2': '40011', 'CDE26RP4': '40148',
        'CDE26RP3': '40147', 'CDE26BH2': '39978', 'AQA26RJ2': '40070',
        'CDE26PL3': '40050', 'CDE26AN3': '40054', 'CDE26CP3': '40005',
        'CDE26FT3': '39983', 'CDE26BS3': '39976', 'CDE26VT3': '40017',
        'CDE26RC3': '39988', 'CDE26SP3': '39966', 'CDE26CT3': '39997',
        'CDE26TS3': '40159', 'CDE26SV3': '39992', 'CDE26BL3': '40012',
        'TBT26ST3': '40077', 'CDE26RJ3': '39972', 'CDE26PA3': '40000',
        'NRU26FT1': '40113', 'NRU26SV1': '40109', 'NRU26RJ2': '40081',
    }
    
    return sku_to_id_evento.get(sku)


def calculate_action_impact(db: Session, acao) -> dict:
    """
    Calcula o impacto de uma ação comercial comparando vendas consolidadas (Ativo + Magento)
    7 dias antes vs 7 dias depois da ação.
    """
    if not acao.data_acao:
        return {"vendas_antes": None, "vendas_depois": None, "impacto_percentual": None}
    
    projeto = db.query(DimProjeto).filter(DimProjeto.id == acao.projeto_id).first()
    if not projeto or not projeto.codigo:
        return {"vendas_antes": None, "vendas_depois": None, "impacto_percentual": None}
    
    sku = projeto.codigo.upper().strip()
    id_evento = get_id_evento_from_projeto(db, acao.projeto_id)
    location_id = get_location_id_from_sku(sku)
    
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
    dMinus: int
    isc: float
    iscComponents: ISCComponents
    iscStatus: str
    suggestedAction: str
    lastAction: Optional[CommercialAction] = None
    isActive: bool
    sku: Optional[str] = None

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

def get_isc_status(isc: float) -> str:
    if isc > 1.10:
        return "accelerating"
    if isc >= 0.90:
        return "stable"
    return "decelerating"

def get_suggested_action(isc: float, d_minus: int) -> str:
    status = get_isc_status(isc)
    
    if status == "accelerating":
        return "Evento forte. Considere ajuste de preço para cima."
    
    if status == "stable":
        if d_minus >= 40:
            return "Evento estável. Monitore e reforce comunicação."
        return "Evento estável. Apenas ajustes de comunicação."
    
    if d_minus >= 40:
        return "Evento fraco. Janela aberta para ação promocional."
    
    return "⚠️ Evento fraco, mas fora da janela de promoção. Apenas reforço de comunicação."

def calculate_d_minus(event_date: date) -> int:
    if not event_date:
        return 0
    today = date.today()
    delta = (event_date - today).days
    return max(0, delta)

def calculate_isc_components(current_sales: int, sales_goal: int, d_minus: int) -> ISCComponents:
    """
    Calcula os componentes do ISC baseado nas vendas atuais vs meta.
    Como não temos dados diários de vendas, estimamos os componentes
    baseados na progressão atual vs esperada.
    """
    if sales_goal == 0:
        return ISCComponents(ia730=1.0, curvaDPercent=1.0, rolling14d=1.0)
    
    progress_percent = current_sales / sales_goal
    
    total_days = 90
    elapsed_days = max(1, total_days - d_minus)
    expected_progress = elapsed_days / total_days
    
    if expected_progress == 0:
        expected_progress = 0.01
    
    curva_d_percent = progress_percent / expected_progress
    
    if curva_d_percent > 1.2:
        ia730 = 1.15 + (curva_d_percent - 1.2) * 0.3
    elif curva_d_percent > 1.0:
        ia730 = 1.0 + (curva_d_percent - 1.0) * 0.5
    elif curva_d_percent > 0.8:
        ia730 = 0.9 + (curva_d_percent - 0.8) * 0.5
    else:
        ia730 = 0.7 + curva_d_percent * 0.25
    
    rolling14d = (curva_d_percent + ia730) / 2
    
    ia730 = max(0.5, min(1.5, ia730))
    curva_d_percent = max(0.5, min(1.5, curva_d_percent))
    rolling14d = max(0.5, min(1.5, rolling14d))
    
    return ISCComponents(
        ia730=round(ia730, 2),
        curvaDPercent=round(curva_d_percent, 2),
        rolling14d=round(rolling14d, 2)
    )

def calculate_isc(components: ISCComponents) -> float:
    """Calcula o ISC como média dos 3 componentes"""
    return round((components.ia730 + components.curvaDPercent + components.rolling14d) / 3, 2)

def generate_daily_sales_data(current_sales: int, sales_goal: int, event_date, days_history: int = 60) -> List[dict]:
    """
    Gera dados de vendas diárias simulados para os gráficos.
    Baseado nas vendas acumuladas atuais e na meta.
    """
    import random
    from datetime import timedelta
    
    if not event_date:
        return []
    
    today = datetime.now().date()
    event_day = event_date if isinstance(event_date, date) else event_date.date() if hasattr(event_date, 'date') else today
    
    days_until_event = (event_day - today).days
    total_sales_period = days_history + max(0, days_until_event)
    days_elapsed = days_history
    
    daily_sales = []
    
    if current_sales > 0 and days_elapsed > 0:
        base_daily = current_sales / days_elapsed
    else:
        base_daily = sales_goal / total_sales_period if total_sales_period > 0 else 10
    
    cumulative_sales = 0
    cumulative_expected = 0
    
    for i in range(days_history):
        day_date = today - timedelta(days=days_history - i - 1)
        
        progress_ratio = (i + 1) / total_sales_period if total_sales_period > 0 else 1
        expected_daily = (sales_goal / total_sales_period) * (1 + 0.5 * progress_ratio)
        
        variation = random.uniform(0.7, 1.3)
        actual_daily = max(0, int(base_daily * variation))
        
        cumulative_sales += actual_daily
        cumulative_expected += expected_daily
        
        daily_sales.append({
            "date": day_date.isoformat(),
            "sales": actual_daily,
            "expected": round(expected_daily, 1),
            "cumulativeSales": cumulative_sales,
            "cumulativeExpected": round(cumulative_expected, 1)
        })
    
    if daily_sales and current_sales > 0:
        scale_factor = current_sales / cumulative_sales if cumulative_sales > 0 else 1
        running_total = 0
        for day in daily_sales:
            day["sales"] = max(0, int(day["sales"] * scale_factor))
            running_total += day["sales"]
            day["cumulativeSales"] = running_total
    
    return daily_sales

_sales_cache = {}
_cache_timestamp = None

def fetch_consolidated_sales_by_skus(skus: List[str], ano: int) -> dict:
    """
    Busca vendas consolidadas (Ativo + Magento) para uma lista de SKUs.
    Usa cache para evitar queries repetidas.
    Retorna dict com SKU como chave.
    """
    global _sales_cache, _cache_timestamp
    from .inscricoes_consolidado import fetch_ativo_data, fetch_magento_data
    import time
    
    sales_by_sku = {}
    
    if not skus:
        return sales_by_sku
    
    skus_normalized = [normalize_sku(s) for s in skus]
    cache_key = f"{ano}"
    
    current_time = time.time()
    cache_valid = _cache_timestamp and (current_time - _cache_timestamp) < 300
    
    if cache_valid and cache_key in _sales_cache:
        cached_data = _sales_cache[cache_key]
        for sku in skus_normalized:
            if sku in cached_data:
                sales_by_sku[sku] = cached_data[sku].copy()
        return sales_by_sku
    
    all_sales = {}
    
    try:
        dados_ativo, error = fetch_ativo_data(ano)
        if dados_ativo:
            for row in dados_ativo:
                sku = normalize_sku(row.get('sku', '') or '')
                if sku:
                    all_sales[sku] = {
                        'qtd_ativo': int(row.get('qtd_vendida', 0) or 0),
                        'valor_ativo': float(row.get('inscricao_liquida', 0) or 0),
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
            for row in dados_magento:
                sku = normalize_sku(row.get('sku', '') or '')
                if sku:
                    if sku in all_sales:
                        all_sales[sku]['qtd_magento'] = int(row.get('qtd_vendida', 0) or 0)
                        all_sales[sku]['valor_magento'] = float(row.get('inscricao_liquida', 0) or 0)
                    else:
                        all_sales[sku] = {
                            'qtd_ativo': 0,
                            'valor_ativo': 0,
                            'qtd_magento': int(row.get('qtd_vendida', 0) or 0),
                            'valor_magento': float(row.get('inscricao_liquida', 0) or 0)
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


@router.get("/eventos", response_model=MarketingEventsResponse)
async def get_marketing_events(
    ano: int = Query(default=None, description="Ano dos eventos"),
    status: Optional[str] = Query(None, description="Filtrar por status: active, closed, all"),
    categoria: Optional[str] = Query(None, description="Filtrar por categoria/modalidade"),
    busca: Optional[str] = Query(None, description="Buscar por nome do evento"),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    """
    Retorna eventos para o Dashboard ISC com dados consolidados de vendas
    dos bancos Ativo e Magento.
    """
    if ano is None:
        ano = datetime.now().year
    
    query = db.query(DimProjeto).filter(
        DimProjeto.codigo.isnot(None),
        DimProjeto.codigo != ''
    )
    
    if categoria and categoria != 'all':
        query = query.filter(DimProjeto.modalidade == categoria)
    
    if busca:
        query = query.filter(DimProjeto.evento.ilike(f'%{busca}%'))
    
    projetos = query.all()
    
    skus = [str(p.codigo) for p in projetos if p.codigo]
    sales_data = fetch_consolidated_sales_by_skus(skus, ano)
    
    eventos = []
    categorias_set: set[str] = set()
    events_green = 0
    events_yellow = 0
    events_red = 0
    active_count = 0
    
    for projeto in projetos:
        projeto_codigo = str(projeto.codigo) if projeto.codigo else None
        if not projeto_codigo:
            continue
        
        sku = projeto_codigo
        projeto_data_evento = projeto.data_evento
        d_minus = calculate_d_minus(projeto_data_evento) if projeto_data_evento else 0
        is_active = d_minus > 0
        
        if status == 'active' and not is_active:
            continue
        if status == 'closed' and is_active:
            continue
        
        sales_info = sales_data.get(sku, {})
        current_sales = sales_info.get('qtd_ativo', 0) + sales_info.get('qtd_magento', 0)
        total_revenue = sales_info.get('valor_ativo', 0) + sales_info.get('valor_magento', 0)
        
        sales_goal = int(projeto.capacidade_maxima) if projeto.capacidade_maxima else 1000
        
        avg_ticket = total_revenue / current_sales if current_sales > 0 else 150.0
        
        isc_components = calculate_isc_components(current_sales, sales_goal, d_minus)
        isc = calculate_isc(isc_components)
        isc_status = get_isc_status(isc)
        suggested_action = get_suggested_action(isc, d_minus)
        
        if is_active:
            active_count += 1
            if isc_status == 'accelerating':
                events_green += 1
            elif isc_status == 'stable':
                events_yellow += 1
            else:
                events_red += 1
        
        projeto_modalidade = str(projeto.modalidade) if projeto.modalidade else None
        if projeto_modalidade:
            categorias_set.add(projeto_modalidade)
        
        projeto_cidade = str(projeto.cidade) if projeto.cidade else None
        projeto_estado = str(projeto.estado) if projeto.estado else None
        projeto_nome = str(projeto.evento) if projeto.evento else "Evento sem nome"
        projeto_limite = int(projeto.capacidade_maxima) if projeto.capacidade_maxima else sales_goal
        
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
            dMinus=d_minus,
            isc=isc,
            iscComponents=isc_components,
            iscStatus=isc_status,
            suggestedAction=suggested_action,
            isActive=is_active,
            sku=sku
        )
        eventos.append(evento)
    
    eventos.sort(key=lambda e: (not e.isActive, e.dMinus))
    
    resumo = DashboardSummary(
        totalActiveEvents=active_count,
        eventsGreen=events_green,
        eventsYellow=events_yellow,
        eventsRed=events_red
    )
    
    return MarketingEventsResponse(
        status="success",
        eventos=eventos,
        resumo=resumo,
        categorias=sorted(list(categorias_set)),
        ultima_atualizacao=datetime.now().isoformat()
    )


@router.get("/resumo")
async def get_marketing_summary(
    ano: int = Query(default=None, description="Ano dos eventos"),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    """
    Retorna apenas o resumo do Dashboard ISC (contagem por zona).
    """
    response = await get_marketing_events(ano=ano, db=db, current_user=current_user)
    return {
        "status": "success",
        "resumo": response.resumo,
        "ultima_atualizacao": response.ultima_atualizacao
    }


@router.get("/eventos/{evento_id}")
async def get_marketing_event_by_id(
    evento_id: str,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    """
    Retorna os dados de um evento específico pelo ID.
    """
    projeto = db.query(DimProjeto).filter(DimProjeto.id == int(evento_id)).first()
    
    if not projeto:
        raise HTTPException(status_code=404, detail="Evento não encontrado")
    
    projeto_codigo = str(projeto.codigo) if projeto.codigo else None
    sku = projeto_codigo
    projeto_data_evento = projeto.data_evento
    d_minus = calculate_d_minus(projeto_data_evento) if projeto_data_evento else 0
    is_active = d_minus > 0
    
    ano = projeto_data_evento.year if projeto_data_evento else datetime.now().year
    sales_data = fetch_consolidated_sales_by_skus([sku] if sku else [], ano)
    
    sales_info = sales_data.get(sku, {}) if sku else {}
    current_sales = sales_info.get('qtd_ativo', 0) + sales_info.get('qtd_magento', 0)
    total_revenue = sales_info.get('valor_ativo', 0) + sales_info.get('valor_magento', 0)
    
    sales_goal = int(projeto.capacidade_maxima) if projeto.capacidade_maxima else 1000
    avg_ticket = total_revenue / current_sales if current_sales > 0 else 150.0
    
    isc_components = calculate_isc_components(current_sales, sales_goal, d_minus)
    isc = calculate_isc(isc_components)
    isc_status = get_isc_status(isc)
    suggested_action = get_suggested_action(isc, d_minus)
    
    projeto_modalidade = str(projeto.modalidade) if projeto.modalidade else None
    projeto_cidade = str(projeto.cidade) if projeto.cidade else None
    projeto_estado = str(projeto.estado) if projeto.estado else None
    projeto_nome = str(projeto.evento) if projeto.evento else "Evento sem nome"
    projeto_limite = int(projeto.capacidade_maxima) if projeto.capacidade_maxima else sales_goal
    
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
        dMinus=d_minus,
        isc=isc,
        iscComponents=isc_components,
        iscStatus=isc_status,
        suggestedAction=suggested_action,
        isActive=is_active,
        sku=sku
    )
    
    daily_sales = generate_daily_sales_data(
        current_sales=current_sales,
        sales_goal=sales_goal,
        event_date=projeto_data_evento,
        days_history=60
    )
    
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
    
    return {
        "status": "success",
        "evento": evento,
        "dailySales": daily_sales,
        "commercialActions": commercial_actions,
        "ultima_atualizacao": datetime.now().isoformat()
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
async def get_acoes_comerciais(
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
async def create_acao_comercial(
    acao: AcaoComercialCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    """Cria uma nova ação comercial"""
    from ...models.dimensoes import AcaoComercial
    
    projeto = db.query(DimProjeto).filter(DimProjeto.id == acao.projeto_id).first()
    if not projeto:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")
    
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
async def update_acao_comercial(
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
async def delete_acao_comercial(
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
