import React, { useEffect, useState, useMemo, useRef, useLayoutEffect } from 'react';
import { createPortal } from 'react-dom';
import { projecaoService, usersService } from '../../services/api';
import { useTheme } from '../../context/ThemeContext';
import { useAuth } from '../../context/AuthContext';
import { usePermissions } from '../../context/PermissionContext';
import {
  BarChart3, Plus, Pencil, Trash2, X, History, Users, Settings,
  Calendar, Filter, Eye, ChevronDown, ChevronUp, Search,
  Layers, Download, RotateCcw,
  AlertTriangle, Trash, Check, Lock, LockOpen, Clock, Bell, Zap,
  Package, Info, Truck, Mail,
} from 'lucide-react';

interface MultiSelectOption {
  value: string;
  label: string;
}

const MultiSelectDropdown: React.FC<{
  options: MultiSelectOption[];
  selected: string[];
  onChange: (selected: string[]) => void;
  placeholder: string;
  isDark: boolean;
}> = ({ options, selected, onChange, placeholder, isDark }) => {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const toggle = (val: string) => {
    onChange(
      selected.includes(val)
        ? selected.filter(s => s !== val)
        : [...selected, val]
    );
  };

  const displayLabel = selected.length === 0
    ? placeholder
    : selected.length === 1
      ? options.find(o => o.value === selected[0])?.label || selected[0]
      : `${selected.length} selecionados`;

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className={`flex items-center gap-2 px-3 py-2 rounded-xl border text-sm min-w-[150px] text-left transition-all ${
          isDark
            ? 'bg-gray-800/50 border-gray-600 text-white hover:border-gray-500'
            : 'bg-white border-gray-300 text-gray-900 hover:border-gray-400'
        } ${open ? 'ring-2 ring-blue-500' : ''} ${selected.length > 0 ? (isDark ? 'border-violet-500/60' : 'border-violet-400') : ''}`}
      >
        <span className="flex-1 truncate">{displayLabel}</span>
        <ChevronDown className={`w-3.5 h-3.5 shrink-0 transition-transform ${open ? 'rotate-180' : ''} ${isDark ? 'text-gray-400' : 'text-gray-500'}`} />
      </button>
      {open && (
        <div className={`absolute z-50 mt-1 w-full min-w-[200px] max-h-64 overflow-y-auto rounded-xl border shadow-xl ${
          isDark ? 'bg-gray-800 border-gray-600' : 'bg-white border-gray-200'
        }`}>
          {selected.length > 0 && (
            <button
              type="button"
              onClick={() => onChange([])}
              className={`w-full px-3 py-2 text-xs font-semibold text-left border-b transition-colors ${
                isDark ? 'text-red-400 hover:bg-gray-700/50 border-gray-700' : 'text-red-500 hover:bg-red-50 border-gray-100'
              }`}
            >
              Limpar seleção
            </button>
          )}
          {options.map(opt => {
            const isSelected = selected.includes(opt.value);
            return (
              <button
                key={opt.value}
                type="button"
                onClick={() => toggle(opt.value)}
                className={`w-full flex items-center gap-2 px-3 py-2 text-sm text-left transition-colors ${
                  isSelected
                    ? isDark ? 'bg-violet-500/20 text-violet-300' : 'bg-violet-50 text-violet-700'
                    : isDark ? 'text-gray-300 hover:bg-gray-700/50' : 'text-gray-700 hover:bg-gray-50'
                }`}
              >
                <div className={`w-4 h-4 rounded border flex items-center justify-center shrink-0 ${
                  isSelected
                    ? 'bg-violet-500 border-violet-500'
                    : isDark ? 'border-gray-500' : 'border-gray-300'
                }`}>
                  {isSelected && <Check className="w-3 h-3 text-white" />}
                </div>
                <span className="truncate">{opt.label}</span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
};

interface AreaProjecao {
  id: number;
  nome: string;
  usa_cutoff_customizado?: boolean;
}

interface CutoffEventoArea {
  id: number;
  evento_id: number;
  area_projecao_id: number;
  area_projecao_nome: string | null;
  data_corte_1: string | null;
  data_corte_2: string | null;
  data_saida_caminhao: string | null;
  updated_by: number | null;
  updated_by_nome: string | null;
  updated_at: string | null;
}

interface ClienteItem {
  nome_cliente: string;
  quantidade: string;
}

interface ClienteResponse {
  id: number;
  projecao_id: number;
  nome_cliente: string;
  quantidade: number;
}

interface KitItem {
  nome_kit: string;
  quantidade: string;
}

interface KitResponse {
  id: number;
  projecao_id: number;
  nome_kit: string;
  quantidade: number;
}

const KITS_PADRAO = ['Kit Básico', 'Inscrição Participação', 'Kit Completo - Sem camiseta', 'Kit Vip', 'Kit Plus', 'Kit Super'];
const KITS_DESCRICOES: Record<string, string> = {
  'Kit Básico': 'Kit padrão da corrida',
  'Inscrição Participação': 'Apenas medalha e n° de peito',
  'Kit Completo - Sem camiseta': 'Itens do Kit Básico sem a camiseta',
  'Kit Vip': 'Jaqueta',
  'Kit Plus': 'Boné / Viseira',
  'Kit Super': 'Mochila / Bag / Mala tubo',
};
const KIT_CAMISETA_ORIGEM = 'Kit Completo - Sem camiseta';
const KIT_CAMISETA_LABEL = 'Camiseta avulsa';
const buildKitsPadrao = (): KitItem[] => KITS_PADRAO.map(nome => ({ nome_kit: nome, quantidade: '' }));

interface Projecao {
  id: number;
  evento_id: number;
  evento_nome: string;
  evento_data: string | null;
  evento_tipo: string | null;
  evento_modalidade: string | null;
  area_projecao_id: number;
  area_projecao_nome: string;
  quantidade: number;
  clientes: ClienteResponse[];
  kits: KitResponse[];
  created_by: number;
  created_by_nome: string | null;
  updated_by: number | null;
  updated_by_nome: string | null;
  locked_at: string | null;
  locked_by_nome: string | null;
  created_at: string | null;
  updated_at: string | null;
  deleted_at: string | null;
  deleted_by_nome: string | null;
}

interface HistoricoItem {
  id: number;
  projecao_id: number;
  acao: string;
  campo_alterado: string | null;
  valor_anterior: string | null;
  valor_novo: string | null;
  usuario_id: number;
  usuario_nome: string | null;
  created_at: string | null;
}

interface ConsolidadoEvento {
  evento_id: number;
  evento_nome: string;
  evento_data: string | null;
  inscritos_reais: number;
  projecoes: { area_projecao_id: number; area_projecao_nome: string; quantidade: number; kits?: { nome_kit: string; quantidade: number }[]; convicta_quantidade?: number; convicta_kits?: { nome_kit: string; quantidade: number }[]; camiseta_avulsa_teto?: number | null }[];
  total_projecoes: number;
  projecao_site: number;
  total_geral: number;
  inscricao_participacao?: number;
  projecao_camisetas?: number;
  corte_dias_1?: number | null;
  corte_dias_2?: number | null;
  corte_ativo?: boolean;
  corte_valor_1?: number | null;
  corte_congelado_1_em?: string | null;
  corte_valor_2?: number | null;
  corte_congelado_2_em?: string | null;
  corte_data_envio?: string | null;
  data_saida_caminhao?: string | null;
  reaberto_manual_corte_1?: boolean;
  reaberto_manual_corte_2?: boolean;
  em_corte2?: boolean;
}

interface AreaDetail {
  id: number;
  nome: string;
  ativo: boolean;
  usa_cutoff_customizado?: boolean;
  usuarios: { id: number; usuario_id: number; usuario_nome: string; usuario_email: string }[];
}

interface Evento {
  id: number;
  nome: string;
  data_evento?: string;
  info_geral?: { data?: string };
  tipo_evento?: string;
  modalidade?: string;
  status?: string;
  cidade?: string;
  circuito_produto?: string;
}

interface SimpleUser {
  id: number;
  nome: string;
  email: string;
  ativo?: boolean;
}

interface CutoffRule {
  id: number;
  nome: string;
  dias_antes_evento: number;
  ativo: boolean;
  created_at?: string | null;
  updated_at?: string | null;
}

interface AutoLockConfig {
  dias_antes_evento: number;
  hora_trava: string;
  ativo: boolean;
  updated_by_nome?: string | null;
  updated_at?: string | null;
}

interface AreaPendente {
  area_projecao_id: number;
  area_projecao_nome: string;
}

interface PendenciaItem {
  evento_id: number;
  evento_nome: string;
  evento_data: string | null;
  dias_ate_evento: number;
  cutoff_dias: number;
  cutoff_nome: string;
  cutoff_customizado?: boolean;
  cutoff_data?: string | null;
  areas_pendentes: AreaPendente[];
}

interface PendenciasResponse {
  total_eventos: number;
  total_areas: number;
  pendencias: PendenciaItem[];
}

const mesesOptions: MultiSelectOption[] = [
  { value: '1', label: 'Janeiro' }, { value: '2', label: 'Fevereiro' },
  { value: '3', label: 'Março' }, { value: '4', label: 'Abril' },
  { value: '5', label: 'Maio' }, { value: '6', label: 'Junho' },
  { value: '7', label: 'Julho' }, { value: '8', label: 'Agosto' },
  { value: '9', label: 'Setembro' }, { value: '10', label: 'Outubro' },
  { value: '11', label: 'Novembro' }, { value: '12', label: 'Dezembro' },
];

type BreakdownItem = { id: number; label: string; quantidade: number };

const BreakdownPopover: React.FC<{
  items: BreakdownItem[];
  title: string;
  color: 'amber' | 'violet';
  icon: React.ReactNode;
  isDark: boolean;
  formatNumber: (n: number) => string;
  showTotal?: boolean;
}> = ({ items, title, color, icon, isDark, formatNumber, showTotal = true }) => {
  const [visible, setVisible] = useState(false);
  const [coords, setCoords] = useState<{ top: number; left: number } | null>(null);
  const triggerRef = useRef<HTMLDivElement>(null);

  useLayoutEffect(() => {
    if (!visible || !triggerRef.current) return;
    const rect = triggerRef.current.getBoundingClientRect();
    const tooltipWidth = 240;
    const margin = 8;
    let left = rect.left;
    if (left + tooltipWidth + margin > window.innerWidth) {
      left = Math.max(margin, window.innerWidth - tooltipWidth - margin);
    }
    setCoords({ top: rect.bottom + 6, left });
  }, [visible]);

  useEffect(() => {
    if (!visible) return;
    const close = () => setVisible(false);
    window.addEventListener('scroll', close, true);
    window.addEventListener('resize', close);
    return () => {
      window.removeEventListener('scroll', close, true);
      window.removeEventListener('resize', close);
    };
  }, [visible]);

  if (!items || items.length === 0) return null;

  const total = items.reduce((s, i) => s + i.quantidade, 0);
  const trigBg = color === 'amber'
    ? (isDark ? 'bg-amber-500/20 text-amber-400' : 'bg-amber-100 text-amber-700')
    : (isDark ? 'bg-violet-500/20 text-violet-400' : 'bg-violet-100 text-violet-600');
  const valColor = color === 'amber'
    ? (isDark ? 'text-amber-400' : 'text-amber-600')
    : (isDark ? 'text-violet-400' : 'text-violet-600');

  return (
    <>
      <div
        ref={triggerRef}
        className={`flex items-center gap-0.5 px-1.5 py-0.5 rounded-md cursor-default ${trigBg}`}
        onMouseEnter={() => setVisible(true)}
        onMouseLeave={() => setVisible(false)}
      >
        {icon}
        <span className="text-xs font-semibold">{items.length}</span>
      </div>
      {visible && coords && createPortal(
        <div
          style={{ position: 'fixed', top: coords.top, left: coords.left, width: 240, zIndex: 9999, pointerEvents: 'none' }}
          className={`rounded-xl shadow-2xl border p-3 space-y-1.5 ${isDark ? 'bg-gray-900 border-gray-700' : 'bg-white border-gray-200'}`}
        >
          <p className={`text-xs font-bold uppercase tracking-wider mb-2 ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>{title}</p>
          {items.map(i => (
            <div key={i.id} className={`flex items-center justify-between gap-3 text-xs ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
              <span className="truncate">{i.label}</span>
              <span className={`font-bold shrink-0 ${valColor}`}>{formatNumber(i.quantidade)}</span>
            </div>
          ))}
          {showTotal && (
            <div className={`pt-1.5 mt-1.5 border-t flex items-center justify-between gap-3 text-xs ${isDark ? 'border-gray-700 text-gray-400' : 'border-gray-200 text-gray-500'}`}>
              <span className="font-semibold uppercase tracking-wider">Total</span>
              <span className={`font-bold ${valColor}`}>{formatNumber(total)}</span>
            </div>
          )}
        </div>,
        document.body
      )}
    </>
  );
};

const KitsTooltip: React.FC<{
  kits: KitResponse[];
  isDark: boolean;
  formatNumber: (n: number) => string;
}> = ({ kits, isDark, formatNumber }) => (
  <BreakdownPopover
    items={(kits || []).map(k => ({ id: k.id, label: k.nome_kit, quantidade: k.quantidade }))}
    title="Por kit"
    color="amber"
    icon={<Package className="w-3 h-3" />}
    isDark={isDark}
    formatNumber={formatNumber}
  />
);

const ClientesTooltip: React.FC<{
  clientes: ClienteResponse[];
  quantidade: number;
  isDark: boolean;
  formatNumber: (n: number) => string;
}> = ({ clientes, quantidade, isDark, formatNumber }) => (
  <div className="flex items-center gap-1.5">
    <span>{formatNumber(quantidade)}</span>
    <BreakdownPopover
      items={(clientes || []).map(c => ({ id: c.id, label: c.nome_cliente, quantidade: c.quantidade }))}
      title="Por cliente"
      color="violet"
      icon={<Users className="w-3 h-3" />}
      isDark={isDark}
      formatNumber={formatNumber}
      showTotal={false}
    />
  </div>
);

const ProjecaoInscritos: React.FC = () => {
  const { isDark } = useTheme();
  const { user } = useAuth();
  const { canView, canCreate, canEdit, canDelete } = usePermissions();
  const isAdmin = user?.is_admin || false;
  const hasAccess = canView('projecao_inscritos');
  const canCreateProjecao = canCreate('projecao_inscritos');
  const canEditProjecao = canEdit('projecao_inscritos');
  const canDeleteProjecao = canDelete('projecao_inscritos');

  const [activeTab, setActiveTab] = useState<'projecoes' | 'consolidado' | 'config' | 'lixeira'>('projecoes');
  const [projecoes, setProjecoes] = useState<Projecao[]>([]);
  const [areas, setAreas] = useState<AreaProjecao[]>([]);
  const [myAreaIds, setMyAreaIds] = useState<Set<number>>(new Set());
  const [eventos, setEventos] = useState<Evento[]>([]);
  const [consolidado, setConsolidado] = useState<ConsolidadoEvento[]>([]);
  const [cutoffEnvioMap, setCutoffEnvioMap] = useState<Record<string, string>>({});
  const [consolidadoLoading, setConsolidadoLoading] = useState(false);
  const [consolidadoLoaded, setConsolidadoLoaded] = useState(false);
  const [areasDetail, setAreasDetail] = useState<AreaDetail[]>([]);
  const [allUsers, setAllUsers] = useState<SimpleUser[]>([]);
  const [lixeira, setLixeira] = useState<Projecao[]>([]);
  const [loading, setLoading] = useState(true);

  const [filterMes, setFilterMes] = useState<string[]>([]);
  const [filterTipoEvento, setFilterTipoEvento] = useState<string[]>([]);
  const [filterModalidade, setFilterModalidade] = useState<string[]>([]);
  const [filterArea, setFilterArea] = useState<string[]>([]);
  const [searchTerm, setSearchTerm] = useState('');

  const [showCreateModal, setShowCreateModal] = useState(false);
  const [editingProjecao, setEditingProjecao] = useState<Projecao | null>(null);
  const [formEventoId, setFormEventoId] = useState<number | ''>('');
  const [formAreaId, setFormAreaId] = useState<number | ''>('');
  const [formQuantidade, setFormQuantidade] = useState<string>('');
  const [formTemCliente, setFormTemCliente] = useState(false);
  const [formClientes, setFormClientes] = useState<ClienteItem[]>([{ nome_cliente: '', quantidade: '' }]);
  const [formTemKit, setFormTemKit] = useState(false);
  const [formKits, setFormKits] = useState<KitItem[]>(buildKitsPadrao());
  const [camisetaAvulsaInfo, setCamisetaAvulsaInfo] = useState<{ corte1_congelado: boolean; teto: number }>({ corte1_congelado: false, teto: 0 });
  const [editCorte2, setEditCorte2] = useState(false);
  const [corte1Dist, setCorte1Dist] = useState<{ evento_id: number; area_projecao_id: number; quantidade: number; kits: { nome_kit: string; quantidade: number }[]; clientes: { nome_cliente: string; quantidade: number }[]; fonte: string } | null>(null);
  const [corte1DistError, setCorte1DistError] = useState(false);
  const [corteLoading, setCorteLoading] = useState(false);
  const corte1DistReqRef = useRef(0);
  const [eventoSearchTerm, setEventoSearchTerm] = useState('');
  const [showEventoDropdown, setShowEventoDropdown] = useState(false);
  const eventoDropdownRef = useRef<HTMLDivElement>(null);

  const [showHistorico, setShowHistorico] = useState(false);
  const [historico, setHistorico] = useState<HistoricoItem[]>([]);
  const [historicoProjecao, setHistoricoProjecao] = useState<Projecao | null>(null);

  const [showAtribuirModal, setShowAtribuirModal] = useState(false);
  const [atribuirArea, setAtribuirArea] = useState<AreaDetail | null>(null);
  const [selectedUserIds, setSelectedUserIds] = useState<number[]>([]);

  const [showCreateAreaModal, setShowCreateAreaModal] = useState(false);
  const [newAreaNome, setNewAreaNome] = useState('');

  const [expandedConsolidado, setExpandedConsolidado] = useState<Set<number>>(new Set());
  const [kitBreakdownEvento, setKitBreakdownEvento] = useState<ConsolidadoEvento | null>(null);

  const [confirmModal, setConfirmModal] = useState<{
    title: string;
    message: string;
    confirmLabel: string;
    variant: 'danger' | 'warning' | 'info';
    onConfirm: () => void;
  } | null>(null);

  const [lockingEventoId, setLockingEventoId] = useState<number | null>(null);
  const [selectedEvento, setSelectedEvento] = useState<Evento | null>(null);
  const [eventoListSearch, setEventoListSearch] = useState('');
  const [eventoListMes, setEventoListMes] = useState<string>('');
  const [eventoListModalidade, setEventoListModalidade] = useState<string>('');
  const [eventoListCidade, setEventoListCidade] = useState<string>('');
  const [eventoListStatus, setEventoListStatus] = useState<string>('Em andamento');
  const [consolidadoStatus, setConsolidadoStatus] = useState<string>('Em andamento');
  const [eventoListOnlyCutoff, setEventoListOnlyCutoff] = useState<boolean>(false);
  const [eventoListOnlyLocked, setEventoListOnlyLocked] = useState<boolean>(false);
  const [eventoListSort, setEventoListSort] = useState<{ field: string; dir: 'asc' | 'desc' }>({ field: 'data', dir: 'asc' });
  const [projecaoSort, setProjecaoSort] = useState<{ field: string; dir: 'asc' | 'desc' }>({ field: 'quantidade', dir: 'desc' });

  const [pendencias, setPendencias] = useState<PendenciasResponse | null>(null);
  const [pendenciasBannerDismissed, setPendenciasBannerDismissed] = useState(false);
  const [alertaDraft, setAlertaDraft] = useState<string>('30');
  const [savingAlerta, setSavingAlerta] = useState(false);

  const [eventoCutoffs, setEventoCutoffs] = useState<CutoffEventoArea[]>([]);
  const [eventoCutoffsLoading, setEventoCutoffsLoading] = useState(false);
  const [savingCutoffAreaId, setSavingCutoffAreaId] = useState<number | null>(null);
  const [cutoffDraft, setCutoffDraft] = useState<Record<number, { d1: string; d2: string; saida: string }>>({});
  const cutoffsLoadTokenRef = useRef(0);

  const [selectedEventoCorteSnap, setSelectedEventoCorteSnap] = useState<{ congelado_corte_1_em: string | null; reaberto_manual_corte_1: boolean; congelado_corte_2_em: string | null; reaberto_manual_corte_2: boolean } | null>(null);

  const [autoLockConfig, setAutoLockConfig] = useState<AutoLockConfig>({ dias_antes_evento: 0, hora_trava: '00:00', ativo: false });
  const [autoLockDraft, setAutoLockDraft] = useState<{ dias: string; hora: string; ativo: boolean }>({ dias: '0', hora: '00:00', ativo: false });
  const [savingAutoLock, setSavingAutoLock] = useState(false);

  const [corteConfig, setCorteConfig] = useState<{ dias_corte_1: number; dias_corte_2: number; dias_alerta_envio: number; notif_email_ativo?: boolean; notif_email_hora?: number; ativo: boolean; updated_by_nome?: string | null }>({ dias_corte_1: 30, dias_corte_2: 7, dias_alerta_envio: 30, notif_email_ativo: false, notif_email_hora: 8, ativo: false });
  const [corteDraft, setCorteDraft] = useState<{ dias1: string; dias2: string; ativo: boolean }>({ dias1: '30', dias2: '7', ativo: false });
  const [savingCorte, setSavingCorte] = useState(false);
  const [corteActionBusy, setCorteActionBusy] = useState<string | null>(null);

  const [notifDraft, setNotifDraft] = useState<{ ativo: boolean; hora: string }>({ ativo: false, hora: '8' });
  const [savingNotif, setSavingNotif] = useState(false);
  const [sendingNotifTest, setSendingNotifTest] = useState(false);

  const [toast, setToast] = useState<{ message: string; type: 'error' | 'success' } | null>(null);
  const toastTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);

  const showToast = (message: unknown, type: 'error' | 'success' = 'error') => {
    if (toastTimeout.current) clearTimeout(toastTimeout.current);
    let text: string;
    if (typeof message === 'string') {
      text = message;
    } else if (Array.isArray(message)) {
      text = message
        .map((m: unknown) =>
          m !== null && typeof m === 'object'
            ? ((m as Record<string, unknown>).msg as string) ||
              ((m as Record<string, unknown>).message as string) ||
              JSON.stringify(m)
            : String(m),
        )
        .join('; ');
    } else if (message !== null && typeof message === 'object') {
      const obj = message as Record<string, unknown>;
      text = (obj.msg as string) || (obj.message as string) || (obj.detail as string) || JSON.stringify(message);
    } else {
      text = message != null ? String(message) : 'Erro desconhecido';
    }
    setToast({ message: text || 'Erro desconhecido', type });
    toastTimeout.current = setTimeout(() => setToast(null), 4000);
  };

  const showConfirm = (opts: {
    title: string;
    message: string;
    confirmLabel?: string;
    variant?: 'danger' | 'warning' | 'info';
    onConfirm: () => void;
  }) => {
    setConfirmModal({
      title: opts.title,
      message: opts.message,
      confirmLabel: opts.confirmLabel || 'Confirmar',
      variant: opts.variant || 'danger',
      onConfirm: opts.onConfirm,
    });
  };

  const cardClass = `relative overflow-hidden rounded-2xl p-4 ${isDark ? 'bg-gray-800/50 backdrop-blur-xl border border-gray-700/50' : 'bg-white/70 backdrop-blur-xl border border-gray-200'}`;
  const inputClass = `w-full px-4 py-2.5 rounded-xl border ${isDark ? 'bg-gray-800/50 border-gray-600 text-white' : 'bg-white border-gray-300 text-gray-900'} focus:outline-none focus:ring-2 focus:ring-blue-500`;
  const selectClass = `px-3 py-2 rounded-xl border text-sm ${isDark ? 'bg-gray-800/50 border-gray-600 text-white' : 'bg-white border-gray-300 text-gray-900'} focus:outline-none focus:ring-2 focus:ring-blue-500`;

  const loadData = async () => {
    setLoading(true);
    try {
      const [areasData, myAreasData, projecoesData] = await Promise.all([
        projecaoService.listAreas(),
        projecaoService.minhasAreas(),
        projecaoService.list(buildFilters()),
      ]);
      setAreas(areasData);
      setMyAreaIds(new Set(myAreasData.map((a: AreaProjecao) => a.id)));
      setProjecoes(projecoesData);
      // Pendências can change any time projections are mutated; refresh in background.
      loadPendencias();
    } catch (error) {
      console.error('Erro ao carregar projeções:', error);
    } finally {
      setLoading(false);
    }
  };

  const loadEventos = async () => {
    try {
      const { default: api } = await import('../../services/api');
      const res = await api.get('/cadastros/');
      setEventos(res.data);
    } catch (error) {
      console.error('Erro ao carregar eventos:', error);
    }
  };

  const loadConsolidado = async (force: boolean = false) => {
    // Só exibe o spinner enquanto ainda não há nenhum dado carregado; em
    // recargas (filtros/SWR) mantém os dados atuais visíveis para não "piscar".
    if (!consolidadoLoaded) setConsolidadoLoading(true);
    try {
      const data = await projecaoService.getConsolidado({ ...buildFilters(), ...(force ? { force_refresh: true } : {}) });
      setConsolidado(data);
      setConsolidadoLoaded(true);
    } catch (error) {
      console.error('Erro ao carregar consolidado:', error);
    } finally {
      setConsolidadoLoading(false);
    }
  };

  const loadAreasDetail = async () => {
    try {
      const [areasData, usersData] = await Promise.all([
        projecaoService.listAreasDetail(),
        usersService.list(),
      ]);
      setAreasDetail(areasData);
      setAllUsers(usersData);
    } catch (error) {
      console.error('Erro ao carregar config de áreas:', error);
    }
  };

  const buildFilters = () => {
    const params: any = {};
    if (filterMes.length > 0) params.mes = filterMes.join(',');
    if (filterTipoEvento.length > 0) params.tipo_evento = filterTipoEvento.join(',');
    if (filterModalidade.length > 0) params.modalidade = filterModalidade.join(',');
    if (filterArea.length > 0) params.area_projecao_id = filterArea.join(',');
    return params;
  };

  const loadPendencias = async () => {
    try {
      const data: PendenciasResponse = await projecaoService.getPendencias();
      // Reset banner dismissal whenever the pendência set actually changes
      // (count or which events are pending), so a new alert breaks through.
      setPendencias(prev => {
        const prevSig = prev
          ? `${prev.total_eventos}|${prev.total_areas}|${prev.pendencias.map((p: PendenciaItem) => `${p.evento_id}:${p.dias_ate_evento}:${p.areas_pendentes.length}`).join(',')}`
          : '';
        const nextSig = `${data.total_eventos}|${data.total_areas}|${data.pendencias.map((p: PendenciaItem) => `${p.evento_id}:${p.dias_ate_evento}:${p.areas_pendentes.length}`).join(',')}`;
        if (prevSig !== nextSig) {
          setPendenciasBannerDismissed(false);
        }
        return data;
      });
    } catch {
    }
  };

  const loadAutoLockConfig = async () => {
    try {
      const data = await projecaoService.getAutoLockConfig();
      setAutoLockConfig(data);
      // Se nunca foi configurado (dias=0, ativo=false), pré-preenche com ativo=true
      // para que o admin apenas precise definir os dias e salvar.
      const neverConfigured = data.dias_antes_evento === 0 && !data.ativo && !data.updated_by_nome;
      setAutoLockDraft({ dias: String(data.dias_antes_evento), hora: data.hora_trava || '00:00', ativo: neverConfigured ? true : data.ativo });
    } catch {
      // silently ignore — config pode não existir ainda
    }
  };

  const saveAutoLockConfig = async () => {
    const dias = parseInt(autoLockDraft.dias, 10);
    if (isNaN(dias) || dias < 0 || dias > 365) {
      showToast('Dias deve ser um número entre 0 e 365');
      return;
    }
    const hora = (autoLockDraft.hora || '00:00').trim();
    if (!/^([01]\d|2[0-3]):([0-5]\d)$/.test(hora)) {
      showToast('Horário deve estar no formato HH:MM (00:00 a 23:59)');
      return;
    }
    setSavingAutoLock(true);
    try {
      const updated = await projecaoService.updateAutoLockConfig({ dias_antes_evento: dias, hora_trava: hora, ativo: autoLockDraft.ativo });
      setAutoLockConfig(updated);
      setAutoLockDraft({ dias: String(updated.dias_antes_evento), hora: updated.hora_trava || '00:00', ativo: updated.ativo });
      showToast('Trava automática atualizada com sucesso', 'success');
    } catch (err: any) {
      showToast(err?.response?.data?.detail || 'Erro ao salvar trava automática');
    } finally {
      setSavingAutoLock(false);
    }
  };

  const loadCorteConfig = async () => {
    try {
      const data = await projecaoService.getCorteConfig();
      setCorteConfig(data);
      setCorteDraft({ dias1: String(data.dias_corte_1), dias2: String(data.dias_corte_2), ativo: data.ativo });
      setAlertaDraft(String(data.dias_alerta_envio ?? 30));
      setNotifDraft({ ativo: !!data.notif_email_ativo, hora: String(data.notif_email_hora ?? 8) });
    } catch {
      // silently ignore — config pode não existir ainda
    }
  };

  const saveAlertaConfig = async () => {
    const dias = parseInt(alertaDraft, 10);
    if (isNaN(dias) || dias < 0 || dias > 365) {
      showToast('Dias deve ser um número entre 0 e 365');
      return;
    }
    setSavingAlerta(true);
    try {
      const updated = await projecaoService.updateAlertaConfig({ dias_alerta_envio: dias });
      setCorteConfig(updated);
      setAlertaDraft(String(updated.dias_alerta_envio));
      showToast('Alerta de ponto de corte atualizado', 'success');
      loadPendencias();
    } catch (err: any) {
      showToast(err?.response?.data?.detail || 'Erro ao salvar alerta de ponto de corte');
    } finally {
      setSavingAlerta(false);
    }
  };

  const saveNotifConfig = async () => {
    const hora = parseInt(notifDraft.hora, 10);
    if (isNaN(hora) || hora < 0 || hora > 23) {
      showToast('Hora deve ser um número entre 0 e 23');
      return;
    }
    setSavingNotif(true);
    try {
      const updated = await projecaoService.updateNotifConfig({ notif_email_ativo: notifDraft.ativo, notif_email_hora: hora });
      setCorteConfig(updated);
      setNotifDraft({ ativo: !!updated.notif_email_ativo, hora: String(updated.notif_email_hora ?? 8) });
      showToast('Notificação por e-mail atualizada', 'success');
    } catch (err: any) {
      showToast(err?.response?.data?.detail || 'Erro ao salvar notificação por e-mail');
    } finally {
      setSavingNotif(false);
    }
  };

  const sendNotifTest = async () => {
    setSendingNotifTest(true);
    try {
      const r = await projecaoService.sendNotifTest();
      const enviados = r?.enviados ?? 0;
      const falhas = r?.falhas ?? 0;
      if (enviados === 0 && falhas === 0) {
        showToast('Nenhuma pendência para notificar hoje (nada enviado).', 'success');
      } else if (falhas > 0) {
        showToast(`Enviados: ${enviados}. Falhas: ${falhas}. ${(r?.erros || []).slice(0, 1).join('') || ''}`.trim());
      } else {
        showToast(`Resumo enviado para ${enviados} destinatário(s).`, 'success');
      }
    } catch (err: any) {
      showToast(err?.response?.data?.detail || 'Erro ao enviar e-mail de teste');
    } finally {
      setSendingNotifTest(false);
    }
  };

  const saveCorteConfig = async () => {
    const d1 = parseInt(corteDraft.dias1, 10);
    const d2 = parseInt(corteDraft.dias2, 10);
    if (isNaN(d1) || d1 < 0 || d1 > 365 || isNaN(d2) || d2 < 0 || d2 > 365) {
      showToast('Dias deve ser um número entre 0 e 365');
      return;
    }
    setSavingCorte(true);
    try {
      const updated = await projecaoService.updateCorteConfig({ dias_corte_1: d1, dias_corte_2: d2, ativo: corteDraft.ativo });
      setCorteConfig(updated);
      setCorteDraft({ dias1: String(updated.dias_corte_1), dias2: String(updated.dias_corte_2), ativo: updated.ativo });
      showToast('Cortes de projeção atualizados com sucesso', 'success');
    } catch (err: any) {
      showToast(err?.response?.data?.detail || 'Erro ao salvar cortes de projeção');
    } finally {
      setSavingCorte(false);
    }
  };

  // Atualiza localmente o card de um corte para refletir a ação na hora, sem
  // depender da recarga (que é reconciliada em seguida). Garante feedback visual
  // instantâneo ao congelar/reabrir.
  const patchCorteLocal = (
    eventoId: number,
    corte: 1 | 2,
    patch: { valor: number | null; congeladoEm: string | null; reabertoManual: boolean },
  ) => {
    setConsolidado(prev => prev.map(c => {
      if (c.evento_id !== eventoId) return c;
      return corte === 1
        ? { ...c, corte_valor_1: patch.valor, corte_congelado_1_em: patch.congeladoEm, reaberto_manual_corte_1: patch.reabertoManual }
        : { ...c, corte_valor_2: patch.valor, corte_congelado_2_em: patch.congeladoEm, reaberto_manual_corte_2: patch.reabertoManual };
    }));
  };

  const handleReabrirCorte = async (eventoId: number, corte: 1 | 2) => {
    setCorteActionBusy(`${eventoId}-${corte}`);
    try {
      await projecaoService.reabrirCorte(eventoId, corte);
      // Atualização otimista: volta a acompanhar ao vivo imediatamente.
      patchCorteLocal(eventoId, corte, { valor: null, congeladoEm: null, reabertoManual: true });
      // A mutação já invalidou o cache no backend; recarga normal (sem
      // force_refresh) recomputa fresco e não cai no rate limit agressivo.
      await loadConsolidado();
      showToast(`Corte ${corte} reaberto`, 'success');
    } catch (err: any) {
      showToast(err?.response?.data?.detail || 'Erro ao reabrir corte');
    } finally {
      setCorteActionBusy(null);
    }
  };

  const handleRecongelarCorte = async (eventoId: number, corte: 1 | 2) => {
    setCorteActionBusy(`${eventoId}-${corte}`);
    try {
      const resp = await projecaoService.recongelarCorte(eventoId, corte);
      // Atualização otimista: já mostra congelado com o valor retornado.
      patchCorteLocal(eventoId, corte, {
        valor: typeof resp?.valor === 'number' ? resp.valor : 0,
        congeladoEm: new Date().toISOString(),
        reabertoManual: false,
      });
      await loadConsolidado();
      showToast(`Corte ${corte} congelado`, 'success');
    } catch (err: any) {
      showToast(err?.response?.data?.detail || 'Erro ao congelar corte');
    } finally {
      setCorteActionBusy(null);
    }
  };


  const toggleAreaCutoffCustomizado = async (area: AreaDetail) => {
    const next = !area.usa_cutoff_customizado;
    try {
      await projecaoService.setAreaCutoffCustomizado(area.id, next);
      showToast(next ? 'Cortes por evento ativados' : 'Cortes por evento desativados', 'success');
      await loadAreasDetail();
      await loadData();
      loadPendencias();
    } catch (err: any) {
      showToast(err?.response?.data?.detail || 'Erro ao atualizar área');
    }
  };

  const loadEventoCutoffs = async (eventoId: number) => {
    const token = ++cutoffsLoadTokenRef.current;
    setEventoCutoffsLoading(true);
    try {
      const data = await projecaoService.listCutoffsEvento(eventoId);
      // Descarta a resposta se outro evento foi selecionado durante a requisição
      if (token !== cutoffsLoadTokenRef.current) return;
      setEventoCutoffs(data);
      const draft: Record<number, { d1: string; d2: string; saida: string }> = {};
      data.forEach((c: CutoffEventoArea) => {
        draft[c.area_projecao_id] = {
          d1: c.data_corte_1 || '',
          d2: c.data_corte_2 || '',
          saida: c.data_saida_caminhao || '',
        };
      });
      setCutoffDraft(draft);
    } catch (err) {
      if (token !== cutoffsLoadTokenRef.current) return;
      console.error('Erro ao carregar cortes do evento:', err);
      setEventoCutoffs([]);
      setCutoffDraft({});
    } finally {
      if (token === cutoffsLoadTokenRef.current) {
        setEventoCutoffsLoading(false);
      }
    }
  };

  const saveEventoCutoff = async (eventoId: number, areaId: number) => {
    const draft = cutoffDraft[areaId] || { d1: '', d2: '', saida: '' };
    setSavingCutoffAreaId(areaId);
    try {
      await projecaoService.upsertCutoffEventoArea({
        evento_id: eventoId,
        area_projecao_id: areaId,
        data_corte_1: draft.d1 || null,
        data_corte_2: draft.d2 || null,
        data_saida_caminhao: draft.saida || null,
      });
      showToast('Datas de corte salvas', 'success');
      await loadEventoCutoffs(eventoId);
      loadPendencias();
    } catch (err: any) {
      showToast(err?.response?.data?.detail || 'Erro ao salvar datas');
    } finally {
      setSavingCutoffAreaId(null);
    }
  };

  const loadLixeira = async () => {
    try {
      const data = await projecaoService.getLixeira();
      setLixeira(data);
    } catch (error) {
      console.error('Erro ao carregar lixeira:', error);
    }
  };

  const handleRestaurar = (id: number) => {
    showConfirm({
      title: 'Restaurar projeção',
      message: 'Deseja restaurar esta projeção? Ela voltará a aparecer na listagem principal.',
      confirmLabel: 'Restaurar',
      variant: 'info',
      onConfirm: async () => {
        try {
          await projecaoService.restaurar(id);
          loadLixeira();
          loadData();
          showToast('Projeção restaurada com sucesso', 'success');
        } catch (error: any) {
          showToast(error.response?.data?.detail || 'Erro ao restaurar');
        }
      },
    });
  };

  const handleDeletePermanente = (id: number) => {
    showConfirm({
      title: 'Exclusão permanente',
      message: 'ATENÇÃO: Esta ação é irreversível. A projeção e todo seu histórico serão excluídos permanentemente.',
      confirmLabel: 'Excluir permanentemente',
      variant: 'danger',
      onConfirm: async () => {
        try {
          await projecaoService.deletePermanente(id);
          loadLixeira();
          showToast('Projeção excluída permanentemente', 'success');
        } catch (error: any) {
          showToast(error.response?.data?.detail || 'Erro ao excluir permanentemente');
        }
      },
    });
  };

  const handleExportar = async () => {
    try {
      await projecaoService.exportar(buildFilters());
    } catch (error) {
      console.error('Erro ao exportar:', error);
      showToast('Erro ao exportar relatório');
    }
  };

  const loadCutoffEnvioMap = async () => {
    try {
      const map = await projecaoService.getCutoffEnvioMap();
      setCutoffEnvioMap(map || {});
    } catch (error) {
      console.error('Erro ao carregar mapa de Data de corte Envio:', error);
    }
  };

  useEffect(() => {
    loadData();
    loadEventos();
    loadCutoffEnvioMap();
  }, []);

  useEffect(() => {
    loadData();
    if (activeTab === 'consolidado') loadConsolidado();
  }, [filterMes, filterTipoEvento, filterModalidade, filterArea]);

  useEffect(() => {
    if (activeTab === 'consolidado') loadConsolidado();
    if (activeTab === 'config' && isAdmin) { loadAreasDetail(); loadAutoLockConfig(); loadCorteConfig(); }
    if (activeTab === 'lixeira' && isAdmin) loadLixeira();
  }, [activeTab]);

  useEffect(() => {
    if (activeTab === 'projecoes' && selectedEvento) {
      loadEventoCutoffs(selectedEvento.id);
    } else {
      cutoffsLoadTokenRef.current += 1;
      setEventoCutoffs([]);
      setCutoffDraft({});
    }
  }, [activeTab, selectedEvento?.id]);

  useEffect(() => {
    if (!selectedEvento) {
      setSelectedEventoCorteSnap(null);
      return;
    }
    let cancelled = false;
    projecaoService.getConsolidado({ evento_id: selectedEvento.id })
      .then((data: ConsolidadoEvento[]) => {
        if (cancelled) return;
        const ev = data[0];
        if (ev) {
          setSelectedEventoCorteSnap({
            congelado_corte_1_em: ev.corte_congelado_1_em ?? null,
            reaberto_manual_corte_1: !!ev.reaberto_manual_corte_1,
            congelado_corte_2_em: ev.corte_congelado_2_em ?? null,
            reaberto_manual_corte_2: !!ev.reaberto_manual_corte_2,
          });
        } else {
          setSelectedEventoCorteSnap(null);
        }
      })
      .catch(() => { if (!cancelled) setSelectedEventoCorteSnap(null); });
    return () => { cancelled = true; };
  }, [selectedEvento?.id]);

  useEffect(() => {
    const eventoId = editingProjecao ? editingProjecao.evento_id : (typeof formEventoId === 'number' ? formEventoId : null);
    const areaId = editingProjecao ? editingProjecao.area_projecao_id : (typeof formAreaId === 'number' ? formAreaId : null);
    const aberto = showCreateModal || !!editingProjecao;
    if (aberto && eventoId != null && areaId != null) {
      let cancelled = false;
      projecaoService.getCamisetaAvulsaInfo(eventoId, areaId)
        .then(info => {
          if (cancelled) return;
          setCamisetaAvulsaInfo(info);
          // Pré-preenche a "Camiseta avulsa" com o teto (Corte 1) quando o
          // campo ainda está vazio ou acima do teto — o usuário só diminui.
          if (info.corte1_congelado && info.teto > 0) {
            setFormKits(prev => prev.map(k => {
              if (k.nome_kit !== KIT_CAMISETA_ORIGEM) return k;
              const atual = parseInt(k.quantidade);
              if (!k.quantidade || isNaN(atual) || atual > info.teto) {
                return { ...k, quantidade: String(info.teto) };
              }
              return k;
            }));
          }
        })
        .catch(() => { if (!cancelled) setCamisetaAvulsaInfo({ corte1_congelado: false, teto: 0 }); });
      return () => { cancelled = true; };
    } else {
      setCamisetaAvulsaInfo({ corte1_congelado: false, teto: 0 });
    }
  }, [showCreateModal, editingProjecao, formEventoId, formAreaId]);

  useEffect(() => {
    loadPendencias();
    loadCorteConfig();
    loadAutoLockConfig();
    const interval = setInterval(() => {
      if (!document.hidden) loadPendencias();
    }, 180000);
    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const pendenciasByEventoId = useMemo(() => {
    const map: Record<number, PendenciaItem> = {};
    if (!pendencias) return map;
    for (const p of pendencias.pendencias) {
      map[p.evento_id] = p;
    }
    return map;
  }, [pendencias]);

  const autoLockedEventoIds = useMemo(() => {
    const ids = new Set<number>();
    if (!autoLockConfig.ativo || autoLockConfig.dias_antes_evento <= 0) return ids;
    const fmt = new Intl.DateTimeFormat('en-CA', {
      timeZone: 'America/Sao_Paulo',
      year: 'numeric', month: '2-digit', day: '2-digit',
    });
    const todayParts = fmt.format(new Date()).split('-').map(Number);
    const todayUtc = Date.UTC(todayParts[0], todayParts[1] - 1, todayParts[2]);
    // Horário atual em BRT (minutos desde 00:00) para comparar no dia exato D-N.
    const nowHm = (() => {
      const t = new Intl.DateTimeFormat('en-GB', {
        timeZone: 'America/Sao_Paulo', hour: '2-digit', minute: '2-digit', hour12: false,
      }).format(new Date());
      const [h, m] = t.split(':').map(Number);
      return (h || 0) * 60 + (m || 0);
    })();
    const [lh, lm] = (autoLockConfig.hora_trava || '00:00').split(':').map(Number);
    const lockHm = (lh || 0) * 60 + (lm || 0);
    for (const ev of eventos) {
      const dateStr = ev.info_geral?.data || ev.data_evento;
      if (!dateStr) continue;
      const datePart = dateStr.slice(0, 10);
      const parts = datePart.split('-').map(Number);
      if (parts.length !== 3 || parts.some(isNaN)) continue;
      const evUtc = Date.UTC(parts[0], parts[1] - 1, parts[2]);
      const dias = Math.round((evUtc - todayUtc) / 86400000);
      if (dias < autoLockConfig.dias_antes_evento) ids.add(ev.id);
      else if (dias === autoLockConfig.dias_antes_evento && nowHm >= lockHm) ids.add(ev.id);
    }
    return ids;
  }, [eventos, autoLockConfig]);

  // "Data de corte Envio" (a mais antiga do evento) — única âncora que o backend
  // usa para disparar os pontos de corte (/projecao/cutoff-envio-map). Carregado
  // junto com os eventos para não depender da aba consolidado estar aberta; o
  // consolidado, quando presente, complementa o mapa. Eventos sem corte de envio
  // ficam de fora e não geram alerta (sem fallback pela data do evento — idêntico
  // ao backend).
  const corteEnvioByEventoId = useMemo(() => {
    const map: Record<number, string> = {};
    for (const [eid, dt] of Object.entries(cutoffEnvioMap)) {
      if (dt) map[Number(eid)] = dt.slice(0, 10);
    }
    for (const c of consolidado) {
      if (c.corte_data_envio && map[c.evento_id] === undefined) {
        map[c.evento_id] = c.corte_data_envio.slice(0, 10);
      }
    }
    return map;
  }, [cutoffEnvioMap, consolidado]);

  const cutoffByEventoId = useMemo(() => {
    const map: Record<number, { dias: number; refDate: string | null }> = {};
    const n = corteConfig.dias_alerta_envio;
    // Alerta desligado quando não há dias configurados.
    if (!n || n <= 0) return map;
    // "Hoje" no fuso de São Paulo (alinha com o backend, que também usa America/Sao_Paulo)
    const fmt = new Intl.DateTimeFormat('en-CA', {
      timeZone: 'America/Sao_Paulo',
      year: 'numeric', month: '2-digit', day: '2-digit',
    });
    const todayParts = fmt.format(new Date()).split('-').map(Number);
    const todayUtc = Date.UTC(todayParts[0], todayParts[1] - 1, todayParts[2]);
    const diasAte = (datePart: string | null | undefined): number | null => {
      if (!datePart) return null;
      const dp = datePart.length >= 10 ? datePart.slice(0, 10) : null;
      if (!dp) return null;
      const parts = dp.split('-').map(Number);
      if (parts.length !== 3 || parts.some(isNaN)) return null;
      const utc = Date.UTC(parts[0], parts[1] - 1, parts[2]);
      return Math.round((utc - todayUtc) / 86400000);
    };
    for (const ev of eventos) {
      // Só consideramos eventos "Em andamento" — alinhado com o backend de pendências.
      // Eventos Concluído/Cancelado não devem disparar ponto de corte.
      if ((ev.status || 'Em andamento') !== 'Em andamento') continue;
      // Âncora ÚNICA: Data de corte Envio do evento. Sem fallback pela data do evento.
      const envio = corteEnvioByEventoId[ev.id] || null;
      if (!envio) continue;
      const dias = diasAte(envio);
      if (dias === null) continue;
      // Dispara somente no dia exato em que faltam N dias para a Data de corte Envio.
      if (dias === n) map[ev.id] = { dias, refDate: envio.slice(0, 10) };
    }
    return map;
  }, [eventos, corteConfig.dias_alerta_envio, corteEnvioByEventoId]);

  const tiposEvento = useMemo(() => {
    const tipos = [...new Set(eventos.map(e => e.tipo_evento).filter(Boolean))] as string[];
    return tipos.sort();
  }, [eventos]);

  const modalidades = useMemo(() => {
    const mods = [...new Set(eventos.map(e => e.modalidade).filter(Boolean))] as string[];
    return mods.sort();
  }, [eventos]);

  const filteredProjecoes = useMemo(() => {
    if (!searchTerm) return projecoes;
    const term = searchTerm.toLowerCase();
    return projecoes.filter(p =>
      p.evento_nome?.toLowerCase().includes(term) ||
      p.area_projecao_nome?.toLowerCase().includes(term)
    );
  }, [projecoes, searchTerm]);

  const eventoStatusById = useMemo(() => {
    const map: Record<number, string> = {};
    for (const e of eventos) map[e.id] = e.status || 'Em andamento';
    return map;
  }, [eventos]);

  const filteredConsolidado = useMemo(() => {
    const term = searchTerm.toLowerCase();
    const base = consolidado.filter(c => {
      if (term && !c.evento_nome?.toLowerCase().includes(term)) return false;
      if (consolidadoStatus && eventoStatusById[c.evento_id] !== consolidadoStatus) return false;
      return true;
    });
    return [...base].sort((a, b) => {
      const av = a.evento_data || '';
      const bv = b.evento_data || '';
      if (!av && !bv) return 0;
      if (!av) return 1;
      if (!bv) return -1;
      return av.localeCompare(bv);
    });
  }, [consolidado, searchTerm, consolidadoStatus, eventoStatusById]);

  const projecoesPorEventoId = useMemo(() => {
    const map: Record<number, Projecao[]> = {};
    for (const p of projecoes) {
      if (!map[p.evento_id]) map[p.evento_id] = [];
      map[p.evento_id].push(p);
    }
    return map;
  }, [projecoes]);

  const eventGroups = useMemo(() => {
    const grouped: Record<number, Projecao[]> = {};
    for (const p of filteredProjecoes) {
      if (!grouped[p.evento_id]) grouped[p.evento_id] = [];
      grouped[p.evento_id].push(p);
    }
    return Object.values(grouped);
  }, [filteredProjecoes]);

  const eventoListOpts = useMemo(() => {
    const modalidades = [...new Set(eventos.map(e => e.modalidade).filter(Boolean))].sort() as string[];
    const cidades = [...new Set(eventos.map(e => e.cidade).filter(Boolean))].sort() as string[];
    const statuses = [...new Set(eventos.map(e => e.status || 'Em andamento').filter(Boolean))].sort() as string[];
    return { modalidades, cidades, statuses };
  }, [eventos]);

  const filteredEventosList = useMemo(() => {
    const term = eventoListSearch.toLowerCase();
    return eventos.filter(e => {
      if (term && !e.nome?.toLowerCase().includes(term) && !e.cidade?.toLowerCase().includes(term) && !e.tipo_evento?.toLowerCase().includes(term)) return false;
      if (eventoListModalidade && e.modalidade !== eventoListModalidade) return false;
      if (eventoListCidade && e.cidade !== eventoListCidade) return false;
      if (eventoListStatus && (e.status || 'Em andamento') !== eventoListStatus) return false;
      if (eventoListMes) {
        const dateStr = e.info_geral?.data || e.data_evento;
        if (!dateStr) return false;
        const month = String(new Date(dateStr + (dateStr.length === 10 ? 'T00:00:00' : '')).getMonth() + 1);
        if (month !== eventoListMes) return false;
      }
      if (eventoListOnlyCutoff && !cutoffByEventoId[e.id]) return false;
      if (eventoListOnlyLocked && !autoLockedEventoIds.has(e.id)) return false;
      return true;
    });
  }, [eventos, eventoListSearch, eventoListMes, eventoListModalidade, eventoListCidade, eventoListStatus, eventoListOnlyCutoff, eventoListOnlyLocked, cutoffByEventoId, autoLockedEventoIds]);

  const sortedEventosList = useMemo(() => {
    const { field, dir } = eventoListSort;
    const mul = dir === 'asc' ? 1 : -1;
    return [...filteredEventosList].sort((a, b) => {
      let av = '', bv = '';
      if (field === 'nome') { av = a.nome || ''; bv = b.nome || ''; }
      else if (field === 'data') { av = a.info_geral?.data || a.data_evento || ''; bv = b.info_geral?.data || b.data_evento || ''; }
      else if (field === 'modalidade') { av = a.modalidade || ''; bv = b.modalidade || ''; }
      else if (field === 'cidade') { av = a.cidade || ''; bv = b.cidade || ''; }
      else if (field === 'status') { av = a.status || ''; bv = b.status || ''; }
      else if (field === 'projecoes') {
        return mul * ((projecoesPorEventoId[a.id]?.length || 0) - (projecoesPorEventoId[b.id]?.length || 0));
      }
      return mul * av.localeCompare(bv, 'pt-BR');
    });
  }, [filteredEventosList, eventoListSort, projecoesPorEventoId]);

  const toggleEventoSort = (field: string) => {
    setEventoListSort(prev => prev.field === field ? { field, dir: prev.dir === 'asc' ? 'desc' : 'asc' } : { field, dir: 'asc' });
  };

  const toggleProjecaoSort = (field: string) => {
    setProjecaoSort(prev => prev.field === field ? { field, dir: prev.dir === 'asc' ? 'desc' : 'asc' } : { field, dir: field === 'quantidade' ? 'desc' : 'asc' });
  };

  const sortProjecaoGroup = (group: Projecao[]): Projecao[] => {
    const { field, dir } = projecaoSort;
    const mult = dir === 'asc' ? 1 : -1;
    const ts = (s?: string | null) => s ? new Date(s).getTime() : 0;
    return [...group].sort((a, b) => {
      switch (field) {
        case 'area':
          return mult * (a.area_projecao_nome || '').localeCompare(b.area_projecao_nome || '', 'pt-BR');
        case 'quantidade':
          return mult * ((a.quantidade || 0) - (b.quantidade || 0));
        case 'criado': {
          const cmp = (a.created_by_nome || '').localeCompare(b.created_by_nome || '', 'pt-BR');
          return mult * (cmp !== 0 ? cmp : ts(a.created_at) - ts(b.created_at));
        }
        case 'ultima': {
          const aT = ts(a.locked_at) || ts(a.updated_at);
          const bT = ts(b.locked_at) || ts(b.updated_at);
          return mult * (aT - bT);
        }
        default:
          return 0;
      }
    });
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    const qty = parseInt(formQuantidade);
    if (!formEventoId || !formAreaId || !qty || qty <= 0) {
      showToast('Informe uma quantidade válida (maior que zero).');
      return;
    }
    if (formTemCliente) {
      const clientesValidos = formClientes.filter(c => c.nome_cliente.trim() && parseInt(c.quantidade) > 0);
      if (clientesValidos.length === 0) {
        showToast('Adicione ao menos um cliente com nome e quantidade válidos.');
        return;
      }
      const somaClientes = clientesValidos.reduce((s, c) => s + parseInt(c.quantidade), 0);
      if (somaClientes !== qty) {
        showToast(`A soma das quantidades por cliente (${somaClientes}) deve ser igual à quantidade total (${qty}).`);
        return;
      }
    }
    if (formTemKit) {
      const kitsValidos = formKits.filter(k => k.nome_kit.trim() && parseInt(k.quantidade) > 0);
      if (kitsValidos.length === 0) {
        showToast('Informe a quantidade de pelo menos um Kit.');
        return;
      }
      const somaKits = kitsValidos.reduce((s, k) => s + parseInt(k.quantidade), 0);
      if (somaKits !== qty) {
        showToast(`A soma das quantidades por Kit (${somaKits}) deve ser igual à quantidade total (${qty}).`);
        return;
      }
    }
    try {
      const clientes = formTemCliente
        ? formClientes
            .filter(c => c.nome_cliente.trim() && parseInt(c.quantidade) > 0)
            .map(c => ({ nome_cliente: c.nome_cliente.trim(), quantidade: parseInt(c.quantidade) }))
        : undefined;
      const kits = formTemKit
        ? formKits
            .filter(k => k.nome_kit.trim() && parseInt(k.quantidade) > 0)
            .map(k => ({ nome_kit: k.nome_kit.trim(), quantidade: parseInt(k.quantidade) }))
        : undefined;
      await projecaoService.create({
        evento_id: formEventoId as number,
        area_projecao_id: formAreaId as number,
        quantidade: qty,
        clientes,
        kits,
      });
      setShowCreateModal(false);
      resetForm();
      loadData();
    } catch (error: any) {
      showToast(error.response?.data?.detail || 'Erro ao criar projeção');
    }
  };

  const handleUpdate = async (e: React.FormEvent) => {
    e.preventDefault();
    const qty = parseInt(formQuantidade);
    if (!editingProjecao || !qty || qty <= 0) {
      showToast('Informe uma quantidade válida (maior que zero).');
      return;
    }
    const c1Ready = !!corte1Dist && corte1Dist.evento_id === editingProjecao.evento_id && corte1Dist.area_projecao_id === editingProjecao.area_projecao_id;
    if (corteLoading || corte1DistError || (editCorte2 && !c1Ready)) {
      showToast('Aguarde o carregamento dos dados do corte antes de salvar.');
      return;
    }
    if (editCorte2 && c1Ready) {
      if ((corte1Dist?.kits?.length ?? 0) > 0 && !formTemKit) {
        showToast('No Corte 2, a distribuição por Kit do Corte 1 deve ser preservada (só recebe adições).');
        return;
      }
      if ((corte1Dist?.clientes?.length ?? 0) > 0 && !formTemCliente) {
        showToast('No Corte 2, a distribuição por cliente do Corte 1 deve ser preservada (só recebe adições).');
        return;
      }
    }
    if (formTemCliente) {
      const clientesValidos = formClientes.filter(c => c.nome_cliente.trim() && parseInt(c.quantidade) > 0);
      if (clientesValidos.length === 0) {
        showToast('Adicione ao menos um cliente com nome e quantidade válidos.');
        return;
      }
      const somaClientes = clientesValidos.reduce((s, c) => s + parseInt(c.quantidade), 0);
      if (somaClientes !== qty) {
        showToast(`A soma das quantidades por cliente (${somaClientes}) deve ser igual à quantidade total (${qty}).`);
        return;
      }
    }
    if (formTemKit) {
      const kitsValidos = formKits.filter(k => k.nome_kit.trim() && parseInt(k.quantidade) > 0);
      if (kitsValidos.length === 0) {
        showToast('Informe a quantidade de pelo menos um Kit.');
        return;
      }
      const somaKits = kitsValidos.reduce((s, k) => s + parseInt(k.quantidade), 0);
      if (somaKits !== qty) {
        showToast(`A soma das quantidades por Kit (${somaKits}) deve ser igual à quantidade total (${qty}).`);
        return;
      }
    }
    try {
      const clientes = formTemCliente
        ? formClientes
            .filter(c => c.nome_cliente.trim() && parseInt(c.quantidade) > 0)
            .map(c => ({ nome_cliente: c.nome_cliente.trim(), quantidade: parseInt(c.quantidade) }))
        : [];
      const kits = formTemKit
        ? formKits
            .filter(k => k.nome_kit.trim() && parseInt(k.quantidade) > 0)
            .map(k => ({ nome_kit: k.nome_kit.trim(), quantidade: parseInt(k.quantidade) }))
        : [];
      await projecaoService.update(editingProjecao.id, { quantidade: qty, clientes, kits });
      setEditingProjecao(null);
      resetForm();
      loadData();
    } catch (error: any) {
      showToast(error.response?.data?.detail || 'Erro ao atualizar projeção');
    }
  };

  const handleDelete = (id: number) => {
    showConfirm({
      title: 'Excluir projeção',
      message: 'Deseja realmente excluir esta projeção? Ela será movida para a lixeira.',
      confirmLabel: 'Excluir',
      variant: 'warning',
      onConfirm: async () => {
        try {
          await projecaoService.delete(id);
          loadData();
          showToast('Projeção excluída com sucesso', 'success');
        } catch (error: any) {
          showToast(error.response?.data?.detail || 'Erro ao excluir');
        }
      },
    });
  };

  const handleToggleLock = (eventoId: number, allLocked: boolean) => {
    const label = allLocked ? 'Destravar' : 'Travar';
    const msg = allLocked
      ? 'Deseja destravar todas as projeções deste evento? Edições voltarão a ser permitidas.'
      : 'Deseja travar todas as projeções deste evento? Não será mais possível editar ou excluir os números.';
    showConfirm({
      title: `${label} projeções do evento`,
      message: msg,
      confirmLabel: label,
      variant: allLocked ? 'warning' : 'info',
      onConfirm: async () => {
        setLockingEventoId(eventoId);
        try {
          await projecaoService.toggleLock(eventoId);
          await loadData();
          showToast(allLocked ? 'Projeções destravadas com sucesso' : 'Projeções travadas com sucesso', 'success');
        } catch (error: any) {
          showToast(error.response?.data?.detail || 'Erro ao alterar travamento');
        } finally {
          setLockingEventoId(null);
        }
      },
    });
  };

  const openHistorico = async (p: Projecao) => {
    try {
      const data = await projecaoService.getHistorico(p.id);
      setHistorico(data);
      setHistoricoProjecao(p);
      setShowHistorico(true);
    } catch (error) {
      console.error('Erro ao carregar histórico:', error);
    }
  };

  const loadCorteInfo = (evento_id: number, area_projecao_id: number) => {
    const reqId = ++corte1DistReqRef.current;
    setCorteLoading(true);
    setEditCorte2(false);
    setCorte1Dist(null);
    setCorte1DistError(false);
    projecaoService.getCorte1Distribuicao(evento_id, area_projecao_id)
      .then(d => {
        if (corte1DistReqRef.current !== reqId) return;
        setEditCorte2(!!d.em_corte2);
        setCorte1Dist({ evento_id, area_projecao_id, quantidade: d.quantidade, kits: d.kits, clientes: d.clientes, fonte: d.fonte });
        setCorteLoading(false);
      })
      .catch(() => {
        if (corte1DistReqRef.current !== reqId) return;
        setCorte1DistError(true);
        setCorteLoading(false);
      });
  };

  const openEdit = (p: Projecao) => {
    setEditingProjecao(p);
    setFormQuantidade(String(p.quantidade));
    loadCorteInfo(p.evento_id, p.area_projecao_id);
    if (p.clientes && p.clientes.length > 0) {
      setFormTemCliente(true);
      setFormClientes(p.clientes.map(c => ({ nome_cliente: c.nome_cliente, quantidade: String(c.quantidade) })));
    } else {
      setFormTemCliente(false);
      setFormClientes([{ nome_cliente: '', quantidade: '' }]);
    }
    if (p.kits && p.kits.length > 0) {
      setFormTemKit(true);
      const savedByName = new Map(p.kits.map(k => [k.nome_kit, k.quantidade]));
      setFormKits(KITS_PADRAO.map(nome => ({
        nome_kit: nome,
        quantidade: savedByName.has(nome) ? String(savedByName.get(nome)) : '',
      })));
    } else {
      setFormTemKit(false);
      setFormKits(buildKitsPadrao());
    }
  };

  const resetForm = () => {
    setFormEventoId(selectedEvento ? selectedEvento.id : '');
    setFormAreaId('');
    setFormQuantidade('');
    setFormTemCliente(false);
    setFormClientes([{ nome_cliente: '', quantidade: '' }]);
    setFormTemKit(false);
    setFormKits(buildKitsPadrao());
    setEventoSearchTerm('');
    setShowEventoDropdown(false);
    setEditCorte2(false);
    setCorte1Dist(null);
    setCorte1DistError(false);
    setCorteLoading(false);
  };

  const addCliente = () => {
    setFormClientes(prev => [...prev, { nome_cliente: '', quantidade: '' }]);
  };

  const removeCliente = (idx: number) => {
    setFormClientes(prev => prev.filter((_, i) => i !== idx));
  };

  const updateCliente = (idx: number, field: keyof ClienteItem, value: string) => {
    setFormClientes(prev => prev.map((c, i) => i === idx ? { ...c, [field]: value } : c));
  };

  const addKit = () => {
    setFormKits(prev => [...prev, { nome_kit: '', quantidade: '' }]);
  };

  const removeKit = (idx: number) => {
    setFormKits(prev => prev.filter((_, i) => i !== idx));
  };

  const updateKit = (idx: number, field: keyof KitItem, value: string) => {
    setFormKits(prev => {
      const updated = prev.map((k, i) => i === idx ? { ...k, [field]: value } : k);
      if (emCorte2 && formTemKit && field === 'quantidade') {
        const total = updated.reduce((sum, k) => sum + (parseInt(k.quantidade) || 0), 0);
        setFormQuantidade(String(total));
      }
      return updated;
    });
  };

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (eventoDropdownRef.current && !eventoDropdownRef.current.contains(e.target as Node)) {
        setShowEventoDropdown(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const filteredEventos = useMemo(() => {
    if (!eventoSearchTerm) return eventos;
    const term = eventoSearchTerm.toLowerCase();
    return eventos.filter(ev => ev.nome.toLowerCase().includes(term));
  }, [eventos, eventoSearchTerm]);

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return '-';
    try {
      return new Date(dateStr + 'T00:00:00').toLocaleDateString('pt-BR');
    } catch {
      return dateStr;
    }
  };

  const formatDateTime = (dateStr: string | null) => {
    if (!dateStr) return '-';
    try {
      return new Date(dateStr).toLocaleString('pt-BR');
    } catch {
      return dateStr;
    }
  };

  const formatNumber = (n: number) => n.toLocaleString('pt-BR');
  const formatMilhar = (v: string | number) => {
    const s = String(v ?? '');
    const neg = s.trim().startsWith('-');
    const digits = s.replace(/\D/g, '');
    if (!digits) return neg ? '-' : '';
    return (neg ? '-' : '') + parseInt(digits, 10).toLocaleString('pt-BR');
  };
  const stripMilhar = (v: string) => {
    const neg = v.trim().startsWith('-');
    const digits = v.replace(/\D/g, '');
    return (neg ? '-' : '') + digits;
  };

  const selectedEventoNome = useMemo(() => {
    if (!formEventoId) return '';
    const ev = eventos.find(e => e.id === formEventoId);
    return ev ? `${ev.nome}${ev.info_geral?.data ? ` (${formatDate(ev.info_geral.data)})` : ''}` : '';
  }, [formEventoId, eventos]);

  const openAtribuir = (area: AreaDetail) => {
    setAtribuirArea(area);
    setSelectedUserIds(area.usuarios.map(u => u.usuario_id));
    setShowAtribuirModal(true);
  };

  const handleAtribuir = async () => {
    if (!atribuirArea) return;
    try {
      await projecaoService.atribuirUsuarios({
        area_projecao_id: atribuirArea.id,
        usuario_ids: selectedUserIds,
      });
      setShowAtribuirModal(false);
      loadAreasDetail();
    } catch (error: any) {
      showToast(error.response?.data?.detail || 'Erro ao atribuir usuários');
    }
  };

  const handleCreateArea = async (e: React.FormEvent) => {
    e.preventDefault();
    const nome = newAreaNome.trim();
    if (!nome) {
      showToast('Informe o nome da área.');
      return;
    }
    try {
      await projecaoService.createArea(nome);
      setShowCreateAreaModal(false);
      setNewAreaNome('');
      loadAreasDetail();
      loadData();
      showToast('Área criada com sucesso', 'success');
    } catch (error: any) {
      showToast(error.response?.data?.detail || 'Erro ao criar área');
    }
  };

  const toggleConsolidado = (eventoId: number) => {
    setExpandedConsolidado(prev => {
      const next = new Set(prev);
      if (next.has(eventoId)) next.delete(eventoId);
      else next.add(eventoId);
      return next;
    });
  };

  if (!hasAccess) {
    return (
      <div className={`p-8 text-center ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>
        <p className="text-lg">Você não tem permissão para acessar esta página.</p>
      </div>
    );
  }

  const corte1DistReady = !!corte1Dist && !!editingProjecao
    && corte1Dist.evento_id === editingProjecao.evento_id
    && corte1Dist.area_projecao_id === editingProjecao.area_projecao_id;
  const emCorte2 = editCorte2 && corte1DistReady;
  const editGateBlocked = corteLoading || corte1DistError || (editCorte2 && !corte1DistReady);
  const c1Qty = corte1DistReady ? (corte1Dist?.quantidade ?? 0) : 0;
  const c1KitMap = new Map<string, number>();
  if (corte1DistReady) {
    (corte1Dist?.kits ?? []).forEach(k => c1KitMap.set(k.nome_kit, (c1KitMap.get(k.nome_kit) ?? 0) + k.quantidade));
  }
  const c1CliMap = new Map<string, number>();
  if (corte1DistReady) {
    (corte1Dist?.clientes ?? []).forEach(c => c1CliMap.set(c.nome_cliente, (c1CliMap.get(c.nome_cliente) ?? 0) + c.quantidade));
  }
  const c2BoxRead = isDark ? 'bg-gray-900/40 border-gray-700 text-gray-300' : 'bg-gray-100 border-gray-200 text-gray-600';

  return (
    <div className="min-h-screen">
      <div className="fixed inset-0 pointer-events-none overflow-hidden">
        <div className="absolute top-0 left-1/4 w-96 h-96 bg-violet-500/10 rounded-full blur-3xl animate-pulse" />
        <div className="absolute bottom-0 right-1/4 w-96 h-96 bg-blue-500/10 rounded-full blur-3xl animate-pulse" style={{ animationDelay: '1s' }} />
      </div>

      <div className="relative z-10 space-y-6 p-6">
        {/* Header */}
        <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-xl bg-gradient-to-br from-violet-500 to-blue-500 shadow-lg shadow-violet-500/30">
              <BarChart3 className="w-6 h-6 text-white" />
            </div>
            <div>
              <h1 className={`text-3xl font-black tracking-tight ${isDark ? 'text-white' : 'text-gray-900'}`}>
                Projeção de
                <span className="bg-gradient-to-r from-violet-400 via-blue-500 to-cyan-500 bg-clip-text text-transparent"> Inscritos</span>
              </h1>
              <p className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>
                Gerencie as projeções de inscritos por evento e área
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            {(activeTab === 'projecoes' || activeTab === 'consolidado') && (
              <button
                onClick={handleExportar}
                className={`flex items-center gap-2 px-4 py-3 rounded-2xl font-semibold text-sm transition-all duration-300 hover:scale-105 ${isDark ? 'bg-gray-700/60 text-gray-200 hover:bg-gray-600/80 border border-gray-600' : 'bg-white text-gray-700 hover:bg-gray-50 border border-gray-300 shadow-sm'}`}
              >
                <Download className="w-4 h-4" />
                Exportar CSV
              </button>
            )}
            {activeTab === 'projecoes' && canCreateProjecao && selectedEvento && (() => {
              const corteSnap = selectedEventoCorteSnap;
              const corte2Frozen = !!(corteSnap?.congelado_corte_2_em) && !corteSnap?.reaberto_manual_corte_2;
              const corte1Frozen = !!(corteSnap?.congelado_corte_1_em) && !corteSnap?.reaberto_manual_corte_1;
              const corteFrozen = !isAdmin && (corte2Frozen || corte1Frozen);
              const corteLabel = corte2Frozen ? 'Corte 2' : 'Corte 1';
              const corteDate = corte2Frozen
                ? (corteSnap?.congelado_corte_2_em ? new Date(corteSnap.congelado_corte_2_em).toLocaleDateString('pt-BR') : '')
                : (corteSnap?.congelado_corte_1_em ? new Date(corteSnap.congelado_corte_1_em).toLocaleDateString('pt-BR') : '');

              if (!isAdmin && autoLockedEventoIds.has(selectedEvento.id)) {
                return (
                  <div
                    title={`Trava automática ativa: D-${autoLockConfig.dias_antes_evento}`}
                    className="flex items-center gap-2 px-6 py-3 rounded-2xl font-semibold text-sm cursor-not-allowed bg-amber-500/20 text-amber-400 border border-amber-500/40"
                  >
                    <Lock className="w-4 h-4" />
                    Evento travado (D-{autoLockConfig.dias_antes_evento})
                  </div>
                );
              }
              if (corteFrozen) {
                return (
                  <div
                    title={`${corteLabel} congelado em ${corteDate} — novas projeções não são permitidas`}
                    className="flex items-center gap-2 px-6 py-3 rounded-2xl font-semibold text-sm cursor-not-allowed bg-rose-500/20 text-rose-400 border border-rose-500/40"
                  >
                    <Lock className="w-4 h-4" />
                    {corteLabel} congelado
                  </div>
                );
              }
              return (
                <button
                  onClick={() => { resetForm(); setFormEventoId(selectedEvento.id); setShowCreateModal(true); }}
                  className="group relative px-6 py-3 bg-gradient-to-r from-violet-600 via-blue-600 to-cyan-500 text-white rounded-2xl font-semibold shadow-xl shadow-violet-500/30 hover:shadow-violet-500/50 transition-all duration-300 hover:scale-105 overflow-hidden"
                >
                  <div className="absolute inset-0 bg-gradient-to-r from-violet-400 via-blue-400 to-cyan-400 opacity-0 group-hover:opacity-100 transition-opacity duration-300" />
                  <span className="relative flex items-center gap-2">
                    <Plus className="w-5 h-5" />
                    Nova Projeção
                  </span>
                </button>
              );
            })()}
          </div>
        </div>

        {/* Tabs */}
        <div className="flex gap-2">
          {[
            { key: 'projecoes' as const, label: 'Projeções', icon: BarChart3 },
            { key: 'consolidado' as const, label: 'Visão Consolidada', icon: Eye },
            ...(isAdmin ? [
              { key: 'config' as const, label: 'Configurações', icon: Settings },
              { key: 'lixeira' as const, label: 'Lixeira', icon: Trash },
            ] : []),
          ].map(tab => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-semibold transition-all ${
                activeTab === tab.key
                  ? 'bg-gradient-to-r from-violet-600 to-blue-600 text-white shadow-lg shadow-violet-500/30'
                  : isDark ? 'bg-gray-800/50 text-gray-400 hover:text-white hover:bg-gray-700/50' : 'bg-white/70 text-gray-600 hover:text-gray-900 hover:bg-gray-100'
              }`}
            >
              <tab.icon className="w-4 h-4" />
              {tab.label}
            </button>
          ))}
        </div>

        {/* Filters */}
        {(activeTab === 'consolidado' || (activeTab === 'projecoes' && selectedEvento)) && (
          <div className={`flex flex-wrap items-center gap-3 p-4 rounded-2xl ${isDark ? 'bg-gray-800/30 border border-gray-700/50' : 'bg-white/50 border border-gray-200'}`}>
            <Filter className={`w-4 h-4 ${isDark ? 'text-gray-400' : 'text-gray-500'}`} />
            <MultiSelectDropdown
              options={mesesOptions}
              selected={filterMes}
              onChange={setFilterMes}
              placeholder="Todos os meses"
              isDark={isDark}
            />
            <MultiSelectDropdown
              options={tiposEvento.map(t => ({ value: t, label: t }))}
              selected={filterTipoEvento}
              onChange={setFilterTipoEvento}
              placeholder="Todos os tipos"
              isDark={isDark}
            />
            <MultiSelectDropdown
              options={modalidades.map(m => ({ value: m, label: m }))}
              selected={filterModalidade}
              onChange={setFilterModalidade}
              placeholder="Todas as modalidades"
              isDark={isDark}
            />
            <MultiSelectDropdown
              options={areas.map(a => ({ value: String(a.id), label: a.nome }))}
              selected={filterArea}
              onChange={setFilterArea}
              placeholder="Todas as áreas"
              isDark={isDark}
            />
            {activeTab === 'consolidado' && (
              <div className="relative">
                <select
                  value={consolidadoStatus}
                  onChange={e => setConsolidadoStatus(e.target.value)}
                  className={`${selectClass} pr-8 appearance-none cursor-pointer`}
                >
                  <option value="">Todos status</option>
                  {eventoListOpts.statuses.map(s => <option key={s} value={s}>{s}</option>)}
                </select>
                <ChevronDown className={`pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 ${isDark ? 'text-gray-400' : 'text-gray-500'}`} />
              </div>
            )}
            <div className="relative flex-1 min-w-[200px]">
              <Search className={`absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 ${isDark ? 'text-gray-400' : 'text-gray-500'}`} />
              <input
                type="text"
                placeholder="Buscar evento..."
                value={searchTerm}
                onChange={e => setSearchTerm(e.target.value)}
                className={`${selectClass} pl-9 w-full`}
              />
            </div>
            {(filterMes.length > 0 || filterTipoEvento.length > 0 || filterModalidade.length > 0 || filterArea.length > 0 || searchTerm || (activeTab === 'consolidado' && consolidadoStatus !== 'Em andamento')) && (
              <button
                type="button"
                onClick={() => { setFilterMes([]); setFilterTipoEvento([]); setFilterModalidade([]); setFilterArea([]); setSearchTerm(''); setConsolidadoStatus('Em andamento'); }}
                className={`flex items-center gap-1.5 px-3 py-2 rounded-xl text-xs font-semibold transition-all hover:scale-105 ${
                  isDark ? 'bg-red-500/15 text-red-400 hover:bg-red-500/25 border border-red-500/30' : 'bg-red-50 text-red-600 hover:bg-red-100 border border-red-200'
                }`}
              >
                <X className="w-3.5 h-3.5" />
                Limpar filtros
              </button>
            )}
          </div>
        )}

        {/* Content */}
        {activeTab === 'projecoes' && !selectedEvento && pendencias && pendencias.total_eventos > 0 && !pendenciasBannerDismissed && (
          /* ── Pendências banner ── */
          <div className={`relative overflow-hidden rounded-2xl border ${isDark ? 'bg-gradient-to-r from-red-500/10 via-orange-500/10 to-red-500/5 border-red-500/40' : 'bg-gradient-to-r from-red-50 via-orange-50 to-red-50/50 border-red-200'}`}>
            <div className="flex items-start gap-3 p-4">
              <div className={`flex items-center justify-center w-10 h-10 rounded-xl flex-shrink-0 ${isDark ? 'bg-red-500/20' : 'bg-red-100'}`}>
                <Bell className={`w-5 h-5 ${isDark ? 'text-red-400' : 'text-red-600'} animate-pulse`} />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <h3 className={`text-sm font-bold ${isDark ? 'text-red-300' : 'text-red-800'}`}>
                    {pendencias.total_eventos} evento{pendencias.total_eventos !== 1 ? 's' : ''} em ponto de corte sem projeção
                  </h3>
                  <span className={`inline-flex px-2 py-0.5 rounded-full text-[10px] font-bold ${isDark ? 'bg-red-500/30 text-red-200' : 'bg-red-200 text-red-800'}`}>
                    {pendencias.total_areas} pendência{pendencias.total_areas !== 1 ? 's' : ''} de área
                  </span>
                </div>
                <p className={`text-xs mt-1 ${isDark ? 'text-red-200/80' : 'text-red-700'}`}>
                  Os eventos abaixo estão exatamente em um ponto de corte hoje (D-N contado a partir da Data de corte Envio) e ainda não têm projeção registrada para áreas que você pode editar.
                </p>
                <div className="flex flex-wrap gap-2 mt-2.5">
                  {pendencias.pendencias.slice(0, 6).map(p => (
                    <button
                      key={p.evento_id}
                      onClick={() => {
                        const ev = eventos.find(e => e.id === p.evento_id);
                        if (ev) setSelectedEvento(ev);
                      }}
                      className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-semibold transition-all ${
                        isDark ? 'bg-red-500/20 text-red-300 hover:bg-red-500/30 border border-red-500/40' : 'bg-red-100 text-red-700 hover:bg-red-200 border border-red-300'
                      }`}
                      title={`${p.evento_nome} — ${p.cutoff_customizado ? `Corte ${formatDate(p.cutoff_data || null)}` : `D-${p.dias_ate_evento}`} • ${p.areas_pendentes.map(a => a.area_projecao_nome).join(', ')}`}
                    >
                      {p.cutoff_customizado ? <Clock className="w-3 h-3" /> : <Zap className="w-3 h-3" />}
                      <span className="truncate max-w-[180px]">{p.evento_nome}</span>
                      {p.cutoff_customizado ? (
                        <span className="font-mono opacity-80">{formatDate(p.cutoff_data || null)}</span>
                      ) : (
                        <span className="font-mono opacity-80">D-{p.dias_ate_evento}</span>
                      )}
                    </button>
                  ))}
                  {pendencias.pendencias.length > 6 && (
                    <span className={`px-2.5 py-1 text-xs font-semibold ${isDark ? 'text-red-300' : 'text-red-700'}`}>
                      +{pendencias.pendencias.length - 6} evento{pendencias.pendencias.length - 6 !== 1 ? 's' : ''}
                    </span>
                  )}
                </div>
              </div>
              <button
                onClick={() => setPendenciasBannerDismissed(true)}
                title="Dispensar até a próxima atualização"
                className={`p-1.5 rounded-lg flex-shrink-0 transition-colors ${isDark ? 'text-red-300 hover:bg-red-500/20' : 'text-red-600 hover:bg-red-100'}`}
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}

        {activeTab === 'projecoes' && !selectedEvento && (
          /* ── Events master table ── */
          <div className={`rounded-2xl overflow-hidden ${isDark ? 'bg-gray-800/50 backdrop-blur-xl border border-gray-700/50' : 'bg-white/70 backdrop-blur-xl border border-gray-200'}`}>
            {/* Events filter bar */}
            {(() => {
              const selClass = `h-9 pl-3 pr-8 rounded-xl border text-sm appearance-none cursor-pointer focus:outline-none focus:ring-2 focus:ring-violet-500 ${isDark ? 'bg-gray-900/50 border-gray-600 text-white' : 'bg-gray-50 border-gray-200 text-gray-900'}`;
              const hasFilters = eventoListSearch || eventoListMes || eventoListModalidade || eventoListCidade || eventoListStatus !== 'Em andamento' || eventoListOnlyCutoff || eventoListOnlyLocked;
              const cutoffCount = Object.keys(cutoffByEventoId).length;
              const lockedCount = autoLockedEventoIds.size;
              return (
                <div className={`flex flex-wrap items-center gap-2 p-4 border-b ${isDark ? 'border-gray-700/50' : 'border-gray-200'}`}>
                  {/* Search */}
                  <div className="relative">
                    <Search className={`absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 ${isDark ? 'text-gray-400' : 'text-gray-500'}`} />
                    <input
                      type="text"
                      placeholder="Buscar evento..."
                      value={eventoListSearch}
                      onChange={e => setEventoListSearch(e.target.value)}
                      className={`pl-9 pr-3 h-9 w-48 rounded-xl border text-sm ${isDark ? 'bg-gray-900/50 border-gray-600 text-white placeholder-gray-500' : 'bg-gray-50 border-gray-200 text-gray-900 placeholder-gray-400'} focus:outline-none focus:ring-2 focus:ring-violet-500`}
                    />
                  </div>

                  {/* Mês */}
                  <div className="relative">
                    <select value={eventoListMes} onChange={e => setEventoListMes(e.target.value)} className={selClass}>
                      <option value="">Todos os meses</option>
                      {['Janeiro','Fevereiro','Março','Abril','Maio','Junho','Julho','Agosto','Setembro','Outubro','Novembro','Dezembro'].map((m, i) => (
                        <option key={i+1} value={String(i+1)}>{m}</option>
                      ))}
                    </select>
                    <ChevronDown className={`pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 ${isDark ? 'text-gray-400' : 'text-gray-500'}`} />
                  </div>

                  {/* Modalidade */}
                  <div className="relative">
                    <select value={eventoListModalidade} onChange={e => setEventoListModalidade(e.target.value)} className={selClass}>
                      <option value="">Todas modalidades</option>
                      {eventoListOpts.modalidades.map(m => <option key={m} value={m}>{m}</option>)}
                    </select>
                    <ChevronDown className={`pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 ${isDark ? 'text-gray-400' : 'text-gray-500'}`} />
                  </div>

                  {/* Cidade */}
                  <div className="relative">
                    <select value={eventoListCidade} onChange={e => setEventoListCidade(e.target.value)} className={selClass}>
                      <option value="">Todas cidades</option>
                      {eventoListOpts.cidades.map(c => <option key={c} value={c}>{c}</option>)}
                    </select>
                    <ChevronDown className={`pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 ${isDark ? 'text-gray-400' : 'text-gray-500'}`} />
                  </div>

                  {/* Status */}
                  <div className="relative">
                    <select value={eventoListStatus} onChange={e => setEventoListStatus(e.target.value)} className={selClass}>
                      <option value="">Todos status</option>
                      {eventoListOpts.statuses.map(s => <option key={s} value={s}>{s}</option>)}
                    </select>
                    <ChevronDown className={`pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 ${isDark ? 'text-gray-400' : 'text-gray-500'}`} />
                  </div>

                  {/* Apenas em ponto de corte */}
                  <button
                    onClick={() => setEventoListOnlyCutoff(v => !v)}
                    disabled={cutoffCount === 0 && !eventoListOnlyCutoff}
                    title={cutoffCount === 0 ? 'Nenhum evento está em ponto de corte hoje' : 'Mostrar apenas eventos em ponto de corte hoje'}
                    className={`flex items-center gap-1.5 h-9 px-3 rounded-xl text-xs font-semibold transition-all border ${
                      eventoListOnlyCutoff
                        ? isDark ? 'bg-rose-500/25 text-rose-200 border-rose-500/50' : 'bg-rose-100 text-rose-700 border-rose-300'
                        : cutoffCount === 0
                          ? isDark ? 'bg-gray-800/30 text-gray-600 border-gray-700/40 cursor-not-allowed' : 'bg-gray-100 text-gray-400 border-gray-200 cursor-not-allowed'
                          : isDark ? 'bg-gray-900/50 text-gray-300 border-gray-600 hover:bg-rose-500/15 hover:text-rose-300 hover:border-rose-500/40' : 'bg-gray-50 text-gray-700 border-gray-200 hover:bg-rose-50 hover:text-rose-700 hover:border-rose-300'
                    }`}
                  >
                    <Bell className="w-3.5 h-3.5" />
                    Em ponto de corte
                    {cutoffCount > 0 && (
                      <span className={`ml-0.5 px-1.5 py-0.5 rounded-full text-[10px] font-bold ${
                        eventoListOnlyCutoff
                          ? isDark ? 'bg-rose-500/40 text-rose-100' : 'bg-rose-200 text-rose-800'
                          : isDark ? 'bg-rose-500/30 text-rose-200' : 'bg-rose-100 text-rose-700'
                      }`}>{cutoffCount}</span>
                    )}
                  </button>

                  {/* Apenas com trava automática */}
                  <button
                    onClick={() => setEventoListOnlyLocked(v => !v)}
                    disabled={lockedCount === 0 && !eventoListOnlyLocked}
                    title={lockedCount === 0 ? 'Nenhum evento está com trava automática ativa' : 'Mostrar apenas eventos com trava automática ativa'}
                    className={`flex items-center gap-1.5 h-9 px-3 rounded-xl text-xs font-semibold transition-all border ${
                      eventoListOnlyLocked
                        ? isDark ? 'bg-amber-500/25 text-amber-200 border-amber-500/50' : 'bg-amber-100 text-amber-700 border-amber-300'
                        : lockedCount === 0
                          ? isDark ? 'bg-gray-800/30 text-gray-600 border-gray-700/40 cursor-not-allowed' : 'bg-gray-100 text-gray-400 border-gray-200 cursor-not-allowed'
                          : isDark ? 'bg-gray-900/50 text-gray-300 border-gray-600 hover:bg-amber-500/15 hover:text-amber-300 hover:border-amber-500/40' : 'bg-gray-50 text-gray-700 border-gray-200 hover:bg-amber-50 hover:text-amber-700 hover:border-amber-300'
                    }`}
                  >
                    <Lock className="w-3.5 h-3.5" />
                    Com trava
                    {lockedCount > 0 && (
                      <span className={`ml-0.5 px-1.5 py-0.5 rounded-full text-[10px] font-bold ${
                        eventoListOnlyLocked
                          ? isDark ? 'bg-amber-500/40 text-amber-100' : 'bg-amber-200 text-amber-800'
                          : isDark ? 'bg-amber-500/30 text-amber-200' : 'bg-amber-100 text-amber-700'
                      }`}>{lockedCount}</span>
                    )}
                  </button>

                  {/* Clear */}
                  {hasFilters && (
                    <button
                      onClick={() => { setEventoListSearch(''); setEventoListMes(''); setEventoListModalidade(''); setEventoListCidade(''); setEventoListStatus('Em andamento'); setEventoListOnlyCutoff(false); setEventoListOnlyLocked(false); }}
                      className={`flex items-center gap-1 h-9 px-3 rounded-xl text-xs font-semibold transition-all ${isDark ? 'bg-red-500/15 text-red-400 hover:bg-red-500/25 border border-red-500/30' : 'bg-red-50 text-red-600 hover:bg-red-100 border border-red-200'}`}
                    >
                      <X className="w-3.5 h-3.5" /> Limpar
                    </button>
                  )}

                  <span className={`ml-auto text-xs ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>{filteredEventosList.length} evento(s)</span>
                </div>
              );
            })()}
            {loading ? (
              <div className="flex justify-center py-12">
                <div className="w-8 h-8 border-4 border-violet-500 border-t-transparent rounded-full animate-spin" />
              </div>
            ) : filteredEventosList.length === 0 ? (
              <div className={`text-center py-12 ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                <Calendar className="w-12 h-12 mx-auto mb-3 opacity-30" />
                <p className="font-semibold">Nenhum evento encontrado</p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className={isDark ? 'bg-gray-900/50' : 'bg-gray-50'}>
                      {([
                        { label: 'Evento',           field: 'nome' },
                        { label: 'Data',             field: 'data' },
                        { label: 'Tipo / Modalidade',field: 'modalidade' },
                        { label: 'Cidade',           field: 'cidade' },
                        { label: 'Status',           field: 'status' },
                        { label: 'Projeções',        field: 'projecoes' },
                      ] as { label: string; field: string | null }[]).map(({ label, field }) => (
                        <th
                          key={label}
                          onClick={field ? () => toggleEventoSort(field) : undefined}
                          className={`px-4 py-3 text-left text-xs font-bold uppercase tracking-wider select-none ${field ? 'cursor-pointer hover:opacity-80' : ''} ${isDark ? 'text-gray-400' : 'text-gray-500'}`}
                        >
                          <span className="inline-flex items-center gap-1">
                            {label}
                            {field && (
                              eventoListSort.field === field ? (
                                eventoListSort.dir === 'asc'
                                  ? <span className={isDark ? 'text-violet-400' : 'text-violet-600'}>↑</span>
                                  : <span className={isDark ? 'text-violet-400' : 'text-violet-600'}>↓</span>
                              ) : (
                                <span className="opacity-25">↕</span>
                              )
                            )}
                          </span>
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className={`divide-y ${isDark ? 'divide-gray-700/50' : 'divide-gray-100'}`}>
                    {sortedEventosList.map(ev => {
                      const evProjecoes = projecoesPorEventoId[ev.id] || [];
                      const allLocked = evProjecoes.length > 0 && evProjecoes.every(p => p.locked_at);
                      const someLocked = evProjecoes.some(p => p.locked_at);
                      const pend = pendenciasByEventoId[ev.id];
                      const cutoff = cutoffByEventoId[ev.id];
                      const statusColors: Record<string, string> = {
                        'Em andamento': isDark ? 'bg-emerald-500/20 text-emerald-400' : 'bg-emerald-100 text-emerald-700',
                        'Encerrado': isDark ? 'bg-gray-500/20 text-gray-400' : 'bg-gray-100 text-gray-600',
                        'Cancelado': isDark ? 'bg-red-500/20 text-red-400' : 'bg-red-100 text-red-700',
                      };
                      const statusColor = statusColors[ev.status || ''] || (isDark ? 'bg-gray-700 text-gray-400' : 'bg-gray-100 text-gray-500');
                      const cutoffDias = cutoff ? cutoff.dias : (pend ? pend.dias_ate_evento : null);
                      const cutoffUrgent = cutoffDias !== null && cutoffDias <= 15;
                      const showCutoffMarker = !!cutoff || !!pend;
                      const cutoffPending = !!pend;
                      return (
                        <tr
                          key={ev.id}
                          onClick={() => setSelectedEvento(ev)}
                          className={`cursor-pointer transition-colors ${
                            showCutoffMarker
                              ? cutoffPending
                                ? cutoffUrgent
                                  ? isDark ? 'bg-red-500/[0.07] hover:bg-red-500/15' : 'bg-red-50/60 hover:bg-red-50'
                                  : isDark ? 'bg-amber-500/[0.06] hover:bg-amber-500/15' : 'bg-amber-50/60 hover:bg-amber-50'
                                : isDark ? 'bg-emerald-500/[0.05] hover:bg-emerald-500/10' : 'bg-emerald-50/50 hover:bg-emerald-50'
                              : isDark ? 'hover:bg-violet-500/10' : 'hover:bg-violet-50'
                          }`}
                        >
                          <td className={`px-4 py-3 text-sm font-semibold ${isDark ? 'text-white' : 'text-gray-900'}`}>
                            <div className="flex items-center gap-2 flex-wrap">
                              <span>{ev.nome}</span>
                              {autoLockedEventoIds.has(ev.id) && (
                                <span
                                  title={`Trava automática ativa (D-${autoLockConfig.dias_antes_evento} às ${autoLockConfig.hora_trava || '00:00'})`}
                                  className={`inline-flex items-center justify-center w-5 h-5 rounded-md flex-shrink-0 ${isDark ? 'bg-amber-500/20 text-amber-300' : 'bg-amber-100 text-amber-600'}`}
                                >
                                  <Lock className="w-3 h-3" />
                                </span>
                              )}
                              {showCutoffMarker && (
                                <span
                                  title={
                                    cutoffPending && pend
                                      ? `Ponto de corte D-${pend.cutoff_dias} sobre a Data de corte Envio ${formatDate(pend.cutoff_data || null)} atingido. Áreas pendentes: ${pend.areas_pendentes.map(a => a.area_projecao_nome).join(', ')}`
                                      : cutoff
                                        ? `Ponto de corte D-${cutoff.dias} sobre a Data de corte Envio ${formatDate(cutoff.refDate)} atingido. Todas as áreas que você pode editar já têm projeção registrada.`
                                        : ''
                                  }
                                  className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-bold ${
                                    cutoffPending
                                      ? cutoffUrgent
                                        ? isDark ? 'bg-red-500/30 text-red-200 border border-red-500/50' : 'bg-red-100 text-red-700 border border-red-300'
                                        : isDark ? 'bg-amber-500/30 text-amber-200 border border-amber-500/50' : 'bg-amber-100 text-amber-700 border border-amber-300'
                                      : isDark ? 'bg-emerald-500/30 text-emerald-200 border border-emerald-500/50' : 'bg-emerald-100 text-emerald-700 border border-emerald-300'
                                  }`}
                                >
                                  {cutoffPending && pend?.cutoff_customizado ? <Clock className="w-2.5 h-2.5" /> : <Bell className="w-2.5 h-2.5" />}
                                  {cutoffPending ? 'Pendente' : 'Em corte'}
                                  {' • '}
                                  {cutoffPending && pend?.cutoff_customizado
                                    ? formatDate(pend.cutoff_data || null)
                                    : `D-${cutoffDias}`}
                                </span>
                              )}
                            </div>
                            {ev.circuito_produto && (
                              <div className={`text-xs mt-0.5 ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>{ev.circuito_produto}</div>
                            )}
                          </td>
                          <td className={`px-4 py-3 text-sm ${isDark ? 'text-gray-300' : 'text-gray-600'}`}>
                            {formatDate(ev.info_geral?.data || ev.data_evento || null)}
                          </td>
                          <td className="px-4 py-3">
                            <div className={`text-xs font-medium ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>{ev.tipo_evento || '-'}</div>
                            <div className={`text-xs mt-0.5 ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>{ev.modalidade || '-'}</div>
                          </td>
                          <td className={`px-4 py-3 text-sm ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                            {ev.cidade || '-'}
                          </td>
                          <td className="px-4 py-3">
                            {ev.status && (
                              <span className={`inline-flex px-2 py-0.5 rounded-md text-xs font-semibold ${statusColor}`}>
                                {ev.status}
                              </span>
                            )}
                          </td>
                          <td className="px-4 py-3">
                            {evProjecoes.length === 0 ? (
                              <span className={`text-xs ${isDark ? 'text-gray-600' : 'text-gray-400'}`}>Nenhuma</span>
                            ) : (
                              <div className="flex items-center gap-2">
                                <span className={`inline-flex px-2 py-0.5 rounded-md text-xs font-bold ${isDark ? 'bg-violet-500/20 text-violet-400' : 'bg-violet-100 text-violet-700'}`}>
                                  {evProjecoes.length} área{evProjecoes.length !== 1 ? 's' : ''}
                                </span>
                                {allLocked && (
                                  <span className={`flex items-center gap-0.5 text-xs ${isDark ? 'text-red-400' : 'text-red-600'}`}>
                                    <Lock className="w-3 h-3" /> Travado
                                  </span>
                                )}
                                {!allLocked && someLocked && (
                                  <span className={`flex items-center gap-0.5 text-xs ${isDark ? 'text-amber-400' : 'text-amber-600'}`}>
                                    <Lock className="w-3 h-3" /> Parcial
                                  </span>
                                )}
                              </div>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {activeTab === 'projecoes' && selectedEvento && (
          /* ── Projections detail view ── */
          <div className="space-y-3">
            {/* Breadcrumb */}
            <div className="flex items-center gap-2">
              <button
                onClick={() => setSelectedEvento(null)}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-semibold transition-colors ${isDark ? 'text-gray-400 hover:text-white hover:bg-gray-700/50' : 'text-gray-500 hover:text-gray-900 hover:bg-gray-100'}`}
              >
                <ChevronDown className="w-4 h-4 rotate-90" />
                Eventos
              </button>
              <span className={isDark ? 'text-gray-600' : 'text-gray-300'}>/</span>
              <span className={`text-sm font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>{selectedEvento.nome}</span>
              {(selectedEvento.info_geral?.data || selectedEvento.data_evento) && (
                <span className={`text-xs ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>{formatDate(selectedEvento.info_geral?.data || selectedEvento.data_evento || null)}</span>
              )}
            </div>

            {/* Banner de trava automática */}
            {autoLockConfig.ativo && autoLockConfig.dias_antes_evento > 0 && autoLockedEventoIds.has(selectedEvento.id) && (
              isAdmin ? (
                <div className={`flex items-center gap-2.5 px-4 py-2.5 rounded-xl text-xs ${isDark ? 'bg-amber-500/10 border border-amber-500/20 text-amber-300' : 'bg-amber-50 border border-amber-200 text-amber-700'}`}>
                  <Lock className="w-3.5 h-3.5 flex-shrink-0" />
                  <span>
                    <strong>Trava automática ativa (D-{autoLockConfig.dias_antes_evento} às {autoLockConfig.hora_trava || '00:00'})</strong> — como administrador, você ainda pode criar e editar projeções neste evento.
                  </span>
                </div>
              ) : (
                <div className={`flex items-center gap-2.5 px-4 py-3 rounded-xl text-sm font-medium ${isDark ? 'bg-amber-500/15 border border-amber-500/30 text-amber-300' : 'bg-amber-100 border border-amber-300 text-amber-800'}`}>
                  <Lock className="w-4 h-4 flex-shrink-0" />
                  <span>
                    Este evento está dentro do período de <strong>trava automática (D-{autoLockConfig.dias_antes_evento} às {autoLockConfig.hora_trava || '00:00'})</strong>.
                    Criação, edição e exclusão de projeções estão bloqueadas.
                  </span>
                </div>
              )
            )}

            {(() => {
              const myCustomAreas = areas.filter(a => a.usa_cutoff_customizado && (isAdmin || myAreaIds.has(a.id)));
              if (myCustomAreas.length === 0) return null;
              return (
                <div className={`rounded-2xl p-4 ${isDark ? 'bg-orange-500/5 border border-orange-500/20' : 'bg-orange-50/60 border border-orange-200'}`}>
                  <div className="flex items-center gap-2 mb-3">
                    <Clock className={`w-4 h-4 ${isDark ? 'text-orange-300' : 'text-orange-600'}`} />
                    <h3 className={`text-sm font-bold ${isDark ? 'text-orange-200' : 'text-orange-800'}`}>
                      Datas de corte por evento
                    </h3>
                  </div>
                  {eventoCutoffsLoading ? (
                    <div className="flex justify-center py-4">
                      <div className="w-5 h-5 border-2 border-orange-500 border-t-transparent rounded-full animate-spin" />
                    </div>
                  ) : (
                    <div className="space-y-2">
                      {myCustomAreas.map(area => {
                        const draft = cutoffDraft[area.id] || { d1: '', d2: '', saida: '' };
                        const existing = eventoCutoffs.find(c => c.area_projecao_id === area.id);
                        return (
                          <div
                            key={area.id}
                            className={`flex flex-wrap items-end gap-3 p-3 rounded-xl ${isDark ? 'bg-gray-800/40 border border-gray-700/40' : 'bg-white border border-gray-200'}`}
                          >
                            <div className="flex-1 min-w-[140px]">
                              <div className={`text-xs font-bold uppercase tracking-wider mb-1 ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Área</div>
                              <div className={`text-sm font-semibold ${isDark ? 'text-white' : 'text-gray-900'}`}>{area.nome}</div>
                              {existing?.updated_at && (
                                <div className={`text-[11px] mt-1 ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>
                                  Atualizado por {existing.updated_by_nome || 'usuário'} em {formatDateTime(existing.updated_at)}
                                </div>
                              )}
                            </div>
                            <div>
                              <div className={`text-xs font-bold uppercase tracking-wider mb-1 ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Data de corte Envio</div>
                              <input
                                type="date"
                                value={draft.d1}
                                onChange={e => setCutoffDraft(prev => ({ ...prev, [area.id]: { ...(prev[area.id] || { d1: '', d2: '', saida: '' }), d1: e.target.value } }))}
                                className={`px-3 py-2 rounded-lg border text-sm ${isDark ? 'bg-gray-800/50 border-gray-600 text-white' : 'bg-white border-gray-300 text-gray-900'} focus:outline-none focus:ring-2 focus:ring-orange-500`}
                              />
                            </div>
                            <div>
                              <div className={`text-xs font-bold uppercase tracking-wider mb-1 ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Saída caminhão</div>
                              <input
                                type="date"
                                value={draft.saida}
                                onChange={e => setCutoffDraft(prev => ({ ...prev, [area.id]: { ...(prev[area.id] || { d1: '', d2: '', saida: '' }), saida: e.target.value } }))}
                                className={`px-3 py-2 rounded-lg border text-sm ${isDark ? 'bg-gray-800/50 border-gray-600 text-white' : 'bg-white border-gray-300 text-gray-900'} focus:outline-none focus:ring-2 focus:ring-orange-500`}
                              />
                            </div>
                            <button
                              onClick={() => saveEventoCutoff(selectedEvento.id, area.id)}
                              disabled={savingCutoffAreaId === area.id}
                              className={`flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-semibold transition-all ${
                                savingCutoffAreaId === area.id
                                  ? 'opacity-60 cursor-wait bg-orange-500/40 text-white'
                                  : 'bg-gradient-to-r from-orange-500 to-amber-500 text-white hover:shadow-lg'
                              }`}
                            >
                              {savingCutoffAreaId === area.id ? 'Salvando...' : 'Salvar'}
                            </button>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              );
            })()}

          <div className={`rounded-2xl overflow-hidden ${isDark ? 'bg-gray-800/50 backdrop-blur-xl border border-gray-700/50' : 'bg-white/70 backdrop-blur-xl border border-gray-200'}`}>
            {loading ? (
              <div className="flex justify-center py-12">
                <div className="w-8 h-8 border-4 border-violet-500 border-t-transparent rounded-full animate-spin" />
              </div>
            ) : (eventGroups.filter(g => g[0].evento_id === selectedEvento.id)).length === 0 ? (
              <div className={`text-center py-12 ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                <BarChart3 className="w-12 h-12 mx-auto mb-3 opacity-30" />
                <p className="font-semibold">Nenhuma projeção para este evento</p>
                {canCreateProjecao && <p className="text-sm mt-1">Clique em "Nova Projeção" para começar</p>}
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full table-fixed">
                  <colgroup>
                    <col />
                    <col className="w-40" />
                    <col className="w-48" />
                    <col className="w-40" />
                    <col className="w-28" />
                  </colgroup>
                  <thead>
                    <tr className={isDark ? 'bg-gray-900/50' : 'bg-gray-50'}>
                      {([
                        { label: 'Área',                          field: 'area' },
                        { label: 'Quantidade',                    field: 'quantidade' },
                        { label: 'Criado por',                    field: 'criado' },
                        { label: 'Última edição / Travamento',    field: 'ultima' },
                        { label: 'Ações',                         field: null },
                      ] as { label: string; field: string | null }[]).map(({ label, field }) => (
                        <th
                          key={label}
                          onClick={field ? () => toggleProjecaoSort(field) : undefined}
                          className={`px-4 py-3 text-left text-xs font-bold uppercase tracking-wider select-none ${field ? 'cursor-pointer hover:opacity-80' : ''} ${isDark ? 'text-gray-400' : 'text-gray-500'}`}
                        >
                          <span className="inline-flex items-center gap-1">
                            {label}
                            {field && (
                              projecaoSort.field === field ? (
                                projecaoSort.dir === 'asc'
                                  ? <span className={isDark ? 'text-violet-400' : 'text-violet-600'}>↑</span>
                                  : <span className={isDark ? 'text-violet-400' : 'text-violet-600'}>↓</span>
                              ) : (
                                <span className="opacity-25">↕</span>
                              )
                            )}
                          </span>
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className={`divide-y ${isDark ? 'divide-gray-700/50' : 'divide-gray-100'}`}>
                    {eventGroups.filter(g => selectedEvento ? g[0].evento_id === selectedEvento.id : true).map(rawGroup => {
                      const group = sortProjecaoGroup(rawGroup);
                      const firstP = group[0];
                      const allLocked = group.every(p => p.locked_at);
                      const someLocked = group.some(p => p.locked_at);
                      return (
                        <React.Fragment key={firstP.evento_id}>
                          {/* Event header row */}
                          <tr className={isDark ? 'bg-gray-900/70' : 'bg-gray-100/80'}>
                            <td colSpan={5} className="px-4 py-2.5">
                              <div className="flex items-center justify-between gap-4">
                                <div className="flex items-center gap-3 flex-wrap">
                                  <span className={`font-bold text-sm ${isDark ? 'text-white' : 'text-gray-900'}`}>
                                    {firstP.evento_nome}
                                  </span>
                                  {firstP.evento_data && (
                                    <span className={`text-xs ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                                      {formatDate(firstP.evento_data)}
                                    </span>
                                  )}
                                  {firstP.evento_tipo && (
                                    <span className={`text-xs px-2 py-0.5 rounded-md ${isDark ? 'bg-gray-700 text-gray-300' : 'bg-gray-200 text-gray-600'}`}>
                                      {firstP.evento_tipo}
                                    </span>
                                  )}
                                  {allLocked && (
                                    <span className={`flex items-center gap-1 text-xs px-2 py-0.5 rounded-md font-semibold ${isDark ? 'bg-red-500/20 text-red-400' : 'bg-red-100 text-red-700'}`}>
                                      <Lock className="w-3 h-3" /> Travado
                                    </span>
                                  )}
                                  {!allLocked && someLocked && (
                                    <span className={`flex items-center gap-1 text-xs px-2 py-0.5 rounded-md font-semibold ${isDark ? 'bg-amber-500/20 text-amber-400' : 'bg-amber-100 text-amber-700'}`}>
                                      <Lock className="w-3 h-3" /> Parcialmente travado
                                    </span>
                                  )}
                                </div>
                                {canEditProjecao && isAdmin && (
                                  <button
                                    onClick={() => handleToggleLock(firstP.evento_id, allLocked)}
                                    disabled={lockingEventoId === firstP.evento_id}
                                    title={allLocked ? 'Destravar projeções (admin)' : 'Travar todas as projeções deste evento (admin)'}
                                    className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all disabled:opacity-50 disabled:cursor-not-allowed ${
                                      allLocked
                                        ? isDark ? 'bg-orange-500/20 text-orange-400 hover:bg-orange-500/30' : 'bg-orange-100 text-orange-700 hover:bg-orange-200'
                                        : isDark ? 'bg-violet-500/20 text-violet-400 hover:bg-violet-500/30' : 'bg-violet-100 text-violet-700 hover:bg-violet-200'
                                    }`}
                                  >
                                    {lockingEventoId === firstP.evento_id ? (
                                      <span className="animate-pulse">Aguarde...</span>
                                    ) : allLocked ? (
                                      <><LockOpen className="w-3.5 h-3.5" /> Destravar</>
                                    ) : (
                                      <><Lock className="w-3.5 h-3.5" /> Travar</>
                                    )}
                                  </button>
                                )}
                              </div>
                            </td>
                          </tr>
                          {/* Sub-rows per area */}
                          {group.map(p => (
                            <tr key={p.id} className={`transition-colors ${p.locked_at ? (isDark ? 'opacity-75' : 'opacity-80') : ''} ${isDark ? 'hover:bg-gray-700/30' : 'hover:bg-gray-50'}`}>
                              <td className="px-4 py-3 pl-6">
                                <div className="flex items-center gap-2">
                                  {p.locked_at && <Lock className={`w-3 h-3 flex-shrink-0 ${isDark ? 'text-red-400' : 'text-red-500'}`} />}
                                  <span className={`inline-flex px-2.5 py-1 rounded-lg text-xs font-semibold ${isDark ? 'bg-violet-500/20 text-violet-300' : 'bg-violet-100 text-violet-700'}`}>
                                    {p.area_projecao_nome}
                                  </span>
                                </div>
                              </td>
                              <td className={`px-4 py-3 text-sm font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>
                                <div className="flex items-center gap-1.5 flex-wrap">
                                  <ClientesTooltip clientes={p.clientes} quantidade={p.quantidade} isDark={isDark} formatNumber={formatNumber} />
                                  <KitsTooltip kits={p.kits} isDark={isDark} formatNumber={formatNumber} />
                                </div>
                              </td>
                              <td className={`px-4 py-3 text-xs ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                                <div>{p.created_by_nome}</div>
                                <div>{formatDateTime(p.created_at)}</div>
                              </td>
                              <td className={`px-4 py-3 text-xs`}>
                                {p.locked_at ? (
                                  <div className={`flex items-center gap-1.5 ${isDark ? 'text-red-400' : 'text-red-600'}`}>
                                    <Lock className="w-3 h-3 flex-shrink-0" />
                                    <div>
                                      <div className="font-medium">{p.locked_by_nome}</div>
                                      <div>{formatDateTime(p.locked_at)}</div>
                                    </div>
                                  </div>
                                ) : p.updated_by_nome ? (
                                  <div className={isDark ? 'text-gray-400' : 'text-gray-500'}>
                                    <div>{p.updated_by_nome}</div>
                                    <div>{formatDateTime(p.updated_at)}</div>
                                  </div>
                                ) : <span className={isDark ? 'text-gray-600' : 'text-gray-400'}>-</span>}
                              </td>
                              <td className="px-4 py-3">
                                <div className="flex items-center gap-1">
                                  {canEditProjecao && myAreaIds.has(p.area_projecao_id) && !p.locked_at && !(!isAdmin && selectedEvento && autoLockedEventoIds.has(selectedEvento.id)) && (
                                    <button
                                      onClick={() => openEdit(p)}
                                      className="p-1.5 rounded-lg hover:bg-blue-500/20 text-blue-400 transition-colors"
                                      title="Editar"
                                    >
                                      <Pencil className="w-4 h-4" />
                                    </button>
                                  )}
                                  {(myAreaIds.has(p.area_projecao_id) || isAdmin) && (
                                    <button
                                      onClick={() => openHistorico(p)}
                                      className="p-1.5 rounded-lg hover:bg-amber-500/20 text-amber-400 transition-colors"
                                      title="Histórico"
                                    >
                                      <History className="w-4 h-4" />
                                    </button>
                                  )}
                                  {canDeleteProjecao && myAreaIds.has(p.area_projecao_id) && !p.locked_at && !(!isAdmin && selectedEvento && autoLockedEventoIds.has(selectedEvento.id)) && (
                                    <button
                                      onClick={() => handleDelete(p.id)}
                                      className="p-1.5 rounded-lg hover:bg-red-500/20 text-red-400 transition-colors"
                                      title="Excluir"
                                    >
                                      <Trash2 className="w-4 h-4" />
                                    </button>
                                  )}
                                </div>
                              </td>
                            </tr>
                          ))}
                        </React.Fragment>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
          </div>
        )}

        {activeTab === 'consolidado' && (
          <div className="space-y-6">
            {consolidadoLoading && filteredConsolidado.length === 0 ? (
              <div className="space-y-4">
                {[0, 1, 2].map(i => (
                  <div
                    key={i}
                    className={`relative overflow-hidden rounded-2xl p-5 pl-6 animate-pulse ${isDark ? 'bg-gray-800/60 border border-gray-700/50' : 'bg-white/80 border border-gray-200'}`}
                  >
                    <div className={`absolute top-0 left-0 h-full w-1 bg-gradient-to-b from-violet-400/40 to-purple-500/40`} />
                    <div className={`h-5 w-1/3 rounded-lg ${isDark ? 'bg-gray-700/70' : 'bg-gray-200'}`} />
                    <div className="mt-4 flex gap-3">
                      <div className={`h-20 flex-1 rounded-2xl ${isDark ? 'bg-gray-700/50' : 'bg-gray-100'}`} />
                      <div className={`h-20 flex-1 rounded-2xl ${isDark ? 'bg-gray-700/50' : 'bg-gray-100'}`} />
                    </div>
                  </div>
                ))}
                <p className={`text-center text-sm ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                  Carregando visão consolidada...
                </p>
              </div>
            ) : filteredConsolidado.length === 0 ? (
              <div className={`text-center py-16 rounded-2xl ${isDark ? 'bg-gray-800/50 border border-gray-700/50 text-gray-400' : 'bg-white/70 border border-gray-200 text-gray-500'}`}>
                <Eye className="w-14 h-14 mx-auto mb-4 opacity-20" />
                <p className="text-lg font-semibold">Nenhum evento com projeções</p>
                <p className="text-sm mt-1">Crie projeções na aba anterior para ver a visão consolidada</p>
              </div>
            ) : (
              <>
                {/* Event Cards */}
                <div className="space-y-4">
                  {filteredConsolidado.map(c => {
                    const isExpanded = expandedConsolidado.has(c.evento_id);
                    const effectiveQtd = (p: { area_projecao_nome: string; quantidade: number }) => p.quantidade;
                    const diasAteEvento = (() => {
                      if (!c.evento_data) return null;
                      const datePart = c.evento_data.slice(0, 10);
                      const parts = datePart.split('-').map(Number);
                      if (parts.length !== 3 || parts.some(isNaN)) return null;
                      const fmt = new Intl.DateTimeFormat('en-CA', {
                        timeZone: 'America/Sao_Paulo',
                        year: 'numeric', month: '2-digit', day: '2-digit',
                      });
                      const tp = fmt.format(new Date()).split('-').map(Number);
                      const todayUtc = Date.UTC(tp[0], tp[1] - 1, tp[2]);
                      const evUtc = Date.UTC(parts[0], parts[1] - 1, parts[2]);
                      return Math.round((evUtc - todayUtc) / 86400000);
                    })();

                    return (
                      <div
                        key={c.evento_id}
                        className={`relative overflow-hidden rounded-2xl transition-all duration-300 ${isDark ? 'bg-gray-800/60 backdrop-blur-xl border border-gray-700/50 hover:border-gray-600/70' : 'bg-white/80 backdrop-blur-xl border border-gray-200 shadow-sm hover:shadow-md'}`}
                      >
                        <div className={`absolute top-0 left-0 h-full w-1 bg-gradient-to-b from-violet-400 to-purple-500`} />

                        <div
                          className="cursor-pointer p-5 pl-6"
                          onClick={() => toggleConsolidado(c.evento_id)}
                        >
                          <div className="flex items-start justify-between gap-4">
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-3 flex-wrap">
                                <h3 className={`text-lg font-bold truncate ${isDark ? 'text-white' : 'text-gray-900'}`}>
                                  {c.evento_nome}
                                </h3>
                                {c.evento_data && (
                                  <span className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium ${isDark ? 'bg-gray-700/70 text-gray-300' : 'bg-gray-100 text-gray-600'}`}>
                                    <Calendar className="w-3 h-3" />
                                    {formatDate(c.evento_data)}
                                  </span>
                                )}
                                {diasAteEvento !== null && diasAteEvento >= 0 && (
                                  <span className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-bold font-mono ${isDark ? 'bg-violet-500/20 text-violet-300' : 'bg-violet-100 text-violet-700'}`}>
                                    D-{diasAteEvento}
                                  </span>
                                )}
                                {c.data_saida_caminhao && (
                                  <span
                                    title="Data de saída do caminhão"
                                    className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium ${isDark ? 'bg-amber-500/15 text-amber-300' : 'bg-amber-100 text-amber-700'}`}
                                  >
                                    <Truck className="w-3 h-3" />
                                    Saída caminhão: {formatDate(c.data_saida_caminhao)}
                                  </span>
                                )}
                              </div>

                              <div className="mt-4 flex items-stretch gap-3 flex-wrap">
                                {([
                                  { corte: 1 as const, label: 'Projeção Convicta', dias: c.corte_dias_1, valor: c.corte_valor_1, congeladoEm: c.corte_congelado_1_em,
                                    text: isDark ? 'text-violet-300' : 'text-violet-700',
                                    iconBadge: isDark ? 'bg-violet-500/15 text-violet-300' : 'bg-violet-100 text-violet-600',
                                    frozenBg: isDark ? 'bg-violet-500/[0.07] border-violet-500/25' : 'bg-violet-50 border-violet-200' },
                                  { corte: 2 as const, label: 'Projeção de Ajuste', dias: c.corte_dias_2, valor: c.corte_valor_2, congeladoEm: c.corte_congelado_2_em,
                                    text: isDark ? 'text-purple-300' : 'text-purple-700',
                                    iconBadge: isDark ? 'bg-purple-500/15 text-purple-300' : 'bg-purple-100 text-purple-600',
                                    frozenBg: isDark ? 'bg-purple-500/[0.07] border-purple-500/25' : 'bg-purple-50 border-purple-200' },
                                ]).map(({ corte, label, dias, valor, congeladoEm, text, iconBadge, frozenBg }) => {
                                  const isFrozen = valor !== null && valor !== undefined;
                                  const busy = corteActionBusy === `${c.evento_id}-${corte}`;
                                  const congeladoData = congeladoEm ? new Date(congeladoEm).toLocaleDateString('pt-BR') : null;
                                  const reabertoManual = corte === 1 ? !!c.reaberto_manual_corte_1 : !!c.reaberto_manual_corte_2;
                                  const congelaEmTxt = (corte === 1 && c.corte_data_envio)
                                    ? formatDate(c.corte_data_envio)
                                    : `D-${dias ?? '?'}`;
                                  return (
                                    <div
                                      key={corte}
                                      onClick={(e) => e.stopPropagation()}
                                      className={`relative min-w-[180px] flex-1 px-4 py-3 rounded-2xl border transition-all ${isFrozen
                                        ? frozenBg
                                        : (isDark ? 'bg-gray-900/20 border-dashed border-gray-700/60' : 'bg-gray-50/60 border-dashed border-gray-300')}`}
                                    >
                                      <div className="flex items-center justify-between gap-2 mb-2">
                                        <span className={`flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider ${isFrozen ? text : (isDark ? 'text-gray-400' : 'text-gray-500')}`}>
                                          <span className={`flex items-center justify-center w-5 h-5 rounded-lg ${isFrozen ? iconBadge : (isDark ? 'bg-gray-700/50 text-gray-400' : 'bg-gray-200 text-gray-500')}`}>
                                            {isFrozen ? <Lock className="w-3 h-3" /> : <LockOpen className="w-3 h-3" />}
                                          </span>
                                          {label}
                                        </span>
                                      </div>
                                      {(() => {
                                        const valorExibido = isFrozen ? (valor as number) : c.total_projecoes;
                                        const diffAjuste = (corte === 2 && c.corte_valor_1 != null)
                                          ? valorExibido - (c.corte_valor_1 as number)
                                          : null;
                                        return (
                                          <span className="flex items-baseline gap-2 flex-wrap">
                                            <span className={`text-3xl font-black tracking-tight ${isFrozen ? text : (isDark ? 'text-gray-400' : 'text-gray-500')}`}>
                                              {formatNumber(valorExibido)}
                                            </span>
                                            {diffAjuste != null && diffAjuste !== 0 && (
                                              <span
                                                className={`text-sm font-bold tabular-nums ${diffAjuste > 0
                                                  ? (isDark ? 'text-emerald-300' : 'text-emerald-600')
                                                  : (isDark ? 'text-rose-300' : 'text-rose-600')}`}
                                              >
                                                ({diffAjuste > 0 ? '+' : '−'} {formatNumber(Math.abs(diffAjuste))})
                                              </span>
                                            )}
                                          </span>
                                        );
                                      })()}
                                      {isFrozen ? (
                                        <span className={`inline-flex items-center gap-1 mt-1.5 px-2 py-0.5 rounded-lg text-[10px] font-bold ${isDark ? 'bg-emerald-500/15 text-emerald-300' : 'bg-emerald-100 text-emerald-700'}`}>
                                          <Clock className="w-2.5 h-2.5" />
                                          {congeladoData ? `Congelado em ${congeladoData}` : 'Valor congelado'}
                                        </span>
                                      ) : reabertoManual ? (
                                        <span className={`inline-flex items-center gap-1 mt-1.5 px-2 py-0.5 rounded-lg text-[10px] font-bold ${isDark ? 'bg-sky-500/15 text-sky-300' : 'bg-sky-100 text-sky-700'}`}>
                                          <LockOpen className="w-2.5 h-2.5" />
                                          Reaberto · congele manualmente
                                        </span>
                                      ) : c.corte_ativo ? (
                                        <span className={`inline-flex items-center gap-1 mt-1.5 px-2 py-0.5 rounded-lg text-[10px] font-bold ${isDark ? 'bg-amber-500/15 text-amber-300' : 'bg-amber-100 text-amber-700'}`}>
                                          <Clock className="w-2.5 h-2.5" />
                                          {`Congela em ${congelaEmTxt}`}
                                        </span>
                                      ) : (
                                        <span className={`block text-[10px] mt-1 ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>
                                          Congelamento inativo
                                        </span>
                                      )}
                                      {isAdmin && (
                                        <button
                                          disabled={busy}
                                          onClick={() => isFrozen ? handleReabrirCorte(c.evento_id, corte) : handleRecongelarCorte(c.evento_id, corte)}
                                          className={`mt-2 inline-flex items-center gap-1 text-[10px] font-semibold px-2.5 py-1 rounded-lg border transition-colors disabled:opacity-50 ${isDark ? 'border-gray-600/70 text-gray-300 hover:bg-gray-700/50' : 'border-gray-300 text-gray-600 hover:bg-gray-100'}`}
                                        >
                                          {isFrozen ? <><LockOpen className="w-3 h-3" /> Reabrir</> : <><Lock className="w-3 h-3" /> Congelar agora</>}
                                        </button>
                                      )}
                                    </div>
                                  );
                                })}
                              </div>

                            </div>

                            <button className={`mt-1 p-2 rounded-xl transition-colors ${isDark ? 'hover:bg-gray-700/50 text-gray-400' : 'hover:bg-gray-100 text-gray-400'}`}>
                              {isExpanded ? <ChevronUp className="w-5 h-5" /> : <ChevronDown className="w-5 h-5" />}
                            </button>
                          </div>
                        </div>

                        {isExpanded && (
                          <div className={`px-5 pl-6 pb-5 border-t ${isDark ? 'border-gray-700/40' : 'border-gray-100'}`}>
                            <div className="pt-4">
                              <div className="flex items-center gap-2 mb-4">
                                <Layers className={`w-4 h-4 ${isDark ? 'text-gray-500' : 'text-gray-400'}`} />
                                <span className={`text-xs font-bold uppercase tracking-wider ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>
                                  Projeção por Área
                                </span>
                                <button
                                  onClick={(e) => { e.stopPropagation(); setKitBreakdownEvento(c); }}
                                  title="Ver total por tipo de kit"
                                  className={`inline-flex items-center gap-1 px-2 py-1 rounded-lg text-[11px] font-semibold border transition-colors ${isDark ? 'border-gray-600/70 text-gray-300 hover:bg-gray-700/50' : 'border-gray-300 text-gray-600 hover:bg-gray-100'}`}
                                >
                                  <Package className="w-3 h-3" /> Por tipo de kit
                                </button>
                              </div>
                              <div className="space-y-3">
                                {c.projecoes
                                  .slice()
                                  .sort((a, b) => effectiveQtd(b) - effectiveQtd(a))
                                  .map((p, idx) => {
                                    const areaColors = [
                                      { bar: 'from-violet-500 to-purple-500', text: isDark ? 'text-violet-300' : 'text-violet-700', bg: isDark ? 'bg-violet-500/10' : 'bg-violet-50' },
                                      { bar: 'from-blue-500 to-cyan-500', text: isDark ? 'text-blue-300' : 'text-blue-700', bg: isDark ? 'bg-blue-500/10' : 'bg-blue-50' },
                                      { bar: 'from-emerald-500 to-teal-500', text: isDark ? 'text-emerald-300' : 'text-emerald-700', bg: isDark ? 'bg-emerald-500/10' : 'bg-emerald-50' },
                                      { bar: 'from-amber-500 to-orange-500', text: isDark ? 'text-amber-300' : 'text-amber-700', bg: isDark ? 'bg-amber-500/10' : 'bg-amber-50' },
                                      { bar: 'from-rose-500 to-pink-500', text: isDark ? 'text-rose-300' : 'text-rose-700', bg: isDark ? 'bg-rose-500/10' : 'bg-rose-50' },
                                      { bar: 'from-indigo-500 to-blue-500', text: isDark ? 'text-indigo-300' : 'text-indigo-700', bg: isDark ? 'bg-indigo-500/10' : 'bg-indigo-50' },
                                      { bar: 'from-teal-500 to-cyan-500', text: isDark ? 'text-teal-300' : 'text-teal-700', bg: isDark ? 'bg-teal-500/10' : 'bg-teal-50' },
                                      { bar: 'from-fuchsia-500 to-purple-500', text: isDark ? 'text-fuchsia-300' : 'text-fuchsia-700', bg: isDark ? 'bg-fuchsia-500/10' : 'bg-fuchsia-50' },
                                    ];
                                    const color = areaColors[idx % areaColors.length];
                                    const convictaKits = p.convicta_kits ?? p.kits ?? [];
                                    const convictaQtd = p.convicta_quantidade ?? p.quantidade;

                                    const renderKitChips = (kits: { nome_kit: string; quantidade: number }[], isAjuste = false) => {
                                      if (!kits || kits.length === 0) {
                                        return <span className={`text-[11px] ${isDark ? 'text-gray-600' : 'text-gray-400'}`}>—</span>;
                                      }
                                      return (
                                        <div className="flex flex-wrap gap-1.5">
                                          {kits
                                            .slice()
                                            .sort((a, b) => b.quantidade - a.quantidade)
                                            .map((k, kidx) => {
                                              const nomeExibido = (isAjuste && k.nome_kit === KIT_CAMISETA_ORIGEM) ? KIT_CAMISETA_LABEL : k.nome_kit;
                                              return (
                                                <span
                                                  key={`${k.nome_kit}-${kidx}`}
                                                  className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-lg text-[11px] font-medium ${isDark ? 'bg-gray-900/40 text-gray-300 border border-gray-700/50' : 'bg-white/70 text-gray-600 border border-gray-200'}`}
                                                >
                                                  <Package className="w-2.5 h-2.5 opacity-60" />
                                                  <span className="truncate max-w-[140px]">{nomeExibido}</span>
                                                  <span className={`font-bold tabular-nums ${color.text}`}>{formatNumber(k.quantidade)}</span>
                                                </span>
                                              );
                                            })}
                                        </div>
                                      );
                                    };

                                    return (
                                      <div key={p.area_projecao_id} className={`p-3 rounded-xl ${color.bg}`}>
                                        <div className="flex items-center justify-between mb-2 gap-3">
                                          <span className={`text-sm font-semibold ${color.text}`}>{p.area_projecao_nome}</span>
                                        </div>
                                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-3">
                                          {/* Projeção Convicta (Corte 1) */}
                                          <div className={`rounded-lg p-2.5 border ${isDark ? 'bg-gray-900/40 border-gray-700/60' : 'bg-white/70 border-gray-200'}`}>
                                            <div className="flex items-center justify-between gap-2 mb-2 pb-1.5 border-b border-dashed border-current/10">
                                              <span className={`text-[10px] font-bold uppercase tracking-wider ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                                                Convicta
                                              </span>
                                              <span className={`text-xs font-black tabular-nums ${isDark ? 'text-gray-200' : 'text-gray-800'}`}>
                                                {formatNumber(convictaQtd)}
                                              </span>
                                            </div>
                                            {renderKitChips(convictaKits)}
                                          </div>
                                          {/* Projeção Ajuste (Corte 2 / ao vivo) */}
                                          <div className={`rounded-lg p-2.5 border ${isDark ? 'bg-blue-500/10 border-blue-500/30' : 'bg-blue-50/80 border-blue-200'}`}>
                                            <div className={`flex items-center justify-between gap-2 mb-2 pb-1.5 border-b border-dashed ${isDark ? 'border-blue-500/20' : 'border-blue-200'}`}>
                                              <span className={`text-[10px] font-bold uppercase tracking-wider ${isDark ? 'text-blue-400' : 'text-blue-600'}`}>
                                                Ajuste
                                              </span>
                                              <span className={`text-xs font-black tabular-nums ${isDark ? 'text-blue-200' : 'text-blue-700'}`}>
                                                {formatNumber(p.quantidade)}
                                              </span>
                                            </div>
                                            {renderKitChips(p.kits ?? [], true)}
                                          </div>
                                        </div>
                                      </div>
                                    );
                                  })}
                              </div>
                            </div>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </>
            )}
          </div>
        )}

        {activeTab === 'config' && isAdmin && (
          <div className="space-y-6">
            {/* ── Trava Automática ── */}
            <div className={`rounded-2xl p-5 border ${isDark ? 'bg-gray-800/60 border-amber-500/30' : 'bg-amber-50/80 border-amber-300/60'}`}>
              <div className="flex items-start justify-between gap-3 mb-4 flex-wrap">
                <div className="flex items-center gap-2">
                  <Lock className={`w-5 h-5 flex-shrink-0 ${isDark ? 'text-amber-400' : 'text-amber-600'}`} />
                  <div>
                    <h2 className={`text-lg font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>Trava Automática</h2>
                    <p className={`text-xs ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>
                      Bloqueia criação, edição e exclusão de projeções quando o evento está a N dias ou menos da data. No dia exato D-N, a trava passa a valer a partir do horário definido.
                    </p>
                  </div>
                </div>
                {/* Status atual salvo */}
                <span className={`flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold border ${
                  autoLockConfig.ativo && autoLockConfig.dias_antes_evento > 0
                    ? isDark ? 'bg-amber-500/20 text-amber-300 border-amber-500/40' : 'bg-amber-100 text-amber-700 border-amber-300'
                    : isDark ? 'bg-gray-700 text-gray-400 border-gray-600' : 'bg-gray-100 text-gray-500 border-gray-200'
                }`}>
                  {autoLockConfig.ativo && autoLockConfig.dias_antes_evento > 0
                    ? <><Lock className="w-3 h-3" /> Ativa — D-{autoLockConfig.dias_antes_evento} às {autoLockConfig.hora_trava || '00:00'}</>
                    : <><LockOpen className="w-3 h-3" /> Inativa</>}
                </span>
              </div>

              {/* Aviso de bypass admin */}
              <div className={`flex items-start gap-2 mb-4 px-3 py-2.5 rounded-xl text-xs ${isDark ? 'bg-blue-500/10 border border-blue-500/20 text-blue-300' : 'bg-blue-50 border border-blue-200 text-blue-700'}`}>
                <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
                <span>
                  <strong>Administradores sempre podem criar e editar projeções</strong>, independente da trava.
                  Para verificar que a trava está bloqueando corretamente, teste com uma conta não-administradora.
                </span>
              </div>

              <div className="flex flex-wrap items-end gap-4">
                <div className="flex flex-col gap-1">
                  <label className={`text-xs font-semibold ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>Dias antes do evento (D-N)</label>
                  <input
                    type="number"
                    min={0}
                    max={365}
                    value={autoLockDraft.dias}
                    onChange={e => {
                      const val = e.target.value;
                      const n = parseInt(val, 10);
                      setAutoLockDraft(d => ({
                        ...d,
                        dias: val,
                        // Ativa automaticamente quando dias > 0; desativa quando dias = 0
                        ativo: (!isNaN(n) && n > 0) ? true : (!isNaN(n) && n === 0) ? false : d.ativo,
                      }));
                    }}
                    className={`w-28 px-3 py-2 rounded-xl border text-sm font-mono ${isDark ? 'bg-gray-700 border-gray-600 text-white' : 'bg-white border-gray-300 text-gray-900'} focus:outline-none focus:ring-2 focus:ring-amber-500/50`}
                  />
                </div>
                <div className="flex flex-col gap-1">
                  <label className={`text-xs font-semibold ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>Horário da trava (HH:MM)</label>
                  <input
                    type="time"
                    value={autoLockDraft.hora}
                    onChange={e => setAutoLockDraft(d => ({ ...d, hora: e.target.value || '00:00' }))}
                    className={`w-32 px-3 py-2 rounded-xl border text-sm font-mono ${isDark ? 'bg-gray-700 border-gray-600 text-white' : 'bg-white border-gray-300 text-gray-900'} focus:outline-none focus:ring-2 focus:ring-amber-500/50`}
                  />
                </div>
                <div className="flex flex-col gap-1">
                  <label className={`text-xs font-semibold ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>Status da trava</label>
                  <button
                    onClick={() => setAutoLockDraft(d => ({ ...d, ativo: !d.ativo }))}
                    className={`flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-semibold transition-all border ${autoLockDraft.ativo ? 'bg-amber-500 text-white border-amber-600 hover:bg-amber-600' : (isDark ? 'bg-gray-700 text-gray-300 border-gray-600 hover:bg-gray-600' : 'bg-white text-gray-500 border-gray-300 hover:bg-gray-50')}`}
                  >
                    {autoLockDraft.ativo ? <><Lock className="w-4 h-4" /> Ativa</> : <><LockOpen className="w-4 h-4" /> Inativa</>}
                  </button>
                </div>
                <button
                  onClick={saveAutoLockConfig}
                  disabled={savingAutoLock}
                  className="flex items-center gap-2 px-4 py-2 rounded-xl bg-gradient-to-r from-amber-500 to-orange-500 text-white text-sm font-semibold hover:shadow-lg transition-all disabled:opacity-50"
                >
                  {savingAutoLock ? 'Salvando…' : 'Salvar'}
                </button>
              </div>
              {autoLockConfig.updated_by_nome && (
                <p className={`mt-3 text-xs ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>
                  Última atualização por <span className="font-semibold">{autoLockConfig.updated_by_nome}</span>
                  {autoLockConfig.updated_at ? ` em ${new Date(autoLockConfig.updated_at).toLocaleDateString('pt-BR')}` : ''}
                </p>
              )}
            </div>

            {/* ── Cortes de Projeção (congelamento envio / convicta) ── */}
            <div className={`rounded-2xl p-5 border ${isDark ? 'bg-gray-800/60 border-violet-500/30' : 'bg-violet-50/80 border-violet-300/60'}`}>
              <div className="flex items-start justify-between gap-3 mb-4 flex-wrap">
                <div className="flex items-center gap-2">
                  <Lock className={`w-5 h-5 flex-shrink-0 ${isDark ? 'text-violet-400' : 'text-violet-600'}`} />
                  <div>
                    <h2 className={`text-lg font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>Cortes de Projeção</h2>
                    <p className={`text-xs ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>
                      Congela automaticamente o total de projeção de cada evento em dois momentos: <strong>Projeção Convicta</strong> (corte 1) e <strong>Projeção de Ajuste</strong> (corte 2). O valor é gravado no job noturno quando o evento atinge o D- configurado e permanece fixo a partir daí.
                    </p>
                  </div>
                </div>
                <span className={`flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold border ${
                  corteConfig.ativo
                    ? isDark ? 'bg-violet-500/20 text-violet-300 border-violet-500/40' : 'bg-violet-100 text-violet-700 border-violet-300'
                    : isDark ? 'bg-gray-700 text-gray-400 border-gray-600' : 'bg-gray-100 text-gray-500 border-gray-200'
                }`}>
                  {corteConfig.ativo
                    ? <><Lock className="w-3 h-3" /> Ativo — D-{corteConfig.dias_corte_1} / D-{corteConfig.dias_corte_2}</>
                    : <><LockOpen className="w-3 h-3" /> Inativo</>}
                </span>
              </div>

              <div className="flex flex-wrap items-end gap-4">
                <div className="flex flex-col gap-1">
                  <label className={`text-xs font-semibold ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>Corte 1 — Projeção Convicta (D-N)</label>
                  <input
                    type="number"
                    min={0}
                    max={365}
                    value={corteDraft.dias1}
                    onChange={e => setCorteDraft(d => ({ ...d, dias1: e.target.value }))}
                    className={`w-28 px-3 py-2 rounded-xl border text-sm font-mono ${isDark ? 'bg-gray-700 border-gray-600 text-white' : 'bg-white border-gray-300 text-gray-900'} focus:outline-none focus:ring-2 focus:ring-violet-500/50`}
                  />
                </div>
                <div className="flex flex-col gap-1">
                  <label className={`text-xs font-semibold ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>Corte 2 — Projeção de Ajuste (D-N)</label>
                  <input
                    type="number"
                    min={0}
                    max={365}
                    value={corteDraft.dias2}
                    onChange={e => setCorteDraft(d => ({ ...d, dias2: e.target.value }))}
                    className={`w-28 px-3 py-2 rounded-xl border text-sm font-mono ${isDark ? 'bg-gray-700 border-gray-600 text-white' : 'bg-white border-gray-300 text-gray-900'} focus:outline-none focus:ring-2 focus:ring-violet-500/50`}
                  />
                </div>
                <div className="flex flex-col gap-1">
                  <label className={`text-xs font-semibold ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>Congelamento automático</label>
                  <button
                    onClick={() => setCorteDraft(d => ({ ...d, ativo: !d.ativo }))}
                    className={`flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-semibold transition-all border ${corteDraft.ativo ? 'bg-violet-500 text-white border-violet-600 hover:bg-violet-600' : (isDark ? 'bg-gray-700 text-gray-300 border-gray-600 hover:bg-gray-600' : 'bg-white text-gray-500 border-gray-300 hover:bg-gray-50')}`}
                  >
                    {corteDraft.ativo ? <><Lock className="w-4 h-4" /> Ativo</> : <><LockOpen className="w-4 h-4" /> Inativo</>}
                  </button>
                </div>
                <button
                  onClick={saveCorteConfig}
                  disabled={savingCorte}
                  className="flex items-center gap-2 px-4 py-2 rounded-xl bg-gradient-to-r from-violet-500 to-purple-500 text-white text-sm font-semibold hover:shadow-lg transition-all disabled:opacity-50"
                >
                  {savingCorte ? 'Salvando…' : 'Salvar'}
                </button>
              </div>
              <p className={`mt-3 text-xs ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>
                Cada corte congela uma única vez por evento. Para regravar com o valor atual ou voltar a acompanhar ao vivo, use os botões <strong>Congelar agora</strong> / <strong>Reabrir</strong> em cada card da aba Visão Consolidada.
              </p>
              {corteConfig.updated_by_nome && (
                <p className={`mt-1 text-xs ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>
                  Última atualização por <span className="font-semibold">{corteConfig.updated_by_nome}</span>
                </p>
              )}
            </div>

            {/* ── Ponto de corte (alerta D- sobre a Data de corte Envio) ── */}
            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <Clock className={`w-5 h-5 ${isDark ? 'text-violet-400' : 'text-violet-600'}`} />
                <div>
                  <h2 className={`text-lg font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>Alerta de Pendência</h2>
                  <p className={`text-xs ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>
                    O alerta de pendência é contado em cima da "Data de corte Envio" do evento (a mais antiga entre as áreas). Define a quantidade de dias para o cálculo do D-: o alerta dispara no dia exato em que faltam esta quantidade de dias para a Data de corte Envio. Eventos sem Data de corte Envio cadastrada não geram alerta. Use 0 para desligar.
                  </p>
                </div>
              </div>

              <div className={`rounded-2xl p-4 border ${isDark ? 'bg-gray-800/50 border-gray-700/50' : 'bg-white border-gray-200'}`}>
                <div className="flex flex-wrap items-end gap-4">
                  <div>
                    <label className={`block text-xs font-bold uppercase tracking-wide mb-1.5 ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>
                      Dias para o D- (Data de corte Envio)
                    </label>
                    <div className="flex items-center gap-2">
                      <span className={`text-sm font-bold font-mono ${isDark ? 'text-violet-300' : 'text-violet-600'}`}>D-</span>
                      <input
                        type="number"
                        min={0}
                        max={365}
                        value={alertaDraft}
                        onChange={e => setAlertaDraft(e.target.value)}
                        className={`w-28 h-10 px-3 rounded-xl border text-sm focus:outline-none focus:ring-2 focus:ring-violet-500 ${isDark ? 'bg-gray-900 border-gray-700 text-white' : 'bg-gray-50 border-gray-200 text-gray-900'}`}
                      />
                    </div>
                  </div>
                  <button
                    onClick={saveAlertaConfig}
                    disabled={savingAlerta}
                    className="h-10 flex items-center gap-2 px-5 rounded-xl bg-gradient-to-r from-rose-600 to-orange-600 text-white text-sm font-semibold hover:shadow-lg transition-all disabled:opacity-60"
                  >
                    {savingAlerta ? 'Salvando…' : 'Salvar'}
                  </button>
                </div>
                <p className={`text-xs mt-3 ${isDark ? 'text-gray-500' : 'text-gray-500'}`}>
                  {corteConfig.dias_alerta_envio > 0
                    ? `Atualmente o alerta dispara em D-${corteConfig.dias_alerta_envio} da Data de corte Envio.`
                    : 'Alerta de ponto de corte desligado.'}
                  {corteConfig.updated_by_nome && <> Última atualização por <span className="font-semibold">{corteConfig.updated_by_nome}</span>.</>}
                </p>
              </div>
            </div>

            {/* ── Resumo diário por e-mail das pendências ── */}
            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <Mail className={`w-5 h-5 ${isDark ? 'text-violet-400' : 'text-violet-600'}`} />
                <div>
                  <h2 className={`text-lg font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>Notificação por E-mail</h2>
                  <p className={`text-xs ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>
                    Envia um resumo diário por e-mail para os responsáveis de cada área que tiverem projeção pendente no dia (mesma regra do alerta acima). Cada pessoa recebe apenas as suas áreas. Use o botão de teste para enviar agora, independente do horário.
                  </p>
                </div>
              </div>

              <div className={`rounded-2xl p-4 border ${isDark ? 'bg-gray-800/50 border-gray-700/50' : 'bg-white border-gray-200'}`}>
                <div className="flex flex-wrap items-end gap-4">
                  <div>
                    <label className={`block text-xs font-bold uppercase tracking-wide mb-1.5 ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>
                      Enviar resumo diário
                    </label>
                    <button
                      type="button"
                      onClick={() => setNotifDraft(d => ({ ...d, ativo: !d.ativo }))}
                      className={`relative inline-flex h-10 w-20 items-center rounded-xl transition-colors ${notifDraft.ativo ? 'bg-emerald-500' : (isDark ? 'bg-gray-700' : 'bg-gray-300')}`}
                    >
                      <span className={`inline-block h-8 w-8 transform rounded-lg bg-white shadow transition-transform ${notifDraft.ativo ? 'translate-x-11' : 'translate-x-1'}`} />
                    </button>
                  </div>
                  <div>
                    <label className={`block text-xs font-bold uppercase tracking-wide mb-1.5 ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>
                      Horário do envio (BRT)
                    </label>
                    <div className="flex items-center gap-2">
                      <input
                        type="number"
                        min={0}
                        max={23}
                        value={notifDraft.hora}
                        onChange={e => setNotifDraft(d => ({ ...d, hora: e.target.value }))}
                        className={`w-28 h-10 px-3 rounded-xl border text-sm focus:outline-none focus:ring-2 focus:ring-violet-500 ${isDark ? 'bg-gray-900 border-gray-700 text-white' : 'bg-gray-50 border-gray-200 text-gray-900'}`}
                      />
                      <span className={`text-sm font-mono ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>:00</span>
                    </div>
                  </div>
                  <button
                    onClick={saveNotifConfig}
                    disabled={savingNotif}
                    className="h-10 flex items-center gap-2 px-5 rounded-xl bg-gradient-to-r from-rose-600 to-orange-600 text-white text-sm font-semibold hover:shadow-lg transition-all disabled:opacity-60"
                  >
                    {savingNotif ? 'Salvando…' : 'Salvar'}
                  </button>
                  <button
                    onClick={sendNotifTest}
                    disabled={sendingNotifTest}
                    className={`h-10 flex items-center gap-2 px-5 rounded-xl border text-sm font-semibold transition-all disabled:opacity-60 ${isDark ? 'border-gray-600 text-gray-200 hover:bg-gray-700/50' : 'border-gray-300 text-gray-700 hover:bg-gray-100'}`}
                  >
                    <Mail className="w-4 h-4" />
                    {sendingNotifTest ? 'Enviando…' : 'Enviar agora (teste)'}
                  </button>
                </div>
                <p className={`text-xs mt-3 ${isDark ? 'text-gray-500' : 'text-gray-500'}`}>
                  {corteConfig.notif_email_ativo
                    ? `Resumo diário ativo — envio às ${corteConfig.notif_email_hora ?? 8}h (BRT).`
                    : 'Resumo diário por e-mail desativado.'}
                </p>
              </div>
            </div>

            {/* ── Áreas e usuários ── */}
            <div className="space-y-3">
              <div className="flex items-center justify-between flex-wrap gap-3">
                <div className="flex items-center gap-2">
                  <Users className={`w-5 h-5 ${isDark ? 'text-violet-400' : 'text-violet-600'}`} />
                  <div>
                    <h2 className={`text-lg font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>Áreas e Usuários</h2>
                    <p className={`text-xs ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>
                      Defina quais usuários podem preencher projeções em cada área.
                    </p>
                  </div>
                </div>
                <button
                  onClick={() => { setNewAreaNome(''); setShowCreateAreaModal(true); }}
                  className="flex items-center gap-2 px-4 py-2 rounded-xl bg-gradient-to-r from-violet-600 to-blue-600 text-white text-sm font-semibold hover:shadow-lg transition-all"
                >
                  <Plus className="w-4 h-4" />
                  Nova Área
                </button>
              </div>
              {areasDetail.map(area => (
                <div key={area.id} className={cardClass}>
                  <div className="flex items-center justify-between flex-wrap gap-3">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <h3 className={`text-lg font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>{area.nome}</h3>
                        {area.usa_cutoff_customizado && (
                          <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-bold uppercase tracking-wider ${isDark ? 'bg-orange-500/20 text-orange-300 border border-orange-500/30' : 'bg-orange-100 text-orange-700 border border-orange-200'}`}>
                            <Clock className="w-2.5 h-2.5" />
                            Cortes por evento
                          </span>
                        )}
                      </div>
                      <div className="flex flex-wrap gap-2 mt-2">
                        {area.usuarios.length === 0 ? (
                          <span className={`text-sm italic ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>Nenhum usuário atribuído</span>
                        ) : (
                          area.usuarios.map(u => (
                            <span key={u.usuario_id} className={`inline-flex px-2.5 py-1 rounded-lg text-xs font-semibold ${isDark ? 'bg-blue-500/20 text-blue-300' : 'bg-blue-100 text-blue-700'}`}>
                              {u.usuario_nome}
                            </span>
                          ))
                        )}
                      </div>
                    </div>
                    <div className="flex items-center gap-2 flex-wrap">
                      <button
                        onClick={() => toggleAreaCutoffCustomizado(area)}
                        title={area.usa_cutoff_customizado
                          ? 'Desativar datas de corte por evento para esta área'
                          : 'Permitir que esta área defina duas datas de corte por evento'}
                        className={`flex items-center gap-2 px-3 py-2 rounded-xl text-sm font-semibold transition-all border ${
                          area.usa_cutoff_customizado
                            ? isDark
                              ? 'bg-orange-500/20 text-orange-300 border-orange-500/40 hover:bg-orange-500/30'
                              : 'bg-orange-100 text-orange-700 border-orange-200 hover:bg-orange-200'
                            : isDark
                              ? 'bg-gray-700/40 text-gray-300 border-gray-600/50 hover:bg-gray-700/60'
                              : 'bg-white text-gray-700 border-gray-200 hover:bg-gray-50'
                        }`}
                      >
                        <Clock className="w-4 h-4" />
                        {area.usa_cutoff_customizado ? 'Cortes ON' : 'Cortes OFF'}
                      </button>
                      <button
                        onClick={() => openAtribuir(area)}
                        className="flex items-center gap-2 px-4 py-2 rounded-xl bg-gradient-to-r from-violet-600 to-blue-600 text-white text-sm font-semibold hover:shadow-lg transition-all"
                      >
                        <Users className="w-4 h-4" />
                        Gerenciar
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {activeTab === 'lixeira' && isAdmin && (
          <div className="space-y-4">
            <div className={`flex items-center gap-3 p-4 rounded-2xl ${isDark ? 'bg-amber-500/10 border border-amber-500/30' : 'bg-amber-50 border border-amber-200'}`}>
              <AlertTriangle className={`w-5 h-5 ${isDark ? 'text-amber-400' : 'text-amber-600'}`} />
              <p className={`text-sm ${isDark ? 'text-amber-300' : 'text-amber-700'}`}>
                Itens na lixeira podem ser restaurados ou excluídos permanentemente. A exclusão permanente é irreversível.
              </p>
            </div>

            {lixeira.length === 0 ? (
              <div className={`text-center py-16 rounded-2xl ${isDark ? 'bg-gray-800/50 border border-gray-700/50 text-gray-400' : 'bg-white/70 border border-gray-200 text-gray-500'}`}>
                <Trash className="w-14 h-14 mx-auto mb-4 opacity-20" />
                <p className="text-lg font-semibold">Lixeira vazia</p>
                <p className="text-sm mt-1">Nenhuma projeção excluída</p>
              </div>
            ) : (
              <div className={`rounded-2xl overflow-hidden ${isDark ? 'bg-gray-800/50 backdrop-blur-xl border border-gray-700/50' : 'bg-white/70 backdrop-blur-xl border border-gray-200'}`}>
                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead>
                      <tr className={isDark ? 'bg-gray-900/50' : 'bg-gray-50'}>
                        {['Evento', 'Área', 'Quantidade', 'Excluído por', 'Data exclusão', 'Ações'].map(h => (
                          <th key={h} className={`px-4 py-3 text-left text-xs font-bold uppercase tracking-wider ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className={`divide-y ${isDark ? 'divide-gray-700/50' : 'divide-gray-100'}`}>
                      {lixeira.map(p => (
                        <tr key={p.id} className={`transition-colors ${isDark ? 'hover:bg-gray-700/30' : 'hover:bg-gray-50'}`}>
                          <td className={`px-4 py-3 text-sm font-medium ${isDark ? 'text-white' : 'text-gray-900'}`}>
                            {p.evento_nome}
                          </td>
                          <td className="px-4 py-3">
                            <span className={`inline-flex px-2.5 py-1 rounded-lg text-xs font-semibold ${isDark ? 'bg-violet-500/20 text-violet-300' : 'bg-violet-100 text-violet-700'}`}>
                              {p.area_projecao_nome}
                            </span>
                          </td>
                          <td className={`px-4 py-3 text-sm font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>
                            {formatNumber(p.quantidade)}
                          </td>
                          <td className={`px-4 py-3 text-xs ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                            {p.deleted_by_nome || p.updated_by_nome || '-'}
                          </td>
                          <td className={`px-4 py-3 text-xs ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                            {formatDateTime(p.deleted_at)}
                          </td>
                          <td className="px-4 py-3">
                            <div className="flex items-center gap-1">
                              <button
                                onClick={() => handleRestaurar(p.id)}
                                className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-semibold bg-emerald-500/20 text-emerald-400 hover:bg-emerald-500/30 transition-colors"
                                title="Restaurar"
                              >
                                <RotateCcw className="w-3.5 h-3.5" />
                                Restaurar
                              </button>
                              <button
                                onClick={() => handleDeletePermanente(p.id)}
                                className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-semibold bg-red-500/20 text-red-400 hover:bg-red-500/30 transition-colors"
                                title="Excluir permanentemente"
                              >
                                <Trash2 className="w-3.5 h-3.5" />
                                Excluir
                              </button>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Kit Breakdown Modal */}
      {kitBreakdownEvento && (() => {
        const totaisPorKit: Record<string, number> = {};
        for (const p of kitBreakdownEvento.projecoes) {
          for (const k of (p.kits || [])) {
            const nome = k.nome_kit;
            totaisPorKit[nome] = (totaisPorKit[nome] || 0) + k.quantidade;
          }
        }
        const linhas = Object.entries(totaisPorKit).sort((a, b) => b[1] - a[1]);
        const totalGeral = linhas.reduce((s, [, q]) => s + q, 0);
        return (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4" onClick={() => setKitBreakdownEvento(null)}>
            <div className={`w-full max-w-lg max-h-[90vh] overflow-y-auto rounded-2xl shadow-2xl ${isDark ? 'bg-gray-800 border border-gray-700' : 'bg-white'}`} onClick={(e) => e.stopPropagation()}>
              <div className="flex items-center justify-between p-6 border-b border-gray-700/50">
                <div className="flex items-center gap-2">
                  <Package className={`w-5 h-5 ${isDark ? 'text-violet-400' : 'text-violet-600'}`} />
                  <div>
                    <h2 className={`text-lg font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>Total por tipo de kit</h2>
                    <p className={`text-xs ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>{kitBreakdownEvento.evento_nome}</p>
                  </div>
                </div>
                <button onClick={() => setKitBreakdownEvento(null)} className="p-2 rounded-lg hover:bg-gray-700/50">
                  <X className={`w-5 h-5 ${isDark ? 'text-gray-400' : 'text-gray-500'}`} />
                </button>
              </div>
              <div className="p-6 space-y-2">
                {linhas.length === 0 ? (
                  <p className={`text-sm text-center py-6 ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Nenhum kit informado nas projeções deste evento.</p>
                ) : (
                  <>
                    {linhas.map(([nome, qtd]) => {
                      const pct = totalGeral > 0 ? (qtd / totalGeral) * 100 : 0;
                      return (
                        <div key={nome} className={`p-3 rounded-xl ${isDark ? 'bg-gray-900/40' : 'bg-gray-50'}`}>
                          <div className="flex items-center justify-between gap-3 mb-2">
                            <span className={`text-sm font-semibold flex items-center gap-1.5 ${isDark ? 'text-gray-200' : 'text-gray-700'}`}>
                              <Package className="w-3.5 h-3.5 opacity-60" /> {nome}
                            </span>
                            <span className={`text-sm font-black tabular-nums ${isDark ? 'text-white' : 'text-gray-900'}`}>{formatNumber(qtd)}</span>
                          </div>
                          <div className={`relative h-2 rounded-full overflow-hidden ${isDark ? 'bg-gray-700/50' : 'bg-gray-200/80'}`}>
                            <div className="h-full rounded-full bg-gradient-to-r from-violet-500 to-purple-500 transition-all duration-500 ease-out" style={{ width: `${pct}%` }} />
                          </div>
                        </div>
                      );
                    })}
                    <div className={`flex items-center justify-between gap-3 pt-3 mt-1 border-t ${isDark ? 'border-gray-700/50' : 'border-gray-200'}`}>
                      <span className={`text-sm font-bold uppercase tracking-wider ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Total geral</span>
                      <span className={`text-base font-black tabular-nums ${isDark ? 'text-violet-300' : 'text-violet-700'}`}>{formatNumber(totalGeral)}</span>
                    </div>
                  </>
                )}
              </div>
            </div>
          </div>
        );
      })()}

      {/* Create Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
          <div className={`w-full max-w-lg max-h-[90vh] overflow-y-auto rounded-2xl shadow-2xl ${isDark ? 'bg-gray-800 border border-gray-700' : 'bg-white'}`}>
            <div className="flex items-center justify-between p-6 border-b border-gray-700/50">
              <h2 className={`text-xl font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>Projeção Convicta</h2>
              <button onClick={() => setShowCreateModal(false)} className="p-2 rounded-lg hover:bg-gray-700/50">
                <X className={`w-5 h-5 ${isDark ? 'text-gray-400' : 'text-gray-500'}`} />
              </button>
            </div>
            <form onSubmit={handleCreate} className="p-6 space-y-4">
              <div>
                <label className={`block text-sm font-semibold mb-1 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>Evento</label>
                {selectedEvento ? (
                  <div className={`flex items-center gap-2 px-3 py-2.5 rounded-xl border ${isDark ? 'bg-gray-900/50 border-gray-600 text-white' : 'bg-gray-50 border-gray-200 text-gray-900'}`}>
                    <Calendar className={`w-4 h-4 shrink-0 ${isDark ? 'text-violet-400' : 'text-violet-600'}`} />
                    <span className="text-sm font-medium">{selectedEvento.nome}</span>
                    <input type="hidden" value={selectedEvento.id} />
                  </div>
                ) : (
                <div ref={eventoDropdownRef} className="relative">
                  <button
                    type="button"
                    onClick={() => setShowEventoDropdown(!showEventoDropdown)}
                    className={`${inputClass} text-left flex items-center justify-between`}
                  >
                    <span className={formEventoId ? '' : (isDark ? 'text-gray-500' : 'text-gray-400')}>
                      {formEventoId ? selectedEventoNome : 'Selecione um evento'}
                    </span>
                    <ChevronDown className={`w-4 h-4 shrink-0 transition-transform ${showEventoDropdown ? 'rotate-180' : ''} ${isDark ? 'text-gray-400' : 'text-gray-500'}`} />
                  </button>
                  {showEventoDropdown && (
                    <div className={`absolute z-50 mt-1 w-full rounded-xl border shadow-xl overflow-hidden ${isDark ? 'bg-gray-800 border-gray-600' : 'bg-white border-gray-200'}`}>
                      <div className={`p-2 border-b ${isDark ? 'border-gray-700' : 'border-gray-100'}`}>
                        <div className="relative">
                          <Search className={`absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 ${isDark ? 'text-gray-400' : 'text-gray-500'}`} />
                          <input
                            type="text"
                            value={eventoSearchTerm}
                            onChange={e => setEventoSearchTerm(e.target.value)}
                            placeholder="Filtrar eventos..."
                            className={`w-full pl-9 pr-3 py-2 rounded-lg border text-sm ${isDark ? 'bg-gray-900/50 border-gray-600 text-white placeholder-gray-500' : 'bg-gray-50 border-gray-200 text-gray-900 placeholder-gray-400'} focus:outline-none focus:ring-2 focus:ring-blue-500`}
                            autoFocus
                          />
                        </div>
                      </div>
                      <div className="max-h-48 overflow-y-auto">
                        {filteredEventos.length === 0 ? (
                          <p className={`px-3 py-3 text-sm text-center ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>Nenhum evento encontrado</p>
                        ) : (
                          filteredEventos.map(ev => (
                            <button
                              key={ev.id}
                              type="button"
                              onClick={() => { setFormEventoId(ev.id); setShowEventoDropdown(false); setEventoSearchTerm(''); }}
                              className={`w-full text-left px-3 py-2.5 text-sm transition-colors ${
                                formEventoId === ev.id
                                  ? isDark ? 'bg-violet-500/20 text-violet-300' : 'bg-violet-50 text-violet-700'
                                  : isDark ? 'text-gray-300 hover:bg-gray-700/50' : 'text-gray-700 hover:bg-gray-50'
                              }`}
                            >
                              <div className="font-medium">{ev.nome}</div>
                              {ev.info_geral?.data && (
                                <div className={`text-xs mt-0.5 ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>{formatDate(ev.info_geral.data)}</div>
                              )}
                            </button>
                          ))
                        )}
                      </div>
                    </div>
                  )}
                  <input type="hidden" value={formEventoId} required />
                </div>
                )}
              </div>
              <div>
                <label className={`block text-sm font-semibold mb-1 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>Área</label>
                <select
                  value={formAreaId}
                  onChange={e => setFormAreaId(e.target.value ? parseInt(e.target.value) : '')}
                  className={inputClass}
                  required
                >
                  <option value="">Selecione uma área</option>
                  {areas.filter(a => myAreaIds.has(a.id)).map(a => (
                    <option key={a.id} value={a.id}>{a.nome}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className={`block text-sm font-semibold mb-1 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>Quantidade</label>
                <input
                  type="text"
                  inputMode="numeric"
                  value={formatMilhar(formQuantidade)}
                  onChange={e => setFormQuantidade(stripMilhar(e.target.value))}
                  placeholder="Ex: 150"
                  className={inputClass}
                  required
                />
              </div>

              {/* Toggle kits */}
              <div className={`flex items-center justify-between p-3 rounded-xl border ${isDark ? 'border-gray-700 bg-gray-900/30' : 'border-gray-200 bg-gray-50'}`}>
                <div className="flex items-center gap-2">
                  <Package className={`w-4 h-4 ${isDark ? 'text-gray-400' : 'text-gray-500'}`} />
                  <span className={`text-sm font-semibold ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>Distribuir por Kit</span>
                </div>
                <button
                  type="button"
                  disabled={emCorte2 && c1KitMap.size > 0}
                  onClick={() => { if (!(emCorte2 && c1KitMap.size > 0)) setFormTemKit(v => !v); }}
                  title={emCorte2 && c1KitMap.size > 0 ? 'No Corte 2 a distribuição por Kit do Corte 1 é mantida e só recebe adições' : undefined}
                  className={`relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors focus:outline-none ${emCorte2 && c1KitMap.size > 0 ? 'opacity-60 cursor-not-allowed' : 'cursor-pointer'} ${formTemKit ? 'bg-amber-600' : isDark ? 'bg-gray-600' : 'bg-gray-300'}`}
                >
                  <span className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${formTemKit ? 'translate-x-6' : 'translate-x-1'}`} />
                </button>
              </div>

              {formTemKit && (
                <div className="space-y-2">
                  <div className="flex items-center justify-between mb-1">
                    <span className={`text-xs font-semibold uppercase tracking-wider ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Kits</span>
                    {formQuantidade && (
                      <span className={`text-xs ${
                        formKits.filter(k => k.nome_kit.trim() && parseInt(k.quantidade) > 0).reduce((s, k) => s + parseInt(k.quantidade), 0) === parseInt(formQuantidade)
                          ? 'text-emerald-400'
                          : 'text-amber-400'
                      }`}>
                        {formKits.filter(k => k.nome_kit.trim() && parseInt(k.quantidade) > 0).reduce((s, k) => s + parseInt(k.quantidade), 0)} / {formQuantidade}
                      </span>
                    )}
                  </div>
                  {emCorte2 ? (
                    <>
                      <div className="flex items-center gap-2 px-1 pb-0.5">
                        <div className="flex-1" />
                        <div className={`w-14 text-center text-[10px] uppercase tracking-wider ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>C1</div>
                        <div className={`w-14 text-center text-[10px] uppercase tracking-wider ${isDark ? 'text-blue-400' : 'text-blue-600'}`}>C2 +</div>
                        <div className={`w-14 text-center text-[10px] uppercase tracking-wider ${isDark ? 'text-emerald-400' : 'text-emerald-600'}`}>Total</div>
                      </div>
                      {formKits.map((kit, idx) => {
                        const isCam = camisetaAvulsaInfo.corte1_congelado && camisetaAvulsaInfo.teto > 0 && kit.nome_kit === KIT_CAMISETA_ORIGEM;
                        const kc1 = isCam ? camisetaAvulsaInfo.teto : (c1KitMap.get(kit.nome_kit) ?? 0);
                        const ktotal = parseInt(kit.quantidade) || 0;
                        const kc2 = ktotal - kc1;
                        return (
                          <div key={idx} className="flex items-center gap-2">
                            {KITS_DESCRICOES[kit.nome_kit] && (
                              <div className="relative group flex items-center">
                                <Info className={`w-4 h-4 cursor-help ${isDark ? 'text-gray-500 hover:text-gray-300' : 'text-gray-400 hover:text-gray-600'}`} />
                                <div className={`pointer-events-none absolute left-6 top-1/2 -translate-y-1/2 z-50 hidden group-hover:block whitespace-nowrap px-2.5 py-1.5 rounded-lg text-xs shadow-lg ${isDark ? 'bg-gray-700 text-gray-100 border border-gray-600' : 'bg-gray-900 text-white'}`}>
                                  {KITS_DESCRICOES[kit.nome_kit]}
                                </div>
                              </div>
                            )}
                            <div className={`flex-1 px-3 py-2 rounded-lg border text-sm ${isDark ? 'bg-gray-900/40 border-gray-700 text-gray-200' : 'bg-gray-50 border-gray-200 text-gray-700'}`}>
                              {isCam ? KIT_CAMISETA_LABEL : kit.nome_kit}
                              {isCam && <span className={`ml-1 text-[10px] ${isDark ? 'text-amber-400' : 'text-amber-600'}`}>(só diminui)</span>}
                            </div>
                            <div className={`w-14 px-2 py-2 rounded-lg border text-sm text-center ${c2BoxRead}`}>{kc1}</div>
                            {isCam ? (
                              <div className={`w-14 px-2 py-2 rounded-lg border text-sm text-center ${kc2 < 0 ? (isDark ? 'bg-red-500/10 border-red-500/30 text-red-300' : 'bg-red-50 border-red-200 text-red-600') : c2BoxRead}`}>{kc2}</div>
                            ) : (
                              <input
                                type="text"
                                inputMode="numeric"
                                value={formatMilhar(Math.max(0, kc2))}
                                onChange={e => { const c2 = Math.max(0, parseInt(stripMilhar(e.target.value)) || 0); updateKit(idx, 'quantidade', String(kc1 + c2)); }}
                                placeholder="0"
                                min={0}
                                className={`w-14 px-2 py-2 rounded-lg border text-sm text-center ${isDark ? 'bg-gray-800/50 border-gray-600 text-white placeholder-gray-500' : 'bg-white border-gray-300 text-gray-900 placeholder-gray-400'} focus:outline-none focus:ring-2 focus:ring-blue-500`}
                              />
                            )}
                            {isCam ? (
                              <input
                                type="text"
                                inputMode="numeric"
                                value={formatMilhar(kit.quantidade)}
                                onChange={e => { let val = stripMilhar(e.target.value); const n = parseInt(val); if (!isNaN(n) && n > camisetaAvulsaInfo.teto) val = String(camisetaAvulsaInfo.teto); updateKit(idx, 'quantidade', val); }}
                                placeholder="0"
                                min={0}
                                max={camisetaAvulsaInfo.teto}
                                className={`w-14 px-2 py-2 rounded-lg border text-sm text-center font-bold ${isDark ? 'bg-gray-800/50 border-gray-600 text-white' : 'bg-white border-gray-300 text-gray-900'} focus:outline-none focus:ring-2 focus:ring-amber-500`}
                              />
                            ) : (
                              <div className={`w-14 px-2 py-2 rounded-lg border text-sm text-center font-bold ${isDark ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300' : 'bg-emerald-50 border-emerald-200 text-emerald-700'}`}>{ktotal}</div>
                            )}
                          </div>
                        );
                      })}
                    </>
                  ) : (
                  formKits.map((kit, idx) => (
                    <div key={idx} className="flex items-center gap-2">
                      {KITS_DESCRICOES[kit.nome_kit] && (
                        <div className="relative group flex items-center">
                          <Info className={`w-4 h-4 cursor-help ${isDark ? 'text-gray-500 hover:text-gray-300' : 'text-gray-400 hover:text-gray-600'}`} />
                          <div className={`pointer-events-none absolute left-6 top-1/2 -translate-y-1/2 z-50 hidden group-hover:block whitespace-nowrap px-2.5 py-1.5 rounded-lg text-xs shadow-lg ${isDark ? 'bg-gray-700 text-gray-100 border border-gray-600' : 'bg-gray-900 text-white'}`}>
                            {KITS_DESCRICOES[kit.nome_kit]}
                          </div>
                        </div>
                      )}
                      <div className={`flex-1 px-3 py-2 rounded-lg border text-sm ${isDark ? 'bg-gray-900/40 border-gray-700 text-gray-200' : 'bg-gray-50 border-gray-200 text-gray-700'}`}>
                        {kit.nome_kit}
                        {camisetaAvulsaInfo.corte1_congelado && camisetaAvulsaInfo.teto > 0 && kit.nome_kit === KIT_CAMISETA_ORIGEM && (
                          <span className={`ml-2 text-xs ${isDark ? 'text-amber-400' : 'text-amber-600'}`}>
                            (Corte 1: {camisetaAvulsaInfo.teto} → máx. {camisetaAvulsaInfo.teto}; só diminui)
                          </span>
                        )}
                      </div>
                      <input
                        type="text"
                        inputMode="numeric"
                        value={formatMilhar(kit.quantidade)}
                        onChange={e => {
                          let val = stripMilhar(e.target.value);
                          if (camisetaAvulsaInfo.corte1_congelado && camisetaAvulsaInfo.teto > 0 && kit.nome_kit === KIT_CAMISETA_ORIGEM) {
                            const n = parseInt(val);
                            if (!isNaN(n) && n > camisetaAvulsaInfo.teto) val = String(camisetaAvulsaInfo.teto);
                          }
                          updateKit(idx, 'quantidade', val);
                        }}
                        placeholder="Qtd"
                        min={0}
                        max={(camisetaAvulsaInfo.corte1_congelado && camisetaAvulsaInfo.teto > 0 && kit.nome_kit === KIT_CAMISETA_ORIGEM) ? camisetaAvulsaInfo.teto : undefined}
                        className={`w-20 px-3 py-2 rounded-lg border text-sm ${isDark ? 'bg-gray-800/50 border-gray-600 text-white placeholder-gray-500' : 'bg-white border-gray-300 text-gray-900 placeholder-gray-400'} focus:outline-none focus:ring-2 focus:ring-amber-500`}
                      />
                    </div>
                  ))
                  )}
                </div>
              )}

              {/* Toggle clientes */}
              <div className={`flex items-center justify-between p-3 rounded-xl border ${isDark ? 'border-gray-700 bg-gray-900/30' : 'border-gray-200 bg-gray-50'}`}>
                <div className="flex items-center gap-2">
                  <Users className={`w-4 h-4 ${isDark ? 'text-gray-400' : 'text-gray-500'}`} />
                  <span className={`text-sm font-semibold ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>Distribuir por cliente</span>
                </div>
                <button
                  type="button"
                  disabled={emCorte2 && c1CliMap.size > 0}
                  onClick={() => { if (!(emCorte2 && c1CliMap.size > 0)) setFormTemCliente(v => !v); }}
                  title={emCorte2 && c1CliMap.size > 0 ? 'No Corte 2 a distribuição por cliente do Corte 1 é mantida e só recebe adições' : undefined}
                  className={`relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors focus:outline-none ${emCorte2 && c1CliMap.size > 0 ? 'opacity-60 cursor-not-allowed' : 'cursor-pointer'} ${formTemCliente ? 'bg-violet-600' : isDark ? 'bg-gray-600' : 'bg-gray-300'}`}
                >
                  <span className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${formTemCliente ? 'translate-x-6' : 'translate-x-1'}`} />
                </button>
              </div>

              {formTemCliente && (
                <div className="space-y-2">
                  <div className="flex items-center justify-between mb-1">
                    <span className={`text-xs font-semibold uppercase tracking-wider ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Clientes</span>
                    {formQuantidade && (
                      <span className={`text-xs ${
                        formClientes.filter(c => c.nome_cliente.trim() && parseInt(c.quantidade) > 0).reduce((s, c) => s + parseInt(c.quantidade), 0) === parseInt(formQuantidade)
                          ? 'text-emerald-400'
                          : 'text-amber-400'
                      }`}>
                        {formClientes.filter(c => c.nome_cliente.trim() && parseInt(c.quantidade) > 0).reduce((s, c) => s + parseInt(c.quantidade), 0)} / {formQuantidade}
                      </span>
                    )}
                  </div>
                  {emCorte2 ? (
                    formClientes.map((cliente, idx) => {
                      const cnome = cliente.nome_cliente.trim();
                      const isC1Row = c1CliMap.has(cnome);
                      const cc1 = c1CliMap.get(cnome) ?? 0;
                      const ctotal = parseInt(cliente.quantidade) || 0;
                      const cc2 = ctotal - cc1;
                      return (
                        <div key={idx} className={`space-y-1.5 rounded-xl border p-2 ${isDark ? 'border-gray-700 bg-gray-900/20' : 'border-gray-200 bg-gray-50/50'}`}>
                          <div className="flex items-center gap-2">
                            <input
                              type="text"
                              value={cliente.nome_cliente}
                              onChange={e => updateCliente(idx, 'nome_cliente', e.target.value)}
                              placeholder="Nome do cliente"
                              readOnly={isC1Row}
                              title={isC1Row ? 'Cliente do Corte 1 — não pode ser renomeado nem removido (só recebe adições)' : undefined}
                              className={`flex-1 px-3 py-2 rounded-lg border text-sm ${isC1Row ? (isDark ? 'bg-gray-900/40 border-gray-700 text-gray-300 cursor-not-allowed' : 'bg-gray-100 border-gray-200 text-gray-600 cursor-not-allowed') : (isDark ? 'bg-gray-800/50 border-gray-600 text-white placeholder-gray-500' : 'bg-white border-gray-300 text-gray-900 placeholder-gray-400')} focus:outline-none focus:ring-2 focus:ring-violet-500`}
                            />
                            {!isC1Row && formClientes.length > 1 && (
                              <button type="button" onClick={() => removeCliente(idx)} className="p-1.5 rounded-lg text-red-400 hover:bg-red-500/20 transition-colors">
                                <X className="w-4 h-4" />
                              </button>
                            )}
                          </div>
                          <div className="grid grid-cols-3 gap-2">
                            <div>
                              <div className={`text-[10px] uppercase tracking-wider mb-0.5 ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>Corte 1</div>
                              <div className={`px-2 py-1.5 rounded-lg border text-sm text-center ${c2BoxRead}`}>{cc1}</div>
                            </div>
                            <div>
                              <div className={`text-[10px] uppercase tracking-wider mb-0.5 ${isDark ? 'text-blue-400' : 'text-blue-600'}`}>Corte 2 (+)</div>
                              <input
                                type="text"
                                inputMode="numeric"
                                value={formatMilhar(Math.max(0, cc2))}
                                onChange={e => { const c2 = Math.max(0, parseInt(stripMilhar(e.target.value)) || 0); updateCliente(idx, 'quantidade', String(cc1 + c2)); }}
                                placeholder="0"
                                min={0}
                                className={`w-full px-2 py-1.5 rounded-lg border text-sm text-center ${isDark ? 'bg-gray-800/50 border-gray-600 text-white placeholder-gray-500' : 'bg-white border-gray-300 text-gray-900 placeholder-gray-400'} focus:outline-none focus:ring-2 focus:ring-blue-500`}
                              />
                            </div>
                            <div>
                              <div className={`text-[10px] uppercase tracking-wider mb-0.5 ${isDark ? 'text-emerald-400' : 'text-emerald-600'}`}>Total</div>
                              <div className={`px-2 py-1.5 rounded-lg border text-sm text-center font-bold ${isDark ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300' : 'bg-emerald-50 border-emerald-200 text-emerald-700'}`}>{ctotal}</div>
                            </div>
                          </div>
                        </div>
                      );
                    })
                  ) : (
                  formClientes.map((cliente, idx) => (
                    <div key={idx} className="flex items-center gap-2">
                      <input
                        type="text"
                        value={cliente.nome_cliente}
                        onChange={e => updateCliente(idx, 'nome_cliente', e.target.value)}
                        placeholder="Nome do cliente"
                        className={`flex-1 px-3 py-2 rounded-lg border text-sm ${isDark ? 'bg-gray-800/50 border-gray-600 text-white placeholder-gray-500' : 'bg-white border-gray-300 text-gray-900 placeholder-gray-400'} focus:outline-none focus:ring-2 focus:ring-violet-500`}
                      />
                      <input
                        type="text"
                        inputMode="numeric"
                        value={formatMilhar(cliente.quantidade)}
                        onChange={e => updateCliente(idx, 'quantidade', stripMilhar(e.target.value))}
                        placeholder="Qtd"
                        min={1}
                        className={`w-20 px-3 py-2 rounded-lg border text-sm ${isDark ? 'bg-gray-800/50 border-gray-600 text-white placeholder-gray-500' : 'bg-white border-gray-300 text-gray-900 placeholder-gray-400'} focus:outline-none focus:ring-2 focus:ring-violet-500`}
                      />
                      {formClientes.length > 1 && (
                        <button type="button" onClick={() => removeCliente(idx)} className="p-1.5 rounded-lg text-red-400 hover:bg-red-500/20 transition-colors">
                          <X className="w-4 h-4" />
                        </button>
                      )}
                    </div>
                  ))
                  )}
                  <button
                    type="button"
                    onClick={addCliente}
                    className={`flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-lg transition-colors ${isDark ? 'text-violet-400 hover:bg-violet-500/20' : 'text-violet-600 hover:bg-violet-50'}`}
                  >
                    <Plus className="w-3.5 h-3.5" />
                    Adicionar cliente
                  </button>
                </div>
              )}

              <div className="flex justify-end gap-3 pt-4">
                <button
                  type="button"
                  onClick={() => setShowCreateModal(false)}
                  className={`px-4 py-2.5 rounded-xl font-semibold ${isDark ? 'bg-gray-700 text-gray-300 hover:bg-gray-600' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'}`}
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  className="px-6 py-2.5 rounded-xl bg-gradient-to-r from-violet-600 to-blue-600 text-white font-semibold shadow-lg hover:shadow-xl transition-all"
                >
                  Criar
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Edit Modal */}
      {editingProjecao && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
          <div className={`w-full max-w-lg max-h-[90vh] overflow-y-auto rounded-2xl shadow-2xl ${isDark ? 'bg-gray-800 border border-gray-700' : 'bg-white'}`}>
            <div className="flex items-center justify-between p-6 border-b border-gray-700/50">
              <div>
                <h2 className={`text-xl font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>{emCorte2 ? 'Projeção Ajuste' : 'Projeção Convicta'}</h2>
                <p className={`text-sm mt-1 ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                  {editingProjecao.evento_nome} — {editingProjecao.area_projecao_nome}
                </p>
              </div>
              <button onClick={() => setEditingProjecao(null)} className="p-2 rounded-lg hover:bg-gray-700/50">
                <X className={`w-5 h-5 ${isDark ? 'text-gray-400' : 'text-gray-500'}`} />
              </button>
            </div>
            <form onSubmit={handleUpdate} className="p-6 space-y-4">
              {editGateBlocked ? (
                <div className="py-10 text-center space-y-3">
                  {corte1DistError ? (
                    <>
                      <p className={`text-sm ${isDark ? 'text-red-400' : 'text-red-600'}`}>Não foi possível carregar os dados do corte. A edição fica bloqueada até confirmar a fase do corte.</p>
                      <button
                        type="button"
                        onClick={() => editingProjecao && loadCorteInfo(editingProjecao.evento_id, editingProjecao.area_projecao_id)}
                        className={`px-4 py-2 rounded-xl font-semibold text-sm ${isDark ? 'bg-gray-700 text-gray-200 hover:bg-gray-600' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'}`}
                      >
                        Tentar novamente
                      </button>
                    </>
                  ) : (
                    <p className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Carregando dados do corte…</p>
                  )}
                </div>
              ) : (
              <>
              {emCorte2 ? (
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <label className={`block text-sm font-semibold ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>Quantidade</label>
                  </div>
                  <div className="grid grid-cols-3 gap-2">
                    <div>
                      <div className={`text-[10px] uppercase tracking-wider mb-1 ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>Projeção Convicta</div>
                      <div className={`px-3 py-2 rounded-lg border text-sm ${c2BoxRead}`}>{formatNumber(c1Qty)}</div>
                    </div>
                    <div>
                      <div className={`text-[10px] uppercase tracking-wider mb-1 ${isDark ? 'text-blue-400' : 'text-blue-600'}`}>Projeção Ajuste</div>
                      <div className={`flex items-center rounded-lg border overflow-hidden ${isDark ? 'bg-gray-800/50 border-gray-600' : 'bg-white border-gray-300'} focus-within:ring-2 focus-within:ring-blue-500`}>
                        <button
                          type="button"
                          onClick={() => { const c2 = Math.max(0, ((parseInt(formQuantidade) || 0) - c1Qty) - 1); setFormQuantidade(String(c1Qty + c2)); }}
                          className={`px-2 py-2 text-sm font-bold shrink-0 select-none transition-colors ${isDark ? 'text-gray-300 hover:bg-gray-700' : 'text-gray-600 hover:bg-gray-100'}`}
                        >−</button>
                        <input
                          type="text"
                          inputMode="numeric"
                          value={formatMilhar(Math.max(0, (parseInt(formQuantidade) || 0) - c1Qty))}
                          onChange={e => { const c2 = Math.max(0, parseInt(stripMilhar(e.target.value)) || 0); setFormQuantidade(String(c1Qty + c2)); }}
                          placeholder="0"
                          className={`flex-1 min-w-0 py-2 text-sm text-center bg-transparent border-0 focus:outline-none focus:ring-0 ${isDark ? 'text-white placeholder-gray-500' : 'text-gray-900 placeholder-gray-400'}`}
                        />
                        <button
                          type="button"
                          onClick={() => { const c2 = Math.max(0, ((parseInt(formQuantidade) || 0) - c1Qty)) + 1; setFormQuantidade(String(c1Qty + c2)); }}
                          className={`px-2 py-2 text-sm font-bold shrink-0 select-none transition-colors ${isDark ? 'text-gray-300 hover:bg-gray-700' : 'text-gray-600 hover:bg-gray-100'}`}
                        >+</button>
                      </div>
                    </div>
                    <div>
                      <div className={`text-[10px] uppercase tracking-wider mb-1 ${isDark ? 'text-emerald-400' : 'text-emerald-600'}`}>Total</div>
                      <div className={`px-3 py-2 rounded-lg border text-sm font-bold ${isDark ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300' : 'bg-emerald-50 border-emerald-200 text-emerald-700'}`}>{formatNumber(parseInt(formQuantidade) || 0)}</div>
                    </div>
                  </div>
                  {corte1Dist?.fonte === 'aproximado' && (
                    <p className={`mt-1.5 text-[11px] ${isDark ? 'text-amber-400' : 'text-amber-600'}`}>Corte 1 aproximado (evento sem foto registrada — usando valores atuais).</p>
                  )}
                </div>
              ) : (
                <div>
                  <label className={`block text-sm font-semibold mb-1 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>Quantidade</label>
                  <input
                    type="text"
                    inputMode="numeric"
                    value={formatMilhar(formQuantidade)}
                    onChange={e => setFormQuantidade(stripMilhar(e.target.value))}
                    placeholder="Ex: 150"
                    className={inputClass}
                    required
                  />
                </div>
              )}

              {/* Toggle kits */}
              <div className={`flex items-center justify-between p-3 rounded-xl border ${isDark ? 'border-gray-700 bg-gray-900/30' : 'border-gray-200 bg-gray-50'}`}>
                <div className="flex items-center gap-2">
                  <Package className={`w-4 h-4 ${isDark ? 'text-gray-400' : 'text-gray-500'}`} />
                  <span className={`text-sm font-semibold ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>Distribuir por Kit</span>
                </div>
                <button
                  type="button"
                  disabled={emCorte2 && c1KitMap.size > 0}
                  onClick={() => { if (!(emCorte2 && c1KitMap.size > 0)) setFormTemKit(v => !v); }}
                  title={emCorte2 && c1KitMap.size > 0 ? 'No Corte 2 a distribuição por Kit do Corte 1 é mantida e só recebe adições' : undefined}
                  className={`relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors focus:outline-none ${emCorte2 && c1KitMap.size > 0 ? 'opacity-60 cursor-not-allowed' : 'cursor-pointer'} ${formTemKit ? 'bg-amber-600' : isDark ? 'bg-gray-600' : 'bg-gray-300'}`}
                >
                  <span className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${formTemKit ? 'translate-x-6' : 'translate-x-1'}`} />
                </button>
              </div>

              {formTemKit && (
                <div className="space-y-2">
                  <div className="flex items-center justify-between mb-1">
                    <span className={`text-xs font-semibold uppercase tracking-wider ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Kits</span>
                    {formQuantidade && (
                      <span className={`text-xs ${
                        formKits.filter(k => k.nome_kit.trim() && parseInt(k.quantidade) > 0).reduce((s, k) => s + parseInt(k.quantidade), 0) === parseInt(formQuantidade)
                          ? 'text-emerald-400'
                          : 'text-amber-400'
                      }`}>
                        {formKits.filter(k => k.nome_kit.trim() && parseInt(k.quantidade) > 0).reduce((s, k) => s + parseInt(k.quantidade), 0)} / {formQuantidade}
                      </span>
                    )}
                  </div>
                  {emCorte2 ? (
                    <>
                      <div className="flex items-center gap-2 px-1 pb-0.5">
                        <div className="flex-1" />
                        <div className={`w-14 text-center text-[10px] uppercase tracking-wider ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>Convicta</div>
                        <div className={`w-24 text-center text-[10px] uppercase tracking-wider ${isDark ? 'text-blue-400' : 'text-blue-600'}`}>Ajuste</div>
                        <div className={`w-14 text-center text-[10px] uppercase tracking-wider ${isDark ? 'text-emerald-400' : 'text-emerald-600'}`}>Total</div>
                      </div>
                      {formKits.map((kit, idx) => {
                        const isCam = camisetaAvulsaInfo.corte1_congelado && camisetaAvulsaInfo.teto > 0 && kit.nome_kit === KIT_CAMISETA_ORIGEM;
                        const kc1 = isCam ? camisetaAvulsaInfo.teto : (c1KitMap.get(kit.nome_kit) ?? 0);
                        const ktotal = parseInt(kit.quantidade) || 0;
                        const kc2 = ktotal - kc1;
                        return (
                          <div key={idx} className="flex items-center gap-2">
                            {KITS_DESCRICOES[kit.nome_kit] && (
                              <div className="relative group flex items-center">
                                <Info className={`w-4 h-4 cursor-help ${isDark ? 'text-gray-500 hover:text-gray-300' : 'text-gray-400 hover:text-gray-600'}`} />
                                <div className={`pointer-events-none absolute left-6 top-1/2 -translate-y-1/2 z-50 hidden group-hover:block whitespace-nowrap px-2.5 py-1.5 rounded-lg text-xs shadow-lg ${isDark ? 'bg-gray-700 text-gray-100 border border-gray-600' : 'bg-gray-900 text-white'}`}>
                                  {KITS_DESCRICOES[kit.nome_kit]}
                                </div>
                              </div>
                            )}
                            <div className={`flex-1 px-3 py-2 rounded-lg border text-sm ${isDark ? 'bg-gray-900/40 border-gray-700 text-gray-200' : 'bg-gray-50 border-gray-200 text-gray-700'}`}>
                              {isCam ? KIT_CAMISETA_LABEL : kit.nome_kit}
                              {isCam && <span className={`ml-1 text-[10px] ${isDark ? 'text-amber-400' : 'text-amber-600'}`}>(só diminui)</span>}
                            </div>
                            <div className={`w-14 px-2 py-2 rounded-lg border text-sm text-center ${c2BoxRead}`}>{kc1}</div>
                            {isCam ? (
                              <div className={`w-24 flex items-center rounded-lg border overflow-hidden focus-within:ring-2 focus-within:ring-blue-500 ${kc2 < 0 ? (isDark ? 'bg-red-500/10 border-red-500/30' : 'bg-red-50 border-red-200') : (isDark ? 'bg-gray-800/50 border-gray-600' : 'bg-white border-gray-300')}`}>
                                <button
                                  type="button"
                                  onClick={() => { let c2 = kc2 - 1; if (c2 < -kc1) c2 = -kc1; updateKit(idx, 'quantidade', String(kc1 + c2)); }}
                                  className={`px-1.5 py-2 text-sm font-bold shrink-0 select-none transition-colors ${isDark ? 'text-red-400 hover:bg-red-500/20' : 'text-red-600 hover:bg-red-100'}`}
                                >−</button>
                                <input
                                  type="text"
                                  inputMode="numeric"
                                  value={formatMilhar(kc2)}
                                  onChange={e => { let c2 = parseInt(stripMilhar(e.target.value)); if (isNaN(c2)) c2 = 0; if (c2 > 0) c2 = 0; if (c2 < -kc1) c2 = -kc1; updateKit(idx, 'quantidade', String(kc1 + c2)); }}
                                  placeholder="0"
                                  className={`flex-1 min-w-0 py-2 text-xs text-center bg-transparent border-0 focus:outline-none focus:ring-0 font-semibold ${kc2 < 0 ? (isDark ? 'text-red-300' : 'text-red-600') : (isDark ? 'text-white' : 'text-gray-900')}`}
                                />
                                <button
                                  type="button"
                                  onClick={() => { let c2 = kc2 + 1; if (c2 > 0) c2 = 0; updateKit(idx, 'quantidade', String(kc1 + c2)); }}
                                  className={`px-1.5 py-2 text-sm font-bold shrink-0 select-none transition-colors ${isDark ? 'text-gray-400 hover:bg-gray-700' : 'text-gray-500 hover:bg-gray-100'}`}
                                >+</button>
                              </div>
                            ) : (
                              <div className={`w-24 flex items-center rounded-lg border overflow-hidden focus-within:ring-2 focus-within:ring-blue-500 ${isDark ? 'bg-gray-800/50 border-gray-600' : 'bg-white border-gray-300'}`}>
                                <button
                                  type="button"
                                  onClick={() => { const c2 = Math.max(0, kc2 - 1); updateKit(idx, 'quantidade', String(kc1 + c2)); }}
                                  className={`px-1.5 py-2 text-sm font-bold shrink-0 select-none transition-colors ${isDark ? 'text-gray-300 hover:bg-gray-700' : 'text-gray-600 hover:bg-gray-100'}`}
                                >−</button>
                                <input
                                  type="text"
                                  inputMode="numeric"
                                  value={formatMilhar(Math.max(0, kc2))}
                                  onChange={e => { const c2 = Math.max(0, parseInt(stripMilhar(e.target.value)) || 0); updateKit(idx, 'quantidade', String(kc1 + c2)); }}
                                  placeholder="0"
                                  className={`flex-1 min-w-0 py-2 text-xs text-center bg-transparent border-0 focus:outline-none focus:ring-0 ${isDark ? 'text-white placeholder-gray-500' : 'text-gray-900 placeholder-gray-400'}`}
                                />
                                <button
                                  type="button"
                                  onClick={() => { const c2 = Math.max(0, kc2) + 1; updateKit(idx, 'quantidade', String(kc1 + c2)); }}
                                  className={`px-1.5 py-2 text-sm font-bold shrink-0 select-none transition-colors ${isDark ? 'text-gray-300 hover:bg-gray-700' : 'text-gray-600 hover:bg-gray-100'}`}
                                >+</button>
                              </div>
                            )}
                            <div className={`w-14 px-2 py-2 rounded-lg border text-sm text-center font-bold ${isDark ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300' : 'bg-emerald-50 border-emerald-200 text-emerald-700'}`}>{ktotal}</div>
                          </div>
                        );
                      })}
                    </>
                  ) : (
                  formKits.map((kit, idx) => (
                    <div key={idx} className="flex items-center gap-2">
                      {KITS_DESCRICOES[kit.nome_kit] && (
                        <div className="relative group flex items-center">
                          <Info className={`w-4 h-4 cursor-help ${isDark ? 'text-gray-500 hover:text-gray-300' : 'text-gray-400 hover:text-gray-600'}`} />
                          <div className={`pointer-events-none absolute left-6 top-1/2 -translate-y-1/2 z-50 hidden group-hover:block whitespace-nowrap px-2.5 py-1.5 rounded-lg text-xs shadow-lg ${isDark ? 'bg-gray-700 text-gray-100 border border-gray-600' : 'bg-gray-900 text-white'}`}>
                            {KITS_DESCRICOES[kit.nome_kit]}
                          </div>
                        </div>
                      )}
                      <div className={`flex-1 px-3 py-2 rounded-lg border text-sm ${isDark ? 'bg-gray-900/40 border-gray-700 text-gray-200' : 'bg-gray-50 border-gray-200 text-gray-700'}`}>
                        {kit.nome_kit}
                        {camisetaAvulsaInfo.corte1_congelado && camisetaAvulsaInfo.teto > 0 && kit.nome_kit === KIT_CAMISETA_ORIGEM && (
                          <span className={`ml-2 text-xs ${isDark ? 'text-amber-400' : 'text-amber-600'}`}>
                            (Corte 1: {camisetaAvulsaInfo.teto} → máx. {camisetaAvulsaInfo.teto}; só diminui)
                          </span>
                        )}
                      </div>
                      <input
                        type="text"
                        inputMode="numeric"
                        value={formatMilhar(kit.quantidade)}
                        onChange={e => {
                          let val = stripMilhar(e.target.value);
                          if (camisetaAvulsaInfo.corte1_congelado && camisetaAvulsaInfo.teto > 0 && kit.nome_kit === KIT_CAMISETA_ORIGEM) {
                            const n = parseInt(val);
                            if (!isNaN(n) && n > camisetaAvulsaInfo.teto) val = String(camisetaAvulsaInfo.teto);
                          }
                          updateKit(idx, 'quantidade', val);
                        }}
                        placeholder="Qtd"
                        min={0}
                        max={(camisetaAvulsaInfo.corte1_congelado && camisetaAvulsaInfo.teto > 0 && kit.nome_kit === KIT_CAMISETA_ORIGEM) ? camisetaAvulsaInfo.teto : undefined}
                        className={`w-20 px-3 py-2 rounded-lg border text-sm ${isDark ? 'bg-gray-800/50 border-gray-600 text-white placeholder-gray-500' : 'bg-white border-gray-300 text-gray-900 placeholder-gray-400'} focus:outline-none focus:ring-2 focus:ring-amber-500`}
                      />
                    </div>
                  ))
                  )}
                </div>
              )}

              {/* Toggle clientes */}
              <div className={`flex items-center justify-between p-3 rounded-xl border ${isDark ? 'border-gray-700 bg-gray-900/30' : 'border-gray-200 bg-gray-50'}`}>
                <div className="flex items-center gap-2">
                  <Users className={`w-4 h-4 ${isDark ? 'text-gray-400' : 'text-gray-500'}`} />
                  <span className={`text-sm font-semibold ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>Distribuir por cliente</span>
                </div>
                <button
                  type="button"
                  disabled={emCorte2 && c1CliMap.size > 0}
                  onClick={() => { if (!(emCorte2 && c1CliMap.size > 0)) setFormTemCliente(v => !v); }}
                  title={emCorte2 && c1CliMap.size > 0 ? 'No Corte 2 a distribuição por cliente do Corte 1 é mantida e só recebe adições' : undefined}
                  className={`relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors focus:outline-none ${emCorte2 && c1CliMap.size > 0 ? 'opacity-60 cursor-not-allowed' : 'cursor-pointer'} ${formTemCliente ? 'bg-violet-600' : isDark ? 'bg-gray-600' : 'bg-gray-300'}`}
                >
                  <span className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${formTemCliente ? 'translate-x-6' : 'translate-x-1'}`} />
                </button>
              </div>

              {formTemCliente && (
                <div className="space-y-2">
                  <div className="flex items-center justify-between mb-1">
                    <span className={`text-xs font-semibold uppercase tracking-wider ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Clientes</span>
                    {formQuantidade && (
                      <span className={`text-xs ${
                        formClientes.filter(c => c.nome_cliente.trim() && parseInt(c.quantidade) > 0).reduce((s, c) => s + parseInt(c.quantidade), 0) === parseInt(formQuantidade)
                          ? 'text-emerald-400'
                          : 'text-amber-400'
                      }`}>
                        {formClientes.filter(c => c.nome_cliente.trim() && parseInt(c.quantidade) > 0).reduce((s, c) => s + parseInt(c.quantidade), 0)} / {formQuantidade}
                      </span>
                    )}
                  </div>
                  {emCorte2 ? (
                    formClientes.map((cliente, idx) => {
                      const cnome = cliente.nome_cliente.trim();
                      const isC1Row = c1CliMap.has(cnome);
                      const cc1 = c1CliMap.get(cnome) ?? 0;
                      const ctotal = parseInt(cliente.quantidade) || 0;
                      const cc2 = ctotal - cc1;
                      return (
                        <div key={idx} className={`space-y-1.5 rounded-xl border p-2 ${isDark ? 'border-gray-700 bg-gray-900/20' : 'border-gray-200 bg-gray-50/50'}`}>
                          <div className="flex items-center gap-2">
                            <input
                              type="text"
                              value={cliente.nome_cliente}
                              onChange={e => updateCliente(idx, 'nome_cliente', e.target.value)}
                              placeholder="Nome do cliente"
                              readOnly={isC1Row}
                              title={isC1Row ? 'Cliente do Corte 1 — não pode ser renomeado nem removido (só recebe adições)' : undefined}
                              className={`flex-1 px-3 py-2 rounded-lg border text-sm ${isC1Row ? (isDark ? 'bg-gray-900/40 border-gray-700 text-gray-300 cursor-not-allowed' : 'bg-gray-100 border-gray-200 text-gray-600 cursor-not-allowed') : (isDark ? 'bg-gray-800/50 border-gray-600 text-white placeholder-gray-500' : 'bg-white border-gray-300 text-gray-900 placeholder-gray-400')} focus:outline-none focus:ring-2 focus:ring-violet-500`}
                            />
                            {!isC1Row && formClientes.length > 1 && (
                              <button type="button" onClick={() => removeCliente(idx)} className="p-1.5 rounded-lg text-red-400 hover:bg-red-500/20 transition-colors">
                                <X className="w-4 h-4" />
                              </button>
                            )}
                          </div>
                          <div className="grid grid-cols-3 gap-2">
                            <div>
                              <div className={`text-[10px] uppercase tracking-wider mb-0.5 ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>Projeção Convicta</div>
                              <div className={`px-2 py-1.5 rounded-lg border text-sm text-center ${c2BoxRead}`}>{cc1}</div>
                            </div>
                            <div>
                              <div className={`text-[10px] uppercase tracking-wider mb-0.5 ${isDark ? 'text-blue-400' : 'text-blue-600'}`}>Projeção Ajuste</div>
                              <input
                                type="text"
                                inputMode="numeric"
                                value={formatMilhar(Math.max(0, cc2))}
                                onChange={e => { const c2 = Math.max(0, parseInt(stripMilhar(e.target.value)) || 0); updateCliente(idx, 'quantidade', String(cc1 + c2)); }}
                                placeholder="0"
                                min={0}
                                className={`w-full px-2 py-1.5 rounded-lg border text-sm text-center ${isDark ? 'bg-gray-800/50 border-gray-600 text-white placeholder-gray-500' : 'bg-white border-gray-300 text-gray-900 placeholder-gray-400'} focus:outline-none focus:ring-2 focus:ring-blue-500`}
                              />
                            </div>
                            <div>
                              <div className={`text-[10px] uppercase tracking-wider mb-0.5 ${isDark ? 'text-emerald-400' : 'text-emerald-600'}`}>Total</div>
                              <div className={`px-2 py-1.5 rounded-lg border text-sm text-center font-bold ${isDark ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300' : 'bg-emerald-50 border-emerald-200 text-emerald-700'}`}>{ctotal}</div>
                            </div>
                          </div>
                        </div>
                      );
                    })
                  ) : (
                  formClientes.map((cliente, idx) => (
                    <div key={idx} className="flex items-center gap-2">
                      <input
                        type="text"
                        value={cliente.nome_cliente}
                        onChange={e => updateCliente(idx, 'nome_cliente', e.target.value)}
                        placeholder="Nome do cliente"
                        className={`flex-1 px-3 py-2 rounded-lg border text-sm ${isDark ? 'bg-gray-800/50 border-gray-600 text-white placeholder-gray-500' : 'bg-white border-gray-300 text-gray-900 placeholder-gray-400'} focus:outline-none focus:ring-2 focus:ring-violet-500`}
                      />
                      <input
                        type="text"
                        inputMode="numeric"
                        value={formatMilhar(cliente.quantidade)}
                        onChange={e => updateCliente(idx, 'quantidade', stripMilhar(e.target.value))}
                        placeholder="Qtd"
                        min={1}
                        className={`w-20 px-3 py-2 rounded-lg border text-sm ${isDark ? 'bg-gray-800/50 border-gray-600 text-white placeholder-gray-500' : 'bg-white border-gray-300 text-gray-900 placeholder-gray-400'} focus:outline-none focus:ring-2 focus:ring-violet-500`}
                      />
                      {formClientes.length > 1 && (
                        <button type="button" onClick={() => removeCliente(idx)} className="p-1.5 rounded-lg text-red-400 hover:bg-red-500/20 transition-colors">
                          <X className="w-4 h-4" />
                        </button>
                      )}
                    </div>
                  ))
                  )}
                  <button
                    type="button"
                    onClick={addCliente}
                    className={`flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-lg transition-colors ${isDark ? 'text-violet-400 hover:bg-violet-500/20' : 'text-violet-600 hover:bg-violet-50'}`}
                  >
                    <Plus className="w-3.5 h-3.5" />
                    Adicionar cliente
                  </button>
                </div>
              )}
              </>
              )}

              <div className="flex justify-end gap-3 pt-4">
                <button
                  type="button"
                  onClick={() => setEditingProjecao(null)}
                  className={`px-4 py-2.5 rounded-xl font-semibold ${isDark ? 'bg-gray-700 text-gray-300 hover:bg-gray-600' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'}`}
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  disabled={editGateBlocked}
                  className={`px-6 py-2.5 rounded-xl bg-gradient-to-r from-violet-600 to-blue-600 text-white font-semibold shadow-lg transition-all ${editGateBlocked ? 'opacity-50 cursor-not-allowed' : 'hover:shadow-xl'}`}
                >
                  Salvar
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Histórico Modal */}
      {showHistorico && historicoProjecao && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
          <div className={`w-full max-w-2xl max-h-[80vh] rounded-2xl shadow-2xl flex flex-col ${isDark ? 'bg-gray-800 border border-gray-700' : 'bg-white'}`}>
            <div className="flex items-center justify-between p-6 border-b border-gray-700/50">
              <div>
                <h2 className={`text-xl font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>Histórico de Alterações</h2>
                <p className={`text-sm mt-1 ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                  {historicoProjecao.evento_nome} — {historicoProjecao.area_projecao_nome}
                </p>
              </div>
              <button onClick={() => setShowHistorico(false)} className="p-2 rounded-lg hover:bg-gray-700/50">
                <X className={`w-5 h-5 ${isDark ? 'text-gray-400' : 'text-gray-500'}`} />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-6">
              {historico.length === 0 ? (
                <p className={`text-center py-8 ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Nenhum registro no histórico</p>
              ) : (
                <div className="space-y-4">
                  {historico.map(h => {
                    const acaoConfig: Record<string, { bg: string; icon: React.ReactNode; label: string }> = {
                      CRIACAO: { bg: 'bg-emerald-500/20', icon: <Plus className={`w-5 h-5 ${isDark ? 'text-emerald-400' : 'text-emerald-600'}`} />, label: 'Criação' },
                      EDICAO: { bg: 'bg-amber-500/20', icon: <Pencil className={`w-5 h-5 ${isDark ? 'text-amber-400' : 'text-amber-600'}`} />, label: 'Edição' },
                      DELECAO: { bg: 'bg-red-500/20', icon: <Trash2 className={`w-5 h-5 ${isDark ? 'text-red-400' : 'text-red-600'}`} />, label: 'Exclusão' },
                      RESTAURACAO: { bg: 'bg-blue-500/20', icon: <RotateCcw className={`w-5 h-5 ${isDark ? 'text-blue-400' : 'text-blue-600'}`} />, label: 'Restauração' },
                      TRAVAMENTO: { bg: 'bg-red-500/20', icon: <Lock className={`w-5 h-5 ${isDark ? 'text-red-400' : 'text-red-600'}`} />, label: 'Travamento' },
                      DESTRAVAMENTO: { bg: 'bg-orange-500/20', icon: <LockOpen className={`w-5 h-5 ${isDark ? 'text-orange-400' : 'text-orange-600'}`} />, label: 'Destravamento' },
                    };
                    const cfg = acaoConfig[h.acao] || acaoConfig.EDICAO;
                    return (
                    <div key={h.id} className={`flex gap-4 p-4 rounded-xl ${isDark ? 'bg-gray-900/50' : 'bg-gray-50'}`}>
                      <div className={`flex-shrink-0 w-10 h-10 rounded-full flex items-center justify-center ${cfg.bg}`}>
                        {cfg.icon}
                      </div>
                      <div className="flex-1">
                        <div className="flex items-center justify-between">
                          <span className={`font-semibold text-sm ${isDark ? 'text-white' : 'text-gray-900'}`}>
                            {cfg.label}
                          </span>
                          <span className={`text-xs ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>
                            {formatDateTime(h.created_at)}
                          </span>
                        </div>
                        <p className={`text-sm mt-1 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
                          por <strong>{h.usuario_nome}</strong>
                        </p>
                        {h.campo_alterado && (() => {
                          const campo = h.campo_alterado;
                          if (campo === 'Cliente adicionado') {
                            return (
                              <div className={`mt-2 flex items-center gap-2 text-sm`}>
                                <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-xs font-bold ${isDark ? 'bg-emerald-500/20 text-emerald-400' : 'bg-emerald-100 text-emerald-700'}`}>
                                  <Plus className="w-3 h-3" /> cliente
                                </span>
                                <span className={`font-medium ${isDark ? 'text-emerald-400' : 'text-emerald-600'}`}>{h.valor_novo}</span>
                              </div>
                            );
                          }
                          if (campo === 'Cliente removido') {
                            return (
                              <div className={`mt-2 flex items-center gap-2 text-sm`}>
                                <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-xs font-bold ${isDark ? 'bg-red-500/20 text-red-400' : 'bg-red-100 text-red-700'}`}>
                                  <X className="w-3 h-3" /> cliente
                                </span>
                                <span className={`font-medium line-through ${isDark ? 'text-red-400' : 'text-red-600'}`}>{h.valor_anterior}</span>
                              </div>
                            );
                          }
                          if (campo.startsWith('Cliente: ')) {
                            const clienteNome = campo.replace('Cliente: ', '');
                            return (
                              <div className={`mt-2 text-sm ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                                <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-xs font-bold mr-2 ${isDark ? 'bg-violet-500/20 text-violet-400' : 'bg-violet-100 text-violet-700'}`}>
                                  <Users className="w-3 h-3" /> {clienteNome}
                                </span>
                                <span className="line-through text-red-400 mr-1">{h.valor_anterior}</span>
                                <span className={`${isDark ? 'text-gray-500' : 'text-gray-400'} mr-1`}>→</span>
                                <span className="text-emerald-400 font-semibold">{h.valor_novo}</span>
                              </div>
                            );
                          }
                          return (
                            <div className={`mt-2 text-sm ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                              <span className="font-medium">{campo}:</span>{' '}
                              {h.valor_anterior && (
                                <span className="line-through text-red-400 mr-2">{h.valor_anterior}</span>
                              )}
                              <span className="text-emerald-400 font-semibold">{h.valor_novo}</span>
                            </div>
                          );
                        })()}
                      </div>
                    </div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Nova Área Modal */}
      {showCreateAreaModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
          <div className={`w-full max-w-md rounded-2xl shadow-2xl ${isDark ? 'bg-gray-800 border border-gray-700' : 'bg-white'}`}>
            <div className="flex items-center justify-between p-6 border-b border-gray-700/50">
              <h2 className={`text-xl font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>Nova Área</h2>
              <button onClick={() => setShowCreateAreaModal(false)} className="p-2 rounded-lg hover:bg-gray-700/50">
                <X className={`w-5 h-5 ${isDark ? 'text-gray-400' : 'text-gray-500'}`} />
              </button>
            </div>
            <form onSubmit={handleCreateArea} className="p-6 space-y-4">
              <div>
                <label className={`block text-sm font-semibold mb-2 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
                  Nome da Área
                </label>
                <input
                  type="text"
                  value={newAreaNome}
                  onChange={e => setNewAreaNome(e.target.value)}
                  placeholder="Ex: Site, Marketing, Operações..."
                  className={inputClass}
                  autoFocus
                />
              </div>
              <div className="flex justify-end gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setShowCreateAreaModal(false)}
                  className={`px-4 py-2.5 rounded-xl font-semibold ${isDark ? 'bg-gray-700 text-gray-300 hover:bg-gray-600' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'}`}
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  className="px-6 py-2.5 rounded-xl bg-gradient-to-r from-violet-600 to-blue-600 text-white font-semibold shadow-lg hover:shadow-xl transition-all"
                >
                  Criar Área
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Atribuir Usuários Modal */}
      {showAtribuirModal && atribuirArea && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
          <div className={`w-full max-w-lg max-h-[80vh] rounded-2xl shadow-2xl flex flex-col ${isDark ? 'bg-gray-800 border border-gray-700' : 'bg-white'}`}>
            <div className="flex items-center justify-between p-6 border-b border-gray-700/50">
              <div>
                <h2 className={`text-xl font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>Atribuir Usuários</h2>
                <p className={`text-sm mt-1 ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                  Área: {atribuirArea.nome}
                </p>
              </div>
              <button onClick={() => setShowAtribuirModal(false)} className="p-2 rounded-lg hover:bg-gray-700/50">
                <X className={`w-5 h-5 ${isDark ? 'text-gray-400' : 'text-gray-500'}`} />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-6">
              <p className={`text-sm mb-4 ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                Selecione os usuários que podem preencher projeções nesta área:
              </p>
              <div className="space-y-2">
                {allUsers
                  .filter(u => u.ativo !== false)
                  .map(u => (
                  <label
                    key={u.id}
                    className={`flex items-center gap-3 p-3 rounded-xl cursor-pointer transition-colors ${
                      selectedUserIds.includes(u.id)
                        ? isDark ? 'bg-violet-500/20 border border-violet-500/50' : 'bg-violet-50 border border-violet-200'
                        : isDark ? 'bg-gray-900/30 border border-gray-700/50 hover:bg-gray-700/30' : 'bg-gray-50 border border-gray-200 hover:bg-gray-100'
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={selectedUserIds.includes(u.id)}
                      onChange={() => {
                        setSelectedUserIds(prev =>
                          prev.includes(u.id)
                            ? prev.filter(id => id !== u.id)
                            : [...prev, u.id]
                        );
                      }}
                      className="w-4 h-4 rounded text-violet-500 focus:ring-violet-500"
                    />
                    <div>
                      <p className={`text-sm font-semibold ${isDark ? 'text-white' : 'text-gray-900'}`}>{u.nome}</p>
                      <p className={`text-xs ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>{u.email}</p>
                    </div>
                  </label>
                ))}
              </div>
            </div>
            <div className="flex justify-end gap-3 p-6 border-t border-gray-700/50">
              <button
                onClick={() => setShowAtribuirModal(false)}
                className={`px-4 py-2.5 rounded-xl font-semibold ${isDark ? 'bg-gray-700 text-gray-300 hover:bg-gray-600' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'}`}
              >
                Cancelar
              </button>
              <button
                onClick={handleAtribuir}
                className="px-6 py-2.5 rounded-xl bg-gradient-to-r from-violet-600 to-blue-600 text-white font-semibold shadow-lg hover:shadow-xl transition-all"
              >
                Salvar Atribuições
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Confirmation Modal */}
      {confirmModal && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <div className={`w-full max-w-md rounded-2xl shadow-2xl ${isDark ? 'bg-gray-800 border border-gray-700' : 'bg-white'}`}>
            <div className="p-6">
              <div className="flex items-start gap-4">
                <div className={`p-3 rounded-xl shrink-0 ${
                  confirmModal.variant === 'danger'
                    ? 'bg-red-500/15'
                    : confirmModal.variant === 'warning'
                      ? 'bg-amber-500/15'
                      : 'bg-blue-500/15'
                }`}>
                  <AlertTriangle className={`w-6 h-6 ${
                    confirmModal.variant === 'danger'
                      ? 'text-red-500'
                      : confirmModal.variant === 'warning'
                        ? 'text-amber-500'
                        : 'text-blue-500'
                  }`} />
                </div>
                <div className="flex-1 min-w-0">
                  <h3 className={`text-lg font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>
                    {confirmModal.title}
                  </h3>
                  <p className={`mt-2 text-sm leading-relaxed ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>
                    {confirmModal.message}
                  </p>
                </div>
              </div>
            </div>
            <div className={`flex items-center justify-end gap-3 px-6 py-4 border-t ${isDark ? 'border-gray-700' : 'border-gray-100'}`}>
              <button
                onClick={() => setConfirmModal(null)}
                className={`px-4 py-2.5 rounded-xl font-semibold text-sm transition-colors ${isDark ? 'bg-gray-700 text-gray-300 hover:bg-gray-600' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'}`}
              >
                Cancelar
              </button>
              <button
                onClick={() => { confirmModal.onConfirm(); setConfirmModal(null); }}
                className={`px-5 py-2.5 rounded-xl font-semibold text-sm text-white shadow-lg transition-all hover:scale-105 ${
                  confirmModal.variant === 'danger'
                    ? 'bg-gradient-to-r from-red-600 to-red-500 shadow-red-500/30 hover:shadow-red-500/50'
                    : confirmModal.variant === 'warning'
                      ? 'bg-gradient-to-r from-amber-600 to-orange-500 shadow-amber-500/30 hover:shadow-amber-500/50'
                      : 'bg-gradient-to-r from-blue-600 to-cyan-500 shadow-blue-500/30 hover:shadow-blue-500/50'
                }`}
              >
                {confirmModal.confirmLabel}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Toast Notification */}
      {toast && (
        <div className="fixed bottom-6 right-6 z-[70] animate-in slide-in-from-bottom-4 fade-in duration-300">
          <div className={`flex items-center gap-3 px-5 py-3.5 rounded-2xl shadow-2xl border ${
            toast.type === 'error'
              ? isDark ? 'bg-red-950/90 border-red-800/60 text-red-200' : 'bg-red-50 border-red-200 text-red-800'
              : isDark ? 'bg-emerald-950/90 border-emerald-800/60 text-emerald-200' : 'bg-emerald-50 border-emerald-200 text-emerald-800'
          }`}>
            {toast.type === 'error'
              ? <AlertTriangle className="w-5 h-5 shrink-0" />
              : <Check className="w-5 h-5 shrink-0" />
            }
            <span className="text-sm font-medium">{toast.message}</span>
            <button
              onClick={() => setToast(null)}
              className={`p-1 rounded-lg transition-colors ${
                toast.type === 'error'
                  ? isDark ? 'hover:bg-red-800/50' : 'hover:bg-red-100'
                  : isDark ? 'hover:bg-emerald-800/50' : 'hover:bg-emerald-100'
              }`}
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}

    </div>
  );
};

export default ProjecaoInscritos;
