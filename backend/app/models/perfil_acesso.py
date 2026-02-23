from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from ..core.database import Base


class PerfilAcesso(Base):
    __tablename__ = "perfil_acesso"

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String(50), unique=True, nullable=False)
    descricao = Column(String(200))
    is_sistema = Column(Boolean, default=False)
    is_admin = Column(Boolean, default=False)
    ativo = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    permissoes = relationship("PerfilPermissao", back_populates="perfil_acesso", cascade="all, delete-orphan")
    permissoes_campo = relationship("PerfilPermissaoCampo", back_populates="perfil_acesso_rel", cascade="all, delete-orphan")
    usuarios = relationship("Usuario", back_populates="perfil_acesso_rel")


class PerfilPermissao(Base):
    __tablename__ = "perfil_permissao"

    id = Column(Integer, primary_key=True, index=True)
    perfil_acesso_id = Column(Integer, ForeignKey("perfil_acesso.id", ondelete="CASCADE"), nullable=False)
    modulo = Column(String(50), nullable=False)
    pode_visualizar = Column(Boolean, default=False)
    pode_criar = Column(Boolean, default=False)
    pode_editar = Column(Boolean, default=False)
    pode_deletar = Column(Boolean, default=False)

    perfil_acesso = relationship("PerfilAcesso", back_populates="permissoes")


class PerfilPermissaoCampo(Base):
    __tablename__ = "perfil_permissao_campo"

    id = Column(Integer, primary_key=True, index=True)
    perfil_acesso_id = Column(Integer, ForeignKey("perfil_acesso.id", ondelete="CASCADE"), nullable=False)
    entidade = Column(String(50), nullable=False)
    campo = Column(String(50), nullable=False)
    pode_visualizar = Column(Boolean, default=True)
    pode_editar = Column(Boolean, default=True)

    perfil_acesso_rel = relationship("PerfilAcesso", back_populates="permissoes_campo")
