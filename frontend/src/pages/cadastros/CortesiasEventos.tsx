import React, { useEffect, useMemo, useRef, useState } from 'react';
import { cortesiaService } from '../../services/api';
import type { CortesiaEventoRow, CortesiaEventosResponse, CortesiaMetrics, CortesiaUser } from '../../services/api';
import { useTheme } from '../../context/ThemeContext';
import {
  Gift, Search, ChevronDown, RefreshCw, AlertTriangle, Calendar, Info,
} from 'lucide-react';

// ─────────────────────────────────────────────────────────────
// Cortesias por Evento
//
// Lista os eventos futuros (cadastro) com os 4 números do app externo de
// Cortesias, consultados por SKU no backend (lote com concorrência limitada).
// Limitação da API externa: exatamente UM filtro por consulta — não existe
// cruzamento evento × área. Por isso o seletor de área altera apenas os KPIs
// do topo (consulta por área), enquanto a tabela sempre mostra totais por
// evento. Nenhuma falha vira zero silencioso: status por linha + banner.
// ─────────────────────────────────────────────────────────────

const MESES_PT = [
  'Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
  'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro',
];

// Formata 'YYYY-MM-DD' sem passar por Date (evita shift de fuso).
const fmtData = (iso: string | null): string => {
  if (!iso) return '—';
  const [y, m, d] = iso.split('-');
  if (!y || !m || !d) return iso;
  return `${d}/${m}/${y}`;
};

const mesKey = (iso: string | null): string | null => {
  if (!iso) return null;
  const [y, m] = iso.split('-');
  return y && m ? `${y}-${m}` : null;
};

const mesLabel = (key: string): string => {
  const [y, m] = key.split('-');
  const idx = parseInt(m, 10) - 1;
  return idx >= 0 && idx < 12 ? `${MESES_PT[idx]} ${y}` : key;
};

const extractCortesiaError = (e: any): string => {
  const detail = e?.response?.data?.detail;
  if (typeof detail === 'string' && detail.trim()) return detail;
  if (e?.code === 'ECONNABORTED') return 'A consulta ao app de Cortesias demorou demais. Tente novamente.';
  return 'Não foi possível consultar o app de Cortesias. Tente novamente em instantes.';
};

const fmtNum = (n: number | undefined | null): string =>
  n === undefined || n === null ? '—' : n.toLocaleString('pt-BR');

const CortesiasEventos: React.FC = () => {
  const { isDark } = useTheme();

  // Lote de eventos
  const [data, setData] = useState<CortesiaEventosResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const loadReqRef = useRef(0);

  // Áreas (derivadas dos usuários do app de Cortesias)
  const [users, setUsers] = useState<CortesiaUser[]>([]);
  const [usersLoading, setUsersLoading] = useState(true);
  const [usersError, setUsersError] = useState<string | null>(null);

  // KPIs por área selecionada ('' = total geral dos eventos carregados)
  const [areaSel, setAreaSel] = useState('');
  const [areaMetrics, setAreaMetrics] = useState<CortesiaMetrics | null>(null);
  const [areaLoading, setAreaLoading] = useState(false);
  const [areaError, setAreaError] = useState<string | null>(null);
  const areaReqRef = useRef(0);

  // Filtros da tabela
  const [searchTerm, setSearchTerm] = useState('');
  const [filterMes, setFilterMes] = useState('');

  // Retry por linha (por SKU)
  const [retryingSkus, setRetryingSkus] = useState<Set<string>>(new Set());

  const carregarEventos = async () => {
    const reqId = ++loadReqRef.current;
    setLoading(true);
    setError(null);
    try {
      const resp = await cortesiaService.getEventos();
      if (reqId !== loadReqRef.current) return;
      setData(resp);
    } catch (e: any) {
      if (reqId !== loadReqRef.current) return;
      setData(null);
      setError(extractCortesiaError(e));
    } finally {
      if (reqId === loadReqRef.current) setLoading(false);
    }
  };

  const carregarUsers = async () => {
    setUsersLoading(true);
    setUsersError(null);
    try {
      const resp = await cortesiaService.getUsers();
      setUsers(resp.users || []);
    } catch (e: any) {
      setUsersError(extractCortesiaError(e));
    } finally {
      setUsersLoading(false);
    }
  };

  useEffect(() => {
    carregarEventos();
    carregarUsers();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const areas = useMemo(
    () => Array.from(new Set(users.map(u => (u.area || '').trim()).filter(Boolean)))
      .sort((a, b) => a.localeCompare(b, 'pt-BR')),
    [users]
  );

  const consultarArea = async (area: string) => {
    const reqId = ++areaReqRef.current;
    setAreaLoading(true);
    setAreaError(null);
    try {
      const m = await cortesiaService.getMetrics({ area });
      if (reqId !== areaReqRef.current) return;
      setAreaMetrics(m);
    } catch (e: any) {
      if (reqId !== areaReqRef.current) return;
      setAreaMetrics(null);
      setAreaError(extractCortesiaError(e));
    } finally {
      if (reqId === areaReqRef.current) setAreaLoading(false);
    }
  };

  useEffect(() => {
    if (areaSel) {
      consultarArea(areaSel);
    } else {
      areaReqRef.current++; // invalida respostas em voo
      setAreaMetrics(null);
      setAreaError(null);
      setAreaLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [areaSel]);

  const retryRow = async (sku: string) => {
    setRetryingSkus(prev => new Set(prev).add(sku));
    try {
      const m = await cortesiaService.getMetrics({ sku });
      setData(prev => prev ? {
        ...prev,
        eventos: prev.eventos.map(row => row.sku === sku ? {
          ...row,
          status: 'ok' as const,
          mensagem: undefined,
          solicitados: m.solicitados,
          aprovados: m.aprovados,
          utilizados: m.utilizados,
          disponiveis: m.disponiveis,
        } : row),
      } : prev);
    } catch (e: any) {
      const status = e?.response?.status;
      const msg = extractCortesiaError(e);
      setData(prev => prev ? {
        ...prev,
        eventos: prev.eventos.map(row => row.sku === sku ? {
          ...row,
          status: status === 404 ? 'nao_encontrado' as const : 'erro' as const,
          mensagem: msg,
        } : row),
      } : prev);
    } finally {
      setRetryingSkus(prev => {
        const next = new Set(prev);
        next.delete(sku);
        return next;
      });
    }
  };

  const eventos = data?.eventos || [];

  // Chips do cabeçalho recalculados a partir das linhas atuais — assim um
  // retry por linha (ok ou rebaixado para nao_encontrado) atualiza os chips,
  // em vez de exibir o resumo defasado do lote original.
  const resumoAtual = useMemo(() => {
    const r = { ok: 0, nao_encontrado: 0, erro: 0 };
    eventos.forEach(ev => {
      if (ev.status === 'ok') r.ok += 1;
      else if (ev.status === 'nao_encontrado') r.nao_encontrado += 1;
      else r.erro += 1;
    });
    return r;
  }, [eventos]);

  const mesesDisponiveis = useMemo(() => {
    const keys = new Set<string>();
    eventos.forEach(ev => {
      const k = mesKey(ev.data_evento);
      if (k) keys.add(k);
    });
    return Array.from(keys).sort();
  }, [eventos]);

  const eventosFiltrados = useMemo(() => {
    const term = searchTerm.trim().toLowerCase();
    return eventos.filter(ev => {
      if (filterMes && mesKey(ev.data_evento) !== filterMes) return false;
      if (term) {
        const alvo = `${ev.nome} ${ev.sku} ${ev.cidade || ''} ${ev.estado || ''}`.toLowerCase();
        if (!alvo.includes(term)) return false;
      }
      return true;
    });
  }, [eventos, searchTerm, filterMes]);

  // Totais gerais: somente linhas ok (a contagem de respondentes fica visível).
  const totaisGerais = useMemo(() => {
    const ok = eventos.filter(ev => ev.status === 'ok');
    return {
      respondentes: ok.length,
      total: eventos.length,
      solicitados: ok.reduce((s, ev) => s + (ev.solicitados || 0), 0),
      aprovados: ok.reduce((s, ev) => s + (ev.aprovados || 0), 0),
      utilizados: ok.reduce((s, ev) => s + (ev.utilizados || 0), 0),
      disponiveis: ok.reduce((s, ev) => s + (ev.disponiveis || 0), 0),
    };
  }, [eventos]);

  const kpiValues: { label: string; value: number | null; color: string }[] = areaSel
    ? [
        { label: 'Solicitados', value: areaMetrics ? areaMetrics.solicitados : null, color: isDark ? 'text-blue-400' : 'text-blue-600' },
        { label: 'Aprovados', value: areaMetrics ? areaMetrics.aprovados : null, color: isDark ? 'text-emerald-400' : 'text-emerald-600' },
        { label: 'Utilizados', value: areaMetrics ? areaMetrics.utilizados : null, color: isDark ? 'text-amber-400' : 'text-amber-600' },
        { label: 'Disponíveis', value: areaMetrics ? areaMetrics.disponiveis : null, color: isDark ? 'text-violet-400' : 'text-violet-600' },
      ]
    : [
        { label: 'Solicitados', value: data ? totaisGerais.solicitados : null, color: isDark ? 'text-blue-400' : 'text-blue-600' },
        { label: 'Aprovados', value: data ? totaisGerais.aprovados : null, color: isDark ? 'text-emerald-400' : 'text-emerald-600' },
        { label: 'Utilizados', value: data ? totaisGerais.utilizados : null, color: isDark ? 'text-amber-400' : 'text-amber-600' },
        { label: 'Disponíveis', value: data ? totaisGerais.disponiveis : null, color: isDark ? 'text-violet-400' : 'text-violet-600' },
      ];

  const selClass = `h-10 pl-3 pr-8 rounded-xl border text-sm appearance-none cursor-pointer focus:outline-none focus:ring-2 focus:ring-emerald-500 ${
    isDark ? 'bg-gray-900/50 border-gray-600 text-white' : 'bg-white border-gray-200 text-gray-900'
  }`;

  const cardClass = `rounded-2xl overflow-hidden ${isDark ? 'bg-gray-800/50 backdrop-blur-xl border border-gray-700/50' : 'bg-white/70 backdrop-blur-xl border border-gray-200'}`;

  return (
    <div className="min-h-screen">
      <div className="fixed inset-0 pointer-events-none overflow-hidden">
        <div className="absolute top-0 left-1/4 w-96 h-96 bg-emerald-500/10 rounded-full blur-3xl animate-pulse" />
        <div className="absolute bottom-0 right-1/4 w-96 h-96 bg-teal-500/10 rounded-full blur-3xl animate-pulse" style={{ animationDelay: '1s' }} />
      </div>

      <div className="relative z-10 space-y-6 p-6">
        {/* Header */}
        <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-xl bg-gradient-to-br from-emerald-500 to-teal-500 shadow-lg shadow-emerald-500/30">
              <Gift className="w-6 h-6 text-white" />
            </div>
            <div>
              <h1 className={`text-3xl font-black tracking-tight ${isDark ? 'text-white' : 'text-gray-900'}`}>
                Cortesias por
                <span className="bg-gradient-to-r from-emerald-400 via-teal-500 to-cyan-500 bg-clip-text text-transparent"> Evento</span>
              </h1>
              <p className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>
                Dados ao vivo do app de Cortesias — eventos futuros consultados por SKU
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={() => { carregarEventos(); if (areaSel) consultarArea(areaSel); }}
              disabled={loading}
              className={`flex items-center gap-2 px-4 py-3 rounded-2xl font-semibold text-sm transition-all duration-300 hover:scale-105 disabled:opacity-50 disabled:hover:scale-100 ${isDark ? 'bg-emerald-500/15 text-emerald-300 hover:bg-emerald-500/25 border border-emerald-500/30' : 'bg-emerald-50 text-emerald-700 hover:bg-emerald-100 border border-emerald-200 shadow-sm'}`}
            >
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
              Atualizar
            </button>
          </div>
        </div>

        {/* Aviso da limitação evento × área */}
        <div className={`flex items-start gap-2.5 p-3 rounded-xl border text-xs ${isDark ? 'bg-gray-800/60 border-gray-700 text-gray-400' : 'bg-white/80 border-gray-200 text-gray-500'}`}>
          <Info className="w-4 h-4 mt-0.5 shrink-0" />
          <span>
            O app de Cortesias aceita apenas um filtro por consulta: a tabela mostra os totais <strong>por evento</strong> (via SKU)
            e, ao selecionar uma área, os cards do topo mostram os totais <strong>daquela área</strong> — não existe cruzamento evento × área.
          </span>
        </div>

        {/* KPIs + seletor de área */}
        <div className={cardClass}>
          <div className={`flex flex-wrap items-center gap-3 p-4 border-b ${isDark ? 'border-gray-700/50' : 'border-gray-200'}`}>
            <h3 className={`text-sm font-bold mr-auto ${isDark ? 'text-white' : 'text-gray-900'}`}>
              {areaSel ? `Totais da área: ${areaSel}` : 'Totais gerais dos eventos futuros'}
            </h3>
            {!areaSel && data && (
              <span className={`text-[11px] ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                {totaisGerais.respondentes} de {totaisGerais.total} eventos responderam
              </span>
            )}
            <div className="relative">
              <select
                value={areaSel}
                onChange={e => setAreaSel(e.target.value)}
                disabled={usersLoading}
                className={selClass}
              >
                <option value="">Todas as áreas (soma dos eventos)</option>
                {areas.map(a => <option key={a} value={a}>{a}</option>)}
              </select>
              <ChevronDown className={`pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 ${isDark ? 'text-gray-400' : 'text-gray-500'}`} />
            </div>
          </div>

          <div className="p-4">
            {usersError && !areaSel && (
              <div className={`flex items-start gap-2.5 p-3 mb-3 rounded-xl border text-xs ${isDark ? 'bg-amber-500/10 border-amber-500/40 text-amber-300' : 'bg-amber-50 border-amber-200 text-amber-700'}`}>
                <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
                <span className="flex-1">Não foi possível carregar as áreas do app de Cortesias: {usersError}</span>
                <button
                  onClick={carregarUsers}
                  className={`flex items-center gap-1 text-xs font-semibold shrink-0 ${isDark ? 'text-amber-300 hover:text-amber-200' : 'text-amber-700 hover:text-amber-900'}`}
                >
                  <RefreshCw className="w-3 h-3" />
                  Tentar novamente
                </button>
              </div>
            )}
            {areaSel && areaError ? (
              <div className={`flex items-start gap-2.5 p-3 rounded-xl border text-sm ${isDark ? 'bg-red-500/10 border-red-500/40 text-red-300' : 'bg-red-50 border-red-200 text-red-700'}`}>
                <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
                <span className="flex-1">{areaError}</span>
                <button
                  onClick={() => consultarArea(areaSel)}
                  className={`flex items-center gap-1 text-xs font-semibold shrink-0 ${isDark ? 'text-red-300 hover:text-red-200' : 'text-red-600 hover:text-red-800'}`}
                >
                  <RefreshCw className="w-3 h-3" />
                  Tentar novamente
                </button>
              </div>
            ) : areaSel && areaLoading ? (
              <div className={`flex items-center gap-2 text-sm py-3 ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                <RefreshCw className="w-4 h-4 animate-spin" />
                Consultando os totais da área...
              </div>
            ) : (
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                {kpiValues.map(k => (
                  <div key={k.label} className={`p-3 rounded-xl border ${isDark ? 'bg-gray-900/40 border-gray-700/60' : 'bg-gray-50 border-gray-200'}`}>
                    <p className={`text-[11px] font-semibold uppercase tracking-wider ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>{k.label}</p>
                    <p className={`text-xl font-bold mt-0.5 ${k.color}`}>{k.value !== null ? fmtNum(k.value) : '—'}</p>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Tabela de eventos */}
        <div className={cardClass}>
          <div className={`flex flex-wrap items-center gap-3 p-4 border-b ${isDark ? 'border-gray-700/50' : 'border-gray-200'}`}>
            <h3 className={`text-sm font-bold mr-auto ${isDark ? 'text-white' : 'text-gray-900'}`}>Eventos futuros</h3>
            {data && (
              <div className="flex items-center gap-2 text-[11px]">
                <span className={`px-2 py-0.5 rounded-full font-semibold ${isDark ? 'bg-emerald-500/15 text-emerald-300' : 'bg-emerald-50 text-emerald-700'}`}>
                  {resumoAtual.ok} ok
                </span>
                {resumoAtual.nao_encontrado > 0 && (
                  <span className={`px-2 py-0.5 rounded-full font-semibold ${isDark ? 'bg-amber-500/15 text-amber-300' : 'bg-amber-50 text-amber-700'}`}>
                    {resumoAtual.nao_encontrado} não cadastrados
                  </span>
                )}
                {resumoAtual.erro > 0 && (
                  <span className={`px-2 py-0.5 rounded-full font-semibold ${isDark ? 'bg-red-500/15 text-red-300' : 'bg-red-50 text-red-700'}`}>
                    {resumoAtual.erro} com erro
                  </span>
                )}
              </div>
            )}
            <div className="relative">
              <Search className={`absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 ${isDark ? 'text-gray-500' : 'text-gray-400'}`} />
              <input
                type="text"
                placeholder="Buscar evento ou SKU..."
                value={searchTerm}
                onChange={e => setSearchTerm(e.target.value)}
                className={`h-10 pl-9 pr-3 w-56 rounded-xl border text-sm ${isDark ? 'bg-gray-900/50 border-gray-600 text-white placeholder-gray-500' : 'bg-white border-gray-200 text-gray-900 placeholder-gray-400'} focus:outline-none focus:ring-2 focus:ring-emerald-500`}
              />
            </div>
            <div className="relative">
              <select
                value={filterMes}
                onChange={e => setFilterMes(e.target.value)}
                className={selClass}
              >
                <option value="">Todos os meses</option>
                {mesesDisponiveis.map(k => <option key={k} value={k}>{mesLabel(k)}</option>)}
              </select>
              <ChevronDown className={`pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 ${isDark ? 'text-gray-400' : 'text-gray-500'}`} />
            </div>
          </div>

          {error ? (
            <div className="p-4">
              <div className={`flex items-start gap-2.5 p-4 rounded-xl border text-sm ${isDark ? 'bg-red-500/10 border-red-500/40 text-red-300' : 'bg-red-50 border-red-200 text-red-700'}`}>
                <AlertTriangle className="w-5 h-5 mt-0.5 shrink-0" />
                <span className="flex-1">{error}</span>
                <button
                  onClick={carregarEventos}
                  className={`flex items-center gap-1 text-xs font-semibold shrink-0 ${isDark ? 'text-red-300 hover:text-red-200' : 'text-red-600 hover:text-red-800'}`}
                >
                  <RefreshCw className="w-3 h-3" />
                  Tentar novamente
                </button>
              </div>
            </div>
          ) : loading ? (
            <div className={`flex items-center gap-3 p-6 text-sm ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
              <RefreshCw className="w-5 h-5 animate-spin" />
              Consultando o app de Cortesias para todos os eventos futuros... isso pode levar alguns segundos.
            </div>
          ) : eventosFiltrados.length === 0 ? (
            <div className={`flex items-center gap-3 p-6 text-sm ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>
              <Calendar className="w-5 h-5" />
              {eventos.length === 0
                ? 'Nenhum evento futuro com SKU encontrado no cadastro.'
                : 'Nenhum evento corresponde aos filtros.'}
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className={`text-left text-[11px] uppercase tracking-wider ${isDark ? 'text-gray-400 bg-gray-900/30' : 'text-gray-500 bg-gray-50'}`}>
                    <th className="px-4 py-3 font-semibold">Evento</th>
                    <th className="px-4 py-3 font-semibold whitespace-nowrap">Data</th>
                    <th className="px-4 py-3 font-semibold">SKU</th>
                    <th className="px-4 py-3 font-semibold text-right">Solicitados</th>
                    <th className="px-4 py-3 font-semibold text-right">Aprovados</th>
                    <th className="px-4 py-3 font-semibold text-right">Utilizados</th>
                    <th className="px-4 py-3 font-semibold text-right">Disponíveis</th>
                  </tr>
                </thead>
                <tbody className={isDark ? 'divide-y divide-gray-700/50' : 'divide-y divide-gray-100'}>
                  {eventosFiltrados.map(ev => (
                    <tr key={ev.evento_id} className={isDark ? 'hover:bg-gray-700/20' : 'hover:bg-gray-50'}>
                      <td className="px-4 py-3">
                        <p className={`font-semibold ${isDark ? 'text-white' : 'text-gray-900'}`}>{ev.nome}</p>
                        {(ev.cidade || ev.estado) && (
                          <p className={`text-[11px] ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>
                            {[ev.cidade, ev.estado].filter(Boolean).join(' — ')}
                          </p>
                        )}
                      </td>
                      <td className={`px-4 py-3 whitespace-nowrap ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
                        {fmtData(ev.data_evento)}
                      </td>
                      <td className={`px-4 py-3 font-mono text-xs ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>{ev.sku}</td>
                      {ev.status === 'ok' ? (
                        <>
                          <td className={`px-4 py-3 text-right font-semibold ${isDark ? 'text-blue-400' : 'text-blue-600'}`}>{fmtNum(ev.solicitados)}</td>
                          <td className={`px-4 py-3 text-right font-semibold ${isDark ? 'text-emerald-400' : 'text-emerald-600'}`}>{fmtNum(ev.aprovados)}</td>
                          <td className={`px-4 py-3 text-right font-semibold ${isDark ? 'text-amber-400' : 'text-amber-600'}`}>{fmtNum(ev.utilizados)}</td>
                          <td className={`px-4 py-3 text-right font-semibold ${isDark ? 'text-violet-400' : 'text-violet-600'}`}>{fmtNum(ev.disponiveis)}</td>
                        </>
                      ) : ev.status === 'nao_encontrado' ? (
                        <td colSpan={4} className="px-4 py-3">
                          <span
                            title={ev.mensagem || undefined}
                            className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-semibold ${isDark ? 'bg-amber-500/15 text-amber-300 border border-amber-500/30' : 'bg-amber-50 text-amber-700 border border-amber-200'}`}
                          >
                            <Info className="w-3 h-3" />
                            Não cadastrado no app de Cortesias
                          </span>
                        </td>
                      ) : (
                        <td colSpan={4} className="px-4 py-3">
                          <div className={`flex items-center gap-2 text-xs ${isDark ? 'text-red-300' : 'text-red-600'}`}>
                            <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
                            <span className="flex-1 min-w-0">{ev.mensagem || 'Falha na consulta.'}</span>
                            <button
                              onClick={() => retryRow(ev.sku)}
                              disabled={retryingSkus.has(ev.sku)}
                              className={`flex items-center gap-1 font-semibold shrink-0 disabled:opacity-50 ${isDark ? 'text-red-300 hover:text-red-200' : 'text-red-600 hover:text-red-800'}`}
                            >
                              <RefreshCw className={`w-3 h-3 ${retryingSkus.has(ev.sku) ? 'animate-spin' : ''}`} />
                              Tentar novamente
                            </button>
                          </div>
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default CortesiasEventos;
