from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import text
from typing import Optional, List
from pydantic import BaseModel
import app.core.database as db_module
from datetime import datetime, timedelta
import asyncio
from concurrent.futures import ThreadPoolExecutor
from functools import partial
import logging
import re

logger = logging.getLogger(__name__)

router = APIRouter()

def normalize_sku(sku: str) -> str:
    """
    Normaliza o SKU para o código base do evento.
    Exemplos:
    - SOL26SP1 -> SOL26SP1 (já é base)
    - EVSOL26SP1MB-5Km -> SOL26SP1
    - EVSOL26SP1KB-EVSOL26SP1MB-5Km-EVSOL26SP1CFINAL-M -> SOL26SP1
    - CPA25SP1 -> CPA25SP1
    - CDE25RJ3 -> CDE25RJ3
    
    Padrão: 2-4 letras + 2 dígitos (ano) + 2-3 letras (cidade) + 1 dígito (edição)
    """
    if not sku:
        return sku
    
    sku_upper = sku.upper()
    
    if sku_upper.startswith('EV'):
        sku_upper = sku_upper[2:]
    
    pattern = r'^([A-Z]{2,4}\d{2}[A-Z]{2,3}\d)'
    match = re.match(pattern, sku_upper)
    
    if match:
        return match.group(1)
    
    return sku

class InscricaoFonteDetalhe(BaseModel):
    qtd: int
    valor: float
    cortesia: int = 0
    inscricao_liquida: float = 0.0
    ticket_medio: float = 0.0
    taxa_liquida: float = 0.0
    kit_produto: float = 0.0
    qtd_grupos: int = 0
    inscricao_liquida_grupos: float = 0.0
    ticket_medio_grupos: float = 0.0
    qtd_site: int = 0
    inscricao_liquida_site: float = 0.0
    ticket_medio_site: float = 0.0

class InscricaoPorFonte(BaseModel):
    ativo: Optional[InscricaoFonteDetalhe] = None
    magento: Optional[InscricaoFonteDetalhe] = None

class InscricaoConsolidada(BaseModel):
    sku: str
    id_evento: Optional[str] = None
    evento: Optional[str] = None
    data_evento: Optional[str] = None
    categoria_evento: Optional[str] = None
    cidade: Optional[str] = None
    qtd_vendida_total: int
    valor_total: float
    cortesia_total: int = 0
    inscricao_liquida_total: float = 0.0
    ticket_medio_total: float = 0.0
    taxa_liquida_total: float = 0.0
    kit_produto_total: float = 0.0
    qtd_grupos_total: int = 0
    inscricao_liquida_grupos_total: float = 0.0
    qtd_site_total: int = 0
    inscricao_liquida_site_total: float = 0.0
    por_fonte: InscricaoPorFonte

class InscricoesConsolidadasResponse(BaseModel):
    status: str
    total_eventos: int
    qtd_vendida_total: int
    valor_total: float
    dados: List[InscricaoConsolidada]
    fontes_disponiveis: dict

def build_query_ativo(ano: int) -> str:
    """
    Constroi query do Ativo filtrando por ano do evento (dt_evento).
    Retorna métricas completas: quantidade, cortesia, inscrição líquida, ticket médio,
    taxa líquida, kit produto, e breakdown por grupos/site.
    """
    return f"""
SELECT
    b.id_evento AS id_evento,
    b.ds_evento AS evento,
    DATE(b.dt_evento) AS data_evento,
    COUNT(a.id_pedido_evento) AS qtd_total,
    SUM(CASE WHEN c.nr_total = 0 THEN 1 ELSE 0 END) AS cortesia,
    SUM(
        IF(a.nr_preco - COALESCE(a.nr_desconto_individual, 0) - COALESCE(h.vl_kit, 0) < 0, 0,
        a.nr_preco - COALESCE(a.nr_desconto_individual, 0) - COALESCE(h.vl_kit, 0))
    ) AS inscricao_liquida,
    SUM(
        IF(a.nr_preco - COALESCE(a.nr_desconto_individual, 0) - COALESCE(h.vl_kit, 0) < 0, 0,
        a.nr_preco - COALESCE(a.nr_desconto_individual, 0) - COALESCE(h.vl_kit, 0))
    ) / COUNT(a.id_pedido_evento) AS ticket_medio,
    SUM(
        IF(c.fl_local_inscricao = '1',
            IF(a.nr_preco + a.nr_taxa - COALESCE(a.nr_desconto_individual, 0) > a.nr_taxa, 
                a.nr_taxa, 
                a.nr_preco + a.nr_taxa - COALESCE(a.nr_desconto_individual, 0)),
            c.nr_taxa / (SELECT COUNT(*) FROM sa_pedido_evento AS pe2 
                         WHERE pe2.id_pedido = a.id_pedido GROUP BY pe2.id_pedido)
        )
    ) AS taxa_liquida,
    SUM(
        IF(
            (SELECT MIN(pe2.id_pedido_evento) FROM sa_pedido_evento AS pe2 
             WHERE pe2.id_pedido = c.id_pedido GROUP BY pe2.id_pedido) = a.id_pedido_evento,
            i.nr_preco * i.nr_quantidade,
            NULL
        )
    ) AS kit_produto,
    SUM(CASE WHEN f.en_cupom_classificacao OR h.ds_categoria LIKE '%Grup%' THEN 1 ELSE 0 END) AS qtd_grupos,
    SUM(CASE WHEN f.en_cupom_classificacao OR h.ds_categoria LIKE '%Grup%' THEN 
        IF(a.nr_preco - COALESCE(a.nr_desconto_individual, 0) - COALESCE(h.vl_kit, 0) < 0, 0,
        a.nr_preco - COALESCE(a.nr_desconto_individual, 0) - COALESCE(h.vl_kit, 0))
    ELSE 0 END) AS inscricao_liquida_grupos,
    SUM(CASE WHEN f.en_cupom_classificacao OR h.ds_categoria LIKE '%Grup%' THEN 
        IF(a.nr_preco - COALESCE(a.nr_desconto_individual, 0) - COALESCE(h.vl_kit, 0) < 0, 0,
        a.nr_preco - COALESCE(a.nr_desconto_individual, 0) - COALESCE(h.vl_kit, 0))
    ELSE 0 END) / NULLIF(SUM(CASE WHEN f.en_cupom_classificacao OR h.ds_categoria LIKE '%Grup%' THEN 1 ELSE 0 END), 0) AS ticket_medio_grupos,
    SUM(CASE WHEN (f.en_cupom_classificacao IS NULL OR NOT f.en_cupom_classificacao) 
        AND h.ds_categoria NOT LIKE '%Grup%'
        AND c.nr_total > 0 THEN 1 ELSE 0 END) AS qtd_site,
    SUM(CASE WHEN (f.en_cupom_classificacao IS NULL OR NOT f.en_cupom_classificacao)
        AND h.ds_categoria NOT LIKE '%Grup%' THEN 
        IF(a.nr_preco - COALESCE(a.nr_desconto_individual, 0) - COALESCE(h.vl_kit, 0) < 0, 0,
        a.nr_preco - COALESCE(a.nr_desconto_individual, 0) - COALESCE(h.vl_kit, 0))
    ELSE 0 END) AS inscricao_liquida_site,
    SUM(CASE WHEN (f.en_cupom_classificacao IS NULL OR NOT f.en_cupom_classificacao)
        AND h.ds_categoria NOT LIKE '%Grup%' THEN 
        IF(a.nr_preco - COALESCE(a.nr_desconto_individual, 0) - COALESCE(h.vl_kit, 0) < 0, 0,
        a.nr_preco - COALESCE(a.nr_desconto_individual, 0) - COALESCE(h.vl_kit, 0))
    ELSE 0 END) / NULLIF(SUM(CASE WHEN (f.en_cupom_classificacao IS NULL OR NOT f.en_cupom_classificacao)
        AND h.ds_categoria NOT LIKE '%Grup%'
        AND c.nr_total > 0 THEN 1 ELSE 0 END), 0) AS ticket_medio_site
FROM sa_pedido_evento AS a
INNER JOIN sa_evento AS b ON b.id_evento = a.id_evento
INNER JOIN sa_pedido AS c ON c.id_pedido = a.id_pedido
LEFT JOIN sa_modalidade_categoria AS h ON a.id_categoria = h.id_categoria
LEFT JOIN sa_cupom_desconto_item AS e ON e.id_cupom_desconto_item = a.id_cupom_individual
LEFT JOIN sa_cupom_desconto AS f ON f.id_cupom_desconto = e.id_cupom_desconto
LEFT JOIN sa_pedido_produto AS i ON a.id_pedido = i.id_pedido
WHERE 
    YEAR(b.dt_evento) = {ano}
    AND c.id_pedido_status = 2
GROUP BY b.id_evento, b.ds_evento, b.dt_evento
ORDER BY b.dt_evento
"""

def build_query_magento(ano: int) -> str:
    """
    Constroi query do Magento filtrando por ano do evento (wl.final_date).
    Retorna métricas completas: quantidade, cortesia, inscrição líquida, ticket médio,
    taxa líquida, kit produto, e breakdown por grupos/site.
    """
    return f"""
SELECT
    wl.location_id AS id_evento,
    REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(
        REPLACE(wl.name, 'Retirada de kit - CE', 'Circuito das Estações'),
        'Retirada de Kit - CE', 'Circuito das Estações'),'Retirada de KIt - CE', 'Circuito das Estações'),
        'Retirada de Kit- CE', 'Circuito das Estações'),'Retirada de Kit - ', ''),'Retirada de kit - ', ''),
        'SSA', 'Salvador') AS evento,
    wl.final_date AS data_evento,
    COUNT(wl.name) AS qtd_total,
    SUM(CASE WHEN so.base_grand_total = 0 THEN 1 ELSE 0 END) AS cortesia,
    SUM(soi.price - CASE WHEN soi.price = 0 THEN 0 
        WHEN soi.name LIKE '%plus%' THEN 69.00
        WHEN soi.name LIKE '%super%' THEN 269.00
        WHEN soi.name LIKE '%vip%' THEN 199.99
        ELSE 0 END + COALESCE(so.base_discount_invoiced, 0) 
        * (soi.price / NULLIF(so.base_subtotal, 1))
        - CASE WHEN cg.customer_group_id = 4 THEN 0
        WHEN COALESCE(soiaa.price, 0) = 14.90 AND cg.customer_group_id IN (0, 1, 2, 3, 5, 7) THEN 14.90
        ELSE 0 END) AS inscricao_liquida,
    SUM(soi.price - CASE WHEN soi.price = 0 THEN 0 
        WHEN soi.name LIKE '%plus%' THEN 69.00
        WHEN soi.name LIKE '%super%' THEN 269.00
        WHEN soi.name LIKE '%vip%' THEN 199.99
        ELSE 0 END + COALESCE(so.base_discount_invoiced, 0) 
        * (soi.price / NULLIF(so.base_subtotal, 1))
        - CASE WHEN cg.customer_group_id = 4 THEN 0
        WHEN COALESCE(soiaa.price, 0) = 14.90 AND cg.customer_group_id IN (0, 1, 2, 3, 5, 7) THEN 14.90
        ELSE 0 END) / COUNT(wl.name) AS ticket_medio,
    SUM(sot.amount / (SELECT COUNT(*) FROM sales_order_item AS ba 
        WHERE ba.order_id = soi.order_id AND ba.product_type = 'Bundle'
        GROUP BY ba.order_id)) AS taxa_liquida,
    SUM(CASE
        WHEN soi.name LIKE '%plus%' THEN 69.00
        WHEN soi.name LIKE '%super%' THEN 269.00
        WHEN soi.name LIKE '%vip%' THEN 199.99
        ELSE 0
    END) AS kit_produto,
    SUM(CASE WHEN so.discount_description LIKE '%Grup%' THEN 1 ELSE 0 END) AS qtd_grupos,
    SUM(CASE WHEN so.discount_description LIKE '%Grup%' THEN 
        (soi.price - CASE WHEN soi.price = 0 THEN 0 
            WHEN soi.name LIKE '%plus%' THEN 69.00
            WHEN soi.name LIKE '%super%' THEN 269.00
            WHEN soi.name LIKE '%vip%' THEN 199.99
            ELSE 0 END + COALESCE(so.base_discount_invoiced, 0) * (soi.price / NULLIF(so.base_subtotal, 1))
        - CASE WHEN cg.customer_group_id = 4 THEN 0
            WHEN COALESCE(soiaa.price, 0) = 14.90 AND cg.customer_group_id IN (0, 1, 2, 3, 5, 7) THEN 14.90
            ELSE 0 END) ELSE 0 END) AS inscricao_liquida_grupos,
    SUM(CASE WHEN so.discount_description LIKE '%Grup%' THEN 
        (soi.price - CASE WHEN soi.price = 0 THEN 0 
            WHEN soi.name LIKE '%plus%' THEN 69.00
            WHEN soi.name LIKE '%super%' THEN 269.00
            WHEN soi.name LIKE '%vip%' THEN 199.99
            ELSE 0 END + COALESCE(so.base_discount_invoiced, 0) * (soi.price / NULLIF(so.base_subtotal, 1))
        - CASE WHEN cg.customer_group_id = 4 THEN 0
            WHEN COALESCE(soiaa.price, 0) = 14.90 AND cg.customer_group_id IN (0, 1, 2, 3, 5, 7) THEN 14.90
            ELSE 0 END) ELSE 0 END) / NULLIF(SUM(CASE WHEN so.discount_description LIKE '%Grup%' THEN 1 ELSE 0 END), 0) AS ticket_medio_grupos,
    SUM(CASE WHEN (so.discount_description IS NULL OR so.discount_description NOT LIKE '%Grup%') 
        AND so.base_grand_total > 0 THEN 1 ELSE 0 END) AS qtd_site,
    SUM(CASE WHEN (so.discount_description IS NULL OR so.discount_description NOT LIKE '%Grup%') THEN 
        (soi.price - CASE WHEN soi.price = 0 THEN 0 
            WHEN soi.name LIKE '%plus%' THEN 69.00
            WHEN soi.name LIKE '%super%' THEN 269.00
            WHEN soi.name LIKE '%vip%' THEN 199.99
            ELSE 0 END 
        + COALESCE(so.base_discount_invoiced, 0) * (soi.price / NULLIF(so.base_subtotal, 1))
        - CASE WHEN cg.customer_group_id = 4 THEN 0
            WHEN COALESCE(soiaa.price, 0) = 14.90 AND cg.customer_group_id IN (0, 1, 2, 3, 5, 7) THEN 14.90
            ELSE 0 END) ELSE 0 END) AS inscricao_liquida_site,
    SUM(CASE WHEN (so.discount_description IS NULL OR so.discount_description NOT LIKE '%Grup%') THEN 
        (soi.price - CASE WHEN soi.price = 0 THEN 0 
            WHEN soi.name LIKE '%plus%' THEN 69.00
            WHEN soi.name LIKE '%super%' THEN 269.00
            WHEN soi.name LIKE '%vip%' THEN 199.99
            ELSE 0 END 
        + COALESCE(so.base_discount_invoiced, 0) * (soi.price / NULLIF(so.base_subtotal, 1))
        - CASE WHEN cg.customer_group_id = 4 THEN 0
            WHEN COALESCE(soiaa.price, 0) = 14.90 AND cg.customer_group_id IN (0, 1, 2, 3, 5, 7) THEN 14.90
            ELSE 0 END) ELSE 0 END) / NULLIF(SUM(CASE WHEN (so.discount_description IS NULL OR so.discount_description NOT LIKE '%Grup%') 
        AND so.base_grand_total > 0 THEN 1 ELSE 0 END), 0) AS ticket_medio_site,
    CASE
        WHEN wl.name LIKE '%Night Run%' THEN 'Night Run'
        WHEN wl.name LIKE '% CE %' THEN 'Circuito das Estações'
        WHEN wl.name LIKE '%verão%' THEN 'Circuito das Estações'
        WHEN wl.name LIKE '%Banco%' THEN 'Banco Do Brasil'
        WHEN wl.name LIKE '%Eco Run%' THEN 'Eco Run'
        WHEN wl.name LIKE '%Girl%' THEN 'Girl Power'
        WHEN wl.name LIKE '%Meia%' THEN 'Meias e Maratonas'
        WHEN wl.name LIKE '%Maratona%' THEN 'Meias e Maratonas'
        WHEN wl.name LIKE '%21k%' THEN 'Meias e Maratonas'
        WHEN wl.name LIKE '%sol%' THEN 'Circuito Sol'
        WHEN wl.name LIKE '%Treinão%' THEN 'Treinão'
        WHEN wl.name LIKE '%cruz%' THEN 'Vera Cruz'
        WHEN wl.name LIKE '%Rios%' THEN 'Meias e Maratonas'
        WHEN wl.name LIKE '%Bravus%' THEN 'Bravus'
        WHEN wl.name LIKE '%Bem%' THEN 'Corrida do Bem'
        WHEN wl.name LIKE '%Triathlon%' THEN 'Triathlon'
        WHEN wl.name LIKE '%Estações%' THEN 'Circuito das Estações'
        WHEN wl.name LIKE '%Primavera%' THEN 'Circuito das Estações'
        WHEN wl.name LIKE '%Outono%' THEN 'Circuito das Estações'
        WHEN wl.name LIKE '%Troféu %' THEN 'Troféu Brasil'
        WHEN wl.name LIKE '%Parcel%' THEN 'Triathlon'
        WHEN wl.name LIKE '%ilha%' THEN 'Triathlon'
        WHEN wl.name LIKE '%Eco%' THEN 'Eco Run'
        WHEN wl.name LIKE '%Bull%' THEN 'Bull Run'
        WHEN wl.name LIKE '%Juntos%' THEN 'Juntos'
        WHEN wl.name LIKE '%Blue%' THEN 'Blue Run'
        WHEN wl.name LIKE '%Energy%' THEN 'Energy'
        WHEN wl.name LIKE '%Pedelar%' THEN 'Eventos de Ciclismo'
        WHEN wl.name LIKE '%Bike%' THEN 'Eventos de Ciclismo'
        WHEN wl.name LIKE '%Riders%' THEN 'Eventos de Ciclismo'    
        WHEN wl.name LIKE '%humans%' THEN 'Humans'    
        WHEN wl.name LIKE '%S RUN%' THEN 'S RUN'  
        WHEN wl.name LIKE '%Agro%' THEN 'Agro'  
        WHEN wl.name LIKE '%Running%' THEN 'Treinão'  
        WHEN wl.name LIKE '%Teste%' THEN 'Treinão'  
        WHEN wl.name LIKE '%S21%' THEN 'Meias e Maratonas'  
        WHEN wl.name LIKE '%gilr%' THEN 'Girl Power'  
        WHEN wl.name LIKE '%testar%' THEN 'Treinão'  
        WHEN wl.name LIKE '%pão%' THEN 'Pão De Açucar'
        WHEN wl.name LIKE '%Floripa%' THEN 'Meias e Maratonas'
        WHEN wl.name LIKE '%Tis%' THEN 'Meias e Maratonas'
        WHEN wl.name LIKE '%Biomas%' THEN 'Biomas'
        ELSE 'Outra Categoria'
    END AS categoria_evento,
    city AS cidade
FROM sales_order AS so
LEFT JOIN sales_order_item AS soi ON soi.order_id = so.entity_id  
LEFT JOIN sales_order_tax AS sot ON sot.order_id = so.entity_id  
LEFT JOIN sales_order_payment AS sop ON sop.parent_id = so.entity_id  
LEFT JOIN customer_group AS cg ON cg.customer_group_id = so.customer_group_id  
LEFT JOIN webpos_location AS wl ON so.location_pickup_id = wl.location_id
LEFT JOIN (SELECT * FROM sales_order_item WHERE name LIKE '%persona%') AS soiaa ON soiaa.parent_item_id = soi.item_id  
WHERE 
    wl.final_date >= '{ano}-01-01' 
    AND wl.final_date <= '{ano}-12-31'
    AND so.increment_id NOT LIKE '%-1%'
    AND so.increment_id NOT LIKE '%-2%'
    AND so.increment_id NOT LIKE '%-3%'
    AND so.increment_id NOT LIKE '%-4%'
    AND so.increment_id NOT LIKE '%-5%'
    AND so.increment_id NOT LIKE '%-6%'
    AND so.increment_id NOT LIKE '%-7%'
    AND so.increment_id NOT LIKE '%-8%'
    AND so.increment_id NOT LIKE '%-9%'
    AND so.increment_id NOT LIKE '%-10%'
    AND so.increment_id NOT LIKE '%-11%'
    AND so.increment_id NOT LIKE '%-12%'
    AND so.increment_id NOT LIKE '%-13%'
    AND so.increment_id NOT LIKE '%-14%'
    AND so.increment_id NOT LIKE '%-15%'
    AND so.increment_id NOT LIKE '%-16%'
    AND so.increment_id NOT LIKE '%-17%'
    AND so.status IN ('Processing','Complete','approved')
    AND soi.product_type = 'Bundle'
GROUP BY wl.name, wl.final_date, wl.location_id, city
ORDER BY wl.final_date
"""

def fetch_ativo_data(ano: int = 2026):
    if db_module.engine_ssh is None:
        return None, "SSH tunnel não configurado"
    try:
        query = build_query_ativo(ano)
        logger.info(f"Buscando dados do banco Ativo (ano={ano})...")
        with db_module.engine_ssh.connect() as conn:
            result = conn.execute(text(query))
            rows = result.fetchall()
            logger.info(f"Banco Ativo: {len(rows)} registros para {ano}")
            return [
                {
                    "id_evento": str(row[0]) if row[0] else None,
                    "evento": row[1],
                    "data_evento": str(row[2]) if row[2] else None,
                    "qtd_vendida": int(row[3]) if row[3] else 0,
                    "cortesia": int(row[4]) if row[4] else 0,
                    "inscricao_liquida": float(row[5]) if row[5] else 0.0,
                    "ticket_medio": float(row[6]) if row[6] else 0.0,
                    "taxa_liquida": float(row[7]) if row[7] else 0.0,
                    "kit_produto": float(row[8]) if row[8] else 0.0,
                    "qtd_grupos": int(row[9]) if row[9] else 0,
                    "inscricao_liquida_grupos": float(row[10]) if row[10] else 0.0,
                    "ticket_medio_grupos": float(row[11]) if row[11] else 0.0,
                    "qtd_site": int(row[12]) if row[12] else 0,
                    "inscricao_liquida_site": float(row[13]) if row[13] else 0.0,
                    "ticket_medio_site": float(row[14]) if row[14] else 0.0,
                }
                for row in rows
            ], None
    except Exception as e:
        logger.error(f"Erro banco Ativo: {e}")
        return None, str(e)

def fetch_magento_data(ano: int = 2026):
    if db_module.engine_magento is None:
        return None, "Conexão Magento não configurada"
    try:
        query = build_query_magento(ano)
        logger.info(f"Buscando dados do banco Magento (ano={ano})...")
        
        engine_with_timeout = db_module.engine_magento.execution_options(timeout=60)
        with engine_with_timeout.connect() as conn:
            result = conn.execute(text(query))
            rows = result.fetchall()
            logger.info(f"Banco Magento: {len(rows)} registros para {ano}")
            return [
                {
                    "id_evento": str(row[0]) if row[0] else None,
                    "evento": row[1],
                    "data_evento": str(row[2]) if row[2] else None,
                    "qtd_vendida": int(row[3]) if row[3] else 0,
                    "cortesia": int(row[4]) if row[4] else 0,
                    "inscricao_liquida": float(row[5]) if row[5] else 0.0,
                    "ticket_medio": float(row[6]) if row[6] else 0.0,
                    "taxa_liquida": float(row[7]) if row[7] else 0.0,
                    "kit_produto": float(row[8]) if row[8] else 0.0,
                    "qtd_grupos": int(row[9]) if row[9] else 0,
                    "inscricao_liquida_grupos": float(row[10]) if row[10] else 0.0,
                    "ticket_medio_grupos": float(row[11]) if row[11] else 0.0,
                    "qtd_site": int(row[12]) if row[12] else 0,
                    "inscricao_liquida_site": float(row[13]) if row[13] else 0.0,
                    "ticket_medio_site": float(row[14]) if row[14] else 0.0,
                    "categoria_evento": row[15] if row[15] else None,
                    "cidade": row[16] if row[16] else None,
                }
                for row in rows
            ], None
    except Exception as e:
        logger.error(f"Erro banco Magento: {e}")
        return None, f"Query timeout ou erro: {str(e)[:100]}"

@router.get("/consolidado", response_model=InscricoesConsolidadasResponse)
async def get_inscricoes_consolidadas(
    sku: Optional[str] = Query(None, description="Filtrar por SKU específico"),
    incluir_magento: bool = Query(True, description="Incluir dados do Magento"),
    ano: int = Query(2026, description="Ano do evento para filtrar (default: 2026)")
):
    executor = ThreadPoolExecutor(max_workers=2)
    loop = asyncio.get_event_loop()
    
    ativo_future = loop.run_in_executor(executor, partial(fetch_ativo_data, ano))
    
    magento_result = None
    magento_error = None
    
    if incluir_magento:
        magento_future = loop.run_in_executor(executor, partial(fetch_magento_data, ano))
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
    
    dados = []
    
    def create_fonte_detalhe(row):
        return {
            "qtd": row.get("qtd_vendida", 0),
            "valor": row.get("inscricao_liquida", 0.0),
            "cortesia": row.get("cortesia", 0),
            "inscricao_liquida": row.get("inscricao_liquida", 0.0),
            "ticket_medio": row.get("ticket_medio", 0.0),
            "taxa_liquida": row.get("taxa_liquida", 0.0),
            "kit_produto": row.get("kit_produto", 0.0),
            "qtd_grupos": row.get("qtd_grupos", 0),
            "inscricao_liquida_grupos": row.get("inscricao_liquida_grupos", 0.0),
            "ticket_medio_grupos": row.get("ticket_medio_grupos", 0.0),
            "qtd_site": row.get("qtd_site", 0),
            "inscricao_liquida_site": row.get("inscricao_liquida_site", 0.0),
            "ticket_medio_site": row.get("ticket_medio_site", 0.0),
        }
    
    if ativo_result:
        for row in ativo_result:
            evento_key = f"ativo_{row['id_evento']}"
            dados.append({
                "sku": evento_key,
                "id_evento": row["id_evento"],
                "evento": row["evento"],
                "data_evento": row.get("data_evento"),
                "categoria_evento": None,
                "cidade": None,
                "qtd_vendida_total": row.get("qtd_vendida", 0),
                "valor_total": row.get("inscricao_liquida", 0.0),
                "cortesia_total": row.get("cortesia", 0),
                "inscricao_liquida_total": row.get("inscricao_liquida", 0.0),
                "ticket_medio_total": row.get("ticket_medio", 0.0),
                "taxa_liquida_total": row.get("taxa_liquida", 0.0),
                "kit_produto_total": row.get("kit_produto", 0.0),
                "qtd_grupos_total": row.get("qtd_grupos", 0),
                "inscricao_liquida_grupos_total": row.get("inscricao_liquida_grupos", 0.0),
                "qtd_site_total": row.get("qtd_site", 0),
                "inscricao_liquida_site_total": row.get("inscricao_liquida_site", 0.0),
                "por_fonte": {
                    "ativo": create_fonte_detalhe(row),
                    "magento": None
                }
            })
    
    if magento_result:
        for row in magento_result:
            evento_key = f"magento_{row['id_evento']}"
            dados.append({
                "sku": evento_key,
                "id_evento": row["id_evento"],
                "evento": row["evento"],
                "data_evento": row.get("data_evento"),
                "categoria_evento": row.get("categoria_evento"),
                "cidade": row.get("cidade"),
                "qtd_vendida_total": row.get("qtd_vendida", 0),
                "valor_total": row.get("inscricao_liquida", 0.0),
                "cortesia_total": row.get("cortesia", 0),
                "inscricao_liquida_total": row.get("inscricao_liquida", 0.0),
                "ticket_medio_total": row.get("ticket_medio", 0.0),
                "taxa_liquida_total": row.get("taxa_liquida", 0.0),
                "kit_produto_total": row.get("kit_produto", 0.0),
                "qtd_grupos_total": row.get("qtd_grupos", 0),
                "inscricao_liquida_grupos_total": row.get("inscricao_liquida_grupos", 0.0),
                "qtd_site_total": row.get("qtd_site", 0),
                "inscricao_liquida_site_total": row.get("inscricao_liquida_site", 0.0),
                "por_fonte": {
                    "ativo": None,
                    "magento": create_fonte_detalhe(row)
                }
            })
    
    if sku:
        dados = [d for d in dados if d["evento"] and sku.upper() in d["evento"].upper()]
    
    dados.sort(key=lambda x: x.get("data_evento") or "", reverse=False)
    
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
async def test_ativo_query(ano: int = 2026):
    if db_module.engine_ssh is None:
        return {"status": "error", "message": "SSH tunnel não configurado"}
    
    try:
        query = build_query_ativo(ano)
        logger.info(f"Iniciando query Ativo (ano={ano})...")
        with db_module.engine_ssh.connect() as conn:
            result = conn.execute(text(query))
            rows = result.fetchall()
            logger.info(f"Query Ativo retornou {len(rows)} linhas")
            return {
                "status": "success",
                "ano": ano,
                "total_rows": len(rows),
                "sample": [
                    {
                        "id_evento": str(row[0]),
                        "evento": row[1],
                        "data_evento": str(row[2]) if row[2] else None,
                        "qtd_total": int(row[3]) if row[3] else 0,
                        "cortesia": int(row[4]) if row[4] else 0,
                        "inscricao_liquida": float(row[5]) if row[5] else 0.0,
                        "ticket_medio": float(row[6]) if row[6] else 0.0,
                    }
                    for row in rows[:5]
                ]
            }
    except Exception as e:
        logger.error(f"Erro query Ativo: {e}")
        return {"status": "error", "message": str(e)}

@router.get("/test-magento")
async def test_magento_query(ano: int = 2026):
    if db_module.engine_magento is None:
        return {"status": "error", "message": "Conexão Magento não configurada"}
    
    try:
        query = build_query_magento(ano)
        logger.info(f"Iniciando query Magento (ano={ano})...")
        with db_module.engine_magento.connect() as conn:
            result = conn.execute(text(query))
            rows = result.fetchall()
            logger.info(f"Query Magento retornou {len(rows)} linhas")
            return {
                "status": "success",
                "ano": ano,
                "total_rows": len(rows),
                "sample": [
                    {
                        "id_evento": str(row[0]) if row[0] else None,
                        "evento": row[1],
                        "data_evento": str(row[2]) if row[2] else None,
                        "qtd_total": int(row[3]) if row[3] else 0,
                        "cortesia": int(row[4]) if row[4] else 0,
                        "inscricao_liquida": float(row[5]) if row[5] else 0.0,
                        "ticket_medio": float(row[6]) if row[6] else 0.0,
                    }
                    for row in rows[:5]
                ]
            }
    except Exception as e:
        logger.error(f"Erro query Magento: {e}")
        return {"status": "error", "message": str(e)}
