---
name: Fila pendente vs. histórico resolvido — o que janelar
description: Ao aplicar paginação/janela de performance num endpoint que mistura uma fila de trabalho (pendente) com um log histórico (já resolvido), decide o que pode ser cortado sem virar regressão.
---

Quando um endpoint devolve dois grupos com semântica diferente — itens
"pendentes de ação" e itens "já resolvidos" — a janela de data (ou qualquer
corte de performance) só deve recortar o grupo histórico. O grupo pendente é
lido como fila de trabalho: um item antigo esquecido ali é exatamente o
cenário que a tela existe para pegar, então ele nunca pode desaparecer por
filtro de data nem por um filtro de evento/entidade selecionado alhures na
mesma tela.

**Why:** aplicado na fila de geração de cupons de cortesia — "pendentes"
ficam sempre completos e imunes ao filtro de evento; só "gerados" leva
janela padrão (90 dias, ancorada em quando foi gerado) com escape hatch
explícito (selecionar um evento remove a janela e busca o histórico
completo daquele evento). Uma janela única e cega para os dois grupos
esconderia solicitações pendentes antigas — a pior regressão possível numa
fila de trabalho.

**How to apply:** ao adicionar paginação/filtro de performance em qualquer
outro endpoint que junte fila-de-trabalho + histórico nesse mesmo app
(candidato conhecido: a aba "Solicitações" da tela de Solicitação de
Cortesias, que ainda devolve tudo sem corte), janele só o lado "resolvido";
mantenha o lado "pendente" sempre completo e sempre imune ao filtro
escolhido para o outro lado.
