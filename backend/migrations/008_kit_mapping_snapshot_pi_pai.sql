-- Adiciona coluna pi_pai_min_price ao kit_mapping_snapshot.
-- Armazena o valor bruto de catalog_product_index_price.min_price do bundle pai,
-- separado do campo special_price (que é COALESCE(pi_pai.min_price, fallback)).
-- Necessário para que a leitura do snapshot possa distinguir:
--   - special_price vindo do índice (pi_pai_min_price IS NOT NULL) → usa diretamente
--   - special_price vindo do fallback (soma de componentes) → aplica Regra B (>= price)
-- Isso corrige o bug onde kits com min_price do índice > soma de componentes EAV
-- tinham o special_price descartado incorretamente (ex.: Troféu Brasil 2ª Etapa).
ALTER TABLE kit_mapping_snapshot
    ADD COLUMN IF NOT EXISTS pi_pai_min_price NUMERIC(12,2);
