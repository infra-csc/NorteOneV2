-- =====================================================================
-- MAGENTO | Detalhe de inscricoes por evento  (CONTRATO CONSOLIDADO)
-- ---------------------------------------------------------------------
-- Saida ALINHADA ao mesmo contrato de colunas da query do Ativo, para
-- merge na camada de aplicacao (Node). Os dois bancos sao distintos
-- (replica Magento x 0_transfer Ativo) => a consolidacao NAO pode ser
-- feita em SQL; e feita no back (rodar as duas, concatenar, reagrupar).
--
-- CONTRATO (ordem fixa, identica nas duas queries):
--   banco, id_evento, evento, canal, kit, distancia, modalidade,
--   pelotao, produtos, tamanho_camiseta,
--   inscritos, receita_bruta, receita_liquida, ticket_medio
--
-- distancia = rotulo normalizado A PARTIR DO NOME (distancia vendida).
-- modalidade = NULL (Magento nao tem dimensao separada; vem embutida na
--              distancia). Ver nota no README/prompt.
--
-- MANUTENCAO: o CASE de 'canal' precisa ser IDENTICO no SELECT e no GROUP BY.
-- =====================================================================
SELECT
    'Magento'                                                                       AS banco,
    cpev1.value                                                                     AS id_evento,
    cpev2.value                                                                     AS evento,

    -- canal (IDENTICO ao GROUP BY)
    CASE
        WHEN so.base_grand_total = 0                                    THEN 'Cortesia'
        WHEN soi_child.price - soi_child.discount_amount = 0           THEN 'Cortesia'
        WHEN so.discount_description LIKE '%GRUPOS%'                    THEN 'Grupos/B2B'
        WHEN so.coupon_code LIKE 'GRUP%'                               THEN 'Grupos/B2B'
        ELSE                                                                 'Site'
    END                                                                             AS canal,

    soi_parent.name                                                                 AS kit,

    -- distancia = modalidade_ajustada normalizada a partir do nome do filho
    CASE
        -- ---- MODALIDADES TEXTUAIS (mais especificas primeiro) ----
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

        -- ---- DISTANCIAS NUMERICAS: LIKE ancorado na cauda (apos 1o hifen) ----
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

        -- ---- FALLBACK: cauda do nome (apos 1o hifen) ----
        ELSE TRIM(SUBSTRING(soi_child.name, LOCATE('-', soi_child.name) + 1))
    END                                                                             AS distancia,

    NULL                                                                            AS modalidade,  -- Magento nao tem modalidade separada (embutida na distancia)

    soi_parent.ext_order_item_id                                                    AS pelotao,
    prod.produtos                                                                   AS produtos,
    shirt.tamanho_camiseta                                                          AS tamanho_camiseta,

    COUNT(DISTINCT soi_parent.item_id)                                              AS inscritos,

    SUM(CASE
        WHEN so.base_grand_total = 0                                    THEN 0
        ELSE soi_child.price
    END)                                                                            AS receita_bruta,

    SUM(CASE
        WHEN so.base_grand_total = 0                                    THEN 0
        ELSE soi_child.price - soi_child.discount_amount
    END)                                                                            AS receita_liquida,

    SUM(CASE
        WHEN so.base_grand_total = 0                                    THEN 0
        ELSE soi_child.price - soi_child.discount_amount
    END) / NULLIF(COUNT(DISTINCT CASE
        WHEN so.base_grand_total = 0                                    THEN NULL
        ELSE soi_parent.item_id
    END), 0)                                                                        AS ticket_medio

FROM sales_order so

JOIN sales_order_item soi_parent
       ON soi_parent.order_id     = so.entity_id
      AND soi_parent.product_type = 'bundle'

JOIN sales_order_item soi_child
       ON soi_child.parent_item_id = soi_parent.item_id
      AND soi_child.product_type   = 'simple'
      AND (
            soi_child.name LIKE '%Distância%'
         OR soi_child.name LIKE '%Distancia%'
         OR soi_child.name LIKE '%Distâncias%'
         OR soi_child.name LIKE '%Modalidade%'
         OR soi_child.name REGEXP '-[0-9]+[Kk]m$'
         OR soi_child.name REGEXP '^[0-9]+[Kk]m?$'
         OR soi_child.name LIKE 'Kit Participação%'
         OR soi_child.name LIKE 'Olímpico%'
         OR soi_child.name LIKE 'Yoga%'
      )

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
    GROUP BY entity_id
) AS cpev2 ON cpev2.entity_id = cpev1.value

JOIN (
    SELECT entity_id, MIN(value) AS value
    FROM catalog_product_entity_datetime
    WHERE attribute_id = 195
    GROUP BY entity_id
) AS cped ON cped.entity_id = cpev1.value

-- Tamanho Camiseta (atributo 207 nos filhos do attribute_set 27)
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

-- Produtos (nomes dos filhos fora dos attribute_sets 30/28/27/31)
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
 -- AND cpev1.value       = 48152  -- Filtro evento (toggle)

GROUP BY
    cpev1.value,
    cpev2.value,
    -- canal: IDENTICO ao SELECT
    CASE
        WHEN so.base_grand_total = 0                                    THEN 'Cortesia'
        WHEN soi_child.price - soi_child.discount_amount = 0           THEN 'Cortesia'
        WHEN so.discount_description LIKE '%GRUPOS%'                    THEN 'Grupos/B2B'
        WHEN so.coupon_code LIKE 'GRUP%'                               THEN 'Grupos/B2B'
        ELSE                                                                 'Site'
    END,
    soi_parent.name,
    distancia,                       -- alias do CASE de distancia (idem SELECT)
    soi_parent.ext_order_item_id,
    prod.produtos,
    shirt.tamanho_camiseta

ORDER BY
    cpev1.value,
    canal,
    soi_parent.name;
