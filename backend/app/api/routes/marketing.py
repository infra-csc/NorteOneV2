from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional, List
from pydantic import BaseModel
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo
from ...core.database import get_db, engine_ativo, engine_ssh
from ...core import database as db_module
from ...core.security import get_current_user
from ...models.dimensoes import DimProjeto, EventoConsolidado, SkuMapping, EventoGrupo as EventoGrupoModel
from ...models.user import Usuario
from ...models.cadastro_evento import CadastroEvento, CadastroKitProduto, CadastroKitProdutoItem
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


def get_location_id_from_sku(db: Session, sku: str) -> Optional[str]:
    """
    Obtém o location_id do Magento a partir do SKU.
    Consulta dinâmica na tabela SkuMapping.
    """
    from ...models.dimensoes import SkuMapping
    mapping = db.query(SkuMapping).filter(
        SkuMapping.fonte == 'MAGENTO',
        SkuMapping.sku == sku.upper().strip(),
        SkuMapping.ativo == True
    ).first()
    return str(mapping.id_externo) if mapping else None


def get_id_evento_from_projeto(db: Session, projeto_id: int) -> Optional[str]:
    """
    Obtém o id_evento do Ativo a partir do projeto (via codigo/SKU).
    Consulta dinâmica na tabela SkuMapping.
    """
    from ...models.dimensoes import SkuMapping
    projeto = db.query(DimProjeto).filter(DimProjeto.id == projeto_id).first()
    if not projeto or not projeto.codigo:
        return None
    
    sku = projeto.codigo.upper().strip()
    
    mapping = db.query(SkuMapping).filter(
        SkuMapping.fonte == 'ATIVO',
        SkuMapping.sku == sku,
        SkuMapping.ativo == True
    ).first()
    return str(mapping.id_externo) if mapping else None


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
    avisos: List[str] = []

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

_isc_cache = {}
_isc_cache_timestamp = None

def build_query_isc_ativo() -> str:
    return """
SELECT /*+ MAX_EXECUTION_TIME(120000) */
    b.id_evento AS "id de evento",
    b.id_campanha_salesforce AS 'SKU',
    b.ds_evento AS "Evento",
    DATE(b.dt_evento) AS "Data Evento",
    COUNT(CASE WHEN (f.en_cupom_classificacao IS NULL OR NOT f.en_cupom_classificacao OR h.ds_categoria NOT LIKE '%%Grup%%') 
        AND c.nr_total > 0 THEN 1 END) AS "Qtd Site Atual",
    COUNT(CASE WHEN (f.en_cupom_classificacao IS NULL OR NOT f.en_cupom_classificacao OR h.ds_categoria NOT LIKE '%%Grup%%') 
        AND c.nr_total > 0
        AND c.dt_pedido >= DATE_SUB(CURDATE(), INTERVAL 14 DAY)
        AND c.dt_pedido < DATE_ADD(CURDATE(), INTERVAL 1 DAY)
        THEN 1 END) / 14 AS "Média Diária Últimos 14 Dias",
    COUNT(CASE WHEN (f.en_cupom_classificacao IS NULL OR NOT f.en_cupom_classificacao OR h.ds_categoria NOT LIKE '%%Grup%%') 
        AND c.nr_total > 0
        AND c.dt_pedido >= DATE_SUB(DATE_SUB(CURDATE(), INTERVAL 1 YEAR), INTERVAL 14 DAY)
        AND c.dt_pedido < DATE_ADD(DATE_SUB(CURDATE(), INTERVAL 1 YEAR), INTERVAL 1 DAY)
        THEN 1 END) / 14 AS "Média Diária Últimos 14 Dias (Ano Passado)",
    DATEDIFF(DATE(b.dt_evento), CURDATE()) AS "Dias Até Evento",
    COUNT(CASE WHEN (f.en_cupom_classificacao IS NULL OR NOT f.en_cupom_classificacao OR h.ds_categoria NOT LIKE '%%Grup%%') 
        AND c.nr_total > 0 THEN 1 END) + 
    (
        COUNT(CASE WHEN (f.en_cupom_classificacao IS NULL OR NOT f.en_cupom_classificacao OR h.ds_categoria NOT LIKE '%%Grup%%') 
            AND c.nr_total > 0
            AND c.dt_pedido >= DATE_SUB(CURDATE(), INTERVAL 14 DAY)
            AND c.dt_pedido < DATE_ADD(CURDATE(), INTERVAL 1 DAY)
            THEN 1 END) / 14 * DATEDIFF(DATE(b.dt_evento), CURDATE())
    ) AS "Projeção Final"
FROM sa_pedido_evento AS a
INNER JOIN sa_evento AS b ON b.id_evento = a.id_evento
INNER JOIN sa_pedido AS c ON c.id_pedido = a.id_pedido
LEFT JOIN sa_modalidade_categoria AS h ON a.id_categoria = h.id_categoria
LEFT JOIN sa_cupom_desconto_item AS e ON e.id_cupom_desconto_item = a.id_cupom_individual
LEFT JOIN sa_cupom_desconto AS f ON f.id_cupom_desconto = e.id_cupom_desconto
WHERE 
    b.dt_evento >= CONCAT(YEAR(CURDATE()) - 1, '-01-01')
    AND b.dt_evento < CONCAT(YEAR(CURDATE()) + 1, '-01-01')
    AND c.id_pedido_status = 2
    AND (b.id_campanha_salesforce NOT LIKE '701d0000000%%' OR b.id_campanha_salesforce IS NULL)
GROUP BY b.id_evento, b.ds_evento, b.dt_evento
ORDER BY b.dt_evento
"""


def build_query_isc_magento() -> str:
    return """
SELECT
    wl.location_id AS "id de evento",
    d.sku AS 'SKU',
    REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(
        REPLACE(wl.`name`, 'Retirada de kit - CE', 'Circuito das Estações'),
        'Retirada de Kit - CE', 'Circuito das Estações'),'Retirada de KIt - CE', 'Circuito das Estações'),
        'Retirada de Kit- CE', 'Circuito das Estações'),'Retirada de Kit - ', ''),'Retirada de kit - ', ''),
        'SSA', 'Salvador') AS "Evento",
    wl.final_date AS "Data Evento",
    COUNT(CASE WHEN (so.discount_description IS NULL OR so.discount_description NOT LIKE '%%Grup%%') 
        AND so.base_grand_total > 0 THEN 1 END) AS "Qtd Site Atual",
    COUNT(CASE WHEN (so.discount_description IS NULL OR so.discount_description NOT LIKE '%%Grup%%') 
        AND so.base_grand_total > 0
        AND so.created_at >= DATE_SUB(CURDATE(), INTERVAL 14 DAY)
        AND so.created_at < DATE_ADD(CURDATE(), INTERVAL 1 DAY)
        THEN 1 END) / 14 AS "Média Diária Últimos 14 Dias",
    COUNT(CASE WHEN (so.discount_description IS NULL OR so.discount_description NOT LIKE '%%Grup%%') 
        AND so.base_grand_total > 0
        AND so.created_at >= DATE_SUB(DATE_SUB(CURDATE(), INTERVAL 1 YEAR), INTERVAL 14 DAY)
        AND so.created_at < DATE_ADD(DATE_SUB(CURDATE(), INTERVAL 1 YEAR), INTERVAL 1 DAY)
        THEN 1 END) / 14 AS "Média Diária Últimos 14 Dias (Ano Passado)",
    DATEDIFF(DATE(wl.final_date), CURDATE()) AS "Dias Até Evento",
    COUNT(CASE WHEN (so.discount_description IS NULL OR so.discount_description NOT LIKE '%%Grup%%') 
        AND so.base_grand_total > 0 THEN 1 END) + 
    (
        COUNT(CASE WHEN (so.discount_description IS NULL OR so.discount_description NOT LIKE '%%Grup%%') 
            AND so.base_grand_total > 0
            AND so.created_at >= DATE_SUB(CURDATE(), INTERVAL 14 DAY)
            AND so.created_at < DATE_ADD(CURDATE(), INTERVAL 1 DAY)
            THEN 1 END) / 14 * DATEDIFF(DATE(wl.final_date), CURDATE())
    ) AS "Projeção Final"
FROM sales_order AS so
LEFT JOIN sales_order_item AS soi ON soi.order_id = so.entity_id  
LEFT JOIN webpos_location AS wl ON so.location_pickup_id = wl.location_id
LEFT JOIN catalog_product_entity_varchar AS pai ON pai.entity_id = soi.product_id AND pai.attribute_id = 321
LEFT JOIN catalog_product_entity AS d ON pai.value = d.entity_id
WHERE
    wl.final_date >= CONCAT(YEAR(CURDATE()) - 1, '-01-01')
    AND wl.final_date < CONCAT(YEAR(CURDATE()) + 1, '-01-01')
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
    AND so.increment_id NOT LIKE "%%-17%%"
    AND so.status IN ('Processing', 'Complete', 'approved')
    AND soi.product_type = 'Bundle'
GROUP BY wl.location_id, wl.name, wl.final_date, d.sku
ORDER BY wl.final_date
"""


def fetch_isc_data_ativo():
    if db_module.engine_ssh is None:
        return {"error": "Conexão SSH não configurada"}
    try:
        query = build_query_isc_ativo()
        with db_module.engine_ssh.connect() as conn:
            result = conn.execute(text(query))
            rows = result.fetchall()
            logger.info(f"ISC Ativo: {len(rows)} registros")
            return [
                {
                    "id_evento": str(row[0]) if row[0] else None,
                    "sku": str(row[1]) if row[1] else None,
                    "evento": str(row[2]) if row[2] else None,
                    "data_evento": str(row[3]) if row[3] else None,
                    "qtd_site": int(row[4]) if row[4] else 0,
                    "media_14d": float(row[5]) if row[5] else 0.0,
                    "media_14d_ano_passado": float(row[6]) if row[6] else 0.0,
                    "dias_ate_evento": int(row[7]) if row[7] is not None else 0,
                    "projecao_final": float(row[8]) if row[8] else 0.0,
                }
                for row in rows
            ]
    except Exception as e:
        logger.error(f"Erro ISC Ativo: {e}")
        return {"error": f"Timeout ou erro de conexão ({type(e).__name__})"}


def fetch_isc_data_magento():
    if db_module.engine_magento is None:
        return {"error": "Conexão Magento não configurada"}
    try:
        query = build_query_isc_magento()
        with db_module.engine_magento.connect() as conn:
            result = conn.execute(text(query))
            rows = result.fetchall()
            logger.info(f"ISC Magento: {len(rows)} registros")
            return [
                {
                    "id_evento": str(row[0]) if row[0] else None,
                    "sku": str(row[1]) if row[1] else None,
                    "evento": str(row[2]) if row[2] else None,
                    "data_evento": str(row[3]) if row[3] else None,
                    "qtd_site": int(row[4]) if row[4] else 0,
                    "media_14d": float(row[5]) if row[5] else 0.0,
                    "media_14d_ano_passado": float(row[6]) if row[6] else 0.0,
                    "dias_ate_evento": int(row[7]) if row[7] is not None else 0,
                    "projecao_final": float(row[8]) if row[8] else 0.0,
                }
                for row in rows
            ]
    except Exception as e:
        logger.error(f"Erro ISC Magento: {e}")
        return {"error": f"Timeout ou erro de conexão ({type(e).__name__})"}


_isc_warnings = []

def fetch_isc_pricing_data(db: Session = None) -> dict:
    global _isc_cache, _isc_cache_timestamp, _isc_warnings
    import time

    current_time = time.time()
    cache_valid = _isc_cache_timestamp and (current_time - _isc_cache_timestamp) < 300

    if cache_valid and _isc_cache is not None:
        return _isc_cache

    from .inscricoes_consolidado import get_sku_mappings_from_db, enrich_with_mappings

    warnings = []

    mappings = None
    if db:
        try:
            current_year = datetime.now().year
            mappings = get_sku_mappings_from_db(db, current_year)
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

    for row in dados_ativo:
        sku = normalize_sku(row.get('sku', '') or '')
        if not sku:
            continue
        if sku in all_data:
            all_data[sku]['qtd_site'] += row.get('qtd_site', 0)
            all_data[sku]['media_14d'] += row.get('media_14d', 0.0)
            all_data[sku]['media_14d_ano_passado'] += row.get('media_14d_ano_passado', 0.0)
        else:
            all_data[sku] = {
                'qtd_site': row.get('qtd_site', 0),
                'media_14d': row.get('media_14d', 0.0),
                'media_14d_ano_passado': row.get('media_14d_ano_passado', 0.0),
                'dias_ate_evento': row.get('dias_ate_evento', 0),
                'projecao_final': 0,
                'evento_name': row.get('evento', ''),
                'data_evento': row.get('data_evento', ''),
            }

    if mappings and dados_magento:
        import copy
        dados_magento = copy.deepcopy(dados_magento)
        dados_magento = enrich_with_mappings(dados_magento, mappings, "magento", datetime.now().year)

    for row in dados_magento:
        sku = normalize_sku(row.get('sku', '') or '')
        if not sku:
            continue
        if sku in all_data:
            all_data[sku]['qtd_site'] += row.get('qtd_site', 0)
            all_data[sku]['media_14d'] += row.get('media_14d', 0.0)
            all_data[sku]['media_14d_ano_passado'] += row.get('media_14d_ano_passado', 0.0)
        else:
            all_data[sku] = {
                'qtd_site': row.get('qtd_site', 0),
                'media_14d': row.get('media_14d', 0.0),
                'media_14d_ano_passado': row.get('media_14d_ano_passado', 0.0),
                'dias_ate_evento': row.get('dias_ate_evento', 0),
                'projecao_final': 0,
                'evento_name': row.get('evento', ''),
                'data_evento': row.get('data_evento', ''),
            }

    for sku, data in all_data.items():
        dias = max(data['dias_ate_evento'], 0)
        data['projecao_final'] = data['qtd_site'] + data['media_14d'] * dias

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
    
    query = db.query(DimProjeto).filter(
        DimProjeto.codigo.isnot(None),
        DimProjeto.codigo != ''
    )
    
    if categoria and categoria != 'all':
        query = query.filter(DimProjeto.modalidade == categoria)
    
    if busca:
        query = query.filter(DimProjeto.evento.ilike(f'%{busca}%'))
    
    projetos = query.all()
    
    isc_data = fetch_isc_pricing_data(db=db)
    
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
    
    for grupo_nome, proj_list in grupo_projetos.items():
        grupo = grupo_details[grupo_nome]
        
        total_capacity = 0
        latest_date = None
        rep_projeto = proj_list[0]
        
        for p in proj_list:
            if p.capacidade_maxima:
                total_capacity += int(p.capacidade_maxima)
            if p.data_evento:
                if latest_date is None or p.data_evento > latest_date:
                    latest_date = p.data_evento
                    rep_projeto = p
        
        projeto_data_evento = latest_date or rep_projeto.data_evento
        d_minus = calculate_d_minus(projeto_data_evento) if projeto_data_evento else 0
        is_active = d_minus > 0
        
        if status == 'active' and not is_active:
            continue
        if status == 'closed' and is_active:
            continue
        
        current_sales = 0
        seen_grupo_norms = set()
        for p in proj_list:
            p_sku = normalize_sku(str(p.codigo)) if p.codigo else None
            if p_sku and p_sku not in seen_grupo_norms and p_sku in isc_data:
                seen_grupo_norms.add(p_sku)
                current_sales += isc_data[p_sku].get('qtd_site', 0)
        
        sales_goal = total_capacity if total_capacity > 0 else 1000
        avg_ticket = 150.0
        
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
        
        projeto_modalidade = str(rep_projeto.modalidade) if rep_projeto.modalidade else None
        if projeto_modalidade:
            categorias_set.add(projeto_modalidade)
        
        projeto_cidade = str(rep_projeto.cidade) if rep_projeto.cidade else None
        projeto_estado = str(rep_projeto.estado) if rep_projeto.estado else None
        
        skus_list = [str(p.codigo) for p in proj_list if p.codigo]
        
        evento = MarketingEvent(
            id=f"grp_{grupo_nome}",
            name=grupo.nome,
            date=projeto_data_evento.isoformat() if projeto_data_evento else "",
            location=projeto_cidade or projeto_estado or "Não definido",
            category=projeto_modalidade or "Corrida",
            totalCapacity=sales_goal,
            currentSales=current_sales,
            salesGoal=sales_goal,
            averageTicket=round(avg_ticket, 2),
            dMinus=d_minus,
            isc=isc,
            iscComponents=isc_components,
            iscStatus=isc_status,
            suggestedAction=suggested_action,
            isActive=is_active,
            sku=",".join(skus_list)
        )
        eventos.append(evento)
    
    for projeto in standalone_projetos:
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
        
        sku_norm = normalize_sku(sku)
        sales_info = isc_data.get(sku_norm, {})
        current_sales = sales_info.get('qtd_site', 0)
        
        sales_goal = int(projeto.capacidade_maxima) if projeto.capacidade_maxima else 1000
        avg_ticket = 150.0
        
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
        ultima_atualizacao=datetime.now(ZoneInfo('America/Sao_Paulo')).isoformat(),
        avisos=get_isc_warnings()
    )


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


@router.get("/eventos/{evento_id}")
def get_marketing_event_by_id(
    evento_id: str,
    ano: int = Query(default=None, description="Ano para evento consolidado"),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    """
    Retorna os dados de um evento específico pelo ID.
    Suporta IDs de EventoGrupo (prefixo 'grp_') e DimProjeto (número puro).
    """
    is_grouped = evento_id.startswith("grp_")
    
    if is_grouped:
        grupo_nome = evento_id.replace("grp_", "")
        grupo = db.query(EventoGrupoModel).filter(EventoGrupoModel.nome == grupo_nome).first()
        if not grupo:
            raise HTTPException(status_code=404, detail="Grupo de evento não encontrado")
        
        if ano is None:
            ano = datetime.now().year
        
        mappings = db.query(SkuMapping).filter(
            SkuMapping.evento_grupo == grupo_nome,
            SkuMapping.ano == ano,
            SkuMapping.ativo == True
        ).all()
        
        skus = [m.sku for m in mappings]
        isc_data = fetch_isc_pricing_data(db=db)
        
        current_sales = 0
        seen_norms = set()
        for s_sku in skus:
            s_norm = normalize_sku(s_sku)
            if s_norm in seen_norms:
                continue
            seen_norms.add(s_norm)
            info = isc_data.get(s_norm, {})
            current_sales += info.get('qtd_site', 0)
        
        proj_skus = [m.sku for m in mappings]
        projetos = db.query(DimProjeto).filter(
            DimProjeto.codigo.in_(proj_skus)
        ).all() if proj_skus else []
        
        total_capacity = 0
        latest_date = None
        rep_projeto = projetos[0] if projetos else None
        for p in projetos:
            if p.capacidade_maxima:
                total_capacity += int(p.capacidade_maxima)
            if p.data_evento:
                if latest_date is None or p.data_evento > latest_date:
                    latest_date = p.data_evento
                    rep_projeto = p
        
        projeto_data_evento = latest_date
        d_minus = calculate_d_minus(projeto_data_evento) if projeto_data_evento else 0
        is_active = d_minus > 0
        sales_goal = total_capacity if total_capacity > 0 else 1000
        avg_ticket = 150.0
        
        isc_components = calculate_isc_components(current_sales, sales_goal, d_minus)
        isc = calculate_isc(isc_components)
        isc_status = get_isc_status(isc)
        suggested_action = get_suggested_action(isc, d_minus)
        
        projeto_modalidade = str(rep_projeto.modalidade) if rep_projeto and rep_projeto.modalidade else None
        projeto_cidade = str(rep_projeto.cidade) if rep_projeto and rep_projeto.cidade else None
        projeto_estado = str(rep_projeto.estado) if rep_projeto and rep_projeto.estado else None
        
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
            dMinus=d_minus,
            isc=isc,
            iscComponents=isc_components,
            iscStatus=isc_status,
            suggestedAction=suggested_action,
            isActive=is_active,
            sku=",".join(skus)
        )
        
        daily_sales = generate_daily_sales_data(
            current_sales=current_sales,
            sales_goal=sales_goal,
            event_date=projeto_data_evento,
            days_history=60
        )
        
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
        mappings_anterior = db.query(SkuMapping).filter(
            SkuMapping.evento_grupo == grupo_nome,
            SkuMapping.ano == ano_anterior,
            SkuMapping.ativo == True
        ).all()
        
        comparacao_anual = None
        if mappings_anterior:
            skus_anterior = [m.sku for m in mappings_anterior]
            
            vendas_anterior = 0
            seen_norms_ant = set()
            for s_sku in skus_anterior:
                s_norm = normalize_sku(s_sku)
                if s_norm in seen_norms_ant:
                    continue
                seen_norms_ant.add(s_norm)
                info = isc_data.get(s_norm, {})
                vendas_anterior += info.get('qtd_site', 0)
            
            proj_skus_anterior = [m.sku for m in mappings_anterior]
            projetos_anterior = db.query(DimProjeto).filter(
                DimProjeto.codigo.in_(proj_skus_anterior)
            ).all() if proj_skus_anterior else []
            
            cap_anterior = sum(int(p.capacidade_maxima) for p in projetos_anterior if p.capacidade_maxima)
            meta_anterior = cap_anterior if cap_anterior > 0 else 1000
            ticket_anterior = 0
            
            variacao_vendas = ((current_sales - vendas_anterior) / vendas_anterior * 100) if vendas_anterior > 0 else None
            
            comparacao_anual = {
                "ano_atual": ano,
                "ano_anterior": ano_anterior,
                "atual": {
                    "vendas": current_sales,
                    "receita": 0,
                    "meta": sales_goal,
                    "ticket_medio": round(avg_ticket, 2),
                    "ocupacao_pct": round(current_sales / sales_goal * 100, 1) if sales_goal > 0 else 0
                },
                "anterior": {
                    "vendas": vendas_anterior,
                    "receita": 0,
                    "meta": meta_anterior,
                    "ticket_medio": round(ticket_anterior, 2),
                    "ocupacao_pct": round(vendas_anterior / meta_anterior * 100, 1) if meta_anterior > 0 else 0
                },
                "variacao": {
                    "vendas_pct": round(variacao_vendas, 1) if variacao_vendas is not None else None,
                    "receita_pct": None
                }
            }
        
        anos_disponiveis = db.query(SkuMapping.ano).filter(
            SkuMapping.evento_grupo == grupo_nome,
            SkuMapping.ativo == True
        ).distinct().order_by(SkuMapping.ano.desc()).all()
        
        return {
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
    
    projeto = db.query(DimProjeto).filter(DimProjeto.id == int(evento_id)).first()
    
    if not projeto:
        raise HTTPException(status_code=404, detail="Evento não encontrado")
    
    projeto_codigo = str(projeto.codigo) if projeto.codigo else None
    sku = projeto_codigo
    projeto_data_evento = projeto.data_evento
    d_minus = calculate_d_minus(projeto_data_evento) if projeto_data_evento else 0
    is_active = d_minus > 0
    
    if ano is None:
        ano = projeto_data_evento.year if projeto_data_evento else datetime.now().year
    isc_data = fetch_isc_pricing_data(db=db)
    
    sales_info = isc_data.get(normalize_sku(sku), {}) if sku else {}
    current_sales = sales_info.get('qtd_site', 0)
    
    sales_goal = int(projeto.capacidade_maxima) if projeto.capacidade_maxima else 1000
    avg_ticket = 150.0
    
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
        "ultima_atualizacao": datetime.now(ZoneInfo('America/Sao_Paulo')).isoformat(),
        "avisos": get_isc_warnings()
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
        SELECT /*+ MAX_EXECUTION_TIME(25000) */
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
    
    increment_filters = " ".join([
        f"AND so.increment_id NOT LIKE '%%-{i}%%'" for i in range(1, 18)
    ])
    
    try:
        query = f"""
        SELECT /*+ MAX_EXECUTION_TIME(25000) */
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
            {increment_filters}
            AND so.status IN ('Processing', 'Complete', 'approved')
            AND soi.product_type = 'Bundle'
            AND (so.discount_description IS NULL OR so.discount_description NOT LIKE '%%Grup%%')
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


_rolling_avg_executor = ThreadPoolExecutor(max_workers=2)

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
        magento_data = future_magento.result(timeout=30)
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
    
    query = db.query(DimProjeto).filter(
        DimProjeto.codigo.isnot(None),
        DimProjeto.codigo != ''
    )
    
    if categoria and categoria != 'all':
        query = query.filter(DimProjeto.modalidade == categoria)
    
    if busca:
        query = query.filter(DimProjeto.evento.ilike(f'%{busca}%'))
    
    projetos = query.all()
    
    isc_data = fetch_isc_pricing_data(db=db)
    
    projeto_ids = [p.id for p in projetos if p.id]
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
    
    for grupo_nome, proj_list in grupo_projetos.items():
        grupo = grupo_details[grupo_nome]
        
        total_capacity = 0
        latest_date = None
        rep_projeto = proj_list[0]
        total_kit_cost = 0.0
        kit_count = 0
        
        for p in proj_list:
            if p.capacidade_maxima:
                total_capacity += int(p.capacidade_maxima)
            if p.data_evento:
                if latest_date is None or p.data_evento > latest_date:
                    latest_date = p.data_evento
                    rep_projeto = p
            kc = kit_costs.get(p.id, 50.0)
            total_kit_cost += kc
            kit_count += 1
        
        projeto_data_evento = latest_date or rep_projeto.data_evento
        d_minus = calculate_d_minus(projeto_data_evento) if projeto_data_evento else 0
        is_active = d_minus > 0
        
        if status == 'active' and not is_active:
            continue
        if status == 'closed' and is_active:
            continue
        
        modalidade = rep_projeto.modalidade or 'OUTROS'
        categorias_set.add(modalidade)
        
        current_sales = 0
        combined_rolling_14d = 0.0
        combined_rolling_14d_ly = 0.0
        seen_pricing_norms = set()
        for p in proj_list:
            p_sku = normalize_sku(str(p.codigo)) if p.codigo else None
            if p_sku and p_sku not in seen_pricing_norms and p_sku in isc_data:
                seen_pricing_norms.add(p_sku)
                current_sales += isc_data[p_sku].get('qtd_site', 0)
                combined_rolling_14d += isc_data[p_sku].get('media_14d', 0.0)
                combined_rolling_14d_ly += isc_data[p_sku].get('media_14d_ano_passado', 0.0)
        
        average_ticket = 120.0
        sales_goal = total_capacity if total_capacity > 0 else 1000
        kit_cost = total_kit_cost / kit_count if kit_count > 0 else 50.0
        
        all_skus = [str(p.codigo) for p in proj_list if p.codigo]
        
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
        
        isc_components = calculate_isc_components(current_sales, sales_goal, d_minus)
        isc = calculate_isc(isc_components)
        isc_status = get_isc_status(isc)
        
        evento = PricingEvent(
            id=f"grp_{grupo_nome}",
            name=grupo.nome,
            date=projeto_data_evento.isoformat() if projeto_data_evento else "",
            location=rep_projeto.cidade or "Local não definido",
            category=modalidade,
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
        
        sku = projeto_codigo
        sku_normalized = normalize_sku(sku)
        projeto_data_evento = projeto.data_evento
        d_minus = calculate_d_minus(projeto_data_evento) if projeto_data_evento else 0
        is_active = d_minus > 0
        
        if status == 'active' and not is_active:
            continue
        if status == 'closed' and is_active:
            continue
        
        modalidade = projeto.modalidade or 'OUTROS'
        categorias_set.add(modalidade)
        
        sales_info = isc_data.get(sku_normalized, {})
        current_sales = sales_info.get('qtd_site', 0)
        
        average_ticket = 120.0
        total_capacity = projeto.capacidade_maxima or 10000
        sales_goal = int(projeto.capacidade_maxima) if projeto.capacidade_maxima else 1000
        
        kit_cost = kit_costs.get(projeto.id, 50.0)
        
        rolling_avg_14d_real = sales_info.get('media_14d', None)
        rolling_avg_14d_last_year = sales_info.get('media_14d_ano_passado', 0.0)
        
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
        
        isc_components = calculate_isc_components(current_sales, sales_goal, d_minus)
        isc = calculate_isc(isc_components)
        isc_status = get_isc_status(isc)
        
        evento = PricingEvent(
            id=sku,
            name=projeto.evento or f"Evento {sku}",
            date=projeto_data_evento.isoformat() if projeto_data_evento else "",
            location=projeto.cidade or "Local não definido",
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
