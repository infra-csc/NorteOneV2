---
name: Grace period em snapshots disparados por leitura
description: Capturas/congelamentos disparados por leituras devem debounce escritas recentes, senão fotografam estado no meio da digitação.
---

**Regra:** qualquer captura de snapshot/congelamento disparado por LEITURA (ex.: auto-freeze de cortes rodando a cada load do consolidado) deve pular entidades com escrita recente (grace period configurável) e tentar no próximo ciclo.

**Why:** o auto-freeze do Corte 1 congelou 17s após o usuário salvar a PRIMEIRA área (outra pessoa abriu o consolidado), fotografando 2.500 de um total real de 3.458 — kit/dist snapshots incompletos e "+958" fantasma na reconciliação, sem edição no histórico.

**How to apply:**
- Grace via `MAX(updated_at/created_at)` das linhas do escopo, SEM filtrar soft-deleted (soft-delete também indica edição em andamento; onupdate bumps updated_at).
- A ação manual do admin ("agora") nunca passa pelo grace e recaptura TODAS as fotos em lockstep (total + snapshots derivados).
- Grace só adia a captura; nunca afeta o caminho de reversão (auto-descongelamento) nem flags manuais.
