import React, { useEffect, useState, useMemo } from 'react';
import { dashboardService } from '../../services/api';
import { DashboardResumo, EvolucaoMensal, AtletasPorProjeto } from '../../types';
import { useTheme } from '../../context/ThemeContext';
import { useAuth } from '../../context/AuthContext';
import { 
  TrendingUp, 
  TrendingDown, 
  Users, 
  DollarSign,
  Target,
  BarChart3,
  PieChart as PieChartIcon,
  Activity,
  Filter,
  X,
  Search,
  ChevronDown
} from 'lucide-react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell
} from 'recharts';

const COLORS = ['#3B82F6', '#10B981', '#F59E0B', '#EF4444', '#8B5CF6', '#EC4899'];

const formatCurrency = (value: number) => {
  return new Intl.NumberFormat('pt-BR', {
    style: 'currency',
    currency: 'BRL',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0
  }).format(value);
};

interface FilterOption {
  value: string | number;
  label: string;
}

interface Filters {
  ano: number | null;
  mes: number | null;
  produto: string | null;
  tipoEvento: string | null;
  projeto: number | null;
  modalidade: string | null;
  cidade: string | null;
}

interface FilterOptions {
  anos: FilterOption[];
  meses: FilterOption[];
  produtos: FilterOption[];
  tipos_evento: FilterOption[];
  projetos: FilterOption[];
  modalidades: FilterOption[];
  cidades: FilterOption[];
}

interface SearchableDropdownProps {
  label: string;
  options: FilterOption[];
  value: string | number | null;
  onChange: (value: string | number | null) => void;
  placeholder?: string;
  isDark: boolean;
}

const SearchableDropdown: React.FC<SearchableDropdownProps> = ({ 
  label, 
  options, 
  value, 
  onChange, 
  placeholder = "Selecione...",
  isDark 
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const [search, setSearch] = useState('');

  const filteredOptions = useMemo(() => {
    if (!search) return options;
    return options.filter(opt => 
      opt.label.toLowerCase().includes(search.toLowerCase())
    );
  }, [options, search]);

  const selectedLabel = options.find(opt => opt.value === value)?.label || placeholder;

  return (
    <div className="relative">
      <label className={`block text-sm font-medium mb-1 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
        {label}
      </label>
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className={`w-full px-3 py-2 text-left rounded-lg border flex items-center justify-between ${
          isDark 
            ? 'bg-gray-700 border-gray-600 text-white hover:bg-gray-600' 
            : 'bg-white border-gray-300 text-gray-900 hover:bg-gray-50'
        }`}
      >
        <span className={value ? '' : 'text-gray-400'}>{selectedLabel}</span>
        <ChevronDown className="w-4 h-4" />
      </button>
      
      {isOpen && (
        <div className={`absolute z-50 w-full mt-1 rounded-lg shadow-lg border ${
          isDark ? 'bg-gray-800 border-gray-600' : 'bg-white border-gray-200'
        }`}>
          <div className="p-2">
            <div className="relative">
              <Search className={`absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 ${isDark ? 'text-gray-400' : 'text-gray-500'}`} />
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Buscar..."
                className={`w-full pl-9 pr-3 py-2 rounded border ${
                  isDark 
                    ? 'bg-gray-700 border-gray-600 text-white placeholder-gray-400' 
                    : 'bg-gray-50 border-gray-300 text-gray-900 placeholder-gray-500'
                }`}
              />
            </div>
          </div>
          <div className="max-h-48 overflow-y-auto">
            <button
              type="button"
              onClick={() => {
                onChange(null);
                setIsOpen(false);
                setSearch('');
              }}
              className={`w-full px-3 py-2 text-left ${
                isDark ? 'hover:bg-gray-700 text-gray-300' : 'hover:bg-gray-100 text-gray-500'
              }`}
            >
              -- Limpar --
            </button>
            {filteredOptions.map((option) => (
              <button
                key={option.value}
                type="button"
                onClick={() => {
                  onChange(option.value);
                  setIsOpen(false);
                  setSearch('');
                }}
                className={`w-full px-3 py-2 text-left ${
                  value === option.value 
                    ? 'bg-blue-500 text-white' 
                    : isDark 
                      ? 'hover:bg-gray-700 text-gray-200' 
                      : 'hover:bg-gray-100 text-gray-900'
                }`}
              >
                {option.label}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

const Dashboard: React.FC = () => {
  const { isDark } = useTheme();
  const { user } = useAuth();
  const isAdmin = user?.perfil === 'ADMIN';
  
  const [resumo, setResumo] = useState<DashboardResumo | null>(null);
  const [evolucao, setEvolucao] = useState<EvolucaoMensal[]>([]);
  const [atletasProjeto, setAtletasProjeto] = useState<AtletasPorProjeto[]>([]);
  const [atletasModalidade, setAtletasModalidade] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  
  const [showFilters, setShowFilters] = useState(false);
  const [filterOptions, setFilterOptions] = useState<FilterOptions>({
    anos: [],
    meses: [],
    produtos: [],
    tipos_evento: [],
    projetos: [],
    modalidades: [],
    cidades: []
  });
  
  const [filters, setFilters] = useState<Filters>({
    ano: 2025,
    mes: null,
    produto: null,
    tipoEvento: null,
    projeto: null,
    modalidade: null,
    cidade: null
  });

  const activeFiltersCount = useMemo(() => {
    let count = 0;
    if (filters.mes) count++;
    if (filters.produto) count++;
    if (filters.tipoEvento) count++;
    if (filters.projeto) count++;
    if (filters.modalidade) count++;
    if (filters.cidade) count++;
    return count;
  }, [filters]);

  const [defaultAno, setDefaultAno] = useState<number>(2025);

  const clearAllFilters = () => {
    setFilters({
      ano: defaultAno,
      mes: null,
      produto: null,
      tipoEvento: null,
      projeto: null,
      modalidade: null,
      cidade: null
    });
  };

  useEffect(() => {
    const loadFilterOptions = async () => {
      try {
        const data = await dashboardService.getFiltros();
        setFilterOptions(data);
        if (data.anos.length > 0) {
          const firstAno = data.anos[0].value;
          setDefaultAno(firstAno);
          setFilters(prev => ({ ...prev, ano: firstAno }));
        }
      } catch (error) {
        console.error('Erro ao carregar filtros:', error);
      }
    };
    loadFilterOptions();
  }, []);

  useEffect(() => {
    const loadData = async () => {
      if (!filters.ano) return;
      
      setLoading(true);
      try {
        const apiFilters = {
          ano: filters.ano,
          mes: filters.mes,
          produto: filters.produto,
          tipo_evento: filters.tipoEvento,
          projeto_id: filters.projeto,
          modalidade: filters.modalidade,
          cidade: filters.cidade
        };
        
        const [resumoData, evolucaoData, atletasProjetoData, atletasModalidadeData] = await Promise.all([
          dashboardService.getResumoGeral(apiFilters),
          dashboardService.getEvolucaoMensal(apiFilters),
          dashboardService.getAtletasPorProjeto(apiFilters),
          dashboardService.getAtletasPorModalidade(apiFilters)
        ]);
        setResumo(resumoData);
        setEvolucao(evolucaoData);
        setAtletasProjeto(atletasProjetoData);
        setAtletasModalidade(atletasModalidadeData);
      } catch (error) {
        console.error('Erro ao carregar dashboard:', error);
      } finally {
        setLoading(false);
      }
    };
    loadData();
  }, [filters]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="w-8 h-8 border-4 border-blue-500 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  const cardClass = `p-6 rounded-xl shadow-lg ${isDark ? 'bg-gray-800' : 'bg-white'}`;
  const textClass = isDark ? 'text-gray-200' : 'text-gray-600';
  const headingClass = isDark ? 'text-white' : 'text-gray-800';

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap justify-between items-center gap-4">
        <h1 className={`text-2xl font-bold ${headingClass}`}>Dashboard Consolidado</h1>
        <div className="flex items-center gap-3">
          <button
            onClick={() => setShowFilters(!showFilters)}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg border transition-colors ${
              isDark 
                ? 'bg-gray-700 border-gray-600 text-white hover:bg-gray-600' 
                : 'bg-white border-gray-300 hover:bg-gray-50'
            } ${activeFiltersCount > 0 ? 'ring-2 ring-blue-500' : ''}`}
          >
            <Filter className="w-4 h-4" />
            <span>Filtros</span>
            {activeFiltersCount > 0 && (
              <span className="bg-blue-500 text-white text-xs px-2 py-0.5 rounded-full">
                {activeFiltersCount}
              </span>
            )}
          </button>
          
          {activeFiltersCount > 0 && (
            <button
              onClick={clearAllFilters}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg border transition-colors ${
                isDark 
                  ? 'bg-red-900 border-red-700 text-red-200 hover:bg-red-800' 
                  : 'bg-red-50 border-red-200 text-red-600 hover:bg-red-100'
              }`}
            >
              <X className="w-4 h-4" />
              <span>Limpar Filtros</span>
            </button>
          )}
        </div>
      </div>

      {showFilters && (
        <div className={`p-6 rounded-xl shadow-lg ${isDark ? 'bg-gray-800' : 'bg-white'}`}>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 xl:grid-cols-7 gap-4">
            <SearchableDropdown
              label="Ano"
              options={filterOptions.anos}
              value={filters.ano}
              onChange={(val) => setFilters(prev => ({ ...prev, ano: val as number }))}
              placeholder="Selecione o ano"
              isDark={isDark}
            />
            <SearchableDropdown
              label="Mes"
              options={filterOptions.meses}
              value={filters.mes}
              onChange={(val) => setFilters(prev => ({ ...prev, mes: val as number | null }))}
              placeholder="Todos os meses"
              isDark={isDark}
            />
            <SearchableDropdown
              label="Produto"
              options={filterOptions.produtos}
              value={filters.produto}
              onChange={(val) => setFilters(prev => ({ ...prev, produto: val as string | null }))}
              placeholder="Todos os produtos"
              isDark={isDark}
            />
            <SearchableDropdown
              label="Tipo Evento"
              options={filterOptions.tipos_evento}
              value={filters.tipoEvento}
              onChange={(val) => setFilters(prev => ({ ...prev, tipoEvento: val as string | null }))}
              placeholder="Todos os tipos"
              isDark={isDark}
            />
            <SearchableDropdown
              label="Projeto"
              options={filterOptions.projetos}
              value={filters.projeto}
              onChange={(val) => setFilters(prev => ({ ...prev, projeto: val as number | null }))}
              placeholder="Todos os projetos"
              isDark={isDark}
            />
            <SearchableDropdown
              label="Modalidade"
              options={filterOptions.modalidades}
              value={filters.modalidade}
              onChange={(val) => setFilters(prev => ({ ...prev, modalidade: val as string | null }))}
              placeholder="Todas as modalidades"
              isDark={isDark}
            />
            <SearchableDropdown
              label="Cidade"
              options={filterOptions.cidades}
              value={filters.cidade}
              onChange={(val) => setFilters(prev => ({ ...prev, cidade: val as string | null }))}
              placeholder="Todas as cidades"
              isDark={isDark}
            />
          </div>
        </div>
      )}

      {isAdmin && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          <div className={cardClass}>
            <div className="flex items-center justify-between">
              <div>
                <p className={textClass}>Orcado (Ano)</p>
                <p className={`text-2xl font-bold ${headingClass}`}>{formatCurrency(resumo?.financeiro.orcado_resultado || 0)}</p>
              </div>
              <div className="p-3 bg-blue-100 rounded-full">
                <Target className="w-6 h-6 text-blue-600" />
              </div>
            </div>
          </div>

          <div className={cardClass}>
            <div className="flex items-center justify-between">
              <div>
                <p className={textClass}>Projetado (Ano)</p>
                <p className={`text-2xl font-bold ${headingClass}`}>{formatCurrency(resumo?.financeiro.projetado_resultado || 0)}</p>
              </div>
              <div className="p-3 bg-yellow-100 rounded-full">
                <TrendingUp className="w-6 h-6 text-yellow-600" />
              </div>
            </div>
          </div>

          <div className={cardClass}>
            <div className="flex items-center justify-between">
              <div>
                <p className={textClass}>Realizado (YTD)</p>
                <p className={`text-2xl font-bold ${headingClass}`}>{formatCurrency(resumo?.financeiro.realizado_resultado || 0)}</p>
              </div>
              <div className="p-3 bg-green-100 rounded-full">
                <DollarSign className="w-6 h-6 text-green-600" />
              </div>
            </div>
          </div>

          <div className={cardClass}>
            <div className="flex items-center justify-between">
              <div>
                <p className={textClass}>Variacao Orc x Real</p>
                <p className={`text-2xl font-bold ${(resumo?.financeiro.variacao_percentual || 0) >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                  {resumo?.financeiro.variacao_percentual || 0}%
                </p>
              </div>
              <div className={`p-3 rounded-full ${(resumo?.financeiro.variacao_percentual || 0) >= 0 ? 'bg-green-100' : 'bg-red-100'}`}>
                {(resumo?.financeiro.variacao_percentual || 0) >= 0 ? 
                  <TrendingUp className="w-6 h-6 text-green-600" /> : 
                  <TrendingDown className="w-6 h-6 text-red-600" />
                }
              </div>
            </div>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className={cardClass}>
          <div className="flex items-center justify-between">
            <div>
              <p className={textClass}>Atletas Orçados</p>
              <p className={`text-2xl font-bold ${headingClass}`}>{resumo?.atletas.total_orcado?.toLocaleString() || 0}</p>
            </div>
            <div className="p-3 bg-purple-100 rounded-full">
              <Users className="w-6 h-6 text-purple-600" />
            </div>
          </div>
        </div>

        <div className={cardClass}>
          <div className="flex items-center justify-between">
            <div>
              <p className={textClass}>Atletas Projetados</p>
              <p className={`text-2xl font-bold ${headingClass}`}>{resumo?.atletas.total_projetado?.toLocaleString() || 0}</p>
            </div>
            <div className="p-3 bg-indigo-100 rounded-full">
              <Users className="w-6 h-6 text-indigo-600" />
            </div>
          </div>
        </div>

        <div className={cardClass}>
          <div className="flex items-center justify-between">
            <div>
              <p className={textClass}>Atletas Realizados</p>
              <p className={`text-2xl font-bold ${headingClass}`}>{resumo?.atletas.total_realizado?.toLocaleString() || 0}</p>
            </div>
            <div className="p-3 bg-teal-100 rounded-full">
              <Users className="w-6 h-6 text-teal-600" />
            </div>
          </div>
        </div>
      </div>

      <div className={`grid grid-cols-1 ${isAdmin ? 'lg:grid-cols-2' : ''} gap-6`}>
        {isAdmin && (
          <div className={cardClass}>
            <h3 className={`text-lg font-semibold mb-4 ${headingClass}`}>
              <BarChart3 className="inline w-5 h-5 mr-2" />
              Evolucao Mensal - Orcado x Realizado
            </h3>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={evolucao}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="mes" />
                <YAxis tickFormatter={(value) => `${(value / 1000).toFixed(0)}k`} />
                <Tooltip formatter={(value: number) => formatCurrency(value)} />
                <Legend />
                <Bar dataKey="orcado" name="Orcado" fill="#3B82F6" />
                <Bar dataKey="realizado" name="Realizado" fill="#10B981" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}

        <div className={cardClass}>
          <h3 className={`text-lg font-semibold mb-4 ${headingClass}`}>
            <PieChartIcon className="inline w-5 h-5 mr-2" />
            Atletas por Modalidade
          </h3>
          <ResponsiveContainer width="100%" height={300}>
            <PieChart>
              <Pie
                data={atletasModalidade}
                dataKey="total"
                nameKey="modalidade"
                cx="50%"
                cy="50%"
                outerRadius={100}
                label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
              >
                {atletasModalidade.map((_, index) => (
                  <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                ))}
              </Pie>
              <Tooltip />
            </PieChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className={cardClass}>
        <h3 className={`text-lg font-semibold mb-4 ${headingClass}`}>
          <Activity className="inline w-5 h-5 mr-2" />
          Atletas por Evento
        </h3>
        <ResponsiveContainer width="100%" height={300}>
          <BarChart data={atletasProjeto} layout="vertical">
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis type="number" />
            <YAxis dataKey="evento" type="category" width={200} />
            <Tooltip />
            <Legend />
            <Bar dataKey="orcado" name="Orcado" fill="#3B82F6" />
            <Bar dataKey="projetado" name="Projetado" fill="#F59E0B" />
            <Bar dataKey="realizado" name="Realizado" fill="#10B981" />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};

export default Dashboard;
