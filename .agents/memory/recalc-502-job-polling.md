---
name: Reconsolidar 502 = job em thread + polling
description: Ações admin longas (pipeline Ativo+Magento) não podem rodar dentro do request HTTP; proxy corta com 502. Padrão adotado: thread + registro em memória + endpoint de status.
---

**Regra:** qualquer ação disparada por botão que rode o pipeline pesado (Ativo via SSH + Magento fila concorrência=1) deve executar em thread de background e responder `{status:'started'}` imediatamente; o front acompanha por polling de um endpoint de status.

**Why:** o proxy na frente do backend (dev e produção) corta requests longos — o cliente recebia "502 Request failed" mesmo com o backend concluindo o trabalho com sucesso. Esticar timeout do axios (180s→600s) NÃO resolve: o corte é do proxy, não do cliente.

**How to apply:**
- Padrão implementado na reconsolidação manual: `POST .../recalcular-snapshot` (marketing) e `POST /admin/snapshots/consolidar-evento` (admin) disparam thread daemon; registro de job em memória (`_recalc_jobs` em admin.py, ao lado do slot `_evento_inflight`, mesma premissa single-process); status em `GET /marketing/eventos/{key}/recalcular-snapshot/status` (key = evento_id com `grp_` no marketing, nome do grupo sem prefixo no admin).
- A thread abre sua própria `SessionLocal` (nunca a sessão do request), seta cooldown Diretoria só em sucesso e libera o slot global no `finally`. Falha ANTES do `Thread.start()` deve liberar o slot no request.
- Front: `marketingService.aguardarRecalcularSnapshot(key)` (4s intervalo, cap 20min, estados sintéticos cancelled/timeout/unreachable). Manter fallback para resposta síncrona legada (`status:'ok'`) por causa de bundle PWA velho em produção.
