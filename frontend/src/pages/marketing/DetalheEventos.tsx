import React, { useState, useEffect, useLayoutEffect, useMemo, useCallback, useRef } from 'react';
import { useTheme } from '../../context/ThemeContext';
import {
  detalheEventosService,
  DetalheEventoDisponivel,
  DetalheEventoPayload,
  DetalheRow,
  DetalheBancoRow,
  userPrefsService,
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
  Info,
  GripVertical,
  RotateCcw,
  Check,
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
import { motion, AnimatePresence, Reorder } from 'framer-motion';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const fmt = (n: number) =>
  n.toLocaleString('pt-BR', { minimumFractionDigits: 0, maximumFractionDigits: 0 });

const fmtR = (n: number) =>
  n.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL', minimumFractionDigits: 2 });

const NULL_LABEL = '—';
const val = (v: string | null | undefined) => v || NULL_LABEL;

const CANAL_COLORS: Record<string, string> = {
  Site: '#3b82f6',
  'Grupos/B2B': '#8b5cf6',
  Cortesia: '#6b7280',
};

const CHART_COLORS = [
  '#3b82f6', '#8b5cf6', '#06b6d4', '#10b981', '#f59e0b',
  '#ef4444', '#ec4899', '#84cc16', '#f97316', '#6366f1',
];

const DIM_LABELS: Record<string, string> = {
  kit: 'Kit',
  canal: 'Canal',
  modalidade: 'Modalidade',
  pelotao: 'Pelotão',
  produtos: 'Produtos',
  tamanho_camiseta: 'Tamanho Camiseta',
};

type DimKey = 'canal' | 'kit' | 'modalidade' | 'pelotao' | 'produtos' | 'tamanho_camiseta';

const DEFAULT_HIERARCHY: DimKey[] = ['kit', 'modalidade', 'pelotao', 'produtos', 'tamanho_camiseta'];

const ALL_DIMS = Object.keys(DIM_LABELS) as DimKey[];

// Preferência de granularidade da árvore — a fonte da verdade é a conta do
// usuário no servidor; o localStorage vira cache local/fallback offline.
const HIERARCHY_STORAGE_KEY = 'detalhe_eventos_hierarchy_v1';

const sameHierarchy = (a: DimKey[], b: DimKey[]) =>
  a.length === b.length && a.every((d, i) => d === b[i]);

// Colunas de dimensão da visão plana (mesmo padrão de persistência da árvore,
// chave separada — layouts independentes)
const FLAT_COLS_STORAGE_KEY = 'detalhe_eventos_flat_cols_v1';
const DEFAULT_FLAT_COLS: DimKey[] = ['canal', 'kit', 'modalidade', 'pelotao', 'produtos', 'tamanho_camiseta'];

// Chaves das preferências no servidor (por conta de usuário)
const HIERARCHY_PREF_KEY = 'detalhe_eventos_hierarchy';
const FLAT_COLS_PREF_KEY = 'detalhe_eventos_flat_cols';

// Valida uma lista de dimensões vinda de fora (localStorage ou servidor)
function sanitizeDims(parsed: unknown): DimKey[] | null {
  if (!Array.isArray(parsed)) return null;
  const valid = [...new Set(parsed.filter((d): d is DimKey => typeof d === 'string' && (ALL_DIMS as string[]).includes(d)))];
  // Exige ao menos um nível além de "Produtos" (que é condicional por evento)
  return valid.some(d => d !== 'produtos') ? valid : null;
}

function loadStoredDims(storageKey: string): DimKey[] | null {
  try {
    const raw = localStorage.getItem(storageKey);
    if (!raw) return null;
    return sanitizeDims(JSON.parse(raw));
  } catch {
    return null;
  }
}

const loadStoredHierarchy = () => loadStoredDims(HIERARCHY_STORAGE_KEY);
const loadStoredFlatCols = () => loadStoredDims(FLAT_COLS_STORAGE_KEY);

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
  delay?: number;
}

const KpiCard: React.FC<KpiCardProps> = ({ label, value, sub, icon, color, dark, delay = 0 }) => (
  <motion.div 
    initial={{ opacity: 0, y: 20 }}
    animate={{ opacity: 1, y: 0 }}
    transition={{ delay, duration: 0.5, ease: "easeOut" }}
    className={`rounded-2xl p-5 flex items-center gap-4 ${dark ? 'bg-slate-900/80 border border-slate-800' : 'bg-white border border-slate-200'} shadow-lg backdrop-blur-xl hover:-translate-y-1 transition-transform duration-300 relative overflow-hidden group`}
  >
    <div className={`absolute top-0 right-0 w-32 h-32 bg-gradient-to-br from-current to-transparent opacity-[0.03] rounded-full blur-3xl group-hover:opacity-[0.08] transition-opacity`} style={{ color: dark ? '#fff' : '#000' }} />
    <div className={`p-3 rounded-xl ${color} shadow-inner`}>{icon}</div>
    <div className="min-w-0 z-10">
      <p className={`text-[11px] font-bold uppercase tracking-wider ${dark ? 'text-slate-400' : 'text-slate-500'}`}>{label}</p>
      <p className={`text-2xl font-black tabular-nums tracking-tight ${dark ? 'text-white' : 'text-slate-900'} mt-0.5`}>{value}</p>
      {sub && <p className={`text-[10px] font-medium ${dark ? 'text-slate-500' : 'text-slate-400'} mt-1`}>{sub}</p>}
    </div>
  </motion.div>
);

// ---------------------------------------------------------------------------
// Badges
// ---------------------------------------------------------------------------

const CanalBadge: React.FC<{ canal: string | null }> = ({ canal }) => {
  const map: Record<string, string> = {
    Site: 'bg-blue-500/10 text-blue-600 dark:text-blue-400 ring-1 ring-blue-500/20',
    'Grupos/B2B': 'bg-purple-500/10 text-purple-600 dark:text-purple-400 ring-1 ring-purple-500/20',
    Cortesia: 'bg-slate-500/10 text-slate-600 dark:text-slate-400 ring-1 ring-slate-500/20',
  };
  const cls = (canal && map[canal]) || 'bg-slate-500/10 text-slate-600 dark:text-slate-400 ring-1 ring-slate-500/20';
  return (
    <span className={`inline-flex items-center px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider rounded-md ${cls}`}>
      {val(canal)}
    </span>
  );
};

const BancoBadge: React.FC<{ banco: string }> = ({ banco }) => {
  const cls =
    banco === 'Ativo'
      ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 ring-1 ring-emerald-500/20'
      : 'bg-orange-500/10 text-orange-600 dark:text-orange-400 ring-1 ring-orange-500/20';
  return (
    <span className={`inline-flex items-center px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider rounded ${cls}`}>
      {banco}
    </span>
  );
};

const SnapshotBadge: React.FC<{
  source?: string | null;
  snapshotUpdatedAt?: string | null;
  dark: boolean;
}> = ({ source, snapshotUpdatedAt, dark }) => {
  if (!source) return null;

  if (source === 'snapshot' && snapshotUpdatedAt) {
    const diff = Date.now() - new Date(snapshotUpdatedAt).getTime();
    const hours = Math.floor(diff / 3600000);
    const mins = Math.floor((diff % 3600000) / 60000);
    const label = hours > 0 ? `há ${hours}h${mins > 0 ? `${mins}m` : ''}` : `há ${mins}m`;
    return (
      <span
        title={`Dados do snapshot noturno. Atualizado ${label}. Clique em "Atualizar" para buscar ao vivo.`}
        className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[10px] font-bold tracking-wide ${
          dark ? 'bg-blue-500/10 text-blue-400 ring-1 ring-blue-500/20' : 'bg-blue-50 text-blue-700 ring-1 ring-blue-200'
        }`}
      >
        <Database className="w-3 h-3" />
        Snapshot · {label}
      </span>
    );
  }

  if (source === 'live') {
    return (
      <span
        title="Dados buscados ao vivo de Ativo e Magento agora."
        className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[10px] font-bold tracking-wide ${
          dark ? 'bg-emerald-500/10 text-emerald-400 ring-1 ring-emerald-500/20' : 'bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200'
        }`}
      >
        <TrendingUp className="w-3 h-3" />
        Ao vivo
      </span>
    );
  }

  return null;
};

// ---------------------------------------------------------------------------
// Tree node types
// ---------------------------------------------------------------------------

interface TreeNode {
  key: string;
  label: string;
  dimKey: string;
  inscritos: number;
  receita_bruta: number;
  receita_liquida: number;
  ticket_medio: number;
  bancos: string[];
  canal?: string | null;
  depth: number;
  children?: TreeNode[];
  bankSplit?: BankSplitNode[];
  hasDivergencia?: boolean;
}

interface BankSplitNode {
  banco: string;
  inscritos: number;
  receita_bruta: number;
  receita_liquida: number;
  ticket_medio: number;
  id_evento: string | null;
  evento: string | null;
  canal: string | null;
  modalidade: string | null;
  produtos: string | null;
}

// ---------------------------------------------------------------------------
// Build tree with leaf-level bank split
// ---------------------------------------------------------------------------

function findBancoRows(
  row: DetalheRow,
  allBancoRows: DetalheBancoRow[],
): DetalheBancoRow[] {
  const DIM_KEYS: (keyof DetalheRow)[] = ['canal', 'kit', 'modalidade', 'pelotao', 'produtos', 'tamanho_camiseta'];
  return allBancoRows.filter(br =>
    DIM_KEYS.every(k => (br[k] ?? null) === (row[k] ?? null))
  );
}

function buildBankSplit(matching: DetalheBancoRow[]): BankSplitNode[] {
  const byBanco = new Map<string, BankSplitNode>();
  for (const r of matching) {
    const banco = r.banco || '?';
    if (!byBanco.has(banco)) {
      byBanco.set(banco, {
        banco,
        inscritos: 0,
        receita_bruta: 0,
        receita_liquida: 0,
        ticket_medio: 0,
        id_evento: r.id_evento ? String(r.id_evento) : null,
        evento: r.evento ?? null,
        canal: r.canal ?? null,
        modalidade: r.modalidade ?? null,
        produtos: r.produtos ?? null,
      });
    }
    const node = byBanco.get(banco)!;
    node.inscritos += r.inscritos || 0;
    node.receita_bruta += r.receita_bruta || 0;
    node.receita_liquida += r.receita_liquida || 0;
  }
  for (const node of byBanco.values()) {
    node.receita_bruta = Math.round(node.receita_bruta * 100) / 100;
    node.receita_liquida = Math.round(node.receita_liquida * 100) / 100;
    node.ticket_medio = node.inscritos > 0
      ? Math.round((node.receita_liquida / node.inscritos) * 100) / 100
      : 0;
  }
  return [...byBanco.values()].sort((a, b) => b.inscritos - a.inscritos);
}

function buildTree(
  rows: DetalheRow[],
  allBancoRows: DetalheBancoRow[],
  hierarchy: DimKey[],
  divergencias: Set<string>,
): TreeNode[] {
  function group(items: DetalheRow[], dims: DimKey[], depth: number, parentKey: string): TreeNode[] {
    if (items.length === 0) return [];
    const [dim, ...rest] = dims;
    const grouped = new Map<string, DetalheRow[]>();

    for (const row of items) {
      const k = row[dim as keyof DetalheRow] as string ?? NULL_LABEL;
      if (!grouped.has(k)) grouped.set(k, []);
      grouped.get(k)!.push(row);
    }

    const nodes: TreeNode[] = [];
    grouped.forEach((groupRows, k) => {
      if (dim === 'produtos' && k === NULL_LABEL && rest.length > 0) {
        const promoted = group(groupRows, rest, depth, parentKey);
        nodes.push(...promoted);
        return;
      }

      const totalIns = groupRows.reduce((s, r) => s + (r.inscritos || 0), 0);
      const totalBruta = groupRows.reduce((s, r) => s + (r.receita_bruta || 0), 0);
      const totalLiq = groupRows.reduce((s, r) => s + (r.receita_liquida || 0), 0);
      const bancos = [...new Set(groupRows.flatMap(r => r.bancos || []))];
      const firstCanal = groupRows[0]?.canal ?? null;

      const isLeaf = rest.length === 0;

      const hasDivergencia = groupRows.some(r => {
        const dk = `${r.canal}|${r.kit}|${r.modalidade}|${r.pelotao}|${r.produtos}|${r.tamanho_camiseta}`;
        return divergencias.has(dk);
      });

      const escapedK = k.replace(/[|:]/g, '_');
      const nodeKey = `${parentKey}|${dim}:${escapedK}`;

      const node: TreeNode = {
        key: nodeKey,
        label: k,
        dimKey: dim,
        inscritos: totalIns,
        receita_bruta: Math.round(totalBruta * 100) / 100,
        receita_liquida: Math.round(totalLiq * 100) / 100,
        ticket_medio: totalIns > 0 ? Math.round((totalLiq / totalIns) * 100) / 100 : 0,
        bancos,
        canal: firstCanal,
        depth,
        hasDivergencia,
      };

      if (!isLeaf) {
        node.children = group(groupRows, rest, depth + 1, nodeKey);
      } else {
        const matchingBancoRows = groupRows.flatMap(r => findBancoRows(r, allBancoRows));
        if (matchingBancoRows.length > 0) {
          node.bankSplit = buildBankSplit(matchingBancoRows);
        }
      }

      nodes.push(node);
    });

    nodes.sort((a, b) => b.inscritos - a.inscritos);
    return nodes;
  }

  return group(rows, hierarchy, 0, 'root');
}

// ---------------------------------------------------------------------------
// TreeRow component
// ---------------------------------------------------------------------------

interface TreeRowProps {
  node: TreeNode;
  dark: boolean;
  expanded: Set<string>;
  bankExpanded: Set<string>;
  onToggle: (key: string) => void;
  onBankToggle: (key: string) => void;
  totalInscritos: number;
}

const TreeRow: React.FC<TreeRowProps> = ({ node, dark, expanded, bankExpanded, onToggle, onBankToggle, totalInscritos }) => {
  const isOpen = expanded.has(node.key);
  const bankKey = `bank-${node.key}`;
  const isBankOpen = bankExpanded.has(bankKey);
  const hasChildren = node.children && node.children.length > 0;
  const hasBankSplit = node.bankSplit && node.bankSplit.length > 0;
  const isExpandable = hasChildren || hasBankSplit;

  const pct = totalInscritos > 0 ? (node.inscritos / totalInscritos) * 100 : 0;
  const depthPad = node.depth * 24;

  const getRowBg = () => {
    if (dark) {
      if (node.depth === 0) return 'bg-slate-800/80';
      if (node.depth === 1) return 'bg-slate-800/50';
      if (node.depth === 2) return 'bg-slate-800/30';
      return 'bg-transparent';
    } else {
      if (node.depth === 0) return 'bg-blue-50/50';
      if (node.depth === 1) return 'bg-slate-50/80';
      if (node.depth === 2) return 'bg-slate-50/40';
      return 'bg-white';
    }
  };

  const handleClick = () => {
    if (hasChildren) onToggle(node.key);
    else if (hasBankSplit) onBankToggle(bankKey);
  };

  return (
    <>
      <tr
        className={`border-b ${dark ? 'border-slate-800/60' : 'border-slate-100'} ${getRowBg()} ${isExpandable ? 'cursor-pointer hover:brightness-95' : ''} transition-colors group`}
        onClick={handleClick}
      >
        <td className="py-2.5 pr-4" style={{ paddingLeft: depthPad + 16 }}>
          <div className="flex items-center gap-2">
            {hasChildren ? (
              <div className={`p-0.5 rounded-md transition-colors ${isOpen ? 'bg-blue-500/10 text-blue-500' : dark ? 'text-slate-500 group-hover:bg-slate-700' : 'text-slate-400 group-hover:bg-slate-100'}`}>
                <motion.div animate={{ rotate: isOpen ? 90 : 0 }} transition={{ duration: 0.2 }}>
                  <ChevronRight className="w-3.5 h-3.5" />
                </motion.div>
              </div>
            ) : hasBankSplit ? (
              <div className={`p-0.5 rounded-md transition-colors ${isBankOpen ? 'bg-emerald-500/10 text-emerald-500' : dark ? 'text-slate-500 group-hover:bg-slate-700' : 'text-slate-400 group-hover:bg-slate-100'}`}>
                <motion.div animate={{ rotate: isBankOpen ? 90 : 0 }} transition={{ duration: 0.2 }}>
                  <ChevronRight className="w-3.5 h-3.5" />
                </motion.div>
              </div>
            ) : (
              <span className="w-4.5 inline-block" />
            )}
            <span className={`text-[13px] ${node.depth === 0 ? 'font-bold' : node.depth === 1 ? 'font-semibold' : 'font-medium'} ${dark ? 'text-slate-200' : 'text-slate-800'} truncate max-w-[280px]`}>
              {node.label}
            </span>
            {node.hasDivergencia && (
              <span title="Divergência detectada" className="flex-shrink-0 inline-flex ml-1 bg-amber-500/10 p-1 rounded-md">
                <AlertTriangle className="w-3 h-3 text-amber-500" />
              </span>
            )}
          </div>
        </td>
        <td className={`py-2.5 px-4 text-right text-[13px] ${dark ? 'text-slate-300' : 'text-slate-700'}`}>
          <div className="flex flex-col items-end gap-1">
            <span className="font-bold tabular-nums">{fmt(node.inscritos)}</span>
            <div className={`w-16 h-1.5 rounded-full overflow-hidden ${dark ? 'bg-slate-800' : 'bg-slate-100'}`}>
              <motion.div 
                initial={{ width: 0 }}
                animate={{ width: `${Math.min(pct, 100)}%` }}
                transition={{ duration: 0.5 }}
                className="h-full bg-blue-500 rounded-full" 
              />
            </div>
          </div>
        </td>
        <td className={`py-2.5 px-3 text-right text-xs font-medium ${dark ? 'text-slate-500' : 'text-slate-400'} tabular-nums`}>
          {pct.toFixed(1)}%
        </td>
        <td className={`py-2.5 px-4 text-right text-[13px] font-medium ${dark ? 'text-slate-400' : 'text-slate-600'} tabular-nums`}>
          {fmtR(node.receita_bruta)}
        </td>
        <td className={`py-2.5 px-4 text-right text-[13px] font-bold ${dark ? 'text-emerald-400' : 'text-emerald-600'} tabular-nums`}>
          {fmtR(node.receita_liquida)}
        </td>
        <td className={`py-2.5 px-4 text-right text-[13px] font-semibold ${dark ? 'text-amber-400' : 'text-amber-600'} tabular-nums`}>
          {fmtR(node.ticket_medio)}
        </td>
      </tr>

      {/* Children (non-leaf) — sibling rows keep the shared column grid aligned */}
      {hasChildren && isOpen && node.children!.map(child => (
        <TreeRow
          key={child.key}
          node={child}
          dark={dark}
          expanded={expanded}
          bankExpanded={bankExpanded}
          onToggle={onToggle}
          onBankToggle={onBankToggle}
          totalInscritos={totalInscritos}
        />
      ))}

      {/* Bank split (leaf expansion) — sibling rows in the same table */}
      {hasBankSplit && isBankOpen && node.bankSplit!.map((bs, i) => (
        <tr
          key={`${bankKey}-${bs.banco}-${i}`}
          className={`border-b border-dashed ${dark ? 'border-slate-800/40 bg-slate-900/40' : 'border-slate-200 bg-blue-50/20'}`}
        >
          <td className="py-2 pr-4" style={{ paddingLeft: depthPad + 40 }}>
            <div className="flex items-center gap-2.5">
              <span className="w-1 h-1 rounded-full bg-slate-400 flex-shrink-0" />
              <BancoBadge banco={bs.banco} />
              {bs.canal && <CanalBadge canal={bs.canal} />}
              {bs.id_evento && (
                <span className={`text-[10px] font-mono ${dark ? 'text-slate-500' : 'text-slate-400'}`}>
                  ID:{bs.id_evento}
                </span>
              )}
              {bs.modalidade && (
                <span className={`text-[10px] font-medium ${dark ? 'text-slate-400' : 'text-slate-500'}`}>
                  {bs.modalidade}
                </span>
              )}
              {bs.produtos && (
                <span className={`text-[10px] ${dark ? 'text-slate-500' : 'text-slate-400'} truncate max-w-[140px]`} title={bs.produtos}>
                  {bs.produtos}
                </span>
              )}
            </div>
          </td>
          <td className={`py-2 px-4 text-right text-xs font-bold ${dark ? 'text-slate-300' : 'text-slate-700'} tabular-nums`}>
            {fmt(bs.inscritos)}
          </td>
          <td className={`py-2 px-3 text-right text-xs font-medium ${dark ? 'text-slate-500' : 'text-slate-400'} tabular-nums`}>
            {totalInscritos > 0 ? ((bs.inscritos / totalInscritos) * 100).toFixed(1) : '0.0'}%
          </td>
          <td className={`py-2 px-4 text-right text-xs font-medium ${dark ? 'text-slate-400' : 'text-slate-600'} tabular-nums`}>
            {fmtR(bs.receita_bruta)}
          </td>
          <td className={`py-2 px-4 text-right text-xs font-bold ${dark ? 'text-emerald-400' : 'text-emerald-600'} tabular-nums`}>
            {fmtR(bs.receita_liquida)}
          </td>
          <td className={`py-2 px-4 text-right text-xs font-bold ${dark ? 'text-amber-400' : 'text-amber-600'} tabular-nums`}>
            {fmtR(bs.ticket_medio)}
          </td>
        </tr>
      ))}
    </>
  );
};

// ---------------------------------------------------------------------------
// Filter state
// ---------------------------------------------------------------------------

interface FilterState {
  canal: string[];
  kit: string[];
  modalidade: string[];
  pelotao: string[];
  produtos: string[];
  tamanho_camiseta: string[];
  search: string;
}

const EMPTY_FILTERS: FilterState = {
  canal: [], kit: [], modalidade: [],
  pelotao: [], produtos: [], tamanho_camiseta: [], search: '',
};

// Valor da linha para uma dimensão, com o mesmo rótulo de nulos da tabela.
const dimValue = (r: DetalheRow, d: DimKey): string => (r[d] as string | null) ?? NULL_LABEL;

// Remove acentos para a busca dentro dos dropdowns de filtro.
const norm = (s: string) => s.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');

// Regra espelhada do mapeamento de kits (KitConfig -> isParticipacaoOuMeia):
// kits de "Participação"/"Meia Inscrição" (custo fixo R$ 10) ficam FORA do
// denominador do share de tamanhos de camiseta.
const isKitParticipacaoOuMeia = (kit: string | null): boolean => {
  const n = norm(kit || '');
  return n.includes('participacao') || n.includes('meia');
};

interface MultiSelectFilterProps {
  label: string;
  values: string[];
  available: Set<string>;
  selected: string[];
  onChange: (next: string[]) => void;
  dark: boolean;
}

// Dropdown multi-seleção com busca interna; opções vêm em cascata dos demais filtros.
const MultiSelectFilter: React.FC<MultiSelectFilterProps> = ({ label, values, available, selected, onChange, dark }) => {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const rootRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: PointerEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false); };
    document.addEventListener('pointerdown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('pointerdown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  const togglePanel = () => {
    if (!open) {
      setQuery('');
      setTimeout(() => searchRef.current?.focus({ preventScroll: true }), 30);
    }
    setOpen(!open);
  };

  const shown = query ? values.filter(v => norm(v).includes(norm(query))) : values;
  const toggleValue = (v: string) =>
    onChange(selected.includes(v) ? selected.filter(s => s !== v) : [...selected, v]);
  const active = selected.length > 0;

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        onClick={togglePanel}
        className={`flex items-center gap-1.5 text-xs font-bold rounded-xl border px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 cursor-pointer transition-shadow ${
          active
            ? dark ? 'bg-blue-900/30 border-blue-500/50 text-blue-300' : 'bg-blue-50 border-blue-200 text-blue-700'
            : dark ? 'bg-slate-900 border-slate-700 text-slate-300' : 'bg-white border-slate-200 text-slate-700'
        }`}
      >
        {label}
        {active && (
          <span className={`px-1.5 py-0.5 rounded-md text-[10px] font-black ${dark ? 'bg-blue-500/20 text-blue-300' : 'bg-blue-500/10 text-blue-600'}`}>
            {selected.length}
          </span>
        )}
        <ChevronDown className={`w-3.5 h-3.5 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>

      {open && (
        <div className={`absolute left-0 top-full mt-2 w-64 rounded-2xl border shadow-2xl z-50 overflow-hidden ${dark ? 'bg-slate-900 border-slate-700' : 'bg-white border-slate-200'}`}>
          <div className={`p-2 border-b ${dark ? 'border-slate-800' : 'border-slate-100'}`}>
            <div className="relative">
              <Search className={`absolute left-2.5 top-2 w-3.5 h-3.5 ${dark ? 'text-slate-500' : 'text-slate-400'}`} />
              <input
                ref={searchRef}
                type="text"
                value={query}
                onChange={e => setQuery(e.target.value)}
                placeholder={`Buscar ${label.toLowerCase()}...`}
                className={`w-full pl-8 pr-2 py-1.5 text-xs font-medium rounded-lg border focus:outline-none focus:ring-2 focus:ring-blue-500 ${dark ? 'bg-slate-800 border-slate-700 text-white placeholder-slate-500' : 'bg-slate-50 border-slate-200 text-slate-900 placeholder-slate-400'}`}
              />
            </div>
          </div>
          <div className="max-h-60 overflow-y-auto py-1">
            {shown.length === 0 && (
              <p className={`px-3 py-3 text-xs font-medium text-center ${dark ? 'text-slate-500' : 'text-slate-400'}`}>Nada encontrado.</p>
            )}
            {shown.map(v => {
              const checked = selected.includes(v);
              const off = !available.has(v);
              return (
                <button
                  key={v}
                  type="button"
                  onClick={() => toggleValue(v)}
                  title={off ? 'Sem registros com os filtros atuais' : undefined}
                  className={`w-full flex items-center gap-2 px-3 py-1.5 text-left text-xs font-medium transition-colors ${
                    dark ? 'hover:bg-slate-800' : 'hover:bg-slate-50'
                  } ${off ? 'opacity-40' : ''} ${checked ? (dark ? 'text-blue-300' : 'text-blue-700') : (dark ? 'text-slate-300' : 'text-slate-700')}`}
                >
                  <span className={`w-4 h-4 rounded-md border flex items-center justify-center shrink-0 ${
                    checked
                      ? 'bg-blue-600 border-blue-600 text-white'
                      : dark ? 'border-slate-600' : 'border-slate-300'
                  }`}>
                    {checked && <Check className="w-3 h-3" />}
                  </span>
                  <span className="truncate">{v}</span>
                </button>
              );
            })}
          </div>
          <div className={`flex items-center justify-between px-3 py-2 border-t text-[11px] font-bold ${dark ? 'border-slate-800 text-slate-500' : 'border-slate-100 text-slate-400'}`}>
            <span>{selected.length} selecionado{selected.length === 1 ? '' : 's'}</span>
            {active && (
              <button type="button" onClick={() => onChange([])} className="text-red-500 hover:underline">
                Limpar
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

const DetalheEventos: React.FC = () => {
  const { isDark: dark } = useTheme();

  const [eventos, setEventos] = useState<DetalheEventoDisponivel[]>([]);
  const [eventoGrupo, setEventoGrupo] = useState<string>('');
  const [payload, setPayload] = useState<DetalheEventoPayload | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadingEventos, setLoadingEventos] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filters, setFilters] = useState<FilterState>(EMPTY_FILTERS);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [bankExpanded, setBankExpanded] = useState<Set<string>>(new Set());
  const [viewMode, setViewMode] = useState<'tree' | 'flat'>('tree');
  // Troca de visão preservando a rolagem: ao substituir a árvore pela tabela
  // (e vice-versa), o "scroll anchoring" do navegador pode empurrar a tela
  // para o meio do conteúdo novo. Guardamos a posição no clique e restauramos
  // antes do paint (useLayoutEffect), mantendo a tela exatamente onde estava.
  const pendingScrollRef = useRef<number | null>(null);
  const switchViewMode = useCallback((mode: 'tree' | 'flat') => {
    pendingScrollRef.current = window.scrollY;
    setViewMode(mode);
  }, []);
  useLayoutEffect(() => {
    if (pendingScrollRef.current !== null) {
      window.scrollTo(0, pendingScrollRef.current);
      pendingScrollRef.current = null;
    }
  }, [viewMode]);
  const [hierarchy, setHierarchy] = useState<DimKey[]>(() => loadStoredHierarchy() ?? DEFAULT_HIERARCHY);
  const [flatCols, setFlatCols] = useState<DimKey[]>(() => loadStoredFlatCols() ?? DEFAULT_FLAT_COLS);
  const [activeTab, setActiveTab] = useState<'consolidado' | 'ativo' | 'magento'>('consolidado');
  const [searchEventos, setSearchEventos] = useState('');
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const comboboxRef = useRef<HTMLDivElement>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);
  const [loadingSecs, setLoadingSecs] = useState(0);
  const [isLiveLoad, setIsLiveLoad] = useState(false);
  const [refreshCooldown, setRefreshCooldown] = useState(0);
  const cooldownRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const [refreshInProgress, setRefreshInProgress] = useState(false);
  const [tamanhoDetalhado, setTamanhoDetalhado] = useState(false);
  const pollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (cooldownRef.current) clearInterval(cooldownRef.current);
      if (pollTimerRef.current) clearTimeout(pollTimerRef.current);
    };
  }, []);

  const startRefreshCooldown = useCallback(() => {
    if (cooldownRef.current) clearInterval(cooldownRef.current);
    setRefreshCooldown(30);
    cooldownRef.current = setInterval(() => {
      setRefreshCooldown(s => {
        if (s <= 1) {
          clearInterval(cooldownRef.current!);
          cooldownRef.current = null;
          return 0;
        }
        return s - 1;
      });
    }, 1000);
  }, []);

  useEffect(() => {
    if (!loading) { setLoadingSecs(0); return; }
    setLoadingSecs(0);
    const t = setInterval(() => setLoadingSecs(s => s + 1), 1000);
    return () => clearInterval(t);
  }, [loading]);

  useEffect(() => {
    setLoadingEventos(true);
    detalheEventosService.listEventos()
      .then(setEventos)
      .catch(e => setError(e?.response?.data?.detail || e.message))
      .finally(() => setLoadingEventos(false));
  }, []);

  const loadDetalhe = useCallback(async (grupo: string, force = false) => {
    if (!grupo) return;
    setLoading(true);
    setIsLiveLoad(force);
    setError(null);
    setExpanded(new Set());
    setBankExpanded(new Set());
    setFilters(EMPTY_FILTERS);

    if (force) startRefreshCooldown();

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 150_000);

    try {
      const data = await detalheEventosService.getDetalhe(grupo, force, controller.signal);
      setPayload(data);
      const inProgress = !!(data as any)?.refresh_in_progress;
      setRefreshInProgress(inProgress);
      if (inProgress) {
        if (pollTimerRef.current) clearTimeout(pollTimerRef.current);
        pollTimerRef.current = setTimeout(() => loadDetalhe(grupo, false), 6000);
      }
    } catch (e: any) {
      const isAbort = e?.name === 'AbortError' || e?.name === 'CanceledError' || e?.code === 'ERR_CANCELED';
      const is429 = e?.response?.status === 429 || e?.response?.status === 202;
      if (isAbort) {
        setError('A consulta demorou mais de 2 minutos e meio e foi cancelada. O servidor pode estar sobrecarregado — tente novamente em alguns instantes.');
      } else if (is429) {
        setRefreshInProgress(true);
        if (pollTimerRef.current) clearTimeout(pollTimerRef.current);
        pollTimerRef.current = setTimeout(() => loadDetalhe(grupo, false), 8000);
      } else {
        setError(e?.response?.data?.detail || e.message || 'Erro ao carregar dados');
      }
    } finally {
      clearTimeout(timeoutId);
      setLoading(false);
      setIsLiveLoad(false);
    }
  }, [startRefreshCooldown]);

  useEffect(() => {
    if (eventoGrupo) loadDetalhe(eventoGrupo);
  }, [eventoGrupo, loadDetalhe]);

  useEffect(() => {
    if (!dropdownOpen) return;
    const handler = (e: MouseEvent) => {
      if (comboboxRef.current && !comboboxRef.current.contains(e.target as Node)) {
        setDropdownOpen(false);
        setSearchEventos('');
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [dropdownOpen]);

  useEffect(() => {
    if (dropdownOpen) setTimeout(() => searchInputRef.current?.focus(), 50);
    else setSearchEventos('');
  }, [dropdownOpen]);

  const handleToggle = useCallback((key: string) => {
    setExpanded(prev => {
      const next = new Set(prev);
      next.has(key) ? next.delete(key) : next.add(key);
      return next;
    });
  }, []);

  const handleBankToggle = useCallback((key: string) => {
    setBankExpanded(prev => {
      const next = new Set(prev);
      next.has(key) ? next.delete(key) : next.add(key);
      return next;
    });
  }, []);

  const tabRows = useMemo<DetalheRow[]>(() => {
    if (!payload) return [];
    return activeTab === 'consolidado'
      ? payload.consolidado
      : activeTab === 'ativo'
      ? payload.por_banco.Ativo
      : payload.por_banco.Magento;
  }, [payload, activeTab]);

  const filteredRows = useMemo<DetalheRow[]>(() => {
    let rows = tabRows;
    for (const dim of ALL_DIMS) {
      const sel = filters[dim];
      if (sel.length > 0) rows = rows.filter(r => sel.includes(dimValue(r, dim)));
    }
    if (filters.search) {
      const q = filters.search.toLowerCase();
      rows = rows.filter(r =>
        [r.kit, r.modalidade, r.canal, r.pelotao, r.produtos, r.tamanho_camiseta]
          .some(v => v?.toLowerCase().includes(q))
      );
    }
    return rows;
  }, [tabRows, filters]);

  const allBancoRows = useMemo<DetalheBancoRow[]>(() => {
    if (!payload) return [];
    const all = [...payload.por_banco.Ativo, ...payload.por_banco.Magento];
    if (filters.canal.length > 0) return all.filter(r => filters.canal.includes(r.canal ?? NULL_LABEL));
    return all;
  }, [payload, filters.canal]);

  const divergenciaKeys = useMemo(() => {
    if (!payload) return new Set<string>();
    return new Set(
      payload.divergencias.map(d =>
        `${d.dimensoes.canal}|${d.dimensoes.kit}|${d.dimensoes.modalidade}|${d.dimensoes.pelotao}|${d.dimensoes.produtos}|${d.dimensoes.tamanho_camiseta}`
      )
    );
  }, [payload]);

  // Opções em cascata: cada dropdown lista apenas valores presentes nas linhas
  // que passam pelos filtros das OUTRAS dimensões (na aba atual). Valores já
  // selecionados permanecem na lista para poderem ser desmarcados, sinalizados
  // como indisponíveis quando a cascata os elimina.
  const opts = useMemo(() => {
    const result = {} as Record<DimKey, { values: string[]; available: Set<string> }>;
    for (const dim of ALL_DIMS) {
      let rows = tabRows;
      for (const other of ALL_DIMS) {
        if (other === dim) continue;
        const sel = filters[other];
        if (sel.length > 0) rows = rows.filter(r => sel.includes(dimValue(r, other)));
      }
      const available = new Set(rows.map(r => dimValue(r, dim)));
      result[dim] = { values: [...new Set([...available, ...filters[dim]])].sort(), available };
    }
    return result;
  }, [tabRows, filters]);

  const hasProdutos = useMemo(
    () => (payload?.consolidado ?? []).some(r => r.produtos != null && r.produtos !== ''),
    [payload]
  );

  // Hierarquia efetiva: preferência do usuário, omitindo "Produtos" quando o
  // evento não tem produtos (mesma regra do padrão antigo). Nunca fica vazia.
  const activeHierarchy = useMemo(() => {
    const eff = hasProdutos ? hierarchy : hierarchy.filter(d => d !== 'produtos');
    if (eff.length > 0) return eff;
    return hasProdutos ? DEFAULT_HIERARCHY : DEFAULT_HIERARCHY.filter(d => d !== 'produtos');
  }, [hierarchy, hasProdutos]);

  const isDefaultHierarchy = sameHierarchy(hierarchy, DEFAULT_HIERARCHY);

  const availableDims = useMemo(
    () => ALL_DIMS.filter(d => !hierarchy.includes(d) && (d !== 'produtos' || hasProdutos)),
    [hierarchy, hasProdutos]
  );

  // Preferências vindas do servidor não devem sobrescrever mudanças que o
  // usuário fez enquanto o fetch estava em andamento.
  const hierarchyTouchedRef = useRef(false);
  const flatColsTouchedRef = useRef(false);

  // Carrega preferências salvas na conta (localStorage já foi usado como
  // valor inicial otimista; o servidor é a fonte da verdade).
  useEffect(() => {
    let cancelled = false;
    userPrefsService.getAll()
      .then(prefs => {
        if (cancelled) return;
        const serverHierarchy = sanitizeDims(prefs[HIERARCHY_PREF_KEY]);
        const serverFlatCols = sanitizeDims(prefs[FLAT_COLS_PREF_KEY]);
        if (!hierarchyTouchedRef.current) {
          if (serverHierarchy) {
            setHierarchy(serverHierarchy);
            try { localStorage.setItem(HIERARCHY_STORAGE_KEY, JSON.stringify(serverHierarchy)); } catch { /* noop */ }
          } else {
            // Sem preferência no servidor: migra a do navegador, se existir
            const local = loadStoredHierarchy();
            if (local && !sameHierarchy(local, DEFAULT_HIERARCHY)) {
              userPrefsService.set(HIERARCHY_PREF_KEY, local).catch(() => { /* melhor esforço */ });
            }
          }
        }
        if (!flatColsTouchedRef.current) {
          if (serverFlatCols) {
            setFlatCols(serverFlatCols);
            try { localStorage.setItem(FLAT_COLS_STORAGE_KEY, JSON.stringify(serverFlatCols)); } catch { /* noop */ }
          } else {
            const local = loadStoredFlatCols();
            if (local && !sameHierarchy(local, DEFAULT_FLAT_COLS)) {
              userPrefsService.set(FLAT_COLS_PREF_KEY, local).catch(() => { /* melhor esforço */ });
            }
          }
        }
      })
      .catch(() => { /* servidor indisponível — segue com localStorage */ });
    return () => { cancelled = true; };
  }, []);

  // Troca de hierarquia invalida as chaves dos nós — reseta expansão junto.
  const applyHierarchy = useCallback((next: DimKey[]) => {
    hierarchyTouchedRef.current = true;
    setHierarchy(next);
    setExpanded(new Set());
    setBankExpanded(new Set());
    const isDefault = sameHierarchy(next, DEFAULT_HIERARCHY);
    try {
      if (isDefault) localStorage.removeItem(HIERARCHY_STORAGE_KEY);
      else localStorage.setItem(HIERARCHY_STORAGE_KEY, JSON.stringify(next));
    } catch { /* armazenamento indisponível — segue só em memória */ }
    // Persiste na conta do usuário (melhor esforço; localStorage é o fallback)
    (isDefault
      ? userPrefsService.remove(HIERARCHY_PREF_KEY)
      : userPrefsService.set(HIERARCHY_PREF_KEY, next)
    ).catch(() => { /* offline/erro — preferência local continua valendo */ });
  }, []);

  const removeDim = useCallback((dim: DimKey) => {
    const next = hierarchy.filter(d => d !== dim);
    // Sempre manter ao menos um nível além de "Produtos" (condicional por evento),
    // para a hierarquia nunca ficar vazia/divergente ao trocar de evento.
    if (!next.some(d => d !== 'produtos')) return;
    applyHierarchy(next);
  }, [hierarchy, applyHierarchy]);

  const addDim = useCallback((dim: DimKey) => {
    if (hierarchy.includes(dim)) return;
    applyHierarchy([...hierarchy, dim]);
  }, [hierarchy, applyHierarchy]);

  // --- Colunas de dimensão da visão plana (mesmo controle de chips da árvore) ---
  const activeFlatCols = useMemo(() => {
    const eff = hasProdutos ? flatCols : flatCols.filter(d => d !== 'produtos');
    if (eff.length > 0) return eff;
    return hasProdutos ? DEFAULT_FLAT_COLS : DEFAULT_FLAT_COLS.filter(d => d !== 'produtos');
  }, [flatCols, hasProdutos]);

  const isDefaultFlatCols = sameHierarchy(flatCols, DEFAULT_FLAT_COLS);

  const availableFlatCols = useMemo(
    () => ALL_DIMS.filter(d => !flatCols.includes(d) && (d !== 'produtos' || hasProdutos)),
    [flatCols, hasProdutos]
  );

  const applyFlatCols = useCallback((next: DimKey[]) => {
    flatColsTouchedRef.current = true;
    setFlatCols(next);
    const isDefault = sameHierarchy(next, DEFAULT_FLAT_COLS);
    try {
      if (isDefault) localStorage.removeItem(FLAT_COLS_STORAGE_KEY);
      else localStorage.setItem(FLAT_COLS_STORAGE_KEY, JSON.stringify(next));
    } catch { /* armazenamento indisponível — segue só em memória */ }
    (isDefault
      ? userPrefsService.remove(FLAT_COLS_PREF_KEY)
      : userPrefsService.set(FLAT_COLS_PREF_KEY, next)
    ).catch(() => { /* offline/erro — preferência local continua valendo */ });
  }, []);

  const removeFlatCol = useCallback((dim: DimKey) => {
    const next = flatCols.filter(d => d !== dim);
    if (!next.some(d => d !== 'produtos')) return;
    applyFlatCols(next);
  }, [flatCols, applyFlatCols]);

  const addFlatCol = useCallback((dim: DimKey) => {
    if (flatCols.includes(dim)) return;
    applyFlatCols([...flatCols, dim]);
  }, [flatCols, applyFlatCols]);

  const tree = useMemo(
    () => buildTree(filteredRows, allBancoRows, activeHierarchy, divergenciaKeys),
    [filteredRows, allBancoRows, activeHierarchy, divergenciaKeys]
  );

  const canalChartData = useMemo(() => {
    if (!payload) return [];
    return Object.entries(payload.totais.por_canal)
      .map(([canal, v]) => ({ canal, inscritos: v.inscritos, receita: Math.round(v.receita_liquida) }))
      .sort((a, b) => b.inscritos - a.inscritos);
  }, [payload]);

  const modalidadeChartData = useMemo(() => {
    if (!payload) return [];
    const map = new Map<string, number>();
    payload.consolidado.forEach(r => {
      const k = r.modalidade || NULL_LABEL;
      map.set(k, (map.get(k) || 0) + r.inscritos);
    });
    return [...map.entries()].map(([name, value]) => ({ name, value }))
      .sort((a, b) => b.value - a.value).slice(0, 12);
  }, [payload]);

  const tamanhoChartData = useMemo(() => {
    if (!payload) return [];
    const map = new Map<string, number>();
    payload.consolidado.forEach(r => {
      const k = r.tamanho_camiseta || NULL_LABEL;
      if (k !== NULL_LABEL) map.set(k, (map.get(k) || 0) + r.inscritos);
    });
    return [...map.entries()].map(([name, value]) => ({ name, value }))
      .sort((a, b) => b.value - a.value);
  }, [payload]);

  const tamanhoChartDataSimple = useMemo(() => {
    if (!payload) return [];
    const map = new Map<string, number>();
    payload.consolidado.forEach(r => {
      const raw = r.tamanho_camiseta || NULL_LABEL;
      if (raw === NULL_LABEL) return;
      const base = raw.includes(' - ') ? raw.split(' - ')[0].trim() : raw;
      map.set(base, (map.get(base) || 0) + r.inscritos);
    });
    return [...map.entries()].map(([name, value]) => ({ name, value }))
      .sort((a, b) => b.value - a.value);
  }, [payload]);

  const tamanhoBreakdownMap = useMemo(() => {
    if (!payload) return new Map<string, { name: string; value: number }[]>();
    const map = new Map<string, Map<string, number>>();
    payload.consolidado.forEach(r => {
      const raw = r.tamanho_camiseta || NULL_LABEL;
      if (raw === NULL_LABEL) return;
      const base = raw.includes(' - ') ? raw.split(' - ')[0].trim() : raw;
      if (!map.has(base)) map.set(base, new Map());
      const inner = map.get(base)!;
      inner.set(raw, (inner.get(raw) || 0) + r.inscritos);
    });
    const result = new Map<string, { name: string; value: number }[]>();
    map.forEach((inner, base) => {
      result.set(base, [...inner.entries()]
        .map(([name, value]) => ({ name, value }))
        .sort((a, b) => b.value - a.value));
    });
    return result;
  }, [payload]);

  // Denominador do share de tamanhos: total geral de inscritos SEM os kits
  // de Participação/Meia Inscrição (mesma regra do mapeamento de kits).
  const tamanhoShareTotal = useMemo(() => {
    if (!payload) return 0;
    return payload.consolidado.reduce(
      (s, r) => s + (isKitParticipacaoOuMeia(r.kit) ? 0 : r.inscritos), 0);
  }, [payload]);

  const totalInscritos = payload?.totais.inscritos ?? 0;
  const activeFiltersCount = ALL_DIMS.filter(d => filters[d].length > 0).length;

  const filteredEventos = useMemo(() =>
    eventos.filter(e =>
      !searchEventos ||
      e.nome_evento.toLowerCase().includes(searchEventos.toLowerCase()) ||
      e.evento_grupo.toLowerCase().includes(searchEventos.toLowerCase())
    ),
    [eventos, searchEventos]
  );

  const selectedEvento = useMemo(
    () => eventos.find(e => e.evento_grupo === eventoGrupo),
    [eventos, eventoGrupo]
  );

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------

  const cardBg = dark ? 'bg-slate-900 border-slate-800' : 'bg-white border-slate-200';
  const textPrimary = dark ? 'text-white' : 'text-slate-900';
  const textSec = dark ? 'text-slate-400' : 'text-slate-500';
  const borderCol = dark ? 'border-slate-800' : 'border-slate-200';

  return (
    <div className={`min-h-screen relative overflow-hidden font-sans ${dark ? 'bg-[#060913]' : 'bg-slate-50'}`}>
      {/* Dynamic Background */}
      <div className="absolute top-0 left-1/4 w-[600px] h-[600px] bg-gradient-to-r from-blue-600/10 to-purple-600/10 rounded-full blur-[120px] pointer-events-none" />
      <div className="absolute bottom-1/4 right-1/4 w-[500px] h-[500px] bg-gradient-to-r from-emerald-600/10 to-teal-600/10 rounded-full blur-[100px] pointer-events-none" />

      <div className="relative p-6 lg:p-8 max-w-[1600px] mx-auto">
        {/* Header */}
        <motion.div 
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          className="mb-8 flex items-center justify-between"
        >
          <div className="flex items-center gap-4">
            <div className="p-3.5 rounded-2xl bg-gradient-to-br from-blue-600 to-indigo-600 shadow-xl shadow-blue-900/20 ring-1 ring-white/10">
              <Table2 className="w-6 h-6 text-white" />
            </div>
            <div>
              <h1 className={`text-3xl font-black tracking-tight ${textPrimary}`}>Painel do evento</h1>
              <p className={`text-[13px] font-medium mt-1 ${textSec}`}>Detalhamento de inscrições por canal, kit, modalidade e mais.</p>
            </div>
          </div>
        </motion.div>

        {/* Event Selector */}
        <motion.div 
          initial={{ opacity: 0, scale: 0.98 }}
          animate={{ opacity: 1, scale: 1 }}
          className={`rounded-3xl border ${cardBg} p-6 mb-8 shadow-sm backdrop-blur-xl relative z-20`}
        >
          <div className="flex flex-col sm:flex-row gap-4 items-start sm:items-end">
            <div className="flex-1 min-w-0" ref={comboboxRef}>
              <label className={`block text-[11px] font-bold uppercase tracking-wider mb-2 ${textSec}`}>
                Selecione o Evento
              </label>
              {loadingEventos ? (
                <div className="h-11 w-full rounded-xl bg-slate-200 dark:bg-slate-800 animate-pulse" />
              ) : (
                <div className="relative">
                  <button
                    type="button"
                    onClick={() => setDropdownOpen(o => !o)}
                    className={`w-full flex items-center justify-between rounded-xl border px-4 py-3 text-sm font-medium text-left focus:outline-none focus:ring-2 focus:ring-blue-500 transition-shadow ${
                      dark ? 'bg-slate-800/50 border-slate-700 text-slate-100 hover:bg-slate-800' : 'bg-slate-50 border-slate-200 text-slate-900 hover:bg-slate-100'
                    }`}
                  >
                    <span className="truncate">
                      {selectedEvento
                        ? `${selectedEvento.nome_evento}${selectedEvento.anos.length > 0 ? ` (${selectedEvento.anos[0]})` : ''} · ${selectedEvento.evento_grupo}`
                        : '— Selecionar evento —'}
                    </span>
                    <ChevronDown className={`ml-2 w-4 h-4 flex-shrink-0 transition-transform duration-300 ${dropdownOpen ? 'rotate-180' : ''} ${textSec}`} />
                  </button>

                  <AnimatePresence>
                    {dropdownOpen && (
                      <motion.div 
                        initial={{ opacity: 0, y: 8, scale: 0.98 }}
                        animate={{ opacity: 1, y: 0, scale: 1 }}
                        exit={{ opacity: 0, y: 4, scale: 0.98 }}
                        transition={{ duration: 0.15 }}
                        className={`absolute z-50 mt-2 w-full rounded-2xl border shadow-2xl overflow-hidden backdrop-blur-xl ${
                          dark ? 'bg-slate-800/90 border-slate-700' : 'bg-white/90 border-slate-200'
                        }`}
                      >
                        <div className={`flex items-center gap-3 px-4 py-3 border-b ${dark ? 'border-slate-700' : 'border-slate-100'}`}>
                          <Search className={`w-4 h-4 flex-shrink-0 ${textSec}`} />
                          <input
                            ref={searchInputRef}
                            type="text"
                            placeholder="Buscar por nome ou ID..."
                            value={searchEventos}
                            onChange={e => setSearchEventos(e.target.value)}
                            className={`flex-1 text-sm bg-transparent outline-none font-medium ${dark ? 'text-white placeholder-slate-500' : 'text-slate-900 placeholder-slate-400'}`}
                          />
                          {searchEventos && (
                            <button onClick={() => setSearchEventos('')} className={`${textSec} hover:text-red-500 transition-colors`}>
                              <X className="w-4 h-4" />
                            </button>
                          )}
                        </div>

                        <div className="max-h-80 overflow-y-auto scrollbar-thin-custom">
                          <button
                            type="button"
                            onClick={() => { setEventoGrupo(''); setDropdownOpen(false); }}
                            className={`w-full text-left px-5 py-3 text-sm font-medium transition-colors ${
                              !eventoGrupo
                                ? 'bg-blue-600 text-white'
                                : dark ? 'text-slate-400 hover:bg-slate-700/50' : 'text-slate-500 hover:bg-slate-50'
                            }`}
                          >
                            — Limpar Seleção —
                          </button>
                          {filteredEventos.length === 0 && (
                            <p className={`px-5 py-4 text-sm ${textSec} text-center`}>Nenhum evento encontrado.</p>
                          )}
                          {filteredEventos.map(e => {
                            const isSelected = e.evento_grupo === eventoGrupo;
                            return (
                              <button
                                key={e.evento_grupo}
                                type="button"
                                onClick={() => { setEventoGrupo(e.evento_grupo); setDropdownOpen(false); }}
                                className={`w-full text-left px-5 py-3 transition-colors border-b last:border-0 ${dark ? 'border-slate-700/50' : 'border-slate-100'} ${
                                  isSelected
                                    ? 'bg-blue-600 text-white'
                                    : dark ? 'hover:bg-slate-700/50' : 'hover:bg-slate-50'
                                }`}
                              >
                                <span className={`block font-bold text-sm truncate ${isSelected ? 'text-white' : dark ? 'text-slate-200' : 'text-slate-800'}`}>
                                  {e.nome_evento}
                                  {e.anos.length > 0 ? ` (${e.anos[0]})` : ''}
                                </span>
                                <span className={`block text-xs font-mono mt-0.5 truncate ${isSelected ? 'text-blue-200' : textSec}`}>
                                  {e.evento_grupo}
                                </span>
                              </button>
                            );
                          })}
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>
              )}
            </div>

            <button
              onClick={() => eventoGrupo && loadDetalhe(eventoGrupo, true)}
              disabled={!eventoGrupo || loading || refreshCooldown > 0}
              className={`flex items-center justify-center gap-2 px-5 py-3 rounded-xl text-sm font-bold tracking-wide transition-all shadow-sm ${
                dark 
                  ? 'bg-blue-600 hover:bg-blue-500 text-white disabled:bg-slate-800 disabled:text-slate-500 disabled:shadow-none' 
                  : 'bg-blue-600 hover:bg-blue-700 text-white disabled:bg-slate-200 disabled:text-slate-400 disabled:shadow-none'
              }`}
            >
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
              {refreshCooldown > 0 ? `Aguarde (${refreshCooldown}s)` : 'Atualizar Dados'}
            </button>
          </div>

          <AnimatePresence>
            {selectedEvento && (
              <motion.div 
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: 'auto' }}
                className={`mt-4 pt-4 border-t ${borderCol} flex flex-wrap gap-4 items-center`}
              >
                {selectedEvento.ativo_ids.length > 0 && (
                  <div className="flex items-center gap-2">
                    <span className="text-[11px] font-bold uppercase tracking-wider text-emerald-600 dark:text-emerald-500">Ativo IDs:</span>
                    <span className={`text-xs font-mono font-medium ${dark ? 'text-slate-300' : 'text-slate-700'}`}>{selectedEvento.ativo_ids.join(', ')}</span>
                  </div>
                )}
                {selectedEvento.magento_ids.length > 0 && (
                  <div className="flex items-center gap-2">
                    <span className="text-[11px] font-bold uppercase tracking-wider text-orange-600 dark:text-orange-500">Magento IDs:</span>
                    <span className={`text-xs font-mono font-medium ${dark ? 'text-slate-300' : 'text-slate-700'}`}>{selectedEvento.magento_ids.join(', ')}</span>
                  </div>
                )}
                {payload && !loading && (
                  <div className="ml-auto">
                    <SnapshotBadge source={payload.source} snapshotUpdatedAt={payload.snapshot_updated_at} dark={dark} />
                  </div>
                )}
              </motion.div>
            )}
          </AnimatePresence>
        </motion.div>

        <AnimatePresence>
          {error && (
            <motion.div 
              initial={{ opacity: 0, y: -10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              className={`mb-8 flex items-start gap-3 rounded-2xl border p-4 shadow-lg ${dark ? 'bg-red-500/10 border-red-500/20 text-red-400' : 'bg-red-50 border-red-200 text-red-700'}`}
            >
              <div className="p-2 bg-red-500/20 rounded-lg">
                <AlertTriangle className="w-5 h-5 flex-shrink-0" />
              </div>
              <div>
                <p className="font-bold text-sm">Erro ao carregar dados</p>
                <p className="text-sm mt-1 opacity-90">{error}</p>
              </div>
            </motion.div>
          )}

          {refreshInProgress && !loading && (
            <motion.div 
              initial={{ opacity: 0, y: -10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              className={`mb-8 flex items-center gap-3 rounded-2xl p-4 border shadow-lg ${
                dark ? 'bg-amber-500/10 border-amber-500/20 text-amber-400' : 'bg-amber-50 border-amber-200 text-amber-700'
              }`}
            >
              <div className="p-2 bg-amber-500/20 rounded-lg">
                <RefreshCw className="w-5 h-5 animate-spin flex-shrink-0" />
              </div>
              <span className="text-sm font-bold tracking-wide">Atualização em andamento — dados mais recentes chegarão em instantes.</span>
            </motion.div>
          )}
        </AnimatePresence>

        {loading && (
          <motion.div 
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="space-y-6"
          >
            <div className={`rounded-2xl border ${
              isLiveLoad
                ? dark ? 'border-amber-500/30 bg-amber-500/10' : 'border-amber-200 bg-amber-50'
                : dark ? 'border-blue-500/30 bg-blue-500/10' : 'border-blue-200 bg-blue-50'
            } p-6 flex items-center gap-5 shadow-lg`}>
              <div className={`p-3 rounded-xl ${isLiveLoad ? 'bg-amber-500/20' : 'bg-blue-500/20'}`}>
                <RefreshCw className={`w-6 h-6 animate-spin flex-shrink-0 ${isLiveLoad ? 'text-amber-500' : 'text-blue-500'}`} />
              </div>
              <div className="min-w-0">
                <p className={`text-base font-bold tracking-wide ${
                  isLiveLoad
                    ? dark ? 'text-amber-400' : 'text-amber-700'
                    : dark ? 'text-blue-400' : 'text-blue-700'
                }`}>
                  {isLiveLoad
                    ? 'Buscando dados ao vivo… (pode levar ~2 min)'
                    : 'Carregando dados do snapshot…'}
                </p>
                <p className={`text-sm mt-1 font-medium ${
                  isLiveLoad
                    ? dark ? 'text-amber-500/70' : 'text-amber-600/80'
                    : dark ? 'text-blue-400/70' : 'text-blue-600/80'
                }`}>
                  {isLiveLoad
                    ? <>Consulta direta aos bancos externos (Ativo via SSH, Magento direto).{loadingSecs > 0 && <span className="ml-2 font-mono font-bold">{loadingSecs}s / 150s</span>}</>
                    : 'Lendo snapshot consolidado — geralmente rápido.'}
                </p>
              </div>
            </div>
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-6">
              {[...Array(4)].map((_, i) => (
                <div key={i} className={`h-28 rounded-2xl animate-pulse ${dark ? 'bg-slate-800' : 'bg-slate-200'}`} />
              ))}
            </div>
            <div className={`h-[400px] rounded-3xl animate-pulse ${dark ? 'bg-slate-800' : 'bg-slate-200'}`} />
          </motion.div>
        )}

        {!loading && !payload && !error && (
          <motion.div 
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className={`rounded-3xl border ${cardBg} p-16 text-center shadow-sm flex flex-col items-center justify-center min-h-[400px]`}
          >
            <div className={`p-6 rounded-full mb-6 ${dark ? 'bg-slate-800/50' : 'bg-slate-100'}`}>
              <Table2 className={`w-12 h-12 ${dark ? 'text-slate-600' : 'text-slate-400'}`} />
            </div>
            <p className={`text-xl font-black tracking-tight ${textPrimary}`}>Nenhum evento selecionado</p>
            <p className={`text-sm font-medium mt-2 max-w-sm ${textSec}`}>Selecione um evento acima para visualizar o detalhamento completo de inscrições e receita.</p>
          </motion.div>
        )}

        {!loading && payload && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="space-y-8"
          >
            {Object.keys(payload.erros).length > 0 && (
              <div className={`flex items-start gap-3 rounded-2xl border p-4 shadow-sm ${dark ? 'bg-amber-500/10 border-amber-500/20 text-amber-400' : 'bg-amber-50 border-amber-200 text-amber-700'}`}>
                <AlertTriangle className="w-5 h-5 flex-shrink-0 mt-0.5" />
                <div>
                  <p className="text-sm font-bold">Atenção: erros ao buscar dados de alguns bancos</p>
                  {Object.entries(payload.erros).map(([banco, msg]) => (
                    <p key={banco} className="text-xs font-medium mt-1 opacity-90">{banco}: {msg}</p>
                  ))}
                </div>
              </div>
            )}

            {payload.divergencias.length > 0 && (
              <div className={`flex items-start gap-3 rounded-2xl border p-4 shadow-sm ${dark ? 'bg-red-500/10 border-red-500/20 text-red-400' : 'bg-red-50 border-red-200 text-red-700'}`}>
                <AlertTriangle className="w-5 h-5 flex-shrink-0 mt-0.5" />
                <div>
                  <p className="text-sm font-bold">{payload.divergencias.length} divergência(s) detectada(s)</p>
                  <p className="text-xs font-medium mt-1 opacity-90">A soma dos bancos difere do total consolidado em algumas combinações. Indicado por <AlertTriangle className="inline w-3 h-3 mx-1" /> na árvore.</p>
                </div>
              </div>
            )}

            {/* KPI Cards */}
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 lg:gap-6">
              <KpiCard delay={0.0} label="Total Inscritos" value={fmt(payload.totais.inscritos)} icon={<Users className="w-5 h-5 text-blue-500" />} color="bg-blue-500/20" dark={dark} />
              <KpiCard delay={0.1} label="Receita Bruta" value={fmtR(payload.totais.receita_bruta)} icon={<DollarSign className="w-5 h-5 text-emerald-500" />} color="bg-emerald-500/20" dark={dark} />
              <KpiCard delay={0.2} label="Receita Líquida" value={fmtR(payload.totais.receita_liquida)} icon={<TrendingUp className="w-5 h-5 text-indigo-500" />} color="bg-indigo-500/20" dark={dark} />
              <KpiCard delay={0.3} label="Ticket Médio" value={fmtR(payload.totais.ticket_medio)} sub="Por inscrito (rec. líquida)" icon={<Tag className="w-5 h-5 text-amber-500" />} color="bg-amber-500/20" dark={dark} />
            </div>

            {/* Canal pills */}
            <div className="flex flex-wrap gap-3 items-center">
              <span className={`text-[11px] font-bold uppercase tracking-wider ${textSec}`}>Filtrar por Canal:</span>
              <div className="flex flex-wrap gap-2">
                {Object.entries(payload.totais.por_canal).map(([canal, stats]) => (
                  <button
                    key={canal}
                    onClick={() => setFilters(f => ({ ...f, canal: f.canal.includes(canal) ? f.canal.filter(c => c !== canal) : [...f.canal, canal] }))}
                    className={`flex items-center gap-2.5 px-4 py-2 rounded-xl text-xs font-bold border transition-all duration-300 ${
                      filters.canal.includes(canal) 
                        ? 'ring-2 ring-offset-2 ring-blue-500 shadow-md scale-105' 
                        : 'hover:scale-105'
                    } ${dark ? 'bg-slate-800 border-slate-700 text-slate-200 hover:bg-slate-700' : 'bg-white border-slate-200 text-slate-700 hover:bg-slate-50 shadow-sm'}`}
                  >
                    <span className="w-2.5 h-2.5 rounded-full shadow-inner" style={{ background: CANAL_COLORS[canal] || '#6b7280' }} />
                    <span>{canal}</span>
                    <span className={`px-1.5 py-0.5 rounded-md text-[10px] ${dark ? 'bg-slate-900 text-slate-400' : 'bg-slate-100 text-slate-500'}`}>{fmt(stats.inscritos)}</span>
                  </button>
                ))}
                {filters.canal.length > 0 && (
                  <button 
                    onClick={() => setFilters(f => ({ ...f, canal: [] }))} 
                    className="flex items-center gap-1.5 px-3 py-2 rounded-xl text-xs font-bold text-red-500 hover:bg-red-500/10 transition-colors"
                  >
                    <X className="w-3.5 h-3.5" /> Limpar
                  </button>
                )}
              </div>
            </div>

            {/* Charts Grid */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              <div className={`rounded-3xl border ${cardBg} p-6 shadow-sm backdrop-blur-xl`}>
                <p className={`text-[11px] font-bold uppercase tracking-wider mb-6 ${textSec}`}>Inscritos por Canal</p>
                <div className="h-[180px]">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={canalChartData} barSize={40} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                      <XAxis dataKey="canal" tick={{ fontSize: 11, fill: dark ? '#94a3b8' : '#64748b', fontWeight: 600 }} axisLine={false} tickLine={false} />
                      <YAxis tick={{ fontSize: 11, fill: dark ? '#94a3b8' : '#64748b' }} axisLine={false} tickLine={false} />
                      <Tooltip formatter={(v: number | undefined) => [fmt(v ?? 0), 'Inscritos']} cursor={{ fill: dark ? '#334155' : '#f1f5f9' }} contentStyle={{ background: dark ? '#1e293b' : '#fff', border: 'none', borderRadius: 12, fontSize: 12, fontWeight: 600, boxShadow: '0 10px 25px -5px rgba(0, 0, 0, 0.1), 0 8px 10px -6px rgba(0, 0, 0, 0.1)' }} />
                      <Bar dataKey="inscritos" radius={[6, 6, 0, 0]}>
                        {canalChartData.map((entry, i) => <Cell key={i} fill={CANAL_COLORS[entry.canal] || CHART_COLORS[i % CHART_COLORS.length]} />)}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>

              <div className={`rounded-3xl border ${cardBg} p-6 shadow-sm backdrop-blur-xl`}>
                <p className={`text-[11px] font-bold uppercase tracking-wider mb-6 ${textSec}`}>Top Modalidades</p>
                <div className="h-[180px]">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={modalidadeChartData.slice(0, 8)} layout="vertical" barSize={16} margin={{ top: 0, right: 20, left: 0, bottom: 0 }}>
                      <XAxis type="number" hide />
                      <YAxis type="category" dataKey="name" width={90} tick={{ fontSize: 10, fill: dark ? '#94a3b8' : '#64748b', fontWeight: 600 }} axisLine={false} tickLine={false} />
                      <Tooltip formatter={(v: number | undefined) => [fmt(v ?? 0), 'Inscritos']} cursor={{ fill: dark ? '#334155' : '#f1f5f9' }} contentStyle={{ background: dark ? '#1e293b' : '#fff', border: 'none', borderRadius: 12, fontSize: 12, fontWeight: 600, boxShadow: '0 10px 25px -5px rgba(0, 0, 0, 0.1)' }} />
                      <Bar dataKey="value" radius={[0, 6, 6, 0]}>
                        {modalidadeChartData.slice(0, 8).map((_, i) => <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />)}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>

              <div className={`rounded-3xl border ${cardBg} p-6 shadow-sm backdrop-blur-xl flex flex-col`}>
                <div className="flex items-center justify-between mb-4">
                  <p className={`text-[11px] font-bold uppercase tracking-wider ${textSec}`}>Tamanhos de Camiseta</p>
                  {tamanhoChartData.length > 0 && (
                    <button
                      onClick={() => setTamanhoDetalhado(v => !v)}
                      className={`text-[10px] px-3 py-1 font-bold uppercase tracking-wider rounded-lg transition-colors ${
                        tamanhoDetalhado
                          ? dark ? 'bg-blue-600 text-white' : 'bg-blue-600 text-white shadow-md'
                          : dark ? 'bg-slate-800 text-slate-300 hover:bg-slate-700' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                      }`}
                    >
                      {tamanhoDetalhado ? 'Simplificado' : 'Ver Detalhes'}
                    </button>
                  )}
                </div>
                <div className="flex-1 min-h-0 relative">
                  {tamanhoChartData.length > 0 ? (
                    tamanhoDetalhado ? (
                      <div className="absolute inset-0 overflow-y-auto scrollbar-thin-custom pr-2">
                        <table className="w-full text-[11px] font-medium">
                          <thead className="sticky top-0 z-10 backdrop-blur-md pb-2">
                            <tr className={`${dark ? 'text-slate-400 bg-slate-900/80' : 'text-slate-500 bg-white/80'} uppercase tracking-wider`}>
                              <th className="text-left py-2 font-bold pr-2">Tamanho</th>
                              <th className="text-right py-2 font-bold pr-3">Qtd</th>
                              <th className="text-right py-2 font-bold w-12">%</th>
                            </tr>
                          </thead>
                          <tbody>
                            {tamanhoChartData.map((row, i) => {
                              const pct = tamanhoShareTotal > 0 ? (row.value / tamanhoShareTotal) * 100 : 0;
                              return (
                                <tr key={row.name} className={`border-b last:border-0 ${dark ? 'border-slate-800/50' : 'border-slate-100'}`}>
                                  <td className="py-2 pr-2">
                                    <div className="flex items-center gap-2">
                                      <span style={{ width: 8, height: 8, borderRadius: 2, flexShrink: 0, background: CHART_COLORS[i % CHART_COLORS.length] }} />
                                      <span className={`${dark ? 'text-slate-200' : 'text-slate-700'} truncate font-semibold`} style={{ maxWidth: 120 }}>{row.name}</span>
                                    </div>
                                  </td>
                                  <td className={`py-2 pr-3 text-right tabular-nums font-bold ${dark ? 'text-slate-300' : 'text-slate-600'}`}>{fmt(row.value)}</td>
                                  <td className="py-2 text-right w-12">
                                    <span className={`tabular-nums font-bold ${dark ? 'text-slate-400' : 'text-slate-500'}`}>{pct.toFixed(1)}%</span>
                                  </td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                    ) : (
                      <div className="absolute inset-0">
                        <ResponsiveContainer width="100%" height="100%">
                          <PieChart margin={{ top: 0, right: 0, bottom: 0, left: 0 }}>
                            <Pie
                              data={tamanhoChartDataSimple}
                              dataKey="value"
                              nameKey="name"
                              cx="50%"
                              cy="50%"
                              outerRadius={65}
                              innerRadius={40}
                              stroke="none"
                            >
                              {tamanhoChartDataSimple.map((_, i) => (
                                <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />
                              ))}
                            </Pie>
                            <Tooltip
                              content={({ active, payload: tp }) => {
                                if (!active || !tp?.length) return null;
                                const entry = tp[0];
                                const baseName = entry.name as string;
                                const total = entry.value as number;
                                const variants = tamanhoBreakdownMap.get(baseName);
                                const hasVariants = variants && variants.length > 1;
                                return (
                                  <div className={`p-3 rounded-xl shadow-xl ${dark ? 'bg-slate-800 text-white' : 'bg-white text-slate-900'} border ${dark ? 'border-slate-700' : 'border-slate-100'} text-xs min-w-[160px]`}>
                                    <p className="font-bold border-b pb-2 mb-2 border-current border-opacity-10">
                                      {baseName} — {fmt(total)}{tamanhoShareTotal > 0 && ` (${((total / tamanhoShareTotal) * 100).toFixed(1)}%)`}
                                    </p>
                                    {hasVariants && variants!.map(v => {
                                      const pct = tamanhoShareTotal > 0 ? ((v.value / tamanhoShareTotal) * 100).toFixed(1) : '0';
                                      const label = v.name === baseName ? `${baseName} (único)` : v.name;
                                      return (
                                        <div key={v.name} className={`flex justify-between gap-3 mt-1.5 font-medium ${dark ? 'text-slate-300' : 'text-slate-600'}`}>
                                          <span className="truncate max-w-[120px]">{label}</span>
                                          <span className="flex-shrink-0">{fmt(v.value)} ({pct}%)</span>
                                        </div>
                                      );
                                    })}
                                  </div>
                                );
                              }}
                            />
                            <Legend iconSize={8} iconType="circle" wrapperStyle={{ fontSize: 11, fontWeight: 600, paddingTop: 10 }} />
                          </PieChart>
                        </ResponsiveContainer>
                      </div>
                    )
                  ) : (
                    <div className={`absolute inset-0 flex items-center justify-center text-sm font-medium ${textSec}`}>Sem dados de tamanho</div>
                  )}
                </div>
              </div>
            </div>

            {/* Main Table Area */}
            <div className={`rounded-3xl border ${cardBg} shadow-xl flex flex-col backdrop-blur-xl`}>
              
              {/* Filter Toolbar inside table container for cohesion */}
              <div className={`p-4 border-b rounded-t-3xl ${borderCol} ${dark ? 'bg-slate-800/50' : 'bg-slate-50/50'}`}>
                <div className="flex flex-wrap gap-3 items-center">
                  <div className="relative">
                    <Search className={`absolute left-3 top-2.5 w-4 h-4 ${textSec}`} />
                    <input
                      type="text"
                      placeholder="Buscar na tabela..."
                      value={filters.search}
                      onChange={e => setFilters(f => ({ ...f, search: e.target.value }))}
                      className={`pl-9 pr-4 py-2 text-sm font-medium rounded-xl border focus:outline-none focus:ring-2 focus:ring-blue-500 w-[200px] transition-shadow ${
                        dark ? 'bg-slate-900 border-slate-700 text-white placeholder-slate-500' : 'bg-white border-slate-200 text-slate-900 placeholder-slate-400'
                      }`}
                    />
                  </div>
                  
                  <div className={`w-px h-6 ${dark ? 'bg-slate-700' : 'bg-slate-200'} mx-1`} />
                  
                  <div className="flex flex-wrap gap-2">
                    {(['kit', 'modalidade', 'pelotao', 'produtos', 'tamanho_camiseta'] as const)
                      .filter(dim => dim !== 'produtos' || hasProdutos)
                      .map(dim => (
                        <MultiSelectFilter
                          key={dim}
                          label={DIM_LABELS[dim]}
                          values={opts[dim]?.values ?? []}
                          available={opts[dim]?.available ?? new Set<string>()}
                          selected={filters[dim]}
                          onChange={next => setFilters(f => ({ ...f, [dim]: next }))}
                          dark={dark}
                        />
                      ))}
                  </div>

                  {(activeFiltersCount > 0 || filters.search) && (
                    <button onClick={() => setFilters(EMPTY_FILTERS)} className="flex items-center gap-1.5 px-3 py-2 text-xs font-bold text-red-500 hover:bg-red-500/10 rounded-xl transition-colors ml-auto">
                      <X className="w-4 h-4" /> Limpar Filtros
                    </button>
                  )}
                </div>
              </div>

              {/* Tabs + view toggle */}
              <div className={`flex items-center justify-between px-5 py-3 border-b ${borderCol} ${dark ? 'bg-slate-900/80' : 'bg-white'}`}>
                <div className="flex gap-2">
                  {(['consolidado', 'ativo', 'magento'] as const).map(tab => (
                    <button
                      key={tab}
                      onClick={() => { setActiveTab(tab); setExpanded(new Set()); setBankExpanded(new Set()); }}
                      className={`flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-bold tracking-wide transition-all ${
                        activeTab === tab 
                          ? 'bg-slate-800 text-white shadow-md dark:bg-blue-600' 
                          : dark ? 'text-slate-400 hover:bg-slate-800 hover:text-slate-200' : 'text-slate-500 hover:bg-slate-100 hover:text-slate-700'
                      }`}
                    >
                      {tab === 'consolidado' && <Layers className="w-4 h-4" />}
                      {tab !== 'consolidado' && <Database className="w-4 h-4" />}
                      {tab === 'consolidado' ? 'Consolidado' : tab === 'ativo' ? 'Ativo' : 'Magento'}
                    </button>
                  ))}
                </div>
                <div className="flex items-center gap-2 bg-slate-100 dark:bg-slate-800 p-1 rounded-xl">
                  <button
                    onClick={() => switchViewMode('tree')}
                    className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition-colors ${viewMode === 'tree' ? 'bg-white dark:bg-slate-700 text-blue-600 dark:text-blue-400 shadow-sm' : 'text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200'}`}
                    title="Visão hierárquica"
                  >
                    <Layers className="w-3.5 h-3.5" /> Árvore
                  </button>
                  <button
                    onClick={() => switchViewMode('flat')}
                    className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition-colors ${viewMode === 'flat' ? 'bg-white dark:bg-slate-700 text-blue-600 dark:text-blue-400 shadow-sm' : 'text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200'}`}
                    title="Visão em tabela"
                  >
                    <Table2 className="w-3.5 h-3.5" /> Tabela
                  </button>
                </div>
              </div>

              {/* Granularidade da árvore: níveis de agrupamento configuráveis */}
              {viewMode === 'tree' && (
                <div className={`flex flex-wrap items-center gap-2 px-5 py-3 border-b ${borderCol} ${dark ? 'bg-slate-900/60' : 'bg-slate-50/80'}`}>
                  <span className={`flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider ${textSec}`}>
                    <Layers className="w-3.5 h-3.5" /> Agrupar por
                  </span>
                  <Reorder.Group
                    as="div"
                    axis="x"
                    values={hierarchy}
                    onReorder={applyHierarchy}
                    className="flex flex-wrap items-center gap-1.5"
                  >
                    {hierarchy.map(dim => {
                      const inactive = dim === 'produtos' && !hasProdutos;
                      const pos = activeHierarchy.indexOf(dim);
                      // X escondido quando é o único nível além de "Produtos" (mesma regra do removeDim)
                      const isLastActive = dim !== 'produtos' && hierarchy.filter(d => d !== 'produtos').length <= 1;
                      return (
                        <Reorder.Item
                          key={dim}
                          value={dim}
                          as="div"
                          title={inactive ? 'Evento sem produtos — nível ignorado' : 'Arraste para reordenar'}
                          className={`flex items-center gap-1 pl-1.5 pr-1 py-1 rounded-xl border select-none ${
                            inactive
                              ? `border-dashed opacity-50 ${dark ? 'border-slate-700 bg-slate-900 text-slate-400' : 'border-slate-300 bg-slate-50 text-slate-400'}`
                              : `cursor-grab active:cursor-grabbing ${dark ? 'border-slate-700 bg-slate-900 text-slate-200' : 'border-slate-200 bg-white text-slate-700 shadow-sm'}`
                          }`}
                        >
                          <GripVertical className={`w-3 h-3 ${dark ? 'text-slate-600' : 'text-slate-300'}`} />
                          <span className={`w-4 h-4 rounded-full text-[10px] font-black flex items-center justify-center ${dark ? 'bg-blue-500/20 text-blue-400' : 'bg-blue-500/10 text-blue-600'}`}>
                            {inactive ? '–' : pos + 1}
                          </span>
                          <span className="text-xs font-bold whitespace-nowrap">{DIM_LABELS[dim]}</span>
                          {!isLastActive && (
                            <button
                              onClick={() => removeDim(dim)}
                              onPointerDown={e => e.stopPropagation()}
                              title="Remover nível"
                              className={`p-0.5 rounded-md transition-colors ${dark ? 'text-slate-500 hover:text-red-400 hover:bg-red-500/10' : 'text-slate-400 hover:text-red-500 hover:bg-red-500/10'}`}
                            >
                              <X className="w-3 h-3" />
                            </button>
                          )}
                        </Reorder.Item>
                      );
                    })}
                  </Reorder.Group>
                  {availableDims.length > 0 && (
                    <select
                      value=""
                      onChange={e => { if (e.target.value) addDim(e.target.value as DimKey); }}
                      title="Adicionar nível de agrupamento"
                      className={`text-xs font-bold rounded-xl border px-2.5 py-1.5 appearance-none focus:outline-none focus:ring-2 focus:ring-blue-500 cursor-pointer ${dark ? 'bg-slate-900 border-slate-700 text-slate-400' : 'bg-white border-slate-200 text-slate-500'}`}
                    >
                      <option value="">+ Nível</option>
                      {availableDims.map(d => <option key={d} value={d}>{DIM_LABELS[d]}</option>)}
                    </select>
                  )}
                  {!isDefaultHierarchy && (
                    <button
                      onClick={() => applyHierarchy(DEFAULT_HIERARCHY)}
                      className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold text-blue-500 hover:bg-blue-500/10 transition-colors ml-auto"
                      title="Voltar ao agrupamento padrão"
                    >
                      <RotateCcw className="w-3.5 h-3.5" /> Padrão
                    </button>
                  )}
                </div>
              )}

              {/* Colunas da visão plana: dimensões visíveis configuráveis */}
              {viewMode === 'flat' && (
                <div className={`flex flex-wrap items-center gap-2 px-5 py-3 border-b ${borderCol} ${dark ? 'bg-slate-900/60' : 'bg-slate-50/80'}`}>
                  <span className={`flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider ${textSec}`}>
                    <Table2 className="w-3.5 h-3.5" /> Colunas
                  </span>
                  <Reorder.Group
                    as="div"
                    axis="x"
                    values={flatCols}
                    onReorder={applyFlatCols}
                    className="flex flex-wrap items-center gap-1.5"
                  >
                    {flatCols.map(dim => {
                      const inactive = dim === 'produtos' && !hasProdutos;
                      const pos = activeFlatCols.indexOf(dim);
                      // X escondido quando é a única coluna além de "Produtos" (mesma regra do removeFlatCol)
                      const isLastActive = dim !== 'produtos' && flatCols.filter(d => d !== 'produtos').length <= 1;
                      return (
                        <Reorder.Item
                          key={dim}
                          value={dim}
                          as="div"
                          title={inactive ? 'Evento sem produtos — coluna ignorada' : 'Arraste para reordenar'}
                          className={`flex items-center gap-1 pl-1.5 pr-1 py-1 rounded-xl border select-none ${
                            inactive
                              ? `border-dashed opacity-50 ${dark ? 'border-slate-700 bg-slate-900 text-slate-400' : 'border-slate-300 bg-slate-50 text-slate-400'}`
                              : `cursor-grab active:cursor-grabbing ${dark ? 'border-slate-700 bg-slate-900 text-slate-200' : 'border-slate-200 bg-white text-slate-700 shadow-sm'}`
                          }`}
                        >
                          <GripVertical className={`w-3 h-3 ${dark ? 'text-slate-600' : 'text-slate-300'}`} />
                          <span className={`w-4 h-4 rounded-full text-[10px] font-black flex items-center justify-center ${dark ? 'bg-blue-500/20 text-blue-400' : 'bg-blue-500/10 text-blue-600'}`}>
                            {inactive ? '–' : pos + 1}
                          </span>
                          <span className="text-xs font-bold whitespace-nowrap">{DIM_LABELS[dim]}</span>
                          {!isLastActive && (
                            <button
                              onClick={() => removeFlatCol(dim)}
                              onPointerDown={e => e.stopPropagation()}
                              title="Remover coluna"
                              className={`p-0.5 rounded-md transition-colors ${dark ? 'text-slate-500 hover:text-red-400 hover:bg-red-500/10' : 'text-slate-400 hover:text-red-500 hover:bg-red-500/10'}`}
                            >
                              <X className="w-3 h-3" />
                            </button>
                          )}
                        </Reorder.Item>
                      );
                    })}
                  </Reorder.Group>
                  {availableFlatCols.length > 0 && (
                    <select
                      value=""
                      onChange={e => { if (e.target.value) addFlatCol(e.target.value as DimKey); }}
                      title="Adicionar coluna"
                      className={`text-xs font-bold rounded-xl border px-2.5 py-1.5 appearance-none focus:outline-none focus:ring-2 focus:ring-blue-500 cursor-pointer ${dark ? 'bg-slate-900 border-slate-700 text-slate-400' : 'bg-white border-slate-200 text-slate-500'}`}
                    >
                      <option value="">+ Coluna</option>
                      {availableFlatCols.map(d => <option key={d} value={d}>{DIM_LABELS[d]}</option>)}
                    </select>
                  )}
                  {!isDefaultFlatCols && (
                    <button
                      onClick={() => applyFlatCols(DEFAULT_FLAT_COLS)}
                      className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold text-blue-500 hover:bg-blue-500/10 transition-colors ml-auto"
                      title="Voltar às colunas padrão"
                    >
                      <RotateCcw className="w-3.5 h-3.5" /> Padrão
                    </button>
                  )}
                </div>
              )}

              {filteredRows.length === 0 ? (
                <div className="py-20 text-center flex flex-col items-center">
                  <Search className={`w-10 h-10 mb-4 ${dark ? 'text-slate-700' : 'text-slate-300'}`} />
                  <p className={`text-sm font-bold ${textSec}`}>Nenhum dado com os filtros atuais.</p>
                  <button onClick={() => setFilters(EMPTY_FILTERS)} className="mt-4 text-sm font-bold text-blue-500 hover:underline">Limpar filtros</button>
                </div>
              ) : viewMode === 'tree' ? (
                <div className="overflow-x-auto rounded-b-3xl">
                  {viewMode === 'tree' && (
                    <div className={`px-5 py-2 flex justify-end gap-3 border-b ${borderCol} ${dark ? 'bg-slate-900/50' : 'bg-slate-50/50'}`}>
                      <button
                        onClick={() => {
                          const keys = new Set<string>();
                          const collect = (nodes: TreeNode[]) => nodes.forEach(n => {
                            if (n.children) { keys.add(n.key); collect(n.children); }
                          });
                          collect(tree);
                          setExpanded(keys);
                        }}
                        className={`text-[11px] font-bold uppercase tracking-wider px-3 py-1.5 rounded-lg transition-colors ${dark ? 'text-blue-400 hover:bg-blue-500/10' : 'text-blue-600 hover:bg-blue-50'}`}
                      >
                        Expandir tudo
                      </button>
                      <button
                        onClick={() => { setExpanded(new Set()); setBankExpanded(new Set()); }}
                        className={`text-[11px] font-bold uppercase tracking-wider px-3 py-1.5 rounded-lg transition-colors ${dark ? 'text-slate-400 hover:bg-slate-800' : 'text-slate-500 hover:bg-slate-200'}`}
                      >
                        Colapsar tudo
                      </button>
                    </div>
                  )}
                  <table className="w-full min-w-[800px] text-sm">
                    <thead>
                      <tr className={`text-left text-[11px] font-bold uppercase tracking-wider border-b ${borderCol} ${dark ? 'bg-slate-900 text-slate-400' : 'bg-slate-50 text-slate-500'}`}>
                        <th className="py-4 px-5">
                          <div className="flex items-center gap-1.5">
                            Dimensão
                            <span className="relative group cursor-default">
                              <Info className="w-3.5 h-3.5 text-slate-400 hover:text-blue-500 transition-colors" />
                              <span className={`pointer-events-none absolute left-0 top-6 z-50 w-max max-w-xs rounded-xl px-4 py-3 text-xs font-medium normal-case shadow-xl opacity-0 group-hover:opacity-100 transition-opacity ${dark ? 'bg-slate-800 text-slate-200 border border-slate-700' : 'bg-white text-slate-700 border border-slate-200'}`}>
                                Visão granular de inscrições e receita.<br />
                                Hierarquia atual:<br/>
                                <span className="font-mono text-[10px] mt-2 block text-blue-500">{activeHierarchy.map(d => DIM_LABELS[d]).join(' → ')}</span>
                              </span>
                            </span>
                          </div>
                        </th>
                        <th className="py-4 px-4 text-right">Inscritos</th>
                        <th className="py-4 px-3 text-right">%</th>
                        <th className="py-4 px-4 text-right">Rec. Bruta</th>
                        <th className="py-4 px-4 text-right">Rec. Líquida</th>
                        <th className="py-4 px-4 text-right">Ticket Médio</th>
                      </tr>
                    </thead>
                    <tbody>
                      {tree.map(node => (
                        <TreeRow
                          key={node.key}
                          node={node}
                          dark={dark}
                          expanded={expanded}
                          bankExpanded={bankExpanded}
                          onToggle={handleToggle}
                          onBankToggle={handleBankToggle}
                          totalInscritos={totalInscritos}
                        />
                      ))}
                    </tbody>
                    <tfoot>
                      <tr className={`text-xs font-black uppercase tracking-wider ${dark ? 'bg-slate-900 text-slate-200 border-t-2 border-slate-700' : 'bg-slate-100 text-slate-800 border-t-2 border-slate-200'}`}>
                        <td className="py-4 px-5">TOTAL FILTRADO</td>
                        <td className="py-4 px-4 text-right">{fmt(filteredRows.reduce((s, r) => s + r.inscritos, 0))}</td>
                        <td className="py-4 px-3 text-right text-slate-500">100%</td>
                        <td className="py-4 px-4 text-right">{fmtR(filteredRows.reduce((s, r) => s + r.receita_bruta, 0))}</td>
                        <td className={`py-4 px-4 text-right ${dark ? 'text-emerald-400' : 'text-emerald-600'}`}>
                          {fmtR(filteredRows.reduce((s, r) => s + r.receita_liquida, 0))}
                        </td>
                        <td className={`py-4 px-4 text-right ${dark ? 'text-amber-400' : 'text-amber-600'}`}>
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
                <div className="overflow-x-auto rounded-b-3xl">
                  <table className="w-full min-w-[1000px] text-sm">
                    <thead>
                      <tr className={`text-left text-[11px] font-bold uppercase tracking-wider border-b ${borderCol} ${dark ? 'bg-slate-900 text-slate-400' : 'bg-slate-50 text-slate-500'}`}>
                        {activeFlatCols.map(dim => (
                          <th key={dim} className="py-4 px-4">
                            {dim === 'tamanho_camiseta' ? 'Tamanho' : DIM_LABELS[dim]}
                          </th>
                        ))}
                        <th className="py-4 px-4 text-right">Inscritos</th>
                        <th className="py-4 px-4 text-right">Rec. Liq.</th>
                        <th className="py-4 px-4 text-right">Ticket</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredRows.map((row, i) => (
                        <tr key={i} className={`border-b hover:bg-blue-500/5 transition-colors ${dark ? 'border-slate-800 odd:bg-slate-900/40 even:bg-slate-800/20' : 'border-slate-100 odd:bg-white even:bg-slate-50/50'}`}>
                          {activeFlatCols.map(dim => {
                            if (dim === 'canal') return <td key={dim} className="py-3 px-4"><CanalBadge canal={row.canal} /></td>;
                            if (dim === 'kit') return <td key={dim} className={`py-3 px-4 text-xs font-bold ${dark ? 'text-slate-200' : 'text-slate-800'} max-w-[180px] truncate`} title={row.kit || ''}>{val(row.kit)}</td>;
                            if (dim === 'produtos') return <td key={dim} className={`py-3 px-4 text-xs font-medium ${dark ? 'text-slate-400' : 'text-slate-600'} max-w-[140px] truncate`} title={row.produtos || ''}>{val(row.produtos)}</td>;
                            if (dim === 'tamanho_camiseta') return <td key={dim} className={`py-3 px-4 text-xs font-bold ${dark ? 'text-slate-300' : 'text-slate-700'}`}>{val(row.tamanho_camiseta)}</td>;
                            return <td key={dim} className={`py-3 px-4 text-xs font-medium ${dark ? 'text-slate-400' : 'text-slate-600'}`}>{val(row[dim])}</td>;
                          })}
                          <td className={`py-3 px-4 text-xs text-right font-black tabular-nums ${dark ? 'text-white' : 'text-slate-900'}`}>{fmt(row.inscritos)}</td>
                          <td className={`py-3 px-4 text-xs text-right font-bold tabular-nums ${dark ? 'text-emerald-400' : 'text-emerald-600'}`}>{fmtR(row.receita_liquida)}</td>
                          <td className={`py-3 px-4 text-xs text-right font-bold tabular-nums ${dark ? 'text-amber-400' : 'text-amber-600'}`}>{fmtR(row.ticket_medio)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

            </div>
          </motion.div>
        )}
      </div>
    </div>
  );
};

export default DetalheEventos;
