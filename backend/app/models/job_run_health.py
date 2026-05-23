from sqlalchemy import Column, Integer, BigInteger, String, DateTime, Text, Index
from sqlalchemy.sql import func
from ..core.database import Base


class JobRunHealth(Base):
    """Métricas históricas por execução dos jobs de sincronização.

    Permite analisar tendência (ex.: 'Magento está piorando há 3 noites?')
    e comparar antes/depois de mudanças no scheduler.

    Populada por:
      - sincronizar_hoje_batch (job_name='sincronizar_hoje')
      - snapshot_diario_batch  (job_name='snapshot_diario')
    """
    __tablename__ = "job_run_health"

    id = Column(BigInteger, primary_key=True, index=True)
    job_name = Column(String(60), nullable=False, index=True)
    started_at = Column(DateTime(timezone=True), nullable=False)
    finished_at = Column(DateTime(timezone=True), nullable=False)
    duration_ms = Column(Integer, nullable=False)
    grupos_total = Column(Integer, nullable=False, default=0)
    grupos_ok = Column(Integer, nullable=False, default=0)
    grupos_parcial = Column(Integer, nullable=False, default=0)
    grupos_falha = Column(Integer, nullable=False, default=0)
    grupos_pulado = Column(Integer, nullable=False, default=0)
    status = Column(String(20), nullable=False, default="concluido")
    extra = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_job_run_health_job_started", "job_name", "started_at"),
    )
