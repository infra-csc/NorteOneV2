-- Backfill: copia sku_mappings.id_externo (fonte=MAGENTO) para
-- cadastro_evento.id_evento_magento usando o SKU como chave (case-insensitive, trim).
--
-- Por que rodar: o snapshot_service.sincronizar_margem_bundle_rev_batch e
-- outros consumidores leem cadastro_evento.id_evento_magento diretamente. Quando
-- o cadastro tem SKU correto mas id_evento_magento NULL, os jobs noturnos pulam
-- o evento (margem_bundle_rev_snapshot fica vazio, evento_detail_snapshot
-- desatualizado, e a tela trava nas vendas antigas).
--
-- Idempotente: só atualiza quando o valor atual difere do mapping.
-- Após esta migração, o sync passa a ser automático via _sync_id_evento_magento_from_mapping
-- nos endpoints de create/update/bulk de sku-mappings.
--
-- Rode com role read-write em PROD. Espere ~150-200 linhas atualizadas.

BEGIN;

WITH upd AS (
  UPDATE cadastro_evento ce
  SET id_evento_magento = sm.id_externo
  FROM sku_mappings sm
  WHERE sm.fonte = 'MAGENTO'
    AND sm.sku IS NOT NULL
    AND ce.sku IS NOT NULL
    AND LOWER(TRIM(ce.sku)) = LOWER(TRIM(sm.sku))
    AND (ce.id_evento_magento IS NULL OR ce.id_evento_magento <> sm.id_externo)
  RETURNING ce.id, ce.nome, ce.sku, ce.id_evento_magento
)
SELECT COUNT(*) AS atualizados FROM upd;

-- Confira antes de COMMIT/ROLLBACK:
SELECT
  COUNT(*) FILTER (WHERE id_evento_magento IS NULL) AS ainda_sem_id,
  COUNT(*) FILTER (WHERE id_evento_magento IS NOT NULL) AS com_id
FROM cadastro_evento
WHERE sku IS NOT NULL AND TRIM(sku) <> '';

-- Conferir Blue Run RJ especificamente (id=109 em PROD):
SELECT id, nome, sku, id_evento_magento
FROM cadastro_evento
WHERE LOWER(TRIM(sku)) = 'blu26rj1';

COMMIT;
