---
name: "Ticket Atual (Kit) → Não encontrado" diagnosis
description: When event detail shows "Ticket Atual (Kit) → Não encontrado" or kits/promos don't appear, check for inverted Magento SKUs across years.
---

# "Ticket Atual (Kit) → Não encontrado" / kit não aparece no evento

**Sintoma:** página do evento mostra "Não encontrado" no Ticket Atual, ou um kit
(ex: Kit Promocional) configurado no `kit_config` não aparece na tela do evento.

**Causa raiz típica:** SKUs do Magento **invertidos entre anos** em `sku_mappings`
(fonte=MAGENTO). Ex.: evento 2026 fica com o SKU de 2025 e vice-versa — acontece
em lote quando os eventos do ano novo são criados copiando os do ano anterior no Magento.

**Por que quebra:** a resolução de ticket/kits liga `cadastro_evento` → Magento por SKU:
- caminho primário: `kit_config.id_evento` → `cadastro_evento.id_evento_magento` → `projeto_id`
- fallback: `id_externo` Magento → `sku_mappings.sku` → `cadastro_evento.sku` → `projeto_id`

Se o SKU do Magento está colado no evento do ano errado, ambos os caminhos falham:
o app encontra o evento do ano anterior (ou nenhum), nunca o evento correto onde os
bundles/kits realmente vivem. Resultado: ticket_atual_map sem entrada → `_get_ticket_atual_for_event`
retorna 0.0 → frontend mostra "Não encontrado".

**Como diagnosticar:** comparar `sku_mappings` (fonte=MAGENTO) dos dois anos do mesmo
evento_grupo — ver se o par (id_externo, ano) bate com o (sku) esperado. id_externo
maior/recente = ano mais novo.

**Correção:** corrigir os SKUs trocados no admin de Mapeamento de SKU. Ao salvar um
mapping MAGENTO, `_sync_id_evento_magento_from_mapping` repropaga
`cadastro_evento.id_evento_magento` automaticamente (match por SKU). Confirmar em prod
que `cadastro_evento.id_evento_magento` passou a apontar pro id_externo correto.

**Atenção ao cache:** `ticket_atual_map` tem TTL ~15min em memória no processo backend.
Após a correção dos dados, a tela pode mostrar "Não encontrado" por até ~15min até o
cache expirar (ou republicar o app pra limpar na hora).
