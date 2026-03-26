import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft, BookOpen, Target, MessageSquare, CheckSquare, BarChart2, Clock, ChevronDown, ChevronRight } from 'lucide-react';
import { marketingService } from '../../services/api';

interface PlaybookEntry {
  letter: string;
  name: string;
  stage: string;
  stageName: string;
  iscLabel: string;
  objective: string;
  narrative: string;
  actions: string[];
  kpis: string[];
  cutoffs: string[];
  stageInfo: { key: string; label: string; sublabel: string; description: string };
  iscInfo: { key: string; label: string; threshold: string; color: string };
}

interface PlaybookData {
  stages: { key: string; label: string; sublabel: string; description: string }[];
  iscStates: { key: string; label: string; threshold: string; color: string }[];
  entries: PlaybookEntry[];
}

const STAGE_COLORS: Record<string, { bg: string; border: string; text: string; badge: string }> = {
  analitico: {
    bg: 'bg-indigo-50 dark:bg-indigo-950/30',
    border: 'border-indigo-200 dark:border-indigo-800',
    text: 'text-indigo-700 dark:text-indigo-300',
    badge: 'bg-indigo-100 dark:bg-indigo-900/60 text-indigo-800 dark:text-indigo-200',
  },
  estrategico: {
    bg: 'bg-amber-50 dark:bg-amber-950/30',
    border: 'border-amber-200 dark:border-amber-800',
    text: 'text-amber-700 dark:text-amber-300',
    badge: 'bg-amber-100 dark:bg-amber-900/60 text-amber-800 dark:text-amber-200',
  },
  operacional: {
    bg: 'bg-rose-50 dark:bg-rose-950/30',
    border: 'border-rose-200 dark:border-rose-800',
    text: 'text-rose-700 dark:text-rose-300',
    badge: 'bg-rose-100 dark:bg-rose-900/60 text-rose-800 dark:text-rose-200',
  },
};

const ISC_COLORS: Record<string, { dot: string; text: string; badge: string }> = {
  forte: { dot: 'bg-green-500', text: 'text-green-700 dark:text-green-300', badge: 'bg-green-100 dark:bg-green-900/40 text-green-800 dark:text-green-200' },
  estavel: { dot: 'bg-yellow-400', text: 'text-yellow-700 dark:text-yellow-300', badge: 'bg-yellow-100 dark:bg-yellow-900/40 text-yellow-800 dark:text-yellow-200' },
  fraco: { dot: 'bg-red-500', text: 'text-red-700 dark:text-red-300', badge: 'bg-red-100 dark:bg-red-900/40 text-red-800 dark:text-red-200' },
};

function PlaybookCard({ entry, expanded, onToggle }: { entry: PlaybookEntry; expanded: boolean; onToggle: () => void }) {
  const stageColor = STAGE_COLORS[entry.stage] || STAGE_COLORS.analitico;
  const iscColor = ISC_COLORS[entry.iscInfo.key] || ISC_COLORS.estavel;

  return (
    <div className={`rounded-2xl border-2 ${stageColor.border} ${stageColor.bg} overflow-hidden transition-all duration-200`}>
      <button
        className="w-full text-left p-5 flex items-start gap-4"
        onClick={onToggle}
      >
        <div className={`shrink-0 w-12 h-12 rounded-xl flex items-center justify-center text-xl font-black ${stageColor.badge}`}>
          {entry.letter}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2 mb-1">
            <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${stageColor.badge}`}>
              {entry.stageInfo.label} · {entry.stageInfo.sublabel}
            </span>
            <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${iscColor.badge} flex items-center gap-1`}>
              <span className={`w-1.5 h-1.5 rounded-full inline-block ${iscColor.dot}`} />
              {entry.iscLabel}
            </span>
          </div>
          <p className={`font-bold text-base ${stageColor.text}`}>{entry.name}</p>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-0.5 line-clamp-1">{entry.objective}</p>
        </div>
        <div className="shrink-0 text-gray-400 mt-1">
          {expanded ? <ChevronDown className="w-5 h-5" /> : <ChevronRight className="w-5 h-5" />}
        </div>
      </button>

      {expanded && (
        <div className="px-5 pb-5 space-y-4 border-t border-dashed border-current/20">
          <div className="pt-4">
            <div className="flex items-center gap-2 mb-2">
              <MessageSquare className={`w-4 h-4 ${stageColor.text}`} />
              <span className={`text-xs font-bold uppercase tracking-wider ${stageColor.text}`}>Narrativa</span>
            </div>
            <p className="text-sm italic text-gray-700 dark:text-gray-300 bg-white/60 dark:bg-black/20 rounded-lg px-4 py-2 border-l-4 border-current/30">
              {entry.narrative}
            </p>
          </div>

          <div>
            <div className="flex items-center gap-2 mb-2">
              <Target className={`w-4 h-4 ${stageColor.text}`} />
              <span className={`text-xs font-bold uppercase tracking-wider ${stageColor.text}`}>Objetivo</span>
            </div>
            <p className="text-sm text-gray-700 dark:text-gray-300">{entry.objective}</p>
          </div>

          <div>
            <div className="flex items-center gap-2 mb-2">
              <CheckSquare className={`w-4 h-4 ${stageColor.text}`} />
              <span className={`text-xs font-bold uppercase tracking-wider ${stageColor.text}`}>Ações Operacionais</span>
            </div>
            <ul className="space-y-1.5">
              {entry.actions.map((action, i) => (
                <li key={i} className="flex items-start gap-2 text-sm text-gray-700 dark:text-gray-300">
                  <span className={`mt-1 w-1.5 h-1.5 rounded-full shrink-0 ${iscColor.dot}`} />
                  {action}
                </li>
              ))}
            </ul>
          </div>

          <div className="flex flex-col sm:flex-row gap-4">
            <div className="flex-1">
              <div className="flex items-center gap-2 mb-2">
                <BarChart2 className={`w-4 h-4 ${stageColor.text}`} />
                <span className={`text-xs font-bold uppercase tracking-wider ${stageColor.text}`}>KPIs (48–72h)</span>
              </div>
              <ul className="space-y-1">
                {entry.kpis.map((kpi, i) => (
                  <li key={i} className="text-sm text-gray-700 dark:text-gray-300 bg-white/50 dark:bg-black/20 rounded-lg px-3 py-1.5 font-medium">
                    {kpi}
                  </li>
                ))}
              </ul>
            </div>
            <div className="flex-1">
              <div className="flex items-center gap-2 mb-2">
                <Clock className={`w-4 h-4 ${stageColor.text}`} />
                <span className={`text-xs font-bold uppercase tracking-wider ${stageColor.text}`}>Pontos de Corte</span>
              </div>
              <div className="flex flex-wrap gap-2">
                {entry.cutoffs.map((cutoff, i) => (
                  <span key={i} className={`text-sm font-bold px-3 py-1 rounded-lg ${stageColor.badge}`}>
                    {cutoff}
                  </span>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default function PlaybookPage() {
  const navigate = useNavigate();
  const [playbook, setPlaybook] = useState<PlaybookData | null>(null);
  const [loading, setLoading] = useState(true);
  const [expandedCards, setExpandedCards] = useState<Set<string>>(new Set());
  const [filterStage, setFilterStage] = useState<string>('all');
  const [filterIsc, setFilterIsc] = useState<string>('all');

  useEffect(() => {
    marketingService.getPlaybook()
      .then(data => { setPlaybook(data); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  const toggleCard = (letter: string) => {
    setExpandedCards(prev => {
      const next = new Set(prev);
      if (next.has(letter)) next.delete(letter); else next.add(letter);
      return next;
    });
  };

  const expandAll = () => {
    if (!playbook) return;
    setExpandedCards(new Set(playbook.entries.map(e => e.letter)));
  };
  const collapseAll = () => setExpandedCards(new Set());

  const filteredEntries = playbook?.entries.filter(e =>
    (filterStage === 'all' || e.stage === filterStage) &&
    (filterIsc === 'all' || e.iscInfo.key === filterIsc)
  ) ?? [];

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-950">
      <div className="max-w-4xl mx-auto px-4 py-6">
        <div className="flex items-center gap-3 mb-6">
          <button
            onClick={() => navigate(-1)}
            className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-600 dark:text-gray-400 transition-colors"
          >
            <ArrowLeft className="w-5 h-5" />
          </button>
          <div className="flex items-center gap-2">
            <BookOpen className="w-6 h-6 text-indigo-600 dark:text-indigo-400" />
            <div>
              <h1 className="text-xl font-bold text-gray-900 dark:text-white">Playbook Comercial</h1>
              <p className="text-xs text-gray-500 dark:text-gray-400">9 estratégias por estágio e estado ISC</p>
            </div>
          </div>
        </div>

        {!loading && playbook && (
          <>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-6">
              {playbook.stages.map(stage => {
                const color = STAGE_COLORS[stage.key];
                return (
                  <div key={stage.key} className={`rounded-xl p-4 border ${color.border} ${color.bg}`}>
                    <p className={`text-xs font-bold uppercase tracking-wider mb-1 ${color.text}`}>{stage.sublabel}</p>
                    <p className={`text-lg font-black ${color.text}`}>{stage.label}</p>
                    <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">{stage.description}</p>
                  </div>
                );
              })}
            </div>

            <div className="flex flex-wrap items-center gap-2 mb-4">
              <div className="flex items-center gap-1">
                <span className="text-xs text-gray-500 dark:text-gray-400">Estágio:</span>
                {['all', 'analitico', 'estrategico', 'operacional'].map(s => (
                  <button
                    key={s}
                    onClick={() => setFilterStage(s)}
                    className={`text-xs px-2.5 py-1 rounded-full font-medium transition-colors ${
                      filterStage === s
                        ? 'bg-gray-900 dark:bg-white text-white dark:text-gray-900'
                        : 'bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700'
                    }`}
                  >
                    {s === 'all' ? 'Todos' : s === 'analitico' ? 'Analítico' : s === 'estrategico' ? 'Estratégico' : 'Operacional'}
                  </button>
                ))}
              </div>
              <div className="flex items-center gap-1">
                <span className="text-xs text-gray-500 dark:text-gray-400">ISC:</span>
                {['all', 'forte', 'estavel', 'fraco'].map(s => (
                  <button
                    key={s}
                    onClick={() => setFilterIsc(s)}
                    className={`text-xs px-2.5 py-1 rounded-full font-medium transition-colors ${
                      filterIsc === s
                        ? 'bg-gray-900 dark:bg-white text-white dark:text-gray-900'
                        : 'bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700'
                    }`}
                  >
                    {s === 'all' ? 'Todos' : s === 'forte' ? '🟢 Forte' : s === 'estavel' ? '🟡 Estável' : '🔴 Fraco'}
                  </button>
                ))}
              </div>
              <div className="ml-auto flex gap-2">
                <button onClick={expandAll} className="text-xs text-indigo-600 dark:text-indigo-400 hover:underline">Expandir tudo</button>
                <span className="text-gray-300 dark:text-gray-600">|</span>
                <button onClick={collapseAll} className="text-xs text-gray-500 dark:text-gray-400 hover:underline">Recolher tudo</button>
              </div>
            </div>

            <div className="space-y-3">
              {filteredEntries.map(entry => (
                <PlaybookCard
                  key={entry.letter}
                  entry={entry}
                  expanded={expandedCards.has(entry.letter)}
                  onToggle={() => toggleCard(entry.letter)}
                />
              ))}
              {filteredEntries.length === 0 && (
                <div className="text-center py-12 text-gray-400 dark:text-gray-600">
                  <BookOpen className="w-10 h-10 mx-auto mb-2 opacity-40" />
                  <p>Nenhuma entrada encontrada para os filtros selecionados.</p>
                </div>
              )}
            </div>
          </>
        )}

        {loading && (
          <div className="flex items-center justify-center py-20">
            <div className="animate-spin rounded-full w-10 h-10 border-4 border-indigo-500 border-t-transparent" />
          </div>
        )}
      </div>
    </div>
  );
}
