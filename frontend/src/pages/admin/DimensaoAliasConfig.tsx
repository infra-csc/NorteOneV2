import React, { useState, useEffect, useCallback } from 'react';
import { useTheme } from '../../context/ThemeContext';
import { usePermissions } from '../../context/PermissionContext';
import api from '../../services/api';
import {
  Plus, Trash2, Save, FlaskConical, ChevronDown, ChevronUp,
  CheckCircle2, XCircle, Loader2, Info,
} from 'lucide-react';

interface Alias {
  id: number;
  dimensao: string;
  pattern: string;
  substituicao: string;
  is_regex: boolean;
  ordem: number;
  ativo: boolean;
  descricao: string | null;
  created_at: string;
  updated_at: string | null;
}

interface NewAlias {
  dimensao: string;
  pattern: string;
  substituicao: string;
  is_regex: boolean;
  ordem: number;
  ativo: boolean;
  descricao: string;
}

const DIMENSOES = [
  { key: 'kit', label: 'Kit' },
  { key: 'modalidade', label: 'Modalidade' },
  { key: 'pelotao', label: 'Pelotão' },
  { key: 'tamanho_camiseta', label: 'Tamanho Camiseta' },
  { key: 'produtos', label: 'Produtos' },
];

const BLANK: NewAlias = {
  dimensao: 'kit',
  pattern: '',
  substituicao: '',
  is_regex: false,
  ordem: 0,
  ativo: true,
  descricao: '',
};

const DimensaoAliasConfig: React.FC = () => {
  const { isDark } = useTheme();
  const { canEdit } = usePermissions();
  const canEditAlias = canEdit('admin_detalhe_alias');

  const bg = isDark ? 'bg-gray-900 text-gray-100' : 'bg-gray-50 text-gray-900';
  const card = isDark ? 'bg-gray-800 border-gray-700' : 'bg-white border-gray-200';
  const inputCls = isDark
    ? 'bg-gray-700 border-gray-600 text-gray-100 placeholder-gray-400 focus:border-blue-500'
    : 'bg-white border-gray-300 text-gray-900 placeholder-gray-400 focus:border-blue-500';
  const textSecondary = isDark ? 'text-gray-400' : 'text-gray-500';
  const rowHover = isDark ? 'hover:bg-gray-750' : 'hover:bg-gray-50';

  const [aliases, setAliases] = useState<Alias[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState<Record<number, boolean>>({});
  const [deleting, setDeleting] = useState<Record<number, boolean>>({});
  const [collapsedDims, setCollapsedDims] = useState<Set<string>>(new Set());

  const toggleDim = (key: string) =>
    setCollapsedDims(prev => {
      const next = new Set(prev);
      next.has(key) ? next.delete(key) : next.add(key);
      return next;
    });
  const [toast, setToast] = useState<{ msg: string; ok: boolean } | null>(null);

  // New alias form state
  const [newAlias, setNewAlias] = useState<NewAlias>({ ...BLANK });
  const [creating, setCreating] = useState(false);
  const [showForm, setShowForm] = useState(false);

  // Test pattern state
  const [testState, setTestState] = useState<Record<number, { sample: string; result: string | null; casou: boolean | null; erro: string | null; loading: boolean }>>({});
  const [newTest, setNewTest] = useState('');
  const [newTestResult, setNewTestResult] = useState<{ result: string; casou: boolean; erro?: string } | null>(null);
  const [newTestLoading, setNewTestLoading] = useState(false);

  const showToast = (msg: string, ok = true) => {
    setToast({ msg, ok });
    setTimeout(() => setToast(null), 3500);
  };

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get<Alias[]>('/detalhe-alias/');
      setAliases(data);
    } catch {
      showToast('Erro ao carregar padrões', false);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleCreate = async () => {
    if (!newAlias.pattern.trim() || !newAlias.substituicao.trim()) {
      showToast('Preencha padrão e substituição', false);
      return;
    }
    setCreating(true);
    try {
      const { data } = await api.post<Alias>('/detalhe-alias/', {
        ...newAlias,
        descricao: newAlias.descricao || null,
      });
      setAliases(prev => [...prev, data]);
      setNewAlias({ ...BLANK });
      setShowForm(false);
      showToast('Padrão criado');
    } catch (e: any) {
      const detail = e?.response?.data?.detail;
      showToast(typeof detail === 'string' ? detail : 'Erro ao criar padrão', false);
    } finally {
      setCreating(false);
    }
  };

  const handleSave = async (alias: Alias) => {
    setSaving(prev => ({ ...prev, [alias.id]: true }));
    try {
      const { data } = await api.put<Alias>(`/detalhe-alias/${alias.id}`, alias);
      setAliases(prev => prev.map(a => a.id === alias.id ? data : a));
      showToast('Padrão salvo');
    } catch (e: any) {
      const detail = e?.response?.data?.detail;
      showToast(typeof detail === 'string' ? detail : 'Erro ao salvar', false);
    } finally {
      setSaving(prev => ({ ...prev, [alias.id]: false }));
    }
  };

  const handleDelete = async (id: number) => {
    if (!confirm('Remover este padrão?')) return;
    setDeleting(prev => ({ ...prev, [id]: true }));
    try {
      await api.delete(`/detalhe-alias/${id}`);
      setAliases(prev => prev.filter(a => a.id !== id));
      showToast('Padrão removido');
    } catch {
      showToast('Erro ao remover', false);
    } finally {
      setDeleting(prev => ({ ...prev, [id]: false }));
    }
  };

  const updateAlias = (id: number, field: keyof Alias, value: unknown) => {
    setAliases(prev => prev.map(a => a.id === id ? { ...a, [field]: value } : a));
  };

  const handleTest = async (alias: Alias, sample: string) => {
    if (!sample.trim()) return;
    setTestState(prev => ({ ...prev, [alias.id]: { sample, result: null, casou: null, erro: null, loading: true } }));
    try {
      const { data } = await api.post('/detalhe-alias/test', {
        pattern: alias.pattern,
        substituicao: alias.substituicao,
        is_regex: alias.is_regex,
        sample,
      });
      setTestState(prev => ({ ...prev, [alias.id]: { sample, result: data.resultado, casou: data.casou, erro: data.erro || null, loading: false } }));
    } catch {
      setTestState(prev => ({ ...prev, [alias.id]: { sample, result: null, casou: null, erro: 'Erro ao testar', loading: false } }));
    }
  };

  const handleNewTest = async () => {
    if (!newTest.trim()) return;
    setNewTestLoading(true);
    setNewTestResult(null);
    try {
      const { data } = await api.post('/detalhe-alias/test', {
        pattern: newAlias.pattern,
        substituicao: newAlias.substituicao,
        is_regex: newAlias.is_regex,
        sample: newTest,
      });
      setNewTestResult({ result: data.resultado, casou: data.casou, erro: data.erro });
    } catch {
      setNewTestResult({ result: '', casou: false, erro: 'Erro ao testar' });
    } finally {
      setNewTestLoading(false);
    }
  };

  const grouped = DIMENSOES.map(d => ({
    ...d,
    items: aliases.filter(a => a.dimensao === d.key).sort((x, y) => x.ordem - y.ordem),
  }));

  return (
    <div className="relative">
      {/* Toast */}
      {toast && (
        <div className={`fixed bottom-6 right-6 z-50 flex items-center gap-2 px-4 py-3 rounded-xl shadow-lg text-sm font-medium transition-all ${
          toast.ok
            ? isDark ? 'bg-emerald-700 text-white' : 'bg-emerald-500 text-white'
            : isDark ? 'bg-red-700 text-white' : 'bg-red-500 text-white'
        }`}>
          {toast.ok ? <CheckCircle2 className="w-4 h-4" /> : <XCircle className="w-4 h-4" />}
          {toast.msg}
        </div>
      )}

      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-lg font-semibold">Padrões de Dimensão</h2>
          <p className={`text-sm mt-0.5 ${textSecondary}`}>
            Renomeie ou agrupe valores brutos de kit, modalidade, pelotão, tamanho e produtos no Detalhamento.
            As regras são aplicadas em ordem dentro de cada dimensão — a primeira que casar é usada.
          </p>
        </div>
        {canEditAlias && (
          <button
            onClick={() => setShowForm(v => !v)}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              isDark ? 'bg-blue-600 hover:bg-blue-500 text-white' : 'bg-blue-500 hover:bg-blue-600 text-white'
            }`}
          >
            <Plus className="w-4 h-4" />
            Novo Padrão
          </button>
        )}
      </div>

      {/* Info box */}
      <div className={`flex gap-3 p-3 rounded-lg border mb-5 text-sm ${isDark ? 'bg-blue-900/30 border-blue-700 text-blue-300' : 'bg-blue-50 border-blue-200 text-blue-700'}`}>
        <Info className="w-4 h-4 mt-0.5 flex-shrink-0" />
        <div>
          <strong>Tipo Exato:</strong> compara o valor inteiro (sem distinção de maiúsculas/minúsculas).{' '}
          <strong>Regex:</strong> aceita expressões regulares com grupos de captura <code className="text-xs bg-black/10 px-1 rounded">\1</code>,{' '}
          flag <code className="text-xs bg-black/10 px-1 rounded">(?i)</code> para ignorar maiúsculas.
          Use o botão <FlaskConical className="w-3 h-3 inline" /> para testar antes de salvar.
        </div>
      </div>

      {/* New alias form */}
      {showForm && canEditAlias && (
        <div className={`border rounded-xl p-4 mb-6 ${card}`}>
          <h3 className="text-sm font-semibold mb-3">Novo Padrão</h3>
          <div className="grid grid-cols-2 gap-3 mb-3">
            <div>
              <label className={`block text-xs font-medium mb-1 ${textSecondary}`}>Dimensão</label>
              <select
                value={newAlias.dimensao}
                onChange={e => setNewAlias(p => ({ ...p, dimensao: e.target.value }))}
                className={`w-full text-sm border rounded-lg px-3 py-2 outline-none ${inputCls}`}
              >
                {DIMENSOES.map(d => <option key={d.key} value={d.key}>{d.label}</option>)}
              </select>
            </div>
            <div>
              <label className={`block text-xs font-medium mb-1 ${textSecondary}`}>Ordem</label>
              <input
                type="number"
                value={newAlias.ordem}
                onChange={e => setNewAlias(p => ({ ...p, ordem: Number(e.target.value) }))}
                className={`w-full text-sm border rounded-lg px-3 py-2 outline-none ${inputCls}`}
              />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3 mb-3">
            <div>
              <label className={`block text-xs font-medium mb-1 ${textSecondary}`}>
                Padrão{' '}
                <span className={`font-normal ${textSecondary}`}>
                  {newAlias.is_regex ? '(regex)' : '(texto exato)'}
                </span>
              </label>
              <input
                value={newAlias.pattern}
                onChange={e => setNewAlias(p => ({ ...p, pattern: e.target.value }))}
                placeholder={newAlias.is_regex ? 'ex: (?i)^desconto.*-\\s*[\\d,]+$' : 'ex: MASCULINO 5KM'}
                className={`w-full text-sm border rounded-lg px-3 py-2 outline-none font-mono ${inputCls}`}
              />
            </div>
            <div>
              <label className={`block text-xs font-medium mb-1 ${textSecondary}`}>Substituição</label>
              <input
                value={newAlias.substituicao}
                onChange={e => setNewAlias(p => ({ ...p, substituicao: e.target.value }))}
                placeholder="ex: Masc 5km"
                className={`w-full text-sm border rounded-lg px-3 py-2 outline-none ${inputCls}`}
              />
            </div>
          </div>
          <div className="mb-3">
            <label className={`block text-xs font-medium mb-1 ${textSecondary}`}>Descrição (opcional)</label>
            <input
              value={newAlias.descricao}
              onChange={e => setNewAlias(p => ({ ...p, descricao: e.target.value }))}
              placeholder="Explique o objetivo deste padrão"
              className={`w-full text-sm border rounded-lg px-3 py-2 outline-none ${inputCls}`}
            />
          </div>
          <div className="flex items-center gap-4 mb-4">
            <label className="flex items-center gap-2 cursor-pointer text-sm">
              <input
                type="checkbox"
                checked={newAlias.is_regex}
                onChange={e => setNewAlias(p => ({ ...p, is_regex: e.target.checked }))}
                className="rounded"
              />
              Usar Regex
            </label>
            <label className="flex items-center gap-2 cursor-pointer text-sm">
              <input
                type="checkbox"
                checked={newAlias.ativo}
                onChange={e => setNewAlias(p => ({ ...p, ativo: e.target.checked }))}
                className="rounded"
              />
              Ativo
            </label>
          </div>
          {/* Test area for new alias */}
          <div className={`flex gap-2 items-center mb-4 p-3 rounded-lg ${isDark ? 'bg-gray-700/50' : 'bg-gray-50'}`}>
            <FlaskConical className={`w-4 h-4 flex-shrink-0 ${textSecondary}`} />
            <input
              value={newTest}
              onChange={e => setNewTest(e.target.value)}
              placeholder="Digite um valor para testar o padrão"
              className={`flex-1 text-sm border rounded-lg px-3 py-1.5 outline-none ${inputCls}`}
              onKeyDown={e => e.key === 'Enter' && handleNewTest()}
            />
            <button
              onClick={handleNewTest}
              disabled={newTestLoading || !newTest.trim()}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium ${isDark ? 'bg-gray-600 hover:bg-gray-500 text-white' : 'bg-gray-200 hover:bg-gray-300 text-gray-700'} disabled:opacity-50`}
            >
              {newTestLoading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : 'Testar'}
            </button>
            {newTestResult && (
              <span className={`text-xs px-2 py-1 rounded-md font-medium ${newTestResult.erro ? 'bg-red-100 text-red-600' : newTestResult.casou ? 'bg-emerald-100 text-emerald-700' : 'bg-yellow-100 text-yellow-700'}`}>
                {newTestResult.erro ? `Erro: ${newTestResult.erro}` : newTestResult.casou ? `→ "${newTestResult.result}"` : 'Não casou'}
              </span>
            )}
          </div>
          <div className="flex justify-end gap-2">
            <button
              onClick={() => { setShowForm(false); setNewAlias({ ...BLANK }); setNewTestResult(null); }}
              className={`px-4 py-2 rounded-lg text-sm ${isDark ? 'text-gray-300 hover:bg-gray-700' : 'text-gray-600 hover:bg-gray-100'}`}
            >
              Cancelar
            </button>
            <button
              onClick={handleCreate}
              disabled={creating}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium text-white ${isDark ? 'bg-emerald-600 hover:bg-emerald-500' : 'bg-emerald-500 hover:bg-emerald-600'} disabled:opacity-50`}
            >
              {creating ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
              Criar Padrão
            </button>
          </div>
        </div>
      )}

      {loading ? (
        <div className="flex justify-center py-16">
          <Loader2 className={`w-6 h-6 animate-spin ${textSecondary}`} />
        </div>
      ) : (
        <div className="space-y-4">
          {grouped.map(group => {
            const isCollapsed = collapsedDims.has(group.key);
            return (
            <div key={group.key} className={`border rounded-xl overflow-hidden ${card}`}>
              <button
                onClick={() => toggleDim(group.key)}
                className={`w-full flex items-center justify-between px-4 py-3 transition-colors text-left ${
                  isDark
                    ? 'bg-gray-750 hover:bg-gray-700' + (isCollapsed ? '' : ' border-b border-gray-700')
                    : 'bg-gray-50 hover:bg-gray-100' + (isCollapsed ? '' : ' border-b border-gray-200')
                }`}
              >
                <div className="flex items-center gap-2">
                  {isCollapsed
                    ? <ChevronDown className={`w-4 h-4 ${textSecondary}`} />
                    : <ChevronUp className={`w-4 h-4 ${textSecondary}`} />}
                  <span className="font-semibold text-sm">{group.label}</span>
                </div>
                <span className={`text-xs ${textSecondary}`}>
                  {group.items.length} {group.items.length === 1 ? 'padrão' : 'padrões'}
                </span>
              </button>
              {!isCollapsed && group.items.length === 0 && (
                <p className={`text-sm px-4 py-4 ${textSecondary}`}>Nenhum padrão configurado para esta dimensão.</p>
              )}
              {!isCollapsed && group.items.length > 0 && (
                <table className="w-full text-sm">
                  <thead>
                    <tr className={`text-xs ${textSecondary} ${isDark ? 'bg-gray-800' : 'bg-gray-50'}`}>
                      <th className="text-left px-4 py-2 font-medium w-8">Ord.</th>
                      <th className="text-left px-4 py-2 font-medium">Padrão</th>
                      <th className="text-left px-4 py-2 font-medium">Substituição</th>
                      <th className="text-left px-4 py-2 font-medium w-20">Tipo</th>
                      <th className="text-left px-4 py-2 font-medium w-16">Ativo</th>
                      <th className="text-left px-4 py-2 font-medium">Descrição</th>
                      <th className="text-right px-4 py-2 font-medium w-32">Ações</th>
                    </tr>
                  </thead>
                  <tbody className={`divide-y ${isDark ? 'divide-gray-700' : 'divide-gray-100'}`}>
                    {group.items.map(alias => {
                      const ts = testState[alias.id];
                      return (
                        <React.Fragment key={alias.id}>
                          <tr className={`${rowHover} transition-colors`}>
                            <td className="px-4 py-2">
                              <input
                                type="number"
                                value={alias.ordem}
                                onChange={e => updateAlias(alias.id, 'ordem', Number(e.target.value))}
                                disabled={!canEditAlias}
                                className={`w-14 text-sm border rounded px-2 py-1 outline-none ${inputCls} disabled:opacity-60`}
                              />
                            </td>
                            <td className="px-4 py-2">
                              <input
                                value={alias.pattern}
                                onChange={e => updateAlias(alias.id, 'pattern', e.target.value)}
                                disabled={!canEditAlias}
                                className={`w-full text-sm border rounded-lg px-2 py-1 outline-none font-mono ${inputCls} disabled:opacity-60`}
                              />
                            </td>
                            <td className="px-4 py-2">
                              <input
                                value={alias.substituicao}
                                onChange={e => updateAlias(alias.id, 'substituicao', e.target.value)}
                                disabled={!canEditAlias}
                                className={`w-full text-sm border rounded-lg px-2 py-1 outline-none ${inputCls} disabled:opacity-60`}
                              />
                            </td>
                            <td className="px-4 py-2">
                              <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${alias.is_regex ? 'bg-purple-100 text-purple-700' : 'bg-gray-100 text-gray-600'}`}>
                                {alias.is_regex ? 'Regex' : 'Exato'}
                              </span>
                            </td>
                            <td className="px-4 py-2">
                              <input
                                type="checkbox"
                                checked={alias.ativo}
                                onChange={e => updateAlias(alias.id, 'ativo', e.target.checked)}
                                disabled={!canEditAlias}
                                className="rounded"
                              />
                            </td>
                            <td className="px-4 py-2">
                              <span className={`text-xs ${textSecondary}`}>{alias.descricao || '—'}</span>
                            </td>
                            <td className="px-4 py-2">
                              <div className="flex items-center justify-end gap-1">
                                {canEditAlias && (
                                  <>
                                    <button
                                      onClick={() => {
                                        const sample = ts?.sample || '';
                                        const next = prompt('Valor para testar:', sample) || '';
                                        if (next) handleTest(alias, next);
                                      }}
                                      title="Testar padrão"
                                      className={`p-1.5 rounded-lg transition-colors ${isDark ? 'hover:bg-gray-600' : 'hover:bg-gray-100'}`}
                                    >
                                      {ts?.loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <FlaskConical className={`w-3.5 h-3.5 ${textSecondary}`} />}
                                    </button>
                                    <button
                                      onClick={() => handleSave(alias)}
                                      disabled={saving[alias.id]}
                                      title="Salvar"
                                      className={`p-1.5 rounded-lg transition-colors ${isDark ? 'hover:bg-emerald-700' : 'hover:bg-emerald-100'}`}
                                    >
                                      {saving[alias.id] ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className={`w-3.5 h-3.5 ${isDark ? 'text-emerald-400' : 'text-emerald-600'}`} />}
                                    </button>
                                    <button
                                      onClick={() => handleDelete(alias.id)}
                                      disabled={deleting[alias.id]}
                                      title="Remover"
                                      className={`p-1.5 rounded-lg transition-colors ${isDark ? 'hover:bg-red-800' : 'hover:bg-red-100'}`}
                                    >
                                      {deleting[alias.id] ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Trash2 className={`w-3.5 h-3.5 ${isDark ? 'text-red-400' : 'text-red-500'}`} />}
                                    </button>
                                  </>
                                )}
                              </div>
                            </td>
                          </tr>
                          {ts && !ts.loading && (
                            <tr className={isDark ? 'bg-gray-850' : 'bg-gray-50'}>
                              <td colSpan={7} className="px-4 py-2">
                                <div className="flex items-center gap-3 text-xs">
                                  <span className={textSecondary}>Teste: <code className="font-mono">"{ts.sample}"</code></span>
                                  {ts.erro ? (
                                    <span className="text-red-500">Erro: {ts.erro}</span>
                                  ) : ts.casou ? (
                                    <span className="text-emerald-600 font-medium">→ "{ts.result}"</span>
                                  ) : (
                                    <span className="text-yellow-600">Não casou</span>
                                  )}
                                </div>
                              </td>
                            </tr>
                          )}
                        </React.Fragment>
                      );
                    })}
                  </tbody>
                </table>
              )}
            </div>
          ); })}
        </div>
      )}
    </div>
  );
};

export default DimensaoAliasConfig;
