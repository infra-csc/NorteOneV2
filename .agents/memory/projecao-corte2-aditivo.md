---
name: Projeção Corte 2 edição aditiva
description: Como funciona a edição aditiva no Corte 2 e por que a fase do corte precisa de fonte autoritativa no momento da edição.
---

# Edição aditiva no Corte 2 (Projeção de Inscritos)

No Corte 2, o modal de edição usa 3 colunas por nível (quantidade total, cada kit, cada cliente): Corte 1 (foto congelada só-leitura) | Corte 2 (input aditivo) | Total (= C1 + C2, ao vivo). O estado do form guarda o TOTAL ao vivo; o input C2 = total − C1, e onChange faz total = C1 + C2. Aditivo vale para os 3 níveis. A foto completa do Corte 1 fica em `projecao_corte_dist_snapshot` (capturada no congelamento do C1); eventos antigos sem snapshot caem em fallback aproximado com valores ao vivo.

**Por que a fase do corte precisa de fonte autoritativa no edit:** a aba padrão "Projeções" NÃO carrega o estado do consolidado, então não dá pra decidir "está em Corte 2?" a partir dele. A fase tem que vir de uma fonte por-evento buscada no momento de abrir o modal — o endpoint `/projecao/corte1-distribuicao` retorna `em_corte2` (derivado de `ProjecaoCorteSnapshot.valor_corte_2`/`congelado_corte_2_em`). `openEdit` sempre chama o load do corte; os campos e o Salvar ficam bloqueados enquanto carrega/erro.

**How to apply:** ao mexer no fluxo de edição da Projeção, NÃO confie no consolidado para saber a fase do corte — use a resposta do endpoint de distribuição. Em Corte 2 com baseline existente, os toggles "Distribuir por Kit/cliente" devem ficar travados ligados (não dá pra zerar a composição do C1) e o submit deve barrar se o baseline tem kits/clientes mas o toggle está off. Respostas assíncronas precisam de request-token + checagem de identidade (evento_id/area_projecao_id) pra evitar race de resposta velha.
