import React, { useState, useEffect } from 'react';
import { Target, Edit2, Save, X, TrendingUp, DollarSign, Loader2 } from 'lucide-react';
import { EventGoal } from '../../../types/marketingSettings';
import { marketingService } from '../../../services/api';

const EventGoalsSettings: React.FC = () => {
  const [goals, setGoals] = useState<EventGoal[]>([]);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editForm, setEditForm] = useState<Partial<EventGoal>>({});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    marketingService.getSettings('event_goals').then((res) => {
      if (res.value) {
        setGoals(res.value);
      }
    }).catch(() => {}).finally(() => setLoading(false));
  }, []);

  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat('pt-BR', {
      style: 'currency',
      currency: 'BRL'
    }).format(value);
  };

  const formatNumber = (value: number) => {
    return new Intl.NumberFormat('pt-BR').format(value);
  };

  const handleEdit = (goal: EventGoal) => {
    setEditingId(goal.id);
    setEditForm({ ...goal });
  };

  const handleSave = () => {
    if (editingId && editForm) {
      const updatedGoals = goals.map(g => 
        g.id === editingId 
          ? { ...g, ...editForm, updatedAt: new Date().toISOString().split('T')[0] }
          : g
      );
      setGoals(updatedGoals);
      setEditingId(null);
      setEditForm({});
      marketingService.updateSettings('event_goals', updatedGoals).catch(() => {});
    }
  };

  const handleCancel = () => {
    setEditingId(null);
    setEditForm({});
  };

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
            Definição de Metas por Evento
          </h2>
          <p className="text-gray-500 dark:text-gray-400 mt-1">
            Configure as metas de vendas e receita para cada evento
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-blue-50 dark:bg-blue-900/20 rounded-xl p-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-blue-100 dark:bg-blue-900/40 rounded-lg">
              <Target className="w-5 h-5 text-blue-600 dark:text-blue-400" />
            </div>
            <div>
              <p className="text-sm text-blue-600 dark:text-blue-400">Total de Eventos</p>
              <p className="text-2xl font-bold text-blue-800 dark:text-blue-200">{goals.length}</p>
            </div>
          </div>
        </div>
        <div className="bg-green-50 dark:bg-green-900/20 rounded-xl p-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-green-100 dark:bg-green-900/40 rounded-lg">
              <TrendingUp className="w-5 h-5 text-green-600 dark:text-green-400" />
            </div>
            <div>
              <p className="text-sm text-green-600 dark:text-green-400">Meta Total de Vendas</p>
              <p className="text-2xl font-bold text-green-800 dark:text-green-200">
                {formatNumber(goals.reduce((sum, g) => sum + g.salesGoal, 0))}
              </p>
            </div>
          </div>
        </div>
        <div className="bg-purple-50 dark:bg-purple-900/20 rounded-xl p-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-purple-100 dark:bg-purple-900/40 rounded-lg">
              <DollarSign className="w-5 h-5 text-purple-600 dark:text-purple-400" />
            </div>
            <div>
              <p className="text-sm text-purple-600 dark:text-purple-400">Meta Total de Receita</p>
              <p className="text-2xl font-bold text-purple-800 dark:text-purple-200">
                {formatCurrency(goals.reduce((sum, g) => sum + g.revenueGoal, 0))}
              </p>
            </div>
          </div>
        </div>
      </div>

      <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="bg-gray-50 dark:bg-gray-700/50">
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                  Evento
                </th>
                <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                  Meta de Vendas
                </th>
                <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                  Meta de Receita
                </th>
                <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                  Conversão Alvo
                </th>
                <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                  Ticket Médio Alvo
                </th>
                <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                  Atualizado
                </th>
                <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                  Ações
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
              {goals.map((goal) => (
                <tr key={goal.id} className="hover:bg-gray-50 dark:hover:bg-gray-700/50">
                  <td className="px-4 py-4">
                    <p className="font-medium text-gray-900 dark:text-white">{goal.eventName}</p>
                  </td>
                  <td className="px-4 py-4 text-center">
                    {editingId === goal.id ? (
                      <input
                        type="number"
                        value={editForm.salesGoal || 0}
                        onChange={(e) => setEditForm({ ...editForm, salesGoal: Number(e.target.value) })}
                        className="w-24 px-2 py-1 border border-gray-300 dark:border-gray-600 rounded text-center bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                      />
                    ) : (
                      <span className="text-gray-900 dark:text-white">{formatNumber(goal.salesGoal)}</span>
                    )}
                  </td>
                  <td className="px-4 py-4 text-center">
                    {editingId === goal.id ? (
                      <input
                        type="number"
                        value={editForm.revenueGoal || 0}
                        onChange={(e) => setEditForm({ ...editForm, revenueGoal: Number(e.target.value) })}
                        className="w-32 px-2 py-1 border border-gray-300 dark:border-gray-600 rounded text-center bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                      />
                    ) : (
                      <span className="text-gray-900 dark:text-white">{formatCurrency(goal.revenueGoal)}</span>
                    )}
                  </td>
                  <td className="px-4 py-4 text-center">
                    {editingId === goal.id ? (
                      <input
                        type="number"
                        value={editForm.conversionTarget || 0}
                        onChange={(e) => setEditForm({ ...editForm, conversionTarget: Number(e.target.value) })}
                        className="w-20 px-2 py-1 border border-gray-300 dark:border-gray-600 rounded text-center bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                      />
                    ) : (
                      <span className="text-gray-900 dark:text-white">{goal.conversionTarget}%</span>
                    )}
                  </td>
                  <td className="px-4 py-4 text-center">
                    {editingId === goal.id ? (
                      <input
                        type="number"
                        step="0.01"
                        value={editForm.averageTicketTarget || 0}
                        onChange={(e) => setEditForm({ ...editForm, averageTicketTarget: Number(e.target.value) })}
                        className="w-24 px-2 py-1 border border-gray-300 dark:border-gray-600 rounded text-center bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                      />
                    ) : (
                      <span className="text-gray-900 dark:text-white">{formatCurrency(goal.averageTicketTarget)}</span>
                    )}
                  </td>
                  <td className="px-4 py-4 text-center text-sm text-gray-500 dark:text-gray-400">
                    {new Date(goal.updatedAt).toLocaleDateString('pt-BR')}
                  </td>
                  <td className="px-4 py-4 text-center">
                    {editingId === goal.id ? (
                      <div className="flex items-center justify-center gap-2">
                        <button
                          onClick={handleSave}
                          className="p-1.5 text-green-600 hover:bg-green-100 dark:hover:bg-green-900/30 rounded-lg transition-colors"
                        >
                          <Save className="w-4 h-4" />
                        </button>
                        <button
                          onClick={handleCancel}
                          className="p-1.5 text-red-600 hover:bg-red-100 dark:hover:bg-red-900/30 rounded-lg transition-colors"
                        >
                          <X className="w-4 h-4" />
                        </button>
                      </div>
                    ) : (
                      <button
                        onClick={() => handleEdit(goal)}
                        className="p-1.5 text-blue-600 hover:bg-blue-100 dark:hover:bg-blue-900/30 rounded-lg transition-colors"
                      >
                        <Edit2 className="w-4 h-4" />
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

export default EventGoalsSettings;
