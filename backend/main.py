from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.database import engine, Base
from app.api.routes import auth, users, centros_custo, contas, projetos, categorias_atletas, orcamento, projecao, realizado, atletas, atletas_satelite, dashboard

Base.metadata.create_all(bind=engine)

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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
