from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Numeric, Text, Date
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from ..core.database import Base
import enum


class StatusViagem(str, enum.Enum):
    PLANEJADA = "Planejada"
    EM_ANDAMENTO = "Em Andamento"
    FINALIZADA = "Finalizada"


class ViagemCotacao(Base):
    __tablename__ = "viagem_cotacao"

    id = Column(Integer, primary_key=True, index=True)
    titulo = Column(String(200), nullable=False)
    destino = Column(String(200), default="China")
    ano_competencia = Column(Integer, nullable=False, index=True)
    data_inicio = Column(Date, nullable=True)
    data_fim = Column(Date, nullable=True)
    status = Column(String(50), default=StatusViagem.PLANEJADA.value, index=True)
    observacoes = Column(Text, nullable=True)
    created_by = Column(Integer, ForeignKey("dim_usuario.id"), nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    cotacoes = relationship("Cotacao", back_populates="viagem", cascade="all, delete-orphan")
    custos_importacao = relationship("CustoImportacao", back_populates="viagem", cascade="all, delete-orphan")
    criador = relationship("Usuario", foreign_keys=[created_by])


class Fornecedor(Base):
    __tablename__ = "fornecedor"

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String(200), nullable=False)
    contato = Column(String(200), nullable=True)
    localizacao = Column(String(200), nullable=True)
    observacoes = Column(Text, nullable=True)
    ativo = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.now())

    cotacoes = relationship("Cotacao", back_populates="fornecedor")


class Cotacao(Base):
    __tablename__ = "cotacao"

    id = Column(Integer, primary_key=True, index=True)
    viagem_id = Column(Integer, ForeignKey("viagem_cotacao.id", ondelete="CASCADE"), nullable=False, index=True)
    fornecedor_id = Column(Integer, ForeignKey("fornecedor.id"), nullable=True, index=True)
    produto_nome = Column(String(200), nullable=False)
    descricao = Column(Text, nullable=True)
    valor_unitario_usd = Column(Numeric(12, 4), nullable=False, default=0)
    quantidade = Column(Integer, default=1)
    taxa_cambio = Column(Numeric(10, 4), nullable=True)
    valor_unitario_brl = Column(Numeric(12, 4), nullable=True)
    valor_total_usd = Column(Numeric(15, 4), nullable=True)
    valor_total_brl = Column(Numeric(15, 4), nullable=True)
    selecionado = Column(Boolean, default=False, index=True)
    data_cotacao = Column(Date, nullable=True)
    observacoes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    viagem = relationship("ViagemCotacao", back_populates="cotacoes")
    fornecedor = relationship("Fornecedor", back_populates="cotacoes")
    eventos = relationship("CotacaoEvento", back_populates="cotacao", cascade="all, delete-orphan")


class CustoImportacao(Base):
    __tablename__ = "custo_importacao"

    id = Column(Integer, primary_key=True, index=True)
    viagem_id = Column(Integer, ForeignKey("viagem_cotacao.id", ondelete="CASCADE"), nullable=False, index=True)
    descricao = Column(String(200), nullable=False)
    tipo = Column(String(50), nullable=False)
    valor_usd = Column(Numeric(12, 4), default=0)
    valor_brl = Column(Numeric(12, 4), default=0)
    observacoes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now())

    viagem = relationship("ViagemCotacao", back_populates="custos_importacao")


class CotacaoEvento(Base):
    __tablename__ = "cotacao_evento"

    id = Column(Integer, primary_key=True, index=True)
    cotacao_id = Column(Integer, ForeignKey("cotacao.id", ondelete="CASCADE"), nullable=False, index=True)
    cadastro_evento_id = Column(Integer, ForeignKey("cadastro_evento.id"), nullable=True, index=True)
    evento_nome_manual = Column(String(300), nullable=True)
    quantidade = Column(Integer, default=1)
    observacoes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now())

    cotacao = relationship("Cotacao", back_populates="eventos")
    evento = relationship("CadastroEvento")


class CotacaoFob(Base):
    __tablename__ = "cotacao_fob"

    id = Column(Integer, primary_key=True, index=True)
    circuito = Column(String(200), nullable=False)
    produto = Column(String(200), nullable=False)
    valor_fob = Column(Numeric(12, 4), nullable=False, default=0)
    indice_importacao = Column(Numeric(10, 6), nullable=True)
    bec = Column(Numeric(10, 6), nullable=True)
    cotacao_cambio = Column(Numeric(10, 4), nullable=True)
    valor_nacionalizado = Column(Numeric(15, 4), nullable=True)
    taxa_cambio = Column(Numeric(10, 4), nullable=True)
    valor_brl = Column(Numeric(12, 4), nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
