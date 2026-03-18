from sqlalchemy import Column, Integer, String, DateTime, Boolean, Numeric
from sqlalchemy.sql import func
from ..core.database import Base


class KitConfig(Base):
    __tablename__ = "kit_config"

    bundle_entity_id = Column(Integer, primary_key=True)
    id_evento = Column(Integer, nullable=True)
    kit_nome = Column(String(255), nullable=True)
    tipo_kit = Column(String(100), nullable=True)
    tipo = Column(String(20), default="multiplier")
    multiplicador = Column(Integer, default=1)
    is_kit_basico = Column(Boolean, default=False, nullable=False)
    custo_kit = Column(Numeric(10, 2), nullable=True)
    ativo_categoria = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
