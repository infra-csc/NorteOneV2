import React, { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import { useTheme } from '../../context/ThemeContext';
import {
  detalheEventosService,
  DetalheEventoDisponivel,
  DetalheEventoPayload,
  DetalheRow,
  DetalheBancoRow,
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

// Hierarquia canônica: kit → modalidade → pelotao → produtos → tamanho_camiseta
// Canal é um filtro de primeira camada (pills), não faz parte da árvore de drill-down.
const DEFAULT_HIERARCHY: DimKey[] = ['kit', 'modalidade', 'pelotao', 'produtos', 'tamanho_camiseta'];

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
    <div className={`p-2 rounded-lg ${color}`}>{icon}</div>
    <div className="min-w-0">
      <p className={`text-xs font-medium uppercase tracking-wide ${dark ? 'text-gray-400' : 'text-gray-500'}`}>{label}</p>
      <p className={`text-xl font-bold ${dark ? 'text-white' : 'text-gray-900'}`}>{value}</p>
      {sub && <p className={`text-xs ${dark ? 'text-gray-500' : 'text-gray-400'} mt-0.5`}>{sub}</p>}
    </div>
  </div>
);

// ---------------------------------------------------------------------------
// Badges
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
        className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium ${
          dark ? 'bg-blue-900/50 text-blue-300 border border-blue-700/50' : 'bg-blue-50 text-blue-600 border border-blue-200'
        }`}
      >
        <Database className="w-2.5 h-2.5" />
        Snapshot · {label}
      </span>
    );
  }

  if (source === 'live') {
    return (
      <span
        title="Dados buscados ao vivo de Ativo e Magento agora."
        className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium ${
          dark ? 'bg-emerald-900/50 text-emerald-300 border border-emerald-700/50' : 'bg-emerald-50 text-emerald-600 border border-emerald-200'
        }`}
      >
        <TrendingUp className="w-2.5 h-2.5" />
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
  // Bank-split children at leaf level
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
  // parentKey is threaded through to build path-stable, globally-unique keys.
  // Format: "<parentKey>|<dim>:<escaped-value>"
  // This ensures that the same label at the same depth under different parents
  // gets a distinct key — preventing expand/collapse cross-contamination.
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
      const totalIns = groupRows.reduce((s, r) => s + (r.inscritos || 0), 0);
      const totalBruta = groupRows.reduce((s, r) => s + (r.receita_bruta || 0), 0);
      const totalLiq = groupRows.reduce((s, r) => s + (r.receita_liquida || 0), 0);
      const bancos = [...new Set(groupRows.flatMap(r => r.bancos || []))];
      const firstCanal = groupRows[0]?.canal ?? null;

      const isLeaf = rest.length === 0;

      // Detect divergências for this subtree
      const hasDivergencia = groupRows.some(r => {
        const dk = `${r.canal}|${r.kit}|${r.modalidade}|${r.pelotao}|${r.produtos}|${r.tamanho_camiseta}`;
        return divergencias.has(dk);
      });

      // Path-stable unique key: includes full ancestor lineage
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

      if (isLeaf) {
        // Leaf: add bank-split sub-nodes by matching all groupRows against por_banco rows
        const matching = groupRows.flatMap(gr => findBancoRows(gr, allBancoRows));
        // Deduplicate by banco+id_evento combination
        const seen = new Set<string>();
        const deduped = matching.filter(r => {
          const id = `${r.banco}|${r.id_evento}|${r.canal}|${r.kit}|${r.modalidade}`;
          if (seen.has(id)) return false;
          seen.add(id);
          return true;
        });
        if (deduped.length > 0) {
          node.bankSplit = buildBankSplit(deduped);
        }
      } else {
        node.children = group(groupRows, rest, depth + 1, nodeKey);
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

const DEPTH_COLORS_DARK = [
  'bg-gray-700/70',
  'bg-gray-700/40',
  'bg-gray-800/50',
  'bg-gray-800/30',
  'bg-gray-800/20',
  'bg-gray-800/10',
];
const DEPTH_COLORS_LIGHT = [
  'bg-blue-50/60',
  'bg-gray-50',
  'bg-white',
  'bg-gray-50/60',
  'bg-white',
  'bg-gray-50/30',
];

const TreeRow: React.FC<TreeRowProps> = ({ node, dark, expanded, bankExpanded, onToggle, onBankToggle, totalInscritos }) => {
  const isOpen = expanded.has(node.key);
  const bankKey = `bank-${node.key}`;
  const isBankOpen = bankExpanded.has(bankKey);
  const hasChildren = node.children && node.children.length > 0;
  const hasBankSplit = node.bankSplit && node.bankSplit.length > 0;
  const isExpandable = hasChildren || hasBankSplit;

  const pct = totalInscritos > 0 ? (node.inscritos / totalInscritos) * 100 : 0;
  const depthPad = node.depth * 20;
  const rowBg = dark
    ? DEPTH_COLORS_DARK[Math.min(node.depth, DEPTH_COLORS_DARK.length - 1)]
    : DEPTH_COLORS_LIGHT[Math.min(node.depth, DEPTH_COLORS_LIGHT.length - 1)];

  const handleClick = () => {
    if (hasChildren) onToggle(node.key);
    else if (hasBankSplit) onBankToggle(bankKey);
  };

  return (
    <>
      <tr
        className={`border-b ${dark ? 'border-gray-700/60' : 'border-gray-100'} ${rowBg} ${isExpandable ? 'cursor-pointer hover:brightness-95' : ''} transition-all`}
        onClick={handleClick}
      >
        <td className="py-2 pr-3" style={{ paddingLeft: depthPad + 12 }}>
          <div className="flex items-center gap-1.5">
            {hasChildren ? (
              isOpen
                ? <ChevronDown className="w-3.5 h-3.5 text-blue-400 flex-shrink-0" />
                : <ChevronRight className="w-3.5 h-3.5 text-blue-400 flex-shrink-0" />
            ) : hasBankSplit ? (
              isBankOpen
                ? <ChevronDown className="w-3.5 h-3.5 text-emerald-400 flex-shrink-0" />
                : <ChevronRight className="w-3.5 h-3.5 text-emerald-400 flex-shrink-0" />
            ) : (
              <span className="w-3.5" />
            )}
            <span className={`text-sm ${node.depth === 0 ? 'font-semibold' : node.depth === 1 ? 'font-medium' : 'font-normal'} ${dark ? 'text-gray-100' : 'text-gray-800'} truncate max-w-[260px]`}>
              {node.label}
            </span>
            {node.hasDivergencia && (
              <AlertTriangle className="w-3 h-3 text-amber-500 flex-shrink-0" title="Divergência detectada" />
            )}
            {/* Show bank badges at deep levels or leaf */}
            {(node.depth >= 2 || hasBankSplit) && node.bancos.length > 0 && (
              <span className="flex gap-0.5 ml-1">
                {node.bancos.map(b => <BancoBadge key={b} banco={b} />)}
              </span>
            )}
          </div>
        </td>
        <td className={`py-2 px-3 text-right text-sm ${dark ? 'text-gray-300' : 'text-gray-700'}`}>
          <div className="flex flex-col items-end gap-0.5">
            <span className="font-medium">{fmt(node.inscritos)}</span>
            <div className="w-14 h-1 rounded-full bg-gray-200 dark:bg-gray-600 overflow-hidden">
              <div className="h-full bg-blue-500 rounded-full" style={{ width: `${Math.min(pct, 100)}%` }} />
            </div>
          </div>
        </td>
        <td className={`py-2 px-2 text-right text-xs ${dark ? 'text-gray-500' : 'text-gray-400'}`}>
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

      {/* Children (non-leaf) */}
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

      {/* Bank split (leaf expansion) */}
      {hasBankSplit && isBankOpen && node.bankSplit!.map((bs, i) => (
        <tr
          key={`${bankKey}-${bs.banco}-${i}`}
          className={`border-b ${dark ? 'border-gray-700/40 bg-gray-900/40' : 'border-gray-100 bg-blue-50/30'}`}
        >
          <td className="py-1.5 pr-3" style={{ paddingLeft: depthPad + 36 }}>
            <div className="flex items-center gap-2">
              <span className="w-1.5 h-1.5 rounded-full bg-gray-400 flex-shrink-0" />
              <BancoBadge banco={bs.banco} />
              {bs.canal && <CanalBadge canal={bs.canal} />}
              {bs.id_evento && (
                <span className={`text-[10px] ${dark ? 'text-gray-500' : 'text-gray-400'}`}>
                  ID {bs.id_evento}
                </span>
              )}
              {bs.modalidade && (
                <span className={`text-[10px] italic ${dark ? 'text-gray-500' : 'text-gray-400'}`}>
                  {bs.modalidade}
                </span>
              )}
              {bs.produtos && (
                <span className={`text-[10px] ${dark ? 'text-gray-500' : 'text-gray-400'} truncate max-w-[120px]`} title={bs.produtos}>
                  {bs.produtos}
                </span>
              )}
            </div>
          </td>
          <td className={`py-1.5 px-3 text-right text-xs font-medium ${dark ? 'text-gray-300' : 'text-gray-700'}`}>
            {fmt(bs.inscritos)}
          </td>
          <td className={`py-1.5 px-2 text-right text-xs ${dark ? 'text-gray-500' : 'text-gray-400'}`}>
            {totalInscritos > 0 ? ((bs.inscritos / totalInscritos) * 100).toFixed(1) : '0.0'}%
          </td>
          <td className={`py-1.5 px-3 text-right text-xs ${dark ? 'text-gray-400' : 'text-gray-600'}`}>
            {fmtR(bs.receita_bruta)}
          </td>
          <td className={`py-1.5 px-3 text-right text-xs ${dark ? 'text-emerald-500' : 'text-emerald-600'}`}>
            {fmtR(bs.receita_liquida)}
          </td>
          <td className={`py-1.5 px-3 text-right text-xs ${dark ? 'text-amber-500' : 'text-amber-600'}`}>
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
  canal: string;
  kit: string;
  modalidade: string;
  pelotao: string;
  produtos: string;
  tamanho_camiseta: string;
  search: string;
}

const EMPTY_FILTERS: FilterState = {
  canal: '', kit: '', modalidade: '',
  pelotao: '', produtos: '', tamanho_camiseta: '', search: '',
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
  const [bankExpanded, setBankExpanded] = useState<Set<string>>(new Set());
  const [viewMode, setViewMode] = useState<'tree' | 'flat'>('tree');
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
        // Outra consulta ao vivo já está em andamento para este evento.
        // Trata igual ao refresh_in_progress: mostra banner amber e faz
        // re-poll automático sem substituir os dados já exibidos.
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
  }, [eventoGrupo]);

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
    if (filters.kit) rows = rows.filter(r => (r.kit || NULL_LABEL) === filters.kit);
    if (filters.modalidade) rows = rows.filter(r => (r.modalidade || NULL_LABEL) === filters.modalidade);
    if (filters.pelotao) rows = rows.filter(r => (r.pelotao || NULL_LABEL) === filters.pelotao);
    if (filters.produtos) rows = rows.filter(r => (r.produtos || NULL_LABEL) === filters.produtos);
    if (filters.tamanho_camiseta) rows = rows.filter(r => (r.tamanho_camiseta || NULL_LABEL) === filters.tamanho_camiseta);
    if (filters.search) {
      const q = filters.search.toLowerCase();
      rows = rows.filter(r =>
        [r.kit, r.modalidade, r.canal, r.pelotao, r.produtos, r.tamanho_camiseta]
          .some(v => v?.toLowerCase().includes(q))
      );
    }
    return rows;
  }, [payload, activeTab, filters]);

  // All banco rows for matching (filtered by active canal)
  const allBancoRows = useMemo<DetalheBancoRow[]>(() => {
    if (!payload) return [];
    const all = [...payload.por_banco.Ativo, ...payload.por_banco.Magento];
    if (filters.canal) return all.filter(r => r.canal === filters.canal);
    return all;
  }, [payload, filters.canal]);

  // Divergencias as a set of dim keys for fast lookup
  const divergenciaKeys = useMemo(() => {
    if (!payload) return new Set<string>();
    return new Set(
      payload.divergencias.map(d =>
        `${d.dimensoes.canal}|${d.dimensoes.kit}|${d.dimensoes.modalidade}|${d.dimensoes.pelotao}|${d.dimensoes.produtos}|${d.dimensoes.tamanho_camiseta}`
      )
    );
  }, [payload]);

  const opts = useMemo(() => {
    if (!payload) return {} as Record<string, string[]>;
    const all = [...payload.consolidado];
    const uniq = (key: keyof DetalheRow) =>
      [...new Set(all.map(r => r[key] as string | null).map(v => v ?? NULL_LABEL))].sort();
    return {
      canal: uniq('canal'),
      kit: uniq('kit'),
      modalidade: uniq('modalidade'),
      pelotao: uniq('pelotao'),
      produtos: uniq('produtos'),
      tamanho_camiseta: uniq('tamanho_camiseta'),
    };
  }, [payload]);

  const tree = useMemo(
    () => buildTree(filteredRows, allBancoRows, DEFAULT_HIERARCHY, divergenciaKeys),
    [filteredRows, allBancoRows, divergenciaKeys]
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

  // Simplified: aggregate by base size (text before first " - ")
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

  // Breakdown map: base size → sorted list of variants with counts
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

  const totalInscritos = payload?.totais.inscritos ?? 0;
  const activeFiltersCount = Object.entries(filters).filter(([k, v]) => k !== 'search' && v !== '').length;

  const filteredEventos = useMemo(() =>
    eventos.filter(e =>
      !searchEventos ||
      e.nome_evento.toLowerCase().includes(searchEventos.toLowerCase()) ||
      e.evento_grupo.toLowerCase().includes(searchEventos.toLowerCase())
    ),
    [eventos, searchEventos]
  );

  // Selected event info
  const selectedEvento = useMemo(
    () => eventos.find(e => e.evento_grupo === eventoGrupo),
    [eventos, eventoGrupo]
  );

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
          Visão granular de inscrições e receita — hierarquia: Kit → Modalidade → Pelotão → Produtos → Tamanho
        </p>
      </div>

      {/* Event Selector */}
      <div className={`rounded-xl border ${cardBg} p-4 mb-6 shadow-sm`}>
        <div className="flex flex-col sm:flex-row gap-3 items-start sm:items-end">
          <div className="flex-1 min-w-0" ref={comboboxRef}>
            <label className={`block text-xs font-semibold uppercase tracking-wide mb-1 ${textSec}`}>
              Evento
            </label>
            {loadingEventos ? (
              <div className="h-9 w-full rounded-lg bg-gray-200 dark:bg-gray-700 animate-pulse" />
            ) : (
              <div className="relative">
                {/* Trigger */}
                <button
                  type="button"
                  onClick={() => setDropdownOpen(o => !o)}
                  className={`w-full flex items-center justify-between rounded-lg border px-3 py-2 text-sm text-left focus:outline-none focus:ring-2 focus:ring-blue-500 ${
                    dark ? 'bg-gray-700 border-gray-600 text-gray-100' : 'bg-white border-gray-300 text-gray-900'
                  }`}
                >
                  <span className="truncate">
                    {selectedEvento
                      ? `${selectedEvento.nome_evento}${selectedEvento.anos.length > 0 ? ` (${selectedEvento.anos[0]})` : ''} · ${selectedEvento.evento_grupo}`
                      : '— Selecionar evento —'}
                  </span>
                  <ChevronDown className={`ml-2 w-4 h-4 flex-shrink-0 transition-transform ${dropdownOpen ? 'rotate-180' : ''} ${textSec}`} />
                </button>

                {/* Dropdown panel */}
                {dropdownOpen && (
                  <div className={`absolute z-50 mt-1 w-full rounded-xl border shadow-xl overflow-hidden ${
                    dark ? 'bg-gray-800 border-gray-600' : 'bg-white border-gray-200'
                  }`}>
                    {/* Search inside dropdown */}
                    <div className={`flex items-center gap-2 px-3 py-2 border-b ${dark ? 'border-gray-700' : 'border-gray-100'}`}>
                      <Search className={`w-3.5 h-3.5 flex-shrink-0 ${textSec}`} />
                      <input
                        ref={searchInputRef}
                        type="text"
                        placeholder="Filtrar eventos…"
                        value={searchEventos}
                        onChange={e => setSearchEventos(e.target.value)}
                        className={`flex-1 text-sm bg-transparent outline-none ${dark ? 'text-gray-100 placeholder-gray-500' : 'text-gray-900 placeholder-gray-400'}`}
                      />
                      {searchEventos && (
                        <button onClick={() => setSearchEventos('')} className={`${textSec} hover:text-red-500`}>
                          <X className="w-3.5 h-3.5" />
                        </button>
                      )}
                    </div>

                    {/* Options list */}
                    <div className="max-h-72 overflow-y-auto">
                      <button
                        type="button"
                        onClick={() => { setEventoGrupo(''); setDropdownOpen(false); }}
                        className={`w-full text-left px-4 py-2.5 text-sm transition-colors ${
                          !eventoGrupo
                            ? 'bg-indigo-600 text-white'
                            : dark ? 'text-gray-400 hover:bg-gray-700' : 'text-gray-400 hover:bg-gray-50'
                        }`}
                      >
                        — Selecionar evento —
                      </button>
                      {filteredEventos.length === 0 && (
                        <p className={`px-4 py-3 text-sm ${textSec}`}>Nenhum evento encontrado.</p>
                      )}
                      {filteredEventos.map(e => {
                        const isSelected = e.evento_grupo === eventoGrupo;
                        return (
                          <button
                            key={e.evento_grupo}
                            type="button"
                            onClick={() => { setEventoGrupo(e.evento_grupo); setDropdownOpen(false); }}
                            className={`w-full text-left px-4 py-2.5 text-sm transition-colors ${
                              isSelected
                                ? 'bg-indigo-600 text-white'
                                : dark ? 'text-gray-200 hover:bg-gray-700' : 'text-gray-800 hover:bg-gray-50'
                            }`}
                          >
                            <span className="block font-medium truncate">
                              {e.nome_evento}
                              {e.anos.length > 0 ? ` (${e.anos[0]})` : ''}
                            </span>
                            <span className={`block text-xs truncate ${isSelected ? 'text-indigo-200' : textSec}`}>
                              {e.evento_grupo}
                            </span>
                          </button>
                        );
                      })}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>

          <button
            onClick={() => eventoGrupo && loadDetalhe(eventoGrupo, true)}
            disabled={!eventoGrupo || loading || refreshCooldown > 0}
            title={
              refreshCooldown > 0
                ? `Aguarde ${refreshCooldown}s antes de atualizar novamente`
                : 'Recarregar sem cache'
            }
            className={`flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
              dark ? 'bg-gray-700 hover:bg-gray-600 text-gray-200 disabled:opacity-40' : 'bg-gray-100 hover:bg-gray-200 text-gray-700 disabled:opacity-40'
            }`}
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            {refreshCooldown > 0 ? `Atualizar (${refreshCooldown}s)` : 'Atualizar'}
          </button>
        </div>

        {/* Selected event metadata */}
        {selectedEvento && (
          <div className={`mt-3 pt-3 border-t ${borderCol} flex flex-wrap gap-3 text-xs ${textSec}`}>
            <span>
              <span className="font-semibold">Grupo / SKU:</span>{' '}
              <code className={`px-1.5 py-0.5 rounded text-xs ${dark ? 'bg-gray-700 text-gray-300' : 'bg-gray-100 text-gray-700'}`}>
                {selectedEvento.evento_grupo}
              </code>
            </span>
            {selectedEvento.ativo_ids.length > 0 && (
              <span>
                <span className="font-semibold text-emerald-600 dark:text-emerald-400">Ativo IDs:</span>{' '}
                {selectedEvento.ativo_ids.join(', ')}
              </span>
            )}
            {selectedEvento.magento_ids.length > 0 && (
              <span>
                <span className="font-semibold text-orange-600 dark:text-orange-400">Magento IDs:</span>{' '}
                {selectedEvento.magento_ids.join(', ')}
              </span>
            )}
            {payload && !loading && (
              <SnapshotBadge source={payload.source} snapshotUpdatedAt={payload.snapshot_updated_at} dark={dark} />
            )}
          </div>
        )}
      </div>

      {error && (
        <div className="mb-4 flex items-start gap-2 rounded-lg bg-red-50 border border-red-200 p-3 text-red-700">
          <AlertTriangle className="w-4 h-4 flex-shrink-0 mt-0.5" />
          <p className="text-sm">{error}</p>
        </div>
      )}

      {refreshInProgress && !loading && (
        <div className={`mb-4 flex items-center gap-2 rounded-lg px-4 py-2.5 text-sm border ${
          dark ? 'bg-amber-900/30 border-amber-700 text-amber-300' : 'bg-amber-50 border-amber-200 text-amber-700'
        }`}>
          <RefreshCw className="w-3.5 h-3.5 animate-spin flex-shrink-0" />
          <span>Atualização em andamento — dados mais recentes chegarão em instantes.</span>
        </div>
      )}

      {loading && (
        <div className="space-y-4">
          <div className={`rounded-xl border ${
            isLiveLoad
              ? dark ? 'border-amber-700 bg-amber-900/30' : 'border-amber-200 bg-amber-50'
              : dark ? 'border-indigo-700 bg-indigo-900/30' : 'border-indigo-200 bg-indigo-50'
          } px-5 py-4 flex items-center gap-4`}>
            <RefreshCw className={`w-5 h-5 animate-spin flex-shrink-0 ${isLiveLoad ? 'text-amber-500' : 'text-indigo-500'}`} />
            <div className="min-w-0">
              <p className={`text-sm font-semibold ${
                isLiveLoad
                  ? dark ? 'text-amber-300' : 'text-amber-700'
                  : dark ? 'text-indigo-300' : 'text-indigo-700'
              }`}>
                {isLiveLoad
                  ? 'Buscando dados ao vivo… (pode levar ~2 min)'
                  : 'Carregando dados do snapshot…'}
              </p>
              <p className={`text-xs mt-0.5 ${
                isLiveLoad
                  ? dark ? 'text-amber-400' : 'text-amber-600'
                  : dark ? 'text-indigo-400' : 'text-indigo-500'
              }`}>
                {isLiveLoad
                  ? <>Consulta direta aos bancos externos (Ativo via SSH, Magento direto).{loadingSecs > 0 && <span className="ml-2 font-mono">{loadingSecs}s / 150s</span>}</>
                  : 'Lendo snapshot consolidado — geralmente rápido.'}
              </p>
            </div>
          </div>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            {[...Array(4)].map((_, i) => (
              <div key={i} className={`h-20 rounded-xl animate-pulse ${dark ? 'bg-gray-800' : 'bg-gray-200'}`} />
            ))}
          </div>
          <div className={`h-64 rounded-xl animate-pulse ${dark ? 'bg-gray-800' : 'bg-gray-200'}`} />
        </div>
      )}

      {!loading && !payload && !error && (
        <div className={`rounded-xl border ${cardBg} p-12 text-center shadow-sm`}>
          <Table2 className={`w-12 h-12 mx-auto mb-3 ${dark ? 'text-gray-600' : 'text-gray-300'}`} />
          <p className={`text-base font-medium ${textPrimary}`}>Nenhum evento selecionado</p>
          <p className={`text-sm mt-1 ${textSec}`}>Selecione um evento acima para visualizar o detalhamento.</p>
        </div>
      )}

      {!loading && payload && (
        <>
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

          {payload.divergencias.length > 0 && (
            <div className="mb-4 flex items-start gap-2 rounded-lg bg-red-50 border border-red-200 p-3 text-red-700">
              <AlertTriangle className="w-4 h-4 flex-shrink-0 mt-0.5" />
              <div>
                <p className="text-sm font-semibold">{payload.divergencias.length} divergência(s) detectada(s)</p>
                <p className="text-xs mt-0.5">A soma dos bancos difere do total consolidado em algumas combinações. Indicado por <AlertTriangle className="inline w-3 h-3" /> na árvore.</p>
              </div>
            </div>
          )}

          {/* KPI Cards */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
            <KpiCard label="Total Inscritos" value={fmt(payload.totais.inscritos)} icon={<Users className="w-4 h-4 text-blue-600" />} color="bg-blue-50" dark={dark} />
            <KpiCard label="Receita Bruta" value={fmtR(payload.totais.receita_bruta)} icon={<DollarSign className="w-4 h-4 text-emerald-600" />} color="bg-emerald-50" dark={dark} />
            <KpiCard label="Receita Líquida" value={fmtR(payload.totais.receita_liquida)} icon={<TrendingUp className="w-4 h-4 text-indigo-600" />} color="bg-indigo-50" dark={dark} />
            <KpiCard label="Ticket Médio" value={fmtR(payload.totais.ticket_medio)} sub="Por inscrito (rec. líquida)" icon={<Tag className="w-4 h-4 text-amber-600" />} color="bg-amber-50" dark={dark} />
          </div>

          {/* Canal pills — funciona como filtro de primeira camada */}
          <div className="flex flex-wrap gap-2 mb-5">
            <span className={`text-xs font-semibold self-center mr-1 ${textSec}`}>Canal:</span>
            {Object.entries(payload.totais.por_canal).map(([canal, stats]) => (
              <button
                key={canal}
                onClick={() => setFilters(f => ({ ...f, canal: f.canal === canal ? '' : canal }))}
                className={`flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-semibold border transition-all ${
                  filters.canal === canal ? 'ring-2 ring-offset-1 ring-blue-500' : ''
                } ${dark ? 'border-gray-600 bg-gray-700 text-gray-200 hover:bg-gray-600' : 'border-gray-200 bg-white text-gray-700 hover:bg-gray-50'}`}
              >
                <span className="w-2.5 h-2.5 rounded-full" style={{ background: CANAL_COLORS[canal] || '#6b7280' }} />
                <span>{canal}</span>
                <span className={dark ? 'text-gray-400' : 'text-gray-500'}>{fmt(stats.inscritos)}</span>
              </button>
            ))}
            {filters.canal && (
              <button onClick={() => setFilters(f => ({ ...f, canal: '' }))} className="flex items-center gap-1 px-2 py-1.5 text-xs text-red-500 hover:text-red-700">
                <X className="w-3 h-3" /> Limpar
              </button>
            )}
          </div>

          {/* Charts */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-6">
            <div className={`rounded-xl border ${cardBg} p-4 shadow-sm`}>
              <p className={`text-xs font-semibold uppercase tracking-wide mb-3 ${textSec}`}>Inscritos por Canal</p>
              <ResponsiveContainer width="100%" height={140}>
                <BarChart data={canalChartData} barSize={32}>
                  <XAxis dataKey="canal" tick={{ fontSize: 11, fill: dark ? '#9ca3af' : '#6b7280' }} axisLine={false} tickLine={false} />
                  <YAxis hide />
                  <Tooltip formatter={(v: number) => [fmt(v), 'Inscritos']} contentStyle={{ background: dark ? '#1f2937' : '#fff', border: 'none', borderRadius: 8, fontSize: 12 }} />
                  <Bar dataKey="inscritos" radius={[4, 4, 0, 0]}>
                    {canalChartData.map((entry, i) => <Cell key={i} fill={CANAL_COLORS[entry.canal] || CHART_COLORS[i % CHART_COLORS.length]} />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
            <div className={`rounded-xl border ${cardBg} p-4 shadow-sm`}>
              <p className={`text-xs font-semibold uppercase tracking-wide mb-3 ${textSec}`}>Top Modalidades</p>
              <ResponsiveContainer width="100%" height={140}>
                <BarChart data={modalidadeChartData.slice(0, 8)} layout="vertical" barSize={12}>
                  <XAxis type="number" hide />
                  <YAxis type="category" dataKey="name" width={80} tick={{ fontSize: 10, fill: dark ? '#9ca3af' : '#6b7280' }} axisLine={false} tickLine={false} />
                  <Tooltip formatter={(v: number) => [fmt(v), 'Inscritos']} contentStyle={{ background: dark ? '#1f2937' : '#fff', border: 'none', borderRadius: 8, fontSize: 12 }} />
                  <Bar dataKey="value" radius={[0, 4, 4, 0]}>
                    {modalidadeChartData.slice(0, 8).map((_, i) => <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
            <div className={`rounded-xl border ${cardBg} p-4 shadow-sm`}>
              <div className="flex items-center justify-between mb-3">
                <p className={`text-xs font-semibold uppercase tracking-wide ${textSec}`}>Tamanhos de Camiseta</p>
                {tamanhoChartData.length > 0 && (
                  <button
                    onClick={() => setTamanhoDetalhado(v => !v)}
                    className={`text-[10px] px-2 py-0.5 rounded-full border transition-colors ${
                      tamanhoDetalhado
                        ? dark ? 'bg-blue-600 border-blue-500 text-white' : 'bg-blue-500 border-blue-500 text-white'
                        : dark ? 'border-gray-600 text-gray-400 hover:text-gray-200' : 'border-gray-300 text-gray-500 hover:text-gray-700'
                    }`}
                  >
                    {tamanhoDetalhado ? 'Simplificado' : 'Ver variações'}
                  </button>
                )}
              </div>
              {tamanhoChartData.length > 0 ? (
                <ResponsiveContainer width="100%" height={160}>
                  <PieChart>
                    <Pie
                      data={tamanhoDetalhado ? tamanhoChartData : tamanhoChartDataSimple}
                      dataKey="value"
                      nameKey="name"
                      cx="50%"
                      cy="50%"
                      outerRadius={52}
                      innerRadius={28}
                    >
                      {(tamanhoDetalhado ? tamanhoChartData : tamanhoChartDataSimple).map((_, i) => (
                        <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip
                      content={({ active, payload: tp }) => {
                        if (!active || !tp?.length) return null;
                        const entry = tp[0];
                        const baseName = entry.name as string;
                        const total = entry.value as number;
                        const variants = !tamanhoDetalhado ? tamanhoBreakdownMap.get(baseName) : null;
                        const hasVariants = variants && variants.length > 1;
                        return (
                          <div style={{
                            background: dark ? '#1f2937' : '#fff',
                            border: `1px solid ${dark ? '#374151' : '#e5e7eb'}`,
                            borderRadius: 8,
                            padding: '8px 10px',
                            fontSize: 12,
                            minWidth: 140,
                            maxWidth: 220,
                          }}>
                            <p style={{ fontWeight: 600, marginBottom: hasVariants ? 6 : 0, color: dark ? '#f3f4f6' : '#111827' }}>
                              {baseName} — {fmt(total)}
                            </p>
                            {hasVariants && variants!.map(v => {
                              const pct = total > 0 ? ((v.value / total) * 100).toFixed(1) : '0';
                              const label = v.name === baseName ? `${baseName} (sem variação)` : v.name;
                              return (
                                <div key={v.name} style={{ display: 'flex', justifyContent: 'space-between', gap: 12, color: dark ? '#9ca3af' : '#6b7280', marginTop: 2 }}>
                                  <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{label}</span>
                                  <span style={{ flexShrink: 0 }}>{fmt(v.value)} ({pct}%)</span>
                                </div>
                              );
                            })}
                          </div>
                        );
                      }}
                    />
                    <Legend iconSize={8} iconType="circle" wrapperStyle={{ fontSize: 10 }} />
                  </PieChart>
                </ResponsiveContainer>
              ) : (
                <div className={`flex items-center justify-center h-[160px] text-sm ${textSec}`}>Sem dados de tamanho</div>
              )}
            </div>
          </div>

          {/* Additional filters bar */}
          <div className={`rounded-xl border ${cardBg} p-3 mb-4 shadow-sm`}>
            <div className="flex flex-wrap gap-2 items-center">
              <div className="flex items-center gap-1.5 mr-1">
                <Filter className={`w-3.5 h-3.5 ${textSec}`} />
                <span className={`text-xs font-semibold ${textSec}`}>Filtros adicionais</span>
                {activeFiltersCount > 0 && (
                  <span className="bg-blue-500 text-white text-[10px] font-bold px-1.5 py-0.5 rounded-full">{activeFiltersCount}</span>
                )}
              </div>
              <div className="relative">
                <Search className={`absolute left-2 top-1.5 w-3.5 h-3.5 ${textSec}`} />
                <input
                  type="text"
                  placeholder="Buscar…"
                  value={filters.search}
                  onChange={e => setFilters(f => ({ ...f, search: e.target.value }))}
                  className={`pl-7 pr-3 py-1 text-xs rounded-lg border focus:outline-none focus:ring-2 focus:ring-blue-500 ${
                    dark ? 'bg-gray-700 border-gray-600 text-gray-100 placeholder-gray-500' : 'bg-white border-gray-300 text-gray-900 placeholder-gray-400'
                  }`}
                  style={{ width: 130 }}
                />
              </div>
              {/* Dimension dropdowns (sans canal — já tem pills acima) */}
              {(['kit', 'modalidade', 'pelotao', 'produtos', 'tamanho_camiseta'] as const).map(dim => (
                <select
                  key={dim}
                  value={(filters as any)[dim]}
                  onChange={e => setFilters(f => ({ ...f, [dim]: e.target.value }))}
                  className={`text-xs rounded-lg border px-2 py-1 focus:outline-none focus:ring-2 focus:ring-blue-500 ${
                    (filters as any)[dim] ? 'ring-1 ring-blue-500' : ''
                  } ${dark ? 'bg-gray-700 border-gray-600 text-gray-100' : 'bg-white border-gray-300 text-gray-900'}`}
                >
                  <option value="">{DIM_LABELS[dim] || dim}</option>
                  {(opts[dim] || []).map(v => <option key={v} value={v}>{v}</option>)}
                </select>
              ))}
              {(activeFiltersCount > 0 || filters.search) && (
                <button onClick={() => setFilters(EMPTY_FILTERS)} className="flex items-center gap-1 text-xs text-red-500 hover:text-red-700 ml-1">
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
                    onClick={() => { setActiveTab(tab); setExpanded(new Set()); setBankExpanded(new Set()); }}
                    className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors ${
                      activeTab === tab ? 'bg-blue-500 text-white' : dark ? 'text-gray-400 hover:bg-gray-700' : 'text-gray-600 hover:bg-gray-100'
                    }`}
                  >
                    {tab === 'consolidado' && <Layers className="w-3.5 h-3.5" />}
                    {tab !== 'consolidado' && <Database className="w-3.5 h-3.5" />}
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
                  className={`p-1.5 rounded text-xs font-medium transition-colors ${viewMode === 'tree' ? 'bg-blue-500 text-white' : dark ? 'text-gray-400 hover:bg-gray-700' : 'text-gray-500 hover:bg-gray-100'}`}
                  title="Visão hierárquica"
                >
                  <Layers className="w-3.5 h-3.5" />
                </button>
                <button
                  onClick={() => setViewMode('flat')}
                  className={`p-1.5 rounded text-xs font-medium transition-colors ${viewMode === 'flat' ? 'bg-blue-500 text-white' : dark ? 'text-gray-400 hover:bg-gray-700' : 'text-gray-500 hover:bg-gray-100'}`}
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
                      className={`text-xs px-2 py-1 rounded ${dark ? 'text-blue-400 hover:bg-gray-700' : 'text-blue-600 hover:bg-blue-50'}`}
                    >
                      Expandir tudo
                    </button>
                    <button
                      onClick={() => { setExpanded(new Set()); setBankExpanded(new Set()); }}
                      className={`text-xs px-2 py-1 rounded ${dark ? 'text-gray-400 hover:bg-gray-700' : 'text-gray-500 hover:bg-gray-100'}`}
                    >
                      Colapsar
                    </button>
                  </>
                )}
              </div>
            </div>

            {filteredRows.length === 0 ? (
              <div className="py-12 text-center">
                <p className={`text-sm ${textSec}`}>Nenhum dado com os filtros atuais.</p>
              </div>
            ) : viewMode === 'tree' ? (
              <div className="overflow-auto">
                <table className="w-full min-w-[700px] text-sm">
                  <thead>
                    <tr className={`text-left text-xs font-semibold uppercase tracking-wide ${dark ? 'bg-gray-700/80 text-gray-400' : 'bg-gray-50 text-gray-500'}`}>
                      <th className="py-2 px-3">
                        Dimensão
                        {activeTab === 'consolidado' && (
                          <span className={`ml-1.5 text-[10px] normal-case font-normal ${textSec}`}>
                            (clique na folha para ver split Ativo/Magento)
                          </span>
                        )}
                      </th>
                      <th className="py-2 px-3 text-right">Inscritos</th>
                      <th className="py-2 px-2 text-right">%</th>
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
                        bankExpanded={bankExpanded}
                        onToggle={handleToggle}
                        onBankToggle={handleBankToggle}
                        totalInscritos={totalInscritos}
                      />
                    ))}
                  </tbody>
                  <tfoot>
                    <tr className={`text-xs font-bold uppercase ${dark ? 'bg-gray-700 text-gray-300 border-t border-gray-600' : 'bg-gray-100 text-gray-700 border-t border-gray-200'}`}>
                      <td className="py-2 px-3">TOTAL FILTRADO</td>
                      <td className="py-2 px-3 text-right">{fmt(filteredRows.reduce((s, r) => s + r.inscritos, 0))}</td>
                      <td className="py-2 px-2 text-right">100%</td>
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
                      <tr key={i} className={`border-b ${dark ? 'border-gray-700 odd:bg-gray-800/40 even:bg-gray-800/20' : 'border-gray-100 odd:bg-white even:bg-gray-50/50'}`}>
                        <td className="py-1.5 px-3"><CanalBadge canal={row.canal} /></td>
                        <td className={`py-1.5 px-3 text-xs ${dark ? 'text-gray-300' : 'text-gray-700'} max-w-[160px] truncate`} title={row.kit || ''}>{val(row.kit)}</td>
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

            <div className={`px-4 py-2 border-t ${borderCol} flex justify-between items-center`}>
              <span className={`text-xs ${textSec}`}>
                {filteredRows.length} combinações · {fmt(filteredRows.reduce((s, r) => s + r.inscritos, 0))} inscritos
              </span>
              <span className={`text-xs ${textSec}`}>
                Ativo: {fmt(payload.por_banco.Ativo.length)} linhas · Magento: {fmt(payload.por_banco.Magento.length)} linhas
              </span>
            </div>
          </div>
        </>
      )}
    </div>
  );
};

export default DetalheEventos;
