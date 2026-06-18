import React, { useState, useEffect, useMemo, useCallback } from 'react';
import { useTheme } from '../../context/ThemeContext';
import {
  detalheEventosService,
  DetalheEventoDisponivel,
  DetalheEventoPayload,
  DetalheRow,
} from '../../services/api';
import {
  Search,
  RefreshCw,
  ChevronDown,
  ChevronRight,
  AlertTriangle,
  Table2,
  Users,
  TrendingUp,
  DollarSign,
  Tag,
  X,
  Filter,
  Database,
  Layers,
} from 'lucide-react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  Legend,
} from 'recharts';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const fmt = (n: number) =>
  n.toLocaleString('pt-BR', { minimumFractionDigits: 0, maximumFractionDigits: 0 });

const fmtR = (n: number) =>
  n.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL', minimumFractionDigits: 2 });

const nullLabel = '—';
const val = (v: string | null | undefined) => v || nullLabel;

const CANAL_COLORS: Record<string, string> = {
  Site: '#3b82f6',
  'Grupos/B2B': '#8b5cf6',
  Cortesia: '#6b7280',
};

const CHART_COLORS = [
  '#3b82f6', '#8b5cf6', '#06b6d4', '#10b981', '#f59e0b',
  '#ef4444', '#ec4899', '#84cc16', '#f97316', '#6366f1',
];

// ---------------------------------------------------------------------------
// KPI Card
// ---------------------------------------------------------------------------

interface KpiCardProps {
  label: string;
  value: string;
  sub?: string;
  icon: React.ReactNode;
  color: string;
  dark: boolean;
}

const KpiCard: React.FC<KpiCardProps> = ({ label, value, sub, icon, color, dark }) => (
  <div className={`rounded-xl p-4 flex items-start gap-3 ${dark ? 'bg-gray-800 border border-gray-700' : 'bg-white border border-gray-200'} shadow-sm`}>
    <div className={`p-2 rounded-lg ${color}`}>
      {icon}
    </div>
    <div className="min-w-0">
      <p className={`text-xs font-medium uppercase tracking-wide ${dark ? 'text-gray-400' : 'text-gray-500'}`}>{label}</p>
      <p className={`text-xl font-bold ${dark ? 'text-white' : 'text-gray-900'}`}>{value}</p>
      {sub && <p className={`text-xs ${dark ? 'text-gray-500' : 'text-gray-400'} mt-0.5`}>{sub}</p>}
    </div>
  </div>
);

// ---------------------------------------------------------------------------
// Canal badge
// ---------------------------------------------------------------------------

const CanalBadge: React.FC<{ canal: string | null }> = ({ canal }) => {
  const map: Record<string, string> = {
    Site: 'bg-blue-100 text-blue-700',
    'Grupos/B2B': 'bg-purple-100 text-purple-700',
    Cortesia: 'bg-gray-100 text-gray-600',
  };
  const cls = (canal && map[canal]) || 'bg-gray-100 text-gray-600';
  return (
    <span className={`inline-block px-2 py-0.5 text-xs font-medium rounded-full ${cls}`}>
      {val(canal)}
    </span>
  );
};

// ---------------------------------------------------------------------------
// Banco badge
// ---------------------------------------------------------------------------

const BancoBadge: React.FC<{ banco: string }> = ({ banco }) => {
  const cls =
    banco === 'Ativo'
      ? 'bg-emerald-100 text-emerald-700'
      : 'bg-orange-100 text-orange-700';
  return (
    <span className={`inline-block px-1.5 py-0.5 text-[10px] font-semibold rounded ${cls}`}>
      {banco}
    </span>
  );
};

// ---------------------------------------------------------------------------
// Tree node types
// ---------------------------------------------------------------------------

interface TreeNode {
  key: string;
  label: string;
  inscritos: number;
  receita_bruta: number;
  receita_liquida: number;
  ticket_medio: number;
  bancos?: string[];
  canal?: string | null;
  depth: number;
  children?: TreeNode[];
  isLeaf?: boolean;
  raw?: DetalheRow;
}

const DIM_LABELS: Record<string, string> = {
  kit: 'Kit',
  canal: 'Canal',
  distancia: 'Distância',
  modalidade: 'Modalidade',
  pelotao: 'Pelotão',
  produtos: 'Produtos',
  tamanho_camiseta: 'Tamanho',
};

type DimKey = 'canal' | 'kit' | 'distancia' | 'modalidade' | 'pelotao' | 'produtos' | 'tamanho_camiseta';

const DEFAULT_HIERARCHY: DimKey[] = ['canal', 'kit', 'distancia', 'modalidade', 'tamanho_camiseta'];

function buildTree(rows: DetalheRow[], hierarchy: DimKey[]): TreeNode[] {
  function group(items: DetalheRow[], dims: DimKey[], depth: number): TreeNode[] {
    if (dims.length === 0 || items.length === 0) return [];
    const [dim, ...rest] = dims;
    const grouped = new Map<string, DetalheRow[]>();
    for (const row of items) {
      const k = row[dim] ?? nullLabel;
      if (!grouped.has(k)) grouped.set(k, []);
      grouped.get(k)!.push(row);
    }
    const nodes: TreeNode[] = [];
    grouped.forEach((groupRows, k) => {
      const totalIns = groupRows.reduce((s, r) => s + (r.inscritos || 0), 0);
      const totalBruta = groupRows.reduce((s, r) => s + (r.receita_bruta || 0), 0);
      const totalLiq = groupRows.reduce((s, r) => s + (r.receita_liquida || 0), 0);
      const bancos = [...new Set(groupRows.flatMap(r => r.bancos || []))];
      const isLeaf = rest.length === 0 || groupRows.length === 1;
      const node: TreeNode = {
        key: `${depth}-${dim}-${k}`,
        label: k,
        inscritos: totalIns,
        receita_bruta: totalBruta,
        receita_liquida: totalLiq,
        ticket_medio: totalIns > 0 ? totalLiq / totalIns : 0,
        bancos,
        canal: dim === 'canal' ? (groupRows[0]?.canal ?? null) : groupRows[0]?.canal ?? null,
        depth,
        isLeaf,
      };
      if (!isLeaf) {
        node.children = group(groupRows, rest, depth + 1);
      } else if (rest.length > 0 && groupRows.length === 1) {
        node.raw = groupRows[0];
      }
      nodes.push(node);
    });
    nodes.sort((a, b) => b.inscritos - a.inscritos);
    return nodes;
  }
  return group(rows, hierarchy, 0);
}

// ---------------------------------------------------------------------------
// TreeRow component
// ---------------------------------------------------------------------------

interface TreeRowProps {
  node: TreeNode;
  dark: boolean;
  expanded: Set<string>;
  onToggle: (key: string) => void;
  totalInscritos: number;
}

const TreeRow: React.FC<TreeRowProps> = ({ node, dark, expanded, onToggle, totalInscritos }) => {
  const isOpen = expanded.has(node.key);
  const hasChildren = node.children && node.children.length > 0;
  const pct = totalInscritos > 0 ? (node.inscritos / totalInscritos) * 100 : 0;

  const depthPad = node.depth * 20;
  const rowBg = node.depth === 0
    ? dark ? 'bg-gray-700/60' : 'bg-gray-50'
    : node.depth === 1
    ? dark ? 'bg-gray-800/40' : 'bg-white'
    : dark ? 'bg-gray-800/20' : 'bg-gray-50/50';

  return (
    <>
      <tr
        className={`border-b ${dark ? 'border-gray-700' : 'border-gray-100'} ${rowBg} ${hasChildren ? 'cursor-pointer hover:opacity-80' : ''} transition-opacity`}
        onClick={() => hasChildren && onToggle(node.key)}
      >
        <td className="py-2 pr-3" style={{ paddingLeft: depthPad + 12 }}>
          <div className="flex items-center gap-1.5">
            {hasChildren ? (
              isOpen
                ? <ChevronDown className="w-3.5 h-3.5 text-blue-400 flex-shrink-0" />
                : <ChevronRight className="w-3.5 h-3.5 text-blue-400 flex-shrink-0" />
            ) : (
              <span className="w-3.5" />
            )}
            <span className={`text-sm ${node.depth === 0 ? 'font-semibold' : 'font-normal'} ${dark ? 'text-gray-100' : 'text-gray-800'} truncate max-w-[240px]`}>
              {node.label}
            </span>
            {node.bancos && node.bancos.length > 0 && node.depth > 1 && (
              <span className="flex gap-1 ml-1">
                {node.bancos.map(b => <BancoBadge key={b} banco={b} />)}
              </span>
            )}
          </div>
        </td>
        <td className={`py-2 px-3 text-right text-sm ${dark ? 'text-gray-300' : 'text-gray-700'}`}>
          <div className="flex flex-col items-end gap-0.5">
            <span className="font-medium">{fmt(node.inscritos)}</span>
            <div className="w-16 h-1 rounded-full bg-gray-200 dark:bg-gray-600 overflow-hidden">
              <div
                className="h-full bg-blue-500 rounded-full"
                style={{ width: `${Math.min(pct, 100)}%` }}
              />
            </div>
          </div>
        </td>
        <td className={`py-2 px-3 text-right text-xs ${dark ? 'text-gray-400' : 'text-gray-500'}`}>
          {pct.toFixed(1)}%
        </td>
        <td className={`py-2 px-3 text-right text-sm ${dark ? 'text-gray-300' : 'text-gray-700'}`}>
          {fmtR(node.receita_bruta)}
        </td>
        <td className={`py-2 px-3 text-right text-sm font-medium ${dark ? 'text-emerald-400' : 'text-emerald-700'}`}>
          {fmtR(node.receita_liquida)}
        </td>
        <td className={`py-2 px-3 text-right text-sm ${dark ? 'text-amber-400' : 'text-amber-700'}`}>
          {fmtR(node.ticket_medio)}
        </td>
      </tr>
      {hasChildren && isOpen && node.children!.map(child => (
        <TreeRow
          key={child.key}
          node={child}
          dark={dark}
          expanded={expanded}
          onToggle={onToggle}
          totalInscritos={totalInscritos}
        />
      ))}
    </>
  );
};

// ---------------------------------------------------------------------------
// Dimension filter chip
// ---------------------------------------------------------------------------

interface FilterState {
  canal: string;
  kit: string;
  distancia: string;
  modalidade: string;
  pelotao: string;
  produtos: string;
  tamanho_camiseta: string;
  banco: string;
  search: string;
}

const EMPTY_FILTERS: FilterState = {
  canal: '', kit: '', distancia: '', modalidade: '',
  pelotao: '', produtos: '', tamanho_camiseta: '', banco: '', search: '',
};

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

const DetalheEventos: React.FC = () => {
  const { theme } = useTheme();
  const dark = theme === 'dark';

  const [eventos, setEventos] = useState<DetalheEventoDisponivel[]>([]);
  const [eventoGrupo, setEventoGrupo] = useState<string>('');
  const [payload, setPayload] = useState<DetalheEventoPayload | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadingEventos, setLoadingEventos] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filters, setFilters] = useState<FilterState>(EMPTY_FILTERS);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [hierarchy] = useState<DimKey[]>(DEFAULT_HIERARCHY);
  const [viewMode, setViewMode] = useState<'tree' | 'flat'>('tree');
  const [activeTab, setActiveTab] = useState<'consolidado' | 'ativo' | 'magento'>('consolidado');
  const [searchEventos, setSearchEventos] = useState('');

  // Load event list
  useEffect(() => {
    setLoadingEventos(true);
    detalheEventosService.listEventos()
      .then(setEventos)
      .catch(e => setError(e?.response?.data?.detail || e.message))
      .finally(() => setLoadingEventos(false));
  }, []);

  // Load detail when event changes
  const loadDetalhe = useCallback(async (grupo: string, force = false) => {
    if (!grupo) return;
    setLoading(true);
    setError(null);
    setExpanded(new Set());
    setFilters(EMPTY_FILTERS);
    try {
      const data = await detalheEventosService.getDetalhe(grupo, force);
      setPayload(data);
    } catch (e: any) {
      setError(e?.response?.data?.detail || e.message || 'Erro ao carregar dados');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (eventoGrupo) loadDetalhe(eventoGrupo);
  }, [eventoGrupo]);

  const handleToggle = useCallback((key: string) => {
    setExpanded(prev => {
      const next = new Set(prev);
      next.has(key) ? next.delete(key) : next.add(key);
      return next;
    });
  }, []);

  // Filtered rows
  const filteredRows = useMemo<DetalheRow[]>(() => {
    if (!payload) return [];
    let rows =
      activeTab === 'consolidado'
        ? payload.consolidado
        : activeTab === 'ativo'
        ? payload.por_banco.Ativo
        : payload.por_banco.Magento;

    if (filters.canal) rows = rows.filter(r => r.canal === filters.canal);
    if (filters.kit) rows = rows.filter(r => (r.kit || nullLabel) === filters.kit);
    if (filters.distancia) rows = rows.filter(r => (r.distancia || nullLabel) === filters.distancia);
    if (filters.modalidade) rows = rows.filter(r => (r.modalidade || nullLabel) === filters.modalidade);
    if (filters.pelotao) rows = rows.filter(r => (r.pelotao || nullLabel) === filters.pelotao);
    if (filters.produtos) rows = rows.filter(r => (r.produtos || nullLabel) === filters.produtos);
    if (filters.tamanho_camiseta) rows = rows.filter(r => (r.tamanho_camiseta || nullLabel) === filters.tamanho_camiseta);
    if (filters.search) {
      const q = filters.search.toLowerCase();
      rows = rows.filter(r =>
        [r.kit, r.distancia, r.modalidade, r.canal, r.pelotao, r.produtos, r.tamanho_camiseta]
          .some(v => v?.toLowerCase().includes(q))
      );
    }
    return rows;
  }, [payload, activeTab, filters]);

  // Unique values for filter dropdowns
  const opts = useMemo(() => {
    if (!payload) return {} as Record<string, string[]>;
    const all = [...payload.consolidado];
    const uniq = (key: keyof DetalheRow) =>
      [...new Set(all.map(r => r[key] as string | null).map(v => v ?? nullLabel))].sort();
    return {
      canal: uniq('canal'),
      kit: uniq('kit'),
      distancia: uniq('distancia'),
      modalidade: uniq('modalidade'),
      pelotao: uniq('pelotao'),
      produtos: uniq('produtos'),
      tamanho_camiseta: uniq('tamanho_camiseta'),
    };
  }, [payload]);

  // Tree
  const tree = useMemo(() => buildTree(filteredRows, hierarchy), [filteredRows, hierarchy]);

  // Chart data
  const canalChartData = useMemo(() => {
    if (!payload) return [];
    return Object.entries(payload.totais.por_canal).map(([canal, v]) => ({
      canal,
      inscritos: v.inscritos,
      receita: Math.round(v.receita_liquida),
    })).sort((a, b) => b.inscritos - a.inscritos);
  }, [payload]);

  const distanciaChartData = useMemo(() => {
    if (!payload) return [];
    const map = new Map<string, number>();
    payload.consolidado.forEach(r => {
      const k = r.distancia || nullLabel;
      map.set(k, (map.get(k) || 0) + r.inscritos);
    });
    return [...map.entries()]
      .map(([name, value]) => ({ name, value }))
      .sort((a, b) => b.value - a.value)
      .slice(0, 12);
  }, [payload]);

  const tamanhoChartData = useMemo(() => {
    if (!payload) return [];
    const map = new Map<string, number>();
    payload.consolidado.forEach(r => {
      const k = r.tamanho_camiseta || nullLabel;
      if (k !== nullLabel) map.set(k, (map.get(k) || 0) + r.inscritos);
    });
    return [...map.entries()]
      .map(([name, value]) => ({ name, value }))
      .sort((a, b) => b.value - a.value);
  }, [payload]);

  const totalInscritos = payload?.totais.inscritos ?? 0;

  const filteredEventos = useMemo(() =>
    eventos.filter(e =>
      !searchEventos ||
      e.nome_evento.toLowerCase().includes(searchEventos.toLowerCase()) ||
      e.evento_grupo.toLowerCase().includes(searchEventos.toLowerCase())
    ),
    [eventos, searchEventos]
  );

  const activeFiltersCount = Object.entries(filters).filter(([k, v]) => k !== 'search' && v !== '').length;

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------

  const cardBg = dark ? 'bg-gray-800 border-gray-700' : 'bg-white border-gray-200';
  const textPrimary = dark ? 'text-white' : 'text-gray-900';
  const textSec = dark ? 'text-gray-400' : 'text-gray-500';
  const borderCol = dark ? 'border-gray-700' : 'border-gray-200';

  return (
    <div className={`min-h-screen p-4 lg:p-6 ${dark ? 'bg-gray-900' : 'bg-gray-50'}`}>
      {/* Header */}
      <div className="mb-6">
        <div className="flex items-center gap-2 mb-1">
          <Table2 className={`w-5 h-5 ${dark ? 'text-blue-400' : 'text-blue-600'}`} />
          <h1 className={`text-xl font-bold ${textPrimary}`}>Detalhamento de Eventos</h1>
        </div>
        <p className={`text-sm ${textSec}`}>
          Visão granular de inscrições e receita por Canal · Kit · Distância · Modalidade · Pelotão · Produtos · Tamanho
        </p>
      </div>

      {/* Event Selector */}
      <div className={`rounded-xl border ${cardBg} p-4 mb-6 shadow-sm`}>
        <div className="flex flex-col sm:flex-row gap-3 items-start sm:items-center">
          <div className="flex-1 min-w-0">
            <label className={`block text-xs font-semibold uppercase tracking-wide mb-1 ${textSec}`}>
              Evento
            </label>
            {loadingEventos ? (
              <div className="h-9 w-full rounded-lg bg-gray-200 dark:bg-gray-700 animate-pulse" />
            ) : (
              <div className="relative">
                <select
                  value={eventoGrupo}
                  onChange={e => { setEventoGrupo(e.target.value); }}
                  className={`w-full rounded-lg border px-3 py-2 text-sm appearance-none pr-8 focus:outline-none focus:ring-2 focus:ring-blue-500 ${
                    dark
                      ? 'bg-gray-700 border-gray-600 text-gray-100'
                      : 'bg-white border-gray-300 text-gray-900'
                  }`}
                >
                  <option value="">— Selecionar evento —</option>
                  {filteredEventos.map(e => (
                    <option key={e.evento_grupo} value={e.evento_grupo}>
                      {e.nome_evento} {e.anos.length > 0 ? `(${e.anos[0]})` : ''}
                    </option>
                  ))}
                </select>
                <ChevronDown className={`absolute right-2 top-2.5 w-4 h-4 pointer-events-none ${textSec}`} />
              </div>
            )}
          </div>
          <div className="flex items-end gap-2">
            {/* Search eventos */}
            <div className="relative">
              <Search className={`absolute left-2.5 top-2.5 w-3.5 h-3.5 ${textSec} pointer-events-none`} />
              <input
                type="text"
                placeholder="Buscar evento…"
                value={searchEventos}
                onChange={e => setSearchEventos(e.target.value)}
                className={`pl-8 pr-3 py-2 text-sm rounded-lg border focus:outline-none focus:ring-2 focus:ring-blue-500 ${
                  dark
                    ? 'bg-gray-700 border-gray-600 text-gray-100 placeholder-gray-500'
                    : 'bg-white border-gray-300 text-gray-900 placeholder-gray-400'
                }`}
                style={{ width: 160 }}
              />
            </div>
            <button
              onClick={() => eventoGrupo && loadDetalhe(eventoGrupo, true)}
              disabled={!eventoGrupo || loading}
              title="Recarregar sem cache"
              className={`flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                dark
                  ? 'bg-gray-700 hover:bg-gray-600 text-gray-200 disabled:opacity-40'
                  : 'bg-gray-100 hover:bg-gray-200 text-gray-700 disabled:opacity-40'
              }`}
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
              Atualizar
            </button>
          </div>
        </div>
      </div>

      {/* Error state */}
      {error && (
        <div className="mb-4 flex items-start gap-2 rounded-lg bg-red-50 border border-red-200 p-3 text-red-700">
          <AlertTriangle className="w-4 h-4 flex-shrink-0 mt-0.5" />
          <p className="text-sm">{error}</p>
        </div>
      )}

      {/* Loading skeleton */}
      {loading && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            {[...Array(4)].map((_, i) => (
              <div key={i} className={`h-20 rounded-xl animate-pulse ${dark ? 'bg-gray-800' : 'bg-gray-200'}`} />
            ))}
          </div>
          <div className={`h-64 rounded-xl animate-pulse ${dark ? 'bg-gray-800' : 'bg-gray-200'}`} />
        </div>
      )}

      {/* Empty state */}
      {!loading && !payload && !error && (
        <div className={`rounded-xl border ${cardBg} p-12 text-center shadow-sm`}>
          <Table2 className={`w-12 h-12 mx-auto mb-3 ${dark ? 'text-gray-600' : 'text-gray-300'}`} />
          <p className={`text-base font-medium ${textPrimary}`}>Nenhum evento selecionado</p>
          <p className={`text-sm mt-1 ${textSec}`}>Selecione um evento acima para visualizar o detalhamento completo.</p>
        </div>
      )}

      {/* Main content */}
      {!loading && payload && (
        <>
          {/* Banco errors */}
          {Object.keys(payload.erros).length > 0 && (
            <div className="mb-4 flex items-start gap-2 rounded-lg bg-amber-50 border border-amber-200 p-3 text-amber-700">
              <AlertTriangle className="w-4 h-4 flex-shrink-0 mt-0.5" />
              <div>
                <p className="text-sm font-semibold">Atenção: erros ao buscar dados de alguns bancos</p>
                {Object.entries(payload.erros).map(([banco, msg]) => (
                  <p key={banco} className="text-xs mt-0.5">{banco}: {msg}</p>
                ))}
              </div>
            </div>
          )}

          {/* Divergencias */}
          {payload.divergencias.length > 0 && (
            <div className="mb-4 flex items-start gap-2 rounded-lg bg-red-50 border border-red-200 p-3 text-red-700">
              <AlertTriangle className="w-4 h-4 flex-shrink-0 mt-0.5" />
              <div>
                <p className="text-sm font-semibold">{payload.divergencias.length} divergência(s) detectada(s) na consolidação</p>
                <p className="text-xs mt-0.5">A soma dos bancos individualmente difere do total consolidado em algumas combinações de dimensões.</p>
              </div>
            </div>
          )}

          {/* KPI Cards */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
            <KpiCard
              label="Total Inscritos"
              value={fmt(payload.totais.inscritos)}
              icon={<Users className="w-4 h-4 text-blue-600" />}
              color="bg-blue-50"
              dark={dark}
            />
            <KpiCard
              label="Receita Bruta"
              value={fmtR(payload.totais.receita_bruta)}
              icon={<DollarSign className="w-4 h-4 text-emerald-600" />}
              color="bg-emerald-50"
              dark={dark}
            />
            <KpiCard
              label="Receita Líquida"
              value={fmtR(payload.totais.receita_liquida)}
              icon={<TrendingUp className="w-4 h-4 text-indigo-600" />}
              color="bg-indigo-50"
              dark={dark}
            />
            <KpiCard
              label="Ticket Médio"
              value={fmtR(payload.totais.ticket_medio)}
              sub="Por inscrito (receita líquida)"
              icon={<Tag className="w-4 h-4 text-amber-600" />}
              color="bg-amber-50"
              dark={dark}
            />
          </div>

          {/* Canal breakdown pills */}
          <div className="flex flex-wrap gap-2 mb-5">
            {Object.entries(payload.totais.por_canal).map(([canal, stats]) => (
              <button
                key={canal}
                onClick={() => setFilters(f => ({ ...f, canal: f.canal === canal ? '' : canal }))}
                className={`flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-semibold border transition-all ${
                  filters.canal === canal
                    ? 'ring-2 ring-offset-1 ring-blue-500'
                    : ''
                } ${dark ? 'border-gray-600 bg-gray-700 text-gray-200 hover:bg-gray-600' : 'border-gray-200 bg-white text-gray-700 hover:bg-gray-50'}`}
              >
                <span className="w-2.5 h-2.5 rounded-full" style={{ background: CANAL_COLORS[canal] || '#6b7280' }} />
                <span>{canal}</span>
                <span className={dark ? 'text-gray-400' : 'text-gray-500'}>{fmt(stats.inscritos)}</span>
              </button>
            ))}
            {filters.canal && (
              <button
                onClick={() => setFilters(f => ({ ...f, canal: '' }))}
                className="flex items-center gap-1 px-2 py-1.5 text-xs text-red-500 hover:text-red-700"
              >
                <X className="w-3 h-3" /> Limpar filtro canal
              </button>
            )}
          </div>

          {/* Charts row */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-6">
            {/* Canal chart */}
            <div className={`rounded-xl border ${cardBg} p-4 shadow-sm`}>
              <p className={`text-xs font-semibold uppercase tracking-wide mb-3 ${textSec}`}>Inscritos por Canal</p>
              <ResponsiveContainer width="100%" height={140}>
                <BarChart data={canalChartData} barSize={32}>
                  <XAxis dataKey="canal" tick={{ fontSize: 11, fill: dark ? '#9ca3af' : '#6b7280' }} axisLine={false} tickLine={false} />
                  <YAxis hide />
                  <Tooltip
                    formatter={(v: number) => [fmt(v), 'Inscritos']}
                    contentStyle={{ background: dark ? '#1f2937' : '#fff', border: 'none', borderRadius: 8, fontSize: 12 }}
                  />
                  <Bar dataKey="inscritos" radius={[4, 4, 0, 0]}>
                    {canalChartData.map((entry, i) => (
                      <Cell key={i} fill={CANAL_COLORS[entry.canal] || CHART_COLORS[i % CHART_COLORS.length]} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>

            {/* Distância chart */}
            <div className={`rounded-xl border ${cardBg} p-4 shadow-sm`}>
              <p className={`text-xs font-semibold uppercase tracking-wide mb-3 ${textSec}`}>Top Distâncias (inscritos)</p>
              <ResponsiveContainer width="100%" height={140}>
                <BarChart data={distanciaChartData.slice(0, 8)} layout="vertical" barSize={12}>
                  <XAxis type="number" hide />
                  <YAxis type="category" dataKey="name" width={80} tick={{ fontSize: 10, fill: dark ? '#9ca3af' : '#6b7280' }} axisLine={false} tickLine={false} />
                  <Tooltip
                    formatter={(v: number) => [fmt(v), 'Inscritos']}
                    contentStyle={{ background: dark ? '#1f2937' : '#fff', border: 'none', borderRadius: 8, fontSize: 12 }}
                  />
                  <Bar dataKey="value" radius={[0, 4, 4, 0]}>
                    {distanciaChartData.slice(0, 8).map((_, i) => (
                      <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>

            {/* Tamanho camiseta chart */}
            <div className={`rounded-xl border ${cardBg} p-4 shadow-sm`}>
              <p className={`text-xs font-semibold uppercase tracking-wide mb-3 ${textSec}`}>Tamanhos de Camiseta</p>
              {tamanhoChartData.length > 0 ? (
                <ResponsiveContainer width="100%" height={140}>
                  <PieChart>
                    <Pie
                      data={tamanhoChartData}
                      dataKey="value"
                      nameKey="name"
                      cx="50%"
                      cy="50%"
                      outerRadius={52}
                      innerRadius={28}
                    >
                      {tamanhoChartData.map((_, i) => (
                        <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip
                      formatter={(v: number, name: string) => [fmt(v), name]}
                      contentStyle={{ background: dark ? '#1f2937' : '#fff', border: 'none', borderRadius: 8, fontSize: 12 }}
                    />
                    <Legend iconSize={8} iconType="circle" wrapperStyle={{ fontSize: 10 }} />
                  </PieChart>
                </ResponsiveContainer>
              ) : (
                <div className={`flex items-center justify-center h-[140px] text-sm ${textSec}`}>
                  Sem dados de tamanho
                </div>
              )}
            </div>
          </div>

          {/* Filters bar */}
          <div className={`rounded-xl border ${cardBg} p-3 mb-4 shadow-sm`}>
            <div className="flex flex-wrap gap-2 items-center">
              <div className="flex items-center gap-1.5 mr-1">
                <Filter className={`w-3.5 h-3.5 ${textSec}`} />
                <span className={`text-xs font-semibold ${textSec}`}>Filtros</span>
                {activeFiltersCount > 0 && (
                  <span className="bg-blue-500 text-white text-[10px] font-bold px-1.5 py-0.5 rounded-full">
                    {activeFiltersCount}
                  </span>
                )}
              </div>

              {/* Search */}
              <div className="relative">
                <Search className={`absolute left-2 top-1.5 w-3.5 h-3.5 ${textSec}`} />
                <input
                  type="text"
                  placeholder="Buscar…"
                  value={filters.search}
                  onChange={e => setFilters(f => ({ ...f, search: e.target.value }))}
                  className={`pl-7 pr-3 py-1 text-xs rounded-lg border focus:outline-none focus:ring-2 focus:ring-blue-500 ${
                    dark
                      ? 'bg-gray-700 border-gray-600 text-gray-100 placeholder-gray-500'
                      : 'bg-white border-gray-300 text-gray-900 placeholder-gray-400'
                  }`}
                  style={{ width: 130 }}
                />
              </div>

              {/* Dimension dropdowns */}
              {(Object.entries(opts) as [string, string[]][]).map(([dim, values]) => (
                <select
                  key={dim}
                  value={(filters as any)[dim]}
                  onChange={e => setFilters(f => ({ ...f, [dim]: e.target.value }))}
                  className={`text-xs rounded-lg border px-2 py-1 focus:outline-none focus:ring-2 focus:ring-blue-500 ${
                    (filters as any)[dim]
                      ? 'ring-1 ring-blue-500'
                      : ''
                  } ${
                    dark
                      ? 'bg-gray-700 border-gray-600 text-gray-100'
                      : 'bg-white border-gray-300 text-gray-900'
                  }`}
                >
                  <option value="">{DIM_LABELS[dim] || dim}</option>
                  {values.map(v => <option key={v} value={v}>{v}</option>)}
                </select>
              ))}

              {/* Clear */}
              {(activeFiltersCount > 0 || filters.search) && (
                <button
                  onClick={() => setFilters(EMPTY_FILTERS)}
                  className="flex items-center gap-1 text-xs text-red-500 hover:text-red-700 ml-1"
                >
                  <X className="w-3 h-3" /> Limpar
                </button>
              )}
            </div>
          </div>

          {/* Table */}
          <div className={`rounded-xl border ${cardBg} shadow-sm overflow-hidden`}>
            {/* Tabs + view toggle */}
            <div className={`flex items-center justify-between px-4 py-2 border-b ${borderCol}`}>
              <div className="flex gap-1">
                {(['consolidado', 'ativo', 'magento'] as const).map(tab => (
                  <button
                    key={tab}
                    onClick={() => { setActiveTab(tab); setExpanded(new Set()); }}
                    className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors ${
                      activeTab === tab
                        ? 'bg-blue-500 text-white'
                        : dark
                        ? 'text-gray-400 hover:bg-gray-700'
                        : 'text-gray-600 hover:bg-gray-100'
                    }`}
                  >
                    {tab === 'consolidado' && <Layers className="w-3.5 h-3.5" />}
                    {tab === 'ativo' && <Database className="w-3.5 h-3.5" />}
                    {tab === 'magento' && <Database className="w-3.5 h-3.5" />}
                    {tab === 'consolidado'
                      ? `Consolidado (${fmt(payload.consolidado.length)})`
                      : tab === 'ativo'
                      ? `Ativo (${fmt(payload.por_banco.Ativo.length)})`
                      : `Magento (${fmt(payload.por_banco.Magento.length)})`}
                  </button>
                ))}
              </div>
              <div className="flex items-center gap-1">
                <button
                  onClick={() => setViewMode('tree')}
                  className={`p-1.5 rounded text-xs font-medium transition-colors ${
                    viewMode === 'tree'
                      ? 'bg-blue-500 text-white'
                      : dark ? 'text-gray-400 hover:bg-gray-700' : 'text-gray-500 hover:bg-gray-100'
                  }`}
                  title="Visão hierárquica"
                >
                  <Layers className="w-3.5 h-3.5" />
                </button>
                <button
                  onClick={() => setViewMode('flat')}
                  className={`p-1.5 rounded text-xs font-medium transition-colors ${
                    viewMode === 'flat'
                      ? 'bg-blue-500 text-white'
                      : dark ? 'text-gray-400 hover:bg-gray-700' : 'text-gray-500 hover:bg-gray-100'
                  }`}
                  title="Visão plana"
                >
                  <Table2 className="w-3.5 h-3.5" />
                </button>
                {viewMode === 'tree' && (
                  <>
                    <button
                      onClick={() => {
                        const keys = new Set<string>();
                        const collect = (nodes: TreeNode[]) => nodes.forEach(n => {
                          if (n.children) { keys.add(n.key); collect(n.children); }
                        });
                        collect(tree);
                        setExpanded(keys);
                      }}
                      className={`text-xs px-2 py-1 rounded transition-colors ${dark ? 'text-blue-400 hover:bg-gray-700' : 'text-blue-600 hover:bg-blue-50'}`}
                    >
                      Expandir tudo
                    </button>
                    <button
                      onClick={() => setExpanded(new Set())}
                      className={`text-xs px-2 py-1 rounded transition-colors ${dark ? 'text-gray-400 hover:bg-gray-700' : 'text-gray-500 hover:bg-gray-100'}`}
                    >
                      Colapsar
                    </button>
                  </>
                )}
              </div>
            </div>

            {filteredRows.length === 0 ? (
              <div className="py-12 text-center">
                <p className={`text-sm ${textSec}`}>Nenhum dado encontrado com os filtros atuais.</p>
              </div>
            ) : viewMode === 'tree' ? (
              <div className="overflow-auto">
                <table className="w-full min-w-[700px] text-sm">
                  <thead>
                    <tr className={`text-left text-xs font-semibold uppercase tracking-wide ${dark ? 'bg-gray-700/80 text-gray-400' : 'bg-gray-50 text-gray-500'}`}>
                      <th className="py-2 px-3">Dimensão / Valor</th>
                      <th className="py-2 px-3 text-right">Inscritos</th>
                      <th className="py-2 px-3 text-right">%</th>
                      <th className="py-2 px-3 text-right">Rec. Bruta</th>
                      <th className="py-2 px-3 text-right">Rec. Líquida</th>
                      <th className="py-2 px-3 text-right">Ticket Médio</th>
                    </tr>
                  </thead>
                  <tbody>
                    {tree.map(node => (
                      <TreeRow
                        key={node.key}
                        node={node}
                        dark={dark}
                        expanded={expanded}
                        onToggle={handleToggle}
                        totalInscritos={totalInscritos}
                      />
                    ))}
                  </tbody>
                  <tfoot>
                    <tr className={`text-xs font-bold uppercase ${dark ? 'bg-gray-700 text-gray-300 border-t border-gray-600' : 'bg-gray-100 text-gray-700 border-t border-gray-200'}`}>
                      <td className="py-2 px-3">TOTAL FILTRADO</td>
                      <td className="py-2 px-3 text-right">{fmt(filteredRows.reduce((s, r) => s + r.inscritos, 0))}</td>
                      <td className="py-2 px-3 text-right">100%</td>
                      <td className="py-2 px-3 text-right">{fmtR(filteredRows.reduce((s, r) => s + r.receita_bruta, 0))}</td>
                      <td className={`py-2 px-3 text-right ${dark ? 'text-emerald-400' : 'text-emerald-700'}`}>
                        {fmtR(filteredRows.reduce((s, r) => s + r.receita_liquida, 0))}
                      </td>
                      <td className={`py-2 px-3 text-right ${dark ? 'text-amber-400' : 'text-amber-700'}`}>
                        {(() => {
                          const ins = filteredRows.reduce((s, r) => s + r.inscritos, 0);
                          const liq = filteredRows.reduce((s, r) => s + r.receita_liquida, 0);
                          return fmtR(ins > 0 ? liq / ins : 0);
                        })()}
                      </td>
                    </tr>
                  </tfoot>
                </table>
              </div>
            ) : (
              /* Flat view */
              <div className="overflow-auto">
                <table className="w-full min-w-[900px] text-sm">
                  <thead>
                    <tr className={`text-left text-xs font-semibold uppercase tracking-wide ${dark ? 'bg-gray-700/80 text-gray-400' : 'bg-gray-50 text-gray-500'}`}>
                      <th className="py-2 px-3">Canal</th>
                      <th className="py-2 px-3">Kit</th>
                      <th className="py-2 px-3">Distância</th>
                      <th className="py-2 px-3">Modalidade</th>
                      <th className="py-2 px-3">Pelotão</th>
                      <th className="py-2 px-3">Produtos</th>
                      <th className="py-2 px-3">Tamanho</th>
                      <th className="py-2 px-3 text-right">Inscritos</th>
                      <th className="py-2 px-3 text-right">Rec. Liq.</th>
                      <th className="py-2 px-3 text-right">Ticket</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredRows.map((row, i) => (
                      <tr
                        key={i}
                        className={`border-b ${dark ? 'border-gray-700 odd:bg-gray-800/40 even:bg-gray-800/20' : 'border-gray-100 odd:bg-white even:bg-gray-50/50'}`}
                      >
                        <td className="py-1.5 px-3"><CanalBadge canal={row.canal} /></td>
                        <td className={`py-1.5 px-3 text-xs ${dark ? 'text-gray-300' : 'text-gray-700'} max-w-[160px] truncate`} title={row.kit || ''}>{val(row.kit)}</td>
                        <td className={`py-1.5 px-3 text-xs ${dark ? 'text-gray-300' : 'text-gray-700'}`}>{val(row.distancia)}</td>
                        <td className={`py-1.5 px-3 text-xs ${dark ? 'text-gray-400' : 'text-gray-500'}`}>{val(row.modalidade)}</td>
                        <td className={`py-1.5 px-3 text-xs ${dark ? 'text-gray-400' : 'text-gray-500'}`}>{val(row.pelotao)}</td>
                        <td className={`py-1.5 px-3 text-xs ${dark ? 'text-gray-400' : 'text-gray-500'} max-w-[120px] truncate`} title={row.produtos || ''}>{val(row.produtos)}</td>
                        <td className={`py-1.5 px-3 text-xs ${dark ? 'text-gray-300' : 'text-gray-700'}`}>{val(row.tamanho_camiseta)}</td>
                        <td className={`py-1.5 px-3 text-xs text-right font-medium ${dark ? 'text-gray-200' : 'text-gray-800'}`}>{fmt(row.inscritos)}</td>
                        <td className={`py-1.5 px-3 text-xs text-right ${dark ? 'text-emerald-400' : 'text-emerald-700'}`}>{fmtR(row.receita_liquida)}</td>
                        <td className={`py-1.5 px-3 text-xs text-right ${dark ? 'text-amber-400' : 'text-amber-700'}`}>{fmtR(row.ticket_medio)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {/* Row count footer */}
            <div className={`px-4 py-2 border-t ${borderCol} flex justify-between items-center`}>
              <span className={`text-xs ${textSec}`}>
                {filteredRows.length} combinações · {fmt(filteredRows.reduce((s, r) => s + r.inscritos, 0))} inscritos
              </span>
              <span className={`text-xs ${textSec}`}>
                Bancos: Ativo ({fmt(payload.por_banco.Ativo.length)} linhas) · Magento ({fmt(payload.por_banco.Magento.length)} linhas)
              </span>
            </div>
          </div>
        </>
      )}
    </div>
  );
};

export default DetalheEventos;
