import React, { useEffect, useState, useMemo, useCallback } from 'react';
import { dashboardService } from '../../services/api';
import { useTheme } from '../../context/ThemeContext';
import { usePermissions } from '../../context/PermissionContext';
import { useAuth } from '../../context/AuthContext';
import RelatorioFinanceiro from './RelatorioFinanceiro';
import {
  Filter, Search, ChevronDown, LayoutDashboard, RotateCcw,
  RefreshCw,
  ListOrdered, ArrowUp, ArrowDown, ArrowUpDown, ChevronUp
} from 'lucide-react';

const formatNumber = (value: number) =>
  new Intl.NumberFormat('pt-BR').format(value);

interface FilterOption { value: string | number; label: string; }

interface Filters {
  ano: number | null;
  mes: number | null;
  produto: string | null;
  modalidade: string | null;
  cidade: string | null;
}

interface FilterOptions {
  anos: FilterOption[];
  meses: FilterOption[];
  produtos: FilterOption[];
  modalidades: FilterOption[];
  cidades: FilterOption[];
}

const SearchableDropdown: React.FC<{
  label: string; options: FilterOption[]; value: string | number | null;
  onChange: (v: string | number | null) => void; placeholder?: string; isDark: boolean;
}> = ({ label, options, value, onChange, placeholder = 'Selecione...', isDark }) => {
  const [isOpen, setIsOpen] = useState(false);
  const [search, setSearch] = useState('');
  const filtered = useMemo(() => search ? options.filter(o => o.label.toLowerCase().includes(search.toLowerCase())) : options, [options, search]);
  const selectedLabel = options.find(o => o.value === value)?.label || placeholder;

  return (
    <div className="relative">
      <label className={`block text-xs font-bold mb-1.5 ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>{label}</label>
      <button type="button" onClick={() => setIsOpen(!isOpen)}
        className={`w-full px-3 py-2.5 text-sm text-left rounded-xl border flex items-center justify-between ${
          isDark ? 'bg-gray-800 border-gray-700 text-white hover:bg-gray-700' : 'bg-gray-50 border-gray-200 text-gray-900 hover:bg-gray-100'
        } transition-all`}>
        <span className={value ? '' : 'text-gray-400'}>{selectedLabel}</span>
        <ChevronDown className="w-4 h-4" />
      </button>
      {isOpen && (
        <div className={`absolute z-50 w-full mt-1 rounded-xl shadow-xl border ${isDark ? 'bg-gray-800 border-gray-700' : 'bg-white border-gray-200'}`}>
          <div className="p-2">
            <div className="relative">
              <Search className={`absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 ${isDark ? 'text-gray-400' : 'text-gray-500'}`} />
              <input type="text" value={search} onChange={e => setSearch(e.target.value)} placeholder="Buscar..."
                className={`w-full pl-9 pr-3 py-2 text-sm rounded-lg border ${
                  isDark ? 'bg-gray-700 border-gray-600 text-white placeholder-gray-400' : 'bg-gray-50 border-gray-300 text-gray-900 placeholder-gray-500'
                } focus:ring-2 focus:ring-indigo-500 focus:border-transparent`} />
            </div>
          </div>
          <div className="max-h-48 overflow-y-auto">
            <button type="button" onClick={() => { onChange(null); setIsOpen(false); setSearch(''); }}
              className={`w-full px-4 py-2 text-sm text-left ${isDark ? 'hover:bg-gray-700 text-gray-300' : 'hover:bg-gray-100 text-gray-500'} transition-colors`}>
              -- Limpar --
            </button>
            {filtered.map(option => (
              <button key={option.value} type="button"
                onClick={() => { onChange(option.value); setIsOpen(false); setSearch(''); }}
                className={`w-full px-4 py-2 text-sm text-left ${
                  value === option.value ? 'bg-indigo-500 text-white' : isDark ? 'hover:bg-gray-700 text-gray-200' : 'hover:bg-gray-100 text-gray-900'
                } transition-colors`}>
                {option.label}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

const KpiCard: React.FC<{
  title: string; value: string; subtitle?: string;
  icon: React.ReactNode; gradient: string; isDark: boolean;
}> = ({ title, value, subtitle, icon, gradient, isDark }) => (
  <div className={`relative overflow-hidden rounded-2xl p-5 ${isDark ? 'bg-gray-800/60 backdrop-blur-xl border border-gray-700/50' : 'bg-white/80 backdrop-blur-xl border border-gray-200/80'} transition-all hover:scale-[1.02] hover:shadow-lg`}>
    <div className={`absolute top-0 right-0 w-24 h-24 rounded-full blur-2xl opacity-20 ${gradient}`} />
    <div className="relative flex items-start justify-between">
      <div className="flex-1">
        <p className={`text-xs font-semibold uppercase tracking-wider ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>{title}</p>
        <p className={`text-2xl font-black mt-1.5 ${isDark ? 'text-white' : 'text-gray-900'}`}>{value}</p>
        {subtitle && <p className={`text-xs mt-1 ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>{subtitle}</p>}
      </div>
      <div className={`p-2.5 rounded-xl bg-gradient-to-br ${gradient} shadow-lg`}>{icon}</div>
    </div>
  </div>
);

const SectionLabel: React.FC<{ label: string; isDark: boolean; color: string }> = ({ label, isDark, color }) => (
  <div className="flex items-center gap-3 mb-4">
    <div className={`h-px flex-1 ${isDark ? 'bg-gray-700' : 'bg-gray-200'}`} />
    <span className={`text-xs font-bold uppercase tracking-widest px-3 py-1 rounded-full ${color}`}>{label}</span>
    <div className={`h-px flex-1 ${isDark ? 'bg-gray-700' : 'bg-gray-200'}`} />
  </div>
);

const OcupacaoBar: React.FC<{ taxa: number }> = ({ taxa }) => {
  const color = taxa >= 80 ? 'bg-emerald-500' : taxa >= 50 ? 'bg-amber-500' : 'bg-red-500';
  const textColor = taxa >= 80 ? 'text-emerald-400' : taxa >= 50 ? 'text-amber-400' : 'text-red-400';
  return (
    <div className="flex items-center gap-2">
      <div className="w-16 h-2 rounded-full bg-gray-200 dark:bg-gray-700 overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${Math.min(taxa, 100)}%` }} />
      </div>
      <span className={`text-xs font-medium ${textColor}`}>{taxa}%</span>
    </div>
  );
};

interface ProjecaoAreaItem {
  area: string;
  quantidade: number;
}

interface EventoInscricoes {
  id: number;
  evento: string;
  cidade: string;
  modalidade: string;
  produto: string;
  data_evento: string | null;
  dias_para_evento: number | null;
  inscritos_total: number;
  inscritos_projetados?: number;
  inscritos_projetados_site?: number;
  projecoes_por_area?: ProjecaoAreaItem[];
  total_geral?: number;
  inscritos_hoje: number;
  inscritos_ontem: number;
  media_7d: number;
  media_14d: number;
  isc_status: string;
  taxa_ocupacao: number;
  capacidade: number;
}

type SortKey = keyof Pick<EventoInscricoes,
  'evento' | 'data_evento' | 'inscritos_total' | 'inscritos_projetados' | 'total_geral' | 'inscritos_hoje' | 'inscritos_ontem' | 'media_7d' | 'media_14d' | 'taxa_ocupacao'
>;

const EventosInscricoesTable: React.FC<{ rows: EventoInscricoes[]; isDark: boolean }> = ({ rows, isDark }) => {
  const [search, setSearch] = useState('');
  const [periodoFilter, setPeriodoFilter] = useState<string>('all');
  const [eventoStatusFilter, setEventoStatusFilter] = useState<string>('em_andamento');
  const [collapsed, setCollapsed] = useState(false);
  const [sortKey, setSortKey] = useState<SortKey>('data_evento');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc');
  const [viewMode, setViewMode] = useState<'site' | 'projecoes'>('site');
  const [expandedRows, setExpandedRows] = useState<Set<number>>(new Set());

  const filtered = useMemo(() => {
    const s = search.trim().toLowerCase();
    return rows.filter(r => {
      if (s && !(r.evento.toLowerCase().includes(s) || (r.cidade || '').toLowerCase().includes(s))) return false;
      if (eventoStatusFilter !== 'all') {
        const d = r.dias_para_evento;
        if (eventoStatusFilter === 'em_andamento' && d != null && d < 0) return false;
        if (eventoStatusFilter === 'concluido' && (d == null || d >= 0)) return false;
      }
      if (periodoFilter !== 'all') {
        const d = r.dias_para_evento;
        if (d == null || d < 0) return false;
        if (periodoFilter === '30' && d > 30) return false;
        if (periodoFilter === '60' && d > 60) return false;
        if (periodoFilter === '90' && d > 90) return false;
      }
      return true;
    });
  }, [rows, search, eventoStatusFilter, periodoFilter]);

  const sorted = useMemo(() => {
    const arr = [...filtered];
    arr.sort((a, b) => {
      const av = (a[sortKey] ?? '') as any;
      const bv = (b[sortKey] ?? '') as any;
      if (typeof av === 'number' && typeof bv === 'number') return sortDir === 'asc' ? av - bv : bv - av;
      const as = String(av), bs = String(bv);
      return sortDir === 'asc' ? as.localeCompare(bs) : bs.localeCompare(as);
    });
    return arr;
  }, [filtered, sortKey, sortDir]);

  const totals = useMemo(() => {
    const sum = filtered.reduce((acc, r) => ({
      total: acc.total + (r.inscritos_total || 0),
      projetados: acc.projetados + (r.inscritos_projetados || 0),
      projetados_site: acc.projetados_site + (r.inscritos_projetados_site || 0),
      geral: acc.geral + (r.total_geral ?? ((r.inscritos_total || 0) + (r.inscritos_projetados || 0))),
      hoje: acc.hoje + (r.inscritos_hoje || 0),
      ontem: acc.ontem + (r.inscritos_ontem || 0),
      m7: acc.m7 + (r.media_7d || 0),
      m14: acc.m14 + (r.media_14d || 0),
    }), { total: 0, projetados: 0, projetados_site: 0, geral: 0, hoje: 0, ontem: 0, m7: 0, m14: 0 });
    const n = filtered.length || 1;
    return { ...sum, m7Avg: sum.m7 / n, m14Avg: sum.m14 / n };
  }, [filtered]);

  const toggleRow = (id: number) => {
    setExpandedRows(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  const toggleSort = (k: SortKey) => {
    if (sortKey === k) setSortDir(d => d === 'asc' ? 'desc' : 'asc');
    else { setSortKey(k); setSortDir(k === 'evento' || k === 'data_evento' ? 'asc' : 'desc'); }
  };

  const SortIcon = ({ k }: { k: SortKey }) => {
    if (sortKey !== k) return <ArrowUpDown className="w-3 h-3 opacity-40" />;
    return sortDir === 'asc' ? <ArrowUp className="w-3 h-3 text-indigo-400" /> : <ArrowDown className="w-3 h-3 text-indigo-400" />;
  };

  const Th: React.FC<{ k?: SortKey; align?: 'left' | 'right' | 'center'; children: React.ReactNode }> = ({ k, align = 'left', children }) => {
    const justify = align === 'right' ? 'justify-end' : align === 'center' ? 'justify-center' : 'justify-start';
    return (
      <th className={`px-4 py-3 text-${align} text-xs font-bold uppercase tracking-wider ${isDark ? 'text-gray-300' : 'text-gray-600'} ${k ? 'cursor-pointer select-none' : ''}`}
        onClick={k ? () => toggleSort(k) : undefined}>
        <span className={`inline-flex items-center gap-1.5 w-full ${justify}`}>
          {children}{k && <SortIcon k={k} />}
        </span>
      </th>
    );
  };

  const fmtNum = (v: number) => new Intl.NumberFormat('pt-BR').format(v);
  const fmtAvg = (v: number) => new Intl.NumberFormat('pt-BR', { minimumFractionDigits: 1, maximumFractionDigits: 1 }).format(v);
  const fmtDate = (iso: string | null) => iso ? new Date(iso + 'T00:00:00').toLocaleDateString('pt-BR') : '—';

  const deltaCell = (hoje: number, ontem: number) => {
    if (!ontem && !hoje) return <span className={isDark ? 'text-gray-500' : 'text-gray-400'}>—</span>;
    if (!ontem) return <span className="text-emerald-400 font-semibold">+{fmtNum(hoje)}</span>;
    const diff = hoje - ontem;
    const cls = diff > 0 ? 'text-emerald-400' : diff < 0 ? 'text-red-400' : (isDark ? 'text-gray-300' : 'text-gray-600');
    const sign = diff > 0 ? '+' : '';
    return <span className={`font-semibold ${cls}`}>{sign}{fmtNum(diff)}</span>;
  };

  const cardClass = `rounded-2xl ${isDark ? 'bg-gray-800/60 backdrop-blur-xl border border-gray-700/50' : 'bg-white/80 backdrop-blur-xl border border-gray-200/80'}`;

  return (
    <div className={`${cardClass} overflow-hidden`}>
      <div className={`p-5 flex flex-col lg:flex-row lg:items-center lg:justify-between gap-3 ${collapsed ? '' : 'border-b border-gray-200/50 dark:border-gray-700/50'}`}>
        <div className="flex items-center gap-3 min-w-0">
          <button
            type="button"
            onClick={() => setCollapsed(c => !c)}
            title={collapsed ? 'Expandir tabela' : 'Recolher tabela'}
            className={`text-sm font-bold flex items-center gap-2 shrink-0 ${isDark ? 'text-white hover:text-indigo-300' : 'text-gray-900 hover:text-indigo-600'} transition-colors`}
          >
            <ListOrdered className="w-4 h-4 text-indigo-400" />
            Inscrições por Evento <span className={`text-xs font-normal ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>· {filtered.length} de {rows.length}</span>
            <ChevronUp className={`w-4 h-4 ml-1 transition-transform ${collapsed ? 'rotate-180' : ''} ${isDark ? 'text-gray-400' : 'text-gray-500'}`} />
          </button>
          {!collapsed && (
            <div className={`flex items-center rounded-lg border p-0.5 ${isDark ? 'bg-gray-700/60 border-gray-600' : 'bg-gray-100 border-gray-200'}`}>
              <button
                type="button"
                onClick={() => setViewMode('site')}
                className={`px-3 py-1 text-xs font-semibold rounded-md transition-all ${viewMode === 'site'
                  ? 'bg-indigo-500 text-white shadow-sm'
                  : isDark ? 'text-gray-400 hover:text-gray-200' : 'text-gray-500 hover:text-gray-700'}`}
              >
                Site
              </button>
              <button
                type="button"
                onClick={() => setViewMode('projecoes')}
                className={`px-3 py-1 text-xs font-semibold rounded-md transition-all ${viewMode === 'projecoes'
                  ? 'bg-violet-500 text-white shadow-sm'
                  : isDark ? 'text-gray-400 hover:text-gray-200' : 'text-gray-500 hover:text-gray-700'}`}
              >
                Projeções
              </button>
            </div>
          )}
        </div>
        {!collapsed && (
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative">
            <Search className={`absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 ${isDark ? 'text-gray-400' : 'text-gray-500'}`} />
            <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Buscar evento ou cidade..."
              className={`pl-9 pr-3 py-2 text-sm rounded-lg border w-56 ${
                isDark ? 'bg-gray-700/60 border-gray-600 text-white placeholder-gray-400' : 'bg-gray-50 border-gray-200 text-gray-900 placeholder-gray-500'
              } focus:ring-2 focus:ring-indigo-500 focus:border-transparent`} />
          </div>
          <select value={eventoStatusFilter} onChange={e => setEventoStatusFilter(e.target.value)}
            className={`px-3 py-2 text-sm rounded-lg border ${isDark ? 'bg-gray-700/60 border-gray-600 text-white' : 'bg-gray-50 border-gray-200 text-gray-900'} focus:ring-2 focus:ring-indigo-500 focus:border-transparent`}>
            <option value="all">Todos os eventos</option>
            <option value="em_andamento">Em andamento</option>
            <option value="concluido">Concluídos</option>
          </select>
          <select value={periodoFilter} onChange={e => setPeriodoFilter(e.target.value)}
            className={`px-3 py-2 text-sm rounded-lg border ${isDark ? 'bg-gray-700/60 border-gray-600 text-white' : 'bg-gray-50 border-gray-200 text-gray-900'} focus:ring-2 focus:ring-indigo-500 focus:border-transparent`}>
            <option value="all">Todos os períodos</option>
            <option value="30">Próximos 30 dias</option>
            <option value="60">Próximos 60 dias</option>
            <option value="90">Próximos 90 dias</option>
          </select>
        </div>
        )}
      </div>
      {viewMode === 'site' && (
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className={isDark ? 'bg-gray-700/40' : 'bg-gray-50/80'}>
              <Th k="evento">Evento</Th>
              <Th k="data_evento" align="center">Data</Th>
              <Th k="inscritos_total" align="center">Inscritos Site</Th>
              <Th k="inscritos_projetados" align="center">Projeção Site</Th>
              <Th k="inscritos_ontem" align="center">Ontem</Th>
              <Th k="inscritos_hoje" align="center">Hoje</Th>
              <Th align="center">Δ Hoje</Th>
              <Th k="media_7d" align="center">Média 7d</Th>
              <Th k="media_14d" align="center">Média 14d</Th>
              <Th k="taxa_ocupacao" align="center">Ocupação</Th>
            </tr>
          </thead>
          <tbody className={`divide-y ${isDark ? 'divide-gray-700/40' : 'divide-gray-100'}`}>
            {!collapsed && sorted.length === 0 && (
              <tr><td colSpan={10} className={`px-4 py-8 text-center text-sm ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>Nenhum evento encontrado</td></tr>
            )}
            {!collapsed && sorted.map(r => {
              const projSite = r.inscritos_projetados_site || 0;
              return (
                <tr key={r.id} className={isDark ? 'hover:bg-gray-700/30' : 'hover:bg-indigo-50/40'}>
                  <td className="px-4 py-3">
                    <div className={`font-semibold ${isDark ? 'text-white' : 'text-gray-900'}`}>{r.evento}</div>
                    <div className={`text-xs ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>{r.cidade} · {r.modalidade}</div>
                  </td>
                  <td className="px-4 py-3 text-center">
                    <div className={isDark ? 'text-gray-200' : 'text-gray-800'}>{fmtDate(r.data_evento)}</div>
                    {r.dias_para_evento != null && r.dias_para_evento >= 0 && (
                      <div className={`text-xs font-bold mt-0.5 inline-block px-2 py-0.5 rounded-full ${
                        r.dias_para_evento <= 7 ? 'bg-red-500/20 text-red-400' :
                        r.dias_para_evento <= 30 ? 'bg-amber-500/20 text-amber-400' :
                        'bg-indigo-500/20 text-indigo-400'
                      }`}>D-{r.dias_para_evento}</div>
                    )}
                  </td>
                  <td className={`px-4 py-3 text-center font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>{fmtNum(r.inscritos_total)}</td>
                  <td className={`px-4 py-3 text-center ${projSite > 0 ? 'text-indigo-400 font-semibold' : (isDark ? 'text-gray-500' : 'text-gray-400')}`}>{fmtNum(projSite)}</td>
                  <td className={`px-4 py-3 text-center ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>{fmtNum(r.inscritos_ontem)}</td>
                  <td className={`px-4 py-3 text-center font-semibold ${r.inscritos_hoje > 0 ? 'text-emerald-400' : (isDark ? 'text-gray-300' : 'text-gray-700')}`}>{fmtNum(r.inscritos_hoje)}</td>
                  <td className="px-4 py-3 text-center">{deltaCell(r.inscritos_hoje, r.inscritos_ontem)}</td>
                  <td className={`px-4 py-3 text-center ${isDark ? 'text-gray-200' : 'text-gray-800'}`}>{fmtAvg(r.media_7d)}</td>
                  <td className={`px-4 py-3 text-center ${isDark ? 'text-gray-200' : 'text-gray-800'}`}>{fmtAvg(r.media_14d)}</td>
                  <td className="px-4 py-3 text-center"><div className="inline-flex"><OcupacaoBar taxa={r.taxa_ocupacao} /></div></td>
                </tr>
              );
            })}
          </tbody>
          {sorted.length > 0 && (
            <tfoot>
              <tr className={`${isDark ? 'bg-gray-700/40 border-t border-gray-700/60' : 'bg-gray-50 border-t border-gray-200'}`}>
                <td colSpan={2} className={`px-4 py-3 text-xs font-bold uppercase tracking-wider ${isDark ? 'text-gray-300' : 'text-gray-600'}`}>Totais ({filtered.length} eventos)</td>
                <td className={`px-4 py-3 text-center font-black ${isDark ? 'text-white' : 'text-gray-900'}`}>{fmtNum(totals.total)}</td>
                <td className={`px-4 py-3 text-center font-bold ${totals.projetados_site > 0 ? 'text-indigo-400' : (isDark ? 'text-gray-200' : 'text-gray-800')}`}>{fmtNum(totals.projetados_site)}</td>
                <td className={`px-4 py-3 text-center font-bold ${isDark ? 'text-gray-200' : 'text-gray-800'}`}>{fmtNum(totals.ontem)}</td>
                <td className={`px-4 py-3 text-center font-bold ${totals.hoje > 0 ? 'text-emerald-400' : (isDark ? 'text-gray-200' : 'text-gray-800')}`}>{fmtNum(totals.hoje)}</td>
                <td className="px-4 py-3 text-center">{deltaCell(totals.hoje, totals.ontem)}</td>
                <td className={`px-4 py-3 text-center font-bold ${isDark ? 'text-gray-200' : 'text-gray-800'}`} title="Média das médias 7d">⌀ {fmtAvg(totals.m7Avg)}</td>
                <td className={`px-4 py-3 text-center font-bold ${isDark ? 'text-gray-200' : 'text-gray-800'}`} title="Média das médias 14d">⌀ {fmtAvg(totals.m14Avg)}</td>
                <td />
              </tr>
            </tfoot>
          )}
        </table>
      </div>
      )}

      {viewMode === 'projecoes' && (
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className={isDark ? 'bg-gray-700/40' : 'bg-gray-50/80'}>
              <Th k="evento">Evento</Th>
              <Th k="data_evento" align="center">Data</Th>
              <Th k="total_geral" align="center">Total Inscritos</Th>
              <Th align="center"><span className={`text-xs ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>Expandir detalhes →</span></Th>
            </tr>
          </thead>
          <tbody className={`divide-y ${isDark ? 'divide-gray-700/40' : 'divide-gray-100'}`}>
            {!collapsed && sorted.length === 0 && (
              <tr><td colSpan={4} className={`px-4 py-8 text-center text-sm ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>Nenhum evento encontrado</td></tr>
            )}
            {!collapsed && sorted.map(r => {
              const isExpanded = expandedRows.has(r.id);
              const areas = (r.projecoes_por_area || []).slice().sort((a, b) => b.quantidade - a.quantidade);
              const totalProj = r.inscritos_projetados || 0;
              const totalGeral = r.total_geral ?? ((r.inscritos_total || 0) + totalProj);
              return (
                <React.Fragment key={r.id}>
                  <tr
                    className={`cursor-pointer transition-colors ${isExpanded
                      ? isDark ? 'bg-violet-500/10' : 'bg-violet-50/60'
                      : isDark ? 'hover:bg-gray-700/30' : 'hover:bg-violet-50/30'}`}
                    onClick={() => toggleRow(r.id)}
                  >
                    <td className="px-4 py-3">
                      <div className={`font-semibold ${isDark ? 'text-white' : 'text-gray-900'}`}>{r.evento}</div>
                      <div className={`text-xs ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>{r.cidade} · {r.modalidade}</div>
                    </td>
                    <td className="px-4 py-3 text-center">
                      <div className={isDark ? 'text-gray-200' : 'text-gray-800'}>{fmtDate(r.data_evento)}</div>
                      {r.dias_para_evento != null && r.dias_para_evento >= 0 && (
                        <div className={`text-xs font-bold mt-0.5 inline-block px-2 py-0.5 rounded-full ${
                          r.dias_para_evento <= 7 ? 'bg-red-500/20 text-red-400' :
                          r.dias_para_evento <= 30 ? 'bg-amber-500/20 text-amber-400' :
                          'bg-indigo-500/20 text-indigo-400'
                        }`}>D-{r.dias_para_evento}</div>
                      )}
                    </td>
                    <td className="px-4 py-3 text-center">
                      <span className={`inline-flex items-center justify-center min-w-[64px] px-3 py-1 rounded-lg text-base font-black tracking-tight shadow-sm ${
                        isDark
                          ? 'bg-gradient-to-br from-violet-500/30 to-purple-500/20 text-white ring-1 ring-violet-400/40'
                          : 'bg-gradient-to-br from-violet-100 to-purple-100 text-violet-900 ring-1 ring-violet-300/60'
                      }`}>
                        {fmtNum(totalProj)}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-center">
                      <div className={`inline-flex items-center gap-1 text-xs font-semibold transition-colors ${
                        isExpanded
                          ? isDark ? 'text-violet-400' : 'text-violet-600'
                          : isDark ? 'text-gray-500 hover:text-gray-300' : 'text-gray-400 hover:text-gray-600'
                      }`}>
                        {areas.length > 0 ? `${areas.length} área${areas.length > 1 ? 's' : ''}` : 'sem projeções'}
                        <ChevronDown className={`w-3.5 h-3.5 transition-transform ${isExpanded ? 'rotate-180' : ''}`} />
                      </div>
                    </td>
                  </tr>
                  {isExpanded && (
                    <tr className={isDark ? 'bg-gray-900/30' : 'bg-violet-50/40'}>
                      <td colSpan={4} className="px-6 py-4">
                        <div className={`rounded-xl border p-4 ${isDark ? 'bg-gray-800/60 border-gray-700/50' : 'bg-white border-violet-100'}`}>
                          <p className={`text-xs font-bold uppercase tracking-wider mb-3 ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                            Composição de Inscritos
                          </p>
                          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
                            {areas.map((a, idx) => {
                              const areaColors = [
                                { bg: isDark ? 'bg-violet-500/10 border-violet-500/20' : 'bg-violet-50 border-violet-200/60', text: isDark ? 'text-violet-400' : 'text-violet-700', val: isDark ? 'text-violet-300' : 'text-violet-800' },
                                { bg: isDark ? 'bg-blue-500/10 border-blue-500/20' : 'bg-blue-50 border-blue-200/60', text: isDark ? 'text-blue-400' : 'text-blue-700', val: isDark ? 'text-blue-300' : 'text-blue-800' },
                                { bg: isDark ? 'bg-amber-500/10 border-amber-500/20' : 'bg-amber-50 border-amber-200/60', text: isDark ? 'text-amber-400' : 'text-amber-700', val: isDark ? 'text-amber-300' : 'text-amber-800' },
                                { bg: isDark ? 'bg-rose-500/10 border-rose-500/20' : 'bg-rose-50 border-rose-200/60', text: isDark ? 'text-rose-400' : 'text-rose-700', val: isDark ? 'text-rose-300' : 'text-rose-800' },
                                { bg: isDark ? 'bg-teal-500/10 border-teal-500/20' : 'bg-teal-50 border-teal-200/60', text: isDark ? 'text-teal-400' : 'text-teal-700', val: isDark ? 'text-teal-300' : 'text-teal-800' },
                                { bg: isDark ? 'bg-indigo-500/10 border-indigo-500/20' : 'bg-indigo-50 border-indigo-200/60', text: isDark ? 'text-indigo-400' : 'text-indigo-700', val: isDark ? 'text-indigo-300' : 'text-indigo-800' },
                                { bg: isDark ? 'bg-fuchsia-500/10 border-fuchsia-500/20' : 'bg-fuchsia-50 border-fuchsia-200/60', text: isDark ? 'text-fuchsia-400' : 'text-fuchsia-700', val: isDark ? 'text-fuchsia-300' : 'text-fuchsia-800' },
                                { bg: isDark ? 'bg-orange-500/10 border-orange-500/20' : 'bg-orange-50 border-orange-200/60', text: isDark ? 'text-orange-400' : 'text-orange-700', val: isDark ? 'text-orange-300' : 'text-orange-800' },
                              ];
                              const c = areaColors[idx % areaColors.length];
                              return (
                                <div key={a.area} className={`flex items-center justify-between px-3 py-2 rounded-lg border ${c.bg}`}>
                                  <span className={`text-xs font-semibold ${c.text}`}>{a.area}</span>
                                  <span className={`text-sm font-black tabular-nums ${c.val}`}>{fmtNum(a.quantidade)}</span>
                                </div>
                              );
                            })}
                            {areas.length === 0 && (
                              <div className={`col-span-full text-center text-xs italic ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>
                                Nenhuma projeção cadastrada para este evento
                              </div>
                            )}
                          </div>
                        </div>
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              );
            })}
          </tbody>
          {sorted.length > 0 && (
            <tfoot>
              <tr className={`${isDark ? 'bg-gray-700/40 border-t border-gray-700/60' : 'bg-gray-50 border-t border-gray-200'}`}>
                <td colSpan={2} className={`px-4 py-3 text-xs font-bold uppercase tracking-wider ${isDark ? 'text-gray-300' : 'text-gray-600'}`}>Totais ({filtered.length} eventos)</td>
                <td className="px-4 py-3 text-center">
                  <span className={`inline-flex items-center justify-center min-w-[64px] px-3 py-1 rounded-lg text-base font-black tracking-tight shadow-sm ${
                    isDark
                      ? 'bg-gradient-to-br from-violet-500/40 to-purple-500/30 text-white ring-1 ring-violet-400/50'
                      : 'bg-gradient-to-br from-violet-200 to-purple-200 text-violet-900 ring-1 ring-violet-400/60'
                  }`}>
                    {fmtNum(totals.projetados)}
                  </span>
                </td>
                <td />
              </tr>
            </tfoot>
          )}
        </table>
      </div>
      )}
    </div>
  );
};

const Dashboard: React.FC = () => {
  const { isDark } = useTheme();
  const { canViewCampo } = usePermissions();
  const { user } = useAuth();
  const canSeeFinancial = canViewCampo('dashboard', 'dados_financeiros');

  const uid = user?.id ?? 'anon';
  const CACHE_KEY_OP = `dash_op_${uid}`;
  const CACHE_KEY_FIN = `dash_fin_${uid}`;
  const CACHE_KEY_REL = `dash_rel_v2_${uid}`;
  const CACHE_KEY_FILTROS = `dash_filtros_v2_${uid}`;

  const CACHE_TTL_MS = 30 * 60 * 1000;
  const getNextRefreshMs = (): number => Date.now() + CACHE_TTL_MS;

  const readCache = (key: string) => {
    try {
      const raw = localStorage.getItem(key);
      if (!raw) return null;
      const { data, ts, expiresAt } = JSON.parse(raw);
      const expired = expiresAt ? Date.now() > expiresAt : Date.now() - ts > 30 * 60 * 1000;
      if (expired) return null;
      return data;
    } catch { return null; }
  };

  const writeCache = (key: string, data: any) => {
    try {
      localStorage.setItem(key, JSON.stringify({ data, ts: Date.now(), expiresAt: getNextRefreshMs() }));
    } catch {}
  };

  const isCacheStale = (key: string) => readCache(key) === null;

  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [showFilters, setShowFilters] = useState(false);
  const [opData, setOpData] = useState<any>(() => readCache(CACHE_KEY_OP));
  const [finData, setFinData] = useState<any>(() => canSeeFinancial ? readCache(CACHE_KEY_FIN) : null);
  const [relData, setRelData] = useState<any>(() => canSeeFinancial ? readCache(CACHE_KEY_REL) : null);
  const [relLoading, setRelLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [defaultAno, setDefaultAno] = useState<number>(new Date().getFullYear());

  const cachedFiltros = readCache(CACHE_KEY_FILTROS);
  const [filterOptions, setFilterOptions] = useState<FilterOptions>(
    cachedFiltros || { anos: [], meses: [], produtos: [], modalidades: [], cidades: [] }
  );
  const [filters, setFilters] = useState<Filters>(() => {
    const ano = cachedFiltros?.anos?.[0]?.value || new Date().getFullYear();
    return { ano: ano as number, mes: null, produto: null, modalidade: null, cidade: null };
  });

  const activeFiltersCount = useMemo(() => {
    let c = 0;
    if (filters.mes) c++;
    if (filters.produto) c++;
    if (filters.modalidade) c++;
    if (filters.cidade) c++;
    return c;
  }, [filters]);

  const clearFilters = () => setFilters({ ano: defaultAno, mes: null, produto: null, modalidade: null, cidade: null });

  const hasDataRef = React.useRef(!!readCache(CACHE_KEY_OP));
  const mountHandlingRef = React.useRef(false);

  const loadData = useCallback(async (f: Filters, silent = false) => {
    if (!silent) setRefreshing(true);
    setError(null);
    const apiF = { ano: f.ano, mes: f.mes, produto: f.produto, modalidade: f.modalidade, cidade: f.cidade };
    try {
      const ops: Promise<any>[] = [dashboardService.getOperacional(apiF)];
      if (canSeeFinancial) ops.push(dashboardService.getFinanceiro(apiF));
      const results = await Promise.all(ops);
      setOpData(results[0]);
      hasDataRef.current = true;
      writeCache(CACHE_KEY_OP, results[0]);
      if (canSeeFinancial) {
        setFinData(results[1]);
        writeCache(CACHE_KEY_FIN, results[1]);
      }
    } catch (err: any) {
      if (!hasDataRef.current) setError('Erro ao carregar dados do dashboard');
      console.error('Erro ao carregar dashboard:', err);
    } finally {
      setRefreshing(false);
    }

    if (canSeeFinancial) {
      setRelLoading(true);
      try {
        const rel = await dashboardService.getRelatorioFinanceiro(apiF);
        setRelData(rel);
        writeCache(CACHE_KEY_REL, rel);
      } catch (err: any) {
        console.error('Erro ao carregar relatório financeiro:', err);
      } finally {
        setRelLoading(false);
      }
    }
  }, [canSeeFinancial]);

  useEffect(() => {
    const hasCachedData = !!readCache(CACHE_KEY_OP);

    const init = async () => {
      try {
        const data = await dashboardService.getFiltros();
        const firstAno = data.anos?.[0]?.value || new Date().getFullYear();
        setDefaultAno(firstAno as number);
        const newFiltros = {
          anos: data.anos || [],
          meses: data.meses || [],
          produtos: data.produtos || [],
          modalidades: data.modalidades || [],
          cidades: data.cidades || [],
        };
        setFilterOptions(newFiltros);
        writeCache(CACHE_KEY_FILTROS, newFiltros);
        if (!hasCachedData) {
          setFilters(prev => ({ ...prev, ano: firstAno as number }));
        } else {
          setFilters(prev => {
            const ano = prev.ano || firstAno as number;
            return { ...prev, ano };
          });
        }
      } catch {
        if (!hasCachedData) setFilters(prev => ({ ...prev, ano: new Date().getFullYear() }));
      } finally {
        setLoading(false);
      }
    };

    if (hasCachedData) {
      setLoading(false);
      mountHandlingRef.current = true;
      init().then(() => {
        if (isCacheStale(CACHE_KEY_OP)) {
          const currentAno = filters.ano || defaultAno;
          loadData({ ...filters, ano: currentAno }, true);
        }
        mountHandlingRef.current = false;
      });
    } else {
      init();
    }
  }, []);

  useEffect(() => {
    if (mountHandlingRef.current) return;
    if (!loading && filters.ano) {
      const timer = window.setTimeout(() => loadData(filters, false), 250);
      return () => window.clearTimeout(timer);
    }
  }, [filters, loading, loadData]);

  const cardClass = `rounded-2xl p-6 ${isDark ? 'bg-gray-800/60 backdrop-blur-xl border border-gray-700/50' : 'bg-white/80 backdrop-blur-xl border border-gray-200/80'}`;

  if (loading && !opData) return (
    <div className="min-h-screen flex items-center justify-center">
      <div className="w-8 h-8 border-4 border-indigo-500 border-t-transparent rounded-full animate-spin" />
    </div>
  );

  return (
    <div className="min-h-screen">
      <div className="fixed inset-0 pointer-events-none overflow-hidden">
        <div className="absolute top-0 left-1/4 w-96 h-96 bg-indigo-500/10 rounded-full blur-3xl animate-pulse" />
        <div className="absolute bottom-0 right-1/4 w-96 h-96 bg-purple-500/10 rounded-full blur-3xl animate-pulse" style={{ animationDelay: '1s' }} />
      </div>

      <div className="relative z-10 space-y-6 p-6">
        <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-xl bg-gradient-to-br from-indigo-500 to-purple-500 shadow-lg shadow-indigo-500/30">
              <LayoutDashboard className="w-6 h-6 text-white" />
            </div>
            <div>
              <h1 className={`text-3xl font-black tracking-tight ${isDark ? 'text-white' : 'text-gray-900'}`}>
                Dashboard
                <span className="bg-gradient-to-r from-indigo-400 via-purple-500 to-pink-500 bg-clip-text text-transparent"> Consolidado</span>
              </h1>
              <p className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>Visão geral do portfólio de eventos</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <button onClick={() => loadData(filters)} disabled={refreshing}
              className={`flex items-center gap-2 px-4 py-3 rounded-xl border transition-all ${
                isDark ? 'bg-gray-800/50 border-gray-700 text-gray-300 hover:bg-gray-700' : 'bg-white/70 border-gray-200 text-gray-700 hover:bg-gray-50'
              }`}>
              <RefreshCw className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''}`} />
              <span className="font-medium text-sm">Atualizar</span>
            </button>
            <button onClick={() => setShowFilters(!showFilters)}
              className={`flex items-center gap-2 px-4 py-3 rounded-xl border transition-all ${
                showFilters || activeFiltersCount > 0
                  ? 'bg-indigo-500/20 border-indigo-500/50 text-indigo-400'
                  : isDark ? 'bg-gray-800/50 border-gray-700 text-gray-300 hover:bg-gray-700' : 'bg-white/70 border-gray-200 text-gray-700 hover:bg-gray-50'
              }`}>
              <Filter className="w-5 h-5" />
              <span className="font-medium text-sm">Filtros</span>
              {activeFiltersCount > 0 && (
                <span className="px-2 py-0.5 text-xs font-bold bg-indigo-500 text-white rounded-full">{activeFiltersCount}</span>
              )}
              <ChevronDown className={`w-4 h-4 transition-transform ${showFilters ? 'rotate-180' : ''}`} />
            </button>
            {activeFiltersCount > 0 && (
              <button onClick={clearFilters}
                className={`flex items-center gap-2 px-4 py-3 rounded-xl border ${isDark ? 'border-gray-700 text-gray-300 hover:bg-gray-700' : 'border-gray-200 text-gray-700 hover:bg-gray-50'} transition-all`}>
                <RotateCcw className="w-4 h-4" />
                <span className="font-medium text-sm">Limpar</span>
              </button>
            )}
          </div>
        </div>

        {showFilters && (
          <div className={`relative z-[100] p-5 rounded-2xl ${isDark ? 'bg-gray-800/50 backdrop-blur-xl border border-gray-700/50' : 'bg-white/70 backdrop-blur-xl border border-gray-200'}`}>
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
              <SearchableDropdown label="Ano" options={filterOptions.anos} value={filters.ano}
                onChange={v => setFilters(p => ({ ...p, ano: v as number }))} placeholder="Selecione o ano" isDark={isDark} />
              <SearchableDropdown label="Mês" options={filterOptions.meses} value={filters.mes}
                onChange={v => setFilters(p => ({ ...p, mes: v as number | null }))} placeholder="Todos" isDark={isDark} />
              <SearchableDropdown label="Produto" options={filterOptions.produtos} value={filters.produto}
                onChange={v => setFilters(p => ({ ...p, produto: v as string | null }))} placeholder="Todos" isDark={isDark} />
              <SearchableDropdown label="Modalidade" options={filterOptions.modalidades} value={filters.modalidade}
                onChange={v => setFilters(p => ({ ...p, modalidade: v as string | null }))} placeholder="Todas" isDark={isDark} />
              <SearchableDropdown label="Cidade" options={filterOptions.cidades} value={filters.cidade}
                onChange={v => setFilters(p => ({ ...p, cidade: v as string | null }))} placeholder="Todas" isDark={isDark} />
            </div>
          </div>
        )}

        {error && (
          <div className="p-4 rounded-xl bg-red-500/10 border border-red-500/30 text-red-400 text-sm">{error}</div>
        )}

        {refreshing && (
          <div className="flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-medium text-indigo-400 bg-indigo-500/10 border border-indigo-500/20 w-fit">
            <div className="w-3 h-3 border-2 border-indigo-400 border-t-transparent rounded-full animate-spin" />
            Atualizando dados...
          </div>
        )}

        {canSeeFinancial && (
          <div className="space-y-4">
            <SectionLabel label="Relatório Financeiro" isDark={isDark}
              color={isDark ? 'text-emerald-400 bg-emerald-500/10' : 'text-emerald-600 bg-emerald-50'} />
            <RelatorioFinanceiro
              data={relData || { meses: [] }}
              loading={relLoading && !relData}
              onRefresh={() => loadData(filters, true)}
            />
          </div>
        )}

        {opData && (
          <div className="space-y-6">

            {opData.tabela_eventos?.length > 0 && (
              <EventosInscricoesTable rows={opData.tabela_eventos} isDark={isDark} />
            )}

          </div>
        )}

        {!opData && !refreshing && !error && (
          <div className="flex items-center justify-center py-20">
            <p className={`text-sm ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>Selecione um período para visualizar os dados</p>
          </div>
        )}
      </div>
    </div>
  );
};

export default Dashboard;
