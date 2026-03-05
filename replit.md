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
- **Persistent Multi-Tier Cache:** `SmartCache` module utilizes in-memory and PostgreSQL `cache_entries` table for persistent caching. Features year-aware TTL, atomic UPSERTs, background refresh, and a 3-step optimized warm-up pipeline with resilience for external data source failures.
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
- **SKU Mapping & Event Groups:** Unified administration for SKU mappings and event groups.
- **Strategic Insights Dashboard:** Calculates insights from Ativo+Magento data, including Acceleration Index, Daily Pace, Closing Projection, and Category Mix.
- **Marketing Settings Persistence:** API for persisting marketing settings (key-value JSON), actively used in ISC calculations.
- **Event Detail Layout:** Redesigned layout for improved readability, including D- bar, ISC gauge, and sales indicators, with instant header rendering during data loading.
- **Cotação & Importação (Quote & Import):** System for managing product quotes and import costs, including suppliers, exchange rates, and event linking, with a dashboard and access control.

## External Dependencies
- **PostgreSQL:** Primary application database.
- **MySQL:** External athlete data storage.
- **OpenAI:** GPT-4o-mini for Nori Virtual Assistant.
- **Web Speech API:** Nori's speech-to-text.
- **SpeechSynthesis API:** Nori's text-to-speech.
- **Paramiko:** SSH Tunnel connections.