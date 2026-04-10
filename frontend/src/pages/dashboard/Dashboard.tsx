import React, { useEffect, useState, useMemo, useCallback } from 'react';
import { dashboardService } from '../../services/api';
import { useTheme } from '../../context/ThemeContext';
import { usePermissions } from '../../context/PermissionContext';
import { useAuth } from '../../context/AuthContext';
import RelatorioFinanceiro from './RelatorioFinanceiro';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell
} from 'recharts';
import {
  Filter, Search, ChevronDown, LayoutDashboard, RotateCcw,
  Users, CalendarDays, TrendingUp, AlertTriangle,
  RefreshCw, Target, Percent, Zap, DollarSign, TrendingDown, ArrowRight
} from 'lucide-react';

const formatCurrency = (value: number) =>
  new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL', minimumFractionDigits: 0, maximumFractionDigits: 0 }).format(value);

const formatNumber = (value: number) =>
  new Intl.NumberFormat('pt-BR').format(value);

interface FilterOption { value: string | number; label: string; }

interface Filters {
  ano: number | null;
  mes: number | null;
  produto: string | null;
  modalidade: string | null;
  cidade: string | null;
}

interface FilterOptions {
  anos: FilterOption[];
  meses: FilterOption[];
  produtos: FilterOption[];
  modalidades: FilterOption[];
  cidades: FilterOption[];
}

const PIE_COLORS = ['#6366f1', '#8b5cf6', '#ec4899', '#f59e0b', '#10b981', '#3b82f6', '#ef4444', '#14b8a6'];

const ISC_BADGE: Record<string, { bg: string; text: string; label: string }> = {
  accelerating: { bg: 'bg-emerald-500/20', text: 'text-emerald-400', label: 'Acelerando' },
  stable: { bg: 'bg-amber-500/20', text: 'text-amber-400', label: 'Estável' },
  decelerating: { bg: 'bg-red-500/20', text: 'text-red-400', label: 'Desacelerando' },
};

const SearchableDropdown: React.FC<{
  label: string; options: FilterOption[]; value: string | number | null;
  onChange: (v: string | number | null) => void; placeholder?: string; isDark: boolean;
}> = ({ label, options, value, onChange, placeholder = 'Selecione...', isDark }) => {
  const [isOpen, setIsOpen] = useState(false);
  const [search, setSearch] = useState('');
  const filtered = useMemo(() => search ? options.filter(o => o.label.toLowerCase().includes(search.toLowerCase())) : options, [options, search]);
  const selectedLabel = options.find(o => o.value === value)?.label || placeholder;

  return (
    <div className="relative">
      <label className={`block text-xs font-bold mb-1.5 ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>{label}</label>
      <button type="button" onClick={() => setIsOpen(!isOpen)}
        className={`w-full px-3 py-2.5 text-sm text-left rounded-xl border flex items-center justify-between ${
          isDark ? 'bg-gray-800 border-gray-700 text-white hover:bg-gray-700' : 'bg-gray-50 border-gray-200 text-gray-900 hover:bg-gray-100'
        } transition-all`}>
        <span className={value ? '' : 'text-gray-400'}>{selectedLabel}</span>
        <ChevronDown className="w-4 h-4" />
      </button>
      {isOpen && (
        <div className={`absolute z-50 w-full mt-1 rounded-xl shadow-xl border ${isDark ? 'bg-gray-800 border-gray-700' : 'bg-white border-gray-200'}`}>
          <div className="p-2">
            <div className="relative">
              <Search className={`absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 ${isDark ? 'text-gray-400' : 'text-gray-500'}`} />
              <input type="text" value={search} onChange={e => setSearch(e.target.value)} placeholder="Buscar..."
                className={`w-full pl-9 pr-3 py-2 text-sm rounded-lg border ${
                  isDark ? 'bg-gray-700 border-gray-600 text-white placeholder-gray-400' : 'bg-gray-50 border-gray-300 text-gray-900 placeholder-gray-500'
                } focus:ring-2 focus:ring-indigo-500 focus:border-transparent`} />
            </div>
          </div>
          <div className="max-h-48 overflow-y-auto">
            <button type="button" onClick={() => { onChange(null); setIsOpen(false); setSearch(''); }}
              className={`w-full px-4 py-2 text-sm text-left ${isDark ? 'hover:bg-gray-700 text-gray-300' : 'hover:bg-gray-100 text-gray-500'} transition-colors`}>
              -- Limpar --
            </button>
            {filtered.map(option => (
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

const KpiCard: React.FC<{
  title: string; value: string; subtitle?: string;
  icon: React.ReactNode; gradient: string; isDark: boolean;
}> = ({ title, value, subtitle, icon, gradient, isDark }) => (
  <div className={`relative overflow-hidden rounded-2xl p-5 ${isDark ? 'bg-gray-800/60 backdrop-blur-xl border border-gray-700/50' : 'bg-white/80 backdrop-blur-xl border border-gray-200/80'} transition-all hover:scale-[1.02] hover:shadow-lg`}>
    <div className={`absolute top-0 right-0 w-24 h-24 rounded-full blur-2xl opacity-20 ${gradient}`} />
    <div className="relative flex items-start justify-between">
      <div className="flex-1">
        <p className={`text-xs font-semibold uppercase tracking-wider ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>{title}</p>
        <p className={`text-2xl font-black mt-1.5 ${isDark ? 'text-white' : 'text-gray-900'}`}>{value}</p>
        {subtitle && <p className={`text-xs mt-1 ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>{subtitle}</p>}
      </div>
      <div className={`p-2.5 rounded-xl bg-gradient-to-br ${gradient} shadow-lg`}>{icon}</div>
    </div>
  </div>
);

const SectionLabel: React.FC<{ label: string; isDark: boolean; color: string }> = ({ label, isDark, color }) => (
  <div className="flex items-center gap-3 mb-4">
    <div className={`h-px flex-1 ${isDark ? 'bg-gray-700' : 'bg-gray-200'}`} />
    <span className={`text-xs font-bold uppercase tracking-widest px-3 py-1 rounded-full ${color}`}>{label}</span>
    <div className={`h-px flex-1 ${isDark ? 'bg-gray-700' : 'bg-gray-200'}`} />
  </div>
);

const IscBadge: React.FC<{ status: string }> = ({ status }) => {
  const info = ISC_BADGE[status] || { bg: 'bg-gray-500/20', text: 'text-gray-400', label: status };
  return (
    <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${info.bg} ${info.text}`}>{info.label}</span>
  );
};

const OcupacaoBar: React.FC<{ taxa: number }> = ({ taxa }) => {
  const color = taxa >= 80 ? 'bg-emerald-500' : taxa >= 50 ? 'bg-amber-500' : 'bg-red-500';
  const textColor = taxa >= 80 ? 'text-emerald-400' : taxa >= 50 ? 'text-amber-400' : 'text-red-400';
  return (
    <div className="flex items-center gap-2">
      <div className="w-16 h-2 rounded-full bg-gray-200 dark:bg-gray-700 overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${Math.min(taxa, 100)}%` }} />
      </div>
      <span className={`text-xs font-medium ${textColor}`}>{taxa}%</span>
    </div>
  );
};

const CustomTooltip = ({ active, payload, label, isDark }: any) => {
  if (!active || !payload || !payload.length) return null;
  return (
    <div className={`rounded-xl p-3 shadow-xl border ${isDark ? 'bg-gray-800 border-gray-700' : 'bg-white border-gray-200'}`}>
      <p className={`text-sm font-bold mb-1 ${isDark ? 'text-white' : 'text-gray-900'}`}>{label}</p>
      {payload.map((entry: any, i: number) => (
        <p key={i} className="text-xs" style={{ color: entry.color }}>
          {entry.name}: {typeof entry.value === 'number' ? formatNumber(entry.value) : entry.value}
        </p>
      ))}
    </div>
  );
};

const Dashboard: React.FC = () => {
  const { isDark } = useTheme();
  const { canViewCampo } = usePermissions();
  const { user } = useAuth();
  const canSeeFinancial = canViewCampo('dashboard', 'dados_financeiros');

  const uid = user?.id ?? 'anon';
  const CACHE_KEY_OP = `dash_op_${uid}`;
  const CACHE_KEY_FIN = `dash_fin_${uid}`;
  const CACHE_KEY_REL = `dash_rel_${uid}`;
  const CACHE_KEY_FILTROS = `dash_filtros_v2_${uid}`;

  const CACHE_TTL_MS = 30 * 60 * 1000;
  const getNextRefreshMs = (): number => Date.now() + CACHE_TTL_MS;

  const readCache = (key: string) => {
    try {
      const raw = localStorage.getItem(key);
      if (!raw) return null;
      const { data, ts, expiresAt } = JSON.parse(raw);
      const expired = expiresAt ? Date.now() > expiresAt : Date.now() - ts > 30 * 60 * 1000;
      if (expired) return null;
      return data;
    } catch { return null; }
  };

  const writeCache = (key: string, data: any) => {
    try {
      localStorage.setItem(key, JSON.stringify({ data, ts: Date.now(), expiresAt: getNextRefreshMs() }));
    } catch {}
  };

  const isCacheStale = (key: string) => readCache(key) === null;

  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [showFilters, setShowFilters] = useState(false);
  const [opData, setOpData] = useState<any>(() => readCache(CACHE_KEY_OP));
  const [finData, setFinData] = useState<any>(() => canSeeFinancial ? readCache(CACHE_KEY_FIN) : null);
  const [relData, setRelData] = useState<any>(() => canSeeFinancial ? readCache(CACHE_KEY_REL) : null);
  const [relLoading, setRelLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [defaultAno, setDefaultAno] = useState<number>(new Date().getFullYear());

  const cachedFiltros = readCache(CACHE_KEY_FILTROS);
  const [filterOptions, setFilterOptions] = useState<FilterOptions>(
    cachedFiltros || { anos: [], meses: [], produtos: [], modalidades: [], cidades: [] }
  );
  const [filters, setFilters] = useState<Filters>(() => {
    const ano = cachedFiltros?.anos?.[0]?.value || new Date().getFullYear();
    return { ano: ano as number, mes: null, produto: null, modalidade: null, cidade: null };
  });

  const activeFiltersCount = useMemo(() => {
    let c = 0;
    if (filters.mes) c++;
    if (filters.produto) c++;
    if (filters.modalidade) c++;
    if (filters.cidade) c++;
    return c;
  }, [filters]);

  const clearFilters = () => setFilters({ ano: defaultAno, mes: null, produto: null, modalidade: null, cidade: null });

  const hasDataRef = React.useRef(!!readCache(CACHE_KEY_OP));
  const mountHandlingRef = React.useRef(false);

  const loadData = useCallback(async (f: Filters, silent = false) => {
    if (!silent) setRefreshing(true);
    setError(null);
    const apiF = { ano: f.ano, mes: f.mes, produto: f.produto, modalidade: f.modalidade, cidade: f.cidade };
    try {
      const ops: Promise<any>[] = [dashboardService.getOperacional(apiF)];
      if (canSeeFinancial) ops.push(dashboardService.getFinanceiro(apiF));
      const results = await Promise.all(ops);
      setOpData(results[0]);
      hasDataRef.current = true;
      writeCache(CACHE_KEY_OP, results[0]);
      if (canSeeFinancial) {
        setFinData(results[1]);
        writeCache(CACHE_KEY_FIN, results[1]);
      }
    } catch (err: any) {
      if (!hasDataRef.current) setError('Erro ao carregar dados do dashboard');
      console.error('Erro ao carregar dashboard:', err);
    } finally {
      setRefreshing(false);
    }

    if (canSeeFinancial) {
      setRelLoading(true);
      try {
        const rel = await dashboardService.getRelatorioFinanceiro(apiF);
        setRelData(rel);
        writeCache(CACHE_KEY_REL, rel);
      } catch (err: any) {
        console.error('Erro ao carregar relatório financeiro:', err);
      } finally {
        setRelLoading(false);
      }
    }
  }, [canSeeFinancial]);

  useEffect(() => {
    const hasCachedData = !!readCache(CACHE_KEY_OP);

    const init = async () => {
      try {
        const data = await dashboardService.getFiltros();
        const firstAno = data.anos?.[0]?.value || new Date().getFullYear();
        setDefaultAno(firstAno as number);
        const newFiltros = {
          anos: data.anos || [],
          meses: data.meses || [],
          produtos: data.produtos || [],
          modalidades: data.modalidades || [],
          cidades: data.cidades || [],
        };
        setFilterOptions(newFiltros);
        writeCache(CACHE_KEY_FILTROS, newFiltros);
        if (!hasCachedData) {
          setFilters(prev => ({ ...prev, ano: firstAno as number }));
        } else {
          setFilters(prev => {
            const ano = prev.ano || firstAno as number;
            return { ...prev, ano };
          });
        }
      } catch {
        if (!hasCachedData) setFilters(prev => ({ ...prev, ano: new Date().getFullYear() }));
      } finally {
        setLoading(false);
      }
    };

    if (hasCachedData) {
      setLoading(false);
      mountHandlingRef.current = true;
      init().then(() => {
        if (isCacheStale(CACHE_KEY_OP)) {
          const currentAno = filters.ano || defaultAno;
          loadData({ ...filters, ano: currentAno }, true);
        }
        mountHandlingRef.current = false;
      });
    } else {
      init();
    }
  }, []);

  useEffect(() => {
    if (mountHandlingRef.current) return;
    if (!loading && filters.ano) loadData(filters, false);
  }, [filters]);

  const cardClass = `rounded-2xl p-6 ${isDark ? 'bg-gray-800/60 backdrop-blur-xl border border-gray-700/50' : 'bg-white/80 backdrop-blur-xl border border-gray-200/80'}`;

  if (loading && !opData) return (
    <div className="min-h-screen flex items-center justify-center">
      <div className="w-8 h-8 border-4 border-indigo-500 border-t-transparent rounded-full animate-spin" />
    </div>
  );

  return (
    <div className="min-h-screen">
      <div className="fixed inset-0 pointer-events-none overflow-hidden">
        <div className="absolute top-0 left-1/4 w-96 h-96 bg-indigo-500/10 rounded-full blur-3xl animate-pulse" />
        <div className="absolute bottom-0 right-1/4 w-96 h-96 bg-purple-500/10 rounded-full blur-3xl animate-pulse" style={{ animationDelay: '1s' }} />
      </div>

      <div className="relative z-10 space-y-6 p-6">
        <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-xl bg-gradient-to-br from-indigo-500 to-purple-500 shadow-lg shadow-indigo-500/30">
              <LayoutDashboard className="w-6 h-6 text-white" />
            </div>
            <div>
              <h1 className={`text-3xl font-black tracking-tight ${isDark ? 'text-white' : 'text-gray-900'}`}>
                Dashboard
                <span className="bg-gradient-to-r from-indigo-400 via-purple-500 to-pink-500 bg-clip-text text-transparent"> Consolidado</span>
              </h1>
              <p className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>Visão geral do portfólio de eventos</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <button onClick={() => loadData(filters)} disabled={refreshing}
              className={`flex items-center gap-2 px-4 py-3 rounded-xl border transition-all ${
                isDark ? 'bg-gray-800/50 border-gray-700 text-gray-300 hover:bg-gray-700' : 'bg-white/70 border-gray-200 text-gray-700 hover:bg-gray-50'
              }`}>
              <RefreshCw className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''}`} />
              <span className="font-medium text-sm">Atualizar</span>
            </button>
            <button onClick={() => setShowFilters(!showFilters)}
              className={`flex items-center gap-2 px-4 py-3 rounded-xl border transition-all ${
                showFilters || activeFiltersCount > 0
                  ? 'bg-indigo-500/20 border-indigo-500/50 text-indigo-400'
                  : isDark ? 'bg-gray-800/50 border-gray-700 text-gray-300 hover:bg-gray-700' : 'bg-white/70 border-gray-200 text-gray-700 hover:bg-gray-50'
              }`}>
              <Filter className="w-5 h-5" />
              <span className="font-medium text-sm">Filtros</span>
              {activeFiltersCount > 0 && (
                <span className="px-2 py-0.5 text-xs font-bold bg-indigo-500 text-white rounded-full">{activeFiltersCount}</span>
              )}
              <ChevronDown className={`w-4 h-4 transition-transform ${showFilters ? 'rotate-180' : ''}`} />
            </button>
            {activeFiltersCount > 0 && (
              <button onClick={clearFilters}
                className={`flex items-center gap-2 px-4 py-3 rounded-xl border ${isDark ? 'border-gray-700 text-gray-300 hover:bg-gray-700' : 'border-gray-200 text-gray-700 hover:bg-gray-50'} transition-all`}>
                <RotateCcw className="w-4 h-4" />
                <span className="font-medium text-sm">Limpar</span>
              </button>
            )}
          </div>
        </div>

        {showFilters && (
          <div className={`relative z-[100] p-5 rounded-2xl ${isDark ? 'bg-gray-800/50 backdrop-blur-xl border border-gray-700/50' : 'bg-white/70 backdrop-blur-xl border border-gray-200'}`}>
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
              <SearchableDropdown label="Ano" options={filterOptions.anos} value={filters.ano}
                onChange={v => setFilters(p => ({ ...p, ano: v as number }))} placeholder="Selecione o ano" isDark={isDark} />
              <SearchableDropdown label="Mês" options={filterOptions.meses} value={filters.mes}
                onChange={v => setFilters(p => ({ ...p, mes: v as number | null }))} placeholder="Todos" isDark={isDark} />
              <SearchableDropdown label="Produto" options={filterOptions.produtos} value={filters.produto}
                onChange={v => setFilters(p => ({ ...p, produto: v as string | null }))} placeholder="Todos" isDark={isDark} />
              <SearchableDropdown label="Modalidade" options={filterOptions.modalidades} value={filters.modalidade}
                onChange={v => setFilters(p => ({ ...p, modalidade: v as string | null }))} placeholder="Todas" isDark={isDark} />
              <SearchableDropdown label="Cidade" options={filterOptions.cidades} value={filters.cidade}
                onChange={v => setFilters(p => ({ ...p, cidade: v as string | null }))} placeholder="Todas" isDark={isDark} />
            </div>
          </div>
        )}

        {error && (
          <div className="p-4 rounded-xl bg-red-500/10 border border-red-500/30 text-red-400 text-sm">{error}</div>
        )}

        {refreshing && (
          <div className="flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-medium text-indigo-400 bg-indigo-500/10 border border-indigo-500/20 w-fit">
            <div className="w-3 h-3 border-2 border-indigo-400 border-t-transparent rounded-full animate-spin" />
            Atualizando dados...
          </div>
        )}

        {canSeeFinancial && (
          <div className="space-y-4">
            <SectionLabel label="Relatório Financeiro" isDark={isDark}
              color={isDark ? 'text-emerald-400 bg-emerald-500/10' : 'text-emerald-600 bg-emerald-50'} />
            <RelatorioFinanceiro
              data={relData || { meses: [] }}
              loading={relLoading && !relData}
            />
          </div>
        )}

        {opData && (
          <div className="space-y-6">

            <SectionLabel label="Portfólio Operacional" isDark={isDark}
              color={isDark ? 'text-indigo-400 bg-indigo-500/10' : 'text-indigo-600 bg-indigo-50'} />

            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
              <div className={`relative overflow-hidden rounded-2xl p-5 ${isDark ? 'bg-gray-800/60 backdrop-blur-xl border border-gray-700/50' : 'bg-white/80 backdrop-blur-xl border border-gray-200/80'}`}>
                <div className="absolute top-0 right-0 w-24 h-24 rounded-full blur-2xl opacity-20 bg-indigo-500" />
                <div className="relative flex items-start justify-between">
                  <div className="flex-1">
                    <p className={`text-xs font-semibold uppercase tracking-wider ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Atletas Orçados vs Confirmados</p>
                    <p className={`text-2xl font-black mt-1.5 ${isDark ? 'text-white' : 'text-gray-900'}`}>{formatNumber(opData.kpis?.total_atletas_orcado || 0)}</p>
                    <p className={`text-xs mt-1 ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>Confirmados: {formatNumber(opData.kpis?.total_atletas_confirmados || 0)}</p>
                    {opData.kpis?.progresso_atletas_pct !== undefined && (
                      <div className="mt-1.5">
                        <div className="w-full h-1.5 rounded-full bg-gray-200 dark:bg-gray-700 overflow-hidden">
                          <div className="h-full rounded-full bg-indigo-500" style={{ width: `${Math.min(opData.kpis.progresso_atletas_pct, 100)}%` }} />
                        </div>
                        <p className="text-xs mt-0.5 text-indigo-400 font-medium">{opData.kpis.progresso_atletas_pct}% confirmados</p>
                      </div>
                    )}
                  </div>
                  <div className="p-2.5 rounded-xl bg-gradient-to-br from-indigo-500 to-blue-500 shadow-lg"><Users className="w-5 h-5 text-white" /></div>
                </div>
              </div>
              <KpiCard title="Ocupação Média" value={`${opData.kpis?.taxa_ocupacao_media || 0}%`}
                subtitle={`${opData.kpis?.total_eventos || 0} eventos no portfólio`}
                icon={<Percent className="w-5 h-5 text-white" />} gradient="from-purple-500 to-pink-500" isDark={isDark} />
              <KpiCard title="Sell-out Projetado" value={`${opData.kpis?.candidatos_sellout || 0}`}
                subtitle="Ocupação ≥ 80%"
                icon={<Zap className="w-5 h-5 text-white" />} gradient="from-amber-500 to-orange-500" isDark={isDark} />
              <div className={`relative overflow-hidden rounded-2xl p-5 ${isDark ? 'bg-gray-800/60 backdrop-blur-xl border border-gray-700/50' : 'bg-white/80 backdrop-blur-xl border border-gray-200/80'}`}>
                <p className={`text-xs font-semibold uppercase tracking-wider mb-2 ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Saúde ISC</p>
                <div className="space-y-1.5">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-medium text-emerald-400">Acelerando</span>
                    <span className="text-sm font-bold text-emerald-400">{opData.kpis?.isc_acelerando || 0}</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-medium text-amber-400">Estável</span>
                    <span className="text-sm font-bold text-amber-400">{opData.kpis?.isc_estavel || 0}</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-medium text-red-400">Desacelerando</span>
                    <span className="text-sm font-bold text-red-400">{opData.kpis?.isc_desacelerando || 0}</span>
                  </div>
                </div>
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {opData.proximos_eventos?.length > 0 && (
                <div className={`${cardClass} md:col-span-2`}>
                  <h3 className={`text-sm font-bold mb-4 flex items-center gap-2 ${isDark ? 'text-white' : 'text-gray-900'}`}>
                    <CalendarDays className="w-4 h-4 text-indigo-400" />
                    Próximas 4 semanas
                  </h3>
                  <div className="space-y-2">
                    {opData.proximos_eventos.slice(0, 7).map((ev: any, i: number) => (
                      <div key={i} className={`flex items-center justify-between p-2.5 rounded-xl ${isDark ? 'bg-gray-700/40' : 'bg-gray-50'}`}>
                        <div className="flex-1 min-w-0">
                          <p className={`text-sm font-medium truncate ${isDark ? 'text-white' : 'text-gray-900'}`}>{ev.evento}</p>
                          <div className="flex items-center gap-2 mt-0.5">
                            <p className={`text-xs ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>{ev.cidade} · {new Date(ev.data_evento + 'T00:00:00').toLocaleDateString('pt-BR')}</p>
                            {ev.isc_status && <IscBadge status={ev.isc_status} />}
                          </div>
                        </div>
                        <div className="flex items-center gap-3 ml-3">
                          <OcupacaoBar taxa={ev.taxa_ocupacao} />
                          <span className={`text-xs font-bold px-2 py-1 rounded-full ${
                            ev.dias_para_evento <= 7
                              ? 'bg-red-500/20 text-red-400'
                              : ev.dias_para_evento <= 14
                              ? 'bg-amber-500/20 text-amber-400'
                              : 'bg-indigo-500/20 text-indigo-400'
                          }`}>D-{ev.dias_para_evento}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <div className="space-y-4">
                {opData.alertas_ocupacao?.length > 0 && (
                  <div className={cardClass}>
                    <h3 className={`text-sm font-bold mb-3 flex items-center gap-2 ${isDark ? 'text-white' : 'text-gray-900'}`}>
                      <AlertTriangle className="w-4 h-4 text-red-400" />
                      Abaixo da Curva
                    </h3>
                    <div className="space-y-2">
                      {opData.alertas_ocupacao.slice(0, 4).map((ev: any, i: number) => (
                        <div key={i} className={`flex items-center justify-between p-2 rounded-lg ${isDark ? 'bg-gray-700/40' : 'bg-red-50'}`}>
                          <p className={`text-xs font-medium truncate flex-1 ${isDark ? 'text-gray-200' : 'text-gray-800'}`}>{ev.evento}</p>
                          <div className="flex items-center gap-1.5 ml-2">
                            {ev.isc_status && <IscBadge status={ev.isc_status} />}
                            <span className="text-xs font-bold text-red-400">{ev.taxa_ocupacao}%</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {opData.candidatos_sellout?.length > 0 && (
                  <div className={cardClass}>
                    <h3 className={`text-sm font-bold mb-3 flex items-center gap-2 ${isDark ? 'text-white' : 'text-gray-900'}`}>
                      <Zap className="w-4 h-4 text-emerald-400" />
                      Sell-out Projetado
                    </h3>
                    <div className="space-y-2">
                      {opData.candidatos_sellout.slice(0, 4).map((ev: any, i: number) => (
                        <div key={i} className={`flex items-center justify-between p-2 rounded-lg ${isDark ? 'bg-gray-700/40' : 'bg-emerald-50'}`}>
                          <div className="flex-1 min-w-0">
                            <p className={`text-xs font-medium truncate ${isDark ? 'text-gray-200' : 'text-gray-800'}`}>{ev.evento}</p>
                            {ev.vagas_restantes !== undefined && (
                              <p className={`text-xs ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>{formatNumber(ev.vagas_restantes)} vagas restantes</p>
                            )}
                          </div>
                          <span className="ml-2 text-xs font-bold text-emerald-400">{ev.taxa_ocupacao}%</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {opData.top_por_velocity?.length > 0 && (
                <div className={cardClass}>
                  <h3 className={`text-sm font-bold mb-4 flex items-center gap-2 ${isDark ? 'text-white' : 'text-gray-900'}`}>
                    <TrendingUp className="w-4 h-4 text-amber-400" />
                    Top Eventos — Velocidade Rolling 14d
                  </h3>
                  <ResponsiveContainer width="100%" height={260}>
                    <BarChart data={opData.top_por_velocity} layout="vertical" margin={{ left: 8, right: 16 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke={isDark ? '#374151' : '#e5e7eb'} />
                      <XAxis type="number" tick={{ fontSize: 11, fill: isDark ? '#9ca3af' : '#6b7280' }} tickFormatter={v => `${v.toFixed(1)}`} />
                      <YAxis type="category" dataKey="evento" width={140} tick={{ fontSize: 10, fill: isDark ? '#9ca3af' : '#6b7280' }} />
                      <Tooltip content={<CustomTooltip isDark={isDark} />} />
                      <Bar dataKey="rolling14d" name="Vel. 14d (inscrições/dia)" fill="#f59e0b" radius={[0, 6, 6, 0]} barSize={16} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}

              {opData.distribuicao_modalidade?.length > 0 && (
                <div className={cardClass}>
                  <h3 className={`text-sm font-bold mb-4 flex items-center gap-2 ${isDark ? 'text-white' : 'text-gray-900'}`}>
                    <Target className="w-4 h-4 text-purple-400" />
                    Atletas por Modalidade
                  </h3>
                  <ResponsiveContainer width="100%" height={260}>
                    <PieChart>
                      <Pie data={opData.distribuicao_modalidade} dataKey="atletas" nameKey="modalidade"
                        cx="50%" cy="50%" outerRadius={95} innerRadius={50} paddingAngle={3}
                        label={({ modalidade, percent }: any) => `${modalidade} ${(percent * 100).toFixed(0)}%`}
                        labelLine={{ stroke: isDark ? '#6b7280' : '#9ca3af' }}>
                        {opData.distribuicao_modalidade.map((_: any, idx: number) => (
                          <Cell key={idx} fill={PIE_COLORS[idx % PIE_COLORS.length]} />
                        ))}
                      </Pie>
                      <Tooltip content={<CustomTooltip isDark={isDark} />} />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
              )}
            </div>

            {canSeeFinancial && finData && (
              <>
                <SectionLabel label="Análise Financeira" isDark={isDark}
                  color={isDark ? 'text-emerald-400 bg-emerald-500/10' : 'text-emerald-600 bg-emerald-50'} />

                <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                  <div className={`relative overflow-hidden rounded-2xl p-5 ${isDark ? 'bg-gray-800/60 backdrop-blur-xl border border-gray-700/50' : 'bg-white/80 backdrop-blur-xl border border-gray-200/80'}`}>
                    <div className="absolute top-0 right-0 w-24 h-24 rounded-full blur-2xl opacity-20 bg-emerald-500" />
                    <p className={`text-xs font-semibold uppercase tracking-wider ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Receita Projetada vs Orçada</p>
                    <p className={`text-2xl font-black mt-1.5 ${isDark ? 'text-white' : 'text-gray-900'}`}>{formatCurrency(finData.kpis?.receita_total_projetada || 0)}</p>
                    <p className={`text-xs mt-1 ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>Orçado: {formatCurrency(finData.kpis?.receita_total_orcada || 0)}</p>
                    {finData.kpis?.variacao_receita !== undefined && (
                      <p className={`text-xs font-semibold mt-0.5 ${finData.kpis.variacao_receita >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                        {finData.kpis.variacao_receita >= 0 ? '+' : ''}{formatCurrency(finData.kpis.variacao_receita)} vs orçado
                      </p>
                    )}
                  </div>
                  <div className={`relative overflow-hidden rounded-2xl p-5 ${isDark ? 'bg-gray-800/60 backdrop-blur-xl border border-gray-700/50' : 'bg-white/80 backdrop-blur-xl border border-gray-200/80'}`}>
                    <div className="absolute top-0 right-0 w-24 h-24 rounded-full blur-2xl opacity-20 bg-blue-500" />
                    <p className={`text-xs font-semibold uppercase tracking-wider ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Ticket Médio Realizado vs Planejado</p>
                    <p className={`text-2xl font-black mt-1.5 ${isDark ? 'text-white' : 'text-gray-900'}`}>{formatCurrency(finData.kpis?.ticket_medio_realizado || 0)}</p>
                    <p className={`text-xs mt-1 ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>Planejado: {formatCurrency(finData.kpis?.ticket_medio_planejado || 0)}</p>
                    {finData.kpis?.variacao_ticket !== undefined && (
                      <p className={`text-xs font-semibold mt-0.5 ${finData.kpis.variacao_ticket >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                        {finData.kpis.variacao_ticket >= 0 ? '+' : ''}{formatCurrency(finData.kpis.variacao_ticket)} vs planejado
                      </p>
                    )}
                  </div>
                  <KpiCard title="Margem Líquida Média" value={formatCurrency(finData.kpis?.margem_media_liquida || 0)}
                    subtitle={finData.kpis?.percentual_margem_media ? `${finData.kpis.percentual_margem_media}% do ticket` : 'Após custo de kit'}
                    icon={<Percent className="w-5 h-5 text-white" />} gradient="from-violet-500 to-purple-500" isDark={isDark} />
                  <KpiCard title="Receita em Risco (ISC)" value={formatCurrency(finData.kpis?.receita_em_risco || 0)}
                    subtitle={`${finData.eventos_em_risco?.length || 0} eventos desacelerando`}
                    icon={<TrendingDown className="w-5 h-5 text-white" />} gradient="from-red-500 to-rose-500" isDark={isDark} />
                </div>

                <div className="grid grid-cols-2 lg:grid-cols-3 gap-4">
                  <KpiCard title="Atletas Orçados" value={formatNumber(finData.kpis?.atletas_orcado_total || 0)}
                    subtitle={`Confirmados: ${formatNumber(finData.kpis?.atletas_confirmados_total || 0)}`}
                    icon={<Users className="w-5 h-5 text-white" />} gradient="from-indigo-500 to-blue-500" isDark={isDark} />
                  <KpiCard title="Atletas via Site" value={formatNumber(finData.kpis?.atletas_site_total || 0)}
                    subtitle="Inscrições pagas canal site"
                    icon={<Target className="w-5 h-5 text-white" />} gradient="from-purple-500 to-pink-500" isDark={isDark} />
                  <KpiCard title="Oportunidades Yield (ISC)" value={String(finData.kpis?.total_oportunidades_yield || 0)}
                    subtitle="Acelerando c/ ≥10% cap. disponível"
                    icon={<Zap className="w-5 h-5 text-white" />} gradient="from-amber-500 to-orange-500" isDark={isDark} />
                </div>

                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                  {finData.margem_por_modalidade?.length > 0 && (
                    <div className={cardClass}>
                      <h3 className={`text-sm font-bold mb-4 flex items-center gap-2 ${isDark ? 'text-white' : 'text-gray-900'}`}>
                        <DollarSign className="w-4 h-4 text-emerald-400" />
                        Receita Projetada por Modalidade
                      </h3>
                      <ResponsiveContainer width="100%" height={260}>
                        <BarChart data={finData.margem_por_modalidade} margin={{ left: 8, right: 16 }}>
                          <CartesianGrid strokeDasharray="3 3" stroke={isDark ? '#374151' : '#e5e7eb'} />
                          <XAxis dataKey="modalidade" tick={{ fontSize: 11, fill: isDark ? '#9ca3af' : '#6b7280' }} />
                          <YAxis tick={{ fontSize: 11, fill: isDark ? '#9ca3af' : '#6b7280' }} tickFormatter={v => `R$${(v / 1000).toFixed(0)}k`} />
                          <Tooltip content={({ active, payload, label }: any) => {
                            if (!active || !payload?.length) return null;
                            return (
                              <div className={`rounded-xl p-3 shadow-xl border ${isDark ? 'bg-gray-800 border-gray-700' : 'bg-white border-gray-200'}`}>
                                <p className={`text-sm font-bold mb-1 ${isDark ? 'text-white' : 'text-gray-900'}`}>{label}</p>
                                <p className="text-xs text-emerald-400">Receita: {formatCurrency(payload[0]?.value || 0)}</p>
                                {payload[0]?.payload?.margem_media && (
                                  <p className="text-xs text-purple-400">Margem média: {formatCurrency(payload[0].payload.margem_media)}</p>
                                )}
                              </div>
                            );
                          }} />
                          <Bar dataKey="receita_projetada" name="Receita" fill="#10b981" radius={[6, 6, 0, 0]} barSize={40} />
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  )}

                  <div className="space-y-4">
                    {finData.eventos_em_risco?.length > 0 && (
                      <div className={cardClass}>
                        <h3 className={`text-sm font-bold mb-3 flex items-center gap-2 ${isDark ? 'text-white' : 'text-gray-900'}`}>
                          <TrendingDown className="w-4 h-4 text-red-400" />
                          Receita em Risco
                        </h3>
                        <div className="space-y-2">
                          {finData.eventos_em_risco.slice(0, 4).map((ev: any, i: number) => (
                            <div key={i} className={`flex items-center justify-between p-2.5 rounded-xl ${isDark ? 'bg-gray-700/40' : 'bg-red-50'}`}>
                              <div className="flex-1 min-w-0">
                                <p className={`text-xs font-medium truncate ${isDark ? 'text-white' : 'text-gray-900'}`}>{ev.evento}</p>
                                <p className="text-xs text-red-400">{ev.taxa_ocupacao}% ocupação</p>
                              </div>
                              <span className={`ml-2 text-xs font-bold ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>{formatCurrency(ev.receita_projetada)}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {finData.oportunidades_yield?.length > 0 && (
                      <div className={cardClass}>
                        <h3 className={`text-sm font-bold mb-3 flex items-center gap-2 ${isDark ? 'text-white' : 'text-gray-900'}`}>
                          <ArrowRight className="w-4 h-4 text-amber-400" />
                          Oportunidades de Yield
                        </h3>
                        <div className={`p-2 rounded-lg mb-2 text-xs ${isDark ? 'text-gray-400 bg-gray-700/40' : 'text-gray-500 bg-amber-50'}`}>
                          Eventos com boa ocupação e vagas disponíveis — candidatos a ajuste de preço
                        </div>
                        <div className="space-y-2">
                          {finData.oportunidades_yield.slice(0, 4).map((ev: any, i: number) => (
                            <div key={i} className={`flex items-center justify-between p-2.5 rounded-xl ${isDark ? 'bg-gray-700/40' : 'bg-amber-50'}`}>
                              <div className="flex-1 min-w-0">
                                <p className={`text-xs font-medium truncate ${isDark ? 'text-white' : 'text-gray-900'}`}>{ev.evento}</p>
                                <p className="text-xs text-amber-400">{ev.taxa_ocupacao}% · {formatNumber(ev.vagas_restantes)} vagas</p>
                              </div>
                              <span className={`ml-2 text-xs font-bold ${isDark ? 'text-emerald-400' : 'text-emerald-600'}`}>{formatCurrency(ev.ticket_medio)}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                </div>

                {finData.receita_por_produto?.length > 0 && (
                  <div className={cardClass}>
                    <h3 className={`text-sm font-bold mb-4 flex items-center gap-2 ${isDark ? 'text-white' : 'text-gray-900'}`}>
                      <TrendingUp className="w-4 h-4 text-blue-400" />
                      Receita Projetada por Produto
                    </h3>
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className={isDark ? 'bg-gray-700/50' : 'bg-gray-50'}>
                            {['Produto', 'Receita Projetada', 'Ticket Médio', 'Atletas'].map(h => (
                              <th key={h} className={`px-4 py-3 text-left text-xs font-bold uppercase tracking-wider ${isDark ? 'text-gray-300' : 'text-gray-600'}`}>{h}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody className={`divide-y ${isDark ? 'divide-gray-700/50' : 'divide-gray-100'}`}>
                          {finData.receita_por_produto.map((row: any, i: number) => (
                            <tr key={i} className={isDark ? 'hover:bg-gray-700/30' : 'hover:bg-gray-50/80'}>
                              <td className={`px-4 py-3 font-medium ${isDark ? 'text-white' : 'text-gray-900'}`}>{row.produto}</td>
                              <td className={`px-4 py-3 font-semibold ${isDark ? 'text-emerald-400' : 'text-emerald-600'}`}>{formatCurrency(row.receita_projetada)}</td>
                              <td className={`px-4 py-3 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>{row.ticket_medio > 0 ? formatCurrency(row.ticket_medio) : '-'}</td>
                              <td className={`px-4 py-3 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>{formatNumber(row.atletas)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        )}

        {!opData && !refreshing && !error && (
          <div className="flex items-center justify-center py-20">
            <p className={`text-sm ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>Selecione um período para visualizar os dados</p>
          </div>
        )}
      </div>
    </div>
  );
};

export default Dashboard;
