from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from contextlib import asynccontextmanager
from app.core.database import engine, Base, init_mysql_connections, engine_ativo, init_ssh_tunnel, close_ssh_tunnel, engine_ssh
from app.api.routes import auth, users, centros_custo, contas, projetos, categorias_atletas, orcamento, projecao, realizado, atletas, atletas_satelite, dashboard, nori, tarefas, cadastros, atletas_externos, magento, inscricoes_consolidado, marketing, sku_mappings, perfil_acesso, distancias, cotacoes
from app.core.cache import cache_scheduler
import logging

logger = logging.getLogger(__name__)

def _scheduled_isc_refresh():
    from app.core.database import SessionLocal
    try:
        db = SessionLocal()
        marketing.fetch_isc_pricing_data(db=db, force_refresh=True)
        logger.info("Scheduled ISC cache refresh completed successfully")
        db.close()
    except Exception as e:
        logger.error(f"Scheduled ISC cache refresh failed: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    if engine:
        Base.metadata.create_all(bind=engine)
    init_mysql_connections()
    init_ssh_tunnel()
    
    cache_scheduler.register(_scheduled_isc_refresh)
    cache_scheduler.start(interval=3600)
    logger.info("Cache auto-refresh scheduler started (1 hour interval)")
    
    yield
    cache_scheduler.stop()
    close_ssh_tunnel()

app = FastAPI(title="DW Financeiro - Eventos", version="1.0.0", lifespan=lifespan)

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
app.include_router(contas.router, prefix="/api")
app.include_router(projetos.router, prefix="/api")
app.include_router(categorias_atletas.router, prefix="/api")
app.include_router(orcamento.router, prefix="/api")
app.include_router(projecao.router, prefix="/api")
app.include_router(realizado.router, prefix="/api")
app.include_router(atletas.router, prefix="/api")
app.include_router(atletas_satelite.router, prefix="/api")
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

@app.get("/api/mysql/ativo/test")
async def test_mysql_ativo():
    from app.core.database import engine_ativo
    if engine_ativo is None:
        return {"status": "error", "message": "MySQL Ativo connection not configured"}
    try:
        with engine_ativo.connect() as conn:
            result = conn.execute(text("SELECT 1 as test"))
            row = result.fetchone()
            return {"status": "success", "message": "Connected to MySQL Ativo", "test_result": row[0]}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/mysql/ativo/tables")
async def list_mysql_ativo_tables():
    from app.core.database import engine_ativo
    if engine_ativo is None:
        return {"status": "error", "message": "MySQL Ativo connection not configured"}
    try:
        with engine_ativo.connect() as conn:
            result = conn.execute(text("SHOW TABLES"))
            tables = [row[0] for row in result.fetchall()]
            return {"status": "success", "tables": tables, "count": len(tables)}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/ssh/test")
async def test_ssh_connection():
    from app.core.database import engine_ssh
    if engine_ssh is None:
        return {"status": "error", "message": "SSH tunnel database connection not configured. Check SSH_HOST, SSH_USER, SSH_PRIVATE_KEY, DB_HOST, DB_USER, DB_PASSWORD, DB_NAME."}
    try:
        with engine_ssh.connect() as conn:
            result = conn.execute(text("SELECT 1 as test"))
            row = result.fetchone()
            return {"status": "success", "message": "Connected to database via SSH tunnel", "test_result": row[0]}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/ssh/tables")
async def list_ssh_tables():
    from app.core.database import engine_ssh
    if engine_ssh is None:
        return {"status": "error", "message": "SSH tunnel database connection not configured"}
    try:
        with engine_ssh.connect() as conn:
            result = conn.execute(text("SHOW TABLES"))
            tables = [row[0] for row in result.fetchall()]
            return {"status": "success", "tables": tables, "count": len(tables)}
    except Exception as e:
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
