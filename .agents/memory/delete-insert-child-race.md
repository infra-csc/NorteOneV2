---
name: Delete+insert child rows race
description: Por que DELETE+INSERT de linhas filhas duplica dados sob concorrência e o padrão de fix
---
Regra: qualquer save que faz DELETE de linhas filhas e reinsere (ex.: kits de projeção) precisa de UNIQUE INDEX na chave natural (parent_id, nome).

**Why:** em READ COMMITTED, dois saves concorrentes não veem as linhas um do outro no DELETE (snapshot do statement) e ambos inserem o conjunto completo — duplicatas exatas no banco (caso real: projecao_inscritos_kit em prod).

**How to apply:** (1) migração startup com DELETE dedupe (manter maior id) ANTES do CREATE UNIQUE INDEX na mesma lista; (2) agregar o payload por nome antes do insert; (3) capturar IntegrityError no commit e devolver 409 "salvo por outra requisição" em vez de 500.
