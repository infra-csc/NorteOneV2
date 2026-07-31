from sqlalchemy import Column, Integer, String, Date, DateTime, Float, Numeric, UniqueConstraint, Index
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
    ano = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint('evento_grupo', 'fonte', 'data_venda', name='uq_snapshot_grupo_fonte_data'),
        Index('ix_snapshot_grupo_data', 'evento_grupo', 'data_venda'),
        Index('ix_snapshot_data_venda', 'data_venda'),
    )


class CurvaHistoricaSnapshot(Base):
    __tablename__ = "curva_historica_snapshot"

    id = Column(Integer, primary_key=True, index=True)
    evento_grupo = Column(String(200), nullable=False, index=True)
    ano_referencia = Column(Integer, nullable=False)
    d_minus = Column(Integer, nullable=False)
    percentual_acumulado = Column(Float, nullable=False)
    total_vendas_referencia = Column(Integer, nullable=True)
    origem = Column(String(50), nullable=True)
    fonte_origem = Column(String(200), nullable=True)
    created_at = Column(DateTime, default=func.now())

    __table_args__ = (
        UniqueConstraint('evento_grupo', 'ano_referencia', 'd_minus', name='uq_curva_grupo_ano_dminus'),
        Index('ix_curva_grupo_ano', 'evento_grupo', 'ano_referencia'),
    )


class MargemBundleRevSnapshot(Base):
    """Cache persistente de receita E quantidade Magento por bundle_entity_id.

    Pré-computado pelo job diário das 4h (antes do full warmup das 5h).
    Elimina timeouts e quedas parciais do Magento em get_margem_por_kit:
    - receita_liquida: soma de price-discount dos itens-filho (Distância/Modalidade)
    - qtd_inscricoes: COUNT(DISTINCT soi_parent.item_id) — total de inscrições
    Apesar do nome legado, hoje guarda os dois agregados que alimentam a tabela
    "Margem por Tipo de Kit" e o currentSales do detalhe do evento.
    """
    __tablename__ = "margem_bundle_rev_snapshot"

    bundle_entity_id = Column(Integer, primary_key=True)
    receita_liquida = Column(Numeric(14, 2), nullable=False, default=0)
    qtd_inscricoes = Column(Integer, nullable=True, default=0)
    calculado_em = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class DetalheEventosSnapshot(Base):
    """Snapshot do payload completo de Detalhamento de Eventos por (evento_grupo, ano).

    Pré-computado pelo job noturno (~03h BRT), eliminando timeouts de Ativo/Magento
    em acessos do usuário. Leitura serve em <1s; fallback ao vivo quando ausente.

    Uma linha por edição (ano) do evento_grupo — permite que edições de anos
    diferentes (ex.: mesmo evento em 2026 e 2027) tenham snapshots independentes.
    A linha sentinela "__version__" (usada por maybe_flush_snapshots_on_version_change)
    usa ano=0.

    payload: JSON com {consolidado, por_banco, divergencias, erros, totais, skus}
    """
    __tablename__ = "detalhe_eventos_snapshot"

    id = Column(Integer, primary_key=True, index=True)
    evento_grupo = Column(String(200), nullable=False, index=True)
    ano = Column(Integer, nullable=True)
    payload = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint('evento_grupo', 'ano', name='uq_detalhe_eventos_snapshot_grupo_ano'),
    )
