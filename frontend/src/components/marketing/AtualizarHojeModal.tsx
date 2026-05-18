import React, { useEffect, useRef, useState } from 'react';
import { X, CheckCircle, XCircle, AlertTriangle, RefreshCw, Loader2, Database, Zap, Save, RotateCcw, Archive } from 'lucide-react';

export type SyncStatus = 'loading' | 'success' | 'partial' | 'frozen' | 'failed' | 'error' | 'busy' | 'cooldown';

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
}

interface Props {
  open: boolean;
  status: SyncStatus;
  result?: SyncResult | null;
  errorMsg?: string | null;
  onClose: () => void;
}

type StepState = 'pending' | 'running' | 'done' | 'error';

interface Step {
  id: string;
  label: string;
  icon: React.ReactNode;
  state: StepState;
}

function fmt(n: number) {
  return n.toLocaleString('pt-BR');
}

export default function AtualizarHojeModal({ open, status, result, errorMsg, onClose }: Props) {
  const [steps, setSteps] = useState<Step[]>([]);
  const timer1 = useRef<ReturnType<typeof setTimeout> | null>(null);
  const timer2 = useRef<ReturnType<typeof setTimeout> | null>(null);
  const autoCloseTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const clearTimers = () => {
    [timer1, timer2, autoCloseTimer].forEach(t => {
      if (t.current) { clearTimeout(t.current); t.current = null; }
    });
  };

  useEffect(() => {
    if (!open) {
      clearTimers();
      return;
    }

    if (status === 'loading') {
      clearTimers();
      setSteps([
        { id: 'init',    label: 'Iniciando sincronização…',                icon: <Zap className="w-4 h-4" />,      state: 'running' },
        { id: 'fetch',   label: 'Buscando vendas no Ativo e Magento…',     icon: <Database className="w-4 h-4" />, state: 'pending' },
        { id: 'save',    label: 'Gravando snapshot consolidado…',           icon: <Save className="w-4 h-4" />,     state: 'pending' },
        { id: 'reload',  label: 'Recarregando dados do evento…',            icon: <RotateCcw className="w-4 h-4" />,state: 'pending' },
      ]);

      timer1.current = setTimeout(() => {
        setSteps(prev => prev.map(s =>
          s.id === 'init'  ? { ...s, state: 'done' as StepState } :
          s.id === 'fetch' ? { ...s, state: 'running' as StepState } : s
        ));
      }, 600);

      return;
    }

    const isDone = ['success', 'partial', 'frozen', 'failed', 'error', 'busy', 'cooldown'].includes(status);
    if (isDone) {
      clearTimers();
      const isError = status === 'error' || status === 'busy' || status === 'cooldown';
      const isFrozen = status === 'frozen';
      const isPartial = status === 'partial';

      setSteps(prev => {
        const base = prev.length > 0 ? prev : [
          { id: 'init',   label: 'Iniciando sincronização…',                icon: <Zap className="w-4 h-4" />,       state: 'done' as StepState },
          { id: 'fetch',  label: 'Buscando vendas no Ativo e Magento…',     icon: <Database className="w-4 h-4" />,  state: 'done' as StepState },
          { id: 'save',   label: 'Gravando snapshot consolidado…',           icon: <Save className="w-4 h-4" />,      state: 'pending' as StepState },
          { id: 'reload', label: 'Recarregando dados do evento…',            icon: <RotateCcw className="w-4 h-4" />, state: 'pending' as StepState },
        ];
        return base.map(s => {
          if (s.id === 'init' || s.id === 'fetch') {
            return { ...s, state: isError ? 'error' as StepState : 'done' as StepState };
          }
          if (s.id === 'save') {
            if (isError) return { ...s, state: 'error' as StepState };
            if (isFrozen) return { ...s, label: 'Evento finalizado — dados do snapshot', state: 'done' as StepState };
            return { ...s, state: (isPartial ? 'done' : 'done') as StepState };
          }
          if (s.id === 'reload') {
            if (isError) return { ...s, state: 'pending' as StepState };
            return { ...s, state: 'running' as StepState };
          }
          return s;
        });
      });

      timer1.current = setTimeout(() => {
        setSteps(prev => prev.map(s =>
          s.id === 'reload' && !isError ? { ...s, state: 'done' as StepState } : s
        ));
      }, 1200);

      if (!isError && !isFrozen) {
        autoCloseTimer.current = setTimeout(() => onClose(), 6000);
      }
    }

    return clearTimers;
  }, [open, status]);

  useEffect(() => {
    return clearTimers;
  }, []);

  if (!open) return null;

  const isDone = status !== 'loading';
  const isError = status === 'error' || status === 'busy' || status === 'cooldown';
  const isSuccess = status === 'success' || status === 'frozen';
  const isPartial = status === 'partial';

  const headerColor = isError
    ? 'from-red-600 to-red-700'
    : isPartial
      ? 'from-amber-500 to-amber-600'
      : isSuccess
        ? 'from-green-600 to-green-700'
        : 'from-blue-600 to-blue-700';

  const headerLabel = isError
    ? status === 'busy' ? 'Sincronização em andamento' : status === 'cooldown' ? 'Aguarde o intervalo' : 'Falha na atualização'
    : isPartial
      ? 'Dados parcialmente atualizados'
      : status === 'frozen'
        ? 'Evento finalizado'
        : isDone
          ? 'Atualização concluída!'
          : 'Atualizando dados de hoje…';

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" style={{ backgroundColor: 'rgba(0,0,0,0.5)' }}>
      <div className="bg-white dark:bg-gray-900 rounded-2xl shadow-2xl w-full max-w-md overflow-hidden">

        <div className={`bg-gradient-to-r ${headerColor} px-5 py-4 flex items-center justify-between`}>
          <div className="flex items-center gap-3">
            {!isDone
              ? <Loader2 className="w-5 h-5 text-white animate-spin" />
              : isError
                ? <XCircle className="w-5 h-5 text-white" />
                : isPartial
                  ? <AlertTriangle className="w-5 h-5 text-white" />
                  : <CheckCircle className="w-5 h-5 text-white" />}
            <span className="text-white font-semibold text-sm">{headerLabel}</span>
          </div>
          {isDone && (
            <button onClick={onClose} className="text-white/80 hover:text-white transition-colors">
              <X className="w-5 h-5" />
            </button>
          )}
        </div>

        <div className="px-5 py-4 space-y-3">
          <div className="space-y-2">
            {steps.map((step, i) => (
              <StepRow key={step.id} step={step} index={i} />
            ))}
          </div>

          {isDone && (
            <div className="mt-4 space-y-3">
              {isError ? (
                <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-xl p-3">
                  <p className="text-sm text-red-700 dark:text-red-300">{errorMsg || 'Não foi possível concluir a atualização.'}</p>
                </div>
              ) : result ? (
                <ResultCard result={result} status={status} />
              ) : null}

              {!isError && isDone && (
                <p className="text-xs text-gray-400 dark:text-gray-500 text-center">
                  {isSuccess && !isError
                    ? 'Dados do evento sendo recarregados em segundo plano…'
                    : isPartial
                      ? 'Recarregue novamente em alguns instantes para completar a sincronização.'
                      : ''}
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

function StepRow({ step }: { step: Step; index: number }) {
  const stateIcon = {
    pending: <div className="w-4 h-4 rounded-full border-2 border-gray-300 dark:border-gray-600" />,
    running: <Loader2 className="w-4 h-4 text-blue-500 animate-spin" />,
    done:    <CheckCircle className="w-4 h-4 text-green-500" />,
    error:   <XCircle className="w-4 h-4 text-red-500" />,
  }[step.state];

  const textColor = {
    pending: 'text-gray-400 dark:text-gray-500',
    running: 'text-blue-600 dark:text-blue-400 font-medium',
    done:    'text-gray-700 dark:text-gray-300',
    error:   'text-red-600 dark:text-red-400',
  }[step.state];

  return (
    <div className={`flex items-center gap-3 transition-all duration-300 ${step.state === 'pending' ? 'opacity-40' : 'opacity-100'}`}>
      <div className="flex-shrink-0">{stateIcon}</div>
      <div className={`flex items-center gap-2 text-sm ${textColor}`}>
        <span className={`${step.state === 'pending' ? 'text-gray-400' : ''}`}>{step.icon}</span>
        <span>{step.label}</span>
      </div>
    </div>
  );
}

function ResultCard({ result, status }: { result: SyncResult; status: SyncStatus }) {
  const isFrozen = status === 'frozen';
  const isPartial = status === 'partial';
  const bridge = result.snapshot_bridge === true;

  const ativoViaSnapshot  = bridge && result.ativo_ok === false;
  const magentoViaSnapshot = bridge && result.magento_ok === false;

  return (
    <div className="bg-gray-50 dark:bg-gray-800 rounded-xl p-4 space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">Resultado</span>
        {isFrozen && (
          <span className="px-2 py-0.5 rounded-full text-xs bg-gray-200 dark:bg-gray-700 text-gray-600 dark:text-gray-300 font-medium">Evento finalizado</span>
        )}
        {isPartial && (
          <span className="px-2 py-0.5 rounded-full text-xs bg-amber-100 dark:bg-amber-900/40 text-amber-700 dark:text-amber-300 font-medium">Parcial</span>
        )}
        {status === 'success' && !bridge && (
          <span className="px-2 py-0.5 rounded-full text-xs bg-green-100 dark:bg-green-900/40 text-green-700 dark:text-green-300 font-medium">Completo</span>
        )}
        {status === 'success' && bridge && (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs bg-amber-100 dark:bg-amber-900/40 text-amber-700 dark:text-amber-300 font-medium">
            <Archive className="w-3 h-3" />
            Via snapshot
          </span>
        )}
      </div>

      <div className="grid grid-cols-2 gap-3">
        <SourceBadge label="Ativo"   value={result.hoje_ativo}   ok={result.ativo_ok !== false}   viaSnapshot={ativoViaSnapshot} />
        <SourceBadge label="Magento" value={result.hoje_magento} ok={result.magento_ok !== false} viaSnapshot={magentoViaSnapshot} />
      </div>

      {bridge && (
        <p className="text-xs text-amber-600 dark:text-amber-400 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-lg px-3 py-2">
          O Magento não respondeu ao vivo, mas o snapshot do batch anterior preservou os dados — total não foi reduzido.
        </p>
      )}

      <div className="border-t border-gray-200 dark:border-gray-700 pt-3 grid grid-cols-2 gap-3">
        <MetricItem label="Total hoje" value={fmt(result.hoje_total)} highlight />
        <MetricItem label="Acumulado" value={fmt(result.total_acumulado)} />
        <MetricItem label="Média 7d" value={`${result.media_7d.toFixed(1)}/dia`} />
        <MetricItem label="Média 14d" value={`${result.media_14d.toFixed(1)}/dia`} />
      </div>
    </div>
  );
}

function SourceBadge({ label, value, ok, viaSnapshot }: { label: string; value: number; ok: boolean; viaSnapshot?: boolean }) {
  if (viaSnapshot) {
    return (
      <div className="flex items-center gap-2 rounded-lg px-3 py-2 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800">
        <Archive className="w-3.5 h-3.5 text-amber-500 flex-shrink-0" />
        <div className="min-w-0">
          <div className="text-xs text-amber-600 dark:text-amber-400">{label}</div>
          <div className="text-sm font-semibold text-amber-700 dark:text-amber-300">via snapshot</div>
        </div>
      </div>
    );
  }
  return (
    <div className={`flex items-center gap-2 rounded-lg px-3 py-2 ${ok ? 'bg-white dark:bg-gray-700 border border-gray-200 dark:border-gray-600' : 'bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800'}`}>
      {ok
        ? <CheckCircle className="w-3.5 h-3.5 text-green-500 flex-shrink-0" />
        : <XCircle className="w-3.5 h-3.5 text-red-400 flex-shrink-0" />}
      <div className="min-w-0">
        <div className="text-xs text-gray-500 dark:text-gray-400">{label}</div>
        <div className={`text-sm font-semibold ${ok ? 'text-gray-800 dark:text-gray-100' : 'text-red-600 dark:text-red-400'}`}>
          {ok ? `${fmt(value)} insc.` : 'indisponível'}
        </div>
      </div>
    </div>
  );
}

function MetricItem({ label, value, highlight }: { label: string; value: string; highlight?: boolean }) {
  return (
    <div>
      <div className="text-xs text-gray-400 dark:text-gray-500">{label}</div>
      <div className={`text-sm font-semibold ${highlight ? 'text-blue-600 dark:text-blue-400' : 'text-gray-700 dark:text-gray-200'}`}>{value}</div>
    </div>
  );
}
