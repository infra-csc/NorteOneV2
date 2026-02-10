import React, { useEffect, useState } from 'react';
import { useTheme } from '../../context/ThemeContext';
import api from '../../services/api';
import { 
  Package, Search, Plus, Edit2, Trash2, RefreshCw, 
  AlertTriangle, CheckCircle, X, Calendar,
  Link2, Filter, Check, FolderOpen, Globe, ChevronDown, ChevronRight
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

interface EventoSugerido {
  id_evento: string;
  nome_evento: string;
  sku_original: string | null;
  data_evento: string | null;
  fonte: string;
  ano: number;
  sku_sugerido: string | null;
  evento_grupo_sugerido: string | null;
  match_origem: string | null;
  selecionado?: boolean;
  evento_grupo_editado?: string;
}

interface EventoSemMatch {
  id_evento: string;
  nome_evento: string;
  sku_original: string | null;
  data_evento: string | null;
  fonte: string;
  ano: number;
  selecionado?: boolean;
  evento_grupo_editado?: string;
  sku_editado?: string;
}

interface EventoGrupo {
  id: number;
  nome: string;
  descricao: string | null;
  ativo: boolean;
  created_at: string | null;
  updated_at: string | null;
}

const fontes = ['ATIVO', 'MAGENTO'] as const;
const currentYear = new Date().getFullYear();
const anos = Array.from({ length: 5 }, (_, i) => currentYear - 2 + i);

type TabType = 'mapeamentos' | 'eventos' | 'grupos';

const SkuMappings: React.FC = () => {
  const { isDark } = useTheme();
  const [activeTab, setActiveTab] = useState<TabType>('mapeamentos');

  const [mappings, setMappings] = useState<SkuMapping[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [filterFonte, setFilterFonte] = useState<string>('todos');
  const [filterAno, setFilterAno] = useState<string>('todos');
  const [filterGrupo, setFilterGrupo] = useState<string>('todos');
  const [filterStatus, setFilterStatus] = useState<string>('ativos');
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(new Set());

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

  const [loadingEventos, setLoadingEventos] = useState(false);
  const [eventosSugeridos, setEventosSugeridos] = useState<EventoSugerido[]>([]);
  const [eventosSemMatch, setEventosSemMatch] = useState<EventoSemMatch[]>([]);
  const [eventosError, setEventosError] = useState<string | null>(null);
  const [savingImport, setSavingImport] = useState(false);
  const [eventosLoaded, setEventosLoaded] = useState(false);

  const [eventoGrupos, setEventoGrupos] = useState<EventoGrupo[]>([]);
  const [loadingGrupos, setLoadingGrupos] = useState(false);
  const [gruposError, setGruposError] = useState<string | null>(null);
  const [showGrupoModal, setShowGrupoModal] = useState(false);
  const [editingGrupo, setEditingGrupo] = useState<EventoGrupo | null>(null);
  const [grupoFormData, setGrupoFormData] = useState({ nome: '', descricao: '', ativo: true });
  const [grupoFormError, setGrupoFormError] = useState<string | null>(null);
  const [savingGrupo, setSavingGrupo] = useState(false);
  const [showDeleteGrupoConfirm, setShowDeleteGrupoConfirm] = useState<number | null>(null);

  const fetchMappings = async () => {
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

  const fetchEventosExternos = async () => {
    setLoadingEventos(true);
    setEventosError(null);
    try {
      const res = await api.get('/admin/sku-mappings/descobrir-eventos', { timeout: 90000 });
      if (!res.data) {
        setEventosError('Resposta vazia do servidor');
        setEventosLoaded(true);
        return;
      }
      const sugeridos = (res.data.eventos_sugeridos || []).map((e: EventoSugerido) => ({
        ...e,
        selecionado: true,
        evento_grupo_editado: e.evento_grupo_sugerido || ''
      }));
      const semMatch = (res.data.eventos_sem_match || []).map((e: EventoSemMatch) => ({
        ...e,
        selecionado: false,
        evento_grupo_editado: '',
        sku_editado: ''
      }));
      setEventosSugeridos(sugeridos);
      setEventosSemMatch(semMatch);
      setEventosLoaded(true);
    } catch (err: any) {
      const msg = err.code === 'ECONNABORTED' 
        ? 'Tempo limite excedido. Os bancos externos podem estar lentos ou indisponíveis.'
        : err.response?.data?.detail || 'Erro ao buscar eventos externos. Verifique a conexão com os bancos.';
      setEventosError(msg);
      setEventosLoaded(true);
    } finally {
      setLoadingEventos(false);
    }
  };

  const fetchEventoGrupos = async () => {
    setLoadingGrupos(true);
    setGruposError(null);
    try {
      const res = await api.get('/admin/evento-grupos');
      setEventoGrupos(res.data);
    } catch (err: any) {
      setGruposError(err.response?.data?.detail || 'Erro ao carregar grupos');
    } finally {
      setLoadingGrupos(false);
    }
  };

  useEffect(() => {
    fetchMappings();
    fetchEventoGrupos();
  }, []);

  useEffect(() => {
    if (activeTab === 'eventos' && !eventosLoaded) {
      fetchEventosExternos();
    }
    if (activeTab === 'grupos') {
      fetchEventoGrupos();
    }
  }, [activeTab]);

  const filteredMappings = mappings.filter(m => {
    const matchesSearch = !search || 
      m.nome_evento.toLowerCase().includes(search.toLowerCase()) ||
      m.sku.toLowerCase().includes(search.toLowerCase()) ||
      (m.evento_grupo && m.evento_grupo.toLowerCase().includes(search.toLowerCase())) ||
      m.id_externo.toString().includes(search);
    const matchesFonte = filterFonte === 'todos' || m.fonte === filterFonte;
    const matchesAno = filterAno === 'todos' || m.ano === parseInt(filterAno);
    const matchesGrupo = filterGrupo === 'todos' || m.evento_grupo === filterGrupo;
    const matchesStatus = filterStatus === 'todos' || 
      (filterStatus === 'ativos' ? m.ativo : !m.ativo);
    return matchesSearch && matchesFonte && matchesAno && matchesGrupo && matchesStatus;
  });

  const groupedMappings = filteredMappings.reduce((acc, m) => {
    const key = m.evento_grupo || '(Sem Grupo)';
    if (!acc[key]) acc[key] = [];
    acc[key].push(m);
    return acc;
  }, {} as Record<string, SkuMapping[]>);

  const toggleGroupCollapse = (grupo: string) => {
    setCollapsedGroups(prev => {
      const next = new Set(prev);
      if (next.has(grupo)) next.delete(grupo);
      else next.add(grupo);
      return next;
    });
  };

  const openCreateModal = () => {
    setEditingMapping(null);
    setFormData({ fonte: 'ATIVO', id_externo: 0, sku: '', evento_grupo: '', ano: currentYear, nome_evento: '', ativo: true });
    setFormError(null);
    setShowModal(true);
  };

  const openEditModal = (mapping: SkuMapping) => {
    setEditingMapping(mapping);
    setFormData({
      fonte: mapping.fonte, id_externo: mapping.id_externo, sku: mapping.sku,
      evento_grupo: mapping.evento_grupo, ano: mapping.ano, nome_evento: mapping.nome_evento, ativo: mapping.ativo
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
      fetchMappings();
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
      fetchMappings();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Erro ao excluir mapeamento');
    }
  };

  const toggleEventoSelecionado = (index: number, type: 'sugerido' | 'semMatch') => {
    if (type === 'sugerido') {
      setEventosSugeridos(prev => prev.map((e, i) => i === index ? { ...e, selecionado: !e.selecionado } : e));
    } else {
      setEventosSemMatch(prev => prev.map((e, i) => i === index ? { ...e, selecionado: !e.selecionado } : e));
    }
  };

  const updateEventoGrupoField = (index: number, value: string, type: 'sugerido' | 'semMatch') => {
    if (type === 'sugerido') {
      setEventosSugeridos(prev => prev.map((e, i) => i === index ? { ...e, evento_grupo_editado: value } : e));
    } else {
      setEventosSemMatch(prev => prev.map((e, i) => i === index ? { ...e, evento_grupo_editado: value } : e));
    }
  };

  const salvarMapeamentosImportados = async () => {
    const selecionadosSugeridos = eventosSugeridos.filter(e => e.selecionado && e.evento_grupo_editado);
    const selecionadosSemMatch = eventosSemMatch.filter(e => e.selecionado && e.evento_grupo_editado);
    const total = selecionadosSugeridos.length + selecionadosSemMatch.length;

    if (total === 0) {
      setEventosError('Selecione pelo menos um evento com grupo preenchido para importar');
      return;
    }

    setSavingImport(true);
    setEventosError(null);

    try {
      const mappingsToCreate = [
        ...selecionadosSugeridos.map(e => ({
          fonte: e.fonte,
          id_externo: parseInt(e.id_evento),
          sku: e.sku_sugerido || e.sku_original || `${e.evento_grupo_editado}${e.ano}`,
          evento_grupo: e.evento_grupo_editado,
          ano: e.ano,
          nome_evento: e.nome_evento,
          ativo: true
        })),
        ...selecionadosSemMatch.map(e => ({
          fonte: e.fonte,
          id_externo: parseInt(e.id_evento),
          sku: e.sku_editado || e.sku_original || `${e.evento_grupo_editado}${e.ano}`,
          evento_grupo: e.evento_grupo_editado,
          ano: e.ano,
          nome_evento: e.nome_evento,
          ativo: true
        }))
      ];

      await api.post('/admin/sku-mappings/bulk', mappingsToCreate);
      setEventosLoaded(false);
      fetchEventosExternos();
      fetchMappings();
    } catch (err: any) {
      setEventosError(err.response?.data?.detail || 'Erro ao salvar mapeamentos');
    } finally {
      setSavingImport(false);
    }
  };

  const openCreateGrupoModal = () => {
    setEditingGrupo(null);
    setGrupoFormData({ nome: '', descricao: '', ativo: true });
    setGrupoFormError(null);
    setShowGrupoModal(true);
  };

  const openEditGrupoModal = (grupo: EventoGrupo) => {
    setEditingGrupo(grupo);
    setGrupoFormData({ nome: grupo.nome, descricao: grupo.descricao || '', ativo: grupo.ativo });
    setGrupoFormError(null);
    setShowGrupoModal(true);
  };

  const handleGrupoSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setGrupoFormError(null);
    setSavingGrupo(true);
    try {
      if (editingGrupo) {
        await api.put(`/admin/evento-grupos/${editingGrupo.id}`, grupoFormData);
      } else {
        await api.post('/admin/evento-grupos', grupoFormData);
      }
      setShowGrupoModal(false);
      fetchEventoGrupos();
      fetchMappings();
    } catch (err: any) {
      setGrupoFormError(err.response?.data?.detail || 'Erro ao salvar grupo');
    } finally {
      setSavingGrupo(false);
    }
  };

  const handleDeleteGrupo = async (id: number) => {
    try {
      await api.delete(`/admin/evento-grupos/${id}`);
      setShowDeleteGrupoConfirm(null);
      fetchEventoGrupos();
    } catch (err: any) {
      setGruposError(err.response?.data?.detail || 'Erro ao excluir grupo');
    }
  };

  const getFonteColor = (fonte: string) => {
    return fonte === 'ATIVO' 
      ? 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400'
      : 'bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-400';
  };

  const allGrupoNames = [
    ...new Set([
      ...grupos,
      ...eventoGrupos.map(g => g.nome)
    ])
  ].sort();

  const tabs: { key: TabType; label: string; icon: React.ReactNode }[] = [
    { key: 'mapeamentos', label: 'Mapeamentos', icon: <Link2 className="w-4 h-4" /> },
    { key: 'eventos', label: 'Eventos Externos', icon: <Globe className="w-4 h-4" /> },
    { key: 'grupos', label: 'Grupos de Evento', icon: <FolderOpen className="w-4 h-4" /> },
  ];

  return (
    <div className="min-h-screen p-6">
      <div className="max-w-7xl mx-auto">
        <div className={`rounded-2xl shadow-xl overflow-hidden ${
          isDark ? 'bg-gray-800/50 backdrop-blur-sm' : 'bg-white/80 backdrop-blur-sm'
        }`}>
          <div className={`p-6 border-b ${isDark ? 'border-gray-700' : 'border-gray-200'}`}>
            <div className="flex items-center gap-3 mb-4">
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
                  Gerencie eventos, grupos e mapeamentos entre Ativo e Magento
                </p>
              </div>
            </div>

            <div className="flex gap-1">
              {tabs.map(tab => (
                <button
                  key={tab.key}
                  onClick={() => setActiveTab(tab.key)}
                  className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                    activeTab === tab.key
                      ? isDark
                        ? 'bg-emerald-600 text-white'
                        : 'bg-emerald-500 text-white'
                      : isDark
                        ? 'text-gray-400 hover:text-white hover:bg-gray-700'
                        : 'text-gray-600 hover:text-gray-900 hover:bg-gray-100'
                  }`}
                >
                  {tab.icon}
                  {tab.label}
                </button>
              ))}
            </div>
          </div>

          {activeTab === 'mapeamentos' && (
            <>
              <div className={`p-4 border-b ${isDark ? 'border-gray-700' : 'border-gray-200'}`}>
                <div className="flex flex-wrap gap-3 items-center">
                  <div className="flex-1 min-w-[200px]">
                    <div className="relative">
                      <Search className={`absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 ${isDark ? 'text-gray-500' : 'text-gray-400'}`} />
                      <input
                        type="text"
                        placeholder="Buscar por nome, SKU, grupo ou ID..."
                        value={search}
                        onChange={(e) => setSearch(e.target.value)}
                        className={`w-full pl-10 pr-4 py-2 rounded-lg border ${
                          isDark ? 'bg-gray-700 border-gray-600 text-white placeholder-gray-400' : 'bg-white border-gray-300 text-gray-900 placeholder-gray-500'
                        } focus:ring-2 focus:ring-emerald-500 focus:border-transparent`}
                      />
                    </div>
                  </div>
                  <select value={filterFonte} onChange={(e) => setFilterFonte(e.target.value)}
                    className={`px-3 py-2 rounded-lg border text-sm ${isDark ? 'bg-gray-700 border-gray-600 text-white' : 'bg-white border-gray-300 text-gray-900'}`}>
                    <option value="todos">Todas Fontes</option>
                    {fontes.map(f => <option key={f} value={f}>{f}</option>)}
                  </select>
                  <select value={filterAno} onChange={(e) => setFilterAno(e.target.value)}
                    className={`px-3 py-2 rounded-lg border text-sm ${isDark ? 'bg-gray-700 border-gray-600 text-white' : 'bg-white border-gray-300 text-gray-900'}`}>
                    <option value="todos">Todos Anos</option>
                    {(anosDisponiveis.length > 0 ? anosDisponiveis : anos).map(a => <option key={a} value={a}>{a}</option>)}
                  </select>
                  <select value={filterGrupo} onChange={(e) => setFilterGrupo(e.target.value)}
                    className={`px-3 py-2 rounded-lg border text-sm ${isDark ? 'bg-gray-700 border-gray-600 text-white' : 'bg-white border-gray-300 text-gray-900'}`}>
                    <option value="todos">Todos Grupos</option>
                    {grupos.map(g => <option key={g} value={g}>{g}</option>)}
                  </select>
                  <select value={filterStatus} onChange={(e) => setFilterStatus(e.target.value)}
                    className={`px-3 py-2 rounded-lg border text-sm ${isDark ? 'bg-gray-700 border-gray-600 text-white' : 'bg-white border-gray-300 text-gray-900'}`}>
                    <option value="ativos">Ativos</option>
                    <option value="inativos">Inativos</option>
                    <option value="todos">Todos</option>
                  </select>
                  <button onClick={fetchMappings} className={`p-2 rounded-lg ${isDark ? 'bg-gray-700 hover:bg-gray-600 text-gray-300' : 'bg-gray-100 hover:bg-gray-200 text-gray-600'}`} title="Atualizar">
                    <RefreshCw className={`w-5 h-5 ${loading ? 'animate-spin' : ''}`} />
                  </button>
                  <button onClick={openCreateModal}
                    className="flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-emerald-500 to-teal-500 text-white rounded-lg hover:from-emerald-600 hover:to-teal-600 transition-all shadow-lg text-sm">
                    <Plus className="w-4 h-4" />
                    Novo
                  </button>
                </div>
              </div>

              <div className="p-6">
                {loading ? (
                  <div className="flex justify-center items-center py-12">
                    <RefreshCw className={`w-8 h-8 animate-spin ${isDark ? 'text-emerald-400' : 'text-emerald-600'}`} />
                  </div>
                ) : error ? (
                  <div className={`flex items-center justify-center gap-3 py-12 ${isDark ? 'text-red-400' : 'text-red-600'}`}>
                    <AlertTriangle className="w-6 h-6" />
                    <span>{error}</span>
                    <button onClick={fetchMappings} className="underline hover:no-underline">Tentar novamente</button>
                  </div>
                ) : Object.keys(groupedMappings).length === 0 ? (
                  <div className={`text-center py-12 ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                    <Package className="w-12 h-12 mx-auto mb-3 opacity-50" />
                    <p>Nenhum mapeamento encontrado</p>
                    <button onClick={openCreateModal} className="mt-4 text-emerald-500 hover:underline">Criar primeiro mapeamento</button>
                  </div>
                ) : (
                  <div className="space-y-4">
                    {Object.entries(groupedMappings).sort(([a], [b]) => a.localeCompare(b)).map(([grupo, items]) => (
                      <div key={grupo} className={`rounded-xl overflow-hidden border ${isDark ? 'border-gray-700 bg-gray-800/30' : 'border-gray-200 bg-gray-50/50'}`}>
                        <button
                          onClick={() => toggleGroupCollapse(grupo)}
                          className={`w-full px-4 py-3 flex items-center gap-3 text-left ${isDark ? 'bg-gray-700/50 hover:bg-gray-700' : 'bg-gray-100 hover:bg-gray-200'} transition-colors`}
                        >
                          {collapsedGroups.has(grupo) 
                            ? <ChevronRight className={`w-4 h-4 ${isDark ? 'text-gray-400' : 'text-gray-500'}`} />
                            : <ChevronDown className={`w-4 h-4 ${isDark ? 'text-gray-400' : 'text-gray-500'}`} />
                          }
                          <Link2 className={`w-5 h-5 ${isDark ? 'text-emerald-400' : 'text-emerald-600'}`} />
                          <span className={`font-semibold ${isDark ? 'text-white' : 'text-gray-900'}`}>{grupo}</span>
                          <span className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                            ({items.length} {items.length === 1 ? 'evento' : 'eventos'})
                          </span>
                        </button>
                        {!collapsedGroups.has(grupo) && (
                          <div className="divide-y divide-gray-200 dark:divide-gray-700">
                            {items.sort((a, b) => b.ano - a.ano || a.fonte.localeCompare(b.fonte)).map(mapping => (
                              <div key={mapping.id} className={`p-4 flex items-center justify-between gap-4 ${!mapping.ativo ? 'opacity-50' : ''}`}>
                                <div className="flex items-center gap-4 flex-1">
                                  <div className="flex flex-col gap-1">
                                    <div className="flex items-center gap-2">
                                      <span className={`px-2 py-0.5 rounded text-xs font-medium ${getFonteColor(mapping.fonte)}`}>{mapping.fonte}</span>
                                      <span className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>ID: {mapping.id_externo}</span>
                                    </div>
                                    <span className={`font-medium ${isDark ? 'text-white' : 'text-gray-900'}`}>{mapping.nome_evento}</span>
                                  </div>
                                </div>
                                <div className="flex items-center gap-4">
                                  <div className={`px-3 py-1 rounded-lg ${isDark ? 'bg-gray-700' : 'bg-gray-100'}`}>
                                    <span className={`text-sm font-mono ${isDark ? 'text-emerald-400' : 'text-emerald-600'}`}>{mapping.sku}</span>
                                  </div>
                                  <div className="flex items-center gap-1">
                                    <Calendar className={`w-4 h-4 ${isDark ? 'text-gray-500' : 'text-gray-400'}`} />
                                    <span className={`text-sm font-medium ${isDark ? 'text-gray-300' : 'text-gray-600'}`}>{mapping.ano}</span>
                                  </div>
                                  <div className="flex items-center gap-1">
                                    <button onClick={() => openEditModal(mapping)} className={`p-2 rounded-lg transition-colors ${isDark ? 'hover:bg-gray-700 text-gray-400 hover:text-white' : 'hover:bg-gray-200 text-gray-500 hover:text-gray-700'}`} title="Editar">
                                      <Edit2 className="w-4 h-4" />
                                    </button>
                                    <button onClick={() => setShowDeleteConfirm(mapping.id)} className={`p-2 rounded-lg transition-colors ${isDark ? 'hover:bg-red-900/30 text-gray-400 hover:text-red-400' : 'hover:bg-red-100 text-gray-500 hover:text-red-600'}`} title="Excluir">
                                      <Trash2 className="w-4 h-4" />
                                    </button>
                                  </div>
                                </div>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </>
          )}

          {activeTab === 'eventos' && (
            <div className="p-6">
              <div className="flex items-center justify-between mb-6">
                <div>
                  <h2 className={`text-lg font-semibold ${isDark ? 'text-white' : 'text-gray-900'}`}>
                    Eventos Externos (Ano Atual e Anterior)
                  </h2>
                  <p className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>
                    Eventos encontrados no Ativo e Magento que ainda n&atilde;o foram mapeados
                  </p>
                </div>
                <button onClick={() => { setEventosLoaded(false); fetchEventosExternos(); }}
                  disabled={loadingEventos}
                  className={`flex items-center gap-2 px-4 py-2 rounded-lg ${isDark ? 'bg-gray-700 hover:bg-gray-600 text-gray-300' : 'bg-gray-100 hover:bg-gray-200 text-gray-600'}`}>
                  <RefreshCw className={`w-4 h-4 ${loadingEventos ? 'animate-spin' : ''}`} />
                  Atualizar
                </button>
              </div>

              {loadingEventos ? (
                <div className="flex flex-col items-center justify-center py-16 gap-4">
                  <RefreshCw className={`w-10 h-10 animate-spin ${isDark ? 'text-emerald-400' : 'text-emerald-600'}`} />
                  <p className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>
                    Buscando eventos nos bancos externos...
                  </p>
                </div>
              ) : eventosError ? (
                <div className={`flex flex-col items-center justify-center gap-3 py-12 ${isDark ? 'text-red-400' : 'text-red-600'}`}>
                  <AlertTriangle className="w-8 h-8" />
                  <span className="text-center">{eventosError}</span>
                  <button onClick={() => { setEventosLoaded(false); fetchEventosExternos(); }} className="underline hover:no-underline text-sm">
                    Tentar novamente
                  </button>
                </div>
              ) : (
                <>
                  {eventosSugeridos.length === 0 && eventosSemMatch.length === 0 ? (
                    <div className={`text-center py-12 ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                      <CheckCircle className="w-12 h-12 mx-auto mb-3 text-emerald-500 opacity-70" />
                      <p className="font-medium">Todos os eventos j&aacute; est&atilde;o mapeados!</p>
                      <p className="text-sm mt-1">N&atilde;o h&aacute; novos eventos para importar.</p>
                    </div>
                  ) : (
                    <>
                      {eventosSugeridos.length > 0 && (
                        <div className="mb-8">
                          <h3 className={`text-md font-semibold mb-3 flex items-center gap-2 ${isDark ? 'text-white' : 'text-gray-900'}`}>
                            <CheckCircle className="w-5 h-5 text-emerald-500" />
                            Com Sugest&atilde;o de Mapeamento ({eventosSugeridos.length})
                          </h3>
                          <div className={`max-h-[400px] overflow-y-auto border rounded-lg ${isDark ? 'border-gray-700' : 'border-gray-200'}`}>
                            <table className="w-full">
                              <thead className={`sticky top-0 z-10 ${isDark ? 'bg-gray-700' : 'bg-gray-50'}`}>
                                <tr>
                                  <th className="p-3 text-left w-10"><Check className="w-4 h-4" /></th>
                                  <th className={`p-3 text-left text-xs font-medium ${isDark ? 'text-gray-300' : 'text-gray-600'}`}>Fonte</th>
                                  <th className={`p-3 text-left text-xs font-medium ${isDark ? 'text-gray-300' : 'text-gray-600'}`}>Evento</th>
                                  <th className={`p-3 text-left text-xs font-medium ${isDark ? 'text-gray-300' : 'text-gray-600'}`}>SKU</th>
                                  <th className={`p-3 text-left text-xs font-medium ${isDark ? 'text-gray-300' : 'text-gray-600'}`}>Grupo</th>
                                  <th className={`p-3 text-left text-xs font-medium ${isDark ? 'text-gray-300' : 'text-gray-600'}`}>Match</th>
                                </tr>
                              </thead>
                              <tbody>
                                {eventosSugeridos.map((evento, index) => (
                                  <tr key={`s-${evento.fonte}-${evento.id_evento}`}
                                    className={`border-t ${isDark ? 'border-gray-700' : 'border-gray-200'} ${evento.selecionado ? '' : 'opacity-40'}`}>
                                    <td className="p-3">
                                      <input type="checkbox" checked={evento.selecionado} onChange={() => toggleEventoSelecionado(index, 'sugerido')}
                                        className="w-4 h-4 rounded border-gray-300 text-emerald-600 focus:ring-emerald-500" />
                                    </td>
                                    <td className="p-3">
                                      <span className={`px-2 py-1 text-xs rounded-full ${getFonteColor(evento.fonte)}`}>{evento.fonte}</span>
                                    </td>
                                    <td className={`p-3 text-sm ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
                                      <div>{evento.nome_evento}</div>
                                      <div className={`text-xs ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>
                                        ID: {evento.id_evento} | Ano: {evento.ano} | Data: {evento.data_evento || 'N/A'}
                                      </div>
                                    </td>
                                    <td className={`p-3 text-sm font-mono ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
                                      {evento.sku_sugerido || evento.sku_original || '-'}
                                    </td>
                                    <td className="p-3">
                                      <select value={evento.evento_grupo_editado || ''}
                                        onChange={(e) => updateEventoGrupoField(index, e.target.value, 'sugerido')}
                                        className={`w-full px-2 py-1 text-sm rounded border ${isDark ? 'bg-gray-700 border-gray-600 text-white' : 'bg-white border-gray-300 text-gray-900'}`}>
                                        <option value="">Selecione...</option>
                                        {allGrupoNames.map(g => <option key={g} value={g}>{g}</option>)}
                                      </select>
                                    </td>
                                    <td className="p-3">
                                      <span className={`px-2 py-1 text-xs rounded-full ${
                                        evento.match_origem === 'nome' 
                                          ? 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400'
                                          : 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400'
                                      }`}>{evento.match_origem || 'auto'}</span>
                                    </td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        </div>
                      )}

                      {eventosSemMatch.length > 0 && (
                        <div className="mb-8">
                          <h3 className={`text-md font-semibold mb-3 flex items-center gap-2 ${isDark ? 'text-white' : 'text-gray-900'}`}>
                            <AlertTriangle className="w-5 h-5 text-yellow-500" />
                            Sem Match Autom&aacute;tico ({eventosSemMatch.length})
                          </h3>
                          <p className={`text-sm mb-3 ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>
                            Selecione e preencha o grupo para importar estes eventos tamb&eacute;m.
                          </p>
                          <div className={`max-h-[300px] overflow-y-auto border rounded-lg ${isDark ? 'border-gray-700' : 'border-gray-200'}`}>
                            <table className="w-full">
                              <thead className={`sticky top-0 z-10 ${isDark ? 'bg-gray-700' : 'bg-gray-50'}`}>
                                <tr>
                                  <th className="p-3 text-left w-10"><Check className="w-4 h-4" /></th>
                                  <th className={`p-3 text-left text-xs font-medium ${isDark ? 'text-gray-300' : 'text-gray-600'}`}>Fonte</th>
                                  <th className={`p-3 text-left text-xs font-medium ${isDark ? 'text-gray-300' : 'text-gray-600'}`}>Evento</th>
                                  <th className={`p-3 text-left text-xs font-medium ${isDark ? 'text-gray-300' : 'text-gray-600'}`}>SKU</th>
                                  <th className={`p-3 text-left text-xs font-medium ${isDark ? 'text-gray-300' : 'text-gray-600'}`}>Grupo</th>
                                </tr>
                              </thead>
                              <tbody>
                                {eventosSemMatch.map((evento, index) => (
                                  <tr key={`m-${evento.fonte}-${evento.id_evento}`}
                                    className={`border-t ${isDark ? 'border-gray-700' : 'border-gray-200'} ${evento.selecionado ? '' : 'opacity-40'}`}>
                                    <td className="p-3">
                                      <input type="checkbox" checked={evento.selecionado} onChange={() => toggleEventoSelecionado(index, 'semMatch')}
                                        className="w-4 h-4 rounded border-gray-300 text-emerald-600 focus:ring-emerald-500" />
                                    </td>
                                    <td className="p-3">
                                      <span className={`px-2 py-1 text-xs rounded-full ${getFonteColor(evento.fonte)}`}>{evento.fonte}</span>
                                    </td>
                                    <td className={`p-3 text-sm ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
                                      <div>{evento.nome_evento}</div>
                                      <div className={`text-xs ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>
                                        ID: {evento.id_evento} | Ano: {evento.ano} | Data: {evento.data_evento || 'N/A'}
                                      </div>
                                    </td>
                                    <td className="p-3">
                                      <input type="text" value={evento.sku_editado || evento.sku_original || ''}
                                        onChange={(e) => setEventosSemMatch(prev => prev.map((ev, i) => i === index ? { ...ev, sku_editado: e.target.value } : ev))}
                                        className={`w-full px-2 py-1 text-sm font-mono rounded border ${isDark ? 'bg-gray-700 border-gray-600 text-white' : 'bg-white border-gray-300 text-gray-900'}`}
                                        placeholder="SKU" />
                                    </td>
                                    <td className="p-3">
                                      <select value={evento.evento_grupo_editado || ''}
                                        onChange={(e) => updateEventoGrupoField(index, e.target.value, 'semMatch')}
                                        className={`w-full px-2 py-1 text-sm rounded border ${isDark ? 'bg-gray-700 border-gray-600 text-white' : 'bg-white border-gray-300 text-gray-900'}`}>
                                        <option value="">Selecione...</option>
                                        {allGrupoNames.map(g => <option key={g} value={g}>{g}</option>)}
                                      </select>
                                    </td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        </div>
                      )}

                      <div className={`flex justify-between items-center pt-4 border-t ${isDark ? 'border-gray-700' : 'border-gray-200'}`}>
                        <div className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>
                          {eventosSugeridos.filter(e => e.selecionado).length + eventosSemMatch.filter(e => e.selecionado).length} eventos selecionados
                        </div>
                        <button onClick={salvarMapeamentosImportados} disabled={savingImport}
                          className="flex items-center gap-2 px-5 py-2 bg-gradient-to-r from-emerald-500 to-teal-500 text-white rounded-lg hover:from-emerald-600 hover:to-teal-600 disabled:opacity-50 transition-all shadow-lg">
                          {savingImport ? <RefreshCw className="w-4 h-4 animate-spin" /> : <CheckCircle className="w-4 h-4" />}
                          Salvar Mapeamentos Selecionados
                        </button>
                      </div>
                    </>
                  )}
                </>
              )}
            </div>
          )}

          {activeTab === 'grupos' && (
            <div className="p-6">
              <div className="flex items-center justify-between mb-6">
                <div>
                  <h2 className={`text-lg font-semibold ${isDark ? 'text-white' : 'text-gray-900'}`}>
                    Grupos de Evento
                  </h2>
                  <p className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>
                    Crie e gerencie os agrupamentos de eventos
                  </p>
                </div>
                <div className="flex gap-2">
                  <button onClick={fetchEventoGrupos} className={`p-2 rounded-lg ${isDark ? 'bg-gray-700 hover:bg-gray-600 text-gray-300' : 'bg-gray-100 hover:bg-gray-200 text-gray-600'}`}>
                    <RefreshCw className={`w-5 h-5 ${loadingGrupos ? 'animate-spin' : ''}`} />
                  </button>
                  <button onClick={openCreateGrupoModal}
                    className="flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-emerald-500 to-teal-500 text-white rounded-lg hover:from-emerald-600 hover:to-teal-600 transition-all shadow-lg text-sm">
                    <Plus className="w-4 h-4" />
                    Novo Grupo
                  </button>
                </div>
              </div>

              {loadingGrupos ? (
                <div className="flex justify-center py-12">
                  <RefreshCw className={`w-8 h-8 animate-spin ${isDark ? 'text-emerald-400' : 'text-emerald-600'}`} />
                </div>
              ) : gruposError ? (
                <div className={`flex items-center justify-center gap-3 py-12 ${isDark ? 'text-red-400' : 'text-red-600'}`}>
                  <AlertTriangle className="w-6 h-6" />
                  <span>{gruposError}</span>
                </div>
              ) : eventoGrupos.length === 0 ? (
                <div className={`text-center py-12 ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                  <FolderOpen className="w-12 h-12 mx-auto mb-3 opacity-50" />
                  <p>Nenhum grupo cadastrado</p>
                  <button onClick={openCreateGrupoModal} className="mt-4 text-emerald-500 hover:underline">Criar primeiro grupo</button>
                </div>
              ) : (
                <div className={`border rounded-xl overflow-hidden ${isDark ? 'border-gray-700' : 'border-gray-200'}`}>
                  <table className="w-full">
                    <thead className={isDark ? 'bg-gray-700/50' : 'bg-gray-50'}>
                      <tr>
                        <th className={`p-4 text-left text-sm font-medium ${isDark ? 'text-gray-300' : 'text-gray-600'}`}>Nome</th>
                        <th className={`p-4 text-left text-sm font-medium ${isDark ? 'text-gray-300' : 'text-gray-600'}`}>Descri&ccedil;&atilde;o</th>
                        <th className={`p-4 text-left text-sm font-medium ${isDark ? 'text-gray-300' : 'text-gray-600'}`}>Status</th>
                        <th className={`p-4 text-right text-sm font-medium ${isDark ? 'text-gray-300' : 'text-gray-600'}`}>A&ccedil;&otilde;es</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
                      {eventoGrupos.map(grupo => (
                        <tr key={grupo.id} className={!grupo.ativo ? 'opacity-50' : ''}>
                          <td className={`p-4 font-medium ${isDark ? 'text-white' : 'text-gray-900'}`}>{grupo.nome}</td>
                          <td className={`p-4 text-sm ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>{grupo.descricao || '-'}</td>
                          <td className="p-4">
                            <span className={`px-2 py-1 text-xs rounded-full ${
                              grupo.ativo 
                                ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-400'
                                : 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-400'
                            }`}>{grupo.ativo ? 'Ativo' : 'Inativo'}</span>
                          </td>
                          <td className="p-4">
                            <div className="flex items-center justify-end gap-1">
                              <button onClick={() => openEditGrupoModal(grupo)} className={`p-2 rounded-lg transition-colors ${isDark ? 'hover:bg-gray-700 text-gray-400 hover:text-white' : 'hover:bg-gray-200 text-gray-500 hover:text-gray-700'}`}>
                                <Edit2 className="w-4 h-4" />
                              </button>
                              <button onClick={() => setShowDeleteGrupoConfirm(grupo.id)} className={`p-2 rounded-lg transition-colors ${isDark ? 'hover:bg-red-900/30 text-gray-400 hover:text-red-400' : 'hover:bg-red-100 text-gray-500 hover:text-red-600'}`}>
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
        </div>
      </div>

      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
          <div className={`w-full max-w-lg rounded-2xl shadow-2xl ${isDark ? 'bg-gray-800' : 'bg-white'}`}>
            <div className={`flex items-center justify-between p-6 border-b ${isDark ? 'border-gray-700' : 'border-gray-200'}`}>
              <h2 className={`text-xl font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>
                {editingMapping ? 'Editar Mapeamento' : 'Novo Mapeamento'}
              </h2>
              <button onClick={() => setShowModal(false)} className={`p-2 rounded-lg ${isDark ? 'hover:bg-gray-700 text-gray-400' : 'hover:bg-gray-100 text-gray-500'}`}>
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
                  <label className={`block text-sm font-medium mb-1 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>Fonte *</label>
                  <select required value={formData.fonte} onChange={(e) => setFormData({ ...formData, fonte: e.target.value as 'ATIVO' | 'MAGENTO' })}
                    className={`w-full px-4 py-2 rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white' : 'bg-white border-gray-300 text-gray-900'} focus:ring-2 focus:ring-emerald-500`}>
                    {fontes.map(f => <option key={f} value={f}>{f}</option>)}
                  </select>
                </div>
                <div>
                  <label className={`block text-sm font-medium mb-1 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>ID Externo *</label>
                  <input type="number" required value={formData.id_externo || ''} onChange={(e) => setFormData({ ...formData, id_externo: parseInt(e.target.value) || 0 })}
                    placeholder="Ex: 40048"
                    className={`w-full px-4 py-2 rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white placeholder-gray-400' : 'bg-white border-gray-300 text-gray-900 placeholder-gray-500'} focus:ring-2 focus:ring-emerald-500`} />
                </div>
              </div>
              <div>
                <label className={`block text-sm font-medium mb-1 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>Nome do Evento *</label>
                <input type="text" required value={formData.nome_evento} onChange={(e) => setFormData({ ...formData, nome_evento: e.target.value })}
                  placeholder="Ex: Corrida do Esporte 2026 - Planalto"
                  className={`w-full px-4 py-2 rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white placeholder-gray-400' : 'bg-white border-gray-300 text-gray-900 placeholder-gray-500'} focus:ring-2 focus:ring-emerald-500`} />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className={`block text-sm font-medium mb-1 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>SKU *</label>
                  <input type="text" required value={formData.sku} onChange={(e) => setFormData({ ...formData, sku: e.target.value.toUpperCase() })}
                    placeholder="Ex: CDE26PL1"
                    className={`w-full px-4 py-2 rounded-lg border font-mono ${isDark ? 'bg-gray-700 border-gray-600 text-white placeholder-gray-400' : 'bg-white border-gray-300 text-gray-900 placeholder-gray-500'} focus:ring-2 focus:ring-emerald-500`} />
                </div>
                <div>
                  <label className={`block text-sm font-medium mb-1 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>Ano *</label>
                  <select required value={formData.ano} onChange={(e) => setFormData({ ...formData, ano: parseInt(e.target.value) })}
                    className={`w-full px-4 py-2 rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white' : 'bg-white border-gray-300 text-gray-900'} focus:ring-2 focus:ring-emerald-500`}>
                    {anos.map(a => <option key={a} value={a}>{a}</option>)}
                  </select>
                </div>
              </div>
              <div>
                <label className={`block text-sm font-medium mb-1 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>Grupo do Evento *</label>
                <select required value={formData.evento_grupo} onChange={(e) => setFormData({ ...formData, evento_grupo: e.target.value })}
                  className={`w-full px-4 py-2 rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white' : 'bg-white border-gray-300 text-gray-900'} focus:ring-2 focus:ring-emerald-500`}>
                  <option value="">Selecione um grupo...</option>
                  {allGrupoNames.map(g => <option key={g} value={g}>{g}</option>)}
                </select>
                <p className={`text-xs mt-1 ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>
                  Cadastre novos grupos na aba "Grupos de Evento"
                </p>
              </div>
              <div className="flex items-center gap-2">
                <input type="checkbox" id="ativo" checked={formData.ativo} onChange={(e) => setFormData({ ...formData, ativo: e.target.checked })}
                  className="w-4 h-4 rounded border-gray-300 text-emerald-500 focus:ring-emerald-500" />
                <label htmlFor="ativo" className={`text-sm ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>Mapeamento ativo</label>
              </div>
              <div className="flex justify-end gap-3 pt-4">
                <button type="button" onClick={() => setShowModal(false)}
                  className={`px-4 py-2 rounded-lg ${isDark ? 'bg-gray-700 text-gray-300 hover:bg-gray-600' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'} transition-colors`}>Cancelar</button>
                <button type="submit" disabled={saving}
                  className="flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-emerald-500 to-teal-500 text-white rounded-lg hover:from-emerald-600 hover:to-teal-600 transition-all disabled:opacity-50">
                  {saving ? <RefreshCw className="w-4 h-4 animate-spin" /> : <CheckCircle className="w-4 h-4" />}
                  {editingMapping ? 'Salvar' : 'Criar'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {showDeleteConfirm !== null && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
          <div className={`w-full max-w-md rounded-2xl shadow-2xl p-6 ${isDark ? 'bg-gray-800' : 'bg-white'}`}>
            <div className="flex items-center gap-3 mb-4">
              <div className="p-3 rounded-full bg-red-100 dark:bg-red-900/30">
                <AlertTriangle className="w-6 h-6 text-red-600 dark:text-red-400" />
              </div>
              <div>
                <h3 className={`font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>Confirmar Exclus&atilde;o</h3>
                <p className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Esta a&ccedil;&atilde;o n&atilde;o pode ser desfeita</p>
              </div>
            </div>
            <div className="flex justify-end gap-3">
              <button onClick={() => setShowDeleteConfirm(null)}
                className={`px-4 py-2 rounded-lg ${isDark ? 'bg-gray-700 text-gray-300 hover:bg-gray-600' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'} transition-colors`}>Cancelar</button>
              <button onClick={() => handleDelete(showDeleteConfirm)}
                className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors">Excluir</button>
            </div>
          </div>
        </div>
      )}

      {showGrupoModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
          <div className={`w-full max-w-md rounded-2xl shadow-2xl ${isDark ? 'bg-gray-800' : 'bg-white'}`}>
            <div className={`flex items-center justify-between p-6 border-b ${isDark ? 'border-gray-700' : 'border-gray-200'}`}>
              <h2 className={`text-xl font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>
                {editingGrupo ? 'Editar Grupo' : 'Novo Grupo'}
              </h2>
              <button onClick={() => setShowGrupoModal(false)} className={`p-2 rounded-lg ${isDark ? 'hover:bg-gray-700 text-gray-400' : 'hover:bg-gray-100 text-gray-500'}`}>
                <X className="w-5 h-5" />
              </button>
            </div>
            <form onSubmit={handleGrupoSubmit} className="p-6 space-y-4">
              {grupoFormError && (
                <div className="flex items-center gap-2 p-3 rounded-lg bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-400">
                  <AlertTriangle className="w-5 h-5 flex-shrink-0" />
                  <span className="text-sm">{grupoFormError}</span>
                </div>
              )}
              <div>
                <label className={`block text-sm font-medium mb-1 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>Nome do Grupo *</label>
                <input type="text" required value={grupoFormData.nome} onChange={(e) => setGrupoFormData({ ...grupoFormData, nome: e.target.value })}
                  placeholder="Ex: CORRIDA_ESPORTE_PLANALTO"
                  className={`w-full px-4 py-2 rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white placeholder-gray-400' : 'bg-white border-gray-300 text-gray-900 placeholder-gray-500'} focus:ring-2 focus:ring-emerald-500`} />
              </div>
              <div>
                <label className={`block text-sm font-medium mb-1 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>Descri&ccedil;&atilde;o</label>
                <textarea value={grupoFormData.descricao} onChange={(e) => setGrupoFormData({ ...grupoFormData, descricao: e.target.value })}
                  placeholder="Descri&ccedil;&atilde;o opcional do grupo"
                  rows={3}
                  className={`w-full px-4 py-2 rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white placeholder-gray-400' : 'bg-white border-gray-300 text-gray-900 placeholder-gray-500'} focus:ring-2 focus:ring-emerald-500`} />
              </div>
              <div className="flex items-center gap-2">
                <input type="checkbox" id="grupo-ativo" checked={grupoFormData.ativo} onChange={(e) => setGrupoFormData({ ...grupoFormData, ativo: e.target.checked })}
                  className="w-4 h-4 rounded border-gray-300 text-emerald-500 focus:ring-emerald-500" />
                <label htmlFor="grupo-ativo" className={`text-sm ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>Grupo ativo</label>
              </div>
              <div className="flex justify-end gap-3 pt-4">
                <button type="button" onClick={() => setShowGrupoModal(false)}
                  className={`px-4 py-2 rounded-lg ${isDark ? 'bg-gray-700 text-gray-300 hover:bg-gray-600' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'} transition-colors`}>Cancelar</button>
                <button type="submit" disabled={savingGrupo}
                  className="flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-emerald-500 to-teal-500 text-white rounded-lg hover:from-emerald-600 hover:to-teal-600 transition-all disabled:opacity-50">
                  {savingGrupo ? <RefreshCw className="w-4 h-4 animate-spin" /> : <CheckCircle className="w-4 h-4" />}
                  {editingGrupo ? 'Salvar' : 'Criar'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {showDeleteGrupoConfirm !== null && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
          <div className={`w-full max-w-md rounded-2xl shadow-2xl p-6 ${isDark ? 'bg-gray-800' : 'bg-white'}`}>
            <div className="flex items-center gap-3 mb-4">
              <div className="p-3 rounded-full bg-red-100 dark:bg-red-900/30">
                <AlertTriangle className="w-6 h-6 text-red-600 dark:text-red-400" />
              </div>
              <div>
                <h3 className={`font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>Excluir Grupo</h3>
                <p className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Esta a&ccedil;&atilde;o n&atilde;o pode ser desfeita</p>
              </div>
            </div>
            <div className="flex justify-end gap-3">
              <button onClick={() => setShowDeleteGrupoConfirm(null)}
                className={`px-4 py-2 rounded-lg ${isDark ? 'bg-gray-700 text-gray-300 hover:bg-gray-600' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'} transition-colors`}>Cancelar</button>
              <button onClick={() => handleDeleteGrupo(showDeleteGrupoConfirm)}
                className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors">Excluir</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default SkuMappings;
