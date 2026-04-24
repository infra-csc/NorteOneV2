from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class AreaProjecaoResponse(BaseModel):
    id: int
    nome: str
    ativo: bool
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


class ProjecaoInscritosCreate(BaseModel):
    evento_id: int
    area_projecao_id: int
    quantidade: int


class ProjecaoInscritosUpdate(BaseModel):
    quantidade: int


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
    created_by: int
    created_by_nome: Optional[str] = None
    updated_by: Optional[int] = None
    updated_by_nome: Optional[str] = None
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
    total_geral: int
