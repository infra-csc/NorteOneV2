import React, { useState, useEffect, useMemo } from 'react';
import { useTheme } from '../../context/ThemeContext';
import api from '../../services/api';
import { RefreshCw, Save, Search, AlertCircle, Package, Check } from 'lucide-react';

interface KitRow {
  id_evento: string | null;
  nome_evento: string | null;
  bundle_entity_id: number;
  nome_kit: string | null;
  lote_atual: string | null;
  preco_lote: number | null;
  lote_termina_em: string | null;
  preco_adicional_kit: number | null;
  ticket_base: number | null;
  distancias: string | null;
  multiplicador: number;
  ticket_final: number | null;
  is_configured: boolean;
}

const fmtBRL = (v: number | null | undefined): string => {
  if (v == null) return '—';
  return v.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
};

const KitConfig: React.FC = () => {
  const { isDark } = useTheme();
  const [kits, setKits] = useState<KitRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editValues, setEditValues] = useState<Record<number, number>>({});
  const [saving, setSaving] = useState<Record<number, boolean>>({});
  const [savedFeedback, setSavedFeedback] = useState<Record<number, boolean>>({});
  const [search, setSearch] = useState('');

  const fetchKits = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.get('/kit-config/kits');
      setKits(res.data);
      const edits: Record<number, number> = {};
      res.data.forEach((k: KitRow) => {
        edits[k.bundle_entity_id] = k.multiplicador;
      });
      setEditValues(edits);
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Erro ao carregar kits do Magento');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchKits();
  }, []);

  const handleSave = async (bundleId: number) => {
    const mult = editValues[bundleId] ?? 1;
    setSaving((s) => ({ ...s, [bundleId]: true }));
    try {
      await api.post(`/kit-config/${bundleId}`, { multiplicador: mult });
      setSavedFeedback((s) => ({ ...s, [bundleId]: true }));
      setTimeout(() => setSavedFeedback((s) => ({ ...s, [bundleId]: false })), 2000);
      setKits((prev) =>
        prev.map((k) =>
          k.bundle_entity_id === bundleId
            ? {
                ...k,
                multiplicador: mult,
                ticket_final: k.ticket_base != null ? k.ticket_base * mult : null,
                is_configured: true,
              }
            : k,
        ),
      );
    } catch {
      alert('Erro ao salvar configuração');
    } finally {
      setSaving((s) => ({ ...s, [bundleId]: false }));
    }
  };

  const handleMultChange = (bundleId: number, val: string) => {
    const num = parseInt(val, 10);
    if (!isNaN(num) && num >= 1) {
      setEditValues((prev) => ({ ...prev, [bundleId]: num }));
    }
  };

  const filteredKits = useMemo(() => {
    if (!search.trim()) return kits;
    const q = search.toLowerCase();
    return kits.filter(
      (k) =>
        (k.nome_evento || '').toLowerCase().includes(q) ||
        (k.nome_kit || '').toLowerCase().includes(q) ||
        String(k.bundle_entity_id).includes(q),
    );
  }, [kits, search]);

  const unconfiguredCount = kits.filter((k) => !k.is_configured).length;

  const bg = isDark ? 'bg-gray-900' : 'bg-gray-50';
  const cardBg = isDark ? 'bg-gray-800' : 'bg-white';
  const borderColor = isDark ? 'border-gray-700' : 'border-gray-200';
  const textPrimary = isDark ? 'text-white' : 'text-gray-900';
  const textSecondary = isDark ? 'text-gray-400' : 'text-gray-500';
  const headerBg = isDark ? 'bg-slate-700' : 'bg-slate-100';

  return (
    <div className={`min-h-screen ${bg} p-0`}>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className={`text-2xl font-bold ${textPrimary}`}>Mapeamento de Kits</h1>
          <p className={`text-sm mt-1 ${textSecondary}`}>
            Configure o multiplicador de cada kit para calcular o ticket final correto.
          </p>
        </div>
        <button
          onClick={fetchKits}
          disabled={loading}
          className={`flex items-center gap-2 px-4 py-2 rounded-lg font-medium transition-colors ${
            isDark
              ? 'bg-blue-600 text-white hover:bg-blue-500 disabled:bg-gray-600'
              : 'bg-blue-500 text-white hover:bg-blue-600 disabled:bg-gray-300'
          }`}
        >
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          Atualizar
        </button>
      </div>

      {unconfiguredCount > 0 && !loading && (
        <div
          className={`flex items-center gap-3 p-3 rounded-lg mb-4 border ${
            isDark
              ? 'bg-amber-900/20 border-amber-700 text-amber-300'
              : 'bg-amber-50 border-amber-200 text-amber-700'
          }`}
        >
          <AlertCircle className="w-5 h-5 flex-shrink-0" />
          <span className="text-sm">
            <strong>{unconfiguredCount}</strong> kit(s) ainda sem configuração de multiplicador.
          </span>
        </div>
      )}

      <div className="flex items-center gap-3 mb-4">
        <div className={`flex items-center flex-1 gap-2 px-3 py-2 rounded-lg border ${cardBg} ${borderColor}`}>
          <Search className={`w-4 h-4 ${textSecondary}`} />
          <input
            type="text"
            placeholder="Buscar por evento, kit ou ID..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className={`flex-1 bg-transparent outline-none text-sm ${textPrimary}`}
          />
        </div>
        <div className={`flex items-center gap-2 px-3 py-2 rounded-lg ${cardBg} border ${borderColor}`}>
          <Package className={`w-4 h-4 ${textSecondary}`} />
          <span className={`text-sm font-medium ${textPrimary}`}>{filteredKits.length} kits</span>
        </div>
      </div>

      {error && (
        <div
          className={`p-4 rounded-lg mb-4 border ${
            isDark ? 'bg-red-900/20 border-red-700 text-red-300' : 'bg-red-50 border-red-200 text-red-700'
          }`}
        >
          {error}
        </div>
      )}

      {loading ? (
        <div className="flex items-center justify-center py-20">
          <RefreshCw className={`w-8 h-8 animate-spin ${textSecondary}`} />
        </div>
      ) : (
        <div className={`rounded-lg overflow-hidden border ${borderColor}`}>
          <div className="overflow-auto max-h-[calc(100vh-280px)]">
            <table className="w-full text-sm border-collapse">
              <thead>
                <tr>
                  {['Evento', 'Kit', 'Lote Atual', 'Ticket Base', 'Mult.', 'Ticket Final', ''].map(
                    (label, i) => (
                      <th
                        key={i}
                        className={`px-3 py-3 text-xs font-bold uppercase tracking-wider whitespace-nowrap sticky top-0 z-10 border-b-2 ${
                          i >= 3 ? 'text-right' : 'text-left'
                        } ${
                          isDark
                            ? `${headerBg} text-blue-300 border-blue-500/50`
                            : `${headerBg} text-slate-700 border-slate-300`
                        }`}
                      >
                        {label}
                      </th>
                    ),
                  )}
                </tr>
              </thead>
              <tbody>
                {filteredKits.map((kit, i) => {
                  const evenRow = i % 2 === 0;
                  const rowBg = isDark
                    ? evenRow
                      ? 'bg-gray-800'
                      : 'bg-[#2d3748]'
                    : evenRow
                    ? 'bg-white'
                    : 'bg-slate-50';
                  const hoverBg = isDark ? 'hover:bg-slate-600' : 'hover:bg-blue-50';
                  const editMult = editValues[kit.bundle_entity_id] ?? kit.multiplicador;
                  const computedFinal = kit.ticket_base != null ? kit.ticket_base * editMult : null;
                  const hasChanged = editMult !== kit.multiplicador;
                  const canSave = hasChanged || !kit.is_configured;
                  const isSaving = saving[kit.bundle_entity_id];
                  const showSaved = savedFeedback[kit.bundle_entity_id];

                  return (
                    <tr
                      key={kit.bundle_entity_id}
                      className={`${rowBg} ${hoverBg} transition-colors border-b ${borderColor} ${
                        !kit.is_configured
                          ? isDark
                            ? 'border-l-4 border-l-amber-500'
                            : 'border-l-4 border-l-amber-400'
                          : ''
                      }`}
                    >
                      <td className={`px-3 py-2.5 text-left whitespace-nowrap ${textPrimary}`}>
                        <div className="flex items-center gap-2">
                          {!kit.is_configured && (
                            <span
                              className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${
                                isDark ? 'bg-amber-900/40 text-amber-300' : 'bg-amber-100 text-amber-700'
                              }`}
                            >
                              NOVO
                            </span>
                          )}
                          <span className="truncate max-w-[200px]" title={kit.nome_evento || ''}>
                            {kit.nome_evento || '—'}
                          </span>
                        </div>
                      </td>
                      <td className={`px-3 py-2.5 text-left whitespace-nowrap ${textSecondary}`}>
                        <span className="truncate max-w-[180px] block" title={kit.nome_kit || ''}>
                          {kit.nome_kit || '—'}
                        </span>
                      </td>
                      <td className={`px-3 py-2.5 text-left whitespace-nowrap ${textSecondary}`}>
                        {kit.lote_atual || '—'}
                      </td>
                      <td className={`px-3 py-2.5 text-right whitespace-nowrap font-medium ${textPrimary}`}>
                        {fmtBRL(kit.ticket_base)}
                      </td>
                      <td className="px-3 py-2.5 text-right whitespace-nowrap">
                        <input
                          type="number"
                          min={1}
                          value={editMult}
                          onChange={(e) => handleMultChange(kit.bundle_entity_id, e.target.value)}
                          className={`w-16 text-right px-2 py-1 rounded border text-sm font-bold ${
                            isDark
                              ? 'bg-gray-700 border-gray-600 text-white focus:border-blue-400'
                              : 'bg-white border-gray-300 text-gray-900 focus:border-blue-500'
                          } outline-none ${hasChanged ? (isDark ? 'ring-1 ring-blue-400' : 'ring-1 ring-blue-500') : ''}`}
                        />
                      </td>
                      <td
                        className={`px-3 py-2.5 text-right whitespace-nowrap font-bold ${
                          editMult > 1
                            ? isDark
                              ? 'text-emerald-400'
                              : 'text-emerald-600'
                            : textPrimary
                        }`}
                      >
                        {fmtBRL(computedFinal)}
                      </td>
                      <td className="px-3 py-2.5 text-center whitespace-nowrap">
                        {showSaved ? (
                          <span className="inline-flex items-center gap-1 text-emerald-500 text-xs font-medium">
                            <Check className="w-3.5 h-3.5" /> Salvo
                          </span>
                        ) : (
                          <button
                            onClick={() => handleSave(kit.bundle_entity_id)}
                            disabled={isSaving || !canSave}
                            className={`inline-flex items-center gap-1 px-2.5 py-1 rounded text-xs font-medium transition-colors ${
                              canSave
                                ? isDark
                                  ? 'bg-blue-600 text-white hover:bg-blue-500'
                                  : 'bg-blue-500 text-white hover:bg-blue-600'
                                : isDark
                                ? 'bg-gray-700 text-gray-500 cursor-not-allowed'
                                : 'bg-gray-100 text-gray-400 cursor-not-allowed'
                            }`}
                          >
                            <Save className="w-3 h-3" />
                            {isSaving ? '...' : 'Salvar'}
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })}
                {filteredKits.length === 0 && (
                  <tr>
                    <td colSpan={7} className={`px-3 py-12 text-center ${textSecondary}`}>
                      {search ? 'Nenhum kit encontrado para esta busca.' : 'Nenhum kit encontrado.'}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
};

export default KitConfig;
