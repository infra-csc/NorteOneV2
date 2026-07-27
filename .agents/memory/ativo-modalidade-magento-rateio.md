---
name: Modalidade Ativo + rateio de desconto de carrinho Magento
description: Fonte confiável de modalidade no Ativo (nm_modalidade via categoria) e fórmula de receita líquida Magento com rateio de desconto de carrinho
---

## Regra 1 — Modalidade no Ativo: `nm_modalidade` via categoria

Em `sa_evento_modalidade`, `ds_modalidade` fica **vazia** ('' não NULL) em grande parte dos eventos (~54% das modalidades de eventos 2026). O nome confiável é `nm_modalidade`, e o caminho canônico de join é pela **categoria** da inscrição:

```sql
LEFT JOIN sa_modalidade_categoria h ON h.id_categoria = a.id_categoria
LEFT JOIN sa_evento_modalidade  q ON q.id_modalidade = h.id_modalidade
```

`id_modalidade` é única → não precisa (nem deve) filtrar por `id_evento` nesse join.

**Why:** barras "—" (sem rótulo) no Detalhe de Eventos: todos os inscritos Ativo apareciam sem modalidade quando `ds_modalidade` estava vazia; join via `a.id_modalidade` da inscrição também diverge (~1 inscrito) do caminho por categoria usado pelo analista.

**How to apply:** qualquer query nova que rotule modalidade/distância vinda do Ativo deve usar `q.nm_modalidade` + join via categoria. Nunca reintroduzir `ds_modalidade` como rótulo.

## Regra 2 — Receita líquida Magento precisa ratear desconto de CARRINHO

`soi_child.price - soi_child.discount_amount` só remove desconto de **item**; cupons de carrinho (nível pedido) ficam de fora e superestimam a líquida. Fórmula canônica: subtrair também o resíduo de carrinho rateado por bundle do pedido:

```
resíduo = ABS(so.discount_amount) - SUM(discount_amount dos itens não-bundle do pedido)
líquida_por_bundle -= resíduo / qtd_bundles_do_pedido   (COALESCE(...,0) obrigatório)
```

Implementado via derivada `agg` (order_id → qtd_bundles, desc_itens) com pedidos-alvo **escopados por evento** (param) ou **ano corrente** (global) — nunca full scan em `sales_order_item` (5,4M linhas). Sem `COALESCE(...,0)`, pedido sem match em `agg` vira NULL e a linha sai do SUM.

**How to apply:** qualquer medida nova de receita líquida Magento por item/bundle deve incluir esse rateio (o Detalhe de Eventos usa a constante compartilhada `_RECEITA_LIQUIDA_SUM`). Atenção: o breakdown Magento do Painel do evento (vendas-kit-detalhe) ainda usa a fórmula antiga sem rateio.
