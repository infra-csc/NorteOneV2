import React, { useEffect, useState, useCallback, useMemo } from 'react';
import { projetosService, atletasExternosService, AtletaExternoPorProjeto } from '../../services/api';
import { Projeto } from '../../types';
import { useTheme } from '../../context/ThemeContext';
import { 
  Plus, Pencil, X, Check, Calendar, MapPin, Users, Globe, 
  UsersRound, Trophy, Zap, Target, TrendingUp, Sparkles,
  Image as ImageIcon, Building2, FileText, Search, Filter,
  ChevronDown, RotateCcw, Eye, BarChart3, ArrowUpRight, 
  ArrowDownRight, Minus, Award, Hash, Briefcase, Landmark,UserStar,Scale,Component,LoaderPinwheel,
  Database, RefreshCw, DollarSign, Store, ShoppingBag, Truck,
} from 'lucide-react';

const modalidades = ['Beach', 'Ciclismo', 'Corrida', 'Cultura', 'Educação', 'E-Sports', 'Família', 'Natação', 'Obstáculo', 'Saúde', 'Triathlon'];
const tiposEvento = ['Próprio', 'Incentivado', 'Organização', 'Licenciado'];
const leis = ['','LIE', 'PIE', 'FIA', 'ICMS RJ', 'PROAC', 'PRONAC', 'ROUANET', 'ISS RJ'];
const statusList = ['Em andamento', 'Concluído', 'Cancelado'];

// Interface estendida para incluir dados de atletas
interface ProjetoComAtletas extends Projeto {
  imagem_kv?: string;
  atletas_total?: number;
  atletas_site?: number;
  atletas_grupo?: number;
  qtd_atletas_orcado?: number;
  qtd_atletas_projetado?: number;
}

// Interface para filtros
interface Filtros {
  status: string;
  modalidade: string;
  tipo_evento: string;
  lei: string;
  ano: string;
  busca: string;
}

// Interface para opções de filtros do backend
interface FiltrosDisponiveis {
  modalidades: string[];
  tipos_evento: string[];
  leis: string[];
  estados: string[];
  cidades: string[];
  anos: number[];
  status: string[];
}

// Mapeamento de cores por modalidade
const modalidadeColors: Record<string, { bg: string; text: string; glow: string }> = {
  'Corrida': { bg: 'from-orange-500 to-red-600', text: 'text-orange-400', glow: 'shadow-orange-500/50' },
  'Ciclismo': { bg: 'from-cyan-500 to-blue-600', text: 'text-cyan-400', glow: 'shadow-cyan-500/50' },
  'Natação': { bg: 'from-blue-400 to-indigo-600', text: 'text-blue-400', glow: 'shadow-blue-500/50' },
  'Triathlon': { bg: 'from-purple-500 to-pink-600', text: 'text-purple-400', glow: 'shadow-purple-500/50' },
  'Beach': { bg: 'from-yellow-400 to-orange-500', text: 'text-yellow-400', glow: 'shadow-yellow-500/50' },
  'Obstáculo': { bg: 'from-green-500 to-emerald-600', text: 'text-green-400', glow: 'shadow-green-500/50' },
  'E-Sports': { bg: 'from-violet-500 to-purple-600', text: 'text-violet-400', glow: 'shadow-violet-500/50' },
  'Cultura': { bg: 'from-rose-500 to-pink-600', text: 'text-rose-400', glow: 'shadow-rose-500/50' },
  'Educação': { bg: 'from-teal-500 to-cyan-600', text: 'text-teal-400', glow: 'shadow-teal-500/50' },
  'Família': { bg: 'from-amber-500 to-yellow-600', text: 'text-amber-400', glow: 'shadow-amber-500/50' },
  'Saúde': { bg: 'from-lime-500 to-green-600', text: 'text-lime-400', glow: 'shadow-lime-500/50' },
};

const getModalidadeStyle = (modalidade: string) => {
  return modalidadeColors[modalidade] || { bg: 'from-gray-500 to-gray-600', text: 'text-gray-400', glow: 'shadow-gray-500/50' };
};

const getStatusStyle = (status: string) => {
  switch (status) {
    case 'Em andamento':
      return { bg: 'bg-emerald-500/20', text: 'text-emerald-400', border: 'border-emerald-500/50', icon: <Zap className="w-3 h-3" /> };
    case 'Concluído':
      return { bg: 'bg-blue-500/20', text: 'text-blue-400', border: 'border-blue-500/50', icon: <Check className="w-3 h-3" /> };
    case 'Cancelado':
      return { bg: 'bg-red-500/20', text: 'text-red-400', border: 'border-red-500/50', icon: <X className="w-3 h-3" /> };
    default:
      return { bg: 'bg-gray-500/20', text: 'text-gray-400', border: 'border-gray-500/50', icon: null };
  }
};

// Função helper para formatar a data corretamente sem problemas de timezone
const formatDateDisplay = (dateString: string | null | undefined): string => {
  if (!dateString) return '-';

  const parts = dateString.split('T')[0].split('-');
  if (parts.length === 3) {
    const [year, month, day] = parts;
    const date = new Date(parseInt(year), parseInt(month) - 1, parseInt(day));
    return date.toLocaleDateString('pt-BR', { day: '2-digit', month: 'short', year: '2-digit' });
  }

  return dateString;
};

// Função helper para formatar data completa
const formatDateFull = (dateString: string | null | undefined): string => {
  if (!dateString) return '-';

  const parts = dateString.split('T')[0].split('-');
  if (parts.length === 3) {
    const [year, month, day] = parts;
    const date = new Date(parseInt(year), parseInt(month) - 1, parseInt(day));
    return date.toLocaleDateString('pt-BR', { day: '2-digit', month: 'long', year: 'numeric' });
  }

  return dateString;
};

// Função helper para ordenar projetos por data (mais próximos primeiro)
const parseDateForSort = (dateString: string | null | undefined): number => {
  if (!dateString) return Infinity;

  const parts = dateString.split('T')[0].split('-');
  if (parts.length === 3) {
    const [year, month, day] = parts;
    return new Date(parseInt(year), parseInt(month) - 1, parseInt(day)).getTime();
  }

  return Infinity;
};

// Função para gerar insight de atletas
const getAtletasInsight = (orcado: number, realizado: number) => {
  if (orcado === 0) {
    return {
      percentage: 0,
      type: 'neutral' as const,
      message: 'Sem meta orçada definida',
      icon: <Minus className="w-4 h-4" />
    };
  }

  const percentage = ((realizado - orcado) / orcado) * 100;

  if (percentage > 10) {
    return {
      percentage: Math.abs(percentage),
      type: 'positive' as const,
      message: `Superou a meta em ${Math.abs(percentage).toFixed(1)}%`,
      icon: <ArrowUpRight className="w-4 h-4" />
    };
  } else if (percentage < -10) {
    return {
      percentage: Math.abs(percentage),
      type: 'negative' as const,
      message: `Abaixo da meta em ${Math.abs(percentage).toFixed(1)}%`,
      icon: <ArrowDownRight className="w-4 h-4" />
    };
  } else {
    return {
      percentage: Math.abs(percentage),
      type: 'neutral' as const,
      message: `Meta atingida (${percentage >= 0 ? '+' : ''}${percentage.toFixed(1)}%)`,
      icon: <Check className="w-4 h-4" />
    };
  }
};

const Projetos: React.FC = () => {
  const { isDark } = useTheme();
  const [projetos, setProjetos] = useState<ProjetoComAtletas[]>([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [showDetailsModal, setShowDetailsModal] = useState(false);
  const [selectedProjeto, setSelectedProjeto] = useState<ProjetoComAtletas | null>(null);
  const [editItem, setEditItem] = useState<ProjetoComAtletas | null>(null);
  const [showFilters, setShowFilters] = useState(false);
  const [filtrosDisponiveis, setFiltrosDisponiveis] = useState<FiltrosDisponiveis | null>(null);
  const [dadosExternos, setDadosExternos] = useState<AtletaExternoPorProjeto | null>(null);
  const [loadingExternos, setLoadingExternos] = useState(false);
  const [erroExternos, setErroExternos] = useState<string | null>(null);

  // Estado dos filtros
  const [filtros, setFiltros] = useState<Filtros>({
    status: '',
    modalidade: '',
    tipo_evento: '',
    lei: '',
    ano: '',
    busca: ''
  });

  // Estado do formulário
  const [form, setForm] = useState({
    codigo: '', produto: '', modalidade: 'Corrida', tipo_evento: 'Próprio', evento: '',
    lei: 'ROUANET', cliente: '', status: 'Em andamento', data_evento: '', local_evento: '',
    cidade: '', estado: '', capacidade_maxima: '', etapa: '', imagem_kv: ''
  });

  // Ordenar projetos por data (mais próximos primeiro)
  const projetosOrdenados = useMemo(() => {
    return [...projetos].sort((a, b) => {
      const dateA = parseDateForSort(a.data_evento);
      const dateB = parseDateForSort(b.data_evento);
      return dateA - dateB;
    });
  }, [projetos]);

  // Carregar filtros disponíveis
  const loadFiltros = async () => {
    try {
      const data = await projetosService.getFiltros();
      setFiltrosDisponiveis(data);
    } catch (error) {
      console.error('Erro ao carregar filtros:', error);
    }
  };

  // Carregar dados com filtros
  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, string> = {};
      if (filtros.status) params.status = filtros.status;
      if (filtros.modalidade) params.modalidade = filtros.modalidade;
      if (filtros.tipo_evento) params.tipo_evento = filtros.tipo_evento;
      if (filtros.lei) params.lei = filtros.lei;
      if (filtros.ano) params.ano = filtros.ano;
      if (filtros.busca) params.busca = filtros.busca;

      const data = await projetosService.listComAtletas(params);
      setProjetos(data);
    } catch (error) {
      console.error('Erro:', error);
      try {
        const data = await projetosService.list();
        setProjetos(data);
      } catch (e) {
        console.error('Erro no fallback:', e);
      }
    } finally {
      setLoading(false);
    }
  }, [filtros]);

  useEffect(() => { 
    loadFiltros();
  }, []);

  useEffect(() => { 
    loadData(); 
  }, [loadData]);

  const handleClearFilters = () => {
    setFiltros({
      status: '',
      modalidade: '',
      tipo_evento: '',
      lei: '',
      ano: '',
      busca: ''
    });
  };

  const hasActiveFilters = Object.values(filtros).some(v => v !== '');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const payload = { 
        ...form, 
        capacidade_maxima: form.capacidade_maxima ? Number(form.capacidade_maxima) : null, 
        etapa: form.etapa ? Number(form.etapa) : null
      };
      if (editItem) {
        await projetosService.update(editItem.id, payload);
      } else {
        await projetosService.create(payload);
      }
      setShowModal(false);
      setEditItem(null);
      loadData();
    } catch (error: any) {
      alert(error.response?.data?.detail || 'Erro ao salvar');
    }
  };

  const handleEdit = (item: ProjetoComAtletas) => {
    setEditItem(item);
    setForm({
      codigo: item.codigo || '',
      produto: item.produto || '',
      modalidade: item.modalidade || 'Corrida',
      tipo_evento: item.tipo_evento || 'Próprio',
      evento: item.evento || '',
      lei: item.lei || 'ROUANET',
      cliente: item.cliente || '',
      status: item.status || 'Em andamento',
      data_evento: item.data_evento ? item.data_evento.split('T')[0] : '',
      local_evento: item.local_evento || '',
      cidade: item.cidade || '',
      estado: item.estado || '',
      capacidade_maxima: item.capacidade_maxima?.toString() || '',
      etapa: item.etapa?.toString() || '',
      imagem_kv: item.imagem_kv || ''
    });
    setShowModal(true);
  };

  const handleViewDetails = async (projeto: ProjetoComAtletas) => {
    setSelectedProjeto(projeto);
    setShowDetailsModal(true);
    setDadosExternos(null);
    setErroExternos(null);
    
    if (projeto.codigo) {
      setLoadingExternos(true);
      try {
        const response = await atletasExternosService.getByProjeto(projeto.codigo);
        if (response.status === 'success' && response.data) {
          setDadosExternos(response.data);
        }
      } catch (error: any) {
        if (error.response?.status !== 503) {
          setErroExternos('Não foi possível carregar dados externos');
        }
      } finally {
        setLoadingExternos(false);
      }
    }
  };

  const handleRefreshExternos = async () => {
    if (!selectedProjeto?.codigo) return;
    setLoadingExternos(true);
    setErroExternos(null);
    try {
      await atletasExternosService.clearCache();
      const response = await atletasExternosService.getByProjeto(selectedProjeto.codigo);
      if (response.status === 'success' && response.data) {
        setDadosExternos(response.data);
      }
    } catch (error: any) {
      setErroExternos('Erro ao atualizar dados');
    } finally {
      setLoadingExternos(false);
    }
  };

  const openNewModal = () => {
    setEditItem(null);
    setForm({
      codigo: '', produto: '', modalidade: 'Corrida', tipo_evento: 'Próprio', evento: '',
      lei: 'ROUANET', cliente: '', status: 'Em andamento', data_evento: '', local_evento: '',
      cidade: '', estado: '', capacidade_maxima: '', etapa: '', imagem_kv: ''
    });
    setShowModal(true);
  };

  // Stats cards data
  const totalProjetos = projetos.length;
  const emAndamento = projetos.filter(p => p.status === 'Em andamento').length;
  const concluidos = projetos.filter(p => p.status === 'Concluído').length;
  const totalAtletas = projetos.reduce((acc, p) => acc + (p.atletas_total || 0), 0);

  return (
    <div className="min-h-screen">
      {/* Background effects */}
      <div className="fixed inset-0 pointer-events-none overflow-hidden">
        <div className="absolute top-0 left-1/4 w-96 h-96 bg-purple-500/10 rounded-full blur-3xl animate-pulse" />
        <div className="absolute bottom-0 right-1/4 w-96 h-96 bg-cyan-500/10 rounded-full blur-3xl animate-pulse" style={{ animationDelay: '1s' }} />
        <div className="absolute top-1/2 left-1/2 w-64 h-64 bg-orange-500/5 rounded-full blur-3xl animate-pulse" style={{ animationDelay: '2s' }} />
      </div>

      <div className="relative z-10 space-y-8 p-6">
        {/* Header */}
        <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
          <div>
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-xl bg-gradient-to-br from-purple-500 to-pink-500 shadow-lg shadow-purple-500/30">
                <Trophy className="w-6 h-6 text-white" />
              </div>
              <div>
                <h1 className={`text-3xl font-black tracking-tight ${isDark ? 'text-white' : 'text-gray-900'}`}>
                  Eventos
                  <span className="bg-gradient-to-r from-purple-400 via-pink-500 to-orange-500 bg-clip-text text-transparent"> 2026</span>
                </h1>
                <p className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>
                  Gerencie seus eventos esportivos com estilo
                </p>
              </div>
            </div>
          </div>

          <button 
            onClick={openNewModal} 
            className="group relative px-6 py-3 bg-gradient-to-r from-purple-600 via-pink-600 to-orange-500 text-white rounded-2xl font-semibold shadow-xl shadow-purple-500/30 hover:shadow-purple-500/50 transition-all duration-300 hover:scale-105 overflow-hidden"
          >
            <div className="absolute inset-0 bg-gradient-to-r from-purple-400 via-pink-400 to-orange-400 opacity-0 group-hover:opacity-100 transition-opacity duration-300" />
            <span className="relative flex items-center gap-2">
              <Plus className="w-5 h-5" />
              Novo Evento
              <Sparkles className="w-4 h-4" />
            </span>
          </button>
        </div>

        {/* Search and Filters Bar */}
        <div className={`p-4 rounded-2xl ${isDark ? 'bg-gray-800/50 backdrop-blur-xl border border-gray-700/50' : 'bg-white/70 backdrop-blur-xl border border-gray-200'}`}>
          <div className="flex flex-col md:flex-row gap-4">
            <div className="flex-1 relative">
              <Search className={`absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 ${isDark ? 'text-gray-400' : 'text-gray-500'}`} />
              <input
                type="text"
                placeholder="Buscar por código, nome do evento ou produto..."
                value={filtros.busca}
                onChange={(e) => setFiltros({ ...filtros, busca: e.target.value })}
                className={`w-full pl-10 pr-4 py-3 rounded-xl border ${isDark ? 'bg-gray-700/50 border-gray-600 text-white placeholder-gray-400' : 'bg-white border-gray-300 placeholder-gray-500'} focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all`}
              />
            </div>

            <button
              onClick={() => setShowFilters(!showFilters)}
              className={`flex items-center gap-2 px-4 py-3 rounded-xl border transition-all ${
                showFilters || hasActiveFilters
                  ? 'bg-purple-500/20 border-purple-500/50 text-purple-400'
                  : isDark 
                    ? 'bg-gray-700/50 border-gray-600 text-gray-300 hover:bg-gray-700' 
                    : 'bg-white border-gray-300 text-gray-700 hover:bg-gray-50'
              }`}
            >
              <Filter className="w-5 h-5" />
              <span className="font-medium">Filtros</span>
              {hasActiveFilters && (
                <span className="px-2 py-0.5 text-xs font-bold bg-purple-500 text-white rounded-full">
                  {Object.values(filtros).filter(v => v !== '').length}
                </span>
              )}
              <ChevronDown className={`w-4 h-4 transition-transform ${showFilters ? 'rotate-180' : ''}`} />
            </button>

            {hasActiveFilters && (
              <button
                onClick={handleClearFilters}
                className={`flex items-center gap-2 px-4 py-3 rounded-xl border ${isDark ? 'border-gray-600 text-gray-300 hover:bg-gray-700' : 'border-gray-300 text-gray-700 hover:bg-gray-50'} transition-all`}
              >
                <RotateCcw className="w-4 h-4" />
                <span className="font-medium">Limpar</span>
              </button>
            )}
          </div>

          {showFilters && (
            <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mt-4 pt-4 border-t border-gray-700/50">
              <div>
                <label className={`block text-xs font-bold mb-2 ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>Status</label>
                <select
                  value={filtros.status}
                  onChange={(e) => setFiltros({ ...filtros, status: e.target.value })}
                  className={`w-full px-3 py-2 rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-purple-500`}
                >
                  <option value="">Todos</option>
                  {statusList.map(s => (
                    <option key={s} value={s}>{s.replace('_', ' ')}</option>
                  ))}
                </select>
              </div>

              <div>
                <label className={`block text-xs font-bold mb-2 ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>Modalidade</label>
                <select
                  value={filtros.modalidade}
                  onChange={(e) => setFiltros({ ...filtros, modalidade: e.target.value })}
                  className={`w-full px-3 py-2 rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-purple-500`}
                >
                  <option value="">Todas</option>
                  {(filtrosDisponiveis?.modalidades || modalidades).map(m => (
                    <option key={m} value={m}>{m}</option>
                  ))}
                </select>
              </div>

              <div>
                <label className={`block text-xs font-bold mb-2 ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>Tipo Evento</label>
                <select
                  value={filtros.tipo_evento}
                  onChange={(e) => setFiltros({ ...filtros, tipo_evento: e.target.value })}
                  className={`w-full px-3 py-2 rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-purple-500`}
                >
                  <option value="">Todos</option>
                  {(filtrosDisponiveis?.tipos_evento || tiposEvento).map(t => (
                    <option key={t} value={t}>{t}</option>
                  ))}
                </select>
              </div>

              <div>
                <label className={`block text-xs font-bold mb-2 ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>Lei</label>
                <select
                  value={filtros.lei}
                  onChange={(e) => setFiltros({ ...filtros, lei: e.target.value })}
                  className={`w-full px-3 py-2 rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-purple-500`}
                >
                  <option value="">Todas</option>
                  {(filtrosDisponiveis?.leis || leis).map(l => (
                    <option key={l} value={l}>{l}</option>
                  ))}
                </select>
              </div>

              <div>
                <label className={`block text-xs font-bold mb-2 ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>Ano</label>
                <select
                  value={filtros.ano}
                  onChange={(e) => setFiltros({ ...filtros, ano: e.target.value })}
                  className={`w-full px-3 py-2 rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-purple-500`}
                >
                  <option value="">Todos</option>
                  {filtrosDisponiveis?.anos?.map(a => (
                    <option key={a} value={a}>{a}</option>
                  ))}
                </select>
              </div>
            </div>
          )}
        </div>

        {/* Stats Cards */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className={`relative overflow-hidden rounded-2xl p-4 ${isDark ? 'bg-gray-800/50 backdrop-blur-xl border border-gray-700/50' : 'bg-white/70 backdrop-blur-xl border border-gray-200'}`}>
            <div className="absolute top-0 right-0 w-20 h-20 bg-gradient-to-br from-purple-500/20 to-transparent rounded-full blur-2xl" />
            <div className="relative">
              <div className="flex items-center gap-2 mb-2">
                <div className="p-1.5 rounded-lg bg-purple-500/20">
                  <Target className="w-4 h-4 text-purple-400" />
                </div>
                <span className={`text-xs font-medium ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>Total Eventos</span>
              </div>
              <p className={`text-3xl font-black ${isDark ? 'text-white' : 'text-gray-900'}`}>{totalProjetos}</p>
            </div>
          </div>

          <div className={`relative overflow-hidden rounded-2xl p-4 ${isDark ? 'bg-gray-800/50 backdrop-blur-xl border border-gray-700/50' : 'bg-white/70 backdrop-blur-xl border border-gray-200'}`}>
            <div className="absolute top-0 right-0 w-20 h-20 bg-gradient-to-br from-emerald-500/20 to-transparent rounded-full blur-2xl" />
            <div className="relative">
              <div className="flex items-center gap-2 mb-2">
                <div className="p-1.5 rounded-lg bg-emerald-500/20">
                  <Zap className="w-4 h-4 text-emerald-400" />
                </div>
                <span className={`text-xs font-medium ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>Em Andamento</span>
              </div>
              <p className={`text-3xl font-black ${isDark ? 'text-white' : 'text-gray-900'}`}>{emAndamento}</p>
            </div>
          </div>

          <div className={`relative overflow-hidden rounded-2xl p-4 ${isDark ? 'bg-gray-800/50 backdrop-blur-xl border border-gray-700/50' : 'bg-white/70 backdrop-blur-xl border border-gray-200'}`}>
            <div className="absolute top-0 right-0 w-20 h-20 bg-gradient-to-br from-blue-500/20 to-transparent rounded-full blur-2xl" />
            <div className="relative">
              <div className="flex items-center gap-2 mb-2">
                <div className="p-1.5 rounded-lg bg-blue-500/20">
                  <Check className="w-4 h-4 text-blue-400" />
                </div>
                <span className={`text-xs font-medium ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>Concluídos</span>
              </div>
              <p className={`text-3xl font-black ${isDark ? 'text-white' : 'text-gray-900'}`}>{concluidos}</p>
            </div>
          </div>

          <div className={`relative overflow-hidden rounded-2xl p-4 ${isDark ? 'bg-gray-800/50 backdrop-blur-xl border border-gray-700/50' : 'bg-white/70 backdrop-blur-xl border border-gray-200'}`}>
            <div className="absolute top-0 right-0 w-20 h-20 bg-gradient-to-br from-orange-500/20 to-transparent rounded-full blur-2xl" />
            <div className="relative">
              <div className="flex items-center gap-2 mb-2">
                <div className="p-1.5 rounded-lg bg-orange-500/20">
                  <Users className="w-4 h-4 text-orange-400" />
                </div>
                <span className={`text-xs font-medium ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>Total Atletas</span>
              </div>
              <p className={`text-3xl font-black ${isDark ? 'text-white' : 'text-gray-900'}`}>{totalAtletas.toLocaleString('pt-BR')}</p>
            </div>
          </div>
        </div>

        {/* Cards Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
          {loading ? (
            <div className="col-span-full flex flex-col items-center justify-center py-20">
              <div className="relative">
                <div className="w-16 h-16 border-4 border-purple-500/30 rounded-full" />
                <div className="absolute top-0 left-0 w-16 h-16 border-4 border-transparent border-t-purple-500 rounded-full animate-spin" />
              </div>
              <p className={`mt-4 ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>Carregando eventos...</p>
            </div>
          ) : projetosOrdenados.length === 0 ? (
            <div className="col-span-full flex flex-col items-center justify-center py-20">
              <div className="p-4 rounded-2xl bg-gradient-to-br from-purple-500/20 to-pink-500/20 mb-4">
                <Trophy className="w-12 h-12 text-purple-400" />
              </div>
              <p className={`text-lg font-semibold ${isDark ? 'text-white' : 'text-gray-900'}`}>
                {hasActiveFilters ? 'Nenhum evento encontrado com esses filtros' : 'Nenhum evento encontrado'}
              </p>
              <p className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>
                {hasActiveFilters ? 'Tente ajustar os filtros' : 'Crie seu primeiro evento clicando no botão acima'}
              </p>
              {hasActiveFilters && (
                <button
                  onClick={handleClearFilters}
                  className="mt-4 px-4 py-2 bg-purple-500/20 text-purple-400 rounded-lg hover:bg-purple-500/30 transition-colors"
                >
                  Limpar filtros
                </button>
              )}
            </div>
          ) : projetosOrdenados.map((projeto, index) => {
            const modalidadeStyle = getModalidadeStyle(projeto.modalidade);
            const statusStyle = getStatusStyle(projeto.status);
            const atletasTotal = projeto.atletas_total || 0;
            const atletasSite = projeto.atletas_site || 0;
            const atletasGrupo = projeto.atletas_grupo || 0;

            return (
              <div 
                key={projeto.id} 
                className={`group relative overflow-hidden rounded-3xl ${isDark ? 'bg-gray-800/80 backdrop-blur-xl' : 'bg-white/90 backdrop-blur-xl'} border ${isDark ? 'border-gray-700/50' : 'border-gray-200'} shadow-xl hover:shadow-2xl transition-all duration-500 hover:-translate-y-2`}
                style={{ animationDelay: `${index * 100}ms` }}
              >
                <div className={`absolute inset-0 bg-gradient-to-br ${modalidadeStyle.bg} opacity-0 group-hover:opacity-10 transition-opacity duration-500 pointer-events-none`} />

                {/* Image KV Section */}
                <div className="relative h-48 overflow-hidden">
                  {projeto.imagem_kv ? (
                    <img 
                      src={projeto.imagem_kv} 
                      alt={projeto.evento}
                      className="w-full h-full object-cover transition-transform duration-700 group-hover:scale-110"
                      onError={(e) => {
                        (e.target as HTMLImageElement).style.display = 'none';
                        (e.target as HTMLImageElement).nextElementSibling?.classList.remove('hidden');
                      }}
                    />
                  ) : null}
                  <div className={`w-full h-full bg-gradient-to-br ${modalidadeStyle.bg} flex items-center justify-center ${projeto.imagem_kv ? 'hidden' : ''}`}>
                    <div className="text-center">
                      <ImageIcon className="w-12 h-12 text-white/50 mx-auto mb-2" />
                      <span className="text-white/70 text-sm font-medium">KV do Evento</span>
                    </div>
                  </div>

                  <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/20 to-transparent pointer-events-none" />

                  <div className={`absolute top-4 right-4 px-3 py-1.5 rounded-full ${statusStyle.bg} ${statusStyle.border} border backdrop-blur-md flex items-center gap-1.5`}>
                    {statusStyle.icon}
                    <span className={`text-xs font-bold ${statusStyle.text}`}>
                      {projeto.status.replace('_', ' ')}
                    </span>
                  </div>

                  <div className={`absolute top-4 left-4 px-3 py-1.5 rounded-full bg-black/40 backdrop-blur-md border border-white/20`}>
                    <span className={`text-xs font-bold ${modalidadeStyle.text}`}>
                      {projeto.modalidade}
                    </span>
                  </div>

                  <div className="absolute bottom-0 left-0 right-0 p-4">
                    <span className="text-white/60 text-xs font-mono tracking-wider">{projeto.codigo}</span>
                    <h3 className="text-xl font-black text-white leading-tight mt-1 line-clamp-2">
                      {projeto.evento}
                    </h3>
                  </div>
                </div>

                {/* Content Section */}
                <div className="p-5 space-y-4">
                  <div className="grid grid-cols-2 gap-3">
                    <div className={`flex items-center gap-2 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
                      <div className={`p-1.5 rounded-lg ${isDark ? 'bg-gray-700' : 'bg-gray-100'}`}>
                        <Calendar className="w-4 h-4 text-pink-500" />
                      </div>
                      <span className="text-sm font-medium">
                        {formatDateDisplay(projeto.data_evento)}
                      </span>
                    </div>

                    <div className={`flex items-center gap-2 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
                      <div className={`p-1.5 rounded-lg ${isDark ? 'bg-gray-700' : 'bg-gray-100'}`}>
                        <MapPin className="w-4 h-4 text-cyan-500" />
                      </div>
                      <span className="text-sm font-medium truncate">
                        {projeto.cidade || projeto.local_evento}
                      </span>
                    </div>

                    <div className={`flex items-center gap-2 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
                      <div className={`p-1.5 rounded-lg ${isDark ? 'bg-gray-700' : 'bg-gray-100'}`}>
                        <FileText className="w-4 h-4 text-purple-500" />
                      </div>
                      <span className="text-sm font-medium">{projeto.lei}</span>
                    </div>

                    <div className={`flex items-center gap-2 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
                      <div className={`p-1.5 rounded-lg ${isDark ? 'bg-gray-700' : 'bg-gray-100'}`}>
                        <Component className="w-4 h-4 text-amber-500" />
                      </div>
                      <span className="text-sm font-medium">{projeto.tipo_evento}</span>
                    </div>
                  </div>

                  {/* Atletas Section */}
                  <div className={`p-4 rounded-2xl ${isDark ? 'bg-gray-900/50' : 'bg-gray-50'} border ${isDark ? 'border-gray-700/50' : 'border-gray-200'}`}>
                    <div className="flex items-center gap-2 mb-3">
                      <TrendingUp className={`w-4 h-4 ${modalidadeStyle.text}`} />
                      <span className={`text-xs font-bold uppercase tracking-wider ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>
                        Atletas
                      </span>
                    </div>

                    <div className="grid grid-cols-3 gap-2">
                      {/* Total/Realizado */}
                      <div className={`relative overflow-hidden p-2 rounded-xl ${isDark ? 'bg-gradient-to-br from-purple-500/20 to-pink-500/20 border border-purple-500/30' : 'bg-gradient-to-br from-purple-100 to-pink-100 border border-purple-200'}`}>
                        <div className="relative text-center">
                          <Users className="w-4 h-4 text-purple-500 mx-auto mb-1" />
                          <p className={`text-sm font-black ${isDark ? 'text-white' : 'text-gray-900'}`}>
                            {atletasTotal.toLocaleString('pt-BR')}
                          </p>
                          <span className={`text-[9px] font-bold uppercase tracking-wider ${isDark ? 'text-purple-400' : 'text-purple-600'}`}>
                            Realizado
                          </span>
                        </div>
                      </div>

                      {/* Site */}
                      <div className={`relative overflow-hidden p-2 rounded-xl ${isDark ? 'bg-gradient-to-br from-cyan-500/20 to-blue-500/20 border border-cyan-500/30' : 'bg-gradient-to-br from-cyan-100 to-blue-100 border border-cyan-200'}`}>
                        <div className="relative text-center">
                          <Globe className="w-4 h-4 text-cyan-500 mx-auto mb-1" />
                          <p className={`text-sm font-black ${isDark ? 'text-white' : 'text-gray-900'}`}>
                            {atletasSite.toLocaleString('pt-BR')}
                          </p>
                          <span className={`text-[9px] font-bold uppercase tracking-wider ${isDark ? 'text-cyan-400' : 'text-cyan-600'}`}>
                            Site
                          </span>
                        </div>
                      </div>

                      {/* Grupo */}
                      <div className={`relative overflow-hidden p-2 rounded-xl ${isDark ? 'bg-gradient-to-br from-orange-500/20 to-amber-500/20 border border-orange-500/30' : 'bg-gradient-to-br from-orange-100 to-amber-100 border border-orange-200'}`}>
                        <div className="relative text-center">
                          <Award className="w-4 h-4 text-orange-500 mx-auto mb-1" />
                          <p className={`text-sm font-black ${isDark ? 'text-white' : 'text-gray-900'}`}>
                            {atletasGrupo.toLocaleString('pt-BR')}
                          </p>
                          <span className={`text-[9px] font-bold uppercase tracking-wider ${isDark ? 'text-orange-400' : 'text-orange-600'}`}>
                            Grupo
                          </span>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Actions */}
                  <div className="flex justify-end gap-2 pt-2">
                    <button 
                      onClick={(e) => {
                        e.preventDefault();
                        e.stopPropagation();
                        handleViewDetails(projeto);
                      }} 
                      className={`flex items-center gap-2 px-4 py-2 rounded-xl ${isDark ? 'bg-purple-500/20 hover:bg-purple-500/30 text-purple-400' : 'bg-purple-100 hover:bg-purple-200 text-purple-700'} transition-all duration-300 hover:scale-105`}
                    >
                      <Eye className="w-4 h-4" />
                      <span className="text-sm font-medium">Detalhes</span>
                    </button>
                    <button 
                      onClick={(e) => {
                        e.preventDefault();
                        e.stopPropagation();
                        handleEdit(projeto);
                      }} 
                      className={`flex items-center gap-2 px-4 py-2 rounded-xl ${isDark ? 'bg-gray-700 hover:bg-gray-600 text-gray-300' : 'bg-gray-100 hover:bg-gray-200 text-gray-700'} transition-all duration-300 hover:scale-105`}
                    >
                      <Pencil className="w-4 h-4" />
                      <span className="text-sm font-medium">Editar</span>
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Details Modal */}
      {showDetailsModal && selectedProjeto && (
        <div 
          className="fixed inset-0 bg-black/70 backdrop-blur-md flex items-center justify-center z-50 overflow-y-auto p-4"
          onClick={(e) => {
            if (e.target === e.currentTarget) {
              setShowDetailsModal(false);
              setSelectedProjeto(null);
            }
          }}
        >
          <div 
            className={`${isDark ? 'bg-gray-900' : 'bg-white'} rounded-3xl w-full max-w-5xl my-8 shadow-2xl border ${isDark ? 'border-gray-700' : 'border-gray-200'} overflow-hidden`}
            onClick={(e) => e.stopPropagation()}
            style={{ animation: 'slideUp 0.4s ease-out' }}
          >
            {/* Hero Image Section */}
            <div className="relative h-64 md:h-80 overflow-hidden">
              {selectedProjeto.imagem_kv ? (
                <img 
                  src={selectedProjeto.imagem_kv} 
                  alt={selectedProjeto.evento}
                  className="w-full h-full object-cover"
                />
              ) : (
                <div className={`w-full h-full bg-gradient-to-br ${getModalidadeStyle(selectedProjeto.modalidade).bg} flex items-center justify-center`}>
                  <div className="text-center">
                    <ImageIcon className="w-20 h-20 text-white/30 mx-auto mb-4" />
                    <span className="text-white/50 text-lg font-medium">Sem imagem do evento</span>
                  </div>
                </div>
              )}

              {/* Gradient Overlay */}
              <div className="absolute inset-0 bg-gradient-to-t from-black/90 via-black/40 to-transparent" />

              {/* Close Button */}
              <button 
                onClick={() => {
                  setShowDetailsModal(false);
                  setSelectedProjeto(null);
                }}
                className="absolute top-4 right-4 p-2 rounded-full bg-black/40 backdrop-blur-md border border-white/20 text-white hover:bg-black/60 transition-colors"
              >
                <X className="w-6 h-6" />
              </button>

              {/* Badges */}
              <div className="absolute top-4 left-4 flex gap-2">
                <div className={`px-4 py-2 rounded-full bg-black/40 backdrop-blur-md border border-white/20`}>
                  <span className={`text-sm font-bold ${getModalidadeStyle(selectedProjeto.modalidade).text}`}>
                    {selectedProjeto.modalidade}
                  </span>
                </div>
                <div className={`px-4 py-2 rounded-full ${getStatusStyle(selectedProjeto.status).bg} ${getStatusStyle(selectedProjeto.status).border} border backdrop-blur-md flex items-center gap-2`}>
                  {getStatusStyle(selectedProjeto.status).icon}
                  <span className={`text-sm font-bold ${getStatusStyle(selectedProjeto.status).text}`}>
                    {selectedProjeto.status.replace('_', ' ')}
                  </span>
                </div>
              </div>

              {/* Event Title */}
              <div className="absolute bottom-0 left-0 right-0 p-6 md:p-8">
                <span className="text-white/60 text-sm font-mono tracking-wider">{selectedProjeto.codigo}</span>
                <h2 className="text-3xl md:text-4xl font-black text-white leading-tight mt-2">
                  {selectedProjeto.evento}
                </h2>
              </div>
            </div>

            {/* Content */}
            <div className="p-6 md:p-8 space-y-8">
              {/* Quick Info Grid */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div className={`p-4 rounded-2xl ${isDark ? 'bg-gray-800/50' : 'bg-gray-50'} border ${isDark ? 'border-gray-700' : 'border-gray-200'}`}>
                  <div className="flex items-center gap-2 mb-2">
                    <Calendar className="w-5 h-5 text-pink-500" />
                    <span className={`text-xs font-bold uppercase ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Data</span>
                  </div>
                  <p className={`text-lg font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>
                    {formatDateFull(selectedProjeto.data_evento)}
                  </p>
                </div>

                <div className={`p-4 rounded-2xl ${isDark ? 'bg-gray-800/50' : 'bg-gray-50'} border ${isDark ? 'border-gray-700' : 'border-gray-200'}`}>
                  <div className="flex items-center gap-2 mb-2">
                    <MapPin className="w-5 h-5 text-cyan-500" />
                    <span className={`text-xs font-bold uppercase ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Local</span>
                  </div>
                  <p className={`text-lg font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>
                    {selectedProjeto.cidade}{selectedProjeto.estado ? `, ${selectedProjeto.estado}` : ''}
                  </p>
                  <p className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>
                    {selectedProjeto.local_evento}
                  </p>
                </div>

                <div className={`p-4 rounded-2xl ${isDark ? 'bg-gray-800/50' : 'bg-gray-50'} border ${isDark ? 'border-gray-700' : 'border-gray-200'}`}>
                  <div className="flex items-center gap-2 mb-2">
                    <Scale className="w-5 h-5 text-purple-500" />
                    <span className={`text-xs font-bold uppercase ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Lei</span>
                  </div>
                  <p className={`text-lg font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>
                    {selectedProjeto.lei}
                  </p>
                </div>

                <div className={`p-4 rounded-2xl ${isDark ? 'bg-gray-800/50' : 'bg-gray-50'} border ${isDark ? 'border-gray-700' : 'border-gray-200'}`}>
                  <div className="flex items-center gap-2 mb-2">
                    <Component className="w-5 h-5 text-amber-500" />
                    <span className={`text-xs font-bold uppercase ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Tipo</span>
                  </div>
                  <p className={`text-lg font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>
                    {selectedProjeto.tipo_evento}
                  </p>
                </div>
              </div>

              {/* Additional Info */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div className={`p-4 rounded-2xl ${isDark ? 'bg-gray-800/50' : 'bg-gray-50'} border ${isDark ? 'border-gray-700' : 'border-gray-200'}`}>
                  <div className="flex items-center gap-2 mb-2">
                    <Briefcase className="w-5 h-5 text-indigo-500" />
                    <span className={`text-xs font-bold uppercase ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Produto</span>
                  </div>
                  <p className={`text-lg font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>
                    {selectedProjeto.produto || '-'}
                  </p>
                </div>

                <div className={`p-4 rounded-2xl ${isDark ? 'bg-gray-800/50' : 'bg-gray-50'} border ${isDark ? 'border-gray-700' : 'border-gray-200'}`}>
                  <div className="flex items-center gap-2 mb-2">
                    <UserStar className="w-5 h-5 text-rose-500" />
                    <span className={`text-xs font-bold uppercase ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Cliente</span>
                  </div>
                  <p className={`text-lg font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>
                    {selectedProjeto.cliente || '-'}
                  </p>
                </div>

                <div className={`p-4 rounded-2xl ${isDark ? 'bg-gray-800/50' : 'bg-gray-50'} border ${isDark ? 'border-gray-700' : 'border-gray-200'}`}>
                  <div className="flex items-center gap-2 mb-2">
                    <Hash className="w-5 h-5 text-emerald-500" />
                    <span className={`text-xs font-bold uppercase ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Etapa</span>
                  </div>
                  <p className={`text-lg font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>
                    {selectedProjeto.etapa || '-'}
                  </p>
                </div>

                <div className={`p-4 rounded-2xl ${isDark ? 'bg-gray-800/50' : 'bg-gray-50'} border ${isDark ? 'border-gray-700' : 'border-gray-200'}`}>
                  <div className="flex items-center gap-2 mb-2">
                    <Users className="w-5 h-5 text-blue-500" />
                    <span className={`text-xs font-bold uppercase ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Capacidade</span>
                  </div>
                  <p className={`text-lg font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>
                    {selectedProjeto.capacidade_maxima?.toLocaleString('pt-BR') || '-'}
                  </p>
                </div>
              </div>

              {/* Atletas Analysis Section */}
              <div className={`p-6 rounded-3xl ${isDark ? 'bg-gradient-to-br from-gray-800 to-gray-800/50' : 'bg-gradient-to-br from-gray-50 to-white'} border ${isDark ? 'border-gray-700' : 'border-gray-200'}`}>
                <div className="flex items-center gap-3 mb-6">
                  <div className="p-2 rounded-xl bg-gradient-to-br from-purple-500 to-pink-500">
                    <BarChart3 className="w-5 h-5 text-white" />
                  </div>
                  <div>
                    <h3 className={`text-xl font-black ${isDark ? 'text-white' : 'text-gray-900'}`}>
                      Análise de Atletas
                    </h3>
                    <p className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>
                      Comparativo entre orçado, projetado e realizado
                    </p>
                  </div>
                </div>

                <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-6">
                  {/* Orçado */}
                  <div className={`relative overflow-hidden p-4 rounded-2xl ${isDark ? 'bg-gradient-to-br from-amber-500/20 to-yellow-500/20 border border-amber-500/30' : 'bg-gradient-to-br from-amber-50 to-yellow-50 border border-amber-200'}`}>
                    <div className="absolute top-0 right-0 w-16 h-16 bg-amber-500/20 rounded-full blur-2xl" />
                    <div className="relative text-center">
                      <Landmark className="w-6 h-6 text-amber-500 mx-auto mb-2" />
                      <p className={`text-2xl font-black ${isDark ? 'text-white' : 'text-gray-900'}`}>
                        {(selectedProjeto.qtd_atletas_orcado || 0).toLocaleString('pt-BR')}
                      </p>
                      <span className={`text-xs font-bold uppercase tracking-wider ${isDark ? 'text-amber-400' : 'text-amber-600'}`}>
                        Orçado
                      </span>
                    </div>
                  </div>

                  {/* Projetado */}
                  <div className={`relative overflow-hidden p-4 rounded-2xl ${isDark ? 'bg-gradient-to-br from-indigo-500/20 to-violet-500/20 border border-indigo-500/30' : 'bg-gradient-to-br from-indigo-50 to-violet-50 border border-indigo-200'}`}>
                    <div className="absolute top-0 right-0 w-16 h-16 bg-indigo-500/20 rounded-full blur-2xl" />
                    <div className="relative text-center">
                      <Target className="w-6 h-6 text-indigo-500 mx-auto mb-2" />
                      <p className={`text-2xl font-black ${isDark ? 'text-white' : 'text-gray-900'}`}>
                        {(selectedProjeto.qtd_atletas_projetado || 0).toLocaleString('pt-BR')}
                      </p>
                      <span className={`text-xs font-bold uppercase tracking-wider ${isDark ? 'text-indigo-400' : 'text-indigo-600'}`}>
                        Projetado
                      </span>
                    </div>
                  </div>

                  {/* Total Realizado */}
                  <div className={`relative overflow-hidden p-4 rounded-2xl ${isDark ? 'bg-gradient-to-br from-purple-500/20 to-pink-500/20 border border-purple-500/30' : 'bg-gradient-to-br from-purple-50 to-pink-50 border border-purple-200'}`}>
                    <div className="absolute top-0 right-0 w-16 h-16 bg-purple-500/20 rounded-full blur-2xl" />
                    <div className="relative text-center">
                      <Users className="w-6 h-6 text-purple-500 mx-auto mb-2" />
                      <p className={`text-2xl font-black ${isDark ? 'text-white' : 'text-gray-900'}`}>
                        {(selectedProjeto.atletas_total || 0).toLocaleString('pt-BR')}
                      </p>
                      <span className={`text-xs font-bold uppercase tracking-wider ${isDark ? 'text-purple-400' : 'text-purple-600'}`}>
                        Realizado
                      </span>
                    </div>
                  </div>

                  {/* Site */}
                  <div className={`relative overflow-hidden p-4 rounded-2xl ${isDark ? 'bg-gradient-to-br from-cyan-500/20 to-blue-500/20 border border-cyan-500/30' : 'bg-gradient-to-br from-cyan-50 to-blue-50 border border-cyan-200'}`}>
                    <div className="absolute top-0 right-0 w-16 h-16 bg-cyan-500/20 rounded-full blur-2xl" />
                    <div className="relative text-center">
                      <Globe className="w-6 h-6 text-cyan-500 mx-auto mb-2" />
                      <p className={`text-2xl font-black ${isDark ? 'text-white' : 'text-gray-900'}`}>
                        {(selectedProjeto.atletas_site || 0).toLocaleString('pt-BR')}
                      </p>
                      <span className={`text-xs font-bold uppercase tracking-wider ${isDark ? 'text-cyan-400' : 'text-cyan-600'}`}>
                        Site
                      </span>
                    </div>
                  </div>

                  {/* Grupo */}
                  <div className={`relative overflow-hidden p-4 rounded-2xl ${isDark ? 'bg-gradient-to-br from-orange-500/20 to-amber-500/20 border border-orange-500/30' : 'bg-gradient-to-br from-orange-50 to-amber-50 border border-orange-200'}`}>
                    <div className="absolute top-0 right-0 w-16 h-16 bg-orange-500/20 rounded-full blur-2xl" />
                    <div className="relative text-center">
                      <Award className="w-6 h-6 text-orange-500 mx-auto mb-2" />
                      <p className={`text-2xl font-black ${isDark ? 'text-white' : 'text-gray-900'}`}>
                        {(selectedProjeto.atletas_grupo || 0).toLocaleString('pt-BR')}
                      </p>
                      <span className={`text-xs font-bold uppercase tracking-wider ${isDark ? 'text-orange-400' : 'text-orange-600'}`}>
                        Grupo
                      </span>
                    </div>
                  </div>
                </div>

                {/* Insight Card */}
                {(() => {
                  const insight = getAtletasInsight(
                    selectedProjeto.qtd_atletas_orcado || 0,
                    selectedProjeto.atletas_total || 0
                  );

                  const bgColor = insight.type === 'positive' 
                    ? isDark ? 'from-emerald-500/20 to-green-500/20 border-emerald-500/30' : 'from-emerald-50 to-green-50 border-emerald-200'
                    : insight.type === 'negative'
                    ? isDark ? 'from-red-500/20 to-rose-500/20 border-red-500/30' : 'from-red-50 to-rose-50 border-red-200'
                    : isDark ? 'from-gray-500/20 to-slate-500/20 border-gray-500/30' : 'from-gray-50 to-slate-50 border-gray-200';

                  const textColor = insight.type === 'positive'
                    ? 'text-emerald-500'
                    : insight.type === 'negative'
                    ? 'text-red-500'
                    : isDark ? 'text-gray-400' : 'text-gray-500';

                  return (
                    <div className={`p-4 rounded-2xl bg-gradient-to-r ${bgColor} border flex items-center gap-4`}>
                      <div className={`p-3 rounded-xl ${insight.type === 'positive' ? 'bg-emerald-500/20' : insight.type === 'negative' ? 'bg-red-500/20' : 'bg-gray-500/20'}`}>
                        <div className={textColor}>
                          {insight.icon}
                        </div>
                      </div>
                      <div className="flex-1">
                        <p className={`text-sm font-bold uppercase tracking-wider ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                          Insight de Performance
                        </p>
                        <p className={`text-lg font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>
                          {insight.message}
                        </p>
                      </div>
                      {insight.type !== 'neutral' && (
                        <div className={`text-3xl font-black ${textColor}`}>
                          {insight.percentage.toFixed(0)}%
                        </div>
                      )}
                    </div>
                  );
                })()}
              </div>

              {/* Dados em Tempo Real - Banco Externo */}
              {selectedProjeto?.codigo && (
                <div className={`p-6 rounded-3xl ${isDark ? 'bg-gradient-to-br from-emerald-900/20 to-teal-900/20' : 'bg-gradient-to-br from-emerald-50 to-teal-50'} border ${isDark ? 'border-emerald-700/50' : 'border-emerald-200'}`}>
                  <div className="flex items-center justify-between mb-6">
                    <div className="flex items-center gap-3">
                      <div className="p-2 rounded-xl bg-gradient-to-br from-emerald-500 to-teal-500">
                        <Database className="w-5 h-5 text-white" />
                      </div>
                      <div>
                        <h3 className={`text-xl font-black ${isDark ? 'text-white' : 'text-gray-900'}`}>
                          Dados em Tempo Real
                        </h3>
                        <p className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>
                          Inscrições do banco de vendas (atualizado a cada 5 min)
                        </p>
                      </div>
                    </div>
                    <button
                      onClick={handleRefreshExternos}
                      disabled={loadingExternos}
                      className={`flex items-center gap-2 px-3 py-2 rounded-xl ${isDark ? 'bg-emerald-500/20 hover:bg-emerald-500/30 text-emerald-400' : 'bg-emerald-100 hover:bg-emerald-200 text-emerald-700'} transition-all ${loadingExternos ? 'opacity-50 cursor-not-allowed' : ''}`}
                    >
                      <RefreshCw className={`w-4 h-4 ${loadingExternos ? 'animate-spin' : ''}`} />
                      <span className="text-sm font-medium">Atualizar</span>
                    </button>
                  </div>

                  {loadingExternos && !dadosExternos && (
                    <div className="flex items-center justify-center py-8">
                      <LoaderPinwheel className="w-8 h-8 text-emerald-500 animate-spin" />
                      <span className={`ml-3 ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>Carregando dados do banco externo...</span>
                    </div>
                  )}

                  {erroExternos && !dadosExternos && (
                    <div className={`p-4 rounded-xl ${isDark ? 'bg-red-500/20 border border-red-500/30' : 'bg-red-50 border border-red-200'}`}>
                      <p className={`text-sm ${isDark ? 'text-red-400' : 'text-red-600'}`}>{erroExternos}</p>
                    </div>
                  )}

                  {dadosExternos && (
                    <>
                      {/* Totais */}
                      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
                        <div className={`relative overflow-hidden p-4 rounded-2xl ${isDark ? 'bg-gradient-to-br from-emerald-500/20 to-teal-500/20 border border-emerald-500/30' : 'bg-gradient-to-br from-emerald-50 to-teal-50 border border-emerald-200'}`}>
                          <div className="absolute top-0 right-0 w-16 h-16 bg-emerald-500/20 rounded-full blur-2xl" />
                          <div className="relative text-center">
                            <Users className="w-6 h-6 text-emerald-500 mx-auto mb-2" />
                            <p className={`text-2xl font-black ${isDark ? 'text-white' : 'text-gray-900'}`}>
                              {(dadosExternos.qtd_total || 0).toLocaleString('pt-BR')}
                            </p>
                            <span className={`text-xs font-bold uppercase tracking-wider ${isDark ? 'text-emerald-400' : 'text-emerald-600'}`}>
                              Inscritos (Tempo Real)
                            </span>
                          </div>
                        </div>

                        <div className={`relative overflow-hidden p-4 rounded-2xl ${isDark ? 'bg-gradient-to-br from-green-500/20 to-lime-500/20 border border-green-500/30' : 'bg-gradient-to-br from-green-50 to-lime-50 border border-green-200'}`}>
                          <div className="absolute top-0 right-0 w-16 h-16 bg-green-500/20 rounded-full blur-2xl" />
                          <div className="relative text-center">
                            <DollarSign className="w-6 h-6 text-green-500 mx-auto mb-2" />
                            <p className={`text-2xl font-black ${isDark ? 'text-white' : 'text-gray-900'}`}>
                              {(dadosExternos.receita_total || 0).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL', maximumFractionDigits: 0 })}
                            </p>
                            <span className={`text-xs font-bold uppercase tracking-wider ${isDark ? 'text-green-400' : 'text-green-600'}`}>
                              Receita Total
                            </span>
                          </div>
                        </div>

                        {/* Por Local */}
                        {dadosExternos.por_local?.slice(0, 2).map((local, idx) => (
                          <div key={idx} className={`relative overflow-hidden p-4 rounded-2xl ${isDark ? 'bg-gradient-to-br from-cyan-500/20 to-blue-500/20 border border-cyan-500/30' : 'bg-gradient-to-br from-cyan-50 to-blue-50 border border-cyan-200'}`}>
                            <div className="absolute top-0 right-0 w-16 h-16 bg-cyan-500/20 rounded-full blur-2xl" />
                            <div className="relative text-center">
                              {local.local === 'Site' ? <Globe className="w-6 h-6 text-cyan-500 mx-auto mb-2" /> : 
                               local.local === 'Balcão' ? <Store className="w-6 h-6 text-cyan-500 mx-auto mb-2" /> :
                               <Truck className="w-6 h-6 text-cyan-500 mx-auto mb-2" />}
                              <p className={`text-2xl font-black ${isDark ? 'text-white' : 'text-gray-900'}`}>
                                {(local.qtd || 0).toLocaleString('pt-BR')}
                              </p>
                              <span className={`text-xs font-bold uppercase tracking-wider ${isDark ? 'text-cyan-400' : 'text-cyan-600'}`}>
                                {local.local}
                              </span>
                            </div>
                          </div>
                        ))}
                      </div>

                      {/* Top Categorias */}
                      {dadosExternos.por_categoria && dadosExternos.por_categoria.length > 0 && (
                        <div className={`p-4 rounded-2xl ${isDark ? 'bg-gray-800/50' : 'bg-white/50'} border ${isDark ? 'border-gray-700' : 'border-gray-200'}`}>
                          <p className={`text-sm font-bold uppercase tracking-wider mb-3 ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                            Top Categorias
                          </p>
                          <div className="space-y-2">
                            {dadosExternos.por_categoria.slice(0, 5).map((cat, idx) => (
                              <div key={idx} className="flex items-center justify-between">
                                <span className={`text-sm ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
                                  {cat.categoria}
                                </span>
                                <div className="flex items-center gap-4">
                                  <span className={`text-sm font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>
                                    {cat.qtd.toLocaleString('pt-BR')} atletas
                                  </span>
                                  <span className={`text-sm ${isDark ? 'text-emerald-400' : 'text-emerald-600'}`}>
                                    {cat.receita.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL', maximumFractionDigits: 0 })}
                                  </span>
                                </div>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </>
                  )}

                  {!dadosExternos && !loadingExternos && !erroExternos && (
                    <div className={`p-4 rounded-xl ${isDark ? 'bg-gray-800/50' : 'bg-gray-50'}`}>
                      <p className={`text-sm text-center ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>
                        Nenhum dado encontrado para o SKU: {selectedProjeto?.codigo}
                      </p>
                    </div>
                  )}
                </div>
              )}

              {/* Action Buttons */}
              <div className="flex justify-end gap-3 pt-4">
                <button 
                  onClick={() => {
                    setShowDetailsModal(false);
                    setSelectedProjeto(null);
                  }}
                  className={`px-6 py-3 rounded-xl font-semibold ${isDark ? 'bg-gray-800 hover:bg-gray-700 text-gray-300 border border-gray-700' : 'bg-gray-100 hover:bg-gray-200 text-gray-700 border border-gray-300'} transition-all`}
                >
                  Fechar
                </button>
                <button 
                  onClick={() => {
                    setShowDetailsModal(false);
                    handleEdit(selectedProjeto);
                  }}
                  className="px-6 py-3 bg-gradient-to-r from-purple-600 via-pink-600 to-orange-500 text-white rounded-xl font-semibold shadow-lg shadow-purple-500/30 hover:shadow-purple-500/50 transition-all hover:scale-105 flex items-center gap-2"
                >
                  <Pencil className="w-5 h-5" />
                  Editar Evento
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Edit Modal */}
      {showModal && (
        <div 
          className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 overflow-y-auto p-4"
          onClick={(e) => {
            if (e.target === e.currentTarget) {
              setShowModal(false);
              setEditItem(null);
            }
          }}
        >
          <div 
            className={`${isDark ? 'bg-gray-900' : 'bg-white'} rounded-3xl p-8 w-full max-w-3xl my-8 shadow-2xl border ${isDark ? 'border-gray-700' : 'border-gray-200'}`}
            onClick={(e) => e.stopPropagation()}
            style={{ animation: 'slideUp 0.3s ease-out' }}
          >
            <div className="flex justify-between items-center mb-6">
              <div className="flex items-center gap-3">
                <div className="p-2 rounded-xl bg-gradient-to-br from-purple-500 to-pink-500">
                  <Trophy className="w-5 h-5 text-white" />
                </div>
                <div>
                  <h2 className={`text-2xl font-black ${isDark ? 'text-white' : 'text-gray-900'}`}>
                    {editItem ? 'Editar' : 'Novo'} Evento
                  </h2>
                  <p className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>
                    Preencha as informações do evento
                  </p>
                </div>
              </div>
              <button 
                type="button"
                onClick={() => {
                  setShowModal(false);
                  setEditItem(null);
                }}
                className={`p-2 rounded-xl ${isDark ? 'hover:bg-gray-800 text-gray-400' : 'hover:bg-gray-100 text-gray-600'} transition-colors`}
              >
                <X className="w-6 h-6" />
              </button>
            </div>

            <form onSubmit={handleSubmit} className="space-y-6">
              {/* Image KV Field */}
              <div className={`p-4 rounded-2xl ${isDark ? 'bg-gray-800' : 'bg-gray-50'} border ${isDark ? 'border-gray-700' : 'border-gray-200'}`}>
                <label className={`flex items-center gap-2 text-sm font-bold mb-3 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
                  <ImageIcon className="w-4 h-4 text-pink-500" />
                  URL da Imagem KV (Key Visual)
                </label>
                <input 
                  type="url" 
                  value={form.imagem_kv} 
                  onChange={(e) => setForm({ ...form, imagem_kv: e.target.value })} 
                  placeholder="https://exemplo.com/imagem-do-evento.jpg"
                  className={`w-full px-4 py-3 rounded-xl border ${isDark ? 'bg-gray-700 border-gray-600 text-white placeholder-gray-500' : 'bg-white border-gray-300 placeholder-gray-400'} focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all`}
                />
                {form.imagem_kv && (
                  <div className="mt-3">
                    <img 
                      src={form.imagem_kv} 
                      alt="Preview" 
                      className="w-full h-32 object-cover rounded-lg"
                      onError={(e) => {
                        (e.target as HTMLImageElement).style.display = 'none';
                      }}
                    />
                  </div>
                )}
              </div>

              {/* Basic Info */}
              <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                <div>
                  <label className={`block text-sm font-bold mb-2 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>Código</label>
                  <input 
                    type="text" 
                    value={form.codigo} 
                    onChange={(e) => setForm({ ...form, codigo: e.target.value })} 
                    className={`w-full px-4 py-3 rounded-xl border ${isDark ? 'bg-gray-800 border-gray-700 text-white' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all`}
                    required 
                  />
                </div>
                <div>
                  <label className={`block text-sm font-bold mb-2 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>Produto</label>
                  <input 
                    type="text" 
                    value={form.produto} 
                    onChange={(e) => setForm({ ...form, produto: e.target.value })} 
                    className={`w-full px-4 py-3 rounded-xl border ${isDark ? 'bg-gray-800 border-gray-700 text-white' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all`}
                    required 
                  />
                </div>
                <div>
                  <label className={`block text-sm font-bold mb-2 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>Cliente</label>
                  <input 
                    type="text" 
                    value={form.cliente} 
                    onChange={(e) => setForm({ ...form, cliente: e.target.value })} 
                    className={`w-full px-4 py-3 rounded-xl border ${isDark ? 'bg-gray-800 border-gray-700 text-white' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all`}
                  />
                </div>
              </div>

              <div>
                <label className={`block text-sm font-bold mb-2 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>Nome do Evento</label>
                <input 
                  type="text" 
                  value={form.evento} 
                  onChange={(e) => setForm({ ...form, evento: e.target.value })} 
                  className={`w-full px-4 py-3 rounded-xl border ${isDark ? 'bg-gray-800 border-gray-700 text-white' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all`}
                  required 
                />
              </div>

              {/* Selects Grid */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div>
                  <label className={`block text-sm font-bold mb-2 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>Modalidade</label>
                  <select 
                    value={form.modalidade} 
                    onChange={(e) => setForm({ ...form, modalidade: e.target.value })} 
                    className={`w-full px-4 py-3 rounded-xl border ${isDark ? 'bg-gray-800 border-gray-700 text-white' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all`}
                  >
                    {modalidades.map(m => <option key={m} value={m}>{m}</option>)}
                  </select>
                </div>
                <div>
                  <label className={`block text-sm font-bold mb-2 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>Tipo Evento</label>
                  <select 
                    value={form.tipo_evento} 
                    onChange={(e) => setForm({ ...form, tipo_evento: e.target.value })} 
                    className={`w-full px-4 py-3 rounded-xl border ${isDark ? 'bg-gray-800 border-gray-700 text-white' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all`}
                  >
                    {tiposEvento.map(t => <option key={t} value={t}>{t}</option>)}
                  </select>
                </div>
                <div>
                  <label className={`block text-sm font-bold mb-2 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>Lei</label>
                  <select 
                    value={form.lei} 
                    onChange={(e) => setForm({ ...form, lei: e.target.value })} 
                    className={`w-full px-4 py-3 rounded-xl border ${isDark ? 'bg-gray-800 border-gray-700 text-white' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all`}
                  >
                    {leis.map(l => <option key={l} value={l}>{l}</option>)}
                  </select>
                </div>
                <div>
                  <label className={`block text-sm font-bold mb-2 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>Status</label>
                  <select 
                    value={form.status} 
                    onChange={(e) => setForm({ ...form, status: e.target.value })} 
                    className={`w-full px-4 py-3 rounded-xl border ${isDark ? 'bg-gray-800 border-gray-700 text-white' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all`}
                  >
                    {statusList.map(s => <option key={s} value={s}>{s}</option>)}
                  </select>
                </div>
              </div>

              {/* Location */}
              <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                <div className="md:col-span-2">
                  <label className={`block text-sm font-bold mb-2 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>Local do Evento</label>
                  <input 
                    type="text" 
                    value={form.local_evento} 
                    onChange={(e) => setForm({ ...form, local_evento: e.target.value })} 
                    className={`w-full px-4 py-3 rounded-xl border ${isDark ? 'bg-gray-800 border-gray-700 text-white' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all`}
                    required 
                  />
                </div>
                <div>
                  <label className={`block text-sm font-bold mb-2 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>Cidade</label>
                  <input 
                    type="text" 
                    value={form.cidade} 
                    onChange={(e) => setForm({ ...form, cidade: e.target.value })} 
                    className={`w-full px-4 py-3 rounded-xl border ${isDark ? 'bg-gray-800 border-gray-700 text-white' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all`}
                  />
                </div>
                <div>
                  <label className={`block text-sm font-bold mb-2 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>Estado</label>
                  <input 
                    type="text" 
                    value={form.estado} 
                    onChange={(e) => setForm({ ...form, estado: e.target.value })} 
                    className={`w-full px-4 py-3 rounded-xl border ${isDark ? 'bg-gray-800 border-gray-700 text-white' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all`}
                  />
                </div>
              </div>

              {/* Date and capacity */}
              <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                <div>
                  <label className={`block text-sm font-bold mb-2 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>Data do Evento</label>
                  <input 
                    type="date" 
                    value={form.data_evento} 
                    onChange={(e) => setForm({ ...form, data_evento: e.target.value })} 
                    className={`w-full px-4 py-3 rounded-xl border ${isDark ? 'bg-gray-800 border-gray-700 text-white' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all`}
                    required 
                  />
                </div>
                <div>
                  <label className={`block text-sm font-bold mb-2 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>Capacidade Máxima</label>
                  <input 
                    type="number" 
                    value={form.capacidade_maxima} 
                    onChange={(e) => setForm({ ...form, capacidade_maxima: e.target.value })} 
                    className={`w-full px-4 py-3 rounded-xl border ${isDark ? 'bg-gray-800 border-gray-700 text-white' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all`}
                  />
                </div>
                <div>
                  <label className={`block text-sm font-bold mb-2 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>Etapa</label>
                  <input 
                    type="number" 
                    value={form.etapa} 
                    onChange={(e) => setForm({ ...form, etapa: e.target.value })} 
                    className={`w-full px-4 py-3 rounded-xl border ${isDark ? 'bg-gray-800 border-gray-700 text-white' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all`}
                  />
                </div>
              </div>

              {/* Actions */}
              <div className={`flex justify-end gap-3 pt-4 border-t ${isDark ? 'border-gray-700' : 'border-gray-200'}`}>
                <button 
                  type="button" 
                  onClick={() => {
                    setShowModal(false);
                    setEditItem(null);
                  }} 
                  className={`px-6 py-3 rounded-xl font-semibold ${isDark ? 'bg-gray-800 hover:bg-gray-700 text-gray-300 border border-gray-700' : 'bg-gray-100 hover:bg-gray-200 text-gray-700 border border-gray-300'} transition-all`}
                >
                  Cancelar
                </button>
                <button 
                  type="submit" 
                  className="px-6 py-3 bg-gradient-to-r from-purple-600 via-pink-600 to-orange-500 text-white rounded-xl font-semibold shadow-lg shadow-purple-500/30 hover:shadow-purple-500/50 transition-all hover:scale-105 flex items-center gap-2"
                >
                  <Check className="w-5 h-5" />
                  Salvar Evento
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* CSS Animations */}
      <style>{`
        @keyframes slideUp {
          from {
            opacity: 0;
            transform: translateY(20px);
          }
          to {
            opacity: 1;
            transform: translateY(0);
          }
        }
      `}</style>
    </div>
  );
};

export default Projetos;
