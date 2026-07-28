---
name: Screenshot tool blocked by app auth
description: Why the Screenshot tool can't show authenticated pages of this app, and what to do instead.
---

Every route in this app (Norte) sits behind a login wall — Microsoft SSO or the "Acesso de emergência" local email/password fallback — with no dev-mode bypass. The Screenshot tool only captures a static path/URL; it has no way to fill in a login form or carry over a session, so any `appPreview` screenshot of an app route renders the login screen instead of the real page.

**Why:** discovered while trying to visually verify a UI change — creating a throwaway test user to log in isn't viable either, since there is no interactive/browser-automation tool available to actually submit the login form even after a valid account exists.

**How to apply:** for this project, verify UI-affecting changes via `tsc --noEmit` / Python compile checks, direct backend/DB-level functional tests (create real rows through the actual route functions, assert, clean up), and careful JSX review against existing patterns in the file. Reserve screenshot verification for pages that don't require auth, or ask the user for a quick visual confirmation instead of chasing it.
