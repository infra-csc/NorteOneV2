# DW Financeiro - Sistema de Gestao de Data Warehouse para Eventos

## Overview
The DW Financeiro system is a web-based platform designed as a "Single Source of Truth" for event management data. Its primary purpose is to provide consolidated insights, particularly for event-related metrics and marketing performance, to facilitate data-driven decision-making. Key capabilities include secure authentication, robust master data management, and dynamic marketing performance dashboards. The Marketing Performance (ISC Dashboard) monitors event sales, such as race registrations, to identify strong or weak events, inform strategic planning, and enhance market potential for event organizers.

## User Preferences
I want iterative development.
Ask before making major changes.
I prefer detailed explanations.
Do not make changes to the folder `Z`.
Do not make changes to the file `Y`.

## System Architecture

### UI/UX Decisions
The frontend utilizes React, TypeScript, and Tailwind CSS for a modern and consistent user experience, featuring an animated background, gradient headers, contemporary card designs, and support for both light and dark themes. UI animations are managed with `framer-motion`, and 3D elements on the login page are rendered using `@react-three/fiber`.

### Technical Implementations
- **Backend:** Python with FastAPI for high performance and asynchronous operations.
- **Frontend:** React, TypeScript, and Tailwind CSS.
- **PWA (Progressive Web App):** App is installable on Android (Chrome `beforeinstallprompt`) and iOS/iPadOS (manual "Adicionar à Tela de Início" hint shown after a delay; iPadOS 13+ detected via `navigator.maxTouchPoints` since UA reports as Macintosh). Configured via `vite-plugin-pwa` in `frontend/vite.config.ts` (generateSW mode). Runtime cache is intentionally narrow: only GET requests to `/api/marketing/*` (excluding `refresh`/`sync`/`configuracoes`) are cached with NetworkFirst — auth, admin, profile, kit-config etc. are never cached to avoid leaking session data between users on shared devices. Images use StaleWhileRevalidate, fonts use CacheFirst. Manifest, theme color (`#111827`), maskable + apple-touch icons live in `frontend/public/`. Service worker registration, update prompt, and install prompt UI live in `frontend/src/pwa/` (`usePWA.ts` + `PWAManager.tsx`, mounted from `App.tsx`). iOS safe-area insets and reduced body overscroll in `frontend/src/index.css`. The `Layout` sidebar auto-closes on mobile route changes, shows a backdrop overlay when open, and uses a refcount-style body scroll lock that re-evaluates on viewport resize. **Note:** `package.json` no longer pins `brace-expansion` — natural resolution lets `minimatch@10` (workbox-build's chain) get v5.x while legacy `minimatch@3` (ESLint chain) keeps v1.x. Pinning `brace-expansion` globally either way breaks one of the toolchains.
- **Databases:** PostgreSQL serves as the primary database, complemented by MySQL for external athlete data accessed via SSH Tunnel.
- **ORM:** SQLAlchemy is used for database interactions.
- **Authentication:** JWT (PyJWT) ensures secure session management and API route protection.
- **Access Management:** A unified `PerfilAcesso` system provides granular CRUD and field-level permissions, alongside dynamic sidebar filtering.
- **Dynamic Content:** Supports dynamic distance and product kit options.
- **Charting:** Recharts library for interactive data visualizations.
- **SSH Tunneling:** Paramiko library secures connections to external MySQL.
- **Security:** Implements CORS, secure credential storage, sanitized error messages, and parameterized SQL queries.
- **Virtual Assistant (Nori):** An AI-powered assistant leveraging OpenAI GPT-4o-mini for NLP, Web Speech API for speech-to-text, and SpeechSynthesis API for text-to-speech in Brazilian Portuguese.
- **Data Consolidation:** Consolidates inscription data from Ativo and Magento based on SKU, ensuring data consistency and providing resync capabilities.
- **Double-Submit Protection:** Mechanisms are in place on both frontend and backend to prevent duplicate form submissions.
- **User Activity Monitoring:** Tracks user activity with an admin page displaying online status and activity logs.
- **Performance Optimizations:** Includes FastAPI for asynchronous operations, AbortController for frontend requests, SARGable SQL queries, N+1 query resolution, explicit connection pool configurations, and production-scale warmup optimizations.
- **Hybrid Data Model (Snapshots):** Daily sales data is stored in PostgreSQL for historical reference, while real-time data for the current day is fetched directly from Ativo/Magento. Historical curves are pre-calculated and stored as snapshots.
- **Persistent Multi-Tier Cache with SWR:** A `SmartCache` module uses in-memory and PostgreSQL for persistent caching, featuring year-aware TTL, atomic UPSERTs, background refresh, and a 4-step optimized warm-up pipeline with resilience, utilizing a Stale-While-Revalidate (SWR) mechanism.
- **ConnectionAlert:** A reusable frontend component provides diagnostics and retry functionality for database connection issues.

### Feature Specifications
- **Authentication:** Standard email/password login with profile management (password change, photo upload).
- **Master Data Management:** CRUD operations for Cost Centers, Athlete Categories, and Users; "Projetos" are integrated into "Eventos."
- **Consolidated Dashboard:** An interactive, globally filterable dashboard displaying KPIs, charts, and tables.
- **Marketing Performance (ISC Dashboard):** Displays Commercial Health Index (ISC) based on Acceleration Index, D-% Curve, and rolling 14-day sales average. Includes detailed event pages with multiple tabs (Dashboard, Simulador, Precificação, Projeção, Complementares) and a dynamic **Playbook** based on event stage and ISC state. Strategic cutoff dates are anticipated to the preceding Friday if they fall on a weekend.
- **Pricing Analysis:** Analyzes pricing strategies using metrics like "Rolling Index," "IED," "IA," "Pace de Segurança," and "FEM," with elasticity simulation.
- **External Athlete Data:** Real-time fetching and in-memory caching of athlete data from external MySQL.
- **Commercial Actions Timeline:** Manages and tracks the impact of commercial actions.
- **Sales Averages Analysis:** Provides daily sales averages from Ativo + Magento.
- **Year-over-Year Comparison:** Compares cumulative inscriptions and revenue by "days before event."
- **Historical Benchmark Curve:** Generates expected sales curves using previous year's sales distribution with an intelligent fallback chain (manual override, circuit+city, circuit average, regional, linear).
- **ISC Data Consistency:** Ensures all ISC components derive current sales data consistently, including today's partial data.
- **Error Boundary:** EventDetail route is wrapped in an ErrorBoundary for graceful handling of render crashes.
- **Margem por Tipo de Kit:** "Composição da Margem" modal provides a per-kit breakdown of sales, revenue, and margins, based on kit costs and user-configured mappings.
- **Force-Refresh Cooldown:** "Atualizar Dados" button on event detail pages has a 10-minute cooldown, clearing in-memory cache if snapshot is recent.
- **Order Status Filter:** Aligned order status filters for Ativo and Magento queries.
- **Canal-based Inscription Filtering (Controle Diário):** Implements canal-based logic for daily sales fetching, distinguishing 'Site', 'Cortesia' (by coupon classification), and 'Grupos/B2B'.
- **Configurable Registration Close Date:** `dias_encerramento_inscricao` field on `CadastroEvento` defines registration close days for D- calculations.
- **Enriched Daily Sales API:** Each daily sales entry includes `dMinus`, `curvaAnoAnterior`, `dif`, `atingimentoAcumulado`, `atingimentoDiario`, `normalizedSales`, and `cumulativeNormalized`.
- **Normalized Sales Curve:** Detects and redistributes campaign outliers using a rolling 7-day median, with a toggle to visualize the normalized curve.
- **SKU Mapping & Event Groups:** Unified administration for SKU mappings and event groups, with automated cache invalidation. SKU mappings include an optional `data_evento` field for D-minus curves.
- **Cycling Scenarios (Cenários de Ciclismo):** For "Ciclismo" events, supports three distinct sales scenarios ("Inscrição Participação," "Kit sem Bike," "Kit com Bike") with dedicated UI for configuration and analysis.
- **Kit Config (Mapeamento de Kits):** Admin page (`/admin/kit-config`) for configuring kit multipliers and marking a "Kit Básico" per event. Kits are sourced from two queries: `MAGENTO_KITS_QUERY` (Magento MySQL) for events that exist there, and `ATIVO_KITS_QUERY` (Ativo MySQL — combo + modalidade simples, lote vigente) to enrich Ativo-only events with `price`/`special_price`/`lote_atual`/`tipo_categoria`. Ativo rows match by `(id_evento, normalized nome_kit)` against `CadastroKitProduto` and keep their synthetic `bundle_entity_id = -kp.id` so existing KitConfig rows survive. The Dash ISC ticket map (`_fetch_ticket_atual_map` in `marketing.py`) consumes both queries; Magento always wins when an event exists in both bases — Ativo only contributes the ticket for events that are not in Magento.
- **Cache Poisoning Protection:** Validates cached results for comparative curves, discarding invalid or empty data.
- **Strategic Insights Dashboard:** Calculates insights including Acceleration Index, Daily Pace, Closing Projection, and Category Mix.
- **Marketing Settings Persistence:** API for persisting key-value JSON marketing settings, used in ISC calculations.
- **Event Detail Layout:** Redesigned for improved readability with D- bar, ISC gauge, sales indicators, and a "Controle Diário" tab.
- **Cotação & Importação (Quote & Import):** FOB quote registration page with manual inputs for Índice de Importação, BEC, and Cotação (USD/BRL). Calculates Nacionalizado as `FOB × Índice × Cotação + (BEC × FOB × Cotação)` and Valor BRL as `FOB × Cotação`. No external exchange rate API dependency on frontend.
- **Manual do Sistema:** Built-in documentation/knowledge base page (`/manual`) accessible to all authenticated users, with search and navigation.
- **Projeção de Inscritos por Eventos e Áreas:** Allows users to input projected subscriber counts per event across predefined areas. Includes admin assignment of users to areas, full audit history, and a consolidated view of real and projected subscribers.
- **Pontos de Corte (Cutoff Rules) para Projeção:** Configurable D-day thresholds (default seeded D-45 "Primeiro alerta" and D-15 "Alerta final") that trigger in-app pendência indicators on Projeção Inscritos. Backend model `ProjecaoCutoffRule` (table `projecao_cutoff_rule`, unique `dias_antes_evento`) with admin-only CRUD endpoints under `/api/projecao/cutoff-rules`; `GET /api/projecao/pendencias` returns active events whose `data_evento - today` is within the largest active cutoff window and that still lack projeção for areas the requesting user can edit (admins see all areas, others limited to `area_projecao_usuario` assignments). Frontend shows an animated red badge on the sidebar "Projeção Inscritos" item plus a header chip (3-min polling), a dismissible banner above the events master table that auto-resets when the pendência set changes, a per-row "Pendente • D-{n}" chip with red/amber tint based on urgency (≤15 days = red), and a "Pontos de Corte" admin section inside the Configurações tab for CRUD.

## External Dependencies
- **PostgreSQL:** Primary application database.
- **MySQL:** External athlete data storage.
- **OpenAI:** GPT-4o-mini for Nori Virtual Assistant.
- **Web Speech API:** Used for Nori's speech-to-text functionality.
- **SpeechSynthesis API:** Used for Nori's text-to-speech functionality.
- **Paramiko:** Used for establishing secure SSH Tunnel connections.