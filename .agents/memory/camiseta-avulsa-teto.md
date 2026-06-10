---
name: Camiseta avulsa — teto (ceiling) rule
description: After Corte 1 freezes, "Camiseta avulsa" (ex "Kit Completo - Sem camiseta") is capped by the frozen value, user can only DECREASE.
---

# Camiseta avulsa is a CEILING, not a floor

When Corte 1 freezes, the kit "Kit Completo - Sem camiseta" is displayed as
"Camiseta avulsa". The value captured at Corte 1 (stored in
`ProjecaoKitCorteSnapshot.valor_corte_1`) is the **teto (máximo)**: the user may
only edit it **downward** (qty ≤ teto). Omitting the kit or setting it to 0 is a
valid decrease and is allowed.

**Why:** Business rule. It was originally implemented as a *piso* (floor — user
could only increase), then reversed to a ceiling per the product owner. The DB
column name `valor_corte_1` is neutral (just "value frozen at Corte 1"), so the
reversal needed no migration — only the comparison direction and the UI
naming/labels flipped (piso→teto, min→max, "só aumenta"→"só diminui").

**How to apply:** Backend validation lives in `_validate_camiseta_avulsa_teto`
(projecao.py): reject only when a provided qty > teto; skip entirely when
`teto <= 0` (frozen but no snapshot row). The frontend must gate the input `max`
and the helper text by `corte1_congelado && teto > 0` — applying `max={teto}`
with teto=0 would wrongly hard-limit the field to 0 while the API accepts any
value. API contract field is `camiseta_avulsa_teto` / `CamisetaAvulsaInfoResponse.teto`.
