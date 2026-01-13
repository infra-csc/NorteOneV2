from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, Enum
from sqlalchemy.orm import relationship
from app.core.database import Base
from datetime import datetime
import enum


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
    data_vencimento = Column(DateTime, nullable=True)
    hora_lembrete = Column(DateTime, nullable=True)
    prioridade = Column(Enum(PrioridadeTarefa), default=PrioridadeTarefa.MEDIA)
    status = Column(Enum(StatusTarefa), default=StatusTarefa.PENDENTE)
    criado_por_nori = Column(Boolean, default=False)
    usuario_id = Column(Integer, ForeignKey("dim_usuario.id"), nullable=False)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    usuario = relationship("Usuario", backref="tarefas")
