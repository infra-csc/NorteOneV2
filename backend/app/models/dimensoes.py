from sqlalchemy import Column, Integer, String, Boolean, Date, DateTime, ForeignKey, Numeric, Float, Text, CheckConstraint, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from ..core.database import Base

class DimTempo(Base):
    __tablename__ = "dim_tempo"
    
    id = Column(Integer, primary_key=True, index=True)
    data = Column(Date, unique=True, nullable=False)
    dia = Column(Integer)
    mes = Column(Integer)
    trimestre = Column(Integer)
    semestre = Column(Integer)
    ano = Column(Integer)
    dia_semana = Column(String(20))
    nome_mes = Column(String(20))
    is_feriado = Column(Boolean, default=False)

class DimCentroCusto(Base):
    __tablename__ = "dim_centro_custo"
    
    id = Column(Integer, primary_key=True, index=True)
    codigo = Column(String(20), unique=True, nullable=False)
    nome = Column(String(100), nullable=False)
    area = Column(String(50))
    gestor_responsavel = Column(String(100))
    ativo = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

class DimProjeto(Base):
    __tablename__ = "dim_projeto"
    
    id = Column(Integer, primary_key=True, index=True)
    codigo = Column(String(20), unique=True, nullable=False)
    produto = Column(String(50), nullable=False)
    modalidade = Column(String(20), nullable=False)
    tipo_evento = Column(String(50), nullable=False)
    evento = Column(String(200), nullable=False)
    lei = Column(String(50), nullable=False)
    cliente = Column(String(100))
    status = Column(String(20), nullable=False)
    data_evento = Column(Date, nullable=False)
    local_evento = Column(String(150), nullable=False)
    cidade = Column(String(100))
    estado = Column(String(50))
    capacidade_maxima = Column(Integer)
    etapa = Column(Integer)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())
    imagem_kv = Column(String(500)) 

class DimCategoriaAtleta(Base):
    __tablename__ = "dim_categoria_atleta"
    
    id = Column(Integer, primary_key=True, index=True)
    codigo = Column(String(20), unique=True, nullable=False)
    nome = Column(String(100), nullable=False)
    faixa_etaria = Column(String(50))
    genero = Column(String(20))
    modalidade = Column(String(50))
    is_pcd = Column(Boolean, default=False)
    valor_inscricao_padrao = Column(Numeric(10, 2))
    custo_kit_padrao = Column(Numeric(10, 2))
    ativo = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.now())

class AcaoComercial(Base):
    __tablename__ = "acoes_comerciais"
    
    id = Column(Integer, primary_key=True, index=True)
    projeto_id = Column(Integer, ForeignKey("dim_projeto.id"), nullable=False)
    tipo = Column(String(50), nullable=False)
    descricao = Column(Text, nullable=False)
    data_acao = Column(Date, nullable=False)
    impacto_percentual = Column(Numeric(5, 2))
    vendas_antes = Column(Integer)
    vendas_depois = Column(Integer)
    ponto_corte = Column(String(10))
    estagio = Column(String(20))
    snapshot_isc = Column(Numeric(6, 4))
    snapshot_isc_state = Column(String(10))
    snapshot_d_minus = Column(Integer)
    snapshot_ia730 = Column(Float)
    snapshot_rolling14d = Column(Float)
    snapshot_curva_percent = Column(Float)
    snapshot_vendas_acumuladas = Column(Integer)
    snapshot_playbook_letter = Column(String(5))
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())
    
    projeto = relationship("DimProjeto", backref="acoes_comerciais")
    
    __table_args__ = (
        CheckConstraint(
            "tipo IN ('AUMENTO_PRECO', 'REDUCAO_PRECO', 'PROMOCAO', 'CAMPANHA', 'COMUNICACAO', 'NENHUMA_ACAO', 'OUTROS')",
            name="check_tipo_acao"
        ),
    )


class EventoConsolidado(Base):
    __tablename__ = "eventos_consolidados"
    
    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String(255), nullable=False)
    descricao = Column(Text, nullable=True)
    ativo = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())
    
    mapeamentos = relationship("SkuMapping", back_populates="evento_consolidado")


class EventoGrupo(Base):
    __tablename__ = "evento_grupos"
    
    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String(200), nullable=False, unique=True)
    descricao = Column(Text, nullable=True)
    ativo = Column(Boolean, default=True)
    circuito = Column(String(200), nullable=True)
    cidade_normalizada = Column(String(200), nullable=True)
    curva_override = Column(String(200), nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())


class SkuMapping(Base):
    __tablename__ = "sku_mappings"
    
    id = Column(Integer, primary_key=True, index=True)
    fonte = Column(String(20), nullable=False)
    id_externo = Column(Integer, nullable=False)
    sku = Column(String(50), nullable=False)
    evento_grupo = Column(String(200), nullable=True)
    ano = Column(Integer, nullable=False)
    nome_evento = Column(String(255), nullable=False)
    ativo = Column(Boolean, default=True)
    evento_consolidado_id = Column(Integer, ForeignKey("eventos_consolidados.id"), nullable=True)
    data_evento = Column(Date, nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())
    
    evento_consolidado = relationship("EventoConsolidado", back_populates="mapeamentos")
    
    __table_args__ = (
        CheckConstraint("fonte IN ('ATIVO', 'MAGENTO')", name="check_fonte_sku"),
    )


class MarketingSettings(Base):
    __tablename__ = "marketing_settings"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(100), unique=True, nullable=False, index=True)
    value = Column(JSON, nullable=False, default=dict)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
