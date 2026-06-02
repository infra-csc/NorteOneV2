"""Conclusão automática de eventos cuja data já passou.

Regra: um evento com `data_evento < hoje` e status `Em andamento` passa
automaticamente para `Concluído`. Eventos `Cancelado` ou já `Concluído`
(inclusive os concluídos manualmente) nunca são alterados, assim como
eventos sem data definida.

Esta função é a fonte única usada tanto pela listagem (gravação na hora do
acesso) quanto pelo job noturno de garantia, mantendo `cadastro_evento` e
`dim_projeto` em lockstep.
"""

import logging
from datetime import date

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models.cadastro_evento import CadastroEvento
from app.models.dimensoes import DimProjeto

logger = logging.getLogger(__name__)

_EM_ANDAMENTO = "Em andamento"
_CONCLUIDO = "Concluído"


def auto_concluir_eventos_passados(db: Session) -> int:
    """Marca como 'Concluído' os eventos com data passada ainda 'Em andamento'.

    Retorna a quantidade de cadastros alterados. Mantém `dim_projeto`
    sincronizado pelo SKU (codigo). Faz commit ao final somente quando há
    alterações; em caso de erro, faz rollback e propaga.
    """
    hoje = date.today()
    try:
        result = db.execute(
            update(CadastroEvento)
            .where(
                CadastroEvento.deleted_at.is_(None),
                CadastroEvento.status == _EM_ANDAMENTO,
                CadastroEvento.data_evento.isnot(None),
                CadastroEvento.data_evento < hoje,
            )
            .values(status=_CONCLUIDO)
        )
        alterados = result.rowcount or 0

        if alterados:
            # Sincroniza dim_projeto pelos SKUs dos cadastros recém-concluídos.
            db.execute(
                update(DimProjeto)
                .where(
                    DimProjeto.codigo.in_(
                        db.query(CadastroEvento.sku).filter(
                            CadastroEvento.deleted_at.is_(None),
                            CadastroEvento.status == _CONCLUIDO,
                            CadastroEvento.data_evento.isnot(None),
                            CadastroEvento.data_evento < hoje,
                            CadastroEvento.sku.isnot(None),
                        )
                    ),
                    DimProjeto.status == _EM_ANDAMENTO,
                )
                .values(status=_CONCLUIDO)
            )
            db.commit()
            logger.warning(
                f"[AutoConcluir] {alterados} evento(s) marcados como 'Concluído' "
                f"(data_evento < {hoje.isoformat()})."
            )
        return alterados
    except Exception as e:
        db.rollback()
        logger.error(f"[AutoConcluir] Falha ao concluir eventos passados: {e}")
        raise
