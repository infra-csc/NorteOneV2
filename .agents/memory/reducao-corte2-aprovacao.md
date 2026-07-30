---
name: Aprovação de redução no Corte de Ajuste
description: Regra de negócio do gate de aprovação para reduções de projeção durante Corte 2 (Task #212) — quando dispara, quem aprova, e como fica obsoleto.
---

# Aprovação de redução no Corte de Ajuste (Corte 2)

Durante `em_corte2` (Corte 1 já congelado via `valor_corte_1`/
`congelado_corte_1_em`), qualquer edição que DIMINUA a `quantidade` TOTAL de
uma `ProjecaoInscritos` não aplica direto: `update_projecao` bloqueia com
409 `reducao_requer_aprovacao` (payload traz quantidade_atual/proposta) e o
front abre um modal para abrir um chamado (`ProjecaoReducaoSolicitacao`) em
vez de salvar. Aumentos e qualquer edição fora do Corte 2 (inclusive Corte 1)
não passam por esse gate — comportamento inalterado.

- Área aprovadora é **uma única configuração global**
  (`ProjecaoCorteConfig.area_aprovadora_reducao_id`), não por evento/área
  solicitante. Só admin configura; admins sempre podem decidir qualquer
  chamado (fallback), sem checagem de auto-aprovação.
- Um novo chamado pendente para o mesmo (evento, área) auto-cancela o
  anterior (status='cancelado', mensagem fixa) — índice único parcial em
  Postgres `WHERE status='pendente'` garante isso mesmo sob concorrência.
- Aprovar revalida DUAS coisas no momento da decisão: (1) o evento ainda
  está em corte de ajuste (senão auto-cancela o chamado com 409); (2) a
  `quantidade` atual da projeção ainda bate com o snapshot
  `quantidade_atual` do chamado (senão 409 `solicitacao_desatualizada` e o
  chamado FICA pendente — não há auto-cancelamento nesse caso específico;
  alguém precisa rejeitar manualmente ou o solicitante reenvia).
- Teto de "Camiseta avulsa" (ver `camiseta-avulsa-teto.md`) é revalidado
  tanto na criação do chamado quanto na aprovação — são checagens
  ortogonais/independentes uma da outra.

**Why:** dar a uma área de controle (ex.: financeiro) visibilidade e poder
de veto sobre reduções tardias de projeção, sem travar aumentos nem mexer
no Corte 1.

**How to apply:** qualquer mudança em `_em_corte2_ativo`, no cálculo de
`quantidade` total, ou no fluxo de save da Projeção precisa considerar se
ainda preserva esse gate (só reduções, só Corte 2, revalidação dupla no
aprovar).
