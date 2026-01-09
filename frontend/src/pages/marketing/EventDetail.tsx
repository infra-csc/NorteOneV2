import React from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { 
  ArrowLeft, 
  Calendar, 
  MapPin, 
  Users, 
  DollarSign,
  TrendingUp,
  TrendingDown,
  Activity,
  Target,
  AlertTriangle,
  Clock,
  CheckCircle,
  Info
} from 'lucide-react';
import { 
  LineChart, 
  Line, 
  BarChart, 
  Bar, 
  XAxis, 
  YAxis, 
  CartesianGrid, 
  Tooltip, 
  Legend, 
  ResponsiveContainer,
  ReferenceLine
} from 'recharts';
import { getEventById } from '../../data/mockMarketingData';
import { 
  getISCColor, 
  getISCEmoji, 
  isInCriticalWindow,
  getISCStatus
} from '../../types/marketingPerformance';

const EventDetail: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  
  const event = getEventById(id || '');
  
  if (!event) {
    return (
      <div className="p-6">
        <div className="bg-white dark:bg-gray-800 rounded-xl p-8 text-center">
          <p className="text-gray-500 dark:text-gray-400">Evento não encontrado.</p>
          <button
            onClick={() => navigate('/marketing')}
            className="mt-4 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
          >
            Voltar ao Dashboard
          </button>
        </div>
      </div>
    );
  }

  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat('pt-BR', {
      style: 'currency',
      currency: 'BRL'
    }).format(value);
  };

  const formatNumber = (value: number) => {
    return new Intl.NumberFormat('pt-BR').format(value);
  };

  const cumulativeData = event.dailySales.reduce((acc, day, index) => {
    const prevCumulative = index > 0 ? acc[index - 1].cumulative : 0;
    const prevExpected = index > 0 ? acc[index - 1].cumulativeExpected : 0;
    
    acc.push({
      date: day.date,
      cumulative: prevCumulative + day.sales,
      cumulativeExpected: prevExpected + day.expected,
      daily: day.sales
    });
    
    return acc;
  }, [] as { date: string; cumulative: number; cumulativeExpected: number; daily: number }[]);

  const last30Days = event.dailySales.slice(-30);

  const getRecommendationStyle = () => {
    if (event.iscStatus === 'accelerating') {
      return 'bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-800';
    }
    if (event.iscStatus === 'stable') {
      return 'bg-yellow-50 dark:bg-yellow-900/20 border-yellow-200 dark:border-yellow-800';
    }
    if (event.dMinus <= 40) {
      return 'bg-orange-50 dark:bg-orange-900/20 border-orange-200 dark:border-orange-800';
    }
    return 'bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800';
  };

  const gaugeRotation = Math.min(Math.max((event.isc - 0.5) * 180, 0), 180);

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center gap-4">
        <button
          onClick={() => navigate('/marketing')}
          className="p-2 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors"
        >
          <ArrowLeft className="w-5 h-5 text-gray-600 dark:text-gray-400" />
        </button>
        <div className="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400">
          <Link to="/marketing" className="hover:text-blue-600">Dashboard</Link>
          <span>/</span>
          <span className="text-gray-900 dark:text-white">{event.name}</span>
        </div>
      </div>

      <div className="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm border border-gray-200 dark:border-gray-700">
        <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
                {event.name}
              </h1>
              {isInCriticalWindow(event.dMinus) && (
                <span className="px-3 py-1 text-sm font-medium bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400 rounded-full flex items-center gap-1">
                  <Target className="w-4 h-4" />
                  JANELA CRÍTICA DE DECISÃO
                </span>
              )}
            </div>
            <div className="flex flex-wrap items-center gap-4 mt-2 text-sm text-gray-500 dark:text-gray-400">
              <span className="flex items-center gap-1">
                <Calendar className="w-4 h-4" />
                {new Date(event.date).toLocaleDateString('pt-BR', { 
                  day: '2-digit', 
                  month: 'long', 
                  year: 'numeric' 
                })}
              </span>
              <span className="flex items-center gap-1">
                <MapPin className="w-4 h-4" />
                {event.location}
              </span>
              <span className="flex items-center gap-1">
                <Users className="w-4 h-4" />
                Capacidade: {formatNumber(event.totalCapacity)}
              </span>
            </div>
          </div>
          <div className="px-4 py-2 bg-gray-100 dark:bg-gray-700 rounded-lg">
            <span className="text-sm text-gray-500 dark:text-gray-400">Categoria</span>
            <p className="font-medium text-gray-900 dark:text-white">{event.category}</p>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm border border-gray-200 dark:border-gray-700">
          <div className="flex items-center justify-between mb-4">
            <p className="text-sm text-gray-500 dark:text-gray-400">ISC Atual</p>
            <div className="group relative">
              <Info className="w-4 h-4 text-gray-400 cursor-help" />
              <div className="hidden group-hover:block absolute z-10 w-64 p-2 bg-gray-900 text-white text-xs rounded-lg right-0 top-6">
                Índice de Saúde Comercial: média de IA 7/30, Curva D-% e Rolling 14d
              </div>
            </div>
          </div>
          <div className="flex flex-col items-center">
            <div className="relative w-32 h-16 overflow-hidden">
              <div className="absolute w-32 h-32 rounded-full border-8 border-gray-200 dark:border-gray-600"></div>
              <div 
                className="absolute w-32 h-32 rounded-full border-8 border-transparent"
                style={{
                  borderTopColor: getISCColor(event.iscStatus),
                  borderRightColor: getISCColor(event.iscStatus),
                  transform: `rotate(${gaugeRotation - 90}deg)`,
                  transition: 'transform 0.5s ease-out'
                }}
              ></div>
            </div>
            <p 
              className="text-3xl font-bold mt-2"
              style={{ color: getISCColor(event.iscStatus) }}
            >
              {getISCEmoji(event.iscStatus)} {event.isc.toFixed(2)}
            </p>
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
              {event.iscStatus === 'accelerating' ? 'Acelerando' : 
               event.iscStatus === 'stable' ? 'Estável' : 'Desacelerando'}
            </p>
          </div>
        </div>

        <div className="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm border border-gray-200 dark:border-gray-700">
          <p className="text-sm text-gray-500 dark:text-gray-400">Dias para o Evento</p>
          <p className={`text-4xl font-bold mt-2 ${
            event.dMinus < 40 
              ? 'text-orange-600 dark:text-orange-400' 
              : 'text-gray-900 dark:text-white'
          }`}>
            D-{event.dMinus}
          </p>
          {event.dMinus < 40 && (
            <p className="text-xs text-orange-600 dark:text-orange-400 mt-2 flex items-center gap-1">
              <AlertTriangle className="w-3 h-3" />
              Fora da janela de promoção
            </p>
          )}
          {isInCriticalWindow(event.dMinus) && (
            <p className="text-xs text-amber-600 dark:text-amber-400 mt-2 flex items-center gap-1">
              <Target className="w-3 h-3" />
              Janela crítica D-45 a D-40
            </p>
          )}
        </div>

        <div className="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm border border-gray-200 dark:border-gray-700">
          <p className="text-sm text-gray-500 dark:text-gray-400">Vendas / Meta</p>
          <p className="text-2xl font-bold text-gray-900 dark:text-white mt-2">
            {formatNumber(event.currentSales)} / {formatNumber(event.salesGoal)}
          </p>
          <div className="mt-3 w-full bg-gray-200 dark:bg-gray-600 rounded-full h-3">
            <div 
              className="bg-blue-600 h-3 rounded-full transition-all"
              style={{ width: `${Math.min((event.currentSales / event.salesGoal) * 100, 100)}%` }}
            />
          </div>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-2">
            {Math.round((event.currentSales / event.salesGoal) * 100)}% da meta
          </p>
        </div>

        <div className="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm border border-gray-200 dark:border-gray-700">
          <p className="text-sm text-gray-500 dark:text-gray-400">Ticket Médio Atual</p>
          <p className="text-2xl font-bold text-gray-900 dark:text-white mt-2">
            {formatCurrency(event.averageTicket)}
          </p>
          <div className="flex items-center gap-1 mt-2 text-sm text-gray-500 dark:text-gray-400">
            <DollarSign className="w-4 h-4" />
            Receita estimada: {formatCurrency(event.currentSales * event.averageTicket)}
          </div>
        </div>
      </div>

      <div className={`rounded-xl p-4 border ${getRecommendationStyle()}`}>
        <div className="flex items-start gap-3">
          {event.iscStatus === 'accelerating' ? (
            <TrendingUp className="w-6 h-6 text-green-600 dark:text-green-400 mt-0.5" />
          ) : event.iscStatus === 'stable' ? (
            <Activity className="w-6 h-6 text-yellow-600 dark:text-yellow-400 mt-0.5" />
          ) : (
            <TrendingDown className="w-6 h-6 text-red-600 dark:text-red-400 mt-0.5" />
          )}
          <div>
            <h3 className="font-semibold text-gray-900 dark:text-white">
              Recomendação Automática
            </h3>
            <p className="text-gray-700 dark:text-gray-300 mt-1">
              {event.suggestedAction}
            </p>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm border border-gray-200 dark:border-gray-700">
          <h3 className="font-semibold text-gray-900 dark:text-white mb-4">
            Curva de Vendas Acumuladas vs Esperado
          </h3>
          <div className="h-80">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={cumulativeData.slice(-30)}>
                <CartesianGrid strokeDasharray="3 3" stroke="#374151" opacity={0.2} />
                <XAxis 
                  dataKey="date" 
                  tickFormatter={(value) => new Date(value).toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' })}
                  stroke="#6B7280"
                  fontSize={12}
                />
                <YAxis stroke="#6B7280" fontSize={12} />
                <Tooltip 
                  labelFormatter={(value) => new Date(value).toLocaleDateString('pt-BR')}
                  formatter={(value) => formatNumber(Number(value ?? 0))}
                  contentStyle={{ 
                    backgroundColor: '#1F2937', 
                    border: 'none', 
                    borderRadius: '8px',
                    color: '#fff'
                  }}
                />
                <Legend />
                <Line 
                  type="monotone" 
                  dataKey="cumulative" 
                  name="Vendas Reais"
                  stroke="#3B82F6" 
                  strokeWidth={2}
                  dot={false}
                />
                <Line 
                  type="monotone" 
                  dataKey="cumulativeExpected" 
                  name="Benchmark Esperado"
                  stroke="#9CA3AF" 
                  strokeWidth={2}
                  strokeDasharray="5 5"
                  dot={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm border border-gray-200 dark:border-gray-700">
          <h3 className="font-semibold text-gray-900 dark:text-white mb-4">
            Vendas Diárias (Últimos 30 dias)
          </h3>
          <div className="h-80">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={last30Days}>
                <CartesianGrid strokeDasharray="3 3" stroke="#374151" opacity={0.2} />
                <XAxis 
                  dataKey="date" 
                  tickFormatter={(value) => new Date(value).toLocaleDateString('pt-BR', { day: '2-digit' })}
                  stroke="#6B7280"
                  fontSize={12}
                />
                <YAxis stroke="#6B7280" fontSize={12} />
                <Tooltip 
                  labelFormatter={(value) => new Date(value).toLocaleDateString('pt-BR')}
                  formatter={(value) => formatNumber(Number(value ?? 0))}
                  contentStyle={{ 
                    backgroundColor: '#1F2937', 
                    border: 'none', 
                    borderRadius: '8px',
                    color: '#fff'
                  }}
                />
                <Bar 
                  dataKey="sales" 
                  name="Vendas"
                  fill="#3B82F6" 
                  radius={[4, 4, 0, 0]}
                />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      <div className="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm border border-gray-200 dark:border-gray-700">
        <h3 className="font-semibold text-gray-900 dark:text-white mb-4">
          Componentes do ISC
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className="p-4 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm text-gray-500 dark:text-gray-400">IA 7/30</span>
              <div className="group relative">
                <Info className="w-4 h-4 text-gray-400 cursor-help" />
                <div className="hidden group-hover:block absolute z-10 w-56 p-2 bg-gray-900 text-white text-xs rounded-lg right-0 top-6">
                  Índice de Aceleração: Vendas 7 dias / Vendas 30 dias × (30/7). {'>'} 1 = acelerando
                </div>
              </div>
            </div>
            <p className="text-2xl font-bold text-gray-900 dark:text-white">
              {event.iscComponents.ia730.toFixed(2)}
            </p>
            <div className="flex items-center gap-1 mt-2 text-sm">
              {event.iscComponents.ia730 > 1 ? (
                <>
                  <TrendingUp className="w-4 h-4 text-green-500" />
                  <span className="text-green-600 dark:text-green-400">Acelerando</span>
                </>
              ) : (
                <>
                  <TrendingDown className="w-4 h-4 text-red-500" />
                  <span className="text-red-600 dark:text-red-400">Desacelerando</span>
                </>
              )}
            </div>
          </div>

          <div className="p-4 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm text-gray-500 dark:text-gray-400">Curva D-%</span>
              <div className="group relative">
                <Info className="w-4 h-4 text-gray-400 cursor-help" />
                <div className="hidden group-hover:block absolute z-10 w-56 p-2 bg-gray-900 text-white text-xs rounded-lg right-0 top-6">
                  Vendas reais / Vendas esperadas para este D-. {'>'} 1 = adiantado
                </div>
              </div>
            </div>
            <p className="text-2xl font-bold text-gray-900 dark:text-white">
              {event.iscComponents.curvaDPercent.toFixed(2)}
            </p>
            <div className="flex items-center gap-1 mt-2 text-sm">
              {event.iscComponents.curvaDPercent > 1 ? (
                <>
                  <TrendingUp className="w-4 h-4 text-green-500" />
                  <span className="text-green-600 dark:text-green-400">Adiantado</span>
                </>
              ) : (
                <>
                  <TrendingDown className="w-4 h-4 text-red-500" />
                  <span className="text-red-600 dark:text-red-400">Atrasado</span>
                </>
              )}
            </div>
          </div>

          <div className="p-4 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm text-gray-500 dark:text-gray-400">Rolling 14d</span>
              <div className="group relative">
                <Info className="w-4 h-4 text-gray-400 cursor-help" />
                <div className="hidden group-hover:block absolute z-10 w-56 p-2 bg-gray-900 text-white text-xs rounded-lg right-0 top-6">
                  Média de vendas 14 dias (normalizada). {'>'} 1 = momentum quente
                </div>
              </div>
            </div>
            <p className="text-2xl font-bold text-gray-900 dark:text-white">
              {event.iscComponents.rolling14d.toFixed(2)}
            </p>
            <div className="flex items-center gap-1 mt-2 text-sm">
              {event.iscComponents.rolling14d > 1 ? (
                <>
                  <Activity className="w-4 h-4 text-green-500" />
                  <span className="text-green-600 dark:text-green-400">Momentum Quente</span>
                </>
              ) : (
                <>
                  <Activity className="w-4 h-4 text-blue-500" />
                  <span className="text-blue-600 dark:text-blue-400">Momentum Frio</span>
                </>
              )}
            </div>
          </div>
        </div>
      </div>

      <div className="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm border border-gray-200 dark:border-gray-700">
        <h3 className="font-semibold text-gray-900 dark:text-white mb-4">
          Timeline de Ações Comerciais
        </h3>
        {event.commercialActions.length > 0 ? (
          <div className="space-y-4">
            {event.commercialActions.map((action, index) => (
              <div key={action.id} className="flex gap-4">
                <div className="flex flex-col items-center">
                  <div className={`w-10 h-10 rounded-full flex items-center justify-center ${
                    action.type === 'price_increase' ? 'bg-green-100 dark:bg-green-900/30' :
                    action.type === 'price_decrease' ? 'bg-red-100 dark:bg-red-900/30' :
                    action.type === 'promotion' ? 'bg-purple-100 dark:bg-purple-900/30' :
                    action.type === 'campaign' ? 'bg-blue-100 dark:bg-blue-900/30' :
                    'bg-gray-100 dark:bg-gray-700'
                  }`}>
                    {action.type === 'price_increase' && <TrendingUp className="w-5 h-5 text-green-600" />}
                    {action.type === 'price_decrease' && <TrendingDown className="w-5 h-5 text-red-600" />}
                    {action.type === 'promotion' && <Target className="w-5 h-5 text-purple-600" />}
                    {action.type === 'campaign' && <Activity className="w-5 h-5 text-blue-600" />}
                    {action.type === 'communication' && <Clock className="w-5 h-5 text-gray-600" />}
                  </div>
                  {index < event.commercialActions.length - 1 && (
                    <div className="w-0.5 h-full bg-gray-200 dark:bg-gray-600 mt-2" />
                  )}
                </div>
                <div className="flex-1 pb-4">
                  <div className="flex items-center justify-between">
                    <p className="font-medium text-gray-900 dark:text-white">
                      {action.description}
                    </p>
                    <span className="text-sm text-gray-500 dark:text-gray-400">
                      {new Date(action.date).toLocaleDateString('pt-BR')}
                    </span>
                  </div>
                  {action.impact && (
                    <p className="text-sm text-green-600 dark:text-green-400 mt-1 flex items-center gap-1">
                      <CheckCircle className="w-4 h-4" />
                      {action.impact}
                    </p>
                  )}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-gray-500 dark:text-gray-400 text-center py-4">
            Nenhuma ação comercial registrada.
          </p>
        )}
      </div>
    </div>
  );
};

export default EventDetail;
