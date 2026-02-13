CREATE TABLE IF NOT EXISTS circuito_produto (
    id SERIAL PRIMARY KEY,
    nome VARCHAR(200) NOT NULL UNIQUE,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS localizacao (
    id SERIAL PRIMARY KEY,
    nome VARCHAR(200) NOT NULL UNIQUE,
    created_at TIMESTAMP DEFAULT NOW()
);

ALTER TABLE cadastro_evento ADD COLUMN IF NOT EXISTS circuito_produto VARCHAR(200);
ALTER TABLE cadastro_evento ADD COLUMN IF NOT EXISTS localizacao_evento VARCHAR(200);
ALTER TABLE cadastro_evento ADD COLUMN IF NOT EXISTS ano_evento INTEGER;

INSERT INTO circuito_produto (nome) VALUES
    ('Bravus Speed I'),
    ('Circuito das Estações - Outono'),
    ('Circuito do Sol'),
    ('Girl Power Run 11'),
    ('Longevidade'),
    ('Night Run I'),
    ('Triathlon Internacional de Santos'),
    ('Troféu Brasil de Triathlon - 1ª Etapa')
ON CONFLICT (nome) DO NOTHING;

INSERT INTO localizacao (nome) VALUES
    ('São Paulo'),
    ('Belo Horizonte'),
    ('Porto Alegre'),
    ('Recife'),
    ('Rio de Janeiro'),
    ('Santos')
ON CONFLICT (nome) DO NOTHING;
