import React, { useEffect, useState, useMemo, useRef } from 'react';
import { projecaoService, usersService } from '../../services/api';
import { useTheme } from '../../context/ThemeContext';
import { useAuth } from '../../context/AuthContext';
import { usePermissions } from '../../context/PermissionContext';
import {
  BarChart3, Plus, Pencil, Trash2, X, History, Users, Settings,
  Calendar, Filter, Eye, ChevronDown, ChevronUp, Search,
  TrendingUp, Target, UserCheck, Layers, Download, RotateCcw,
  AlertTriangle, Trash, Check, Lock, LockOpen, Clock, Bell, Zap,
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
  projecoes: { area_projecao_id: number; area_projecao_nome: string; quantidade: number }[];
  total_projecoes: number;
  total_geral: number;
}

interface AreaDetail {
  id: number;
  nome: string;
  ativo: boolean;
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

const ClientesTooltip: React.FC<{
  clientes: ClienteResponse[];
  quantidade: number;
  isDark: boolean;
  formatNumber: (n: number) => string;
}> = ({ clientes, quantidade, isDark, formatNumber }) => {
  const [visible, setVisible] = useState(false);
  return (
    <div className="flex items-center gap-1.5">
      <span>{formatNumber(quantidade)}</span>
      {clientes && clientes.length > 0 && (
        <div className="relative"
          onMouseEnter={() => setVisible(true)}
          onMouseLeave={() => setVisible(false)}
        >
          <div className={`flex items-center gap-0.5 px-1.5 py-0.5 rounded-md cursor-default ${isDark ? 'bg-violet-500/20 text-violet-400' : 'bg-violet-100 text-violet-600'}`}>
            <Users className="w-3 h-3" />
            <span className="text-xs font-semibold">{clientes.length}</span>
          </div>
          {visible && (
            <div className={`absolute z-50 left-0 top-full mt-1.5 min-w-[200px] rounded-xl shadow-2xl border p-3 space-y-1.5 ${isDark ? 'bg-gray-900 border-gray-700' : 'bg-white border-gray-200'}`}>
              <p className={`text-xs font-bold uppercase tracking-wider mb-2 ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Por cliente</p>
              {clientes.map(c => (
                <div key={c.id} className={`flex items-center justify-between gap-3 text-xs ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
                  <span className="truncate">{c.nome_cliente}</span>
                  <span className={`font-bold shrink-0 ${isDark ? 'text-violet-400' : 'text-violet-600'}`}>{formatNumber(c.quantidade)}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

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
  const [eventoListSort, setEventoListSort] = useState<{ field: string; dir: 'asc' | 'desc' }>({ field: 'data', dir: 'asc' });

  const [pendencias, setPendencias] = useState<PendenciasResponse | null>(null);
  const [pendenciasBannerDismissed, setPendenciasBannerDismissed] = useState(false);
  const [cutoffRules, setCutoffRules] = useState<CutoffRule[]>([]);
  const [cutoffModal, setCutoffModal] = useState<{ mode: 'create' | 'edit'; rule: CutoffRule | null } | null>(null);
  const [cutoffForm, setCutoffForm] = useState<{ nome: string; dias_antes_evento: string; ativo: boolean }>({
    nome: '', dias_antes_evento: '', ativo: true,
  });

  const [toast, setToast] = useState<{ message: string; type: 'error' | 'success' } | null>(null);
  const toastTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);

  const showToast = (message: string, type: 'error' | 'success' = 'error') => {
    if (toastTimeout.current) clearTimeout(toastTimeout.current);
    setToast({ message, type });
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

  const loadConsolidado = async () => {
    try {
      const data = await projecaoService.getConsolidado(buildFilters());
      setConsolidado(data);
    } catch (error) {
      console.error('Erro ao carregar consolidado:', error);
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
      const data = await projecaoService.getPendencias();
      // Reset banner dismissal whenever the pendência set actually changes
      // (count or which events are pending), so a new alert breaks through.
      setPendencias(prev => {
        const prevSig = prev
          ? `${prev.total_eventos}|${prev.total_areas}|${prev.pendencias.map(p => `${p.evento_id}:${p.dias_ate_evento}:${p.areas_pendentes.length}`).join(',')}`
          : '';
        const nextSig = `${data.total_eventos}|${data.total_areas}|${data.pendencias.map(p => `${p.evento_id}:${p.dias_ate_evento}:${p.areas_pendentes.length}`).join(',')}`;
        if (prevSig !== nextSig) {
          setPendenciasBannerDismissed(false);
        }
        return data;
      });
    } catch {
    }
  };

  const loadCutoffRules = async () => {
    try {
      const data = await projecaoService.listCutoffRules(true);
      setCutoffRules(data);
    } catch (err: any) {
      showToast(err?.response?.data?.detail || 'Erro ao carregar regras de corte');
    }
  };

  const openCreateCutoff = () => {
    setCutoffForm({ nome: '', dias_antes_evento: '', ativo: true });
    setCutoffModal({ mode: 'create', rule: null });
  };

  const openEditCutoff = (rule: CutoffRule) => {
    setCutoffForm({ nome: rule.nome, dias_antes_evento: String(rule.dias_antes_evento), ativo: rule.ativo });
    setCutoffModal({ mode: 'edit', rule });
  };

  const submitCutoff = async () => {
    const nome = cutoffForm.nome.trim();
    const dias = parseInt(cutoffForm.dias_antes_evento, 10);
    if (!nome) { showToast('Nome é obrigatório'); return; }
    if (isNaN(dias) || dias < 0 || dias > 365) {
      showToast('Dias deve ser um número entre 0 e 365');
      return;
    }
    try {
      if (cutoffModal?.mode === 'create') {
        await projecaoService.createCutoffRule({ nome, dias_antes_evento: dias, ativo: cutoffForm.ativo });
        showToast('Regra criada com sucesso', 'success');
      } else if (cutoffModal?.rule) {
        await projecaoService.updateCutoffRule(cutoffModal.rule.id, { nome, dias_antes_evento: dias, ativo: cutoffForm.ativo });
        showToast('Regra atualizada', 'success');
      }
      setCutoffModal(null);
      loadCutoffRules();
      loadPendencias();
    } catch (err: any) {
      showToast(err?.response?.data?.detail || 'Erro ao salvar regra');
    }
  };

  const handleDeleteCutoff = (rule: CutoffRule) => {
    showConfirm({
      title: 'Excluir regra de corte',
      message: `Deseja realmente excluir a regra "${rule.nome}" (D-${rule.dias_antes_evento})?`,
      confirmLabel: 'Excluir',
      variant: 'danger',
      onConfirm: async () => {
        try {
          await projecaoService.deleteCutoffRule(rule.id);
          showToast('Regra excluída', 'success');
          loadCutoffRules();
          loadPendencias();
          setConfirmModal(null);
        } catch (err: any) {
          showToast(err?.response?.data?.detail || 'Erro ao excluir regra');
        }
      },
    });
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

  useEffect(() => {
    loadData();
    loadEventos();
  }, []);

  useEffect(() => {
    loadData();
    if (activeTab === 'consolidado') loadConsolidado();
  }, [filterMes, filterTipoEvento, filterModalidade, filterArea]);

  useEffect(() => {
    if (activeTab === 'consolidado') loadConsolidado();
    if (activeTab === 'config' && isAdmin) { loadAreasDetail(); loadCutoffRules(); }
    if (activeTab === 'lixeira' && isAdmin) loadLixeira();
  }, [activeTab]);

  useEffect(() => {
    loadPendencias();
    const interval = setInterval(loadPendencias, 180000);
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

  const filteredConsolidado = useMemo(() => {
    if (!searchTerm) return consolidado;
    const term = searchTerm.toLowerCase();
    return consolidado.filter(c => c.evento_nome?.toLowerCase().includes(term));
  }, [consolidado, searchTerm]);

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
      return true;
    });
  }, [eventos, eventoListSearch, eventoListMes, eventoListModalidade, eventoListCidade, eventoListStatus]);

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
    try {
      const clientes = formTemCliente
        ? formClientes
            .filter(c => c.nome_cliente.trim() && parseInt(c.quantidade) > 0)
            .map(c => ({ nome_cliente: c.nome_cliente.trim(), quantidade: parseInt(c.quantidade) }))
        : undefined;
      await projecaoService.create({
        evento_id: formEventoId as number,
        area_projecao_id: formAreaId as number,
        quantidade: qty,
        clientes,
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
    try {
      const clientes = formTemCliente
        ? formClientes
            .filter(c => c.nome_cliente.trim() && parseInt(c.quantidade) > 0)
            .map(c => ({ nome_cliente: c.nome_cliente.trim(), quantidade: parseInt(c.quantidade) }))
        : [];
      await projecaoService.update(editingProjecao.id, { quantidade: qty, clientes });
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

  const openEdit = (p: Projecao) => {
    setEditingProjecao(p);
    setFormQuantidade(String(p.quantidade));
    if (p.clientes && p.clientes.length > 0) {
      setFormTemCliente(true);
      setFormClientes(p.clientes.map(c => ({ nome_cliente: c.nome_cliente, quantidade: String(c.quantidade) })));
    } else {
      setFormTemCliente(false);
      setFormClientes([{ nome_cliente: '', quantidade: '' }]);
    }
  };

  const resetForm = () => {
    setFormEventoId(selectedEvento ? selectedEvento.id : '');
    setFormAreaId('');
    setFormQuantidade('');
    setFormTemCliente(false);
    setFormClientes([{ nome_cliente: '', quantidade: '' }]);
    setEventoSearchTerm('');
    setShowEventoDropdown(false);
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
            {activeTab === 'projecoes' && canCreateProjecao && selectedEvento && (
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
            )}
          </div>
        </div>

        {/* Tabs */}
        <div className="flex gap-2">
          {[
            { key: 'projecoes' as const, label: 'Projeções', icon: BarChart3 },
            { key: 'consolidado' as const, label: 'Visão Consolidada', icon: Eye },
            ...(isAdmin ? [
              { key: 'config' as const, label: 'Configuração de Áreas', icon: Settings },
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
            {(filterMes.length > 0 || filterTipoEvento.length > 0 || filterModalidade.length > 0 || filterArea.length > 0 || searchTerm) && (
              <button
                type="button"
                onClick={() => { setFilterMes([]); setFilterTipoEvento([]); setFilterModalidade([]); setFilterArea([]); setSearchTerm(''); }}
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
                  Os eventos abaixo cruzaram um ponto de corte e ainda não têm projeção registrada para áreas que você pode editar.
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
                        p.dias_ate_evento <= 15
                          ? isDark ? 'bg-red-500/20 text-red-300 hover:bg-red-500/30 border border-red-500/40' : 'bg-red-100 text-red-700 hover:bg-red-200 border border-red-300'
                          : isDark ? 'bg-amber-500/20 text-amber-300 hover:bg-amber-500/30 border border-amber-500/40' : 'bg-amber-100 text-amber-700 hover:bg-amber-200 border border-amber-300'
                      }`}
                      title={`${p.evento_nome} — D-${p.dias_ate_evento} • ${p.areas_pendentes.map(a => a.area_projecao_nome).join(', ')}`}
                    >
                      <Zap className="w-3 h-3" />
                      <span className="truncate max-w-[180px]">{p.evento_nome}</span>
                      <span className="font-mono opacity-80">D-{p.dias_ate_evento}</span>
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
              const hasFilters = eventoListSearch || eventoListMes || eventoListModalidade || eventoListCidade || eventoListStatus !== 'Em andamento';
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

                  {/* Clear */}
                  {hasFilters && (
                    <button
                      onClick={() => { setEventoListSearch(''); setEventoListMes(''); setEventoListModalidade(''); setEventoListCidade(''); setEventoListStatus('Em andamento'); }}
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
                        { label: 'Ações',            field: null },
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
                      const statusColors: Record<string, string> = {
                        'Em andamento': isDark ? 'bg-emerald-500/20 text-emerald-400' : 'bg-emerald-100 text-emerald-700',
                        'Encerrado': isDark ? 'bg-gray-500/20 text-gray-400' : 'bg-gray-100 text-gray-600',
                        'Cancelado': isDark ? 'bg-red-500/20 text-red-400' : 'bg-red-100 text-red-700',
                      };
                      const statusColor = statusColors[ev.status || ''] || (isDark ? 'bg-gray-700 text-gray-400' : 'bg-gray-100 text-gray-500');
                      const pendUrgent = pend && pend.dias_ate_evento <= 15;
                      return (
                        <tr
                          key={ev.id}
                          onClick={() => setSelectedEvento(ev)}
                          className={`cursor-pointer transition-colors ${
                            pend
                              ? pendUrgent
                                ? isDark ? 'bg-red-500/[0.07] hover:bg-red-500/15' : 'bg-red-50/60 hover:bg-red-50'
                                : isDark ? 'bg-amber-500/[0.06] hover:bg-amber-500/15' : 'bg-amber-50/60 hover:bg-amber-50'
                              : isDark ? 'hover:bg-violet-500/10' : 'hover:bg-violet-50'
                          }`}
                        >
                          <td className={`px-4 py-3 text-sm font-semibold ${isDark ? 'text-white' : 'text-gray-900'}`}>
                            <div className="flex items-center gap-2 flex-wrap">
                              <span>{ev.nome}</span>
                              {pend && (
                                <span
                                  title={`Ponto de corte ${pend.cutoff_nome} (D-${pend.cutoff_dias}) atingido. Áreas pendentes: ${pend.areas_pendentes.map(a => a.area_projecao_nome).join(', ')}`}
                                  className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-bold ${
                                    pendUrgent
                                      ? isDark ? 'bg-red-500/30 text-red-200 border border-red-500/50' : 'bg-red-100 text-red-700 border border-red-300'
                                      : isDark ? 'bg-amber-500/30 text-amber-200 border border-amber-500/50' : 'bg-amber-100 text-amber-700 border border-amber-300'
                                  }`}
                                >
                                  <Bell className="w-2.5 h-2.5" />
                                  Pendente • D-{pend.dias_ate_evento}
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
                          <td className="px-4 py-3">
                            <button
                              onClick={e => { e.stopPropagation(); setSelectedEvento(ev); }}
                              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${isDark ? 'bg-violet-500/20 text-violet-400 hover:bg-violet-500/30' : 'bg-violet-100 text-violet-700 hover:bg-violet-200'}`}
                            >
                              <BarChart3 className="w-3.5 h-3.5" />
                              Projeções
                            </button>
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
                <table className="w-full">
                  <thead>
                    <tr className={isDark ? 'bg-gray-900/50' : 'bg-gray-50'}>
                      {['Área', 'Quantidade', 'Criado por', 'Última edição / Travamento', 'Ações'].map(h => (
                        <th key={h} className={`px-4 py-3 text-left text-xs font-bold uppercase tracking-wider ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className={`divide-y ${isDark ? 'divide-gray-700/50' : 'divide-gray-100'}`}>
                    {eventGroups.filter(g => selectedEvento ? g[0].evento_id === selectedEvento.id : true).map(group => {
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
                                {canEditProjecao && (
                                  <button
                                    onClick={() => {
                                      if (allLocked && !isAdmin) return;
                                      handleToggleLock(firstP.evento_id, allLocked);
                                    }}
                                    disabled={lockingEventoId === firstP.evento_id || (allLocked && !isAdmin)}
                                    title={allLocked ? (isAdmin ? 'Destravar projeções (admin)' : 'Apenas administradores podem destravar') : 'Travar todas as projeções deste evento'}
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
                                <ClientesTooltip clientes={p.clientes} quantidade={p.quantidade} isDark={isDark} formatNumber={formatNumber} />
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
                                  {canEditProjecao && myAreaIds.has(p.area_projecao_id) && !p.locked_at && (
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
                                  {canDeleteProjecao && myAreaIds.has(p.area_projecao_id) && !p.locked_at && (
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
            {filteredConsolidado.length === 0 ? (
              <div className={`text-center py-16 rounded-2xl ${isDark ? 'bg-gray-800/50 border border-gray-700/50 text-gray-400' : 'bg-white/70 border border-gray-200 text-gray-500'}`}>
                <Eye className="w-14 h-14 mx-auto mb-4 opacity-20" />
                <p className="text-lg font-semibold">Nenhum evento com projeções</p>
                <p className="text-sm mt-1">Crie projeções na aba anterior para ver a visão consolidada</p>
              </div>
            ) : (
              <>
                {/* KPI Summary Row */}
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  {[
                    {
                      label: 'Total Inscritos Reais',
                      value: filteredConsolidado.reduce((s, c) => s + c.inscritos_reais, 0),
                      icon: UserCheck,
                      gradient: 'from-emerald-500 to-teal-600',
                      shadow: 'shadow-emerald-500/25',
                      textColor: isDark ? 'text-emerald-400' : 'text-emerald-600',
                      bgIcon: 'bg-emerald-500/15',
                    },
                    {
                      label: 'Total Projeções',
                      value: filteredConsolidado.reduce((s, c) => s + c.total_projecoes, 0),
                      icon: TrendingUp,
                      gradient: 'from-violet-500 to-purple-600',
                      shadow: 'shadow-violet-500/25',
                      textColor: isDark ? 'text-violet-400' : 'text-violet-600',
                      bgIcon: 'bg-violet-500/15',
                    },
                    {
                      label: 'Total Geral',
                      value: filteredConsolidado.reduce((s, c) => s + c.total_geral, 0),
                      icon: Target,
                      gradient: 'from-blue-500 to-cyan-600',
                      shadow: 'shadow-blue-500/25',
                      textColor: isDark ? 'text-blue-400' : 'text-blue-600',
                      bgIcon: 'bg-blue-500/15',
                    },
                  ].map((kpi) => (
                    <div
                      key={kpi.label}
                      className={`relative overflow-hidden rounded-2xl p-5 ${isDark ? 'bg-gray-800/60 backdrop-blur-xl border border-gray-700/50' : 'bg-white/80 backdrop-blur-xl border border-gray-200 shadow-sm'}`}
                    >
                      <div className={`absolute top-0 right-0 w-24 h-24 rounded-full blur-2xl opacity-20 bg-gradient-to-br ${kpi.gradient}`} />
                      <div className="relative flex items-center gap-4">
                        <div className={`p-3 rounded-xl ${kpi.bgIcon}`}>
                          <kpi.icon className={`w-6 h-6 ${kpi.textColor}`} />
                        </div>
                        <div>
                          <p className={`text-xs font-semibold uppercase tracking-wider ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>{kpi.label}</p>
                          <p className={`text-3xl font-black tracking-tight ${kpi.textColor}`}>{formatNumber(kpi.value)}</p>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>

                {/* Event Cards */}
                <div className="space-y-4">
                  {filteredConsolidado.map(c => {
                    const isExpanded = expandedConsolidado.has(c.evento_id);
                    const maxAreaQtd = Math.max(...c.projecoes.map(p => p.quantidade), 1);

                    return (
                      <div
                        key={c.evento_id}
                        className={`relative overflow-hidden rounded-2xl transition-all duration-300 ${isDark ? 'bg-gray-800/60 backdrop-blur-xl border border-gray-700/50 hover:border-gray-600/70' : 'bg-white/80 backdrop-blur-xl border border-gray-200 shadow-sm hover:shadow-md'}`}
                      >
                        <div className={`absolute top-0 left-0 h-full w-1 bg-gradient-to-b ${c.total_geral > 0 && (c.inscritos_reais / c.total_geral) >= 0.5 ? 'from-emerald-400 to-teal-500' : 'from-amber-400 to-orange-500'}`} />

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
                              </div>

                              <div className="mt-4 flex items-end gap-8 flex-wrap">
                                <div className="flex items-baseline gap-2">
                                  <span className={`text-3xl font-black tracking-tight ${isDark ? 'text-emerald-400' : 'text-emerald-600'}`}>
                                    {formatNumber(c.inscritos_reais)}
                                  </span>
                                  <span className={`text-sm font-medium ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>reais</span>
                                </div>
                                <div className={`text-lg ${isDark ? 'text-gray-600' : 'text-gray-300'}`}>+</div>
                                <div className="flex items-baseline gap-2">
                                  <span className={`text-3xl font-black tracking-tight ${isDark ? 'text-violet-400' : 'text-violet-600'}`}>
                                    {formatNumber(c.total_projecoes)}
                                  </span>
                                  <span className={`text-sm font-medium ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>projeções</span>
                                </div>
                                <div className={`text-lg ${isDark ? 'text-gray-600' : 'text-gray-300'}`}>=</div>
                                <div className="flex items-baseline gap-2">
                                  <span className={`text-3xl font-black tracking-tight ${isDark ? 'text-blue-400' : 'text-blue-600'}`}>
                                    {formatNumber(c.total_geral)}
                                  </span>
                                  <span className={`text-sm font-medium ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>total</span>
                                </div>
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
                              </div>
                              <div className="space-y-3">
                                {c.projecoes
                                  .slice()
                                  .sort((a, b) => b.quantidade - a.quantidade)
                                  .map((p, idx) => {
                                    const barPct = (p.quantidade / maxAreaQtd) * 100;
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

                                    return (
                                      <div key={p.area_projecao_id} className={`p-3 rounded-xl ${color.bg}`}>
                                        <div className="flex items-center justify-between mb-2">
                                          <span className={`text-sm font-semibold ${color.text}`}>{p.area_projecao_nome}</span>
                                          <span className={`text-sm font-black tabular-nums ${isDark ? 'text-white' : 'text-gray-900'}`}>
                                            {formatNumber(p.quantidade)}
                                          </span>
                                        </div>
                                        <div className={`h-2 rounded-full overflow-hidden ${isDark ? 'bg-gray-700/50' : 'bg-gray-200/80'}`}>
                                          <div
                                            className={`h-full rounded-full bg-gradient-to-r ${color.bar} transition-all duration-500 ease-out`}
                                            style={{ width: `${barPct}%` }}
                                          />
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
            {/* ── Pontos de corte (regras de notificação) ── */}
            <div className="space-y-3">
              <div className="flex items-center justify-between flex-wrap gap-3">
                <div className="flex items-center gap-2">
                  <Clock className={`w-5 h-5 ${isDark ? 'text-violet-400' : 'text-violet-600'}`} />
                  <div>
                    <h2 className={`text-lg font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>Pontos de Corte</h2>
                    <p className={`text-xs ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>
                      Quando um evento atinge um destes prazos (em dias até a data do evento), os usuários com permissão de editar a área recebem alerta de pendência.
                    </p>
                  </div>
                </div>
                <button
                  onClick={openCreateCutoff}
                  className="flex items-center gap-2 px-4 py-2 rounded-xl bg-gradient-to-r from-rose-600 to-orange-600 text-white text-sm font-semibold hover:shadow-lg transition-all"
                >
                  <Plus className="w-4 h-4" />
                  Nova Regra
                </button>
              </div>

              {cutoffRules.length === 0 ? (
                <div className={`text-center py-8 rounded-2xl ${isDark ? 'bg-gray-800/50 border border-gray-700/50 text-gray-400' : 'bg-white/70 border border-gray-200 text-gray-500'}`}>
                  <Clock className="w-10 h-10 mx-auto mb-2 opacity-30" />
                  <p className="text-sm font-medium">Nenhuma regra de corte configurada</p>
                </div>
              ) : (
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                  {cutoffRules.map(rule => (
                    <div
                      key={rule.id}
                      className={`relative overflow-hidden rounded-2xl p-4 border ${
                        rule.ativo
                          ? isDark ? 'bg-gray-800/50 border-gray-700/50' : 'bg-white border-gray-200'
                          : isDark ? 'bg-gray-900/40 border-gray-800 opacity-60' : 'bg-gray-50 border-gray-200 opacity-70'
                      }`}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0">
                          <div className="flex items-center gap-2">
                            <span className={`inline-flex px-2 py-0.5 rounded-md text-xs font-bold font-mono ${
                              rule.dias_antes_evento <= 15
                                ? isDark ? 'bg-red-500/20 text-red-300' : 'bg-red-100 text-red-700'
                                : rule.dias_antes_evento <= 30
                                ? isDark ? 'bg-amber-500/20 text-amber-300' : 'bg-amber-100 text-amber-700'
                                : isDark ? 'bg-violet-500/20 text-violet-300' : 'bg-violet-100 text-violet-700'
                            }`}>
                              D-{rule.dias_antes_evento}
                            </span>
                            {!rule.ativo && (
                              <span className={`text-[10px] font-bold uppercase ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>Inativa</span>
                            )}
                          </div>
                          <h3 className={`text-base font-bold mt-2 ${isDark ? 'text-white' : 'text-gray-900'}`}>{rule.nome}</h3>
                          <p className={`text-xs mt-1 ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                            Aciona quando faltam {rule.dias_antes_evento} dia{rule.dias_antes_evento !== 1 ? 's' : ''} ou menos para o evento.
                          </p>
                        </div>
                        <div className="flex items-center gap-1 flex-shrink-0">
                          <button
                            onClick={() => openEditCutoff(rule)}
                            title="Editar"
                            className={`p-1.5 rounded-lg ${isDark ? 'text-gray-400 hover:bg-gray-700/60' : 'text-gray-500 hover:bg-gray-100'}`}
                          >
                            <Pencil className="w-3.5 h-3.5" />
                          </button>
                          <button
                            onClick={() => handleDeleteCutoff(rule)}
                            title="Excluir"
                            className={`p-1.5 rounded-lg ${isDark ? 'text-red-400 hover:bg-red-500/20' : 'text-red-500 hover:bg-red-50'}`}
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
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
                  <div className="flex items-center justify-between">
                    <div>
                      <h3 className={`text-lg font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>{area.nome}</h3>
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
                    <button
                      onClick={() => openAtribuir(area)}
                      className="flex items-center gap-2 px-4 py-2 rounded-xl bg-gradient-to-r from-violet-600 to-blue-600 text-white text-sm font-semibold hover:shadow-lg transition-all"
                    >
                      <Users className="w-4 h-4" />
                      Gerenciar
                    </button>
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

      {/* Create Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
          <div className={`w-full max-w-lg max-h-[90vh] overflow-y-auto rounded-2xl shadow-2xl ${isDark ? 'bg-gray-800 border border-gray-700' : 'bg-white'}`}>
            <div className="flex items-center justify-between p-6 border-b border-gray-700/50">
              <h2 className={`text-xl font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>Nova Projeção</h2>
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
                  type="number"
                  value={formQuantidade}
                  onChange={e => setFormQuantidade(e.target.value)}
                  placeholder="Ex: 150"
                  className={inputClass}
                  min={1}
                  required
                />
              </div>

              {/* Toggle clientes */}
              <div className={`flex items-center justify-between p-3 rounded-xl border ${isDark ? 'border-gray-700 bg-gray-900/30' : 'border-gray-200 bg-gray-50'}`}>
                <div className="flex items-center gap-2">
                  <Users className={`w-4 h-4 ${isDark ? 'text-gray-400' : 'text-gray-500'}`} />
                  <span className={`text-sm font-semibold ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>Distribuir por cliente</span>
                </div>
                <button
                  type="button"
                  onClick={() => setFormTemCliente(v => !v)}
                  className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer items-center rounded-full transition-colors focus:outline-none ${formTemCliente ? 'bg-violet-600' : isDark ? 'bg-gray-600' : 'bg-gray-300'}`}
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
                  {formClientes.map((cliente, idx) => (
                    <div key={idx} className="flex items-center gap-2">
                      <input
                        type="text"
                        value={cliente.nome_cliente}
                        onChange={e => updateCliente(idx, 'nome_cliente', e.target.value)}
                        placeholder="Nome do cliente"
                        className={`flex-1 px-3 py-2 rounded-lg border text-sm ${isDark ? 'bg-gray-800/50 border-gray-600 text-white placeholder-gray-500' : 'bg-white border-gray-300 text-gray-900 placeholder-gray-400'} focus:outline-none focus:ring-2 focus:ring-violet-500`}
                      />
                      <input
                        type="number"
                        value={cliente.quantidade}
                        onChange={e => updateCliente(idx, 'quantidade', e.target.value)}
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
                  ))}
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
                <h2 className={`text-xl font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>Editar Projeção</h2>
                <p className={`text-sm mt-1 ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                  {editingProjecao.evento_nome} — {editingProjecao.area_projecao_nome}
                </p>
              </div>
              <button onClick={() => setEditingProjecao(null)} className="p-2 rounded-lg hover:bg-gray-700/50">
                <X className={`w-5 h-5 ${isDark ? 'text-gray-400' : 'text-gray-500'}`} />
              </button>
            </div>
            <form onSubmit={handleUpdate} className="p-6 space-y-4">
              <div>
                <label className={`block text-sm font-semibold mb-1 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>Quantidade</label>
                <input
                  type="number"
                  value={formQuantidade}
                  onChange={e => setFormQuantidade(e.target.value)}
                  placeholder="Ex: 150"
                  className={inputClass}
                  min={1}
                  required
                />
              </div>

              {/* Toggle clientes */}
              <div className={`flex items-center justify-between p-3 rounded-xl border ${isDark ? 'border-gray-700 bg-gray-900/30' : 'border-gray-200 bg-gray-50'}`}>
                <div className="flex items-center gap-2">
                  <Users className={`w-4 h-4 ${isDark ? 'text-gray-400' : 'text-gray-500'}`} />
                  <span className={`text-sm font-semibold ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>Distribuir por cliente</span>
                </div>
                <button
                  type="button"
                  onClick={() => setFormTemCliente(v => !v)}
                  className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer items-center rounded-full transition-colors focus:outline-none ${formTemCliente ? 'bg-violet-600' : isDark ? 'bg-gray-600' : 'bg-gray-300'}`}
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
                  {formClientes.map((cliente, idx) => (
                    <div key={idx} className="flex items-center gap-2">
                      <input
                        type="text"
                        value={cliente.nome_cliente}
                        onChange={e => updateCliente(idx, 'nome_cliente', e.target.value)}
                        placeholder="Nome do cliente"
                        className={`flex-1 px-3 py-2 rounded-lg border text-sm ${isDark ? 'bg-gray-800/50 border-gray-600 text-white placeholder-gray-500' : 'bg-white border-gray-300 text-gray-900 placeholder-gray-400'} focus:outline-none focus:ring-2 focus:ring-violet-500`}
                      />
                      <input
                        type="number"
                        value={cliente.quantidade}
                        onChange={e => updateCliente(idx, 'quantidade', e.target.value)}
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
                  ))}
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
                  onClick={() => setEditingProjecao(null)}
                  className={`px-4 py-2.5 rounded-xl font-semibold ${isDark ? 'bg-gray-700 text-gray-300 hover:bg-gray-600' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'}`}
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  className="px-6 py-2.5 rounded-xl bg-gradient-to-r from-violet-600 to-blue-600 text-white font-semibold shadow-lg hover:shadow-xl transition-all"
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

      {/* ── Cutoff Rule create/edit modal ── */}
      {cutoffModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm" onClick={() => setCutoffModal(null)}>
          <div
            onClick={e => e.stopPropagation()}
            className={`w-full max-w-md rounded-2xl shadow-2xl overflow-hidden ${isDark ? 'bg-gray-900 border border-gray-700' : 'bg-white border border-gray-200'}`}
          >
            <div className={`flex items-center gap-3 px-5 py-4 border-b ${isDark ? 'border-gray-700' : 'border-gray-200'}`}>
              <div className={`flex items-center justify-center w-9 h-9 rounded-xl ${isDark ? 'bg-rose-500/20' : 'bg-rose-100'}`}>
                <Clock className={`w-4 h-4 ${isDark ? 'text-rose-300' : 'text-rose-600'}`} />
              </div>
              <h3 className={`text-lg font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>
                {cutoffModal.mode === 'create' ? 'Nova regra de corte' : 'Editar regra de corte'}
              </h3>
            </div>

            <div className="px-5 py-4 space-y-4">
              <div>
                <label className={`block text-xs font-bold uppercase tracking-wide mb-1.5 ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>Nome</label>
                <input
                  type="text"
                  value={cutoffForm.nome}
                  onChange={e => setCutoffForm(f => ({ ...f, nome: e.target.value }))}
                  placeholder="Ex.: Primeiro alerta"
                  className={`w-full h-10 px-3 rounded-xl border text-sm focus:outline-none focus:ring-2 focus:ring-rose-500 ${isDark ? 'bg-gray-800 border-gray-700 text-white placeholder-gray-500' : 'bg-gray-50 border-gray-200 text-gray-900 placeholder-gray-400'}`}
                />
              </div>

              <div>
                <label className={`block text-xs font-bold uppercase tracking-wide mb-1.5 ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>Dias antes do evento</label>
                <input
                  type="number"
                  min={1}
                  max={365}
                  value={cutoffForm.dias_antes_evento}
                  onChange={e => setCutoffForm(f => ({ ...f, dias_antes_evento: e.target.value }))}
                  className={`w-full h-10 px-3 rounded-xl border text-sm focus:outline-none focus:ring-2 focus:ring-rose-500 ${isDark ? 'bg-gray-800 border-gray-700 text-white' : 'bg-gray-50 border-gray-200 text-gray-900'}`}
                />
                <p className={`text-xs mt-1.5 ${isDark ? 'text-gray-500' : 'text-gray-500'}`}>
                  A regra dispara quando faltam esta quantidade de dias (ou menos) para o evento.
                </p>
              </div>

              <label className={`flex items-center gap-2 cursor-pointer select-none ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
                <input
                  type="checkbox"
                  checked={cutoffForm.ativo}
                  onChange={e => setCutoffForm(f => ({ ...f, ativo: e.target.checked }))}
                  className="w-4 h-4 rounded accent-rose-600"
                />
                <span className="text-sm font-medium">Regra ativa</span>
              </label>
            </div>

            <div className={`flex items-center justify-end gap-2 px-5 py-3 border-t ${isDark ? 'border-gray-700 bg-gray-900/50' : 'border-gray-200 bg-gray-50'}`}>
              <button
                onClick={() => setCutoffModal(null)}
                className={`px-4 py-2 rounded-xl text-sm font-semibold ${isDark ? 'text-gray-300 hover:bg-gray-800' : 'text-gray-700 hover:bg-gray-100'}`}
              >
                Cancelar
              </button>
              <button
                onClick={submitCutoff}
                className="px-4 py-2 rounded-xl bg-gradient-to-r from-rose-600 to-orange-600 text-white text-sm font-semibold hover:shadow-lg transition-all"
              >
                {cutoffModal?.mode === 'create' ? 'Criar regra' : 'Salvar alterações'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default ProjecaoInscritos;
