# DW Financeiro - Sistema de Gestao de Data Warehouse para Eventos

## Overview
The DW Financeiro system is a comprehensive web-based platform designed for managing the financial Data Warehouse of an events company. It serves as the "Single Source of Truth" for budgetary data, financial projections, and actual performance. The system aims to provide consolidated financial insights, especially for event-related metrics and marketing performance, to enable data-driven decision-making. Key capabilities include authentication, master data management (dimensions), budget tracking, athlete performance dashboards, and a consolidated financial dashboard with KPIs. A significant component is the Marketing Performance (ISC Dashboard) which provides critical metrics for event sales, particularly for race registrations, helping to identify strong or weak events and guide pricing and communication strategies.

## User Preferences
I want iterative development.
Ask before making major changes.
I prefer detailed explanations.
Do not make changes to the folder `Z`.
Do not make changes to the file `Y`.

## System Architecture

### UI/UX Decisions
The frontend is built with React, TypeScript, and Tailwind CSS, featuring a modern, consistent design with an animated background, gradient headers, and modern cards. It includes full support for light and dark themes.

### Technical Implementations
- **Backend:** Python with FastAPI.
- **Frontend:** React with TypeScript and Tailwind CSS.
- **Database:** PostgreSQL for the main application, and MySQL accessed via SSH Tunnel for external athlete data.
- **ORM:** SQLAlchemy for database interactions.
- **Authentication:** JWT for secure session management and role-based access control (ADMIN, GESTOR, ANALISTA, VISUALIZADOR).
- **Charting:** Recharts for data visualization in dashboards.
- **SSH Tunnel:** Paramiko for secure connections to external MySQL databases, including support for various SSH key types and automatic tunnel lifecycle management.
- **Virtual Assistant (Nori):** Integrated AI-powered virtual assistant utilizing OpenAI GPT-4o-mini for natural language processing, Web Speech API for speech-to-text, and SpeechSynthesis API for text-to-speech in Brazilian Portuguese. It provides event scenario analysis, conversational chat, and task scheduling.
- **Data Consolidation:** Implemented an endpoint for consolidating inscription data from multiple sources (Ativo and Magento databases) by normalizing SKUs, providing a unified view of event registrations.

### Feature Specifications
- **Authentication:** Login with email/password, JWT sessions, and role-based access.
- **Master Data Management (Dimensions):** CRUD operations for Cost Centers, Accounting Accounts, Projects/Events, Athlete Categories, and Users.
- **Budget Module:** Annual/monthly budget visualization, revenue and expense summaries.
- **Athlete Module:** Dashboard for athletes per event, comparing budgeted vs. projected vs. actual.
- **Consolidated Dashboard:** Financial KPIs, monthly evolution graphs, distribution by type, and athletes by modality/project.
- **Marketing Performance (ISC Dashboard):**
    - **Key Metric:** Commercial Health Index (ISC) indicating event strength (Accelerating, Stable, Decelerating).
    - **ISC Components:** Acceleration Index (IA 7/30), D-% Curve (actual vs. expected sales), Rolling 14-day sales average.
    - **Business Rule D-40:** Critical window for promotions (diagnose by D-45, act by D-40; no promotions after D-40).
    - **Views:** General Dashboard (event table with ISC), Event Detail (ISC gauge, sales graphs), Comparative (side-by-side event comparison).
    - **Configuration Module:** Define sales/revenue goals, configure benchmark curves, adjust ISC parameters, manage event categories, and set up automatic alerts (email, SMS, push, Slack).
- **External Athlete Data:** Real-time fetching of athlete data from an external MySQL database via SSH Tunnel. Features include summarized data, event-specific data, project-specific data, project linking, and an in-memory cache with TTL.
- **Athlete Data Model:** Athlete metrics are organized into four direct tables linked by `projeto_id` (project_id) instead of an intermediate `fato_atletas` table:
    - `fato_atletas_metricas`: Main metrics (quantity, ticket_medium, inscription, kit_cost_unit).
    - `fato_atletas_canais`: Metrics by distribution channel (SITE, GRUPOS, APPAI).
    - `fato_atletas_kits`: Metrics for different kit types (VIP, PLUS, SUPER, PRODUCT).
    - `fato_atletas_custos`: Operational costs per athlete (AGUA, ISOTONICO, HIDRATACAO, etc.).

## External Dependencies
- **PostgreSQL:** Primary database for the DW Financeiro system.
- **MySQL:** External database for real-time athlete data, accessed securely via SSH Tunnel.
- **OpenAI:** Used for the Nori Virtual Assistant's natural language processing (GPT-4o-mini).
- **Web Speech API:** Browser-based API for speech-to-text functionality in Nori.
- **SpeechSynthesis API:** Browser-based API for text-to-speech functionality in Nori.
- **Paramiko:** Python library for establishing SSH Tunnels to external databases.