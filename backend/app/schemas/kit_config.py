from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class KitConfigUpsert(BaseModel):
    multiplicador: int = Field(default=1, ge=1, le=100)
    is_kit_basico: bool = False
    id_evento: Optional[int] = None


class KitConfigResponse(BaseModel):
    bundle_entity_id: int
    id_evento: Optional[int] = None
    kit_nome: Optional[str] = None
    tipo: str = "multiplier"
    multiplicador: int = 1
    is_kit_basico: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class KitRow(BaseModel):
    id_evento: Optional[str] = None
    nome_evento: Optional[str] = None
    bundle_entity_id: int
    nome_kit: Optional[str] = None
    lote_atual: Optional[str] = None
    preco_lote: Optional[float] = None
    lote_termina_em: Optional[str] = None
    preco_adicional_kit: Optional[float] = None
    ticket_base: Optional[float] = None
    distancias: Optional[str] = None
    multiplicador: int = 1
    ticket_final: Optional[float] = None
    is_configured: bool = False
    is_kit_basico: bool = False
