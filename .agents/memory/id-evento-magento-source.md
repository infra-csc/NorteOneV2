---
name: id_evento_magento canonical source
description: De onde vem o id_evento_magento usado pelo snapshot/marketing — sku_mappings é a fonte canônica, cadastro_evento é cache materializado.
---

A coluna `cadastro_evento.id_evento_magento` NÃO é um campo editável pelo usuário. A fonte canônica é a tabela `sku_mappings` (linhas com `fonte='MAGENTO'`), via o SKU do evento. O valor em `cadastro_evento` é um cache materializado mantido por sincronização automática.

**Why:** O snapshot_service (`sincronizar_margem_bundle_rev_batch`, ~linha 1911) e outros consumidores fazem `if not cadastro.id_evento_magento: skip` sem fallback. Sem o cache, eventos com SKU mapping correto ficavam órfãos de vendas e travavam no histórico até alguém dar UPDATE manual no banco. O caso de Blue Run RJ 2026 (sku BLU26RJ1, mapping MAGENTO 53171) ficou parado em ~1409 inscritos por isso.

**How to apply:**
- Para "ligar" um evento ao Magento: criar/editar o **mapeamento de SKU** (admin / sku-mappings) com `fonte=MAGENTO`, `id_externo=<ID Magento>`, `sku=<SKU do cadastro>`. O auto-sync `_sync_id_evento_magento_from_mapping` em `backend/app/api/routes/sku_mappings.py` propaga para `cadastro_evento` automaticamente em create/update/bulk.
- Para preencher histórico: rodar `scripts/backfill_id_evento_magento.sql` em PROD (idempotente, ~150-200 linhas).
- Para diagnosticar evento parado nas vendas: confira `cadastro_evento.id_evento_magento`. Se NULL apesar do mapping existir, é bug no auto-sync (pode ter sido bypass via SQL direto ou import sem passar pelos endpoints).
- NÃO adicionar campo "ID Evento Magento" no formulário de cadastro — duplica a verdade e desincroniza. Já foi tentado e revertido.
- Pegadinha futura: se algum dia precisar permitir override manual no cadastro (raríssimo), pense em flag tipo `id_evento_magento_override` separado, e faça o auto-sync respeitar o override.
