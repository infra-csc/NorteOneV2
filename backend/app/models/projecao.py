from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime
from zoneinfo import ZoneInfo
from ..core.database import Base


def _now_brasilia():
    return datetime.now(ZoneInfo('America/Sao_Paulo')).replace(tzinfo=None)


class AreaProjecao(Base):
    __tablename__ = "area_projecao"

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String(100), unique=True, nullable=False)
    ativo = Column(Boolean, default=True)
    created_at = Column(DateTime, default=_now_brasilia)
    updated_at = Column(DateTime, onupdate=_now_brasilia)

    usuarios = relationship("AreaProjecaoUsuario", back_populates="area", cascade="all, delete-orphan")
    projecoes = relationship("ProjecaoInscritos", back_populates="area_projecao")


class AreaProjecaoUsuario(Base):
    __tablename__ = "area_projecao_usuario"

    id = Column(Integer, primary_key=True, index=True)
    area_projecao_id = Column(Integer, ForeignKey("area_projecao.id", ondelete="CASCADE"), nullable=False)
    usuario_id = Column(Integer, ForeignKey("dim_usuario.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, default=_now_brasilia)

    area = relationship("AreaProjecao", back_populates="usuarios")
    usuario = relationship("Usuario")

    __table_args__ = (
        UniqueConstraint("area_projecao_id", "usuario_id", name="uq_area_usuario"),
    )


class ProjecaoInscritos(Base):
    __tablename__ = "projecao_inscritos"

    id = Column(Integer, primary_key=True, index=True)
    evento_id = Column(Integer, ForeignKey("cadastro_evento.id", ondelete="CASCADE"), nullable=False)
    area_projecao_id = Column(Integer, ForeignKey("area_projecao.id", ondelete="CASCADE"), nullable=False)
    quantidade = Column(Integer, nullable=False, default=0)
    created_by = Column(Integer, ForeignKey("dim_usuario.id"), nullable=False)
    updated_by = Column(Integer, ForeignKey("dim_usuario.id"), nullable=True)
    locked_by = Column(Integer, ForeignKey("dim_usuario.id"), nullable=True)
    created_at = Column(DateTime, default=_now_brasilia)
    updated_at = Column(DateTime, onupdate=_now_brasilia)
    locked_at = Column(DateTime, nullable=True)
    deleted_at = Column(DateTime, nullable=True)

    evento = relationship("CadastroEvento")
    area_projecao = relationship("AreaProjecao", back_populates="projecoes")
    criador = relationship("Usuario", foreign_keys=[created_by])
    editor = relationship("Usuario", foreign_keys=[updated_by])
    travador = relationship("Usuario", foreign_keys=[locked_by])
    historico = relationship("ProjecaoInscritosHistorico", back_populates="projecao")
    clientes = relationship("ProjecaoInscritosCliente", back_populates="projecao", cascade="all, delete-orphan")


class ProjecaoInscritosHistorico(Base):
    __tablename__ = "projecao_inscritos_historico"

    id = Column(Integer, primary_key=True, index=True)
    projecao_id = Column(Integer, ForeignKey("projecao_inscritos.id", ondelete="CASCADE"), nullable=False)
    acao = Column(String(20), nullable=False)
    campo_alterado = Column(String(50), nullable=True)
    valor_anterior = Column(Text, nullable=True)
    valor_novo = Column(Text, nullable=True)
    usuario_id = Column(Integer, ForeignKey("dim_usuario.id"), nullable=False)
    created_at = Column(DateTime, default=_now_brasilia)

    projecao = relationship("ProjecaoInscritos", back_populates="historico")
    usuario = relationship("Usuario")


class ProjecaoInscritosCliente(Base):
    __tablename__ = "projecao_inscritos_cliente"

    id = Column(Integer, primary_key=True, index=True)
    projecao_id = Column(Integer, ForeignKey("projecao_inscritos.id", ondelete="CASCADE"), nullable=False)
    nome_cliente = Column(String(200), nullable=False)
    quantidade = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=_now_brasilia)

    projecao = relationship("ProjecaoInscritos", back_populates="clientes")


class ProjecaoCutoffRule(Base):
    __tablename__ = "projecao_cutoff_rule"

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String(100), nullable=False)
    dias_antes_evento = Column(Integer, nullable=False)
    ativo = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=_now_brasilia)
    updated_at = Column(DateTime, onupdate=_now_brasilia)

    __table_args__ = (
        UniqueConstraint("dias_antes_evento", name="uq_cutoff_dias"),
    )
