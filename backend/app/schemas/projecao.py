from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class AreaProjecaoResponse(BaseModel):
    id: int
    nome: str
    ativo: bool
    usa_cutoff_customizado: bool = False
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class AreaProjecaoUsuarioResponse(BaseModel):
    id: int
    area_projecao_id: int
    usuario_id: int
    usuario_nome: Optional[str] = None
    usuario_email: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class AreaProjecaoDetailResponse(AreaProjecaoResponse):
    usuarios: List[AreaProjecaoUsuarioResponse] = []

    class Config:
        from_attributes = True


class AreaProjecaoCreate(BaseModel):
    nome: str


class AreaProjecaoUsuarioCreate(BaseModel):
    area_projecao_id: int
    usuario_id: int


class AreaProjecaoUsuarioBulk(BaseModel):
    area_projecao_id: int
    usuario_ids: List[int]


class ClienteProjecaoItem(BaseModel):
    nome_cliente: str
    quantidade: int


class ClienteProjecaoResponse(BaseModel):
    id: int
    projecao_id: int
    nome_cliente: str
    quantidade: int
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class KitProjecaoItem(BaseModel):
    nome_kit: str
    quantidade: int


class KitProjecaoResponse(BaseModel):
    id: int
    projecao_id: int
    nome_kit: str
    quantidade: int
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ProjecaoInscritosCreate(BaseModel):
    evento_id: int
    area_projecao_id: int
    quantidade: int
    clientes: Optional[List[ClienteProjecaoItem]] = None
    kits: Optional[List[KitProjecaoItem]] = None


class ProjecaoInscritosUpdate(BaseModel):
    quantidade: int
    clientes: Optional[List[ClienteProjecaoItem]] = None
    kits: Optional[List[KitProjecaoItem]] = None


class ProjecaoInscritosResponse(BaseModel):
    id: int
    evento_id: int
    evento_nome: Optional[str] = None
    evento_data: Optional[str] = None
    evento_tipo: Optional[str] = None
    evento_modalidade: Optional[str] = None
    area_projecao_id: int
    area_projecao_nome: Optional[str] = None
    quantidade: int
    clientes: List[ClienteProjecaoResponse] = []
    kits: List[KitProjecaoResponse] = []
    created_by: int
    created_by_nome: Optional[str] = None
    updated_by: Optional[int] = None
    updated_by_nome: Optional[str] = None
    locked_at: Optional[datetime] = None
    locked_by_nome: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    deleted_at: Optional[datetime] = None
    deleted_by_nome: Optional[str] = None

    class Config:
        from_attributes = True


class HistoricoResponse(BaseModel):
    id: int
    projecao_id: int
    acao: str
    campo_alterado: Optional[str] = None
    valor_anterior: Optional[str] = None
    valor_novo: Optional[str] = None
    usuario_id: int
    usuario_nome: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ConsolidadoAreaItem(BaseModel):
    area_projecao_id: int
    area_projecao_nome: str
    quantidade: int


class ConsolidadoEventoResponse(BaseModel):
    evento_id: int
    evento_nome: str
    evento_data: Optional[str] = None
    inscritos_reais: int
    projecoes: List[ConsolidadoAreaItem]
    total_projecoes: int
    projecao_site: int = 0
    total_geral: int


class CutoffRuleCreate(BaseModel):
    nome: str
    dias_antes_evento: int
    ativo: Optional[bool] = True


class CutoffRuleUpdate(BaseModel):
    nome: Optional[str] = None
    dias_antes_evento: Optional[int] = None
    ativo: Optional[bool] = None


class CutoffRuleResponse(BaseModel):
    id: int
    nome: str
    dias_antes_evento: int
    ativo: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class AreaPendenteItem(BaseModel):
    area_projecao_id: int
    area_projecao_nome: str


class PendenciaItem(BaseModel):
    evento_id: int
    evento_nome: str
    evento_data: Optional[str] = None
    dias_ate_evento: int
    cutoff_dias: int
    cutoff_nome: str
    cutoff_customizado: bool = False
    cutoff_data: Optional[str] = None
    areas_pendentes: List[AreaPendenteItem]


class PendenciasResponse(BaseModel):
    total_eventos: int
    total_areas: int
    pendencias: List[PendenciaItem]


class AreaCutoffCustomizadoToggle(BaseModel):
    ativo: bool


class CutoffEventoAreaUpsert(BaseModel):
    evento_id: int
    area_projecao_id: int
    data_corte_1: Optional[str] = None  # ISO date YYYY-MM-DD
    data_corte_2: Optional[str] = None


class CutoffEventoAreaResponse(BaseModel):
    id: int
    evento_id: int
    area_projecao_id: int
    area_projecao_nome: Optional[str] = None
    data_corte_1: Optional[str] = None
    data_corte_2: Optional[str] = None
    updated_by: Optional[int] = None
    updated_by_nome: Optional[str] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class AutoLockConfigUpdate(BaseModel):
    dias_antes_evento: int
    ativo: bool


class AutoLockConfigResponse(BaseModel):
    dias_antes_evento: int
    ativo: bool
    updated_by_nome: Optional[str] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

