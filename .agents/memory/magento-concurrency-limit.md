---
name: Magento concurrency limit
description: Por que o tunnel SSH Magento exige serialização (concorrência=1) e como o limite é aplicado.
---

# Limite de concorrência Magento

**Regra:** Magento via SSH tunnel não aguenta queries em paralelo. Default `MAGENTO_MAX_CONCURRENCY=1` (serializado).

**Why:** Observado em produção (24-26/05/2026): quando o usuário (ou frontend em loop) dispara `force_magento_refresh=true` para 5+ grupos diferentes em sequência, cada grupo fan-out 3-7 queries pesadas (`get_margem_por_kit` count+revenue, `fetch_real_daily_sales`, cpev1 prefetch). Tunnel SSH satura, queries começam a dar timeout em cascata, circuit breaker abre, requests viram 429/500. O cooldown por-grupo não resolve esse caso porque cada grupo é uma chave distinta.

**How to apply:**
- Todo acesso a Magento DEVE passar por `magento_run` em `backend/app/core/db_retry.py` — é onde o semáforo (`_magento_concurrency_sem`) está. Bypassar com `engine_magento.connect()` direto fura o limite.
- Não chamar `magento_run` dentro de `work_fn` passado pra outro `magento_run` (deadlock — semáforo size=1 com mesma thread esperaria a si própria).
- Se `MagentoEngineUnavailable` "Fila Magento cheia" aparecer frequente nos logs, considerar subir para 2 (env `MAGENTO_MAX_CONCURRENCY=2`).
- Timeout de acquire (`MAGENTO_ACQUIRE_TIMEOUT_S=25s` default): se a fila não anda em 25s, cai para snapshot piso — melhor que travar a request.
- Cooldown `force_magento_refresh` por (grupo, ano) — `_force_refresh_last_ts` + `_FORCE_REFRESH_COOLDOWN_SECONDS=300s` — é complementar (cobre cliques repetidos no MESMO grupo), aplicado no endpoint `get_marketing_event_by_id` (early demote) E em `fetch_real_daily_sales_for_projetos` (cinto e suspensórios).
