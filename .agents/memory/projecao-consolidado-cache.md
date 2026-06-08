---
name: Projeção Consolidado SWR cache
description: Por que a Visão Consolidada é cacheada e a regra de invalidação a manter
---

A aba "Visão Consolidada" da Projeção de Inscritos é uma agregação cara (varre o snapshot
de vendas) somada a um congelamento ao vivo que escreve no banco — por isso é servida por
um SmartCache em modo SWR, não computada a cada request.

**Regra a manter:** toda mutação que altere projeções OU cortes deve invalidar esse cache
logo após o commit. Se esquecer, a aba mostra números velhos até o TTL expirar.

**Why:** sem cache a aba abria "vazia" e os dados só apareciam depois de muito tempo
(reclamação do usuário). SWR resolve servindo o último resultado na hora e atualizando em
background; a contrapartida é que a frescura passa a depender da invalidação explícita.

**How to apply:** ao criar um novo endpoint de escrita que afete o consolidado (nova regra
de corte, novo campo somado, etc.), acrescente a chamada de invalidação como nos demais.
O refresh em background roda em sessão própria — nunca reutilize a `db` do request nele.
