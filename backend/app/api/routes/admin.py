from datetime import datetime, date, timedelta, timezone
from fastapi import APIRouter, Depends, Query, HTTPException, Header
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import desc, func as sa_func
from typing import Optional
import threading as _threading
import time as _time_module
import copy as _copy
import os as _os
from concurrent.futures import ThreadPoolExecutor as _TPE, as_completed as _as_completed
from ...core.database import get_db
from ...core.security import require_permission
from ...models.user import Usuario
from ...models.sync_event_log import SyncEventLog

router = APIRouter(prefix="/api/admin", tags=["Admin"])

_SYNC_OVERVIEW_CACHE_TTL = 5
_sync_overview_cache = {"data": None, "ts": 0.0}
_sync_overview_cache_lock = _threading.Lock()
_USER_ACTIVITY_CACHE_TTL = 10
_user_activity_cache = {"data": None, "ts": 0.0}
_user_activity_cache_lock = _threading.Lock()

# ── Consolidação Full Manual — rastreamento em memória ──────────────────────
_consolidation_full_lock = _threading.Lock()
_consolidation_full_progress: dict = {
    "status": "idle",
    "started_at": None,
    "finished_at": None,
    "triggered_by": None,
    "total": 0,
    "current": 0,
    "current_grupo": None,
    "ok": 0,
    "failed": 0,
    "skipped": 0,
    "frozen": 0,
    "results": [],
    "ciclo_id": None,
    "error": None,
    # Fase de preparação (ANTES do total ser conhecido): texto curto
    # descrevendo o passo atual ("Carregando mapeamento de SKUs",
    # "Identificando eventos ativos", etc.). Frontend usa pra mostrar
    # "Preparando…" em vez de "Processando 0%".
    "setup_step": None,
    # Lista ordenada dos grupos a processar (preenchida 1 vez após o
    # cálculo). Frontend mostra como "fila"; à medida que cada grupo
    # termina, ele é removido aqui pra a UI refletir só o que falta.
    "grupos_pendentes": [],
    # Grupos em execução nesta janela (até CONSOLIDAR_FULL_WORKERS).
    # Cada item: {"grupo": str, "started_at": float epoch}.
    "em_execucao": [],
    # Auto-retry: tentativa atual / máximo. Quando o ciclo termina com
    # `failed > 0` ou `status == "error"` e `auto_retry=True`, um timer
    # agenda nova execução em `auto_retry_delay_sec` segundos usando o
    # mesmo checkpoint (retoma só os grupos que faltaram).
    "auto_retry": False,
    "auto_retry_attempt": 1,
    "auto_retry_max_attempts": 1,
    "auto_retry_next_at": None,  # epoch da próxima tentativa agendada
}

# Timer ativo de auto-retry (para conseguirmos cancelar se o usuário
# disparar manualmente uma nova consolidação no meio do intervalo).
_consolidation_retry_lock = _threading.Lock()
_consolidation_retry_timer: Optional[_threading.Timer] = None

# Geração da consolidação. Incrementado a cada disparo manual e a cada
# cancelamento. O _maybe_schedule_auto_retry e o _fire() guardam a geração
# que enxergavam no início e abortam se ela mudou — impede que o `finally`
# de um ciclo antigo (lento) reagende um timer "fantasma" depois que o
# usuário já cancelou ou disparou outra consolidação.
_consolidation_generation: int = 0


def _bump_consolidation_generation() -> int:
    """Invalida qualquer auto-retry pendente do ciclo anterior. Retorna
    o novo número de geração. Deve ser chamado sob `_consolidation_retry_lock`."""
    global _consolidation_generation
    _consolidation_generation += 1
    return _consolidation_generation


def _cancel_pending_auto_retry(invalidate_generation: bool = True) -> bool:
    """Cancela um timer de auto-retry pendente (se houver). Se
    `invalidate_generation=True` (default), também invalida a geração
    atual, garantindo que qualquer `_finally` em execução de ciclo anterior
    NÃO agende um novo timer e que `_fire()`s do ciclo anterior abortem.

    Use `invalidate_generation=False` apenas internamente, quando o próprio
    `_maybe_schedule_auto_retry` está prestes a substituir o timer pelo
    próximo da MESMA geração (não queremos invalidar a si mesmo)."""
    global _consolidation_retry_timer
    cancelled = False
    with _consolidation_retry_lock:
        if _consolidation_retry_timer is not None:
            try:
                _consolidation_retry_timer.cancel()
            except Exception:
                pass
            _consolidation_retry_timer = None
            cancelled = True
        if invalidate_generation:
            _bump_consolidation_generation()
    return cancelled


def _current_consolidation_generation() -> int:
    with _consolidation_retry_lock:
        return _consolidation_generation


# ── Cooldown por evento (Reconsolidar individual) ─────────────────────────
# Quando um usuário com perfil "Diretoria" reconsolida um evento com sucesso,
# o evento fica bloqueado por DIRETORIA_RECONSOLIDAR_COOLDOWN_SEC (padrão 1200s
# = 20min). Usuários de outros perfis (Admin, etc) NÃO são afetados pelo lock.
# Evita que clique compulsivo ou recarregamento de página por parte da diretoria
# dispare uma reconsolidação pesada (Magento + Ativo) repetidas vezes.
_evento_cooldown_lock = _threading.Lock()
_evento_cooldown: dict = {}  # {evento_grupo: locked_until_epoch}
_evento_inflight: set = set()  # eventos em reconsolidação manual AGORA (gate global, qualquer perfil)
DIRETORIA_PERFIL_NOME = "Diretoria"


def _diretoria_cooldown_sec() -> int:
    try:
        return max(0, int(_os.getenv("DIRETORIA_RECONSOLIDAR_COOLDOWN_SEC", "1200")))
    except (TypeError, ValueError):
        return 1200


def _user_is_diretoria(user: Usuario) -> bool:
    perfil = getattr(user, "perfil_acesso_rel", None)
    if not perfil:
        return False
    nome = (getattr(perfil, "nome", "") or "").strip().lower()
    return nome == DIRETORIA_PERFIL_NOME.lower()


def _evento_cooldown_remaining(evento_grupo: str) -> int:
    """Retorna segundos restantes do cooldown (0 se expirou ou não existe).
    Apenas leitura — NÃO use para gate atômico; use `_try_acquire_evento_slot`."""
    with _evento_cooldown_lock:
        until = _evento_cooldown.get(evento_grupo)
    if not until:
        return 0
    now = _time_module.time()
    if now >= until:
        with _evento_cooldown_lock:
            _evento_cooldown.pop(evento_grupo, None)
        return 0
    return int(until - now)


def _try_acquire_evento_slot(evento_grupo: str, check_cooldown: bool) -> tuple[bool, int, Optional[str]]:
    """Gate ATÔMICO global: garante que NO MÁXIMO um evento esteja sendo
    reconsolidado no sistema inteiro de cada vez. Se `check_cooldown=True`
    (Diretoria), também verifica cooldown do próprio evento.

    Retorna `(acquired, remaining_sec, busy_evento_grupo)`:
    - `(True, 0, None)`              — slot adquirido, pode prosseguir.
    - `(False, remaining_sec, None)` — bloqueado por cooldown deste evento.
    - `(False, 0, <grupo>)`          — outra reconsolidação em curso. `<grupo>`
      é o evento que está rodando agora (pode ser o mesmo, se o usuário
      clicou duas vezes, ou outro qualquer).
    """
    now = _time_module.time()
    with _evento_cooldown_lock:
        if check_cooldown:
            until = _evento_cooldown.get(evento_grupo)
            if until and now < until:
                return (False, int(until - now), None)
            if until and now >= until:
                _evento_cooldown.pop(evento_grupo, None)
        if _evento_inflight:
            busy = next(iter(_evento_inflight))
            return (False, 0, busy)
        _evento_inflight.add(evento_grupo)
        return (True, 0, None)


def _release_evento_slot(evento_grupo: str):
    """Remove evento do in_flight. Idempotente."""
    with _evento_cooldown_lock:
        _evento_inflight.discard(evento_grupo)


def _current_evento_inflight() -> Optional[str]:
    """Retorna o evento atualmente em reconsolidação (ou None)."""
    with _evento_cooldown_lock:
        if _evento_inflight:
            return next(iter(_evento_inflight))
    return None


def _set_evento_cooldown(evento_grupo: str, ttl_sec: int) -> float:
    """Seta lock até now+ttl. Retorna o epoch de liberação."""
    until = _time_module.time() + max(1, ttl_sec)
    with _evento_cooldown_lock:
        _evento_cooldown[evento_grupo] = until
    return until

ONLINE_THRESHOLD_MINUTES = 5
AWAY_THRESHOLD_MINUTES = 30


@router.get("/user-activity")
def get_user_activity(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("admin_monitoramento")),
):
    cache_now = _time_module.time()
    with _user_activity_cache_lock:
        cached = _user_activity_cache["data"]
        if cached is not None and (cache_now - _user_activity_cache["ts"]) < _USER_ACTIVITY_CACHE_TTL:
            return _copy.deepcopy(cached)

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

    response = {
        "resumo": {
            "total_usuarios": len(users),
            "online": online_count,
            "ausentes": away_count,
            "ativos_hoje": active_today_count,
        },
        "usuarios": user_list,
    }
    with _user_activity_cache_lock:
        _user_activity_cache["data"] = _copy.deepcopy(response)
        _user_activity_cache["ts"] = cache_now
    return response


@router.post("/scheduled-jobs/consolidacao-diaria")
def trigger_scheduled_daily_consolidation(
    x_scheduler_token: Optional[str] = Header(None, alias="X-Scheduler-Token"),
):
    """Endpoint chamado por **Replit Scheduled Deployment** às 02h BRT todo dia.

    Camada externa de defesa do job noturno: independe do uptime do processo
    backend — se ele estiver parado/hibernando, o Scheduled Deployment liga e
    chama. Síncrono (retorna só após terminar) para que o Scheduled Deployment
    marque success/failure corretamente.

    Protegido por shared-secret em env `SCHEDULER_TOKEN` (header
    `X-Scheduler-Token`). Idempotente: batches usam UPSERT com `GREATEST()`,
    então re-execuções não corrompem snapshots.

    Replica exatamente a sequência de `_run_snapshot_consolidation` (cache.py)
    e do startup em `main.py`: snapshot_diario → curvas → hoje → margem →
    refresh_active_event_details.
    """
    import logging as _logging_sd
    import time as _time_sd

    _logger_sd = _logging_sd.getLogger(__name__)

    expected = (_os.environ.get("SCHEDULER_TOKEN") or "").strip()
    if not expected:
        _logger_sd.error("[ScheduledJob] SCHEDULER_TOKEN não configurado no backend — endpoint inacessível")
        raise HTTPException(status_code=500, detail="SCHEDULER_TOKEN não configurado no backend")
    received = (x_scheduler_token or "").strip()
    if not received or received != expected:
        _logger_sd.warning("[ScheduledJob] Tentativa de execução com token inválido/ausente")
        raise HTTPException(status_code=401, detail="Token inválido")

    from app.core.database import SessionLocal as _SL_sd
    from app.services.snapshot_service import (
        snapshot_diario_batch as _sdb_sd,
        rebuild_rolling_grupos_batch as _rrgb_sd,
        consolidar_curvas_historicas_batch as _cchb_sd,
        sincronizar_hoje_batch as _shb_sd,
        sincronizar_margem_bundle_rev_batch as _smbrb_sd,
        congelar_cortes_projecao_batch as _ccpb_sd,
    )
    from app.services.sync_log_service import (
        log_evento as _le_sd,
        log_evento_strict as _les_sd,
        new_ciclo_id as _ncid_sd,
        acquire_consolidation_lock as _acq_sd,
        release_consolidation_lock as _rel_sd,
    )
    from fastapi.responses import JSONResponse as _JSON_sd

    _t0_sd = _time_sd.time()
    _ciclo_sd = _ncid_sd()
    _job_sd = "consolidacao_diaria_04h"  # MESMO job_name das camadas 2/3 — crítico p/ observabilidade
    _result_sd: dict = {
        "ciclo_id": _ciclo_sd,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "snapshot_diario": None,
        "curvas": None,
        "hoje": None,
        "margem": None,
        "event_details": None,
        "errors": [],
    }

    _logger_sd.info(f"[ScheduledJob] === CONSOLIDAÇÃO DIÁRIA 02h BRT (Scheduled Deployment) INICIADA ciclo={_ciclo_sd} ===")

    # ADVISORY LOCK cross-process — bloqueia execução paralela com catch-up
    # de startup (main.py) ou scheduler interno (cache.py). Se outro processo
    # detém o lock, retornamos 409 e o Scheduled Deployment vai retentar.
    _lock_conn_sd = _acq_sd()
    if _lock_conn_sd is None:
        _logger_sd.warning(f"[ScheduledJob] Advisory lock NÃO obtido (outro processo já está consolidando) — abortando ciclo {_ciclo_sd}")
        # Loga 'pulado' para auditoria (best-effort, sem strict pois é não-crítico).
        try:
            _le_sd(_ciclo_sd, _job_sd, "pulado", nivel="ciclo",
                   motivo="lock_em_uso",
                   detalhes="Outro processo (startup catch-up ou scheduler interno) já está rodando a consolidação")
        except Exception:
            pass
        raise HTTPException(status_code=409, detail="Consolidação já em andamento por outro processo")

    # Loga ciclo 'iniciado' com STRICT (re-raises): se falhar, abortamos com 500
    # para evitar race condition. O lock JÁ foi adquirido, então liberamos antes.
    try:
        _les_sd(_ciclo_sd, _job_sd, "iniciado", nivel="ciclo",
                detalhes="Job 02h BRT via Scheduled Deployment externo (snapshot diário, curvas, hoje, margem)")
    except Exception as _le_err:
        _logger_sd.error(f"[ScheduledJob] Falha CRÍTICA ao logar ciclo 'iniciado' — liberando lock e abortando: {_le_err}")
        _rel_sd(_lock_conn_sd)
        raise HTTPException(status_code=500, detail=f"Falha ao registrar ciclo: {str(_le_err)[:200]}")

    # Interpreta retorno dict.status dos batches que NÃO lançam exception
    # (sincronizar_margem_bundle_rev_batch pode retornar status='falha_persistencia',
    # 'parcial', 'sem_dados', etc.) — mesma lógica de _run_step em cache.py.
    def _classify_return(ret) -> str:
        """Retorna 'ok' | 'parcial' | 'falha' | 'pulado' baseado no retorno do batch."""
        if not isinstance(ret, dict):
            return "ok"
        raw = str(ret.get("status") or "").lower()
        if raw in ("ok", "concluido", "concluído", "sucesso", "success", ""):
            return "ok"
        if raw in ("skipped", "pulado", "ignorado", "sem_dados", "no_data"):
            return "pulado"
        if raw.startswith("falha") or raw in ("erro", "error", "failed", "failure"):
            return "falha"
        if raw == "parcial":
            return "parcial"
        return "ok"

    # Tracker de classificação por passo (ok/parcial/falha/pulado) — usado para
    # determinar _n_success real (não baseado em non-None, que conta dict.status='falha').
    _step_outcomes: dict = {}

    def _run_and_classify(step: str, fn):
        """Executa, captura exception, e classifica dict.status. Popula errors e _step_outcomes.

        Idempotência: pula se este sub-passo já concluiu OK hoje BRT em qualquer
        ciclo (startup catch-up, scheduler interno, ou retentativa anterior do
        próprio endpoint). Permite retentar o Scheduled Deployment sem refazer
        trabalho pesado de Magento — só re-executa o que falhou.
        """
        try:
            from app.services.sync_log_service import step_already_done_today as _sad
            if _sad(_job_sd, step):
                _step_outcomes[step] = "pulado"
                _result_sd[step] = "ja_executado_hoje"
                # Grava 'pulado' nivel='grupo' para rastreabilidade do ciclo.
                try:
                    _le_sd(_ciclo_sd, _job_sd, "pulado", nivel="grupo", grupo=step,
                           motivo="ja_executado_hoje",
                           detalhes=f"{step} já concluído hoje BRT — pulado (idempotência)")
                except Exception:
                    pass
                _logger_sd.info(f"[ScheduledJob] {step} pulado: já concluiu hoje BRT (idempotência)")
                return
        except Exception as _e_idem:
            _logger_sd.warning(f"[ScheduledJob] check idempotência de {step} falhou: {_e_idem}")
        # Grava 'iniciado' do sub-passo para rastreabilidade.
        try:
            _le_sd(_ciclo_sd, _job_sd, "iniciado", nivel="grupo", grupo=step)
        except Exception:
            pass
        try:
            ret = fn()
            _result_sd[step] = ret
            cls = _classify_return(ret)
            _step_outcomes[step] = cls
            if cls == "falha":
                _result_sd["errors"].append(f"{step}: retorno falha — {ret}")
            elif cls == "parcial":
                _result_sd["errors"].append(f"{step}: retorno parcial — {ret}")
            # Grava status terminal do sub-passo (CRÍTICO para idempotência cross-camada).
            try:
                _le_sd(_ciclo_sd, _job_sd, cls, nivel="grupo", grupo=step,
                       detalhes=f"{step} terminou {cls}: {str(ret)[:200]}")
            except Exception:
                pass
        except Exception as ex:
            _logger_sd.error(f"[ScheduledJob] {step} lançou exception: {ex}")
            _step_outcomes[step] = "falha"
            _result_sd["errors"].append(f"{step}: {str(ex)[:300]}")
            try:
                _le_sd(_ciclo_sd, _job_sd, "falha", nivel="grupo", grupo=step,
                       motivo="exception", detalhes=str(ex)[:300])
            except Exception:
                pass

    # Tudo daqui pra baixo está sob try/finally para garantir release do advisory lock.
    try:
        _db_sd = _SL_sd()
        try:
            # Nomes canônicos (mesmos do scheduler interno cache.py _run_step):
            # essencial para compartilhar idempotência cross-camada via SyncEventLog.
            def _auto_concluir_sd():
                from app.services.event_status_service import auto_concluir_eventos_passados
                return auto_concluir_eventos_passados(_db_sd)
            _run_and_classify("auto_concluir_eventos_passados", _auto_concluir_sd)
            _run_and_classify("snapshot_diario_batch", lambda: _sdb_sd(_db_sd))
            _run_and_classify("rebuild_rolling_grupos_batch", lambda: _rrgb_sd(_db_sd))
            _run_and_classify("consolidar_curvas_historicas_batch", lambda: _cchb_sd(_db_sd))
            _run_and_classify("sincronizar_hoje_batch", lambda: _shb_sd(_db_sd))
            _run_and_classify("sincronizar_margem_bundle_rev_batch", lambda: _smbrb_sd(_db_sd))
            _run_and_classify("congelar_cortes_projecao_batch", lambda: _ccpb_sd(_db_sd))
        finally:
            _db_sd.close()

        try:
            from app.services.event_detail_snapshot_service import refresh_active_event_details as _raed_sd
            _result_sd["event_details"] = _raed_sd()
            _step_outcomes["event_details"] = "ok"
        except Exception as _e5:
            _logger_sd.error(f"[ScheduledJob] refresh_active_event_details falhou: {_e5}")
            _step_outcomes["event_details"] = "falha"
            _result_sd["errors"].append(f"event_details: {str(_e5)[:300]}")

        _result_sd["duration_s"] = round(_time_sd.time() - _t0_sd, 1)
        _result_sd["finished_at"] = datetime.now(timezone.utc).isoformat()
        _result_sd["step_outcomes"] = _step_outcomes
        _n_errors = len(_result_sd["errors"])
        # _n_success: passos que terminaram como 'ok' ou 'pulado' (skipped é OK semântico).
        _n_success = sum(1 for cls in _step_outcomes.values() if cls in ("ok", "pulado"))
        if _n_errors == 0:
            _result_sd["status"] = "concluido"
            _http_status = 200
        elif _n_success > 0:
            # Parcial: usa 500 (não 207) para garantir que Scheduled Deployment trate
            # como FAILURE e gere retry/alerta — alguns executores ignoram 207 como 2xx.
            _result_sd["status"] = "parcial"
            _http_status = 500
        else:
            _result_sd["status"] = "falha"
            _http_status = 500

        # Loga ciclo terminal — camadas 2/3 dependem desse log para saber se rodou hoje.
        try:
            _le_sd(_ciclo_sd, _job_sd, _result_sd["status"], nivel="ciclo",
                   detalhes=(f"Scheduled Deployment 02h BRT terminou em {_result_sd['duration_s']}s. "
                             f"sucessos={_n_success}, erros={_n_errors}. outcomes={_step_outcomes}. "
                             f"errors={' | '.join(_result_sd['errors'])[:500] if _result_sd['errors'] else 'nenhum'}"))
        except Exception as _le_err2:
            _logger_sd.warning(f"[ScheduledJob] Falha ao logar ciclo terminal '{_result_sd['status']}': {_le_err2}")

        _logger_sd.info(
            f"[ScheduledJob] === CONSOLIDAÇÃO DIÁRIA 02h BRT TERMINOU em {_result_sd['duration_s']}s — "
            f"status={_result_sd['status']}, sucessos={_n_success}, erros={_n_errors}, http={_http_status} ==="
        )

        if _result_sd["errors"]:
            try:
                from app.services.health_alert_service import log_and_alert as _laa_sd
                _laa_sd(
                    event_type="SCHEDULED_DAILY_PARTIAL",
                    severity="HIGH",
                    message=f"Consolidação 02h BRT terminou {_result_sd['status']}: {_n_errors} sub-passo(s) falharam",
                    detail=" | ".join(_result_sd["errors"])[:2000],
                )
            except Exception as _alert_err:
                _logger_sd.warning(f"[ScheduledJob] Falha ao registrar alerta: {_alert_err}")

        return _JSON_sd(status_code=_http_status, content=_result_sd)
    finally:
        # Libera advisory lock SEMPRE — mesmo em path de exception não previsto.
        _rel_sd(_lock_conn_sd)


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
        from app.services.snapshot_service import snapshot_diario_batch, rebuild_rolling_grupos_batch, consolidar_curvas_historicas_batch, sincronizar_hoje_batch, congelar_cortes_projecao_batch
        local_db = SessionLocal()
        try:
            try:
                from app.services.event_status_service import auto_concluir_eventos_passados
                concluidos = auto_concluir_eventos_passados(local_db)
                logger.info(f"Manual snapshot consolidation: auto-conclusão {concluidos} evento(s)")
            except Exception as ace:
                logger.error(f"Manual snapshot consolidation: auto_concluir_eventos_passados falhou: {ace}")
            grupos = snapshot_diario_batch(local_db)
            try:
                rolling = rebuild_rolling_grupos_batch(local_db)
                logger.info(f"Manual snapshot consolidation: rebuild rolante={rolling}")
            except Exception as rre:
                logger.error(f"Manual snapshot consolidation: rebuild_rolling_grupos_batch falhou: {rre}")
            curvas = consolidar_curvas_historicas_batch(local_db)
            hoje = sincronizar_hoje_batch(local_db)
            try:
                cortes = congelar_cortes_projecao_batch(local_db)
            except Exception as ce:
                logger.error(f"Manual snapshot consolidation: congelar_cortes_projecao_batch falhou: {ce}")
                cortes = {"status": "erro"}
            logger.info(f"Manual snapshot consolidation: {grupos} grupos, {curvas} curvas, {hoje} hoje, cortes={cortes}")
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


def _find_resumable_checkpoint(db: Session) -> Optional[dict]:
    """Busca o ciclo de consolidação mais recente que ficou incompleto.

    Um ciclo é "incompleto" quando:
      - Tem linhas em ``consolidacao_checkpoint`` nas últimas 24h, E
      - NÃO existe linha em ``sync_event_log`` com job_name='consolidar_full_manual'
        nivel='ciclo' status='concluido' para o mesmo ciclo_id.

    Retorna {ciclo_id, incremental, triggered_by, started_at_cycle, ok_count,
    failed_count, last_grupo, last_processed_at} ou None.
    """
    from ...models.consolidacao_checkpoint import ConsolidacaoCheckpoint
    from datetime import datetime as _dt, timedelta as _td, timezone as _tz
    cutoff = _dt.now(_tz.utc) - _td(hours=24)

    # Sub-query: ciclos JÁ concluídos (consolidar_full_manual nivel='ciclo' status='concluido')
    concluded_subq = (
        db.query(SyncEventLog.ciclo_id)
        .filter(
            SyncEventLog.job_name == "consolidar_full_manual",
            SyncEventLog.nivel == "ciclo",
            SyncEventLog.status == "concluido",
        )
        .subquery()
    )

    # Ciclo NÃO concluído mais recente (dentre os últimos 24h) — anti-join.
    # Evita falso-negativo: se o ciclo mais novo já foi concluído mas existe
    # um anterior ainda incompleto, ele é detectado.
    latest = (
        db.query(ConsolidacaoCheckpoint.ciclo_id, sa_func.max(ConsolidacaoCheckpoint.processed_at).label("latest"))
        .filter(
            ConsolidacaoCheckpoint.processed_at >= cutoff,
            ~ConsolidacaoCheckpoint.ciclo_id.in_(db.query(concluded_subq.c.ciclo_id)),
        )
        .group_by(ConsolidacaoCheckpoint.ciclo_id)
        .order_by(desc("latest"))
        .first()
    )
    if not latest:
        return None
    ciclo_id = latest[0]
    rows = db.query(ConsolidacaoCheckpoint).filter(
        ConsolidacaoCheckpoint.ciclo_id == ciclo_id
    ).order_by(desc(ConsolidacaoCheckpoint.processed_at)).all()
    if not rows:
        return None
    ok_count = sum(1 for r in rows if r.status == "ok")
    failed_count = sum(1 for r in rows if r.status == "failed")
    first_row = rows[-1]
    last_row = rows[0]
    return {
        "ciclo_id": ciclo_id,
        "incremental": bool(first_row.incremental),
        "triggered_by": first_row.triggered_by,
        "started_at_cycle": first_row.started_at_cycle.isoformat() if first_row.started_at_cycle else None,
        "ok_count": ok_count,
        "failed_count": failed_count,
        "last_grupo": last_row.evento_grupo,
        "last_processed_at": last_row.processed_at.isoformat() if last_row.processed_at else None,
    }


@router.get("/snapshots/consolidar-full/checkpoint")
def get_consolidation_checkpoint(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("admin_monitoramento")),
):
    """Retorna um checkpoint retomável (se houver) — ciclo iniciado nas últimas
    24h que ainda não foi concluído. Usado pela UI pra oferecer "Retomar"."""
    ckpt = _find_resumable_checkpoint(db)
    if not ckpt:
        return {"resumable": False}
    return {"resumable": True, **ckpt}


def _execute_consolidation_full(resume_ckpt: Optional[dict], incremental: bool):
    """Executa a consolidação completa em thread daemon. Lê metadados de
    retry (`auto_retry`, `auto_retry_attempt`, `auto_retry_max_attempts`,
    `auto_retry_delay_sec`) do `_consolidation_full_progress` já preparado
    pelo chamador. Ao final, se houver falhas e auto_retry estiver ativo,
    agenda nova tentativa via `_schedule_auto_retry`."""
    global _consolidation_full_progress
    # Captura a geração no início. Se o usuário cancelar ou disparar outra
    # consolidação enquanto este ciclo ainda está rodando, a geração muda e
    # o `_maybe_schedule_auto_retry` no `finally` aborta sem agendar timer.
    _my_generation = _current_consolidation_generation()
    import logging as _log
    _logger = _log.getLogger(__name__)
    from app.core.database import SessionLocal
    from app.models.sku_mapping import SkuMapping
    from app.models.dimensoes import DimProjeto
    from app.models.cadastro_evento import CadastroEvento
    from app.models.consolidacao_checkpoint import ConsolidacaoCheckpoint
    from app.services.snapshot_service import (
        consolidar_vendas_grupo, _freeze_after_days, _load_active_grupos,
        _snapshot_lookback_days,
    )
    from app.services.sync_log_service import new_ciclo_id, log_evento
    from app.api.routes.marketing import _build_sku_to_grupo_map, normalize_sku
    from sqlalchemy.dialects.postgresql import insert as _pg_insert
    from datetime import datetime as _dt, timezone as _tz
    import time as _t
    from datetime import date as _date, timedelta

    # Diagnóstico de hang: logamos cada passo do setup com timing pra que,
    # se o thread travar antes do primeiro log_evento (pool exausto, etc),
    # consigamos ver no log da aplicação onde parou.
    _setup_t0 = _t.time()
    _logger.info("consolidar_full_manual: thread iniciado, abrindo SessionLocal…")
    with _consolidation_full_lock:
        _consolidation_full_progress["setup_step"] = "Abrindo sessão no banco…"
    try:
        local_db = SessionLocal()
    except Exception as _sl_err:
        _logger.error(f"consolidar_full_manual: SessionLocal falhou: {_sl_err}")
        with _consolidation_full_lock:
            _consolidation_full_progress["status"] = "error"
            _consolidation_full_progress["error"] = f"SessionLocal: {str(_sl_err)[:300]}"
            _consolidation_full_progress["finished_at"] = _t.time()
        return
    _logger.info(f"consolidar_full_manual: SessionLocal ok em {(_t.time()-_setup_t0)*1000:.0f}ms")

    try:
        # Resume path: reusa ciclo_id e marca os grupos já OK pra pular
        already_ok_grupos: set = set()
        if resume_ckpt:
            ciclo_id = resume_ckpt["ciclo_id"]
            rows_done = local_db.query(ConsolidacaoCheckpoint.evento_grupo).filter(
                ConsolidacaoCheckpoint.ciclo_id == ciclo_id,
                ConsolidacaoCheckpoint.status == "ok",
            ).all()
            already_ok_grupos = {r[0] for r in rows_done}
        else:
            ciclo_id = new_ciclo_id()
        triggered_by = _consolidation_full_progress.get("triggered_by", "")
        cycle_started_at_dt = _dt.now(_tz.utc)
        with _consolidation_full_lock:
            _consolidation_full_progress["ciclo_id"] = ciclo_id
            _consolidation_full_progress["setup_step"] = "Registrando início do ciclo…"

        # Sempre status='iniciado' no nível ciclo (mesmo quando retomado).
        # 'retomado' fica apenas em detalhes — list_sync_cycles trata qualquer
        # status != 'iniciado' como final, o que esconderia ciclos em execução.
        _t_le = _t.time()
        log_evento(
            ciclo_id, "consolidar_full_manual", "iniciado", nivel="ciclo",
            detalhes=(
                f"incremental={incremental} por {triggered_by}"
                + (f" (RETOMADO de {len(already_ok_grupos)} já OK)" if resume_ckpt else "")
            ),
        )
        _logger.info(f"consolidar_full_manual: log_evento iniciado em {(_t.time()-_t_le)*1000:.0f}ms (ciclo={ciclo_id})")

        today = _date.today()
        yesterday = today - timedelta(days=1)
        ano = today.year

        with _consolidation_full_lock:
            _consolidation_full_progress["setup_step"] = "Carregando mapeamento de SKUs…"
        sku_to_grupo = _build_sku_to_grupo_map(local_db, ano)
        if not sku_to_grupo:
            with _consolidation_full_lock:
                _consolidation_full_progress["status"] = "error"
                _consolidation_full_progress["error"] = "Nenhum sku_to_grupo encontrado para o ano corrente"
                _consolidation_full_progress["finished_at"] = _t.time()
            return

        with _consolidation_full_lock:
            _consolidation_full_progress["setup_step"] = "Identificando eventos do ano corrente…"
        # Coleta grupos — mesma lógica do snapshot_diario_batch
        grupos_candidatos: set = set()
        for p in local_db.query(DimProjeto).all():
            if not p.data_evento or not p.codigo:
                continue
            if p.data_evento.year != ano:
                continue
            g = sku_to_grupo.get(normalize_sku(str(p.codigo)))
            if g:
                grupos_candidatos.add(g)

        magento_id_to_grupo: dict = {}
        for mm in local_db.query(SkuMapping).filter(
            SkuMapping.ano == ano, SkuMapping.ativo == True,
            SkuMapping.fonte == "MAGENTO", SkuMapping.id_externo.isnot(None),
            SkuMapping.evento_grupo.isnot(None),
        ).all():
            magento_id_to_grupo[str(mm.id_externo)] = mm.evento_grupo

        cadastros = local_db.query(CadastroEvento).filter(CadastroEvento.deleted_at.is_(None)).all()
        projeto_ids = {c.projeto_id for c in cadastros if getattr(c, "projeto_id", None)}
        projeto_codigo_by_id: dict = {}
        if projeto_ids:
            for pj in local_db.query(DimProjeto.id, DimProjeto.codigo).filter(DimProjeto.id.in_(projeto_ids)).all():
                if pj.codigo:
                    projeto_codigo_by_id[pj.id] = str(pj.codigo)

        for c in cadastros:
            if not c.data_evento or c.data_evento.year != ano:
                continue
            g = None
            if getattr(c, "sku", None):
                g = sku_to_grupo.get(normalize_sku(str(c.sku)))
            if not g and getattr(c, "projeto_id", None):
                cod = projeto_codigo_by_id.get(c.projeto_id)
                if cod:
                    g = sku_to_grupo.get(normalize_sku(cod))
            if not g and getattr(c, "id_evento_magento", None):
                g = magento_id_to_grupo.get(str(c.id_evento_magento))
            if g:
                grupos_candidatos.add(g)

        with _consolidation_full_lock:
            _consolidation_full_progress["setup_step"] = "Filtrando eventos ativos (excluindo congelados)…"
        freeze_days = _freeze_after_days()
        active_grupos = _load_active_grupos(local_db, freeze_days)
        grupos_frozen = grupos_candidatos - active_grupos
        grupos_to_process_all = sorted(grupos_candidatos & active_grupos)

        # Resume: pula grupos que já foram OK neste ciclo
        grupos_to_process = [g for g in grupos_to_process_all if g not in already_ok_grupos]
        skipped_resume = len(grupos_to_process_all) - len(grupos_to_process)

        with _consolidation_full_lock:
            _consolidation_full_progress["total"] = len(grupos_to_process_all)
            _consolidation_full_progress["frozen"] = len(grupos_frozen)
            # Fila inicial: tudo que ainda falta processar nesta execução.
            # À medida que cada worker pega um grupo, ele sai daqui e vai
            # pra `em_execucao`; ao terminar, sai de ambos.
            _consolidation_full_progress["grupos_pendentes"] = list(grupos_to_process)
            _consolidation_full_progress["setup_step"] = None  # Fase de prep terminou
            # Pré-popula contadores com o que já foi feito antes do reinício
            if skipped_resume > 0:
                _consolidation_full_progress["ok"] = skipped_resume
                _consolidation_full_progress["current"] = skipped_resume

        t_start = _consolidation_full_progress["started_at"]

        # Paralelização: cada worker abre sua própria SessionLocal pra não
        # compartilhar Session (SQLAlchemy Session não é thread-safe).
        # Default conservador de 3 workers (≈3 conexões simultâneas pelo
        # túnel SSH); o pool local PG (25/50) e o pool MySQL têm folga.
        # Pode subir até 6 com `CONSOLIDAR_FULL_WORKERS=6` em ambientes
        # onde o SSH aguenta. Em 1 worker o comportamento é equivalente
        # ao serial original.
        try:
            _max_workers = max(1, int(_os.getenv("CONSOLIDAR_FULL_WORKERS", "3")))
        except ValueError:
            _max_workers = 3
        _max_workers = min(_max_workers, max(1, len(grupos_to_process)))
        _logger.info(
            f"consolidar_full_manual: processando {len(grupos_to_process)} grupos "
            f"em paralelo com {_max_workers} worker(s) (ciclo={ciclo_id})"
        )

        def _process_one(grupo: str) -> dict:
            """Processa 1 grupo numa SessionLocal isolada do thread."""
            t_grupo = _t.time()
            # Marca grupo como "em execução" e remove da fila pendente
            # ANTES de qualquer operação que possa falhar (ex.: SessionLocal()
            # com pool exaurido). Garante que mesmo numa falha precoce o
            # grupo não fique preso visualmente em `grupos_pendentes`.
            # O cleanup de `em_execucao` está no finally externo abaixo.
            with _consolidation_full_lock:
                _consolidation_full_progress["em_execucao"].append(
                    {"grupo": grupo, "started_at": t_grupo}
                )
                try:
                    _consolidation_full_progress["grupos_pendentes"].remove(grupo)
                except ValueError:
                    pass  # já removido (improvável, defensivo)
            thread_db = None
            result_entry: dict = {
                "grupo": grupo,
                "status": "ok",
                "motivo": None,
                "qtd_antes": None,
                "qtd_depois": None,
                "duracao_ms": None,
                "detalhes": None,
            }
            try:
                # SessionLocal() pode falhar (pool exaurido). Tratamos aqui
                # pra registrar como failed em vez de propagar como worker
                # crash (que deixaria o estado inconsistente).
                try:
                    thread_db = SessionLocal()
                except Exception as _sess_err:
                    result_entry["status"] = "failed"
                    result_entry["motivo"] = f"SessionLocal: {str(_sess_err)[:280]}"
                    result_entry["duracao_ms"] = int((_t.time() - t_grupo) * 1000)
                    _logger.error(
                        f"consolidar_full_manual: SessionLocal falhou p/ '{grupo}': {_sess_err}"
                    )
                    return result_entry

                try:
                    # incremental + lookback: reprocessa janela rolante (default
                    # 7 dias) para corrigir snapshots parciais antigos. Mesmo
                    # comportamento do batch das 04h e do "Reconsolidar"
                    # individual. Sem lookback, incremental só busca dias novos
                    # > max_dia e nunca corrige um valor errado de dia anterior.
                    _lb_full = _snapshot_lookback_days() if incremental else 0
                    consolidar_vendas_grupo(
                        thread_db, grupo, ano,
                        data_inicio=None, data_fim=yesterday,
                        incremental=incremental,
                        lookback_days=_lb_full,
                        ciclo_id=ciclo_id,
                        parent_job_name="consolidar_full_manual",
                    )
                except Exception as exc:
                    result_entry["status"] = "failed"
                    result_entry["motivo"] = str(exc)[:300]
                    _logger.error(f"consolidar_full_manual: erro grupo='{grupo}': {exc}")

                result_entry["duracao_ms"] = int((_t.time() - t_grupo) * 1000)

                # Checkpoint UPSERT — sobrevive a reinício, com session do
                # próprio thread (evita disputa pelo cursor entre workers).
                try:
                    stmt = _pg_insert(ConsolidacaoCheckpoint).values(
                        ciclo_id=ciclo_id,
                        evento_grupo=grupo,
                        status=result_entry["status"],
                        incremental=1 if incremental else 0,
                        triggered_by=triggered_by[:200] if triggered_by else None,
                        duracao_ms=result_entry["duracao_ms"],
                        motivo=(result_entry["motivo"] or None),
                        qtd_antes=result_entry.get("qtd_antes"),
                        qtd_depois=result_entry.get("qtd_depois"),
                        started_at_cycle=cycle_started_at_dt,
                    )
                    stmt = stmt.on_conflict_do_update(
                        constraint="uq_consol_ckpt_ciclo_grupo",
                        set_={
                            "status": stmt.excluded.status,
                            "duracao_ms": stmt.excluded.duracao_ms,
                            "motivo": stmt.excluded.motivo,
                            "processed_at": _dt.now(_tz.utc),
                        },
                    )
                    thread_db.execute(stmt)
                    thread_db.commit()
                except Exception as _ckpt_err:
                    thread_db.rollback()
                    _logger.warning(
                        f"consolidar_full_manual: falha ao gravar checkpoint "
                        f"para '{grupo}': {_ckpt_err}"
                    )
            finally:
                if thread_db is not None:
                    try:
                        thread_db.close()
                    except Exception:
                        pass  # defensivo — close já errou, nada a fazer
                # Sai da lista "em execução" assim que o worker termina,
                # independente de ok/falha. Fica no `results` (adicionado
                # pelo agregador no loop principal) ou nos contadores.
                with _consolidation_full_lock:
                    _consolidation_full_progress["em_execucao"] = [
                        x for x in _consolidation_full_progress["em_execucao"]
                        if x.get("grupo") != grupo
                    ]
            return result_entry

        with _TPE(max_workers=_max_workers, thread_name_prefix="consolfull") as _pool:
            _futures = {_pool.submit(_process_one, g): g for g in grupos_to_process}
            for _fut in _as_completed(_futures):
                _grupo = _futures[_fut]
                try:
                    result_entry = _fut.result()
                except Exception as exc:
                    # _process_one já trata internamente; se chegou aqui é
                    # algo bem inesperado (ex.: SessionLocal() falhou).
                    result_entry = {
                        "grupo": _grupo, "status": "failed",
                        "motivo": f"worker_crash: {str(exc)[:280]}",
                        "duracao_ms": None,
                        "qtd_antes": None, "qtd_depois": None, "detalhes": None,
                    }
                    _logger.error(f"consolidar_full_manual: worker crash em '{_grupo}': {exc}")

                # Tudo sob o mesmo lock: contadores ok/failed e current
                # derivado deles mantêm consistência mesmo se no futuro
                # houver múltiplos agregadores.
                with _consolidation_full_lock:
                    if result_entry["status"] == "ok":
                        _consolidation_full_progress["ok"] += 1
                    else:
                        _consolidation_full_progress["failed"] += 1
                    _consolidation_full_progress["current"] = (
                        _consolidation_full_progress["ok"]
                        + _consolidation_full_progress["failed"]
                    )
                    _consolidation_full_progress["current_grupo"] = result_entry["grupo"]
                    _consolidation_full_progress["results"].append(result_entry)

        total_ms = int((_t.time() - t_start) * 1000)
        log_evento(
            ciclo_id, "consolidar_full_manual", "concluido", nivel="ciclo",
            detalhes=(
                f"{len(grupos_to_process)} processados agora "
                + (f"(+{skipped_resume} retomados) " if skipped_resume else "")
                + f"({_consolidation_full_progress['ok']} ok, "
                f"{_consolidation_full_progress['failed']} falha), "
                f"{len(grupos_frozen)} congelados"
            ),
            duracao_ms=total_ms,
        )
        with _consolidation_full_lock:
            _consolidation_full_progress["status"] = "done"
            _consolidation_full_progress["finished_at"] = _t.time()
            _consolidation_full_progress["current_grupo"] = None

    except Exception as exc:
        _logger.error(f"consolidar_full_manual: falha geral: {exc}")
        with _consolidation_full_lock:
            _consolidation_full_progress["status"] = "error"
            _consolidation_full_progress["error"] = str(exc)[:500]
            _consolidation_full_progress["finished_at"] = _t.time()
    finally:
        try:
            local_db.close()
        except Exception:
            pass
        # ── Auto-retry: se o ciclo terminou com falhas e auto_retry está
        # ativo, agenda nova tentativa em N segundos via threading.Timer.
        # A tentativa usa o checkpoint existente (retoma só pendentes).
        try:
            _maybe_schedule_auto_retry(owner_generation=_my_generation)
        except Exception as _retry_err:
            _logger.error(f"consolidar_full_manual: falha ao agendar auto-retry: {_retry_err}")


def _maybe_schedule_auto_retry(owner_generation: int):
    """Agenda nova tentativa se o ciclo terminou com `failed > 0` ou
    `status == "error"`, `auto_retry=True` e ainda restam tentativas.
    Idempotente: cancela timer pendente antes de criar novo.

    `owner_generation` é a geração capturada no início do ciclo que está
    chamando. Se ela foi invalidada (cancelamento manual ou novo disparo),
    NÃO agenda timer — evita retry-fantasma."""
    import logging as _log
    _logger = _log.getLogger(__name__)
    global _consolidation_retry_timer

    current_gen = _current_consolidation_generation()
    if owner_generation != current_gen:
        _logger.info(
            f"auto_retry: geração {owner_generation} foi invalidada "
            f"(atual={current_gen}) — não reagenda."
        )
        return

    with _consolidation_full_lock:
        snap = dict(_consolidation_full_progress)

    if not snap.get("auto_retry"):
        return
    attempt = int(snap.get("auto_retry_attempt", 1) or 1)
    max_att = int(snap.get("auto_retry_max_attempts", 1) or 1)
    if attempt >= max_att:
        _logger.info(
            f"auto_retry: tentativa {attempt}/{max_att} esgotada, não reagenda."
        )
        return

    final_status = snap.get("status")
    failed = int(snap.get("failed", 0) or 0)
    if final_status != "error" and failed == 0:
        _logger.info("auto_retry: ciclo sem falhas, não reagenda.")
        return

    delay_sec = int(snap.get("auto_retry_delay_sec", 1200) or 1200)
    next_at = _time_module.time() + delay_sec
    triggered_by = snap.get("triggered_by", "auto-retry")

    def _fire():
        global _consolidation_retry_timer
        with _consolidation_retry_lock:
            _consolidation_retry_timer = None
            # Revalida a geração no momento do disparo. Se foi invalidada
            # entre o agendamento e o fire (cancelamento ou novo disparo
            # manual), aborta sem fazer nada.
            if _consolidation_generation != owner_generation:
                _logger.info(
                    f"auto_retry: geração mudou antes do fire "
                    f"({owner_generation} → {_consolidation_generation}), abortando."
                )
                return
        _logger.info("auto_retry: timer disparou, abrindo SessionLocal p/ checkpoint…")
        try:
            from app.core.database import SessionLocal
            db = SessionLocal()
            try:
                ckpt = _find_resumable_checkpoint(db)
            finally:
                db.close()
        except Exception as _e:
            _logger.error(f"auto_retry: falha ao buscar checkpoint: {_e}")
            return
        if not ckpt:
            _logger.info("auto_retry: nenhum checkpoint pendente — nada a retomar.")
            return

        with _consolidation_full_lock:
            if _consolidation_full_progress.get("status") == "running":
                _logger.info("auto_retry: já existe consolidação em execução, abortando timer.")
                return
            new_attempt = attempt + 1
            _consolidation_full_progress.clear()
            _consolidation_full_progress.update({
                "status": "running",
                "started_at": _time_module.time(),
                "finished_at": None,
                "triggered_by": f"{triggered_by} [auto-retry {new_attempt}/{max_att}]",
                "incremental": bool(ckpt["incremental"]),
                "total": 0,
                "current": 0,
                "current_grupo": None,
                "ok": 0,
                "failed": 0,
                "skipped": 0,
                "frozen": 0,
                "results": [],
                "ciclo_id": ckpt["ciclo_id"],
                "error": None,
                "resumed": True,
                "resumed_from_ok": ckpt["ok_count"],
                "setup_step": f"Auto-retry {new_attempt}/{max_att} — iniciando…",
                "grupos_pendentes": [],
                "em_execucao": [],
                "auto_retry": True,
                "auto_retry_attempt": new_attempt,
                "auto_retry_max_attempts": max_att,
                "auto_retry_delay_sec": delay_sec,
                "auto_retry_next_at": None,
            })
        # Revalidação final ANTES de spawnar o thread: se a geração foi
        # invalidada entre a primeira checagem do _fire e este ponto (ex.:
        # cancelar-retry chegou no meio), aborta e reverte progress.
        with _consolidation_retry_lock:
            if _consolidation_generation != owner_generation:
                _logger.info(
                    f"auto_retry: geração mudou imediatamente antes do start "
                    f"({owner_generation} → {_consolidation_generation}), abortando."
                )
                with _consolidation_full_lock:
                    _consolidation_full_progress["status"] = "cancelled"
                    _consolidation_full_progress["error"] = "auto-retry cancelado"
                    _consolidation_full_progress["finished_at"] = _time_module.time()
                return
            _threading.Thread(
                target=_execute_consolidation_full,
                args=(ckpt, bool(ckpt["incremental"])),
                daemon=True,
            ).start()

    # Cancela timer anterior (se houver) e agenda novo. Mantemos a geração
    # intacta — este é o próprio fluxo de auto-retry continuando, não um
    # cancelamento externo. Invalidar aqui faria o `_fire` abaixo abortar.
    _cancel_pending_auto_retry(invalidate_generation=False)
    timer = _threading.Timer(delay_sec, _fire)
    timer.daemon = True
    with _consolidation_retry_lock:
        _consolidation_retry_timer = timer
    timer.start()
    with _consolidation_full_lock:
        _consolidation_full_progress["auto_retry_next_at"] = next_at
    _logger.info(
        f"auto_retry: agendado em {delay_sec}s (tentativa {attempt+1}/{max_att})."
    )


@router.post("/snapshots/consolidar-full")
def trigger_snapshot_consolidation_full(
    incremental: bool = Query(default=False, description="True=incremental (só dias novos). False=reconstrução completa."),
    resume: bool = Query(default=False, description="True=retomar o ciclo incompleto mais recente; ignora 'incremental' e usa o do ciclo original."),
    auto_retry: bool = Query(default=True, description="Se True, agenda nova tentativa automática a cada `auto_retry_delay_min` minutos quando houver falhas, até `auto_retry_max_attempts` tentativas."),
    auto_retry_delay_min: int = Query(default=20, ge=1, le=120, description="Intervalo (min) entre tentativas automáticas."),
    auto_retry_max_attempts: int = Query(default=6, ge=1, le=20, description="Número máximo de tentativas (1ª + retries)."),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("admin_monitoramento")),
):
    """Consolidação completa de snapshots de todos os eventos com rastreamento de progresso em tempo real.

    Quando ``resume=True``, retoma o último ciclo incompleto: pula os grupos que
    já estão no ``consolidacao_checkpoint`` com status='ok' e reprocessa o resto.

    Quando ``auto_retry=True`` (padrão), se o ciclo terminar com `failed > 0`
    ou `status == "error"`, agenda automaticamente nova tentativa em
    ``auto_retry_delay_min`` minutos (padrão 20), até no máximo
    ``auto_retry_max_attempts`` tentativas no total (padrão 6).
    """
    global _consolidation_full_progress

    # Resolver ciclo + lista de grupos a pular (se resume)
    resume_ckpt = None
    if resume:
        resume_ckpt = _find_resumable_checkpoint(db)
        if not resume_ckpt:
            return {
                "status": "no_checkpoint",
                "message": "Nenhum ciclo incompleto encontrado para retomar.",
            }
        incremental = bool(resume_ckpt["incremental"])

    # Pre-check rápido SEM segurar lock nenhum aninhado: evita inversão de
    # ordem com `retry_lock` (segurado por `_fire`). Se já há execução em
    # curso, retorna sem cancelar auto-retry.
    with _consolidation_full_lock:
        if _consolidation_full_progress.get("status") == "running":
            return {
                "status": "already_running",
                "message": "Já existe uma consolidação em andamento",
            }

    # Fora de qualquer lock: cancelar auto-retry pendente e invalidar
    # geração (`_cancel_pending_auto_retry` adquire SOMENTE retry_lock).
    # Ordem global de locks: retry_lock SEMPRE antes de full_lock.
    _cancel_pending_auto_retry()

    with _consolidation_full_lock:
        # Double-check: outra requisição pode ter iniciado entre nossos dois
        # blocos. Improvável (request handler é síncrono por worker), mas
        # mantém invariante "só 1 execução por vez" sem race.
        if _consolidation_full_progress.get("status") == "running":
            return {
                "status": "already_running",
                "message": "Já existe uma consolidação em andamento",
            }
        _consolidation_full_progress.clear()
        _consolidation_full_progress.update({
            "status": "running",
            "started_at": _time_module.time(),
            "finished_at": None,
            "triggered_by": f"{current_user.nome} ({current_user.email})",
            "incremental": incremental,
            "total": 0,
            "current": 0,
            "current_grupo": None,
            "ok": 0,
            "failed": 0,
            "skipped": 0,
            "frozen": 0,
            "results": [],
            "ciclo_id": resume_ckpt["ciclo_id"] if resume_ckpt else None,
            "error": None,
            "resumed": bool(resume_ckpt),
            "resumed_from_ok": resume_ckpt["ok_count"] if resume_ckpt else 0,
            "setup_step": "Iniciando…",
            "grupos_pendentes": [],
            "em_execucao": [],
            "auto_retry": bool(auto_retry),
            "auto_retry_attempt": 1,
            "auto_retry_max_attempts": int(auto_retry_max_attempts),
            "auto_retry_delay_sec": int(auto_retry_delay_min) * 60,
            "auto_retry_next_at": None,
        })

    _threading.Thread(
        target=_execute_consolidation_full,
        args=(resume_ckpt, incremental),
        daemon=True,
    ).start()
    return {
        "status": "started",
        "message": "Consolidação completa iniciada em background",
        "auto_retry": bool(auto_retry),
        "auto_retry_max_attempts": int(auto_retry_max_attempts),
        "auto_retry_delay_min": int(auto_retry_delay_min),
    }


@router.post("/snapshots/consolidar-full/cancelar-retry")
def cancel_auto_retry(
    current_user: Usuario = Depends(require_permission("admin_monitoramento")),
):
    """Cancela um auto-retry agendado (se houver). Não afeta consolidação
    em execução."""
    cancelled = _cancel_pending_auto_retry()
    with _consolidation_full_lock:
        _consolidation_full_progress["auto_retry"] = False
        _consolidation_full_progress["auto_retry_next_at"] = None
    return {"cancelled": cancelled}


@router.get("/snapshots/consolidar-full/progress")
def get_snapshot_consolidation_full_progress(
    current_user: Usuario = Depends(require_permission("marketing")),
):
    """Retorna o progresso atual da consolidação completa de snapshots."""
    with _consolidation_full_lock:
        return _copy.deepcopy(_consolidation_full_progress)


@router.get("/snapshots/consolidar-evento/cooldown")
def get_evento_cooldown(
    evento_grupo: str = Query(..., description="Nome do grupo de evento"),
    current_user: Usuario = Depends(require_permission("admin_monitoramento")),
):
    """Retorna o status de cooldown do evento para o usuário atual.

    Cooldown só se aplica a perfis "Diretoria". Para outros perfis sempre
    retorna `locked=false`. A UI pode usar isso para desabilitar o botão
    "Reconsolidar" mostrando um countdown."""
    is_diretoria = _user_is_diretoria(current_user)
    remaining = _evento_cooldown_remaining(evento_grupo) if is_diretoria else 0
    busy_evento = _current_evento_inflight()
    return {
        "evento_grupo": evento_grupo,
        "is_diretoria": is_diretoria,
        "locked": remaining > 0,
        "remaining_sec": remaining,
        "cooldown_total_sec": _diretoria_cooldown_sec(),
        "evento_em_andamento": busy_evento,
        "outro_em_andamento": (busy_evento is not None and busy_evento != evento_grupo),
    }


@router.post("/snapshots/consolidar-evento")
def trigger_consolidar_evento(
    evento_grupo: str = Query(..., description="Nome do grupo de evento a consolidar"),
    incremental: bool = Query(default=False, description="Se True, apenas dias novos; se False, reconstrói completo"),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("admin_monitoramento")),
):
    """Consolida o snapshot de vendas de um único evento específico.

    Executa de forma síncrona e retorna o resultado completo com qtd_antes/depois.
    Requer permissão admin_monitoramento.

    **Cooldown Diretoria:** quando um usuário com perfil "Diretoria" reconsolida
    com sucesso, o evento fica bloqueado por 20 min (configurável via
    DIRETORIA_RECONSOLIDAR_COOLDOWN_SEC) para outros usuários "Diretoria".
    Usuários Admin/etc bypassam o lock.
    """
    import time as _t
    from datetime import date as _date, timedelta
    from app.services.snapshot_service import consolidar_vendas_grupo
    from app.services.sync_log_service import new_ciclo_id, log_evento
    from app.models.vendas_snapshot import VendasDiariaSnapshot
    from sqlalchemy import func as sa_func2

    # ── Gate ATÔMICO GLOBAL: só permite UMA reconsolidação por vez no
    # sistema inteiro (vale para qualquer perfil). Se outro evento estiver
    # rodando, retorna 429 com qual evento está em curso. A checagem de
    # cooldown adicional (anti-clique compulsivo) só se aplica à Diretoria.
    is_diretoria = _user_is_diretoria(current_user)
    acquired, remaining, busy_evento = _try_acquire_evento_slot(
        evento_grupo, check_cooldown=is_diretoria
    )
    slot_acquired = acquired
    if not acquired:
        if busy_evento is not None:
            if busy_evento == evento_grupo:
                message = (
                    "Já existe uma reconsolidação em andamento para este "
                    "evento. Aguarde a conclusão."
                )
                code = "reconsolidacao_em_andamento"
            else:
                message = (
                    f"Outro evento está sendo reconsolidado agora "
                    f"('{busy_evento}'). Aguarde a conclusão antes de iniciar "
                    f"uma nova reconsolidação."
                )
                code = "outro_evento_em_andamento"
            raise HTTPException(
                status_code=429,
                detail={
                    "code": code,
                    "message": message,
                    "evento_grupo": evento_grupo,
                    "evento_em_andamento": busy_evento,
                },
            )
        # Cooldown da Diretoria
        mins = remaining // 60
        secs = remaining % 60
        tempo = f"{mins}min {secs}s" if mins else f"{secs}s"
        raise HTTPException(
            status_code=429,
            detail={
                "code": "cooldown_diretoria",
                "message": (
                    f"Este evento foi reconsolidado recentemente. "
                    f"Aguarde {tempo} antes de tentar novamente."
                ),
                "remaining_sec": remaining,
                "evento_grupo": evento_grupo,
            },
        )

    # Tudo abaixo do acquire fica dentro de try/finally para garantir que
    # qualquer exceção (incluindo em new_ciclo_id, log_evento, queries de
    # qtd_antes/depois) libere o slot in_flight.
    try:
        ciclo_id = new_ciclo_id()
        triggered_by = current_user.email if hasattr(current_user, 'email') else str(current_user.id)
        ano = _date.today().year
        yesterday = _date.today() - timedelta(days=1)

        # qtd_antes
        try:
            qtd_antes = int(
                db.query(sa_func2.coalesce(sa_func2.sum(VendasDiariaSnapshot.quantidade), 0))
                .filter(
                    VendasDiariaSnapshot.evento_grupo == evento_grupo,
                    VendasDiariaSnapshot.fonte == 'CONSOLIDADO',
                    VendasDiariaSnapshot.ano == ano,
                ).scalar() or 0
            )
        except Exception:
            qtd_antes = None

        log_evento(ciclo_id, "consolidar_evento_manual", "iniciado", nivel="ciclo",
                   detalhes=f"grupo={evento_grupo} incremental={incremental} por {triggered_by}")

        t0 = _t.time()
        try:
            consolidar_vendas_grupo(
                db, evento_grupo, ano,
                data_inicio=None, data_fim=yesterday,
                incremental=incremental,
                ciclo_id=ciclo_id,
                parent_job_name="consolidar_evento_manual",
            )
            duracao_ms = int((_t.time() - t0) * 1000)

            try:
                qtd_depois = int(
                    db.query(sa_func2.coalesce(sa_func2.sum(VendasDiariaSnapshot.quantidade), 0))
                    .filter(
                        VendasDiariaSnapshot.evento_grupo == evento_grupo,
                        VendasDiariaSnapshot.fonte == 'CONSOLIDADO',
                        VendasDiariaSnapshot.ano == ano,
                    ).scalar() or 0
                )
            except Exception:
                qtd_depois = None

            log_evento(ciclo_id, "consolidar_evento_manual", "concluido", nivel="ciclo",
                       detalhes=f"qtd_antes={qtd_antes} qtd_depois={qtd_depois}",
                       duracao_ms=duracao_ms)

            # ── Cooldown: grava lock só para perfil Diretoria após sucesso ─────
            cooldown_until = None
            cooldown_sec_used = 0
            if is_diretoria:
                cooldown_sec_used = _diretoria_cooldown_sec()
                if cooldown_sec_used > 0:
                    cooldown_until = _set_evento_cooldown(evento_grupo, cooldown_sec_used)

            return {
                "status": "ok",
                "evento_grupo": evento_grupo,
                "incremental": incremental,
                "qtd_antes": qtd_antes,
                "qtd_depois": qtd_depois,
                "duracao_ms": duracao_ms,
                "ciclo_id": ciclo_id,
                "cooldown_aplicado": cooldown_until is not None,
                "cooldown_until_epoch": cooldown_until,
                "cooldown_total_sec": cooldown_sec_used,
            }
        except Exception as exc:
            duracao_ms = int((_t.time() - t0) * 1000)
            logger.error(f"consolidar_evento_manual: erro grupo='{evento_grupo}': {exc}")
            log_evento(ciclo_id, "consolidar_evento_manual", "falha", nivel="ciclo",
                       grupo=evento_grupo, motivo=str(exc)[:300], duracao_ms=duracao_ms)
            raise HTTPException(status_code=500, detail=str(exc))
    finally:
        # Sempre libera o slot in_flight em caso de Diretoria (sucesso OU
        # exceção). Em falha, NÃO seta cooldown — usuário pode tentar de novo.
        if slot_acquired:
            _release_evento_slot(evento_grupo)


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
    evento_grupo: str = Query(default=None, description="Filtra para um único evento_grupo (ex: 'Blue Run - Rio de Janeiro'). Se omitido, roda para todos os grupos do ano."),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("marketing")),
):
    from ...services.snapshot_service import backfill_historico
    import logging
    logger = logging.getLogger(__name__)

    start = date.fromisoformat(data_inicio) if data_inicio else None
    end = date.fromisoformat(data_fim) if data_fim else None

    try:
        result = backfill_historico(db, ano, data_inicio=start, data_fim=end, evento_grupo=evento_grupo)
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


@router.post("/snapshots/backfill-scheduled")
def trigger_backfill_scheduled(
    ano: int = Query(..., description="Ano para backfill"),
    data_inicio: str = Query(default=None, description="Data início (YYYY-MM-DD)"),
    data_fim: str = Query(default=None, description="Data fim (YYYY-MM-DD)"),
    evento_grupo: str = Query(default=None, description="Filtra para um único evento_grupo. Se omitido, roda para todos os grupos do ano."),
    x_scheduler_token: Optional[str] = Header(None, alias="X-Scheduler-Token"),
    db: Session = Depends(get_db),
):
    """Variante scheduler-token do backfill histórico.

    Protegida pelo mesmo shared-secret SCHEDULER_TOKEN usado pelo job
    noturno. Existe para permitir disparo manual via curl quando o /docs
    do Swagger não está acessível em produção (frontend SPA captura essa
    rota).

    NÃO substitui o endpoint /snapshots/backfill (que continua exigindo
    JWT) — é só um caminho alternativo de autenticação.
    """
    import logging
    logger = logging.getLogger(__name__)

    expected = (_os.environ.get("SCHEDULER_TOKEN") or "").strip()
    if not expected:
        raise HTTPException(status_code=500, detail="SCHEDULER_TOKEN não configurado no backend")
    received = (x_scheduler_token or "").strip()
    if not received or received != expected:
        logger.warning("[BackfillScheduled] Token inválido/ausente")
        raise HTTPException(status_code=401, detail="Token inválido")

    from ...services.snapshot_service import backfill_historico
    start = date.fromisoformat(data_inicio) if data_inicio else None
    end = date.fromisoformat(data_fim) if data_fim else None

    try:
        result = backfill_historico(db, ano, data_inicio=start, data_fim=end, evento_grupo=evento_grupo)
        logger.info(f"[BackfillScheduled] OK: {result}")
        return {"status": "completed", "resultado": result}
    except Exception as e:
        logger.error(f"[BackfillScheduled] Falhou: {e}")
        return {"status": "error", "message": str(e)}


@router.get("/snapshots/diag-magento-bundle")
def diag_magento_bundle(
    bundle_id: int = Query(..., description="bundle_entity_id do Magento"),
    x_scheduler_token: Optional[str] = Header(None, alias="X-Scheduler-Token"),
):
    """Compara duas leituras Magento para o mesmo bundle:

    A) Contagem agregada (mesma query da Margem por Kit / kit-alignment).
    B) Quebra diária (mesma query do consolidar_vendas_grupo, soma por dia).

    Útil para confirmar se a diferença entre Vendas Global e Vendas Dia
    é de fato resposta parcial Magento ou problema de filtro distinto.
    """
    import logging
    logger = logging.getLogger(__name__)
    from sqlalchemy import text as _sa_text, bindparam as _sa_bind
    from ...core import database as _db_mod

    expected = (_os.environ.get("SCHEDULER_TOKEN") or "").strip()
    received = (x_scheduler_token or "").strip()
    if not expected or received != expected:
        raise HTTPException(status_code=401, detail="Token inválido")

    if _db_mod.engine_magento is None:
        return {"status": "error", "message": "engine_magento indisponível"}

    sql_count = (
        "SELECT COUNT(DISTINCT soi_parent.item_id) AS qtd\n"
        "FROM sales_order_item soi_parent\n"
        "INNER JOIN sales_order so ON so.entity_id = soi_parent.order_id\n"
        "WHERE soi_parent.product_type='bundle'\n"
        "AND soi_parent.product_id = :bid\n"
        "AND so.created_at >= DATE_SUB(CURDATE(), INTERVAL 2 YEAR)\n"
        "AND so.status IN ('processing','complete','approved','aprovado_link','reembolso_parcial','closed','retirado')\n"
        "AND so.state != 'canceled'\n"
        "AND so.base_grand_total > 0\n"
        "AND NOT (so.discount_description LIKE '%%CORTESIA%%' AND so.base_grand_total < 50)\n"
        "AND so.created_at < CURDATE() + INTERVAL 1 DAY\n"
        "AND (so.discount_description IS NULL OR so.discount_description NOT LIKE '%%GRUPOS%%')\n"
        "AND (so.coupon_code IS NULL OR so.coupon_code NOT LIKE 'GRUP%%')\n"
        "AND so.increment_id NOT REGEXP '-[0-9]'\n"
    )

    sql_daily = (
        "SELECT DATE(so.created_at) AS dia, COUNT(DISTINCT soi_parent.item_id) AS qtd\n"
        "FROM sales_order_item soi_parent\n"
        "INNER JOIN sales_order so ON so.entity_id = soi_parent.order_id\n"
        "WHERE soi_parent.product_type='bundle'\n"
        "AND soi_parent.product_id = :bid\n"
        "AND so.created_at >= DATE_SUB(CURDATE(), INTERVAL 2 YEAR)\n"
        "AND so.status IN ('processing','complete','approved','aprovado_link','reembolso_parcial','closed','retirado')\n"
        "AND so.state != 'canceled'\n"
        "AND so.base_grand_total > 0\n"
        "AND NOT (so.discount_description LIKE '%%CORTESIA%%' AND so.base_grand_total < 50)\n"
        "AND so.created_at < CURDATE() + INTERVAL 1 DAY\n"
        "AND (so.discount_description IS NULL OR so.discount_description NOT LIKE '%%GRUPOS%%')\n"
        "AND (so.coupon_code IS NULL OR so.coupon_code NOT LIKE 'GRUP%%')\n"
        "AND so.increment_id NOT REGEXP '-[0-9]'\n"
        "GROUP BY DATE(so.created_at)\n"
        "ORDER BY dia\n"
    )

    out = {"bundle_id": bundle_id}
    try:
        with _db_mod.engine_magento.connect() as conn:
            r1 = conn.execute(_sa_text(sql_count), {"bid": bundle_id}).fetchone()
            out["count_aggregate"] = int(r1[0]) if r1 and r1[0] is not None else 0
            r2 = conn.execute(_sa_text(sql_daily), {"bid": bundle_id}).fetchall()
            daily = [{"dia": str(row[0]), "qtd": int(row[1])} for row in r2]
            out["count_daily_sum"] = sum(d["qtd"] for d in daily)
            out["dias_distintos"] = len(daily)
            out["daily_head"] = daily[:5]
            out["daily_tail"] = daily[-10:]
        out["diff"] = out["count_aggregate"] - out["count_daily_sum"]
        return {"status": "ok", "data": out}
    except Exception as e:
        logger.error(f"[DiagBundle] Falhou: {e}")
        return {"status": "error", "message": f"{type(e).__name__}: {e}"}


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


@router.post("/sync/cycles/{ciclo_id}/interrupt")
def interrupt_single_cycle(
    ciclo_id: str,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("admin_monitoramento")),
):
    """Interrompe imediatamente um ciclo específico pelo ciclo_id."""
    updated = (
        db.query(SyncEventLog)
        .filter(
            SyncEventLog.ciclo_id == ciclo_id,
            SyncEventLog.status == "iniciado",
            SyncEventLog.nivel == "ciclo",
        )
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
    if updated == 0:
        raise HTTPException(status_code=404, detail="Ciclo não encontrado ou não está em execução.")
    return {"status": "interrupted", "ciclo_id": ciclo_id, "cycles_interrupted": updated}


class InterruptBatchRequest(BaseModel):
    ciclo_ids: list[str]


@router.post("/sync/cycles/interrupt-batch")
def interrupt_cycles_batch(
    payload: InterruptBatchRequest,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("admin_monitoramento")),
):
    """Interrompe imediatamente um conjunto de ciclos pelo ciclo_id."""
    if not payload.ciclo_ids:
        return {"status": "ok", "cycles_interrupted": 0}
    updated = (
        db.query(SyncEventLog)
        .filter(
            SyncEventLog.ciclo_id.in_(payload.ciclo_ids),
            SyncEventLog.status == "iniciado",
            SyncEventLog.nivel == "ciclo",
        )
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
    return {"status": "interrupted", "cycles_interrupted": updated}


@router.get("/sync/pause-status")
def get_sync_pause_status(
    current_user: Usuario = Depends(require_permission("admin_monitoramento")),
):
    """Retorna o estado atual de pausa dos jobs de sincronização."""
    from ...core.cache import get_sync_pause_info
    return get_sync_pause_info()


@router.get("/sync/overview")
def get_sync_overview(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("admin_monitoramento")),
):
    """Visão consolidada para o painel "Sincronizações" da Saúde do Sistema.

    Retorna 3 blocos:
      - `scheduled_jobs`: próximas execuções dos jobs fixos (02h/05h/17h BRT) +
        rede de segurança (HojeSyncLoop) e safety check de margem (~90min tick).
      - `today_summary`: eventos/grupos sincronizados hoje, último sync e
        métricas históricas (JobRunHealth) das últimas 7 execuções.
      - `kit_mapping`: status do snapshot margem_bundle_rev (idade, cobertura,
        bundles sem mapeamento — proxy direto pro aviso "X kits sem
        configuração" no topo da tela).
    """
    cache_now = _time_module.time()
    with _sync_overview_cache_lock:
        cached = _sync_overview_cache["data"]
        if cached is not None and (cache_now - _sync_overview_cache["ts"]) < _SYNC_OVERVIEW_CACHE_TTL:
            return _copy.deepcopy(cached)

    from zoneinfo import ZoneInfo as _ZI
    from ...models.vendas_snapshot import MargemBundleRevSnapshot
    from ...models.kit_config import KitConfig
    from ...models.job_run_health import JobRunHealth
    from ...core.cache import get_last_sync_hoje

    _now_brt = datetime.now(_ZI("America/Sao_Paulo"))
    _now_utc = datetime.now(timezone.utc)

    # ── Bloco 1: scheduled_jobs ────────────────────────────────────────────
    def _next_at_hour(h: int) -> datetime:
        """Próxima ocorrência de HH:00 BRT (hoje se ainda não passou, senão amanhã)."""
        target = _now_brt.replace(hour=h, minute=0, second=0, microsecond=0)
        if target <= _now_brt:
            target += timedelta(days=1)
        return target

    _hoje_interval_h = max(1, int(_os.getenv("HOJE_SYNC_INTERVAL_HOURS", "12")))
    _last_hoje_ts = get_last_sync_hoje()
    _hoje_next_iso = None
    _hoje_seconds_until = None
    if _last_hoje_ts is not None:
        _next_hoje_dt = datetime.fromtimestamp(
            _last_hoje_ts + _hoje_interval_h * 3600, tz=_ZI("America/Sao_Paulo")
        )
        _hoje_next_iso = _next_hoje_dt.isoformat()
        _hoje_seconds_until = max(0, int((_next_hoje_dt - _now_brt).total_seconds()))

    # Safety check tick: usa last_safety_tick (módulo main) + intervalo do scheduler
    # para mostrar countdown real. Se nunca rodou (ex.: ENABLE_BACKGROUND_MAGENTO_SYNC=false),
    # next_run fica None e o frontend exibe "tick".
    try:
        from app.core.sync_state import get_last_safety_tick as _gst
        _last_tick_epoch = _gst()
    except Exception:
        _last_tick_epoch = None
    _safety_interval_s = max(60, int(_os.getenv("CACHE_REFRESH_INTERVAL_SECONDS", "5400")))
    _safety_next_iso = None
    _safety_seconds_until = None
    if _last_tick_epoch is not None:
        _next_tick_dt = datetime.fromtimestamp(
            _last_tick_epoch + _safety_interval_s, tz=_ZI("America/Sao_Paulo")
        )
        _safety_next_iso = _next_tick_dt.isoformat()
        _safety_seconds_until = max(0, int((_next_tick_dt - _now_brt).total_seconds()))

    # Detecta atraso do job 02h: se o último ciclo concluído está > 26h atrás,
    # marcamos atrasado=True para o card mostrar badge inline (substitui o banner antigo).
    _last_02h_row = db.query(
        sa_func.max(SyncEventLog.created_at)
    ).filter(
        SyncEventLog.job_name == "consolidacao_diaria_04h",
        SyncEventLog.nivel == "ciclo",
        SyncEventLog.status.in_(["concluido", "ok", "parcial"]),
    ).scalar()
    _job_02h_atrasado = False
    _job_02h_ultima_exec_iso = None
    if _last_02h_row is not None:
        if _last_02h_row.tzinfo is None:
            _last_02h_row = _last_02h_row.replace(tzinfo=timezone.utc)
        _job_02h_ultima_exec_iso = _last_02h_row.isoformat()
        _age_02h_h = (_now_utc - _last_02h_row).total_seconds() / 3600
        _job_02h_atrasado = _age_02h_h > 26
    else:
        _job_02h_atrasado = True  # nunca executou

    _scheduled_jobs = [
        {
            "key": "snapshot_02h",
            "label": "Consolidação diária (snapshot)",
            "next_run_iso": _next_at_hour(2).isoformat(),
            "seconds_until": int((_next_at_hour(2) - _now_brt).total_seconds()),
            "tipo": "fixo",
            "descricao": "Consolida snapshots de vendas do dia + curvas históricas",
            "atrasado": _job_02h_atrasado,
            "ultima_exec_iso": _job_02h_ultima_exec_iso,
        },
        {
            "key": "daily_05h",
            "label": "Refresh diário (manhã)",
            "next_run_iso": _next_at_hour(5).isoformat(),
            "seconds_until": int((_next_at_hour(5) - _now_brt).total_seconds()),
            "tipo": "fixo",
            "descricao": "Sincroniza vendas de hoje + reconstrói cache ISC",
            "atrasado": False,
            "ultima_exec_iso": None,
        },
        {
            "key": "evening_17h",
            "label": "Refresh diário (tarde)",
            "next_run_iso": _next_at_hour(17).isoformat(),
            "seconds_until": int((_next_at_hour(17) - _now_brt).total_seconds()),
            "tipo": "fixo",
            "descricao": "Sincroniza vendas de hoje (segunda passada do dia)",
            "atrasado": False,
            "ultima_exec_iso": None,
        },
        {
            "key": "hoje_loop",
            "label": "Rede de segurança (sync hoje)",
            "next_run_iso": _hoje_next_iso,
            "seconds_until": _hoje_seconds_until,
            "tipo": "rede_seguranca",
            "descricao": f"Só dispara se não houve sync nas últimas {_hoje_interval_h}h",
            "atrasado": False,
            "ultima_exec_iso": None,
        },
        {
            "key": "margem_safety",
            "label": "Verificação de margem",
            "next_run_iso": _safety_next_iso,
            "seconds_until": _safety_seconds_until,
            "tipo": "tick",
            "descricao": f"A cada ~{_safety_interval_s // 60}min — só age se snapshot > 36h durante o dia ou > 25h à noite",
            "atrasado": False,
            "ultima_exec_iso": (
                datetime.fromtimestamp(_last_tick_epoch, tz=timezone.utc).isoformat()
                if _last_tick_epoch is not None else None
            ),
        },
    ]

    # ── Bloco 2: today_summary ─────────────────────────────────────────────
    _today_start_brt = _now_brt.replace(hour=0, minute=0, second=0, microsecond=0)
    _today_start_utc = _today_start_brt.astimezone(timezone.utc)

    _today_grupo_rows = db.query(
        SyncEventLog.grupo,
        SyncEventLog.status,
        SyncEventLog.created_at,
    ).filter(
        SyncEventLog.created_at >= _today_start_utc,
        SyncEventLog.nivel == "grupo",
        SyncEventLog.grupo.isnot(None),
    ).all()

    _grupos_unicos: dict = {}
    for _g, _st, _ts in _today_grupo_rows:
        prev = _grupos_unicos.get(_g)
        if prev is None or _ts > prev[1]:
            _grupos_unicos[_g] = (_st, _ts)

    _eventos_ok = sum(1 for v in _grupos_unicos.values() if v[0] == "ok")
    _eventos_parcial = sum(1 for v in _grupos_unicos.values() if v[0] == "parcial")
    _eventos_falha = sum(1 for v in _grupos_unicos.values() if v[0] == "falha")
    _eventos_pulado = sum(1 for v in _grupos_unicos.values() if v[0] == "pulado")
    _ultimo_sync_iso = (
        max(v[1] for v in _grupos_unicos.values()).astimezone(timezone.utc).isoformat()
        if _grupos_unicos else None
    )

    # Top 10 eventos mais recentes
    _eventos_recentes = sorted(
        [{"grupo": g, "status": v[0], "ts": v[1].astimezone(timezone.utc).isoformat()}
         for g, v in _grupos_unicos.items()],
        key=lambda x: x["ts"], reverse=True,
    )[:10]

    # JobRunHealth: últimas 7 execuções de CADA job (sincronizar_hoje + snapshot_diario).
    # Frontend usa toggle para alternar entre os dois.
    def _serialize_job_runs(job_name: str):
        rows = db.query(JobRunHealth).filter(
            JobRunHealth.job_name == job_name
        ).order_by(desc(JobRunHealth.started_at)).limit(7).all()
        return [
            {
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "duration_ms": r.duration_ms,
                "grupos_total": r.grupos_total,
                "grupos_ok": r.grupos_ok,
                "grupos_parcial": r.grupos_parcial,
                "grupos_falha": r.grupos_falha,
                "status": r.status,
            }
            for r in rows
        ]
    _job_health_by_name = {
        "sincronizar_hoje": _serialize_job_runs("sincronizar_hoje"),
        "snapshot_diario": _serialize_job_runs("snapshot_diario"),
    }

    _today_summary = {
        "eventos_sincronizados": len(_grupos_unicos),
        "eventos_ok": _eventos_ok,
        "eventos_parcial": _eventos_parcial,
        "eventos_falha": _eventos_falha,
        "eventos_pulado": _eventos_pulado,
        "ultimo_sync_iso": _ultimo_sync_iso,
        "eventos_recentes": _eventos_recentes,
        "historico_jobs_by_name": _job_health_by_name,
    }

    # ── Bloco 3: kit_mapping ───────────────────────────────────────────────
    _newest_margem_ts = db.query(
        sa_func.max(MargemBundleRevSnapshot.calculado_em)
    ).scalar()
    _idade_h = None
    _ultima_atualizacao_iso = None
    if _newest_margem_ts is not None:
        if _newest_margem_ts.tzinfo is None:
            _newest_margem_ts = _newest_margem_ts.replace(tzinfo=timezone.utc)
        _idade_h = (_now_utc - _newest_margem_ts).total_seconds() / 3600
        _ultima_atualizacao_iso = _newest_margem_ts.isoformat()

    _total_snap = db.query(
        sa_func.count(MargemBundleRevSnapshot.bundle_entity_id)
    ).scalar() or 0
    _bundles_esperados = db.query(
        sa_func.count(sa_func.distinct(KitConfig.bundle_entity_id))
    ).filter(KitConfig.tipo_kit.isnot(None)).scalar() or 0
    _kits_sem_config = db.query(
        sa_func.count(sa_func.distinct(KitConfig.bundle_entity_id))
    ).filter(KitConfig.tipo_kit.is_(None)).scalar() or 0

    _coverage = (_total_snap / _bundles_esperados) if _bundles_esperados > 0 else None

    _kit_status = "ok"
    if _idade_h is None or _idade_h > 36:
        _kit_status = "critico"
    elif _idade_h > 25 or (_coverage is not None and _coverage < 0.85):
        _kit_status = "atencao"

    # Bundles configurados (tipo_kit != null) que NÃO têm snapshot — diagnóstico
    # do "missing 550 bundles" sem precisar abrir o banco. Limita a 50 pra não inchar
    # a resposta; a flag has_more avisa quando há mais.
    _bundles_faltantes_rows = db.query(
        KitConfig.bundle_entity_id,
        KitConfig.kit_nome,
        KitConfig.tipo_kit,
        KitConfig.id_evento,
    ).outerjoin(
        MargemBundleRevSnapshot,
        MargemBundleRevSnapshot.bundle_entity_id == KitConfig.bundle_entity_id,
    ).filter(
        KitConfig.tipo_kit.isnot(None),
        MargemBundleRevSnapshot.bundle_entity_id.is_(None),
    ).order_by(KitConfig.id_evento.desc().nullslast(), KitConfig.bundle_entity_id).limit(51).all()

    _bundles_faltantes = [
        {
            "bundle_entity_id": int(r[0]),
            "kit_nome": r[1],
            "tipo_kit": r[2],
            "id_evento": int(r[3]) if r[3] is not None else None,
        }
        for r in _bundles_faltantes_rows[:50]
    ]
    # COUNT real do LEFT JOIN (não a diferença de agregados) — evita
    # subestimar quando há snapshots órfãos sem tipo_kit configurado.
    _bundles_faltantes_total = db.query(
        sa_func.count(KitConfig.bundle_entity_id)
    ).outerjoin(
        MargemBundleRevSnapshot,
        MargemBundleRevSnapshot.bundle_entity_id == KitConfig.bundle_entity_id,
    ).filter(
        KitConfig.tipo_kit.isnot(None),
        MargemBundleRevSnapshot.bundle_entity_id.is_(None),
    ).scalar() or 0

    _kit_mapping = {
        "ultima_atualizacao_iso": _ultima_atualizacao_iso,
        "idade_horas": round(_idade_h, 1) if _idade_h is not None else None,
        "bundles_com_snapshot": _total_snap,
        "bundles_esperados": _bundles_esperados,
        "cobertura_pct": round(_coverage * 100, 1) if _coverage is not None else None,
        "kits_sem_configuracao": _kits_sem_config,
        "bundles_sem_snapshot_total": _bundles_faltantes_total,
        "bundles_sem_snapshot_lista": _bundles_faltantes,
        "bundles_sem_snapshot_truncated": len(_bundles_faltantes_rows) > 50,
        "status": _kit_status,
    }

    response = {
        "scheduled_jobs": _scheduled_jobs,
        "today_summary": _today_summary,
        "kit_mapping": _kit_mapping,
        "generated_at": _now_utc.isoformat(),
    }
    with _sync_overview_cache_lock:
        _sync_overview_cache["data"] = _copy.deepcopy(response)
        _sync_overview_cache["ts"] = cache_now
    return response


@router.get("/sync/eventos-ultima-atualizacao")
def list_eventos_ultima_sync(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("admin_monitoramento")),
):
    """Tabela: todos os cadastros de evento ativos com a última sincronização
    conhecida (último SyncEventLog nivel='grupo' para o evento_grupo resolvido).

    Resolução cadastro → evento_grupo:
      1. id_evento_magento → SkuMapping(fonte='MAGENTO').evento_grupo
      2. sku → SkuMapping(qualquer fonte).evento_grupo

    Cadastros sem grupo resolvido retornam evento_grupo=None e ultima_sync=None
    (ainda aparecem na tabela para diagnóstico de mapeamento ausente).
    """
    from ...models.cadastro_evento import CadastroEvento
    from ...models.dimensoes import SkuMapping

    # Dicts de resolução: magento_id → grupo, sku → grupo (qualquer fonte).
    _magento_to_grupo: dict[int, str] = {}
    _sku_to_grupo: dict[str, str] = {}
    for _row in db.query(
        SkuMapping.fonte, SkuMapping.id_externo, SkuMapping.sku, SkuMapping.evento_grupo
    ).filter(
        SkuMapping.ativo == True,  # noqa: E712
        SkuMapping.evento_grupo.isnot(None),
    ).all():
        _fonte, _idext, _sku, _grupo = _row
        if _fonte == "MAGENTO" and _idext is not None:
            _magento_to_grupo.setdefault(int(_idext), _grupo)
        if _sku:
            _sku_to_grupo.setdefault(_sku, _grupo)

    # Última sync por grupo via DISTINCT ON (PostgreSQL).
    _last_sync_rows = db.query(
        SyncEventLog.grupo, SyncEventLog.created_at, SyncEventLog.status,
    ).filter(
        SyncEventLog.nivel == "grupo",
        SyncEventLog.grupo.isnot(None),
    ).distinct(SyncEventLog.grupo).order_by(
        SyncEventLog.grupo, SyncEventLog.created_at.desc(),
    ).all()
    _last_by_grupo: dict[str, tuple] = {
        r[0]: (r[1], r[2]) for r in _last_sync_rows
    }

    # Cadastros ativos (não soft-deleted).
    _cadastros = db.query(
        CadastroEvento.id,
        CadastroEvento.nome_evento,
        CadastroEvento.data_evento,
        CadastroEvento.status,
        CadastroEvento.sku,
        CadastroEvento.id_evento_magento,
    ).filter(CadastroEvento.deleted_at.is_(None)).all()

    _eventos: list[dict] = []
    for c in _cadastros:
        _grupo = None
        if c.id_evento_magento is not None:
            _grupo = _magento_to_grupo.get(int(c.id_evento_magento))
        if _grupo is None and c.sku:
            _grupo = _sku_to_grupo.get(c.sku)
        _last = _last_by_grupo.get(_grupo) if _grupo else None
        _eventos.append({
            "id_cadastro": int(c.id),
            "nome_evento": c.nome_evento,
            "data_evento": c.data_evento.isoformat() if c.data_evento else None,
            "status_cadastro": c.status,
            "evento_grupo": _grupo,
            "id_evento_magento": int(c.id_evento_magento) if c.id_evento_magento is not None else None,
            "ultima_sync_iso": _last[0].astimezone(timezone.utc).isoformat() if _last else None,
            "ultima_sync_status": _last[1] if _last else None,
        })

    # Ordena: nunca sincronizado primeiro (diagnóstico), depois por última sync desc.
    _eventos.sort(key=lambda e: (
        0 if e["ultima_sync_iso"] is None else 1,
        e["ultima_sync_iso"] or "",
    ), reverse=True)
    # Após o reverse: 1 (com sync) vem antes de 0 (sem sync) — invertemos manualmente.
    _com = [e for e in _eventos if e["ultima_sync_iso"] is not None]
    _sem = [e for e in _eventos if e["ultima_sync_iso"] is None]
    _com.sort(key=lambda e: e["ultima_sync_iso"], reverse=True)
    _sem.sort(key=lambda e: e["nome_evento"] or "")
    _eventos_final = _com + _sem

    return {
        "total": len(_eventos_final),
        "com_sync": len(_com),
        "sem_sync": len(_sem),
        "eventos": _eventos_final,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


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
