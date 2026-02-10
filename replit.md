# DW Financeiro - Sistema de Gestao de Data Warehouse para Eventos

## Overview
The DW Financeiro system is a comprehensive web-based platform for managing the financial Data Warehouse of an events company. It serves as the "Single Source of Truth" for budgetary data, financial projections, and actual performance. The system provides consolidated financial insights, especially for event-related metrics and marketing performance, to enable data-driven decision-making. Key capabilities include authentication, master data management, budget tracking, athlete performance dashboards, and a consolidated financial dashboard with KPIs. It features a Marketing Performance (ISC Dashboard) to monitor event sales, particularly race registrations, helping to identify strong or weak events and guide pricing and communication strategies.

## User Preferences
I want iterative development.
Ask before making major changes.
I prefer detailed explanations.
Do not make changes to the folder `Z`.
Do not make changes to the file `Y`.

## System Architecture

### UI/UX Decisions
The frontend is built with React, TypeScript, and Tailwind CSS, featuring a modern, consistent design with an animated background, gradient headers, and modern cards. It supports both light and dark themes.

### Technical Implementations
- **Backend:** Python with FastAPI.
- **Frontend:** React with TypeScript and Tailwind CSS.
- **Database:** PostgreSQL for the main application, and MySQL accessed via SSH Tunnel for external athlete data.
- **ORM:** SQLAlchemy for database interactions.
- **Authentication:** JWT for secure session management and role-based access control (ADMIN, GESTOR, ANALISTA, VISUALIZADOR).
- **Charting:** Recharts for data visualization in dashboards.
- **SSH Tunnel:** Paramiko for secure connections to external MySQL databases, including support for various SSH key types and automatic tunnel lifecycle management.
- **Virtual Assistant (Nori):** Integrated AI-powered virtual assistant utilizing OpenAI GPT-4o-mini for natural language processing, Web Speech API for speech-to-text, and SpeechSynthesis API for text-to-speech in Brazilian Portuguese. It provides event scenario analysis, conversational chat, and task scheduling.
- **Data Consolidation:** Implemented an endpoint for consolidating inscription data from multiple sources (Ativo and Magento databases) using SKU as the primary key. SKU mappings use Python dict lookups with SQL catalog_product_entity fallback for unmapped locations.
- **Performance Optimizations (Feb 2026):**
  - **Critical fix:** All FastAPI route handlers converted from `async def` to `def` to prevent event loop blocking with synchronous database operations. FastAPI now runs blocking DB calls in thread pools automatically.
  - Frontend AbortController pattern cancels pending API requests on page navigation (PricingAnalysis, MarketingDashboard, EventDetail).
  - Frontend progressive loading: pages render structure immediately with inline loading indicators instead of full-screen blockers.
  - Rolling average queries optimized: correlated subqueries replaced with conditional COUNT/GROUP BY.
  - MySQL queries use MAX_EXECUTION_TIME(25000) hints for database-level timeout enforcement.
  - Ativo and Magento rolling average queries run in parallel via ThreadPoolExecutor (2 workers, 30s timeout each).
  - MySQL connection timeouts: 10s connect, 30s read/write on all external database engines.

### Feature Specifications
- **Authentication:** Login with email/password, JWT sessions, and role-based access.
- **Master Data Management (Dimensions):** CRUD operations for Cost Centers, Accounting Accounts, Projects/Events, Athlete Categories, and Users.
- **Budget Module:** Annual/monthly budget visualization, revenue and expense summaries.
- **Athlete Module:** Dashboard for athletes per event, comparing budgeted vs. projected vs. actual.
- **Consolidated Dashboard:** Financial KPIs, monthly evolution graphs, distribution by type, and athletes by modality/project.
- **Marketing Performance (ISC Dashboard):** Displays Commercial Health Index (ISC) indicating event strength (Accelerating, Stable, Decelerating) based on Acceleration Index (IA 7/30), D-% Curve, and Rolling 14-day sales average. Includes General Dashboard, Event Detail, Comparative views, and a Configuration Module for goals, benchmarks, and alerts. Features a "Business Rule D-40" for promotion timing.
- **Pricing Analysis Dashboard:** New dashboard for analyzing event pricing strategies, including "Rolling Index (Sell-out)", "IED (Indice de Excedente de Demanda)", "Pace de Seguranca", and "FEM (Fator de Equivalencia de Margem)". Features an elasticity simulator and a decision matrix for pricing recommendations.
- **External Athlete Data:** Real-time fetching of athlete data from an external MySQL database via SSH Tunnel, including summarized and event/project-specific data, project linking, and an in-memory cache.
- **Athlete Data Model:** Athlete metrics are organized into four direct tables linked by `projeto_id` (`fato_atletas_metricas`, `fato_atletas_canais`, `fato_atletas_kits`, `fato_atletas_custos`).
- **Commercial Actions Timeline:** Manages commercial actions (e.g., price changes, promotions) with CRUD operations, allowing tracking of their impact on sales before and after the action.
- **SKU Mapping & Event Groups (Feb 2026 Restructure):** Unified admin page at `/admin/sku-mappings` with 3 tabs: "Mapeamentos" (existing SKU mappings grouped by evento_grupo with collapsible sections), "Eventos Externos" (auto-loads events from Ativo/Magento for current+previous year using lightweight queries without JOINs), and "Grupos de Evento" (CRUD for managing event groups via `evento_grupos` table). Removed the separate "Eventos Consolidados" admin page. Event discovery queries no longer require manual year selection — they automatically fetch current year and previous year.
- **EventoGrupo Migration (Feb 2026):** Both ISC Dashboard and Pricing Analysis Dashboard now use `evento_grupo` string field from SkuMapping for event grouping, replacing the old `evento_consolidado_id` foreign key approach. Group-based events use `grp_` prefix IDs (e.g., `grp_Corrida XYZ`). Helper functions `_build_sku_to_grupo_map` and `_aggregate_grupo_sales` handle SKU→grupo mapping and sales aggregation. The EventoConsolidado model is retained in the codebase but no longer actively used by dashboards. Projects form includes SKU autocomplete via `/projetos/skus-disponiveis` endpoint using HTML datalist.

## External Dependencies
- **PostgreSQL:** Primary database for the DW Financeiro system.
- **MySQL:** External database for real-time athlete data.
- **OpenAI:** Used for the Nori Virtual Assistant's natural language processing (GPT-4o-mini).
- **Web Speech API:** Browser-based API for speech-to-text functionality in Nori.
- **SpeechSynthesis API:** Browser-based API for text-to-speech functionality in Nori.
- **Paramiko:** Python library for establishing SSH Tunnels to external databases.