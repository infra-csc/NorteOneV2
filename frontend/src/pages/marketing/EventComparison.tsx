import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { 
  ArrowLeft, 
  Plus, 
  X, 
  TrendingUp, 
  TrendingDown,
  Activity,
  Info
} from 'lucide-react';
import { 
  LineChart, 
  Line, 
  XAxis, 
  YAxis, 
  CartesianGrid, 
  Tooltip, 
  Legend, 
  ResponsiveContainer 
} from 'recharts';
import { mockEvents } from '../../data/mockMarketingData';
import { getISCColor, getISCEmoji } from '../../types/marketingPerformance';
import { useTheme } from '../../context/ThemeContext';

const COLORS = ['#3B82F6', '#10B981', '#F59E0B', '#EF4444'];

const EventComparison: React.FC = () => {
  const { isDark } = useTheme();
  const [selectedEvents, setSelectedEvents] = useState<string[]>([]);
  
  const availableEvents = mockEvents.filter(e => !selectedEvents.includes(e.id));
  const compareEvents = mockEvents.filter(e => selectedEvents.includes(e.id));

  const addEvent = (eventId: string) => {
    if (selectedEvents.length < 4) {
      setSelectedEvents([...selectedEvents, eventId]);
    }
  };

  const removeEvent = (eventId: string) => {
    setSelectedEvents(selectedEvents.filter(id => id !== eventId));
  };

  const formatNumber = (value: number) => {
    return new Intl.NumberFormat('pt-BR').format(value);
  };

  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat('pt-BR', {
      style: 'currency',
      currency: 'BRL'
    }).format(value);
  };

  const getComparisonChartData = () => {
    if (compareEvents.length === 0) return [];
    
    const maxDays = Math.max(...compareEvents.map(e => e.dailySales.length));
    const data: Record<string, unknown>[] = [];
    
    for (let i = 0; i < maxDays; i++) {
      const dayData: Record<string, unknown> = { day: `D-${maxDays - i}` };
      
      compareEvents.forEach((event, idx) => {
        const sales = event.dailySales.slice(0, i + 1);
        const cumulative = sales.reduce((sum, d) => sum + d.sales, 0);
        dayData[event.name] = cumulative;
      });
      
      data.push(dayData);
    }
    
    return data.slice(-30);
  };

  const chartData = getComparisonChartData();

  return (
    <div className="min-h-screen">
      <div className="fixed inset-0 pointer-events-none overflow-hidden">
        <div className={`absolute top-0 left-1/4 w-96 h-96 ${isDark ? 'bg-blue-500/10' : 'bg-blue-400/20'} rounded-full blur-3xl animate-pulse`} />
        <div className={`absolute bottom-0 right-1/4 w-96 h-96 ${isDark ? 'bg-purple-500/10' : 'bg-purple-400/20'} rounded-full blur-3xl animate-pulse`} style={{ animationDelay: '1s' }} />
        <div className={`absolute top-1/2 left-1/2 w-64 h-64 ${isDark ? 'bg-indigo-500/5' : 'bg-indigo-400/15'} rounded-full blur-3xl animate-pulse`} style={{ animationDelay: '2s' }} />
      </div>

      <div className="relative z-10 p-6 space-y-6">
      <div className="flex items-center gap-4">
        <Link
          to="/marketing"
          className={`p-2 rounded-lg transition-colors ${isDark ? 'hover:bg-gray-700' : 'hover:bg-gray-100'}`}
        >
          <ArrowLeft className={`w-5 h-5 ${isDark ? 'text-gray-400' : 'text-gray-600'}`} />
        </Link>
        <div>
          <h1 className={`text-2xl font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>
            Comparativo de Eventos
          </h1>
          <p className={`mt-1 ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
            Compare até 4 eventos lado a lado
          </p>
        </div>
      </div>

      <div className="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm border border-gray-200 dark:border-gray-700">
        <h3 className="font-semibold text-gray-900 dark:text-white mb-4">
          Eventos Selecionados ({selectedEvents.length}/4)
        </h3>
        
        <div className="flex flex-wrap gap-3 mb-4">
          {compareEvents.map((event, idx) => (
            <div 
              key={event.id}
              className="flex items-center gap-2 px-3 py-2 rounded-lg border"
              style={{ borderColor: COLORS[idx] }}
            >
              <div 
                className="w-3 h-3 rounded-full"
                style={{ backgroundColor: COLORS[idx] }}
              />
              <span className="text-sm font-medium text-gray-900 dark:text-white">
                {event.name}
              </span>
              <button
                onClick={() => removeEvent(event.id)}
                className="p-1 hover:bg-gray-100 dark:hover:bg-gray-700 rounded"
              >
                <X className="w-4 h-4 text-gray-500" />
              </button>
            </div>
          ))}
          
          {selectedEvents.length < 4 && (
            <div className="relative">
              <select
                onChange={(e) => {
                  if (e.target.value) {
                    addEvent(e.target.value);
                    e.target.value = '';
                  }
                }}
                className="appearance-none px-4 py-2 pr-8 border border-dashed border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm cursor-pointer hover:border-blue-500 dark:hover:border-blue-400"
                defaultValue=""
              >
                <option value="" disabled>+ Adicionar evento</option>
                {availableEvents.map(event => (
                  <option key={event.id} value={event.id}>
                    {event.name} - D-{event.dMinus}
                  </option>
                ))}
              </select>
              <Plus className="absolute right-2 top-1/2 transform -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none" />
            </div>
          )}
        </div>

        {selectedEvents.length === 0 && (
          <div className="text-center py-8 text-gray-500 dark:text-gray-400">
            <Activity className="w-12 h-12 mx-auto mb-3 opacity-50" />
            <p>Selecione eventos para comparar</p>
            <p className="text-sm mt-1">Você pode comparar até 4 eventos simultaneamente</p>
          </div>
        )}
      </div>

      {selectedEvents.length >= 2 && (
        <>
          <div className="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm border border-gray-200 dark:border-gray-700">
            <h3 className="font-semibold text-gray-900 dark:text-white mb-4">
              Curvas de Vendas Sobrepostas
            </h3>
            <div className="h-80">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#374151" opacity={0.2} />
                  <XAxis 
                    dataKey="day" 
                    stroke="#6B7280"
                    fontSize={12}
                  />
                  <YAxis stroke="#6B7280" fontSize={12} />
                  <Tooltip 
                    formatter={(value) => formatNumber(Number(value ?? 0))}
                    contentStyle={{ 
                      backgroundColor: '#1F2937', 
                      border: 'none', 
                      borderRadius: '8px',
                      color: '#fff'
                    }}
                  />
                  <Legend />
                  {compareEvents.map((event, idx) => (
                    <Line 
                      key={event.id}
                      type="monotone" 
                      dataKey={event.name}
                      stroke={COLORS[idx]} 
                      strokeWidth={2}
                      dot={false}
                    />
                  ))}
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 overflow-hidden">
            <div className="p-4 border-b border-gray-200 dark:border-gray-700">
              <h3 className="font-semibold text-gray-900 dark:text-white">
                Tabela Comparativa
              </h3>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="bg-gray-50 dark:bg-gray-700/50">
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                      Métrica
                    </th>
                    {compareEvents.map((event, idx) => (
                      <th 
                        key={event.id} 
                        className="px-4 py-3 text-center text-xs font-medium uppercase"
                        style={{ color: COLORS[idx] }}
                      >
                        {event.name}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
                  <tr className="hover:bg-gray-50 dark:hover:bg-gray-700/50">
                    <td className="px-4 py-3 text-sm text-gray-500 dark:text-gray-400">
                      D- (Dias para evento)
                    </td>
                    {compareEvents.map(event => (
                      <td key={event.id} className="px-4 py-3 text-center font-medium text-gray-900 dark:text-white">
                        D-{event.dMinus}
                      </td>
                    ))}
                  </tr>
                  <tr className="hover:bg-gray-50 dark:hover:bg-gray-700/50">
                    <td className="px-4 py-3 text-sm text-gray-500 dark:text-gray-400">
                      <div className="flex items-center gap-1">
                        ISC
                        <div className="group relative">
                          <Info className="w-3 h-3 cursor-help" />
                          <div className="hidden group-hover:block absolute z-10 w-48 p-2 bg-gray-900 text-white text-xs rounded-lg left-0 top-5">
                            Índice de Saúde Comercial
                          </div>
                        </div>
                      </div>
                    </td>
                    {compareEvents.map(event => (
                      <td key={event.id} className="px-4 py-3 text-center">
                        <span 
                          className="font-bold"
                          style={{ color: getISCColor(event.iscStatus) }}
                        >
                          {getISCEmoji(event.iscStatus)} {event.isc.toFixed(2)}
                        </span>
                      </td>
                    ))}
                  </tr>
                  <tr className="hover:bg-gray-50 dark:hover:bg-gray-700/50">
                    <td className="px-4 py-3 text-sm text-gray-500 dark:text-gray-400">
                      IA 7/30
                    </td>
                    {compareEvents.map(event => (
                      <td key={event.id} className="px-4 py-3 text-center font-medium text-gray-900 dark:text-white">
                        <div className="flex items-center justify-center gap-1">
                          {event.iscComponents.ia730.toFixed(2)}
                          {event.iscComponents.ia730 > 1 ? (
                            <TrendingUp className="w-4 h-4 text-green-500" />
                          ) : (
                            <TrendingDown className="w-4 h-4 text-red-500" />
                          )}
                        </div>
                      </td>
                    ))}
                  </tr>
                  <tr className="hover:bg-gray-50 dark:hover:bg-gray-700/50">
                    <td className="px-4 py-3 text-sm text-gray-500 dark:text-gray-400">
                      Curva D-%
                    </td>
                    {compareEvents.map(event => (
                      <td key={event.id} className="px-4 py-3 text-center font-medium text-gray-900 dark:text-white">
                        <div className="flex items-center justify-center gap-1">
                          {event.iscComponents.curvaDPercent.toFixed(2)}
                          {event.iscComponents.curvaDPercent > 1 ? (
                            <TrendingUp className="w-4 h-4 text-green-500" />
                          ) : (
                            <TrendingDown className="w-4 h-4 text-red-500" />
                          )}
                        </div>
                      </td>
                    ))}
                  </tr>
                  <tr className="hover:bg-gray-50 dark:hover:bg-gray-700/50">
                    <td className="px-4 py-3 text-sm text-gray-500 dark:text-gray-400">
                      Rolling 14d
                    </td>
                    {compareEvents.map(event => (
                      <td key={event.id} className="px-4 py-3 text-center font-medium text-gray-900 dark:text-white">
                        {event.iscComponents.rolling14d.toFixed(2)}
                      </td>
                    ))}
                  </tr>
                  <tr className="hover:bg-gray-50 dark:hover:bg-gray-700/50">
                    <td className="px-4 py-3 text-sm text-gray-500 dark:text-gray-400">
                      Vendas Atuais
                    </td>
                    {compareEvents.map(event => (
                      <td key={event.id} className="px-4 py-3 text-center font-medium text-gray-900 dark:text-white">
                        {formatNumber(event.currentSales)}
                      </td>
                    ))}
                  </tr>
                  <tr className="hover:bg-gray-50 dark:hover:bg-gray-700/50">
                    <td className="px-4 py-3 text-sm text-gray-500 dark:text-gray-400">
                      Meta
                    </td>
                    {compareEvents.map(event => (
                      <td key={event.id} className="px-4 py-3 text-center font-medium text-gray-900 dark:text-white">
                        {formatNumber(event.salesGoal)}
                      </td>
                    ))}
                  </tr>
                  <tr className="hover:bg-gray-50 dark:hover:bg-gray-700/50">
                    <td className="px-4 py-3 text-sm text-gray-500 dark:text-gray-400">
                      % da Meta
                    </td>
                    {compareEvents.map(event => (
                      <td key={event.id} className="px-4 py-3 text-center">
                        <div className="flex flex-col items-center">
                          <span className="font-medium text-gray-900 dark:text-white">
                            {Math.round((event.currentSales / event.salesGoal) * 100)}%
                          </span>
                          <div className="w-16 bg-gray-200 dark:bg-gray-600 rounded-full h-1.5 mt-1">
                            <div 
                              className="bg-blue-600 h-1.5 rounded-full"
                              style={{ width: `${Math.min((event.currentSales / event.salesGoal) * 100, 100)}%` }}
                            />
                          </div>
                        </div>
                      </td>
                    ))}
                  </tr>
                  <tr className="hover:bg-gray-50 dark:hover:bg-gray-700/50">
                    <td className="px-4 py-3 text-sm text-gray-500 dark:text-gray-400">
                      Ticket Médio
                    </td>
                    {compareEvents.map(event => (
                      <td key={event.id} className="px-4 py-3 text-center font-medium text-gray-900 dark:text-white">
                        {formatCurrency(event.averageTicket)}
                      </td>
                    ))}
                  </tr>
                  <tr className="hover:bg-gray-50 dark:hover:bg-gray-700/50">
                    <td className="px-4 py-3 text-sm text-gray-500 dark:text-gray-400">
                      Categoria
                    </td>
                    {compareEvents.map(event => (
                      <td key={event.id} className="px-4 py-3 text-center text-sm text-gray-900 dark:text-white">
                        {event.category}
                      </td>
                    ))}
                  </tr>
                  <tr className="hover:bg-gray-50 dark:hover:bg-gray-700/50">
                    <td className="px-4 py-3 text-sm text-gray-500 dark:text-gray-400">
                      Local
                    </td>
                    {compareEvents.map(event => (
                      <td key={event.id} className="px-4 py-3 text-center text-sm text-gray-900 dark:text-white">
                        {event.location}
                      </td>
                    ))}
                  </tr>
                  <tr className="hover:bg-gray-50 dark:hover:bg-gray-700/50">
                    <td className="px-4 py-3 text-sm text-gray-500 dark:text-gray-400">
                      Ação Sugerida
                    </td>
                    {compareEvents.map(event => (
                      <td key={event.id} className="px-4 py-3 text-center text-sm text-gray-700 dark:text-gray-300">
                        {event.suggestedAction}
                      </td>
                    ))}
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}

      {selectedEvents.length === 1 && (
        <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-xl p-4 text-center">
          <p className="text-blue-700 dark:text-blue-300">
            Selecione pelo menos mais 1 evento para ver a comparação.
          </p>
        </div>
      )}
      </div>
    </div>
  );
};

export default EventComparison;
