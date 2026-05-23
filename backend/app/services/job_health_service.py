import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


def record_job_run(
    job_name: str,
    started_at: datetime,
    grupos_total: int,
    grupos_ok: int = 0,
    grupos_parcial: int = 0,
    grupos_falha: int = 0,
    grupos_pulado: int = 0,
    status: str = "concluido",
    extra: Optional[str] = None,
) -> None:
    try:
        from app.core.database import SessionLocal
        from app.models.job_run_health import JobRunHealth
        finished_at = datetime.now(timezone.utc)
        if started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=timezone.utc)
        duration_ms = int((finished_at - started_at).total_seconds() * 1000)
        db = SessionLocal()
        try:
            row = JobRunHealth(
                job_name=job_name,
                started_at=started_at,
                finished_at=finished_at,
                duration_ms=duration_ms,
                grupos_total=grupos_total,
                grupos_ok=grupos_ok,
                grupos_parcial=grupos_parcial,
                grupos_falha=grupos_falha,
                grupos_pulado=grupos_pulado,
                status=status,
                extra=extra,
            )
            db.add(row)
            db.commit()
        except Exception as e:
            db.rollback()
            logger.warning(f"[JobHealth] Falha ao gravar métrica de '{job_name}': {e}")
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"[JobHealth] DB session error: {e}")


def maybe_alert_high_partial_ratio(
    job_name: str,
    grupos_total: int,
    grupos_parcial: int,
    grupos_falha: int = 0,
    threshold: float = 0.20,
) -> None:
    """Dispara alerta HIGH quando >20% dos grupos caíram em parcial+falha."""
    if grupos_total <= 0:
        return
    ratio = (grupos_parcial + grupos_falha) / grupos_total
    if ratio < threshold:
        return
    try:
        from app.services.health_alert_service import log_and_alert
        pct = ratio * 100
        log_and_alert(
            "SYNC_PARTIAL_HIGH",
            "HIGH",
            f"{job_name}: {pct:.1f}% dos grupos em parcial/falha "
            f"({grupos_parcial} parcial + {grupos_falha} falha de {grupos_total})",
            f"Provável instabilidade Magento/Ativo — snapshots usados como piso. "
            f"Verifique logs do túnel SSH e estado do Magento.",
        )
    except Exception as e:
        logger.warning(f"[JobHealth] Falha ao disparar alerta: {e}")
