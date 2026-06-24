from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime
from sqlalchemy.sql import func
from ..core.database import Base


class DetalheDimensaoAlias(Base):
    """Regras de renomeação/agrupamento de dimensões no Detalhamento de Eventos.

    Cada linha mapeia um padrão (texto exato ou regex) de um valor bruto de
    dimensão (kit, modalidade, pelotao, tamanho_camiseta, produtos) para um
    nome canônico exibido na tela.

    As regras são aplicadas em ordem crescente de `ordem` dentro de cada
    `dimensao`. A primeira que casar é aplicada; as demais são ignoradas.
    Regras com `ativo=False` são ignoradas.
    """

    __tablename__ = "detalhe_dimensao_alias"

    id = Column(Integer, primary_key=True, index=True)
    dimensao = Column(String(50), nullable=False, index=True)
    pattern = Column(Text, nullable=False)
    substituicao = Column(Text, nullable=False)
    is_regex = Column(Boolean, nullable=False, default=False)
    ordem = Column(Integer, nullable=False, default=0)
    ativo = Column(Boolean, nullable=False, default=True)
    descricao = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)
