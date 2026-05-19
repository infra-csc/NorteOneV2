import React, { useState, useMemo } from 'react';
import { ArrowUpDown, ArrowDown, ArrowUp, Download } from 'lucide-react';

interface DailySaleRow {
  date: string;
  sales: number;
  expected: number;
  cumulativeSales?: number;
  cumulativeExpected?: number;
  dMinus?: number;
  curvaAnoAnterior?: number;
  dif?: number;
  atingimentoAcumulado?: number;
  atingimentoDiario?: number;
  normalizedSales?: number;
  isOutlier?: boolean;
  normalizedExpected?: number;
  cumulativeNormalizedExpected?: number;
  expectedIsOutlier?: boolean;
}

interface DailySalesTableProps {
  dailySales: DailySaleRow[];
  isDark: boolean;
  eventName?: string;
  salesGoal?: number;
  showNormalized?: boolean;
  onAtualizarHoje?: () => void;
  isLoading?: boolean;
}

const fmtInt = (v: number | undefined | null): string => {
  if (v == null || isNaN(v)) return '—';
  return Math.round(v).toLocaleString('pt-BR');
};

const fmtPct = (v: number | undefined | null, decimals = 1): string => {
  if (v == null || isNaN(v)) return '—';
  return `${v.toFixed(decimals)}%`;
};

const fmtDate = (dateStr: string): string => {
  const parts = dateStr.split('-');
  if (parts.length === 3) return `${parts[2]}/${parts[1]}/${parts[0]}`;
  return dateStr;
};

const colorClass = (v: number | undefined | null, isDark: boolean): string => {
  if (v == null || isNaN(v) || v === 0) return isDark ? 'text-gray-300' : 'text-gray-700';
  return v > 0 ? 'text-emerald-400' : 'text-red-400';
};

const DailySalesTable: React.FC<DailySalesTableProps> = ({ dailySales: dailySalesRaw, isDark, eventName, salesGoal, showNormalized = false, onAtualizarHoje, isLoading = false }) => {
  const [sortAsc, setSortAsc] = useState(false);

  const dailySales = useMemo(() => {
    if (!showNormalized) return dailySalesRaw;
    // Inscritos (sales) permanecem inalterados. Substituímos a META pela versão normalizada.
    return dailySalesRaw.map(d => {
      const exp = d.normalizedExpected != null ? d.normalizedExpected : d.expected;
      const cumExp = d.cumulativeNormalizedExpected != null ? d.cumulativeNormalizedExpected : d.cumulativeExpected;
      const atingDia = exp > 0 ? (d.sales / exp) * 100 : d.atingimentoDiario;
      const atingAcum = (cumExp && cumExp > 0 && d.cumulativeSales != null)
        ? (d.cumulativeSales / cumExp) * 100
        : d.atingimentoAcumulado;
      return {
        ...d,
        expected: exp,
        cumulativeExpected: cumExp,
        atingimentoDiario: atingDia,
        atingimentoAcumulado: atingAcum,
      };
    });
  }, [dailySalesRaw, showNormalized]);

  const sortedData = useMemo(() => {
    const data = [...dailySales];
    data.sort((a, b) => {
      const cmp = a.date.localeCompare(b.date);
      return sortAsc ? cmp : -cmp;
    });
    return data;
  }, [dailySales, sortAsc]);

  const totals = useMemo(() => {
    if (!dailySales.length) return null;
    const totalSales = dailySales.reduce((s, d) => s + d.sales, 0);
    const totalExpected = dailySales.reduce((s, d) => s + (d.expected || 0), 0);
    const lastRow = dailySales[dailySales.length - 1];
    const avgDailyAtingimento = dailySales.filter(d => d.atingimentoDiario != null && isFinite(d.atingimentoDiario!));
    const avgAtDia = avgDailyAtingimento.length > 0
      ? avgDailyAtingimento.reduce((s, d) => s + d.atingimentoDiario!, 0) / avgDailyAtingimento.length
      : null;
    return {
      totalSales,
      totalExpected,
      finalCumSales: lastRow?.cumulativeSales ?? totalSales,
      finalCumExpected: lastRow?.cumulativeExpected,
      finalAtingAcum: lastRow?.atingimentoAcumulado,
      avgAtingDia: avgAtDia,
      days: dailySales.length
    };
  }, [dailySales]);

  const globalMetrics = useMemo(() => {
    if (!dailySales.length) return null;
    const lastRow = [...dailySales].sort((a, b) => a.date.localeCompare(b.date))[dailySales.length - 1];
    const vendasGlobal = lastRow?.cumulativeSales ?? dailySales.reduce((s, d) => s + d.sales, 0);
    const metaGlobal = salesGoal && salesGoal > 0
      ? salesGoal
      : (lastRow?.cumulativeExpected ?? dailySales.reduce((s, d) => s + (d.expected || 0), 0));
    if (!metaGlobal || metaGlobal <= 0) return null;
    const atingGlobal = (vendasGlobal / metaGlobal) * 100;
    return {
      metaGlobal,
      vendasGlobal,
      atingGlobal,
    };
  }, [dailySales, salesGoal]);

  const handleExportCSV = () => {
    const headers = ['Data', 'D-', 'Meta Dia', 'Vendas Dia', 'Ating. Dia (%)', 'Meta Acum.', 'Vendas Acum.', 'Ating. Acum. (%)'];
    const rows = sortedData.map(d => [
      fmtDate(d.date),
      d.dMinus ?? '',
      d.expected != null ? d.expected.toFixed(1) : '',
      d.sales,
      d.atingimentoDiario != null ? d.atingimentoDiario.toFixed(1) : '',
      d.cumulativeExpected != null ? d.cumulativeExpected.toFixed(1) : '',
      d.cumulativeSales ?? '',
      d.atingimentoAcumulado != null ? d.atingimentoAcumulado.toFixed(1) : '',
    ]);
    const csv = [headers.join(';'), ...rows.map(r => r.join(';'))].join('\n');
    const blob = new Blob(['\ufeff' + csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `controle_diario_${eventName?.replace(/\s/g, '_') || 'evento'}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  if (!dailySales.length) {
    if (isLoading) {
      return (
        <div className="space-y-2 py-2 animate-pulse">
          <div className={`h-6 rounded ${isDark ? 'bg-gray-700' : 'bg-gray-200'} w-1/3 mb-4`} />
          {[...Array(8)].map((_, i) => (
            <div key={i} className={`h-8 rounded ${isDark ? 'bg-gray-700/60' : 'bg-gray-100'} w-full`} />
          ))}
        </div>
      );
    }
    return (
      <div className={`flex flex-col items-center justify-center py-10 gap-3 ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
        <svg className={`w-8 h-8 ${isDark ? 'text-gray-600' : 'text-gray-300'}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
        </svg>
        <div className="text-center space-y-1">
          <p className={`text-sm font-medium ${isDark ? 'text-gray-300' : 'text-gray-600'}`}>
            Sem histórico de vendas
          </p>
          <p className="text-xs">
            Use "Atualizar Hoje" para sincronizar os dados deste evento.
          </p>
        </div>
        {onAtualizarHoje && (
          <button
            onClick={onAtualizarHoje}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium bg-blue-600 hover:bg-blue-700 text-white transition-colors shadow-sm"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
            Atualizar Hoje
          </button>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {globalMetrics && (
        <div className={`grid grid-cols-3 gap-4 mb-2`}>
          <div className={`rounded-lg p-4 border ${isDark ? 'bg-blue-900/20 border-blue-800' : 'bg-blue-50 border-blue-200'}`}>
            <span className={`text-xs font-medium ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Meta Global</span>
            <p className={`text-xl font-bold mt-1 ${isDark ? 'text-blue-400' : 'text-blue-600'}`}>{fmtInt(globalMetrics.metaGlobal)}</p>
          </div>
          <div className={`rounded-lg p-4 border ${isDark ? 'bg-emerald-900/20 border-emerald-800' : 'bg-emerald-50 border-emerald-200'}`}>
            <span className={`text-xs font-medium ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Vendas Global</span>
            <p className={`text-xl font-bold mt-1 ${isDark ? 'text-emerald-400' : 'text-emerald-600'}`}>{fmtInt(globalMetrics.vendasGlobal)}</p>
          </div>
          {(() => {
            const delta = globalMetrics.atingGlobal - 100;
            const isPositive = delta >= 0;
            return (
              <div className={`rounded-lg p-4 border ${
                isPositive
                  ? (isDark ? 'bg-emerald-900/20 border-emerald-800' : 'bg-emerald-50 border-emerald-200')
                  : (isDark ? 'bg-red-900/20 border-red-800' : 'bg-red-50 border-red-200')
              }`}>
                <span className={`text-xs font-medium ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Ating. Global</span>
                <p className={`text-xl font-bold mt-1 ${
                  isPositive
                    ? (isDark ? 'text-emerald-400' : 'text-emerald-600')
                    : (isDark ? 'text-red-400' : 'text-red-600')
                }`}>{isPositive ? '+' : ''}{delta.toFixed(1).replace('.', ',')}%</p>
              </div>
            );
          })()}
        </div>
      )}

      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <button
            onClick={() => setSortAsc(!sortAsc)}
            className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
              isDark
                ? 'bg-gray-600 text-gray-100 hover:bg-gray-500'
                : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
            }`}
          >
            {sortAsc ? <ArrowUp className="w-3.5 h-3.5" /> : <ArrowDown className="w-3.5 h-3.5" />}
            {sortAsc ? 'Mais antigo primeiro' : 'Mais recente primeiro'}
          </button>
          <span className={`text-xs ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>{dailySales.length} dias</span>
        </div>
        <button
          onClick={handleExportCSV}
          className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
            isDark
              ? 'bg-blue-600 text-white hover:bg-blue-500'
              : 'bg-blue-500 text-white hover:bg-blue-600'
          }`}
        >
          <Download className="w-3.5 h-3.5" />
          Exportar CSV
        </button>
      </div>

      <div className={`rounded-lg overflow-hidden border ${isDark ? 'border-gray-600' : 'border-gray-300'}`}>
        <div className="overflow-auto max-h-[600px]">
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr>
                {[
                  { label: 'Data', align: 'left', sortable: true },
                  { label: 'D-', align: 'right' },
                  { label: 'Meta Dia', align: 'right' },
                  { label: 'Vendas Dia', align: 'right' },
                  { label: 'Ating. Dia', align: 'right' },
                  { label: 'Meta Acum.', align: 'right' },
                  { label: 'Vendas Acum.', align: 'right' },
                  { label: 'Ating. Acum.', align: 'right' },
                ].map((col, idx) => (
                  <th
                    key={idx}
                    onClick={col.sortable ? () => setSortAsc(!sortAsc) : undefined}
                    className={`px-3 py-3 text-xs font-bold uppercase tracking-wider whitespace-nowrap sticky top-0 z-10 border-b-2 ${
                      col.align === 'left' ? 'text-left' : 'text-right'
                    } ${col.sortable ? 'cursor-pointer' : ''} ${
                      isDark
                        ? 'bg-slate-700 text-blue-300 border-blue-500/50'
                        : 'bg-slate-100 text-slate-700 border-slate-300'
                    }`}
                  >
                    {col.sortable ? (
                      <span className="flex items-center gap-1">{col.label} <ArrowUpDown className="w-3 h-3" /></span>
                    ) : col.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {sortedData.map((row, i) => {
                const evenRow = i % 2 === 0;
                const rowBg = isDark
                  ? (evenRow ? 'bg-gray-800' : 'bg-gray-750 bg-[#2d3748]')
                  : (evenRow ? 'bg-white' : 'bg-slate-50');
                const hoverBg = isDark ? 'hover:bg-slate-600' : 'hover:bg-blue-50';
                const borderColor = isDark ? 'border-gray-700' : 'border-gray-200';
                const textPrimary = isDark ? 'text-white' : 'text-gray-900';
                const textSecondary = isDark ? 'text-gray-200' : 'text-gray-700';
                const textMuted = isDark ? 'text-blue-200' : 'text-slate-600';

                return (
                  <tr
                    key={row.date}
                    className={`${rowBg} ${hoverBg} transition-colors border-b ${borderColor}`}
                  >
                    <td className={`px-3 py-2.5 text-left font-mono text-sm ${textPrimary} font-medium whitespace-nowrap`}>
                      {fmtDate(row.date)}
                    </td>
                    <td className={`px-3 py-2.5 text-right text-sm font-semibold whitespace-nowrap ${
                      isDark ? 'text-cyan-300' : 'text-cyan-700'
                    }`}>
                      {row.dMinus ?? '—'}
                    </td>
                    <td className={`px-3 py-2.5 text-right text-sm whitespace-nowrap ${textMuted}`}>
                      {fmtInt(row.expected)}
                    </td>
                    <td className={`px-3 py-2.5 text-right text-sm font-bold whitespace-nowrap ${textPrimary}`}>
                      {fmtInt(row.sales)}
                    </td>
                    <td className={`px-3 py-2.5 text-right text-sm font-semibold whitespace-nowrap ${colorClass(row.atingimentoDiario, isDark)}`}>
                      {fmtPct(row.atingimentoDiario)}
                    </td>
                    <td className={`px-3 py-2.5 text-right text-sm whitespace-nowrap ${textMuted}`}>
                      {fmtInt(row.cumulativeExpected)}
                    </td>
                    <td className={`px-3 py-2.5 text-right text-sm whitespace-nowrap ${textSecondary}`}>
                      {fmtInt(row.cumulativeSales)}
                    </td>
                    <td className={`px-3 py-2.5 text-right text-sm font-semibold whitespace-nowrap ${colorClass(row.atingimentoAcumulado, isDark)}`}>
                      {fmtPct(row.atingimentoAcumulado)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
            {totals && (
              <tfoot>
                <tr className={`font-bold text-sm sticky bottom-0 ${
                  isDark
                    ? 'bg-slate-700 text-white border-t-2 border-blue-500/50'
                    : 'bg-slate-100 text-slate-900 border-t-2 border-slate-400'
                }`}>
                  <td className="px-3 py-3 text-left whitespace-nowrap">Total / Resumo</td>
                  <td className="px-3 py-3 text-right">—</td>
                  <td className="px-3 py-3 text-right">{fmtInt(totals.totalExpected)}</td>
                  <td className="px-3 py-3 text-right">{fmtInt(totals.totalSales)}</td>
                  <td className={`px-3 py-3 text-right ${colorClass(totals.avgAtingDia, isDark)}`}>
                    {totals.avgAtingDia != null ? `μ ${fmtPct(totals.avgAtingDia)}` : '—'}
                  </td>
                  <td className="px-3 py-3 text-right">{fmtInt(totals.finalCumExpected)}</td>
                  <td className="px-3 py-3 text-right">{fmtInt(totals.finalCumSales)}</td>
                  <td className={`px-3 py-3 text-right ${colorClass(totals.finalAtingAcum, isDark)}`}>{fmtPct(totals.finalAtingAcum)}</td>
                </tr>
              </tfoot>
            )}
          </table>
        </div>
      </div>
    </div>
  );
};

export default DailySalesTable;
