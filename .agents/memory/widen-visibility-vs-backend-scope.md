---
name: Widening visibility requires widening the backend read scope too
description: Making an area/owner-only card "visible to everyone, read-only for others" by loosening only the frontend render gate leaves fields blank for non-owners if the GET endpoint still filters rows by the caller's own area.
---

When a feature was originally "visible AND editable only to the owning área/admin"
via a single combined frontend condition, and the request is to make it
"visible to everyone, editable only as before," there are two independent
gates to find and split, not one:

1. The frontend render condition (which rows/cards show up in the UI).
2. The backend GET endpoint's row-scoping (which rows the API even returns
   to that caller).

Loosening only #1 is not enough if #2 independently restricts by the
caller's own `área`/permission — non-owners will see the now-visible
card/row rendered with empty/blank values, because the API silently
dropped their data before it ever reached the frontend. This looks like a
frontend bug ("the field just doesn't show the value") but is actually the
backend still doing the old area-scoped filtering.

**Why:** Found on the Projeção screen's per-área cutoff-date cards
(`GET /projecao/cutoff-evento-area`). First pass loosened the frontend's
`myCustomAreas` filter and added a `canEditThisArea` render gate on the
inputs/save button — correct for visibility, but the GET endpoint still did
`area_ids = _get_user_area_ids(...)` and filtered rows to the caller's own
áreas for non-admins. A "padrão" user outside the owning área then saw the
date card but with empty inputs, since the API never sent that área's row.

**How to apply:** When asked to convert an "edit-gated" card/list into
"visible to all, edit-gated as before," trace the data from DB → API →
frontend state → render — don't stop at the render condition. Before
dropping the backend's area filter on the read endpoint, confirm the
paired write/mutate endpoint (PUT/POST/DELETE) re-validates the caller's
area permission independently (many codebases have a small
`_check_area_permission`-style helper reused across mutate endpoints) —
if so, the read endpoint's filter is redundant with the write guard and
safe to drop entirely. If the write endpoint instead trusted the read
endpoint's scoping implicitly (no independent check), add that check to
the write endpoint first, or the widened read access becomes a widened
write hole too.
