from pydantic import BaseModel
from typing import Optional, List
from datetime import date, datetime
from decimal import Decimal

class CentroCustoBase(BaseModel):
    codigo: str
    nome: str
    area: Optional[str] = None
    gestor_responsavel: Optional[str] = None
    ativo: bool = True

class CentroCustoCreate(CentroCustoBase):
    pass

class CentroCustoUpdate(BaseModel):
    codigo: Optional[str] = None
    nome: Optional[str] = None
    area: Optional[str] = None
    gestor_responsavel: Optional[str] = None
    ativo: Optional[bool] = None

class CentroCustoResponse(CentroCustoBase):
    id: int
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class ProjetoBase(BaseModel):
    codigo: str
    produto: str
    modalidade: str
    tipo_evento: str
    evento: str
    lei: str
    cliente: Optional[str] = None
    status: str
    data_evento: date
    local_evento: str
    cidade: Optional[str] = None
    estado: Optional[str] = None
    capacidade_maxima: Optional[int] = None
    etapa: Optional[int] = None
    imagem_kv: Optional[str] = None

class ProjetoCreate(ProjetoBase):
    pass

class ProjetoUpdate(BaseModel):
    codigo: Optional[str] = None
    produto: Optional[str] = None
    modalidade: Optional[str] = None
    tipo_evento: Optional[str] = None
    evento: Optional[str] = None
    lei: Optional[str] = None
    cliente: Optional[str] = None
    status: Optional[str] = None
    data_evento: Optional[date] = None
    local_evento: Optional[str] = None
    cidade: Optional[str] = None
    estado: Optional[str] = None
    capacidade_maxima: Optional[int] = None
    etapa: Optional[int] = None
    imagem_kv: Optional[str] = None

class ProjetoResponse(ProjetoBase):
    id: int
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class CategoriaAtletaBase(BaseModel):
    codigo: str
    nome: str
    faixa_etaria: Optional[str] = None
    genero: Optional[str] = None
    modalidade: Optional[str] = None
    is_pcd: bool = False
    valor_inscricao_padrao: Optional[Decimal] = None
    custo_kit_padrao: Optional[Decimal] = None
    ativo: bool = True

class CategoriaAtletaCreate(CategoriaAtletaBase):
    pass

class CategoriaAtletaUpdate(BaseModel):
    codigo: Optional[str] = None
    nome: Optional[str] = None
    faixa_etaria: Optional[str] = None
    genero: Optional[str] = None
    modalidade: Optional[str] = None
    is_pcd: Optional[bool] = None
    valor_inscricao_padrao: Optional[Decimal] = None
    custo_kit_padrao: Optional[Decimal] = None
    ativo: Optional[bool] = None

class CategoriaAtletaResponse(CategoriaAtletaBase):
    id: int
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class TempoBase(BaseModel):
    data: date
    dia: Optional[int] = None
    mes: Optional[int] = None
    trimestre: Optional[int] = None
    semestre: Optional[int] = None
    ano: Optional[int] = None
    dia_semana: Optional[str] = None
    nome_mes: Optional[str] = None
    is_feriado: bool = False

class TempoResponse(TempoBase):
    id: int

    class Config:
        from_attributes = True


class EventoConsolidadoBase(BaseModel):
    nome: str
    descricao: Optional[str] = None
    ativo: bool = True

class EventoConsolidadoCreate(EventoConsolidadoBase):
    pass

class EventoConsolidadoUpdate(BaseModel):
    nome: Optional[str] = None
    descricao: Optional[str] = None
    ativo: Optional[bool] = None

class EventoConsolidadoResponse(EventoConsolidadoBase):
    id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class EventoConsolidadoDetailResponse(EventoConsolidadoResponse):
    mapeamentos: List["SkuMappingResponse"] = []

    class Config:
        from_attributes = True


class EventoGrupoBase(BaseModel):
    nome: str
    descricao: Optional[str] = None
    ativo: bool = True

class EventoGrupoCreate(EventoGrupoBase):
    pass

class EventoGrupoUpdate(BaseModel):
    nome: Optional[str] = None
    descricao: Optional[str] = None
    ativo: Optional[bool] = None

class EventoGrupoResponse(EventoGrupoBase):
    id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class SkuMappingBase(BaseModel):
    fonte: str
    id_externo: int
    sku: str
    evento_grupo: Optional[str] = None
    ano: int
    nome_evento: str
    ativo: bool = True
    evento_consolidado_id: Optional[int] = None
    data_evento: Optional[date] = None

class SkuMappingCreate(SkuMappingBase):
    pass

class SkuMappingUpdate(BaseModel):
    fonte: Optional[str] = None
    id_externo: Optional[int] = None
    sku: Optional[str] = None
    evento_grupo: Optional[str] = None
    ano: Optional[int] = None
    nome_evento: Optional[str] = None
    ativo: Optional[bool] = None
    evento_consolidado_id: Optional[int] = None
    data_evento: Optional[date] = None

class SkuMappingResponse(SkuMappingBase):
    id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
