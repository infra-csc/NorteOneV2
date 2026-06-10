---
name: Curvas derivadas mascaradas de "Histórico Próprio"
description: Por que a consolidação grava curvas de fallback sob o nome do próprio evento e como o read path deve rotular pela coluna origem (não como histórico).
---

A consolidação noturna de curvas históricas pré-computa curvas de fallback
(média regional, similar de circuito, etc.) e as PERSISTE sob o nome do próprio
evento em `curva_historica_snapshot` com `ano_referencia = ano_anterior` e a
coluna `origem` indicando a real procedência (ex.: `regional`).

**Regra:** qualquer read path que rotula a curva (`_resolve_hist_pattern` e o
diagnóstico `_resolve_hist_pattern_readonly`) DEVE consultar a coluna `origem`
do snapshot do próprio evento ANTES de assumir `tipo_curva='historico'`. Se
`origem` for derivada (regional/circuito/circuito_similar/manual/derivado), o
rótulo correto é essa origem — não "Histórico Próprio". Caso contrário, eventos
sem histórico real de ano anterior (ex.: mapeados só no ano corrente) aparecem
mentirosamente como tendo curva própria do ano passado.

**Why:** a presença de um snapshot em `(evento, prev_ano)` NÃO prova que o evento
teve vendas no ano anterior — pode ser fallback materializado pelo job.

**fonte precisa:** a coluna `fonte_origem` guarda a origem exata (ex.: estado
`SP` para regional). Para `origem='regional'` a fonte é simplesmente o `estado`
do grupo (mesmo valor que a derivação ao vivo produz), então legados com
`fonte_origem IS NULL` podem ser backfillados com o estado sem recomputar o
padrão. Sem `fonte_origem` o consumidor cai num rótulo genérico ("Média
Regional").

**How to apply:** ao mexer em rotulagem/resolução de curva, manter live resolver
e diagnóstico em lockstep (ambos carregam origem+fonte_origem no índice de
snapshots). Override manual (`curva_override`) tem precedência e rotula `manual`.
`use_normalized=True` recomputa ao vivo e ignora o snapshot de propósito.
