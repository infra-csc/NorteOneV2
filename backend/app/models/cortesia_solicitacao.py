from sqlalchemy import Boolean, Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from datetime import datetime
from zoneinfo import ZoneInfo
from ..core.database import Base


def _now_brasilia():
    return datetime.now(ZoneInfo('America/Sao_Paulo')).replace(tzinfo=None)


# Tipos de solicitação de cortesia.
TIPO_CUPOM = "cupom"
TIPO_PLANILHA = "planilha"

# Status possíveis. Solicitações de planilha nascem e permanecem em
# "solicitado" (não há etapa de geração para esse tipo). Solicitações de
# cupom nascem em "solicitado" e passam para "gerado" quando alguém com a
# permissão de geração preenche o(s) código(s).
STATUS_SOLICITADO = "solicitado"
STATUS_GERADO = "gerado"


class CortesiaSolicitacao(Base):
    """Solicitação de cortesias aberta por um responsável de área para um
    evento, respeitando como trava a quantidade total projetada da área
    (projecao_inscritos.quantidade) menos o que já foi solicitado.

    Dois cenários (campo `tipo`):
      - 'cupom': fica registrada para outro usuário (permissão distinta)
        gerar manualmente o(s) cupom(ns) depois e preencher `codigo_cupom`.
      - 'planilha': armazena o arquivo enviado pelo cliente + metadados
        básicos, sem extrair/validar linha a linha.

    Sem etapa de aprovação: a validação do saldo já é suficiente para
    registrar a solicitação.
    """
    __tablename__ = "cortesia_solicitacao"

    id = Column(Integer, primary_key=True, index=True)
    evento_id = Column(Integer, ForeignKey("cadastro_evento.id", ondelete="CASCADE"), nullable=False, index=True)
    area_projecao_id = Column(Integer, ForeignKey("area_projecao.id", ondelete="CASCADE"), nullable=False, index=True)
    tipo = Column(String(20), nullable=False, index=True)  # 'cupom' | 'planilha'
    quantidade = Column(Integer, nullable=False, default=0)
    status = Column(String(20), nullable=False, default=STATUS_SOLICITADO, index=True)
    observacao = Column(Text, nullable=True)

    # Cenário 'cupom': preenchido quando alguém com permissão gera o(s) cupom(ns).
    codigo_cupom = Column(Text, nullable=True)
    gerado_por = Column(Integer, ForeignKey("dim_usuario.id"), nullable=True, index=True)
    gerado_em = Column(DateTime, nullable=True)

    # Cenário 'planilha': arquivo enviado pelo cliente + metadados básicos.
    nome_arquivo = Column(String(300), nullable=True)
    caminho_arquivo = Column(String(500), nullable=True)
    quantidade_linhas = Column(Integer, nullable=True)

    solicitado_por = Column(Integer, ForeignKey("dim_usuario.id"), nullable=False, index=True)
    created_at = Column(DateTime, default=_now_brasilia, index=True)
    updated_at = Column(DateTime, default=_now_brasilia, onupdate=_now_brasilia)
    deleted_at = Column(DateTime, nullable=True, index=True)
    deleted_by = Column(Integer, ForeignKey("dim_usuario.id"), nullable=True)

    evento = relationship("CadastroEvento")
    area_projecao = relationship("AreaProjecao")
    solicitante = relationship("Usuario", foreign_keys=[solicitado_por])
    gerador = relationship("Usuario", foreign_keys=[gerado_por])
    excluidor = relationship("Usuario", foreign_keys=[deleted_by])
    codigos = relationship("CortesiaCupomCodigo", back_populates="solicitacao", order_by="CortesiaCupomCodigo.id")


class CortesiaCupomCodigo(Base):
    """Uma linha por código de cupom gerado dentro de uma solicitação.
    Substitui o texto livre codigo_cupom (mantido para compatibilidade) com
    rastreamento individual de uso."""
    __tablename__ = "cortesia_cupom_codigo"

    id = Column(Integer, primary_key=True, index=True)
    solicitacao_id = Column(
        Integer,
        ForeignKey("cortesia_solicitacao.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    codigo = Column(String(300), nullable=False)
    # Prefixo fixo usado na geração (sigla+SKU, uppercased). Persisted para
    # permitir contagem exata de ocupação do espaço de sufixos sem ambiguidade
    # de prefixo entre bases distintas.
    base = Column(String(50), nullable=True)
    usado = Column(Boolean, nullable=False, default=False)
    usado_em = Column(DateTime, nullable=True)
    usado_por = Column(Integer, ForeignKey("dim_usuario.id"), nullable=True)
    created_at = Column(DateTime, default=_now_brasilia)

    solicitacao = relationship("CortesiaSolicitacao", back_populates="codigos")
    usuario_uso = relationship("Usuario", foreign_keys=[usado_por])
