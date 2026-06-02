---
name: medias-vendas window anchors to yesterday
description: Why ISC sales averages/windows must end at the last closed day (ontem), not today
---

Rule: the marketing sales-averages endpoint (`/eventos/{id}/medias-vendas`, `get_sales_averages`) and any rolling window (7/14/30d, vendas_diarias, tendencia) must anchor `ref_date` to YESTERDAY for active events, never to `today`.

**Why:** the current day is always partial — the day isn't over and the snapshot only holds sales up to the last sync. Including it in the numerator while dividing by the full window count drags averages down, with bigger error on shorter windows (7d > 14d > 30d). This produced a real divergence vs the user's "até ontem" control (e.g. 66.3 vs 73.1 on 7d). The cumulative card is labeled "até ontem" and the frontend's own fallback averages already filter `< today` (completeDailySales), so the backend was the inconsistent piece.

**How to apply:** keep the frozen-event branch (`(today - latest_sale).days > 30 → ref_date = latest_sale`) untouched; only the fresh/no-data branches use `yesterday = today - 1`. After deploy, `medias_cache` has a long TTL (~22h) so old biased values persist until SWR revalidation — force-refresh if immediate correctness is needed. Note: VendasDiariaSnapshot can sit slightly above a live "até ontem" count due to snapshot floor/GREATEST behavior (small, by design), separate from this windowing fix.
