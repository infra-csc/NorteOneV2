from datetime import datetime, date, timedelta
from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import desc, func as sa_func
from typing import Optional
from ...core.database import get_db
from ...core.security import require_permission
from ...models.user import Usuario
from ...models.sync_event_log import SyncEventLog

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


@router.get("/sync-logs/cycles")
def list_sync_cycles(
    job: Optional[str] = Query(default=None, description="Filtra por job_name"),
    status: Optional[str] = Query(default=None, description="Filtra por status do ciclo"),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("admin_monitoramento")),
):
    """Lista os ciclos mais recentes de jobs de sincronização.

    Cada ciclo é identificado por `ciclo_id` e agrega múltiplos eventos.
    Retorna o evento de nível 'ciclo' mais recente de cada ciclo + agregados
    dos eventos de grupo (ok, parcial, falha, pulado).
    """
    cycle_ids_query = db.query(
        SyncEventLog.ciclo_id,
        sa_func.max(SyncEventLog.created_at).label("ultimo"),
    ).group_by(SyncEventLog.ciclo_id).order_by(desc("ultimo")).limit(limit)
    if job:
        cycle_ids_query = db.query(
            SyncEventLog.ciclo_id,
            sa_func.max(SyncEventLog.created_at).label("ultimo"),
        ).filter(SyncEventLog.job_name == job).group_by(SyncEventLog.ciclo_id).order_by(desc("ultimo")).limit(limit)

    cycle_ids = [row[0] for row in cycle_ids_query.all()]
    if not cycle_ids:
        return {"cycles": []}

    rows = db.query(SyncEventLog).filter(SyncEventLog.ciclo_id.in_(cycle_ids)).all()

    by_cycle: dict = {}
    for r in rows:
        c = by_cycle.setdefault(r.ciclo_id, {
            "ciclo_id": r.ciclo_id,
            "job_name": None,
            "fallback_job_name": r.job_name,
            "ciclo_iniciado_at": None,
            "ciclo_concluido_at": None,
            "iniciado_em": None,
            "concluido_em": None,
            "status": "iniciado",
            "duracao_ms": None,
            "detalhes_ciclo": None,
            "motivo_ciclo": None,
            "total_grupos": 0,
            "ok": 0, "parcial": 0, "falha": 0, "pulado": 0,
            "ultima_atividade": None,
            "first_failure_motivo": None,
        })
        if not c["ultima_atividade"] or r.created_at > c["ultima_atividade"]:
            c["ultima_atividade"] = r.created_at
        if r.nivel == "ciclo":
            # job_name autoritativo vem das linhas nivel='ciclo' (registradas pelo
            # batch raiz). Em caso de múltiplas, prevalece a mais antiga ('iniciado').
            if r.status == "iniciado":
                if not c["ciclo_iniciado_at"] or r.created_at < c["ciclo_iniciado_at"]:
                    c["ciclo_iniciado_at"] = r.created_at
                    c["job_name"] = r.job_name
                    c["iniciado_em"] = r.created_at
            else:
                if not c["ciclo_concluido_at"] or r.created_at > c["ciclo_concluido_at"]:
                    c["ciclo_concluido_at"] = r.created_at
                    c["concluido_em"] = r.created_at
                    c["status"] = r.status
                    c["duracao_ms"] = r.duracao_ms
                    c["detalhes_ciclo"] = r.detalhes
                    c["motivo_ciclo"] = r.motivo
                    if not c["job_name"]:
                        c["job_name"] = r.job_name
        else:
            if r.grupo:
                c["total_grupos"] += 1
            if r.status in c:
                c[r.status] += 1
            if r.status in ("falha", "parcial") and not c["first_failure_motivo"]:
                c["first_failure_motivo"] = r.motivo

    result = []
    for c in by_cycle.values():
        if c["status"] == "iniciado" and not c["concluido_em"]:
            age = (datetime.utcnow() - (c["iniciado_em"] or c["ultima_atividade"]).replace(tzinfo=None)).total_seconds() if (c["iniciado_em"] or c["ultima_atividade"]) else 0
            if age > 3600:
                c["status"] = "interrompido"
        result.append({
            "ciclo_id": c["ciclo_id"],
            "job_name": c["job_name"] or c["fallback_job_name"],
            "iniciado_em": c["iniciado_em"].isoformat() if c["iniciado_em"] else None,
            "concluido_em": c["concluido_em"].isoformat() if c["concluido_em"] else None,
            "ultima_atividade": c["ultima_atividade"].isoformat() if c["ultima_atividade"] else None,
            "status": c["status"],
            "duracao_ms": c["duracao_ms"],
            "detalhes": c["detalhes_ciclo"],
            "motivo": c["motivo_ciclo"] or c["first_failure_motivo"],
            "total_grupos": c["total_grupos"],
            "ok": c["ok"],
            "parcial": c["parcial"],
            "falha": c["falha"],
            "pulado": c["pulado"],
        })
    result.sort(key=lambda x: x["ultima_atividade"] or "", reverse=True)
    if status:
        result = [c for c in result if c["status"] == status]
    return {"cycles": result}


@router.get("/sync-logs/{ciclo_id}")
def get_sync_cycle_detail(
    ciclo_id: str,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("admin_monitoramento")),
):
    """Detalhe de um ciclo — todos os eventos (ciclo + grupos)."""
    rows = db.query(SyncEventLog).filter(
        SyncEventLog.ciclo_id == ciclo_id
    ).order_by(SyncEventLog.created_at.asc(), SyncEventLog.id.asc()).all()

    if not rows:
        raise HTTPException(status_code=404, detail="Ciclo não encontrado")

    return {
        "ciclo_id": ciclo_id,
        "events": [
            {
                "id": r.id,
                "nivel": r.nivel,
                "job_name": r.job_name,
                "grupo": r.grupo,
                "fonte": r.fonte,
                "status": r.status,
                "motivo": r.motivo,
                "detalhes": r.detalhes,
                "qtd_antes": r.qtd_antes,
                "qtd_depois": r.qtd_depois,
                "data_floor": r.data_floor.isoformat() if r.data_floor else None,
                "duracao_ms": r.duracao_ms,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
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
    date_from: Optional[str] = Query(default=None, description="ISO date string (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(default=None, description="ISO date string (YYYY-MM-DD)"),
    show_resolved: Optional[str] = Query(default=None, description="'true'=only resolved, 'false'=only unresolved, omit=all"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("admin_monitoramento")),
):
    from ...models.system_health import SystemHealthEvent
    query = db.query(SystemHealthEvent).order_by(desc(SystemHealthEvent.created_at))
    if severity:
        query = query.filter(SystemHealthEvent.severity == severity.upper())
    if event_type:
        query = query.filter(SystemHealthEvent.event_type == event_type.upper())
    if date_from:
        try:
            dt_from = datetime.fromisoformat(date_from)
            query = query.filter(SystemHealthEvent.created_at >= dt_from)
        except ValueError:
            pass
    if date_to:
        try:
            dt_to = datetime.fromisoformat(date_to)
            from datetime import timedelta
            dt_to = dt_to + timedelta(days=1)
            query = query.filter(SystemHealthEvent.created_at < dt_to)
        except ValueError:
            pass
    if show_resolved == "true":
        query = query.filter(SystemHealthEvent.resolved_at.isnot(None))
    elif show_resolved == "false":
        query = query.filter(SystemHealthEvent.resolved_at.is_(None))
    total_count = query.count()
    offset = (page - 1) * page_size
    events = query.offset(offset).limit(page_size).all()
    return {
        "events": [e.to_dict() for e in events],
        "total": total_count,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, (total_count + page_size - 1) // page_size),
    }


@router.post("/health-events/{event_id}/resolve")
def resolve_health_event(
    event_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("admin_monitoramento")),
):
    from ...models.system_health import SystemHealthEvent
    event = db.query(SystemHealthEvent).filter(SystemHealthEvent.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Evento não encontrado")
    event.resolved_at = datetime.utcnow()
    event.resolved_by = current_user.nome or current_user.email
    db.commit()
    return {"status": "ok", "event": event.to_dict()}


@router.post("/health-events/{event_id}/reopen")
def reopen_health_event(
    event_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("admin_monitoramento")),
):
    from ...models.system_health import SystemHealthEvent
    event = db.query(SystemHealthEvent).filter(SystemHealthEvent.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Evento não encontrado")
    event.resolved_at = None
    event.resolved_by = None
    db.commit()
    return {"status": "ok", "event": event.to_dict()}


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

    # --- Fontes de dados: última falha por source nas últimas 24h ---
    DATA_SOURCE_GROUPS = {
        "magento": ["MARGEM_MAGENTO_FAILED"],
        "ativo": ["MARGEM_ATIVO_FAILED"],
        "ssh": ["SSH_TUNNEL_DOWN", "SSH_TUNNEL_RECONNECT_FAILED"],
        "cache": ["WARMUP_FAILED", "DAILY_REFRESH_FAILED", "ISC_REFRESH_FAILED"],
        "sync": ["SYNC_BATCH_FAILED", "STARTUP_RESYNC_FAILED"],
    }
    data_sources = {}
    for source, event_types in DATA_SOURCE_GROUPS.items():
        fail_count = (
            db.query(func.count(SystemHealthEvent.id))
            .filter(
                SystemHealthEvent.event_type.in_(event_types),
                SystemHealthEvent.created_at >= last_24h,
            )
            .scalar()
        ) or 0
        last_failure = (
            db.query(SystemHealthEvent)
            .filter(
                SystemHealthEvent.event_type.in_(event_types),
                SystemHealthEvent.created_at >= last_24h,
            )
            .order_by(desc(SystemHealthEvent.created_at))
            .first()
        )
        data_sources[source] = {
            "failures_24h": fail_count,
            "last_failure": last_failure.to_dict() if last_failure else None,
        }

    return {
        "status": status,
        "critical_24h": critical_24h,
        "high_24h": high_24h,
        "total_24h": total_24h,
        "last_event": last_event.to_dict() if last_event else None,
        "data_sources": data_sources,
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
    if payload.slack_webhook_url and payload.slack_webhook_url.strip():
        cfg.slack_webhook_url = payload.slack_webhook_url
    cfg.min_severity = payload.min_severity

    db.commit()
    return {"status": "ok", "message": "Configuração salva com sucesso"}


@router.post("/sync/pause")
def pause_sync_jobs(
    current_user: Usuario = Depends(require_permission("admin_monitoramento")),
):
    """Pausa a execução dos jobs de sincronização entre iterações de grupo."""
    from ...core.cache import pause_sync
    pause_sync(by=f"{current_user.nome} ({current_user.email})")
    return {"status": "paused", "message": "Jobs de sincronização pausados. A pausa será aplicada na próxima iteração de cada job em execução."}


@router.post("/sync/resume")
def resume_sync_jobs(
    current_user: Usuario = Depends(require_permission("admin_monitoramento")),
):
    """Retoma a execução dos jobs de sincronização."""
    from ...core.cache import resume_sync
    resume_sync(by=f"{current_user.nome} ({current_user.email})")
    return {"status": "active", "message": "Jobs de sincronização retomados."}


@router.post("/sync/interrupt")
def interrupt_sync_jobs(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("admin_monitoramento")),
):
    """Interrompe imediatamente os jobs de sincronização em execução:
    1. Ativa o flag de pausa (impede novas iterações de grupo).
    2. Marca todos os ciclos com status 'iniciado' como 'interrompido' no banco,
       sem aguardar a iteração atual terminar.
    """
    from ...core.cache import pause_sync
    from datetime import datetime as _dt
    import time as _t

    pause_sync(by=f"{current_user.nome} ({current_user.email})")

    now_ms = int(_t.time() * 1000)
    updated = (
        db.query(SyncEventLog)
        .filter(SyncEventLog.status == "iniciado", SyncEventLog.nivel == "ciclo")
        .update(
            {
                "status": "interrompido",
                "motivo": "interrupcao_manual",
                "detalhes": f"Interrompido manualmente por {current_user.nome} ({current_user.email})",
            },
            synchronize_session=False,
        )
    )
    db.commit()

    return {
        "status": "interrupted",
        "message": f"Execuções interrompidas. {updated} ciclo(s) marcado(s) como interrompido no banco. Pausa ativada para impedir novas iterações.",
        "cycles_interrupted": updated,
    }


@router.get("/sync/pause-status")
def get_sync_pause_status(
    current_user: Usuario = Depends(require_permission("admin_monitoramento")),
):
    """Retorna o estado atual de pausa dos jobs de sincronização."""
    from ...core.cache import get_sync_pause_info
    return get_sync_pause_info()


@router.post("/alert-config/test")
def test_alert(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("admin_monitoramento")),
):
    from app.services.health_alert_service import log_event, _dispatch_alert_force
    log_event(
        event_type="TEST",
        severity="INFO",
        message="Teste de alerta enviado manualmente",
        detail=f"Disparado por {current_user.nome} ({current_user.email})",
    )
    import threading as _threading
    _threading.Thread(
        target=_dispatch_alert_force,
        args=("TEST", "INFO", "Teste de alerta enviado manualmente", f"Disparado por {current_user.nome} ({current_user.email})"),
        daemon=True,
    ).start()
    return {"status": "ok", "message": "Alerta de teste enviado (ignora filtro de severidade)"}
