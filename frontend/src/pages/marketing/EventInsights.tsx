import React, { useState, useEffect } from 'react';
import {
  Loader2,
  TrendingUp,
  TrendingDown,
  Target,
  Clock,
  AlertTriangle,
  CheckCircle,
  Zap
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
import { marketingService } from '../../services/api';
import { useTheme } from '../../context/ThemeContext';

interface EventInsightsProps {
  eventoId: string;
  ano?: number;
  forceRefresh?: boolean;
}

const formatNumber = (n: number) => n.toLocaleString('pt-BR');
const formatCurrency = (n: number) => n.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });

const COLORS = {
  anoAtual: '#3b82f6',
  anoAnterior: '#94a3b8',
  positive: '#10b981',
  negative: '#ef4444',
  neutral: '#f59e0b',
  ticketMedio: '#10b981',
};

const CATEGORY_COLORS = [
  '#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6',
  '#ec4899', '#06b6d4', '#f97316', '#6366f1', '#14b8a6'
];

const EventInsights: React.FC<EventInsightsProps> = ({ eventoId, ano, forceRefresh }) => {
  const { isDark } = useTheme();
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();

    const fetchInsights = async () => {
      try {
        setLoading(true);
        setError(null);
        const response = await marketingService.getEventInsights(eventoId, controller.signal, ano, forceRefresh);
        if (!controller.signal.aborted) {
          setData(response);
        }
      } catch (err: any) {
        if (err?.name === 'CanceledError' || err?.code === 'ERR_CANCELED' || err?.name === 'AbortError') return;
        if (!controller.signal.aborted) {
          setError('Erro ao carregar insights estratégicos');
        }
      } finally {
        if (!controller.signal.aborted) {
          setLoading(false);
        }
      }
    };

    fetchInsights();
    return () => { controller.abort(); };
  }, [eventoId, ano, forceRefresh]);

  if (loading) {
    return (
      <div className="bg-white dark:bg-gray-800 rounded-xl p-12 shadow-sm border border-gray-200 dark:border-gray-700 flex flex-col items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-blue-600" />
        <p className="mt-4 text-gray-500 dark:text-gray-400">Carregando insights estratégicos...</p>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="bg-white dark:bg-gray-800 rounded-xl p-8 shadow-sm border border-gray-200 dark:border-gray-700 text-center">
        <AlertTriangle className="w-8 h-8 text-amber-500 mx-auto mb-3" />
        <p className="text-gray-500 dark:text-gray-400">{error || 'Dados não disponíveis'}</p>
      </div>
    );
  }

  const { projecao_fechamento, janela_acao, indice_aceleracao, pace_diario, ticket_medio, mix_categorias } = data;

  const pctAbove = projecao_fechamento?.pct_vs_anterior >= 100;

  const getStatusConfig = (status: string) => {
    switch (status) {
      case 'acima':
        return { label: 'Acima do esperado', color: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400', icon: CheckCircle };
      case 'em_ritmo':
        return { label: 'Em ritmo', color: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400', icon: TrendingUp };
      case 'abaixo':
      default:
        return { label: 'Ação necessária', color: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400', icon: AlertTriangle };
    }
  };

  const statusConfig = getStatusConfig(janela_acao?.status);
  const StatusIcon = statusConfig.icon;

  const processCategories = (items: any[]) => {
    if (!items || items.length === 0) return [];
    const sorted = [...items].sort((a, b) => b.pct - a.pct);
    if (sorted.length <= 8) return sorted;
    const top8 = sorted.slice(0, 8);
    const others = sorted.slice(8);
    const othersPct = others.reduce((sum: number, item: any) => sum + item.pct, 0);
    const othersQtd = others.reduce((sum: number, item: any) => sum + item.qtd, 0);
    return [...top8, { categoria: 'Outros', pct: othersPct, qtd: othersQtd }];
  };

  const categoriasAnterior = processCategories(mix_categorias?.anterior || []);
  const categoriasAtual = processCategories(mix_categorias?.atual || []);

  const gridColor = isDark ? '#374151' : '#e5e7eb';
  const textColor = isDark ? '#9ca3af' : '#6b7280';

  const cardClass = 'bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm border border-gray-200 dark:border-gray-700';

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className={cardClass}>
          <div className="flex items-center gap-2 mb-4">
            <Target className="w-5 h-5 text-blue-500" />
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white">Projeção de Fechamento</h3>
          </div>
          {projecao_fechamento ? (
            <div>
              <div className="flex items-baseline gap-3 mb-2">
                <span className={`text-4xl font-bold ${pctAbove ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}>
                  {formatNumber(projecao_fechamento.projecao_inscricoes)}
                </span>
                <span className={`text-lg font-semibold flex items-center gap-1 ${pctAbove ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}>
                  {pctAbove ? <TrendingUp className="w-4 h-4" /> : <TrendingDown className="w-4 h-4" />}
                  {projecao_fechamento.pct_vs_anterior?.toFixed(1)}%
                </span>
              </div>
              <p className="text-sm text-gray-500 dark:text-gray-400 mb-3">
                Projeção baseada na média de {projecao_fechamento.media_diaria_atual?.toFixed(1)} vendas/dia
              </p>
              <div className="flex items-center gap-4 text-sm">
                <div className="px-3 py-1.5 rounded-lg bg-gray-100 dark:bg-gray-700">
                  <span className="text-gray-500 dark:text-gray-400">Ano anterior: </span>
                  <span className="font-medium text-gray-900 dark:text-white">{formatNumber(projecao_fechamento.total_anterior)}</span>
                </div>
                <div className="px-3 py-1.5 rounded-lg bg-gray-100 dark:bg-gray-700">
                  <span className="text-gray-500 dark:text-gray-400">Dias restantes: </span>
                  <span className="font-medium text-gray-900 dark:text-white">{projecao_fechamento.dias_restantes}</span>
                </div>
              </div>
              {projecao_fechamento.projecao_receita != null && (
                <div className="mt-3 pt-3 border-t border-gray-200 dark:border-gray-700">
                  <span className="text-sm text-gray-500 dark:text-gray-400">Receita projetada: </span>
                  <span className="text-sm font-semibold text-gray-900 dark:text-white">{formatCurrency(projecao_fechamento.projecao_receita)}</span>
                </div>
              )}
            </div>
          ) : (
            <p className="text-gray-400">Dados insuficientes</p>
          )}
        </div>

        <div className={cardClass}>
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <Clock className="w-5 h-5 text-amber-500" />
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white">Janela de Ação</h3>
            </div>
            {janela_acao && (
              <span className={`px-3 py-1 rounded-full text-xs font-semibold flex items-center gap-1.5 ${statusConfig.color}`}>
                <StatusIcon className="w-3.5 h-3.5" />
                {statusConfig.label}
              </span>
            )}
          </div>
          {janela_acao ? (
            <div>
              <div className="flex items-center gap-3 mb-4">
                <div className="relative">
                  <span className="text-4xl font-bold text-gray-900 dark:text-white">D-{janela_acao.dias_ate_evento}</span>
                  {janela_acao.dentro_d40 && (
                    <span className="absolute -top-1 -right-3 w-3 h-3 bg-amber-500 rounded-full animate-pulse" />
                  )}
                </div>
                {janela_acao.dentro_d40 && (
                  <span className="px-2 py-0.5 text-xs font-medium bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400 rounded-full flex items-center gap-1">
                    <Zap className="w-3 h-3" />
                    Janela D-40
                  </span>
                )}
              </div>
              <div className="grid grid-cols-2 gap-3 mb-3">
                <div className="px-3 py-2 rounded-lg bg-gray-100 dark:bg-gray-700">
                  <p className="text-xs text-gray-500 dark:text-gray-400">Pace Atual</p>
                  <p className="text-lg font-bold text-gray-900 dark:text-white">{janela_acao.pace_atual?.toFixed(1)}</p>
                </div>
                <div className="px-3 py-2 rounded-lg bg-gray-100 dark:bg-gray-700">
                  <p className="text-xs text-gray-500 dark:text-gray-400">Pace Necessário</p>
                  <p className="text-lg font-bold text-gray-900 dark:text-white">{janela_acao.pace_necessario?.toFixed(1)}</p>
                </div>
              </div>
              <div className="flex items-center justify-between text-sm">
                <div>
                  <span className="text-gray-500 dark:text-gray-400">Atingido: </span>
                  <span className="font-semibold text-gray-900 dark:text-white">{janela_acao.pct_atingido?.toFixed(1)}%</span>
                </div>
                <div className={`font-semibold ${janela_acao.deficit_superavit >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}>
                  {janela_acao.deficit_superavit >= 0 ? '+' : ''}{formatNumber(janela_acao.deficit_superavit)} {janela_acao.deficit_superavit >= 0 ? 'superávit' : 'déficit'}
                </div>
              </div>
            </div>
          ) : (
            <p className="text-gray-400">Dados insuficientes</p>
          )}
        </div>
      </div>

      {indice_aceleracao && indice_aceleracao.length > 0 && (
        <div className={cardClass}>
          <div className="mb-4">
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white">Índice de Aceleração (IA)</h3>
            <p className="text-sm text-gray-500 dark:text-gray-400">IA {'>'} 1 = Acelerando | IA {'<'} 1 = Desacelerando</p>
          </div>
          <div style={{ height: 300 }}>
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={indice_aceleracao}>
                <CartesianGrid strokeDasharray="3 3" stroke={gridColor} />
                <XAxis dataKey="label" tick={{ fill: textColor, fontSize: 12 }} />
                <YAxis tick={{ fill: textColor, fontSize: 12 }} domain={['auto', 'auto']} />
                <Tooltip
                  contentStyle={{
                    backgroundColor: isDark ? '#1f2937' : '#fff',
                    border: `1px solid ${isDark ? '#374151' : '#e5e7eb'}`,
                    borderRadius: '8px',
                    color: isDark ? '#fff' : '#111'
                  }}
                  formatter={(value: any, name: any) => [
                    typeof value === 'number' ? value.toFixed(3) : value,
                    name === 'ia_atual' ? `Ano ${data.ano_atual}` : `Ano ${data.ano_anterior}`
                  ]}
                />
                <Legend
                  formatter={(value: string) => value === 'ia_atual' ? `Ano ${data.ano_atual}` : `Ano ${data.ano_anterior}`}
                />
                <ReferenceLine y={1} stroke={COLORS.neutral} strokeDasharray="6 4" label={{ value: 'Neutro', fill: COLORS.neutral, fontSize: 12 }} />
                <Line type="monotone" dataKey="ia_atual" stroke={COLORS.anoAtual} strokeWidth={2.5} dot={false} activeDot={{ r: 5 }} />
                <Line type="monotone" dataKey="ia_anterior" stroke={COLORS.anoAnterior} strokeWidth={2} strokeDasharray="5 5" dot={false} activeDot={{ r: 4 }} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {pace_diario && pace_diario.length > 0 && (
        <div className={cardClass}>
          <div className="mb-4">
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white">Velocidade de Vendas (Pace Diário)</h3>
            <p className="text-sm text-gray-500 dark:text-gray-400">Vendas por dia em cada período de 7 dias</p>
          </div>
          <div style={{ height: 300 }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={pace_diario}>
                <CartesianGrid strokeDasharray="3 3" stroke={gridColor} />
                <XAxis dataKey="label" tick={{ fill: textColor, fontSize: 12 }} />
                <YAxis tick={{ fill: textColor, fontSize: 12 }} />
                <Tooltip
                  contentStyle={{
                    backgroundColor: isDark ? '#1f2937' : '#fff',
                    border: `1px solid ${isDark ? '#374151' : '#e5e7eb'}`,
                    borderRadius: '8px',
                    color: isDark ? '#fff' : '#111'
                  }}
                  formatter={(value: any, name: any) => [
                    typeof value === 'number' ? value.toFixed(1) : value,
                    name === 'pace_atual' ? `Ano ${data.ano_atual}` : `Ano ${data.ano_anterior}`
                  ]}
                />
                <Legend
                  formatter={(value: string) => value === 'pace_atual' ? `Ano ${data.ano_atual}` : `Ano ${data.ano_anterior}`}
                />
                <Bar dataKey="pace_anterior" fill={COLORS.anoAnterior} radius={[4, 4, 0, 0]} />
                <Bar dataKey="pace_atual" fill={COLORS.anoAtual} radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {ticket_medio && ticket_medio.length > 0 && (
        <div className={cardClass}>
          <div className="mb-4">
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white">Ticket Médio por Período</h3>
            <p className="text-sm text-gray-500 dark:text-gray-400">Evolução do ticket médio ao longo do tempo</p>
          </div>
          <div style={{ height: 300 }}>
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={ticket_medio}>
                <CartesianGrid strokeDasharray="3 3" stroke={gridColor} />
                <XAxis dataKey="label" tick={{ fill: textColor, fontSize: 12 }} />
                <YAxis
                  tick={{ fill: textColor, fontSize: 12 }}
                  tickFormatter={(v: number) => `R$ ${v}`}
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: isDark ? '#1f2937' : '#fff',
                    border: `1px solid ${isDark ? '#374151' : '#e5e7eb'}`,
                    borderRadius: '8px',
                    color: isDark ? '#fff' : '#111'
                  }}
                  formatter={(value: any, name: any) => [
                    typeof value === 'number' ? formatCurrency(value) : value,
                    name === 'ticket_atual' ? `Ano ${data.ano_atual}` : `Ano ${data.ano_anterior}`
                  ]}
                />
                <Legend
                  formatter={(value: string) => value === 'ticket_atual' ? `Ano ${data.ano_atual}` : `Ano ${data.ano_anterior}`}
                />
                <Line type="monotone" dataKey="ticket_atual" stroke={COLORS.ticketMedio} strokeWidth={2.5} dot={false} activeDot={{ r: 5 }} />
                <Line type="monotone" dataKey="ticket_anterior" stroke={COLORS.anoAnterior} strokeWidth={2} strokeDasharray="5 5" dot={false} activeDot={{ r: 4 }} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {mix_categorias && (categoriasAtual.length > 0 || categoriasAnterior.length > 0) && (
        <div className={cardClass}>
          <div className="mb-6">
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white">Mix de Categorias</h3>
            <p className="text-sm text-gray-500 dark:text-gray-400">Distribuição por categoria de inscrição</p>
          </div>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
            <div>
              <h4 className="text-sm font-semibold text-gray-500 dark:text-gray-400 mb-4 text-center">
                Ano {data.ano_anterior}
              </h4>
              <div className="space-y-2">
                {categoriasAnterior.map((item: any, index: number) => {
                  const maxPct = Math.max(...categoriasAnterior.map((c: any) => c.pct));
                  return (
                    <div key={item.categoria} className="flex items-center gap-3">
                      <span className="text-xs text-gray-600 dark:text-gray-300 w-24 truncate text-right" title={item.categoria}>
                        {item.categoria}
                      </span>
                      <div className="flex-1 h-6 bg-gray-100 dark:bg-gray-700 rounded-full overflow-hidden">
                        <div
                          className="h-full rounded-full transition-all duration-500 flex items-center justify-end pr-2"
                          style={{
                            width: `${Math.max((item.pct / maxPct) * 100, 8)}%`,
                            backgroundColor: CATEGORY_COLORS[index % CATEGORY_COLORS.length]
                          }}
                        >
                          <span className="text-[10px] font-bold text-white">{item.pct.toFixed(1)}%</span>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            <div>
              <h4 className="text-sm font-semibold text-gray-500 dark:text-gray-400 mb-4 text-center">
                Ano {data.ano_atual}
              </h4>
              <div className="space-y-2">
                {categoriasAtual.map((item: any, index: number) => {
                  const maxPct = Math.max(...categoriasAtual.map((c: any) => c.pct));
                  return (
                    <div key={item.categoria} className="flex items-center gap-3">
                      <span className="text-xs text-gray-600 dark:text-gray-300 w-24 truncate text-right" title={item.categoria}>
                        {item.categoria}
                      </span>
                      <div className="flex-1 h-6 bg-gray-100 dark:bg-gray-700 rounded-full overflow-hidden">
                        <div
                          className="h-full rounded-full transition-all duration-500 flex items-center justify-end pr-2"
                          style={{
                            width: `${Math.max((item.pct / maxPct) * 100, 8)}%`,
                            backgroundColor: CATEGORY_COLORS[index % CATEGORY_COLORS.length]
                          }}
                        >
                          <span className="text-[10px] font-bold text-white">{item.pct.toFixed(1)}%</span>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default EventInsights;
