"""
Endpoint: Detalhamento de Eventos (grão fino por Canal/Kit/Distância/Modalidade/Pelotão/Produtos/Tamanho).

GET /api/marketing/detalhe-eventos/eventos  → lista de eventos disponíveis (de sku_mappings)
GET /api/marketing/detalhe-eventos          → dados consolidados para um evento_grupo/ano
"""
import copy
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from typing import Optional

from app.core.database import get_db
from app.core.security import require_permission, get_current_user
from app.models.user import Usuario
from app.services.detalhe_eventos_service import (
    list_eventos_disponiveis,
    get_detalhe,
    get_anos_evento,
    resolve_ano_padrao,
)

router = APIRouter(
    prefix="/api/marketing/detalhe-eventos",
    tags=["Detalhe Eventos"],
    dependencies=[Depends(require_permission("marketing_detalhe", "pode_visualizar"))],
)

# Campos monetários removidos da resposta quando o usuário não tem a permissão
# de campo "Dados Financeiros" (entidade=marketing_detalhe). Mantém inscritos
# e demais dimensões intactos — só o dinheiro é ocultado.
_REVENUE_ROW_KEYS = ("receita_bruta", "receita_liquida", "ticket_medio")
_REVENUE_DIVERGENCIA_KEYS = (
    "consolidado_receita_liquida",
    "soma_bancos_receita_liquida",
    "diff_receita_liquida",
)


def _user_can_view_financeiro(db: Session, user: Usuario) -> bool:
    from app.api.routes.dashboard import user_can_view_campo
    return user_can_view_campo(db, user, "marketing_detalhe", "dados_financeiros")


def _redact_receita(payload: dict) -> dict:
    """
    Retorna uma CÓPIA do payload sem nenhum campo de receita/ticket médio.
    Nunca muta o payload original — ele pode ser o mesmo objeto guardado no
    cache em memória / usado para montar o snapshot, compartilhado entre
    todos os usuários (com e sem permissão financeira).
    """
    redacted = copy.deepcopy(payload)

    for row in redacted.get("consolidado") or []:
        for k in _REVENUE_ROW_KEYS:
            row.pop(k, None)

    por_banco = redacted.get("por_banco") or {}
    for banco_rows in por_banco.values():
        for row in banco_rows or []:
            for k in _REVENUE_ROW_KEYS:
                row.pop(k, None)

    for div in redacted.get("divergencias") or []:
        for k in _REVENUE_DIVERGENCIA_KEYS:
            div.pop(k, None)

    totais = redacted.get("totais") or {}
    for k in _REVENUE_ROW_KEYS:
        totais.pop(k, None)
    for canal_data in (totais.get("por_canal") or {}).values():
        if isinstance(canal_data, dict):
            canal_data.pop("receita_liquida", None)

    redacted["financeiro_oculto"] = True
    return redacted


@router.get("/eventos")
def get_eventos_disponiveis(
    db: Session = Depends(get_db),
):
    """
    Lista todos os evento_grupos disponíveis em sku_mappings,
    com nome amigável, anos cadastrados e IDs de Ativo/Magento por ano.
    Usado para popular o seletor de evento no frontend.
    """
    return list_eventos_disponiveis(db)


@router.get("")
def get_detalhe_evento(
    evento_grupo: Optional[str] = Query(None, description="Chave canônica do evento (evento_grupo do sku_mappings)"),
    ano: Optional[int] = Query(None, description="Ano da edição do evento. Se omitido, usa o ano corrente (ou o mais recente cadastrado)"),
    force_refresh: bool = Query(False, description="Ignorar cache e re-executar as queries"),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """
    Retorna o detalhamento consolidado de inscrições para uma edição de evento.

    Resposta:
    - consolidado: linhas agregadas por [canal, kit, modalidade, pelotao, produtos, tamanho_camiseta]
    - por_banco: { Ativo: [...], Magento: [...] } — raw rows para auditoria
    - divergencias: combinações onde a soma por banco diverge do total consolidado
    - erros: erros por banco (se alguma query falhou)
    - totais: KPI summary (inscritos, receita_bruta, receita_liquida, ticket_medio, por_canal)

    Usuários sem a permissão de campo "Dados Financeiros" (marketing_detalhe/
    dados_financeiros) recebem a mesma resposta com todo campo de receita e
    ticket médio removido — só inscritos.
    """
    ano_efetivo = ano
    if evento_grupo and ano_efetivo is None:
        anos_disponiveis = get_anos_evento(db, evento_grupo)
        ano_efetivo = resolve_ano_padrao(anos_disponiveis)
        if ano_efetivo is None:
            raise HTTPException(
                status_code=404,
                detail=f"evento_grupo '{evento_grupo}' não encontrado ou sem mapeamentos ativos em sku_mappings.",
            )

    payload = get_detalhe(db, evento_grupo, ano_efetivo, force_refresh=force_refresh)

    if not _user_can_view_financeiro(db, current_user):
        payload = _redact_receita(payload)

    return payload
