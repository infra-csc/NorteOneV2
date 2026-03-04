import React, { useEffect, useState, useCallback } from 'react';
import { useTheme } from '../../context/ThemeContext';
import { adminService } from '../../services/api';
import { Monitor, RefreshCw, Users, UserCheck, Clock, Filter } from 'lucide-react';

interface UserActivity {
  id: number;
  nome: string;
  email: string;
  perfil_acesso: string | null;
  status: 'online' | 'ausente' | 'offline';
  last_activity: string | null;
}

interface ActivitySummary {
  total_usuarios: number;
  online: number;
  ausentes: number;
  ativos_hoje: number;
}

interface ActivityResponse {
  resumo: ActivitySummary;
  usuarios: UserActivity[];
}

const STATUS_CONFIG = {
  online: { label: 'Online', color: 'bg-emerald-500', textColor: 'text-emerald-400', bgCard: 'bg-emerald-500/10', border: 'border-emerald-500/30' },
  ausente: { label: 'Ausente', color: 'bg-amber-500', textColor: 'text-amber-400', bgCard: 'bg-amber-500/10', border: 'border-amber-500/30' },
  offline: { label: 'Offline', color: 'bg-gray-500', textColor: 'text-gray-400', bgCard: 'bg-gray-500/10', border: 'border-gray-500/30' },
};

function formatTimeAgo(isoDate: string | null): string {
  if (!isoDate) return 'Nunca acessou';
  const now = new Date();
  const date = new Date(isoDate + 'Z');
  const diffMs = now.getTime() - date.getTime();
  const diffSec = Math.floor(diffMs / 1000);
  if (diffSec < 60) return 'Agora';
  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return `há ${diffMin} min`;
  const diffHours = Math.floor(diffMin / 60);
  if (diffHours < 24) return `há ${diffHours}h`;
  const diffDays = Math.floor(diffHours / 24);
  if (diffDays === 1) return 'há 1 dia';
  return `há ${diffDays} dias`;
}

const MonitoramentoUsuarios: React.FC = () => {
  const { isDark } = useTheme();
  const [data, setData] = useState<ActivityResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<string>('todos');
  const [lastRefresh, setLastRefresh] = useState<Date>(new Date());

  const fetchData = useCallback(async () => {
    try {
      const result = await adminService.getUserActivity();
      setData(result);
      setError(null);
      setLastRefresh(new Date());
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Erro ao carregar dados de monitoramento');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, [fetchData]);

  const filteredUsers = data?.usuarios.filter(u => {
    if (statusFilter === 'todos') return true;
    return u.status === statusFilter;
  }) || [];

  const cardBase = isDark
    ? 'bg-gray-800/50 backdrop-blur-sm border border-gray-700/50'
    : 'bg-white/80 backdrop-blur-sm border border-gray-200 shadow-sm';

  const textPrimary = isDark ? 'text-white' : 'text-gray-900';
  const textSecondary = isDark ? 'text-gray-400' : 'text-gray-500';
  const headerBg = isDark ? 'bg-gray-700/30' : 'bg-gray-50';

  return (
    <div className="p-4 md:p-6 space-y-6">
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-blue-500/10 rounded-lg">
            <Monitor className="w-6 h-6 text-blue-400" />
          </div>
          <div>
            <h1 className={`text-2xl font-bold ${textPrimary}`}>Monitoramento de Usuários</h1>
            <p className={`text-sm ${textSecondary}`}>
              Atualizado {formatTimeAgo(lastRefresh.toISOString().replace('Z', ''))} · Auto-refresh 30s
            </p>
          </div>
        </div>
        <button
          onClick={() => { setLoading(true); fetchData(); }}
          disabled={loading}
          className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all
            ${isDark ? 'bg-blue-600 hover:bg-blue-500 text-white' : 'bg-blue-500 hover:bg-blue-600 text-white'}
            disabled:opacity-50`}
        >
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          Atualizar
        </button>
      </div>

      {error && (
        <div className="p-4 bg-red-500/10 border border-red-500/30 rounded-lg text-red-400 text-sm">
          {error}
        </div>
      )}

      {data && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <div className={`${cardBase} rounded-xl p-4`}>
            <div className="flex items-center gap-3">
              <div className="p-2 bg-blue-500/10 rounded-lg">
                <Users className="w-5 h-5 text-blue-400" />
              </div>
              <div>
                <p className={`text-sm ${textSecondary}`}>Total Ativos</p>
                <p className={`text-2xl font-bold ${textPrimary}`}>{data.resumo.total_usuarios}</p>
              </div>
            </div>
          </div>
          <div className={`${cardBase} rounded-xl p-4`}>
            <div className="flex items-center gap-3">
              <div className="p-2 bg-emerald-500/10 rounded-lg">
                <UserCheck className="w-5 h-5 text-emerald-400" />
              </div>
              <div>
                <p className={`text-sm ${textSecondary}`}>Online Agora</p>
                <p className="text-2xl font-bold text-emerald-400">{data.resumo.online}</p>
              </div>
            </div>
          </div>
          <div className={`${cardBase} rounded-xl p-4`}>
            <div className="flex items-center gap-3">
              <div className="p-2 bg-amber-500/10 rounded-lg">
                <Clock className="w-5 h-5 text-amber-400" />
              </div>
              <div>
                <p className={`text-sm ${textSecondary}`}>Ausentes</p>
                <p className="text-2xl font-bold text-amber-400">{data.resumo.ausentes}</p>
              </div>
            </div>
          </div>
          <div className={`${cardBase} rounded-xl p-4`}>
            <div className="flex items-center gap-3">
              <div className="p-2 bg-purple-500/10 rounded-lg">
                <Users className="w-5 h-5 text-purple-400" />
              </div>
              <div>
                <p className={`text-sm ${textSecondary}`}>Ativos Hoje</p>
                <p className="text-2xl font-bold text-purple-400">{data.resumo.ativos_hoje}</p>
              </div>
            </div>
          </div>
        </div>
      )}

      <div className={`${cardBase} rounded-xl overflow-hidden`}>
        <div className={`px-4 py-3 ${headerBg} flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3`}>
          <h2 className={`text-sm font-semibold ${textPrimary}`}>Usuários</h2>
          <div className="flex items-center gap-2">
            <Filter className={`w-4 h-4 ${textSecondary}`} />
            <select
              value={statusFilter}
              onChange={e => setStatusFilter(e.target.value)}
              className={`text-sm rounded-lg px-3 py-1.5 border outline-none
                ${isDark
                  ? 'bg-gray-700 border-gray-600 text-white'
                  : 'bg-white border-gray-300 text-gray-900'
                }`}
            >
              <option value="todos">Todos</option>
              <option value="online">Online</option>
              <option value="ausente">Ausente</option>
              <option value="offline">Offline</option>
            </select>
          </div>
        </div>

        {loading && !data ? (
          <div className="p-12 flex justify-center">
            <RefreshCw className="w-8 h-8 text-blue-400 animate-spin" />
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className={headerBg}>
                  <th className={`text-left text-xs font-medium ${textSecondary} uppercase tracking-wider px-4 py-3`}>Usuário</th>
                  <th className={`text-left text-xs font-medium ${textSecondary} uppercase tracking-wider px-4 py-3 hidden sm:table-cell`}>Email</th>
                  <th className={`text-left text-xs font-medium ${textSecondary} uppercase tracking-wider px-4 py-3 hidden md:table-cell`}>Perfil</th>
                  <th className={`text-center text-xs font-medium ${textSecondary} uppercase tracking-wider px-4 py-3`}>Status</th>
                  <th className={`text-right text-xs font-medium ${textSecondary} uppercase tracking-wider px-4 py-3`}>Último Acesso</th>
                </tr>
              </thead>
              <tbody className={`divide-y ${isDark ? 'divide-gray-700/50' : 'divide-gray-100'}`}>
                {filteredUsers.map(user => {
                  const cfg = STATUS_CONFIG[user.status];
                  return (
                    <tr
                      key={user.id}
                      className={`transition-colors ${isDark ? 'hover:bg-gray-700/30' : 'hover:bg-gray-50'}`}
                    >
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-3">
                          <div className="relative">
                            <div className={`w-9 h-9 rounded-full flex items-center justify-center text-sm font-medium
                              ${isDark ? 'bg-gray-700 text-gray-300' : 'bg-gray-200 text-gray-600'}`}>
                              {user.nome.split(' ').map(n => n[0]).slice(0, 2).join('').toUpperCase()}
                            </div>
                            <span className={`absolute -bottom-0.5 -right-0.5 w-3 h-3 rounded-full border-2 ${isDark ? 'border-gray-800' : 'border-white'} ${cfg.color}`} />
                          </div>
                          <span className={`font-medium text-sm ${textPrimary}`}>{user.nome}</span>
                        </div>
                      </td>
                      <td className={`px-4 py-3 text-sm hidden sm:table-cell ${textSecondary}`}>{user.email}</td>
                      <td className={`px-4 py-3 text-sm hidden md:table-cell ${textSecondary}`}>{user.perfil_acesso || '—'}</td>
                      <td className="px-4 py-3 text-center">
                        <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium ${cfg.bgCard} ${cfg.textColor} border ${cfg.border}`}>
                          <span className={`w-1.5 h-1.5 rounded-full ${cfg.color}`} />
                          {cfg.label}
                        </span>
                      </td>
                      <td className={`px-4 py-3 text-right text-sm ${textSecondary}`}>
                        {formatTimeAgo(user.last_activity)}
                      </td>
                    </tr>
                  );
                })}
                {filteredUsers.length === 0 && (
                  <tr>
                    <td colSpan={5} className={`px-4 py-8 text-center text-sm ${textSecondary}`}>
                      Nenhum usuário encontrado com este filtro
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};

export default MonitoramentoUsuarios;
