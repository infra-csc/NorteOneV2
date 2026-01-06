# DW Financeiro - Sistema de Gestao de Data Warehouse para Eventos

## Overview
Sistema web completo para gerenciamento de Data Warehouse financeiro de uma empresa de eventos. O sistema e a "fonte unica de verdade" (Single Source of Truth) para dados orcamentarios, projecoes e realizados.

## Stack Tecnologica
- **Backend:** Python com FastAPI
- **Frontend:** React com TypeScript e Tailwind CSS
- **Banco de Dados:** PostgreSQL
- **ORM:** SQLAlchemy
- **Autenticacao:** JWT
- **Graficos:** Recharts

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
    /pages         - Paginas da aplicacao
    /services      - Servicos de API
    /types         - Definicoes TypeScript
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
- fato_atletas

### Tabelas Satelite de Atletas (Normalizadas)
As metricas detalhadas de atletas foram normalizadas em 4 tabelas satelite para melhor organizacao e extensibilidade:

- **fato_atletas_metricas** - Metricas principais por cenario
  - Campos: fato_atletas_id, cenario (ORCADO/PROJETADO/REALIZADO)
  - Metricas: qtd_atletas, qtd_atletas_pago, qtd_atletas_cortesia, tkt_medio, inscricao, custo_kit_unitario

- **fato_atletas_canais** - Metricas por canal de distribuicao
  - Campos: fato_atletas_id, canal (SITE/GRUPOS/APPAI), cenario (ORCADO/PROJETADO/REALIZADO)
  - Metricas: qtd_atletas, tkt_medio, inscricao

- **fato_atletas_kits** - Metricas de kits
  - Campos: fato_atletas_id, tipo_kit (VIP/PLUS/SUPER/PRODUTO), cenario
  - Metricas: qtd_kit, tkt_medio, inscricao, custo_unitario

- **fato_atletas_custos** - Custos operacionais por atleta
  - Campos: fato_atletas_id, tipo_custo (AGUA/ISOTONICO/HIDRATACAO/NUMERO_PEITO/CHIP/ALFINETE/IDENTIFICACAO), cenario
  - Metricas: custo_unitario, qtd_por_atleta, custo_total

## Ultimas Modificacoes
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
