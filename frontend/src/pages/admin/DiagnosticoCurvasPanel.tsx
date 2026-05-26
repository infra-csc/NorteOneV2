import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useTheme } from '../../context/ThemeContext';
import { marketingService } from '../../services/api';
import { RefreshCw, Search, TrendingUp, AlertTriangle, Pin, Activity, Zap, MapPin, Layers } from 'lucide-react';

interface CurvaItem {
  evento_grupo: string;
  circuito: string | null;
  cidade: string | null;
  estado: string | null;
  data_evento: string | null;
  tipo_curva: string | null;
  fonte_curva: string | null;
  ano_referencia: number | null;
  tem_override: boolean;
  override_target: string | null;
  fabricated_linear: boolean;
  sales_goal: number;
  tem_mapeamento: boolean;
  erro?: string;
}

const TIPO_CONFIG: Record<string, { label: string; icon: any; classLight: string; classDark: string; desc: string }> = {
  manual: { label: 'Manual (Override)', icon: Pin, classLight: 'bg-purple-100 text-purple-800 border-purple-200', classDark: 'bg-purple-900/30 text-purple-300 border-purple-700/40', desc: 'Curva apontada manualmente pelo usuário' },
  historico: { label: 'Histórico Próprio', icon: TrendingUp, classLight: 'bg-emerald-100 text-emerald-800 border-emerald-200', classDark: 'bg-emerald-900/30 text-emerald-300 border-emerald-700/40', desc: 'Histórico do próprio evento no ano anterior' },
  circuito_similar: { label: 'Circuito + Cidade', icon: MapPin, classLight: 'bg-blue-100 text-blue-800 border-blue-200', classDark: 'bg-blue-900/30 text-blue-300 border-blue-700/40', desc: 'Outro evento do mesmo circuito na mesma cidade' },
  circuito: { label: 'Circuito', icon: Layers, classLight: 'bg-cyan-100 text-cyan-800 border-cyan-200', classDark: 'bg-cyan-900/30 text-cyan-300 border-cyan-700/40', desc: 'Outro evento do mesmo circuito (cidade diferente)' },
  regional: { label: 'Regional', icon: MapPin, classLight: 'bg-amber-100 text-amber-800 border-amber-200', classDark: 'bg-amber-900/30 text-amber-300 border-amber-700/40', desc: 'Média da região (estado) do evento' },
  linear: { label: 'Linear Fabricada', icon: Zap, classLight: 'bg-orange-100 text-orange-800 border-orange-200', classDark: 'bg-orange-900/30 text-orange-300 border-orange-700/40', desc: 'Distribuição linear (último recurso, sem histórico)' },
};

function formatDate(iso: string | null): string {
  if (!iso) return '—';
  try {
    return new Date(iso + 'T00:00:00').toLocaleDateString('pt-BR');
  } catch {
    return iso;
  }
}

function daysUntil(iso: string | null): number | null {
  if (!iso) return null;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const d = new Date(iso + 'T00:00:00');
  return Math.round((d.getTime() - today.getTime()) / 86400000);
}

const DiagnosticoCurvasPanel: React.FC = () => {
  const { isDark } = useTheme();
  const [data, setData] = useState<CurvaItem[]>([]);
  const [ano, setAno] = useState<number>(new Date().getFullYear());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filterTipo, setFilterTipo] = useState<string>('');
  const [busca, setBusca] = useState<string>('');
  const [onlyFuture, setOnlyFuture] = useState<boolean>(true);

  const cardBase = isDark
    ? 'bg-gray-800/50 backdrop-blur-sm border border-gray-700/50'
    : 'bg-white/80 backdrop-blur-sm border border-gray-200 shadow-sm';
  const textPrimary = isDark ? 'text-white' : 'text-gray-900';
  const textSecondary = isDark ? 'text-gray-400' : 'text-gray-500';
  const inputClass = `px-3 py-2 rounded-lg border text-sm outline-none transition-colors ${isDark ? 'bg-gray-700 border-gray-600 text-white placeholder-gray-400 focus:border-blue-500' : 'bg-white border-gray-300 text-gray-900 placeholder-gray-400 focus:border-blue-400'}`;

  const fetchData = useCallback(async (forceRefresh = false) => {
    setLoading(true);
    setError(null);
    try {
      const res = await marketingService.getDiagnosticoCurvas(ano, undefined, forceRefresh);
      setData(res.eventos || []);
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Erro ao carregar diagnóstico de curvas');
    } finally {
      setLoading(false);
    }
  }, [ano]);

  useEffect(() => { fetchData(false); }, [fetchData]);

  const filtered = useMemo(() => {
    const q = busca.trim().toLowerCase();
    return data.filter(item => {
      if (filterTipo && (item.tipo_curva || '') !== filterTipo) return false;
      if (onlyFuture && item.data_evento) {
        const d = daysUntil(item.data_evento);
        if (d !== null && d < 0) return false;
      }
      if (q) {
        const hay = [item.evento_grupo, item.circuito, item.cidade, item.estado, item.fonte_curva, item.override_target]
          .filter(Boolean).join(' ').toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }, [data, filterTipo, busca, onlyFuture]);

  const counts = useMemo(() => {
    const c: Record<string, number> = {};
    for (const i of data) {
      const k = i.tipo_curva || 'sem_dados';
      c[k] = (c[k] || 0) + 1;
    }
    return c;
  }, [data]);

  const totalsList = useMemo(() => {
    const order = ['manual', 'historico', 'circuito_similar', 'circuito', 'regional', 'linear'];
    return order.map(k => ({ key: k, count: counts[k] || 0, cfg: TIPO_CONFIG[k] })).filter(x => x.cfg);
  }, [counts]);

  return (
    <div className="space-y-4">
      <div className={`${cardBase} rounded-xl p-5`}>
        <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-3 mb-4">
          <div>
            <h2 className={`text-lg font-semibold ${textPrimary} flex items-center gap-2`}>
              <Activity className="w-5 h-5 text-blue-500" />
              Diagnóstico de Curvas D-%
            </h2>
            <p className={`text-xs ${textSecondary} mt-1`}>
              Mostra qual fonte de curva cada evento ativo está usando — sem precisar abrir um por um.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <label className={`text-xs ${textSecondary}`}>Ano:</label>
            <select className={inputClass} value={ano} onChange={e => setAno(Number(e.target.value))}>
              {[new Date().getFullYear() - 1, new Date().getFullYear(), new Date().getFullYear() + 1].map(y => (
                <option key={y} value={y}>{y}</option>
              ))}
            </select>
            <button
              onClick={() => fetchData(true)}
              disabled={loading}
              className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium bg-blue-600 hover:bg-blue-500 text-white disabled:opacity-50"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
              Atualizar
            </button>
          </div>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-2">
          {totalsList.map(({ key, count, cfg }) => {
            const Icon = cfg.icon;
            return (
              <button
                key={key}
                onClick={() => setFilterTipo(filterTipo === key ? '' : key)}
                className={`flex items-center gap-2 p-2.5 rounded-lg border text-left transition-all ${
                  filterTipo === key
                    ? (isDark ? cfg.classDark : cfg.classLight) + ' ring-2 ring-blue-500/50'
                    : (isDark ? 'bg-gray-700/30 border-gray-600/40 hover:bg-gray-700/60' : 'bg-gray-50 border-gray-200 hover:bg-gray-100')
                }`}
                title={cfg.desc}
              >
                <Icon className="w-4 h-4 flex-shrink-0" />
                <div className="min-w-0 flex-1">
                  <p className={`text-xs font-medium truncate ${filterTipo === key ? '' : textSecondary}`}>{cfg.label}</p>
                  <p className={`text-lg font-bold leading-tight ${filterTipo === key ? '' : textPrimary}`}>{count}</p>
                </div>
              </button>
            );
          })}
        </div>
      </div>

      <div className={`${cardBase} rounded-xl p-5`}>
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3 mb-4">
          <div className="relative flex-1 max-w-md">
            <Search className={`absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 ${textSecondary}`} />
            <input
              type="text"
              value={busca}
              onChange={e => setBusca(e.target.value)}
              placeholder="Buscar por evento, circuito, cidade, estado..."
              className={`${inputClass} pl-10 w-full`}
            />
          </div>
          <div className="flex items-center gap-3">
            <label className={`flex items-center gap-2 text-sm ${textPrimary} cursor-pointer`}>
              <input
                type="checkbox"
                checked={onlyFuture}
                onChange={e => setOnlyFuture(e.target.checked)}
                className="rounded"
              />
              Apenas eventos futuros
            </label>
            {filterTipo && (
              <button
                onClick={() => setFilterTipo('')}
                className={`text-xs px-2 py-1 rounded ${isDark ? 'bg-gray-700 text-gray-300 hover:bg-gray-600' : 'bg-gray-200 text-gray-700 hover:bg-gray-300'}`}
              >
                Limpar filtro: {TIPO_CONFIG[filterTipo]?.label}
              </button>
            )}
            <span className={`text-xs ${textSecondary}`}>
              {filtered.length} de {data.length}
            </span>
          </div>
        </div>

        {error && (
          <div className={`p-3 rounded-lg text-sm mb-3 ${isDark ? 'bg-red-900/30 text-red-300 border border-red-700/40' : 'bg-red-50 text-red-700 border border-red-200'}`}>
            <AlertTriangle className="w-4 h-4 inline mr-2" />{error}
          </div>
        )}

        {loading && data.length === 0 ? (
          <div className={`text-center py-8 ${textSecondary}`}>
            <RefreshCw className="w-6 h-6 animate-spin mx-auto mb-2" />
            Carregando diagnóstico (pode levar alguns segundos)...
          </div>
        ) : filtered.length === 0 ? (
          <div className={`text-center py-8 ${textSecondary}`}>Nenhum evento encontrado com os filtros atuais.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className={`text-left text-xs uppercase tracking-wider ${textSecondary} border-b ${isDark ? 'border-gray-700' : 'border-gray-200'}`}>
                  <th className="py-2 pr-3 font-medium">Evento</th>
                  <th className="py-2 pr-3 font-medium">Circuito / Local</th>
                  <th className="py-2 pr-3 font-medium">Data</th>
                  <th className="py-2 pr-3 font-medium">Curva em Uso</th>
                  <th className="py-2 pr-3 font-medium">Fonte</th>
                  <th className="py-2 pr-3 font-medium">Ano Ref.</th>
                  <th className="py-2 pr-3 font-medium text-right">Meta</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((item, idx) => {
                  const tipo = item.tipo_curva || 'sem_dados';
                  const cfg = TIPO_CONFIG[tipo];
                  const Icon = cfg?.icon || AlertTriangle;
                  const dias = daysUntil(item.data_evento);
                  return (
                    <tr
                      key={`${item.evento_grupo}-${idx}`}
                      className={`border-b ${isDark ? 'border-gray-700/50 hover:bg-gray-700/30' : 'border-gray-100 hover:bg-gray-50'}`}
                    >
                      <td className="py-2.5 pr-3">
                        <div className={`font-medium ${textPrimary}`}>{item.evento_grupo}</div>
                        {item.tem_override && (
                          <div className={`text-xs ${isDark ? 'text-purple-300' : 'text-purple-700'} flex items-center gap-1 mt-0.5`}>
                            <Pin className="w-3 h-3" /> Override: {item.override_target}
                          </div>
                        )}
                        {!item.tem_mapeamento && (
                          <div className={`text-xs ${isDark ? 'text-yellow-300' : 'text-yellow-700'} mt-0.5`}>
                            Sem mapeamento de SKU para {ano}
                          </div>
                        )}
                      </td>
                      <td className={`py-2.5 pr-3 ${textSecondary} text-xs`}>
                        {item.circuito || '—'}
                        <div>{[item.cidade, item.estado].filter(Boolean).join(' / ') || '—'}</div>
                      </td>
                      <td className={`py-2.5 pr-3 text-xs ${textSecondary}`}>
                        {formatDate(item.data_evento)}
                        {dias !== null && (
                          <div className={dias < 0 ? 'text-gray-400' : dias < 30 ? 'text-orange-500 font-medium' : ''}>
                            {dias < 0 ? `${Math.abs(dias)}d atrás` : `em ${dias}d`}
                          </div>
                        )}
                      </td>
                      <td className="py-2.5 pr-3">
                        {cfg ? (
                          <span className={`inline-flex items-center gap-1.5 px-2 py-1 rounded-md text-xs font-medium border ${isDark ? cfg.classDark : cfg.classLight}`} title={cfg.desc}>
                            <Icon className="w-3.5 h-3.5" />
                            {cfg.label}
                          </span>
                        ) : (
                          <span className={`text-xs ${textSecondary}`}>{item.erro || 'sem dados'}</span>
                        )}
                      </td>
                      <td className={`py-2.5 pr-3 text-xs ${textPrimary}`}>
                        {item.fonte_curva || (item.fabricated_linear ? <span className={textSecondary}>—</span> : <span className={textSecondary}>{item.evento_grupo}</span>)}
                      </td>
                      <td className={`py-2.5 pr-3 text-xs ${textSecondary}`}>
                        {item.ano_referencia ?? '—'}
                      </td>
                      <td className={`py-2.5 pr-3 text-xs text-right ${textPrimary} tabular-nums`}>
                        {item.sales_goal > 0 ? item.sales_goal.toLocaleString('pt-BR') : '—'}
                      </td>
                    </tr>
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

export default DiagnosticoCurvasPanel;
