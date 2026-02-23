# DW Financeiro - Sistema de Gestao de Data Warehouse para Eventos

## Overview
The DW Financeiro system is a comprehensive web-based platform designed to serve as the "Single Source of Truth" for budgetary data, financial projections, and actual performance within an events company. Its primary purpose is to provide consolidated financial insights, especially for event-related metrics and marketing performance, to enable data-driven decision-making. Key capabilities include secure authentication, robust master data management, detailed budget tracking, athlete performance dashboards, and a consolidated financial dashboard with key performance indicators (KPIs). A significant feature is the Marketing Performance (ISC Dashboard) which monitors event sales, particularly race registrations, to identify strong or weak events and inform pricing and communication strategies. The system aims to enhance financial transparency and strategic planning for event management.

## User Preferences
I want iterative development.
Ask before making major changes.
I prefer detailed explanations.
Do not make changes to the folder `Z`.
Do not make changes to the file `Y`.

## System Architecture

### UI/UX Decisions
The frontend utilizes React, TypeScript, and Tailwind CSS to deliver a modern, consistent user experience. Design elements include an animated background, gradient headers, and contemporary card designs, with support for both light and dark themes.

### Technical Implementations
- **Backend:** Python with FastAPI for high-performance API services.
- **Frontend:** React, TypeScript, and Tailwind CSS for a dynamic and responsive user interface.
- **Database:** PostgreSQL as the primary application database. MySQL is used for accessing external athlete data via SSH Tunnel.
- **ORM:** SQLAlchemy for efficient and abstracted database interactions.
- **Authentication:** JWT (JSON Web Tokens) for secure session management.
- **Access Management:** Unified PerfilAcesso system with `is_admin` flag for admin privileges and granular CRUD permissions per module (16 modules). Users are assigned one access profile (defining permissions) and optionally one cost center (for data-level filtering). The old `perfil` column on `dim_usuario` has been removed. PermissionContext provides global permission checking (canView, canCreate, canEdit, canDelete) across the frontend. Sidebar menu items are dynamically filtered based on user permissions. Admin users (is_admin=true on their PerfilAcesso) automatically receive full permissions. Backend uses `is_user_admin()`, `require_admin()`, and `require_permission()` helpers. All backend routes now use `require_permission(module, permission)` for granular access control instead of role-based checks. The `is_admin` flag on profiles can only be set/changed by existing admin users (privilege escalation protection). The `require_roles()` function is deprecated but kept for backward compatibility.
- **Charting:** Recharts library for interactive data visualization across various dashboards.
- **SSH Tunneling:** Paramiko library manages secure SSH connections to external MySQL databases, supporting diverse SSH key types and automatic tunnel lifecycle.
- **Virtual Assistant (Nori):** An AI-powered assistant using OpenAI GPT-4o-mini for NLP, Web Speech API for speech-to-text, and SpeechSynthesis API for text-to-speech in Brazilian Portuguese. It offers event scenario analysis, conversational chat, and task scheduling.
- **Data Consolidation:** An endpoint consolidates inscription data from Ativo and Magento databases using SKU as the primary key. SKU mappings use Python dict lookups with SQL catalog_product_entity fallback. Marketing dashboards (ISC Dashboard and Pricing Analysis) use `cadastro_evento` as the primary source of events — only events registered in the Eventos screen appear in these dashboards. Sales goals come from `atletas_site_pago` (Pago field in Site card, Atletas tab). Dedicated SQL queries provide consolidated data, including `qtd_site`, rolling averages, `dias_ate_evento`, and `projecao_final`, with a 5-minute cache.
- **Performance Optimizations:** FastAPI route handlers are `def` instead of `async def` to leverage automatic thread pooling for blocking DB operations. Frontend implements AbortController for cancelling requests on navigation and uses progressive loading with inline indicators. ISC/Pricing queries directly calculate rolling averages and projections in SQL. Ticket Médio Site is calculated from real database data using specific formulas for Ativo and Magento. MySQL queries utilize `MAX_EXECUTION_TIME` hints, and external MySQL connections have defined timeouts.
- **Smart Multi-Tier Cache:** A centralized `SmartCache` module manages year-aware TTL. Historical data (years < current) is permanently cached in memory, while current year data has a 1-hour TTL with background auto-refresh. This applies to ISC pricing, event details, daily sales, comparative curves, and sales averages. A refresh endpoint and status endpoint are available, and frontend "Atualizar Dados" buttons bypass the cache.

### Feature Specifications
- **Authentication:** Standard email/password login with JWT-based sessions and role-based permissions.
- **Master Data Management:** CRUD operations for Cost Centers, Accounting Accounts, Athlete Categories, and Users. The "Projetos" screen has been merged into "Eventos", with project fields integrated into the Eventos Info Geral tab, and a sync function for backward compatibility.
- **Budget Module:** Functionality for visualizing annual and monthly budgets, along with revenue and expense summaries.
- **Athlete Module:** Dashboards to compare budgeted, projected, and actual athlete numbers per event.
- **Consolidated Dashboard:** A central dashboard displaying financial KPIs, monthly evolution graphs, financial distribution by type, and athlete distribution by modality/project.
- **Marketing Performance (ISC Dashboard):** Displays a Commercial Health Index (ISC) based on Acceleration Index, D-% Curve, and rolling 14-day sales average. ISC uses historical patterns from the previous year for curva_d_percent calculation instead of generic 90-day linear distribution. Rolling14d compares current pace against actual remaining pace needed (remaining_sales/d_minus) rather than a fixed linear pace. Includes a general dashboard, event details, comparative views, and a configuration module for goals, benchmarks, and alerts. Features a "Business Rule D-40" for promotion timing.
- **Pricing Analysis (Event Detail Tab):** Pricing analysis is integrated as a tab within the Event Detail page (not a standalone page). Analyzes event pricing strategies using metrics like "Rolling Index (Sell-out)", "IED" (Índice de Eficiência de Demanda), "IA" (Índice de Aceleração), "Pace de Segurança", and "FEM" (Fator de Elasticidade de Margem). Each metric includes explanatory tooltips. Includes an elasticity simulator and a pricing recommendation with confidence level.
- **External Athlete Data:** Real-time fetching of summarized and event-specific athlete data from an external MySQL database via SSH, with project linking and an in-memory cache. Athlete metrics are structured across four direct tables linked by `projeto_id`.
- **Commercial Actions Timeline:** Manages and tracks the impact of commercial actions (e.g., price changes, promotions) on sales. Prevents duplicate actions within a 7-day window and visually indicates active actions.
- **Sales Averages Analysis:** An endpoint provides daily sales averages with configurable periods (7, 14, 30, 60, 90 days), utilizing real data from Ativo + Magento via SKU resolution. Frontend displays period selection, summary cards, and a ComposedChart of daily sales and 7-day moving average.
- **Year-over-Year Comparison Chart:** Available in the Event Detail page, aligning data by "days before event" for accurate cross-year comparisons. Uses event dates from `dim_projeto` and calculates `dias_antes_evento` for each sale, bucketed into 7-day intervals. Displays cumulative curves for inscriptions and revenue, with a projection line for the current year. Sales attribution is by event edition year from `sku_mappings.ano`.
- **Historical Benchmark Curve:** The "Curva de Vendas Acumuladas vs Esperado" chart uses the previous year's actual sales distribution (aligned by D-) to generate the expected curve, instead of a simple linear distribution. The function `_fetch_previous_year_cumulative_pattern` fetches the prior year's daily sales for the same `evento_grupo`, calculates cumulative percentages by D-, and applies them to the current year's goal. Falls back to linear distribution when no historical data is available. Pattern includes interpolation between known D- values and anchors at D-0 = 100%. The historical pattern is NOT re-normalized — if the previous year started sales earlier, the expected curve reflects that full history, showing when the current year may have opened sales later.
- **Simulated D- for Historical Years:** `calculate_d_minus()` supports an optional `reference_year` parameter to simulate historical perspectives for D- calculations.
- **SKU Mapping & Event Groups:** A unified admin page (`/admin/sku-mappings`) manages SKU mappings grouped by `evento_grupo`, external event discovery, and CRUD for event groups. ISC and Pricing dashboards now use the `evento_grupo` string field for event grouping.
- **Strategic Insights Dashboard:** An endpoint and component within Event Detail page calculates insights from real Ativo+Magento data, including Acceleration Index, Daily Pace, Closing Projection, D-40 Action Window analysis, Average Ticket evolution, and Category Mix. Uses `SmartCache`.
- **Marketing Settings Persistence:** Marketing settings are persisted using a `MarketingSettings` model (key-value JSON in PostgreSQL) via dedicated API endpoints. All marketing settings components now fetch/persist data via API, eliminating mock data.

## External Dependencies
- **PostgreSQL:** Primary database for the DW Financeiro application.
- **MySQL:** External database used for retrieving real-time athlete data.
- **OpenAI:** Provides the GPT-4o-mini model for the Nori Virtual Assistant's natural language processing.
- **Web Speech API:** Browser-native API enabling speech-to-text functionality for Nori.
- **SpeechSynthesis API:** Browser-native API enabling text-to-speech functionality for Nori.
- **Paramiko:** Python library facilitating secure SSH Tunnel connections to external databases.