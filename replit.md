# DW Financeiro - Sistema de Gestao de Data Warehouse para Eventos

## Overview
The DW Financeiro system is a web-based platform serving as a "Single Source of Truth" for event management data. Its core purpose is to deliver consolidated insights, particularly for event-related metrics and marketing performance, to enable data-driven decision-making. Key capabilities include secure authentication, comprehensive master data management, and dynamic marketing performance dashboards. The Marketing Performance (ISC Dashboard) specifically monitors event sales, such as race registrations, to identify high and low-performing events, inform strategic planning, and enhance market potential for event organizers.

## User Preferences
I want iterative development.
Ask before making major changes.
I prefer detailed explanations.
Do not make changes to the folder `Z`.
Do not make changes to the file `Y`.

## System Architecture

### UI/UX Decisions
The frontend is built with React, TypeScript, and Tailwind CSS, providing a modern and consistent user experience. It features an animated background, gradient headers, contemporary card designs, and supports both light and dark themes. UI animations are handled by `framer-motion`, and 3D elements on the login page are rendered using `@react-three/fiber`.

### Technical Implementations
- **Backend:** Python with FastAPI for high performance and asynchronous operations.
- **Frontend:** React, TypeScript, and Tailwind CSS.
- **PWA (Progressive Web App):** The application is installable on Android and iOS/iPadOS, configured via `vite-plugin-pwa` with specific caching strategies.
- **Databases:** PostgreSQL is the primary database, complemented by MySQL for external athlete data accessed via SSH Tunnel.
- **ORM:** SQLAlchemy manages database interactions.
- **Authentication:** JWT (PyJWT) provides secure session management and API route protection.
- **Access Management:** A unified `PerfilAcesso` system offers granular CRUD and field-level permissions, alongside dynamic sidebar filtering.
- **Virtual Assistant (Nori):** An AI-powered assistant utilizing OpenAI GPT-4o-mini for NLP, Web Speech API for speech-to-text, and SpeechSynthesis API for text-to-speech in Brazilian Portuguese.
- **Data Consolidation:** Consolidates inscription data from Ativo and Magento based on SKU, ensuring data consistency and providing resync capabilities.
- **Performance Optimizations:** Includes FastAPI for asynchronous operations, SARGable SQL queries, N+1 query resolution, explicit connection pool configurations, and production-scale warmup optimizations.
- **Local PG Pool Resilience:** Local Postgres pool sized 25/50. `db_retry.magento_run` calls `database.release_local_db_connections()` before each Magento attempt to release idle local PG sessions held by the request thread (via `get_db()`'s thread-local registry). Prevents pool exhaustion when Magento queries time out and unrelated endpoints (e.g. `/api/admin/sku-mappings/grupos`) returning 500 due to `QueuePool limit reached`. Sessions with pending uncommitted writes are skipped; SQLAlchemy 2.x lazily reacquires on next ORM op.
- **Hybrid Data Model (Snapshots):** Stores daily sales data in PostgreSQL for historical reference, while real-time data for the current day is fetched directly. Historical curves are pre-calculated and stored as snapshots.
- **Magento Connection Resilience:** All Magento queries incorporate centralized retry logic for transient errors and are tuned for SSH tunnel stability. The per-bundle margem snapshot (`MargemBundleRevSnapshot`, populated by the 04h job) holds both `receita_liquida` AND `qtd_inscricoes` and serves as a piso de segurança: it is read first (≤25h) before any live Magento count/revenue, and live results that come back lower than the snapshot are treated as partial responses (snapshot wins). UPSERTs in this snapshot use `GREATEST()` so partial syncs can never lower a previously known value. The event-detail `currentSales` alignment with the kit table only raises the value — never lowers it — so connection issues no longer cause the displayed total to flicker downward.
- **Freeze of Finalized Events:** Sync jobs skip events whose `data_evento + EVENTO_FREEZE_AFTER_DAYS` is past (default 30 days, env-configurable). Snapshots already persisted continue to be read normally; only the writes stop. This shrinks the Magento window each night, lowering the chance of partial responses, and removes pointless work on data that no longer changes. Applied to: `sincronizar_margem_bundle_rev_batch` (filters bundles via `KitConfig.id_evento` → `CadastroEvento.id_evento_magento`) and `snapshot_diario_batch` (filters grupos via DimProjeto + CadastroEvento union). Bundles/grupos with no cadastro mapping or null date stay in the sync (conservative — can't classify without a date). `sincronizar_hoje_batch` already filtered by Live/Hybrid; warmup already filtered to active + last 14 days.
- **Persistent Multi-Tier Cache with SWR:** A `SmartCache` module uses in-memory and PostgreSQL for persistent caching with year-aware TTL, atomic UPSERTs, background refresh, and an optimized warm-up pipeline.
- **Controle Diário com Fallback Robusto (Vitória fix, Maio/2026):** O endpoint `/marketing/eventos/{evento_id}/curva-snapshot` (aba "Controle Diário") deixou de ler `get_curva_historica_snapshot` direto e passou a usar `_resolve_hist_pattern` (cadeia completa: override → próprio → circuito+cidade → circuito → regional → linear). Adicionado check pós-resolve `_pattern_is_saturated` (pct≥0.95 em D-≥30) que descarta padrões resolvidos mas saturados — caso de Vitória, onde TODAS as curvas 2025 (próprio, override Outono, todas regionais ES) gravam pct=1.0 em qualquer d_minus (bug histórico da consolidação dessas curvas pequenas). Quando o padrão é nulo/saturado E há `data_evento`, fabrica curva linear `pct(d) = max(0, 1 - d/d_open)` distribuindo a meta uniformemente sobre `(dias até evento + 90)` dias. Garante que "Meta Dia" nunca fique zerada quando há `sales_goal` e data definida. Resposta inclui `tipo_curva`, `fonte_curva` e `fabricated_linear` para diagnóstico.
- **Job Scheduler Hardening (Maio/2026):** (1) Consolidação diária movida de 04h→02h BRT (`cache.py` `_schedule_snapshot_consolidation` agora usa `hour=2`); job_name `consolidacao_diaria_04h` mantido por compatibilidade com queries históricas do `SyncEventLog`. (2) Alerta HIGH `SYNC_PARTIAL_HIGH` disparado pelo `sincronizar_hoje_batch` quando `(parcial+falha)/total > 20%` via `health_alert_service.log_and_alert` (throttle 300s) — indica instabilidade Magento/Ativo onde snapshots viram piso. (3) Nova tabela `job_run_health` (modelo `JobRunHealth`) populada ao final de `snapshot_diario_batch` e `sincronizar_hoje_batch` com `started_at, finished_at, duration_ms, grupos_total/ok/parcial/falha/pulado, status, extra` — permite análise de tendência (ex.: "Magento piorou nas últimas 3 noites?"). Helper centralizado em `backend/app/services/job_health_service.py`.

### Feature Specifications
- **Authentication:** Standard email/password login with profile management.
- **Master Data Management:** CRUD operations for Cost Centers, Athlete Categories, and Users.
- **Consolidated Dashboard:** An interactive, globally filterable dashboard displaying KPIs, charts, and tables.
- **Marketing Performance (ISC Dashboard):** Displays Commercial Health Index (ISC) based on Acceleration Index, D-% Curve, and rolling 14-day sales average. Includes detailed event pages with a dynamic **Playbook**.
- **Pricing Analysis:** Analyzes pricing strategies using various metrics and elasticity simulation.
- **External Athlete Data:** Real-time fetching and in-memory caching of athlete data from external MySQL.
- **Commercial Actions Timeline:** Manages and tracks the impact of commercial actions.
- **Sales Averages Analysis:** Provides daily sales averages from Ativo + Magento.
- **Year-over-Year Comparison:** Compares cumulative inscriptions and revenue by "days before event."
- **Historical Benchmark Curve:** Generates expected sales curves using previous year's sales distribution with an intelligent fallback chain.
- **Margem por Tipo de Kit:** Modal providing a per-kit breakdown of sales, revenue, and margins.
- **Configurable Registration Close Date:** Defines registration close days for D- calculations.
- **Normalized Sales Curve:** Detects and redistributes campaign outliers using a rolling 7-day median.
- **SKU Mapping & Event Groups:** Unified administration for SKU mappings and event groups with automated cache invalidation.
- **Cycling Scenarios (Cenários de Ciclismo):** Supports three distinct sales scenarios for "Ciclismo" events with dedicated UI for configuration and analysis.
- **Kit Config (Mapeamento de Kits):** Admin page for configuring kit multipliers and marking a "Kit Básico" per event, sourcing kits from both Magento and Ativo.
- **Strategic Insights Dashboard:** Calculates insights including Acceleration Index, Daily Pace, Closing Projection, and Category Mix.
- **Marketing Settings Persistence:** API for persisting key-value JSON marketing settings, used in ISC calculations.
- **Cotação & Importação (Quote & Import):** FOB quote registration page with manual inputs to calculate nationalized and BRL values.
- **Manual do Sistema:** Built-in documentation/knowledge base page accessible to all authenticated users.
- **Projeção de Inscritos por Eventos e Áreas:** Allows users to input projected subscriber counts per event across predefined areas, with admin assignment, audit history, and consolidated views, supporting breakdowns by Kit and Client.
- **Pontos de Corte (Cutoff Rules) para Projeção:** Configurable D-day thresholds that trigger in-app pendency indicators for Projeção Inscritos.
- **Cortes customizados por (evento, área):** Allows custom cutoff dates per event/area, overriding global D-N rules.

## External Dependencies
- **PostgreSQL:** Primary application database.
- **MySQL:** External athlete data storage.
- **OpenAI:** GPT-4o-mini for Nori Virtual Assistant.
- **Web Speech API:** Used for Nori's speech-to-text functionality.
- **SpeechSynthesis API:** Used for Nori's text-to-speech functionality.
- **Paramiko:** Used for establishing secure SSH Tunnel connections.