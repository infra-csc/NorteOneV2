---
name: Rolling full-rebuild for snapshot drift
description: Why the nightly snapshot needs a rolling full-rebuild and the ano-scoped DELETE rule that makes it safe for recurring events
---

# Rolling full-rebuild of vendas_diaria_snapshot

## The drift problem
The nightly `snapshot_diario_batch` only runs INCREMENTAL consolidation over a short
rolling lookback window (`DAILY_SNAPSHOT_LOOKBACK_DAYS`, default 3). Cancellations/refunds
of OLD orders (outside that window) are never re-queried, so the snapshot total drifts
ABOVE the real count over time. The ISC "Reconsolidar" button does NOT fix this — it calls
`force_refresh` which is still incremental+lookback. Only a full rebuild
(`consolidar_vendas_grupo(incremental=False)` — DELETE + re-query whole ~24mo window)
corrects old-day drift.

## The rolling fix
`rebuild_rolling_grupos_batch` full-rebuilds a slice of N active groups per night
(`ROLLING_REBUILD_GROUPS_PER_NIGHT`, default 10, cap 60, 0=off), picking the groups with
the oldest `MIN(updated_at)` among their CONSOLIDADO rows. Rotation covers the whole active
set in ~total/N nights with no extra schema: a full rebuild restamps `updated_at=now` on
every row of the group, so ordering by `MIN(updated_at)` is a natural queue. Incremental only
touches recent days, so `MIN(updated_at)` reflects the last FULL rebuild.

## CRITICAL: ano-scoped DELETE for recurring events
**The full-mode DELETE in `consolidar_vendas_grupo` filters only by `evento_grupo`+`fonte`
(+ optional `data_fim`), NOT by `ano`.** For a recurring group (e.g. Circuito SP has a 2025
AND a 2026 edition under the same `evento_grupo`), a full rebuild for the current year would
DELETE the prior edition's rows and only rebuild the current edition (the rebuild fetches with
mappings filtered to `SkuMapping.ano == current`), permanently losing the prior edition's
snapshot. Rare/intentional for a manual reconsolidar, but SYSTEMATIC once automated nightly.

**Rule:** the rolling rebuild MUST pass `delete_scope_ano=True` so the DELETE adds
`VendasDiariaSnapshot.ano == ano`. This still fixes current-edition drift (all current rows are
tagged with the current ano; days that dropped to zero get deleted and not restored) while
preserving prior editions. **Why:** the `(evento_grupo, fonte, data_venda)` upsert conflict key
ignores `ano`, so one calendar day holds only one edition's value — the broad DELETE is the only
thing that touches cross-year rows, and scoping it by ano is the safety boundary. The default
of `delete_scope_ano=False` keeps legacy callers (manual reconsolidar, first build) unchanged.

## Wiring
The nightly sequence is duplicated across 4 paths (see daily-job-step-drift.md). The rolling
step goes AFTER `snapshot_diario_batch`, BEFORE `consolidar_curvas_historicas_batch`, in all 4.
In dev, `ENABLE_BACKGROUND_MAGENTO_SYNC=false` disables the whole nightly run — the step only
fires in production via the Scheduled Deployment consolidation path.
