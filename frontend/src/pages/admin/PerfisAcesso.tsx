import React, { useEffect, useState } from 'react';
import { useTheme } from '../../context/ThemeContext';
import api from '../../services/api';
import {
  ShieldCheck, Search, Plus, Edit2, Trash2, RefreshCw,
  AlertTriangle, X, Users, Eye, PenLine, FilePlus, Trash,
  Check, ChevronDown, ChevronUp, Save
} from 'lucide-react';

interface Permissao {
  id?: number;
  perfil_acesso_id?: number;
  modulo: string;
  pode_visualizar: boolean;
  pode_criar: boolean;
  pode_editar: boolean;
  pode_deletar: boolean;
}

interface PerfilAcesso {
  id: number;
  nome: string;
  descricao: string | null;
  is_sistema: boolean;
  ativo: boolean;
  total_usuarios?: number;
  permissoes?: Permissao[];
}

interface ModuloInfo {
  key: string;
  label: string;
}

const PerfisAcesso: React.FC = () => {
  const { isDark } = useTheme();
  const [perfis, setPerfis] = useState<PerfilAcesso[]>([]);
  const [modulos, setModulos] = useState<ModuloInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');

  const [showModal, setShowModal] = useState(false);
  const [editingPerfil, setEditingPerfil] = useState<PerfilAcesso | null>(null);
  const [formNome, setFormNome] = useState('');
  const [formDescricao, setFormDescricao] = useState('');
  const [formPermissoes, setFormPermissoes] = useState<Record<string, Permissao>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const [expandedPerfil, setExpandedPerfil] = useState<number | null>(null);
  const [expandedPermissoes, setExpandedPermissoes] = useState<Permissao[]>([]);
  const [loadingPermissoes, setLoadingPermissoes] = useState(false);

  const fetchData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [perfisRes, modulosRes] = await Promise.all([
        api.get('/perfis-acesso/'),
        api.get('/perfis-acesso/modulos')
      ]);
      setPerfis(perfisRes.data);
      setModulos(modulosRes.data);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Erro ao carregar dados');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const filteredPerfis = perfis.filter(p =>
    !search ||
    p.nome.toLowerCase().includes(search.toLowerCase()) ||
    (p.descricao && p.descricao.toLowerCase().includes(search.toLowerCase()))
  );

  const toggleExpand = async (perfilId: number) => {
    if (expandedPerfil === perfilId) {
      setExpandedPerfil(null);
      setExpandedPermissoes([]);
      return;
    }
    setExpandedPerfil(perfilId);
    setLoadingPermissoes(true);
    try {
      const res = await api.get(`/perfis-acesso/${perfilId}`);
      setExpandedPermissoes(res.data.permissoes || []);
    } catch {
      setExpandedPermissoes([]);
    } finally {
      setLoadingPermissoes(false);
    }
  };

  const initFormPermissoes = (permissoes?: Permissao[]) => {
    const map: Record<string, Permissao> = {};
    modulos.forEach(m => {
      const existing = permissoes?.find(p => p.modulo === m.key);
      map[m.key] = {
        modulo: m.key,
        pode_visualizar: existing?.pode_visualizar || false,
        pode_criar: existing?.pode_criar || false,
        pode_editar: existing?.pode_editar || false,
        pode_deletar: existing?.pode_deletar || false,
      };
    });
    return map;
  };

  const openCreateModal = () => {
    setEditingPerfil(null);
    setFormNome('');
    setFormDescricao('');
    setFormPermissoes(initFormPermissoes());
    setFormError(null);
    setShowModal(true);
  };

  const openEditModal = async (perfil: PerfilAcesso) => {
    setFormError(null);
    try {
      const res = await api.get(`/perfis-acesso/${perfil.id}`);
      setEditingPerfil(res.data);
      setFormNome(res.data.nome);
      setFormDescricao(res.data.descricao || '');
      setFormPermissoes(initFormPermissoes(res.data.permissoes));
      setShowModal(true);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Erro ao carregar perfil');
    }
  };

  const togglePermissao = (modulo: string, campo: keyof Permissao) => {
    setFormPermissoes(prev => {
      const updated = { ...prev };
      const perm = { ...updated[modulo] };
      (perm as any)[campo] = !(perm as any)[campo];
      if (campo !== 'pode_visualizar' && (perm as any)[campo]) {
        perm.pode_visualizar = true;
      }
      if (campo === 'pode_visualizar' && !perm.pode_visualizar) {
        perm.pode_criar = false;
        perm.pode_editar = false;
        perm.pode_deletar = false;
      }
      updated[modulo] = perm;
      return updated;
    });
  };

  const toggleAllModulo = (modulo: string, value: boolean) => {
    setFormPermissoes(prev => {
      const updated = { ...prev };
      updated[modulo] = {
        ...updated[modulo],
        pode_visualizar: value,
        pode_criar: value,
        pode_editar: value,
        pode_deletar: value,
      };
      return updated;
    });
  };

  const toggleAllColumn = (campo: 'pode_visualizar' | 'pode_criar' | 'pode_editar' | 'pode_deletar', value: boolean) => {
    setFormPermissoes(prev => {
      const updated = { ...prev };
      Object.keys(updated).forEach(modulo => {
        updated[modulo] = { ...updated[modulo], [campo]: value };
        if (campo !== 'pode_visualizar' && value) {
          updated[modulo].pode_visualizar = true;
        }
        if (campo === 'pode_visualizar' && !value) {
          updated[modulo].pode_criar = false;
          updated[modulo].pode_editar = false;
          updated[modulo].pode_deletar = false;
        }
      });
      return updated;
    });
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formNome.trim()) {
      setFormError('Nome é obrigatório');
      return;
    }
    setFormError(null);
    setSaving(true);

    const permissoesList = Object.values(formPermissoes).filter(p =>
      p.pode_visualizar || p.pode_criar || p.pode_editar || p.pode_deletar
    );

    try {
      if (editingPerfil) {
        await api.put(`/perfis-acesso/${editingPerfil.id}`, {
          nome: formNome,
          descricao: formDescricao || null,
          permissoes: permissoesList,
        });
      } else {
        await api.post('/perfis-acesso/', {
          nome: formNome,
          descricao: formDescricao || null,
          permissoes: permissoesList,
        });
      }
      setShowModal(false);
      fetchData();
    } catch (err: any) {
      setFormError(err.response?.data?.detail || 'Erro ao salvar perfil');
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (perfil: PerfilAcesso) => {
    if (perfil.is_sistema) {
      setError('Perfis de sistema não podem ser excluídos');
      return;
    }
    if (!confirm(`Deseja realmente desativar o perfil "${perfil.nome}"?`)) return;
    try {
      await api.delete(`/perfis-acesso/${perfil.id}`);
      fetchData();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Erro ao desativar perfil');
    }
  };

  const getModuloLabel = (key: string) => {
    const mod = modulos.find(m => m.key === key);
    return mod?.label || key;
  };

  const getModuloGroup = (key: string): string => {
    if (key.startsWith('admin_')) return 'Admin';
    if (key.startsWith('marketing_')) return 'Marketing';
    return 'Geral';
  };

  const groupedModulos = modulos.reduce<Record<string, ModuloInfo[]>>((acc, m) => {
    const group = getModuloGroup(m.key);
    if (!acc[group]) acc[group] = [];
    acc[group].push(m);
    return acc;
  }, {});

  const isAllColumnChecked = (campo: 'pode_visualizar' | 'pode_criar' | 'pode_editar' | 'pode_deletar') => {
    return modulos.every(m => formPermissoes[m.key]?.[campo]);
  };

  return (
    <div className={`min-h-screen ${isDark ? 'bg-gray-900' : 'bg-gray-50'}`}>
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute top-0 left-1/4 w-96 h-96 bg-gradient-to-r from-indigo-500/10 to-purple-500/10 rounded-full blur-3xl" />
        <div className="absolute bottom-1/4 right-1/4 w-80 h-80 bg-gradient-to-r from-purple-500/10 to-pink-500/10 rounded-full blur-3xl" />
      </div>

      <div className="relative p-6 max-w-[1600px] mx-auto">
        <div className="mb-6">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="p-3 rounded-xl bg-gradient-to-r from-indigo-500 to-purple-500 shadow-lg shadow-indigo-500/25">
                <ShieldCheck className="w-6 h-6 text-white" />
              </div>
              <div>
                <h1 className={`text-2xl font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>
                  Perfis de Acesso
                </h1>
                <p className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>
                  Gerencie os perfis e permissões de acesso ao sistema
                </p>
              </div>
            </div>
            <button
              onClick={openCreateModal}
              className="flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-indigo-500 to-purple-500 text-white rounded-lg hover:opacity-90 transition-opacity shadow-lg shadow-indigo-500/25"
            >
              <Plus className="w-5 h-5" />
              Novo Perfil
            </button>
          </div>
        </div>

        <div className={`p-4 rounded-xl ${isDark ? 'bg-gray-800/80' : 'bg-white'} shadow-lg backdrop-blur-sm border ${isDark ? 'border-gray-700' : 'border-gray-200'} mb-6`}>
          <div className="flex gap-4 items-center">
            <div className="flex-1">
              <div className="relative">
                <Search className={`absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 ${isDark ? 'text-gray-400' : 'text-gray-500'}`} />
                <input
                  type="text"
                  placeholder="Buscar por nome ou descrição..."
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  className={`w-full pl-10 pr-4 py-2 rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white placeholder-gray-400' : 'bg-gray-50 border-gray-300 text-gray-900'} focus:ring-2 focus:ring-indigo-500`}
                />
              </div>
            </div>
            <button
              onClick={fetchData}
              disabled={loading}
              className="flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-indigo-500 to-purple-500 text-white rounded-lg hover:opacity-90 transition-opacity disabled:opacity-50"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
              Atualizar
            </button>
          </div>
        </div>

        {error && (
          <div className="mb-6 p-4 bg-red-500/20 border border-red-500/50 rounded-xl flex items-center gap-3">
            <AlertTriangle className="w-5 h-5 text-red-400" />
            <span className="text-red-400">{error}</span>
            <button onClick={() => setError(null)} className="ml-auto">
              <X className="w-4 h-4 text-red-400" />
            </button>
          </div>
        )}

        <div className="space-y-4">
          {loading ? (
            <div className={`p-12 text-center rounded-xl ${isDark ? 'bg-gray-800/80' : 'bg-white'} shadow-lg border ${isDark ? 'border-gray-700' : 'border-gray-200'}`}>
              <RefreshCw className={`w-8 h-8 mx-auto animate-spin ${isDark ? 'text-gray-400' : 'text-gray-500'}`} />
              <p className={`mt-2 ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Carregando perfis...</p>
            </div>
          ) : filteredPerfis.length === 0 ? (
            <div className={`p-12 text-center rounded-xl ${isDark ? 'bg-gray-800/80' : 'bg-white'} shadow-lg border ${isDark ? 'border-gray-700' : 'border-gray-200'}`}>
              <ShieldCheck className={`w-8 h-8 mx-auto ${isDark ? 'text-gray-500' : 'text-gray-400'}`} />
              <p className={`mt-2 ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Nenhum perfil encontrado</p>
            </div>
          ) : (
            filteredPerfis.map((perfil) => (
              <div key={perfil.id} className={`rounded-xl ${isDark ? 'bg-gray-800/80' : 'bg-white'} shadow-lg backdrop-blur-sm border ${isDark ? 'border-gray-700' : 'border-gray-200'} overflow-hidden`}>
                <div className="flex items-center justify-between p-4">
                  <div className="flex items-center gap-4 flex-1">
                    <div className={`p-2 rounded-lg ${isDark ? 'bg-gray-700' : 'bg-gray-100'}`}>
                      <ShieldCheck className={`w-5 h-5 ${perfil.is_sistema ? 'text-indigo-500' : 'text-gray-400'}`} />
                    </div>
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <h3 className={`font-semibold ${isDark ? 'text-white' : 'text-gray-900'}`}>
                          {perfil.nome}
                        </h3>
                        {perfil.is_sistema && (
                          <span className="px-2 py-0.5 text-xs rounded-full bg-indigo-500/20 text-indigo-400 border border-indigo-500/30">
                            Sistema
                          </span>
                        )}
                      </div>
                      <p className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>
                        {perfil.descricao || 'Sem descrição'}
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      <Users className="w-4 h-4 text-gray-400" />
                      <span className={`text-sm ${isDark ? 'text-gray-300' : 'text-gray-600'}`}>
                        {perfil.total_usuarios || 0} usuário(s)
                      </span>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 ml-4">
                    <button
                      onClick={() => toggleExpand(perfil.id)}
                      className={`p-2 rounded-lg ${isDark ? 'hover:bg-gray-700 text-gray-400 hover:text-white' : 'hover:bg-gray-100 text-gray-500 hover:text-gray-700'} transition-colors`}
                      title="Ver permissões"
                    >
                      {expandedPerfil === perfil.id ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                    </button>
                    <button
                      onClick={() => openEditModal(perfil)}
                      className={`p-2 rounded-lg ${isDark ? 'hover:bg-gray-700 text-gray-400 hover:text-white' : 'hover:bg-gray-100 text-gray-500 hover:text-gray-700'} transition-colors`}
                      title="Editar perfil"
                    >
                      <Edit2 className="w-4 h-4" />
                    </button>
                    {!perfil.is_sistema && (
                      <button
                        onClick={() => handleDelete(perfil)}
                        className={`p-2 rounded-lg ${isDark ? 'hover:bg-red-500/20 text-gray-400 hover:text-red-400' : 'hover:bg-red-100 text-gray-500 hover:text-red-600'} transition-colors`}
                        title="Desativar perfil"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    )}
                  </div>
                </div>

                {expandedPerfil === perfil.id && (
                  <div className={`border-t ${isDark ? 'border-gray-700' : 'border-gray-200'} p-4`}>
                    {loadingPermissoes ? (
                      <div className="text-center py-4">
                        <RefreshCw className={`w-5 h-5 mx-auto animate-spin ${isDark ? 'text-gray-400' : 'text-gray-500'}`} />
                      </div>
                    ) : (
                      <div className="overflow-x-auto">
                        <table className="w-full">
                          <thead>
                            <tr className={isDark ? 'text-gray-400' : 'text-gray-500'}>
                              <th className="text-left text-xs font-medium uppercase px-3 py-2">Módulo</th>
                              <th className="text-center text-xs font-medium uppercase px-3 py-2">
                                <div className="flex items-center justify-center gap-1"><Eye className="w-3 h-3" /> Visualizar</div>
                              </th>
                              <th className="text-center text-xs font-medium uppercase px-3 py-2">
                                <div className="flex items-center justify-center gap-1"><FilePlus className="w-3 h-3" /> Criar</div>
                              </th>
                              <th className="text-center text-xs font-medium uppercase px-3 py-2">
                                <div className="flex items-center justify-center gap-1"><PenLine className="w-3 h-3" /> Editar</div>
                              </th>
                              <th className="text-center text-xs font-medium uppercase px-3 py-2">
                                <div className="flex items-center justify-center gap-1"><Trash className="w-3 h-3" /> Deletar</div>
                              </th>
                            </tr>
                          </thead>
                          <tbody>
                            {modulos.map(m => {
                              const perm = expandedPermissoes.find(p => p.modulo === m.key);
                              return (
                                <tr key={m.key} className={`${isDark ? 'hover:bg-gray-700/30' : 'hover:bg-gray-50'}`}>
                                  <td className={`px-3 py-2 text-sm ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>{m.label}</td>
                                  {(['pode_visualizar', 'pode_criar', 'pode_editar', 'pode_deletar'] as const).map(campo => (
                                    <td key={campo} className="px-3 py-2 text-center">
                                      {perm?.[campo] ? (
                                        <Check className="w-4 h-4 text-green-500 mx-auto" />
                                      ) : (
                                        <X className="w-4 h-4 text-gray-500/30 mx-auto" />
                                      )}
                                    </td>
                                  ))}
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))
          )}
        </div>
      </div>

      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
          <div className={`w-full max-w-4xl mx-4 rounded-xl ${isDark ? 'bg-gray-800' : 'bg-white'} shadow-2xl max-h-[90vh] flex flex-col`}>
            <div className={`flex items-center justify-between p-4 border-b ${isDark ? 'border-gray-700' : 'border-gray-200'}`}>
              <h2 className={`text-lg font-semibold ${isDark ? 'text-white' : 'text-gray-900'}`}>
                {editingPerfil ? 'Editar Perfil de Acesso' : 'Novo Perfil de Acesso'}
              </h2>
              <button
                onClick={() => setShowModal(false)}
                className={`p-2 rounded-lg ${isDark ? 'hover:bg-gray-700 text-gray-400' : 'hover:bg-gray-100 text-gray-500'}`}
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleSubmit} className="flex flex-col flex-1 overflow-hidden">
              <div className="p-4 space-y-4 overflow-y-auto flex-1">
                {formError && (
                  <div className="p-3 bg-red-500/20 border border-red-500/50 rounded-lg flex items-center gap-2 text-red-400 text-sm">
                    <AlertTriangle className="w-4 h-4" />
                    {formError}
                  </div>
                )}

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className={`block text-sm font-medium mb-1 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
                      Nome do Perfil *
                    </label>
                    <input
                      type="text"
                      value={formNome}
                      onChange={(e) => setFormNome(e.target.value)}
                      required
                      className={`w-full px-4 py-2 rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white' : 'bg-gray-50 border-gray-300 text-gray-900'} focus:ring-2 focus:ring-indigo-500`}
                      placeholder="Ex: Gerente de Marketing"
                    />
                  </div>
                  <div>
                    <label className={`block text-sm font-medium mb-1 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
                      Descrição
                    </label>
                    <input
                      type="text"
                      value={formDescricao}
                      onChange={(e) => setFormDescricao(e.target.value)}
                      className={`w-full px-4 py-2 rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white' : 'bg-gray-50 border-gray-300 text-gray-900'} focus:ring-2 focus:ring-indigo-500`}
                      placeholder="Descrição do perfil"
                    />
                  </div>
                </div>

                <div>
                  <h3 className={`text-sm font-semibold mb-3 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
                    Matriz de Permissões
                  </h3>
                  <div className="overflow-x-auto">
                    <table className="w-full">
                      <thead>
                        <tr className={`${isDark ? 'bg-gray-700/50' : 'bg-gray-100'}`}>
                          <th className={`text-left text-xs font-medium uppercase px-3 py-2 ${isDark ? 'text-gray-300' : 'text-gray-600'}`}>
                            Módulo
                          </th>
                          <th className="text-center text-xs font-medium uppercase px-3 py-2">
                            <button type="button" onClick={() => toggleAllColumn('pode_visualizar', !isAllColumnChecked('pode_visualizar'))}
                              className={`flex items-center justify-center gap-1 mx-auto ${isDark ? 'text-gray-300 hover:text-white' : 'text-gray-600 hover:text-gray-900'}`}>
                              <Eye className="w-3 h-3" /> Visualizar
                            </button>
                          </th>
                          <th className="text-center text-xs font-medium uppercase px-3 py-2">
                            <button type="button" onClick={() => toggleAllColumn('pode_criar', !isAllColumnChecked('pode_criar'))}
                              className={`flex items-center justify-center gap-1 mx-auto ${isDark ? 'text-gray-300 hover:text-white' : 'text-gray-600 hover:text-gray-900'}`}>
                              <FilePlus className="w-3 h-3" /> Criar
                            </button>
                          </th>
                          <th className="text-center text-xs font-medium uppercase px-3 py-2">
                            <button type="button" onClick={() => toggleAllColumn('pode_editar', !isAllColumnChecked('pode_editar'))}
                              className={`flex items-center justify-center gap-1 mx-auto ${isDark ? 'text-gray-300 hover:text-white' : 'text-gray-600 hover:text-gray-900'}`}>
                              <PenLine className="w-3 h-3" /> Editar
                            </button>
                          </th>
                          <th className="text-center text-xs font-medium uppercase px-3 py-2">
                            <button type="button" onClick={() => toggleAllColumn('pode_deletar', !isAllColumnChecked('pode_deletar'))}
                              className={`flex items-center justify-center gap-1 mx-auto ${isDark ? 'text-gray-300 hover:text-white' : 'text-gray-600 hover:text-gray-900'}`}>
                              <Trash className="w-3 h-3" /> Deletar
                            </button>
                          </th>
                          <th className={`text-center text-xs font-medium uppercase px-3 py-2 ${isDark ? 'text-gray-300' : 'text-gray-600'}`}>
                            Todos
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                        {Object.entries(groupedModulos).map(([group, mods]) => (
                          <React.Fragment key={group}>
                            <tr>
                              <td colSpan={6} className={`px-3 py-2 text-xs font-bold uppercase ${isDark ? 'text-indigo-400 bg-gray-700/30' : 'text-indigo-600 bg-indigo-50'}`}>
                                {group}
                              </td>
                            </tr>
                            {mods.map(m => {
                              const perm = formPermissoes[m.key];
                              if (!perm) return null;
                              const allChecked = perm.pode_visualizar && perm.pode_criar && perm.pode_editar && perm.pode_deletar;
                              return (
                                <tr key={m.key} className={`${isDark ? 'hover:bg-gray-700/30 border-gray-700/50' : 'hover:bg-gray-50 border-gray-100'} border-b`}>
                                  <td className={`px-3 py-2 text-sm ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
                                    {m.label.replace('Admin - ', '').replace('Marketing - ', '')}
                                  </td>
                                  {(['pode_visualizar', 'pode_criar', 'pode_editar', 'pode_deletar'] as const).map(campo => (
                                    <td key={campo} className="px-3 py-2 text-center">
                                      <button
                                        type="button"
                                        onClick={() => togglePermissao(m.key, campo)}
                                        className={`w-6 h-6 rounded border-2 flex items-center justify-center transition-colors mx-auto ${
                                          (perm as any)[campo]
                                            ? 'bg-indigo-500 border-indigo-500 text-white'
                                            : isDark ? 'border-gray-600 hover:border-gray-500' : 'border-gray-300 hover:border-gray-400'
                                        }`}
                                      >
                                        {(perm as any)[campo] && <Check className="w-4 h-4" />}
                                      </button>
                                    </td>
                                  ))}
                                  <td className="px-3 py-2 text-center">
                                    <button
                                      type="button"
                                      onClick={() => toggleAllModulo(m.key, !allChecked)}
                                      className={`w-6 h-6 rounded border-2 flex items-center justify-center transition-colors mx-auto ${
                                        allChecked
                                          ? 'bg-green-500 border-green-500 text-white'
                                          : isDark ? 'border-gray-600 hover:border-gray-500' : 'border-gray-300 hover:border-gray-400'
                                      }`}
                                    >
                                      {allChecked && <Check className="w-4 h-4" />}
                                    </button>
                                  </td>
                                </tr>
                              );
                            })}
                          </React.Fragment>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>

              <div className={`flex items-center justify-end gap-3 p-4 border-t ${isDark ? 'border-gray-700' : 'border-gray-200'}`}>
                <button
                  type="button"
                  onClick={() => setShowModal(false)}
                  className={`px-4 py-2 rounded-lg ${isDark ? 'bg-gray-700 text-gray-300 hover:bg-gray-600' : 'bg-gray-200 text-gray-700 hover:bg-gray-300'} transition-colors`}
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  disabled={saving}
                  className="flex items-center gap-2 px-6 py-2 bg-gradient-to-r from-indigo-500 to-purple-500 text-white rounded-lg hover:opacity-90 transition-opacity disabled:opacity-50"
                >
                  <Save className="w-4 h-4" />
                  {saving ? 'Salvando...' : 'Salvar Perfil'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};

export default PerfisAcesso;
