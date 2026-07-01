---
name: Magento threadpool starvation vs login
description: Why sync Magento routes could starve /auth/login, and the admission-control rules that prevent it.
---

# Magento threadpool starvation vs /auth/login

Sync (`def`) FastAPI endpoints all run in ONE shared anyio threadpool. Magento is
serialized at concurrency=1 (a hard remote-server limit — parallel heavy queries
kill it with error 3024; it is a DIRECT TCP/IP MySQL conn, NOT the SSH tunnel).
A queued Magento call used to hold its threadpool thread for the full acquire
timeout with UNBOUNDED waiters, so a burst of Magento requests drained the pool
and starved every other sync route — including `/auth/login`.

**The rules that keep login alive (all in `db_retry.magento_run`):**
- There is an admission gate (`_magento_pending` counter under a lock) that caps
  how many calls may occupy a thread inside `magento_run` at once. Over the cap →
  raise `MagentoEngineUnavailable` immediately (falls to snapshot piso) WITHOUT
  holding a thread. Never let waiters grow unbounded again.
- The cap is profile-aware: background (scheduler/warmup/jobs) has a LOWER cap
  than interactive, reserving slots so a background burst can't deny interactive
  admission. Env: `MAGENTO_MAX_PENDING` (total), `MAGENTO_MAX_PENDING_BG`.
- Keep the queue acquire timeout modest (env `MAGENTO_ACQUIRE_TIMEOUT_S`) — long
  waits re-create the starvation.
- The anyio threadpool is widened at startup (env `FASTAPI_THREADPOOL_SIZE`, ~64)
  but stays UNDER the local PG pool ceiling (25+50=75) so it can't exhaust PG.

**Why:** login is a sync route with no Magento dependency, yet it went down
whenever Magento got slow. The fix is admission control + reserved interactive
capacity, not raising Magento concurrency.

**How to apply:** NEVER raise Magento concurrency above 1. When adding new
Magento call sites, route them through `magento_run` (never bypass to
`engine_magento.connect()` directly) so they honor the semaphore + admission cap.
Pending counter increments only AFTER the cap check passes and decrements in the
per-attempt `finally` — keep that invariant on any edit to the retry loop.
