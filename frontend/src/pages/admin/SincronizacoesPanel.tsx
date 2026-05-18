import React, { useEffect, useState, useCallback, useRef } from 'react';
import { adminService } from '../../services/api';
import { useTheme } from '../../context/ThemeContext';
import {
  RefreshCw, ChevronDown, ChevronRight, CheckCircle2, AlertTriangle,
  XCircle, MinusCircle, Clock, Activity, Loader2, PauseCircle, PlayCircle,
  StopCircle, ArrowRight
} from 'lucide-react';

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
  sincronizar_hoje_batch:   'Sincronização de hoje',
  snapshot_diario_batch:    'Snapshot diário',
  consolidar_vendas_grupo:  'Consolidação por grupo',
  atualizar_hoje:           'Atualizar Hoje (manual)',
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
  const [interruptLoading, setInterruptLoading] = useState(false);
  const [interruptResult, setInterruptResult] = useState<string | null>(null);
  const [selectedCycles, setSelectedCycles] = useState<Set<string>>(new Set());
  const [interruptingCycles, setInterruptingCycles] = useState<Set<string>>(new Set());

  // Track previous cycle states to detect "iniciado → final" transitions
  const prevCyclesRef = useRef<SyncCycle[]>([]);
  // Use a ref for expanded so fetchCycles can access it without being in deps
  const expandedRef = useRef<Set<string>>(new Set());

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
    try {
      const d = await adminService.getSyncCycleDetail(cicloId);
      setDetails(prev => ({ ...prev, [cicloId]: d.events }));
    } catch (e) {
      console.error('detail refresh failed:', e);
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

  useEffect(() => {
    setLoading(true);
    fetchCycles();
    fetchPauseStatus();
    // Poll every 10s for better real-time feel (was 30s)
    const it = setInterval(() => { fetchCycles(); fetchPauseStatus(); }, 10000);
    return () => clearInterval(it);
  }, [fetchCycles, fetchPauseStatus]);

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

  return (
    <div className="space-y-4">
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
            <select
              value={filterJob}
              onChange={(e) => setFilterJob(e.target.value)}
              className={selectClass}
            >
              <option value="">Todos os jobs</option>
              <option value="atualizar_hoje">Atualizar Hoje (manual)</option>
              <option value="sincronizar_hoje_batch">Sincronização de hoje</option>
              <option value="snapshot_diario_batch">Snapshot diário</option>
              <option value="consolidar_vendas_grupo">Consolidação por grupo</option>
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

  // For completed cycles: hide ciclo-level "iniciado" entries — they're redundant
  // (the cycle status is shown in the parent row) and confuse the status column
  // by showing "Em execução" after the cycle is already done.
  const visibleEvents = cycleFinished
    ? events.filter(ev => !(ev.nivel === 'ciclo' && ev.status === 'iniciado'))
    : events;

  // For running cycles that have a ciclo-level "iniciado" entry, normalize its
  // display to avoid duplicate "Em execução" — we use a softer "inicio" status
  const displayEvents = visibleEvents.map(ev =>
    (ev.nivel === 'ciclo' && ev.status === 'iniciado' && !cycleFinished)
      ? { ...ev, status: 'inicio' }
      : ev
  );

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
