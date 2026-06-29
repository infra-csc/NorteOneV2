---
name: Authoritative down-correction of inflated inscritos
description: How/when the "Atualizar" button may LOWER a finished event's subscriber count past the anti-partial floors, and why the completeness signal is trustworthy.
---

# Correção autoritativa para baixo (inscritos inflados)

Eventos concluídos têm 3 guardas que impedem BAIXAR o valor de inscritos
(anti-resposta-parcial do Magento): alinhamento "só sobe" da tabela de kits,
guard de `_event_is_past` (preserva currentSales anterior) e piso de 95% de
margem em `save_persisted_detail`. O botão "Atualizar" (`force_magento_refresh`)
pode baixar o valor **somente** quando a leitura ao vivo é verificada completa.

## Sinal de "leitura verificada completa"
`_live_read_verified_complete` = `force_magento_refresh` AND
`meta_out.count_source=="live"` AND `meta_out.revenue_source=="live"` AND
`avisos_out` vazio AND `not _margem_por_kit_is_degraded(rows)` AND `kit_qty>0`.

**Why é confiável (não é inferência frágil):**
- `count_query` é UMA query única sobre todos os bundle_ids — SQL ou completa ou
  lança; `count_source=="live"` ⇒ resultado completo. Bundles com 0 vendas
  simplesmente não retornam linha (não é parcialidade).
- `revenue_query` é batcheada; QUALQUER backfill parcial vira
  `revenue_source=="partial"` (não "live"). "live" ⇒ nenhum batch falhou.
- Sob `force_refresh`, o backfill que restaura o piso do snapshot é PULADO de
  propósito (count e revenue), então o valor ao vivo não é "puxado para cima".
- "live < snapshot" sozinho NÃO distingue parcial de correção legítima — por
  isso o sinal vem da MECÂNICA da query (sucesso/sem-parcial), nunca de comparar
  números com o snapshot.

## Como aplicar
Quando o sinal é verdadeiro e a tabela de kit < currentSales: adquire o slot
global de reconsolidação (`_try_acquire_evento_slot(check_cooldown=False)`),
baixa currentSales, seta `_authoritative_downcorrect=True`, roda sync de margem
ESCOPADO ao evento (`sincronizar_margem_bundle_rev_batch(only_bundle_ids=...)`,
que ignora o freeze), libera o slot. `_authoritative_downcorrect` afrouxa Guard B
e o piso de 95% (`bypass_completed_guard`) SÓ nesse caminho. Slot ocupado ou
leitura parcial ⇒ preserva piso + aviso ao usuário. Auto-heal noturno
(`reconcile_completed_event_details`) chama o mesmo caminho com
`force_magento_refresh=True` para concluídos dentro da janela de freeze.

**NÃO confundir:** o `EXCLUDED` direto (não GREATEST) para `qtd_inscricoes` de
bundles MAPEADOS em `_persist_batch` é PRÉ-EXISTENTE (fix de cross-event
contamination), não faz parte dessa correção e não deve virar GREATEST.
