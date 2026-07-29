import axios from 'axios';

const api = axios.create({
  baseURL: '/api',
  headers: {
    'Content-Type': 'application/json',
  },
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('token');
      localStorage.removeItem('user');
      window.location.href = '/login';
    }
    if (error.response?.status === 429) {
      const retryAfter = error.response.data?.retry_after ?? 60;
      const rawDetail = error.response.data?.detail;
      // Se o backend devolveu detail como objeto estruturado (ex.: gate de
      // reconsolidação com {code, message, remaining_sec}), o handler de origem
      // precisa enxergar isso. Mensagem amigável vira o texto do Error.
      const detailText = typeof rawDetail === 'string'
        ? rawDetail
        : (rawDetail?.message ?? `Muitas requisições. Aguarde ${retryAfter}s.`);
      const enriched = new Error(detailText) as Error & {
        isRateLimit: boolean;
        retryAfter: number;
        blockedBy?: string;
        nextAllowedAt?: string;
        response?: typeof error.response;
        config?: typeof error.config;
      };
      enriched.isRateLimit = true;
      enriched.retryAfter = retryAfter;
      if (error.response.data?.blocked_by) enriched.blockedBy = error.response.data.blocked_by;
      if (error.response.data?.next_allowed_at) enriched.nextAllowedAt = error.response.data.next_allowed_at;
      // Preserva a resposta original para que handlers possam ler detail.code,
      // detail.remaining_sec etc. (necessário p/ cooldown de reconsolidação).
      enriched.response = error.response;
      enriched.config = error.config;
      return Promise.reject(enriched);
    }
    if (error.response?.status === 409) {
      const msg = error.response.data?.message ?? 'Operação já em andamento. Aguarde o término e tente novamente.';
      const enriched = new Error(msg) as Error & { isBusy: boolean };
      enriched.isBusy = true;
      return Promise.reject(enriched);
    }
    return Promise.reject(error);
  }
);

export const authService = {
  login: async (email: string, password: string) => {
    const formData = new URLSearchParams();
    formData.append('username', email);
    formData.append('password', password);
    const response = await api.post('/auth/login', formData, {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' }
    });
    return response.data;
  },
  getMe: async () => {
    const response = await api.get('/auth/me');
    return response.data;
  },
  // Indica se o login via Microsoft está disponível (credenciais configuradas).
  // Timeout curto: essa checagem nunca deve segurar a tela de login. Se o
  // servidor estiver saturado (ex.: fila do Magento), preferimos falhar rápido
  // e cair no estado conhecido/cacheado a deixar o usuário sem botão.
  microsoftStatus: async (): Promise<{ enabled: boolean }> => {
    const response = await api.get('/auth/microsoft/status', { timeout: 6000 });
    return response.data;
  },
  // Inicia o SSO redirecionando o browser para o endpoint do backend, que por
  // sua vez redireciona para a Microsoft (full-page redirect, não XHR).
  microsoftLoginUrl: (): string => {
    const base = (api.defaults.baseURL || '/api').replace(/\/$/, '');
    return `${base}/auth/microsoft/login`;
  },
  logout: async (token: string) => {
    await api.post('/auth/logout', null, {
      headers: { Authorization: `Bearer ${token}` },
    });
  },
};

interface DashboardFilters {
  ano?: number | null;
  mes?: number | null;
  produto?: string | null;
  tipo_evento?: string | null;
  projeto_id?: number | null;
  modalidade?: string | null;
  cidade?: string | null;
}

const buildFilterParams = (filters: DashboardFilters): string => {
  const params = new URLSearchParams();
  if (filters.ano) params.append('ano', filters.ano.toString());
  if (filters.mes) params.append('mes', filters.mes.toString());
  if (filters.produto) params.append('produto', filters.produto);
  if (filters.tipo_evento) params.append('tipo_evento', filters.tipo_evento);
  if (filters.projeto_id) params.append('projeto_id', filters.projeto_id.toString());
  if (filters.modalidade) params.append('modalidade', filters.modalidade);
  if (filters.cidade) params.append('cidade', filters.cidade);
  return params.toString();
};

export const dashboardService = {
  getFiltros: async () => {
    const response = await api.get('/dashboard/filtros');
    return response.data;
  },
  getResumoGeral: async (filters: DashboardFilters) => {
    const params = buildFilterParams(filters);
    const response = await api.get(`/dashboard/resumo-geral?${params}`);
    return response.data;
  },
  getConsolidado: async (filters: DashboardFilters) => {
    const params = buildFilterParams(filters);
    const response = await api.get(`/dashboard/consolidado?${params}`);
    return response.data;
  },
  getOperacional: async (filters: { ano?: number | null; mes?: number | null; produto?: string | null; modalidade?: string | null; cidade?: string | null }) => {
    const params = new URLSearchParams();
    if (filters.ano) params.append('ano', filters.ano.toString());
    if (filters.mes) params.append('mes', filters.mes.toString());
    if (filters.produto) params.append('produto', filters.produto);
    if (filters.modalidade) params.append('modalidade', filters.modalidade);
    if (filters.cidade) params.append('cidade', filters.cidade);
    const response = await api.get(`/dashboard/operacional?${params.toString()}`);
    return response.data;
  },
  getFinanceiro: async (filters: { ano?: number | null; mes?: number | null; produto?: string | null; modalidade?: string | null; cidade?: string | null }) => {
    const params = new URLSearchParams();
    if (filters.ano) params.append('ano', filters.ano.toString());
    if (filters.mes) params.append('mes', filters.mes.toString());
    if (filters.produto) params.append('produto', filters.produto);
    if (filters.modalidade) params.append('modalidade', filters.modalidade);
    if (filters.cidade) params.append('cidade', filters.cidade);
    const response = await api.get(`/dashboard/financeiro?${params.toString()}`);
    return response.data;
  },
  getRelatorioFinanceiro: async (filters: { ano?: number | null; mes?: number | null; produto?: string | null; modalidade?: string | null; cidade?: string | null }) => {
    const params = new URLSearchParams();
    if (filters.ano) params.append('ano', filters.ano.toString());
    if (filters.mes) params.append('mes', filters.mes.toString());
    if (filters.produto) params.append('produto', filters.produto);
    if (filters.modalidade) params.append('modalidade', filters.modalidade);
    if (filters.cidade) params.append('cidade', filters.cidade);
    const response = await api.get(`/dashboard/relatorio-financeiro?${params.toString()}`);
    return response.data;
  },
  getCamposDashboard: async () => {
    const response = await api.get('/perfis-acesso/campos-dashboard');
    return response.data;
  },
  getInscricoesDiarias: async (ano?: number | null) => {
    const params = new URLSearchParams();
    if (ano) params.append('ano', ano.toString());
    const response = await api.get(`/dashboard/inscricoes-diarias?${params.toString()}`);
    return response.data;
  },
};

export const centrosCustoService = {
  list: async () => {
    const response = await api.get('/centros-custo/');
    return response.data;
  },
  create: async (data: any) => {
    const response = await api.post('/centros-custo/', data);
    return response.data;
  },
  update: async (id: number, data: any) => {
    const response = await api.put(`/centros-custo/${id}`, data);
    return response.data;
  },
  delete: async (id: number) => {
    const response = await api.delete(`/centros-custo/${id}`);
    return response.data;
  }
};

export const projetosService = {
  list: async (params?: Record<string, string>) => {
    const query = new URLSearchParams(params || {}).toString();
    const response = await api.get(`/projetos/${query ? `?${query}` : ''}`);
    return response.data;
  },


  getFiltros: async () => {
    try {
      const response = await api.get('/projetos/filtros');
      return response.data;
    } catch (error: any) {
      // Se o endpoint não existir, retorna valores padrão
      if (error.response?.status === 404) {
        console.warn('Endpoint /projetos/filtros não encontrado, usando valores padrão');
        return {
          modalidades: ['BEACH', 'CICLISMO', 'CORRIDA', 'CULTURA', 'EDUCACAO', 'E-SPORTS', 'FAMILIA', 'NATACAO', 'OBSTACULO', 'SAUDE', 'TRIATHLON'],
          tipos_evento: ['PROPRIO', 'INCENTIVO', 'ORGANIZACAO', 'LICENCIADO'],
          leis: ['LIE', 'PIE', 'FIA', 'ICMS RJ', 'PROAC', 'PRONAC', 'ROUANET', 'ISS RJ'],
          estados: [],
          cidades: [],
          anos: [],
          status: ['EM_ANDAMENTO', 'CONCLUIDO', 'CANCELADO']
        };
      }
      throw error;
    }
  },

  create: async (data: any) => {
    const response = await api.post('/projetos/', data);
    return response.data;
  },
  update: async (id: number, data: any) => {
    const response = await api.put(`/projetos/${id}`, data);
    return response.data;
  },
  delete: async (id: number) => {
    const response = await api.delete(`/projetos/${id}`);
    return response.data;
  }
};

export const categoriasAtletasService = {
  list: async () => {
    const response = await api.get('/categorias-atletas/');
    return response.data;
  },
  create: async (data: any) => {
    const response = await api.post('/categorias-atletas/', data);
    return response.data;
  },
  update: async (id: number, data: any) => {
    const response = await api.put(`/categorias-atletas/${id}`, data);
    return response.data;
  },
  delete: async (id: number) => {
    const response = await api.delete(`/categorias-atletas/${id}`);
    return response.data;
  }
};

export const usersService = {
  list: async (params?: { q?: string; skip?: number; limit?: number; ativo?: boolean }) => {
    const response = await api.get('/users/', { params });
    return response.data;
  },
  create: async (data: any) => {
    const response = await api.post('/users/', data);
    return response.data;
  },
  update: async (id: number, data: any) => {
    const response = await api.put(`/users/${id}`, data);
    return response.data;
  },
  delete: async (id: number) => {
    const response = await api.delete(`/users/${id}`);
    return response.data;
  }
};


export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

export const noriService = {
  getGreeting: async () => {
    const response = await api.get('/nori/greeting');
    return response.data;
  },
  chat: async (message: string, context?: ChatMessage[], eventsData?: any[]) => {
    const response = await api.post('/nori/chat', {
      message,
      context,
      events_data: eventsData
    });
    return response.data;
  },
  analyze: async (eventsData: any[]) => {
    const response = await api.post('/nori/analyze', {
      events_data: eventsData
    });
    return response.data;
  }
};

export interface NoriInsightContexto {
  vendas_atuais?: number;
  meta_vendas?: number;
  pct_vendas_meta?: number;
  ticket_medio_realizado?: number;
  ticket_orcado?: number;
  ticket_atual_magento?: number;
  custo_kit?: number;
  margem_bruta_pct?: number;
  margem_orcada_bruta_pct?: number;
  margem_realizacao_rate_pct?: number;
  'margem_realizada_total_R$'?: number;
  'margem_orcada_total_R$'?: number;
  // Campos legados (formato anterior — mantidos para compatibilidade com insights antigos)
  margem_realizada_pct?: number;
  margem_orcada_pct?: number;
  isc?: number;
  d_minus?: number;
}

export interface NoriInsight {
  id: number;
  evento_id?: string;
  evento_nome: string;
  tipo: string;
  titulo: string;
  conteudo: string;
  acao_sugerida?: string;
  impacto_estimado_reais?: number;
  impacto_estimado_percentual?: number;
  dados_contexto?: NoriInsightContexto;
  status: 'novo' | 'visto' | 'descartado';
  gerado_em: string;
}

export const noriInsightsService = {
  list: async (status?: string, tipo?: string): Promise<NoriInsight[]> => {
    const params = new URLSearchParams();
    if (status) params.append('status', status);
    if (tipo) params.append('tipo', tipo);
    const response = await api.get(`/nori/insights?${params.toString()}`);
    return response.data;
  },
  updateStatus: async (id: number, status: string) => {
    const response = await api.patch(`/nori/insights/${id}?status=${status}`);
    return response.data;
  },
  delete: async (id: number) => {
    const response = await api.delete(`/nori/insights/${id}`);
    return response.data;
  },
  generate: async () => {
    const response = await api.post('/nori/insights/gerar');
    return response.data;
  },
  clearOld: async (dias = 30, status = 'descartado') => {
    const response = await api.delete(`/nori/insights?dias=${dias}&status=${status}`);
    return response.data;
  },
};

export interface ResponsavelInfo {
  id: number;
  nome: string;
  email: string;
}

export interface UsuarioInfo {
  id: number;
  nome: string;
  email: string;
}

export interface Tarefa {
  id: number;
  titulo: string;
  descricao?: string;
  data_vencimento?: string;
  hora_lembrete?: string;
  prioridade: 'BAIXA' | 'MEDIA' | 'ALTA' | 'URGENTE';
  status: 'PENDENTE' | 'EM_ANDAMENTO' | 'CONCLUIDA' | 'CANCELADA';
  criado_por_nori: boolean;
  usuario_id: number;
  responsavel_id?: number;
  responsavel?: UsuarioInfo;
  usuario?: UsuarioInfo;
  dados_analise?: string;
  created_at: string;
  updated_at: string;
}

export interface TarefaCreate {
  titulo: string;
  descricao?: string;
  data_vencimento?: string;
  hora_lembrete?: string;
  prioridade?: 'BAIXA' | 'MEDIA' | 'ALTA' | 'URGENTE';
  criado_por_nori?: boolean;
  responsavel_id?: number;
  dados_analise?: string;
}

export const cadastrosService = {
  list: async (status?: string) => {
    const params = status ? `?status=${status}` : '';
    const response = await api.get(`/cadastros/${params}`);
    return response.data;
  },
  get: async (id: number) => {
    const response = await api.get(`/cadastros/${id}`);
    return response.data;
  },
  create: async (data: any) => {
    const response = await api.post('/cadastros/', data);
    return response.data;
  },
  update: async (id: number, data: any) => {
    const response = await api.put(`/cadastros/${id}`, data);
    clearMarketingDashboardCache();
    return response.data;
  },
  delete: async (id: number) => {
    const response = await api.delete(`/cadastros/${id}`);
    return response.data;
  },
  listLixeira: async () => {
    const response = await api.get('/cadastros/lixeira/itens');
    return response.data;
  },
  restore: async (id: number) => {
    const response = await api.post(`/cadastros/${id}/restaurar`);
    return response.data;
  },
  getCircuitos: async () => {
    const response = await api.get('/cadastros/opcoes/circuitos');
    return response.data;
  },
  createCircuito: async (nome: string) => {
    const response = await api.post('/cadastros/opcoes/circuitos', { nome });
    return response.data;
  },
  updateCircuito: async (id: number, nome: string) => {
    const response = await api.put(`/cadastros/opcoes/circuitos/${id}`, { nome });
    return response.data;
  },
  deleteCircuito: async (id: number) => {
    const response = await api.delete(`/cadastros/opcoes/circuitos/${id}`);
    return response.data;
  },
  getLocalizacoes: async () => {
    const response = await api.get('/cadastros/opcoes/localizacoes');
    return response.data;
  },
  createLocalizacao: async (nome: string) => {
    const response = await api.post('/cadastros/opcoes/localizacoes', { nome });
    return response.data;
  },
  updateLocalizacao: async (id: number, nome: string) => {
    const response = await api.put(`/cadastros/opcoes/localizacoes/${id}`, { nome });
    return response.data;
  },
  deleteLocalizacao: async (id: number) => {
    const response = await api.delete(`/cadastros/opcoes/localizacoes/${id}`);
    return response.data;
  }
};

export const tarefasService = {
  list: async (status?: string, prioridade?: string) => {
    const params = new URLSearchParams();
    if (status) params.append('status', status);
    if (prioridade) params.append('prioridade', prioridade);
    const response = await api.get(`/tarefas/?${params.toString()}`);
    return response.data;
  },
  getPendentes: async () => {
    const response = await api.get('/tarefas/pendentes');
    return response.data;
  },
  getHoje: async () => {
    const response = await api.get('/tarefas/hoje');
    return response.data;
  },
  getResumo: async () => {
    const response = await api.get('/tarefas/resumo');
    return response.data;
  },
  getDelegadas: async (status?: string) => {
    const params = new URLSearchParams();
    if (status) params.append('status', status);
    const response = await api.get(`/tarefas/delegadas?${params.toString()}`);
    return response.data;
  },
  get: async (id: number) => {
    const response = await api.get(`/tarefas/${id}`);
    return response.data;
  },
  create: async (tarefa: TarefaCreate) => {
    const response = await api.post('/tarefas/', tarefa);
    return response.data;
  },
  update: async (id: number, tarefa: Partial<TarefaCreate>) => {
    const response = await api.put(`/tarefas/${id}`, tarefa);
    return response.data;
  },
  concluir: async (id: number) => {
    const response = await api.put(`/tarefas/${id}/concluir`);
    return response.data;
  },
  delete: async (id: number) => {
    const response = await api.delete(`/tarefas/${id}`);
    return response.data;
  }
};

export interface AtletaExternoPorCategoria {
  categoria: string;
  qtd: number;
  receita: number;
}

export interface AtletaExternoPorLocal {
  local: string;
  qtd: number;
  receita: number;
}

export interface AtletaExternoPorDia {
  data: string | null;
  qtd: number;
  receita: number;
}

export interface AtletaExternoPorProjeto {
  sku: string;
  evento: string | null;
  data_evento: string | null;
  qtd_total: number;
  receita_total: number;
  por_categoria: AtletaExternoPorCategoria[];
  por_local: AtletaExternoPorLocal[];
  por_dia: AtletaExternoPorDia[];
}

export interface AtletaExternoResponse {
  status: string;
  cached: boolean;
  data: AtletaExternoPorProjeto;
}

export const atletasExternosService = {
  getByProjeto: async (codigoSku: string, dataInicio?: string, dataFim?: string): Promise<AtletaExternoResponse> => {
    const params = new URLSearchParams();
    if (dataInicio) params.append('data_inicio', dataInicio);
    if (dataFim) params.append('data_fim', dataFim);
    const queryString = params.toString() ? `?${params.toString()}` : '';
    const response = await api.get(`/atletas-externos/por-projeto/${codigoSku}${queryString}`);
    return response.data;
  },
  getResumo: async (idEvento?: number, sku?: string, dataInicio?: string, dataFim?: string) => {
    const params = new URLSearchParams();
    if (idEvento) params.append('id_evento', idEvento.toString());
    if (sku) params.append('sku', sku);
    if (dataInicio) params.append('data_inicio', dataInicio);
    if (dataFim) params.append('data_fim', dataFim);
    const response = await api.get(`/atletas-externos/resumo?${params.toString()}`);
    return response.data;
  },
  clearCache: async () => {
    const response = await api.delete('/atletas-externos/cache');
    return response.data;
  }
};

export const kitConfigService = {
  getUnconfiguredSummary: async (): Promise<{
    total_unconfigured: number;
    events: Array<{ nome_evento: string; count: number }>;
    magento_available: boolean;
  }> => {
    const response = await api.get('/kit-config/unconfigured-summary');
    return response.data;
  },
};

export const adminService = {
  getUserActivity: async () => {
    const response = await api.get('/admin/user-activity');
    return response.data;
  },
  syncMicrosoftDirectory: async () => {
    const response = await api.post('/admin/usuarios/sincronizar-microsoft');
    return response.data;
  },
  getHealthSummary: async () => {
    const response = await api.get('/admin/health-events/summary');
    return response.data;
  },
  getHealthEvents: async (params?: { severity?: string; event_type?: string; date_from?: string; date_to?: string; show_resolved?: string; page?: number; page_size?: number }) => {
    const response = await api.get('/admin/health-events', { params });
    return response.data;
  },
  resolveHealthEvent: async (eventId: number) => {
    const response = await api.post(`/admin/health-events/${eventId}/resolve`);
    return response.data;
  },
  reopenHealthEvent: async (eventId: number) => {
    const response = await api.post(`/admin/health-events/${eventId}/reopen`);
    return response.data;
  },
  getAlertConfig: async () => {
    const response = await api.get('/admin/alert-config');
    return response.data;
  },
  updateAlertConfig: async (config: object) => {
    const response = await api.put('/admin/alert-config', config);
    return response.data;
  },
  testAlert: async () => {
    const response = await api.post('/admin/alert-config/test');
    return response.data;
  },
  getSyncCycles: async (params?: { job?: string; status?: string; limit?: number }) => {
    const response = await api.get('/admin/sync-logs/cycles', { params });
    return response.data as {
      cycles: Array<{
        ciclo_id: string;
        job_name: string;
        iniciado_em: string | null;
        concluido_em: string | null;
        ultima_atividade: string | null;
        status: string;
        duracao_ms: number | null;
        detalhes: string | null;
        motivo: string | null;
        total_grupos: number;
        ok: number;
        parcial: number;
        falha: number;
        pulado: number;
      }>;
    };
  },
  getSyncCycleDetail: async (cicloId: string) => {
    const response = await api.get(`/admin/sync-logs/${encodeURIComponent(cicloId)}`);
    return response.data as {
      ciclo_id: string;
      events: Array<{
        id: number;
        nivel: string;
        job_name: string;
        grupo: string | null;
        fonte: string | null;
        status: string;
        motivo: string | null;
        detalhes: string | null;
        qtd_antes: number | null;
        qtd_depois: number | null;
        data_floor: string | null;
        duracao_ms: number | null;
        created_at: string;
      }>;
    };
  },
  triggerSnapshotConsolidation: async () => {
    const response = await api.post('/admin/snapshots/consolidar');
    return response.data as { status: string; message: string };
  },
  triggerSnapshotConsolidationFull: async (incremental: boolean = false, resume: boolean = false) => {
    const response = await api.post(
      `/admin/snapshots/consolidar-full?incremental=${incremental}&resume=${resume}`,
      null,
      { timeout: 30000 }
    );
    return response.data as { status: string; message: string };
  },
  getSnapshotConsolidationCheckpoint: async () => {
    const response = await api.get('/admin/snapshots/consolidar-full/checkpoint', { timeout: 10000 });
    return response.data as
      | { resumable: false }
      | {
          resumable: true;
          ciclo_id: string;
          incremental: boolean;
          triggered_by: string | null;
          started_at_cycle: string | null;
          ok_count: number;
          failed_count: number;
          last_grupo: string | null;
          last_processed_at: string | null;
        };
  },
  getSnapshotConsolidationFullProgress: async () => {
    const response = await api.get('/admin/snapshots/consolidar-full/progress', { timeout: 10000 });
    return response.data as {
      status: 'idle' | 'running' | 'done' | 'error';
      started_at: number | null;
      finished_at: number | null;
      triggered_by: string | null;
      incremental: boolean;
      total: number;
      current: number;
      current_grupo: string | null;
      ok: number;
      failed: number;
      skipped: number;
      frozen: number;
      ciclo_id: string | null;
      error: string | null;
      results: Array<{
        grupo: string;
        status: 'ok' | 'failed' | 'skipped';
        motivo: string | null;
        qtd_antes: number | null;
        qtd_depois: number | null;
        duracao_ms: number | null;
        detalhes: string | null;
      }>;
    };
  },
  consolidarEvento: async (eventoGrupo: string, incremental: boolean = false) => {
    // Dispara em BACKGROUND no servidor (retorna {status:'started'} na hora).
    // Acompanhar via marketingService.aguardarRecalcularSnapshot(eventoGrupo) —
    // o job fica registrado sob o nome do grupo. Antes era síncrono (5 min de
    // timeout) e o proxy cortava a conexão com 502 quando o Magento estava lento.
    const response = await api.post(
      `/admin/snapshots/consolidar-evento?evento_grupo=${encodeURIComponent(eventoGrupo)}&incremental=${incremental}`,
      null,
      { timeout: 60000 }
    );
    return response.data as {
      status: string;
      evento_grupo: string;
      incremental: boolean;
      ciclo_id?: string;
      // Campos legados (resposta síncrona antiga):
      qtd_antes?: number | null;
      qtd_depois?: number | null;
      duracao_ms?: number;
    };
  },
  getSyncPauseStatus: async () => {
    const response = await api.get('/admin/sync/pause-status');
    return response.data as { paused: boolean; by: string | null; since: string | null };
  },
  getSyncOverview: async () => {
    const response = await api.get('/admin/sync/overview');
    return response.data as {
      scheduled_jobs: Array<{
        key: string;
        label: string;
        next_run_iso: string | null;
        seconds_until: number | null;
        tipo: 'fixo' | 'rede_seguranca' | 'tick';
        descricao: string;
        atrasado: boolean;
        ultima_exec_iso: string | null;
      }>;
      today_summary: {
        eventos_sincronizados: number;
        eventos_ok: number;
        eventos_parcial: number;
        eventos_falha: number;
        eventos_pulado: number;
        ultimo_sync_iso: string | null;
        eventos_recentes: Array<{ grupo: string; status: string; ts: string }>;
        historico_jobs_by_name: {
          sincronizar_hoje: Array<{
            started_at: string | null;
            duration_ms: number;
            grupos_total: number;
            grupos_ok: number;
            grupos_parcial: number;
            grupos_falha: number;
            status: string;
          }>;
          snapshot_diario: Array<{
            started_at: string | null;
            duration_ms: number;
            grupos_total: number;
            grupos_ok: number;
            grupos_parcial: number;
            grupos_falha: number;
            status: string;
          }>;
        };
      };
      kit_mapping: {
        ultima_atualizacao_iso: string | null;
        idade_horas: number | null;
        bundles_com_snapshot: number;
        bundles_esperados: number;
        cobertura_pct: number | null;
        kits_sem_configuracao: number;
        bundles_sem_snapshot_total: number;
        bundles_sem_snapshot_lista: Array<{
          bundle_entity_id: number;
          kit_nome: string | null;
          tipo_kit: string | null;
          id_evento: number | null;
        }>;
        bundles_sem_snapshot_truncated: boolean;
        status: 'ok' | 'atencao' | 'critico';
      };
      generated_at: string;
    };
  },
  getEventosUltimaSync: async () => {
    const response = await api.get('/admin/sync/eventos-ultima-atualizacao');
    return response.data as {
      total: number;
      com_sync: number;
      sem_sync: number;
      generated_at: string;
      eventos: Array<{
        id_cadastro: number;
        nome_evento: string;
        data_evento: string | null;
        status_cadastro: string | null;
        evento_grupo: string | null;
        id_evento_magento: number | null;
        ultima_sync_iso: string | null;
        ultima_sync_status: string | null;
      }>;
    };
  },
  pauseSync: async () => {
    const response = await api.post('/admin/sync/pause');
    return response.data as { status: string; message: string };
  },
  resumeSync: async () => {
    const response = await api.post('/admin/sync/resume');
    return response.data as { status: string; message: string };
  },
  interruptSync: async () => {
    const response = await api.post('/admin/sync/interrupt');
    return response.data as { status: string; message: string; cycles_interrupted: number };
  },
  interruptCycle: async (cicloId: string) => {
    const response = await api.post(`/admin/sync/cycles/${encodeURIComponent(cicloId)}/interrupt`);
    return response.data as { status: string; ciclo_id: string; cycles_interrupted: number };
  },
  interruptCyclesBatch: async (cicloIds: string[]) => {
    const response = await api.post('/admin/sync/cycles/interrupt-batch', { ciclo_ids: cicloIds });
    return response.data as { status: string; cycles_interrupted: number };
  },
};

export interface FonteDisponivel {
  disponivel: boolean;
  erro: string | null;
}

export interface InscricaoFonteDetalhe {
  qtd: number;
  valor: number;
  cortesia: number;
  inscricao_liquida: number;
  ticket_medio: number;
  taxa_liquida: number;
  kit_produto: number;
  qtd_grupos: number;
  inscricao_liquida_grupos: number;
  ticket_medio_grupos: number;
  qtd_site: number;
  inscricao_liquida_site: number;
  ticket_medio_site: number;
}

export interface InscricaoConsolidadaPorFonte {
  ativo?: InscricaoFonteDetalhe;
  magento?: InscricaoFonteDetalhe;
}

export interface InscricaoConsolidada {
  sku: string;
  id_evento: string | null;
  evento: string | null;
  data_evento: string | null;
  categoria_evento: string | null;
  cidade: string | null;
  qtd_vendida_total: number;
  valor_total: number;
  cortesia_total: number;
  inscricao_liquida_total: number;
  ticket_medio_total: number;
  taxa_liquida_total: number;
  kit_produto_total: number;
  qtd_grupos_total: number;
  inscricao_liquida_grupos_total: number;
  qtd_site_total: number;
  inscricao_liquida_site_total: number;
  por_fonte: InscricaoConsolidadaPorFonte;
}

export interface InscricoesConsolidadasResponse {
  status: string;
  total_eventos: number;
  qtd_vendida_total: number;
  valor_total: number;
  fontes_disponiveis: {
    ativo: FonteDisponivel;
    magento: FonteDisponivel;
  };
  dados: InscricaoConsolidada[];
}

export const inscricoesConsolidadasService = {
  getConsolidado: async (sku?: string, incluirMagento: boolean = true, ano: number = 2026): Promise<InscricoesConsolidadasResponse> => {
    const params = new URLSearchParams();
    if (sku) params.append('sku', sku);
    params.append('incluir_magento', incluirMagento ? 'true' : 'false');
    params.append('ano', ano.toString());
    const queryString = params.toString() ? `?${params.toString()}` : '';
    const response = await api.get(`/inscricoes/consolidado${queryString}`);
    return response.data;
  },
  getBySku: async (sku: string, incluirMagento: boolean = true, ano: number = 2026): Promise<InscricaoConsolidada | null> => {
    const data = await inscricoesConsolidadasService.getConsolidado(sku, incluirMagento, ano);
    return data.dados.length > 0 ? data.dados[0] : null;
  }
};

export interface MarketingISCComponents {
  ia730: number;
  curvaDPercent: number;
  rolling14d: number;
  tipoCurva?: string;
  fonteCurva?: string;
  anoReferencia?: number;
}

export interface PlaybookEntry {
  letter: string;
  name: string;
  stageName: string;
  iscLabel: string;
  iscState: 'forte' | 'estável' | 'fraco';
  objective: string;
  narrative: string;
  actions: string[];
  kpis: string[];
  cutoffs: string[];
}

export interface MarketingEvent {
  id: string;
  name: string;
  date: string;
  location: string;
  category: string;
  totalCapacity: number;
  currentSales: number;
  salesGoal: number;
  averageTicket: number;
  budgetTicket: number;
  dMinus: number;
  dMinusInscricoes: number;
  isc: number;
  iscRaw?: number;
  iscComponents: MarketingISCComponents;
  iscComponentsRaw?: MarketingISCComponents;
  iscComponentsNormalized?: MarketingISCComponents;
  iscStatus: 'accelerating' | 'stable' | 'decelerating';
  suggestedAction: PlaybookEntry;
  isActive: boolean;
  sku?: string;
  activeAction?: { id: number; tipo: string; descricao: string; data_acao: string; dias_restantes: number } | null;
  kitCostPerUnit?: number;
  receitaOrcadaTotal?: number;
  currentReceita?: number;
  margemOrcadaUnit?: number;
  margemOrcadaTotal?: number;
  margemOrcadaPct?: number;
  margemRealizadaUnit?: number;
  margemRealizadaTotal?: number;
  margemRealizadaKitsTotal?: number | null;
  margemRealizadaPct?: number;
  ticketAtual?: number;
  ticketKitNome?: string | null;
  dataRegime?: 'consolidated' | 'hybrid' | 'live' | null;
  margemPorKit?: Array<{
    tipoKit: string;
    qtd: number;
    receitaLiquida: number;
    ticketMedio: number;
    ticketAtual: number | null;
    custoKit: number | null;
    margemUnit: number | null;
    margemTotal: number;
  }> | null;
  margemAvisos?: string[] | null;
  consistencyWarning?: {
    totalIsc: number;
    totalMargem: number;
    diff: number;
    diffAbs: number;
    diffPct: number;
    tolerance: number;
  } | null;
  detalheVendasPorKit?: Array<{
    kit: string;
    tipoCategoria: string | null;
    distancia: string | null;
    canal: string;
    loteAtual: string | null;
    price: number | null;
    specialPrice: number | null;
    inscritos: number;
    receitaBruta: number;
    receitaLiquida: number;
    ticketMedio: number | null;
  }> | null;
  detalheVendasAtivoKit?: Array<{
    kit: string;
    tipoCategoria: string | null;
    distancia: string | null;
    canal: string;
    loteAtual: string | null;
    price: number | null;
    specialPrice: number | null;
    inscritos: number;
    receitaBruta: number;
    receitaLiquida: number;
    ticketMedio: number | null;
  }> | null;
  kitQueryFailed?: boolean;
  incluirCortesias?: boolean;
}

export interface MarketingDashboardSummary {
  totalActiveEvents: number;
  eventsGreen: number;
  eventsYellow: number;
  eventsRed: number;
}

export interface MarketingEventsResponse {
  status: string;
  eventos: MarketingEvent[];
  resumo: MarketingDashboardSummary;
  categorias: string[];
  ultima_atualizacao: string;
}

export interface CutoffAlert {
  id: string;
  name: string;
  category: string;
  dMinusInscricoes: number;
  ponto_corte: string;
  estagio: string;
  estagio_label: string;
  isc: number | null;
  iscStatus: string | null;
  acao_definida?: boolean;
  antecipado?: boolean;
}

export interface PricingMetrics {
  rollingIndex: number;
  rollingAvg14d: number;
  rollingAvg14dLastYear: number;
  paceRequired: number;
  ied: number;
  projection: number;
  paceSeguranca: number;
  fem: number;
  ia: number;
}

export interface ElasticityScenario {
  priceIncrease: number;
  newPrice: number;
  newMargin: number;
  acceptableVolumeDrop: number;
  minPace: number;
}

export interface PricingDecision {
  action: 'increase_now' | 'increase_gradual' | 'maintain' | 'decrease';
  reason: string;
  confidence: 'high' | 'medium' | 'low';
}

export interface KitBreakdownItem {
  tipoKit: string;
  custoKit: number | null;
}

export interface PricingEvent {
  id: string;
  name: string;
  date: string;
  location: string;
  category: string;
  totalCapacity: number;
  currentSales: number;
  salesGoal: number;
  averageTicket: number;
  kitCost: number;
  dMinus: number;
  isActive: boolean;
  sku?: string;
  pricingMetrics: PricingMetrics;
  elasticityScenarios: ElasticityScenario[];
  decision: PricingDecision;
  iscStatus: 'accelerating' | 'stable' | 'decelerating';
  kitBreakdown?: KitBreakdownItem[] | null;
}

export interface PricingSummary {
  totalEvents: number;
  eventsToIncrease: number;
  eventsToMaintain: number;
  eventsToDecrease: number;
}

export interface PricingEventsResponse {
  status: string;
  eventos: PricingEvent[];
  resumo: PricingSummary;
  categorias: string[];
  ultima_atualizacao: string;
}

export const pricingService = {
  getAnalysis: async (params?: {
    ano?: number;
    status?: string;
    categoria?: string;
    busca?: string;
  }, signal?: AbortSignal): Promise<PricingEventsResponse> => {
    const queryParams = new URLSearchParams();
    if (params?.ano) queryParams.append('ano', params.ano.toString());
    if (params?.status) queryParams.append('status', params.status);
    if (params?.categoria) queryParams.append('categoria', params.categoria);
    if (params?.busca) queryParams.append('busca', params.busca);
    const queryString = queryParams.toString() ? `?${queryParams.toString()}` : '';
    const response = await api.get(`/marketing/pricing${queryString}`, { signal });
    return response.data;
  }
};

interface CacheEntry<T> {
  data: T;
  timestamp: number;
  key: string;
}

const dashboardCache: Map<string, CacheEntry<MarketingEventsResponse>> = new Map();
const CACHE_MAX_AGE = 30 * 60 * 1000;
// sessionStorage permite que os dados sobrevivam a um F5/page-refresh,
// eliminando o skeleton na maioria das visitas subsequentes.
const _SS_KEY = 'dw_mkt_cache_v2';
const _SS_MAX_AGE = 4 * 60 * 60 * 1000; // 4 h — exibe dado antigo sem piscar

// Restaura o cache em memória a partir do sessionStorage na inicialização do módulo.
try {
  const _raw = sessionStorage.getItem(_SS_KEY);
  if (_raw) {
    const _parsed: Record<string, CacheEntry<MarketingEventsResponse>> = JSON.parse(_raw);
    const _now = Date.now();
    for (const [k, v] of Object.entries(_parsed)) {
      if (_now - v.timestamp < _SS_MAX_AGE) {
        dashboardCache.set(k, v);
      }
    }
  }
} catch { /* sessionStorage indisponível ou JSON inválido */ }

function _persistToSessionStorage(): void {
  try {
    const obj: Record<string, CacheEntry<MarketingEventsResponse>> = {};
    dashboardCache.forEach((v, k) => { obj[k] = v; });
    sessionStorage.setItem(_SS_KEY, JSON.stringify(obj));
  } catch { /* quota exceeded ou navegador sem sessionStorage */ }
}

function getCacheKey(params?: {
  ano?: number;
  status?: string;
  categoria?: string;
  busca?: string;
  force_refresh?: boolean;
}): string {
  return `mkt_${params?.ano || ''}_${params?.status || ''}_${params?.categoria || ''}_${params?.busca || ''}`;
}

const MAX_CACHE_ENTRIES = 20;

export function clearMarketingDashboardCache(): void {
  dashboardCache.clear();
  try { sessionStorage.removeItem(_SS_KEY); } catch { /* ok */ }
}

export function getMarketingDashboardCache(params?: {
  ano?: number;
  status?: string;
  categoria?: string;
  busca?: string;
}): { data: MarketingEventsResponse; age: number; isExpired: boolean } | null {
  const key = getCacheKey(params);
  const entry = dashboardCache.get(key);
  if (!entry) return null;
  const age = Date.now() - entry.timestamp;
  // Serve dado do sessionStorage por até _SS_MAX_AGE (4 h) como stale,
  // para nunca exibir skeleton quando já existe um resultado anterior.
  // O componente sempre dispara um fetch em bg e atualiza quando chega.
  if (age > _SS_MAX_AGE) {
    dashboardCache.delete(key);
    return null;
  }
  return { data: entry.data, age, isExpired: age > CACHE_MAX_AGE };
}

export function isMarketingCacheStale(params?: {
  ano?: number;
  status?: string;
  categoria?: string;
  busca?: string;
}): boolean {
  const cached = getMarketingDashboardCache(params);
  if (!cached) return true;
  return cached.age > CACHE_MAX_AGE;
}

// Status do job assíncrono de reconsolidação (recalcular-snapshot /
// consolidar-evento). Os estados 'cancelled' | 'timeout' | 'unreachable' são
// sintéticos do cliente (aguardarRecalcularSnapshot), não vêm do backend.
export interface RecalcSnapshotStatus {
  evento_id: string;
  state: 'idle' | 'running' | 'done' | 'error' | 'cancelled' | 'timeout' | 'unreachable';
  kind?: string;
  started_at?: number | null;
  finished_at?: number | null;
  error?: string | null;
  result?: {
    status?: string;
    evento_id?: string;
    evento_grupo?: string;
    ano?: number;
    incremental?: boolean;
    margem_recalculada?: number | null;
    ultima_atualizacao?: string;
    qtd_antes?: number | null;
    qtd_depois?: number | null;
    duracao_ms?: number;
    ciclo_id?: string;
    cooldown_aplicado?: boolean;
    cooldown_until_epoch?: number | null;
    cooldown_total_sec?: number;
  } | null;
}

export const marketingService = {
  getEventos: async (params?: {
    ano?: number;
    status?: string;
    categoria?: string;
    busca?: string;
    force_refresh?: boolean;
  }, signal?: AbortSignal): Promise<MarketingEventsResponse & { _isStale?: boolean }> => {
    const queryParams = new URLSearchParams();
    if (params?.ano) queryParams.append('ano', params.ano.toString());
    if (params?.status) queryParams.append('status', params.status);
    if (params?.categoria) queryParams.append('categoria', params.categoria);
    if (params?.busca) queryParams.append('busca', params.busca);
    if (params?.force_refresh) queryParams.append('force_refresh', 'true');
    const queryString = queryParams.toString() ? `?${queryParams.toString()}` : '';
    const response = await api.get(`/marketing/eventos${queryString}`, { signal });
    const data = response.data;
    const isStale = response.headers?.['x-data-stale'] === 'true';
    data._isStale = isStale;
    const key = getCacheKey(params);
    if (dashboardCache.size >= MAX_CACHE_ENTRIES) {
      const oldestKey = dashboardCache.keys().next().value;
      if (oldestKey) dashboardCache.delete(oldestKey);
    }
    dashboardCache.set(key, { data, timestamp: Date.now(), key });
    _persistToSessionStorage();
    return data;
  },
  getResumo: async (ano?: number, signal?: AbortSignal): Promise<{ status: string; resumo: MarketingDashboardSummary; ultima_atualizacao: string }> => {
    const queryString = ano ? `?ano=${ano}` : '';
    const response = await api.get(`/marketing/resumo${queryString}`, { signal });
    return response.data;
  },
  getCutoffAlerts: async (signal?: AbortSignal): Promise<{ alerts: CutoffAlert[]; total: number; status?: string }> => {
    const response = await api.get('/marketing/cutoff-alerts', { signal });
    return response.data;
  },
  getEventoById: async (id: string, signal?: AbortSignal, ano?: number, force_refresh?: boolean, force_magento_refresh?: boolean): Promise<{ 
    status: string; 
    evento: MarketingEvent; 
    dailySales?: { date: string; sales: number; expected: number; cumulativeSales: number; cumulativeExpected: number; dMinus?: number; curvaAnoAnterior?: number; dif?: number; atingimentoAcumulado?: number; atingimentoDiario?: number; normalizedSales?: number; cumulativeNormalized?: number; localMedian?: number | null; outlierLimit?: number | null; isOutlier?: boolean; excessRemoved?: number; excessReceived?: number }[];
    commercialActions?: {
      id: string;
      type: string;
      description: string;
      date: string;
      impact?: string;
      vendas_antes?: number | null;
      vendas_depois?: number | null;
      impacto_percentual?: number | null;
      status_impacto?: string;
      ponto_corte?: string | null;
      estagio?: string | null;
      snapshot_isc?: number | null;
      snapshot_isc_state?: string | null;
      snapshot_d_minus?: number | null;
      snapshot_ia730?: number | null;
      snapshot_rolling14d?: number | null;
      snapshot_curva_percent?: number | null;
      snapshot_vendas_acumuladas?: number | null;
      snapshot_playbook_letter?: string | null;
    }[];
    projetos_vinculados?: { id: number; nome: string; sku: string }[];
    ultima_atualizacao: string;
    _isStale?: boolean;
  }> => {
    const queryParams = new URLSearchParams();
    if (ano) queryParams.append('ano', ano.toString());
    if (force_refresh) queryParams.append('force_refresh', 'true');
    if (force_magento_refresh) queryParams.append('force_magento_refresh', 'true');
    const queryString = queryParams.toString() ? `?${queryParams.toString()}` : '';
    const response = await api.get(`/marketing/eventos/${encodeURIComponent(id)}${queryString}`, { signal });
    const data = response.data;
    data._isStale = response.headers?.['x-data-stale'] === 'true';
    return data;
  },
  getEventoVersion: async (id: string, ano?: number): Promise<{
    evento_id: string;
    ano: number;
    snapshot_updated_at: string | null;
    last_sync_hoje: string | null;
    server_now: string;
  }> => {
    const queryParams = new URLSearchParams();
    if (ano) queryParams.append('ano', ano.toString());
    const queryString = queryParams.toString() ? `?${queryParams.toString()}` : '';
    const response = await api.get(`/marketing/eventos/${encodeURIComponent(id)}/version${queryString}`);
    return response.data;
  },
  atualizarHoje: async (id: string, ano?: number): Promise<{
    status: string;
    evento_id: string;
    data: string;
    hoje_ativo: number;
    hoje_magento: number;
    hoje_total: number;
    media_7d: number;
    media_14d: number;
    media_30d: number;
    total_acumulado: number;
    ultima_atualizacao: string;
    ativo_ok?: boolean;
    magento_ok?: boolean;
    fontes_indisponiveis?: string[];
  }> => {
    const queryParams = new URLSearchParams();
    if (ano) queryParams.append('ano', ano.toString());
    const queryString = queryParams.toString() ? `?${queryParams.toString()}` : '';
    const response = await api.post(`/marketing/eventos/${encodeURIComponent(id)}/atualizar-hoje${queryString}`);
    return response.data;
  },
  recalcularSnapshot: async (eventoId: string, ano?: number): Promise<{
    status: string;
    evento_id: string;
    ano: number;
    // Campos abaixo só existem na resposta síncrona LEGADA (backend antigo).
    // O backend atual responde {status:'started'} imediatamente.
    margem_recalculada?: number | null;
    ultima_atualizacao?: string;
    cooldown_aplicado?: boolean;
    cooldown_until_epoch?: number | null;
    cooldown_total_sec?: number;
  }> => {
    // Dispara a reconsolidação em BACKGROUND no servidor e retorna na hora
    // ({status:'started'}). Acompanhar via aguardarRecalcularSnapshot().
    // Antes o endpoint era síncrono (timeout de 10 min) e o proxy na frente
    // do backend cortava a conexão com 502 quando o Magento estava lento,
    // mesmo com a reconsolidação terminando OK no servidor.
    // `ano` deve ser o mesmo ano que a tela está exibindo — sem ele, eventos
    // agrupados cuja edição vista difere do ano corrente do servidor (ex.:
    // próxima edição já com carrinho aberto) nunca reconsolidam a certa.
    const queryString = ano ? `?ano=${ano}` : '';
    const response = await api.post(
      `/marketing/eventos/${encodeURIComponent(eventoId)}/recalcular-snapshot${queryString}`,
      null,
      { timeout: 60000 }
    );
    return response.data;
  },
  getRecalcularSnapshotStatus: async (eventoId: string, ano?: number): Promise<RecalcSnapshotStatus> => {
    const queryString = ano ? `?ano=${ano}` : '';
    const response = await api.get(
      `/marketing/eventos/${encodeURIComponent(eventoId)}/recalcular-snapshot/status${queryString}`,
      { timeout: 15000 }
    );
    return response.data;
  },
  aguardarRecalcularSnapshot: async (
    eventoId: string,
    opts?: { intervalMs?: number; timeoutMs?: number; isCancelled?: () => boolean },
    ano?: number
  ): Promise<RecalcSnapshotStatus> => {
    // Polling do job assíncrono até estado terminal ('done' | 'error' | 'idle').
    // Sintéticos: 'cancelled' (isCancelled), 'timeout' (excedeu timeoutMs) e
    // 'unreachable' (5 falhas de rede consecutivas). Em todos os casos o job
    // continua rodando no servidor — o slot global evita duplicidade.
    // `ano` deve ser o mesmo enviado ao disparar (recalcularSnapshot), senão
    // o polling procura o job sob a chave errada e nunca encontra o job.
    const intervalMs = opts?.intervalMs ?? 4000;
    const timeoutMs = opts?.timeoutMs ?? 20 * 60 * 1000;
    const queryString = ano ? `?ano=${ano}` : '';
    const t0 = Date.now();
    let falhasRede = 0;
    while (true) {
      if (opts?.isCancelled?.()) return { evento_id: eventoId, state: 'cancelled' };
      if (Date.now() - t0 > timeoutMs) return { evento_id: eventoId, state: 'timeout' };
      await new Promise(r => setTimeout(r, intervalMs));
      try {
        const st: RecalcSnapshotStatus = (await api.get(
          `/marketing/eventos/${encodeURIComponent(eventoId)}/recalcular-snapshot/status${queryString}`,
          { timeout: 15000 }
        )).data;
        falhasRede = 0;
        // Cancelamento pode ter ocorrido DURANTE o sleep/request — checa de
        // novo antes de devolver estado terminal, senão a run antiga aplicaria
        // resultado/erro na tela de outro evento.
        if (opts?.isCancelled?.()) return { evento_id: eventoId, state: 'cancelled' };
        if (st.state === 'done' || st.state === 'error' || st.state === 'idle') return st;
      } catch {
        falhasRede += 1;
        if (falhasRede >= 5) return { evento_id: eventoId, state: 'unreachable' };
      }
    }
  },
  getReconsolidarCooldown: async (eventoId: string, ano?: number): Promise<{
    evento_id: string;
    can_reconsolidar: boolean;
    is_diretoria: boolean;
    locked: boolean;
    remaining_sec: number;
    cooldown_total_sec: number;
    evento_em_andamento: string | null;
    outro_em_andamento: boolean;
  }> => {
    const queryString = ano ? `?ano=${ano}` : '';
    const response = await api.get(
      `/marketing/eventos/${encodeURIComponent(eventoId)}/reconsolidar-cooldown${queryString}`,
      { timeout: 10000 }
    );
    return response.data;
  },
  toggleCortesias: async (eventoId: string): Promise<{ incluirCortesias: boolean }> => {
    const response = await api.patch(`/marketing/eventos/${encodeURIComponent(eventoId)}/cortesias`);
    return response.data;
  },
  getAcoesComerciais: async (projetoId: string): Promise<{ status: string; acoes: any[] }> => {
    const response = await api.get(`/marketing/acoes-comerciais/${projetoId}`);
    return response.data;
  },
  createAcaoComercial: async (data: {
    projeto_id: number;
    tipo: string;
    descricao: string;
    data_acao: string;
    ponto_corte?: string;
    estagio?: string;
    snapshot_isc?: number;
    snapshot_isc_state?: string;
    snapshot_d_minus?: number;
    snapshot_ia730?: number;
    snapshot_rolling14d?: number;
    snapshot_curva_percent?: number;
    snapshot_vendas_acumuladas?: number;
    snapshot_playbook_letter?: string;
  }): Promise<any> => {
    const response = await api.post('/marketing/acoes-comerciais', data);
    return response.data;
  },
  updateAcaoComercial: async (id: number, data: { tipo?: string; descricao?: string; data_acao?: string }): Promise<any> => {
    const response = await api.put(`/marketing/acoes-comerciais/${id}`, data);
    return response.data;
  },
  deleteAcaoComercial: async (id: number): Promise<any> => {
    const response = await api.delete(`/marketing/acoes-comerciais/${id}`);
    return response.data;
  },
  getAnalisesDiarias: async (projetoId: string): Promise<{ status: string; analises: any[] }> => {
    const response = await api.get(`/marketing/analises-diarias/${projetoId}`);
    return response.data;
  },
  createOrUpdateAnaliseDiaria: async (data: {
    projeto_id: number;
    data_analise: string;
    ponto_corte?: string;
    estagio?: string;
    analise_texto: string;
    tipo_acao_sugerida: string;
    acao_sugerida_descricao?: string;
    retorno_estimado_tipo?: string;
    retorno_estimado_valor?: number;
    snapshot_isc?: number;
    snapshot_isc_state?: string;
    snapshot_d_minus?: number;
    snapshot_ia730?: number;
    snapshot_rolling14d?: number;
    snapshot_curva_percent?: number;
    snapshot_vendas_acumuladas?: number;
    snapshot_playbook_letter?: string;
    snapshot_media_semana_atual?: number;
    snapshot_ticket_medio_realizado?: number;
  }): Promise<any> => {
    const response = await api.post('/marketing/analises-diarias', data);
    return response.data;
  },
  updateAnaliseDiaria: async (id: number, data: {
    analise_texto?: string;
    tipo_acao_sugerida?: string;
    acao_sugerida_descricao?: string;
    retorno_estimado_tipo?: string | null;
    retorno_estimado_valor?: number;
  }): Promise<any> => {
    const response = await api.put(`/marketing/analises-diarias/${id}`, data);
    return response.data;
  },
  deleteAnaliseDiaria: async (id: number): Promise<any> => {
    const response = await api.delete(`/marketing/analises-diarias/${id}`);
    return response.data;
  },
  getCurvaComparativa: async (signal?: AbortSignal): Promise<{
    status: string;
    ano_atual: number;
    ano_anterior: number;
    data: {
      mes: string;
      [key: string]: string | number;
    }[];
    ultima_atualizacao: string;
  }> => {
    const response = await api.get('/marketing/curva-comparativa', { signal });
    return response.data;
  },
  getCurvaComparativaEvento: async (eventoId: string, signal?: AbortSignal, ano?: number): Promise<{
    status: string;
    modo?: string;
    ano_atual: number;
    ano_anterior: number;
    data_evento_atual?: string | null;
    data_evento_anterior?: string | null;
    data: {
      label?: string;
      dias_antes?: number;
      mes?: string;
      [key: string]: string | number | undefined;
    }[];
    evento_nome: string;
    ultima_atualizacao: string;
  }> => {
    const params: any = {};
    if (ano) params.ano = ano;
    const response = await api.get(`/marketing/curva-comparativa/${encodeURIComponent(eventoId)}`, { signal, params });
    return response.data;
  },
  getSalesAverages: async (eventoId: string, periodo: number = 30, signal?: AbortSignal, ano?: number, force_refresh?: boolean): Promise<{
    status: string;
    periodo_dias: number;
    media_geral: number;
    total_vendas: number;
    dias_com_dados: number;
    medias: Array<{ periodo: number; label: string; media: number; total: number; dias: number }>;
    vendas_diarias: { date: string; sales: number }[];
    tendencia: { date: string; media_movel_7d: number; vendas: number }[];
  }> => {
    const queryParams = new URLSearchParams();
    queryParams.append('periodo', periodo.toString());
    if (ano) queryParams.append('ano', ano.toString());
    if (force_refresh) queryParams.append('force_refresh', 'true');
    const url = `/marketing/eventos/${encodeURIComponent(eventoId)}/medias-vendas?${queryParams.toString()}`;
    const response = await api.get(url, { signal });
    return response.data;
  },
  getCurvaSnapshot: async (eventoId: string, signal?: AbortSignal, ano?: number): Promise<{
    status: string;
    evento_grupo: string;
    ano_referencia: number;
    sales_goal: number;
    data: { d_minus: number; percentual_acumulado: number; percentual_dia: number; meta_acumulado: number; meta_dia: number }[];
    message?: string;
  }> => {
    const params: any = {};
    if (ano) params.ano = ano;
    const response = await api.get(`/marketing/eventos/${encodeURIComponent(eventoId)}/curva-snapshot`, { signal, params });
    return response.data;
  },
  getDiagnosticoCurvas: async (ano?: number, signal?: AbortSignal, forceRefresh?: boolean): Promise<{
    ano: number;
    total: number;
    eventos: Array<{
      grupo_id: number;
      evento_grupo: string;
      circuito: string | null;
      cidade: string | null;
      estado: string | null;
      data_evento: string | null;
      tipo_curva: string | null;
      fonte_curva: string | null;
      ano_referencia: number | null;
      tem_override: boolean;
      override_target: string | null;
      fabricated_linear: boolean;
      sales_goal: number;
      tem_mapeamento: boolean;
      erro?: string;
    }>;
  }> => {
    const params: any = {};
    if (ano) params.ano = ano;
    if (forceRefresh) params.force_refresh = true;
    const response = await api.get('/marketing/diagnostico-curvas', { signal, params });
    return response.data;
  },
  getSimulacao: async (eventoId: string, signal?: AbortSignal, ano?: number): Promise<any> => {
    const queryParams = new URLSearchParams();
    if (ano) queryParams.append('ano', ano.toString());
    const url = `/marketing/eventos/${encodeURIComponent(eventoId)}/simulacao?${queryParams.toString()}`;
    const response = await api.get(url, { signal });
    return response.data;
  },
  checkDuplicateAction: async (projetoId: number, tipo: string): Promise<{
    status: string;
    has_duplicate: boolean;
    existing_action: { id: number; tipo: string; descricao: string; data_acao: string; dias_restantes: number } | null;
  }> => {
    const response = await api.get(`/marketing/check-duplicate-action/${projetoId}?tipo=${tipo}`);
    return response.data;
  },
  refreshCache: async (): Promise<{
    status: string;
    message: string;
    cache_info: Record<string, any>;
    ultima_atualizacao: string;
  }> => {
    const response = await api.post('/marketing/cache/refresh');
    return response.data;
  },
  refreshAllCaches: async (): Promise<{
    status: string;
    message: string;
    ultima_atualizacao: string;
  }> => {
    const response = await api.post('/marketing/cache/refresh-all');
    return response.data;
  },
  syncHoje: async (): Promise<{
    status: string;
    synced: number;
    message: string;
    ultima_atualizacao: string;
  }> => {
    const response = await api.post('/marketing/cache/sync-hoje', null, { timeout: 120000 });
    return response.data;
  },
  getCacheStatus: async (): Promise<{
    status: string;
    refresh_in_progress: boolean;
    progress: { step: number; total_steps: number; label: string; elapsed_seconds: number | null; sub_current?: number; sub_total?: number } | null;
    last_error: string | null;
    ultima_atualizacao_completa: string | null;
    last_sync_hoje: string | null;
    warmup_duration_seconds: number | null;
    warmup_completed_at: string | null;
    warmup_summary: Record<string, any>;
    warmup_results: Record<string, string>;
    gap_detection: {
      tier1_event_count: number;
      missing_tier1_events: string[];
      stale_tier1_events: string[];
      detected_at: string;
    } | null;
    missing_tier1_events: string[];
    stale_tier1_events: string[];
    oldest_event_detail_age_hours: number | null;
    newest_event_detail_age_hours: number | null;
    stale_events: string[];
    caches: {
      event_detail: {
        entries: number;
        historical: number;
        current_year: number;
        oldest_event_detail_age_hours: number | null;
        newest_event_detail_age_hours: number | null;
        stale_events: string[];
      };
      [key: string]: any;
    };
    config: Record<string, any>;
  }> => {
    const response = await api.get('/marketing/cache/status');
    return response.data;
  },
  getEventInsights: async (eventoId: string, signal?: AbortSignal, ano?: number, force_refresh?: boolean): Promise<any> => {
    const params: any = {};
    if (ano) params.ano = ano;
    if (force_refresh) params.force_refresh = true;
    const response = await api.get(`/marketing/eventos/${encodeURIComponent(eventoId)}/insights`, { signal, params });
    return response.data;
  },
  getSettings: async (key: string): Promise<{ status: string; key: string; value: any }> => {
    const response = await api.get(`/marketing/settings/${key}`);
    return response.data;
  },
  updateSettings: async (key: string, value: any): Promise<{ status: string; key: string; value: any }> => {
    const response = await api.put(`/marketing/settings/${key}`, { value });
    return response.data;
  },
  getPlaybook: async (): Promise<any> => {
    const response = await api.get('/marketing/playbook');
    return response.data;
  },
  getProjetadoFaixas: async (eventoId: string): Promise<{ status: string; faixas: { id: string; nome: string; preco: string; qtd: string }[] }> => {
    const response = await api.get(`/marketing/eventos/${encodeURIComponent(eventoId)}/projetado-faixas`);
    return response.data;
  },
  upsertProjetadoFaixas: async (eventoId: string, faixas: { id: string; nome: string; preco: string; qtd: string }[]): Promise<{ status: string }> => {
    const response = await api.put(`/marketing/eventos/${encodeURIComponent(eventoId)}/projetado-faixas`, { faixas });
    return response.data;
  },
  deleteProjetadoFaixas: async (eventoId: string): Promise<{ status: string }> => {
    const response = await api.delete(`/marketing/eventos/${encodeURIComponent(eventoId)}/projetado-faixas`);
    return response.data;
  },
};

export const profileService = {
  changePassword: async (currentPassword: string, newPassword: string) => {
    const response = await api.put('/profile/password', {
      current_password: currentPassword,
      new_password: newPassword,
    });
    return response.data;
  },
  uploadPhoto: async (file: File) => {
    const formData = new FormData();
    formData.append('file', file);
    const response = await api.post('/profile/photo', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return response.data;
  },
  deletePhoto: async () => {
    const response = await api.delete('/profile/photo');
    return response.data;
  },
};

export interface CortesiaMetrics {
  filter: { type: string; value: string; label: string };
  solicitados: number;
  aprovados: number;
  utilizados: number;
  disponiveis: number;
  source?: string;
}

export interface CortesiaUser {
  id: string;
  name: string;
  email: string;
  role: string;
  roleLabel: string;
  area: string;
  createdAt?: string;
}

// Linha do lote de eventos futuros consultados por SKU no app de Cortesias.
// status é sempre explícito — nunca zeros silenciosos.
export interface CortesiaEventoRow {
  evento_id: number;
  nome: string;
  data_evento: string | null;
  sku: string;
  cidade?: string | null;
  estado?: string | null;
  status: 'ok' | 'nao_encontrado' | 'erro';
  mensagem?: string;
  solicitados?: number;
  aprovados?: number;
  utilizados?: number;
  disponiveis?: number;
  // Infos extras da API externa (apenas linhas "ok"):
  nome_externo?: string | null; // filter.label — nome do evento no app de Cortesias
  fonte?: string | null; // source — "magento" | "local"
}

export interface CortesiaEventosResponse {
  eventos: CortesiaEventoRow[];
  resumo: { total: number; ok: number; nao_encontrado: number; erro: number };
  atualizado_em: string;
}

// Integração somente-leitura com o app externo de Cortesias.
// O token da integração vive apenas no backend (rotas proxy autenticadas).
export const cortesiaService = {
  getMetrics: async (filtro: { sku?: string; userId?: string; area?: string }): Promise<CortesiaMetrics> => {
    const response = await api.get('/cortesia/metrics', { params: filtro, timeout: 15000 });
    return response.data;
  },
  // Lote pesado (1 consulta externa por SKU, com concorrência limitada no
  // backend): timeout generoso — pior caso legítimo passa de 1 minuto.
  getEventos: async (): Promise<CortesiaEventosResponse> => {
    const response = await api.get('/cortesia/eventos', { timeout: 120000 });
    return response.data;
  },
  getUsers: async (): Promise<{ total: number; users: CortesiaUser[] }> => {
    const response = await api.get('/cortesia/users', { timeout: 15000 });
    return response.data;
  },
};

export interface CortesiaSaldoAreaItem {
  area_projecao_id: number;
  area_projecao_nome: string;
  projetado: number;
  solicitado: number;
  saldo: number;
  area_sigla?: string | null;
}

export interface CortesiaEventoSaldoResponse {
  evento_id: number;
  evento_nome: string;
  evento_data: string | null;
  evento_sku?: string | null;
  areas: CortesiaSaldoAreaItem[];
}

export interface CupomCodigoItem {
  id: number;
  codigo: string;
  usado: boolean;
  usado_em?: string | null;
  usado_por_nome?: string | null;
}

// Opção enxuta (sem números de saldo) para o filtro por evento da fila de
// geração de cupons — só eventos com pelo menos um cupom já gerado.
export interface CortesiaEventoFilaOpcao {
  evento_id: number;
  evento_nome: string;
  evento_data: string | null;
}

export interface CortesiaSolicitacaoResponse {
  id: number;
  evento_id: number;
  evento_nome?: string | null;
  evento_data?: string | null;
  area_projecao_id: number;
  area_projecao_nome?: string | null;
  tipo: 'cupom' | 'planilha';
  quantidade: number;
  status: 'solicitado' | 'gerado';
  observacao?: string | null;
  codigo_cupom?: string | null;
  codigo_cupom_lista?: string[];
  codigos_detalhes?: CupomCodigoItem[];
  gerado_por_nome?: string | null;
  gerado_em?: string | null;
  nome_arquivo?: string | null;
  quantidade_linhas?: number | null;
  solicitado_por_nome?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

// Tela nova e independente da Cortesias por Evento (proxy externo): fluxo de
// solicitação/registro interno de cortesias, com trava de saldo pela
// Projeção de Inscritos.
export const cortesiaSolicitacaoService = {
  listEventosSaldo: async (): Promise<CortesiaEventoSaldoResponse[]> => {
    const response = await api.get('/cortesia-solicitacao/eventos');
    return response.data;
  },
  getSaldo: async (evento_id: number): Promise<CortesiaSaldoAreaItem[]> => {
    const response = await api.get('/cortesia-solicitacao/saldo', { params: { evento_id } });
    return response.data;
  },
  list: async (params?: { evento_id?: number; area_projecao_id?: number }): Promise<CortesiaSolicitacaoResponse[]> => {
    const response = await api.get('/cortesia-solicitacao/', { params });
    return response.data;
  },
  criarCupom: async (data: { evento_id: number; area_projecao_id: number; quantidade: number; observacao?: string }): Promise<CortesiaSolicitacaoResponse> => {
    const response = await api.post('/cortesia-solicitacao/cupom', data);
    return response.data;
  },
  criarPlanilha: async (data: { evento_id: number; area_projecao_id: number; quantidade: number; observacao?: string; arquivo: File }): Promise<CortesiaSolicitacaoResponse> => {
    const form = new FormData();
    form.append('evento_id', String(data.evento_id));
    form.append('area_projecao_id', String(data.area_projecao_id));
    form.append('quantidade', String(data.quantidade));
    if (data.observacao) form.append('observacao', data.observacao);
    form.append('arquivo', data.arquivo);
    const response = await api.post('/cortesia-solicitacao/planilha', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 60000,
    });
    return response.data;
  },
  gerarCupom: async (id: number): Promise<CortesiaSolicitacaoResponse> => {
    const response = await api.post(`/cortesia-solicitacao/${id}/gerar`);
    return response.data;
  },
  cancelar: async (id: number) => {
    const response = await api.delete(`/cortesia-solicitacao/${id}`);
    return response.data;
  },
  baixarArquivo: async (id: number, nomeArquivo: string): Promise<void> => {
    const response = await api.get(`/cortesia-solicitacao/${id}/arquivo`, { responseType: 'blob' });
    const url = window.URL.createObjectURL(new Blob([response.data]));
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', nomeArquivo || 'planilha');
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.URL.revokeObjectURL(url);
  },
  // Fila dedicada de quem gera os cupons: todas as solicitações tipo cupom,
  // sem recorte por área (backend usa pode_editar, não vínculo com a área).
  // Pendentes sempre vêm completos; gerados são limitados aos últimos 90
  // dias a menos que evento_id seja informado (aí vem o histórico completo
  // daquele evento).
  filaGeracao: async (params?: { evento_id?: number }): Promise<CortesiaSolicitacaoResponse[]> => {
    const response = await api.get('/cortesia-solicitacao/fila-geracao', { params });
    return response.data;
  },
  // Eventos com pelo menos um cupom já gerado — alimenta o filtro acima.
  eventosFilaGeracao: async (): Promise<CortesiaEventoFilaOpcao[]> => {
    const response = await api.get('/cortesia-solicitacao/fila-geracao/eventos');
    return response.data;
  },
  toggleCodigoUsado: async (solicitacaoId: number, codigoId: number): Promise<CupomCodigoItem> => {
    const response = await api.patch(`/cortesia-solicitacao/${solicitacaoId}/codigos/${codigoId}/toggle-usado`);
    return response.data;
  },
  exportarCupons: async (params?: { evento_id?: number; area_projecao_id?: number }): Promise<void> => {
    const response = await api.get('/cortesia-solicitacao/exportar-cupons', { params, responseType: 'blob' });
    const url = window.URL.createObjectURL(new Blob([response.data]));
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', 'cupons_gerados.csv');
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.URL.revokeObjectURL(url);
  },
};

export const projecaoService = {
  listAreas: async () => {
    const response = await api.get('/projecao/areas');
    return response.data;
  },
  listAreasDetail: async () => {
    const response = await api.get('/projecao/areas/detail');
    return response.data;
  },
  createArea: async (nome: string, sigla: string) => {
    const response = await api.post('/projecao/areas', { nome, sigla });
    return response.data;
  },
  updateAreaSigla: async (areaId: number, sigla: string) => {
    const response = await api.put(`/projecao/areas/${areaId}/sigla`, { sigla });
    return response.data;
  },
  atribuirUsuarios: async (data: { area_projecao_id: number; usuario_ids: number[] }) => {
    const response = await api.post('/projecao/areas/atribuir', data);
    return response.data;
  },
  minhasAreas: async () => {
    const response = await api.get('/projecao/minhas-areas');
    return response.data;
  },
  list: async (params?: { mes?: string; tipo_evento?: string; modalidade?: string; area_projecao_id?: string; evento_id?: number }) => {
    const response = await api.get('/projecao/', { params });
    return response.data;
  },
  create: async (data: { evento_id: number; area_projecao_id: number; quantidade: number; clientes?: { nome_cliente: string; quantidade: number }[]; kits?: { nome_kit: string; quantidade: number }[] }) => {
    const response = await api.post('/projecao/', data);
    return response.data;
  },
  update: async (id: number, data: { quantidade: number; clientes?: { nome_cliente: string; quantidade: number }[] | null; kits?: { nome_kit: string; quantidade: number }[] | null }) => {
    const response = await api.put(`/projecao/${id}`, data);
    return response.data;
  },
  delete: async (id: number) => {
    const response = await api.delete(`/projecao/${id}`);
    return response.data;
  },
  toggleLock: async (eventoId: number) => {
    const response = await api.post(`/projecao/evento/${eventoId}/toggle-lock`);
    return response.data;
  },
  getHistorico: async (id: number) => {
    const response = await api.get(`/projecao/${id}/historico`);
    return response.data;
  },
  getConsolidado: async (params?: { mes?: string; tipo_evento?: string; modalidade?: string; area_projecao_id?: string; evento_id?: number; force_refresh?: boolean }) => {
    const response = await api.get('/projecao/consolidado', { params });
    // 'stale' indica que o backend serviu um valor anterior enquanto recalcula
    // em background (SWR) — o chamador deve rebuscar até vir fresco.
    return { data: response.data, stale: response.headers?.['x-consolidado-stale'] === '1' };
  },
  getCamisetaAvulsaInfo: async (evento_id: number, area_projecao_id: number): Promise<{ corte1_congelado: boolean; teto: number }> => {
    const response = await api.get('/projecao/camiseta-avulsa-info', { params: { evento_id, area_projecao_id } });
    return response.data;
  },
  getCorte1Distribuicao: async (evento_id: number, area_projecao_id: number): Promise<{ evento_id: number; area_projecao_id: number; quantidade: number; kits: { nome_kit: string; quantidade: number }[]; clientes: { nome_cliente: string; quantidade: number }[]; fonte: string; congelado_em: string | null; em_corte2: boolean }> => {
    const response = await api.get('/projecao/corte1-distribuicao', { params: { evento_id, area_projecao_id } });
    return response.data;
  },
  getLixeira: async () => {
    const response = await api.get('/projecao/lixeira');
    return response.data;
  },
  restaurar: async (id: number) => {
    const response = await api.post(`/projecao/lixeira/${id}/restaurar`);
    return response.data;
  },
  deletePermanente: async (id: number) => {
    const response = await api.delete(`/projecao/lixeira/${id}/permanente`);
    return response.data;
  },
  exportar: async (params?: { mes?: string; tipo_evento?: string; modalidade?: string; area_projecao_id?: string }) => {
    const response = await api.get('/projecao/exportar', { params, responseType: 'blob' });
    const url = window.URL.createObjectURL(new Blob([response.data]));
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', 'projecao_inscritos.csv');
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.URL.revokeObjectURL(url);
  },
  listCutoffRules: async (incluirInativas = false) => {
    const response = await api.get('/projecao/cutoff-rules', { params: { incluir_inativas: incluirInativas } });
    return response.data;
  },
  createCutoffRule: async (data: { nome: string; dias_antes_evento: number; ativo?: boolean }) => {
    const response = await api.post('/projecao/cutoff-rules', data);
    return response.data;
  },
  updateCutoffRule: async (id: number, data: { nome?: string; dias_antes_evento?: number; ativo?: boolean }) => {
    const response = await api.put(`/projecao/cutoff-rules/${id}`, data);
    return response.data;
  },
  deleteCutoffRule: async (id: number) => {
    const response = await api.delete(`/projecao/cutoff-rules/${id}`);
    return response.data;
  },
  getPendencias: async () => {
    const response = await api.get('/projecao/pendencias');
    return response.data;
  },
  getCutoffEnvioMap: async () => {
    const response = await api.get('/projecao/cutoff-envio-map');
    return response.data as Record<string, string>;
  },
  setAreaCutoffCustomizado: async (areaId: number, ativo: boolean) => {
    const response = await api.put(`/projecao/areas/${areaId}/cutoff-customizado`, { ativo });
    return response.data;
  },
  listCutoffsEvento: async (eventoId: number) => {
    const response = await api.get('/projecao/cutoff-evento-area', { params: { evento_id: eventoId } });
    return response.data;
  },
  upsertCutoffEventoArea: async (data: { evento_id: number; area_projecao_id: number; data_corte_1: string | null; data_corte_2: string | null; data_saida_caminhao: string | null; observacao_corte_1?: string | null }) => {
    const response = await api.put('/projecao/cutoff-evento-area', data);
    return response.data;
  },
  getAutoLockConfig: async () => {
    const response = await api.get('/projecao/auto-lock-config');
    return response.data;
  },
  updateAutoLockConfig: async (data: { dias_antes_evento: number; hora_trava: string; ativo: boolean }) => {
    const response = await api.put('/projecao/auto-lock-config', data);
    return response.data;
  },
  getCorteConfig: async () => {
    const response = await api.get('/projecao/corte-config');
    return response.data;
  },
  updateCorteConfig: async (data: { dias_corte_1: number; dias_corte_2: number; ativo: boolean }) => {
    const response = await api.put('/projecao/corte-config', data);
    return response.data;
  },
  updateAlertaConfig: async (data: { dias_alerta_envio: number }) => {
    const response = await api.put('/projecao/alerta-config', data);
    return response.data;
  },
  updateNotifConfig: async (data: { notif_email_ativo: boolean; notif_email_hora: number; notif_canal: string }) => {
    const response = await api.put('/projecao/notif-config', data);
    return response.data;
  },
  listAlteracaoNotifConfig: async (): Promise<{ area_projecao_id: number; area_projecao_nome: string | null; ativo: boolean; emails: string[]; updated_by_nome: string | null; updated_at: string | null }[]> => {
    const response = await api.get('/projecao/alteracao-notif-config');
    return response.data;
  },
  upsertAlteracaoNotifConfig: async (data: { area_projecao_id: number; ativo: boolean; emails: string[] }) => {
    const response = await api.put('/projecao/alteracao-notif-config', data);
    return response.data;
  },
  sendNotifTest: async () => {
    const response = await api.post('/projecao/notif-test');
    return response.data;
  },
  getNotifHistory: async (limit = 20) => {
    const response = await api.get('/projecao/notif-history', { params: { limit } });
    return response.data;
  },
  reabrirCorte: async (eventoId: number, corte: 1 | 2) => {
    const response = await api.post(`/projecao/eventos/${eventoId}/corte/${corte}/reabrir`);
    return response.data;
  },
  recongelarCorte: async (eventoId: number, corte: 1 | 2) => {
    const response = await api.post(`/projecao/eventos/${eventoId}/corte/${corte}/recongelar`);
    return response.data;
  },
  getDiagnosticoPosCorte: async (): Promise<{
    projecao_id: number;
    evento_id: number;
    evento_nome: string;
    area_projecao_id: number;
    area_nome: string;
    quantidade: number;
    valor_corte_1_atual: number | null;
    congelado_em: string | null;
    created_at: string | null;
  }[]> => {
    const response = await api.get('/projecao/diagnostico-pos-corte');
    return response.data;
  },
  backfillPosCorte: async (eventoId: number, areaProjecaoId: number) => {
    const response = await api.post('/projecao/diagnostico-pos-corte/backfill', null, {
      params: { evento_id: eventoId, area_projecao_id: areaProjecaoId },
    });
    return response.data;
  },
};

// ---------------------------------------------------------------------------
// Detalhamento de Eventos
// ---------------------------------------------------------------------------

export interface DetalheEventoDisponivel {
  evento_grupo: string;
  nome_evento: string;
  ativo_ids: number[];
  magento_ids: number[];
  anos: number[];
}

export interface DetalheRow {
  canal: string | null;
  kit: string | null;
  modalidade: string | null;
  pelotao: string | null;
  produtos: string | null;
  tamanho_camiseta: string | null;
  inscritos: number;
  receita_bruta: number;
  receita_liquida: number;
  ticket_medio: number;
  bancos?: string[];
}

export interface DetalheBancoRow extends DetalheRow {
  banco: string;
  id_evento: string | number | null;
  evento: string | null;
}

export interface DetalheDivergencia {
  dimensoes: Record<string, string | null>;
  consolidado_inscritos: number;
  soma_bancos_inscritos: number;
  diff_inscritos: number;
  consolidado_receita_liquida: number;
  soma_bancos_receita_liquida: number;
  diff_receita_liquida: number;
}

export interface DetalheTotais {
  inscritos: number;
  receita_bruta: number;
  receita_liquida: number;
  ticket_medio: number;
  por_canal: Record<string, { inscritos: number; receita_liquida: number }>;
}

export interface DetalheEventoPayload {
  evento_grupo: string | null;
  nome_evento: string | null;
  consolidado: DetalheRow[];
  por_banco: {
    Ativo: DetalheBancoRow[];
    Magento: DetalheBancoRow[];
  };
  divergencias: DetalheDivergencia[];
  erros: Record<string, string>;
  totais: DetalheTotais;
  source?: 'cache' | 'snapshot' | 'live';
  snapshot_updated_at?: string | null;
}

// Preferências de UI por usuário (persistidas no servidor; localStorage é cache)
export const userPrefsService = {
  getAll: async (): Promise<Record<string, unknown>> => {
    const response = await api.get('/profile/prefs');
    return response.data;
  },
  set: async (chave: string, valor: unknown): Promise<void> => {
    await api.put(`/profile/prefs/${encodeURIComponent(chave)}`, { valor });
  },
  remove: async (chave: string): Promise<void> => {
    await api.delete(`/profile/prefs/${encodeURIComponent(chave)}`);
  },
};

export const detalheEventosService = {
  listEventos: async (): Promise<DetalheEventoDisponivel[]> => {
    const response = await api.get('/marketing/detalhe-eventos/eventos');
    return response.data;
  },

  getDetalhe: async (
    eventoGrupo: string,
    forceRefresh = false,
    signal?: AbortSignal,
  ): Promise<DetalheEventoPayload> => {
    const response = await api.get('/marketing/detalhe-eventos', {
      params: { evento_grupo: eventoGrupo, force_refresh: forceRefresh },
      signal,
    });
    return response.data;
  },
};

export default api;
