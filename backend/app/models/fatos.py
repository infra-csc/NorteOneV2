from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Numeric, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from ..core.database import Base

class FatoOrcamento(Base):
    __tablename__ = "fato_orcamento"
    
    id = Column(Integer, primary_key=True, index=True)
    tempo_id = Column(Integer, ForeignKey("dim_tempo.id"))
    centro_custo_id = Column(Integer, ForeignKey("dim_centro_custo.id"))
    conta_id = Column(Integer, ForeignKey("dim_conta.id"))
    projeto_id = Column(Integer, ForeignKey("dim_projeto.id"))
    valor_orcado = Column(Numeric(15, 2), nullable=False)
    quantidade_orcada = Column(Numeric(10, 2))
    versao_orcamento = Column(String(20), default='V1')
    ano_referencia = Column(Integer, nullable=False)
    created_by = Column(Integer, ForeignKey("dim_usuario.id"))
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())
    
    tempo = relationship("DimTempo")
    centro_custo = relationship("DimCentroCusto")
    conta = relationship("DimConta")
    projeto = relationship("DimProjeto")
    criador = relationship("Usuario", foreign_keys=[created_by])
    
    __table_args__ = (
        UniqueConstraint('tempo_id', 'centro_custo_id', 'conta_id', 'projeto_id', 'versao_orcamento', name='uq_orcamento'),
    )

class FatoProjecao(Base):
    __tablename__ = "fato_projecao"
    
    id = Column(Integer, primary_key=True, index=True)
    tempo_id = Column(Integer, ForeignKey("dim_tempo.id"))
    centro_custo_id = Column(Integer, ForeignKey("dim_centro_custo.id"))
    conta_id = Column(Integer, ForeignKey("dim_conta.id"))
    projeto_id = Column(Integer, ForeignKey("dim_projeto.id"))
    valor_projetado = Column(Numeric(15, 2), nullable=False)
    quantidade_projetada = Column(Numeric(10, 2))
    versao = Column(Integer, default=1)
    justificativa = Column(Text)
    status = Column(String(20), default='RASCUNHO')
    created_by = Column(Integer, ForeignKey("dim_usuario.id"))
    approved_by = Column(Integer, ForeignKey("dim_usuario.id"))
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())
    
    tempo = relationship("DimTempo")
    centro_custo = relationship("DimCentroCusto")
    conta = relationship("DimConta")
    projeto = relationship("DimProjeto")
    criador = relationship("Usuario", foreign_keys=[created_by])
    aprovador = relationship("Usuario", foreign_keys=[approved_by])

class FatoRealizado(Base):
    __tablename__ = "fato_realizado"
    
    id = Column(Integer, primary_key=True, index=True)
    tempo_id = Column(Integer, ForeignKey("dim_tempo.id"))
    centro_custo_id = Column(Integer, ForeignKey("dim_centro_custo.id"))
    conta_id = Column(Integer, ForeignKey("dim_conta.id"))
    projeto_id = Column(Integer, ForeignKey("dim_projeto.id"))
    valor_realizado = Column(Numeric(15, 2), nullable=False)
    quantidade_realizada = Column(Numeric(10, 2))
    documento_referencia = Column(String(50))
    descricao = Column(Text)
    created_at = Column(DateTime, default=func.now())
    
    tempo = relationship("DimTempo")
    centro_custo = relationship("DimCentroCusto")
    conta = relationship("DimConta")
    projeto = relationship("DimProjeto")

class FatoAtletas(Base):
    __tablename__ = "fato_atletas"
    
    id = Column(Integer, primary_key=True, index=True)
    projeto_id = Column(Integer, ForeignKey("dim_projeto.id"), nullable=False)
    categoria_atleta_id = Column(Integer, ForeignKey("dim_categoria_atleta.id"), nullable=False)
    tempo_id = Column(Integer, ForeignKey("dim_tempo.id"))
    
    qtd_atletas_orcado = Column(Integer, default=0)
    qtd_atletas_projetado = Column(Integer, default=0)
    qtd_atletas_realizado = Column(Integer, default=0)
    qtd_atletas_pago_orcado = Column(Integer, default=0)
    qtd_atletas_pago_projetado = Column(Integer, default=0)
    qtd_atletas_pago_realizado = Column(Integer, default=0)
    qtd_atletas_cortesia_orcado = Column(Integer, default=0)
    qtd_atletas_cortesia_projetado = Column(Integer, default=0)
    qtd_atletas_cortesia_realizado = Column(Integer, default=0)
    
    tkt_medio_orcado = Column(Numeric(10, 2))
    tkt_medio_projetado = Column(Numeric(10, 2))
    tkt_medio_realizado = Column(Numeric(10, 2))
    inscricao_orcado = Column(Numeric(10, 2))
    inscricao_projetado = Column(Numeric(10, 2))
    inscricao_realizado = Column(Numeric(10, 2))
    
    valor_inscricao_unitario = Column(Numeric(10, 2))
    custo_kit_unitario_orcado = Column(Numeric(10, 2))
    custo_kit_unitario_projetado = Column(Numeric(10, 2))
    custo_kit_unitario_realizado = Column(Numeric(10, 2))
    
    versao_projecao = Column(Integer, default=1)
    observacao = Column(Text)
    created_by = Column(Integer, ForeignKey("dim_usuario.id"))
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())
    
    projeto = relationship("DimProjeto")
    categoria_atleta = relationship("DimCategoriaAtleta")
    tempo = relationship("DimTempo")
    criador = relationship("Usuario", foreign_keys=[created_by])
    
    __table_args__ = (
        UniqueConstraint('projeto_id', 'categoria_atleta_id', 'tempo_id', 'versao_projecao', name='uq_atletas'),
    )


class FatoAtletasMetricas(Base):
    """Métricas principais de atletas normalizadas por cenário"""
    __tablename__ = "fato_atletas_metricas"
    
    id = Column(Integer, primary_key=True, index=True)
    fato_atletas_id = Column(Integer, ForeignKey("fato_atletas.id", ondelete="CASCADE"), nullable=False)
    cenario = Column(String(20), nullable=False)  # ORCADO, PROJETADO, REALIZADO
    
    qtd_atletas = Column(Integer, default=0)
    qtd_atletas_pago = Column(Integer, default=0)
    qtd_atletas_cortesia = Column(Integer, default=0)
    tkt_medio = Column(Numeric(10, 2))
    inscricao = Column(Numeric(10, 2))
    custo_kit_unitario = Column(Numeric(10, 2))
    
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())
    
    fato_atletas = relationship("FatoAtletas", backref="metricas")
    
    __table_args__ = (
        UniqueConstraint('fato_atletas_id', 'cenario', name='uq_atletas_metricas'),
    )


class FatoAtletasCanais(Base):
    """Métricas de atletas por canal de distribuição (site, grupos, appai)"""
    __tablename__ = "fato_atletas_canais"
    
    id = Column(Integer, primary_key=True, index=True)
    fato_atletas_id = Column(Integer, ForeignKey("fato_atletas.id", ondelete="CASCADE"), nullable=False)
    canal = Column(String(50), nullable=False)  # SITE, GRUPOS, APPAI
    cenario = Column(String(20), nullable=False)  # ORCADO, PROJETADO, REALIZADO
    
    qtd_atletas = Column(Integer, default=0)
    tkt_medio = Column(Numeric(10, 2))
    inscricao = Column(Numeric(10, 2))
    
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())
    
    fato_atletas = relationship("FatoAtletas", backref="canais")
    
    __table_args__ = (
        UniqueConstraint('fato_atletas_id', 'canal', 'cenario', name='uq_atletas_canais'),
    )


class FatoAtletasKits(Base):
    """Métricas de kits (vip, plus, super, produto)"""
    __tablename__ = "fato_atletas_kits"
    
    id = Column(Integer, primary_key=True, index=True)
    fato_atletas_id = Column(Integer, ForeignKey("fato_atletas.id", ondelete="CASCADE"), nullable=False)
    tipo_kit = Column(String(50), nullable=False)  # VIP, PLUS, SUPER, PRODUTO
    cenario = Column(String(20), nullable=False)  # ORCADO, PROJETADO, REALIZADO
    
    qtd_kit = Column(Integer, default=0)
    tkt_medio = Column(Numeric(10, 2))
    inscricao = Column(Numeric(10, 2))
    custo_unitario = Column(Numeric(10, 2))
    
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())
    
    fato_atletas = relationship("FatoAtletas", backref="kits")
    
    __table_args__ = (
        UniqueConstraint('fato_atletas_id', 'tipo_kit', 'cenario', name='uq_atletas_kits'),
    )


class FatoAtletasCustos(Base):
    """Custos operacionais por atleta (hidratação, identificação, etc)"""
    __tablename__ = "fato_atletas_custos"
    
    id = Column(Integer, primary_key=True, index=True)
    fato_atletas_id = Column(Integer, ForeignKey("fato_atletas.id", ondelete="CASCADE"), nullable=False)
    tipo_custo = Column(String(50), nullable=False)  # AGUA, ISOTONICO, HIDRATACAO, NUMERO_PEITO, CHIP, ALFINETE, IDENTIFICACAO
    cenario = Column(String(20), nullable=False)  # ORCADO, PROJETADO, REALIZADO
    
    custo_unitario = Column(Numeric(10, 2))
    qtd_por_atleta = Column(Numeric(10, 2))
    custo_total = Column(Numeric(10, 2))
    
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())
    
    fato_atletas = relationship("FatoAtletas", backref="custos")
    
    __table_args__ = (
        UniqueConstraint('fato_atletas_id', 'tipo_custo', 'cenario', name='uq_atletas_custos'),
    )
