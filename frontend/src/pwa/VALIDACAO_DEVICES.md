# Validação de instalação PWA em devices reais

Este checklist precisa ser executado **em campo, com aparelhos reais**, contra a
URL de produção do Norte One. A configuração do PWA já foi validada por build,
mas o comportamento de instalação, atualização e cache offline depende de
device + navegador e não pode ser verificado em ambiente de desenvolvimento.

> Tempo estimado: ~20 min (10 min Android + 10 min iPhone).
> Requisito: 1 deploy disponível para disparar antes do passo "Nova versão".

---

## Pré-requisitos

- [ ] URL de produção em mãos (HTTPS, mesma origem onde o app é usado)
- [ ] Conta de teste com acesso ao ISC Dashboard
- [ ] Possibilidade de fazer 1 novo deploy durante o teste (para validar update)
- [ ] Em ambos os devices, **limpar dados do site** antes de começar
  (Chrome: Configurações do site → Limpar dados; Safari: Ajustes → Safari →
  Avançado → Dados de Sites → Remover)

---

## 1. Android (Chrome) — instalação

1. [ ] Abrir a URL no Chrome do Android
2. [ ] Navegar pelo menos 3x no app (visitar Dashboard, abrir 1 evento, voltar)
       — o `beforeinstallprompt` exige engagement mínimo
3. [ ] Aguardar até aparecer o banner inferior **"Instalar Norte One"**
       (vem do `PWAManager.tsx`, com botão "Instalar")
4. [ ] Tocar em **Instalar** → aceitar prompt nativo do Chrome
5. [ ] Conferir ícone na tela inicial (ícone Norte, sem badge do Chrome)
6. [ ] Abrir pelo ícone → app deve abrir **sem barra de URL** (modo standalone),
       splash com fundo `#111827`

> Observação: se o banner não aparecer, conferir em
> `chrome://flags` se "Bypass user engagement checks" está habilitado para
> teste; em produção real basta navegar mais.

**Print sugerido:** banner de instalação + app aberto em standalone.

---

## 2. iPhone (Safari) — instalação

1. [ ] Abrir a URL no **Safari** (não Chrome iOS — lá não funciona)
2. [ ] Aguardar ~4s no app — deve aparecer o card inferior
       **"Instalar Norte One no iPhone"** com instruções de Compartilhar →
       Adicionar à Tela de Início
3. [ ] Tocar em **Compartilhar** (ícone na barra do Safari) →
       **Adicionar à Tela de Início** → confirmar nome → Adicionar
4. [ ] Conferir ícone na tela inicial (apple-touch-icon Norte, sem reflexo)
5. [ ] Abrir pelo ícone → app deve abrir **sem barra do Safari**, em tela cheia
6. [ ] Conferir que rotação travada em **portrait** funciona

**Print sugerido:** card de instrução iOS + app aberto pelo ícone.

---

## 3. Offline — ISC Dashboard

Executar em qualquer um dos dois devices (idealmente nos dois):

1. [ ] Com sinal, abrir o app instalado e navegar pelo **ISC Dashboard**
       (carrega `/api/marketing/eventos`, `/api/marketing/playbook`,
       `/api/marketing/pricing`, `/api/marketing/cache/status`)
2. [ ] Abrir também 1 **Detalhe de Evento** e a **Curva Comparativa**
       (são as outras rotas no allowlist do service worker)
3. [ ] Ativar **modo avião** (ou desligar Wi-Fi + dados móveis)
4. [ ] Fechar e reabrir o app pelo ícone
5. [ ] Conferir que:
   - [ ] ISC Dashboard abre com os mesmos dados (vindos do cache)
   - [ ] Detalhe de Evento já visitado abre normalmente
   - [ ] Tentar uma ação de **escrita** (ex.: refresh manual, salvar acao
         comercial) deve falhar de forma explícita — **não pode** completar
         silenciosamente. Isso é proposital: só leituras do dashboard são
         cacheadas, escrita/auth/insights nunca.
6. [ ] Religar a rede → app deve voltar ao normal sem precisar reinstalar

**Print sugerido:** ISC Dashboard aberto em modo avião.

---

## 4. Atualização — "Nova versão disponível"

1. [ ] Com app aberto e online, deixar a aba/PWA ativa
2. [ ] Disparar um **novo deploy** do frontend (qualquer mudança serve;
       basta que gere um novo `sw.js`)
3. [ ] Em até ~1 min após o deploy, deve aparecer a faixa roxa no rodapé:
       **"Nova versão disponível — Atualizar"**
4. [ ] Tocar em **Atualizar** → app recarrega imediatamente já na nova versão
5. [ ] (Opcional) Repetir e tocar no **X** para confirmar que a faixa some
       e o app continua funcionando na versão antiga até o próximo reload

**Print sugerido:** banner "Nova versão disponível" sobre a tela.

---

## 5. Documentação do resultado

Cole abaixo (ou em uma issue/nota):

```
Data: ____ / ____ / 2026
Responsável: __________________________

ANDROID (modelo + versão Chrome): _________________________
[ ] Instalação OK     [ ] Standalone OK     [ ] Offline OK     [ ] Update OK
Observações:
- ...

iPHONE (modelo + versão iOS): _____________________________
[ ] Hint iOS apareceu [ ] Add to Home OK   [ ] Standalone OK  [ ] Offline OK
[ ] Update OK
Observações:
- ...

Bugs / ajustes a abrir:
- ...
```

Anexar prints dos passos 1, 2, 3 e 4.

---

## Referências de código

- Banner de instalação / hint iOS / banner de update: `frontend/src/pwa/PWAManager.tsx`
- Lógica de detecção (standalone, iOS, dismiss de 14 dias): `frontend/src/pwa/usePWA.ts`
- Manifest, ícones, allowlist de cache e estratégias: `frontend/vite.config.ts`
