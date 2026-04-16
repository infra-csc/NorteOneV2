import React, { useEffect, useState, useMemo, useRef } from 'react';
import { projecaoService, usersService } from '../../services/api';
import { useTheme } from '../../context/ThemeContext';
import { useAuth } from '../../context/AuthContext';
import { usePermissions } from '../../context/PermissionContext';
import {
  BarChart3, Plus, Pencil, Trash2, X, History, Users, Settings,
  Calendar, Filter, Eye, ChevronDown, ChevronUp, Search,
  TrendingUp, Target, UserCheck, Layers, Download, RotateCcw,
  AlertTriangle, Trash, Check,
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
  created_by: number;
  created_by_nome: string | null;
  updated_by: number | null;
  updated_by_nome: string | null;
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
}

interface SimpleUser {
  id: number;
  nome: string;
  email: string;
  ativo?: boolean;
}

const mesesOptions: MultiSelectOption[] = [
  { value: '1', label: 'Janeiro' }, { value: '2', label: 'Fevereiro' },
  { value: '3', label: 'Março' }, { value: '4', label: 'Abril' },
  { value: '5', label: 'Maio' }, { value: '6', label: 'Junho' },
  { value: '7', label: 'Julho' }, { value: '8', label: 'Agosto' },
  { value: '9', label: 'Setembro' }, { value: '10', label: 'Outubro' },
  { value: '11', label: 'Novembro' }, { value: '12', label: 'Dezembro' },
];

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
  const [eventoSearchTerm, setEventoSearchTerm] = useState('');
  const [showEventoDropdown, setShowEventoDropdown] = useState(false);
  const eventoDropdownRef = useRef<HTMLDivElement>(null);

  const [showHistorico, setShowHistorico] = useState(false);
  const [historico, setHistorico] = useState<HistoricoItem[]>([]);
  const [historicoProjecao, setHistoricoProjecao] = useState<Projecao | null>(null);

  const [showAtribuirModal, setShowAtribuirModal] = useState(false);
  const [atribuirArea, setAtribuirArea] = useState<AreaDetail | null>(null);
  const [selectedUserIds, setSelectedUserIds] = useState<number[]>([]);

  const [expandedConsolidado, setExpandedConsolidado] = useState<Set<number>>(new Set());

  const [confirmModal, setConfirmModal] = useState<{
    title: string;
    message: string;
    confirmLabel: string;
    variant: 'danger' | 'warning' | 'info';
    onConfirm: () => void;
  } | null>(null);

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
    if (activeTab === 'config' && isAdmin) loadAreasDetail();
    if (activeTab === 'lixeira' && isAdmin) loadLixeira();
  }, [activeTab]);

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

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    const qty = parseInt(formQuantidade);
    if (!formEventoId || !formAreaId || !qty || qty <= 0) {
      showToast('Informe uma quantidade válida (maior que zero).');
      return;
    }
    try {
      await projecaoService.create({
        evento_id: formEventoId as number,
        area_projecao_id: formAreaId as number,
        quantidade: qty,
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
    try {
      await projecaoService.update(editingProjecao.id, { quantidade: qty });
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
  };

  const resetForm = () => {
    setFormEventoId('');
    setFormAreaId('');
    setFormQuantidade('');
    setEventoSearchTerm('');
    setShowEventoDropdown(false);
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
            {activeTab === 'projecoes' && canCreateProjecao && (
              <button
                onClick={() => { resetForm(); setShowCreateModal(true); }}
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
        {(activeTab === 'projecoes' || activeTab === 'consolidado') && (
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
        {activeTab === 'projecoes' && (
          <div className={`rounded-2xl overflow-hidden ${isDark ? 'bg-gray-800/50 backdrop-blur-xl border border-gray-700/50' : 'bg-white/70 backdrop-blur-xl border border-gray-200'}`}>
            {loading ? (
              <div className="flex justify-center py-12">
                <div className="w-8 h-8 border-4 border-violet-500 border-t-transparent rounded-full animate-spin" />
              </div>
            ) : filteredProjecoes.length === 0 ? (
              <div className={`text-center py-12 ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                <BarChart3 className="w-12 h-12 mx-auto mb-3 opacity-30" />
                <p className="font-semibold">Nenhuma projeção encontrada</p>
                <p className="text-sm mt-1">Crie uma nova projeção para começar</p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className={isDark ? 'bg-gray-900/50' : 'bg-gray-50'}>
                      {['Evento', 'Data', 'Tipo', 'Área', 'Quantidade', 'Criado por', 'Última edição', 'Ações'].map(h => (
                        <th key={h} className={`px-4 py-3 text-left text-xs font-bold uppercase tracking-wider ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className={`divide-y ${isDark ? 'divide-gray-700/50' : 'divide-gray-100'}`}>
                    {filteredProjecoes.map(p => (
                      <tr key={p.id} className={`transition-colors ${isDark ? 'hover:bg-gray-700/30' : 'hover:bg-gray-50'}`}>
                        <td className={`px-4 py-3 text-sm font-medium ${isDark ? 'text-white' : 'text-gray-900'}`}>
                          {p.evento_nome}
                        </td>
                        <td className={`px-4 py-3 text-sm ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
                          {formatDate(p.evento_data)}
                        </td>
                        <td className={`px-4 py-3 text-sm ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
                          {p.evento_tipo || '-'}
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
                          <div>{p.created_by_nome}</div>
                          <div>{formatDateTime(p.created_at)}</div>
                        </td>
                        <td className={`px-4 py-3 text-xs ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                          {p.updated_by_nome ? (
                            <>
                              <div>{p.updated_by_nome}</div>
                              <div>{formatDateTime(p.updated_at)}</div>
                            </>
                          ) : '-'}
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-1">
                            {canEditProjecao && myAreaIds.has(p.area_projecao_id) && (
                              <button
                                onClick={() => openEdit(p)}
                                className="p-1.5 rounded-lg hover:bg-blue-500/20 text-blue-400 transition-colors"
                                title="Editar"
                              >
                                <Pencil className="w-4 h-4" />
                              </button>
                            )}
                            {myAreaIds.has(p.area_projecao_id) && (
                              <button
                                onClick={() => openHistorico(p)}
                                className="p-1.5 rounded-lg hover:bg-amber-500/20 text-amber-400 transition-colors"
                                title="Histórico"
                              >
                                <History className="w-4 h-4" />
                              </button>
                            )}
                            {canDeleteProjecao && myAreaIds.has(p.area_projecao_id) && (
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
                  </tbody>
                </table>
              </div>
            )}
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
          <div className="space-y-4">
            <p className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>
              Defina quais usuários podem preencher projeções em cada área.
            </p>
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
          <div className={`w-full max-w-lg rounded-2xl shadow-2xl ${isDark ? 'bg-gray-800 border border-gray-700' : 'bg-white'}`}>
            <div className="flex items-center justify-between p-6 border-b border-gray-700/50">
              <h2 className={`text-xl font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>Nova Projeção</h2>
              <button onClick={() => setShowCreateModal(false)} className="p-2 rounded-lg hover:bg-gray-700/50">
                <X className={`w-5 h-5 ${isDark ? 'text-gray-400' : 'text-gray-500'}`} />
              </button>
            </div>
            <form onSubmit={handleCreate} className="p-6 space-y-4">
              <div>
                <label className={`block text-sm font-semibold mb-1 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>Evento</label>
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
          <div className={`w-full max-w-lg rounded-2xl shadow-2xl ${isDark ? 'bg-gray-800 border border-gray-700' : 'bg-white'}`}>
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
                        {h.campo_alterado && (
                          <div className={`mt-2 text-sm ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                            <span className="font-medium">{h.campo_alterado}:</span>{' '}
                            {h.valor_anterior && (
                              <span className="line-through text-red-400 mr-2">{h.valor_anterior}</span>
                            )}
                            <span className="text-emerald-400 font-semibold">{h.valor_novo}</span>
                          </div>
                        )}
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
