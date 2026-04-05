import React, { useState, useEffect, useRef, lazy, Suspense } from 'react';
import { useParams, useNavigate, useSearchParams, useLocation, Link } from 'react-router-dom';
import ConnectionAlert from '../../components/common/ConnectionAlert';
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
  RefreshCw,
  TableProperties,
  ChevronDown,
  Archive
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
import { marketingService, MarketingEvent, clearMarketingDashboardCache } from '../../services/api';
import { 
  getISCColor, 
  getISCEmoji, 
  isInCriticalWindow,
  getISCStatus
} from '../../types/marketingPerformance';
import { useTheme } from '../../context/ThemeContext';
import EventInsights from './EventInsights';
import EventSimulator from './EventSimulator';
import DailySalesTable from './DailySalesTable';

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
  ponto_corte?: string;
  estagio?: string;
  snapshot_isc?: number;
  snapshot_isc_state?: string;
  snapshot_d_minus?: number;
  snapshot_ia730?: number;
  snapshot_rolling14d?: number;
  snapshot_curva_percent?: number;
  snapshot_vendas_acumuladas?: number;
  snapshot_playbook_letter?: string;
}

interface ExtendedEvent extends MarketingEvent {
  dailySales?: { date: string; sales: number; expected: number; cumulativeSales?: number; cumulativeExpected?: number; dMinus?: number; curvaAnoAnterior?: number; dif?: number; atingimentoAcumulado?: number; atingimentoDiario?: number; normalizedSales?: number; cumulativeNormalized?: number; localMedian?: number | null; outlierLimit?: number | null; isOutlier?: boolean; excessRemoved?: number; excessReceived?: number }[];
  commercialActions?: CommercialAction[];
}

const EventDetail: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const { isDark } = useTheme();
  const anoParam = searchParams.get('ano') ? parseInt(searchParams.get('ano')!) : undefined;
  const previewEvent = (location.state as any)?.previewEvent as MarketingEvent | undefined;
  const [event, setEvent] = useState<ExtendedEvent | null>(previewEvent ? { ...previewEvent } : null);
  const [loading, setLoading] = useState(!previewEvent);
  const [detailsLoading, setDetailsLoading] = useState(!!previewEvent);
  const [error, setError] = useState<string | null>(null);
  const [showActionModal, setShowActionModal] = useState(false);
  const [showMargemInfo, setShowMargemInfo] = useState(false);
  const [showReceitaOrcada, setShowReceitaOrcada] = useState(false);
  const [showReceitaRealizada, setShowReceitaRealizada] = useState(false);
  const [showDetalheVendas, setShowDetalheVendas] = useState(false);
  const getTodayLocalDate = () => {
    const now = new Date();
    return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
  };

  const [actionForm, setActionForm] = useState({
    tipo: 'PROMOCAO',
    descricao: '',
    data_acao: getTodayLocalDate(),
    projeto_id_selecionado: 0,
    forced_ponto_corte: '',
    forced_estagio: '',
  });
  const [savingAction, setSavingAction] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [projetosVinculados, setProjetosVinculados] = useState<{id: number; nome: string; sku: string}[]>([]);
  const [comparacaoAnual, setComparacaoAnual] = useState<any>(null);
  const [anosDisponiveis, setAnosDisponiveis] = useState<number[]>([]);
  const [avisos, setAvisos] = useState<string[]>([]);
  const [curvaData, setCurvaData] = useState<any[]>([]);
  const [curvaMeta, setCurvaMeta] = useState<any>(null);
  const [curvaAnoAtual, setCurvaAnoAtual] = useState<number>(new Date().getFullYear());
  const [curvaAnoAnterior, setCurvaAnoAnterior] = useState<number>(new Date().getFullYear() - 1);
  const [activeTab, setActiveTab] = useState<'dashboard' | 'simulator' | 'complementares' | 'controle'>('dashboard');
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
  const [refreshSuccess, setRefreshSuccess] = useState(false);
  const [chartPeriod, setChartPeriod] = useState<number | null>(null);
  const [attainmentPeriod, setAttainmentPeriod] = useState<number | null>(30);
  const [attainmentMode, setAttainmentMode] = useState<'acumulado' | 'diario'>('acumulado');
  const [controleSubTab, setControleSubTab] = useState<'tabela' | 'curva'>('tabela');
  const [curvaSnapshot, setCurvaSnapshot] = useState<{ evento_grupo: string; ano_referencia: number; sales_goal: number; data: { d_minus: number; percentual_acumulado: number; percentual_dia: number; meta_acumulado: number; meta_dia: number }[]; message?: string } | null>(null);
  const [curvaSnapshotLoading, setCurvaSnapshotLoading] = useState(false);
  const [showNormalized, setShowNormalized] = useState(false);
  const [showNormalizationDetail, setShowNormalizationDetail] = useState(false);
  const [isStaleData, setIsStaleData] = useState(false);
  const [ultimaAtualizacao, setUltimaAtualizacao] = useState<string | null>(null);
  const silentRefetchDoneRef = useRef(false);
  const fetchEventRef = useRef<((forceRefresh?: boolean, silent?: boolean) => void) | null>(null);

  const isConsolidated = id?.startsWith('grp_') ?? false;
  const abortControllerRef = useRef<AbortController | null>(null);
  const curvaAbortRef = useRef<AbortController | null>(null);
  const staleRetryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    silentRefetchDoneRef.current = false;
    const controller = new AbortController();
    abortControllerRef.current = controller;

    const fetchEvent = async (forceRefresh = false, silent = false) => {
      if (!id) {
        setError('ID do evento não fornecido');
        setLoading(false);
        setDetailsLoading(false);
        return;
      }
      
      try {
        if (!forceRefresh) {
          if (!event) setLoading(true);
        }
        if (!silent && previewEvent) setDetailsLoading(true);
        const response = await marketingService.getEventoById(id, controller.signal, anoParam, forceRefresh || undefined);
        if (controller.signal.aborted) return;

        const stale = response._isStale === true;
        setIsStaleData(stale);

        const eventWithData = {
          ...response.evento,
          dailySales: response.dailySales?.map(d => ({
            date: d.date,
            sales: d.sales,
            expected: d.expected,
            cumulativeSales: d.cumulativeSales,
            cumulativeExpected: d.cumulativeExpected,
            dMinus: d.dMinus,
            curvaAnoAnterior: d.curvaAnoAnterior,
            dif: d.dif,
            atingimentoAcumulado: d.atingimentoAcumulado,
            atingimentoDiario: d.atingimentoDiario,
            normalizedSales: d.normalizedSales,
            cumulativeNormalized: d.cumulativeNormalized,
            localMedian: d.localMedian,
            outlierLimit: d.outlierLimit,
            isOutlier: d.isOutlier,
            excessRemoved: d.excessRemoved,
            excessReceived: d.excessReceived
          })),
          commercialActions: mapEventResponseToActions(response.commercialActions ?? [])
        };
        setEvent(eventWithData);
        const cacheTime: string | undefined = (response as any).ultima_atualizacao;
        const systemRefresh: string | undefined = (response as any).ultima_atualizacao_completa;
        // Display uses last full-system refresh time for consistency with the dashboard
        setUltimaAtualizacao(systemRefresh || cacheTime || null);
        // If the event cache is older than the last full refresh, silently refetch once
        if (
          !forceRefresh &&
          !silentRefetchDoneRef.current &&
          cacheTime &&
          systemRefresh &&
          new Date(cacheTime) < new Date(systemRefresh)
        ) {
          silentRefetchDoneRef.current = true;
          fetchEvent(true, true);
          return;
        }
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
        if (!event) setError('Erro ao carregar dados do evento');
      } finally {
        if (!controller.signal.aborted) {
          setLoading(false);
          setDetailsLoading(false);
        }
      }
    };
    
    fetchEventRef.current = fetchEvent;
    fetchEvent();
    return () => {
      controller.abort();
      if (staleRetryTimerRef.current) {
        clearTimeout(staleRetryTimerRef.current);
        staleRetryTimerRef.current = null;
      }
    };
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
          setCurvaMeta((response as any).meta || null);
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

  useEffect(() => {
    if (!id || controleSubTab !== 'curva') return;
    if (curvaSnapshot !== null) return;
    const controller = new AbortController();
    const fetchSnapshot = async () => {
      setCurvaSnapshotLoading(true);
      try {
        const data = await marketingService.getCurvaSnapshot(id, controller.signal, anoParam);
        if (!controller.signal.aborted) {
          setCurvaSnapshot(data);
        }
      } catch (err: any) {
        if (err?.name !== 'AbortError' && err?.code !== 'ERR_CANCELED') {
          console.error('Error fetching curva snapshot:', err);
        }
      } finally {
        if (!controller.signal.aborted) {
          setCurvaSnapshotLoading(false);
        }
      }
    };
    fetchSnapshot();
    return () => controller.abort();
  }, [id, controleSubTab, anoParam]);

  const handleForceRefresh = async () => {
    if (!id || refreshing) return;
    setRefreshing(true);
    try {
      const result = await marketingService.atualizarHoje(id, anoParam);
      const todayStr = new Date().toISOString().split('T')[0];
      setEvent(prev => {
        if (!prev) return prev;
        const updatedDailySales = prev.dailySales ? prev.dailySales.map(d => {
          if (d.date === todayStr) {
            return { ...d, sales: result.hoje_total };
          }
          return d;
        }) : prev.dailySales;
        const todayExists = prev.dailySales?.some(d => d.date === todayStr);
        const finalDailySales = (!todayExists && result.hoje_total > 0 && prev.dailySales)
          ? [...prev.dailySales, { date: todayStr, sales: result.hoje_total, expected: 0, cumulativeSales: result.hoje_total, cumulativeExpected: 0 }]
          : updatedDailySales;
        return {
          ...prev,
          currentSales: (result.total_acumulado > 0 && result.total_acumulado >= (prev.currentSales || 0))
            ? result.total_acumulado
            : prev.currentSales,
          dailySales: finalDailySales
        };
      });
      clearMarketingDashboardCache();
      setIsStaleData(false);
      setRefreshSuccess(true);
      setTimeout(() => setRefreshSuccess(false), 4000);
      if (staleRetryTimerRef.current) {
        clearTimeout(staleRetryTimerRef.current);
        staleRetryTimerRef.current = null;
      }
    } catch (err: any) {
      console.error('Erro ao atualizar vendas de hoje:', err);
    } finally {
      setRefreshing(false);
    }
  };

  if (!event && (loading || error)) {
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

  if (!event) {
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
        <div className="bg-white dark:bg-gray-800 rounded-xl p-12 flex flex-col items-center justify-center">
          <Loader2 className="w-8 h-8 animate-spin text-blue-600" />
          <p className="mt-4 text-gray-500 dark:text-gray-400">Carregando dados do evento...</p>
        </div>
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

  const getActionCutoffInfo = (dMinus: number): { ponto_corte: string; estagio: string } => {
    if (dMinus >= 50) {
      return { ponto_corte: dMinus >= 70 ? 'D-70' : 'D-50', estagio: 'analitico' };
    } else if (dMinus >= 32) {
      return { ponto_corte: dMinus >= 45 ? 'D-45' : 'D-35', estagio: 'estrategico' };
    } else {
      return { ponto_corte: dMinus >= 15 ? 'D-30' : 'D-15', estagio: 'operacional' };
    }
  };

  const mapEventResponseToActions = (actions: any[]): CommercialAction[] =>
    actions.map((a: any) => ({
      id: a.id,
      type: a.type as CommercialAction['type'],
      description: a.description,
      date: a.date,
      impact: a.impact,
      vendas_antes: a.vendas_antes,
      vendas_depois: a.vendas_depois,
      impacto_percentual: a.impacto_percentual,
      status_impacto: a.status_impacto,
      ponto_corte: a.ponto_corte,
      estagio: a.estagio,
      snapshot_isc: a.snapshot_isc,
      snapshot_isc_state: a.snapshot_isc_state,
      snapshot_d_minus: a.snapshot_d_minus,
      snapshot_ia730: a.snapshot_ia730,
      snapshot_rolling14d: a.snapshot_rolling14d,
      snapshot_curva_percent: a.snapshot_curva_percent,
      snapshot_vendas_acumuladas: a.snapshot_vendas_acumuladas,
      snapshot_playbook_letter: a.snapshot_playbook_letter,
    }));

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
      const dMinus = event?.dMinus ?? 0;
      const dMinusInscricoes = event?.dMinusInscricoes ?? dMinus;
      const cutoffInfo = actionForm.forced_ponto_corte && actionForm.forced_estagio
        ? { ponto_corte: actionForm.forced_ponto_corte, estagio: actionForm.forced_estagio }
        : getActionCutoffInfo(dMinus);
      const iscStatusMap: Record<string, string> = {
        accelerating: 'forte',
        stable: 'estavel',
        decelerating: 'fraco'
      };

      const snapshotData = {
        snapshot_isc: event?.isc,
        snapshot_isc_state: event?.iscStatus ? iscStatusMap[event.iscStatus] : undefined,
        snapshot_d_minus: dMinusInscricoes,
        snapshot_ia730: event?.iscComponents?.ia730,
        snapshot_rolling14d: event?.iscComponents?.rolling14d,
        snapshot_curva_percent: event?.iscComponents?.curvaDPercent,
        snapshot_vendas_acumuladas: event?.currentSales,
        snapshot_playbook_letter: event?.suggestedAction?.letter,
      };

      const result = await marketingService.createAcaoComercial({
        projeto_id: projetoIdParaAcao,
        tipo: actionForm.tipo,
        descricao: actionForm.descricao,
        data_acao: actionForm.data_acao,
        ponto_corte: cutoffInfo.ponto_corte,
        estagio: cutoffInfo.estagio,
        ...snapshotData,
      });

      const newAction: CommercialAction = {
        id: String(result.acao?.id ?? Date.now()),
        type: actionForm.tipo === 'AUMENTO_PRECO' ? 'price_increase'
            : actionForm.tipo === 'REDUCAO_PRECO' ? 'price_decrease'
            : actionForm.tipo === 'CAMPANHA' ? 'campaign'
            : actionForm.tipo === 'COMUNICACAO' ? 'communication'
            : 'promotion',
        description: actionForm.descricao,
        date: actionForm.data_acao,
        impact: undefined,
        impacto_percentual: undefined,
        vendas_antes: undefined,
        vendas_depois: undefined,
        status_impacto: undefined,
        ponto_corte: cutoffInfo.ponto_corte,
        estagio: cutoffInfo.estagio,
        ...snapshotData,
      };

      setEvent(prev => prev ? {
        ...prev,
        commercialActions: [...(prev.commercialActions ?? []), newAction]
      } : prev);

      setShowActionModal(false);
      setActionError(null);
      setActionForm({
        tipo: 'PROMOCAO',
        descricao: '',
        data_acao: getTodayLocalDate(),
        projeto_id_selecionado: 0,
        forced_ponto_corte: '',
        forced_estagio: '',
      });

    } catch (err: any) {
      if (err?.name === 'CanceledError' || err?.code === 'ERR_CANCELED') return;
      console.error('Erro ao salvar ação:', err);
      setActionError('Erro ao salvar ação. Tente novamente.');
    } finally {
      setSavingAction(false);
    }
  };

  const handleDeleteAction = async (actionId: string) => {
    if (!id) return;
    const previousActions = event?.commercialActions;
    setEvent(prev => prev ? {
      ...prev,
      commercialActions: prev.commercialActions?.filter(a => a.id !== actionId)
    } : prev);
    try {
      await marketingService.deleteAcaoComercial(parseInt(actionId));
    } catch (err) {
      console.error('Erro ao excluir ação:', err);
      setEvent(prev => prev ? { ...prev, commercialActions: previousActions } : prev);
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
    const prevNormalized = index > 0 ? acc[index - 1].cumulativeNormalized : 0;
    const normDaily = day.normalizedSales ?? day.sales;
    
    acc.push({
      date: day.date,
      cumulative: prevCumulative + day.sales,
      cumulativeExpected: day.cumulativeExpected != null ? day.cumulativeExpected : (prevExpected + day.expected),
      daily: day.sales,
      cumulativeNormalized: day.cumulativeNormalized ?? (prevNormalized + normDaily),
      normalizedDaily: normDaily
    });
    
    return acc;
  }, [] as { date: string; cumulative: number; cumulativeExpected: number; daily: number; cumulativeNormalized: number; normalizedDaily: number }[]);

  const filteredCumulativeData = chartPeriod
    ? cumulativeData.slice(-chartPeriod)
    : cumulativeData;

  const todayStr = new Date().toISOString().split('T')[0];

  const parsedEventDate = event.date ? new Date(event.date + 'T12:00:00') : null;
  const hasValidEventDate = parsedEventDate && !isNaN(parsedEventDate.getTime());

  const goalAttainmentData = cumulativeData
    .filter(d => d.cumulativeExpected > 0)
    .map(d => {
      let dMinusInsc = 0;
      if (hasValidEventDate) {
        const dayDate = new Date(d.date + 'T12:00:00');
        const diffMs = parsedEventDate!.getTime() - dayDate.getTime();
        const dMinusEvento = Math.round(diffMs / (1000 * 60 * 60 * 24));
        dMinusInsc = Math.max(0, dMinusEvento - 2);
      }
      const pct = parseFloat((((d.cumulative / d.cumulativeExpected) * 100) - 100).toFixed(1));
      return {
        date: d.date,
        dMinus: dMinusInsc,
        label: `D-${dMinusInsc}`,
        percentual: pct,
        cumulative: Math.round(d.cumulative),
        cumulativeExpected: Math.round(d.cumulativeExpected),
      };
    });

  const goalAttainmentDailyData = (event.dailySales || [])
    .filter(d => d.expected > 0)
    .map(d => {
      let dMinusInsc = 0;
      if (hasValidEventDate) {
        const dayDate = new Date(d.date + 'T12:00:00');
        const diffMs = parsedEventDate!.getTime() - dayDate.getTime();
        const dMinusEvento = Math.round(diffMs / (1000 * 60 * 60 * 24));
        dMinusInsc = Math.max(0, dMinusEvento - 2);
      }
      const pct = parseFloat((((d.sales / d.expected) * 100) - 100).toFixed(1));
      return {
        date: d.date,
        dMinus: dMinusInsc,
        label: `D-${dMinusInsc}`,
        percentual: pct,
        sales: Math.round(d.sales),
        expected: Math.round(d.expected),
      };
    });

  const activeAttainmentData = attainmentMode === 'acumulado' ? goalAttainmentData : goalAttainmentDailyData;
  const filteredAttainmentData = attainmentPeriod ? activeAttainmentData.slice(-attainmentPeriod) : activeAttainmentData;

  const dailySalesArr = event.dailySales || [];
  const todayDailySale = dailySalesArr.find(d => d.date === todayStr);
  const lastDailySale = dailySalesArr.length > 0 ? dailySalesArr[dailySalesArr.length - 1] : null;
  const hasTodayData = !!todayDailySale;
  const todaySales = todayDailySale?.sales ?? 0;
  const todayExpectedRounded = Math.round(todayDailySale?.expected ?? 0);
  const todayPct = todayExpectedRounded > 0 ? Math.round((todaySales / todayExpectedRounded) * 100) : (todaySales > 0 ? 100 : 0);
  // Usa o último ponto do cumulativo (incluindo hoje se houver dados),
  // para alinhar com o gráfico Atingimento que também inclui hoje.
  const lastCumData = cumulativeData.length > 0
    ? cumulativeData[cumulativeData.length - 1]
    : null;
  const metaAcumulada = lastCumData ? Math.round(lastCumData.cumulativeExpected) : 0;
  const inscritosTotal = lastCumData ? Math.round(lastCumData.cumulative) : 0;
  // currentSales é a fonte única de verdade: backend garante que é sempre >= inscritosTotal
  const totalInscritos = (event.currentSales != null && event.currentSales > 0) ? event.currentSales : inscritosTotal;
  const acumuladoGap = metaAcumulada > 0 ? Math.round(((totalInscritos - metaAcumulada) / metaAcumulada) * 100) : (totalInscritos > 0 ? 100 : 0);

  const completeDailySales = (event.dailySales || []).filter(d => d.date < todayStr);
  const last30Days = completeDailySales.slice(-30);
  // Total acumulado apenas de dias fechados (exclui o dia atual, que é parcial).
  // Usado nos cards que devem refletir somente inscrições consolidadas até ontem.
  const totalInscritosConsolidado = completeDailySales.reduce((sum, d) => sum + d.sales, 0);

  const _rawDMinusCalc = event.dMinusInscricoes != null ? event.dMinusInscricoes : (event.dMinus != null ? Math.max(0, event.dMinus - 2) : 0);
  const dMinusCalc = isNaN(_rawDMinusCalc) ? 0 : _rawDMinusCalc;
  const _safeDMinus = (event.dMinus != null && !isNaN(event.dMinus)) ? event.dMinus : 0;
  const volumeParaMeta = event.salesGoal - totalInscritos;
  const _kitRowsRealizado = (event.margemPorKit ?? []).filter(r => r.tipoKit !== 'CONSOLIDADO');
  const _kitTotalReceita = _kitRowsRealizado.reduce((s, r) => s + (r.receitaLiquida || 0), 0);
  const _kitTotalQtd = _kitRowsRealizado.reduce((s, r) => s + (r.qtd || 0), 0);
  const ticketMedioRealizado = _kitTotalQtd > 0 ? Math.round((_kitTotalReceita / _kitTotalQtd) * 100) / 100 : (event.averageTicket || 0);
  // Use individual kits when they have data (qtd > 0), otherwise fall back to CONSOLIDADO row.
  // This prevents divergence when CONSOLIDADO has real data but individual kits are zeroed out.
  const _consRowMargem = (event.margemPorKit ?? []).find(r => r.tipoKit === 'CONSOLIDADO')?.margemTotal ?? null;
  const _kitSumMargem = _kitRowsRealizado.reduce((s, r) => s + (r.margemTotal || 0), 0);
  const margemRealizadaKits = _kitRowsRealizado.length > 0 && _kitTotalQtd > 0
    ? _kitSumMargem
    : _consRowMargem ?? null;
  const mediaDiariaNecessaria = dMinusCalc > 0 ? Math.max(volumeParaMeta, 0) / dMinusCalc : 0;
  const last7DaysSales = completeDailySales.slice(-7);
  const mediaSemanaAtual = last7DaysSales.length > 0
    ? last7DaysSales.reduce((sum, d) => sum + d.sales, 0) / last7DaysSales.length
    : 0;
  const pctMedias = mediaDiariaNecessaria > 0
    ? ((mediaSemanaAtual / mediaDiariaNecessaria) * 100) - 100
    : (mediaSemanaAtual > 0 ? 100 : 0);

  const indicadoresVolume = [3, 7, 14, 30].map(dias => {
    const vendas = completeDailySales.slice(-dias);
    const totalVendas = vendas.reduce((sum, d) => sum + d.sales, 0);
    const media = vendas.length > 0 ? totalVendas / vendas.length : 0;
    const potencial = media * dMinusCalc;
    const atingimento = totalInscritosConsolidado + potencial;
    const alvo = event.salesGoal > 0 ? (atingimento / event.salesGoal) - 1 : 0;
    return {
      periodo: dias === 3 ? '3 dias' : dias === 7 ? '1 semana' : dias === 14 ? '14 dias' : '30 dias',
      media: Math.round(media * 10) / 10,
      dMinus: dMinusCalc,
      potencial: Math.round(potencial),
      vendasAcumuladas: totalInscritosConsolidado,
      atingimento: Math.round(atingimento),
      meta: event.salesGoal,
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
    if (dMinusCalc <= 40) {
      return 'bg-orange-50 dark:bg-orange-900/20 border-orange-200 dark:border-orange-800';
    }
    return 'bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800';
  };

  const gaugeRotation = Math.min(Math.max(((event.isc ?? 0) - 0.5) * 180, 0), 180);

  const getDataAgeInfo = () => {
    if (!ultimaAtualizacao) return null;
    const updatedAt = new Date(ultimaAtualizacao);
    const now = new Date();
    const diffMs = now.getTime() - updatedAt.getTime();
    const diffHours = diffMs / (1000 * 60 * 60);
    const diffDays = Math.floor(diffHours / 24);
    const timeStr = updatedAt.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
    const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const yesterdayStart = new Date(todayStart.getTime() - 86400000);
    if (updatedAt >= todayStart) {
      return { label: `Dados atualizados às ${timeStr} de hoje`, color: 'text-green-600 dark:text-green-400', isStale: false };
    } else if (updatedAt >= yesterdayStart) {
      return { label: `Dados de ontem às ${timeStr}`, color: 'text-yellow-600 dark:text-yellow-400', isStale: diffHours > 25 };
    } else {
      return { label: `Dados de ${diffDays} dias atrás (${timeStr})`, color: 'text-red-600 dark:text-red-400', isStale: true };
    }
  };

  const dataAgeInfo = getDataAgeInfo();
  const showDataStaleWarning = dataAgeInfo?.isStale && !refreshing;

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
          <div>
            <div className={`flex items-center gap-2 text-sm ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
              <Link to="/marketing" className="hover:text-blue-600">Dashboard</Link>
              <span>/</span>
              <span className={isDark ? 'text-white' : 'text-gray-900'}>{event.name}</span>
            </div>
            {dataAgeInfo && (
              <div className={`flex items-center gap-1 mt-0.5 text-xs ${dataAgeInfo.color}`}>
                <Clock className="w-3 h-3" />
                <span>{dataAgeInfo.label}</span>
              </div>
            )}
          </div>
        </div>
        <button
          onClick={handleForceRefresh}
          disabled={refreshing}
          className={`flex items-center gap-2 px-4 py-2 rounded-lg bg-blue-100 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400 hover:bg-blue-200 dark:hover:bg-blue-900/50 transition-colors ${refreshing ? 'opacity-50 cursor-not-allowed' : ''}`}
          title="Buscar vendas de hoje do Ativo e Magento (consulta rápida)"
        >
          <RefreshCw className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''}`} />
          <span className="text-sm font-medium">{refreshing ? 'Buscando hoje...' : 'Atualizar Hoje'}</span>
        </button>
      </div>

      {refreshSuccess && (
        <div className="bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-xl p-3 flex items-center gap-3">
          <span className="text-sm text-green-700 dark:text-green-300 font-medium">Vendas de hoje atualizadas com sucesso.</span>
        </div>
      )}

      <ConnectionAlert
        avisos={avisos}
        onRetry={handleForceRefresh}
        retrying={refreshing}
      />

      {detailsLoading && !refreshing && (
        <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-xl p-3 flex items-center gap-3">
          <Loader2 className="w-5 h-5 animate-spin text-blue-600 dark:text-blue-400 flex-shrink-0" />
          <span className="text-sm text-blue-700 dark:text-blue-300">
            {previewEvent ? 'Atualizando dados do evento em tempo real...' : 'Carregando dados completos do evento...'}
          </span>
        </div>
      )}

      <div className="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm border border-gray-200 dark:border-gray-700">
        <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
                {event.name}
              </h1>
              {isInCriticalWindow(dMinusCalc) && (
                <span className="px-3 py-1 text-sm font-medium bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400 rounded-full flex items-center gap-1">
                  <Target className="w-4 h-4" />
                  JANELA CRÍTICA DE DECISÃO
                </span>
              )}
            </div>
            <div className="flex flex-wrap items-center gap-4 mt-2 text-sm text-gray-500 dark:text-gray-400">
              <span className="flex items-center gap-1">
                <Calendar className="w-4 h-4" />
                {event.date
                  ? new Date(event.date + 'T00:00:00').toLocaleDateString('pt-BR', { 
                      day: '2-digit', 
                      month: 'long', 
                      year: 'numeric' 
                    })
                  : 'Data não definida'}
              </span>
              <span className="flex items-center gap-1">
                <MapPin className="w-4 h-4" />
                {event.location}
              </span>
              <span className="flex items-center gap-1">
                <Users className="w-4 h-4" />
                Meta total: {event.totalCapacity != null && !isNaN(event.totalCapacity as number) ? formatNumber(event.totalCapacity) : '—'}
              </span>
            </div>
            {event.dataRegime === 'consolidated' ? (
              <div className="flex items-center gap-2 mt-1.5">
                <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300 border border-gray-200 dark:border-gray-600">
                  <Archive className="w-3 h-3" />
                  Dados consolidados — evento encerrado
                </span>
              </div>
            ) : event.dataRegime === 'hybrid' ? (
              <div className="flex items-center gap-2 mt-1.5 text-xs text-gray-400 dark:text-gray-500">
                {totalInscritos > 0 && (
                  <>
                    <CheckCircle className="w-3.5 h-3.5 text-green-500 dark:text-green-400" />
                    <span>{formatNumber(totalInscritos)} consolidados</span>
                  </>
                )}
                {hasTodayData && todaySales > 0 && (
                  <>
                    {totalInscritos > 0 && <span className="text-gray-300 dark:text-gray-600">·</span>}
                    <Clock className="w-3.5 h-3.5 text-amber-500 dark:text-amber-400" />
                    <span>+{formatNumber(todaySales)} de hoje (parcial)</span>
                  </>
                )}
              </div>
            ) : null}
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
          onClick={() => setActiveTab('complementares')}
          className={`px-5 py-2.5 text-sm font-medium rounded-t-lg transition-colors ${
            activeTab === 'complementares'
              ? 'bg-white dark:bg-gray-800 text-blue-600 dark:text-blue-400 border border-b-0 border-gray-200 dark:border-gray-700'
              : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300'
          }`}
        >
          Complementares
        </button>
        <button
          onClick={() => setActiveTab('controle')}
          className={`px-5 py-2.5 text-sm font-medium rounded-t-lg transition-colors flex items-center gap-1.5 ${
            activeTab === 'controle'
              ? 'bg-white dark:bg-gray-800 text-blue-600 dark:text-blue-400 border border-b-0 border-gray-200 dark:border-gray-700'
              : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300'
          }`}
        >
          <TableProperties className="w-4 h-4" />
          Controle Diário
        </button>
      </div>

      {activeTab === 'simulator' ? (
        <EventSimulator eventoId={id!} ano={anoParam ?? new Date().getFullYear()} isDark={isDark} />
      ) : activeTab === 'controle' ? (
        <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700">
          <div className={`flex border-b ${isDark ? 'border-gray-700' : 'border-gray-200'}`}>
            <button
              onClick={() => setControleSubTab('tabela')}
              className={`px-5 py-3 text-sm font-medium transition-colors ${
                controleSubTab === 'tabela'
                  ? isDark
                    ? 'text-blue-400 border-b-2 border-blue-400'
                    : 'text-blue-600 border-b-2 border-blue-600'
                  : isDark
                    ? 'text-gray-400 hover:text-gray-200'
                    : 'text-gray-500 hover:text-gray-700'
              }`}
            >
              Controle Diário
            </button>
            <button
              onClick={() => setControleSubTab('curva')}
              className={`px-5 py-3 text-sm font-medium transition-colors ${
                controleSubTab === 'curva'
                  ? isDark
                    ? 'text-blue-400 border-b-2 border-blue-400'
                    : 'text-blue-600 border-b-2 border-blue-600'
                  : isDark
                    ? 'text-gray-400 hover:text-gray-200'
                    : 'text-gray-500 hover:text-gray-700'
              }`}
            >
              Composição da Curva
            </button>
          </div>

          <div className="p-6">
            {controleSubTab === 'tabela' ? (
              <DailySalesTable
                dailySales={event.dailySales || []}
                isDark={isDark}
                eventName={event.name}
                salesGoal={event.salesGoal}
              />
            ) : (
              <div>
                {curvaSnapshotLoading ? (
                  <div className="flex items-center justify-center py-12">
                    <Loader2 className="w-6 h-6 animate-spin text-blue-500 mr-2" />
                    <span className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Carregando dados da curva...</span>
                  </div>
                ) : !curvaSnapshot || curvaSnapshot.data.length === 0 ? (
                  <div className={`text-center py-12 ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                    {curvaSnapshot?.message || 'Sem dados de curva histórica disponíveis para este evento.'}
                  </div>
                ) : (
                  <div className="space-y-4">
                    <div className={`grid grid-cols-2 sm:grid-cols-3 gap-3 mb-4`}>
                      <div className={`rounded-lg p-4 border ${isDark ? 'bg-blue-900/20 border-blue-800' : 'bg-blue-50 border-blue-200'}`}>
                        <span className={`text-xs font-medium ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Ano de Referência</span>
                        <p className={`text-xl font-bold mt-1 ${isDark ? 'text-blue-400' : 'text-blue-600'}`}>{curvaSnapshot.ano_referencia}</p>
                      </div>
                      <div className={`rounded-lg p-4 border ${isDark ? 'bg-purple-900/20 border-purple-800' : 'bg-purple-50 border-purple-200'}`}>
                        <span className={`text-xs font-medium ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Meta Atual (base)</span>
                        <p className={`text-xl font-bold mt-1 ${isDark ? 'text-purple-400' : 'text-purple-600'}`}>{curvaSnapshot.sales_goal.toLocaleString('pt-BR')}</p>
                      </div>
                      <div className={`rounded-lg p-4 border ${isDark ? 'bg-gray-700 border-gray-600' : 'bg-gray-50 border-gray-200'}`}>
                        <span className={`text-xs font-medium ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Pontos D-minus</span>
                        <p className={`text-xl font-bold mt-1 ${isDark ? 'text-gray-200' : 'text-gray-700'}`}>{curvaSnapshot.data.length}</p>
                      </div>
                    </div>

                    <p className={`text-xs ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>
                      A curva é baseada no histórico de {curvaSnapshot.ano_referencia}. As quantidades de meta são calculadas aplicando o % acumulado à meta atual de {curvaSnapshot.sales_goal.toLocaleString('pt-BR')} inscrições.
                    </p>

                    <div className={`rounded-lg overflow-hidden border ${isDark ? 'border-gray-600' : 'border-gray-300'}`}>
                      <div className="overflow-auto max-h-[550px]">
                        <table className="w-full text-sm border-collapse">
                          <thead>
                            <tr className={`sticky top-0 z-10 border-b-2 ${isDark ? 'bg-slate-700 border-blue-500/50' : 'bg-slate-100 border-slate-300'}`}>
                              {['D-', '% Acum.', '% Dia', 'Meta Acum.', 'Meta Dia'].map((col, i) => (
                                <th key={i} className={`px-3 py-3 text-xs font-bold uppercase tracking-wider whitespace-nowrap ${i === 0 ? 'text-left' : 'text-right'} ${isDark ? 'text-blue-300' : 'text-slate-700'}`}>
                                  {col}
                                </th>
                              ))}
                            </tr>
                          </thead>
                          <tbody>
                            {curvaSnapshot.data.map((row, i) => {
                              const evenRow = i % 2 === 0;
                              const rowBg = isDark
                                ? (evenRow ? 'bg-gray-800' : 'bg-[#2d3748]')
                                : (evenRow ? 'bg-white' : 'bg-slate-50');
                              return (
                                <tr key={row.d_minus} className={`${rowBg} hover:${isDark ? 'bg-slate-600' : 'bg-blue-50'} transition-colors border-b ${isDark ? 'border-gray-700' : 'border-gray-200'}`}>
                                  <td className={`px-3 py-2.5 text-left font-semibold text-sm ${isDark ? 'text-cyan-300' : 'text-cyan-700'}`}>
                                    D-{row.d_minus}
                                  </td>
                                  <td className={`px-3 py-2.5 text-right text-sm ${isDark ? 'text-gray-300' : 'text-gray-600'}`}>
                                    {row.percentual_acumulado.toFixed(2)}%
                                  </td>
                                  <td className={`px-3 py-2.5 text-right text-sm ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                                    {row.percentual_dia.toFixed(2)}%
                                  </td>
                                  <td className={`px-3 py-2.5 text-right text-sm font-semibold ${isDark ? 'text-blue-300' : 'text-blue-700'}`}>
                                    {row.meta_acumulado.toLocaleString('pt-BR')}
                                  </td>
                                  <td className={`px-3 py-2.5 text-right text-sm ${isDark ? 'text-gray-200' : 'text-gray-700'}`}>
                                    {row.meta_dia.toLocaleString('pt-BR')}
                                  </td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      ) : activeTab === 'complementares' ? (
        <div className="space-y-6">
          <div className="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm border border-gray-200 dark:border-gray-700">
              <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-4">
                <h3 className="font-semibold text-gray-900 dark:text-white">
                  Curva de Vendas Acumuladas vs Esperado
                </h3>
                <div className="flex items-center gap-3">
                  <button
                    onClick={() => setShowNormalized(!showNormalized)}
                    className={`flex items-center gap-1.5 px-3 py-1 text-xs font-medium rounded-md transition-colors ${
                      showNormalized
                        ? 'bg-orange-500 text-white'
                        : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600'
                    }`}
                    title="Mostra curva com outliers de campanhas suavizados"
                  >
                    <Activity className="w-3.5 h-3.5" />
                    Normalizada
                  </button>
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
                        const normalizado = showNormalized ? Math.round(Number(payload.find((p: any) => p.dataKey === 'cumulativeNormalized')?.value ?? 0)) : null;
                        const diff = real - esperado;
                        const diffColor = diff >= 0 ? '#22C55E' : '#EF4444';
                        return (
                          <div style={{ backgroundColor: '#1F2937', border: 'none', borderRadius: '8px', padding: '12px', color: '#fff' }}>
                            <p style={{ marginBottom: '8px', color: '#9CA3AF' }}>{new Date(label + 'T12:00:00').toLocaleDateString('pt-BR')}</p>
                            <p style={{ color: '#3B82F6' }}>Vendas Reais: {formatNumber(real)}</p>
                            {normalizado !== null && (
                              <p style={{ color: '#F97316' }}>Normalizada: {formatNumber(normalizado)}</p>
                            )}
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
                    {showNormalized && (
                      <Line 
                        type="monotone" 
                        dataKey="cumulativeNormalized" 
                        name="Normalizada"
                        stroke="#F97316" 
                        strokeWidth={2}
                        strokeDasharray="8 4"
                        dot={false}
                      />
                    )}
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

          {event.dailySales && event.dailySales.length > 0 && (
            <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-6">
              <button
                onClick={() => setShowNormalizationDetail(!showNormalizationDetail)}
                className="flex items-center gap-2 text-sm font-medium text-gray-700 dark:text-gray-300 hover:text-blue-600 dark:hover:text-blue-400 transition-colors"
              >
                <ChevronDown className={`w-4 h-4 transition-transform duration-200 ${showNormalizationDetail ? 'rotate-180' : '-rotate-90'}`} />
                Ver detalhamento da normalização
              </button>
              {showNormalizationDetail && (
                <div className="mt-4">
                  <p className="text-xs text-gray-500 dark:text-gray-400 mb-3">
                    Parâmetros: janela = 7 dias · threshold = 2.0× · spread = 3 dias
                  </p>
                  <div className="overflow-x-auto">
                    <table className="min-w-full text-xs">
                      <thead>
                        <tr className="border-b border-gray-200 dark:border-gray-700">
                          <th className="text-left py-2 px-2 font-semibold text-gray-600 dark:text-gray-400">Data</th>
                          <th className="text-right py-2 px-2 font-semibold text-gray-600 dark:text-gray-400">Vendas Reais</th>
                          <th className="text-right py-2 px-2 font-semibold text-gray-600 dark:text-gray-400">Mediana Local</th>
                          <th className="text-right py-2 px-2 font-semibold text-gray-600 dark:text-gray-400">Limite</th>
                          <th className="text-center py-2 px-2 font-semibold text-gray-600 dark:text-gray-400">Outlier?</th>
                          <th className="text-right py-2 px-2 font-semibold text-gray-600 dark:text-gray-400">Excesso Removido</th>
                          <th className="text-right py-2 px-2 font-semibold text-gray-600 dark:text-gray-400">Excesso Recebido</th>
                          <th className="text-right py-2 px-2 font-semibold text-gray-600 dark:text-gray-400">Vendas Normalizadas</th>
                          <th className="text-right py-2 px-2 font-semibold text-gray-600 dark:text-gray-400">Δ</th>
                        </tr>
                      </thead>
                      <tbody>
                        {event.dailySales.map((day, idx) => {
                          const delta = (day.normalizedSales ?? day.sales) - day.sales;
                          const deltaColor = delta > 0 ? 'text-green-600 dark:text-green-400' : delta < 0 ? 'text-red-600 dark:text-red-400' : 'text-gray-500 dark:text-gray-400';
                          return (
                            <tr
                              key={idx}
                              className={`border-b border-gray-100 dark:border-gray-700/50 ${day.isOutlier ? 'bg-red-50 dark:bg-red-900/20' : ''}`}
                            >
                              <td className="py-1.5 px-2 text-gray-800 dark:text-gray-200">
                                {new Date(day.date + 'T12:00:00').toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit', year: '2-digit' })}
                              </td>
                              <td className="py-1.5 px-2 text-right text-gray-800 dark:text-gray-200">{day.sales}</td>
                              <td className="py-1.5 px-2 text-right text-gray-600 dark:text-gray-400">{day.localMedian ?? '—'}</td>
                              <td className="py-1.5 px-2 text-right text-gray-600 dark:text-gray-400">{day.outlierLimit ?? '—'}</td>
                              <td className="py-1.5 px-2 text-center">
                                {day.isOutlier ? (
                                  <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-semibold bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-400">
                                    OUTLIER
                                  </span>
                                ) : (
                                  <span className="text-gray-400 dark:text-gray-500">—</span>
                                )}
                              </td>
                              <td className="py-1.5 px-2 text-right text-red-600 dark:text-red-400">{(day.excessRemoved ?? 0) > 0 ? `-${day.excessRemoved}` : '—'}</td>
                              <td className="py-1.5 px-2 text-right text-green-600 dark:text-green-400">{(day.excessReceived ?? 0) > 0 ? `+${day.excessReceived}` : '—'}</td>
                              <td className="py-1.5 px-2 text-right font-medium text-gray-800 dark:text-gray-200">{day.normalizedSales ?? day.sales}</td>
                              <td className={`py-1.5 px-2 text-right font-medium ${deltaColor}`}>
                                {delta !== 0 ? (delta > 0 ? '+' : '') + delta.toFixed(1) : '—'}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          )}

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
                    const diasAteEvento = Math.max(0, (m.dias_ate_evento ?? 0) - 2);
                    const metaRef = isVendas ? (m.meta_orcada > 0 ? m.meta_orcada : m.total_vendas_anterior) : m.total_receita_anterior;
                    const totalAtual = isVendas ? m.total_vendas_atual : m.total_receita_atual;
                    const faltam = Math.max(0, metaRef - totalAtual);
                    const fmt = (v: number) => isVendas ? formatNumber(Math.round(v)) : formatCurrency(v);
                    const labelCurva = isVendas ? 'inscrições' : 'receita';

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
                            <InfoTooltip text={`Quantas ${labelCurva} o evento de ${curvaAnoAnterior} tinha acumulado faltando o mesmo número de dias (D-${diasAteEvento}) para o evento. Permite comparar o ritmo de vendas no mesmo momento da jornada.`} />
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
                            <InfoTooltip text={`Variação percentual das ${labelCurva} de ${curvaAnoAtual} comparado com ${curvaAnoAnterior} no mesmo D-${diasAteEvento} (mesma distância do evento). Positivo = melhor que o ano anterior neste momento.`} />
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
                            <InfoTooltip text={`Quantidade de ${labelCurva} por dia necessária nos próximos ${diasAteEvento} dias restantes para atingir a meta${isVendas && m.meta_orcada > 0 ? ` orçada de ${formatNumber(m.meta_orcada)}` : ''}. Calculado como: (meta - acumulado atual) / dias restantes.`} />
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
        </div>
      ) : (
      <>
      <div className={`rounded-xl px-4 py-2 shadow-sm border flex flex-wrap items-center gap-3 ${getRecommendationStyle()}`}>
        <div className="flex items-center gap-3">
          <Clock className="w-4 h-4 text-gray-400" />
          <span className="text-sm text-gray-500 dark:text-gray-400">D- Inscrições</span>
          <span className={`text-xl font-bold ${
            dMinusCalc < 40 
              ? 'text-orange-600 dark:text-orange-400' 
              : 'text-blue-600 dark:text-blue-400'
          }`}>
            D-{dMinusCalc}
          </span>
          <span className="text-gray-300 dark:text-gray-600">|</span>
          <span className="text-sm text-gray-500 dark:text-gray-400">Evento</span>
          <span className={`text-sm font-medium ${
            _safeDMinus < 40 
              ? 'text-orange-500 dark:text-orange-400' 
              : 'text-gray-500 dark:text-gray-400'
          }`}>
            D-{_safeDMinus}
          </span>
          {dMinusCalc < 40 && (
            <span className="text-xs text-orange-600 dark:text-orange-400 flex items-center gap-1">
              <AlertTriangle className="w-3 h-3" />
              Fora da janela de promoção
            </span>
          )}
          {isInCriticalWindow(dMinusCalc) && (
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
          <span className={`text-xs font-bold px-2 py-0.5 rounded-full shrink-0 ${
            event.iscStatus === 'accelerating' ? 'bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300' :
            event.iscStatus === 'stable' ? 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/40 dark:text-yellow-300' :
            'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300'
          }`}>
            Playbook {event.suggestedAction?.letter}
          </span>
          <p className="text-sm text-gray-700 dark:text-gray-300 truncate">
            {event.suggestedAction?.name}
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm border border-gray-200 dark:border-gray-700">
          <div className="flex items-center justify-between mb-4">
            <p className="text-sm text-gray-500 dark:text-gray-400">ISC Atual (ref. ontem)</p>
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
              {getISCEmoji(event.iscStatus)} {(event.isc ?? 0).toFixed(2)}
            </p>
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
              {event.iscStatus === 'accelerating' ? 'Acelerando' : 
               event.iscStatus === 'stable' ? 'Estável' : 'Desacelerando'}
            </p>
          </div>
        </div>

        <div className="lg:col-span-2 bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm border border-gray-200 dark:border-gray-700">
          <h3 className="font-semibold text-gray-900 dark:text-white mb-3 text-sm">Componentes do ISC (ref. ontem)</h3>
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
                {(event.iscComponents?.ia730 ?? 0).toFixed(2)}
              </p>
              <div className="flex items-center gap-1 mt-1 text-xs">
                {(event.iscComponents?.ia730 ?? 0) > 1 ? (
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
                {(event.iscComponents?.curvaDPercent ?? 0).toFixed(2)}
              </p>
              <div className="flex items-center gap-1 mt-1 text-xs">
                {(event.iscComponents?.curvaDPercent ?? 0) > 1 ? (
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
                {(event.iscComponents?.rolling14d ?? 0).toFixed(2)}
              </p>
              <div className="flex items-center gap-1 mt-1 text-xs">
                {(event.iscComponents?.rolling14d ?? 0) > 1 ? (
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

      {event.suggestedAction && (
        <div className={`rounded-xl p-5 border-2 ${
          event.iscStatus === 'accelerating'
            ? 'bg-green-50 dark:bg-green-950/20 border-green-200 dark:border-green-800'
            : event.iscStatus === 'stable'
              ? 'bg-amber-50 dark:bg-amber-950/20 border-amber-200 dark:border-amber-800'
              : 'bg-red-50 dark:bg-red-950/20 border-red-200 dark:border-red-800'
        }`}>
          <div className="flex items-start gap-4 mb-4">
            <div className={`shrink-0 w-12 h-12 rounded-xl flex items-center justify-center text-xl font-black ${
              event.iscStatus === 'accelerating'
                ? 'bg-green-100 dark:bg-green-900/50 text-green-800 dark:text-green-200'
                : event.iscStatus === 'stable'
                  ? 'bg-amber-100 dark:bg-amber-900/50 text-amber-800 dark:text-amber-200'
                  : 'bg-red-100 dark:bg-red-900/50 text-red-800 dark:text-red-200'
            }`}>
              {event.suggestedAction.letter}
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex flex-wrap items-center gap-2 mb-1">
                <span className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider">Playbook Ativo</span>
                <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                  event.iscStatus === 'accelerating'
                    ? 'bg-green-100 dark:bg-green-900/40 text-green-800 dark:text-green-200'
                    : event.iscStatus === 'stable'
                      ? 'bg-amber-100 dark:bg-amber-900/40 text-amber-800 dark:text-amber-200'
                      : 'bg-red-100 dark:bg-red-900/40 text-red-800 dark:text-red-200'
                }`}>{event.suggestedAction.stageName}</span>
                <span className="text-xs text-gray-400 dark:text-gray-500">{event.suggestedAction.iscLabel}</span>
              </div>
              <p className={`font-bold text-base ${
                event.iscStatus === 'accelerating'
                  ? 'text-green-800 dark:text-green-200'
                  : event.iscStatus === 'stable'
                    ? 'text-amber-800 dark:text-amber-200'
                    : 'text-red-800 dark:text-red-200'
              }`}>{event.suggestedAction.name}</p>
              <p className="text-xs text-gray-600 dark:text-gray-400 mt-0.5 italic">{event.suggestedAction.narrative}</p>
            </div>
            <Link to="/marketing/playbook" className="shrink-0 text-xs font-medium text-indigo-600 dark:text-indigo-400 hover:underline whitespace-nowrap">
              Ver Playbook Completo →
            </Link>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div className="sm:col-span-2">
              <p className="text-xs font-bold uppercase tracking-wider text-gray-500 dark:text-gray-400 mb-2">Ações Operacionais</p>
              <ul className="space-y-1.5">
                {(event.suggestedAction.actions ?? []).map((action, i) => (
                  <li key={i} className="flex items-start gap-2 text-sm text-gray-700 dark:text-gray-300">
                    <span className={`mt-1.5 w-1.5 h-1.5 rounded-full shrink-0 ${
                      event.iscStatus === 'accelerating' ? 'bg-green-500' : event.iscStatus === 'stable' ? 'bg-amber-400' : 'bg-red-500'
                    }`} />
                    {action}
                  </li>
                ))}
              </ul>
            </div>
            <div className="space-y-3">
              <div>
                <p className="text-xs font-bold uppercase tracking-wider text-gray-500 dark:text-gray-400 mb-2">KPIs (48–72h)</p>
                {(event.suggestedAction.kpis ?? []).map((kpi, i) => (
                  <div key={i} className="text-sm text-gray-700 dark:text-gray-300 bg-white/60 dark:bg-black/20 rounded-lg px-3 py-1.5 font-medium">
                    {kpi}
                  </div>
                ))}
              </div>
              <div>
                <p className="text-xs font-bold uppercase tracking-wider text-gray-500 dark:text-gray-400 mb-2">Pontos de Corte</p>
                <div className="flex gap-2 flex-wrap">
                  {(event.suggestedAction.cutoffs ?? []).map((c, i) => (
                    <span key={i} className={`text-sm font-bold px-3 py-1 rounded-lg ${
                      event.iscStatus === 'accelerating'
                        ? 'bg-green-100 dark:bg-green-900/40 text-green-800 dark:text-green-200'
                        : event.iscStatus === 'stable'
                          ? 'bg-amber-100 dark:bg-amber-900/40 text-amber-800 dark:text-amber-200'
                          : 'bg-red-100 dark:bg-red-900/40 text-red-800 dark:text-red-200'
                    }`}>{c}</span>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      <div>
        {isConsolidated && cumulativeData.length > 0 ? (
          <div className="bg-white dark:bg-gray-800 rounded-xl p-5 shadow-sm border border-gray-200 dark:border-gray-700">
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
                <p className="text-xs text-gray-500 dark:text-gray-400 mb-3">Meta Acumulada vs Inscritos Total (até ontem)</p>
                <div className="flex items-center justify-between mb-2">
                  <div>
                    <p className="text-xs text-gray-400 dark:text-gray-500 mb-0.5">Inscritos</p>
                    <p className="text-lg font-bold text-blue-600 dark:text-blue-400">{formatNumber(totalInscritosConsolidado)}</p>
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
          <div className="bg-white dark:bg-gray-800 rounded-xl p-5 shadow-sm border border-gray-200 dark:border-gray-700">
            <p className="text-sm text-gray-500 dark:text-gray-400">Vendas / Meta</p>
            <p className="text-lg font-bold text-gray-900 dark:text-white mt-2">
              {formatNumber(event.currentSales)} / {formatNumber(event.salesGoal)}
            </p>
            <div className="mt-3 w-full bg-gray-200 dark:bg-gray-600 rounded-full h-2">
              <div 
                className="bg-blue-600 h-2 rounded-full transition-all"
                style={{ width: `${event.salesGoal > 0 ? Math.min((event.currentSales / event.salesGoal) * 100, 100) : 0}%` }}
              />
            </div>
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-2">
              {event.salesGoal > 0 ? Math.round((event.currentSales / event.salesGoal) * 100) : 0}% da meta
            </p>
          </div>
        )}
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
              <XAxis dataKey="label" stroke="#6B7280" fontSize={11} />
              <YAxis stroke="#6B7280" fontSize={11} tickFormatter={(v) => `${v}%`} />
              <Tooltip 
                content={({ active, payload }: any) => {
                  if (!active || !payload || !payload.length) return null;
                  const d = payload[0]?.payload;
                  if (!d) return null;
                  const isAcum = attainmentMode === 'acumulado';
                  const real = isAcum ? d.cumulative : d.sales;
                  const esperado = isAcum ? d.cumulativeExpected : d.expected;
                  const diff = real - esperado;
                  return (
                    <div style={{ backgroundColor: '#1F2937', border: 'none', borderRadius: '8px', padding: '12px', color: '#fff' }}>
                      <p style={{ marginBottom: '8px', color: '#9CA3AF' }}>{d.label} — {new Date(d.date + 'T12:00:00').toLocaleDateString('pt-BR')}</p>
                      <p style={{ color: '#3B82F6' }}>{isAcum ? 'Acumulado Real' : 'Vendas Dia'}: {formatNumber(real)}</p>
                      <p style={{ color: '#9CA3AF' }}>Esperado: {formatNumber(esperado)}</p>
                      <p style={{ color: diff >= 0 ? '#22C55E' : '#EF4444', marginTop: '6px', borderTop: '1px solid #374151', paddingTop: '6px', fontWeight: 600 }}>
                        Variação: {d.percentual >= 0 ? '+' : ''}{d.percentual}% ({diff >= 0 ? '+' : ''}{formatNumber(diff)})
                      </p>
                    </div>
                  );
                }}
              />
              <ReferenceLine y={0} stroke="#6B7280" strokeDasharray="3 3" />
              <Bar dataKey="percentual" name="Atingimento vs Esperado" radius={[4, 4, 0, 0]}>
                {filteredAttainmentData.map((entry: any, index: number) => (
                  <Cell key={`cell-${index}`} fill={entry.percentual >= 0 ? '#22C55E' : '#EF4444'} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm border border-gray-200 dark:border-gray-700">
        <h3 className="font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
          <Activity className="w-5 h-5 text-blue-500" />
          Curva no Tempo
        </h3>
        <div className="mb-4">
          <p className="text-sm text-gray-500 dark:text-gray-400">Vendas Totais / Meta Global</p>
          <p className="text-2xl font-bold text-gray-900 dark:text-white">
            {formatNumber(event.currentSales ?? inscritosTotal)} / {formatNumber(event.salesGoal)}
          </p>
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
            <div className="p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
              <p className="text-xs text-gray-500 dark:text-gray-400">D- (Inscrições)</p>
              <p className={`text-xl font-bold ${dMinusCalc < 40 ? 'text-orange-600 dark:text-orange-400' : 'text-blue-600 dark:text-blue-400'}`}>
                {dMinusCalc}
              </p>
              <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">Evento: <span className="font-semibold text-gray-600 dark:text-gray-300">{_safeDMinus}</span></p>
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
          <span className="text-xs font-normal text-gray-400 dark:text-gray-500">(dados até ontem)</span>
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

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="bg-white dark:bg-gray-800 rounded-xl p-5 shadow-sm border border-gray-200 dark:border-gray-700">
          <h3 className="text-sm font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
            <DollarSign className="w-4 h-4 text-green-500" />
            Análise de Ticket Médio
          </h3>
          {(() => {
            const ticketRef = event.ticketAtual && event.ticketAtual > 0 ? event.ticketAtual : event.averageTicket;
            return (
          <div className="space-y-3">
            <div className="flex items-center justify-between p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
              <span className="text-xs text-gray-500 dark:text-gray-400">Ticket Atual (Kit)</span>
              <span className="text-lg font-bold text-gray-900 dark:text-white">{ticketRef > 0 ? formatCurrency(ticketRef) : '—'}</span>
            </div>
            {ticketMedioRealizado > 0 && (
              <div className="flex items-center justify-between p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
                <span className="text-xs text-gray-500 dark:text-gray-400">Ticket Médio Realizado</span>
                <span className="text-base font-medium text-gray-600 dark:text-gray-300">{formatCurrency(ticketMedioRealizado)}</span>
              </div>
            )}
            <div className="flex items-center justify-between p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
              <span className="text-xs text-gray-500 dark:text-gray-400">Ticket Orçado</span>
              <span className="text-lg font-bold text-gray-600 dark:text-gray-300">{formatCurrency(event.budgetTicket || 0)}</span>
            </div>
            {event.budgetTicket > 0 && ticketRef > 0 && (
              <div className="flex items-center justify-between p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
                <span className="text-xs text-gray-500 dark:text-gray-400">% do Orçado</span>
                <span className={`text-lg font-bold ${(ticketRef / event.budgetTicket) >= 1 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}>
                  {((ticketRef / event.budgetTicket) - 1) >= 0 ? '+' : ''}{Math.round(((ticketRef / event.budgetTicket) - 1) * 100)}%
                </span>
              </div>
            )}
            <div className="flex items-center justify-between p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
              <span className="text-xs text-gray-500 dark:text-gray-400">Inscrições p/ Meta</span>
              <span className={`text-lg font-bold ${volumeParaMeta <= 0 ? 'text-green-600 dark:text-green-400' : 'text-gray-900 dark:text-white'}`}>
                {formatNumber(Math.max(volumeParaMeta, 0))}
              </span>
            </div>
            {event.budgetTicket > 0 && volumeParaMeta > 0 && (
              <div className="flex items-center justify-between p-3 bg-blue-50 dark:bg-blue-900/20 rounded-lg border border-blue-200 dark:border-blue-800">
                <span className="text-xs text-gray-500 dark:text-gray-400">Ticket Necessário p/ Convergência</span>
                <span className="text-lg font-bold text-blue-600 dark:text-blue-400">
                  {formatCurrency(
                    (() => {
                      const kc = event.kitCostPerUnit || 0;
                      const metaM = (event.budgetTicket - kc) * event.salesGoal;
                      const margAcum = margemRealizadaKits != null ? margemRealizadaKits : (event.margemRealizadaTotal || 0);
                      const vr = Math.max(volumeParaMeta, 1);
                      return Math.max(0, ((metaM - margAcum) / vr) + kc);
                    })()
                  )}
                </span>
              </div>
            )}
          </div>
            );
          })()}
        </div>

        <div className="bg-white dark:bg-gray-800 rounded-xl p-5 shadow-sm border border-gray-200 dark:border-gray-700">
          <h3 className="text-sm font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
            <Target className="w-4 h-4 text-amber-500" />
            Análise de Margem
            <button
              onClick={() => setShowMargemInfo(true)}
              className="ml-auto p-1 rounded-full hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
              title="Ver composição da margem"
            >
              <Info className="w-4 h-4 text-gray-400 hover:text-blue-500 dark:hover:text-blue-400" />
            </button>
          </h3>
          {(() => {
            const kitCost = event.kitCostPerUnit || 0;
            const ticketRef = event.ticketAtual && event.ticketAtual > 0 ? event.ticketAtual : (event.averageTicket || 0);
            const margemOrcadaTotal = event.budgetTicket > 0 && kitCost > 0 ? (event.budgetTicket - kitCost) * event.salesGoal : 0;
            const margemRealizadaTotal = margemRealizadaKits != null
              ? margemRealizadaKits
              : (ticketRef > 0 && event.currentSales > 0 ? Math.round((ticketRef - kitCost) * event.currentSales * 100) / 100 : 0);
            const faltaParaMeta = margemOrcadaTotal - margemRealizadaTotal;
            return (
              <div className="space-y-3">
                <div className="flex items-center justify-between p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
                  <span className="text-xs text-gray-500 dark:text-gray-400">Margem Realizada</span>
                  <span className={`text-lg font-bold ${margemRealizadaTotal >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}>
                    {formatCurrency(margemRealizadaTotal)}
                  </span>
                </div>
                <div className="flex items-center justify-between p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
                  <span className="text-xs text-gray-500 dark:text-gray-400">Margem Orçada</span>
                  <span className="text-lg font-bold text-gray-600 dark:text-gray-300">{formatCurrency(margemOrcadaTotal)}</span>
                </div>
                <div className="flex items-center justify-between p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
                  <span className="text-xs text-gray-500 dark:text-gray-400">Falta p/ Meta</span>
                  <span className={`text-lg font-bold ${faltaParaMeta <= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}>
                    {formatCurrency(Math.max(faltaParaMeta, 0))}
                  </span>
                </div>
                <div className="flex items-center justify-between p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
                  <span className="text-xs text-gray-500 dark:text-gray-400">Volume p/ Meta</span>
                  <span className={`text-lg font-bold ${volumeParaMeta <= 0 ? 'text-green-600 dark:text-green-400' : 'text-gray-900 dark:text-white'}`}>
                    {formatNumber(Math.max(volumeParaMeta, 0))}
                  </span>
                </div>
                <div className="p-3 bg-amber-50 dark:bg-amber-900/20 rounded-lg border border-amber-200 dark:border-amber-800">
                  <div className="flex items-center justify-between">
                    {event.margemPorKit && event.margemPorKit.filter(r => r.tipoKit !== 'CONSOLIDADO').length > 0 ? (
                      <div className="group relative">
                        <span className="text-xs text-gray-500 dark:text-gray-400 flex items-center gap-1 cursor-help">
                          Custo Kit Básico
                          <Info className="w-3 h-3 text-gray-400" />
                        </span>
                        <div className="hidden group-hover:block absolute z-50 left-0 top-5 w-56 bg-gray-900 text-white rounded-xl shadow-xl p-3 text-xs">
                          <p className="font-semibold mb-2 text-gray-200">Custo por tipo de kit</p>
                          <div className="space-y-1.5">
                            {event.margemPorKit
                              .filter(r => r.tipoKit !== 'CONSOLIDADO')
                              .map((r, i) => (
                                <div key={i} className="flex items-center justify-between gap-3">
                                  <span className="text-gray-300 truncate">{r.tipoKit}</span>
                                  <span className="font-medium text-amber-300 shrink-0">
                                    {r.custoKit != null ? formatCurrency(r.custoKit) : '—'}
                                  </span>
                                </div>
                              ))}
                          </div>
                          <div className="absolute -top-1.5 left-4 w-3 h-3 bg-gray-900 rotate-45" />
                        </div>
                      </div>
                    ) : (
                      <span className="text-xs text-gray-500 dark:text-gray-400">Custo Kit Básico</span>
                    )}
                    <span className="text-sm font-semibold text-amber-600 dark:text-amber-400">{formatCurrency(kitCost)}</span>
                  </div>
                </div>
                {_kitTotalReceita > 0 && (
                  <div className="flex items-center justify-between p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
                    <span className="text-xs text-gray-500 dark:text-gray-400">Receita Líquida Total</span>
                    <span className="text-base font-semibold text-gray-900 dark:text-white">{formatCurrency(_kitTotalReceita)}</span>
                  </div>
                )}
              </div>
            );
          })()}
        </div>

        {showMargemInfo && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4" onClick={() => setShowMargemInfo(false)}>
            <div className="absolute inset-0 bg-black/50" />
            <div
              className="relative bg-white dark:bg-gray-800 rounded-2xl shadow-xl border border-gray-200 dark:border-gray-700 w-full max-w-lg md:max-w-3xl max-h-[90vh] overflow-y-auto"
              onClick={e => e.stopPropagation()}
            >
              <div className="flex items-center justify-between p-5 border-b border-gray-200 dark:border-gray-700">
                <h2 className="text-lg font-bold text-gray-900 dark:text-white flex items-center gap-2">
                  <Info className="w-5 h-5 text-blue-500" />
                  Composição da Margem
                </h2>
                <button
                  onClick={() => setShowMargemInfo(false)}
                  className="p-1 rounded-full hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
                >
                  <X className="w-5 h-5 text-gray-500" />
                </button>
              </div>

              <div className="p-5">
                <div className="grid grid-cols-1 gap-6">
                  <div>
                    <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3 flex items-center gap-2">
                      <div className="w-2 h-2 rounded-full bg-gray-500" />
                      Margem Orçada
                    </h3>
                    {event.budgetTicket > 0 && (event.kitCostPerUnit || 0) > 0 ? (
                      <div className="space-y-2 text-sm">
                        <div className="flex justify-between p-2.5 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
                          <span className="text-gray-500 dark:text-gray-400">Ticket Orçado</span>
                          <span className="font-medium text-gray-900 dark:text-white">{formatCurrency(event.budgetTicket)}</span>
                        </div>
                        <div className="flex justify-between p-2.5 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
                          <span className="text-gray-500 dark:text-gray-400">(-) Custo Kit</span>
                          <span className="font-medium text-red-600 dark:text-red-400">- {formatCurrency(event.kitCostPerUnit || 0)}</span>
                        </div>
                        <div className="flex justify-between p-2.5 bg-blue-50 dark:bg-blue-900/20 rounded-lg border border-blue-200 dark:border-blue-800">
                          <span className="text-blue-700 dark:text-blue-300 font-medium">= Margem / Unidade</span>
                          <span className="font-bold text-blue-700 dark:text-blue-300">{formatCurrency(event.margemOrcadaUnit || 0)}</span>
                        </div>
                        <div className="flex justify-between p-2.5 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
                          <span className="text-gray-500 dark:text-gray-400">(×) Meta de Inscrições</span>
                          <span className="font-medium text-gray-900 dark:text-white">{formatNumber(event.salesGoal)}</span>
                        </div>
                        <button
                          onClick={() => setShowReceitaOrcada(!showReceitaOrcada)}
                          className="my-3 w-full flex items-center gap-2 group cursor-pointer"
                        >
                          <div className="flex-1 border-t border-dashed border-gray-300 dark:border-gray-600" />
                          <span className="flex items-center gap-1 text-[11px] text-gray-400 dark:text-gray-500 group-hover:text-blue-500 dark:group-hover:text-blue-400 transition-colors whitespace-nowrap">
                            <DollarSign className="w-3 h-3" />
                            Receita
                            <ChevronDown className={`w-3 h-3 transition-transform duration-200 ${showReceitaOrcada ? 'rotate-180' : ''}`} />
                          </span>
                          <div className="flex-1 border-t border-dashed border-gray-300 dark:border-gray-600" />
                        </button>
                        <div className={`space-y-2 overflow-hidden transition-all duration-300 ease-in-out ${showReceitaOrcada ? 'max-h-40 opacity-100' : 'max-h-0 opacity-0'}`}>
                          <div className="flex justify-between p-2.5 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
                            <span className="text-gray-500 dark:text-gray-400">Receita Orçada Total</span>
                            <span className="font-medium text-gray-900 dark:text-white">{formatCurrency(event.receitaOrcadaTotal || 0)}</span>
                          </div>
                          <div className="flex justify-between p-2.5 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
                            <span className="text-gray-500 dark:text-gray-400">(-) Custo Total Kits</span>
                            <span className="font-medium text-red-600 dark:text-red-400">- {formatCurrency((event.kitCostPerUnit || 0) * event.salesGoal)}</span>
                          </div>
                        </div>
                        <div className="flex justify-between p-2.5 bg-gray-100 dark:bg-gray-700 rounded-lg border border-gray-300 dark:border-gray-600">
                          <span className="text-gray-800 dark:text-gray-200 font-semibold">= Margem Orçada Total</span>
                          <div className="text-right">
                            <span className="font-bold text-gray-900 dark:text-white">{formatCurrency(event.margemOrcadaTotal || 0)}</span>
                          </div>
                        </div>
                      </div>
                    ) : (
                      <p className="text-sm text-gray-400 dark:text-gray-500 italic p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
                        Dados insuficientes.
                      </p>
                    )}
                  </div>

                </div>
              </div>

              {event.kitQueryFailed && (
                <div className="px-5 pb-4">
                  <div className="flex items-start gap-2 rounded-lg bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-700/50 px-4 py-3">
                    <span className="text-amber-500 mt-0.5 flex-shrink-0">⚠</span>
                    <p className="text-xs text-amber-700 dark:text-amber-300">
                      Dados de vendas detalhados por kit temporariamente indisponíveis — erro ao consultar o Magento. Serão atualizados na próxima recarga.
                    </p>
                  </div>
                </div>
              )}

              {event.margemPorKit && event.margemPorKit.length > 0 && (
                <div className="px-5 pb-5">
                  <div className="border-t border-gray-200 dark:border-gray-700 pt-5">
                    <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-1 flex items-center gap-2">
                      <div className="w-2 h-2 rounded-full bg-purple-500" />
                      Margem por Tipo de Kit
                    </h3>
                    <p className="text-xs text-gray-400 dark:text-gray-500 mb-3 italic">
                      Baseado em vendas Magento (bundle) + Ativo (por categoria), somadas por tipo de kit. Requer configuração de "Tipo Kit" e "Cat. Ativo" no painel de kits.
                    </p>
                    <div className="overflow-x-auto">
                      <table className="w-full text-xs">
                        <thead>
                          <tr className="border-b border-gray-200 dark:border-gray-700">
                            <th className="text-left py-2 px-2 font-semibold text-gray-500 dark:text-gray-400">Tipo de Kit</th>
                            <th className="text-right py-2 px-2 font-semibold text-gray-500 dark:text-gray-400">Qtd Vendida</th>
                            <th className="text-right py-2 px-2 font-semibold text-gray-500 dark:text-gray-400">Receita Líquida</th>
                            <th className="text-right py-2 px-2 font-semibold text-gray-500 dark:text-gray-400">Ticket Médio</th>
                            <th className="text-right py-2 px-2 font-semibold text-gray-500 dark:text-gray-400">Custo Kit</th>
                            <th className="text-right py-2 px-2 font-semibold text-gray-500 dark:text-gray-400">Margem/Un</th>
                            <th className="text-right py-2 px-2 font-semibold text-gray-500 dark:text-gray-400">Margem Total</th>
                          </tr>
                        </thead>
                        <tbody>
                          {(() => {
                            // Compute all CONSOLIDADO totals from the actual kit rows (exclude CONSOLIDADO itself)
                            const _kitRows = event.margemPorKit.filter(r => r.tipoKit !== 'CONSOLIDADO');
                            const _totalQtd = _kitRows.reduce((acc, r) => acc + r.qtd, 0);
                            const _totalReceita = _kitRows.reduce((acc, r) => acc + r.receitaLiquida, 0);
                            const _totalMargem = _kitRows.reduce((acc, r) => acc + r.margemTotal, 0);
                            const _totalTicketMedio = _totalQtd > 0 ? _totalReceita / _totalQtd : 0;
                            return event.margemPorKit.map((row, idx) => {
                              const isConsolidado = row.tipoKit === 'CONSOLIDADO';
                              // For CONSOLIDADO, all values come from the sum of kit rows above
                              const displayQtd = isConsolidado ? _totalQtd : row.qtd;
                              const displayReceita = isConsolidado ? _totalReceita : row.receitaLiquida;
                              const displayTicketMedio = isConsolidado ? _totalTicketMedio : row.ticketMedio;
                              const displayMargem = isConsolidado ? _totalMargem : row.margemTotal;
                              const margemPositiva = displayMargem >= 0;
                              return (
                                <tr
                                  key={idx}
                                  className={`border-b border-gray-100 dark:border-gray-700/50 ${
                                    isConsolidado
                                      ? 'bg-purple-50 dark:bg-purple-900/20 font-semibold'
                                      : 'hover:bg-gray-50 dark:hover:bg-gray-700/30'
                                  }`}
                                >
                                  <td className={`py-2 px-2 ${isConsolidado ? 'text-purple-700 dark:text-purple-300' : 'text-gray-700 dark:text-gray-300'}`}>
                                    {isConsolidado ? 'TOTAL CONSOLIDADO' : row.tipoKit}
                                  </td>
                                  <td className="text-right py-2 px-2 text-gray-700 dark:text-gray-300">
                                    {displayQtd.toLocaleString('pt-BR')}
                                  </td>
                                  <td className="text-right py-2 px-2 text-gray-700 dark:text-gray-300">
                                    {displayReceita.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })}
                                  </td>
                                  <td className="text-right py-2 px-2 text-gray-700 dark:text-gray-300">
                                    {displayTicketMedio > 0
                                      ? displayTicketMedio.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })
                                      : '—'}
                                  </td>
                                  <td className="text-right py-2 px-2 text-red-600 dark:text-red-400">
                                    {row.custoKit != null
                                      ? row.custoKit.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })
                                      : '—'}
                                  </td>
                                  <td className={`text-right py-2 px-2 ${row.margemUnit != null ? (row.margemUnit >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400') : 'text-gray-400'}`}>
                                    {row.margemUnit != null
                                      ? row.margemUnit.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })
                                      : '—'}
                                  </td>
                                  <td className={`text-right py-2 px-2 font-medium ${margemPositiva ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}>
                                    {displayMargem.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })}
                                  </td>
                                </tr>
                              );
                            });
                          })()}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </div>
              )}

            </div>
          </div>
        )}
      </div>

      <div className="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm border border-gray-200 dark:border-gray-700">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-6 flex items-center gap-2">
          Simulação por Ticket (volume fixo)
          <span className="group relative inline-flex items-center">
            <Info className="w-4 h-4 text-gray-400 cursor-help" />
            <span className="absolute left-1/2 -translate-x-1/2 bottom-full mb-2 w-72 rounded-lg bg-gray-800 text-white text-xs px-3 py-2 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-50 shadow-lg">
              Simula o impacto de mudanças no ticket médio mantendo o volume necessário para atingir a meta.
            </span>
          </span>
        </h3>
        {(() => {
          const kitCost = event.kitCostPerUnit || 0;
          const ticketKitConfig = event.ticketAtual || 0;
          const ticketMedio = ticketMedioRealizado || 0;
          const volRestante = Math.max(volumeParaMeta, 0);
          const margemRealizada = margemRealizadaKits != null ? margemRealizadaKits : (event.margemRealizadaTotal || 0);
          const metaMargem = event.budgetTicket > 0 && kitCost > 0 ? (event.budgetTicket - kitCost) * event.salesGoal : 0;
          const faltaMargemGap = metaMargem - margemRealizada;
          const metaVolumeJaAtingida = volumeParaMeta <= 0;
          const margemPorInscricao = ticketKitConfig - kitCost;

          const ticketConvergencia = volRestante > 0 && metaMargem > 0
            ? Math.max(0, (faltaMargemGap / volRestante) + kitCost)
            : metaVolumeJaAtingida && margemPorInscricao > 0 && faltaMargemGap > 0
            ? ticketKitConfig
            : 0;

          const volConvergenciaFallback = metaVolumeJaAtingida && margemPorInscricao > 0 && faltaMargemGap > 0
            ? Math.max(0, faltaMargemGap / margemPorInscricao)
            : 0;

          const rows = [
            { label: 'Ticket p/ Meta', ticket: ticketConvergencia, isSeparator: false },
            { label: 'Atual', ticket: ticketKitConfig, isSeparator: false },
            { label: 'Ticket Médio', ticket: ticketMedio, isSeparator: false },
            { label: 'Análise de sensibilidade', ticket: 0, isSeparator: true },
            { label: 'Atual + 10%', ticket: ticketKitConfig * 1.10, isSeparator: false },
            { label: 'Atual + 20%', ticket: ticketKitConfig * 1.20, isSeparator: false },
            { label: 'Atual + 30%', ticket: ticketKitConfig * 1.30, isSeparator: false },
            { label: 'Atual + 40%', ticket: ticketKitConfig * 1.40, isSeparator: false },
          ];

          return (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-200 dark:border-gray-700">
                    <th className="text-left py-2 px-3 text-xs font-semibold text-gray-500 dark:text-gray-400">Ticket vendas futuras</th>
                    <th className="text-right py-2 px-3 text-xs font-semibold text-gray-500 dark:text-gray-400">Ticket</th>
                    <th className="text-right py-2 px-3 text-xs font-semibold text-gray-500 dark:text-gray-400">Vol. Restante</th>
                    <th className="text-right py-2 px-3 text-xs font-semibold text-gray-500 dark:text-gray-400">Margem Adicional</th>
                    <th className="text-right py-2 px-3 text-xs font-semibold text-gray-500 dark:text-gray-400">Margem Global</th>
                    <th className="text-right py-2 px-3 text-xs font-semibold text-gray-500 dark:text-gray-400">Margem Nominal</th>
                    <th className="text-right py-2 px-3 text-xs font-semibold text-gray-500 dark:text-gray-400">Margem %</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => {
                    if (row.isSeparator) {
                      return (
                        <tr key={row.label} className="bg-gray-100 dark:bg-gray-700/60">
                          <td colSpan={7} className="py-2 px-3 text-xs font-semibold text-gray-600 dark:text-gray-300 uppercase tracking-wide">
                            {row.label}
                          </td>
                        </tr>
                      );
                    }
                    const isConvergencia = row.label === 'Ticket p/ Meta';
                    const volEfetivo = isConvergencia && metaVolumeJaAtingida
                      ? volConvergenciaFallback
                      : volRestante;
                    const margemAdicional = (volEfetivo * row.ticket) - (kitCost * volEfetivo);
                    const margemGlobal = margemAdicional + margemRealizada;
                    const margemNominal = margemGlobal - metaMargem;
                    const margemPct = metaMargem > 0 ? (margemNominal / metaMargem) * 100 : 0;
                    return (
                      <tr
                        key={row.label}
                        className={`border-b border-gray-100 dark:border-gray-700/50 ${
                          isConvergencia
                            ? 'bg-purple-50 dark:bg-purple-900/20 font-semibold'
                            : 'hover:bg-gray-50 dark:hover:bg-gray-700/30'
                        }`}
                      >
                        <td className={`py-2.5 px-3 ${isConvergencia ? 'text-purple-700 dark:text-purple-300' : 'text-gray-900 dark:text-white'} font-medium`}>
                          {row.label}
                          {isConvergencia && metaVolumeJaAtingida && faltaMargemGap > 0 && (
                            <span className="ml-1.5 text-[10px] font-normal text-purple-500 dark:text-purple-400">(vol. extra p/ fechar margem)</span>
                          )}
                        </td>
                        <td className={`py-2.5 px-3 text-right ${isConvergencia ? 'text-purple-700 dark:text-purple-300 font-bold' : 'text-gray-700 dark:text-gray-300'}`}>
                          {formatCurrency(row.ticket)}
                        </td>
                        <td className="py-2.5 px-3 text-right text-gray-700 dark:text-gray-300">
                          {formatNumber(volEfetivo)}
                        </td>
                        <td className={`py-2.5 px-3 text-right ${margemAdicional >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}>
                          {formatCurrency(margemAdicional)}
                        </td>
                        <td className={`py-2.5 px-3 text-right ${margemGlobal >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}>
                          {formatCurrency(margemGlobal)}
                        </td>
                        <td className={`py-2.5 px-3 text-right font-semibold ${isConvergencia ? 'text-gray-400 dark:text-gray-500' : margemNominal >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}>
                          {isConvergencia ? '-' : formatCurrency(margemNominal)}
                        </td>
                        <td className={`py-2.5 px-3 text-right font-semibold ${isConvergencia ? 'text-purple-600 dark:text-purple-400' : margemPct >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}>
                          {isConvergencia ? '100%' : `${margemPct >= 0 ? '+' : ''}${Math.round(margemPct * 10) / 10}%`}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          );
        })()}
      </div>

      <div className="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm border border-gray-200 dark:border-gray-700">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-6 flex items-center gap-2">
          Simulação por Volume (ticket fixo)
          <span className="group relative inline-flex items-center">
            <Info className="w-4 h-4 text-gray-400 cursor-help" />
            <span className="absolute left-1/2 -translate-x-1/2 bottom-full mb-2 w-72 rounded-lg bg-gray-800 text-white text-xs px-3 py-2 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-50 shadow-lg">
              Simula o impacto de mudanças no volume de vendas mantendo o ticket atual.
            </span>
          </span>
        </h3>
        {(() => {
          const kitCost = event.kitCostPerUnit || 0;
          const ticketKitConfig = event.ticketAtual || event.averageTicket || 0;
          const volBase = Math.max(volumeParaMeta, 0);
          const margemReal = margemRealizadaKits != null ? margemRealizadaKits : (event.margemRealizadaTotal || 0);
          const metaMargemGlobal = event.budgetTicket > 0 && kitCost > 0 ? (event.budgetTicket - kitCost) * event.salesGoal : 0;

          const multipliers = [0.90, 1.00, 1.05, 1.10, 1.15, 1.20];
          const labels = ['Vendas futuras -10%', 'Meta (0%)', 'Vendas futuras +5%', 'Vendas futuras +10%', 'Vendas futuras +15%', 'Vendas futuras +20%'];

          const rows = multipliers.map((mult, i) => {
            const volFuturo = Math.round(volBase * mult);
            const volGlobal = totalInscritos + volFuturo;
            const margemAdicional = (volFuturo * ticketKitConfig) - (volFuturo * kitCost);
            const margemGlobal = margemAdicional + margemReal;
            const margemNominal = margemGlobal - metaMargemGlobal;
            const margemPct = metaMargemGlobal > 0 ? (margemNominal / metaMargemGlobal) * 100 : 0;
            return {
              label: labels[i],
              volFuturo,
              ticket: ticketKitConfig,
              volGlobal,
              margemAdicional,
              margemGlobal,
              margemNominal,
              margemPct,
              isMeta: mult === 1.00,
            };
          });

          return (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-200 dark:border-gray-700">
                    <th className="text-left py-2 px-3 text-xs font-semibold text-gray-500 dark:text-gray-400">Volume vendas futuras</th>
                    <th className="text-right py-2 px-3 text-xs font-semibold text-gray-500 dark:text-gray-400">Restante</th>
                    <th className="text-right py-2 px-3 text-xs font-semibold text-gray-500 dark:text-gray-400">Ticket</th>
                    <th className="text-right py-2 px-3 text-xs font-semibold text-gray-500 dark:text-gray-400">Volume Global</th>
                    <th className="text-right py-2 px-3 text-xs font-semibold text-gray-500 dark:text-gray-400">Margem Adicional</th>
                    <th className="text-right py-2 px-3 text-xs font-semibold text-gray-500 dark:text-gray-400">Margem Global</th>
                    <th className="text-right py-2 px-3 text-xs font-semibold text-gray-500 dark:text-gray-400">Margem Nominal</th>
                    <th className="text-right py-2 px-3 text-xs font-semibold text-gray-500 dark:text-gray-400">Margem %</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <tr
                      key={row.label}
                      className="border-b border-gray-100 dark:border-gray-700/50 hover:bg-gray-50 dark:hover:bg-gray-700/30"
                    >
                      <td className="py-2.5 px-3 text-gray-900 dark:text-white font-medium">
                        {row.label}
                      </td>
                      <td className="py-2.5 px-3 text-right text-gray-700 dark:text-gray-300">
                        {formatNumber(row.volFuturo)}
                      </td>
                      <td className="py-2.5 px-3 text-right text-gray-700 dark:text-gray-300">
                        {formatCurrency(row.ticket)}
                      </td>
                      <td className="py-2.5 px-3 text-right text-gray-700 dark:text-gray-300 font-semibold">
                        {formatNumber(row.volGlobal)}
                      </td>
                      <td className={`py-2.5 px-3 text-right ${row.margemAdicional >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}>
                        {formatCurrency(row.margemAdicional)}
                      </td>
                      <td className={`py-2.5 px-3 text-right ${row.margemGlobal >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}>
                        {formatCurrency(row.margemGlobal)}
                      </td>
                      <td className={`py-2.5 px-3 text-right font-semibold ${row.margemNominal >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}>
                        {formatCurrency(row.margemNominal)}
                      </td>
                      <td className={`py-2.5 px-3 text-right font-semibold ${row.margemPct >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}>
                        {`${row.margemPct >= 0 ? '+' : ''}${Math.round(row.margemPct * 10) / 10}%`}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          );
        })()}
      </div>

      <div className="bg-white dark:bg-gray-800 rounded-xl p-5 shadow-sm border border-gray-200 dark:border-gray-700">
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-semibold text-gray-900 dark:text-white text-sm">Ações Comerciais</h3>
          <span className="text-[10px] text-gray-400 dark:text-gray-500 font-mono">D-Insc atual: {event.dMinusInscricoes ?? event.dMinus ?? '—'}</span>
        </div>
        {(() => {
          const dInscricoes = event.dMinusInscricoes ?? event.dMinus ?? 999;
          const SLOTS = [
            { ponto_corte: 'D-70', estagio: 'analitico', cutoffValue: 70, nextCutoff: 50 },
            { ponto_corte: 'D-50', estagio: 'analitico', cutoffValue: 50, nextCutoff: 45 },
            { ponto_corte: 'D-45', estagio: 'estrategico', cutoffValue: 45, nextCutoff: 35 },
            { ponto_corte: 'D-35', estagio: 'estrategico', cutoffValue: 35, nextCutoff: 30 },
            { ponto_corte: 'D-30', estagio: 'operacional', cutoffValue: 30, nextCutoff: 15 },
            { ponto_corte: 'D-15', estagio: 'operacional', cutoffValue: 15, nextCutoff: 0 },
          ] as const;
          const STAGE_META: Record<string, { label: string; text: string; bg: string; border: string; badge: string; btn: string }> = {
            analitico: {
              label: 'Analítico',
              text: 'text-indigo-700 dark:text-indigo-300',
              bg: 'bg-indigo-50 dark:bg-indigo-950/30',
              border: 'border-indigo-200 dark:border-indigo-800',
              badge: 'bg-indigo-100 dark:bg-indigo-900/60 text-indigo-800 dark:text-indigo-200',
              btn: 'bg-indigo-600 hover:bg-indigo-700 text-white',
            },
            estrategico: {
              label: 'Estratégico',
              text: 'text-amber-700 dark:text-amber-300',
              bg: 'bg-amber-50 dark:bg-amber-950/30',
              border: 'border-amber-200 dark:border-amber-800',
              badge: 'bg-amber-100 dark:bg-amber-900/60 text-amber-800 dark:text-amber-200',
              btn: 'bg-amber-500 hover:bg-amber-600 text-white',
            },
            operacional: {
              label: 'Operacional',
              text: 'text-rose-700 dark:text-rose-300',
              bg: 'bg-rose-50 dark:bg-rose-950/30',
              border: 'border-rose-200 dark:border-rose-800',
              badge: 'bg-rose-100 dark:bg-rose-900/60 text-rose-800 dark:text-rose-200',
              btn: 'bg-rose-600 hover:bg-rose-700 text-white',
            },
          };
          const legacyActions = (event.commercialActions ?? []).filter(a => !a.ponto_corte || !a.estagio);
          return (
            <div className="space-y-3">
              <div className="grid grid-cols-3 gap-2">
                {SLOTS.map(slot => {
                  const meta = STAGE_META[slot.estagio];
                  const slotAction = (event.commercialActions ?? []).find(a => a.ponto_corte === slot.ponto_corte);
                  const isFuture = dInscricoes > slot.cutoffValue;
                  const isActive = dInscricoes === slot.cutoffValue;
                  const isMissed = dInscricoes < slot.cutoffValue && !slotAction;
                  if (isFuture) {
                    return (
                      <div key={slot.ponto_corte} className="rounded-xl border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/40 p-3 opacity-50 flex flex-col gap-1">
                        <div className="flex items-center justify-between">
                          <span className="text-[10px] font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-wide">{meta.label}</span>
                          <span className="text-[9px] text-gray-300 dark:text-gray-600">🔒</span>
                        </div>
                        <span className="text-lg font-black font-mono text-gray-300 dark:text-gray-600 leading-none">{slot.ponto_corte}</span>
                        <span className="text-[10px] text-gray-300 dark:text-gray-600">faltam {dInscricoes - slot.cutoffValue}d</span>
                      </div>
                    );
                  }
                  if (isMissed) {
                    return (
                      <div key={slot.ponto_corte} className="rounded-xl border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/40 p-3 opacity-40 flex flex-col gap-1">
                        <div className="flex items-center justify-between">
                          <span className="text-[10px] font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-wide">{meta.label}</span>
                          <span className="text-[9px] text-gray-400 dark:text-gray-500">—</span>
                        </div>
                        <span className="text-lg font-black font-mono text-gray-300 dark:text-gray-600 leading-none">{slot.ponto_corte}</span>
                        <span className="text-[10px] text-gray-400 dark:text-gray-500">janela encerrada</span>
                      </div>
                    );
                  }
                  if (slotAction) {
                    return (
                      <div key={slot.ponto_corte} className={`rounded-xl border-2 ${meta.border} ${meta.bg} p-3 flex flex-col gap-1.5`}>
                        <div className="flex items-center justify-between">
                          <span className={`text-[10px] font-semibold uppercase tracking-wide ${meta.text}`}>{meta.label}</span>
                          <button onClick={() => handleDeleteAction(slotAction.id)} className="p-0.5 text-gray-300 hover:text-red-400 transition-colors" title="Excluir">
                            <Trash2 className="w-3 h-3" />
                          </button>
                        </div>
                        <div className="flex items-center gap-1.5">
                          <span className={`text-lg font-black font-mono leading-none ${meta.text}`}>{slot.ponto_corte}</span>
                          {slotAction.snapshot_isc != null && (
                            <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${meta.badge}`}>ISC {slotAction.snapshot_isc.toFixed(2)}</span>
                          )}
                        </div>
                        <p className="text-[11px] text-gray-700 dark:text-gray-300 leading-snug line-clamp-2">{slotAction.description}</p>
                        <div className="flex flex-wrap gap-1 mt-1">
                          {slotAction.snapshot_d_minus != null && (
                            <span className="inline-flex items-center px-1.5 py-0.5 rounded bg-white/70 dark:bg-gray-700/70 border border-gray-200 dark:border-gray-600 text-[10px] text-gray-600 dark:text-gray-300">D-<span className="font-bold ml-0.5">{slotAction.snapshot_d_minus}</span></span>
                          )}
                          {slotAction.snapshot_ia730 != null && (
                            <span className="inline-flex items-center px-1.5 py-0.5 rounded bg-white/70 dark:bg-gray-700/70 border border-gray-200 dark:border-gray-600 text-[10px] text-gray-600 dark:text-gray-300">IA730 <span className="font-bold ml-0.5">{slotAction.snapshot_ia730.toFixed(2)}</span></span>
                          )}
                          {slotAction.snapshot_rolling14d != null && (
                            <span className="inline-flex items-center px-1.5 py-0.5 rounded bg-white/70 dark:bg-gray-700/70 border border-gray-200 dark:border-gray-600 text-[10px] text-gray-600 dark:text-gray-300">14d <span className="font-bold ml-0.5">{slotAction.snapshot_rolling14d.toFixed(2)}</span></span>
                          )}
                          {slotAction.snapshot_curva_percent != null && (
                            <span className="inline-flex items-center px-1.5 py-0.5 rounded bg-white/70 dark:bg-gray-700/70 border border-gray-200 dark:border-gray-600 text-[10px] text-gray-600 dark:text-gray-300">Curva <span className="font-bold ml-0.5">{(slotAction.snapshot_curva_percent * 100).toFixed(0)}%</span></span>
                          )}
                          {slotAction.snapshot_vendas_acumuladas != null && (
                            <span className="inline-flex items-center px-1.5 py-0.5 rounded bg-white/70 dark:bg-gray-700/70 border border-gray-200 dark:border-gray-600 text-[10px] text-gray-600 dark:text-gray-300">Vnd <span className="font-bold ml-0.5">{slotAction.snapshot_vendas_acumuladas.toLocaleString('pt-BR')}</span></span>
                          )}
                          {slotAction.snapshot_playbook_letter && (
                            <span className="inline-flex items-center px-1.5 py-0.5 rounded bg-blue-100 dark:bg-blue-900/40 border border-blue-200 dark:border-blue-700 text-[10px] font-bold text-blue-700 dark:text-blue-300">{slotAction.snapshot_playbook_letter}</span>
                          )}
                        </div>
                        <span className="text-[10px] text-gray-400 dark:text-gray-500 mt-auto">{new Date(slotAction.date + 'T00:00:00').toLocaleDateString('pt-BR')}</span>
                      </div>
                    );
                  }
                  return (
                    <div key={slot.ponto_corte} className={`rounded-xl border-2 border-dashed ${meta.border} p-3 flex flex-col gap-1.5`}>
                      <div className="flex items-center justify-between">
                        <span className={`text-[10px] font-semibold uppercase tracking-wide ${meta.text}`}>{meta.label}</span>
                        <span className="text-[9px] text-yellow-500">●</span>
                      </div>
                      <span className={`text-lg font-black font-mono leading-none ${meta.text}`}>{slot.ponto_corte}</span>
                      <button
                        onClick={() => {
                          setActionForm(f => ({ ...f, forced_ponto_corte: slot.ponto_corte, forced_estagio: slot.estagio }));
                          setShowActionModal(true);
                          setActionError(null);
                        }}
                        className={`mt-auto w-full flex items-center justify-center gap-1 px-2 py-1.5 text-[11px] font-medium rounded-lg transition-colors ${meta.btn}`}
                      >
                        <Plus className="w-3 h-3" />
                        Registrar
                      </button>
                    </div>
                  );
                })}
              </div>
              {legacyActions.length > 0 && (
                <div className="pt-2 border-t border-gray-100 dark:border-gray-700">
                  <p className="text-[10px] font-bold uppercase tracking-widest text-gray-400 dark:text-gray-500 mb-2">Histórico</p>
                  <div className="space-y-1.5">
                    {legacyActions.map(action => (
                      <div key={action.id} className="flex items-center justify-between gap-2 py-1">
                        <p className="text-xs text-gray-700 dark:text-gray-300 leading-snug truncate">{action.description}</p>
                        <div className="flex items-center gap-1.5 flex-shrink-0">
                          <span className="text-[10px] text-gray-400">{new Date(action.date + 'T00:00:00').toLocaleDateString('pt-BR')}</span>
                          <button onClick={() => handleDeleteAction(action.id)} className="p-0.5 text-gray-300 hover:text-red-400 transition-colors">
                            <Trash2 className="w-3 h-3" />
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          );
        })()}
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

      {showActionModal && (() => {
        const dMinus = event?.dMinus ?? 0;
        const dMinusInscricoes = event?.dMinusInscricoes ?? dMinus;
        const cutoffInfo = actionForm.forced_ponto_corte && actionForm.forced_estagio
          ? { ponto_corte: actionForm.forced_ponto_corte, estagio: actionForm.forced_estagio }
          : getActionCutoffInfo(dMinus);
        const stageLabel: Record<string, string> = { analitico: 'Analítico', estrategico: 'Estratégico', operacional: 'Operacional' };
        const stageColor: Record<string, string> = {
          analitico: 'bg-indigo-50 dark:bg-indigo-950/30 text-indigo-700 dark:text-indigo-300 border-indigo-200 dark:border-indigo-800',
          estrategico: 'bg-amber-50 dark:bg-amber-950/30 text-amber-700 dark:text-amber-300 border-amber-200 dark:border-amber-800',
          operacional: 'bg-rose-50 dark:bg-rose-950/30 text-rose-700 dark:text-rose-300 border-rose-200 dark:border-rose-800',
        };
        const iscStatusMap: Record<string, string> = { accelerating: 'Forte', stable: 'Estável', decelerating: 'Fraco' };
        const iscColorMap: Record<string, string> = { accelerating: 'text-green-600 dark:text-green-400', stable: 'text-yellow-600 dark:text-yellow-400', decelerating: 'text-red-500 dark:text-red-400' };
        return (
          <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
            <div className="bg-white dark:bg-gray-800 rounded-xl w-full max-w-lg shadow-xl flex flex-col max-h-[90vh] overflow-y-auto">
              <div className="flex items-center justify-between p-5 pb-0">
                <h3 className="text-lg font-semibold text-gray-900 dark:text-white">Registrar Ação Comercial</h3>
                <button onClick={() => { setShowActionModal(false); setActionError(null); setActionForm(f => ({ ...f, forced_ponto_corte: '', forced_estagio: '' })); }} className="p-1 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300">
                  <X className="w-5 h-5" />
                </button>
              </div>

              <div className="p-5 space-y-4">
                {actionError && (
                  <div className="flex items-start gap-2 p-3 rounded-lg bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-800 text-sm text-red-700 dark:text-red-300">
                    <span className="shrink-0 mt-0.5">⚠️</span>
                    <span>{actionError}</span>
                  </div>
                )}

                <div className={`rounded-lg border p-3 ${stageColor[cutoffInfo.estagio] || 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 border-gray-200 dark:border-gray-600'}`}>
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-xs font-bold uppercase tracking-wider opacity-70">Ponto de Corte</p>
                      <p className="text-xl font-bold font-mono mt-0.5">{cutoffInfo.ponto_corte}</p>
                    </div>
                    <div className="text-right">
                      <p className="text-xs font-bold uppercase tracking-wider opacity-70">Estágio</p>
                      <p className="text-sm font-semibold mt-0.5">{stageLabel[cutoffInfo.estagio] || cutoffInfo.estagio}</p>
                    </div>
                  </div>
                  <p className="text-xs opacity-60 mt-1">Snapshot dos dados ISC será congelado ao salvar</p>
                </div>

                {event && (
                  <div className="rounded-lg border border-gray-200 dark:border-gray-600 bg-gray-50 dark:bg-gray-700/50 p-3">
                    <p className="text-xs font-bold text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-2">Snapshot ISC atual</p>
                    <div className="grid grid-cols-2 gap-2">
                      <div className="flex flex-col">
                        <span className="text-[10px] text-gray-400 dark:text-gray-500 uppercase tracking-wide">ISC</span>
                        <span className={`text-base font-bold ${iscColorMap[event.iscStatus] || 'text-gray-700 dark:text-gray-300'}`}>
                          {event.isc?.toFixed(2)} <span className="text-xs font-normal">({iscStatusMap[event.iscStatus] || event.iscStatus})</span>
                        </span>
                      </div>
                      <div className="flex flex-col">
                        <span className="text-[10px] text-gray-400 dark:text-gray-500 uppercase tracking-wide">D-Inscrição</span>
                        <span className="text-base font-bold text-gray-700 dark:text-gray-300">D-{dMinusInscricoes}</span>
                      </div>
                      {event.iscComponents && (
                        <>
                          <div className="flex flex-col">
                            <span className="text-[10px] text-gray-400 dark:text-gray-500 uppercase tracking-wide">IA 730</span>
                            <span className="text-sm font-semibold text-gray-700 dark:text-gray-300">{event.iscComponents.ia730.toFixed(2)}</span>
                          </div>
                          <div className="flex flex-col">
                            <span className="text-[10px] text-gray-400 dark:text-gray-500 uppercase tracking-wide">Rolling 14d</span>
                            <span className="text-sm font-semibold text-gray-700 dark:text-gray-300">{event.iscComponents.rolling14d.toFixed(2)}</span>
                          </div>
                          <div className="flex flex-col">
                            <span className="text-[10px] text-gray-400 dark:text-gray-500 uppercase tracking-wide">Curva D%</span>
                            <span className="text-sm font-semibold text-gray-700 dark:text-gray-300">{event.iscComponents.curvaDPercent.toFixed(2)}</span>
                          </div>
                          <div className="flex flex-col">
                            <span className="text-[10px] text-gray-400 dark:text-gray-500 uppercase tracking-wide">Vendas acumuladas</span>
                            <span className="text-sm font-semibold text-gray-700 dark:text-gray-300">{event.currentSales?.toLocaleString('pt-BR')}</span>
                          </div>
                        </>
                      )}
                      {event.suggestedAction?.letter && (
                        <div className="col-span-2 flex flex-col">
                          <span className="text-[10px] text-gray-400 dark:text-gray-500 uppercase tracking-wide">Playbook</span>
                          <span className="text-sm font-bold text-blue-600 dark:text-blue-400">{event.suggestedAction.letter} — {event.suggestedAction.name}</span>
                        </div>
                      )}
                    </div>
                  </div>
                )}

                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Tipo de Ação</label>
                  <select
                    value={actionForm.tipo}
                    onChange={(e) => { setActionForm({ ...actionForm, tipo: e.target.value }); setActionError(null); }}
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 text-sm"
                  >
                    {tipoOptions.map(opt => (
                      <option key={opt.value} value={opt.value}>{opt.label}</option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Data da Ação</label>
                  <input
                    type="date"
                    value={actionForm.data_acao}
                    onChange={(e) => setActionForm({ ...actionForm, data_acao: e.target.value })}
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 text-sm"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Descrição</label>
                  <textarea
                    value={actionForm.descricao}
                    onChange={(e) => setActionForm({ ...actionForm, descricao: e.target.value })}
                    placeholder="Descreva a ação realizada..."
                    rows={3}
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 resize-none text-sm"
                  />
                </div>
              </div>

              <div className="flex gap-3 p-5 pt-0">
                <button
                  onClick={() => { setShowActionModal(false); setActionError(null); setActionForm(f => ({ ...f, forced_ponto_corte: '', forced_estagio: '' })); }}
                  className="flex-1 px-4 py-2 border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors text-sm"
                >
                  Cancelar
                </button>
                <button
                  onClick={handleSaveAction}
                  disabled={savingAction || !actionForm.descricao.trim()}
                  className="flex-1 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2 text-sm font-medium"
                >
                  {savingAction ? (
                    <><Loader2 className="w-4 h-4 animate-spin" />Salvando...</>
                  ) : 'Salvar Ação'}
                </button>
              </div>
            </div>
          </div>
        );
      })()}
      </>
      )}
      </div>
    </div>
  );
};

export default EventDetail;
