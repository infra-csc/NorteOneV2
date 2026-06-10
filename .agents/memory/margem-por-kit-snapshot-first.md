---
name: Margem por Kit — leitura snapshot-first + janela de pedidos
description: Por que a margem lê sempre do snapshot e a janela de created_at é 15 meses (não 2 anos).
---

# Margem por Kit: leitura sempre via snapshot + janela de 15 meses

## Regra
- A query de **receita** da Margem por Kit (join `sales_order_item soi_child ON parent_item_id` + `LIKE/REGEXP` em `soi_child.name`) é o gargalo: estoura `MAX_EXECUTION_TIME(90000)` (erro MySQL 3024) em eventos de alto volume. `parent_item_id` não tem índice no Magento 2.
- O caminho de **leitura** (carregamento de tela/modal) deve **sempre** servir do snapshot Postgres `MargemBundleRevSnapshot`, qualquer idade. Isto é feito com `_snapshot_max_age_h = None` em `get_margem_por_kit`. A query pesada ao vivo só roda no batch noturno `sincronizar_margem_bundle_rev_batch`, em `force_refresh` (botão Reconsolidar) ou quando não há snapshot (bootstrap).
- A janela `so.created_at >= DATE_SUB(CURDATE(), INTERVAL N)` foi reduzida de `2 YEAR` para `15 MONTH` nas queries de margem (count + receita: live, fallback, supplementary) e no batch. **Receita e qtd devem usar a MESMA janela** senão `margem = receita - custo*qtd` fica distorcida.

## Por quê
- 2 anos varria pedidos demais; nenhum evento vende por 2 anos. 15 meses = 1 ano + 3 de folga para early-bird, cobrindo a edição atual com margem de segurança e cortando ~37% do scan — suficiente para o batch completar e manter o snapshot fresco.
- Eventos finalizados congelam 30 dias após a data e não são recomputados (snapshot preservado), então reduzir a janela não rebaixa contagens históricas já gravadas.

## Onde NÃO mexer
- `_populate_cenarios_from_bundles` (Cenários de Ciclismo) e o endpoint admin `diag_magento_bundle` mantêm `2 YEAR` de propósito.
- A correção definitiva da raiz seria um índice em `sales_order_item.parent_item_id` no Magento (banco de terceiros, sem DDL nosso).

## Cuidado operacional
- Como o snapshot stale é sempre aceito, o batch precisa rodar de fato em produção (`ENABLE_BACKGROUND_MAGENTO_SYNC=true`) e a cobertura do `margem_bundle_rev_snapshot` deve ser monitorada (startup já loga "cobertura baixa" quando < ~limite).
