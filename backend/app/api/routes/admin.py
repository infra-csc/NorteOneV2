from datetime import datetime, date
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session, joinedload
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
        from app.services.snapshot_service import snapshot_diario_batch, consolidar_curvas_historicas_batch
        local_db = SessionLocal()
        try:
            grupos = snapshot_diario_batch(local_db)
            curvas = consolidar_curvas_historicas_batch(local_db)
            logger.info(f"Manual snapshot consolidation: {grupos} grupos, {curvas} curvas")
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
