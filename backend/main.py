from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy import text
from contextlib import asynccontextmanager
import os
import time
from app.core.database import engine, Base, init_mysql_connections, engine_ativo, init_ssh_tunnel, close_ssh_tunnel, engine_ssh
from app.api.routes import auth, users, centros_custo, projetos, categorias_atletas, dashboard, nori, tarefas, cadastros, atletas_externos, magento, inscricoes_consolidado, marketing, sku_mappings, perfil_acesso, distancias, cotacoes, admin, kit_config
from app.core.cache import (
    cache_scheduler, warm_all_caches_from_db,
    set_last_full_refresh, set_full_refresh_in_progress, 
    register_full_warmup_fn,
    isc_cache, event_detail_cache, curva_cache, medias_cache,
    _full_refresh_lock,
    set_warmup_metadata_cache, clear_warmup_metadata_cache
)
import app.core.cache as _cache_module
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def _scheduled_isc_refresh():
    from app.core.database import SessionLocal
    db = None
    try:
        db = SessionLocal()
        marketing.fetch_isc_pricing_data(db=db, force_refresh=True)
        logger.info("Scheduled ISC cache refresh completed successfully")
    except Exception as e:
        logger.error(f"Scheduled ISC cache refresh failed: {e}")
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
        _build_sku_to_grupo_map,
        set_warmup_daily_cache, clear_warmup_daily_cache,
        _fetch_daily_sales_ativo_by_ids_grouped, _fetch_daily_sales_magento_by_ids_grouped,
        _fetch_category_sales_ativo_by_ids_grouped, _fetch_category_sales_magento_by_ids_grouped,
        register_warmup_thread, unregister_warmup_thread,
        _warmup_daily_cache, _warmup_daily_cache_lock, daily_sales_cache,
        _hist_pattern_cache, _hist_pattern_cache_lock
    )
    from concurrent.futures import ThreadPoolExecutor, as_completed
    import threading

    WARMUP_WORKERS = 8
    TIER1_D_MINUS_THRESHOLD = 60

    with _full_refresh_lock:
        if _cache_module._full_refresh_in_progress:
            logger.info("Full cache warmup flag already set, proceeding")
        else:
            _cache_module._full_refresh_in_progress = True
    set_last_refresh_error(None)
    start = time.time()
    logger.info("=== FULL CACHE WARMUP STARTED ===")

    partial_warnings = []
    db = None
    try:
        db = SessionLocal()
        ano = datetime.now().year

        daily_sales_cache.invalidate(f"{ano}_prefetch_daily")
        with _hist_pattern_cache_lock:
            _hist_pattern_cache.clear()
        logger.info(f"[Warmup] Invalidated daily_sales + hist_pattern caches for {ano}")

        set_warmup_progress(1, "Atualizando dados de inscrições", 0, 4)
        logger.info("[Warmup 1/4] Refreshing ISC pricing data...")
        try:
            fetch_isc_pricing_data(db=db, force_refresh=True)
            logger.info("[Warmup 1/4] ISC pricing data refreshed")
            update_warmup_sub_progress(1)
        except Exception as e:
            logger.error(f"[Warmup 1/4] ISC pricing data FAILED: {e}")
            partial_warnings.append(f"Dados de inscrições parciais: {str(e)[:100]}")

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
        all_ativo_ids = []
        all_magento_ids = []

        for cad in all_cadastros:
            if not cad.projeto_id:
                continue
            projeto = proj_by_id.get(cad.projeto_id)
            if not projeto or not projeto.data_evento:
                continue

            d_minus = calculate_d_minus(projeto.data_evento)
            if d_minus <= 0:
                continue

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

        for m in all_sku_mappings:
            if m.id_externo:
                ext_id = str(m.id_externo)
                if m.fonte == 'ATIVO':
                    all_ativo_ids.append(ext_id)
                elif m.fonte == 'MAGENTO':
                    all_magento_ids.append(ext_id)

        all_ativo_ids = list(set(all_ativo_ids))
        all_magento_ids = list(set(all_magento_ids))
        active_evento_ids = tier1_evento_ids + tier2_evento_ids
        logger.info(f"[Warmup] Found {len(active_evento_ids)} active events: Tier 1 (d-≤{TIER1_D_MINUS_THRESHOLD}): {len(tier1_evento_ids)}, Tier 2 (d->{TIER1_D_MINUS_THRESHOLD}): {len(tier2_evento_ids)}")
        logger.info(f"[Warmup 1/4] Pre-fetching daily sales: {len(all_ativo_ids)} Ativo IDs, {len(all_magento_ids)} Magento IDs")

        ativo_grouped = {}
        magento_grouped = {}
        cat_ativo_grouped = {}
        cat_magento_grouped = {}

        with ThreadPoolExecutor(max_workers=4, thread_name_prefix="prefetch") as pf_executor:
            pf_futures = {}
            if all_ativo_ids:
                pf_futures["ativo_daily"] = pf_executor.submit(_fetch_daily_sales_ativo_by_ids_grouped, all_ativo_ids)
                pf_futures["ativo_cat"] = pf_executor.submit(_fetch_category_sales_ativo_by_ids_grouped, all_ativo_ids)
            if all_magento_ids:
                pf_futures["magento_daily"] = pf_executor.submit(_fetch_daily_sales_magento_by_ids_grouped, all_magento_ids)
                pf_futures["magento_cat"] = pf_executor.submit(_fetch_category_sales_magento_by_ids_grouped, all_magento_ids)

            for name, fut in pf_futures.items():
                try:
                    result = fut.result(timeout=120)
                    if name == "ativo_daily":
                        ativo_grouped = result
                        logger.info(f"[Warmup 1/4] Ativo daily pre-fetch: {len(result)} events")
                    elif name == "magento_daily":
                        magento_grouped = result
                        logger.info(f"[Warmup 1/4] Magento daily pre-fetch: {len(result)} events")
                    elif name == "ativo_cat":
                        cat_ativo_grouped = result
                        logger.info(f"[Warmup 1/4] Ativo category pre-fetch: {len(result)} events")
                    elif name == "magento_cat":
                        cat_magento_grouped = result
                        logger.info(f"[Warmup 1/4] Magento category pre-fetch: {len(result)} events")
                except Exception as e:
                    logger.error(f"[Warmup 1/4] Pre-fetch {name} FAILED: {e}")
                    partial_warnings.append(f"Pre-fetch {name} parcial: {str(e)[:80]}")

        set_warmup_daily_cache(ativo_grouped, magento_grouped, cat_ativo_grouped, cat_magento_grouped)
        update_warmup_sub_progress(4)
        logger.info(f"[Warmup 1/4] Phase 1 complete in {time.time()-start:.1f}s")

        from app.api.routes.marketing import (
            get_marketing_event_by_id,
            get_curva_comparativa_evento,
            get_sales_averages,
            get_evento_insights,
            get_marketing_events
        )

        priority_fns = [
            ("detalhes", lambda eid, a, d: get_marketing_event_by_id(evento_id=eid, ano=a, force_refresh=True, db=d, current_user=None)),
        ]
        secondary_fns = [
            ("curvas", lambda eid, a, d: get_curva_comparativa_evento(evento_id=eid, ano=a, force_refresh=True, db=d, current_user=None)),
            ("medias", lambda eid, a, d: get_sales_averages(evento_id=eid, periodo=30, ano=a, force_refresh=True, db=d, current_user=None)),
            ("insights", lambda eid, a, d: get_evento_insights(evento_id=eid, ano=a, force_refresh=True, db=d, current_user=None)),
        ]

        tier1_full_tasks = len(tier1_evento_ids) * 4
        tier2_detail_tasks = len(tier2_evento_ids)
        total_tasks = tier1_full_tasks + tier2_detail_tasks
        set_warmup_progress(2, "Processando eventos", 0, total_tasks)
        logger.info(f"[Warmup 2/4] Processing {total_tasks} tasks — Tier1: {tier1_full_tasks} (full), Tier2: {tier2_detail_tasks} (details only)")

        completed_tasks = 0
        task_counter_lock = threading.Lock()
        step_counts = {"detalhes": 0, "curvas": 0, "medias": 0, "insights": 0}

        def _do_task(eid, step_name, step_fn):
            nonlocal completed_tasks
            tid = threading.current_thread().ident
            register_warmup_thread(tid)
            local_db = SessionLocal()
            try:
                step_fn(eid, ano, local_db)
                with task_counter_lock:
                    completed_tasks += 1
                    step_counts[step_name] += 1
                    update_warmup_sub_progress(completed_tasks)
            except Exception as e:
                with task_counter_lock:
                    completed_tasks += 1
                    update_warmup_sub_progress(completed_tasks)
                logger.warning(f"[Warmup] Failed {step_name} for {eid}: {e}")
            finally:
                unregister_warmup_thread(tid)
                try:
                    local_db.close()
                except Exception:
                    pass

        phase2_start = time.time()
        with ThreadPoolExecutor(max_workers=WARMUP_WORKERS, thread_name_prefix="warmup") as executor:
            all_detail_futures = []
            for eid in active_evento_ids:
                for step_name, step_fn in priority_fns:
                    all_detail_futures.append(executor.submit(_do_task, eid, step_name, step_fn))
            for f in as_completed(all_detail_futures):
                try:
                    f.result()
                except Exception:
                    pass
            details_elapsed = time.time() - phase2_start
            logger.info(f"[Warmup 2/4] All detalhes done ({step_counts['detalhes']}) in {details_elapsed:.1f}s, starting Tier 1 secondary...")

            secondary_futures = []
            for eid in tier1_evento_ids:
                for step_name, step_fn in secondary_fns:
                    secondary_futures.append(executor.submit(_do_task, eid, step_name, step_fn))
            for f in as_completed(secondary_futures):
                try:
                    f.result()
                except Exception:
                    pass

        logger.info(f"[Warmup 2/4] All tasks done: {step_counts}")

        set_warmup_progress(3, "Finalizando", 0, 1)

        try:
            with _warmup_daily_cache_lock:
                ativo_cache = _warmup_daily_cache.get("ativo", {})
                magento_cache = _warmup_daily_cache.get("magento", {})
            if ativo_cache or magento_cache:
                year_mappings = [m for m in all_sku_mappings if m.ano == ano]
                id_to_skus = {}
                for m in year_mappings:
                    if m.id_externo:
                        ext_id = str(m.id_externo)
                        if ext_id not in id_to_skus:
                            id_to_skus[ext_id] = set()
                        id_to_skus[ext_id].add(m.sku.upper().strip() if m.sku else "")
                sku_daily = {}
                for ext_id, daily in ativo_cache.items():
                    for sku in id_to_skus.get(str(ext_id), []):
                        if sku not in sku_daily:
                            sku_daily[sku] = {}
                        for d, qtd in daily.items():
                            sku_daily[sku][d] = sku_daily[sku].get(d, 0) + qtd
                for ext_id, daily in magento_cache.items():
                    for sku in id_to_skus.get(str(ext_id), []):
                        if sku not in sku_daily:
                            sku_daily[sku] = {}
                        for d, qtd in daily.items():
                            sku_daily[sku][d] = sku_daily[sku].get(d, 0) + qtd
                daily_sales_cache.set(f"{ano}_prefetch_daily", sku_daily)
                logger.info(f"[Warmup 3/4] Pre-populated daily_sales_cache with {len(sku_daily)} SKUs from warmup data")
        except Exception as e:
            logger.warning(f"[Warmup 3/4] Failed to pre-populate daily_sales_cache: {e}")

        clear_warmup_daily_cache()
        clear_warmup_metadata_cache()

        from app.api.routes.marketing import eventos_list_cache as _evt_list_cache
        _evt_list_cache.invalidate_all()
        logger.info("[Warmup 3/4] Caches cleaned, eventos_list invalidated")

        try:
            logger.info(f"[Warmup 3/4] Populating default dashboard cache keys")
            _warmup_db = SessionLocal()
            try:
                get_marketing_events(ano=ano, status="active", categoria=None, busca=None, force_refresh=True, db=_warmup_db, current_user=None)
                logger.info(f"[Warmup 3/4] Default dashboard cache key '{ano}_active_all_' populated")
                get_marketing_events(ano=ano, status=None, categoria=None, busca=None, force_refresh=True, db=_warmup_db, current_user=None)
                logger.info(f"[Warmup 3/4] Dashboard cache key '{ano}_all_all_' populated")
            finally:
                _warmup_db.close()
        except Exception as e:
            logger.warning(f"[Warmup 3/4] Failed to populate default dashboard cache: {e}")

        set_last_full_refresh(time.time())
        elapsed = time.time() - start
        logger.info(f"=== FULL CACHE WARMUP COMPLETED in {elapsed:.1f}s ===")
        logger.info(f"    Tier1: {len(tier1_evento_ids)} events (full), Tier2: {len(tier2_evento_ids)} events (details only)")
        logger.info(f"    Details: {step_counts['detalhes']}, Curvas: {step_counts['curvas']}, Médias: {step_counts['medias']}, Insights: {step_counts['insights']}")
        update_warmup_sub_progress(1)

        if partial_warnings:
            set_last_refresh_error("Atualização concluída com avisos: " + "; ".join(partial_warnings))

    except Exception as e:
        logger.error(f"Full cache warmup failed: {e}", exc_info=True)
        set_last_refresh_error(f"Falha na atualização dos dados: {str(e)}")
    finally:
        clear_warmup_daily_cache()
        clear_warmup_metadata_cache()
        set_full_refresh_in_progress(False)
        if db:
            try:
                db.close()
            except Exception:
                pass

def _startup_resync_projetos():
    from app.core.database import SessionLocal
    from app.models.cadastro_evento import CadastroEvento
    from app.api.routes.cadastros import _sync_dim_projeto
    try:
        db = SessionLocal()
        cadastros = db.query(CadastroEvento).all()
        synced = 0
        for c in cadastros:
            try:
                _sync_dim_projeto(db, c)
                synced += 1
            except Exception as e:
                logger.warning(f"Resync failed for cadastro {c.id} ({c.nome}): {e}")
        db.commit()
        logger.info(f"Startup resync: {synced}/{len(cadastros)} cadastros synced to dim_projeto")
        db.close()
    except Exception as e:
        logger.error(f"Startup resync failed: {e}")

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
        ]
        kit_basico_idx = [
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_kit_basico_per_evento ON kit_config (id_evento) WHERE is_kit_basico = TRUE",
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
    if engine:
        Base.metadata.create_all(bind=engine)
    _run_column_migrations()
    seed_admin_user()
    _seed_kit_config()

    register_full_warmup_fn(_full_cache_warmup)
    cache_scheduler.register(_scheduled_isc_refresh)
    cache_scheduler.register_full_refresh(_full_cache_warmup)

    import threading

    def _startup_background_init():
        try:
            _startup_resync_projetos()
        except Exception as e:
            logger.error(f"Startup resync projetos failed: {e}")

        try:
            init_mysql_connections()
        except Exception as e:
            logger.error(f"MySQL connections init failed: {e}")

        try:
            init_ssh_tunnel()
        except Exception as e:
            logger.error(f"SSH tunnel init failed: {e}")

        try:
            logger.info("Loading persistent cache from PostgreSQL...")
            warm_all_caches_from_db()
            logger.info("Persistent cache loaded - users will see cached data immediately")
        except Exception as e:
            logger.error(f"Persistent cache warmup failed: {e}")

        cache_scheduler.start(interval=1800)
        logger.info("Cache auto-refresh scheduler started (30 min interval + daily 07:00 BRT)")

        try:
            from app.core.database import SessionLocal
            from app.services.snapshot_service import snapshot_diario_batch, consolidar_curvas_historicas_batch
            logger.info("Starting snapshot consolidation...")
            db = SessionLocal()
            try:
                snapshot_diario_batch(db)
                consolidar_curvas_historicas_batch(db)
                logger.info("Startup snapshot consolidation completed")
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Startup snapshot consolidation failed: {e}")

        logger.info("Starting full cache warmup in background...")
        try:
            _full_cache_warmup()
        except Exception as e:
            logger.error(f"Full cache warmup failed: {e}")

    init_thread = threading.Thread(target=_startup_background_init, daemon=True)
    init_thread.start()
    logger.info("Background initialization launched - server ready to accept requests")

    yield
    cache_scheduler.stop()
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
