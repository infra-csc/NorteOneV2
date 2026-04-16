from sqlalchemy import Column, Integer, String, Date, DateTime, Boolean, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from ..core.database import Base


class EventoDetailSnapshot(Base):
    """Snapshot persistente do payload completo do detalhe de um evento.

    Permite servir GET /marketing/eventos/{id} de forma instantânea (~50ms),
    independente de cache em memória ser limpo por restart ou invalidação.
    O scheduler atualiza este snapshot a cada 30 min em background.
    """
    __tablename__ = "evento_detail_snapshot"

    id = Column(Integer, primary_key=True, index=True)
    evento_id = Column(String(100), nullable=False)
    ano = Column(Integer, nullable=False)
    payload = Column(JSONB, nullable=False)
    data_evento = Column(Date, nullable=True)
    is_completed = Column(Boolean, nullable=False, default=False)
    computed_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint('evento_id', 'ano', name='uq_evento_detail_snapshot_eid_ano'),
        Index('ix_evento_detail_snapshot_eid_ano', 'evento_id', 'ano'),
    )
