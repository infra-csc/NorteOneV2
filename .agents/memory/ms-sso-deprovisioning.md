---
name: Microsoft SSO deprovisioning & break-glass
description: How Entra ID SSO accounts are deprovisioned and how the local break-glass admin must be configured so it survives directory sync.
---

# Microsoft Entra ID SSO — deprovisioning & break-glass

The app supports SSO-only login via Microsoft Entra ID plus a daily directory sync.
A few non-obvious rules keep deprovisioning airtight without locking out emergency access.

## Rule: a Microsoft-managed account must never be able to log in locally
Three layers enforce this together — changing any one in isolation reopens a bypass:
1. On adoption (an Entra user matching a local account by email), the sync/login sets
   `auth_provider='microsoft'` AND zeroes `senha_hash`.
2. `/auth/login` hard-rejects any account with `auth_provider=='microsoft'` BEFORE the
   password check — so even a residual `senha_hash` can't be used.
3. The sync deactivates Microsoft accounts uniformly (no admin exemption) on
   `accountEnabled=false` or when the oid disappears from the directory, and invalidates
   their sessions.

**Why:** an earlier attempt exempted `is_admin` accounts from deactivation as a
"break-glass safety net." Combined with adopted accounts keeping their `senha_hash`,
that let a disabled/removed Entra admin still authenticate via local password — a
directory-deprovisioning bypass. The fix is to NOT special-case admins here.

## Rule: break-glass = a local account kept OUT of the Entra directory
**Why:** the sync only ever touches `auth_provider=='microsoft'` accounts. A dedicated
local admin (the seed admin) whose email is NOT in the directory is never adopted, never
deactivated, and keeps its password — so it always works. Do not try to protect
break-glass by exempting admins inside the sync logic; protect it by keeping the account
out of the directory.

## Login-CSRF defense on the SSO callback
The SSO `state` is double-submitted: stored in an HttpOnly/Secure/SameSite=Lax cookie
(`ms_sso_state`, path `/api/auth/microsoft`) at `/microsoft/login`, and the callback
requires `state` query == cookie (constant-time compare) AND a server-side single-use
`consume_state()`. SameSite=Lax is correct because the Microsoft callback is a top-level
GET navigation, so the cookie is sent. The cookie is cleared on every callback exit.
