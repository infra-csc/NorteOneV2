import React from 'react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Cell,
} from 'recharts';
import { TrendingUp, TrendingDown, Minus, Trophy, BarChart2, Info } from 'lucide-react';

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

const fmtNum = (v: number) => new Intl.NumberFormat('pt-BR').format(v);

const fmtDate = (iso: string) => {
  const [, m, d] = iso.split('-');
  return `${d}/${m}`;
};

const BAR_COLOR_DARK = '#818cf8';
const BAR_COLOR_LIGHT = '#6366f1';

const MEDAL: Record<number, string> = { 0: '🥇', 1: '🥈', 2: '🥉' };

const SkeletonBar: React.FC<{ isDark: boolean }> = ({ isDark }) => (
  <div className={`h-4 rounded-full animate-pulse ${isDark ? 'bg-gray-700' : 'bg-gray-200'}`} />
);

const CustomTooltipDaily: React.FC<any> = ({ active, payload, label, isDark, dayGruposMap, gruposMeta }) => {
  if (!active || !payload?.length) return null;
  const total: number = payload[0]?.value ?? 0;

  // per-event rows for this day, sorted desc, non-zero only
  const dateKey = payload[0]?.payload?.data as string | undefined;
  const gruposOnDay = dateKey ? (dayGruposMap[dateKey] ?? []) : [];
  const rows = gruposOnDay.filter((r: any) => r.count > 0);

  return (
    <div className={`px-3 py-2.5 rounded-xl shadow-xl border text-xs ${isDark ? 'bg-gray-800 border-gray-700 text-white' : 'bg-white border-gray-200 text-gray-900'}`}
      style={{ minWidth: 460, maxWidth: 640 }}>
      <div className="flex items-center justify-between mb-2">
        <span className={`font-bold text-sm ${isDark ? 'text-white' : 'text-gray-900'}`}>{label}</span>
        <span className={`font-black text-sm ml-4 ${isDark ? 'text-indigo-300' : 'text-indigo-600'}`}>{fmtNum(total)}</span>
      </div>
      {rows.length > 0 && (
        <>
          <div className={`border-t mb-1.5 ${isDark ? 'border-gray-700' : 'border-gray-100'}`} />
          <div className="space-y-1.5">
            {rows.map((r: any) => {
              const pct = total > 0 ? Math.round((r.count / total) * 100) : 0;
              return (
                <div key={r.key} className="flex items-center gap-2">
                  <span className={`flex-1 leading-tight ${isDark ? 'text-gray-300' : 'text-gray-600'}`}>
                    {r.nome}
                  </span>
                  <span className={`flex-shrink-0 tabular-nums font-semibold text-right ${isDark ? 'text-gray-100' : 'text-gray-800'}`}
                    style={{ minWidth: 36 }}>
                    {fmtNum(r.count)}
                  </span>
                  <span className={`flex-shrink-0 text-right tabular-nums ${isDark ? 'text-gray-500' : 'text-gray-400'}`}
                    style={{ minWidth: 32 }}>
                    {pct}%
                  </span>
                </div>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
};

const InscricoesDiariasPanel: React.FC<Props> = ({ data, loading, isDark }) => {
  const cardClass = `rounded-2xl ${isDark ? 'bg-gray-800/60 backdrop-blur-xl border border-gray-700/50' : 'bg-white/80 backdrop-blur-xl border border-gray-200/80'}`;

  const maxTotal = data ? Math.max(...data.diario.map(d => d.total), 1) : 1;
  const gruposMeta = data?.grupos_meta ?? [];

  // Map: date_iso → [{key, nome, count}] sorted desc by count
  const dayGruposMap = React.useMemo<Record<string, { key: string; nome: string; count: number }[]>>(() => {
    if (!data?.diario_por_grupo || !gruposMeta.length) return {};
    const map: Record<string, { key: string; nome: string; count: number }[]> = {};
    for (const entry of data.diario_por_grupo) {
      map[entry.data] = gruposMeta
        .map(gm => ({ key: gm.key, nome: gm.nome, count: entry.grupos[gm.key] ?? 0 }))
        .sort((a, b) => b.count - a.count);
    }
    return map;
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
      {/* Gráfico de barras diário */}
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
            {Array.from({ length: 5 }).map((_, i) => <SkeletonBar key={i} isDark={isDark} />)}
          </div>
        ) : isEmpty ? (
          <div className={`flex items-center justify-center h-40 text-sm ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>
            Sem dados de inscrições no período
          </div>
        ) : (
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
                content={<CustomTooltipDaily isDark={isDark} dayGruposMap={dayGruposMap} gruposMeta={gruposMeta} />}
                cursor={{ fill: isDark ? 'rgba(99,102,241,0.1)' : 'rgba(99,102,241,0.05)' }}
              />
              <Bar dataKey="total" radius={[6, 6, 0, 0]}>
                {data!.diario.map(entry => (
                  <Cell
                    key={entry.data}
                    fill={isDark ? BAR_COLOR_DARK : BAR_COLOR_LIGHT}
                    opacity={entry.total === maxTotal ? 1 : 0.65}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        )}

        {data && !loading && !isEmpty && (
          <div className={`mt-3 pt-3 border-t ${isDark ? 'border-gray-700/60' : 'border-gray-100'} flex items-center justify-between`}>
            <span className={`text-xs ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Total no período</span>
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
          <div className="flex-1">
            <h3 className={`text-sm font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>
              TOP 10 Eventos
            </h3>
            <p className={`text-xs ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
              Mais vendidos hoje e ontem
            </p>
          </div>
          <div className="group relative flex-shrink-0">
            <Info className={`w-4 h-4 cursor-help ${isDark ? 'text-gray-500 hover:text-gray-300' : 'text-gray-400 hover:text-gray-600'}`} />
            <div className={`
              pointer-events-none absolute right-0 top-6 z-50 w-64 rounded-xl p-3 shadow-xl
              opacity-0 group-hover:opacity-100 transition-opacity duration-150
              ${isDark ? 'bg-gray-900 border border-gray-700 text-gray-200' : 'bg-white border border-gray-200 text-gray-700'}
            `}>
              <p className={`text-xs font-semibold mb-2.5 ${isDark ? 'text-white' : 'text-gray-900'}`}>Como ler os números</p>

              {/* Number on the right */}
              <div className="flex items-start gap-2 mb-2.5">
                <span className={`text-xs font-black flex-shrink-0 mt-0.5 w-8 text-right ${isDark ? 'text-white' : 'text-gray-900'}`}>31</span>
                <p className="text-xs leading-snug"><span className={`font-semibold ${isDark ? 'text-white' : 'text-gray-900'}`}>Total de hoje e ontem</span> — soma das inscrições do dia atual (estimativa ao vivo) com as de ontem (snapshot). É o critério de ordenação do ranking.</p>
              </div>

              {/* Divider */}
              <div className={`border-t mb-2.5 ${isDark ? 'border-gray-700' : 'border-gray-100'}`} />

              {/* Variation badge */}
              <div className="flex items-start gap-2 mb-2.5">
                <span className="flex items-center gap-0.5 text-xs font-semibold text-emerald-400 flex-shrink-0 mt-0.5 w-8 justify-end">
                  <TrendingUp className="w-3 h-3" />+31
                </span>
                <p className="text-xs leading-snug"><span className="font-semibold text-emerald-400">Variação</span> = inscrições de hoje + ontem <span className={`font-semibold ${isDark ? 'text-white' : 'text-gray-900'}`}>menos</span> as inscrições de anteontem.</p>
              </div>

              {/* Period diagram */}
              <div className={`rounded-lg p-2 text-xs ${isDark ? 'bg-gray-800' : 'bg-gray-50'}`}>
                <div className="flex items-center gap-1 mb-1">
                  <div className={`w-2 h-2 rounded-sm flex-shrink-0 ${isDark ? 'bg-gray-600' : 'bg-gray-300'}`} />
                  <span className={isDark ? 'text-gray-400' : 'text-gray-500'}>Anteontem → período anterior (comparação)</span>
                </div>
                <div className="flex items-center gap-1">
                  <div className="w-2 h-2 rounded-sm flex-shrink-0 bg-indigo-500" />
                  <span className={isDark ? 'text-gray-300' : 'text-gray-600'}>Ontem + hoje → período atual (ranking)</span>
                </div>
              </div>

              {/* Example */}
              <div className={`mt-2 rounded-lg p-2 text-xs ${isDark ? 'bg-gray-800' : 'bg-gray-50'}`}>
                <p className={`mb-1 font-semibold ${isDark ? 'text-gray-300' : 'text-gray-600'}`}>Exemplo: badge <span className="text-red-400">−5</span></p>
                <p className={isDark ? 'text-gray-400' : 'text-gray-500'}>12 inscrições (hoje + ontem) − 17 (anteontem) = −5. O evento vendeu menos nestes 2 dias do que no dia anterior.</p>
              </div>
            </div>
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
                <div key={ev.evento_grupo}>
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
                      className="h-full rounded-full transition-all duration-500"
                      style={{ width: `${barPct}%`, background: isDark ? BAR_COLOR_DARK : BAR_COLOR_LIGHT, opacity: 0.6 }}
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
