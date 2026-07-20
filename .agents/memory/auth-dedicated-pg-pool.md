---
name: Auth dedicated PG pool
description: Login/sessão usam pool PG dedicado e sessão curta; usuário retorna detached
---

Autenticação (login, SSO callback, logout, get_current_user) usa um engine PG DEDICADO (`engine_auth`, pool pequeno, env: DB_AUTH_POOL_SIZE/DB_AUTH_MAX_OVERFLOW/DB_AUTH_POOL_TIMEOUT) separado do pool principal.

**Why:** Em produção, tempestades de sync Magento/Ativo + túnel MySQL caído esgotaram o QueuePool principal (25/50) e `/api/auth/me` passou a dar 500 — ninguém conseguia logar exatamente durante o incidente.

**How to apply:**
- `get_current_user` abre e fecha a sessão de auth DENTRO da função (não via Depends) — a conexão volta ao pool imediatamente; não usar Depends(get_db) ali, senão a conexão fica presa a requisição inteira.
- O `current_user` retornado é DETACHED (expunge, sessionmaker com expire_on_commit=False), com perfil_acesso_rel + permissoes + permissoes_campo eager-carregados. Qualquer NOVO acesso lazy a relação de current_user vai quebrar — eager-load lá também.
- Endpoints que GRAVAM no usuário devem recarregar na própria sessão: `user = db.get(Usuario, current_user.id)` e mutar `user` (nunca `current_user`).
- Orçamento de conexões: pool principal 25/50 + auth 5/5 = 85/processo; PG prod max_connections=112 — cuidado com sobreposição de deploy (ajustável por env sem redeploy).
