from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy import text
from contextlib import asynccontextmanager
import os
import time
from app.core.database import engine, Base, init_mysql_connections, engine_ativo, init_ssh_tunnel, close_ssh_tunnel, engine_ssh
from app.api.routes import auth, users, centros_custo, projetos, categorias_atletas, dashboard, nori, tarefas, cadastros, atletas_externos, magento, inscricoes_consolidado, marketing, sku_mappings, perfil_acesso, distancias, cotacoes
from app.core.cache import (
    cache_scheduler, warm_all_caches_from_db,
    set_last_full_refresh, set_full_refresh_in_progress, 
    register_full_warmup_fn,
    isc_cache, event_detail_cache, curva_cache, medias_cache,
    _full_refresh_lock
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
    from app.core.cache import set_warmup_progress, set_last_refresh_error
    from datetime import datetime
    from app.models.cadastro_evento import CadastroEvento
    from app.models.dimensoes import DimProjeto, SkuMapping
    from app.api.routes.marketing import (
        fetch_isc_pricing_data, normalize_sku, calculate_d_minus,
        _build_sku_to_grupo_map
    )

    with _full_refresh_lock:
        if _cache_module._full_refresh_in_progress:
            logger.info("Full cache warmup flag already set, proceeding")
        else:
            _cache_module._full_refresh_in_progress = True
    set_last_refresh_error(None)
    start = time.time()
    logger.info("=== FULL CACHE WARMUP STARTED ===")

    db = None
    try:
        db = SessionLocal()
        ano = datetime.now().year

        set_warmup_progress(1, "Atualizando dados de inscrições")
        logger.info("[Warmup 1/5] Refreshing ISC pricing data...")
        fetch_isc_pricing_data(db=db, force_refresh=True)
        logger.info("[Warmup 1/5] ISC pricing data refreshed")

        cadastros_list = db.query(CadastroEvento).all()
        sku_to_grupo = _build_sku_to_grupo_map(db, ano)

        active_evento_ids = []
        grupo_names_seen = set()

        for cad in cadastros_list:
            if not cad.projeto_id:
                continue
            projeto = db.query(DimProjeto).filter(DimProjeto.id == cad.projeto_id).first()
            if not projeto or not projeto.data_evento:
                continue

            d_minus = calculate_d_minus(projeto.data_evento)
            if d_minus <= 0:
                continue

            sku_norm = normalize_sku(str(projeto.codigo)) if projeto.codigo else None
            grupo_nome = sku_to_grupo.get(sku_norm) if sku_norm else None

            if grupo_nome and grupo_nome not in grupo_names_seen:
                grupo_names_seen.add(grupo_nome)
                active_evento_ids.append(f"grp_{grupo_nome}")
            elif not grupo_nome:
                active_evento_ids.append(str(projeto.id))

        logger.info(f"[Warmup] Found {len(active_evento_ids)} active events to warm up")

        from app.api.routes.marketing import (
            get_marketing_event_by_id,
            get_curva_comparativa_evento,
            get_sales_averages,
            get_evento_insights
        )

        set_warmup_progress(2, "Detalhes dos eventos")
        logger.info("[Warmup 2/5] Warming event details...")
        warmed_details = 0
        for evento_id in active_evento_ids:
            try:
                get_marketing_event_by_id(
                    evento_id=evento_id, ano=ano, force_refresh=True, db=db,
                    current_user=None
                )
                warmed_details += 1
            except Exception as e:
                logger.warning(f"[Warmup] Failed to warm event detail for {evento_id}: {e}")
        logger.info(f"[Warmup 2/5] Warmed {warmed_details}/{len(active_evento_ids)} event details")

        set_warmup_progress(3, "Curvas comparativas")
        logger.info("[Warmup 3/5] Warming curva comparativa...")
        warmed_curvas = 0
        for evento_id in active_evento_ids:
            try:
                get_curva_comparativa_evento(
                    evento_id=evento_id, ano=ano, force_refresh=True, db=db,
                    current_user=None
                )
                warmed_curvas += 1
            except Exception as e:
                logger.warning(f"[Warmup] Failed to warm curva for {evento_id}: {e}")
        logger.info(f"[Warmup 3/5] Warmed {warmed_curvas}/{len(active_evento_ids)} curvas")

        set_warmup_progress(4, "Médias de vendas")
        logger.info("[Warmup 4/5] Warming medias de vendas...")
        warmed_medias = 0
        for evento_id in active_evento_ids:
            try:
                get_sales_averages(
                    evento_id=evento_id, periodo=30, ano=ano, force_refresh=True, db=db,
                    current_user=None
                )
                warmed_medias += 1
            except Exception as e:
                logger.warning(f"[Warmup] Failed to warm medias for {evento_id}: {e}")
        logger.info(f"[Warmup 4/5] Warmed {warmed_medias}/{len(active_evento_ids)} medias")

        set_warmup_progress(5, "Gerando insights")
        logger.info("[Warmup 5/5] Warming insights...")
        warmed_insights = 0
        for evento_id in active_evento_ids:
            try:
                get_evento_insights(
                    evento_id=evento_id, ano=ano, force_refresh=True, db=db,
                    current_user=None
                )
                warmed_insights += 1
            except Exception as e:
                logger.warning(f"[Warmup] Failed to warm insights for {evento_id}: {e}")
        logger.info(f"[Warmup 5/5] Warmed {warmed_insights}/{len(active_evento_ids)} insights")

        set_last_full_refresh(time.time())
        elapsed = time.time() - start
        logger.info(f"=== FULL CACHE WARMUP COMPLETED in {elapsed:.1f}s ===")
        logger.info(f"    Details: {warmed_details}, Curvas: {warmed_curvas}, Médias: {warmed_medias}, Insights: {warmed_insights}")

    except Exception as e:
        logger.error(f"Full cache warmup failed: {e}", exc_info=True)
        set_last_refresh_error(f"Falha na atualização dos dados: {str(e)}")
    finally:
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

def _run_column_migrations():
    from app.core.database import SessionLocal
    try:
        db = SessionLocal()
        migrations = [
            "ALTER TABLE cadastro_evento ADD COLUMN IF NOT EXISTS atletas_appai_pago INTEGER DEFAULT 0",
            "ALTER TABLE cadastro_evento ADD COLUMN IF NOT EXISTS atletas_appai_tkt_medio NUMERIC(10,2) DEFAULT 0",
            "ALTER TABLE evento_grupos ALTER COLUMN nome TYPE VARCHAR(200)",
            "ALTER TABLE sku_mappings ALTER COLUMN evento_grupo TYPE VARCHAR(200)",
        ]
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
    _startup_resync_projetos()
    init_mysql_connections()
    init_ssh_tunnel()

    logger.info("Loading persistent cache from PostgreSQL...")
    warm_all_caches_from_db()
    logger.info("Persistent cache loaded - users will see cached data immediately")

    register_full_warmup_fn(_full_cache_warmup)

    cache_scheduler.register(_scheduled_isc_refresh)
    cache_scheduler.register_full_refresh(_full_cache_warmup)
    cache_scheduler.start(interval=1800)
    logger.info("Cache auto-refresh scheduler started (30 min interval + daily 07:00 BRT)")

    import threading
    def _startup_full_warmup():
        logger.info("Starting full cache warmup in background...")
        _full_cache_warmup()
    warm_thread = threading.Thread(target=_startup_full_warmup, daemon=True)
    warm_thread.start()
    logger.info("Full cache warmup thread launched")

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
