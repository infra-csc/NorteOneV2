import React, { useEffect, useState, useCallback } from 'react';
import { useTheme } from '../../context/ThemeContext';
import api from '../../services/api';
import {
  Layers, Search, Plus, Edit2, Trash2, RefreshCw,
  AlertTriangle, X, Link2, Unlink, Check,
  ChevronDown, ChevronUp, Filter, Database
} from 'lucide-react';

interface SkuMapping {
  id: number;
  fonte: 'ATIVO' | 'MAGENTO';
  id_externo: number;
  sku: string;
  evento_grupo: string | null;
  ano: number;
  nome_evento: string;
  ativo: boolean;
  evento_consolidado_id: number | null;
  created_at: string | null;
  updated_at: string | null;
}

interface EventoConsolidado {
  id: number;
  nome: string;
  descricao: string | null;
  ativo: boolean;
  created_at: string | null;
  updated_at: string | null;
}

interface EventoConsolidadoDetail extends EventoConsolidado {
  mapeamentos: SkuMapping[];
}

const currentYear = new Date().getFullYear();
const anos = Array.from({ length: 5 }, (_, i) => currentYear - 2 + i);

const EventosConsolidados: React.FC = () => {
  const { isDark } = useTheme();

  const [eventos, setEventos] = useState<EventoConsolidado[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');

  const [showCreateModal, setShowCreateModal] = useState(false);
  const [createForm, setCreateForm] = useState({ nome: '', descricao: '' });
  const [createError, setCreateError] = useState<string | null>(null);
  const [savingCreate, setSavingCreate] = useState(false);

  const [detailEvento, setDetailEvento] = useState<EventoConsolidadoDetail | null>(null);
  const [showDetailModal, setShowDetailModal] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [editNome, setEditNome] = useState('');
  const [editDescricao, setEditDescricao] = useState('');
  const [savingEdit, setSavingEdit] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);

  const [availableMappings, setAvailableMappings] = useState<SkuMapping[]>([]);
  const [availableLoading, setAvailableLoading] = useState(false);
  const [availableFilterFonte, setAvailableFilterFonte] = useState<string>('');
  const [availableFilterAno, setAvailableFilterAno] = useState<string>('');
  const [availableFilterBusca, setAvailableFilterBusca] = useState('');
  const [selectedMappingIds, setSelectedMappingIds] = useState<Set<number>>(new Set());
  const [vinculando, setVinculando] = useState(false);

  const [showDeleteConfirm, setShowDeleteConfirm] = useState<number | null>(null);

  const fetchEventos = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params: Record<string, string> = {};
      if (search) params.busca = search;
      const res = await api.get('/admin/eventos-consolidados', { params });
      setEventos(res.data);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Erro ao carregar eventos consolidados');
    } finally {
      setLoading(false);
    }
  }, [search]);

  useEffect(() => {
    fetchEventos();
  }, [fetchEventos]);

  const openDetail = async (evento: EventoConsolidado) => {
    setShowDetailModal(true);
    setDetailLoading(true);
    setEditError(null);
    setAvailableMappings([]);
    setSelectedMappingIds(new Set());
    setAvailableFilterFonte('');
    setAvailableFilterAno('');
    setAvailableFilterBusca('');
    try {
      const res = await api.get(`/admin/eventos-consolidados/${evento.id}`);
      setDetailEvento(res.data);
      setEditNome(res.data.nome);
      setEditDescricao(res.data.descricao || '');
    } catch (err: any) {
      setEditError(err.response?.data?.detail || 'Erro ao carregar detalhes');
    } finally {
      setDetailLoading(false);
    }
  };

  const refreshDetail = async () => {
    if (!detailEvento) return;
    try {
      const res = await api.get(`/admin/eventos-consolidados/${detailEvento.id}`);
      setDetailEvento(res.data);
      setEditNome(res.data.nome);
      setEditDescricao(res.data.descricao || '');
    } catch (err: any) {
      setEditError(err.response?.data?.detail || 'Erro ao atualizar detalhes');
    }
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!createForm.nome.trim()) {
      setCreateError('Nome é obrigatório');
      return;
    }
    setSavingCreate(true);
    setCreateError(null);
    try {
      await api.post('/admin/eventos-consolidados', {
        nome: createForm.nome.trim(),
        descricao: createForm.descricao.trim() || null,
        ativo: true
      });
      setShowCreateModal(false);
      setCreateForm({ nome: '', descricao: '' });
      fetchEventos();
    } catch (err: any) {
      setCreateError(err.response?.data?.detail || 'Erro ao criar evento consolidado');
    } finally {
      setSavingCreate(false);
    }
  };

  const handleEditSave = async () => {
    if (!detailEvento || !editNome.trim()) return;
    setSavingEdit(true);
    setEditError(null);
    try {
      await api.put(`/admin/eventos-consolidados/${detailEvento.id}`, {
        nome: editNome.trim(),
        descricao: editDescricao.trim() || null
      });
      await refreshDetail();
      fetchEventos();
    } catch (err: any) {
      setEditError(err.response?.data?.detail || 'Erro ao salvar alterações');
    } finally {
      setSavingEdit(false);
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await api.delete(`/admin/eventos-consolidados/${id}`);
      setShowDeleteConfirm(null);
      if (detailEvento?.id === id) {
        setShowDetailModal(false);
        setDetailEvento(null);
      }
      fetchEventos();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Erro ao excluir evento');
    }
  };

  const fetchAvailableMappings = async () => {
    if (!detailEvento) return;
    setAvailableLoading(true);
    try {
      const params: Record<string, string> = {};
      if (availableFilterFonte) params.fonte = availableFilterFonte;
      if (availableFilterAno) params.ano = availableFilterAno;
      if (availableFilterBusca) params.busca = availableFilterBusca;
      const res = await api.get(`/admin/eventos-consolidados/${detailEvento.id}/mapeamentos-disponiveis`, { params });
      const linked = new Set(detailEvento.mapeamentos.map(m => m.id));
      setAvailableMappings(res.data.filter((m: SkuMapping) => !linked.has(m.id)));
      setSelectedMappingIds(new Set());
    } catch (err: any) {
      setEditError(err.response?.data?.detail || 'Erro ao buscar mapeamentos disponíveis');
    } finally {
      setAvailableLoading(false);
    }
  };

  useEffect(() => {
    if (detailEvento && showDetailModal) {
      fetchAvailableMappings();
    }
  }, [detailEvento?.id, availableFilterFonte, availableFilterAno]);

  const handleVincular = async () => {
    if (!detailEvento || selectedMappingIds.size === 0) return;
    setVinculando(true);
    try {
      await api.post(`/admin/eventos-consolidados/${detailEvento.id}/vincular`, Array.from(selectedMappingIds));
      await refreshDetail();
      setSelectedMappingIds(new Set());
      fetchAvailableMappings();
      fetchEventos();
    } catch (err: any) {
      setEditError(err.response?.data?.detail || 'Erro ao vincular mapeamentos');
    } finally {
      setVinculando(false);
    }
  };

  const handleDesvincular = async (mappingId: number) => {
    if (!detailEvento) return;
    try {
      await api.post(`/admin/eventos-consolidados/${detailEvento.id}/desvincular`, [mappingId]);
      await refreshDetail();
      fetchAvailableMappings();
      fetchEventos();
    } catch (err: any) {
      setEditError(err.response?.data?.detail || 'Erro ao desvincular mapeamento');
    }
  };

  const toggleMappingSelection = (id: number) => {
    setSelectedMappingIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const getFonteColor = (fonte: string) => {
    return fonte === 'ATIVO'
      ? 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400'
      : 'bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-400';
  };

  const getLinkedCounts = (evento: EventoConsolidado) => {
    const detail = detailEvento?.id === evento.id ? detailEvento : null;
    return detail
      ? {
          ativo: detail.mapeamentos.filter(m => m.fonte === 'ATIVO').length,
          magento: detail.mapeamentos.filter(m => m.fonte === 'MAGENTO').length,
          total: detail.mapeamentos.length
        }
      : null;
  };

  const groupMapeamentosByAno = (mapeamentos: SkuMapping[]) => {
    const grouped: Record<number, { ATIVO: SkuMapping[]; MAGENTO: SkuMapping[] }> = {};
    mapeamentos.forEach(m => {
      if (!grouped[m.ano]) grouped[m.ano] = { ATIVO: [], MAGENTO: [] };
      grouped[m.ano][m.fonte].push(m);
    });
    return grouped;
  };

  return (
    <div className="min-h-screen p-6">
      <div className="max-w-7xl mx-auto">
        <div className={`rounded-2xl shadow-xl overflow-hidden ${
          isDark ? 'bg-gray-800/50 backdrop-blur-sm' : 'bg-white/80 backdrop-blur-sm'
        }`}>
          <div className={`p-6 border-b ${isDark ? 'border-gray-700' : 'border-gray-200'}`}>
            <div className="flex items-center justify-between flex-wrap gap-4">
              <div className="flex items-center gap-3">
                <div className={`p-3 rounded-xl ${
                  isDark ? 'bg-gradient-to-br from-indigo-500 to-purple-600' : 'bg-gradient-to-br from-indigo-400 to-purple-500'
                }`}>
                  <Layers className="w-6 h-6 text-white" />
                </div>
                <div>
                  <h1 className={`text-2xl font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>
                    Relacionamento de Eventos
                  </h1>
                  <p className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>
                    Gerencie eventos consolidados e seus mapeamentos
                  </p>
                </div>
              </div>
              <div className="flex gap-2">
                <button
                  onClick={fetchEventos}
                  className={`p-2 rounded-lg transition-colors ${
                    isDark
                      ? 'bg-gray-700 hover:bg-gray-600 text-gray-300'
                      : 'bg-gray-100 hover:bg-gray-200 text-gray-600'
                  }`}
                  title="Atualizar"
                >
                  <RefreshCw className={`w-5 h-5 ${loading ? 'animate-spin' : ''}`} />
                </button>
                <button
                  onClick={() => {
                    setCreateForm({ nome: '', descricao: '' });
                    setCreateError(null);
                    setShowCreateModal(true);
                  }}
                  className="flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-indigo-500 to-purple-500 text-white rounded-lg hover:from-indigo-600 hover:to-purple-600 transition-all shadow-lg"
                >
                  <Plus className="w-5 h-5" />
                  Novo Evento Consolidado
                </button>
              </div>
            </div>
          </div>

          <div className={`p-4 border-b ${isDark ? 'border-gray-700' : 'border-gray-200'}`}>
            <div className="flex flex-wrap gap-4">
              <div className="flex-1 min-w-[200px]">
                <div className="relative">
                  <Search className={`absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 ${
                    isDark ? 'text-gray-500' : 'text-gray-400'
                  }`} />
                  <input
                    type="text"
                    placeholder="Buscar por nome do evento..."
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    className={`w-full pl-10 pr-4 py-2 rounded-lg border ${
                      isDark
                        ? 'bg-gray-700 border-gray-600 text-white placeholder-gray-400'
                        : 'bg-white border-gray-300 text-gray-900 placeholder-gray-500'
                    } focus:ring-2 focus:ring-indigo-500 focus:border-transparent`}
                  />
                </div>
              </div>
            </div>
          </div>

          <div className="p-6">
            {loading ? (
              <div className="flex justify-center items-center py-12">
                <RefreshCw className={`w-8 h-8 animate-spin ${isDark ? 'text-indigo-400' : 'text-indigo-600'}`} />
              </div>
            ) : error ? (
              <div className={`flex items-center justify-center gap-3 py-12 ${
                isDark ? 'text-red-400' : 'text-red-600'
              }`}>
                <AlertTriangle className="w-6 h-6" />
                <span>{error}</span>
                <button onClick={fetchEventos} className="underline hover:no-underline">
                  Tentar novamente
                </button>
              </div>
            ) : eventos.length === 0 ? (
              <div className={`text-center py-12 ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                <Layers className="w-12 h-12 mx-auto mb-3 opacity-50" />
                <p>Nenhum evento consolidado encontrado</p>
                <button
                  onClick={() => {
                    setCreateForm({ nome: '', descricao: '' });
                    setCreateError(null);
                    setShowCreateModal(true);
                  }}
                  className="mt-4 text-indigo-500 hover:underline"
                >
                  Criar primeiro evento consolidado
                </button>
              </div>
            ) : (
              <div className="space-y-4">
                {eventos.map(evento => (
                  <div
                    key={evento.id}
                    className={`rounded-xl border p-4 cursor-pointer transition-all hover:shadow-md ${
                      isDark
                        ? 'border-gray-700 bg-gray-800/30 hover:bg-gray-700/50'
                        : 'border-gray-200 bg-gray-50/50 hover:bg-gray-100/80'
                    }`}
                    onClick={() => openDetail(evento)}
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-3">
                          <h3 className={`text-lg font-semibold truncate ${isDark ? 'text-white' : 'text-gray-900'}`}>
                            {evento.nome}
                          </h3>
                          <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                            evento.ativo
                              ? 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400'
                              : 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400'
                          }`}>
                            {evento.ativo ? 'Ativo' : 'Inativo'}
                          </span>
                        </div>
                        {evento.descricao && (
                          <p className={`text-sm mt-1 truncate ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                            {evento.descricao}
                          </p>
                        )}
                      </div>
                      <div className="flex items-center gap-2 ml-4">
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            openDetail(evento);
                          }}
                          className={`p-2 rounded-lg transition-colors ${
                            isDark
                              ? 'hover:bg-gray-600 text-gray-400 hover:text-blue-400'
                              : 'hover:bg-gray-200 text-gray-500 hover:text-blue-600'
                          }`}
                          title="Editar"
                        >
                          <Edit2 className="w-4 h-4" />
                        </button>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            setShowDeleteConfirm(evento.id);
                          }}
                          className={`p-2 rounded-lg transition-colors ${
                            isDark
                              ? 'hover:bg-gray-600 text-gray-400 hover:text-red-400'
                              : 'hover:bg-gray-200 text-gray-500 hover:text-red-600'
                          }`}
                          title="Excluir"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {showCreateModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className={`w-full max-w-lg rounded-2xl shadow-2xl ${
            isDark ? 'bg-gray-800' : 'bg-white'
          }`}>
            <div className={`flex items-center justify-between p-6 border-b ${
              isDark ? 'border-gray-700' : 'border-gray-200'
            }`}>
              <h2 className={`text-xl font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>
                Novo Evento Consolidado
              </h2>
              <button
                onClick={() => setShowCreateModal(false)}
                className={`p-2 rounded-lg transition-colors ${
                  isDark ? 'hover:bg-gray-700 text-gray-400' : 'hover:bg-gray-100 text-gray-500'
                }`}
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            <form onSubmit={handleCreate} className="p-6 space-y-4">
              {createError && (
                <div className="flex items-center gap-2 p-3 rounded-lg bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400">
                  <AlertTriangle className="w-4 h-4 flex-shrink-0" />
                  <span className="text-sm">{createError}</span>
                </div>
              )}
              <div>
                <label className={`block text-sm font-medium mb-1 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
                  Nome *
                </label>
                <input
                  type="text"
                  value={createForm.nome}
                  onChange={(e) => setCreateForm(prev => ({ ...prev, nome: e.target.value }))}
                  className={`w-full px-4 py-2 rounded-lg border ${
                    isDark
                      ? 'bg-gray-700 border-gray-600 text-white placeholder-gray-400'
                      : 'bg-white border-gray-300 text-gray-900 placeholder-gray-500'
                  } focus:ring-2 focus:ring-indigo-500 focus:border-transparent`}
                  placeholder="Nome do evento consolidado"
                  required
                />
              </div>
              <div>
                <label className={`block text-sm font-medium mb-1 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
                  Descricao
                </label>
                <textarea
                  value={createForm.descricao}
                  onChange={(e) => setCreateForm(prev => ({ ...prev, descricao: e.target.value }))}
                  className={`w-full px-4 py-2 rounded-lg border ${
                    isDark
                      ? 'bg-gray-700 border-gray-600 text-white placeholder-gray-400'
                      : 'bg-white border-gray-300 text-gray-900 placeholder-gray-500'
                  } focus:ring-2 focus:ring-indigo-500 focus:border-transparent`}
                  placeholder="Descricao opcional"
                  rows={3}
                />
              </div>
              <div className="flex justify-end gap-3 pt-4">
                <button
                  type="button"
                  onClick={() => setShowCreateModal(false)}
                  className={`px-4 py-2 rounded-lg transition-colors ${
                    isDark
                      ? 'bg-gray-700 hover:bg-gray-600 text-gray-300'
                      : 'bg-gray-100 hover:bg-gray-200 text-gray-700'
                  }`}
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  disabled={savingCreate}
                  className="px-4 py-2 bg-gradient-to-r from-indigo-500 to-purple-500 text-white rounded-lg hover:from-indigo-600 hover:to-purple-600 transition-all disabled:opacity-50"
                >
                  {savingCreate ? 'Salvando...' : 'Criar'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {showDeleteConfirm !== null && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className={`w-full max-w-sm rounded-2xl shadow-2xl p-6 ${
            isDark ? 'bg-gray-800' : 'bg-white'
          }`}>
            <div className="flex items-center gap-3 mb-4">
              <div className="p-2 rounded-full bg-red-100 dark:bg-red-900/30">
                <AlertTriangle className="w-6 h-6 text-red-600 dark:text-red-400" />
              </div>
              <h3 className={`text-lg font-semibold ${isDark ? 'text-white' : 'text-gray-900'}`}>
                Confirmar exclusao
              </h3>
            </div>
            <p className={`mb-6 ${isDark ? 'text-gray-300' : 'text-gray-600'}`}>
              Deseja realmente excluir este evento consolidado? Todos os mapeamentos vinculados serao desvinculados.
            </p>
            <div className="flex justify-end gap-3">
              <button
                onClick={() => setShowDeleteConfirm(null)}
                className={`px-4 py-2 rounded-lg transition-colors ${
                  isDark
                    ? 'bg-gray-700 hover:bg-gray-600 text-gray-300'
                    : 'bg-gray-100 hover:bg-gray-200 text-gray-700'
                }`}
              >
                Cancelar
              </button>
              <button
                onClick={() => handleDelete(showDeleteConfirm)}
                className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors"
              >
                Excluir
              </button>
            </div>
          </div>
        </div>
      )}

      {showDetailModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className={`w-full max-w-5xl max-h-[90vh] rounded-2xl shadow-2xl flex flex-col ${
            isDark ? 'bg-gray-800' : 'bg-white'
          }`}>
            <div className={`flex items-center justify-between p-6 border-b flex-shrink-0 ${
              isDark ? 'border-gray-700' : 'border-gray-200'
            }`}>
              <h2 className={`text-xl font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>
                Detalhes do Evento Consolidado
              </h2>
              <button
                onClick={() => {
                  setShowDetailModal(false);
                  setDetailEvento(null);
                }}
                className={`p-2 rounded-lg transition-colors ${
                  isDark ? 'hover:bg-gray-700 text-gray-400' : 'hover:bg-gray-100 text-gray-500'
                }`}
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto p-6 space-y-6">
              {detailLoading ? (
                <div className="flex justify-center items-center py-12">
                  <RefreshCw className={`w-8 h-8 animate-spin ${isDark ? 'text-indigo-400' : 'text-indigo-600'}`} />
                </div>
              ) : detailEvento ? (
                <>
                  {editError && (
                    <div className="flex items-center gap-2 p-3 rounded-lg bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400">
                      <AlertTriangle className="w-4 h-4 flex-shrink-0" />
                      <span className="text-sm">{editError}</span>
                    </div>
                  )}

                  <div className={`rounded-xl border p-4 ${
                    isDark ? 'border-gray-700 bg-gray-800/50' : 'border-gray-200 bg-gray-50'
                  }`}>
                    <h3 className={`text-sm font-semibold mb-3 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
                      Informacoes do Evento
                    </h3>
                    <div className="space-y-3">
                      <div>
                        <label className={`block text-sm font-medium mb-1 ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>
                          Nome
                        </label>
                        <input
                          type="text"
                          value={editNome}
                          onChange={(e) => setEditNome(e.target.value)}
                          className={`w-full px-4 py-2 rounded-lg border ${
                            isDark
                              ? 'bg-gray-700 border-gray-600 text-white'
                              : 'bg-white border-gray-300 text-gray-900'
                          } focus:ring-2 focus:ring-indigo-500 focus:border-transparent`}
                        />
                      </div>
                      <div>
                        <label className={`block text-sm font-medium mb-1 ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>
                          Descricao
                        </label>
                        <textarea
                          value={editDescricao}
                          onChange={(e) => setEditDescricao(e.target.value)}
                          className={`w-full px-4 py-2 rounded-lg border ${
                            isDark
                              ? 'bg-gray-700 border-gray-600 text-white'
                              : 'bg-white border-gray-300 text-gray-900'
                          } focus:ring-2 focus:ring-indigo-500 focus:border-transparent`}
                          rows={2}
                        />
                      </div>
                      <div className="flex justify-end">
                        <button
                          onClick={handleEditSave}
                          disabled={savingEdit || !editNome.trim()}
                          className="px-4 py-2 bg-gradient-to-r from-indigo-500 to-purple-500 text-white rounded-lg hover:from-indigo-600 hover:to-purple-600 transition-all disabled:opacity-50 text-sm"
                        >
                          {savingEdit ? 'Salvando...' : 'Salvar Alteracoes'}
                        </button>
                      </div>
                    </div>
                  </div>

                  <div className={`rounded-xl border p-4 ${
                    isDark ? 'border-gray-700 bg-gray-800/50' : 'border-gray-200 bg-gray-50'
                  }`}>
                    <div className="flex items-center gap-2 mb-4">
                      <Link2 className={`w-5 h-5 ${isDark ? 'text-indigo-400' : 'text-indigo-600'}`} />
                      <h3 className={`text-sm font-semibold ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
                        Mapeamentos Vinculados ({detailEvento.mapeamentos.length})
                      </h3>
                    </div>

                    {detailEvento.mapeamentos.length === 0 ? (
                      <p className={`text-sm py-4 text-center ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>
                        Nenhum mapeamento vinculado a este evento
                      </p>
                    ) : (
                      <div className="space-y-4">
                        {Object.entries(groupMapeamentosByAno(detailEvento.mapeamentos))
                          .sort(([a], [b]) => Number(b) - Number(a))
                          .map(([ano, byFonte]) => (
                            <div key={ano}>
                              <div className={`flex items-center gap-2 mb-2 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
                                <Database className="w-4 h-4" />
                                <span className="text-sm font-semibold">{ano}</span>
                              </div>
                              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                                {(['ATIVO', 'MAGENTO'] as const).map(fonte => (
                                  <div key={fonte}>
                                    <div className={`text-xs font-medium mb-1 px-1 ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                                      {fonte} ({byFonte[fonte].length})
                                    </div>
                                    {byFonte[fonte].length === 0 ? (
                                      <p className={`text-xs px-2 py-1 ${isDark ? 'text-gray-600' : 'text-gray-400'}`}>
                                        Nenhum mapeamento {fonte}
                                      </p>
                                    ) : (
                                      <div className="space-y-1">
                                        {byFonte[fonte].map(m => (
                                          <div
                                            key={m.id}
                                            className={`flex items-center justify-between gap-2 px-3 py-2 rounded-lg text-sm ${
                                              isDark ? 'bg-gray-700/50' : 'bg-white border border-gray-100'
                                            }`}
                                          >
                                            <div className="flex items-center gap-2 flex-1 min-w-0">
                                              <span className={`px-2 py-0.5 rounded text-xs font-medium flex-shrink-0 ${getFonteColor(m.fonte)}`}>
                                                {m.fonte}
                                              </span>
                                              <span className={`truncate ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
                                                {m.nome_evento}
                                              </span>
                                              <span className={`text-xs flex-shrink-0 ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>
                                                ID: {m.id_externo} | SKU: {m.sku}
                                              </span>
                                            </div>
                                            <button
                                              onClick={() => handleDesvincular(m.id)}
                                              className={`p-1 rounded transition-colors flex-shrink-0 ${
                                                isDark
                                                  ? 'hover:bg-red-900/30 text-gray-500 hover:text-red-400'
                                                  : 'hover:bg-red-50 text-gray-400 hover:text-red-600'
                                              }`}
                                              title="Desvincular"
                                            >
                                              <Unlink className="w-4 h-4" />
                                            </button>
                                          </div>
                                        ))}
                                      </div>
                                    )}
                                  </div>
                                ))}
                              </div>
                            </div>
                          ))}
                      </div>
                    )}
                  </div>

                  <div className={`rounded-xl border p-4 ${
                    isDark ? 'border-gray-700 bg-gray-800/50' : 'border-gray-200 bg-gray-50'
                  }`}>
                    <div className="flex items-center gap-2 mb-4">
                      <Plus className={`w-5 h-5 ${isDark ? 'text-green-400' : 'text-green-600'}`} />
                      <h3 className={`text-sm font-semibold ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
                        Adicionar Mapeamentos
                      </h3>
                    </div>

                    <div className="flex flex-wrap gap-3 mb-4">
                      <select
                        value={availableFilterFonte}
                        onChange={(e) => setAvailableFilterFonte(e.target.value)}
                        className={`px-3 py-2 rounded-lg border text-sm ${
                          isDark
                            ? 'bg-gray-700 border-gray-600 text-white'
                            : 'bg-white border-gray-300 text-gray-900'
                        } focus:ring-2 focus:ring-indigo-500`}
                      >
                        <option value="">Todas as Fontes</option>
                        <option value="ATIVO">ATIVO</option>
                        <option value="MAGENTO">MAGENTO</option>
                      </select>

                      <select
                        value={availableFilterAno}
                        onChange={(e) => setAvailableFilterAno(e.target.value)}
                        className={`px-3 py-2 rounded-lg border text-sm ${
                          isDark
                            ? 'bg-gray-700 border-gray-600 text-white'
                            : 'bg-white border-gray-300 text-gray-900'
                        } focus:ring-2 focus:ring-indigo-500`}
                      >
                        <option value="">Todos os Anos</option>
                        {anos.map(a => (
                          <option key={a} value={a}>{a}</option>
                        ))}
                      </select>

                      <div className="relative flex-1 min-w-[150px]">
                        <Search className={`absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 ${
                          isDark ? 'text-gray-500' : 'text-gray-400'
                        }`} />
                        <input
                          type="text"
                          placeholder="Buscar mapeamentos..."
                          value={availableFilterBusca}
                          onChange={(e) => setAvailableFilterBusca(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter') fetchAvailableMappings();
                          }}
                          className={`w-full pl-9 pr-4 py-2 rounded-lg border text-sm ${
                            isDark
                              ? 'bg-gray-700 border-gray-600 text-white placeholder-gray-400'
                              : 'bg-white border-gray-300 text-gray-900 placeholder-gray-500'
                          } focus:ring-2 focus:ring-indigo-500 focus:border-transparent`}
                        />
                      </div>

                      <button
                        onClick={fetchAvailableMappings}
                        className={`px-3 py-2 rounded-lg border text-sm transition-colors ${
                          isDark
                            ? 'bg-gray-700 border-gray-600 text-gray-300 hover:bg-gray-600'
                            : 'bg-white border-gray-300 text-gray-700 hover:bg-gray-50'
                        }`}
                      >
                        <Filter className="w-4 h-4" />
                      </button>
                    </div>

                    {availableLoading ? (
                      <div className="flex justify-center py-6">
                        <RefreshCw className={`w-6 h-6 animate-spin ${isDark ? 'text-indigo-400' : 'text-indigo-600'}`} />
                      </div>
                    ) : availableMappings.length === 0 ? (
                      <p className={`text-sm py-4 text-center ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>
                        Nenhum mapeamento disponivel encontrado
                      </p>
                    ) : (
                      <>
                        <div className={`max-h-64 overflow-y-auto rounded-lg border ${
                          isDark ? 'border-gray-700' : 'border-gray-200'
                        }`}>
                          {availableMappings.map(m => (
                            <div
                              key={m.id}
                              onClick={() => toggleMappingSelection(m.id)}
                              className={`flex items-center gap-3 px-3 py-2 cursor-pointer border-b last:border-b-0 text-sm ${
                                isDark
                                  ? `border-gray-700 ${selectedMappingIds.has(m.id) ? 'bg-indigo-900/20' : 'hover:bg-gray-700/50'}`
                                  : `border-gray-100 ${selectedMappingIds.has(m.id) ? 'bg-indigo-50' : 'hover:bg-gray-50'}`
                              }`}
                            >
                              <div className={`w-5 h-5 rounded border-2 flex items-center justify-center flex-shrink-0 ${
                                selectedMappingIds.has(m.id)
                                  ? 'bg-indigo-500 border-indigo-500'
                                  : isDark ? 'border-gray-600' : 'border-gray-300'
                              }`}>
                                {selectedMappingIds.has(m.id) && <Check className="w-3 h-3 text-white" />}
                              </div>
                              <span className={`px-2 py-0.5 rounded text-xs font-medium flex-shrink-0 ${getFonteColor(m.fonte)}`}>
                                {m.fonte}
                              </span>
                              <span className={`truncate ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
                                {m.nome_evento}
                              </span>
                              <span className={`text-xs flex-shrink-0 ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>
                                {m.ano} | ID: {m.id_externo} | SKU: {m.sku}
                              </span>
                            </div>
                          ))}
                        </div>

                        {selectedMappingIds.size > 0 && (
                          <div className="flex justify-end mt-3">
                            <button
                              onClick={handleVincular}
                              disabled={vinculando}
                              className="flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-green-500 to-emerald-500 text-white rounded-lg hover:from-green-600 hover:to-emerald-600 transition-all disabled:opacity-50 text-sm"
                            >
                              <Link2 className="w-4 h-4" />
                              {vinculando
                                ? 'Vinculando...'
                                : `Vincular Selecionados (${selectedMappingIds.size})`}
                            </button>
                          </div>
                        )}
                      </>
                    )}
                  </div>
                </>
              ) : (
                <div className={`text-center py-12 ${isDark ? 'text-red-400' : 'text-red-600'}`}>
                  <AlertTriangle className="w-8 h-8 mx-auto mb-2" />
                  <p>Erro ao carregar detalhes do evento</p>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default EventosConsolidados;
