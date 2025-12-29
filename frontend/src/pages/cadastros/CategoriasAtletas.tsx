import React, { useEffect, useState } from 'react';
import { categoriasAtletasService } from '../../services/api';
import { CategoriaAtleta } from '../../types';
import { useTheme } from '../../context/ThemeContext';
import { Plus, Pencil, Trash2, X, Check, Users } from 'lucide-react';

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

  const cardClass = `rounded-xl shadow-lg ${isDark ? 'bg-gray-800' : 'bg-white'}`;
  const textClass = isDark ? 'text-gray-200' : 'text-gray-600';
  const headingClass = isDark ? 'text-white' : 'text-gray-800';

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h1 className={`text-2xl font-bold ${headingClass}`}>Categorias de Atletas</h1>
        <button onClick={() => { setShowModal(true); setEditItem(null); }} className="flex items-center px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700">
          <Plus className="w-5 h-5 mr-2" /> Nova
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {loading ? (
          <div className="col-span-full flex justify-center py-8"><div className="w-8 h-8 border-4 border-blue-500 border-t-transparent rounded-full animate-spin" /></div>
        ) : categorias.map((cat) => (
          <div key={cat.id} className={`${cardClass} p-6`}>
            <div className="flex justify-between items-start mb-4">
              <div className="flex items-center">
                <div className="p-2 bg-purple-100 rounded-full mr-3">
                  <Users className="w-5 h-5 text-purple-600" />
                </div>
                <div>
                  <span className={`text-xs font-mono ${textClass}`}>{cat.codigo}</span>
                  <h3 className={`font-semibold ${headingClass}`}>{cat.nome}</h3>
                </div>
              </div>
              {cat.is_pcd && <span className="px-2 py-1 text-xs rounded-full bg-blue-100 text-blue-800">PCD</span>}
            </div>
            <div className="space-y-2 text-sm">
              <div className="flex justify-between">
                <span className={textClass}>Modalidade:</span>
                <span className={headingClass}>{cat.modalidade}</span>
              </div>
              <div className="flex justify-between">
                <span className={textClass}>Genero:</span>
                <span className={headingClass}>{cat.genero}</span>
              </div>
              <div className="flex justify-between">
                <span className={textClass}>Faixa Etaria:</span>
                <span className={headingClass}>{cat.faixa_etaria}</span>
              </div>
              <div className="flex justify-between pt-2 border-t">
                <span className={textClass}>Inscricao:</span>
                <span className="text-green-600 font-medium">R$ {cat.valor_inscricao_padrao}</span>
              </div>
              <div className="flex justify-between">
                <span className={textClass}>Custo Kit:</span>
                <span className="text-orange-600 font-medium">R$ {cat.custo_kit_padrao}</span>
              </div>
            </div>
            <div className="flex justify-end mt-4">
              <button onClick={() => handleEdit(cat)} className="p-2 text-blue-600 hover:bg-blue-50 rounded"><Pencil className="w-4 h-4" /></button>
            </div>
          </div>
        ))}
      </div>

      {showModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className={`${isDark ? 'bg-gray-800' : 'bg-white'} rounded-xl p-6 w-full max-w-md`}>
            <div className="flex justify-between items-center mb-4">
              <h2 className={`text-xl font-bold ${headingClass}`}>{editItem ? 'Editar' : 'Nova'} Categoria</h2>
              <button onClick={() => setShowModal(false)}><X className={textClass} /></button>
            </div>
            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className={`block text-sm font-medium mb-1 ${textClass}`}>Codigo</label>
                  <input type="text" value={form.codigo} onChange={(e) => setForm({ ...form, codigo: e.target.value })} className={`w-full px-3 py-2 rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white' : 'border-gray-300'}`} required />
                </div>
                <div>
                  <label className={`block text-sm font-medium mb-1 ${textClass}`}>Modalidade</label>
                  <select value={form.modalidade} onChange={(e) => setForm({ ...form, modalidade: e.target.value })} className={`w-full px-3 py-2 rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white' : 'border-gray-300'}`}>
                    <option value="CORRIDA">CORRIDA</option>
                    <option value="CICLISMO">CICLISMO</option>
                    <option value="NATACAO">NATACAO</option>
                    <option value="TRIATHLON">TRIATHLON</option>
                  </select>
                </div>
              </div>
              <div>
                <label className={`block text-sm font-medium mb-1 ${textClass}`}>Nome</label>
                <input type="text" value={form.nome} onChange={(e) => setForm({ ...form, nome: e.target.value })} className={`w-full px-3 py-2 rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white' : 'border-gray-300'}`} required />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className={`block text-sm font-medium mb-1 ${textClass}`}>Genero</label>
                  <select value={form.genero} onChange={(e) => setForm({ ...form, genero: e.target.value })} className={`w-full px-3 py-2 rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white' : 'border-gray-300'}`}>
                    <option value="MASCULINO">MASCULINO</option>
                    <option value="FEMININO">FEMININO</option>
                    <option value="MISTO">MISTO</option>
                  </select>
                </div>
                <div>
                  <label className={`block text-sm font-medium mb-1 ${textClass}`}>Faixa Etaria</label>
                  <input type="text" value={form.faixa_etaria} onChange={(e) => setForm({ ...form, faixa_etaria: e.target.value })} className={`w-full px-3 py-2 rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white' : 'border-gray-300'}`} />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className={`block text-sm font-medium mb-1 ${textClass}`}>Valor Inscricao (R$)</label>
                  <input type="number" step="0.01" value={form.valor_inscricao_padrao} onChange={(e) => setForm({ ...form, valor_inscricao_padrao: e.target.value })} className={`w-full px-3 py-2 rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white' : 'border-gray-300'}`} />
                </div>
                <div>
                  <label className={`block text-sm font-medium mb-1 ${textClass}`}>Custo Kit (R$)</label>
                  <input type="number" step="0.01" value={form.custo_kit_padrao} onChange={(e) => setForm({ ...form, custo_kit_padrao: e.target.value })} className={`w-full px-3 py-2 rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white' : 'border-gray-300'}`} />
                </div>
              </div>
              <div className="flex items-center">
                <input type="checkbox" checked={form.is_pcd} onChange={(e) => setForm({ ...form, is_pcd: e.target.checked })} className="mr-2" />
                <label className={textClass}>Categoria PCD</label>
              </div>
              <div className="flex justify-end space-x-3 pt-4">
                <button type="button" onClick={() => setShowModal(false)} className={`px-4 py-2 rounded-lg border ${isDark ? 'border-gray-600 text-gray-300' : 'border-gray-300'}`}>Cancelar</button>
                <button type="submit" className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 flex items-center"><Check className="w-4 h-4 mr-2" /> Salvar</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};

export default Categorias;
