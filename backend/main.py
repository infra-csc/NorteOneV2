from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy import text
from contextlib import asynccontextmanager
import os
import time
from app.core.database import engine, Base, init_mysql_connections, engine_ativo, init_ssh_tunnel, close_ssh_tunnel, stop_ssh_watchdog, engine_ssh
from app.api.routes import auth, users, centros_custo, projetos, categorias_atletas, dashboard, nori, tarefas, cadastros, atletas_externos, magento, inscricoes_consolidado, marketing, sku_mappings, perfil_acesso, distancias, cotacoes, admin, kit_config
from app.core.cache import (
    cache_scheduler, warm_all_caches_from_db,
    set_last_full_refresh, set_full_refresh_in_progress, 
    set_last_sync_hoje,
    register_full_warmup_fn,
    isc_cache, event_detail_cache, curva_cache, medias_cache,
    _full_refresh_lock,
    set_warmup_metadata_cache, clear_warmup_metadata_cache,
    set_gap_detection_result, set_known_tier1_ids,
    get_gap_detection_result,
)
import app.core.cache as _cache_module
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

_no_grupo_event_ids: set = set()

def _scheduled_isc_refresh():
    from app.core.database import SessionLocal
    db = None
    try:
        db = SessionLocal()
        marketing.fetch_isc_pricing_data(db=db, force_refresh=True)
        logger.info("Scheduled ISC cache refresh completed successfully")
    except Exception as e:
        logger.error(f"Scheduled ISC cache refresh failed: {e}")
        try:
            from app.services.health_alert_service import log_and_alert
            log_and_alert("ISC_REFRESH_FAILED", "HIGH", f"Falha no refresh automático do ISC", str(e))
        except Exception:
            pass
    finally:
        if db:
            db.close()


def _scheduled_sincronizar_hoje():
    from app.core.database import SessionLocal
    from app.services.snapshot_service import sincronizar_hoje_batch
    import time as _time
    db = None
    try:
        db = SessionLocal()
        count = sincronizar_hoje_batch(db)
        logger.info(f"Scheduled sincronizar_hoje_batch completed: {count} groups synced")
        set_last_sync_hoje(_time.time())
        logger.info("last_sync_hoje atualizado após sincronizar_hoje_batch")
    except Exception as e:
        logger.error(f"Scheduled sincronizar_hoje_batch failed: {e}")
        try:
            from app.services.health_alert_service import log_and_alert
            log_and_alert("SYNC_BATCH_FAILED", "HIGH", f"Falha na sincronização diária de snapshots", str(e))
        except Exception:
            pass
    finally:
        if db:
            db.close()


def _scheduled_nori_insights():
    from app.core.database import SessionLocal
    import asyncio as _aio
    db = None
    try:
        db = SessionLocal()
        from app.services.nori_insights_service import run_proactive_insights_job
        result = _aio.run(run_proactive_insights_job(db))
        logger.info(f"Scheduled Nori insights job completed: {result}")
    except Exception as e:
        logger.error(f"Scheduled Nori insights job failed: {e}")
    finally:
        if db:
            db.close()


def _full_cache_warmup():
    from app.core.database import SessionLocal
    from app.core.cache import set_warmup_progress, set_last_refresh_error, update_warmup_sub_progress
    from datetime import datetime
    from app.models.cadastro_evento import CadastroEvento
    from app.models.dimensoes import DimProjeto, SkuMapping
    from app.api.routes.marketing import (
        fetch_isc_pricing_data, normalize_sku, calculate_d_minus,
        get_event_regime, today_brazil,
        _build_sku_to_grupo_map,
        clear_warmup_daily_cache,
        _hist_pattern_cache, _hist_pattern_cache_lock
    )
    from datetime import timedelta as _warmup_timedelta

    TIER1_D_MINUS_THRESHOLD = 60

    with _full_refresh_lock:
        if _cache_module._full_refresh_in_progress:
            logger.warning("Full cache warmup already in progress — skipping duplicate run to prevent concurrent DB conflicts")
            return
        _cache_module._full_refresh_in_progress = True
        _cache_module._warmup_progress["step"] = 1
        _cache_module._warmup_progress["label"] = "Iniciando atualização..."
        _cache_module._warmup_progress["started_at"] = time.time()
        _cache_module._warmup_progress["sub_current"] = 0
        _cache_module._warmup_progress["sub_total"] = 0
    set_last_refresh_error(None)
    from app.core.cache import set_warmup_event_results as _clear_wer, set_warmup_summary as _clear_ws
    _clear_wer({})
    _clear_ws({})
    start = time.time()
    logger.info("=== FULL CACHE WARMUP STARTED ===")

    partial_warnings = []
    db = None
    try:
        db = SessionLocal()
        ano = datetime.now().year
        from concurrent.futures import ThreadPoolExecutor as _TPE

        with _hist_pattern_cache_lock:
            _hist_pattern_cache.clear()
        logger.info(f"[Warmup] Cleared hist_pattern cache for {ano}")

        set_warmup_progress(1, "Atualizando dados de inscrições", 0, 4)

        # --- Phase 1a: metadata pre-fetch (fast, ~0.5s) ---
        prefetch_start = time.time()
        all_cadastros = db.query(CadastroEvento).all()
        all_sku_mappings = db.query(SkuMapping).filter(SkuMapping.ativo == True).all()
        all_projetos = db.query(DimProjeto).all()

        from types import SimpleNamespace

        def _detach_sku(m):
            return SimpleNamespace(
                id=m.id, fonte=m.fonte, id_externo=m.id_externo, sku=m.sku,
                evento_grupo=m.evento_grupo, ano=m.ano, nome_evento=m.nome_evento,
                ativo=m.ativo, evento_consolidado_id=m.evento_consolidado_id,
                data_evento=getattr(m, 'data_evento', None)
            )

        def _detach_proj(p):
            return SimpleNamespace(
                id=p.id, codigo=p.codigo, produto=p.produto, modalidade=p.modalidade,
                tipo_evento=p.tipo_evento, evento=p.evento, lei=p.lei, cliente=p.cliente,
                status=p.status, data_evento=p.data_evento, local_evento=p.local_evento,
                cidade=p.cidade, estado=p.estado, capacidade_maxima=p.capacidade_maxima,
                etapa=p.etapa, imagem_kv=p.imagem_kv
            )

        def _detach_cad(c):
            return SimpleNamespace(
                id=c.id, projeto_id=c.projeto_id, nome=c.nome,
                circuito_produto=c.circuito_produto, localizacao_evento=c.localizacao_evento,
                ano_evento=c.ano_evento, imagem_kv=c.imagem_kv, status=c.status,
                modalidade=c.modalidade, sku=c.sku, produto=c.produto,
                tipo_evento=c.tipo_evento, lei=c.lei, capacidade_maxima=c.capacidade_maxima,
                cidade=c.cidade, estado=c.estado, data_evento=c.data_evento,
                atletas_site_pago=c.atletas_site_pago,
                atletas_site_tkt_medio=c.atletas_site_tkt_medio,
                atletas_grupos_pago=c.atletas_grupos_pago,
                atletas_grupos_tkt_medio=c.atletas_grupos_tkt_medio,
                atletas_cortesia=c.atletas_cortesia,
                atletas_appai_pago=c.atletas_appai_pago,
                atletas_appai_tkt_medio=c.atletas_appai_tkt_medio,
                dias_encerramento_inscricao=c.dias_encerramento_inscricao
            )

        sku_by_grupo = {}
        sku_by_sku = {}
        for m in all_sku_mappings:
            dm = _detach_sku(m)
            if m.evento_grupo and m.ano:
                key = f"{m.evento_grupo}_{m.ano}"
                sku_by_grupo.setdefault(key, []).append(dm)
            if m.sku:
                sku_key = m.sku.upper().strip()
                sku_by_sku.setdefault(sku_key, []).append(dm)

        proj_by_codigo = {}
        proj_by_id = {}
        detached_all_projetos = []
        for p in all_projetos:
            dp = _detach_proj(p)
            detached_all_projetos.append(dp)
            proj_by_id[p.id] = dp
            if p.codigo:
                key = str(p.codigo).upper().strip()
                proj_by_codigo.setdefault(key, []).append(dp)

        cad_by_proj = {}
        for c in all_cadastros:
            if c.projeto_id:
                cad_by_proj[c.projeto_id] = _detach_cad(c)

        set_warmup_metadata_cache(sku_by_grupo, sku_by_sku, proj_by_codigo, proj_by_id, cad_by_proj, detached_all_projetos)
        logger.info(f"[Warmup 1/4] Metadata pre-fetched: {len(all_sku_mappings)} SkuMappings, {len(all_projetos)} DimProjetos, {len(all_cadastros)} Cadastros in {time.time()-prefetch_start:.1f}s")
        update_warmup_sub_progress(2)

        sku_to_grupo = _build_sku_to_grupo_map(db, ano)

        tier1_evento_ids = []
        tier2_evento_ids = []
        grupo_names_seen = set()
        grupo_d_minus = {}

        for cad in all_cadastros:
            if not cad.projeto_id:
                continue
            projeto = proj_by_id.get(cad.projeto_id)
            if not projeto or not projeto.data_evento:
                continue

            _reg_close = projeto.data_evento - _warmup_timedelta(days=2)
            _raw_dm = (_reg_close - today_brazil()).days
            _regime = get_event_regime(_raw_dm)
            if _regime == "consolidated":
                continue

            d_minus = max(0, _raw_dm)

            sku_norm = normalize_sku(str(projeto.codigo)) if projeto.codigo else None
            grupo_nome = sku_to_grupo.get(sku_norm) if sku_norm else None

            if grupo_nome:
                if grupo_nome not in grupo_names_seen:
                    grupo_names_seen.add(grupo_nome)
                    eid = f"grp_{grupo_nome}"
                    grupo_d_minus[eid] = d_minus
                    if d_minus <= TIER1_D_MINUS_THRESHOLD:
                        tier1_evento_ids.append(eid)
                    else:
                        tier2_evento_ids.append(eid)
                else:
                    eid = f"grp_{grupo_nome}"
                    if eid in grupo_d_minus:
                        grupo_d_minus[eid] = min(grupo_d_minus[eid], d_minus)
                        if grupo_d_minus[eid] <= TIER1_D_MINUS_THRESHOLD and eid in tier2_evento_ids:
                            tier2_evento_ids.remove(eid)
                            tier1_evento_ids.append(eid)
            elif not grupo_nome:
                eid = str(projeto.id)
                if d_minus <= TIER1_D_MINUS_THRESHOLD:
                    tier1_evento_ids.append(eid)
                else:
                    tier2_evento_ids.append(eid)

        active_evento_ids = tier1_evento_ids + tier2_evento_ids
        logger.info(f"[Warmup] Found {len(active_evento_ids)} active events: Tier 1 (d-≤{TIER1_D_MINUS_THRESHOLD}): {len(tier1_evento_ids)}, Tier 2 (d->{TIER1_D_MINUS_THRESHOLD}): {len(tier2_evento_ids)}")
        update_warmup_sub_progress(4)

        # --- Collect recently-completed events (last 14 days) for warmup ---
        RECENTLY_COMPLETED_DAYS = 14
        recently_completed_ids = []
        _recent_grupo_seen = set()
        for _rcad in all_cadastros:
            if not _rcad.projeto_id:
                continue
            _rproj = proj_by_id.get(_rcad.projeto_id)
            if not _rproj or not _rproj.data_evento:
                continue
            _rreg_close = _rproj.data_evento - _warmup_timedelta(days=2)
            _rraw_dm = (_rreg_close - today_brazil()).days
            if _rraw_dm >= -1 or _rraw_dm < -RECENTLY_COMPLETED_DAYS:
                continue  # Only want events 2–14 days in the past
            _rsku_norm = normalize_sku(str(_rproj.codigo)) if _rproj.codigo else None
            _rgrupo_nome = sku_to_grupo.get(_rsku_norm) if _rsku_norm else None
            if _rgrupo_nome:
                _reid = f"grp_{_rgrupo_nome}"
                if _reid not in _recent_grupo_seen and _reid not in active_evento_ids:
                    _recent_grupo_seen.add(_reid)
                    recently_completed_ids.append(_reid)
            else:
                _reid = str(_rproj.id)
                if _reid not in _recent_grupo_seen and _reid not in active_evento_ids:
                    _recent_grupo_seen.add(_reid)
                    recently_completed_ids.append(_reid)
        if recently_completed_ids:
            logger.info(f"[Warmup] Found {len(recently_completed_ids)} recently-completed events (last {RECENTLY_COMPLETED_DAYS} days) — will pre-warm in background")

        # --- Phase 1b: kick off event_detail pre-warm for ALL active + recently-completed events ---
        _all_prewarm_ids = active_evento_ids + recently_completed_ids
        _detail_futures: dict = {}
        _tier1_aux_futures: dict = {}
        _prewarm_detail_fn = None
        if _all_prewarm_ids:
            from app.api.routes.marketing import (
                get_marketing_event_by_id as _get_evt_detail,
                get_sales_averages as _get_medias,
                get_curva_snapshot as _get_curva
            )
            _detail_prewarm_executor = _TPE(max_workers=min(3, len(_all_prewarm_ids)), thread_name_prefix="warmup_detail")

            def _prewarm_detail_fn(eid, _ano):
                from fastapi import HTTPException as _HTTPEx
                if eid in _no_grupo_event_ids:
                    return "skipped_no_grupo"
                _db2 = SessionLocal()
                try:
                    _get_evt_detail(evento_id=eid, ano=_ano, force_refresh=True, db=_db2, current_user=None)
                    return "ok"
                except _HTTPEx as _he:
                    _detail = str(getattr(_he, 'detail', '')).lower()
                    if "sem grupo" in _detail:
                        _no_grupo_event_ids.add(eid)
                        logger.info(f"[Warmup] Evento {eid} sem grupo configurado – ignorado nos próximos ciclos")
                    else:
                        logger.warning(f"[Warmup] event_detail failed for {eid}: {_he}")
                    return "failed"
                except Exception as _e:
                    logger.warning(f"[Warmup] event_detail failed for {eid}: {_e}")
                    return "failed"
                finally:
                    _db2.close()

            for _eid in _all_prewarm_ids:
                _detail_futures[_eid] = _detail_prewarm_executor.submit(_prewarm_detail_fn, _eid, ano)
            _detail_prewarm_executor.shutdown(wait=False)
            logger.info(f"[Warmup] event_detail background pre-warm started for {len(active_evento_ids)} active + {len(recently_completed_ids)} recent events ({min(3, len(_all_prewarm_ids))} workers)")

            # --- Phase 1b-extra: prewarm medias_vendas + curva_comparativa for Tier 1 events ---
            if tier1_evento_ids:
                _tier1_aux_executor = _TPE(max_workers=min(2, len(tier1_evento_ids)), thread_name_prefix="warmup_tier1")

                def _prewarm_tier1_aux(eid, _ano):
                    if eid in _no_grupo_event_ids:
                        return "skipped_no_grupo"
                    _db3 = SessionLocal()
                    try:
                        _get_medias(evento_id=eid, periodo=30, ano=_ano, force_refresh=True, db=_db3, current_user=None, response=None)
                        logger.info(f"[Warmup BG] medias pre-warm OK: {eid}")
                    except Exception as _e:
                        logger.warning(f"[Warmup BG] medias pre-warm failed for {eid}: {_e}")
                    try:
                        _get_curva(evento_id=eid, ano=_ano, db=_db3, current_user=None)
                        logger.info(f"[Warmup BG] curva pre-warm OK: {eid}")
                    except Exception as _e:
                        logger.warning(f"[Warmup BG] curva pre-warm failed for {eid}: {_e}")
                    finally:
                        _db3.close()
                    return "ok"

                for _eid in tier1_evento_ids:
                    _tier1_aux_futures[_eid] = _tier1_aux_executor.submit(_prewarm_tier1_aux, _eid, ano)
                _tier1_aux_executor.shutdown(wait=False)
                logger.info(f"[Warmup] medias+curva Tier 1 pre-warm started for {len(tier1_evento_ids)} events ({min(3, len(tier1_evento_ids))} workers)")

        # --- Phase 1b-early: pre-populate eventos_list with seeded ISC data ---
        # This ensures users see data immediately even while the slow ISC Magento
        # query (up to 8 minutes) is still running. After ISC refresh completes,
        # Phase 2 will rebuild eventos_list with fresh data.
        try:
            from app.api.routes.marketing import (
                get_marketing_events as _get_mkt_events_early,
                eventos_list_cache as _evt_list_cache_early
            )
            _early_key_all = f"{ano}_all_all_"
            _early_key_active = f"{ano}_active_all_"
            _early_cached_all, _ = _evt_list_cache_early.get_or_revalidate(_early_key_all, refresh_fn=None)
            _early_cached_active, _ = _evt_list_cache_early.get_or_revalidate(_early_key_active, refresh_fn=None)
            if _early_cached_all is None or _early_cached_active is None:
                logger.info("[Warmup 1b-early] eventos_list cache miss — pre-populating with seeded ISC data...")
                _early_db = SessionLocal()
                try:
                    if _early_cached_active is None:
                        _get_mkt_events_early(ano=ano, status="active", categoria=None, busca=None, force_refresh=True, db=_early_db, current_user=None)
                        logger.info(f"[Warmup 1b-early] '{ano}_active_all_' pre-populated")
                    if _early_cached_all is None:
                        _get_mkt_events_early(ano=ano, status=None, categoria=None, busca=None, force_refresh=True, db=_early_db, current_user=None)
                        logger.info(f"[Warmup 1b-early] '{ano}_all_all_' pre-populated")
                finally:
                    _early_db.close()
            else:
                logger.info("[Warmup 1b-early] eventos_list cache already warm — skipping early pre-populate")
        except Exception as _early_err:
            logger.warning(f"[Warmup 1b-early] Early eventos_list pre-populate failed (non-critical): {_early_err}")

        # --- Phase 1c: ISC refresh (heavy, ~44s) — runs in parallel with event_detail pre-warm ---
        logger.info("[Warmup 1/4] Refreshing ISC pricing data...")
        try:
            fetch_isc_pricing_data(db=db, force_refresh=True)
            logger.info("[Warmup 1/4] ISC pricing data refreshed")
            update_warmup_sub_progress(1)
            # Atualiza o timestamp logo após o ISC ser renovado, sem aguardar o warmup
            # completo de 300+ eventos (~43 min). Assim, se o servidor reiniciar durante
            # a fase de event_detail, o dashboard não exibirá uma data obsoleta.
            set_last_full_refresh(time.time())
            logger.info("[Warmup 1/4] last_full_refresh atualizado após ISC refresh")
        except Exception as e:
            logger.error(f"[Warmup 1/4] ISC pricing data FAILED: {e}")
            partial_warnings.append(f"Dados de inscrições parciais: {str(e)[:100]}")

        logger.info(f"[Warmup 1/4] Phase 1 complete in {time.time()-start:.1f}s")

        # --- Phase 1d: collect event_detail futures with per-event timeout; retry failures ---
        _warmup_event_results: dict = {}
        if _detail_futures and _prewarm_detail_fn:
            from concurrent.futures import TimeoutError as _FutureTimeout
            _DETAIL_TIMEOUT = 300
            _failed_eids: list = []
            _total_detail = len(_detail_futures)
            logger.info(f"[Warmup 1d] Collecting event_detail results for {_total_detail} events (timeout {_DETAIL_TIMEOUT}s each)...")
            set_warmup_progress(2, "Preparando detalhes dos eventos", 0, _total_detail)
            _done_count = 0
            for _eid, _fut in _detail_futures.items():
                try:
                    _r = _fut.result(timeout=_DETAIL_TIMEOUT)
                    _warmup_event_results[_eid] = _r
                    if _r != "ok":
                        _failed_eids.append(_eid)
                except _FutureTimeout:
                    logger.warning(f"[Warmup 1d] Timeout collecting event_detail for {_eid}")
                    _warmup_event_results[_eid] = "timeout"
                    _failed_eids.append(_eid)
                except Exception as _ec:
                    logger.warning(f"[Warmup 1d] Exception collecting event_detail for {_eid}: {_ec}")
                    _warmup_event_results[_eid] = "failed"
                    _failed_eids.append(_eid)
                finally:
                    _done_count += 1
                    update_warmup_sub_progress(_done_count)

            if _failed_eids:
                logger.info(f"[Warmup 1d] Second pass: retrying {len(_failed_eids)} failed/timeout events (4 workers, timeout 600s)...")
                _retry_executor = _TPE(max_workers=min(4, len(_failed_eids)), thread_name_prefix="warmup_retry")
                _retry_futs = {_eid: _retry_executor.submit(_prewarm_detail_fn, _eid, ano) for _eid in _failed_eids}
                _retry_executor.shutdown(wait=False)
                for _eid, _fut in _retry_futs.items():
                    try:
                        _r = _fut.result(timeout=600)
                        _warmup_event_results[_eid] = "retried_ok" if _r == "ok" else "failed"
                        if _r == "ok":
                            logger.info(f"[Warmup 1d] Retry OK: {_eid}")
                    except _FutureTimeout:
                        _warmup_event_results[_eid] = "timeout"
                        logger.warning(f"[Warmup 1d] Retry timeout: {_eid}")
                    except Exception as _ec:
                        _warmup_event_results[_eid] = "failed"
                        logger.warning(f"[Warmup 1d] Retry exception for {_eid}: {_ec}")

            _ok_cnt = sum(1 for v in _warmup_event_results.values() if v == "ok")
            _retried_ok_cnt = sum(1 for v in _warmup_event_results.values() if v == "retried_ok")
            _fail_cnt = len(_warmup_event_results) - _ok_cnt - _retried_ok_cnt
            logger.info(f"[Warmup] event_detail summary: {_ok_cnt}/{len(_warmup_event_results)} OK, {_retried_ok_cnt} retried OK, {_fail_cnt} still failed")

            from app.core.cache import set_warmup_event_results as _set_wer, set_warmup_summary as _set_ws
            _set_wer(_warmup_event_results)
            _warmup_elapsed = time.time() - start
            _set_ws({
                "total": len(_warmup_event_results),
                "ok": _ok_cnt,
                "retried_ok": _retried_ok_cnt,
                "failed": _fail_cnt,
                "duration_seconds": round(_warmup_elapsed, 1),
                "completed_at": datetime.utcnow().isoformat() + "Z"
            })

        # --- Phase 1d-extra: collect tier1 aux (medias/curva) futures with timeout ---
        if _tier1_aux_futures:
            from concurrent.futures import TimeoutError as _FutureTimeout2
            _t1_ok = 0
            _t1_fail = 0
            for _eid, _fut in _tier1_aux_futures.items():
                try:
                    _fut.result(timeout=300)
                    _t1_ok += 1
                except _FutureTimeout2:
                    logger.warning(f"[Warmup 1d] Tier1 aux timeout: {_eid}")
                    _t1_fail += 1
                except Exception as _ec:
                    logger.warning(f"[Warmup 1d] Tier1 aux exception for {_eid}: {_ec}")
                    _t1_fail += 1
            logger.info(f"[Warmup] medias+curva summary: {_t1_ok} OK, {_t1_fail} failed from {len(_tier1_aux_futures)} Tier1 events")

        set_warmup_progress(3, "Finalizando lista", 0, 1)

        from app.api.routes.marketing import (
            get_marketing_events,
            eventos_list_cache as _evt_list_cache
        )

        clear_warmup_daily_cache()
        clear_warmup_metadata_cache()

        # Atomic cache swap: build fresh data FIRST, then clear stale filter entries.
        # This ensures there is never a window where the main cache keys are empty,
        # so users browsing the dashboard always see data during background refresh.
        try:
            logger.info(f"[Warmup 2/4] Populating default dashboard list cache keys (atomic swap)")
            _warmup_db = SessionLocal()
            try:
                get_marketing_events(ano=ano, status="active", categoria=None, busca=None, force_refresh=True, db=_warmup_db, current_user=None)
                logger.info(f"[Warmup 2/4] List cache key '{ano}_active_all_' populated")
                get_marketing_events(ano=ano, status=None, categoria=None, busca=None, force_refresh=True, db=_warmup_db, current_user=None)
                logger.info(f"[Warmup 2/4] List cache key '{ano}_all_all_' populated")
            finally:
                _warmup_db.close()
        except Exception as e:
            logger.warning(f"[Warmup 2/4] Failed to populate list cache: {e}")

        # After new main keys are ready, purge any stale filter-specific entries
        # (e.g., 2026_active_corrida_, 2026_all_trail_, etc.) but keep the fresh ones.
        _keep_keys = {f"{ano}_active_all_", f"{ano}_all_all_"}
        _evt_list_cache.invalidate_all_except(_keep_keys)
        logger.info("[Warmup 2/4] Caches cleaned, stale filter entries purged (main keys preserved)")

        set_last_full_refresh(time.time())
        elapsed = time.time() - start
        logger.info(f"=== FULL CACHE WARMUP COMPLETED in {elapsed:.1f}s ===")
        logger.info(f"    Active events identified: Tier1={len(tier1_evento_ids)}, Tier2={len(tier2_evento_ids)}")
        logger.info(f"    Detail pre-warm: {len(_detail_futures)} events processed (ok={sum(1 for v in _warmup_event_results.values() if v=='ok')}, retried_ok={sum(1 for v in _warmup_event_results.values() if v=='retried_ok')}, failed={sum(1 for v in _warmup_event_results.values() if v not in ('ok','retried_ok'))})")
        update_warmup_sub_progress(1)

        if partial_warnings:
            set_last_refresh_error("Atualização concluída com avisos: " + "; ".join(partial_warnings))

    except Exception as e:
        logger.error(f"Full cache warmup failed: {e}", exc_info=True)
        set_last_refresh_error(f"Falha na atualização dos dados: {str(e)}")
        try:
            from app.services.health_alert_service import log_and_alert
            log_and_alert("WARMUP_FAILED", "CRITICAL", "Falha crítica no refresh completo dos dados", str(e))
        except Exception:
            pass
    finally:
        clear_warmup_daily_cache()
        clear_warmup_metadata_cache()
        set_full_refresh_in_progress(False)
        if db:
            try:
                db.close()
            except Exception:
                pass

def _startup_tier1_gap_warmup():
    """Detect and warm Tier 1 events with missing or stale (>25h) cache right after startup DB load."""
    from app.core.database import SessionLocal
    from app.models.cadastro_evento import CadastroEvento
    from app.models.dimensoes import DimProjeto, SkuMapping
    from app.api.routes.marketing import (
        normalize_sku, calculate_d_minus, get_event_regime, today_brazil,
        _build_sku_to_grupo_map, get_marketing_event_by_id
    )
    from datetime import datetime as _dt, timedelta as _td, date as _date
    from concurrent.futures import ThreadPoolExecutor as _TPE, as_completed as _as_completed
    import time as _time

    GAP_STALE_SECONDS = 25 * 3600
    GAP_TIER1_THRESHOLD = 60
    GAP_WORKERS = 2
    GAP_TIMEOUT = 180

    db = None
    try:
        db = SessionLocal()
        ano = _dt.now().year
        all_cadastros = db.query(CadastroEvento).all()
        all_projetos = db.query(DimProjeto).all()
        proj_by_id = {p.id: p for p in all_projetos}

        sku_to_grupo = _build_sku_to_grupo_map(db, ano)

        today = today_brazil()
        grupo_min_dm: dict = {}
        standalone_dm: dict = {}

        for cad in all_cadastros:
            if not cad.projeto_id:
                continue
            proj = proj_by_id.get(cad.projeto_id)
            if not proj or not proj.data_evento:
                continue

            if proj.data_evento.year != ano or proj.data_evento < today:
                continue

            reg_close = proj.data_evento - _td(days=2)
            raw_dm = (reg_close - today).days
            regime = get_event_regime(raw_dm)
            if regime == "consolidated":
                continue

            d_minus = max(0, raw_dm)
            sku_norm = normalize_sku(str(proj.codigo)) if proj.codigo else None
            grupo_nome = sku_to_grupo.get(sku_norm) if sku_norm else None

            if grupo_nome:
                eid = f"grp_{grupo_nome}"
                grupo_min_dm[eid] = min(grupo_min_dm.get(eid, d_minus), d_minus)
            else:
                eid = str(proj.id)
                standalone_dm[eid] = min(standalone_dm.get(eid, d_minus), d_minus)

        all_event_dm = {**grupo_min_dm, **standalone_dm}
        tier1_ids = [eid for eid, dm in all_event_dm.items() if dm <= GAP_TIER1_THRESHOLD]

        db.close()
        db = None

        set_known_tier1_ids(tier1_ids)

        now_ts = _time.time()
        timestamps = event_detail_cache.get_all_timestamps()

        missing_ids = []
        stale_ids = []
        for eid in tier1_ids:
            cache_key = f"{ano}_{eid}_detail"
            ts = timestamps.get(cache_key)
            if ts is None:
                missing_ids.append(eid)
            elif (now_ts - ts) > GAP_STALE_SECONDS:
                stale_ids.append(eid)

        set_gap_detection_result({
            "tier1_event_count": len(tier1_ids),
            "missing_tier1_events": missing_ids,
            "stale_tier1_events": stale_ids,
            "detected_at": _dt.now().isoformat(),
        })

        needs_warmup = missing_ids + stale_ids
        if not needs_warmup:
            logger.info(f"[StartupGap] All {len(tier1_ids)} Tier1 events have fresh cache. Nothing to warm.")
            return

        logger.info(f"[StartupGap] {len(needs_warmup)} Tier1 events need warmup: {len(missing_ids)} missing, {len(stale_ids)} stale. Starting targeted warmup with {GAP_WORKERS} workers...")

        def _gap_warm_one(eid):
            from fastapi import HTTPException as _HTTPEx
            if eid in _no_grupo_event_ids:
                return eid, "skipped_no_grupo"
            _db = None
            try:
                _db = SessionLocal()
                get_marketing_event_by_id(evento_id=eid, ano=ano, force_refresh=True, db=_db, current_user=None, response=None)
                return eid, "ok"
            except _HTTPEx as _he:
                _detail = str(getattr(_he, 'detail', '')).lower()
                if "sem grupo" in _detail:
                    _no_grupo_event_ids.add(eid)
                    logger.info(f"[StartupGap] Evento {eid} sem grupo – ignorado nos próximos ciclos")
                    return eid, "no_grupo"
                return eid, f"error: {_he}"
            except Exception as ex:
                return eid, f"error: {ex}"
            finally:
                if _db:
                    try:
                        _db.close()
                    except Exception:
                        pass

        ok_count = 0
        fail_count = 0
        with _TPE(max_workers=GAP_WORKERS, thread_name_prefix="gap_warmup") as ex:
            futs = {ex.submit(_gap_warm_one, eid): eid for eid in needs_warmup}
            for fut in _as_completed(futs, timeout=GAP_TIMEOUT * len(needs_warmup)):
                eid, result = fut.result()
                if result == "ok":
                    ok_count += 1
                else:
                    fail_count += 1
                    logger.warning(f"[StartupGap] Failed to warm {eid}: {result}")

        logger.info(f"[StartupGap] Targeted warmup done: {ok_count} ok, {fail_count} failed")
        return ok_count, fail_count

    except Exception as e:
        logger.error(f"[StartupGap] Startup gap detection failed: {e}", exc_info=True)
        return 0, -1
    finally:
        if db:
            try:
                db.close()
            except Exception:
                pass


def _startup_resync_projetos():
    from app.core.database import SessionLocal
    from app.models.cadastro_evento import CadastroEvento
    from app.api.routes.cadastros import _sync_dim_projeto
    _ACTIVE_STATUSES = {'Em andamento', 'Em breve', 'Suspenso'}
    try:
        db = SessionLocal()
        cadastros = (
            db.query(CadastroEvento)
            .filter(CadastroEvento.deleted_at.is_(None))
            .filter(CadastroEvento.status.in_(list(_ACTIVE_STATUSES)))
            .all()
        )
        synced = 0
        for c in cadastros:
            try:
                _sync_dim_projeto(db, c)
                db.commit()
                synced += 1
            except Exception as e:
                logger.warning(f"Resync failed for cadastro {c.id} ({c.nome}): {e}")
                try:
                    db.rollback()
                except Exception:
                    pass
        logger.info(f"Startup resync: {synced}/{len(cadastros)} active cadastros synced to dim_projeto (Concluído/Cancelado skipped)")
        db.close()
    except Exception as e:
        logger.error(f"Startup resync failed: {e}")
        try:
            from app.services.health_alert_service import log_and_alert
            log_and_alert("STARTUP_RESYNC_FAILED", "HIGH", "Falha no resync de eventos na inicialização", str(e))
        except Exception:
            pass

def _prewarm_revenue_cache():
    """
    Pré-aquece o _margem_rev_cache para todos os grupos de bundles ativos.
    Roda em background após o startup para garantir que a primeira requisição de
    receita de qualquer evento seja respondida a partir do cache em memória.
    """
    import threading as _threading
    import time as _t

    def _do_prewarm():
        _t.sleep(5)  # aguarda o servidor estar pronto
        try:
            from app.core.database import SessionLocal
            from app.models.kit_config import KitConfig
            from app.models.dimensoes import DimProjeto, SkuMapping
            from app.api.routes.marketing import get_margem_por_kit, _margem_rev_cache, today_brazil
            import app.core.database as _db_mod

            if _db_mod.engine_magento is None:
                logger.info("[RevenuePrewarm] Magento engine não disponível — pulando pré-aquecimento de receita")
                return

            db = SessionLocal()
            try:
                from datetime import date as _date, timedelta as _td
                today = today_brazil()

                # Coleta todos os projetos com data futura ou recente (últimos 30d)
                projetos = db.query(DimProjeto).filter(
                    DimProjeto.data_evento >= today - _td(days=30),
                ).all()

                if not projetos:
                    logger.info("[RevenuePrewarm] Nenhum projeto ativo encontrado — pulando")
                    return

                # O caminho correto: DimProjeto.codigo → SkuMapping.sku (fonte=MAGENTO)
                # → SkuMapping.id_externo (Magento event entity_id) → KitConfig.id_evento
                codigos = [p.codigo.upper().strip() for p in projetos if p.codigo]
                sku_maps = db.query(SkuMapping).filter(
                    SkuMapping.sku.in_(codigos),
                    SkuMapping.fonte == 'MAGENTO',
                    SkuMapping.ativo == True,
                ).all()

                # sku → [magento_event_id, ...]
                magento_ids_by_sku: dict = {}
                for sm in sku_maps:
                    if sm.id_externo:
                        try:
                            magento_ids_by_sku.setdefault(sm.sku.upper(), []).append(int(sm.id_externo))
                        except (ValueError, TypeError):
                            pass

                # Para cada projeto, determina os bundle_ids via KitConfig.id_evento
                seen_cache_keys: set = set()
                proj_bundle_map: list = []  # [(proj_id, bundle_ids)]
                for proj in projetos:
                    sku = (proj.codigo or "").upper().strip()
                    magento_ids = magento_ids_by_sku.get(sku, [])
                    if not magento_ids:
                        continue
                    kcs = db.query(KitConfig).filter(
                        KitConfig.id_evento.in_(magento_ids),
                        KitConfig.bundle_entity_id.isnot(None),
                        KitConfig.tipo_kit.isnot(None),
                    ).all()
                    bundle_ids = list({kc.bundle_entity_id for kc in kcs if kc.bundle_entity_id})
                    if not bundle_ids:
                        continue
                    cache_key = frozenset(bundle_ids)
                    if cache_key in seen_cache_keys:
                        continue  # grupo já representado por outro projeto
                    seen_cache_keys.add(cache_key)
                    proj_bundle_map.append((proj.id, bundle_ids))

                if not proj_bundle_map:
                    logger.info("[RevenuePrewarm] Nenhum bundle mapeado — pulando pré-aquecimento")
                    return

                logger.info(f"[RevenuePrewarm] Iniciando pré-aquecimento de receita para {len(proj_bundle_map)} grupos de bundles")
                ok = 0
                skipped = 0
                failed = 0

                for proj_id, bundle_ids in proj_bundle_map:
                    cache_key = frozenset(bundle_ids)
                    if cache_key in _margem_rev_cache:
                        skipped += 1
                        continue
                    try:
                        # Chama get_margem_por_kit — popula _margem_rev_cache como side effect
                        get_margem_por_kit(db, [proj_id], avisos_out=[], force_refresh=False)
                        ok += 1
                    except Exception as _pe:
                        logger.debug(f"[RevenuePrewarm] Projeto {proj_id} falhou: {_pe}")
                        failed += 1

                logger.info(f"[RevenuePrewarm] Concluído: {ok} ok, {skipped} já em cache, {failed} falhou")
            finally:
                db.close()
        except Exception as e:
            logger.error(f"[RevenuePrewarm] Erro no pré-aquecimento de receita: {e}")

    _threading.Thread(target=_do_prewarm, daemon=True, name="revenue-prewarm").start()


def _sync_id_evento_magento():
    from app.core.database import SessionLocal
    from app.models.cadastro_evento import CadastroEvento
    from app.models.dimensoes import SkuMapping
    try:
        db = SessionLocal()
        cadastros = db.query(CadastroEvento).filter(
            CadastroEvento.sku.isnot(None),
            CadastroEvento.id_evento_magento.is_(None),
        ).all()
        if not cadastros:
            db.close()
            return
        updated = 0
        for cad in cadastros:
            mapping = db.query(SkuMapping).filter(
                SkuMapping.sku == cad.sku.upper().strip(),
                SkuMapping.fonte == 'ATIVO',
                SkuMapping.ativo == True,
            ).first()
            if mapping and mapping.id_externo:
                cad.id_evento_magento = int(mapping.id_externo)
                updated += 1
        if updated:
            db.commit()
            logger.info(f"Synced id_evento_magento for {updated} cadastro_evento records")
        db.close()
    except Exception as e:
        logger.error(f"id_evento_magento sync failed: {e}")


def seed_admin_user():
    from app.core.database import SessionLocal
    from app.models.user import Usuario
    from app.models.perfil_acesso import PerfilAcesso, PerfilPermissao
    from app.core.security import get_password_hash
    try:
        db = SessionLocal()
        user_count = db.query(Usuario).count()
        if user_count > 0:
            db.close()
            return
        logger.info("No users found. Seeding admin user...")
        admin_perfil = db.query(PerfilAcesso).filter(PerfilAcesso.is_admin == True).first()
        if not admin_perfil:
            admin_perfil = PerfilAcesso(
                nome="Administrador",
                descricao="Perfil de administrador com acesso total",
                is_sistema=True,
                is_admin=True,
                ativo=True
            )
            db.add(admin_perfil)
            db.flush()
            modulos = [
                "admin_usuarios", "centro_custo", "categorias_atletas",
                "projetos", "dashboard", "tarefas", "cadastro_eventos",
                "marketing", "sku_mappings", "perfil_acesso", "cotacoes"
            ]
            for modulo in modulos:
                perm = PerfilPermissao(
                    perfil_acesso_id=admin_perfil.id,
                    modulo=modulo,
                    pode_visualizar=True,
                    pode_criar=True,
                    pode_editar=True,
                    pode_deletar=True
                )
                db.add(perm)
            logger.info("Admin profile created with full permissions")
        admin_user = Usuario(
            email="leonardo.micheletti@cscdoesporte.com.br",
            nome="Leonardo Micheletti",
            senha_hash=get_password_hash("Norte@2024"),
            perfil_acesso_id=admin_perfil.id,
            ativo=True
        )
        db.add(admin_user)
        db.commit()
        logger.info(f"Admin user created: leonardo.micheletti@cscdoesporte.com.br")
        db.close()
    except Exception as e:
        logger.error(f"Error seeding admin user: {e}")

def _seed_kit_config():
    from app.core.database import SessionLocal
    from app.models.kit_config import KitConfig
    from app.models.perfil_acesso import PerfilAcesso, PerfilPermissao
    try:
        db = SessionLocal()
        seeds = [
            {"bundle_entity_id": 50999, "kit_nome": "Kit Bota Pra Correr", "multiplicador": 2},
            {"bundle_entity_id": 54863, "kit_nome": "Kit Capitão", "multiplicador": 5},
        ]
        for s in seeds:
            existing = db.query(KitConfig).filter(KitConfig.bundle_entity_id == s["bundle_entity_id"]).first()
            if not existing:
                db.add(KitConfig(**s))

        admin_profiles = db.query(PerfilAcesso).filter(PerfilAcesso.is_admin == True).all()
        for profile in admin_profiles:
            has_perm = db.query(PerfilPermissao).filter(
                PerfilPermissao.perfil_acesso_id == profile.id,
                PerfilPermissao.modulo == "admin_kit_config"
            ).first()
            if not has_perm:
                db.add(PerfilPermissao(
                    perfil_acesso_id=profile.id,
                    modulo="admin_kit_config",
                    pode_visualizar=True,
                    pode_criar=True,
                    pode_editar=True,
                    pode_deletar=True,
                ))

        db.commit()
        db.close()
        logger.info("Kit config seed completed")
    except Exception as e:
        logger.error(f"Kit config seed failed: {e}")


def _run_column_migrations():
    from app.core.database import SessionLocal
    try:
        db = SessionLocal()
        migrations = [
            "ALTER TABLE cadastro_evento ADD COLUMN IF NOT EXISTS atletas_appai_pago INTEGER DEFAULT 0",
            "ALTER TABLE cadastro_evento ADD COLUMN IF NOT EXISTS atletas_appai_tkt_medio NUMERIC(10,2) DEFAULT 0",
            "ALTER TABLE evento_grupos ALTER COLUMN nome TYPE VARCHAR(200)",
            "ALTER TABLE sku_mappings ALTER COLUMN evento_grupo TYPE VARCHAR(200)",
            "ALTER TABLE dim_usuario ADD COLUMN IF NOT EXISTS last_activity TIMESTAMP",
            "ALTER TABLE cadastro_evento ADD COLUMN IF NOT EXISTS dias_encerramento_inscricao INTEGER DEFAULT 2",
            "ALTER TABLE sku_mappings ADD COLUMN IF NOT EXISTS data_evento DATE",
            "ALTER TABLE kit_config ADD COLUMN IF NOT EXISTS is_kit_basico BOOLEAN DEFAULT FALSE NOT NULL",
            "ALTER TABLE cadastro_evento ADD COLUMN IF NOT EXISTS id_evento_magento INTEGER",
            "ALTER TABLE cadastro_evento ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP",
            "ALTER TABLE kit_config ADD COLUMN IF NOT EXISTS tipo_kit VARCHAR(100)",
            "ALTER TABLE kit_config ADD COLUMN IF NOT EXISTS custo_kit DECIMAL(10,2)",
            "ALTER TABLE kit_config ADD COLUMN IF NOT EXISTS ativo_categoria VARCHAR(100)",
            "ALTER TABLE cadastro_kit_produto ADD COLUMN IF NOT EXISTS ativo_categoria VARCHAR(100)",
            "ALTER TABLE kit_config ALTER COLUMN ativo_categoria TYPE VARCHAR(500)",
            "ALTER TABLE vendas_diaria_snapshot ADD COLUMN IF NOT EXISTS ano INTEGER",
            # acoes_comerciais: snapshot fields + cutoff point (task #51)
            "ALTER TABLE acoes_comerciais ADD COLUMN IF NOT EXISTS ponto_corte VARCHAR(10)",
            "ALTER TABLE acoes_comerciais ADD COLUMN IF NOT EXISTS estagio VARCHAR(20)",
            "ALTER TABLE acoes_comerciais ADD COLUMN IF NOT EXISTS snapshot_isc NUMERIC(6,4)",
            "ALTER TABLE acoes_comerciais ADD COLUMN IF NOT EXISTS snapshot_isc_state VARCHAR(10)",
            "ALTER TABLE acoes_comerciais ADD COLUMN IF NOT EXISTS snapshot_d_minus INTEGER",
            "ALTER TABLE acoes_comerciais ADD COLUMN IF NOT EXISTS snapshot_ia730 NUMERIC(6,4)",
            "ALTER TABLE acoes_comerciais ADD COLUMN IF NOT EXISTS snapshot_rolling14d NUMERIC(6,4)",
            "ALTER TABLE acoes_comerciais ADD COLUMN IF NOT EXISTS snapshot_curva_percent NUMERIC(6,4)",
            # widen snapshot ratio columns from NUMERIC(6,4) to FLOAT (values can exceed 99.9999)
            "ALTER TABLE acoes_comerciais ALTER COLUMN snapshot_ia730 TYPE DOUBLE PRECISION USING snapshot_ia730::double precision",
            "ALTER TABLE acoes_comerciais ALTER COLUMN snapshot_rolling14d TYPE DOUBLE PRECISION USING snapshot_rolling14d::double precision",
            "ALTER TABLE acoes_comerciais ALTER COLUMN snapshot_curva_percent TYPE DOUBLE PRECISION USING snapshot_curva_percent::double precision",
            "ALTER TABLE acoes_comerciais ADD COLUMN IF NOT EXISTS snapshot_vendas_acumuladas INTEGER",
            "ALTER TABLE acoes_comerciais ADD COLUMN IF NOT EXISTS snapshot_playbook_letter VARCHAR(5)",
            "ALTER TABLE dim_usuario ADD COLUMN IF NOT EXISTS recebe_alertas_corte BOOLEAN DEFAULT FALSE",
            "ALTER TABLE system_health_events ADD COLUMN IF NOT EXISTS resolved_at TIMESTAMP WITH TIME ZONE",
            "ALTER TABLE system_health_events ADD COLUMN IF NOT EXISTS resolved_by VARCHAR(255)",
            "ALTER TABLE evento_grupos ADD COLUMN IF NOT EXISTS circuito VARCHAR(200)",
            "ALTER TABLE evento_grupos ADD COLUMN IF NOT EXISTS cidade_normalizada VARCHAR(200)",
            "ALTER TABLE evento_grupos ADD COLUMN IF NOT EXISTS curva_override VARCHAR(200)",
            "ALTER TABLE curva_historica_snapshot ADD COLUMN IF NOT EXISTS origem VARCHAR(50)",
            # nori_insights table (idempotent — create_all handles new installs; this covers existing DBs)
            """
            CREATE TABLE IF NOT EXISTS nori_insights (
                id SERIAL PRIMARY KEY,
                evento_id VARCHAR(200),
                evento_nome VARCHAR(300) NOT NULL DEFAULT '',
                tipo VARCHAR(50) NOT NULL,
                titulo VARCHAR(400) NOT NULL,
                conteudo TEXT NOT NULL,
                acao_sugerida TEXT,
                impacto_estimado_reais NUMERIC(12,2),
                impacto_estimado_percentual NUMERIC(6,2),
                dados_contexto JSONB,
                status VARCHAR(20) NOT NULL DEFAULT 'novo',
                gerado_em TIMESTAMP DEFAULT NOW(),
                atualizado_em TIMESTAMP DEFAULT NOW()
            )
            """,
            "CREATE INDEX IF NOT EXISTS ix_nori_insights_status ON nori_insights (status)",
            "CREATE INDEX IF NOT EXISTS ix_nori_insights_evento_id ON nori_insights (evento_id)",
            "CREATE INDEX IF NOT EXISTS ix_nori_insights_gerado_em ON nori_insights (gerado_em DESC)",
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_nori_insights_per_day ON nori_insights (evento_id, tipo, DATE(gerado_em))",
            # merchan tables (task #53)
            """
            CREATE TABLE IF NOT EXISTS cadastro_merchan (
                id SERIAL PRIMARY KEY,
                cadastro_id INTEGER NOT NULL REFERENCES cadastro_evento(id) ON DELETE CASCADE,
                kit VARCHAR(100)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS cadastro_merchan_item (
                id SERIAL PRIMARY KEY,
                merchan_id INTEGER NOT NULL REFERENCES cadastro_merchan(id) ON DELETE CASCADE,
                nome VARCHAR(100) NOT NULL,
                valor_venda NUMERIC(10,2) DEFAULT 0
            )
            """,
        ]
        kit_basico_idx = [
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_kit_basico_per_evento ON kit_config (id_evento) WHERE is_kit_basico = TRUE",
            "CREATE INDEX IF NOT EXISTS ix_snapshot_data_venda ON vendas_diaria_snapshot (data_venda)",
        ]
        migrations.extend(kit_basico_idx)
        for sql in migrations:
            try:
                db.execute(text(sql))
            except Exception as e:
                logger.warning(f"Migration skipped: {e}")
        db.commit()

        cache_dedup_migrations = [
            """DELETE FROM cache_entries a USING cache_entries b
               WHERE a.id < b.id
               AND a.cache_name = b.cache_name
               AND a.cache_key = b.cache_key""",
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_cache_name_key ON cache_entries (cache_name, cache_key)",
        ]
        for sql in cache_dedup_migrations:
            try:
                db.execute(text(sql))
            except Exception as e:
                logger.warning(f"Cache migration skipped: {e}")
        db.commit()
        db.close()
        logger.info("Column migrations completed")
    except Exception as e:
        logger.error(f"Column migrations failed: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    register_full_warmup_fn(_full_cache_warmup)
    cache_scheduler.register_full_refresh(_full_cache_warmup)
    cache_scheduler.register(_scheduled_isc_refresh)
    cache_scheduler.register(_scheduled_sincronizar_hoje)
    # NOTE: _scheduled_nori_insights is also registered with cache_scheduler for
    # periodic execution, but since the daily 05:00 BRT path uses _full_refresh_callback
    # and skips _refresh_callbacks, we add a dedicated daily timer at 05:30 BRT.
    # This ensures insights are generated once per day regardless of the main refresh path.

    import threading

    def _schedule_daily_nori_insights():
        """Schedule insights generation at 05:30 BRT daily (after daily cache refresh)."""
        from zoneinfo import ZoneInfo as _ZI
        from datetime import datetime as _dt, timedelta as _td
        _brt = _ZI('America/Sao_Paulo')
        _now = _dt.now(_brt)
        _target = _now.replace(hour=5, minute=30, second=0, microsecond=0)
        if _now >= _target:
            _target += _td(days=1)
        _delay = (_target - _now).total_seconds()
        logger.info(f"[NoriInsights] Daily timer: next run at {_target.isoformat()} BRT (in {_delay/3600:.1f}h)")

        def _run_and_reschedule():
            _scheduled_nori_insights()
            _schedule_daily_nori_insights()

        _timer = threading.Timer(_delay, _run_and_reschedule)
        _timer.daemon = True
        _timer.name = "nori-insights-daily-timer"
        _timer.start()
        return _timer

    def _all_background_init():
        """All startup work runs in background so the server starts immediately."""
        # Phase 0: schema setup (idempotent, safe to run after yield)
        try:
            from app.models import nori_insights as _ni_models  # noqa: F401 — ensure table is registered
            from app.models import system_health as _sh_models  # noqa: F401 — ensure health tables are registered
            if engine:
                Base.metadata.create_all(bind=engine)
            _run_column_migrations()
            seed_admin_user()
            _seed_kit_config()
        except Exception as e:
            logger.error(f"Schema/seed setup failed: {e}")

        # Phase 1: connections & sync
        try:
            _startup_resync_projetos()
        except Exception as e:
            logger.error(f"Startup resync projetos failed: {e}")

        try:
            from app.core.database import SessionLocal as _SL
            from app.api.routes.cadastros import warm_list_cache as _warm_cadastros
            _db_warm = _SL()
            try:
                _warm_cadastros(_db_warm)
            finally:
                _db_warm.close()
        except Exception as e:
            logger.error(f"Cadastros list cache warmup failed: {e}")

        try:
            _sync_id_evento_magento()
        except Exception as e:
            logger.error(f"Startup id_evento_magento sync failed: {e}")

        try:
            init_mysql_connections()
        except Exception as e:
            logger.error(f"MySQL connections init failed: {e}")

        try:
            init_ssh_tunnel()
        except Exception as e:
            logger.error(f"SSH tunnel init failed: {e}")

        # Phase 2: load persistent cache from DB
        try:
            logger.info("Loading persistent cache from PostgreSQL...")
            warm_all_caches_from_db()
            logger.info("Persistent cache loaded from PostgreSQL")
        except Exception as e:
            logger.error(f"Persistent cache load failed: {e}")

        # Phase 3: Tier1 gap detection + targeted warmup
        _gap_warmup_ok = 0
        _gap_warmup_fail = 0
        try:
            logger.info("Running Tier1 gap detection...")
            _gap_result = _startup_tier1_gap_warmup()
            if isinstance(_gap_result, tuple):
                _gap_warmup_ok, _gap_warmup_fail = _gap_result
            logger.info("Tier1 gap detection complete")
        except Exception as e:
            logger.error(f"Startup gap detection failed: {e}")

        # After targeted warmup, re-check cache timestamps DIRECTLY rather than
        # relying on the pre-warmup gap result (which reflects state *before* warmup).
        # This avoids spuriously triggering a full warmup when targeted warmup succeeded.
        try:
            import time as _ts_check
            from app.core.cache import get_known_tier1_ids as _get_t1_ids
            _known_t1 = _get_t1_ids()
            _fresh_ts = event_detail_cache.get_all_timestamps()
            _now_ts = _ts_check.time()
            _ano_check = __import__('datetime').datetime.now().year
            _still_missing = [eid for eid in _known_t1
                              if f"{_ano_check}_{eid}_detail" not in _fresh_ts]
            _still_stale = [eid for eid in _known_t1
                            if f"{_ano_check}_{eid}_detail" in _fresh_ts
                            and (_now_ts - _fresh_ts.get(f"{_ano_check}_{eid}_detail", 0)) > 25 * 3600]
            _gap_count_post = len(_still_missing) + len(_still_stale)
            if _gap_count_post == 0:
                logger.info("[Startup] Direct cache check: all Tier1 events have fresh cache — clearing gap result")
                set_gap_detection_result({"missing_tier1_events": [], "stale_tier1_events": []})
            else:
                logger.info(f"[Startup] Direct cache check: {_gap_count_post} Tier1 events still need warmup ({len(_still_missing)} missing, {len(_still_stale)} stale)")
                set_gap_detection_result({"missing_tier1_events": _still_missing, "stale_tier1_events": _still_stale})
        except Exception as _cache_check_err:
            logger.warning(f"[Startup] Direct cache check failed: {_cache_check_err}")
            # Fallback: use original gap result
            _gap_result_post = get_gap_detection_result()
            _gap_count_post = len(_gap_result_post.get("missing_tier1_events", [])) + len(_gap_result_post.get("stale_tier1_events", []))

        # Phase 4: scheduler, then snapshot + warmup in parallel
        cache_scheduler.start(interval=1800)
        logger.info("Cache auto-refresh scheduler started (30 min interval + daily 05:00 BRT)")

        # Check if snapshots are fresh enough to skip consolidation at startup.
        # If snapshots were updated within the last 2 hours (e.g. after "Atualizar Tudo" or
        # the previous 05:00/17:00 warmup), skip the expensive snapshot rebuild entirely.
        SNAPSHOT_FRESH_SECONDS = 2 * 3600
        _snapshot_is_fresh = False
        try:
            from app.core.database import SessionLocal as _SnapSL
            from app.models.vendas_snapshot import VendasDiariaSnapshot as _VDS_check
            from sqlalchemy import func as _sfunc
            from datetime import datetime as _dt_startup
            _snap_db = _SnapSL()
            try:
                _last_snap_ts = _snap_db.query(_sfunc.max(_VDS_check.updated_at)).scalar()
                if _last_snap_ts:
                    _snap_age = (_dt_startup.utcnow() - _last_snap_ts).total_seconds()
                    if _snap_age < SNAPSHOT_FRESH_SECONDS:
                        _snapshot_is_fresh = True
                        logger.info(f"[Startup] Snapshots are fresh (updated {_snap_age/60:.1f}min ago) — skipping startup consolidation")
                    else:
                        logger.info(f"[Startup] Snapshots are stale ({_snap_age/3600:.1f}h ago) — will run consolidation")
            finally:
                _snap_db.close()
        except Exception as _snap_check_err:
            logger.warning(f"[Startup] Could not check snapshot freshness: {_snap_check_err}")

        def _run_snapshot_consolidation():
            try:
                from app.core.database import SessionLocal
                from app.services.snapshot_service import snapshot_diario_batch, consolidar_curvas_historicas_batch, sincronizar_hoje_batch, sincronizar_margem_bundle_rev_batch
                logger.info("Starting snapshot consolidation (parallel)...")
                db = SessionLocal()
                try:
                    snapshot_diario_batch(db)
                    consolidar_curvas_historicas_batch(db)
                    sincronizar_hoje_batch(db)
                    try:
                        result_margem = sincronizar_margem_bundle_rev_batch(db)
                        logger.info(f"[Startup] sincronizar_margem_bundle_rev_batch: {result_margem}")
                    except Exception as _e_margem:
                        logger.error(f"[Startup] sincronizar_margem_bundle_rev_batch falhou (não bloqueante): {_e_margem}")
                    logger.info("Startup snapshot consolidation completed")
                finally:
                    db.close()
            except Exception as e:
                logger.error(f"Startup snapshot consolidation failed: {e}")

        snapshot_thread = threading.Thread(target=_run_snapshot_consolidation, daemon=True, name="startup-snapshot")
        if not _snapshot_is_fresh:
            snapshot_thread.start()
        else:
            # Snapshots are fresh — mark thread as not started (join will return immediately)
            snapshot_thread = threading.Thread(target=lambda: None, daemon=True)
            snapshot_thread.start()

        # Se a tabela margem_bundle_rev_snapshot estiver vazia (deploy inicial ou primeiro boot
        # após criação da tabela), dispara o sync em background independentemente da freshness
        # dos outros snapshots.
        def _maybe_sync_margem_rev():
            try:
                from app.core.database import SessionLocal as _SL2
                from app.models.vendas_snapshot import MargemBundleRevSnapshot as _MBR2
                from app.services.snapshot_service import sincronizar_margem_bundle_rev_batch as _smrb
                _db2 = _SL2()
                try:
                    _empty = _db2.query(_MBR2).count() == 0
                    if _empty:
                        logger.info("[Startup] margem_bundle_rev_snapshot vazio — disparando sync inicial em background")
                        result = _smrb(_db2)
                        logger.info(f"[Startup] margem_bundle_rev_snapshot sync inicial: {result}")
                    else:
                        logger.info("[Startup] margem_bundle_rev_snapshot já populado — sync inicial ignorado")
                finally:
                    _db2.close()
            except Exception as _e_m:
                logger.error(f"[Startup] Erro no sync inicial de margem_bundle_rev_snapshot: {_e_m}")

        _margem_thread = threading.Thread(target=_maybe_sync_margem_rev, daemon=True, name="startup-margem-rev-sync")
        _margem_thread.start()

        # Decide whether to run a full warmup on startup.
        # If targeted warmup resolved all gaps (gap count == 0 now), skip the full warmup.
        # If there are still gaps AND snapshots are fresh, run warmup immediately (no wait).
        # If gaps remain AND snapshots are stale, wait for snapshot before warmup to avoid
        # a race where Phase 1d reads snapshot data before it's rebuilt.
        _gap_result = get_gap_detection_result()
        _gap_count = len(_gap_result.get("missing_tier1_events", [])) + len(_gap_result.get("stale_tier1_events", []))

        if _gap_count == 0:
            logger.info("[Startup] All Tier1 events have fresh cache — skipping full warmup. Snapshot running in background.")
            # Even when skipping full warmup, always rebuild ISC data in background so
            # the in-memory ISC is fresh (the DB-loaded copy may be from a prior run
            # where Magento timed out and only Ativo data was stored).
            def _bg_isc_refresh():
                try:
                    from app.core.database import SessionLocal as _SL
                    from app.api.routes.marketing import fetch_isc_pricing_data as _fetch_isc
                    from app.core.cache import event_detail_cache as _edc, isc_cache as _isc_c
                    _db = _SL()
                    try:
                        # Snapshot total for comparison — sum qtd_site of all live ISC entries
                        # (excludes _consolidated_totals which is for completed events only)
                        def _isc_total_qtd(isc_dict):
                            if not isinstance(isc_dict, dict):
                                return 0
                            return sum(
                                v.get('qtd_site', 0)
                                for k, v in isc_dict.items()
                                if k != '_consolidated_totals' and isinstance(v, dict)
                            )
                        _before_total = _isc_total_qtd(_isc_c.get("2026_isc") or {})
                        _fetch_isc(db=_db, force_refresh=True)
                        _after_total = _isc_total_qtd(_isc_c.get("2026_isc") or {})
                        # If ISC totals improved (Magento succeeded), clear live event_detail
                        # cache so they recompute with the fresh data. Completed/historical events
                        # are marked permanent and will NOT be cleared.
                        if _after_total > _before_total:
                            _edc.invalidate()  # clears non-permanent (live) entries only
                            logger.info(f"[Startup] ISC improved ({_before_total} → {_after_total}) — cleared live event_detail cache for recompute")
                        logger.info("[Startup] Background ISC refresh completed")
                    finally:
                        _db.close()
                except Exception as _e:
                    logger.warning(f"[Startup] Background ISC refresh failed: {_e}")
            threading.Thread(target=_bg_isc_refresh, daemon=True, name="startup-isc-refresh").start()
        elif _snapshot_is_fresh:
            logger.info(f"[Startup] {_gap_count} Tier1 events need warmup — snapshots fresh, running warmup immediately (no snapshot wait)...")
            try:
                _full_cache_warmup()
            except Exception as e:
                logger.error(f"Full cache warmup failed: {e}")
        else:
            logger.info(f"[Startup] {_gap_count} Tier1 events need warmup — waiting for snapshot to complete before pre-warming...")
            snapshot_thread.join(timeout=600)  # wait up to 10 min for snapshot
            logger.info("Starting full cache warmup (post-snapshot)...")
            try:
                _full_cache_warmup()
            except Exception as e:
                logger.error(f"Full cache warmup failed: {e}")

        logger.info("=== All background startup tasks completed ===")

        # Pré-aquece cache de receita Magento por bundle em background (não bloqueia startup).
        # Garante que a primeira requisição de margem para qualquer evento ativo
        # responda a partir do cache em memória, não espere 20-55s na query de receita.
        _prewarm_revenue_cache()

        # Trigger proactive insights generation on startup (non-blocking, best-effort)
        try:
            from app.core.database import SessionLocal as _InsightSL
            from app.services.nori_insights_service import run_proactive_insights_job
            import asyncio as _aio
            _ins_db = _InsightSL()
            try:
                _ins_result = _aio.run(run_proactive_insights_job(_ins_db))
                logger.info(f"[Startup] Nori insights job: {_ins_result.get('insights_saved', 0)} saved, {_ins_result.get('events_analyzed', 0)} events analyzed")
            finally:
                _ins_db.close()
        except Exception as _ins_err:
            logger.warning(f"[Startup] Nori insights startup run failed (non-fatal): {_ins_err}")

        # Start the dedicated 05:30 BRT daily timer for insights generation
        _schedule_daily_nori_insights()

    # Warmup do cache de cadastros no main thread (antes de aceitar requests)
    try:
        from app.api.routes.cadastros import warm_list_cache as _warm_cadastros
        from app.core.database import SessionLocal as _SL
        _db_warm = _SL()
        try:
            _warm_cadastros(_db_warm)
        finally:
            _db_warm.close()
    except Exception as e:
        import traceback
        logger.error(f"[Startup] Cadastros cache warmup FALHOU: {e}\n{traceback.format_exc()}")

    init_thread = threading.Thread(target=_all_background_init, daemon=True, name="startup-bg-init")
    init_thread.start()

    logger.info("=== Server ready to accept requests (background init running) ===")

    yield
    cache_scheduler.stop()
    stop_ssh_watchdog()
    close_ssh_tunnel()

app = FastAPI(title="DW Financeiro - Eventos", version="1.0.0", lifespan=lifespan)

from app.core.config import settings as app_settings

cors_origins = [origin.strip() for origin in app_settings.CORS_ORIGINS.split(",") if origin.strip()]
cors_origins.append("https://*.replit.app")
cors_origins.append("https://*.replit.dev")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Data-Stale"],
)

app.include_router(auth.router, prefix="/api")
app.include_router(users.router, prefix="/api")
app.include_router(centros_custo.router, prefix="/api")
app.include_router(projetos.router, prefix="/api")
app.include_router(categorias_atletas.router, prefix="/api")
app.include_router(dashboard.router, prefix="/api")
app.include_router(nori.router, prefix="/api")
app.include_router(tarefas.router, prefix="/api")
app.include_router(cadastros.router, prefix="/api")
app.include_router(atletas_externos.router, prefix="/api")
app.include_router(magento.router, prefix="/api/magento", tags=["Magento"])
app.include_router(inscricoes_consolidado.router, prefix="/api/inscricoes", tags=["Inscricoes Consolidadas"])
app.include_router(marketing.router, prefix="/api", tags=["Marketing ISC"])
app.include_router(sku_mappings.router, tags=["SKU Mappings"])
app.include_router(sku_mappings.grupo_router, tags=["Evento Grupos"])
app.include_router(perfil_acesso.router, prefix="/api", tags=["Perfis de Acesso"])
app.include_router(distancias.router, prefix="/api", tags=["Distâncias"])
app.include_router(cotacoes.router, prefix="/api", tags=["Cotações & Importação"])
app.include_router(admin.router, tags=["Admin"])
app.include_router(kit_config.router, tags=["Kit Config"])

@app.get("/api/health")
async def health_check():
    return {"status": "healthy"}

from app.core.security import get_current_user

@app.get("/api/mysql/ativo/test")
async def test_mysql_ativo(current_user=Depends(get_current_user)):
    from app.core.database import engine_ativo
    if engine_ativo is None:
        return {"status": "error", "message": "Conexão MySQL Ativo não configurada"}
    try:
        with engine_ativo.connect() as conn:
            result = conn.execute(text("SELECT 1 as test"))
            row = result.fetchone()
            return {"status": "success", "message": "Connected to MySQL Ativo", "test_result": row[0]}
    except Exception as e:
        logger.error(f"Erro ao testar MySQL Ativo: {str(e)}")
        return {"status": "error", "message": "Erro interno ao conectar no banco de dados"}

@app.get("/api/mysql/ativo/tables")
async def list_mysql_ativo_tables(current_user=Depends(get_current_user)):
    from app.core.database import engine_ativo
    if engine_ativo is None:
        return {"status": "error", "message": "Conexão MySQL Ativo não configurada"}
    try:
        with engine_ativo.connect() as conn:
            result = conn.execute(text("SHOW TABLES"))
            tables = [row[0] for row in result.fetchall()]
            return {"status": "success", "tables": tables, "count": len(tables)}
    except Exception as e:
        logger.error(f"Erro ao listar tabelas MySQL Ativo: {str(e)}")
        return {"status": "error", "message": "Erro interno ao listar tabelas"}

@app.get("/api/ssh/test")
async def test_ssh_connection(current_user=Depends(get_current_user)):
    from app.core.database import engine_ssh
    if engine_ssh is None:
        return {"status": "error", "message": "Conexão SSH não configurada"}
    try:
        with engine_ssh.connect() as conn:
            result = conn.execute(text("SELECT 1 as test"))
            row = result.fetchone()
            return {"status": "success", "message": "Connected to database via SSH tunnel", "test_result": row[0]}
    except Exception as e:
        logger.error(f"Erro ao testar conexão SSH: {str(e)}")
        return {"status": "error", "message": "Erro interno ao conectar via SSH"}

@app.get("/api/ssh/tables")
async def list_ssh_tables(current_user=Depends(get_current_user)):
    from app.core.database import engine_ssh
    if engine_ssh is None:
        return {"status": "error", "message": "Conexão SSH não configurada"}
    try:
        with engine_ssh.connect() as conn:
            result = conn.execute(text("SHOW TABLES"))
            tables = [row[0] for row in result.fetchall()]
            return {"status": "success", "tables": tables, "count": len(tables)}
    except Exception as e:
        logger.error(f"Erro ao listar tabelas SSH: {str(e)}")
        return {"status": "error", "message": "Erro interno ao listar tabelas"}

frontend_dist = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend", "dist")
if os.path.isdir(frontend_dist):
    assets_dir = os.path.join(frontend_dist, "assets")
    if os.path.isdir(assets_dir):
        app.mount("/assets", StaticFiles(directory=assets_dir), name="static-assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        if full_path.startswith("api/"):
            return {"detail": "Not Found"}
        file_path = os.path.join(frontend_dist, full_path)
        if full_path and os.path.isfile(file_path):
            return FileResponse(file_path)
        index_path = os.path.join(frontend_dist, "index.html")
        if os.path.isfile(index_path):
            return FileResponse(index_path)
        return {"detail": "Not Found"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
