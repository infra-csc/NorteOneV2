import React, { useEffect, useState } from 'react';
import { useTheme } from '../../context/ThemeContext';
import api from '../../services/api';
import { 
  Package, Search, Plus, Edit2, Trash2, RefreshCw, 
  AlertTriangle, CheckCircle, XCircle, X, Calendar, Database,
  Link2, Filter
} from 'lucide-react';

interface SkuMapping {
  id: number;
  fonte: 'ATIVO' | 'MAGENTO';
  id_externo: number;
  sku: string;
  evento_grupo: string;
  ano: number;
  nome_evento: string;
  ativo: boolean;
  created_at: string | null;
  updated_at: string | null;
}

interface SkuMappingForm {
  fonte: 'ATIVO' | 'MAGENTO';
  id_externo: number;
  sku: string;
  evento_grupo: string;
  ano: number;
  nome_evento: string;
  ativo: boolean;
}

const fontes = ['ATIVO', 'MAGENTO'] as const;
const currentYear = new Date().getFullYear();
const anos = Array.from({ length: 5 }, (_, i) => currentYear - 2 + i);

const SkuMappings: React.FC = () => {
  const { isDark } = useTheme();
  const [mappings, setMappings] = useState<SkuMapping[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [filterFonte, setFilterFonte] = useState<string>('todos');
  const [filterAno, setFilterAno] = useState<string>('todos');
  const [filterGrupo, setFilterGrupo] = useState<string>('todos');
  const [filterStatus, setFilterStatus] = useState<string>('ativos');
  
  const [grupos, setGrupos] = useState<string[]>([]);
  const [anosDisponiveis, setAnosDisponiveis] = useState<number[]>([]);
  
  const [showModal, setShowModal] = useState(false);
  const [editingMapping, setEditingMapping] = useState<SkuMapping | null>(null);
  const [formData, setFormData] = useState<SkuMappingForm>({
    fonte: 'ATIVO',
    id_externo: 0,
    sku: '',
    evento_grupo: '',
    ano: currentYear,
    nome_evento: '',
    ativo: true
  });
  const [formError, setFormError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState<number | null>(null);

  const fetchData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [mappingsRes, gruposRes, anosRes] = await Promise.all([
        api.get('/admin/sku-mappings'),
        api.get('/admin/sku-mappings/grupos'),
        api.get('/admin/sku-mappings/anos')
      ]);
      setMappings(mappingsRes.data);
      setGrupos(gruposRes.data);
      setAnosDisponiveis(anosRes.data.length > 0 ? anosRes.data : anos);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Erro ao carregar dados');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const filteredMappings = mappings.filter(m => {
    const matchesSearch = !search || 
      m.nome_evento.toLowerCase().includes(search.toLowerCase()) ||
      m.sku.toLowerCase().includes(search.toLowerCase()) ||
      m.evento_grupo.toLowerCase().includes(search.toLowerCase()) ||
      m.id_externo.toString().includes(search);
    const matchesFonte = filterFonte === 'todos' || m.fonte === filterFonte;
    const matchesAno = filterAno === 'todos' || m.ano === parseInt(filterAno);
    const matchesGrupo = filterGrupo === 'todos' || m.evento_grupo === filterGrupo;
    const matchesStatus = filterStatus === 'todos' || 
      (filterStatus === 'ativos' ? m.ativo : !m.ativo);
    return matchesSearch && matchesFonte && matchesAno && matchesGrupo && matchesStatus;
  });

  const groupedMappings = filteredMappings.reduce((acc, m) => {
    if (!acc[m.evento_grupo]) {
      acc[m.evento_grupo] = [];
    }
    acc[m.evento_grupo].push(m);
    return acc;
  }, {} as Record<string, SkuMapping[]>);

  const openCreateModal = () => {
    setEditingMapping(null);
    setFormData({
      fonte: 'ATIVO',
      id_externo: 0,
      sku: '',
      evento_grupo: '',
      ano: currentYear,
      nome_evento: '',
      ativo: true
    });
    setFormError(null);
    setShowModal(true);
  };

  const openEditModal = (mapping: SkuMapping) => {
    setEditingMapping(mapping);
    setFormData({
      fonte: mapping.fonte,
      id_externo: mapping.id_externo,
      sku: mapping.sku,
      evento_grupo: mapping.evento_grupo,
      ano: mapping.ano,
      nome_evento: mapping.nome_evento,
      ativo: mapping.ativo
    });
    setFormError(null);
    setShowModal(true);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);
    setSaving(true);

    try {
      if (editingMapping) {
        await api.put(`/admin/sku-mappings/${editingMapping.id}`, formData);
      } else {
        await api.post('/admin/sku-mappings', formData);
      }
      setShowModal(false);
      fetchData();
    } catch (err: any) {
      setFormError(err.response?.data?.detail || 'Erro ao salvar mapeamento');
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await api.delete(`/admin/sku-mappings/${id}`);
      setShowDeleteConfirm(null);
      fetchData();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Erro ao excluir mapeamento');
    }
  };

  const getFonteColor = (fonte: string) => {
    return fonte === 'ATIVO' 
      ? 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400'
      : 'bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-400';
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
                  isDark ? 'bg-gradient-to-br from-emerald-500 to-teal-600' : 'bg-gradient-to-br from-emerald-400 to-teal-500'
                }`}>
                  <Package className="w-6 h-6 text-white" />
                </div>
                <div>
                  <h1 className={`text-2xl font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>
                    Mapeamento de SKUs
                  </h1>
                  <p className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>
                    Gerencie a consolidação de eventos entre Ativo e Magento
                  </p>
                </div>
              </div>
              <div className="flex gap-2">
                <button
                  onClick={fetchData}
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
                  onClick={openCreateModal}
                  className="flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-emerald-500 to-teal-500 text-white rounded-lg hover:from-emerald-600 hover:to-teal-600 transition-all shadow-lg"
                >
                  <Plus className="w-5 h-5" />
                  Novo Mapeamento
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
                    placeholder="Buscar por nome, SKU, grupo ou ID..."
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    className={`w-full pl-10 pr-4 py-2 rounded-lg border ${
                      isDark 
                        ? 'bg-gray-700 border-gray-600 text-white placeholder-gray-400' 
                        : 'bg-white border-gray-300 text-gray-900 placeholder-gray-500'
                    } focus:ring-2 focus:ring-emerald-500 focus:border-transparent`}
                  />
                </div>
              </div>
              
              <select
                value={filterFonte}
                onChange={(e) => setFilterFonte(e.target.value)}
                className={`px-4 py-2 rounded-lg border ${
                  isDark 
                    ? 'bg-gray-700 border-gray-600 text-white' 
                    : 'bg-white border-gray-300 text-gray-900'
                } focus:ring-2 focus:ring-emerald-500`}
              >
                <option value="todos">Todas as Fontes</option>
                {fontes.map(f => (
                  <option key={f} value={f}>{f}</option>
                ))}
              </select>

              <select
                value={filterAno}
                onChange={(e) => setFilterAno(e.target.value)}
                className={`px-4 py-2 rounded-lg border ${
                  isDark 
                    ? 'bg-gray-700 border-gray-600 text-white' 
                    : 'bg-white border-gray-300 text-gray-900'
                } focus:ring-2 focus:ring-emerald-500`}
              >
                <option value="todos">Todos os Anos</option>
                {(anosDisponiveis.length > 0 ? anosDisponiveis : anos).map(a => (
                  <option key={a} value={a}>{a}</option>
                ))}
              </select>

              <select
                value={filterGrupo}
                onChange={(e) => setFilterGrupo(e.target.value)}
                className={`px-4 py-2 rounded-lg border ${
                  isDark 
                    ? 'bg-gray-700 border-gray-600 text-white' 
                    : 'bg-white border-gray-300 text-gray-900'
                } focus:ring-2 focus:ring-emerald-500`}
              >
                <option value="todos">Todos os Grupos</option>
                {grupos.map(g => (
                  <option key={g} value={g}>{g}</option>
                ))}
              </select>

              <select
                value={filterStatus}
                onChange={(e) => setFilterStatus(e.target.value)}
                className={`px-4 py-2 rounded-lg border ${
                  isDark 
                    ? 'bg-gray-700 border-gray-600 text-white' 
                    : 'bg-white border-gray-300 text-gray-900'
                } focus:ring-2 focus:ring-emerald-500`}
              >
                <option value="ativos">Ativos</option>
                <option value="inativos">Inativos</option>
                <option value="todos">Todos</option>
              </select>
            </div>
          </div>

          <div className="p-6">
            {loading ? (
              <div className="flex justify-center items-center py-12">
                <RefreshCw className={`w-8 h-8 animate-spin ${isDark ? 'text-emerald-400' : 'text-emerald-600'}`} />
              </div>
            ) : error ? (
              <div className={`flex items-center justify-center gap-3 py-12 ${
                isDark ? 'text-red-400' : 'text-red-600'
              }`}>
                <AlertTriangle className="w-6 h-6" />
                <span>{error}</span>
                <button onClick={fetchData} className="underline hover:no-underline">
                  Tentar novamente
                </button>
              </div>
            ) : Object.keys(groupedMappings).length === 0 ? (
              <div className={`text-center py-12 ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                <Package className="w-12 h-12 mx-auto mb-3 opacity-50" />
                <p>Nenhum mapeamento encontrado</p>
                <button 
                  onClick={openCreateModal}
                  className="mt-4 text-emerald-500 hover:underline"
                >
                  Criar primeiro mapeamento
                </button>
              </div>
            ) : (
              <div className="space-y-6">
                {Object.entries(groupedMappings).sort(([a], [b]) => a.localeCompare(b)).map(([grupo, items]) => (
                  <div key={grupo} className={`rounded-xl overflow-hidden border ${
                    isDark ? 'border-gray-700 bg-gray-800/30' : 'border-gray-200 bg-gray-50/50'
                  }`}>
                    <div className={`px-4 py-3 flex items-center gap-3 ${
                      isDark ? 'bg-gray-700/50' : 'bg-gray-100'
                    }`}>
                      <Link2 className={`w-5 h-5 ${isDark ? 'text-emerald-400' : 'text-emerald-600'}`} />
                      <span className={`font-semibold ${isDark ? 'text-white' : 'text-gray-900'}`}>
                        {grupo}
                      </span>
                      <span className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                        ({items.length} {items.length === 1 ? 'evento' : 'eventos'})
                      </span>
                    </div>
                    <div className="divide-y divide-gray-200 dark:divide-gray-700">
                      {items.sort((a, b) => b.ano - a.ano || a.fonte.localeCompare(b.fonte)).map(mapping => (
                        <div key={mapping.id} className={`p-4 flex items-center justify-between gap-4 ${
                          !mapping.ativo ? 'opacity-50' : ''
                        }`}>
                          <div className="flex items-center gap-4 flex-1">
                            <div className="flex flex-col gap-1">
                              <div className="flex items-center gap-2">
                                <span className={`px-2 py-0.5 rounded text-xs font-medium ${getFonteColor(mapping.fonte)}`}>
                                  {mapping.fonte}
                                </span>
                                <span className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                                  ID: {mapping.id_externo}
                                </span>
                              </div>
                              <span className={`font-medium ${isDark ? 'text-white' : 'text-gray-900'}`}>
                                {mapping.nome_evento}
                              </span>
                            </div>
                          </div>
                          
                          <div className="flex items-center gap-4">
                            <div className={`px-3 py-1 rounded-lg ${
                              isDark ? 'bg-gray-700' : 'bg-gray-100'
                            }`}>
                              <span className={`text-sm font-mono ${isDark ? 'text-emerald-400' : 'text-emerald-600'}`}>
                                {mapping.sku}
                              </span>
                            </div>
                            
                            <div className="flex items-center gap-1">
                              <Calendar className={`w-4 h-4 ${isDark ? 'text-gray-500' : 'text-gray-400'}`} />
                              <span className={`text-sm font-medium ${isDark ? 'text-gray-300' : 'text-gray-600'}`}>
                                {mapping.ano}
                              </span>
                            </div>
                            
                            <div className="flex items-center gap-1">
                              <button
                                onClick={() => openEditModal(mapping)}
                                className={`p-2 rounded-lg transition-colors ${
                                  isDark 
                                    ? 'hover:bg-gray-700 text-gray-400 hover:text-white' 
                                    : 'hover:bg-gray-200 text-gray-500 hover:text-gray-700'
                                }`}
                                title="Editar"
                              >
                                <Edit2 className="w-4 h-4" />
                              </button>
                              <button
                                onClick={() => setShowDeleteConfirm(mapping.id)}
                                className={`p-2 rounded-lg transition-colors ${
                                  isDark 
                                    ? 'hover:bg-red-900/30 text-gray-400 hover:text-red-400' 
                                    : 'hover:bg-red-100 text-gray-500 hover:text-red-600'
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
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
          <div className={`w-full max-w-lg rounded-2xl shadow-2xl ${
            isDark ? 'bg-gray-800' : 'bg-white'
          }`}>
            <div className={`flex items-center justify-between p-6 border-b ${
              isDark ? 'border-gray-700' : 'border-gray-200'
            }`}>
              <h2 className={`text-xl font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>
                {editingMapping ? 'Editar Mapeamento' : 'Novo Mapeamento'}
              </h2>
              <button
                onClick={() => setShowModal(false)}
                className={`p-2 rounded-lg transition-colors ${
                  isDark ? 'hover:bg-gray-700 text-gray-400' : 'hover:bg-gray-100 text-gray-500'
                }`}
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleSubmit} className="p-6 space-y-4">
              {formError && (
                <div className="flex items-center gap-2 p-3 rounded-lg bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-400">
                  <AlertTriangle className="w-5 h-5 flex-shrink-0" />
                  <span className="text-sm">{formError}</span>
                </div>
              )}

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className={`block text-sm font-medium mb-1 ${
                    isDark ? 'text-gray-300' : 'text-gray-700'
                  }`}>
                    Fonte *
                  </label>
                  <select
                    required
                    value={formData.fonte}
                    onChange={(e) => setFormData({ ...formData, fonte: e.target.value as 'ATIVO' | 'MAGENTO' })}
                    className={`w-full px-4 py-2 rounded-lg border ${
                      isDark 
                        ? 'bg-gray-700 border-gray-600 text-white' 
                        : 'bg-white border-gray-300 text-gray-900'
                    } focus:ring-2 focus:ring-emerald-500`}
                  >
                    {fontes.map(f => (
                      <option key={f} value={f}>{f}</option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className={`block text-sm font-medium mb-1 ${
                    isDark ? 'text-gray-300' : 'text-gray-700'
                  }`}>
                    ID Externo *
                  </label>
                  <input
                    type="number"
                    required
                    value={formData.id_externo || ''}
                    onChange={(e) => setFormData({ ...formData, id_externo: parseInt(e.target.value) || 0 })}
                    placeholder="Ex: 40048"
                    className={`w-full px-4 py-2 rounded-lg border ${
                      isDark 
                        ? 'bg-gray-700 border-gray-600 text-white placeholder-gray-400' 
                        : 'bg-white border-gray-300 text-gray-900 placeholder-gray-500'
                    } focus:ring-2 focus:ring-emerald-500`}
                  />
                </div>
              </div>

              <div>
                <label className={`block text-sm font-medium mb-1 ${
                  isDark ? 'text-gray-300' : 'text-gray-700'
                }`}>
                  Nome do Evento *
                </label>
                <input
                  type="text"
                  required
                  value={formData.nome_evento}
                  onChange={(e) => setFormData({ ...formData, nome_evento: e.target.value })}
                  placeholder="Ex: Corrida do Esporte 2026 - Planalto"
                  className={`w-full px-4 py-2 rounded-lg border ${
                    isDark 
                      ? 'bg-gray-700 border-gray-600 text-white placeholder-gray-400' 
                      : 'bg-white border-gray-300 text-gray-900 placeholder-gray-500'
                  } focus:ring-2 focus:ring-emerald-500`}
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className={`block text-sm font-medium mb-1 ${
                    isDark ? 'text-gray-300' : 'text-gray-700'
                  }`}>
                    SKU *
                  </label>
                  <input
                    type="text"
                    required
                    value={formData.sku}
                    onChange={(e) => setFormData({ ...formData, sku: e.target.value.toUpperCase() })}
                    placeholder="Ex: CDE26PL1"
                    className={`w-full px-4 py-2 rounded-lg border font-mono ${
                      isDark 
                        ? 'bg-gray-700 border-gray-600 text-white placeholder-gray-400' 
                        : 'bg-white border-gray-300 text-gray-900 placeholder-gray-500'
                    } focus:ring-2 focus:ring-emerald-500`}
                  />
                </div>

                <div>
                  <label className={`block text-sm font-medium mb-1 ${
                    isDark ? 'text-gray-300' : 'text-gray-700'
                  }`}>
                    Ano *
                  </label>
                  <select
                    required
                    value={formData.ano}
                    onChange={(e) => setFormData({ ...formData, ano: parseInt(e.target.value) })}
                    className={`w-full px-4 py-2 rounded-lg border ${
                      isDark 
                        ? 'bg-gray-700 border-gray-600 text-white' 
                        : 'bg-white border-gray-300 text-gray-900'
                    } focus:ring-2 focus:ring-emerald-500`}
                  >
                    {anos.map(a => (
                      <option key={a} value={a}>{a}</option>
                    ))}
                  </select>
                </div>
              </div>

              <div>
                <label className={`block text-sm font-medium mb-1 ${
                  isDark ? 'text-gray-300' : 'text-gray-700'
                }`}>
                  Grupo do Evento *
                </label>
                <input
                  type="text"
                  required
                  value={formData.evento_grupo}
                  onChange={(e) => setFormData({ ...formData, evento_grupo: e.target.value })}
                  placeholder="Ex: CORRIDA_ESPORTE_PLANALTO"
                  list="grupos-list"
                  className={`w-full px-4 py-2 rounded-lg border ${
                    isDark 
                      ? 'bg-gray-700 border-gray-600 text-white placeholder-gray-400' 
                      : 'bg-white border-gray-300 text-gray-900 placeholder-gray-500'
                  } focus:ring-2 focus:ring-emerald-500`}
                />
                <datalist id="grupos-list">
                  {grupos.map(g => (
                    <option key={g} value={g} />
                  ))}
                </datalist>
                <p className={`text-xs mt-1 ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>
                  Use o mesmo grupo para eventos equivalentes em anos diferentes
                </p>
              </div>

              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  id="ativo"
                  checked={formData.ativo}
                  onChange={(e) => setFormData({ ...formData, ativo: e.target.checked })}
                  className="w-4 h-4 rounded border-gray-300 text-emerald-500 focus:ring-emerald-500"
                />
                <label htmlFor="ativo" className={`text-sm ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
                  Mapeamento ativo
                </label>
              </div>

              <div className="flex justify-end gap-3 pt-4">
                <button
                  type="button"
                  onClick={() => setShowModal(false)}
                  className={`px-4 py-2 rounded-lg ${
                    isDark 
                      ? 'bg-gray-700 text-gray-300 hover:bg-gray-600' 
                      : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                  } transition-colors`}
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  disabled={saving}
                  className="flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-emerald-500 to-teal-500 text-white rounded-lg hover:from-emerald-600 hover:to-teal-600 transition-all disabled:opacity-50"
                >
                  {saving ? (
                    <RefreshCw className="w-4 h-4 animate-spin" />
                  ) : (
                    <CheckCircle className="w-4 h-4" />
                  )}
                  {editingMapping ? 'Salvar Alterações' : 'Criar Mapeamento'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {showDeleteConfirm !== null && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
          <div className={`w-full max-w-md rounded-2xl shadow-2xl p-6 ${
            isDark ? 'bg-gray-800' : 'bg-white'
          }`}>
            <div className="flex items-center gap-3 mb-4">
              <div className="p-3 rounded-full bg-red-100 dark:bg-red-900/30">
                <AlertTriangle className="w-6 h-6 text-red-600 dark:text-red-400" />
              </div>
              <div>
                <h3 className={`font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>
                  Confirmar Exclusão
                </h3>
                <p className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                  Esta ação não pode ser desfeita
                </p>
              </div>
            </div>
            <div className="flex justify-end gap-3">
              <button
                onClick={() => setShowDeleteConfirm(null)}
                className={`px-4 py-2 rounded-lg ${
                  isDark 
                    ? 'bg-gray-700 text-gray-300 hover:bg-gray-600' 
                    : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                } transition-colors`}
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
    </div>
  );
};

export default SkuMappings;
