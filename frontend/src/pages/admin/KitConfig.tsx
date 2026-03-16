import React, { useState, useEffect, useMemo } from 'react';
import { useTheme } from '../../context/ThemeContext';
import api from '../../services/api';
import { RefreshCw, Save, Search, AlertCircle, Package, Check, Star } from 'lucide-react';

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
  is_kit_basico: boolean;
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
  const [basicoValues, setBasicoValues] = useState<Record<number, boolean>>({});
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
      const basicos: Record<number, boolean> = {};
      res.data.forEach((k: KitRow) => {
        edits[k.bundle_entity_id] = k.multiplicador;
        basicos[k.bundle_entity_id] = k.is_kit_basico;
      });
      setEditValues(edits);
      setBasicoValues(basicos);
    } catch (err) {
      const axiosErr = err as { response?: { data?: { detail?: string } } };
      setError(axiosErr?.response?.data?.detail || 'Erro ao carregar kits do Magento');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchKits();
  }, []);

  const handleSave = async (bundleId: number) => {
    const mult = editValues[bundleId] ?? 1;
    const isBasico = basicoValues[bundleId] ?? false;
    const kit = kits.find((k) => k.bundle_entity_id === bundleId);
    const idEvento = kit?.id_evento ? parseInt(kit.id_evento, 10) : null;

    setSaving((s) => ({ ...s, [bundleId]: true }));
    try {
      await api.post(`/kit-config/${bundleId}`, {
        multiplicador: mult,
        is_kit_basico: isBasico,
        id_evento: idEvento,
      });
      setSavedFeedback((s) => ({ ...s, [bundleId]: true }));
      setTimeout(() => setSavedFeedback((s) => ({ ...s, [bundleId]: false })), 2000);

      setKits((prev) =>
        prev.map((k) => {
          if (k.bundle_entity_id === bundleId) {
            return {
              ...k,
              multiplicador: mult,
              ticket_final: k.ticket_base != null ? k.ticket_base * mult : null,
              is_configured: true,
              is_kit_basico: isBasico,
            };
          }
          if (isBasico && k.id_evento === kit?.id_evento && k.is_kit_basico) {
            return { ...k, is_kit_basico: false };
          }
          return k;
        }),
      );

      if (isBasico && kit?.id_evento) {
        setBasicoValues((prev) => {
          const updated = { ...prev };
          kits.forEach((k) => {
            if (k.id_evento === kit.id_evento && k.bundle_entity_id !== bundleId) {
              updated[k.bundle_entity_id] = false;
            }
          });
          updated[bundleId] = true;
          return updated;
        });
      }
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

  const handleBasicoToggle = (bundleId: number, idEvento: string | null) => {
    setBasicoValues((prev) => {
      const updated = { ...prev };
      const newVal = !prev[bundleId];
      if (newVal && idEvento) {
        kits.forEach((k) => {
          if (k.id_evento === idEvento) {
            updated[k.bundle_entity_id] = false;
          }
        });
      }
      updated[bundleId] = newVal;
      return updated;
    });
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

  const eventosUniqueIds = new Set(kits.map((k) => k.id_evento).filter(Boolean));
  const eventosComBasico = new Set(
    kits.filter((k) => k.is_kit_basico).map((k) => k.id_evento).filter(Boolean),
  );
  const eventosSemBasico = eventosUniqueIds.size - eventosComBasico.size;

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
            Configure o multiplicador e marque o Kit Básico de cada evento.
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

      {(unconfiguredCount > 0 || eventosSemBasico > 0) && !loading && (
        <div className="flex flex-col gap-2 mb-4">
          {unconfiguredCount > 0 && (
            <div
              className={`flex items-center gap-3 p-3 rounded-lg border ${
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
          {eventosSemBasico > 0 && (
            <div
              className={`flex items-center gap-3 p-3 rounded-lg border ${
                isDark
                  ? 'bg-blue-900/20 border-blue-700 text-blue-300'
                  : 'bg-blue-50 border-blue-200 text-blue-700'
              }`}
            >
              <Star className="w-5 h-5 flex-shrink-0" />
              <span className="text-sm">
                <strong>{eventosSemBasico}</strong> evento(s) sem Kit Básico definido. O ticket desses eventos não aparecerá no ISC.
              </span>
            </div>
          )}
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
                  {['Evento', 'Kit', 'Lote Atual', 'Ticket Base', 'Mult.', 'Ticket Final', 'Básico', ''].map(
                    (label, i) => (
                      <th
                        key={i}
                        className={`px-3 py-3 text-xs font-bold uppercase tracking-wider whitespace-nowrap sticky top-0 z-10 border-b-2 ${
                          i >= 3 ? 'text-right' : 'text-left'
                        } ${i === 6 ? 'text-center' : ''} ${
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
                  const isBasico = basicoValues[kit.bundle_entity_id] ?? kit.is_kit_basico;
                  const computedFinal = kit.ticket_base != null ? kit.ticket_base * editMult : null;
                  const hasChanged = editMult !== kit.multiplicador || isBasico !== kit.is_kit_basico;
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
                      <td className={`px-3 py-2.5 text-left ${textPrimary}`}>
                        <div className="flex items-start gap-2">
                          {!kit.is_configured && (
                            <span
                              className={`text-[10px] font-bold px-1.5 py-0.5 rounded flex-shrink-0 mt-0.5 ${
                                isDark ? 'bg-amber-900/40 text-amber-300' : 'bg-amber-100 text-amber-700'
                              }`}
                            >
                              NOVO
                            </span>
                          )}
                          <span title={kit.nome_evento || ''}>
                            {kit.nome_evento || '—'}
                          </span>
                        </div>
                      </td>
                      <td className={`px-3 py-2.5 text-left ${textSecondary}`}>
                        <span title={kit.nome_kit || ''}>
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
                        <button
                          onClick={() => handleBasicoToggle(kit.bundle_entity_id, kit.id_evento)}
                          className={`p-1 rounded transition-colors ${
                            isBasico
                              ? 'text-yellow-500 hover:text-yellow-400'
                              : isDark
                              ? 'text-gray-600 hover:text-gray-400'
                              : 'text-gray-300 hover:text-gray-500'
                          }`}
                          title={isBasico ? 'Kit Básico (clique para desmarcar)' : 'Marcar como Kit Básico'}
                        >
                          <Star className={`w-5 h-5 ${isBasico ? 'fill-current' : ''}`} />
                        </button>
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
                    <td colSpan={8} className={`px-3 py-12 text-center ${textSecondary}`}>
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
