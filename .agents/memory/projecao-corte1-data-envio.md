---
name: Corte 1 freeze rule (Projeção envio)
description: Business rule for which date triggers the Corte 1 nightly freeze in Projeção Inscritos.
---

# Corte 1 (Projeção envio) — regra de congelamento

O congelamento do Corte 1 usa, como regra PRINCIPAL, a "Data de corte Envio" por
evento (`data_corte_1` em `ProjecaoCutoffEventoArea`): congela quando
`hoje >= data_corte_1`. Só quando essa data é nula é que cai no fallback D-N
(`ProjecaoCorteConfig.dias_corte_1`).

O congelamento acontece **AO VIVO** no carregamento de `GET /projecao/consolidado`
(não espera o job da madrugada). Fonte única: `congelar_cortes_para_eventos(db,
evento_ids)` em `snapshot_service.py`, que também é chamada pelo job noturno
(`congelar_cortes_projecao_batch`, agora wrapper com `evento_ids=None`) — o job é
só rede de segurança para eventos que ninguém abriu na tela. O total congelado vem
de uma query agregada (SUM por evento) independente de qualquer filtro de área do
consolidado, para nunca congelar total parcial.

- **Corte 2 (Projeção convicta)** NÃO usa data — segue só por D-N (`dias_corte_2`).
- Embora `data_corte_1` seja por (evento, área), na prática só uma única área a
  preenche por evento; o batch e o `get_consolidado` tratam como por-evento usando
  a **data mais antiga** quando há mais de uma (determinístico nos dois lados).
- Ações manuais de admin ("Congelar agora" / "Reabrir") ignoram a data — congelam/
  reabrem no momento do clique. A regra de data vale só para o job noturno.
- **Auto-DESCONGELAR Corte 1:** se um corte já congelado tem `data_corte_1` cadastrada
  e ela ainda NÃO chegou (`hoje < data_corte_1` => need_1 False), o snapshot é
  limpo (`valor_corte_1`/`congelado_corte_1_em` = None) e volta a acompanhar ao vivo.
  Caso típico: congelou pelo fallback D-N quando a data não existia, e depois o
  usuário cadastrou uma data de envio futura. SÓ dispara quando `data_envio is not
  None` — congelamentos por D-N puro (sem data) e o Corte 2 ficam intactos. Roda no
  mesmo loop do freeze, ANTES das escritas, então não oscila (após descongelar,
  need_1 é False e nada re-congela na mesma passada). Como `hoje` só cresce, um corte
  legitimamente congelado por data (hoje>=data) nunca descongela. Retorna contador
  `descongelados`.

**Why:** o usuário define a data real de envio da projeção por evento; o D-N fixo
não reflete isso. A data específica deve mandar quando existir.

**How to apply:** qualquer mudança no gatilho de congelamento do Corte 1 deve manter
batch (`congelar_cortes_projecao_batch`) e display (`get_consolidado` →
`corte_data_envio`) em lockstep, senão a prévia do card e o que de fato congela
divergem.
