import React, { useState, useEffect, useMemo, useCallback } from 'react';
import {
  Target,
  TrendingUp,
  TrendingDown,
  DollarSign,
  Users,
  Zap,
  Info,
  Loader2,
  BarChart3,
  ArrowUpRight,
  ArrowDownRight,
  Minus,
} from 'lucide-react';
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
  Legend,
} from 'recharts';
import { marketingService } from '../../services/api';

interface EventSimulatorProps {
  eventoId: string;
  ano: number;
  isDark: boolean;
}

const formatNumber = (n: number) => n.toLocaleString('pt-BR');
const formatCurrency = (n: number) => `R$ ${n.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

const InfoTooltip = ({ text, isDark }: { text: string; isDark: boolean }) => (
  <div className="relative group inline-flex">
    <Info className="w-3.5 h-3.5 text-gray-400 dark:text-gray-500 cursor-help" />
    <div className={`absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-3 py-2 ${isDark ? 'bg-gray-700' : 'bg-gray-900'} text-white text-xs rounded-lg shadow-lg opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none w-64 z-50`}>
      {text}
    </div>
  </div>
);

export default function EventSimulator({ eventoId, ano, isDark }: EventSimulatorProps) {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [metaCustom, setMetaCustom] = useState<number | null>(null);
  const [ticketCustom, setTicketCustom] = useState<number | null>(null);
  const [taxaCrescimento, setTaxaCrescimento] = useState<number>(0);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    marketingService.getSimulacao(eventoId, controller.signal, ano)
      .then((res: any) => {
        if (!controller.signal.aborted) {
          setData(res);
          setMetaCustom(res.evento.meta_orcada);
          setTicketCustom(Math.round(res.atual.ticket_medio));
        }
      })
      .catch((err: any) => {
        if (err?.name !== 'AbortError' && err?.code !== 'ERR_CANCELED') {
          setError('Erro ao carregar dados da simulação');
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [eventoId, ano]);

  const meta = metaCustom ?? data?.evento?.meta_orcada ?? 0;
  const ticket = ticketCustom ?? data?.atual?.ticket_medio ?? 0;
  const taxaMultiplier = 1 + (taxaCrescimento / 100);

  const simulacao = useMemo(() => {
    if (!data) return null;
    const { atual, evento, cenarios } = data;
    const diasRestantes = Math.max(0, evento.dias_ate_evento);

    const ritmoAtual = atual.media_14d * taxaMultiplier;
    const projVendas = atual.total_vendas + Math.round(ritmoAtual * diasRestantes);
    const projReceita = atual.total_receita + ritmoAtual * diasRestantes * ticket;
    const pctMeta = meta > 0 ? Math.round(projVendas / meta * 1000) / 10 : 0;
    const gapVendas = Math.max(0, meta - projVendas);
    const receitaMeta = meta * ticket;
    const gapReceita = Math.max(0, receitaMeta - projReceita);
    const ritmoNecessario = diasRestantes > 0 && meta > atual.total_vendas
      ? Math.round((meta - atual.total_vendas) / diasRestantes * 10) / 10
      : 0;

    const pessRitmo = cenarios.pessimista.ritmo_diario * taxaMultiplier;
    const otimRitmo = cenarios.otimista.ritmo_diario * taxaMultiplier;
    const pessVendas = atual.total_vendas + Math.round(pessRitmo * diasRestantes);
    const otimVendas = atual.total_vendas + Math.round(otimRitmo * diasRestantes);

    return {
      ritmoAtual: Math.round(ritmoAtual * 10) / 10,
      projVendas,
      projReceita: Math.round(projReceita * 100) / 100,
      pctMeta,
      gapVendas,
      receitaMeta: Math.round(receitaMeta * 100) / 100,
      gapReceita: Math.round(gapReceita * 100) / 100,
      ritmoNecessario,
      pessVendas,
      otimVendas,
      pessRitmo: Math.round(pessRitmo * 10) / 10,
      otimRitmo: Math.round(otimRitmo * 10) / 10,
      diasRestantes,
    };
  }, [data, meta, ticket, taxaCrescimento, taxaMultiplier]);

  const chartData = useMemo(() => {
    if (!data || !simulacao) return [];
    const { vendas_diarias, atual, evento } = data;
    const diasRestantes = Math.max(0, evento.dias_ate_evento);
    if (!vendas_diarias || vendas_diarias.length === 0) return [];

    let acum = 0;
    const points: any[] = [];
    for (const d of vendas_diarias) {
      acum += d.vendas;
      points.push({
        date: d.date,
        label: new Date(d.date + 'T12:00:00').toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' }),
        real: acum,
      });
    }

    if (diasRestantes > 0 && points.length > 0) {
      const lastDate = new Date(vendas_diarias[vendas_diarias.length - 1].date + 'T12:00:00');
      const lastAcum = acum;

      let acumReal = lastAcum;
      let acumPess = lastAcum;
      let acumOtim = lastAcum;

      for (let i = 1; i <= diasRestantes; i++) {
        const nextDate = new Date(lastDate);
        nextDate.setDate(nextDate.getDate() + i);
        const dateStr = nextDate.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' });

        acumReal += simulacao.ritmoAtual;
        acumPess += simulacao.pessRitmo;
        acumOtim += simulacao.otimRitmo;

        points.push({
          date: nextDate.toISOString().split('T')[0],
          label: dateStr,
          projecao_realista: Math.round(acumReal),
          projecao_pessimista: Math.round(acumPess),
          projecao_otimista: Math.round(acumOtim),
          isProjection: true,
        });
      }

      if (points.length > 0) {
        const transitionIdx = points.findIndex(p => p.isProjection);
        if (transitionIdx > 0) {
          points[transitionIdx].real = points[transitionIdx - 1].real;
        }
      }
    }

    return points;
  }, [data, simulacao]);

  const handleResetMeta = useCallback(() => {
    if (data) setMetaCustom(data.evento.meta_orcada);
  }, [data]);

  const handleResetTicket = useCallback(() => {
    if (data) setTicketCustom(Math.round(data.atual.ticket_medio));
  }, [data]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-96">
        <div className="text-center">
          <Loader2 className="w-10 h-10 animate-spin text-indigo-500 mx-auto mb-3" />
          <p className="text-gray-500 dark:text-gray-400">Carregando simulação...</p>
        </div>
      </div>
    );
  }

  if (error || !data || !simulacao) {
    return (
      <div className="flex items-center justify-center h-64 text-gray-500 dark:text-gray-400">
        {error || 'Sem dados disponíveis para simulação.'}
      </div>
    );
  }

  const { atual, evento } = data;
  const metaChanged = meta !== data.evento.meta_orcada;
  const ticketChanged = ticketCustom !== Math.round(data.atual.ticket_medio);
  const hasTaxa = taxaCrescimento !== 0;

  const statusColor = simulacao.pctMeta >= 100
    ? 'from-emerald-500 to-green-600'
    : simulacao.pctMeta >= 85
      ? 'from-amber-500 to-yellow-600'
      : 'from-red-500 to-rose-600';

  const statusText = simulacao.pctMeta >= 100
    ? 'Meta Atingível'
    : simulacao.pctMeta >= 85
      ? 'Atenção Necessária'
      : 'Risco Alto';

  const statusIcon = simulacao.pctMeta >= 100
    ? <ArrowUpRight className="w-5 h-5" />
    : simulacao.pctMeta >= 85
      ? <Minus className="w-5 h-5" />
      : <ArrowDownRight className="w-5 h-5" />;

  const cardBase = `rounded-xl border shadow-sm transition-all duration-300`;
  const cardBg = isDark ? 'bg-gray-800 border-gray-700' : 'bg-white border-gray-200';

  const xAxisInterval = chartData.length > 30 ? Math.floor(chartData.length / 12) : chartData.length > 15 ? Math.floor(chartData.length / 8) : 0;

  return (
    <div className="space-y-6">
      <div className={`${cardBase} ${isDark ? 'bg-gradient-to-r from-indigo-900/50 to-purple-900/50 border-indigo-700/50' : 'bg-gradient-to-r from-indigo-50 to-purple-50 border-indigo-200'} p-6`}>
        <div className="flex items-center justify-between mb-5">
          <div className="flex items-center gap-3">
            <div className={`p-2.5 rounded-xl bg-gradient-to-br from-indigo-500 to-purple-600 text-white shadow-lg`}>
              <Zap className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-lg font-bold text-gray-900 dark:text-white">Simulador de Cenários</h3>
              <p className="text-sm text-gray-500 dark:text-gray-400">Ajuste os parâmetros para simular diferentes cenários</p>
            </div>
          </div>
          <div className={`px-4 py-2 rounded-full bg-gradient-to-r ${statusColor} text-white text-sm font-semibold flex items-center gap-1.5 shadow-md`}>
            {statusIcon}
            {statusText} ({simulacao.pctMeta}%)
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
          <div className={`${cardBase} ${cardBg} p-4`}>
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <Target className="w-4 h-4 text-indigo-500" />
                <span className="text-sm font-semibold text-gray-700 dark:text-gray-300">Meta de Inscrições</span>
                <InfoTooltip text="Meta de inscrições para o evento. Ajuste para simular cenários com metas diferentes." isDark={isDark} />
              </div>
              {metaChanged && (
                <button onClick={handleResetMeta} className="text-[10px] text-indigo-500 hover:text-indigo-700 font-medium">
                  Resetar
                </button>
              )}
            </div>
            <input
              type="range"
              min={Math.round(data.evento.meta_orcada * 0.5)}
              max={Math.round(data.evento.meta_orcada * 1.5)}
              step={50}
              value={meta}
              onChange={(e) => setMetaCustom(Number(e.target.value))}
              className="w-full h-2 bg-gray-200 dark:bg-gray-600 rounded-lg appearance-none cursor-pointer accent-indigo-500 mb-2"
            />
            <div className="flex justify-between items-center">
              <input
                type="number"
                value={meta}
                onChange={(e) => setMetaCustom(Number(e.target.value) || 0)}
                className={`w-28 text-xl font-bold ${isDark ? 'bg-gray-700 text-white border-gray-600' : 'bg-gray-50 text-gray-900 border-gray-300'} border rounded-lg px-3 py-1 text-center`}
              />
              <span className="text-xs text-gray-400">
                Orçado: {formatNumber(data.evento.meta_orcada)}
              </span>
            </div>
          </div>

          <div className={`${cardBase} ${cardBg} p-4`}>
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <DollarSign className="w-4 h-4 text-emerald-500" />
                <span className="text-sm font-semibold text-gray-700 dark:text-gray-300">Ticket Médio Alvo</span>
                <InfoTooltip text="Ticket médio usado na projeção de receita. O valor atual é o ticket médio real das vendas até agora." isDark={isDark} />
              </div>
              {ticketChanged && (
                <button onClick={handleResetTicket} className="text-[10px] text-emerald-500 hover:text-emerald-700 font-medium">
                  Resetar
                </button>
              )}
            </div>
            <input
              type="range"
              min={Math.round(data.atual.ticket_medio * 0.5)}
              max={Math.round(data.atual.ticket_medio * 2)}
              step={5}
              value={ticket}
              onChange={(e) => setTicketCustom(Number(e.target.value))}
              className="w-full h-2 bg-gray-200 dark:bg-gray-600 rounded-lg appearance-none cursor-pointer accent-emerald-500 mb-2"
            />
            <div className="flex justify-between items-center">
              <div className="flex items-center gap-1">
                <span className="text-sm text-gray-500 dark:text-gray-400">R$</span>
                <input
                  type="number"
                  value={ticket}
                  onChange={(e) => setTicketCustom(Number(e.target.value) || 0)}
                  className={`w-24 text-xl font-bold ${isDark ? 'bg-gray-700 text-white border-gray-600' : 'bg-gray-50 text-gray-900 border-gray-300'} border rounded-lg px-3 py-1 text-center`}
                />
              </div>
              <span className="text-xs text-gray-400">
                Real: R$ {data.atual.ticket_medio.toFixed(0)}
              </span>
            </div>
          </div>

          <div className={`${cardBase} ${cardBg} p-4`}>
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <TrendingUp className="w-4 h-4 text-amber-500" />
                <span className="text-sm font-semibold text-gray-700 dark:text-gray-300">Ajuste de Ritmo</span>
                <InfoTooltip text="Aplica um multiplicador ao ritmo atual de vendas. +10% simula aceleração (ex: promoção), -10% simula desaceleração." isDark={isDark} />
              </div>
              {hasTaxa && (
                <button onClick={() => setTaxaCrescimento(0)} className="text-[10px] text-amber-500 hover:text-amber-700 font-medium">
                  Resetar
                </button>
              )}
            </div>
            <input
              type="range"
              min={-50}
              max={100}
              step={5}
              value={taxaCrescimento}
              onChange={(e) => setTaxaCrescimento(Number(e.target.value))}
              className="w-full h-2 bg-gray-200 dark:bg-gray-600 rounded-lg appearance-none cursor-pointer accent-amber-500 mb-2"
            />
            <div className="flex justify-between items-center">
              <span className={`text-xl font-bold ${taxaCrescimento > 0 ? 'text-emerald-500' : taxaCrescimento < 0 ? 'text-red-500' : 'text-gray-500 dark:text-gray-400'}`}>
                {taxaCrescimento > 0 ? '+' : ''}{taxaCrescimento}%
              </span>
              <span className="text-xs text-gray-400">
                Ritmo: {simulacao.ritmoAtual}/dia
              </span>
            </div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className={`${cardBase} ${cardBg} p-4 group hover:shadow-md`}>
          <div className="flex items-center gap-2 mb-2">
            <Users className="w-4 h-4 text-indigo-500" />
            <span className="text-xs font-medium text-gray-500 dark:text-gray-400">Projeção de Vendas</span>
          </div>
          <p className="text-2xl font-bold text-gray-900 dark:text-white">{formatNumber(simulacao.projVendas)}</p>
          <p className="text-xs text-gray-400 mt-1">{simulacao.pctMeta}% da meta</p>
          <div className={`mt-2 h-1.5 rounded-full ${isDark ? 'bg-gray-700' : 'bg-gray-200'} overflow-hidden`}>
            <div
              className={`h-full rounded-full transition-all duration-500 bg-gradient-to-r ${simulacao.pctMeta >= 100 ? 'from-emerald-400 to-green-500' : simulacao.pctMeta >= 85 ? 'from-amber-400 to-yellow-500' : 'from-red-400 to-rose-500'}`}
              style={{ width: `${Math.min(100, simulacao.pctMeta)}%` }}
            />
          </div>
        </div>

        <div className={`${cardBase} ${cardBg} p-4 group hover:shadow-md`}>
          <div className="flex items-center gap-2 mb-2">
            <DollarSign className="w-4 h-4 text-emerald-500" />
            <span className="text-xs font-medium text-gray-500 dark:text-gray-400">Receita Projetada</span>
          </div>
          <p className="text-2xl font-bold text-gray-900 dark:text-white">{formatCurrency(simulacao.projReceita)}</p>
          <p className="text-xs text-gray-400 mt-1">
            Meta: {formatCurrency(simulacao.receitaMeta)}
          </p>
        </div>

        <div className={`${cardBase} ${cardBg} p-4 group hover:shadow-md`}>
          <div className="flex items-center gap-2 mb-2">
            <BarChart3 className="w-4 h-4 text-amber-500" />
            <span className="text-xs font-medium text-gray-500 dark:text-gray-400">Gap para Meta</span>
          </div>
          <p className={`text-2xl font-bold ${simulacao.gapVendas > 0 ? 'text-red-500' : 'text-emerald-500'}`}>
            {simulacao.gapVendas > 0 ? `-${formatNumber(simulacao.gapVendas)}` : 'Atingida'}
          </p>
          <p className="text-xs text-gray-400 mt-1">
            {simulacao.gapReceita > 0 ? `-${formatCurrency(simulacao.gapReceita)}` : 'Receita OK'}
          </p>
        </div>

        <div className={`${cardBase} ${cardBg} p-4 group hover:shadow-md`}>
          <div className="flex items-center gap-2 mb-2">
            <Zap className="w-4 h-4 text-purple-500" />
            <span className="text-xs font-medium text-gray-500 dark:text-gray-400">Ritmo Necessário</span>
          </div>
          <p className={`text-2xl font-bold ${simulacao.ritmoNecessario <= simulacao.ritmoAtual ? 'text-emerald-500' : 'text-red-500'}`}>
            {simulacao.ritmoNecessario}/dia
          </p>
          <p className="text-xs text-gray-400 mt-1">
            Atual: {simulacao.ritmoAtual}/dia
          </p>
        </div>
      </div>

      {chartData.length > 0 && (
        <div className={`${cardBase} ${cardBg} p-6`}>
          <div className="flex items-center gap-2 mb-4">
            <TrendingUp className="w-5 h-5 text-indigo-500" />
            <h4 className="text-base font-semibold text-gray-900 dark:text-white">Curva de Projeção</h4>
            <InfoTooltip text="Linha sólida: vendas acumuladas reais. Áreas coloridas: projeção dos cenários pessimista, realista e otimista baseados nos ritmos atuais. A linha pontilhada indica a meta." isDark={isDark} />
          </div>
          <div className="h-80">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={chartData}>
                <defs>
                  <linearGradient id="gradOtimista" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#10b981" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#10b981" stopOpacity={0.05} />
                  </linearGradient>
                  <linearGradient id="gradRealista" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#6366f1" stopOpacity={0.4} />
                    <stop offset="95%" stopColor="#6366f1" stopOpacity={0.05} />
                  </linearGradient>
                  <linearGradient id="gradPessimista" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#ef4444" stopOpacity={0.2} />
                    <stop offset="95%" stopColor="#ef4444" stopOpacity={0.05} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke={isDark ? '#374151' : '#e5e7eb'} />
                <XAxis
                  dataKey="label"
                  tick={{ fill: isDark ? '#9ca3af' : '#6b7280', fontSize: 11 }}
                  interval={xAxisInterval}
                />
                <YAxis tick={{ fill: isDark ? '#9ca3af' : '#6b7280', fontSize: 12 }} />
                <Tooltip
                  contentStyle={{
                    backgroundColor: isDark ? '#1f2937' : '#fff',
                    border: `1px solid ${isDark ? '#374151' : '#e5e7eb'}`,
                    borderRadius: '8px',
                    color: isDark ? '#fff' : '#111',
                  }}
                  formatter={(value: any, name: any) => {
                    const labels: Record<string, string> = {
                      real: 'Vendas Reais',
                      projecao_otimista: 'Cenário Otimista',
                      projecao_realista: 'Cenário Realista',
                      projecao_pessimista: 'Cenário Pessimista',
                    };
                    return [formatNumber(Number(value)), labels[name] || name];
                  }}
                />
                <Legend
                  formatter={(value: string) => {
                    const labels: Record<string, string> = {
                      real: 'Vendas Reais',
                      projecao_otimista: 'Otimista',
                      projecao_realista: 'Realista',
                      projecao_pessimista: 'Pessimista',
                    };
                    return labels[value] || value;
                  }}
                />
                {meta > 0 && (
                  <ReferenceLine
                    y={meta}
                    stroke={isDark ? '#f59e0b' : '#d97706'}
                    strokeDasharray="8 4"
                    label={{ value: `Meta: ${formatNumber(meta)}`, fill: isDark ? '#f59e0b' : '#d97706', fontSize: 12, position: 'right' }}
                  />
                )}
                <Area type="monotone" dataKey="projecao_otimista" stroke="#10b981" fill="url(#gradOtimista)" strokeWidth={1.5} strokeDasharray="4 3" dot={false} connectNulls={false} />
                <Area type="monotone" dataKey="projecao_realista" stroke="#6366f1" fill="url(#gradRealista)" strokeWidth={2} strokeDasharray="4 3" dot={false} connectNulls={false} />
                <Area type="monotone" dataKey="projecao_pessimista" stroke="#ef4444" fill="url(#gradPessimista)" strokeWidth={1.5} strokeDasharray="4 3" dot={false} connectNulls={false} />
                <Area type="monotone" dataKey="real" stroke="#6366f1" fill="none" strokeWidth={3} dot={false} connectNulls={false} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {[
          { key: 'pessimista', label: 'Pessimista', color: 'red', icon: <TrendingDown className="w-4 h-4" />, desc: 'Baseado no menor ritmo entre 7d, 14d e 30d com -15%' },
          { key: 'realista', label: 'Realista', color: 'indigo', icon: <Minus className="w-4 h-4" />, desc: 'Baseado no ritmo mediano entre 7d, 14d e 30d' },
          { key: 'otimista', label: 'Otimista', color: 'emerald', icon: <TrendingUp className="w-4 h-4" />, desc: 'Baseado no maior ritmo entre 7d, 14d e 30d com +15%' },
        ].map(({ key, label, color, icon, desc }) => {
          const c = key === 'pessimista' ? simulacao.pessVendas : key === 'otimista' ? simulacao.otimVendas : simulacao.projVendas;
          const r = key === 'pessimista' ? simulacao.pessRitmo : key === 'otimista' ? simulacao.otimRitmo : simulacao.ritmoAtual;
          const pct = meta > 0 ? Math.round(c / meta * 1000) / 10 : 0;
          return (
            <div key={key} className={`${cardBase} ${cardBg} p-5 hover:shadow-md transition-shadow`}>
              <div className="flex items-center gap-2 mb-3">
                <div className={`p-1.5 rounded-lg bg-${color}-100 dark:bg-${color}-900/30 text-${color}-600 dark:text-${color}-400`}>
                  {icon}
                </div>
                <span className={`text-sm font-bold text-${color}-600 dark:text-${color}-400`}>{label}</span>
              </div>
              <p className="text-2xl font-bold text-gray-900 dark:text-white mb-1">{formatNumber(c)}</p>
              <p className="text-xs text-gray-400 mb-3">{pct}% da meta • {r}/dia</p>
              <p className="text-[11px] text-gray-400 dark:text-gray-500 leading-snug">{desc}</p>
            </div>
          );
        })}
      </div>

      <div className={`${cardBase} ${cardBg} p-5`}>
        <div className="flex items-center gap-2 mb-4">
          <BarChart3 className="w-5 h-5 text-indigo-500" />
          <h4 className="text-base font-semibold text-gray-900 dark:text-white">Resumo do Evento</h4>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div>
            <p className="text-xs text-gray-400 mb-1">D- (Dias até evento)</p>
            <p className="text-lg font-bold text-gray-900 dark:text-white">D-{evento.dias_ate_evento}</p>
          </div>
          <div>
            <p className="text-xs text-gray-400 mb-1">Vendas Atuais</p>
            <p className="text-lg font-bold text-gray-900 dark:text-white">{formatNumber(atual.total_vendas)}</p>
          </div>
          <div>
            <p className="text-xs text-gray-400 mb-1">Receita Atual</p>
            <p className="text-lg font-bold text-gray-900 dark:text-white">{formatCurrency(atual.total_receita)}</p>
          </div>
          <div>
            <p className="text-xs text-gray-400 mb-1">Dias em Venda</p>
            <p className="text-lg font-bold text-gray-900 dark:text-white">{atual.dias_em_venda}</p>
          </div>
          <div>
            <p className="text-xs text-gray-400 mb-1">Média 7 dias</p>
            <p className="text-lg font-bold text-blue-600 dark:text-blue-400">{atual.media_7d}/dia</p>
          </div>
          <div>
            <p className="text-xs text-gray-400 mb-1">Média 14 dias</p>
            <p className="text-lg font-bold text-cyan-600 dark:text-cyan-400">{atual.media_14d}/dia</p>
          </div>
          <div>
            <p className="text-xs text-gray-400 mb-1">Média 30 dias</p>
            <p className="text-lg font-bold text-emerald-600 dark:text-emerald-400">{atual.media_30d}/dia</p>
          </div>
          <div>
            <p className="text-xs text-gray-400 mb-1">Média Histórica</p>
            <p className="text-lg font-bold text-gray-600 dark:text-gray-300">{atual.media_historica}/dia</p>
          </div>
        </div>
      </div>
    </div>
  );
}
