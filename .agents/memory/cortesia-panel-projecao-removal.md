---
name: Cortesias panel removed from Projeção screen
description: Why an external Cortesias API panel was removed from ProjecaoInscritos.tsx and where courtesy metrics live now
---

Do not embed the external "Cortesias" app integration (`cortesiaService.getMetrics`/`getUsers`,
which hits a 3rd-party API via an authenticated backend proxy, historically seen with up to ~10s
timeouts and occasional 502/504) as an eagerly-mounted panel on the Projeção screen's main view.
A component named `CortesiasPanel` used to live inside `ProjecaoInscritos.tsx` and render
unconditionally on the default "projeções" tab — it was removed.

**Why:** User reported the Projeção screen felt slow and asked to find/remove "an API connection"
made on it. Investigation confirmed the only genuine external (non-DB, 3rd-party) network
dependency on that screen was this always-mounted courtesy-metrics widget: it fired 2 external
HTTP calls (getUsers on mount, getMetrics once an area auto-selects) every single time the screen
opened, with a visible blocking spinner ("Consultando o app de Cortesias...") — independent of
this app's own (fast, cached) Postgres-backed data. The other polling loops on this screen
(pendências every 3min, consolidado SWR retry after cache invalidation) are unrelated, intentional,
already-documented caching patterns — not the cause.

**How to apply:** Courtesy/cortesia metrics are still fully available via the dedicated
`CortesiasEventos.tsx` page (own route) — the shared `cortesiaService`, its types, and the backend
`/api/cortesia/*` routes / `cortesia_service.py` were NOT touched, only the duplicate widget
embedded in `ProjecaoInscritos.tsx` was deleted. If courtesy data is wanted back on the Projeção
screen, make it opt-in/lazy (load only when a user expands a section), never eager-mounted on the
main tab that every visitor hits.
