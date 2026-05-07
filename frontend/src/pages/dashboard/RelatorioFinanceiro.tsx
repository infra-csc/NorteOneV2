import React, { useState } from 'react';
import { useTheme } from '../../context/ThemeContext';
import { usePermissions } from '../../context/PermissionContext';
import { marketingApi } from '../../services/api';
import {
  ChevronDown, ChevronRight,
  BarChart2, Calendar, RefreshCw
} from 'lucide-react';

const formatCurrency = (value: number) =>
  new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL', minimumFractionDigits: 0, maximumFractionDigits: 0 }).format(value);

const formatNumber = (value: number) =>
  new Intl.NumberFormat('pt-BR').format(value);


interface EventoRow {
  id_evento: number;
  evento_id?: string;
  nome_evento: string;
  data_evento: string;
  receita_realizada: number;
  ticket_medio: number;
  margem_orcada: number;
  margem_orcada_pct: number;
  margem_realizada: number;
  margem_realizada_pct: number;
  atletas: number;
}

interface MesRow {
  mes_key: string;
  mes_num: number;
  ano_num: number;
  mes_label: string;
  eventos: EventoRow[];
  receita_orcada_total: number;
  receita_liquida: number;
  margem_orcada_total: number;
  margem_orcada_pct: number;
  margem_realizada_total: number;
  margem_realizada_pct: number;
  n_eventos: number;
}

interface Props {
  data: { meses: MesRow[] };
  loading?: boolean;
  onRefresh?: () => void;
}

const DeltaBadge: React.FC<{ value: number; small?: boolean }> = ({ value, small }) => {
  const positive = value >= 0;
  const size = small ? 'text-xs' : 'text-sm';
  return (
    <div className="flex flex-col items-end">
      <span className={`${size} font-bold ${positive ? 'text-emerald-400' : 'text-red-400'}`}>
        {positive ? '+' : ''}{formatCurrency(value)}
      </span>
    </div>
  );
};

const MargemBadge: React.FC<{ value: number; small?: boolean }> = ({ value, small }) => {
  const { isDark } = useTheme();
  const size = small ? 'text-xs' : 'text-sm';
  return (
    <div className="flex flex-col items-end">
      <span className={`${size} font-bold ${isDark ? 'text-blue-300/80' : 'text-blue-600/80'}`}>
        {formatCurrency(value)}
      </span>
    </div>
  );
};

const RelatorioFinanceiro: React.FC<Props> = ({ data, loading, onRefresh }) => {
  const { isDark } = useTheme();
  const { permissions } = usePermissions();
  const isAdmin = permissions?.is_admin === true;

  const [expandedMonths, setExpandedMonths] = useState<Set<string>>(new Set());
  const [recalculating, setRecalculating] = useState<Set<string>>(new Set());
  const [recalcMessages, setRecalcMessages] = useState<Record<string, string>>({});

  const cardClass = `rounded-2xl ${isDark ? 'bg-gray-800/60 backdrop-blur-xl border border-gray-700/50' : 'bg-white/80 backdrop-blur-xl border border-gray-200/80'}`;

  const toggleMonth = (key: string) => {
    setExpandedMonths(prev => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const handleRecalcular = async (ev: EventoRow) => {
    const key = ev.evento_id || String(ev.id_evento);
    if (!key || recalculating.has(key)) return;

    setRecalculating(prev => new Set(prev).add(key));
    setRecalcMessages(prev => ({ ...prev, [key]: '' }));

    try {
      const res = await marketingApi.recalcularSnapshot(key);
      const msg = res.margem_recalculada != null
        ? `Margem recalculada: ${formatCurrency(res.margem_recalculada)}`
        : 'Snapshot atualizado';
      setRecalcMessages(prev => ({ ...prev, [key]: msg }));
      if (onRefresh) setTimeout(onRefresh, 800);
    } catch (err: any) {
      const detail = err?.response?.data?.detail || 'Erro ao recalcular';
      setRecalcMessages(prev => ({ ...prev, [key]: `⚠ ${detail}` }));
    } finally {
      setRecalculating(prev => {
        const next = new Set(prev);
        next.delete(key);
        return next;
      });
    }
  };

  const meses = data?.meses || [];

  const totalReceita = meses.reduce((s, m) => s + m.receita_liquida, 0);
  const totalMargemOrcada = meses.reduce((s, m) => s + m.margem_orcada_total, 0);
  const totalOrcado = meses.reduce((s, m) => s + m.receita_orcada_total, 0);
  const totalMargemRealizada = meses.reduce((s, m) => s + m.margem_realizada_total, 0);

  if (loading) {
    return (
      <div className={`${cardClass} p-6`}>
        <div className="flex items-center gap-2 text-sm text-gray-400">
          <div className="w-4 h-4 border-2 border-emerald-400 border-t-transparent rounded-full animate-spin" />
          Carregando relatório financeiro...
        </div>
      </div>
    );
  }

  if (!meses.length) {
    return (
      <div className={`${cardClass} p-6`}>
        <p className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Nenhum dado financeiro disponível para o período selecionado.</p>
      </div>
    );
  }

  return (
    <div className={`${cardClass} overflow-hidden`}>
      <div className={`px-6 py-4 border-b ${isDark ? 'border-gray-700/50' : 'border-gray-200/80'}`}>
        <div className="flex items-center justify-between flex-wrap gap-3">
          <h3 className={`text-sm font-bold flex items-center gap-2 ${isDark ? 'text-white' : 'text-gray-900'}`}>
            <BarChart2 className="w-4 h-4 text-emerald-400" />
            Resultado por Mês e Evento
          </h3>
          {isAdmin && (
            <span className={`text-[10px] px-2 py-0.5 rounded-full ${isDark ? 'bg-gray-700 text-gray-400' : 'bg-gray-200 text-gray-500'}`}>
              ↺ disponível para eventos concluídos
            </span>
          )}
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm min-w-[700px]">
          <thead>
            <tr className={`${isDark ? 'bg-gray-700/40' : 'bg-gray-50'}`}>
              <th className={`px-4 py-3 text-left text-xs font-bold uppercase tracking-wider ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                Mês / Evento
              </th>
              <th className={`px-4 py-3 text-right text-xs font-bold uppercase tracking-wider ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                Atletas
              </th>
              <th className={`px-4 py-3 text-right text-xs font-bold uppercase tracking-wider ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                Rec. Realizada
              </th>
              <th className={`px-4 py-3 text-right text-xs font-bold uppercase tracking-wider ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                Margem Orçada
              </th>
              <th className={`px-4 py-3 text-right text-xs font-bold uppercase tracking-wider ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                Margem Realizada
              </th>
              <th className={`px-4 py-3 text-right text-xs font-bold uppercase tracking-wider ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                Real vs Orç
              </th>
            </tr>
          </thead>
          <tbody className={`divide-y ${isDark ? 'divide-gray-700/30' : 'divide-gray-100'}`}>
            {meses.map((mes) => {
              const isExpanded = expandedMonths.has(mes.mes_key);

              return (
                <React.Fragment key={mes.mes_key}>
                  <tr
                    onClick={() => toggleMonth(mes.mes_key)}
                    className={`cursor-pointer transition-colors ${
                      isDark
                        ? 'hover:bg-emerald-500/5 bg-gray-800/40'
                        : 'hover:bg-emerald-50/60 bg-gray-50/80'
                    }`}
                  >
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <span className="text-emerald-400 flex-shrink-0">
                          {isExpanded
                            ? <ChevronDown className="w-4 h-4" />
                            : <ChevronRight className="w-4 h-4" />}
                        </span>
                        <Calendar className={`w-3.5 h-3.5 flex-shrink-0 ${isDark ? 'text-gray-400' : 'text-gray-400'}`} />
                        <span className={`font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>
                          {mes.mes_label}
                        </span>
                        <span className={`text-xs px-1.5 py-0.5 rounded-full ${isDark ? 'bg-gray-700 text-gray-400' : 'bg-gray-200 text-gray-600'}`}>
                          {mes.n_eventos} evento{mes.n_eventos !== 1 ? 's' : ''}
                        </span>
                      </div>
                    </td>
                    <td className={`px-4 py-3 text-right font-semibold ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
                      {formatNumber(mes.eventos.reduce((s, ev) => s + ev.atletas, 0))}
                    </td>
                    <td className={`px-4 py-3 text-right text-xs ${isDark ? 'text-blue-300/80' : 'text-blue-600/80'}`}>
                      {mes.receita_liquida > 0 ? formatCurrency(mes.receita_liquida) : <span className="text-gray-400">—</span>}
                    </td>
                    <td className="px-4 py-3 text-right">
                      {mes.receita_orcada_total > 0
                        ? <MargemBadge value={mes.margem_orcada_total} />
                        : <span className="text-xs text-gray-400">—</span>
                      }
                    </td>
                    <td className="px-4 py-3 text-right">
                      {mes.receita_liquida > 0
                        ? <MargemBadge value={mes.margem_realizada_total} />
                        : <span className="text-xs text-gray-400">—</span>
                      }
                    </td>
                    <td className="px-4 py-3 text-right">
                      {mes.receita_orcada_total > 0 || mes.receita_liquida > 0
                        ? <DeltaBadge value={mes.margem_realizada_total - mes.margem_orcada_total} />
                        : <span className="text-xs text-gray-400">—</span>
                      }
                    </td>
                  </tr>

                  {isExpanded && mes.eventos.map((ev) => {
                    const evKey = ev.evento_id || String(ev.id_evento);
                    const isCompleted = ev.receita_realizada > 0;
                    const isRecalculating = recalculating.has(evKey);
                    const recalcMsg = recalcMessages[evKey];
                    const isEventoPast = new Date(ev.data_evento + 'T00:00:00') < new Date();

                    return (
                      <tr
                        key={ev.id_evento}
                        className={`transition-colors ${
                          isDark
                            ? 'bg-gray-900/40 hover:bg-gray-900/60'
                            : 'bg-gray-50/90 hover:bg-gray-100/80'
                        }`}
                      >
                        <td className={`py-2 pl-10 pr-4 border-l-2 ${isDark ? 'border-emerald-500/25' : 'border-emerald-400/40'}`}>
                          <div className="flex items-start gap-2">
                            <span className={`text-[10px] leading-none font-bold select-none mt-1 ${isDark ? 'text-gray-600' : 'text-gray-300'}`}>▸</span>
                            <div className="flex-1 min-w-0">
                              <p className={`text-xs font-medium ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
                                {ev.nome_evento}
                              </p>
                              <p className={`text-[11px] ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>
                                {new Date(ev.data_evento + 'T00:00:00').toLocaleDateString('pt-BR')}
                                {ev.ticket_medio > 0 && ` · TKT ${formatCurrency(ev.ticket_medio)}`}
                              </p>
                              {recalcMsg && (
                                <p className={`text-[10px] mt-0.5 ${recalcMsg.startsWith('⚠') ? 'text-red-400' : 'text-emerald-400'}`}>
                                  {recalcMsg}
                                </p>
                              )}
                            </div>
                            {isAdmin && isCompleted && isEventoPast && ev.evento_id && (
                              <button
                                onClick={(e) => { e.stopPropagation(); handleRecalcular(ev); }}
                                disabled={isRecalculating}
                                title="Recalcular margem final a partir do Magento"
                                className={`flex-shrink-0 p-1 rounded transition-colors ${
                                  isRecalculating
                                    ? 'opacity-50 cursor-wait'
                                    : isDark
                                      ? 'text-gray-500 hover:text-emerald-400 hover:bg-emerald-500/10'
                                      : 'text-gray-400 hover:text-emerald-600 hover:bg-emerald-50'
                                }`}
                              >
                                <RefreshCw className={`w-3 h-3 ${isRecalculating ? 'animate-spin' : ''}`} />
                              </button>
                            )}
                          </div>
                        </td>
                        <td className={`px-4 py-2 text-right text-xs ${isDark ? 'text-gray-500' : 'text-gray-500'}`}>
                          {formatNumber(ev.atletas)}
                        </td>
                        <td className={`px-4 py-2 text-right text-xs ${isDark ? 'text-blue-300/60' : 'text-blue-500/70'}`}>
                          {ev.receita_realizada > 0 ? formatCurrency(ev.receita_realizada) : <span className="text-gray-400">—</span>}
                        </td>
                        <td className="px-4 py-2 text-right">
                          {ev.margem_orcada !== 0 || ev.margem_orcada_pct !== 0
                            ? <MargemBadge value={ev.margem_orcada} small />
                            : <span className="text-xs text-gray-400">—</span>
                          }
                        </td>
                        <td className="px-4 py-2 text-right">
                          {ev.receita_realizada > 0
                            ? <MargemBadge value={ev.margem_realizada} small />
                            : <span className="text-xs text-gray-400">—</span>
                          }
                        </td>
                        <td className="px-4 py-2 text-right">
                          {ev.receita_realizada > 0 || ev.margem_orcada !== 0
                            ? <DeltaBadge value={ev.margem_realizada - ev.margem_orcada} small />
                            : <span className="text-xs text-gray-400">—</span>
                          }
                        </td>
                      </tr>
                    );
                  })}
                </React.Fragment>
              );
            })}

            <tr className={`border-t-2 ${isDark ? 'border-gray-600 bg-gray-700/40' : 'border-gray-300 bg-gray-100/80'}`}>
              <td className="px-4 py-3">
                <span className={`font-black text-xs uppercase tracking-wider ${isDark ? 'text-white' : 'text-gray-900'}`}>
                  Total Geral
                </span>
              </td>
              <td className={`px-4 py-3 text-right font-bold text-xs ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
                {formatNumber(meses.reduce((s, m) => s + m.eventos.reduce((a, e) => a + e.atletas, 0), 0))}
              </td>
              <td className={`px-4 py-3 text-right font-bold text-xs ${isDark ? 'text-blue-300/80' : 'text-blue-700/80'}`}>
                {formatCurrency(totalReceita)}
              </td>
              <td className="px-4 py-3 text-right">
                {totalOrcado > 0
                  ? <MargemBadge value={totalMargemOrcada} />
                  : <span className="text-xs text-gray-400">—</span>}
              </td>
              <td className="px-4 py-3 text-right">
                {totalReceita > 0
                  ? <MargemBadge value={totalMargemRealizada} />
                  : <span className="text-xs text-gray-400">—</span>}
              </td>
              <td className="px-4 py-3 text-right">
                {totalOrcado > 0 || totalReceita > 0
                  ? <DeltaBadge value={totalMargemRealizada - totalMargemOrcada} />
                  : <span className="text-xs text-gray-400">—</span>}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default RelatorioFinanceiro;
