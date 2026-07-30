---
name: Resumo diário de pendências por e-mail (Projeção)
description: Política do guard diário (notif_email_last_sent) e regra de destinatários do digest de pendências.
---

# Digest de pendências por e-mail (Projeção de Inscritos)

Loop diário em `backend/main.py` (`_projecao_notif_loop`, thread `projecao-notif-loop`) +
`services/projecao_notif_service.py` + `services/email_service.py` (Microsoft Graph API —
client_credentials OAuth2 com MS_TENANT_ID/MS_CLIENT_ID/MS_CLIENT_SECRET/MS_SENDER_EMAIL,
NÃO SendGrid — credenciais buscadas em runtime, nunca logadas/persistidas).

## Regra do disparo
Reaproveita EXATAMENTE a regra do alerta in-app `/projecao/pendencias`:
`hoje == min(data_corte_1 das áreas) - dias_alerta_envio`, só eventos `status='Em andamento'`,
sem fallback por data do evento. Agrupa por responsável via `area_projecao_usuario` —
cada usuário recebe só as suas áreas. (Decidido: NÃO usa o flag `recebe_alertas_corte`;
envia a todos os responsáveis.)

## Guard diário (notif_email_last_sent) — decisão importante
Marca `notif_email_last_sent = today` quando: houve sucesso (mesmo parcial, `enviados>0`)
OU não havia nada a enviar (`falhas==0`). **NÃO marca** em falha TOTAL (`enviados==0 && falhas>0`),
e nesse caso re-tenta no mesmo dia com cooldown de 10min (`_RETRY_COOLDOWN_S`).

**Why:** dois riscos opostos. (1) Marcar sempre → falha de credencial/connector suprime o dia
inteiro (bug pego em review). (2) Não marcar em falha parcial e re-tentar a cada 60s →
`enviar_resumo_diario` reenvia a TODOS os grupos, duplicando e-mail de quem já recebeu. A
política acima evita os dois: sucesso parcial conta como "feito" (não duplica), só falha
total (ninguém recebeu) re-tenta.

**How to apply:** se mexer no loop ou no retorno de `enviar_resumo_diario`, preserve a
distinção sucesso-parcial vs falha-total. O endpoint de teste `POST /projecao/notif-test`
usa `force=True` e NÃO toca em `last_sent` (testar não consome o envio do dia).

O loop roda independente de `ENABLE_BACKGROUND_MAGENTO_SYNC` (puro-PG + Microsoft Graph).
Hora do envio é BRT, configurável (`notif_email_hora`); só envia se `notif_email_ativo`.
O mesmo `email_service.py` (Microsoft Graph) é reaproveitado por outros avisos best-effort
da Projeção (ex.: aprovação de redução no Corte de Ajuste) — não é exclusivo do digest.
