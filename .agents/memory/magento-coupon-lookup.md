---
name: Magento — buscar cupom no Magento
description: Como achar um cupom/regra de desconto no Magento quando o usuário só sabe o nome que aparece no carrinho.
---

# Cupom no Magento: nome interno ≠ etiqueta do carrinho

No Magento, uma sales rule tem DOIS textos distintos:

- `salesrule.name` — nome interno, só admin vê.
- `salesrule_label.label` (por `store_id`) — é o que **aparece pro cliente no carrinho e no pedido**.

Quando o time comercial te dá um "nome de cupom" tipo `Desconto_Funcionario_BB_50%`, esse é quase sempre o **label**, não o name. Procurar só por `salesrule.name LIKE '%...%'` retorna vazio e dá falso negativo. Exemplo real: o label `Desconto_Funcionario_BB_50%` correspondia à regra cujo `name` era `Desconto - Funcionários BB - Matricula` — nada parecido textualmente.

**Como aplicar:** Sempre buscar pelos DOIS campos (faça as duas queries, ou um JOIN com `salesrule_label`). Se a busca por `name` vier vazia, ainda não conclua que o cupom não existe — repita por `label` antes de responder.

Também útil saber: `salesrule.times_used` é o contador **histórico total** da regra, não filtrado por evento/período. Pra atribuir uso a um evento específico precisa cruzar com pedidos por SKU.

Tabelas relacionadas que costumam aparecer no diagnóstico: `salesrule`, `salesrule_coupon` (os códigos), `salesrule_label` (rótulo por store), `salesrule_website`, `salesrule_customer_group`.
