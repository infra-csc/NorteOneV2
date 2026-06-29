---
name: SSO redirect base_url behind proxy
description: Why MS SSO must use an explicit public origin, not request.base_url, on Replit
---

# MS SSO redirect URLs behind the Replit/Vite proxy

Behind Replit's setup the public domain (port 80 → Vite on 5000) proxies `/api/*`
to the FastAPI backend on 8000. When Vite proxies, the backend sees `Host: localhost:8000`,
so `request.base_url` resolves to `http://localhost:8000` — NOT the public domain.

**Rule:** Never build externally-visible SSO URLs from `request.base_url`. Two URLs must be
the real public origin:
1. The `redirect_uri` sent to Azure (else AADSTS50011 redirect-mismatch).
2. The post-login browser redirect back to the frontend (else the browser is sent to
   `localhost` → ERR_CONNECTION_REFUSED).

**How to apply:** `MS_REDIRECT_URI` must be set per environment (dev domain vs `*.replit.app`)
and registered in the Azure portal. `_public_base_url()` derives `scheme://host` from
`MS_REDIRECT_URI` and is used by `_frontend_redirect()`. The dev domain is stable (tied to
REPL_ID). Production needs its own `MS_REDIRECT_URI` (production env) + matching Azure entry.

**Why:** `request.base_url` only reflects the public host if the proxy forwards trusted
X-Forwarded-* headers and uvicorn honors them; here it doesn't, so the explicit env var is
the canonical source for the public origin.
