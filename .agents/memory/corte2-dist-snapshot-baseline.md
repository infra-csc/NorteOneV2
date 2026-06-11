---
name: Corte 2 baseline needs a frozen dist snapshot
description: Why the additive "Projeção Ajuste" silently resets to 0, and the self-heal that fixes it.
---

# Corte 2 additive baseline must come from a FROZEN dist snapshot, never live values

The Corte-2 additive UI ("Projeção Convicta" = baseline, "Projeção Ajuste" = acréscimo,
Total = baseline + ajuste) reads its baseline from `GET /api/projecao/corte1-distribuicao`.
That endpoint serves the frozen `projecao_corte_dist_snapshot` when it exists, otherwise
falls back to an `fonte="aproximado"` branch that returns the LIVE current projeção as the
baseline.

**The trap:** if an event is in Corte 2 (`projecao_corte_snapshot.valor_corte_1` set) but has
NO dist snapshot row, the aproximado baseline moves with every save → each saved ajuste is
absorbed back into the baseline → reopening the modal shows `ajuste = total - baseline = 0`.
The user sees "Projeção Ajuste não salva, volta com 0". Same mechanism hits the editable
camiseta-avulsa ajuste and any kit ajuste.

**Why the gap existed:** `capturar_dist_snapshot_corte1` was deployed AFTER several events had
already frozen Corte 1, so those events have a `projecao_kit_corte_snapshot` (camiseta teto)
but no dist snapshot — the two captures must run in lockstep but didn't historically.

**Fix / how to apply:** `get_corte1_distribuicao` self-heals — when `em_corte2 and snap is None`
it calls `capturar_dist_snapshot_corte1` once (freezing the baseline from current state),
commits, re-queries; wrapped in `try/except IntegrityError + rollback` for the unique
`(evento_id, area_projecao_id)` race. The capture snapshots ALL areas of the event at once, so
one read heals the whole event. Backfill is from CURRENT live (true historical Corte-1 per-area
distribution was never captured for legacy events — best-effort, not exact).

**Rule:** any path that freezes Corte 1 must write the dist snapshot in lockstep with the kit
(camiseta teto) snapshot, or the additive Corte-2 layout silently corrupts. Writing inside this
GET is transitional debt — a proper one-time backfill (events with `valor_corte_1 IS NOT NULL`
and no dist snapshot) could later replace it.
