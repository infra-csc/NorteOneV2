---
name: Teams DM app-only impossível
description: Por que o canal Teams DM das notificações de Projeção foi descontinuado (limitação do Microsoft Graph)
---

# Teams DM com client credentials não funciona

**Regra:** Aplicações (client_credentials, sem usuário logado) NÃO conseguem enviar mensagens de chat 1:1 no Teams via Graph (`POST /chats/{id}/messages`). `ChatMessage.Send` é permissão **exclusivamente delegada** — não existe como application permission no Azure. O Graph responde 403 exigindo `Teamwork.Migrate.All` (que serve só para importação/migração, não para notificações).

**Why:** Confirmado por probe real (jul/2026): token app-only tinha Chat.Create, User.Read.All, TeamsActivity.Send, Mail.Send — e ainda assim o POST foi bloqueado. Adicionar a permissão no Azure Portal não resolve, porque delegada nunca entra no token app-only.

**How to apply:** Se voltar o desejo de notificar via Teams, os caminhos suportados são: (1) activity feed via `TeamsActivity.Send` (requer app Teams registrado e instalado para os usuários), ou (2) webhook/Workflows postando em canal. Nunca reativar o caminho de DM por chat. O canal de notificação da Projeção foi fixado em 'email' (backend normaliza valores legados 'teams'/'ambos' no read, no save e no envio).
