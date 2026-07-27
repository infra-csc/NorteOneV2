---
name: Split de módulo de permissão por tela
description: Como criar módulo de permissão dedicado para uma tela existente sem quebrar acesso; invariantes do perfil_permissao.
---

# Split de módulo de permissão (perfil de acesso por tela)

Regra ao dar módulo próprio a uma tela que antes pegava carona em outro módulo:

1. Adicionar a key em `MODULOS_SISTEMA` (backend/app/schemas/perfil_acesso.py). Prefixo importa: `marketing_`/`admin_` controla o agrupamento na UI de Perfis de Acesso.
2. Gatear frontend (rota em App.tsx + item de nav em Layout.tsx) E backend (router `dependencies=[Depends(require_permission(...))]`) com a key nova.
3. Backfill one-shot em `_run_column_migrations()` copiando as flags do módulo "pai" para os perfis existentes (status quo preservado; admins revogam depois).

**Invariante crítico:** a UI de Perfis de Acesso revoga módulos DELETANDO a linha — o submit filtra permissões all-false e o update é DELETE+INSERT. Logo o guard do backfill deve ser GLOBAL one-shot (`NOT EXISTS` qualquer linha do módulo novo), NUNCA anti-join por perfil — anti-join re-concederia revogações a cada restart.

**Why:** descoberto ao criar `marketing_detalhe` (Painel do evento, Jul/2026); review sugeriu anti-join por perfil, que seria bug neste codebase.

**How to apply:** qualquer novo módulo de permissão para tela existente. `perfil_permissao` tem unique index `(perfil_acesso_id, modulo)` desde Jul/2026 (dedupe + índice na migration list). Backfill roda em prod no primeiro deploy (startup).
