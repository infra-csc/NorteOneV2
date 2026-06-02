---
name: id-sequence-desync
description: PostgreSQL id-sequence drift from explicit-id seeds/imports causing PK UniqueViolation on insert
---

# id sequence desync (PK UniqueViolation on insert)

When rows are inserted with explicit `id` values (seed scripts, data imports, copying
between dev and prod), the table's `_id_seq` is NOT advanced. Later normal inserts then
collide: `duplicate key value violates unique constraint "<table>_pkey"`. Seen in prod
on `projecao_inscritos` ("Erro ao criar projeção"), but it is a whole-class problem.

**Fix (two layers, both in place):**
- `_resync_id_sequences()` in `backend/main.py` runs at Phase 0 startup: loops every
  public table with an `id` column and `setval`s its owned sequence to
  `GREATEST(current last_value, MAX(id))` — **monotonic, never moves a sequence
  backward**, skips empty tables. This is how prod gets fixed (runs on next deploy).
- In-route self-heal in `create_projecao` (`backend/app/api/routes/projecao.py`):
  on `IntegrityError` matching a `_pkey` duplicate, rollback → `_resync_projecao_sequences`
  → retry once.

**Why:** prod DB is read-only via the database tool, so the sequence can only be
repaired by code the app itself runs against prod (startup hook), not by an ad-hoc
write. Keep the repair monotonic to stay safe under concurrent writers.

**How to apply:** if any other table starts throwing `_pkey` duplicate on insert, the
startup resync already covers it after a restart/deploy; for a hot path add the same
catch-resync-retry pattern.
