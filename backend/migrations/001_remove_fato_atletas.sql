-- Migration: Remove fato_atletas table and add project references to satellite tables
-- Date: 2026-01-07
-- Description: Moves projeto_id, categoria_atleta_id, tempo_id, versao_projecao, observacao, created_by
--              from fato_atletas to each satellite table (metricas, canais, kits, custos)
-- 
-- IMPORTANTE: Execute este script manualmente se você já tem dados no banco
-- Para ambientes novos, o SQLAlchemy criará as tabelas com a estrutura correta

BEGIN;

-- Step 1: Add new columns to satellite tables (if they don't exist)

-- FatoAtletasMetricas
DO $$ 
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'fato_atletas_metricas' AND column_name = 'fato_atletas_id') THEN
        ALTER TABLE fato_atletas_metricas ADD COLUMN IF NOT EXISTS projeto_id INTEGER;
        ALTER TABLE fato_atletas_metricas ADD COLUMN IF NOT EXISTS categoria_atleta_id INTEGER;
        ALTER TABLE fato_atletas_metricas ADD COLUMN IF NOT EXISTS tempo_id INTEGER;
        ALTER TABLE fato_atletas_metricas ADD COLUMN IF NOT EXISTS versao_projecao INTEGER DEFAULT 1;
        ALTER TABLE fato_atletas_metricas ADD COLUMN IF NOT EXISTS observacao TEXT;
        ALTER TABLE fato_atletas_metricas ADD COLUMN IF NOT EXISTS created_by INTEGER;
    END IF;
END $$;

-- FatoAtletasCanais
DO $$ 
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'fato_atletas_canais' AND column_name = 'fato_atletas_id') THEN
        ALTER TABLE fato_atletas_canais ADD COLUMN IF NOT EXISTS projeto_id INTEGER;
        ALTER TABLE fato_atletas_canais ADD COLUMN IF NOT EXISTS categoria_atleta_id INTEGER;
        ALTER TABLE fato_atletas_canais ADD COLUMN IF NOT EXISTS tempo_id INTEGER;
        ALTER TABLE fato_atletas_canais ADD COLUMN IF NOT EXISTS versao_projecao INTEGER DEFAULT 1;
        ALTER TABLE fato_atletas_canais ADD COLUMN IF NOT EXISTS observacao TEXT;
        ALTER TABLE fato_atletas_canais ADD COLUMN IF NOT EXISTS created_by INTEGER;
    END IF;
END $$;

-- FatoAtletasKits
DO $$ 
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'fato_atletas_kits' AND column_name = 'fato_atletas_id') THEN
        ALTER TABLE fato_atletas_kits ADD COLUMN IF NOT EXISTS projeto_id INTEGER;
        ALTER TABLE fato_atletas_kits ADD COLUMN IF NOT EXISTS categoria_atleta_id INTEGER;
        ALTER TABLE fato_atletas_kits ADD COLUMN IF NOT EXISTS tempo_id INTEGER;
        ALTER TABLE fato_atletas_kits ADD COLUMN IF NOT EXISTS versao_projecao INTEGER DEFAULT 1;
        ALTER TABLE fato_atletas_kits ADD COLUMN IF NOT EXISTS observacao TEXT;
        ALTER TABLE fato_atletas_kits ADD COLUMN IF NOT EXISTS created_by INTEGER;
    END IF;
END $$;

-- FatoAtletasCustos
DO $$ 
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'fato_atletas_custos' AND column_name = 'fato_atletas_id') THEN
        ALTER TABLE fato_atletas_custos ADD COLUMN IF NOT EXISTS projeto_id INTEGER;
        ALTER TABLE fato_atletas_custos ADD COLUMN IF NOT EXISTS categoria_atleta_id INTEGER;
        ALTER TABLE fato_atletas_custos ADD COLUMN IF NOT EXISTS tempo_id INTEGER;
        ALTER TABLE fato_atletas_custos ADD COLUMN IF NOT EXISTS versao_projecao INTEGER DEFAULT 1;
        ALTER TABLE fato_atletas_custos ADD COLUMN IF NOT EXISTS observacao TEXT;
        ALTER TABLE fato_atletas_custos ADD COLUMN IF NOT EXISTS created_by INTEGER;
    END IF;
END $$;

-- Step 2: Migrate data from fato_atletas to satellite tables (only if fato_atletas exists)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'fato_atletas') THEN
        -- Update FatoAtletasMetricas
        UPDATE fato_atletas_metricas m
        SET 
            projeto_id = fa.projeto_id,
            categoria_atleta_id = fa.categoria_atleta_id,
            tempo_id = fa.tempo_id,
            versao_projecao = COALESCE(fa.versao_projecao, 1),
            observacao = fa.observacao,
            created_by = fa.created_by
        FROM fato_atletas fa
        WHERE m.fato_atletas_id = fa.id AND m.projeto_id IS NULL;

        -- Update FatoAtletasCanais
        UPDATE fato_atletas_canais c
        SET 
            projeto_id = fa.projeto_id,
            categoria_atleta_id = fa.categoria_atleta_id,
            tempo_id = fa.tempo_id,
            versao_projecao = COALESCE(fa.versao_projecao, 1),
            observacao = fa.observacao,
            created_by = fa.created_by
        FROM fato_atletas fa
        WHERE c.fato_atletas_id = fa.id AND c.projeto_id IS NULL;

        -- Update FatoAtletasKits
        UPDATE fato_atletas_kits k
        SET 
            projeto_id = fa.projeto_id,
            categoria_atleta_id = fa.categoria_atleta_id,
            tempo_id = fa.tempo_id,
            versao_projecao = COALESCE(fa.versao_projecao, 1),
            observacao = fa.observacao,
            created_by = fa.created_by
        FROM fato_atletas fa
        WHERE k.fato_atletas_id = fa.id AND k.projeto_id IS NULL;

        -- Update FatoAtletasCustos
        UPDATE fato_atletas_custos cu
        SET 
            projeto_id = fa.projeto_id,
            categoria_atleta_id = fa.categoria_atleta_id,
            tempo_id = fa.tempo_id,
            versao_projecao = COALESCE(fa.versao_projecao, 1),
            observacao = fa.observacao,
            created_by = fa.created_by
        FROM fato_atletas fa
        WHERE cu.fato_atletas_id = fa.id AND cu.projeto_id IS NULL;
    END IF;
END $$;

-- Step 3: Delete orphan rows without projeto_id (safety measure)
DELETE FROM fato_atletas_metricas WHERE projeto_id IS NULL;
DELETE FROM fato_atletas_canais WHERE projeto_id IS NULL;
DELETE FROM fato_atletas_kits WHERE projeto_id IS NULL;
DELETE FROM fato_atletas_custos WHERE projeto_id IS NULL;

-- Step 4: Make projeto_id NOT NULL after migration
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'fato_atletas_metricas' AND column_name = 'projeto_id' AND is_nullable = 'YES') THEN
        ALTER TABLE fato_atletas_metricas ALTER COLUMN projeto_id SET NOT NULL;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'fato_atletas_canais' AND column_name = 'projeto_id' AND is_nullable = 'YES') THEN
        ALTER TABLE fato_atletas_canais ALTER COLUMN projeto_id SET NOT NULL;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'fato_atletas_kits' AND column_name = 'projeto_id' AND is_nullable = 'YES') THEN
        ALTER TABLE fato_atletas_kits ALTER COLUMN projeto_id SET NOT NULL;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'fato_atletas_custos' AND column_name = 'projeto_id' AND is_nullable = 'YES') THEN
        ALTER TABLE fato_atletas_custos ALTER COLUMN projeto_id SET NOT NULL;
    END IF;
END $$;

-- Step 5: Drop old constraints that reference fato_atletas_id (if they exist)
DO $$
BEGIN
    ALTER TABLE fato_atletas_metricas DROP CONSTRAINT IF EXISTS fato_atletas_metricas_fato_atletas_id_fkey;
    ALTER TABLE fato_atletas_canais DROP CONSTRAINT IF EXISTS fato_atletas_canais_fato_atletas_id_fkey;
    ALTER TABLE fato_atletas_kits DROP CONSTRAINT IF EXISTS fato_atletas_kits_fato_atletas_id_fkey;
    ALTER TABLE fato_atletas_custos DROP CONSTRAINT IF EXISTS fato_atletas_custos_fato_atletas_id_fkey;
EXCEPTION WHEN OTHERS THEN
    NULL;
END $$;

-- Step 6: Drop the fato_atletas_id column from satellite tables
ALTER TABLE fato_atletas_metricas DROP COLUMN IF EXISTS fato_atletas_id;
ALTER TABLE fato_atletas_canais DROP COLUMN IF EXISTS fato_atletas_id;
ALTER TABLE fato_atletas_kits DROP COLUMN IF EXISTS fato_atletas_id;
ALTER TABLE fato_atletas_custos DROP COLUMN IF EXISTS fato_atletas_id;

-- Step 7: Add foreign key constraints (if not exist)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.table_constraints WHERE constraint_name = 'fk_metricas_projeto') THEN
        ALTER TABLE fato_atletas_metricas ADD CONSTRAINT fk_metricas_projeto FOREIGN KEY (projeto_id) REFERENCES dim_projeto(id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.table_constraints WHERE constraint_name = 'fk_canais_projeto') THEN
        ALTER TABLE fato_atletas_canais ADD CONSTRAINT fk_canais_projeto FOREIGN KEY (projeto_id) REFERENCES dim_projeto(id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.table_constraints WHERE constraint_name = 'fk_kits_projeto') THEN
        ALTER TABLE fato_atletas_kits ADD CONSTRAINT fk_kits_projeto FOREIGN KEY (projeto_id) REFERENCES dim_projeto(id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.table_constraints WHERE constraint_name = 'fk_custos_projeto') THEN
        ALTER TABLE fato_atletas_custos ADD CONSTRAINT fk_custos_projeto FOREIGN KEY (projeto_id) REFERENCES dim_projeto(id);
    END IF;
EXCEPTION WHEN OTHERS THEN
    NULL;
END $$;

-- Step 8: Drop old unique constraints and create new ones
ALTER TABLE fato_atletas_metricas DROP CONSTRAINT IF EXISTS uq_atletas_metricas;
ALTER TABLE fato_atletas_canais DROP CONSTRAINT IF EXISTS uq_atletas_canais;
ALTER TABLE fato_atletas_kits DROP CONSTRAINT IF EXISTS uq_atletas_kits;
ALTER TABLE fato_atletas_custos DROP CONSTRAINT IF EXISTS uq_atletas_custos;

-- Create new unique constraints (ignoring errors if they already exist with correct columns)
DO $$
BEGIN
    ALTER TABLE fato_atletas_metricas ADD CONSTRAINT uq_atletas_metricas 
        UNIQUE (projeto_id, categoria_atleta_id, tempo_id, cenario, versao_projecao);
EXCEPTION WHEN duplicate_table THEN
    NULL;
END $$;

DO $$
BEGIN
    ALTER TABLE fato_atletas_canais ADD CONSTRAINT uq_atletas_canais 
        UNIQUE (projeto_id, categoria_atleta_id, tempo_id, canal, cenario, versao_projecao);
EXCEPTION WHEN duplicate_table THEN
    NULL;
END $$;

DO $$
BEGIN
    ALTER TABLE fato_atletas_kits ADD CONSTRAINT uq_atletas_kits 
        UNIQUE (projeto_id, categoria_atleta_id, tempo_id, tipo_kit, cenario, versao_projecao);
EXCEPTION WHEN duplicate_table THEN
    NULL;
END $$;

DO $$
BEGIN
    ALTER TABLE fato_atletas_custos ADD CONSTRAINT uq_atletas_custos 
        UNIQUE (projeto_id, categoria_atleta_id, tempo_id, tipo_custo, cenario, versao_projecao);
EXCEPTION WHEN duplicate_table THEN
    NULL;
END $$;

-- Step 9: Drop fato_atletas table
DROP TABLE IF EXISTS fato_atletas CASCADE;

COMMIT;
