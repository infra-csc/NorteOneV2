from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from ..core.database import Base

class Usuario(Base):
    __tablename__ = "dim_usuario"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(100), unique=True, nullable=False, index=True)
    nome = Column(String(100), nullable=False)
    senha_hash = Column(String(255), nullable=False)
    perfil_acesso_id = Column(Integer, ForeignKey("perfil_acesso.id"), nullable=True)
    centro_custo_id = Column(Integer, ForeignKey("dim_centro_custo.id"))
    ativo = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.now())
    
    centro_custo = relationship("DimCentroCusto")
    perfil_acesso_rel = relationship("PerfilAcesso", back_populates="usuarios")
