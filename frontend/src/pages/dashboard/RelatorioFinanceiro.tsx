import React, { useState } from 'react';
import { useTheme } from '../../context/ThemeContext';
import {
  ChevronDown, ChevronRight, TrendingUp, TrendingDown,
  BarChart2, Calendar, DollarSign
} from 'lucide-react';

const formatCurrency = (value: number) =>
  new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL', minimumFractionDigits: 0, maximumFractionDigits: 0 }).format(value);

const formatNumber = (value: number) =>
  new Intl.NumberFormat('pt-BR').format(value);

const formatPct = (value: number) =>
  `${value.toFixed(1)}%`;

interface EventoRow {
  id_evento: number;
  nome_evento: string;
  data_evento: string;
  receita_orcada: number;
  receita_realizada: number;
  ticket_medio: number;
  custo_kit_unit: number;
  custo_kit_total: number;
  margem_liquida: number;
  margem_percentual: number;
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
  custo_total: number;
  margem_bruta: number;
  margem_percentual: number;
  n_eventos: number;
}

interface Props {
  data: { meses: MesRow[] };
  loading?: boolean;
}

const MargemBadge: React.FC<{ value: number; pct: number }> = ({ value, pct }) => {
  const positive = value >= 0;
  return (
    <div className={`flex flex-col items-end`}>
      <span className={`text-sm font-bold ${positive ? 'text-emerald-400' : 'text-red-400'}`}>
        {formatCurrency(value)}
      </span>
      <span className={`text-xs font-medium flex items-center gap-0.5 ${positive ? 'text-emerald-500' : 'text-red-500'}`}>
        {positive
          ? <TrendingUp className="w-3 h-3" />
          : <TrendingDown className="w-3 h-3" />}
        {formatPct(pct)}
      </span>
    </div>
  );
};

const RelatorioFinanceiro: React.FC<Props> = ({ data, loading }) => {
  const { isDark } = useTheme();
  const [expandedMonths, setExpandedMonths] = useState<Set<string>>(new Set());

  const cardClass = `rounded-2xl ${isDark ? 'bg-gray-800/60 backdrop-blur-xl border border-gray-700/50' : 'bg-white/80 backdrop-blur-xl border border-gray-200/80'}`;
  const rowClass = (idx: number) =>
    idx % 2 === 0
      ? isDark ? 'bg-gray-700/20' : 'bg-gray-50/60'
      : '';

  const toggleMonth = (key: string) => {
    setExpandedMonths(prev => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const meses = data?.meses || [];

  const totalReceita = meses.reduce((s, m) => s + m.receita_liquida, 0);
  const totalOrcado = meses.reduce((s, m) => s + m.receita_orcada_total, 0);
  const totalCusto = meses.reduce((s, m) => s + m.custo_total, 0);
  const totalMargem = meses.reduce((s, m) => s + m.margem_bruta, 0);
  const totalMargemPct = totalReceita > 0 ? totalMargem / totalReceita * 100 : 0;

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
          <div className="flex items-center gap-6 text-xs flex-wrap">
            <div className="flex flex-col items-end">
              <span className={isDark ? 'text-gray-400' : 'text-gray-500'}>Receita Total</span>
              <span className={`font-bold text-sm ${isDark ? 'text-white' : 'text-gray-900'}`}>{formatCurrency(totalReceita)}</span>
            </div>
            <div className="flex flex-col items-end">
              <span className={isDark ? 'text-gray-400' : 'text-gray-500'}>Custo de Kit</span>
              <span className={`font-bold text-sm ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>{formatCurrency(totalCusto)}</span>
            </div>
            <div className="flex flex-col items-end">
              <span className={isDark ? 'text-gray-400' : 'text-gray-500'}>Margem Total</span>
              <MargemBadge value={totalMargem} pct={totalMargemPct} />
            </div>
          </div>
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
                Rec. Orçada
              </th>
              <th className={`px-4 py-3 text-right text-xs font-bold uppercase tracking-wider ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                Rec. Realizada
              </th>
              <th className={`px-4 py-3 text-right text-xs font-bold uppercase tracking-wider ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                Custo Kit
              </th>
              <th className={`px-4 py-3 text-right text-xs font-bold uppercase tracking-wider ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                Margem
              </th>
            </tr>
          </thead>
          <tbody className={`divide-y ${isDark ? 'divide-gray-700/30' : 'divide-gray-100'}`}>
            {meses.map((mes, mIdx) => {
              const isExpanded = expandedMonths.has(mes.mes_key);
              const allEventsHaveCusto = mes.eventos.some(ev => ev.custo_kit_total > 0);

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
                        <span className={`text-emerald-400 flex-shrink-0`}>
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
                    <td className={`px-4 py-3 text-right ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                      {mes.receita_orcada_total > 0 ? formatCurrency(mes.receita_orcada_total) : <span className="text-gray-400">—</span>}
                    </td>
                    <td className={`px-4 py-3 text-right font-semibold ${isDark ? 'text-blue-300' : 'text-blue-700'}`}>
                      {mes.receita_liquida > 0 ? formatCurrency(mes.receita_liquida) : <span className="text-gray-400">—</span>}
                    </td>
                    <td className={`px-4 py-3 text-right ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                      {allEventsHaveCusto ? formatCurrency(mes.custo_total) : <span className="text-xs text-gray-400">sem custo</span>}
                    </td>
                    <td className="px-4 py-3 text-right">
                      {mes.receita_liquida > 0 && allEventsHaveCusto
                        ? <MargemBadge value={mes.margem_bruta} pct={mes.margem_percentual} />
                        : <span className="text-xs text-gray-400">—</span>
                      }
                    </td>
                  </tr>

                  {isExpanded && mes.eventos.map((ev, evIdx) => (
                    <tr
                      key={ev.id_evento}
                      className={`transition-colors ${rowClass(evIdx)} ${
                        isDark ? 'hover:bg-gray-700/30' : 'hover:bg-gray-50'
                      }`}
                    >
                      <td className="px-4 py-2.5 pl-12">
                        <div className="flex items-center gap-2">
                          <DollarSign className={`w-3 h-3 flex-shrink-0 ${isDark ? 'text-gray-500' : 'text-gray-400'}`} />
                          <div>
                            <p className={`text-xs font-medium ${isDark ? 'text-gray-200' : 'text-gray-800'}`}>
                              {ev.nome_evento}
                            </p>
                            <p className={`text-xs ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>
                              {new Date(ev.data_evento + 'T00:00:00').toLocaleDateString('pt-BR')}
                              {ev.ticket_medio > 0 && ` · TKT ${formatCurrency(ev.ticket_medio)}`}
                            </p>
                          </div>
                        </div>
                      </td>
                      <td className={`px-4 py-2.5 text-right text-xs ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>
                        {formatNumber(ev.atletas)}
                      </td>
                      <td className={`px-4 py-2.5 text-right text-xs ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                        {ev.receita_orcada > 0 ? formatCurrency(ev.receita_orcada) : <span className="text-gray-400">—</span>}
                      </td>
                      <td className={`px-4 py-2.5 text-right text-xs font-medium ${isDark ? 'text-blue-300' : 'text-blue-600'}`}>
                        {ev.receita_realizada > 0 ? formatCurrency(ev.receita_realizada) : <span className="text-gray-400">—</span>}
                      </td>
                      <td className={`px-4 py-2.5 text-right text-xs ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                        {ev.custo_kit_total > 0
                          ? formatCurrency(ev.custo_kit_total)
                          : <span className="text-xs text-gray-400">sem custo</span>}
                      </td>
                      <td className="px-4 py-2.5 text-right">
                        {ev.receita_realizada > 0 && ev.custo_kit_total > 0
                          ? <MargemBadge value={ev.margem_liquida} pct={ev.margem_percentual} />
                          : ev.receita_realizada > 0
                            ? <span className="text-xs text-gray-400">sem custo kit</span>
                            : <span className="text-xs text-gray-400">—</span>
                        }
                      </td>
                    </tr>
                  ))}
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
              <td className={`px-4 py-3 text-right font-semibold text-xs ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                {totalOrcado > 0 ? formatCurrency(totalOrcado) : '—'}
              </td>
              <td className={`px-4 py-3 text-right font-bold text-xs ${isDark ? 'text-blue-300' : 'text-blue-700'}`}>
                {formatCurrency(totalReceita)}
              </td>
              <td className={`px-4 py-3 text-right font-semibold text-xs ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                {totalCusto > 0 ? formatCurrency(totalCusto) : '—'}
              </td>
              <td className="px-4 py-3 text-right">
                {totalReceita > 0 && totalCusto > 0
                  ? <MargemBadge value={totalMargem} pct={totalMargemPct} />
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
