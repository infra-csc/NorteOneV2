import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { cortesiaSolicitacaoService } from '../../services/api';
import type { CortesiaEventoSaldoResponse, CortesiaEventoFilaOpcao, CortesiaSolicitacaoResponse, CupomCodigoItem } from '../../services/api';
import { useTheme } from '../../context/ThemeContext';
import { usePermissions } from '../../context/PermissionContext';
import {
  Gift, Plus, X, RefreshCw, AlertTriangle, Ticket, FileSpreadsheet,
  CheckCircle2, Clock, Download, Trash2, ChevronDown, ChevronUp,
  LayoutGrid, List as ListIcon, Copy, Check, ClipboardList, FileDown,
  ToggleLeft, ToggleRight, Search, ChevronsDown, ChevronsUp,
  ClipboardCheck,
} from 'lucide-react';

// ─────────────────────────────────────────────────────────────
// Solicitação de Cortesias
//
// Tela nova e independente da "Cortesias por Evento" (que só espelha o app
// externo, somente-leitura). Aqui o responsável de cada área abre uma
// solicitação de cortesias para um evento — cupom a ser gerado manualmente
// depois, ou planilha do cliente com a lista de participantes — respeitando
// como trava o saldo (projetado na Projeção de Inscritos - já solicitado).
// Sem etapa de aprovação: a checagem de saldo já é a única trava.
//
// Duas abas: "Solicitações" (quem pede — tabela ou Kanban, à escolha do
// usuário) e "Geração de Cupons" (quem gera os códigos — fila dedicada, sem
// recorte por área, com exportação em CSV). A segunda só aparece para quem
// tem a permissão de editar (pode_editar) deste módulo.
// ─────────────────────────────────────────────────────────────

const VISUALIZACAO_STORAGE_KEY = 'cortesias_solicitacoes_visualizacao';

// Deve ficar em sincronia com _FILA_GERADOS_JANELA_DIAS no backend
// (backend/app/api/routes/cortesia_solicitacao.py) — é só o texto exibido,
// o corte de verdade é aplicado no servidor.
const FILA_GERADOS_JANELA_DIAS = 90;

const fmtData = (iso: string | null | undefined): string => {
  if (!iso) return '—';
  const [y, m, d] = iso.split('-');
  if (!y || !m || !d) return iso;
  return `${d}/${m}/${y}`;
};

const fmtDataHora = (iso: string | null | undefined): string => {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString('pt-BR');
  } catch {
    return iso;
  }
};

const fmtTamanhoArquivo = (bytes: number): string => {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
};

const extractError = (e: any): string => {
  const detail = e?.response?.data?.detail;
  if (typeof detail === 'string' && detail.trim()) return detail;
  return 'Não foi possível concluir a operação. Tente novamente.';
};

// Mesma regra de quebra usada no backend (_parse_codigos_cupom): um código
// por linha, ou separados por vírgula/ponto e vírgula — para colar de
// qualquer fonte (planilha, e-mail, sistema de geração) sem reformatar.
const parseCodigos = (texto: string): string[] =>
  texto.split(/[\r\n,;]+/).map(c => c.trim()).filter(Boolean);

const codigosDe = (sol: CortesiaSolicitacaoResponse): string[] =>
  (sol.codigo_cupom_lista && sol.codigo_cupom_lista.length > 0)
    ? sol.codigo_cupom_lista
    : parseCodigos(sol.codigo_cupom || '');

interface FormState {
  evento_id: number;
  evento_nome: string;
  evento_sku: string | null | undefined;
  area_projecao_id: number;
  area_projecao_nome: string;
  area_sigla: string | null | undefined;
  saldo: number;
}

type Aba = 'solicitacoes' | 'acompanhamento' | 'geracao';
type Visualizacao = 'tabela' | 'kanban';
type KanbanColKey = 'aguardando' | 'gerado' | 'recebida';

const KANBAN_COLUNAS: { key: KanbanColKey; titulo: string }[] = [
  { key: 'aguardando', titulo: 'Aguardando geração' },
  { key: 'gerado', titulo: 'Gerado' },
  { key: 'recebida', titulo: 'Recebida' },
];

const colunaDe = (sol: CortesiaSolicitacaoResponse): KanbanColKey => {
  if (sol.tipo === 'planilha') return 'recebida';
  return sol.status === 'gerado' ? 'gerado' : 'aguardando';
};

// Lista de códigos reutilizada na tabela, no Kanban e na aba de geração.
// "compact": poucos chips + copiar tudo (linha/card de uma solicitação).
// "full": lista completa rolável, com copiar por código e toggle de uso (aba de geração).
//
// Quando codigos_detalhes está disponível, mostra badge usado/disponível por código.
// O toggle só aparece em variant="full" quando onToggleUsado é passado.
interface CodigosListProps {
  codigos: string[];
  isDark: boolean;
  variant?: 'compact' | 'full';
  detalhes?: CupomCodigoItem[];
  onToggleUsado?: (item: CupomCodigoItem) => void;
  togglingId?: number | null;
}

const CodigosList: React.FC<CodigosListProps> = ({ codigos, isDark, variant = 'compact', detalhes, onToggleUsado, togglingId }) => {
  const [copiedAll, setCopiedAll] = useState(false);
  const [copiedIdx, setCopiedIdx] = useState<number | null>(null);

  if (codigos.length === 0) return null;

  const copiarTudo = async () => {
    try {
      await navigator.clipboard.writeText(codigos.join('\n'));
      setCopiedAll(true);
      setTimeout(() => setCopiedAll(false), 1500);
    } catch {
      // clipboard indisponível (contexto não seguro, permissão negada) — ignora
    }
  };

  const copiarUm = async (codigo: string, idx: number) => {
    try {
      await navigator.clipboard.writeText(codigo);
      setCopiedIdx(idx);
      setTimeout(() => setCopiedIdx(null), 1200);
    } catch {
      // idem
    }
  };

  // Quantos códigos já foram marcados como usados (para a variante compact)
  const usadosCount = detalhes ? detalhes.filter(d => d.usado).length : 0;

  if (variant === 'compact') {
    const visiveis = codigos.slice(0, 3);
    const resto = codigos.length - visiveis.length;
    return (
      <div className="flex flex-wrap items-center gap-1 mt-1">
        {visiveis.map((c, i) => {
          const det = detalhes?.[i];
          return (
            <span
              key={i}
              className={`px-1.5 py-0.5 rounded text-[10px] font-mono ${
                det?.usado
                  ? (isDark ? 'bg-gray-700 text-gray-500 line-through' : 'bg-gray-100 text-gray-400 line-through')
                  : (isDark ? 'bg-gray-900/60 text-gray-300' : 'bg-gray-100 text-gray-700')
              }`}
              title={det?.usado ? `Usado em ${det.usado_em ? new Date(det.usado_em).toLocaleString('pt-BR') : '—'}` : undefined}
            >
              {c}
            </span>
          );
        })}
        {resto > 0 && (
          <span className={`text-[10px] ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>+{resto}</span>
        )}
        {detalhes && usadosCount > 0 && (
          <span className={`text-[10px] font-semibold ${isDark ? 'text-amber-400' : 'text-amber-600'}`}>
            {usadosCount}/{detalhes.length} usados
          </span>
        )}
        <button
          type="button"
          onClick={copiarTudo}
          title="Copiar todos os códigos"
          className={`inline-flex items-center gap-0.5 text-[10px] font-semibold transition-colors ${isDark ? 'text-gray-400 hover:text-white' : 'text-gray-500 hover:text-gray-800'}`}
        >
          {copiedAll ? <Check className="w-3 h-3 text-emerald-500" /> : <Copy className="w-3 h-3" />}
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between">
        <p className={`text-[11px] font-semibold ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
          {codigos.length} código(s)
          {detalhes && usadosCount > 0 && (
            <span className={`ml-1.5 ${isDark ? 'text-amber-400' : 'text-amber-600'}`}>
              · {usadosCount} usado{usadosCount !== 1 ? 's' : ''}
            </span>
          )}
        </p>
        <button
          type="button"
          onClick={copiarTudo}
          className={`inline-flex items-center gap-1 text-[11px] font-semibold px-2 py-0.5 rounded-lg transition-colors ${isDark ? 'bg-gray-700 text-gray-300 hover:bg-gray-600' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'}`}
        >
          {copiedAll ? <Check className="w-3 h-3" /> : <Copy className="w-3 h-3" />} {copiedAll ? 'Copiado' : 'Copiar todos'}
        </button>
      </div>
      <div className={`max-h-48 overflow-y-auto rounded-lg border divide-y ${isDark ? 'border-gray-700 divide-gray-700' : 'border-gray-200 divide-gray-100'}`}>
        {codigos.map((c, i) => {
          const det = detalhes?.[i];
          const isUsado = det?.usado ?? false;
          const isToggling = det && togglingId === det.id;
          return (
            <div
              key={det?.id ?? i}
              className={`flex items-center gap-2 px-2 py-1.5 text-xs font-mono ${
                isUsado
                  ? (isDark ? 'bg-gray-900/40 text-gray-600' : 'bg-gray-50 text-gray-400')
                  : (isDark ? 'text-gray-200' : 'text-gray-700')
              }`}
            >
              {/* Used/available badge */}
              {detalhes && (
                <span
                  className={`shrink-0 text-[9px] font-bold uppercase rounded px-1 py-0.5 ${
                    isUsado
                      ? (isDark ? 'bg-gray-700 text-gray-500' : 'bg-gray-200 text-gray-500')
                      : (isDark ? 'bg-emerald-500/20 text-emerald-400' : 'bg-emerald-100 text-emerald-700')
                  }`}
                  title={isUsado && det?.usado_em ? `Usado em ${new Date(det.usado_em).toLocaleString('pt-BR')}${det.usado_por_nome ? ` por ${det.usado_por_nome}` : ''}` : undefined}
                >
                  {isUsado ? 'Usado' : 'Disponível'}
                </span>
              )}
              <span className={`flex-1 truncate ${isUsado ? 'line-through' : ''}`}>{c}</span>
              <div className="shrink-0 flex items-center gap-1">
                {/* Copy button */}
                <button type="button" onClick={() => copiarUm(c, i)} title="Copiar código" className={`${isDark ? 'text-gray-500 hover:text-white' : 'text-gray-400 hover:text-gray-700'}`}>
                  {copiedIdx === i ? <Check className="w-3 h-3 text-emerald-500" /> : <Copy className="w-3 h-3" />}
                </button>
                {/* Toggle used button */}
                {onToggleUsado && det && (
                  <button
                    type="button"
                    disabled={!!isToggling}
                    onClick={() => onToggleUsado(det)}
                    title={isUsado ? 'Marcar como disponível' : 'Marcar como usado'}
                    className={`transition-colors disabled:opacity-40 ${
                      isUsado
                        ? (isDark ? 'text-amber-400 hover:text-amber-300' : 'text-amber-500 hover:text-amber-700')
                        : (isDark ? 'text-gray-500 hover:text-emerald-400' : 'text-gray-400 hover:text-emerald-600')
                    }`}
                  >
                    {isUsado ? <ToggleRight className="w-3.5 h-3.5" /> : <ToggleLeft className="w-3.5 h-3.5" />}
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

interface CardActionsProps {
  sol: CortesiaSolicitacaoResponse;
  isDark: boolean;
  podeGerarCupom: boolean;
  podeCancelar: boolean;
  cancelandoId: number | null;
  onGerar: (sol: CortesiaSolicitacaoResponse) => void;
  onCancelar: (sol: CortesiaSolicitacaoResponse) => void;
  onBaixar: (sol: CortesiaSolicitacaoResponse) => void;
  onToggleUsado?: (sol: CortesiaSolicitacaoResponse, item: CupomCodigoItem) => void;
  togglingCodigoId?: number | null;
}

const KanbanCard: React.FC<CardActionsProps> = ({ sol, isDark, podeGerarCupom, podeCancelar, cancelandoId, onGerar, onCancelar, onBaixar, onToggleUsado, togglingCodigoId }) => {
  const codigos = codigosDe(sol);
  return (
    <div className={`rounded-xl border p-3 space-y-2 ${isDark ? 'bg-gray-800/60 border-gray-700' : 'bg-white border-gray-200'}`}>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className={`text-xs font-bold truncate ${isDark ? 'text-white' : 'text-gray-900'}`}>{sol.evento_nome}</p>
          <p className={`text-[11px] truncate ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>{sol.area_projecao_nome}</p>
        </div>
        <span className={`inline-flex items-center gap-1 text-[10px] font-semibold px-1.5 py-0.5 rounded shrink-0 ${isDark ? 'bg-gray-700 text-gray-300' : 'bg-gray-100 text-gray-600'}`}>
          {sol.tipo === 'cupom' ? <Ticket className="w-3 h-3" /> : <FileSpreadsheet className="w-3 h-3" />}
          {sol.quantidade}
        </span>
      </div>
      {codigos.length > 0 && (
        <CodigosList
          codigos={codigos}
          isDark={isDark}
          variant="compact"
          detalhes={sol.codigos_detalhes}
        />
      )}
      {sol.observacao && (
        <p className={`text-[11px] italic line-clamp-2 ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>{sol.observacao}</p>
      )}
      <div className={`flex items-center justify-between gap-2 text-[10px] ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>
        <span className="truncate">{sol.solicitado_por_nome || '—'}</span>
        <span className="shrink-0">{fmtDataHora(sol.created_at)}</span>
      </div>
      <div className="flex items-center justify-end gap-1.5 pt-1">
        {sol.tipo === 'planilha' && sol.nome_arquivo && (
          <button type="button" onClick={() => onBaixar(sol)} title="Baixar arquivo" className={`p-1.5 rounded-lg transition-colors ${isDark ? 'hover:bg-gray-700 text-gray-400' : 'hover:bg-gray-100 text-gray-500'}`}>
            <Download className="w-3.5 h-3.5" />
          </button>
        )}
        {sol.tipo === 'cupom' && sol.status === 'solicitado' && podeGerarCupom && (
          <button type="button" onClick={() => onGerar(sol)} className={`px-2 py-1 rounded-lg text-[11px] font-semibold transition-colors ${isDark ? 'bg-blue-500/20 text-blue-400 hover:bg-blue-500/30' : 'bg-blue-100 text-blue-700 hover:bg-blue-200'}`}>
            Marcar gerado
          </button>
        )}
        {podeCancelar && (
          <button type="button" disabled={cancelandoId === sol.id} onClick={() => onCancelar(sol)} title="Cancelar solicitação" className={`p-1.5 rounded-lg transition-colors ${isDark ? 'hover:bg-red-500/20 text-red-400' : 'hover:bg-red-50 text-red-500'} disabled:opacity-50`}>
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        )}
      </div>
    </div>
  );
};

const KanbanBoard: React.FC<{ solicitacoes: CortesiaSolicitacaoResponse[] } & Omit<CardActionsProps, 'sol'>> = ({ solicitacoes, isDark, ...cardProps  }) => {
  const porColuna = useMemo(() => {
    const grupos: Record<KanbanColKey, CortesiaSolicitacaoResponse[]> = { aguardando: [], gerado: [], recebida: [] };
    for (const sol of solicitacoes) grupos[colunaDe(sol)].push(sol);
    return grupos;
  }, [solicitacoes]);

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
      {KANBAN_COLUNAS.map(col => (
        <div key={col.key} className={`rounded-xl border ${isDark ? 'border-gray-700 bg-gray-900/30' : 'border-gray-200 bg-gray-50/60'}`}>
          <div className={`flex items-center justify-between px-3 py-2 border-b ${isDark ? 'border-gray-700' : 'border-gray-200'}`}>
            <span className={`text-xs font-bold ${isDark ? 'text-gray-200' : 'text-gray-700'}`}>{col.titulo}</span>
            <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded-full ${isDark ? 'bg-gray-700 text-gray-300' : 'bg-white text-gray-500 border border-gray-200'}`}>{porColuna[col.key].length}</span>
          </div>
          <div className="p-2 space-y-2 max-h-[560px] overflow-y-auto">
            {porColuna[col.key].length === 0 ? (
              <p className={`text-[11px] text-center py-4 ${isDark ? 'text-gray-600' : 'text-gray-400'}`}>Nenhuma solicitação</p>
            ) : (
              porColuna[col.key].map(sol => (
                <KanbanCard key={sol.id} sol={sol} isDark={isDark} {...cardProps} />
              ))
            )}
          </div>
        </div>
      ))}
    </div>
  );
};

// ─────────────────────────────────────────────────────────────
// Filtro padrão — mesmo componente e mesmo conjunto de campos (busca,
// evento, área, e opcionalmente tipo/status) em Acompanhamento e Geração de
// Cupons, para que o usuário aprenda o padrão uma vez e reaproveite nas
// duas telas.
// ─────────────────────────────────────────────────────────────
interface OpcaoFiltro { id: number; nome: string; }

interface FiltroSolicitacoes {
  busca: string;
  areaId: number | '';
  eventoId: number | '';
  tipo: '' | 'cupom' | 'planilha';
  status: '' | KanbanColKey;
}

const FILTRO_VAZIO: FiltroSolicitacoes = { busca: '', areaId: '', eventoId: '', tipo: '', status: '' };

const filtroEstaAtivo = (f: Partial<FiltroSolicitacoes>): boolean =>
  Boolean(f.busca?.trim() || f.areaId || f.eventoId || f.tipo || f.status);

const opcoesArea = (lista: CortesiaSolicitacaoResponse[]): OpcaoFiltro[] => {
  const map = new Map<number, string>();
  for (const s of lista) if (!map.has(s.area_projecao_id)) map.set(s.area_projecao_id, s.area_projecao_nome || `Área ${s.area_projecao_id}`);
  return Array.from(map, ([id, nome]) => ({ id, nome })).sort((a, b) => a.nome.localeCompare(b.nome, 'pt-BR'));
};

const opcoesEvento = (lista: CortesiaSolicitacaoResponse[]): OpcaoFiltro[] => {
  const map = new Map<number, string>();
  for (const s of lista) if (!map.has(s.evento_id)) map.set(s.evento_id, s.evento_nome || `Evento ${s.evento_id}`);
  return Array.from(map, ([id, nome]) => ({ id, nome })).sort((a, b) => a.nome.localeCompare(b.nome, 'pt-BR'));
};

const buscaCasa = (sol: CortesiaSolicitacaoResponse, busca: string): boolean => {
  const alvo = busca.trim().toLowerCase();
  if (!alvo) return true;
  return [sol.evento_nome, sol.area_projecao_nome, sol.solicitado_por_nome, sol.gerado_por_nome, sol.observacao]
    .some(v => (v || '').toLowerCase().includes(alvo));
};

// opts.ignorarEvento: Geração de Cupons já usa o campo Evento do filtro para
// trocar a janela de "Gerados" no backend (histórico completo daquele
// evento) — reaplicar o mesmo filtro no cliente aí seria redundante, então
// pendentes filtra por evento e gerados não.
const aplicarFiltro = (
  lista: CortesiaSolicitacaoResponse[],
  filtro: Partial<FiltroSolicitacoes>,
  opts?: { ignorarEvento?: boolean }
): CortesiaSolicitacaoResponse[] =>
  lista.filter(s =>
    buscaCasa(s, filtro.busca || '') &&
    (!filtro.areaId || s.area_projecao_id === filtro.areaId) &&
    (opts?.ignorarEvento || !filtro.eventoId || s.evento_id === filtro.eventoId) &&
    (!filtro.tipo || s.tipo === filtro.tipo) &&
    (!filtro.status || colunaDe(s) === filtro.status)
  );

interface FiltroBarProps {
  isDark: boolean;
  busca: string;
  onBusca: (v: string) => void;
  buscaPlaceholder?: string;
  areaId: number | '';
  onArea: (v: number | '') => void;
  areaOpcoes: OpcaoFiltro[];
  eventoId?: number | '';
  onEvento?: (v: number | '') => void;
  eventoOpcoes?: OpcaoFiltro[];
  eventoPlaceholder?: string;
  status?: '' | KanbanColKey;
  onStatus?: (v: '' | KanbanColKey) => void;
  tipo?: '' | 'cupom' | 'planilha';
  onTipo?: (v: '' | 'cupom' | 'planilha') => void;
  onLimpar: () => void;
  resultCount: number;
  resultLabel?: string;
}

const FiltroBar: React.FC<FiltroBarProps> = ({
  isDark, busca, onBusca, buscaPlaceholder, areaId, onArea, areaOpcoes,
  eventoId, onEvento, eventoOpcoes, eventoPlaceholder, status, onStatus, tipo, onTipo,
  onLimpar, resultCount, resultLabel,
}) => {
  const selectCls = `px-2.5 py-1.5 rounded-lg border text-xs font-medium focus:outline-none focus:ring-2 focus:ring-emerald-500 ${isDark ? 'bg-gray-900/50 border-gray-600 text-white' : 'bg-white border-gray-300 text-gray-900'}`;
  const ativo = filtroEstaAtivo({ busca, areaId, eventoId, tipo, status });
  return (
    <div className={`flex flex-wrap items-center gap-2 p-3 rounded-xl border mb-3 ${isDark ? 'border-gray-700 bg-gray-900/30' : 'border-gray-200 bg-gray-50/60'}`}>
      <div className={`flex items-center gap-1.5 flex-1 min-w-[180px] px-2.5 py-1.5 rounded-lg border ${isDark ? 'bg-gray-900/50 border-gray-600' : 'bg-white border-gray-300'}`}>
        <Search className={`w-3.5 h-3.5 shrink-0 ${isDark ? 'text-gray-500' : 'text-gray-400'}`} />
        <input
          type="text"
          value={busca}
          onChange={e => onBusca(e.target.value)}
          placeholder={buscaPlaceholder || 'Buscar por evento, área ou solicitante...'}
          className={`w-full bg-transparent text-xs focus:outline-none ${isDark ? 'text-gray-200 placeholder:text-gray-600' : 'text-gray-800 placeholder:text-gray-400'}`}
        />
      </div>
      {onEvento && (
        <select value={eventoId ?? ''} onChange={e => onEvento(e.target.value ? Number(e.target.value) : '')} className={selectCls}>
          <option value="">{eventoPlaceholder || 'Todos os eventos'}</option>
          {(eventoOpcoes || []).map(o => <option key={o.id} value={o.id}>{o.nome}</option>)}
        </select>
      )}
      <select value={areaId} onChange={e => onArea(e.target.value ? Number(e.target.value) : '')} className={selectCls}>
        <option value="">Todas as áreas</option>
        {areaOpcoes.map(o => <option key={o.id} value={o.id}>{o.nome}</option>)}
      </select>
      {onTipo && (
        <select value={tipo} onChange={e => onTipo(e.target.value as '' | 'cupom' | 'planilha')} className={selectCls}>
          <option value="">Cupom e planilha</option>
          <option value="cupom">Só cupom</option>
          <option value="planilha">Só planilha</option>
        </select>
      )}
      {onStatus && (
        <select value={status} onChange={e => onStatus(e.target.value as '' | KanbanColKey)} className={selectCls}>
          <option value="">Todos os status</option>
          <option value="aguardando">Aguardando geração</option>
          <option value="gerado">Gerado</option>
          <option value="recebida">Recebida</option>
        </select>
      )}
      <span className={`text-[11px] font-medium whitespace-nowrap ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>
        {resultCount} {resultLabel || 'resultado(s)'}
      </span>
      {ativo && (
        <button type="button" onClick={onLimpar} className={`text-[11px] font-semibold underline whitespace-nowrap ${isDark ? 'text-gray-400 hover:text-white' : 'text-gray-500 hover:text-gray-800'}`}>
          Limpar filtros
        </button>
      )}
    </div>
  );
};

// ─────────────────────────────────────────────────────────────
// Agrupamento por evento (Geração de Cupons) — mesmo espírito do acordeão de
// "Eventos e saldo por área": cabeçalho com nome/data/contagem, clicável
// para recolher, várias seções podem ficar abertas ao mesmo tempo.
// ─────────────────────────────────────────────────────────────
interface GrupoEvento {
  evento_id: number;
  evento_nome: string;
  evento_data?: string | null;
  itens: CortesiaSolicitacaoResponse[];
}

const agruparPorEvento = (lista: CortesiaSolicitacaoResponse[]): GrupoEvento[] => {
  const ordem: number[] = [];
  const grupos = new Map<number, GrupoEvento>();
  for (const sol of lista) {
    if (!grupos.has(sol.evento_id)) {
      grupos.set(sol.evento_id, { evento_id: sol.evento_id, evento_nome: sol.evento_nome || `Evento ${sol.evento_id}`, evento_data: sol.evento_data, itens: [] });
      ordem.push(sol.evento_id);
    }
    grupos.get(sol.evento_id)!.itens.push(sol);
  }
  return ordem.map(id => grupos.get(id)!);
};

interface GrupoEventoSectionProps {
  grupo: GrupoEvento;
  isDark: boolean;
  colapsado: boolean;
  onToggle: () => void;
  children: React.ReactNode;
}

const GrupoEventoSection: React.FC<GrupoEventoSectionProps> = ({ grupo, isDark, colapsado, onToggle, children }) => (
  <div className={`rounded-xl border overflow-hidden ${isDark ? 'border-gray-700' : 'border-gray-200'}`}>
    <button
      type="button"
      onClick={onToggle}
      className={`w-full flex items-center justify-between gap-3 px-3 py-2 text-left transition-colors ${isDark ? 'hover:bg-gray-700/30 bg-gray-800/40' : 'hover:bg-gray-50 bg-gray-50/80'}`}
    >
      <div className="flex items-center gap-2 min-w-0">
        {colapsado ? <ChevronDown className="w-3.5 h-3.5 shrink-0" /> : <ChevronUp className="w-3.5 h-3.5 shrink-0" />}
        <span className={`text-xs font-bold truncate ${isDark ? 'text-white' : 'text-gray-900'}`}>{grupo.evento_nome}</span>
        {grupo.evento_data && <span className={`text-[11px] shrink-0 ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>{fmtData(grupo.evento_data)}</span>}
      </div>
      <span className={`shrink-0 text-[10px] font-semibold px-1.5 py-0.5 rounded-full ${isDark ? 'bg-gray-700 text-gray-300' : 'bg-white text-gray-500 border border-gray-200'}`}>
        {grupo.itens.length}
      </span>
    </button>
    {!colapsado && <div className="p-2 space-y-2">{children}</div>}
  </div>
);

const SolicitacaoCortesias: React.FC = () => {
  const { isDark } = useTheme();
  const { canView, canCreate, canEdit, canDelete } = usePermissions();

  const podeVisualizar = canView('cortesia_solicitacao');
  const podeCriar = canCreate('cortesia_solicitacao');
  const podeGerarCupom = canEdit('cortesia_solicitacao');
  const podeCancelar = canDelete('cortesia_solicitacao');

  const [aba, setAba] = useState<Aba>('solicitacoes');
  const [visualizacao, setVisualizacao] = useState<Visualizacao>(() => {
    try {
      return localStorage.getItem(VISUALIZACAO_STORAGE_KEY) === 'kanban' ? 'kanban' : 'tabela';
    } catch {
      return 'tabela';
    }
  });

  useEffect(() => {
    if (!podeGerarCupom && aba === 'geracao') setAba('solicitacoes');
  }, [podeGerarCupom, aba]);

  useEffect(() => {
    try { localStorage.setItem(VISUALIZACAO_STORAGE_KEY, visualizacao); } catch { /* noop */ }
  }, [visualizacao]);

  const [eventos, setEventos] = useState<CortesiaEventoSaldoResponse[]>([]);
  const [loadingEventos, setLoadingEventos] = useState(true);
  const [errorEventos, setErrorEventos] = useState<string | null>(null);
  const [eventoExpandido, setEventoExpandido] = useState<number | null>(null);

  const [solicitacoes, setSolicitacoes] = useState<CortesiaSolicitacaoResponse[]>([]);
  const [loadingSolic, setLoadingSolic] = useState(true);
  const [errorSolic, setErrorSolic] = useState<string | null>(null);

  const [filaGeracao, setFilaGeracao] = useState<CortesiaSolicitacaoResponse[]>([]);
  const [loadingFila, setLoadingFila] = useState(true);
  const [errorFila, setErrorFila] = useState<string | null>(null);
  const [exportando, setExportando] = useState(false);
  // Filtro por evento dos "Gerados": vazio = janela padrão (últimos
  // FILA_GERADOS_JANELA_DIAS dias); com evento selecionado, o backend troca
  // para o histórico completo daquele evento. Nunca afeta os "Pendentes".
  const [filaEventoId, setFilaEventoId] = useState<number | ''>('');
  const [eventosFila, setEventosFila] = useState<CortesiaEventoFilaOpcao[]>([]);

  // Filtro da aba Acompanhamento (busca + evento + área + tipo + status,
  // tudo em memória sobre a lista já carregada).
  const [filtroAcomp, setFiltroAcomp] = useState<FiltroSolicitacoes>(FILTRO_VAZIO);
  // Filtro da aba Geração de Cupons: busca + área em memória; o campo Evento
  // reaproveita filaEventoId, que já troca a janela de "Gerados" no backend.
  const [filtroGeracaoBusca, setFiltroGeracaoBusca] = useState('');
  const [filtroGeracaoArea, setFiltroGeracaoArea] = useState<number | ''>('');
  // Filtro da aba Solicitações ("Eventos e saldo por área"): busca pelo nome
  // do evento + área, tudo em memória sobre a lista já carregada.
  const [filtroEventosBusca, setFiltroEventosBusca] = useState('');
  const [filtroEventosArea, setFiltroEventosArea] = useState<number | ''>('');
  // Chaves "secao-eventoId" recolhidas nos agrupamentos por evento de
  // Pendentes/Gerados — Set vazio = tudo expandido (padrão).
  const [gruposColapsados, setGruposColapsados] = useState<Set<string>>(new Set());
  const toggleGrupo = (chave: string) => {
    setGruposColapsados(prev => {
      const next = new Set(prev);
      if (next.has(chave)) next.delete(chave); else next.add(chave);
      return next;
    });
  };
  const expandirTodos = (secao: 'pendentes' | 'gerados', grupos: GrupoEvento[]) => {
    setGruposColapsados(prev => {
      const next = new Set(prev);
      grupos.forEach(g => next.delete(`${secao}-${g.evento_id}`));
      return next;
    });
  };
  const recolherTodos = (secao: 'pendentes' | 'gerados', grupos: GrupoEvento[]) => {
    setGruposColapsados(prev => {
      const next = new Set(prev);
      grupos.forEach(g => next.add(`${secao}-${g.evento_id}`));
      return next;
    });
  };

  const [form, setForm] = useState<FormState | null>(null);
  const [tipo, setTipo] = useState<'cupom' | 'planilha'>('cupom');
  const [quantidade, setQuantidade] = useState<string>('');
  const [observacao, setObservacao] = useState('');
  const [arquivo, setArquivo] = useState<File | null>(null);
  const [salvando, setSalvando] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const [gerarAlvo, setGerarAlvo] = useState<CortesiaSolicitacaoResponse | null>(null);
  const [gerarCodigosTexto, setGerarCodigosTexto] = useState('');
  const [gerandoSalvando, setGerandoSalvando] = useState(false);
  const [gerarError, setGerarError] = useState<string | null>(null);

  const [cancelandoId, setCancelandoId] = useState<number | null>(null);
  const [togglingCodigoId, setTogglingCodigoId] = useState<number | null>(null);

  const carregarEventos = async () => {
    setLoadingEventos(true);
    setErrorEventos(null);
    try {
      const data = await cortesiaSolicitacaoService.listEventosSaldo();
      setEventos(data);
    } catch (e) {
      setErrorEventos(extractError(e));
    } finally {
      setLoadingEventos(false);
    }
  };

  const carregarSolicitacoes = async () => {
    setLoadingSolic(true);
    setErrorSolic(null);
    try {
      const data = await cortesiaSolicitacaoService.list();
      setSolicitacoes(data);
    } catch (e) {
      setErrorSolic(extractError(e));
    } finally {
      setLoadingSolic(false);
    }
  };

  const carregarFila = async () => {
    setLoadingFila(true);
    setErrorFila(null);
    try {
      const data = await cortesiaSolicitacaoService.filaGeracao(
        filaEventoId ? { evento_id: filaEventoId } : undefined
      );
      setFilaGeracao(data);
    } catch (e) {
      setErrorFila(extractError(e));
    } finally {
      setLoadingFila(false);
    }
  };

  // Opções do filtro por evento — carregado à parte da fila em si (não
  // precisa recarregar quando o filtro muda, só quando um novo cupom é
  // gerado) e falha em silêncio: sem as opções, o filtro só fica vazio.
  const carregarEventosFila = async () => {
    try {
      const data = await cortesiaSolicitacaoService.eventosFilaGeracao();
      setEventosFila(data);
    } catch (e) {
      console.error('Erro ao carregar eventos da fila de geração:', e);
    }
  };

  useEffect(() => {
    if (!podeVisualizar) return;
    carregarEventos();
    carregarSolicitacoes();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [podeVisualizar]);

  useEffect(() => {
    if (!podeGerarCupom) {
      setLoadingFila(false);
      return;
    }
    carregarEventosFila();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [podeGerarCupom]);

  useEffect(() => {
    if (!podeGerarCupom) return;
    carregarFila();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [podeGerarCupom, filaEventoId]);

  const abrirForm = (f: FormState) => {
    setForm(f);
    setTipo('cupom');
    setQuantidade('');
    setObservacao('');
    setArquivo(null);
    setFormError(null);
  };

  const fecharForm = () => {
    setForm(null);
    setSalvando(false);
    setFormError(null);
  };

  const submitForm = async () => {
    if (!form) return;
    const qtd = parseInt(quantidade, 10);
    if (!qtd || qtd <= 0) {
      setFormError('Informe uma quantidade maior que zero.');
      return;
    }
    if (qtd > form.saldo) {
      setFormError(`Quantidade maior que o saldo disponível (${form.saldo}).`);
      return;
    }
    if (tipo === 'planilha' && !arquivo) {
      setFormError('Selecione o arquivo enviado pelo cliente.');
      return;
    }
    setSalvando(true);
    setFormError(null);
    try {
      if (tipo === 'cupom') {
        await cortesiaSolicitacaoService.criarCupom({
          evento_id: form.evento_id,
          area_projecao_id: form.area_projecao_id,
          quantidade: qtd,
          observacao: observacao.trim() || undefined,
        });
      } else {
        await cortesiaSolicitacaoService.criarPlanilha({
          evento_id: form.evento_id,
          area_projecao_id: form.area_projecao_id,
          quantidade: qtd,
          observacao: observacao.trim() || undefined,
          arquivo: arquivo as File,
        });
      }
      fecharForm();
      await Promise.all([carregarEventos(), carregarSolicitacoes()]);
    } catch (e) {
      setFormError(extractError(e));
      setSalvando(false);
    }
  };

  const abrirGerar = (sol: CortesiaSolicitacaoResponse) => {
    setGerarAlvo(sol);
    setGerarCodigosTexto('');
    setGerarError(null);
  };

  const parseCodigosColados = (texto: string): string[] =>
    texto.split('\n').map((c) => c.trim()).filter((c) => c.length > 0);

  const submitGerar = async () => {
    if (!gerarAlvo) return;
    const codigos = parseCodigosColados(gerarCodigosTexto);
    if (codigos.length === 0) {
      setGerarError('Cole ao menos um código de cupom gerado no Magento.');
      return;
    }
    setGerandoSalvando(true);
    setGerarError(null);
    try {
      await cortesiaSolicitacaoService.gerarCupom(gerarAlvo.id, codigos);
      setGerarAlvo(null);
      setGerarCodigosTexto('');
      await Promise.all([carregarSolicitacoes(), carregarFila()]);
    } catch (e) {
      setGerarError(extractError(e));
    } finally {
      setGerandoSalvando(false);
    }
  };

  const cancelar = async (sol: CortesiaSolicitacaoResponse) => {
    if (!window.confirm('Cancelar esta solicitação? O saldo da área será liberado.')) return;
    setCancelandoId(sol.id);
    try {
      await cortesiaSolicitacaoService.cancelar(sol.id);
      const tarefas = [carregarEventos(), carregarSolicitacoes()];
      if (podeGerarCupom) tarefas.push(carregarFila());
      await Promise.all(tarefas);
    } catch (e) {
      window.alert(extractError(e));
    } finally {
      setCancelandoId(null);
    }
  };

  const baixar = async (sol: CortesiaSolicitacaoResponse) => {
    try {
      await cortesiaSolicitacaoService.baixarArquivo(sol.id, sol.nome_arquivo || 'planilha');
    } catch (e) {
      window.alert(extractError(e));
    }
  };

  const toggleUsado = useCallback(async (sol: CortesiaSolicitacaoResponse, item: CupomCodigoItem) => {
    setTogglingCodigoId(item.id);
    try {
      const updated = await cortesiaSolicitacaoService.toggleCodigoUsado(sol.id, item.id);
      // Patch the item in both local lists without a full reload
      const patch = (list: CortesiaSolicitacaoResponse[]) =>
        list.map(s =>
          s.id !== sol.id
            ? s
            : {
                ...s,
                codigos_detalhes: (s.codigos_detalhes || []).map(c =>
                  c.id === item.id ? updated : c
                ),
              }
        );
      setSolicitacoes(prev => patch(prev));
      setFilaGeracao(prev => patch(prev));
    } catch (e) {
      window.alert(extractError(e));
    } finally {
      setTogglingCodigoId(null);
    }
  }, []);

  const exportarCupons = async () => {
    setExportando(true);
    try {
      // Exporta sem janela de data (ação explícita); respeita o mesmo
      // filtro de evento selecionado na fila, se houver.
      await cortesiaSolicitacaoService.exportarCupons(filaEventoId ? { evento_id: filaEventoId } : undefined);
    } catch (e) {
      window.alert(extractError(e));
    } finally {
      setExportando(false);
    }
  };

  const cardCls = `rounded-2xl overflow-hidden ${isDark ? 'bg-gray-800/50 backdrop-blur-xl border border-gray-700/50' : 'bg-white/70 backdrop-blur-xl border border-gray-200'}`;
  const inputCls = `w-full px-3 py-2 rounded-xl border text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500 ${isDark ? 'bg-gray-900/50 border-gray-600 text-white placeholder-gray-500' : 'bg-white border-gray-300 text-gray-900 placeholder-gray-400'}`;

  const abaBtnCls = (ativo: boolean) => `inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors ${
    ativo
      ? (isDark ? 'bg-emerald-500/20 text-emerald-400' : 'bg-emerald-100 text-emerald-700')
      : (isDark ? 'text-gray-400 hover:text-gray-200' : 'text-gray-500 hover:text-gray-700')
  }`;

  const viewBtnCls = (ativo: boolean) => `inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-xs font-semibold transition-colors ${
    ativo
      ? (isDark ? 'bg-gray-700 text-white' : 'bg-white text-gray-900 shadow-sm')
      : (isDark ? 'text-gray-400 hover:text-gray-200' : 'text-gray-500 hover:text-gray-700')
  }`;

  const pendentesFila = useMemo(() => filaGeracao.filter(s => s.status === 'solicitado'), [filaGeracao]);
  const geradosFila = useMemo(() => filaGeracao.filter(s => s.status === 'gerado'), [filaGeracao]);

  // Solicitações (Eventos e saldo por área): busca por nome do evento +
  // área, filtrando tanto quais eventos aparecem quanto quais linhas de
  // área aparecem dentro de cada evento expandido.
  const areaOpcoesEventos = useMemo(() => {
    const map = new Map<number, string>();
    for (const ev of eventos) for (const a of ev.areas) if (!map.has(a.area_projecao_id)) map.set(a.area_projecao_id, a.area_projecao_nome || `Área ${a.area_projecao_id}`);
    return Array.from(map, ([id, nome]) => ({ id, nome })).sort((a, b) => a.nome.localeCompare(b.nome, 'pt-BR'));
  }, [eventos]);
  const eventosFiltrados = useMemo(() => {
    const busca = filtroEventosBusca.trim().toLowerCase();
    return eventos
      .filter(ev => !busca || (ev.evento_nome || '').toLowerCase().includes(busca))
      .map(ev => filtroEventosArea ? { ...ev, areas: ev.areas.filter(a => a.area_projecao_id === filtroEventosArea) } : ev)
      .filter(ev => !filtroEventosArea || ev.areas.length > 0);
  }, [eventos, filtroEventosBusca, filtroEventosArea]);
  const limparFiltroEventos = () => { setFiltroEventosBusca(''); setFiltroEventosArea(''); };

  // Acompanhamento: opções do filtro vêm da própria lista carregada e o
  // resultado filtrado alimenta tanto a Tabela quanto o Kanban.
  const areaOpcoesAcomp = useMemo(() => opcoesArea(solicitacoes), [solicitacoes]);
  const eventoOpcoesAcomp = useMemo(() => opcoesEvento(solicitacoes), [solicitacoes]);
  const solicitacoesFiltradas = useMemo(() => aplicarFiltro(solicitacoes, filtroAcomp), [solicitacoes, filtroAcomp]);

  // Geração de Cupons: mesma busca+área nas duas seções; evento filtra só
  // Pendentes (Gerados já muda de janela via filaEventoId no backend).
  const areaOpcoesGeracao = useMemo(() => opcoesArea([...pendentesFila, ...geradosFila]), [pendentesFila, geradosFila]);
  const eventoOpcoesGeracao = useMemo(() => opcoesEvento([...pendentesFila, ...geradosFila]), [pendentesFila, geradosFila]);
  const filtroGeracaoAtivo = { busca: filtroGeracaoBusca, areaId: filtroGeracaoArea, eventoId: filaEventoId };
  const pendentesFiltrados = useMemo(
    () => aplicarFiltro(pendentesFila, filtroGeracaoAtivo),
    [pendentesFila, filtroGeracaoBusca, filtroGeracaoArea, filaEventoId]
  );
  const geradosFiltrados = useMemo(
    () => aplicarFiltro(geradosFila, filtroGeracaoAtivo, { ignorarEvento: true }),
    [geradosFila, filtroGeracaoBusca, filtroGeracaoArea]
  );
  const gruposPendentes = useMemo(() => agruparPorEvento(pendentesFiltrados), [pendentesFiltrados]);
  const gruposGerados = useMemo(() => agruparPorEvento(geradosFiltrados), [geradosFiltrados]);
  const limparFiltroGeracao = () => { setFiltroGeracaoBusca(''); setFiltroGeracaoArea(''); setFilaEventoId(''); };

  if (!podeVisualizar) {
    return (
      <div className="p-6">
        <div className={`${cardCls} p-6 flex items-center gap-3`}>
          <AlertTriangle className="w-5 h-5 text-amber-500 shrink-0" />
          <p className={isDark ? 'text-gray-300' : 'text-gray-700'}>Você não tem permissão para acessar esta tela.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="p-4 md:p-6 space-y-5">
      <div className="flex items-center gap-3">
        <div className="p-2 rounded-xl bg-gradient-to-br from-emerald-500 to-teal-500 shadow-lg shadow-emerald-500/30">
          <Gift className="w-6 h-6 text-white" />
        </div>
        <div>
          <h1 className={`text-3xl font-black tracking-tight ${isDark ? 'text-white' : 'text-gray-900'}`}>
            <span className="bg-gradient-to-r from-emerald-400 via-teal-500 to-cyan-500 bg-clip-text text-transparent">Cortesias</span>
          </h1>
          <p className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>
            Registre pedidos de cupom ou planilha do cliente, dentro do saldo projetado da sua área.
          </p>
        </div>
      </div>

      {/* Abas: quem solicita x quem gera os cupons */}
      <div className={`inline-flex items-center gap-1 p-1 rounded-xl ${isDark ? 'bg-gray-800/50 border border-gray-700/50' : 'bg-gray-100 border border-gray-200'}`}>
        <button type="button" onClick={() => setAba('solicitacoes')} className={abaBtnCls(aba === 'solicitacoes')}>
          <ClipboardList className="w-3.5 h-3.5" /> Solicitações
        </button>
        <button type="button" onClick={() => setAba('acompanhamento')} className={abaBtnCls(aba === 'acompanhamento')}>
          <ClipboardCheck className="w-3.5 h-3.5" /> Acompanhamento
        </button>
        {podeGerarCupom && (
          <button type="button" onClick={() => setAba('geracao')} className={abaBtnCls(aba === 'geracao')}>
            <Ticket className="w-3.5 h-3.5" /> Geração de Cupons
            {pendentesFila.length > 0 && (
              <span className={`ml-0.5 px-1.5 rounded-full text-[10px] font-bold ${isDark ? 'bg-amber-500/30 text-amber-300' : 'bg-amber-200 text-amber-800'}`}>
                {pendentesFila.length}
              </span>
            )}
          </button>
        )}
      </div>

      {aba === 'solicitacoes' && (
        <>
          {/* Eventos com saldo por área */}
          <div className={cardCls}>
            <div className={`flex items-center justify-between p-4 border-b ${isDark ? 'border-gray-700/50' : 'border-gray-200'}`}>
              <h2 className={`text-sm font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>Eventos e saldo por área</h2>
              <button
                onClick={carregarEventos}
                className={`p-2 rounded-lg transition-colors ${isDark ? 'hover:bg-gray-700 text-gray-400' : 'hover:bg-gray-100 text-gray-500'}`}
                title="Atualizar"
              >
                <RefreshCw className={`w-4 h-4 ${loadingEventos ? 'animate-spin' : ''}`} />
              </button>
            </div>
            <div className="p-4">
              {errorEventos && (
                <div className={`flex items-center gap-2 p-3 mb-3 rounded-xl text-sm ${isDark ? 'bg-red-500/10 text-red-400' : 'bg-red-50 text-red-600'}`}>
                  <AlertTriangle className="w-4 h-4 shrink-0" /> {errorEventos}
                </div>
              )}
              {!loadingEventos && eventos.length > 0 && (
                <FiltroBar
                  isDark={isDark}
                  busca={filtroEventosBusca}
                  onBusca={setFiltroEventosBusca}
                  buscaPlaceholder="Buscar evento por nome..."
                  areaId={filtroEventosArea}
                  onArea={setFiltroEventosArea}
                  areaOpcoes={areaOpcoesEventos}
                  onLimpar={limparFiltroEventos}
                  resultCount={eventosFiltrados.length}
                  resultLabel="evento(s)"
                />
              )}
              {loadingEventos ? (
                <p className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Carregando...</p>
              ) : eventos.length === 0 ? (
                <p className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                  Nenhum evento futuro com projeção cadastrada para as suas áreas.
                </p>
              ) : eventosFiltrados.length === 0 ? (
                <p className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                  Nenhum evento encontrado para estes filtros.
                </p>
              ) : (
                <div className="space-y-2">
                  {eventosFiltrados.map(ev => {
                    const expandido = eventoExpandido === ev.evento_id;
                    return (
                      <div key={ev.evento_id} className={`rounded-xl border overflow-hidden ${isDark ? 'border-gray-700' : 'border-gray-200'}`}>
                        <button
                          type="button"
                          onClick={() => setEventoExpandido(expandido ? null : ev.evento_id)}
                          className={`w-full flex items-center justify-between gap-3 px-4 py-3 text-left transition-colors ${isDark ? 'hover:bg-gray-700/30' : 'hover:bg-gray-50'}`}
                        >
                          <div>
                            <p className={`text-sm font-semibold ${isDark ? 'text-white' : 'text-gray-900'}`}>{ev.evento_nome}</p>
                            <p className={`text-xs ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>{fmtData(ev.evento_data)}</p>
                          </div>
                          {expandido ? <ChevronUp className="w-4 h-4 shrink-0" /> : <ChevronDown className="w-4 h-4 shrink-0" />}
                        </button>
                        {expandido && (
                          <div className={`border-t ${isDark ? 'border-gray-700' : 'border-gray-200'}`}>
                            <table className="w-full text-sm">
                              <thead>
                                <tr className={isDark ? 'text-gray-400' : 'text-gray-500'}>
                                  <th className="text-left font-medium px-4 py-2">Área</th>
                                  <th className="text-right font-medium px-4 py-2">Projetado</th>
                                  <th className="text-right font-medium px-4 py-2">Solicitado</th>
                                  <th className="text-right font-medium px-4 py-2">Saldo</th>
                                  {podeCriar && <th className="px-4 py-2" />}
                                </tr>
                              </thead>
                              <tbody>
                                {ev.areas.map(area => (
                                  <tr key={area.area_projecao_id} className={`border-t ${isDark ? 'border-gray-700/50' : 'border-gray-100'}`}>
                                    <td className={`px-4 py-2 ${isDark ? 'text-gray-200' : 'text-gray-800'}`}>{area.area_projecao_nome}</td>
                                    <td className={`px-4 py-2 text-right ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>{area.projetado}</td>
                                    <td className={`px-4 py-2 text-right ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>{area.solicitado}</td>
                                    <td className={`px-4 py-2 text-right font-semibold ${area.saldo > 0 ? (isDark ? 'text-emerald-400' : 'text-emerald-600') : (isDark ? 'text-gray-500' : 'text-gray-400')}`}>
                                      {area.saldo}
                                    </td>
                                    {podeCriar && (
                                      <td className="px-4 py-2 text-right">
                                        <button
                                          type="button"
                                          disabled={area.saldo <= 0}
                                          onClick={() => abrirForm({
                                            evento_id: ev.evento_id,
                                            evento_nome: ev.evento_nome,
                                            evento_sku: ev.evento_sku,
                                            area_projecao_id: area.area_projecao_id,
                                            area_projecao_nome: area.area_projecao_nome,
                                            area_sigla: area.area_sigla,
                                            saldo: area.saldo,
                                          })}
                                          className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-semibold transition-colors ${
                                            area.saldo <= 0
                                              ? (isDark ? 'bg-gray-700 text-gray-500 cursor-not-allowed' : 'bg-gray-100 text-gray-400 cursor-not-allowed')
                                              : (isDark ? 'bg-emerald-500/20 text-emerald-400 hover:bg-emerald-500/30' : 'bg-emerald-100 text-emerald-700 hover:bg-emerald-200')
                                          }`}
                                        >
                                          <Plus className="w-3.5 h-3.5" /> Solicitar
                                        </button>
                                      </td>
                                    )}
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        </>
      )}

      {aba === 'acompanhamento' && (
        <div className={cardCls}>
          <div className={`flex items-center justify-between p-4 border-b ${isDark ? 'border-gray-700/50' : 'border-gray-200'}`}>
            <h2 className={`text-sm font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>Solicitações</h2>
            <div className="flex items-center gap-1.5">
              <div className={`flex items-center gap-0.5 p-0.5 rounded-lg ${isDark ? 'bg-gray-900/50' : 'bg-gray-100'}`}>
                <button type="button" onClick={() => setVisualizacao('tabela')} className={viewBtnCls(visualizacao === 'tabela')}>
                  <ListIcon className="w-3.5 h-3.5" /> Tabela
                </button>
                <button type="button" onClick={() => setVisualizacao('kanban')} className={viewBtnCls(visualizacao === 'kanban')}>
                  <LayoutGrid className="w-3.5 h-3.5" /> Kanban
                </button>
              </div>
              <button
                onClick={carregarSolicitacoes}
                className={`p-2 rounded-lg transition-colors ${isDark ? 'hover:bg-gray-700 text-gray-400' : 'hover:bg-gray-100 text-gray-500'}`}
                title="Atualizar"
              >
                <RefreshCw className={`w-4 h-4 ${loadingSolic ? 'animate-spin' : ''}`} />
              </button>
            </div>
          </div>
          <div className="p-4">
            {errorSolic && (
              <div className={`flex items-center gap-2 p-3 mb-3 rounded-xl text-sm ${isDark ? 'bg-red-500/10 text-red-400' : 'bg-red-50 text-red-600'}`}>
                <AlertTriangle className="w-4 h-4 shrink-0" /> {errorSolic}
              </div>
            )}
            {!loadingSolic && solicitacoes.length > 0 && (
              <FiltroBar
                isDark={isDark}
                busca={filtroAcomp.busca}
                onBusca={v => setFiltroAcomp(f => ({ ...f, busca: v }))}
                areaId={filtroAcomp.areaId}
                onArea={v => setFiltroAcomp(f => ({ ...f, areaId: v }))}
                areaOpcoes={areaOpcoesAcomp}
                eventoId={filtroAcomp.eventoId}
                onEvento={v => setFiltroAcomp(f => ({ ...f, eventoId: v }))}
                eventoOpcoes={eventoOpcoesAcomp}
                tipo={filtroAcomp.tipo}
                onTipo={v => setFiltroAcomp(f => ({ ...f, tipo: v }))}
                status={filtroAcomp.status}
                onStatus={v => setFiltroAcomp(f => ({ ...f, status: v }))}
                onLimpar={() => setFiltroAcomp(FILTRO_VAZIO)}
                resultCount={solicitacoesFiltradas.length}
                resultLabel="solicitação(ões)"
              />
            )}
            {loadingSolic ? (
              <p className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Carregando...</p>
            ) : solicitacoes.length === 0 ? (
              <p className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Nenhuma solicitação registrada ainda.</p>
            ) : solicitacoesFiltradas.length === 0 ? (
              <p className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Nenhuma solicitação encontrada para estes filtros.</p>
            ) : visualizacao === 'tabela' ? (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className={isDark ? 'text-gray-400' : 'text-gray-500'}>
                        <th className="text-left font-medium px-3 py-2">Evento</th>
                        <th className="text-left font-medium px-3 py-2">Área</th>
                        <th className="text-left font-medium px-3 py-2">Tipo</th>
                        <th className="text-right font-medium px-3 py-2">Qtd</th>
                        <th className="text-left font-medium px-3 py-2">Status</th>
                        <th className="text-left font-medium px-3 py-2">Solicitante</th>
                        <th className="text-left font-medium px-3 py-2">Data</th>
                        <th className="px-3 py-2" />
                      </tr>
                    </thead>
                    <tbody>
                      {solicitacoesFiltradas.map(sol => (
                        <tr key={sol.id} className={`border-t ${isDark ? 'border-gray-700/50' : 'border-gray-100'}`}>
                          <td className={`px-3 py-2 ${isDark ? 'text-gray-200' : 'text-gray-800'}`}>{sol.evento_nome}</td>
                          <td className={`px-3 py-2 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>{sol.area_projecao_nome}</td>
                          <td className="px-3 py-2">
                            <span className={`inline-flex items-center gap-1 text-xs font-semibold ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
                              {sol.tipo === 'cupom' ? <Ticket className="w-3.5 h-3.5" /> : <FileSpreadsheet className="w-3.5 h-3.5" />}
                              {sol.tipo === 'cupom' ? 'Cupom' : 'Planilha'}
                            </span>
                          </td>
                          <td className={`px-3 py-2 text-right font-semibold ${isDark ? 'text-gray-200' : 'text-gray-800'}`}>{sol.quantidade}</td>
                          <td className="px-3 py-2">
                            {sol.tipo === 'cupom' ? (
                              sol.status === 'gerado' ? (
                                <span className={`inline-flex items-center gap-1 text-xs font-semibold ${isDark ? 'text-emerald-400' : 'text-emerald-600'}`}>
                                  <CheckCircle2 className="w-3.5 h-3.5" /> Gerado
                                </span>
                              ) : (
                                <span className={`inline-flex items-center gap-1 text-xs font-semibold ${isDark ? 'text-amber-400' : 'text-amber-600'}`}>
                                  <Clock className="w-3.5 h-3.5" /> Aguardando geração
                                </span>
                              )
                            ) : (
                              <span className={`inline-flex items-center gap-1 text-xs font-semibold ${isDark ? 'text-blue-400' : 'text-blue-600'}`}>
                                <CheckCircle2 className="w-3.5 h-3.5" /> Recebida
                              </span>
                            )}
                            {sol.tipo === 'cupom' && sol.status === 'gerado' && (
                              <CodigosList
                                codigos={codigosDe(sol)}
                                isDark={isDark}
                                variant="compact"
                                detalhes={sol.codigos_detalhes}
                              />
                            )}
                          </td>
                          <td className={`px-3 py-2 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>{sol.solicitado_por_nome || '—'}</td>
                          <td className={`px-3 py-2 text-xs ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>{fmtDataHora(sol.created_at)}</td>
                          <td className="px-3 py-2">
                            <div className="flex items-center justify-end gap-1.5">
                              {sol.tipo === 'planilha' && sol.nome_arquivo && (
                                <button
                                  type="button"
                                  onClick={() => baixar(sol)}
                                  title="Baixar arquivo"
                                  className={`p-1.5 rounded-lg transition-colors ${isDark ? 'hover:bg-gray-700 text-gray-400' : 'hover:bg-gray-100 text-gray-500'}`}
                                >
                                  <Download className="w-4 h-4" />
                                </button>
                              )}
                              {sol.tipo === 'cupom' && sol.status === 'solicitado' && podeGerarCupom && (
                                <button
                                  type="button"
                                  onClick={() => abrirGerar(sol)}
                                  className={`px-2.5 py-1 rounded-lg text-xs font-semibold transition-colors ${isDark ? 'bg-blue-500/20 text-blue-400 hover:bg-blue-500/30' : 'bg-blue-100 text-blue-700 hover:bg-blue-200'}`}
                                >
                                  Marcar gerado
                                </button>
                              )}
                              {podeCancelar && (
                                <button
                                  type="button"
                                  disabled={cancelandoId === sol.id}
                                  onClick={() => cancelar(sol)}
                                  title="Cancelar solicitação"
                                  className={`p-1.5 rounded-lg transition-colors ${isDark ? 'hover:bg-red-500/20 text-red-400' : 'hover:bg-red-50 text-red-500'} disabled:opacity-50`}
                                >
                                  <Trash2 className="w-4 h-4" />
                                </button>
                              )}
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <KanbanBoard
                  solicitacoes={solicitacoesFiltradas}
                  isDark={isDark}
                  podeGerarCupom={podeGerarCupom}
                  podeCancelar={podeCancelar}
                  cancelandoId={cancelandoId}
                  onGerar={abrirGerar}
                  onCancelar={cancelar}
                  onBaixar={baixar}
                  onToggleUsado={podeGerarCupom ? toggleUsado : undefined}
                  togglingCodigoId={togglingCodigoId}
                />
              )}
            </div>
          </div>
      )}
      {aba === 'geracao' && podeGerarCupom && (
        <div className={cardCls}>
          <div className={`flex items-center justify-between p-4 border-b ${isDark ? 'border-gray-700/50' : 'border-gray-200'}`}>
            <div>
              <h2 className={`text-sm font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>Fila de Geração de Cupons</h2>
              <p className={`text-xs mt-0.5 ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                Pendentes de todas as áreas, sempre completos. Gerados dos últimos {FILA_GERADOS_JANELA_DIAS} dias por padrão — selecione um evento no filtro para ver o histórico completo.
              </p>
            </div>
            <div className="flex items-center gap-1.5">
              <button
                type="button"
                onClick={exportarCupons}
                disabled={exportando}
                className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors disabled:opacity-50 ${isDark ? 'bg-emerald-500/20 text-emerald-400 hover:bg-emerald-500/30' : 'bg-emerald-100 text-emerald-700 hover:bg-emerald-200'}`}
              >
                <FileDown className="w-3.5 h-3.5" /> {exportando ? 'Exportando...' : 'Exportar CSV'}
              </button>
              <button
                onClick={() => { carregarFila(); carregarEventosFila(); }}
                className={`p-2 rounded-lg transition-colors ${isDark ? 'hover:bg-gray-700 text-gray-400' : 'hover:bg-gray-100 text-gray-500'}`}
                title="Atualizar"
              >
                <RefreshCw className={`w-4 h-4 ${loadingFila ? 'animate-spin' : ''}`} />
              </button>
            </div>
          </div>
          <div className="p-4 space-y-5">
            {errorFila && (
              <div className={`flex items-center gap-2 p-3 rounded-xl text-sm ${isDark ? 'bg-red-500/10 text-red-400' : 'bg-red-50 text-red-600'}`}>
                <AlertTriangle className="w-4 h-4 shrink-0" /> {errorFila}
              </div>
            )}
            {!loadingFila && (pendentesFila.length > 0 || geradosFila.length > 0) && (
              <FiltroBar
                isDark={isDark}
                busca={filtroGeracaoBusca}
                onBusca={setFiltroGeracaoBusca}
                areaId={filtroGeracaoArea}
                onArea={setFiltroGeracaoArea}
                areaOpcoes={areaOpcoesGeracao}
                eventoId={filaEventoId}
                onEvento={setFilaEventoId}
                eventoOpcoes={eventoOpcoesGeracao}
                eventoPlaceholder={`Últimos ${FILA_GERADOS_JANELA_DIAS} dias (gerados)`}
                onLimpar={limparFiltroGeracao}
                resultCount={pendentesFiltrados.length + geradosFiltrados.length}
                resultLabel="na fila"
              />
            )}
            {loadingFila ? (
              <p className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Carregando...</p>
            ) : (
              <>
                <section>
                  <div className="flex items-center justify-between gap-3 flex-wrap mb-2">
                    <h3 className={`text-xs font-bold uppercase tracking-wide ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                      Pendentes <span className={isDark ? 'text-gray-600' : 'text-gray-400'}>({pendentesFiltrados.length})</span>
                    </h3>
                    {gruposPendentes.length > 1 && (
                      <div className="flex items-center gap-3">
                        <button type="button" onClick={() => expandirTodos('pendentes', gruposPendentes)} className={`inline-flex items-center gap-1 text-[11px] font-semibold ${isDark ? 'text-gray-400 hover:text-white' : 'text-gray-500 hover:text-gray-800'}`}>
                          <ChevronsDown className="w-3 h-3" /> Expandir todos
                        </button>
                        <button type="button" onClick={() => recolherTodos('pendentes', gruposPendentes)} className={`inline-flex items-center gap-1 text-[11px] font-semibold ${isDark ? 'text-gray-400 hover:text-white' : 'text-gray-500 hover:text-gray-800'}`}>
                          <ChevronsUp className="w-3 h-3" /> Recolher todos
                        </button>
                      </div>
                    )}
                  </div>
                  {pendentesFila.length === 0 ? (
                    <p className={`text-sm ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>Nenhuma solicitação aguardando geração.</p>
                  ) : pendentesFiltrados.length === 0 ? (
                    <p className={`text-sm ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>Nenhum pendente encontrado para estes filtros.</p>
                  ) : (
                    <div className="space-y-2">
                      {gruposPendentes.map(grupo => (
                        <GrupoEventoSection
                          key={grupo.evento_id}
                          grupo={grupo}
                          isDark={isDark}
                          colapsado={gruposColapsados.has(`pendentes-${grupo.evento_id}`)}
                          onToggle={() => toggleGrupo(`pendentes-${grupo.evento_id}`)}
                        >
                          {grupo.itens.map(sol => (
                            <div key={sol.id} className={`flex items-center justify-between gap-3 rounded-xl border p-3 ${isDark ? 'border-gray-700 bg-gray-800/30' : 'border-gray-200 bg-white'}`}>
                              <div className="min-w-0">
                                <p className={`text-sm font-semibold truncate ${isDark ? 'text-white' : 'text-gray-900'}`}>{sol.area_projecao_nome}</p>
                                <p className={`text-xs ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                                  {sol.quantidade} cortesias · solicitado por {sol.solicitado_por_nome || '—'} em {fmtDataHora(sol.created_at)}
                                </p>
                                {sol.observacao && <p className={`text-xs italic mt-0.5 ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>{sol.observacao}</p>}
                              </div>
                              <button
                                type="button"
                                onClick={() => abrirGerar(sol)}
                                className={`shrink-0 px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors ${isDark ? 'bg-blue-500/20 text-blue-400 hover:bg-blue-500/30' : 'bg-blue-100 text-blue-700 hover:bg-blue-200'}`}
                              >
                                Marcar gerado
                              </button>
                            </div>
                          ))}
                        </GrupoEventoSection>
                      ))}
                    </div>
                  )}
                </section>
                <section>
                  <div className="flex items-center justify-between gap-3 flex-wrap mb-1">
                    <h3 className={`text-xs font-bold uppercase tracking-wide ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                      Gerados <span className={isDark ? 'text-gray-600' : 'text-gray-400'}>({geradosFiltrados.length})</span>
                    </h3>
                    {gruposGerados.length > 1 && (
                      <div className="flex items-center gap-3">
                        <button type="button" onClick={() => expandirTodos('gerados', gruposGerados)} className={`inline-flex items-center gap-1 text-[11px] font-semibold ${isDark ? 'text-gray-400 hover:text-white' : 'text-gray-500 hover:text-gray-800'}`}>
                          <ChevronsDown className="w-3 h-3" /> Expandir todos
                        </button>
                        <button type="button" onClick={() => recolherTodos('gerados', gruposGerados)} className={`inline-flex items-center gap-1 text-[11px] font-semibold ${isDark ? 'text-gray-400 hover:text-white' : 'text-gray-500 hover:text-gray-800'}`}>
                          <ChevronsUp className="w-3 h-3" /> Recolher todos
                        </button>
                      </div>
                    )}
                  </div>
                  <p className={`text-xs mb-2 ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>
                    {filaEventoId
                      ? 'Histórico completo de cupons gerados para o evento selecionado.'
                      : `Mostrando apenas os gerados nos últimos ${FILA_GERADOS_JANELA_DIAS} dias. Selecione um evento no filtro para buscar códigos mais antigos.`}
                  </p>
                  {geradosFila.length === 0 ? (
                    <p className={`text-sm ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>
                      {filaEventoId ? 'Nenhum cupom gerado para este evento.' : `Nenhum cupom gerado nos últimos ${FILA_GERADOS_JANELA_DIAS} dias.`}
                    </p>
                  ) : geradosFiltrados.length === 0 ? (
                    <p className={`text-sm ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>Nenhum gerado encontrado para estes filtros.</p>
                  ) : (
                    <div className="space-y-3">
                      {gruposGerados.map(grupo => (
                        <GrupoEventoSection
                          key={grupo.evento_id}
                          grupo={grupo}
                          isDark={isDark}
                          colapsado={gruposColapsados.has(`gerados-${grupo.evento_id}`)}
                          onToggle={() => toggleGrupo(`gerados-${grupo.evento_id}`)}
                        >
                          {grupo.itens.map(sol => (
                            <div key={sol.id} className={`rounded-xl border p-3 space-y-2 ${isDark ? 'border-gray-700 bg-gray-800/30' : 'border-gray-200 bg-white'}`}>
                              <div className="flex items-center justify-between gap-3">
                                <p className={`text-sm font-semibold truncate ${isDark ? 'text-white' : 'text-gray-900'}`}>{sol.area_projecao_nome}</p>
                                <span className={`shrink-0 text-xs ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>{fmtDataHora(sol.gerado_em)} · {sol.gerado_por_nome || '—'}</span>
                              </div>
                              <CodigosList
                                codigos={codigosDe(sol)}
                                isDark={isDark}
                                variant="full"
                                detalhes={sol.codigos_detalhes}
                                onToggleUsado={item => toggleUsado(sol, item)}
                                togglingId={togglingCodigoId}
                              />
                            </div>
                          ))}
                        </GrupoEventoSection>
                      ))}
                    </div>
                  )}
                </section>
              </>
            )}
          </div>
        </div>
      )}

      {/* Modal: nova solicitação */}
      {form && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
          <div className={`w-full max-w-md rounded-2xl shadow-2xl border ${isDark ? 'bg-gray-800 border-gray-700' : 'bg-white border-gray-200'}`}>
            <div className={`flex items-center justify-between p-4 border-b ${isDark ? 'border-gray-700' : 'border-gray-200'}`}>
              <h3 className={`text-sm font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>Nova solicitação de cortesia</h3>
              <button onClick={fecharForm} className={isDark ? 'text-gray-400 hover:text-white' : 'text-gray-400 hover:text-gray-700'}>
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="p-4 space-y-3">
              <div className={`text-xs p-2.5 rounded-lg ${isDark ? 'bg-gray-900/50 text-gray-300' : 'bg-gray-50 text-gray-700'}`}>
                <p><strong>{form.evento_nome}</strong> — {form.area_projecao_nome}</p>
                <p className="mt-0.5">Saldo disponível: <strong>{form.saldo}</strong></p>
              </div>

              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => setTipo('cupom')}
                  className={`flex-1 flex items-center justify-center gap-1.5 px-3 py-2 rounded-xl text-sm font-semibold border transition-colors ${
                    tipo === 'cupom'
                      ? (isDark ? 'bg-emerald-500/20 border-emerald-500 text-emerald-400' : 'bg-emerald-50 border-emerald-400 text-emerald-700')
                      : (isDark ? 'border-gray-600 text-gray-300' : 'border-gray-300 text-gray-600')
                  }`}
                >
                  <Ticket className="w-4 h-4" /> Gerar cupom
                </button>
                <button
                  type="button"
                  onClick={() => setTipo('planilha')}
                  className={`flex-1 flex items-center justify-center gap-1.5 px-3 py-2 rounded-xl text-sm font-semibold border transition-colors ${
                    tipo === 'planilha'
                      ? (isDark ? 'bg-emerald-500/20 border-emerald-500 text-emerald-400' : 'bg-emerald-50 border-emerald-400 text-emerald-700')
                      : (isDark ? 'border-gray-600 text-gray-300' : 'border-gray-300 text-gray-600')
                  }`}
                >
                  <FileSpreadsheet className="w-4 h-4" /> Planilha do cliente
                </button>
              </div>

              {tipo === 'cupom' && (!form.area_sigla || !form.evento_sku) && (
                <div className={`flex items-start gap-2 p-3 rounded-xl text-xs ${isDark ? 'bg-amber-500/10 border border-amber-500/30 text-amber-300' : 'bg-amber-50 border border-amber-200 text-amber-800'}`}>
                  <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
                  <div className="space-y-1">
                    {!form.area_sigla && (
                      <p>
                        A área <strong>{form.area_projecao_nome}</strong> ainda não tem uma sigla configurada — necessária para gerar os códigos de cupom.
                        {' '}Configure a sigla em <strong>Configurações › Áreas e Usuários</strong> antes de enviar esta solicitação.
                      </p>
                    )}
                    {!form.evento_sku && (
                      <p>
                        O evento <strong>{form.evento_nome}</strong> não tem um SKU cadastrado — necessário para gerar os códigos de cupom.
                        {' '}Cadastre o SKU do evento antes de enviar esta solicitação.
                      </p>
                    )}
                  </div>
                </div>
              )}

              <div>
                <label className={`text-xs font-medium ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Quantidade</label>
                <input
                  type="number"
                  min={1}
                  max={form.saldo}
                  value={quantidade}
                  onChange={e => setQuantidade(e.target.value)}
                  className={inputCls}
                  placeholder="Ex.: 10"
                />
              </div>

              {tipo === 'planilha' && (
                <div>
                  <label className={`text-xs font-medium ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Arquivo (.xlsx, .xls ou .csv)</label>
                  {arquivo ? (
                    <div className={`mt-1 flex items-center justify-between gap-2 p-2.5 rounded-lg border ${isDark ? 'border-gray-600 bg-gray-900/50' : 'border-gray-300 bg-gray-50'}`}>
                      <div className="flex items-center gap-2 min-w-0">
                        <FileSpreadsheet className={`w-4 h-4 shrink-0 ${isDark ? 'text-emerald-400' : 'text-emerald-600'}`} />
                        <div className="min-w-0">
                          <p className={`text-xs font-semibold truncate ${isDark ? 'text-gray-200' : 'text-gray-800'}`}>{arquivo.name}</p>
                          <p className={`text-[11px] ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>{fmtTamanhoArquivo(arquivo.size)} · anexado, pronto para enviar</p>
                        </div>
                      </div>
                      <button
                        type="button"
                        onClick={() => setArquivo(null)}
                        title="Remover arquivo"
                        className={`p-1 rounded-lg shrink-0 transition-colors ${isDark ? 'hover:bg-gray-700 text-gray-400' : 'hover:bg-gray-200 text-gray-500'}`}
                      >
                        <X className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  ) : (
                    <input
                      type="file"
                      accept=".xlsx,.xls,.csv"
                      onChange={e => setArquivo(e.target.files?.[0] || null)}
                      className={`w-full text-sm ${isDark ? 'text-gray-300' : 'text-gray-700'}`}
                    />
                  )}
                  <p className={`text-[11px] mt-1 ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>
                    Depois de enviada, a planilha fica disponível para baixar na aba Acompanhamento.
                  </p>
                </div>
              )}

              <div>
                <label className={`text-xs font-medium ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Observação (opcional)</label>
                <textarea
                  value={observacao}
                  onChange={e => setObservacao(e.target.value)}
                  rows={2}
                  className={inputCls}
                  placeholder="Contexto adicional para quem for gerar/receber"
                />
              </div>

              {formError && (
                <div className={`flex items-center gap-2 p-2.5 rounded-lg text-sm ${isDark ? 'bg-red-500/10 text-red-400' : 'bg-red-50 text-red-600'}`}>
                  <AlertTriangle className="w-4 h-4 shrink-0" /> {formError}
                </div>
              )}
            </div>
            <div className={`flex items-center justify-end gap-2 p-4 border-t ${isDark ? 'border-gray-700' : 'border-gray-200'}`}>
              <button
                onClick={fecharForm}
                className={`px-4 py-2 rounded-xl text-sm font-semibold ${isDark ? 'text-gray-300 hover:bg-gray-700' : 'text-gray-600 hover:bg-gray-100'}`}
              >
                Cancelar
              </button>
              <button
                onClick={submitForm}
                disabled={salvando}
                className="px-4 py-2 rounded-xl text-sm font-semibold bg-emerald-600 text-white hover:bg-emerald-700 disabled:opacity-50"
              >
                {salvando ? 'Enviando...' : 'Enviar solicitação'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Modal: colar cupom gerado no Magento */}
      {gerarAlvo && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
          <div className={`w-full max-w-lg rounded-2xl shadow-2xl border max-h-[90vh] flex flex-col ${isDark ? 'bg-gray-800 border-gray-700' : 'bg-white border-gray-200'}`}>
            <div className={`flex items-center justify-between p-4 border-b ${isDark ? 'border-gray-700' : 'border-gray-200'}`}>
              <h3 className={`text-sm font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>Colar código de cupom</h3>
              <button onClick={() => setGerarAlvo(null)} className={isDark ? 'text-gray-400 hover:text-white' : 'text-gray-400 hover:text-gray-700'}>
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="p-4 space-y-3 overflow-y-auto">
              <p className={`text-sm font-semibold ${isDark ? 'text-gray-200' : 'text-gray-800'}`}>
                {gerarAlvo.evento_nome} — {gerarAlvo.area_projecao_nome}
              </p>
              <p className={`text-xs ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                Gere {gerarAlvo.quantidade} código(s) no Magento e cole abaixo, um por linha ({parseCodigosColados(gerarCodigosTexto).length} de {gerarAlvo.quantidade} colado(s)).
              </p>
              <textarea
                value={gerarCodigosTexto}
                onChange={(e) => setGerarCodigosTexto(e.target.value)}
                rows={Math.min(10, Math.max(4, gerarAlvo.quantidade))}
                placeholder={'Cole aqui o(s) código(s) gerados no Magento\num por linha'}
                className={`w-full rounded-xl border px-3 py-2 text-sm font-mono resize-y ${isDark ? 'bg-gray-900 border-gray-700 text-gray-100 placeholder-gray-500' : 'bg-white border-gray-300 text-gray-900 placeholder-gray-400'}`}
              />
              {gerarError && (
                <div className={`flex items-center gap-2 p-2.5 rounded-lg text-sm ${isDark ? 'bg-red-500/10 text-red-400' : 'bg-red-50 text-red-600'}`}>
                  <AlertTriangle className="w-4 h-4 shrink-0" /> {gerarError}
                </div>
              )}
            </div>
            <div className={`flex items-center justify-end gap-2 p-4 border-t ${isDark ? 'border-gray-700' : 'border-gray-200'}`}>
              <button
                onClick={() => setGerarAlvo(null)}
                className={`px-4 py-2 rounded-xl text-sm font-semibold ${isDark ? 'text-gray-300 hover:bg-gray-700' : 'text-gray-600 hover:bg-gray-100'}`}
              >
                Cancelar
              </button>
              <button
                onClick={submitGerar}
                disabled={gerandoSalvando}
                className="px-4 py-2 rounded-xl text-sm font-semibold bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50"
              >
                {gerandoSalvando ? 'Salvando...' : 'Salvar código(s)'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default SolicitacaoCortesias;
