# Threat Model

## Project Overview

DW Financeiro is a web application for internal event and marketing analytics, master-data management, operational projections, and monitoring. The production stack is a FastAPI backend in `backend/`, a React/Vite frontend in `frontend/`, PostgreSQL as the primary datastore, and external MySQL sources reached through SSH tunneling for Ativo/Magento data. Users authenticate with email/password and receive JWT bearer tokens.

This threat model focuses on production-reachable code paths only. Dev-only artifacts, local caches, and experimental sandbox behavior are out of scope unless production reachability is demonstrated. TLS is provided by the platform in production.

## Assets

- **User accounts and sessions** — user identities, password hashes, JWT bearer tokens, and profile metadata. Compromise enables impersonation and access to internal dashboards and admin tools.
- **Business data and operational planning data** — event registrations, pricing, projections, commercial actions, benchmark curves, and health-monitoring records. Unauthorized modification can distort operational decisions and downstream reporting.
- **Administrative configuration** — SKU mappings, event groups, kit mappings, permissions, marketing settings, cache/snapshot control paths, and other operational toggles. These are high-impact because they shape cross-system joins and the data shown to all users.
- **AI assistant outputs and AI spend** — Nori chat responses, stored insights, insight status/history, and OpenAI-backed analysis jobs. Unauthorized access can disclose internal recommendations, while unrestricted triggering can consume paid model quota.
- **Application secrets and integration credentials** — PostgreSQL connection string, JWT signing secret, OpenAI key, SSH credentials, and MySQL credentials for external systems.
- **Externally sourced data** — Ativo and Magento data pulled through the backend. The app must treat remote systems and their responses as separate trust domains.

## Trust Boundaries

- **Browser to API** — all frontend input is untrusted until validated server-side. Authentication and authorization must be enforced on every protected endpoint regardless of frontend route gating.
- **API to PostgreSQL** — the backend has broad write access to application data. Injection or broken authorization at the API layer can directly alter core business records.
- **API to external MySQL via SSH** — the backend bridges into external systems and converts remote results into application responses and snapshots. Query safety, timeouts, and least privilege matter here.
- **Authenticated user to privileged operator/admin surfaces** — the app contains monitoring, configuration, mapping, and snapshot-management features that should not be available to ordinary authenticated users.
- **Authenticated user to permission-scoped module surfaces** — marketing, Nori, and master-data modules are hidden in the frontend based on `PerfilAcesso`, but those menu decisions are not a security boundary. Backend routes must enforce equivalent permissions server-side.
- **Public to authenticated resources** — login is public; most other business endpoints are authenticated. Any resource intended only for authenticated or privileged users must not rely solely on client-side navigation filtering.

## Scan Anchors

- **Production entry points:** `backend/main.py`, `backend/app/api/routes/*.py`, `frontend/src/main.tsx`, `frontend/src/App.tsx`
- **Highest-risk backend areas:** `backend/app/core/security.py`, `backend/app/api/routes/auth.py`, `backend/app/api/routes/marketing.py`, `backend/app/api/routes/nori.py`, `backend/app/api/routes/sku_mappings.py`, `backend/app/api/routes/cadastros.py`, `backend/app/api/routes/centros_custo.py`, `backend/app/api/routes/categorias_atletas.py`, `backend/app/api/routes/admin.py`, `backend/app/api/routes/profile.py`
- **Privileged/frontend-gated surfaces:** `frontend/src/context/PermissionContext.tsx`, `frontend/src/components/common/Layout.tsx`, admin and configuration routes under `/admin/*`, `/marketing`, `/marketing/configuracoes`, `/cadastros/eventos`, `/cadastros/categorias-atletas`, `/nori`, `/projecao-inscritos`
- **Usually ignore unless proven production-reachable:** `frontend/node_modules`, build artifacts, local caches, attached reference assets, and mock/dev-only tooling

## Threat Categories

### Spoofing

Users authenticate with email/password and a JWT bearer token. The system must verify token signatures and expiry on every protected request, reject inactive users, and ensure the signing secret is present and strong in production. Any route that trusts only the presence of a frontend session without backend token validation would permit impersonation.

### Tampering

This project exposes many write paths that update projections, marketing settings, event definitions, mappings, snapshots, and operational metadata. These changes have business-wide effects, so the API must enforce server-side permissions on every write endpoint. The frontend's permission-aware navigation is not a security boundary; any authenticated user can call backend routes directly.

### Information Disclosure

The application stores and serves internal operational data, user metadata, and monitoring events. API responses must be scoped to authenticated users and privileged roles as appropriate, and must not leak sensitive records through admin endpoints, debug/status routes, or overly broad list APIs. Error handling and logs must avoid exposing secrets, tokens, or raw integration failures to users.

### Denial of Service

Several endpoints trigger expensive computations, cache refreshes, backfills, snapshot generation, or remote database access over SSH. The system must ensure that expensive refresh or sync operations are restricted to authorized operators and protected from abuse, since repeated triggering could exhaust DB pools, worker threads, or external integration capacity.

Marketing diagnostic/refresh endpoints and AI-backed helper endpoints deserve special attention here because they can turn an ordinary authenticated account into a trigger for heavy upstream queries or paid model usage if module permissions are not enforced server-side.

### Elevation of Privilege

This is the highest-risk category for the current architecture. The application implements granular `PerfilAcesso` permissions and presents many admin/configuration pages conditionally in the frontend, so backend routes must enforce equivalent permission checks. Any endpoint under admin/configuration/monitoring/master-data areas that accepts a generic authenticated user instead of the required permission creates a direct privilege-escalation path.
