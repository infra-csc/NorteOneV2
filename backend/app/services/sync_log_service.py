"""Helpers de gravação do log de sincronização (`sync_event_log`).

Toda gravação é best-effort: erros aqui NUNCA devem quebrar o job real.
"""
import uuid
import logging
from datetime import datetime, timedelta, date
from typing import Optional

from ..core.database import SessionLocal
from ..models.sync_event_log import SyncEventLog

logger = logging.getLogger(__name__)


def new_ciclo_id() -> str:
    """Gera um identificador curto para agrupar todas as linhas de um batch."""
    return uuid.uuid4().hex[:16]


def log_evento(
    ciclo_id: str,
    job_name: str,
    status: str,
    *,
    nivel: str = "grupo",
    grupo: Optional[str] = None,
    fonte: Optional[str] = None,
    motivo: Optional[str] = None,
    detalhes: Optional[str] = None,
    qtd_antes: Optional[int] = None,
    qtd_depois: Optional[int] = None,
    data_floor: Optional[date] = None,
    duracao_ms: Optional[int] = None,
) -> None:
    """Grava uma linha no log. Silencioso em caso de falha."""
    try:
        db = SessionLocal()
        try:
            entry = SyncEventLog(
                ciclo_id=ciclo_id,
                job_name=job_name,
                nivel=nivel,
                grupo=grupo,
                fonte=fonte,
                status=status,
                motivo=motivo,
                detalhes=(detalhes[:2000] if detalhes else None),
                qtd_antes=qtd_antes,
                qtd_depois=qtd_depois,
                data_floor=data_floor,
                duracao_ms=duracao_ms,
            )
            db.add(entry)
            db.commit()
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"[sync_log] gravação falhou (ignorado): {e}")


def log_evento_strict(
    ciclo_id: str,
    job_name: str,
    status: str,
    *,
    nivel: str = "grupo",
    grupo: Optional[str] = None,
    fonte: Optional[str] = None,
    motivo: Optional[str] = None,
    detalhes: Optional[str] = None,
    qtd_antes: Optional[int] = None,
    qtd_depois: Optional[int] = None,
    data_floor: Optional[date] = None,
    duracao_ms: Optional[int] = None,
) -> None:
    """Versão estrita que RE-RAISES em caso de falha.

    Usar apenas para marcadores críticos de coordenação (ex.: 'iniciado' de
    ciclo da consolidação diária) onde a ausência do log permitiria duplicidade.
    """
    db = SessionLocal()
    try:
        entry = SyncEventLog(
            ciclo_id=ciclo_id,
            job_name=job_name,
            nivel=nivel,
            grupo=grupo,
            fonte=fonte,
            status=status,
            motivo=motivo,
            detalhes=(detalhes[:2000] if detalhes else None),
            qtd_antes=qtd_antes,
            qtd_depois=qtd_depois,
            data_floor=data_floor,
            duracao_ms=duracao_ms,
        )
        db.add(entry)
        db.commit()
    finally:
        db.close()


# Chave fixa do advisory lock cross-process da consolidação diária 02h BRT.
# Compartilhada entre: endpoint /api/admin/scheduled-jobs/consolidacao-diaria,
# catch-up de startup (main.py) e scheduler interno (cache.py).
CONSOLIDACAO_DIARIA_LOCK_KEY = 7423919204


def acquire_consolidation_lock():
    """Tenta adquirir advisory lock pg da consolidação diária.

    Retorna o objeto connection se obteve o lock (caller DEVE chamar
    release_consolidation_lock para liberar e fechar). Retorna None se outro
    processo já o detém — caller deve abortar/pular execução para evitar
    cycles duplicados em paralelo.
    """
    from sqlalchemy import text
    from ..core.database import engine
    try:
        conn = engine.raw_connection()
    except Exception as e:
        logger.error(f"[ConsolidacaoLock] raw_connection falhou: {e}")
        raise
    try:
        cur = conn.cursor()
        cur.execute(f"SELECT pg_try_advisory_lock({CONSOLIDACAO_DIARIA_LOCK_KEY})")
        got = bool(cur.fetchone()[0])
        cur.close()
        if not got:
            try:
                conn.close()
            except Exception:
                pass
            return None
        return conn
    except Exception:
        try:
            conn.close()
        except Exception:
            pass
        raise


def release_consolidation_lock(conn) -> None:
    """Libera o advisory lock e fecha a connection. Silencioso em caso de erro."""
    if conn is None:
        return
    try:
        cur = conn.cursor()
        cur.execute(f"SELECT pg_advisory_unlock({CONSOLIDACAO_DIARIA_LOCK_KEY})")
        cur.close()
    except Exception as e:
        logger.warning(f"[ConsolidacaoLock] unlock falhou (ignorado): {e}")
    try:
        conn.close()
    except Exception:
        pass


def classify_motivo(exc: BaseException) -> str:
    """Heurística pra rotular falhas com códigos curtos exibíveis na UI."""
    msg = str(exc).lower()
    if "max_execution_time" in msg or "max execution time" in msg or "3024" in msg:
        return "magento_timeout"
    if "lost connection" in msg or "gone away" in msg or "broken pipe" in msg or "server has gone" in msg:
        return "conexao_perdida"
    if "ssh" in msg or "tunnel" in msg or "engine_ssh" in msg:
        return "ssh_down"
    if "circuitopen" in msg or "circuit open" in msg or "circuit_open" in msg:
        return "circuit_aberto"
    if "queuepool" in msg or "queue pool" in msg or "pool limit" in msg or "queuepool limit" in msg:
        return "pool_exaurido"
    if "operationalerror" in msg or "operational error" in msg:
        return "erro_operacional"
    if "timeout" in msg or "timed out" in msg:
        return "timeout"
    if "no_mappings" in msg or "sem mapeamento" in msg or "sem mappings" in msg:
        return "sem_mapeamento"
    return "erro_generico"


def cleanup_old(days: int = 30) -> int:
    """Apaga logs com mais de N dias. Retorna quantidade removida."""
    try:
        db = SessionLocal()
        try:
            cutoff = datetime.utcnow() - timedelta(days=days)
            removed = db.query(SyncEventLog).filter(SyncEventLog.created_at < cutoff).delete(synchronize_session=False)
            db.commit()
            return int(removed or 0)
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"[sync_log] cleanup falhou: {e}")
        return 0
