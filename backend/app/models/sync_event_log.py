from sqlalchemy import Column, Integer, BigInteger, String, Text, Date, DateTime, Index
from sqlalchemy.sql import func
from ..core.database import Base


class SyncEventLog(Base):
    """Log estruturado dos jobs de sincronização (sincronizar_hoje_batch,
    snapshot_diario_batch, consolidar_vendas_grupo).

    Cada ciclo de batch recebe um ciclo_id único; dentro do ciclo são gravadas:
      - 1 linha 'ciclo' com nivel='ciclo' (resumo no fim do batch)
      - N linhas 'grupo' com nivel='grupo' (uma por evento_grupo processado)

    Retenção: 30 dias (cleanup chamado pelo job das 04h).
    """
    __tablename__ = "sync_event_log"

    id = Column(BigInteger, primary_key=True, index=True)
    ciclo_id = Column(String(40), nullable=False, index=True)
    job_name = Column(String(60), nullable=False, index=True)
    nivel = Column(String(20), nullable=False, default="grupo")
    grupo = Column(String(200), nullable=True, index=True)
    fonte = Column(String(20), nullable=True)
    status = Column(String(20), nullable=False, index=True)
    motivo = Column(String(80), nullable=True)
    detalhes = Column(Text, nullable=True)
    qtd_antes = Column(Integer, nullable=True)
    qtd_depois = Column(Integer, nullable=True)
    data_floor = Column(Date, nullable=True)
    duracao_ms = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)

    __table_args__ = (
        Index("ix_sync_log_ciclo_nivel", "ciclo_id", "nivel"),
        Index("ix_sync_log_job_created", "job_name", "created_at"),
    )
