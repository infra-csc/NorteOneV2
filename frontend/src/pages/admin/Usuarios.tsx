import React, { useEffect, useState } from 'react';
import { useTheme } from '../../context/ThemeContext';
import api from '../../services/api';
import { 
  Users, Search, Plus, Edit2, Trash2, RefreshCw, 
  AlertTriangle, CheckCircle, XCircle, X, Building2, ShieldCheck,
  Upload, Download, FileSpreadsheet
} from 'lucide-react';

interface ImportSkipped {
  linha: number;
  email: string;
  motivo: string;
}

interface ImportResult {
  total: number;
  criados: number;
  pulados: ImportSkipped[];
}

interface CentroCusto {
  id: number;
  nome: string;
}

interface PerfilAcessoOption {
  id: number;
  nome: string;
  descricao: string | null;
}

interface Usuario {
  id: number;
  email: string;
  nome: string;
  perfil_acesso_id: number | null;
  perfil_acesso_nome: string | null;
  is_admin: boolean;
  centro_custo_id: number | null;
  ativo: boolean;
  recebe_alertas_corte: boolean;
  recebe_insights_nori: boolean;
}

interface UsuarioForm {
  email: string;
  nome: string;
  password: string;
  perfil_acesso_id: number | null;
  centro_custo_id: number | null;
  ativo: boolean;
  recebe_alertas_corte: boolean;
  recebe_insights_nori: boolean;
}

const Usuarios: React.FC = () => {
  const { isDark } = useTheme();
  const [usuarios, setUsuarios] = useState<Usuario[]>([]);
  const [centrosCusto, setCentrosCusto] = useState<CentroCusto[]>([]);
  const [perfisAcesso, setPerfisAcesso] = useState<PerfilAcessoOption[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [filterPerfilAcesso, setFilterPerfilAcesso] = useState<string>('todos');
  const [filterCentroCusto, setFilterCentroCusto] = useState<string>('todos');
  const [filterStatus, setFilterStatus] = useState<string>('ativos');
  
  const [showModal, setShowModal] = useState(false);
  const [editingUser, setEditingUser] = useState<Usuario | null>(null);
  const [formData, setFormData] = useState<UsuarioForm>({
    email: '',
    nome: '',
    password: '',
    perfil_acesso_id: null,
    centro_custo_id: null,
    ativo: true,
    recebe_alertas_corte: false,
    recebe_insights_nori: false
  });
  const [formError, setFormError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const [showImportModal, setShowImportModal] = useState(false);
  const [importFile, setImportFile] = useState<File | null>(null);
  const [importPassword, setImportPassword] = useState('');
  const [importError, setImportError] = useState<string | null>(null);
  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState<ImportResult | null>(null);
  const [dragOver, setDragOver] = useState(false);

  const fetchData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [usersRes, centrosRes, perfisRes] = await Promise.all([
        api.get('/users/'),
        api.get('/centros-custo/'),
        api.get('/perfis-acesso/')
      ]);
      setUsuarios(usersRes.data);
      setCentrosCusto(centrosRes.data);
      setPerfisAcesso(perfisRes.data);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Erro ao carregar dados');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const getCentroCustoNome = (id: number | null) => {
    if (!id) return '-';
    const centro = centrosCusto.find(c => c.id === id);
    return centro?.nome || '-';
  };

  const filteredUsuarios = usuarios.filter(user => {
    const matchesSearch = !search || 
      user.nome.toLowerCase().includes(search.toLowerCase()) ||
      user.email.toLowerCase().includes(search.toLowerCase());
    const matchesPerfilAcesso = filterPerfilAcesso === 'todos' || 
      (filterPerfilAcesso === 'sem_perfil' ? !user.perfil_acesso_id : user.perfil_acesso_id === parseInt(filterPerfilAcesso));
    const matchesCentro = filterCentroCusto === 'todos' || 
      (filterCentroCusto === 'sem_centro' ? !user.centro_custo_id : user.centro_custo_id === parseInt(filterCentroCusto));
    const matchesStatus = filterStatus === 'todos' || 
      (filterStatus === 'ativos' ? user.ativo : !user.ativo);
    return matchesSearch && matchesPerfilAcesso && matchesCentro && matchesStatus;
  });

  const getPerfilAcessoNome = (id: number | null) => {
    if (!id) return '-';
    const perfil = perfisAcesso.find(p => p.id === id);
    return perfil?.nome || '-';
  };

  const openCreateModal = () => {
    setEditingUser(null);
    setFormData({
      email: '',
      nome: '',
      password: '',
      perfil_acesso_id: null,
      centro_custo_id: null,
      ativo: true,
      recebe_alertas_corte: false,
      recebe_insights_nori: false
    });
    setFormError(null);
    setShowModal(true);
  };

  const openEditModal = (user: Usuario) => {
    setEditingUser(user);
    setFormData({
      email: user.email,
      nome: user.nome,
      password: '',
      perfil_acesso_id: user.perfil_acesso_id,
      centro_custo_id: user.centro_custo_id,
      ativo: user.ativo,
      recebe_alertas_corte: user.recebe_alertas_corte,
      recebe_insights_nori: user.recebe_insights_nori
    });
    setFormError(null);
    setShowModal(true);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);
    setSaving(true);

    try {
      if (editingUser) {
        const updateData: any = {
          nome: formData.nome,
          perfil_acesso_id: formData.perfil_acesso_id,
          centro_custo_id: formData.centro_custo_id,
          ativo: formData.ativo,
          recebe_alertas_corte: formData.recebe_alertas_corte,
          recebe_insights_nori: formData.recebe_insights_nori
        };
        if (formData.password) {
          updateData.password = formData.password;
        }
        await api.put(`/users/${editingUser.id}`, updateData);
      } else {
        if (!formData.password) {
          setFormError('Senha é obrigatória para novos usuários');
          setSaving(false);
          return;
        }
        await api.post('/users/', formData);
      }
      setShowModal(false);
      fetchData();
    } catch (err: any) {
      setFormError(err.response?.data?.detail || 'Erro ao salvar usuário');
    } finally {
      setSaving(false);
    }
  };

  const openImportModal = () => {
    setImportFile(null);
    setImportPassword('');
    setImportError(null);
    setImportResult(null);
    setDragOver(false);
    setShowImportModal(true);
  };

  const handleDownloadTemplate = async () => {
    try {
      const res = await api.get('/users/bulk-import/template', { responseType: 'blob' });
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', 'modelo_importacao_usuarios.csv');
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch {
      setImportError('Não foi possível baixar o modelo.');
    }
  };

  const handleDownloadPulados = () => {
    if (!importResult || importResult.pulados.length === 0) return;
    const escapeCsv = (value: string | number) => {
      const str = String(value ?? '');
      if (/[",\n;]/.test(str)) {
        return `"${str.replace(/"/g, '""')}"`;
      }
      return str;
    };
    const header = ['linha', 'email', 'motivo'];
    const rows = importResult.pulados.map((p) =>
      [escapeCsv(p.linha), escapeCsv(p.email), escapeCsv(p.motivo)].join(',')
    );
    const csv = '\ufeff' + [header.join(','), ...rows].join('\r\n');
    const url = window.URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8;' }));
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', 'linhas_puladas_importacao.csv');
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.URL.revokeObjectURL(url);
  };

  const validateImportFile = (file: File): boolean => {
    const name = file.name.toLowerCase();
    if (!name.endsWith('.csv') && !name.endsWith('.xlsx') && !name.endsWith('.xls')) {
      setImportError('Formato não suportado. Use um arquivo .csv ou .xlsx');
      return false;
    }
    return true;
  };

  const handleImportFileSelect = (file: File | null) => {
    setImportError(null);
    setImportResult(null);
    if (!file) {
      setImportFile(null);
      return;
    }
    if (validateImportFile(file)) {
      setImportFile(file);
    } else {
      setImportFile(null);
    }
  };

  const handleImportSubmit = async () => {
    setImportError(null);
    if (!importFile) {
      setImportError('Selecione um arquivo .csv ou .xlsx');
      return;
    }
    if (!importPassword || importPassword.length < 6) {
      setImportError('A senha padrão deve ter pelo menos 6 caracteres');
      return;
    }
    setImporting(true);
    setImportResult(null);
    try {
      const fd = new FormData();
      fd.append('file', importFile);
      fd.append('senha_padrao', importPassword);
      const res = await api.post('/users/bulk-import', fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setImportResult(res.data);
      if (res.data.criados > 0) {
        fetchData();
      }
    } catch (err: any) {
      setImportError(err.response?.data?.detail || 'Erro ao importar usuários');
    } finally {
      setImporting(false);
    }
  };

  const handleToggleStatus = async (user: Usuario) => {
    try {
      await api.put(`/users/${user.id}`, { ativo: !user.ativo });
      fetchData();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Erro ao atualizar status');
    }
  };

  const handleDelete = async (user: Usuario) => {
    if (!confirm(`Deseja realmente desativar o usuário "${user.nome}"?`)) return;
    try {
      await api.delete(`/users/${user.id}`);
      fetchData();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Erro ao desativar usuário');
    }
  };

  const getPerfilBadgeColor = (isAdmin: boolean) => {
    return isAdmin 
      ? 'bg-red-500/20 text-red-400 border-red-500/30'
      : 'bg-indigo-500/20 text-indigo-400 border-indigo-500/30';
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
                <Users className="w-6 h-6 text-white" />
              </div>
              <div>
                <h1 className={`text-2xl font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>
                  Gestão de Usuários
                </h1>
                <p className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>
                  Gerencie os usuários do sistema com controle de hierarquia e centro de custo
                </p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <button
                onClick={openImportModal}
                className={`flex items-center gap-2 px-4 py-2 rounded-lg transition-colors border ${isDark ? 'bg-gray-800 border-gray-700 text-gray-200 hover:bg-gray-700' : 'bg-white border-gray-300 text-gray-700 hover:bg-gray-50'} shadow-sm`}
              >
                <Upload className="w-5 h-5" />
                Importar em lote
              </button>
              <button
                onClick={openCreateModal}
                className="flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-indigo-500 to-purple-500 text-white rounded-lg hover:opacity-90 transition-opacity shadow-lg shadow-indigo-500/25"
              >
                <Plus className="w-5 h-5" />
                Novo Usuário
              </button>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-4 gap-4 mb-6">
          <div className={`p-4 rounded-xl ${isDark ? 'bg-gray-800/80' : 'bg-white'} shadow-lg backdrop-blur-sm border ${isDark ? 'border-gray-700' : 'border-gray-200'}`}>
            <div className="flex items-center justify-between">
              <span className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>Total de Usuários</span>
              <Users className="w-5 h-5 text-indigo-500" />
            </div>
            <p className={`text-2xl font-bold mt-1 ${isDark ? 'text-white' : 'text-gray-900'}`}>
              {usuarios.length}
            </p>
          </div>
          <div className={`p-4 rounded-xl ${isDark ? 'bg-gray-800/80' : 'bg-white'} shadow-lg backdrop-blur-sm border ${isDark ? 'border-gray-700' : 'border-gray-200'}`}>
            <div className="flex items-center justify-between">
              <span className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>Ativos</span>
              <CheckCircle className="w-5 h-5 text-green-500" />
            </div>
            <p className={`text-2xl font-bold mt-1 ${isDark ? 'text-white' : 'text-gray-900'}`}>
              {usuarios.filter(u => u.ativo).length}
            </p>
          </div>
          <div className={`p-4 rounded-xl ${isDark ? 'bg-gray-800/80' : 'bg-white'} shadow-lg backdrop-blur-sm border ${isDark ? 'border-gray-700' : 'border-gray-200'}`}>
            <div className="flex items-center justify-between">
              <span className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>Administradores</span>
              <ShieldCheck className="w-5 h-5 text-red-500" />
            </div>
            <p className={`text-2xl font-bold mt-1 ${isDark ? 'text-white' : 'text-gray-900'}`}>
              {usuarios.filter(u => u.is_admin).length}
            </p>
          </div>
          <div className={`p-4 rounded-xl ${isDark ? 'bg-gray-800/80' : 'bg-white'} shadow-lg backdrop-blur-sm border ${isDark ? 'border-gray-700' : 'border-gray-200'}`}>
            <div className="flex items-center justify-between">
              <span className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>Centros de Custo</span>
              <Building2 className="w-5 h-5 text-blue-500" />
            </div>
            <p className={`text-2xl font-bold mt-1 ${isDark ? 'text-white' : 'text-gray-900'}`}>
              {centrosCusto.length}
            </p>
          </div>
        </div>

        <div className={`p-4 rounded-xl ${isDark ? 'bg-gray-800/80' : 'bg-white'} shadow-lg backdrop-blur-sm border ${isDark ? 'border-gray-700' : 'border-gray-200'} mb-6`}>
          <div className="flex flex-wrap gap-4 items-center">
            <div className="flex-1 min-w-[250px]">
              <div className="relative">
                <Search className={`absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 ${isDark ? 'text-gray-400' : 'text-gray-500'}`} />
                <input
                  type="text"
                  placeholder="Buscar por nome ou email..."
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  className={`w-full pl-10 pr-4 py-2 rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white placeholder-gray-400' : 'bg-gray-50 border-gray-300 text-gray-900'} focus:ring-2 focus:ring-indigo-500`}
                />
              </div>
            </div>
            <select
              value={filterPerfilAcesso}
              onChange={(e) => setFilterPerfilAcesso(e.target.value)}
              className={`px-4 py-2 rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white' : 'bg-gray-50 border-gray-300 text-gray-900'} focus:ring-2 focus:ring-indigo-500`}
            >
              <option value="todos">Todos os perfis</option>
              <option value="sem_perfil">Sem perfil de acesso</option>
              {perfisAcesso.map(p => (
                <option key={p.id} value={p.id}>{p.nome}</option>
              ))}
            </select>
            <select
              value={filterCentroCusto}
              onChange={(e) => setFilterCentroCusto(e.target.value)}
              className={`px-4 py-2 rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white' : 'bg-gray-50 border-gray-300 text-gray-900'} focus:ring-2 focus:ring-indigo-500`}
            >
              <option value="todos">Todos os centros</option>
              <option value="sem_centro">Sem centro de custo</option>
              {centrosCusto.map(c => (
                <option key={c.id} value={c.id}>{c.nome}</option>
              ))}
            </select>
            <select
              value={filterStatus}
              onChange={(e) => setFilterStatus(e.target.value)}
              className={`px-4 py-2 rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white' : 'bg-gray-50 border-gray-300 text-gray-900'} focus:ring-2 focus:ring-indigo-500`}
            >
              <option value="ativos">Apenas ativos</option>
              <option value="inativos">Apenas inativos</option>
              <option value="todos">Todos</option>
            </select>
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

        <div className={`rounded-xl ${isDark ? 'bg-gray-800/80' : 'bg-white'} shadow-lg backdrop-blur-sm border ${isDark ? 'border-gray-700' : 'border-gray-200'} overflow-hidden`}>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className={isDark ? 'bg-gray-700/50' : 'bg-gray-100'}>
                <tr>
                  <th className={`px-6 py-3 text-left text-xs font-medium uppercase tracking-wider ${isDark ? 'text-gray-300' : 'text-gray-600'}`}>
                    Usuário
                  </th>
                  <th className={`px-6 py-3 text-left text-xs font-medium uppercase tracking-wider ${isDark ? 'text-gray-300' : 'text-gray-600'}`}>
                    Email
                  </th>
                  <th className={`px-6 py-3 text-left text-xs font-medium uppercase tracking-wider ${isDark ? 'text-gray-300' : 'text-gray-600'}`}>
                    Perfil de Acesso
                  </th>
                  <th className={`px-6 py-3 text-left text-xs font-medium uppercase tracking-wider ${isDark ? 'text-gray-300' : 'text-gray-600'}`}>
                    Centro de Custo
                  </th>
                  <th className={`px-6 py-3 text-center text-xs font-medium uppercase tracking-wider ${isDark ? 'text-gray-300' : 'text-gray-600'}`}>
                    Status
                  </th>
                  <th className={`px-6 py-3 text-center text-xs font-medium uppercase tracking-wider ${isDark ? 'text-gray-300' : 'text-gray-600'}`}>
                    Ações
                  </th>
                </tr>
              </thead>
              <tbody className={`divide-y ${isDark ? 'divide-gray-700' : 'divide-gray-200'}`}>
                {loading ? (
                  <tr>
                    <td colSpan={6} className="px-6 py-12 text-center">
                      <RefreshCw className={`w-8 h-8 mx-auto animate-spin ${isDark ? 'text-gray-400' : 'text-gray-500'}`} />
                      <p className={`mt-2 ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Carregando usuários...</p>
                    </td>
                  </tr>
                ) : filteredUsuarios.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="px-6 py-12 text-center">
                      <Users className={`w-8 h-8 mx-auto ${isDark ? 'text-gray-500' : 'text-gray-400'}`} />
                      <p className={`mt-2 ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Nenhum usuário encontrado</p>
                    </td>
                  </tr>
                ) : (
                  filteredUsuarios.map((user) => (
                    <tr 
                      key={user.id}
                      className={`${isDark ? 'hover:bg-gray-700/50' : 'hover:bg-gray-50'} transition-colors`}
                    >
                      <td className={`px-6 py-4 ${isDark ? 'text-white' : 'text-gray-900'}`}>
                        <div className="flex items-center gap-3">
                          <div className={`w-10 h-10 rounded-full flex items-center justify-center ${isDark ? 'bg-gray-700' : 'bg-gray-200'}`}>
                            <span className="font-medium">
                              {user.nome.split(' ').map(n => n[0]).join('').slice(0, 2).toUpperCase()}
                            </span>
                          </div>
                          <span className="font-medium">{user.nome}</span>
                        </div>
                      </td>
                      <td className={`px-6 py-4 ${isDark ? 'text-gray-300' : 'text-gray-600'}`}>
                        {user.email}
                      </td>
                      <td className={`px-6 py-4 ${isDark ? 'text-gray-300' : 'text-gray-600'}`}>
                        <div className="flex items-center gap-2">
                          <ShieldCheck className="w-4 h-4 text-indigo-400" />
                          <span className={`px-3 py-1 rounded-full text-xs font-medium border ${getPerfilBadgeColor(user.is_admin)}`}>
                            {user.perfil_acesso_nome || 'Sem perfil'}
                          </span>
                        </div>
                      </td>
                      <td className={`px-6 py-4 ${isDark ? 'text-gray-300' : 'text-gray-600'}`}>
                        <div className="flex items-center gap-2">
                          <Building2 className="w-4 h-4 text-gray-400" />
                          {getCentroCustoNome(user.centro_custo_id)}
                        </div>
                      </td>
                      <td className="px-6 py-4 text-center">
                        <button
                          onClick={() => handleToggleStatus(user)}
                          className={`inline-flex items-center gap-1 px-3 py-1 rounded-full text-xs font-medium ${
                            user.ativo
                              ? 'bg-green-500/20 text-green-400 hover:bg-green-500/30'
                              : 'bg-red-500/20 text-red-400 hover:bg-red-500/30'
                          } transition-colors`}
                        >
                          {user.ativo ? (
                            <>
                              <CheckCircle className="w-3 h-3" />
                              Ativo
                            </>
                          ) : (
                            <>
                              <XCircle className="w-3 h-3" />
                              Inativo
                            </>
                          )}
                        </button>
                      </td>
                      <td className="px-6 py-4">
                        <div className="flex items-center justify-center gap-2">
                          <button
                            onClick={() => openEditModal(user)}
                            className={`p-2 rounded-lg ${isDark ? 'hover:bg-gray-700 text-gray-400 hover:text-white' : 'hover:bg-gray-100 text-gray-500 hover:text-gray-700'} transition-colors`}
                            title="Editar usuário"
                          >
                            <Edit2 className="w-4 h-4" />
                          </button>
                          <button
                            onClick={() => handleDelete(user)}
                            className={`p-2 rounded-lg ${isDark ? 'hover:bg-red-500/20 text-gray-400 hover:text-red-400' : 'hover:bg-red-100 text-gray-500 hover:text-red-600'} transition-colors`}
                            title="Desativar usuário"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
          <div className={`w-full max-w-lg mx-4 rounded-xl ${isDark ? 'bg-gray-800' : 'bg-white'} shadow-2xl`}>
            <div className={`flex items-center justify-between p-4 border-b ${isDark ? 'border-gray-700' : 'border-gray-200'}`}>
              <h2 className={`text-lg font-semibold ${isDark ? 'text-white' : 'text-gray-900'}`}>
                {editingUser ? 'Editar Usuário' : 'Novo Usuário'}
              </h2>
              <button
                onClick={() => setShowModal(false)}
                className={`p-2 rounded-lg ${isDark ? 'hover:bg-gray-700 text-gray-400' : 'hover:bg-gray-100 text-gray-500'}`}
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleSubmit} className="p-4 space-y-4">
              {formError && (
                <div className="p-3 bg-red-500/20 border border-red-500/50 rounded-lg flex items-center gap-2 text-red-400 text-sm">
                  <AlertTriangle className="w-4 h-4" />
                  {formError}
                </div>
              )}

              <div>
                <label className={`block text-sm font-medium mb-1 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
                  Nome *
                </label>
                <input
                  type="text"
                  value={formData.nome}
                  onChange={(e) => setFormData({ ...formData, nome: e.target.value })}
                  required
                  className={`w-full px-4 py-2 rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white' : 'bg-gray-50 border-gray-300 text-gray-900'} focus:ring-2 focus:ring-indigo-500`}
                  placeholder="Nome completo"
                />
              </div>

              <div>
                <label className={`block text-sm font-medium mb-1 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
                  Email *
                </label>
                <input
                  type="email"
                  value={formData.email}
                  onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                  required
                  disabled={!!editingUser}
                  className={`w-full px-4 py-2 rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white disabled:opacity-50' : 'bg-gray-50 border-gray-300 text-gray-900 disabled:opacity-50'} focus:ring-2 focus:ring-indigo-500`}
                  placeholder="email@exemplo.com"
                />
              </div>

              <div>
                <label className={`block text-sm font-medium mb-1 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
                  {editingUser ? 'Nova Senha (deixe em branco para manter a atual)' : 'Senha *'}
                </label>
                <input
                  type="password"
                  value={formData.password}
                  onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                  required={!editingUser}
                  className={`w-full px-4 py-2 rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white' : 'bg-gray-50 border-gray-300 text-gray-900'} focus:ring-2 focus:ring-indigo-500`}
                  placeholder={editingUser ? 'Digite para redefinir a senha' : 'Senha de acesso'}
                />
                {editingUser && (
                  <p className={`text-xs mt-1 ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                    Preencha apenas se desejar alterar a senha do usuário
                  </p>
                )}
              </div>

              <div>
                <label className={`block text-sm font-medium mb-1 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
                  Perfil de Acesso *
                </label>
                <select
                  value={formData.perfil_acesso_id || ''}
                  onChange={(e) => setFormData({ ...formData, perfil_acesso_id: e.target.value ? parseInt(e.target.value) : null })}
                  required
                  className={`w-full px-4 py-2 rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white' : 'bg-gray-50 border-gray-300 text-gray-900'} focus:ring-2 focus:ring-indigo-500`}
                >
                  <option value="">Selecione um perfil de acesso</option>
                  {perfisAcesso.map(p => (
                    <option key={p.id} value={p.id}>{p.nome}</option>
                  ))}
                </select>
                <p className={`text-xs mt-1 ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                  Define quais telas e ações o usuário pode acessar
                </p>
              </div>

              <div>
                <label className={`block text-sm font-medium mb-1 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
                  Centro de Custo
                </label>
                <select
                  value={formData.centro_custo_id || ''}
                  onChange={(e) => setFormData({ ...formData, centro_custo_id: e.target.value ? parseInt(e.target.value) : null })}
                  className={`w-full px-4 py-2 rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white' : 'bg-gray-50 border-gray-300 text-gray-900'} focus:ring-2 focus:ring-indigo-500`}
                >
                  <option value="">Nenhum centro de custo</option>
                  {centrosCusto.map(c => (
                    <option key={c.id} value={c.id}>{c.nome}</option>
                  ))}
                </select>
                <p className={`text-xs mt-1 ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                  Vincula o usuário a um centro de custo específico
                </p>
              </div>

              {editingUser && (
                <div className={`p-4 rounded-lg ${isDark ? 'bg-gray-700/50' : 'bg-gray-100'}`}>
                  <div className="flex items-center justify-between">
                    <div>
                      <label className={`block text-sm font-medium ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
                        Status do Usuário
                      </label>
                      <p className={`text-xs ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                        Usuários inativos não podem acessar o sistema
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={() => setFormData({ ...formData, ativo: !formData.ativo })}
                      className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                        formData.ativo ? 'bg-green-500' : 'bg-gray-400'
                      }`}
                    >
                      <span
                        className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                          formData.ativo ? 'translate-x-6' : 'translate-x-1'
                        }`}
                      />
                    </button>
                  </div>
                  <div className={`mt-2 flex items-center gap-2 text-sm ${formData.ativo ? 'text-green-400' : 'text-red-400'}`}>
                    {formData.ativo ? (
                      <>
                        <CheckCircle className="w-4 h-4" />
                        Usuário ativo - pode acessar o sistema
                      </>
                    ) : (
                      <>
                        <XCircle className="w-4 h-4" />
                        Usuário inativo - sem acesso ao sistema
                      </>
                    )}
                  </div>
                </div>
              )}

              <div className={`p-4 rounded-lg border ${isDark ? 'bg-amber-950/20 border-amber-800/40' : 'bg-amber-50 border-amber-200'}`}>
                <div className="flex items-center justify-between">
                  <div>
                    <label className={`block text-sm font-medium ${isDark ? 'text-amber-300' : 'text-amber-900'}`}>
                      Alertas de Ponto de Corte
                    </label>
                    <p className={`text-xs mt-0.5 ${isDark ? 'text-amber-400/70' : 'text-amber-700'}`}>
                      Exibe no Nori os eventos que estão no D-ponto de corte
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => setFormData({ ...formData, recebe_alertas_corte: !formData.recebe_alertas_corte })}
                    className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                      formData.recebe_alertas_corte ? 'bg-amber-500' : 'bg-gray-400'
                    }`}
                  >
                    <span
                      className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                        formData.recebe_alertas_corte ? 'translate-x-6' : 'translate-x-1'
                      }`}
                    />
                  </button>
                </div>
              </div>

              <div className={`p-4 rounded-lg border ${isDark ? 'bg-indigo-950/20 border-indigo-800/40' : 'bg-indigo-50 border-indigo-200'}`}>
                <div className="flex items-center justify-between">
                  <div>
                    <label className={`block text-sm font-medium ${isDark ? 'text-indigo-300' : 'text-indigo-900'}`}>
                      Insights Proativos (Nori)
                    </label>
                    <p className={`text-xs mt-0.5 ${isDark ? 'text-indigo-400/70' : 'text-indigo-700'}`}>
                      Exibe a aba de insights gerados por IA no Nori
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => setFormData({ ...formData, recebe_insights_nori: !formData.recebe_insights_nori })}
                    className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                      formData.recebe_insights_nori ? 'bg-indigo-500' : 'bg-gray-400'
                    }`}
                  >
                    <span
                      className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                        formData.recebe_insights_nori ? 'translate-x-6' : 'translate-x-1'
                      }`}
                    />
                  </button>
                </div>
              </div>

              <div className={`flex justify-end gap-3 pt-4 border-t ${isDark ? 'border-gray-700' : 'border-gray-200'}`}>
                <button
                  type="button"
                  onClick={() => setShowModal(false)}
                  className={`px-4 py-2 rounded-lg ${isDark ? 'bg-gray-700 text-gray-300 hover:bg-gray-600' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'} transition-colors`}
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  disabled={saving}
                  className="px-4 py-2 bg-gradient-to-r from-indigo-500 to-purple-500 text-white rounded-lg hover:opacity-90 transition-opacity disabled:opacity-50 flex items-center gap-2"
                >
                  {saving && <RefreshCw className="w-4 h-4 animate-spin" />}
                  {editingUser ? 'Salvar Alterações' : 'Criar Usuário'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {showImportModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
          <div className={`w-full max-w-lg mx-4 rounded-xl ${isDark ? 'bg-gray-800' : 'bg-white'} shadow-2xl max-h-[90vh] flex flex-col`}>
            <div className={`flex items-center justify-between p-4 border-b ${isDark ? 'border-gray-700' : 'border-gray-200'}`}>
              <div className="flex items-center gap-2">
                <FileSpreadsheet className="w-5 h-5 text-indigo-400" />
                <h2 className={`text-lg font-semibold ${isDark ? 'text-white' : 'text-gray-900'}`}>
                  Importar Usuários em Lote
                </h2>
              </div>
              <button
                onClick={() => setShowImportModal(false)}
                className={`p-2 rounded-lg ${isDark ? 'hover:bg-gray-700 text-gray-400' : 'hover:bg-gray-100 text-gray-500'}`}
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="p-4 space-y-4 overflow-y-auto">
              {importError && (
                <div className="p-3 bg-red-500/20 border border-red-500/50 rounded-lg flex items-center gap-2 text-red-400 text-sm">
                  <AlertTriangle className="w-4 h-4 flex-shrink-0" />
                  {importError}
                </div>
              )}

              {importResult ? (
                <div className="space-y-4">
                  <div className="grid grid-cols-3 gap-3">
                    <div className={`p-3 rounded-lg text-center ${isDark ? 'bg-gray-700/50' : 'bg-gray-100'}`}>
                      <p className={`text-2xl font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>{importResult.total}</p>
                      <p className={`text-xs ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>Linhas lidas</p>
                    </div>
                    <div className="p-3 rounded-lg text-center bg-green-500/20">
                      <p className="text-2xl font-bold text-green-400">{importResult.criados}</p>
                      <p className="text-xs text-green-400">Criados</p>
                    </div>
                    <div className="p-3 rounded-lg text-center bg-amber-500/20">
                      <p className="text-2xl font-bold text-amber-400">{importResult.pulados.length}</p>
                      <p className="text-xs text-amber-400">Pulados</p>
                    </div>
                  </div>

                  {importResult.pulados.length > 0 && (
                    <div>
                      <div className="flex items-center justify-between mb-2">
                        <p className={`text-sm font-medium ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
                          Linhas puladas
                        </p>
                        <button
                          onClick={handleDownloadPulados}
                          className="flex items-center gap-1.5 text-sm text-indigo-400 hover:text-indigo-300 transition-colors"
                        >
                          <Download className="w-4 h-4" />
                          Baixar linhas puladas (CSV)
                        </button>
                      </div>
                      <div className={`rounded-lg border max-h-60 overflow-y-auto ${isDark ? 'border-gray-700' : 'border-gray-200'}`}>
                        {importResult.pulados.map((p, i) => (
                          <div
                            key={i}
                            className={`flex items-start gap-2 px-3 py-2 text-sm ${i > 0 ? (isDark ? 'border-t border-gray-700' : 'border-t border-gray-100') : ''}`}
                          >
                            <XCircle className="w-4 h-4 text-amber-400 flex-shrink-0 mt-0.5" />
                            <span className={isDark ? 'text-gray-300' : 'text-gray-600'}>
                              <span className="font-medium">Linha {p.linha}</span>
                              {p.email ? ` (${p.email})` : ''} — {p.motivo}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {importResult.criados > 0 && (
                    <div className="p-3 bg-green-500/10 border border-green-500/30 rounded-lg flex items-center gap-2 text-green-400 text-sm">
                      <CheckCircle className="w-4 h-4 flex-shrink-0" />
                      {importResult.criados} usuário(s) criado(s) com sucesso. A lista foi atualizada.
                    </div>
                  )}
                </div>
              ) : (
                <>
                  <div className={`p-3 rounded-lg ${isDark ? 'bg-gray-700/40' : 'bg-gray-50'}`}>
                    <p className={`text-sm ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
                      Envie uma planilha <span className="font-medium">.csv</span> ou{' '}
                      <span className="font-medium">.xlsx</span> com as colunas: nome, email, perfil_acesso,
                      centro_custo, recebe_alertas_corte, recebe_insights_nori. Apenas nome e email são obrigatórios.
                    </p>
                    <button
                      onClick={handleDownloadTemplate}
                      className="mt-2 flex items-center gap-2 text-sm text-indigo-400 hover:text-indigo-300 transition-colors"
                    >
                      <Download className="w-4 h-4" />
                      Baixar modelo da planilha
                    </button>
                  </div>

                  <div
                    onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
                    onDragLeave={(e) => { e.preventDefault(); setDragOver(false); }}
                    onDrop={(e) => {
                      e.preventDefault();
                      setDragOver(false);
                      const f = e.dataTransfer.files?.[0];
                      if (f) handleImportFileSelect(f);
                    }}
                    className={`rounded-lg border-2 border-dashed p-6 text-center transition-colors ${
                      dragOver
                        ? 'border-indigo-500 bg-indigo-500/10'
                        : isDark ? 'border-gray-600' : 'border-gray-300'
                    }`}
                  >
                    <FileSpreadsheet className={`w-8 h-8 mx-auto mb-2 ${isDark ? 'text-gray-400' : 'text-gray-400'}`} />
                    {importFile ? (
                      <div className="flex items-center justify-center gap-2">
                        <span className={`text-sm font-medium ${isDark ? 'text-white' : 'text-gray-900'}`}>{importFile.name}</span>
                        <button
                          onClick={() => handleImportFileSelect(null)}
                          className="text-gray-400 hover:text-red-400"
                        >
                          <X className="w-4 h-4" />
                        </button>
                      </div>
                    ) : (
                      <p className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                        Arraste o arquivo aqui ou
                      </p>
                    )}
                    <label className="inline-block mt-2 cursor-pointer">
                      <span className="px-3 py-1.5 rounded-lg text-sm bg-gradient-to-r from-indigo-500 to-purple-500 text-white hover:opacity-90 transition-opacity">
                        Selecionar arquivo
                      </span>
                      <input
                        type="file"
                        accept=".csv,.xlsx,.xls"
                        className="hidden"
                        onChange={(e) => handleImportFileSelect(e.target.files?.[0] || null)}
                      />
                    </label>
                  </div>

                  <div>
                    <label className={`block text-sm font-medium mb-1 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
                      Senha padrão *
                    </label>
                    <input
                      type="password"
                      value={importPassword}
                      onChange={(e) => setImportPassword(e.target.value)}
                      className={`w-full px-4 py-2 rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white' : 'bg-gray-50 border-gray-300 text-gray-900'} focus:ring-2 focus:ring-indigo-500`}
                      placeholder="Mínimo 6 caracteres"
                    />
                    <p className={`text-xs mt-1 ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                      Aplicada a todos os usuários criados neste lote. Eles podem trocar depois.
                    </p>
                  </div>
                </>
              )}
            </div>

            <div className={`flex justify-end gap-3 p-4 border-t ${isDark ? 'border-gray-700' : 'border-gray-200'}`}>
              <button
                type="button"
                onClick={() => setShowImportModal(false)}
                className={`px-4 py-2 rounded-lg ${isDark ? 'bg-gray-700 text-gray-300 hover:bg-gray-600' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'} transition-colors`}
              >
                {importResult ? 'Fechar' : 'Cancelar'}
              </button>
              {!importResult && (
                <button
                  type="button"
                  onClick={handleImportSubmit}
                  disabled={importing}
                  className="px-4 py-2 bg-gradient-to-r from-indigo-500 to-purple-500 text-white rounded-lg hover:opacity-90 transition-opacity disabled:opacity-50 flex items-center gap-2"
                >
                  {importing ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Upload className="w-4 h-4" />}
                  {importing ? 'Importando...' : 'Importar'}
                </button>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default Usuarios;
