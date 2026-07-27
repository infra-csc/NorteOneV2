from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.sql import func
from ..core.database import Base


class UserUiPref(Base):
    """Preferências de UI por usuário (layouts de tela, colunas, agrupamentos).

    Chave/valor genérico: `chave` identifica a preferência (ex.:
    'detalhe_eventos_hierarchy') e `valor` guarda o JSON serializado.
    O frontend continua usando localStorage como cache local/fallback;
    a fonte da verdade passa a ser esta tabela.
    """

    __tablename__ = "user_ui_pref"
    __table_args__ = (
        UniqueConstraint("usuario_id", "chave", name="uq_user_ui_pref_usuario_chave"),
    )

    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("dim_usuario.id", ondelete="CASCADE"), nullable=False, index=True)
    chave = Column(String(100), nullable=False)
    valor = Column(Text, nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
