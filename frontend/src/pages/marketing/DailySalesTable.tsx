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
}

interface DailySalesTableProps {
  dailySales: DailySaleRow[];
  isDark: boolean;
  eventName?: string;
}

const fmt = (v: number | undefined | null, decimals = 1): string => {
  if (v == null || isNaN(v)) return '—';
  return v.toFixed(decimals);
};

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

const colorClass = (v: number | undefined | null): string => {
  if (v == null || isNaN(v) || v === 0) return '';
  return v > 0 ? 'text-emerald-400' : 'text-red-400';
};

const DailySalesTable: React.FC<DailySalesTableProps> = ({ dailySales, isDark, eventName }) => {
  const [sortAsc, setSortAsc] = useState(false);

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
    const lastRow = dailySales[dailySales.length - 1];
    const avgDailyAtingimento = dailySales.filter(d => d.atingimentoDiario != null && isFinite(d.atingimentoDiario!));
    const avgAtDia = avgDailyAtingimento.length > 0
      ? avgDailyAtingimento.reduce((s, d) => s + d.atingimentoDiario!, 0) / avgDailyAtingimento.length
      : null;
    return {
      totalSales,
      finalCumSales: lastRow?.cumulativeSales ?? totalSales,
      finalCumExpected: lastRow?.cumulativeExpected,
      finalDif: lastRow?.dif,
      finalAtingAcum: lastRow?.atingimentoAcumulado,
      avgAtingDia: avgAtDia,
      days: dailySales.length
    };
  }, [dailySales]);

  const handleExportCSV = () => {
    const headers = ['Data', 'D-', 'Vendas Diárias', 'Vendas Acumuladas', '% Curva Ano Anterior', 'Meta Diária', 'Meta Acumulada', 'Dif', 'Ating. Acumulado (%)', 'Ating. Diário (%)'];
    const rows = sortedData.map(d => [
      fmtDate(d.date),
      d.dMinus ?? '',
      d.sales,
      d.cumulativeSales ?? '',
      d.curvaAnoAnterior != null ? d.curvaAnoAnterior.toFixed(1) : '',
      d.expected != null ? d.expected.toFixed(1) : '',
      d.cumulativeExpected != null ? d.cumulativeExpected.toFixed(1) : '',
      d.dif != null ? d.dif.toFixed(1) : '',
      d.atingimentoAcumulado != null ? d.atingimentoAcumulado.toFixed(1) : '',
      d.atingimentoDiario != null ? d.atingimentoDiario.toFixed(1) : ''
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
    return (
      <div className="text-center py-12 text-gray-400">
        Nenhum dado de vendas diárias disponível.
      </div>
    );
  }

  const thClass = 'px-3 py-2.5 text-xs font-semibold uppercase tracking-wider text-gray-300 bg-gray-800 border-b border-gray-600 sticky top-0 z-10 whitespace-nowrap';
  const tdClass = 'px-3 py-2 text-sm text-right whitespace-nowrap';

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <button
            onClick={() => setSortAsc(!sortAsc)}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md bg-gray-700 text-gray-300 hover:bg-gray-600 transition-colors"
          >
            {sortAsc ? <ArrowUp className="w-3.5 h-3.5" /> : <ArrowDown className="w-3.5 h-3.5" />}
            {sortAsc ? 'Mais antigo primeiro' : 'Mais recente primeiro'}
          </button>
          <span className="text-xs text-gray-500">{dailySales.length} dias</span>
        </div>
        <button
          onClick={handleExportCSV}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md bg-gray-700 text-gray-300 hover:bg-gray-600 transition-colors"
        >
          <Download className="w-3.5 h-3.5" />
          Exportar CSV
        </button>
      </div>

      <div className="rounded-lg border border-gray-700 overflow-hidden">
        <div className="overflow-auto max-h-[600px]">
          <table className="w-full text-sm">
            <thead>
              <tr>
                <th className={`${thClass} text-left cursor-pointer`} onClick={() => setSortAsc(!sortAsc)}>
                  <span className="flex items-center gap-1">Data <ArrowUpDown className="w-3 h-3" /></span>
                </th>
                <th className={`${thClass} text-right`}>D-</th>
                <th className={`${thClass} text-right`}>Vendas Dia</th>
                <th className={`${thClass} text-right`}>Vendas Acum.</th>
                <th className={`${thClass} text-right`}>% Curva Ant.</th>
                <th className={`${thClass} text-right`}>Meta Dia</th>
                <th className={`${thClass} text-right`}>Meta Acum.</th>
                <th className={`${thClass} text-right`}>Dif</th>
                <th className={`${thClass} text-right`}>Ating. Acum.</th>
                <th className={`${thClass} text-right`}>Ating. Dia</th>
              </tr>
            </thead>
            <tbody>
              {sortedData.map((row, i) => (
                <tr
                  key={row.date}
                  className={`${i % 2 === 0 ? 'bg-gray-900/50' : 'bg-gray-800/30'} hover:bg-gray-700/50 transition-colors border-b border-gray-800/50`}
                >
                  <td className={`${tdClass} text-left font-mono text-gray-300`}>{fmtDate(row.date)}</td>
                  <td className={`${tdClass} text-gray-300 font-medium`}>{row.dMinus ?? '—'}</td>
                  <td className={`${tdClass} text-gray-200 font-medium`}>{fmtInt(row.sales)}</td>
                  <td className={`${tdClass} text-gray-200`}>{fmtInt(row.cumulativeSales)}</td>
                  <td className={`${tdClass} text-gray-400`}>{fmtPct(row.curvaAnoAnterior)}</td>
                  <td className={`${tdClass} text-gray-400`}>{fmt(row.expected)}</td>
                  <td className={`${tdClass} text-gray-400`}>{fmt(row.cumulativeExpected)}</td>
                  <td className={`${tdClass} font-medium ${colorClass(row.dif)}`}>{fmt(row.dif)}</td>
                  <td className={`${tdClass} font-medium ${colorClass(row.atingimentoAcumulado)}`}>{fmtPct(row.atingimentoAcumulado)}</td>
                  <td className={`${tdClass} font-medium ${colorClass(row.atingimentoDiario)}`}>{fmtPct(row.atingimentoDiario)}</td>
                </tr>
              ))}
            </tbody>
            {totals && (
              <tfoot>
                <tr className="bg-gray-800 border-t-2 border-gray-600 font-semibold text-gray-200">
                  <td className={`${tdClass} text-left`}>Total / Resumo</td>
                  <td className={tdClass}>—</td>
                  <td className={tdClass}>{fmtInt(totals.totalSales)}</td>
                  <td className={tdClass}>{fmtInt(totals.finalCumSales)}</td>
                  <td className={tdClass}>—</td>
                  <td className={tdClass}>—</td>
                  <td className={tdClass}>{fmt(totals.finalCumExpected)}</td>
                  <td className={`${tdClass} ${colorClass(totals.finalDif)}`}>{fmt(totals.finalDif)}</td>
                  <td className={`${tdClass} ${colorClass(totals.finalAtingAcum)}`}>{fmtPct(totals.finalAtingAcum)}</td>
                  <td className={`${tdClass} ${colorClass(totals.avgAtingDia)}`}>
                    {totals.avgAtingDia != null ? `μ ${fmtPct(totals.avgAtingDia)}` : '—'}
                  </td>
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
