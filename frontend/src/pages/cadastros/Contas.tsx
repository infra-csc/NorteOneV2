import React, { useEffect, useState } from 'react';
import { contasService } from '../../services/api';
import { Conta } from '../../types';
import { useTheme } from '../../context/ThemeContext';
import { Plus, Pencil, Trash2, X, Check } from 'lucide-react';

const Contas: React.FC = () => {
  const { isDark } = useTheme();
  const [contas, setContas] = useState<Conta[]>([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [editItem, setEditItem] = useState<Conta | null>(null);
  const [form, setForm] = useState({ codigo: '', nome: '', tipo: 'RECEITA', grupo: '', subgrupo: '' });

  const loadData = async () => {
    setLoading(true);
    try {
      const data = await contasService.list();
      setContas(data);
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
      if (editItem) {
        await contasService.update(editItem.id, form);
      } else {
        await contasService.create(form);
      }
      setShowModal(false);
      setEditItem(null);
      setForm({ codigo: '', nome: '', tipo: 'RECEITA', grupo: '', subgrupo: '' });
      loadData();
    } catch (error: any) {
      alert(error.response?.data?.detail || 'Erro ao salvar');
    }
  };

  const handleEdit = (item: Conta) => {
    setEditItem(item);
    setForm({ codigo: item.codigo, nome: item.nome, tipo: item.tipo, grupo: item.grupo || '', subgrupo: item.subgrupo || '' });
    setShowModal(true);
  };

  const handleDelete = async (id: number) => {
    if (confirm('Confirma a exclusao?')) {
      try {
        await contasService.delete(id);
        loadData();
      } catch (error: any) {
        alert(error.response?.data?.detail || 'Erro');
      }
    }
  };

  const cardClass = `rounded-xl shadow-lg ${isDark ? 'bg-gray-800' : 'bg-white'}`;
  const textClass = isDark ? 'text-gray-200' : 'text-gray-600';
  const headingClass = isDark ? 'text-white' : 'text-gray-800';

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h1 className={`text-2xl font-bold ${headingClass}`}>Contas Contabeis</h1>
        <button onClick={() => { setShowModal(true); setEditItem(null); setForm({ codigo: '', nome: '', tipo: 'RECEITA', grupo: '', subgrupo: '' }); }} className="flex items-center px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700">
          <Plus className="w-5 h-5 mr-2" /> Nova
        </button>
      </div>

      <div className={cardClass}>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className={isDark ? 'bg-gray-700' : 'bg-gray-50'}>
              <tr>
                <th className={`px-6 py-3 text-left text-xs font-medium uppercase ${textClass}`}>Codigo</th>
                <th className={`px-6 py-3 text-left text-xs font-medium uppercase ${textClass}`}>Nome</th>
                <th className={`px-6 py-3 text-left text-xs font-medium uppercase ${textClass}`}>Tipo</th>
                <th className={`px-6 py-3 text-left text-xs font-medium uppercase ${textClass}`}>Grupo</th>
                <th className={`px-6 py-3 text-left text-xs font-medium uppercase ${textClass}`}>Subgrupo</th>
                <th className={`px-6 py-3 text-right text-xs font-medium uppercase ${textClass}`}>Acoes</th>
              </tr>
            </thead>
            <tbody className={`divide-y ${isDark ? 'divide-gray-700' : 'divide-gray-200'}`}>
              {loading ? (
                <tr><td colSpan={6} className="text-center py-8"><div className="w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full animate-spin mx-auto" /></td></tr>
              ) : contas.map((conta) => (
                <tr key={conta.id} className={isDark ? 'hover:bg-gray-700' : 'hover:bg-gray-50'}>
                  <td className={`px-6 py-4 font-mono ${headingClass}`}>{conta.codigo}</td>
                  <td className={`px-6 py-4 ${headingClass}`}>{conta.nome}</td>
                  <td className="px-6 py-4">
                    <span className={`px-2 py-1 text-xs rounded-full ${conta.tipo === 'RECEITA' ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'}`}>
                      {conta.tipo}
                    </span>
                  </td>
                  <td className={`px-6 py-4 ${textClass}`}>{conta.grupo}</td>
                  <td className={`px-6 py-4 ${textClass}`}>{conta.subgrupo}</td>
                  <td className="px-6 py-4 text-right">
                    <button onClick={() => handleEdit(conta)} className="p-1 text-blue-600 hover:text-blue-800 mr-2"><Pencil className="w-4 h-4" /></button>
                    <button onClick={() => handleDelete(conta.id)} className="p-1 text-red-600 hover:text-red-800"><Trash2 className="w-4 h-4" /></button>
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
              <h2 className={`text-xl font-bold ${headingClass}`}>{editItem ? 'Editar' : 'Nova'} Conta</h2>
              <button onClick={() => setShowModal(false)}><X className={textClass} /></button>
            </div>
            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className={`block text-sm font-medium mb-1 ${textClass}`}>Codigo</label>
                <input type="text" value={form.codigo} onChange={(e) => setForm({ ...form, codigo: e.target.value })} className={`w-full px-3 py-2 rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white' : 'border-gray-300'}`} required />
              </div>
              <div>
                <label className={`block text-sm font-medium mb-1 ${textClass}`}>Nome</label>
                <input type="text" value={form.nome} onChange={(e) => setForm({ ...form, nome: e.target.value })} className={`w-full px-3 py-2 rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white' : 'border-gray-300'}`} required />
              </div>
              <div>
                <label className={`block text-sm font-medium mb-1 ${textClass}`}>Tipo</label>
                <select value={form.tipo} onChange={(e) => setForm({ ...form, tipo: e.target.value })} className={`w-full px-3 py-2 rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white' : 'border-gray-300'}`}>
                  <option value="RECEITA">RECEITA</option>
                  <option value="DESPESA">DESPESA</option>
                </select>
              </div>
              <div>
                <label className={`block text-sm font-medium mb-1 ${textClass}`}>Grupo</label>
                <input type="text" value={form.grupo} onChange={(e) => setForm({ ...form, grupo: e.target.value })} className={`w-full px-3 py-2 rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white' : 'border-gray-300'}`} />
              </div>
              <div>
                <label className={`block text-sm font-medium mb-1 ${textClass}`}>Subgrupo</label>
                <input type="text" value={form.subgrupo} onChange={(e) => setForm({ ...form, subgrupo: e.target.value })} className={`w-full px-3 py-2 rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white' : 'border-gray-300'}`} />
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

export default Contas;
