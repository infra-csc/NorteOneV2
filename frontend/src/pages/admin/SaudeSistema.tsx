import React, { useEffect, useState, useCallback } from 'react';
import { useTheme } from '../../context/ThemeContext';
import { adminService } from '../../services/api';
import {
  ShieldCheck, ShieldAlert, AlertTriangle, Info, RefreshCw, Settings,
  Save, Send, ChevronDown, ChevronUp, Filter, Clock, Activity,
  ChevronLeft, ChevronRight
} from 'lucide-react';

interface HealthEvent {
  id: number;
  event_type: string;
  severity: 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW' | 'INFO';
  message: string;
  detail: string | null;
  created_at: string;
}

interface HealthSummary {
  status: 'healthy' | 'warning' | 'critical' | 'info';
  critical_24h: number;
  high_24h: number;
  total_24h: number;
  last_event: HealthEvent | null;
}

interface AlertConfig {
  email_enabled: boolean;
  email_recipients: string | null;
  email_from: string | null;
  smtp_host: string | null;
  smtp_port: number | null;
  smtp_user: string | null;
  smtp_password: string | null;
  slack_enabled: boolean;
  slack_webhook_url: string | null;
  min_severity: string;
}

const SEVERITY_CONFIG = {
  CRITICAL: { label: 'Crítico', badge: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400', dot: 'bg-red-500' },
  HIGH: { label: 'Alto', badge: 'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-400', dot: 'bg-orange-500' },
  MEDIUM: { label: 'Médio', badge: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400', dot: 'bg-yellow-500' },
  LOW: { label: 'Baixo', badge: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400', dot: 'bg-blue-500' },
  INFO: { label: 'Info', badge: 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300', dot: 'bg-gray-500' },
};

const EVENT_TYPE_LABELS: Record<string, string> = {
  SSH_TUNNEL_DOWN: 'Túnel SSH caiu',
  SSH_TUNNEL_RECONNECTED: 'Túnel SSH reconectado',
  SSH_TUNNEL_RECONNECT_FAILED: 'Falha ao reconectar SSH',
  WARMUP_FAILED: 'Falha no refresh completo',
  WARMUP_STUCK: 'Refresh travado',
  DAILY_REFRESH_FAILED: 'Falha no refresh diário',
  DAILY_REFRESH_COMPLETED: 'Refresh diário concluído',
  ISC_REFRESH_FAILED: 'Falha no refresh ISC',
  SYNC_BATCH_FAILED: 'Falha na sincronização',
  STARTUP_RESYNC_FAILED: 'Falha no resync inicial',
  TEST: 'Teste de alerta',
};

function formatDatetime(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleString('pt-BR', { timeZone: 'America/Sao_Paulo', day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

function timeAgo(iso: string): string {
  const now = Date.now();
  const dt = new Date(iso).getTime();
  const diff = Math.floor((now - dt) / 1000);
  if (diff < 60) return `há ${diff}s`;
  if (diff < 3600) return `há ${Math.floor(diff / 60)}min`;
  if (diff < 86400) return `há ${Math.floor(diff / 3600)}h`;
  return `há ${Math.floor(diff / 86400)}d`;
}

const PAGE_SIZE = 50;

const SaudeSistema: React.FC = () => {
  const { isDark } = useTheme();
  const [summary, setSummary] = useState<HealthSummary | null>(null);
  const [events, setEvents] = useState<HealthEvent[]>([]);
  const [totalEvents, setTotalEvents] = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  const [currentPage, setCurrentPage] = useState(1);
  const [config, setConfig] = useState<AlertConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [configLoading, setConfigLoading] = useState(true);
  const [savingConfig, setSavingConfig] = useState(false);
  const [testingAlert, setTestingAlert] = useState(false);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);
  const [filterSeverity, setFilterSeverity] = useState<string>('');
  const [filterDateFrom, setFilterDateFrom] = useState<string>('');
  const [filterDateTo, setFilterDateTo] = useState<string>('');
  const [expandedEvents, setExpandedEvents] = useState<Set<number>>(new Set());
  const [showConfig, setShowConfig] = useState(false);
  const [formConfig, setFormConfig] = useState<AlertConfig>({
    email_enabled: false, email_recipients: '', email_from: '', smtp_host: '',
    smtp_port: 587, smtp_user: '', smtp_password: '', slack_enabled: false,
    slack_webhook_url: '', min_severity: 'HIGH',
  });

  const cardBase = isDark
    ? 'bg-gray-800/50 backdrop-blur-sm border border-gray-700/50'
    : 'bg-white/80 backdrop-blur-sm border border-gray-200 shadow-sm';
  const textPrimary = isDark ? 'text-white' : 'text-gray-900';
  const textSecondary = isDark ? 'text-gray-400' : 'text-gray-500';
  const inputClass = `w-full px-3 py-2 rounded-lg border text-sm outline-none transition-colors ${isDark ? 'bg-gray-700 border-gray-600 text-white placeholder-gray-400 focus:border-blue-500' : 'bg-white border-gray-300 text-gray-900 placeholder-gray-400 focus:border-blue-400'}`;
  const selectClass = `text-sm rounded-lg px-3 py-1.5 border outline-none ${isDark ? 'bg-gray-700 border-gray-600 text-white' : 'bg-white border-gray-300 text-gray-900'}`;

  const fetchEvents = useCallback(async (page: number) => {
    setLoading(true);
    try {
      const data = await adminService.getHealthEvents({
        severity: filterSeverity || undefined,
        date_from: filterDateFrom || undefined,
        date_to: filterDateTo || undefined,
        page,
        page_size: PAGE_SIZE,
      });
      setEvents(data.events || []);
      setTotalEvents(data.total ?? 0);
      setTotalPages(data.total_pages ?? 1);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, [filterSeverity, filterDateFrom, filterDateTo]);

  const fetchSummary = useCallback(async () => {
    try {
      const data = await adminService.getHealthSummary();
      setSummary(data);
    } catch (e) {
      console.error(e);
    }
  }, []);

  const fetchConfig = useCallback(async () => {
    try {
      const cfg = await adminService.getAlertConfig();
      setConfig(cfg);
      setFormConfig({
        email_enabled: cfg.email_enabled ?? false,
        email_recipients: cfg.email_recipients ?? '',
        email_from: cfg.email_from ?? '',
        smtp_host: cfg.smtp_host ?? '',
        smtp_port: cfg.smtp_port ?? 587,
        smtp_user: cfg.smtp_user ?? '',
        smtp_password: '',
        slack_enabled: cfg.slack_enabled ?? false,
        slack_webhook_url: '',
        min_severity: cfg.min_severity ?? 'HIGH',
      });
    } catch (e) {
      console.error(e);
    } finally {
      setConfigLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchSummary();
    fetchConfig();
    const interval = setInterval(fetchSummary, 30000);
    return () => clearInterval(interval);
  }, [fetchSummary, fetchConfig]);

  useEffect(() => {
    setCurrentPage(1);
    fetchEvents(1);
  }, [filterSeverity, filterDateFrom, filterDateTo]);

  const handlePageChange = (page: number) => {
    setCurrentPage(page);
    fetchEvents(page);
  };

  const handleApplyFilters = () => {
    setCurrentPage(1);
    fetchEvents(1);
  };

  const handleSaveConfig = async () => {
    setSavingConfig(true);
    setSaveMsg(null);
    try {
      await adminService.updateAlertConfig(formConfig);
      setSaveMsg('Configuração salva com sucesso');
      fetchConfig();
    } catch (e: any) {
      setSaveMsg('Erro ao salvar: ' + (e?.response?.data?.detail || e.message));
    } finally {
      setSavingConfig(false);
      setTimeout(() => setSaveMsg(null), 4000);
    }
  };

  const handleTestAlert = async () => {
    setTestingAlert(true);
    try {
      await adminService.testAlert();
      setSaveMsg('Alerta de teste enviado!');
      setTimeout(() => fetchSummary(), 1500);
    } catch (e: any) {
      setSaveMsg('Erro ao testar: ' + (e?.response?.data?.detail || e.message));
    } finally {
      setTestingAlert(false);
      setTimeout(() => setSaveMsg(null), 5000);
    }
  };

  const toggleExpand = (id: number) => {
    setExpandedEvents(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  const statusConfig = {
    healthy: { icon: ShieldCheck, color: 'text-emerald-400', bg: 'bg-emerald-500/10', border: 'border-emerald-500/30', label: 'Saudável', desc: 'Nenhum problema nas últimas 24h' },
    warning: { icon: AlertTriangle, color: 'text-amber-400', bg: 'bg-amber-500/10', border: 'border-amber-500/30', label: 'Alerta', desc: 'Há alertas de alta severidade nas últimas 24h' },
    critical: { icon: ShieldAlert, color: 'text-red-400', bg: 'bg-red-500/10', border: 'border-red-500/30', label: 'Crítico', desc: 'Há eventos críticos nas últimas 24h' },
    info: { icon: Info, color: 'text-blue-400', bg: 'bg-blue-500/10', border: 'border-blue-500/30', label: 'Info', desc: 'Eventos informativos nas últimas 24h' },
  };

  const stt = summary ? statusConfig[summary.status] : statusConfig.healthy;
  const SttIcon = stt.icon;

  return (
    <div className="p-4 md:p-6 space-y-6">
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div className="flex items-center gap-3">
          <div className={`p-2 rounded-lg ${stt.bg}`}>
            <Activity className={`w-6 h-6 ${stt.color}`} />
          </div>
          <div>
            <h1 className={`text-2xl font-bold ${textPrimary}`}>Saúde do Sistema</h1>
            <p className={`text-sm ${textSecondary}`}>Monitoramento de eventos e alertas de infraestrutura</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowConfig(v => !v)}
            className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-all border
              ${isDark ? 'border-gray-600 text-gray-300 hover:bg-gray-700' : 'border-gray-300 text-gray-600 hover:bg-gray-100'}`}
          >
            <Settings className="w-4 h-4" />
            Configurações
          </button>
          <button
            onClick={() => { fetchSummary(); fetchEvents(currentPage); }}
            disabled={loading}
            className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium bg-blue-600 hover:bg-blue-500 text-white disabled:opacity-50 transition-all"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            Atualizar
          </button>
        </div>
      </div>

      {summary && (
        <div className={`${cardBase} rounded-xl p-5 border-l-4 ${stt.border}`}>
          <div className="flex flex-col sm:flex-row items-start sm:items-center gap-4">
            <div className={`p-3 rounded-xl ${stt.bg} flex-shrink-0`}>
              <SttIcon className={`w-8 h-8 ${stt.color}`} />
            </div>
            <div className="flex-1">
              <span className={`text-xl font-bold ${stt.color}`}>{stt.label}</span>
              <p className={`text-sm ${textSecondary} mt-0.5`}>{stt.desc}</p>
              {summary.last_event && (
                <p className={`text-xs ${textSecondary} mt-1`}>
                  Último evento: <span className={textPrimary}>{EVENT_TYPE_LABELS[summary.last_event.event_type] || summary.last_event.event_type}</span>
                  {' '}— {timeAgo(summary.last_event.created_at)}
                </p>
              )}
            </div>
            <div className="flex gap-4 text-center">
              <div>
                <p className="text-2xl font-bold text-red-400">{summary.critical_24h}</p>
                <p className={`text-xs ${textSecondary}`}>Críticos 24h</p>
              </div>
              <div>
                <p className="text-2xl font-bold text-orange-400">{summary.high_24h}</p>
                <p className={`text-xs ${textSecondary}`}>Altos 24h</p>
              </div>
              <div>
                <p className={`text-2xl font-bold ${textPrimary}`}>{summary.total_24h}</p>
                <p className={`text-xs ${textSecondary}`}>Total 24h</p>
              </div>
            </div>
          </div>
        </div>
      )}

      {showConfig && (
        <div className={`${cardBase} rounded-xl p-6 space-y-6`}>
          <div className="flex items-center justify-between flex-wrap gap-2">
            <h2 className={`text-lg font-semibold ${textPrimary}`}>Configurações de Alerta</h2>
            {saveMsg && (
              <span className={`text-sm px-3 py-1 rounded-lg ${saveMsg.includes('Erro') ? 'bg-red-500/10 text-red-400' : 'bg-emerald-500/10 text-emerald-400'}`}>
                {saveMsg}
              </span>
            )}
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="space-y-4">
              <div className="flex items-center gap-3">
                <button
                  onClick={() => setFormConfig(f => ({ ...f, email_enabled: !f.email_enabled }))}
                  className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${formConfig.email_enabled ? 'bg-blue-600' : isDark ? 'bg-gray-600' : 'bg-gray-300'}`}
                >
                  <span className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${formConfig.email_enabled ? 'translate-x-6' : 'translate-x-1'}`} />
                </button>
                <span className={`font-medium ${textPrimary}`}>Notificações por E-mail</span>
              </div>
              {formConfig.email_enabled && (
                <div className="space-y-3 pl-4 border-l-2 border-blue-500/30">
                  <div>
                    <label className={`block text-xs font-medium ${textSecondary} mb-1`}>Destinatários (separados por vírgula)</label>
                    <input className={inputClass} placeholder="admin@empresa.com, tech@empresa.com" value={formConfig.email_recipients || ''} onChange={e => setFormConfig(f => ({ ...f, email_recipients: e.target.value }))} />
                  </div>
                  <div>
                    <label className={`block text-xs font-medium ${textSecondary} mb-1`}>E-mail remetente</label>
                    <input className={inputClass} placeholder="alertas@empresa.com" value={formConfig.email_from || ''} onChange={e => setFormConfig(f => ({ ...f, email_from: e.target.value }))} />
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <div>
                      <label className={`block text-xs font-medium ${textSecondary} mb-1`}>Servidor SMTP</label>
                      <input className={inputClass} placeholder="smtp.gmail.com" value={formConfig.smtp_host || ''} onChange={e => setFormConfig(f => ({ ...f, smtp_host: e.target.value }))} />
                    </div>
                    <div>
                      <label className={`block text-xs font-medium ${textSecondary} mb-1`}>Porta</label>
                      <input className={inputClass} type="number" placeholder="587" value={formConfig.smtp_port || ''} onChange={e => setFormConfig(f => ({ ...f, smtp_port: Number(e.target.value) }))} />
                    </div>
                  </div>
                  <div>
                    <label className={`block text-xs font-medium ${textSecondary} mb-1`}>Usuário SMTP</label>
                    <input className={inputClass} placeholder="usuario@gmail.com" value={formConfig.smtp_user || ''} onChange={e => setFormConfig(f => ({ ...f, smtp_user: e.target.value }))} />
                  </div>
                  <div>
                    <label className={`block text-xs font-medium ${textSecondary} mb-1`}>Senha SMTP</label>
                    <input className={inputClass} type="password" placeholder="••••••••" value={formConfig.smtp_password || ''} onChange={e => setFormConfig(f => ({ ...f, smtp_password: e.target.value }))} />
                  </div>
                </div>
              )}
            </div>

            <div className="space-y-4">
              <div className="flex items-center gap-3">
                <button
                  onClick={() => setFormConfig(f => ({ ...f, slack_enabled: !f.slack_enabled }))}
                  className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${formConfig.slack_enabled ? 'bg-purple-600' : isDark ? 'bg-gray-600' : 'bg-gray-300'}`}
                >
                  <span className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${formConfig.slack_enabled ? 'translate-x-6' : 'translate-x-1'}`} />
                </button>
                <span className={`font-medium ${textPrimary}`}>Notificações no Slack</span>
              </div>
              {formConfig.slack_enabled && (
                <div className="space-y-3 pl-4 border-l-2 border-purple-500/30">
                  <div>
                    <label className={`block text-xs font-medium ${textSecondary} mb-1`}>Slack Webhook URL</label>
                    <input className={inputClass} type="password" placeholder="https://hooks.slack.com/services/..." value={formConfig.slack_webhook_url || ''} onChange={e => setFormConfig(f => ({ ...f, slack_webhook_url: e.target.value }))} />
                    {config?.slack_webhook_url && (
                      <p className={`text-xs ${textSecondary} mt-1`}>Webhook configurado: <code className="text-xs">{config.slack_webhook_url}</code></p>
                    )}
                  </div>
                </div>
              )}

              <div className="mt-4">
                <label className={`block text-xs font-medium ${textSecondary} mb-1`}>Severidade mínima para notificar</label>
                <select
                  className={inputClass}
                  value={formConfig.min_severity}
                  onChange={e => setFormConfig(f => ({ ...f, min_severity: e.target.value }))}
                >
                  <option value="CRITICAL">Apenas Crítico</option>
                  <option value="HIGH">Alto e Crítico</option>
                  <option value="MEDIUM">Médio, Alto e Crítico</option>
                  <option value="LOW">Tudo (exceto Info)</option>
                  <option value="INFO">Tudo</option>
                </select>
              </div>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-3 pt-2 border-t border-gray-200 dark:border-gray-700">
            <button
              onClick={handleSaveConfig}
              disabled={savingConfig}
              className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm font-medium transition-colors disabled:opacity-50"
            >
              <Save className="w-4 h-4" />
              {savingConfig ? 'Salvando...' : 'Salvar Configurações'}
            </button>
            <button
              onClick={handleTestAlert}
              disabled={testingAlert}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors disabled:opacity-50 border
                ${isDark ? 'border-gray-600 text-gray-300 hover:bg-gray-700' : 'border-gray-300 text-gray-600 hover:bg-gray-100'}`}
            >
              <Send className="w-4 h-4" />
              {testingAlert ? 'Enviando...' : 'Enviar Teste'}
            </button>
            <p className={`text-xs ${textSecondary}`}>O botão de teste envia um alerta "Info" para verificar as configurações.</p>
          </div>
        </div>
      )}

      <div className={`${cardBase} rounded-xl overflow-hidden`}>
        <div className={`px-4 py-3 ${isDark ? 'bg-gray-700/30' : 'bg-gray-50'} flex flex-col gap-3`}>
          <div className="flex items-center justify-between">
            <h2 className={`text-sm font-semibold ${textPrimary} flex items-center gap-2`}>
              <Clock className="w-4 h-4" />
              Histórico de Eventos
              {totalEvents > 0 && <span className={`text-xs ${textSecondary}`}>({totalEvents} total)</span>}
            </h2>
            <button
              onClick={handleApplyFilters}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg bg-blue-600 text-white hover:bg-blue-500 transition-colors"
            >
              <Filter className="w-3 h-3" />
              Filtrar
            </button>
          </div>
          <div className="flex flex-wrap gap-2 items-center">
            <select
              value={filterSeverity}
              onChange={e => setFilterSeverity(e.target.value)}
              className={selectClass}
            >
              <option value="">Todas as severidades</option>
              <option value="CRITICAL">Crítico</option>
              <option value="HIGH">Alto</option>
              <option value="MEDIUM">Médio</option>
              <option value="LOW">Baixo</option>
              <option value="INFO">Info</option>
            </select>
            <div className="flex items-center gap-1">
              <label className={`text-xs ${textSecondary}`}>De:</label>
              <input
                type="date"
                value={filterDateFrom}
                onChange={e => setFilterDateFrom(e.target.value)}
                className={selectClass}
              />
            </div>
            <div className="flex items-center gap-1">
              <label className={`text-xs ${textSecondary}`}>Até:</label>
              <input
                type="date"
                value={filterDateTo}
                onChange={e => setFilterDateTo(e.target.value)}
                className={selectClass}
              />
            </div>
            {(filterSeverity || filterDateFrom || filterDateTo) && (
              <button
                onClick={() => { setFilterSeverity(''); setFilterDateFrom(''); setFilterDateTo(''); }}
                className={`text-xs ${textSecondary} hover:text-red-400 underline`}
              >
                Limpar filtros
              </button>
            )}
          </div>
        </div>

        {loading ? (
          <div className="p-12 flex justify-center">
            <RefreshCw className="w-8 h-8 text-blue-400 animate-spin" />
          </div>
        ) : events.length === 0 ? (
          <div className={`p-12 text-center ${textSecondary} text-sm`}>
            <ShieldCheck className="w-10 h-10 mx-auto mb-3 opacity-30" />
            Nenhum evento encontrado para os filtros selecionados
          </div>
        ) : (
          <>
            <div className={`divide-y ${isDark ? 'divide-gray-700/50' : 'divide-gray-100'}`}>
              {events.map(event => {
                const sev = SEVERITY_CONFIG[event.severity] || SEVERITY_CONFIG.INFO;
                const isExpanded = expandedEvents.has(event.id);
                const typeLabel = EVENT_TYPE_LABELS[event.event_type] || event.event_type;
                return (
                  <div key={event.id} className={`px-4 py-3 transition-colors ${isDark ? 'hover:bg-gray-700/20' : 'hover:bg-gray-50'}`}>
                    <div
                      className="flex items-start justify-between gap-3 cursor-pointer"
                      onClick={() => event.detail && toggleExpand(event.id)}
                    >
                      <div className="flex items-start gap-3 min-w-0">
                        <span className={`mt-1.5 w-2 h-2 rounded-full flex-shrink-0 ${sev.dot}`} />
                        <div className="min-w-0">
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${sev.badge}`}>
                              {sev.label}
                            </span>
                            <span className={`text-xs font-medium ${textSecondary}`}>{typeLabel}</span>
                          </div>
                          <p className={`text-sm mt-1 ${textPrimary}`}>{event.message}</p>
                        </div>
                      </div>
                      <div className="flex items-center gap-2 flex-shrink-0">
                        <div className="text-right">
                          <p className={`text-xs ${textSecondary}`}>{timeAgo(event.created_at)}</p>
                          <p className={`text-xs ${textSecondary} hidden sm:block`}>{formatDatetime(event.created_at)}</p>
                        </div>
                        {event.detail && (
                          <div className={textSecondary}>
                            {isExpanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                          </div>
                        )}
                      </div>
                    </div>
                    {isExpanded && event.detail && (
                      <div className={`mt-2 ml-5 p-3 rounded-lg text-xs font-mono whitespace-pre-wrap ${isDark ? 'bg-gray-900/50 text-gray-300' : 'bg-gray-100 text-gray-700'}`}>
                        {event.detail}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>

            {totalPages > 1 && (
              <div className={`px-4 py-3 flex items-center justify-between border-t ${isDark ? 'border-gray-700' : 'border-gray-100'}`}>
                <p className={`text-xs ${textSecondary}`}>
                  Página {currentPage} de {totalPages} — {totalEvents} eventos
                </p>
                <div className="flex items-center gap-1">
                  <button
                    onClick={() => handlePageChange(currentPage - 1)}
                    disabled={currentPage === 1}
                    className={`p-1.5 rounded-lg transition-colors disabled:opacity-40 ${isDark ? 'hover:bg-gray-700 text-gray-300' : 'hover:bg-gray-100 text-gray-600'}`}
                  >
                    <ChevronLeft className="w-4 h-4" />
                  </button>
                  {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
                    let page: number;
                    if (totalPages <= 5) {
                      page = i + 1;
                    } else if (currentPage <= 3) {
                      page = i + 1;
                    } else if (currentPage >= totalPages - 2) {
                      page = totalPages - 4 + i;
                    } else {
                      page = currentPage - 2 + i;
                    }
                    return (
                      <button
                        key={page}
                        onClick={() => handlePageChange(page)}
                        className={`w-8 h-8 rounded-lg text-xs font-medium transition-colors ${
                          page === currentPage
                            ? 'bg-blue-600 text-white'
                            : isDark ? 'hover:bg-gray-700 text-gray-300' : 'hover:bg-gray-100 text-gray-600'
                        }`}
                      >
                        {page}
                      </button>
                    );
                  })}
                  <button
                    onClick={() => handlePageChange(currentPage + 1)}
                    disabled={currentPage === totalPages}
                    className={`p-1.5 rounded-lg transition-colors disabled:opacity-40 ${isDark ? 'hover:bg-gray-700 text-gray-300' : 'hover:bg-gray-100 text-gray-600'}`}
                  >
                    <ChevronRight className="w-4 h-4" />
                  </button>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
};

export default SaudeSistema;
