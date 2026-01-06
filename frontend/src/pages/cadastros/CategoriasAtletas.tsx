import React, { useEffect, useState } from 'react';
import { categoriasAtletasService } from '../../services/api';
import { CategoriaAtleta } from '../../types';
import { useTheme } from '../../context/ThemeContext';
import { Plus, Pencil, X, Check, Users, Sparkles, Target, DollarSign, Activity } from 'lucide-react';

const Categorias: React.FC = () => {
  const { isDark } = useTheme();
  const [categorias, setCategorias] = useState<CategoriaAtleta[]>([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [editItem, setEditItem] = useState<CategoriaAtleta | null>(null);
  const [form, setForm] = useState({
    codigo: '', nome: '', faixa_etaria: '', genero: 'MASCULINO', modalidade: 'CORRIDA',
    is_pcd: false, valor_inscricao_padrao: '', custo_kit_padrao: ''
  });

  const loadData = async () => {
    setLoading(true);
    try {
      const data = await categoriasAtletasService.list();
      setCategorias(data);
    } catch (error) {
      console.error('Erro:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadData(); }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const payload = {
        ...form,
        valor_inscricao_padrao: form.valor_inscricao_padrao ? Number(form.valor_inscricao_padrao) : null,
        custo_kit_padrao: form.custo_kit_padrao ? Number(form.custo_kit_padrao) : null
      };
      if (editItem) {
        await categoriasAtletasService.update(editItem.id, payload);
      } else {
        await categoriasAtletasService.create(payload);
      }
      setShowModal(false);
      loadData();
    } catch (error: any) {
      alert(error.response?.data?.detail || 'Erro');
    }
  };

  const handleEdit = (item: CategoriaAtleta) => {
    setEditItem(item);
    setForm({
      codigo: item.codigo, nome: item.nome, faixa_etaria: item.faixa_etaria || '',
      genero: item.genero || 'MASCULINO', modalidade: item.modalidade || 'CORRIDA',
      is_pcd: item.is_pcd, valor_inscricao_padrao: item.valor_inscricao_padrao?.toString() || '',
      custo_kit_padrao: item.custo_kit_padrao?.toString() || ''
    });
    setShowModal(true);
  };

  const openNewModal = () => {
    setEditItem(null);
    setForm({
      codigo: '', nome: '', faixa_etaria: '', genero: 'MASCULINO', modalidade: 'CORRIDA',
      is_pcd: false, valor_inscricao_padrao: '', custo_kit_padrao: ''
    });
    setShowModal(true);
  };

  const totalCategorias = categorias.length;
  const pcdCount = categorias.filter(c => c.is_pcd).length;
  const modalidades = [...new Set(categorias.map(c => c.modalidade).filter(Boolean))].length;
  const generos = [...new Set(categorias.map(c => c.genero).filter(Boolean))].length;

  const modalidadeColors: Record<string, { bg: string; text: string; border: string }> = {
    'CORRIDA': { bg: 'from-orange-500 to-red-600', text: 'text-orange-400', border: 'border-orange-500/30' },
    'CICLISMO': { bg: 'from-cyan-500 to-blue-600', text: 'text-cyan-400', border: 'border-cyan-500/30' },
    'NATACAO': { bg: 'from-blue-400 to-indigo-600', text: 'text-blue-400', border: 'border-blue-500/30' },
    'TRIATHLON': { bg: 'from-purple-500 to-pink-600', text: 'text-purple-400', border: 'border-purple-500/30' },
  };

  return (
    <div className="min-h-screen">
      <div className="fixed inset-0 pointer-events-none overflow-hidden">
        <div className="absolute top-0 left-1/4 w-96 h-96 bg-violet-500/10 rounded-full blur-3xl animate-pulse" />
        <div className="absolute bottom-0 right-1/4 w-96 h-96 bg-purple-500/10 rounded-full blur-3xl animate-pulse" style={{ animationDelay: '1s' }} />
        <div className="absolute top-1/2 left-1/2 w-64 h-64 bg-pink-500/5 rounded-full blur-3xl animate-pulse" style={{ animationDelay: '2s' }} />
      </div>

      <div className="relative z-10 space-y-8 p-6">
        <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
          <div>
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-xl bg-gradient-to-br from-violet-500 to-purple-500 shadow-lg shadow-violet-500/30">
                <Users className="w-6 h-6 text-white" />
              </div>
              <div>
                <h1 className={`text-3xl font-black tracking-tight ${isDark ? 'text-white' : 'text-gray-900'}`}>
                  Categorias de
                  <span className="bg-gradient-to-r from-violet-400 via-purple-500 to-pink-500 bg-clip-text text-transparent"> Atletas</span>
                </h1>
                <p className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>
                  Gerencie as categorias dos atletas
                </p>
              </div>
            </div>
          </div>

          <button 
            onClick={openNewModal} 
            className="group relative px-6 py-3 bg-gradient-to-r from-violet-600 via-purple-600 to-pink-500 text-white rounded-2xl font-semibold shadow-xl shadow-violet-500/30 hover:shadow-violet-500/50 transition-all duration-300 hover:scale-105 overflow-hidden"
          >
            <div className="absolute inset-0 bg-gradient-to-r from-violet-400 via-purple-400 to-pink-400 opacity-0 group-hover:opacity-100 transition-opacity duration-300" />
            <span className="relative flex items-center gap-2">
              <Plus className="w-5 h-5" />
              Nova Categoria
              <Sparkles className="w-4 h-4" />
            </span>
          </button>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className={`relative overflow-hidden rounded-2xl p-4 ${isDark ? 'bg-gray-800/50 backdrop-blur-xl border border-gray-700/50' : 'bg-white/70 backdrop-blur-xl border border-gray-200'}`}>
            <div className="absolute top-0 right-0 w-20 h-20 bg-gradient-to-br from-violet-500/20 to-transparent rounded-full blur-2xl" />
            <div className="relative">
              <div className="flex items-center gap-2 mb-2">
                <div className="p-1.5 rounded-lg bg-violet-500/20">
                  <Target className="w-4 h-4 text-violet-400" />
                </div>
                <span className={`text-xs font-medium ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>Total Categorias</span>
              </div>
              <p className={`text-3xl font-black ${isDark ? 'text-white' : 'text-gray-900'}`}>{totalCategorias}</p>
            </div>
          </div>

          <div className={`relative overflow-hidden rounded-2xl p-4 ${isDark ? 'bg-gray-800/50 backdrop-blur-xl border border-gray-700/50' : 'bg-white/70 backdrop-blur-xl border border-gray-200'}`}>
            <div className="absolute top-0 right-0 w-20 h-20 bg-gradient-to-br from-blue-500/20 to-transparent rounded-full blur-2xl" />
            <div className="relative">
              <div className="flex items-center gap-2 mb-2">
                <div className="p-1.5 rounded-lg bg-blue-500/20">
                  <Users className="w-4 h-4 text-blue-400" />
                </div>
                <span className={`text-xs font-medium ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>Categorias PCD</span>
              </div>
              <p className={`text-3xl font-black ${isDark ? 'text-white' : 'text-gray-900'}`}>{pcdCount}</p>
            </div>
          </div>

          <div className={`relative overflow-hidden rounded-2xl p-4 ${isDark ? 'bg-gray-800/50 backdrop-blur-xl border border-gray-700/50' : 'bg-white/70 backdrop-blur-xl border border-gray-200'}`}>
            <div className="absolute top-0 right-0 w-20 h-20 bg-gradient-to-br from-orange-500/20 to-transparent rounded-full blur-2xl" />
            <div className="relative">
              <div className="flex items-center gap-2 mb-2">
                <div className="p-1.5 rounded-lg bg-orange-500/20">
                  <Activity className="w-4 h-4 text-orange-400" />
                </div>
                <span className={`text-xs font-medium ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>Modalidades</span>
              </div>
              <p className={`text-3xl font-black ${isDark ? 'text-white' : 'text-gray-900'}`}>{modalidades}</p>
            </div>
          </div>

          <div className={`relative overflow-hidden rounded-2xl p-4 ${isDark ? 'bg-gray-800/50 backdrop-blur-xl border border-gray-700/50' : 'bg-white/70 backdrop-blur-xl border border-gray-200'}`}>
            <div className="absolute top-0 right-0 w-20 h-20 bg-gradient-to-br from-pink-500/20 to-transparent rounded-full blur-2xl" />
            <div className="relative">
              <div className="flex items-center gap-2 mb-2">
                <div className="p-1.5 rounded-lg bg-pink-500/20">
                  <Users className="w-4 h-4 text-pink-400" />
                </div>
                <span className={`text-xs font-medium ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>Generos</span>
              </div>
              <p className={`text-3xl font-black ${isDark ? 'text-white' : 'text-gray-900'}`}>{generos}</p>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {loading ? (
            <div className="col-span-full flex justify-center py-8"><div className="w-8 h-8 border-4 border-violet-500 border-t-transparent rounded-full animate-spin" /></div>
          ) : categorias.map((cat) => {
            const colors = modalidadeColors[cat.modalidade || 'CORRIDA'] || modalidadeColors['CORRIDA'];
            return (
              <div 
                key={cat.id} 
                className={`relative overflow-hidden rounded-2xl ${isDark ? 'bg-gray-800/50 backdrop-blur-xl border border-gray-700/50' : 'bg-white/70 backdrop-blur-xl border border-gray-200'} p-6 transition-all duration-300 hover:scale-[1.02] hover:shadow-xl`}
              >
                <div className={`absolute top-0 right-0 w-32 h-32 bg-gradient-to-br ${colors.bg} opacity-10 rounded-full blur-2xl`} />
                
                <div className="relative">
                  <div className="flex justify-between items-start mb-4">
                    <div className="flex items-center gap-3">
                      <div className={`p-2.5 rounded-xl bg-gradient-to-br ${colors.bg} shadow-lg`}>
                        <Users className="w-5 h-5 text-white" />
                      </div>
                      <div>
                        <span className={`text-xs font-mono ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>{cat.codigo}</span>
                        <h3 className={`font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>{cat.nome}</h3>
                      </div>
                    </div>
                    {cat.is_pcd && (
                      <span className="px-3 py-1 text-xs font-bold rounded-full bg-blue-500/20 text-blue-400 border border-blue-500/30">
                        PCD
                      </span>
                    )}
                  </div>

                  <div className="space-y-3">
                    <div className="flex items-center justify-between">
                      <span className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>Modalidade</span>
                      <span className={`px-3 py-1 text-xs font-bold rounded-full bg-gradient-to-r ${colors.bg} text-white`}>
                        {cat.modalidade}
                      </span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>Genero</span>
                      <span className={`font-medium ${isDark ? 'text-white' : 'text-gray-900'}`}>{cat.genero}</span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>Faixa Etaria</span>
                      <span className={`font-medium ${isDark ? 'text-white' : 'text-gray-900'}`}>{cat.faixa_etaria || '-'}</span>
                    </div>
                    
                    <div className={`pt-3 border-t ${isDark ? 'border-gray-700' : 'border-gray-200'}`}>
                      <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center gap-2">
                          <DollarSign className="w-4 h-4 text-emerald-400" />
                          <span className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>Inscricao</span>
                        </div>
                        <span className="font-bold text-emerald-400">R$ {cat.valor_inscricao_padrao || 0}</span>
                      </div>
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <DollarSign className="w-4 h-4 text-orange-400" />
                          <span className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>Custo Kit</span>
                        </div>
                        <span className="font-bold text-orange-400">R$ {cat.custo_kit_padrao || 0}</span>
                      </div>
                    </div>
                  </div>

                  <div className="flex justify-end mt-4">
                    <button 
                      onClick={() => handleEdit(cat)} 
                      className={`p-2 rounded-xl ${isDark ? 'hover:bg-gray-700 text-violet-400' : 'hover:bg-gray-100 text-violet-600'} transition-colors`}
                    >
                      <Pencil className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {showModal && (
        <div 
          className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 overflow-y-auto p-4"
          onClick={(e) => {
            if (e.target === e.currentTarget) {
              setShowModal(false);
              setEditItem(null);
            }
          }}
        >
          <div 
            className={`${isDark ? 'bg-gray-900' : 'bg-white'} rounded-3xl p-8 w-full max-w-md shadow-2xl border ${isDark ? 'border-gray-700' : 'border-gray-200'}`}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex justify-between items-center mb-6">
              <div className="flex items-center gap-3">
                <div className="p-2 rounded-xl bg-gradient-to-br from-violet-500 to-purple-500">
                  <Users className="w-5 h-5 text-white" />
                </div>
                <div>
                  <h2 className={`text-2xl font-black ${isDark ? 'text-white' : 'text-gray-900'}`}>
                    {editItem ? 'Editar' : 'Nova'} Categoria
                  </h2>
                  <p className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>
                    Preencha as informacoes
                  </p>
                </div>
              </div>
              <button 
                type="button"
                onClick={() => setShowModal(false)}
                className={`p-2 rounded-xl ${isDark ? 'hover:bg-gray-800 text-gray-400' : 'hover:bg-gray-100 text-gray-600'} transition-colors`}
              >
                <X className="w-6 h-6" />
              </button>
            </div>

            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className={`block text-sm font-bold mb-2 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>Codigo</label>
                  <input type="text" value={form.codigo} onChange={(e) => setForm({ ...form, codigo: e.target.value })} className={`w-full px-4 py-3 rounded-xl border ${isDark ? 'bg-gray-800 border-gray-700 text-white' : 'bg-gray-50 border-gray-200'} focus:ring-2 focus:ring-violet-500 focus:border-transparent transition-all`} required />
                </div>
                <div>
                  <label className={`block text-sm font-bold mb-2 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>Modalidade</label>
                  <select value={form.modalidade} onChange={(e) => setForm({ ...form, modalidade: e.target.value })} className={`w-full px-4 py-3 rounded-xl border ${isDark ? 'bg-gray-800 border-gray-700 text-white' : 'bg-gray-50 border-gray-200'} focus:ring-2 focus:ring-violet-500 focus:border-transparent transition-all`}>
                    <option value="CORRIDA">CORRIDA</option>
                    <option value="CICLISMO">CICLISMO</option>
                    <option value="NATACAO">NATACAO</option>
                    <option value="TRIATHLON">TRIATHLON</option>
                  </select>
                </div>
              </div>
              <div>
                <label className={`block text-sm font-bold mb-2 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>Nome</label>
                <input type="text" value={form.nome} onChange={(e) => setForm({ ...form, nome: e.target.value })} className={`w-full px-4 py-3 rounded-xl border ${isDark ? 'bg-gray-800 border-gray-700 text-white' : 'bg-gray-50 border-gray-200'} focus:ring-2 focus:ring-violet-500 focus:border-transparent transition-all`} required />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className={`block text-sm font-bold mb-2 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>Genero</label>
                  <select value={form.genero} onChange={(e) => setForm({ ...form, genero: e.target.value })} className={`w-full px-4 py-3 rounded-xl border ${isDark ? 'bg-gray-800 border-gray-700 text-white' : 'bg-gray-50 border-gray-200'} focus:ring-2 focus:ring-violet-500 focus:border-transparent transition-all`}>
                    <option value="MASCULINO">MASCULINO</option>
                    <option value="FEMININO">FEMININO</option>
                    <option value="MISTO">MISTO</option>
                  </select>
                </div>
                <div>
                  <label className={`block text-sm font-bold mb-2 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>Faixa Etaria</label>
                  <input type="text" value={form.faixa_etaria} onChange={(e) => setForm({ ...form, faixa_etaria: e.target.value })} className={`w-full px-4 py-3 rounded-xl border ${isDark ? 'bg-gray-800 border-gray-700 text-white' : 'bg-gray-50 border-gray-200'} focus:ring-2 focus:ring-violet-500 focus:border-transparent transition-all`} />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className={`block text-sm font-bold mb-2 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>Valor Inscricao (R$)</label>
                  <input type="number" step="0.01" value={form.valor_inscricao_padrao} onChange={(e) => setForm({ ...form, valor_inscricao_padrao: e.target.value })} className={`w-full px-4 py-3 rounded-xl border ${isDark ? 'bg-gray-800 border-gray-700 text-white' : 'bg-gray-50 border-gray-200'} focus:ring-2 focus:ring-violet-500 focus:border-transparent transition-all`} />
                </div>
                <div>
                  <label className={`block text-sm font-bold mb-2 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>Custo Kit (R$)</label>
                  <input type="number" step="0.01" value={form.custo_kit_padrao} onChange={(e) => setForm({ ...form, custo_kit_padrao: e.target.value })} className={`w-full px-4 py-3 rounded-xl border ${isDark ? 'bg-gray-800 border-gray-700 text-white' : 'bg-gray-50 border-gray-200'} focus:ring-2 focus:ring-violet-500 focus:border-transparent transition-all`} />
                </div>
              </div>
              <div className="flex items-center gap-3">
                <input type="checkbox" checked={form.is_pcd} onChange={(e) => setForm({ ...form, is_pcd: e.target.checked })} className="w-5 h-5 rounded border-gray-300 text-violet-600 focus:ring-violet-500" />
                <label className={`font-medium ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>Categoria PCD</label>
              </div>
              <div className="flex justify-end gap-3 pt-4">
                <button type="button" onClick={() => setShowModal(false)} className={`px-6 py-3 rounded-xl border font-semibold ${isDark ? 'border-gray-700 text-gray-300 hover:bg-gray-800' : 'border-gray-200 text-gray-600 hover:bg-gray-50'} transition-all`}>Cancelar</button>
                <button type="submit" className="px-6 py-3 bg-gradient-to-r from-violet-600 to-purple-600 text-white rounded-xl font-semibold shadow-lg shadow-violet-500/30 hover:shadow-violet-500/50 transition-all hover:scale-105 flex items-center gap-2"><Check className="w-4 h-4" /> Salvar</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};

export default Categorias;
