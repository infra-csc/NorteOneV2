import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { 
  TrendingUp, 
  TrendingDown, 
  Activity, 
  Calendar,
  Search,
  Filter,
  DollarSign,
  Target,
  ChevronRight,
  Info,
  RefreshCw,
  Loader2,
  Clock,
  Zap,
  AlertTriangle,
  CheckCircle,
  ArrowUpRight,
  ArrowDownRight,
  Minus
} from 'lucide-react';
import { pricingService, PricingEvent, PricingSummary } from '../../services/api';
import { useTheme } from '../../context/ThemeContext';
import { getISCColor } from '../../types/marketingPerformance';

const PricingAnalysis: React.FC = () => {
  const navigate = useNavigate();
  const { isDark } = useTheme();
  const [searchInput, setSearchInput] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('all');
  const [statusFilter, setStatusFilter] = useState('active');
  
  const [eventos, setEventos] = useState<PricingEvent[]>([]);
  const [summary, setSummary] = useState<PricingSummary>({
    totalEvents: 0,
    eventsToIncrease: 0,
    eventsToMaintain: 0,
    eventsToDecrease: 0
  });
  const [categories, setCategories] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null);
  const [expandedEvent, setExpandedEvent] = useState<string | null>(null);
  const [avisos, setAvisos] = useState<string[]>([]);

  const abortControllerRef = useRef<AbortController | null>(null);

  const fetchData = useCallback(async (isRefresh = false) => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    const controller = new AbortController();
    abortControllerRef.current = controller;

    try {
      if (isRefresh) {
        setRefreshing(true);
      } else {
        setLoading(true);
      }
      setError(null);
      
      const response = await pricingService.getAnalysis({
        ano: new Date().getFullYear(),
        status: statusFilter === 'all' ? undefined : statusFilter,
        categoria: categoryFilter === 'all' ? undefined : categoryFilter,
        busca: debouncedSearch || undefined
      }, controller.signal);
      
      if (!controller.signal.aborted) {
        setEventos(response.eventos);
        setSummary(response.resumo);
        setCategories(response.categorias);
        setLastUpdate(new Date(response.ultima_atualizacao));
        setAvisos((response as any).avisos || []);
      }
    } catch (err: any) {
      if (err?.name === 'CanceledError' || err?.code === 'ERR_CANCELED') {
        return;
      }
      console.error('Erro ao carregar dados:', err);
      setError('Erro ao carregar dados. Tente novamente.');
    } finally {
      if (!controller.signal.aborted) {
        setLoading(false);
        setRefreshing(false);
      }
    }
  }, [statusFilter, categoryFilter, debouncedSearch]);

  useEffect(() => {
    fetchData();
    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, [fetchData]);

  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(searchInput);
    }, 500);
    return () => clearTimeout(timer);
  }, [searchInput]);

  const getDecisionColor = (action: string): string => {
    switch (action) {
      case 'increase_now': return '#22c55e';
      case 'increase_gradual': return '#84cc16';
      case 'maintain': return '#eab308';
      case 'decrease': return '#ef4444';
      default: return '#6b7280';
    }
  };

  const getDecisionLabel = (action: string): string => {
    switch (action) {
      case 'increase_now': return 'Subir Agora';
      case 'increase_gradual': return 'Subir Gradual';
      case 'maintain': return 'Manter';
      case 'decrease': return 'Reduzir';
      default: return action;
    }
  };

  const getDecisionIcon = (action: string) => {
    switch (action) {
      case 'increase_now': return <ArrowUpRight className="w-4 h-4" />;
      case 'increase_gradual': return <TrendingUp className="w-4 h-4" />;
      case 'maintain': return <Minus className="w-4 h-4" />;
      case 'decrease': return <ArrowDownRight className="w-4 h-4" />;
      default: return <Activity className="w-4 h-4" />;
    }
  };

  const formatCurrency = (value: number): string => {
    return new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(value);
  };

  const formatNumber = (value: number): string => {
    return new Intl.NumberFormat('pt-BR').format(value);
  };

  const bgColor = isDark ? 'bg-gray-900' : 'bg-gray-50';
  const cardBg = isDark ? 'bg-gray-800' : 'bg-white';
  const textColor = isDark ? 'text-white' : 'text-gray-900';
  const textMuted = isDark ? 'text-gray-400' : 'text-gray-500';
  const borderColor = isDark ? 'border-gray-700' : 'border-gray-200';

  return (
    <div className={`min-h-screen ${bgColor} p-6`}>
      <div className="max-w-7xl mx-auto">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className={`text-2xl font-bold ${textColor}`}>Analise de Pricing</h1>
            <p className={textMuted}>Decisao de preco baseada em Rolling Index, IED e elasticidade</p>
          </div>
          <div className="flex items-center gap-4">
            {lastUpdate && (
              <span className={`text-sm ${textMuted} flex items-center gap-1`}>
                <Clock className="w-4 h-4" />
                Atualizado: {lastUpdate.toLocaleTimeString('pt-BR')}
              </span>
            )}
            <button
              onClick={() => fetchData(true)}
              disabled={refreshing || loading}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg ${cardBg} ${borderColor} border hover:bg-opacity-80 transition-colors`}
            >
              <RefreshCw className={`w-4 h-4 ${(refreshing || loading) ? 'animate-spin' : ''}`} />
              {loading ? 'Carregando...' : 'Atualizar'}
            </button>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
          <div className={`${cardBg} rounded-xl p-4 border ${borderColor}`}>
            <div className="flex items-center justify-between">
              <span className={textMuted}>Eventos Ativos</span>
              <Activity className="w-5 h-5 text-blue-500" />
            </div>
            <p className={`text-2xl font-bold mt-2 ${textColor}`}>{loading ? '-' : summary.totalEvents}</p>
          </div>
          <div className={`${cardBg} rounded-xl p-4 border ${borderColor}`}>
            <div className="flex items-center justify-between">
              <span className={textMuted}>Subir Preco</span>
              <ArrowUpRight className="w-5 h-5 text-green-500" />
            </div>
            <p className="text-2xl font-bold mt-2 text-green-500">{loading ? '-' : summary.eventsToIncrease}</p>
          </div>
          <div className={`${cardBg} rounded-xl p-4 border ${borderColor}`}>
            <div className="flex items-center justify-between">
              <span className={textMuted}>Manter Preco</span>
              <Minus className="w-5 h-5 text-yellow-500" />
            </div>
            <p className="text-2xl font-bold mt-2 text-yellow-500">{loading ? '-' : summary.eventsToMaintain}</p>
          </div>
          <div className={`${cardBg} rounded-xl p-4 border ${borderColor}`}>
            <div className="flex items-center justify-between">
              <span className={textMuted}>Reduzir Preco</span>
              <ArrowDownRight className="w-5 h-5 text-red-500" />
            </div>
            <p className="text-2xl font-bold mt-2 text-red-500">{loading ? '-' : summary.eventsToDecrease}</p>
          </div>
        </div>

        <div className={`${cardBg} rounded-xl p-4 border ${borderColor} mb-6`}>
          <div className="flex flex-wrap gap-4">
            <div className="flex-1 min-w-[200px]">
              <div className="relative">
                <Search className={`absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 ${textMuted}`} />
                <input
                  type="text"
                  placeholder="Buscar evento..."
                  value={searchInput}
                  onChange={(e) => setSearchInput(e.target.value)}
                  className={`w-full pl-10 pr-4 py-2 rounded-lg border ${borderColor} ${cardBg} ${textColor} focus:outline-none focus:ring-2 focus:ring-blue-500`}
                />
              </div>
            </div>
            <select
              value={categoryFilter}
              onChange={(e) => setCategoryFilter(e.target.value)}
              className={`px-4 py-2 rounded-lg border ${borderColor} ${cardBg} ${textColor}`}
            >
              <option value="all">Todas Categorias</option>
              {categories.map(cat => (
                <option key={cat} value={cat}>{cat}</option>
              ))}
            </select>
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className={`px-4 py-2 rounded-lg border ${borderColor} ${cardBg} ${textColor}`}
            >
              <option value="active">Ativos</option>
              <option value="closed">Encerrados</option>
              <option value="all">Todos</option>
            </select>
          </div>
        </div>

        {error && (
          <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded-lg mb-6">
            {error}
          </div>
        )}

        {avisos.length > 0 && (
          <div className="mb-4 rounded-lg border border-yellow-500/30 bg-yellow-500/10 p-4">
            <div className="flex items-start gap-2">
              <span className="text-yellow-500 text-lg">⚠️</span>
              <div>
                <p className="font-semibold text-yellow-500">Atenção: Dados Parciais</p>
                {avisos.map((aviso, index) => (
                  <p key={index} className="text-sm text-yellow-400/80 mt-1">{aviso}</p>
                ))}
              </div>
            </div>
          </div>
        )}

        {loading ? (
          <div className={`${cardBg} rounded-xl border ${borderColor} p-12 text-center`}>
            <Loader2 className={`w-8 h-8 animate-spin mx-auto ${textMuted}`} />
            <p className={`mt-3 ${textMuted}`}>Carregando eventos...</p>
          </div>
        ) : (
        <div className="space-y-4">
          {eventos.map((evento) => (
            <div
              key={evento.id}
              className={`${cardBg} rounded-xl border ${borderColor} overflow-hidden`}
            >
              <div 
                className="p-4 cursor-pointer hover:bg-opacity-80 transition-colors"
                onClick={() => setExpandedEvent(expandedEvent === evento.id ? null : evento.id)}
              >
                <div className="flex items-center justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-3">
                      <div 
                        className="w-3 h-3 rounded-full"
                        style={{ backgroundColor: getDecisionColor(evento.decision.action) }}
                      />
                      <h3 className={`font-semibold ${textColor}`}>{evento.name}</h3>
                      <span className={`text-sm ${textMuted}`}>D-{evento.dMinus}</span>
                      <span 
                        className="px-2 py-0.5 rounded-full text-xs font-medium text-white flex items-center gap-1"
                        style={{ backgroundColor: getDecisionColor(evento.decision.action) }}
                      >
                        {getDecisionIcon(evento.decision.action)}
                        {getDecisionLabel(evento.decision.action)}
                      </span>
                    </div>
                    <div className={`flex items-center gap-4 mt-2 text-sm ${textMuted}`}>
                      <span>{evento.category}</span>
                      <span>{evento.location}</span>
                      <span>{formatNumber(evento.currentSales)} / {formatNumber(evento.salesGoal)} vendas</span>
                    </div>
                  </div>
                  <div className="flex items-center gap-6">
                    <div className="text-center">
                      <p className={`text-xs ${textMuted}`}>Rolling Index</p>
                      <p className={`text-lg font-bold ${evento.pricingMetrics.rollingIndex > 1.2 ? 'text-green-500' : evento.pricingMetrics.rollingIndex < 0.8 ? 'text-red-500' : 'text-yellow-500'}`}>
                        {evento.pricingMetrics.rollingIndex.toFixed(2)}
                      </p>
                    </div>
                    <div className="text-center">
                      <p className={`text-xs ${textMuted}`}>IED</p>
                      <p className={`text-lg font-bold ${evento.pricingMetrics.ied > 1.1 ? 'text-green-500' : evento.pricingMetrics.ied < 0.9 ? 'text-red-500' : 'text-yellow-500'}`}>
                        {evento.pricingMetrics.ied.toFixed(2)}
                      </p>
                    </div>
                    <div className="text-center">
                      <p className={`text-xs ${textMuted}`}>IA</p>
                      <p className={`text-lg font-bold ${evento.pricingMetrics.ia > 1.2 ? 'text-green-500' : evento.pricingMetrics.ia < 0.9 ? 'text-red-500' : 'text-yellow-500'}`}>
                        {evento.pricingMetrics.ia.toFixed(2)}
                      </p>
                    </div>
                    <ChevronRight className={`w-5 h-5 ${textMuted} transition-transform ${expandedEvent === evento.id ? 'rotate-90' : ''}`} />
                  </div>
                </div>
              </div>

              {expandedEvent === evento.id && (
                <div className={`border-t ${borderColor} p-4`}>
                  <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                    <div>
                      <h4 className={`font-semibold mb-3 ${textColor} flex items-center gap-2`}>
                        <Target className="w-4 h-4" />
                        Metricas de Pricing
                      </h4>
                      <div className="grid grid-cols-2 gap-3">
                        <div className={`p-3 rounded-lg ${isDark ? 'bg-gray-700' : 'bg-gray-100'}`}>
                          <p className={`text-xs ${textMuted}`}>Rolling 14d</p>
                          <p className={`font-bold ${textColor}`}>{evento.pricingMetrics.rollingAvg14d.toFixed(1)} vendas/dia</p>
                          {evento.pricingMetrics.rollingAvg14dLastYear > 0 && (
                            <p className={`text-xs ${textMuted}`}>Ano ant: {evento.pricingMetrics.rollingAvg14dLastYear.toFixed(1)}/dia</p>
                          )}
                        </div>
                        <div className={`p-3 rounded-lg ${isDark ? 'bg-gray-700' : 'bg-gray-100'}`}>
                          <p className={`text-xs ${textMuted}`}>Pace Necessario</p>
                          <p className={`font-bold ${textColor}`}>{evento.pricingMetrics.paceRequired.toFixed(1)} vendas/dia</p>
                        </div>
                        <div className={`p-3 rounded-lg ${isDark ? 'bg-gray-700' : 'bg-gray-100'}`}>
                          <p className={`text-xs ${textMuted}`}>Projecao</p>
                          <p className={`font-bold ${textColor}`}>{formatNumber(evento.pricingMetrics.projection)}</p>
                        </div>
                        <div className={`p-3 rounded-lg ${isDark ? 'bg-gray-700' : 'bg-gray-100'}`}>
                          <p className={`text-xs ${textMuted}`}>Pace de Seguranca</p>
                          <p className={`font-bold ${textColor}`}>{evento.pricingMetrics.paceSeguranca.toFixed(1)} vendas/dia</p>
                        </div>
                        <div className={`p-3 rounded-lg ${isDark ? 'bg-gray-700' : 'bg-gray-100'}`}>
                          <p className={`text-xs ${textMuted}`}>Ticket Medio</p>
                          <p className={`font-bold ${textColor}`}>{formatCurrency(evento.averageTicket)}</p>
                        </div>
                        <div className={`p-3 rounded-lg ${isDark ? 'bg-gray-700' : 'bg-gray-100'}`}>
                          <p className={`text-xs ${textMuted}`}>Custo Kit</p>
                          <p className={`font-bold ${textColor}`}>{formatCurrency(evento.kitCost)}</p>
                        </div>
                      </div>
                    </div>

                    <div>
                      <h4 className={`font-semibold mb-3 ${textColor} flex items-center gap-2`}>
                        <DollarSign className="w-4 h-4" />
                        Simulador de Elasticidade
                      </h4>
                      <div className="overflow-x-auto">
                        <table className="w-full text-sm">
                          <thead>
                            <tr className={textMuted}>
                              <th className="text-left py-2">Aumento</th>
                              <th className="text-right py-2">Novo Preco</th>
                              <th className="text-right py-2">Nova Margem</th>
                              <th className="text-right py-2">Queda Aceitavel</th>
                              <th className="text-right py-2">Pace Min</th>
                            </tr>
                          </thead>
                          <tbody>
                            {evento.elasticityScenarios.map((scenario, idx) => (
                              <tr key={idx} className={`border-t ${borderColor}`}>
                                <td className={`py-2 ${textColor} font-medium`}>+{scenario.priceIncrease}%</td>
                                <td className={`py-2 text-right ${textColor}`}>{formatCurrency(scenario.newPrice)}</td>
                                <td className="py-2 text-right text-green-500">{formatCurrency(scenario.newMargin)}</td>
                                <td className="py-2 text-right text-yellow-500">{scenario.acceptableVolumeDrop.toFixed(1)}%</td>
                                <td className={`py-2 text-right ${textColor}`}>{scenario.minPace.toFixed(1)}/dia</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  </div>

                  <div className={`mt-4 p-4 rounded-lg ${isDark ? 'bg-gray-700' : 'bg-blue-50'}`}>
                    <div className="flex items-start gap-3">
                      <Info className="w-5 h-5 text-blue-500 flex-shrink-0 mt-0.5" />
                      <div>
                        <p className={`font-semibold ${textColor}`}>Recomendacao: {getDecisionLabel(evento.decision.action)}</p>
                        <p className={`text-sm ${textMuted} mt-1`}>{evento.decision.reason}</p>
                        <p className={`text-xs ${textMuted} mt-2`}>
                          Confianca: {evento.decision.confidence === 'high' ? 'Alta' : evento.decision.confidence === 'medium' ? 'Media' : 'Baixa'}
                        </p>
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </div>
          ))}

          {eventos.length === 0 && !loading && (
            <div className={`${cardBg} rounded-xl p-8 text-center border ${borderColor}`}>
              <AlertTriangle className={`w-12 h-12 mx-auto ${textMuted} mb-4`} />
              <p className={textColor}>Nenhum evento encontrado com os filtros selecionados.</p>
            </div>
          )}
        </div>
        )}
      </div>
    </div>
  );
};

export default PricingAnalysis;
