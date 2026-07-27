---
name: Publish build fails on TS errors that dev hides
description: Why "works in dev, fails on publish" happens for the frontend, and where to look first.
---

# Publish build = strict tsc gate (dev is not)

O publish roda `build.sh` → `cd frontend && tsc -b && vite build`. O `tsc -b`
falha o build inteiro em QUALQUER erro de tipo e aborta antes de gerar logs de
runtime — por isso `fetchDeploymentLogs` volta vazio quando a falha é de build.
O `npm run dev` (Vite) NÃO checa tipos de forma bloqueante, então esses erros
passam em desenvolvimento e só aparecem no publish.

**Onde olhar primeiro num "deployment build failed":** usar
`listDeploymentBuilds` + `getDeploymentBuild(id)` e ler o tail dos logs; a causa
costuma ser erro de TS no `tsc -b`, não runtime.

**Padrões recorrentes nesta base (recharts + lucide):**
- Ícones Lucide NÃO aceitam prop `title`. Para tooltip de hover, envolver em
  `<span title="...">`.
- `<Tooltip formatter={...}>` do recharts entrega `number | undefined`. Tipar o
  callback como `(v: number) => ...` quebra (TS2322). Usar
  `(v: number | undefined) => [fmt(v ?? 0), ...]`.

**Verificar localmente antes de re-publicar:** `cd frontend && npm run build`
(exit 0). É o mesmo gate do publish.

**Armadilha do gate local:** `npx tsc --noEmit -p tsconfig.json` na raiz do frontend NÃO checa nada — o tsconfig.json é solution-style (`"files": []` + references), então o comando passa silenciosamente mesmo com o arquivo quebrado. O gate local correto é `cd frontend && npx tsc -b` (mesmo do publish) ou `npm run build`.
