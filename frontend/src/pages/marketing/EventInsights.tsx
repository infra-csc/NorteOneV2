import React, { useState, useEffect } from 'react';
import {
  Loader2,
  TrendingUp,
  TrendingDown,
  AlertTriangle,
} from 'lucide-react';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  ReferenceLine
} from 'recharts';
import { marketingService } from '../../services/api';
import { useTheme } from '../../context/ThemeContext';

interface EventInsightsProps {
  eventoId: string;
  ano?: number;
  forceRefresh?: boolean;
}

const formatCurrency = (n: number) => n.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });

const COLORS = {
  anoAtual: '#3b82f6',
  anoAnterior: '#94a3b8',
  neutral: '#f59e0b',
  ticketMedio: '#10b981',
};

const EventInsights: React.FC<EventInsightsProps> = ({ eventoId, ano, forceRefresh }) => {
  const { isDark } = useTheme();
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();

    const fetchInsights = async () => {
      try {
        setLoading(true);
        setError(null);
        const response = await marketingService.getEventInsights(eventoId, controller.signal, ano, forceRefresh);
        if (!controller.signal.aborted) {
          setData(response);
        }
      } catch (err: any) {
        if (err?.name === 'CanceledError' || err?.code === 'ERR_CANCELED' || err?.name === 'AbortError') return;
        if (!controller.signal.aborted) {
          setError('Erro ao carregar insights estratégicos');
        }
      } finally {
        if (!controller.signal.aborted) {
          setLoading(false);
        }
      }
    };

    fetchInsights();
    return () => { controller.abort(); };
  }, [eventoId, ano, forceRefresh]);

  if (loading) {
    return (
      <div className="bg-white dark:bg-gray-800 rounded-xl p-12 shadow-sm border border-gray-200 dark:border-gray-700 flex flex-col items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-blue-600" />
        <p className="mt-4 text-gray-500 dark:text-gray-400">Carregando insights estratégicos...</p>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="bg-white dark:bg-gray-800 rounded-xl p-8 shadow-sm border border-gray-200 dark:border-gray-700 text-center">
        <AlertTriangle className="w-8 h-8 text-amber-500 mx-auto mb-3" />
        <p className="text-gray-500 dark:text-gray-400">{error || 'Dados não disponíveis'}</p>
      </div>
    );
  }

  const { indice_aceleracao, ticket_medio } = data;

  const gridColor = isDark ? '#374151' : '#e5e7eb';
  const textColor = isDark ? '#9ca3af' : '#6b7280';

  const cardClass = 'bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm border border-gray-200 dark:border-gray-700';

  const hasContent = (indice_aceleracao && indice_aceleracao.length > 0) || (ticket_medio && ticket_medio.length > 0);

  if (!hasContent) return null;

  return (
    <div className="space-y-6">
      {indice_aceleracao && indice_aceleracao.length > 0 && (
        <div className={cardClass}>
          <div className="mb-4">
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white">Índice de Aceleração (IA)</h3>
            <p className="text-sm text-gray-500 dark:text-gray-400">IA {'>'} 1 = Acelerando | IA {'<'} 1 = Desacelerando</p>
          </div>
          <div style={{ height: 300 }}>
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={indice_aceleracao}>
                <CartesianGrid strokeDasharray="3 3" stroke={gridColor} />
                <XAxis dataKey="label" tick={{ fill: textColor, fontSize: 12 }} />
                <YAxis tick={{ fill: textColor, fontSize: 12 }} domain={['auto', 'auto']} />
                <Tooltip
                  contentStyle={{
                    backgroundColor: isDark ? '#1f2937' : '#fff',
                    border: `1px solid ${isDark ? '#374151' : '#e5e7eb'}`,
                    borderRadius: '8px',
                    color: isDark ? '#fff' : '#111'
                  }}
                  formatter={(value: any, name: any) => [
                    typeof value === 'number' ? value.toFixed(3) : value,
                    name === 'ia_atual' ? `Ano ${data.ano_atual}` : `Ano ${data.ano_anterior}`
                  ]}
                />
                <Legend
                  formatter={(value: string) => value === 'ia_atual' ? `Ano ${data.ano_atual}` : `Ano ${data.ano_anterior}`}
                />
                <ReferenceLine y={1} stroke={COLORS.neutral} strokeDasharray="6 4" label={{ value: 'Neutro', fill: COLORS.neutral, fontSize: 12 }} />
                <Line type="monotone" dataKey="ia_atual" stroke={COLORS.anoAtual} strokeWidth={2.5} dot={false} activeDot={{ r: 5 }} connectNulls={false} />
                <Line type="monotone" dataKey="ia_anterior" stroke={COLORS.anoAnterior} strokeWidth={2} strokeDasharray="5 5" dot={false} activeDot={{ r: 4 }} connectNulls={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {ticket_medio && ticket_medio.length > 0 && (
        <div className={cardClass}>
          <div className="mb-4">
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white">Ticket Médio por Período</h3>
            <p className="text-sm text-gray-500 dark:text-gray-400">Evolução do ticket médio ao longo do tempo</p>
          </div>
          <div style={{ height: 300 }}>
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={ticket_medio}>
                <CartesianGrid strokeDasharray="3 3" stroke={gridColor} />
                <XAxis dataKey="label" tick={{ fill: textColor, fontSize: 12 }} />
                <YAxis
                  tick={{ fill: textColor, fontSize: 12 }}
                  tickFormatter={(v: number) => `R$ ${v}`}
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: isDark ? '#1f2937' : '#fff',
                    border: `1px solid ${isDark ? '#374151' : '#e5e7eb'}`,
                    borderRadius: '8px',
                    color: isDark ? '#fff' : '#111'
                  }}
                  formatter={(value: any, name: any) => [
                    typeof value === 'number' ? formatCurrency(value) : value,
                    name === 'ticket_atual' ? `Ano ${data.ano_atual}` : `Ano ${data.ano_anterior}`
                  ]}
                />
                <Legend
                  formatter={(value: string) => value === 'ticket_atual' ? `Ano ${data.ano_atual}` : `Ano ${data.ano_anterior}`}
                />
                <Line type="monotone" dataKey="ticket_atual" stroke={COLORS.ticketMedio} strokeWidth={2.5} dot={false} activeDot={{ r: 5 }} connectNulls={false} />
                <Line type="monotone" dataKey="ticket_anterior" stroke={COLORS.anoAnterior} strokeWidth={2} strokeDasharray="5 5" dot={false} activeDot={{ r: 4 }} connectNulls={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}
    </div>
  );
};

export default EventInsights;
