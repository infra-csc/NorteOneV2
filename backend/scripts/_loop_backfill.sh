#!/usr/bin/env bash
set -u
cd "$(dirname "$0")/.."
export DATABASE_URL="$PROD_DATABASE_URL"
export BUDGET=110
i=0
while true; do
  i=$((i+1))
  echo "=== iter $i $(date '+%H:%M:%S') ==="
  python -u scripts/_chunk_backfill.py 2>&1 | grep -E "^Processados|FAIL" | tail -3
  # Critério parada: arquivo de zero+snapshots cobre tudo
  faltam=$(python -c "
import os, json
from sqlalchemy import create_engine, text
eng = create_engine(os.environ['PROD_DATABASE_URL'])
with eng.connect() as conn:
    snap = {r[0] for r in conn.execute(text(\"SELECT DISTINCT evento_grupo FROM vendas_diaria_snapshot WHERE data_venda='2026-05-23'\"))}
try:
    with open('/tmp/grupos_zero_23.json') as f: zero=set(json.load(f))
except: zero=set()
with open('/tmp/grupos_backfill_23.json') as f: gs=json.load(f)
faltam=[g for g in gs if g not in snap and g not in zero]
print(len(faltam))
")
  echo "faltam=$faltam"
  if [ "$faltam" = "0" ]; then echo "FIM"; break; fi
  sleep 2
done
