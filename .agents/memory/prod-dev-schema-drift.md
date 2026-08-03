---
name: Prod/dev schema drift diagnosis
description: How to check whether a "feature doesn't work" report is actually a missing-table/column (or missing-row/mapping) in production rather than a code bug, and how this project's prod vs dev DBs are told apart.
---

## The check

When a save/write feature "doesn't work" (button seems to do nothing, or errors generically)
right after it starts getting real usage, check for prod/dev schema drift before assuming a
frontend/backend logic bug:

```sql
-- run once with environment: "development" and once with environment: "production"
SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name;
```

Diff the two lists. If the table the feature writes to is dev-only, every write in the live
(published) app fails at the DB layer (`relation does not exist`), regardless of how correct
the frontend/backend code is.

**Why:** found this after a feature ("Análise Diária" daily-analysis notes) was reported broken
right after a UI change made it far more visible/used. The frontend and backend logic were both
correct; `analises_diarias` simply didn't exist yet in the production database because the schema
change had never been published. Confirmed via `executeSql` with `environment: "production"` —
`information_schema.tables` had no row for it there, while a sibling feature table
(`acoes_comerciais`, older/already-published) existed in both and had rows created minutes earlier
in prod.

**How to apply:** the fix is NOT a migration script — per the database skill, prod schema is
synced only by the user Publishing (Replit diffs dev vs prod schema and applies it). Explain the
root cause and suggest `SuggestUserAction({ action: "deploy" })`.

## Row-level drift (not just missing tables/columns)

The same drift also happens one level down: the table/column exists in both
databases, but a specific **row** (a mapping, a config entry) only exists in
prod. Symptom: an event/entity the user references from the live app cannot
be found via dev-environment `executeSql` at all — not degraded data, zero
rows. Before concluding "this doesn't exist" or trying to reproduce in dev,
re-run the exact same lookup with `environment: "production"`; a row that
appears there but not in dev means the feature/data is real, just
prod-only, and any validation or admin action for it must target prod (reads
via SSH-tunneled external sources like Ativo/Magento are unaffected by this
split since those are outside the app's own Postgres, but the app's own
mapping tables, e.g. `sku_mappings`, are not).

**Why:** hit this validating a fix for a specific reported event — the
`sku_mappings` row linking it to its external-system id existed only in
production, never in dev, so the dev app's own lookup path returned nothing
for it even though the underlying bug and fix applied equally to both.

## Telling prod and dev apart in this project

- `acoes_comerciais` (or any actively-used table) having recent `MAX(created_at)` timestamps in
  prod but stale/old ones in dev confirms **production carries the real, live user traffic** —
  dev is a separate copy only touched by manual/agent testing. Don't assume dev row counts (e.g.
  "zero rows") reflect real-world usage; check prod.
- As of 2026-07-29, tables present in dev but NOT yet in production: `analises_diarias`,
  `cortesia_cupom_codigo`, `cortesia_solicitacao`, `user_ui_pref`. This list will change after the
  next publish — re-run the diff rather than trusting this snapshot.
