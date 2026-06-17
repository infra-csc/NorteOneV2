from sqlalchemy import Column, Integer, BigInteger, String, Text, Numeric, DateTime, UniqueConstraint, Index
from sqlalchemy.sql import func
from ..core.database import Base


class KitMappingSnapshot(Base):
    """Snapshot persistente das colunas vindas de Magento+Ativo na tela
    de Mapeamento de Kits. KitConfig (multiplicador, is_kit_basico, custo,
    etc.) NÃO é guardado aqui — segue lido de :class:`KitConfig` em tempo
    real para refletir edições do usuário imediatamente.
    """

    __tablename__ = "kit_mapping_snapshot"

    id               = Column(Integer, primary_key=True, index=True)
    bundle_entity_id = Column(BigInteger, nullable=False)
    tipo_categoria   = Column(String(255), nullable=False, default="")
    fonte            = Column(String(16), nullable=False)
    id_evento        = Column(String(64), nullable=True)
    nome_evento      = Column(Text, nullable=True)
    nome_kit         = Column(Text, nullable=True)
    lote_atual       = Column(Text, nullable=True)
    price            = Column(Numeric(12, 2), nullable=True)
    special_price    = Column(Numeric(12, 2), nullable=True)
    pi_pai_min_price = Column(Numeric(12, 2), nullable=True)
    status_kit       = Column(String(16), nullable=True)
    content_hash     = Column(String(64), nullable=False)
    atualizado_em    = Column(DateTime, nullable=False, server_default=func.now())
    visto_em         = Column(DateTime, nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("bundle_entity_id", "tipo_categoria",
                         name="uq_kit_mapping_bundle_tipocat"),
        Index("ix_kit_mapping_fonte", "fonte"),
    )
