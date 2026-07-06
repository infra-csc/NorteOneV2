---
name: Consolidado total sempre ao vivo (nunca corte_valor_2)
description: Por que o totalizador da Visão Consolidada da Projeção deve mostrar o total ao vivo, e não o valor congelado do Corte 2.
---

# Totalizador da Visão Consolidada = total ao vivo, nunca o valor congelado do Corte 2

**Regra:** no card "Projeção Total" e na linha "Total" do rodapé da tabela por área
(Visão Consolidada da Projeção de Inscritos), o número grande exibido é SEMPRE o total
ao vivo (`total_projecoes`, soma das projeções atuais). A "Convicta" continua sendo o
Corte 1 congelado (`corte_valor_1`, base). O "Ajuste" = total ao vivo − Convicta.
NÃO usar `corte_valor_2` como o total exibido.

**Why (incidente):** Corte 1 (Convicta) e Corte 2 (Ajuste) podem congelar no MESMO
instante — quando a primeira leitura após a janela do Corte 2 (D-`dias_corte_2`) também
é a primeira que atinge o Corte 1. Nesse caso o Ajuste trava valendo 0 (sem janela de
ajuste). Um ajuste feito depois (ex.: +100 em uma área) fica só na projeção ao vivo; o
`corte_valor_2` congelado não muda. As linhas por área mostram o valor ao vivo, então a
soma das áreas ≠ o total do rodapé/card (cálculo visivelmente errado). Decisão do usuário
(jul/2026): o número tem que estar SEMPRE certo e atualizado — a currentness vence o lock.

**How to apply:** o `corte_valor_2` continua sendo gravado no banco (histórico/auditoria e
o badge "Congelado em"), mas não governa mais o total exibido. Se algum novo consumidor
(relatório, modal de kit, e-mail) precisar do "total", use o ao vivo, não `corte_valor_2`.
O `corte_valor_1` (Convicta) permanece congelado e canônico como base do aditivo.
