---
name: Area-scoped lists vs module permissions
description: Endpoints scoped to a user's assigned areas can wrongly empty-out for roles that hold a module permission but no area assignment (e.g. a global coupon generator); don't retrofit the scoped endpoint.
---

Many list endpoints filter non-admins down to their assigned areas (via
`AreaProjecaoUsuario`), while the ability to act on a resource is governed
independently by `PerfilPermissao` flags (`pode_visualizar`/`pode_criar`/
`pode_editar`/`pode_deletar`) per module. These two mechanisms are
orthogonal: a user can hold `pode_editar` on a module's permission profile
while having zero rows in the area-assignment table — a "global" role with
no area at all (e.g. someone whose whole job is generating coupons across
every area, not owning any one area).

Reusing the existing area-scoped list for that role silently returns empty
results — it looks like "nothing pending" when really the user just isn't
scoped to any area.

**Why:** Found while adding a dedicated queue view for coupon generators in
the Solicitação de Cortesias feature — the existing list endpoint (scoped by
area, correct for area owners requesting their own courtesies) returned
nothing for a generator account with edit rights but no area assignment.

**How to apply:** When a new role is meant to see across all areas (a
"global" reviewer/generator/approver), add a new endpoint gated purely on
the module permission flag (no area filter) rather than changing the
existing scoped endpoint — patching the scoped one to skip area filtering
for some permission would silently widen what area-owners can see too.
Expect this same shape anywhere else area-scoping and module permissions
coexist (e.g. future approval queues).
