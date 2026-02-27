import type { ReactNode } from 'react';
import { AlertTriangle, Database, RefreshCw, WifiOff, Clock, Server } from 'lucide-react';

interface ConnectionAlertProps {
  avisos: string[];
  error?: string | null;
  onRetry?: () => void;
  retrying?: boolean;
}

function classifyWarning(aviso: string): {
  icon: ReactNode;
  source: string;
  type: string;
  suggestion: string;
} {
  const lowerAviso = aviso.toLowerCase();

  let source = 'Banco de Dados';
  if (lowerAviso.includes('ativo')) source = 'Banco Ativo (Inscrições)';
  else if (lowerAviso.includes('magento')) source = 'Banco Magento (E-commerce)';
  else if (lowerAviso.includes('ssh')) source = 'Túnel SSH';
  else if (lowerAviso.includes('nenhuma fonte')) source = 'Todas as fontes';

  let type = 'Erro de conexão';
  let icon = <WifiOff className="w-4 h-4" />;
  let suggestion = 'Tente atualizar os dados clicando em "Atualizar".';

  if (lowerAviso.includes('timeout')) {
    type = 'Tempo limite excedido';
    icon = <Clock className="w-4 h-4" />;
    suggestion = 'O banco demorou para responder. Aguarde alguns minutos e tente novamente.';
  } else if (lowerAviso.includes('operationalerror') || lowerAviso.includes('ssl')) {
    type = 'Conexão interrompida';
    icon = <WifiOff className="w-4 h-4" />;
    suggestion = 'A conexão com o banco foi perdida. Uma nova tentativa geralmente resolve o problema.';
  } else if (lowerAviso.includes('não configurad')) {
    type = 'Configuração ausente';
    icon = <Server className="w-4 h-4" />;
    suggestion = 'Verifique as variáveis de ambiente de conexão no servidor.';
  } else if (lowerAviso.includes('nenhuma fonte')) {
    type = 'Sem dados disponíveis';
    icon = <Database className="w-4 h-4" />;
    suggestion = 'Nenhum banco respondeu. Verifique a infraestrutura ou tente novamente em alguns minutos.';
  }

  return { icon, source, type, suggestion };
}

function classifyError(error: string): {
  title: string;
  detail: string;
  suggestion: string;
} {
  const lower = error.toLowerCase();

  if (lower.includes('sessão expirada') || lower.includes('faça login')) {
    return {
      title: 'Sessão Expirada',
      detail: 'Sua sessão de login expirou ou suas credenciais não são mais válidas.',
      suggestion: 'Faça login novamente para continuar acessando o sistema.'
    };
  }
  if (lower.includes('erro interno') || lower.includes('indisponível')) {
    return {
      title: 'Erro no Servidor',
      detail: error,
      suggestion: 'O banco de dados pode estar temporariamente fora do ar. Aguarde 1-2 minutos e clique em "Tentar novamente".'
    };
  }
  if (lower.includes('erro de rede') || lower.includes('conectar ao servidor')) {
    return {
      title: 'Sem Conexão',
      detail: 'Não foi possível se comunicar com o servidor da aplicação.',
      suggestion: 'Verifique sua conexão com a internet. Se estiver conectado, o servidor pode estar reiniciando.'
    };
  }
  if (lower.includes('timeout') || lower.includes('tempo limite')) {
    return {
      title: 'Tempo Limite Excedido',
      detail: 'A requisição demorou demais para ser processada.',
      suggestion: 'Os dados estão sendo processados. Aguarde um momento e tente novamente.'
    };
  }

  return {
    title: 'Erro ao Carregar Dados',
    detail: error,
    suggestion: 'Tente atualizar a página ou clique em "Atualizar".'
  };
}

export function ConnectionWarningBanner({ avisos, onRetry, retrying }: { avisos: string[]; onRetry?: () => void; retrying?: boolean }) {
  if (avisos.length === 0) return null;

  const now = new Date();
  const timestamp = now.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit', second: '2-digit' });

  return (
    <div className="mb-4 rounded-lg border border-yellow-500/30 bg-yellow-500/10 p-4">
      <div className="flex items-start gap-3">
        <AlertTriangle className="w-5 h-5 text-yellow-500 mt-0.5 flex-shrink-0" />
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between gap-2">
            <p className="font-semibold text-yellow-500">Dados Parciais</p>
            <span className="text-xs text-yellow-400/60 flex-shrink-0">{timestamp}</span>
          </div>
          <p className="text-xs text-yellow-400/70 mt-1">
            Alguns dados podem estar incompletos porque uma ou mais fontes de dados apresentaram problemas.
          </p>

          <div className="mt-3 space-y-2">
            {avisos.map((aviso, index) => {
              const info = classifyWarning(aviso);
              return (
                <div key={index} className="flex items-start gap-2 bg-yellow-500/5 rounded-md p-2">
                  <span className="text-yellow-400 mt-0.5 flex-shrink-0">{info.icon}</span>
                  <div className="min-w-0">
                    <p className="text-sm text-yellow-400">
                      <span className="font-medium">{info.source}</span>
                      <span className="text-yellow-400/60"> - {info.type}</span>
                    </p>
                    <p className="text-xs text-yellow-400/60 mt-0.5">{info.suggestion}</p>
                  </div>
                </div>
              );
            })}
          </div>

          {onRetry && (
            <button
              onClick={onRetry}
              disabled={retrying}
              className="mt-3 flex items-center gap-1.5 text-xs font-medium text-yellow-500 hover:text-yellow-400 transition-colors disabled:opacity-50"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${retrying ? 'animate-spin' : ''}`} />
              {retrying ? 'Tentando reconectar...' : 'Tentar novamente'}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

export function ConnectionErrorBanner({ error, onRetry, retrying }: { error: string; onRetry?: () => void; retrying?: boolean }) {
  const info = classifyError(error);
  const now = new Date();
  const timestamp = now.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit', second: '2-digit' });

  return (
    <div className="mb-4 rounded-lg border border-red-500/30 bg-red-500/10 p-4">
      <div className="flex items-start gap-3">
        <Database className="w-5 h-5 text-red-400 mt-0.5 flex-shrink-0" />
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between gap-2">
            <p className="font-semibold text-red-400">{info.title}</p>
            <span className="text-xs text-red-400/60 flex-shrink-0">{timestamp}</span>
          </div>
          <p className="text-sm text-red-400/80 mt-1">{info.detail}</p>
          <p className="text-xs text-red-400/60 mt-1">{info.suggestion}</p>

          {onRetry && (
            <button
              onClick={onRetry}
              disabled={retrying}
              className="mt-3 flex items-center gap-1.5 text-xs font-medium text-red-400 hover:text-red-300 transition-colors disabled:opacity-50"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${retrying ? 'animate-spin' : ''}`} />
              {retrying ? 'Reconectando...' : 'Tentar novamente'}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

export default function ConnectionAlert({ avisos, error, onRetry, retrying }: ConnectionAlertProps) {
  return (
    <>
      {error && <ConnectionErrorBanner error={error} onRetry={onRetry} retrying={retrying} />}
      <ConnectionWarningBanner avisos={avisos} onRetry={onRetry} retrying={retrying} />
    </>
  );
}
