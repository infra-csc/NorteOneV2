---
name: Projeção Consolidado SWR cache
description: Por que a Visão Consolidada é cacheada e a regra de invalidação a manter
---

A aba "Visão Consolidada" da Projeção de Inscritos é uma agregação cara (varre o snapshot
de vendas) somada a um congelamento ao vivo que escreve no banco — por isso é servida por
um SmartCache em modo SWR, não computada a cada request.

**Regra a manter:** toda mutação que altere projeções OU cortes deve invalidar esse cache
logo após o commit. Se esquecer, a aba mostra números velhos até o TTL expirar.

**Invalidação = mark-stale, nunca delete (Julho/2026):** a invalidação NÃO apaga as
entradas — marca como stale e agenda recompute em background (single-flight; mutação
durante o refresh dispara re-execução ao final, então o último save sempre aparece).
Apagar o cache fazia cada save de qualquer usuário jogar a próxima leitura de todos num
recálculo síncrono pesado — era o gargalo da tela com usuários simultâneos. O caminho de
hard-miss tem trava por chave (anti-estampede). Qualquer recompute do consolidado (SWR,
miss, pós-save) DEVE rodar `congelar_cortes_para_eventos` antes do compute — os três
caminhos precisam ficar em lockstep.

**Why:** sem cache a aba abria "vazia" e os dados só apareciam depois de muito tempo
(reclamação do usuário). SWR resolve servindo o último resultado na hora e atualizando em
background; a contrapartida é que a frescura passa a depender da invalidação explícita.

**How to apply:** ao criar um novo endpoint de escrita que afete o consolidado (nova regra
de corte, novo campo somado, etc.), acrescente a chamada de invalidação como nos demais.
O refresh em background roda em sessão própria — nunca reutilize a `db` do request nele.
Os endpoints leves da tela (pendências por usuário, cutoff-envio-map) têm cache curto de
60s limpo pela mesma invalidação central — novos endpoints "polled" devem seguir o padrão.
