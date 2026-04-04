import json
from datetime import datetime, date
from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import desc
from typing import Optional, List
from ...core.database import get_db
from ...core.security import require_permission
from ...models.user import Usuario

router = APIRouter(prefix="/api/admin", tags=["Admin"])

ONLINE_THRESHOLD_MINUTES = 5
AWAY_THRESHOLD_MINUTES = 30


@router.get("/user-activity")
def get_user_activity(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("admin_monitoramento")),
):
    now = datetime.utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    users = (
        db.query(Usuario)
        .options(joinedload(Usuario.perfil_acesso_rel))
        .filter(Usuario.ativo == True)
        .order_by(Usuario.last_activity.desc().nullslast(), Usuario.nome)
        .all()
    )

    online_count = 0
    away_count = 0
    active_today_count = 0
    user_list = []

    for u in users:
        if u.last_activity:
            diff = now - u.last_activity
            minutes_ago = diff.total_seconds() / 60

            if minutes_ago <= ONLINE_THRESHOLD_MINUTES:
                status = "online"
                online_count += 1
            elif minutes_ago <= AWAY_THRESHOLD_MINUTES:
                status = "ausente"
                away_count += 1
            else:
                status = "offline"

            if u.last_activity >= today_start:
                active_today_count += 1
        else:
            status = "offline"
            minutes_ago = None

        perfil_nome = None
        if u.perfil_acesso_rel:
            perfil_nome = u.perfil_acesso_rel.nome

        user_list.append({
            "id": u.id,
            "nome": u.nome,
            "email": u.email,
            "perfil_acesso": perfil_nome,
            "status": status,
            "last_activity": u.last_activity.isoformat() if u.last_activity else None,
        })

    return {
        "resumo": {
            "total_usuarios": len(users),
            "online": online_count,
            "ausentes": away_count,
            "ativos_hoje": active_today_count,
        },
        "usuarios": user_list,
    }


@router.post("/snapshots/consolidar")
def trigger_snapshot_consolidation(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("marketing")),
):
    import threading
    import logging
    logger = logging.getLogger(__name__)

    def _run():
        from app.core.database import SessionLocal
        from app.services.snapshot_service import snapshot_diario_batch, consolidar_curvas_historicas_batch, sincronizar_hoje_batch
        local_db = SessionLocal()
        try:
            grupos = snapshot_diario_batch(local_db)
            curvas = consolidar_curvas_historicas_batch(local_db)
            hoje = sincronizar_hoje_batch(local_db)
            logger.info(f"Manual snapshot consolidation: {grupos} grupos, {curvas} curvas, {hoje} hoje")
        except Exception as e:
            logger.error(f"Manual snapshot consolidation failed: {e}")
        finally:
            local_db.close()

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()

    return {
        "status": "started",
        "message": "Consolidação de snapshots iniciada em background"
    }


@router.post("/snapshots/backfill")
def trigger_backfill(
    ano: int = Query(..., description="Ano para backfill"),
    data_inicio: str = Query(default=None, description="Data início (YYYY-MM-DD)"),
    data_fim: str = Query(default=None, description="Data fim (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("marketing")),
):
    from ...services.snapshot_service import backfill_historico
    import logging
    logger = logging.getLogger(__name__)

    start = date.fromisoformat(data_inicio) if data_inicio else None
    end = date.fromisoformat(data_fim) if data_fim else None

    try:
        result = backfill_historico(db, ano, data_inicio=start, data_fim=end)
        return {
            "status": "completed",
            "resultado": result
        }
    except Exception as e:
        logger.error(f"Backfill failed: {e}")
        return {
            "status": "error",
            "message": str(e)
        }


@router.get("/snapshots/status")
def get_snapshot_status(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("marketing")),
):
    from sqlalchemy import func
    from ...models.vendas_snapshot import VendasDiariaSnapshot, CurvaHistoricaSnapshot

    total_snapshots = db.query(func.count(VendasDiariaSnapshot.id)).scalar()
    total_curvas = db.query(func.count(CurvaHistoricaSnapshot.id)).scalar()

    grupos_snapshot = db.query(
        func.count(func.distinct(VendasDiariaSnapshot.evento_grupo))
    ).scalar()
    grupos_curva = db.query(
        func.count(func.distinct(CurvaHistoricaSnapshot.evento_grupo))
    ).scalar()

    latest_date = db.query(func.max(VendasDiariaSnapshot.data_venda)).scalar()
    earliest_date = db.query(func.min(VendasDiariaSnapshot.data_venda)).scalar()

    return {
        "vendas_snapshot": {
            "total_registros": total_snapshots,
            "total_grupos": grupos_snapshot,
            "data_mais_antiga": earliest_date.isoformat() if earliest_date else None,
            "data_mais_recente": latest_date.isoformat() if latest_date else None,
        },
        "curva_historica": {
            "total_registros": total_curvas,
            "total_grupos": grupos_curva,
        }
    }


@router.get("/health-events")
def get_health_events(
    severity: Optional[str] = Query(default=None),
    event_type: Optional[str] = Query(default=None),
    limit: int = Query(default=100, le=500),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("admin_monitoramento")),
):
    from ...models.system_health import SystemHealthEvent
    query = db.query(SystemHealthEvent).order_by(desc(SystemHealthEvent.created_at))
    if severity:
        query = query.filter(SystemHealthEvent.severity == severity.upper())
    if event_type:
        query = query.filter(SystemHealthEvent.event_type == event_type.upper())
    events = query.limit(limit).all()
    return {
        "events": [e.to_dict() for e in events],
        "total": len(events),
    }


@router.get("/health-events/summary")
def get_health_summary(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("admin_monitoramento")),
):
    from sqlalchemy import func
    from datetime import timedelta
    from ...models.system_health import SystemHealthEvent

    now = datetime.utcnow()
    last_24h = now - timedelta(hours=24)
    last_event = (
        db.query(SystemHealthEvent)
        .order_by(desc(SystemHealthEvent.created_at))
        .first()
    )
    critical_24h = (
        db.query(func.count(SystemHealthEvent.id))
        .filter(SystemHealthEvent.severity == "CRITICAL", SystemHealthEvent.created_at >= last_24h)
        .scalar()
    ) or 0
    high_24h = (
        db.query(func.count(SystemHealthEvent.id))
        .filter(SystemHealthEvent.severity == "HIGH", SystemHealthEvent.created_at >= last_24h)
        .scalar()
    ) or 0
    total_24h = (
        db.query(func.count(SystemHealthEvent.id))
        .filter(SystemHealthEvent.created_at >= last_24h)
        .scalar()
    ) or 0

    if critical_24h > 0:
        status = "critical"
    elif high_24h > 0:
        status = "warning"
    elif total_24h > 0:
        status = "info"
    else:
        status = "healthy"

    return {
        "status": status,
        "critical_24h": critical_24h,
        "high_24h": high_24h,
        "total_24h": total_24h,
        "last_event": last_event.to_dict() if last_event else None,
    }


class AlertConfigRequest(BaseModel):
    email_enabled: bool = False
    email_recipients: Optional[str] = None
    email_from: Optional[str] = None
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = 587
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None
    slack_enabled: bool = False
    slack_webhook_url: Optional[str] = None
    min_severity: str = "HIGH"


@router.get("/alert-config")
def get_alert_config(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("admin_monitoramento")),
):
    from ...models.system_health import SystemAlertConfig
    cfg = db.query(SystemAlertConfig).filter(SystemAlertConfig.id == 1).first()
    if not cfg:
        return SystemAlertConfig(id=1).to_dict()
    return cfg.to_dict()


@router.put("/alert-config")
def update_alert_config(
    payload: AlertConfigRequest,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("admin_monitoramento")),
):
    from ...models.system_health import SystemAlertConfig
    cfg = db.query(SystemAlertConfig).filter(SystemAlertConfig.id == 1).first()
    if not cfg:
        cfg = SystemAlertConfig(id=1)
        db.add(cfg)

    cfg.email_enabled = payload.email_enabled
    cfg.email_recipients = payload.email_recipients
    cfg.email_from = payload.email_from
    cfg.smtp_host = payload.smtp_host
    cfg.smtp_port = payload.smtp_port or 587
    cfg.smtp_user = payload.smtp_user
    if payload.smtp_password and payload.smtp_password != "***":
        cfg.smtp_password = payload.smtp_password
    cfg.slack_enabled = payload.slack_enabled
    cfg.slack_webhook_url = payload.slack_webhook_url
    cfg.min_severity = payload.min_severity

    db.commit()
    return {"status": "ok", "message": "Configuração salva com sucesso"}


@router.post("/alert-config/test")
def test_alert(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("admin_monitoramento")),
):
    from app.services.health_alert_service import log_and_alert
    log_and_alert(
        event_type="TEST",
        severity="INFO",
        message="Teste de alerta enviado manualmente",
        detail=f"Disparado por {current_user.nome} ({current_user.email})",
    )
    return {"status": "ok", "message": "Alerta de teste enviado"}
