from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, Enum, Text
from sqlalchemy.orm import relationship
from app.core.database import Base
from datetime import datetime
from zoneinfo import ZoneInfo
import enum


def get_brasilia_now():
    return datetime.now(ZoneInfo('America/Sao_Paulo')).replace(tzinfo=None)


class PrioridadeTarefa(str, enum.Enum):
    BAIXA = "BAIXA"
    MEDIA = "MEDIA"
    ALTA = "ALTA"
    URGENTE = "URGENTE"


class StatusTarefa(str, enum.Enum):
    PENDENTE = "PENDENTE"
    EM_ANDAMENTO = "EM_ANDAMENTO"
    CONCLUIDA = "CONCLUIDA"
    CANCELADA = "CANCELADA"


class Tarefa(Base):
    __tablename__ = "tarefas"
    
    id = Column(Integer, primary_key=True, index=True)
    titulo = Column(String(255), nullable=False)
    descricao = Column(String(1000), nullable=True)
    data_vencimento = Column(DateTime, nullable=True, index=True)
    hora_lembrete = Column(DateTime, nullable=True)
    prioridade = Column(Enum(PrioridadeTarefa), default=PrioridadeTarefa.MEDIA, index=True)
    status = Column(Enum(StatusTarefa), default=StatusTarefa.PENDENTE, index=True)
    criado_por_nori = Column(Boolean, default=False)
    usuario_id = Column(Integer, ForeignKey("dim_usuario.id"), nullable=False, index=True)
    responsavel_id = Column(Integer, ForeignKey("dim_usuario.id"), nullable=True, index=True)
    dados_analise = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=get_brasilia_now, index=True)
    updated_at = Column(DateTime, default=get_brasilia_now, onupdate=get_brasilia_now)
    
    usuario = relationship("Usuario", foreign_keys=[usuario_id], backref="tarefas_criadas")
    responsavel = relationship("Usuario", foreign_keys=[responsavel_id], backref="tarefas_atribuidas")
