---
name: Login button must fail open
description: Why the Microsoft SSO button on the login page must never be gated solely on a live status check.
---

# Login SSO button: fail open, never fail closed

The "Entrar com Microsoft" button on the login page must remain visible whenever
SSO is (or was recently) configured, independent of live backend health.

**Why:** The button used to render only after a live `/auth/microsoft/status`
check returned `enabled:true`, starting hidden and hiding again on any error.
The axios client had no timeout. Under heavy load (Magento SSH queue blocks the
FastAPI event loop; unrelated endpoints return 500 and requests wait 60–80s),
that trivial config check would stall or fail, so users intermittently saw no
Microsoft button — a DB/infra problem was blocking authentication, which must
never happen. Credentials were fine the whole time (secrets present in prod,
`MS_REDIRECT_URI` correct); the fragility was purely client-side.

**How to apply:**
- Cache the last-known SSO-enabled state in `localStorage` (`sso_enabled`) and
  seed initial UI from it so the button shows immediately on return visits.
- Give the status check a short timeout (~6s).
- On check failure, fail OPEN: keep the button if we previously knew SSO was on.
- Preserve "Microsoft-first" on success: `showLocalLogin = enabled ? userOpenedEmergency : true`.
  Track the explicit break-glass toggle with a ref so background revalidation
  doesn't close the emergency form under the user.
- Guard every `localStorage` access with try/catch (private/restricted modes).
