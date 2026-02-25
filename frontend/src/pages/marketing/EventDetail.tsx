import React, { useState, useEffect, useRef, lazy, Suspense } from 'react';
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
  Trash2,
  RefreshCw
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
  ReferenceLine,
  Cell
} from 'recharts';
import { marketingService, MarketingEvent } from '../../services/api';
import { 
  getISCColor, 
  getISCEmoji, 
  isInCriticalWindow,
  getISCStatus
} from '../../types/marketingPerformance';
import { useTheme } from '../../context/ThemeContext';
import EventInsights from './EventInsights';
import EventSimulator from './EventSimulator';
import EventPricing from './EventPricing';

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
  const [curvaData, setCurvaData] = useState<any[]>([]);
  const [curvaMeta, setCurvaMeta] = useState<any>(null);
  const [curvaAnoAtual, setCurvaAnoAtual] = useState<number>(new Date().getFullYear());
  const [curvaAnoAnterior, setCurvaAnoAnterior] = useState<number>(new Date().getFullYear() - 1);
  const [activeTab, setActiveTab] = useState<'dashboard' | 'simulator' | 'pricing'>('dashboard');
  const [curvaLoading, setCurvaLoading] = useState(false);
  const [curvaMode, setCurvaMode] = useState<'vendas' | 'receita'>('vendas');
  const [curvaView, setCurvaView] = useState<'semanal' | 'acumulado'>('acumulado');
  const [curvaModo, setCurvaModo] = useState<string>('mensal');
  const [dataEventoAtual, setDataEventoAtual] = useState<string | null>(null);
  const [dataEventoAnterior, setDataEventoAnterior] = useState<string | null>(null);
  const [salesAverages, setSalesAverages] = useState<any>(null);
  const [salesAvgLoading, setSalesAvgLoading] = useState(false);
  const [salesAvgPeriod, setSalesAvgPeriod] = useState(30);
  const [refreshing, setRefreshing] = useState(false);
  const [chartPeriod, setChartPeriod] = useState<number | null>(null);
  const [attainmentPeriod, setAttainmentPeriod] = useState<number | null>(30);
  const [attainmentMode, setAttainmentMode] = useState<'acumulado' | 'diario'>('acumulado');

  const isConsolidated = id?.startsWith('grp_') ?? false;
  const abortControllerRef = useRef<AbortController | null>(null);
  const curvaAbortRef = useRef<AbortController | null>(null);

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

  useEffect(() => {
    if (!id) return;
    if (curvaAbortRef.current) {
      curvaAbortRef.current.abort();
    }
    const curvaController = new AbortController();
    curvaAbortRef.current = curvaController;

    const fetchCurva = async () => {
      try {
        setCurvaLoading(true);
        const response = await marketingService.getCurvaComparativaEvento(id, curvaController.signal, anoParam);
        if (!curvaController.signal.aborted) {
          setCurvaData(response.data);
          setCurvaAnoAtual(response.ano_atual);
          setCurvaAnoAnterior(response.ano_anterior);
          setCurvaModo(response.modo || 'mensal');
          setDataEventoAtual(response.data_evento_atual || null);
          setDataEventoAnterior(response.data_evento_anterior || null);
          setCurvaMeta(response.meta || null);
        }
      } catch (err: any) {
        if (err?.name === 'CanceledError' || err?.code === 'ERR_CANCELED') return;
        console.error('Erro ao carregar curva comparativa do evento:', err);
      } finally {
        if (!curvaController.signal.aborted) {
          setCurvaLoading(false);
        }
      }
    };

    fetchCurva();
    return () => { curvaController.abort(); };
  }, [id, anoParam]);

  useEffect(() => {
    if (!id) return;
    const controller = new AbortController();
    
    const fetchAverages = async () => {
      setSalesAvgLoading(true);
      try {
        const data = await marketingService.getSalesAverages(id, salesAvgPeriod, controller.signal, anoParam);
        if (!controller.signal.aborted) {
          setSalesAverages(data);
        }
      } catch (err: any) {
        if (err?.name !== 'AbortError' && err?.code !== 'ERR_CANCELED') {
          console.error('Error fetching sales averages:', err);
        }
      } finally {
        if (!controller.signal.aborted) {
          setSalesAvgLoading(false);
        }
      }
    };
    
    fetchAverages();
    return () => controller.abort();
  }, [id, salesAvgPeriod, anoParam]);

  const handleForceRefresh = async () => {
    if (!id || refreshing) return;
    setRefreshing(true);
    try {
      const controller = new AbortController();
      const response = await marketingService.getEventoById(id, controller.signal, anoParam, true);
      const eventWithData = {
        ...response.evento,
        dailySales: response.dailySales?.map(d => ({
          date: d.date,
          sales: d.sales,
          expected: d.expected,
          cumulativeSales: d.cumulativeSales,
          cumulativeExpected: d.cumulativeExpected
        })),
        commercialActions: (response as any).commercialActions?.map((a: any) => ({
          id: a.id,
          type: a.type,
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
      }
      if ((response as any).anos_disponiveis) {
        setAnosDisponiveis((response as any).anos_disponiveis);
      }
      setAvisos((response as any).avisos || []);
    } catch (err: any) {
      console.error('Erro ao atualizar:', err);
    } finally {
      setRefreshing(false);
    }
  };

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
      const duplicateCheck = await marketingService.checkDuplicateAction(projetoIdParaAcao, actionForm.tipo);
      if (duplicateCheck.has_duplicate && duplicateCheck.existing_action) {
        const tipoLabels: Record<string, string> = {
          'PROMOCAO': 'Promoção',
          'AUMENTO_PRECO': 'Aumento de Preço',
          'REDUCAO_PRECO': 'Redução de Preço',
          'CAMPANHA': 'Campanha',
          'COMUNICACAO': 'Comunicação'
        };
        const tipoLabel = tipoLabels[actionForm.tipo] || actionForm.tipo;
        alert(`Já existe uma ação de "${tipoLabel}" ativa neste evento.\n\n` +
          `Ação: ${duplicateCheck.existing_action.descricao}\n` +
          `Data: ${new Date(duplicateCheck.existing_action.data_acao + 'T00:00:00').toLocaleDateString('pt-BR')}\n` +
          `Ativa por mais: ${duplicateCheck.existing_action.dias_restantes} dia(s)\n\n` +
          `Aguarde o término do período de 7 dias para criar uma nova ação do mesmo tipo.`);
        setSavingAction(false);
        return;
      }
    } catch (err) {
      console.error('Error checking duplicate:', err);
    }
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

  const filteredCumulativeData = chartPeriod
    ? cumulativeData.slice(-chartPeriod)
    : cumulativeData;

  const goalAttainmentData = cumulativeData
    .filter(d => d.cumulativeExpected > 0)
    .map(d => {
      const eventDate = new Date(event.date + 'T12:00:00');
      const dayDate = new Date(d.date + 'T12:00:00');
      const diffMs = eventDate.getTime() - dayDate.getTime();
      const dMinus = Math.round(diffMs / (1000 * 60 * 60 * 24));
      const pct = parseFloat((((d.cumulative / d.cumulativeExpected) * 100) - 100).toFixed(1));
      return {
        date: d.date,
        dMinus,
        label: `D-${dMinus}`,
        percentual: pct,
        cumulative: Math.round(d.cumulative),
        cumulativeExpected: Math.round(d.cumulativeExpected),
      };
    });

  const goalAttainmentDailyData = (event.dailySales || [])
    .filter(d => d.expected > 0)
    .map(d => {
      const eventDate = new Date(event.date + 'T12:00:00');
      const dayDate = new Date(d.date + 'T12:00:00');
      const diffMs = eventDate.getTime() - dayDate.getTime();
      const dMinus = Math.round(diffMs / (1000 * 60 * 60 * 24));
      const pct = parseFloat((((d.sales / d.expected) * 100) - 100).toFixed(1));
      return {
        date: d.date,
        dMinus,
        label: `D-${dMinus}`,
        percentual: pct,
        sales: Math.round(d.sales),
        expected: Math.round(d.expected),
      };
    });

  const activeAttainmentData = attainmentMode === 'acumulado' ? goalAttainmentData : goalAttainmentDailyData;
  const filteredAttainmentData = attainmentPeriod ? activeAttainmentData.slice(-attainmentPeriod) : activeAttainmentData;

  const todayStr = new Date().toISOString().split('T')[0];
  const dailySalesArr = event.dailySales || [];
  const todayDailySale = dailySalesArr.find(d => d.date === todayStr);
  const lastDailySale = dailySalesArr.length > 0 ? dailySalesArr[dailySalesArr.length - 1] : null;
  const hasTodayData = !!todayDailySale;
  const todaySales = todayDailySale?.sales ?? 0;
  const todayExpectedRounded = Math.round(todayDailySale?.expected ?? 0);
  const todayPct = todayExpectedRounded > 0 ? Math.round((todaySales / todayExpectedRounded) * 100) : (todaySales > 0 ? 100 : 0);
  const lastCumData = cumulativeData.length > 0 ? cumulativeData[cumulativeData.length - 1] : null;
  const metaAcumulada = lastCumData ? Math.round(lastCumData.cumulativeExpected) : 0;
  const inscritosTotal = lastCumData ? Math.round(lastCumData.cumulative) : 0;
  const acumuladoGap = metaAcumulada > 0 ? Math.round(((inscritosTotal - metaAcumulada) / metaAcumulada) * 100) : (inscritosTotal > 0 ? 100 : 0);

  const last30Days = (event.dailySales || []).slice(-30);

  const volumeParaMeta = metaAcumulada - inscritosTotal;
  const mediaDiariaNecessaria = event.dMinus > 0 ? Math.max(volumeParaMeta, 0) / event.dMinus : 0;
  const last7DaysSales = (event.dailySales || []).slice(-7);
  const mediaSemanaAtual = last7DaysSales.length > 0
    ? last7DaysSales.reduce((sum, d) => sum + d.sales, 0) / last7DaysSales.length
    : 0;
  const pctMedias = mediaDiariaNecessaria > 0
    ? ((mediaSemanaAtual / mediaDiariaNecessaria) * 100) - 100
    : (mediaSemanaAtual > 0 ? 100 : 0);

  const indicadoresVolume = [3, 7, 14].map(dias => {
    const vendas = (event.dailySales || []).slice(-dias);
    const totalVendas = vendas.reduce((sum, d) => sum + d.sales, 0);
    const media = vendas.length > 0 ? totalVendas / vendas.length : 0;
    const potencial = media * event.dMinus;
    const atingimento = inscritosTotal + potencial;
    const alvo = metaAcumulada > 0 ? (atingimento / metaAcumulada) - 1 : 0;
    return {
      periodo: dias === 3 ? '3 dias' : dias === 7 ? '1 semana' : '14 dias',
      media: Math.round(media * 10) / 10,
      dMinus: event.dMinus,
      potencial: Math.round(potencial),
      vendasAcumuladas: inscritosTotal,
      atingimento: Math.round(atingimento),
      meta: metaAcumulada,
      alvo: Math.round(alvo * 1000) / 10,
    };
  });

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
      <div className="flex items-center justify-between">
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
        <button
          onClick={handleForceRefresh}
          disabled={refreshing}
          className={`flex items-center gap-2 px-4 py-2 rounded-lg bg-blue-100 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400 hover:bg-blue-200 dark:hover:bg-blue-900/50 transition-colors ${refreshing ? 'opacity-50 cursor-not-allowed' : ''}`}
          title="Buscar dados atualizados do banco de dados"
        >
          <RefreshCw className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''}`} />
          <span className="text-sm font-medium">{refreshing ? 'Atualizando...' : 'Atualizar Dados'}</span>
        </button>
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

      <div className="flex gap-2 border-b border-gray-200 dark:border-gray-700">
        <button
          onClick={() => setActiveTab('dashboard')}
          className={`px-5 py-2.5 text-sm font-medium rounded-t-lg transition-colors ${
            activeTab === 'dashboard'
              ? 'bg-white dark:bg-gray-800 text-blue-600 dark:text-blue-400 border border-b-0 border-gray-200 dark:border-gray-700'
              : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300'
          }`}
        >
          Dashboard
        </button>
        <button
          onClick={() => setActiveTab('simulator')}
          className={`px-5 py-2.5 text-sm font-medium rounded-t-lg transition-colors ${
            activeTab === 'simulator'
              ? 'bg-white dark:bg-gray-800 text-blue-600 dark:text-blue-400 border border-b-0 border-gray-200 dark:border-gray-700'
              : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300'
          }`}
        >
          Simulador
        </button>
        <button
          onClick={() => setActiveTab('pricing')}
          className={`px-5 py-2.5 text-sm font-medium rounded-t-lg transition-colors ${
            activeTab === 'pricing'
              ? 'bg-white dark:bg-gray-800 text-blue-600 dark:text-blue-400 border border-b-0 border-gray-200 dark:border-gray-700'
              : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300'
          }`}
        >
          Pricing
        </button>
      </div>

      {activeTab === 'pricing' ? (
        <EventPricing eventoId={id!} ano={anoParam} />
      ) : activeTab === 'simulator' ? (
        <EventSimulator eventoId={id!} ano={anoParam} isDark={isDark} />
      ) : (
      <>
      <div className={`rounded-xl px-4 py-2 shadow-sm border flex flex-wrap items-center gap-3 ${getRecommendationStyle()}`}>
        <div className="flex items-center gap-3">
          <Clock className="w-4 h-4 text-gray-400" />
          <span className="text-sm text-gray-500 dark:text-gray-400">Dias para o Evento</span>
          <span className={`text-xl font-bold ${
            event.dMinus < 40 
              ? 'text-orange-600 dark:text-orange-400' 
              : 'text-gray-900 dark:text-white'
          }`}>
            D-{event.dMinus}
          </span>
          {event.dMinus < 40 && (
            <span className="text-xs text-orange-600 dark:text-orange-400 flex items-center gap-1">
              <AlertTriangle className="w-3 h-3" />
              Fora da janela de promoção
            </span>
          )}
          {isInCriticalWindow(event.dMinus) && (
            <span className="text-xs text-amber-600 dark:text-amber-400 flex items-center gap-1">
              <Target className="w-3 h-3" />
              Janela crítica D-45 a D-40
            </span>
          )}
        </div>
        <div className="hidden sm:block w-px h-6 bg-gray-300 dark:bg-gray-600" />
        <div className="flex items-center gap-2 flex-1 min-w-0">
          {event.iscStatus === 'accelerating' ? (
            <TrendingUp className="w-4 h-4 text-green-600 dark:text-green-400 shrink-0" />
          ) : event.iscStatus === 'stable' ? (
            <Activity className="w-4 h-4 text-yellow-600 dark:text-yellow-400 shrink-0" />
          ) : (
            <TrendingDown className="w-4 h-4 text-red-600 dark:text-red-400 shrink-0" />
          )}
          <p className="text-sm text-gray-700 dark:text-gray-300 truncate">
            {event.suggestedAction}
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
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

        <div className="lg:col-span-2 bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm border border-gray-200 dark:border-gray-700">
          <h3 className="font-semibold text-gray-900 dark:text-white mb-3 text-sm">Componentes do ISC</h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs text-gray-500 dark:text-gray-400">IA 7/30</span>
                <div className="group relative">
                  <Info className="w-3.5 h-3.5 text-gray-400 cursor-help" />
                  <div className="hidden group-hover:block absolute z-10 w-56 p-2 bg-gray-900 text-white text-xs rounded-lg right-0 top-5">
                    Índice de Aceleração: Vendas 7 dias / Vendas 30 dias × (30/7). {'>'} 1 = acelerando
                  </div>
                </div>
              </div>
              <p className="text-xl font-bold text-gray-900 dark:text-white">
                {event.iscComponents.ia730.toFixed(2)}
              </p>
              <div className="flex items-center gap-1 mt-1 text-xs">
                {event.iscComponents.ia730 > 1 ? (
                  <>
                    <TrendingUp className="w-3.5 h-3.5 text-green-500" />
                    <span className="text-green-600 dark:text-green-400">Acelerando</span>
                  </>
                ) : (
                  <>
                    <TrendingDown className="w-3.5 h-3.5 text-red-500" />
                    <span className="text-red-600 dark:text-red-400">Desacelerando</span>
                  </>
                )}
              </div>
            </div>

            <div className="p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs text-gray-500 dark:text-gray-400">Curva D-%</span>
                <div className="group relative">
                  <Info className="w-3.5 h-3.5 text-gray-400 cursor-help" />
                  <div className="hidden group-hover:block absolute z-10 w-56 p-2 bg-gray-900 text-white text-xs rounded-lg right-0 top-5">
                    Vendas reais / Vendas esperadas para este D-. {'>'} 1 = adiantado
                  </div>
                </div>
              </div>
              <p className="text-xl font-bold text-gray-900 dark:text-white">
                {event.iscComponents.curvaDPercent.toFixed(2)}
              </p>
              <div className="flex items-center gap-1 mt-1 text-xs">
                {event.iscComponents.curvaDPercent > 1 ? (
                  <>
                    <TrendingUp className="w-3.5 h-3.5 text-green-500" />
                    <span className="text-green-600 dark:text-green-400">Adiantado</span>
                  </>
                ) : (
                  <>
                    <TrendingDown className="w-3.5 h-3.5 text-red-500" />
                    <span className="text-red-600 dark:text-red-400">Atrasado</span>
                  </>
                )}
              </div>
            </div>

            <div className="p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs text-gray-500 dark:text-gray-400">Rolling 14d</span>
                <div className="group relative">
                  <Info className="w-3.5 h-3.5 text-gray-400 cursor-help" />
                  <div className="hidden group-hover:block absolute z-10 w-56 p-2 bg-gray-900 text-white text-xs rounded-lg right-0 top-5">
                    Média de vendas 14 dias (normalizada). {'>'} 1 = momentum quente
                  </div>
                </div>
              </div>
              <p className="text-xl font-bold text-gray-900 dark:text-white">
                {event.iscComponents.rolling14d.toFixed(2)}
              </p>
              <div className="flex items-center gap-1 mt-1 text-xs">
                {event.iscComponents.rolling14d > 1 ? (
                  <>
                    <Activity className="w-3.5 h-3.5 text-green-500" />
                    <span className="text-green-600 dark:text-green-400">Momentum Quente</span>
                  </>
                ) : (
                  <>
                    <Activity className="w-3.5 h-3.5 text-blue-500" />
                    <span className="text-blue-600 dark:text-blue-400">Momentum Frio</span>
                  </>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {isConsolidated && cumulativeData.length > 0 ? (
          <div className="lg:col-span-2 bg-white dark:bg-gray-800 rounded-xl p-5 shadow-sm border border-gray-200 dark:border-gray-700">
            <h3 className="text-sm font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
              <Target className="w-4 h-4 text-blue-500" />
              Acompanhamento de Meta
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="p-4 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
                <p className="text-xs text-gray-500 dark:text-gray-400 mb-3">Meta de Hoje vs Vendas Hoje</p>
                {hasTodayData ? (
                  <>
                    <div className="flex items-center justify-between mb-2">
                      <div>
                        <p className="text-xs text-gray-400 dark:text-gray-500 mb-0.5">Vendas Hoje</p>
                        <p className="text-lg font-bold text-blue-600 dark:text-blue-400">{formatNumber(todaySales)}</p>
                      </div>
                      <div className="text-gray-300 dark:text-gray-600 text-sm">vs</div>
                      <div className="text-right">
                        <p className="text-xs text-gray-400 dark:text-gray-500 mb-0.5">Meta Hoje</p>
                        <p className="text-lg font-bold text-gray-600 dark:text-gray-300">{formatNumber(todayExpectedRounded)}</p>
                      </div>
                    </div>
                    <div className="mt-2">
                      <div className="flex justify-between text-xs text-gray-500 dark:text-gray-400 mb-1">
                        <span>Atingimento</span>
                        <span className={`font-semibold ${todayPct >= 100 ? 'text-green-600 dark:text-green-400' : todayPct >= 70 ? 'text-yellow-600 dark:text-yellow-400' : 'text-red-600 dark:text-red-400'}`}>{todayPct}%</span>
                      </div>
                      <div className="w-full bg-gray-200 dark:bg-gray-600 rounded-full h-2">
                        <div
                          className={`h-2 rounded-full transition-all ${todayPct >= 100 ? 'bg-green-500' : todayPct >= 70 ? 'bg-yellow-500' : 'bg-red-500'}`}
                          style={{ width: `${Math.min(todayPct, 100)}%` }}
                        />
                      </div>
                    </div>
                  </>
                ) : (
                  <p className="text-xs text-gray-400 dark:text-gray-500 italic">Sem dados para hoje</p>
                )}
              </div>

              <div className="p-4 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
                <p className="text-xs text-gray-500 dark:text-gray-400 mb-3">Meta Acumulada vs Inscritos Total</p>
                <div className="flex items-center justify-between mb-2">
                  <div>
                    <p className="text-xs text-gray-400 dark:text-gray-500 mb-0.5">Inscritos</p>
                    <p className="text-lg font-bold text-blue-600 dark:text-blue-400">{formatNumber(inscritosTotal)}</p>
                  </div>
                  <div className="text-gray-300 dark:text-gray-600 text-sm">vs</div>
                  <div className="text-right">
                    <p className="text-xs text-gray-400 dark:text-gray-500 mb-0.5">Meta Acumulada</p>
                    <p className="text-lg font-bold text-gray-600 dark:text-gray-300">{formatNumber(metaAcumulada)}</p>
                  </div>
                </div>
                <div className="mt-2 flex items-center justify-center gap-2">
                  <span className="text-xs text-gray-500 dark:text-gray-400">Gap vs Meta</span>
                  <span className={`text-lg font-bold ${acumuladoGap >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}>
                    {acumuladoGap > 0 ? '+' : ''}{acumuladoGap}%
                  </span>
                </div>
              </div>
            </div>
          </div>
        ) : (
          <div className="lg:col-span-2 bg-white dark:bg-gray-800 rounded-xl p-5 shadow-sm border border-gray-200 dark:border-gray-700">
            <p className="text-sm text-gray-500 dark:text-gray-400">Vendas / Meta</p>
            <p className="text-lg font-bold text-gray-900 dark:text-white mt-2">
              {formatNumber(event.currentSales)} / {formatNumber(event.salesGoal)}
            </p>
            <div className="mt-3 w-full bg-gray-200 dark:bg-gray-600 rounded-full h-2">
              <div 
                className="bg-blue-600 h-2 rounded-full transition-all"
                style={{ width: `${Math.min((event.currentSales / event.salesGoal) * 100, 100)}%` }}
              />
            </div>
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-2">
              {Math.round((event.currentSales / event.salesGoal) * 100)}% da meta
            </p>
          </div>
        )}

        <div className="bg-white dark:bg-gray-800 rounded-xl p-5 shadow-sm border border-gray-200 dark:border-gray-700">
          <p className="text-sm text-gray-500 dark:text-gray-400">Ticket Médio / Orçado</p>
          <p className="text-lg font-bold text-gray-900 dark:text-white mt-2">
            {formatCurrency(event.averageTicket)} / {formatCurrency(event.budgetTicket || 0)}
          </p>
          {event.budgetTicket > 0 && (
            <>
              <div className="mt-3 w-full bg-gray-200 dark:bg-gray-600 rounded-full h-2">
                <div 
                  className={`h-2 rounded-full transition-all ${
                    (event.averageTicket / event.budgetTicket) >= 1 ? 'bg-green-500' : 
                    (event.averageTicket / event.budgetTicket) >= 0.8 ? 'bg-blue-600' : 'bg-orange-500'
                  }`}
                  style={{ width: `${Math.min((event.averageTicket / event.budgetTicket) * 100, 100)}%` }}
                />
              </div>
              <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                {Math.round((event.averageTicket / event.budgetTicket) * 100)}% do orçado
              </p>
            </>
          )}
          <div className="flex items-center gap-1 mt-3 text-xs text-gray-500 dark:text-gray-400">
            <DollarSign className="w-3.5 h-3.5" />
            Receita estimada: {formatCurrency(event.currentSales * event.averageTicket)}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm border border-gray-200 dark:border-gray-700">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-4">
            <h3 className="font-semibold text-gray-900 dark:text-white">
              Curva de Vendas Acumuladas vs Esperado
            </h3>
            <div className="flex flex-wrap gap-1">
              {[
                { label: '7d', value: 7 },
                { label: '14d', value: 14 },
                { label: '30d', value: 30 },
                { label: '60d', value: 60 },
                { label: '90d', value: 90 },
                { label: 'Todos', value: null as number | null },
              ].map((opt) => (
                <button
                  key={opt.label}
                  onClick={() => setChartPeriod(opt.value)}
                  className={`px-3 py-1 text-xs font-medium rounded-md transition-colors ${
                    chartPeriod === opt.value
                      ? 'bg-blue-600 text-white'
                      : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600'
                  }`}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>
          <div className="h-80">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={filteredCumulativeData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#374151" opacity={0.2} />
                <XAxis 
                  dataKey="date" 
                  tickFormatter={(value) => new Date(value + 'T12:00:00').toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' })}
                  stroke="#6B7280"
                  fontSize={12}
                />
                <YAxis stroke="#6B7280" fontSize={12} />
                <Tooltip 
                  content={({ active, payload, label }: any) => {
                    if (!active || !payload || !payload.length) return null;
                    const real = Math.round(Number(payload.find((p: any) => p.dataKey === 'cumulative')?.value ?? 0));
                    const esperado = Math.round(Number(payload.find((p: any) => p.dataKey === 'cumulativeExpected')?.value ?? 0));
                    const diff = real - esperado;
                    const diffColor = diff >= 0 ? '#22C55E' : '#EF4444';
                    return (
                      <div style={{ backgroundColor: '#1F2937', border: 'none', borderRadius: '8px', padding: '12px', color: '#fff' }}>
                        <p style={{ marginBottom: '8px', color: '#9CA3AF' }}>{new Date(label + 'T12:00:00').toLocaleDateString('pt-BR')}</p>
                        <p style={{ color: '#3B82F6' }}>Vendas Reais: {formatNumber(real)}</p>
                        <p style={{ color: '#9CA3AF' }}>Esperado: {formatNumber(esperado)}</p>
                        <p style={{ color: diffColor, marginTop: '6px', borderTop: '1px solid #374151', paddingTop: '6px', fontWeight: 600 }}>
                          Diferença: {diff >= 0 ? '+' : ''}{formatNumber(diff)}
                        </p>
                      </div>
                    );
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
                  name="Esperado"
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
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-4">
            <h3 className="font-semibold text-gray-900 dark:text-white">
              Atingimento da Meta por D- ({attainmentMode === 'acumulado' ? 'Acumulado' : 'Diário'})
            </h3>
            <div className="flex items-center gap-3">
              <div className="flex gap-1 border border-gray-200 dark:border-gray-600 rounded-lg p-0.5">
                <button
                  onClick={() => setAttainmentMode('acumulado')}
                  className={`px-3 py-1 text-xs font-medium rounded-md transition-colors ${
                    attainmentMode === 'acumulado'
                      ? 'bg-indigo-600 text-white'
                      : 'text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700'
                  }`}
                >
                  Acumulado
                </button>
                <button
                  onClick={() => setAttainmentMode('diario')}
                  className={`px-3 py-1 text-xs font-medium rounded-md transition-colors ${
                    attainmentMode === 'diario'
                      ? 'bg-indigo-600 text-white'
                      : 'text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700'
                  }`}
                >
                  Diário
                </button>
              </div>
              <div className="flex flex-wrap gap-1">
                {[
                  { label: '7d', value: 7 },
                  { label: '10d', value: 10 },
                  { label: '14d', value: 14 },
                  { label: '30d', value: 30 },
                  { label: '60d', value: 60 },
                  { label: '90d', value: 90 },
                  { label: 'Todos', value: null as number | null },
                ].map((opt) => (
                  <button
                    key={opt.label}
                    onClick={() => setAttainmentPeriod(opt.value)}
                    className={`px-3 py-1 text-xs font-medium rounded-md transition-colors ${
                      attainmentPeriod === opt.value
                        ? 'bg-blue-600 text-white'
                        : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600'
                    }`}
                  >
                    {opt.label}
                  </button>
                ))}
              </div>
            </div>
          </div>
          <div className="h-80">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={filteredAttainmentData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#374151" opacity={0.2} />
                <XAxis
                  dataKey="label"
                  stroke="#6B7280"
                  fontSize={11}
                  interval="preserveStartEnd"
                />
                <YAxis
                  stroke="#6B7280"
                  fontSize={12}
                  tickFormatter={(v) => `${v}%`}
                />
                <Tooltip
                  content={({ active, payload }: any) => {
                    if (!active || !payload || !payload.length) return null;
                    const d = payload[0].payload;
                    const color = d.percentual >= 0 ? '#22C55E' : '#EF4444';
                    const isAcumulado = attainmentMode === 'acumulado';
                    return (
                      <div style={{ backgroundColor: '#1F2937', border: 'none', borderRadius: '8px', padding: '12px', color: '#fff', minWidth: 200 }}>
                        <p style={{ marginBottom: '4px', color: '#9CA3AF', fontWeight: 600 }}>{d.label} — {new Date(d.date + 'T12:00:00').toLocaleDateString('pt-BR')}</p>
                        <p style={{ color: '#3B82F6' }}>{isAcumulado ? 'Inscrições' : 'Vendas do Dia'}: {formatNumber(isAcumulado ? d.cumulative : d.sales)}</p>
                        <p style={{ color: '#9CA3AF' }}>{isAcumulado ? 'Meta Acumulada' : 'Esperado Diário'}: {formatNumber(isAcumulado ? d.cumulativeExpected : d.expected)}</p>
                        <p style={{ color, marginTop: '6px', borderTop: '1px solid #374151', paddingTop: '6px', fontWeight: 700, fontSize: '14px' }}>
                          {d.percentual >= 0 ? '+' : ''}{d.percentual}% da meta
                        </p>
                      </div>
                    );
                  }}
                />
                <ReferenceLine y={0} stroke="#6B7280" strokeDasharray="3 3" />
                <Bar dataKey="percentual" name="% Atingimento" radius={[4, 4, 0, 0]}>
                  {filteredAttainmentData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.percentual >= 0 ? '#22C55E' : '#EF4444'} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

      </div>

      <div className="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm border border-gray-200 dark:border-gray-700">
        <h3 className="font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
          <Activity className="w-5 h-5 text-blue-500" />
          Curva no Tempo
        </h3>
        <div className="mb-4">
          <p className="text-sm text-gray-500 dark:text-gray-400">Vendas / Meta Acumulada</p>
          <p className="text-2xl font-bold text-gray-900 dark:text-white">
            {formatNumber(inscritosTotal)} / {formatNumber(metaAcumulada)}
          </p>
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
            <div className="p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
              <p className="text-xs text-gray-500 dark:text-gray-400">D-</p>
              <p className={`text-xl font-bold ${event.dMinus < 40 ? 'text-orange-600 dark:text-orange-400' : 'text-gray-900 dark:text-white'}`}>
                {event.dMinus}
              </p>
            </div>
            <div className="p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
              <p className="text-xs text-gray-500 dark:text-gray-400">Volume p/ Meta</p>
              <p className={`text-xl font-bold ${volumeParaMeta <= 0 ? 'text-green-600 dark:text-green-400' : 'text-gray-900 dark:text-white'}`}>
                {formatNumber(Math.max(volumeParaMeta, 0))}
              </p>
            </div>
            <div className="p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
              <p className="text-xs text-gray-500 dark:text-gray-400">Média Diária Necessária</p>
              <p className="text-xl font-bold text-gray-900 dark:text-white">
                {mediaDiariaNecessaria.toFixed(1)}
              </p>
            </div>
            <div className="p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
              <p className="text-xs text-gray-500 dark:text-gray-400">Média Semana Atual</p>
              <p className="text-xl font-bold text-gray-900 dark:text-white">
                {mediaSemanaAtual.toFixed(1)}
              </p>
            </div>
            <div className="p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg col-span-2 sm:col-span-2">
              <p className="text-xs text-gray-500 dark:text-gray-400">% Média Atual vs Necessária</p>
              <p className={`text-xl font-bold ${pctMedias >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}>
                {pctMedias > 0 ? '+' : ''}{pctMedias.toFixed(1)}%
              </p>
            </div>
          </div>

          <div>
            <p className="text-sm text-gray-500 dark:text-gray-400 mb-2">Vendas Diárias (Últimos 30 dias)</p>
            <div className="h-56">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={last30Days}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#374151" opacity={0.2} />
                  <XAxis 
                    dataKey="date" 
                    tickFormatter={(value) => new Date(value + 'T12:00:00').toLocaleDateString('pt-BR', { day: '2-digit' })}
                    stroke="#6B7280"
                    fontSize={11}
                  />
                  <YAxis stroke="#6B7280" fontSize={11} />
                  <Tooltip 
                    labelFormatter={(value) => new Date(value + 'T12:00:00').toLocaleDateString('pt-BR')}
                    formatter={(value: any) => formatNumber(Math.round(Number(value ?? 0)))}
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
      </div>

      <div className="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm border border-gray-200 dark:border-gray-700">
        <h3 className="font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
          <Target className="w-5 h-5 text-indigo-500" />
          Indicadores de Volume
        </h3>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-200 dark:border-gray-700">
                <th className="text-left py-2 px-3 text-xs font-semibold text-gray-500 dark:text-gray-400">Período</th>
                <th className="text-right py-2 px-3 text-xs font-semibold text-gray-500 dark:text-gray-400">Média de Vendas</th>
                <th className="text-right py-2 px-3 text-xs font-semibold text-gray-500 dark:text-gray-400">D-</th>
                <th className="text-right py-2 px-3 text-xs font-semibold text-gray-500 dark:text-gray-400">Potencial</th>
                <th className="text-right py-2 px-3 text-xs font-semibold text-gray-500 dark:text-gray-400">Vendas Acum.</th>
                <th className="text-right py-2 px-3 text-xs font-semibold text-gray-500 dark:text-gray-400">Atingimento</th>
                <th className="text-right py-2 px-3 text-xs font-semibold text-gray-500 dark:text-gray-400">Meta Acum.</th>
                <th className="text-right py-2 px-3 text-xs font-semibold text-gray-500 dark:text-gray-400">Alvo</th>
              </tr>
            </thead>
            <tbody>
              {indicadoresVolume.map((row) => (
                <tr key={row.periodo} className="border-b border-gray-100 dark:border-gray-700/50 hover:bg-gray-50 dark:hover:bg-gray-700/30">
                  <td className="py-2.5 px-3 font-medium text-gray-900 dark:text-white">{row.periodo}</td>
                  <td className="py-2.5 px-3 text-right text-gray-700 dark:text-gray-300">{row.media.toFixed(1)}</td>
                  <td className="py-2.5 px-3 text-right text-gray-700 dark:text-gray-300">{row.dMinus}</td>
                  <td className="py-2.5 px-3 text-right text-gray-700 dark:text-gray-300">{formatNumber(row.potencial)}</td>
                  <td className="py-2.5 px-3 text-right text-gray-700 dark:text-gray-300">{formatNumber(row.vendasAcumuladas)}</td>
                  <td className="py-2.5 px-3 text-right text-gray-700 dark:text-gray-300">{formatNumber(row.atingimento)}</td>
                  <td className="py-2.5 px-3 text-right text-gray-700 dark:text-gray-300">{formatNumber(row.meta)}</td>
                  <td className={`py-2.5 px-3 text-right font-bold ${row.alvo >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}>
                    {row.alvo > 0 ? '+' : ''}{row.alvo.toFixed(1)}%
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm border border-gray-200 dark:border-gray-700">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-4">
          <div className="flex items-center gap-2">
            <TrendingUp className="w-5 h-5 text-indigo-500" />
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
              Análise de Médias de Vendas
            </h3>
            <div className="relative group">
              <Info className="w-4 h-4 text-gray-400 dark:text-gray-500 cursor-help" />
              <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-3 py-2 bg-gray-900 dark:bg-gray-700 text-white text-xs rounded-lg shadow-lg opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none w-72 z-50">
                <p className="mb-1"><strong>Período:</strong> Define a janela de dias analisada. Todas as médias são calculadas dividindo vendas por dias corridos (incluindo dias sem vendas).</p>
                <p><strong>Cards:</strong> Mostram a média diária de vendas para sub-períodos relevantes dentro da janela selecionada.</p>
              </div>
            </div>
          </div>
          <div className="flex rounded-lg border border-gray-300 dark:border-gray-600 overflow-hidden">
            {[7, 14, 30, 60, 90].map((p) => (
              <button
                key={p}
                onClick={() => setSalesAvgPeriod(p)}
                className={`px-3 py-1.5 text-xs font-medium transition-colors ${
                  salesAvgPeriod === p
                    ? 'bg-indigo-500 text-white'
                    : 'bg-white dark:bg-gray-700 text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-600'
                }`}
              >
                {p}d
              </button>
            ))}
          </div>
        </div>

        {salesAvgLoading ? (
          <div className="flex items-center justify-center h-64">
            <Loader2 className="w-8 h-8 animate-spin text-indigo-500" />
            <span className="ml-3 text-gray-500 dark:text-gray-400">Carregando médias...</span>
          </div>
        ) : salesAverages ? (
          <>
            <div className={`grid grid-cols-2 ${Array.isArray(salesAverages.medias) ? (salesAverages.medias.length >= 3 ? 'md:grid-cols-4' : 'md:grid-cols-3') : 'md:grid-cols-4'} gap-3`}>
              <div className={`p-4 rounded-lg ${isDark ? 'bg-gray-700/50' : 'bg-indigo-50'}`}>
                <p className="text-xs text-gray-500 dark:text-gray-400">Média Geral ({salesAverages.periodo_dias}d)</p>
                <p className="text-2xl font-bold text-indigo-600 dark:text-indigo-400">
                  {salesAverages.media_geral?.toFixed(1) || '0'}
                </p>
                <p className="text-[10px] text-gray-400 mt-1">{salesAverages.total_vendas || 0} vendas em {salesAverages.periodo_dias} dias</p>
              </div>
              {Array.isArray(salesAverages.medias) && salesAverages.medias.map((m: any, idx: number) => {
                const colors = [
                  { bg: 'bg-blue-50', text: 'text-blue-600 dark:text-blue-400', darkBg: 'bg-gray-700/50' },
                  { bg: 'bg-cyan-50', text: 'text-cyan-600 dark:text-cyan-400', darkBg: 'bg-gray-700/50' },
                  { bg: 'bg-emerald-50', text: 'text-emerald-600 dark:text-emerald-400', darkBg: 'bg-gray-700/50' },
                ];
                const c = colors[idx % colors.length];
                return (
                  <div key={m.periodo} className={`p-4 rounded-lg ${isDark ? c.darkBg : c.bg}`}>
                    <p className="text-xs text-gray-500 dark:text-gray-400">Média {m.label}</p>
                    <p className={`text-2xl font-bold ${c.text}`}>
                      {m.media?.toFixed(1) || '0'}
                    </p>
                    <p className="text-[10px] text-gray-400 mt-1">{m.total || 0} vendas em {m.dias}d</p>
                  </div>
                );
              })}
            </div>
          </>
        ) : (
          <div className="flex items-center justify-center h-40 text-gray-500 dark:text-gray-400">
            Sem dados disponíveis para este evento.
          </div>
        )}
      </div>

      <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-6">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-4">
          <div className="flex flex-col gap-1">
            <div className="flex items-center gap-2">
              <Activity className="w-5 h-5 text-blue-500" />
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
                Curva Comparativa: {curvaAnoAnterior} vs {curvaAnoAtual}
              </h3>
            </div>
            {curvaModo === 'dias_antes_evento' && (dataEventoAtual || dataEventoAnterior) && (
              <p className="text-xs text-gray-500 dark:text-gray-400 ml-7">
                Alinhado por dias antes do evento
                {dataEventoAtual && ` | ${curvaAnoAtual}: ${new Date(dataEventoAtual + 'T12:00:00').toLocaleDateString('pt-BR')}`}
                {dataEventoAnterior && ` | ${curvaAnoAnterior}: ${new Date(dataEventoAnterior + 'T12:00:00').toLocaleDateString('pt-BR')}`}
              </p>
            )}
          </div>
          <div className="flex items-center gap-2">
            <div className="flex rounded-lg border border-gray-300 dark:border-gray-600 overflow-hidden">
              <button
                onClick={() => setCurvaMode('vendas')}
                className={`px-3 py-1.5 text-xs font-medium transition-colors ${
                  curvaMode === 'vendas' 
                    ? 'bg-blue-500 text-white' 
                    : 'bg-white dark:bg-gray-700 text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-600'
                }`}
              >
                Inscrições
              </button>
              <button
                onClick={() => setCurvaMode('receita')}
                className={`px-3 py-1.5 text-xs font-medium transition-colors ${
                  curvaMode === 'receita' 
                    ? 'bg-blue-500 text-white' 
                    : 'bg-white dark:bg-gray-700 text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-600'
                }`}
              >
                Receita
              </button>
            </div>
            <div className="flex rounded-lg border border-gray-300 dark:border-gray-600 overflow-hidden">
              <button
                onClick={() => setCurvaView('semanal')}
                className={`px-3 py-1.5 text-xs font-medium transition-colors ${
                  curvaView === 'semanal' 
                    ? 'bg-blue-500 text-white' 
                    : 'bg-white dark:bg-gray-700 text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-600'
                }`}
              >
                Semanal
              </button>
              <button
                onClick={() => setCurvaView('acumulado')}
                className={`px-3 py-1.5 text-xs font-medium transition-colors ${
                  curvaView === 'acumulado' 
                    ? 'bg-blue-500 text-white' 
                    : 'bg-white dark:bg-gray-700 text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-600'
                }`}
              >
                Acumulado
              </button>
            </div>
          </div>
        </div>

        {curvaLoading ? (
          <div className="flex items-center justify-center h-64">
            <Loader2 className="w-8 h-8 animate-spin text-blue-500" />
            <span className="ml-3 text-gray-500 dark:text-gray-400">Carregando curva comparativa...</span>
          </div>
        ) : curvaData.length === 0 ? (
          <div className="flex items-center justify-center h-64 text-gray-500 dark:text-gray-400">
            Sem dados disponíveis para a curva comparativa deste evento.
          </div>
        ) : curvaView === 'semanal' && curvaMode === 'vendas' ? (
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={curvaData} margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={isDark ? '#374151' : '#e5e7eb'} />
              <XAxis dataKey="label" stroke={isDark ? '#9ca3af' : '#6b7280'} tick={{ fontSize: 10 }} interval={Math.max(0, Math.floor(curvaData.length / 12))} angle={-45} textAnchor="end" height={50} />
              <YAxis stroke={isDark ? '#9ca3af' : '#6b7280'} tick={{ fontSize: 12 }} />
              <Tooltip
                contentStyle={{ 
                  backgroundColor: isDark ? '#1f2937' : '#fff',
                  border: `1px solid ${isDark ? '#374151' : '#e5e7eb'}`,
                  borderRadius: '8px',
                  color: isDark ? '#fff' : '#111'
                }}
                formatter={(value: any) => [formatNumber(Number(value || 0)), '']}
                labelFormatter={(label: any) => `${label} (semana)`}
              />
              <Legend />
              <Bar dataKey={`vendas_${curvaAnoAnterior}`} name={`${curvaAnoAnterior}`} fill="#94a3b8" radius={[4, 4, 0, 0]} />
              <Bar dataKey={`vendas_${curvaAnoAtual}`} name={`${curvaAnoAtual}`} fill="#3b82f6" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        ) : curvaView === 'semanal' && curvaMode === 'receita' ? (
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={curvaData} margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={isDark ? '#374151' : '#e5e7eb'} />
              <XAxis dataKey="label" stroke={isDark ? '#9ca3af' : '#6b7280'} tick={{ fontSize: 10 }} interval={Math.max(0, Math.floor(curvaData.length / 12))} angle={-45} textAnchor="end" height={50} />
              <YAxis stroke={isDark ? '#9ca3af' : '#6b7280'} tick={{ fontSize: 12 }} tickFormatter={(v) => `R$${(v/1000).toFixed(0)}k`} />
              <Tooltip
                contentStyle={{ 
                  backgroundColor: isDark ? '#1f2937' : '#fff',
                  border: `1px solid ${isDark ? '#374151' : '#e5e7eb'}`,
                  borderRadius: '8px',
                  color: isDark ? '#fff' : '#111'
                }}
                formatter={(value: any) => [formatCurrency(Number(value || 0)), '']}
                labelFormatter={(label: any) => `${label} (semana)`}
              />
              <Legend />
              <Bar dataKey={`receita_${curvaAnoAnterior}`} name={`${curvaAnoAnterior}`} fill="#94a3b8" radius={[4, 4, 0, 0]} />
              <Bar dataKey={`receita_${curvaAnoAtual}`} name={`${curvaAnoAtual}`} fill="#10b981" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        ) : (() => {
          const hasProjecao = curvaData.some((d: any) => d[`projecao_acumulado_${curvaAnoAtual}`] !== undefined);
          const pctKey = curvaMode === 'vendas' ? `pct_meta_vendas_${curvaAnoAtual}` : `pct_meta_receita_${curvaAnoAtual}`;
          const pctAntKey = curvaMode === 'vendas' ? `pct_meta_vendas_${curvaAnoAnterior}` : `pct_meta_receita_${curvaAnoAnterior}`;
          const pctProjKey = curvaMode === 'vendas' ? `pct_meta_projecao_vendas_${curvaAnoAtual}` : `pct_meta_projecao_receita_${curvaAnoAtual}`;
          const acumKey = curvaMode === 'vendas' ? `acumulado_${curvaAnoAtual}` : `acumulado_receita_${curvaAnoAtual}`;
          const acumAntKey = curvaMode === 'vendas' ? `acumulado_${curvaAnoAnterior}` : `acumulado_receita_${curvaAnoAnterior}`;

          let chartData = curvaData.map((d: any) => {
            const entry = { ...d };
            const isProj = d.is_projecao === true;
            if (hasProjecao) {
              if (isProj) {
                entry[`realizado_pct_${curvaAnoAtual}`] = undefined;
              } else {
                entry[`realizado_pct_${curvaAnoAtual}`] = d[pctKey];
              }
              if (d[pctProjKey] !== undefined) {
                entry[`projecao_pct_${curvaAnoAtual}`] = d[pctProjKey];
              }
            }
            return entry;
          });

          const strokeColor = curvaMode === 'vendas' ? '#3b82f6' : '#10b981';

          return (
            <ResponsiveContainer width="100%" height={320}>
              <LineChart data={chartData} margin={{ top: 10, right: 30, left: 20, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke={isDark ? '#374151' : '#e5e7eb'} />
                <XAxis dataKey="label" stroke={isDark ? '#9ca3af' : '#6b7280'} tick={{ fontSize: 10 }} interval={Math.max(0, Math.floor(chartData.length / 12))} angle={-45} textAnchor="end" height={50} />
                <YAxis 
                  stroke={isDark ? '#9ca3af' : '#6b7280'} 
                  tick={{ fontSize: 12 }}
                  tickFormatter={(v: number) => `${v}%`}
                  domain={[0, (dataMax: number) => Math.max(110, Math.ceil(dataMax / 10) * 10 + 10)]}
                />
                <Tooltip
                  contentStyle={{ 
                    backgroundColor: isDark ? '#1f2937' : '#fff',
                    border: `1px solid ${isDark ? '#374151' : '#e5e7eb'}`,
                    borderRadius: '8px',
                    color: isDark ? '#fff' : '#111'
                  }}
                  formatter={(value: any, name?: string, props?: any) => {
                    if (value === undefined || value === null) return [null, null];
                    const pctFormatted = `${Number(value).toFixed(1)}%`;
                    const d = props?.payload;
                    let absVal = '';
                    if (d) {
                      if ((name || '').includes(String(curvaAnoAnterior))) {
                        const abs = d[acumAntKey];
                        absVal = abs !== undefined ? ` (${curvaMode === 'receita' ? formatCurrency(abs) : formatNumber(abs)})` : '';
                      } else {
                        const abs = d[acumKey] || d[`projecao_acumulado_${curvaAnoAtual}`] || d[`projecao_acumulado_receita_${curvaAnoAtual}`];
                        absVal = abs !== undefined ? ` (${curvaMode === 'receita' ? formatCurrency(abs) : formatNumber(abs)})` : '';
                      }
                    }
                    const suffix = (name || '').includes('Projeção') ? ' (projeção)' : '';
                    return [`${pctFormatted}${absVal}${suffix}`, ''];
                  }}
                  labelFormatter={(label: any) => `${label}`}
                />
                <Legend />
                <Line 
                  type="monotone" 
                  dataKey={pctAntKey}
                  name={`${curvaAnoAnterior} (% meta)`} 
                  stroke="#94a3b8" 
                  strokeWidth={2} 
                  dot={{ r: 3, fill: '#94a3b8' }} 
                  strokeDasharray="5 5"
                />
                {hasProjecao ? (
                  <>
                    <Line 
                      type="monotone" 
                      dataKey={`realizado_pct_${curvaAnoAtual}`}
                      name={`${curvaAnoAtual} Realizado`}
                      stroke={strokeColor}
                      strokeWidth={2.5} 
                      dot={{ r: 3, fill: strokeColor }}
                      connectNulls={false}
                    />
                    <Line 
                      type="monotone" 
                      dataKey={`projecao_pct_${curvaAnoAtual}`}
                      name={`${curvaAnoAtual} Projeção`}
                      stroke="#8B5CF6"
                      strokeWidth={2} 
                      strokeDasharray="8 4"
                      strokeOpacity={0.85}
                      dot={{ r: 2, fill: '#8B5CF6', fillOpacity: 0.7 }}
                    />
                  </>
                ) : (
                  <Line 
                    type="monotone" 
                    dataKey={pctKey}
                    name={`${curvaAnoAtual} (% meta)`} 
                    stroke={strokeColor}
                    strokeWidth={2.5} 
                    dot={{ r: 3, fill: strokeColor }} 
                  />
                )}
              </LineChart>
            </ResponsiveContainer>
          );
        })()}

        {!curvaLoading && curvaData.length > 0 && curvaMeta && (
          <div className="mt-4 space-y-3">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              {(() => {
                const m = curvaMeta;
                const isVendas = curvaMode === 'vendas';
                const acumAnteriorMesmoD = isVendas ? m.ultimo_acum_vendas_anterior_mesmo_d : m.ultimo_acum_receita_anterior_mesmo_d;
                const pctAnteriorMesmoD = isVendas ? m.pct_anterior_vendas_mesmo_d : m.pct_anterior_receita_mesmo_d;
                const varMesmoD = isVendas ? (m.variacao_mesmo_d_vendas ?? 0) : (m.variacao_mesmo_d_receita ?? 0);
                const ritmo = isVendas ? (m.ritmo_diario_necessario_vendas ?? 0) : (m.ritmo_diario_necessario_receita ?? 0);
                const diasAteEvento = m.dias_ate_evento ?? 0;
                const metaRef = isVendas ? (m.meta_orcada > 0 ? m.meta_orcada : m.total_vendas_anterior) : m.total_receita_anterior;
                const totalAtual = isVendas ? m.total_vendas_atual : m.total_receita_atual;
                const faltam = Math.max(0, metaRef - totalAtual);
                const fmt = (v: number) => isVendas ? formatNumber(Math.round(v)) : formatCurrency(v);
                const label = isVendas ? 'inscrições' : 'receita';

                const InfoTooltip = ({ text }: { text: string }) => (
                  <div className="group relative inline-flex ml-1">
                    <Info className="w-3.5 h-3.5 text-gray-400 dark:text-gray-500 cursor-help" />
                    <div className="invisible group-hover:visible absolute bottom-full left-1/2 -translate-x-1/2 mb-2 w-56 p-2 text-xs text-white bg-gray-900 dark:bg-gray-700 rounded-lg shadow-lg z-50 leading-relaxed">
                      {text}
                      <div className="absolute top-full left-1/2 -translate-x-1/2 border-4 border-transparent border-t-gray-900 dark:border-t-gray-700" />
                    </div>
                  </div>
                );

                return (
                  <>
                    <div className={`p-3 rounded-xl ${isDark ? 'bg-gray-700/50 border border-gray-600' : 'bg-gray-50 border border-gray-200'}`}>
                      <div className="flex items-center gap-1 mb-1">
                        <p className="text-xs text-gray-500 dark:text-gray-400">No mesmo D- em {curvaAnoAnterior}</p>
                        <InfoTooltip text={`Quantas ${label} o evento de ${curvaAnoAnterior} tinha acumulado faltando o mesmo número de dias (D-${diasAteEvento}) para o evento. Permite comparar o ritmo de vendas no mesmo momento da jornada.`} />
                      </div>
                      {acumAnteriorMesmoD > 0 ? (
                        <>
                          <p className="text-lg font-bold text-gray-600 dark:text-gray-300">{fmt(acumAnteriorMesmoD)}</p>
                          <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">
                            {pctAnteriorMesmoD}% do total final de {curvaAnoAnterior}
                          </p>
                        </>
                      ) : (
                        <p className="text-sm text-gray-400 dark:text-gray-500 mt-1">Sem dados de {curvaAnoAnterior}</p>
                      )}
                    </div>

                    <div className={`p-3 rounded-xl border-2 ${
                      varMesmoD >= 0 
                        ? 'border-green-400/50 bg-green-50 dark:bg-green-900/20 dark:border-green-500/30' 
                        : 'border-red-400/50 bg-red-50 dark:bg-red-900/20 dark:border-red-500/30'
                    }`}>
                      <div className="flex items-center gap-1 mb-1">
                        <p className="text-xs text-gray-500 dark:text-gray-400">Variação vs {curvaAnoAnterior} (mesmo D-)</p>
                        <InfoTooltip text={`Variação percentual das ${label} de ${curvaAnoAtual} comparado com ${curvaAnoAnterior} no mesmo D-${diasAteEvento} (mesma distância do evento). Positivo = melhor que o ano anterior neste momento.`} />
                      </div>
                      <div className="flex items-center gap-1.5">
                        {varMesmoD >= 0 ? (
                          <TrendingUp className="w-5 h-5 text-green-600 dark:text-green-400" />
                        ) : (
                          <TrendingDown className="w-5 h-5 text-red-600 dark:text-red-400" />
                        )}
                        <span className={`text-lg font-bold ${varMesmoD >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}>
                          {varMesmoD >= 0 ? '+' : ''}{varMesmoD.toFixed(1)}%
                        </span>
                      </div>
                      <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">
                        {curvaAnoAtual}: {fmt(totalAtual)} vs {curvaAnoAnterior}: {fmt(acumAnteriorMesmoD)}
                      </p>
                    </div>

                    <div className={`p-3 rounded-xl ${isDark ? 'bg-amber-900/20 border border-amber-500/30' : 'bg-amber-50 border border-amber-200'}`}>
                      <div className="flex items-center gap-1 mb-1">
                        <p className="text-xs text-gray-500 dark:text-gray-400">Ritmo Diário Necessário</p>
                        <InfoTooltip text={`Quantidade de ${label} por dia necessária nos próximos ${diasAteEvento} dias restantes para atingir a meta${isVendas && m.meta_orcada > 0 ? ` orçada de ${formatNumber(m.meta_orcada)}` : ''}. Calculado como: (meta - acumulado atual) / dias restantes.`} />
                      </div>
                      <p className="text-lg font-bold text-amber-600 dark:text-amber-400">{fmt(ritmo)}<span className="text-xs font-normal text-gray-400">/dia</span></p>
                      <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">
                        Faltam {fmt(faltam)} em {diasAteEvento} dias
                      </p>
                    </div>
                  </>
                );
              })()}
            </div>
          </div>
        )}
      </div>

      <EventInsights eventoId={id!} ano={anoParam} />

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
                      {(() => {
                        const actionDate = new Date(action.date + 'T00:00:00');
                        const now = new Date();
                        const diffDays = Math.floor((now.getTime() - actionDate.getTime()) / (1000 * 60 * 60 * 24));
                        if (diffDays <= 7 && diffDays >= 0) {
                          return (
                            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-gradient-to-r from-green-500/20 to-emerald-500/20 border border-green-400/50 dark:border-green-600/50">
                              <span className="relative flex h-2 w-2">
                                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
                                <span className="relative inline-flex rounded-full h-2 w-2 bg-green-500"></span>
                              </span>
                              <span className="text-[10px] font-bold text-green-700 dark:text-green-400 uppercase tracking-wider">Ativa</span>
                              <span className="text-[10px] text-green-600 dark:text-green-400 font-mono">{7 - diffDays}d</span>
                            </span>
                          );
                        }
                        return null;
                      })()}
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

      {isConsolidated && projetosVinculados.length > 0 && (
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
      </>
      )}
      </div>
    </div>
  );
};

export default EventDetail;
