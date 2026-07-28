---
name: Scripts standalone contra engine_ssh/engine_magento
description: Como rodar scripts avulsos (fora do ciclo de vida do FastAPI) que precisam do túnel SSH Ativo e/ou MySQL Magento, e o risco de deadlock contra o backend ao vivo.
---

# Scripts standalone precisam inicializar os engines manualmente

`engine_ssh` (túnel SSH → MySQL Ativo) e `engine_magento` só são criados no
startup real do FastAPI (`main.py`). Um script Python avulso que importa
`app.core.database` diretamente (ex. para testar uma query ou rodar
`rebuild_kit_snapshot` fora do endpoint) encontra os dois como `None`.

**Fix:** chamar `ensure_ssh_engine_ready()` e `ensure_magento_engine_ready()`
(ambos em `app/core/database.py`) antes de qualquer uso — cada um
(re)cria o engine sob demanda de forma idempotente, best-effort.

**Cuidado com operações de escrita (ex. `rebuild_kit_snapshot`):** rodar isso
num processo Python separado ENQUANTO o workflow real do backend está no ar
pode colidir em deadlock do Postgres (duas transações concorrentes, ordens de
lock diferentes, ex. `kit_config` vs `kit_mapping_snapshot`) — não é bug do
código, é contenção real de duas conexões independentes. É transitório:
retry costuma passar. Prefira, quando possível, disparar a operação através
do próprio endpoint HTTP do backend ao vivo (um único processo, como um admin
real faria) em vez de duplicar a chamada num script externo.
