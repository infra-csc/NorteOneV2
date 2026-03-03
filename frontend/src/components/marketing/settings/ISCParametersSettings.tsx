import React, { useState, useEffect } from 'react';
import { Activity, Save, RotateCcw, Info, AlertTriangle, Loader2 } from 'lucide-react';
import { ISCParameters } from '../../../types/marketingSettings';
import { marketingService } from '../../../services/api';

const defaultISCParameters: ISCParameters = {
  ia730Weight: 20.0,
  curvaDWeight: 40.0,
  rolling14dWeight: 40.0,
  greenThreshold: 1.10,
  yellowThreshold: 0.90,
  criticalWindowStart: 45,
  criticalWindowEnd: 40,
  promotionDeadline: 40
};

const ISCParametersSettings: React.FC = () => {
  const [parameters, setParameters] = useState<ISCParameters>({ ...defaultISCParameters });
  const [hasChanges, setHasChanges] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    marketingService.getSettings('isc_parameters').then((res) => {
      if (res.value) {
        setParameters(res.value);
      }
    }).catch(() => {}).finally(() => setLoading(false));
  }, []);

  const handleChange = (field: keyof ISCParameters, value: number) => {
    setParameters({ ...parameters, [field]: value });
    setHasChanges(true);
  };

  const handleSave = () => {
    marketingService.updateSettings('isc_parameters', parameters).catch(() => {});
    setHasChanges(false);
  };

  const handleReset = () => {
    setParameters({ ...defaultISCParameters });
    setHasChanges(true);
  };

  const totalWeight = parameters.ia730Weight + parameters.curvaDWeight + parameters.rolling14dWeight;
  const isWeightValid = Math.abs(totalWeight - 100) < 0.1;

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="w-8 h-8 text-blue-600 animate-spin" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold text-gray-900 dark:text-white">
            Ajuste de Parâmetros do ISC
          </h2>
          <p className="text-gray-500 dark:text-gray-400 mt-1">
            Configure os pesos e limiares do Índice de Saúde Comercial
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleReset}
            className="px-4 py-2 border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors flex items-center gap-2"
          >
            <RotateCcw className="w-4 h-4" />
            Restaurar Padrão
          </button>
          <button
            onClick={handleSave}
            disabled={!hasChanges || !isWeightValid}
            className={`px-4 py-2 rounded-lg flex items-center gap-2 transition-colors ${
              hasChanges && isWeightValid
                ? 'bg-blue-600 text-white hover:bg-blue-700'
                : 'bg-gray-300 text-gray-500 cursor-not-allowed dark:bg-gray-600'
            }`}
          >
            <Save className="w-4 h-4" />
            Salvar
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6">
          <div className="flex items-center gap-3 mb-6">
            <div className="p-2 bg-blue-100 dark:bg-blue-900/30 rounded-lg">
              <Activity className="w-5 h-5 text-blue-600 dark:text-blue-400" />
            </div>
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
              Pesos dos Componentes
            </h3>
          </div>

          <div className="space-y-6">
            <div>
              <div className="flex items-center justify-between mb-2">
                <label className="text-sm font-medium text-gray-700 dark:text-gray-300 flex items-center gap-2">
                  IA 7/30 (Índice de Aceleração)
                  <div className="group relative">
                    <Info className="w-4 h-4 text-gray-400 cursor-help" />
                    <div className="hidden group-hover:block absolute z-10 w-64 p-2 bg-gray-900 text-white text-xs rounded-lg left-0 top-6">
                      Compara vendas dos últimos 7 dias vs 30 dias, indicando aceleração ou desaceleração
                    </div>
                  </div>
                </label>
                <span className="text-sm font-bold text-gray-900 dark:text-white">{parameters.ia730Weight.toFixed(2)}%</span>
              </div>
              <input
                type="range"
                min="0"
                max="100"
                step="0.1"
                value={parameters.ia730Weight}
                onChange={(e) => handleChange('ia730Weight', Number(e.target.value))}
                className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer dark:bg-gray-700"
              />
            </div>

            <div>
              <div className="flex items-center justify-between mb-2">
                <label className="text-sm font-medium text-gray-700 dark:text-gray-300 flex items-center gap-2">
                  Curva D-% (Progresso no Tempo)
                  <div className="group relative">
                    <Info className="w-4 h-4 text-gray-400 cursor-help" />
                    <div className="hidden group-hover:block absolute z-10 w-64 p-2 bg-gray-900 text-white text-xs rounded-lg left-0 top-6">
                      Compara vendas reais acumuladas vs vendas esperadas pelo benchmark
                    </div>
                  </div>
                </label>
                <span className="text-sm font-bold text-gray-900 dark:text-white">{parameters.curvaDWeight.toFixed(2)}%</span>
              </div>
              <input
                type="range"
                min="0"
                max="100"
                step="0.1"
                value={parameters.curvaDWeight}
                onChange={(e) => handleChange('curvaDWeight', Number(e.target.value))}
                className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer dark:bg-gray-700"
              />
            </div>

            <div>
              <div className="flex items-center justify-between mb-2">
                <label className="text-sm font-medium text-gray-700 dark:text-gray-300 flex items-center gap-2">
                  Rolling 14d (Média Móvel)
                  <div className="group relative">
                    <Info className="w-4 h-4 text-gray-400 cursor-help" />
                    <div className="hidden group-hover:block absolute z-10 w-64 p-2 bg-gray-900 text-white text-xs rounded-lg left-0 top-6">
                      Média de vendas dos últimos 14 dias normalizada pelo histórico
                    </div>
                  </div>
                </label>
                <span className="text-sm font-bold text-gray-900 dark:text-white">{parameters.rolling14dWeight.toFixed(2)}%</span>
              </div>
              <input
                type="range"
                min="0"
                max="100"
                step="0.1"
                value={parameters.rolling14dWeight}
                onChange={(e) => handleChange('rolling14dWeight', Number(e.target.value))}
                className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer dark:bg-gray-700"
              />
            </div>

            <div className={`p-4 rounded-lg ${isWeightValid ? 'bg-green-50 dark:bg-green-900/20' : 'bg-red-50 dark:bg-red-900/20'}`}>
              <div className="flex items-center justify-between">
                <span className={`text-sm font-medium ${isWeightValid ? 'text-green-700 dark:text-green-400' : 'text-red-700 dark:text-red-400'}`}>
                  Total dos Pesos:
                </span>
                <span className={`text-lg font-bold ${isWeightValid ? 'text-green-700 dark:text-green-400' : 'text-red-700 dark:text-red-400'}`}>
                  {totalWeight.toFixed(2)}%
                </span>
              </div>
              {!isWeightValid && (
                <p className="text-xs text-red-600 dark:text-red-400 mt-1">
                  O total deve ser 100%
                </p>
              )}
            </div>
          </div>
        </div>

        <div className="space-y-6">
          <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6">
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-6">
              Limiares de Classificação
            </h3>

            <div className="space-y-4">
              <div>
                <label className="text-sm font-medium text-gray-700 dark:text-gray-300 block mb-2">
                  Limiar Verde (Acelerando)
                </label>
                <div className="flex items-center gap-4">
                  <span className="text-green-600">ISC &gt;</span>
                  <input
                    type="number"
                    step="0.01"
                    value={parameters.greenThreshold}
                    onChange={(e) => handleChange('greenThreshold', Number(e.target.value))}
                    className="w-24 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                  />
                  <div className="flex items-center gap-2 px-3 py-2 bg-green-100 dark:bg-green-900/30 rounded-lg">
                    <span className="text-lg">🟢</span>
                    <span className="text-sm font-medium text-green-700 dark:text-green-400">Acelerando</span>
                  </div>
                </div>
              </div>

              <div>
                <label className="text-sm font-medium text-gray-700 dark:text-gray-300 block mb-2">
                  Limiar Amarelo (Estável)
                </label>
                <div className="flex items-center gap-4">
                  <span className="text-yellow-600">ISC &ge;</span>
                  <input
                    type="number"
                    step="0.01"
                    value={parameters.yellowThreshold}
                    onChange={(e) => handleChange('yellowThreshold', Number(e.target.value))}
                    className="w-24 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                  />
                  <div className="flex items-center gap-2 px-3 py-2 bg-yellow-100 dark:bg-yellow-900/30 rounded-lg">
                    <span className="text-lg">🟡</span>
                    <span className="text-sm font-medium text-yellow-700 dark:text-yellow-400">Estável</span>
                  </div>
                </div>
              </div>

              <div className="p-3 bg-red-50 dark:bg-red-900/20 rounded-lg">
                <div className="flex items-center gap-2">
                  <span className="text-lg">🔴</span>
                  <span className="text-sm text-red-700 dark:text-red-400">
                    Desacelerando: ISC &lt; {parameters.yellowThreshold}
                  </span>
                </div>
              </div>
            </div>
          </div>

          <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6">
            <div className="flex items-center gap-3 mb-6">
              <AlertTriangle className="w-5 h-5 text-amber-600" />
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
                Janela Crítica (Regra D-40)
              </h3>
            </div>

            <div className="space-y-4">
              <div>
                <label className="text-sm font-medium text-gray-700 dark:text-gray-300 block mb-2">
                  Início da Janela de Diagnóstico
                </label>
                <div className="flex items-center gap-2">
                  <span className="text-gray-600 dark:text-gray-400">D-</span>
                  <input
                    type="number"
                    value={parameters.criticalWindowStart}
                    onChange={(e) => handleChange('criticalWindowStart', Number(e.target.value))}
                    className="w-20 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                  />
                </div>
              </div>

              <div>
                <label className="text-sm font-medium text-gray-700 dark:text-gray-300 block mb-2">
                  Fim da Janela / Deadline de Promoção
                </label>
                <div className="flex items-center gap-2">
                  <span className="text-gray-600 dark:text-gray-400">D-</span>
                  <input
                    type="number"
                    value={parameters.promotionDeadline}
                    onChange={(e) => handleChange('promotionDeadline', Number(e.target.value))}
                    className="w-20 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                  />
                </div>
              </div>

              <div className="p-3 bg-amber-50 dark:bg-amber-900/20 rounded-lg border border-amber-200 dark:border-amber-800">
                <p className="text-sm text-amber-700 dark:text-amber-400">
                  Eventos entre D-{parameters.criticalWindowStart} e D-{parameters.promotionDeadline} estão na janela crítica. 
                  Após D-{parameters.promotionDeadline}, promoções não são recomendadas.
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-xl p-4">
        <h4 className="font-medium text-blue-800 dark:text-blue-300 mb-2">
          Fórmula do ISC
        </h4>
        <div className="bg-white dark:bg-gray-800 rounded-lg p-4 font-mono text-sm text-gray-800 dark:text-gray-200">
          ISC = 1.0 + ({parameters.curvaDWeight.toFixed(0)}% × D + {parameters.rolling14dWeight.toFixed(0)}% × R + {parameters.ia730Weight.toFixed(0)}% × IA)
          <div className="mt-2 text-xs text-gray-500 dark:text-gray-400">
            D = clamp(CurvaD - 1, ±0.30) | R = clamp(Rolling14 - 1, ±0.30) | IA = clamp(IA7/30 - 1, ±0.30)
          </div>
        </div>
      </div>
    </div>
  );
};

export default ISCParametersSettings;
