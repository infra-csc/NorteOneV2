from sqlalchemy import Column, Integer, String, DateTime, Numeric, Text
from sqlalchemy.dialects.postgresql import JSONB
from app.core.database import Base
from datetime import datetime
from zoneinfo import ZoneInfo


def get_brasilia_now():
    return datetime.now(ZoneInfo('America/Sao_Paulo')).replace(tzinfo=None)


class NoriInsight(Base):
    """
    Proactive AI-generated insights for margin improvement opportunities.

    Deduplification policy: one insight per (evento_id, tipo, UTC-date) per day
    regardless of status. Enforced in service layer (save_insights_to_db) so that
    even a discarded insight blocks regeneration of the same type on the same day.
    The SQL migration includes a partial unique index covering only novo/visto rows
    as a DB-level safety net, but the application enforces the stricter all-status
    rule via the service query.
    """
    __tablename__ = "nori_insights"

    id = Column(Integer, primary_key=True, index=True)
    # VARCHAR lengths match migration 005_nori_insights.sql exactly
    evento_id = Column(String(200), nullable=True, index=True)
    evento_nome = Column(String(300), nullable=False, default="")
    tipo = Column(String(50), nullable=False, index=True)
    titulo = Column(String(400), nullable=False)
    conteudo = Column(Text, nullable=False)
    acao_sugerida = Column(Text, nullable=True)
    # NUMERIC matches migration; Numeric(12,2) / Numeric(6,2) == NUMERIC(12,2) / NUMERIC(6,2)
    impacto_estimado_reais = Column(Numeric(12, 2), nullable=True)
    impacto_estimado_percentual = Column(Numeric(6, 2), nullable=True)
    # JSONB for efficient querying of event metrics context
    dados_contexto = Column(JSONB, nullable=True)
    status = Column(String(20), default="novo", nullable=False, index=True)
    gerado_em = Column(DateTime, default=get_brasilia_now, nullable=False, index=True)
    atualizado_em = Column(DateTime, default=get_brasilia_now, onupdate=get_brasilia_now, nullable=False)
