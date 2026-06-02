---
name: Daily consolidation job step drift
description: The nightly batch sequence is duplicated across 3 execution paths that must stay in sync.
---

The daily snapshot/consolidation step list is hand-duplicated in THREE places, with no
shared helper. When you add a new nightly batch step you MUST add it to all three or
behavior silently diverges (e.g. manual rebuild not refreshing what the nightly run does):

1. `backend/app/core/cache.py` — internal scheduler (`_run_step(...)` sequence, ~02h BRT).
2. `backend/app/api/routes/admin.py` — token-protected `trigger_scheduled_daily_consolidation`
   (`_run_and_classify(...)` sequence).
3. `backend/app/api/routes/admin.py` — manual admin endpoint `POST /admin/snapshots/consolidar`
   (`_run()` inner thread, plain calls, easy to forget — it has no canonical-name loop).

**Why:** during the "Cortes de Projeção" freeze feature, the batch was added to (1) and (2)
but (3) was missed; a manual reconsolidation would not freeze cortes. Caught in review.

**How to apply:** any new `*_batch` added to the nightly run → grep for
`sincronizar_margem_bundle_rev_batch` (present in all 3) and add the new step next to each
occurrence. Consider centralizing into one shared step-list helper if it drifts again.
