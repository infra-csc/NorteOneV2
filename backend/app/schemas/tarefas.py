from pydantic import BaseModel, field_validator
from typing import Optional, Union
from datetime import datetime
from enum import Enum


class PrioridadeTarefa(str, Enum):
    BAIXA = "BAIXA"
    MEDIA = "MEDIA"
    ALTA = "ALTA"
    URGENTE = "URGENTE"


class StatusTarefa(str, Enum):
    PENDENTE = "PENDENTE"
    EM_ANDAMENTO = "EM_ANDAMENTO"
    CONCLUIDA = "CONCLUIDA"
    CANCELADA = "CANCELADA"


class TarefaBase(BaseModel):
    titulo: str
    descricao: Optional[str] = None
    data_vencimento: Optional[Union[datetime, str]] = None
    hora_lembrete: Optional[Union[datetime, str]] = None
    prioridade: PrioridadeTarefa = PrioridadeTarefa.MEDIA
    
    @field_validator('data_vencimento', 'hora_lembrete', mode='before')
    @classmethod
    def parse_datetime(cls, v):
        if v is None or v == '':
            return None
        if isinstance(v, datetime):
            return v
        if isinstance(v, str):
            formats = [
                '%Y-%m-%dT%H:%M:%S.%fZ',
                '%Y-%m-%dT%H:%M:%S.%f',
                '%Y-%m-%dT%H:%M:%SZ',
                '%Y-%m-%dT%H:%M:%S',
                '%Y-%m-%dT%H:%M',
                '%Y-%m-%d',
            ]
            for fmt in formats:
                try:
                    return datetime.strptime(v, fmt)
                except ValueError:
                    continue
            try:
                return datetime.fromisoformat(v.replace('Z', '+00:00'))
            except ValueError:
                raise ValueError(f"Formato de data inválido: {v}")
        return v


class TarefaCreate(TarefaBase):
    criado_por_nori: bool = False
    responsavel_id: Optional[int] = None


class TarefaUpdate(BaseModel):
    titulo: Optional[str] = None
    descricao: Optional[str] = None
    data_vencimento: Optional[datetime] = None
    hora_lembrete: Optional[datetime] = None
    prioridade: Optional[PrioridadeTarefa] = None
    status: Optional[StatusTarefa] = None


class UsuarioInfo(BaseModel):
    id: int
    nome: str
    email: str
    
    class Config:
        from_attributes = True


class TarefaResponse(TarefaBase):
    id: int
    status: StatusTarefa
    criado_por_nori: bool
    usuario_id: int
    responsavel_id: Optional[int] = None
    responsavel: Optional[UsuarioInfo] = None
    usuario: Optional[UsuarioInfo] = None
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True
