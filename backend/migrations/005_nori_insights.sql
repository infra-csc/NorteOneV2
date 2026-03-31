-- Migration 005: nori_insights table
-- Stores proactive AI-generated insights for margin improvement opportunities.
-- Idempotent: uses CREATE TABLE IF NOT EXISTS and CREATE INDEX IF NOT EXISTS.

CREATE TABLE IF NOT EXISTS nori_insights (
    id                         SERIAL PRIMARY KEY,
    evento_id                  VARCHAR(200),
    evento_nome                VARCHAR(300) NOT NULL DEFAULT '',
    tipo                       VARCHAR(50)  NOT NULL,
    titulo                     VARCHAR(400) NOT NULL,
    conteudo                   TEXT         NOT NULL,
    acao_sugerida              TEXT,
    impacto_estimado_reais     NUMERIC(12, 2),
    impacto_estimado_percentual NUMERIC(6, 2),
    dados_contexto             JSONB,
    status                     VARCHAR(20)  NOT NULL DEFAULT 'novo'
                                    CHECK (status IN ('novo', 'visto', 'descartado')),
    gerado_em                  TIMESTAMP    NOT NULL DEFAULT NOW(),
    atualizado_em              TIMESTAMP    NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_nori_insights_status
    ON nori_insights (status);

CREATE INDEX IF NOT EXISTS ix_nori_insights_evento_id
    ON nori_insights (evento_id);

CREATE INDEX IF NOT EXISTS ix_nori_insights_gerado_em
    ON nori_insights (gerado_em DESC);

-- Unique index enforcing one insight per (evento_id, tipo, day) regardless of status.
-- Matches the service-layer deduplification policy in save_insights_to_db(), which
-- also blocks re-creation for discarded insights on the same day.
CREATE UNIQUE INDEX IF NOT EXISTS uq_nori_insights_per_day
    ON nori_insights (evento_id, tipo, DATE(gerado_em));
