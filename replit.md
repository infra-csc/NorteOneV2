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
- **Authentication:** JWT (PyJWT) for secure session management and API route protection.
- **Access Management:** Unified `PerfilAcesso` system with granular CRUD and field-level permissions, and dynamic sidebar filtering.
- **Dynamic Content:** Distance management via `DistanciaOpcao` and dynamic `Kit Produtos` options.
- **Charting:** Recharts library for interactive data visualization.
- **SSH Tunneling:** Paramiko library manages secure SSH connections to external MySQL.
- **Security:** CORS, secure credential storage, sanitized error messages, parameterized SQL queries.
- **Virtual Assistant (Nori):** AI-powered assistant using OpenAI GPT-4o-mini for NLP, Web Speech API for speech-to-text, and SpeechSynthesis API for text-to-speech in Brazilian Portuguese.
- **Data Consolidation:** Consolidates inscription data from Ativo and Magento using SKU, ensuring data consistency and providing resync capabilities.
- **Double-Submit Protection:** Frontend and backend mechanisms to prevent duplicate form submissions.
- **User Activity Monitoring:** Tracks user activity with an admin monitoring page displaying online status and activity logs.
- **Performance Optimizations:** FastAPI for asynchronous operations, AbortController for frontend requests, SARGable SQL queries, N+1 query resolution, explicit connection pool configurations, and production-scale warmup optimizations.
- **Hybrid Data Model (Snapshots):** Daily sales data is stored in PostgreSQL `vendas_diaria_snapshot` for historical data (up to yesterday). Real-time queries to Ativo/Magento are restricted to today's data. Historical curves are pre-calculated and stored in `curva_historica_snapshot`. Snapshot consolidation runs daily.
- **Persistent Multi-Tier Cache with SWR:** `SmartCache` module utilizes in-memory and PostgreSQL `cache_entries` for persistent caching, featuring year-aware TTL, `MAX_STALE_AGE`, atomic UPSERTs, background refresh, and a 4-step optimized warm-up pipeline with resilience. Stale-While-Revalidate (SWR) mechanism returns stale data immediately and triggers background refresh. Applied to all ISC marketing endpoints.
- **ConnectionAlert:** Reusable frontend component for displaying database connection issues with diagnostics and retry functionality.

### Feature Specifications
- **Authentication:** Standard email/password login.
- **Master Data Management:** CRUD operations for Cost Centers, Athlete Categories, and Users; "Projetos" integrated into "Eventos".
- **Consolidated Dashboard:** Interactive dashboard with KPIs, charts, tables, and insights, globally filterable.
- **Marketing Performance (ISC Dashboard):** Displays Commercial Health Index (ISC) based on Acceleration Index, D-% Curve, and rolling 14-day sales average. Features detailed event pages with multiple tabs (Dashboard, Simulador, Precificação, Projeção, Complementares) including comparative curves and insights. ISC uses a `desvio+cap` model for calculation. Each event has a **Playbook** (A–I) based on stage (D-90→D-50 Analítico, D-50→D-32 Estratégico, D-32→D-0 Operacional) × ISC state (Forte/Estável/Fraco). Playbook is a structured object with name, objective, narrative, actions, KPIs, and cutoffs. Full playbook visualization available at `/marketing/playbook`.
- **Pricing Analysis:** Analyzes pricing strategies with metrics like "Rolling Index," "IED," "IA," "Pace de Segurança," and "FEM," including elasticity simulation.
- **External Athlete Data:** Real-time fetching and in-memory caching of athlete data from external MySQL.
- **Commercial Actions Timeline:** Manages and tracks the impact of commercial actions.
- **Sales Averages Analysis:** Provides daily sales averages from Ativo + Magento.
- **Year-over-Year Comparison:** Compares cumulative inscriptions and revenue by "days before event."
- **Historical Benchmark Curve:** Uses previous year's sales distribution for expected curve generation. Intelligent fallback chain for events without own history: manual override → same circuit+city → same circuit (average) → regional (same state, min 2 curves) → linear. Fallback source is tracked via `tipoCurva`/`fonteCurva`/`anoReferencia` in ISCComponents and shown in the UI with color-coded badges (blue=histórico, purple=circuito, violet=circuito similar, gray=regional, green=manual, amber=linear). Circuit/city metadata stored on `EventoGrupo` model (`circuito`, `cidade_normalizada`, `curva_override` fields). Clicking the badge opens a visual "Curva de Referência" info modal showing the full fallback chain with the active curve highlighted (playbook-style cards). Manual page has a dedicated "Curvas de Referência" section documenting the entire system.
- **ISC Data Consistency:** All ISC components derive `current_sales` from `daily_sales_dict`. Daily sales queries use `< CURDATE() + INTERVAL 1 DAY` to include today's partial data.
- **Error Boundary:** EventDetail route is wrapped in an ErrorBoundary component for graceful handling of React render crashes.
- **Margem por Tipo de Kit:** EventDetail "Composição da Margem" modal shows a per-kit breakdown table (Qtd Vendida, Receita Líquida, Ticket Médio, Custo Kit, Margem/Un, Margem Total) for each kit type plus a consolidated totals row. Kit costs come from CadastroKitProduto. Sales data is joined via `tipo_kit` in KitConfig (Magento bundles → kit name) and `ativo_categoria` in CadastroKitProduto (kit name → Ativo ds_categoria). Both mappings are configured explicitly by the user in the KitConfig admin page and Cadastro form.
- **Force-Refresh Cooldown:** "Atualizar Dados" button on event detail pages has a 10-minute cooldown, clearing in-memory cache without re-querying external databases if snapshot is recent.
- **Order Status Filter:** Ativo queries use `id_pedido_status IN (1, 2)`. Magento uses `status IN ('processing', 'complete', 'approved', ...)`. Filters are aligned with user reference queries for both Ativo and Magento.
- **Canal-based Inscription Filtering (Controle Diário):** `_fetch_daily_sales_ativo_by_ids`, `_fetch_today_sales_ativo_by_ids`, and `_fetch_daily_sales_ativo_by_ids_grouped` use canal-based logic. Canal 'Site' = everything not explicitly Cortesia or Grupos. Cortesia is identified **only** by `cupom.en_cupom_classificacao IN ('Funcionário', 'Cortesia Faturada', 'Coligados', 'Eventos Terceiros')`. Grupos/B2B by `en_cupom_classificacao = 'Grupos'` OR `ds_categoria LIKE '%Grup%'`. **`a.nr_preco = 0` (zero inscription price) is NOT a Cortesia criterion** — zero-priced inscriptions may be legitimate site registrations (e.g., bundled kit purchases). Only cupom classification identifies Cortesia.
- **Configurable Registration Close Date:** `dias_encerramento_inscricao` field on `CadastroEvento` defines registration close days before the event, used for all D- calculations.
- **Enriched Daily Sales API:** Each daily sales entry includes `dMinus`, `curvaAnoAnterior`, `dif`, `atingimentoAcumulado`, `atingimentoDiario`, `normalizedSales`, and `cumulativeNormalized`.
- **Normalized Sales Curve:** Detects campaign outliers using rolling 7-day median with 2x threshold, redistributes excess forward into next 5 days. Toggle button on Complementares tab shows orange dashed normalized curve alongside real cumulative curve. Total is preserved; only distribution changes.
- **SKU Mapping & Event Groups:** Unified administration for SKU mappings and event groups. SKU mappings include an optional `data_evento` field that takes priority for historical D-minus curves. Cache invalidation is automated.
- **Kit Config (Mapeamento de Kits):** Admin page (`/admin/kit-config`) for configuring kit multipliers and marking a "Kit Básico" per event. Fetches kit data from Magento MySQL with a query that pre-calculates the `multiplicador` based on `tipo_categoria` (e.g., Duathlon=2, Triathlon=3). Columns: Evento, Kit, Tipo (tipo_categoria), Lote Atual, Mult. (editable), Price (base price × mult), Special Price (final_price × mult). Backend returns `price_base` and `special_price_base` (un-multiplied) so the frontend recalculates in real-time when the user edits the multiplier input. If a saved config exists in PostgreSQL `kit_config`, its multiplicador overrides the suggested one. `ticketAtual` resolution priority: (1) `is_promo_principal` flag (explicit selection among multiple promos) → (2) any active kit with `tipo_kit` containing "promo" → (3) Kit Básico (`is_kit_basico`). Both `is_kit_basico` and `is_promo_principal` are exclusive per event. The Dash ISC shows a tooltip with the kit name used for `ticketAtual` (Info icon). `_fetch_ticket_atual_map` returns `{pid: {"value": float, "nome_kit": str}}`. Seed: bundle 50999 (mult 2), 54863 (mult 5).
- **Cache Poisoning Protection:** Curva comparativa endpoint validates cached results, discarding empty data and invalidating entries. Cross-validation for `data_evento` in `_find_data_evento`.
- **Strategic Insights Dashboard:** Calculates insights including Acceleration Index, Daily Pace, Closing Projection, and Category Mix.
- **Marketing Settings Persistence:** API for persisting marketing settings (key-value JSON), actively used in ISC calculations.
- **Event Detail Layout:** Redesigned layout for improved readability, including D- bar, ISC gauge, sales indicators, and a "Controle Diário" tab with a spreadsheet-style table.
- **Cotação & Importação (Quote & Import):** System for managing product quotes and import costs, including suppliers, exchange rates, and event linking, with a dashboard and access control.
- **Manual do Sistema:** Built-in documentation/knowledge base page at `/manual`, accessible to all authenticated users via the sidebar, covering all system features with search, navigation, and theme support.

## External Dependencies
- **PostgreSQL:** Primary application database.
- **MySQL:** External athlete data storage.
- **OpenAI:** GPT-4o-mini for Nori Virtual Assistant.
- **Web Speech API:** Nori's speech-to-text.
- **SpeechSynthesis API:** Nori's text-to-speech.
- **Paramiko:** SSH Tunnel connections.