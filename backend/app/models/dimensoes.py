from sqlalchemy import Column, Integer, String, Boolean, Date, DateTime, ForeignKey, Numeric, Text, CheckConstraint
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

class DimConta(Base):
    __tablename__ = "dim_conta"
    
    id = Column(Integer, primary_key=True, index=True)
    codigo = Column(String(20), unique=True, nullable=False)
    nome = Column(String(100), nullable=False)
    tipo = Column(String(20))
    grupo = Column(String(50))
    subgrupo = Column(String(50))
    ativo = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.now())
    
    __table_args__ = (
        CheckConstraint("tipo IN ('RECEITA', 'DESPESA')", name="check_tipo_conta"),
    )

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
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())
    
    projeto = relationship("DimProjeto", backref="acoes_comerciais")
    
    __table_args__ = (
        CheckConstraint(
            "tipo IN ('AUMENTO_PRECO', 'REDUCAO_PRECO', 'PROMOCAO', 'CAMPANHA', 'COMUNICACAO')",
            name="check_tipo_acao"
        ),
    )
