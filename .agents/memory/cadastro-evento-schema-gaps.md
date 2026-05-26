---
name: Cadastro Evento schema gaps
description: Campos do model CadastroEvento que existem no banco mas podem não estar expostos no contrato Pydantic/UI — checklist para adicionar campo editável.
---

Em `backend/app/models/cadastro_evento.py` existem campos que historicamente foram adicionados ao banco/model sem nunca terem sido expostos no contrato de API e formulário. Quando o usuário pede para "preencher X" e não acha na tela, a causa quase sempre é essa.

**Why:** o `id_evento_magento` (chave de junção crítica com Magento — usada por snapshot_service, marketing, kit_config) existia só no model. Resultado: evento ficava órfão de vendas até alguém abrir o DB e dar UPDATE manual. Bug invisível, demora horas pra diagnosticar.

**How to apply — checklist quando for tornar um campo do `CadastroEvento` editável:**
1. `backend/app/schemas/cadastro_evento.py`: adicionar em **três** classes — `CadastroEventoBase`, `CadastroEventoUpdate`, `CadastroEventoResponse`. (Base cobre Create; Update e Response são separados.)
2. `backend/app/api/routes/cadastros.py`:
   - `criar_cadastro` → incluir no construtor `CadastroEvento(...)`.
   - `atualizar_cadastro` → usar `'<campo>' in data.model_fields_set` (Pydantic v2) em vez de `is not None`, para permitir `null` explícito como "limpar". `if data.X is not None` impede limpeza via UI.
   - `db_to_response` E `db_to_list_response` → adicionar a chave no dict retornado; senão o Pydantic preenche default e o frontend nunca vê o valor real.
3. Frontend `frontend/src/pages/cadastros/Cadastro.tsx`: adicionar em **cinco** lugares — interface `CadastroEvento`, interface `FormData`, `initialFormData`, `populateForm` (edição), payload do `handleSubmit`, e o input JSX na aba certa.
4. Para IDs externos (Magento, Ativo), validar `> 0` no backend e tratar 0/negativo como NULL — evita FK lixo.
