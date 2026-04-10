import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import ConnectionAlert from '../../components/common/ConnectionAlert';
import { 
  TrendingUp, 
  TrendingDown, 
  Activity, 
  Calendar,
  Search,
  Filter,
  FilterX,
  AlertTriangle,
  Target,
  ChevronRight,
  Info,
  RefreshCw,
  Clock,
  CheckCircle,
  XCircle,
  AlertCircle,
  Archive,
  BookOpen,
  Zap
} from 'lucide-react';
import { 
  getISCColor, 
  getISCEmoji, 
  isInCriticalWindow 
} from '../../types/marketingPerformance';
import { marketingService, MarketingEvent, MarketingDashboardSummary, getMarketingDashboardCache, clearMarketingDashboardCache } from '../../services/api';
import { useTheme } from '../../context/ThemeContext';
import { usePermissions } from '../../context/PermissionContext';

const SkeletonPulse: React.FC<{ className?: string }> = ({ className = '' }) => (
  <div className={`animate-pulse bg-gray-200 dark:bg-gray-700 rounded ${className}`} />
);

const SkeletonCard: React.FC = () => (
  <div className="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm border border-gray-200 dark:border-gray-700">
    <div className="flex items-center justify-between">
      <div className="space-y-3 flex-1">
        <SkeletonPulse className="h-4 w-24" />
        <SkeletonPulse className="h-8 w-16" />
        <SkeletonPulse className="h-3 w-32" />
      </div>
      <SkeletonPulse className="h-12 w-12 rounded-lg" />
    </div>
  </div>
);

const SkeletonTableRow: React.FC = () => (
  <tr className="border-b border-gray-200 dark:border-gray-700">
    <td className="px-4 py-4">
      <div className="space-y-2">
        <SkeletonPulse className="h-4 w-36" />
        <SkeletonPulse className="h-3 w-24" />
      </div>
    </td>
    <td className="px-4 py-4"><SkeletonPulse className="h-4 w-20" /></td>
    <td className="px-4 py-4"><SkeletonPulse className="h-4 w-12 mx-auto" /></td>
    <td className="px-4 py-4"><SkeletonPulse className="h-4 w-12 mx-auto" /></td>
    <td className="px-4 py-4">
      <div className="flex flex-col items-center gap-1">
        <SkeletonPulse className="h-4 w-24" />
        <SkeletonPulse className="h-2 w-24 rounded-full" />
        <SkeletonPulse className="h-3 w-10" />
      </div>
    </td>
    <td className="px-4 py-4"><SkeletonPulse className="h-5 w-16 mx-auto" /></td>
    <td className="px-4 py-4"><SkeletonPulse className="h-4 w-12 mx-auto" /></td>
    <td className="px-4 py-4"><SkeletonPulse className="h-4 w-12 mx-auto" /></td>
    <td className="px-4 py-4"><SkeletonPulse className="h-4 w-12 mx-auto" /></td>
    <td className="px-4 py-4"><SkeletonPulse className="h-6 w-24 mx-auto rounded-full" /></td>
    <td className="px-4 py-4"><SkeletonPulse className="h-4 w-8 mx-auto" /></td>
    <td className="px-4 py-4"><SkeletonPulse className="h-5 w-5 mx-auto" /></td>
  </tr>
);

const SkeletonFilters: React.FC = () => (
  <div className="p-4 border-b border-gray-200 dark:border-gray-700">
    <div className="flex flex-col lg:flex-row lg:items-center gap-4">
      <SkeletonPulse className="h-10 flex-1 rounded-lg" />
      <div className="flex items-center gap-3">
        <SkeletonPulse className="h-10 w-40 rounded-lg" />
        <SkeletonPulse className="h-10 w-28 rounded-lg" />
      </div>
    </div>
  </div>
);

const SESSION_STORAGE_KEY = 'mktDashFilters';

const VALID_STATUS = ['all', 'active', 'closed'];
const VALID_ZONE = ['all', 'accelerating', 'stable', 'decelerating'];
const VALID_DMINUS = ['all', 'critical', '41-60', '61-90', '91-120', '120+'];

const PLAYBOOK_CUTOFFS = [
  { value: 70, label: 'D-70', stage: 'Analítico' },
  { value: 50, label: 'D-50', stage: 'Analítico' },
  { value: 45, label: 'D-45', stage: 'Estratégico' },
  { value: 35, label: 'D-35', stage: 'Estratégico' },
  { value: 30, label: 'D-30', stage: 'Operacional' },
  { value: 15, label: 'D-15', stage: 'Operacional' },
];
function getCutoffAlert(dMinus: number): { value: number; label: string; stage: string } | null {
  for (const co of PLAYBOOK_CUTOFFS) {
    if (dMinus === co.value) {
      return co;
    }
  }
  return null;
}

function loadFilters(): { search: string; category: string; status: string; zone: string; dMinus: string; onlyCutoff: boolean } {
  try {
    const raw = sessionStorage.getItem(SESSION_STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      return {
        search: typeof parsed.search === 'string' ? parsed.search : '',
        category: typeof parsed.category === 'string' ? parsed.category : 'all',
        status: VALID_STATUS.includes(parsed.status) ? parsed.status : 'active',
        zone: VALID_ZONE.includes(parsed.zone) ? parsed.zone : 'all',
        dMinus: VALID_DMINUS.includes(parsed.dMinus) ? parsed.dMinus : 'all',
        onlyCutoff: typeof parsed.onlyCutoff === 'boolean' ? parsed.onlyCutoff : false,
      };
    }
  } catch {}
  return { search: '', category: 'all', status: 'active', zone: 'all', dMinus: 'all', onlyCutoff: false };
}

function saveFilters(filters: { search: string; category: string; status: string; zone: string; dMinus: string; onlyCutoff: boolean }) {
  try {
    sessionStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(filters));
  } catch {}
}

const MarketingDashboard: React.FC = () => {
  const navigate = useNavigate();
  const { isDark } = useTheme();
  const { permissions } = usePermissions();
  const isAdmin = permissions?.is_admin === true;
  const initialFilters = useMemo(() => loadFilters(), []);
  const [searchInput, setSearchInput] = useState(initialFilters.search);
  const [debouncedSearch, setDebouncedSearch] = useState(initialFilters.search);
  const [categoryFilter, setCategoryFilter] = useState(initialFilters.category);
  const [statusFilter, setStatusFilter] = useState(initialFilters.status);
  const [zoneFilter, setZoneFilter] = useState(initialFilters.zone);
  const [dMinusFilter, setDMinusFilter] = useState(initialFilters.dMinus);
  const [onlyCutoff, setOnlyCutoff] = useState(initialFilters.onlyCutoff);
  
  const [eventos, setEventos] = useState<MarketingEvent[]>([]);
  const [summary, setSummary] = useState<MarketingDashboardSummary>({
    totalActiveEvents: 0,
    eventsGreen: 0,
    eventsYellow: 0,
    eventsRed: 0
  });
  const [categories, setCategories] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingTooLong, setLoadingTooLong] = useState(false);
  const loadingTooLongTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [fullRefreshing, setFullRefreshing] = useState(false);
  const [syncingHoje, setSyncingHoje] = useState(false);
  const [syncHojeResult, setSyncHojeResult] = useState<'success' | 'error' | null>(null);
  const [bgRefreshing, setBgRefreshing] = useState(false);
  const [refreshProgress, setRefreshProgress] = useState<{step: number; total_steps: number; label: string; elapsed_seconds: number | null; sub_current?: number; sub_total?: number} | null>(null);
  const [refreshResult, setRefreshResult] = useState<'success' | 'error' | 'timeout' | null>(null);
  const [revalidating, setRevalidating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [serverLastUpdate, setServerLastUpdate] = useState<string | null>(null);
  const [dataTimestamp, setDataTimestamp] = useState<string | null>(null);
  const [avisos, setAvisos] = useState<string[]>([]);
  const [fromCache, setFromCache] = useState(false);
  const [serverStale, setServerStale] = useState(false);
  
  const autoRefreshRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const staleRefetchTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const cacheStatusIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const refreshResultRef = useRef<'success' | 'error' | 'timeout' | null>(null);
  const AUTO_REFRESH_INTERVAL = 60 * 60 * 1000;

  const applyResponse = useCallback((response: any) => {
    setEventos(response.eventos);
    setSummary(response.resumo);
    setCategories(response.categorias);
    setAvisos((response as any).avisos || []);
    if (response.ultima_atualizacao) {
      setDataTimestamp(response.ultima_atualizacao);
    }
  }, []);

  useEffect(() => {
    saveFilters({
      search: searchInput,
      category: categoryFilter,
      status: statusFilter,
      zone: zoneFilter,
      dMinus: dMinusFilter,
      onlyCutoff,
    });
  }, [searchInput, categoryFilter, statusFilter, zoneFilter, dMinusFilter, onlyCutoff]);

  const fetchData = useCallback(async (isRefresh = false, forceRefresh = false) => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    const controller = new AbortController();
    abortControllerRef.current = controller;

    const requestParams = {
      ano: new Date().getFullYear(),
    };

    const cached = getMarketingDashboardCache(requestParams);
    const hasCachedData = cached !== null;

    if (hasCachedData && !isRefresh && !forceRefresh) {
      applyResponse(cached.data);
      setLoading(false);
      setLoadingTooLong(false);
      setFromCache(true);
      setRevalidating(true);
    } else if (isRefresh) {
      setRefreshing(true);
    } else {
      setLoading(true);
      setLoadingTooLong(false);
      if (loadingTooLongTimerRef.current) clearTimeout(loadingTooLongTimerRef.current);
      loadingTooLongTimerRef.current = setTimeout(() => setLoadingTooLong(true), 12000);
    }

    try {
      if (!refreshResultRef.current) {
        setError(null);
      }
      
      const response = await marketingService.getEventos({
        ...requestParams,
        force_refresh: forceRefresh || undefined
      }, controller.signal);
      
      if (!controller.signal.aborted) {
        applyResponse(response);
        setFromCache(false);
        const isStale = !!(response as any)._isStale;
        setServerStale(isStale);
        if (staleRefetchTimerRef.current) {
          clearTimeout(staleRefetchTimerRef.current);
          staleRefetchTimerRef.current = null;
        }
        if (isStale) {
          staleRefetchTimerRef.current = setTimeout(() => {
            fetchData(true);
          }, 30000);
        }
      }
    } catch (err: any) {
      if (err?.name === 'CanceledError' || err?.code === 'ERR_CANCELED') {
        return;
      }
      if (hasCachedData) {
        console.warn('Falha ao revalidar dados, mantendo cache:', err?.message);
        setFromCache(true);
        setRevalidating(false);
        setRefreshing(false);
        setLoading(false);
        return;
      }
      console.error('Erro ao carregar dados:', err);
      const status = err?.response?.status;
      const detail = err?.response?.data?.detail;
      if (status === 401 || status === 403) {
        setError('Sessão expirada. Faça login novamente para continuar.');
      } else if (status === 500) {
        setError(`Erro interno do servidor${detail ? `: ${detail}` : ''}. O banco de dados pode estar temporariamente indisponível.`);
      } else if (err?.code === 'ERR_NETWORK' || err?.message?.includes('Network')) {
        setError('Erro de rede: não foi possível conectar ao servidor. Verifique sua conexão.');
      } else {
        setError(`Erro ao carregar dados${detail ? `: ${detail}` : ''}. Tente novamente.`);
      }
    } finally {
      if (!controller.signal.aborted) {
        if (loadingTooLongTimerRef.current) {
          clearTimeout(loadingTooLongTimerRef.current);
          loadingTooLongTimerRef.current = null;
        }
        setLoading(false);
        setLoadingTooLong(false);
        setRefreshing(false);
        setRevalidating(false);
      }
    }
  }, [applyResponse]);

  useEffect(() => {
    fetchData();
    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
      if (staleRefetchTimerRef.current) {
        clearTimeout(staleRefetchTimerRef.current);
      }
    };
  }, [fetchData]);

  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(searchInput);
    }, 500);
    return () => clearTimeout(timer);
  }, [searchInput]);

  useEffect(() => {
    autoRefreshRef.current = setInterval(() => {
      fetchData(true);
    }, AUTO_REFRESH_INTERVAL);

    return () => {
      if (autoRefreshRef.current) {
        clearInterval(autoRefreshRef.current);
      }
    };
  }, [fetchData]);

  const showRefreshResult = (result: 'success' | 'error' | 'timeout') => {
    setRefreshResult(result);
    refreshResultRef.current = result;
    setTimeout(() => {
      setRefreshResult(null);
      refreshResultRef.current = null;
    }, 5000);
  };

  const handleSyncHoje = async () => {
    if (syncingHoje || fullRefreshing) return;
    setSyncingHoje(true);
    setSyncHojeResult(null);
    try {
      const result = await marketingService.syncHoje();
      if (result.status === 'ok') {
        setSyncHojeResult('success');
        clearMarketingDashboardCache();
        fetchData(true, false);
      } else {
        setSyncHojeResult('error');
      }
    } catch {
      setSyncHojeResult('error');
    } finally {
      setSyncingHoje(false);
      setTimeout(() => setSyncHojeResult(null), 5000);
    }
  };

  const handleFullRefresh = async () => {
    setFullRefreshing(true);
    setRefreshProgress(null);
    setRefreshResult(null);
    const MAX_POLL_TIME = 3 * 60 * 1000;
    const POLL_INTERVAL = 3000;

    const startPolling = () => {
      const pollStart = Date.now();
      const pollStatus = setInterval(async () => {
        try {
          if (Date.now() - pollStart > MAX_POLL_TIME) {
            clearInterval(pollStatus);
            setFullRefreshing(false);
            setRefreshProgress(null);
            showRefreshResult('timeout');
            setAvisos(prev => [...prev, 'A atualização está demorando mais que o esperado. Ela continua em andamento no servidor e será concluída em breve.']);
            fetchData(true, false);
            return;
          }
          const status = await marketingService.getCacheStatus();
          if (!status.refresh_in_progress) {
            clearInterval(pollStatus);
            setFullRefreshing(false);
            setRefreshProgress(null);
            if (status.last_error) {
              if (status.last_error.includes('avisos')) {
                showRefreshResult('success');
                setAvisos(prev => [...prev, status.last_error!]);
              } else {
                showRefreshResult('error');
                setError(status.last_error);
              }
            } else {
              showRefreshResult('success');
            }
            if (status.ultima_atualizacao_completa) {
              setServerLastUpdate(status.ultima_atualizacao_completa);
            }
            fetchData(true, false);
          } else if (status.progress) {
            setRefreshProgress(status.progress);
          }
        } catch {
          clearInterval(pollStatus);
          setFullRefreshing(false);
          setRefreshProgress(null);
          showRefreshResult('error');
          setError('Erro de conexão ao verificar o status da atualização. Tente novamente.');
        }
      }, POLL_INTERVAL);
    };

    try {
      const result = await marketingService.refreshAllCaches();
      if (result.status === 'started' || result.status === 'in_progress') {
        startPolling();
      } else {
        setFullRefreshing(false);
        showRefreshResult('error');
        setError('Não foi possível iniciar a atualização. Tente novamente.');
      }
    } catch (err) {
      console.error('Erro ao atualizar todos os caches:', err);
      setFullRefreshing(false);
      setRefreshProgress(null);
      showRefreshResult('error');
      setError('Erro ao conectar com o servidor para iniciar a atualização.');
    }
  };

  useEffect(() => {
    const fetchCacheStatus = async () => {
      try {
        const status = await marketingService.getCacheStatus();
        const latestSync = status.last_sync_hoje || status.ultima_atualizacao_completa;
        if (latestSync) {
          setServerLastUpdate(latestSync);
        }
        setBgRefreshing(status.refresh_in_progress);
        if (!status.refresh_in_progress) {
          setFullRefreshing(false);
          setRefreshProgress(null);
        }
      } catch {}
    };
    fetchCacheStatus();
    cacheStatusIntervalRef.current = setInterval(fetchCacheStatus, 60000);
    return () => {
      if (cacheStatusIntervalRef.current) {
        clearInterval(cacheStatusIntervalRef.current);
      }
    };
  }, []);

  const hasActiveFilters = useMemo(() => {
    return searchInput !== '' || categoryFilter !== 'all' || statusFilter !== 'active' || zoneFilter !== 'all' || dMinusFilter !== 'all' || onlyCutoff;
  }, [searchInput, categoryFilter, statusFilter, zoneFilter, dMinusFilter, onlyCutoff]);

  const clearAllFilters = useCallback(() => {
    setSearchInput('');
    setDebouncedSearch('');
    setCategoryFilter('all');
    setStatusFilter('active');
    setZoneFilter('all');
    setDMinusFilter('all');
    setOnlyCutoff(false);
    try { sessionStorage.removeItem(SESSION_STORAGE_KEY); } catch {}
  }, []);

  const filteredEventos = useMemo(() => {
    let filtered = eventos;

    if (debouncedSearch) {
      const lower = debouncedSearch.toLowerCase();
      filtered = filtered.filter(e =>
        (e.name ?? '').toLowerCase().includes(lower) ||
        (e.location ?? '').toLowerCase().includes(lower)
      );
    }

    if (categoryFilter !== 'all') {
      filtered = filtered.filter(e => e.category === categoryFilter);
    }

    if (statusFilter !== 'all') {
      filtered = filtered.filter(e => {
        if (statusFilter === 'active') return e.isActive;
        if (statusFilter === 'closed') return !e.isActive;
        return true;
      });
    }

    if (zoneFilter !== 'all') {
      filtered = filtered.filter(e => e.iscStatus === zoneFilter);
    }

    if (dMinusFilter !== 'all') {
      filtered = filtered.filter(e => {
        switch (dMinusFilter) {
          case 'critical': return e.dMinusInscricoes <= 40;
          case '41-60': return e.dMinusInscricoes >= 41 && e.dMinusInscricoes <= 60;
          case '61-90': return e.dMinusInscricoes >= 61 && e.dMinusInscricoes <= 90;
          case '91-120': return e.dMinusInscricoes >= 91 && e.dMinusInscricoes <= 120;
          case '120+': return e.dMinusInscricoes > 120;
          default: return true;
        }
      });
    }

    if (onlyCutoff) {
      filtered = filtered.filter(e => getCutoffAlert(e.dMinusInscricoes) !== null);
    }

    return filtered;
  }, [eventos, debouncedSearch, categoryFilter, statusFilter, zoneFilter, dMinusFilter, onlyCutoff]);

  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat('pt-BR', {
      style: 'currency',
      currency: 'BRL'
    }).format(value);
  };

  const formatNumber = (value: number) => {
    return new Intl.NumberFormat('pt-BR').format(value);
  };

  const formatLastUpdate = (date: Date | null) => {
    if (!date) return '';
    return date.toLocaleString('pt-BR', { 
      day: '2-digit', 
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit', 
      minute: '2-digit',
      timeZone: 'America/Sao_Paulo'
    });
  };

  return (
    <div className="min-h-screen">
      <div className="fixed inset-0 pointer-events-none overflow-hidden">
        <div className={`absolute top-0 left-1/4 w-96 h-96 ${isDark ? 'bg-blue-500/10' : 'bg-blue-400/20'} rounded-full blur-3xl animate-pulse`} />
        <div className={`absolute bottom-0 right-1/4 w-96 h-96 ${isDark ? 'bg-purple-500/10' : 'bg-purple-400/20'} rounded-full blur-3xl animate-pulse`} style={{ animationDelay: '1s' }} />
        <div className={`absolute top-1/2 left-1/2 w-64 h-64 ${isDark ? 'bg-indigo-500/5' : 'bg-indigo-400/15'} rounded-full blur-3xl animate-pulse`} style={{ animationDelay: '2s' }} />
      </div>

      {(revalidating || serverStale) && (
        <div className="fixed top-0 left-0 right-0 z-50 h-1 bg-gray-200 dark:bg-gray-700 overflow-hidden">
          <div className="h-full bg-gradient-to-r from-blue-500 via-indigo-500 to-blue-500 animate-[shimmer_1.5s_ease-in-out_infinite]" style={{ width: '40%', animation: 'shimmer 1.5s ease-in-out infinite' }} />
          <style>{`@keyframes shimmer { 0% { transform: translateX(-100%); } 100% { transform: translateX(350%); } }`}</style>
        </div>
      )}

      <div className="relative z-10 p-6 space-y-6">
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <h1 className={`text-2xl font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>
              Marketing Performance
            </h1>
            <button
              onClick={() => navigate('/marketing/playbook')}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-indigo-100 dark:bg-indigo-900/40 text-indigo-700 dark:text-indigo-300 hover:bg-indigo-200 dark:hover:bg-indigo-900/60 transition-colors border border-indigo-200 dark:border-indigo-700"
            >
              <BookOpen className="w-3.5 h-3.5" />
              Playbook
            </button>
          </div>
          <p className={`mt-1 ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
            Acompanhamento de vendas e ISC dos eventos
          </p>
        </div>
        
        <div className="flex items-center gap-3 flex-wrap">
          {/* Data freshness banner — always visible */}
          <div className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium border ${
            loading
              ? isDark ? 'bg-gray-800/60 border-gray-700 text-gray-400' : 'bg-gray-100 border-gray-200 text-gray-400'
              : serverStale
                ? isDark ? 'bg-amber-900/30 border-amber-700/50 text-amber-300' : 'bg-amber-50 border-amber-200 text-amber-700'
                : isDark ? 'bg-gray-800/60 border-gray-700/50 text-gray-300' : 'bg-gray-50 border-gray-200 text-gray-600'
          }`}>
            {loading ? (
              <>
                <RefreshCw className="w-3.5 h-3.5 animate-spin opacity-60" />
                <span>Carregando dados...</span>
              </>
            ) : serverStale ? (
              <>
                <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                <span>Atualizando dados do servidor...</span>
              </>
            ) : (
              <>
                <Clock className="w-3.5 h-3.5 opacity-70" />
                <span>
                  {(() => {
                    const ts = serverLastUpdate || dataTimestamp;
                    if (!ts) return 'Horário de sincronização indisponível';
                    const d = new Date(ts);
                    const now = new Date();
                    const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate());
                    const yesterdayStart = new Date(todayStart.getTime() - 86400000);
                    const syncTimeStr = d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
                    const nextSync = new Date(d.getTime() + 30 * 60 * 1000);
                    const nextStr = nextSync.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
                    const prefix = d >= todayStart
                      ? `Sinc. hoje às ${syncTimeStr}`
                      : d >= yesterdayStart
                        ? `Sinc. ontem às ${syncTimeStr}`
                        : `Sinc. ${d.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' })} às ${syncTimeStr}`;
                    const nextLabel = nextSync > now ? ` · próx. ${nextStr}` : '';
                    return prefix + nextLabel;
                  })()}
                </span>
              </>
            )}
          </div>
          {isAdmin && (
          <div className="flex flex-col gap-1.5">
            <div className="flex items-center gap-2">
              <button
                onClick={handleFullRefresh}
                disabled={fullRefreshing || loading}
                title="Atualiza todos os dados do servidor (somente admin)"
                className={`flex items-center gap-2 px-3 py-1.5 rounded-lg transition-colors text-sm ${
                  refreshResult === 'success'
                    ? 'bg-green-100 dark:bg-green-900/30 text-green-600 dark:text-green-400'
                    : refreshResult === 'error'
                      ? 'bg-red-100 dark:bg-red-900/30 text-red-600 dark:text-red-400'
                      : refreshResult === 'timeout'
                        ? 'bg-yellow-100 dark:bg-yellow-900/30 text-yellow-600 dark:text-yellow-400'
                        : 'bg-emerald-100 dark:bg-emerald-900/30 text-emerald-600 dark:text-emerald-400 hover:bg-emerald-200 dark:hover:bg-emerald-900/50'
                } ${(fullRefreshing || loading) ? 'opacity-50 cursor-not-allowed' : ''}`}
              >
                {refreshResult === 'success' ? (
                  <CheckCircle className="w-3.5 h-3.5" />
                ) : refreshResult === 'error' ? (
                  <XCircle className="w-3.5 h-3.5" />
                ) : refreshResult === 'timeout' ? (
                  <AlertCircle className="w-3.5 h-3.5" />
                ) : (
                  <RefreshCw className={`w-3.5 h-3.5 ${fullRefreshing ? 'animate-spin' : ''}`} />
                )}
                <span className="font-medium">
                  {refreshResult === 'success'
                    ? 'Atualizado!'
                    : refreshResult === 'error'
                      ? 'Falha na atualização'
                      : refreshResult === 'timeout'
                        ? 'Tempo esgotado'
                        : fullRefreshing
                          ? refreshProgress && refreshProgress.step > 0
                            ? refreshProgress.label || `Passo ${refreshProgress.step}/${refreshProgress.total_steps}`
                            : 'Iniciando...'
                          : 'Atualizar'}
                </span>
              </button>
              <button
                onClick={handleSyncHoje}
                disabled={syncingHoje || fullRefreshing || loading}
                title="Sincroniza apenas os dados de hoje do MySQL para todos os eventos (~1 min)"
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg transition-colors text-sm ${
                  syncHojeResult === 'success'
                    ? 'bg-green-100 dark:bg-green-900/30 text-green-600 dark:text-green-400'
                    : syncHojeResult === 'error'
                      ? 'bg-red-100 dark:bg-red-900/30 text-red-600 dark:text-red-400'
                      : 'bg-blue-100 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400 hover:bg-blue-200 dark:hover:bg-blue-900/50'
                } ${(syncingHoje || fullRefreshing || loading) ? 'opacity-50 cursor-not-allowed' : ''}`}
              >
                {syncHojeResult === 'success' ? (
                  <CheckCircle className="w-3.5 h-3.5" />
                ) : syncHojeResult === 'error' ? (
                  <XCircle className="w-3.5 h-3.5" />
                ) : (
                  <Zap className={`w-3.5 h-3.5 ${syncingHoje ? 'animate-pulse' : ''}`} />
                )}
                <span className="font-medium">
                  {syncHojeResult === 'success'
                    ? 'Sincronizado!'
                    : syncHojeResult === 'error'
                      ? 'Falha'
                      : syncingHoje
                        ? 'Sincronizando...'
                        : 'Sincronizar Hoje'}
                </span>
              </button>
              {fullRefreshing && refreshProgress && refreshProgress.elapsed_seconds != null && (
                <span className="text-[10px] text-gray-400 dark:text-gray-500 whitespace-nowrap">
                  {Math.round(refreshProgress.elapsed_seconds)}s
                </span>
              )}
              {!fullRefreshing && bgRefreshing && (
                <span className="flex items-center gap-1 text-[10px] text-amber-500 dark:text-amber-400 whitespace-nowrap">
                  <RefreshCw className="w-2.5 h-2.5 animate-spin" />
                  Atualizando em 2º plano
                </span>
              )}
            </div>
            {fullRefreshing && (
              <div className="flex flex-col gap-0.5 w-full min-w-[180px]">
                <div className="w-full h-1.5 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
                  {refreshProgress && refreshProgress.step > 0 ? (
                    <div
                      className="h-full bg-emerald-500 dark:bg-emerald-400 rounded-full transition-all duration-500 ease-out"
                      style={{ width: `${Math.round(((refreshProgress.step - 1 + (refreshProgress.sub_total && refreshProgress.sub_total > 0 ? (refreshProgress.sub_current || 0) / refreshProgress.sub_total : 0)) / refreshProgress.total_steps) * 100)}%` }}
                    />
                  ) : (
                    <div className="h-full w-full bg-emerald-400 dark:bg-emerald-500 rounded-full animate-pulse" />
                  )}
                </div>
                {refreshProgress && refreshProgress.step > 0 && (
                  <div className="flex items-center justify-between">
                    <span className="text-[10px] text-gray-400 dark:text-gray-500">
                      {refreshProgress.sub_total && refreshProgress.sub_total > 0
                        ? `${refreshProgress.sub_current || 0} de ${refreshProgress.sub_total} eventos`
                        : `Passo ${refreshProgress.step} de ${refreshProgress.total_steps}`}
                    </span>
                  </div>
                )}
              </div>
            )}
          </div>
          )}
        </div>
      </div>

      <ConnectionAlert
        avisos={avisos}
        error={error}
        onRetry={() => fetchData(true, true)}
        retrying={refreshing}
      />

      {loadingTooLong && loading && (
        <div className={`rounded-xl p-6 border flex flex-col items-center gap-4 text-center ${isDark ? 'bg-blue-950/40 border-blue-800/50' : 'bg-blue-50 border-blue-200'}`}>
          <RefreshCw className={`w-8 h-8 animate-spin ${isDark ? 'text-blue-400' : 'text-blue-500'}`} />
          <div>
            <p className={`font-semibold text-base ${isDark ? 'text-blue-300' : 'text-blue-700'}`}>Preparando os dados do servidor...</p>
            <p className={`text-sm mt-1 ${isDark ? 'text-blue-400/70' : 'text-blue-600/70'}`}>
              O sistema está consolidando as informações de vendas e ISC. Isso pode levar alguns minutos na primeira carga do dia.
            </p>
          </div>
          <button
            onClick={() => fetchData(true)}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${isDark ? 'bg-blue-800 hover:bg-blue-700 text-blue-100' : 'bg-blue-100 hover:bg-blue-200 text-blue-700'}`}
          >
            Tentar novamente
          </button>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {loading ? (
          <>
            <SkeletonCard />
            <SkeletonCard />
            <SkeletonCard />
            <SkeletonCard />
          </>
        ) : (
          <>
            <div className="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm border border-gray-200 dark:border-gray-700">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-gray-500 dark:text-gray-400">Eventos Ativos</p>
                  <p className="text-3xl font-bold text-gray-900 dark:text-white mt-1">
                    {summary.totalActiveEvents}
                  </p>
                </div>
                <div className="p-3 bg-blue-100 dark:bg-blue-900/30 rounded-lg">
                  <Calendar className="w-6 h-6 text-blue-600 dark:text-blue-400" />
                </div>
              </div>
            </div>

            <div className="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm border border-gray-200 dark:border-gray-700">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-gray-500 dark:text-gray-400">Zona Verde 🟢</p>
                  <p className="text-3xl font-bold text-green-600 dark:text-green-400 mt-1">
                    {summary.eventsGreen}
                  </p>
                  <p className="text-xs text-gray-400 mt-1">ISC {'>'} 1.10 - Acelerando</p>
                </div>
                <div className="p-3 bg-green-100 dark:bg-green-900/30 rounded-lg">
                  <TrendingUp className="w-6 h-6 text-green-600 dark:text-green-400" />
                </div>
              </div>
            </div>

            <div className="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm border border-gray-200 dark:border-gray-700">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-gray-500 dark:text-gray-400">Zona Amarela 🟡</p>
                  <p className="text-3xl font-bold text-yellow-600 dark:text-yellow-400 mt-1">
                    {summary.eventsYellow}
                  </p>
                  <p className="text-xs text-gray-400 mt-1">ISC 0.90-1.10 - Estável</p>
                </div>
                <div className="p-3 bg-yellow-100 dark:bg-yellow-900/30 rounded-lg">
                  <Activity className="w-6 h-6 text-yellow-600 dark:text-yellow-400" />
                </div>
              </div>
            </div>

            <div className="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm border border-gray-200 dark:border-gray-700">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-gray-500 dark:text-gray-400">Zona Vermelha 🔴</p>
                  <p className="text-3xl font-bold text-red-600 dark:text-red-400 mt-1">
                    {summary.eventsRed}
                  </p>
                  <p className="text-xs text-gray-400 mt-1">ISC {'<'} 0.90 - Desacelerando</p>
                </div>
                <div className="p-3 bg-red-100 dark:bg-red-900/30 rounded-lg">
                  <TrendingDown className="w-6 h-6 text-red-600 dark:text-red-400" />
                </div>
              </div>
            </div>
          </>
        )}
      </div>

      <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700">
        {loading ? (
          <SkeletonFilters />
        ) : (
        <div className="p-4 border-b border-gray-200 dark:border-gray-700">
          <div className="flex flex-col lg:flex-row lg:items-center gap-4">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-5 h-5 text-gray-400" />
              <input
                type="text"
                placeholder="Buscar evento..."
                value={searchInput}
                onChange={(e) => setSearchInput(e.target.value)}
                className="w-full pl-10 pr-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
            </div>
            
            <div className="flex items-center gap-3">
              <div className="flex items-center gap-2">
                <Filter className="w-4 h-4 text-gray-400" />
                <select
                  value={categoryFilter}
                  onChange={(e) => setCategoryFilter(e.target.value)}
                  className="px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm"
                >
                  <option value="all">Todas Categorias</option>
                  {categories.map(cat => (
                    <option key={cat} value={cat}>{cat}</option>
                  ))}
                </select>
              </div>

              <select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
                className="px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm"
              >
                <option value="all">Todos</option>
                <option value="active">Ativos</option>
                <option value="closed">Encerrados</option>
              </select>

              <select
                value={zoneFilter}
                onChange={(e) => setZoneFilter(e.target.value)}
                className="px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm"
              >
                <option value="all">Todas Zonas</option>
                <option value="accelerating">🟢 Verde</option>
                <option value="stable">🟡 Amarela</option>
                <option value="decelerating">🔴 Vermelha</option>
              </select>

              <select
                value={dMinusFilter}
                onChange={(e) => setDMinusFilter(e.target.value)}
                className="px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm"
              >
                <option value="all">Todos D-</option>
                <option value="critical">⚠️ D- ≤ 40 (Crítico)</option>
                <option value="41-60">D- 41–60</option>
                <option value="61-90">D- 61–90</option>
                <option value="91-120">D- 91–120</option>
                <option value="120+">D- {'>'} 120</option>
              </select>

              <button
                onClick={() => setOnlyCutoff(v => !v)}
                title="Exibir apenas eventos cujo D- é exatamente 70, 50, 45, 35, 30 ou 15 (pontos de corte do playbook)"
                className={`flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium border transition-colors ${
                  onlyCutoff
                    ? 'bg-purple-600 text-white border-purple-600 dark:bg-purple-500 dark:border-purple-500'
                    : 'bg-white text-purple-700 border-purple-300 hover:bg-purple-50 dark:bg-gray-700 dark:text-purple-300 dark:border-purple-600 dark:hover:bg-purple-900/20'
                }`}
              >
                <BookOpen className="w-4 h-4" />
                Pontos de corte
              </button>

              {hasActiveFilters && (
                <button
                  onClick={clearAllFilters}
                  className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium bg-red-100 text-red-700 hover:bg-red-200 dark:bg-red-900/30 dark:text-red-400 dark:hover:bg-red-900/50 transition-colors"
                >
                  <FilterX className="w-4 h-4" />
                  Limpar filtros
                </button>
              )}
            </div>
          </div>
        </div>
        )}

        {!loading && hasActiveFilters && (
          <div className="px-4 py-2 bg-blue-50 dark:bg-blue-900/20 border-b border-gray-200 dark:border-gray-700 flex items-center justify-between">
            <span className="text-sm text-blue-700 dark:text-blue-300">
              Exibindo {filteredEventos.length} de {eventos.length} eventos
            </span>
          </div>
        )}

        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="bg-gray-50 dark:bg-gray-700/50">
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                  Evento
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                  Data
                </th>
                <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                  <div className="flex items-center justify-center gap-1">
                    D-
                    <div className="group relative">
                      <Info className="w-3 h-3 cursor-help" />
                      <div className="hidden group-hover:block absolute z-10 w-52 p-2 bg-gray-900 text-white text-xs rounded-lg -left-22 top-5">
                        Dias restantes até o fechamento das inscrições
                      </div>
                    </div>
                  </div>
                </th>
                <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                  Vendas / Meta
                </th>
                <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                  Ticket Atual
                </th>
                <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                  <div className="flex items-center justify-center gap-1">
                    ISC
                    <div className="group relative">
                      <Info className="w-3 h-3 cursor-help" />
                      <div className="hidden group-hover:block absolute z-10 w-64 p-2 bg-gray-900 text-white text-xs rounded-lg -left-28 top-5">
                        Índice de Saúde Comercial (ref. ontem): indica se o evento está acelerando (🟢), estável (🟡) ou desacelerando (🔴)
                      </div>
                    </div>
                  </div>
                </th>
                <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                  <div className="flex items-center justify-center gap-1">
                    IA 7/30
                    <div className="group relative">
                      <Info className="w-3 h-3 cursor-help" />
                      <div className="hidden group-hover:block absolute z-10 w-56 p-2 bg-gray-900 text-white text-xs rounded-lg -left-24 top-5">
                        Índice de Aceleração: compara vendas dos últimos 7 dias vs 30 dias
                      </div>
                    </div>
                  </div>
                </th>
                <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                  <div className="flex items-center justify-center gap-1">
                    R14
                    <div className="group relative">
                      <Info className="w-3 h-3 cursor-help" />
                      <div className="hidden group-hover:block absolute z-10 w-56 p-2 bg-gray-900 text-white text-xs rounded-lg -left-24 top-5">
                        Rolling 14 dias: velocidade de vendas dos últimos 14 dias vs esperado
                      </div>
                    </div>
                  </div>
                </th>
                <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                  <div className="flex items-center justify-center gap-1">
                    Curva D-%
                    <div className="group relative">
                      <Info className="w-3 h-3 cursor-help" />
                      <div className="hidden group-hover:block absolute z-10 w-56 p-2 bg-gray-900 text-white text-xs rounded-lg -left-24 top-5">
                        Progresso no Tempo: vendas reais vs esperadas para este momento
                      </div>
                    </div>
                  </div>
                </th>
                <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                  <div className="flex items-center justify-center gap-1">
                    Guia Playbook
                    <div className="group relative">
                      <Info className="w-3 h-3 cursor-help" />
                      <div className="hidden group-hover:block absolute z-10 w-64 p-2 bg-gray-900 text-white text-xs rounded-lg -left-28 top-5">
                        Sinaliza o ponto de corte do playbook — aparece somente quando o D- for exatamente 70, 50, 45, 35, 30 ou 15
                      </div>
                    </div>
                  </div>
                </th>
                <th className="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
              {loading ? (
                <>
                  <SkeletonTableRow />
                  <SkeletonTableRow />
                  <SkeletonTableRow />
                  <SkeletonTableRow />
                  <SkeletonTableRow />
                  <SkeletonTableRow />
                </>
              ) : filteredEventos.length === 0 ? (
                <tr>
                  <td colSpan={12} className="px-4 py-12 text-center text-gray-500 dark:text-gray-400">
                    {eventos.length > 0 ? 'Nenhum evento encontrado com os filtros selecionados.' : 'Nenhum evento encontrado.'}
                  </td>
                </tr>
              ) : filteredEventos.map((event) => (
                <tr 
                  key={event.id}
                  onClick={() => navigate(
                    `/marketing/evento/${event.id}${event.id.startsWith('grp_') ? `?ano=${new Date().getFullYear()}` : ''}`,
                    { state: { previewEvent: event } }
                  )}
                  className={`hover:bg-gray-50 dark:hover:bg-gray-700/50 cursor-pointer transition-colors ${
                    isInCriticalWindow(event.dMinusInscricoes) 
                      ? 'bg-amber-50 dark:bg-amber-900/10 border-l-4 border-l-amber-500' 
                      : ''
                  }`}
                >
                  <td className="px-4 py-4">
                    <div className="flex items-center gap-3">
                      <div>
                        <div className="flex items-center gap-2">
                          <p className="font-medium text-gray-900 dark:text-white" title={event.name}>
                            {event.name}
                          </p>
                        </div>
                        <p className="text-sm text-gray-500 dark:text-gray-400">
                          {event.location}
                        </p>
                      </div>
                      {event.dataRegime === 'consolidated' && (
                        <span className="px-2 py-1 text-xs font-medium bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-400 rounded-full flex items-center gap-1 border border-gray-200 dark:border-gray-600">
                          <Archive className="w-3 h-3" />
                          Consolidado
                        </span>
                      )}
                      {isInCriticalWindow(event.dMinusInscricoes) && (
                        <span className="px-2 py-1 text-xs font-medium bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400 rounded-full flex items-center gap-1">
                          <Target className="w-3 h-3" />
                          JANELA CRÍTICA
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="px-4 py-4 text-sm text-gray-900 dark:text-white">
                    {event.date ? new Date(event.date + 'T00:00:00').toLocaleDateString('pt-BR') : '-'}
                  </td>
                  <td className="px-4 py-4 text-center">
                    <span className={`font-bold ${
                      event.dMinusInscricoes < 40 
                        ? 'text-orange-600 dark:text-orange-400' 
                        : 'text-gray-900 dark:text-white'
                    }`}>
                      D-{event.dMinusInscricoes}
                    </span>
                  </td>
                  <td className="px-4 py-4">
                    <div className="text-center">
                      <p className="text-sm font-medium text-gray-900 dark:text-white">
                        {formatNumber(event.currentSales)} / {formatNumber(event.salesGoal)}
                      </p>
                      <div className="mt-1 w-24 mx-auto bg-gray-200 dark:bg-gray-600 rounded-full h-2">
                        <div 
                          className="bg-blue-600 h-2 rounded-full"
                          style={{ width: `${Math.min((event.currentSales / event.salesGoal) * 100, 100)}%` }}
                        />
                      </div>
                      <p className="text-xs text-gray-500 mt-1">
                        {Math.round((event.currentSales / event.salesGoal) * 100)}%
                      </p>
                    </div>
                  </td>
                  <td className="px-4 py-4 text-center text-sm font-medium text-gray-900 dark:text-white">
                    {event.ticketAtual && event.ticketAtual > 0 ? (
                      <span
                        className="inline-flex items-center gap-1"
                        title={event.ticketKitNome ? `Kit: ${event.ticketKitNome}` : undefined}
                      >
                        {formatCurrency(event.ticketAtual)}
                        {event.ticketKitNome && (
                          <Info className="w-3.5 h-3.5 text-gray-400 dark:text-gray-500 flex-shrink-0" />
                        )}
                      </span>
                    ) : '—'}
                  </td>
                  <td className="px-4 py-4 text-center">
                    <div className="flex items-center justify-center gap-2">
                      <span 
                        className="text-lg font-bold"
                        style={{ color: getISCColor(event.iscStatus) }}
                      >
                        {getISCEmoji(event.iscStatus)} {event.isc.toFixed(2)}
                      </span>
                    </div>
                  </td>
                  <td className="px-4 py-4 text-center text-sm text-gray-900 dark:text-white">
                    {event.iscComponents.ia730.toFixed(2)}
                  </td>
                  <td className="px-4 py-4 text-center text-sm text-gray-900 dark:text-white">
                    {event.iscComponents.rolling14d.toFixed(2)}
                  </td>
                  <td className="px-4 py-4 text-center text-sm text-gray-900 dark:text-white">
                    {event.iscComponents.curvaDPercent.toFixed(2)}
                  </td>
                  <td className="px-4 py-4 text-center">
                    {(() => {
                      const cutoff = getCutoffAlert(event.dMinusInscricoes);
                      if (!cutoff || !event.suggestedAction) return <span className="text-xs text-gray-300 dark:text-gray-600">—</span>;
                      const dotColor = event.suggestedAction.iscState === 'forte'
                        ? 'bg-green-500'
                        : event.suggestedAction.iscState === 'estável'
                        ? 'bg-yellow-500'
                        : 'bg-red-500';
                      return (
                        <span
                          className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-gray-100 dark:bg-gray-700 border border-gray-200 dark:border-gray-600 text-xs font-mono font-semibold text-gray-700 dark:text-gray-300"
                          title={`${cutoff.label} · ${event.suggestedAction.letter} — ${event.suggestedAction.name}`}
                        >
                          <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${dotColor}`} />
                          {event.suggestedAction.letter}
                        </span>
                      );
                    })()}
                  </td>
                  <td className="px-4 py-4">
                    <ChevronRight className="w-5 h-5 text-gray-400" />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

      </div>

      <div className="bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-xl p-4">
        <div className="flex items-start gap-3">
          <AlertTriangle className="w-5 h-5 text-amber-600 dark:text-amber-400 mt-0.5" />
          <div>
            <h3 className="font-medium text-amber-800 dark:text-amber-300">
              Regra D-40: Janela de Promoção
            </h3>
            <p className="text-sm text-amber-700 dark:text-amber-400 mt-1">
              D-40 é a última janela para promoções. Diagnóstico até D-45, ação até D-40. 
              <strong> Após D-40, NUNCA fazer promoção</strong> - apenas ajustes de comunicação ou preço para cima.
            </p>
          </div>
        </div>
      </div>
      </div>
    </div>
  );
};

export default MarketingDashboard;
