import React, { useEffect, useState, useMemo } from 'react';
import { inscricoesConsolidadasService, InscricaoConsolidada, InscricoesConsolidadasResponse } from '../../services/api';
import { useTheme } from '../../context/ThemeContext';
import { 
  Database, Search, Filter, RefreshCw, Download, AlertTriangle,
  CheckCircle, XCircle, ChevronDown, ChevronUp, ArrowUpDown,
  Eye, DollarSign, Users, Store, ShoppingBag
} from 'lucide-react';

type SortField = 'evento' | 'data_evento' | 'qtd_vendida_total' | 'inscricao_liquida_total' | 'ticket_medio_total' | 'qtd_grupos_total' | 'qtd_site_total';
type SortDirection = 'asc' | 'desc';

const DadosConsolidados: React.FC = () => {
  const { isDark } = useTheme();
  const [data, setData] = useState<InscricoesConsolidadasResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchSku, setSearchSku] = useState('');
  const [searchEvento, setSearchEvento] = useState('');
  const [filterFonte, setFilterFonte] = useState<'todos' | 'ativo' | 'magento' | 'ambos'>('todos');
  const [sortField, setSortField] = useState<SortField>('qtd_vendida_total');
  const [sortDirection, setSortDirection] = useState<SortDirection>('desc');
  const [selectedItem, setSelectedItem] = useState<InscricaoConsolidada | null>(null);

  const fetchData = async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await inscricoesConsolidadasService.getConsolidado(undefined, true);
      setData(result);
    } catch (err: any) {
      setError(err.message || 'Erro ao carregar dados');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const filteredAndSortedData = useMemo(() => {
    if (!data?.dados) return [];
    
    let filtered = data.dados.filter(item => {
      const matchesSku = !searchSku || (item.sku && item.sku.toLowerCase().includes(searchSku.toLowerCase()));
      const matchesEvento = !searchEvento || (item.evento && item.evento.toLowerCase().includes(searchEvento.toLowerCase()));
      
      let matchesFonte = true;
      if (filterFonte === 'ativo') {
        matchesFonte = !!item.por_fonte.ativo && item.por_fonte.ativo.qtd > 0;
      } else if (filterFonte === 'magento') {
        matchesFonte = !!item.por_fonte.magento && item.por_fonte.magento.qtd > 0;
      } else if (filterFonte === 'ambos') {
        matchesFonte = !!item.por_fonte.ativo && item.por_fonte.ativo.qtd > 0 && !!item.por_fonte.magento && item.por_fonte.magento.qtd > 0;
      }
      
      return matchesSku && matchesEvento && matchesFonte;
    });

    filtered.sort((a, b) => {
      let aVal: number | string = 0;
      let bVal: number | string = 0;
      
      switch (sortField) {
        case 'evento':
          aVal = a.evento || '';
          bVal = b.evento || '';
          break;
        case 'data_evento':
          aVal = a.data_evento || '';
          bVal = b.data_evento || '';
          break;
        case 'qtd_vendida_total':
          aVal = a.qtd_vendida_total;
          bVal = b.qtd_vendida_total;
          break;
        case 'inscricao_liquida_total':
          aVal = a.inscricao_liquida_total;
          bVal = b.inscricao_liquida_total;
          break;
        case 'ticket_medio_total':
          aVal = a.ticket_medio_total;
          bVal = b.ticket_medio_total;
          break;
        case 'qtd_grupos_total':
          aVal = a.qtd_grupos_total;
          bVal = b.qtd_grupos_total;
          break;
        case 'qtd_site_total':
          aVal = a.qtd_site_total;
          bVal = b.qtd_site_total;
          break;
      }
      
      if (typeof aVal === 'string' && typeof bVal === 'string') {
        return sortDirection === 'asc' ? aVal.localeCompare(bVal) : bVal.localeCompare(aVal);
      }
      return sortDirection === 'asc' ? (aVal as number) - (bVal as number) : (bVal as number) - (aVal as number);
    });

    return filtered;
  }, [data, searchSku, searchEvento, filterFonte, sortField, sortDirection]);

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDirection(prev => prev === 'asc' ? 'desc' : 'asc');
    } else {
      setSortField(field);
      setSortDirection('desc');
    }
  };

  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(value);
  };

  const formatNumber = (value: number) => {
    return new Intl.NumberFormat('pt-BR').format(value);
  };

  const exportToCSV = () => {
    if (!filteredAndSortedData.length) return;
    
    const headers = [
      'Data Evento', 'Evento', 'Cidade', 'Categoria', 
      'Qtd Total', 'Valor Total', 'Cortesias', 'Inscricao Liquida Total', 'Ticket Medio Total',
      'Taxa Liquida Total', 'Kit Produto Total',
      'Qtd Grupos', 'Inscricao Liquida Grupos',
      'Qtd Site', 'Inscricao Liquida Site',
      'Fonte Ativo', 'Ativo Qtd', 'Ativo Inscricao Liquida', 'Ativo Ticket Medio',
      'Fonte Magento', 'Magento Qtd', 'Magento Inscricao Liquida', 'Magento Ticket Medio'
    ];
    const rows = filteredAndSortedData.map(item => [
      item.data_evento || '',
      item.evento || '',
      item.cidade || '',
      item.categoria_evento || '',
      item.qtd_vendida_total,
      item.valor_total,
      item.cortesia_total,
      item.inscricao_liquida_total,
      item.ticket_medio_total,
      item.taxa_liquida_total,
      item.kit_produto_total,
      item.qtd_grupos_total,
      item.inscricao_liquida_grupos_total,
      item.qtd_site_total,
      item.inscricao_liquida_site_total,
      item.por_fonte.ativo ? 'Sim' : 'Nao',
      item.por_fonte.ativo?.qtd || 0,
      item.por_fonte.ativo?.inscricao_liquida || 0,
      item.por_fonte.ativo?.ticket_medio || 0,
      item.por_fonte.magento ? 'Sim' : 'Nao',
      item.por_fonte.magento?.qtd || 0,
      item.por_fonte.magento?.inscricao_liquida || 0,
      item.por_fonte.magento?.ticket_medio || 0
    ]);
    
    const csvContent = [headers.join(';'), ...rows.map(row => row.join(';'))].join('\n');
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = `dados_consolidados_${new Date().toISOString().split('T')[0]}.csv`;
    link.click();
  };

  const SortIcon = ({ field }: { field: SortField }) => {
    if (sortField !== field) return <ArrowUpDown className="w-4 h-4 opacity-30" />;
    return sortDirection === 'asc' ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />;
  };

  const totals = useMemo(() => {
    return {
      eventos: filteredAndSortedData.length,
      qtdTotal: filteredAndSortedData.reduce((sum, item) => sum + item.qtd_vendida_total, 0),
      valorTotal: filteredAndSortedData.reduce((sum, item) => sum + item.valor_total, 0),
      ativoQtd: filteredAndSortedData.reduce((sum, item) => sum + (item.por_fonte.ativo?.qtd || 0), 0),
      magentoQtd: filteredAndSortedData.reduce((sum, item) => sum + (item.por_fonte.magento?.qtd || 0), 0),
    };
  }, [filteredAndSortedData]);

  return (
    <div className={`min-h-screen ${isDark ? 'bg-gray-900' : 'bg-gray-50'}`}>
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute top-0 left-1/4 w-96 h-96 bg-gradient-to-r from-blue-500/10 to-cyan-500/10 rounded-full blur-3xl" />
        <div className="absolute bottom-1/4 right-1/4 w-80 h-80 bg-gradient-to-r from-purple-500/10 to-pink-500/10 rounded-full blur-3xl" />
      </div>

      <div className="relative p-6 max-w-[1800px] mx-auto">
        <div className="mb-6">
          <div className="flex items-center gap-3 mb-2">
            <div className="p-3 rounded-xl bg-gradient-to-r from-blue-500 to-cyan-500 shadow-lg shadow-blue-500/25">
              <Database className="w-6 h-6 text-white" />
            </div>
            <div>
              <h1 className={`text-2xl font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>
                Admin - Dados Consolidados
              </h1>
              <p className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>
                Visualize e analise os dados de inscrições de ambas as fontes (Ativo e Magento)
              </p>
            </div>
          </div>
        </div>

        {data?.fontes_disponiveis && (
          <div className="flex gap-4 mb-6">
            <div className={`flex items-center gap-2 px-4 py-2 rounded-lg ${isDark ? 'bg-gray-800' : 'bg-white'} shadow`}>
              <Store className="w-5 h-5 text-blue-500" />
              <span className={isDark ? 'text-gray-300' : 'text-gray-700'}>Ativo:</span>
              {data.fontes_disponiveis.ativo.disponivel ? (
                <CheckCircle className="w-5 h-5 text-green-500" />
              ) : (
                <XCircle className="w-5 h-5 text-red-500" />
              )}
              {data.fontes_disponiveis.ativo.erro && (
                <span className="text-red-400 text-xs ml-1">{data.fontes_disponiveis.ativo.erro}</span>
              )}
            </div>
            <div className={`flex items-center gap-2 px-4 py-2 rounded-lg ${isDark ? 'bg-gray-800' : 'bg-white'} shadow`}>
              <ShoppingBag className="w-5 h-5 text-orange-500" />
              <span className={isDark ? 'text-gray-300' : 'text-gray-700'}>Magento:</span>
              {data.fontes_disponiveis.magento.disponivel ? (
                <CheckCircle className="w-5 h-5 text-green-500" />
              ) : (
                <XCircle className="w-5 h-5 text-red-500" />
              )}
              {data.fontes_disponiveis.magento.erro && (
                <span className="text-red-400 text-xs ml-1">{data.fontes_disponiveis.magento.erro}</span>
              )}
            </div>
          </div>
        )}

        <div className="grid grid-cols-5 gap-4 mb-6">
          <div className={`p-4 rounded-xl ${isDark ? 'bg-gray-800/80' : 'bg-white'} shadow-lg backdrop-blur-sm border ${isDark ? 'border-gray-700' : 'border-gray-200'}`}>
            <div className="flex items-center justify-between">
              <span className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>Eventos</span>
              <Database className="w-5 h-5 text-blue-500" />
            </div>
            <p className={`text-2xl font-bold mt-1 ${isDark ? 'text-white' : 'text-gray-900'}`}>
              {formatNumber(totals.eventos)}
            </p>
          </div>
          <div className={`p-4 rounded-xl ${isDark ? 'bg-gray-800/80' : 'bg-white'} shadow-lg backdrop-blur-sm border ${isDark ? 'border-gray-700' : 'border-gray-200'}`}>
            <div className="flex items-center justify-between">
              <span className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>Inscritos Total</span>
              <Users className="w-5 h-5 text-green-500" />
            </div>
            <p className={`text-2xl font-bold mt-1 ${isDark ? 'text-white' : 'text-gray-900'}`}>
              {formatNumber(totals.qtdTotal)}
            </p>
          </div>
          <div className={`p-4 rounded-xl ${isDark ? 'bg-gray-800/80' : 'bg-white'} shadow-lg backdrop-blur-sm border ${isDark ? 'border-gray-700' : 'border-gray-200'}`}>
            <div className="flex items-center justify-between">
              <span className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>Receita Total</span>
              <DollarSign className="w-5 h-5 text-emerald-500" />
            </div>
            <p className={`text-2xl font-bold mt-1 ${isDark ? 'text-white' : 'text-gray-900'}`}>
              {formatCurrency(totals.valorTotal)}
            </p>
          </div>
          <div className={`p-4 rounded-xl ${isDark ? 'bg-gray-800/80' : 'bg-white'} shadow-lg backdrop-blur-sm border ${isDark ? 'border-gray-700' : 'border-gray-200'}`}>
            <div className="flex items-center justify-between">
              <span className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>Ativo</span>
              <Store className="w-5 h-5 text-blue-500" />
            </div>
            <p className={`text-2xl font-bold mt-1 ${isDark ? 'text-white' : 'text-gray-900'}`}>
              {formatNumber(totals.ativoQtd)}
            </p>
          </div>
          <div className={`p-4 rounded-xl ${isDark ? 'bg-gray-800/80' : 'bg-white'} shadow-lg backdrop-blur-sm border ${isDark ? 'border-gray-700' : 'border-gray-200'}`}>
            <div className="flex items-center justify-between">
              <span className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>Magento</span>
              <ShoppingBag className="w-5 h-5 text-orange-500" />
            </div>
            <p className={`text-2xl font-bold mt-1 ${isDark ? 'text-white' : 'text-gray-900'}`}>
              {formatNumber(totals.magentoQtd)}
            </p>
          </div>
        </div>

        <div className={`p-4 rounded-xl ${isDark ? 'bg-gray-800/80' : 'bg-white'} shadow-lg backdrop-blur-sm border ${isDark ? 'border-gray-700' : 'border-gray-200'} mb-6`}>
          <div className="flex flex-wrap gap-4 items-center">
            <div className="flex-1 min-w-[200px]">
              <div className="relative">
                <Search className={`absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 ${isDark ? 'text-gray-400' : 'text-gray-500'}`} />
                <input
                  type="text"
                  placeholder="Buscar por SKU..."
                  value={searchSku}
                  onChange={(e) => setSearchSku(e.target.value)}
                  className={`w-full pl-10 pr-4 py-2 rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white placeholder-gray-400' : 'bg-gray-50 border-gray-300 text-gray-900'} focus:ring-2 focus:ring-blue-500`}
                />
              </div>
            </div>
            <div className="flex-1 min-w-[200px]">
              <div className="relative">
                <Search className={`absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 ${isDark ? 'text-gray-400' : 'text-gray-500'}`} />
                <input
                  type="text"
                  placeholder="Buscar por Evento..."
                  value={searchEvento}
                  onChange={(e) => setSearchEvento(e.target.value)}
                  className={`w-full pl-10 pr-4 py-2 rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white placeholder-gray-400' : 'bg-gray-50 border-gray-300 text-gray-900'} focus:ring-2 focus:ring-blue-500`}
                />
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Filter className={`w-4 h-4 ${isDark ? 'text-gray-400' : 'text-gray-500'}`} />
              <select
                value={filterFonte}
                onChange={(e) => setFilterFonte(e.target.value as typeof filterFonte)}
                className={`px-4 py-2 rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white' : 'bg-gray-50 border-gray-300 text-gray-900'} focus:ring-2 focus:ring-blue-500`}
              >
                <option value="todos">Todas as fontes</option>
                <option value="ativo">Apenas Ativo</option>
                <option value="magento">Apenas Magento</option>
                <option value="ambos">Com ambas fontes</option>
              </select>
            </div>
            <button
              onClick={fetchData}
              disabled={loading}
              className="flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-blue-500 to-cyan-500 text-white rounded-lg hover:opacity-90 transition-opacity disabled:opacity-50"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
              Atualizar
            </button>
            <button
              onClick={exportToCSV}
              disabled={!filteredAndSortedData.length}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg border ${isDark ? 'border-gray-600 text-gray-300 hover:bg-gray-700' : 'border-gray-300 text-gray-700 hover:bg-gray-100'} transition-colors disabled:opacity-50`}
            >
              <Download className="w-4 h-4" />
              Exportar CSV
            </button>
          </div>
        </div>

        {error && (
          <div className="mb-6 p-4 bg-red-500/20 border border-red-500/50 rounded-xl flex items-center gap-3">
            <AlertTriangle className="w-5 h-5 text-red-400" />
            <span className="text-red-400">{error}</span>
          </div>
        )}

        <div className={`rounded-xl ${isDark ? 'bg-gray-800/80' : 'bg-white'} shadow-lg backdrop-blur-sm border ${isDark ? 'border-gray-700' : 'border-gray-200'} overflow-hidden`}>
          <style>{`
            .resizable-th {
              position: relative;
              overflow: hidden;
              resize: horizontal;
              min-width: 80px;
            }
            .resizable-th::after {
              content: '';
              position: absolute;
              right: 0;
              top: 25%;
              height: 50%;
              width: 4px;
              background: linear-gradient(90deg, transparent, ${isDark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.1)'});
              cursor: col-resize;
            }
            .resizable-th:hover::after {
              background: linear-gradient(90deg, transparent, ${isDark ? 'rgba(59,130,246,0.5)' : 'rgba(59,130,246,0.3)'});
            }
          `}</style>
          <div className="overflow-x-auto">
            <table className="w-full" style={{ tableLayout: 'fixed' }}>
              <thead className={isDark ? 'bg-gray-700/50' : 'bg-gray-100'}>
                <tr>
                  <th className={`resizable-th px-4 py-3 text-left text-xs font-medium uppercase tracking-wider ${isDark ? 'text-gray-300' : 'text-gray-600'}`} style={{ width: '100px' }}>
                    <button onClick={() => handleSort('data_evento')} className="flex items-center gap-1 hover:text-blue-500">
                      Data <SortIcon field="data_evento" />
                    </button>
                  </th>
                  <th className={`resizable-th px-4 py-3 text-left text-xs font-medium uppercase tracking-wider ${isDark ? 'text-gray-300' : 'text-gray-600'}`} style={{ width: '250px' }}>
                    <button onClick={() => handleSort('evento')} className="flex items-center gap-1 hover:text-blue-500">
                      Evento <SortIcon field="evento" />
                    </button>
                  </th>
                  <th className={`resizable-th px-4 py-3 text-right text-xs font-medium uppercase tracking-wider ${isDark ? 'text-gray-300' : 'text-gray-600'}`} style={{ width: '80px' }}>
                    <button onClick={() => handleSort('qtd_vendida_total')} className="flex items-center gap-1 justify-end hover:text-blue-500">
                      Qtd <SortIcon field="qtd_vendida_total" />
                    </button>
                  </th>
                  <th className={`resizable-th px-4 py-3 text-right text-xs font-medium uppercase tracking-wider ${isDark ? 'text-gray-300' : 'text-gray-600'}`} style={{ width: '120px' }}>
                    <button onClick={() => handleSort('inscricao_liquida_total')} className="flex items-center gap-1 justify-end hover:text-blue-500">
                      Insc. Líquida <SortIcon field="inscricao_liquida_total" />
                    </button>
                  </th>
                  <th className={`resizable-th px-4 py-3 text-right text-xs font-medium uppercase tracking-wider ${isDark ? 'text-gray-300' : 'text-gray-600'}`} style={{ width: '100px' }}>
                    <button onClick={() => handleSort('ticket_medio_total')} className="flex items-center gap-1 justify-end hover:text-blue-500">
                      Ticket Médio <SortIcon field="ticket_medio_total" />
                    </button>
                  </th>
                  <th className={`resizable-th px-4 py-3 text-right text-xs font-medium uppercase tracking-wider ${isDark ? 'text-gray-300' : 'text-gray-600'}`} style={{ width: '80px' }}>
                    <button onClick={() => handleSort('qtd_grupos_total')} className="flex items-center gap-1 justify-end hover:text-blue-500">
                      Grupos <SortIcon field="qtd_grupos_total" />
                    </button>
                  </th>
                  <th className={`resizable-th px-4 py-3 text-right text-xs font-medium uppercase tracking-wider ${isDark ? 'text-gray-300' : 'text-gray-600'}`} style={{ width: '80px' }}>
                    <button onClick={() => handleSort('qtd_site_total')} className="flex items-center gap-1 justify-end hover:text-blue-500">
                      Site <SortIcon field="qtd_site_total" />
                    </button>
                  </th>
                  <th className={`px-4 py-3 text-center text-xs font-medium uppercase tracking-wider ${isDark ? 'text-gray-300' : 'text-gray-600'}`} style={{ width: '60px' }}>
                    Fonte
                  </th>
                  <th className={`px-4 py-3 text-center text-xs font-medium uppercase tracking-wider ${isDark ? 'text-gray-300' : 'text-gray-600'}`} style={{ width: '50px' }}>
                    
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-700">
                {loading ? (
                  <tr>
                    <td colSpan={9} className="px-4 py-12 text-center">
                      <RefreshCw className={`w-8 h-8 mx-auto animate-spin ${isDark ? 'text-gray-400' : 'text-gray-500'}`} />
                      <p className={`mt-2 ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Carregando dados...</p>
                    </td>
                  </tr>
                ) : filteredAndSortedData.length === 0 ? (
                  <tr>
                    <td colSpan={9} className="px-4 py-12 text-center">
                      <Database className={`w-8 h-8 mx-auto ${isDark ? 'text-gray-500' : 'text-gray-400'}`} />
                      <p className={`mt-2 ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Nenhum dado encontrado</p>
                    </td>
                  </tr>
                ) : (
                  filteredAndSortedData.map((item, index) => (
                    <tr 
                      key={`${item.sku}-${index}`}
                      className={`${isDark ? 'hover:bg-gray-700/50' : 'hover:bg-gray-50'} transition-colors`}
                    >
                      <td className={`px-4 py-3 ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>
                        <span className="text-sm">{item.data_evento || '-'}</span>
                      </td>
                      <td className={`px-4 py-3 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
                        <div className="break-words font-medium" title={item.evento || '-'}>
                          {item.evento || <span className="text-gray-500 italic">Sem nome</span>}
                        </div>
                        {item.cidade && (
                          <span className={`text-xs ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>
                            {item.cidade}
                          </span>
                        )}
                      </td>
                      <td className={`px-4 py-3 text-right font-semibold ${isDark ? 'text-white' : 'text-gray-900'}`}>
                        {formatNumber(item.qtd_vendida_total)}
                        {item.cortesia_total > 0 && (
                          <div className={`text-xs ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>
                            ({item.cortesia_total} cortesias)
                          </div>
                        )}
                      </td>
                      <td className={`px-4 py-3 text-right ${isDark ? 'text-emerald-400' : 'text-emerald-600'}`}>
                        {formatCurrency(item.inscricao_liquida_total)}
                      </td>
                      <td className={`px-4 py-3 text-right ${isDark ? 'text-blue-400' : 'text-blue-600'}`}>
                        {formatCurrency(item.ticket_medio_total)}
                      </td>
                      <td className={`px-4 py-3 text-right ${isDark ? 'text-purple-400' : 'text-purple-600'}`}>
                        {formatNumber(item.qtd_grupos_total)}
                      </td>
                      <td className={`px-4 py-3 text-right ${isDark ? 'text-orange-400' : 'text-orange-600'}`}>
                        {formatNumber(item.qtd_site_total)}
                      </td>
                      <td className="px-4 py-3 text-center">
                        {item.por_fonte.ativo && (
                          <span className="inline-flex items-center px-2 py-1 rounded text-xs bg-blue-500/20 text-blue-400" title="Ativo">
                            <Store className="w-3 h-3" />
                          </span>
                        )}
                        {item.por_fonte.magento && (
                          <span className="inline-flex items-center px-2 py-1 rounded text-xs bg-orange-500/20 text-orange-400 ml-1" title="Magento">
                            <ShoppingBag className="w-3 h-3" />
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-center">
                        <button
                          onClick={() => setSelectedItem(item)}
                          className={`p-2 rounded-lg ${isDark ? 'hover:bg-gray-600' : 'hover:bg-gray-200'} transition-colors`}
                          title="Ver detalhes"
                        >
                          <Eye className={`w-4 h-4 ${isDark ? 'text-gray-400' : 'text-gray-500'}`} />
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>

        <div className={`mt-4 text-sm ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>
          Exibindo {formatNumber(filteredAndSortedData.length)} de {formatNumber(data?.dados.length || 0)} eventos
        </div>
      </div>

      {selectedItem && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 p-4">
          <div className={`w-full max-w-3xl max-h-[90vh] ${isDark ? 'bg-gray-800' : 'bg-white'} rounded-2xl shadow-2xl overflow-hidden`}>
            <div className="p-6 border-b border-gray-700">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className={`text-xl font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>
                    {selectedItem.evento || 'Evento sem nome'}
                  </h2>
                  <p className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>
                    {selectedItem.data_evento} {selectedItem.cidade && `- ${selectedItem.cidade}`}
                  </p>
                </div>
                <button
                  onClick={() => setSelectedItem(null)}
                  className={`p-2 rounded-lg ${isDark ? 'hover:bg-gray-700' : 'hover:bg-gray-100'}`}
                >
                  <XCircle className={`w-5 h-5 ${isDark ? 'text-gray-400' : 'text-gray-500'}`} />
                </button>
              </div>
            </div>
            <div className="p-6 space-y-4 overflow-y-auto max-h-[70vh]">
              <div className="grid grid-cols-4 gap-3">
                <div className={`p-3 rounded-lg ${isDark ? 'bg-gray-700/50' : 'bg-gray-100'}`}>
                  <label className={`text-xs uppercase ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Qtd Total</label>
                  <p className={`text-xl font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>{formatNumber(selectedItem.qtd_vendida_total)}</p>
                </div>
                <div className={`p-3 rounded-lg ${isDark ? 'bg-gray-700/50' : 'bg-gray-100'}`}>
                  <label className={`text-xs uppercase ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Cortesias</label>
                  <p className={`text-xl font-bold ${isDark ? 'text-yellow-400' : 'text-yellow-600'}`}>{formatNumber(selectedItem.cortesia_total)}</p>
                </div>
                <div className={`p-3 rounded-lg ${isDark ? 'bg-gray-700/50' : 'bg-gray-100'}`}>
                  <label className={`text-xs uppercase ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Insc. Líquida</label>
                  <p className={`text-xl font-bold ${isDark ? 'text-emerald-400' : 'text-emerald-600'}`}>{formatCurrency(selectedItem.inscricao_liquida_total)}</p>
                </div>
                <div className={`p-3 rounded-lg ${isDark ? 'bg-gray-700/50' : 'bg-gray-100'}`}>
                  <label className={`text-xs uppercase ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Ticket Médio</label>
                  <p className={`text-xl font-bold ${isDark ? 'text-blue-400' : 'text-blue-600'}`}>{formatCurrency(selectedItem.ticket_medio_total)}</p>
                </div>
              </div>

              <div className="grid grid-cols-3 gap-3">
                <div className={`p-3 rounded-lg ${isDark ? 'bg-gray-700/50' : 'bg-gray-100'}`}>
                  <label className={`text-xs uppercase ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Taxa Líquida</label>
                  <p className={`text-lg font-bold ${isDark ? 'text-purple-400' : 'text-purple-600'}`}>{formatCurrency(selectedItem.taxa_liquida_total)}</p>
                </div>
                <div className={`p-3 rounded-lg ${isDark ? 'bg-gray-700/50' : 'bg-gray-100'}`}>
                  <label className={`text-xs uppercase ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Kit/Produto</label>
                  <p className={`text-lg font-bold ${isDark ? 'text-pink-400' : 'text-pink-600'}`}>{formatCurrency(selectedItem.kit_produto_total)}</p>
                </div>
                <div className={`p-3 rounded-lg ${isDark ? 'bg-gray-700/50' : 'bg-gray-100'}`}>
                  <label className={`text-xs uppercase ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Valor Total</label>
                  <p className={`text-lg font-bold ${isDark ? 'text-emerald-400' : 'text-emerald-600'}`}>{formatCurrency(selectedItem.valor_total)}</p>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className={`p-4 rounded-lg ${isDark ? 'bg-purple-900/20' : 'bg-purple-50'}`}>
                  <div className="flex items-center gap-2 mb-2">
                    <Users className="w-5 h-5 text-purple-500" />
                    <label className={`text-sm font-semibold ${isDark ? 'text-purple-400' : 'text-purple-600'}`}>Grupos</label>
                  </div>
                  <p className={`text-2xl font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>{formatNumber(selectedItem.qtd_grupos_total)}</p>
                  <p className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>{formatCurrency(selectedItem.inscricao_liquida_grupos_total)}</p>
                </div>
                <div className={`p-4 rounded-lg ${isDark ? 'bg-orange-900/20' : 'bg-orange-50'}`}>
                  <div className="flex items-center gap-2 mb-2">
                    <ShoppingBag className="w-5 h-5 text-orange-500" />
                    <label className={`text-sm font-semibold ${isDark ? 'text-orange-400' : 'text-orange-600'}`}>Site</label>
                  </div>
                  <p className={`text-2xl font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>{formatNumber(selectedItem.qtd_site_total)}</p>
                  <p className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>{formatCurrency(selectedItem.inscricao_liquida_site_total)}</p>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className={`p-4 rounded-lg border-2 ${isDark ? 'bg-blue-900/20 border-blue-500/50' : 'bg-blue-50 border-blue-200'}`}>
                  <div className="flex items-center gap-2 mb-2">
                    <Store className="w-5 h-5 text-blue-500" />
                    <label className={`text-sm font-semibold ${isDark ? 'text-blue-400' : 'text-blue-600'}`}>Fonte: Ativo</label>
                  </div>
                  {selectedItem.por_fonte.ativo ? (
                    <div className="space-y-1">
                      <p className={`text-lg font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>{formatNumber(selectedItem.por_fonte.ativo.qtd)} inscritos</p>
                      <p className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>Insc. Líq: {formatCurrency(selectedItem.por_fonte.ativo.inscricao_liquida)}</p>
                      <p className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>Ticket: {formatCurrency(selectedItem.por_fonte.ativo.ticket_medio)}</p>
                    </div>
                  ) : (
                    <p className={`text-sm ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>Sem dados</p>
                  )}
                </div>
                <div className={`p-4 rounded-lg border-2 ${isDark ? 'bg-orange-900/20 border-orange-500/50' : 'bg-orange-50 border-orange-200'}`}>
                  <div className="flex items-center gap-2 mb-2">
                    <ShoppingBag className="w-5 h-5 text-orange-500" />
                    <label className={`text-sm font-semibold ${isDark ? 'text-orange-400' : 'text-orange-600'}`}>Fonte: Magento</label>
                  </div>
                  {selectedItem.por_fonte.magento ? (
                    <div className="space-y-1">
                      <p className={`text-lg font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>{formatNumber(selectedItem.por_fonte.magento.qtd)} inscritos</p>
                      <p className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>Insc. Líq: {formatCurrency(selectedItem.por_fonte.magento.inscricao_liquida)}</p>
                      <p className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>Ticket: {formatCurrency(selectedItem.por_fonte.magento.ticket_medio)}</p>
                    </div>
                  ) : (
                    <p className={`text-sm ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>Sem dados</p>
                  )}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default DadosConsolidados;