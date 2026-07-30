---
name: E2E testing against the live dev backend
description: Gotchas when driving real HTTP requests at the running Backend API during verification — reload deadlocks and real email sends.
---

# E2E testing against the live dev backend

Verifying a new endpoint end-to-end by minting a JWT + `UserSession` row and
hitting the running Uvicorn server directly (mirrors the login flow in
`backend/app/api/routes/auth.py`) is the right approach when the UI sits
behind SSO (see `screenshot-auth-wall.md`). Two non-obvious hazards:

1. **Never place a throwaway test script inside `backend/`.** Uvicorn runs
   with `--reload` and watches that whole tree; writing/deleting a `.py`
   file there mid-test triggers a full app reload. A request that lands
   during the reload's startup migrations can produce a genuine Postgres
   deadlock (AccessShareLock vs AccessExclusiveLock) that looks like a
   concurrency bug in the endpoint you just wrote but is actually the
   migration racing your request. Write test scripts to `/tmp/` and run
   them with `cd backend && python3 /tmp/script.py` instead.

2. **Email sends are real, not mocked.** `email_service.py` (Microsoft
   Graph, MS_CLIENT_ID/SECRET/TENANT_ID/MS_SENDER_EMAIL) has no dev/sandbox
   mode — any code path that calls `send_email()` during a test delivers a
   real message to the recipient's real inbox (confirmed: users in this DB
   have real corporate addresses). Best-effort notification helpers also
   tend to log failures but not successes, so silence in the logs does not
   mean "not sent" — it's equally consistent with a successful real send.
   Before E2E-testing a feature with best-effort email notifications,
   expect real emails to go out to whichever real users are in your test
   path; there is no way to dry-run `send_email()`.

**Why:** discovered while testing Task #212 (reduction-approval flow) — a
first test run hit a deadlock purely from the script's own file living in
`backend/`, and a second, clean run silently sent real "chamado pendente"
emails to two real employee inboxes with no way to intercept or undo it.

**How to apply:** for any future feature verified this way, write test
scripts outside `backend/`/`frontend/`, and if the feature under test
triggers email/SMS/webhook notifications, disclose to the user afterward
that real sends happened rather than assuming they were suppressed.
