"""
Diagnóstico Outono - Salvador 2026:
Conta separado Ativo vs Magento para identificar os 10 inscritos extras.
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from sqlalchemy import text

from app.core.database import init_mysql_connections, init_ssh_tunnel
import app.core.database as db_module

print("Inicializando conexões SSH + MySQL...")
try:
    init_ssh_tunnel()
    import time; time.sleep(3)
except Exception as e:
    print(f"  SSH: {e}")
try:
    init_mysql_connections()
    import time; time.sleep(2)
except Exception as e:
    print(f"  MySQL: {e}")

# IDs do evento "Circuito das Estações - Outono - Salvador" 2026
ATIVO_ID      = 39990   # sa_evento.id_evento
MAGENTO_EV_ID = '48152' # valor em catalog_product_entity_varchar.attribute_id=321

# ── ATIVO ──────────────────────────────────────────────────────────────────
print("\n" + "="*60)
print("CANAL ATIVO  (id_evento=39990)")
print("="*60)

Q_ATIVO_BREAKDOWN = text("""
SELECT
    CASE
        WHEN a.nr_preco = 0                 THEN 'Cortesia'
        WHEN h.ds_categoria LIKE '%%Grup%%' THEN 'Grupos/B2B'
        ELSE 'Site'
    END AS canal,
    COUNT(DISTINCT a.id_pedido_evento) AS qtd
FROM sa_pedido_evento AS a
INNER JOIN sa_evento AS b ON b.id_evento = a.id_evento
INNER JOIN sa_pedido AS c
    ON c.id_pedido = a.id_pedido
   AND c.fl_local_inscricao = '1'
   AND c.id_pedido_status IN (1, 2)
LEFT JOIN sa_modalidade_categoria AS h ON h.id_categoria = a.id_categoria
WHERE b.id_evento = :id_evento
  AND (b.id_campanha_salesforce IS NULL OR b.id_campanha_salesforce NOT LIKE '701d0000000%%')
  AND c.dt_pedido < CURDATE() + INTERVAL 1 DAY
GROUP BY 1
ORDER BY 1
""")

Q_ATIVO_MENSAL = text("""
SELECT
    DATE_FORMAT(c.dt_pedido, '%Y-%m') AS mes,
    COUNT(DISTINCT a.id_pedido_evento) AS qtd
FROM sa_pedido_evento AS a
INNER JOIN sa_evento AS b ON b.id_evento = a.id_evento
INNER JOIN sa_pedido AS c
    ON c.id_pedido = a.id_pedido
   AND c.fl_local_inscricao = '1'
   AND c.id_pedido_status IN (1, 2)
LEFT JOIN sa_modalidade_categoria AS h ON h.id_categoria = a.id_categoria
WHERE b.id_evento = :id_evento
  AND (b.id_campanha_salesforce IS NULL OR b.id_campanha_salesforce NOT LIKE '701d0000000%%')
  AND c.dt_pedido < CURDATE() + INTERVAL 1 DAY
  AND a.nr_preco > 0
  AND (h.ds_categoria IS NULL OR h.ds_categoria NOT LIKE '%%Grup%%')
GROUP BY 1
ORDER BY 1
""")

ativo_site = 0
if db_module.engine_ssh:
    with db_module.engine_ssh.connect() as conn:
        rows = conn.execute(Q_ATIVO_BREAKDOWN, {"id_evento": ATIVO_ID}).fetchall()
        for r in rows:
            print(f"  {r[0]:<15}: {r[1]}")
            if r[0] == 'Site':
                ativo_site = r[1]
        print("\n  Site por mês:")
        for r in conn.execute(Q_ATIVO_MENSAL, {"id_evento": ATIVO_ID}).fetchall():
            print(f"    {r[0]}: {r[1]}")
else:
    print("  !! engine_ssh não disponível")

# ── MAGENTO ────────────────────────────────────────────────────────────────
print("\n" + "="*60)
print(f"CANAL MAGENTO  (magento_event_id cpev1.value='{MAGENTO_EV_ID}')")
print("="*60)

Q_MAGENTO_BREAKDOWN = text("""
SELECT
    COUNT(CASE WHEN (soi.sku IS NULL OR soi.sku NOT LIKE '%%CORTESIA%%')
                    AND so.base_grand_total > 0
                    AND NOT (so.discount_description LIKE '%%CORTESIA%%' AND so.base_grand_total < 50)
                    AND (so.discount_description IS NULL OR so.discount_description NOT LIKE '%%Grup%%')
                    AND (so.coupon_code IS NULL OR so.coupon_code NOT LIKE 'GR%%')
                    AND soi.price > 0 THEN 1 END) AS site,
    COUNT(CASE WHEN (so.discount_description LIKE '%%Grup%%' OR so.coupon_code LIKE 'GR%%') THEN 1 END) AS grupos,
    COUNT(CASE WHEN so.base_grand_total = 0 OR (so.discount_description LIKE '%%CORTESIA%%' AND so.base_grand_total < 50) THEN 1 END) AS cortesia,
    COUNT(CASE WHEN so.status = 'reembolso_parcial' THEN 1 END) AS reembolso_parcial,
    COUNT(*) AS total_bruto
FROM sales_order so
INNER JOIN sales_order_item soi
       ON soi.order_id = so.entity_id
      AND soi.product_type = 'bundle'
INNER JOIN catalog_product_entity_varchar cpev1
       ON cpev1.entity_id = soi.product_id
      AND cpev1.attribute_id = 321
      AND cpev1.store_id = 0
WHERE so.status IN ('processing', 'complete', 'approved', 'aprovado_link', 'reembolso_parcial')
  AND so.state != 'canceled'
  AND cpev1.value = :ev_id
  AND so.increment_id NOT REGEXP '-[0-9]'
  AND so.created_at < CURDATE() + INTERVAL 1 DAY
""")

Q_MAGENTO_MENSAL = text("""
SELECT
    DATE_FORMAT(so.created_at, '%Y-%m') AS mes,
    COUNT(CASE WHEN (soi.sku IS NULL OR soi.sku NOT LIKE '%%CORTESIA%%')
                    AND so.base_grand_total > 0
                    AND NOT (so.discount_description LIKE '%%CORTESIA%%' AND so.base_grand_total < 50)
                    AND (so.discount_description IS NULL OR so.discount_description NOT LIKE '%%Grup%%')
                    AND (so.coupon_code IS NULL OR so.coupon_code NOT LIKE 'GR%%')
                    AND soi.price > 0 THEN 1 END) AS site_qtd
FROM sales_order so
INNER JOIN sales_order_item soi
       ON soi.order_id = so.entity_id
      AND soi.product_type = 'bundle'
INNER JOIN catalog_product_entity_varchar cpev1
       ON cpev1.entity_id = soi.product_id
      AND cpev1.attribute_id = 321
      AND cpev1.store_id = 0
WHERE so.status IN ('processing', 'complete', 'approved', 'aprovado_link', 'reembolso_parcial')
  AND so.state != 'canceled'
  AND cpev1.value = :ev_id
  AND so.increment_id NOT REGEXP '-[0-9]'
  AND so.created_at < CURDATE() + INTERVAL 1 DAY
GROUP BY 1
ORDER BY 1
""")

magento_site = 0
if db_module.engine_magento:
    with db_module.engine_magento.connect() as conn:
        row = conn.execute(Q_MAGENTO_BREAKDOWN, {"ev_id": MAGENTO_EV_ID}).fetchone()
        if row:
            print(f"  Site:             {row[0]}")
            print(f"  Grupos:           {row[1]}")
            print(f"  Cortesia:         {row[2]}")
            print(f"  Reembolso parcial:{row[3]}")
            print(f"  Total bruto:      {row[4]}")
            magento_site = row[0] or 0
        else:
            print("  (sem dados)")
        print("\n  Site por mês:")
        for r in conn.execute(Q_MAGENTO_MENSAL, {"ev_id": MAGENTO_EV_ID}).fetchall():
            print(f"    {r[0]}: {r[1]}")
else:
    print("  !! engine_magento não disponível")

# ── RESUMO ─────────────────────────────────────────────────────────────────
print("\n" + "="*60)
print("RESUMO FINAL")
print("="*60)
total_bruto = ativo_site + magento_site
print(f"  Ativo  Site:   {ativo_site}")
print(f"  Magento Site:  {magento_site}")
print(f"  ─────────────────────")
print(f"  Soma bruta:    {total_bruto}")
print(f"  Dashboard ISC: 2532")
print(f"  Controle ext.: 2522")
print(f"  Diferença:     {total_bruto - 2522} vs controle / {total_bruto - 2532} vs dashboard")
if total_bruto > 2532:
    print(f"\n  ⚠ SOMA BRUTA ({total_bruto}) > 2532 → POSSÍVEL DUPLA CONTAGEM de {total_bruto - 2532}")
elif total_bruto == 2532:
    print("\n  ✓ Sem dupla contagem entre canais. Diferença tem outra causa.")
else:
    print(f"\n  Soma bruta ({total_bruto}) < 2532 — checar query.")
