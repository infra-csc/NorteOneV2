import React, { useState, useEffect, useMemo, useCallback } from 'react';
import { useTheme } from '../../context/ThemeContext';
import api from '../../services/api';
import { RefreshCw, Save, Search, AlertCircle, Package, Check, Star, Zap, Download, Filter, X } from 'lucide-react';

interface KitRow {
  id_evento: string | null;
  nome_evento: string | null;
  bundle_entity_id: number;
  nome_kit: string | null;
  tipo_kit: string | null;
  tipo_categoria: string | null;
  lote_atual: string | null;
  multiplicador_sugerido: number;
  multiplicador: number;
  price_base: number | null;
  special_price_base: number | null;
  price: number | null;
  special_price: number | null;
  is_configured: boolean;
  is_kit_basico: boolean;
  is_promo_principal: boolean;
  custo_cadastro: number | null;
  custo_kit: number | null;
  ativo_categoria: string | null;
  status_kit: string | null;
}

const fmtBRL = (v: number | null | undefined): string => {
  if (v == null) return '—';
  return v.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
};

const isParticipacaoOuMeia = (nome: string | null): boolean => {
  const n = (nome || '').toLowerCase();
  return n.includes('participação') || n.includes('participacao') || n.includes('meia');
};

const KitConfig: React.FC = () => {
  const { isDark } = useTheme();
  const [kits, setKits] = useState<KitRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editValues, setEditValues] = useState<Record<number, number>>({});
  const [basicoValues, setBasicoValues] = useState<Record<number, boolean>>({});
  const [promoValues, setPromoValues] = useState<Record<number, boolean>>({});
  const [tipoKitValues, setTipoKitValues] = useState<Record<number, string>>({});
  const [custoKitValues, setCustoKitValues] = useState<Record<number, string>>({});
  const [ativoCategValues, setAtivoCategValues] = useState<Record<number, string>>({});
  const [saving, setSaving] = useState<Record<number, boolean>>({});
  const [savedFeedback, setSavedFeedback] = useState<Record<number, boolean>>({});
  const [search, setSearch] = useState('');
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [savingMany, setSavingMany] = useState(false);

  const [filterTipo, setFilterTipo] = useState('');
  const [filterBasico, setFilterBasico] = useState('');
  const [filterStatus, setFilterStatus] = useState('');
  const [filterLote, setFilterLote] = useState('');
  const [filterStatusKit, setFilterStatusKit] = useState('');

  const hasActiveFilters = filterTipo !== '' || filterBasico !== '' || filterStatus !== '' || filterLote !== '' || filterStatusKit !== '';

  const clearFilters = () => {
    setFilterTipo('');
    setFilterBasico('');
    setFilterStatus('');
    setFilterLote('');
    setFilterStatusKit('');
  };

  const tipoOptions = useMemo(() => {
    const unique = new Set(kits.map((k) => k.tipo_categoria).filter(Boolean) as string[]);
    return Array.from(unique).sort();
  }, [kits]);

  const loteOptions = useMemo(() => {
    const unique = new Set(kits.map((k) => k.lote_atual).filter(Boolean) as string[]);
    return Array.from(unique).sort();
  }, [kits]);

  const fetchKits = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.get('/kit-config/kits');
      setKits(res.data);
      const edits: Record<number, number> = {};
      const basicos: Record<number, boolean> = {};
      const promos: Record<number, boolean> = {};
      const tipoKits: Record<number, string> = {};
      const custoKits: Record<number, string> = {};
      const ativoCats: Record<number, string> = {};

      res.data.forEach((k: KitRow) => {
        edits[k.bundle_entity_id] = k.multiplicador;
        basicos[k.bundle_entity_id] = k.is_kit_basico;
        promos[k.bundle_entity_id] = k.is_promo_principal;
        tipoKits[k.bundle_entity_id] = k.tipo_kit || '';
        custoKits[k.bundle_entity_id] = k.custo_kit != null ? String(k.custo_kit) : '';
        ativoCats[k.bundle_entity_id] = k.ativo_categoria || '';
      });

      // Custo do Kit Básico por evento (para auto-preenchimento)
      const basicoCostByEvento: Record<string, number> = {};
      res.data.forEach((k: KitRow) => {
        if (k.is_kit_basico && k.id_evento) {
          const cost = k.custo_cadastro ?? k.custo_kit ?? null;
          if (cost != null) basicoCostByEvento[k.id_evento] = cost;
        }
      });

      // Auto-preenchimento: kits sem custo definido
      res.data.forEach((k: KitRow) => {
        if (k.custo_kit != null || k.custo_cadastro != null) return;
        if (isParticipacaoOuMeia(k.nome_kit)) {
          custoKits[k.bundle_entity_id] = '10';
        } else if (k.id_evento && basicoCostByEvento[k.id_evento] != null) {
          custoKits[k.bundle_entity_id] = String(basicoCostByEvento[k.id_evento]);
        }
      });

      setEditValues(edits);
      setBasicoValues(basicos);
      setPromoValues(promos);
      setTipoKitValues(tipoKits);
      setCustoKitValues(custoKits);
      setAtivoCategValues(ativoCats);
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
    const isPromoPrincipal = promoValues[bundleId] ?? false;
    const tipoKit = (tipoKitValues[bundleId] ?? '').trim() || null;
    const kit = kits.find((k) => k.bundle_entity_id === bundleId);
    const idEvento = kit?.id_evento ? parseInt(kit.id_evento, 10) : null;
    const custoKitStr = (custoKitValues[bundleId] ?? '').trim();
    const custoKit = custoKitStr !== '' ? parseFloat(custoKitStr) : null;
    const ativoCateg = (ativoCategValues[bundleId] ?? '').trim() || null;

    setSaving((s) => ({ ...s, [bundleId]: true }));
    try {
      await api.post(`/kit-config/${bundleId}`, {
        multiplicador: mult,
        is_kit_basico: isBasico,
        is_promo_principal: isPromoPrincipal,
        id_evento: idEvento,
        tipo_kit: tipoKit,
        custo_kit: custoKit,
        ativo_categoria: ativoCateg,
      });
      setSavedFeedback((s) => ({ ...s, [bundleId]: true }));
      setTimeout(() => setSavedFeedback((s) => ({ ...s, [bundleId]: false })), 2000);

      setKits((prev) =>
        prev.map((k) => {
          if (k.bundle_entity_id === bundleId) {
            return {
              ...k,
              multiplicador: mult,
              price: k.price_base != null ? k.price_base * mult : null,
              special_price: k.special_price_base != null ? k.special_price_base * mult : null,
              is_configured: true,
              is_kit_basico: isBasico,
              is_promo_principal: isPromoPrincipal,
              custo_kit: custoKit,
              tipo_kit: tipoKit,
              ativo_categoria: ativoCateg,
            };
          }
          if (isBasico && k.id_evento === kit?.id_evento && k.is_kit_basico) {
            return { ...k, is_kit_basico: false };
          }
          if (isPromoPrincipal && k.id_evento === kit?.id_evento && k.is_promo_principal) {
            return { ...k, is_promo_principal: false };
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

      if (isPromoPrincipal && kit?.id_evento) {
        setPromoValues((prev) => {
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

  const handleSaveMany = async () => {
    setSavingMany(true);
    const ids = Array.from(selectedIds);
    await Promise.all(ids.map((id) => handleSave(id)));
    setSavingMany(false);
    setSelectedIds(new Set());
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

  const handlePromoToggle = (bundleId: number, idEvento: string | null) => {
    setPromoValues((prev) => {
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
    let result = kits;

    if (search.trim()) {
      const q = search.toLowerCase();
      result = result.filter(
        (k) =>
          (k.nome_evento || '').toLowerCase().includes(q) ||
          (k.nome_kit || '').toLowerCase().includes(q) ||
          (k.tipo_categoria || '').toLowerCase().includes(q) ||
          String(k.bundle_entity_id).includes(q),
      );
    }

    if (filterTipo) {
      result = result.filter((k) => k.tipo_categoria === filterTipo);
    }

    if (filterBasico === 'sim') {
      result = result.filter((k) => basicoValues[k.bundle_entity_id] ?? k.is_kit_basico);
    } else if (filterBasico === 'nao') {
      result = result.filter((k) => !(basicoValues[k.bundle_entity_id] ?? k.is_kit_basico));
    }

    if (filterStatus === 'configurado') {
      result = result.filter((k) => k.is_configured);
    } else if (filterStatus === 'novo') {
      result = result.filter((k) => !k.is_configured);
    }

    if (filterLote) {
      result = result.filter((k) => k.lote_atual === filterLote);
    }

    if (filterStatusKit) {
      result = result.filter((k) => (k.status_kit ?? '') === filterStatusKit);
    }

    return result;
  }, [kits, search, filterTipo, filterBasico, filterStatus, filterLote, filterStatusKit, basicoValues]);

  const allSelected = filteredKits.length > 0 && filteredKits.every((k) => selectedIds.has(k.bundle_entity_id));
  const someSelected = !allSelected && filteredKits.some((k) => selectedIds.has(k.bundle_entity_id));

  const handleSelectAll = () => {
    if (allSelected) {
      setSelectedIds((prev) => {
        const next = new Set(prev);
        filteredKits.forEach((k) => next.delete(k.bundle_entity_id));
        return next;
      });
    } else {
      setSelectedIds((prev) => {
        const next = new Set(prev);
        filteredKits.forEach((k) => next.add(k.bundle_entity_id));
        return next;
      });
    }
  };

  const handleSelectRow = (bundleId: number) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(bundleId)) next.delete(bundleId);
      else next.add(bundleId);
      return next;
    });
  };

  const handleExportCSV = useCallback(() => {
    const headers = ['Evento', 'Kit', 'Tipo', 'Lote Atual', 'Price', 'Special Price', 'Custo (R$)', 'Kit Básico', 'Configurado'];

    const escapeCSV = (val: string): string => {
      if (val.includes(';') || val.includes('"') || val.includes('\n')) {
        return `"${val.replace(/"/g, '""')}"`;
      }
      return val;
    };

    const rows = filteredKits.map((kit) => {
      const editMult = editValues[kit.bundle_entity_id] ?? kit.multiplicador;
      const computedPrice = kit.price_base != null ? kit.price_base * editMult : null;
      const computedSpecialPrice = kit.special_price_base != null ? kit.special_price_base * editMult : null;
      const isBasico = basicoValues[kit.bundle_entity_id] ?? kit.is_kit_basico;
      const custoStr = (custoKitValues[kit.bundle_entity_id] ?? '').trim();

      return [
        escapeCSV(kit.nome_evento || ''),
        escapeCSV(kit.nome_kit || ''),
        escapeCSV(kit.tipo_categoria || ''),
        escapeCSV(kit.lote_atual || ''),
        computedPrice != null ? computedPrice.toFixed(2) : '',
        computedSpecialPrice != null ? computedSpecialPrice.toFixed(2) : '',
        custoStr,
        isBasico ? 'Sim' : 'Não',
        kit.is_configured ? 'Sim' : 'Não',
      ].join(';');
    });

    const bom = '\uFEFF';
    const csvContent = bom + [headers.join(';'), ...rows].join('\n');
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `mapeamento-kits-${new Date().toISOString().slice(0, 10)}.csv`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  }, [filteredKits, editValues, basicoValues, custoKitValues]);

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

  const selectClass = `text-xs px-2 py-1.5 rounded border outline-none cursor-pointer ${
    isDark
      ? 'bg-gray-700 border-gray-600 text-white'
      : 'bg-white border-gray-300 text-gray-900'
  }`;

  const checkboxClass = `w-4 h-4 rounded cursor-pointer accent-blue-500`;

  return (
    <div className={`min-h-screen ${bg} p-0`}>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className={`text-2xl font-bold ${textPrimary}`}>Mapeamento de Kits</h1>
          <p className={`text-sm mt-1 ${textSecondary}`}>
            Configure o custo e marque o Kit Básico de cada evento.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleExportCSV}
            disabled={loading || filteredKits.length === 0}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg font-medium transition-colors ${
              isDark
                ? 'bg-emerald-600 text-white hover:bg-emerald-500 disabled:bg-gray-600 disabled:text-gray-400'
                : 'bg-emerald-500 text-white hover:bg-emerald-600 disabled:bg-gray-300 disabled:text-gray-500'
            }`}
          >
            <Download className="w-4 h-4" />
            Exportar CSV
          </button>
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
                <strong>{unconfiguredCount}</strong> kit(s) ainda sem configuração salva.
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

      <div className="flex items-center gap-3 mb-3">
        <div className={`flex items-center flex-1 gap-2 px-3 py-2 rounded-lg border ${cardBg} ${borderColor}`}>
          <Search className={`w-4 h-4 ${textSecondary}`} />
          <input
            type="text"
            placeholder="Buscar por evento, kit, categoria ou ID..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className={`flex-1 bg-transparent outline-none text-sm ${textPrimary}`}
          />
        </div>
        <div className={`flex items-center gap-2 px-3 py-2 rounded-lg ${cardBg} border ${borderColor}`}>
          <Package className={`w-4 h-4 ${textSecondary}`} />
          <span className={`text-sm font-medium ${textPrimary}`}>{filteredKits.length} kits</span>
        </div>
        {selectedIds.size > 0 && (
          <button
            onClick={handleSaveMany}
            disabled={savingMany}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg font-medium transition-colors ${
              isDark
                ? 'bg-indigo-600 text-white hover:bg-indigo-500 disabled:bg-gray-600 disabled:text-gray-400'
                : 'bg-indigo-500 text-white hover:bg-indigo-600 disabled:bg-gray-300 disabled:text-gray-500'
            }`}
          >
            <Save className="w-4 h-4" />
            {savingMany ? 'Salvando...' : `Salvar ${selectedIds.size} selecionado${selectedIds.size !== 1 ? 's' : ''}`}
          </button>
        )}
      </div>

      <div className={`flex items-center gap-3 mb-4 flex-wrap`}>
        <div className={`flex items-center gap-1.5 ${textSecondary}`}>
          <Filter className="w-3.5 h-3.5" />
          <span className="text-xs font-medium uppercase tracking-wider">Filtros</span>
        </div>

        <select value={filterTipo} onChange={(e) => setFilterTipo(e.target.value)} className={selectClass}>
          <option value="">Tipo: Todos</option>
          {tipoOptions.map((t) => (
            <option key={t} value={t}>{t}</option>
          ))}
        </select>

        <select value={filterBasico} onChange={(e) => setFilterBasico(e.target.value)} className={selectClass}>
          <option value="">Básico: Todos</option>
          <option value="sim">Com estrela</option>
          <option value="nao">Sem estrela</option>
        </select>

        <select value={filterStatus} onChange={(e) => setFilterStatus(e.target.value)} className={selectClass}>
          <option value="">Status: Todos</option>
          <option value="configurado">Configurados</option>
          <option value="novo">Não configurados</option>
        </select>

        <select value={filterLote} onChange={(e) => setFilterLote(e.target.value)} className={selectClass}>
          <option value="">Lote: Todos</option>
          {loteOptions.map((l) => (
            <option key={l} value={l}>{l}</option>
          ))}
        </select>

        <select value={filterStatusKit} onChange={(e) => setFilterStatusKit(e.target.value)} className={selectClass}>
          <option value="">Status Kit: Todos</option>
          <option value="ativo">Ativo</option>
          <option value="inativo">Inativo</option>
        </select>

        {hasActiveFilters && (
          <button
            onClick={clearFilters}
            className={`flex items-center gap-1 text-xs px-2 py-1.5 rounded transition-colors ${
              isDark
                ? 'text-red-400 hover:bg-red-900/30'
                : 'text-red-500 hover:bg-red-50'
            }`}
          >
            <X className="w-3 h-3" />
            Limpar filtros
          </button>
        )}
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
          <div className="overflow-auto max-h-[calc(100vh-320px)]">
            <table className="w-full text-sm border-collapse">
              <thead>
                <tr>
                  {/* Checkbox select-all */}
                  <th
                    className={`px-3 py-3 text-center text-xs font-bold uppercase tracking-wider whitespace-nowrap sticky top-0 z-10 border-b-2 ${
                      isDark
                        ? `${headerBg} text-blue-300 border-blue-500/50`
                        : `${headerBg} text-slate-700 border-slate-300`
                    }`}
                  >
                    <input
                      type="checkbox"
                      className={checkboxClass}
                      checked={allSelected}
                      ref={(el) => { if (el) el.indeterminate = someSelected; }}
                      onChange={handleSelectAll}
                      title="Selecionar todos os visíveis"
                    />
                  </th>
                  {[
                    { label: 'Evento', align: 'text-left' },
                    { label: 'Kit', align: 'text-left' },
                    { label: 'Tipo Kit (Cadastro)', align: 'text-left' },
                    { label: 'Cat. Ativo', align: 'text-left' },
                    { label: 'Tipo', align: 'text-left' },
                    { label: 'Lote Atual', align: 'text-left' },
                    { label: 'Status Site', align: 'text-left' },
                    { label: 'Price', align: 'text-right' },
                    { label: 'Special Price', align: 'text-right' },
                    { label: 'Custo (R$)', align: 'text-right' },
                    { label: 'Básico', align: 'text-center' },
                    { label: 'Promo', align: 'text-center' },
                    { label: '', align: 'text-center' },
                  ].map(({ label, align }, i) => (
                    <th
                      key={i}
                      className={`px-3 py-3 text-xs font-bold uppercase tracking-wider whitespace-nowrap sticky top-0 z-10 border-b-2 ${align} ${
                        isDark
                          ? `${headerBg} text-blue-300 border-blue-500/50`
                          : `${headerBg} text-slate-700 border-slate-300`
                      }`}
                    >
                      {label}
                    </th>
                  ))}
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
                  const isPromoPrincipal = promoValues[kit.bundle_entity_id] ?? kit.is_promo_principal;
                  const editTipoKit = tipoKitValues[kit.bundle_entity_id] ?? (kit.tipo_kit || '');
                  const editAtivoCateg = ativoCategValues[kit.bundle_entity_id] ?? (kit.ativo_categoria || '');
                  const custoKitStr = (custoKitValues[kit.bundle_entity_id] ?? '').trim();
                  const computedPrice = kit.price_base != null ? kit.price_base * editMult : null;
                  const computedSpecialPrice = kit.special_price_base != null ? kit.special_price_base * editMult : null;
                  const custoKitChanged = kit.custo_cadastro == null && custoKitStr !== '' && parseFloat(custoKitStr) !== (kit.custo_kit ?? 0);
                  const hasChanged = isBasico !== kit.is_kit_basico || isPromoPrincipal !== kit.is_promo_principal || editTipoKit !== (kit.tipo_kit || '') || custoKitChanged || editAtivoCateg !== (kit.ativo_categoria || '');
                  const canSave = hasChanged || !kit.is_configured;
                  const isSaving = saving[kit.bundle_entity_id];
                  const showSaved = savedFeedback[kit.bundle_entity_id];
                  const isSelected = selectedIds.has(kit.bundle_entity_id);

                  return (
                    <tr
                      key={kit.bundle_entity_id}
                      className={`${isSelected ? (isDark ? 'bg-indigo-900/30' : 'bg-indigo-50') : rowBg} ${hoverBg} transition-colors border-b ${borderColor} ${
                        !kit.is_configured
                          ? isDark
                            ? 'border-l-4 border-l-amber-500'
                            : 'border-l-4 border-l-amber-400'
                          : ''
                      }`}
                    >
                      {/* Checkbox */}
                      <td className="px-3 py-2.5 text-center whitespace-nowrap">
                        <input
                          type="checkbox"
                          className={checkboxClass}
                          checked={isSelected}
                          onChange={() => handleSelectRow(kit.bundle_entity_id)}
                        />
                      </td>

                      {/* Evento */}
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

                      {/* Kit */}
                      <td className={`px-3 py-2.5 text-left ${textSecondary}`}>
                        <span title={kit.nome_kit || ''}>
                          {kit.nome_kit || '—'}
                        </span>
                      </td>

                      {/* Tipo Kit (Cadastro) */}
                      <td className="px-3 py-2.5 text-left whitespace-nowrap">
                        <input
                          type="text"
                          placeholder="Ex: Kit Básico"
                          value={editTipoKit}
                          onChange={(e) => setTipoKitValues((prev) => ({ ...prev, [kit.bundle_entity_id]: e.target.value }))}
                          className={`w-32 text-left px-2 py-1 rounded border text-xs ${
                            isDark
                              ? 'bg-gray-700 border-gray-600 text-white focus:border-purple-400 placeholder-gray-500'
                              : 'bg-white border-gray-300 text-gray-900 focus:border-purple-500 placeholder-gray-400'
                          } outline-none ${editTipoKit !== (kit.tipo_kit || '') ? (isDark ? 'ring-1 ring-purple-400' : 'ring-1 ring-purple-500') : ''}`}
                        />
                      </td>

                      {/* Cat. Ativo */}
                      <td className="px-3 py-2.5 text-left whitespace-nowrap">
                        <input
                          type="text"
                          placeholder="Ex: Kit Básico"
                          value={editAtivoCateg}
                          onChange={(e) => setAtivoCategValues((prev) => ({ ...prev, [kit.bundle_entity_id]: e.target.value }))}
                          className={`w-32 text-left px-2 py-1 rounded border text-xs ${
                            isDark
                              ? 'bg-gray-700 border-gray-600 text-white focus:border-teal-400 placeholder-gray-500'
                              : 'bg-white border-gray-300 text-gray-900 focus:border-teal-500 placeholder-gray-400'
                          } outline-none ${editAtivoCateg !== (kit.ativo_categoria || '') ? (isDark ? 'ring-1 ring-teal-400' : 'ring-1 ring-teal-500') : ''}`}
                        />
                      </td>

                      {/* Tipo */}
                      <td className={`px-3 py-2.5 text-left whitespace-nowrap ${textSecondary}`}>
                        {kit.tipo_categoria || '—'}
                      </td>

                      {/* Lote Atual */}
                      <td className={`px-3 py-2.5 text-left whitespace-nowrap ${textSecondary}`}>
                        {kit.lote_atual || '—'}
                      </td>

                      {/* Status Site */}
                      <td className="px-3 py-2.5 text-left whitespace-nowrap">
                        {kit.status_kit === 'ativo' ? (
                          <span className={`inline-flex items-center gap-1 text-[11px] font-semibold px-2 py-0.5 rounded-full ${
                            isDark ? 'bg-emerald-900/40 text-emerald-300' : 'bg-emerald-100 text-emerald-700'
                          }`}>
                            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 inline-block" />
                            Ativo
                          </span>
                        ) : kit.status_kit === 'inativo' ? (
                          <span className={`inline-flex items-center gap-1 text-[11px] font-semibold px-2 py-0.5 rounded-full ${
                            isDark ? 'bg-red-900/40 text-red-400' : 'bg-red-100 text-red-600'
                          }`}>
                            <span className="w-1.5 h-1.5 rounded-full bg-red-500 inline-block" />
                            Inativo
                          </span>
                        ) : (
                          <span className={`text-xs ${textSecondary}`}>—</span>
                        )}
                      </td>

                      {/* Price */}
                      <td className={`px-3 py-2.5 text-right whitespace-nowrap font-medium ${textPrimary}`}>
                        {fmtBRL(computedPrice)}
                      </td>

                      {/* Special Price */}
                      <td
                        className={`px-3 py-2.5 text-right whitespace-nowrap font-bold ${
                          editMult > 1
                            ? isDark
                              ? 'text-emerald-400'
                              : 'text-emerald-600'
                            : textPrimary
                        }`}
                      >
                        {fmtBRL(computedSpecialPrice)}
                      </td>

                      {/* Custo (R$) */}
                      <td className="px-3 py-2.5 text-right whitespace-nowrap">
                        {kit.custo_cadastro != null ? (
                          <div className="flex flex-col items-end gap-0.5">
                            <span className={`text-sm font-medium ${isDark ? 'text-gray-300' : 'text-gray-600'}`}>
                              {fmtBRL(kit.custo_cadastro)}
                            </span>
                            <span className={`text-[10px] ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>do cadastro</span>
                          </div>
                        ) : (
                          <input
                            type="number"
                            min={0}
                            step={0.01}
                            placeholder="0,00"
                            value={custoKitStr}
                            onChange={(e) => setCustoKitValues((prev) => ({ ...prev, [kit.bundle_entity_id]: e.target.value }))}
                            className={`w-24 text-right px-2 py-1 rounded border text-sm ${
                              isDark
                                ? 'bg-gray-700 border-gray-600 text-white focus:border-amber-400 placeholder-gray-500'
                                : 'bg-white border-gray-300 text-gray-900 focus:border-amber-500 placeholder-gray-400'
                            } outline-none ${custoKitChanged ? (isDark ? 'ring-1 ring-amber-400' : 'ring-1 ring-amber-500') : ''}`}
                          />
                        )}
                      </td>

                      {/* Básico */}
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

                      {/* Promo */}
                      <td className="px-3 py-2.5 text-center whitespace-nowrap">
                        <button
                          onClick={() => handlePromoToggle(kit.bundle_entity_id, kit.id_evento)}
                          className={`p-1 rounded transition-colors ${
                            isPromoPrincipal
                              ? 'text-purple-500 hover:text-purple-400'
                              : isDark
                              ? 'text-gray-600 hover:text-gray-400'
                              : 'text-gray-300 hover:text-gray-500'
                          }`}
                          title={isPromoPrincipal ? 'Promo Principal para ticket (clique para desmarcar)' : 'Marcar como Promo Principal para cálculo do ticket'}
                        >
                          <Zap className={`w-5 h-5 ${isPromoPrincipal ? 'fill-current' : ''}`} />
                        </button>
                      </td>

                      {/* Salvar */}
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
                    <td colSpan={14} className={`px-3 py-12 text-center ${textSecondary}`}>
                      {search || hasActiveFilters ? 'Nenhum kit encontrado para os filtros aplicados.' : 'Nenhum kit encontrado.'}
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
