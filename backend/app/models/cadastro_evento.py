from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Numeric, Date, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from ..core.database import Base


class CircuitoProduto(Base):
    __tablename__ = "circuito_produto"
    
    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String(200), nullable=False, unique=True)
    created_at = Column(DateTime, default=func.now())


class Localizacao(Base):
    __tablename__ = "localizacao"
    
    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String(200), nullable=False, unique=True)
    created_at = Column(DateTime, default=func.now())


class DistanciaOpcao(Base):
    __tablename__ = "distancia_opcao"

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String(20), nullable=False, unique=True)
    ativo = Column(Boolean, default=True)
    ordem = Column(Integer, default=0)
    created_at = Column(DateTime, default=func.now())


class CadastroEvento(Base):
    """Cadastro principal de eventos esportivos"""
    __tablename__ = "cadastro_evento"
    
    id = Column(Integer, primary_key=True, index=True)
    projeto_id = Column(Integer, ForeignKey("dim_projeto.id"), nullable=True)
    nome = Column(String(200), nullable=False)
    circuito_produto = Column(String(200))
    localizacao_evento = Column(String(200))
    ano_evento = Column(Integer)
    imagem_kv = Column(String(500))
    status = Column(String(50), default='Em andamento')
    modalidade = Column(String(50), default='Corrida')
    
    sku = Column(String(50))
    produto = Column(String(100))
    tipo_evento = Column(String(50))
    lei = Column(String(50))
    capacidade_maxima = Column(Integer)
    cidade = Column(String(100))
    estado = Column(String(50))
    
    data_evento = Column(Date)
    horario_largada = Column(String(10))
    local = Column(String(300))
    distancias = Column(JSON, default=list)
    
    atletas_site_pago = Column(Integer, default=0)
    atletas_site_tkt_medio = Column(Numeric(10, 2), default=0)
    atletas_grupos_pago = Column(Integer, default=0)
    atletas_grupos_tkt_medio = Column(Numeric(10, 2), default=0)
    atletas_cortesia = Column(Integer, default=0)
    atletas_appai_pago = Column(Integer, default=0)
    atletas_appai_tkt_medio = Column(Numeric(10, 2), default=0)
    
    dias_encerramento_inscricao = Column(Integer, default=2)
    id_evento_magento = Column(Integer, nullable=True)
    
    retirada_kit_local = Column(String(300))
    retirada_kit_data_horario = Column(DateTime)
    
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())
    
    projeto = relationship("DimProjeto")
    cortesias = relationship("CadastroCortesia", back_populates="cadastro", cascade="all, delete-orphan")
    taxas = relationship("CadastroTaxa", back_populates="cadastro", cascade="all, delete-orphan")
    kit_produtos = relationship("CadastroKitProduto", back_populates="cadastro", cascade="all, delete-orphan")
    faixas_preco_site = relationship("CadastroFaixaPrecoSite", back_populates="cadastro", cascade="all, delete-orphan")
    faixas_preco_grupos = relationship("CadastroFaixaPrecoGrupos", back_populates="cadastro", cascade="all, delete-orphan")


class CadastroCortesia(Base):
    """Cortesias do evento"""
    __tablename__ = "cadastro_cortesia"
    
    id = Column(Integer, primary_key=True, index=True)
    cadastro_id = Column(Integer, ForeignKey("cadastro_evento.id", ondelete="CASCADE"), nullable=False)
    cliente = Column(String(200), nullable=False)
    quantidade = Column(Integer, default=0)
    
    cadastro = relationship("CadastroEvento", back_populates="cortesias")


class CadastroTaxa(Base):
    """Taxas do evento"""
    __tablename__ = "cadastro_taxa"
    
    id = Column(Integer, primary_key=True, index=True)
    cadastro_id = Column(Integer, ForeignKey("cadastro_evento.id", ondelete="CASCADE"), nullable=False)
    valor_unitario = Column(Numeric(10, 2), default=0)
    percentual_inscricao = Column(Numeric(5, 2), default=0)
    validado = Column(Boolean, default=False)
    data_validacao = Column(Date)
    
    cadastro = relationship("CadastroEvento", back_populates="taxas")


class CadastroKitProduto(Base):
    """Kits de produtos do evento"""
    __tablename__ = "cadastro_kit_produto"
    
    id = Column(Integer, primary_key=True, index=True)
    cadastro_id = Column(Integer, ForeignKey("cadastro_evento.id", ondelete="CASCADE"), nullable=False)
    kit = Column(String(100))
    ativo_categoria = Column(String(100), nullable=True)
    
    cadastro = relationship("CadastroEvento", back_populates="kit_produtos")
    produtos = relationship("CadastroKitProdutoItem", back_populates="kit_produto", cascade="all, delete-orphan")


class CadastroKitProdutoItem(Base):
    """Itens de produto dentro de um kit"""
    __tablename__ = "cadastro_kit_produto_item"
    
    id = Column(Integer, primary_key=True, index=True)
    kit_produto_id = Column(Integer, ForeignKey("cadastro_kit_produto.id", ondelete="CASCADE"), nullable=False)
    nome = Column(String(100), nullable=False)
    valor_unitario = Column(Numeric(10, 2), default=0)
    
    kit_produto = relationship("CadastroKitProduto", back_populates="produtos")


class CadastroFaixaPrecoSite(Base):
    """Faixas de preço - Site"""
    __tablename__ = "cadastro_faixa_preco_site"
    
    id = Column(Integer, primary_key=True, index=True)
    cadastro_id = Column(Integer, ForeignKey("cadastro_evento.id", ondelete="CASCADE"), nullable=False)
    tipo_kit = Column(String(50), nullable=False)
    faixa = Column(String(10), nullable=False)
    qtd = Column(Integer, default=0)
    tkt_medio = Column(Numeric(10, 2), default=0)
    total = Column(Numeric(15, 2), default=0)
    
    cadastro = relationship("CadastroEvento", back_populates="faixas_preco_site")


class CadastroFaixaPrecoGrupos(Base):
    """Faixas de preço - Grupos"""
    __tablename__ = "cadastro_faixa_preco_grupos"
    
    id = Column(Integer, primary_key=True, index=True)
    cadastro_id = Column(Integer, ForeignKey("cadastro_evento.id", ondelete="CASCADE"), nullable=False)
    tipo_kit = Column(String(50), nullable=False)
    faixa = Column(String(10), nullable=False)
    qtd = Column(Integer, default=0)
    tkt_medio = Column(Numeric(10, 2), default=0)
    total = Column(Numeric(15, 2), default=0)
    
    cadastro = relationship("CadastroEvento", back_populates="faixas_preco_grupos")
