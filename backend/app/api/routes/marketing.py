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
from .inscricoes_consolidado import normalize_sku
import logging
import asyncio
from concurrent.futures import ThreadPoolExecutor
import httpx

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
    
    return {
        "status": "success",
        "evento": evento,
        "ultima_atualizacao": datetime.now().isoformat()
    }
