import React, { useEffect, useState, useMemo } from 'react';
import { dashboardService } from '../../services/api';
import { useTheme } from '../../context/ThemeContext';
import { 
  Filter,
  Search,
  ChevronDown,
  LayoutDashboard,
  Sparkles,
  RotateCcw
} from 'lucide-react';

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
      <label className={`block text-sm font-bold mb-2 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
        {label}
      </label>
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className={`w-full px-4 py-3 text-left rounded-xl border flex items-center justify-between ${
          isDark 
            ? 'bg-gray-800 border-gray-700 text-white hover:bg-gray-700' 
            : 'bg-gray-50 border-gray-200 text-gray-900 hover:bg-gray-100'
        } transition-all`}
      >
        <span className={value ? '' : 'text-gray-400'}>{selectedLabel}</span>
        <ChevronDown className="w-4 h-4" />
      </button>
      
      {isOpen && (
        <div className={`absolute z-50 w-full mt-2 rounded-xl shadow-xl border ${
          isDark ? 'bg-gray-800 border-gray-700' : 'bg-white border-gray-200'
        }`}>
          <div className="p-3">
            <div className="relative">
              <Search className={`absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 ${isDark ? 'text-gray-400' : 'text-gray-500'}`} />
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Buscar..."
                className={`w-full pl-10 pr-4 py-2 rounded-lg border ${
                  isDark 
                    ? 'bg-gray-700 border-gray-600 text-white placeholder-gray-400' 
                    : 'bg-gray-50 border-gray-300 text-gray-900 placeholder-gray-500'
                } focus:ring-2 focus:ring-indigo-500 focus:border-transparent`}
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
              className={`w-full px-4 py-2 text-left ${
                isDark ? 'hover:bg-gray-700 text-gray-300' : 'hover:bg-gray-100 text-gray-500'
              } transition-colors`}
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
                className={`w-full px-4 py-2 text-left ${
                  value === option.value 
                    ? 'bg-indigo-500 text-white' 
                    : isDark 
                      ? 'hover:bg-gray-700 text-gray-200' 
                      : 'hover:bg-gray-100 text-gray-900'
                } transition-colors`}
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
    ano: null,
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
        const firstAno = data.anos.length > 0 ? data.anos[0].value : 2025;
        setDefaultAno(firstAno);
        setFilters(prev => ({ ...prev, ano: firstAno }));
      } catch (error) {
        console.error('Erro ao carregar filtros:', error);
        setFilters(prev => ({ ...prev, ano: 2025 }));
      } finally {
        setLoading(false);
      }
    };
    loadFilterOptions();
  }, []);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="w-8 h-8 border-4 border-indigo-500 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      <div className="fixed inset-0 pointer-events-none overflow-hidden">
        <div className="absolute top-0 left-1/4 w-96 h-96 bg-indigo-500/10 rounded-full blur-3xl animate-pulse" />
        <div className="absolute bottom-0 right-1/4 w-96 h-96 bg-purple-500/10 rounded-full blur-3xl animate-pulse" style={{ animationDelay: '1s' }} />
        <div className="absolute top-1/2 left-1/2 w-64 h-64 bg-pink-500/5 rounded-full blur-3xl animate-pulse" style={{ animationDelay: '2s' }} />
      </div>

      <div className="relative z-10 space-y-8 p-6">
        <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
          <div>
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-xl bg-gradient-to-br from-indigo-500 to-purple-500 shadow-lg shadow-indigo-500/30">
                <LayoutDashboard className="w-6 h-6 text-white" />
              </div>
              <div>
                <h1 className={`text-3xl font-black tracking-tight ${isDark ? 'text-white' : 'text-gray-900'}`}>
                  Dashboard
                  <span className="bg-gradient-to-r from-indigo-400 via-purple-500 to-pink-500 bg-clip-text text-transparent"> Consolidado</span>
                </h1>
                <p className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>
                  Visão geral do sistema
                </p>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={() => setShowFilters(!showFilters)}
              className={`flex items-center gap-2 px-4 py-3 rounded-xl border transition-all ${
                showFilters || activeFiltersCount > 0
                  ? 'bg-indigo-500/20 border-indigo-500/50 text-indigo-400'
                  : isDark 
                    ? 'bg-gray-800/50 border-gray-700 text-gray-300 hover:bg-gray-700' 
                    : 'bg-white/70 border-gray-200 text-gray-700 hover:bg-gray-50'
              }`}
            >
              <Filter className="w-5 h-5" />
              <span className="font-medium">Filtros</span>
              {activeFiltersCount > 0 && (
                <span className="px-2 py-0.5 text-xs font-bold bg-indigo-500 text-white rounded-full">
                  {activeFiltersCount}
                </span>
              )}
              <ChevronDown className={`w-4 h-4 transition-transform ${showFilters ? 'rotate-180' : ''}`} />
            </button>
            
            {activeFiltersCount > 0 && (
              <button
                onClick={clearAllFilters}
                className={`flex items-center gap-2 px-4 py-3 rounded-xl border ${isDark ? 'border-gray-700 text-gray-300 hover:bg-gray-700' : 'border-gray-200 text-gray-700 hover:bg-gray-50'} transition-all`}
              >
                <RotateCcw className="w-4 h-4" />
                <span className="font-medium">Limpar</span>
              </button>
            )}
          </div>
        </div>

        {showFilters && (
          <div className={`p-6 rounded-2xl ${isDark ? 'bg-gray-800/50 backdrop-blur-xl border border-gray-700/50' : 'bg-white/70 backdrop-blur-xl border border-gray-200'}`}>
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

        <div className={`rounded-2xl ${isDark ? 'bg-gray-800/50 backdrop-blur-xl border border-gray-700/50' : 'bg-white/70 backdrop-blur-xl border border-gray-200'} p-12`}>
          <div className="flex flex-col items-center justify-center text-center">
            <div className="p-4 rounded-2xl bg-gradient-to-br from-indigo-500/20 to-purple-500/20 mb-6">
              <Sparkles className="w-12 h-12 text-indigo-400" />
            </div>
            <h2 className={`text-2xl font-black mb-3 ${isDark ? 'text-white' : 'text-gray-900'}`}>
              Dashboard em construção
            </h2>
            <p className={`text-lg max-w-md ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>
              Estamos reestruturando o dashboard para oferecer uma experiência ainda melhor. Em breve, novas visualizações estarão disponíveis.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Dashboard;
