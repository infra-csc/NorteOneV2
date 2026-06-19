# Prompt para o agente do Replit — "Detalhamento de Eventos" (fonte Magento, drill-down)

## Contexto
Plataforma de analytics que consolida inscrições de eventos esportivos de dois bancos:
**Magento** (replica read-only, MySQL 5.7) e **Ativo** (`0_transfer`). Este prompt cobre
**apenas a fonte Magento** da tela "Detalhamento de Eventos".

A tela funciona em **drill-down: um evento por vez**. O usuário seleciona um evento e a
tela carrega o detalhamento daquele evento específico.

## Objetivo desta tarefa
Implementar/ajustar o endpoint de back-end que retorna o detalhamento de **um** evento
Magento, executando a query SQL do final deste documento, parametrizada pelo id do evento.

## Como integrar (back-end Node)
- O endpoint recebe `idEvento` (o id do evento no Magento, vindo da seleção na tela).
- Executar a query com mysql2 usando **named placeholders**:
  `pool.query(SQL, { evento: idEvento })`, com o pool criado com `namedPlaceholders: true`.
  O placeholder `:evento` aparece **4 vezes** na query e o mysql2 reaproveita o mesmo valor.
- Definir um **timeout explícito** na execução (~15–20s) para retornar erro tratável em
  vez de deixar a requisição travar até estourar o limite do Replit.
- Mapear o retorno para o contrato de consolidação (abaixo) e devolver via API para o
  front (React + TypeScript + TanStack Query).

## Regra de escopo (CRÍTICA)
- **Nunca** buscar todos os eventos de uma vez. Puxar o ano inteiro (376 eventos) custa
  de 51s a 165s e estoura o timeout do Replit. A consulta é **sempre por evento**.
- Custo medido por evento: ~2s. A tela deve mostrar um **loading state** (spinner)
  enquanto carrega.
- (Opcional) cachear o resultado por evento e invalidar quando as vendas daquele evento
  mudarem — só vale se o mesmo evento for reaberto com frequência.

## Restrições técnicas que NÃO podem ser alteradas (são propositais)
1. **Replica Magento é read-only**: sem DDL. Não criar índice, view nem tabela temporária.
2. **Join redundante por `order_id`** (`soi_child.order_id = soi_parent.order_id` e, dentro
   das derivadas, `si.order_id = sp.order_id`): é proposital. Não existe índice em
   `sales_order_item.parent_item_id`, então a igualdade por `order_id` destrava o índice
   `SALES_ORDER_ITEM_ORDER_ID` e evita full scan da tabela (5,4M linhas). **Não remover.**
3. **`STRAIGHT_JOIN`**: trava a ordem de join partindo do evento (conjunto pequeno) e desce
   por índice. **Não remover.**
4. **MySQL 5.7 não tem CTE**: a query usa derived tables de propósito. **Não converter para
   `WITH`.**
5. O `CASE` da coluna `canal` precisa permanecer **idêntico** no `SELECT` e no `GROUP BY`
   (qualquer divergência entre os dois quebra o agrupamento).
6. `ticket_medio` é sempre recalculado (`receita_liquida / inscritos`), **nunca somado** —
   importante se o front reagrupar linhas.

## Contrato de consolidação (14 colunas — alinhar com a fonte Ativo)
`banco, id_evento, evento, canal, kit, distancia, modalidade, pelotao, produtos,
tamanho_camiseta, inscritos, receita_bruta, receita_liquida, ticket_medio`
- No Magento, `modalidade` vem da coluna `modalidade_ajustada` (derivada do nome do produto).
- A consolidação Magento + Ativo acontece **na camada de aplicação** (queries paralelas),
  nunca via JOIN entre os dois bancos.

## O que NÃO fazer
- Não substituir por uma query que puxe todos os eventos de uma vez.
- Não remover `order_id` dos joins, o `STRAIGHT_JOIN`, nem mexer no `CASE` de canal.
- Não tentar criar índice ou tabela temporária na base Magento.

---

## Query SQL (parametrizada por `:evento`)

```sql
SELECT STRAIGHT_JOIN
    CONVERT_TZ(NOW(), '+00:00', '-03:00')                                           AS 'Data extração',
    'Magento'                                                                       AS banco,
    cpev1.id_evento                                                                 AS id_evento,
    cpev2.value                                                                     AS evento,
    soi_parent.name                                                                 AS kit,
    eaov_tipo.value                                                                 AS tipo_categoria,
    soi_child.name                                                                  AS distancia,

    CASE
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
        ELSE TRIM(SUBSTRING(soi_child.name, LOCATE('-', soi_child.name) + 1))
    END                                                                             AS modalidade_ajustada,

    CASE
        WHEN so.base_grand_total = 0                                    THEN 'Cortesia'
        WHEN soi_child.price - soi_child.discount_amount = 0           THEN 'Cortesia'
        WHEN so.discount_description LIKE '%GRUPOS%'                   THEN 'Grupos/B2B'
        WHEN so.coupon_code LIKE 'GRUP%'                               THEN 'Grupos/B2B'
        ELSE                                                                 'Site'
    END                                                                             AS canal,

    soi_parent.ext_order_item_id                                                    AS pelotao,
    shirt.tamanho_camiseta                                                          AS tamanho_camiseta,
    prod.produtos                                                                   AS produtos,

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

FROM (
    SELECT cpev.entity_id AS product_id,
           cpev.value     AS id_evento
    FROM catalog_product_entity_varchar cpev
    JOIN catalog_product_entity cpe
          ON cpe.entity_id = cpev.entity_id
         AND cpe.type_id   = 'bundle'
    WHERE cpev.attribute_id = 321
      AND cpev.store_id     = 0
      AND cpev.value        = :evento
) AS cpev1

JOIN sales_order_item soi_parent
       ON soi_parent.product_id   = cpev1.product_id
      AND soi_parent.product_type = 'bundle'

JOIN sales_order_item soi_child
       ON soi_child.order_id       = soi_parent.order_id     -- destrava o indice ORDER_ID (NAO remover)
      AND soi_child.parent_item_id = soi_parent.item_id
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

JOIN sales_order so
       ON so.entity_id = soi_parent.order_id
      AND so.status IN ('processing', 'complete', 'approved', 'aprovado_link', 'reembolso_parcial', 'closed', 'retirado')
      AND so.state NOT IN ('canceled')
      AND so.increment_id NOT REGEXP '-[0-9]'

JOIN (
    SELECT entity_id, MIN(value) AS value
    FROM catalog_product_entity_varchar
    WHERE attribute_id = 73
      AND store_id     = 0
      AND entity_id    = :evento
    GROUP BY entity_id
) AS cpev2 ON cpev2.entity_id = cpev1.id_evento

LEFT JOIN catalog_product_entity_int cpei_tipo
       ON cpei_tipo.entity_id    = soi_parent.product_id
      AND cpei_tipo.attribute_id = (
            SELECT attribute_id FROM eav_attribute
            WHERE attribute_code = 'tipo_categoria'
              AND entity_type_id = (
                    SELECT entity_type_id FROM eav_entity_type
                    WHERE entity_type_code = 'catalog_product'
              )
      )
LEFT JOIN eav_attribute_option_value eaov_tipo
       ON eaov_tipo.option_id = cpei_tipo.value

LEFT JOIN (
    SELECT
        si.parent_item_id,
        MAX(eaov.value) AS tamanho_camiseta
    FROM catalog_product_entity_varchar evb
    JOIN sales_order_item sp
          ON sp.product_id   = evb.entity_id
         AND sp.product_type = 'bundle'
    JOIN sales_order_item si
          ON si.order_id       = sp.order_id             -- destrava o indice ORDER_ID (NAO remover)
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
      AND evb.value        = :evento
    GROUP BY si.parent_item_id
) AS shirt ON shirt.parent_item_id = soi_parent.item_id

LEFT JOIN (
    SELECT
        si.parent_item_id,
        GROUP_CONCAT(DISTINCT si.name ORDER BY si.name SEPARATOR ', ') AS produtos
    FROM catalog_product_entity_varchar evb
    JOIN sales_order_item sp
          ON sp.product_id   = evb.entity_id
         AND sp.product_type = 'bundle'
    JOIN sales_order_item si
          ON si.order_id       = sp.order_id             -- destrava o indice ORDER_ID (NAO remover)
         AND si.parent_item_id = sp.item_id
    JOIN catalog_product_entity cpe_p
          ON cpe_p.entity_id = si.product_id
         AND cpe_p.attribute_set_id NOT IN (30, 28, 27, 31)
    WHERE evb.attribute_id = 321
      AND evb.store_id     = 0
      AND evb.value        = :evento
    GROUP BY si.parent_item_id
) AS prod ON prod.parent_item_id = soi_parent.item_id

GROUP BY
    cpev1.id_evento,
    cpev2.value,
    soi_parent.name,
    eaov_tipo.value,
    soi_child.name,
    modalidade_ajustada,
    CASE
        WHEN so.base_grand_total = 0                                    THEN 'Cortesia'
        WHEN soi_child.price - soi_child.discount_amount = 0           THEN 'Cortesia'
        WHEN so.discount_description LIKE '%GRUPOS%'                   THEN 'Grupos/B2B'
        WHEN so.coupon_code LIKE 'GRUP%'                               THEN 'Grupos/B2B'
        ELSE                                                                 'Site'
    END,
    soi_parent.ext_order_item_id,
    shirt.tamanho_camiseta,
    prod.produtos

ORDER BY
    cpev1.id_evento,
    canal,
    soi_parent.name;
```
