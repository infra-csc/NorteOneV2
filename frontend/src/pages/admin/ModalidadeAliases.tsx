import React, { useEffect, useState } from 'react';
import { useTheme } from '../../context/ThemeContext';
import api from '../../services/api';
import {
  ArrowRight, Plus, Edit2, Trash2, RefreshCw,
  AlertTriangle, CheckCircle, X, Search, Info,
} from 'lucide-react';

interface Alias {
  id: number;
  raw_value: string;
  canonical_value: string;
  created_at: string | null;
  updated_at: string | null;
}

interface FormState {
  raw_value: string;
  canonical_value: string;
}

const EMPTY_FORM: FormState = { raw_value: '', canonical_value: '' };

export default function ModalidadeAliases() {
  const { isDark } = useTheme();

  const [aliases, setAliases] = useState<Alias[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const [search, setSearch] = useState('');
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [showForm, setShowForm] = useState(false);

  const card = isDark ? 'bg-gray-800 border-gray-700' : 'bg-white border-gray-200';
  const text = isDark ? 'text-gray-100' : 'text-gray-900';
  const subtext = isDark ? 'text-gray-400' : 'text-gray-500';
  const inputCls = `w-full px-3 py-2 rounded-lg border text-sm ${isDark ? 'bg-gray-700 border-gray-600 text-gray-100 placeholder-gray-400' : 'bg-white border-gray-300 text-gray-900 placeholder-gray-400'} focus:outline-none focus:ring-2 focus:ring-blue-500`;
  const rowHover = isDark ? 'hover:bg-gray-700/60' : 'hover:bg-gray-50';

  async function fetchAliases() {
    setLoading(true);
    setError(null);
    try {
      const { data } = await api.get('/api/admin/modalidade-aliases');
      setAliases(data);
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Erro ao carregar aliases.');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { fetchAliases(); }, []);

  function flash(msg: string) {
    setSuccess(msg);
    setTimeout(() => setSuccess(null), 3500);
  }

  function openCreate() {
    setEditingId(null);
    setForm(EMPTY_FORM);
    setShowForm(true);
  }

  function openEdit(alias: Alias) {
    setEditingId(alias.id);
    setForm({ raw_value: alias.raw_value, canonical_value: alias.canonical_value });
    setShowForm(true);
  }

  function cancelForm() {
    setShowForm(false);
    setEditingId(null);
    setForm(EMPTY_FORM);
  }

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    if (!form.raw_value.trim() || !form.canonical_value.trim()) return;
    setSaving(true);
    setError(null);
    try {
      if (editingId !== null) {
        await api.put(`/api/admin/modalidade-aliases/${editingId}`, form);
        flash('Alias atualizado com sucesso.');
      } else {
        await api.post('/api/admin/modalidade-aliases', form);
        flash('Alias criado com sucesso.');
      }
      cancelForm();
      await fetchAliases();
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Erro ao salvar alias.');
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(id: number, raw: string) {
    if (!window.confirm(`Remover alias para "${raw}"?`)) return;
    setDeletingId(id);
    setError(null);
    try {
      await api.delete(`/api/admin/modalidade-aliases/${id}`);
      flash('Alias removido.');
      await fetchAliases();
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Erro ao remover alias.');
    } finally {
      setDeletingId(null);
    }
  }

  const filtered = aliases.filter(a =>
    a.raw_value.toLowerCase().includes(search.toLowerCase()) ||
    a.canonical_value.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className={`text-2xl font-bold ${text}`}>Aliases de Modalidade</h1>
          <p className={`mt-1 text-sm ${subtext}`}>
            Mapeie valores brutos de modalidade (vindos do Ativo/Magento) para um nome canônico unificado.
            A normalização automática por regex já trata padrões numéricos (5K, 5km, 5 Km → 5km);
            os aliases permitem cobrir casos irregulares manualmente.
          </p>
        </div>
        <button
          onClick={openCreate}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium rounded-lg transition-colors"
        >
          <Plus className="w-4 h-4" /> Novo alias
        </button>
      </div>

      {/* Info box */}
      <div className={`flex gap-3 p-4 rounded-lg border ${isDark ? 'bg-blue-900/20 border-blue-800 text-blue-300' : 'bg-blue-50 border-blue-200 text-blue-700'} text-sm`}>
        <Info className="w-4 h-4 mt-0.5 shrink-0" />
        <div>
          <span className="font-semibold">Como funciona a normalização:</span>{' '}
          Primeiro, a regex transforma "5K", "5Km", "5 km" → "5km". Depois, o alias
          é consultado duas vezes — antes da regex (valor bruto) e depois (valor já normalizado).
          Aliases têm prioridade sobre a regex.
        </div>
      </div>

      {/* Toasts */}
      {error && (
        <div className="flex items-center gap-2 p-3 rounded-lg bg-red-500/10 border border-red-500/30 text-red-500 text-sm">
          <AlertTriangle className="w-4 h-4 shrink-0" />
          <span>{error}</span>
          <button className="ml-auto" onClick={() => setError(null)}><X className="w-4 h-4" /></button>
        </div>
      )}
      {success && (
        <div className="flex items-center gap-2 p-3 rounded-lg bg-green-500/10 border border-green-500/30 text-green-500 text-sm">
          <CheckCircle className="w-4 h-4 shrink-0" />
          <span>{success}</span>
        </div>
      )}

      {/* Form modal */}
      {showForm && (
        <div className={`rounded-xl border p-5 ${card} shadow-md`}>
          <h2 className={`text-base font-semibold mb-4 ${text}`}>
            {editingId !== null ? 'Editar alias' : 'Novo alias'}
          </h2>
          <form onSubmit={handleSave} className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className={`block text-xs font-medium mb-1 ${subtext}`}>Valor bruto (raw)</label>
                <input
                  className={inputCls}
                  placeholder="ex: 5Km, corridinha kid"
                  value={form.raw_value}
                  onChange={e => setForm(f => ({ ...f, raw_value: e.target.value }))}
                  required
                  disabled={saving}
                />
                <p className={`mt-1 text-xs ${subtext}`}>Texto exato que vem do Ativo/Magento.</p>
              </div>
              <div>
                <label className={`block text-xs font-medium mb-1 ${subtext}`}>Valor canônico</label>
                <input
                  className={inputCls}
                  placeholder="ex: 5km, corridinha"
                  value={form.canonical_value}
                  onChange={e => setForm(f => ({ ...f, canonical_value: e.target.value }))}
                  required
                  disabled={saving}
                />
                <p className={`mt-1 text-xs ${subtext}`}>Nome padronizado que aparecerá no sistema.</p>
              </div>
            </div>
            {form.raw_value && form.canonical_value && (
              <div className={`flex items-center gap-2 text-sm px-3 py-2 rounded-lg ${isDark ? 'bg-gray-700' : 'bg-gray-50'}`}>
                <span className={`font-mono ${isDark ? 'text-yellow-300' : 'text-yellow-700'}`}>{form.raw_value.trim()}</span>
                <ArrowRight className={`w-4 h-4 ${subtext}`} />
                <span className={`font-mono font-semibold ${isDark ? 'text-green-300' : 'text-green-700'}`}>{form.canonical_value.trim()}</span>
              </div>
            )}
            <div className="flex items-center gap-3 pt-1">
              <button
                type="submit"
                disabled={saving || !form.raw_value.trim() || !form.canonical_value.trim()}
                className="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-sm font-medium rounded-lg transition-colors"
              >
                {saving ? 'Salvando…' : 'Salvar'}
              </button>
              <button
                type="button"
                onClick={cancelForm}
                disabled={saving}
                className={`px-4 py-2 text-sm rounded-lg border transition-colors ${isDark ? 'border-gray-600 text-gray-300 hover:bg-gray-700' : 'border-gray-300 text-gray-600 hover:bg-gray-50'}`}
              >
                Cancelar
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Lista */}
      <div className={`rounded-xl border ${card} shadow-sm overflow-hidden`}>
        {/* Toolbar */}
        <div className={`flex items-center gap-3 px-4 py-3 border-b ${isDark ? 'border-gray-700' : 'border-gray-200'}`}>
          <div className="relative flex-1 max-w-xs">
            <Search className={`absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 ${subtext}`} />
            <input
              className={`${inputCls} pl-9`}
              placeholder="Buscar alias…"
              value={search}
              onChange={e => setSearch(e.target.value)}
            />
          </div>
          <span className={`text-xs ${subtext}`}>{filtered.length} alias{filtered.length !== 1 ? 'es' : ''}</span>
          <button
            onClick={fetchAliases}
            disabled={loading}
            className={`p-2 rounded-lg transition-colors ${isDark ? 'hover:bg-gray-700' : 'hover:bg-gray-100'}`}
            title="Recarregar"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''} ${subtext}`} />
          </button>
        </div>

        {/* Table */}
        {loading ? (
          <div className="flex items-center justify-center py-16">
            <RefreshCw className="w-6 h-6 animate-spin text-blue-500" />
          </div>
        ) : filtered.length === 0 ? (
          <div className={`text-center py-16 ${subtext} text-sm`}>
            {search ? 'Nenhum alias encontrado para esta busca.' : 'Nenhum alias cadastrado ainda. Clique em "Novo alias" para começar.'}
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className={isDark ? 'bg-gray-700/50 text-gray-400' : 'bg-gray-50 text-gray-500'}>
                <th className="px-4 py-3 text-left font-medium text-xs uppercase tracking-wider">Valor bruto</th>
                <th className="px-4 py-3 text-left font-medium text-xs uppercase tracking-wider w-8"></th>
                <th className="px-4 py-3 text-left font-medium text-xs uppercase tracking-wider">Canônico</th>
                <th className="px-4 py-3 text-right font-medium text-xs uppercase tracking-wider w-24">Ações</th>
              </tr>
            </thead>
            <tbody className={`divide-y ${isDark ? 'divide-gray-700' : 'divide-gray-100'}`}>
              {filtered.map(alias => (
                <tr key={alias.id} className={`transition-colors ${rowHover}`}>
                  <td className="px-4 py-3">
                    <span className={`font-mono text-xs px-2 py-1 rounded ${isDark ? 'bg-yellow-900/30 text-yellow-300' : 'bg-yellow-50 text-yellow-800'}`}>
                      {alias.raw_value}
                    </span>
                  </td>
                  <td className="px-2 py-3 text-center">
                    <ArrowRight className={`w-4 h-4 ${subtext}`} />
                  </td>
                  <td className="px-4 py-3">
                    <span className={`font-mono text-xs font-semibold px-2 py-1 rounded ${isDark ? 'bg-green-900/30 text-green-300' : 'bg-green-50 text-green-700'}`}>
                      {alias.canonical_value}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center justify-end gap-1">
                      <button
                        onClick={() => openEdit(alias)}
                        className={`p-1.5 rounded-lg transition-colors ${isDark ? 'hover:bg-gray-600 text-gray-400 hover:text-gray-200' : 'hover:bg-gray-100 text-gray-400 hover:text-gray-700'}`}
                        title="Editar"
                      >
                        <Edit2 className="w-3.5 h-3.5" />
                      </button>
                      <button
                        onClick={() => handleDelete(alias.id, alias.raw_value)}
                        disabled={deletingId === alias.id}
                        className={`p-1.5 rounded-lg transition-colors ${isDark ? 'hover:bg-red-900/40 text-gray-400 hover:text-red-400' : 'hover:bg-red-50 text-gray-400 hover:text-red-600'}`}
                        title="Remover"
                      >
                        {deletingId === alias.id
                          ? <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                          : <Trash2 className="w-3.5 h-3.5" />}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
