---
name: Override de curva — modo vigente vs histórico
description: Como funciona o override de curva de referência da ISC quando aponta para uma etapa do PRÓPRIO ano que já fechou (modo "vigente") em vez do ano anterior.
---

# Override de curva: dois modos

O override manual da curva de referência da ISC (`EventoGrupo.curva_override`)
agora tem um qualificador `EventoGrupo.curva_override_modo`:

- `historico` (default / legado): aponta para a curva do **ano anterior** do
  grupo-alvo (caminho clássico via `CurvaHistoricaSnapshot`).
- `vigente`: usa a curva **REAL já realizada** do grupo-alvo no **mesmo ano da
  edição** — caso de "usar a etapa anterior do mesmo ano que já fechou" (ex.:
  Outono/2026 como referência para Inverno/2026, quando não há histórico do ano
  anterior porque o grupo é todo derivado/regional).

**Por que:** eventos novos / circuitos com etapas só de 2026 não têm histórico
de ano anterior; a única curva real disponível é a de uma etapa irmã do mesmo
ano que já encerrou.

**Como aplicar:**
- A curva vigente é montada ao vivo a partir de `vendas_diaria_snapshot`
  (`ano` = ano da edição), nunca de `CurvaHistoricaSnapshot`. Helper:
  `marketing._fetch_current_year_realized_pattern`.
- Só monta quando o alvo **encerrou** (`data_inscricao = data_evento -
  dias_encerramento < hoje`) — senão a curva seria parcial e satura em pct=1.0.
  Também descarta total<20 e curvas saturadas.
- Se `modo=='vigente'` mas a curva não puder ser montada, o resolvedor **ignora
  o override** e cai na cadeia de fallback normal (NÃO usa o histórico do alvo).
  Comportamento intencional, porém silencioso.
- O endpoint `available-curves` retorna `{historicas, vigentes}` (não é mais um
  array). Os candidatos `vigentes` são pré-validados chamando o próprio builder,
  então tudo que aparece na lista realmente se aplica ao ser selecionado.
  Qualquer consumidor novo precisa tratar o shape de objeto (há fallback p/ array
  antigo no front).
- `tipo_curva` resultante é `manual_vigente` (vs `manual` do histórico); os mapas
  de label/cor no front (EventDetail + DiagnosticoCurvasPanel) precisam dessa
  chave.
