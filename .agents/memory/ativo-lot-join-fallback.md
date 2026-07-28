---
name: Ativo lot-JOIN fallback (kit mapping)
description: ATIVO_KITS_QUERY lot resolution can silently drop the whole event/kit row; LEFT JOIN + COALESCE fallback fix, and why sa_modalidade_categoria_kit must stay INNER.
---

# Ativo lot-JOIN fallback no Mapeamento de Kits

`ATIVO_KITS_QUERY` (kit_config.py) resolve o "lote atual" de um evento via
subquery correlacionada (`dt_limite >= CURDATE() ORDER BY dt_limite ASC LIMIT 1`).
Quando isso não acha nada (evento sem lote futuro configurado — comum em
eventos cujo cadastro de lotes ainda não foi completado), o INNER JOIN em
`sa_evento_lote`/`sa_lotes` derrubava a linha inteira (evento/kit sumia da
tela, não só o preço).

**Fix (task #186):** `sa_evento_lote`/`sa_lotes` viraram LEFT JOIN, com a
subquery de lote embrulhada em `COALESCE(lote-atual, lote-mais-recente)`
(fallback = `ORDER BY dt_limite DESC LIMIT 1`, sem filtro de data).

**Why NÃO fazer o mesmo em `sa_modalidade_categoria_kit` (mck):** primeira
tentativa (LEFT JOIN em tudo, incluindo mck) recuperou mais linhas mas MySQL
começou a devolver `ds_categoria` inconsistente entre execuções para grupos
com nomes de categoria quase-duplicados (diferem só por maiúsc./espaço —
colação case-insensitive os agrupa juntos) — o optimizer escolhe
arbitrariamente qual linha do grupo representa o texto quando o JOIN que
definia a igualdade exata deixa de ser INNER. Mantendo mck como INNER JOIN
(só a JOIN de metadado do lote virou LEFT), o fix recupera as linhas visadas
(142 linhas / 39 eventos, testado contra dados reais) com ZERO linhas
perdidas e ZERO diffs de campo nas linhas pré-existentes.

**How to apply:** se tocar em `ATIVO_KITS_QUERY` de novo, NUNCA converta o
JOIN de `sa_modalidade_categoria_kit` (ou qualquer JOIN cuja igualdade defina
"qual categoria é essa") para LEFT/OUTER sem re-testar precisamente esse
cenário (grupos de nomes quase-duplicados sob colação case-insensitive).
Restam ~12 eventos futuros (jul/2026) ainda invisíveis por terem ZERO lotes
cadastrados (não é falha de JOIN, é ausência real de dado — fallback não tem
o que buscar); isso é gap separado, não coberto por este fix (proposto como
follow-up).
