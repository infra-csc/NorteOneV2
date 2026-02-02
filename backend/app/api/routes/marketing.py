from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional, List
from pydantic import BaseModel
from datetime import datetime, date
from ...core.database import get_db, engine_ativo, engine_ssh
from ...core.security import get_current_user
from ...models.dimensoes import DimProjeto
from ...models.user import Usuario
import logging
import asyncio
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

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

def fetch_consolidated_sales_by_skus(skus: List[str], ano: int) -> dict:
    """
    Busca vendas consolidadas (Ativo + Magento) para uma lista de SKUs.
    Retorna dict com SKU como chave.
    """
    sales_by_sku = {}
    
    if not skus:
        return sales_by_sku
    
    sku_list_str = ", ".join([f"'{sku}'" for sku in skus])
    
    if engine_ativo:
        try:
            query_ativo = f"""
            SELECT
                CASE 
                    WHEN b.id_evento = '40048' THEN 'CDE26PL1'
                    WHEN b.id_evento = '40145' THEN 'CDE26RP1'
                    WHEN b.id_evento = '39969' THEN 'CDE26RJ1'
                    WHEN b.id_evento = '40120' THEN 'CDE26FL1'
                    WHEN b.id_evento = '39996' THEN 'CDE26PA1'
                    WHEN b.id_evento = '39964' THEN 'CDE26SP1'
                    WHEN b.id_evento = '40052' THEN 'CDE26AN1'
                    WHEN b.id_evento = '39974' THEN 'CDE26BH1'
                    WHEN b.id_evento = '39970' THEN 'CDE26BS1'
                    WHEN b.id_evento = '40001' THEN 'CDE26CP1'
                    WHEN b.id_evento = '39986' THEN 'CDE26RC1'
                    WHEN b.id_evento = '40010' THEN 'CDE26BL1'
                    WHEN b.id_evento = '39980' THEN 'CDE26FT1'
                    WHEN b.id_evento = '40149' THEN 'CDE26SJ1'
                    WHEN b.id_evento = '39994' THEN 'CDE26CT1'
                    WHEN b.id_evento = '40157' THEN 'CDE26TS1'
                    WHEN b.id_evento = '40015' THEN 'CDE26VT1'
                    WHEN b.id_evento = '40144' THEN 'CDE26MN4'
                    WHEN b.id_evento = '40142' THEN 'CDE26MN2'
                    WHEN b.id_evento = '40143' THEN 'CDE26MN3'
                    WHEN b.id_evento = '39990' THEN 'CDE26SV1'
                    WHEN b.id_evento = '40075' THEN 'TBT26ST1'
                    WHEN b.id_evento = '40108' THEN 'NRU26RF1'
                    WHEN b.id_evento = '40073' THEN 'BRV26SP4'
                    WHEN b.id_evento = '39999' THEN 'CDE26PA2'
                    WHEN b.id_evento = '39971' THEN 'CDE26RJ2'
                    WHEN b.id_evento = '40122' THEN 'CDE26FL3'
                    WHEN b.id_evento = '40121' THEN 'CDE26FL2'
                    WHEN b.id_evento = '40076' THEN 'TBT26ST2'
                    WHEN b.id_evento = '40049' THEN 'CDE26PL2'
                    WHEN b.id_evento = '40158' THEN 'CDE26TS2'
                    WHEN b.id_evento = '40072' THEN 'BRV26SP2'
                    WHEN b.id_evento = '40150' THEN 'CDE26SJ2'
                    WHEN b.id_evento = '40151' THEN 'CDE26SJ3'
                    WHEN b.id_evento = '40146' THEN 'CDE26RP2'
                    WHEN b.id_evento = '40053' THEN 'CDE26AN2'
                    WHEN b.id_evento = '40003' THEN 'CDE26CP2'
                    WHEN b.id_evento = '39987' THEN 'CDE26RC2'
                    WHEN b.id_evento = '39965' THEN 'CDE26SP2'
                    WHEN b.id_evento = '39975' THEN 'CDE26BS2'
                    WHEN b.id_evento = '39982' THEN 'CDE26FT2'
                    WHEN b.id_evento = '40107' THEN 'NRU26CW1'
                    WHEN b.id_evento = '40074' THEN 'BRV26SJ1'
                    WHEN b.id_evento = '39995' THEN 'CDE26CT2'
                    WHEN b.id_evento = '40016' THEN 'CDE26VT2'
                    WHEN b.id_evento = '39991' THEN 'CDE26SV2'
                    WHEN b.id_evento = '40011' THEN 'CDE26BL2'
                    WHEN b.id_evento = '40148' THEN 'CDE26RP4'
                    WHEN b.id_evento = '40116' THEN 'SOL26SP1'
                    WHEN b.id_evento = '40117' THEN 'SOL26RJ1'
                    WHEN b.id_evento = '40118' THEN 'SOL26BH1'
                    WHEN b.id_evento = '40119' THEN 'SOL26RS1'
                    WHEN b.id_evento = '40113' THEN 'SOL26CT1'
                    WHEN b.id_evento = '40109' THEN 'NRU26FT1'
                    WHEN b.id_evento = '40110' THEN 'NRU26FT2'
                    WHEN b.id_evento = '40111' THEN 'NRU26FT3'
                    WHEN b.id_evento = '40112' THEN 'NRU26DT1'
                    ELSE NULL
                END AS sku,
                COUNT(*) as qtd,
                COALESCE(SUM(bc.vlr_inscricao), 0) as valor
            FROM boleto b
            LEFT JOIN boleto_complemento bc ON b.id_boleto = bc.id_boleto
            WHERE b.excluido = 0 
              AND b.id_status IN (1, 4)
              AND YEAR(b.dt_evento) = {ano}
            GROUP BY sku
            HAVING sku IN ({sku_list_str})
            """
            
            with engine_ativo.connect() as conn:
                result = conn.execute(text(query_ativo))
                for row in result.fetchall():
                    sku = row[0]
                    if sku:
                        sales_by_sku[sku] = {
                            'qtd_ativo': int(row[1] or 0),
                            'valor_ativo': float(row[2] or 0),
                            'qtd_magento': 0,
                            'valor_magento': 0
                        }
        except Exception as e:
            logger.error(f"Erro ao buscar dados Ativo: {e}")
    
    if engine_ssh:
        try:
            query_magento = f"""
            SELECT
                CASE 
                    WHEN oli.location_id = 587 THEN 'CPLIE26SP1'
                    WHEN oli.location_id = 612 THEN 'BLU26RJ1'
                    WHEN oli.location_id = 613 THEN 'BLU26SP1'
                    WHEN oli.location_id = 645 THEN 'CDE26MN2'
                    WHEN oli.location_id = 647 THEN 'CDE26MN3'
                    WHEN oli.location_id = 646 THEN 'CDE26MN4'
                    WHEN oli.location_id = 648 THEN 'NRU26FT1'
                    WHEN oli.location_id = 649 THEN 'NRU26FT2'
                    WHEN oli.location_id = 650 THEN 'NRU26FT3'
                    WHEN oli.location_id = 651 THEN 'NRU26DT1'
                    WHEN oli.location_id = 652 THEN 'NRU26CW1'
                    WHEN oli.location_id = 653 THEN 'NRU26RF1'
                    WHEN oli.location_id = 654 THEN 'SOL26SP1'
                    WHEN oli.location_id = 655 THEN 'SOL26RJ1'
                    WHEN oli.location_id = 656 THEN 'SOL26BH1'
                    WHEN oli.location_id = 657 THEN 'SOL26RS1'
                    WHEN oli.location_id = 658 THEN 'SOL26CT1'
                    ELSE cpe.sku
                END AS sku,
                COUNT(DISTINCT o.entity_id) as qtd,
                COALESCE(SUM(oi.row_total), 0) as valor
            FROM sales_order o
            JOIN sales_order_item oi ON o.entity_id = oi.order_id
            LEFT JOIN amasty_amlocator_order_location_item oli ON oi.item_id = oli.order_item_id
            LEFT JOIN catalog_product_entity cpe ON oi.product_id = cpe.entity_id
            WHERE o.status IN ('complete', 'processing')
              AND YEAR(o.created_at) >= {ano - 1}
            GROUP BY sku
            HAVING sku IN ({sku_list_str})
            """
            
            with engine_ssh.connect() as conn:
                result = conn.execute(text(query_magento))
                for row in result.fetchall():
                    sku = row[0]
                    if sku:
                        if sku in sales_by_sku:
                            sales_by_sku[sku]['qtd_magento'] = int(row[1] or 0)
                            sales_by_sku[sku]['valor_magento'] = float(row[2] or 0)
                        else:
                            sales_by_sku[sku] = {
                                'qtd_ativo': 0,
                                'valor_ativo': 0,
                                'qtd_magento': int(row[1] or 0),
                                'valor_magento': float(row[2] or 0)
                            }
        except Exception as e:
            logger.error(f"Erro ao buscar dados Magento: {e}")
    
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
        query = query.filter(DimProjeto.nome.ilike(f'%{busca}%'))
    
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
