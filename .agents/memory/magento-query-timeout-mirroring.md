---
name: Magento/Ativo query timeout mismatch when mirroring sibling SQL functions
description: A new SQL function copied from an existing "impl" pattern silently got a shorter MAX_EXECUTION_TIME hint than its source, causing spurious timeouts that looked like a query-correctness bug.
---

## The lesson

This codebase's Magento/Ativo raw-SQL functions embed a MySQL optimizer hint literal
in the query text itself, e.g. `SELECT /*+ MAX_EXECUTION_TIME(90000) */ ...`. When
writing a new sibling function "mirroring" an existing one (same joins/filters, plus
one new dimension), it is easy to structurally copy the query correctly but still type
a different timeout literal (e.g. `60000` instead of `90000`) — nothing catches this at
review time because the query still runs and still returns correct rows for small/fast
events. It only surfaces as `(3024, 'Query execution was interrupted, maximum statement
execution time exceeded')` on larger events, which looks exactly like a correctness or
performance regression in the new dimension you added, when the SQL logic was actually
fine all along.

**Why:** Existing sibling functions' timeout budgets (60s/90s/etc.) were tuned per query
shape against real replica load; a shorter budget copied by accident is invisible in code
review (both numbers look equally plausible) and only fails probabilistically in
production-scale data, not in small dev smoke tests.

**How to apply:** When adding a new function that mirrors an existing Magento/Ativo SQL
function (same tables/joins, new GROUP BY dimension or column), diff the literal
`MAX_EXECUTION_TIME(...)` value — and any other hardcoded constant — against the exact
source function you're mirroring, not just the query structure. Test with an event/date
range known to have non-trivial data volume, not just a happy-path row-shape check,
before trusting a "0 rows" result as correct rather than a silent timeout swallowed by
a broad `except Exception` (these functions intentionally degrade to `[]` on any error,
so a timeout and "genuinely no data" look identical from the caller's side — check logs
for `Erro ... by IDs: (pymysql.err.OperationalError) (3024, ...)` before accepting an
empty result as ground truth).
