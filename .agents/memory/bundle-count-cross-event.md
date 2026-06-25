---
name: Bundle count cross-event contamination
description: Count query sem filtro id_evento soma pedidos de edições anteriores na janela de 15 meses, inflando inscrições no ISC Dashboard.
---

## A regra

Toda query de contagem de `sales_order_item` por `bundle_entity_id` deve filtrar pelo `id_evento` específico do bundle, usando um JOIN com `catalog_product_entity_varchar` (attribute_id=321, store_id=0).

**Why:** O mesmo `bundle_entity_id` é reutilizado em edições anuais do mesmo evento (ex.: "Troféu Brasil 1ª Etapa" + "2ª Etapa"). A janela padrão de 15 meses na count_query abrange ambas as edições, somando pedidos de eventos diferentes. Resultou em 580 exibido vs 562 real no ISC Dashboard.

## Como aplicar

1. **Build do mapa `bid → id_evento`:** via `KitConfig.bundle_entity_id` + `KitConfig.id_evento` (já disponível em `bundle_rows` no batch ou via query adicional no endpoint ao vivo).

2. **Query de contagem com escopo (MySQL 8+):**
```sql
INNER JOIN (
    SELECT t.bid AS product_id, t.evento_id
    FROM (VALUES (:cnt_bid_0, :cnt_evid_0), ...) AS t (bid, evento_id)
) AS ev_scope ON ev_scope.product_id = soi_parent.product_id
INNER JOIN catalog_product_entity_varchar cpev_scope
       ON cpev_scope.entity_id    = soi_parent.product_id
      AND cpev_scope.attribute_id = 321
      AND cpev_scope.store_id     = 0
      AND cpev_scope.value        = ev_scope.evento_id
```
Remove o `AND soi_parent.product_id IN :bundle_ids` (substituído pelo JOIN).

3. **Fallback:** bundles sem `id_evento` no mapa (legado/sem KitConfig) usam a query antiga com `IN :bundle_ids`.

## Upsert no snapshot (`_persist_batch`)

- Bundles **COM** mapa `bid_to_evento_id`: usar `EXCLUDED.valor` (substituição direta). GREATEST() aqui preservaria valores inflados gravados antes do fix.
- Bundles **SEM** mapa: manter `GREATEST(EXCLUDED.valor, current.valor)` como piso contra respostas parciais do Magento.

## Arquivos afetados

- `backend/app/api/routes/marketing.py` — `get_margem_por_kit`: bloco de count query ao vivo
- `backend/app/services/snapshot_service.py` — `sincronizar_margem_bundle_rev_batch`: `_build_cnt_query_for_batch()` + `_persist_batch()`

## Efeito pós-deploy

O próximo "Reconsolidar" (admin) reescreve o `margem_bundle_rev_snapshot` com os valores corretos por evento (sem GREATEST), corrigindo permanentemente os valores inflados gravados antes do fix.
