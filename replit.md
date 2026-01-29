# DW Financeiro - Sistema de Gestao de Data Warehouse para Eventos

## Overview
Sistema web completo para gerenciamento de Data Warehouse financeiro de uma empresa de eventos. O sistema e a "fonte unica de verdade" (Single Source of Truth) para dados orcamentarios, projecoes e realizados.

## Stack Tecnologica
- **Backend:** Python com FastAPI
- **Frontend:** React com TypeScript e Tailwind CSS
- **Banco de Dados:** PostgreSQL, MySQL (via SSH Tunnel)
- **ORM:** SQLAlchemy
- **Autenticacao:** JWT
- **Graficos:** Recharts
- **SSH Tunnel:** Paramiko para conexao segura a bancos externos

## Estrutura do Projeto

```
/backend
  /app
    /api/routes    - Rotas da API (auth, users, centros_custo, contas, projetos, etc)
    /core          - Configuracoes, database, seguranca
    /models        - Modelos SQLAlchemy
    /schemas       - Schemas Pydantic
  main.py          - Aplicacao FastAPI principal
  seed_data.py     - Script para popular dados de exemplo

/frontend
  /src
    /components    - Componentes React reutilizaveis
    /context       - Contextos (Auth, Theme)
    /data          - Dados mock (mockMarketingData.ts)
    /pages         - Paginas da aplicacao
      /marketing   - Dashboard Marketing Performance (ISC)
    /services      - Servicos de API
    /types         - Definicoes TypeScript (marketingPerformance.ts)
```

## Funcionalidades Implementadas

### 1. Autenticacao
- Login com email/senha
- JWT para sessoes
- Perfis de acesso: ADMIN, GESTOR, ANALISTA, VISUALIZADOR

### 2. Cadastros (Dimensoes)
- Centro de Custo
- Contas Contabeis
- Projetos/Eventos
- Categorias de Atletas
- Usuarios (ADMIN)

### 3. Modulo Orcamento
- Visualizacao do orcamento anual/mensal
- Resumo de receitas e despesas

### 4. Modulo Atletas
- Dashboard de atletas por evento
- Comparativo orcado x projetado x realizado

### 5. Dashboard Consolidado
- KPIs financeiros
- Graficos de evolucao mensal
- Distribuicao por tipo
- Atletas por modalidade e projeto

### 6. Marketing Performance (ISC Dashboard)
Dashboard para area de Marketing acompanhar vendas de inscricoes de eventos de corrida.

**Metrica Principal: ISC (Indice de Saude Comercial)**
- 🟢 Acelerando (ISC > 1.10) - evento forte, pode subir preco
- 🟡 Estavel (ISC 0.90 a 1.10) - manter/ajustar comunicacao
- 🔴 Desacelerando (ISC < 0.90) - evento fraco, reforcar demanda

**Componentes do ISC:**
- IA 7/30 (Indice de Aceleracao): Vendas 7 dias / Vendas 30 dias × (30/7)
- Curva D-%: Vendas reais acumuladas / Vendas esperadas
- Rolling 14d: Media de vendas dos ultimos 14 dias (normalizada)

**Regra de Negocio D-40:**
- D-40 e a ultima janela para promocoes
- Diagnostico ate D-45, acao ate D-40
- Apos D-40: NUNCA fazer promocao (apenas comunicacao ou preco para cima)

**Telas:**
- Dashboard Geral: tabela de eventos com ISC, filtros e cards resumo
- Detalhe do Evento: gauge ISC, graficos de vendas, timeline de acoes
- Comparativo: comparacao lado a lado de ate 4 eventos
- Configuracoes: pagina completa de configuracoes com 5 modulos

**Modulo de Configuracoes (Marketing Performance):**
- Definicao de Metas por Evento: editar metas de vendas, receita, conversao e ticket medio
- Curvas de Benchmark: configurar curvas de referencia (agressiva, moderada, conservadora)
- Parametros ISC: ajustar pesos dos componentes e limiares de classificacao
- Categorias de Eventos: gerenciar categorias com cores, capacidade e precos padrao
- Alertas Automaticos: configurar notificacoes para eventos criticos (email, SMS, push, Slack)

## Credenciais de Teste
- **Admin:** admin@cscdoesporte.com / admin123
- **Gestor:** gestor@cscdoesporte.com / gestor123

## Como Executar

### Backend (porta 8000)
```bash
cd backend && python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### Frontend (porta 5000)
```bash
cd frontend && npm run dev
```

## API Endpoints

### Autenticacao
- POST /api/auth/login - Login
- GET /api/auth/me - Usuario atual

### Cadastros
- GET/POST/PUT/DELETE /api/centros-custo/
- GET/POST/PUT/DELETE /api/contas/
- GET/POST/PUT/DELETE /api/projetos/
- GET/POST/PUT/DELETE /api/categorias-atletas/
- GET/POST/PUT/DELETE /api/users/

### Fatos
- GET/POST/PUT/DELETE /api/orcamento/
- GET/POST/PUT /api/projecao/
- GET/POST/DELETE /api/realizado/
- GET/POST/PUT/DELETE /api/atletas/

### Atletas Satelite (Tabelas Normalizadas)
- GET/POST/PUT/DELETE /api/atletas-satelite/metricas/ - Metricas principais (qtd_atletas, tkt_medio, inscricao, custo_kit)
- GET/POST/PUT/DELETE /api/atletas-satelite/canais/ - Metricas por canal (SITE, GRUPOS, APPAI)
- GET/POST/PUT/DELETE /api/atletas-satelite/kits/ - Metricas de kits (VIP, PLUS, SUPER, PRODUTO)
- GET/POST/PUT/DELETE /api/atletas-satelite/custos/ - Custos operacionais (AGUA, ISOTONICO, HIDRATACAO, etc)
- POST /api/atletas-satelite/metricas/bulk - Criacao em lote de metricas
- POST /api/atletas-satelite/canais/bulk - Criacao em lote de canais
- POST /api/atletas-satelite/kits/bulk - Criacao em lote de kits
- POST /api/atletas-satelite/custos/bulk - Criacao em lote de custos

### Dashboard
- GET /api/dashboard/resumo-geral
- GET /api/dashboard/evolucao-mensal
- GET /api/dashboard/distribuicao-tipo
- GET /api/dashboard/atletas-por-modalidade
- GET /api/dashboard/atletas-por-projeto

## Banco de Dados

### Tabelas Dimensionais
- dim_tempo
- dim_centro_custo
- dim_conta
- dim_projeto
- dim_categoria_atleta
- dim_usuario

### Tabelas Fato
- fato_orcamento
- fato_projecao
- fato_realizado

### Tabelas de Atletas (Estrutura Direta)
As metricas de atletas estao organizadas em 4 tabelas com vinculo direto a projeto_id:

- **fato_atletas_metricas** - Metricas principais por cenario
  - Campos: projeto_id, categoria_atleta_id, tempo_id, cenario (ORCADO/PROJETADO/REALIZADO), versao_projecao
  - Metricas: qtd_atletas, qtd_atletas_pago, qtd_atletas_cortesia, tkt_medio, inscricao, custo_kit_unitario

- **fato_atletas_canais** - Metricas por canal de distribuicao
  - Campos: projeto_id, categoria_atleta_id, tempo_id, canal (SITE/GRUPOS/APPAI), cenario, versao_projecao
  - Metricas: qtd_atletas, tkt_medio, inscricao

- **fato_atletas_kits** - Metricas de kits
  - Campos: projeto_id, categoria_atleta_id, tempo_id, tipo_kit (VIP/PLUS/SUPER/PRODUTO), cenario, versao_projecao
  - Metricas: qtd_kit, tkt_medio, inscricao, custo_unitario

- **fato_atletas_custos** - Custos operacionais por atleta
  - Campos: projeto_id, categoria_atleta_id, tempo_id, tipo_custo (AGUA/ISOTONICO/HIDRATACAO/etc), cenario, versao_projecao
  - Metricas: custo_unitario, qtd_por_atleta, custo_total

### 7. Atletas Externos (MySQL via SSH Tunnel)
Endpoint para busca de dados de atletas do banco MySQL externo em tempo real.

**Endpoints:**
- GET /api/atletas-externos/resumo - Resumo geral com filtros
- GET /api/atletas-externos/por-evento - Dados agrupados por evento
- GET /api/atletas-externos/por-projeto/{codigo_sku} - Dados de um projeto específico
- GET /api/atletas-externos/vincular-projetos - Lista projetos internos para vinculação
- DELETE /api/atletas-externos/cache - Limpar cache

**Recursos:**
- Cache em memória com TTL de 5 minutos
- Proteção contra SQL injection com parâmetros vinculados
- Validação de formato de datas e SKUs
- Vinculação via id_campanha_salesforce (externo) = dim_projeto.codigo (interno)

### 8. Nori - Assistente Virtual
Assistente virtual inteligente por voz integrado ao sistema.

**Funcionalidades:**
- Analise de cenario dos eventos por IA (GPT-4o-mini)
- Reconhecimento de voz (Speech-to-Text) via Web Speech API
- Sintese de voz (Text-to-Speech) para respostas faladas
- Chat conversacional com contexto dos dados de marketing
- Sistema de agendamento de tarefas integrado

**Tecnologias:**
- OpenAI GPT-4o-mini para processamento de linguagem natural
- Web Speech API para reconhecimento de voz no navegador
- SpeechSynthesis API para sintese de voz em portugues brasileiro

**Telas:**
- Pagina do Assistente (/nori): dashboard de tarefas + chat com Nori
- Botao flutuante em todas as paginas para acesso rapido ao chat

**Endpoints:**
- GET /api/nori/greeting - Saudacao personalizada
- POST /api/nori/chat - Conversa com contexto
- POST /api/nori/analyze - Analise de dados de marketing
- CRUD /api/tarefas/ - Gerenciamento de tarefas

## Ultimas Modificacoes
- 29/01/2026: Tela Admin de Dados Consolidados
  - Nova pagina /admin/dados-consolidados para analise de dados de inscricoes
  - Tabela com SKU, evento, quantidades e valores de ambas fontes (Ativo e Magento)
  - Filtros por SKU, nome do evento e fonte de dados
  - Ordenacao por todas as colunas
  - Exportacao para CSV
  - Modal de detalhes com breakdown por fonte
  - Acessivel apenas para usuarios ADMIN via menu lateral

- 29/01/2026: Normalizacao de SKU para Consolidacao Multi-Database
  - Funcao normalize_sku() extrai codigo base do evento (ex: EVSOL26SP1MB-5Km -> SOL26SP1)
  - Padrao regex: 2-4 letras + 2 digitos (ano) + 2-3 letras (cidade) + 1 digito (edicao)
  - Dados de fontes diferentes agora consolidados corretamente por evento
  - Exemplo: SOL26SP1 mostra 8.934 inscritos (2.139 Ativo + 6.795 Magento)

- 29/01/2026: Endpoint de Inscricoes Consolidadas (Multi-Database)
  - Novo endpoint /api/inscricoes/consolidado que agrega dados dos bancos Ativo e Magento
  - Retorna totais consolidados com breakdown por fonte (por_fonte: {ativo, magento})
  - Frontend atualizado com inscricoesConsolidadasService e tipos TypeScript
  - Modal de projetos exibe dados consolidados com tooltips mostrando origem dos dados
  - Parametro incluir_magento para habilitar consulta ao Magento (desabilitado por padrao por lentidao)
  - Query Magento otimizada com timeout de 60 segundos para evitar travamentos

- 28/01/2026: Integracao Frontend para Dados de Atletas Externos
  - Novo servico atletasExternosService em api.ts com tipos TypeScript
  - Modal de detalhes do projeto exibe dados em tempo real do banco MySQL externo
  - Secao "Dados em Tempo Real" mostra: inscritos, receita, locais de inscricao, top categorias
  - Botao de atualizar para refresh manual (limpa cache e busca dados novos)
  - Tratamento de erros e estados de loading

- 28/01/2026: Implementacao de Conexao SSH Tunnel para Banco de Dados Externo
  - Configuracao de tunel SSH usando Paramiko para acesso seguro a banco MySQL externo
  - Suporte a chaves SSH Ed25519, RSA e ECDSA
  - Endpoints de teste: GET /api/ssh/test e GET /api/ssh/tables
  - Lifecycle management com abertura e fechamento automatico do tunel
  - Secrets configurados: SSH_HOST, SSH_PORT, SSH_USER, SSH_PRIVATE_KEY, DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD

- 13/01/2026: Implementacao do Nori - Assistente Virtual por Voz
  - Backend: servico de IA com OpenAI, endpoints para chat e analise
  - Frontend: componente de chat com reconhecimento e sintese de voz
  - Sistema de tarefas: modelo, API CRUD, interface de gerenciamento
  - Integracao ao menu lateral e botao flutuante em todas as paginas

- 09/01/2026: Implementacao completa do Modulo de Configuracoes do Marketing Performance
  - Definicao de Metas por Evento: tabela editavel com metas de vendas e receita
  - Curvas de Benchmark: visualizacao e edicao de curvas de referencia com grafico SVG
  - Parametros ISC: ajuste de pesos (IA 7/30, Curva D-%, Rolling 14d) e limiares de cor
  - Categorias de Eventos: CRUD completo com cores e precos padrao
  - Alertas Automaticos: configuracao de condicoes e canais de notificacao
  - Novos arquivos: marketingSettings.ts, mockMarketingSettings.ts, 5 componentes de settings
  - Navegacao por tabs integrada na pagina MarketingSettings.tsx

- 09/01/2026: Adicao do Dashboard Marketing Performance (ISC)
  - Nova secao no menu lateral com Dashboard ISC, Comparativo e Configuracoes
  - Tipos e dados mock em frontend/src/types/marketingPerformance.ts e frontend/src/data/mockMarketingData.ts
  - Paginas: MarketingDashboard.tsx, EventDetail.tsx, EventComparison.tsx, MarketingSettings.tsx
  - Calculo do ISC com IA 7/30, Curva D-% e Rolling 14d
  - Regra D-40 para janela de promocoes implementada
  - Graficos com Recharts (curva de vendas, vendas diarias)

- 07/01/2026: Remocao da tabela intermediaria fato_atletas
  - Tabela fato_atletas foi removida do modelo de dados
  - Campos projeto_id, categoria_atleta_id, tempo_id, versao_projecao, created_by adicionados diretamente nas 4 tabelas satelite
  - Rotas da API refatoradas para usar projeto_id diretamente
  - Script de migracao SQL criado para bancos existentes (backend/migrations/001_remove_fato_atletas.sql)
- 06/01/2025: Correcao de valores zerados no modal de detalhes de projetos
  - Endpoint /api/projetos/com-atletas agora retorna qtd_atletas_orcado e qtd_atletas_projetado
  - Adicionadas subqueries para buscar atletas dos 3 cenarios (ORCADO, PROJETADO, REALIZADO)
  - Schema ProjetoComAtletasResponse atualizado com os novos campos

- 06/01/2025: Padronizacao do layout moderno em todas as telas
  - Aplicado design consistente: fundo animado, cabecalhos gradiente, cards modernos
  - Telas atualizadas: CentrosCusto, Contas, CategoriasAtletas, Orcamento, Atletas, Dashboard
  - Suporte completo para temas claro/escuro

- 29/12/2024: Adicao de tabelas satelite para atletas
  - Criacao de fato_atletas_canais, fato_atletas_kits, fato_atletas_custos
  - Endpoints CRUD e bulk para as novas tabelas
  - Normalizacao das 95 colunas pendentes em estrutura extensivel

- 29/12/2024: Criacao do sistema completo
  - Backend FastAPI com todas as rotas
  - Frontend React com Tailwind CSS
  - Autenticacao JWT
  - Dashboard com graficos Recharts
  - Dados de exemplo populados
