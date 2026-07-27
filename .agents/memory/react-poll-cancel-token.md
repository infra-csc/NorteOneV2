---
name: Cancelamento de polling React por generation token
description: Como cancelar loops de polling async quando o usuário troca de entidade (id de rota) — boolean compartilhado não funciona.
---

**Regra:** para cancelar um loop de polling quando o usuário troca de evento/rota, use um generation token (`useRef(0)`; cleanup do effect `[id]` faz `ref.current += 1`; cada run captura `const runToken = ++ref.current` e usa `isCancelled: () => ref.current !== runToken`). Depois de QUALQUER `await` no handler, recheque o token antes de escrever estado.

**Why:** um `useRef(false)` compartilhado é quebrado de duas formas: (1) o effect do novo id re-zera o boolean logo após o cleanup setá-lo, então a run antiga "des-cancela"; (2) o loop que só checa cancelamento antes do sleep pode retornar estado terminal capturado durante o sleep/request e o handler antigo aplica sucesso/erro/cooldown na tela do evento novo.

**How to apply:** checar `isCancelled` no início da iteração E imediatamente após o request retornar (antes de devolver estado terminal); no handler, `if (ref.current !== runToken) return;` após o await de polling, antes dos setState. Aplicado em EventDetail (handleReconsolidar/handleConsolidarEvento) + `aguardarRecalcularSnapshot`.
