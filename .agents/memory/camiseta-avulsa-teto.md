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

# Teto capture MUST happen in EVERY Corte-1 freeze path

The teto is only meaningful if `ProjecaoKitCorteSnapshot` is written at the moment
Corte 1 freezes. There are **two** freeze paths and both must capture it via the
shared helper `capturar_kit_snapshot_corte1(db, evento_id, now)` (snapshot_service.py):
(1) auto/consolidado freeze `congelar_cortes_para_eventos`, and (2) admin manual
recongelar `recongelar_corte` (projecao.py). 

**Why:** Originally only path (1) captured the kit snapshot. Events frozen via the
admin manual path (`congelado_manual_corte_1=True`) kept NO kit snapshot row → teto
stayed 0 → validation was silently skipped ("not validating" bug). This is the same
class of bug as the nightly-job step drift: freeze logic is duplicated across paths
and a new sub-step added to one path silently no-ops in the others.

**How to apply:** Never inline the capture — always call the shared helper from any
code that sets `valor_corte_1`/`congelado_corte_1_em`. The helper upserts current
camiseta qty per area AND zeroes areas whose kit was removed ("regrava com o atual").
For already-frozen legacy events with no snapshot row, `_camiseta_avulsa_info` has a
read-only fallback: teto = current saved camiseta total for that (evento, área), i.e.
"only decrease from current". `congelar_cortes_para_eventos`'s auto-DESCONGELAR
deletes the kit snapshot when Corte 1 unfreezes, so the fallback never collides with it.
