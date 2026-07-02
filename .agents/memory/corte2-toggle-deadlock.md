---
name: Corte 2 toggle deadlock
description: Modal de Projeção Ajuste — validações de save nunca podem exigir um estado que a UI bloqueia; formulário deve reconciliar com a baseline assíncrona do Corte 1.
---

# Corte 2 — deadlock de toggle vs validação

**Regra:** no modal de edição da Projeção (Corte 2), qualquer validação de save que exija toggle LIGADO (kit/cliente presentes na baseline do Corte 1) precisa de uma UI que garanta esse estado: reconciliar o formulário quando a baseline chegar (ligar toggle + pré-preencher com valores C1, adição zero) e travar toggles apenas no estado LIGADO (impedir desligar), nunca prender o desligado.

**Why:** a baseline do Corte 1 chega assíncrona (`corte1-distribuicao`) e pode ter kits mesmo quando a projeção salva não tem (fonte "aproximado" ou "Kit Básico" fabricado no snapshot). O openEdit inicializa toggles sincronicamente a partir da projeção salva → toggle OFF + lock bidirecional + validação exigindo ON = usuário sem saída em produção.

**How to apply:** ao adicionar novas validações de save ou novos locks de UI no modal de projeção, verificar que existe caminho de reconciliação pós-fetch e que o lock só congela o estado que a validação exige.
