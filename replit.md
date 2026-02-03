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
- **Data Consolidation:** Implemented an endpoint for consolidating inscription data from multiple sources (Ativo and Magento databases) using SKU as the primary key for matching events across databases. SKU mappings are defined via CASE statements that convert id_evento (Ativo) and location_id (Magento) to standardized SKU codes (e.g., CDE26PL1, NRU26FT1), enabling accurate data aggregation across both platforms.

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

## Recent Changes

### 2026-02-03
- **Separated User Tasks from Delegated Tasks:**
  - Modified task listing endpoints to separate "my tasks" (where user is responsável or created for self) from "delegated tasks" (tasks created for other users).
  - Added new `/api/tarefas/delegadas` endpoint to list tasks delegated to others.
  - Updated `/api/tarefas/resumo` to include `delegadas_total` and `delegadas_pendentes` counts.
  - Added "Delegadas" tab in NoriAssistant with Users icon, showing tasks assigned to other users.
  - In "Delegadas" tab, tasks show "Delegada para: @responsavel.nome" badge.
  - In other tabs, tasks show "Atribuída por @usuario" when assigned by another user.
  - Tasks created for other users no longer appear in the creator's main task lists (only in "Delegadas" tab).
  - Used SQLAlchemy `is_(None)` and `isnot(None)` for proper null comparisons.
  - Added filter buttons in "Delegadas" tab (Todas, Pendentes, Em Andamento, Concluídas) for tracking progress.
  - Added status indicator tooltip showing task state (Pendente, Em Andamento, Concluída) on hover.
  - Removed action buttons (complete, start, delete) from delegated tasks view - only the assignee can manage them.

- **Improved Nori Assistente Task Management:**
  - Added tab system (Pendentes, Em Andamento, Concluídas, Todas) for better task navigation and tracking.
  - Tasks now display who assigned them ("Atribuída por @usuario") when a different user created the task.
  - Completed tasks remain visible with differentiated styling (line-through, reduced opacity, green check icon).
  - Added "Iniciar" button to move tasks from PENDENTE to EM_ANDAMENTO status.
  - Backend TarefaResponse schema updated to include `usuario` field (task creator info).
  - All task API endpoints now filter by both creator (usuario_id) and assignee (responsavel_id).
  - Task summary counts now include tasks where user is the assignee.

### 2026-02-02
- **Updated 'Análise de Atletas' cards in Projetos screen:**
  - Cards now display consolidated data from both Ativo and Magento databases.
  - "Realizado" shows qtd_vendida_total (consolidated total).
  - "Site" shows qtd_site_total (site sales).
  - "Grupo" shows qtd_grupos_total (group sales).
  - Added new "Cortesia" card showing cortesia_total (courtesy entries).
- **Implemented auto-refresh for consolidated data:** 5-minute interval with last update timestamp display and proper cleanup on modal close.
- **Separated data loading flows:**
  - Consolidated data (Análise de Atletas) auto-refreshes every 5 minutes.
  - External data (Dados em Tempo Real) requires manual button click for performance optimization.
- **Removed monetary values from Dados em Tempo Real section:**
  - Removed "Receita Total" card.
  - "Top Categorias" now shows only quantities (no monetary values).
- **Updated SQL queries for Ativo and Magento databases:** Added comprehensive CASE WHEN mappings to convert id_evento (Ativo) and location_id (Magento) to standardized SKU codes. This enables proper relation between both databases using SKU as the matching key.
- **SKU Mappings Added:**
  - Ativo: 91 id_evento mappings to SKU codes (e.g., 40048 → CDE26PL1, 39969 → CDE26RJ1)
  - Magento: 48 location_id mappings to SKU codes (e.g., 587 → CPLIE26SP1, 612 → BLU26RJ1)
- **Data consolidation logic updated:** Changed from event name-based matching to SKU-based matching for more accurate aggregation across databases.
- **Added JOINs for Magento SKU fallback:** Included catalog_product_entity_varchar and catalog_product_entity tables to provide SKU fallback when location_id is not mapped.
- **Marketing ISC Dashboard with Real Data:**
  - Created `/api/marketing/eventos` endpoint that fetches events from DimProjeto with consolidated sales data from Ativo/Magento.
  - Created `/api/marketing/resumo` endpoint for summary counts by ISC zone (green/yellow/red).
  - Implemented ISC calculation logic: IA 7/30 (acceleration index), Curva D-% (sales progress vs goal), Rolling 14d average, D-minus (days until event).
  - ISC zones: Green (>1.10 accelerating), Yellow (0.90-1.10 stable), Red (<0.90 decelerating).
  - Updated MarketingDashboard.tsx to use real API data instead of mock data.
  - Implemented 5-minute auto-refresh with timestamp display and manual refresh button.
  - Added loading states and error handling.
  - Uses DimProjeto.capacidade_maxima as sales goal and DimProjeto.evento for event names.
- **Event Detail Charts:**
  - Added daily sales data generation (generate_daily_sales_data function) for event detail charts.
  - Charts show "Curva de Vendas Acumuladas vs Esperado" and "Vendas Diárias (Últimos 30 dias)".
  - Event detail API now returns dailySales with cumulative and expected values.
- **Commercial Actions (Timeline de Ações Comerciais):**
  - Created `acoes_comerciais` table in PostgreSQL with fields: id, projeto_id, tipo, descricao, data_acao, impacto_percentual, vendas_antes, vendas_depois.
  - Added AcaoComercial model in dimensoes.py with relationship to DimProjeto.
  - Created CRUD endpoints: GET/POST/PUT/DELETE `/api/marketing/acoes-comerciais`.
  - Action types: AUMENTO_PRECO, REDUCAO_PRECO, PROMOCAO, CAMPANHA, COMUNICACAO.
  - Event detail API now returns commercialActions for the timeline display.
  - Frontend modal form to add new commercial actions (type, date, description).
  - Delete functionality with trash icon on each timeline entry.
  - Timeline shows action icon based on type, date, and impact percentage if available.
  - **Impact Calculation:** Implemented automatic calculation comparing consolidated sales (Ativo + Magento) 7 days before vs 7 days after each action.
  - Functions added: `fetch_daily_sales_ativo()`, `fetch_daily_sales_magento()`, `get_id_evento_from_projeto()`, `get_location_id_from_sku()`, `calculate_action_impact()`.
  - Impact displayed with color coding: green for positive, red for negative, yellow for "aguardando dados" (when 7 days haven't passed yet).
  - Shows detailed breakdown: "7d antes: X vendas → 7d depois: Y vendas".
  - Uses consolidated data from both Ativo and Magento databases for accurate impact measurement.