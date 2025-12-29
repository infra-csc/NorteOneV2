import React, { useEffect, useState } from 'react';
import { centrosCustoService } from '../../services/api';
import { CentroCusto } from '../../types';
import { useTheme } from '../../context/ThemeContext';
import { Plus, Pencil, Trash2, X, Check } from 'lucide-react';

const CentrosCusto: React.FC = () => {
  const { isDark } = useTheme();
  const [centros, setCentros] = useState<CentroCusto[]>([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [editItem, setEditItem] = useState<CentroCusto | null>(null);
  const [form, setForm] = useState({ codigo: '', nome: '', area: '', gestor_responsavel: '' });

  const loadData = async () => {
    setLoading(true);
    try {
      const data = await centrosCustoService.list();
      setCentros(data);
    } catch (error) {
      console.error('Erro ao carregar centros de custo:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      if (editItem) {
        await centrosCustoService.update(editItem.id, form);
      } else {
        await centrosCustoService.create(form);
      }
      setShowModal(false);
      setEditItem(null);
      setForm({ codigo: '', nome: '', area: '', gestor_responsavel: '' });
      loadData();
    } catch (error: any) {
      alert(error.response?.data?.detail || 'Erro ao salvar');
    }
  };

  const handleEdit = (item: CentroCusto) => {
    setEditItem(item);
    setForm({
      codigo: item.codigo,
      nome: item.nome,
      area: item.area || '',
      gestor_responsavel: item.gestor_responsavel || ''
    });
    setShowModal(true);
  };

  const handleDelete = async (id: number) => {
    if (confirm('Confirma a exclusao?')) {
      try {
        await centrosCustoService.delete(id);
        loadData();
      } catch (error: any) {
        alert(error.response?.data?.detail || 'Erro ao excluir');
      }
    }
  };

  const cardClass = `rounded-xl shadow-lg ${isDark ? 'bg-gray-800' : 'bg-white'}`;
  const textClass = isDark ? 'text-gray-200' : 'text-gray-600';
  const headingClass = isDark ? 'text-white' : 'text-gray-800';

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h1 className={`text-2xl font-bold ${headingClass}`}>Centros de Custo</h1>
        <button
          onClick={() => { setShowModal(true); setEditItem(null); setForm({ codigo: '', nome: '', area: '', gestor_responsavel: '' }); }}
          className="flex items-center px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
        >
          <Plus className="w-5 h-5 mr-2" /> Novo
        </button>
      </div>

      <div className={cardClass}>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className={isDark ? 'bg-gray-700' : 'bg-gray-50'}>
              <tr>
                <th className={`px-6 py-3 text-left text-xs font-medium uppercase tracking-wider ${textClass}`}>Codigo</th>
                <th className={`px-6 py-3 text-left text-xs font-medium uppercase tracking-wider ${textClass}`}>Nome</th>
                <th className={`px-6 py-3 text-left text-xs font-medium uppercase tracking-wider ${textClass}`}>Area</th>
                <th className={`px-6 py-3 text-left text-xs font-medium uppercase tracking-wider ${textClass}`}>Gestor</th>
                <th className={`px-6 py-3 text-left text-xs font-medium uppercase tracking-wider ${textClass}`}>Status</th>
                <th className={`px-6 py-3 text-right text-xs font-medium uppercase tracking-wider ${textClass}`}>Acoes</th>
              </tr>
            </thead>
            <tbody className={`divide-y ${isDark ? 'divide-gray-700' : 'divide-gray-200'}`}>
              {loading ? (
                <tr><td colSpan={6} className="text-center py-8"><div className="w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full animate-spin mx-auto" /></td></tr>
              ) : centros.map((centro) => (
                <tr key={centro.id} className={isDark ? 'hover:bg-gray-700' : 'hover:bg-gray-50'}>
                  <td className={`px-6 py-4 whitespace-nowrap font-mono ${headingClass}`}>{centro.codigo}</td>
                  <td className={`px-6 py-4 whitespace-nowrap ${headingClass}`}>{centro.nome}</td>
                  <td className={`px-6 py-4 whitespace-nowrap ${textClass}`}>{centro.area}</td>
                  <td className={`px-6 py-4 whitespace-nowrap ${textClass}`}>{centro.gestor_responsavel}</td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <span className={`px-2 py-1 text-xs rounded-full ${centro.ativo ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'}`}>
                      {centro.ativo ? 'Ativo' : 'Inativo'}
                    </span>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-right">
                    <button onClick={() => handleEdit(centro)} className="p-1 text-blue-600 hover:text-blue-800 mr-2">
                      <Pencil className="w-4 h-4" />
                    </button>
                    <button onClick={() => handleDelete(centro.id)} className="p-1 text-red-600 hover:text-red-800">
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {showModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className={`${isDark ? 'bg-gray-800' : 'bg-white'} rounded-xl p-6 w-full max-w-md`}>
            <div className="flex justify-between items-center mb-4">
              <h2 className={`text-xl font-bold ${headingClass}`}>{editItem ? 'Editar' : 'Novo'} Centro de Custo</h2>
              <button onClick={() => setShowModal(false)}><X className={textClass} /></button>
            </div>
            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className={`block text-sm font-medium mb-1 ${textClass}`}>Codigo</label>
                <input
                  type="text"
                  value={form.codigo}
                  onChange={(e) => setForm({ ...form, codigo: e.target.value })}
                  className={`w-full px-3 py-2 rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white' : 'border-gray-300'}`}
                  required
                />
              </div>
              <div>
                <label className={`block text-sm font-medium mb-1 ${textClass}`}>Nome</label>
                <input
                  type="text"
                  value={form.nome}
                  onChange={(e) => setForm({ ...form, nome: e.target.value })}
                  className={`w-full px-3 py-2 rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white' : 'border-gray-300'}`}
                  required
                />
              </div>
              <div>
                <label className={`block text-sm font-medium mb-1 ${textClass}`}>Area</label>
                <input
                  type="text"
                  value={form.area}
                  onChange={(e) => setForm({ ...form, area: e.target.value })}
                  className={`w-full px-3 py-2 rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white' : 'border-gray-300'}`}
                />
              </div>
              <div>
                <label className={`block text-sm font-medium mb-1 ${textClass}`}>Gestor Responsavel</label>
                <input
                  type="text"
                  value={form.gestor_responsavel}
                  onChange={(e) => setForm({ ...form, gestor_responsavel: e.target.value })}
                  className={`w-full px-3 py-2 rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white' : 'border-gray-300'}`}
                />
              </div>
              <div className="flex justify-end space-x-3 pt-4">
                <button type="button" onClick={() => setShowModal(false)} className={`px-4 py-2 rounded-lg border ${isDark ? 'border-gray-600 text-gray-300' : 'border-gray-300'}`}>
                  Cancelar
                </button>
                <button type="submit" className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 flex items-center">
                  <Check className="w-4 h-4 mr-2" /> Salvar
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};

export default CentrosCusto;
