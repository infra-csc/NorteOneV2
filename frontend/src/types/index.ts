export interface User {
  id: number;
  email: string;
  nome: string;
  perfil: string;
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
  cliente?: string;
  status: string;
  data_evento: string;
  local_evento: string;
  cidade?: string;
  estado?: string;
  capacidade_maxima?: number;
  etapa?: number;
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
