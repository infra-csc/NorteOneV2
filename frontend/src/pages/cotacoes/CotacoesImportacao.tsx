import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useTheme } from '../../context/ThemeContext';
import api from '../../services/api';
import {
  Plus, Edit2, Trash2, X, Search, RefreshCw,
  DollarSign, Package, AlertCircle, Save, ChevronDown, TrendingUp
} from 'lucide-react';

interface CotacaoFob {
  id: number;
  circuito: string;
  produto: string;
  valor_fob: number;
  indice_importacao?: number | null;
  bec?: number | null;
  cotacao_cambio?: number | null;
  valor_nacionalizado?: number | null;
  taxa_cambio?: number | null;
  valor_brl?: number | null;
  created_at?: string;
  updated_at?: string;
}

interface ComboboxProps {
  value: string;
  onChange: (val: string) => void;
  options: string[];
  placeholder: string;
  isDark: boolean;
}

const Combobox: React.FC<ComboboxProps> = ({ value, onChange, options, placeholder, isDark }) => {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState('');
  const ref = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const filtered = options.filter(o => o.toLowerCase().includes((search || value).toLowerCase()));
  const showAdd = (search || value).trim() && !options.some(o => o.toLowerCase() === (search || value).trim().toLowerCase());

  return (
    <div ref={ref} className="relative">
      <div className="relative">
        <input
          ref={inputRef}
          value={open ? search : value}
          onChange={e => {
            setSearch(e.target.value);
            if (!open) setOpen(true);
          }}
          onFocus={() => {
            setSearch(value);
            setOpen(true);
          }}
          placeholder={placeholder}
          className={`w-full px-3 py-2 pr-8 rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white' : 'bg-white border-gray-300 text-gray-900'} focus:ring-2 focus:ring-purple-500 focus:border-transparent outline-none text-sm`}
        />
        <ChevronDown className={`absolute right-2.5 top-1/2 -translate-y-1/2 w-4 h-4 ${isDark ? 'text-gray-500' : 'text-gray-400'} pointer-events-none`} />
      </div>
      {open && (
        <div className={`absolute z-50 w-full mt-1 max-h-48 overflow-y-auto rounded-lg border shadow-lg ${isDark ? 'bg-gray-700 border-gray-600' : 'bg-white border-gray-200'}`}>
          {filtered.map(o => (
            <button
              key={o}
              type="button"
              onClick={() => { onChange(o); setSearch(''); setOpen(false); }}
              className={`w-full text-left px-3 py-2 text-sm ${isDark ? 'hover:bg-gray-600 text-gray-200' : 'hover:bg-gray-100 text-gray-800'} ${o === value ? (isDark ? 'bg-purple-900/30 text-purple-300' : 'bg-purple-50 text-purple-700') : ''}`}
            >
              {o}
            </button>
          ))}
          {showAdd && (
            <button
              type="button"
              onClick={() => {
                const val = (search || value).trim();
                onChange(val);
                setSearch('');
                setOpen(false);
              }}
              className={`w-full text-left px-3 py-2 text-sm font-medium ${isDark ? 'text-purple-400 hover:bg-gray-600' : 'text-purple-600 hover:bg-purple-50'} flex items-center gap-2 border-t ${isDark ? 'border-gray-600' : 'border-gray-200'}`}
            >
              <Plus className="w-3.5 h-3.5" /> Adicionar "{(search || value).trim()}"
            </button>
          )}
          {filtered.length === 0 && !showAdd && (
            <div className={`px-3 py-2 text-sm ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>Nenhuma opção</div>
          )}
        </div>
      )}
    </div>
  );
};

const CotacoesImportacao: React.FC = () => {
  const { isDark } = useTheme();
  const [items, setItems] = useState<CotacaoFob[]>([]);
  const [circuitos, setCircuitos] = useState<string[]>([]);
  const [produtos, setProdutos] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [searchText, setSearchText] = useState('');

  const [showModal, setShowModal] = useState(false);
  const [editingItem, setEditingItem] = useState<CotacaoFob | null>(null);
  const [formCircuito, setFormCircuito] = useState('');
  const [formProduto, setFormProduto] = useState('');
  const [formValorFob, setFormValorFob] = useState('');
  const [formIndice, setFormIndice] = useState('');
  const [formBec, setFormBec] = useState('');
  const [formCotacao, setFormCotacao] = useState('');

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [itemsRes, circRes, prodRes] = await Promise.all([
        api.get('/cotacoes/fob'),
        api.get('/cotacoes/fob/circuitos'),
        api.get('/cotacoes/fob/produtos'),
      ]);
      setItems(itemsRes.data);
      setCircuitos(circRes.data);
      setProdutos(prodRes.data);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Erro ao carregar dados');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  const openNew = () => {
    setEditingItem(null);
    setFormCircuito('');
    setFormProduto('');
    setFormValorFob('');
    setFormIndice('');
    setFormBec('');
    setFormCotacao('');
    setShowModal(true);
  };

  const openEdit = (item: CotacaoFob) => {
    setEditingItem(item);
    setFormCircuito(item.circuito);
    setFormProduto(item.produto);
    setFormValorFob(item.valor_fob.toString());
    setFormIndice(item.indice_importacao != null ? item.indice_importacao.toString() : '');
    setFormBec(item.bec != null ? item.bec.toString() : '');
    setFormCotacao(item.cotacao_cambio != null ? item.cotacao_cambio.toString() : '');
    setShowModal(true);
  };

  const calcNacionalizado = (fob: number, indice: number, becPercent: number, cotacao: number): number => {
    const becDecimal = becPercent / 100;
    return fob * indice * cotacao + (becDecimal * fob * cotacao);
  };

  const handleSave = async () => {
    if (!formCircuito.trim()) { setError('Informe o circuito'); return; }
    if (!formProduto.trim()) { setError('Informe o produto'); return; }
    if (!formValorFob || isNaN(Number(formValorFob))) { setError('Informe o valor FOB'); return; }

    setSaving(true);
    try {
      const valorFob = Number(formValorFob);
      const indice = formIndice ? Number(formIndice) : null;
      const bec = formBec ? Number(formBec) : null;
      const cotacao = formCotacao ? Number(formCotacao) : null;

      let valorNac: number | null = null;
      let valorBrl: number | null = null;
      if (indice !== null && bec !== null && cotacao && valorFob) {
        valorNac = round(calcNacionalizado(valorFob, indice, bec, cotacao), 4);
      }
      if (cotacao && valorFob) {
        valorBrl = round(valorFob * cotacao, 2);
      }

      const payload = {
        circuito: formCircuito.trim(),
        produto: formProduto.trim(),
        valor_fob: valorFob,
        indice_importacao: indice,
        bec: bec,
        cotacao_cambio: cotacao,
        valor_nacionalizado: valorNac,
        taxa_cambio: cotacao,
        valor_brl: valorBrl,
      };
      if (editingItem) {
        await api.put(`/cotacoes/fob/${editingItem.id}`, payload);
      } else {
        await api.post('/cotacoes/fob', payload);
      }
      setShowModal(false);
      loadData();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Erro ao salvar');
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id: number) => {
    if (!confirm('Excluir esta cotação FOB?')) return;
    try {
      await api.delete(`/cotacoes/fob/${id}`);
      loadData();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Erro ao excluir');
    }
  };

  const round = (v: number, d: number) => Math.round(v * Math.pow(10, d)) / Math.pow(10, d);
  const fmt = (v: number) => v.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const fmtDec = (v: number, digits = 4) => v.toLocaleString('pt-BR', { minimumFractionDigits: digits, maximumFractionDigits: digits });

  const previewNac = (() => {
    const fob = Number(formValorFob);
    const indice = Number(formIndice);
    const bec = Number(formBec);
    const cotacao = Number(formCotacao);
    if (fob && !isNaN(indice) && formIndice !== '' && !isNaN(bec) && formBec !== '' && cotacao) {
      return round(calcNacionalizado(fob, indice, bec, cotacao), 2);
    }
    return null;
  })();

  const previewBrl = (() => {
    const fob = Number(formValorFob);
    const cotacao = Number(formCotacao);
    if (fob && cotacao) return round(fob * cotacao, 2);
    return null;
  })();

  const filtered = items.filter(item => {
    if (!searchText) return true;
    const s = searchText.toLowerCase();
    return item.circuito.toLowerCase().includes(s) || item.produto.toLowerCase().includes(s);
  });

  const grouped = filtered.reduce<Record<string, CotacaoFob[]>>((acc, item) => {
    if (!acc[item.circuito]) acc[item.circuito] = [];
    acc[item.circuito].push(item);
    return acc;
  }, {});

  const cardClass = `rounded-2xl p-5 ${isDark ? 'bg-gray-800/60 border border-gray-700/50' : 'bg-white border border-gray-200'} shadow-sm`;
  const inputClass = `w-full px-3 py-2 rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white' : 'bg-white border-gray-300 text-gray-900'} focus:ring-2 focus:ring-purple-500 focus:border-transparent outline-none text-sm`;
  const labelClass = `block text-xs font-medium mb-1.5 ${isDark ? 'text-gray-400' : 'text-gray-600'}`;

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className={`text-2xl font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>Cotação & Importação</h1>
          <p className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Registro de valores FOB por circuito e produto</p>
        </div>
        <div className="flex items-center gap-3">
          <button onClick={() => { loadData(); }} className={`p-2 rounded-lg ${isDark ? 'hover:bg-gray-700 text-gray-400' : 'hover:bg-gray-100 text-gray-500'}`}>
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
          <button onClick={openNew} className="flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-purple-500 to-pink-500 text-white rounded-xl text-sm font-medium hover:opacity-90 transition-opacity">
            <Plus className="w-4 h-4" /> Nova Cotação
          </button>
        </div>
      </div>

      <div className="relative">
        <Search className={`absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 ${isDark ? 'text-gray-500' : 'text-gray-400'}`} />
        <input
          value={searchText}
          onChange={e => setSearchText(e.target.value)}
          placeholder="Buscar por circuito ou produto..."
          className={`${inputClass} pl-9 max-w-md`}
        />
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
      ) : filtered.length === 0 ? (
        <div className={`${cardClass} text-center py-12`}>
          <Package className={`w-12 h-12 mx-auto mb-3 ${isDark ? 'text-gray-600' : 'text-gray-400'}`} />
          <p className={`${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
            {searchText ? 'Nenhuma cotação encontrada para essa busca' : 'Nenhuma cotação FOB registrada'}
          </p>
          {!searchText && (
            <button onClick={openNew} className="mt-4 px-4 py-2 bg-gradient-to-r from-purple-500 to-pink-500 text-white rounded-xl text-sm font-medium hover:opacity-90">
              <Plus className="w-4 h-4 inline mr-1" /> Adicionar primeira cotação
            </button>
          )}
        </div>
      ) : (
        <div className="space-y-4">
          {Object.entries(grouped).map(([circuito, cotacoes]) => (
            <div key={circuito} className={cardClass}>
              <div className="flex items-center gap-2 mb-4">
                <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-purple-500 to-pink-500 flex items-center justify-center">
                  <Package className="w-4 h-4 text-white" />
                </div>
                <h3 className={`font-semibold ${isDark ? 'text-white' : 'text-gray-900'}`}>{circuito}</h3>
                <span className={`text-xs px-2 py-0.5 rounded-full ${isDark ? 'bg-gray-700 text-gray-400' : 'bg-gray-100 text-gray-500'}`}>
                  {cotacoes.length} {cotacoes.length === 1 ? 'produto' : 'produtos'}
                </span>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className={`border-b ${isDark ? 'border-gray-700' : 'border-gray-200'}`}>
                      <th className={`text-left py-2 px-3 font-medium ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Produto</th>
                      <th className={`text-right py-2 px-3 font-medium ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>FOB (USD)</th>
                      <th className={`text-right py-2 px-3 font-medium ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Índ. Import.</th>
                      <th className={`text-right py-2 px-3 font-medium ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>BEC</th>
                      <th className={`text-right py-2 px-3 font-medium ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Cotação</th>
                      <th className={`text-right py-2 px-3 font-medium ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Valor (BRL)</th>
                      <th className={`text-right py-2 px-3 font-medium ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Nacionalizado</th>
                      <th className="w-20"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {cotacoes.map(item => (
                      <tr key={item.id} className={`border-b last:border-b-0 ${isDark ? 'border-gray-700/50 hover:bg-gray-700/30' : 'border-gray-100 hover:bg-gray-50'} transition-colors`}>
                        <td className={`py-2.5 px-3 ${isDark ? 'text-gray-200' : 'text-gray-800'}`}>{item.produto}</td>
                        <td className="py-2.5 px-3 text-right">
                          <span className="font-semibold text-emerald-500">$ {fmt(item.valor_fob)}</span>
                        </td>
                        <td className={`py-2.5 px-3 text-right ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
                          {item.indice_importacao != null ? fmtDec(item.indice_importacao, 4) : '-'}
                        </td>
                        <td className={`py-2.5 px-3 text-right ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
                          {item.bec != null ? `${fmtDec(item.bec, 2)}%` : '-'}
                        </td>
                        <td className={`py-2.5 px-3 text-right ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
                          {item.cotacao_cambio != null ? fmtDec(item.cotacao_cambio, 4) : '-'}
                        </td>
                        <td className="py-2.5 px-3 text-right">
                          {item.valor_brl ? (
                            <span className="font-semibold text-blue-500">R$ {fmt(item.valor_brl)}</span>
                          ) : (
                            <span className={`text-xs ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>-</span>
                          )}
                        </td>
                        <td className="py-2.5 px-3 text-right">
                          {item.valor_nacionalizado != null ? (
                            <span className="font-semibold text-orange-500">R$ {fmt(item.valor_nacionalizado)}</span>
                          ) : (
                            <span className={`text-xs ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>-</span>
                          )}
                        </td>
                        <td className="py-2.5 px-3">
                          <div className="flex items-center justify-end gap-1">
                            <button onClick={() => openEdit(item)} className={`p-1.5 rounded-lg ${isDark ? 'hover:bg-gray-600' : 'hover:bg-gray-200'}`}>
                              <Edit2 className="w-3.5 h-3.5 text-blue-500" />
                            </button>
                            <button onClick={() => handleDelete(item.id)} className={`p-1.5 rounded-lg ${isDark ? 'hover:bg-gray-600' : 'hover:bg-gray-200'}`}>
                              <Trash2 className="w-3.5 h-3.5 text-red-500" />
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ))}

          <div className={`${cardClass} flex items-center justify-between`}>
            <span className={`text-sm font-medium ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>Total de cotações</span>
            <span className={`text-lg font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>{filtered.length}</span>
          </div>
        </div>
      )}

      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4" onClick={() => setShowModal(false)}>
          <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" />
          <div className={`relative w-full max-w-lg rounded-2xl shadow-2xl ${isDark ? 'bg-gray-800' : 'bg-white'}`} onClick={e => e.stopPropagation()}>
            <div className={`flex items-center justify-between p-4 border-b ${isDark ? 'border-gray-700' : 'border-gray-200'}`}>
              <h3 className={`font-semibold ${isDark ? 'text-white' : 'text-gray-900'}`}>
                {editingItem ? 'Editar Cotação FOB' : 'Nova Cotação FOB'}
              </h3>
              <button onClick={() => setShowModal(false)} className={`p-1 rounded-lg ${isDark ? 'hover:bg-gray-700' : 'hover:bg-gray-100'}`}>
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="p-4 space-y-4">
              <div>
                <label className={labelClass}>Circuito *</label>
                <Combobox
                  value={formCircuito}
                  onChange={setFormCircuito}
                  options={circuitos}
                  placeholder="Selecione ou digite um circuito"
                  isDark={isDark}
                />
              </div>
              <div>
                <label className={labelClass}>Produto *</label>
                <Combobox
                  value={formProduto}
                  onChange={setFormProduto}
                  options={produtos}
                  placeholder="Selecione ou digite um produto"
                  isDark={isDark}
                />
              </div>
              <div>
                <label className={labelClass}>Valor FOB (USD) *</label>
                <div className="relative">
                  <DollarSign className={`absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 ${isDark ? 'text-gray-500' : 'text-gray-400'}`} />
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    value={formValorFob}
                    onChange={e => setFormValorFob(e.target.value)}
                    placeholder="0.00"
                    className={`${inputClass} pl-9`}
                  />
                </div>
              </div>

              <div className="grid grid-cols-3 gap-3">
                <div>
                  <label className={labelClass}>Índice de Importação</label>
                  <input
                    type="number"
                    step="0.0001"
                    min="0"
                    value={formIndice}
                    onChange={e => setFormIndice(e.target.value)}
                    placeholder="0.0000"
                    className={inputClass}
                  />
                </div>
                <div>
                  <label className={labelClass}>BEC (%)</label>
                  <div className="relative">
                    <input
                      type="number"
                      step="0.01"
                      min="0"
                      value={formBec}
                      onChange={e => setFormBec(e.target.value)}
                      placeholder="0.00"
                      className={`${inputClass} pr-8`}
                    />
                    <span className={`absolute right-3 top-1/2 -translate-y-1/2 text-xs ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>%</span>
                  </div>
                </div>
                <div>
                  <label className={labelClass}>Cotação (USD/BRL)</label>
                  <input
                    type="number"
                    step="0.0001"
                    min="0"
                    value={formCotacao}
                    onChange={e => setFormCotacao(e.target.value)}
                    placeholder="0.0000"
                    className={inputClass}
                  />
                </div>
              </div>

              <div className={`rounded-lg p-3 ${isDark ? 'bg-gray-700/50' : 'bg-gray-50'} space-y-2`}>
                <div className="flex items-center gap-2 mb-1">
                  <TrendingUp className="w-3.5 h-3.5 text-blue-500" />
                  <span className={`text-xs font-medium ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                    Prévia dos cálculos
                  </span>
                </div>
                {previewBrl !== null && (
                  <div className="flex items-center justify-between">
                    <span className={`text-xs ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>FOB × Cotação (BRL):</span>
                    <span className="text-sm font-bold text-blue-500">R$ {fmt(previewBrl)}</span>
                  </div>
                )}
                {previewNac !== null && (
                  <div className="flex items-center justify-between">
                    <span className={`text-xs ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Nacionalizado:</span>
                    <span className="text-sm font-bold text-orange-500">R$ {fmt(previewNac)}</span>
                  </div>
                )}
                {previewNac === null && previewBrl === null && (
                  <span className={`text-xs ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>
                    Preencha os campos para ver a prévia
                  </span>
                )}
              </div>
            </div>
            <div className={`flex justify-end gap-3 p-4 border-t ${isDark ? 'border-gray-700' : 'border-gray-200'}`}>
              <button onClick={() => setShowModal(false)} className={`px-4 py-2 rounded-lg text-sm ${isDark ? 'bg-gray-700 text-gray-300 hover:bg-gray-600' : 'bg-gray-200 text-gray-700 hover:bg-gray-300'}`}>
                Cancelar
              </button>
              <button onClick={handleSave} disabled={saving} className="flex items-center gap-2 px-5 py-2 bg-gradient-to-r from-purple-500 to-pink-500 text-white rounded-lg text-sm font-medium hover:opacity-90 disabled:opacity-50">
                <Save className="w-4 h-4" /> {saving ? 'Salvando...' : 'Salvar'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default CotacoesImportacao;
