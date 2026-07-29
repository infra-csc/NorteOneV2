---
name: Ano seguinte em eventos agrupados
description: Padrão do bug "ano seguinte" para grupos (SkuMapping.evento_grupo) com mapping ativo em 2 anos ao mesmo tempo — onde o dado se perde e como não regredir.
---

# Ano seguinte em eventos agrupados (grp_*)

Quando um grupo tem SkuMapping ATIVO tanto para o ano corrente quanto para
ano+1 ao mesmo tempo (carrinho da próxima edição aberto antes da atual
terminar), o bug "não aparece em lugar nenhum" (ou "aparece errado/duplicado")
tem VÁRIAS camadas independentes — corrigir só uma não resolve:

0. **Regra geral, vale para TODAS as camadas abaixo**: `ano == datetime.now().year`
   (ou qualquer comparação do ano pedido/rotulado contra o ano do calendário)
   é um proxy ruim para "esta edição está ao vivo/vigente". Uma edição datada
   no ano seguinte pode já estar vendendo (regime live) enquanto o ano
   corrente ainda não virou; uma edição do ano corrente pode já ter
   encerrado (regime consolidated) meses antes do ano acabar. Qualquer gate
   que decide "reconstruir snapshot vs. servir versão congelada" (ou
   "agrupar vs. tratar como standalone") deve resolver o REGIME real da
   edição (data_evento + status, via get_event_regime/get_data_regime) e
   nunca comparar o rótulo do ano contra o relógio. Isso já se repetiu tanto
   no endpoint de DETALHE (gates de rebuild/floor do snapshot, grouped E
   standalone) quanto no endpoint de LISTA (item 3 abaixo) — buscar por
   `== datetime.now().year` / `== date.today().year` em endpoints novos.

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

3. **Classificação grupo↔standalone (endpoint de LISTA)**: o mapa
   sku→evento_grupo usado para decidir "este projeto pertence a um grupo ou é
   standalone" costuma ser construído com `SkuMapping.ano == ano` estrito
   (sem olhar ano+1), igual ao item 2 mas para uma função DIFERENTE (não é
   fallback de qual `ano` usar — é "a que grupo este projeto pertence, dado
   um `ano` já resolvido"). Quando a edição do `ano` pedido já consolidou e o
   ano seguinte já tem mapping ativo, o projeto do ano seguinte não bate com
   nenhuma entrada do mapa (que só conhece o SKU velho) e cai como
   "standalone órfão" — some do card do grupo e some da lista até algum
   bootstrap assíncrono descobrir e persistir seu snapshot avulso pela
   primeira vez. Fix: função dedicada que parte do mapa base do `ano` e, por
   grupo, HANDOFF (troca, não soma) os SKUs do `ano` pelos do `ano+1` quando
   a edição do `ano` já está em regime consolidated (ou não tem mapping ativo
   nenhum) — nunca fazer merge/soma aqui, isso é para agregação de valores
   (item "Totais ISC" abaixo), não para classificação de pertencimento.
   Resolver a data por DimProjeto (join por SKU normalizado), não por
   SkuMapping.data_evento (ver gotcha de NULL abaixo). Aplicar essa função
   dedicada SÓ no endpoint de lista (e no fast-path de snapshot agregado que
   o alimenta) — os demais chamadores do mapa base (curvas históricas,
   diagnósticos, endpoints de análise de um ano específico) querem o mapping
   literal do ano pedido, sem handoff.

## Totais ISC (agregados por grupo) devem somar os anos, nunca sobrescrever
Funções que agregam qtd/receita por grupo (ex.: pricing/ISC) devem SOMAR os
dois anos quando ambos ativos e recalcular métricas derivadas (ticket médio
etc.) do total combinado. Isso é sobre VALORES (qtd/receita) com os dois anos
ainda vivos ao mesmo tempo — não confundir com o handoff do item 3, que é
sobre PERTENCIMENTO (a que grupo o projeto pertence) e só troca depois que a
edição velha já consolidou (nunca soma as duas, seria dobrar o card).

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
- Cuidado ao aplicar o handoff do item 3: se o fast-path de lista (leitura
  agregada de snapshots persistidos, usada para responder rápido sem
  recalcular tudo) tiver sua PRÓPRIA query de classificação grupo↔standalone
  independente (usada só para detectar/limpar snapshots órfãos), ela precisa
  ser migrada para a MESMA função com handoff — senão o card correto
  (caminho normal, já corrigido) e uma entrada standalone órfã do snapshot
  antigo (fast-path ainda com a query velha) aparecem os DOIS na lista ao
  mesmo tempo, duplicado. Já aconteceu neste projeto — as duas queries foram
  alinhadas para reusar a função de handoff. Mesmo alinhadas, o fast-path
  ainda depende do caminho normal ter rodado pelo menos uma vez para ter um
  snapshot correto para servir (gap de bootstrap continua, é só o de
  classificação duplicada que fecha).
