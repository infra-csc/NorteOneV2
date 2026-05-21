import React, { useState, useEffect, useRef, useCallback, lazy, Suspense } from 'react';
import AtualizarHojeModal, { SyncStatus, SyncResult } from '../../components/marketing/AtualizarHojeModal';
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
  Pencil,
  Eye,
  RefreshCw,
  TableProperties,
  ChevronDown,
  ChevronUp,
  Archive,
  Sliders,
  DatabaseZap,
  CheckCheck
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
import api, { marketingService, MarketingEvent, clearMarketingDashboardCache, adminService } from '../../services/api';
import { 
  getISCColor, 
  getISCEmoji, 
  isInCriticalWindow,
  getISCStatus
} from '../../types/marketingPerformance';
import { useTheme } from '../../context/ThemeContext';
import { usePermissions } from '../../context/PermissionContext';
const EventInsights = React.memo(lazy(() => import('./EventInsights')));
const EventSimulator = React.memo(lazy(() => import('./EventSimulator')));
const DailySalesTable = React.memo(lazy(() => import('./DailySalesTable')));

interface CommercialAction {
  id: string;
  tipo?: string;
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

const mapEventResponseToActions = (actions: any[]): CommercialAction[] =>
  actions.map((a: any) => ({
    id: a.id,
    tipo: a.tipo,
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

type _ExpectedItem = { expected: number };
type _NormExpectedFields = {
  normalizedExpected: number;
  expectedLocalMedian: number | null;
  expectedOutlierLimit: number | null;
  expectedIsOutlier: boolean;
  expectedExcessRemoved: number;
  expectedExcessReceived: number;
  cumulativeNormalizedExpected: number;
};

function normalizeExpectedOutliers<T extends _ExpectedItem>(
  items: T[],
  window = 7,
  threshold = 2.0,
  spread = 3,
): (T & _NormExpectedFields)[] {
  const n = items.length;
  const median = (arr: number[]): number => {
    if (arr.length === 0) return 0;
    const s = [...arr].sort((a, b) => a - b);
    return s[Math.floor(s.length / 2)];
  };
  if (n < window) {
    let cum = 0;
    return items.map(it => {
      const exp = it.expected || 0;
      cum += exp;
      return {
        ...it,
        normalizedExpected: Math.round(exp * 10) / 10,
        expectedLocalMedian: null,
        expectedOutlierLimit: null,
        expectedIsOutlier: false,
        expectedExcessRemoved: 0,
        expectedExcessReceived: 0,
        cumulativeNormalizedExpected: Math.round(cum * 10) / 10,
      };
    });
  }
  const raw = items.map(it => it.expected || 0);
  const normalized = [...raw];
  const excessReceived = new Array<number>(n).fill(0);
  const excessRemoved = new Array<number>(n).fill(0);
  const localMedians: (number | null)[] = new Array(n).fill(null);
  const outlierLimits: (number | null)[] = new Array(n).fill(null);
  const isOutlier: boolean[] = new Array(n).fill(false);
  const globalMedian = median(raw);
  const half = Math.floor(window / 2);
  for (let i = 0; i < n; i++) {
    const lo = Math.max(0, i - half);
    const hi = Math.min(n, i + half + 1);
    const lm = median(raw.slice(lo, hi));
    const limit = Math.max(lm * threshold, globalMedian * 0.5, 5);
    localMedians[i] = Math.round(lm * 10) / 10;
    outlierLimits[i] = Math.round(limit * 10) / 10;
    if (raw[i] > limit) {
      const excess = raw[i] - limit;
      normalized[i] = limit;
      isOutlier[i] = true;
      excessRemoved[i] = excess;
      let totalShare = 0;
      for (let j = Math.max(0, i - spread); j < Math.min(n, i + spread + 1); j++) {
        if (j !== i) totalShare++;
      }
      if (totalShare > 0) {
        const share = excess / totalShare;
        for (let j = Math.max(0, i - spread); j < Math.min(n, i + spread + 1); j++) {
          if (j !== i) {
            normalized[j] += share;
            excessReceived[j] += share;
          }
        }
      }
    }
  }
  let cum = 0;
  return items.map((it, i) => {
    cum += normalized[i];
    return {
      ...it,
      normalizedExpected: Math.round(normalized[i] * 10) / 10,
      expectedLocalMedian: localMedians[i],
      expectedOutlierLimit: outlierLimits[i],
      expectedIsOutlier: isOutlier[i],
      expectedExcessRemoved: Math.round(excessRemoved[i] * 10) / 10,
      expectedExcessReceived: Math.round(excessReceived[i] * 10) / 10,
      cumulativeNormalizedExpected: Math.round(cum * 10) / 10,
    };
  });
}

// Cache em memória do estado completo do evento (module-level).
// Persiste entre navegações (o componente pode desmontar/remontar).
// Garante que na segunda visita os gráficos aparecem imediatamente
// e o banner de "Atualizando..." só aparece na primeira visita.
interface _EventDetailSnapshot {
  event: ExtendedEvent;
  comparacaoAnual: any;
  cenariosCiclismo: any;
  faixasPrecoSite: any;
  avisos: string[];
  projetosVinculados: { id: number; nome: string; sku: string }[];
  anosDisponiveis: number[];
  cachedAt: number;
}
const _eventDetailCache = new Map<string, _EventDetailSnapshot>();

// Caches módulo para dados secundários — evitam re-fetch ao navegar de volta ao evento.
// Padrão SWR: na re-visita usa dado do cache imediatamente e busca atualização em background.
interface _CurvaComparativaCache {
  data: any[]; anoAtual: number; anoAnterior: number; modo: string;
  dataEventoAtual: string | null; dataEventoAnterior: string | null; meta: any; cachedAt: number;
}
const _curvaComparativaCache = new Map<string, _CurvaComparativaCache>();
const _salesAvgCache = new Map<string, { data: any; period: number; cachedAt: number }>();
const _curvaSnapshotModCache = new Map<string, { data: any; cachedAt: number }>();

const EventDetail: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const { isDark } = useTheme();
  const { permissions } = usePermissions();
  const isAdmin = permissions?.is_admin ?? false;
  const anoParam = searchParams.get('ano') ? parseInt(searchParams.get('ano')!) : undefined;
  // Consulta o cache de módulo ANTES dos useState para que o estado seja
  // inicializado com os dados completos (inclusive dailySales/gráficos) se o
  // evento já tiver sido aberto antes nesta sessão.
  const _detailCacheKey = `${id}_${anoParam ?? 'cur'}`;
  const _detailCached = _eventDetailCache.get(_detailCacheKey);
  // O cache dura a sessão inteira — sem TTL. O backend já aplica o overlay
  // de hoje em cada resposta (apply_today_overlay), então os dados são
  // sempre atualizados silenciosamente a cada visita. O "Atualizar Hoje"
  // existe para o usuário forçar a atualização quando quiser.
  const _detailCacheFresh = !!_detailCached;
  // Lookups dos caches secundários — usados para inicializar estados sem esperar o fetch.
  const _curvaCached = _curvaComparativaCache.get(_detailCacheKey);
  const _salesCacheKey = `${_detailCacheKey}_30`;
  const _salesCached = _salesAvgCache.get(_salesCacheKey);
  const _snapModCached = _curvaSnapshotModCache.get(_detailCacheKey);
  // Seed instantly with the snapshot the user already saw on the dashboard so the
  // transition is imperceptible. Fresh data overwrites it once the API responds.
  const previewEvent = (location.state as any)?.previewEvent as MarketingEvent | undefined;
  const [event, setEvent] = useState<ExtendedEvent | null>(
    _detailCacheFresh ? _detailCached!.event : (previewEvent ? { ...previewEvent } : null)
  );
  const [loading, setLoading] = useState(!_detailCacheFresh && !previewEvent);
  // Rastreia se o primeiro fetch completo (com dailySales) já chegou.
  // false quando previewEvent é usado como estado inicial (sem dailySales),
  // true quando cache fresco existe ou após o primeiro fetch bem-sucedido.
  const [isFirstFetchDone, setIsFirstFetchDone] = useState(_detailCacheFresh);
  // Banner "Atualizando dados em tempo real..." aparece somente se a requisição
  // demorar mais que DETAILS_LOADING_DELAY_MS (caminho lento). Para respostas
  // rápidas (snapshot fresco em ~100ms), o banner nunca chega a aparecer e a
  // experiência fica perceptivelmente "instantânea".
  const [detailsLoading, setDetailsLoading] = useState(false);
  const detailsLoadingTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const DETAILS_LOADING_DELAY_MS = 600;
  const [error, setError] = useState<string | null>(null);
  const [showActionModal, setShowActionModal] = useState(false);
  const [viewOnlyAction, setViewOnlyAction] = useState(false);
  const [acoesColapsadas, setAcoesColapsadas] = useState(false);
  const [showMargemInfo, setShowMargemInfo] = useState(false);
  const [showReceitaOrcada, setShowReceitaOrcada] = useState(false);
  const [showReceitaRealizada, setShowReceitaRealizada] = useState(false);
  const [showDetalheVendas, setShowDetalheVendas] = useState(false);
  const getTodayLocalDate = () => {
    const now = new Date();
    return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
  };

  const [actionForm, setActionForm] = useState({
    tipo: '',
    descricao: '',
    data_acao: getTodayLocalDate(),
    projeto_id_selecionado: 0,
    forced_ponto_corte: '',
    forced_estagio: '',
  });
  const [editingActionId, setEditingActionId] = useState<string | null>(null);
  const [savingAction, setSavingAction] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [projetosVinculados, setProjetosVinculados] = useState<{id: number; nome: string; sku: string}[]>(_detailCacheFresh ? _detailCached!.projetosVinculados : []);
  const [comparacaoAnual, setComparacaoAnual] = useState<any>(_detailCacheFresh ? _detailCached!.comparacaoAnual : null);
  const [anosDisponiveis, setAnosDisponiveis] = useState<number[]>(_detailCacheFresh ? _detailCached!.anosDisponiveis : []);
  const [faixasPrecoSite, setFaixasPrecoSite] = useState<{ kit_basico: { faixa: string; qtd: number; tkt_medio: number; total: number }[]; kit_participacao: { faixa: string; qtd: number; tkt_medio: number; total: number }[] } | null>(_detailCacheFresh ? _detailCached!.faixasPrecoSite : null);
  const [simuladorFaixas, setSimuladorFaixas] = useState(false);
  const [projetadoFaixas, setProjetadoFaixas] = useState<{ id: string; nome: string; preco: string; qtd: string }[]>([]);

  const [cenariosCiclismo, setCenariosCiclismo] = useState<{ [key: string]: { orcado_pago: number; tkt_medio_orcado: number; real_vendas?: number; real_receita?: number; real_tkt_medio?: number; custo_kit?: number; margem_orcada?: number; margem_realizada?: number } } | null>(_detailCacheFresh ? _detailCached!.cenariosCiclismo : null);
  const [avisos, setAvisos] = useState<string[]>(_detailCacheFresh ? _detailCached!.avisos : []);
  const [curvaData, setCurvaData] = useState<any[]>(_curvaCached?.data ?? []);
  const [curvaMeta, setCurvaMeta] = useState<any>(_curvaCached?.meta ?? null);
  const [showOverrideModal, setShowOverrideModal] = useState(false);
  const [showCurveInfoModal, setShowCurveInfoModal] = useState(false);
  const [availableCurves, setAvailableCurves] = useState<{grupo: string; anoReferencia: number; pontos: number; origem: string}[]>([]);
  const [overrideSearch, setOverrideSearch] = useState('');
  const [savingOverride, setSavingOverride] = useState(false);
  const [curvaAnoAtual, setCurvaAnoAtual] = useState<number>(_curvaCached?.anoAtual ?? new Date().getFullYear());
  const [curvaAnoAnterior, setCurvaAnoAnterior] = useState<number>(_curvaCached?.anoAnterior ?? new Date().getFullYear() - 1);
  const [activeTab, setActiveTab] = useState<'dashboard' | 'simulator' | 'complementares' | 'controle'>('dashboard');
  // curvaLoading: começa true apenas se não há cache → evita flash de "sem dados" antes do fetch
  const [curvaLoading, setCurvaLoading] = useState(!_curvaCached);
  const [curvaMode, setCurvaMode] = useState<'vendas' | 'receita'>('vendas');
  const [curvaView, setCurvaView] = useState<'semanal' | 'acumulado'>('acumulado');
  const [curvaModo, setCurvaModo] = useState<string>(_curvaCached?.modo ?? 'mensal');
  const [dataEventoAtual, setDataEventoAtual] = useState<string | null>(_curvaCached?.dataEventoAtual ?? null);
  const [dataEventoAnterior, setDataEventoAnterior] = useState<string | null>(_curvaCached?.dataEventoAnterior ?? null);
  const [salesAverages, setSalesAverages] = useState<any>(_salesCached?.data ?? null);
  const [salesAvgLoading, setSalesAvgLoading] = useState(!_salesCached);
  const [salesAvgPeriod, setSalesAvgPeriod] = useState(30);
  const [refreshing, setRefreshing] = useState(false);
  const [refreshSuccess, setRefreshSuccess] = useState(false);
  const [refreshError, setRefreshError] = useState<string | null>(null);
  // Piso de currentSales confirmado pelo último atualizarHoje bem-sucedido.
  // Garante que re-fetches subsequentes nunca baixem o valor abaixo do que
  // o sync confirmou, mesmo que o backend recompute com dado parcial do Magento.
  // Expira em 2 min para não congelar o valor indefinidamente.
  const postSyncFloorRef = useRef<{ value: number; until: number } | null>(null);
  const [showSyncModal, setShowSyncModal] = useState(false);
  const [syncStatus, setSyncStatus] = useState<SyncStatus>('loading');
  const [syncResult, setSyncResult] = useState<SyncResult | null>(null);
  const [syncErrorMsg, setSyncErrorMsg] = useState<string | null>(null);
  const [syncStartTime, setSyncStartTime] = useState<number | undefined>(undefined);
  const [chartPeriod, setChartPeriod] = useState<number | null>(null);
  const [attainmentPeriod, setAttainmentPeriod] = useState<number | null>(30);
  const [attainmentMode, setAttainmentMode] = useState<'acumulado' | 'diario'>('acumulado');
  const [controleSubTab, setControleSubTab] = useState<'tabela' | 'curva'>('tabela');
  const [curvaSnapshot, setCurvaSnapshot] = useState<{ evento_grupo: string; ano_referencia: number; sales_goal: number; data: { d_minus: number; percentual_acumulado: number; percentual_dia: number; meta_acumulado: number; meta_dia: number }[]; message?: string } | null>(_snapModCached?.data ?? null);
  const [curvaSnapshotLoading, setCurvaSnapshotLoading] = useState(false);
  const [showNormalized, setShowNormalized] = useState(false);
  const [showNormalizationDetail, setShowNormalizationDetail] = useState(false);
  const [isStaleData, setIsStaleData] = useState(false);
  const [ultimaAtualizacao, setUltimaAtualizacao] = useState<string | null>(null);
  const [ultimaAtualizacaoInscricoes, setUltimaAtualizacaoInscricoes] = useState<string | null>(null);
  const [snapshotComputedAt, setSnapshotComputedAt] = useState<string | null>(null);
  const [isPreparing, setIsPreparing] = useState(false);
  const [preparingGaveUp, setPreparingGaveUp] = useState(false);
  const silentRefetchDoneRef = useRef(false);
  const fetchEventRef = useRef<((forceRefresh?: boolean, silent?: boolean, forceMagentoRefresh?: boolean) => void) | null>(null);
  // Rastreia se algum dado de evento já foi exibido na tela. Persistido como ref
  // para que fetchEvent (closure do useEffect) acesse o valor atualizado mesmo
  // após re-fetches subsequentes, sem precisar recriar a função.
  const hasEventDataRef = useRef<boolean>(!!_detailCacheFresh || !!previewEvent);
  const [magentoRefreshing, setMagentoRefreshing] = useState(false);
  const preparingStartedAtRef = useRef<number | null>(null);
  const PREPARING_GIVE_UP_MS = 3 * 60 * 1000;

  const isConsolidated = id?.startsWith('grp_') ?? false;

  // ── Consolidação de evento único (admin) ────────────────────────────────────
  const [showConsolidarModal, setShowConsolidarModal] = useState(false);
  const [consolidarIncremental, setConsolidarIncremental] = useState(false);
  const [consolidarLoading, setConsolidarLoading] = useState(false);
  const [consolidarResult, setConsolidarResult] = useState<{
    status: string; qtd_antes: number | null; qtd_depois: number | null; duracao_ms: number;
  } | null>(null);
  const [consolidarError, setConsolidarError] = useState<string | null>(null);

  const handleOpenSyncModal = useCallback(() => setShowSyncModal(true), []);

  const handleConsolidarEvento = async () => {
    const grupoNome = isConsolidated ? id!.replace(/^grp_/, '') : id!;
    setConsolidarLoading(true);
    setConsolidarError(null);
    setConsolidarResult(null);
    try {
      const res = await adminService.consolidarEvento(grupoNome, consolidarIncremental);
      setConsolidarResult({ status: res.status, qtd_antes: res.qtd_antes, qtd_depois: res.qtd_depois, duracao_ms: res.duracao_ms });
      // Invalida o cache do dashboard (lista de eventos) para que ao voltar
      // à primeira tela os dados reflitam a reconsolidação recém-executada.
      clearMarketingDashboardCache();
      // Recarrega o detalhe do evento imediatamente em background com force_refresh=true,
      // bypassing o event_detail_cache do backend. Assim quando o usuário fechar o modal
      // os dados já estarão atualizados na tela sem precisar clicar em nada.
      fetchEventRef.current?.(true, true);
    } catch (e: any) {
      setConsolidarError(e?.response?.data?.detail ?? e?.message ?? 'Erro ao consolidar');
    } finally {
      setConsolidarLoading(false);
    }
  };
  // ────────────────────────────────────────────────────────────────────────────

  const projFaixasHydratedRef = useRef<string | null>(null);
  const projFaixasFetchTokenRef = useRef<number>(0);
  const projFaixasSaveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const projFaixasSkipNextSaveRef = useRef<boolean>(false);

  useEffect(() => {
    if (!id || projFaixasHydratedRef.current !== id) return;
    if (projFaixasSkipNextSaveRef.current) {
      projFaixasSkipNextSaveRef.current = false;
      return;
    }
    try {
      if (projetadoFaixas.length === 0) {
        localStorage.removeItem(`proj_faixas_${id}`);
      } else {
        localStorage.setItem(`proj_faixas_${id}`, JSON.stringify(projetadoFaixas));
      }
    } catch {
    }
    if (projFaixasSaveTimerRef.current) clearTimeout(projFaixasSaveTimerRef.current);
    const savedId = id;
    const snapshot = projetadoFaixas;
    projFaixasSaveTimerRef.current = setTimeout(() => {
      if (snapshot.length === 0) {
        marketingService.deleteProjetadoFaixas(savedId).catch(() => {});
      } else {
        marketingService.upsertProjetadoFaixas(savedId, snapshot).catch(() => {});
      }
    }, 800);
    return () => {
      if (projFaixasSaveTimerRef.current) clearTimeout(projFaixasSaveTimerRef.current);
    };
  }, [id, projetadoFaixas]);

  const abortControllerRef = useRef<AbortController | null>(null);
  const curvaAbortRef = useRef<AbortController | null>(null);
  const staleRetryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    silentRefetchDoneRef.current = false;
    preparingStartedAtRef.current = null;
    setIsPreparing(false);
    setPreparingGaveUp(false);
    setSimuladorFaixas(false);
    const projFaixasFetchId = id;
    projFaixasHydratedRef.current = null;
    projFaixasFetchTokenRef.current += 1;
    const myToken = projFaixasFetchTokenRef.current;
    if (projFaixasFetchId) {
      marketingService.getProjetadoFaixas(projFaixasFetchId).then((res) => {
        if (projFaixasFetchTokenRef.current !== myToken) return;
        const isValid = Array.isArray(res.faixas) && res.faixas.every(
          (r: unknown) => r !== null && typeof r === 'object' &&
            'id' in (r as object) && 'nome' in (r as object) &&
            'preco' in (r as object) && 'qtd' in (r as object)
        );
        const faixas = isValid ? res.faixas : [];
        projFaixasSkipNextSaveRef.current = true;
        setProjetadoFaixas(faixas);
        if (faixas.length > 0) {
          try { localStorage.setItem(`proj_faixas_${projFaixasFetchId}`, JSON.stringify(faixas)); } catch {}
        } else {
          try { localStorage.removeItem(`proj_faixas_${projFaixasFetchId}`); } catch {}
        }
        projFaixasHydratedRef.current = projFaixasFetchId;
      }).catch(() => {
        if (projFaixasFetchTokenRef.current !== myToken) return;
        try {
          const saved = localStorage.getItem(`proj_faixas_${projFaixasFetchId}`);
          const parsed = saved ? JSON.parse(saved) : [];
          const isValid = Array.isArray(parsed) && parsed.every(
            (r: unknown) => r !== null && typeof r === 'object' &&
              'id' in (r as object) && 'nome' in (r as object) &&
              'preco' in (r as object) && 'qtd' in (r as object)
          );
          projFaixasSkipNextSaveRef.current = true;
          setProjetadoFaixas(isValid ? parsed : []);
        } catch {
          projFaixasSkipNextSaveRef.current = true;
          setProjetadoFaixas([]);
        }
        projFaixasHydratedRef.current = projFaixasFetchId;
      });
    } else {
      setProjetadoFaixas([]);
    }
    const controller = new AbortController();
    abortControllerRef.current = controller;

    const fetchEvent = async (forceRefresh = false, silent = false, forceMagentoRefresh = false) => {
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
        // Banner com delay: só aparece quando não há absolutamente nenhum dado
        // na tela (acesso direto pela URL sem cache e sem previewEvent).
        // Durante forceRefresh ou quando já temos dados, o carregamento é sempre
        // silencioso — gráficos permanecem visíveis e só são substituídos quando
        // a nova resposta chega.
        if (!silent && !hasEventDataRef.current) {
          if (detailsLoadingTimerRef.current) clearTimeout(detailsLoadingTimerRef.current);
          detailsLoadingTimerRef.current = setTimeout(() => {
            if (!controller.signal.aborted) setDetailsLoading(true);
          }, DETAILS_LOADING_DELAY_MS);
        }
        const response = await marketingService.getEventoById(id, controller.signal, anoParam, forceRefresh || undefined, forceMagentoRefresh || undefined);
        if (controller.signal.aborted) return;

        // Backend sinaliza que ainda está preparando o snapshot — retry em 5s.
        if ((response as any)?.status === 'preparing') {
          if (!event) setLoading(true);
          setIsPreparing(true);
          if (preparingStartedAtRef.current === null) {
            preparingStartedAtRef.current = Date.now();
          }
          const elapsed = Date.now() - (preparingStartedAtRef.current || Date.now());
          if (elapsed >= PREPARING_GIVE_UP_MS) {
            setPreparingGaveUp(true);
            if (staleRetryTimerRef.current) {
              clearTimeout(staleRetryTimerRef.current);
              staleRetryTimerRef.current = null;
            }
            return;
          }
          if (staleRetryTimerRef.current) clearTimeout(staleRetryTimerRef.current);
          const retrySec = Number((response as any).retry_after_seconds) || 5;
          staleRetryTimerRef.current = setTimeout(() => {
            if (!controller.signal.aborted && fetchEventRef.current) {
              fetchEventRef.current(false, true);
            }
          }, retrySec * 1000);
          return;
        }
        setIsPreparing(false);
        setPreparingGaveUp(false);
        preparingStartedAtRef.current = null;

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

        // ── Guardas pós-sync ──────────────────────────────────────────────────
        // 1. Nunca baixar currentSales abaixo do piso confirmado por atualizarHoje.
        //    Cobre o caso de recompute com dado parcial do Magento retornando valor
        //    menor do que o sync acabou de confirmar.
        const _floor = postSyncFloorRef.current;
        const _guardedCurrentSales =
          _floor && Date.now() < _floor.until && typeof eventWithData.currentSales === 'number'
            ? Math.max(eventWithData.currentSales, _floor.value)
            : eventWithData.currentSales;

        // 2. Preservar dailySales existentes se o re-fetch retornar array vazio.
        //    Evita gráficos sumindo enquanto o backend ainda está recomputando.
        const _guardedDailySales =
          eventWithData.dailySales && eventWithData.dailySales.length > 0
            ? eventWithData.dailySales
            : (event?.dailySales && event.dailySales.length > 0
                ? event.dailySales
                : eventWithData.dailySales);

        hasEventDataRef.current = true;
        setIsFirstFetchDone(true);
        setEvent({
          ...eventWithData,
          currentSales: _guardedCurrentSales,
          dailySales: _guardedDailySales,
        });
        const cacheTime: string | undefined = (response as any).ultima_atualizacao;
        const systemRefresh: string | undefined = (response as any).ultima_atualizacao_completa;
        const inscricoesSync: string | undefined = (response as any).ultima_atualizacao_inscricoes;
        const snapshotAt: string | undefined = (response as any).snapshot_computed_at;
        // Display uses last full-system refresh time for consistency with the dashboard
        setUltimaAtualizacao(systemRefresh || cacheTime || null);
        setUltimaAtualizacaoInscricoes(inscricoesSync || cacheTime || null);
        setSnapshotComputedAt(snapshotAt || systemRefresh || cacheTime || null);
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
        if ((response as any).faixas_preco_site) {
          setFaixasPrecoSite((response as any).faixas_preco_site);
        }
        if ((response as any).cenarios_ciclismo) {
          setCenariosCiclismo((response as any).cenarios_ciclismo);
        } else {
          setCenariosCiclismo(null);
        }
        setAvisos((response as any).avisos || []);
        // Salva estado completo no cache de módulo para visitas futuras.
        // Na segunda visita, todos os estados (inclusive dailySales/gráficos)
        // são restaurados imediatamente sem depender da API.
        // Só salva se o response tem dailySales válido para evitar cachear dados incompletos.
        if (id && eventWithData.dailySales && eventWithData.dailySales.length > 0) {
          _eventDetailCache.set(_detailCacheKey, {
            event: eventWithData,
            comparacaoAnual: (response as any).comparacao_anual || null,
            cenariosCiclismo: (response as any).cenarios_ciclismo || null,
            faixasPrecoSite: (response as any).faixas_preco_site || null,
            avisos: (response as any).avisos || [],
            projetosVinculados: (response as any).projetos_vinculados || [],
            anosDisponiveis: (response as any).anos_disponiveis || [],
            cachedAt: Date.now(),
          });
        }
        setError(null);
        // Se o cache do evento é mais antigo que o último refresh completo do sistema,
        // dispara um re-fetch silencioso para atualizar os dados. O estado já foi
        // aplicado acima, então o usuário vê os dados atuais enquanto aguarda.
        if (
          !forceRefresh &&
          !silentRefetchDoneRef.current &&
          cacheTime &&
          systemRefresh &&
          new Date(cacheTime) < new Date(systemRefresh)
        ) {
          silentRefetchDoneRef.current = true;
          fetchEvent(true, true);
        }
      } catch (err: any) {
        if (err?.name === 'CanceledError' || err?.code === 'ERR_CANCELED') return;
        console.error('Erro ao carregar evento:', err);
        if (!event) setError('Erro ao carregar dados do evento');
      } finally {
        // Cancela timer pendente antes do delay disparar — evita o banner
        // piscar logo após a resposta chegar.
        if (detailsLoadingTimerRef.current) {
          clearTimeout(detailsLoadingTimerRef.current);
          detailsLoadingTimerRef.current = null;
        }
        // SEMPRE limpar os flags de loading, mesmo quando o request foi
        // abortado. Caso contrário, se o timer de 600ms tiver disparado e
        // ligado o banner azul ANTES do abort, o banner nunca era zerado
        // (a guarda anterior `if (!aborted)` pulava esse `setState`) e o
        // usuário ficava preso em "Atualizando dados do evento em tempo
        // real..." indefinidamente. O componente continua montado depois
        // do abort (o effect só re-roda), então o setState é seguro.
        setLoading(false);
        setDetailsLoading(false);
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
      if (detailsLoadingTimerRef.current) {
        clearTimeout(detailsLoadingTimerRef.current);
        detailsLoadingTimerRef.current = null;
      }
      // Garantia extra: ao re-rodar o effect ou desmontar, limpar o banner
      // azul para que ele nunca fique preso entre cycles.
      setDetailsLoading(false);
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
      // SWR: se já há dado no cache (estado inicializado), não mostra spinner —
      // busca em background e atualiza silenciosamente.
      const hasCurvaCached = curvaData.length > 0;
      if (!hasCurvaCached) setCurvaLoading(true);
      try {
        const response = await marketingService.getCurvaComparativaEvento(id, curvaController.signal, anoParam);
        if (!curvaController.signal.aborted) {
          const curvaPayload: _CurvaComparativaCache = {
            data: response.data,
            anoAtual: response.ano_atual,
            anoAnterior: response.ano_anterior,
            modo: response.modo || 'mensal',
            dataEventoAtual: response.data_evento_atual || null,
            dataEventoAnterior: response.data_evento_anterior || null,
            meta: (response as any).meta || null,
            cachedAt: Date.now(),
          };
          _curvaComparativaCache.set(_detailCacheKey, curvaPayload);
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
      // SWR: só mostra spinner quando não há dado anterior para o período atual.
      const hasSalesAvgCached = salesAverages !== null;
      if (!hasSalesAvgCached) setSalesAvgLoading(true);
      try {
        const data = await marketingService.getSalesAverages(id, salesAvgPeriod, controller.signal, anoParam);
        if (!controller.signal.aborted) {
          const avCacheKey = `${_detailCacheKey}_${salesAvgPeriod}`;
          _salesAvgCache.set(avCacheKey, { data, period: salesAvgPeriod, cachedAt: Date.now() });
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
          _curvaSnapshotModCache.set(_detailCacheKey, { data, cachedAt: Date.now() });
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
    setRefreshError(null);
    setSyncResult(null);
    setSyncErrorMsg(null);
    setSyncStartTime(Date.now());
    setSyncStatus('loading');
    setShowSyncModal(true);
    const _hadNoDailySales = !event?.dailySales || event.dailySales.length === 0;
    try {
      const result = await marketingService.atualizarHoje(id, anoParam);
      const partial = result.status === 'partial' || result.ativo_ok === false || result.magento_ok === false;
      const newStatus: SyncStatus = result.status === 'frozen'
        ? 'frozen'
        : partial
          ? 'partial'
          : result.status === 'failed'
            ? 'failed'
            : 'success';
      setSyncResult(result as SyncResult);
      setSyncStatus(newStatus);
      if (partial) {
        const fontes = (result.fontes_indisponiveis || []).join(' e ').toUpperCase() || 'a fonte';
        setRefreshError(
          `Dados parciais: ${fontes} indisponível no momento. Exibindo o que conseguimos sincronizar — atualize de novo em instantes para completar.`
        );
        setTimeout(() => setRefreshError(null), 8000);
      }
      {
        const todayStr = new Date().toLocaleDateString('sv-SE', { timeZone: 'America/Sao_Paulo' });
        setEvent(prev => {
          if (!prev) return prev;

          // Helper: given a dailySales array sorted by date, find the cumulative
          // sales of the day immediately before todayStr.
          const getPrevCumSales = (arr: typeof prev.dailySales): number => {
            if (!arr) return 0;
            const sorted = [...arr]
              .filter(d => d.date < todayStr)
              .sort((a, b) => a.date.localeCompare(b.date));
            const prev = sorted[sorted.length - 1];
            return prev?.cumulativeSales ?? 0;
          };

          const todayExists = prev.dailySales?.some(d => d.date === todayStr);

          // Case 1 — today's row already exists (snapshot had a stale/zero value).
          // Usa total_acumulado (soma real do banco) como cumulativeSales de hoje.
          // Evita duplicação que ocorreria se prevCum + hoje_total fosse calculado
          // com um prevCum incorreto. Fallback para prevCum + hoje_total caso
          // total_acumulado não esteja disponível (ex: evento frozen).
          const _trueCum = result.total_acumulado > 0
            ? result.total_acumulado
            : getPrevCumSales(prev.dailySales) + result.hoje_total;

          // Recalculate cumulativeSales, atingimentoDiario, atingimentoAcumulado and dif.
          const updatedDailySales = prev.dailySales ? prev.dailySales.map(d => {
            if (d.date === todayStr) {
              const expDay = d.expected ?? 0;
              const expCum = d.cumulativeExpected ?? 0;
              const newAtingDia = expDay > 0
                ? Math.round(((result.hoje_total - expDay) / expDay) * 1000) / 10
                : 0;
              const newDif = Math.round((_trueCum - expCum) * 10) / 10;
              const newAtingAcum = expCum > 0
                ? Math.round(((_trueCum - expCum) / expCum) * 1000) / 10
                : 0;
              return {
                ...d,
                sales: result.hoje_total,
                cumulativeSales: _trueCum,
                atingimentoDiario: newAtingDia,
                atingimentoAcumulado: newAtingAcum,
                dif: newDif,
              };
            }
            return d;
          }) : prev.dailySales;

          // Case 2 — today not yet in the array: add a new row with correct cumulative.
          const finalDailySales = (!todayExists && result.hoje_total > 0 && prev.dailySales)
            ? [...prev.dailySales, {
                date: todayStr,
                sales: result.hoje_total,
                expected: 0,
                cumulativeSales: _trueCum,
                cumulativeExpected: 0,
                atingimentoDiario: 0,
                atingimentoAcumulado: 0,
                dif: _trueCum,
              }]
            : updatedDailySales;
          return {
            ...prev,
            currentSales: (result.total_acumulado > 0 && result.total_acumulado >= (prev.currentSales || 0))
              ? result.total_acumulado
              : prev.currentSales,
            dailySales: finalDailySales
          };
        });
        if (result.ultima_atualizacao) {
          setUltimaAtualizacaoInscricoes(result.ultima_atualizacao);
        }
        setIsStaleData(false);
        setRefreshSuccess(true);
        setTimeout(() => setRefreshSuccess(false), 4000);
        // Grava piso de currentSales confirmado por este sync (válido por 2 min).
        // Re-fetches seguintes não podem baixar o valor abaixo desse piso.
        if (result.total_acumulado > 0) {
          postSyncFloorRef.current = { value: result.total_acumulado, until: Date.now() + 120000 };
        }
        if (staleRetryTimerRef.current) {
          clearTimeout(staleRetryTimerRef.current);
          staleRetryTimerRef.current = null;
        }
        // Delay o primeiro re-fetch para dar tempo ao recompute em background
        // (disparado pelo backend imediatamente após o sync) de concluir.
        // silent=true: evita banner de loading e preserva gráficos existentes
        // enquanto os dados novos chegam em background.
        staleRetryTimerRef.current = setTimeout(() => {
          staleRetryTimerRef.current = null;
          fetchEventRef.current?.(true, true, true);
          // Segunda rodada silenciosa após mais 12s (total ~16s) para pegar
          // qualquer dado que o recompute completo tenha atualizado.
          staleRetryTimerRef.current = setTimeout(() => {
            staleRetryTimerRef.current = null;
            fetchEventRef.current?.(true, true);
            // Terceira rodada: apenas quando o evento não tinha histórico antes do sync.
            // O backend dispara consolidar_vendas_grupo em background (pode levar 30-60s)
            // para popular o histórico completo no Controle Diário.
            if (_hadNoDailySales) {
              staleRetryTimerRef.current = setTimeout(() => {
                staleRetryTimerRef.current = null;
                fetchEventRef.current?.(true, true);
              }, 30000);
            }
          }, 12000);
        }, 4000);
      }
    } catch (err: any) {
      console.error('Erro ao atualizar vendas de hoje:', err);
      let errMsg = 'Não foi possível atualizar as vendas de hoje agora. Tente novamente em alguns instantes.';
      let errStatus: SyncStatus = 'error';
      if (err?.isBusy) {
        errMsg = err.message || 'Sincronização já em andamento. Os dados serão atualizados em instantes.';
        errStatus = 'busy';
      } else if (err?.isRateLimit) {
        const mins = Math.floor((err.retryAfter ?? 0) / 60);
        const secs = (err.retryAfter ?? 0) % 60;
        const quem = err.blockedBy ? ` por ${err.blockedBy}` : '';
        const tempo = mins > 0 ? `${mins}min ${secs}s` : `${secs}s`;
        errMsg = `Atualização já solicitada recentemente${quem}. Disponível novamente em ${tempo}.`;
        errStatus = 'cooldown';
      }
      setSyncErrorMsg(errMsg);
      setSyncStatus(errStatus);
      setRefreshError(errMsg);
      setTimeout(() => setRefreshError(null), 10000);
    } finally {
      setRefreshing(false);
    }
  };

  const [togglingCortesias, setTogglingCortesias] = useState(false);
  const handleToggleCortesias = async () => {
    if (!id || togglingCortesias) return;
    setTogglingCortesias(true);
    try {
      const result = await marketingService.toggleCortesias(id);
      setEvent(prev => prev ? { ...prev, incluirCortesias: result.incluirCortesias } : prev);
      clearMarketingDashboardCache();
      if (fetchEventRef.current) {
        fetchEventRef.current(true, true);
      }
    } catch (err) {
      console.error('Erro ao alternar cortesias:', err);
    } finally {
      setTogglingCortesias(false);
    }
  };

  const openOverrideModal = async () => {
    try {
      const res = await api.get('/admin/evento-grupos/available-curves');
      setAvailableCurves(res.data);
    } catch (err) {
      console.error('Erro ao buscar curvas disponíveis:', err);
    }
    setOverrideSearch('');
    setShowOverrideModal(true);
  };


  const handleSetOverride = async (curvaGrupo: string | null) => {
    if (!id) return;
    const grupoNome = curvaSnapshot?.evento_grupo || (isConsolidated ? id.replace(/^grp_/, '') : id);
    setSavingOverride(true);
    try {
      const gruposRes = await api.get('/admin/evento-grupos', { params: { busca: grupoNome } });
      const norm = (s: string) => (s || '').normalize('NFKC').trim().toLowerCase();
      const target = norm(grupoNome);
      const matchedGrupo =
        gruposRes.data.find((g: any) => g.nome === grupoNome) ||
        gruposRes.data.find((g: any) => norm(g.nome) === target);
      if (!matchedGrupo) {
        console.error('Grupo não encontrado:', grupoNome, 'opções:', gruposRes.data?.map((g: any) => g.nome));
        alert(`Não foi possível salvar: o grupo "${grupoNome}" não foi encontrado no cadastro.`);
        setSavingOverride(false);
        return;
      }
      await api.put(`/admin/evento-grupos/${matchedGrupo.id}/curva-override`, {
        curva_override: curvaGrupo
      });
      setShowOverrideModal(false);
      if (fetchEventRef.current) {
        await fetchEventRef.current(true);
      }
    } catch (err: any) {
      console.error('Erro ao salvar override:', err);
      alert(`Erro ao salvar curva de referência: ${err?.response?.data?.detail || err?.message || 'erro desconhecido'}`);
    } finally {
      setSavingOverride(false);
    }
  };

  const renderPreparingSkeleton = (giveUp: boolean) => (
    <div className="bg-white dark:bg-gray-800 rounded-xl p-8">
      <div className="flex flex-col items-center justify-center text-center mb-6">
        {giveUp ? (
          <>
            <AlertTriangle className="w-10 h-10 text-amber-500" />
            <p className="mt-4 text-gray-700 dark:text-gray-200 font-medium">
              Ainda não conseguimos preparar este evento.
            </p>
            <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
              Tente novamente em alguns minutos. Se persistir, avise o time de dados.
            </p>
            <button
              onClick={() => {
                setPreparingGaveUp(false);
                preparingStartedAtRef.current = null;
                if (fetchEventRef.current) fetchEventRef.current(false, true);
              }}
              className="mt-4 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 inline-flex items-center gap-2"
            >
              <RefreshCw className="w-4 h-4" />
              Tentar novamente
            </button>
          </>
        ) : (
          <>
            <Loader2 className="w-8 h-8 animate-spin text-blue-600" />
            <p className="mt-4 text-gray-700 dark:text-gray-200 font-medium">
              Estamos preparando este evento, pode levar 1-3 minutos
            </p>
            <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
              Você pode aguardar nesta tela — vamos atualizar automaticamente.
            </p>
          </>
        )}
      </div>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {[0, 1, 2].map(i => (
          <div key={i} className="h-24 rounded-lg bg-gray-100 dark:bg-gray-700 animate-pulse" />
        ))}
      </div>
      <div className="mt-4 h-48 rounded-lg bg-gray-100 dark:bg-gray-700 animate-pulse" />
    </div>
  );

  if (!event && (loading || error || isPreparing)) {
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
        ) : isPreparing ? (
          renderPreparingSkeleton(preparingGaveUp)
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
      return { ponto_corte: dMinus >= 65 ? 'D-65' : 'D-50', estagio: 'analitico' };
    } else if (dMinus >= 32) {
      return { ponto_corte: dMinus >= 45 ? 'D-45' : 'D-35', estagio: 'estrategico' };
    } else {
      return { ponto_corte: dMinus >= 15 ? 'D-30' : 'D-15', estagio: 'operacional' };
    }
  };

  const handleSaveAction = async () => {
    if (viewOnlyAction) return;
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

      if (editingActionId) {
        await marketingService.updateAcaoComercial(parseInt(editingActionId), {
          tipo: actionForm.tipo,
          descricao: actionForm.descricao,
          data_acao: actionForm.data_acao,
        });
        setEvent(prev => prev ? {
          ...prev,
          commercialActions: (prev.commercialActions ?? []).map(a =>
            a.id === editingActionId
              ? { ...a, tipo: actionForm.tipo, description: actionForm.descricao, date: actionForm.data_acao }
              : a
          )
        } : prev);
      } else {
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
          tipo: actionForm.tipo,
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
      }

      setShowActionModal(false);
      setActionError(null);
      setEditingActionId(null);
      setActionForm({
        tipo: '',
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
    { value: '', label: '' },
    { value: 'AUMENTO_PRECO', label: 'Aumento de Preço' },
    { value: 'REDUCAO_PRECO', label: 'Redução de Preço' },
    { value: 'PROMOCAO', label: 'Promoção/Desconto' },
    { value: 'CAMPANHA', label: 'Campanha de Marketing' },
    { value: 'COMUNICACAO', label: 'Comunicação/Email' },
    { value: 'NENHUMA_ACAO', label: 'Nenhuma Ação Tomada' },
    { value: 'OUTROS', label: 'Outros' },
  ];
  const tipoLabelMap: Record<string, string> = {
    AUMENTO_PRECO: 'Aumento de Preço',
    REDUCAO_PRECO: 'Redução de Preço',
    PROMOCAO: 'Promoção/Desconto',
    CAMPANHA: 'Campanha de Marketing',
    COMUNICACAO: 'Comunicação/Email',
    NENHUMA_ACAO: 'Nenhuma Ação Tomada',
    OUTROS: 'Outros',
  };

  const dailySalesNormExpected = normalizeExpectedOutliers(event.dailySales || []);

  const cumulativeData = dailySalesNormExpected.reduce((acc, day, index) => {
    const prevCumulative = index > 0 ? acc[index - 1].cumulative : 0;
    const prevExpected = index > 0 ? acc[index - 1].cumulativeExpected : 0;

    acc.push({
      date: day.date,
      cumulative: prevCumulative + day.sales,
      cumulativeExpected: day.cumulativeExpected != null ? day.cumulativeExpected : (prevExpected + day.expected),
      cumulativeExpectedNormalized: day.cumulativeNormalizedExpected,
      daily: day.sales,
      expectedDaily: day.expected,
      normalizedExpectedDaily: day.normalizedExpected,
    });

    return acc;
  }, [] as { date: string; cumulative: number; cumulativeExpected: number; cumulativeExpectedNormalized: number; daily: number; expectedDaily: number; normalizedExpectedDaily: number }[]);

  const filteredCumulativeData = chartPeriod
    ? cumulativeData.slice(-chartPeriod)
    : cumulativeData;

  const todayStr = new Date().toLocaleDateString('sv-SE', { timeZone: 'America/Sao_Paulo' });

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
      const realCumul = d.cumulative;
      const refExpected = showNormalized ? d.cumulativeExpectedNormalized : d.cumulativeExpected;
      const pct = parseFloat((((realCumul / refExpected) * 100) - 100).toFixed(1));
      return {
        date: d.date,
        dMinus: dMinusInsc,
        label: `D-${dMinusInsc}`,
        percentual: pct,
        cumulative: Math.round(realCumul),
        cumulativeExpected: Math.round(refExpected),
      };
    });

  const goalAttainmentDailyData = dailySalesNormExpected
    .filter(d => d.expected > 0)
    .map(d => {
      let dMinusInsc = 0;
      if (hasValidEventDate) {
        const dayDate = new Date(d.date + 'T12:00:00');
        const diffMs = parsedEventDate!.getTime() - dayDate.getTime();
        const dMinusEvento = Math.round(diffMs / (1000 * 60 * 60 * 24));
        dMinusInsc = Math.max(0, dMinusEvento - 2);
      }
      const realDay = d.sales;
      const refExpected = showNormalized ? d.normalizedExpected : d.expected;
      const pct = parseFloat((((realDay / refExpected) * 100) - 100).toFixed(1));
      return {
        date: d.date,
        dMinus: dMinusInsc,
        label: `D-${dMinusInsc}`,
        percentual: pct,
        sales: Math.round(realDay),
        expected: Math.round(refExpected),
      };
    });

  const activeAttainmentData = attainmentMode === 'acumulado' ? goalAttainmentData : goalAttainmentDailyData;
  const filteredAttainmentData = attainmentPeriod ? activeAttainmentData.slice(-attainmentPeriod) : activeAttainmentData;

  const dailySalesArr = event.dailySales || [];
  const todayDailySale = dailySalesArr.find(d => d.date === todayStr);
  const todayDailySaleNorm = dailySalesNormExpected.find(d => d.date === todayStr);
  const lastDailySale = dailySalesArr.length > 0 ? dailySalesArr[dailySalesArr.length - 1] : null;
  const hasTodayData = !!todayDailySale;
  const todaySales = todayDailySale?.sales ?? 0;
  const todayExpectedRaw = todayDailySale?.expected ?? 0;
  const todayExpectedNorm = todayDailySaleNorm?.normalizedExpected ?? todayExpectedRaw;
  const todayExpectedRounded = Math.round(showNormalized ? todayExpectedNorm : todayExpectedRaw);
  const todayPct = todayExpectedRounded > 0 ? Math.round((todaySales / todayExpectedRounded) * 100) : (todaySales > 0 ? 100 : 0);
  // Último ponto do cumulativo (pode incluir hoje) — usado para outros fins.
  const lastCumData = cumulativeData.length > 0
    ? cumulativeData[cumulativeData.length - 1]
    : null;
  const inscritosTotal = lastCumData ? Math.round(lastCumData.cumulative) : 0;
  // currentSales é a fonte única de verdade: backend garante que é sempre >= inscritosTotal
  const totalInscritosRaw = (event.currentSales != null && event.currentSales > 0) ? event.currentSales : inscritosTotal;

  type _SaleLike = { sales: number };
  // Inscritos são sempre o número real — nunca substituímos por normalizado.
  // A normalização agora se aplica somente à curva (meta).
  const _saleVal = (d: _SaleLike): number => d.sales;
  const inscritosTotalNorm = totalInscritosRaw;
  const displayedCurrentSales = totalInscritosRaw;
  const totalInscritos = displayedCurrentSales;
  const completeDailySales = (() => {
    const raw = (event.dailySales || []).filter(d => d.date < todayStr);
    // Dedup por data (mantém última ocorrência) e garante ordem cronológica ascendente.
    // Evita que entradas duplicadas de uma mesma data comprometam os slices de "últimos N dias".
    const map = new Map<string, typeof raw[0]>();
    for (const d of raw) map.set(d.date, d);
    return Array.from(map.values()).sort((a, b) => a.date.localeCompare(b.date));
  })();
  const last30Days = completeDailySales.slice(-30).map(d => ({ ...d, sales: _saleVal(d) }));
  // Total acumulado apenas de dias fechados (exclui o dia atual, que é parcial).
  // Usado nos cards que devem refletir somente inscrições consolidadas até ontem.
  const totalInscritosConsolidado = completeDailySales.reduce((sum, d) => sum + _saleVal(d), 0);

  // Card "Meta Acumulada vs Inscritos Total": usa somente dados até ontem (dias fechados).
  const lastCumDataOntem = cumulativeData.filter(d => d.date < todayStr).at(-1) ?? null;
  const metaAcumuladaRaw = lastCumDataOntem ? Math.round(lastCumDataOntem.cumulativeExpected) : 0;
  const metaAcumuladaNorm = lastCumDataOntem ? Math.round(lastCumDataOntem.cumulativeExpectedNormalized || lastCumDataOntem.cumulativeExpected) : 0;
  const metaAcumulada = showNormalized ? metaAcumuladaNorm : metaAcumuladaRaw;
  const inscritosOntem = totalInscritosConsolidado;
  const acumuladoGap = metaAcumulada > 0 ? Math.round(((inscritosOntem - metaAcumulada) / metaAcumulada) * 100) : (inscritosOntem > 0 ? 100 : 0);

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
  // Quando D-Inscrições chega a 0, usa D-Evento como fallback para evitar divisão por zero e campos zerados
  const dMinusEfetivo = dMinusCalc > 0 ? dMinusCalc : _safeDMinus;
  const mediaDiariaNecessaria = dMinusEfetivo > 0 ? Math.max(volumeParaMeta, 0) / dMinusEfetivo : 0;
  // Média 14d usada como ritmo base no Simulador. Sempre baseada nas vendas reais.
  // Prefere salesAverages (cache próprio, resiliente a falhas de Magento/snapshot) quando disponível.
  const _last14DaysSim = completeDailySales.slice(-14);
  const _avgMedia14 = (salesAverages?.medias as any[] | undefined)?.find((m: any) => m.periodo === 14)?.media;
  const dashMediaDiaria14 = _avgMedia14 != null
    ? _avgMedia14
    : (_last14DaysSim.length > 0
        ? _last14DaysSim.reduce((sum, d) => sum + _saleVal(d), 0) / _last14DaysSim.length
        : 0);
  const last7DaysSales = completeDailySales.slice(-7);
  const _avgMedia7 = (salesAverages?.medias as any[] | undefined)?.find((m: any) => m.periodo === 7)?.media;
  const mediaSemanaAtual = _avgMedia7 != null
    ? _avgMedia7
    : (last7DaysSales.length > 0
        ? last7DaysSales.reduce((sum, d) => sum + _saleVal(d), 0) / last7DaysSales.length
        : 0);
  const pctMedias = mediaDiariaNecessaria > 0
    ? ((mediaSemanaAtual / mediaDiariaNecessaria) * 100) - 100
    : (mediaSemanaAtual > 0 ? 100 : 0);

  const indicadoresVolume = (() => {
    const ticketAtualKit = event.ticketAtual && event.ticketAtual > 0 ? event.ticketAtual : 0;
    const custoKitBasico = event.kitCostPerUnit || 0;
    const margRealizada = margemRealizadaKits != null ? margemRealizadaKits : (event.margemRealizadaTotal || 0);
    const margOrcada = event.budgetTicket > 0 && custoKitBasico > 0 ? (event.budgetTicket - custoKitBasico) * event.salesGoal : 0;

    return [3, 7, 14, 30].map(dias => {
      const vendas = completeDailySales.slice(-dias);
      const totalVendas = vendas.reduce((sum, d) => sum + _saleVal(d), 0);
      const mediaLocal = vendas.length > 0 ? totalVendas / vendas.length : 0;
      // Para 7d, 14d e 30d prefere salesAverages (cache próprio, resiliente a falhas de conexão).
      // Para 3d não há período correspondente em salesAverages → usa cálculo local.
      const mediaFromAvg = dias !== 3
        ? (salesAverages?.medias as any[] | undefined)?.find((m: any) => m.periodo === dias)?.media
        : null;
      const media = mediaFromAvg != null ? mediaFromAvg : mediaLocal;
      const potencial = media * dMinusEfetivo;
      // Usa displayedCurrentSales (fonte primária) em vez de totalInscritosConsolidado,
      // que pode estar zerado quando o snapshot está desatualizado.
      const baseVendas = displayedCurrentSales > 0 ? displayedCurrentSales : totalInscritosConsolidado;
      const atingimento = baseVendas + potencial;
      const alvo = event.salesGoal > 0 ? (atingimento / event.salesGoal) - 1 : 0;
      const insightMargem = ticketAtualKit > 0 && custoKitBasico > 0 && event.budgetTicket > 0 && event.salesGoal > 0
        ? (margRealizada + (potencial * (ticketAtualKit - custoKitBasico))) - margOrcada
        : null;
      return {
        periodo: dias === 3 ? '3 dias' : dias === 7 ? '1 semana' : dias === 14 ? '14 dias' : '30 dias',
        media: Math.round(media * 10) / 10,
        dMinus: dMinusEfetivo,
        potencial: Math.round(potencial),
        vendasAcumuladas: baseVendas,
        atingimento: Math.round(atingimento),
        meta: event.salesGoal,
        alvo: Math.round(alvo * 1000) / 10,
        insightMargem,
      };
    });
  })();

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

  // Limiares por tipo:
  // - inscricoes: dado volátil (atualiza no sync_hoje a cada 30 min). Verde
  //   <=30min, amarelo <=2h, vermelho >2h.
  // - snapshot: dado pesado (atualiza no recompute completo). Verde <=24h,
  //   amarelo <=48h, vermelho >48h.
  const buildAgeInfo = (
    iso: string | null,
    prefix: string,
    kind: 'inscricoes' | 'snapshot',
  ) => {
    if (!iso) return null;
    const updatedAt = new Date(iso);
    if (isNaN(updatedAt.getTime())) return null;
    const now = new Date();
    const diffMs = now.getTime() - updatedAt.getTime();
    const diffMin = diffMs / (1000 * 60);
    const diffHours = diffMin / 60;
    const TZ = 'America/Sao_Paulo';
    const timeStr = updatedAt.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit', timeZone: TZ });
    const ymdInTz = (d: Date) => d.toLocaleDateString('en-CA', { timeZone: TZ });
    const updatedYmd = ymdInTz(updatedAt);
    const todayYmd = ymdInTz(now);
    const yesterdayYmd = ymdInTz(new Date(now.getTime() - 86400000));
    let labelTime: string;
    if (updatedYmd === todayYmd) labelTime = `hoje às ${timeStr}`;
    else if (updatedYmd === yesterdayYmd) labelTime = `ontem às ${timeStr}`;
    else labelTime = `${Math.floor(diffHours / 24)}d atrás (${timeStr})`;

    let greenMax: number;  // em horas
    let yellowMax: number;
    if (kind === 'inscricoes') {
      greenMax = 0.5;   // 30 min
      yellowMax = 2;    // 2h
    } else {
      greenMax = 24;
      yellowMax = 48;
    }
    let color: string;
    let isStale: boolean;
    if (diffHours <= greenMax) {
      color = 'text-green-600 dark:text-green-400';
      isStale = false;
    } else if (diffHours <= yellowMax) {
      color = 'text-yellow-600 dark:text-yellow-400';
      isStale = false;
    } else {
      color = 'text-red-600 dark:text-red-400';
      isStale = true;
    }
    return { label: `${prefix} ${labelTime}`, color, isStale };
  };

  const dataAgeInfo = buildAgeInfo(ultimaAtualizacaoInscricoes || ultimaAtualizacao, 'Inscrições', 'inscricoes');
  const detailAgeInfo = buildAgeInfo(snapshotComputedAt, 'Detalhe', 'snapshot');
  const showDataStaleWarning = dataAgeInfo?.isStale && !refreshing;

  return (
    <div className="min-h-screen">
      <AtualizarHojeModal
        open={showSyncModal}
        status={syncStatus}
        result={syncResult}
        errorMsg={syncErrorMsg}
        onClose={() => setShowSyncModal(false)}
        startTime={syncStartTime}
      />
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
              <div className="flex items-center gap-x-3 mt-0.5 text-xs">
                <span
                  className={`flex items-center gap-1 ${dataAgeInfo.color}`}
                  title="Quando os dados de inscrições (vendas, ticket, vendas de hoje) foram atualizados"
                >
                  <Clock className="w-3 h-3" />
                  <span>{dataAgeInfo.label}</span>
                </span>
              </div>
            )}
          </div>
        </div>
        <div className="flex items-center gap-3">
          {isAdmin && (
            <label
              className={`flex items-center gap-2 px-3 py-2 rounded-lg cursor-pointer select-none transition-colors ${
                event.incluirCortesias
                  ? 'bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-400'
                  : isDark ? 'bg-gray-700 text-gray-400' : 'bg-gray-100 text-gray-500'
              } ${togglingCortesias ? 'opacity-50 pointer-events-none' : ''}`}
              title="Incluir inscrições de cortesia em todas as métricas deste evento"
            >
              <span className="relative inline-flex h-5 w-9 items-center rounded-full transition-colors"
                style={{ backgroundColor: event.incluirCortesias ? '#10b981' : (isDark ? '#4b5563' : '#d1d5db') }}>
                <span className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform ${event.incluirCortesias ? 'translate-x-4' : 'translate-x-0.5'}`} />
              </span>
              <input
                type="checkbox"
                className="sr-only"
                checked={!!event.incluirCortesias}
                onChange={handleToggleCortesias}
                disabled={togglingCortesias}
              />
              <span className="text-sm font-medium whitespace-nowrap">
                {togglingCortesias ? 'Salvando...' : 'Incluir Cortesias'}
              </span>
            </label>
          )}
          {isAdmin && (
            <button
              onClick={() => { setConsolidarResult(null); setConsolidarError(null); setShowConsolidarModal(true); }}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg transition-colors ${isDark ? 'bg-indigo-900/30 text-indigo-400 hover:bg-indigo-900/50' : 'bg-indigo-100 text-indigo-600 hover:bg-indigo-200'}`}
              title="Reconstruir o histórico de vendas deste evento consultando Ativo e Magento (apenas admin)"
            >
              <DatabaseZap className="w-4 h-4" />
              <span className="text-sm font-medium whitespace-nowrap">Reconsolidar</span>
            </button>
          )}
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
      </div>

      {/* ── Modal Reconsolidar Evento (admin) ─────────────────────────────────── */}
      {showConsolidarModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={() => { if (!consolidarLoading) setShowConsolidarModal(false); }} />
          <div className={`relative w-full max-w-md rounded-2xl shadow-2xl border overflow-hidden ${isDark ? 'bg-gray-900 border-gray-700' : 'bg-white border-gray-200'}`}>

            {/* Header */}
            <div className={`flex items-center justify-between px-5 py-4 border-b ${isDark ? 'border-gray-700 bg-gray-800/60' : 'border-gray-200 bg-gray-50'}`}>
              <div className="flex items-center gap-2.5">
                <DatabaseZap className={`w-5 h-5 ${isDark ? 'text-indigo-400' : 'text-indigo-600'}`} />
                <div>
                  <h2 className={`text-sm font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>Reconsolidar Dados do Evento</h2>
                  <p className={`text-xs mt-0.5 truncate max-w-[260px] ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                    {isConsolidated ? id!.replace(/^grp_/, '') : id}
                  </p>
                </div>
              </div>
              <button
                onClick={() => { if (!consolidarLoading) setShowConsolidarModal(false); }}
                disabled={consolidarLoading}
                className={`p-1.5 rounded-lg transition-colors disabled:opacity-30 ${isDark ? 'hover:bg-gray-700 text-gray-400' : 'hover:bg-gray-200 text-gray-500'}`}
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Body */}
            <div className="px-5 py-5 space-y-4">
              {/* Resultado OK */}
              {consolidarResult && !consolidarError && (
                <div className={`rounded-xl border p-4 space-y-3 ${isDark ? 'bg-emerald-900/20 border-emerald-700/50' : 'bg-emerald-50 border-emerald-200'}`}>
                  <div className="flex items-center gap-2">
                    <CheckCheck className={`w-5 h-5 ${isDark ? 'text-emerald-400' : 'text-emerald-600'}`} />
                    <p className={`font-bold text-sm ${isDark ? 'text-emerald-300' : 'text-emerald-800'}`}>Consolidação concluída!</p>
                  </div>
                  <div className={`grid grid-cols-3 gap-3 text-xs ${isDark ? 'text-emerald-300' : 'text-emerald-800'}`}>
                    <div className="text-center">
                      <p className="opacity-70 mb-1">Antes</p>
                      <p className="text-2xl font-bold">{consolidarResult.qtd_antes ?? '—'}</p>
                    </div>
                    <div className="flex items-center justify-center">
                      <span className="text-lg opacity-50">→</span>
                    </div>
                    <div className="text-center">
                      <p className="opacity-70 mb-1">Depois</p>
                      <p className={`text-2xl font-bold ${(consolidarResult.qtd_depois ?? 0) > (consolidarResult.qtd_antes ?? 0) ? (isDark ? 'text-emerald-300' : 'text-emerald-700') : ''}`}>
                        {consolidarResult.qtd_depois ?? '—'}
                      </p>
                    </div>
                  </div>
                  <p className={`text-xs text-center opacity-60`}>
                    Duração: {consolidarResult.duracao_ms < 1000 ? `${consolidarResult.duracao_ms}ms` : `${(consolidarResult.duracao_ms / 1000).toFixed(1)}s`}
                  </p>
                  <div className={`flex items-center justify-center gap-1.5 text-xs ${isDark ? 'text-emerald-400/70' : 'text-emerald-700/70'}`}>
                    <RefreshCw className="w-3 h-3 animate-spin" />
                    <span>Dados sendo atualizados automaticamente…</span>
                  </div>
                  <button
                    onClick={() => setShowConsolidarModal(false)}
                    className={`w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl text-sm font-semibold transition-colors ${isDark ? 'bg-emerald-600 hover:bg-emerald-500 text-white' : 'bg-emerald-600 hover:bg-emerald-700 text-white'}`}
                  >
                    Fechar
                  </button>
                </div>
              )}

              {/* Erro */}
              {consolidarError && (
                <div className={`rounded-xl border p-4 ${isDark ? 'bg-red-900/20 border-red-700/50' : 'bg-red-50 border-red-200'}`}>
                  <p className={`text-sm font-semibold mb-1 ${isDark ? 'text-red-300' : 'text-red-700'}`}>Erro na consolidação</p>
                  <p className={`text-xs font-mono break-all ${isDark ? 'text-red-400' : 'text-red-600'}`}>{consolidarError}</p>
                  <button
                    onClick={() => setConsolidarError(null)}
                    className={`mt-3 text-xs underline ${isDark ? 'text-red-400' : 'text-red-600'}`}
                  >Tentar novamente</button>
                </div>
              )}

              {/* Configuração (só aparece antes de rodar) */}
              {!consolidarResult && !consolidarError && (
                <>
                  <p className={`text-sm ${isDark ? 'text-gray-300' : 'text-gray-600'}`}>
                    Reconstrói o histórico de vendas deste evento buscando dados diretamente do Ativo e do Magento.
                    Corrige snapshots desatualizados ou com dados incompletos.
                  </p>

                  <div className={`rounded-xl border p-3 space-y-2 ${isDark ? 'bg-gray-800/60 border-gray-700' : 'bg-gray-50 border-gray-200'}`}>
                    <p className={`text-xs font-semibold ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>Modo</p>
                    <label className={`flex items-start gap-2.5 p-2.5 rounded-lg cursor-pointer border transition-colors ${!consolidarIncremental ? (isDark ? 'border-indigo-500 bg-indigo-900/20' : 'border-indigo-400 bg-indigo-50') : (isDark ? 'border-gray-700' : 'border-transparent')}`}>
                      <input type="radio" name="modo_evento" checked={!consolidarIncremental} onChange={() => setConsolidarIncremental(false)} className="mt-0.5 accent-indigo-500" />
                      <div>
                        <p className={`text-xs font-semibold ${isDark ? 'text-white' : 'text-gray-900'}`}>Reconstrução completa <span className="ml-1 font-normal text-amber-600 dark:text-amber-400">(recomendado)</span></p>
                        <p className={`text-xs mt-0.5 ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Apaga e regrava todo o histórico do evento.</p>
                      </div>
                    </label>
                    <label className={`flex items-start gap-2.5 p-2.5 rounded-lg cursor-pointer border transition-colors ${consolidarIncremental ? (isDark ? 'border-indigo-500 bg-indigo-900/20' : 'border-indigo-400 bg-indigo-50') : (isDark ? 'border-gray-700' : 'border-transparent')}`}>
                      <input type="radio" name="modo_evento" checked={consolidarIncremental} onChange={() => setConsolidarIncremental(true)} className="mt-0.5 accent-indigo-500" />
                      <div>
                        <p className={`text-xs font-semibold ${isDark ? 'text-white' : 'text-gray-900'}`}>Incremental</p>
                        <p className={`text-xs mt-0.5 ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Busca apenas dias novos desde o último snapshot.</p>
                      </div>
                    </label>
                  </div>

                  <div className={`flex items-start gap-2 px-3 py-2.5 rounded-lg border text-xs ${isDark ? 'bg-amber-900/20 border-amber-700/50 text-amber-300' : 'bg-amber-50 border-amber-200 text-amber-800'}`}>
                    <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
                    <span>Pode levar de alguns segundos a 1-2 minutos dependendo do Magento. Os dados anteriores são preservados se a fonte retornar erro.</span>
                  </div>

                  <button
                    onClick={handleConsolidarEvento}
                    disabled={consolidarLoading}
                    className={`w-full flex items-center justify-center gap-2 px-4 py-3 rounded-xl font-semibold text-sm transition-colors disabled:opacity-60 ${isDark ? 'bg-indigo-600 hover:bg-indigo-500 text-white' : 'bg-indigo-600 hover:bg-indigo-700 text-white'}`}
                  >
                    {consolidarLoading
                      ? <><Loader2 className="w-4 h-4 animate-spin" /> Consolidando...</>
                      : <><DatabaseZap className="w-4 h-4" /> {consolidarIncremental ? 'Iniciar Incremental' : 'Iniciar Reconstrução'}</>
                    }
                  </button>

                  {consolidarLoading && (
                    <p className={`text-xs text-center ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                      Aguarde, consultando Ativo e Magento…
                    </p>
                  )}
                </>
              )}
            </div>
          </div>
        </div>
      )}

      {refreshSuccess && (
        <div className="bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-xl p-3 flex items-center gap-3">
          <span className="text-sm text-green-700 dark:text-green-300 font-medium">Vendas de hoje sincronizadas — recarregando todos os dados da página...</span>
        </div>
      )}

      {refreshError && (
        <div className="bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-xl p-3 flex items-center gap-3">
          <span className="text-sm text-amber-700 dark:text-amber-300 font-medium">{refreshError}</span>
        </div>
      )}

      <ConnectionAlert
        avisos={avisos}
        onRetry={handleForceRefresh}
        retrying={refreshing}
      />

      {((detailsLoading || (curvaLoading && curvaData.length === 0) || (salesAvgLoading && salesAverages === null)) && !refreshing) && (
        <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-xl p-3">
          <div className="flex items-center gap-2 mb-1.5">
            <Loader2 className="w-4 h-4 animate-spin text-blue-600 dark:text-blue-400 flex-shrink-0" />
            <span className="text-sm font-medium text-blue-700 dark:text-blue-300">Carregando dados do evento...</span>
          </div>
          <div className="flex flex-wrap gap-x-4 gap-y-1 pl-6">
            {detailsLoading && (
              <span className="text-xs text-blue-500 dark:text-blue-400 flex items-center gap-1.5">
                <span className="inline-block w-1.5 h-1.5 bg-blue-400 rounded-full animate-pulse" />
                {previewEvent ? 'Dados em tempo real' : 'Dados principais'}
              </span>
            )}
            {curvaLoading && curvaData.length === 0 && (
              <span className="text-xs text-blue-500 dark:text-blue-400 flex items-center gap-1.5">
                <span className="inline-block w-1.5 h-1.5 bg-blue-400 rounded-full animate-pulse" />
                Curva comparativa
              </span>
            )}
            {salesAvgLoading && salesAverages === null && (
              <span className="text-xs text-blue-500 dark:text-blue-400 flex items-center gap-1.5">
                <span className="inline-block w-1.5 h-1.5 bg-blue-400 rounded-full animate-pulse" />
                Médias de vendas
              </span>
            )}
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
          <div className="flex flex-col items-end gap-2">
            <div className="px-4 py-2 bg-gray-100 dark:bg-gray-700 rounded-lg">
              <span className="text-sm text-gray-500 dark:text-gray-400">Categoria</span>
              <p className="font-medium text-gray-900 dark:text-white">{event.category}</p>
            </div>
            <Link to="/marketing/playbook" className="text-xs font-medium text-indigo-600 dark:text-indigo-400 hover:underline whitespace-nowrap">
              Ver Playbook Completo →
            </Link>
          </div>
        </div>
      </div>

      <div className="flex flex-wrap items-end justify-between gap-2 border-b border-gray-200 dark:border-gray-700">
        <div className="flex gap-2">
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
        <div className="flex items-center gap-2 pb-2">
          <button
            onClick={() => setShowNormalized(!showNormalized)}
            className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md transition-colors border ${
              showNormalized
                ? 'bg-orange-500 text-white border-orange-500'
                : 'bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-300 border-gray-200 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-700'
            }`}
            title="Suaviza picos da curva de meta (vindos do histórico do ano anterior). Os inscritos reais deste ano nunca são alterados."
          >
            <Activity className="w-3.5 h-3.5" />
            {showNormalized ? 'Meta Normalizada: ON' : 'Normalizar Meta'}
          </button>
        </div>
      </div>
      {showNormalized && (
        <div className="bg-orange-50 dark:bg-orange-900/20 border border-orange-200 dark:border-orange-800 rounded-lg px-3 py-2 text-xs text-orange-800 dark:text-orange-300 flex items-center gap-2">
          <Activity className="w-3.5 h-3.5" />
          Modo meta normalizada ativo: picos da curva esperada (vindos do histórico) são suavizados (janela 7d, threshold 2,0×). Os inscritos reais deste ano permanecem inalterados.
        </div>
      )}

      {activeTab === 'simulator' ? (
        <Suspense fallback={<div className="flex items-center justify-center py-10"><Loader2 className="w-5 h-5 animate-spin text-blue-400" /></div>}>
          <EventSimulator
            eventoId={id!}
            ano={anoParam ?? new Date().getFullYear()}
            isDark={isDark}
            dashTicketMedio={ticketMedioRealizado > 0 ? ticketMedioRealizado : undefined}
            dashMargem={margemRealizadaKits != null ? margemRealizadaKits : (event?.margemRealizadaTotal ?? undefined)}
            dashTotalVendas={event?.currentSales && event.currentSales > 0 ? event.currentSales : undefined}
            dashTicketAtual={event?.ticketAtual && event.ticketAtual > 0 ? event.ticketAtual : undefined}
            dashMediaDiaria={undefined}
            normalizedBase={false}
          />
        </Suspense>
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
              <Suspense fallback={<div className="flex items-center justify-center py-10"><Loader2 className="w-5 h-5 animate-spin text-blue-400" /></div>}>
                <DailySalesTable
                  dailySales={dailySalesNormExpected}
                  isDark={isDark}
                  eventName={event.name}
                  salesGoal={event.salesGoal}
                  showNormalized={showNormalized}
                  onAtualizarHoje={handleOpenSyncModal}
                  isLoading={!isFirstFetchDone}
                />
              </Suspense>
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
                        const esperadoBruto = Math.round(Number(payload.find((p: any) => p.dataKey === 'cumulativeExpected')?.value ?? 0));
                        const esperadoNorm = showNormalized ? Math.round(Number(payload.find((p: any) => p.dataKey === 'cumulativeExpectedNormalized')?.value ?? 0)) : null;
                        const esperado = showNormalized && esperadoNorm !== null ? esperadoNorm : esperadoBruto;
                        const diff = real - esperado;
                        const diffColor = diff >= 0 ? '#22C55E' : '#EF4444';
                        return (
                          <div style={{ backgroundColor: '#1F2937', border: 'none', borderRadius: '8px', padding: '12px', color: '#fff' }}>
                            <p style={{ marginBottom: '8px', color: '#9CA3AF' }}>{new Date(label + 'T12:00:00').toLocaleDateString('pt-BR')}</p>
                            <p style={{ color: '#3B82F6' }}>Vendas Reais: {formatNumber(real)}</p>
                            {showNormalized && esperadoNorm !== null ? (
                              <>
                                <p style={{ color: '#F97316' }}>Meta Normalizada: {formatNumber(esperadoNorm)}</p>
                                <p style={{ color: '#9CA3AF', textDecoration: 'line-through', opacity: 0.7 }}>Meta Bruta: {formatNumber(esperadoBruto)}</p>
                              </>
                            ) : (
                              <p style={{ color: '#9CA3AF' }}>Esperado: {formatNumber(esperado)}</p>
                            )}
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
                      name={showNormalized ? "Meta Bruta" : "Esperado"}
                      stroke="#9CA3AF" 
                      strokeWidth={2}
                      strokeDasharray="5 5"
                      dot={false}
                      strokeOpacity={showNormalized ? 0.5 : 1}
                    />
                    {showNormalized && (
                      <Line 
                        type="monotone" 
                        dataKey="cumulativeExpectedNormalized" 
                        name="Meta Normalizada"
                        stroke="#F97316" 
                        strokeWidth={2}
                        strokeDasharray="8 4"
                        dot={false}
                      />
                    )}
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
                          <th className="text-right py-2 px-2 font-semibold text-gray-600 dark:text-gray-400">Meta Bruta</th>
                          <th className="text-right py-2 px-2 font-semibold text-gray-600 dark:text-gray-400">Mediana Local</th>
                          <th className="text-right py-2 px-2 font-semibold text-gray-600 dark:text-gray-400">Limite</th>
                          <th className="text-center py-2 px-2 font-semibold text-gray-600 dark:text-gray-400">Outlier?</th>
                          <th className="text-right py-2 px-2 font-semibold text-gray-600 dark:text-gray-400">Excesso Removido</th>
                          <th className="text-right py-2 px-2 font-semibold text-gray-600 dark:text-gray-400">Excesso Recebido</th>
                          <th className="text-right py-2 px-2 font-semibold text-gray-600 dark:text-gray-400">Meta Normalizada</th>
                          <th className="text-right py-2 px-2 font-semibold text-gray-600 dark:text-gray-400">Δ</th>
                        </tr>
                      </thead>
                      <tbody>
                        {dailySalesNormExpected.map((day, idx) => {
                          const delta = day.normalizedExpected - day.expected;
                          const deltaColor = delta > 0 ? 'text-green-600 dark:text-green-400' : delta < 0 ? 'text-red-600 dark:text-red-400' : 'text-gray-500 dark:text-gray-400';
                          return (
                            <tr
                              key={idx}
                              className={`border-b border-gray-100 dark:border-gray-700/50 ${day.expectedIsOutlier ? 'bg-red-50 dark:bg-red-900/20' : ''}`}
                            >
                              <td className="py-1.5 px-2 text-gray-800 dark:text-gray-200">
                                {new Date(day.date + 'T12:00:00').toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit', year: '2-digit' })}
                              </td>
                              <td className="py-1.5 px-2 text-right text-gray-800 dark:text-gray-200">{day.expected.toFixed(1)}</td>
                              <td className="py-1.5 px-2 text-right text-gray-600 dark:text-gray-400">{day.expectedLocalMedian ?? '—'}</td>
                              <td className="py-1.5 px-2 text-right text-gray-600 dark:text-gray-400">{day.expectedOutlierLimit ?? '—'}</td>
                              <td className="py-1.5 px-2 text-center">
                                {day.expectedIsOutlier ? (
                                  <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-semibold bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-400">
                                    OUTLIER
                                  </span>
                                ) : (
                                  <span className="text-gray-400 dark:text-gray-500">—</span>
                                )}
                              </td>
                              <td className="py-1.5 px-2 text-right text-red-600 dark:text-red-400">{day.expectedExcessRemoved > 0 ? `-${day.expectedExcessRemoved}` : '—'}</td>
                              <td className="py-1.5 px-2 text-right text-green-600 dark:text-green-400">{day.expectedExcessReceived > 0 ? `+${day.expectedExcessReceived}` : '—'}</td>
                              <td className="py-1.5 px-2 text-right font-medium text-gray-800 dark:text-gray-200">{day.normalizedExpected.toFixed(1)}</td>
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

            {curvaLoading && curvaData.length === 0 ? (
              /* Skeleton animado — primeira carga sem cache */
              <div className="h-64 flex flex-col justify-end gap-0 px-4 pb-8 animate-pulse">
                <div className="flex items-end gap-1 h-48">
                  {[35, 55, 40, 72, 48, 88, 62, 79, 45, 91, 58, 70, 50, 83, 42, 67].map((h, i) => (
                    <div
                      key={i}
                      className={`flex-1 rounded-t ${isDark ? 'bg-gray-700' : 'bg-gray-200'}`}
                      style={{ height: `${h}%` }}
                    />
                  ))}
                </div>
                <div className={`h-4 mt-2 rounded ${isDark ? 'bg-gray-700' : 'bg-gray-200'}`} />
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

          <Suspense fallback={<div className="flex items-center justify-center py-10"><Loader2 className="w-5 h-5 animate-spin text-blue-400" /></div>}>
            <EventInsights eventoId={id!} ano={anoParam} />
          </Suspense>
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
            {event.iscRaw != null && (
              <p className="text-xs text-gray-500 dark:text-gray-400 mt-1" title="ISC calculado sobre a curva bruta (sem normalização de outliers) para comparação">
                Bruto: <span className="font-semibold text-gray-700 dark:text-gray-300">{event.iscRaw.toFixed(2)}</span>
                {event.iscRaw !== event.isc && (
                  <span className={`ml-1 ${event.isc >= event.iscRaw ? 'text-orange-500' : 'text-blue-500'}`}>
                    ({event.isc >= event.iscRaw ? '+' : ''}{(event.isc - event.iscRaw).toFixed(2)})
                  </span>
                )}
              </p>
            )}
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
                {(((showNormalized ? event.iscComponentsNormalized : event.iscComponentsRaw) ?? event.iscComponents)?.ia730 ?? 0).toFixed(2)}
              </p>
              <div className="flex items-center gap-1 mt-1 text-xs">
                {(((showNormalized ? event.iscComponentsNormalized : event.iscComponentsRaw) ?? event.iscComponents)?.ia730 ?? 0) > 1 ? (
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
                {(((showNormalized ? event.iscComponentsNormalized : event.iscComponentsRaw) ?? event.iscComponents)?.curvaDPercent ?? 0).toFixed(2)}
              </p>
              <div className="flex items-center gap-1 mt-1 text-xs">
                {(((showNormalized ? event.iscComponentsNormalized : event.iscComponentsRaw) ?? event.iscComponents)?.curvaDPercent ?? 0) > 1 ? (
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
              <div className="mt-1.5 flex items-center gap-1">
                {(() => {
                  const tipo = event.iscComponents?.tipoCurva;
                  const fonte = event.iscComponents?.fonteCurva;
                  const anoRef = event.iscComponents?.anoReferencia;
                  const styles: Record<string, string> = {
                    historico: 'bg-blue-50 text-blue-600 dark:bg-blue-900/30 dark:text-blue-400 border-blue-200 dark:border-blue-700',
                    circuito: 'bg-purple-50 text-purple-600 dark:bg-purple-900/30 dark:text-purple-400 border-purple-200 dark:border-purple-700',
                    circuito_similar: 'bg-violet-50 text-violet-600 dark:bg-violet-900/30 dark:text-violet-400 border-violet-200 dark:border-violet-700',
                    regional: 'bg-gray-100 text-gray-600 dark:bg-gray-700/50 dark:text-gray-300 border-gray-300 dark:border-gray-600',
                    manual: 'bg-green-50 text-green-600 dark:bg-green-900/30 dark:text-green-400 border-green-200 dark:border-green-700',
                    linear: 'bg-amber-50 text-amber-600 dark:bg-amber-900/30 dark:text-amber-400 border-amber-200 dark:border-amber-700',
                  };
                  const labels: Record<string, string> = {
                    historico: `Histórico ${anoRef || curvaAnoAnterior}`,
                    circuito: `Circuito: ${fonte || ''}`,
                    circuito_similar: `Circuito (média): ${fonte || ''}`,
                    regional: `Regional: ${fonte || ''}`,
                    manual: `Manual: ${fonte || ''}`,
                    linear: 'Curva Linear',
                  };
                  const style = styles[tipo || 'linear'] || styles.linear;
                  const label = labels[tipo || 'linear'] || labels.linear;
                  return (
                    <button onClick={() => setShowCurveInfoModal(true)} className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium border cursor-pointer hover:opacity-80 transition-opacity ${style}`} title="Ver detalhes da curva de referência">
                      {label}
                      <Info className="w-2.5 h-2.5" />
                    </button>
                  );
                })()}
                <button onClick={openOverrideModal} className="p-0.5 rounded hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors" title="Alterar curva de referência">
                  <Pencil className="w-3 h-3 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300" />
                </button>
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
                {(((showNormalized ? event.iscComponentsNormalized : event.iscComponentsRaw) ?? event.iscComponents)?.rolling14d ?? 0).toFixed(2)}
              </p>
              <div className="flex items-center gap-1 mt-1 text-xs">
                {(((showNormalized ? event.iscComponentsNormalized : event.iscComponentsRaw) ?? event.iscComponents)?.rolling14d ?? 0) > 1 ? (
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

      <div className="bg-white dark:bg-gray-800 rounded-xl p-5 shadow-sm border border-gray-200 dark:border-gray-700">
        <div className={`flex items-center justify-between ${acoesColapsadas ? '' : 'mb-4'}`}>
          <button
            onClick={() => setAcoesColapsadas(v => !v)}
            className="flex items-center gap-2 group"
          >
            <h3 className="font-semibold text-gray-900 dark:text-white text-sm">Ações Estratégicas</h3>
            {acoesColapsadas
              ? <ChevronDown className="w-4 h-4 text-gray-400 group-hover:text-gray-600 dark:group-hover:text-gray-300 transition-colors" />
              : <ChevronUp className="w-4 h-4 text-gray-400 group-hover:text-gray-600 dark:group-hover:text-gray-300 transition-colors" />
            }
          </button>
          <span className="text-[10px] text-gray-400 dark:text-gray-500 font-mono">D-Insc atual: {event.dMinusInscricoes ?? event.dMinus ?? '—'}</span>
        </div>
        {!acoesColapsadas && (() => {
          const dInscricoes = event.dMinusInscricoes ?? event.dMinus ?? 999;
          const SLOTS = [
            { ponto_corte: 'D-65', estagio: 'analitico', cutoffValue: 65, nextCutoff: 50 },
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
              bg: 'bg-indigo-100 dark:bg-indigo-950/30',
              border: 'border-indigo-300 dark:border-indigo-800',
              badge: 'bg-indigo-200 dark:bg-indigo-900/60 text-indigo-800 dark:text-indigo-200',
              btn: 'bg-indigo-600 hover:bg-indigo-700 text-white',
            },
            estrategico: {
              label: 'Estratégico',
              text: 'text-amber-700 dark:text-amber-300',
              bg: 'bg-amber-100 dark:bg-amber-950/30',
              border: 'border-amber-300 dark:border-amber-800',
              badge: 'bg-amber-200 dark:bg-amber-900/60 text-amber-800 dark:text-amber-200',
              btn: 'bg-amber-500 hover:bg-amber-600 text-white',
            },
            operacional: {
              label: 'Operacional',
              text: 'text-rose-700 dark:text-rose-300',
              bg: 'bg-rose-100 dark:bg-rose-950/30',
              border: 'border-rose-300 dark:border-rose-800',
              badge: 'bg-rose-200 dark:bg-rose-900/60 text-rose-800 dark:text-rose-200',
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
                  const isFriday = (() => { const now = new Date(); return now.toLocaleDateString('en-US', { weekday: 'long', timeZone: 'America/Sao_Paulo' }).startsWith('Friday'); })();
                  const isWeekendAnticipated = isFriday && (dInscricoes - 1 === slot.cutoffValue || dInscricoes - 2 === slot.cutoffValue);
                  const isFuture = dInscricoes > slot.cutoffValue && !isWeekendAnticipated;
                  const isActive = dInscricoes === slot.cutoffValue || isWeekendAnticipated;
                  const isMissed = dInscricoes < slot.cutoffValue && !slotAction;
                  if (isFuture) {
                    return (
                      <div key={slot.ponto_corte} className="rounded-xl border border-gray-300 dark:border-gray-700 bg-gray-100 dark:bg-gray-800/40 p-3 flex flex-col gap-1">
                        <div className="flex items-center justify-between">
                          <span className="text-[10px] font-semibold text-gray-500 dark:text-gray-500 uppercase tracking-wide">{meta.label}</span>
                          <span className="text-[9px] text-gray-400 dark:text-gray-600">🔒</span>
                        </div>
                        <span className="text-lg font-black font-mono text-gray-500 dark:text-gray-600 leading-none">{slot.ponto_corte}</span>
                        <span className="text-[10px] text-gray-500 dark:text-gray-500">faltam {dInscricoes - slot.cutoffValue}d</span>
                      </div>
                    );
                  }
                  if (isMissed) {
                    return (
                      <div key={slot.ponto_corte} className="rounded-xl border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/40 p-3 flex flex-col gap-1">
                        <div className="flex items-center justify-between">
                          <span className="text-[10px] font-semibold text-gray-500 dark:text-gray-500 uppercase tracking-wide">{meta.label}</span>
                          <span className="text-[9px] text-gray-400 dark:text-gray-500">—</span>
                        </div>
                        <span className="text-lg font-black font-mono text-gray-500 dark:text-gray-600 leading-none">{slot.ponto_corte}</span>
                        <span className="text-[10px] text-gray-400 dark:text-gray-500">janela encerrada</span>
                      </div>
                    );
                  }
                  if (slotAction) {
                    const canEdit = slotAction.date === getTodayLocalDate();
                    return (
                      <div key={slot.ponto_corte} className={`rounded-xl border-2 ${meta.border} ${meta.bg} p-3 flex flex-col gap-1.5`}>
                        <div className="flex items-center justify-between">
                          <div className="flex flex-col gap-0">
                            <span className={`text-[10px] font-semibold uppercase tracking-wide ${meta.text}`}>{meta.label}</span>
                            {slotAction.tipo && tipoLabelMap[slotAction.tipo] && (
                              <span className="text-[9px] text-gray-500 dark:text-gray-400 font-normal leading-tight normal-case">{tipoLabelMap[slotAction.tipo]}</span>
                            )}
                          </div>
                          <div className="flex items-center gap-1">
                            {canEdit ? (
                              <button
                                onClick={() => {
                                  setEditingActionId(slotAction.id);
                                  setViewOnlyAction(false);
                                  setActionForm(f => ({
                                    ...f,
                                    tipo: slotAction.tipo ?? '',
                                    descricao: slotAction.description,
                                    data_acao: slotAction.date,
                                    forced_ponto_corte: slotAction.ponto_corte ?? '',
                                    forced_estagio: slotAction.estagio ?? '',
                                  }));
                                  setShowActionModal(true);
                                  setActionError(null);
                                }}
                                className="p-0.5 text-gray-300 hover:text-blue-400 transition-colors"
                                title="Editar"
                              >
                                <Pencil className="w-3 h-3" />
                              </button>
                            ) : (
                              <button
                                onClick={() => {
                                  setEditingActionId(slotAction.id);
                                  setViewOnlyAction(true);
                                  setActionForm(f => ({
                                    ...f,
                                    tipo: slotAction.tipo ?? '',
                                    descricao: slotAction.description,
                                    data_acao: slotAction.date,
                                    forced_ponto_corte: slotAction.ponto_corte ?? '',
                                    forced_estagio: slotAction.estagio ?? '',
                                  }));
                                  setShowActionModal(true);
                                  setActionError(null);
                                }}
                                className="p-0.5 text-gray-300 hover:text-blue-400 transition-colors"
                                title="Visualizar"
                              >
                                <Eye className="w-3 h-3" />
                              </button>
                            )}
                            {canEdit && (
                              <button onClick={() => handleDeleteAction(slotAction.id)} className="p-0.5 text-gray-300 hover:text-red-400 transition-colors" title="Excluir">
                                <Trash2 className="w-3 h-3" />
                              </button>
                            )}
                          </div>
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
                          setEditingActionId(null);
                          setViewOnlyAction(false);
                          setActionForm({
                            tipo: '',
                            descricao: '',
                            data_acao: getTodayLocalDate(),
                            projeto_id_selecionado: 0,
                            forced_ponto_corte: slot.ponto_corte,
                            forced_estagio: slot.estagio,
                          });
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

              {/* AÇÃO FINAL — liberada a partir de D-7 */}
              {(() => {
                const finalAction = (event.commercialActions ?? []).find(a => a.ponto_corte === 'D-7');
                const isFridayFinal = (() => { const now = new Date(); return now.toLocaleDateString('en-US', { weekday: 'long', timeZone: 'America/Sao_Paulo' }).startsWith('Friday'); })();
                const isWeekendAnticipatedFinal = isFridayFinal && (dInscricoes - 1 === 7 || dInscricoes - 2 === 7);
                const isLocked = dInscricoes > 7 && !isWeekendAnticipatedFinal;
                if (isLocked) {
                  return (
                    <div className="rounded-xl border border-gray-300 dark:border-gray-700 bg-gray-100 dark:bg-gray-800/40 p-4 flex items-center justify-between gap-3">
                      <div className="flex flex-col gap-0.5">
                        <span className="text-[10px] font-bold uppercase tracking-widest text-gray-400 dark:text-gray-500">Ação Final</span>
                        <span className="text-lg font-black font-mono text-gray-400 dark:text-gray-600 leading-none">D-7</span>
                        <span className="text-[10px] text-gray-400 dark:text-gray-500">disponível na semana do evento · faltam {dInscricoes - 7}d</span>
                      </div>
                      <span className="text-2xl select-none">🔒</span>
                    </div>
                  );
                }
                if (finalAction) {
                  const canEditFinal = finalAction.date === getTodayLocalDate();
                  return (
                    <div className="rounded-xl border-2 border-emerald-400 dark:border-emerald-700 bg-emerald-50 dark:bg-emerald-950/30 p-4 flex flex-col gap-2">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <div className="flex flex-col gap-0">
                            <span className="text-[10px] font-bold uppercase tracking-widest text-emerald-700 dark:text-emerald-300">Ação Final</span>
                            {finalAction.tipo && tipoLabelMap[finalAction.tipo] && (
                              <span className="text-[9px] text-gray-500 dark:text-gray-400 font-normal leading-tight normal-case">{tipoLabelMap[finalAction.tipo]}</span>
                            )}
                          </div>
                          {finalAction.snapshot_isc != null && (
                            <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-emerald-200 dark:bg-emerald-900/60 text-emerald-800 dark:text-emerald-200">ISC {finalAction.snapshot_isc.toFixed(2)}</span>
                          )}
                        </div>
                        <div className="flex items-center gap-2">
                          <span className="text-[11px] font-black font-mono text-emerald-700 dark:text-emerald-300">D-7</span>
                          {canEditFinal ? (
                            <button
                              onClick={() => {
                                setEditingActionId(finalAction.id);
                                setViewOnlyAction(false);
                                setActionForm(f => ({
                                  ...f,
                                  tipo: finalAction.tipo ?? '',
                                  descricao: finalAction.description,
                                  data_acao: finalAction.date,
                                  forced_ponto_corte: finalAction.ponto_corte ?? 'D-7',
                                  forced_estagio: finalAction.estagio ?? 'operacional',
                                }));
                                setShowActionModal(true);
                                setActionError(null);
                              }}
                              className="p-0.5 text-gray-300 hover:text-blue-400 transition-colors"
                              title="Editar"
                            >
                              <Pencil className="w-3 h-3" />
                            </button>
                          ) : (
                            <button
                              onClick={() => {
                                setEditingActionId(finalAction.id);
                                setViewOnlyAction(true);
                                setActionForm(f => ({
                                  ...f,
                                  tipo: finalAction.tipo ?? '',
                                  descricao: finalAction.description,
                                  data_acao: finalAction.date,
                                  forced_ponto_corte: finalAction.ponto_corte ?? 'D-7',
                                  forced_estagio: finalAction.estagio ?? 'operacional',
                                }));
                                setShowActionModal(true);
                                setActionError(null);
                              }}
                              className="p-0.5 text-gray-300 hover:text-blue-400 transition-colors"
                              title="Visualizar"
                            >
                              <Eye className="w-3 h-3" />
                            </button>
                          )}
                          {canEditFinal && (
                            <button onClick={() => handleDeleteAction(finalAction.id)} className="p-0.5 text-gray-300 hover:text-red-400 transition-colors" title="Excluir">
                              <Trash2 className="w-3 h-3" />
                            </button>
                          )}
                        </div>
                      </div>
                      <p className="text-[11px] text-gray-700 dark:text-gray-300 leading-snug">{finalAction.description}</p>
                      <div className="flex flex-wrap gap-1">
                        {finalAction.snapshot_d_minus != null && (
                          <span className="inline-flex items-center px-1.5 py-0.5 rounded bg-white/70 dark:bg-gray-700/70 border border-gray-200 dark:border-gray-600 text-[10px] text-gray-600 dark:text-gray-300">D-<span className="font-bold ml-0.5">{finalAction.snapshot_d_minus}</span></span>
                        )}
                        {finalAction.snapshot_ia730 != null && (
                          <span className="inline-flex items-center px-1.5 py-0.5 rounded bg-white/70 dark:bg-gray-700/70 border border-gray-200 dark:border-gray-600 text-[10px] text-gray-600 dark:text-gray-300">IA730 <span className="font-bold ml-0.5">{finalAction.snapshot_ia730.toFixed(2)}</span></span>
                        )}
                        {finalAction.snapshot_rolling14d != null && (
                          <span className="inline-flex items-center px-1.5 py-0.5 rounded bg-white/70 dark:bg-gray-700/70 border border-gray-200 dark:border-gray-600 text-[10px] text-gray-600 dark:text-gray-300">14d <span className="font-bold ml-0.5">{finalAction.snapshot_rolling14d.toFixed(2)}</span></span>
                        )}
                        {finalAction.snapshot_curva_percent != null && (
                          <span className="inline-flex items-center px-1.5 py-0.5 rounded bg-white/70 dark:bg-gray-700/70 border border-gray-200 dark:border-gray-600 text-[10px] text-gray-600 dark:text-gray-300">Curva <span className="font-bold ml-0.5">{(finalAction.snapshot_curva_percent * 100).toFixed(0)}%</span></span>
                        )}
                        {finalAction.snapshot_vendas_acumuladas != null && (
                          <span className="inline-flex items-center px-1.5 py-0.5 rounded bg-white/70 dark:bg-gray-700/70 border border-gray-200 dark:border-gray-600 text-[10px] text-gray-600 dark:text-gray-300">Vnd <span className="font-bold ml-0.5">{finalAction.snapshot_vendas_acumuladas.toLocaleString('pt-BR')}</span></span>
                        )}
                        {finalAction.snapshot_playbook_letter && (
                          <span className="inline-flex items-center px-1.5 py-0.5 rounded bg-blue-100 dark:bg-blue-900/40 border border-blue-200 dark:border-blue-700 text-[10px] font-bold text-blue-700 dark:text-blue-300">{finalAction.snapshot_playbook_letter}</span>
                        )}
                      </div>
                      <span className="text-[10px] text-gray-400 dark:text-gray-500">{new Date(finalAction.date + 'T00:00:00').toLocaleDateString('pt-BR')}</span>
                    </div>
                  );
                }
                return (
                  <div className="rounded-xl border-2 border-dashed border-emerald-400 dark:border-emerald-700 p-4 flex items-center justify-between gap-3">
                    <div className="flex flex-col gap-0.5">
                      <span className="text-[10px] font-bold uppercase tracking-widest text-emerald-700 dark:text-emerald-300">Ação Final</span>
                      <span className="text-lg font-black font-mono text-emerald-700 dark:text-emerald-300 leading-none">D-7</span>
                      <span className="text-[10px] text-emerald-600 dark:text-emerald-400">semana do evento — registre a ação final</span>
                    </div>
                    <button
                      onClick={() => {
                        setEditingActionId(null);
                        setViewOnlyAction(false);
                        setActionForm({
                          tipo: '',
                          descricao: '',
                          data_acao: getTodayLocalDate(),
                          projeto_id_selecionado: 0,
                          forced_ponto_corte: 'D-7',
                          forced_estagio: 'final',
                        });
                        setShowActionModal(true);
                        setActionError(null);
                      }}
                      className="flex items-center gap-1.5 px-3 py-2 text-[11px] font-semibold rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white transition-colors"
                    >
                      <Plus className="w-3 h-3" />
                      Registrar
                    </button>
                  </div>
                );
              })()}

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
                    <p className="text-lg font-bold text-blue-600 dark:text-blue-400">{formatNumber(inscritosOntem)}</p>
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
            {event.salesGoal > 0 ? (
              <>
                <p className="text-lg font-bold text-gray-900 dark:text-white mt-2">
                  {formatNumber(displayedCurrentSales)} / {formatNumber(event.salesGoal)}
                </p>
                <div className="mt-3 w-full bg-gray-200 dark:bg-gray-600 rounded-full h-2">
                  <div 
                    className="bg-blue-600 h-2 rounded-full transition-all"
                    style={{ width: `${Math.min((displayedCurrentSales / event.salesGoal) * 100, 100)}%` }}
                  />
                </div>
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-2">
                  {Math.round((displayedCurrentSales / event.salesGoal) * 100)}% da meta
                </p>
              </>
            ) : (
              <>
                <p className="text-lg font-bold text-gray-900 dark:text-white mt-2">
                  {formatNumber(displayedCurrentSales)}
                </p>
                <p className="text-xs text-amber-500 dark:text-amber-400 mt-2">
                  Meta não configurada
                </p>
              </>
            )}
          </div>
        )}
      </div>

      <div className="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm border border-gray-200 dark:border-gray-700">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-4">
          <div className="flex items-center gap-2 flex-wrap">
            <h3 className="font-semibold text-gray-900 dark:text-white">
              Atingimento da Meta por D- ({attainmentMode === 'acumulado' ? 'Acumulado' : 'Diário'})
            </h3>
            {(() => {
              const tipo = event.iscComponents?.tipoCurva;
              const fonte = event.iscComponents?.fonteCurva;
              const anoRef = event.iscComponents?.anoReferencia;
              const styles: Record<string, string> = {
                historico: 'bg-blue-50 text-blue-600 dark:bg-blue-900/30 dark:text-blue-400 border-blue-200 dark:border-blue-700',
                circuito: 'bg-purple-50 text-purple-600 dark:bg-purple-900/30 dark:text-purple-400 border-purple-200 dark:border-purple-700',
                circuito_similar: 'bg-violet-50 text-violet-600 dark:bg-violet-900/30 dark:text-violet-400 border-violet-200 dark:border-violet-700',
                regional: 'bg-gray-100 text-gray-600 dark:bg-gray-700/50 dark:text-gray-300 border-gray-300 dark:border-gray-600',
                manual: 'bg-green-50 text-green-600 dark:bg-green-900/30 dark:text-green-400 border-green-200 dark:border-green-700',
                linear: 'bg-amber-50 text-amber-600 dark:bg-amber-900/30 dark:text-amber-400 border-amber-200 dark:border-amber-700',
              };
              const labels: Record<string, string> = {
                historico: `Histórico ${anoRef || curvaAnoAnterior}`,
                circuito: `Circuito: ${fonte || ''}`,
                circuito_similar: `Circuito (média): ${fonte || ''}`,
                regional: `Regional: ${fonte || ''}`,
                manual: `Manual: ${fonte || ''}`,
                linear: 'Curva Linear',
              };
              const style = styles[tipo || 'linear'] || styles.linear;
              const label = labels[tipo || 'linear'] || labels.linear;
              return (
                <>
                  <button onClick={() => setShowCurveInfoModal(true)} className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium border cursor-pointer hover:opacity-80 transition-opacity ${style}`} title="Ver detalhes da curva de referência">
                    {label}
                    <Info className="w-2.5 h-2.5" />
                  </button>
                  <button onClick={openOverrideModal} className="p-0.5 rounded hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors" title="Alterar curva de referência">
                    <Pencil className="w-3 h-3 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300" />
                  </button>
                </>
              );
            })()}
          </div>
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
          <p className="text-sm text-gray-500 dark:text-gray-400">Vendas Totais{event.salesGoal > 0 ? ' / Meta Global' : ''}</p>
          <p className="text-2xl font-bold text-gray-900 dark:text-white">
            {formatNumber(displayedCurrentSales)}{event.salesGoal > 0 ? ` / ${formatNumber(event.salesGoal)}` : ''}
          </p>
          {event.salesGoal <= 0 && (
            <p className="text-xs text-amber-500 dark:text-amber-400">Meta não configurada</p>
          )}
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
                <th className="text-right py-2 px-3 text-xs font-semibold text-gray-500 dark:text-gray-400">Margem Potencial</th>
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
                  <td className={`py-2.5 px-3 text-right font-bold ${row.insightMargem == null ? 'text-gray-400 dark:text-gray-500' : row.insightMargem >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}>
                    {row.insightMargem != null ? (row.insightMargem >= 0 ? '+' : '') + formatCurrency(row.insightMargem) : '—'}
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
            const ticketRef = event.ticketAtual && event.ticketAtual > 0 ? event.ticketAtual : 0;
            return (
          <div className="space-y-3">
            <div className="flex items-center justify-between p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
              <span className="text-xs text-gray-500 dark:text-gray-400">Ticket Atual (Kit)</span>
              <span className={`text-lg font-bold ${ticketRef > 0 ? 'text-gray-900 dark:text-white' : 'text-amber-500 dark:text-amber-400'}`}>
                {ticketRef > 0 ? formatCurrency(ticketRef) : 'Não encontrado'}
              </span>
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
            {event.margemAvisos && event.margemAvisos.length > 0 && (() => {
              const hasOnlyInfo = event.margemAvisos!.every(a => a.startsWith('INFO:'));
              const hasAviso = event.margemAvisos!.some(a => a.startsWith('AVISO:'));
              if (hasOnlyInfo) return (
                <span className="ml-1 flex items-center gap-1 text-xs font-semibold text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-900/30 border border-blue-200 dark:border-blue-700 rounded-full px-2 py-0.5">
                  <Info className="w-3 h-3 shrink-0" />
                  Snapshot
                </span>
              );
              if (hasAviso) return (
                <span className="ml-1 flex items-center gap-1 text-xs font-semibold text-amber-600 dark:text-amber-400 bg-amber-50 dark:bg-amber-900/30 border border-amber-200 dark:border-amber-700 rounded-full px-2 py-0.5">
                  <AlertTriangle className="w-3 h-3 shrink-0" />
                  Sincronizando
                </span>
              );
              return (
                <span className="ml-1 flex items-center gap-1 text-xs font-semibold text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-700 rounded-full px-2 py-0.5">
                  <AlertTriangle className="w-3 h-3 shrink-0" />
                  Dados incompletos
                </span>
              );
            })()}
            <button
              onClick={() => setShowMargemInfo(true)}
              className="ml-auto p-1 rounded-full hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
              title="Ver composição da margem"
            >
              <Info className="w-4 h-4 text-gray-400 hover:text-blue-500 dark:hover:text-blue-400" />
            </button>
          </h3>
          {event.margemAvisos && event.margemAvisos.length > 0 && (
            <div className="mb-3 flex flex-col gap-1.5">
              {event.margemAvisos.map((aviso, i) => {
                const isInfo = aviso.startsWith('INFO:');
                const isAviso = aviso.startsWith('AVISO:');
                const textoLimpo = aviso.replace(/^(INFO|AVISO):\s*/, '');
                if (isInfo) return (
                  <div key={i} className="flex items-start gap-2 p-2.5 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-700 rounded-lg text-xs text-blue-700 dark:text-blue-300">
                    <Info className="w-3.5 h-3.5 mt-0.5 shrink-0 text-blue-500" />
                    <span className="flex-1">{textoLimpo}</span>
                  </div>
                );
                if (isAviso) return (
                  <div key={i} className="flex items-start gap-2 p-2.5 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-700 rounded-lg text-xs text-amber-700 dark:text-amber-300">
                    <AlertTriangle className="w-3.5 h-3.5 mt-0.5 shrink-0 text-amber-500" />
                    <span className="flex-1">{textoLimpo}</span>
                  </div>
                );
                return (
                  <div key={i} className="flex items-start gap-2 p-2.5 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-700 rounded-lg text-xs text-red-700 dark:text-red-300">
                    <AlertTriangle className="w-3.5 h-3.5 mt-0.5 shrink-0 text-red-500" />
                    <span className="flex-1">{textoLimpo}</span>
                  </div>
                );
              })}
              {event.margemAvisos.some(a => !a.startsWith('INFO:')) && (
                <button
                  onClick={() => fetchEventRef.current?.(true)}
                  disabled={loading || detailsLoading}
                  className="flex items-center justify-center gap-1.5 w-full py-1.5 text-xs font-medium text-gray-600 dark:text-gray-400 border border-gray-200 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  <RefreshCw className={`w-3 h-3 ${(loading || detailsLoading) ? 'animate-spin' : ''}`} />
                  Atualizar dados
                </button>
              )}
            </div>
          )}
          {(() => {
            const kitCost = event.kitCostPerUnit || 0;
            const ticketRef = event.ticketAtual && event.ticketAtual > 0 ? event.ticketAtual : 0;
            const margemOrcadaTotal = event.budgetTicket > 0 && kitCost > 0 ? (event.budgetTicket - kitCost) * event.salesGoal : 0;
            const margemRealizadaTotal = margemRealizadaKits != null
              ? margemRealizadaKits
              : (ticketRef > 0 && displayedCurrentSales > 0 ? Math.round((ticketRef - kitCost) * displayedCurrentSales * 100) / 100 : 0);
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
                          <span className={`font-medium ${event.salesGoal > 0 ? 'text-gray-900 dark:text-white' : 'text-amber-500 dark:text-amber-400 text-xs'}`}>
                            {event.salesGoal > 0 ? formatNumber(event.salesGoal) : 'Não configurada'}
                          </span>
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
                            <span className="font-medium text-red-600 dark:text-red-400">- {event.salesGoal > 0 ? formatCurrency((event.kitCostPerUnit || 0) * event.salesGoal) : '—'}</span>
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
                    {event.consistencyWarning && (
                      <div className="mb-3 flex items-start gap-2 rounded-md border border-amber-300 bg-amber-50 px-3 py-2 dark:border-amber-700 dark:bg-amber-900/30">
                        <span className="text-amber-500 mt-0.5 flex-shrink-0">⚠</span>
                        <div className="text-xs text-amber-800 dark:text-amber-200">
                          <p className="font-semibold mb-0.5">
                            Divergência detectada entre o total de inscrições e a tabela de Margem por Tipo de Kit.
                          </p>
                          <p>
                            Card ISC: <strong>{event.consistencyWarning.totalIsc.toLocaleString('pt-BR')}</strong>
                            {' · '}
                            Soma dos kits: <strong>{event.consistencyWarning.totalMargem.toLocaleString('pt-BR')}</strong>
                            {' · '}
                            Diferença: <strong>{event.consistencyWarning.diff > 0 ? '+' : ''}{event.consistencyWarning.diff.toLocaleString('pt-BR')}</strong>
                            {' ('}{event.consistencyWarning.diffPct.toFixed(1)}%)
                          </p>
                          <p className="mt-1 opacity-80">
                            Possíveis causas: bundles ativos fora do cadastro de kits, mapeamento de "Tipo Kit" ausente ou conflitante, ou vendas do dia ainda não consolidadas no snapshot.
                          </p>
                        </div>
                      </div>
                    )}
                    <div className="flex items-center justify-between mb-1 gap-2">
                      <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 flex items-center gap-2">
                        <div className="w-2 h-2 rounded-full bg-purple-500" />
                        Margem por Tipo de Kit
                      </h3>
                      <button
                        type="button"
                        disabled={magentoRefreshing}
                        onClick={async () => {
                          if (!fetchEventRef.current) return;
                          setMagentoRefreshing(true);
                          try {
                            // Primeira chamada: dispara o recompute (pode voltar stale + bg refresh).
                            await Promise.resolve(fetchEventRef.current(true, false, true));
                            // Como o backend usa SWR (snapshot + recompute em background),
                            // fazemos retries silenciosos até a resposta voltar fresca ou
                            // atingir o limite. Cada retry espera o bg job terminar.
                            for (let i = 0; i < 4; i++) {
                              await new Promise(r => setTimeout(r, 4000));
                              if (!fetchEventRef.current) break;
                              await Promise.resolve(fetchEventRef.current(false, true, false));
                              // Lê o estado mais recente para decidir se ainda está stale.
                              // Se _isStale virou false (resposta direta do recompute), paramos.
                              // Nota: o componente é remontado a cada fetch, então usamos um
                              // pequeno delay e confiamos no limite máximo de retries.
                            }
                          } finally {
                            setMagentoRefreshing(false);
                          }
                        }}
                        title="Ignora o snapshot e consulta o Magento agora (útil em eventos finalizados onde o snapshot é a fonte padrão)."
                        className="text-[11px] px-2 py-1 rounded border border-purple-300 text-purple-700 hover:bg-purple-50 dark:border-purple-700 dark:text-purple-300 dark:hover:bg-purple-900/30 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                      >
                        {magentoRefreshing ? 'Atualizando…' : '⟳ Atualizar do Magento'}
                      </button>
                    </div>
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

      {cenariosCiclismo && event.category?.toLowerCase() === 'ciclismo' && (
        <div className="bg-white dark:bg-gray-800 rounded-xl p-5 shadow-sm border border-gray-200 dark:border-gray-700">
          <h3 className="text-sm font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
            <Activity className="w-4 h-4 text-purple-500" />
            Cenários de Ciclismo
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {[
              { key: 'participacao', label: 'Inscrição Participação', cardClass: 'bg-blue-50 dark:bg-blue-900/10 border-blue-200 dark:border-blue-800', desc: 'Ticket zero' },
              { key: 'sem_bike', label: 'Kit sem Bike', cardClass: 'bg-green-50 dark:bg-green-900/10 border-green-200 dark:border-green-800', desc: 'Ticket menor' },
              { key: 'com_bike', label: 'Kit com Bike', cardClass: 'bg-amber-50 dark:bg-amber-900/10 border-amber-200 dark:border-amber-800', desc: 'Ticket maior' },
            ].map(({ key, label, cardClass, desc }) => {
              const c = cenariosCiclismo[key];
              if (!c) return null;
              const atingimento = c.orcado_pago > 0 && (c.real_vendas || 0) > 0
                ? Math.round(((c.real_vendas || 0) / c.orcado_pago) * 100)
                : 0;
              return (
                <div key={key} className={`rounded-xl border p-4 ${cardClass}`}>
                  <div className="flex items-center justify-between mb-3">
                    <div>
                      <p className="text-xs font-semibold text-gray-700 dark:text-gray-300">{label}</p>
                      <p className="text-[10px] text-gray-400 dark:text-gray-500">{desc}</p>
                    </div>
                    {c.orcado_pago > 0 && (
                      <span className={`text-xs font-bold px-2 py-0.5 rounded-full ${atingimento >= 100 ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400' : atingimento >= 50 ? 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400' : 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400'}`}>
                        {atingimento}%
                      </span>
                    )}
                  </div>
                  <div className="space-y-2">
                    <div className="flex justify-between items-center">
                      <span className="text-xs text-gray-500 dark:text-gray-400">Vendas</span>
                      <span className="text-sm font-bold text-gray-900 dark:text-white">
                        {(c.real_vendas || 0).toLocaleString('pt-BR')} / {c.orcado_pago.toLocaleString('pt-BR')}
                      </span>
                    </div>
                    {c.orcado_pago > 0 && (
                      <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-1.5">
                        <div
                          className={`h-1.5 rounded-full ${atingimento >= 100 ? 'bg-green-500' : atingimento >= 50 ? 'bg-yellow-500' : 'bg-red-500'}`}
                          style={{ width: `${Math.min(atingimento, 100)}%` }}
                        />
                      </div>
                    )}
                    <div className="flex justify-between items-center">
                      <span className="text-xs text-gray-500 dark:text-gray-400">Tkt Orçado</span>
                      <span className="text-sm font-medium text-gray-600 dark:text-gray-300">
                        {c.tkt_medio_orcado > 0 ? c.tkt_medio_orcado.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' }) : '—'}
                      </span>
                    </div>
                    <div className="flex justify-between items-center">
                      <span className="text-xs text-gray-500 dark:text-gray-400">Tkt Realizado</span>
                      <span className="text-sm font-medium text-gray-900 dark:text-white">
                        {(c.real_tkt_medio || 0) > 0 ? (c.real_tkt_medio || 0).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' }) : '—'}
                      </span>
                    </div>
                    <div className="flex justify-between items-center">
                      <span className="text-xs text-gray-500 dark:text-gray-400">Receita</span>
                      <span className="text-sm font-semibold text-gray-900 dark:text-white">
                        {(c.real_receita || 0).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })}
                      </span>
                    </div>
                    {(c.custo_kit || 0) > 0 && (
                      <div className="flex justify-between items-center pt-1 border-t border-gray-200 dark:border-gray-600">
                        <span className="text-xs text-gray-500 dark:text-gray-400">Custo Kit</span>
                        <span className="text-sm font-medium text-amber-600 dark:text-amber-400">
                          {(c.custo_kit || 0).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })}
                        </span>
                      </div>
                    )}
                    <div className="flex justify-between items-center">
                      <span className="text-xs text-gray-500 dark:text-gray-400">Margem Orçada</span>
                      <span className="text-sm font-medium text-gray-600 dark:text-gray-300">
                        {(c.margem_orcada || 0).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })}
                      </span>
                    </div>
                    <div className="flex justify-between items-center">
                      <span className="text-xs text-gray-500 dark:text-gray-400">Margem Realizada</span>
                      <span className={`text-sm font-bold ${(c.margem_realizada || 0) >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}>
                        {(c.margem_realizada || 0).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })}
                      </span>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

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
          const ticketKitConfig = event.ticketAtual || 0;
          const volBase = Math.max(volumeParaMeta, 0);
          const margemReal = margemRealizadaKits != null ? margemRealizadaKits : (event.margemRealizadaTotal || 0);
          const metaMargemGlobal = event.budgetTicket > 0 && kitCost > 0 ? (event.budgetTicket - kitCost) * event.salesGoal : 0;

          const multipliers = [0.80, 0.85, 0.90, 0.95, 1.00, 1.05, 1.10, 1.15, 1.20];
          const labels = ['Vendas futuras -20%', 'Vendas futuras -15%', 'Vendas futuras -10%', 'Vendas futuras -5%', 'Meta (0%)', 'Vendas futuras +5%', 'Vendas futuras +10%', 'Vendas futuras +15%', 'Vendas futuras +20%'];

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

      {faixasPrecoSite && (faixasPrecoSite.kit_basico.length > 0 || faixasPrecoSite.kit_participacao.length > 0) && (
        <div className="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm border border-gray-200 dark:border-gray-700">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold text-gray-900 dark:text-white flex items-center gap-2">
              <DollarSign className="w-4 h-4 text-blue-500" />
              Faixas de Preço Site (Orçado)
            </h3>
            <button
              onClick={() => setSimuladorFaixas(v => !v)}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors ${
                simuladorFaixas
                  ? 'bg-purple-600 text-white hover:bg-purple-700'
                  : 'bg-purple-50 dark:bg-purple-900/20 text-purple-700 dark:text-purple-300 hover:bg-purple-100 dark:hover:bg-purple-900/40 border border-purple-200 dark:border-purple-700'
              }`}
            >
              <Sliders className="w-3.5 h-3.5" />
              {simuladorFaixas ? 'Fechar Simulador' : 'Simulador'}
            </button>
          </div>

          {!simuladorFaixas ? (
            <div className="space-y-4">
              {(['kit_basico', 'kit_participacao'] as const).map((tipoKit) => {
                const faixas = faixasPrecoSite[tipoKit];
                if (faixas.length === 0) return null;
                const totalQtd = faixas.reduce((s, f) => s + f.qtd, 0);
                const totalReceita = faixas.reduce((s, f) => s + f.total, 0);
                const tktMedioGlobal = totalQtd > 0 ? totalReceita / totalQtd : 0;
                const label = tipoKit === 'kit_basico' ? 'Kit Básico' : 'Kit Participação';
                return (
                  <div key={tipoKit}>
                    <p className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-2">{label}</p>
                    <div className="overflow-x-auto rounded-lg border border-gray-200 dark:border-gray-700">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className={`border-b ${isDark ? 'bg-gray-700/50 border-gray-600' : 'bg-gray-50 border-gray-200'}`}>
                            <th className="text-left py-2 px-3 text-xs font-semibold text-gray-500 dark:text-gray-400">Faixa</th>
                            <th className="text-right py-2 px-3 text-xs font-semibold text-gray-500 dark:text-gray-400">Qtd</th>
                            <th className="text-right py-2 px-3 text-xs font-semibold text-gray-500 dark:text-gray-400">Tkt Médio</th>
                            <th className="text-right py-2 px-3 text-xs font-semibold text-gray-500 dark:text-gray-400">Total</th>
                            <th className="text-right py-2 px-3 text-xs font-semibold text-gray-500 dark:text-gray-400">% Qtd</th>
                          </tr>
                        </thead>
                        <tbody>
                          {faixas.map((f, i) => (
                            <tr key={i} className={`border-b border-gray-100 dark:border-gray-700/50 hover:bg-gray-50 dark:hover:bg-gray-700/30`}>
                              <td className="py-2 px-3 font-medium text-gray-900 dark:text-white">Faixa {f.faixa}</td>
                              <td className="py-2 px-3 text-right text-gray-700 dark:text-gray-300">{formatNumber(f.qtd)}</td>
                              <td className="py-2 px-3 text-right text-blue-600 dark:text-blue-400 font-medium">{formatCurrency(f.tkt_medio)}</td>
                              <td className="py-2 px-3 text-right text-gray-700 dark:text-gray-300">{formatCurrency(f.total)}</td>
                              <td className="py-2 px-3 text-right text-gray-500 dark:text-gray-400">{totalQtd > 0 ? ((f.qtd / totalQtd) * 100).toFixed(1) : '0.0'}%</td>
                            </tr>
                          ))}
                          <tr className={`font-semibold ${isDark ? 'bg-gray-700/50' : 'bg-gray-50'}`}>
                            <td className="py-2 px-3 text-gray-900 dark:text-white">Total</td>
                            <td className="py-2 px-3 text-right text-gray-900 dark:text-white">{formatNumber(totalQtd)}</td>
                            <td className="py-2 px-3 text-right text-blue-600 dark:text-blue-400">{formatCurrency(tktMedioGlobal)}</td>
                            <td className="py-2 px-3 text-right text-gray-900 dark:text-white">{formatCurrency(totalReceita)}</td>
                            <td className="py-2 px-3 text-right text-gray-500 dark:text-gray-400">100%</td>
                          </tr>
                        </tbody>
                      </table>
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            /* ── SIMULATOR MODE ── */
            (() => {
              // Orçado: uses atletas_site_pago and atletas_site_tkt_medio from the
              // cadastro (salesGoal / budgetTicket), not the faixas breakdown table.
              const orcQtd = event?.salesGoal ?? 0;
              const orcTkt = event?.budgetTicket ?? 0;
              const orcReceita = Math.round(orcQtd * orcTkt * 100) / 100;
              const orcMargemPct = event?.margemOrcadaPct ?? null;

              const realQtd = event?.currentSales ?? 0;
              const realReceita = event?.currentReceita ?? 0;
              const realTkt = event?.averageTicket ?? 0;
              const realMargemPct = event?.margemRealizadaPct ?? null;

              const { custoKitUnit, custoKitNome } = (() => {
                if (event?.margemPorKit && event.margemPorKit.length > 0) {
                  const isBasico = (nome: string) =>
                    /b[áa]sico/i.test(nome) || /kit.?b[áa]s/i.test(nome);

                  const kitsComCusto = event.margemPorKit.filter(k => k.custoKit !== null && k.custoKit !== undefined && k.qtd > 0);
                  if (kitsComCusto.length > 0) {
                    const kitsBas = kitsComCusto.filter(k => isBasico(k.tipoKit));
                    const kitsAlvo = kitsBas.length > 0 ? kitsBas : kitsComCusto;
                    const totalQtd = kitsAlvo.reduce((s, k) => s + k.qtd, 0);
                    const custo = kitsAlvo.reduce((s, k) => s + (k.custoKit ?? 0) * k.qtd, 0) / totalQtd;
                    const nome = kitsBas.length > 0 ? kitsAlvo[0].tipoKit : 'média ponderada';
                    return { custoKitUnit: custo, custoKitNome: nome };
                  }
                }
                return { custoKitUnit: (event?.kitCostPerUnit ?? null) as number | null, custoKitNome: 'kit' };
              })();

              const projRows = projetadoFaixas
                .map(r => ({ ...r, precoN: parseFloat(r.preco.replace(',', '.')) || 0, qtdN: parseInt(r.qtd, 10) || 0 }))
                .filter(r => r.precoN > 0 && r.qtdN > 0);
              // Incremental (only what was typed in the simulator)
              const projOnlyQtd = projRows.reduce((s, r) => s + r.qtdN, 0);
              const projOnlyReceita = projRows.reduce((s, r) => s + r.precoN * r.qtdN, 0);
              // Combined = Real Atual + Faixas Projetadas (projected final outcome)
              const projQtd = realQtd + projOnlyQtd;
              const projReceita = realReceita + projOnlyReceita;
              const projTkt = projQtd > 0 ? projReceita / projQtd : 0;
              const projMargemVal: number | null = (custoKitUnit !== null && projQtd > 0)
                ? projReceita - custoKitUnit * projQtd
                : null;

              const orcMargemVal: number | null = orcMargemPct !== null && orcReceita > 0
                ? orcReceita * orcMargemPct / 100
                : null;
              const realMargemVal: number | null = realMargemPct !== null && realReceita > 0
                ? realReceita * realMargemPct / 100
                : null;

              const deltaBadge = (proj: number | null, orc: number | null, isCurrency = false) => {
                if (proj === null || orc === null || orc === 0) return null;
                const diff = proj - orc;
                const pctDiff = (diff / Math.abs(orc)) * 100;
                const isPos = diff >= 0;
                return (
                  <span className={`inline-flex items-center gap-0.5 text-xs font-bold px-1.5 py-0.5 rounded ${isPos ? 'bg-green-100 text-green-700 dark:bg-green-800/60 dark:text-green-300' : 'bg-red-100 text-red-700 dark:bg-red-800/60 dark:text-red-300'}`}>
                    {isPos ? '▲' : '▼'}{isCurrency ? formatCurrency(Math.abs(diff)) : formatNumber(Math.abs(diff))} ({Math.abs(pctDiff).toFixed(1)}%)
                  </span>
                );
              };
              const hasValidProjRows = projRows.length > 0;
              // Projetado card shows values whenever there's real data OR typed faixas
              const hasProjData = projQtd > 0;

              const colCard = (
                title: string,
                accent: string,
                titleColor: string,
                qtd: number,
                tkt: number,
                receita: number,
                margemVal: number | null,
                isProj = false,
                subtitle?: string
              ) => (
                <div className={`rounded-xl border p-4 ${accent}`}>
                  <div className="mb-4">
                    <p className={`text-xs font-extrabold uppercase tracking-widest ${titleColor}`}>{title}</p>
                    {subtitle && <p className="text-[10px] text-gray-400 dark:text-gray-500 mt-0.5">{subtitle}</p>}
                  </div>
                  <div className="space-y-3">
                    <div>
                      <div className="flex items-center gap-1.5 mb-0.5">
                        <p className="text-sm font-semibold text-gray-600 dark:text-gray-300">Qtd. Inscritos</p>
                        {isProj && deltaBadge(hasValidProjRows ? qtd : null, orcQtd > 0 ? orcQtd : null)}
                      </div>
                      <p className="text-base font-bold text-gray-900 dark:text-white">
                        {hasProjData || !isProj ? (qtd > 0 ? formatNumber(qtd) : '0') : '—'}
                      </p>
                    </div>
                    <div>
                      <div className="flex items-center gap-1.5 mb-0.5">
                        <p className="text-sm font-semibold text-gray-600 dark:text-gray-300">Ticket Médio</p>
                        {isProj && deltaBadge(hasValidProjRows ? tkt : null, orcTkt > 0 ? orcTkt : null, true)}
                      </div>
                      <p className="text-base font-bold text-blue-600 dark:text-blue-400">
                        {hasProjData || !isProj ? (tkt > 0 ? formatCurrency(tkt) : '—') : '—'}
                      </p>
                    </div>
                    <div>
                      <div className="flex items-center gap-1.5 mb-0.5">
                        <p className="text-sm font-semibold text-gray-600 dark:text-gray-300">Receita Total</p>
                        {isProj && deltaBadge(hasValidProjRows ? receita : null, orcReceita > 0 ? orcReceita : null, true)}
                      </div>
                      <p className="text-base font-bold text-gray-900 dark:text-white">
                        {hasProjData || !isProj ? (receita > 0 ? formatCurrency(receita) : 'R$ 0,00') : '—'}
                      </p>
                    </div>
                    <div className={`pt-3 border-t ${isDark ? 'border-gray-600' : 'border-gray-200'}`}>
                      <div className="flex items-center gap-1.5 mb-0.5">
                        <p className="text-sm font-semibold text-gray-600 dark:text-gray-300">Margem (R$)</p>
                        {isProj && deltaBadge(hasValidProjRows ? margemVal : null, orcMargemVal, true)}
                      </div>
                      <p className={`text-base font-bold ${margemVal !== null && margemVal >= 0 ? 'text-emerald-600 dark:text-emerald-400' : margemVal !== null ? 'text-red-500' : 'text-gray-400 dark:text-gray-500'}`}>
                        {margemVal !== null ? formatCurrency(margemVal) : '—'}
                      </p>
                      {margemVal !== null && receita > 0 && (
                        <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">{((margemVal / receita) * 100).toFixed(1)}% da receita</p>
                      )}
                    </div>
                  </div>
                </div>
              );

              return (
                <div>
                  <div className="grid grid-cols-3 gap-3 mb-6">
                    {colCard('Orçado', isDark ? 'bg-gray-700/40 border-gray-600' : 'bg-gray-50 border-gray-200', 'text-gray-500 dark:text-gray-400', orcQtd, orcTkt, orcReceita, orcMargemVal)}
                    {colCard('Real Atual', isDark ? 'bg-blue-900/20 border-blue-700' : 'bg-blue-50 border-blue-200', 'text-blue-600 dark:text-blue-400', realQtd, realTkt, realReceita, realMargemVal)}
                    {colCard('Projetado', isDark ? 'bg-purple-900/20 border-purple-700' : 'bg-purple-50 border-purple-200', 'text-purple-600 dark:text-purple-400', projQtd, projTkt, projReceita, projMargemVal, true, 'Real atual + faixas projetadas')}
                  </div>

                  <div className="mb-2 flex items-center justify-between">
                    <p className="text-xs font-semibold text-gray-600 dark:text-gray-300 uppercase tracking-wider">Faixas Projetadas</p>
                    <div className="flex items-center gap-3">
                      {custoKitUnit !== null && (
                        <span className="text-[10px] text-gray-400 dark:text-gray-500">
                          Custo usado ({custoKitNome}): {formatCurrency(custoKitUnit)}/unid.
                        </span>
                      )}
                      {projetadoFaixas.length > 0 && (
                        <button
                          onClick={() => {
                            setProjetadoFaixas([]);
                            if (id) {
                              localStorage.removeItem(`proj_faixas_${id}`);
                              marketingService.deleteProjetadoFaixas(id).catch(() => {});
                            }
                          }}
                          className="text-[10px] font-semibold text-red-500 hover:text-red-700 dark:text-red-400 dark:hover:text-red-300 transition-colors"
                        >
                          Limpar projeção
                        </button>
                      )}
                    </div>
                  </div>

                  <div className="rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden mb-3">
                    <table className="w-full text-sm table-fixed">
                      <colgroup>
                        <col className="w-auto" />
                        <col style={{width: '6rem'}} />
                        <col style={{width: '7rem'}} />
                        <col style={{width: '8rem'}} />
                        <col style={{width: '8rem'}} />
                        <col style={{width: '2rem'}} />
                      </colgroup>
                      <thead>
                        <tr className={`border-b ${isDark ? 'bg-gray-700/50 border-gray-600' : 'bg-gray-50 border-gray-200'}`}>
                          <th className="text-left py-2 px-2 text-xs font-semibold text-gray-500 dark:text-gray-400">Faixa</th>
                          <th className="text-right py-2 px-2 text-xs font-semibold text-gray-500 dark:text-gray-400">Qtd</th>
                          <th className="text-right py-2 px-2 text-xs font-semibold text-gray-500 dark:text-gray-400">Ticket Médio</th>
                          <th className="text-right py-2 px-2 text-xs font-semibold text-gray-500 dark:text-gray-400">Receita</th>
                          <th className="text-right py-2 px-2 text-xs font-semibold text-gray-500 dark:text-gray-400">Margem</th>
                          <th className="py-2 px-1"></th>
                        </tr>
                      </thead>
                      <tbody>
                        {projetadoFaixas.length === 0 && (
                          <tr>
                            <td colSpan={6} className="py-6 text-center text-xs text-gray-400 dark:text-gray-500">
                              Nenhuma faixa projetada. Clique em "+ Adicionar Faixa" para começar.
                            </td>
                          </tr>
                        )}
                        {projetadoFaixas.map((row) => {
                          const precoN = parseFloat(row.preco.replace(',', '.')) || 0;
                          const qtdN = parseInt(row.qtd, 10) || 0;
                          const rowReceita = precoN * qtdN;
                          const rowMargem = custoKitUnit !== null && qtdN > 0 ? rowReceita - custoKitUnit * qtdN : null;
                          return (
                            <tr key={row.id} className={`border-b border-gray-100 dark:border-gray-700/50`}>
                              <td className="py-1.5 px-2">
                                <input
                                  type="text"
                                  value={row.nome}
                                  placeholder="Ex: Lote 1"
                                  onChange={e => setProjetadoFaixas(prev => prev.map(r => r.id === row.id ? { ...r, nome: e.target.value } : r))}
                                  className="w-full text-xs bg-transparent border border-gray-200 dark:border-gray-600 rounded px-2 py-1 text-gray-900 dark:text-white placeholder-gray-400 focus:outline-none focus:ring-1 focus:ring-purple-500"
                                />
                              </td>
                              <td className="py-1.5 px-2">
                                <input
                                  type="text"
                                  inputMode="numeric"
                                  value={row.qtd ? (parseInt(row.qtd, 10) || 0) > 0 ? (parseInt(row.qtd, 10)).toLocaleString('pt-BR') : row.qtd : row.qtd}
                                  placeholder="0"
                                  onChange={e => {
                                    const raw = e.target.value.replace(/\./g, '').replace(/\D/g, '');
                                    setProjetadoFaixas(prev => prev.map(r => r.id === row.id ? { ...r, qtd: raw } : r));
                                  }}
                                  className="w-full text-xs bg-transparent border border-gray-200 dark:border-gray-600 rounded px-2 py-1 text-right text-gray-900 dark:text-white placeholder-gray-400 focus:outline-none focus:ring-1 focus:ring-purple-500"
                                />
                              </td>
                              <td className="py-1.5 px-2">
                                <input
                                  type="text"
                                  inputMode="decimal"
                                  value={row.preco}
                                  placeholder="0,00"
                                  onChange={e => setProjetadoFaixas(prev => prev.map(r => r.id === row.id ? { ...r, preco: e.target.value } : r))}
                                  className="w-full text-xs bg-transparent border border-gray-200 dark:border-gray-600 rounded px-2 py-1 text-right text-gray-900 dark:text-white placeholder-gray-400 focus:outline-none focus:ring-1 focus:ring-purple-500"
                                />
                              </td>
                              <td className="py-1.5 px-2 text-right text-xs text-gray-700 dark:text-gray-300 font-medium">
                                {rowReceita > 0 ? formatCurrency(rowReceita) : '—'}
                              </td>
                              <td className={`py-1.5 px-2 text-right text-xs font-medium ${rowMargem !== null && rowMargem >= 0 ? 'text-emerald-600 dark:text-emerald-400' : rowMargem !== null ? 'text-red-500 dark:text-red-400' : 'text-gray-400 dark:text-gray-500'}`}>
                                {rowMargem !== null ? formatCurrency(rowMargem) : '—'}
                              </td>
                              <td className="py-1.5 px-2 text-center">
                                <button
                                  onClick={() => setProjetadoFaixas(prev => prev.filter(r => r.id !== row.id))}
                                  className="text-gray-400 hover:text-red-500 dark:hover:text-red-400 transition-colors"
                                >
                                  <X className="w-3.5 h-3.5" />
                                </button>
                              </td>
                            </tr>
                          );
                        })}
                        {projetadoFaixas.length > 0 && projQtd > 0 && (
                          <tr className={`font-semibold text-xs ${isDark ? 'bg-gray-700/50' : 'bg-gray-50'}`}>
                            <td className="py-2 px-3 text-gray-700 dark:text-gray-300">Total</td>
                            <td className="py-2 px-3 text-right text-gray-500 dark:text-gray-400 font-normal italic">Tkt médio: {formatCurrency(projTkt)}</td>
                            <td className="py-2 px-3 text-right text-gray-900 dark:text-white">{formatNumber(projQtd)}</td>
                            <td className="py-2 px-3 text-right text-gray-900 dark:text-white">{formatCurrency(projReceita)}</td>
                            <td className="py-2 px-3 text-right text-gray-500 dark:text-gray-400">100%</td>
                            <td></td>
                          </tr>
                        )}
                      </tbody>
                    </table>
                  </div>

                  <button
                    onClick={() => setProjetadoFaixas(prev => [...prev, { id: `${Date.now()}`, nome: '', preco: '', qtd: '' }])}
                    className="flex items-center gap-1.5 text-xs font-semibold text-purple-600 dark:text-purple-400 hover:text-purple-800 dark:hover:text-purple-300 transition-colors"
                  >
                    <Plus className="w-3.5 h-3.5" />
                    Adicionar Faixa
                  </button>
                </div>
              );
            })()
          )}
        </div>
      )}

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
        const stageLabel: Record<string, string> = { analitico: 'Analítico', estrategico: 'Estratégico', operacional: 'Operacional', final: 'Ação Final' };
        const stageColor: Record<string, string> = {
          analitico: 'bg-indigo-50 dark:bg-indigo-950/30 text-indigo-700 dark:text-indigo-300 border-indigo-200 dark:border-indigo-800',
          estrategico: 'bg-amber-50 dark:bg-amber-950/30 text-amber-700 dark:text-amber-300 border-amber-200 dark:border-amber-800',
          operacional: 'bg-rose-50 dark:bg-rose-950/30 text-rose-700 dark:text-rose-300 border-rose-200 dark:border-rose-800',
          final: 'bg-emerald-50 dark:bg-emerald-950/30 text-emerald-700 dark:text-emerald-300 border-emerald-200 dark:border-emerald-800',
        };
        const iscStatusMap: Record<string, string> = { accelerating: 'Forte', stable: 'Estável', decelerating: 'Fraco' };
        const iscColorMap: Record<string, string> = { accelerating: 'text-green-600 dark:text-green-400', stable: 'text-yellow-600 dark:text-yellow-400', decelerating: 'text-red-500 dark:text-red-400' };
        return (
          <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
            <div className="bg-white dark:bg-gray-800 rounded-xl w-full max-w-lg shadow-xl flex flex-col max-h-[90vh] overflow-y-auto">
              <div className="flex items-center justify-between p-5 pb-0">
                <h3 className="text-lg font-semibold text-gray-900 dark:text-white">{viewOnlyAction ? 'Visualizar Ação Comercial' : editingActionId ? 'Editar Ação Comercial' : 'Registrar Ação Comercial'}</h3>
                <button onClick={() => { setShowActionModal(false); setActionError(null); setEditingActionId(null); setViewOnlyAction(false); setActionForm(f => ({ ...f, forced_ponto_corte: '', forced_estagio: '' })); }} className="p-1 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300">
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
                  {!viewOnlyAction && <p className="text-xs opacity-60 mt-1">Snapshot dos dados ISC será congelado ao salvar</p>}
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
                    disabled={viewOnlyAction}
                    className={`w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 text-sm ${viewOnlyAction ? 'opacity-70 cursor-not-allowed' : ''}`}
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
                    disabled={viewOnlyAction}
                    className={`w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 text-sm ${viewOnlyAction ? 'opacity-70 cursor-not-allowed' : ''}`}
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Descrição</label>
                  <textarea
                    value={actionForm.descricao}
                    onChange={(e) => setActionForm({ ...actionForm, descricao: e.target.value })}
                    placeholder="Descreva a ação realizada..."
                    rows={3}
                    readOnly={viewOnlyAction}
                    className={`w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 resize-none text-sm ${viewOnlyAction ? 'opacity-70 cursor-not-allowed' : ''}`}
                  />
                </div>
              </div>

              <div className="flex gap-3 p-5 pt-0">
                {viewOnlyAction ? (
                  <button
                    onClick={() => { setShowActionModal(false); setActionError(null); setEditingActionId(null); setViewOnlyAction(false); setActionForm(f => ({ ...f, forced_ponto_corte: '', forced_estagio: '' })); }}
                    className="flex-1 px-4 py-2 border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors text-sm"
                  >
                    Fechar
                  </button>
                ) : (
                  <>
                    <button
                      onClick={() => { setShowActionModal(false); setActionError(null); setEditingActionId(null); setActionForm(f => ({ ...f, forced_ponto_corte: '', forced_estagio: '' })); }}
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
                      ) : editingActionId ? 'Salvar Edição' : 'Salvar Ação'}
                    </button>
                  </>
                )}
              </div>
            </div>
          </div>
        );
      })()}
      </>
      )}

      {showCurveInfoModal && (() => {
        const tipo = event?.iscComponents?.tipoCurva || 'linear';
        const fonte = event?.iscComponents?.fonteCurva || '';
        const anoRef = event?.iscComponents?.anoReferencia;

        const CURVE_CHAIN = [
          {
            key: 'manual',
            priority: 1,
            label: 'Manual',
            description: 'Curva de outro evento, escolhida manualmente pela equipe.',
            detail: 'Quando definida, tem prioridade absoluta sobre todas as outras opções.',
            colors: { bg: 'bg-green-50 dark:bg-green-950/30', border: 'border-green-200 dark:border-green-800', text: 'text-green-700 dark:text-green-300', badge: 'bg-green-100 dark:bg-green-900/60 text-green-800 dark:text-green-200', dot: 'bg-green-500', ring: 'ring-green-500' },
          },
          {
            key: 'historico',
            priority: 2,
            label: 'Histórico',
            description: 'Curva de vendas do próprio evento no ano anterior.',
            detail: 'Fonte mais confiável — usa o padrão real de vendas do mesmo evento.',
            colors: { bg: 'bg-blue-50 dark:bg-blue-950/30', border: 'border-blue-200 dark:border-blue-800', text: 'text-blue-700 dark:text-blue-300', badge: 'bg-blue-100 dark:bg-blue-900/60 text-blue-800 dark:text-blue-200', dot: 'bg-blue-500', ring: 'ring-blue-500' },
          },
          {
            key: 'circuito',
            priority: 3,
            label: 'Circuito',
            description: 'Evento do mesmo circuito e mesma cidade.',
            detail: 'Quando o evento não tem histórico próprio, busca um evento similar do mesmo circuito na mesma localidade.',
            colors: { bg: 'bg-purple-50 dark:bg-purple-950/30', border: 'border-purple-200 dark:border-purple-800', text: 'text-purple-700 dark:text-purple-300', badge: 'bg-purple-100 dark:bg-purple-900/60 text-purple-800 dark:text-purple-200', dot: 'bg-purple-500', ring: 'ring-purple-500' },
          },
          {
            key: 'circuito_similar',
            priority: 4,
            label: 'Circuito (Média)',
            description: 'Média ponderada de todos os eventos do mesmo circuito.',
            detail: 'Quando não há evento exato na mesma cidade, faz uma média de todos os eventos do circuito.',
            colors: { bg: 'bg-violet-50 dark:bg-violet-950/30', border: 'border-violet-200 dark:border-violet-800', text: 'text-violet-700 dark:text-violet-300', badge: 'bg-violet-100 dark:bg-violet-900/60 text-violet-800 dark:text-violet-200', dot: 'bg-violet-500', ring: 'ring-violet-500' },
          },
          {
            key: 'regional',
            priority: 5,
            label: 'Regional',
            description: 'Média de eventos no mesmo estado (mínimo 2 curvas).',
            detail: 'Último recurso baseado em dados reais — agrupa eventos da mesma região geográfica.',
            colors: { bg: 'bg-gray-50 dark:bg-gray-800/50', border: 'border-gray-300 dark:border-gray-600', text: 'text-gray-700 dark:text-gray-300', badge: 'bg-gray-100 dark:bg-gray-700/60 text-gray-800 dark:text-gray-200', dot: 'bg-gray-500', ring: 'ring-gray-500' },
          },
          {
            key: 'linear',
            priority: 6,
            label: 'Linear',
            description: 'Modelo linear de crescimento em 90 dias.',
            detail: 'Fallback final quando nenhuma curva histórica está disponível. Assume crescimento constante.',
            colors: { bg: 'bg-amber-50 dark:bg-amber-950/30', border: 'border-amber-200 dark:border-amber-800', text: 'text-amber-700 dark:text-amber-300', badge: 'bg-amber-100 dark:bg-amber-900/60 text-amber-800 dark:text-amber-200', dot: 'bg-amber-500', ring: 'ring-amber-500' },
          },
        ];

        return (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm" onClick={() => setShowCurveInfoModal(false)}>
            <div className={`w-full max-w-2xl rounded-2xl shadow-2xl ${isDark ? 'bg-gray-800' : 'bg-white'} max-h-[85vh] flex flex-col`} onClick={(e) => e.stopPropagation()}>
              <div className={`flex items-center justify-between p-5 border-b ${isDark ? 'border-gray-700' : 'border-gray-200'}`}>
                <div className="flex items-center gap-3">
                  <div className={`p-2 rounded-xl ${isDark ? 'bg-indigo-600/20' : 'bg-indigo-100'}`}>
                    <Activity className={`w-5 h-5 ${isDark ? 'text-indigo-400' : 'text-indigo-600'}`} />
                  </div>
                  <div>
                    <h3 className={`font-bold text-base ${isDark ? 'text-white' : 'text-gray-900'}`}>Curva de Referência</h3>
                    <p className={`text-xs ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Como o sistema escolhe a curva de benchmark para este evento</p>
                  </div>
                </div>
                <button onClick={() => setShowCurveInfoModal(false)} className="p-1.5 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors">
                  <X className="w-5 h-5 text-gray-500" />
                </button>
              </div>

              <div className="overflow-y-auto flex-1 p-5 space-y-3">
                <div className={`p-4 rounded-xl border-2 border-dashed ${isDark ? 'border-indigo-500/40 bg-indigo-950/20' : 'border-indigo-300 bg-indigo-50/50'}`}>
                  <p className={`text-sm leading-relaxed ${isDark ? 'text-indigo-300' : 'text-indigo-700'}`}>
                    O sistema percorre a cadeia abaixo em ordem de prioridade. A <strong>primeira opção com dados disponíveis</strong> é selecionada automaticamente. Você pode alterar manualmente clicando no botão de edição ao lado do badge.
                  </p>
                </div>

                <div className="relative">
                  <div className={`absolute left-6 top-8 bottom-4 w-0.5 ${isDark ? 'bg-gray-700' : 'bg-gray-200'}`} />

                  <div className="space-y-2">
                    {CURVE_CHAIN.map((curve, idx) => {
                      const isActive = tipo === curve.key;
                      return (
                        <div
                          key={curve.key}
                          className={`relative rounded-2xl border-2 transition-all duration-200 ${
                            isActive
                              ? `${curve.colors.border} ${curve.colors.bg} ${curve.colors.ring} ring-2`
                              : isDark
                                ? 'border-gray-700 bg-gray-800/50 opacity-60'
                                : 'border-gray-200 bg-white opacity-60'
                          }`}
                        >
                          <div className="p-4 flex items-start gap-4">
                            <div className={`shrink-0 w-10 h-10 rounded-xl flex items-center justify-center text-sm font-black ${
                              isActive ? curve.colors.badge : isDark ? 'bg-gray-700 text-gray-400' : 'bg-gray-100 text-gray-400'
                            }`}>
                              {curve.priority}
                            </div>
                            <div className="flex-1 min-w-0">
                              <div className="flex flex-wrap items-center gap-2 mb-1">
                                <span className={`text-sm font-bold ${isActive ? curve.colors.text : isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                                  {curve.label}
                                </span>
                                {isActive && (
                                  <span className={`text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full ${curve.colors.badge} flex items-center gap-1.5`}>
                                    <span className={`w-1.5 h-1.5 rounded-full inline-block ${curve.colors.dot} animate-pulse`} />
                                    Ativa {fonte ? `· ${fonte}` : ''} {anoRef ? `· ${anoRef}` : ''}
                                  </span>
                                )}
                              </div>
                              <p className={`text-sm ${isActive ? (isDark ? 'text-gray-300' : 'text-gray-700') : isDark ? 'text-gray-500' : 'text-gray-400'}`}>
                                {curve.description}
                              </p>
                              {isActive && (
                                <p className={`text-xs mt-1.5 italic ${isDark ? 'text-gray-400' : 'text-gray-500'} bg-white/40 dark:bg-black/20 rounded-lg px-3 py-1.5 border-l-4 ${curve.colors.border}`}>
                                  {curve.detail}
                                </p>
                              )}
                            </div>
                            {!isActive && idx < CURVE_CHAIN.findIndex(c => c.key === tipo) && (
                              <span className={`shrink-0 text-[10px] font-medium px-2 py-0.5 rounded-full ${isDark ? 'bg-gray-700 text-gray-500' : 'bg-gray-100 text-gray-400'}`}>
                                Sem dados
                              </span>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              </div>

              <div className={`p-4 border-t ${isDark ? 'border-gray-700' : 'border-gray-200'} flex items-center justify-between`}>
                <button
                  onClick={() => { setShowCurveInfoModal(false); openOverrideModal(); }}
                  className={`px-4 py-2 text-sm font-medium rounded-lg transition-colors ${isDark ? 'bg-indigo-600 hover:bg-indigo-700 text-white' : 'bg-indigo-600 hover:bg-indigo-700 text-white'}`}
                >
                  <div className="flex items-center gap-2">
                    <Pencil className="w-3.5 h-3.5" />
                    Alterar Curva
                  </div>
                </button>
                <button
                  onClick={() => setShowCurveInfoModal(false)}
                  className={`px-4 py-2 text-sm font-medium rounded-lg transition-colors ${isDark ? 'text-gray-400 hover:bg-gray-700' : 'text-gray-500 hover:bg-gray-100'}`}
                >
                  Fechar
                </button>
              </div>
            </div>
          </div>
        );
      })()}

      {showOverrideModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
          <div className={`w-full max-w-lg rounded-2xl shadow-2xl ${isDark ? 'bg-gray-800' : 'bg-white'} max-h-[80vh] flex flex-col`}>
            <div className="flex items-center justify-between p-4 border-b border-gray-200 dark:border-gray-700">
              <h3 className={`font-semibold ${isDark ? 'text-white' : 'text-gray-900'}`}>Alterar Curva de Referência</h3>
              <button onClick={() => setShowOverrideModal(false)} className="p-1 rounded hover:bg-gray-200 dark:hover:bg-gray-700">
                <X className="w-5 h-5 text-gray-500" />
              </button>
            </div>
            <div className="p-4">
              <input
                type="text"
                placeholder="Buscar grupo..."
                value={overrideSearch}
                onChange={(e) => setOverrideSearch(e.target.value)}
                className={`w-full px-3 py-2 rounded-lg border text-sm ${isDark ? 'bg-gray-700 border-gray-600 text-white placeholder-gray-400' : 'bg-white border-gray-300 text-gray-900 placeholder-gray-500'} focus:ring-2 focus:ring-indigo-500`}
              />
            </div>
            <div className="overflow-y-auto flex-1 px-4 pb-2">
              <button
                onClick={() => handleSetOverride(null)}
                disabled={savingOverride}
                className={`w-full text-left px-3 py-2 rounded-lg mb-1 text-sm transition-colors ${isDark ? 'hover:bg-gray-700 text-gray-300' : 'hover:bg-gray-100 text-gray-700'} ${event?.iscComponents?.tipoCurva !== 'manual' ? 'font-medium' : ''}`}
              >
                <span className="text-amber-500">Automático</span>
                <span className={`text-xs ml-2 ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>— usar cadeia de fallback padrão</span>
              </button>
              {availableCurves
                .filter(c => !overrideSearch || c.grupo.toLowerCase().includes(overrideSearch.toLowerCase()))
                .map(curve => (
                  <button
                    key={curve.grupo}
                    onClick={() => handleSetOverride(curve.grupo)}
                    disabled={savingOverride}
                    className={`w-full text-left px-3 py-2 rounded-lg mb-1 text-sm transition-colors ${isDark ? 'hover:bg-gray-700 text-gray-300' : 'hover:bg-gray-100 text-gray-700'} ${event?.iscComponents?.fonteCurva === curve.grupo && event?.iscComponents?.tipoCurva === 'manual' ? 'ring-2 ring-green-500' : ''}`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-medium truncate">{curve.grupo}</span>
                      <span className={`text-xs flex-shrink-0 ml-2 ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>
                        {curve.pontos} pts | {curve.anoReferencia}
                      </span>
                    </div>
                  </button>
                ))
              }
              {availableCurves.filter(c => !overrideSearch || c.grupo.toLowerCase().includes(overrideSearch.toLowerCase())).length === 0 && (
                <p className={`text-sm text-center py-4 ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>Nenhuma curva encontrada</p>
              )}
            </div>
            {savingOverride && (
              <div className="p-3 border-t border-gray-200 dark:border-gray-700 flex items-center justify-center gap-2 text-sm text-gray-500">
                <RefreshCw className="w-4 h-4 animate-spin" /> Salvando...
              </div>
            )}
          </div>
        </div>
      )}
      </div>
    </div>
  );
};

export default EventDetail;
