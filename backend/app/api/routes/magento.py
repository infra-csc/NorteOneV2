from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy import text
import logging
import app.core.database as db_module
from ...core.security import get_current_user
from ...core.db_retry import magento_run, MagentoEngineUnavailable

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/test")
def test_magento_connection(current_user=Depends(get_current_user)):
    if db_module.engine_magento is None:
        raise HTTPException(
            status_code=503,
            detail="Conexão Magento não configurada. Verifique as credenciais MAGENTO_DB_*"
        )

    def _ping(conn):
        return conn.execute(text("SELECT 1 as test")).fetchone()

    try:
        result = magento_run(_ping, label="magento:test-connection", profile="request")
        return {
            "status": "success",
            "message": "Conexão com banco Magento estabelecida com sucesso",
            "test_result": result[0] if result else None
        }
    except MagentoEngineUnavailable:
        raise HTTPException(status_code=503, detail="Conexão Magento indisponível")
    except Exception as e:
        logger.error(f"Erro ao conectar no banco Magento: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Erro interno ao conectar no banco de dados"
        )

@router.get("/tables")
def list_magento_tables(current_user=Depends(get_current_user)):
    if db_module.engine_magento is None:
        raise HTTPException(
            status_code=503,
            detail="Conexão Magento não configurada"
        )

    def _show_tables(conn):
        return conn.execute(text("SHOW TABLES")).fetchall()

    try:
        result = magento_run(_show_tables, label="magento:show-tables", profile="request")
        tables = [row[0] for row in result]
        return {
            "status": "success",
            "total_tables": len(tables),
            "tables": tables[:50]
        }
    except MagentoEngineUnavailable:
        raise HTTPException(status_code=503, detail="Conexão Magento indisponível")
    except Exception as e:
        logger.error(f"Erro ao listar tabelas Magento: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Erro interno ao listar tabelas"
        )

@router.get("/sales-summary")
def get_sales_summary(current_user=Depends(get_current_user)):
    if db_module.engine_magento is None:
        raise HTTPException(
            status_code=503,
            detail="Conexão Magento não configurada"
        )

    def _summary(conn):
        return conn.execute(text("""
            SELECT /*+ MAX_EXECUTION_TIME(30000) */
                COUNT(*) as total_orders,
                SUM(grand_total) as total_revenue
            FROM sales_order
            WHERE created_at >= DATE_SUB(NOW(), INTERVAL 30 DAY)
        """)).fetchone()

    try:
        result = magento_run(_summary, label="magento:sales-summary", profile="request")
        return {
            "status": "success",
            "period": "últimos 30 dias",
            "total_orders": result[0] if result else 0,
            "total_revenue": float(result[1]) if result and result[1] else 0
        }
    except MagentoEngineUnavailable:
        raise HTTPException(status_code=503, detail="Conexão Magento indisponível")
    except Exception as e:
        logger.error(f"Erro ao buscar resumo de vendas Magento: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Erro interno ao buscar resumo de vendas"
        )
