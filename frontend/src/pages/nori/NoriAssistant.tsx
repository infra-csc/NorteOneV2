import React, { useState, useEffect } from 'react';
import { 
  ListTodo, 
  Plus, 
  Check, 
  Clock, 
  AlertTriangle,
  Trash2,
  Calendar,
  Sparkles,
  Play,
  CheckCircle2,
  User,
  Users,
  BarChart3,
  X,
  TrendingUp,
  TrendingDown,
  Minus
} from 'lucide-react';
import { tarefasService, Tarefa, TarefaCreate } from '../../services/api';
import NoriChat from '../../components/nori/NoriChat';
import noriAvatar from '@assets/Nori_1768273889454.png';

type StatusFilter = 'PENDENTE' | 'EM_ANDAMENTO' | 'CONCLUIDA' | 'TODAS' | 'DELEGADAS';
type DelegadasFilter = 'TODAS' | 'PENDENTE' | 'EM_ANDAMENTO' | 'CONCLUIDA';

interface AnalysisData {
  timestamp: string;
  events: Array<{
    name: string;
    location: string;
    category: string;
    dMinus: number;
    currentSales: number;
    salesGoal: number;
    isc: number;
    iscStatus: string;
  }>;
  analysis: string;
}

const NoriAssistant: React.FC = () => {
  const [tarefas, setTarefas] = useState<Tarefa[]>([]);
  const [resumo, setResumo] = useState<any>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isChatOpen, setIsChatOpen] = useState(false);
  const [showNewTask, setShowNewTask] = useState(false);
  const [activeTab, setActiveTab] = useState<StatusFilter>('PENDENTE');
  const [delegadasFilter, setDelegadasFilter] = useState<DelegadasFilter>('TODAS');
  const [showAnalysisModal, setShowAnalysisModal] = useState(false);
  const [selectedAnalysis, setSelectedAnalysis] = useState<AnalysisData | null>(null);
  const [newTask, setNewTask] = useState<TarefaCreate>({
    titulo: '',
    descricao: '',
    prioridade: 'MEDIA'
  });

  useEffect(() => {
    loadData();
  }, [activeTab, delegadasFilter]);

  const loadData = async () => {
    setIsLoading(true);
    try {
      let tarefasData;
      if (activeTab === 'DELEGADAS') {
        const allDelegadas = await tarefasService.getDelegadas();
        if (delegadasFilter === 'TODAS') {
          tarefasData = allDelegadas;
        } else {
          tarefasData = allDelegadas.filter((t: Tarefa) => t.status === delegadasFilter);
        }
      } else if (activeTab === 'TODAS') {
        tarefasData = await tarefasService.list();
      } else {
        tarefasData = await tarefasService.list(activeTab);
      }
      const resumoData = await tarefasService.getResumo();
      setTarefas(tarefasData);
      setResumo(resumoData);
    } catch (error) {
      console.error('Erro ao carregar dados:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const handleCreateTask = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTask.titulo.trim()) return;

    try {
      await tarefasService.create(newTask);
      setNewTask({ titulo: '', descricao: '', prioridade: 'MEDIA' });
      setShowNewTask(false);
      loadData();
    } catch (error) {
      console.error('Erro ao criar tarefa:', error);
    }
  };

  const handleConcluir = async (id: number) => {
    try {
      await tarefasService.concluir(id);
      loadData();
    } catch (error) {
      console.error('Erro ao concluir tarefa:', error);
    }
  };

  const handleIniciar = async (id: number) => {
    try {
      await tarefasService.update(id, { status: 'EM_ANDAMENTO' } as any);
      loadData();
    } catch (error) {
      console.error('Erro ao iniciar tarefa:', error);
    }
  };

  const handleDelete = async (id: number) => {
    if (!confirm('Deseja excluir esta tarefa?')) return;
    try {
      await tarefasService.delete(id);
      loadData();
    } catch (error) {
      console.error('Erro ao excluir tarefa:', error);
    }
  };

  const handleViewAnalysis = (tarefa: Tarefa) => {
    if (tarefa.dados_analise) {
      try {
        const analysisData = JSON.parse(tarefa.dados_analise) as AnalysisData;
        setSelectedAnalysis(analysisData);
        setShowAnalysisModal(true);
      } catch (error) {
        console.error('Erro ao parsear dados da análise:', error);
      }
    }
  };

  const getPrioridadeColor = (prioridade: string) => {
    switch (prioridade) {
      case 'URGENTE': return 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400';
      case 'ALTA': return 'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-400';
      case 'MEDIA': return 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400';
      default: return 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400';
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'CONCLUIDA': return 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400';
      case 'EM_ANDAMENTO': return 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400';
      case 'CANCELADA': return 'bg-gray-100 text-gray-800 dark:bg-gray-900/30 dark:text-gray-400';
      default: return 'bg-indigo-100 text-indigo-800 dark:bg-indigo-900/30 dark:text-indigo-400';
    }
  };

  const getStatusLabel = (status: string) => {
    switch (status) {
      case 'CONCLUIDA': return 'Concluída';
      case 'EM_ANDAMENTO': return 'Em Andamento';
      case 'CANCELADA': return 'Cancelada';
      case 'PENDENTE': return 'Pendente';
      default: return status;
    }
  };

  const delegadasFilterOptions: { id: DelegadasFilter; label: string }[] = [
    { id: 'TODAS', label: 'Todas' },
    { id: 'PENDENTE', label: 'Pendentes' },
    { id: 'EM_ANDAMENTO', label: 'Em Andamento' },
    { id: 'CONCLUIDA', label: 'Concluídas' },
  ];

  const tabs = [
    { id: 'PENDENTE' as StatusFilter, label: 'Pendentes', icon: ListTodo, count: resumo?.pendentes || 0 },
    { id: 'EM_ANDAMENTO' as StatusFilter, label: 'Em Andamento', icon: Play, count: resumo?.em_andamento || 0 },
    { id: 'CONCLUIDA' as StatusFilter, label: 'Concluídas', icon: CheckCircle2, count: resumo?.concluidas || 0 },
    { id: 'DELEGADAS' as StatusFilter, label: 'Delegadas', icon: Users, count: resumo?.delegadas_total || 0 },
    { id: 'TODAS' as StatusFilter, label: 'Todas', icon: ListTodo, count: resumo?.total || 0 },
  ];

  const getTabTitle = () => {
    switch (activeTab) {
      case 'PENDENTE': return 'Tarefas Pendentes';
      case 'EM_ANDAMENTO': return 'Tarefas em Andamento';
      case 'CONCLUIDA': return 'Tarefas Concluídas';
      case 'DELEGADAS': return 'Tarefas Delegadas';
      default: return 'Todas as Tarefas';
    }
  };

  return (
    <div className="min-h-screen">
      <div className="fixed inset-0 pointer-events-none overflow-hidden">
        <div className="absolute top-0 left-1/4 w-96 h-96 bg-indigo-500/10 rounded-full blur-3xl animate-pulse" />
        <div className="absolute bottom-0 right-1/4 w-96 h-96 bg-purple-500/10 rounded-full blur-3xl animate-pulse" style={{ animationDelay: '1s' }} />
      </div>

      <div className="relative z-10 space-y-8 p-6">
        <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
          <div>
            <div className="flex items-center gap-5">
              <div className="relative">
                <div className="w-20 h-20 rounded-full bg-gradient-to-br from-indigo-500 via-purple-500 to-pink-500 p-1 shadow-xl shadow-indigo-500/30">
                  <div className="w-full h-full rounded-full overflow-hidden bg-white dark:bg-gray-800">
                    <img src={noriAvatar} alt="Nori" className="w-full h-full object-cover scale-125" />
                  </div>
                </div>
                <span className="absolute bottom-1 right-1 w-4 h-4 bg-green-500 rounded-full border-2 border-white dark:border-gray-800 animate-pulse" />
              </div>
              <div>
                <h1 className="text-3xl font-bold bg-gradient-to-r from-indigo-600 to-purple-600 bg-clip-text text-transparent">
                  Nori
                </h1>
                <p className="text-gray-500 dark:text-gray-400">Seu Assistente Virtual</p>
              </div>
            </div>
          </div>
          <div className="flex gap-3">
            <button
              onClick={() => setShowNewTask(true)}
              className="flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-indigo-600 to-purple-600 text-white rounded-lg hover:from-indigo-700 hover:to-purple-700 transition-colors"
            >
              <Plus className="w-5 h-5" />
              Nova Tarefa
            </button>
            <button
              onClick={() => setIsChatOpen(true)}
              className="flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-green-500 to-emerald-500 text-white rounded-lg hover:from-green-600 hover:to-emerald-600 transition-colors"
            >
              Falar com Nori
            </button>
          </div>
        </div>

        {resumo && (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <div className="bg-white dark:bg-gray-800/50 backdrop-blur rounded-xl p-6 border border-gray-200/50 dark:border-gray-700/50">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-gray-500 dark:text-gray-400">Pendentes</p>
                  <p className="text-3xl font-bold text-indigo-600 dark:text-indigo-400">{resumo.pendentes}</p>
                </div>
                <div className="p-3 bg-indigo-100 dark:bg-indigo-900/30 rounded-lg">
                  <ListTodo className="w-6 h-6 text-indigo-600 dark:text-indigo-400" />
                </div>
              </div>
            </div>

            <div className="bg-white dark:bg-gray-800/50 backdrop-blur rounded-xl p-6 border border-gray-200/50 dark:border-gray-700/50">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-gray-500 dark:text-gray-400">Vencendo Hoje</p>
                  <p className="text-3xl font-bold text-amber-600 dark:text-amber-400">{resumo.vencendo_hoje}</p>
                </div>
                <div className="p-3 bg-amber-100 dark:bg-amber-900/30 rounded-lg">
                  <Clock className="w-6 h-6 text-amber-600 dark:text-amber-400" />
                </div>
              </div>
            </div>

            <div className="bg-white dark:bg-gray-800/50 backdrop-blur rounded-xl p-6 border border-gray-200/50 dark:border-gray-700/50">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-gray-500 dark:text-gray-400">Atrasadas</p>
                  <p className="text-3xl font-bold text-red-600 dark:text-red-400">{resumo.atrasadas}</p>
                </div>
                <div className="p-3 bg-red-100 dark:bg-red-900/30 rounded-lg">
                  <AlertTriangle className="w-6 h-6 text-red-600 dark:text-red-400" />
                </div>
              </div>
            </div>

            <div className="bg-white dark:bg-gray-800/50 backdrop-blur rounded-xl p-6 border border-gray-200/50 dark:border-gray-700/50">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-gray-500 dark:text-gray-400">Concluídas</p>
                  <p className="text-3xl font-bold text-green-600 dark:text-green-400">{resumo.concluidas}</p>
                </div>
                <div className="p-3 bg-green-100 dark:bg-green-900/30 rounded-lg">
                  <Check className="w-6 h-6 text-green-600 dark:text-green-400" />
                </div>
              </div>
            </div>
          </div>
        )}

        {showNewTask && (
          <div className="bg-white dark:bg-gray-800/50 backdrop-blur rounded-xl p-6 border border-gray-200/50 dark:border-gray-700/50">
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Nova Tarefa</h3>
            <form onSubmit={handleCreateTask} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Título</label>
                <input
                  type="text"
                  value={newTask.titulo}
                  onChange={(e) => setNewTask({ ...newTask, titulo: e.target.value })}
                  className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500"
                  placeholder="Digite o título da tarefa"
                  required
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Descrição</label>
                <textarea
                  value={newTask.descricao || ''}
                  onChange={(e) => setNewTask({ ...newTask, descricao: e.target.value })}
                  className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500"
                  placeholder="Descrição opcional"
                  rows={3}
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Prioridade</label>
                  <select
                    value={newTask.prioridade}
                    onChange={(e) => setNewTask({ ...newTask, prioridade: e.target.value as any })}
                    className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500"
                  >
                    <option value="BAIXA">Baixa</option>
                    <option value="MEDIA">Média</option>
                    <option value="ALTA">Alta</option>
                    <option value="URGENTE">Urgente</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Data de Vencimento</label>
                  <input
                    type="datetime-local"
                    value={newTask.data_vencimento || ''}
                    onChange={(e) => setNewTask({ ...newTask, data_vencimento: e.target.value })}
                    className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500"
                  />
                </div>
              </div>
              <div className="flex gap-3">
                <button
                  type="submit"
                  className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors"
                >
                  Criar Tarefa
                </button>
                <button
                  type="button"
                  onClick={() => setShowNewTask(false)}
                  className="px-4 py-2 bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-300 dark:hover:bg-gray-600 transition-colors"
                >
                  Cancelar
                </button>
              </div>
            </form>
          </div>
        )}

        <div className="bg-white dark:bg-gray-800/50 backdrop-blur rounded-xl border border-gray-200/50 dark:border-gray-700/50">
          <div className="border-b border-gray-200 dark:border-gray-700">
            <div className="flex overflow-x-auto">
              {tabs.map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 transition-colors whitespace-nowrap ${
                    activeTab === tab.id
                      ? 'border-indigo-600 text-indigo-600 dark:text-indigo-400 dark:border-indigo-400'
                      : 'border-transparent text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300'
                  }`}
                >
                  <tab.icon className="w-4 h-4" />
                  {tab.label}
                  <span className={`px-2 py-0.5 text-xs rounded-full ${
                    activeTab === tab.id
                      ? 'bg-indigo-100 dark:bg-indigo-900/30 text-indigo-600 dark:text-indigo-400'
                      : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400'
                  }`}>
                    {tab.count}
                  </span>
                </button>
              ))}
            </div>
          </div>

          <div className="p-4 border-b border-gray-200 dark:border-gray-700">
            <div className="flex items-center justify-between flex-wrap gap-3">
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white flex items-center gap-2">
                <ListTodo className="w-5 h-5" />
                {getTabTitle()}
              </h3>
              {activeTab === 'DELEGADAS' && (
                <div className="flex items-center gap-2">
                  <span className="text-sm text-gray-500 dark:text-gray-400">Filtrar:</span>
                  <div className="flex gap-1">
                    {delegadasFilterOptions.map((opt) => (
                      <button
                        key={opt.id}
                        onClick={() => setDelegadasFilter(opt.id)}
                        className={`px-3 py-1 text-xs font-medium rounded-full transition-colors ${
                          delegadasFilter === opt.id
                            ? 'bg-indigo-100 dark:bg-indigo-900/30 text-indigo-600 dark:text-indigo-400'
                            : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-600'
                        }`}
                      >
                        {opt.label}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
          
          <div className="divide-y divide-gray-200 dark:divide-gray-700">
            {isLoading ? (
              <div className="p-8 text-center">
                <div className="animate-spin w-8 h-8 border-4 border-indigo-500 border-t-transparent rounded-full mx-auto"></div>
                <p className="text-gray-500 mt-2">Carregando...</p>
              </div>
            ) : tarefas.length === 0 ? (
              <div className="p-8 text-center">
                <div className="w-20 h-20 mx-auto mb-3 rounded-full bg-gradient-to-br from-indigo-500/30 via-purple-500/30 to-pink-500/30 p-1 opacity-60">
                  <div className="w-full h-full rounded-full overflow-hidden bg-white dark:bg-gray-800">
                    <img src={noriAvatar} alt="Nori" className="w-full h-full object-cover scale-125" />
                  </div>
                </div>
                <p className="text-gray-500 dark:text-gray-400">
                  {activeTab === 'CONCLUIDA' ? 'Nenhuma tarefa concluída ainda!' : 'Nenhuma tarefa encontrada!'}
                </p>
                <p className="text-sm text-gray-400 mt-1">Use o Nori para criar novas tarefas</p>
              </div>
            ) : (
              tarefas.map((tarefa) => (
                <div 
                  key={tarefa.id} 
                  className={`p-4 hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors ${
                    tarefa.status === 'CONCLUIDA' ? 'opacity-75' : ''
                  }`}
                >
                  <div className="flex items-start gap-4">
                    {activeTab === 'DELEGADAS' ? (
                      <div 
                        className="mt-1 flex-shrink-0 relative group"
                        title={`Status: ${getStatusLabel(tarefa.status)}`}
                      >
                        <div className={`w-5 h-5 rounded-full flex items-center justify-center ${
                          tarefa.status === 'CONCLUIDA' 
                            ? 'bg-green-100 dark:bg-green-900/30' 
                            : tarefa.status === 'EM_ANDAMENTO'
                            ? 'bg-blue-100 dark:bg-blue-900/30'
                            : 'bg-indigo-100 dark:bg-indigo-900/30'
                        }`}>
                          {tarefa.status === 'CONCLUIDA' ? (
                            <Check className="w-3 h-3 text-green-600 dark:text-green-400" />
                          ) : tarefa.status === 'EM_ANDAMENTO' ? (
                            <Play className="w-3 h-3 text-blue-600 dark:text-blue-400" />
                          ) : (
                            <Clock className="w-3 h-3 text-indigo-600 dark:text-indigo-400" />
                          )}
                        </div>
                        <div className="absolute left-full ml-2 top-1/2 -translate-y-1/2 px-2 py-1 bg-gray-900 dark:bg-gray-700 text-white text-xs rounded opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap z-10 pointer-events-none">
                          {getStatusLabel(tarefa.status)}
                        </div>
                      </div>
                    ) : tarefa.status !== 'CONCLUIDA' && tarefa.status !== 'CANCELADA' ? (
                      <button
                        onClick={() => handleConcluir(tarefa.id)}
                        className="mt-1 w-5 h-5 border-2 border-gray-300 dark:border-gray-600 rounded hover:border-green-500 hover:bg-green-50 dark:hover:bg-green-900/20 transition-colors flex-shrink-0"
                        title="Marcar como concluída"
                      />
                    ) : (
                      <div className="mt-1 w-5 h-5 flex-shrink-0">
                        <CheckCircle2 className="w-5 h-5 text-green-500" />
                      </div>
                    )}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1 flex-wrap">
                        <p className={`font-medium ${
                          tarefa.status === 'CONCLUIDA' 
                            ? 'text-gray-500 dark:text-gray-400 line-through' 
                            : 'text-gray-900 dark:text-white'
                        }`}>
                          {tarefa.titulo}
                        </p>
                        <span className={`px-2 py-0.5 text-xs font-medium rounded-full ${getPrioridadeColor(tarefa.prioridade)}`}>
                          {tarefa.prioridade}
                        </span>
                        {activeTab === 'TODAS' && (
                          <span className={`px-2 py-0.5 text-xs font-medium rounded-full ${getStatusColor(tarefa.status)}`}>
                            {tarefa.status.replace('_', ' ')}
                          </span>
                        )}
                        {tarefa.criado_por_nori && (
                          <span className="px-2 py-0.5 text-xs font-medium rounded-full bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-400">
                            <Sparkles className="w-3 h-3 inline mr-1" />
                            Nori
                          </span>
                        )}
                      </div>
                      {tarefa.descricao && (
                        <p className={`text-sm truncate ${
                          tarefa.status === 'CONCLUIDA'
                            ? 'text-gray-400 dark:text-gray-500'
                            : 'text-gray-500 dark:text-gray-400'
                        }`}>
                          {tarefa.descricao}
                        </p>
                      )}
                      <div className="flex items-center gap-3 mt-2 flex-wrap">
                        {activeTab !== 'DELEGADAS' && tarefa.usuario && tarefa.responsavel && tarefa.usuario.id !== tarefa.responsavel.id && (
                          <span className="text-xs px-2 py-1 bg-purple-50 dark:bg-purple-900/20 text-purple-700 dark:text-purple-300 rounded-full flex items-center gap-1">
                            <User className="w-3 h-3" />
                            Atribuída por @{tarefa.usuario.nome}
                          </span>
                        )}
                        {activeTab === 'DELEGADAS' && tarefa.responsavel && (
                          <span className="text-xs px-2 py-1 bg-blue-50 dark:bg-blue-900/20 text-blue-700 dark:text-blue-300 rounded-full flex items-center gap-1">
                            <Users className="w-3 h-3" />
                            Delegada para: @{tarefa.responsavel.nome}
                          </span>
                        )}
                        {activeTab !== 'DELEGADAS' && tarefa.responsavel && (
                          <span className="text-xs px-2 py-1 bg-blue-50 dark:bg-blue-900/20 text-blue-700 dark:text-blue-300 rounded-full flex items-center gap-1">
                            <User className="w-3 h-3" />
                            Para: @{tarefa.responsavel.nome}
                          </span>
                        )}
                        {tarefa.created_at && (
                          <span className="text-xs text-gray-400 flex items-center gap-1">
                            <Clock className="w-3 h-3" />
                            Criada em {new Date(tarefa.created_at).toLocaleDateString('pt-BR')}
                          </span>
                        )}
                        {tarefa.data_vencimento && (
                          <span className="text-xs text-amber-500 flex items-center gap-1">
                            <Calendar className="w-3 h-3" />
                            Vence em {new Date(tarefa.data_vencimento).toLocaleString('pt-BR')}
                          </span>
                        )}
                        {tarefa.status === 'CONCLUIDA' && tarefa.updated_at && (
                          <span className="text-xs text-green-500 flex items-center gap-1">
                            <Check className="w-3 h-3" />
                            Concluída em {new Date(tarefa.updated_at).toLocaleString('pt-BR')}
                          </span>
                        )}
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      {tarefa.dados_analise && (
                        <button
                          onClick={() => handleViewAnalysis(tarefa)}
                          className="p-2 text-purple-400 hover:text-purple-600 transition-colors"
                          title="Ver análise anexada"
                        >
                          <BarChart3 className="w-4 h-4" />
                        </button>
                      )}
                      {activeTab !== 'DELEGADAS' && (
                        <>
                          {tarefa.status === 'PENDENTE' && (
                            <button
                              onClick={() => handleIniciar(tarefa.id)}
                              className="p-2 text-gray-400 hover:text-blue-500 transition-colors"
                              title="Iniciar tarefa"
                            >
                              <Play className="w-4 h-4" />
                            </button>
                          )}
                          {tarefa.status !== 'CONCLUIDA' && (
                            <button
                              onClick={() => handleDelete(tarefa.id)}
                              className="p-2 text-gray-400 hover:text-red-500 transition-colors"
                              title="Excluir tarefa"
                            >
                              <Trash2 className="w-4 h-4" />
                            </button>
                          )}
                        </>
                      )}
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      <NoriChat 
        isOpen={isChatOpen} 
        onClose={() => setIsChatOpen(false)} 
        onTaskCreated={loadData}
      />

      {showAnalysisModal && selectedAnalysis && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
          <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-2xl w-full max-w-4xl max-h-[90vh] flex flex-col overflow-hidden border border-gray-200 dark:border-gray-700">
            <div className="bg-gradient-to-r from-purple-600 to-indigo-600 p-4 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <BarChart3 className="w-6 h-6 text-white" />
                <div>
                  <h2 className="text-lg font-semibold text-white">Análise de Eventos</h2>
                  <p className="text-sm text-purple-200">
                    Gerada em {new Date(selectedAnalysis.timestamp).toLocaleString('pt-BR')}
                  </p>
                </div>
              </div>
              <button
                onClick={() => setShowAnalysisModal(false)}
                className="p-2 text-white/80 hover:text-white transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            
            <div className="flex-1 overflow-auto p-6 space-y-6">
              <div>
                <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
                  <BarChart3 className="w-5 h-5" />
                  Eventos no Momento da Análise
                </h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {selectedAnalysis.events.map((event, idx) => {
                    const StatusIcon = event.iscStatus === 'accelerating' ? TrendingUp : 
                                       event.iscStatus === 'stable' ? Minus : TrendingDown;
                    const statusColor = event.iscStatus === 'accelerating' ? 'text-green-500 border-green-500 bg-green-50 dark:bg-green-900/20' : 
                                        event.iscStatus === 'stable' ? 'text-yellow-500 border-yellow-500 bg-yellow-50 dark:bg-yellow-900/20' : 
                                        'text-red-500 border-red-500 bg-red-50 dark:bg-red-900/20';
                    const progress = (event.currentSales / event.salesGoal) * 100;
                    
                    return (
                      <div key={idx} className={`border-l-4 rounded-lg p-4 ${statusColor}`}>
                        <div className="flex items-center justify-between mb-2">
                          <div className="flex items-center gap-2">
                            <StatusIcon className="w-4 h-4" />
                            <span className="font-semibold text-gray-900 dark:text-white">{event.name}</span>
                          </div>
                          <span className="font-bold">ISC: {event.isc.toFixed(1)}</span>
                        </div>
                        <div className="text-sm text-gray-600 dark:text-gray-400 mb-2">
                          {event.location} - {event.category}
                        </div>
                        <div className="flex items-center gap-4 text-xs">
                          <span>D-{event.dMinus}</span>
                          <div className="flex-1">
                            <div className="h-2 bg-gray-200 dark:bg-gray-600 rounded-full overflow-hidden">
                              <div 
                                className={`h-full rounded-full ${
                                  event.iscStatus === 'accelerating' ? 'bg-green-500' : 
                                  event.iscStatus === 'stable' ? 'bg-yellow-500' : 'bg-red-500'
                                }`}
                                style={{ width: `${Math.min(progress, 100)}%` }}
                              />
                            </div>
                          </div>
                          <span>{event.currentSales.toLocaleString()}/{event.salesGoal.toLocaleString()}</span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
              
              <div>
                <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
                  <Sparkles className="w-5 h-5" />
                  Análise da Nori
                </h3>
                <div className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-4 prose dark:prose-invert max-w-none">
                  <div className="whitespace-pre-wrap text-gray-700 dark:text-gray-300">
                    {selectedAnalysis.analysis}
                  </div>
                </div>
              </div>
            </div>
            
            <div className="border-t border-gray-200 dark:border-gray-700 p-4 flex justify-end">
              <button
                onClick={() => setShowAnalysisModal(false)}
                className="px-4 py-2 bg-gradient-to-r from-indigo-600 to-purple-600 text-white rounded-lg hover:from-indigo-700 hover:to-purple-700 transition-colors"
              >
                Fechar
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default NoriAssistant;
