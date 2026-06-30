---
name: Magento concurrency limit
description: Por que o tunnel SSH Magento exige serialização (concorrência=1) e como o limite é aplicado.
---

# Limite de concorrência Magento

**Regra:** Magento via SSH tunnel não aguenta paralelo SOB CARGA DE USUÁRIO. Limite só vale pra profile `request` (cliques de dia); profile `background` (scheduler 02h, warmup) roda livre.

**Why:** Observado em produção (24-26/05/2026): quando o usuário (ou frontend em loop) dispara `force_magento_refresh=true` para 5+ grupos diferentes em sequência, cada grupo fan-out 3-7 queries pesadas (`get_margem_por_kit` count+revenue, `fetch_real_daily_sales`, cpev1 prefetch). Tunnel SSH satura, queries dão timeout em cascata, circuit breaker abre, requests viram 429/500. O job noturno (background) NÃO causa esse problema porque é a única carga; serializar ele desnecessariamente atrasaria a janela de manutenção.

**Reincidência (30/06/2026):** o default foi subido de novo para 3 (commit "Increase Magento request concurrency from 1 to 3") e REPRODUZIU o incidente em produção: erro MySQL `3024` (max statement execution time exceeded), `429 Too Many Requests` e filas de 25-32s. Revertido para 1. **Não suba esse default — 3 já falhou duas vezes.** Se precisar de mais vazão, otimize a query, não a concorrência.

**Profile `once` também é serializado:** a query `today-sales-grouped` (vendas de "hoje" do ISC) e o "Atualizar Hoje" usam `profile="once"`. Antes do fix de 30/06/2026 o `once` NÃO passava pelo semáforo (`_use_sem = profile == "request"`), então rodava sem throttle e competia com as queries `request` + jobs, saturando o túnel e sendo morta por timeout — o que zerava o Magento de hoje e deixava só a parte do Ativo (sintoma: "16 vendas hoje" quando eram ~100). Agora `_use_sem = profile in ("request", "once")`. Tradeoff aceito: "Atualizar Hoje" pode esperar na fila (até `MAGENTO_ACQUIRE_TIMEOUT_S`) em vez de falhar rápido — preferível a dado parcial.

**How to apply:**
- Todo acesso a Magento DEVE passar por `magento_run` em `backend/app/core/db_retry.py` — é onde o semáforo (`_magento_concurrency_sem`) está. Bypassar com `engine_magento.connect()` direto fura o limite.
- Usar `profile="request"` para qualquer caminho disparado por click/HTTP de usuário (default) e `profile="once"` para paths interativos single-attempt (ambos agora gated pelo semáforo). Usar `profile="background"` SÓ para scheduler/warmup/jobs noturnos (roda livre).
- Não chamar `magento_run` dentro de `work_fn` passado pra outro `magento_run` em profile gated (deadlock — semáforo size=1 com mesma thread esperaria a si própria).
- Envs: `MAGENTO_MAX_CONCURRENCY` (default 1) controla os profiles request E once. `MAGENTO_ACQUIRE_TIMEOUT_S` (default 180s) é o tempo máximo na fila antes de cair pra snapshot piso — generoso de propósito para preferir esperar a derrubar pra snapshot.
- Cooldown `force_magento_refresh` por (grupo, ano) — `_force_refresh_last_ts` + `_FORCE_REFRESH_COOLDOWN_SECONDS=300s` — é complementar (cobre cliques repetidos no MESMO grupo), aplicado no endpoint `get_marketing_event_by_id` (early demote) E em `fetch_real_daily_sales_for_projetos` (cinto e suspensórios).
