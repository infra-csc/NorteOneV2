---
name: Margem partial refresh & consolidação de avisos
description: Force-refresh parcial não pode misturar contagem viva incompleta com receita de snapshot; avisos de margem colapsam em 1 mensagem
---
- Quando um force-refresh do Magento volta PARCIAL (soma de qtd da tabela de kits < piso de inscritos do snapshot), NÃO retornar as linhas parciais: elas misturam contagem ao vivo incompleta com receita de snapshot e SUBESTIMAM a Margem Realizada (o card mantém o piso, a tabela não — incoerência). Restaurar a última `margemPorKit` íntegra do `EventoDetailSnapshot` (`payload.evento.margemPorKit`), somente se não-degradada e com qtd ≥ parcial. Existe nos DOIS caminhos: agrupado e standalone.
- `margemAvisos` é consolidado em NO MÁXIMO 1 mensagem imediatamente antes de construir o `MarketingEvent` (`_consolidate_margem_avisos`), depois do cálculo de `_live_read_verified_complete` (que exige lista vazia). Contrato do frontend por prefixo: `INFO:`=azul/badge Snapshot; `AVISO:`=âmbar/badge Sincronizando + botão "Atualizar dados"; sem prefixo=vermelho. Mensagens SEM prefixo são RESERVADAS aos 2 estados canônicos (leitura parcial / atualização em andamento) — novos avisos devem usar prefixo ou serão colapsados na mensagem genérica.

**Why:** usuário via Margem Realizada errada + até 3 banners contraditórios (âmbar + azul + vermelho) descrevendo o mesmo estado.

**How to apply:** ao adicionar novo produtor de aviso de margem, prefixe com `INFO:`/`AVISO:`; ao mexer nos ramos de alinhamento parcial, manter card e tabela em lockstep (piso preservado ⇒ tabela restaurada).
