# DW Financeiro - Sistema de Gestao de Data Warehouse para Eventos

## Overview
The DW Financeiro system is a web-based platform serving as a "Single Source of Truth" for event management data. It provides consolidated insights, particularly for event-related metrics and marketing performance, to facilitate data-driven decision-making. Key capabilities include secure authentication, robust master data management, and dynamic marketing performance dashboards. The Marketing Performance (ISC Dashboard) monitors event sales, especially race registrations, to identify strong or weak events and inform strategic planning.

## User Preferences
I want iterative development.
Ask before making major changes.
I prefer detailed explanations.
Do not make changes to the folder `Z`.
Do not make changes to the file `Y`.

## System Architecture

### UI/UX Decisions
The frontend uses React, TypeScript, and Tailwind CSS for a modern, consistent user experience, featuring an animated background, gradient headers, contemporary card designs, and support for both light and dark themes.

### Technical Implementations
- **Backend:** Python with FastAPI.
- **Frontend:** React, TypeScript, and Tailwind CSS.
- **Databases:** PostgreSQL (primary application DB), MySQL (for external athlete data via SSH Tunnel).
- **ORM:** SQLAlchemy.
- **Authentication:** JWT for secure session management.
- **Access Management:** Unified `PerfilAcesso` system with `is_admin` flag, granular CRUD permissions per module, and field-level permissions for event tabs via `PerfilPermissaoCampo`. Dynamic sidebar filtering based on user permissions.
- **Dynamic Distance Management:** Distances are managed via `DistanciaOpcao` model, allowing admin users to create/delete options from the frontend.
- **Charting:** Recharts library for interactive data visualization.
- **SSH Tunneling:** Paramiko library manages secure SSH connections to external MySQL databases.
- **Security:** CORS origins configured via environment variables; credentials stored securely; sanitized error messages.
- **Virtual Assistant (Nori):** AI-powered assistant using OpenAI GPT-4o-mini for NLP, Web Speech API for speech-to-text, and SpeechSynthesis API for text-to-speech in Brazilian Portuguese.
- **Data Consolidation:** Endpoint consolidates inscription data from Ativo and Magento using SKU, with marketing dashboards sourcing from `cadastro_evento` and `atletas_site_pago`.
- **Performance Optimizations:** FastAPI uses `def` for blocking DB operations; frontend employs AbortController and progressive loading; SQL queries optimize calculations.
- **Smart Multi-Tier Cache:** `SmartCache` module manages year-aware TTL, permanently caching historical data and applying a 1-hour TTL with background refresh for current year data.

### Feature Specifications
- **Authentication:** Standard email/password login with JWT.
- **Master Data Management:** CRUD for Cost Centers, Athlete Categories, and Users; "Projetos" merged into "Eventos".
- **Consolidated Dashboard:** Interactive dashboard with 5 KPI cards, 6 interactive charts, a detailed table, and automatic insights, all responding to global filters.
- **Marketing Performance (ISC Dashboard):** Displays Commercial Health Index (ISC) based on Acceleration Index, D-% Curve, and rolling 14-day sales average, using historical patterns for `curva_d_percent`. Includes event details, comparative views, and configuration.
- **Pricing Analysis (Event Detail Tab):** Analyzes event pricing strategies using metrics like "Rolling Index", "IED", "IA", "Pace de Segurança", and "FEM", with an elasticity simulator and pricing recommendation.
- **External Athlete Data:** Real-time fetching of athlete data from external MySQL via SSH, with project linking and in-memory cache.
- **Commercial Actions Timeline:** Manages and tracks the impact of commercial actions on sales, preventing duplicates.
- **Sales Averages Analysis:** Provides daily sales averages with configurable periods, using real data from Ativo + Magento.
- **Year-over-Year Comparison Chart:** Compares cumulative inscriptions and revenue by "days before event", aligning data accurately across years.
- **Historical Benchmark Curve:** "Curva de Vendas Acumuladas vs Esperado" chart uses previous year's actual sales distribution (aligned by D-) for expected curve generation.
- **Simulated D- for Historical Years:** `calculate_d_minus()` supports `reference_year` for historical D- calculations.
- **SKU Mapping & Event Groups:** Unified admin page for managing SKU mappings, `evento_grupo`, and external event discovery.
- **Strategic Insights Dashboard:** Calculates insights from Ativo+Magento data, including Acceleration Index, Daily Pace, Closing Projection, and Category Mix.
- **Marketing Settings Persistence:** Persists marketing settings (key-value JSON) via API, with ISC Parameters actively used in calculations.
- **Event Detail Layout Redesign:** Restructured Dash ISC Event Detail page for improved readability and data presentation, including D- bar, ISC gauge, sales cards, and volume indicators.
- **Cotação & Importação (Quote & Import):** Comprehensive system for managing product quotes and import costs, including trips, suppliers, quotes with real-time exchange rates, import costs, and event linking. Features a dashboard with charts and access control.

## External Dependencies
- **PostgreSQL:** Primary database.
- **MySQL:** External database for athlete data.
- **OpenAI:** GPT-4o-mini for Nori Virtual Assistant.
- **Web Speech API:** For Nori's speech-to-text.
- **SpeechSynthesis API:** For Nori's text-to-speech.
- **Paramiko:** For SSH Tunnel connections.