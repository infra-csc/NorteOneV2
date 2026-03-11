# DW Financeiro - Sistema de Gestao de Data Warehouse para Eventos

## Overview
The DW Financeiro system is a web-based platform serving as a "Single Source of Truth" for event management data. It provides consolidated insights, particularly for event-related metrics and marketing performance, to facilitate data-driven decision-making. Key capabilities include secure authentication, robust master data management, and dynamic marketing performance dashboards. The Marketing Performance (ISC Dashboard) monitors event sales, especially race registrations, to identify strong or weak events and inform strategic planning, ultimately enhancing strategic planning and market potential for event organizers.

## User Preferences
I want iterative development.
Ask before making major changes.
I prefer detailed explanations.
Do not make changes to the folder `Z`.
Do not make changes to the file `Y`.

## System Architecture

### UI/UX Decisions
The frontend uses React, TypeScript, and Tailwind CSS for a modern, consistent user experience, featuring an animated background, gradient headers, contemporary card designs, and support for both light and dark themes. `framer-motion` is used for UI animations, and `@react-three/fiber` for 3D elements on the login page.

### Technical Implementations
- **Backend:** Python with FastAPI.
- **Frontend:** React, TypeScript, and Tailwind CSS.
- **Databases:** PostgreSQL (primary), MySQL (for external athlete data via SSH Tunnel).
- **ORM:** SQLAlchemy.
- **Authentication:** JWT (PyJWT) for secure session management and `get_current_user` dependency for API route protection.
- **Access Management:** Unified `PerfilAcesso` system with `is_admin` flag, granular CRUD permissions per module, and field-level permissions. Dynamic sidebar filtering based on user permissions.
- **Dynamic Content:** Distance management via `DistanciaOpcao` and dynamic `Kit Produtos` options.
- **Charting:** Recharts library for interactive data visualization.
- **SSH Tunneling:** Paramiko library manages secure SSH connections to external MySQL.
- **Security:** CORS, secure credential storage, sanitized error messages, parameterized SQL queries.
- **Virtual Assistant (Nori):** AI-powered assistant using OpenAI GPT-4o-mini for NLP, Web Speech API for speech-to-text, and SpeechSynthesis API for text-to-speech in Brazilian Portuguese.
- **Data Consolidation:** Consolidates inscription data from Ativo and Magento using SKU, ensuring data consistency between `cadastro_evento` and `dim_projeto`. Includes a resync endpoint and startup sync for data integrity.
- **Double-Submit Protection:** Frontend and backend mechanisms to prevent duplicate form submissions.
- **User Activity Monitoring:** Tracks user activity (`last_activity`) with an admin monitoring page displaying online status and activity logs.
- **Performance Optimizations:** FastAPI for asynchronous operations, AbortController for frontend requests, SARGable SQL queries, N+1 query resolution, and explicit connection pool configurations.
- **Hybrid Data Model (Snapshots):** Daily sales data is stored in PostgreSQL `vendas_diaria_snapshot` table for historical data (up to yesterday). Real-time queries to Ativo/Magento are restricted to today's data only. Historical curves from the previous year are pre-calculated and stored in `curva_historica_snapshot` table. Snapshot consolidation runs daily at 06:00 BRT (before cache warmup at 07:00). Admin endpoints: `POST /api/admin/snapshots/consolidar` (trigger manual), `POST /api/admin/snapshots/backfill` (populate historical data), `GET /api/admin/snapshots/status` (check status). Service: `backend/app/services/snapshot_service.py`. Models: `backend/app/models/vendas_snapshot.py`.
- **Persistent Multi-Tier Cache with SWR:** `SmartCache` module utilizes in-memory and PostgreSQL `cache_entries` table for persistent caching. Features year-aware TTL (2h current year, permanent for historical), `MAX_STALE_AGE` (8h) to prevent stale data from being served indefinitely, atomic UPSERTs, background refresh, and a 4-step optimized warm-up pipeline with resilience for external data source failures. `invalidate()` and `invalidate_all()` clean both in-memory and PostgreSQL persistent entries. `warm_from_db()` validates entry age on startup and skips expired non-historical entries. **Stale-While-Revalidate (SWR):** `get_or_revalidate()` method returns stale data immediately when TTL expires (but within MAX_STALE_AGE) and triggers background refresh via `_swr_executor` thread pool (3 workers). Deduplicates concurrent refreshes via `_swr_in_flight` set. Applied to all ISC marketing endpoints (eventos, event detail, curvas, médias, insights). Backend sends `X-Data-Stale` response header; frontend shows "atualizando..." indicator and auto-refetches after 30s when stale. Warmup Phase 3 now populates the default dashboard cache key (`{ano}_all_all_`).
- **Production-Scale Warmup Optimization:** Pre-fetches ALL SkuMappings, DimProjetos, and CadastroEventos in 3 bulk queries during Phase 1, eliminating ~3,200 redundant per-event DB queries for 200 events. Uses `_wq_*` helper functions that check `_is_warmup_thread()` to use pre-fetched data during warmup and fall back to DB for normal requests. Event tiering: Tier 1 (d_minus ≤ 60) gets full warmup (details + curvas + médias + insights), Tier 2 (d_minus > 60) gets details only. `calculate_action_impact` uses pre-fetched daily sales during warmup instead of SSH queries, eliminating ~600 SSH queries per warmup cycle. Metadata pre-fetch cache is cleared after warmup to free memory. **Phase 3 Optimization:** Phase 3 (`get_marketing_events`) no longer re-fetches ISC pricing data from external DBs — uses ISC cache from Phase 1. `daily_sales_cache` is pre-populated from warmup data (ext_id→SKU conversion) before clearing warmup caches. Historical patterns (`_hist_pattern_cache`) are cached in-memory across calls so the second `get_marketing_events` call (all status) reuses patterns from the first. ISC Magento query uses `INNER JOIN` on EAV subqueries with `GROUP BY`, `NOT REGEXP '-[0-9]'` instead of 17 `NOT LIKE` clauses, and `BETWEEN MAKEDATE(...)` for date filtering. **Query Alignment:** All Magento daily queries (grouped, non-grouped, today) use `INNER JOIN catalog_product_entity_varchar ... AND store_id = 0` (prevents EAV duplicates), `soi.price > 0` (excludes free items), and persona subquery uses `MAX(price) GROUP BY parent_item_id` (prevents row duplication). ISC Ativo query handles NULL `ds_categoria` with `(IS NULL OR NOT LIKE)`. `inscricoes_consolidado.py` EAV subqueries use `store_id = 0` instead of `MIN(value) GROUP BY`. Snapshot consolidation does full refresh (delete + re-insert) instead of incremental, ensuring stale snapshot data is cleared.
- **ConnectionAlert:** Reusable frontend component for displaying database connection issues with error classification, source-specific diagnostics, and retry functionality.

### Feature Specifications
- **Authentication:** Standard email/password login.
- **Master Data Management:** CRUD operations for Cost Centers, Athlete Categories, and Users; "Projetos" integrated into "Eventos".
- **Consolidated Dashboard:** Interactive dashboard with KPIs, charts, tables, and insights, globally filterable.
- **Marketing Performance (ISC Dashboard):** Displays Commercial Health Index (ISC) based on Acceleration Index, D-% Curve, and rolling 14-day sales average. Features detailed event pages with multiple tabs (Dashboard, Simulador, Precificação, Projeção, Complementares) including comparative curves and insights. ISC uses a `desvio+cap` model for calculation.
- **Pricing Analysis:** Analyzes pricing strategies with metrics like "Rolling Index," "IED," "IA," "Pace de Segurança," and "FEM," including elasticity simulation.
- **External Athlete Data:** Real-time fetching and in-memory caching of athlete data from external MySQL.
- **Commercial Actions Timeline:** Manages and tracks the impact of commercial actions.
- **Sales Averages Analysis:** Provides daily sales averages from Ativo + Magento.
- **Year-over-Year Comparison:** Compares cumulative inscriptions and revenue by "days before event."
- **Historical Benchmark Curve:** Uses previous year's sales distribution for expected curve generation.
- **ISC Data Consistency:** All 3 ISC components (Curva D-%, IA 7/30, Rolling 14d) derive `current_sales` from `daily_sales_dict` (sum up to today), not from the ISC pricing query. Daily sales queries use `< CURDATE() + INTERVAL 1 DAY` to include today's partial data. Main table `currentSales` sums through `date.today()`.
- **Error Boundary:** EventDetail route is wrapped in an ErrorBoundary component (`frontend/src/components/common/ErrorBoundary.tsx`) that catches React render crashes and shows a fallback error message instead of a blank screen. Null-safety guards protect `event.date`, `event.isc`, and `event.iscComponents` accesses.
- **Force-Refresh Cooldown:** The "Atualizar Dados" button on event detail pages has a 10-minute cooldown. If the snapshot was rebuilt within the last 10 minutes (`VendasDiariaSnapshot.updated_at`), the button only clears in-memory cache without re-querying external databases. Applied to both grouped and standalone event paths.
- **Order Status Filter:** Ativo queries use `id_pedido_status IN (1, 2)` which includes both pending (1) and confirmed (2) orders. Magento uses `status IN ('processing', 'complete', 'approved', ...)`. This may cause discrepancies vs external controls that only count confirmed orders.
- **Ativo Query Filters (aligned with user reference query):** All Ativo queries use: (1) `f.en_cupom_classificacao IS NULL OR f.en_cupom_classificacao NOT IN ('Funcionário', 'Cortesia Faturada', 'Grupos', 'Coligados', 'Eventos Terceiros')` — excludes specific coupon classifications by name; (2) `h.ds_categoria NOT LIKE '%Grup%' AND h.ds_categoria NOT LIKE '%ortesia%'` — excludes both Grupo and Cortesia categories; (3) `b.id_campanha_salesforce IS NULL OR b.id_campanha_salesforce NOT LIKE '701d0000000%'` — includes events with NULL Salesforce campaign. These filters are applied consistently across ISC consolidated, daily grouped, daily standalone, today, monthly, and category queries.
- **Configurable Registration Close Date:** `dias_encerramento_inscricao` field on `CadastroEvento` (default=2) defines how many days before the event registrations close. All D- calculations use `data_evento - dias_encerramento` as the reference point instead of `data_evento` directly. The field is editable in the "Info Geral" tab of the Cadastro form.
- **Enriched Daily Sales API:** Each daily entry in the sales response includes: `dMinus` (D- at that date), `curvaAnoAnterior` (% from previous year curve), `dif` (difference vs expected), `atingimentoAcumulado` (cumulative % deviation), `atingimentoDiario` (daily % deviation). These map directly to the external spreadsheet columns for validation.
- **SKU Mapping & Event Groups:** Unified administration for SKU mappings and event groups. SKU mappings include an optional `data_evento` (Date) field that allows admins to manually specify the event date. This date takes priority over `dim_projeto` lookups when calculating historical D-minus curves, eliminating the need to create retroactive events in the Cadastro system. When mappings are created, updated, or deleted, the curva_comparativa cache for the affected event group (and adjacent years) is automatically invalidated via `_invalidate_curva_cache` in `sku_mappings.py`.
- **Cache Poisoning Protection:** The curva comparativa endpoint validates cached results before serving them — empty data arrays in cache are discarded and the cache entry is invalidated, forcing recalculation. The `_find_data_evento` function performs cross-validation: when an estimated date (from dim_projeto year adjustment) differs by >60 days from a `data_evento` in sku_mappings, it prefers the sku_mappings date and logs a warning.
- **Strategic Insights Dashboard:** Calculates insights from Ativo+Magento data, including Acceleration Index, Daily Pace, Closing Projection, and Category Mix.
- **Marketing Settings Persistence:** API for persisting marketing settings (key-value JSON), actively used in ISC calculations.
- **Event Detail Layout:** Redesigned layout for improved readability, including D- bar, ISC gauge, and sales indicators, with instant header rendering during data loading. Includes a "Controle Diário" tab with a spreadsheet-style table (`DailySalesTable.tsx`) showing all daily sales columns matching the external control spreadsheet (Data, D-, Vendas, Acumulado, % Curva Ant., Meta Dia, Meta Acum., Dif, Ating. Acum., Ating. Dia), with sort toggle and CSV export.
- **Cotação & Importação (Quote & Import):** System for managing product quotes and import costs, including suppliers, exchange rates, and event linking, with a dashboard and access control.
- **Manual do Sistema:** Built-in documentation/knowledge base page at `/manual`, accessible to all authenticated users via the sidebar (BookOpen icon). Contains 12 sections covering all system features: Visão Geral, Dashboard Principal, Mapeamento de SKU, Dashboard ISC, Configurações de Marketing, Comparativo de Eventos, Gestão de Usuários, Nori (Assistente IA), Cotações, Centros de Custo, Categorias de Atletas, Dados Consolidados. Features include section search, responsive sidebar navigation, next/previous navigation, and support for dark/light themes. Component: `frontend/src/pages/manual/ManualSistema.tsx`.

## External Dependencies
- **PostgreSQL:** Primary application database.
- **MySQL:** External athlete data storage.
- **OpenAI:** GPT-4o-mini for Nori Virtual Assistant.
- **Web Speech API:** Nori's speech-to-text.
- **SpeechSynthesis API:** Nori's text-to-speech.
- **Paramiko:** SSH Tunnel connections.