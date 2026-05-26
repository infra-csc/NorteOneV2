---
name: Magento concurrency limit
description: Por que o tunnel SSH Magento exige serialização (concorrência=1) e como o limite é aplicado.
---

# Limite de concorrência Magento

**Regra:** Magento via SSH tunnel não aguenta paralelo SOB CARGA DE USUÁRIO. Limite só vale pra profile `request` (cliques de dia); profile `background` (scheduler 02h, warmup) roda livre.

**Why:** Observado em produção (24-26/05/2026): quando o usuário (ou frontend em loop) dispara `force_magento_refresh=true` para 5+ grupos diferentes em sequência, cada grupo fan-out 3-7 queries pesadas (`get_margem_por_kit` count+revenue, `fetch_real_daily_sales`, cpev1 prefetch). Tunnel SSH satura, queries dão timeout em cascata, circuit breaker abre, requests viram 429/500. O job noturno (background) NÃO causa esse problema porque é a única carga; serializar ele desnecessariamente atrasaria a janela de manutenção.

**How to apply:**
- Todo acesso a Magento DEVE passar por `magento_run` em `backend/app/core/db_retry.py` — é onde o semáforo (`_magento_concurrency_sem`) está. Bypassar com `engine_magento.connect()` direto fura o limite.
- Usar `profile="request"` para qualquer caminho disparado por click/HTTP de usuário (default). Usar `profile="background"` SÓ para scheduler/warmup/jobs noturnos. O profile decide se o semáforo se aplica.
- Não chamar `magento_run` dentro de `work_fn` passado pra outro `magento_run` no mesmo profile request (deadlock — semáforo size=1 com mesma thread esperaria a si própria).
- Envs: `MAGENTO_MAX_CONCURRENCY` (default 1) controla SÓ o profile request. `MAGENTO_ACQUIRE_TIMEOUT_S` (default 180s) é o tempo máximo na fila antes de cair pra snapshot piso — generoso de propósito para preferir esperar a derrubar pra snapshot.
- Cooldown `force_magento_refresh` por (grupo, ano) — `_force_refresh_last_ts` + `_FORCE_REFRESH_COOLDOWN_SECONDS=300s` — é complementar (cobre cliques repetidos no MESMO grupo), aplicado no endpoint `get_marketing_event_by_id` (early demote) E em `fetch_real_daily_sales_for_projetos` (cinto e suspensórios).
