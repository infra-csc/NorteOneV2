import React, { useState } from 'react';
import { TrendingUp, Check, Plus, Trash2, Edit2, Save, X } from 'lucide-react';
import { BenchmarkCurve, BenchmarkDataPoint } from '../../../types/marketingSettings';
import { getBenchmarkCurves } from '../../../data/mockMarketingSettings';

const BenchmarkCurvesSettings: React.FC = () => {
  const [curves, setCurves] = useState<BenchmarkCurve[]>(getBenchmarkCurves());
  const [selectedCurve, setSelectedCurve] = useState<BenchmarkCurve | null>(curves.find(c => c.isDefault) || null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingDataPoints, setEditingDataPoints] = useState<BenchmarkDataPoint[]>([]);

  const getCurveTypeColor = (type: string) => {
    switch (type) {
      case 'aggressive': return 'text-red-600 bg-red-100 dark:text-red-400 dark:bg-red-900/30';
      case 'moderate': return 'text-yellow-600 bg-yellow-100 dark:text-yellow-400 dark:bg-yellow-900/30';
      case 'conservative': return 'text-green-600 bg-green-100 dark:text-green-400 dark:bg-green-900/30';
      default: return 'text-gray-600 bg-gray-100 dark:text-gray-400 dark:bg-gray-700';
    }
  };

  const getCurveTypeLabel = (type: string) => {
    switch (type) {
      case 'aggressive': return 'Agressiva';
      case 'moderate': return 'Moderada';
      case 'conservative': return 'Conservadora';
      default: return type;
    }
  };

  const handleSetDefault = (id: string) => {
    setCurves(curves.map(c => ({
      ...c,
      isDefault: c.id === id
    })));
  };

  const handleEditCurve = (curve: BenchmarkCurve) => {
    setEditingId(curve.id);
    setEditingDataPoints([...curve.dataPoints]);
  };

  const handleSaveEdit = () => {
    if (editingId) {
      setCurves(curves.map(c => 
        c.id === editingId 
          ? { ...c, dataPoints: editingDataPoints }
          : c
      ));
      if (selectedCurve?.id === editingId) {
        setSelectedCurve({ ...selectedCurve, dataPoints: editingDataPoints });
      }
      setEditingId(null);
      setEditingDataPoints([]);
    }
  };

  const handleCancelEdit = () => {
    setEditingId(null);
    setEditingDataPoints([]);
  };

  const updateDataPoint = (index: number, field: keyof BenchmarkDataPoint, value: number) => {
    const newPoints = [...editingDataPoints];
    newPoints[index] = { ...newPoints[index], [field]: value };
    setEditingDataPoints(newPoints);
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold text-gray-900 dark:text-white">
            Configuração de Curvas de Benchmark
          </h2>
          <p className="text-gray-500 dark:text-gray-400 mt-1">
            Defina as curvas de referência para acompanhamento de vendas
          </p>
        </div>
        <button className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors flex items-center gap-2">
          <Plus className="w-4 h-4" />
          Nova Curva
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-1 space-y-4">
          <h3 className="font-medium text-gray-900 dark:text-white">Curvas Disponíveis</h3>
          {curves.map((curve) => (
            <div
              key={curve.id}
              onClick={() => setSelectedCurve(curve)}
              className={`p-4 rounded-xl border-2 cursor-pointer transition-all ${
                selectedCurve?.id === curve.id
                  ? 'border-blue-500 bg-blue-50 dark:bg-blue-900/20'
                  : 'border-gray-200 dark:border-gray-700 hover:border-gray-300 dark:hover:border-gray-600'
              }`}
            >
              <div className="flex items-start justify-between">
                <div className="flex items-center gap-3">
                  <div className={`p-2 rounded-lg ${getCurveTypeColor(curve.type)}`}>
                    <TrendingUp className="w-5 h-5" />
                  </div>
                  <div>
                    <p className="font-medium text-gray-900 dark:text-white">{curve.name}</p>
                    <p className="text-sm text-gray-500 dark:text-gray-400">{curve.description}</p>
                  </div>
                </div>
                {curve.isDefault && (
                  <span className="px-2 py-1 text-xs font-medium bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400 rounded-full">
                    Padrão
                  </span>
                )}
              </div>
              <div className="mt-3 flex items-center justify-between">
                <span className={`px-2 py-1 text-xs font-medium rounded-full ${getCurveTypeColor(curve.type)}`}>
                  {getCurveTypeLabel(curve.type)}
                </span>
                <div className="flex items-center gap-2">
                  {!curve.isDefault && (
                    <button
                      onClick={(e) => { e.stopPropagation(); handleSetDefault(curve.id); }}
                      className="text-xs text-blue-600 hover:text-blue-700 dark:text-blue-400"
                    >
                      Definir como padrão
                    </button>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>

        <div className="lg:col-span-2">
          {selectedCurve && (
            <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6">
              <div className="flex items-center justify-between mb-6">
                <div>
                  <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
                    {selectedCurve.name}
                  </h3>
                  <p className="text-sm text-gray-500 dark:text-gray-400">{selectedCurve.description}</p>
                </div>
                {editingId === selectedCurve.id ? (
                  <div className="flex items-center gap-2">
                    <button
                      onClick={handleSaveEdit}
                      className="p-2 text-green-600 hover:bg-green-100 dark:hover:bg-green-900/30 rounded-lg transition-colors"
                    >
                      <Save className="w-5 h-5" />
                    </button>
                    <button
                      onClick={handleCancelEdit}
                      className="p-2 text-red-600 hover:bg-red-100 dark:hover:bg-red-900/30 rounded-lg transition-colors"
                    >
                      <X className="w-5 h-5" />
                    </button>
                  </div>
                ) : (
                  <button
                    onClick={() => handleEditCurve(selectedCurve)}
                    className="p-2 text-blue-600 hover:bg-blue-100 dark:hover:bg-blue-900/30 rounded-lg transition-colors"
                  >
                    <Edit2 className="w-5 h-5" />
                  </button>
                )}
              </div>

              <div className="mb-6">
                <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">
                  Visualização da Curva
                </h4>
                <div className="h-48 bg-gray-50 dark:bg-gray-700/50 rounded-lg p-4 relative">
                  <svg className="w-full h-full" viewBox="0 0 400 150">
                    <defs>
                      <linearGradient id="curveGradient" x1="0%" y1="0%" x2="0%" y2="100%">
                        <stop offset="0%" stopColor="#3b82f6" stopOpacity="0.3" />
                        <stop offset="100%" stopColor="#3b82f6" stopOpacity="0" />
                      </linearGradient>
                    </defs>
                    <line x1="40" y1="130" x2="380" y2="130" stroke="#9ca3af" strokeWidth="1" />
                    <line x1="40" y1="10" x2="40" y2="130" stroke="#9ca3af" strokeWidth="1" />
                    {[0, 25, 50, 75, 100].map((val, i) => (
                      <g key={i}>
                        <text x="35" y={130 - (val * 1.2)} fontSize="10" textAnchor="end" fill="#6b7280">{val}%</text>
                        <line x1="38" y1={130 - (val * 1.2)} x2="40" y2={130 - (val * 1.2)} stroke="#9ca3af" strokeWidth="1" />
                      </g>
                    ))}
                    {(editingId === selectedCurve.id ? editingDataPoints : selectedCurve.dataPoints).map((point, i) => (
                      <text key={i} x={40 + ((90 - point.dMinus) / 90) * 340} y="145" fontSize="9" textAnchor="middle" fill="#6b7280">
                        D-{point.dMinus}
                      </text>
                    ))}
                    <path
                      d={`M ${(editingId === selectedCurve.id ? editingDataPoints : selectedCurve.dataPoints).map((point, i) => {
                        const x = 40 + ((90 - point.dMinus) / 90) * 340;
                        const y = 130 - (point.expectedPercentage * 1.2);
                        return `${i === 0 ? 'M' : 'L'} ${x} ${y}`;
                      }).join(' ')} L 380 130 L 40 130 Z`}
                      fill="url(#curveGradient)"
                    />
                    <path
                      d={(editingId === selectedCurve.id ? editingDataPoints : selectedCurve.dataPoints).map((point, i) => {
                        const x = 40 + ((90 - point.dMinus) / 90) * 340;
                        const y = 130 - (point.expectedPercentage * 1.2);
                        return `${i === 0 ? 'M' : 'L'} ${x} ${y}`;
                      }).join(' ')}
                      fill="none"
                      stroke="#3b82f6"
                      strokeWidth="2"
                    />
                    {(editingId === selectedCurve.id ? editingDataPoints : selectedCurve.dataPoints).map((point, i) => {
                      const x = 40 + ((90 - point.dMinus) / 90) * 340;
                      const y = 130 - (point.expectedPercentage * 1.2);
                      return (
                        <circle key={i} cx={x} cy={y} r="4" fill="#3b82f6" />
                      );
                    })}
                  </svg>
                </div>
              </div>

              <div>
                <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">
                  Pontos de Referência
                </h4>
                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead>
                      <tr className="bg-gray-50 dark:bg-gray-700/50">
                        <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                          Dias para Evento (D-)
                        </th>
                        <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                          % Esperado de Vendas
                        </th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
                      {(editingId === selectedCurve.id ? editingDataPoints : selectedCurve.dataPoints).map((point, index) => (
                        <tr key={index}>
                          <td className="px-4 py-3">
                            {editingId === selectedCurve.id ? (
                              <input
                                type="number"
                                value={point.dMinus}
                                onChange={(e) => updateDataPoint(index, 'dMinus', Number(e.target.value))}
                                className="w-20 px-2 py-1 border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                              />
                            ) : (
                              <span className="text-gray-900 dark:text-white">D-{point.dMinus}</span>
                            )}
                          </td>
                          <td className="px-4 py-3">
                            {editingId === selectedCurve.id ? (
                              <input
                                type="number"
                                value={point.expectedPercentage}
                                onChange={(e) => updateDataPoint(index, 'expectedPercentage', Number(e.target.value))}
                                className="w-20 px-2 py-1 border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                              />
                            ) : (
                              <span className="text-gray-900 dark:text-white">{point.expectedPercentage}%</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default BenchmarkCurvesSettings;
