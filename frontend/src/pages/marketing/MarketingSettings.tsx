import React from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft, Settings, AlertTriangle } from 'lucide-react';

const MarketingSettings: React.FC = () => {
  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center gap-4">
        <Link
          to="/marketing"
          className="p-2 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors"
        >
          <ArrowLeft className="w-5 h-5 text-gray-600 dark:text-gray-400" />
        </Link>
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
            Configurações
          </h1>
          <p className="text-gray-500 dark:text-gray-400 mt-1">
            Configurações do Marketing Performance
          </p>
        </div>
      </div>

      <div className="bg-white dark:bg-gray-800 rounded-xl p-8 shadow-sm border border-gray-200 dark:border-gray-700">
        <div className="flex flex-col items-center justify-center text-center py-12">
          <div className="p-4 bg-gray-100 dark:bg-gray-700 rounded-full mb-4">
            <Settings className="w-12 h-12 text-gray-400" />
          </div>
          <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-2">
            Em Desenvolvimento
          </h2>
          <p className="text-gray-500 dark:text-gray-400 max-w-md">
            Esta seção está em desenvolvimento. Em breve você poderá configurar 
            metas, benchmarks e parâmetros do ISC.
          </p>
        </div>
      </div>

      <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-xl p-4">
        <div className="flex items-start gap-3">
          <AlertTriangle className="w-5 h-5 text-blue-600 dark:text-blue-400 mt-0.5" />
          <div>
            <h3 className="font-medium text-blue-800 dark:text-blue-300">
              Funcionalidades Planejadas
            </h3>
            <ul className="text-sm text-blue-700 dark:text-blue-400 mt-2 space-y-1 list-disc list-inside">
              <li>Definição de metas por evento</li>
              <li>Configuração de curvas de benchmark</li>
              <li>Ajuste de parâmetros do ISC</li>
              <li>Gestão de categorias de eventos</li>
              <li>Configuração de alertas automáticos</li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
};

export default MarketingSettings;
