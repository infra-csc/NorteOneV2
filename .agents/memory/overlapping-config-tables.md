---
name: Overlapping config/alias tables feeding one pipeline
description: When two admin screens/tables appear to configure the same normalization or business rule, check row counts in dev AND prod before assuming which is authoritative.
---

When a value-normalization or business-rule pipeline is fed by more than one
admin-configurable table (e.g. two alias/override tables consulted in
sequence for the same field), do not assume the more prominent, newer, or
more capable one is "the" system actually in use. Query row counts for each
table directly, in both dev and prod, before deciding which to keep.

**Why:** Two screens ("Configuração Modalidade" / `modalidade_alias` and
"Padrões de Dimensão" / `detalhe_dimensao_alias`) both fed the same
modalidade-normalization step in `detalhe_eventos_service.py`. The first had
a dedicated nav entry, full CRUD API, and looked like the obvious config
screen — but had 0 rows in dev AND prod, so it never did anything. The
second (less discoverable, mounted as a tab inside an unrelated screen) held
the 3 rules actually shaping output. Guessing from code/UI prominence alone
would have picked the wrong one to keep.

**How to apply:** Before consolidating or deleting one of two candidate
config systems: (1) run a read-only row-count query against both dev and
prod for every table involved, (2) grep for other consumers of the
model/table being considered for removal to confirm isolation. Zero rows in
both environments makes the removal a pure code/schema change with no
data-migration step — verify by re-running the pipeline's surviving stage
against representative inputs and confirming output is unchanged.
