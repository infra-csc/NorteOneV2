import React, { useEffect, useState, useMemo } from 'react';
import { projecaoService, usersService } from '../../services/api';
import { useTheme } from '../../context/ThemeContext';
import { useAuth } from '../../context/AuthContext';
import { usePermissions } from '../../context/PermissionContext';
import {
  BarChart3, Plus, Pencil, Trash2, X, History, Users, Settings,
  Calendar, Filter, Eye, ChevronDown, ChevronUp, Search,
} from 'lucide-react';

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

const meses = [
  { value: '', label: 'Todos os meses' },
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
  const { canView } = usePermissions();
  const isAdmin = user?.is_admin || false;
  const hasAccess = canView('projecao_inscritos');

  const [activeTab, setActiveTab] = useState<'projecoes' | 'consolidado' | 'config'>('projecoes');
  const [projecoes, setProjecoes] = useState<Projecao[]>([]);
  const [areas, setAreas] = useState<AreaProjecao[]>([]);
  const [eventos, setEventos] = useState<Evento[]>([]);
  const [consolidado, setConsolidado] = useState<ConsolidadoEvento[]>([]);
  const [areasDetail, setAreasDetail] = useState<AreaDetail[]>([]);
  const [allUsers, setAllUsers] = useState<SimpleUser[]>([]);
  const [loading, setLoading] = useState(true);

  const [filterMes, setFilterMes] = useState('');
  const [filterTipoEvento, setFilterTipoEvento] = useState('');
  const [filterArea, setFilterArea] = useState('');
  const [searchTerm, setSearchTerm] = useState('');

  const [showCreateModal, setShowCreateModal] = useState(false);
  const [editingProjecao, setEditingProjecao] = useState<Projecao | null>(null);
  const [formEventoId, setFormEventoId] = useState<number | ''>('');
  const [formAreaId, setFormAreaId] = useState<number | ''>('');
  const [formQuantidade, setFormQuantidade] = useState<number>(0);

  const [showHistorico, setShowHistorico] = useState(false);
  const [historico, setHistorico] = useState<HistoricoItem[]>([]);
  const [historicoProjecao, setHistoricoProjecao] = useState<Projecao | null>(null);

  const [showAtribuirModal, setShowAtribuirModal] = useState(false);
  const [atribuirArea, setAtribuirArea] = useState<AreaDetail | null>(null);
  const [selectedUserIds, setSelectedUserIds] = useState<number[]>([]);

  const [expandedConsolidado, setExpandedConsolidado] = useState<Set<number>>(new Set());

  const cardClass = `relative overflow-hidden rounded-2xl p-4 ${isDark ? 'bg-gray-800/50 backdrop-blur-xl border border-gray-700/50' : 'bg-white/70 backdrop-blur-xl border border-gray-200'}`;
  const inputClass = `w-full px-4 py-2.5 rounded-xl border ${isDark ? 'bg-gray-800/50 border-gray-600 text-white' : 'bg-white border-gray-300 text-gray-900'} focus:outline-none focus:ring-2 focus:ring-blue-500`;
  const selectClass = `px-3 py-2 rounded-xl border text-sm ${isDark ? 'bg-gray-800/50 border-gray-600 text-white' : 'bg-white border-gray-300 text-gray-900'} focus:outline-none focus:ring-2 focus:ring-blue-500`;

  const loadData = async () => {
    setLoading(true);
    try {
      const [areasData, projecoesData] = await Promise.all([
        projecaoService.minhasAreas(),
        projecaoService.list(buildFilters()),
      ]);
      setAreas(areasData);
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
    if (filterMes) params.mes = parseInt(filterMes);
    if (filterTipoEvento) params.tipo_evento = filterTipoEvento;
    if (filterArea) params.area_projecao_id = parseInt(filterArea);
    return params;
  };

  useEffect(() => {
    loadData();
    loadEventos();
  }, []);

  useEffect(() => {
    loadData();
    if (activeTab === 'consolidado') loadConsolidado();
  }, [filterMes, filterTipoEvento, filterArea]);

  useEffect(() => {
    if (activeTab === 'consolidado') loadConsolidado();
    if (activeTab === 'config' && isAdmin) loadAreasDetail();
  }, [activeTab]);

  const tiposEvento = useMemo(() => {
    const tipos = [...new Set(eventos.map(e => e.tipo_evento).filter(Boolean))] as string[];
    return tipos.sort();
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
    if (!formEventoId || !formAreaId) return;
    try {
      await projecaoService.create({
        evento_id: formEventoId as number,
        area_projecao_id: formAreaId as number,
        quantidade: formQuantidade,
      });
      setShowCreateModal(false);
      resetForm();
      loadData();
    } catch (error: any) {
      alert(error.response?.data?.detail || 'Erro ao criar projeção');
    }
  };

  const handleUpdate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingProjecao) return;
    try {
      await projecaoService.update(editingProjecao.id, { quantidade: formQuantidade });
      setEditingProjecao(null);
      resetForm();
      loadData();
    } catch (error: any) {
      alert(error.response?.data?.detail || 'Erro ao atualizar projeção');
    }
  };

  const handleDelete = async (id: number) => {
    if (!confirm('Deseja realmente excluir esta projeção?')) return;
    try {
      await projecaoService.delete(id);
      loadData();
    } catch (error: any) {
      alert(error.response?.data?.detail || 'Erro ao excluir');
    }
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
    setFormQuantidade(p.quantidade);
  };

  const resetForm = () => {
    setFormEventoId('');
    setFormAreaId('');
    setFormQuantidade(0);
  };

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
      alert(error.response?.data?.detail || 'Erro ao atribuir usuários');
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

          {activeTab === 'projecoes' && (
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

        {/* Tabs */}
        <div className="flex gap-2">
          {[
            { key: 'projecoes' as const, label: 'Projeções', icon: BarChart3 },
            { key: 'consolidado' as const, label: 'Visão Consolidada', icon: Eye },
            ...(isAdmin ? [{ key: 'config' as const, label: 'Configuração de Áreas', icon: Settings }] : []),
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
        {activeTab !== 'config' && (
          <div className={`flex flex-wrap items-center gap-3 p-4 rounded-2xl ${isDark ? 'bg-gray-800/30 border border-gray-700/50' : 'bg-white/50 border border-gray-200'}`}>
            <Filter className={`w-4 h-4 ${isDark ? 'text-gray-400' : 'text-gray-500'}`} />
            <select value={filterMes} onChange={e => setFilterMes(e.target.value)} className={selectClass}>
              {meses.map(m => <option key={m.value} value={m.value}>{m.label}</option>)}
            </select>
            <select value={filterTipoEvento} onChange={e => setFilterTipoEvento(e.target.value)} className={selectClass}>
              <option value="">Todos os tipos</option>
              {tiposEvento.map(t => <option key={t} value={t}>{t}</option>)}
            </select>
            {activeTab === 'projecoes' && (
              <select value={filterArea} onChange={e => setFilterArea(e.target.value)} className={selectClass}>
                <option value="">Todas as áreas</option>
                {areas.map(a => <option key={a.id} value={a.id}>{a.nome}</option>)}
              </select>
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
                            <button
                              onClick={() => openEdit(p)}
                              className="p-1.5 rounded-lg hover:bg-blue-500/20 text-blue-400 transition-colors"
                              title="Editar"
                            >
                              <Pencil className="w-4 h-4" />
                            </button>
                            <button
                              onClick={() => openHistorico(p)}
                              className="p-1.5 rounded-lg hover:bg-amber-500/20 text-amber-400 transition-colors"
                              title="Histórico"
                            >
                              <History className="w-4 h-4" />
                            </button>
                            <button
                              onClick={() => handleDelete(p.id)}
                              className="p-1.5 rounded-lg hover:bg-red-500/20 text-red-400 transition-colors"
                              title="Excluir"
                            >
                              <Trash2 className="w-4 h-4" />
                            </button>
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
          <div className="space-y-4">
            {filteredConsolidado.length === 0 ? (
              <div className={`text-center py-12 rounded-2xl ${isDark ? 'bg-gray-800/50 border border-gray-700/50 text-gray-400' : 'bg-white/70 border border-gray-200 text-gray-500'}`}>
                <Eye className="w-12 h-12 mx-auto mb-3 opacity-30" />
                <p className="font-semibold">Nenhum evento com projeções</p>
                <p className="text-sm mt-1">Crie projeções na aba anterior para ver a visão consolidada</p>
              </div>
            ) : (
              filteredConsolidado.map(c => (
                <div key={c.evento_id} className={cardClass}>
                  <div
                    className="flex items-center justify-between cursor-pointer"
                    onClick={() => toggleConsolidado(c.evento_id)}
                  >
                    <div className="flex-1">
                      <div className="flex items-center gap-3 mb-1">
                        <h3 className={`text-lg font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>
                          {c.evento_nome}
                        </h3>
                        <span className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                          {formatDate(c.evento_data)}
                        </span>
                      </div>
                      <div className="flex items-center gap-6 mt-2">
                        <div>
                          <span className={`text-xs ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Inscritos Reais</span>
                          <p className={`text-xl font-bold ${isDark ? 'text-emerald-400' : 'text-emerald-600'}`}>{formatNumber(c.inscritos_reais)}</p>
                        </div>
                        <div className={`text-2xl font-light ${isDark ? 'text-gray-600' : 'text-gray-300'}`}>+</div>
                        <div>
                          <span className={`text-xs ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Projeções</span>
                          <p className={`text-xl font-bold ${isDark ? 'text-violet-400' : 'text-violet-600'}`}>{formatNumber(c.total_projecoes)}</p>
                        </div>
                        <div className={`text-2xl font-light ${isDark ? 'text-gray-600' : 'text-gray-300'}`}>=</div>
                        <div>
                          <span className={`text-xs ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Total Geral</span>
                          <p className={`text-xl font-black ${isDark ? 'text-blue-400' : 'text-blue-600'}`}>{formatNumber(c.total_geral)}</p>
                        </div>
                      </div>
                    </div>
                    {expandedConsolidado.has(c.evento_id) ? (
                      <ChevronUp className={`w-5 h-5 ${isDark ? 'text-gray-400' : 'text-gray-500'}`} />
                    ) : (
                      <ChevronDown className={`w-5 h-5 ${isDark ? 'text-gray-400' : 'text-gray-500'}`} />
                    )}
                  </div>

                  {expandedConsolidado.has(c.evento_id) && (
                    <div className={`mt-4 pt-4 border-t ${isDark ? 'border-gray-700/50' : 'border-gray-200'}`}>
                      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                        {c.projecoes.map(p => (
                          <div key={p.area_projecao_id} className={`p-3 rounded-xl ${isDark ? 'bg-gray-900/50' : 'bg-gray-50'}`}>
                            <span className={`text-xs font-medium ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>{p.area_projecao_nome}</span>
                            <p className={`text-lg font-bold mt-1 ${isDark ? 'text-white' : 'text-gray-900'}`}>{formatNumber(p.quantidade)}</p>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              ))
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
                <select
                  value={formEventoId}
                  onChange={e => setFormEventoId(e.target.value ? parseInt(e.target.value) : '')}
                  className={inputClass}
                  required
                >
                  <option value="">Selecione um evento</option>
                  {eventos.map(ev => (
                    <option key={ev.id} value={ev.id}>
                      {ev.nome} {ev.info_geral?.data ? `(${formatDate(ev.info_geral.data)})` : ''}
                    </option>
                  ))}
                </select>
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
                  {areas.map(a => (
                    <option key={a.id} value={a.id}>{a.nome}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className={`block text-sm font-semibold mb-1 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>Quantidade</label>
                <input
                  type="number"
                  value={formQuantidade}
                  onChange={e => setFormQuantidade(parseInt(e.target.value) || 0)}
                  className={inputClass}
                  min={0}
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
                  onChange={e => setFormQuantidade(parseInt(e.target.value) || 0)}
                  className={inputClass}
                  min={0}
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
                  {historico.map(h => (
                    <div key={h.id} className={`flex gap-4 p-4 rounded-xl ${isDark ? 'bg-gray-900/50' : 'bg-gray-50'}`}>
                      <div className={`flex-shrink-0 w-10 h-10 rounded-full flex items-center justify-center ${
                        h.acao === 'CRIACAO' ? 'bg-emerald-500/20' : 'bg-amber-500/20'
                      }`}>
                        {h.acao === 'CRIACAO' ? (
                          <Plus className={`w-5 h-5 ${isDark ? 'text-emerald-400' : 'text-emerald-600'}`} />
                        ) : (
                          <Pencil className={`w-5 h-5 ${isDark ? 'text-amber-400' : 'text-amber-600'}`} />
                        )}
                      </div>
                      <div className="flex-1">
                        <div className="flex items-center justify-between">
                          <span className={`font-semibold text-sm ${isDark ? 'text-white' : 'text-gray-900'}`}>
                            {h.acao === 'CRIACAO' ? 'Criação' : 'Edição'}
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
                  ))}
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
    </div>
  );
};

export default ProjecaoInscritos;
