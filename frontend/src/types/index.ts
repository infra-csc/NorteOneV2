export interface User {
  id: number;
  email: string;
  nome: string;
  perfil_acesso_id?: number;
  perfil_acesso_nome?: string;
  is_admin: boolean;
  centro_custo_id?: number;
  ativo: boolean;
}

export interface CentroCusto {
  id: number;
  codigo: string;
  nome: string;
  area?: string;
  gestor_responsavel?: string;
  ativo: boolean;
}

export interface Conta {
  id: number;
  codigo: string;
  nome: string;
  tipo: 'RECEITA' | 'DESPESA';
  grupo?: string;
  subgrupo?: string;
  ativo: boolean;
}

export interface Projeto {
  id: number;
  codigo: string;
  produto: string;
  modalidade: string;
  tipo_evento: string;
  evento: string;
  lei: string;
  cliente?: string | null;
  status: string;
  data_evento: string;
  local_evento: string;
  cidade?: string | null;
  estado?: string | null;
  capacidade_maxima?: number | null;
  etapa?: number | null;
  imagem_kv?: string | null;  // NOVO CAMPO
  created_at?: string | null;
}

// Interface estendida com dados de atletas (NOVA)
export interface ProjetoComAtletas extends Projeto {
  atletas_total: number;
  atletas_site: number;
  atletas_grupo: number;
}

// Interface para filtros disponíveis (NOVA)
export interface FiltrosDisponiveis {
  modalidades: string[];
  tipos_evento: string[];
  leis: string[];
  estados: string[];
  cidades: string[];
  anos: number[];
  status: string[];
}

// Interface para o estado dos filtros (NOVA)
export interface FiltrosState {
  status: string;
  modalidade: string;
  tipo_evento: string;
  lei: string;
  ano: string;
  busca: string;
}

// Interface para criar/atualizar projeto
export interface ProjetoCreate {
  codigo: string;
  produto: string;
  modalidade: string;
  tipo_evento: string;
  evento: string;
  lei: string;
  cliente?: string | null;
  status: string;
  data_evento: string;
  local_evento: string;
  cidade?: string | null;
  estado?: string | null;
  capacidade_maxima?: number | null;
  etapa?: number | null;
  imagem_kv?: string | null;  // NOVO CAMPO
}

export interface ProjetoUpdate {
  codigo?: string;
  produto?: string;
  modalidade?: string;
  tipo_evento?: string;
  evento?: string;
  lei?: string;
  cliente?: string | null;
  status?: string;
  data_evento?: string;
  local_evento?: string;
  cidade?: string | null;
  estado?: string | null;
  capacidade_maxima?: number | null;
  etapa?: number | null;
  imagem_kv?: string | null;  // NOVO CAMPO
}

export interface CategoriaAtleta {
  id: number;
  codigo: string;
  nome: string;
  faixa_etaria?: string;
  genero?: string;
  modalidade?: string;
  is_pcd: boolean;
  valor_inscricao_padrao?: number;
  custo_kit_padrao?: number;
  ativo: boolean;
}

export interface DashboardResumo {
  ano: number;
  financeiro: {
    orcado_receita: number;
    orcado_despesa: number;
    orcado_resultado: number;
    projetado_receita: number;
    projetado_despesa: number;
    projetado_resultado: number;
    realizado_receita: number;
    realizado_despesa: number;
    realizado_resultado: number;
    variacao_percentual: number;
  };
  atletas: {
    total_orcado: number;
    total_projetado: number;
    total_realizado: number;
  };
}

export interface EvolucaoMensal {
  mes: string;
  orcado: number;
  realizado: number;
}

export interface AtletasPorProjeto {
  evento: string;
  orcado: number;
  projetado: number;
  realizado: number;
}
