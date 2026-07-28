-- Adiciona coluna ano ao kit_mapping_snapshot.
-- Distingue edições do ano corrente e do ano seguinte que aparecem juntas
-- no Mapeamento de Kits quando ambas têm carrinho ativo simultaneamente.
ALTER TABLE kit_mapping_snapshot ADD COLUMN IF NOT EXISTS ano INTEGER;
