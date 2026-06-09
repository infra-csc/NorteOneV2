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
