-- Snapshot persistente do Mapeamento de Kits (Magento + Ativo).
-- Permite que a tela /admin/kit-config abra instantaneamente sem rodar
-- a MAGENTO_KITS_QUERY pesada em cada request, e que o botão "Atualizar"
-- aplique apenas o diff (novos / alterados / removidos).
CREATE TABLE IF NOT EXISTS kit_mapping_snapshot (
    id               SERIAL PRIMARY KEY,
    bundle_entity_id BIGINT       NOT NULL,
    tipo_categoria   VARCHAR(255) NOT NULL DEFAULT '',
    fonte            VARCHAR(16)  NOT NULL,
    id_evento        VARCHAR(64),
    nome_evento      TEXT,
    nome_kit         TEXT,
    lote_atual       TEXT,
    price            NUMERIC(12,2),
    special_price    NUMERIC(12,2),
    status_kit       VARCHAR(16),
    content_hash     VARCHAR(64)  NOT NULL,
    atualizado_em    TIMESTAMP    NOT NULL DEFAULT NOW(),
    visto_em         TIMESTAMP    NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_kit_mapping_bundle_tipocat
    ON kit_mapping_snapshot (bundle_entity_id, tipo_categoria);

CREATE INDEX IF NOT EXISTS ix_kit_mapping_fonte
    ON kit_mapping_snapshot (fonte);
