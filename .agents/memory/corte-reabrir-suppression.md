---
name: Corte reabrir vs auto-freeze
description: Why reopening a projeção corte needs a persistent suppression flag
---
The consolidado compute (`_compute_consolidado` → `congelar_cortes_para_eventos`)
runs an automatic live-freeze on EVERY read, and the nightly batch delegates to
the same single-source function. So simply nulling a corte snapshot (Reabrir)
never sticks: the next read re-freezes any corte whose cut window already arrived.

**Rule:** To make an admin "Reabrir" persist as live tracking, a corte must carry
a persistent suppression flag (`reaberto_manual_corte_1/2` on ProjecaoCorteSnapshot).
Reabrir sets it True; "Congelar agora" (recongelar) clears it False. The freeze
function must skip suppressed cortes in BOTH the early-continue (treat as done) AND
each individual freeze block (`and not cX_suppressed`) — otherwise a suppressed
corte still gets frozen when the OTHER corte needs freezing.

**Why:** User chose manual control — a reopened corte only re-freezes on explicit
"Congelar agora", never automatically.

## Manual freeze must persist outside the D-N window
`congelar_cortes_para_eventos` also has an auto-DESCONGELAR block that clears any
frozen corte whose window is NOT currently reached (`not need_X`). So a manual
"Congelar agora" on a corte before its D-N window (common for corte 2 / Projeção
de Ajuste, whose window sits closer to the event) was reverted on the next read.

**Rule:** A manual freeze needs its OWN persistent flag (`congelado_manual_corte_1/2`),
set True by recongelar and False by reabrir, and the auto-descongelar block must
skip cortes where it is set. `reaberto_manual_*` and `congelado_manual_*` are
mutually exclusive by construction (each endpoint sets one True, the other False).

**Why:** "Congelar agora" is an explicit admin choice — it must hold regardless of
the automatic window, and only "Reabrir" undoes it.
