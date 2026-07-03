---
name: Foto do Corte 1 incompleta cria loop de ajuste incorrigível pela UI
description: Quando a foto por área diverge do valor_corte_1, o card mostra convicta reconciliada mas o modal aditivo usa a foto bruta — o ajuste "errado" volta a cada save.
---

# Foto do Corte 1 inconsistente → ajuste fantasma que a UI não consegue zerar

**Sintoma:** uma área (tipicamente a maior, ex. "Site") mostra Ajuste positivo no card da
Projeção de Inscritos, mas o total do evento mostra Ajuste 0. O usuário tenta zerar pelo
modal e o valor volta.

**Mecânica do loop (dois consumidores, duas verdades):**
- O card (`/consolidado`) reconcilia a soma das convictas por área ao `valor_corte_1`
  (fonte canônica), tirando o delta da MAIOR área → exibe convicta reconciliada.
- O modal aditivo do Corte 2 (`/corte1-distribuicao`) usa a foto BRUTA
  (`projecao_corte_dist_snapshot`) como baseline.
- Se a foto está inconsistente (ex.: congelamento pegou o usuário no meio da digitação e
  só capturou 1 área, com o valor total do evento), o baseline do modal ≠ convicta do card.
  Salvar "ajuste 0" no modal grava `baseline_bruto + 0` ao vivo → o card volta a mostrar
  `ao_vivo − convicta_reconciliada` como ajuste fantasma. Incorrigível pela tela.

**Diagnóstico (prod, read-only):** comparar `projecao_inscritos` (ao vivo, deleted_at IS NULL),
`projecao_corte_snapshot.valor_corte_1` e `projecao_corte_dist_snapshot` por área. Se a soma
das fotos (+ áreas sem foto no ao vivo) ≠ valor_corte_1, é este caso.

**Correção (100% pela UI, admin, sem tocar no banco):**
1. **Reabrir** o Corte 1 (Convicta) — limpa valor_corte_1/congelado_em, volta ao layout de
   edição direta e o flag `reaberto_manual_corte_1` suprime o re-congelamento automático.
2. Editar a área contaminada para o valor correto (total − demais áreas).
3. **Congelar agora** (Corte 1) — `recongelar_corte` regrava `valor_corte_1 = soma ao vivo` e
   recaptura a foto COMPLETA (`capturar_dist_snapshot_corte1` SEM only_missing) + kit snapshot
   em lockstep. Isso conserta a foto bruta errada, coisa que o self-heal `only_missing` nunca faz.
4. Recongelar o Corte 2 se quiser fixar o Ajuste.

**Why:** o self-heal do `/corte1-distribuicao` é deliberadamente `only_missing` (nunca regrava
fotos existentes), então uma foto ERRADA persiste para sempre; só o recongelamento manual
substitui a foto. A reconciliação do consolidado é só de leitura — nunca é persistida.

**How to apply:** ao ver "ajuste fantasma numa área só", não caçar bug novo no save — verificar
consistência foto × valor_corte_1 primeiro. Caso clássico: eventos congelados no meio da
digitação antes da carência (grace) existir.
