import React, { useState, useEffect } from 'react';
import {
  Brain,
  TrendingUp,
  AlertTriangle,
  DollarSign,
  Tag,
  Zap,
  RefreshCw,
  Eye,
  EyeOff,
  Trash2,
  ChevronDown,
  ChevronUp,
  Sparkles,
  Loader2,
} from 'lucide-react';
import { noriInsightsService, NoriInsight } from '../../services/api';

const TIPO_CONFIG: Record<string, { label: string; color: string; bgColor: string; borderColor: string; icon: React.ElementType }> = {
  margem_oportunidade: {
    label: 'Oportunidade de Margem',
    color: 'text-emerald-700 dark:text-emerald-400',
    bgColor: 'bg-emerald-50 dark:bg-emerald-900/20',
    borderColor: 'border-emerald-400 dark:border-emerald-600',
    icon: DollarSign,
  },
  aceleracao_sem_reajuste: {
    label: 'Aceleração Sem Reajuste',
    color: 'text-blue-700 dark:text-blue-400',
    bgColor: 'bg-blue-50 dark:bg-blue-900/20',
    borderColor: 'border-blue-400 dark:border-blue-600',
    icon: Zap,
  },
  ticket_abaixo_orcado: {
    label: 'Ticket Abaixo do Orçado',
    color: 'text-amber-700 dark:text-amber-400',
    bgColor: 'bg-amber-50 dark:bg-amber-900/20',
    borderColor: 'border-amber-400 dark:border-amber-600',
    icon: Tag,
  },
  preco_defasado: {
    label: 'Preço Defasado',
    color: 'text-orange-700 dark:text-orange-400',
    bgColor: 'bg-orange-50 dark:bg-orange-900/20',
    borderColor: 'border-orange-400 dark:border-orange-600',
    icon: TrendingUp,
  },
  kit_custo_baixo: {
    label: 'Custo de Kit Baixo',
    color: 'text-purple-700 dark:text-purple-400',
    bgColor: 'bg-purple-50 dark:bg-purple-900/20',
    borderColor: 'border-purple-400 dark:border-purple-600',
    icon: Brain,
  },
  isc_alerta: {
    label: 'Alerta ISC Crítico',
    color: 'text-red-700 dark:text-red-400',
    bgColor: 'bg-red-50 dark:bg-red-900/20',
    borderColor: 'border-red-400 dark:border-red-600',
    icon: AlertTriangle,
  },
};

const DEFAULT_TIPO = {
  label: 'Insight',
  color: 'text-indigo-700 dark:text-indigo-400',
  bgColor: 'bg-indigo-50 dark:bg-indigo-900/20',
  borderColor: 'border-indigo-400 dark:border-indigo-600',
  icon: Sparkles,
};

interface InsightCardProps {
  insight: NoriInsight;
  onMarkVisto: (id: number) => void;
  onDescartar: (id: number) => void;
}

const InsightCard: React.FC<InsightCardProps> = ({ insight, onMarkVisto, onDescartar }) => {
  const [expanded, setExpanded] = useState(false);
  const config = TIPO_CONFIG[insight.tipo] || DEFAULT_TIPO;
  const TipoIcon = config.icon;

  const geradoEm = new Date(insight.gerado_em).toLocaleDateString('pt-BR', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });

  return (
    <div className={`rounded-xl border-l-4 ${config.borderColor} ${config.bgColor} p-4 transition-all duration-200`}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-3 flex-1 min-w-0">
          <div className={`mt-0.5 p-1.5 rounded-lg ${config.bgColor} flex-shrink-0`}>
            <TipoIcon className={`w-4 h-4 ${config.color}`} />
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap mb-1">
              <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${config.bgColor} ${config.color} border ${config.borderColor}`}>
                {config.label}
              </span>
              {insight.status === 'visto' && (
                <span className="text-xs text-gray-400 dark:text-gray-500 italic">Visto</span>
              )}
            </div>
            <p className="text-xs text-gray-500 dark:text-gray-400 mb-1 font-medium">
              📍 {insight.evento_nome}
            </p>
            <h4 className="font-semibold text-gray-900 dark:text-white text-sm leading-snug mb-2">
              {insight.titulo}
            </h4>

            {(insight.impacto_estimado_reais != null || insight.impacto_estimado_percentual != null) && (
              <div className="flex items-center gap-3 mb-2">
                {insight.impacto_estimado_reais != null && (
                  <div className="flex items-center gap-1">
                    <DollarSign className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400" />
                    <span className="text-sm font-bold text-emerald-700 dark:text-emerald-400">
                      +R$ {insight.impacto_estimado_reais.toLocaleString('pt-BR', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}
                    </span>
                  </div>
                )}
                {insight.impacto_estimado_percentual != null && (
                  <div className="flex items-center gap-1">
                    <TrendingUp className="w-3.5 h-3.5 text-blue-600 dark:text-blue-400" />
                    <span className="text-sm font-bold text-blue-700 dark:text-blue-400">
                      +{insight.impacto_estimado_percentual.toFixed(1)}% margem
                    </span>
                  </div>
                )}
              </div>
            )}

            {expanded && (
              <div className="mt-2 space-y-2">
                <p className="text-sm text-gray-700 dark:text-gray-300 leading-relaxed whitespace-pre-wrap">
                  {insight.conteudo}
                </p>
                {insight.acao_sugerida && (
                  <div className="mt-2 p-3 bg-white/60 dark:bg-gray-800/60 rounded-lg border border-gray-200 dark:border-gray-700">
                    <p className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-1">
                      Ação Sugerida
                    </p>
                    <p className="text-sm font-medium text-gray-800 dark:text-gray-200">
                      🎯 {insight.acao_sugerida}
                    </p>
                  </div>
                )}
                <p className="text-xs text-gray-400 dark:text-gray-500">
                  Gerado em {geradoEm}
                </p>
              </div>
            )}
          </div>
        </div>

        <div className="flex flex-col gap-1 flex-shrink-0">
          <button
            onClick={() => setExpanded(!expanded)}
            className="p-1.5 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors"
            title={expanded ? 'Recolher' : 'Ver detalhes'}
          >
            {expanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
          </button>
          {insight.status === 'novo' && (
            <button
              onClick={() => onMarkVisto(insight.id)}
              className="p-1.5 text-gray-400 hover:text-blue-500 transition-colors"
              title="Marcar como visto"
            >
              <Eye className="w-4 h-4" />
            </button>
          )}
          {insight.status === 'visto' && (
            <button
              onClick={() => onMarkVisto(insight.id)}
              className="p-1.5 text-blue-400 hover:text-gray-400 transition-colors"
              title="Marcar como novo"
            >
              <EyeOff className="w-4 h-4" />
            </button>
          )}
          <button
            onClick={() => onDescartar(insight.id)}
            className="p-1.5 text-gray-400 hover:text-red-500 transition-colors"
            title="Descartar insight"
          >
            <Trash2 className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  );
};

interface NoriInsightsPanelProps {
  visible: boolean;
}

const NoriInsightsPanel: React.FC<NoriInsightsPanelProps> = ({ visible }) => {
  const [insights, setInsights] = useState<NoriInsight[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);
  const [showVisto, setShowVisto] = useState(false);
  const [lastGenerated, setLastGenerated] = useState<string | null>(null);
  const [generateResult, setGenerateResult] = useState<string | null>(null);

  useEffect(() => {
    if (visible) {
      loadInsights();
    }
  }, [visible]);

  const loadInsights = async () => {
    setIsLoading(true);
    try {
      const data = await noriInsightsService.list();
      setInsights(data);
    } catch (error) {
      console.error('Erro ao carregar insights:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const handleMarkVisto = async (id: number) => {
    const insight = insights.find(i => i.id === id);
    if (!insight) return;
    const newStatus: NoriInsight['status'] = insight.status === 'novo' ? 'visto' : 'novo';
    try {
      await noriInsightsService.updateStatus(id, newStatus);
      setInsights(prev => prev.map(i => i.id === id ? { ...i, status: newStatus } : i));
    } catch (error) {
      console.error('Erro ao atualizar status:', error);
    }
  };

  const handleDescartar = async (id: number) => {
    try {
      await noriInsightsService.updateStatus(id, 'descartado');
      setInsights(prev => prev.filter(i => i.id !== id));
    } catch (error) {
      console.error('Erro ao descartar insight:', error);
    }
  };

  const handleGenerate = async () => {
    setIsGenerating(true);
    setGenerateResult(null);
    try {
      const result = await noriInsightsService.generate();
      const msg = `${result.insights_saved ?? 0} novos insights gerados (${result.events_analyzed ?? 0} eventos analisados)`;
      setGenerateResult(msg);
      setLastGenerated(new Date().toLocaleTimeString('pt-BR'));
      await loadInsights();
    } catch (error: any) {
      setGenerateResult('Erro ao gerar insights. Verifique os logs.');
      console.error('Erro ao gerar insights:', error);
    } finally {
      setIsGenerating(false);
    }
  };

  const novosInsights = insights.filter(i => i.status === 'novo');
  const vistoInsights = insights.filter(i => i.status === 'visto');
  const displayedInsights = showVisto ? insights : novosInsights;

  if (!visible) return null;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white flex items-center gap-2">
            <Brain className="w-5 h-5 text-indigo-500" />
            Insights Proativos
          </h3>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-0.5">
            Oportunidades detectadas automaticamente pela IA
          </p>
        </div>
        <div className="flex items-center gap-2">
          {vistoInsights.length > 0 && (
            <button
              onClick={() => setShowVisto(!showVisto)}
              className={`flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg border transition-colors ${
                showVisto
                  ? 'bg-indigo-100 dark:bg-indigo-900/30 text-indigo-700 dark:text-indigo-300 border-indigo-300 dark:border-indigo-700'
                  : 'bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-400 border-gray-300 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-700'
              }`}
            >
              {showVisto ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
              {showVisto ? 'Ocultar vistos' : `Ver vistos (${vistoInsights.length})`}
            </button>
          )}
          <button
            onClick={handleGenerate}
            disabled={isGenerating}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-gradient-to-r from-indigo-600 to-purple-600 text-white rounded-lg hover:from-indigo-700 hover:to-purple-700 disabled:opacity-60 transition-colors"
            title="Analisar eventos e gerar novos insights agora"
          >
            {isGenerating ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <RefreshCw className="w-3.5 h-3.5" />
            )}
            {isGenerating ? 'Analisando...' : 'Analisar Agora'}
          </button>
        </div>
      </div>

      {generateResult && (
        <div className="text-sm text-indigo-700 dark:text-indigo-400 bg-indigo-50 dark:bg-indigo-900/20 border border-indigo-200 dark:border-indigo-700 rounded-lg px-3 py-2">
          ✅ {generateResult}
          {lastGenerated && <span className="ml-2 text-xs text-gray-500">às {lastGenerated}</span>}
        </div>
      )}

      {isLoading ? (
        <div className="flex items-center justify-center py-12">
          <div className="text-center">
            <Loader2 className="w-8 h-8 animate-spin text-indigo-500 mx-auto mb-3" />
            <p className="text-sm text-gray-500 dark:text-gray-400">Carregando insights...</p>
          </div>
        </div>
      ) : displayedInsights.length === 0 ? (
        <div className="text-center py-12 space-y-3">
          <div className="w-16 h-16 bg-indigo-100 dark:bg-indigo-900/30 rounded-full flex items-center justify-center mx-auto">
            <Brain className="w-8 h-8 text-indigo-500" />
          </div>
          <div>
            <p className="font-medium text-gray-700 dark:text-gray-300">Nenhum insight disponível</p>
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
              Clique em "Analisar Agora" para que o Nori examine todos os eventos e identifique oportunidades de melhoria de margem.
            </p>
          </div>
        </div>
      ) : (
        <div className="space-y-3">
          {novosInsights.length > 0 && (
            <div className="flex items-center gap-2 mb-2">
              <span className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide">
                Novos ({novosInsights.length})
              </span>
              <div className="flex-1 h-px bg-gray-200 dark:bg-gray-700" />
            </div>
          )}
          {displayedInsights.filter(i => i.status === 'novo').map(insight => (
            <InsightCard
              key={insight.id}
              insight={insight}
              onMarkVisto={handleMarkVisto}
              onDescartar={handleDescartar}
            />
          ))}

          {showVisto && vistoInsights.length > 0 && (
            <>
              <div className="flex items-center gap-2 mt-4 mb-2">
                <span className="text-xs font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-wide">
                  Vistos ({vistoInsights.length})
                </span>
                <div className="flex-1 h-px bg-gray-200 dark:bg-gray-700" />
              </div>
              {vistoInsights.map(insight => (
                <InsightCard
                  key={insight.id}
                  insight={insight}
                  onMarkVisto={handleMarkVisto}
                  onDescartar={handleDescartar}
                />
              ))}
            </>
          )}
        </div>
      )}
    </div>
  );
};

export default NoriInsightsPanel;
