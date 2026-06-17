import React, { useState } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Cell, Legend,
} from 'recharts';
import { TrendingUp, TrendingDown, Minus, Trophy, BarChart2, Layers, AlignJustify } from 'lucide-react';

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

interface GrupoMeta {
  key: string;
  nome: string;
  rank: number;
}

interface DayPerGrupoEntry {
  data: string;
  grupos: Record<string, number>;
}

interface InscricoesDiariaData {
  periodo: { inicio: string; fim: string };
  diario: DayEntry[];
  top10: Top10Entry[];
  grupos_meta?: GrupoMeta[];
  diario_por_grupo?: DayPerGrupoEntry[];
}

interface Props {
  data: InscricoesDiariaData | null;
  loading: boolean;
  isDark: boolean;
}

type ViewMode = 'total' | 'por_evento';

const fmtNum = (v: number) => new Intl.NumberFormat('pt-BR').format(v);

const fmtDate = (iso: string) => {
  const [, m, d] = iso.split('-');
  return `${d}/${m}`;
};

const STACK_COLORS = [
  '#6366f1', '#f59e0b', '#10b981', '#ef4444', '#3b82f6',
  '#8b5cf6', '#ec4899', '#14b8a6', '#f97316', '#84cc16',
];

const MEDAL: Record<number, string> = { 0: '🥇', 1: '🥈', 2: '🥉' };

const SkeletonBar: React.FC<{ isDark: boolean }> = ({ isDark }) => (
  <div className={`h-4 rounded-full animate-pulse ${isDark ? 'bg-gray-700' : 'bg-gray-200'}`} />
);

const CustomTooltipTotal: React.FC<any> = ({ active, payload, label, isDark }) => {
  if (!active || !payload?.length) return null;
  return (
    <div className={`px-3 py-2 rounded-xl shadow-xl border text-sm ${isDark ? 'bg-gray-800 border-gray-700 text-white' : 'bg-white border-gray-200 text-gray-900'}`}>
      <p className="font-bold mb-1">{label}</p>
      <p>{fmtNum(payload[0].value)} inscrições</p>
    </div>
  );
};

const CustomTooltipStacked: React.FC<any> = ({ active, payload, label, isDark }) => {
  if (!active || !payload?.length) return null;
  const total = payload.reduce((s: number, p: any) => s + (p.value || 0), 0);
  const sorted = [...payload].sort((a, b) => (b.value || 0) - (a.value || 0));
  return (
    <div className={`px-3 py-2.5 rounded-xl shadow-xl border text-xs max-w-[220px] ${isDark ? 'bg-gray-800 border-gray-700 text-white' : 'bg-white border-gray-200 text-gray-900'}`}>
      <p className="font-bold text-sm mb-2">{label} — {fmtNum(total)}</p>
      {sorted.filter(p => p.value > 0).map((p: any) => (
        <div key={p.dataKey} className="flex items-center gap-1.5 mb-1">
          <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: p.fill }} />
          <span className={`truncate max-w-[140px] ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>{p.name}</span>
          <span className="ml-auto font-semibold flex-shrink-0">{fmtNum(p.value)}</span>
        </div>
      ))}
    </div>
  );
};

const InscricoesDiariasPanel: React.FC<Props> = ({ data, loading, isDark }) => {
  const [viewMode, setViewMode] = useState<ViewMode>('total');

  const cardClass = `rounded-2xl ${isDark ? 'bg-gray-800/60 backdrop-blur-xl border border-gray-700/50' : 'bg-white/80 backdrop-blur-xl border border-gray-200/80'}`;

  const maxTotal = data ? Math.max(...data.diario.map(d => d.total), 1) : 1;

  const gruposMeta: GrupoMeta[] = data?.grupos_meta ?? [];
  const hasByEvento = gruposMeta.length > 0 && (data?.diario_por_grupo?.length ?? 0) > 0;

  // Build flat Recharts-ready data for stacked chart
  const stackedData = React.useMemo(() => {
    if (!data?.diario_por_grupo) return [];
    return data.diario_por_grupo.map(entry => {
      const row: Record<string, any> = { data: entry.data };
      for (const gm of gruposMeta) {
        row[gm.key] = entry.grupos[gm.key] ?? 0;
      }
      return row;
    });
  }, [data, gruposMeta]);

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

  const isEmpty = !data || data.diario.every(d => d.total === 0);

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      {/* Gráfico de barras */}
      <div className={`${cardClass} p-5`}>
        {/* Header com toggle */}
        <div className="flex items-center gap-2 mb-4">
          <div className="p-2 rounded-xl bg-gradient-to-br from-indigo-500 to-purple-500 shadow-lg shadow-indigo-500/20">
            <BarChart2 className="w-4 h-4 text-white" />
          </div>
          <div className="flex-1 min-w-0">
            <h3 className={`text-sm font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>
              Inscrições Diárias
            </h3>
            <p className={`text-xs truncate ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
              {viewMode === 'total' ? 'Todos os eventos — últimos 10 dias' : 'Por evento — últimos 10 dias'}
            </p>
          </div>
          {/* Toggle Total / Por Evento */}
          {hasByEvento && !loading && !isEmpty && (
            <div className={`flex items-center rounded-lg p-0.5 ${isDark ? 'bg-gray-700/60' : 'bg-gray-100'}`}>
              <button
                onClick={() => setViewMode('total')}
                title="Ver total agregado"
                className={`flex items-center gap-1 px-2.5 py-1 rounded-md text-xs font-semibold transition-all ${
                  viewMode === 'total'
                    ? isDark ? 'bg-indigo-600 text-white shadow' : 'bg-indigo-500 text-white shadow'
                    : isDark ? 'text-gray-400 hover:text-gray-200' : 'text-gray-500 hover:text-gray-700'
                }`}
              >
                <AlignJustify className="w-3 h-3" />
                Total
              </button>
              <button
                onClick={() => setViewMode('por_evento')}
                title="Ver por evento empilhado"
                className={`flex items-center gap-1 px-2.5 py-1 rounded-md text-xs font-semibold transition-all ${
                  viewMode === 'por_evento'
                    ? isDark ? 'bg-indigo-600 text-white shadow' : 'bg-indigo-500 text-white shadow'
                    : isDark ? 'text-gray-400 hover:text-gray-200' : 'text-gray-500 hover:text-gray-700'
                }`}
              >
                <Layers className="w-3 h-3" />
                Por Evento
              </button>
            </div>
          )}
        </div>

        {loading ? (
          <div className="space-y-3 py-4">
            {Array.from({ length: 5 }).map((_, i) => (
              <SkeletonBar key={i} isDark={isDark} />
            ))}
          </div>
        ) : isEmpty ? (
          <div className={`flex items-center justify-center h-40 text-sm ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>
            Sem dados de inscrições no período
          </div>
        ) : viewMode === 'total' ? (
          /* ---- Vista Total ---- */
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={data!.diario} margin={{ top: 4, right: 4, bottom: 0, left: -8 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={isDark ? '#374151' : '#e5e7eb'} vertical={false} />
              <XAxis
                dataKey="data" tickFormatter={fmtDate}
                tick={{ fontSize: 11, fill: isDark ? '#9ca3af' : '#6b7280' }}
                axisLine={false} tickLine={false}
              />
              <YAxis
                tick={{ fontSize: 11, fill: isDark ? '#9ca3af' : '#6b7280' }}
                axisLine={false} tickLine={false}
                tickFormatter={(v: number) => v >= 1000 ? `${(v / 1000).toFixed(0)}k` : String(v)}
              />
              <Tooltip
                content={<CustomTooltipTotal isDark={isDark} />}
                cursor={{ fill: isDark ? 'rgba(99,102,241,0.1)' : 'rgba(99,102,241,0.05)' }}
              />
              <Bar dataKey="total" radius={[6, 6, 0, 0]}>
                {data!.diario.map((entry, index) => (
                  <Cell
                    key={entry.data}
                    fill={isDark ? '#818cf8' : '#6366f1'}
                    opacity={entry.total === maxTotal ? 1 : 0.65}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        ) : (
          /* ---- Vista Por Evento (empilhado) ---- */
          <>
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={stackedData} margin={{ top: 4, right: 4, bottom: 0, left: -8 }}>
                <CartesianGrid strokeDasharray="3 3" stroke={isDark ? '#374151' : '#e5e7eb'} vertical={false} />
                <XAxis
                  dataKey="data" tickFormatter={fmtDate}
                  tick={{ fontSize: 11, fill: isDark ? '#9ca3af' : '#6b7280' }}
                  axisLine={false} tickLine={false}
                />
                <YAxis
                  tick={{ fontSize: 11, fill: isDark ? '#9ca3af' : '#6b7280' }}
                  axisLine={false} tickLine={false}
                  tickFormatter={(v: number) => v >= 1000 ? `${(v / 1000).toFixed(0)}k` : String(v)}
                />
                <Tooltip
                  content={<CustomTooltipStacked isDark={isDark} />}
                  cursor={{ fill: isDark ? 'rgba(99,102,241,0.08)' : 'rgba(99,102,241,0.04)' }}
                />
                {gruposMeta.map((gm, idx) => (
                  <Bar
                    key={gm.key}
                    dataKey={gm.key}
                    name={gm.nome}
                    stackId="a"
                    fill={STACK_COLORS[idx % STACK_COLORS.length]}
                    radius={idx === gruposMeta.length - 1 ? [4, 4, 0, 0] : [0, 0, 0, 0]}
                  />
                ))}
              </BarChart>
            </ResponsiveContainer>
            {/* Legenda compacta de eventos */}
            <div className={`mt-3 pt-3 border-t ${isDark ? 'border-gray-700/60' : 'border-gray-100'}`}>
              <div className="flex flex-wrap gap-x-3 gap-y-1">
                {gruposMeta.map((gm, idx) => (
                  <div key={gm.key} className="flex items-center gap-1 min-w-0">
                    <span
                      className="w-2 h-2 rounded-full flex-shrink-0"
                      style={{ background: STACK_COLORS[idx % STACK_COLORS.length] }}
                    />
                    <span
                      className={`text-xs truncate max-w-[110px] ${isDark ? 'text-gray-400' : 'text-gray-500'}`}
                      title={gm.nome}
                    >
                      {gm.nome}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </>
        )}

        {data && !loading && viewMode === 'total' && (
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
              const dotColor = STACK_COLORS[idx % STACK_COLORS.length];
              return (
                <div key={ev.evento_grupo} className="group">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-sm w-5 text-center flex-shrink-0">
                      {MEDAL[idx] ?? (
                        <span className={`text-xs font-bold ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>{idx + 1}</span>
                      )}
                    </span>
                    {/* Bolinha de cor correspondente ao gráfico empilhado */}
                    <span
                      className="w-2 h-2 rounded-full flex-shrink-0"
                      style={{ background: dotColor }}
                    />
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
                  <div className={`ml-10 h-1.5 rounded-full ${isDark ? 'bg-gray-700' : 'bg-gray-100'} overflow-hidden`}>
                    <div
                      className="h-full rounded-full transition-all duration-500"
                      style={{ width: `${barPct}%`, background: dotColor, opacity: 0.75 }}
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
