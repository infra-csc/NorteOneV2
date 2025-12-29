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

## Ultimas Modificacoes
- 29/12/2024: Criacao do sistema completo
  - Backend FastAPI com todas as rotas
  - Frontend React com Tailwind CSS
  - Autenticacao JWT
  - Dashboard com graficos Recharts
  - Dados de exemplo populados
