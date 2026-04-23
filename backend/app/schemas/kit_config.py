from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class KitConfigUpsert(BaseModel):
    multiplicador: int = Field(default=1, ge=1, le=100)
    is_kit_basico: bool = False
    is_promo_principal: bool = False
    id_evento: Optional[int] = None
    tipo_kit: Optional[str] = None
    custo_kit: Optional[float] = None
    ativo_categoria: Optional[str] = None
    cenario_ciclismo: Optional[str] = None
    ignorado: bool = False


class KitConfigBulkItem(BaseModel):
    bundle_entity_id: int
    multiplicador: int = Field(default=1, ge=1, le=100)
    is_kit_basico: bool = False
    is_promo_principal: bool = False
    id_evento: Optional[int] = None
    tipo_kit: Optional[str] = None
    custo_kit: Optional[float] = None
    ativo_categoria: Optional[str] = None
    cenario_ciclismo: Optional[str] = None
    ignorado: bool = False


class KitConfigBulkUpsert(BaseModel):
    items: List[KitConfigBulkItem]


class KitConfigBulkResult(BaseModel):
    saved: int
    errors: int


class KitConfigResponse(BaseModel):
    bundle_entity_id: int
    id_evento: Optional[int] = None
    kit_nome: Optional[str] = None
    tipo_kit: Optional[str] = None
    tipo: str = "multiplier"
    multiplicador: int = 1
    is_kit_basico: bool = False
    is_promo_principal: bool = False
    custo_kit: Optional[float] = None
    ativo_categoria: Optional[str] = None
    cenario_ciclismo: Optional[str] = None
    ignorado: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class KitRow(BaseModel):
    id_evento: Optional[str] = None
    nome_evento: Optional[str] = None
    bundle_entity_id: int
    nome_kit: Optional[str] = None
    tipo_kit: Optional[str] = None
    tipo_categoria: Optional[str] = None
    lote_atual: Optional[str] = None
    multiplicador_sugerido: int = 1
    multiplicador: int = 1
    price_base: Optional[float] = None
    special_price_base: Optional[float] = None
    price: Optional[float] = None
    special_price: Optional[float] = None
    is_configured: bool = False
    is_kit_basico: bool = False
    is_promo_principal: bool = False
    custo_cadastro: Optional[float] = None
    custo_kit: Optional[float] = None
    ativo_categoria: Optional[str] = None
    cenario_ciclismo: Optional[str] = None
    ignorado: bool = False
    status_kit: Optional[str] = None
    fonte: Optional[str] = None
