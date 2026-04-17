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
  Lightbulb,
  ChevronRight,
  Star,
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
  /** Valores vindos do Dashboard (kit-level Magento) para alinhar o baseline */
  dashTicketMedio?: number;
  dashMargem?: number;
  dashTotalVendas?: number;
  /** Ticket atual (preço vigente / special_price do Magento) para exibição no painel */
  dashTicketAtual?: number;
}

const fmt = (n: number) => n.toLocaleString('pt-BR');
const fmtR$ = (n: number) => `R$ ${n.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const fmtPct = (n: number) => `${n.toFixed(1)}%`;

const InfoTooltip = ({ text, isDark }: { text: string; isDark: boolean }) => (
  <div className="relative group inline-flex">
    <Info className="w-3.5 h-3.5 text-gray-400 dark:text-gray-500 cursor-help" />
    <div className={`absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-3 py-2 ${isDark ? 'bg-gray-700' : 'bg-gray-900'} text-white text-xs rounded-lg shadow-lg opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none w-64 z-50`}>
      {text}
    </div>
  </div>
);

const MargemBadge = ({ pct, isDark }: { pct: number; isDark: boolean }) => {
  const color = pct >= 40 ? 'emerald' : pct >= 25 ? 'amber' : 'red';
  return (
    <span className={`text-xs font-semibold px-2 py-0.5 rounded-full bg-${color}-100 dark:bg-${color}-900/30 text-${color}-700 dark:text-${color}-400`}>
      {fmtPct(pct)} margem
    </span>
  );
};

export default function EventSimulator({ eventoId, ano, isDark, dashTicketMedio, dashMargem, dashTotalVendas, dashTicketAtual }: EventSimulatorProps) {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Cenário 1 — Volume: ajuste de ritmo
  const [ajusteRitmo, setAjusteRitmo] = useState<number>(0);

  // Cenário 2 — Ticket: novo ticket + elasticidade
  const [novoTicket, setNovoTicket] = useState<number | null>(null);
  const [elasticidade, setElasticidade] = useState<number>(0.5);

  // Meta customizável
  const [metaCustom, setMetaCustom] = useState<number | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    marketingService.getSimulacao(eventoId, controller.signal, ano)
      .then((res: any) => {
        if (!controller.signal.aborted) {
          setData(res);
          setMetaCustom(res.evento.meta_orcada || null);
          setNovoTicket(Math.round(res.atual.ticket_medio) || null);
        }
      })
      .catch((err: any) => {
        if (err?.name !== 'AbortError' && err?.code !== 'ERR_CANCELED') {
          setError('Erro ao carregar dados da simulação');
        }
      })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [eventoId, ano]);

  // Baseline alinhado com o Dashboard — quando o pai passa valores kit-level do Magento,
  // esses sobrescrevem os valores ISC do Simulator para garantir consistência visual.
  const atualEfetivo = useMemo(() => {
    if (!data?.atual) return null;
    const base = data.atual;
    if (dashTicketMedio != null && dashTotalVendas != null && dashTicketMedio > 0 && dashTotalVendas > 0) {
      const custo = base.custo_kit ?? 50;
      const totalReceita = Math.round(dashTicketMedio * dashTotalVendas * 100) / 100;
      const margemUnit = Math.round((dashTicketMedio - custo) * 100) / 100;
      const margemTotal = dashMargem != null
        ? dashMargem
        : Math.round((totalReceita - custo * dashTotalVendas) * 100) / 100;
      const margemPct = totalReceita > 0 ? Math.round((margemTotal / totalReceita) * 1000) / 10 : 0;
      return {
        ...base,
        ticket_medio: dashTicketMedio,
        total_vendas: dashTotalVendas,
        total_receita: totalReceita,
        margem_total: margemTotal,
        margem_unit: margemUnit,
        margem_pct: margemPct,
      };
    }
    return base;
  }, [data, dashTicketMedio, dashMargem, dashTotalVendas]);

  const custoKit = atualEfetivo?.custo_kit ?? 50;
  const meta = metaCustom ?? data?.evento?.meta_orcada ?? 0;
  // Ticket médio realizado (média ponderada já vendida) — exibido apenas como referência.
  const ticketMedioRealizado = atualEfetivo?.ticket_medio ?? 0;
  // Ticket atual (preço vigente no Magento) — base de TODOS os cálculos prospectivos.
  // Cai para o realizado como fallback quando o preço vigente não está disponível.
  const ticketAtual = (dashTicketAtual && dashTicketAtual > 0) ? dashTicketAtual : ticketMedioRealizado;
  const ticketAlvo = novoTicket ?? Math.round(ticketAtual);

  // ───────────────────────────────────────────────
  // Cenário 1 — Estratégia Volume
  // Mantém o ticket, ajusta o ritmo de vendas
  // ───────────────────────────────────────────────
  const cenarioVolume = useMemo(() => {
    if (!data || !atualEfetivo) return null;
    const atual = atualEfetivo;
    const { evento } = data;
    const diasRestantes = Math.max(0, evento.dias_ate_evento);
    const multiplicador = 1 + ajusteRitmo / 100;

    const ritmo14d = atual.media_14d ?? 0;
    const ritmo = ritmo14d * multiplicador;

    const vendas_futuras = Math.round(ritmo * diasRestantes);
    const total_vendas_proj = atual.total_vendas + vendas_futuras;
    const receita_futura = vendas_futuras * ticketAtual;
    const total_receita_proj = atual.total_receita + receita_futura;
    const total_custo_proj = custoKit * total_vendas_proj;
    const margem_total = total_receita_proj - total_custo_proj;
    const margem_pct = total_receita_proj > 0 ? (margem_total / total_receita_proj) * 100 : 0;
    const margem_unit = ticketAtual - custoKit;
    const pct_meta = meta > 0 ? (total_vendas_proj / meta) * 100 : 0;
    const gap_vendas = Math.max(0, meta - total_vendas_proj);
    const ritmo_necessario = diasRestantes > 0 && meta > atual.total_vendas
      ? Math.round((meta - atual.total_vendas) / diasRestantes * 10) / 10 : 0;

    // Variação em relação ao cenário atual sem ajuste
    const vendas_base = atual.total_vendas + Math.round(ritmo14d * diasRestantes);
    const receita_base = atual.total_receita + Math.round(ritmo14d * diasRestantes) * ticketAtual;
    const margem_base = receita_base - custoKit * vendas_base;
    const ganho_margem = margem_total - margem_base;

    return {
      ritmo: Math.round(ritmo * 10) / 10,
      ritmoBase: Math.round(ritmo14d * 10) / 10,
      vendas_futuras,
      total_vendas_proj,
      total_receita_proj: Math.round(total_receita_proj * 100) / 100,
      margem_total: Math.round(margem_total * 100) / 100,
      margem_pct: Math.round(margem_pct * 10) / 10,
      margem_unit: Math.round(margem_unit * 100) / 100,
      pct_meta: Math.round(pct_meta * 10) / 10,
      gap_vendas,
      ritmo_necessario,
      ganho_margem: Math.round(ganho_margem * 100) / 100,
      diasRestantes,
    };
  }, [data, atualEfetivo, ajusteRitmo, custoKit, ticketAtual, meta]);

  // ───────────────────────────────────────────────
  // Cenário 2 — Estratégia Ticket
  // Muda o preço, modela o impacto no volume via elasticidade
  // Elasticidade: 1% de variação de preço → -elasticidade% de variação no volume
  // ───────────────────────────────────────────────
  const cenarioTicket = useMemo(() => {
    if (!data || !atualEfetivo) return null;
    const atual = atualEfetivo;
    const { evento } = data;
    const diasRestantes = Math.max(0, evento.dias_ate_evento);

    const delta_pct_ticket = ticketAtual > 0 ? ((ticketAlvo - ticketAtual) / ticketAtual) * 100 : 0;
    const delta_volume_pct = -elasticidade * delta_pct_ticket;

    // Volume futuro base (ritmo dos 14d × dias restantes)
    const ritmo14d = atual.media_14d ?? 0;
    const volume_futuro_base = Math.round(ritmo14d * diasRestantes);
    const volume_futuro_ajustado = Math.max(0, Math.round(volume_futuro_base * (1 + delta_volume_pct / 100)));

    const total_vendas_proj = atual.total_vendas + volume_futuro_ajustado;
    const receita_futura = volume_futuro_ajustado * ticketAlvo;
    const total_receita_proj = atual.total_receita + receita_futura;
    const total_custo_proj = custoKit * total_vendas_proj;
    const margem_total = total_receita_proj - total_custo_proj;
    const margem_pct = total_receita_proj > 0 ? (margem_total / total_receita_proj) * 100 : 0;
    const margem_unit = ticketAlvo - custoKit;
    const pct_meta = meta > 0 ? (total_vendas_proj / meta) * 100 : 0;
    const gap_vendas = Math.max(0, meta - total_vendas_proj);

    // Variação em relação ao cenário base (sem mudança de ticket)
    const receita_base = atual.total_receita + volume_futuro_base * ticketAtual;
    const margem_base = receita_base - custoKit * (atual.total_vendas + volume_futuro_base);
    const ganho_margem = margem_total - margem_base;

    return {
      delta_pct_ticket: Math.round(delta_pct_ticket * 10) / 10,
      delta_volume_pct: Math.round(delta_volume_pct * 10) / 10,
      volume_futuro_base,
      volume_futuro_ajustado,
      total_vendas_proj,
      total_receita_proj: Math.round(total_receita_proj * 100) / 100,
      margem_total: Math.round(margem_total * 100) / 100,
      margem_pct: Math.round(margem_pct * 10) / 10,
      margem_unit: Math.round(margem_unit * 100) / 100,
      pct_meta: Math.round(pct_meta * 10) / 10,
      gap_vendas,
      ganho_margem: Math.round(ganho_margem * 100) / 100,
      diasRestantes,
    };
  }, [data, atualEfetivo, ticketAlvo, ticketAtual, elasticidade, custoKit, meta]);

  // ───────────────────────────────────────────────
  // Recomendação: qual cenário maximiza margem?
  // ───────────────────────────────────────────────
  const recomendacao = useMemo(() => {
    if (!cenarioVolume || !cenarioTicket || !data) return null;
    const mv = cenarioVolume.margem_total;
    const mt = cenarioTicket.margem_total;
    const diff = mt - mv;
    const diffPct = mv !== 0 ? Math.abs(diff / mv) * 100 : 0;

    if (Math.abs(diff) < 500) {
      return {
        tipo: 'empate',
        titulo: 'Cenários equivalentes',
        descricao: `Os dois caminhos produzem margem muito próxima (diferença de ${fmtR$(Math.abs(diff))}). Priorize o que for operacionalmente mais fácil de executar.`,
        cor: 'amber',
      };
    }

    if (mv > mt) {
      const aceleracao = ajusteRitmo > 0
        ? `acelerando o ritmo em ${ajusteRitmo}%`
        : 'mantendo o ritmo atual de vendas';
      return {
        tipo: 'volume',
        titulo: 'Estratégia Volume gera mais margem',
        descricao: `${aceleracao.charAt(0).toUpperCase() + aceleracao.slice(1)} e mantendo o ticket de ${fmtR$(ticketAtual)}, a margem projetada é ${fmtR$(mv)} — ${fmtR$(Math.abs(diff))} a mais (${fmtPct(diffPct)} superior) do que mudar o ticket para ${fmtR$(ticketAlvo)}.`,
        cor: 'indigo',
        ganho: Math.abs(diff),
      };
    }

    const acao = ticketAlvo > ticketAtual ? 'aumentar' : 'reduzir';
    return {
      tipo: 'ticket',
      titulo: 'Estratégia Ticket gera mais margem',
      descricao: `${acao.charAt(0).toUpperCase() + acao.slice(1)} o ticket de ${fmtR$(ticketAtual)} para ${fmtR$(ticketAlvo)} projeta uma margem de ${fmtR$(mt)} — ${fmtR$(Math.abs(diff))} a mais (${fmtPct(diffPct)} superior) comparado à estratégia de volume. ${ticketAlvo > ticketAtual ? `O modelo estima queda de ${Math.abs(cenarioTicket.delta_volume_pct).toFixed(1)}% no volume futuro, mas o ganho por inscrito compensa.` : `O volume cresce ${Math.abs(cenarioTicket.delta_volume_pct).toFixed(1)}% compensando o ticket menor.`}`,
      cor: 'emerald',
      ganho: Math.abs(diff),
    };
  }, [cenarioVolume, cenarioTicket, data, ajusteRitmo, ticketAtual, ticketAlvo]);

  // Chart data — curva real + projeção do cenário volume
  const chartData = useMemo(() => {
    if (!data || !cenarioVolume) return [];
    const { vendas_diarias } = data;
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

    const dias = cenarioVolume.diasRestantes;
    if (dias > 0 && points.length > 0) {
      const lastDate = new Date(vendas_diarias[vendas_diarias.length - 1].date + 'T12:00:00');
      let acumVol = acum;
      let acumTkt = acum;

      for (let i = 1; i <= dias; i++) {
        const nd = new Date(lastDate);
        nd.setDate(nd.getDate() + i);
        const label = nd.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' });

        acumVol += cenarioVolume.ritmo;
        acumTkt += (cenarioTicket?.volume_futuro_ajustado ?? 0) / dias;

        points.push({
          date: nd.toISOString().split('T')[0],
          label,
          proj_volume: Math.round(acumVol),
          proj_ticket: Math.round(acumTkt),
          isProjection: true,
        });
      }

      const tIdx = points.findIndex(p => p.isProjection);
      if (tIdx > 0) {
        points[tIdx].real = points[tIdx - 1].real;
      }
    }

    return points;
  }, [data, cenarioVolume, cenarioTicket]);

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

  if (error || !data || !cenarioVolume || !cenarioTicket) {
    return (
      <div className="flex items-center justify-center h-64 text-gray-500 dark:text-gray-400">
        {error || 'Sem dados disponíveis para simulação.'}
      </div>
    );
  }

  const atual = atualEfetivo ?? data.atual;
  const { evento } = data;
  const cardBase = `rounded-xl border shadow-sm`;
  const cardBg = isDark ? 'bg-gray-800 border-gray-700' : 'bg-white border-gray-200';
  const labelCls = `text-xs font-medium text-gray-500 dark:text-gray-400`;
  const valueCls = `text-xl font-bold text-gray-900 dark:text-white`;

  return (
    <div className="space-y-6">

      {/* ── Painel de Situação Atual ── */}
      <div className={`${cardBase} ${isDark ? 'bg-gray-800/80 border-gray-700' : 'bg-white border-gray-200'} p-5`}>
        <div className="flex items-center gap-2 mb-4">
          <BarChart3 className="w-5 h-5 text-indigo-500" />
          <h3 className="text-base font-bold text-gray-900 dark:text-white">Situação Atual</h3>
          <InfoTooltip text="Dados reais acumulados até hoje. Margem = Receita − (Custo Kit × Inscritos)." isDark={isDark} />
        </div>
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
          <div>
            <p className={labelCls}>Inscritos</p>
            <p className={valueCls}>{fmt(atual.total_vendas)}</p>
            <p className="text-xs text-gray-400 mt-0.5">{fmt(evento.dias_ate_evento)} dias restantes</p>
          </div>
          <div>
            <p className={labelCls} title="Preço vigente do kit no site (special_price do Magento). Base de todos os cálculos prospectivos do simulador.">
              Ticket Atual
              <span className="ml-1 text-[10px] font-semibold uppercase tracking-wide text-indigo-500">(preço vigente)</span>
            </p>
            <p className={valueCls}>{fmtR$(ticketAtual)}</p>
            <p className="text-xs text-gray-400 mt-0.5">médio realizado: {fmtR$(ticketMedioRealizado)}</p>
          </div>
          <div>
            <p className={labelCls}>Custo Kit</p>
            <div className="flex items-center gap-2">
              <p className={valueCls}>{fmtR$(custoKit)}</p>
            </div>
            <p className="text-xs text-gray-400 mt-0.5">/inscrito</p>
          </div>
          <div>
            <p className={labelCls}>Margem Unitária</p>
            <p className={`text-xl font-bold ${atual.margem_unit >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-500'}`}>
              {fmtR$(atual.margem_unit ?? (ticketAtual - custoKit))}
            </p>
            <p className="text-xs text-gray-400 mt-0.5">/inscrito</p>
          </div>
          <div>
            <p className={labelCls}>Margem Total Realizada</p>
            <p className={`text-xl font-bold ${(atual.margem_total ?? 0) >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-500'}`}>
              {fmtR$(atual.margem_total ?? (atual.total_receita - custoKit * atual.total_vendas))}
            </p>
            <MargemBadge pct={atual.margem_pct ?? 0} isDark={isDark} />
          </div>
        </div>

        {meta > 0 && (
          <div className={`mt-4 pt-4 border-t ${isDark ? 'border-gray-700' : 'border-gray-100'} flex items-center gap-2`}>
            <Target className="w-4 h-4 text-gray-400" />
            <span className="text-xs text-gray-500 dark:text-gray-400">Meta: <strong>{fmt(meta)}</strong> inscritos</span>
            {metaCustom && metaCustom !== evento.meta_orcada && (
              <button onClick={() => setMetaCustom(evento.meta_orcada)} className="text-xs text-indigo-500 hover:text-indigo-700">Resetar</button>
            )}
          </div>
        )}
      </div>

      {/* ── Dois cenários lado a lado ── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">

        {/* Cenário 1 — Volume */}
        <div className={`${cardBase} ${isDark ? 'bg-indigo-950/40 border-indigo-800/50' : 'bg-indigo-50 border-indigo-200'} p-5`}>
          <div className="flex items-center gap-2 mb-1">
            <div className="p-1.5 rounded-lg bg-indigo-100 dark:bg-indigo-900/50">
              <Users className="w-4 h-4 text-indigo-600 dark:text-indigo-400" />
            </div>
            <h4 className="text-sm font-bold text-indigo-700 dark:text-indigo-300">Cenário 1 — Estratégia Volume</h4>
          </div>
          <p className={`text-sm font-medium mb-4 px-3 py-2 rounded-lg ${isDark ? 'bg-indigo-900/40 text-indigo-200' : 'bg-indigo-100 text-indigo-800'}`}>
            Mantenho o ticket atual em <strong>{fmtR$(ticketAtual)}</strong> e trabalho o ritmo de vendas
          </p>

          {/* Controle: ajuste de ritmo */}
          <div className={`${cardBase} ${cardBg} p-3 mb-4`}>
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-1.5">
                <TrendingUp className="w-3.5 h-3.5 text-indigo-500" />
                <span className="text-xs font-semibold text-gray-700 dark:text-gray-300">Ajuste de Ritmo</span>
                <InfoTooltip text="Aplica um multiplicador ao ritmo dos últimos 14 dias. +20% significa 20% mais vendas por dia do que o ritmo atual." isDark={isDark} />
              </div>
              <span className={`text-sm font-bold ${ajusteRitmo > 0 ? 'text-emerald-500' : ajusteRitmo < 0 ? 'text-red-500' : 'text-gray-400'}`}>
                {ajusteRitmo > 0 ? '+' : ''}{ajusteRitmo}%
              </span>
            </div>
            <input
              type="range" min={-50} max={100} step={5} value={ajusteRitmo}
              onChange={e => setAjusteRitmo(Number(e.target.value))}
              className="w-full h-2 rounded-lg appearance-none cursor-pointer accent-indigo-500"
            />
            <div className="flex justify-between text-xs text-gray-400 mt-1">
              <span>Desacelerar</span>
              <span className="font-medium text-gray-600 dark:text-gray-300">{cenarioVolume.ritmo}/dia</span>
              <span>Acelerar</span>
            </div>
            {ajusteRitmo !== 0 && (
              <button onClick={() => setAjusteRitmo(0)} className="text-[10px] text-indigo-500 hover:text-indigo-700 mt-1">
                Resetar para ritmo atual
              </button>
            )}
          </div>

          {/* Resultados do Cenário 1 */}
          <div className="grid grid-cols-2 gap-3">
            <div className={`${cardBase} ${cardBg} p-3`}>
              <p className={labelCls}>Inscritos Projetados</p>
              <p className={valueCls}>{fmt(cenarioVolume.total_vendas_proj)}</p>
              {meta > 0 && <p className="text-xs text-gray-400 mt-0.5">{fmtPct(cenarioVolume.pct_meta)} da meta</p>}
            </div>
            <div className={`${cardBase} ${cardBg} p-3`}>
              <p className={labelCls}>Receita Projetada</p>
              <p className="text-lg font-bold text-gray-700 dark:text-gray-300">{fmtR$(cenarioVolume.total_receita_proj)}</p>
              <p className="text-xs text-gray-400 mt-0.5">informativo</p>
            </div>
            <div className={`${cardBase} ${cardBg} p-3 col-span-2`}>
              <p className={labelCls}>Margem Total Projetada</p>
              <p className={`text-2xl font-bold ${cenarioVolume.margem_total >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-500'}`}>
                {fmtR$(cenarioVolume.margem_total)}
              </p>
              <div className="flex items-center justify-between mt-1">
                <MargemBadge pct={cenarioVolume.margem_pct} isDark={isDark} />
                {cenarioVolume.ganho_margem !== 0 && (
                  <span className={`text-xs font-medium ${cenarioVolume.ganho_margem > 0 ? 'text-emerald-500' : 'text-red-500'}`}>
                    {cenarioVolume.ganho_margem > 0 ? '+' : ''}{fmtR$(cenarioVolume.ganho_margem)} vs. ritmo base
                  </span>
                )}
              </div>
            </div>
          </div>

          {meta > 0 && cenarioVolume.gap_vendas > 0 && (
            <div className={`mt-3 p-2.5 rounded-lg ${isDark ? 'bg-amber-900/20 border border-amber-800/30' : 'bg-amber-50 border border-amber-200'}`}>
              <p className="text-xs text-amber-700 dark:text-amber-400">
                Faltam <strong>{fmt(cenarioVolume.gap_vendas)}</strong> inscritos para a meta.
                Ritmo necessário: <strong>{cenarioVolume.ritmo_necessario}/dia</strong> (atual: {cenarioVolume.ritmoBase}/dia)
              </p>
            </div>
          )}
        </div>

        {/* Cenário 2 — Ticket */}
        <div className={`${cardBase} ${isDark ? 'bg-emerald-950/40 border-emerald-800/50' : 'bg-emerald-50 border-emerald-200'} p-5`}>
          <div className="flex items-center gap-2 mb-1">
            <div className="p-1.5 rounded-lg bg-emerald-100 dark:bg-emerald-900/50">
              <DollarSign className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
            </div>
            <h4 className="text-sm font-bold text-emerald-700 dark:text-emerald-300">Cenário 2 — Estratégia Ticket</h4>
          </div>
          <p className={`text-sm font-medium mb-4 px-3 py-2 rounded-lg ${isDark ? 'bg-emerald-900/40 text-emerald-200' : 'bg-emerald-100 text-emerald-800'}`}>
            Mudo o preço e modelo o impacto no volume via elasticidade de demanda
          </p>

          {/* Controles: novo ticket + elasticidade */}
          <div className={`${cardBase} ${cardBg} p-3 mb-3`}>
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-1.5">
                <DollarSign className="w-3.5 h-3.5 text-emerald-500" />
                <span className="text-xs font-semibold text-gray-700 dark:text-gray-300">Novo Ticket Atual</span>
                <InfoTooltip text="Simula uma alteração no preço vigente do kit (special_price). Toda a projeção de receita futura passa a usar este novo valor." isDark={isDark} />
              </div>
              <span className={`text-sm font-bold ${cenarioTicket.delta_pct_ticket > 0 ? 'text-emerald-500' : cenarioTicket.delta_pct_ticket < 0 ? 'text-red-500' : 'text-gray-400'}`}>
                {cenarioTicket.delta_pct_ticket > 0 ? '+' : ''}{fmtPct(cenarioTicket.delta_pct_ticket)}
              </span>
            </div>
            <input
              type="range"
              min={Math.max(1, Math.round(ticketAtual * 0.5))}
              max={Math.round(ticketAtual * 2)}
              step={5}
              value={ticketAlvo}
              onChange={e => setNovoTicket(Number(e.target.value))}
              className="w-full h-2 rounded-lg appearance-none cursor-pointer accent-emerald-500"
            />
            <div className="flex justify-between items-center mt-1">
              <span className="text-xs text-gray-400">-50%</span>
              <div className="flex items-center gap-1">
                <span className="text-xs text-gray-400">R$</span>
                <input
                  type="number"
                  value={ticketAlvo}
                  onChange={e => setNovoTicket(Number(e.target.value) || ticketAtual)}
                  className={`w-20 text-sm font-bold text-center ${isDark ? 'bg-gray-700 text-white border-gray-600' : 'bg-gray-50 text-gray-900 border-gray-300'} border rounded-lg px-2 py-0.5`}
                />
              </div>
              <span className="text-xs text-gray-400">+100%</span>
            </div>
            {novoTicket !== null && novoTicket !== Math.round(ticketAtual) && (
              <button onClick={() => setNovoTicket(Math.round(ticketAtual))} className="text-[10px] text-emerald-500 hover:text-emerald-700 mt-1">
                Resetar para ticket atual
              </button>
            )}
          </div>

          <div className={`${cardBase} ${cardBg} p-3 mb-4`}>
            <div className="flex items-center justify-between mb-1">
              <div className="flex items-center gap-1.5">
                <Zap className="w-3.5 h-3.5 text-amber-500" />
                <span className="text-xs font-semibold text-gray-700 dark:text-gray-300">Elasticidade de Demanda</span>
                <InfoTooltip text="Quanto o volume cai/sobe para cada 1% de variação no preço. Ex: 0.5 significa que subindo 10% no ticket, o volume cai 5%. Eventos premium tendem a ter elasticidade menor (0.2–0.4), eventos populares maior (0.6–1.0)." isDark={isDark} />
              </div>
              <span className="text-sm font-bold text-amber-600 dark:text-amber-400">{elasticidade.toFixed(1)}</span>
            </div>
            <input
              type="range" min={0.1} max={1.5} step={0.1} value={elasticidade}
              onChange={e => setElasticidade(Number(e.target.value))}
              className="w-full h-2 rounded-lg appearance-none cursor-pointer accent-amber-500"
            />
            <div className="flex justify-between text-xs text-gray-400 mt-1">
              <span>Inelástico (premium)</span>
              <span>Elástico (popular)</span>
            </div>
          </div>

          {/* Impacto de volume */}
          {cenarioTicket.delta_pct_ticket !== 0 && (
            <div className={`mb-3 px-3 py-2 rounded-lg text-xs ${isDark ? 'bg-gray-700/50' : 'bg-gray-100'}`}>
              <span className="text-gray-500 dark:text-gray-400">Impacto estimado no volume futuro: </span>
              <span className={`font-semibold ${cenarioTicket.delta_volume_pct < 0 ? 'text-red-500' : 'text-emerald-500'}`}>
                {cenarioTicket.delta_volume_pct > 0 ? '+' : ''}{fmtPct(cenarioTicket.delta_volume_pct)}
              </span>
              <span className="text-gray-500 dark:text-gray-400"> ({fmt(cenarioTicket.volume_futuro_base)} → {fmt(cenarioTicket.volume_futuro_ajustado)} inscrições futuras)</span>
            </div>
          )}

          {/* Resultados do Cenário 2 */}
          <div className="grid grid-cols-2 gap-3">
            <div className={`${cardBase} ${cardBg} p-3`}>
              <p className={labelCls}>Inscritos Projetados</p>
              <p className={valueCls}>{fmt(cenarioTicket.total_vendas_proj)}</p>
              {meta > 0 && <p className="text-xs text-gray-400 mt-0.5">{fmtPct(cenarioTicket.pct_meta)} da meta</p>}
            </div>
            <div className={`${cardBase} ${cardBg} p-3`}>
              <p className={labelCls}>Receita Projetada</p>
              <p className="text-lg font-bold text-gray-700 dark:text-gray-300">{fmtR$(cenarioTicket.total_receita_proj)}</p>
              <p className="text-xs text-gray-400 mt-0.5">informativo</p>
            </div>
            <div className={`${cardBase} ${cardBg} p-3 col-span-2`}>
              <p className={labelCls}>Margem Total Projetada</p>
              <p className={`text-2xl font-bold ${cenarioTicket.margem_total >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-500'}`}>
                {fmtR$(cenarioTicket.margem_total)}
              </p>
              <div className="flex items-center justify-between mt-1">
                <MargemBadge pct={cenarioTicket.margem_pct} isDark={isDark} />
                {cenarioTicket.ganho_margem !== 0 && (
                  <span className={`text-xs font-medium ${cenarioTicket.ganho_margem > 0 ? 'text-emerald-500' : 'text-red-500'}`}>
                    {cenarioTicket.ganho_margem > 0 ? '+' : ''}{fmtR$(cenarioTicket.ganho_margem)} vs. ritmo base
                  </span>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* ── Recomendação ── */}
      {recomendacao && (
        <div className={`${cardBase} p-5 ${
          recomendacao.cor === 'indigo'
            ? isDark ? 'bg-indigo-950/50 border-indigo-700' : 'bg-indigo-50 border-indigo-300'
            : recomendacao.cor === 'emerald'
              ? isDark ? 'bg-emerald-950/50 border-emerald-700' : 'bg-emerald-50 border-emerald-300'
              : isDark ? 'bg-amber-950/50 border-amber-700' : 'bg-amber-50 border-amber-300'
        }`}>
          <div className="flex items-start gap-3">
            <div className={`p-2 rounded-xl ${
              recomendacao.cor === 'indigo' ? 'bg-indigo-100 dark:bg-indigo-900/50' :
              recomendacao.cor === 'emerald' ? 'bg-emerald-100 dark:bg-emerald-900/50' :
              'bg-amber-100 dark:bg-amber-900/50'
            }`}>
              {recomendacao.tipo === 'empate' ? (
                <Minus className={`w-5 h-5 text-amber-600 dark:text-amber-400`} />
              ) : (
                <Lightbulb className={`w-5 h-5 ${recomendacao.cor === 'indigo' ? 'text-indigo-600 dark:text-indigo-400' : 'text-emerald-600 dark:text-emerald-400'}`} />
              )}
            </div>
            <div className="flex-1">
              <div className="flex items-center gap-2 mb-1">
                <h4 className={`text-sm font-bold ${
                  recomendacao.cor === 'indigo' ? 'text-indigo-700 dark:text-indigo-300' :
                  recomendacao.cor === 'emerald' ? 'text-emerald-700 dark:text-emerald-300' :
                  'text-amber-700 dark:text-amber-300'
                }`}>
                  {recomendacao.titulo}
                </h4>
                {recomendacao.tipo !== 'empate' && (
                  <Star className="w-3.5 h-3.5 text-amber-400 fill-amber-400" />
                )}
              </div>
              <p className="text-sm text-gray-600 dark:text-gray-300">{recomendacao.descricao}</p>
            </div>
          </div>

          {/* Comparativo de margens */}
          <div className={`mt-4 pt-4 border-t ${isDark ? 'border-white/10' : 'border-black/10'} grid grid-cols-2 gap-4`}>
            <div className={`p-3 rounded-lg ${recomendacao.tipo === 'volume' ? isDark ? 'bg-indigo-900/40 ring-1 ring-indigo-500' : 'bg-indigo-100 ring-1 ring-indigo-400' : isDark ? 'bg-gray-700/40' : 'bg-white/70'}`}>
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs font-semibold text-indigo-600 dark:text-indigo-400">Cenário 1 — Volume</span>
                {recomendacao.tipo === 'volume' && <span className="text-[10px] font-bold text-indigo-600 dark:text-indigo-400 bg-indigo-100 dark:bg-indigo-900/50 px-1.5 py-0.5 rounded-full">RECOMENDADO</span>}
              </div>
              <p className="text-lg font-bold text-gray-900 dark:text-white">{fmtR$(cenarioVolume.margem_total)}</p>
              <p className="text-xs text-gray-500 dark:text-gray-400">{fmt(cenarioVolume.total_vendas_proj)} inscritos · {fmtPct(cenarioVolume.margem_pct)}</p>
            </div>
            <div className={`p-3 rounded-lg ${recomendacao.tipo === 'ticket' ? isDark ? 'bg-emerald-900/40 ring-1 ring-emerald-500' : 'bg-emerald-100 ring-1 ring-emerald-400' : isDark ? 'bg-gray-700/40' : 'bg-white/70'}`}>
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs font-semibold text-emerald-600 dark:text-emerald-400">Cenário 2 — Ticket</span>
                {recomendacao.tipo === 'ticket' && <span className="text-[10px] font-bold text-emerald-600 dark:text-emerald-400 bg-emerald-100 dark:bg-emerald-900/50 px-1.5 py-0.5 rounded-full">RECOMENDADO</span>}
              </div>
              <p className="text-lg font-bold text-gray-900 dark:text-white">{fmtR$(cenarioTicket.margem_total)}</p>
              <p className="text-xs text-gray-500 dark:text-gray-400">{fmt(cenarioTicket.total_vendas_proj)} inscritos · {fmtPct(cenarioTicket.margem_pct)}</p>
            </div>
          </div>
        </div>
      )}

      {/* ── Gráfico de projeção ── */}
      {chartData.length > 0 && evento.dias_ate_evento > 0 && (
        <div className={`${cardBase} ${cardBg} p-5`}>
          <div className="flex items-center gap-2 mb-4">
            <TrendingUp className="w-5 h-5 text-indigo-500" />
            <h4 className="text-base font-semibold text-gray-900 dark:text-white">Curva de Inscrições — Projeção dos Cenários</h4>
            <InfoTooltip text="Linha sólida: inscrições reais acumuladas. Linhas tracejadas: projeção do Cenário 1 (Volume - azul) e Cenário 2 (Ticket - verde)." isDark={isDark} />
          </div>
          <div className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={chartData}>
                <defs>
                  <linearGradient id="gradVol" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#6366f1" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#6366f1" stopOpacity={0.03} />
                  </linearGradient>
                  <linearGradient id="gradTkt" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#10b981" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#10b981" stopOpacity={0.03} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke={isDark ? '#374151' : '#e5e7eb'} />
                <XAxis
                  dataKey="label"
                  tick={{ fill: isDark ? '#9ca3af' : '#6b7280', fontSize: 11 }}
                  interval={chartData.length > 30 ? Math.floor(chartData.length / 12) : chartData.length > 15 ? Math.floor(chartData.length / 8) : 0}
                />
                <YAxis tick={{ fill: isDark ? '#9ca3af' : '#6b7280', fontSize: 12 }} />
                <Tooltip
                  contentStyle={{ backgroundColor: isDark ? '#1f2937' : '#fff', border: `1px solid ${isDark ? '#374151' : '#e5e7eb'}`, borderRadius: '8px', color: isDark ? '#fff' : '#111' }}
                  formatter={(v: any, n: any) => [fmt(Number(v)), ({ real: 'Real', proj_volume: 'Cenário Volume', proj_ticket: 'Cenário Ticket' } as Record<string, string>)[n as string] || n]}
                />
                <Legend formatter={(v: string) => ({ real: 'Inscrições Reais', proj_volume: 'Cenário 1 — Volume', proj_ticket: 'Cenário 2 — Ticket' }[v] || v)} />
                {meta > 0 && (
                  <ReferenceLine
                    y={meta}
                    stroke={isDark ? '#f59e0b' : '#d97706'}
                    strokeDasharray="8 4"
                    label={{ value: `Meta: ${fmt(meta)}`, fill: isDark ? '#f59e0b' : '#d97706', fontSize: 11, position: 'right' }}
                  />
                )}
                <Area type="monotone" dataKey="proj_volume" stroke="#6366f1" fill="url(#gradVol)" strokeWidth={2} strokeDasharray="5 3" dot={false} connectNulls={false} />
                <Area type="monotone" dataKey="proj_ticket" stroke="#10b981" fill="url(#gradTkt)" strokeWidth={2} strokeDasharray="5 3" dot={false} connectNulls={false} />
                <Area type="monotone" dataKey="real" stroke="#6366f1" fill="none" strokeWidth={3} dot={false} connectNulls={false} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* ── Nota sobre elasticidade ── */}
      <div className={`rounded-xl p-4 border ${isDark ? 'bg-gray-800 border-gray-600 text-gray-300' : 'bg-amber-50 border-amber-200 text-gray-700'}`}>
        <div className="flex items-center gap-2 mb-2">
          <Info className="w-4 h-4 text-amber-500 flex-shrink-0" />
          <span className={`text-sm font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>Como interpretar:</span>
        </div>
        <p className="text-sm leading-relaxed">
          O Cenário 2 usa um modelo de elasticidade de demanda — um parâmetro configurável que estima o quanto o volume de vendas reage à variação de preço.
          Elasticidade <strong>0.5</strong> (padrão) significa que um aumento de 10% no ticket reduz o volume futuro em 5%.
          Ajuste a elasticidade de acordo com o perfil do seu evento: eventos premium tendem a ser menos elásticos (0.2–0.4), enquanto eventos populares são mais elásticos (0.6–1.0).
        </p>
      </div>
    </div>
  );
}
