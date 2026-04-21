import React from 'react';
import { Download, RefreshCw, Share, X, Smartphone, PlusSquare } from 'lucide-react';
import { usePWA } from './usePWA';

const PWAManager: React.FC = () => {
  const {
    needRefresh,
    installPromptAvailable,
    showIOSInstallHint,
    applyUpdate,
    dismissUpdate,
    triggerInstall,
    dismissInstall,
  } = usePWA();

  return (
    <>
      {needRefresh && (
        <div
          role="status"
          className="fixed bottom-4 left-1/2 -translate-x-1/2 z-[100] w-[min(92vw,420px)] rounded-xl shadow-2xl border border-indigo-400/40 bg-gradient-to-r from-indigo-600 to-purple-600 text-white px-4 py-3 flex items-center gap-3"
        >
          <RefreshCw className="w-5 h-5 flex-shrink-0" />
          <div className="flex-1 text-sm">
            <p className="font-semibold leading-tight">Nova versão disponível</p>
            <p className="text-xs text-indigo-100 leading-tight mt-0.5">
              Atualize para receber as últimas melhorias.
            </p>
          </div>
          <button
            onClick={applyUpdate}
            className="text-xs font-semibold bg-white text-indigo-700 hover:bg-indigo-50 rounded-md px-3 py-1.5 transition-colors"
          >
            Atualizar
          </button>
          <button
            onClick={dismissUpdate}
            aria-label="Dispensar"
            className="p-1 rounded-md hover:bg-white/10 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {!needRefresh && installPromptAvailable && (
        <div
          role="dialog"
          aria-label="Instalar Norte One"
          className="fixed bottom-4 left-1/2 -translate-x-1/2 z-[90] w-[min(92vw,420px)] rounded-xl shadow-2xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 px-4 py-3 flex items-center gap-3"
        >
          <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center text-white flex-shrink-0">
            <Smartphone className="w-5 h-5" />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-semibold text-gray-900 dark:text-white leading-tight">
              Instalar Norte One
            </p>
            <p className="text-xs text-gray-500 dark:text-gray-400 leading-tight mt-0.5">
              Acesso rápido pela tela inicial, em tela cheia.
            </p>
          </div>
          <button
            onClick={() => void triggerInstall()}
            className="text-xs font-semibold bg-gradient-to-r from-indigo-600 to-purple-600 text-white hover:opacity-90 rounded-md px-3 py-1.5 transition-opacity flex items-center gap-1.5"
          >
            <Download className="w-3.5 h-3.5" />
            Instalar
          </button>
          <button
            onClick={dismissInstall}
            aria-label="Dispensar"
            className="p-1 rounded-md hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors text-gray-400"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {!needRefresh && !installPromptAvailable && showIOSInstallHint && (
        <div
          role="dialog"
          aria-label="Instalar no iOS"
          className="fixed bottom-4 left-1/2 -translate-x-1/2 z-[90] w-[min(92vw,420px)] rounded-xl shadow-2xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 px-4 py-3"
        >
          <div className="flex items-start gap-3">
            <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center text-white flex-shrink-0">
              <Smartphone className="w-5 h-5" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-semibold text-gray-900 dark:text-white leading-tight">
                Instalar Norte One no iPhone
              </p>
              <p className="text-xs text-gray-500 dark:text-gray-400 mt-1 leading-snug">
                Toque em <Share className="inline w-3.5 h-3.5 mx-0.5 -mt-0.5 text-blue-500" />{' '}
                <span className="font-medium">Compartilhar</span>, depois em{' '}
                <PlusSquare className="inline w-3.5 h-3.5 mx-0.5 -mt-0.5 text-gray-500" />{' '}
                <span className="font-medium">Adicionar à Tela de Início</span>.
              </p>
            </div>
            <button
              onClick={dismissInstall}
              aria-label="Dispensar"
              className="p-1 rounded-md hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors text-gray-400 flex-shrink-0"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}
    </>
  );
};

export default PWAManager;
