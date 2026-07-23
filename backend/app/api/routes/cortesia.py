"""Rotas proxy autenticadas para o app externo de Cortesias.

O token da integração vive apenas no backend (secret CORTESIA_API_TOKEN).
As rotas exigem a mesma permissão de visualização do módulo Projeção de
Inscritos, já que o painel de Cortesias é exibido dentro dessa tela.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from ...core.security import require_permission
from ...models.user import Usuario
from ...services import cortesia_service

router = APIRouter(prefix="/cortesia", tags=["Cortesias"])

PROJECAO_PERMISSION = "projecao_inscritos"


@router.get("/metrics")
def get_cortesia_metrics(
    sku: Optional[str] = Query(None),
    user_id: Optional[str] = Query(None, alias="userId"),
    area: Optional[str] = Query(None),
    current_user: Usuario = Depends(require_permission(PROJECAO_PERMISSION, "pode_visualizar")),
):
    filtros = [("sku", sku), ("userId", user_id), ("area", area)]
    informados = [(t, v) for t, v in filtros if v is not None and v.strip()]
    if len(informados) != 1:
        raise HTTPException(
            status_code=400,
            detail="Informe exatamente um filtro: sku, userId ou area.",
        )
    tipo, valor = informados[0]
    return cortesia_service.get_metrics(tipo, valor)


@router.get("/users")
def get_cortesia_users(
    current_user: Usuario = Depends(require_permission(PROJECAO_PERMISSION, "pode_visualizar")),
):
    return cortesia_service.get_users()
