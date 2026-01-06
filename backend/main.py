from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from app.core.database import engine, Base, init_mysql_connections, engine_ativo
from app.api.routes import auth, users, centros_custo, contas, projetos, categorias_atletas, orcamento, projecao, realizado, atletas, atletas_satelite, dashboard

if engine:
    Base.metadata.create_all(bind=engine)

init_mysql_connections()

app = FastAPI(title="DW Financeiro - Eventos", version="1.0.0")

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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
