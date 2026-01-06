import os
from sqlalchemy import create_engine, text

# Pega a URL do banco da variável de ambiente
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    print("❌ Variável DATABASE_URL não encontrada!")
    exit(1)

print(f"🔗 Conectando ao banco...")

engine = create_engine(DATABASE_URL)

with engine.connect() as conn:
    # Verificar se a coluna já existe
    result = conn.execute(text("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = 'dim_projeto' AND column_name = 'imagem_kv'
    """))

    if result.fetchone():
        print("✅ Coluna 'imagem_kv' já existe!")
    else:
        print("📝 Criando coluna 'imagem_kv'...")
        conn.execute(text("ALTER TABLE dim_projeto ADD COLUMN imagem_kv VARCHAR(500) NULL;"))
        conn.commit()
        print("✅ Coluna 'imagem_kv' criada com sucesso!")

print("🎉 Migração concluída!")