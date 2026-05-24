import sys, json, time, os, logging
sys.path.insert(0, '.')
logging.disable(logging.WARNING)
from datetime import date
from sqlalchemy import text
from app.core.database import SessionLocal, init_ssh_tunnel
from app.services.snapshot_service import consolidar_vendas_grupo

GRUPOS_FILE = '/tmp/grupos_backfill_23.json'
ZERO_FILE = '/tmp/grupos_zero_23.json'
BUDGET = int(os.getenv('BUDGET', '95'))

with open(GRUPOS_FILE) as f:
    grupos = json.load(f)
try:
    with open(ZERO_FILE) as f:
        ja_zero = set(json.load(f))
except Exception:
    ja_zero = set()

init_ssh_tunnel()
db = SessionLocal()
existing = {r[0] for r in db.execute(text("SELECT DISTINCT evento_grupo FROM vendas_diaria_snapshot WHERE data_venda='2026-05-23'"))}
faltam = [g for g in grupos if g not in existing and g not in ja_zero]

ok = zero = falha = 0
t0 = time.time()
done = 0
for grupo in faltam:
    if time.time() - t0 > BUDGET:
        break
    try:
        n = consolidar_vendas_grupo(db, grupo, 2026,
            data_inicio=date(2026, 5, 23), data_fim=date(2026, 5, 23),
            incremental=False, parent_job_name='backfill_23_manual_25mai')
        if n > 0:
            ok += 1
        else:
            zero += 1
            ja_zero.add(grupo)
            with open(ZERO_FILE, 'w') as f:
                json.dump(list(ja_zero), f)
    except Exception:
        falha += 1
    done += 1
db.close()
with open(ZERO_FILE, 'w') as f:
    json.dump(list(ja_zero), f)
print(f'Processados={done} COM_VENDA={ok} SEM_VENDA={zero} FALHA={falha} dur={time.time()-t0:.0f}s faltam_ainda={len(faltam)-done}', flush=True)
