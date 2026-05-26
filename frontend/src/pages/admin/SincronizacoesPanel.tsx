import React, { useEffect, useState, useCallback, useRef } from 'react';
import { adminService } from '../../services/api';
import { useTheme } from '../../context/ThemeContext';
import {
  RefreshCw, ChevronDown, ChevronRight, CheckCircle2, AlertTriangle,
  XCircle, MinusCircle, Clock, Activity, Loader2, PauseCircle, PlayCircle,
  StopCircle, ArrowRight, DatabaseZap, X, Snowflake, CheckCheck, TrendingUp,
  RotateCcw, CalendarClock, ListChecks, Package
} from 'lucide-react';

interface ScheduledJob {
  key: string;
  label: string;
  next_run_iso: string | null;
  seconds_until: number | null;
  tipo: 'fixo' | 'rede_seguranca' | 'tick';
  descricao: string;
  atrasado: boolean;
  ultima_exec_iso: string | null;
}
interface JobRunHistEntry {
  started_at: string | null;
  duration_ms: number;
  grupos_total: number;
  grupos_ok: number;
  grupos_parcial: number;
  grupos_falha: number;
  status: string;
}
interface TodaySummary {
  eventos_sincronizados: number;
  eventos_ok: number;
  eventos_parcial: number;
  eventos_falha: number;
  eventos_pulado: number;
  ultimo_sync_iso: string | null;
  eventos_recentes: Array<{ grupo: string; status: string; ts: string }>;
  historico_jobs_by_name: {
    sincronizar_hoje: JobRunHistEntry[];
    snapshot_diario: JobRunHistEntry[];
  };
}
interface BundleSemSnapshot {
  bundle_entity_id: number;
  kit_nome: string | null;
  tipo_kit: string | null;
  id_evento: number | null;
}
interface KitMappingInfo {
  ultima_atualizacao_iso: string | null;
  idade_horas: number | null;
  bundles_com_snapshot: number;
  bundles_esperados: number;
  cobertura_pct: number | null;
  kits_sem_configuracao: number;
  bundles_sem_snapshot_total: number;
  bundles_sem_snapshot_lista: BundleSemSnapshot[];
  bundles_sem_snapshot_truncated: boolean;
  status: 'ok' | 'atencao' | 'critico';
}
interface SyncOverview {
  scheduled_jobs: ScheduledJob[];
  today_summary: TodaySummary;
  kit_mapping: KitMappingInfo;
  generated_at: string;
}

function fmtCountdown(secs: number | null): string {
  if (secs == null) return '—';
  if (secs <= 0) return 'agora';
  const h = Math.floor(secs / 3600);
  const m = Math.floor((secs % 3600) / 60);
  if (h > 24) {
    const d = Math.floor(h / 24);
    return `${d}d ${h % 24}h`;
  }
  if (h > 0) return `${h}h ${m}min`;
  if (m > 0) return `${m}min`;
  return `${secs}s`;
}

function fmtTimeBRT(iso: string | null): string {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('pt-BR', {
    timeZone: 'America/Sao_Paulo',
    day: '2-digit', month: '2-digit',
    hour: '2-digit', minute: '2-digit',
  });
}

interface SyncCycle {
  ciclo_id: string;
  job_name: string;
  iniciado_em: string | null;
  concluido_em: string | null;
  ultima_atividade: string | null;
  status: string;
  duracao_ms: number | null;
  detalhes: string | null;
  motivo: string | null;
  total_grupos: number;
  ok: number;
  parcial: number;
  falha: number;
  pulado: number;
}

interface SyncEvent {
  id: number;
  nivel: string;
  job_name: string;
  grupo: string | null;
  fonte: string | null;
  status: string;
  motivo: string | null;
  detalhes: string | null;
  qtd_antes: number | null;
  qtd_depois: number | null;
  data_floor: string | null;
  duracao_ms: number | null;
  created_at: string;
}

type FullProgressResult = {
  grupo: string;
  status: 'ok' | 'failed' | 'skipped';
  motivo: string | null;
  qtd_antes: number | null;
  qtd_depois: number | null;
  duracao_ms: number | null;
  detalhes: string | null;
};

type FullProgressInFlight = {
  grupo: string;
  started_at: number;
};

type FullProgress = {
  status: 'idle' | 'running' | 'done' | 'error';
  started_at: number | null;
  finished_at: number | null;
  triggered_by: string | null;
  incremental: boolean;
  total: number;
  current: number;
  current_grupo: string | null;
  ok: number;
  failed: number;
  skipped: number;
  frozen: number;
  ciclo_id: string | null;
  error: string | null;
  results: FullProgressResult[];
  // Fase de preparação — antes de `total` ser conhecido.
  setup_step?: string | null;
  // Lista ordenada do que falta processar (atualizada conforme workers consomem).
  grupos_pendentes?: string[];
  // Grupos atualmente sendo processados em paralelo.
  em_execucao?: FullProgressInFlight[];
};

function fmtElapsed(startTs: number | null, endTs: number | null): string {
  if (!startTs) return '—';
  const ms = ((endTs ?? Date.now() / 1000) - startTs) * 1000;
  const s = Math.floor(ms / 1000);
  const m = Math.floor(s / 60);
  const rs = s - m * 60;
  if (m === 0) return `${rs}s`;
  return `${m}min ${rs}s`;
}

const STATUS_BADGE: Record<string, { label: string; cls: string; Icon: any }> = {
  ok:           { label: 'OK',           cls: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-400', Icon: CheckCircle2 },
  concluido:    { label: 'Concluído',    cls: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-400', Icon: CheckCircle2 },
  parcial:      { label: 'Parcial',      cls: 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400',         Icon: AlertTriangle },
  falha:        { label: 'Falha',        cls: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400',                 Icon: XCircle },
  pulado:       { label: 'Pulado',       cls: 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300',               Icon: MinusCircle },
  iniciado:     { label: 'Em execução', cls: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400',              Icon: Loader2 },
  inicio:       { label: 'Iniciado',     cls: 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-400',               Icon: ArrowRight },
  interrompido: { label: 'Interrompido', cls: 'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-400',     Icon: AlertTriangle },
};

const MOTIVO_LABELS: Record<string, string> = {
  magento_timeout:      'Timeout no Magento',
  magento_indisponivel: 'Magento indisponível',
  ativo_indisponivel:   'Ativo indisponível',
  conexao_perdida:      'Conexão perdida',
  ssh_down:             'Túnel SSH indisponível',
  circuit_aberto:       'Circuit breaker aberto',
  pool_exaurido:        'Pool de conexões esgotado',
  erro_operacional:     'Erro operacional',
  timeout:              'Timeout',
  sem_mapeamento:       'Sem mapeamento',
  erro_generico:        'Erro genérico',
  fonte_indisponivel:   'Fonte indisponível',
};

const JOB_LABELS: Record<string, string> = {
  sincronizar_hoje_batch:              'Sincronização de hoje',
  snapshot_diario_batch:               'Snapshot diário',
  consolidar_vendas_grupo:             'Consolidação por grupo',
  atualizar_hoje:                      'Atualizar Hoje (manual)',
  consolidacao_diaria_04h:             'Job agendado das 04h',
  consolidar_curvas_historicas_batch:  'Curvas históricas',
  sincronizar_margem_bundle_rev_batch: 'Margem por bundle',
  sync_event_log_cleanup:              'Limpeza de logs',
  consolidar_full_manual:              'Reconsolidar Todos (manual)',
};

function fmtDateTime(iso: string | null): string {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('pt-BR', {
    timeZone: 'America/Sao_Paulo',
    day: '2-digit', month: '2-digit', year: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  });
}

function fmtDuration(ms: number | null): string {
  if (ms == null) return '—';
  if (ms < 1000) return `${ms}ms`;
  const s = ms / 1000;
  if (s < 60) return `${s.toFixed(1)}s`;
  const m = Math.floor(s / 60);
  const rs = Math.floor(s - m * 60);
  return `${m}min ${rs}s`;
}

function StatusBadge({ status, spinning }: { status: string; spinning?: boolean }) {
  const cfg = STATUS_BADGE[status] || { label: status, cls: 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300', Icon: Activity };
  const Icon = cfg.Icon;
  const shouldSpin = spinning ?? (status === 'iniciado');
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium ${cfg.cls}`}>
      <Icon className={`w-3 h-3 ${shouldSpin ? 'animate-spin' : ''}`} />
      {cfg.label}
    </span>
  );
}

const SincronizacoesPanel: React.FC = () => {
  const { isDark } = useTheme();
  const [cycles, setCycles] = useState<SyncCycle[]>([]);
  const [loading, setLoading] = useState(true);
  const [filterJob, setFilterJob] = useState<string>('');
  const [filterStatus, setFilterStatus] = useState<string>('');
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [details, setDetails] = useState<Record<string, SyncEvent[]>>({});
  const [loadingDetail, setLoadingDetail] = useState<Set<string>>(new Set());
  const [paused, setPaused] = useState(false);
  const [pausedBy, setPausedBy] = useState<string | null>(null);
  const [pauseLoading, setPauseLoading] = useState(false);
  const [overview, setOverview] = useState<SyncOverview | null>(null);
  const [filterUltimas24h, setFilterUltimas24h] = useState<boolean>(false);
  const [histJobName, setHistJobName] = useState<'sincronizar_hoje' | 'snapshot_diario'>('sincronizar_hoje');
  const [showBundlesFaltantesModal, setShowBundlesFaltantesModal] = useState(false);
  // Tick para "atualizado há Xs" — atualiza a cada 1s sem refazer fetch.
  const [nowTick, setNowTick] = useState<number>(() => Date.now());
  const ciclosSectionRef = useRef<HTMLDivElement | null>(null);
  const [interruptLoading, setInterruptLoading] = useState(false);
  const [interruptResult, setInterruptResult] = useState<string | null>(null);
  const [selectedCycles, setSelectedCycles] = useState<Set<string>>(new Set());
  const [interruptingCycles, setInterruptingCycles] = useState<Set<string>>(new Set());

  // ── Consolidação Full ──────────────────────────────────────────────────────
  const [showFullModal, setShowFullModal] = useState(false);
  const [fullProgress, setFullProgress] = useState<FullProgress | null>(null);
  const [fullStarting, setFullStarting] = useState(false);
  const [fullIncremental, setFullIncremental] = useState(false);
  const [checkpoint, setCheckpoint] = useState<
    | null
    | {
        resumable: true;
        ciclo_id: string;
        incremental: boolean;
        triggered_by: string | null;
        started_at_cycle: string | null;
        ok_count: number;
        failed_count: number;
        last_grupo: string | null;
        last_processed_at: string | null;
      }
  >(null);
  const [checkpointLoading, setCheckpointLoading] = useState(false);
  const [elapsedSecs, setElapsedSecs] = useState(0);
  const resultsEndRef = useRef<HTMLDivElement>(null);
  const prevResultsCount = useRef(0);

  // Track previous cycle states to detect "iniciado → final" transitions
  const prevCyclesRef = useRef<SyncCycle[]>([]);
  // Use a ref for expanded so fetchCycles can access it without being in deps
  const expandedRef = useRef<Set<string>>(new Set());
  // Dedupe do auto-fetch do banner 04h: refetch só quando o ciclo (ou sua
  // última atividade) mudar — evita disparar requisição idêntica a cada poll.
  const last04hFetchKeyRef = useRef<string | null>(null);

  useEffect(() => {
    expandedRef.current = expanded;
  }, [expanded]);

  const cardBase = isDark
    ? 'bg-gray-800/50 backdrop-blur-sm border border-gray-700/50'
    : 'bg-white/80 backdrop-blur-sm border border-gray-200 shadow-sm';
  const textPrimary = isDark ? 'text-white' : 'text-gray-900';
  const textSecondary = isDark ? 'text-gray-400' : 'text-gray-500';
  const selectClass = `text-sm rounded-lg px-3 py-1.5 border outline-none ${isDark ? 'bg-gray-700 border-gray-600 text-white' : 'bg-white border-gray-300 text-gray-900'}`;

  const refreshDetail = useCallback(async (cicloId: string) => {
    setLoadingDetail(prev => {
      if (prev.has(cicloId)) return prev;
      const s = new Set(prev); s.add(cicloId); return s;
    });
    try {
      const d = await adminService.getSyncCycleDetail(cicloId);
      setDetails(prev => ({ ...prev, [cicloId]: d.events }));
    } catch (e) {
      console.error('detail refresh failed:', e);
    } finally {
      setLoadingDetail(prev => { const s = new Set(prev); s.delete(cicloId); return s; });
    }
  }, []);

  const fetchCycles = useCallback(async () => {
    try {
      const data = await adminService.getSyncCycles({
        job: filterJob || undefined,
        status: filterStatus || undefined,
        limit: 100,
      });
      const newCycles: SyncCycle[] = data.cycles || [];

      // Auto-refresh detail for cycles that just transitioned from 'iniciado' → final
      const transitions = newCycles.filter(c => {
        const prev = prevCyclesRef.current.find(p => p.ciclo_id === c.ciclo_id);
        return prev?.status === 'iniciado' && c.status !== 'iniciado';
      });
      // Also refresh detail of still-running expanded cycles (pick up new sub-events)
      const runningExpanded = newCycles.filter(c =>
        c.status === 'iniciado' && expandedRef.current.has(c.ciclo_id)
      );

      const toRefresh = new Set([
        ...transitions.map(c => c.ciclo_id),
        ...runningExpanded.map(c => c.ciclo_id),
      ]);
      toRefresh.forEach(id => {
        if (expandedRef.current.has(id)) {
          refreshDetail(id);
        }
      });

      // Auto-fetch do detalhe do ciclo 04h mais recente — o banner no topo
      // depende dele para mostrar quais sub-passos rodaram. Sem isso o usuário
      // precisaria expandir o ciclo manualmente para ver o resumo. Dedupe pela
      // chave (ciclo_id + ultima_atividade): só refaz se o ciclo mudou ou ganhou
      // atividade nova.
      const last04h = newCycles.find(c => c.job_name === 'consolidacao_diaria_04h');
      if (last04h) {
        const key = `${last04h.ciclo_id}:${last04h.ultima_atividade || ''}:${last04h.status}`;
        if (last04hFetchKeyRef.current !== key) {
          last04hFetchKeyRef.current = key;
          refreshDetail(last04h.ciclo_id);
        }
      }

      prevCyclesRef.current = newCycles;
      setCycles(newCycles);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, [filterJob, filterStatus, refreshDetail]);

  const fetchPauseStatus = useCallback(async () => {
    try {
      const info = await adminService.getSyncPauseStatus();
      setPaused(info.paused);
      setPausedBy(info.by);
    } catch (e) {
      console.error(e);
    }
  }, []);

  const fetchOverview = useCallback(async () => {
    try {
      const ov = await adminService.getSyncOverview();
      setOverview(ov);
    } catch (e) {
      console.error('overview fetch failed:', e);
    }
  }, []);

  useEffect(() => {
    setLoading(true);
    fetchCycles();
    fetchPauseStatus();
    fetchOverview();
    // Poll every 5s for near-real-time feel
    const it = setInterval(() => { fetchCycles(); fetchPauseStatus(); }, 5000);
    // Overview muda mais devagar (timers + agregados) — 30s evita carga desnecessária
    const itOv = setInterval(() => { fetchOverview(); }, 30000);
    // Tick de 1s só pra atualizar "atualizado há Xs" sem novo fetch.
    const itTick = setInterval(() => setNowTick(Date.now()), 1000);
    // Page Visibility API: pausa polling em background pra não martelar API
    // quando o usuário não está olhando, e dispara refresh imediato ao voltar.
    let pausedByHide = false;
    const onVisible = () => {
      if (document.visibilityState === 'visible') {
        if (pausedByHide) {
          fetchCycles();
          fetchPauseStatus();
          fetchOverview();
          pausedByHide = false;
        }
      } else {
        pausedByHide = true;
      }
    };
    document.addEventListener('visibilitychange', onVisible);
    return () => {
      clearInterval(it);
      clearInterval(itOv);
      clearInterval(itTick);
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, [fetchCycles, fetchPauseStatus, fetchOverview]);

  // ── Polling de progresso da consolidação full ──────────────────────────────
  useEffect(() => {
    if (!showFullModal) return;
    const poll = async () => {
      try {
        const p = await adminService.getSnapshotConsolidationFullProgress();
        setFullProgress(p);
        if (p.results.length > prevResultsCount.current) {
          prevResultsCount.current = p.results.length;
          setTimeout(() => resultsEndRef.current?.scrollIntoView({ behavior: 'smooth' }), 80);
        }
      } catch (e) { console.error(e); }
    };
    poll();
    const it = setInterval(poll, 1500);
    // Page Visibility API: dispara re-poll imediato ao retornar ao tab/desbloquear tela.
    // Sem isso, o browser throttle o setInterval para ~60s em segundo plano e o
    // progresso fica parado por até 1 minuto após o usuário voltar.
    const onVisible = () => {
      if (document.visibilityState === 'visible') poll();
    };
    document.addEventListener('visibilitychange', onVisible);
    return () => {
      clearInterval(it);
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, [showFullModal]);

  // ── Timer de tempo decorrido (atualiza a cada segundo) ─────────────────────
  useEffect(() => {
    if (fullProgress?.status !== 'running') { setElapsedSecs(0); return; }
    const it = setInterval(() => {
      setElapsedSecs(s => s + 1);
    }, 1000);
    return () => clearInterval(it);
  }, [fullProgress?.status]);

  const handleTogglePause = async () => {
    setPauseLoading(true);
    try {
      if (paused) {
        await adminService.resumeSync();
        setPaused(false);
        setPausedBy(null);
      } else {
        await adminService.pauseSync();
        setPaused(true);
      }
      await fetchPauseStatus();
    } catch (e) {
      console.error(e);
    } finally {
      setPauseLoading(false);
    }
  };

  const showInterruptResult = (msg: string, duration = 6000) => {
    setInterruptResult(msg);
    setTimeout(() => setInterruptResult(null), duration);
  };

  const handleInterrupt = async () => {
    setInterruptLoading(true);
    setInterruptResult(null);
    try {
      const res = await adminService.interruptSync();
      showInterruptResult(
        res.cycles_interrupted > 0
          ? `${res.cycles_interrupted} ciclo(s) interrompido(s) imediatamente.`
          : 'Nenhum ciclo estava em execução.'
      );
      setSelectedCycles(new Set());
      await fetchPauseStatus();
      await fetchCycles();
    } catch (e) {
      console.error(e);
      showInterruptResult('Erro ao interromper. Tente novamente.', 4000);
    } finally {
      setInterruptLoading(false);
    }
  };

  const handleInterruptSingle = async (cicloId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setInterruptingCycles(prev => new Set(prev).add(cicloId));
    try {
      await adminService.interruptCycle(cicloId);
      showInterruptResult(`Ciclo ${cicloId.slice(0, 8)}… interrompido.`);
      setSelectedCycles(prev => { const s = new Set(prev); s.delete(cicloId); return s; });
      await fetchCycles();
    } catch (e) {
      console.error(e);
      showInterruptResult('Erro ao interromper o ciclo.', 4000);
    } finally {
      setInterruptingCycles(prev => { const s = new Set(prev); s.delete(cicloId); return s; });
    }
  };

  const fetchCheckpoint = useCallback(async () => {
    setCheckpointLoading(true);
    try {
      const r = await adminService.getSnapshotConsolidationCheckpoint();
      setCheckpoint(r.resumable ? r : null);
    } catch (e) {
      console.error(e);
      setCheckpoint(null);
    } finally {
      setCheckpointLoading(false);
    }
  }, []);

  const handleStartFull = async (resume: boolean = false) => {
    setFullStarting(true);
    try {
      prevResultsCount.current = 0;
      const res = await adminService.triggerSnapshotConsolidationFull(
        resume ? !!checkpoint?.incremental : fullIncremental,
        resume
      );
      // Trata as respostas não-iniciadas: o backend devolve status especial
      if (res.status === 'already_running') {
        // Carrega o progresso atual (deve estar "running") e fecha o banner
        const p = await adminService.getSnapshotConsolidationFullProgress();
        setFullProgress(p);
        setCheckpoint(null);
        return;
      }
      if (res.status === 'no_checkpoint') {
        // O checkpoint sumiu entre a consulta e o clique — re-consulta e mantém o banner caso ainda haja outro
        await fetchCheckpoint();
        return;
      }
      // Caso normal (status === 'started' ou similar)
      const p = await adminService.getSnapshotConsolidationFullProgress();
      setFullProgress(p);
      setCheckpoint(null);
    } catch (e) {
      console.error(e);
    } finally {
      setFullStarting(false);
    }
  };

  // Ao abrir o modal, consulta se há ciclo incompleto pra retomar
  useEffect(() => {
    if (!showFullModal) return;
    fetchCheckpoint();
  }, [showFullModal, fetchCheckpoint]);

  const handleInterruptSelected = async () => {
    if (selectedCycles.size === 0) return;
    setInterruptLoading(true);
    try {
      const res = await adminService.interruptCyclesBatch(Array.from(selectedCycles));
      showInterruptResult(`${res.cycles_interrupted} ciclo(s) interrompido(s).`);
      setSelectedCycles(new Set());
      await fetchCycles();
    } catch (e) {
      console.error(e);
      showInterruptResult('Erro ao interromper os ciclos selecionados.', 4000);
    } finally {
      setInterruptLoading(false);
    }
  };

  const runningCycleIds = cycles.filter(c => c.status === 'iniciado').map(c => c.ciclo_id);
  const allRunningSelected = runningCycleIds.length > 0 && runningCycleIds.every(id => selectedCycles.has(id));

  const toggleSelectAll = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (allRunningSelected) {
      setSelectedCycles(new Set());
    } else {
      setSelectedCycles(new Set(runningCycleIds));
    }
  };

  const toggleSelectCycle = (cicloId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setSelectedCycles(prev => {
      const s = new Set(prev);
      if (s.has(cicloId)) s.delete(cicloId); else s.add(cicloId);
      return s;
    });
  };

  const toggleExpand = async (cicloId: string) => {
    const next = new Set(expanded);
    if (next.has(cicloId)) {
      next.delete(cicloId);
      setExpanded(next);
      return;
    }
    next.add(cicloId);
    setExpanded(next);
    // Always fetch fresh detail when expanding (never serve a stale cache)
    setLoadingDetail(prev => new Set(prev).add(cicloId));
    try {
      const d = await adminService.getSyncCycleDetail(cicloId);
      setDetails(prev => ({ ...prev, [cicloId]: d.events }));
    } catch (e) {
      console.error(e);
    } finally {
      setLoadingDetail(prev => { const s = new Set(prev); s.delete(cicloId); return s; });
    }
  };

  const pct = fullProgress && fullProgress.total > 0
    ? Math.round((fullProgress.current / fullProgress.total) * 100)
    : 0;

  const isRunning = fullProgress?.status === 'running';
  const isDone = fullProgress?.status === 'done';
  const isError = fullProgress?.status === 'error';

  return (
    <div className="space-y-4">

      {/* ── Modal Consolidação Full ───────────────────────────────────────── */}
      {showFullModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={() => { if (!isRunning) setShowFullModal(false); }} />
          <div className={`relative w-full max-w-4xl max-h-[92vh] flex flex-col rounded-2xl shadow-2xl border overflow-hidden ${isDark ? 'bg-gray-900 border-gray-700' : 'bg-white border-gray-200'}`}>

            {/* Header */}
            <div className={`flex items-center justify-between px-6 py-4 border-b ${isDark ? 'border-gray-700 bg-gray-800/60' : 'border-gray-200 bg-gray-50'}`}>
              <div className="flex items-center gap-3">
                <DatabaseZap className={`w-5 h-5 ${isDark ? 'text-indigo-400' : 'text-indigo-600'}`} />
                <div>
                  <h2 className={`text-base font-bold ${textPrimary}`}>Consolidar Snapshots — Todos os Eventos</h2>
                  {fullProgress?.triggered_by && (
                    <p className={`text-xs ${textSecondary} mt-0.5`}>Iniciado por: {fullProgress.triggered_by}</p>
                  )}
                </div>
              </div>
              <div className="flex items-center gap-3">
                {isRunning && (
                  <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300">
                    <Loader2 className="w-3 h-3 animate-spin" /> Em execução
                  </span>
                )}
                {isDone && (
                  <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300">
                    <CheckCheck className="w-3 h-3" /> Concluído
                  </span>
                )}
                {isError && (
                  <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300">
                    <XCircle className="w-3 h-3" /> Erro
                  </span>
                )}
                <button
                  onClick={() => { if (!isRunning) setShowFullModal(false); }}
                  disabled={isRunning}
                  className={`p-1.5 rounded-lg transition-colors disabled:opacity-30 ${isDark ? 'hover:bg-gray-700 text-gray-400' : 'hover:bg-gray-200 text-gray-500'}`}
                  title={isRunning ? 'Aguarde o término para fechar' : 'Fechar'}
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            </div>

            {/* Body */}
            <div className="flex-1 overflow-y-auto px-6 py-5 space-y-5">

              {/* Configuração inicial — só aparece quando idle */}
              {!fullProgress || fullProgress.status === 'idle' ? (
                <div className="space-y-5">
                  <p className={`text-sm ${textSecondary}`}>
                    Reconstrói o snapshot diário de vendas para <strong>todos os eventos ativos</strong> do ano corrente,
                    consultando diretamente Ativo e Magento. Garante que dados desatualizados sejam corrigidos.
                  </p>

                  {/* ── Banner de retomada (checkpoint) ─────────────────────── */}
                  {checkpointLoading && (
                    <div className={`flex items-center gap-2 px-4 py-3 rounded-lg border text-xs ${isDark ? 'bg-gray-800/60 border-gray-700 text-gray-400' : 'bg-gray-50 border-gray-200 text-gray-500'}`}>
                      <Loader2 className="w-3 h-3 animate-spin" /> Verificando consolidações anteriores…
                    </div>
                  )}

                  {!checkpointLoading && checkpoint && (
                    <div className={`rounded-xl border p-4 space-y-4 ${isDark ? 'bg-amber-900/15 border-amber-700/50' : 'bg-amber-50 border-amber-300'}`}>
                      {/* Cabeçalho explicativo */}
                      <div className="flex items-start gap-2">
                        <AlertTriangle className={`w-5 h-5 flex-shrink-0 mt-0.5 ${isDark ? 'text-amber-400' : 'text-amber-600'}`} />
                        <div className="flex-1 min-w-0">
                          <p className={`text-sm font-semibold ${isDark ? 'text-amber-200' : 'text-amber-900'}`}>
                            Há uma consolidação anterior que ficou incompleta
                          </p>
                          <p className={`text-xs mt-1 ${isDark ? 'text-amber-300/90' : 'text-amber-800'}`}>
                            Provavelmente o backend foi reiniciado ou a janela foi fechada antes do fim.
                            O progresso foi salvo no banco e você pode escolher como prosseguir.
                          </p>
                        </div>
                      </div>

                      {/* Mini-cards com o estado do ciclo interrompido */}
                      <div className={`grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs`}>
                        <div className={`rounded-lg px-3 py-2 ${isDark ? 'bg-gray-800/60' : 'bg-white/80'}`}>
                          <p className={isDark ? 'text-gray-400' : 'text-gray-500'}>Já processados</p>
                          <p className={`font-bold text-base ${isDark ? 'text-emerald-400' : 'text-emerald-600'}`}>{checkpoint.ok_count}</p>
                        </div>
                        <div className={`rounded-lg px-3 py-2 ${isDark ? 'bg-gray-800/60' : 'bg-white/80'}`}>
                          <p className={isDark ? 'text-gray-400' : 'text-gray-500'}>Com falha</p>
                          <p className={`font-bold text-base ${checkpoint.failed_count > 0 ? (isDark ? 'text-red-400' : 'text-red-600') : (isDark ? 'text-gray-300' : 'text-gray-600')}`}>{checkpoint.failed_count}</p>
                        </div>
                        <div className={`rounded-lg px-3 py-2 ${isDark ? 'bg-gray-800/60' : 'bg-white/80'}`}>
                          <p className={isDark ? 'text-gray-400' : 'text-gray-500'}>Modo original</p>
                          <p className={`font-bold text-base ${textPrimary}`}>{checkpoint.incremental ? 'Incremental' : 'Completa'}</p>
                        </div>
                        <div className={`rounded-lg px-3 py-2 ${isDark ? 'bg-gray-800/60' : 'bg-white/80'}`}>
                          <p className={isDark ? 'text-gray-400' : 'text-gray-500'}>Iniciada por</p>
                          <p className={`font-medium text-xs truncate ${textPrimary}`} title={checkpoint.triggered_by || '—'}>{checkpoint.triggered_by || '—'}</p>
                        </div>
                      </div>

                      {checkpoint.last_grupo && (
                        <p className={`text-xs ${isDark ? 'text-amber-300/80' : 'text-amber-800'}`}>
                          Último evento processado: <span className="font-mono font-semibold">{checkpoint.last_grupo}</span>
                          {checkpoint.last_processed_at && <> em {fmtDateTime(checkpoint.last_processed_at)}</>}.
                        </p>
                      )}

                      {/* Opção 1: Retomar — descrição clara do efeito */}
                      <div className={`rounded-lg border p-3 space-y-2 ${isDark ? 'border-emerald-700/50 bg-emerald-900/15' : 'border-emerald-300 bg-emerald-50'}`}>
                        <div className="flex items-center gap-2">
                          <PlayCircle className={`w-4 h-4 ${isDark ? 'text-emerald-400' : 'text-emerald-600'}`} />
                          <p className={`text-sm font-semibold ${isDark ? 'text-emerald-300' : 'text-emerald-800'}`}>Retomar de onde parou (recomendado)</p>
                        </div>
                        <ul className={`text-xs space-y-0.5 ml-6 list-disc ${isDark ? 'text-emerald-200/90' : 'text-emerald-900'}`}>
                          <li>Pula os <strong>{checkpoint.ok_count}</strong> eventos já processados com sucesso</li>
                          <li>Processa apenas os <strong>pendentes</strong> (mais rápido — economiza horas de Magento)</li>
                          <li>Mantém o mesmo ciclo: o relatório final mostra tudo junto</li>
                          <li>Usa o mesmo modo do ciclo original (<strong>{checkpoint.incremental ? 'Incremental' : 'Reconstrução completa'}</strong>)</li>
                        </ul>
                        <button
                          onClick={() => handleStartFull(true)}
                          disabled={fullStarting}
                          className={`w-full inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg font-semibold text-sm transition-colors disabled:opacity-60 ${isDark ? 'bg-emerald-600 hover:bg-emerald-500 text-white' : 'bg-emerald-600 hover:bg-emerald-700 text-white'}`}
                        >
                          {fullStarting ? <Loader2 className="w-4 h-4 animate-spin" /> : <PlayCircle className="w-4 h-4" />}
                          Retomar ({checkpoint.ok_count} pulados)
                        </button>
                      </div>

                      {/* Opção 2: Começar do zero — descrição do efeito */}
                      <div className={`rounded-lg border p-3 space-y-2 ${isDark ? 'border-gray-600 bg-gray-800/40' : 'border-gray-300 bg-white/60'}`}>
                        <div className="flex items-center gap-2">
                          <RotateCcw className={textSecondary + ' w-4 h-4'} />
                          <p className={`text-sm font-semibold ${textPrimary}`}>Começar do zero</p>
                        </div>
                        <ul className={`text-xs space-y-0.5 ml-6 list-disc ${textSecondary}`}>
                          <li>Ignora o progresso anterior e <strong>reprocessa todos os eventos</strong> de novo</li>
                          <li>Cria um novo ciclo (o anterior fica como abandonado no histórico)</li>
                          <li>Útil se você acha que os dados processados antes podem estar errados</li>
                          <li>Vai demorar bem mais — escolha o modo abaixo antes de iniciar</li>
                        </ul>
                        <button
                          onClick={() => setCheckpoint(null)}
                          disabled={fullStarting}
                          className={`w-full inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg font-medium text-sm transition-colors disabled:opacity-60 border ${isDark ? 'bg-transparent border-gray-600 hover:bg-gray-700/50 text-gray-200' : 'bg-white border-gray-300 hover:bg-gray-100 text-gray-700'}`}
                        >
                          <RotateCcw className="w-4 h-4" />
                          Descartar e começar do zero
                        </button>
                      </div>
                    </div>
                  )}

                  <div className={`rounded-xl border p-4 ${checkpoint ? 'opacity-50 pointer-events-none' : ''} ${isDark ? 'bg-gray-800/60 border-gray-700' : 'bg-gray-50 border-gray-200'}`}>
                    <p className={`text-sm font-medium ${textPrimary} mb-3`}>Modo de execução</p>
                    <div className="flex flex-col gap-2">
                      <label className={`flex items-start gap-3 p-3 rounded-lg cursor-pointer border transition-colors ${!fullIncremental ? (isDark ? 'border-indigo-500 bg-indigo-900/20' : 'border-indigo-400 bg-indigo-50') : (isDark ? 'border-gray-700 hover:border-gray-600' : 'border-gray-200 hover:border-gray-300')}`}>
                        <input type="radio" name="mode" checked={!fullIncremental} onChange={() => setFullIncremental(false)} className="mt-0.5 accent-indigo-500" />
                        <div>
                          <p className={`text-sm font-semibold ${textPrimary}`}>Reconstrução completa <span className="ml-1 text-xs font-normal text-amber-600 dark:text-amber-400">(recomendado)</span></p>
                          <p className={`text-xs ${textSecondary} mt-0.5`}>Apaga e regrava todo o histórico de cada evento. Corrige dados incorretos, lacunas e snapshots desatualizados.</p>
                        </div>
                      </label>
                      <label className={`flex items-start gap-3 p-3 rounded-lg cursor-pointer border transition-colors ${fullIncremental ? (isDark ? 'border-indigo-500 bg-indigo-900/20' : 'border-indigo-400 bg-indigo-50') : (isDark ? 'border-gray-700 hover:border-gray-600' : 'border-gray-200 hover:border-gray-300')}`}>
                        <input type="radio" name="mode" checked={fullIncremental} onChange={() => setFullIncremental(true)} className="mt-0.5 accent-indigo-500" />
                        <div>
                          <p className={`text-sm font-semibold ${textPrimary}`}>Incremental</p>
                          <p className={`text-xs ${textSecondary} mt-0.5`}>Busca apenas dias novos desde o último snapshot. Mais rápido, mas não corrige dados históricos incorretos.</p>
                        </div>
                      </label>
                    </div>
                  </div>
                  <div className={`flex items-start gap-2 px-4 py-3 rounded-lg border ${isDark ? 'bg-amber-900/20 border-amber-700/50 text-amber-300' : 'bg-amber-50 border-amber-200 text-amber-800'}`}>
                    <AlertTriangle className="w-4 h-4 flex-shrink-0 mt-0.5" />
                    <p className="text-xs">Esta operação pode levar vários minutos dependendo do número de eventos e da disponibilidade do Magento. Não feche esta janela durante a execução.</p>
                  </div>
                  <button
                    onClick={() => handleStartFull(false)}
                    disabled={fullStarting || !!checkpoint}
                    className={`w-full flex items-center justify-center gap-2 px-4 py-3 rounded-xl font-semibold text-sm transition-colors disabled:opacity-60 ${isDark ? 'bg-indigo-600 hover:bg-indigo-500 text-white' : 'bg-indigo-600 hover:bg-indigo-700 text-white'}`}
                  >
                    {fullStarting ? <Loader2 className="w-4 h-4 animate-spin" /> : <DatabaseZap className="w-4 h-4" />}
                    {fullStarting ? 'Iniciando...' : `Iniciar ${fullIncremental ? 'Incremental' : 'Reconstrução Completa'}`}
                  </button>
                </div>
              ) : (
                <>
                  {/* ── Estado: Preparando (fase de setup antes do total ser conhecido) ── */}
                  {isRunning && fullProgress.total === 0 ? (
                    <div className={`rounded-xl border p-5 space-y-3 ${isDark ? 'bg-indigo-900/15 border-indigo-700/50' : 'bg-indigo-50 border-indigo-200'}`}>
                      <div className="flex items-center gap-3">
                        <Loader2 className={`w-5 h-5 animate-spin flex-shrink-0 ${isDark ? 'text-indigo-300' : 'text-indigo-600'}`} />
                        <div className="flex-1 min-w-0">
                          <p className={`font-semibold text-sm ${isDark ? 'text-indigo-200' : 'text-indigo-900'}`}>Preparando consolidação…</p>
                          <p className={`text-xs mt-0.5 ${isDark ? 'text-indigo-300/90' : 'text-indigo-700'}`}>
                            {fullProgress.setup_step || 'Identificando eventos a processar…'}
                          </p>
                        </div>
                        <span className={`text-xs font-mono whitespace-nowrap ${isDark ? 'text-indigo-300/70' : 'text-indigo-700/70'}`}>
                          {fmtElapsed(fullProgress.started_at, null)}
                        </span>
                      </div>
                      <p className={`text-xs ${isDark ? 'text-indigo-300/70' : 'text-indigo-600/80'}`}>
                        Esta fase costuma levar 30-60s. A barra de progresso aparece assim que a lista de eventos é montada.
                      </p>
                    </div>
                  ) : (
                  <>
                  {/* ── Barra de progresso ───────────────────────────────────── */}
                  <div className={`rounded-xl border p-4 space-y-3 ${isDark ? 'bg-gray-800/60 border-gray-700' : 'bg-gray-50 border-gray-200'}`}>
                    <div className="flex items-center justify-between text-sm">
                      <span className={`font-medium ${textPrimary}`}>
                        {isRunning ? 'Processando...' : isDone ? 'Concluído!' : 'Erro na execução'}
                      </span>
                      <span className={`font-bold text-lg ${isDark ? 'text-indigo-400' : 'text-indigo-600'}`}>{pct}%</span>
                    </div>
                    <div className={`h-3 rounded-full overflow-hidden ${isDark ? 'bg-gray-700' : 'bg-gray-200'}`}>
                      <div
                        className={`h-full rounded-full transition-all duration-500 ${isDone ? 'bg-emerald-500' : isError ? 'bg-red-500' : 'bg-indigo-500'}`}
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                    <div className={`flex flex-wrap items-center gap-x-4 gap-y-1 text-xs ${textSecondary}`}>
                      <span className="flex items-center gap-1">
                        <TrendingUp className="w-3 h-3" />
                        {fullProgress.current} / {fullProgress.total > 0 ? fullProgress.total : '…'} eventos
                      </span>
                      <span className="flex items-center gap-1">
                        <Clock className="w-3 h-3" />
                        {isRunning
                          ? fmtElapsed(fullProgress.started_at, null)
                          : fmtElapsed(fullProgress.started_at, fullProgress.finished_at)}
                      </span>
                      <span className={`px-1.5 py-0.5 rounded text-xs ${isDark ? 'bg-gray-700 text-gray-300' : 'bg-gray-200 text-gray-600'}`}>
                        {fullProgress.incremental ? 'Incremental' : 'Completo'}
                      </span>
                    </div>
                  </div>

                  {/* ── Cards de contadores (5 com "Na fila") ─────────────────── */}
                  <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
                    {[
                      { label: 'OK', val: fullProgress.ok, color: 'emerald', Icon: CheckCircle2 },
                      { label: 'Falha', val: fullProgress.failed, color: 'red', Icon: XCircle },
                      { label: 'Pulado', val: fullProgress.skipped, color: 'gray', Icon: MinusCircle },
                      { label: 'Congelados', val: fullProgress.frozen, color: 'blue', Icon: Snowflake },
                      { label: 'Na fila', val: (fullProgress.grupos_pendentes?.length ?? 0), color: 'amber', Icon: Clock },
                    ].map(({ label, val, color, Icon }) => (
                      <div key={label} className={`rounded-xl border p-3 text-center ${isDark ? 'bg-gray-800/60 border-gray-700' : 'bg-white border-gray-200 shadow-sm'}`}>
                        <Icon className={`w-5 h-5 mx-auto mb-1 text-${color}-${isDark ? '400' : '500'}`} />
                        <p className={`text-2xl font-bold text-${color}-${isDark ? '400' : '600'}`}>{val}</p>
                        <p className={`text-xs ${textSecondary} mt-0.5`}>{label}</p>
                      </div>
                    ))}
                  </div>

                  {/* ── Em execução agora (paralelos) ─────────────────────────── */}
                  {isRunning && (fullProgress.em_execucao?.length ?? 0) > 0 && (
                    <div className={`rounded-xl border overflow-hidden ${isDark ? 'border-indigo-700/50 bg-indigo-900/15' : 'border-indigo-300 bg-indigo-50/60'}`}>
                      <div className={`flex items-center justify-between px-4 py-2.5 border-b ${isDark ? 'border-indigo-700/50' : 'border-indigo-200'}`}>
                        <p className={`text-xs font-semibold ${isDark ? 'text-indigo-200' : 'text-indigo-900'} flex items-center gap-1.5`}>
                          <Loader2 className="w-3.5 h-3.5 animate-spin" />
                          Em execução agora ({fullProgress.em_execucao!.length} em paralelo)
                        </p>
                      </div>
                      <ul className="divide-y divide-indigo-200/40 dark:divide-indigo-700/30">
                        {fullProgress.em_execucao!.map((ev) => (
                          <li key={ev.grupo} className="flex items-center justify-between px-4 py-2 text-xs">
                            <span className={`truncate ${textPrimary}`} title={ev.grupo}>{ev.grupo}</span>
                            <span className={`font-mono ml-3 whitespace-nowrap ${isDark ? 'text-indigo-300' : 'text-indigo-700'}`}>
                              {fmtElapsed(ev.started_at, null)}
                            </span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {/* ── Aguardando na fila ───────────────────────────────────── */}
                  {isRunning && (fullProgress.grupos_pendentes?.length ?? 0) > 0 && (
                    <details className={`rounded-xl border overflow-hidden ${isDark ? 'border-gray-700 bg-gray-800/40' : 'border-gray-200 bg-gray-50/60'}`}>
                      <summary className={`flex items-center justify-between px-4 py-2.5 cursor-pointer select-none text-xs font-semibold ${textPrimary} hover:bg-black/5 dark:hover:bg-white/5`}>
                        <span className="flex items-center gap-1.5">
                          <Clock className={`w-3.5 h-3.5 ${isDark ? 'text-amber-400' : 'text-amber-600'}`} />
                          Aguardando na fila ({fullProgress.grupos_pendentes!.length} restantes)
                        </span>
                        <span className={`text-xs font-normal ${textSecondary}`}>Clique para expandir</span>
                      </summary>
                      <div className="max-h-48 overflow-y-auto px-4 py-2 border-t border-gray-200 dark:border-gray-700">
                        <ul className={`space-y-1 text-xs ${textSecondary}`}>
                          {fullProgress.grupos_pendentes!.map((g) => (
                            <li key={g} className="truncate" title={g}>· {g}</li>
                          ))}
                        </ul>
                      </div>
                    </details>
                  )}
                  </>
                  )}

                  {/* ── Erro geral ───────────────────────────────────────────── */}
                  {isError && fullProgress.error && (
                    <div className={`flex items-start gap-2 px-4 py-3 rounded-lg border ${isDark ? 'bg-red-900/20 border-red-700/50 text-red-300' : 'bg-red-50 border-red-200 text-red-800'}`}>
                      <XCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
                      <p className="text-xs font-mono break-all">{fullProgress.error}</p>
                    </div>
                  )}

                  {/* ── Tabela de resultados ─────────────────────────────────── */}
                  {fullProgress.results.length > 0 && (
                    <div className={`rounded-xl border overflow-hidden ${isDark ? 'border-gray-700' : 'border-gray-200'}`}>
                      <div className={`flex items-center justify-between px-4 py-2.5 border-b ${isDark ? 'bg-gray-800/60 border-gray-700' : 'bg-gray-50 border-gray-200'}`}>
                        <p className={`text-xs font-semibold ${textPrimary}`}>Resultados por evento ({fullProgress.results.length})</p>
                        {isRunning && <span className={`text-xs ${textSecondary}`}>Atualiza em tempo real</span>}
                      </div>
                      <div className="overflow-y-auto max-h-64">
                        <table className="w-full text-xs">
                          <thead>
                            <tr className={`border-b sticky top-0 z-10 ${isDark ? 'bg-gray-800 border-gray-700 text-gray-400' : 'bg-gray-50 border-gray-200 text-gray-500'}`}>
                              <th className="py-2 px-3 text-left font-medium">Evento</th>
                              <th className="py-2 px-3 text-left font-medium">Status</th>
                              <th className="py-2 px-3 text-right font-medium">Antes</th>
                              <th className="py-2 px-3 text-right font-medium">Depois</th>
                              <th className="py-2 px-3 text-right font-medium">Duração</th>
                              <th className="py-2 px-3 text-left font-medium">Motivo / Erro</th>
                            </tr>
                          </thead>
                          <tbody>
                            {fullProgress.results.map((r, i) => (
                              <tr key={i} className={`border-b ${isDark ? 'border-gray-700/50 even:bg-gray-800/30' : 'border-gray-100 even:bg-gray-50/60'}`}>
                                <td className={`py-2 px-3 ${textPrimary} max-w-[200px] truncate`} title={r.grupo}>{r.grupo}</td>
                                <td className="py-2 px-3">
                                  {r.status === 'ok' && <span className="inline-flex items-center gap-1 text-emerald-600 dark:text-emerald-400 font-medium"><CheckCircle2 className="w-3 h-3" />OK</span>}
                                  {r.status === 'failed' && <span className="inline-flex items-center gap-1 text-red-600 dark:text-red-400 font-medium"><XCircle className="w-3 h-3" />Falha</span>}
                                  {r.status === 'skipped' && <span className="inline-flex items-center gap-1 text-gray-500 font-medium"><MinusCircle className="w-3 h-3" />Pulado</span>}
                                </td>
                                <td className={`py-2 px-3 text-right ${textSecondary}`}>{r.qtd_antes ?? '—'}</td>
                                <td className={`py-2 px-3 text-right ${textSecondary}`}>{r.qtd_depois ?? '—'}</td>
                                <td className={`py-2 px-3 text-right ${textSecondary}`}>{r.duracao_ms != null ? fmtDuration(r.duracao_ms) : '—'}</td>
                                <td className={`py-2 px-3 max-w-[220px] truncate ${r.status === 'failed' ? 'text-red-500 dark:text-red-400' : textSecondary}`} title={r.motivo ?? r.detalhes ?? ''}>
                                  {r.motivo || r.detalhes || '—'}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                        <div ref={resultsEndRef} />
                      </div>
                    </div>
                  )}

                  {/* ── Resumo final ─────────────────────────────────────────── */}
                  {isDone && (
                    <div className={`rounded-xl border p-5 space-y-3 ${isDark ? 'bg-emerald-900/20 border-emerald-700/50' : 'bg-emerald-50 border-emerald-200'}`}>
                      <div className="flex items-center gap-2">
                        <CheckCheck className={`w-5 h-5 ${isDark ? 'text-emerald-400' : 'text-emerald-600'}`} />
                        <p className={`font-bold text-sm ${isDark ? 'text-emerald-300' : 'text-emerald-800'}`}>Consolidação concluída com sucesso</p>
                      </div>
                      <div className={`grid grid-cols-2 sm:grid-cols-3 gap-3 text-xs ${isDark ? 'text-emerald-300' : 'text-emerald-800'}`}>
                        <div><span className="opacity-70">Total processados:</span><br /><strong className="text-base">{fullProgress.total}</strong> eventos</div>
                        <div><span className="opacity-70">Atualizados com sucesso:</span><br /><strong className="text-base text-emerald-600 dark:text-emerald-400">{fullProgress.ok}</strong></div>
                        <div><span className="opacity-70">Falhas:</span><br /><strong className={`text-base ${fullProgress.failed > 0 ? 'text-red-500' : ''}`}>{fullProgress.failed}</strong></div>
                        <div><span className="opacity-70">Congelados (não sincronizados):</span><br /><strong className="text-base">{fullProgress.frozen}</strong></div>
                        <div><span className="opacity-70">Tempo total:</span><br /><strong className="text-base">{fmtElapsed(fullProgress.started_at, fullProgress.finished_at)}</strong></div>
                        <div><span className="opacity-70">Modo:</span><br /><strong className="text-base">{fullProgress.incremental ? 'Incremental' : 'Reconstrução completa'}</strong></div>
                      </div>
                      {fullProgress.ciclo_id && (
                        <p className={`text-xs opacity-60 font-mono`}>Ciclo ID: {fullProgress.ciclo_id}</p>
                      )}
                      {fullProgress.failed > 0 && (
                        <div className={`mt-2 p-3 rounded-lg ${isDark ? 'bg-red-900/30 border border-red-700/50' : 'bg-red-50 border border-red-200'}`}>
                          <p className={`text-xs font-semibold mb-2 ${isDark ? 'text-red-300' : 'text-red-700'}`}>Eventos com falha:</p>
                          <ul className={`space-y-1 text-xs ${isDark ? 'text-red-300' : 'text-red-700'}`}>
                            {fullProgress.results.filter(r => r.status === 'failed').map((r, i) => (
                              <li key={i} className="flex items-start gap-1">
                                <XCircle className="w-3 h-3 flex-shrink-0 mt-0.5" />
                                <span><strong>{r.grupo}</strong>{r.motivo ? ` — ${r.motivo}` : ''}</span>
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </div>
                  )}

                  {/* Botão de nova execução */}
                  {(isDone || isError) && (
                    <button
                      onClick={() => { setFullProgress(null); prevResultsCount.current = 0; }}
                      className={`flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${isDark ? 'bg-gray-700 hover:bg-gray-600 text-gray-200' : 'bg-gray-100 hover:bg-gray-200 text-gray-700'}`}
                    >
                      <RotateCcw className="w-4 h-4" /> Nova execução
                    </button>
                  )}
                </>
              )}
            </div>
          </div>
        </div>
      )}

      {interruptResult && (
        <div className={`flex items-center gap-3 px-4 py-3 rounded-xl border ${isDark ? 'bg-red-900/20 border-red-700/50 text-red-300' : 'bg-red-50 border-red-200 text-red-800'}`}>
          <StopCircle className="w-4 h-4 flex-shrink-0" />
          <span className="text-sm">{interruptResult}</span>
        </div>
      )}
      {paused && (
        <div className={`flex items-center gap-3 px-4 py-3 rounded-xl border ${isDark ? 'bg-orange-900/20 border-orange-700/50 text-orange-300' : 'bg-orange-50 border-orange-200 text-orange-800'}`}>
          <PauseCircle className="w-5 h-5 flex-shrink-0" />
          <div className="flex-1 min-w-0">
            <span className="font-semibold">Execuções pausadas</span>
            {pausedBy && <span className="ml-2 text-sm opacity-80">por {pausedBy}</span>}
            <p className="text-xs opacity-70 mt-0.5">Os jobs em andamento terminarão o grupo atual e então pararão. Novos ciclos automáticos aguardarão.</p>
          </div>
          <button
            onClick={handleTogglePause}
            disabled={pauseLoading}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${isDark ? 'bg-orange-700 hover:bg-orange-600 text-white' : 'bg-orange-600 hover:bg-orange-700 text-white'} disabled:opacity-50`}
          >
            {pauseLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <PlayCircle className="w-4 h-4" />}
            Retomar
          </button>
        </div>
      )}
      {/* ── 3 cards de visão geral (Próximas atualizações, Resumo de hoje, Mapeamento de Kit) ── */}
      {overview && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">

          {/* Card 1 — Próximas atualizações agendadas */}
          <div className={`${cardBase} rounded-xl p-4`}>
            <div className="flex items-center gap-2 mb-3">
              <CalendarClock className={`w-5 h-5 ${isDark ? 'text-indigo-400' : 'text-indigo-600'}`} />
              <h3 className={`text-base font-semibold ${textPrimary}`}>Próximas atualizações</h3>
            </div>
            <ul className="space-y-2">
              {overview.scheduled_jobs.map(job => {
                const isTick = job.tipo === 'tick';
                const isSafetyNet = job.tipo === 'rede_seguranca';
                // Para "tick" (margem_safety) agora temos seconds_until real quando
                // _last_safety_tick já foi populado. Se ainda for null, exibimos "~Xmin"
                // como antes (texto extraído da descrição).
                const countdownText = job.seconds_until != null
                  ? `em ${fmtCountdown(job.seconds_until)}`
                  : isTick ? '~90min' : '—';
                return (
                  <li key={job.key} className={`flex items-start justify-between gap-2 px-2.5 py-2 rounded-lg ${isDark ? 'bg-gray-900/30' : 'bg-gray-50/60'}`}>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-1.5 flex-wrap">
                        <span className={`text-sm font-medium ${textPrimary} truncate`}>{job.label}</span>
                        {isSafetyNet && (
                          <span className={`text-[10px] px-1.5 py-0.5 rounded ${isDark ? 'bg-blue-900/40 text-blue-300' : 'bg-blue-100 text-blue-700'}`}>
                            rede de segurança
                          </span>
                        )}
                        {isTick && (
                          <span className={`text-[10px] px-1.5 py-0.5 rounded ${isDark ? 'bg-gray-700 text-gray-400' : 'bg-gray-200 text-gray-600'}`}>
                            tick
                          </span>
                        )}
                        {job.atrasado && (
                          <span
                            className="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300"
                            title={job.ultima_exec_iso
                              ? `Última execução: ${fmtDateTime(job.ultima_exec_iso)} (> 26h)`
                              : 'Nenhuma execução registrada ainda'}
                          >
                            <AlertTriangle className="w-3 h-3" />
                            atrasado
                          </span>
                        )}
                      </div>
                      <p className={`text-[11px] ${textSecondary} mt-0.5 truncate`} title={job.descricao}>{job.descricao}</p>
                    </div>
                    <div className="text-right shrink-0">
                      <div className={`text-sm font-mono ${textPrimary}`}>{countdownText}</div>
                      {job.next_run_iso && (
                        <div className={`text-[11px] ${textSecondary}`}>{fmtTimeBRT(job.next_run_iso)}</div>
                      )}
                    </div>
                  </li>
                );
              })}
            </ul>
            {/* "atualizado há Xs" — usa generated_at do payload + nowTick */}
            {overview.generated_at && (() => {
              const ageS = Math.max(0, Math.floor((nowTick - new Date(overview.generated_at).getTime()) / 1000));
              return (
                <p className={`text-[10px] ${textSecondary} mt-2 text-right`} title={`Snapshot servido em ${fmtTimeBRT(overview.generated_at)}`}>
                  atualizado há {ageS < 60 ? `${ageS}s` : ageS < 3600 ? `${Math.floor(ageS / 60)}min` : `${(ageS / 3600).toFixed(1)}h`}
                </p>
              );
            })()}
          </div>

          {/* Card 2 — Resumo de hoje */}
          <div className={`${cardBase} rounded-xl p-4`}>
            <div className="flex items-center gap-2 mb-3">
              <ListChecks className={`w-5 h-5 ${isDark ? 'text-emerald-400' : 'text-emerald-600'}`} />
              <h3 className={`text-base font-semibold ${textPrimary}`}>Resumo de hoje</h3>
            </div>
            <div className="grid grid-cols-2 gap-2 mb-3">
              <div className={`px-3 py-2 rounded-lg ${isDark ? 'bg-gray-900/30' : 'bg-gray-50/60'}`}>
                <div className={`text-[11px] ${textSecondary}`}>Eventos sincronizados</div>
                <div className={`text-xl font-bold ${textPrimary}`}>{overview.today_summary.eventos_sincronizados}</div>
              </div>
              <div className={`px-3 py-2 rounded-lg ${isDark ? 'bg-gray-900/30' : 'bg-gray-50/60'}`}>
                <div className={`text-[11px] ${textSecondary}`}>Último sync</div>
                <div className={`text-sm font-semibold ${textPrimary}`}>
                  {overview.today_summary.ultimo_sync_iso
                    ? fmtTimeBRT(overview.today_summary.ultimo_sync_iso)
                    : '—'}
                </div>
              </div>
            </div>
            <div className="flex flex-wrap gap-2 text-xs mb-3">
              {overview.today_summary.eventos_ok > 0 && (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-400">
                  <CheckCircle2 className="w-3 h-3" /> {overview.today_summary.eventos_ok} OK
                </span>
              )}
              {overview.today_summary.eventos_parcial > 0 && (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400">
                  <AlertTriangle className="w-3 h-3" /> {overview.today_summary.eventos_parcial} parcial
                </span>
              )}
              {overview.today_summary.eventos_falha > 0 && (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400">
                  <XCircle className="w-3 h-3" /> {overview.today_summary.eventos_falha} falha
                </span>
              )}
              {overview.today_summary.eventos_pulado > 0 && (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300">
                  <MinusCircle className="w-3 h-3" /> {overview.today_summary.eventos_pulado} pulado
                </span>
              )}
              {overview.today_summary.eventos_sincronizados === 0 && (
                <span className={`text-xs ${textSecondary}`}>Nenhum evento sincronizado hoje ainda.</span>
              )}
            </div>
            {overview.today_summary.historico_jobs.length > 0 && (
              <div>
                <div className={`text-[11px] font-medium ${textSecondary} mb-1`}>Últimas execuções (sincronizar_hoje)</div>
                <div className="flex items-end gap-1 h-10">
                  {overview.today_summary.historico_jobs.slice().reverse().map((h, idx) => {
                    const ratio = h.grupos_total > 0 ? h.grupos_ok / h.grupos_total : 0;
                    const color = ratio >= 0.95 ? 'bg-emerald-500' : ratio >= 0.8 ? 'bg-amber-500' : 'bg-red-500';
                    const heightPct = Math.max(15, Math.round(ratio * 100));
                    return (
                      <div
                        key={idx}
                        className={`flex-1 ${color} rounded-t opacity-80 hover:opacity-100 transition-opacity`}
                        style={{ height: `${heightPct}%` }}
                        title={`${fmtTimeBRT(h.started_at)} — ${h.grupos_ok}/${h.grupos_total} OK (${h.grupos_parcial} parcial, ${h.grupos_falha} falha) · ${fmtDuration(h.duration_ms)}`}
                      />
                    );
                  })}
                </div>
              </div>
            )}
          </div>

          {/* Card 3 — Mapeamento de Kit */}
          {(() => {
            const km = overview.kit_mapping;
            const statusCfg = km.status === 'critico'
              ? { cls: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400', label: 'Crítico', Icon: XCircle }
              : km.status === 'atencao'
                ? { cls: 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400', label: 'Atenção', Icon: AlertTriangle }
                : { cls: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-400', label: 'OK', Icon: CheckCircle2 };
            const StatusIcon = statusCfg.Icon;
            const coverageColor = km.cobertura_pct == null
              ? 'bg-gray-400'
              : km.cobertura_pct >= 95 ? 'bg-emerald-500'
              : km.cobertura_pct >= 85 ? 'bg-amber-500'
              : 'bg-red-500';
            return (
              <div className={`${cardBase} rounded-xl p-4`}>
                <div className="flex items-center justify-between gap-2 mb-3">
                  <div className="flex items-center gap-2">
                    <Package className={`w-5 h-5 ${isDark ? 'text-purple-400' : 'text-purple-600'}`} />
                    <h3 className={`text-base font-semibold ${textPrimary}`}>Mapeamento de Kit</h3>
                  </div>
                  <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium ${statusCfg.cls}`}>
                    <StatusIcon className="w-3 h-3" />
                    {statusCfg.label}
                  </span>
                </div>

                <div className="space-y-2 text-sm">
                  <div className="flex items-center justify-between">
                    <span className={textSecondary}>Última atualização</span>
                    <span className={`font-medium ${textPrimary}`}>
                      {km.ultima_atualizacao_iso
                        ? <>há {km.idade_horas?.toFixed(1)}h</>
                        : '—'}
                    </span>
                  </div>

                  <div>
                    <div className="flex items-center justify-between mb-1">
                      <span className={textSecondary}>Cobertura</span>
                      <span className={`font-medium ${textPrimary}`}>
                        {km.cobertura_pct != null ? `${km.cobertura_pct.toFixed(1)}%` : '—'}
                      </span>
                    </div>
                    <div className={`h-2 rounded-full overflow-hidden ${isDark ? 'bg-gray-700' : 'bg-gray-200'}`}>
                      <div
                        className={`h-full ${coverageColor} transition-all`}
                        style={{ width: `${km.cobertura_pct ?? 0}%` }}
                      />
                    </div>
                    <p className={`text-[11px] ${textSecondary} mt-1`}>
                      {km.bundles_com_snapshot} de {km.bundles_esperados} bundles com receita líquida
                    </p>
                  </div>

                  {km.kits_sem_configuracao > 0 && (
                    <a
                      href="/admin/kit-config"
                      className={`flex items-center gap-2 px-3 py-2 rounded-lg border transition-colors mt-2 ${
                        isDark
                          ? 'bg-amber-900/20 border-amber-700/50 text-amber-300 hover:bg-amber-900/30'
                          : 'bg-amber-50 border-amber-200 text-amber-800 hover:bg-amber-100'
                      }`}
                      title="Abrir página de Mapeamento de Kits"
                    >
                      <AlertTriangle className="w-4 h-4 flex-shrink-0" />
                      <span className="text-xs flex-1">
                        <strong>{km.kits_sem_configuracao}</strong> kits sem configuração
                      </span>
                      <ArrowRight className="w-3.5 h-3.5 flex-shrink-0" />
                    </a>
                  )}
                </div>
              </div>
            );
          })()}

        </div>
      )}

      {(() => {
        const last04h = cycles.find(c => c.job_name === 'consolidacao_diaria_04h');
        const ref = last04h?.concluido_em || last04h?.iniciado_em || last04h?.ultima_atividade;
        const ageH = ref ? (Date.now() - new Date(ref).getTime()) / 3_600_000 : null;
        // Só rotula como "atrasado" depois que o carregamento inicial terminou,
        // para não exibir falso negativo enquanto `cycles` ainda está vazio.
        const late = !loading && (!last04h || (ageH != null && ageH > 26));
        const sub = details[last04h?.ciclo_id || ''] || [];
        const subSteps = sub.filter(e => e.nivel === 'grupo' && e.grupo);
        const detailLoaded = !!last04h && (sub.length > 0 || !loadingDetail.has(last04h.ciclo_id));
        const detailFetching = !!last04h && loadingDetail.has(last04h.ciclo_id);
        const stepsByName = new Map<string, typeof sub[number]>();
        for (const s of subSteps) {
          const prev = stepsByName.get(s.grupo!);
          if (!prev || new Date(s.created_at) > new Date(prev.created_at)) {
            stepsByName.set(s.grupo!, s);
          }
        }
        const ORDER = [
          'snapshot_diario_batch',
          'consolidar_curvas_historicas_batch',
          'sincronizar_hoje_batch',
          'sincronizar_margem_bundle_rev_batch',
          'sync_event_log_cleanup',
        ];
        return (
          <div className={`${cardBase} rounded-xl p-4`}>
            <div className="flex flex-wrap items-start justify-between gap-3 mb-2">
              <div className="flex items-start gap-2">
                <Clock className={`w-5 h-5 mt-0.5 ${late ? 'text-amber-500' : isDark ? 'text-indigo-400' : 'text-indigo-600'}`} />
                <div>
                  <h3 className={`text-base font-semibold ${textPrimary} flex items-center gap-2`}>
                    Job agendado das 04h
                    {last04h && <StatusBadge status={last04h.status} />}
                    {late && (
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300">
                        <AlertTriangle className="w-3 h-3" />
                        {last04h ? 'Atrasado' : 'Sem execução registrada'}
                      </span>
                    )}
                  </h3>
                  <p className={`text-xs ${textSecondary} mt-0.5`}>
                    {last04h ? (
                      <>
                        Última execução: {fmtDateTime(last04h.concluido_em || last04h.iniciado_em)}
                        {last04h.duracao_ms != null && <> · duração {fmtDuration(last04h.duracao_ms)}</>}
                        {ageH != null && <> · há {ageH < 1 ? `${Math.round(ageH * 60)}min` : `${ageH.toFixed(1)}h`}</>}
                      </>
                    ) : (
                      'Nenhum ciclo registrado ainda. O próximo job está agendado para as 04h BRT.'
                    )}
                  </p>
                </div>
              </div>
              {last04h && (
                <button
                  onClick={() => toggleExpand(last04h.ciclo_id)}
                  className={`text-xs px-2.5 py-1 rounded-lg border transition-colors ${isDark ? 'border-gray-600 hover:bg-gray-700 text-gray-300' : 'border-gray-300 hover:bg-gray-50 text-gray-700'}`}
                  title="Ver detalhes completos no histórico abaixo"
                >
                  {expanded.has(last04h.ciclo_id) ? 'Ocultar detalhes' : 'Ver detalhes'}
                </button>
              )}
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-2 mt-3">
              {ORDER.map(stepName => {
                const ev = stepsByName.get(stepName);
                const label = JOB_LABELS[stepName] || stepName;
                // Tri-state: (a) detalhe ainda não carregado → "Aguardando";
                // (b) detalhe carregado e sub-passo presente → status real;
                // (c) detalhe carregado e sub-passo ausente → "Não rodou".
                const showPending = !last04h || !detailLoaded;
                return (
                  <div
                    key={stepName}
                    className={`flex items-center justify-between gap-2 px-3 py-2 rounded-lg border text-xs ${
                      isDark ? 'border-gray-700 bg-gray-900/30' : 'border-gray-200 bg-gray-50/60'
                    }`}
                    title={ev?.detalhes || (showPending ? 'Carregando detalhe…' : (ev ? '' : 'Não executado nesta janela'))}
                  >
                    <span className={`truncate ${textPrimary}`}>{label}</span>
                    {showPending ? (
                      <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium ${isDark ? 'bg-gray-700 text-gray-400' : 'bg-gray-200 text-gray-600'}`}>
                        <Loader2 className="w-3 h-3 animate-spin" />
                        Carregando
                      </span>
                    ) : ev ? (
                      <StatusBadge status={ev.status} />
                    ) : (
                      <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium ${isDark ? 'bg-gray-700 text-gray-400' : 'bg-gray-200 text-gray-600'}`}>
                        <MinusCircle className="w-3 h-3" />
                        Não rodou
                      </span>
                    )}
                  </div>
                );
              })}
            </div>
            {last04h && !detailLoaded && !detailFetching && (
              <p className={`text-[11px] ${textSecondary} mt-2`}>
                Carregando detalhe dos sub-passos…
              </p>
            )}
          </div>
        );
      })()}

      <div className={`${cardBase} rounded-xl p-4`}>
        <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
          <div>
            <h3 className={`text-lg font-semibold ${textPrimary} flex items-center gap-2`}>
              <Activity className="w-5 h-5" />
              Ciclos de sincronização
            </h3>
            <p className={`text-xs ${textSecondary} mt-0.5`}>
              Histórico dos jobs de sincronização (retenção 30 dias). Atualiza a cada 10s.
            </p>
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            <button
              onClick={() => { setShowFullModal(true); }}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                isDark ? 'bg-indigo-700 hover:bg-indigo-600 text-white' : 'bg-indigo-600 hover:bg-indigo-700 text-white'
              }`}
              title="Consolidar snapshots de todos os eventos com progresso em tempo real"
            >
              <DatabaseZap className="w-4 h-4" />
              Consolidar Snapshots
            </button>
            <select
              value={filterJob}
              onChange={(e) => setFilterJob(e.target.value)}
              className={selectClass}
            >
              <option value="">Todos os jobs</option>
              <option value="consolidacao_diaria_04h">Job agendado das 04h</option>
              <option value="atualizar_hoje">Atualizar Hoje (manual)</option>
              <option value="sincronizar_hoje_batch">Sincronização de hoje</option>
              <option value="snapshot_diario_batch">Snapshot diário</option>
              <option value="consolidar_vendas_grupo">Consolidação por grupo</option>
              <option value="consolidar_full_manual">Reconsolidar Todos (manual)</option>
            </select>
            <select
              value={filterStatus}
              onChange={(e) => setFilterStatus(e.target.value)}
              className={selectClass}
            >
              <option value="">Todos os status</option>
              <option value="concluido">Concluído</option>
              <option value="ok">OK</option>
              <option value="parcial">Parcial</option>
              <option value="falha">Falha</option>
              <option value="iniciado">Em execução</option>
              <option value="interrompido">Interrompido</option>
            </select>
            <button
              onClick={handleTogglePause}
              disabled={pauseLoading || interruptLoading}
              title={paused ? 'Retomar execuções' : 'Pausar execuções entre grupos'}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors disabled:opacity-50 ${
                paused
                  ? isDark ? 'bg-emerald-700 hover:bg-emerald-600 text-white' : 'bg-emerald-600 hover:bg-emerald-700 text-white'
                  : isDark ? 'bg-orange-700/80 hover:bg-orange-600 text-white' : 'bg-orange-500 hover:bg-orange-600 text-white'
              }`}
            >
              {pauseLoading
                ? <Loader2 className="w-4 h-4 animate-spin" />
                : paused
                  ? <PlayCircle className="w-4 h-4" />
                  : <PauseCircle className="w-4 h-4" />
              }
              {paused ? 'Retomar' : 'Pausar'}
            </button>
            <button
              onClick={handleInterrupt}
              disabled={pauseLoading || interruptLoading}
              title="Interromper imediatamente — marca ciclos em execução como interrompido no banco"
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors disabled:opacity-50 ${
                isDark ? 'bg-red-700/80 hover:bg-red-600 text-white' : 'bg-red-500 hover:bg-red-600 text-white'
              }`}
            >
              {interruptLoading
                ? <Loader2 className="w-4 h-4 animate-spin" />
                : <StopCircle className="w-4 h-4" />
              }
              Interromper
            </button>
            <button
              onClick={() => { setLoading(true); fetchCycles(); }}
              disabled={loading}
              className={`p-1.5 rounded-lg ${isDark ? 'bg-gray-700 hover:bg-gray-600 text-gray-300' : 'bg-gray-100 hover:bg-gray-200 text-gray-700'} transition-colors disabled:opacity-50`}
              title="Atualizar agora"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            </button>
          </div>
        </div>

        {loading && cycles.length === 0 ? (
          <div className={`text-center py-12 ${textSecondary}`}>
            <Loader2 className="w-6 h-6 mx-auto animate-spin mb-2" />
            Carregando ciclos...
          </div>
        ) : cycles.length === 0 ? (
          <div className={`text-center py-12 ${textSecondary}`}>
            Nenhum ciclo de sincronização registrado ainda.
          </div>
        ) : (
          <div className="overflow-x-auto">
            {selectedCycles.size > 0 && (
              <div className={`flex items-center gap-3 mb-3 px-3 py-2 rounded-lg border ${isDark ? 'bg-gray-700/60 border-gray-600' : 'bg-blue-50 border-blue-200'}`}>
                <span className={`text-sm font-medium ${isDark ? 'text-gray-200' : 'text-blue-800'}`}>
                  {selectedCycles.size} ciclo(s) selecionado(s)
                </span>
                <button
                  onClick={handleInterruptSelected}
                  disabled={interruptLoading}
                  className={`flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-medium transition-colors disabled:opacity-50 ${isDark ? 'bg-red-700 hover:bg-red-600 text-white' : 'bg-red-500 hover:bg-red-600 text-white'}`}
                >
                  {interruptLoading ? <Loader2 className="w-3 h-3 animate-spin" /> : <StopCircle className="w-3 h-3" />}
                  Interromper selecionados
                </button>
                <button
                  onClick={(e) => { e.stopPropagation(); setSelectedCycles(new Set()); }}
                  className={`text-xs ${isDark ? 'text-gray-400 hover:text-gray-200' : 'text-gray-500 hover:text-gray-700'}`}
                >
                  Limpar seleção
                </button>
              </div>
            )}
            <table className="w-full text-sm">
              <thead>
                <tr className={`text-left ${textSecondary} border-b ${isDark ? 'border-gray-700' : 'border-gray-200'}`}>
                  <th className="py-2 pr-2 w-6">
                    {runningCycleIds.length > 0 && (
                      <input
                        type="checkbox"
                        checked={allRunningSelected}
                        onChange={() => {}}
                        onClick={toggleSelectAll}
                        className="w-3.5 h-3.5 rounded cursor-pointer accent-red-500"
                        title="Selecionar todos em execução"
                      />
                    )}
                  </th>
                  <th className="py-2 pr-2 w-6"></th>
                  <th className="py-2 pr-3">Job</th>
                  <th className="py-2 pr-3">Início</th>
                  <th className="py-2 pr-3">Duração</th>
                  <th className="py-2 pr-3">Status</th>
                  <th className="py-2 pr-3">Grupos</th>
                  <th className="py-2 pr-3">Motivo / detalhes</th>
                  <th className="py-2 w-8"></th>
                </tr>
              </thead>
              <tbody>
                {cycles.map(c => {
                  const isOpen = expanded.has(c.ciclo_id);
                  const isLoadingDetail = loadingDetail.has(c.ciclo_id);
                  const cycleDetails = details[c.ciclo_id];
                  const isRunning = c.status === 'iniciado';
                  const isSelected = selectedCycles.has(c.ciclo_id);
                  const isInterruptingThis = interruptingCycles.has(c.ciclo_id);
                  return (
                    <React.Fragment key={c.ciclo_id}>
                      <tr
                        onClick={() => toggleExpand(c.ciclo_id)}
                        className={`cursor-pointer border-b ${isDark ? 'border-gray-700/50 hover:bg-gray-700/30' : 'border-gray-100 hover:bg-gray-50'} ${isSelected ? isDark ? 'bg-red-900/10' : 'bg-red-50/60' : ''}`}
                      >
                        <td className="py-2 pr-2" onClick={e => e.stopPropagation()}>
                          {isRunning ? (
                            <input
                              type="checkbox"
                              checked={isSelected}
                              onChange={() => {}}
                              onClick={(e) => toggleSelectCycle(c.ciclo_id, e)}
                              className="w-3.5 h-3.5 rounded cursor-pointer accent-red-500"
                            />
                          ) : null}
                        </td>
                        <td className="py-2 pr-2">
                          {isOpen ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
                        </td>
                        <td className={`py-2 pr-3 ${textPrimary}`}>
                          {JOB_LABELS[c.job_name] || c.job_name}
                        </td>
                        <td className={`py-2 pr-3 ${textSecondary}`}>
                          <span className="inline-flex items-center gap-1">
                            <Clock className="w-3 h-3" />
                            {fmtDateTime(c.iniciado_em || c.ultima_atividade)}
                          </span>
                        </td>
                        <td className={`py-2 pr-3 ${textSecondary}`}>{fmtDuration(c.duracao_ms)}</td>
                        <td className="py-2 pr-3"><StatusBadge status={c.status} /></td>
                        <td className={`py-2 pr-3 ${textSecondary}`}>
                          {c.total_grupos > 0 ? (
                            <span>
                              <span className={textPrimary}>{c.ok}</span>
                              {' OK'}
                              {c.parcial > 0 && <span className="text-amber-500"> · {c.parcial} parcial</span>}
                              {c.falha > 0 && <span className="text-red-500"> · {c.falha} falha</span>}
                              {c.pulado > 0 && <span> · {c.pulado} pulado</span>}
                              <span className={textSecondary}> / {c.total_grupos}</span>
                            </span>
                          ) : (
                            <span className={textSecondary}>—</span>
                          )}
                        </td>
                        <td className={`py-2 pr-3 ${textSecondary} max-w-md truncate`}>
                          {c.motivo ? (MOTIVO_LABELS[c.motivo] || c.motivo) : (c.detalhes || '—')}
                        </td>
                        <td className="py-2" onClick={e => e.stopPropagation()}>
                          {isRunning && (
                            <button
                              onClick={(e) => handleInterruptSingle(c.ciclo_id, e)}
                              disabled={isInterruptingThis}
                              title="Interromper este ciclo"
                              className={`p-1 rounded transition-colors ${isDark ? 'text-red-400 hover:bg-red-900/40 hover:text-red-300' : 'text-red-500 hover:bg-red-100 hover:text-red-700'} disabled:opacity-40`}
                            >
                              {isInterruptingThis
                                ? <Loader2 className="w-4 h-4 animate-spin" />
                                : <StopCircle className="w-4 h-4" />
                              }
                            </button>
                          )}
                        </td>
                      </tr>
                      {isOpen && (
                        <tr className={isDark ? 'bg-gray-900/40' : 'bg-gray-50/60'}>
                          <td colSpan={9} className="p-3">
                            {isLoadingDetail ? (
                              <div className={`text-center py-4 ${textSecondary}`}>
                                <Loader2 className="w-4 h-4 inline animate-spin mr-2" />
                                Carregando eventos...
                              </div>
                            ) : !cycleDetails || cycleDetails.length === 0 ? (
                              <div className={`text-center py-4 ${textSecondary}`}>Sem eventos registrados.</div>
                            ) : (
                              <DetailTable
                                cycle={c}
                                events={cycleDetails}
                                isDark={isDark}
                                textPrimary={textPrimary}
                                textSecondary={textSecondary}
                                onRefresh={() => refreshDetail(c.ciclo_id)}
                              />
                            )}
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};

interface DetailTableProps {
  cycle: SyncCycle;
  events: SyncEvent[];
  isDark: boolean;
  textPrimary: string;
  textSecondary: string;
  onRefresh: () => void;
}

function DetailTable({ cycle, events, isDark, textPrimary, textSecondary, onRefresh }: DetailTableProps) {
  const cycleFinished = cycle.status !== 'iniciado';

  // For completed cycles: hide ciclo-level "iniciado" entries (they're just
  // start markers — the real result is the terminal ciclo event).
  const visibleEvents = cycleFinished
    ? events.filter(ev => !(ev.nivel === 'ciclo' && ev.status === 'iniciado'))
    : events;

  // Safety net: any remaining 'iniciado' event must never show "Em execução"
  // when the cycle is finished (guards against timing edge cases where the
  // filter above doesn't fire before the re-render). Also softens the ciclo
  // "iniciado" start-marker for still-running cycles.
  const displayEvents = visibleEvents.map(ev => {
    if (ev.status !== 'iniciado') return ev;
    if (cycleFinished) return { ...ev, status: 'inicio' };          // cycle done → neutral
    if (ev.nivel === 'ciclo') return { ...ev, status: 'inicio' };   // running, ciclo start-marker → neutral
    return ev;
  });

  return (
    <div className="overflow-x-auto">
      <div className={`flex items-center justify-between text-xs ${textSecondary} mb-2`}>
        <span>
          ID do ciclo: <code className="font-mono">{cycle.ciclo_id}</code>
        </span>
        <button
          onClick={onRefresh}
          title="Recarregar eventos deste ciclo"
          className={`inline-flex items-center gap-1 px-2 py-0.5 rounded ${isDark ? 'hover:bg-gray-700 text-gray-400 hover:text-gray-200' : 'hover:bg-gray-200 text-gray-500 hover:text-gray-700'} transition-colors`}
        >
          <RefreshCw className="w-3 h-3" />
          Recarregar
        </button>
      </div>
      {displayEvents.length === 0 ? (
        <div className={`text-center py-3 ${textSecondary} text-xs`}>
          Sem eventos de grupo registrados.
        </div>
      ) : (
        <table className="w-full text-xs">
          <thead>
            <tr className={`text-left ${textSecondary} border-b ${isDark ? 'border-gray-700' : 'border-gray-200'}`}>
              <th className="py-1.5 pr-2">Horário</th>
              <th className="py-1.5 pr-2">Nível</th>
              <th className="py-1.5 pr-2">Grupo</th>
              <th className="py-1.5 pr-2">Fonte</th>
              <th className="py-1.5 pr-2">Status</th>
              <th className="py-1.5 pr-2">Qtd</th>
              <th className="py-1.5 pr-2">Duração</th>
              <th className="py-1.5 pr-2">Motivo / Detalhes</th>
            </tr>
          </thead>
          <tbody>
            {displayEvents.map(ev => (
              <tr key={ev.id} className={`border-b ${isDark ? 'border-gray-700/30' : 'border-gray-100'}`}>
                <td className={`py-1.5 pr-2 ${textSecondary}`}>{fmtDateTime(ev.created_at)}</td>
                <td className={`py-1.5 pr-2 ${textSecondary}`}>{ev.nivel}</td>
                <td className={`py-1.5 pr-2 ${textPrimary}`}>{ev.grupo || '—'}</td>
                <td className={`py-1.5 pr-2 ${textSecondary}`}>{ev.fonte || '—'}</td>
                <td className="py-1.5 pr-2">
                  <StatusBadge status={ev.status} spinning={ev.status === 'iniciado' && cycle.status === 'iniciado'} />
                </td>
                <td className={`py-1.5 pr-2 ${textSecondary}`}>
                  {ev.qtd_antes != null || ev.qtd_depois != null ? (
                    <>{ev.qtd_antes ?? '?'} → {ev.qtd_depois ?? '?'}</>
                  ) : '—'}
                </td>
                <td className={`py-1.5 pr-2 ${textSecondary}`}>{fmtDuration(ev.duracao_ms)}</td>
                <td className={`py-1.5 pr-2 ${textSecondary} max-w-xl`}>
                  {ev.motivo && (
                    <span className="font-medium">{MOTIVO_LABELS[ev.motivo] || ev.motivo}</span>
                  )}
                  {ev.motivo && ev.detalhes && ' — '}
                  {ev.detalhes && <span className="break-words">{ev.detalhes}</span>}
                  {!ev.motivo && !ev.detalhes && '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

export default SincronizacoesPanel;
