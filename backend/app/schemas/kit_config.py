from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class KitConfigUpsert(BaseModel):
    multiplicador: int = Field(default=1, ge=1, le=100)
    is_kit_basico: bool = False
    id_evento: Optional[int] = None
    tipo_kit: Optional[str] = None
    custo_kit: Optional[float] = None


class KitConfigResponse(BaseModel):
    bundle_entity_id: int
    id_evento: Optional[int] = None
    kit_nome: Optional[str] = None
    tipo_kit: Optional[str] = None
    tipo: str = "multiplier"
    multiplicador: int = 1
    is_kit_basico: bool = False
    custo_kit: Optional[float] = None
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
    custo_cadastro: Optional[float] = None
    custo_kit: Optional[float] = None
