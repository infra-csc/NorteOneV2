import React, { useState, useEffect, useRef } from 'react';
import {
  TrendingUp,
  TrendingDown,
  Activity,
  DollarSign,
  Target,
  Info,
  RefreshCw,
  Loader2,
  Zap,
  AlertTriangle,
  CheckCircle,
  ArrowUpRight,
  ArrowDownRight,
  Minus,
  HelpCircle,
  Gauge,
  BarChart3,
  ShieldCheck,
  LineChart
} from 'lucide-react';
import { pricingService, PricingEvent } from '../../services/api';
import { useTheme } from '../../context/ThemeContext';

interface EventPricingProps {
  eventoId: string;
  ano?: number;
}

interface MetricTooltipProps {
  label: string;
  description: string;
  interpretation: string;
  icon: React.ReactNode;
  isDark: boolean;
}

const MetricTooltip: React.FC<MetricTooltipProps> = ({ label, description, interpretation, icon, isDark }) => (
  <div className="group relative inline-flex items-center gap-1">
    <span className={`text-xs font-medium ${isDark ? 'text-gray-400' : 'text-gray-500'} flex items-center gap-1`}>
      {icon}
      {label}
    </span>
    <HelpCircle className={`w-3.5 h-3.5 ${isDark ? 'text-gray-500' : 'text-gray-400'} cursor-help`} />
    <div className="hidden group-hover:block absolute z-50 w-72 p-3 bg-gray-900 text-white text-xs rounded-xl shadow-xl left-0 top-6">
      <p className="font-semibold mb-1">{label}</p>
      <p className="text-gray-300 mb-2">{description}</p>
      <div className="border-t border-gray-700 pt-2">
        <p className="text-blue-300 font-medium">Como interpretar:</p>
        <p className="text-gray-300 mt-0.5">{interpretation}</p>
      </div>
      <div className="absolute -top-1.5 left-4 w-3 h-3 bg-gray-900 rotate-45"></div>
    </div>
  </div>
);

const EventPricing: React.FC<EventPricingProps> = ({ eventoId, ano }) => {
  const { isDark } = useTheme();
  const [evento, setEvento] = useState<PricingEvent | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  const fetchData = async (isRefresh = false) => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    const controller = new AbortController();
    abortControllerRef.current = controller;

    try {
      if (isRefresh) setRefreshing(true);
      else setLoading(true);
      setError(null);

      const response = await pricingService.getAnalysis({
        ano: ano || new Date().getFullYear(),
        status: 'all'
      }, controller.signal);

      if (!controller.signal.aborted) {
        const found = response.eventos.find(e => e.id === eventoId);
        if (found) {
          setEvento(found);
        } else {
          setError('Dados de pricing não disponíveis para este evento.');
        }
      }
    } catch (err: any) {
      if (err?.name === 'CanceledError' || err?.code === 'ERR_CANCELED') return;
      setError('Erro ao carregar dados de pricing.');
    } finally {
      if (!controller.signal.aborted) {
        setLoading(false);
        setRefreshing(false);
      }
    }
  };

  useEffect(() => {
    fetchData();
    return () => { abortControllerRef.current?.abort(); };
  }, [eventoId, ano]);

  const getDecisionColor = (action: string): string => {
    switch (action) {
      case 'increase_now': return '#22c55e';
      case 'increase_gradual': return '#84cc16';
      case 'maintain': return '#eab308';
      case 'decrease': return '#ef4444';
      default: return '#6b7280';
    }
  };

  const getDecisionLabel = (action: string): string => {
    switch (action) {
      case 'increase_now': return 'Subir Agora';
      case 'increase_gradual': return 'Subir Gradual';
      case 'maintain': return 'Manter';
      case 'decrease': return 'Reduzir';
      default: return action;
    }
  };

  const getDecisionIcon = (action: string) => {
    switch (action) {
      case 'increase_now': return <ArrowUpRight className="w-5 h-5" />;
      case 'increase_gradual': return <TrendingUp className="w-5 h-5" />;
      case 'maintain': return <Minus className="w-5 h-5" />;
      case 'decrease': return <ArrowDownRight className="w-5 h-5" />;
      default: return <Activity className="w-5 h-5" />;
    }
  };

  const getDecisionBg = (action: string): string => {
    switch (action) {
      case 'increase_now': return isDark ? 'bg-green-900/30 border-green-700' : 'bg-green-50 border-green-200';
      case 'increase_gradual': return isDark ? 'bg-lime-900/30 border-lime-700' : 'bg-lime-50 border-lime-200';
      case 'maintain': return isDark ? 'bg-yellow-900/30 border-yellow-700' : 'bg-yellow-50 border-yellow-200';
      case 'decrease': return isDark ? 'bg-red-900/30 border-red-700' : 'bg-red-50 border-red-200';
      default: return isDark ? 'bg-gray-800 border-gray-700' : 'bg-gray-50 border-gray-200';
    }
  };

  const formatCurrency = (value: number): string => {
    return new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(value);
  };

  const formatNumber = (value: number): string => {
    return new Intl.NumberFormat('pt-BR').format(value);
  };

  const getMetricColor = (value: number, greenAbove: number, redBelow: number): string => {
    if (value > greenAbove) return 'text-green-500';
    if (value < redBelow) return 'text-red-500';
    return 'text-yellow-500';
  };

  const cardBg = isDark ? 'bg-gray-800' : 'bg-white';
  const textColor = isDark ? 'text-white' : 'text-gray-900';
  const textMuted = isDark ? 'text-gray-400' : 'text-gray-500';
  const borderColor = isDark ? 'border-gray-700' : 'border-gray-200';
  const metricBg = isDark ? 'bg-gray-700/50' : 'bg-gray-50';

  if (loading) {
    return (
      <div className={`${cardBg} rounded-xl border ${borderColor} p-12 text-center`}>
        <Loader2 className={`w-8 h-8 animate-spin mx-auto ${textMuted}`} />
        <p className={`mt-3 ${textMuted}`}>Carregando analise de pricing...</p>
      </div>
    );
  }

  if (error || !evento) {
    return (
      <div className={`${cardBg} rounded-xl border ${borderColor} p-8 text-center`}>
        <AlertTriangle className={`w-10 h-10 mx-auto ${textMuted} mb-3`} />
        <p className={textColor}>{error || 'Dados de pricing não disponíveis.'}</p>
        <button
          onClick={() => fetchData()}
          className="mt-4 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors text-sm"
        >
          Tentar Novamente
        </button>
      </div>
    );
  }

  const m = evento.pricingMetrics;

  return (
    <div className="space-y-6">
      <div className={`${getDecisionBg(evento.decision.action)} rounded-xl border p-5`}>
        <div className="flex items-start gap-4">
          <div
            className="p-3 rounded-xl text-white flex-shrink-0"
            style={{ backgroundColor: getDecisionColor(evento.decision.action) }}
          >
            {getDecisionIcon(evento.decision.action)}
          </div>
          <div className="flex-1">
            <div className="flex items-center justify-between">
              <div>
                <h3 className={`text-lg font-bold ${textColor}`}>
                  Recomendação: {getDecisionLabel(evento.decision.action)}
                </h3>
                <p className={`text-sm mt-1 ${textMuted}`}>{evento.decision.reason}</p>
              </div>
              <div className="flex items-center gap-2">
                <span className={`text-xs px-3 py-1.5 rounded-full font-medium ${
                  evento.decision.confidence === 'high'
                    ? 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-400'
                    : evento.decision.confidence === 'medium'
                    ? 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/40 dark:text-yellow-400'
                    : 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-400'
                }`}>
                  Confiança: {evento.decision.confidence === 'high' ? 'Alta' : evento.decision.confidence === 'medium' ? 'Média' : 'Baixa'}
                </span>
                <button
                  onClick={() => fetchData(true)}
                  disabled={refreshing}
                  className={`p-2 rounded-lg ${isDark ? 'hover:bg-gray-700' : 'hover:bg-gray-100'} transition-colors`}
                  title="Atualizar dados"
                >
                  <RefreshCw className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''} ${textMuted}`} />
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className={`${cardBg} rounded-xl p-4 border ${borderColor}`}>
          <MetricTooltip
            label="Rolling Index"
            description="Compara o ritmo atual de vendas (média 14 dias) com o pace necessário para atingir a meta."
            interpretation="Acima de 1.2 = vendas acima do esperado (verde). Abaixo de 0.8 = vendas abaixo do esperado (vermelho). Entre 0.8 e 1.2 = ritmo normal (amarelo)."
            icon={<Gauge className="w-3.5 h-3.5" />}
            isDark={isDark}
          />
          <p className={`text-2xl font-bold mt-2 ${getMetricColor(m.rollingIndex, 1.2, 0.8)}`}>
            {m.rollingIndex.toFixed(2)}
          </p>
          <p className={`text-xs mt-1 ${textMuted}`}>
            {m.rollingIndex > 1.2 ? 'Acima do esperado' : m.rollingIndex < 0.8 ? 'Abaixo do esperado' : 'No ritmo'}
          </p>
        </div>

        <div className={`${cardBg} rounded-xl p-4 border ${borderColor}`}>
          <MetricTooltip
            label="IED"
            description="Índice de Eficiência de Demanda. Mede a proporção entre vendas acumuladas e o esperado para o momento atual baseado na curva D-."
            interpretation="Acima de 1.1 = demanda acima do esperado. Abaixo de 0.9 = demanda fraca. Ideal é manter acima de 1.0."
            icon={<BarChart3 className="w-3.5 h-3.5" />}
            isDark={isDark}
          />
          <p className={`text-2xl font-bold mt-2 ${getMetricColor(m.ied, 1.1, 0.9)}`}>
            {m.ied.toFixed(2)}
          </p>
          <p className={`text-xs mt-1 ${textMuted}`}>
            {m.ied > 1.1 ? 'Demanda forte' : m.ied < 0.9 ? 'Demanda fraca' : 'Demanda normal'}
          </p>
        </div>

        <div className={`${cardBg} rounded-xl p-4 border ${borderColor}`}>
          <MetricTooltip
            label="IA"
            description="Índice de Aceleração. Mede se o ritmo de vendas está acelerando ou desacelerando em relação ao período anterior."
            interpretation="Acima de 1.2 = vendas acelerando (bom sinal). Abaixo de 0.9 = vendas desacelerando (atenção). Perto de 1.0 = ritmo estável."
            icon={<Zap className="w-3.5 h-3.5" />}
            isDark={isDark}
          />
          <p className={`text-2xl font-bold mt-2 ${getMetricColor(m.ia, 1.2, 0.9)}`}>
            {m.ia.toFixed(2)}
          </p>
          <p className={`text-xs mt-1 ${textMuted}`}>
            {m.ia > 1.2 ? 'Acelerando' : m.ia < 0.9 ? 'Desacelerando' : 'Estável'}
          </p>
        </div>

        <div className={`${cardBg} rounded-xl p-4 border ${borderColor}`}>
          <MetricTooltip
            label="FEM"
            description="Fator de Elasticidade de Margem. Indica o quanto a margem pode ser ajustada com base no custo do kit e ticket médio."
            interpretation="Valores altos significam boa margem para ajustes de preço. Valores baixos indicam margem apertada — cuidado ao alterar preços."
            icon={<LineChart className="w-3.5 h-3.5" />}
            isDark={isDark}
          />
          <p className={`text-2xl font-bold mt-2 ${textColor}`}>
            {m.fem.toFixed(2)}
          </p>
          <p className={`text-xs mt-1 ${textMuted}`}>
            Margem: {formatCurrency(evento.averageTicket - evento.kitCost)}
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className={`${cardBg} rounded-xl border ${borderColor} p-5`}>
          <h4 className={`font-semibold mb-4 ${textColor} flex items-center gap-2`}>
            <Activity className="w-4 h-4 text-blue-500" />
            Ritmo de Vendas
          </h4>
          <div className="grid grid-cols-2 gap-4">
            <div className={`${metricBg} rounded-xl p-4`}>
              <MetricTooltip
                label="Rolling 14d"
                description="Média de vendas diárias nos últimos 14 dias. Representa o ritmo recente de vendas."
                interpretation="Compare com o Pace Necessário: se Rolling 14d > Pace, as vendas estão num bom ritmo."
                icon={<TrendingUp className="w-3.5 h-3.5" />}
                isDark={isDark}
              />
              <p className={`text-xl font-bold mt-2 ${textColor}`}>{m.rollingAvg14d.toFixed(1)}</p>
              <p className={`text-xs ${textMuted}`}>vendas/dia</p>
              {m.rollingAvg14dLastYear > 0 && (
                <p className={`text-xs mt-1 ${textMuted}`}>
                  Ano anterior: {m.rollingAvg14dLastYear.toFixed(1)}/dia
                </p>
              )}
            </div>

            <div className={`${metricBg} rounded-xl p-4`}>
              <MetricTooltip
                label="Pace Necessário"
                description="Ritmo diário de vendas necessário para atingir a meta até a data do evento."
                interpretation="Se o Rolling 14d está acima deste valor, o evento está no caminho certo para bater a meta."
                icon={<Target className="w-3.5 h-3.5" />}
                isDark={isDark}
              />
              <p className={`text-xl font-bold mt-2 ${m.rollingAvg14d >= m.paceRequired ? 'text-green-500' : 'text-red-500'}`}>
                {m.paceRequired.toFixed(1)}
              </p>
              <p className={`text-xs ${textMuted}`}>vendas/dia</p>
            </div>

            <div className={`${metricBg} rounded-xl p-4`}>
              <MetricTooltip
                label="Pace de Segurança"
                description="Ritmo mínimo diário para garantir que o evento atinja pelo menos o ponto de equilíbrio (break-even)."
                interpretation="Se o Rolling 14d cair abaixo deste valor, é sinal de alerta — considere ações de marketing."
                icon={<ShieldCheck className="w-3.5 h-3.5" />}
                isDark={isDark}
              />
              <p className={`text-xl font-bold mt-2 ${m.rollingAvg14d >= m.paceSeguranca ? 'text-green-500' : 'text-amber-500'}`}>
                {m.paceSeguranca.toFixed(1)}
              </p>
              <p className={`text-xs ${textMuted}`}>vendas/dia (mínimo)</p>
            </div>

            <div className={`${metricBg} rounded-xl p-4`}>
              <MetricTooltip
                label="Projeção Final"
                description="Número estimado de vendas até o evento, baseado no ritmo atual de vendas (Rolling 14d)."
                interpretation="Compare com a meta para saber se o evento tende a bater ou não o objetivo."
                icon={<TrendingUp className="w-3.5 h-3.5" />}
                isDark={isDark}
              />
              <p className={`text-xl font-bold mt-2 ${m.projection >= evento.salesGoal ? 'text-green-500' : 'text-red-500'}`}>
                {formatNumber(m.projection)}
              </p>
              <p className={`text-xs ${textMuted}`}>
                Meta: {formatNumber(evento.salesGoal)}
              </p>
            </div>
          </div>
        </div>

        <div className={`${cardBg} rounded-xl border ${borderColor} p-5`}>
          <h4 className={`font-semibold mb-4 ${textColor} flex items-center gap-2`}>
            <DollarSign className="w-4 h-4 text-green-500" />
            Simulador de Elasticidade
            <div className="group relative ml-1">
              <HelpCircle className={`w-4 h-4 ${textMuted} cursor-help`} />
              <div className="hidden group-hover:block absolute z-50 w-72 p-3 bg-gray-900 text-white text-xs rounded-xl shadow-xl left-0 top-6">
                <p className="font-semibold mb-1">Como funciona</p>
                <p className="text-gray-300">Simula cenários de aumento de preço mostrando o novo valor, a nova margem por inscrição, a queda máxima aceitável de volume para manter a receita, e o pace mínimo necessário.</p>
                <div className="absolute -top-1.5 left-4 w-3 h-3 bg-gray-900 rotate-45"></div>
              </div>
            </div>
          </h4>

          <div className="mb-4 grid grid-cols-2 gap-3">
            <div className={`${metricBg} rounded-lg p-3`}>
              <p className={`text-xs ${textMuted}`}>Ticket Médio Atual</p>
              <p className={`text-lg font-bold ${textColor}`}>{formatCurrency(evento.averageTicket)}</p>
            </div>
            <div className={`${metricBg} rounded-lg p-3`}>
              <div className="flex items-center gap-1 mb-0.5">
                <p className={`text-xs ${textMuted}`}>Custo Kit</p>
                {evento.kitBreakdown && evento.kitBreakdown.length > 0 && (
                  <div className="group relative">
                    <Info className={`w-3.5 h-3.5 ${textMuted} cursor-help flex-shrink-0`} />
                    <div className="hidden group-hover:block absolute z-50 w-60 p-3 bg-gray-900 text-white text-xs rounded-xl shadow-xl left-0 top-5 pointer-events-none">
                      <p className="font-semibold mb-2 text-gray-200">Custo por tipo de kit</p>
                      <div className="space-y-1">
                        {evento.kitBreakdown.map((k, i) => (
                          <div key={i} className="flex justify-between items-center gap-3">
                            <span className="text-gray-300 truncate">{k.tipoKit}</span>
                            <span className="font-medium text-white whitespace-nowrap">
                              {k.custoKit != null ? formatCurrency(k.custoKit) : '—'}
                            </span>
                          </div>
                        ))}
                      </div>
                      <div className="absolute -top-1.5 left-4 w-3 h-3 bg-gray-900 rotate-45"></div>
                    </div>
                  </div>
                )}
              </div>
              <p className={`text-lg font-bold ${textColor}`}>{formatCurrency(evento.kitCost)}</p>
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className={`${textMuted} border-b ${borderColor}`}>
                  <th className="text-left py-2.5 px-2 font-medium">Aumento</th>
                  <th className="text-right py-2.5 px-2 font-medium">Novo Preço</th>
                  <th className="text-right py-2.5 px-2 font-medium">Nova Margem</th>
                  <th className="text-right py-2.5 px-2 font-medium">Queda Aceitável</th>
                  <th className="text-right py-2.5 px-2 font-medium">Pace Mín</th>
                </tr>
              </thead>
              <tbody>
                {evento.elasticityScenarios.map((scenario, idx) => (
                  <tr key={idx} className={`border-b ${borderColor} ${isDark ? 'hover:bg-gray-700/50' : 'hover:bg-gray-50'} transition-colors`}>
                    <td className={`py-2.5 px-2 ${textColor} font-semibold`}>
                      <span className="inline-flex items-center gap-1">
                        <ArrowUpRight className="w-3.5 h-3.5 text-green-500" />
                        +{scenario.priceIncrease}%
                      </span>
                    </td>
                    <td className={`py-2.5 px-2 text-right ${textColor}`}>{formatCurrency(scenario.newPrice)}</td>
                    <td className="py-2.5 px-2 text-right text-green-500 font-medium">{formatCurrency(scenario.newMargin)}</td>
                    <td className="py-2.5 px-2 text-right text-yellow-500">{scenario.acceptableVolumeDrop.toFixed(1)}%</td>
                    <td className={`py-2.5 px-2 text-right ${textColor}`}>{scenario.minPace.toFixed(1)}/dia</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <div className={`${cardBg} rounded-xl border ${borderColor} p-5`}>
        <h4 className={`font-semibold mb-4 ${textColor} flex items-center gap-2`}>
          <Target className="w-4 h-4 text-purple-500" />
          Resumo de Vendas
        </h4>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className={`${metricBg} rounded-xl p-4 text-center`}>
            <p className={`text-xs ${textMuted} mb-1`}>Vendas Atuais</p>
            <p className={`text-2xl font-bold ${textColor}`}>{formatNumber(evento.currentSales)}</p>
          </div>
          <div className={`${metricBg} rounded-xl p-4 text-center`}>
            <p className={`text-xs ${textMuted} mb-1`}>Meta</p>
            <p className={`text-2xl font-bold ${textColor}`}>{formatNumber(evento.salesGoal)}</p>
          </div>
          <div className={`${metricBg} rounded-xl p-4 text-center`}>
            <p className={`text-xs ${textMuted} mb-1`}>% Atingido</p>
            <p className={`text-2xl font-bold ${evento.salesGoal > 0 && (evento.currentSales / evento.salesGoal) >= 0.8 ? 'text-green-500' : 'text-yellow-500'}`}>
              {evento.salesGoal > 0 ? ((evento.currentSales / evento.salesGoal) * 100).toFixed(1) : '0'}%
            </p>
          </div>
          <div className={`${metricBg} rounded-xl p-4 text-center`}>
            <p className={`text-xs ${textMuted} mb-1`}>D-</p>
            <p className={`text-2xl font-bold ${evento.dMinus <= 40 ? 'text-amber-500' : textColor}`}>
              {evento.dMinus}
            </p>
            <p className={`text-xs ${textMuted}`}>dias até o evento</p>
          </div>
        </div>
      </div>
    </div>
  );
};

export default EventPricing;
