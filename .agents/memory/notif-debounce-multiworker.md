---
name: Debounce de notificação multi-worker
description: Padrão para debounce de e-mails que sobrevive a múltiplos workers/instâncias
---
Debounce de notificação em memória (dict + threading.Timer) só agrupa dentro de UM processo; com múltiplos workers, saves consecutivos geram e-mails duplicados.

**Padrão adotado (aviso de alteração de projeção):** estado persistido em tabela PG com chave única por agrupamento e coluna `flush_after`. Cada save faz UPSERT (preserva baseline da 1ª alteração da janela, atualiza estado final, empurra `flush_after`). Timers locais continuam existindo, mas o envio exige claim atômico `DELETE ... WHERE flush_after <= now RETURNING` — só um worker vence. Órfãs (worker morreu antes do timer) são varridas oportunisticamente a cada novo save, com folga sobre a janela.

**Why:** timers locais não coordenam entre processos; o RETURNING do DELETE é o único árbitro.

**How to apply:** qualquer notificação com debounce que possa rodar em deploy multi-worker. Atenção: timestamps devem ser todos BRT-naive (padrão do app) — misturar `NOW()` do PG (UTC) com `datetime.now(BRT)` quebra as comparações de janela.
