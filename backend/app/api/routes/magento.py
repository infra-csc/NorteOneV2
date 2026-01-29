from fastapi import APIRouter, HTTPException
from sqlalchemy import text
import app.core.database as db_module

router = APIRouter()

@router.get("/test")
async def test_magento_connection():
    if db_module.engine_magento is None:
        raise HTTPException(
            status_code=503,
            detail="Conexão Magento não configurada. Verifique as credenciais MAGENTO_DB_*"
        )
    
    try:
        with db_module.engine_magento.connect() as conn:
            result = conn.execute(text("SELECT 1 as test")).fetchone()
            return {
                "status": "success",
                "message": "Conexão com banco Magento estabelecida com sucesso",
                "test_result": result[0] if result else None
            }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao conectar no banco Magento: {str(e)}"
        )

@router.get("/tables")
async def list_magento_tables():
    if db_module.engine_magento is None:
        raise HTTPException(
            status_code=503,
            detail="Conexão Magento não configurada"
        )
    
    try:
        with db_module.engine_magento.connect() as conn:
            result = conn.execute(text("SHOW TABLES")).fetchall()
            tables = [row[0] for row in result]
            return {
                "status": "success",
                "total_tables": len(tables),
                "tables": tables[:50]
            }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao listar tabelas: {str(e)}"
        )

@router.get("/sales-summary")
async def get_sales_summary():
    if db_module.engine_magento is None:
        raise HTTPException(
            status_code=503,
            detail="Conexão Magento não configurada"
        )
    
    try:
        with db_module.engine_magento.connect() as conn:
            result = conn.execute(text("""
                SELECT 
                    COUNT(*) as total_orders,
                    SUM(grand_total) as total_revenue
                FROM sales_order
                WHERE created_at >= DATE_SUB(NOW(), INTERVAL 30 DAY)
            """)).fetchone()
            
            return {
                "status": "success",
                "period": "últimos 30 dias",
                "total_orders": result[0] if result else 0,
                "total_revenue": float(result[1]) if result and result[1] else 0
            }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao buscar resumo de vendas: {str(e)}"
        )
