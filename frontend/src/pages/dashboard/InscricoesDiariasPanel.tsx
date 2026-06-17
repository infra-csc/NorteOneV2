import React from 'react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell,
} from 'recharts';
import { TrendingUp, TrendingDown, Minus, Trophy, BarChart2 } from 'lucide-react';

interface DayEntry {
  data: string;
  total: number;
}

interface Top10Entry {
  evento_grupo: string;
  nome: string;
  total_periodo: number;
  total_periodo_anterior: number;
  variacao: number;
}

interface InscricoesDiariaData {
  periodo: { inicio: string; fim: string };
  diario: DayEntry[];
  top10: Top10Entry[];
}

interface Props {
  data: InscricoesDiariaData | null;
  loading: boolean;
  isDark: boolean;
}

const fmtNum = (v: number) => new Intl.NumberFormat('pt-BR').format(v);

const fmtDate = (iso: string) => {
  const [, m, d] = iso.split('-');
  return `${d}/${m}`;
};

const BAR_COLORS_DARK = [
  '#818cf8', '#818cf8', '#818cf8', '#818cf8', '#818cf8',
  '#818cf8', '#818cf8', '#818cf8', '#a78bfa', '#c084fc',
];
const BAR_COLORS_LIGHT = [
  '#6366f1', '#6366f1', '#6366f1', '#6366f1', '#6366f1',
  '#6366f1', '#6366f1', '#6366f1', '#8b5cf6', '#a855f7',
];

const MEDAL: Record<number, string> = { 0: '🥇', 1: '🥈', 2: '🥉' };

const SkeletonBar: React.FC<{ isDark: boolean }> = ({ isDark }) => (
  <div className={`h-4 rounded-full animate-pulse ${isDark ? 'bg-gray-700' : 'bg-gray-200'}`} />
);

const CustomTooltip: React.FC<any> = ({ active, payload, label, isDark }) => {
  if (!active || !payload?.length) return null;
  return (
    <div className={`px-3 py-2 rounded-xl shadow-xl border text-sm ${isDark ? 'bg-gray-800 border-gray-700 text-white' : 'bg-white border-gray-200 text-gray-900'}`}>
      <p className="font-bold mb-1">{label}</p>
      <p>{fmtNum(payload[0].value)} inscrições</p>
    </div>
  );
};

const InscricoesDiariasPanel: React.FC<Props> = ({ data, loading, isDark }) => {
  const cardClass = `rounded-2xl ${isDark ? 'bg-gray-800/60 backdrop-blur-xl border border-gray-700/50' : 'bg-white/80 backdrop-blur-xl border border-gray-200/80'}`;

  const barColors = isDark ? BAR_COLORS_DARK : BAR_COLORS_LIGHT;
  const maxTotal = data ? Math.max(...data.diario.map(d => d.total), 1) : 1;

  const VariacaoBadge: React.FC<{ variacao: number; prev: number }> = ({ variacao, prev }) => {
    if (prev === 0 && variacao === 0) return <span className={`text-xs ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>—</span>;
    if (variacao > 0) return (
      <span className="flex items-center gap-0.5 text-xs font-semibold text-emerald-400">
        <TrendingUp className="w-3 h-3" />+{fmtNum(variacao)}
      </span>
    );
    if (variacao < 0) return (
      <span className="flex items-center gap-0.5 text-xs font-semibold text-red-400">
        <TrendingDown className="w-3 h-3" />{fmtNum(variacao)}
      </span>
    );
    return (
      <span className="flex items-center gap-0.5 text-xs text-gray-400">
        <Minus className="w-3 h-3" />0
      </span>
    );
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      {/* Gráfico de barras: inscrições diárias */}
      <div className={`${cardClass} p-5`}>
        <div className="flex items-center gap-2 mb-4">
          <div className="p-2 rounded-xl bg-gradient-to-br from-indigo-500 to-purple-500 shadow-lg shadow-indigo-500/20">
            <BarChart2 className="w-4 h-4 text-white" />
          </div>
          <div>
            <h3 className={`text-sm font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>
              Inscrições Diárias
            </h3>
            <p className={`text-xs ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
              Todos os eventos — últimos 10 dias
            </p>
          </div>
        </div>

        {loading ? (
          <div className="space-y-3 py-4">
            {Array.from({ length: 5 }).map((_, i) => (
              <SkeletonBar key={i} isDark={isDark} />
            ))}
          </div>
        ) : !data || data.diario.every(d => d.total === 0) ? (
          <div className={`flex items-center justify-center h-40 text-sm ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>
            Sem dados de inscrições no período
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={data.diario} margin={{ top: 4, right: 4, bottom: 0, left: -8 }}>
              <CartesianGrid
                strokeDasharray="3 3"
                stroke={isDark ? '#374151' : '#e5e7eb'}
                vertical={false}
              />
              <XAxis
                dataKey="data"
                tickFormatter={fmtDate}
                tick={{ fontSize: 11, fill: isDark ? '#9ca3af' : '#6b7280' }}
                axisLine={false}
                tickLine={false}
              />
              <YAxis
                tick={{ fontSize: 11, fill: isDark ? '#9ca3af' : '#6b7280' }}
                axisLine={false}
                tickLine={false}
                tickFormatter={(v: number) => v >= 1000 ? `${(v / 1000).toFixed(0)}k` : String(v)}
              />
              <Tooltip content={<CustomTooltip isDark={isDark} />} cursor={{ fill: isDark ? 'rgba(99,102,241,0.1)' : 'rgba(99,102,241,0.05)' }} />
              <Bar dataKey="total" radius={[6, 6, 0, 0]}>
                {data.diario.map((entry, index) => (
                  <Cell
                    key={entry.data}
                    fill={barColors[index] || barColors[0]}
                    opacity={entry.total === maxTotal ? 1 : 0.7}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        )}

        {data && !loading && (
          <div className={`mt-3 pt-3 border-t ${isDark ? 'border-gray-700/60' : 'border-gray-100'} flex items-center justify-between`}>
            <span className={`text-xs ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
              Total no período
            </span>
            <span className={`text-sm font-black ${isDark ? 'text-white' : 'text-gray-900'}`}>
              {fmtNum(data.diario.reduce((s, d) => s + d.total, 0))}
            </span>
          </div>
        )}
      </div>

      {/* Tabela: TOP 10 eventos */}
      <div className={`${cardClass} p-5`}>
        <div className="flex items-center gap-2 mb-4">
          <div className="p-2 rounded-xl bg-gradient-to-br from-amber-500 to-orange-500 shadow-lg shadow-amber-500/20">
            <Trophy className="w-4 h-4 text-white" />
          </div>
          <div>
            <h3 className={`text-sm font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>
              TOP 10 Eventos
            </h3>
            <p className={`text-xs ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
              Mais vendidos nos últimos 10 dias
            </p>
          </div>
        </div>

        {loading ? (
          <div className="space-y-3">
            {Array.from({ length: 8 }).map((_, i) => (
              <div key={i} className="flex items-center gap-3">
                <div className={`w-6 h-4 rounded animate-pulse ${isDark ? 'bg-gray-700' : 'bg-gray-200'}`} />
                <div className={`flex-1 h-4 rounded-full animate-pulse ${isDark ? 'bg-gray-700' : 'bg-gray-200'}`} />
                <div className={`w-12 h-4 rounded animate-pulse ${isDark ? 'bg-gray-700' : 'bg-gray-200'}`} />
              </div>
            ))}
          </div>
        ) : !data || data.top10.length === 0 ? (
          <div className={`flex items-center justify-center h-40 text-sm ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>
            Sem dados de inscrições no período
          </div>
        ) : (
          <div className="space-y-2">
            {data.top10.map((ev, idx) => {
              const barPct = data.top10[0].total_periodo > 0
                ? Math.round((ev.total_periodo / data.top10[0].total_periodo) * 100)
                : 0;
              return (
                <div key={ev.evento_grupo} className="group">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-sm w-5 text-center flex-shrink-0">
                      {MEDAL[idx] ?? (
                        <span className={`text-xs font-bold ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>{idx + 1}</span>
                      )}
                    </span>
                    <span
                      className={`text-xs font-medium flex-1 truncate ${isDark ? 'text-gray-200' : 'text-gray-800'}`}
                      title={ev.nome}
                    >
                      {ev.nome}
                    </span>
                    <div className="flex items-center gap-2 flex-shrink-0">
                      <VariacaoBadge variacao={ev.variacao} prev={ev.total_periodo_anterior} />
                      <span className={`text-xs font-black w-14 text-right ${isDark ? 'text-white' : 'text-gray-900'}`}>
                        {fmtNum(ev.total_periodo)}
                      </span>
                    </div>
                  </div>
                  <div className={`ml-7 h-1.5 rounded-full ${isDark ? 'bg-gray-700' : 'bg-gray-100'} overflow-hidden`}>
                    <div
                      className={`h-full rounded-full transition-all duration-500 ${idx === 0 ? 'bg-amber-400' : idx === 1 ? 'bg-amber-300/80' : idx === 2 ? 'bg-amber-200/80' : 'bg-indigo-400/70'}`}
                      style={{ width: `${barPct}%` }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};

export default InscricoesDiariasPanel;
