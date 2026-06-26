---
name: ISC "Site" channel definition + Magento net-revenue proration
description: How the ISC Dashboard sales queries define the "Site" channel (exclude Cortesia + Grupos/B2B) and the V8 prorated net-revenue formula, plus the perf constraint on its agg subquery.
---

# ISC "Site"-only channel

The ISC Dashboard sales counts/revenue must include ONLY the "Site" channel —
exclude **Cortesia** (free) and **Grupos / B2B**. This filter is applied to ALL
ISC feeder query functions in `backend/app/api/routes/marketing.py` (the 4 Ativo
+ 4 Magento daily/grouped/today helpers) so live data and snapshot rebuilds stay
consistent.

**Why:** ISC measures real demand/health; courtesy and bulk B2B/group sales
distort the curve, the acceleration index, and the rolling averages. The user
wants only organic Site sales counted everywhere.

**How to apply — Ativo (MySQL):**
- `a.nr_preco > 0` (excludes cortesia)
- `cupom.en_cupom_classificacao <> 'Grupos'` (NULL-tolerant OR)
- `h.ds_categoria NOT LIKE '%Grup%'` (NULL-tolerant OR)

**How to apply — Magento (MySQL via SSH):**
- `so.base_grand_total > 0` (excludes cortesia/free orders)
- `so.discount_description NOT LIKE '%GRUPOS%'` (or NULL)
- `so.coupon_code NOT LIKE 'GRUP%'` (or NULL)
- `soi_child.price > 0` AND `(soi_child.price - soi_child.discount_amount) > 0`

Note: `cortesia_magento_ids` params remain in signatures (singleflight key /
caller compat) but no longer carve out free events in SQL — the daily impl
already ignored them in SQL before, and Site-only is the explicit intent. A
genuinely-free event with no paid Site sales will correctly read 0.

# Magento V8 net-revenue (cart-discount proration)

The two receita-computing Magento helpers (`_fetch_today_sales_magento_grouped`,
`_fetch_daily_sales_magento_by_ids_impl`) use the V8 formula:
`SUM(price - discount_amount - COALESCE((ABS(so.discount_amount) - COALESCE(agg.desc_itens,0)) / NULLIF(agg.qtd_bundles,0), 0))`.
It subtracts the item-level discount AND the residual order-level (cart) discount
not already allocated to items, prorated evenly across the order's bundles. A
`LEFT JOIN agg` subquery computes per-order `qtd_bundles` and non-bundle
`desc_itens`. `NULLIF`/`COALESCE` guard div-by-zero and NULL.

**CRITICAL perf constraint:** the `agg` subquery's order set (`tgt`) MUST be
time-windowed to the SAME window as the outer query (today for `today_grouped`,
`>= :data_floor` / `< tomorrow` for the daily impl) by joining `sales_order`
inside `tgt`. Without it, agg aggregates the entire order history for the event
ids and `today_grouped` (12s MAX_EXECUTION_TIME) times out → empty fallback →
live ISC totals silently break. Item aggregation inside agg stays full-order
(proration must see the whole cart); only the *set of orders* is windowed.

**Snapshot rebuild after deploy:** no new script. Trigger admin endpoint
`POST /snapshots/consolidar-full` (checkpoint/retry) in PROD — it calls
`consolidar_vendas_grupo` → the modified daily helpers, rebuilding all snapshots
Site-only with the new revenue formula.
