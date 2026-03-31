from sqlalchemy import Column, Integer, String, DateTime, Float, Text
from sqlalchemy.types import JSON
from app.core.database import Base
from datetime import datetime
from zoneinfo import ZoneInfo


def get_brasilia_now():
    return datetime.now(ZoneInfo('America/Sao_Paulo')).replace(tzinfo=None)


class NoriInsight(Base):
    __tablename__ = "nori_insights"

    id = Column(Integer, primary_key=True, index=True)
    evento_id = Column(String(100), nullable=True, index=True)
    evento_nome = Column(String(255), nullable=False)
    tipo = Column(String(50), nullable=False, index=True)
    titulo = Column(String(255), nullable=False)
    conteudo = Column(Text, nullable=False)
    acao_sugerida = Column(Text, nullable=True)
    impacto_estimado_reais = Column(Float, nullable=True)
    impacto_estimado_percentual = Column(Float, nullable=True)
    dados_contexto = Column(JSON, nullable=True)
    status = Column(String(20), default="novo", index=True)
    gerado_em = Column(DateTime, default=get_brasilia_now, index=True)
    atualizado_em = Column(DateTime, default=get_brasilia_now, onupdate=get_brasilia_now)
