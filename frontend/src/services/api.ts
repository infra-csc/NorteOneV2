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
  list: async () => {
    const response = await api.get('/projetos/');
    return response.data;
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

export default api;
