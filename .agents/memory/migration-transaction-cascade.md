---
name: Column migration transaction cascade + create_all vs server_default
description: Why one failing statement in _run_column_migrations silently voids later ones, and why new ORM models need server_default for raw-SQL seed inserts to work.
---

## The pattern

`_run_column_migrations()` in `backend/main.py` runs its entire `migrations` list against **one shared session/transaction**, with a per-statement `try/except` that only logs a warning — it never rolls back the failed statement. In PostgreSQL, once one statement errors, the whole transaction is marked aborted; every statement after it fails too ("current transaction is aborted"), and the final `db.commit()` at the end of the loop effectively performs a rollback, discarding everything in that batch — including earlier statements that looked like they succeeded.

**Why:** Postgres doesn't allow partial-transaction recovery without an explicit `ROLLBACK`/savepoint, which this loop never issues per-statement.

**How to apply:** Don't trust "no error was logged for statement N" as proof it was persisted if a later statement in the same list failed. Idempotent statements (`IF NOT EXISTS`, `ON CONFLICT DO NOTHING`) self-heal on the next restart, so a single bad statement is recoverable, but always re-verify via a live SQL query after a change to this list — don't infer success purely from clean-looking logs of one statement.

## The specific trap: new table + new ORM model together

If you add a brand-new SQLAlchemy model in the same change as a raw-SQL `CREATE TABLE IF NOT EXISTS` migration for that same table, `Base.metadata.create_all()` (which runs at startup before `_run_column_migrations()`) creates the table first, **from the model**, not from your raw SQL string — so your raw `CREATE TABLE IF NOT EXISTS` becomes a silent no-op.

SQLAlchemy's `Column(..., default=X)` is a Python/ORM-side default — it only applies when a row is inserted through the ORM. It does **not** appear in the actual DDL. So a NOT NULL column with only `default=` (no `server_default=`) gets created with no real Postgres-level default. A raw-SQL seed `INSERT` that omits that column (relying on the DEFAULT clause you wrote in your migration string) then fails with a NOT NULL violation, because the live schema has no such default — and per the cascade above, that failure also silently voids every later statement in the same migration batch.

**How to apply:** for any new table that has both a model and a raw-SQL migration: (1) give NOT NULL columns with a default both `default=` and `server_default=text(...)`, and (2) make any raw-SQL seed `INSERT` list every NOT-NULL column explicitly rather than relying on a DEFAULT clause in the migration string, since you can't control which of the two DDL paths actually creates the table first.
