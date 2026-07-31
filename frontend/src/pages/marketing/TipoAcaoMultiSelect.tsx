import React, { useEffect, useMemo, useRef, useState } from 'react';
import { ChevronDown, Search, X, Plus, Loader2 } from 'lucide-react';

export interface TipoAcaoOption {
  id: number;
  codigo: string;
  nome: string;
  is_custom: boolean;
}

interface TipoAcaoMultiSelectProps {
  options: TipoAcaoOption[];
  selected: string[];
  onChange: (next: string[]) => void;
  onCreateNew: (nome: string) => Promise<TipoAcaoOption>;
  disabled?: boolean;
  placeholder?: string;
}

/**
 * Multi-select com busca para "Tipo de Ação Sugerida", seguindo o padrão de
 * dropdown+busca do KitFilterDropdown, mas como campo de formulário completo
 * (não um chip de filtro) e com a capacidade de criar novos tipos no catálogo
 * compartilhado quando a busca não encontra nada equivalente.
 */
const TipoAcaoMultiSelect: React.FC<TipoAcaoMultiSelectProps> = ({
  options,
  selected,
  onChange,
  onCreateNew,
  disabled,
  placeholder = 'Selecione o(s) tipo(s) de ação...',
}) => {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState('');
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const selectedSet = useMemo(() => new Set(selected), [selected]);

  const selectedLabels = useMemo(
    () => selected.map(codigo => options.find(o => o.codigo === codigo)?.nome || codigo),
    [selected, options]
  );

  const filteredOptions = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return options;
    return options.filter(o => o.nome.toLowerCase().includes(q));
  }, [options, search]);

  const searchTrimmed = search.trim();
  const hasExactMatch = useMemo(
    () => options.some(o => o.nome.toLowerCase() === searchTrimmed.toLowerCase()),
    [options, searchTrimmed]
  );
  const canOfferCreate = searchTrimmed.length > 0 && !hasExactMatch;

  const toggle = (codigo: string) => {
    if (disabled) return;
    const next = selectedSet.has(codigo)
      ? selected.filter(c => c !== codigo)
      : [...selected, codigo];
    onChange(next);
  };

  const removeChip = (codigo: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (disabled) return;
    onChange(selected.filter(c => c !== codigo));
  };

  const handleCreate = async () => {
    if (!searchTrimmed || creating) return;
    setCreating(true);
    setCreateError(null);
    try {
      const novo = await onCreateNew(searchTrimmed);
      onChange([...selected, novo.codigo]);
      setSearch('');
      inputRef.current?.focus();
    } catch (err: any) {
      setCreateError(err?.response?.data?.detail || 'Não foi possível criar o novo tipo');
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="relative" ref={containerRef}>
      <button
        type="button"
        onClick={() => !disabled && setOpen(o => !o)}
        disabled={disabled}
        className={`w-full min-h-[42px] flex items-center justify-between gap-2 px-3 py-2 border rounded-lg text-left transition-colors ${
          disabled
            ? 'bg-gray-50 dark:bg-gray-900 border-gray-200 dark:border-gray-700 cursor-not-allowed'
            : 'bg-white dark:bg-gray-800 border-gray-300 dark:border-gray-600 hover:border-gray-400 dark:hover:border-gray-500 cursor-pointer'
        }`}
      >
        {selected.length === 0 ? (
          <span className="text-sm text-gray-400 dark:text-gray-500">{placeholder}</span>
        ) : (
          <div className="flex flex-wrap gap-1.5">
            {selected.map((codigo, idx) => (
              <span
                key={codigo}
                className="inline-flex items-center gap-1 bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 text-xs font-medium px-2 py-0.5 rounded-full"
              >
                {selectedLabels[idx]}
                {!disabled && (
                  <X
                    className="w-3 h-3 hover:text-blue-900 dark:hover:text-blue-100"
                    onClick={(e) => removeChip(codigo, e)}
                  />
                )}
              </span>
            ))}
          </div>
        )}
        {!disabled && (
          <ChevronDown className={`w-4 h-4 flex-shrink-0 text-gray-400 transition-transform ${open ? 'rotate-180' : ''}`} />
        )}
      </button>

      {open && !disabled && (
        <div className="absolute left-0 right-0 z-20 mt-1 rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 shadow-lg p-2">
          <div className="relative mb-2">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-400" />
            <input
              ref={inputRef}
              type="text"
              value={search}
              onChange={e => { setSearch(e.target.value); setCreateError(null); }}
              placeholder="Buscar ou criar novo tipo..."
              autoFocus
              className="w-full pl-8 pr-3 py-1.5 text-sm rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
          <div className="max-h-52 overflow-y-auto space-y-0.5">
            {filteredOptions.length === 0 && !canOfferCreate ? (
              <p className="text-xs text-gray-400 dark:text-gray-500 text-center py-3">Nenhum tipo encontrado</p>
            ) : (
              filteredOptions.map(opt => {
                const active = selectedSet.has(opt.codigo);
                return (
                  <label
                    key={opt.codigo}
                    className={`flex items-center gap-2 px-2 py-1.5 rounded-lg cursor-pointer text-sm transition-colors ${
                      active
                        ? 'bg-blue-50 dark:bg-blue-900/20 text-blue-700 dark:text-blue-300'
                        : 'text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700'
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={active}
                      onChange={() => toggle(opt.codigo)}
                      className="rounded border-gray-300 dark:border-gray-600 text-blue-600 focus:ring-blue-500"
                    />
                    <span className="truncate">{opt.nome}</span>
                    {opt.is_custom && (
                      <span className="ml-auto text-[10px] text-gray-400 dark:text-gray-500 flex-shrink-0">customizado</span>
                    )}
                  </label>
                );
              })
            )}
            {canOfferCreate && (
              <button
                type="button"
                onClick={handleCreate}
                disabled={creating}
                className="w-full flex items-center gap-2 px-2 py-1.5 rounded-lg text-sm text-blue-600 dark:text-blue-400 hover:bg-blue-50 dark:hover:bg-blue-900/20 transition-colors disabled:opacity-60"
              >
                {creating ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Plus className="w-3.5 h-3.5" />}
                <span className="truncate">Adicionar novo tipo: "{searchTrimmed}"</span>
              </button>
            )}
          </div>
          {createError && (
            <p className="text-xs text-red-500 mt-1.5 px-1">{createError}</p>
          )}
        </div>
      )}
    </div>
  );
};

export default TipoAcaoMultiSelect;
