---
name: Kit special_price source
description: De onde vem o special_price no Mapeamento de Kits e por que NÃO usar a cadeia baseada em lotes.
---

# special_price do Mapeamento de Kits

`special_price` (preço promocional/entrada do kit, usado pelo "ticket atual" no
Dash ISC) vem de `catalog_product_index_price.min_price` do **bundle pai**
(`pi_pai`, website_id=1, customer_group_id=0). Fallback (kit inativo, que não
entra no index): soma do `final_price` dos componentes simples via
`pi_filho` — MAX(componente Distância/Modalidade) + MAX(addon não-blacklisted),
ambos com `COALESCE(...,0)` e o todo embrulhado em `NULLIF(...,0)`.

**Why:** `min_price` já reflete as catalog price rules ativas (promoções
vigentes) do Magento — é a fonte canônica do preço de vitrine. Uma versão
anterior trocou isso por uma cadeia de fallback baseada em
`catalog_product_entity_event_lot_price` (lotes), que devolvia valores errados
(somava lote do evento + addon, etc.). Não reintroduzir a lógica de lotes para
special_price.

**How to apply:** Editar só o bloco `special_price` em `MAGENTO_KITS_QUERY`
(`kit_config.py`). A 1ª parcela do fallback PRECISA de `COALESCE(...,0)` (igual
ao `price`): bundles cujo componente "distância" foge da nomenclatura padrão
(ex.: "BPC26SP1MB-5Km") não casam na branch e `NULL + addon` zeraria tudo.
`pi_pai.min_price` é coluna não-agregada → tem que entrar no `GROUP BY`.
Manter intactas as colunas `price`, `current_price` e `bundle_entity_id` (o
resto do sistema depende: bundle_entity_id é PK do snapshot; current_price
alimenta o ticket_atual ISC).
