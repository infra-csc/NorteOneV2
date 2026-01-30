import React, { useState, useEffect } from 'react';
import { 
  ListTodo, 
  Plus, 
  Check, 
  Clock, 
  AlertTriangle,
  Trash2,
  Calendar,
  Sparkles
} from 'lucide-react';
import { tarefasService, Tarefa, TarefaCreate } from '../../services/api';
import NoriChat from '../../components/nori/NoriChat';
import noriAvatar from '@assets/Nori_1768273889454.png';

const NoriAssistant: React.FC = () => {
  const [tarefas, setTarefas] = useState<Tarefa[]>([]);
  const [resumo, setResumo] = useState<any>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isChatOpen, setIsChatOpen] = useState(false);
  const [showNewTask, setShowNewTask] = useState(false);
  const [newTask, setNewTask] = useState<TarefaCreate>({
    titulo: '',
    descricao: '',
    prioridade: 'MEDIA'
  });

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    setIsLoading(true);
    try {
      const [tarefasData, resumoData] = await Promise.all([
        tarefasService.getPendentes(),
        tarefasService.getResumo()
      ]);
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

  const handleDelete = async (id: number) => {
    if (!confirm('Deseja excluir esta tarefa?')) return;
    try {
      await tarefasService.delete(id);
      loadData();
    } catch (error) {
      console.error('Erro ao excluir tarefa:', error);
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

  return (
    <div className="min-h-screen">
      <div className="fixed inset-0 pointer-events-none overflow-hidden">
        <div className="absolute top-0 left-1/4 w-96 h-96 bg-indigo-500/10 rounded-full blur-3xl animate-pulse" />
        <div className="absolute bottom-0 right-1/4 w-96 h-96 bg-purple-500/10 rounded-full blur-3xl animate-pulse" style={{ animationDelay: '1s' }} />
      </div>

      <div className="relative z-10 space-y-8 p-6">
        <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
          <div>
            <div className="flex items-center gap-4">
              <div className="w-16 h-16 rounded-full overflow-hidden shadow-lg shadow-indigo-500/30 border-2 border-indigo-400 bg-gray-900">
                <img src={noriAvatar} alt="Nori" className="w-[140%] h-[140%] object-cover object-center ml-[-20%] mt-[-10%]" />
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
              <div className="w-6 h-6 rounded-full overflow-hidden bg-gray-900">
                <img src={noriAvatar} alt="Nori" className="w-[140%] h-[140%] object-cover object-center ml-[-20%] mt-[-10%]" />
              </div>
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
          <div className="p-4 border-b border-gray-200 dark:border-gray-700">
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white flex items-center gap-2">
              <ListTodo className="w-5 h-5" />
              Tarefas Pendentes
            </h3>
          </div>
          <div className="divide-y divide-gray-200 dark:divide-gray-700">
            {isLoading ? (
              <div className="p-8 text-center">
                <div className="animate-spin w-8 h-8 border-4 border-indigo-500 border-t-transparent rounded-full mx-auto"></div>
                <p className="text-gray-500 mt-2">Carregando...</p>
              </div>
            ) : tarefas.length === 0 ? (
              <div className="p-8 text-center">
                <div className="w-16 h-16 mx-auto mb-3 rounded-full overflow-hidden opacity-60 bg-gray-900">
                  <img src={noriAvatar} alt="Nori" className="w-[140%] h-[140%] object-cover object-center ml-[-20%] mt-[-10%]" />
                </div>
                <p className="text-gray-500 dark:text-gray-400">Nenhuma tarefa pendente!</p>
                <p className="text-sm text-gray-400 mt-1">Use o Nori para criar novas tarefas</p>
              </div>
            ) : (
              tarefas.map((tarefa) => (
                <div key={tarefa.id} className="p-4 hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors">
                  <div className="flex items-start gap-4">
                    <button
                      onClick={() => handleConcluir(tarefa.id)}
                      className="mt-1 w-5 h-5 border-2 border-gray-300 dark:border-gray-600 rounded hover:border-green-500 hover:bg-green-50 dark:hover:bg-green-900/20 transition-colors flex-shrink-0"
                    />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <p className="font-medium text-gray-900 dark:text-white">{tarefa.titulo}</p>
                        <span className={`px-2 py-0.5 text-xs font-medium rounded-full ${getPrioridadeColor(tarefa.prioridade)}`}>
                          {tarefa.prioridade}
                        </span>
                        {tarefa.criado_por_nori && (
                          <span className="px-2 py-0.5 text-xs font-medium rounded-full bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-400">
                            <Sparkles className="w-3 h-3 inline mr-1" />
                            Nori
                          </span>
                        )}
                      </div>
                      {tarefa.descricao && (
                        <p className="text-sm text-gray-500 dark:text-gray-400 truncate">{tarefa.descricao}</p>
                      )}
                      <div className="flex items-center gap-2 mt-1 flex-wrap">
                        {tarefa.responsavel && (
                          <span className="text-xs px-2 py-0.5 bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 rounded-full">
                            @{tarefa.responsavel.nome}
                          </span>
                        )}
                        {tarefa.data_vencimento && (
                          <span className="text-xs text-gray-400 flex items-center gap-1">
                            <Calendar className="w-3 h-3" />
                            {new Date(tarefa.data_vencimento).toLocaleString('pt-BR')}
                          </span>
                        )}
                      </div>
                    </div>
                    <button
                      onClick={() => handleDelete(tarefa.id)}
                      className="p-2 text-gray-400 hover:text-red-500 transition-colors"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
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
    </div>
  );
};

export default NoriAssistant;
