"""Standalone smoke test for GET /marketing/eventos/{evento_id}/vendas-diarias-por-kit
(task #209 - kit filter on the ISC Dashboard "Vendas Diárias" chart).

Calls the route function directly (bypassing HTTP/auth) against the real dev
DB + live Magento/Ativo connections, mirroring the scripts/test_ticket_fix.py
pattern. Picks real evento_ids from SkuMapping/KitConfig instead of hardcoding
IDs that may not exist in this environment.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import date, timedelta

from app.core.database import SessionLocal, init_mysql_connections
init_mysql_connections()

from app.api.routes import marketing as mkt
from app.models.dimensoes import SkuMapping
from app.models.kit_config import KitConfig

FAILS = []


def check(name, cond, extra=""):
    status = "OK  " if cond else "FAIL"
    print(f"[{status}] {name} {extra}")
    if not cond:
        FAILS.append(name)


db = SessionLocal()
today = date.today()
data_fim = (today - timedelta(days=1)).isoformat()
data_inicio = (today - timedelta(days=30)).isoformat()

print("=" * 80)
print(f"Range de teste: {data_inicio} .. {data_fim}")

# ─── Find a real evento_grupo with MAGENTO mappings AND KitConfig rows ──────
kit_event_ids = {row[0] for row in db.query(KitConfig.id_evento).filter(
    KitConfig.tipo_kit.isnot(None), KitConfig.ignorado == False
).distinct().all()}
print(f"Eventos com KitConfig ativo: {len(kit_event_ids)}")

candidate_mapping = None
if kit_event_ids:
    candidate_mapping = db.query(SkuMapping).filter(
        SkuMapping.fonte == 'MAGENTO',
        SkuMapping.ativo == True,
        SkuMapping.id_externo.in_([str(i) for i in kit_event_ids]),
    ).order_by(SkuMapping.ano.desc()).first()

if not candidate_mapping:
    print("Nenhum evento com KitConfig + SkuMapping MAGENTO ativo encontrado — abortando.")
    sys.exit(1)

evento_id = f"grp_{candidate_mapping.evento_grupo}"
ano = candidate_mapping.ano
print(f"Evento escolhido: {evento_id!r} ano={ano} (sku={candidate_mapping.sku})")

# ─── 1. Caminho feliz: ano explícito ────────────────────────────────────────
result = mkt.get_vendas_diarias_por_kit(
    evento_id=evento_id, ano=ano, data_inicio=data_inicio, data_fim=data_fim,
    db=db, current_user=None,
)
check("retorna dict com kitTypes+dailySalesByKit", isinstance(result, dict) and 'kitTypes' in result and 'dailySalesByKit' in result, repr(result)[:300])
check("kitTypes é lista", isinstance(result.get('kitTypes'), list))
check("dailySalesByKit é dict", isinstance(result.get('dailySalesByKit'), dict))
total_qtd = sum(v for day in result['dailySalesByKit'].values() for v in day.values())
print(f"  kitTypes={result['kitTypes']}")
print(f"  dias com dados={len(result['dailySalesByKit'])}  total qtd somada={total_qtd}")
check("todas as datas dentro do range pedido", all(data_inicio <= d <= data_fim for d in result['dailySalesByKit'].keys()))
for dia, kits in result['dailySalesByKit'].items():
    for tipo, qtd in kits.items():
        if qtd < 0:
            check(f"qtd não-negativa ({dia}/{tipo})", False, f"qtd={qtd}")

# ─── 2. ano omitido → deve resolver via _resolve_evento_ano_efetivo (sem 500) ──
try:
    result_no_ano = mkt.get_vendas_diarias_por_kit(
        evento_id=evento_id, ano=None, data_inicio=data_inicio, data_fim=data_fim,
        db=db, current_user=None,
    )
    check("ano=None não lança exceção", True)
    check("ano=None retorna shape válido", isinstance(result_no_ano, dict) and 'kitTypes' in result_no_ano)
except Exception as e:
    check("ano=None não lança exceção", False, repr(e))

# ─── 3. Validação de datas: range > 31 dias deve 400 (HTTPException) ────────
from fastapi import HTTPException
try:
    mkt.get_vendas_diarias_por_kit(
        evento_id=evento_id, ano=ano, data_inicio="2026-01-01", data_fim="2026-03-01",
        db=db, current_user=None,
    )
    check("range > 31 dias rejeitado", False, "não levantou exceção")
except HTTPException as e:
    check("range > 31 dias rejeitado", e.status_code == 400, f"status={e.status_code}")

# ─── 4. data_fim < data_inicio deve 400 ─────────────────────────────────────
try:
    mkt.get_vendas_diarias_por_kit(
        evento_id=evento_id, ano=ano, data_inicio=data_fim, data_fim=data_inicio,
        db=db, current_user=None,
    )
    check("data_fim < data_inicio rejeitado", False, "não levantou exceção")
except HTTPException as e:
    check("data_fim < data_inicio rejeitado", e.status_code == 400, f"status={e.status_code}")

# ─── 5. Evento inexistente → retorno vazio, nunca 500 ───────────────────────
try:
    result_missing = mkt.get_vendas_diarias_por_kit(
        evento_id="grp_EventoQueNaoExisteXYZ123", ano=2026, data_inicio=data_inicio, data_fim=data_fim,
        db=db, current_user=None,
    )
    check("evento inexistente não lança exceção", True)
    check("evento inexistente retorna listas vazias", result_missing == {"kitTypes": [], "dailySalesByKit": {}}, repr(result_missing))
except Exception as e:
    check("evento inexistente não lança exceção", False, repr(e))

# ─── 6. Cache: segunda chamada idêntica deve bater o cache (mesmo resultado) ──
import time
t0 = time.time()
result_cached = mkt.get_vendas_diarias_por_kit(
    evento_id=evento_id, ano=ano, data_inicio=data_inicio, data_fim=data_fim,
    db=db, current_user=None,
)
elapsed = time.time() - t0
check("resultado do cache é idêntico", result_cached == result, f"elapsed={elapsed:.3f}s")

print("=" * 80)
if FAILS:
    print(f"{len(FAILS)} FALHA(S): {FAILS}")
    sys.exit(1)
else:
    print("Todos os testes passaram.")
