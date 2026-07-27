"""
Queries SQL para o Detalhamento de Eventos.

Cada função retorna (sql: str, params: dict) para uso com
SQLAlchemy text() + bind params — nunca interpolação direta de input externo.
Os IDs passados são sempre inteiros provenientes de sku_mappings (banco próprio),
validados como int antes de chamada; usamos bind params nomeados para conformidade.

CONTRATO de colunas (ordem fixa):
  banco, id_evento, evento, canal, kit, modalidade,
  pelotao, produtos, tamanho_camiseta,
  inscritos, receita_bruta, receita_liquida, ticket_medio

Nota: a coluna 'distancia' foi removida em Jun/2026. A granularidade de
distância passou a ser mapeada como 'modalidade' em ambos os bancos.
No Ativo, a coluna era 'ds_modalidade' via join sa_evento_modalidade (id_evento);
no Magento, era o CASE block de soi_child.name — ambos agora chamados 'modalidade'.
"""
from typing import Optional, List, Tuple, Dict


def _validate_ids(ids: List[int]) -> None:
    for v in ids:
        if not isinstance(v, int):
            raise TypeError(f"ID inválido (esperado int): {v!r}")


def build_ativo_detalhe(ids: Optional[List[int]] = None) -> Tuple[str, Dict]:
    """
    Retorna (sql, params) para query Ativo.
    Quando ids é fornecido, gera cláusula IN parametrizada com bind params nomeados.
    """
    params: Dict = {}
    ids_clause = ""

    if ids:
        _validate_ids(ids)
        param_names = [f"ativo_id_{i}" for i in range(len(ids))]
        placeholders = ", ".join(f":{n}" for n in param_names)
        for name, val in zip(param_names, ids):
            params[name] = val
        ids_clause = f"    AND b.id_evento IN ({placeholders})\n"

    sql = f"""
SELECT /*+ MAX_EXECUTION_TIME(90000) */
    'Ativo'                                                                             AS banco,
    b.id_evento                                                                         AS id_evento,
    b.ds_evento                                                                         AS evento,

    CASE
        WHEN a.nr_preco = 0                                        THEN 'Cortesia'
        WHEN cupom.en_cupom_classificacao = 'Grupos'               THEN 'Grupos/B2B'
        WHEN h.ds_categoria LIKE '%Grup%'                          THEN 'Grupos/B2B'
        ELSE                                                            'Site'
    END                                                                                 AS canal,

    h.ds_categoria                                                                      AS kit,
    q.nm_modalidade                                                                     AS modalidade,

    COALESCE(IF(c.fl_local_inscricao = 1, g.pelotao, w.pelotao), 'Branco')              AS pelotao,
    NULL                                                                                AS produtos,
    IF(x.id_tamanho_camiseta = 2, 'BL', x.ds_tamanho)                                   AS tamanho_camiseta,

    COUNT(DISTINCT a.id_pedido_evento)                                                  AS inscritos,
    SUM(a.nr_preco)                                                                     AS receita_bruta,

    SUM(IF(
        a.nr_preco
        - IF(a.nr_desconto_individual IS NULL, 0, a.nr_desconto_individual)
        - IF(h.vl_kit IS NULL, 0, h.vl_kit) < 0,
        0,
        a.nr_preco
        - IF(a.nr_desconto_individual IS NULL, 0, a.nr_desconto_individual)
        - IF(h.vl_kit IS NULL, 0, h.vl_kit)
    ))                                                                                  AS receita_liquida,

    SUM(IF(
        a.nr_preco
        - IF(a.nr_desconto_individual IS NULL, 0, a.nr_desconto_individual)
        - IF(h.vl_kit IS NULL, 0, h.vl_kit) < 0,
        0,
        a.nr_preco
        - IF(a.nr_desconto_individual IS NULL, 0, a.nr_desconto_individual)
        - IF(h.vl_kit IS NULL, 0, h.vl_kit)
    )) / NULLIF(COUNT(DISTINCT a.id_pedido_evento), 0)                                  AS ticket_medio

FROM sa_evento AS b
INNER JOIN sa_pedido_evento AS a
    ON a.id_evento = b.id_evento
INNER JOIN sa_pedido AS c
    ON c.id_pedido = a.id_pedido
    AND c.id_pedido_status IN (2)
LEFT JOIN sa_modalidade_categoria AS h
    ON h.id_categoria = a.id_categoria
LEFT JOIN sa_evento_modalidade AS q
    -- Modalidade pela CATEGORIA (h.id_modalidade), como na query canônica do
    -- analista: ds_modalidade fica vazia em muitos eventos; nm_modalidade é a
    -- fonte confiável. id_modalidade é única — dispensa filtro por id_evento.
    ON q.id_modalidade = h.id_modalidade
LEFT JOIN sa_usuario AS g
    ON g.id_usuario = c.id_usuario
LEFT JOIN sa_usuario_balcao AS w
    ON w.id_usuario = a.id_usuario_balcao
LEFT JOIN sa_tamanho_camiseta AS x
    ON x.id_tamanho_camiseta = a.id_tamanho_camiseta
LEFT JOIN (
    SELECT
        e.id_cupom_desconto_item,
        f.en_cupom_classificacao
    FROM sa_cupom_desconto_item AS e
    INNER JOIN sa_cupom_desconto AS f
        ON f.id_cupom_desconto = e.id_cupom_desconto
) AS cupom
    ON cupom.id_cupom_desconto_item = a.id_cupom_individual

WHERE
    b.dt_evento BETWEEN MAKEDATE(YEAR(CURDATE()), 1)
                    AND MAKEDATE(YEAR(CURDATE()) + 1, 1) - INTERVAL 1 DAY
    AND (b.id_campanha_salesforce IS NULL
         OR b.id_campanha_salesforce NOT LIKE '701d0000000%')
{ids_clause}GROUP BY
    b.id_evento,
    b.ds_evento,
    CASE
        WHEN a.nr_preco = 0                                        THEN 'Cortesia'
        WHEN cupom.en_cupom_classificacao = 'Grupos'               THEN 'Grupos/B2B'
        WHEN h.ds_categoria LIKE '%Grup%'                          THEN 'Grupos/B2B'
        ELSE                                                            'Site'
    END,
    h.id_categoria,
    h.ds_categoria,
    q.nm_modalidade,
    COALESCE(IF(c.fl_local_inscricao = 1, g.pelotao, w.pelotao), 'Branco'),
    IF(x.id_tamanho_camiseta = 2, 'BL', x.ds_tamanho)

ORDER BY b.id_evento, canal, inscritos DESC
"""
    return sql, params


# ---------------------------------------------------------------------------
# CASE block para modalidade (distância/modalidade do produto filho).
# Idêntico no SELECT e GROUP BY — extraído como constante para evitar divergência.
# Antes chamado _DISTANCIA_CASE; renomeado em Jun/2026 quando a coluna passou
# a ser 'modalidade' em vez de 'distancia' em ambos Ativo e Magento.
# ---------------------------------------------------------------------------
_MODALIDADE_CASE = """
        WHEN soi_child.name LIKE '%Corrida e Caminhada Infantil%'        THEN 'Corrida e Caminhada Infantil'
        WHEN soi_child.name LIKE '%corridinha + skate + bravinhos + bike%' THEN 'corridinha + skate + bravinhos + bike'
        WHEN soi_child.name LIKE '%Obstáculo + Corrida%'                 THEN 'Obstáculo + Corrida'
        WHEN soi_child.name LIKE '%Corrida + Obstáculo%'                 THEN 'Corrida + Obstáculo'
        WHEN soi_child.name LIKE '%Corrida + Bravinhos%'                 THEN 'Corrida + Bravinhos'
        WHEN soi_child.name LIKE '%Corrida + Bike%'                      THEN 'Corrida + Bike'
        WHEN soi_child.name LIKE '%Corrida + Skate%'                     THEN 'Corrida + Skate'
        WHEN soi_child.name LIKE '%Corrida de Obstáculo%'                THEN 'Corrida de Obstáculo'
        WHEN soi_child.name LIKE '%Passeio Ciclístico%'                  THEN 'Passeio Ciclístico (10km)'
        WHEN soi_child.name LIKE '%Travessia 1500m%'                     THEN 'Travessia 1500m'
        WHEN soi_child.name LIKE '%5Km - Corrida e Caminhada%'           THEN '5Km - Corrida e Caminhada'
        WHEN soi_child.name LIKE '%5Km - Corrida%'                       THEN '5Km - Corrida'
        WHEN soi_child.name LIKE '%1Km - Caminhada%'                     THEN '1Km - Caminhada'
        WHEN soi_child.name LIKE '%Caminhada 3Km%'
          OR soi_child.name LIKE '%3Km - Caminhada%'                     THEN '3Km - Caminhada'
        WHEN soi_child.name LIKE '%Yoga%'                                THEN 'Yoga - Corrida e Meditação'
        WHEN soi_child.name LIKE '%Treinão%'                             THEN 'Treinão'
        WHEN soi_child.name LIKE '%corridinha%'                          THEN 'corridinha'
        WHEN soi_child.name LIKE '%Bravinhos%'                           THEN 'Bravinhos'
        WHEN soi_child.name LIKE '%Bike%'                                THEN 'Bike'
        WHEN soi_child.name LIKE '%Olímpico%'                            THEN 'Olímpico'
        WHEN soi_child.name LIKE '%Short%'                               THEN 'Short'
        WHEN TRIM(SUBSTRING(soi_child.name, LOCATE('-', soi_child.name)+1)) LIKE '3800m%' THEN '3800m'
        WHEN TRIM(SUBSTRING(soi_child.name, LOCATE('-', soi_child.name)+1)) LIKE '1500m%' THEN '1500m'
        WHEN TRIM(SUBSTRING(soi_child.name, LOCATE('-', soi_child.name)+1)) LIKE '50K%'   THEN '50K'
        WHEN TRIM(SUBSTRING(soi_child.name, LOCATE('-', soi_child.name)+1)) LIKE '50m%'   THEN '50m'
        WHEN TRIM(SUBSTRING(soi_child.name, LOCATE('-', soi_child.name)+1)) LIKE '42K%'   THEN '42Km'
        WHEN TRIM(SUBSTRING(soi_child.name, LOCATE('-', soi_child.name)+1)) LIKE '21K%'   THEN '21Km'
        WHEN TRIM(SUBSTRING(soi_child.name, LOCATE('-', soi_child.name)+1)) LIKE '18K%'   THEN '18Km'
        WHEN TRIM(SUBSTRING(soi_child.name, LOCATE('-', soi_child.name)+1)) LIKE '16K%'   THEN '16Km'
        WHEN TRIM(SUBSTRING(soi_child.name, LOCATE('-', soi_child.name)+1)) LIKE '15K%'   THEN '15Km'
        WHEN TRIM(SUBSTRING(soi_child.name, LOCATE('-', soi_child.name)+1)) LIKE '14K%'   THEN '14Km'
        WHEN TRIM(SUBSTRING(soi_child.name, LOCATE('-', soi_child.name)+1)) LIKE '13K%'   THEN '13Km'
        WHEN TRIM(SUBSTRING(soi_child.name, LOCATE('-', soi_child.name)+1)) LIKE '12K%'   THEN '12Km'
        WHEN TRIM(SUBSTRING(soi_child.name, LOCATE('-', soi_child.name)+1)) LIKE '11K%'   THEN '11Km'
        WHEN TRIM(SUBSTRING(soi_child.name, LOCATE('-', soi_child.name)+1)) LIKE '10K%'   THEN '10Km'
        WHEN TRIM(SUBSTRING(soi_child.name, LOCATE('-', soi_child.name)+1)) LIKE '7,5K%'  THEN '7,5K'
        WHEN TRIM(SUBSTRING(soi_child.name, LOCATE('-', soi_child.name)+1)) LIKE '2,5K%'  THEN '2,5K'
        WHEN TRIM(SUBSTRING(soi_child.name, LOCATE('-', soi_child.name)+1)) LIKE '8K%'    THEN '8Km'
        WHEN TRIM(SUBSTRING(soi_child.name, LOCATE('-', soi_child.name)+1)) LIKE '7K%'    THEN '7Km'
        WHEN TRIM(SUBSTRING(soi_child.name, LOCATE('-', soi_child.name)+1)) LIKE '5K%'    THEN '5Km'
        WHEN TRIM(SUBSTRING(soi_child.name, LOCATE('-', soi_child.name)+1)) LIKE '4K%'    THEN '4Km'
        WHEN TRIM(SUBSTRING(soi_child.name, LOCATE('-', soi_child.name)+1)) LIKE '3K%'    THEN '3Km'
        WHEN TRIM(SUBSTRING(soi_child.name, LOCATE('-', soi_child.name)+1)) LIKE '2K%'    THEN '2Km'
        WHEN TRIM(SUBSTRING(soi_child.name, LOCATE('-', soi_child.name)+1)) LIKE '1K%'    THEN '1Km'
        ELSE TRIM(SUBSTRING(soi_child.name, LOCATE('-', soi_child.name) + 1))"""

_CANAL_CASE = """
        WHEN so.base_grand_total = 0                                    THEN 'Cortesia'
        WHEN soi_child.price - soi_child.discount_amount = 0           THEN 'Cortesia'
        WHEN so.discount_description LIKE '%GRUPOS%'                    THEN 'Grupos/B2B'
        WHEN so.coupon_code LIKE 'GRUP%'                               THEN 'Grupos/B2B'
        ELSE                                                                 'Site'"""

_SOI_CHILD_NAME_FILTER = """(
            soi_child.name LIKE '%Distância%'
         OR soi_child.name LIKE '%Distancia%'
         OR soi_child.name LIKE '%Distâncias%'
         OR soi_child.name LIKE '%Modalidade%'
         OR soi_child.name REGEXP '-[0-9]+[Kk]m$'
         OR soi_child.name REGEXP '^[0-9]+[Kk]m?$'
         OR soi_child.name LIKE 'Kit Participação%'
         OR soi_child.name LIKE 'Olímpico%'
         OR soi_child.name LIKE 'Yoga%'
      )"""

# ---------------------------------------------------------------------------
# Receita líquida Magento com desconto de CARRINHO rateado por bundle do pedido.
# resíduo de carrinho = ABS(so.discount_amount) − descontos já lançados nos
# itens (agg.desc_itens), rateado pela qtd de bundles do pedido (agg.qtd_bundles).
# COALESCE(...,0) protege o SUM: pedido sem match em 'agg' viraria NULL e a
# linha inteira sairia do somatório (SUM ignora NULL).
# Requer o LEFT JOIN 'agg' (agregados por pedido) na query que usa este bloco.
# Usado em receita_liquida E no numerador do ticket_medio — constante única
# para nunca divergirem (mesmo padrão de _MODALIDADE_CASE/_CANAL_CASE).
# ---------------------------------------------------------------------------
_RECEITA_LIQUIDA_SUM = """SUM(CASE
        WHEN so.base_grand_total = 0 THEN 0
        ELSE soi_child.price
           - soi_child.discount_amount
           - COALESCE(
                 (ABS(so.discount_amount) - COALESCE(agg.desc_itens, 0))
                     / NULLIF(agg.qtd_bundles, 0)
               , 0)
    END)"""


def build_magento_detalhe(ids: Optional[List[int]] = None) -> Tuple[str, Dict]:
    """
    Retorna (sql, params) para query Magento.

    Quando ids é fornecido (modo drill-down, caso normal):
      - STRAIGHT_JOIN forçado com cpev1 (conjunto pequeno de produtos do evento)
        como tabela âncora, garantindo plano de execução estável no MySQL 5.7.
      - Os subqueries shirt/prod ancoram diretamente no id_evento via
        catalog_product_entity_varchar (evb.value IN ids), eliminando o
        inner_parent_filter com subquery de item_id que era mais custoso.
      - O join cped (catalog_product_entity_datetime) é removido: ele era
        necessário apenas para o filtro de ano quando ids=None (modo global).
        Com ids explícitos, o filtro de evento já garante o escopo correto.
      - Os joins redundantes por order_id nos subqueries shirt/prod são
        PRESERVADOS: destravam o índice SALES_ORDER_ITEM_ORDER_ID e evitam
        full scan da tabela de 5,4M linhas. NÃO remover.

    Quando ids é None (modo global sem filtro, uso legado):
      - Estrutura original preservada com join cped para filtro de ano corrente.
      - STRAIGHT_JOIN não aplicado (cpev1 sem filtro seria muito grande).
    """
    params: Dict = {}

    if not ids:
        # ids=None → modo global. ids=[] nunca chega aqui (_fetch_magento retorna
        # [] antes de chamar esta função). Usa estrutura original com cped.
        return _build_magento_detalhe_global(), params

    _validate_ids(ids)
    param_names = [f"mag_id_{i}" for i in range(len(ids))]
    placeholders = ", ".join(f":{n}" for n in param_names)
    for name, val in zip(param_names, ids):
        params[name] = val

    # Filtro de cpev1 (produtos pertencentes aos eventos solicitados)
    inner_ids_filter = f"      AND cpev.value IN ({placeholders})\n"
    # Filtro de cpev2 (entity_id = os próprios IDs de evento)
    cpev2_ids_filter = f"      AND entity_id IN ({placeholders})\n"
    # Filtro de shirt/prod (anchor por id_evento via catalog_product_entity_varchar)
    shirt_prod_ids_filter = f"      AND evb.value IN ({placeholders})\n"
    # Filtro dos pedidos-alvo do agregado 'agg' (rateio de desconto de carrinho)
    agg_ids_filter = f"          AND v.value IN ({placeholders})\n"

    sql = f"""
SELECT /*+ MAX_EXECUTION_TIME(90000) */ STRAIGHT_JOIN
    'Magento'                                                                           AS banco,
    cpev1.id_evento                                                                     AS id_evento,
    cpev2.value                                                                         AS evento,

    CASE{_CANAL_CASE}
    END                                                                                 AS canal,

    soi_parent.name                                                                     AS kit,

    CASE{_MODALIDADE_CASE}
    END                                                                                 AS modalidade,

    soi_parent.ext_order_item_id                                                        AS pelotao,
    prod.produtos                                                                       AS produtos,
    shirt.tamanho_camiseta                                                              AS tamanho_camiseta,

    COUNT(DISTINCT soi_parent.item_id)                                                  AS inscritos,

    SUM(CASE
        WHEN so.base_grand_total = 0 THEN 0
        ELSE soi_child.price
    END)                                                                                AS receita_bruta,

    {_RECEITA_LIQUIDA_SUM}                                                              AS receita_liquida,

    {_RECEITA_LIQUIDA_SUM} / NULLIF(COUNT(DISTINCT CASE
        WHEN so.base_grand_total = 0 THEN NULL
        ELSE soi_parent.item_id
    END), 0)                                                                            AS ticket_medio

FROM (
    -- Âncora: bundles dos eventos solicitados, restritos ao ano-competência corrente.
    -- O JOIN em cped (data do evento) filtra IDs cujo evento cai no ano atual,
    -- evitando que edições de anos anteriores com os mesmos IDs Magento sejam somadas.
    -- STRAIGHT_JOIN garante que o MySQL parte daqui e desce por índice.
    SELECT cpev.entity_id AS product_id,
           cpev.value     AS id_evento
    FROM catalog_product_entity_varchar cpev
    JOIN catalog_product_entity cpe
          ON cpe.entity_id = cpev.entity_id
         AND cpe.type_id   = 'bundle'
    JOIN catalog_product_entity_datetime cped
          ON cped.entity_id    = cpev.value
         AND cped.attribute_id = 195
         AND cped.value >= MAKEDATE(YEAR(CURDATE()), 1)
         AND cped.value <  MAKEDATE(YEAR(CURDATE()) + 1, 1)
    WHERE cpev.attribute_id = 321
      AND cpev.store_id     = 0
{inner_ids_filter}) AS cpev1

JOIN sales_order_item soi_parent
       ON soi_parent.product_id   = cpev1.product_id
      AND soi_parent.product_type = 'bundle'

JOIN sales_order_item soi_child
       ON soi_child.order_id       = soi_parent.order_id     -- destrava índice SALES_ORDER_ITEM_ORDER_ID (NÃO remover)
      AND soi_child.parent_item_id = soi_parent.item_id
      AND soi_child.product_type   = 'simple'
      AND {_SOI_CHILD_NAME_FILTER}

JOIN sales_order so
       ON so.entity_id = soi_parent.order_id
      AND so.status IN ('processing', 'complete', 'approved', 'aprovado_link', 'reembolso_parcial', 'closed', 'retirado')
      AND so.state NOT IN ('canceled')
      AND so.increment_id NOT REGEXP '-[0-9]'

JOIN (
    -- Nome canônico do evento, filtrado pelos IDs de evento solicitados
    SELECT entity_id, MIN(value) AS value
    FROM catalog_product_entity_varchar
    WHERE attribute_id = 73
      AND store_id     = 0
{cpev2_ids_filter}    GROUP BY entity_id
) AS cpev2 ON cpev2.entity_id = cpev1.id_evento

LEFT JOIN (
    -- Agregados por pedido para o rateio do desconto de CARRINHO:
    --   qtd_bundles → denominador do rateio
    --   desc_itens  → descontos já lançados nos itens (não-bundle)
    -- Escopo limitado aos pedidos que contêm bundles dos eventos solicitados
    -- (filtro DENTRO da derivada — evita full scan em sales_order_item).
    SELECT
        i.order_id,
        SUM(CASE WHEN i.product_type =  'bundle' THEN 1 ELSE 0 END)                 AS qtd_bundles,
        SUM(CASE WHEN i.product_type <> 'bundle' THEN i.discount_amount ELSE 0 END) AS desc_itens
    FROM sales_order_item i
    JOIN (
        -- pedidos-alvo: têm pelo menos um bundle dos eventos solicitados
        SELECT DISTINCT bo.order_id
        FROM catalog_product_entity_varchar v
        JOIN sales_order_item bo
               ON bo.product_id   = v.entity_id
              AND bo.product_type = 'bundle'
        WHERE v.attribute_id = 321
          AND v.store_id     = 0
{agg_ids_filter}    ) AS tgt ON tgt.order_id = i.order_id
    GROUP BY i.order_id
) AS agg ON agg.order_id = soi_parent.order_id

LEFT JOIN (
    -- Tamanho de camiseta: anchor por id_evento via evb, descendo por order_id (índice).
    -- JOIN a sales_order filtra apenas pedidos válidos — evita varrer cancelados/estornados.
    SELECT
        si.parent_item_id,
        MAX(eaov.value) AS tamanho_camiseta
    FROM catalog_product_entity_varchar evb
    JOIN sales_order_item sp
          ON sp.product_id   = evb.entity_id
         AND sp.product_type = 'bundle'
    JOIN sales_order so_s
          ON so_s.entity_id = sp.order_id
         AND so_s.status IN ('processing', 'complete', 'approved', 'aprovado_link', 'reembolso_parcial', 'closed', 'retirado')
         AND so_s.state NOT IN ('canceled')
         AND so_s.increment_id NOT REGEXP '-[0-9]'
    JOIN sales_order_item si
          ON si.order_id       = sp.order_id             -- destrava índice SALES_ORDER_ITEM_ORDER_ID (NÃO remover)
         AND si.parent_item_id = sp.item_id
    JOIN catalog_product_entity cpe_shirt
          ON cpe_shirt.entity_id        = si.product_id
         AND cpe_shirt.attribute_set_id = 27
    JOIN catalog_product_entity_int cpei_s
          ON cpei_s.entity_id    = si.product_id
         AND cpei_s.attribute_id = 207
    JOIN eav_attribute_option_value eaov
          ON eaov.option_id = cpei_s.value
    WHERE evb.attribute_id = 321
      AND evb.store_id     = 0
{shirt_prod_ids_filter}    GROUP BY si.parent_item_id
) AS shirt ON shirt.parent_item_id = soi_parent.item_id

LEFT JOIN (
    -- Produtos adicionais: anchor por id_evento via evb, descendo por order_id (índice).
    -- JOIN a sales_order filtra apenas pedidos válidos — evita varrer cancelados/estornados.
    SELECT
        si.parent_item_id,
        GROUP_CONCAT(DISTINCT si.name ORDER BY si.name SEPARATOR ', ') AS produtos
    FROM catalog_product_entity_varchar evb
    JOIN sales_order_item sp
          ON sp.product_id   = evb.entity_id
         AND sp.product_type = 'bundle'
    JOIN sales_order so_p
          ON so_p.entity_id = sp.order_id
         AND so_p.status IN ('processing', 'complete', 'approved', 'aprovado_link', 'reembolso_parcial', 'closed', 'retirado')
         AND so_p.state NOT IN ('canceled')
         AND so_p.increment_id NOT REGEXP '-[0-9]'
    JOIN sales_order_item si
          ON si.order_id       = sp.order_id             -- destrava índice SALES_ORDER_ITEM_ORDER_ID (NÃO remover)
         AND si.parent_item_id = sp.item_id
    JOIN catalog_product_entity cpe_p
          ON cpe_p.entity_id = si.product_id
    WHERE cpe_p.attribute_set_id NOT IN (30, 28, 27, 31)
      AND evb.attribute_id = 321
      AND evb.store_id     = 0
{shirt_prod_ids_filter}    GROUP BY si.parent_item_id
) AS prod ON prod.parent_item_id = soi_parent.item_id

GROUP BY
    cpev1.id_evento,
    cpev2.value,
    CASE{_CANAL_CASE}
    END,
    soi_parent.name,
    CASE{_MODALIDADE_CASE}
    END,
    soi_parent.ext_order_item_id,
    prod.produtos,
    shirt.tamanho_camiseta

ORDER BY cpev1.id_evento, canal, soi_parent.name
"""
    return sql, params


def _build_magento_detalhe_global() -> str:
    """
    Query Magento sem filtro de evento (modo global/legado, ids=None).
    Preserva a estrutura original com join cped para filtro de ano corrente.
    NÃO usa STRAIGHT_JOIN pois cpev1 sem filtro abrange todos os eventos.
    """
    return f"""
SELECT /*+ MAX_EXECUTION_TIME(90000) */
    'Magento'                                                                           AS banco,
    cpev1.value                                                                         AS id_evento,
    cpev2.value                                                                         AS evento,

    CASE{_CANAL_CASE}
    END                                                                                 AS canal,

    soi_parent.name                                                                     AS kit,

    CASE{_MODALIDADE_CASE}
    END                                                                                 AS modalidade,

    soi_parent.ext_order_item_id                                                        AS pelotao,
    prod.produtos                                                                       AS produtos,
    shirt.tamanho_camiseta                                                              AS tamanho_camiseta,

    COUNT(DISTINCT soi_parent.item_id)                                                  AS inscritos,

    SUM(CASE
        WHEN so.base_grand_total = 0 THEN 0
        ELSE soi_child.price
    END)                                                                                AS receita_bruta,

    {_RECEITA_LIQUIDA_SUM}                                                              AS receita_liquida,

    {_RECEITA_LIQUIDA_SUM} / NULLIF(COUNT(DISTINCT CASE
        WHEN so.base_grand_total = 0 THEN NULL
        ELSE soi_parent.item_id
    END), 0)                                                                            AS ticket_medio

FROM sales_order so

JOIN sales_order_item soi_parent
       ON soi_parent.order_id     = so.entity_id
      AND soi_parent.product_type = 'bundle'

JOIN sales_order_item soi_child
       ON soi_child.parent_item_id = soi_parent.item_id
      AND soi_child.product_type   = 'simple'
      AND {_SOI_CHILD_NAME_FILTER}

JOIN (
    SELECT cpev.entity_id, cpev.value
    FROM catalog_product_entity_varchar cpev
    JOIN catalog_product_entity cpe
          ON cpe.entity_id = cpev.entity_id
         AND cpe.type_id   = 'bundle'
    WHERE cpev.attribute_id = 321
      AND cpev.store_id     = 0
) AS cpev1 ON cpev1.entity_id = soi_parent.product_id

JOIN (
    SELECT entity_id, MIN(value) AS value
    FROM catalog_product_entity_varchar
    WHERE attribute_id = 73
      AND store_id     = 0
      AND entity_id IN (SELECT value FROM catalog_product_entity_varchar
                        WHERE attribute_id = 321 AND store_id = 0)
    GROUP BY entity_id
) AS cpev2 ON cpev2.entity_id = cpev1.value

JOIN (
    SELECT entity_id, MIN(value) AS value
    FROM catalog_product_entity_datetime
    WHERE attribute_id = 195
      AND entity_id IN (SELECT value FROM catalog_product_entity_varchar
                        WHERE attribute_id = 321 AND store_id = 0)
    GROUP BY entity_id
) AS cped ON cped.entity_id = cpev1.value

LEFT JOIN (
    -- Agregados por pedido para o rateio do desconto de CARRINHO (modo global):
    -- mesmo padrão do modo parametrizado, com pedidos-alvo restritos aos
    -- bundles de eventos do ano corrente — evita full scan em sales_order_item.
    SELECT
        i.order_id,
        SUM(CASE WHEN i.product_type =  'bundle' THEN 1 ELSE 0 END)                 AS qtd_bundles,
        SUM(CASE WHEN i.product_type <> 'bundle' THEN i.discount_amount ELSE 0 END) AS desc_itens
    FROM sales_order_item i
    JOIN (
        -- pedidos-alvo: contêm bundle de evento cujo dt_evento cai no ano corrente
        SELECT DISTINCT bo.order_id
        FROM catalog_product_entity_varchar v
        JOIN catalog_product_entity_datetime d
              ON d.entity_id    = v.value
             AND d.attribute_id = 195
             AND d.value >= MAKEDATE(YEAR(CURDATE()), 1)
             AND d.value <  MAKEDATE(YEAR(CURDATE()) + 1, 1)
        JOIN sales_order_item bo
               ON bo.product_id   = v.entity_id
              AND bo.product_type = 'bundle'
        WHERE v.attribute_id = 321
          AND v.store_id     = 0
    ) AS tgt ON tgt.order_id = i.order_id
    GROUP BY i.order_id
) AS agg ON agg.order_id = soi_parent.order_id

LEFT JOIN (
    SELECT
        si.parent_item_id,
        MAX(eaov.value) AS tamanho_camiseta
    FROM sales_order_item si
    JOIN catalog_product_entity cpe_shirt
          ON cpe_shirt.entity_id        = si.product_id
         AND cpe_shirt.attribute_set_id = 27
    JOIN catalog_product_entity_int cpei_s
          ON cpei_s.entity_id    = si.product_id
         AND cpei_s.attribute_id = 207
    JOIN eav_attribute_option_value eaov
          ON eaov.option_id = cpei_s.value
    GROUP BY si.parent_item_id
) AS shirt ON shirt.parent_item_id = soi_parent.item_id

LEFT JOIN (
    SELECT
        si.parent_item_id,
        GROUP_CONCAT(DISTINCT si.name ORDER BY si.name SEPARATOR ', ') AS produtos
    FROM sales_order_item si
    JOIN catalog_product_entity cpe_p
          ON cpe_p.entity_id = si.product_id
    WHERE cpe_p.attribute_set_id NOT IN (30, 28, 27, 31)
    GROUP BY si.parent_item_id
) AS prod ON prod.parent_item_id = soi_parent.item_id

WHERE so.status IN ('processing', 'complete', 'approved', 'aprovado_link', 'reembolso_parcial', 'closed', 'retirado')
  AND so.state NOT IN ('canceled')
  AND so.increment_id   NOT REGEXP '-[0-9]'
  AND cped.value        >= MAKEDATE(YEAR(CURDATE()), 1)
  AND cped.value        <  MAKEDATE(YEAR(CURDATE()) + 1, 1)

GROUP BY
    cpev1.value,
    cpev2.value,
    CASE{_CANAL_CASE}
    END,
    soi_parent.name,
    CASE{_MODALIDADE_CASE}
    END,
    soi_parent.ext_order_item_id,
    prod.produtos,
    shirt.tamanho_camiseta

ORDER BY cpev1.value, canal, soi_parent.name
"""
