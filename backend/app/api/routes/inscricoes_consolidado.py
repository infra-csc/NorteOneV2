from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import text
from typing import Optional, List
from pydantic import BaseModel
import app.core.database as db_module
from datetime import datetime, timedelta
import asyncio
from concurrent.futures import ThreadPoolExecutor
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

class InscricaoFonteDetalhe(BaseModel):
    qtd: int
    valor: float

class InscricaoPorFonte(BaseModel):
    ativo: Optional[InscricaoFonteDetalhe] = None
    magento: Optional[InscricaoFonteDetalhe] = None

class InscricaoConsolidada(BaseModel):
    sku: str
    id_evento: Optional[str] = None
    evento: Optional[str] = None
    qtd_vendida_total: int
    valor_total: float
    por_fonte: InscricaoPorFonte

class InscricoesConsolidadasResponse(BaseModel):
    status: str
    total_eventos: int
    qtd_vendida_total: int
    valor_total: float
    dados: List[InscricaoConsolidada]
    fontes_disponiveis: dict

QUERY_ATIVO = """
SELECT
    b.id_campanha_salesforce AS sku,
    CAST(b.id_evento AS CHAR) AS id_evento,
    b.ds_evento AS evento,
    COUNT(*) AS qtd_vendida,
    COALESCE(SUM(a.nr_preco), 0) AS valor_total
FROM (
    SELECT id_evento, ds_evento, id_campanha_salesforce
    FROM sa_evento
    WHERE dt_evento BETWEEN DATE_SUB(CURDATE(), INTERVAL 6 MONTH)
                        AND DATE_ADD(CURDATE(), INTERVAL 6 MONTH)
) AS b
INNER JOIN sa_pedido_evento AS a
    ON a.id_evento = b.id_evento
INNER JOIN (
    SELECT id_pedido
    FROM sa_pedido
    WHERE id_pedido_status = 2
       OR (fl_local_inscricao = 2 AND id_pedido_status = 1)
) AS c
    ON c.id_pedido = a.id_pedido
GROUP BY
    b.id_campanha_salesforce,
    b.id_evento,
    b.ds_evento
ORDER BY qtd_vendida DESC
"""

QUERY_MAGENTO = """
SELECT
    b.sku AS sku,
    NULL AS id_evento,
    b.name AS evento,
    COUNT(b.item_id) AS qtd_vendida,
    COALESCE(SUM(b.row_total), 0) AS valor_total
FROM
    sales_order AS a
    INNER JOIN sales_order_item AS b ON b.order_id = a.entity_id
WHERE
    a.created_at >= DATE_SUB(CURRENT_DATE, INTERVAL 6 MONTH)
    AND a.status IN ('processing', 'complete', 'approved', 'aprovado_link', 'pending')
    AND a.state != 'canceled'
    AND b.sku IS NOT NULL
    AND b.sku != ''
    AND b.row_total > 0
GROUP BY
    b.sku,
    b.name
ORDER BY qtd_vendida DESC
LIMIT 500
"""

def fetch_ativo_data():
    if db_module.engine_ssh is None:
        return None, "SSH tunnel não configurado"
    try:
        logger.info("Buscando dados do banco Ativo...")
        with db_module.engine_ssh.connect() as conn:
            result = conn.execute(text(QUERY_ATIVO))
            rows = result.fetchall()
            logger.info(f"Banco Ativo: {len(rows)} registros")
            return [
                {
                    "sku": row[0],
                    "id_evento": str(row[1]) if row[1] else None,
                    "evento": row[2],
                    "qtd_vendida": int(row[3]) if row[3] else 0,
                    "valor_total": float(row[4]) if row[4] else 0.0
                }
                for row in rows
            ], None
    except Exception as e:
        logger.error(f"Erro banco Ativo: {e}")
        return None, str(e)

def fetch_magento_data():
    if db_module.engine_magento is None:
        return None, "Conexão Magento não configurada"
    try:
        logger.info("Buscando dados do banco Magento...")
        from sqlalchemy import create_engine
        from sqlalchemy.pool import NullPool
        
        engine_with_timeout = db_module.engine_magento.execution_options(timeout=30)
        with engine_with_timeout.connect() as conn:
            result = conn.execute(text(QUERY_MAGENTO))
            rows = result.fetchall()
            logger.info(f"Banco Magento: {len(rows)} registros")
            return [
                {
                    "sku": row[0],
                    "id_evento": str(row[1]) if row[1] else None,
                    "evento": row[2],
                    "qtd_vendida": int(row[3]) if row[3] else 0,
                    "valor_total": float(row[4]) if row[4] else 0.0
                }
                for row in rows
            ], None
    except Exception as e:
        logger.error(f"Erro banco Magento: {e}")
        return None, f"Query timeout ou erro: {str(e)[:100]}"

@router.get("/consolidado", response_model=InscricoesConsolidadasResponse)
async def get_inscricoes_consolidadas(
    sku: Optional[str] = Query(None, description="Filtrar por SKU específico"),
    incluir_magento: bool = Query(True, description="Incluir dados do Magento")
):
    executor = ThreadPoolExecutor(max_workers=2)
    loop = asyncio.get_event_loop()
    
    ativo_future = loop.run_in_executor(executor, fetch_ativo_data)
    
    magento_result = None
    magento_error = None
    
    if incluir_magento:
        magento_future = loop.run_in_executor(executor, fetch_magento_data)
        try:
            results = await asyncio.wait_for(
                asyncio.gather(ativo_future, magento_future, return_exceptions=True),
                timeout=90.0
            )
            ativo_result, ativo_error = results[0] if not isinstance(results[0], Exception) else (None, str(results[0]))
            magento_result, magento_error = results[1] if not isinstance(results[1], Exception) else (None, str(results[1]))
        except asyncio.TimeoutError:
            ativo_result, ativo_error = await ativo_future if not ativo_future.done() else (None, "Timeout")
            magento_error = "Timeout após 90 segundos"
    else:
        ativo_result, ativo_error = await ativo_future
        magento_error = "Desabilitado. Use incluir_magento=true para incluir."
    
    fontes_disponiveis = {
        "ativo": {"disponivel": ativo_result is not None, "erro": ativo_error},
        "magento": {"disponivel": magento_result is not None, "erro": magento_error}
    }
    
    if ativo_result is None and magento_result is None:
        raise HTTPException(
            status_code=503,
            detail=f"Nenhuma fonte de dados disponível. Ativo: {ativo_error}. Magento: {magento_error}"
        )
    
    consolidado = {}
    
    if ativo_result:
        for row in ativo_result:
            row_sku = row["sku"]
            if row_sku:
                if row_sku not in consolidado:
                    consolidado[row_sku] = {
                        "sku": row_sku,
                        "id_evento": row["id_evento"],
                        "evento": row["evento"],
                        "qtd_vendida_total": 0,
                        "valor_total": 0.0,
                        "por_fonte": {"ativo": None, "magento": None}
                    }
                consolidado[row_sku]["por_fonte"]["ativo"] = {
                    "qtd": row["qtd_vendida"],
                    "valor": row["valor_total"]
                }
                consolidado[row_sku]["qtd_vendida_total"] += row["qtd_vendida"]
                consolidado[row_sku]["valor_total"] += row["valor_total"]
                if not consolidado[row_sku]["evento"] and row["evento"]:
                    consolidado[row_sku]["evento"] = row["evento"]
    
    if magento_result:
        for row in magento_result:
            row_sku = row["sku"]
            if row_sku:
                if row_sku not in consolidado:
                    consolidado[row_sku] = {
                        "sku": row_sku,
                        "id_evento": row["id_evento"],
                        "evento": row["evento"],
                        "qtd_vendida_total": 0,
                        "valor_total": 0.0,
                        "por_fonte": {"ativo": None, "magento": None}
                    }
                consolidado[row_sku]["por_fonte"]["magento"] = {
                    "qtd": row["qtd_vendida"],
                    "valor": row["valor_total"]
                }
                consolidado[row_sku]["qtd_vendida_total"] += row["qtd_vendida"]
                consolidado[row_sku]["valor_total"] += row["valor_total"]
                if not consolidado[row_sku]["evento"] and row["evento"]:
                    consolidado[row_sku]["evento"] = row["evento"]
    
    dados = list(consolidado.values())
    
    if sku:
        dados = [d for d in dados if d["sku"] and sku.upper() in d["sku"].upper()]
    
    dados.sort(key=lambda x: x["qtd_vendida_total"], reverse=True)
    
    return InscricoesConsolidadasResponse(
        status="success",
        total_eventos=len(dados),
        qtd_vendida_total=sum(d["qtd_vendida_total"] for d in dados),
        valor_total=sum(d["valor_total"] for d in dados),
        dados=[InscricaoConsolidada(**d) for d in dados],
        fontes_disponiveis=fontes_disponiveis
    )

@router.get("/por-projeto/{codigo_sku}")
async def get_inscricoes_por_projeto(codigo_sku: str):
    executor = ThreadPoolExecutor(max_workers=2)
    loop = asyncio.get_event_loop()
    
    ativo_future = loop.run_in_executor(executor, fetch_ativo_data)
    magento_future = loop.run_in_executor(executor, fetch_magento_data)
    
    ativo_result, ativo_error = await ativo_future
    magento_result, magento_error = await magento_future
    
    ativo_data = None
    magento_data = None
    
    if ativo_result:
        for row in ativo_result:
            if row["sku"] and row["sku"].upper() == codigo_sku.upper():
                ativo_data = row
                break
    
    if magento_result:
        for row in magento_result:
            if row["sku"] and row["sku"].upper() == codigo_sku.upper():
                magento_data = row
                break
    
    qtd_total = 0
    valor_total = 0.0
    
    if ativo_data:
        qtd_total += ativo_data["qtd_vendida"]
        valor_total += ativo_data["valor_total"]
    
    if magento_data:
        qtd_total += magento_data["qtd_vendida"]
        valor_total += magento_data["valor_total"]
    
    return {
        "status": "success",
        "sku": codigo_sku,
        "evento": (ativo_data or magento_data or {}).get("evento"),
        "qtd_vendida_total": qtd_total,
        "valor_total": valor_total,
        "fonte_ativo": {
            "disponivel": ativo_error is None,
            "erro": ativo_error,
            "dados": ativo_data
        } if ativo_result is not None or ativo_error else None,
        "fonte_magento": {
            "disponivel": magento_error is None,
            "erro": magento_error,
            "dados": magento_data
        } if magento_result is not None or magento_error else None
    }

@router.get("/test-ativo")
async def test_ativo_query():
    if db_module.engine_ssh is None:
        return {"status": "error", "message": "SSH tunnel não configurado"}
    
    try:
        logger.info("Iniciando query Ativo...")
        with db_module.engine_ssh.connect() as conn:
            result = conn.execute(text(QUERY_ATIVO))
            rows = result.fetchall()
            logger.info(f"Query Ativo retornou {len(rows)} linhas")
            return {
                "status": "success",
                "total_rows": len(rows),
                "sample": [
                    {"sku": row[0], "id_evento": str(row[1]), "evento": row[2], "qtd": int(row[3]), "valor": float(row[4])}
                    for row in rows[:5]
                ]
            }
    except Exception as e:
        logger.error(f"Erro query Ativo: {e}")
        return {"status": "error", "message": str(e)}

@router.get("/test-magento")
async def test_magento_query():
    if db_module.engine_magento is None:
        return {"status": "error", "message": "Conexão Magento não configurada"}
    
    try:
        logger.info("Iniciando query Magento...")
        with db_module.engine_magento.connect() as conn:
            result = conn.execute(text(QUERY_MAGENTO))
            rows = result.fetchall()
            logger.info(f"Query Magento retornou {len(rows)} linhas")
            return {
                "status": "success",
                "total_rows": len(rows),
                "sample": [
                    {"sku": row[0], "id_evento": str(row[1]) if row[1] else None, "evento": row[2], "qtd": int(row[3]), "valor": float(row[4])}
                    for row in rows[:5]
                ]
            }
    except Exception as e:
        logger.error(f"Erro query Magento: {e}")
        return {"status": "error", "message": str(e)}
