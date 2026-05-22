from datetime import datetime, date, timedelta
from fastapi import APIRouter, Depends, Query, HTTPException
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
}

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


@router.post("/snapshots/consolidar-full")
def trigger_snapshot_consolidation_full(
    incremental: bool = Query(default=False, description="True=incremental (só dias novos). False=reconstrução completa."),
    resume: bool = Query(default=False, description="True=retomar o ciclo incompleto mais recente; ignora 'incremental' e usa o do ciclo original."),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("admin_monitoramento")),
):
    """Consolidação completa de snapshots de todos os eventos com rastreamento de progresso em tempo real.

    Quando ``resume=True``, retoma o último ciclo incompleto: pula os grupos que
    já estão no ``consolidacao_checkpoint`` com status='ok' e reprocessa o resto.
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

    with _consolidation_full_lock:
        if _consolidation_full_progress.get("status") == "running":
            return {
                "status": "already_running",
                "message": "Já existe uma consolidação em andamento",
            }
        _consolidation_full_progress = {
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
        }

    def _run_full():
        global _consolidation_full_progress
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
            local_db.close()

    t = _threading.Thread(target=_run_full, daemon=True)
    t.start()
    return {"status": "started", "message": "Consolidação completa iniciada em background"}


@router.get("/snapshots/consolidar-full/progress")
def get_snapshot_consolidation_full_progress(
    current_user: Usuario = Depends(require_permission("marketing")),
):
    """Retorna o progresso atual da consolidação completa de snapshots."""
    with _consolidation_full_lock:
        return _copy.deepcopy(_consolidation_full_progress)


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
    """
    import time as _t
    from datetime import date as _date, timedelta
    from app.services.snapshot_service import consolidar_vendas_grupo
    from app.services.sync_log_service import new_ciclo_id, log_evento
    from app.models.vendas_snapshot import VendasDiariaSnapshot
    from sqlalchemy import func as sa_func2

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

        return {
            "status": "ok",
            "evento_grupo": evento_grupo,
            "incremental": incremental,
            "qtd_antes": qtd_antes,
            "qtd_depois": qtd_depois,
            "duracao_ms": duracao_ms,
            "ciclo_id": ciclo_id,
        }
    except Exception as exc:
        duracao_ms = int((_t.time() - t0) * 1000)
        logger.error(f"consolidar_evento_manual: erro grupo='{evento_grupo}': {exc}")
        log_evento(ciclo_id, "consolidar_evento_manual", "falha", nivel="ciclo",
                   grupo=evento_grupo, motivo=str(exc)[:300], duracao_ms=duracao_ms)
        raise HTTPException(status_code=500, detail=str(exc))


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
