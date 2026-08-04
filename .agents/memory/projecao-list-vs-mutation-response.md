---
name: ProjecaoInscritosResponse — list endpoint is authoritative, mutations are not
description: Where to add new derived/advisory fields on projeção rows (e.g. pending-approval badges) without over-scoping the edit.
---

# List endpoint is authoritative; create/update responses are write-acknowledgments only

`ProjecaoInscritosResponse` is constructed in 4 places in
`backend/app/api/routes/projecao.py`: the main list endpoint, the trash
(`/lixeira`) endpoint, and the single-row create/update endpoints. The
frontend (`ProjecaoInscritos.tsx`) never consumes the create/update response
bodies for state — `handleSalvarProjecao` (and the create equivalent) discard
the returned object and call `loadData()` afterward, which re-fetches
everything from the list endpoint.

**Why:** confirmed while adding a "chamado pendente" (pending
reduction-approval) indicator to projection rows — the field only needed to
be populated in the list endpoint's batched query. Populating it on
create/update too would have been wasted, inconsistent-risk work (those
endpoints don't have easy access to a fresh "is there a pending request"
lookup at that point in the save flow, and it would never be read anyway).

**How to apply:** when adding a new derived/advisory field to a projeção row
(badges, computed flags, anything not directly user-edited), populate it only
in the list endpoint (and `/lixeira` if it should also show there — usually
not, for anything tied to "current state needs attention"). Leave it at the
Pydantic default on create/update responses; don't chase consistency across
all 4 construction sites unless you first verify the frontend actually reads
that particular response body instead of refetching.
