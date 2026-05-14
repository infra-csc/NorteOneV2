from fastapi import APIRouter, HTTPException, Query, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session
from typing import Optional, List, Dict
from pydantic import BaseModel
import app.core.database as db_module
from app.core.database import get_db
from ...core.security import get_current_user
from app.models.dimensoes import SkuMapping
from datetime import datetime  # noqa: F401 - used by callers via from .inscricoes_consolidado import
import logging
import re

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(get_current_user)])


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
        key = f"{str(m.id_externo).strip()}_{m.ano}"
        if m.fonte == "ATIVO":
            by_ativo[key] = data
        else:
            by_magento[key] = data
    
    return {"ativo": by_ativo, "magento": by_magento}


def enrich_with_mappings(data: List[Dict], mappings: Dict, fonte: str, ano: int = None) -> List[Dict]:
    """
    Enriquece dados vindos do MySQL com mapeamentos do PostgreSQL.
    Atualiza o SKU e adiciona evento_grupo para cada registro.
    Fallback: usa SKU normalizado como evento_grupo se não houver mapeamento.
    Tenta encontrar mapeamento com múltiplos anos se o ano específico não for encontrado.
    """
    mapping_dict = mappings.get(fonte, {})
    
    all_years = set()
    for k in mapping_dict:
        parts = k.rsplit("_", 1)
        if len(parts) == 2 and parts[1].isdigit():
            all_years.add(int(parts[1]))
    
    for row in data:
        id_evento = row.get("id_evento")
        if id_evento:
            id_str = str(id_evento).strip()
            found = False
            
            if ano:
                key = f"{id_str}_{ano}"
                if key in mapping_dict:
                    mapping = mapping_dict[key]
                    row["sku"] = mapping["sku"]
                    row["evento_grupo"] = mapping["evento_grupo"]
                    if mapping.get("nome_evento"):
                        row["evento"] = mapping["nome_evento"]
                    found = True
            
            if not found:
                for try_year in sorted(all_years, reverse=True):
                    key = f"{id_str}_{try_year}"
                    if key in mapping_dict:
                        mapping = mapping_dict[key]
                        row["sku"] = mapping["sku"]
                        row["evento_grupo"] = mapping["evento_grupo"]
                        if mapping.get("nome_evento"):
                            row["evento"] = mapping["nome_evento"]
                        found = True
                        break
            
            if not found:
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

def normalize_evento_name(name: str) -> str:
    if not name:
        return name
    replacements = [
        ('Retirada de kit - CE', 'Circuito das Estações'),
        ('Retirada de Kit - CE', 'Circuito das Estações'),
        ('Retirada de KIt - CE', 'Circuito das Estações'),
        ('Retirada de Kit- CE', 'Circuito das Estações'),
        ('Retirada de Kit - ', ''),
        ('Retirada de kit - ', ''),
        ('SSA', 'Salvador'),
    ]
    for old, new in replacements:
        name = name.replace(old, new)
    return name


def classify_event_category(name: str) -> str:
    if not name:
        return 'Outra Categoria'
    name_lower = name.lower()
    patterns = [
        ('night run', 'Night Run'),
        (' ce ', 'Circuito das Estações'),
        ('verão', 'Circuito das Estações'),
        ('banco', 'Banco Do Brasil'),
        ('eco run', 'Eco Run'),
        ('girl', 'Girl Power'),
        ('gilr', 'Girl Power'),
        ('meia', 'Meias e Maratonas'),
        ('maratona', 'Meias e Maratonas'),
        ('21k', 'Meias e Maratonas'),
        ('rios', 'Meias e Maratonas'),
        ('floripa', 'Meias e Maratonas'),
        ('tis', 'Meias e Maratonas'),
        ('s21', 'Meias e Maratonas'),
        ('sol', 'Circuito Sol'),
        ('treinão', 'Treinão'),
        ('running', 'Treinão'),
        ('teste', 'Treinão'),
        ('testar', 'Treinão'),
        ('cruz', 'Vera Cruz'),
        ('bravus', 'Bravus'),
        ('bem', 'Corrida do Bem'),
        ('triathlon', 'Triathlon'),
        ('parcel', 'Triathlon'),
        ('ilha', 'Triathlon'),
        ('estações', 'Circuito das Estações'),
        ('primavera', 'Circuito das Estações'),
        ('outono', 'Circuito das Estações'),
        ('troféu', 'Troféu Brasil'),
        ('eco', 'Eco Run'),
        ('bull', 'Bull Run'),
        ('juntos', 'Juntos'),
        ('blue', 'Blue Run'),
        ('energy', 'Energy'),
        ('pedelar', 'Eventos de Ciclismo'),
        ('bike', 'Eventos de Ciclismo'),
        ('riders', 'Eventos de Ciclismo'),
        ('humans', 'Humans'),
        ('s run', 'S RUN'),
        ('agro', 'Agro'),
        ('pão', 'Pão De Açucar'),
        ('biomas', 'Biomas'),
    ]
    for pattern, category in patterns:
        if pattern in name_lower:
            return category
    return 'Outra Categoria'


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
    Retorna métricas financeiras: receita bruta, desconto, receita líquida e ticket médio,
    agrupados por evento.
    Filtra apenas inscrições site (fl_local_inscricao = 1), exclui grupos e cortesias.
    Colunas (índices): 0=id_evento, 1=evento, 2=qtd_site, 3=receita_bruta,
                       4=total_desconto, 5=receita_liquida, 6=ticket_medio, 7=data_evento
    """
    return f"""
SELECT /*+ MAX_EXECUTION_TIME(60000) */
    b.id_evento                                                                    AS id_evento,
    b.ds_evento                                                                    AS evento,
    COUNT(DISTINCT a.id_pedido_evento)                                             AS qtd_site,
    SUM(a.nr_preco)                                                                AS receita_bruta,
    SUM(COALESCE(a.nr_desconto_individual, 0))                                     AS total_desconto,
    SUM(GREATEST(a.nr_preco - COALESCE(a.nr_desconto_individual, 0) - COALESCE(h.vl_kit, 0), 0)) AS receita_liquida,
    (
        SUM(a.nr_preco)
        - SUM(COALESCE(a.nr_desconto_individual, 0))
    ) / NULLIF(COUNT(DISTINCT a.id_pedido_evento), 0)                              AS ticket_medio,
    MIN(DATE(b.dt_evento))                                                         AS data_evento
FROM sa_evento AS b
INNER JOIN sa_pedido_evento AS a
    ON a.id_evento = b.id_evento
INNER JOIN sa_pedido AS c
    ON c.id_pedido = a.id_pedido
    AND c.fl_local_inscricao = '1'
    AND c.id_pedido_status IN (1, 2)
    AND c.nr_total > 0
LEFT JOIN sa_modalidade_categoria AS h
    ON h.id_categoria = a.id_categoria
LEFT JOIN sa_cupom_desconto_item AS e
    ON e.id_cupom_desconto_item = a.id_cupom_individual
LEFT JOIN sa_cupom_desconto AS f
    ON f.id_cupom_desconto = e.id_cupom_desconto
WHERE
    b.dt_evento BETWEEN '{ano}-01-01' AND '{ano}-12-31'
    AND (b.id_campanha_salesforce IS NULL
         OR b.id_campanha_salesforce NOT LIKE '701d0000000%')
    AND c.nr_total > 0
    AND (h.ds_categoria IS NULL
         OR (h.ds_categoria NOT LIKE '%Grup%'
         AND h.ds_categoria NOT LIKE '%ortesia%'))
    AND (
        f.en_cupom_classificacao IS NULL
        OR f.en_cupom_classificacao NOT IN (
            'Funcionário',
            'Cortesia Faturada',
            'Grupos',
            'Coligados'
        )
    )
GROUP BY
    b.id_evento,
    b.ds_evento
ORDER BY
    b.id_evento
"""

def build_query_magento(ano: int) -> str:
    """
    Constroi query do Magento filtrando por ano do evento (atributo 195 - data evento).
    Retorna métricas financeiras: receita bruta (descontando personalização), receita líquida
    (descontando desconto aplicado nos filhos) e ticket médio, agrupados por evento (atributo 321).
    Colunas (índices): 0=id_evento, 1=evento, 2=qtd_site, 3=receita_bruta,
                       4=receita_liquida, 5=ticket_medio, 6=data_evento
    """
    return f"""
SELECT /*+ MAX_EXECUTION_TIME(60000) */
    cpev1.value                                                                                                                           AS id_evento,
    cpev2.value                                                                                                                           AS evento,
    COUNT(DISTINCT soi.item_id)                                                                                                           AS qtd_site,
    SUM(soi.price - COALESCE(soi_virtual.price_personalizacao, 0))                                                                        AS receita_bruta,
    SUM(soi.price - COALESCE(soi_virtual.price_personalizacao, 0)) - COALESCE(SUM(soi_children.discount_invoiced), 0)                     AS receita_liquida,
    (SUM(soi.price - COALESCE(soi_virtual.price_personalizacao, 0)) - COALESCE(SUM(soi_children.discount_invoiced), 0))
        / NULLIF(COUNT(DISTINCT soi.item_id), 0)                                                                                          AS ticket_medio,
    MIN(cped.value)                                                                                                                        AS data_evento
FROM sales_order so
LEFT JOIN sales_order_item soi
    ON soi.order_id = so.entity_id
    AND soi.product_type = 'bundle'
LEFT JOIN (
    SELECT parent_item_id, SUM(discount_invoiced) AS discount_invoiced
    FROM sales_order_item
    WHERE product_type = 'simple'
      AND parent_item_id IS NOT NULL
    GROUP BY parent_item_id
) AS soi_children ON soi_children.parent_item_id = soi.item_id
LEFT JOIN (
    SELECT parent_item_id, SUM(price) AS price_personalizacao
    FROM sales_order_item
    WHERE product_type = 'virtual'
      AND parent_item_id IS NOT NULL
      AND name LIKE '%ersonaliz%'
    GROUP BY parent_item_id
) AS soi_virtual ON soi_virtual.parent_item_id = soi.item_id
LEFT JOIN (
    SELECT entity_id, MIN(value) AS value
    FROM catalog_product_entity_varchar
    WHERE attribute_id = 321
    GROUP BY entity_id
) AS cpev1 ON soi.product_id = cpev1.entity_id
LEFT JOIN (
    SELECT entity_id, MIN(value) AS value
    FROM catalog_product_entity_varchar
    WHERE attribute_id = 73
    GROUP BY entity_id
) AS cpev2 ON cpev1.value = cpev2.entity_id
LEFT JOIN (
    SELECT entity_id, MIN(value) AS value
    FROM catalog_product_entity_datetime
    WHERE attribute_id = 195
    GROUP BY entity_id
) AS cped ON cpev1.value = cped.entity_id
WHERE
    so.status IN ('processing', 'complete', 'approved', 'aprovado_link', 'reembolso_parcial')
    AND so.state != 'canceled'
    AND cped.value BETWEEN '{ano}-01-01' AND '{ano}-12-31'
    AND soi.sku NOT LIKE '%CORTESIA%'
    AND soi.price > 0
    AND so.base_grand_total > 0
    AND (so.discount_description IS NULL OR so.discount_description NOT LIKE '%Grup%')
    AND so.increment_id NOT REGEXP '-[0-9]'
GROUP BY
    cpev1.value,
    cpev2.value
ORDER BY
    cpev2.value ASC
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
                    "sku": None,
                    "evento": row[1],
                    "data_evento": str(row[7]) if row[7] else None,
                    "qtd_vendida": int(row[2]) if row[2] else 0,
                    "cortesia": 0,
                    "inscricao_liquida": float(row[5]) if row[5] else 0.0,
                    "ticket_medio": float(row[6]) if row[6] else 0.0,
                    "taxa_liquida": 0.0,
                    "kit_produto": 0.0,
                    "receita_bruta": float(row[3]) if row[3] else 0.0,
                    "total_desconto": float(row[4]) if row[4] else 0.0,
                    "qtd_grupos": 0,
                    "inscricao_liquida_grupos": 0.0,
                    "ticket_medio_grupos": 0.0,
                    "qtd_site": int(row[2]) if row[2] else 0,
                    "inscricao_liquida_site": float(row[5]) if row[5] else 0.0,
                    "ticket_medio_site": float(row[6]) if row[6] else 0.0,
                    "valor_total": float(row[3]) if row[3] else 0.0,
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
        from app.core.db_retry import magento_run
        query = build_query_magento(ano)
        logger.info(f"Buscando dados do banco Magento (ano={ano})...")

        def _fetch_work(conn):
            return conn.execute(text(query)).fetchall()

        rows = magento_run(_fetch_work, label=f"inscricoes-consolidado:fetch-magento:{ano}", profile="request")
        logger.info(f"Banco Magento: {len(rows)} registros para {ano}")
        return [
            {
                "id_evento": str(row[0]) if row[0] else None,
                "sku": None,
                "evento": normalize_evento_name(row[1]) if row[1] else None,
                "data_evento": str(row[6]) if row[6] else None,
                "qtd_vendida": int(row[2]) if row[2] else 0,
                "cortesia": 0,
                "inscricao_liquida": float(row[4]) if row[4] else 0.0,
                "ticket_medio": float(row[5]) if row[5] else 0.0,
                "taxa_liquida": 0.0,
                "kit_produto": 0.0,
                "receita_bruta": float(row[3]) if row[3] else 0.0,
                "total_desconto": 0.0,
                "qtd_grupos": 0,
                "inscricao_liquida_grupos": 0.0,
                "ticket_medio_grupos": 0.0,
                "qtd_site": int(row[2]) if row[2] else 0,
                "inscricao_liquida_site": float(row[4]) if row[4] else 0.0,
                "ticket_medio_site": float(row[5]) if row[5] else 0.0,
                "categoria_evento": classify_event_category(row[1]) if row[1] else None,
                "cidade": None,
                "valor_total": float(row[3]) if row[3] else 0.0,
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
    ano: int = Query(2026, description="Ano do evento para filtrar (default: 2026)"),
    db: Session = Depends(get_db)
):
    from concurrent.futures import ThreadPoolExecutor, wait as futures_wait
    
    mappings = get_sku_mappings_from_db(db, ano)
    
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
    
    if ativo_result:
        ativo_result = enrich_with_mappings(ativo_result, mappings, "ativo", ano)
    if magento_result:
        magento_result = enrich_with_mappings(magento_result, mappings, "magento", ano)
    
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
                        "id_evento": str(row[0]) if row[0] else None,
                        "evento": row[1],
                        "qtd_site": int(row[2]) if row[2] else 0,
                        "receita_bruta": float(row[3]) if row[3] else 0.0,
                        "total_taxa": float(row[4]) if row[4] else 0.0,
                        "total_produtos": float(row[5]) if row[5] else 0.0,
                        "total_desconto": float(row[6]) if row[6] else 0.0,
                        "receita_liquida": float(row[7]) if row[7] else 0.0,
                        "ticket_medio": float(row[8]) if row[8] else 0.0,
                        "data_evento": str(row[9]) if row[9] else None,
                    }
                    for row in rows[:5]
                ]
            }
    except Exception as e:
        logger.error(f"Erro query Ativo: {e}")
        return {"status": "error", "message": "Erro interno ao consultar banco Ativo"}

@router.get("/test-magento")
def test_magento_query(ano: int = 2026):
    if db_module.engine_magento is None:
        return {"status": "error", "message": "Conexão Magento não configurada"}
    
    try:
        from app.core.db_retry import magento_run
        query = build_query_magento(ano)
        logger.info(f"Iniciando query Magento (ano={ano})...")

        def _debug_query_work(conn):
            return conn.execute(text(query)).fetchall()

        rows = magento_run(_debug_query_work, label=f"inscricoes-consolidado:debug-magento:{ano}", profile="request")
        logger.info(f"Query Magento retornou {len(rows)} linhas")
        return {
            "status": "success",
            "ano": ano,
            "total_rows": len(rows),
            "sample": [
                {
                    "id_evento": str(row[0]) if row[0] else None,
                    "evento": row[1],
                    "qtd_site": int(row[2]) if row[2] else 0,
                    "receita_bruta": float(row[3]) if row[3] else 0.0,
                    "total_taxa": float(row[4]) if row[4] else 0.0,
                    "total_produtos": float(row[5]) if row[5] else 0.0,
                    "total_desconto": float(row[6]) if row[6] else 0.0,
                    "receita_liquida": float(row[7]) if row[7] else 0.0,
                    "ticket_medio": float(row[8]) if row[8] else 0.0,
                    "data_evento": str(row[9]) if row[9] else None,
                }
                for row in rows[:5]
            ]
        }
    except Exception as e:
        logger.error(f"Erro query Magento: {e}")
        return {"status": "error", "message": "Erro interno ao consultar banco Magento"}


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
