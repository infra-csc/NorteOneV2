---
name: Projeção Convicta = valor_corte_1 (canônico)
description: Por que o total "Convicta" (Corte 1) e a soma por área podem divergir, e como o consolidado reconcilia.
---

# Projeção Convicta (Corte 1): total canônico vs foto por área

**Regra:** o total da "Projeção Convicta" é `projecao_corte_snapshot.valor_corte_1` — congelado UMA vez no instante do Corte 1 e é a fonte canônica. A foto por área (`projecao_corte_dist_snapshot`, `kits_json`) é só o detalhamento e PODE divergir do total.

**Why (deriva real):** `capturar_dist_snapshot_corte1` relê o AO VIVO e reescreve TODAS as áreas. O self-heal de `get_corte1_distribuicao` (dispara quando uma área específica não tem foto) o chamava para todas as áreas sob o carimbo de data do congelamento original → edições feitas DEPOIS do corte vazavam para a foto, somando ≠ `valor_corte_1`. Também há eventos sem nenhuma foto (caem no fallback ao vivo no consolidado), que seguem o ao vivo, não o congelado.

**How to apply:**
- Self-heal usa `capturar_dist_snapshot_corte1(..., only_missing=True)`: preenche só lacunas, nunca regrava/deleta áreas já congeladas. Freeze inicial e recongelar manual continuam com `only_missing=False` (regravam tudo de propósito, e o recongelar atualiza `valor_corte_1` em lockstep).
- O consolidado (`_compute_consolidado`) reconcilia em tempo de leitura: quando o Corte 1 está congelado, ajusta a soma das `convicta_quantidade` (e os `convicta_kits`) para bater EXATO com `valor_corte_1`, via `_aplicar_delta_desc` (delta>0 soma no maior; delta<0 remove em cascata dos maiores, sem negativos). Cobre tanto fotos derivadas quanto eventos sem foto, sem migração de dados histórica.
- Decisão de negócio do usuário (jun/2026): "Convicta" deve permanecer congelada → o total canônico (5.500 no caso do Night Run I - Manaus) vence; o detalhe por área é trazido para somar esse valor.
