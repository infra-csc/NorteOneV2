from fastapi import APIRouter, HTTPException, Query, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session
from typing import Optional, List, Dict
from pydantic import BaseModel
import app.core.database as db_module
from app.core.database import get_db
from app.models.dimensoes import SkuMapping
from datetime import datetime, timedelta
from functools import partial
import logging
import re

logger = logging.getLogger(__name__)

router = APIRouter()


def get_sku_mappings_from_db(db: Session, ano: Optional[int] = None) -> Dict[str, Dict]:
    """
    Busca mapeamentos de SKU do PostgreSQL e retorna dicionários indexados.
    Retorna dois dicts:
    - by_ativo: {id_externo: {sku, evento_grupo, nome_evento, ano}}
    - by_magento: {id_externo: {sku, evento_grupo, nome_evento, ano}}
    """
    query = db.query(SkuMapping).filter(SkuMapping.ativo == True)
    if ano:
        query = query.filter(SkuMapping.ano == ano)
    
    mappings = query.all()
    
    by_ativo = {}
    by_magento = {}
    
    for m in mappings:
        data = {
            "sku": m.sku,
            "evento_grupo": m.evento_grupo,
            "nome_evento": m.nome_evento,
            "ano": m.ano
        }
        key = f"{m.id_externo}_{m.ano}"
        if m.fonte == "ATIVO":
            by_ativo[key] = data
        else:
            by_magento[key] = data
    
    return {"ativo": by_ativo, "magento": by_magento}


def enrich_with_mappings(data: List[Dict], mappings: Dict, fonte: str, ano: int) -> List[Dict]:
    """
    Enriquece dados vindos do MySQL com mapeamentos do PostgreSQL.
    Atualiza o SKU e adiciona evento_grupo para cada registro.
    Fallback: usa SKU normalizado como evento_grupo se não houver mapeamento.
    """
    mapping_dict = mappings.get(fonte, {})
    
    for row in data:
        id_evento = row.get("id_evento")
        if id_evento:
            key = f"{id_evento}_{ano}"
            if key in mapping_dict:
                mapping = mapping_dict[key]
                row["sku"] = mapping["sku"]
                row["evento_grupo"] = mapping["evento_grupo"]
            else:
                existing_sku = row.get("sku") or ""
                normalized = normalize_sku(existing_sku)
                if normalized and len(normalized) >= 6:
                    base_sku = normalized[:3] + normalized[5:]
                    row["evento_grupo"] = f"AUTO_{base_sku}"
                else:
                    row["evento_grupo"] = f"UNMAPPED_{fonte}_{id_evento}"
    
    return data

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
    Inclui mapeamento de id_evento para SKU.
    """
    return f"""
SELECT
    b.id_evento AS id_evento,
    CASE 
        WHEN b.id_evento = '40048' THEN 'CDE26PL1'
        WHEN b.id_evento = '40145' THEN 'CDE26RP1'
        WHEN b.id_evento = '39969' THEN 'CDE26RJ1'
        WHEN b.id_evento = '40120' THEN 'CDE26FL1'
        WHEN b.id_evento = '39996' THEN 'CDE26PA1'
        WHEN b.id_evento = '39964' THEN 'CDE26SP1'
        WHEN b.id_evento = '40052' THEN 'CDE26AN1'
        WHEN b.id_evento = '39974' THEN 'CDE26BH1'
        WHEN b.id_evento = '39970' THEN 'CDE26BS1'
        WHEN b.id_evento = '40001' THEN 'CDE26CP1'
        WHEN b.id_evento = '39986' THEN 'CDE26RC1'
        WHEN b.id_evento = '40010' THEN 'CDE26BL1'
        WHEN b.id_evento = '39980' THEN 'CDE26FT1'
        WHEN b.id_evento = '40149' THEN 'CDE26SJ1'
        WHEN b.id_evento = '39994' THEN 'CDE26CT1'
        WHEN b.id_evento = '40157' THEN 'CDE26TS1'
        WHEN b.id_evento = '40015' THEN 'CDE26VT1'
        WHEN b.id_evento = '40144' THEN 'CDE26MN4'
        WHEN b.id_evento = '40142' THEN 'CDE26MN2'
        WHEN b.id_evento = '40143' THEN 'CDE26MN3'
        WHEN b.id_evento = '39990' THEN 'CDE26SV1'
        WHEN b.id_evento = '40075' THEN 'TBT26ST1'
        WHEN b.id_evento = '40108' THEN 'NRU26RF1'
        WHEN b.id_evento = '40073' THEN 'BRV26SP4'
        WHEN b.id_evento = '39999' THEN 'CDE26PA2'
        WHEN b.id_evento = '39971' THEN 'CDE26RJ2'
        WHEN b.id_evento = '40122' THEN 'CDE26FL3'
        WHEN b.id_evento = '40121' THEN 'CDE26FL2'
        WHEN b.id_evento = '40076' THEN 'TBT26ST2'
        WHEN b.id_evento = '40049' THEN 'CDE26PL2'
        WHEN b.id_evento = '40158' THEN 'CDE26TS2'
        WHEN b.id_evento = '40072' THEN 'BRV26SP2'
        WHEN b.id_evento = '40150' THEN 'CDE26SJ2'
        WHEN b.id_evento = '40151' THEN 'CDE26SJ3'
        WHEN b.id_evento = '40146' THEN 'CDE26RP2'
        WHEN b.id_evento = '40053' THEN 'CDE26AN2'
        WHEN b.id_evento = '40003' THEN 'CDE26CP2'
        WHEN b.id_evento = '39987' THEN 'CDE26RC2'
        WHEN b.id_evento = '39965' THEN 'CDE26SP2'
        WHEN b.id_evento = '39975' THEN 'CDE26BS2'
        WHEN b.id_evento = '39982' THEN 'CDE26FT2'
        WHEN b.id_evento = '40107' THEN 'NRU26CW1'
        WHEN b.id_evento = '40074' THEN 'BRV26SJ1'
        WHEN b.id_evento = '39995' THEN 'CDE26CT2'
        WHEN b.id_evento = '40016' THEN 'CDE26VT2'
        WHEN b.id_evento = '39991' THEN 'CDE26SV2'
        WHEN b.id_evento = '40011' THEN 'CDE26BL2'
        WHEN b.id_evento = '40148' THEN 'CDE26RP4'
        WHEN b.id_evento = '40147' THEN 'CDE26RP3'
        WHEN b.id_evento = '39978' THEN 'CDE26BH2'
        WHEN b.id_evento = '40070' THEN 'AQA26RJ2'
        WHEN b.id_evento = '40050' THEN 'CDE26PL3'
        WHEN b.id_evento = '40054' THEN 'CDE26AN3'
        WHEN b.id_evento = '40005' THEN 'CDE26CP3'
        WHEN b.id_evento = '39983' THEN 'CDE26FT3'
        WHEN b.id_evento = '39976' THEN 'CDE26BS3'
        WHEN b.id_evento = '40017' THEN 'CDE26VT3'
        WHEN b.id_evento = '39988' THEN 'CDE26RC3'
        WHEN b.id_evento = '39966' THEN 'CDE26SP3'
        WHEN b.id_evento = '39997' THEN 'CDE26CT3'
        WHEN b.id_evento = '40159' THEN 'CDE26TS3'
        WHEN b.id_evento = '39992' THEN 'CDE26SV3'
        WHEN b.id_evento = '40012' THEN 'CDE26BL3'
        WHEN b.id_evento = '40077' THEN 'TBT26ST3'
        WHEN b.id_evento = '39972' THEN 'CDE26RJ3'
        WHEN b.id_evento = '40000' THEN 'CDE26PA3'
        WHEN b.id_evento = '40113' THEN 'NRU26FT1'
        WHEN b.id_evento = '40109' THEN 'NRU26SV1'
        WHEN b.id_evento = '40081' THEN 'NRU26RJ2'
        WHEN b.id_evento = '40112' THEN 'NRU26BS1'
        WHEN b.id_evento = '40063' THEN 'NRU26SP3'
        WHEN b.id_evento = '40123' THEN 'CDE26FL4'
        WHEN b.id_evento = '40105' THEN 'NRU26PA1'
        WHEN b.id_evento = '39973' THEN 'CDE26RJ4'
        WHEN b.id_evento = '40047' THEN 'CDE26PL4'
        WHEN b.id_evento = '40160' THEN 'CDE26TS4'
        WHEN b.id_evento = '40055' THEN 'CDE26AN4'
        WHEN b.id_evento = '39967' THEN 'CDE26SP4'
        WHEN b.id_evento = '40078' THEN 'TBT26ST4'
        WHEN b.id_evento = '40152' THEN 'CDE26SJ4'
        WHEN b.id_evento = '39998' THEN 'CDE26CT4'
        WHEN b.id_evento = '39985' THEN 'CDE26FT4'
        WHEN b.id_evento = '39993' THEN 'CDE26SV4'
        WHEN b.id_evento = '40014' THEN 'CDE26BL4'
        WHEN b.id_evento = '39984' THEN 'CDE26BH4'
        WHEN b.id_evento = '39977' THEN 'CDE26BS4'
        WHEN b.id_evento = '40002' THEN 'CDE26PA4'
        WHEN b.id_evento = '40004' THEN 'CDE26CP4'
        WHEN b.id_evento = '40018' THEN 'CDE26VT4'
        WHEN b.id_evento = '39989' THEN 'CDE26RC4'
        ELSE b.id_campanha_salesforce
    END AS sku,
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
    Inclui mapeamento de location_id para SKU.
    """
    return f"""
SELECT
    wl.location_id AS id_evento,
    CASE 
        WHEN wl.location_id = '587' THEN 'CPLIE26SP1'
        WHEN wl.location_id = '612' THEN 'BLU26RJ1'
        WHEN wl.location_id = '539' THEN 'CDE26PL4'
        WHEN wl.location_id = '536' THEN 'CDE26PL1'
        WHEN wl.location_id = '560' THEN 'CDE26TS4'
        WHEN wl.location_id = '559' THEN 'CDE26TS3'
        WHEN wl.location_id = '558' THEN 'CDE26TS2'
        WHEN wl.location_id = '537' THEN 'CDE26PL2'
        WHEN wl.location_id = '557' THEN 'CDE26TS1'
        WHEN wl.location_id = '510' THEN 'NRU26PA1'
        WHEN wl.location_id = '438' THEN 'CDE26RJ4'
        WHEN wl.location_id = '437' THEN 'CDE26RJ3'
        WHEN wl.location_id = '436' THEN 'CDE26RJ2'
        WHEN wl.location_id = '462' THEN 'CDE26SV4'
        WHEN wl.location_id = '464' THEN 'CDE26SV3'
        WHEN wl.location_id = '463' THEN 'CDE26SV2'
        WHEN wl.location_id = '469' THEN 'CDE26CP4'
        WHEN wl.location_id = '470' THEN 'CDE26CP3'
        WHEN wl.location_id = '471' THEN 'CDE26CP2'
        WHEN wl.location_id = '441' THEN 'CDE26SP2'
        WHEN wl.location_id = '443' THEN 'CDE26SP4'
        WHEN wl.location_id = '455' THEN 'CDE26FT4'
        WHEN wl.location_id = '454' THEN 'CDE26FT3'
        WHEN wl.location_id = '453' THEN 'CDE26FT2'
        WHEN wl.location_id = '466' THEN 'CDE26CT2'
        WHEN wl.location_id = '518' THEN 'NRU26FT1'
        WHEN wl.location_id = '513' THEN 'NRU26VT1'
        WHEN wl.location_id = '446' THEN 'CDE26BS3'
        WHEN wl.location_id = '444' THEN 'CDE26BS2'
        WHEN wl.location_id = '449' THEN 'CDE26BH2'
        WHEN wl.location_id = '473' THEN 'CDE26PA4'
        WHEN wl.location_id = '474' THEN 'CDE26PA3'
        WHEN wl.location_id = '475' THEN 'CDE26PA2'
        WHEN wl.location_id = '468' THEN 'CDE26CT4'
        WHEN wl.location_id = '467' THEN 'CDE26CT3'
        WHEN wl.location_id = '447' THEN 'CDE26BS4'
        WHEN wl.location_id = '544' THEN 'GPW26SP11'
        WHEN wl.location_id = '442' THEN 'CDE26SP3'
        WHEN wl.location_id = '451' THEN 'CDE26BH4'
        WHEN wl.location_id = '519' THEN 'NRU26SV1'
        WHEN wl.location_id = '516' THEN 'NRU26BS1'
        WHEN wl.location_id = '515' THEN 'NRU26RF1'
        WHEN wl.location_id = '521' THEN 'NRU26CP1'
        WHEN wl.location_id = '491' THEN 'BRV26SP1'
        WHEN wl.location_id = '512' THEN 'NRU26CW1'
        WHEN wl.location_id = '481' THEN 'NRU26SP3'
        WHEN wl.location_id = '492' THEN 'BRV26SP4'
        ELSE d.sku
    END AS sku,
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
LEFT JOIN catalog_product_entity_varchar AS pai ON pai.entity_id = soi.product_id AND pai.attribute_id = 321
LEFT JOIN catalog_product_entity AS d ON pai.value = d.entity_id
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
                    "sku": row[1] if row[1] else None,
                    "evento": row[2],
                    "data_evento": str(row[3]) if row[3] else None,
                    "qtd_vendida": int(row[4]) if row[4] else 0,
                    "cortesia": int(row[5]) if row[5] else 0,
                    "inscricao_liquida": float(row[6]) if row[6] else 0.0,
                    "ticket_medio": float(row[7]) if row[7] else 0.0,
                    "taxa_liquida": float(row[8]) if row[8] else 0.0,
                    "kit_produto": float(row[9]) if row[9] else 0.0,
                    "qtd_grupos": int(row[10]) if row[10] else 0,
                    "inscricao_liquida_grupos": float(row[11]) if row[11] else 0.0,
                    "ticket_medio_grupos": float(row[12]) if row[12] else 0.0,
                    "qtd_site": int(row[13]) if row[13] else 0,
                    "inscricao_liquida_site": float(row[14]) if row[14] else 0.0,
                    "ticket_medio_site": float(row[15]) if row[15] else 0.0,
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
                    "sku": row[1] if row[1] else None,
                    "evento": row[2],
                    "data_evento": str(row[3]) if row[3] else None,
                    "qtd_vendida": int(row[4]) if row[4] else 0,
                    "cortesia": int(row[5]) if row[5] else 0,
                    "inscricao_liquida": float(row[6]) if row[6] else 0.0,
                    "ticket_medio": float(row[7]) if row[7] else 0.0,
                    "taxa_liquida": float(row[8]) if row[8] else 0.0,
                    "kit_produto": float(row[9]) if row[9] else 0.0,
                    "qtd_grupos": int(row[10]) if row[10] else 0,
                    "inscricao_liquida_grupos": float(row[11]) if row[11] else 0.0,
                    "ticket_medio_grupos": float(row[12]) if row[12] else 0.0,
                    "qtd_site": int(row[13]) if row[13] else 0,
                    "inscricao_liquida_site": float(row[14]) if row[14] else 0.0,
                    "ticket_medio_site": float(row[15]) if row[15] else 0.0,
                    "categoria_evento": row[16] if row[16] else None,
                    "cidade": row[17] if row[17] else None,
                }
                for row in rows
            ], None
    except Exception as e:
        logger.error(f"Erro banco Magento: {e}")
        return None, f"Query timeout ou erro: {str(e)[:100]}"

@router.get("/consolidado", response_model=InscricoesConsolidadasResponse)
def get_inscricoes_consolidadas(
    sku: Optional[str] = Query(None, description="Filtrar por SKU específico"),
    incluir_magento: bool = Query(True, description="Incluir dados do Magento"),
    ano: int = Query(2026, description="Ano do evento para filtrar (default: 2026)")
):
    from concurrent.futures import ThreadPoolExecutor, wait as futures_wait
    executor = ThreadPoolExecutor(max_workers=2)
    
    ativo_future = executor.submit(fetch_ativo_data, ano)
    
    magento_result = None
    magento_error = None
    
    if incluir_magento:
        magento_future = executor.submit(fetch_magento_data, ano)
        try:
            done, not_done = futures_wait([ativo_future, magento_future], timeout=90.0)
            if ativo_future.done():
                result = ativo_future.result()
                ativo_result, ativo_error = result if not isinstance(result, Exception) else (None, str(result))
            else:
                ativo_result, ativo_error = None, "Timeout"
            if magento_future.done():
                result = magento_future.result()
                magento_result, magento_error = result if not isinstance(result, Exception) else (None, str(result))
            else:
                magento_result, magento_error = None, "Timeout após 90 segundos"
        except Exception:
            ativo_result, ativo_error = ativo_future.result() if ativo_future.done() else (None, "Timeout")
            magento_error = "Timeout após 90 segundos"
    else:
        ativo_result, ativo_error = ativo_future.result()
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
    
    eventos_consolidados = {}
    
    if ativo_result:
        for row in ativo_result:
            sku_key = row.get("sku") or ""
            evento_nome = row.get("evento") or ""
            data_evento = row.get("data_evento") or ""
            
            if sku_key not in eventos_consolidados:
                eventos_consolidados[sku_key] = {
                    "sku": sku_key,
                    "id_evento": row["id_evento"],
                    "evento": evento_nome,
                    "data_evento": data_evento,
                    "categoria_evento": None,
                    "cidade": None,
                    "ativo_data": create_fonte_detalhe(row),
                    "magento_data": None
                }
            else:
                existing = eventos_consolidados[sku_key].get("ativo_data")
                if existing:
                    new_data = create_fonte_detalhe(row)
                    for k in ["qtd", "cortesia", "qtd_grupos", "qtd_site"]:
                        existing[k] = existing.get(k, 0) + new_data.get(k, 0)
                    for k in ["valor", "inscricao_liquida", "taxa_liquida", "kit_produto", 
                              "inscricao_liquida_grupos", "inscricao_liquida_site"]:
                        existing[k] = existing.get(k, 0.0) + new_data.get(k, 0.0)
                else:
                    eventos_consolidados[sku_key]["ativo_data"] = create_fonte_detalhe(row)
    
    if magento_result:
        for row in magento_result:
            sku_key = row.get("sku") or ""
            evento_nome = row.get("evento") or ""
            data_evento = row.get("data_evento") or ""
            
            if sku_key not in eventos_consolidados:
                eventos_consolidados[sku_key] = {
                    "sku": sku_key,
                    "id_evento": row["id_evento"],
                    "evento": evento_nome,
                    "data_evento": data_evento,
                    "categoria_evento": row.get("categoria_evento"),
                    "cidade": row.get("cidade"),
                    "ativo_data": None,
                    "magento_data": create_fonte_detalhe(row)
                }
            else:
                eventos_consolidados[sku_key]["categoria_evento"] = row.get("categoria_evento")
                eventos_consolidados[sku_key]["cidade"] = row.get("cidade")
                if not eventos_consolidados[sku_key]["evento"]:
                    eventos_consolidados[sku_key]["evento"] = evento_nome
                if not eventos_consolidados[sku_key]["data_evento"]:
                    eventos_consolidados[sku_key]["data_evento"] = data_evento
                existing = eventos_consolidados[sku_key].get("magento_data")
                if existing:
                    new_data = create_fonte_detalhe(row)
                    for k in ["qtd", "cortesia", "qtd_grupos", "qtd_site"]:
                        existing[k] = existing.get(k, 0) + new_data.get(k, 0)
                    for k in ["valor", "inscricao_liquida", "taxa_liquida", "kit_produto",
                              "inscricao_liquida_grupos", "inscricao_liquida_site"]:
                        existing[k] = existing.get(k, 0.0) + new_data.get(k, 0.0)
                else:
                    eventos_consolidados[sku_key]["magento_data"] = create_fonte_detalhe(row)
    
    dados = []
    for evento_key, ev in eventos_consolidados.items():
        ativo = ev.get("ativo_data") or {}
        magento = ev.get("magento_data") or {}
        
        qtd_total = ativo.get("qtd", 0) + magento.get("qtd", 0)
        inscricao_total = ativo.get("inscricao_liquida", 0.0) + magento.get("inscricao_liquida", 0.0)
        
        dados.append({
            "sku": ev["sku"],
            "id_evento": ev["id_evento"],
            "evento": ev["evento"],
            "data_evento": ev["data_evento"],
            "categoria_evento": ev.get("categoria_evento"),
            "cidade": ev.get("cidade"),
            "qtd_vendida_total": qtd_total,
            "valor_total": inscricao_total,
            "cortesia_total": ativo.get("cortesia", 0) + magento.get("cortesia", 0),
            "inscricao_liquida_total": inscricao_total,
            "ticket_medio_total": inscricao_total / qtd_total if qtd_total > 0 else 0.0,
            "taxa_liquida_total": ativo.get("taxa_liquida", 0.0) + magento.get("taxa_liquida", 0.0),
            "kit_produto_total": ativo.get("kit_produto", 0.0) + magento.get("kit_produto", 0.0),
            "qtd_grupos_total": ativo.get("qtd_grupos", 0) + magento.get("qtd_grupos", 0),
            "inscricao_liquida_grupos_total": ativo.get("inscricao_liquida_grupos", 0.0) + magento.get("inscricao_liquida_grupos", 0.0),
            "qtd_site_total": ativo.get("qtd_site", 0) + magento.get("qtd_site", 0),
            "inscricao_liquida_site_total": ativo.get("inscricao_liquida_site", 0.0) + magento.get("inscricao_liquida_site", 0.0),
            "por_fonte": {
                "ativo": ev.get("ativo_data"),
                "magento": ev.get("magento_data")
            }
        })
    
    if sku:
        dados = [d for d in dados if d["sku"] and sku.upper() in d["sku"].upper()]
    
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
def get_inscricoes_por_projeto(codigo_sku: str):
    from concurrent.futures import ThreadPoolExecutor
    executor = ThreadPoolExecutor(max_workers=2)
    
    ativo_future = executor.submit(fetch_ativo_data)
    magento_future = executor.submit(fetch_magento_data)
    
    ativo_result, ativo_error = ativo_future.result()
    magento_result, magento_error = magento_future.result()
    
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
def test_ativo_query(ano: int = 2026):
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
def test_magento_query(ano: int = 2026):
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


class ComparacaoAnoEvento(BaseModel):
    evento_grupo: str
    nome_evento: str
    ano_atual: int
    ano_anterior: int
    qtd_atual: int
    qtd_anterior: int
    variacao_qtd: float
    inscricao_atual: float
    inscricao_anterior: float
    variacao_inscricao: float
    ticket_atual: float
    ticket_anterior: float
    variacao_ticket: float


class ComparacaoAnoResponse(BaseModel):
    status: str
    ano_atual: int
    ano_anterior: int
    total_grupos: int
    eventos: List[ComparacaoAnoEvento]


@router.get("/comparativo-anual", response_model=ComparacaoAnoResponse)
def get_comparativo_anual(
    ano_atual: int = Query(2026, description="Ano atual para comparação"),
    ano_anterior: int = Query(2025, description="Ano anterior para comparação"),
    db: Session = Depends(get_db)
):
    """
    Compara dados de eventos entre dois anos usando o evento_grupo como chave.
    Permite analisar a performance do mesmo evento em anos diferentes.
    """
    from concurrent.futures import ThreadPoolExecutor, wait as futures_wait
    executor = ThreadPoolExecutor(max_workers=4)
    
    mappings = get_sku_mappings_from_db(db)
    
    atual_ativo_future = executor.submit(fetch_ativo_data, ano_atual)
    atual_magento_future = executor.submit(fetch_magento_data, ano_atual)
    anterior_ativo_future = executor.submit(fetch_ativo_data, ano_anterior)
    anterior_magento_future = executor.submit(fetch_magento_data, ano_anterior)
    
    futures = [atual_ativo_future, atual_magento_future, anterior_ativo_future, anterior_magento_future]
    done, not_done = futures_wait(futures, timeout=120.0)
    if not_done:
        raise HTTPException(status_code=504, detail="Timeout ao buscar dados dos bancos externos")
    
    try:
        results = [f.result() for f in futures]
    except Exception:
        raise HTTPException(status_code=504, detail="Timeout ao buscar dados dos bancos externos")
    
    atual_ativo = results[0][0] if not isinstance(results[0], Exception) and results[0][0] else []
    atual_magento = results[1][0] if not isinstance(results[1], Exception) and results[1][0] else []
    anterior_ativo = results[2][0] if not isinstance(results[2], Exception) and results[2][0] else []
    anterior_magento = results[3][0] if not isinstance(results[3], Exception) and results[3][0] else []
    
    atual_ativo = enrich_with_mappings(atual_ativo, mappings, "ativo", ano_atual)
    atual_magento = enrich_with_mappings(atual_magento, mappings, "magento", ano_atual)
    anterior_ativo = enrich_with_mappings(anterior_ativo, mappings, "ativo", ano_anterior)
    anterior_magento = enrich_with_mappings(anterior_magento, mappings, "magento", ano_anterior)
    
    def consolidate_by_grupo(data_list: List[List[Dict]]) -> Dict[str, Dict]:
        consolidated = {}
        for data in data_list:
            for row in data:
                grupo = row.get("evento_grupo")
                if not grupo:
                    continue
                
                if grupo not in consolidated:
                    consolidated[grupo] = {
                        "nome_evento": row.get("evento") or row.get("sku") or grupo,
                        "qtd": 0,
                        "inscricao": 0.0,
                        "cortesia": 0
                    }
                
                consolidated[grupo]["qtd"] += row.get("qtd_vendida", 0)
                consolidated[grupo]["inscricao"] += row.get("inscricao_liquida", 0.0)
                consolidated[grupo]["cortesia"] += row.get("cortesia", 0)
        
        return consolidated
    
    dados_atual = consolidate_by_grupo([atual_ativo, atual_magento])
    dados_anterior = consolidate_by_grupo([anterior_ativo, anterior_magento])
    
    todos_grupos = set(dados_atual.keys()) | set(dados_anterior.keys())
    
    eventos_comparados = []
    for grupo in sorted(todos_grupos):
        atual = dados_atual.get(grupo, {"nome_evento": grupo, "qtd": 0, "inscricao": 0.0})
        anterior = dados_anterior.get(grupo, {"nome_evento": grupo, "qtd": 0, "inscricao": 0.0})
        
        qtd_atual = atual["qtd"]
        qtd_anterior = anterior["qtd"]
        inscricao_atual = atual["inscricao"]
        inscricao_anterior = anterior["inscricao"]
        
        ticket_atual = inscricao_atual / qtd_atual if qtd_atual > 0 else 0.0
        ticket_anterior = inscricao_anterior / qtd_anterior if qtd_anterior > 0 else 0.0
        
        variacao_qtd = ((qtd_atual - qtd_anterior) / qtd_anterior * 100) if qtd_anterior > 0 else (100.0 if qtd_atual > 0 else 0.0)
        variacao_inscricao = ((inscricao_atual - inscricao_anterior) / inscricao_anterior * 100) if inscricao_anterior > 0 else (100.0 if inscricao_atual > 0 else 0.0)
        variacao_ticket = ((ticket_atual - ticket_anterior) / ticket_anterior * 100) if ticket_anterior > 0 else (100.0 if ticket_atual > 0 else 0.0)
        
        eventos_comparados.append(ComparacaoAnoEvento(
            evento_grupo=grupo,
            nome_evento=atual.get("nome_evento") or anterior.get("nome_evento") or grupo,
            ano_atual=ano_atual,
            ano_anterior=ano_anterior,
            qtd_atual=qtd_atual,
            qtd_anterior=qtd_anterior,
            variacao_qtd=round(variacao_qtd, 2),
            inscricao_atual=round(inscricao_atual, 2),
            inscricao_anterior=round(inscricao_anterior, 2),
            variacao_inscricao=round(variacao_inscricao, 2),
            ticket_atual=round(ticket_atual, 2),
            ticket_anterior=round(ticket_anterior, 2),
            variacao_ticket=round(variacao_ticket, 2)
        ))
    
    eventos_comparados.sort(key=lambda x: x.qtd_atual, reverse=True)
    
    return ComparacaoAnoResponse(
        status="success",
        ano_atual=ano_atual,
        ano_anterior=ano_anterior,
        total_grupos=len(eventos_comparados),
        eventos=eventos_comparados
    )
