import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { 
  TrendingUp, 
  TrendingDown, 
  Activity, 
  Calendar,
  Search,
  Filter,
  AlertTriangle,
  Target,
  ChevronRight,
  Info,
  RefreshCw,
  Loader2,
  Clock
} from 'lucide-react';
import { 
  getISCColor, 
  getISCEmoji, 
  isInCriticalWindow 
} from '../../types/marketingPerformance';
import { marketingService, MarketingEvent, MarketingDashboardSummary } from '../../services/api';

const MarketingDashboard: React.FC = () => {
  const navigate = useNavigate();
  const [search, setSearch] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('all');
  const [statusFilter, setStatusFilter] = useState('active');
  
  const [eventos, setEventos] = useState<MarketingEvent[]>([]);
  const [summary, setSummary] = useState<MarketingDashboardSummary>({
    totalActiveEvents: 0,
    eventsGreen: 0,
    eventsYellow: 0,
    eventsRed: 0
  });
  const [categories, setCategories] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null);
  
  const autoRefreshRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const AUTO_REFRESH_INTERVAL = 5 * 60 * 1000;

  const fetchData = useCallback(async (isRefresh = false) => {
    try {
      if (isRefresh) {
        setRefreshing(true);
      } else {
        setLoading(true);
      }
      setError(null);
      
      const response = await marketingService.getEventos({
        ano: new Date().getFullYear(),
        status: statusFilter === 'all' ? undefined : statusFilter,
        categoria: categoryFilter === 'all' ? undefined : categoryFilter,
        busca: search || undefined
      });
      
      setEventos(response.eventos);
      setSummary(response.resumo);
      setCategories(response.categorias);
      setLastUpdate(new Date(response.ultima_atualizacao));
    } catch (err) {
      console.error('Erro ao carregar dados:', err);
      setError('Erro ao carregar dados. Tente novamente.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [statusFilter, categoryFilter, search]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

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

  const handleManualRefresh = () => {
    fetchData(true);
  };

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
    const now = new Date();
    const isToday = date.getDate() === now.getDate() &&
                    date.getMonth() === now.getMonth() &&
                    date.getFullYear() === now.getFullYear();
    
    if (isToday) {
      return date.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
    }
    return date.toLocaleDateString('pt-BR', { 
      day: '2-digit', 
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit', 
      minute: '2-digit' 
    });
  };

  const getActionChipStyle = (isc: number, dMinus: number) => {
    if (isc > 1.10) {
      return 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400';
    }
    if (isc >= 0.90) {
      return 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400';
    }
    if (dMinus < 40) {
      return 'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-400';
    }
    return 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400';
  };

  const getActionText = (isc: number, dMinus: number) => {
    if (isc > 1.10) return 'Subir Preço';
    if (isc >= 0.90) return 'Monitorar';
    if (dMinus < 40) return 'Só Comunicação';
    return 'Ação Promocional';
  };

  if (loading) {
    return (
      <div className="p-6 flex items-center justify-center min-h-[400px]">
        <div className="flex flex-col items-center gap-3">
          <Loader2 className="w-8 h-8 text-blue-500 animate-spin" />
          <p className="text-gray-500 dark:text-gray-400">Carregando dados de marketing...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6">
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
            Marketing Performance
          </h1>
          <p className="text-gray-500 dark:text-gray-400 mt-1">
            Acompanhamento de vendas e ISC dos eventos
          </p>
        </div>
        
        <div className="flex items-center gap-3">
          {lastUpdate && (
            <div className="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400">
              <Clock className="w-4 h-4" />
              <span>Atualizado às {formatLastUpdate(lastUpdate)}</span>
            </div>
          )}
          <button
            onClick={handleManualRefresh}
            disabled={refreshing}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg bg-blue-100 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400 hover:bg-blue-200 dark:hover:bg-blue-900/50 transition-colors ${refreshing ? 'opacity-50 cursor-not-allowed' : ''}`}
          >
            <RefreshCw className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''}`} />
            <span className="text-sm font-medium">{refreshing ? 'Atualizando...' : 'Atualizar'}</span>
          </button>
        </div>
      </div>

      {error && (
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-xl p-4">
          <p className="text-red-600 dark:text-red-400">{error}</p>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
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
      </div>

      <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700">
        <div className="p-4 border-b border-gray-200 dark:border-gray-700">
          <div className="flex flex-col lg:flex-row lg:items-center gap-4">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-5 h-5 text-gray-400" />
              <input
                type="text"
                placeholder="Buscar evento..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
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
            </div>
          </div>
        </div>

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
                      <div className="hidden group-hover:block absolute z-10 w-48 p-2 bg-gray-900 text-white text-xs rounded-lg -left-20 top-5">
                        Dias restantes até o evento
                      </div>
                    </div>
                  </div>
                </th>
                <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                  Vendas / Meta
                </th>
                <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                  <div className="flex items-center justify-center gap-1">
                    ISC
                    <div className="group relative">
                      <Info className="w-3 h-3 cursor-help" />
                      <div className="hidden group-hover:block absolute z-10 w-64 p-2 bg-gray-900 text-white text-xs rounded-lg -left-28 top-5">
                        Índice de Saúde Comercial: indica se o evento está acelerando (🟢), estável (🟡) ou desacelerando (🔴)
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
                  Ação Sugerida
                </th>
                <th className="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
              {eventos.map((event) => (
                <tr 
                  key={event.id}
                  onClick={() => navigate(`/marketing/evento/${event.id}`)}
                  className={`hover:bg-gray-50 dark:hover:bg-gray-700/50 cursor-pointer transition-colors ${
                    isInCriticalWindow(event.dMinus) 
                      ? 'bg-amber-50 dark:bg-amber-900/10 border-l-4 border-l-amber-500' 
                      : ''
                  }`}
                >
                  <td className="px-4 py-4">
                    <div className="flex items-center gap-3">
                      <div>
                        <p className="font-medium text-gray-900 dark:text-white">
                          {event.name}
                        </p>
                        <p className="text-sm text-gray-500 dark:text-gray-400">
                          {event.location}
                        </p>
                      </div>
                      {isInCriticalWindow(event.dMinus) && (
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
                      event.dMinus < 40 
                        ? 'text-orange-600 dark:text-orange-400' 
                        : 'text-gray-900 dark:text-white'
                    }`}>
                      D-{event.dMinus}
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
                    {event.iscComponents.curvaDPercent.toFixed(2)}
                  </td>
                  <td className="px-4 py-4 text-center">
                    <span className={`px-3 py-1 text-xs font-medium rounded-full ${getActionChipStyle(event.isc, event.dMinus)}`}>
                      {getActionText(event.isc, event.dMinus)}
                    </span>
                  </td>
                  <td className="px-4 py-4">
                    <ChevronRight className="w-5 h-5 text-gray-400" />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {eventos.length === 0 && !loading && (
          <div className="p-8 text-center">
            <p className="text-gray-500 dark:text-gray-400">
              Nenhum evento encontrado com os filtros selecionados.
            </p>
          </div>
        )}
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
  );
};

export default MarketingDashboard;
