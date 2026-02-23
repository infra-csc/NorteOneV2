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
  }
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
  list: async () => {
    const response = await api.get('/projetos/');
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
  list: async () => {
    const response = await api.get('/users/');
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
    return response.data;
  },
  delete: async (id: number) => {
    const response = await api.delete(`/cadastros/${id}`);
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
  isc: number;
  iscComponents: MarketingISCComponents;
  iscStatus: 'accelerating' | 'stable' | 'decelerating';
  suggestedAction: string;
  isActive: boolean;
  sku?: string;
  activeAction?: { id: number; tipo: string; descricao: string; data_acao: string; dias_restantes: number } | null;
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

export const marketingService = {
  getEventos: async (params?: {
    ano?: number;
    status?: string;
    categoria?: string;
    busca?: string;
    force_refresh?: boolean;
  }, signal?: AbortSignal): Promise<MarketingEventsResponse> => {
    const queryParams = new URLSearchParams();
    if (params?.ano) queryParams.append('ano', params.ano.toString());
    if (params?.status) queryParams.append('status', params.status);
    if (params?.categoria) queryParams.append('categoria', params.categoria);
    if (params?.busca) queryParams.append('busca', params.busca);
    if (params?.force_refresh) queryParams.append('force_refresh', 'true');
    const queryString = queryParams.toString() ? `?${queryParams.toString()}` : '';
    const response = await api.get(`/marketing/eventos${queryString}`, { signal });
    return response.data;
  },
  getResumo: async (ano?: number, signal?: AbortSignal): Promise<{ status: string; resumo: MarketingDashboardSummary; ultima_atualizacao: string }> => {
    const queryString = ano ? `?ano=${ano}` : '';
    const response = await api.get(`/marketing/resumo${queryString}`, { signal });
    return response.data;
  },
  getEventoById: async (id: string, signal?: AbortSignal, ano?: number, force_refresh?: boolean): Promise<{ 
    status: string; 
    evento: MarketingEvent; 
    dailySales?: { date: string; sales: number; expected: number; cumulativeSales: number; cumulativeExpected: number }[];
    commercialActions?: { id: string; type: string; description: string; date: string; impact?: string }[];
    projetos_vinculados?: { id: number; nome: string; sku: string }[];
    ultima_atualizacao: string 
  }> => {
    const queryParams = new URLSearchParams();
    if (ano) queryParams.append('ano', ano.toString());
    if (force_refresh) queryParams.append('force_refresh', 'true');
    const queryString = queryParams.toString() ? `?${queryParams.toString()}` : '';
    const response = await api.get(`/marketing/eventos/${id}${queryString}`, { signal });
    return response.data;
  },
  getAcoesComerciais: async (projetoId: string): Promise<{ status: string; acoes: any[] }> => {
    const response = await api.get(`/marketing/acoes-comerciais/${projetoId}`);
    return response.data;
  },
  createAcaoComercial: async (data: { projeto_id: number; tipo: string; descricao: string; data_acao: string }): Promise<any> => {
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
    const response = await api.get(`/marketing/curva-comparativa/${eventoId}`, { signal, params });
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
    const url = `/marketing/eventos/${eventoId}/medias-vendas?${queryParams.toString()}`;
    const response = await api.get(url, { signal });
    return response.data;
  },
  getSimulacao: async (eventoId: string, signal?: AbortSignal, ano?: number): Promise<any> => {
    const queryParams = new URLSearchParams();
    if (ano) queryParams.append('ano', ano.toString());
    const url = `/marketing/eventos/${eventoId}/simulacao?${queryParams.toString()}`;
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
  getCacheStatus: async (): Promise<{
    status: string;
    caches: Record<string, any>;
    config: Record<string, any>;
  }> => {
    const response = await api.get('/marketing/cache/status');
    return response.data;
  },
  getEventInsights: async (eventoId: string, signal?: AbortSignal, ano?: number, force_refresh?: boolean): Promise<any> => {
    const params: any = {};
    if (ano) params.ano = ano;
    if (force_refresh) params.force_refresh = true;
    const response = await api.get(`/marketing/eventos/${eventoId}/insights`, { signal, params });
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
};

export default api;
