ALTER TABLE kit_config ADD COLUMN IF NOT EXISTS is_kit_basico BOOLEAN DEFAULT FALSE NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_kit_basico_per_evento ON kit_config (id_evento) WHERE is_kit_basico = TRUE;
