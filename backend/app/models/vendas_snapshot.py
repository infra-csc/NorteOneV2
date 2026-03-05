from sqlalchemy import Column, Integer, String, Date, DateTime, Float, UniqueConstraint, Index
from sqlalchemy.sql import func
from ..core.database import Base


class VendasDiariaSnapshot(Base):
    __tablename__ = "vendas_diaria_snapshot"

    id = Column(Integer, primary_key=True, index=True)
    evento_grupo = Column(String(200), nullable=False, index=True)
    fonte = Column(String(20), nullable=False)
    data_venda = Column(Date, nullable=False)
    quantidade = Column(Integer, nullable=False, default=0)
    receita = Column(Float, nullable=True, default=0)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint('evento_grupo', 'fonte', 'data_venda', name='uq_snapshot_grupo_fonte_data'),
        Index('ix_snapshot_grupo_data', 'evento_grupo', 'data_venda'),
    )


class CurvaHistoricaSnapshot(Base):
    __tablename__ = "curva_historica_snapshot"

    id = Column(Integer, primary_key=True, index=True)
    evento_grupo = Column(String(200), nullable=False, index=True)
    ano_referencia = Column(Integer, nullable=False)
    d_minus = Column(Integer, nullable=False)
    percentual_acumulado = Column(Float, nullable=False)
    total_vendas_referencia = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=func.now())

    __table_args__ = (
        UniqueConstraint('evento_grupo', 'ano_referencia', 'd_minus', name='uq_curva_grupo_ano_dminus'),
        Index('ix_curva_grupo_ano', 'evento_grupo', 'ano_referencia'),
    )
