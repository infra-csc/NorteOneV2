import React, { useEffect, useRef, useState } from 'react';
import {
  CheckCircle,
  XCircle,
  ChevronDown,
  ChevronUp,
  X,
  RefreshCw,
  Clock,
  Terminal,
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

const levelColor: Record<LogLevel, string> = {
  info:    'text-gray-400 dark:text-gray-500',
  success: 'text-emerald-500 dark:text-emerald-400',
  warning: 'text-amber-500 dark:text-amber-400',
  error:   'text-red-500 dark:text-red-400',
};

const levelPrefix: Record<LogLevel, string> = {
  info:    '●',
  success: '✔',
  warning: '⚠',
  error:   '✖',
};

export const OperationLogPanel: React.FC<Props> = ({ operation, onDismiss }) => {
  const [minimized, setMinimized] = useState(false);
  const logsEndRef = useRef<HTMLDivElement>(null);

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
  const elapsed = Math.round((Date.now() - operation.startedAt) / 1000);

  const progressColor =
    operation.status === 'error'
      ? 'bg-red-500'
      : operation.status === 'success'
        ? 'bg-emerald-500'
        : 'bg-blue-500';

  return (
    <div className="fixed bottom-4 right-4 z-50 w-[420px] max-w-[calc(100vw-2rem)] shadow-2xl rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 flex flex-col overflow-hidden">
      {/* Header */}
      <div className="flex items-center gap-2 px-4 py-2.5 bg-gray-50 dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700">
        <Terminal className="w-4 h-4 text-blue-500 dark:text-blue-400 flex-shrink-0" />
        <span className="text-sm font-semibold text-gray-800 dark:text-gray-100 flex-1 truncate">
          {operation.name}
        </span>

        {operation.status === 'running' && (
          <RefreshCw className="w-3.5 h-3.5 text-blue-500 animate-spin flex-shrink-0" />
        )}
        {operation.status === 'success' && (
          <CheckCircle className="w-3.5 h-3.5 text-emerald-500 flex-shrink-0" />
        )}
        {operation.status === 'error' && (
          <XCircle className="w-3.5 h-3.5 text-red-500 flex-shrink-0" />
        )}

        <button
          onClick={() => setMinimized(v => !v)}
          className="p-0.5 rounded hover:bg-gray-200 dark:hover:bg-gray-700 text-gray-500 dark:text-gray-400"
        >
          {minimized ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
        </button>
        {isDone && (
          <button
            onClick={onDismiss}
            className="p-0.5 rounded hover:bg-gray-200 dark:hover:bg-gray-700 text-gray-500 dark:text-gray-400"
          >
            <X className="w-4 h-4" />
          </button>
        )}
      </div>

      {/* Progress bar */}
      <div className="px-4 pt-2 pb-1 bg-white dark:bg-gray-900">
        <div className="flex items-center justify-between mb-1">
          <span className="text-xs text-gray-500 dark:text-gray-400 truncate max-w-[240px]">
            {operation.progressLabel || (isDone ? (operation.status === 'success' ? 'Concluído' : 'Falha') : 'Aguardando...')}
          </span>
          <div className="flex items-center gap-2 flex-shrink-0">
            <span className="text-xs font-bold text-gray-700 dark:text-gray-300">
              {Math.round(operation.progress)}%
            </span>
            {operation.status === 'running' && (
              <span className="flex items-center gap-1 text-[10px] text-gray-400 dark:text-gray-500">
                <Clock className="w-3 h-3" />
                {operation.eta != null
                  ? `ETA: ${fmtEta(operation.eta)}`
                  : `${elapsed}s`}
              </span>
            )}
          </div>
        </div>
        <div className="w-full h-1.5 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full transition-all duration-500 ease-out ${progressColor} ${operation.status === 'running' && operation.progress < 5 ? 'animate-pulse' : ''}`}
            style={{ width: `${Math.max(2, operation.progress)}%` }}
          />
        </div>
        <div className="flex items-center justify-between mt-0.5">
          <span className="text-[10px] text-gray-400 dark:text-gray-500">
            Iniciado às {fmtTime(operation.startedAt)} · {elapsed}s decorridos
          </span>
          {operation.status === 'running' && (
            <span className="text-[10px] text-blue-500 dark:text-blue-400">
              {operation.logs.length} eventos
            </span>
          )}
        </div>
      </div>

      {/* Logs */}
      {!minimized && (
        <div className="px-3 pb-3 max-h-52 overflow-y-auto bg-gray-950 dark:bg-gray-950 font-mono text-[11px] leading-relaxed">
          {operation.logs.map(entry => (
            <div key={entry.id} className="flex items-start gap-1.5 py-0.5">
              <span className="text-gray-600 dark:text-gray-600 flex-shrink-0">{entry.time}</span>
              <span className={`flex-shrink-0 ${levelColor[entry.level]}`}>{levelPrefix[entry.level]}</span>
              <span className={levelColor[entry.level]}>{entry.message}</span>
            </div>
          ))}
          <div ref={logsEndRef} />
          {operation.logs.length === 0 && (
            <span className="text-gray-600 dark:text-gray-600">Aguardando logs...</span>
          )}
        </div>
      )}
    </div>
  );
};

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
