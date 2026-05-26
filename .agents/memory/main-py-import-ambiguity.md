---
name: Ambiguidade de import "from main"
description: Estado in-process compartilhado entre o app FastAPI e rotas nunca deve viver em backend/main.py — usar módulo dedicado em app.core/.
---

Não use `from main import X` para compartilhar estado entre `backend/main.py` (app FastAPI) e qualquer outro módulo do backend.

**Why:** Há um `main.py` stub na raiz do repositório (Replit). O cwd do workflow é `backend/`, então `from main import` resolve pro arquivo certo em runtime — mas qualquer ferramenta externa rodando do root (architect, scripts ad-hoc, pytest sem rootdir), ou refator que mude o cwd, vai importar o stub e quebrar silenciosamente caindo em `except Exception: ... = None`. Resultado: feature aparenta funcionar mas o valor lido é sempre `None`.

**How to apply:** Para qualquer var/função que precise ser lida fora de `backend/main.py` (countdowns de scheduler, ticks de jobs, contadores in-process), crie um módulo pequeno em `backend/app/core/<feature>_state.py` com Lock + getters/setters explícitos. Importe dele tanto no `main.py` quanto no consumidor. Isso remove a ambiguidade do nome `main` e torna o estado testável.
