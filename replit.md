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
- **Authentication:** JWT (PyJWT) for secure session management. All API routes require authentication via `get_current_user` dependency.
- **Access Management:** Unified `PerfilAcesso` system with `is_admin` flag, granular CRUD permissions per module, and field-level permissions for event tabs via `PerfilPermissaoCampo`. Dynamic sidebar filtering based on user permissions.
- **Dynamic Distance Management:** Distances are managed via `DistanciaOpcao` model, allowing admin users to create/delete options from the frontend.
- **Charting:** Recharts library for interactive data visualization.
- **SSH Tunneling:** Paramiko library manages secure SSH connections to external MySQL databases.
- **Security:** CORS origins configured via environment variables; credentials stored securely; sanitized error messages; SQL queries use parameterized bindings via SQLAlchemy `text()` and `bindparam()`.
- **3D Login Background:** Uses `@react-three/fiber`, `@react-three/drei`, and `three` for animated 3D background on login page, with CSS fallback. `framer-motion` for UI animations.
- **Virtual Assistant (Nori):** AI-powered assistant using OpenAI GPT-4o-mini for NLP, Web Speech API for speech-to-text, and SpeechSynthesis API for text-to-speech in Brazilian Portuguese.
- **Data Consolidation:** Endpoint consolidates inscription data from Ativo and Magento using SKU, with marketing dashboards sourcing from `cadastro_evento` and `atletas_site_pago`. The `_sync_dim_projeto` function in `cadastros.py` ensures each `cadastro_evento` has a matching `dim_projeto` record by SKU; if the SKU doesn't match the linked projeto, it creates or re-links to the correct one. A `/api/cadastros/resync-projetos` endpoint is available to batch-fix any historical mismatches. On startup, `_startup_resync_projetos()` in `main.py` automatically syncs all `cadastro_evento` records to `dim_projeto`, ensuring data consistency after deploys.
- **Double-Submit Protection:** The cadastro form submit button disables during loading (`disabled={excedeCortesias || loading}`) with a spinning icon and "Salvando..." text. `handleSubmit` has a guard clause (`if (loading) return`) to prevent concurrent submissions. Backend enforces SKU uniqueness on both POST and PUT endpoints (409 Conflict), with SKU values trimmed before persistence.
- **Appai/Assist. (Atletas):** `CadastroEvento` stores `atletas_appai_pago` (Integer) and `atletas_appai_tkt_medio` (Numeric) for Rio de Janeiro events. Persisted via `AppaiData` schema in `AtletasData`.
- **Triathlon Distances:** When modalidade is 'Triathlon', distancias JSON stores `[{nado: "...", ciclismo: "...", corrida: "..."}]` instead of string array. Frontend renders 3 separate inputs.
- **SKU/Evento Grupo:** `EventoGrupo.nome` and `SkuMapping.evento_grupo` support up to 200 characters. Migration runs on startup.
- **Sidebar Navigation:** Uses `overflow-y-auto` with `scrollbar-invisible` CSS for invisible scrolling when menu items exceed viewport.
- **Kit Produtos:** Available products include: Camiseta, Medalha, Garrafa, Sacochila, Mochila, Sacola, Moletom, Jaqueta, Boné, Viseira, Toalha, Touca, Squeeze, Munhequeira.
- **Cidade/Estado Fields:** Both `cadastro_evento` and `dim_projeto` have `cidade` (String 100) and `estado` (String 50) columns. The Cadastro form includes text input for Cidade and a dropdown with all 27 Brazilian state abbreviations for Estado. These fields sync to `dim_projeto` via `_update_projeto_fields` and are included in new `DimProjeto` creation.
- **Performance Optimizations:** FastAPI uses `def` for blocking DB operations; frontend employs AbortController and progressive loading; SQL queries use SARGable date range filters (instead of `YEAR()` functions) and `REGEXP '^[0-9]+$'` (instead of multiple `NOT LIKE` patterns) for better index utilization. N+1 query issues resolved via batch prefetching (`_prefetch_all_historical_patterns`). ISC queries use automatic retry with backoff (`_fetch_with_retry`). Connection pools explicitly configured with `pool_size=5`, `max_overflow=10`, `pool_timeout=30`, `read_timeout=90`.
- **Persistent Multi-Tier Cache:** `SmartCache` module uses dual-layer caching: in-memory (fast) + PostgreSQL `cache_entries` table (persistent across restarts, with `UNIQUE(cache_name, cache_key)` constraint). DB writes use atomic PostgreSQL UPSERT (`INSERT ... ON CONFLICT DO UPDATE`) via bounded `ThreadPoolExecutor(max_workers=2)`. Year-aware TTL: historical data cached permanently, current year data with 2-hour TTL but serves stale data while revalidating. DB reads preserve original `updated_at` timestamps for accurate TTL. On startup, all caches are loaded from PostgreSQL in <0.1s for instant data availability. `CacheRefreshScheduler` runs both periodic refresh (every 30 min) and daily full refresh at 07:00 BRT. Full warmup pre-loads ISC, event details, curvas, medias, and insights for all active events. Concurrent full-refresh prevention via atomic lock guard (checked before thread spawn and at warmup entry). Frontend uses stale-while-revalidate in-memory cache (30-min TTL, max 20 entries) with "Atualizar" (quick refresh) and "Atualizar Tudo" (full server-side refresh) buttons. Frontend `fullRefreshing` state syncs bidirectionally with server via polling (3s interval). Server-side last update timestamp displayed in dashboard. `POST /api/marketing/cache/refresh-all` triggers full warmup in background; `GET /api/marketing/cache/status` shows refresh progress (step/total, label, elapsed seconds), timestamps, and `last_error` for warmup failures. Refresh button shows real-time progress ("Passo 2/5 - Detalhes dos eventos (45s)") and visual feedback on completion: green "Atualizado!" on success, red "Falha na atualização" on error, yellow "Tempo esgotado" on 5-min timeout. Errors propagated to `ConnectionAlert` banner. Backend `_full_cache_warmup()` stores error messages via `set_last_refresh_error()`. Magento rolling avg timeout set to 60s to accommodate variable query times (28-54s observed).

### Feature Specifications
- **Authentication:** Standard email/password login with JWT.
- **Master Data Management:** CRUD for Cost Centers, Athlete Categories, and Users; "Projetos" merged into "Eventos".
- **Consolidated Dashboard:** Interactive dashboard with 5 KPI cards, 6 interactive charts, a detailed table, and automatic insights, all responding to global filters.
- **Marketing Performance (ISC Dashboard):** Displays Commercial Health Index (ISC) based on Acceleration Index, D-% Curve, and rolling 14-day sales average, using historical patterns for `curva_d_percent`. ISC calculations exclude today's data (reference = yesterday D-1). Rolling 14d formula: `sum_vendas_14d / meta_esperada_14d` (based on historical pattern or linear). Meta Acumulada vs Inscritos chart uses yesterday's cumulative data. Features dual D- system: `dMinus` (days to event, informational) and `dMinusInscricoes` (D- minus 2, used for all calculations). Event Detail page has 5 tabs: Dashboard, Simulador, Precificação, Projeção, and Complementares. Complementares tab contains: Curva de Vendas Acumuladas vs Esperado, Atingimento da Meta, Curva Comparativa (year-over-year), and EventInsights (Índice de Aceleração, Ticket Médio Acumulado). ISC status uses emoji indicators (😊😐😢). "Caminhos para Meta Margem" table uses corrected ticket convergência formula: (meta_margem - margem_acumulada) / volume_restante - kit_cost. **ISC uses desvio+cap model:** each component ratio is converted to deviation (ratio-1), capped at ±0.30, then `ISC = 1.0 + (40%×D + 40%×R + 20%×IA)`. Ratio scale centered at 1.0, range 0.70-1.30. Thresholds: >1.10 = accelerating, 0.90-1.10 = stable, <0.90 = decelerating.
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

### UI Components
- **ConnectionAlert:** Reusable component (`frontend/src/components/common/ConnectionAlert.tsx`) providing smart error/warning display for database connection issues. Features: error classification (session expired, server error, network error, timeout), per-source diagnostic info with timestamps for partial data warnings (Ativo, Magento, SSH), and retry button. Integrated in MarketingDashboard, EventDetail, and PricingAnalysis pages.

## External Dependencies
- **PostgreSQL:** Primary database.
- **MySQL:** External database for athlete data.
- **OpenAI:** GPT-4o-mini for Nori Virtual Assistant.
- **Web Speech API:** For Nori's speech-to-text.
- **SpeechSynthesis API:** For Nori's text-to-speech.
- **Paramiko:** For SSH Tunnel connections.