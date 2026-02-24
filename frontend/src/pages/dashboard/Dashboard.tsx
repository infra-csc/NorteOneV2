import React, { useEffect, useState, useMemo, useCallback } from 'react';
import { dashboardService } from '../../services/api';
import { useTheme } from '../../context/ThemeContext';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, Area, AreaChart
} from 'recharts';
import { 
  Filter,
  Search,
  ChevronDown,
  LayoutDashboard,
  RotateCcw,
  Users,
  CalendarDays,
  Ticket,
  TrendingUp,
  Trophy,
  AlertTriangle,
  MapPin,
  ArrowUpDown,
  RefreshCw,
  Target,
  Percent
} from 'lucide-react';

const formatCurrency = (value: number) => {
  return new Intl.NumberFormat('pt-BR', {
    style: 'currency',
    currency: 'BRL',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0
  }).format(value);
};

const formatNumber = (value: number) => {
  return new Intl.NumberFormat('pt-BR').format(value);
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
  label, options, value, onChange, placeholder = "Selecione...", isDark 
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const [search, setSearch] = useState('');

  const filteredOptions = useMemo(() => {
    if (!search) return options;
    return options.filter(opt => opt.label.toLowerCase().includes(search.toLowerCase()));
  }, [options, search]);

  const selectedLabel = options.find(opt => opt.value === value)?.label || placeholder;

  return (
    <div className="relative">
      <label className={`block text-xs font-bold mb-1.5 ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>{label}</label>
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className={`w-full px-3 py-2.5 text-sm text-left rounded-xl border flex items-center justify-between ${
          isDark ? 'bg-gray-800 border-gray-700 text-white hover:bg-gray-700' : 'bg-gray-50 border-gray-200 text-gray-900 hover:bg-gray-100'
        } transition-all`}
      >
        <span className={value ? '' : 'text-gray-400'}>{selectedLabel}</span>
        <ChevronDown className="w-4 h-4" />
      </button>
      {isOpen && (
        <div className={`absolute z-50 w-full mt-1 rounded-xl shadow-xl border ${isDark ? 'bg-gray-800 border-gray-700' : 'bg-white border-gray-200'}`}>
          <div className="p-2">
            <div className="relative">
              <Search className={`absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 ${isDark ? 'text-gray-400' : 'text-gray-500'}`} />
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Buscar..."
                className={`w-full pl-9 pr-3 py-2 text-sm rounded-lg border ${
                  isDark ? 'bg-gray-700 border-gray-600 text-white placeholder-gray-400' : 'bg-gray-50 border-gray-300 text-gray-900 placeholder-gray-500'
                } focus:ring-2 focus:ring-indigo-500 focus:border-transparent`}
              />
            </div>
          </div>
          <div className="max-h-48 overflow-y-auto">
            <button type="button" onClick={() => { onChange(null); setIsOpen(false); setSearch(''); }}
              className={`w-full px-4 py-2 text-sm text-left ${isDark ? 'hover:bg-gray-700 text-gray-300' : 'hover:bg-gray-100 text-gray-500'} transition-colors`}>
              -- Limpar --
            </button>
            {filteredOptions.map((option) => (
              <button key={option.value} type="button"
                onClick={() => { onChange(option.value); setIsOpen(false); setSearch(''); }}
                className={`w-full px-4 py-2 text-sm text-left ${
                  value === option.value ? 'bg-indigo-500 text-white' : isDark ? 'hover:bg-gray-700 text-gray-200' : 'hover:bg-gray-100 text-gray-900'
                } transition-colors`}>
                {option.label}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

const CHART_COLORS = ['#6366f1', '#8b5cf6', '#a78bfa', '#c4b5fd', '#818cf8', '#7c3aed', '#5b21b6', '#4f46e5', '#4338ca', '#3730a3'];
const PIE_COLORS = ['#6366f1', '#8b5cf6', '#ec4899', '#f59e0b', '#10b981', '#3b82f6', '#ef4444', '#14b8a6', '#f97316', '#06b6d4'];

interface KpiCardProps {
  title: string;
  value: string;
  subtitle?: string;
  icon: React.ReactNode;
  gradient: string;
  isDark: boolean;
}

const KpiCard: React.FC<KpiCardProps> = ({ title, value, subtitle, icon, gradient, isDark }) => (
  <div className={`relative overflow-hidden rounded-2xl p-5 ${isDark ? 'bg-gray-800/60 backdrop-blur-xl border border-gray-700/50' : 'bg-white/80 backdrop-blur-xl border border-gray-200/80'} transition-all hover:scale-[1.02] hover:shadow-lg`}>
    <div className={`absolute top-0 right-0 w-24 h-24 rounded-full blur-2xl opacity-20 ${gradient}`} />
    <div className="relative flex items-start justify-between">
      <div className="flex-1">
        <p className={`text-xs font-semibold uppercase tracking-wider ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>{title}</p>
        <p className={`text-2xl font-black mt-1.5 ${isDark ? 'text-white' : 'text-gray-900'}`}>{value}</p>
        {subtitle && <p className={`text-xs mt-1 ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>{subtitle}</p>}
      </div>
      <div className={`p-2.5 rounded-xl bg-gradient-to-br ${gradient} shadow-lg`}>
        {icon}
      </div>
    </div>
  </div>
);

const CustomTooltip = ({ active, payload, label, isDark }: any) => {
  if (!active || !payload || !payload.length) return null;
  return (
    <div className={`rounded-xl p-3 shadow-xl border ${isDark ? 'bg-gray-800 border-gray-700' : 'bg-white border-gray-200'}`}>
      <p className={`text-sm font-bold mb-1 ${isDark ? 'text-white' : 'text-gray-900'}`}>{label}</p>
      {payload.map((entry: any, index: number) => (
        <p key={index} className="text-xs" style={{ color: entry.color }}>
          {entry.name}: {typeof entry.value === 'number' ? formatNumber(entry.value) : entry.value}
        </p>
      ))}
    </div>
  );
};

const Dashboard: React.FC = () => {
  const { isDark } = useTheme();
  const [loading, setLoading] = useState(true);
  const [dataLoading, setDataLoading] = useState(false);
  const [showFilters, setShowFilters] = useState(false);
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  
  const [filterOptions, setFilterOptions] = useState<FilterOptions>({
    anos: [], meses: [], produtos: [], tipos_evento: [], projetos: [], modalidades: [], cidades: []
  });
  
  const [filters, setFilters] = useState<Filters>({
    ano: null, mes: null, produto: null, tipoEvento: null, projeto: null, modalidade: null, cidade: null
  });

  const [sortConfig, setSortConfig] = useState<{ key: string; direction: 'asc' | 'desc' }>({ key: 'data_evento', direction: 'asc' });
  const [tableSearch, setTableSearch] = useState('');
  const [defaultAno, setDefaultAno] = useState<number>(2025);

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

  const clearAllFilters = () => {
    setFilters({ ano: defaultAno, mes: null, produto: null, tipoEvento: null, projeto: null, modalidade: null, cidade: null });
  };

  const loadData = useCallback(async (currentFilters: Filters) => {
    setDataLoading(true);
    setError(null);
    try {
      const apiFilters = {
        ano: currentFilters.ano,
        mes: currentFilters.mes,
        produto: currentFilters.produto,
        tipo_evento: currentFilters.tipoEvento,
        projeto_id: currentFilters.projeto,
        modalidade: currentFilters.modalidade,
        cidade: currentFilters.cidade,
      };
      const result = await dashboardService.getConsolidado(apiFilters);
      setData(result);
    } catch (err: any) {
      console.error('Erro ao carregar dados:', err);
      setError('Erro ao carregar dados do dashboard');
    } finally {
      setDataLoading(false);
    }
  }, []);

  useEffect(() => {
    const loadFilterOptions = async () => {
      try {
        const data = await dashboardService.getFiltros();
        setFilterOptions(data);
        const firstAno = data.anos.length > 0 ? data.anos[0].value : 2025;
        setDefaultAno(firstAno as number);
        setFilters(prev => ({ ...prev, ano: firstAno as number }));
      } catch (error) {
        console.error('Erro ao carregar filtros:', error);
        setFilters(prev => ({ ...prev, ano: 2025 }));
      } finally {
        setLoading(false);
      }
    };
    loadFilterOptions();
  }, []);

  useEffect(() => {
    if (filters.ano) {
      loadData(filters);
    }
  }, [filters, loadData]);

  const handleSort = (key: string) => {
    setSortConfig(prev => ({
      key,
      direction: prev.key === key && prev.direction === 'asc' ? 'desc' : 'asc'
    }));
  };

  const sortedTableData = useMemo(() => {
    if (!data?.tabela_detalhada) return [];
    let filtered = data.tabela_detalhada;
    if (tableSearch) {
      const s = tableSearch.toLowerCase();
      filtered = filtered.filter((e: any) =>
        e.evento?.toLowerCase().includes(s) ||
        e.cidade?.toLowerCase().includes(s) ||
        e.modalidade?.toLowerCase().includes(s) ||
        e.produto?.toLowerCase().includes(s)
      );
    }
    return [...filtered].sort((a: any, b: any) => {
      const aVal = a[sortConfig.key];
      const bVal = b[sortConfig.key];
      if (aVal == null) return 1;
      if (bVal == null) return -1;
      const cmp = typeof aVal === 'string' ? aVal.localeCompare(bVal) : aVal - bVal;
      return sortConfig.direction === 'asc' ? cmp : -cmp;
    });
  }, [data?.tabela_detalhada, sortConfig, tableSearch]);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="w-8 h-8 border-4 border-indigo-500 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  const kpis = data?.kpis;
  const cardClass = (base: string) => `rounded-2xl p-6 ${isDark ? `bg-gray-800/60 backdrop-blur-xl border border-gray-700/50` : `bg-white/80 backdrop-blur-xl border border-gray-200/80`}`;

  const SortIcon = ({ column }: { column: string }) => (
    <ArrowUpDown className={`w-3.5 h-3.5 inline ml-1 ${sortConfig.key === column ? 'text-indigo-400' : isDark ? 'text-gray-600' : 'text-gray-300'}`} />
  );

  return (
    <div className="min-h-screen">
      <div className="fixed inset-0 pointer-events-none overflow-hidden">
        <div className="absolute top-0 left-1/4 w-96 h-96 bg-indigo-500/10 rounded-full blur-3xl animate-pulse" />
        <div className="absolute bottom-0 right-1/4 w-96 h-96 bg-purple-500/10 rounded-full blur-3xl animate-pulse" style={{ animationDelay: '1s' }} />
        <div className="absolute top-1/2 left-1/2 w-64 h-64 bg-pink-500/5 rounded-full blur-3xl animate-pulse" style={{ animationDelay: '2s' }} />
      </div>

      <div className="relative z-10 space-y-6 p-6">
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
                  Visão geral de eventos e atletas
                </p>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={() => loadData(filters)}
              disabled={dataLoading}
              className={`flex items-center gap-2 px-4 py-3 rounded-xl border transition-all ${
                isDark ? 'bg-gray-800/50 border-gray-700 text-gray-300 hover:bg-gray-700' : 'bg-white/70 border-gray-200 text-gray-700 hover:bg-gray-50'
              }`}
            >
              <RefreshCw className={`w-4 h-4 ${dataLoading ? 'animate-spin' : ''}`} />
              <span className="font-medium text-sm">Atualizar</span>
            </button>
            <button
              onClick={() => setShowFilters(!showFilters)}
              className={`flex items-center gap-2 px-4 py-3 rounded-xl border transition-all ${
                showFilters || activeFiltersCount > 0
                  ? 'bg-indigo-500/20 border-indigo-500/50 text-indigo-400'
                  : isDark ? 'bg-gray-800/50 border-gray-700 text-gray-300 hover:bg-gray-700' : 'bg-white/70 border-gray-200 text-gray-700 hover:bg-gray-50'
              }`}
            >
              <Filter className="w-5 h-5" />
              <span className="font-medium text-sm">Filtros</span>
              {activeFiltersCount > 0 && (
                <span className="px-2 py-0.5 text-xs font-bold bg-indigo-500 text-white rounded-full">{activeFiltersCount}</span>
              )}
              <ChevronDown className={`w-4 h-4 transition-transform ${showFilters ? 'rotate-180' : ''}`} />
            </button>
            {activeFiltersCount > 0 && (
              <button onClick={clearAllFilters}
                className={`flex items-center gap-2 px-4 py-3 rounded-xl border ${isDark ? 'border-gray-700 text-gray-300 hover:bg-gray-700' : 'border-gray-200 text-gray-700 hover:bg-gray-50'} transition-all`}>
                <RotateCcw className="w-4 h-4" />
                <span className="font-medium text-sm">Limpar</span>
              </button>
            )}
          </div>
        </div>

        {showFilters && (
          <div className={`p-5 rounded-2xl ${isDark ? 'bg-gray-800/50 backdrop-blur-xl border border-gray-700/50' : 'bg-white/70 backdrop-blur-xl border border-gray-200'}`}>
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-7 gap-3">
              <SearchableDropdown label="Ano" options={filterOptions.anos} value={filters.ano}
                onChange={(val) => setFilters(prev => ({ ...prev, ano: val as number }))} placeholder="Selecione o ano" isDark={isDark} />
              <SearchableDropdown label="Mês" options={filterOptions.meses} value={filters.mes}
                onChange={(val) => setFilters(prev => ({ ...prev, mes: val as number | null }))} placeholder="Todos" isDark={isDark} />
              <SearchableDropdown label="Produto" options={filterOptions.produtos} value={filters.produto}
                onChange={(val) => setFilters(prev => ({ ...prev, produto: val as string | null }))} placeholder="Todos" isDark={isDark} />
              <SearchableDropdown label="Tipo Evento" options={filterOptions.tipos_evento} value={filters.tipoEvento}
                onChange={(val) => setFilters(prev => ({ ...prev, tipoEvento: val as string | null }))} placeholder="Todos" isDark={isDark} />
              <SearchableDropdown label="Projeto" options={filterOptions.projetos} value={filters.projeto}
                onChange={(val) => setFilters(prev => ({ ...prev, projeto: val as number | null }))} placeholder="Todos" isDark={isDark} />
              <SearchableDropdown label="Modalidade" options={filterOptions.modalidades} value={filters.modalidade}
                onChange={(val) => setFilters(prev => ({ ...prev, modalidade: val as string | null }))} placeholder="Todas" isDark={isDark} />
              <SearchableDropdown label="Cidade" options={filterOptions.cidades} value={filters.cidade}
                onChange={(val) => setFilters(prev => ({ ...prev, cidade: val as string | null }))} placeholder="Todas" isDark={isDark} />
            </div>
          </div>
        )}

        {error && (
          <div className="p-4 rounded-xl bg-red-500/10 border border-red-500/30 text-red-400 text-sm">
            {error}
          </div>
        )}

        {dataLoading && !data && (
          <div className="flex items-center justify-center py-20">
            <div className="w-8 h-8 border-4 border-indigo-500 border-t-transparent rounded-full animate-spin" />
          </div>
        )}

        {data && (
          <div className={`space-y-6 ${dataLoading ? 'opacity-60 pointer-events-none' : ''}`}>
            <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
              <KpiCard title="Atletas Orçados" value={formatNumber(kpis?.total_atletas_orcado || 0)}
                subtitle={`${kpis?.total_eventos || 0} eventos`}
                icon={<Users className="w-5 h-5 text-white" />} gradient="from-indigo-500 to-blue-500" isDark={isDark} />
              <KpiCard title="Total Eventos" value={formatNumber(kpis?.total_eventos || 0)}
                subtitle={`${kpis?.eventos_planejados || 0} planejados`}
                icon={<CalendarDays className="w-5 h-5 text-white" />} gradient="from-purple-500 to-pink-500" isDark={isDark} />
              <KpiCard title="Ticket Médio" value={formatCurrency(kpis?.ticket_medio || 0)}
                subtitle="Média geral"
                icon={<Ticket className="w-5 h-5 text-white" />} gradient="from-emerald-500 to-teal-500" isDark={isDark} />
              <KpiCard title="Taxa Ocupação" value={`${kpis?.taxa_ocupacao_media || 0}%`}
                subtitle={`Cap. total: ${formatNumber(kpis?.total_capacidade || 0)}`}
                icon={<Percent className="w-5 h-5 text-white" />} gradient="from-amber-500 to-orange-500" isDark={isDark} />
              <KpiCard title="Modalidades" value={`${data.insights?.total_modalidades || 0}`}
                subtitle={`${data.insights?.total_cidades || 0} cidades`}
                icon={<Target className="w-5 h-5 text-white" />} gradient="from-rose-500 to-red-500" isDark={isDark} />
            </div>

            {data.insights?.evento_destaque && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className={`${cardClass('p-4')} flex items-start gap-4`}>
                  <div className="p-3 rounded-xl bg-gradient-to-br from-amber-500 to-yellow-500 shadow-lg">
                    <Trophy className="w-5 h-5 text-white" />
                  </div>
                  <div>
                    <p className={`text-xs font-semibold uppercase tracking-wider ${isDark ? 'text-amber-400' : 'text-amber-600'}`}>Evento Destaque</p>
                    <p className={`text-sm font-bold mt-1 ${isDark ? 'text-white' : 'text-gray-900'}`}>
                      {data.insights.evento_destaque.evento}
                    </p>
                    <p className={`text-xs mt-0.5 ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                      {formatNumber(data.insights.evento_destaque.atletas)} atletas · {data.insights.evento_destaque.cidade}
                    </p>
                  </div>
                </div>

                {data.insights.eventos_alerta?.length > 0 && (
                  <div className={`${cardClass('p-4')} flex items-start gap-4`}>
                    <div className="p-3 rounded-xl bg-gradient-to-br from-red-500 to-rose-500 shadow-lg">
                      <AlertTriangle className="w-5 h-5 text-white" />
                    </div>
                    <div>
                      <p className={`text-xs font-semibold uppercase tracking-wider ${isDark ? 'text-red-400' : 'text-red-600'}`}>
                        Alerta de Ocupação ({data.insights.eventos_alerta.length})
                      </p>
                      <div className="mt-1 space-y-0.5">
                        {data.insights.eventos_alerta.slice(0, 3).map((e: any, i: number) => (
                          <p key={i} className={`text-xs ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
                            <span className="font-medium">{e.evento}</span>
                            <span className="text-red-400 ml-1">({e.taxa_ocupacao}%)</span>
                          </p>
                        ))}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )}

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {data.evolucao_mensal?.length > 0 && (
                <div className={cardClass('evolucao')}>
                  <h3 className={`text-sm font-bold mb-4 ${isDark ? 'text-white' : 'text-gray-900'}`}>
                    <CalendarDays className="w-4 h-4 inline mr-2 text-indigo-400" />
                    Atletas Orçados por Mês
                  </h3>
                  <ResponsiveContainer width="100%" height={280}>
                    <AreaChart data={data.evolucao_mensal}>
                      <defs>
                        <linearGradient id="gradientOrcado" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="#6366f1" stopOpacity={0.3} />
                          <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid strokeDasharray="3 3" stroke={isDark ? '#374151' : '#e5e7eb'} />
                      <XAxis dataKey="mes" tick={{ fontSize: 12, fill: isDark ? '#9ca3af' : '#6b7280' }} />
                      <YAxis tick={{ fontSize: 12, fill: isDark ? '#9ca3af' : '#6b7280' }} />
                      <Tooltip content={<CustomTooltip isDark={isDark} />} />
                      <Area type="monotone" dataKey="orcado" name="Atletas Orçados" stroke="#6366f1" fill="url(#gradientOrcado)" strokeWidth={2.5} dot={{ r: 4, fill: '#6366f1' }} />
                      <Area type="monotone" dataKey="eventos" name="Qtd Eventos" stroke="#8b5cf6" fill="none" strokeWidth={1.5} strokeDasharray="5 5" dot={{ r: 3, fill: '#8b5cf6' }} />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              )}

              {data.atletas_por_modalidade?.length > 0 && (
                <div className={cardClass('modalidade')}>
                  <h3 className={`text-sm font-bold mb-4 ${isDark ? 'text-white' : 'text-gray-900'}`}>
                    <Target className="w-4 h-4 inline mr-2 text-purple-400" />
                    Eventos por Modalidade
                  </h3>
                  <ResponsiveContainer width="100%" height={280}>
                    <PieChart>
                      <Pie data={data.atletas_por_modalidade} dataKey="quantidade" nameKey="modalidade"
                        cx="50%" cy="50%" outerRadius={100} innerRadius={55} paddingAngle={3}
                        label={({ modalidade, percent }: any) => `${modalidade} ${(percent * 100).toFixed(0)}%`}
                        labelLine={{ stroke: isDark ? '#6b7280' : '#9ca3af' }}
                      >
                        {data.atletas_por_modalidade.map((_: any, index: number) => (
                          <Cell key={index} fill={PIE_COLORS[index % PIE_COLORS.length]} />
                        ))}
                      </Pie>
                      <Tooltip content={<CustomTooltip isDark={isDark} />} />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
              )}
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {data.top_eventos?.length > 0 && (
                <div className={cardClass('top')}>
                  <h3 className={`text-sm font-bold mb-4 ${isDark ? 'text-white' : 'text-gray-900'}`}>
                    <TrendingUp className="w-4 h-4 inline mr-2 text-emerald-400" />
                    Top 10 Eventos por Atletas
                  </h3>
                  <ResponsiveContainer width="100%" height={320}>
                    <BarChart data={data.top_eventos} layout="vertical" margin={{ left: 10, right: 20 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke={isDark ? '#374151' : '#e5e7eb'} />
                      <XAxis type="number" tick={{ fontSize: 11, fill: isDark ? '#9ca3af' : '#6b7280' }} />
                      <YAxis type="category" dataKey="evento" width={150}
                        tick={{ fontSize: 10, fill: isDark ? '#9ca3af' : '#6b7280' }} />
                      <Tooltip content={<CustomTooltip isDark={isDark} />} />
                      <Bar dataKey="atletas" name="Atletas" fill="#6366f1" radius={[0, 6, 6, 0]} barSize={18} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}

              {data.distribuicao_geografica?.length > 0 && (
                <div className={cardClass('geo')}>
                  <h3 className={`text-sm font-bold mb-4 ${isDark ? 'text-white' : 'text-gray-900'}`}>
                    <MapPin className="w-4 h-4 inline mr-2 text-rose-400" />
                    Eventos por Cidade
                  </h3>
                  <ResponsiveContainer width="100%" height={320}>
                    <BarChart data={data.distribuicao_geografica} layout="vertical" margin={{ left: 10, right: 20 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke={isDark ? '#374151' : '#e5e7eb'} />
                      <XAxis type="number" tick={{ fontSize: 11, fill: isDark ? '#9ca3af' : '#6b7280' }} />
                      <YAxis type="category" dataKey="cidade" width={120}
                        tick={{ fontSize: 10, fill: isDark ? '#9ca3af' : '#6b7280' }} />
                      <Tooltip content={<CustomTooltip isDark={isDark} />} />
                      <Bar dataKey="quantidade" name="Eventos" fill="#ec4899" radius={[0, 6, 6, 0]} barSize={18} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {data.taxa_ocupacao_eventos?.length > 0 && (
                <div className={cardClass('ocupacao')}>
                  <h3 className={`text-sm font-bold mb-4 ${isDark ? 'text-white' : 'text-gray-900'}`}>
                    <Percent className="w-4 h-4 inline mr-2 text-amber-400" />
                    Taxa de Ocupação por Evento
                  </h3>
                  <ResponsiveContainer width="100%" height={320}>
                    <BarChart data={data.taxa_ocupacao_eventos.slice(0, 10)} layout="vertical" margin={{ left: 10, right: 20 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke={isDark ? '#374151' : '#e5e7eb'} />
                      <XAxis type="number" domain={[0, 'auto']} tick={{ fontSize: 11, fill: isDark ? '#9ca3af' : '#6b7280' }}
                        tickFormatter={(v) => `${v}%`} />
                      <YAxis type="category" dataKey="evento" width={150}
                        tick={{ fontSize: 10, fill: isDark ? '#9ca3af' : '#6b7280' }} />
                      <Tooltip content={<CustomTooltip isDark={isDark} />} />
                      <Bar dataKey="taxa" name="Ocupação %" radius={[0, 6, 6, 0]} barSize={18}>
                        {data.taxa_ocupacao_eventos.slice(0, 10).map((entry: any, index: number) => (
                          <Cell key={index} fill={entry.taxa >= 80 ? '#10b981' : entry.taxa >= 50 ? '#f59e0b' : '#ef4444'} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}

              {data.ticket_medio_por_produto?.length > 0 && (
                <div className={cardClass('ticket')}>
                  <h3 className={`text-sm font-bold mb-4 ${isDark ? 'text-white' : 'text-gray-900'}`}>
                    <Ticket className="w-4 h-4 inline mr-2 text-teal-400" />
                    Ticket Médio por Produto
                  </h3>
                  <ResponsiveContainer width="100%" height={320}>
                    <BarChart data={data.ticket_medio_por_produto} margin={{ left: 10, right: 20 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke={isDark ? '#374151' : '#e5e7eb'} />
                      <XAxis dataKey="produto" tick={{ fontSize: 10, fill: isDark ? '#9ca3af' : '#6b7280' }} />
                      <YAxis tick={{ fontSize: 11, fill: isDark ? '#9ca3af' : '#6b7280' }}
                        tickFormatter={(v) => formatCurrency(v)} />
                      <Tooltip content={({ active, payload, label }: any) => {
                        if (!active || !payload?.length) return null;
                        return (
                          <div className={`rounded-xl p-3 shadow-xl border ${isDark ? 'bg-gray-800 border-gray-700' : 'bg-white border-gray-200'}`}>
                            <p className={`text-sm font-bold mb-1 ${isDark ? 'text-white' : 'text-gray-900'}`}>{label}</p>
                            <p className="text-xs text-teal-400">Ticket Médio: {formatCurrency(payload[0]?.value || 0)}</p>
                          </div>
                        );
                      }} />
                      <Bar dataKey="ticket_medio" name="Ticket Médio" fill="#14b8a6" radius={[6, 6, 0, 0]} barSize={40} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}
            </div>

            <div className={cardClass('tabela')}>
              <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-3 mb-4">
                <h3 className={`text-sm font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>
                  <LayoutDashboard className="w-4 h-4 inline mr-2 text-indigo-400" />
                  Detalhamento por Evento ({sortedTableData.length})
                </h3>
                <div className="relative w-full md:w-72">
                  <Search className={`absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 ${isDark ? 'text-gray-400' : 'text-gray-500'}`} />
                  <input
                    type="text"
                    value={tableSearch}
                    onChange={(e) => setTableSearch(e.target.value)}
                    placeholder="Buscar evento, cidade, modalidade..."
                    className={`w-full pl-10 pr-4 py-2.5 text-sm rounded-xl border ${
                      isDark ? 'bg-gray-700/50 border-gray-600 text-white placeholder-gray-400' : 'bg-gray-50 border-gray-200 text-gray-900 placeholder-gray-500'
                    } focus:ring-2 focus:ring-indigo-500 focus:border-transparent`}
                  />
                </div>
              </div>
              
              <div className="overflow-x-auto rounded-xl">
                <table className="w-full text-sm">
                  <thead>
                    <tr className={isDark ? 'bg-gray-700/50' : 'bg-gray-50'}>
                      {[
                        { key: 'evento', label: 'Evento' },
                        { key: 'data_evento', label: 'Data' },
                        { key: 'cidade', label: 'Cidade' },
                        { key: 'modalidade', label: 'Modalidade' },
                        { key: 'produto', label: 'Produto' },
                        { key: 'atletas_orcado', label: 'Atletas Orçados' },
                        { key: 'ticket_medio', label: 'Ticket Médio' },
                        { key: 'taxa_ocupacao', label: 'Ocupação' },
                        { key: 'status', label: 'Status' },
                      ].map(col => (
                        <th key={col.key}
                          onClick={() => handleSort(col.key)}
                          className={`px-3 py-3 text-left text-xs font-bold uppercase tracking-wider cursor-pointer select-none
                            ${isDark ? 'text-gray-300 hover:text-white' : 'text-gray-600 hover:text-gray-900'} transition-colors`}>
                          {col.label}<SortIcon column={col.key} />
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className={`divide-y ${isDark ? 'divide-gray-700/50' : 'divide-gray-100'}`}>
                    {sortedTableData.map((evento: any) => (
                      <tr key={evento.id} className={`${isDark ? 'hover:bg-gray-700/30' : 'hover:bg-gray-50/80'} transition-colors`}>
                        <td className={`px-3 py-3 font-medium max-w-[200px] truncate ${isDark ? 'text-white' : 'text-gray-900'}`}
                          title={evento.evento}>
                          {evento.evento}
                        </td>
                        <td className={`px-3 py-3 whitespace-nowrap ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
                          {evento.data_evento ? new Date(evento.data_evento + 'T00:00:00').toLocaleDateString('pt-BR') : '-'}
                        </td>
                        <td className={`px-3 py-3 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>{evento.cidade}</td>
                        <td className={`px-3 py-3 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>{evento.modalidade}</td>
                        <td className={`px-3 py-3 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>{evento.produto}</td>
                        <td className={`px-3 py-3 font-semibold ${isDark ? 'text-white' : 'text-gray-900'}`}>
                          {formatNumber(evento.atletas_orcado)}
                        </td>
                        <td className={`px-3 py-3 ${isDark ? 'text-emerald-400' : 'text-emerald-600'}`}>
                          {evento.ticket_medio > 0 ? formatCurrency(evento.ticket_medio) : '-'}
                        </td>
                        <td className="px-3 py-3">
                          <div className="flex items-center gap-2">
                            <div className="w-16 h-2 rounded-full bg-gray-200 dark:bg-gray-700 overflow-hidden">
                              <div className={`h-full rounded-full ${
                                evento.taxa_ocupacao >= 80 ? 'bg-emerald-500' : evento.taxa_ocupacao >= 50 ? 'bg-amber-500' : 'bg-red-500'
                              }`} style={{ width: `${Math.min(evento.taxa_ocupacao, 100)}%` }} />
                            </div>
                            <span className={`text-xs font-medium ${
                              evento.taxa_ocupacao >= 80 ? 'text-emerald-400' : evento.taxa_ocupacao >= 50 ? 'text-amber-400' : 'text-red-400'
                            }`}>
                              {evento.taxa_ocupacao}%
                            </span>
                          </div>
                        </td>
                        <td className="px-3 py-3">
                          <span className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium ${
                            evento.status?.toLowerCase().includes('conclu') || evento.status?.toLowerCase().includes('realizado')
                              ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                              : evento.status?.toLowerCase().includes('cancel')
                                ? 'bg-red-500/10 text-red-400 border border-red-500/20'
                                : 'bg-indigo-500/10 text-indigo-400 border border-indigo-500/20'
                          }`}>
                            {evento.status}
                          </span>
                        </td>
                      </tr>
                    ))}
                    {sortedTableData.length === 0 && (
                      <tr>
                        <td colSpan={9} className={`px-4 py-12 text-center ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>
                          Nenhum evento encontrado para os filtros selecionados
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default Dashboard;
