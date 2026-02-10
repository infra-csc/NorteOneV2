import React, { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate, useSearchParams, Link } from 'react-router-dom';
import { 
  ArrowLeft, 
  Calendar, 
  MapPin, 
  Users, 
  DollarSign,
  TrendingUp,
  TrendingDown,
  Activity,
  Target,
  AlertTriangle,
  Clock,
  CheckCircle,
  Info,
  Loader2,
  Plus,
  X,
  Trash2
} from 'lucide-react';
import { 
  LineChart, 
  Line, 
  BarChart, 
  Bar, 
  XAxis, 
  YAxis, 
  CartesianGrid, 
  Tooltip, 
  Legend, 
  ResponsiveContainer,
  ReferenceLine
} from 'recharts';
import { marketingService, MarketingEvent } from '../../services/api';
import { 
  getISCColor, 
  getISCEmoji, 
  isInCriticalWindow,
  getISCStatus
} from '../../types/marketingPerformance';
import { useTheme } from '../../context/ThemeContext';

interface CommercialAction {
  id: string;
  type: 'price_increase' | 'price_decrease' | 'promotion' | 'campaign' | 'communication';
  description: string;
  date: string;
  impact?: string;
  vendas_antes?: number;
  vendas_depois?: number;
  impacto_percentual?: number;
  status_impacto?: string;
}

interface ExtendedEvent extends MarketingEvent {
  dailySales?: { date: string; sales: number; expected: number; cumulativeSales?: number; cumulativeExpected?: number }[];
  commercialActions?: CommercialAction[];
}

const EventDetail: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { isDark } = useTheme();
  const anoParam = searchParams.get('ano') ? parseInt(searchParams.get('ano')!) : undefined;
  const [event, setEvent] = useState<ExtendedEvent | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showActionModal, setShowActionModal] = useState(false);
  const [actionForm, setActionForm] = useState({
    tipo: 'PROMOCAO',
    descricao: '',
    data_acao: new Date().toISOString().split('T')[0],
    projeto_id_selecionado: 0
  });
  const [savingAction, setSavingAction] = useState(false);
  const [projetosVinculados, setProjetosVinculados] = useState<{id: number; nome: string; sku: string}[]>([]);
  const [comparacaoAnual, setComparacaoAnual] = useState<any>(null);
  const [anosDisponiveis, setAnosDisponiveis] = useState<number[]>([]);
  const [avisos, setAvisos] = useState<string[]>([]);

  const isConsolidated = id?.startsWith('grp_') ?? false;
  const abortControllerRef = useRef<AbortController | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    abortControllerRef.current = controller;

    const fetchEvent = async () => {
      if (!id) {
        setError('ID do evento não fornecido');
        setLoading(false);
        return;
      }
      
      try {
        setLoading(true);
        const response = await marketingService.getEventoById(id, controller.signal, anoParam);
        if (controller.signal.aborted) return;
        const eventWithData = {
          ...response.evento,
          dailySales: response.dailySales?.map(d => ({
            date: d.date,
            sales: d.sales,
            expected: d.expected,
            cumulativeSales: d.cumulativeSales,
            cumulativeExpected: d.cumulativeExpected
          })),
          commercialActions: response.commercialActions?.map((a: any) => ({
            id: a.id,
            type: a.type as 'price_increase' | 'price_decrease' | 'promotion' | 'campaign' | 'communication',
            description: a.description,
            date: a.date,
            impact: a.impact,
            vendas_antes: a.vendas_antes,
            vendas_depois: a.vendas_depois,
            impacto_percentual: a.impacto_percentual,
            status_impacto: a.status_impacto
          }))
        };
        setEvent(eventWithData);
        if ((response as any).projetos_vinculados) {
          setProjetosVinculados((response as any).projetos_vinculados);
        }
        if ((response as any).comparacao_anual) {
          setComparacaoAnual((response as any).comparacao_anual);
        } else {
          setComparacaoAnual(null);
        }
        if ((response as any).anos_disponiveis) {
          setAnosDisponiveis((response as any).anos_disponiveis);
        }
        setAvisos((response as any).avisos || []);
        setError(null);
      } catch (err: any) {
        if (err?.name === 'CanceledError' || err?.code === 'ERR_CANCELED') return;
        console.error('Erro ao carregar evento:', err);
        setError('Erro ao carregar dados do evento');
      } finally {
        if (!controller.signal.aborted) {
          setLoading(false);
        }
      }
    };
    
    fetchEvent();
    return () => { controller.abort(); };
  }, [id, anoParam]);

  if (loading || !event) {
    return (
      <div className="p-6">
        <div className="flex items-center gap-2 mb-6">
          <button
            onClick={() => navigate('/marketing')}
            className="flex items-center gap-2 text-blue-600 dark:text-blue-400 hover:underline"
          >
            <ArrowLeft className="w-5 h-5" />
            Voltar ao Dashboard
          </button>
        </div>
        {error ? (
          <div className="bg-white dark:bg-gray-800 rounded-xl p-8 text-center">
            <p className="text-gray-500 dark:text-gray-400">{error}</p>
            <button
              onClick={() => navigate('/marketing')}
              className="mt-4 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
            >
              Voltar ao Dashboard
            </button>
          </div>
        ) : (
          <div className="bg-white dark:bg-gray-800 rounded-xl p-12 flex flex-col items-center justify-center">
            <Loader2 className="w-8 h-8 animate-spin text-blue-600" />
            <p className="mt-4 text-gray-500 dark:text-gray-400">Carregando dados do evento...</p>
          </div>
        )}
      </div>
    );
  }

  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat('pt-BR', {
      style: 'currency',
      currency: 'BRL'
    }).format(value);
  };

  const formatNumber = (value: number) => {
    return new Intl.NumberFormat('pt-BR').format(value);
  };

  const handleSaveAction = async () => {
    if (!id || !actionForm.descricao.trim()) return;
    
    let projetoIdParaAcao: number | null;
    if (isConsolidated) {
      projetoIdParaAcao = actionForm.projeto_id_selecionado > 0 
        ? actionForm.projeto_id_selecionado 
        : (projetosVinculados.length > 0 ? projetosVinculados[0].id : null);
    } else {
      projetoIdParaAcao = parseInt(id);
    }
    
    if (!projetoIdParaAcao) return;
    
    setSavingAction(true);
    try {
      await marketingService.createAcaoComercial({
        projeto_id: projetoIdParaAcao,
        tipo: actionForm.tipo,
        descricao: actionForm.descricao,
        data_acao: actionForm.data_acao
      });
      
      const response = await marketingService.getEventoById(id, abortControllerRef.current?.signal, anoParam);
      const eventWithData = {
        ...response.evento,
        dailySales: response.dailySales?.map(d => ({
          date: d.date,
          sales: d.sales,
          expected: d.expected,
          cumulativeSales: d.cumulativeSales,
          cumulativeExpected: d.cumulativeExpected
        })),
        commercialActions: response.commercialActions?.map((a: any) => ({
          id: a.id,
          type: a.type as 'price_increase' | 'price_decrease' | 'promotion' | 'campaign' | 'communication',
          description: a.description,
          date: a.date,
          impact: a.impact,
          vendas_antes: a.vendas_antes,
          vendas_depois: a.vendas_depois,
          impacto_percentual: a.impacto_percentual,
          status_impacto: a.status_impacto
        }))
      };
      setEvent(eventWithData);
      
      setShowActionModal(false);
      setActionForm({
        tipo: 'PROMOCAO',
        descricao: '',
        data_acao: new Date().toISOString().split('T')[0],
        projeto_id_selecionado: 0
      });
    } catch (err: any) {
      if (err?.name === 'CanceledError' || err?.code === 'ERR_CANCELED') return;
      console.error('Erro ao salvar ação:', err);
    } finally {
      setSavingAction(false);
    }
  };

  const handleDeleteAction = async (actionId: string) => {
    if (!id) return;
    try {
      await marketingService.deleteAcaoComercial(parseInt(actionId));
      const response = await marketingService.getEventoById(id, abortControllerRef.current?.signal, anoParam);
      const eventWithData = {
        ...response.evento,
        dailySales: response.dailySales?.map(d => ({
          date: d.date,
          sales: d.sales,
          expected: d.expected,
          cumulativeSales: d.cumulativeSales,
          cumulativeExpected: d.cumulativeExpected
        })),
        commercialActions: response.commercialActions?.map((a: any) => ({
          id: a.id,
          type: a.type as 'price_increase' | 'price_decrease' | 'promotion' | 'campaign' | 'communication',
          description: a.description,
          date: a.date,
          impact: a.impact,
          vendas_antes: a.vendas_antes,
          vendas_depois: a.vendas_depois,
          impacto_percentual: a.impacto_percentual,
          status_impacto: a.status_impacto
        }))
      };
      setEvent(eventWithData);
    } catch (err) {
      console.error('Erro ao excluir ação:', err);
    }
  };

  const tipoOptions = [
    { value: 'AUMENTO_PRECO', label: 'Aumento de Preço' },
    { value: 'REDUCAO_PRECO', label: 'Redução de Preço' },
    { value: 'PROMOCAO', label: 'Promoção/Desconto' },
    { value: 'CAMPANHA', label: 'Campanha de Marketing' },
    { value: 'COMUNICACAO', label: 'Comunicação/Email' }
  ];

  const cumulativeData = (event.dailySales || []).reduce((acc, day, index) => {
    const prevCumulative = index > 0 ? acc[index - 1].cumulative : 0;
    const prevExpected = index > 0 ? acc[index - 1].cumulativeExpected : 0;
    
    acc.push({
      date: day.date,
      cumulative: prevCumulative + day.sales,
      cumulativeExpected: prevExpected + day.expected,
      daily: day.sales
    });
    
    return acc;
  }, [] as { date: string; cumulative: number; cumulativeExpected: number; daily: number }[]);

  const last30Days = (event.dailySales || []).slice(-30);

  const getRecommendationStyle = () => {
    if (event.iscStatus === 'accelerating') {
      return 'bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-800';
    }
    if (event.iscStatus === 'stable') {
      return 'bg-yellow-50 dark:bg-yellow-900/20 border-yellow-200 dark:border-yellow-800';
    }
    if (event.dMinus <= 40) {
      return 'bg-orange-50 dark:bg-orange-900/20 border-orange-200 dark:border-orange-800';
    }
    return 'bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800';
  };

  const gaugeRotation = Math.min(Math.max((event.isc - 0.5) * 180, 0), 180);

  return (
    <div className="min-h-screen">
      <div className="fixed inset-0 pointer-events-none overflow-hidden">
        <div className={`absolute top-0 left-1/4 w-96 h-96 ${isDark ? 'bg-blue-500/10' : 'bg-blue-400/20'} rounded-full blur-3xl animate-pulse`} />
        <div className={`absolute bottom-0 right-1/4 w-96 h-96 ${isDark ? 'bg-purple-500/10' : 'bg-purple-400/20'} rounded-full blur-3xl animate-pulse`} style={{ animationDelay: '1s' }} />
        <div className={`absolute top-1/2 left-1/2 w-64 h-64 ${isDark ? 'bg-indigo-500/5' : 'bg-indigo-400/15'} rounded-full blur-3xl animate-pulse`} style={{ animationDelay: '2s' }} />
      </div>

      <div className="relative z-10 p-6 space-y-6">
      <div className="flex items-center gap-4">
        <button
          onClick={() => navigate('/marketing')}
          className={`p-2 rounded-lg transition-colors ${isDark ? 'hover:bg-gray-700' : 'hover:bg-gray-100'}`}
        >
          <ArrowLeft className={`w-5 h-5 ${isDark ? 'text-gray-400' : 'text-gray-600'}`} />
        </button>
        <div className={`flex items-center gap-2 text-sm ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
          <Link to="/marketing" className="hover:text-blue-600">Dashboard</Link>
          <span>/</span>
          <span className={isDark ? 'text-white' : 'text-gray-900'}>{event.name}</span>
        </div>
      </div>

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

      <div className="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm border border-gray-200 dark:border-gray-700">
        <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
                {event.name}
              </h1>
              {isConsolidated && (
                <span className="px-2 py-0.5 text-xs font-medium bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300 rounded-full">
                  Consolidado
                </span>
              )}
              {isInCriticalWindow(event.dMinus) && (
                <span className="px-3 py-1 text-sm font-medium bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400 rounded-full flex items-center gap-1">
                  <Target className="w-4 h-4" />
                  JANELA CRÍTICA DE DECISÃO
                </span>
              )}
            </div>
            <div className="flex flex-wrap items-center gap-4 mt-2 text-sm text-gray-500 dark:text-gray-400">
              <span className="flex items-center gap-1">
                <Calendar className="w-4 h-4" />
                {new Date(event.date + 'T00:00:00').toLocaleDateString('pt-BR', { 
                  day: '2-digit', 
                  month: 'long', 
                  year: 'numeric' 
                })}
              </span>
              <span className="flex items-center gap-1">
                <MapPin className="w-4 h-4" />
                {event.location}
              </span>
              <span className="flex items-center gap-1">
                <Users className="w-4 h-4" />
                Capacidade: {formatNumber(event.totalCapacity)}
              </span>
            </div>
          </div>
          <div className="px-4 py-2 bg-gray-100 dark:bg-gray-700 rounded-lg">
            <span className="text-sm text-gray-500 dark:text-gray-400">Categoria</span>
            <p className="font-medium text-gray-900 dark:text-white">{event.category}</p>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm border border-gray-200 dark:border-gray-700">
          <div className="flex items-center justify-between mb-4">
            <p className="text-sm text-gray-500 dark:text-gray-400">ISC Atual</p>
            <div className="group relative">
              <Info className="w-4 h-4 text-gray-400 cursor-help" />
              <div className="hidden group-hover:block absolute z-10 w-64 p-2 bg-gray-900 text-white text-xs rounded-lg right-0 top-6">
                Índice de Saúde Comercial: média de IA 7/30, Curva D-% e Rolling 14d
              </div>
            </div>
          </div>
          <div className="flex flex-col items-center">
            <div className="relative w-32 h-16 overflow-hidden">
              <div className="absolute w-32 h-32 rounded-full border-8 border-gray-200 dark:border-gray-600"></div>
              <div 
                className="absolute w-32 h-32 rounded-full border-8 border-transparent"
                style={{
                  borderTopColor: getISCColor(event.iscStatus),
                  borderRightColor: getISCColor(event.iscStatus),
                  transform: `rotate(${gaugeRotation - 90}deg)`,
                  transition: 'transform 0.5s ease-out'
                }}
              ></div>
            </div>
            <p 
              className="text-3xl font-bold mt-2"
              style={{ color: getISCColor(event.iscStatus) }}
            >
              {getISCEmoji(event.iscStatus)} {event.isc.toFixed(2)}
            </p>
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
              {event.iscStatus === 'accelerating' ? 'Acelerando' : 
               event.iscStatus === 'stable' ? 'Estável' : 'Desacelerando'}
            </p>
          </div>
        </div>

        <div className="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm border border-gray-200 dark:border-gray-700">
          <p className="text-sm text-gray-500 dark:text-gray-400">Dias para o Evento</p>
          <p className={`text-4xl font-bold mt-2 ${
            event.dMinus < 40 
              ? 'text-orange-600 dark:text-orange-400' 
              : 'text-gray-900 dark:text-white'
          }`}>
            D-{event.dMinus}
          </p>
          {event.dMinus < 40 && (
            <p className="text-xs text-orange-600 dark:text-orange-400 mt-2 flex items-center gap-1">
              <AlertTriangle className="w-3 h-3" />
              Fora da janela de promoção
            </p>
          )}
          {isInCriticalWindow(event.dMinus) && (
            <p className="text-xs text-amber-600 dark:text-amber-400 mt-2 flex items-center gap-1">
              <Target className="w-3 h-3" />
              Janela crítica D-45 a D-40
            </p>
          )}
        </div>

        <div className="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm border border-gray-200 dark:border-gray-700">
          <p className="text-sm text-gray-500 dark:text-gray-400">Vendas / Meta</p>
          <p className="text-2xl font-bold text-gray-900 dark:text-white mt-2">
            {formatNumber(event.currentSales)} / {formatNumber(event.salesGoal)}
          </p>
          <div className="mt-3 w-full bg-gray-200 dark:bg-gray-600 rounded-full h-3">
            <div 
              className="bg-blue-600 h-3 rounded-full transition-all"
              style={{ width: `${Math.min((event.currentSales / event.salesGoal) * 100, 100)}%` }}
            />
          </div>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-2">
            {Math.round((event.currentSales / event.salesGoal) * 100)}% da meta
          </p>
        </div>

        <div className="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm border border-gray-200 dark:border-gray-700">
          <p className="text-sm text-gray-500 dark:text-gray-400">Ticket Médio Atual</p>
          <p className="text-2xl font-bold text-gray-900 dark:text-white mt-2">
            {formatCurrency(event.averageTicket)}
          </p>
          <div className="flex items-center gap-1 mt-2 text-sm text-gray-500 dark:text-gray-400">
            <DollarSign className="w-4 h-4" />
            Receita estimada: {formatCurrency(event.currentSales * event.averageTicket)}
          </div>
        </div>
      </div>

      <div className={`rounded-xl p-4 border ${getRecommendationStyle()}`}>
        <div className="flex items-start gap-3">
          {event.iscStatus === 'accelerating' ? (
            <TrendingUp className="w-6 h-6 text-green-600 dark:text-green-400 mt-0.5" />
          ) : event.iscStatus === 'stable' ? (
            <Activity className="w-6 h-6 text-yellow-600 dark:text-yellow-400 mt-0.5" />
          ) : (
            <TrendingDown className="w-6 h-6 text-red-600 dark:text-red-400 mt-0.5" />
          )}
          <div>
            <h3 className="font-semibold text-gray-900 dark:text-white">
              Recomendação Automática
            </h3>
            <p className="text-gray-700 dark:text-gray-300 mt-1">
              {event.suggestedAction}
            </p>
          </div>
        </div>
      </div>

      {isConsolidated && (
        <div className="flex flex-col gap-6">
          {projetosVinculados.length > 0 && (
            <div className="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm border border-gray-200 dark:border-gray-700">
              <div className="flex items-center justify-between mb-3">
                <h3 className="font-semibold text-gray-900 dark:text-white">
                  Projetos Vinculados ({projetosVinculados.length})
                </h3>
                {anosDisponiveis.length > 1 && (
                  <div className="flex items-center gap-2">
                    <span className="text-sm text-gray-500 dark:text-gray-400">Ano:</span>
                    <select
                      value={anoParam || new Date().getFullYear()}
                      onChange={(e) => {
                        navigate(`/marketing/evento/${id}?ano=${e.target.value}`);
                      }}
                      className="px-3 py-1.5 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500"
                    >
                      {anosDisponiveis.map(a => (
                        <option key={a} value={a}>{a}</option>
                      ))}
                    </select>
                  </div>
                )}
              </div>
              <div className="flex flex-wrap gap-2">
                {projetosVinculados.map((p) => (
                  <span
                    key={p.id}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 rounded-lg text-sm"
                  >
                    <span className="font-medium">{p.sku}</span>
                    <span className="text-blue-500 dark:text-blue-400">-</span>
                    <span>{p.nome || 'Sem nome'}</span>
                  </span>
                ))}
              </div>
            </div>
          )}

          {comparacaoAnual && (
            <div className="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm border border-gray-200 dark:border-gray-700">
              <h3 className="font-semibold text-gray-900 dark:text-white mb-4">
                Comparativo Ano a Ano: {comparacaoAnual.ano_anterior} vs {comparacaoAnual.ano_atual}
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                <div className="p-4 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
                  <p className="text-sm text-gray-500 dark:text-gray-400 mb-1">Vendas</p>
                  <div className="flex items-end gap-3">
                    <div>
                      <p className="text-xs text-gray-400">{comparacaoAnual.ano_anterior}</p>
                      <p className="text-lg font-bold text-gray-600 dark:text-gray-300">
                        {formatNumber(comparacaoAnual.anterior.vendas)}
                      </p>
                    </div>
                    <div className="text-gray-300 dark:text-gray-600 pb-1">vs</div>
                    <div>
                      <p className="text-xs text-gray-400">{comparacaoAnual.ano_atual}</p>
                      <p className="text-lg font-bold text-gray-900 dark:text-white">
                        {formatNumber(comparacaoAnual.atual.vendas)}
                      </p>
                    </div>
                  </div>
                  {comparacaoAnual.variacao.vendas_pct !== null && (
                    <div className={`flex items-center gap-1 mt-2 text-sm ${comparacaoAnual.variacao.vendas_pct >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}>
                      {comparacaoAnual.variacao.vendas_pct >= 0 ? <TrendingUp className="w-4 h-4" /> : <TrendingDown className="w-4 h-4" />}
                      {comparacaoAnual.variacao.vendas_pct >= 0 ? '+' : ''}{comparacaoAnual.variacao.vendas_pct}%
                    </div>
                  )}
                </div>

                <div className="p-4 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
                  <p className="text-sm text-gray-500 dark:text-gray-400 mb-1">Receita</p>
                  <div className="flex items-end gap-3">
                    <div>
                      <p className="text-xs text-gray-400">{comparacaoAnual.ano_anterior}</p>
                      <p className="text-lg font-bold text-gray-600 dark:text-gray-300">
                        R$ {formatNumber(comparacaoAnual.anterior.receita)}
                      </p>
                    </div>
                    <div className="text-gray-300 dark:text-gray-600 pb-1">vs</div>
                    <div>
                      <p className="text-xs text-gray-400">{comparacaoAnual.ano_atual}</p>
                      <p className="text-lg font-bold text-gray-900 dark:text-white">
                        R$ {formatNumber(comparacaoAnual.atual.receita)}
                      </p>
                    </div>
                  </div>
                  {comparacaoAnual.variacao.receita_pct !== null && (
                    <div className={`flex items-center gap-1 mt-2 text-sm ${comparacaoAnual.variacao.receita_pct >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}>
                      {comparacaoAnual.variacao.receita_pct >= 0 ? <TrendingUp className="w-4 h-4" /> : <TrendingDown className="w-4 h-4" />}
                      {comparacaoAnual.variacao.receita_pct >= 0 ? '+' : ''}{comparacaoAnual.variacao.receita_pct}%
                    </div>
                  )}
                </div>

                <div className="p-4 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
                  <p className="text-sm text-gray-500 dark:text-gray-400 mb-1">Ticket Medio</p>
                  <div className="flex items-end gap-3">
                    <div>
                      <p className="text-xs text-gray-400">{comparacaoAnual.ano_anterior}</p>
                      <p className="text-lg font-bold text-gray-600 dark:text-gray-300">
                        R$ {comparacaoAnual.anterior.ticket_medio.toFixed(2)}
                      </p>
                    </div>
                    <div className="text-gray-300 dark:text-gray-600 pb-1">vs</div>
                    <div>
                      <p className="text-xs text-gray-400">{comparacaoAnual.ano_atual}</p>
                      <p className="text-lg font-bold text-gray-900 dark:text-white">
                        R$ {comparacaoAnual.atual.ticket_medio.toFixed(2)}
                      </p>
                    </div>
                  </div>
                </div>

                <div className="p-4 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
                  <p className="text-sm text-gray-500 dark:text-gray-400 mb-1">Ocupacao</p>
                  <div className="flex items-end gap-3">
                    <div>
                      <p className="text-xs text-gray-400">{comparacaoAnual.ano_anterior}</p>
                      <p className="text-lg font-bold text-gray-600 dark:text-gray-300">
                        {comparacaoAnual.anterior.ocupacao_pct}%
                      </p>
                    </div>
                    <div className="text-gray-300 dark:text-gray-600 pb-1">vs</div>
                    <div>
                      <p className="text-xs text-gray-400">{comparacaoAnual.ano_atual}</p>
                      <p className="text-lg font-bold text-gray-900 dark:text-white">
                        {comparacaoAnual.atual.ocupacao_pct}%
                      </p>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm border border-gray-200 dark:border-gray-700">
          <h3 className="font-semibold text-gray-900 dark:text-white mb-4">
            Curva de Vendas Acumuladas vs Esperado
          </h3>
          <div className="h-80">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={cumulativeData.slice(-30)}>
                <CartesianGrid strokeDasharray="3 3" stroke="#374151" opacity={0.2} />
                <XAxis 
                  dataKey="date" 
                  tickFormatter={(value) => new Date(value).toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' })}
                  stroke="#6B7280"
                  fontSize={12}
                />
                <YAxis stroke="#6B7280" fontSize={12} />
                <Tooltip 
                  labelFormatter={(value) => new Date(value).toLocaleDateString('pt-BR')}
                  formatter={(value) => formatNumber(Number(value ?? 0))}
                  contentStyle={{ 
                    backgroundColor: '#1F2937', 
                    border: 'none', 
                    borderRadius: '8px',
                    color: '#fff'
                  }}
                />
                <Legend />
                <Line 
                  type="monotone" 
                  dataKey="cumulative" 
                  name="Vendas Reais"
                  stroke="#3B82F6" 
                  strokeWidth={2}
                  dot={false}
                />
                <Line 
                  type="monotone" 
                  dataKey="cumulativeExpected" 
                  name="Benchmark Esperado"
                  stroke="#9CA3AF" 
                  strokeWidth={2}
                  strokeDasharray="5 5"
                  dot={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm border border-gray-200 dark:border-gray-700">
          <h3 className="font-semibold text-gray-900 dark:text-white mb-4">
            Vendas Diárias (Últimos 30 dias)
          </h3>
          <div className="h-80">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={last30Days}>
                <CartesianGrid strokeDasharray="3 3" stroke="#374151" opacity={0.2} />
                <XAxis 
                  dataKey="date" 
                  tickFormatter={(value) => new Date(value).toLocaleDateString('pt-BR', { day: '2-digit' })}
                  stroke="#6B7280"
                  fontSize={12}
                />
                <YAxis stroke="#6B7280" fontSize={12} />
                <Tooltip 
                  labelFormatter={(value) => new Date(value).toLocaleDateString('pt-BR')}
                  formatter={(value) => formatNumber(Number(value ?? 0))}
                  contentStyle={{ 
                    backgroundColor: '#1F2937', 
                    border: 'none', 
                    borderRadius: '8px',
                    color: '#fff'
                  }}
                />
                <Bar 
                  dataKey="sales" 
                  name="Vendas"
                  fill="#3B82F6" 
                  radius={[4, 4, 0, 0]}
                />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      <div className="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm border border-gray-200 dark:border-gray-700">
        <h3 className="font-semibold text-gray-900 dark:text-white mb-4">
          Componentes do ISC
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className="p-4 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm text-gray-500 dark:text-gray-400">IA 7/30</span>
              <div className="group relative">
                <Info className="w-4 h-4 text-gray-400 cursor-help" />
                <div className="hidden group-hover:block absolute z-10 w-56 p-2 bg-gray-900 text-white text-xs rounded-lg right-0 top-6">
                  Índice de Aceleração: Vendas 7 dias / Vendas 30 dias × (30/7). {'>'} 1 = acelerando
                </div>
              </div>
            </div>
            <p className="text-2xl font-bold text-gray-900 dark:text-white">
              {event.iscComponents.ia730.toFixed(2)}
            </p>
            <div className="flex items-center gap-1 mt-2 text-sm">
              {event.iscComponents.ia730 > 1 ? (
                <>
                  <TrendingUp className="w-4 h-4 text-green-500" />
                  <span className="text-green-600 dark:text-green-400">Acelerando</span>
                </>
              ) : (
                <>
                  <TrendingDown className="w-4 h-4 text-red-500" />
                  <span className="text-red-600 dark:text-red-400">Desacelerando</span>
                </>
              )}
            </div>
          </div>

          <div className="p-4 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm text-gray-500 dark:text-gray-400">Curva D-%</span>
              <div className="group relative">
                <Info className="w-4 h-4 text-gray-400 cursor-help" />
                <div className="hidden group-hover:block absolute z-10 w-56 p-2 bg-gray-900 text-white text-xs rounded-lg right-0 top-6">
                  Vendas reais / Vendas esperadas para este D-. {'>'} 1 = adiantado
                </div>
              </div>
            </div>
            <p className="text-2xl font-bold text-gray-900 dark:text-white">
              {event.iscComponents.curvaDPercent.toFixed(2)}
            </p>
            <div className="flex items-center gap-1 mt-2 text-sm">
              {event.iscComponents.curvaDPercent > 1 ? (
                <>
                  <TrendingUp className="w-4 h-4 text-green-500" />
                  <span className="text-green-600 dark:text-green-400">Adiantado</span>
                </>
              ) : (
                <>
                  <TrendingDown className="w-4 h-4 text-red-500" />
                  <span className="text-red-600 dark:text-red-400">Atrasado</span>
                </>
              )}
            </div>
          </div>

          <div className="p-4 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm text-gray-500 dark:text-gray-400">Rolling 14d</span>
              <div className="group relative">
                <Info className="w-4 h-4 text-gray-400 cursor-help" />
                <div className="hidden group-hover:block absolute z-10 w-56 p-2 bg-gray-900 text-white text-xs rounded-lg right-0 top-6">
                  Média de vendas 14 dias (normalizada). {'>'} 1 = momentum quente
                </div>
              </div>
            </div>
            <p className="text-2xl font-bold text-gray-900 dark:text-white">
              {event.iscComponents.rolling14d.toFixed(2)}
            </p>
            <div className="flex items-center gap-1 mt-2 text-sm">
              {event.iscComponents.rolling14d > 1 ? (
                <>
                  <Activity className="w-4 h-4 text-green-500" />
                  <span className="text-green-600 dark:text-green-400">Momentum Quente</span>
                </>
              ) : (
                <>
                  <Activity className="w-4 h-4 text-blue-500" />
                  <span className="text-blue-600 dark:text-blue-400">Momentum Frio</span>
                </>
              )}
            </div>
          </div>
        </div>
      </div>

      <div className="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm border border-gray-200 dark:border-gray-700">
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-semibold text-gray-900 dark:text-white">
            Timeline de Ações Comerciais
          </h3>
          <button
            onClick={() => setShowActionModal(true)}
            className="flex items-center gap-2 px-3 py-1.5 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
          >
            <Plus className="w-4 h-4" />
            Adicionar Ação
          </button>
        </div>
        {event.commercialActions && event.commercialActions.length > 0 ? (
          <div className="space-y-4">
            {event.commercialActions.map((action: CommercialAction, index: number) => (
              <div key={action.id} className="flex gap-4">
                <div className="flex flex-col items-center">
                  <div className={`w-10 h-10 rounded-full flex items-center justify-center ${
                    action.type === 'price_increase' ? 'bg-green-100 dark:bg-green-900/30' :
                    action.type === 'price_decrease' ? 'bg-red-100 dark:bg-red-900/30' :
                    action.type === 'promotion' ? 'bg-purple-100 dark:bg-purple-900/30' :
                    action.type === 'campaign' ? 'bg-blue-100 dark:bg-blue-900/30' :
                    'bg-gray-100 dark:bg-gray-700'
                  }`}>
                    {action.type === 'price_increase' && <TrendingUp className="w-5 h-5 text-green-600" />}
                    {action.type === 'price_decrease' && <TrendingDown className="w-5 h-5 text-red-600" />}
                    {action.type === 'promotion' && <Target className="w-5 h-5 text-purple-600" />}
                    {action.type === 'campaign' && <Activity className="w-5 h-5 text-blue-600" />}
                    {action.type === 'communication' && <Clock className="w-5 h-5 text-gray-600" />}
                  </div>
                  {index < (event.commercialActions?.length ?? 0) - 1 && (
                    <div className="w-0.5 h-full bg-gray-200 dark:bg-gray-600 mt-2" />
                  )}
                </div>
                <div className="flex-1 pb-4">
                  <div className="flex items-center justify-between">
                    <p className="font-medium text-gray-900 dark:text-white">
                      {action.description}
                    </p>
                    <div className="flex items-center gap-2">
                      <span className="text-sm text-gray-500 dark:text-gray-400">
                        {new Date(action.date + 'T00:00:00').toLocaleDateString('pt-BR')}
                      </span>
                      <button
                        onClick={() => handleDeleteAction(action.id)}
                        className="p-1 text-gray-400 hover:text-red-500 transition-colors"
                        title="Excluir ação"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                  {action.impact ? (
                    <div className="mt-1">
                      <p className={`text-sm flex items-center gap-1 ${
                        action.impacto_percentual && action.impacto_percentual > 0 
                          ? 'text-green-600 dark:text-green-400' 
                          : action.impacto_percentual && action.impacto_percentual < 0
                            ? 'text-red-600 dark:text-red-400'
                            : 'text-gray-600 dark:text-gray-400'
                      }`}>
                        <CheckCircle className="w-4 h-4" />
                        Impacto: {action.impact}
                      </p>
                      {action.vendas_antes !== undefined && action.vendas_depois !== undefined && (
                        <p className="text-xs text-gray-500 dark:text-gray-500 mt-0.5 ml-5">
                          7d antes: {action.vendas_antes} vendas → 7d depois: {action.vendas_depois} vendas
                        </p>
                      )}
                    </div>
                  ) : action.status_impacto === 'aguardando_dados' ? (
                    <p className="text-sm text-yellow-600 dark:text-yellow-400 mt-1 flex items-center gap-1">
                      <Clock className="w-4 h-4" />
                      Aguardando dados (7 dias após a ação)
                    </p>
                  ) : null}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-gray-500 dark:text-gray-400 text-center py-4">
            Nenhuma ação comercial registrada. Clique em "Adicionar Ação" para registrar uma ação realizada.
          </p>
        )}
      </div>

      {showActionModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white dark:bg-gray-800 rounded-xl p-6 w-full max-w-md mx-4 shadow-xl">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
                Adicionar Ação Comercial
              </h3>
              <button
                onClick={() => setShowActionModal(false)}
                className="p-1 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            
            <div className="space-y-4">
              {isConsolidated && projetosVinculados.length > 0 && (
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    Projeto Vinculado
                  </label>
                  <select
                    value={actionForm.projeto_id_selecionado}
                    onChange={(e) => setActionForm({ ...actionForm, projeto_id_selecionado: parseInt(e.target.value) })}
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500"
                  >
                    {projetosVinculados.map(p => (
                      <option key={p.id} value={p.id}>{p.sku} - {p.nome || 'Sem nome'}</option>
                    ))}
                  </select>
                </div>
              )}
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Tipo de Ação
                </label>
                <select
                  value={actionForm.tipo}
                  onChange={(e) => setActionForm({ ...actionForm, tipo: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500"
                >
                  {tipoOptions.map(opt => (
                    <option key={opt.value} value={opt.value}>{opt.label}</option>
                  ))}
                </select>
              </div>
              
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Data da Ação
                </label>
                <input
                  type="date"
                  value={actionForm.data_acao}
                  onChange={(e) => setActionForm({ ...actionForm, data_acao: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500"
                />
              </div>
              
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Descrição
                </label>
                <textarea
                  value={actionForm.descricao}
                  onChange={(e) => setActionForm({ ...actionForm, descricao: e.target.value })}
                  placeholder="Descreva a ação realizada..."
                  rows={3}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 resize-none"
                />
              </div>
            </div>
            
            <div className="flex gap-3 mt-6">
              <button
                onClick={() => setShowActionModal(false)}
                className="flex-1 px-4 py-2 border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
              >
                Cancelar
              </button>
              <button
                onClick={handleSaveAction}
                disabled={savingAction || !actionForm.descricao.trim()}
                className="flex-1 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
              >
                {savingAction ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    Salvando...
                  </>
                ) : (
                  'Salvar Ação'
                )}
              </button>
            </div>
          </div>
        </div>
      )}
      </div>
    </div>
  );
};

export default EventDetail;
