import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Filter, Search, X, ChevronDown } from 'lucide-react';

interface KitFilterDropdownProps {
  kitTypes: string[];
  selected: Set<string>;
  onChange: (next: Set<string>) => void;
  loading?: boolean;
}

/**
 * Dropdown multi-select com busca para filtrar o gráfico "Vendas Diárias" por
 * tipo de kit. Segue o padrão de busca+chips já usado no NoriInsightsPanel,
 * mas como um popover compacto (o gráfico não tem espaço vertical para chips
 * sempre visíveis).
 */
const KitFilterDropdown: React.FC<KitFilterDropdownProps> = ({ kitTypes, selected, onChange, loading }) => {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState('');
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const filteredTypes = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return kitTypes;
    return kitTypes.filter(t => t.toLowerCase().includes(q));
  }, [kitTypes, search]);

  const toggle = (tipo: string) => {
    const next = new Set(selected);
    if (next.has(tipo)) next.delete(tipo);
    else next.add(tipo);
    onChange(next);
  };

  const disabled = !loading && kitTypes.length === 0;

  return (
    <div className="relative" ref={containerRef}>
      <button
        type="button"
        onClick={() => !disabled && setOpen(o => !o)}
        disabled={disabled}
        className={`flex items-center gap-1.5 px-2.5 py-1 text-xs rounded-lg border transition-colors ${
          selected.size > 0
            ? 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 border-blue-300 dark:border-blue-700'
            : 'bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-400 border-gray-300 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-700'
        } ${disabled ? 'opacity-50 cursor-not-allowed' : ''}`}
        title={disabled ? 'Sem detalhamento por kit disponível para este evento' : 'Comparar por tipo de kit'}
      >
        <Filter className="w-3.5 h-3.5" />
        {loading ? 'Carregando kits...' : 'Kits'}
        {selected.size > 0 && (
          <span className="bg-blue-600 text-white text-[10px] font-bold rounded-full w-4 h-4 flex items-center justify-center">
            {selected.size}
          </span>
        )}
        <ChevronDown className={`w-3 h-3 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>

      {open && !disabled && (
        <div className="absolute right-0 z-20 mt-1 w-64 rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 shadow-lg p-2">
          <div className="relative mb-2">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-400" />
            <input
              type="text"
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Buscar tipo de kit..."
              autoFocus
              className="w-full pl-8 pr-3 py-1.5 text-xs rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
          <div className="max-h-56 overflow-y-auto space-y-0.5">
            {filteredTypes.length === 0 ? (
              <p className="text-xs text-gray-400 dark:text-gray-500 text-center py-3">Nenhum kit encontrado</p>
            ) : (
              filteredTypes.map(tipo => {
                const active = selected.has(tipo);
                return (
                  <label
                    key={tipo}
                    className={`flex items-center gap-2 px-2 py-1.5 rounded-lg cursor-pointer text-xs transition-colors ${
                      active
                        ? 'bg-blue-50 dark:bg-blue-900/20 text-blue-700 dark:text-blue-300'
                        : 'text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700'
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={active}
                      onChange={() => toggle(tipo)}
                      className="rounded border-gray-300 dark:border-gray-600 text-blue-600 focus:ring-blue-500"
                    />
                    <span className="truncate">{tipo}</span>
                  </label>
                );
              })
            )}
          </div>
          {selected.size > 0 && (
            <button
              type="button"
              onClick={() => onChange(new Set())}
              className="mt-2 w-full flex items-center justify-center gap-1 text-xs text-gray-500 dark:text-gray-400 hover:text-red-500 transition-colors py-1"
            >
              <X className="w-3 h-3" />
              Limpar seleção
            </button>
          )}
        </div>
      )}
    </div>
  );
};

export default KitFilterDropdown;
