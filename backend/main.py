from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy import text
from contextlib import asynccontextmanager
import os
import time
from app.core.database import engine, Base, init_mysql_connections, engine_ativo, init_ssh_tunnel, close_ssh_tunnel, stop_ssh_watchdog, engine_ssh
from app.api.routes import auth, users, centros_custo, projetos, categorias_atletas, dashboard, nori, tarefas, cadastros, atletas_externos, magento, inscricoes_consolidado, marketing, sku_mappings, perfil_acesso, distancias, cotacoes, admin, kit_config, profile, projecao, detalhe_eventos, detalhe_alias
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

# Flag global: quando False, todas as rotinas automaticas que consomem Magento
# (warmup de startup, scheduler 45min, loop sync-hoje 2h, refresh_active_event_details)
# ficam desativadas. Snapshots so atualizam quando admin clica em "Reconsolidar".
# Default: false (pedido do usuario - evitar carga automatica no Magento/SSH).
ENABLE_BACKGROUND_MAGENTO_SYNC = os.getenv("ENABLE_BACKGROUND_MAGENTO_SYNC", "false").lower() in ("true", "1", "yes")
if not ENABLE_BACKGROUND_MAGENTO_SYNC:
    logger.warning("[Config] ENABLE_BACKGROUND_MAGENTO_SYNC=false - warmup de startup, scheduler 45min e loop sync-hoje DESATIVADOS. Use 'Reconsolidar' (admin) para atualizar snapshots.")

# Flag fina (Maio/2026) — desliga APENAS o Tier1 startup warmup, mantendo
# scheduler/consolidação/hoje-loop ativos. Motivo: análise de PROD mostrou
# que esse warmup roda ~184 queries Magento por deploy (46 eventos × 4 queries
# pesadas de 11-13s cada, em 1 worker sequencial = ~50min de carga contínua),
# porque a maioria dos snapshots persistidos chegam como "bootstrap" sem
# dailySales e são descartados pelo guard de version_mismatch. O custo não
# compensa: o primeiro usuário a abrir cada evento já dispara o recompute
# protegido por singleflight + TTL no caminho normal. Default OFF.
ENABLE_TIER1_STARTUP_WARMUP = os.getenv("ENABLE_TIER1_STARTUP_WARMUP", "false").lower() in ("true", "1", "yes")
if ENABLE_BACKGROUND_MAGENTO_SYNC and not ENABLE_TIER1_STARTUP_WARMUP:
    logger.info("[Config] ENABLE_TIER1_STARTUP_WARMUP=false — Tier1 warmup pós-deploy DESATIVADO (corta ~184 queries Magento/deploy). Scheduler e hoje-sync seguem ativos. Primeiros acessos por evento recompilam lazy via singleflight.")

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


def _run_sincronizar_hoje_com_warmup():
    """
    Executa sincronizar_hoje_batch + pre-warm do cache de detalhes.
    Reutilizado pelo scheduler legado e pelo loop dedicado abaixo.
    """
    from app.core.database import SessionLocal
    from app.services.snapshot_service import sincronizar_hoje_batch
    import time as _time
    import threading as _sh_threading
    db = None
    try:
        db = SessionLocal()
        count = sincronizar_hoje_batch(db)
        logger.info(f"[SyncHoje] sincronizar_hoje_batch concluído: {count} grupos sincronizados")
        # Só marca "fresh" se sincronizou pelo menos 1 grupo. Caso contrário
        # (Magento degradado retornando 0 sem exception, ou todos os grupos
        # pulados por freeze/erro), deixa o last_sync_hoje antigo para que o
        # HojeSyncLoop (12h) re-tente no próximo tick em vez de suprimir
        # retry por 12h achando que tá fresco.
        if count > 0:
            set_last_sync_hoje(_time.time())
        else:
            logger.warning(
                "[SyncHoje] count=0 — NÃO atualizando last_sync_hoje "
                "(loop irá re-tentar no próximo tick)"
            )
        def _refresh_details_bg():
            try:
                from app.services.event_detail_snapshot_service import refresh_active_event_details
                refresh_active_event_details()
            except Exception as _rd_e:
                logger.warning(f"[SyncHoje] refresh_active_event_details falhou: {_rd_e}")
        _sh_threading.Thread(target=_refresh_details_bg, daemon=True).start()
    except Exception as e:
        logger.error(f"[SyncHoje] sincronizar_hoje_batch falhou: {e}")
        try:
            from app.services.health_alert_service import log_and_alert
            log_and_alert("SYNC_BATCH_FAILED", "HIGH", "Falha na sincronização de inscritos de hoje", str(e))
        except Exception:
            pass
    finally:
        if db:
            db.close()


def _scheduled_sincronizar_hoje():
    _run_sincronizar_hoje_com_warmup()


# ────────────────────────────────────────────────────────────────
# Loop dedicado: sincroniza inscritos de hoje a cada N horas,
# apenas se não houver sync recente (automático ou manual).
#
# Dorme HOJE_SYNC_INTERVAL_HOURS horas (padrão 2 h) entre cada
# verificação. Ao acordar, só executa se o último sync — job ou
# clique do usuário em "Atualizar Hoje" — foi há mais de N horas.
# Caso contrário, volta a dormir o intervalo completo.
# ────────────────────────────────────────────────────────────────
def _start_hoje_sync_loop():
    """Loop que sincroniza inscritos de hoje a cada N horas (se não houve sync recente)."""
    import os as _os
    import time as _time
    import threading as _thr
    from app.core.cache import try_acquire_sync_hoje, release_sync_hoje, get_last_sync_hoje

    # Default 12h: o loop vira REDE DE SEGURANÇA. Em dia normal, o sync de
    # Magento já é feito pelos jobs fixos do scheduler — 05h BRT (daily
    # refresh) e 17h BRT (evening refresh), ambos em cache.py. O loop só
    # dispara se algum desses dois falhou e o último sync ficou > 12h atrás.
    # Antes era 2h, o que disparava ~10 syncs extras/dia e mantinha o tunnel
    # SSH sob carga constante, dando a sensação de "sempre atualizando".
    interval_hours = max(1, int(_os.getenv("HOJE_SYNC_INTERVAL_HOURS", "12")))
    interval_sec   = interval_hours * 3600

    def _loop():
        # Aguarda o startup terminar antes do primeiro tick.
        _time.sleep(30)
        logger.info(f"[HojeSyncLoop] Loop iniciado — intervalo: {interval_hours}h (env: HOJE_SYNC_INTERVAL_HOURS)")
        while True:
            _time.sleep(interval_sec)

            # Pula se houve sync recente (job automático OU usuário) dentro do intervalo.
            _last = get_last_sync_hoje()
            if _last is not None:
                _elapsed = _time.time() - _last
                if _elapsed < interval_sec:
                    logger.info(
                        f"[HojeSyncLoop] Sync recente há {int(_elapsed/60)} min — pulando (próximo em ~{int((interval_sec-_elapsed)/60)} min)"
                    )
                    continue

            # Lock global: evita concorrência com outro job em andamento.
            if not try_acquire_sync_hoje("loop-automático"):
                logger.debug("[HojeSyncLoop] Sync já em execução — pulando tick")
                continue

            try:
                logger.info("[HojeSyncLoop] Iniciando sync de inscritos de hoje...")
                _run_sincronizar_hoje_com_warmup()
            except Exception as _loop_e:
                logger.error(f"[HojeSyncLoop] Erro inesperado: {_loop_e}")
            finally:
                release_sync_hoje()

    t = _thr.Thread(target=_loop, daemon=True, name="hoje-sync-loop")
    t.start()
    logger.info(f"[HojeSyncLoop] Thread daemon iniciada (intervalo={interval_hours}h)")


def _scheduled_margem_rev_safety_check():
    """Rede de segurança: a cada tick do scheduler, verifica a idade E a cobertura
    do snapshot margem_bundle_rev_snapshot. Dispara o sync se:
      - snapshot passou de 25h (critério do consumidor em routes/marketing.py), OU
      - cobertura de bundles < 85% (batch foi interrompido a meio).

    Garantia: mesmo se o startup hook não tiver disparado e o job das 4h falhar,
    o snapshot é refrescado dentro de no máximo o intervalo do scheduler (45min).

    HORÁRIO COMERCIAL (Maio/2026): durante 08h-18h BRT, eleva o threshold de
    idade de 25h para 36h — evita disparar sync Magento pesado competindo com
    cliques de usuário. Os jobs fixos (02h consolidação, 05h refresh, 17h
    refresh) cobrem a janela normal; se o snapshot passou de 36h é emergência
    real (dois ciclos noturnos consecutivos falharam) e aí sim vale interromper.
    """
    from app.core.database import SessionLocal
    from app.models.vendas_snapshot import MargemBundleRevSnapshot
    from app.models.kit_config import KitConfig as _KC_sc
    from app.services.snapshot_service import sincronizar_margem_bundle_rev_batch
    from sqlalchemy import func as _sfunc
    from datetime import datetime as _dt, timezone as _tz
    try:
        from zoneinfo import ZoneInfo as _ZI_sc
        _now_brt_h = _dt.now(_ZI_sc("America/Sao_Paulo")).hour
        _in_business_hours = 8 <= _now_brt_h < 18
    except Exception:
        _in_business_hours = False
    db = None
    try:
        db = SessionLocal()
        # Em horário comercial, só dispara se MUITO desatualizado (>36h).
        # Fora do horário comercial, mantém o critério antigo (>25h).
        _MAX_AGE_H = 36 if _in_business_hours else 25
        _newest_ts = db.query(_sfunc.max(MargemBundleRevSnapshot.calculado_em)).scalar()
        _needs_sync = False
        _motivo = ""
        if _newest_ts is None:
            _needs_sync = True
            _motivo = "tabela vazia"
        else:
            if _newest_ts.tzinfo is None:
                _newest_ts = _newest_ts.replace(tzinfo=_tz.utc)
            _age_h = (_dt.now(_tz.utc) - _newest_ts).total_seconds() / 3600
            if _age_h > _MAX_AGE_H:
                _needs_sync = True
                _motivo = f"desatualizado ({_age_h:.1f}h > {_MAX_AGE_H}h)"
            else:
                # Além da idade, verifica cobertura de bundles: se o batch anterior
                # foi interrompido, MAX(calculado_em) parece "fresco" mas muitos
                # bundles não têm entrada. Threshold: < 85% dos bundles do kit_config.
                try:
                    _total_snap = db.query(_sfunc.count(MargemBundleRevSnapshot.bundle_entity_id)).scalar() or 0
                    _expected = db.query(
                        _sfunc.count(_sfunc.distinct(_KC_sc.bundle_entity_id))
                    ).filter(_KC_sc.tipo_kit.isnot(None)).scalar() or 0
                    _coverage = _total_snap / _expected if _expected > 0 else 1.0
                    if _coverage < 0.85:
                        # COOLDOWN ANTI-LOOP (Maio/2026): mesmo motivo do startup
                        # (ver _maybe_sync_margem_rev). Bundles ausentes podem ser
                        # estruturais (sem orders nos últimos 2 anos no Magento)
                        # ou pulados por freeze. Persist-zero cura o caso comum,
                        # mas se a cobertura permanecer baixa por outro motivo
                        # (ex.: freeze removendo muitos bundles ativos), o scheduler
                        # não deve disparar a cada tick (45min) — limita a 1x/6h.
                        _SAFETY_COOLDOWN_H = 6
                        if _age_h < _SAFETY_COOLDOWN_H:
                            logger.debug(
                                f"[SafetyCheck] cobertura baixa ({_total_snap}/{_expected} = "
                                f"{_coverage:.0%}) MAS último sync há {_age_h:.1f}h "
                                f"(< {_SAFETY_COOLDOWN_H}h cooldown) — sync de emergência ignorado (anti-loop)"
                            )
                        else:
                            _needs_sync = True
                            _motivo = f"cobertura baixa ({_total_snap}/{_expected} = {_coverage:.0%})"
                    else:
                        logger.debug(
                            f"[SafetyCheck] margem_bundle_rev_snapshot OK "
                            f"({_age_h:.1f}h, {_total_snap}/{_expected} bundles = {_coverage:.0%})"
                        )
                except Exception as _cov_err:
                    logger.warning(f"[SafetyCheck] Erro ao checar cobertura: {_cov_err}")
                    logger.debug(f"[SafetyCheck] margem_bundle_rev_snapshot fresco ({_age_h:.1f}h) — nada a fazer")
        if _needs_sync:
            logger.warning(f"[SafetyCheck] margem_bundle_rev_snapshot {_motivo} — disparando sync de emergência")
            try:
                result = sincronizar_margem_bundle_rev_batch(db)
                logger.info(f"[SafetyCheck] sync de emergência concluído: {result}")
            except Exception as _e_sync:
                logger.error(f"[SafetyCheck] sync de emergência falhou: {_e_sync}")
                try:
                    from app.services.health_alert_service import log_and_alert
                    log_and_alert(
                        "MARGEM_SNAPSHOT_STALE",
                        "HIGH",
                        "Snapshot de margem está desatualizado e o sync automático falhou",
                        f"motivo={_motivo}; erro={_e_sync}",
                    )
                except Exception:
                    pass
    except Exception as e:
        logger.error(f"[SafetyCheck] Erro ao verificar idade do margem snapshot: {e}")
    finally:
        if db:
            db.close()
        # Marca o tick mesmo em caso de erro — o próximo ainda virá no intervalo.
        try:
            from app.core.sync_state import mark_safety_tick as _mst
            _mst()
        except Exception:
            pass


def _scheduled_cleanup_sessions():
    """Remove sessões expiradas da tabela user_sessions (roda diariamente)."""
    from app.core.database import SessionLocal
    from app.models.user_session import UserSession
    from datetime import datetime
    db = None
    try:
        db = SessionLocal()
        deleted = db.query(UserSession).filter(UserSession.expires_at < datetime.utcnow()).delete()
        db.commit()
        if deleted:
            logger.info(f"[SessionCleanup] {deleted} sessões expiradas removidas.")
    except Exception as e:
        logger.error(f"[SessionCleanup] Erro na limpeza de sessões: {e}")
    finally:
        if db:
            db.close()


def _scheduled_ms_directory_sync():
    """Reconcilia a tabela de usuários com o diretório Microsoft Entra ID.

    Roda independente de ENABLE_BACKGROUND_MAGENTO_SYNC (não toca Magento/SSH).
    Só executa se o SSO/credenciais estiverem configurados; caso contrário sai
    silenciosamente.
    """
    from app.core.database import SessionLocal
    from app.services.ms_auth_service import sso_configured, MSAuthError
    from app.services.ms_directory_sync import sincronizar_diretorio_microsoft
    if not sso_configured():
        logger.info("[MSDirSync] Credenciais Microsoft ausentes — sync de diretório ignorado.")
        return
    db = None
    try:
        db = SessionLocal()
        resumo = sincronizar_diretorio_microsoft(db)
        logger.info(f"[MSDirSync] Sync de diretório concluído: {resumo}")
    except MSAuthError as e:
        logger.error(f"[MSDirSync] Sync de diretório falhou (Graph): {e}")
        try:
            from app.services.health_alert_service import log_and_alert
            log_and_alert("MS_DIR_SYNC_FAILED", "HIGH", "Falha no sync do diretório Microsoft", str(e))
        except Exception:
            pass
    except Exception as e:
        logger.error(f"[MSDirSync] Sync de diretório falhou: {e}")
    finally:
        if db:
            db.close()


def _scheduled_nori_insights():
    # Gateado por ENABLE_BACKGROUND_MAGENTO_SYNC (consistente com startup):
    # em dev (false) o timer 05h30 BRT não dispara — evita ISC force_refresh
    # → kit_cost_batch Magento em ambiente sem necessidade de atualização.
    if not ENABLE_BACKGROUND_MAGENTO_SYNC:
        logger.info("[NoriInsights] Scheduled run SKIPPED (ENABLE_BACKGROUND_MAGENTO_SYNC=false)")
        return
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

            # --- Phase 1b-extra: prewarm medias_vendas + curva_comparativa for ALL active events ---
            # Previously this was Tier 1 only. Extended to all active events so that opening
            # the detail of any active event responds in <1s (no on-demand computation).
            from app.api.routes.marketing import get_curva_comparativa_evento as _get_curva_comp
            _aux_target_ids = active_evento_ids
            if _aux_target_ids:
                _tier1_aux_executor = _TPE(max_workers=min(3, len(_aux_target_ids)), thread_name_prefix="warmup_aux")

                def _prewarm_tier1_aux(eid, _ano):
                    if eid in _no_grupo_event_ids:
                        return "skipped_no_grupo"
                    _db3 = SessionLocal()
                    try:
                        _get_medias(evento_id=eid, periodo=30, ano=_ano, force_refresh=True, db=_db3, current_user=None, response=None)
                    except Exception as _e:
                        logger.warning(f"[Warmup BG] medias pre-warm failed for {eid}: {_e}")
                    try:
                        _get_curva(evento_id=eid, ano=_ano, db=_db3, current_user=None)
                    except Exception as _e:
                        logger.warning(f"[Warmup BG] curva snapshot pre-warm failed for {eid}: {_e}")
                    try:
                        _get_curva_comp(evento_id=eid, ano=_ano, force_refresh=True, db=_db3, current_user=None, response=None)
                    except Exception as _e:
                        logger.warning(f"[Warmup BG] curva_comparativa pre-warm failed for {eid}: {_e}")
                    finally:
                        _db3.close()
                    return "ok"

                for _eid in _aux_target_ids:
                    _tier1_aux_futures[_eid] = _tier1_aux_executor.submit(_prewarm_tier1_aux, _eid, ano)
                _tier1_aux_executor.shutdown(wait=False)
                logger.info(f"[Warmup] medias+curva pre-warm started for {len(_aux_target_ids)} active events ({min(3, len(_aux_target_ids))} workers)")

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
    GAP_WORKERS = 1   # 1 worker: evita saturar o tunnel SSH do Magento no startup
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
                # force_refresh=False: usa snapshot-first (PostgreSQL) se disponível.
                # Isso evita hits desnecessários ao Magento durante o warmup de startup.
                # Snapshots válidos são carregados em memória imediatamente (< 1s).
                # Apenas eventos sem snapshot fazem o recompute completo via Magento.
                get_marketing_event_by_id(evento_id=eid, ano=ano, force_refresh=False, db=_db, current_user=None, response=None)
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

                all_magento_ids = sorted({
                    mid
                    for ids in magento_ids_by_sku.values()
                    for mid in ids
                })
                kit_configs_by_evento: dict[int, list] = {}
                if all_magento_ids:
                    kit_configs = db.query(KitConfig).filter(
                        KitConfig.id_evento.in_(all_magento_ids),
                        KitConfig.bundle_entity_id.isnot(None),
                        KitConfig.tipo_kit.isnot(None),
                    ).all()
                    for kc in kit_configs:
                        try:
                            kit_configs_by_evento.setdefault(int(kc.id_evento), []).append(kc)
                        except (ValueError, TypeError):
                            continue

                # Para cada projeto, determina os bundle_ids via KitConfig.id_evento
                seen_cache_keys: set = set()
                proj_bundle_map: list = []  # [(proj_id, bundle_ids)]
                for proj in projetos:
                    sku = (proj.codigo or "").upper().strip()
                    magento_ids = magento_ids_by_sku.get(sku, [])
                    if not magento_ids:
                        continue
                    kcs = [
                        kc
                        for magento_id in magento_ids
                        for kc in kit_configs_by_evento.get(int(magento_id), [])
                    ]
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
    import os
    from app.core.database import SessionLocal
    from app.models.user import Usuario
    from app.models.perfil_acesso import PerfilAcesso, PerfilPermissao
    from app.core.security import get_password_hash

    seed_email = os.getenv("SEED_ADMIN_EMAIL", "").strip()
    seed_password = os.getenv("SEED_ADMIN_PASSWORD", "").strip()

    if not seed_email or not seed_password:
        logger.info(
            "SEED_ADMIN_EMAIL or SEED_ADMIN_PASSWORD not set — "
            "skipping automatic admin seeding. "
            "Set both environment variables to enable first-run bootstrap."
        )
        return

    try:
        db = SessionLocal()
        user_count = db.query(Usuario).count()
        if user_count > 0:
            db.close()
            return
        logger.info("No users found. Seeding admin user from environment variables...")
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
                "marketing", "sku_mappings", "perfil_acesso", "cotacoes",
                "projecao_inscritos"
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
            email=seed_email,
            nome=seed_email.split("@")[0],
            senha_hash=get_password_hash(seed_password),
            perfil_acesso_id=admin_perfil.id,
            ativo=True
        )
        db.add(admin_user)
        db.commit()
        logger.info(f"Admin user created: {seed_email}")
        db.close()
    except Exception as e:
        logger.error(f"Error seeding admin user: {e}")

def _force_reset_password():
    """
    Se FORCE_RESET_EMAIL e FORCE_RESET_PASSWORD estiverem definidos,
    atualiza a senha daquele usuário no banco e loga o resultado.
    Remove o efeito limpando as vars após o uso (não apaga os secrets,
    apenas não faz nada se já foram removidos).
    """
    import os
    from app.core.database import SessionLocal
    from app.models.user import Usuario
    from app.core.security import get_password_hash

    email = os.getenv("FORCE_RESET_EMAIL", "").strip()
    password = os.getenv("FORCE_RESET_PASSWORD", "").strip()

    if not email or not password:
        return

    try:
        db = SessionLocal()
        user = db.query(Usuario).filter(Usuario.email == email).first()
        if not user:
            logger.warning(f"[ForceReset] Usuário '{email}' não encontrado — senha não alterada.")
            db.close()
            return
        user.senha_hash = get_password_hash(password)
        db.commit()
        logger.info(f"[ForceReset] Senha do usuário '{email}' redefinida com sucesso.")
        db.close()
    except Exception as e:
        logger.error(f"[ForceReset] Erro ao redefinir senha: {e}")


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
            has_alias_perm = db.query(PerfilPermissao).filter(
                PerfilPermissao.perfil_acesso_id == profile.id,
                PerfilPermissao.modulo == "admin_detalhe_alias"
            ).first()
            if not has_alias_perm:
                db.add(PerfilPermissao(
                    perfil_acesso_id=profile.id,
                    modulo="admin_detalhe_alias",
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
            "ALTER TABLE projecao_corte_config ADD COLUMN IF NOT EXISTS dias_alerta_envio INTEGER DEFAULT 30 NOT NULL",
            "ALTER TABLE projecao_corte_config ADD COLUMN IF NOT EXISTS notif_email_ativo BOOLEAN DEFAULT FALSE NOT NULL",
            "ALTER TABLE projecao_corte_config ADD COLUMN IF NOT EXISTS notif_email_hora INTEGER DEFAULT 8 NOT NULL",
            "ALTER TABLE projecao_corte_config ADD COLUMN IF NOT EXISTS notif_email_last_sent DATE",
            "ALTER TABLE projecao_corte_config ADD COLUMN IF NOT EXISTS notif_canal VARCHAR(20) DEFAULT 'email' NOT NULL",
            "ALTER TABLE cadastro_evento ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP",
            "ALTER TABLE kit_config ADD COLUMN IF NOT EXISTS tipo_kit VARCHAR(100)",
            "ALTER TABLE kit_config ADD COLUMN IF NOT EXISTS custo_kit DECIMAL(10,2)",
            "ALTER TABLE kit_config ADD COLUMN IF NOT EXISTS ativo_categoria VARCHAR(100)",
            "ALTER TABLE cadastro_kit_produto ADD COLUMN IF NOT EXISTS ativo_categoria VARCHAR(100)",
            "ALTER TABLE kit_config ALTER COLUMN ativo_categoria TYPE VARCHAR(500)",
            "ALTER TABLE vendas_diaria_snapshot ADD COLUMN IF NOT EXISTS ano INTEGER",
            # sync_event_log: log estruturado dos batches de sincronização
            """CREATE TABLE IF NOT EXISTS sync_event_log (
                id BIGSERIAL PRIMARY KEY,
                ciclo_id VARCHAR(40) NOT NULL,
                job_name VARCHAR(60) NOT NULL,
                nivel VARCHAR(20) NOT NULL DEFAULT 'grupo',
                grupo VARCHAR(200),
                fonte VARCHAR(20),
                status VARCHAR(20) NOT NULL,
                motivo VARCHAR(80),
                detalhes TEXT,
                qtd_antes INTEGER,
                qtd_depois INTEGER,
                data_floor DATE,
                duracao_ms INTEGER,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )""",
            "CREATE INDEX IF NOT EXISTS ix_sync_event_log_ciclo_id ON sync_event_log (ciclo_id)",
            "CREATE INDEX IF NOT EXISTS ix_sync_event_log_job_name ON sync_event_log (job_name)",
            "CREATE INDEX IF NOT EXISTS ix_sync_event_log_status ON sync_event_log (status)",
            "CREATE INDEX IF NOT EXISTS ix_sync_event_log_created_at ON sync_event_log (created_at)",
            "CREATE INDEX IF NOT EXISTS ix_sync_log_ciclo_nivel ON sync_event_log (ciclo_id, nivel)",
            "CREATE INDEX IF NOT EXISTS ix_sync_log_job_created ON sync_event_log (job_name, created_at)",
            "CREATE INDEX IF NOT EXISTS ix_dim_projeto_data_evento ON dim_projeto (data_evento)",
            "CREATE INDEX IF NOT EXISTS ix_dim_projeto_produto ON dim_projeto (produto)",
            "CREATE INDEX IF NOT EXISTS ix_dim_projeto_modalidade ON dim_projeto (modalidade)",
            "CREATE INDEX IF NOT EXISTS ix_dim_projeto_tipo_evento ON dim_projeto (tipo_evento)",
            "CREATE INDEX IF NOT EXISTS ix_dim_projeto_lei ON dim_projeto (lei)",
            "CREATE INDEX IF NOT EXISTS ix_dim_projeto_status ON dim_projeto (status)",
            "CREATE INDEX IF NOT EXISTS ix_dim_projeto_cidade ON dim_projeto (cidade)",
            "CREATE INDEX IF NOT EXISTS ix_dim_centro_custo_ativo ON dim_centro_custo (ativo)",
            "CREATE INDEX IF NOT EXISTS ix_dim_centro_custo_area ON dim_centro_custo (area)",
            "CREATE INDEX IF NOT EXISTS ix_dim_categoria_atleta_ativo ON dim_categoria_atleta (ativo)",
            "CREATE INDEX IF NOT EXISTS ix_dim_categoria_atleta_modalidade ON dim_categoria_atleta (modalidade)",
            "CREATE INDEX IF NOT EXISTS ix_dim_categoria_atleta_genero ON dim_categoria_atleta (genero)",
            "CREATE INDEX IF NOT EXISTS ix_dim_usuario_ativo ON dim_usuario (ativo)",
            "CREATE INDEX IF NOT EXISTS ix_dim_usuario_perfil_acesso_id ON dim_usuario (perfil_acesso_id)",
            "CREATE INDEX IF NOT EXISTS ix_dim_usuario_centro_custo_id ON dim_usuario (centro_custo_id)",
            "CREATE INDEX IF NOT EXISTS ix_dim_usuario_last_activity ON dim_usuario (last_activity)",
            "CREATE INDEX IF NOT EXISTS ix_tarefas_usuario_id ON tarefas (usuario_id)",
            "CREATE INDEX IF NOT EXISTS ix_tarefas_responsavel_id ON tarefas (responsavel_id)",
            "CREATE INDEX IF NOT EXISTS ix_tarefas_status ON tarefas (status)",
            "CREATE INDEX IF NOT EXISTS ix_tarefas_prioridade ON tarefas (prioridade)",
            "CREATE INDEX IF NOT EXISTS ix_tarefas_data_vencimento ON tarefas (data_vencimento)",
            "CREATE INDEX IF NOT EXISTS ix_tarefas_created_at ON tarefas (created_at)",
            "CREATE INDEX IF NOT EXISTS ix_perfil_acesso_ativo ON perfil_acesso (ativo)",
            "CREATE INDEX IF NOT EXISTS ix_perfil_acesso_is_admin ON perfil_acesso (is_admin)",
            "CREATE INDEX IF NOT EXISTS ix_perfil_permissao_perfil_acesso_id ON perfil_permissao (perfil_acesso_id)",
            "CREATE INDEX IF NOT EXISTS ix_perfil_permissao_modulo ON perfil_permissao (modulo)",
            "CREATE INDEX IF NOT EXISTS ix_perfil_permissao_campo_perfil_acesso_id ON perfil_permissao_campo (perfil_acesso_id)",
            "CREATE INDEX IF NOT EXISTS ix_perfil_permissao_campo_entidade ON perfil_permissao_campo (entidade)",
            "CREATE INDEX IF NOT EXISTS ix_perfil_permissao_campo_campo ON perfil_permissao_campo (campo)",
            "CREATE INDEX IF NOT EXISTS ix_cadastro_evento_projeto_id ON cadastro_evento (projeto_id)",
            "CREATE INDEX IF NOT EXISTS ix_cadastro_evento_data_evento ON cadastro_evento (data_evento)",
            "CREATE INDEX IF NOT EXISTS ix_cadastro_evento_deleted_at ON cadastro_evento (deleted_at)",
            "CREATE INDEX IF NOT EXISTS ix_cadastro_evento_status ON cadastro_evento (status)",
            "CREATE INDEX IF NOT EXISTS ix_cadastro_evento_modalidade ON cadastro_evento (modalidade)",
            "CREATE INDEX IF NOT EXISTS ix_cadastro_evento_tipo_evento ON cadastro_evento (tipo_evento)",
            "CREATE INDEX IF NOT EXISTS ix_cadastro_evento_data_month ON cadastro_evento ((EXTRACT(MONTH FROM data_evento)))",
            "CREATE INDEX IF NOT EXISTS ix_cadastro_cortesia_cadastro_id ON cadastro_cortesia (cadastro_id)",
            "CREATE INDEX IF NOT EXISTS ix_cadastro_taxa_cadastro_id ON cadastro_taxa (cadastro_id)",
            "CREATE INDEX IF NOT EXISTS ix_cadastro_kit_produto_cadastro_id ON cadastro_kit_produto (cadastro_id)",
            "CREATE INDEX IF NOT EXISTS ix_cadastro_kit_produto_item_kit_produto_id ON cadastro_kit_produto_item (kit_produto_id)",
            "CREATE INDEX IF NOT EXISTS ix_cadastro_merchan_cadastro_id ON cadastro_merchan (cadastro_id)",
            "CREATE INDEX IF NOT EXISTS ix_cadastro_merchan_item_merchan_id ON cadastro_merchan_item (merchan_id)",
            "CREATE INDEX IF NOT EXISTS ix_cadastro_faixa_preco_site_cadastro_id ON cadastro_faixa_preco_site (cadastro_id)",
            "CREATE INDEX IF NOT EXISTS ix_cadastro_faixa_preco_grupos_cadastro_id ON cadastro_faixa_preco_grupos (cadastro_id)",
            "CREATE INDEX IF NOT EXISTS ix_viagem_cotacao_ano_competencia ON viagem_cotacao (ano_competencia)",
            "CREATE INDEX IF NOT EXISTS ix_viagem_cotacao_status ON viagem_cotacao (status)",
            "CREATE INDEX IF NOT EXISTS ix_viagem_cotacao_created_at ON viagem_cotacao (created_at)",
            "CREATE INDEX IF NOT EXISTS ix_fornecedor_nome ON fornecedor (nome)",
            "CREATE INDEX IF NOT EXISTS ix_fornecedor_ativo ON fornecedor (ativo)",
            "CREATE INDEX IF NOT EXISTS ix_cotacao_viagem_id ON cotacao (viagem_id)",
            "CREATE INDEX IF NOT EXISTS ix_cotacao_fornecedor_id ON cotacao (fornecedor_id)",
            "CREATE INDEX IF NOT EXISTS ix_cotacao_selecionado ON cotacao (selecionado)",
            "CREATE INDEX IF NOT EXISTS ix_custo_importacao_viagem_id ON custo_importacao (viagem_id)",
            "CREATE INDEX IF NOT EXISTS ix_cotacao_evento_cotacao_id ON cotacao_evento (cotacao_id)",
            "CREATE INDEX IF NOT EXISTS ix_cotacao_evento_cadastro_evento_id ON cotacao_evento (cadastro_evento_id)",
            # consolidacao_checkpoint: checkpoint persistente para retomada da
            # reconsolidação completa após reinício/crash do backend.
            """CREATE TABLE IF NOT EXISTS consolidacao_checkpoint (
                id BIGSERIAL PRIMARY KEY,
                ciclo_id VARCHAR(40) NOT NULL,
                evento_grupo VARCHAR(200) NOT NULL,
                status VARCHAR(20) NOT NULL,
                incremental INTEGER NOT NULL DEFAULT 0,
                triggered_by VARCHAR(200),
                duracao_ms INTEGER,
                motivo VARCHAR(400),
                qtd_antes INTEGER,
                qtd_depois INTEGER,
                started_at_cycle TIMESTAMPTZ,
                processed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT uq_consol_ckpt_ciclo_grupo UNIQUE (ciclo_id, evento_grupo)
            )""",
            "CREATE INDEX IF NOT EXISTS ix_consol_ckpt_ciclo_id ON consolidacao_checkpoint (ciclo_id)",
            "CREATE INDEX IF NOT EXISTS ix_consol_ckpt_processed_at ON consolidacao_checkpoint (processed_at)",
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
            "ALTER TABLE dim_usuario ADD COLUMN IF NOT EXISTS recebe_insights_nori BOOLEAN DEFAULT FALSE",
            "ALTER TABLE dim_usuario ADD COLUMN IF NOT EXISTS foto_perfil VARCHAR(500)",
            "ALTER TABLE dim_usuario ADD COLUMN IF NOT EXISTS foto_perfil_data BYTEA",
            "ALTER TABLE dim_usuario ADD COLUMN IF NOT EXISTS foto_perfil_mime VARCHAR(50)",
            # Microsoft Entra ID (SSO + sync de diretório) — task #72
            "ALTER TABLE dim_usuario ALTER COLUMN senha_hash DROP NOT NULL",
            "ALTER TABLE dim_usuario ADD COLUMN IF NOT EXISTS ms_oid VARCHAR(100)",
            "ALTER TABLE dim_usuario ADD COLUMN IF NOT EXISTS auth_provider VARCHAR(20) DEFAULT 'local' NOT NULL",
            "ALTER TABLE dim_usuario ADD COLUMN IF NOT EXISTS ms_synced_at TIMESTAMP",
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_dim_usuario_ms_oid ON dim_usuario (ms_oid)",
            "ALTER TABLE system_health_events ADD COLUMN IF NOT EXISTS resolved_at TIMESTAMP WITH TIME ZONE",
            "ALTER TABLE system_health_events ADD COLUMN IF NOT EXISTS resolved_by VARCHAR(255)",
            "ALTER TABLE projecao_corte_snapshot ADD COLUMN IF NOT EXISTS reaberto_manual_corte_1 BOOLEAN DEFAULT FALSE NOT NULL",
            "ALTER TABLE projecao_corte_snapshot ADD COLUMN IF NOT EXISTS reaberto_manual_corte_2 BOOLEAN DEFAULT FALSE NOT NULL",
            "ALTER TABLE projecao_corte_snapshot ADD COLUMN IF NOT EXISTS congelado_manual_corte_1 BOOLEAN DEFAULT FALSE NOT NULL",
            "ALTER TABLE projecao_corte_snapshot ADD COLUMN IF NOT EXISTS congelado_manual_corte_2 BOOLEAN DEFAULT FALSE NOT NULL",
            "ALTER TABLE evento_grupos ADD COLUMN IF NOT EXISTS circuito VARCHAR(200)",
            "ALTER TABLE evento_grupos ADD COLUMN IF NOT EXISTS cidade_normalizada VARCHAR(200)",
            "ALTER TABLE evento_grupos ADD COLUMN IF NOT EXISTS curva_override VARCHAR(200)",
            "ALTER TABLE evento_grupos ADD COLUMN IF NOT EXISTS curva_override_modo VARCHAR(20)",
            "ALTER TABLE curva_historica_snapshot ADD COLUMN IF NOT EXISTS origem VARCHAR(50)",
            "ALTER TABLE curva_historica_snapshot ADD COLUMN IF NOT EXISTS fonte_origem VARCHAR(200)",
            "ALTER TABLE cadastro_evento ADD COLUMN IF NOT EXISTS ciclismo_participacao_pago INTEGER DEFAULT 0",
            "ALTER TABLE cadastro_evento ADD COLUMN IF NOT EXISTS ciclismo_sem_bike_pago INTEGER DEFAULT 0",
            "ALTER TABLE cadastro_evento ADD COLUMN IF NOT EXISTS ciclismo_sem_bike_tkt_medio NUMERIC(10,2) DEFAULT 0",
            "ALTER TABLE cadastro_evento ADD COLUMN IF NOT EXISTS ciclismo_com_bike_pago INTEGER DEFAULT 0",
            "ALTER TABLE cadastro_evento ADD COLUMN IF NOT EXISTS ciclismo_com_bike_tkt_medio NUMERIC(10,2) DEFAULT 0",
            "ALTER TABLE kit_config ADD COLUMN IF NOT EXISTS cenario_ciclismo VARCHAR(50)",
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
            "ALTER TABLE acoes_comerciais DROP CONSTRAINT IF EXISTS check_tipo_acao",
            "ALTER TABLE acoes_comerciais ADD CONSTRAINT check_tipo_acao CHECK (tipo IN ('AUMENTO_PRECO', 'REDUCAO_PRECO', 'PROMOCAO', 'CAMPANHA', 'COMUNICACAO', 'NENHUMA_ACAO', 'OUTROS'))",
            """
            CREATE TABLE IF NOT EXISTS area_projecao (
                id SERIAL PRIMARY KEY,
                nome VARCHAR(100) UNIQUE NOT NULL,
                ativo BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS area_projecao_usuario (
                id SERIAL PRIMARY KEY,
                area_projecao_id INTEGER NOT NULL REFERENCES area_projecao(id) ON DELETE CASCADE,
                usuario_id INTEGER NOT NULL REFERENCES dim_usuario(id) ON DELETE CASCADE,
                created_at TIMESTAMP DEFAULT NOW(),
                CONSTRAINT uq_area_usuario UNIQUE (area_projecao_id, usuario_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS projecao_inscritos (
                id SERIAL PRIMARY KEY,
                evento_id INTEGER NOT NULL REFERENCES cadastro_evento(id) ON DELETE CASCADE,
                area_projecao_id INTEGER NOT NULL REFERENCES area_projecao(id) ON DELETE CASCADE,
                quantidade INTEGER NOT NULL DEFAULT 0,
                created_by INTEGER NOT NULL REFERENCES dim_usuario(id),
                updated_by INTEGER REFERENCES dim_usuario(id),
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP,
                CONSTRAINT uq_evento_area_projecao UNIQUE (evento_id, area_projecao_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS projecao_inscritos_historico (
                id SERIAL PRIMARY KEY,
                projecao_id INTEGER NOT NULL REFERENCES projecao_inscritos(id) ON DELETE CASCADE,
                acao VARCHAR(20) NOT NULL,
                campo_alterado VARCHAR(50),
                valor_anterior TEXT,
                valor_novo TEXT,
                usuario_id INTEGER NOT NULL REFERENCES dim_usuario(id),
                created_at TIMESTAMP DEFAULT NOW()
            )
            """,
            "CREATE INDEX IF NOT EXISTS ix_projecao_evento ON projecao_inscritos (evento_id)",
            "CREATE INDEX IF NOT EXISTS ix_projecao_area ON projecao_inscritos (area_projecao_id)",
            "CREATE INDEX IF NOT EXISTS ix_projecao_hist_projecao ON projecao_inscritos_historico (projecao_id)",
            "ALTER TABLE projecao_inscritos ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP",
            "ALTER TABLE projecao_inscritos DROP CONSTRAINT IF EXISTS uq_evento_area_projecao",
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_evento_area_projecao_active ON projecao_inscritos (evento_id, area_projecao_id) WHERE deleted_at IS NULL",
            "ALTER TABLE cotacao_fob ADD COLUMN IF NOT EXISTS indice_importacao NUMERIC(10,6)",
            "ALTER TABLE cotacao_fob ADD COLUMN IF NOT EXISTS bec NUMERIC(10,6)",
            "ALTER TABLE cotacao_fob ADD COLUMN IF NOT EXISTS cotacao_cambio NUMERIC(10,4)",
            "ALTER TABLE cotacao_fob ADD COLUMN IF NOT EXISTS valor_nacionalizado NUMERIC(15,4)",
            "ALTER TABLE kit_config ADD COLUMN IF NOT EXISTS ignorado BOOLEAN DEFAULT FALSE NOT NULL",
            # Ativo-only kits use 48-bit synthetic ids (até ~2.8e14), exceeding INTEGER range.
            # Conditional: só executa o ALTER se ainda for INTEGER (evita locks redundantes a cada startup).
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'kit_config'
                      AND column_name = 'bundle_entity_id'
                      AND data_type = 'integer'
                ) THEN
                    ALTER TABLE kit_config ALTER COLUMN bundle_entity_id TYPE BIGINT;
                END IF;
            END $$
            """,
            # margem_bundle_rev_snapshot: qtd por bundle (fallback persistente p/ count_query do Magento)
            "ALTER TABLE margem_bundle_rev_snapshot ADD COLUMN IF NOT EXISTS qtd_inscricoes INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE projecao_inscritos ADD COLUMN IF NOT EXISTS locked_at TIMESTAMP",
            "ALTER TABLE projecao_inscritos ADD COLUMN IF NOT EXISTS locked_by INTEGER REFERENCES dim_usuario(id)",
            "ALTER TABLE projecao_auto_lock_config ADD COLUMN IF NOT EXISTS hora_trava VARCHAR(5) DEFAULT '00:00' NOT NULL",
            "ALTER TABLE projecao_inscritos_historico ALTER COLUMN campo_alterado TYPE VARCHAR(200)",
            "CREATE INDEX IF NOT EXISTS ix_area_projecao_ativo ON area_projecao (ativo)",
            "CREATE INDEX IF NOT EXISTS ix_area_projecao_usuario_area_id ON area_projecao_usuario (area_projecao_id)",
            "CREATE INDEX IF NOT EXISTS ix_area_projecao_usuario_usuario_id ON area_projecao_usuario (usuario_id)",
            "CREATE INDEX IF NOT EXISTS ix_projecao_created_by ON projecao_inscritos (created_by)",
            "CREATE INDEX IF NOT EXISTS ix_projecao_updated_by ON projecao_inscritos (updated_by)",
            "CREATE INDEX IF NOT EXISTS ix_projecao_locked_by ON projecao_inscritos (locked_by)",
            "CREATE INDEX IF NOT EXISTS ix_projecao_locked_at ON projecao_inscritos (locked_at)",
            "CREATE INDEX IF NOT EXISTS ix_projecao_deleted_at ON projecao_inscritos (deleted_at)",
            "CREATE INDEX IF NOT EXISTS ix_projecao_active_evento_area ON projecao_inscritos (evento_id, area_projecao_id) WHERE deleted_at IS NULL",
            "CREATE INDEX IF NOT EXISTS ix_projecao_hist_usuario ON projecao_inscritos_historico (usuario_id)",
            "CREATE INDEX IF NOT EXISTS ix_projecao_hist_created_at ON projecao_inscritos_historico (created_at)",
            "CREATE INDEX IF NOT EXISTS ix_projecao_cliente_projecao_id ON projecao_inscritos_cliente (projecao_id)",
            "CREATE INDEX IF NOT EXISTS ix_projecao_kit_projecao_id ON projecao_inscritos_kit (projecao_id)",
            """
            CREATE TABLE IF NOT EXISTS projecao_cutoff_rule (
                id SERIAL PRIMARY KEY,
                nome VARCHAR(100) NOT NULL,
                dias_antes_evento INTEGER NOT NULL,
                ativo BOOLEAN DEFAULT TRUE NOT NULL,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP
            )
            """,
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_cutoff_dias ON projecao_cutoff_rule (dias_antes_evento)",
            "CREATE INDEX IF NOT EXISTS ix_projecao_cutoff_rule_ativo ON projecao_cutoff_rule (ativo)",
            "ALTER TABLE area_projecao ADD COLUMN IF NOT EXISTS usa_cutoff_customizado BOOLEAN DEFAULT FALSE NOT NULL",
            """
            CREATE TABLE IF NOT EXISTS projecao_cutoff_evento_area (
                id SERIAL PRIMARY KEY,
                evento_id INTEGER NOT NULL REFERENCES cadastro_evento(id) ON DELETE CASCADE,
                area_projecao_id INTEGER NOT NULL REFERENCES area_projecao(id) ON DELETE CASCADE,
                data_corte_1 DATE,
                data_corte_2 DATE,
                data_saida_caminhao DATE,
                created_by INTEGER REFERENCES dim_usuario(id),
                updated_by INTEGER REFERENCES dim_usuario(id),
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP,
                CONSTRAINT uq_cutoff_evento_area UNIQUE (evento_id, area_projecao_id)
            )
            """,
            "ALTER TABLE projecao_cutoff_evento_area ADD COLUMN IF NOT EXISTS data_saida_caminhao DATE",
            "CREATE INDEX IF NOT EXISTS ix_cutoff_evento_area_evento ON projecao_cutoff_evento_area (evento_id)",
            "CREATE INDEX IF NOT EXISTS ix_cutoff_evento_area_area ON projecao_cutoff_evento_area (area_projecao_id)",
            "CREATE INDEX IF NOT EXISTS ix_cutoff_evento_area_created_by ON projecao_cutoff_evento_area (created_by)",
            "CREATE INDEX IF NOT EXISTS ix_cutoff_evento_area_updated_by ON projecao_cutoff_evento_area (updated_by)",
            "ALTER TABLE projecao_cutoff_evento_area ADD COLUMN IF NOT EXISTS observacao_corte_1 TEXT",
            """
            CREATE TABLE IF NOT EXISTS projecao_corte_dist_snapshot (
                id SERIAL PRIMARY KEY,
                evento_id INTEGER NOT NULL REFERENCES cadastro_evento(id) ON DELETE CASCADE,
                area_projecao_id INTEGER NOT NULL REFERENCES area_projecao(id) ON DELETE CASCADE,
                quantidade INTEGER NOT NULL DEFAULT 0,
                kits_json TEXT,
                clientes_json TEXT,
                congelado_em TIMESTAMP,
                updated_at TIMESTAMP DEFAULT NOW(),
                CONSTRAINT uq_corte_dist_snapshot_evento_area UNIQUE (evento_id, area_projecao_id)
            )
            """,
            "CREATE INDEX IF NOT EXISTS ix_corte_dist_snapshot_evento ON projecao_corte_dist_snapshot (evento_id)",
            "CREATE INDEX IF NOT EXISTS ix_corte_dist_snapshot_area ON projecao_corte_dist_snapshot (area_projecao_id)",
            "CREATE INDEX IF NOT EXISTS ix_cotacao_fob_circuito ON cotacao_fob (circuito)",
            "CREATE INDEX IF NOT EXISTS ix_cotacao_fob_produto ON cotacao_fob (produto)",
            # gratuito flag added to cadastro_evento (task #3769e50)
            "ALTER TABLE cadastro_evento ADD COLUMN IF NOT EXISTS gratuito BOOLEAN DEFAULT FALSE",
            # pi_pai_min_price: valor bruto do índice Magento (catalog_product_index_price.min_price)
            # separado do special_price (COALESCE) para bypass da Regra B no ticket ISC
            "ALTER TABLE kit_mapping_snapshot ADD COLUMN IF NOT EXISTS pi_pai_min_price NUMERIC(12,2)",
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

def _seed_areas_projecao():
    from app.core.database import SessionLocal
    try:
        db = SessionLocal()
        areas_padrao = [
            "Atendimento",
            "Marketing",
            "Relações Institucionais",
            "Company",
            "Comercial",
            "Cortesia RH",
            "Site",
        ]
        for nome in areas_padrao:
            exists = db.execute(text("SELECT id FROM area_projecao WHERE nome = :nome"), {"nome": nome}).fetchone()
            if not exists:
                db.execute(text("INSERT INTO area_projecao (nome, ativo) VALUES (:nome, TRUE)"), {"nome": nome})

        # Áreas descontinuadas: marcar como inativas para que sumam da UI
        areas_descontinuadas = [
            "Relações Institucionais - Sem Kit",
            "Company - Sem Kit",
        ]
        for nome in areas_descontinuadas:
            db.execute(
                text("UPDATE area_projecao SET ativo = FALSE WHERE nome = :nome"),
                {"nome": nome},
            )

        db.commit()
        db.close()
        logger.info(f"Seed áreas de projeção: {len(areas_padrao)} áreas verificadas/criadas")
    except Exception as e:
        logger.error(f"Seed áreas de projeção failed: {e}")


def _seed_cutoff_rules():
    from app.core.database import SessionLocal
    try:
        db = SessionLocal()
        regras_padrao = [
            {"nome": "Primeiro alerta", "dias_antes_evento": 45},
            {"nome": "Alerta final", "dias_antes_evento": 15},
        ]
        for r in regras_padrao:
            exists = db.execute(
                text("SELECT id FROM projecao_cutoff_rule WHERE dias_antes_evento = :d"),
                {"d": r["dias_antes_evento"]},
            ).fetchone()
            if not exists:
                db.execute(
                    text("INSERT INTO projecao_cutoff_rule (nome, dias_antes_evento, ativo) VALUES (:n, :d, TRUE)"),
                    {"n": r["nome"], "d": r["dias_antes_evento"]},
                )
        db.commit()
        db.close()
        logger.info(f"Seed regras de corte: {len(regras_padrao)} regras verificadas/criadas")
    except Exception as e:
        logger.error(f"Seed regras de corte failed: {e}")


def _resync_id_sequences():
    """Idempotente: alinha cada sequence de coluna `id` com o MAX(id) da tabela.

    Corrige o caso em que dados foram inseridos com IDs explícitos (seed/importação)
    sem avançar o sequence, causando `UniqueViolation` no PK em INSERTs subsequentes
    (ex.: criação de projeção falhando em produção).
    """
    from app.core.database import SessionLocal
    try:
        db = SessionLocal()
        db.execute(text("""
            DO $$
            DECLARE
                r RECORD;
                seq TEXT;
                maxid BIGINT;
                curval BIGINT;
            BEGIN
                FOR r IN
                    SELECT table_name
                    FROM information_schema.columns
                    WHERE table_schema = 'public' AND column_name = 'id'
                LOOP
                    seq := pg_get_serial_sequence(quote_ident(r.table_name), 'id');
                    IF seq IS NOT NULL THEN
                        EXECUTE format('SELECT COALESCE(MAX(id), 0) FROM %I', r.table_name) INTO maxid;
                        IF maxid > 0 THEN
                            -- Monotônico: nunca recua a sequence, apenas avança quando atrás do MAX(id).
                            EXECUTE format('SELECT last_value FROM %s', seq) INTO curval;
                            PERFORM setval(seq, GREATEST(curval, maxid), true);
                        END IF;
                    END IF;
                END LOOP;
            END $$;
        """))
        db.commit()
        db.close()
        logger.info("Resync de sequences de id concluído")
    except Exception as e:
        logger.error(f"Resync de sequences de id failed: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    register_full_warmup_fn(_full_cache_warmup)
    cache_scheduler.register_full_refresh(_full_cache_warmup)
    cache_scheduler.register(_scheduled_isc_refresh)
    cache_scheduler.register(_scheduled_sincronizar_hoje)
    cache_scheduler.register(_scheduled_margem_rev_safety_check)
    cache_scheduler.register(_scheduled_cleanup_sessions)
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

    def _projecao_notif_loop():
        """Loop diário do resumo de pendências por e-mail (Projeção de Inscritos).

        Verifica a cada 60s; quando ativo e hoje ainda não enviou e já passou da
        hora configurada (BRT), dispara o resumo e marca `notif_email_last_sent`.
        É puro-PG/Microsoft Graph (não toca Magento), por isso roda independente do
        ENABLE_BACKGROUND_MAGENTO_SYNC. Só envia se o admin tiver ativado.
        """
        from zoneinfo import ZoneInfo as _ZI
        from datetime import datetime as _dt
        import time as _t
        from app.core.database import SessionLocal as _SL
        from app.models.projecao import ProjecaoCorteConfig as _PCC
        from app.services.projecao_notif_service import enviar_resumo_diario as _envia
        _brt = _ZI('America/Sao_Paulo')
        logger.info("[ProjecaoNotif] Loop de resumo diário iniciado")
        _last_total_fail_ts = 0.0  # cooldown p/ retry quando NINGUÉM recebeu
        _RETRY_COOLDOWN_S = 600  # 10 min entre tentativas em falha total
        while True:
            try:
                _db = _SL()
                try:
                    _cfg = _db.query(_PCC).first()
                    if _cfg and _cfg.notif_email_ativo:
                        _now = _dt.now(_brt)
                        _today = _now.date()
                        _hora = _cfg.notif_email_hora if _cfg.notif_email_hora is not None else 8
                        if _cfg.notif_email_last_sent != _today and _now.hour >= _hora:
                            if (_t.time() - _last_total_fail_ts) >= _RETRY_COOLDOWN_S:
                                logger.info(f"[ProjecaoNotif] Disparando resumo diário (hora alvo={_hora}h BRT)")
                                _resumo = _envia(_db)
                                _enviados = _resumo.get('enviados', 0) or 0
                                _falhas = _resumo.get('falhas', 0) or 0
                                # Marca o dia como concluído quando houve sucesso
                                # (mesmo parcial — reenviar duplicaria quem recebeu)
                                # OU quando não havia nada a enviar (falhas==0).
                                # Só NÃO marca em falha TOTAL (ninguém recebeu),
                                # para tentar de novo após o cooldown no mesmo dia.
                                if _enviados > 0 or _falhas == 0:
                                    _cfg.notif_email_last_sent = _today
                                    _db.commit()
                                    logger.info(
                                        f"[ProjecaoNotif] Resumo: {_enviados} enviado(s), {_falhas} falha(s) — dia marcado."
                                    )
                                else:
                                    _last_total_fail_ts = _t.time()
                                    logger.warning(
                                        f"[ProjecaoNotif] Falha TOTAL ({_falhas} falha(s), 0 enviado) — "
                                        f"NÃO marcado; nova tentativa em {_RETRY_COOLDOWN_S//60}min."
                                    )
                finally:
                    _db.close()
            except Exception as _e:
                logger.warning(f"[ProjecaoNotif] Loop erro (não-fatal): {_e}")
            _t.sleep(60)

    def _all_background_init():
        """All startup work runs in background so the server starts immediately."""
        # Phase 0: schema setup (idempotent, safe to run after yield)
        try:
            from app.models import nori_insights as _ni_models  # noqa: F401 — ensure table is registered
            from app.models import system_health as _sh_models  # noqa: F401 — ensure health tables are registered
            from app.models import projecao as _proj_models  # noqa: F401 — ensure projecao tables are registered
            from app.models import job_run_health as _jrh_models  # noqa: F401 — ensure job_run_health table is registered
            from app.models import evento_detail_snapshot as _eds_models  # noqa: F401 — ensure detail snapshot table is registered
            from app.models import user_session as _us_models  # noqa: F401 — ensure user_sessions table is registered
            from app.models import vendas_snapshot as _vs_models  # noqa: F401 — ensure DetalheEventosSnapshot table is registered
            if engine:
                Base.metadata.create_all(bind=engine)
            _run_column_migrations()
            seed_admin_user()
            _force_reset_password()
            _seed_kit_config()
            _seed_areas_projecao()
            _seed_cutoff_rules()
            _resync_id_sequences()
        except Exception as e:
            logger.error(f"Schema/seed setup failed: {e}")

        # Phase 0.5: descarta snapshots de detalhe calculados com query antiga
        try:
            from app.core.database import SessionLocal as _SL_flush
            from app.services.detalhe_eventos_service import maybe_flush_snapshots_on_version_change
            _db_flush = _SL_flush()
            try:
                maybe_flush_snapshots_on_version_change(_db_flush)
            finally:
                _db_flush.close()
        except Exception as e:
            logger.error(f"Detalhe snapshot version flush failed: {e}")

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
        if ENABLE_BACKGROUND_MAGENTO_SYNC and ENABLE_TIER1_STARTUP_WARMUP:
            try:
                logger.info("Running Tier1 gap detection...")
                _gap_result = _startup_tier1_gap_warmup()
                if isinstance(_gap_result, tuple):
                    _gap_warmup_ok, _gap_warmup_fail = _gap_result
                logger.info("Tier1 gap detection complete")
            except Exception as e:
                logger.error(f"Startup gap detection failed: {e}")
        elif not ENABLE_BACKGROUND_MAGENTO_SYNC:
            logger.info("[Startup] Tier1 gap warmup SKIPPED (ENABLE_BACKGROUND_MAGENTO_SYNC=false)")
        else:
            logger.info("[Startup] Tier1 gap warmup SKIPPED (ENABLE_TIER1_STARTUP_WARMUP=false — recompute lazy no primeiro acesso, protegido por singleflight)")

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

        # Phase 3.5: repair orphan CurvaHistoricaSnapshot entries in background
        # Groups invalidated/re-synced outside the nightly batch (e.g. newly
        # created historical groups) may have VendasDiariaSnapshot data but no
        # CurvaHistoricaSnapshot.  Repair them now so they appear in
        # available-curves immediately without waiting for the next nightly run.
        try:
            import threading as _repair_threading
            def _repair_orphan_curves():
                try:
                    from app.core.database import SessionLocal as _RepairSL
                    from app.services.snapshot_service import _repair_orphan_curva_historica
                    _rep_db = _RepairSL()
                    try:
                        n = _repair_orphan_curva_historica(_rep_db)
                        if n:
                            logger.info(f"[Startup] Orphan CurvaHistoricaSnapshot repair: {n} group(s) fixed")
                    finally:
                        _rep_db.close()
                except Exception as _re:
                    logger.warning(f"[Startup] Orphan curve repair failed: {_re}")
            _repair_threading.Thread(target=_repair_orphan_curves, daemon=True).start()
        except Exception as _re_err:
            logger.warning(f"[Startup] Could not start orphan curve repair: {_re_err}")

        # Phase 4: scheduler, then snapshot + warmup in parallel
        # Interval bumped from 30min → 45min to reduce daytime pressure on the
        # upstream MySQL pools (Magento via SSH tunnel). The dashboard list
        # also trusts the snapshot as fresh within 50min, so today's row stays
        # visibly up-to-date between batches.
        # ── CAMADA 2: Catch-up reforçado do job 02h BRT ─────────────────────
        # IMPORTANTE: rodar ANTES de cache_scheduler.start() para que, se
        # decidirmos forçar consolidação, possamos logar 'iniciado' no ciclo
        # ANTES do _schedule_snapshot_consolidation rodar — assim o scheduler
        # cai na branch (c) "running_recent" e re-agenda em 10min ao invés de
        # disparar Timer paralelo em 90s. Evita carga duplicada no Magento.
        #
        # Independente da "freshness" de VendasDiariaSnapshot (que pode estar
        # bumpada por sincronizar_hoje_batch do scheduler de 45min sem que a
        # consolidação 02h tenha rodado), checa EXPLICITAMENTE se o ciclo
        # `consolidacao_diaria_04h` (nivel='ciclo' status='concluido') rodou
        # nas últimas 24h. Se NÃO rodou E já passou das 02h BRT hoje, força
        # a consolidação no startup (mesmo se snapshots parecerem frescos).
        # Cobre o cenário: backend reinicia às 13h-22h sem ter rodado 02h.
        _force_consolidation_catchup = False
        _catchup_ciclo_id = None  # ciclo_id pré-alocado, será preenchido se forçarmos catch-up
        _catchup_lock_conn = None  # connection segurando advisory lock — release no fim do thread
        try:
            from app.core.database import SessionLocal as _CatchSL
            from app.models.sync_event_log import SyncEventLog as _SEL_catch
            from sqlalchemy import and_ as _and_catch
            from datetime import datetime as _dt_catch, timedelta as _td_catch, timezone as _tz_catch
            from zoneinfo import ZoneInfo as _ZI_catch
            _now_brt_catch = _dt_catch.now(_ZI_catch('America/Sao_Paulo'))
            _today_02h_brt = _now_brt_catch.replace(hour=2, minute=0, second=0, microsecond=0)
            if _now_brt_catch >= _today_02h_brt:
                _cutoff_utc = (_dt_catch.now(_tz_catch.utc) - _td_catch(hours=24))
                _cdb_catch = _CatchSL()
                try:
                    _last_ok = _cdb_catch.query(_SEL_catch.id).filter(
                        _and_catch(
                            _SEL_catch.job_name == "consolidacao_diaria_04h",
                            _SEL_catch.nivel == "ciclo",
                            _SEL_catch.status == "concluido",
                            _SEL_catch.created_at >= _cutoff_utc,
                        )
                    ).first()
                    if not _last_ok and ENABLE_BACKGROUND_MAGENTO_SYNC:
                        # Gate por ENABLE_BACKGROUND_MAGENTO_SYNC: se a flag está off, o thread
                        # não vai rodar lá embaixo (snapshot_thread.start() é pulado), então NÃO
                        # adquirimos o lock — caso contrário ele ficaria pendurado até o processo
                        # morrer, bloqueando endpoint (409) e scheduler interno (re-agenda 10min).
                        # ADVISORY LOCK cross-process — se endpoint /scheduled-jobs/...
                        # ou scheduler interno já estiver rodando, NÃO ativamos catch-up
                        # (evita dois jobs pesados em paralelo).
                        from app.services.sync_log_service import (
                            new_ciclo_id as _ncid_catch,
                            log_evento_strict as _les_catch,
                            acquire_consolidation_lock as _acq_catch,
                            release_consolidation_lock as _rel_catch,
                        )
                        _catchup_lock_conn = _acq_catch()
                        if _catchup_lock_conn is None:
                            _catchup_ciclo_id = None
                            _force_consolidation_catchup = False
                            logger.warning(
                                "[Startup] CATCH-UP REFORÇADO PULADO: advisory lock detido por outro processo "
                                "(Scheduled Deployment ou scheduler interno já estão consolidando)."
                            )
                        else:
                            # Loga 'iniciado' com STRICT — se falhar, libera lock e desiste.
                            try:
                                _catchup_ciclo_id = _ncid_catch()
                                _les_catch(
                                    _catchup_ciclo_id,
                                    "consolidacao_diaria_04h",
                                    "iniciado",
                                    nivel="ciclo",
                                    detalhes="Startup catch-up reforçado: 02h BRT não rodou nas últimas 24h",
                                )
                                _force_consolidation_catchup = True
                                logger.warning(
                                    f"[Startup] CATCH-UP REFORÇADO ativado (ciclo={_catchup_ciclo_id}): nenhuma "
                                    f"'consolidacao_diaria_04h' concluída nas últimas 24h. Forçando consolidação."
                                )
                            except Exception as _le_err:
                                _rel_catch(_catchup_lock_conn)
                                _catchup_lock_conn = None
                                _catchup_ciclo_id = None
                                _force_consolidation_catchup = False
                                logger.error(
                                    f"[Startup] CATCH-UP REFORÇADO ABORTADO: log strict de 'iniciado' falhou — "
                                    f"lock liberado, scheduler interno (Timer 90s) assume. Erro: {_le_err}"
                                )
                    else:
                        logger.info("[Startup] Consolidação 02h BRT já completou nas últimas 24h — catch-up reforçado não necessário.")
                finally:
                    _cdb_catch.close()
        except Exception as _cc_err:
            logger.warning(f"[Startup] Falha no check de catch-up reforçado: {_cc_err}")

        if ENABLE_BACKGROUND_MAGENTO_SYNC:
            try:
                _scheduler_interval_s = max(300, int(os.getenv("CACHE_REFRESH_INTERVAL_SECONDS", "5400")))
            except (TypeError, ValueError):
                logger.warning(
                    f"[Config] CACHE_REFRESH_INTERVAL_SECONDS inválido "
                    f"('{os.getenv('CACHE_REFRESH_INTERVAL_SECONDS')}') — usando default 5400s"
                )
                _scheduler_interval_s = 5400
            cache_scheduler.start(interval=_scheduler_interval_s)
            logger.info(
                f"Cache auto-refresh scheduler started ({_scheduler_interval_s//60} min interval + "
                f"daily 05:00 BRT, quiet hours {os.getenv('SCHEDULER_QUIET_HOURS_START','22')}h-"
                f"{os.getenv('SCHEDULER_QUIET_HOURS_END','6')}h BRT)"
            )
        else:
            logger.info("[Startup] cache_scheduler NOT started (ENABLE_BACKGROUND_MAGENTO_SYNC=false)")

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
            # Se o catch-up reforçado alocou um ciclo_id, fechamos esse ciclo
            # no fim com 'concluido'/'parcial'/'falha' para que as camadas 2/3
            # enxerguem corretamente que rodou hoje.
            _ciclo_terminal_status = "concluido"
            _ciclo_errors: list = []
            # Sempre aloca um ciclo_id para sub-step logging (reusa _catchup_ciclo_id
            # se já foi alocado pelo catch-up forçado). CRÍTICO p/ idempotência:
            # outras camadas só enxergam steps concluídos via SyncEventLog nivel='grupo'.
            try:
                from app.services.sync_log_service import new_ciclo_id as _ncid_su
                _step_ciclo_id = _catchup_ciclo_id or _ncid_su()
            except Exception:
                _step_ciclo_id = None

            # ADVISORY LOCK obrigatório p/ startup normal (snapshot stale): impede
            # execução paralela com Scheduled Deployment ou scheduler interno.
            # Se catch-up forçado JÁ adquiriu o lock (_catchup_lock_conn set), reusa.
            _local_lock_conn = None  # connection adquirida aqui dentro (release no finally)
            if _catchup_lock_conn is None:
                try:
                    from app.services.sync_log_service import acquire_consolidation_lock as _acq_run
                    _local_lock_conn = _acq_run()
                    if _local_lock_conn is None:
                        logger.warning(
                            "[Startup] Snapshot consolidation PULADA: advisory lock detido por "
                            "outro processo (Scheduled Deployment ou scheduler interno consolidando)."
                        )
                        if _step_ciclo_id:
                            try:
                                from app.services.sync_log_service import log_evento as _le_skip
                                _le_skip(_step_ciclo_id, "consolidacao_diaria_04h", "pulado",
                                         nivel="ciclo", motivo="lock_em_uso",
                                         detalhes="Startup snapshot pulou: outro processo segura advisory lock")
                            except Exception:
                                pass
                        return
                except Exception as _e_acq:
                    # FAIL-CLOSED: se a aquisição do lock lança exceção, NÃO executa
                    # sem lock (evita execução paralela com endpoint/scheduler interno).
                    # Scheduler interno (45min) ou Scheduled Deployment assumem.
                    logger.error(
                        f"[Startup] Snapshot consolidation ABORTADA (fail-closed): "
                        f"acquire_consolidation_lock lançou exception — {_e_acq}"
                    )
                    if _step_ciclo_id:
                        try:
                            from app.services.sync_log_service import log_evento as _le_failclosed
                            _le_failclosed(_step_ciclo_id, "consolidacao_diaria_04h", "falha",
                                           nivel="ciclo", motivo="lock_acquire_error",
                                           detalhes=f"acquire_consolidation_lock exception: {str(_e_acq)[:300]}")
                        except Exception:
                            pass
                    return
            try:
                from app.core.database import SessionLocal
                from app.services.snapshot_service import snapshot_diario_batch, rebuild_rolling_grupos_batch, consolidar_curvas_historicas_batch, sincronizar_hoje_batch, sincronizar_margem_bundle_rev_batch, sincronizar_detalhe_eventos_batch
                logger.info(f"Starting snapshot consolidation (parallel, step_ciclo={_step_ciclo_id})...")
                # Classifica dict.status como _run_step (cache.py): batches que retornam
                # dict com status='falha_persistencia'/'parcial' NÃO lançam exception.
                def _classify_ret(ret) -> str:
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

                def _le_step(status: str, step: str, **kwargs):
                    """Grava SyncEventLog nivel='grupo' p/ este sub-passo.
                    CRÍTICO p/ idempotência: outras camadas só sabem que esse step
                    concluiu OK hoje se houver linha 'ok' nivel='grupo' no SyncEventLog.
                    """
                    if not _step_ciclo_id:
                        return
                    try:
                        from app.services.sync_log_service import log_evento as _le_su
                        _le_su(_step_ciclo_id, "consolidacao_diaria_04h", status,
                               nivel="grupo", grupo=step, **kwargs)
                    except Exception:
                        pass

                def _run_step_startup(step: str, fn):
                    # Idempotência: pula se este sub-passo já concluiu OK hoje BRT
                    # em qualquer ciclo (Scheduled Deployment, scheduler interno, ou
                    # um catch-up anterior). Garante que reinicializações sucessivas
                    # do backend não refaçam trabalho pesado de Magento.
                    try:
                        from app.services.sync_log_service import step_already_done_today as _sad_su
                        if _sad_su("consolidacao_diaria_04h", step):
                            _le_step("pulado", step, motivo="ja_executado_hoje",
                                     detalhes=f"{step} já concluído hoje BRT — pulado (idempotência)")
                            logger.info(f"[Startup] {step} pulado: já concluiu hoje BRT (idempotência)")
                            return
                    except Exception as _e_idem_su:
                        logger.warning(f"[Startup] check idempotência de {step} falhou: {_e_idem_su}")
                    _le_step("iniciado", step)
                    try:
                        ret = fn()
                        cls = _classify_ret(ret)
                        if cls in ("falha", "parcial"):
                            logger.error(f"[Startup] {step} terminou {cls}: {ret}")
                            _ciclo_errors.append(f"{step}: {cls} — {str(ret)[:200]}")
                        else:
                            logger.info(f"[Startup] {step}: {ret if isinstance(ret, (dict, int)) else 'ok'}")
                        # Status terminal nivel='grupo' (alimenta idempotência cross-camada).
                        _le_step(cls, step, detalhes=f"{step} terminou {cls}: {str(ret)[:200]}")
                    except Exception as ex:
                        logger.error(f"[Startup] {step} lançou exception: {ex}")
                        _ciclo_errors.append(f"{step}: {str(ex)[:200]}")
                        _le_step("falha", step, motivo="exception", detalhes=str(ex)[:300])

                db = SessionLocal()
                try:
                    def _auto_concluir_startup():
                        from app.services.event_status_service import auto_concluir_eventos_passados
                        return auto_concluir_eventos_passados(db)
                    _run_step_startup("auto_concluir_eventos_passados", _auto_concluir_startup)
                    _run_step_startup("snapshot_diario_batch", lambda: snapshot_diario_batch(db))
                    _run_step_startup("rebuild_rolling_grupos_batch", lambda: rebuild_rolling_grupos_batch(db))
                    _run_step_startup("consolidar_curvas_historicas_batch", lambda: consolidar_curvas_historicas_batch(db))
                    _run_step_startup("sincronizar_hoje_batch", lambda: sincronizar_hoje_batch(db))
                    _run_step_startup("sincronizar_margem_bundle_rev_batch", lambda: sincronizar_margem_bundle_rev_batch(db))
                    _run_step_startup("sincronizar_detalhe_eventos_batch", lambda: sincronizar_detalhe_eventos_batch(db))
                    logger.info("Startup snapshot consolidation completed")
                finally:
                    db.close()
                # Pre-warm persisted event detail snapshots so first click is instant
                try:
                    from app.services.event_detail_snapshot_service import refresh_active_event_details
                    refresh_active_event_details()
                except Exception as _e_eds:
                    logger.warning(f"[Startup] refresh_active_event_details failed: {_e_eds}")
                    _ciclo_errors.append(f"event_details: {str(_e_eds)[:200]}")
            except Exception as e:
                logger.error(f"Startup snapshot consolidation failed: {e}")
                _ciclo_errors.append(f"outer: {str(e)[:200]}")
                _ciclo_terminal_status = "falha"
            finally:
                # Se _force_consolidation_catchup foi True, fecha o ciclo logado
                # no startup (camadas 2/3 dependem desse status terminal).
                if _catchup_ciclo_id:
                    if _ciclo_errors and _ciclo_terminal_status != "falha":
                        _ciclo_terminal_status = "parcial"
                    try:
                        from app.services.sync_log_service import log_evento as _le_end
                        _le_end(
                            _catchup_ciclo_id,
                            "consolidacao_diaria_04h",
                            _ciclo_terminal_status,
                            nivel="ciclo",
                            detalhes=(f"Startup catch-up terminou: erros={len(_ciclo_errors)}. "
                                      f"{' | '.join(_ciclo_errors)[:500] if _ciclo_errors else 'sem erros'}"),
                        )
                        logger.info(f"[Startup] Ciclo catch-up {_catchup_ciclo_id} fechado como '{_ciclo_terminal_status}'")
                    except Exception as _le_end_err:
                        logger.warning(f"[Startup] Falha ao fechar ciclo catch-up: {_le_end_err}")
                # Libera advisory lock cross-process — SEMPRE, mesmo em erro.
                # Cobre tanto _catchup_lock_conn (catch-up forçado) quanto
                # _local_lock_conn (startup normal com snapshot stale).
                _lock_to_release = _catchup_lock_conn or _local_lock_conn
                if _lock_to_release is not None:
                    try:
                        from app.services.sync_log_service import release_consolidation_lock as _rel_end
                        _rel_end(_lock_to_release)
                        logger.info("[Startup] Advisory lock da consolidação liberado.")
                    except Exception as _rel_err:
                        logger.warning(f"[Startup] Falha ao liberar advisory lock: {_rel_err}")

        snapshot_thread = threading.Thread(target=_run_snapshot_consolidation, daemon=True, name="startup-snapshot")
        if not ENABLE_BACKGROUND_MAGENTO_SYNC:
            logger.info("[Startup] snapshot_consolidation SKIPPED (ENABLE_BACKGROUND_MAGENTO_SYNC=false)")
        elif _force_consolidation_catchup:
            logger.warning("[Startup] Catch-up reforçado: rodando consolidação completa no startup (job 02h BRT não rodou nas últimas 24h)")
            snapshot_thread.start()
        elif not _snapshot_is_fresh:
            snapshot_thread.start()
        else:
            # Snapshots are fresh — skip the heavy consolidation, but ALWAYS run
            # sincronizar_hoje_batch in background to guarantee TODAY's data exists.
            # The "freshness" check only verifies that some snapshot was updated recently,
            # not that today's date has rows. Without this, after a restart users may see
            # zero inscritos until the 30-min scheduler tick or a manual "Sincronizar Hoje".
            def _run_sync_hoje_only():
                try:
                    from app.core.database import SessionLocal as _SyncSL
                    from app.services.snapshot_service import sincronizar_hoje_batch as _sync_hoje
                    import time as _stime
                    logger.info("[Startup] Snapshots fresh — running sincronizar_hoje_batch only (guarantees today's data)")
                    _sdb = _SyncSL()
                    try:
                        _count = _sync_hoje(_sdb)
                        set_last_sync_hoje(_stime.time())
                        logger.info(f"[Startup] sincronizar_hoje_batch completed: {_count} groups synced for today")
                    finally:
                        _sdb.close()
                    # Pre-warm persisted event detail snapshots so first click is instant
                    try:
                        from app.services.event_detail_snapshot_service import refresh_active_event_details as _refr
                        _refr()
                    except Exception as _e_eds2:
                        logger.warning(f"[Startup] refresh_active_event_details failed: {_e_eds2}")
                except Exception as _e_sh:
                    logger.error(f"[Startup] sincronizar_hoje_batch failed: {_e_sh}")
            snapshot_thread = threading.Thread(target=_run_sync_hoje_only, daemon=True, name="startup-sync-hoje")
            snapshot_thread.start()

        # Dispara o sync de margem_bundle_rev_snapshot em background quando a tabela
        # estiver vazia OU desatualizada (> 25h), independentemente da freshness dos
        # demais snapshots. Sem este gatilho, restarts frequentes podem manter o
        # snapshot antigo por dias (o agendamento das 04:00 BRT não fira se a
        # instância for substituída antes desse horário), forçando o detalhe do
        # evento a cair em queries ao vivo no Magento (timeout) e exibir o aviso
        # "Dados do Magento indisponíveis" na Análise de Margem.
        def _maybe_sync_margem_rev():
            try:
                from app.core.database import SessionLocal as _SL2
                from app.models.vendas_snapshot import MargemBundleRevSnapshot as _MBR2
                from app.models.kit_config import KitConfig as _KC2
                from app.services.snapshot_service import sincronizar_margem_bundle_rev_batch as _smrb
                from sqlalchemy import func as _sfunc2
                from datetime import datetime as _dt_m, timezone as _tz_m
                _db2 = _SL2()
                try:
                    _total = _db2.query(_MBR2).count()
                    _empty = _total == 0
                    _stale = False
                    _low_coverage = False
                    _age_h = None
                    if not _empty:
                        # Idade considerada pelo consumidor em routes/marketing.py
                        # (_SNAP_MAX_AGE_H = 25). Se o snapshot mais novo já passou
                        # desse limite, o fallback PostgreSQL não é usado e o detalhe
                        # do evento cai em queries ao vivo no Magento (frequentemente
                        # timeout). Disparamos o sync para reabilitar o fallback.
                        _MAX_AGE_H = 25
                        _newest_ts = _db2.query(_sfunc2.max(_MBR2.calculado_em)).scalar()
                        if _newest_ts is not None:
                            if _newest_ts.tzinfo is None:
                                _newest_ts = _newest_ts.replace(tzinfo=_tz_m.utc)
                            _age_h = (_dt_m.now(_tz_m.utc) - _newest_ts).total_seconds() / 3600
                            _stale = _age_h > _MAX_AGE_H

                        # Cobertura: checamos se todos os bundles esperados (kit_config)
                        # têm uma entrada no snapshot. MAX(calculado_em) reporta "fresco"
                        # mesmo que o batch tenha sido interrompido no meio — bundles
                        # processados depois da interrupção nunca são gravados e sempre
                        # caem na query ao vivo do Magento (timeout de 47s).
                        # Critério: se < 85% dos bundles estão cobertos, re-sync.
                        if not _stale:
                            try:
                                _expected = _db2.query(
                                    _sfunc2.count(_sfunc2.distinct(_KC2.bundle_entity_id))
                                ).filter(_KC2.tipo_kit.isnot(None)).scalar() or 0
                                _coverage = _total / _expected if _expected > 0 else 1.0
                                if _coverage < 0.85:
                                    _low_coverage = True
                                    logger.warning(
                                        f"[Startup] margem_bundle_rev_snapshot cobertura baixa "
                                        f"({_total}/{_expected} = {_coverage:.0%}) — disparando sync"
                                    )
                            except Exception as _cov_err:
                                logger.warning(f"[Startup] Erro ao checar cobertura de bundles: {_cov_err}")

                    # COOLDOWN ANTI-LOOP (Maio/2026): bundles antigos sem orders
                    # nos últimos 2 anos no Magento NUNCA entram no snapshot (query
                    # retorna vazio → não há UPSERT). Cobertura fica em ~65%
                    # permanentemente, então _low_coverage dispara em TODO restart,
                    # martelando o Magento com 20+ batches a cada subida do app.
                    # Persist-zero (no snapshot_service.py) cura a causa-raiz, mas
                    # o cooldown é defesa em profundidade: se persist-zero falhar
                    # por qualquer motivo, não martelamos o Magento mais de 1x a
                    # cada 6h por restart. Para sync por "vazio" ou "desatualizado"
                    # o gatilho continua imediato — só a heurística de cobertura
                    # respeita o cooldown.
                    _COVERAGE_RESYNC_COOLDOWN_H = 6
                    _cov_in_cooldown = (
                        _low_coverage
                        and _age_h is not None
                        and _age_h < _COVERAGE_RESYNC_COOLDOWN_H
                    )
                    if _cov_in_cooldown:
                        logger.info(
                            f"[Startup] margem_bundle_rev_snapshot cobertura baixa MAS "
                            f"último sync há {_age_h:.1f}h (< {_COVERAGE_RESYNC_COOLDOWN_H}h cooldown) "
                            f"— sync de cobertura ignorado (anti-loop)"
                        )
                    should_run = _empty or _stale or (_low_coverage and not _cov_in_cooldown)
                    if should_run:
                        _motivo = (
                            "vazio" if _empty
                            else f"cobertura baixa ({_total} bundles no snapshot)"
                            if _low_coverage
                            else f"desatualizado ({_age_h:.1f}h > 25h)"
                        )
                        logger.info(f"[Startup] margem_bundle_rev_snapshot {_motivo} — disparando sync em background")
                        result = _smrb(_db2)
                        logger.info(f"[Startup] margem_bundle_rev_snapshot sync: {result}")
                    elif not _cov_in_cooldown:
                        logger.info(f"[Startup] margem_bundle_rev_snapshot fresco ({_age_h:.1f}h, cobertura OK) — sync ignorado")
                finally:
                    _db2.close()
            except Exception as _e_m:
                logger.error(f"[Startup] Erro no sync de margem_bundle_rev_snapshot: {_e_m}")

        _margem_thread = threading.Thread(target=_maybe_sync_margem_rev, daemon=True, name="startup-margem-rev-sync")
        _margem_thread.start()

        # Loop dedicado: sincroniza inscritos de hoje a cada HOJE_SYNC_INTERVAL_HOURS
        # (padrão 2 h), somente se não houve sync recente — automático ou manual.
        if ENABLE_BACKGROUND_MAGENTO_SYNC:
            _start_hoje_sync_loop()
        else:
            logger.info("[Startup] hoje_sync_loop NOT started (ENABLE_BACKGROUND_MAGENTO_SYNC=false)")

        # Decide whether to run a full warmup on startup.
        # If targeted warmup resolved all gaps (gap count == 0 now), skip the full warmup.
        # If there are still gaps AND snapshots are fresh, run warmup immediately (no wait).
        # If gaps remain AND snapshots are stale, wait for snapshot before warmup to avoid
        # a race where Phase 1d reads snapshot data before it's rebuilt.
        _gap_result = get_gap_detection_result()
        _gap_count = len(_gap_result.get("missing_tier1_events", [])) + len(_gap_result.get("stale_tier1_events", []))

        if not ENABLE_BACKGROUND_MAGENTO_SYNC:
            logger.info("[Startup] full_cache_warmup + ISC refresh SKIPPED (ENABLE_BACKGROUND_MAGENTO_SYNC=false)")
        elif _gap_count == 0:
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

        # Mapeamento de Kits: garante snapshot persistido pronto na primeira
        # abertura da tela /admin/kit-config. Roda em background para não
        # atrasar startup; respeita ENABLE_BACKGROUND_MAGENTO_SYNC.
        if ENABLE_BACKGROUND_MAGENTO_SYNC:
            def _bg_kit_snapshot_warmup():
                try:
                    from app.core.database import SessionLocal as _SL
                    from app.services.kit_snapshot_service import rebuild_kit_snapshot, snapshot_is_stale
                    _db = _SL()
                    try:
                        if snapshot_is_stale(_db, max_age_hours=24):
                            logger.info("[Startup] kit_mapping_snapshot vazio/stale — rebuild em background")
                            r = rebuild_kit_snapshot(_db)
                            logger.info(f"[Startup] kit_snapshot rebuild concluido: status={r['status']} total={r['total_atual']} novos={r['novos']} alterados={r['alterados']} sem_mudanca={r['sem_mudanca']} removidos={r['removidos']}")
                        else:
                            logger.info("[Startup] kit_mapping_snapshot fresco — rebuild pulado")
                    finally:
                        _db.close()
                except Exception as e:
                    logger.warning(f"[Startup] kit_snapshot warmup falhou: {e}")
            import threading as _kt
            _kt.Thread(target=_bg_kit_snapshot_warmup, daemon=True, name="startup-kit-snapshot").start()
        else:
            logger.info("[Startup] kit_snapshot warmup SKIPPED (ENABLE_BACKGROUND_MAGENTO_SYNC=false)")

        logger.info("=== All background startup tasks completed ===")

        # Pré-aquece cache de receita Magento por bundle em background (não bloqueia startup).
        # Garante que a primeira requisição de margem para qualquer evento ativo
        # responda a partir do cache em memória, não espere 20-55s na query de receita.
        # Gates (precisam dos DOIS estarem true):
        # - ENABLE_BACKGROUND_MAGENTO_SYNC (master switch): em dev fica off para
        #   nunca tocar Magento em background. Mesmo gate de scheduler/hoje-sync.
        # - ENABLE_REVENUE_PREWARM (default true): permite desligar SÓ o prewarm
        #   em PROD mesmo com o restante do background ativo (corta ~150 queries
        #   durante o deploy; primeiro acesso a cada evento recarrega lazy).
        if not ENABLE_BACKGROUND_MAGENTO_SYNC:
            logger.info("[Startup] RevenuePrewarm SKIPPED (ENABLE_BACKGROUND_MAGENTO_SYNC=false)")
        elif os.getenv("ENABLE_REVENUE_PREWARM", "true").lower() in ("true", "1", "yes"):
            _prewarm_revenue_cache()
        else:
            logger.info("[Startup] RevenuePrewarm SKIPPED (ENABLE_REVENUE_PREWARM=false)")

        # Trigger proactive insights generation on startup (non-blocking, best-effort).
        # Gateado por ENABLE_BACKGROUND_MAGENTO_SYNC: o job dispara ISC com
        # force_refresh, que vai ao Magento (kit_cost_batch etc.). Em dev fica off.
        if not ENABLE_BACKGROUND_MAGENTO_SYNC:
            logger.info("[Startup] Nori insights job SKIPPED (ENABLE_BACKGROUND_MAGENTO_SYNC=false)")
        else:
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

        # Sync diário do diretório Microsoft Entra ID (03:00 BRT). Independe do
        # gate de Magento (não usa SSH). Sai silenciosamente se SSO não estiver
        # configurado.
        def _schedule_daily_ms_directory_sync():
            from zoneinfo import ZoneInfo as _ZI
            from datetime import datetime as _dt, timedelta as _td
            _brt = _ZI('America/Sao_Paulo')
            _now = _dt.now(_brt)
            _target = _now.replace(hour=3, minute=0, second=0, microsecond=0)
            if _now >= _target:
                _target += _td(days=1)
            _delay = (_target - _now).total_seconds()
            logger.info(f"[MSDirSync] Daily timer: next run at {_target.isoformat()} BRT (in {_delay/3600:.1f}h)")

            def _run_and_reschedule():
                _scheduled_ms_directory_sync()
                _schedule_daily_ms_directory_sync()

            _timer = threading.Timer(_delay, _run_and_reschedule)
            _timer.daemon = True
            _timer.name = "ms-directory-sync-daily-timer"
            _timer.start()
            return _timer

        _schedule_daily_ms_directory_sync()

        # Loop do resumo diário de pendências por e-mail (independente do Magento gate).
        threading.Thread(target=_projecao_notif_loop, daemon=True, name="projecao-notif-loop").start()

        # Câmbio USD/BRL pre-warm (movido pra background pra não bloquear startup do deploy).
        try:
            from app.api.routes.cotacoes import _cambio_cache
            import httpx as _hx, time as _t
            _taxa = 0
            try:
                with _hx.Client(timeout=10) as _cli:
                    _r = _cli.get("https://economia.awesomeapi.com.br/json/last/USD-BRL")
                    if _r.status_code == 200:
                        _d = _r.json().get("USDBRL", {})
                        _taxa = float(_d.get("bid", 0))
                        if _taxa > 0:
                            _cambio_cache["taxa"] = _taxa
                            _cambio_cache["variacao"] = float(_d.get("varBid", 0))
                            _cambio_cache["data"] = _d.get("create_date", "")
                            _cambio_cache["ts"] = _t.time()
            except Exception:
                pass
            if _taxa == 0:
                try:
                    with _hx.Client(timeout=10) as _cli:
                        _r2 = _cli.get("https://open.er-api.com/v6/latest/USD")
                        if _r2.status_code == 200:
                            _brl = float(_r2.json().get("rates", {}).get("BRL", 0))
                            if _brl > 0:
                                _cambio_cache["taxa"] = round(_brl, 4)
                                _cambio_cache["variacao"] = 0
                                _cambio_cache["data"] = _r2.json().get("time_last_update_utc", "")
                                _cambio_cache["ts"] = _t.time()
                                _taxa = _brl
                except Exception:
                    pass
            if _taxa > 0:
                logger.info(f"[Startup-BG] Câmbio cache pre-warmed: USD/BRL = {round(_taxa, 4)}")
            else:
                logger.warning("[Startup-BG] Câmbio pre-warm: both APIs failed")
        except Exception as _ce:
            logger.warning(f"[Startup-BG] Câmbio pre-warm failed (non-fatal): {_ce}")

    # Warmup de cadastros JÁ é feito dentro de _all_background_init (linhas ~1576-1585).
    # Removida a chamada síncrona duplicada que bloqueava o startup do deploy.
    init_thread = threading.Thread(target=_all_background_init, daemon=True, name="startup-bg-init")
    init_thread.start()

    logger.info("=== Server ready to accept requests (background init running) ===")

    yield
    cache_scheduler.stop()
    stop_ssh_watchdog()
    close_ssh_tunnel()

app = FastAPI(title="DW Financeiro - Eventos", version="1.0.0", lifespan=lifespan)

from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

@app.exception_handler(RequestValidationError)
async def _log_validation_error(request, exc):
    try:
        body = await request.body()
        body_text = body.decode('utf-8', errors='replace')[:2000]
    except Exception:
        body_text = '<unavailable>'
    logger.warning(
        "[ValidationError] %s %s — errors=%s body=%s",
        request.method, request.url.path, exc.errors(), body_text,
    )
    return JSONResponse(status_code=422, content={"detail": exc.errors()})

from app.core.config import settings as app_settings

cors_origins = [origin.strip() for origin in app_settings.CORS_ORIGINS.split(",") if origin.strip()]
cors_origin_regex = r"https://.*\.replit\.(app|dev)"

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_origin_regex=cors_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Data-Stale", "X-Kit-Source", "X-Kit-Stale"],
)

from app.core.rate_limit import RateLimitMiddleware
app.add_middleware(RateLimitMiddleware, secret_key=app_settings.SECRET_KEY, algorithm=app_settings.ALGORITHM)

# Compressão gzip para todas as respostas (bundles JS/CSS do frontend e JSON da API).
# Os assets do frontend chegam a >1MB sem compressão; com gzip caem ~3-4x, acelerando
# o carregamento inicial e a navegação entre telas. minimum_size evita comprimir
# payloads minúsculos onde o overhead não compensa.
app.add_middleware(GZipMiddleware, minimum_size=1024)

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
app.include_router(detalhe_eventos.router, tags=["Detalhe Eventos"])
app.include_router(perfil_acesso.router, prefix="/api", tags=["Perfis de Acesso"])
app.include_router(distancias.router, prefix="/api", tags=["Distâncias"])
app.include_router(cotacoes.router, prefix="/api", tags=["Cotações & Importação"])
app.include_router(admin.router, tags=["Admin"])
app.include_router(kit_config.router, tags=["Kit Config"])
app.include_router(detalhe_alias.router, tags=["Detalhe Dimensao Alias"])
app.include_router(profile.router, prefix="/api", tags=["Perfil"])
app.include_router(projecao.router, prefix="/api", tags=["Projeção de Inscritos"])

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

_backend_dir = os.path.dirname(os.path.abspath(__file__))
_backend_static = os.path.join(_backend_dir, "static")
_workspace_frontend_dist = os.path.join(os.path.dirname(_backend_dir), "frontend", "dist")
frontend_dist = _backend_static if os.path.isdir(_backend_static) and os.path.isfile(os.path.join(_backend_static, "index.html")) else _workspace_frontend_dist
class ImmutableStaticFiles(StaticFiles):
    """Serve os assets com hash no nome (imutáveis) com cache de 1 ano.

    Como o Vite coloca um hash de conteúdo no nome de cada arquivo, qualquer
    mudança gera um nome novo. Marcar como `immutable` elimina as revalidações
    condicionais (304) a cada navegação entre telas, que adicionavam um
    round-trip por arquivo."""

    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        if response.status_code == 200:
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response


if os.path.isdir(frontend_dist):
    assets_dir = os.path.join(frontend_dist, "assets")
    if os.path.isdir(assets_dir):
        app.mount("/assets", ImmutableStaticFiles(directory=assets_dir), name="static-assets")

    # Arquivos que NUNCA podem ser cacheados pelo navegador, senão o usuário
    # fica preso numa versão antiga do app:
    #  - sw.js: se cacheado, o navegador não detecta um service worker novo e a
    #    auto-atualização (registerType: 'autoUpdate') nunca dispara.
    #  - index.html: a "casca" do SPA que aponta para os bundles JS com hash.
    #  - *.webmanifest / manifest.webmanifest: metadados do PWA.
    # Os assets sob /assets têm hash no nome (imutáveis) e continuam cacheáveis.
    _NO_STORE_HEADERS = {
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Pragma": "no-cache",
        "Expires": "0",
    }

    def _is_no_store(name: str) -> bool:
        base = os.path.basename(name).lower()
        return (
            base == "index.html"
            or base == "sw.js"
            or base.endswith(".webmanifest")
            or base == "registersw.js"
        )

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        if full_path.startswith("api/"):
            return {"detail": "Not Found"}
        file_path = os.path.join(frontend_dist, full_path)
        if full_path and os.path.isfile(file_path):
            headers = _NO_STORE_HEADERS if _is_no_store(full_path) else None
            return FileResponse(file_path, headers=headers)
        index_path = os.path.join(frontend_dist, "index.html")
        if os.path.isfile(index_path):
            return FileResponse(index_path, headers=_NO_STORE_HEADERS)
        return {"detail": "Not Found"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
