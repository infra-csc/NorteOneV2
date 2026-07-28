"""Testes das correções: Ticket Atual (promo encerrada) + consolidação de avisos.

Roda contra o dev DB (semeado com espelho do prod para o evento 59367) e o
Magento real. Exercita o caminho AO VIVO e o caminho de FALLBACK (Magento
fora do ar, simulado por monkeypatch).
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal, init_mysql_connections
init_mysql_connections()

from app.api.routes import marketing as mkt
import app.api.routes.kit_config as kc

FAILS = []

def check(name, cond, extra=""):
    status = "OK " if cond else "FAIL"
    print(f"[{status}] {name} {extra}")
    if not cond:
        FAILS.append(name)

# ─── 1. _consolidate_margem_avisos ───────────────────────────────────────────
print("=" * 80)
print("1) _consolidate_margem_avisos")
tres_banners = [
    "AVISO: Conexão com Magento instável — buscando dados do snapshot mais recente.",
    "INFO: Receita atualizada até 9.6 h atrás — valores de inscrições e receita são confiáveis; vendas das últimas 9.6 h serão incluídas na próxima atualização.",
    "Leitura ao vivo veio incompleta — o total não foi corrigido para baixo. Tente atualizar novamente em alguns instantes.",
]
out = mkt._consolidate_margem_avisos(tres_banners)
check("3 banners → 1 AVISO", len(out) == 1 and out[0].startswith("AVISO:"), repr(out))
check("AVISO carrega idade", "9.6 h" in out[0], repr(out))

out2 = mkt._consolidate_margem_avisos([tres_banners[0], tres_banners[1]])
check("amber+info → 1 AVISO com idade", len(out2) == 1 and out2[0].startswith("AVISO:") and "9.6 h" in out2[0], repr(out2))

out3 = mkt._consolidate_margem_avisos([tres_banners[1]])
check("só INFO → mantém INFO", len(out3) == 1 and out3[0].startswith("INFO:"), repr(out3))

out4 = mkt._consolidate_margem_avisos(None)
check("None → []", out4 == [])

out5 = mkt._consolidate_margem_avisos([
    "Outra atualização está em andamento — o valor não foi corrigido agora. Tente novamente em instantes."
])
check("em andamento → AVISO único", len(out5) == 1 and out5[0].startswith("AVISO:") and "andamento" in out5[0], repr(out5))

# Comportamento documentado: sem-prefixo é RESERVADO aos estados canônicos;
# mensagem inédita sem prefixo colapsa no AVISO genérico (novos avisos devem
# usar prefixo INFO:/AVISO: — ver docstring de _consolidate_margem_avisos).
out6 = mkt._consolidate_margem_avisos(["Mensagem vermelha inédita sem prefixo."])
check("red inédita → AVISO canônico", len(out6) == 1 and out6[0].startswith("AVISO:"), repr(out6))

out7 = mkt._consolidate_margem_avisos([None, 123, "   ", tres_banners[1]])
check("não-str/vazios ignorados", len(out7) == 1 and out7[0].startswith("INFO:"), repr(out7))

# ─── 2. _resolve_ticket_for_event (lógica pura) ──────────────────────────────
print("=" * 80)
print("2) _resolve_ticket_for_event")

class Cfg:
    def __init__(self, bid, mult=1):
        self.bundle_entity_id = bid
        self.multiplicador = mult

promo_velha = Cfg(60341)   # R$ 50 OFF — encerrada
promo_nova = Cfg(60559)    # R$70 OFF — vigente
basico = Cfg(59392)

# Caso A: promo velha INATIVA nunca ganha, mesmo listada primeiro
bd_a = {
    60341: {"sp_base": 99.98, "status_kit": "inativo", "nome_kit": "Kit Promocional - R$ 50 OFF"},
    60559: {"sp_base": 129.99, "status_kit": "ativo", "nome_kit": "Kit Promocional - R$70 OFF"},
    59392: {"sp_base": 199.99, "status_kit": "ativo", "nome_kit": "Kit Estações"},
}
r = mkt._resolve_ticket_for_event(bd_a, basico, None, [promo_velha, promo_nova], require_status_active=True)
check("inativa não ganha (129.99)", r and r["value"] == 129.99, r)

# Caso B: status desconhecido em ambas → mais NOVA ganha (determinístico)
bd_b = {
    60341: {"sp_base": 99.98, "status_kit": None, "nome_kit": "R$ 50 OFF"},
    60559: {"sp_base": 129.88, "status_kit": None, "nome_kit": "R$70 OFF"},
}
r = mkt._resolve_ticket_for_event(bd_b, None, None, [promo_velha, promo_nova], require_status_active=True)
check("desconhecido: mais nova ganha", r and r["value"] == 129.88, r)
r_inv = mkt._resolve_ticket_for_event(bd_b, None, None, [promo_nova, promo_velha], require_status_active=True)
check("ordem de entrada irrelevante", r_inv and r_inv["value"] == 129.88, r_inv)

# Caso C: ativa confirmada vence desconhecida mais nova
bd_c = {
    60341: {"sp_base": 99.98, "status_kit": "ativo", "nome_kit": "R$ 50 OFF"},
    60559: {"sp_base": 129.88, "status_kit": None, "nome_kit": "R$70 OFF"},
}
r = mkt._resolve_ticket_for_event(bd_c, None, None, [promo_velha, promo_nova], require_status_active=True)
check("ativa confirmada > desconhecida", r and r["value"] == 99.98, r)

# Caso D: todas inativas → cai no básico
bd_d = {
    60341: {"sp_base": 99.98, "status_kit": "inativo", "nome_kit": "x"},
    60559: {"sp_base": 129.99, "status_kit": "inativo", "nome_kit": "y"},
    59392: {"sp_base": 199.99, "status_kit": "ativo", "nome_kit": "Kit Estações"},
}
r = mkt._resolve_ticket_for_event(bd_d, basico, None, [promo_velha, promo_nova], require_status_active=True)
check("todas inativas → básico 199.99", r and r["value"] == 199.99, r)

# Caso E: caminho Ativo (require_status_active=False) ignora status
r = mkt._resolve_ticket_for_event(bd_d, None, None, [promo_velha, promo_nova], require_status_active=False)
check("caminho Ativo ignora status (mais nova)", r and r["value"] == 129.99, r)

# ─── 3. _fetch_ticket_atual_map AO VIVO (Magento real) ───────────────────────
print("=" * 80)
print("3) _fetch_ticket_atual_map — Magento AO VIVO")
db = SessionLocal()
try:
    mapa = mkt._fetch_ticket_atual_map(db)
    entrada = mapa.get(124) or mapa.get("124")
    print("   projeto 124 →", entrada)
    val = (entrada or {}).get("value") if isinstance(entrada, dict) else entrada
    nome = (entrada or {}).get("nome_kit") if isinstance(entrada, dict) else None
    check("ticket ao vivo = 129.99", val == 129.99, f"val={val} nome={nome}")
    check("kit vigente R$70 OFF", nome and "70" in str(nome), f"nome={nome}")
finally:
    db.close()

# ─── 4. Fallback: Magento fora do ar (monkeypatch) ───────────────────────────
print("=" * 80)
print("4) _fetch_ticket_atual_map — Magento FORA (fallback KMS/snapshot)")

def _boom(label):
    raise RuntimeError("simulado: Magento fora do ar")

_orig = kc._fetch_magento_kits_cached
kc._fetch_magento_kits_cached = _boom
db2 = SessionLocal()
try:
    mapa2 = mkt._fetch_ticket_atual_map(db2)
    entrada2 = mapa2.get(124) or mapa2.get("124")
    print("   projeto 124 →", entrada2)
    val2 = (entrada2 or {}).get("value") if isinstance(entrada2, dict) else entrada2
    nome2 = (entrada2 or {}).get("nome_kit") if isinstance(entrada2, dict) else None
    check("fallback = 129.99 (kit_mapping_snapshot, NÃO 99.98)", val2 == 129.99, f"val={val2} nome={nome2}")
finally:
    kc._fetch_magento_kits_cached = _orig
    db2.close()

print("=" * 80)
if FAILS:
    print(f"RESULTADO: {len(FAILS)} FALHA(S): {FAILS}")
    sys.exit(1)
print("RESULTADO: TODOS OS TESTES PASSARAM")
