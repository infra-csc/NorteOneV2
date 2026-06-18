"""
Endpoint: Detalhamento de Eventos (grão fino por Canal/Kit/Distância/Modalidade/Pelotão/Produtos/Tamanho).

GET /api/marketing/detalhe-eventos/eventos  → lista de eventos disponíveis (de sku_mappings)
GET /api/marketing/detalhe-eventos          → dados consolidados para um evento_grupo
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional

from app.core.database import get_db
from app.core.security import get_current_user
from app.services.detalhe_eventos_service import (
    list_eventos_disponiveis,
    get_detalhe,
)

router = APIRouter(
    prefix="/api/marketing/detalhe-eventos",
    tags=["Detalhe Eventos"],
    dependencies=[Depends(get_current_user)],
)


@router.get("/eventos")
def get_eventos_disponiveis(
    db: Session = Depends(get_db),
):
    """
    Lista todos os evento_grupos disponíveis em sku_mappings,
    com nome amigável e IDs de Ativo/Magento.
    Usado para popular o seletor de evento no frontend.
    """
    return list_eventos_disponiveis(db)


@router.get("")
def get_detalhe_evento(
    evento_grupo: Optional[str] = Query(None, description="Chave canônica do evento (evento_grupo do sku_mappings)"),
    force_refresh: bool = Query(False, description="Ignorar cache e re-executar as queries"),
    db: Session = Depends(get_db),
):
    """
    Retorna o detalhamento consolidado de inscrições para um evento.

    Resposta:
    - consolidado: linhas agregadas por [canal, kit, distancia, modalidade, pelotao, produtos, tamanho_camiseta]
    - por_banco: { Ativo: [...], Magento: [...] } — raw rows para auditoria
    - divergencias: combinações onde a soma por banco diverge do total consolidado
    - erros: erros por banco (se alguma query falhou)
    - totais: KPI summary (inscritos, receita_bruta, receita_liquida, ticket_medio, por_canal)
    """
    return get_detalhe(db, evento_grupo, force_refresh=force_refresh)
