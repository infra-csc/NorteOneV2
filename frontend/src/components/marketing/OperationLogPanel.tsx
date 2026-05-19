import React, { useEffect, useRef, useState } from 'react';
import {
  CheckCircle,
  XCircle,
  ChevronDown,
  ChevronUp,
  X,
  RefreshCw,
  Clock,
  Timer,
  Activity,
  Layers,
} from 'lucide-react';

export type LogLevel = 'info' | 'success' | 'warning' | 'error';

export interface LogEntry {
  id: number;
  time: string;
  level: LogLevel;
  message: string;
}

export type OpStatus = 'idle' | 'running' | 'success' | 'error';

export interface OperationLog {
  name: string;
  startedAt: number;
  progress: number;
  progressLabel: string;
  eta: number | null;
  logs: LogEntry[];
  status: OpStatus;
}

interface Props {
  operation: OperationLog | null;
  onDismiss: () => void;
}

function fmtTime(ts: number): string {
  return new Date(ts).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

function fmtEta(seconds: number): string {
  if (seconds <= 0) return '< 1s';
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return s > 0 ? `${m}m ${s}s` : `${m}m`;
}

function useElapsedSec(startedAt: number, active: boolean) {
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    if (!active) return;
    const iv = setInterval(() => setElapsed(Math.round((Date.now() - startedAt) / 1000)), 500);
    return () => clearInterval(iv);
  }, [startedAt, active]);
  return elapsed;
}

const levelColor: Record<LogLevel, string> = {
  info:    'text-slate-400',
  success: 'text-emerald-400',
  warning: 'text-amber-400',
  error:   'text-red-400',
};

const levelDot: Record<LogLevel, string> = {
  info:    'bg-slate-500',
  success: 'bg-emerald-400',
  warning: 'bg-amber-400',
  error:   'bg-red-400',
};

export const OperationLogPanel: React.FC<Props> = ({ operation, onDismiss }) => {
  const [minimized, setMinimized] = useState(false);
  const logsEndRef = useRef<HTMLDivElement>(null);

  const isRunning = operation?.status === 'running';
  const elapsed = useElapsedSec(operation?.startedAt ?? Date.now(), isRunning);

  useEffect(() => {
    if (!minimized && logsEndRef.current) {
      logsEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [operation?.logs.length, minimized]);

  useEffect(() => {
    setMinimized(false);
  }, [operation?.name]);

  if (!operation || operation.status === 'idle') return null;

  const isDone = operation.status === 'success' || operation.status === 'error';
  const isSuccess = operation.status === 'success';
  const isError = operation.status === 'error';

  const pct = Math.round(operation.progress);

  const headerGradient = isError
    ? 'from-red-600 to-red-700'
    : isSuccess
      ? 'from-emerald-600 to-emerald-700'
      : 'from-blue-600 to-blue-700';

  const barColor = isError
    ? 'bg-red-400'
    : isSuccess
      ? 'bg-emerald-400'
      : 'bg-blue-400';

  const barGlow = isError
    ? 'shadow-red-500/40'
    : isSuccess
      ? 'shadow-emerald-500/40'
      : 'shadow-blue-500/40';

  const statusIcon = isRunning
    ? <RefreshCw className="w-4 h-4 text-white animate-spin flex-shrink-0" />
    : isSuccess
      ? <CheckCircle className="w-4 h-4 text-white flex-shrink-0" />
      : <XCircle className="w-4 h-4 text-white flex-shrink-0" />;

  const finalElapsed = isDone
    ? Math.round((Date.now() - operation.startedAt) / 1000)
    : elapsed;

  return (
    <div className="fixed bottom-4 right-4 z-50 w-[440px] max-w-[calc(100vw-2rem)] shadow-2xl rounded-2xl overflow-hidden flex flex-col"
      style={{ boxShadow: '0 8px 32px rgba(0,0,0,0.28), 0 2px 8px rgba(0,0,0,0.18)' }}>

      {/* ── Header ─────────────────────────────────────────── */}
      <div className={`bg-gradient-to-r ${headerGradient} px-4 py-3`}>
        <div className="flex items-center gap-2.5">
          {statusIcon}
          <span className="text-white font-semibold text-sm flex-1 truncate">
            {operation.name}
          </span>
          <div className="flex items-center gap-1">
            <button
              onClick={() => setMinimized(v => !v)}
              className="p-1 rounded-lg text-white/70 hover:text-white hover:bg-white/15 transition-colors"
              title={minimized ? 'Expandir' : 'Minimizar'}
            >
              {minimized ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
            </button>
            {isDone && (
              <button
                onClick={onDismiss}
                className="p-1 rounded-lg text-white/70 hover:text-white hover:bg-white/15 transition-colors"
                title="Fechar"
              >
                <X className="w-4 h-4" />
              </button>
            )}
          </div>
        </div>

        {/* Progress bar inside header */}
        {!minimized && (
          <div className="mt-3 space-y-1.5">
            {/* Label + percentage */}
            <div className="flex items-center justify-between gap-2">
              <span className="text-white/85 text-xs truncate flex-1">
                {operation.progressLabel || (isDone
                  ? (isSuccess ? 'Concluído com sucesso' : 'Finalizado com erro')
                  : 'Iniciando...')}
              </span>
              <span className={`text-sm font-bold tabular-nums flex-shrink-0 ${
                pct === 100 ? 'text-white' : 'text-white/90'
              }`}>
                {pct}%
              </span>
            </div>

            {/* Bar */}
            <div className="h-1.5 bg-black/20 rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full transition-all duration-500 ease-out ${barColor} shadow-sm ${barGlow} ${
                  isRunning && pct < 5 ? 'animate-pulse' : ''
                }`}
                style={{ width: `${Math.max(2, pct)}%` }}
              />
            </div>
          </div>
        )}
      </div>

      {/* ── Stats row ──────────────────────────────────────── */}
      {!minimized && (
        <div className="flex items-center gap-0 divide-x divide-gray-200 dark:divide-gray-700 bg-gray-50 dark:bg-gray-800/80 border-b border-gray-200 dark:border-gray-700">

          <Stat
            icon={<Clock className="w-3 h-3" />}
            label="Início"
            value={fmtTime(operation.startedAt)}
          />

          <Stat
            icon={<Timer className="w-3 h-3" />}
            label={isDone ? 'Duração' : 'Decorrido'}
            value={`${finalElapsed}s`}
            highlight={isRunning}
          />

          {operation.eta != null && isRunning && (
            <Stat
              icon={<Activity className="w-3 h-3" />}
              label="ETA"
              value={fmtEta(operation.eta)}
              highlight
            />
          )}

          {operation.logs.length > 0 && (
            <Stat
              icon={<Layers className="w-3 h-3" />}
              label="Eventos"
              value={String(operation.logs.length)}
            />
          )}
        </div>
      )}

      {/* ── Log terminal ───────────────────────────────────── */}
      {!minimized && (
        <div className="bg-gray-950 max-h-48 overflow-y-auto">
          {operation.logs.length === 0 ? (
            <div className="px-4 py-3 flex items-center gap-2">
              <RefreshCw className="w-3 h-3 text-slate-600 animate-spin flex-shrink-0" />
              <span className="text-slate-600 text-[11px] font-mono">Aguardando logs...</span>
            </div>
          ) : (
            <div className="py-1.5">
              {operation.logs.map(entry => (
                <div
                  key={entry.id}
                  className="flex items-start gap-2 px-3 py-[3px] hover:bg-white/[0.03] transition-colors group"
                >
                  <span className="text-slate-600 text-[10px] font-mono tabular-nums flex-shrink-0 mt-[1px] group-hover:text-slate-500">
                    {entry.time}
                  </span>
                  <span className={`inline-block w-1.5 h-1.5 rounded-full flex-shrink-0 mt-[4px] ${levelDot[entry.level]}`} />
                  <span className={`text-[11px] font-mono leading-relaxed ${levelColor[entry.level]}`}>
                    {entry.message}
                  </span>
                </div>
              ))}
              <div ref={logsEndRef} />
            </div>
          )}
        </div>
      )}

      {/* ── Done footer ────────────────────────────────────── */}
      {!minimized && isDone && (
        <div className={`px-4 py-2 flex items-center justify-between text-xs ${
          isSuccess
            ? 'bg-emerald-50 dark:bg-emerald-900/20 border-t border-emerald-100 dark:border-emerald-800'
            : 'bg-red-50 dark:bg-red-900/20 border-t border-red-100 dark:border-red-800'
        }`}>
          <span className={isSuccess
            ? 'text-emerald-700 dark:text-emerald-300 font-medium'
            : 'text-red-700 dark:text-red-300 font-medium'}>
            {isSuccess ? 'Sincronização concluída' : 'Finalizado com erros'}
          </span>
          <button
            onClick={onDismiss}
            className={`text-xs px-2.5 py-1 rounded-lg font-medium transition-colors ${
              isSuccess
                ? 'text-emerald-700 dark:text-emerald-300 hover:bg-emerald-100 dark:hover:bg-emerald-800/40'
                : 'text-red-700 dark:text-red-300 hover:bg-red-100 dark:hover:bg-red-800/40'
            }`}
          >
            Fechar
          </button>
        </div>
      )}
    </div>
  );
};

function Stat({ icon, label, value, highlight }: {
  icon: React.ReactNode;
  label: string;
  value: string;
  highlight?: boolean;
}) {
  return (
    <div className="flex items-center gap-1.5 px-3 py-2 flex-1 min-w-0">
      <span className={`flex-shrink-0 ${highlight ? 'text-blue-500 dark:text-blue-400' : 'text-gray-400 dark:text-gray-500'}`}>
        {icon}
      </span>
      <div className="min-w-0">
        <div className="text-[9px] uppercase tracking-wide text-gray-400 dark:text-gray-500 leading-none mb-0.5">
          {label}
        </div>
        <div className={`text-xs font-semibold tabular-nums truncate leading-none ${
          highlight
            ? 'text-blue-600 dark:text-blue-400'
            : 'text-gray-700 dark:text-gray-200'
        }`}>
          {value}
        </div>
      </div>
    </div>
  );
}

let _logId = 0;

export function createEntry(level: LogLevel, message: string): LogEntry {
  return {
    id: ++_logId,
    time: new Date().toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
    level,
    message,
  };
}

export function makeOperation(name: string): OperationLog {
  return {
    name,
    startedAt: Date.now(),
    progress: 0,
    progressLabel: 'Iniciando...',
    eta: null,
    logs: [],
    status: 'running',
  };
}
