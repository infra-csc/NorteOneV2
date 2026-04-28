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
- **PWA (Progressive Web App):** The application is installable on Android and iOS/iPadOS, configured via `vite-plugin-pwa` with specific caching strategies for different API endpoints and assets.
- **Databases:** PostgreSQL serves as the primary database, complemented by MySQL for external athlete data accessed via SSH Tunnel.
- **ORM:** SQLAlchemy is used for database interactions.
- **Authentication:** JWT (PyJWT) ensures secure session management and API route protection.
- **Access Management:** A unified `PerfilAcesso` system provides granular CRUD and field-level permissions, alongside dynamic sidebar filtering.
- **Virtual Assistant (Nori):** An AI-powered assistant leveraging OpenAI GPT-4o-mini for NLP, Web Speech API for speech-to-text, and SpeechSynthesis API for text-to-speech in Brazilian Portuguese.
- **Data Consolidation:** Consolidates inscription data from Ativo and Magento based on SKU, ensuring data consistency and providing resync capabilities.
- **Performance Optimizations:** Includes FastAPI for asynchronous operations, SARGable SQL queries, N+1 query resolution, explicit connection pool configurations, and production-scale warmup optimizations.
- **Hybrid Data Model (Snapshots):** Daily sales data is stored in PostgreSQL for historical reference, while real-time data for the current day is fetched directly from Ativo/Magento. Historical curves are pre-calculated and stored as snapshots with robust rebuild safety mechanisms.
- **Magento Connection Resilience:** All Magento queries include centralized retry logic for transient errors and are tuned for SSH tunnel stability.
- **Persistent Multi-Tier Cache with SWR:** A `SmartCache` module uses in-memory and PostgreSQL for persistent caching with year-aware TTL, atomic UPSERTs, background refresh, and an optimized warm-up pipeline.

### Feature Specifications
- **Authentication:** Standard email/password login with profile management.
- **Master Data Management:** CRUD operations for Cost Centers, Athlete Categories, and Users.
- **Consolidated Dashboard:** An interactive, globally filterable dashboard displaying KPIs, charts, and tables.
- **Marketing Performance (ISC Dashboard):** Displays Commercial Health Index (ISC) based on Acceleration Index, D-% Curve, and rolling 14-day sales average. Includes detailed event pages with multiple tabs and a dynamic **Playbook** based on event stage and ISC state.
- **Pricing Analysis:** Analyzes pricing strategies using various metrics and elasticity simulation.
- **External Athlete Data:** Real-time fetching and in-memory caching of athlete data from external MySQL.
- **Commercial Actions Timeline:** Manages and tracks the impact of commercial actions.
- **Sales Averages Analysis:** Provides daily sales averages from Ativo + Magento.
- **Year-over-Year Comparison:** Compares cumulative inscriptions and revenue by "days before event."
- **Historical Benchmark Curve:** Generates expected sales curves using previous year's sales distribution with an intelligent fallback chain.
- **Margem por Tipo de Kit:** Modal providing a per-kit breakdown of sales, revenue, and margins.
- **Configurable Registration Close Date:** `dias_encerramento_inscricao` field defines registration close days for D- calculations.
- **Normalized Sales Curve:** Detects and redistributes campaign outliers using a rolling 7-day median.
- **SKU Mapping & Event Groups:** Unified administration for SKU mappings and event groups with automated cache invalidation.
- **Cycling Scenarios (Cenários de Ciclismo):** Supports three distinct sales scenarios for "Ciclismo" events with dedicated UI for configuration and analysis.
- **Kit Config (Mapeamento de Kits):** Admin page for configuring kit multipliers and marking a "Kit Básico" per event, sourcing kits from both Magento and Ativo.
- **Strategic Insights Dashboard:** Calculates insights including Acceleration Index, Daily Pace, Closing Projection, and Category Mix.
- **Marketing Settings Persistence:** API for persisting key-value JSON marketing settings, used in ISC calculations.
- **Cotação & Importação (Quote & Import):** FOB quote registration page with manual inputs for Índice de Importação, BEC, and Cotação (USD/BRL) to calculate nationalized and BRL values.
- **Manual do Sistema:** Built-in documentation/knowledge base page accessible to all authenticated users.
- **Projeção de Inscritos por Eventos e Áreas:** Allows users to input projected subscriber counts per event across predefined areas, with admin assignment, audit history, and consolidated views. Supports breakdowns by Kit and Client.
- **Pontos de Corte (Cutoff Rules) para Projeção:** Configurable D-day thresholds that trigger in-app pendency indicators for Projeção Inscritos.
- **Cortes customizados por (evento, área):** Áreas marcadas com `usa_cutoff_customizado` (toggle administrativo na aba Configurações) deixam de seguir as regras globais D-N e passam a usar duas datas de corte específicas por evento, definidas pelos usuários da área no detalhe do evento. As pendências combinam ambas as fontes em um único item por evento (rota `GET /projecao/pendencias`), com gravação atômica via `PUT /projecao/cutoff-evento-area` e leitura via `GET /projecao/cutoff-evento-area`. Schema: coluna `area_projecao.usa_cutoff_customizado` + tabela `projecao_cutoff_evento_area` (criadas em `_run_column_migrations`).

## Resilience Notes
- **Today's sales sync (Atualizar/Sincronizar Hoje):** Inner helpers `_fetch_today_sales_ativo_grouped` and `_fetch_today_sales_magento_grouped` accept `raise_on_error` so callers (`sincronizar_hoje_batch`, `atualizar_vendas_hoje`) can detect upstream DB failures and skip the snapshot UPSERT, preserving the previously stored row instead of overwriting today with 0. Endpoint returns `status: "partial"` with `ativo_ok`/`magento_ok`/`fontes_indisponiveis`; frontend shows an amber warning banner instead of zeroing today's value.
- **Magento DB pool:** `pool_size=8`, `max_overflow=12`, `pool_timeout=20` (was 3/5), tuned to handle bursty refreshes without exhausting the pool.

## External Dependencies
- **PostgreSQL:** Primary application database.
- **MySQL:** External athlete data storage.
- **OpenAI:** GPT-4o-mini for Nori Virtual Assistant.
- **Web Speech API:** Used for Nori's speech-to-text functionality.
- **SpeechSynthesis API:** Used for Nori's text-to-speech functionality.
- **Paramiko:** Used for establishing secure SSH Tunnel connections.