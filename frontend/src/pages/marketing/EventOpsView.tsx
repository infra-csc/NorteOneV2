import React, { useEffect, useMemo, useRef, useState, useCallback } from 'react';
import AtualizarHojeModal, { SyncStatus, SyncResult } from '../../components/marketing/AtualizarHojeModal';
import { useNavigate, useParams, useSearchParams, useLocation } from 'react-router-dom';
import {
  ArrowLeft,
  RefreshCw,
  Loader2,
  CheckCircle,
  AlertTriangle,
  Plus,
  X,
  TrendingUp,
  Activity,
  Calendar,
  MapPin,
  ExternalLink,
  WifiOff,
  Target,
  Clock,
} from 'lucide-react';
import { marketingService, MarketingEvent } from '../../services/api';
import { getISCColor, getISCEmoji, isInCriticalWindow } from '../../types/marketingPerformance';

interface DailySale {
  date: string;
  sales: number;
  expected: number;
  cumulativeSales?: number;
  cumulativeExpected?: number;
  dMinus?: number;
}

interface CommercialAction {
  id: string;
  tipo?: string;
  type: string;
  description: string;
  date: string;
}

interface ProjetoVinculado { id: number; nome: string; sku: string }

const TIPO_OPCOES: { value: string; label: string }[] = [
  { value: 'CAMPANHA', label: 'Campanha de Marketing' },
  { value: 'COMUNICACAO', label: 'Comunicação / Email' },
  { value: 'PROMOCAO', label: 'Promoção / Desconto' },
  { value: 'AUMENTO_PRECO', label: 'Aumento de Preço' },
  { value: 'REDUCAO_PRECO', label: 'Redução de Preço' },
  { value: 'NENHUMA_ACAO', label: 'Nenhuma Ação Tomada' },
  { value: 'OUTROS', label: 'Outros' },
];

const TIPO_LABEL: Record<string, string> = Object.fromEntries(TIPO_OPCOES.map(o => [o.value, o.label]));

const formatNumber = (v: number) => new Intl.NumberFormat('pt-BR').format(v ?? 0);
const formatCurrency = (v: number) => new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(v ?? 0);

const formatRelativeTime = (iso: string | null): string => {
  if (!iso) return '';
  const d = new Date(iso);
  const diff = Math.max(0, (Date.now() - d.getTime()) / 1000);
  if (diff < 60) return 'agora';
  if (diff < 3600) return `há ${Math.round(diff / 60)} min`;
  if (diff < 86400) return `há ${Math.round(diff / 3600)} h`;
  return d.toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
};

const todayLocalDate = () => {
  const n = new Date();
  return `${n.getFullYear()}-${String(n.getMonth() + 1).padStart(2, '0')}-${String(n.getDate()).padStart(2, '0')}`;
};

const EventOpsView: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const anoParam = searchParams.get('ano') ? parseInt(searchParams.get('ano')!) : undefined;
  const previewEvent = (location.state as any)?.previewEvent as MarketingEvent | undefined;

  const [event, setEvent] = useState<MarketingEvent | null>(previewEvent ?? null);
  const [dailySales, setDailySales] = useState<DailySale[]>([]);
  const [actions, setActions] = useState<CommercialAction[]>([]);
  const [projetos, setProjetos] = useState<ProjetoVinculado[]>([]);
  const [loading, setLoading] = useState(!previewEvent);
  const [error, setError] = useState<string | null>(null);
  const [ultimaAtualizacao, setUltimaAtualizacao] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [refreshOk, setRefreshOk] = useState(false);
  const [showSyncModal, setShowSyncModal] = useState(false);
  const [syncStatus, setSyncStatus] = useState<SyncStatus>('loading');
  const [syncResult, setSyncResult] = useState<SyncResult | null>(null);
  const [syncErrorMsg, setSyncErrorMsg] = useState<string | null>(null);
  const [salesAvg, setSalesAvg] = useState<{ media: number; periodo: number; label: string }[]>([]);
  const [hojeTotal, setHojeTotal] = useState<number | null>(null);
  const [showActionModal, setShowActionModal] = useState(false);
  const [savingAction, setSavingAction] = useState(false);
  const [actionForm, setActionForm] = useState({
    tipo: 'CAMPANHA',
    descricao: '',
    data_acao: todayLocalDate(),
    projeto_id: 0,
  });
  const [actionError, setActionError] = useState<string | null>(null);
  const [isOffline, setIsOffline] = useState(!navigator.onLine);

  const abortRef = useRef<AbortController | null>(null);
  const avgAbortRef = useRef<AbortController | null>(null);
  const bgRefreshTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    const onOnline = () => setIsOffline(false);
    const onOffline = () => setIsOffline(true);
    window.addEventListener('online', onOnline);
    window.addEventListener('offline', onOffline);
    return () => {
      window.removeEventListener('online', onOnline);
      window.removeEventListener('offline', onOffline);
    };
  }, []);

  const loadEvent = useCallback(async (forceRefresh = false) => {
    if (!id) return;
    if (abortRef.current) abortRef.current.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    if (!event) setLoading(true);
    try {
      const resp = await marketingService.getEventoById(id, controller.signal, anoParam, forceRefresh || undefined, forceRefresh || undefined);
      if (controller.signal.aborted) return;
      if ((resp as any)?.status === 'preparing') {
        setError('Estamos preparando este evento. Aguarde alguns segundos e atualize.');
        return;
      }
      setEvent(resp.evento);
      setDailySales((resp.dailySales || []) as DailySale[]);
      setActions((resp.commercialActions || []).map((a: any) => ({
        id: String(a.id),
        tipo: a.tipo,
        type: a.type,
        description: a.description,
        date: a.date,
      })));
      setProjetos(resp.projetos_vinculados || []);
      setUltimaAtualizacao((resp as any).ultima_atualizacao || null);
      const proj = (resp.projetos_vinculados || [])[0];
      if (proj) setActionForm(f => ({ ...f, projeto_id: proj.id }));
      setError(null);
    } catch (err: any) {
      if (err?.name === 'CanceledError' || err?.code === 'ERR_CANCELED') return;
      console.error('Erro ao carregar evento (ops):', err);
      if (!event) setError('Não foi possível carregar este evento.');
    } finally {
      if (!controller.signal.aborted) setLoading(false);
    }
  }, [id, anoParam, event]);

  useEffect(() => {
    loadEvent();
    return () => {
      if (abortRef.current) abortRef.current.abort();
      if (bgRefreshTimerRef.current) clearTimeout(bgRefreshTimerRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, anoParam]);

  useEffect(() => {
    if (!id) return;
    if (avgAbortRef.current) avgAbortRef.current.abort();
    const controller = new AbortController();
    avgAbortRef.current = controller;
    (async () => {
      try {
        const data = await marketingService.getSalesAverages(id, 30, controller.signal, anoParam);
        if (controller.signal.aborted) return;
        setSalesAvg(data.medias?.map(m => ({ media: m.media, periodo: m.periodo, label: m.label })) || []);
      } catch (err: any) {
        if (err?.name === 'CanceledError' || err?.code === 'ERR_CANCELED') return;
        console.error('Erro ao carregar médias (ops):', err);
      }
    })();
    return () => controller.abort();
  }, [id, anoParam]);

  const handleAtualizarHoje = async () => {
    if (!id || refreshing) return;
    setRefreshing(true);
    setRefreshOk(false);
    setSyncResult(null);
    setSyncErrorMsg(null);
    setSyncStatus('loading');
    setShowSyncModal(true);
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
      setHojeTotal(result.hoje_total);
      setUltimaAtualizacao(result.ultima_atualizacao || new Date().toISOString());
      setEvent(prev => prev ? {
        ...prev,
        currentSales: result.total_acumulado >= (prev.currentSales || 0)
          ? result.total_acumulado
          : prev.currentSales,
      } : prev);
      const todayStr = todayLocalDate();
      setDailySales(prev => {
        const exists = prev.some(d => d.date === todayStr);
        if (exists) return prev.map(d => d.date === todayStr ? { ...d, sales: result.hoje_total } : d);
        return [...prev, { date: todayStr, sales: result.hoje_total, expected: 0 }];
      });
      setRefreshOk(true);
      setTimeout(() => setRefreshOk(false), 3500);
      // Delay o primeiro re-fetch para dar tempo ao recompute em background
      // (disparado pelo backend) de concluir antes de sobrescrever os dados.
      if (bgRefreshTimerRef.current) clearTimeout(bgRefreshTimerRef.current);
      bgRefreshTimerRef.current = setTimeout(() => {
        bgRefreshTimerRef.current = null;
        loadEvent(true);
        bgRefreshTimerRef.current = setTimeout(() => {
          bgRefreshTimerRef.current = null;
          loadEvent(false);
        }, 12000);
      }, 4000);
    } catch (err: any) {
      console.error('Falha ao atualizar hoje (ops):', err);
      let errMsg = 'Não foi possível atualizar agora. Tente de novo em instantes.';
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
      setError(errMsg);
      setTimeout(() => setError(null), 10000);
    } finally {
      setRefreshing(false);
    }
  };

  const handleSaveAction = async () => {
    if (!actionForm.descricao.trim()) {
      setActionError('Descreva rapidamente o que foi feito.');
      return;
    }
    if (!actionForm.projeto_id) {
      setActionError('Nenhum projeto vinculado a este evento.');
      return;
    }
    setSavingAction(true);
    setActionError(null);
    try {
      const result = await marketingService.createAcaoComercial({
        projeto_id: actionForm.projeto_id,
        tipo: actionForm.tipo,
        descricao: actionForm.descricao.trim(),
        data_acao: actionForm.data_acao,
        snapshot_isc: event?.isc,
        snapshot_d_minus: event?.dMinusInscricoes,
        snapshot_ia730: event?.iscComponents?.ia730,
        snapshot_rolling14d: event?.iscComponents?.rolling14d,
        snapshot_curva_percent: event?.iscComponents?.curvaDPercent,
        snapshot_vendas_acumuladas: event?.currentSales,
        snapshot_playbook_letter: event?.suggestedAction?.letter,
      });
      const newAction: CommercialAction = {
        id: String((result as any)?.acao?.id ?? Date.now()),
        tipo: actionForm.tipo,
        type: actionForm.tipo === 'AUMENTO_PRECO' ? 'price_increase'
            : actionForm.tipo === 'REDUCAO_PRECO' ? 'price_decrease'
            : actionForm.tipo === 'CAMPANHA' ? 'campaign'
            : actionForm.tipo === 'COMUNICACAO' ? 'communication'
            : 'promotion',
        description: actionForm.descricao.trim(),
        date: actionForm.data_acao,
      };
      setActions(prev => [newAction, ...prev]);
      setShowActionModal(false);
      setActionForm(f => ({ ...f, descricao: '', tipo: 'CAMPANHA', data_acao: todayLocalDate() }));
    } catch (err) {
      console.error('Erro ao registrar ação (ops):', err);
      setActionError('Não foi possível salvar agora. Verifique sua conexão.');
    } finally {
      setSavingAction(false);
    }
  };

  const last7Days = useMemo(() => {
    const valid = dailySales.filter(d => !!d.date);
    const sorted = [...valid].sort((a, b) => a.date.localeCompare(b.date));
    return sorted.slice(-7);
  }, [dailySales]);

  const maxLast7 = useMemo(() => Math.max(1, ...last7Days.map(d => Math.max(d.sales, d.expected))), [last7Days]);

  const recentActions = useMemo(() => {
    const valid = actions.filter(a => !!a.date);
    const sorted = [...valid].sort((a, b) => b.date.localeCompare(a.date));
    return sorted.slice(0, 5);
  }, [actions]);

  const cutoffAlerta = event && typeof event.dMinusInscricoes === 'number' && isInCriticalWindow(event.dMinusInscricoes);

  const progresso = event && (event.salesGoal ?? 0) > 0
    ? Math.min(100, Math.round(((event.currentSales ?? 0) / event.salesGoal) * 100))
    : null;

  const media7 = salesAvg.find(m => m.periodo === 7)?.media;
  const media14 = salesAvg.find(m => m.periodo === 14)?.media;
  const media30 = salesAvg.find(m => m.periodo === 30)?.media;

  if (loading && !event) {
    return (
      <div className="min-h-screen bg-gray-50 dark:bg-gray-900 flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-blue-600" />
      </div>
    );
  }

  if (error && !event) {
    return (
      <div className="min-h-screen bg-gray-50 dark:bg-gray-900 p-6 flex flex-col items-center justify-center text-center">
        <AlertTriangle className="w-10 h-10 text-amber-500 mb-3" />
        <p className="text-gray-700 dark:text-gray-200 font-medium mb-4">{error}</p>
        <button
          onClick={() => navigate('/marketing')}
          className="px-4 py-2 bg-blue-600 text-white rounded-lg"
        >
          Voltar para a lista
        </button>
      </div>
    );
  }

  if (!event) return null;

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900 pb-32">
      <AtualizarHojeModal
        open={showSyncModal}
        status={syncStatus}
        result={syncResult}
        errorMsg={syncErrorMsg}
        onClose={() => setShowSyncModal(false)}
      />
      {/* Sticky header */}
      <div className="sticky top-0 z-20 bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700 shadow-sm">
        <div className="px-4 py-3 flex items-center gap-3">
          <button
            onClick={() => navigate('/marketing')}
            aria-label="Voltar"
            className="p-2 -ml-2 rounded-full hover:bg-gray-100 dark:hover:bg-gray-700"
          >
            <ArrowLeft className="w-5 h-5 text-gray-700 dark:text-gray-200" />
          </button>
          <div className="flex-1 min-w-0">
            <h1 className="font-semibold text-gray-900 dark:text-white truncate text-base">
              {event.name}
            </h1>
            <div className="flex items-center gap-2 text-[11px] text-gray-500 dark:text-gray-400">
              <Calendar className="w-3 h-3" />
              <span>{event.date ? new Date(event.date + 'T00:00:00').toLocaleDateString('pt-BR') : '-'}</span>
              {event.location && (<><MapPin className="w-3 h-3 ml-1" /><span className="truncate">{event.location}</span></>)}
            </div>
          </div>
          <button
            onClick={() => navigate(`/marketing/evento/${id}${anoParam ? `?ano=${anoParam}` : ''}`)}
            aria-label="Abrir detalhe completo"
            title="Detalhe completo"
            className="p-2 rounded-full hover:bg-gray-100 dark:hover:bg-gray-700"
          >
            <ExternalLink className="w-4 h-4 text-gray-500" />
          </button>
        </div>

        <div className="px-4 pb-2 flex items-center justify-between text-[11px] text-gray-500 dark:text-gray-400">
          <div className="flex items-center gap-2">
            <Clock className="w-3 h-3" />
            <span>Atualizado {formatRelativeTime(ultimaAtualizacao)}</span>
            {isOffline && (
              <span className="ml-1 inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300">
                <WifiOff className="w-3 h-3" /> offline
              </span>
            )}
          </div>
          <button
            onClick={handleAtualizarHoje}
            disabled={refreshing || isOffline}
            className="inline-flex items-center gap-1 px-2 py-1 rounded-md bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 disabled:opacity-50"
          >
            {refreshing
              ? <><Loader2 className="w-3 h-3 animate-spin" />Atualizando…</>
              : refreshOk
                ? <><CheckCircle className="w-3 h-3" />Atualizado</>
                : <><RefreshCw className="w-3 h-3" />Atualizar hoje</>}
          </button>
        </div>
      </div>

      <div className="px-4 pt-4 space-y-4">
        <button
          onClick={() => navigate(`/marketing/evento/${id}${anoParam ? `?ano=${anoParam}` : ''}`)}
          className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium shadow-sm"
        >
          <Activity className="w-4 h-4" />
          Ver todos os gráficos (Dash ISC)
          <ExternalLink className="w-3.5 h-3.5" />
        </button>

        {cutoffAlerta && (
          <div className="rounded-xl bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 p-3 flex items-center gap-2 text-sm text-amber-800 dark:text-amber-300">
            <Target className="w-4 h-4 flex-shrink-0" />
            <span>Janela crítica D-{event.dMinusInscricoes}: última semana para ajustes táticos.</span>
          </div>
        )}

        {/* KPI grandes */}
        <div className="grid grid-cols-2 gap-3">
          <KpiCard
            label="D- Inscrições"
            value={typeof event.dMinusInscricoes === 'number' ? `D-${event.dMinusInscricoes}` : '—'}
            tone={typeof event.dMinusInscricoes === 'number' && event.dMinusInscricoes <= 30 ? 'orange' : typeof event.dMinusInscricoes === 'number' && event.dMinusInscricoes <= 45 ? 'amber' : 'neutral'}
          />
          <KpiCard
            label="ISC"
            value={typeof event.isc === 'number'
              ? `${getISCEmoji(event.iscStatus || 'stable')} ${event.isc.toFixed(2)}`
              : '—'}
            valueColor={event.iscStatus ? getISCColor(event.iscStatus) : undefined}
          />
          <KpiCard
            label="Vendas hoje"
            value={hojeTotal !== null ? formatNumber(hojeTotal) : '—'}
            hint={hojeTotal === null ? 'Toque em Atualizar' : undefined}
          />
          <KpiCard
            label="Vendas / Meta"
            value={(event.salesGoal ?? 0) > 0
              ? `${formatNumber(event.currentSales ?? 0)} / ${formatNumber(event.salesGoal)}`
              : formatNumber(event.currentSales ?? 0)}
            extra={progresso !== null ? (
              <div className="mt-2">
                <div className="h-2 w-full bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
                  <div className="h-2 bg-blue-600" style={{ width: `${progresso}%` }} />
                </div>
                <p className="text-[11px] text-gray-500 mt-1">{progresso}% da meta</p>
              </div>
            ) : (
              <p className="text-[11px] text-amber-600 mt-1">Meta não configurada</p>
            )}
          />
        </div>

        {/* Ritmo */}
        <div className="rounded-xl bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 p-4">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-semibold text-gray-900 dark:text-white flex items-center gap-2">
              <Activity className="w-4 h-4 text-blue-600" />
              Ritmo de vendas
            </h2>
            {event.ticketAtual && event.ticketAtual > 0 && (
              <span className="text-[11px] text-gray-500 dark:text-gray-400">
                Ticket {formatCurrency(event.ticketAtual)}
              </span>
            )}
          </div>
          <div className="grid grid-cols-3 gap-3 text-center">
            <RitmoStat label="média 7d" value={media7} />
            <RitmoStat label="média 14d" value={media14} />
            <RitmoStat label="média 30d" value={media30} />
          </div>
          {(event.ticketKitNome || (event.kitCostPerUnit && event.kitCostPerUnit > 0)) && (
            <div className="mt-3 pt-3 border-t border-gray-100 dark:border-gray-700 flex flex-wrap items-center gap-2 text-[11px]">
              {event.ticketKitNome && (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300">
                  Kit: {event.ticketKitNome}
                </span>
              )}
              {event.kitCostPerUnit && event.kitCostPerUnit > 0 && (
                <span className="text-gray-500 dark:text-gray-400">
                  Custo unit. {formatCurrency(event.kitCostPerUnit)}
                </span>
              )}
              {event.margemRealizadaPct !== undefined && event.margemRealizadaPct !== null && (
                <span className="text-gray-500 dark:text-gray-400">
                  · Margem realiz. {event.margemRealizadaPct.toFixed(1)}%
                </span>
              )}
            </div>
          )}
        </div>

        {/* Curva D- compacta (últimos 7 dias) */}
        <div className="rounded-xl bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 p-4">
          <h2 className="text-sm font-semibold text-gray-900 dark:text-white flex items-center gap-2 mb-3">
            <TrendingUp className="w-4 h-4 text-blue-600" />
            Últimos 7 dias
          </h2>
          {last7Days.length === 0 ? (
            <p className="text-xs text-gray-500">Sem dados de vendas diárias.</p>
          ) : (
            <div className="space-y-2">
              {last7Days.map(d => {
                const dt = new Date(d.date + 'T00:00:00');
                const wd = dt.toLocaleDateString('pt-BR', { weekday: 'short' });
                const dm = dt.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' });
                const realPct = (d.sales / maxLast7) * 100;
                const expPct = (d.expected / maxLast7) * 100;
                const dif = d.sales - d.expected;
                return (
                  <div key={d.date} className="flex items-center gap-3 text-xs">
                    <div className="w-14 flex-shrink-0">
                      <div className="text-gray-500 capitalize leading-none">{wd}</div>
                      <div className="text-gray-700 dark:text-gray-300 font-medium leading-none mt-0.5">{dm}</div>
                    </div>
                    <div className="flex-1 space-y-1">
                      <div className="h-2 bg-gray-100 dark:bg-gray-700 rounded">
                        <div className="h-2 bg-blue-600 rounded" style={{ width: `${Math.min(100, realPct)}%` }} />
                      </div>
                      {d.expected > 0 && (
                        <div className="h-1 bg-gray-100 dark:bg-gray-700 rounded">
                          <div className="h-1 bg-gray-400 dark:bg-gray-500 rounded" style={{ width: `${Math.min(100, expPct)}%` }} />
                        </div>
                      )}
                    </div>
                    <div className="w-20 text-right">
                      <div className="font-semibold text-gray-900 dark:text-white">{formatNumber(d.sales)}</div>
                      {d.expected > 0 && (
                        <div className={`text-[10px] ${dif >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                          {dif >= 0 ? '+' : ''}{formatNumber(dif)} vs esp.
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Ações recentes */}
        <div className="rounded-xl bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 p-4">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-semibold text-gray-900 dark:text-white">Ações recentes</h2>
            {actions.length > recentActions.length && (
              <button
                onClick={() => navigate(`/marketing/evento/${id}${anoParam ? `?ano=${anoParam}` : ''}`)}
                className="text-[11px] text-blue-600 dark:text-blue-400"
              >
                Ver todas ({actions.length})
              </button>
            )}
          </div>
          {recentActions.length === 0 ? (
            <p className="text-xs text-gray-500">Nenhuma ação registrada ainda.</p>
          ) : (
            <ul className="divide-y divide-gray-100 dark:divide-gray-700">
              {recentActions.map(a => (
                <li key={a.id} className="py-2">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-xs font-medium text-gray-900 dark:text-white">
                      {TIPO_LABEL[a.tipo || ''] || a.tipo || 'Ação'}
                    </span>
                    <span className="text-[11px] text-gray-500">
                      {new Date(a.date + 'T00:00:00').toLocaleDateString('pt-BR')}
                    </span>
                  </div>
                  {a.description && (
                    <p className="text-[11px] text-gray-600 dark:text-gray-400 mt-0.5 line-clamp-2">{a.description}</p>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      {/* Botão flutuante: registrar ação */}
      <button
        onClick={() => {
          setActionError(null);
          if (projetos.length === 0) {
            setActionError('Este evento ainda não tem projeto vinculado.');
          } else if (!actionForm.projeto_id) {
            setActionForm(f => ({ ...f, projeto_id: projetos[0].id }));
          }
          setShowActionModal(true);
        }}
        className="fixed bottom-6 right-4 z-30 inline-flex items-center gap-2 px-5 py-3 rounded-full bg-blue-600 hover:bg-blue-700 text-white shadow-lg shadow-blue-600/30"
      >
        <Plus className="w-5 h-5" />
        <span className="font-medium text-sm">Registrar ação</span>
      </button>

      {/* Modal ação */}
      {showActionModal && (
        <div className="fixed inset-0 z-40 bg-black/50 flex items-end sm:items-center justify-center" onClick={() => setShowActionModal(false)}>
          <div
            className="w-full sm:max-w-md bg-white dark:bg-gray-800 rounded-t-2xl sm:rounded-2xl p-5 space-y-4"
            onClick={e => e.stopPropagation()}
          >
            <div className="flex items-center justify-between">
              <h3 className="text-base font-semibold text-gray-900 dark:text-white">Nova ação comercial</h3>
              <button onClick={() => setShowActionModal(false)} className="p-1 rounded hover:bg-gray-100 dark:hover:bg-gray-700">
                <X className="w-4 h-4 text-gray-500" />
              </button>
            </div>

            {projetos.length > 1 && (
              <div>
                <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">Projeto</label>
                <select
                  value={actionForm.projeto_id}
                  onChange={e => setActionForm(f => ({ ...f, projeto_id: parseInt(e.target.value) }))}
                  className="w-full px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                >
                  {projetos.map(p => (<option key={p.id} value={p.id}>{p.nome}</option>))}
                </select>
              </div>
            )}

            <div>
              <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">Tipo</label>
              <select
                value={actionForm.tipo}
                onChange={e => setActionForm(f => ({ ...f, tipo: e.target.value }))}
                className="w-full px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
              >
                {TIPO_OPCOES.map(opt => (<option key={opt.value} value={opt.value}>{opt.label}</option>))}
              </select>
            </div>

            <div>
              <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">Data</label>
              <input
                type="date"
                value={actionForm.data_acao}
                onChange={e => setActionForm(f => ({ ...f, data_acao: e.target.value }))}
                className="w-full px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">Descrição</label>
              <textarea
                value={actionForm.descricao}
                onChange={e => setActionForm(f => ({ ...f, descricao: e.target.value }))}
                placeholder="O que foi feito? (ex.: campanha Insta stories, push para base inativa…)"
                rows={3}
                className="w-full px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white resize-none"
              />
            </div>

            {actionError && (
              <p className="text-xs text-red-600 dark:text-red-400">{actionError}</p>
            )}

            <button
              onClick={handleSaveAction}
              disabled={savingAction || !actionForm.descricao.trim() || !actionForm.projeto_id}
              className="w-full py-3 rounded-lg bg-blue-600 hover:bg-blue-700 text-white font-medium text-sm disabled:opacity-50 inline-flex items-center justify-center gap-2"
            >
              {savingAction ? <><Loader2 className="w-4 h-4 animate-spin" />Salvando…</> : 'Salvar ação'}
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

interface KpiCardProps {
  label: string;
  value: string;
  hint?: string;
  extra?: React.ReactNode;
  tone?: 'neutral' | 'amber' | 'orange';
  valueColor?: string;
}

const KpiCard: React.FC<KpiCardProps> = ({ label, value, hint, extra, tone = 'neutral', valueColor }) => {
  const toneClass = tone === 'orange'
    ? 'border-orange-200 dark:border-orange-700 bg-orange-50/50 dark:bg-orange-900/10'
    : tone === 'amber'
      ? 'border-amber-200 dark:border-amber-700 bg-amber-50/50 dark:bg-amber-900/10'
      : 'border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800';
  return (
    <div className={`rounded-xl border p-3 ${toneClass}`}>
      <p className="text-[11px] text-gray-500 dark:text-gray-400 uppercase tracking-wide">{label}</p>
      <p className="text-xl font-bold mt-1" style={valueColor ? { color: valueColor } : undefined}>
        {value}
      </p>
      {hint && <p className="text-[11px] text-gray-500 mt-1">{hint}</p>}
      {extra}
    </div>
  );
};

const RitmoStat: React.FC<{ label: string; value?: number }> = ({ label, value }) => (
  <div>
    <p className="text-lg font-bold text-gray-900 dark:text-white">
      {value !== undefined && value !== null ? formatNumber(Math.round(value)) : '—'}
    </p>
    <p className="text-[11px] text-gray-500 dark:text-gray-400">{label}</p>
  </div>
);

export default EventOpsView;
