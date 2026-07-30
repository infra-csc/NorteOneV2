---
name: On-demand per-kit breakdown for chart drill-downs
description: Pattern for adding a new dimension (e.g. kit type) to an existing daily-sales chart without touching the heavily-cached main event endpoint or the nightly snapshot schema.
---

## Pattern

When a chart already fetches its data from a large, cached, perf-sensitive main event
endpoint (e.g. the Detalhe de Evento payload) and needs a new breakdown dimension that
the nightly snapshot doesn't carry (snapshots aggregate away per-kit/per-category detail),
prefer a **new, separate on-demand endpoint** the chart calls lazily on mount, rather than
adding the dimension to the main payload or migrating the snapshot schema:

- Require an **explicit, short, bounded date range** (this codebase caps at 31 days) from
  the caller instead of "all time" — a live query over a short explicit range is cheap even
  for old/frozen events, so you can skip snapshot partitioning (active vs. frozen) entirely
  for this one endpoint.
- Give the new endpoint its own lightweight short-TTL in-memory cache (not the shared
  `SmartCache`/singleflight machinery) when it has a single call site — simpler and
  sufficient.
- Any `ano` query param on a new marketing per-event sub-endpoint should be **optional**
  and resolved server-side via `_resolve_evento_ano_efetivo(db, evento_id, None)` when
  omitted — never make the frontend guess/default to the current calendar year, since an
  event's effective "ano" is a business concept, not the calendar year.

**Why:** keeps the main endpoint's cache/perf characteristics untouched, avoids a snapshot
migration, and matches how this app already resolves "which year does this event mean"
everywhere else.

**How to apply:** for a new "click/hover for breakdown by X" feature on an existing chart,
look for the sibling raw-SQL fetch functions the main endpoint already uses (e.g.
`_fetch_daily_sales_ativo_by_ids`, `_fetch_daily_sales_magento_by_ids_impl` in
`backend/app/api/routes/marketing.py`) and write new sibling functions that add the extra
GROUP BY dimension — see `magento-query-timeout-mirroring.md` for the pitfall to check
when doing this.
