import React, { useState, useEffect } from 'react';
import { Bell, Plus, Edit2, Trash2, Save, X, Mail, MessageSquare, Smartphone, Hash, AlertTriangle, TrendingDown, TrendingUp, Calendar, Target, Loader2 } from 'lucide-react';
import { AlertConfig, AlertCondition, AlertChannel } from '../../../types/marketingSettings';
import { marketingService } from '../../../services/api';

const AlertsSettings: React.FC = () => {
  const [alerts, setAlerts] = useState<AlertConfig[]>([]);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [showNewForm, setShowNewForm] = useState(false);
  const [loading, setLoading] = useState(true);
  const [newAlert, setNewAlert] = useState<Partial<AlertConfig>>({
    name: '',
    description: '',
    condition: { type: 'isc_below', value: 35, comparison: 'less_than' },
    channels: [{ type: 'email', target: '', isEnabled: true }],
    isActive: true
  });

  useEffect(() => {
    marketingService.getSettings('alert_configs').then((res) => {
      if (res.value) {
        setAlerts(res.value);
      }
    }).catch(() => {}).finally(() => setLoading(false));
  }, []);

  const getConditionIcon = (type: string) => {
    switch (type) {
      case 'isc_below': return <TrendingDown className="w-5 h-5 text-red-500" />;
      case 'isc_above': return <TrendingUp className="w-5 h-5 text-green-500" />;
      case 'sales_below': return <TrendingDown className="w-5 h-5 text-orange-500" />;
      case 'sales_above': return <TrendingUp className="w-5 h-5 text-blue-500" />;
      case 'dMinus_reached': return <Calendar className="w-5 h-5 text-purple-500" />;
      case 'critical_window': return <Target className="w-5 h-5 text-amber-500" />;
      default: return <AlertTriangle className="w-5 h-5 text-gray-500" />;
    }
  };

  const getConditionLabel = (condition: AlertCondition) => {
    switch (condition.type) {
      case 'isc_below': return `ISC abaixo de ${condition.value}`;
      case 'isc_above': return `ISC acima de ${condition.value}`;
      case 'sales_below': return `Vendas abaixo de ${condition.value}% do esperado`;
      case 'sales_above': return `Vendas acima de ${condition.value}% do esperado`;
      case 'dMinus_reached': return `Evento atinge D-${condition.value}`;
      case 'critical_window': return `Evento entra na janela D-${condition.value}`;
      default: return 'Condição desconhecida';
    }
  };

  const getChannelIcon = (type: string) => {
    switch (type) {
      case 'email': return <Mail className="w-4 h-4" />;
      case 'sms': return <Smartphone className="w-4 h-4" />;
      case 'push': return <Bell className="w-4 h-4" />;
      case 'slack': return <Hash className="w-4 h-4" />;
      default: return <MessageSquare className="w-4 h-4" />;
    }
  };

  const handleToggleActive = (id: string) => {
    const updatedAlerts = alerts.map(a => 
      a.id === id ? { ...a, isActive: !a.isActive } : a
    );
    setAlerts(updatedAlerts);
    marketingService.updateSettings('alert_configs', updatedAlerts).catch(() => {});
  };

  const handleDelete = (id: string) => {
    const updatedAlerts = alerts.filter(a => a.id !== id);
    setAlerts(updatedAlerts);
    marketingService.updateSettings('alert_configs', updatedAlerts).catch(() => {});
  };

  const handleToggleChannel = (alertId: string, channelIndex: number) => {
    const updatedAlerts = alerts.map(a => {
      if (a.id === alertId) {
        const newChannels = [...a.channels];
        newChannels[channelIndex] = { ...newChannels[channelIndex], isEnabled: !newChannels[channelIndex].isEnabled };
        return { ...a, channels: newChannels };
      }
      return a;
    });
    setAlerts(updatedAlerts);
    marketingService.updateSettings('alert_configs', updatedAlerts).catch(() => {});
  };

  const handleAddAlert = () => {
    if (newAlert.name && newAlert.description) {
      const existingIds = alerts.map(a => Number(a.id));
      const newId = String(existingIds.length > 0 ? Math.max(...existingIds) + 1 : 1);
      const updatedAlerts = [...alerts, {
        ...newAlert,
        id: newId,
        createdAt: new Date().toISOString().split('T')[0]
      } as AlertConfig];
      setAlerts(updatedAlerts);
      setNewAlert({
        name: '',
        description: '',
        condition: { type: 'isc_below', value: 35, comparison: 'less_than' },
        channels: [{ type: 'email', target: '', isEnabled: true }],
        isActive: true
      });
      setShowNewForm(false);
      marketingService.updateSettings('alert_configs', updatedAlerts).catch(() => {});
    }
  };

  const addChannelToNew = () => {
    setNewAlert({
      ...newAlert,
      channels: [...(newAlert.channels || []), { type: 'email', target: '', isEnabled: true }]
    });
  };

  const updateNewChannel = (index: number, field: keyof AlertChannel, value: string | boolean) => {
    const newChannels = [...(newAlert.channels || [])];
    newChannels[index] = { ...newChannels[index], [field]: value };
    setNewAlert({ ...newAlert, channels: newChannels });
  };

  const removeNewChannel = (index: number) => {
    const newChannels = [...(newAlert.channels || [])];
    newChannels.splice(index, 1);
    setNewAlert({ ...newAlert, channels: newChannels });
  };

  const conditionTypes = [
    { value: 'isc_below', label: 'ISC abaixo de' },
    { value: 'isc_above', label: 'ISC acima de' },
    { value: 'sales_below', label: 'Vendas abaixo de % esperado' },
    { value: 'sales_above', label: 'Vendas acima de % esperado' },
    { value: 'dMinus_reached', label: 'Evento atinge D-' },
    { value: 'critical_window', label: 'Janela crítica (D-)' }
  ];

  const channelTypes = [
    { value: 'email', label: 'E-mail' },
    { value: 'sms', label: 'SMS' },
    { value: 'push', label: 'Push Notification' },
    { value: 'slack', label: 'Slack' }
  ];

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
            Configuração de Alertas Automáticos
          </h2>
          <p className="text-gray-500 dark:text-gray-400 mt-1">
            Configure notificações automáticas para eventos importantes
          </p>
        </div>
        <button
          onClick={() => setShowNewForm(true)}
          className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors flex items-center gap-2"
        >
          <Plus className="w-4 h-4" />
          Novo Alerta
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="bg-blue-50 dark:bg-blue-900/20 rounded-xl p-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-blue-100 dark:bg-blue-900/40 rounded-lg">
              <Bell className="w-5 h-5 text-blue-600 dark:text-blue-400" />
            </div>
            <div>
              <p className="text-sm text-blue-600 dark:text-blue-400">Total de Alertas</p>
              <p className="text-2xl font-bold text-blue-800 dark:text-blue-200">{alerts.length}</p>
            </div>
          </div>
        </div>
        <div className="bg-green-50 dark:bg-green-900/20 rounded-xl p-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-green-100 dark:bg-green-900/40 rounded-lg">
              <Bell className="w-5 h-5 text-green-600 dark:text-green-400" />
            </div>
            <div>
              <p className="text-sm text-green-600 dark:text-green-400">Ativos</p>
              <p className="text-2xl font-bold text-green-800 dark:text-green-200">
                {alerts.filter(a => a.isActive).length}
              </p>
            </div>
          </div>
        </div>
        <div className="bg-red-50 dark:bg-red-900/20 rounded-xl p-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-red-100 dark:bg-red-900/40 rounded-lg">
              <TrendingDown className="w-5 h-5 text-red-600 dark:text-red-400" />
            </div>
            <div>
              <p className="text-sm text-red-600 dark:text-red-400">Alertas Críticos</p>
              <p className="text-2xl font-bold text-red-800 dark:text-red-200">
                {alerts.filter(a => a.condition.type === 'isc_below' || a.condition.type === 'critical_window').length}
              </p>
            </div>
          </div>
        </div>
        <div className="bg-purple-50 dark:bg-purple-900/20 rounded-xl p-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-purple-100 dark:bg-purple-900/40 rounded-lg">
              <Mail className="w-5 h-5 text-purple-600 dark:text-purple-400" />
            </div>
            <div>
              <p className="text-sm text-purple-600 dark:text-purple-400">Canais Ativos</p>
              <p className="text-2xl font-bold text-purple-800 dark:text-purple-200">
                {alerts.reduce((sum, a) => sum + a.channels.filter(c => c.isEnabled).length, 0)}
              </p>
            </div>
          </div>
        </div>
      </div>

      {showNewForm && (
        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Novo Alerta</h3>
          <div className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Nome</label>
                <input
                  type="text"
                  value={newAlert.name || ''}
                  onChange={(e) => setNewAlert({ ...newAlert, name: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                  placeholder="Nome do alerta"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Descrição</label>
                <input
                  type="text"
                  value={newAlert.description || ''}
                  onChange={(e) => setNewAlert({ ...newAlert, description: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                  placeholder="Descrição do alerta"
                />
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Condição</label>
                <select
                  value={newAlert.condition?.type || 'isc_below'}
                  onChange={(e) => setNewAlert({
                    ...newAlert,
                    condition: { ...newAlert.condition!, type: e.target.value as AlertCondition['type'] }
                  })}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                >
                  {conditionTypes.map(ct => (
                    <option key={ct.value} value={ct.value}>{ct.label}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Valor</label>
                <input
                  type="number"
                  step="0.01"
                  value={newAlert.condition?.value || 0}
                  onChange={(e) => setNewAlert({
                    ...newAlert,
                    condition: { ...newAlert.condition!, value: Number(e.target.value) }
                  })}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                />
              </div>
            </div>

            <div>
              <div className="flex items-center justify-between mb-2">
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">Canais de Notificação</label>
                <button
                  onClick={addChannelToNew}
                  className="text-sm text-blue-600 hover:text-blue-700 flex items-center gap-1"
                >
                  <Plus className="w-4 h-4" /> Adicionar Canal
                </button>
              </div>
              <div className="space-y-2">
                {(newAlert.channels || []).map((channel, index) => (
                  <div key={index} className="flex items-center gap-2">
                    <select
                      value={channel.type}
                      onChange={(e) => updateNewChannel(index, 'type', e.target.value)}
                      className="px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                    >
                      {channelTypes.map(ct => (
                        <option key={ct.value} value={ct.value}>{ct.label}</option>
                      ))}
                    </select>
                    <input
                      type="text"
                      value={channel.target}
                      onChange={(e) => updateNewChannel(index, 'target', e.target.value)}
                      placeholder={channel.type === 'email' ? 'email@empresa.com' : channel.type === 'slack' ? '#canal' : 'Destinatário'}
                      className="flex-1 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                    />
                    <button
                      onClick={() => removeNewChannel(index)}
                      className="p-2 text-red-600 hover:bg-red-100 dark:hover:bg-red-900/30 rounded-lg"
                    >
                      <X className="w-4 h-4" />
                    </button>
                  </div>
                ))}
              </div>
            </div>

            <div className="flex justify-end gap-2">
              <button
                onClick={() => setShowNewForm(false)}
                className="px-4 py-2 border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700"
              >
                Cancelar
              </button>
              <button
                onClick={handleAddAlert}
                className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
              >
                Criar Alerta
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="space-y-4">
        {alerts.map((alert) => (
          <div
            key={alert.id}
            className={`bg-white dark:bg-gray-800 rounded-xl border-2 p-4 transition-all ${
              alert.isActive
                ? 'border-gray-200 dark:border-gray-700'
                : 'border-gray-100 dark:border-gray-800 opacity-60'
            }`}
          >
            <div className="flex items-start justify-between">
              <div className="flex items-start gap-4">
                <div className="p-3 bg-gray-100 dark:bg-gray-700 rounded-lg">
                  {getConditionIcon(alert.condition.type)}
                </div>
                <div>
                  <h4 className="font-semibold text-gray-900 dark:text-white">{alert.name}</h4>
                  <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">{alert.description}</p>
                  <div className="mt-2">
                    <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium bg-gray-100 dark:bg-gray-700 text-gray-800 dark:text-gray-200">
                      {getConditionLabel(alert.condition)}
                    </span>
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => handleToggleActive(alert.id)}
                  className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                    alert.isActive ? 'bg-green-600' : 'bg-gray-300 dark:bg-gray-600'
                  }`}
                >
                  <span
                    className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                      alert.isActive ? 'translate-x-6' : 'translate-x-1'
                    }`}
                  />
                </button>
                <button
                  onClick={() => handleDelete(alert.id)}
                  className="p-2 text-red-600 hover:bg-red-100 dark:hover:bg-red-900/30 rounded-lg"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            </div>

            <div className="mt-4 pt-4 border-t border-gray-200 dark:border-gray-700">
              <p className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Canais de Notificação</p>
              <div className="flex flex-wrap gap-2">
                {alert.channels.map((channel, index) => (
                  <button
                    key={index}
                    onClick={() => handleToggleChannel(alert.id, index)}
                    className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm transition-all ${
                      channel.isEnabled
                        ? 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400'
                        : 'bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400'
                    }`}
                  >
                    {getChannelIcon(channel.type)}
                    <span>{channel.target}</span>
                    {channel.isEnabled && (
                      <span className="w-2 h-2 bg-green-500 rounded-full"></span>
                    )}
                  </button>
                ))}
              </div>
            </div>

            <div className="mt-3 text-xs text-gray-400">
              Criado em {new Date(alert.createdAt).toLocaleDateString('pt-BR')}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

export default AlertsSettings;
