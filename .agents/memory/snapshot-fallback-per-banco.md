---
name: Fallback por banco em leitura ao vivo (Ativo/Magento)
description: Convenção para endpoints que combinam fetch ao vivo de Ativo+Magento — o que fazer quando só um banco falha, e onde essa proteção ainda falta ou já existe.
---

Quando um endpoint de leitura combina fetch AO VIVO de dois bancos independentes
(Ativo + Magento) e só UM falha, a contribuição desse banco deve ser preenchida
com o último snapshot salvo daquele banco/edição — nunca tratada como zero.
Isso evita tanto subestimar o total exibido quanto (mais grave) deixar esse
resultado parcial sobrescrever um snapshot bom já persistido.

**Padrão de referência:** `detalhe_eventos_service.get_detalhe` (Painel do
Evento) — `_fallback_rows_from_snapshot()` busca as linhas de UM banco no
snapshot mais recente independente da idade; o guard de save vira "pula só se
o banco SEM fallback disponível falhou" em vez de "pula se qualquer banco
falhou"; o snapshot persistido nunca guarda os campos `erros`/`fallback_bancos`
transitórios (só a resposta ao vivo os carrega), para não deixar um alarme já
resolvido grudado no registro.

**Por quê:** bug real em produção — Magento com fila cheia fazia o Painel do
Evento mostrar só a metade do total (só Ativo), e esse parcial podia
sobrescrever um snapshot completo salvo na noite anterior.

**Onde ainda falta (auditoria feita ao corrigir o Painel do Evento):**
`get_curva_comparativa` em `app/api/routes/marketing.py` soma `dados_ativo +
dados_magento` mensal para o gráfico de curva comparativa; cada fetch
(`_fetch_monthly_sales_ativo`/`_fetch_monthly_sales_magento`) engole exceção e
devolve `[]`, sem fallback de snapshot — mesmo ponto cego, ainda não
corrigido (proposto como follow-up task).

**Onde já está protegido (não confundir/duplicar esforço):**
`get_margem_por_kit` (ver margem-por-kit-snapshot-first.md e
margem-parcial-avisos.md) já serve snapshot-first com backfill próprio;
`fetch_isc_pricing_data`/ISC já é snapshot-only no read path (sem fetch ao
vivo dual-banco); `sincronizar_hoje_batch` (batch noturno, não leitura ao
vivo) já usa GREATEST() para o mesmo objetivo.
