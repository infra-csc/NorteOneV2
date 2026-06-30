---
name: Magento concurrency limit
description: Por que o tunnel SSH Magento exige serialização (concorrência=1) e como o limite é aplicado.
---

# Limite de concorrência Magento

**Regra:** Magento via SSH tunnel não aguenta paralelo, ponto. TODOS os profiles (request, once, background) passam pelo MESMO slot único (`_magento_concurrency_sem`, concorrência=1). Interativo (request/once) tem PRIORIDADE: background cede a vez enquanto houver interativo na fila.

**Why:** Observado em produção (24-26/05/2026): quando o usuário (ou frontend em loop) dispara `force_magento_refresh=true` para 5+ grupos diferentes em sequência, cada grupo fan-out 3-7 queries pesadas (`get_margem_por_kit` count+revenue, `fetch_real_daily_sales`, cpev1 prefetch). Tunnel SSH satura, queries dão timeout em cascata, circuit breaker abre, requests viram 429/500. O job noturno (background) NÃO causa esse problema porque é a única carga; serializar ele desnecessariamente atrasaria a janela de manutenção.

**Reincidência (30/06/2026):** o default foi subido de novo para 3 (commit "Increase Magento request concurrency from 1 to 3") e REPRODUZIU o incidente em produção: erro MySQL `3024` (max statement execution time exceeded), `429 Too Many Requests` e filas de 25-32s. Revertido para 1. **Não suba esse default — 3 já falhou duas vezes.** Se precisar de mais vazão, otimize a query, não a concorrência.

**Profile `background` também é gated, com prioridade interativa (30/06/2026 — 2ª rodada do fix):** o 1º fix gateou só request+once, mas `background` continuava BYPASSANDO o semáforo. Como `background` é usado tanto pelo batch das 17h (`sincronizar_hoje_batch`) QUANTO por queries pesadas disparadas pelo dashboard (`kit_cost_batch` ~1500 bundles, curvas, fallbacks de margem), esses inundavam o túnel em paralelo, saturavam o servidor Magento e faziam o "Atualizar Hoje" interativo estourar mesmo com concorrência=1 (sintoma persistia: "16 vendas hoje" quando eram ~100; filas de 47-52s nos logs). Fix: TODOS os profiles passam pelo slot único; interativo (request/once) incrementa um contador `_interactive_waiting` antes de adquirir e background faz spin-wait (poll 0.25s) enquanto esse contador > 0, até o deadline de aquisição. Sem preempção de query em execução (não dá pra matar SQL no meio), então o pior caso de espera interativa é ~1 query de background em voo. À noite (sem interativo) o background não cede e roda serializado — sem perda de throughput porque o túnel não paraleliza mesmo.

**Timeout de aquisição por chamada:** `magento_run(..., acquire_timeout=...)` permite ao caller passar um teto curto alinhado ao seu próprio orçamento de thread. O "Atualizar Hoje" passa `acquire_timeout=_MAGENTO_TIMEOUT_S` (32s; subido de 14s pra cobrir 1 query de background em voo + a própria). **Why:** sem isso, uma query interativa "zumbi" (que o endpoint já abandonou em 32s) continuaria na fila até 180s, e por ser interativa SEGURARIA o background cedendo todo esse tempo. O teto curto bounda a vida do zumbi.

**How to apply:**
- Todo acesso a Magento DEVE passar por `magento_run` em `backend/app/core/db_retry.py` — é onde o semáforo (`_magento_concurrency_sem`) está. Bypassar com `engine_magento.connect()` direto fura o limite.
- Usar `profile="request"` para qualquer caminho disparado por click/HTTP de usuário (default) e `profile="once"` para paths interativos single-attempt (interativos = têm prioridade no slot). Usar `profile="background"` para scheduler/warmup/jobs noturnos E queries pesadas disparadas indiretamente pelo dashboard (kit_cost, curvas) — background é gated igual mas CEDE a vez aos interativos.
- Não chamar `magento_run` dentro de `work_fn` passado pra outro `magento_run` em profile gated (deadlock — semáforo size=1 com mesma thread esperaria a si própria).
- Envs: `MAGENTO_MAX_CONCURRENCY` (default 1) é o tamanho do slot único (todos os profiles). `MAGENTO_ACQUIRE_TIMEOUT_S` (default 180s) é o tempo máximo padrão na fila antes de cair pra snapshot piso — generoso de propósito; callers interativos podem passar `acquire_timeout` curto por chamada (ver acima).
- Cooldown `force_magento_refresh` por (grupo, ano) — `_force_refresh_last_ts` + `_FORCE_REFRESH_COOLDOWN_SECONDS=300s` — é complementar (cobre cliques repetidos no MESMO grupo), aplicado no endpoint `get_marketing_event_by_id` (early demote) E em `fetch_real_daily_sales_for_projetos` (cinto e suspensórios).
