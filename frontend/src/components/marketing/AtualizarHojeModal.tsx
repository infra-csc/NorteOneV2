import React, { useEffect, useRef, useState } from 'react';
import {
  X, CheckCircle, XCircle, AlertTriangle, Loader2,
  Database, Zap, Save, RotateCcw, Archive, Clock, Wifi,
} from 'lucide-react';

export type SyncStatus =
  | 'loading' | 'success' | 'partial' | 'frozen'
  | 'failed' | 'error' | 'busy' | 'cooldown';

export interface SyncResult {
  status: string;
  hoje_ativo: number;
  hoje_magento: number;
  hoje_total: number;
  total_acumulado: number;
  media_7d: number;
  media_14d: number;
  ativo_ok?: boolean;
  magento_ok?: boolean;
  fontes_indisponiveis?: string[];
  ultima_atualizacao?: string;
  snapshot_bridge?: boolean;
  snapshot_atualizado_em?: string | null;
  magento_ultimo_conhecido?: number | null;
  magento_ultimo_data?: string | null;
}

interface Props {
  open: boolean;
  status: SyncStatus;
  result?: SyncResult | null;
  errorMsg?: string | null;
  onClose: () => void;
  startTime?: number;
}

const fmt = (n: number) => n.toLocaleString('pt-BR');
const fmtSec = (ms: number) => (ms / 1000).toFixed(1) + 's';

function useElapsed(active: boolean, startTime?: number) {
  const [elapsed, setElapsed] = useState(0);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const origin = useRef(startTime ?? Date.now());

  useEffect(() => {
    origin.current = startTime ?? Date.now();
  }, [startTime]);

  useEffect(() => {
    if (active) {
      origin.current = startTime ?? Date.now();
      setElapsed(0);
      intervalRef.current = setInterval(() => {
        setElapsed(Date.now() - origin.current);
      }, 100);
    } else {
      if (intervalRef.current) clearInterval(intervalRef.current);
    }
    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, [active]);

  return elapsed;
}

function ScanBar({ color = 'blue' }: { color?: 'blue' | 'amber' | 'red' }) {
  const c = color === 'amber' ? 'via-amber-400' : color === 'red' ? 'via-red-400' : 'via-blue-400';
  return (
    <div className="relative overflow-hidden h-1 rounded-full bg-gray-200 dark:bg-gray-700">
      <style>{`
        @keyframes ah-scan{0%{transform:translateX(-150%)}100%{transform:translateX(450%)}}
        @keyframes ah-cd{from{width:100%}to{width:0%}}
      `}</style>
      <div
        className={`absolute h-full w-2/5 bg-gradient-to-r from-transparent ${c} to-transparent`}
        style={{ animation: 'ah-scan 1.4s ease-in-out infinite' }}
      />
    </div>
  );
}

function SourceCard({
  label, subtitle, icon, phase, value, ok, viaSnapshot, elapsedMs, timeout,
  lastKnown, lastKnownDate,
}: {
  label: string;
  subtitle: string;
  icon: React.ReactNode;
  phase: 'pending' | 'running' | 'done' | 'error';
  value?: number;
  ok?: boolean;
  viaSnapshot?: boolean;
  elapsedMs?: number;
  timeout?: number;
  lastKnown?: number | null;
  lastKnownDate?: string | null;
}) {
  const isRunning = phase === 'running';
  const isDone = phase === 'done';
  const isError = phase === 'error';
  const isPending = phase === 'pending';

  const borderClass = isPending
    ? 'border-gray-200 dark:border-gray-700 opacity-40'
    : isRunning
      ? 'border-blue-400 dark:border-blue-500 shadow-sm shadow-blue-100 dark:shadow-blue-900/20'
      : isDone
        ? 'border-green-400 dark:border-green-600'
        : viaSnapshot
          ? 'border-amber-400 dark:border-amber-600'
          : 'border-red-400 dark:border-red-600';

  const bgClass = isPending
    ? 'bg-gray-50 dark:bg-gray-800/50'
    : isRunning
      ? 'bg-blue-50/50 dark:bg-blue-900/10'
      : isDone
        ? 'bg-green-50/50 dark:bg-green-900/10'
        : viaSnapshot
          ? 'bg-amber-50/50 dark:bg-amber-900/10'
          : 'bg-red-50/50 dark:bg-red-900/10';

  const timeoutLeft = timeout && elapsedMs ? Math.max(0, timeout - elapsedMs / 1000) : null;
  const percentUsed = timeout && elapsedMs ? Math.min(100, (elapsedMs / 1000 / timeout) * 100) : 0;

  return (
    <div className={`rounded-xl border-2 p-3 transition-all duration-300 ${borderClass} ${bgClass}`}>
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-1.5">
          {isRunning && <Loader2 className="w-3.5 h-3.5 text-blue-500 animate-spin flex-shrink-0" />}
          {isDone && <CheckCircle className="w-3.5 h-3.5 text-green-500 flex-shrink-0" />}
          {isError && !viaSnapshot && <XCircle className="w-3.5 h-3.5 text-red-500 flex-shrink-0" />}
          {viaSnapshot && <Archive className="w-3.5 h-3.5 text-amber-500 flex-shrink-0" />}
          {isPending && <div className="w-3.5 h-3.5 rounded-full border-2 border-gray-300 dark:border-gray-600 flex-shrink-0" />}
          <span className={`text-xs font-bold tracking-wide ${
            isRunning ? 'text-blue-700 dark:text-blue-300'
            : isDone ? 'text-green-700 dark:text-green-300'
            : isError && !viaSnapshot ? 'text-red-600 dark:text-red-400'
            : viaSnapshot ? 'text-amber-600 dark:text-amber-400'
            : 'text-gray-400 dark:text-gray-500'
          }`}>{label}</span>
        </div>
        {elapsedMs !== undefined && (isRunning || isDone || isError) && (
          <span className="text-xs font-mono text-gray-400 dark:text-gray-500">
            {fmtSec(elapsedMs)}
          </span>
        )}
      </div>

      <div className="flex items-center gap-1 mb-2">
        <span className="text-gray-400 dark:text-gray-500">{icon}</span>
        <span className={`text-xs ${
          isRunning ? 'text-blue-600 dark:text-blue-400'
          : 'text-gray-500 dark:text-gray-400'
        }`}>
          {subtitle}
        </span>
      </div>

      {isRunning && (
        <div className="space-y-1">
          <ScanBar color="blue" />
          {timeout && elapsedMs !== undefined && (
            <div className="flex justify-between items-center">
              <span className="text-xs text-gray-400">timeout: {timeout}s</span>
              {timeoutLeft !== null && timeoutLeft > 0 && (
                <span className="text-xs text-blue-500 font-medium">
                  {timeoutLeft.toFixed(0)}s restando
                </span>
              )}
            </div>
          )}
          {timeout && elapsedMs !== undefined && (
            <div className="h-0.5 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
              <div
                className="h-full bg-blue-400 dark:bg-blue-600 transition-all duration-100"
                style={{ width: `${100 - percentUsed}%` }}
              />
            </div>
          )}
        </div>
      )}

      {isDone && value !== undefined && (
        <div className="text-sm font-bold text-green-700 dark:text-green-300">
          {fmt(value)} insc.
        </div>
      )}

      {isError && !viaSnapshot && (
        <div className="space-y-1">
          <div className="text-xs text-red-600 dark:text-red-400 font-medium">
            Indisponível
          </div>
          {lastKnown != null && (
            <div className="text-xs text-gray-500 dark:text-gray-400">
              Último registrado: <span className="font-semibold text-gray-700 dark:text-gray-300">{lastKnown.toLocaleString('pt-BR')}</span>
              {lastKnownDate && (
                <span className="ml-1 text-gray-400">
                  ({new Date(lastKnownDate + 'T00:00:00').toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' })})
                </span>
              )}
            </div>
          )}
        </div>
      )}
      {viaSnapshot && (
        <div className="text-xs text-amber-600 dark:text-amber-400 font-medium">
          Via snapshot
        </div>
      )}
    </div>
  );
}

function AutoCloseBar({ seconds, onClose }: { seconds: number; onClose: () => void }) {
  const [left, setLeft] = useState(seconds);
  useEffect(() => {
    const iv = setInterval(() => setLeft(p => {
      if (p <= 1) { clearInterval(iv); onClose(); return 0; }
      return p - 1;
    }), 1000);
    return () => clearInterval(iv);
  }, []);
  return (
    <div className="space-y-1">
      <div className="h-1 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
        <div
          className="h-full bg-green-400 dark:bg-green-600 rounded-full"
          style={{ width: `${(left / seconds) * 100}%`, animation: `ah-cd ${seconds}s linear forwards` }}
        />
      </div>
      <p className="text-xs text-gray-400 dark:text-gray-500 text-center">
        Fechando automaticamente em {left}s
      </p>
    </div>
  );
}

function StepRow({ icon, label, state, timestamp }: {
  icon: React.ReactNode;
  label: string;
  state: 'pending' | 'running' | 'done' | 'error';
  timestamp?: number;
}) {
  const statusIcon = {
    pending: <div className="w-4 h-4 rounded-full border-2 border-gray-300 dark:border-gray-600" />,
    running: <Loader2 className="w-4 h-4 text-blue-500 animate-spin" />,
    done:    <CheckCircle className="w-4 h-4 text-green-500" />,
    error:   <XCircle className="w-4 h-4 text-red-500" />,
  }[state];

  return (
    <div className={`flex items-center gap-3 transition-all duration-300 ${state === 'pending' ? 'opacity-35' : 'opacity-100'}`}>
      <div className="flex-shrink-0">{statusIcon}</div>
      <div className={`flex items-center gap-1.5 text-sm flex-1 min-w-0 ${
        state === 'running' ? 'text-blue-600 dark:text-blue-400 font-medium'
        : state === 'done' ? 'text-gray-700 dark:text-gray-300'
        : state === 'error' ? 'text-red-600 dark:text-red-400'
        : 'text-gray-400 dark:text-gray-500'
      }`}>
        <span className="flex-shrink-0">{icon}</span>
        <span className="truncate">{label}</span>
      </div>
      {timestamp !== undefined && state !== 'pending' && (
        <span className="text-xs font-mono text-gray-400 dark:text-gray-500 flex-shrink-0">
          {fmtSec(timestamp)}
        </span>
      )}
    </div>
  );
}

type SourcePhase = 'pending' | 'running' | 'done' | 'error';
type GenericPhase = 'pending' | 'running' | 'done' | 'error';

export default function AtualizarHojeModal({
  open, status, result, errorMsg, onClose, startTime,
}: Props) {
  const isLoading = status === 'loading';
  const isDone = !isLoading;
  const isError = status === 'error' || status === 'busy' || status === 'cooldown';
  const isPartial = status === 'partial';
  const isFrozen = status === 'frozen';
  const isSuccess = status === 'success';
  const isFailed = status === 'failed';

  const elapsedMs = useElapsed(isLoading, startTime);

  const [sourcesPhase, setSourcesPhase] = useState<'pending' | 'active'>('pending');
  const [ativoPhase, setAtivoPhase] = useState<SourcePhase>('pending');
  const [magentoPhase, setMagentoPhase] = useState<SourcePhase>('pending');
  const [initPhase, setInitPhase] = useState<GenericPhase>('running');
  const [savePhase, setSavePhase] = useState<GenericPhase>('pending');
  const [reloadPhase, setReloadPhase] = useState<GenericPhase>('pending');

  const [initTs, setInitTs] = useState<number | undefined>(undefined);
  const [sourcesTs, setSourcesTs] = useState<number | undefined>(undefined);
  const [saveTs, setSaveTs] = useState<number | undefined>(undefined);
  const [reloadTs, setReloadTs] = useState<number | undefined>(undefined);

  const t1 = useRef<ReturnType<typeof setTimeout> | null>(null);
  const t2 = useRef<ReturnType<typeof setTimeout> | null>(null);
  const t3 = useRef<ReturnType<typeof setTimeout> | null>(null);
  const tAutoClose = useRef<ReturnType<typeof setTimeout> | null>(null);

  const clearAll = () => {
    [t1, t2, t3, tAutoClose].forEach(r => { if (r.current) { clearTimeout(r.current); r.current = null; } });
  };

  useEffect(() => {
    if (!open) { clearAll(); return; }

    if (status === 'loading') {
      clearAll();
      const origin = startTime ?? Date.now();
      setInitPhase('running'); setInitTs(undefined);
      setSourcesPhase('pending');
      setAtivoPhase('pending'); setMagentoPhase('pending');
      setSavePhase('pending'); setSaveTs(undefined);
      setReloadPhase('pending'); setReloadTs(undefined);
      setSourcesTs(undefined);

      t1.current = setTimeout(() => {
        const ts = Date.now() - origin;
        setInitPhase('done');
        setInitTs(ts);
        setSourcesPhase('active');
        setAtivoPhase('running');
        setMagentoPhase('running');
      }, 550);
      return;
    }

    clearAll();
    const origin = startTime ?? Date.now();
    const totalMs = Date.now() - origin;

    const bridge = result?.snapshot_bridge === true;
    const ativoOk = result?.ativo_ok !== false;
    const magentoOk = result?.magento_ok !== false;

    if (isError) {
      setInitPhase('done'); setInitTs(200);
      setSourcesPhase('active');
      setAtivoPhase('error'); setMagentoPhase('error');
      setSourcesTs(totalMs);
      setSavePhase('error'); setSaveTs(undefined);
      setReloadPhase('pending'); setReloadTs(undefined);
      return;
    }

    if (isFrozen) {
      setInitPhase('done'); setInitTs(Math.min(200, totalMs));
      setSourcesPhase('active');
      setAtivoPhase('done'); setMagentoPhase('done');
      setSourcesTs(Math.min(300, totalMs));
      setSavePhase('done'); setSaveTs(Math.min(350, totalMs));
      setReloadPhase('done'); setReloadTs(Math.min(400, totalMs));
      return;
    }

    setInitPhase('done');
    setInitTs(Math.min(550, totalMs * 0.06));
    setSourcesPhase('active');
    setAtivoPhase(ativoOk ? 'done' : (bridge ? 'error' : 'error'));
    setMagentoPhase(magentoOk ? 'done' : (bridge ? 'error' : 'error'));
    setSourcesTs(totalMs - 200);

    t1.current = setTimeout(() => {
      setSavePhase('done');
      setSaveTs(totalMs);

      t2.current = setTimeout(() => {
        setReloadPhase('running');
        t3.current = setTimeout(() => {
          setReloadPhase('done');
          setReloadTs(totalMs + 1600);
        }, 1000);
      }, 200);
    }, 150);

  }, [open, status]);

  useEffect(() => { return clearAll; }, []);

  if (!open) return null;

  const estRemaining = (): string | null => {
    if (!isLoading) return null;
    const s = elapsedMs / 1000;
    if (s < 2) return 'estimando…';
    const magentoLimit = 12;
    const left = Math.max(1, magentoLimit - s);
    if (s >= magentoLimit - 0.5) return 'aguardando resposta…';
    return `~${Math.ceil(left)}s restantes`;
  };

  const headerColor = isError
    ? 'from-red-600 to-red-700'
    : isPartial
      ? 'from-amber-500 to-amber-600'
      : isFailed
        ? 'from-red-600 to-red-700'
        : isSuccess || isFrozen
          ? 'from-green-600 to-green-700'
          : 'from-blue-600 to-blue-700';

  const headerLabel = isLoading
    ? 'Buscando dados de hoje…'
    : isError
      ? (status === 'busy' ? 'Sincronização em andamento' : status === 'cooldown' ? 'Aguarde o intervalo' : 'Erro na comunicação')
      : isFrozen
        ? 'Evento finalizado'
        : isPartial
          ? 'Dados parcialmente atualizados'
          : isFailed
            ? 'Ambas as fontes indisponíveis'
            : 'Atualização concluída!';

  const totalMs = isDone && startTime ? Date.now() - startTime : null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" style={{ backgroundColor: 'rgba(0,0,0,0.55)' }}>
      <div className="bg-white dark:bg-gray-900 rounded-2xl shadow-2xl w-full max-w-lg overflow-hidden">

        {/* ── Header ─────────────────────────────────────────── */}
        <div className={`bg-gradient-to-r ${headerColor} px-5 py-4`}>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              {isLoading
                ? <Loader2 className="w-5 h-5 text-white animate-spin" />
                : isError || isFailed
                  ? <XCircle className="w-5 h-5 text-white" />
                  : isPartial
                    ? <AlertTriangle className="w-5 h-5 text-white" />
                    : <CheckCircle className="w-5 h-5 text-white" />}
              <span className="text-white font-semibold text-sm">{headerLabel}</span>
            </div>
            <div className="flex items-center gap-3">
              {isLoading && (
                <span className="text-white/80 text-sm font-mono tabular-nums flex items-center gap-1">
                  <Clock className="w-3.5 h-3.5" />
                  {(elapsedMs / 1000).toFixed(1)}s
                </span>
              )}
              {isDone && totalMs && (
                <span className="text-white/70 text-xs font-mono flex items-center gap-1">
                  <Clock className="w-3.5 h-3.5" />
                  Durou {fmtSec(totalMs)}
                </span>
              )}
              {isDone && (
                <button onClick={onClose} className="text-white/70 hover:text-white transition-colors">
                  <X className="w-5 h-5" />
                </button>
              )}
            </div>
          </div>

          {/* progress track in header */}
          {isLoading && (
            <div className="mt-3">
              <ScanBar color="blue" />
            </div>
          )}
        </div>

        {/* ── Body ───────────────────────────────────────────── */}
        <div className="px-5 py-4 space-y-3">

          {/* Step 1: Init */}
          <StepRow
            icon={<Zap className="w-3.5 h-3.5" />}
            label="Verificações iniciais e freeze-check"
            state={initPhase}
            timestamp={initTs}
          />

          {/* Parallel sources block */}
          <div className={`rounded-xl border ${
            sourcesPhase === 'pending'
              ? 'border-gray-200 dark:border-gray-700 opacity-40'
              : 'border-gray-200 dark:border-gray-700'
          } overflow-hidden transition-all duration-300`}>
            <div className={`px-3 py-2 flex items-center justify-between text-xs font-semibold uppercase tracking-wide ${
              sourcesPhase === 'active'
                ? 'bg-blue-50 dark:bg-blue-900/20 text-blue-700 dark:text-blue-300 border-b border-blue-100 dark:border-blue-800'
                : 'bg-gray-50 dark:bg-gray-800 text-gray-400 border-b border-gray-200 dark:border-gray-700'
            }`}>
              <div className="flex items-center gap-1.5">
                <Database className="w-3.5 h-3.5" />
                Fontes consultadas em paralelo
              </div>
              {sourcesTs !== undefined && sourcesPhase === 'active' && (
                <span className="font-mono font-normal normal-case text-gray-400 dark:text-gray-500">
                  {fmtSec(sourcesTs)}
                </span>
              )}
            </div>

            <div className="grid grid-cols-2 gap-2 p-2">
              <SourceCard
                label="ATIVO"
                subtitle={ativoPhase === 'running' ? 'MySQL via SSH tunnel' : ativoPhase === 'done' ? 'MySQL via SSH' : 'MySQL via SSH'}
                icon={<Wifi className="w-3 h-3" />}
                phase={ativoPhase}
                value={result?.hoje_ativo}
                ok={result?.ativo_ok}
                elapsedMs={sourcesPhase === 'active' ? (sourcesTs ?? elapsedMs) : undefined}
                timeout={24}
              />
              <SourceCard
                label="MAGENTO"
                subtitle={magentoPhase === 'running' ? 'Pedidos da loja online' : 'Pedidos da loja online'}
                icon={<Database className="w-3 h-3" />}
                phase={magentoPhase}
                value={result?.hoje_magento}
                ok={result?.magento_ok}
                viaSnapshot={result?.snapshot_bridge === true && result?.magento_ok === false}
                elapsedMs={sourcesPhase === 'active' ? (sourcesTs ?? elapsedMs) : undefined}
                timeout={28}
                lastKnown={result?.magento_ultimo_conhecido}
                lastKnownDate={result?.magento_ultimo_data}
              />
            </div>
          </div>

          {/* Step 3: Save */}
          <StepRow
            icon={<Save className="w-3.5 h-3.5" />}
            label={isFrozen ? 'Evento finalizado — lendo snapshot' : 'Gravando snapshot consolidado no banco'}
            state={savePhase}
            timestamp={saveTs}
          />

          {/* Step 4: Reload */}
          <StepRow
            icon={<RotateCcw className="w-3.5 h-3.5" />}
            label="Atualizando exibição do evento"
            state={reloadPhase}
            timestamp={reloadTs}
          />

          {/* Estimated time (loading only) */}
          {isLoading && (() => {
            const est = estRemaining();
            return est ? (
              <div className="flex items-center justify-center gap-1.5 py-1">
                <Clock className="w-3.5 h-3.5 text-gray-400" />
                <span className="text-xs text-gray-400 dark:text-gray-500">
                  Previsão: {est}
                </span>
                <span className="text-xs text-gray-300 dark:text-gray-600">
                  (limite Magento 28s · Ativo 24s)
                </span>
              </div>
            ) : null;
          })()}

          {/* Error / result section */}
          {isDone && (
            <div className="space-y-3">
              {isError ? (
                <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-xl p-3">
                  <p className="text-sm text-red-700 dark:text-red-300">{errorMsg || 'Não foi possível concluir a atualização.'}</p>
                </div>
              ) : result ? (
                <ResultCard result={result} status={status} />
              ) : null}

              {isSuccess && !isError && (
                <AutoCloseBar seconds={6} onClose={onClose} />
              )}

              {(isPartial || isFailed) && !isError && (
                <p className="text-xs text-gray-400 dark:text-gray-500 text-center">
                  {isPartial
                    ? 'Dados do Ativo preservados. Tente novamente em alguns minutos quando o Magento estiver disponível.'
                    : 'Ambas as fontes estão indisponíveis. Tente novamente em 5 minutos.'}
                </p>
              )}

              <button
                onClick={onClose}
                className="w-full py-2 rounded-lg border border-gray-200 dark:border-gray-700 text-sm text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
              >
                Fechar
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function ResultCard({ result, status }: { result: SyncResult; status: SyncStatus }) {
  const isFrozen = status === 'frozen';
  const isPartial = status === 'partial';
  const isFailed = status === 'failed';
  const bridge = result.snapshot_bridge === true;
  const ativoViaSnapshot = bridge && result.ativo_ok === false;
  const magentoViaSnapshot = bridge && result.magento_ok === false;

  return (
    <div className="bg-gray-50 dark:bg-gray-800 rounded-xl p-4 space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">Resultado</span>
        <div className="flex items-center gap-1.5">
          {isFrozen && (
            <span className="px-2 py-0.5 rounded-full text-xs bg-gray-200 dark:bg-gray-700 text-gray-600 dark:text-gray-300 font-medium">Evento finalizado</span>
          )}
          {isPartial && (
            <span className="px-2 py-0.5 rounded-full text-xs bg-amber-100 dark:bg-amber-900/40 text-amber-700 dark:text-amber-300 font-medium">Parcial</span>
          )}
          {isFailed && (
            <span className="px-2 py-0.5 rounded-full text-xs bg-red-100 dark:bg-red-900/40 text-red-700 dark:text-red-300 font-medium">Falha</span>
          )}
          {status === 'success' && bridge && (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs bg-amber-100 dark:bg-amber-900/40 text-amber-700 dark:text-amber-300 font-medium">
              <Archive className="w-3 h-3" /> Via snapshot
            </span>
          )}
          {status === 'success' && !bridge && (
            <span className="px-2 py-0.5 rounded-full text-xs bg-green-100 dark:bg-green-900/40 text-green-700 dark:text-green-300 font-medium">Completo</span>
          )}
        </div>
      </div>

      {bridge && (
        <div className="text-xs text-amber-600 dark:text-amber-400 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-lg px-3 py-2 space-y-1">
          <p>Magento não respondeu ao vivo — snapshot do batch anterior preservou os dados.</p>
          {result.snapshot_atualizado_em && (
            <p className="font-medium">
              Snapshot válido desde{' '}
              {new Date(result.snapshot_atualizado_em).toLocaleString('pt-BR', {
                timeZone: 'America/Sao_Paulo', day: '2-digit', month: '2-digit',
                hour: '2-digit', minute: '2-digit',
              })}
            </p>
          )}
        </div>
      )}

      <div className="grid grid-cols-4 gap-2 border-t border-gray-200 dark:border-gray-700 pt-3">
        <MetricItem label="Total hoje" value={fmt(result.hoje_total)} highlight />
        <MetricItem label="Acumulado" value={fmt(result.total_acumulado)} />
        <MetricItem label="Média 7d" value={`${result.media_7d.toFixed(1)}/d`} />
        <MetricItem label="Média 14d" value={`${result.media_14d.toFixed(1)}/d`} />
      </div>
    </div>
  );
}

function MetricItem({ label, value, highlight }: { label: string; value: string; highlight?: boolean }) {
  return (
    <div>
      <div className="text-xs text-gray-400 dark:text-gray-500 truncate">{label}</div>
      <div className={`text-sm font-semibold ${highlight ? 'text-blue-600 dark:text-blue-400' : 'text-gray-700 dark:text-gray-200'}`}>{value}</div>
    </div>
  );
}
