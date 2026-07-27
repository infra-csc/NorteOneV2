import React from 'react';
import { DollarSign, Sliders, Plus, X } from 'lucide-react';
import { marketingService, MarketingEvent } from '../../services/api';

// Formatadores puros (mesmos usados no EventDetail)
const _nfBR = new Intl.NumberFormat('pt-BR');
const _nfBRL = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' });
const formatNumber = (value: number) => _nfBR.format(value);
const formatCurrency = (value: number) => _nfBRL.format(value);

export interface FaixaPrecoSite {
  faixa: string;
  qtd: number;
  tkt_medio: number;
  total: number;
}

export interface FaixasPrecoSiteData {
  kit_basico: FaixaPrecoSite[];
  kit_participacao: FaixaPrecoSite[];
}

export interface ProjetadoFaixaRow {
  id: string;
  nome: string;
  preco: string;
  qtd: string;
}

interface FaixasPrecoSiteCardProps {
  faixasPrecoSite: FaixasPrecoSiteData | null;
  simuladorFaixas: boolean;
  setSimuladorFaixas: React.Dispatch<React.SetStateAction<boolean>>;
  projetadoFaixas: ProjetadoFaixaRow[];
  setProjetadoFaixas: React.Dispatch<React.SetStateAction<ProjetadoFaixaRow[]>>;
  event: MarketingEvent | null;
  eventId: string | undefined;
  isDark: boolean;
}

/**
 * Card "Faixas de Preço Site (Orçado)" + Simulador de faixas projetadas.
 * Extraído de EventDetail.tsx sem mudança visual ou de comportamento.
 */
const FaixasPrecoSiteCard: React.FC<FaixasPrecoSiteCardProps> = ({
  faixasPrecoSite,
  simuladorFaixas,
  setSimuladorFaixas,
  projetadoFaixas,
  setProjetadoFaixas,
  event,
  eventId,
  isDark,
}) => {
  if (!faixasPrecoSite) return null;
  const id = eventId;

  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm border border-gray-200 dark:border-gray-700">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-gray-900 dark:text-white flex items-center gap-2">
          <DollarSign className="w-4 h-4 text-blue-500" />
          Faixas de Preço Site (Orçado)
        </h3>
        <button
          onClick={() => setSimuladorFaixas(v => !v)}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors ${
            simuladorFaixas
              ? 'bg-purple-600 text-white hover:bg-purple-700'
              : 'bg-purple-50 dark:bg-purple-900/20 text-purple-700 dark:text-purple-300 hover:bg-purple-100 dark:hover:bg-purple-900/40 border border-purple-200 dark:border-purple-700'
          }`}
        >
          <Sliders className="w-3.5 h-3.5" />
          {simuladorFaixas ? 'Fechar Simulador' : 'Simulador'}
        </button>
      </div>

      {!simuladorFaixas ? (
        faixasPrecoSite.kit_basico.length === 0 && faixasPrecoSite.kit_participacao.length === 0 ? (
          /* ── EMPTY STATE: no faixas registered in the project budget ── */
          <div className="py-8 flex flex-col items-center text-center">
            <DollarSign className="w-8 h-8 text-gray-300 dark:text-gray-600 mb-3" />
            <p className="text-sm font-medium text-gray-600 dark:text-gray-300">
              Não há faixas de preço cadastradas no orçamento deste projeto.
            </p>
            <p className="text-xs text-gray-400 dark:text-gray-500 mt-1 max-w-md">
              As faixas são definidas no Cadastro do Projeto. Você ainda pode projetar cenários de preço e volume com o simulador.
            </p>
            <button
              onClick={() => setSimuladorFaixas(true)}
              className="mt-4 flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-purple-50 dark:bg-purple-900/20 text-purple-700 dark:text-purple-300 hover:bg-purple-100 dark:hover:bg-purple-900/40 border border-purple-200 dark:border-purple-700 transition-colors"
            >
              <Sliders className="w-3.5 h-3.5" />
              Abrir Simulador
            </button>
          </div>
        ) : (
        <div className="space-y-4">
          {(['kit_basico', 'kit_participacao'] as const).map((tipoKit) => {
            const faixas = faixasPrecoSite[tipoKit];
            if (faixas.length === 0) return null;
            const totalQtd = faixas.reduce((s, f) => s + f.qtd, 0);
            const totalReceita = faixas.reduce((s, f) => s + f.total, 0);
            const tktMedioGlobal = totalQtd > 0 ? totalReceita / totalQtd : 0;
            const label = tipoKit === 'kit_basico' ? 'Kit Básico' : 'Kit Participação';
            return (
              <div key={tipoKit}>
                <p className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-2">{label}</p>
                <div className="overflow-x-auto rounded-lg border border-gray-200 dark:border-gray-700">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className={`border-b ${isDark ? 'bg-gray-700/50 border-gray-600' : 'bg-gray-50 border-gray-200'}`}>
                        <th className="text-left py-2 px-3 text-xs font-semibold text-gray-500 dark:text-gray-400">Faixa</th>
                        <th className="text-right py-2 px-3 text-xs font-semibold text-gray-500 dark:text-gray-400">Qtd</th>
                        <th className="text-right py-2 px-3 text-xs font-semibold text-gray-500 dark:text-gray-400">Tkt Médio</th>
                        <th className="text-right py-2 px-3 text-xs font-semibold text-gray-500 dark:text-gray-400">Total</th>
                        <th className="text-right py-2 px-3 text-xs font-semibold text-gray-500 dark:text-gray-400">% Qtd</th>
                      </tr>
                    </thead>
                    <tbody>
                      {faixas.map((f, i) => (
                        <tr key={i} className={`border-b border-gray-100 dark:border-gray-700/50 hover:bg-gray-50 dark:hover:bg-gray-700/30`}>
                          <td className="py-2 px-3 font-medium text-gray-900 dark:text-white">Faixa {f.faixa}</td>
                          <td className="py-2 px-3 text-right text-gray-700 dark:text-gray-300">{formatNumber(f.qtd)}</td>
                          <td className="py-2 px-3 text-right text-blue-600 dark:text-blue-400 font-medium">{formatCurrency(f.tkt_medio)}</td>
                          <td className="py-2 px-3 text-right text-gray-700 dark:text-gray-300">{formatCurrency(f.total)}</td>
                          <td className="py-2 px-3 text-right text-gray-500 dark:text-gray-400">{totalQtd > 0 ? ((f.qtd / totalQtd) * 100).toFixed(1) : '0.0'}%</td>
                        </tr>
                      ))}
                      <tr className={`font-semibold ${isDark ? 'bg-gray-700/50' : 'bg-gray-50'}`}>
                        <td className="py-2 px-3 text-gray-900 dark:text-white">Total</td>
                        <td className="py-2 px-3 text-right text-gray-900 dark:text-white">{formatNumber(totalQtd)}</td>
                        <td className="py-2 px-3 text-right text-blue-600 dark:text-blue-400">{formatCurrency(tktMedioGlobal)}</td>
                        <td className="py-2 px-3 text-right text-gray-900 dark:text-white">{formatCurrency(totalReceita)}</td>
                        <td className="py-2 px-3 text-right text-gray-500 dark:text-gray-400">100%</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>
            );
          })}
        </div>
        )
      ) : (
        /* ── SIMULATOR MODE ── */
        (() => {
          // Orçado: uses atletas_site_pago and atletas_site_tkt_medio from the
          // cadastro (salesGoal / budgetTicket), not the faixas breakdown table.
          const orcQtd = event?.salesGoal ?? 0;
          const orcTkt = event?.budgetTicket ?? 0;
          const orcReceita = Math.round(orcQtd * orcTkt * 100) / 100;
          const orcMargemPct = event?.margemOrcadaPct ?? null;

          const realQtd = event?.currentSales ?? 0;
          const realReceita = event?.currentReceita ?? 0;
          const realTkt = event?.averageTicket ?? 0;
          const realMargemPct = event?.margemRealizadaPct ?? null;

          const { custoKitUnit, custoKitNome } = (() => {
            if (event?.margemPorKit && event.margemPorKit.length > 0) {
              const isBasico = (nome: string) =>
                /b[áa]sico/i.test(nome) || /kit.?b[áa]s/i.test(nome);

              const kitsComCusto = event.margemPorKit.filter(k => k.custoKit !== null && k.custoKit !== undefined && k.qtd > 0);
              if (kitsComCusto.length > 0) {
                const kitsBas = kitsComCusto.filter(k => isBasico(k.tipoKit));
                const kitsAlvo = kitsBas.length > 0 ? kitsBas : kitsComCusto;
                const totalQtd = kitsAlvo.reduce((s, k) => s + k.qtd, 0);
                const custo = kitsAlvo.reduce((s, k) => s + (k.custoKit ?? 0) * k.qtd, 0) / totalQtd;
                const nome = kitsBas.length > 0 ? kitsAlvo[0].tipoKit : 'média ponderada';
                return { custoKitUnit: custo, custoKitNome: nome };
              }
            }
            return { custoKitUnit: (event?.kitCostPerUnit ?? null) as number | null, custoKitNome: 'kit' };
          })();

          const projRows = projetadoFaixas
            .map(r => ({ ...r, precoN: parseFloat(r.preco.replace(',', '.')) || 0, qtdN: parseInt(r.qtd, 10) || 0 }))
            .filter(r => r.precoN > 0 && r.qtdN > 0);
          // Incremental (only what was typed in the simulator)
          const projOnlyQtd = projRows.reduce((s, r) => s + r.qtdN, 0);
          const projOnlyReceita = projRows.reduce((s, r) => s + r.precoN * r.qtdN, 0);
          // Combined = Real Atual + Faixas Projetadas (projected final outcome)
          const projQtd = realQtd + projOnlyQtd;
          const projReceita = realReceita + projOnlyReceita;
          const projTkt = projQtd > 0 ? projReceita / projQtd : 0;
          const projMargemVal: number | null = (custoKitUnit !== null && projQtd > 0)
            ? projReceita - custoKitUnit * projQtd
            : null;

          const orcMargemVal: number | null = orcMargemPct !== null && orcReceita > 0
            ? orcReceita * orcMargemPct / 100
            : null;
          const realMargemVal: number | null = realMargemPct !== null && realReceita > 0
            ? realReceita * realMargemPct / 100
            : null;

          const deltaBadge = (proj: number | null, orc: number | null, isCurrency = false) => {
            if (proj === null || orc === null || orc === 0) return null;
            const diff = proj - orc;
            const pctDiff = (diff / Math.abs(orc)) * 100;
            const isPos = diff >= 0;
            return (
              <span className={`inline-flex items-center gap-0.5 text-xs font-bold px-1.5 py-0.5 rounded ${isPos ? 'bg-green-100 text-green-700 dark:bg-green-800/60 dark:text-green-300' : 'bg-red-100 text-red-700 dark:bg-red-800/60 dark:text-red-300'}`}>
                {isPos ? '▲' : '▼'}{isCurrency ? formatCurrency(Math.abs(diff)) : formatNumber(Math.abs(diff))} ({Math.abs(pctDiff).toFixed(1)}%)
              </span>
            );
          };
          const hasValidProjRows = projRows.length > 0;
          // Projetado card shows values whenever there's real data OR typed faixas
          const hasProjData = projQtd > 0;

          const colCard = (
            title: string,
            accent: string,
            titleColor: string,
            qtd: number,
            tkt: number,
            receita: number,
            margemVal: number | null,
            isProj = false,
            subtitle?: string
          ) => (
            <div className={`rounded-xl border p-4 ${accent}`}>
              <div className="mb-4">
                <p className={`text-xs font-extrabold uppercase tracking-widest ${titleColor}`}>{title}</p>
                {subtitle && <p className="text-[10px] text-gray-400 dark:text-gray-500 mt-0.5">{subtitle}</p>}
              </div>
              <div className="space-y-3">
                <div>
                  <div className="flex items-center gap-1.5 mb-0.5">
                    <p className="text-sm font-semibold text-gray-600 dark:text-gray-300">Qtd. Inscritos</p>
                    {isProj && deltaBadge(hasValidProjRows ? qtd : null, orcQtd > 0 ? orcQtd : null)}
                  </div>
                  <p className="text-base font-bold text-gray-900 dark:text-white">
                    {hasProjData || !isProj ? (qtd > 0 ? formatNumber(qtd) : '0') : '—'}
                  </p>
                </div>
                <div>
                  <div className="flex items-center gap-1.5 mb-0.5">
                    <p className="text-sm font-semibold text-gray-600 dark:text-gray-300">Ticket Médio</p>
                    {isProj && deltaBadge(hasValidProjRows ? tkt : null, orcTkt > 0 ? orcTkt : null, true)}
                  </div>
                  <p className="text-base font-bold text-blue-600 dark:text-blue-400">
                    {hasProjData || !isProj ? (tkt > 0 ? formatCurrency(tkt) : '—') : '—'}
                  </p>
                </div>
                <div>
                  <div className="flex items-center gap-1.5 mb-0.5">
                    <p className="text-sm font-semibold text-gray-600 dark:text-gray-300">Receita Total</p>
                    {isProj && deltaBadge(hasValidProjRows ? receita : null, orcReceita > 0 ? orcReceita : null, true)}
                  </div>
                  <p className="text-base font-bold text-gray-900 dark:text-white">
                    {hasProjData || !isProj ? (receita > 0 ? formatCurrency(receita) : 'R$ 0,00') : '—'}
                  </p>
                </div>
                <div className={`pt-3 border-t ${isDark ? 'border-gray-600' : 'border-gray-200'}`}>
                  <div className="flex items-center gap-1.5 mb-0.5">
                    <p className="text-sm font-semibold text-gray-600 dark:text-gray-300">Margem (R$)</p>
                    {isProj && deltaBadge(hasValidProjRows ? margemVal : null, orcMargemVal, true)}
                  </div>
                  <p className={`text-base font-bold ${margemVal !== null && margemVal >= 0 ? 'text-emerald-600 dark:text-emerald-400' : margemVal !== null ? 'text-red-500' : 'text-gray-400 dark:text-gray-500'}`}>
                    {margemVal !== null ? formatCurrency(margemVal) : '—'}
                  </p>
                  {margemVal !== null && receita > 0 && (
                    <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">{((margemVal / receita) * 100).toFixed(1)}% da receita</p>
                  )}
                </div>
              </div>
            </div>
          );

          return (
            <div>
              <div className="grid grid-cols-3 gap-3 mb-6">
                {colCard('Orçado', isDark ? 'bg-gray-700/40 border-gray-600' : 'bg-gray-50 border-gray-200', 'text-gray-500 dark:text-gray-400', orcQtd, orcTkt, orcReceita, orcMargemVal)}
                {colCard('Real Atual', isDark ? 'bg-blue-900/20 border-blue-700' : 'bg-blue-50 border-blue-200', 'text-blue-600 dark:text-blue-400', realQtd, realTkt, realReceita, realMargemVal)}
                {colCard('Projetado', isDark ? 'bg-purple-900/20 border-purple-700' : 'bg-purple-50 border-purple-200', 'text-purple-600 dark:text-purple-400', projQtd, projTkt, projReceita, projMargemVal, true, 'Real atual + faixas projetadas')}
              </div>

              <div className="mb-2 flex items-center justify-between">
                <p className="text-xs font-semibold text-gray-600 dark:text-gray-300 uppercase tracking-wider">Faixas Projetadas</p>
                <div className="flex items-center gap-3">
                  {custoKitUnit !== null && (
                    <span className="text-[10px] text-gray-400 dark:text-gray-500">
                      Custo usado ({custoKitNome}): {formatCurrency(custoKitUnit)}/unid.
                    </span>
                  )}
                  {projetadoFaixas.length > 0 && (
                    <button
                      onClick={() => {
                        setProjetadoFaixas([]);
                        if (id) {
                          localStorage.removeItem(`proj_faixas_${id}`);
                          marketingService.deleteProjetadoFaixas(id).catch(() => {});
                        }
                      }}
                      className="text-[10px] font-semibold text-red-500 hover:text-red-700 dark:text-red-400 dark:hover:text-red-300 transition-colors"
                    >
                      Limpar projeção
                    </button>
                  )}
                </div>
              </div>

              <div className="rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden mb-3">
                <table className="w-full text-sm table-fixed">
                  <colgroup>
                    <col className="w-auto" />
                    <col style={{width: '6rem'}} />
                    <col style={{width: '7rem'}} />
                    <col style={{width: '8rem'}} />
                    <col style={{width: '8rem'}} />
                    <col style={{width: '2rem'}} />
                  </colgroup>
                  <thead>
                    <tr className={`border-b ${isDark ? 'bg-gray-700/50 border-gray-600' : 'bg-gray-50 border-gray-200'}`}>
                      <th className="text-left py-2 px-2 text-xs font-semibold text-gray-500 dark:text-gray-400">Faixa</th>
                      <th className="text-right py-2 px-2 text-xs font-semibold text-gray-500 dark:text-gray-400">Qtd</th>
                      <th className="text-right py-2 px-2 text-xs font-semibold text-gray-500 dark:text-gray-400">Ticket Médio</th>
                      <th className="text-right py-2 px-2 text-xs font-semibold text-gray-500 dark:text-gray-400">Receita</th>
                      <th className="text-right py-2 px-2 text-xs font-semibold text-gray-500 dark:text-gray-400">Margem</th>
                      <th className="py-2 px-1"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {projetadoFaixas.length === 0 && (
                      <tr>
                        <td colSpan={6} className="py-6 text-center text-xs text-gray-400 dark:text-gray-500">
                          Nenhuma faixa projetada. Clique em "+ Adicionar Faixa" para começar.
                        </td>
                      </tr>
                    )}
                    {projetadoFaixas.map((row) => {
                      const precoN = parseFloat(row.preco.replace(',', '.')) || 0;
                      const qtdN = parseInt(row.qtd, 10) || 0;
                      const rowReceita = precoN * qtdN;
                      const rowMargem = custoKitUnit !== null && qtdN > 0 ? rowReceita - custoKitUnit * qtdN : null;
                      return (
                        <tr key={row.id} className={`border-b border-gray-100 dark:border-gray-700/50`}>
                          <td className="py-1.5 px-2">
                            <input
                              type="text"
                              value={row.nome}
                              placeholder="Ex: Lote 1"
                              onChange={e => setProjetadoFaixas(prev => prev.map(r => r.id === row.id ? { ...r, nome: e.target.value } : r))}
                              className="w-full text-xs bg-transparent border border-gray-200 dark:border-gray-600 rounded px-2 py-1 text-gray-900 dark:text-white placeholder-gray-400 focus:outline-none focus:ring-1 focus:ring-purple-500"
                            />
                          </td>
                          <td className="py-1.5 px-2">
                            <input
                              type="text"
                              inputMode="numeric"
                              value={row.qtd ? (parseInt(row.qtd, 10) || 0) > 0 ? (parseInt(row.qtd, 10)).toLocaleString('pt-BR') : row.qtd : row.qtd}
                              placeholder="0"
                              onChange={e => {
                                const raw = e.target.value.replace(/\./g, '').replace(/\D/g, '');
                                setProjetadoFaixas(prev => prev.map(r => r.id === row.id ? { ...r, qtd: raw } : r));
                              }}
                              className="w-full text-xs bg-transparent border border-gray-200 dark:border-gray-600 rounded px-2 py-1 text-right text-gray-900 dark:text-white placeholder-gray-400 focus:outline-none focus:ring-1 focus:ring-purple-500"
                            />
                          </td>
                          <td className="py-1.5 px-2">
                            <input
                              type="text"
                              inputMode="decimal"
                              value={row.preco}
                              placeholder="0,00"
                              onChange={e => setProjetadoFaixas(prev => prev.map(r => r.id === row.id ? { ...r, preco: e.target.value } : r))}
                              className="w-full text-xs bg-transparent border border-gray-200 dark:border-gray-600 rounded px-2 py-1 text-right text-gray-900 dark:text-white placeholder-gray-400 focus:outline-none focus:ring-1 focus:ring-purple-500"
                            />
                          </td>
                          <td className="py-1.5 px-2 text-right text-xs text-gray-700 dark:text-gray-300 font-medium">
                            {rowReceita > 0 ? formatCurrency(rowReceita) : '—'}
                          </td>
                          <td className={`py-1.5 px-2 text-right text-xs font-medium ${rowMargem !== null && rowMargem >= 0 ? 'text-emerald-600 dark:text-emerald-400' : rowMargem !== null ? 'text-red-500 dark:text-red-400' : 'text-gray-400 dark:text-gray-500'}`}>
                            {rowMargem !== null ? formatCurrency(rowMargem) : '—'}
                          </td>
                          <td className="py-1.5 px-2 text-center">
                            <button
                              onClick={() => setProjetadoFaixas(prev => prev.filter(r => r.id !== row.id))}
                              className="text-gray-400 hover:text-red-500 dark:hover:text-red-400 transition-colors"
                            >
                              <X className="w-3.5 h-3.5" />
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                    {projetadoFaixas.length > 0 && projQtd > 0 && (
                      <tr className={`font-semibold text-xs ${isDark ? 'bg-gray-700/50' : 'bg-gray-50'}`}>
                        <td className="py-2 px-3 text-gray-700 dark:text-gray-300">Total</td>
                        <td className="py-2 px-3 text-right text-gray-500 dark:text-gray-400 font-normal italic">Tkt médio: {formatCurrency(projTkt)}</td>
                        <td className="py-2 px-3 text-right text-gray-900 dark:text-white">{formatNumber(projQtd)}</td>
                        <td className="py-2 px-3 text-right text-gray-900 dark:text-white">{formatCurrency(projReceita)}</td>
                        <td className="py-2 px-3 text-right text-gray-500 dark:text-gray-400">100%</td>
                        <td></td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>

              <button
                onClick={() => setProjetadoFaixas(prev => [...prev, { id: `${Date.now()}`, nome: '', preco: '', qtd: '' }])}
                className="flex items-center gap-1.5 text-xs font-semibold text-purple-600 dark:text-purple-400 hover:text-purple-800 dark:hover:text-purple-300 transition-colors"
              >
                <Plus className="w-3.5 h-3.5" />
                Adicionar Faixa
              </button>
            </div>
          );
        })()
      )}
    </div>
  );
};

export default FaixasPrecoSiteCard;
