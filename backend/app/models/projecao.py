from sqlalchemy import Column, Integer, String, Boolean, DateTime, Date, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime
from zoneinfo import ZoneInfo
from ..core.database import Base


def _now_brasilia():
    return datetime.now(ZoneInfo('America/Sao_Paulo')).replace(tzinfo=None)


# Kit cujo comportamento muda no Corte 2: até o Corte 1 ele é "Kit Completo -
# Sem camiseta"; depois que o Corte 1 congela, vira "Camiseta avulsa" (display)
# com piso igual ao valor congelado no Corte 1 (ver ProjecaoKitCorteSnapshot).
KIT_CAMISETA_AVULSA_ORIGEM = "Kit Completo - Sem camiseta"
KIT_CAMISETA_AVULSA_LABEL = "Camiseta avulsa"


class AreaProjecao(Base):
    __tablename__ = "area_projecao"

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String(100), unique=True, nullable=False)
    ativo = Column(Boolean, default=True, index=True)
    usa_cutoff_customizado = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=_now_brasilia)
    updated_at = Column(DateTime, onupdate=_now_brasilia)

    usuarios = relationship("AreaProjecaoUsuario", back_populates="area", cascade="all, delete-orphan")
    projecoes = relationship("ProjecaoInscritos", back_populates="area_projecao")


class AreaProjecaoUsuario(Base):
    __tablename__ = "area_projecao_usuario"

    id = Column(Integer, primary_key=True, index=True)
    area_projecao_id = Column(Integer, ForeignKey("area_projecao.id", ondelete="CASCADE"), nullable=False, index=True)
    usuario_id = Column(Integer, ForeignKey("dim_usuario.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(DateTime, default=_now_brasilia)

    area = relationship("AreaProjecao", back_populates="usuarios")
    usuario = relationship("Usuario")

    __table_args__ = (
        UniqueConstraint("area_projecao_id", "usuario_id", name="uq_area_usuario"),
    )


class ProjecaoInscritos(Base):
    __tablename__ = "projecao_inscritos"

    id = Column(Integer, primary_key=True, index=True)
    evento_id = Column(Integer, ForeignKey("cadastro_evento.id", ondelete="CASCADE"), nullable=False, index=True)
    area_projecao_id = Column(Integer, ForeignKey("area_projecao.id", ondelete="CASCADE"), nullable=False, index=True)
    quantidade = Column(Integer, nullable=False, default=0)
    created_by = Column(Integer, ForeignKey("dim_usuario.id"), nullable=False, index=True)
    updated_by = Column(Integer, ForeignKey("dim_usuario.id"), nullable=True, index=True)
    locked_by = Column(Integer, ForeignKey("dim_usuario.id"), nullable=True, index=True)
    created_at = Column(DateTime, default=_now_brasilia)
    updated_at = Column(DateTime, onupdate=_now_brasilia)
    locked_at = Column(DateTime, nullable=True, index=True)
    deleted_at = Column(DateTime, nullable=True, index=True)

    evento = relationship("CadastroEvento")
    area_projecao = relationship("AreaProjecao", back_populates="projecoes")
    criador = relationship("Usuario", foreign_keys=[created_by])
    editor = relationship("Usuario", foreign_keys=[updated_by])
    travador = relationship("Usuario", foreign_keys=[locked_by])
    historico = relationship("ProjecaoInscritosHistorico", back_populates="projecao")
    clientes = relationship("ProjecaoInscritosCliente", back_populates="projecao", cascade="all, delete-orphan")
    kits = relationship("ProjecaoInscritosKit", back_populates="projecao", cascade="all, delete-orphan")


class ProjecaoInscritosHistorico(Base):
    __tablename__ = "projecao_inscritos_historico"

    id = Column(Integer, primary_key=True, index=True)
    projecao_id = Column(Integer, ForeignKey("projecao_inscritos.id", ondelete="CASCADE"), nullable=False, index=True)
    acao = Column(String(20), nullable=False)
    campo_alterado = Column(String(50), nullable=True)
    valor_anterior = Column(Text, nullable=True)
    valor_novo = Column(Text, nullable=True)
    usuario_id = Column(Integer, ForeignKey("dim_usuario.id"), nullable=False, index=True)
    created_at = Column(DateTime, default=_now_brasilia, index=True)

    projecao = relationship("ProjecaoInscritos", back_populates="historico")
    usuario = relationship("Usuario")


class ProjecaoInscritosCliente(Base):
    __tablename__ = "projecao_inscritos_cliente"

    id = Column(Integer, primary_key=True, index=True)
    projecao_id = Column(Integer, ForeignKey("projecao_inscritos.id", ondelete="CASCADE"), nullable=False, index=True)
    nome_cliente = Column(String(200), nullable=False)
    quantidade = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=_now_brasilia)

    projecao = relationship("ProjecaoInscritos", back_populates="clientes")


class ProjecaoInscritosKit(Base):
    __tablename__ = "projecao_inscritos_kit"

    id = Column(Integer, primary_key=True, index=True)
    projecao_id = Column(Integer, ForeignKey("projecao_inscritos.id", ondelete="CASCADE"), nullable=False, index=True)
    nome_kit = Column(String(200), nullable=False)
    quantidade = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=_now_brasilia)

    projecao = relationship("ProjecaoInscritos", back_populates="kits")


class ProjecaoCutoffRule(Base):
    __tablename__ = "projecao_cutoff_rule"

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String(100), nullable=False)
    dias_antes_evento = Column(Integer, nullable=False, index=True)
    ativo = Column(Boolean, default=True, nullable=False, index=True)
    created_at = Column(DateTime, default=_now_brasilia)
    updated_at = Column(DateTime, onupdate=_now_brasilia)

    __table_args__ = (
        UniqueConstraint("dias_antes_evento", name="uq_cutoff_dias"),
    )


class ProjecaoCutoffEventoArea(Base):
    __tablename__ = "projecao_cutoff_evento_area"

    id = Column(Integer, primary_key=True, index=True)
    evento_id = Column(Integer, ForeignKey("cadastro_evento.id", ondelete="CASCADE"), nullable=False, index=True)
    area_projecao_id = Column(Integer, ForeignKey("area_projecao.id", ondelete="CASCADE"), nullable=False, index=True)
    data_corte_1 = Column(Date, nullable=True)
    data_corte_2 = Column(Date, nullable=True)
    created_by = Column(Integer, ForeignKey("dim_usuario.id"), nullable=True, index=True)
    updated_by = Column(Integer, ForeignKey("dim_usuario.id"), nullable=True, index=True)
    created_at = Column(DateTime, default=_now_brasilia)
    updated_at = Column(DateTime, onupdate=_now_brasilia)

    evento = relationship("CadastroEvento")
    area = relationship("AreaProjecao")
    editor = relationship("Usuario", foreign_keys=[updated_by])
    criador = relationship("Usuario", foreign_keys=[created_by])

    __table_args__ = (
        UniqueConstraint("evento_id", "area_projecao_id", name="uq_cutoff_evento_area"),
    )


class ProjecaoAutoLockConfig(Base):
    __tablename__ = "projecao_auto_lock_config"

    id = Column(Integer, primary_key=True, index=True)
    dias_antes_evento = Column(Integer, nullable=False, default=7)
    # Horário (BRT, formato "HH:MM") em que a trava passa a valer no dia D-N.
    # "00:00" (default) preserva o comportamento legado: trava o dia D-N inteiro.
    hora_trava = Column(String(5), nullable=False, default="00:00")
    ativo = Column(Boolean, default=True, nullable=False)
    updated_by = Column(Integer, ForeignKey("dim_usuario.id"), nullable=True)
    updated_at = Column(DateTime, default=_now_brasilia, onupdate=_now_brasilia)

    editor = relationship("Usuario", foreign_keys=[updated_by])


class ProjecaoCorteConfig(Base):
    """Config global (single-row) dos dois cortes de congelamento por evento.

    dias_corte_1 → Projeção envio (D-N do corte 1)
    dias_corte_2 → Projeção convicta (D-N do corte 2)
    Quando o evento atinge cada D-, o job noturno congela o total de projeção.
    """
    __tablename__ = "projecao_corte_config"

    id = Column(Integer, primary_key=True, index=True)
    dias_corte_1 = Column(Integer, nullable=False, default=30)
    dias_corte_2 = Column(Integer, nullable=False, default=7)
    ativo = Column(Boolean, default=False, nullable=False)
    updated_by = Column(Integer, ForeignKey("dim_usuario.id"), nullable=True)
    updated_at = Column(DateTime, default=_now_brasilia, onupdate=_now_brasilia)

    editor = relationship("Usuario", foreign_keys=[updated_by])


class ProjecaoCorteSnapshot(Base):
    """Valores congelados (por evento) de cada corte. Uma linha por evento."""
    __tablename__ = "projecao_corte_snapshot"

    id = Column(Integer, primary_key=True, index=True)
    evento_id = Column(Integer, ForeignKey("cadastro_evento.id", ondelete="CASCADE"), nullable=False, index=True)
    valor_corte_1 = Column(Integer, nullable=True)
    congelado_corte_1_em = Column(DateTime, nullable=True)
    valor_corte_2 = Column(Integer, nullable=True)
    congelado_corte_2_em = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=_now_brasilia, onupdate=_now_brasilia)

    evento = relationship("CadastroEvento")

    __table_args__ = (
        UniqueConstraint("evento_id", name="uq_corte_snapshot_evento"),
    )


class ProjecaoKitCorteSnapshot(Base):
    """Valor congelado por (evento, área, kit) no momento do Corte 1.

    Hoje só é populado para o kit "Kit Completo - Sem camiseta": guarda quanto
    havia desse kit quando o Corte 1 congelou, servindo de PISO da "Camiseta
    avulsa" no Corte 2 (o usuário só pode aumentar a partir desse valor).
    """
    __tablename__ = "projecao_kit_corte_snapshot"

    id = Column(Integer, primary_key=True, index=True)
    evento_id = Column(Integer, ForeignKey("cadastro_evento.id", ondelete="CASCADE"), nullable=False, index=True)
    area_projecao_id = Column(Integer, ForeignKey("area_projecao.id", ondelete="CASCADE"), nullable=False, index=True)
    nome_kit = Column(String(200), nullable=False)
    valor_corte_1 = Column(Integer, nullable=False, default=0)
    congelado_em = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=_now_brasilia, onupdate=_now_brasilia)

    evento = relationship("CadastroEvento")
    area = relationship("AreaProjecao")

    __table_args__ = (
        UniqueConstraint("evento_id", "area_projecao_id", "nome_kit", name="uq_kit_corte_snapshot_evento_area_kit"),
    )


class SimuladorProjetadoFaixas(Base):
    __tablename__ = "simulador_projetado_faixas"

    id = Column(Integer, primary_key=True, index=True)
    evento_id = Column(String(100), nullable=False, index=True)
    usuario_id = Column(Integer, ForeignKey("dim_usuario.id", ondelete="CASCADE"), nullable=False, index=True)
    faixas = Column(Text, nullable=False, default="[]")
    created_at = Column(DateTime, default=_now_brasilia)
    updated_at = Column(DateTime, default=_now_brasilia, onupdate=_now_brasilia)

    usuario = relationship("Usuario")

    __table_args__ = (
        UniqueConstraint("evento_id", "usuario_id", name="uq_simulador_faixas_evento_usuario"),
    )

