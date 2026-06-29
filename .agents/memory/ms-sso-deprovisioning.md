---
name: Microsoft SSO deprovisioning & break-glass
description: How Entra ID SSO accounts are deprovisioned and how the local break-glass admin must be configured so it survives directory sync.
---

# Microsoft Entra ID SSO — deprovisioning & break-glass

The app supports SSO-only login via Microsoft Entra ID plus a daily directory sync.
A few non-obvious rules keep deprovisioning airtight without locking out emergency access.

## Rule: a Microsoft-managed account must never be able to log in locally — UNLESS it is explicit break-glass
By default, three layers enforce SSO-only — changing any one in isolation reopens a bypass:
1. On adoption (an Entra user matching a local account by email), the sync/login sets
   `auth_provider='microsoft'` AND zeroes `senha_hash`.
2. `/auth/login` hard-rejects any account with `auth_provider=='microsoft'` BEFORE the
   password check — so even a residual `senha_hash` can't be used.
3. The sync deactivates Microsoft accounts on `accountEnabled=false` or when the oid
   disappears from the directory, and invalidates their sessions.

The single sanctioned exception is the per-account boolean `dim_usuario.permite_login_local`
(break-glass / dual login). When True, ALL THREE layers skip the account: adoption and sync
do NOT zero `senha_hash`, `/auth/login` allows the password path even with
`auth_provider=='microsoft'`, and the sync never deactivates it (excluded from the
disabled-branch and from the orphan-SSO query). Net effect: that account logs in BOTH via
Microsoft (ms_oid stays linked) AND via emergency password.

**Why:** an earlier attempt exempted `is_admin` accounts broadly — that was wrong because it
was implicit and class-wide, letting any disabled/removed Entra admin bypass deprovisioning.
The correct shape is an EXPLICIT, opt-in, per-account flag (not a role), so the bypass is a
deliberate operator decision on one named account, not an automatic property of a role.

**How to apply:** to restore/create a break-glass account, set `permite_login_local=True` and
give it a `senha_hash`. Keep the set of flagged accounts tiny and audited. If you add new
deprovisioning/zeroing logic to the sync or login, it MUST honor this flag too or it silently
breaks emergency access (or reopens a class-wide bypass).

Also: the manual sync trigger (`POST /admin/usuarios/sincronizar-microsoft`) is a
mutating/deprovisioning action — guard it with `require_permission(..., "pode_editar")`,
not the default read permission, or read-only users can deactivate accounts.

## Note: break-glass no longer requires keeping the account OUT of the directory
Previously the only break-glass recipe was "a local admin whose email is NOT in Entra" (so the
sync never touches it). That still works, but it fails the moment the person's real corporate
email IS in the directory (the sync adopts it, zeroes the senha, sets microsoft → emergency
login breaks). The `permite_login_local` flag supersedes that: a directory-managed account can
now be break-glass without being pulled out of Entra.

## Login-CSRF defense on the SSO callback
The SSO `state` is double-submitted: stored in an HttpOnly/Secure/SameSite=Lax cookie
(`ms_sso_state`, path `/api/auth/microsoft`) at `/microsoft/login`, and the callback
requires `state` query == cookie (constant-time compare) AND a server-side single-use
`consume_state()`. SameSite=Lax is correct because the Microsoft callback is a top-level
GET navigation, so the cookie is sent. The cookie is cleared on every callback exit.
