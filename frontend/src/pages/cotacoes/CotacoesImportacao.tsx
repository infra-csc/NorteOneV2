import React, { useState, useEffect, useMemo } from 'react';
import { useTheme } from '../../context/ThemeContext';
import api from '../../services/api';
import {
  Plane, Plus, Edit2, Trash2, X, Check, Search, RefreshCw,
  DollarSign, Package, Globe, TrendingUp, ShoppingBag,
  Calendar, MapPin, Eye, ChevronLeft, Star, StarOff,
  BarChart3, Users, AlertCircle, Save, Layers, Filter,
  ArrowRight, Building2, FileText, Tag
} from 'lucide-react';
import { PieChart, Pie, Cell, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts';

const COLORS_CHART = ['#8b5cf6', '#ec4899', '#f97316', '#10b981', '#3b82f6', '#eab308', '#ef4444', '#06b6d4'];

type ViewMode = 'dashboard' | 'viagens' | 'viagem-detail' | 'fornecedores';

interface Fornecedor { id: number; nome: string; contato?: string; localizacao?: string; observacoes?: string; ativo: boolean; }
interface CotacaoEvento { id: number; cotacao_id: number; cadastro_evento_id?: number; evento_nome_manual?: string; quantidade: number; observacoes?: string; evento_nome?: string; }
interface Cotacao {
  id: number; viagem_id: number; fornecedor_id?: number; produto_nome: string; descricao?: string;
  valor_unitario_usd: number; quantidade: number; taxa_cambio?: number;
  valor_unitario_brl?: number; valor_total_usd?: number; valor_total_brl?: number;
  selecionado: boolean; data_cotacao?: string; observacoes?: string;
  fornecedor_nome?: string; eventos: CotacaoEvento[];
}
interface CustoImportacao { id: number; viagem_id: number; descricao: string; tipo: string; valor_usd: number; valor_brl: number; observacoes?: string; }
interface Viagem {
  id: number; titulo: string; destino: string; ano_competencia: number;
  data_inicio?: string; data_fim?: string; status: string; observacoes?: string;
  total_cotacoes: number; total_usd: number; total_brl: number; criador_nome?: string;
}
interface ViagemDetail extends Viagem { cotacoes: Cotacao[]; custos_importacao: CustoImportacao[]; }
interface DashboardData {
  total_viagens: number; viagens_em_andamento: number; total_produtos_cotados: number;
  total_selecionados: number; total_usd: number; total_brl: number;
  total_custos_importacao_usd: number; total_custos_importacao_brl: number;
  custo_total_brl: number; total_fornecedores: number; total_eventos_vinculados: number;
  por_evento: any[]; por_fornecedor: any[]; por_status: any[];
}
interface EventoOption { id: number; nome: string; ano_evento?: number; }

const CotacoesImportacao: React.FC = () => {
  const { isDark } = useTheme();
  const [view, setView] = useState<ViewMode>('dashboard');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [anoFiltro, setAnoFiltro] = useState(new Date().getFullYear());

  const [dashData, setDashData] = useState<DashboardData | null>(null);
  const [cambio, setCambio] = useState<{ taxa: number; variacao: number; data: string }>({ taxa: 0, variacao: 0, data: '' });
  const [viagens, setViagens] = useState<Viagem[]>([]);
  const [selectedViagem, setSelectedViagem] = useState<ViagemDetail | null>(null);
  const [fornecedores, setFornecedores] = useState<Fornecedor[]>([]);
  const [eventos, setEventos] = useState<EventoOption[]>([]);

  const [showViagemModal, setShowViagemModal] = useState(false);
  const [editViagem, setEditViagem] = useState<Viagem | null>(null);
  const [showCotacaoModal, setShowCotacaoModal] = useState(false);
  const [editCotacao, setEditCotacao] = useState<Cotacao | null>(null);
  const [showCustoModal, setShowCustoModal] = useState(false);
  const [editCusto, setEditCusto] = useState<CustoImportacao | null>(null);
  const [showFornecedorModal, setShowFornecedorModal] = useState(false);
  const [editFornecedor, setEditFornecedor] = useState<Fornecedor | null>(null);
  const [showEventoModal, setShowEventoModal] = useState(false);
  const [linkingCotacaoId, setLinkingCotacaoId] = useState<number | null>(null);
  const [editingEventoId, setEditingEventoId] = useState<number | null>(null);

  const [formViagem, setFormViagem] = useState({ titulo: '', destino: 'China', ano_competencia: new Date().getFullYear(), data_inicio: '', data_fim: '', status: 'Planejada', observacoes: '' });
  const [formCotacao, setFormCotacao] = useState({ produto_nome: '', descricao: '', fornecedor_id: '', valor_unitario_usd: '', quantidade: '1', taxa_cambio: '', data_cotacao: '', observacoes: '' });
  const [formCusto, setFormCusto] = useState({ descricao: '', tipo: 'Frete Internacional', valor_usd: '', valor_brl: '', observacoes: '' });
  const [formFornecedor, setFormFornecedor] = useState({ nome: '', contato: '', localizacao: '', observacoes: '' });
  const [formEvento, setFormEvento] = useState({ cadastro_evento_id: '', evento_nome_manual: '', quantidade: '1', observacoes: '' });
  const [eventoInputMode, setEventoInputMode] = useState<'select' | 'free'>('select');
  const [saving, setSaving] = useState(false);
  const [searchViagem, setSearchViagem] = useState('');

  const TIPOS_CUSTO = ['Frete Internacional', 'Frete Nacional', 'Seguro', 'II - Imposto Importação', 'IPI', 'ICMS', 'PIS/COFINS', 'Despachante', 'Armazenagem', 'Outros'];

  const anos = useMemo(() => {
    const currentYear = new Date().getFullYear();
    return Array.from({ length: 5 }, (_, i) => currentYear - 2 + i);
  }, []);

  useEffect(() => {
    loadCambio();
    loadFornecedores();
    loadEventos();
  }, []);

  useEffect(() => {
    if (view === 'dashboard') loadDashboard();
    if (view === 'viagens') loadViagens();
  }, [view, anoFiltro]);

  const loadCambio = async () => {
    try {
      const res = await api.get('/cotacoes/cambio');
      setCambio(res.data);
    } catch { }
  };

  const loadDashboard = async () => {
    setLoading(true);
    try {
      const res = await api.get(`/cotacoes/dashboard?ano=${anoFiltro}`);
      setDashData(res.data);
    } catch (err: any) { setError(err.response?.data?.detail || 'Erro ao carregar dashboard'); }
    finally { setLoading(false); }
  };

  const loadViagens = async () => {
    setLoading(true);
    try {
      const res = await api.get(`/cotacoes/viagens?ano=${anoFiltro}`);
      setViagens(res.data);
    } catch (err: any) { setError(err.response?.data?.detail || 'Erro ao carregar viagens'); }
    finally { setLoading(false); }
  };

  const loadViagemDetail = async (id: number) => {
    setLoading(true);
    try {
      const res = await api.get(`/cotacoes/viagens/${id}`);
      setSelectedViagem(res.data);
      setView('viagem-detail');
    } catch (err: any) { setError(err.response?.data?.detail || 'Erro ao carregar viagem'); }
    finally { setLoading(false); }
  };

  const loadFornecedores = async () => {
    try {
      const res = await api.get('/cotacoes/fornecedores');
      setFornecedores(res.data);
    } catch { }
  };

  const loadEventos = async () => {
    try {
      const res = await api.get('/cadastros/');
      setEventos(res.data.map((e: any) => ({ id: e.id, nome: e.nome, ano_evento: e.ano_evento })));
    } catch { }
  };

  const handleSaveViagem = async () => {
    setSaving(true);
    try {
      const payload = {
        ...formViagem,
        ano_competencia: Number(formViagem.ano_competencia),
        data_inicio: formViagem.data_inicio || null,
        data_fim: formViagem.data_fim || null,
        observacoes: formViagem.observacoes || null,
      };
      if (editViagem) {
        await api.put(`/cotacoes/viagens/${editViagem.id}`, payload);
      } else {
        await api.post('/cotacoes/viagens', payload);
      }
      setShowViagemModal(false);
      loadViagens();
      if (view === 'dashboard') loadDashboard();
    } catch (err: any) { setError(err.response?.data?.detail || 'Erro ao salvar viagem'); }
    finally { setSaving(false); }
  };

  const handleDeleteViagem = async (id: number) => {
    if (!confirm('Excluir esta viagem e todas as cotações?')) return;
    try {
      await api.delete(`/cotacoes/viagens/${id}`);
      loadViagens();
      if (view === 'dashboard') loadDashboard();
    } catch (err: any) { setError(err.response?.data?.detail || 'Erro ao excluir'); }
  };

  const handleSaveCotacao = async () => {
    if (!selectedViagem) return;
    setSaving(true);
    try {
      const payload = {
        produto_nome: formCotacao.produto_nome,
        descricao: formCotacao.descricao || null,
        fornecedor_id: formCotacao.fornecedor_id ? Number(formCotacao.fornecedor_id) : null,
        valor_unitario_usd: Number(formCotacao.valor_unitario_usd) || 0,
        quantidade: Number(formCotacao.quantidade) || 1,
        taxa_cambio: formCotacao.taxa_cambio ? Number(formCotacao.taxa_cambio) : (cambio.taxa || null),
        data_cotacao: formCotacao.data_cotacao || null,
        observacoes: formCotacao.observacoes || null,
      };
      if (editCotacao) {
        await api.put(`/cotacoes/cotacoes/${editCotacao.id}`, payload);
      } else {
        await api.post(`/cotacoes/viagens/${selectedViagem.id}/cotacoes`, payload);
      }
      setShowCotacaoModal(false);
      loadViagemDetail(selectedViagem.id);
    } catch (err: any) { setError(err.response?.data?.detail || 'Erro ao salvar cotação'); }
    finally { setSaving(false); }
  };

  const handleDeleteCotacao = async (id: number) => {
    if (!selectedViagem || !confirm('Excluir esta cotação?')) return;
    try {
      await api.delete(`/cotacoes/cotacoes/${id}`);
      loadViagemDetail(selectedViagem.id);
    } catch (err: any) { setError(err.response?.data?.detail || 'Erro ao excluir'); }
  };

  const handleToggleSelecionado = async (c: Cotacao) => {
    if (!selectedViagem) return;
    try {
      await api.put(`/cotacoes/cotacoes/${c.id}`, { selecionado: !c.selecionado });
      loadViagemDetail(selectedViagem.id);
    } catch { }
  };

  const handleSaveCusto = async () => {
    if (!selectedViagem) return;
    setSaving(true);
    try {
      const payload = {
        descricao: formCusto.descricao,
        tipo: formCusto.tipo,
        valor_usd: Number(formCusto.valor_usd) || 0,
        valor_brl: Number(formCusto.valor_brl) || 0,
        observacoes: formCusto.observacoes || null,
      };
      if (editCusto) {
        await api.put(`/cotacoes/custos/${editCusto.id}`, payload);
      } else {
        await api.post(`/cotacoes/viagens/${selectedViagem.id}/custos`, payload);
      }
      setShowCustoModal(false);
      loadViagemDetail(selectedViagem.id);
    } catch (err: any) { setError(err.response?.data?.detail || 'Erro ao salvar custo'); }
    finally { setSaving(false); }
  };

  const handleDeleteCusto = async (id: number) => {
    if (!selectedViagem || !confirm('Excluir este custo?')) return;
    try {
      await api.delete(`/cotacoes/custos/${id}`);
      loadViagemDetail(selectedViagem.id);
    } catch { }
  };

  const handleSaveFornecedor = async () => {
    setSaving(true);
    try {
      if (editFornecedor) {
        await api.put(`/cotacoes/fornecedores/${editFornecedor.id}`, formFornecedor);
      } else {
        await api.post('/cotacoes/fornecedores', formFornecedor);
      }
      setShowFornecedorModal(false);
      loadFornecedores();
    } catch (err: any) { setError(err.response?.data?.detail || 'Erro ao salvar fornecedor'); }
    finally { setSaving(false); }
  };

  const handleDeleteFornecedor = async (id: number) => {
    if (!confirm('Desativar este fornecedor?')) return;
    try {
      await api.delete(`/cotacoes/fornecedores/${id}`);
      loadFornecedores();
    } catch { }
  };

  const handleLinkEvento = async () => {
    if (!selectedViagem) return;
    if (eventoInputMode === 'select' && !formEvento.cadastro_evento_id) { setError('Selecione um evento'); return; }
    if (eventoInputMode === 'free' && !formEvento.evento_nome_manual.trim()) { setError('Digite o nome do evento'); return; }
    setSaving(true);
    try {
      const payload: any = {
        quantidade: Number(formEvento.quantidade) || 1,
        observacoes: formEvento.observacoes || null,
      };
      if (eventoInputMode === 'select') {
        payload.cadastro_evento_id = Number(formEvento.cadastro_evento_id);
      } else {
        payload.evento_nome_manual = formEvento.evento_nome_manual.trim();
      }
      if (editingEventoId) {
        await api.put(`/cotacoes/cotacoes-evento/${editingEventoId}`, payload);
      } else {
        await api.post(`/cotacoes/cotacoes/${linkingCotacaoId}/eventos`, payload);
      }
      setShowEventoModal(false);
      setEditingEventoId(null);
      loadViagemDetail(selectedViagem.id);
    } catch (err: any) { setError(err.response?.data?.detail || 'Erro ao vincular evento'); }
    finally { setSaving(false); }
  };

  const handleUnlinkEvento = async (ceId: number) => {
    if (!selectedViagem || !confirm('Remover vínculo com evento?')) return;
    try {
      await api.delete(`/cotacoes/cotacoes-evento/${ceId}`);
      loadViagemDetail(selectedViagem.id);
    } catch { }
  };

  const openViagemModal = (v?: Viagem) => {
    setEditViagem(v || null);
    setFormViagem({
      titulo: v?.titulo || '', destino: v?.destino || 'China',
      ano_competencia: v?.ano_competencia || new Date().getFullYear(),
      data_inicio: v?.data_inicio || '', data_fim: v?.data_fim || '',
      status: v?.status || 'Planejada', observacoes: v?.observacoes || '',
    });
    setShowViagemModal(true);
  };

  const openCotacaoModal = (c?: Cotacao) => {
    setEditCotacao(c || null);
    setFormCotacao({
      produto_nome: c?.produto_nome || '', descricao: c?.descricao || '',
      fornecedor_id: c?.fornecedor_id?.toString() || '',
      valor_unitario_usd: c?.valor_unitario_usd?.toString() || '',
      quantidade: c?.quantidade?.toString() || '1',
      taxa_cambio: c?.taxa_cambio?.toString() || (cambio.taxa ? cambio.taxa.toString() : ''),
      data_cotacao: c?.data_cotacao || new Date().toISOString().split('T')[0],
      observacoes: c?.observacoes || '',
    });
    setShowCotacaoModal(true);
  };

  const openCustoModal = (ci?: CustoImportacao) => {
    setEditCusto(ci || null);
    const taxaCambioAtual = cambio.taxa || 0;
    setFormCusto({
      descricao: ci?.descricao || '', tipo: ci?.tipo || 'Frete Internacional',
      valor_usd: ci?.valor_usd?.toString() || '',
      valor_brl: ci?.valor_brl?.toString() || (ci?.valor_usd && taxaCambioAtual ? (ci.valor_usd * taxaCambioAtual).toFixed(2) : ''),
      observacoes: ci?.observacoes || '',
    });
    setShowCustoModal(true);
  };

  const openFornecedorModal = (f?: Fornecedor) => {
    setEditFornecedor(f || null);
    setFormFornecedor({ nome: f?.nome || '', contato: f?.contato || '', localizacao: f?.localizacao || '', observacoes: f?.observacoes || '' });
    setShowFornecedorModal(true);
  };

  const openEventoLink = (cotacaoId: number) => {
    setLinkingCotacaoId(cotacaoId);
    setEditingEventoId(null);
    setFormEvento({ cadastro_evento_id: '', evento_nome_manual: '', quantidade: '1', observacoes: '' });
    setEventoInputMode('select');
    setShowEventoModal(true);
  };

  const openEditEvento = (ce: CotacaoEvento) => {
    setEditingEventoId(ce.id);
    setLinkingCotacaoId(ce.cotacao_id);
    if (ce.cadastro_evento_id) {
      setEventoInputMode('select');
      setFormEvento({ cadastro_evento_id: String(ce.cadastro_evento_id), evento_nome_manual: '', quantidade: String(ce.quantidade), observacoes: ce.observacoes || '' });
    } else {
      setEventoInputMode('free');
      setFormEvento({ cadastro_evento_id: '', evento_nome_manual: ce.evento_nome_manual || ce.evento_nome || '', quantidade: String(ce.quantidade), observacoes: ce.observacoes || '' });
    }
    setShowEventoModal(true);
  };

  const fmt = (v: number) => v.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

  const statusColor = (s: string) => {
    if (s === 'Planejada') return 'bg-blue-500/20 text-blue-400';
    if (s === 'Em Andamento') return 'bg-amber-500/20 text-amber-400';
    return 'bg-emerald-500/20 text-emerald-400';
  };

  const filteredViagens = viagens.filter(v => !searchViagem || v.titulo.toLowerCase().includes(searchViagem.toLowerCase()));

  const cardClass = `rounded-2xl p-5 ${isDark ? 'bg-gray-800/60 border border-gray-700/50' : 'bg-white border border-gray-200'} shadow-sm`;
  const inputClass = `w-full px-3 py-2 rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white' : 'bg-white border-gray-300 text-gray-900'} focus:ring-2 focus:ring-purple-500 focus:border-transparent outline-none text-sm`;
  const labelClass = `block text-xs font-medium mb-1 ${isDark ? 'text-gray-400' : 'text-gray-600'}`;

  const renderDashboard = () => {
    if (!dashData) return null;
    return (
      <div className="space-y-6">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {[
            { label: 'Viagens', value: dashData.total_viagens, icon: Plane, color: 'from-purple-500 to-indigo-500' },
            { label: 'Produtos Cotados', value: dashData.total_produtos_cotados, icon: Package, color: 'from-pink-500 to-rose-500' },
            { label: 'Selecionados', value: dashData.total_selecionados, icon: Check, color: 'from-emerald-500 to-teal-500' },
            { label: 'Fornecedores', value: dashData.total_fornecedores, icon: Building2, color: 'from-amber-500 to-orange-500' },
          ].map(({ label, value, icon: Icon, color }) => (
            <div key={label} className={cardClass}>
              <div className="flex items-center gap-3">
                <div className={`w-10 h-10 rounded-xl bg-gradient-to-br ${color} flex items-center justify-center`}>
                  <Icon className="w-5 h-5 text-white" />
                </div>
                <div>
                  <p className={`text-xs ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>{label}</p>
                  <p className={`text-xl font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>{value}</p>
                </div>
              </div>
            </div>
          ))}
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className={cardClass}>
            <p className={`text-xs ${isDark ? 'text-gray-400' : 'text-gray-500'} mb-1`}>Total Produtos (USD)</p>
            <p className={`text-2xl font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>$ {fmt(dashData.total_usd)}</p>
          </div>
          <div className={cardClass}>
            <p className={`text-xs ${isDark ? 'text-gray-400' : 'text-gray-500'} mb-1`}>Custos Importação (BRL)</p>
            <p className={`text-2xl font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>R$ {fmt(dashData.total_custos_importacao_brl)}</p>
          </div>
          <div className={`${cardClass} bg-gradient-to-br ${isDark ? 'from-purple-900/30 to-pink-900/30' : 'from-purple-50 to-pink-50'}`}>
            <p className={`text-xs ${isDark ? 'text-gray-400' : 'text-gray-500'} mb-1`}>Custo Total (BRL)</p>
            <p className="text-2xl font-bold text-purple-500">R$ {fmt(dashData.custo_total_brl)}</p>
          </div>
        </div>

        {cambio.taxa > 0 && (
          <div className={`${cardClass} flex items-center gap-3`}>
            <Globe className="w-5 h-5 text-blue-500" />
            <div>
              <span className={`text-sm font-medium ${isDark ? 'text-white' : 'text-gray-900'}`}>Câmbio USD/BRL: R$ {cambio.taxa.toFixed(4)}</span>
              <span className={`text-xs ml-3 ${cambio.variacao >= 0 ? 'text-emerald-500' : 'text-red-500'}`}>
                {cambio.variacao >= 0 ? '+' : ''}{cambio.variacao.toFixed(4)}
              </span>
            </div>
          </div>
        )}

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {dashData.por_evento.length > 0 && (
            <div className={cardClass}>
              <h3 className={`text-sm font-semibold mb-4 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>Custo por Evento (BRL)</h3>
              <ResponsiveContainer width="100%" height={250}>
                <BarChart data={dashData.por_evento}>
                  <CartesianGrid strokeDasharray="3 3" stroke={isDark ? '#374151' : '#e5e7eb'} />
                  <XAxis dataKey="evento" tick={{ fontSize: 10, fill: isDark ? '#9ca3af' : '#6b7280' }} />
                  <YAxis tick={{ fontSize: 10, fill: isDark ? '#9ca3af' : '#6b7280' }} tickFormatter={(v: number) => v.toLocaleString('pt-BR')} />
                  <Tooltip contentStyle={{ backgroundColor: isDark ? '#1f2937' : '#fff', border: 'none', borderRadius: 8 }} formatter={(v: any) => `R$ ${fmt(v)}`} />
                  <Bar dataKey="total_brl" name="BRL" fill="#8b5cf6" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
          {dashData.por_fornecedor.length > 0 && (
            <div className={cardClass}>
              <h3 className={`text-sm font-semibold mb-4 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>Por Fornecedor (BRL)</h3>
              <ResponsiveContainer width="100%" height={250}>
                <PieChart>
                  <Pie data={dashData.por_fornecedor} dataKey="total_brl" nameKey="fornecedor" cx="50%" cy="50%" outerRadius={90} label={({ fornecedor, percent }: any) => `${fornecedor} (${(percent * 100).toFixed(0)}%)`}>
                    {dashData.por_fornecedor.map((_, i) => <Cell key={i} fill={COLORS_CHART[i % COLORS_CHART.length]} />)}
                  </Pie>
                  <Tooltip contentStyle={{ backgroundColor: isDark ? '#1f2937' : '#fff', border: 'none', borderRadius: 8 }} formatter={(v: any) => `R$ ${fmt(v)}`} />
                </PieChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>
      </div>
    );
  };

  const renderViagens = () => (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <div className="relative flex-1">
          <Search className={`absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 ${isDark ? 'text-gray-500' : 'text-gray-400'}`} />
          <input
            value={searchViagem} onChange={e => setSearchViagem(e.target.value)}
            placeholder="Buscar viagem..."
            className={`${inputClass} pl-9`}
          />
        </div>
        <button onClick={() => openViagemModal()} className="flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-purple-500 to-pink-500 text-white rounded-xl text-sm font-medium hover:opacity-90 transition-opacity">
          <Plus className="w-4 h-4" /> Nova Viagem
        </button>
      </div>

      {filteredViagens.length === 0 ? (
        <div className={`${cardClass} text-center py-12`}>
          <Plane className={`w-12 h-12 mx-auto mb-3 ${isDark ? 'text-gray-600' : 'text-gray-400'}`} />
          <p className={`${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Nenhuma viagem encontrada para {anoFiltro}</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {filteredViagens.map(v => (
            <div key={v.id} className={`${cardClass} cursor-pointer hover:shadow-md transition-shadow`} onClick={() => loadViagemDetail(v.id)}>
              <div className="flex items-start justify-between mb-3">
                <div>
                  <h3 className={`font-semibold ${isDark ? 'text-white' : 'text-gray-900'}`}>{v.titulo}</h3>
                  <p className={`text-xs ${isDark ? 'text-gray-400' : 'text-gray-500'} flex items-center gap-1 mt-1`}>
                    <MapPin className="w-3 h-3" /> {v.destino}
                    <span className="mx-1">•</span>
                    <Calendar className="w-3 h-3" /> Competência: {v.ano_competencia}
                  </p>
                </div>
                <span className={`px-2 py-1 rounded-full text-xs font-medium ${statusColor(v.status)}`}>{v.status}</span>
              </div>
              <div className="flex items-center gap-4 mt-3">
                <div>
                  <p className={`text-xs ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>Cotações</p>
                  <p className={`text-sm font-semibold ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>{v.total_cotacoes}</p>
                </div>
                <div>
                  <p className={`text-xs ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>Total USD</p>
                  <p className={`text-sm font-semibold ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>$ {fmt(v.total_usd)}</p>
                </div>
                <div>
                  <p className={`text-xs ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>Total BRL</p>
                  <p className={`text-sm font-semibold text-purple-500`}>R$ {fmt(v.total_brl)}</p>
                </div>
              </div>
              {v.data_inicio && (
                <p className={`text-xs mt-2 ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>
                  {v.data_inicio}{v.data_fim ? ` → ${v.data_fim}` : ''}
                </p>
              )}
              <div className="flex justify-end gap-2 mt-3" onClick={e => e.stopPropagation()}>
                <button onClick={() => openViagemModal(v)} className={`p-1.5 rounded-lg ${isDark ? 'hover:bg-gray-700' : 'hover:bg-gray-100'}`}>
                  <Edit2 className="w-3.5 h-3.5 text-blue-500" />
                </button>
                <button onClick={() => handleDeleteViagem(v.id)} className={`p-1.5 rounded-lg ${isDark ? 'hover:bg-gray-700' : 'hover:bg-gray-100'}`}>
                  <Trash2 className="w-3.5 h-3.5 text-red-500" />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );

  const renderViagemDetail = () => {
    if (!selectedViagem) return null;
    const v = selectedViagem;
    const cotacoesSel = v.cotacoes.filter(c => c.selecionado);
    const totalSelUsd = cotacoesSel.reduce((s, c) => s + (c.valor_total_usd || 0), 0);
    const totalSelBrl = cotacoesSel.reduce((s, c) => s + (c.valor_total_brl || 0), 0);
    const totalCustosUsd = v.custos_importacao.reduce((s, ci) => s + ci.valor_usd, 0);
    const totalCustosBrl = v.custos_importacao.reduce((s, ci) => s + ci.valor_brl, 0);

    const produtoGroups: Record<string, Cotacao[]> = {};
    v.cotacoes.forEach(c => {
      const key = c.produto_nome;
      if (!produtoGroups[key]) produtoGroups[key] = [];
      produtoGroups[key].push(c);
    });

    return (
      <div className="space-y-6">
        <div className="flex items-center gap-3">
          <button onClick={() => { setView('viagens'); setSelectedViagem(null); }} className={`p-2 rounded-lg ${isDark ? 'hover:bg-gray-700' : 'hover:bg-gray-100'}`}>
            <ChevronLeft className="w-5 h-5" />
          </button>
          <div className="flex-1">
            <h2 className={`text-lg font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>{v.titulo}</h2>
            <p className={`text-xs ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
              {v.destino} • Competência: {v.ano_competencia}
              {v.data_inicio && ` • ${v.data_inicio}`}{v.data_fim && ` → ${v.data_fim}`}
            </p>
          </div>
          <span className={`px-3 py-1 rounded-full text-xs font-medium ${statusColor(v.status)}`}>{v.status}</span>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <div className={cardClass}>
            <p className={`text-xs ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>Produtos (USD)</p>
            <p className={`text-lg font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>$ {fmt(totalSelUsd)}</p>
          </div>
          <div className={cardClass}>
            <p className={`text-xs ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>Produtos (BRL)</p>
            <p className={`text-lg font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>R$ {fmt(totalSelBrl)}</p>
          </div>
          <div className={cardClass}>
            <p className={`text-xs ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>Importação (BRL)</p>
            <p className={`text-lg font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>R$ {fmt(totalCustosBrl)}</p>
          </div>
          <div className={`${cardClass} bg-gradient-to-br ${isDark ? 'from-purple-900/30 to-pink-900/30' : 'from-purple-50 to-pink-50'}`}>
            <p className={`text-xs ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>Custo Total (BRL)</p>
            <p className="text-lg font-bold text-purple-500">R$ {fmt(totalSelBrl + totalCustosBrl)}</p>
          </div>
        </div>

        <div>
          <div className="flex items-center justify-between mb-3">
            <h3 className={`text-sm font-semibold ${isDark ? 'text-gray-300' : 'text-gray-700'} flex items-center gap-2`}>
              <Package className="w-4 h-4 text-purple-500" /> Cotações ({v.cotacoes.length})
            </h3>
            <button onClick={() => openCotacaoModal()} className="flex items-center gap-1 px-3 py-1.5 bg-gradient-to-r from-purple-500 to-pink-500 text-white rounded-lg text-xs font-medium hover:opacity-90">
              <Plus className="w-3 h-3" /> Nova Cotação
            </button>
          </div>

          {Object.entries(produtoGroups).map(([produto, cotacoes]) => (
            <div key={produto} className={`${cardClass} mb-3`}>
              <div className="flex items-center gap-2 mb-3">
                <Tag className={`w-4 h-4 ${isDark ? 'text-purple-400' : 'text-purple-500'}`} />
                <h4 className={`font-medium text-sm ${isDark ? 'text-white' : 'text-gray-900'}`}>{produto}</h4>
                <span className={`text-xs ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>({cotacoes.length} cotação{cotacoes.length > 1 ? 'ões' : ''})</span>
              </div>
              <div className="space-y-2">
                {cotacoes.map(c => (
                  <div key={c.id} className={`rounded-xl p-3 ${c.selecionado ? (isDark ? 'bg-emerald-900/20 border border-emerald-500/30' : 'bg-emerald-50 border border-emerald-200') : (isDark ? 'bg-gray-700/50' : 'bg-gray-50')} transition-all`}>
                    <div className="flex items-start justify-between">
                      <div className="flex-1">
                        <div className="flex items-center gap-2 flex-wrap">
                          {c.fornecedor_nome && (
                            <span className={`text-xs px-2 py-0.5 rounded-full ${isDark ? 'bg-gray-600 text-gray-300' : 'bg-gray-200 text-gray-600'}`}>
                              <Building2 className="w-3 h-3 inline mr-1" />{c.fornecedor_nome}
                            </span>
                          )}
                          {c.data_cotacao && <span className={`text-xs ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>{c.data_cotacao}</span>}
                        </div>
                        <div className="flex items-center gap-4 mt-2">
                          <div>
                            <span className={`text-xs ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>Unit. USD</span>
                            <p className={`text-sm font-semibold ${isDark ? 'text-gray-200' : 'text-gray-800'}`}>$ {fmt(c.valor_unitario_usd)}</p>
                          </div>
                          <div>
                            <span className={`text-xs ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>Qtd</span>
                            <p className={`text-sm font-semibold ${isDark ? 'text-gray-200' : 'text-gray-800'}`}>{c.quantidade}</p>
                          </div>
                          <div>
                            <span className={`text-xs ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>Total USD</span>
                            <p className={`text-sm font-semibold ${isDark ? 'text-gray-200' : 'text-gray-800'}`}>$ {fmt(c.valor_total_usd || 0)}</p>
                          </div>
                          <div>
                            <span className={`text-xs ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>Total BRL</span>
                            <p className="text-sm font-semibold text-purple-500">R$ {fmt(c.valor_total_brl || 0)}</p>
                          </div>
                          {c.taxa_cambio && (
                            <div>
                              <span className={`text-xs ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>Câmbio</span>
                              <p className={`text-xs ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>{c.taxa_cambio.toFixed(4)}</p>
                            </div>
                          )}
                        </div>
                        {c.descricao && <p className={`text-xs mt-1 ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>{c.descricao}</p>}
                        {c.eventos.length > 0 && (
                          <div className="flex flex-col gap-1.5 mt-2">
                            {c.eventos.map(ce => (
                              <div key={ce.id} className={`flex items-center justify-between text-xs px-2.5 py-1.5 rounded-lg ${isDark ? 'bg-purple-900/30 text-purple-300' : 'bg-purple-100 text-purple-700'}`}>
                                <div className="flex-1 min-w-0">
                                  <span className="font-medium">{ce.evento_nome || ce.evento_nome_manual || `Evento #${ce.cadastro_evento_id}`}</span>
                                  <span className={`ml-2 ${isDark ? 'text-purple-400' : 'text-purple-500'}`}>Qtd: {ce.quantidade}</span>
                                  {ce.observacoes && <span className={`ml-2 truncate ${isDark ? 'text-purple-400/70' : 'text-purple-400'}`}>• {ce.observacoes}</span>}
                                </div>
                                <div className="flex items-center gap-1 ml-2 shrink-0">
                                  <button onClick={() => openEditEvento(ce)} title="Editar vínculo" className="hover:text-blue-400"><Edit2 className="w-3 h-3" /></button>
                                  <button onClick={() => handleUnlinkEvento(ce.id)} title="Remover vínculo" className="hover:text-red-400"><X className="w-3 h-3" /></button>
                                </div>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                      <div className="flex items-center gap-1 ml-2">
                        <button onClick={() => handleToggleSelecionado(c)} title={c.selecionado ? 'Remover seleção' : 'Selecionar'} className={`p-1.5 rounded-lg ${c.selecionado ? 'text-emerald-500' : isDark ? 'text-gray-500 hover:text-gray-300' : 'text-gray-400 hover:text-gray-600'}`}>
                          {c.selecionado ? <Star className="w-4 h-4 fill-current" /> : <StarOff className="w-4 h-4" />}
                        </button>
                        <button onClick={() => openEventoLink(c.id)} title="Vincular evento" className={`p-1.5 rounded-lg ${isDark ? 'text-gray-500 hover:text-gray-300' : 'text-gray-400 hover:text-gray-600'}`}>
                          <Layers className="w-4 h-4" />
                        </button>
                        <button onClick={() => openCotacaoModal(c)} className={`p-1.5 rounded-lg ${isDark ? 'hover:bg-gray-600' : 'hover:bg-gray-200'}`}>
                          <Edit2 className="w-3.5 h-3.5 text-blue-500" />
                        </button>
                        <button onClick={() => handleDeleteCotacao(c.id)} className={`p-1.5 rounded-lg ${isDark ? 'hover:bg-gray-600' : 'hover:bg-gray-200'}`}>
                          <Trash2 className="w-3.5 h-3.5 text-red-500" />
                        </button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
          {v.cotacoes.length === 0 && (
            <div className={`${cardClass} text-center py-8`}>
              <Package className={`w-8 h-8 mx-auto mb-2 ${isDark ? 'text-gray-600' : 'text-gray-400'}`} />
              <p className={`text-sm ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>Nenhuma cotação registrada</p>
            </div>
          )}
        </div>

        <div>
          <div className="flex items-center justify-between mb-3">
            <h3 className={`text-sm font-semibold ${isDark ? 'text-gray-300' : 'text-gray-700'} flex items-center gap-2`}>
              <DollarSign className="w-4 h-4 text-amber-500" /> Custos de Importação ({v.custos_importacao.length})
            </h3>
            <button onClick={() => openCustoModal()} className="flex items-center gap-1 px-3 py-1.5 bg-gradient-to-r from-amber-500 to-orange-500 text-white rounded-lg text-xs font-medium hover:opacity-90">
              <Plus className="w-3 h-3" /> Novo Custo
            </button>
          </div>
          {v.custos_importacao.length > 0 ? (
            <div className={cardClass}>
              <div className="space-y-2">
                {v.custos_importacao.map(ci => (
                  <div key={ci.id} className={`flex items-center justify-between p-3 rounded-lg ${isDark ? 'bg-gray-700/50' : 'bg-gray-50'}`}>
                    <div>
                      <p className={`text-sm font-medium ${isDark ? 'text-white' : 'text-gray-900'}`}>{ci.descricao}</p>
                      <p className={`text-xs ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>{ci.tipo}</p>
                    </div>
                    <div className="flex items-center gap-4">
                      {ci.valor_usd > 0 && <span className={`text-sm ${isDark ? 'text-gray-300' : 'text-gray-600'}`}>$ {fmt(ci.valor_usd)}</span>}
                      <span className="text-sm font-semibold text-amber-500">R$ {fmt(ci.valor_brl)}</span>
                      <button onClick={() => openCustoModal(ci)} className={`p-1 rounded ${isDark ? 'hover:bg-gray-600' : 'hover:bg-gray-200'}`}>
                        <Edit2 className="w-3.5 h-3.5 text-blue-500" />
                      </button>
                      <button onClick={() => handleDeleteCusto(ci.id)} className={`p-1 rounded ${isDark ? 'hover:bg-gray-600' : 'hover:bg-gray-200'}`}>
                        <Trash2 className="w-3.5 h-3.5 text-red-500" />
                      </button>
                    </div>
                  </div>
                ))}
                <div className={`flex justify-end pt-2 border-t ${isDark ? 'border-gray-600' : 'border-gray-200'}`}>
                  <div className="text-right">
                    {totalCustosUsd > 0 && <p className={`text-xs ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Total USD: $ {fmt(totalCustosUsd)}</p>}
                    <p className="text-sm font-bold text-amber-500">Total BRL: R$ {fmt(totalCustosBrl)}</p>
                  </div>
                </div>
              </div>
            </div>
          ) : (
            <div className={`${cardClass} text-center py-8`}>
              <DollarSign className={`w-8 h-8 mx-auto mb-2 ${isDark ? 'text-gray-600' : 'text-gray-400'}`} />
              <p className={`text-sm ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>Nenhum custo de importação registrado</p>
            </div>
          )}
        </div>
      </div>
    );
  };

  const renderFornecedores = () => (
    <div className="space-y-4">
      <div className="flex justify-end">
        <button onClick={() => openFornecedorModal()} className="flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-purple-500 to-pink-500 text-white rounded-xl text-sm font-medium hover:opacity-90">
          <Plus className="w-4 h-4" /> Novo Fornecedor
        </button>
      </div>
      {fornecedores.length === 0 ? (
        <div className={`${cardClass} text-center py-12`}>
          <Building2 className={`w-12 h-12 mx-auto mb-3 ${isDark ? 'text-gray-600' : 'text-gray-400'}`} />
          <p className={`${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Nenhum fornecedor cadastrado</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {fornecedores.map(f => (
            <div key={f.id} className={cardClass}>
              <div className="flex items-start justify-between">
                <div>
                  <h3 className={`font-semibold ${isDark ? 'text-white' : 'text-gray-900'}`}>{f.nome}</h3>
                  {f.localizacao && <p className={`text-xs ${isDark ? 'text-gray-400' : 'text-gray-500'} flex items-center gap-1 mt-1`}><MapPin className="w-3 h-3" /> {f.localizacao}</p>}
                  {f.contato && <p className={`text-xs ${isDark ? 'text-gray-400' : 'text-gray-500'} mt-1`}>{f.contato}</p>}
                  {f.observacoes && <p className={`text-xs ${isDark ? 'text-gray-500' : 'text-gray-400'} mt-2`}>{f.observacoes}</p>}
                </div>
                <div className="flex gap-1">
                  <button onClick={() => openFornecedorModal(f)} className={`p-1.5 rounded-lg ${isDark ? 'hover:bg-gray-700' : 'hover:bg-gray-100'}`}>
                    <Edit2 className="w-3.5 h-3.5 text-blue-500" />
                  </button>
                  <button onClick={() => handleDeleteFornecedor(f.id)} className={`p-1.5 rounded-lg ${isDark ? 'hover:bg-gray-700' : 'hover:bg-gray-100'}`}>
                    <Trash2 className="w-3.5 h-3.5 text-red-500" />
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );

  const renderModal = (show: boolean, onClose: () => void, title: string, onSave: () => void, children: React.ReactNode) => {
    if (!show) return null;
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4" onClick={onClose}>
        <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" />
        <div className={`relative w-full max-w-lg max-h-[90vh] overflow-y-auto rounded-2xl shadow-2xl ${isDark ? 'bg-gray-800' : 'bg-white'}`} onClick={e => e.stopPropagation()}>
          <div className={`flex items-center justify-between p-4 border-b ${isDark ? 'border-gray-700' : 'border-gray-200'}`}>
            <h3 className={`font-semibold ${isDark ? 'text-white' : 'text-gray-900'}`}>{title}</h3>
            <button onClick={onClose} className={`p-1 rounded-lg ${isDark ? 'hover:bg-gray-700' : 'hover:bg-gray-100'}`}><X className="w-5 h-5" /></button>
          </div>
          <div className="p-4 space-y-3">{children}</div>
          <div className={`flex justify-end gap-3 p-4 border-t ${isDark ? 'border-gray-700' : 'border-gray-200'}`}>
            <button onClick={onClose} className={`px-4 py-2 rounded-lg text-sm ${isDark ? 'bg-gray-700 text-gray-300 hover:bg-gray-600' : 'bg-gray-200 text-gray-700 hover:bg-gray-300'}`}>Cancelar</button>
            <button onClick={onSave} disabled={saving} className="flex items-center gap-2 px-5 py-2 bg-gradient-to-r from-purple-500 to-pink-500 text-white rounded-lg text-sm font-medium hover:opacity-90 disabled:opacity-50">
              <Save className="w-4 h-4" /> {saving ? 'Salvando...' : 'Salvar'}
            </button>
          </div>
        </div>
      </div>
    );
  };

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className={`text-2xl font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>Cotação & Importação</h1>
          <p className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Gestão de cotações de produtos e custos de importação</p>
        </div>
        <div className="flex items-center gap-3">
          <select value={anoFiltro} onChange={e => setAnoFiltro(Number(e.target.value))} className={`${inputClass} w-28`}>
            {anos.map(a => <option key={a} value={a}>{a}</option>)}
          </select>
          <button onClick={() => { if (view === 'dashboard') loadDashboard(); else if (view === 'viagens') loadViagens(); }} className={`p-2 rounded-lg ${isDark ? 'hover:bg-gray-700 text-gray-400' : 'hover:bg-gray-100 text-gray-500'}`}>
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      <div className="flex gap-1">
        {[
          { key: 'dashboard' as ViewMode, label: 'Dashboard', icon: BarChart3 },
          { key: 'viagens' as ViewMode, label: 'Viagens', icon: Plane },
          { key: 'fornecedores' as ViewMode, label: 'Fornecedores', icon: Building2 },
        ].map(({ key, label, icon: Icon }) => (
          <button key={key} onClick={() => setView(key)}
            className={`flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium transition-all ${view === key
              ? 'bg-gradient-to-r from-purple-500 to-pink-500 text-white shadow-lg'
              : isDark ? 'text-gray-400 hover:text-gray-200 hover:bg-gray-700/50' : 'text-gray-600 hover:text-gray-800 hover:bg-gray-100'
            }`}
          >
            <Icon className="w-4 h-4" /> {label}
          </button>
        ))}
      </div>

      {error && (
        <div className="flex items-center gap-2 p-3 rounded-xl bg-red-500/10 text-red-400 text-sm">
          <AlertCircle className="w-4 h-4" /> {error}
          <button onClick={() => setError(null)} className="ml-auto"><X className="w-4 h-4" /></button>
        </div>
      )}

      {loading ? (
        <div className="flex items-center justify-center py-20">
          <div className="w-8 h-8 border-4 border-purple-500 border-t-transparent rounded-full animate-spin" />
        </div>
      ) : (
        <>
          {view === 'dashboard' && renderDashboard()}
          {view === 'viagens' && renderViagens()}
          {view === 'viagem-detail' && renderViagemDetail()}
          {view === 'fornecedores' && renderFornecedores()}
        </>
      )}

      {renderModal(showViagemModal, () => setShowViagemModal(false), editViagem ? 'Editar Viagem' : 'Nova Viagem', handleSaveViagem, (
        <>
          <div><label className={labelClass}>Título *</label><input value={formViagem.titulo} onChange={e => setFormViagem({ ...formViagem, titulo: e.target.value })} className={inputClass} placeholder="Ex: China - Março 2026" /></div>
          <div className="grid grid-cols-2 gap-3">
            <div><label className={labelClass}>Destino</label><input value={formViagem.destino} onChange={e => setFormViagem({ ...formViagem, destino: e.target.value })} className={inputClass} /></div>
            <div><label className={labelClass}>Ano Competência *</label><select value={formViagem.ano_competencia} onChange={e => setFormViagem({ ...formViagem, ano_competencia: Number(e.target.value) })} className={inputClass}>{anos.map(a => <option key={a} value={a}>{a}</option>)}</select></div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div><label className={labelClass}>Data Início</label><input type="date" value={formViagem.data_inicio} onChange={e => setFormViagem({ ...formViagem, data_inicio: e.target.value })} className={inputClass} /></div>
            <div><label className={labelClass}>Data Fim</label><input type="date" value={formViagem.data_fim} onChange={e => setFormViagem({ ...formViagem, data_fim: e.target.value })} className={inputClass} /></div>
          </div>
          <div><label className={labelClass}>Status</label><select value={formViagem.status} onChange={e => setFormViagem({ ...formViagem, status: e.target.value })} className={inputClass}><option>Planejada</option><option>Em Andamento</option><option>Finalizada</option></select></div>
          <div><label className={labelClass}>Observações</label><textarea value={formViagem.observacoes} onChange={e => setFormViagem({ ...formViagem, observacoes: e.target.value })} className={`${inputClass} h-20 resize-none`} /></div>
        </>
      ))}

      {renderModal(showCotacaoModal, () => setShowCotacaoModal(false), editCotacao ? 'Editar Cotação' : 'Nova Cotação', handleSaveCotacao, (
        <>
          <div><label className={labelClass}>Produto *</label><input value={formCotacao.produto_nome} onChange={e => setFormCotacao({ ...formCotacao, produto_nome: e.target.value })} className={inputClass} placeholder="Nome do produto" /></div>
          <div><label className={labelClass}>Descrição</label><textarea value={formCotacao.descricao} onChange={e => setFormCotacao({ ...formCotacao, descricao: e.target.value })} className={`${inputClass} h-16 resize-none`} /></div>
          <div><label className={labelClass}>Fornecedor</label>
            <select value={formCotacao.fornecedor_id} onChange={e => setFormCotacao({ ...formCotacao, fornecedor_id: e.target.value })} className={inputClass}>
              <option value="">Selecione...</option>
              {fornecedores.map(f => <option key={f.id} value={f.id}>{f.nome}</option>)}
            </select>
          </div>
          <div className="grid grid-cols-3 gap-3">
            <div><label className={labelClass}>Valor Unit. (USD) *</label><input type="number" step="0.01" value={formCotacao.valor_unitario_usd} onChange={e => setFormCotacao({ ...formCotacao, valor_unitario_usd: e.target.value })} className={inputClass} /></div>
            <div><label className={labelClass}>Quantidade</label><input type="number" value={formCotacao.quantidade} onChange={e => setFormCotacao({ ...formCotacao, quantidade: e.target.value })} className={inputClass} /></div>
            <div><label className={labelClass}>Câmbio (USD/BRL)</label><input type="number" step="0.0001" value={formCotacao.taxa_cambio} onChange={e => setFormCotacao({ ...formCotacao, taxa_cambio: e.target.value })} className={inputClass} placeholder={cambio.taxa ? cambio.taxa.toFixed(4) : ''} /></div>
          </div>
          {formCotacao.valor_unitario_usd && formCotacao.taxa_cambio && (
            <div className={`p-2 rounded-lg text-xs ${isDark ? 'bg-gray-700 text-gray-300' : 'bg-gray-100 text-gray-600'}`}>
              Total estimado: $ {fmt(Number(formCotacao.valor_unitario_usd) * Number(formCotacao.quantidade || 1))} USD = R$ {fmt(Number(formCotacao.valor_unitario_usd) * Number(formCotacao.quantidade || 1) * Number(formCotacao.taxa_cambio))} BRL
            </div>
          )}
          <div><label className={labelClass}>Data da Cotação</label><input type="date" value={formCotacao.data_cotacao} onChange={e => setFormCotacao({ ...formCotacao, data_cotacao: e.target.value })} className={inputClass} /></div>
          <div><label className={labelClass}>Observações</label><textarea value={formCotacao.observacoes} onChange={e => setFormCotacao({ ...formCotacao, observacoes: e.target.value })} className={`${inputClass} h-16 resize-none`} /></div>
        </>
      ))}

      {renderModal(showCustoModal, () => setShowCustoModal(false), editCusto ? 'Editar Custo' : 'Novo Custo de Importação', handleSaveCusto, (
        <>
          <div><label className={labelClass}>Tipo *</label>
            <select value={formCusto.tipo} onChange={e => setFormCusto({ ...formCusto, tipo: e.target.value, descricao: formCusto.descricao || e.target.value })} className={inputClass}>
              {TIPOS_CUSTO.map(t => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>
          <div><label className={labelClass}>Descrição *</label><input value={formCusto.descricao} onChange={e => setFormCusto({ ...formCusto, descricao: e.target.value })} className={inputClass} /></div>
          <div className="grid grid-cols-2 gap-3">
            <div><label className={labelClass}>Valor (USD)</label><input type="number" step="0.01" value={formCusto.valor_usd} onChange={e => {
              const usd = e.target.value;
              setFormCusto({ ...formCusto, valor_usd: usd, valor_brl: cambio.taxa ? (Number(usd) * cambio.taxa).toFixed(2) : formCusto.valor_brl });
            }} className={inputClass} /></div>
            <div><label className={labelClass}>Valor (BRL) *</label><input type="number" step="0.01" value={formCusto.valor_brl} onChange={e => setFormCusto({ ...formCusto, valor_brl: e.target.value })} className={inputClass} /></div>
          </div>
          <div><label className={labelClass}>Observações</label><textarea value={formCusto.observacoes} onChange={e => setFormCusto({ ...formCusto, observacoes: e.target.value })} className={`${inputClass} h-16 resize-none`} /></div>
        </>
      ))}

      {renderModal(showFornecedorModal, () => setShowFornecedorModal(false), editFornecedor ? 'Editar Fornecedor' : 'Novo Fornecedor', handleSaveFornecedor, (
        <>
          <div><label className={labelClass}>Nome *</label><input value={formFornecedor.nome} onChange={e => setFormFornecedor({ ...formFornecedor, nome: e.target.value })} className={inputClass} /></div>
          <div><label className={labelClass}>Contato</label><input value={formFornecedor.contato} onChange={e => setFormFornecedor({ ...formFornecedor, contato: e.target.value })} className={inputClass} placeholder="Email, telefone, WeChat..." /></div>
          <div><label className={labelClass}>Localização</label><input value={formFornecedor.localizacao} onChange={e => setFormFornecedor({ ...formFornecedor, localizacao: e.target.value })} className={inputClass} placeholder="Cidade, região..." /></div>
          <div><label className={labelClass}>Observações</label><textarea value={formFornecedor.observacoes} onChange={e => setFormFornecedor({ ...formFornecedor, observacoes: e.target.value })} className={`${inputClass} h-16 resize-none`} /></div>
        </>
      ))}

      {renderModal(showEventoModal, () => { setShowEventoModal(false); setEditingEventoId(null); }, editingEventoId ? 'Editar Vínculo de Evento' : 'Vincular Evento', handleLinkEvento, (
        <>
          <div>
            <label className={labelClass}>Tipo de vínculo</label>
            <div className="flex gap-2 mb-3">
              <button type="button" onClick={() => { setEventoInputMode('select'); setFormEvento(f => ({ ...f, evento_nome_manual: '' })); }} className={`flex-1 px-3 py-2 rounded-lg text-sm font-medium transition-all ${eventoInputMode === 'select' ? 'bg-indigo-500 text-white' : isDark ? 'bg-gray-700 text-gray-300 hover:bg-gray-600' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'}`}>
                Evento cadastrado
              </button>
              <button type="button" onClick={() => { setEventoInputMode('free'); setFormEvento(f => ({ ...f, cadastro_evento_id: '' })); }} className={`flex-1 px-3 py-2 rounded-lg text-sm font-medium transition-all ${eventoInputMode === 'free' ? 'bg-indigo-500 text-white' : isDark ? 'bg-gray-700 text-gray-300 hover:bg-gray-600' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'}`}>
                Digitar manualmente
              </button>
            </div>
          </div>
          <div><label className={labelClass}>Evento *</label>
            {eventoInputMode === 'select' ? (
              <select value={formEvento.cadastro_evento_id} onChange={e => setFormEvento({ ...formEvento, cadastro_evento_id: e.target.value })} className={inputClass}>
                <option value="">Selecione um evento...</option>
                {eventos.map(e => <option key={e.id} value={e.id}>{e.nome}{e.ano_evento ? ` (${e.ano_evento})` : ''}</option>)}
              </select>
            ) : (
              <input value={formEvento.evento_nome_manual} onChange={e => setFormEvento({ ...formEvento, evento_nome_manual: e.target.value })} className={inputClass} placeholder="Digite o nome do evento..." />
            )}
          </div>
          <div><label className={labelClass}>Quantidade</label><input type="number" value={formEvento.quantidade} onChange={e => setFormEvento({ ...formEvento, quantidade: e.target.value })} className={inputClass} /></div>
          <div><label className={labelClass}>Observações</label><textarea value={formEvento.observacoes} onChange={e => setFormEvento({ ...formEvento, observacoes: e.target.value })} className={`${inputClass} h-16 resize-none`} /></div>
        </>
      ))}
    </div>
  );
};

export default CotacoesImportacao;
