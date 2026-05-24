import json
import sys
import time
from datetime import date
sys.path.insert(0, '.')
from app.core.database import SessionLocal, init_ssh_tunnel
from app.services.snapshot_service import consolidar_vendas_grupo
import logging
logging.basicConfig(level=logging.WARNING, format='%(asctime)s %(levelname)s %(message)s')

with open('/tmp/grupos_backfill_23.json') as f:
    grupos = json.load(f)

print(f'Iniciando SSH tunnel...', flush=True)
init_ssh_tunnel()
print(f'Backfill 2026-05-23 para {len(grupos)} grupos...', flush=True)
db = SessionLocal()
ano = 2026
data_dia = date(2026, 5, 23)
ok = 0
falha = 0
t0 = time.time()
falhas_lista = []
for i, grupo in enumerate(grupos, 1):
    try:
        n = consolidar_vendas_grupo(
            db, grupo, ano,
            data_inicio=data_dia, data_fim=data_dia,
            incremental=False, parent_job_name='backfill_23_manual_25mai'
        )
        ok += 1
    except Exception as e:
        falha += 1
        falhas_lista.append((grupo, str(e)[:120]))
    if i % 10 == 0 or i == len(grupos):
        print(
            f'  [{i:3}/{len(grupos)}] ok={ok} falha={falha} '
            f'elapsed={time.time()-t0:.0f}s last={grupo[:40]}',
            flush=True,
        )
db.close()
print(f'\n=== Resumo ===\nOK={ok}  FALHA={falha}  duração={time.time()-t0:.0f}s')
if falhas_lista:
    print('\n=== Falhas ===')
    for g, err in falhas_lista[:30]:
        print(f'  {g}: {err}')
