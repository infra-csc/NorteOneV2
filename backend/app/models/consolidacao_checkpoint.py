from sqlalchemy import Column, Integer, BigInteger, String, DateTime, Index, UniqueConstraint
from sqlalchemy.sql import func
from ..core.database import Base


class ConsolidacaoCheckpoint(Base):
    """Persistent checkpoint for the manual full consolidation
    (``/api/admin/snapshots/consolidar-full``).

    One row per (ciclo_id, evento_grupo) — written immediately after each
    group is processed. Lets a restarted backend resume an interrupted cycle
    without re-running groups that already finished successfully.

    A "running" cycle is one whose newest row is still recent enough AND
    whose ``sync_event_log`` does not yet contain a 'concluido' marker for
    the same ciclo_id.
    """
    __tablename__ = "consolidacao_checkpoint"

    id = Column(BigInteger, primary_key=True, index=True)
    ciclo_id = Column(String(40), nullable=False, index=True)
    evento_grupo = Column(String(200), nullable=False)
    status = Column(String(20), nullable=False)  # ok | failed
    incremental = Column(Integer, nullable=False, default=0)  # 0/1
    triggered_by = Column(String(200), nullable=True)
    duracao_ms = Column(Integer, nullable=True)
    motivo = Column(String(400), nullable=True)
    qtd_antes = Column(Integer, nullable=True)
    qtd_depois = Column(Integer, nullable=True)
    started_at_cycle = Column(DateTime(timezone=True), nullable=True)
    processed_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("ciclo_id", "evento_grupo", name="uq_consol_ckpt_ciclo_grupo"),
        Index("ix_consol_ckpt_processed_at", "processed_at"),
    )
