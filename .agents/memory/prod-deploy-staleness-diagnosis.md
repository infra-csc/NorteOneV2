---
name: Production running stale (pre-fix) code
description: How to check whether a live user bug report is actually "fix not published yet" rather than a real regression, without needing app-level prod credentials.
---

# Production running stale (pre-fix) code

When a user reports a bug that contradicts a careful code trace (logic looks
correct, and an empirical test against synthetic data shaped like the real
row reproduces the *correct* behavior in dev), consider that the user may be
looking at the **published/deployed** app rather than the dev preview —
especially if they're on a mobile client, which strongly suggests they're
checking the app they use day-to-day (production), not the workspace preview.

VM/autoscale deployments do **not** auto-update when commits land on `main`
(including task-agent merges) — they only update on an explicit Publish.
So "I just fixed and merged this" does not imply "the live site has it."

**How to check without prod app credentials, only `getDeploymentInfo()`
(public visibility) and read-only log/DB access:**
1. `getDeploymentInfo()` → confirm `isDeployed` and get `primaryUrl`.
2. Fetch the deployed frontend's `index.html`, extract `/assets/*.js` bundle
   URLs, download them, and `grep` for a string that is unique to the fix
   (a new JSON field name, a distinctive log tag, translated UI copy added
   by the fix). Absence across the whole bundle is strong evidence the
   deployed build predates the fix. Minifiers rename local identifiers but
   not string literals or plain object-property names, so this is reliable.
3. Cross-check by grepping all captured deployment log files for backend-side
   tags/log-line formats unique to the new code path (Python log strings are
   never minified). Consistent absence across a large, representative sample
   corroborates the bundle finding.

**Why:** discovered when a user reported a "next-year event not appearing"
bug on the same page a task had just fixed for exactly that scenario — the
fix was verified correct in dev (including an empirical DB-backed test), so
the contradiction meant the live app simply hadn't been republished yet, not
that a new regression existed.

**How to apply:** before assuming a fresh regression in just-shipped code,
rule this out first when the report could plausibly be about the deployed
app (mobile session, "the site", non-dev language) — it's cheaper than
re-auditing already-verified logic.

## Fixing the query is not the same as fixing already-persisted data

A query/logic fix only changes what *future* reads compute. Any snapshot
table (`EventoDetailSnapshot`, daily/margin snapshots, etc.) already holding
rows computed by the *old* logic stays wrong until something explicitly
recomputes and re-persists it — publishing the fix alone does not retroactively
correct rows already sitting in the production database. Two ways that
happens in this project: the nightly scheduled batch re-touches "active"
(not-yet-concluded) entities automatically, or an admin manually triggers the
per-entity recompute endpoint (e.g. `recalcular-snapshot` / `consolidar-evento`)
through the live app's own authenticated UI. Neither is something the agent
should improvise around by writing directly to `PROD_DATABASE_URL` from a
standalone script — that bypasses the deployed process's in-memory caches
(TTL/SWR layers) which would keep serving the old value regardless, and
skips the concurrency/slot guards the endpoints use to avoid colliding with
real admin usage.

**How to apply:** after shipping a fix that corrects previously-miscomputed
values, tell the user explicitly that already-cached/persisted rows need one
of the two paths above — don't assume the fix is "fully live" just because
it's published and don't try to correct prod rows out-of-band.
