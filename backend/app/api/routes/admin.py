from datetime import datetime, timedelta
from fastapi import APIRouter, Depends
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
