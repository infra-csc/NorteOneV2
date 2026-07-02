---
name: PWA stale-cache (produção mostra vazio com dados existentes)
description: Quando uma tela só em produção aparece vazia/desatualizada apesar de o backend retornar os dados, suspeitar do bundle JS antigo no service worker do PWA antes de procurar bug de backend.
---

# PWA stale-cache: "produção mostra vazio mesmo tendo dados"

Sintoma clássico do usuário: uma tela (ex.: Projeção Inscritos → Visão Consolidada)
mostra estado vazio **apenas no app publicado/PWA**, enquanto os dados existem e o
endpoint responde `200 OK`.

**Como confirmar que NÃO é backend (faça nesta ordem):**
1. Replicar a lógica do endpoint via SQL contra a réplica de produção (`executeSql environment:"production"`) — confirma que os dados existem e quantas linhas o endpoint retornaria.
2. Conferir nos deployment logs que o endpoint retorna `200 OK` e que o deploy ativo é o commit atual.
3. Rodar a própria função do endpoint contra a DB em dev — se retorna os dados, o código está correto.
4. Conferir que não há cache de resposta no frontend (axios) nem no service worker (`runtimeCaching` do `vite.config.ts` cobre só `/api/marketing/*`, não `/api/projecao/*`).

Se tudo acima passa → a causa é **bundle JS antigo servido pelo service worker** no dispositivo do usuário.

**Why:** o PWA precacheia `index.html` + chunks JS. Apps instalados (iOS/iPadOS/Android)
ficam abertos por horas/dias sem reload completo; se o SW só checa atualização no
carregamento inicial, o usuário fica preso a um bundle antigo.

**How to apply / correção definitiva:**
- `registerType: 'autoUpdate'` no `vite.config.ts` (injeta skipWaiting + clientsClaim).
- Em `usePWA.ts`, no `onRegisteredSW` guardar o `registration` e chamar `registration.update()`
  periodicamente (60s) + em `visibilitychange` (com guard `navigator.onLine` e cleanup do interval/listener).
- Mantém `onNeedRefresh → triggerAutoReload` (aplica e recarrega).
- Workaround imediato para o usuário: Ctrl+Shift+R no navegador, ou fechar/reabrir o app instalado.

**Causa raiz que faz até o Ctrl+Shift+R falhar (MUITO importante):** quando o backend
FastAPI serve o SPA buildado (catch-all `serve_spa` com `FileResponse`), o `sw.js` e o
`index.html` saem **sem cabeçalho anti-cache**. Se o `sw.js` for cacheado, o navegador
nunca enxerga um service worker novo → o `registerType:'autoUpdate'` + `registration.update()`
**nunca disparam** e o usuário fica preso eternamente no bundle antigo, mesmo com hard refresh.
**Why:** a cadeia de auto-update depende de o browser baixar um `sw.js` byte-diferente; um
`sw.js` cacheado quebra toda a corrente. **How to apply:** no `serve_spa`, aplicar
`Cache-Control: no-cache, no-store, must-revalidate` (+ `Pragma: no-cache`, `Expires: 0`)
em `index.html`, `sw.js`, `*.webmanifest` e `registerSW.js`. Os assets sob `/assets` têm hash
no nome (imutáveis) e **devem continuar cacheáveis**. Só toma efeito após republicar.

**Rede de segurança final (version guard, Julho/2026):** mesmo com tudo acima, um
`sw.js` antigo já preso em cache HTTP nunca deixa a cadeia disparar. A solução definitiva
é um guarda de versão independente do SW: versão única por build embutida no bundle
(vite `define`) + `version.json` no dist + endpoint `/api/version` no-store; o app compara
periodicamente e, em mismatch, tenta `update()` e depois escala para unregister do SW +
limpeza só dos caches de precache + reload, com anti-loop em localStorage (máx 2 tentativas
por versão-alvo, resetado quando as versões batem). Nunca apagar os caches de dados runtime.
Em dev o guard fica inerte (`import.meta.env.DEV` + version null quando não há version.json).

**Nota de diagnóstico:** a réplica de leitura de produção tem lag — a mesma query pode
retornar contagens diferentes em chamadas seguidas enquanto replica. Não confundir lag de
réplica com "dados sumindo".
