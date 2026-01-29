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
  getEvolucaoMensal: async (filters: DashboardFilters) => {
    const params = buildFilterParams(filters);
    const response = await api.get(`/dashboard/evolucao-mensal?${params}`);
    return response.data;
  },
  getDistribuicaoTipo: async (filters: DashboardFilters) => {
    const params = buildFilterParams(filters);
    const response = await api.get(`/dashboard/distribuicao-tipo?${params}`);
    return response.data;
  },
  getAtletasPorModalidade: async (filters: DashboardFilters) => {
    const params = buildFilterParams(filters);
    const response = await api.get(`/dashboard/atletas-por-modalidade?${params}`);
    return response.data;
  },
  getAtletasPorProjeto: async (filters: DashboardFilters) => {
    const params = buildFilterParams(filters);
    const response = await api.get(`/dashboard/atletas-por-projeto?${params}`);
    return response.data;
  }
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

export const contasService = {
  list: async (tipo?: string) => {
    const params = tipo ? `?tipo=${tipo}` : '';
    const response = await api.get(`/contas/${params}`);
    return response.data;
  },
  create: async (data: any) => {
    const response = await api.post('/contas/', data);
    return response.data;
  },
  update: async (id: number, data: any) => {
    const response = await api.put(`/contas/${id}`, data);
    return response.data;
  },
  delete: async (id: number) => {
    const response = await api.delete(`/contas/${id}`);
    return response.data;
  }
};

export const projetosService = {
  // Método original
  list: async () => {
    const response = await api.get('/projetos/');
    return response.data;
  },

  // NOVO: Lista projetos com dados de atletas (com fallback para list original)
  listComAtletas: async (params?: Record<string, string>) => {
    try {
      const queryString = params && Object.keys(params).length > 0
        ? '?' + new URLSearchParams(params).toString() 
        : '';
      const response = await api.get(`/projetos/com-atletas${queryString}`);
      return response.data;
    } catch (error: any) {
      // Se o endpoint não existir (404), usa o endpoint antigo
      if (error.response?.status === 404) {
        console.warn('Endpoint /projetos/com-atletas não encontrado, usando fallback');
        const response = await api.get('/projetos/');
        // Adiciona campos de atletas vazios para compatibilidade
        return response.data.map((projeto: any) => ({
          ...projeto,
          atletas_total: projeto.atletas_total || 0,
          atletas_site: projeto.atletas_site || 0,
          atletas_grupo: projeto.atletas_grupo || 0,
        }));
      }
      throw error;
    }
  },

  // NOVO: Busca filtros disponíveis (com fallback para valores padrão)
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

export const orcamentoService = {
  list: async (params?: any) => {
    const queryParams = new URLSearchParams(params).toString();
    const response = await api.get(`/orcamento/?${queryParams}`);
    return response.data;
  },
  getResumo: async (ano: number) => {
    const response = await api.get(`/orcamento/resumo?ano=${ano}`);
    return response.data;
  },
  getPorMes: async (ano: number) => {
    const response = await api.get(`/orcamento/por-mes?ano=${ano}`);
    return response.data;
  },
  create: async (data: any) => {
    const response = await api.post('/orcamento/', data);
    return response.data;
  }
};

export const atletasService = {
  list: async (params?: any) => {
    const queryParams = params ? new URLSearchParams(params).toString() : '';
    const response = await api.get(`/atletas/?${queryParams}`);
    return response.data;
  },
  getResumo: async (projeto_id?: number) => {
    const params = projeto_id ? `?projeto_id=${projeto_id}` : '';
    const response = await api.get(`/atletas/resumo${params}`);
    return response.data;
  },
  getPorProjeto: async () => {
    const response = await api.get('/atletas/por-projeto');
    return response.data;
  },
  create: async (data: any) => {
    const response = await api.post('/atletas/', data);
    return response.data;
  },
  update: async (id: number, data: any) => {
    const response = await api.put(`/atletas/${id}`, data);
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
  responsavel?: ResponsavelInfo;
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

export interface InscricaoConsolidadaPorFonte {
  ativo?: { qtd: number; valor: number };
  magento?: { qtd: number; valor: number };
}

export interface InscricaoConsolidada {
  sku: string;
  id_evento: string | null;
  evento: string | null;
  qtd_vendida_total: number;
  valor_total: number;
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
  getConsolidado: async (sku?: string, incluirMagento: boolean = true): Promise<InscricoesConsolidadasResponse> => {
    const params = new URLSearchParams();
    if (sku) params.append('sku', sku);
    params.append('incluir_magento', incluirMagento ? 'true' : 'false');
    const queryString = params.toString() ? `?${params.toString()}` : '';
    const response = await api.get(`/inscricoes/consolidado${queryString}`);
    return response.data;
  },
  getBySku: async (sku: string, incluirMagento: boolean = true): Promise<InscricaoConsolidada | null> => {
    const data = await inscricoesConsolidadasService.getConsolidado(sku, incluirMagento);
    return data.dados.length > 0 ? data.dados[0] : null;
  }
};

export default api;
