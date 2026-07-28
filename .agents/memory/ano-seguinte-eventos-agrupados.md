---
name: Ano seguinte em eventos agrupados
description: Padrão do bug "ano seguinte" para grupos (SkuMapping.evento_grupo) com mapping ativo em 2 anos ao mesmo tempo — onde o dado se perde e como não regredir.
---

# Ano seguinte em eventos agrupados (grp_*)

Quando um grupo tem SkuMapping ATIVO tanto para o ano corrente quanto para
ano+1 ao mesmo tempo (carrinho da próxima edição aberto antes da atual
terminar), o bug "não aparece em lugar nenhum" tem DUAS camadas
independentes — corrigir só uma não resolve:

1. **Escrita/batch**: jobs que ressincronizam snapshots (sync diário,
   rolling rebuild, refresh de detail snapshot) tendem a iterar "todos os
   grupos ativos" para UM ano hardcoded. Sem um passo extra para o ano
   seguinte, o snapshot daquele ano nunca nasce em background (só via visita
   manual com ?ano=N+1). O passo extra deve ser ESCOPADO — só para grupos
   com mapping ativo detectado no ano seguinte (query dedicada) — nunca uma
   duplicação cega de todos os grupos, para não dobrar carga em sistemas
   externos com concorrência limitada (ver magento-concurrency-limit.md).
   "Concluído" precisa ser rastreado por PAR (evento_id, ano), nunca só por
   evento_id: a edição corrente pode encerrar enquanto a seguinte está viva.

2. **Leitura/defaults**: qualquer endpoint com `ano` opcional que faz
   fallback tipo `ano = datetime.now().year` quando o caller não especifica.
   Para grupos, o fallback correto é resolver o MAX(SkuMapping.ano) ativo
   daquele grupo (não o ano do relógio) — um grupo pode não ter mais mapping
   ativo do ano corrente. Esse mesmo bug se repete em cada endpoint que
   aceita `ano` para eventos agrupados (comparativo de curva, insights,
   detalhe do evento, médias de venda, snapshot de curva, version, "atualizar
   hoje"...) — todo endpoint novo desse tipo precisa do mesmo resolver.

## Totais ISC (agregados por grupo) devem somar os anos, nunca sobrescrever
Funções que agregam qtd/receita por grupo (ex.: pricing/ISC) devem SOMAR os
dois anos quando ambos ativos e recalcular métricas derivadas (ticket médio
etc.) do total combinado.

## Gotcha: data_evento NULL no mapping do ano seguinte
A linha do ano seguinte costuma nascer com data_evento=NULL. Qualquer lógica
que classifica um grupo como "consolidado/encerrado" usando a MAIOR data
resolvida entre os anos pode congelar erroneamente um grupo que já vende a
próxima edição (a data resolvida cai no ano corrente, já encerrado). Fix:
manter um set explícito de grupos com mapping ativo no ano seguinte e nunca
classificá-los como consolidado, independente da data resolvida.

## Frontend: new Date().getFullYear() — dois lugares, tratamento oposto
- Em LINK DE NAVEGAÇÃO de uma linha/card específico, o ano do link deve vir
  da data daquele evento (`event.date`), nunca do relógio — senão o clique
  manda para o ano errado quando a linha já é a edição seguinte.
- Em PARÂMETRO DE REQUISIÇÃO da lista (ex.: "me traga os eventos do ano X"
  sem seletor de ano na tela), manter o ano corrente como default está
  CORRETO desde que o backend já some o ano seguinte nas métricas de cada
  grupo (item anterior) — não confundir com o bug de navegação acima.

## Limitações conhecidas (não cobertas por este padrão de fix)
- Evento cuja PRIMEIRA edição é o ano seguinte (zero presença no ano
  corrente) continua invisível: a descoberta de candidatos costuma
  depender de SkuMapping.ano == ano e de CadastroEvento/DimProjeto do ano
  pedido — nenhum dos dois inclui um grupo que só existe no ano seguinte.
- Um fast-path de lista que lê snapshot persistido por ano único (usado só
  como fallback instantâneo em cold-start, antes do refresh em background
  rodar) pode não somar os 2 anos como o caminho normal soma — gap
  transitório, autocorrige no próximo ciclo de refresh.
