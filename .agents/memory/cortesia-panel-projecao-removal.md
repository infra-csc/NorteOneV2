---
name: External Cortesias app integration fully removed
description: The external "Cortesias" 3rd-party API integration (screen, routes, service) was deleted app-wide; do not re-add it and do not confuse it with the internal cortesia_solicitacao feature
---

The external "Cortesias" integration — a 3rd-party app at `https://app-cortesia.vercel.app`
(courtesy solicitados/aprovados/utilizados/disponiveis metrics + user list, auth via
`CORTESIA_API_TOKEN`) — was removed from this codebase entirely, both frontend and backend.
Deleted: `CortesiasPanel` (an embedded widget, first removed from `ProjecaoInscritos.tsx`), then
the whole standalone `CortesiasEventos.tsx` screen + its `/cortesias` route, its Layout.tsx menu
entry, the frontend `cortesiaService`/`CortesiaMetrics`/`CortesiaUser`/`CortesiaEventoRow`/
`CortesiaEventosResponse` symbols in `services/api.ts`, the backend `/api/cortesia/*` router,
`cortesia_service.py`, and the `CORTESIA_API_BASE_URL`/`CORTESIA_API_TOKEN` config settings.

**Why:** The screen (and the panel before it) fired unconditional external HTTP calls on every
visit — `getUsers` + `getMetrics` on mount for the embedded panel, and a per-SKU fan-out loop
(one external request per event SKU, dozens of sequential calls with a single-flight/45s cache
band-aid already layered on top) for the standalone `/cortesias` screen's `/api/cortesia/eventos`
endpoint. This was a real, user-visible source of slowness and the primary source of the app's only
non-DB, 3rd-party network dependency. User explicitly asked to remove the screen "to end this API
query once and for all" — full removal, not a further mitigation.

**How to apply:** Do not re-add any `cortesiaService`-style client, `/api/cortesia/*` route, or
`app-cortesia.vercel.app` call — the feature was deliberately deleted, not just hidden. If courtesy
metrics from that external app are wanted again, treat it as a new feature request (ask the user)
rather than restoring old code. The `CORTESIA_API_TOKEN` secret itself was left in place (unused);
only the code reading it was removed. Do NOT confuse this with the still-active, fully internal
`cortesia_solicitacao` feature (`SolicitacaoCortesias.tsx`, `/api/cortesia-solicitacao/*`,
`cortesiaSolicitacaoService` in api.ts) — a same-ish-named but functionally unrelated
request/coupon-approval workflow with its own DB tables (`cortesia_solicitacao`,
`cortesia_cupom_codigo`, `cadastro_cortesia`) that never calls any external API; it and the
internal "incluir cortesias"/`cortesia_total` order-labeling analytics (marketing.py,
DadosConsolidados.tsx, EventDetail.tsx) are legitimate, separate, and must not be touched when
someone says "remove Cortesias" — always check which of the two they mean.
