import React, { useEffect, useState } from 'react';
import { projetosService } from '../../services/api';
import { Projeto } from '../../types';
import { useTheme } from '../../context/ThemeContext';
import { Plus, Pencil, Trash2, X, Check, Calendar, MapPin } from 'lucide-react';

const modalidades = ['BEACH', 'CICLISMO', 'CORRIDA', 'CULTURA', 'EDUCACAO', 'E-SPORTS', 'FAMILIA', 'NATACAO', 'OBSTACULO', 'SAUDE', 'TRIATHLON'];
const tiposEvento = ['PROPRIO', 'INCENTIVO', 'ORGANIZACAO', 'LICENCIADO'];
const leis = ['LIE', 'PIE', 'FIA', 'ICMS RJ', 'PROAC', 'PRONAC', 'ROUANET', 'ISS RJ'];
const statusList = ['EM_ANDAMENTO', 'CONCLUIDO', 'CANCELADO'];

const Projetos: React.FC = () => {
  const { isDark } = useTheme();
  const [projetos, setProjetos] = useState<Projeto[]>([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [editItem, setEditItem] = useState<Projeto | null>(null);
  const [form, setForm] = useState({
    codigo: '', produto: '', modalidade: 'CORRIDA', tipo_evento: 'PROPRIO', evento: '',
    lei: 'ROUANET', cliente: '', status: 'EM_ANDAMENTO', data_evento: '', local_evento: '',
    cidade: '', estado: '', capacidade_maxima: '', etapa: ''
  });

  const loadData = async () => {
    setLoading(true);
    try {
      const data = await projetosService.list();
      setProjetos(data);
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
      const payload = { ...form, capacidade_maxima: form.capacidade_maxima ? Number(form.capacidade_maxima) : null, etapa: form.etapa ? Number(form.etapa) : null };
      if (editItem) {
        await projetosService.update(editItem.id, payload);
      } else {
        await projetosService.create(payload);
      }
      setShowModal(false);
      loadData();
    } catch (error: any) {
      alert(error.response?.data?.detail || 'Erro ao salvar');
    }
  };

  const handleEdit = (item: Projeto) => {
    setEditItem(item);
    setForm({
      codigo: item.codigo, produto: item.produto, modalidade: item.modalidade, tipo_evento: item.tipo_evento,
      evento: item.evento, lei: item.lei, cliente: item.cliente || '', status: item.status,
      data_evento: item.data_evento, local_evento: item.local_evento, cidade: item.cidade || '',
      estado: item.estado || '', capacidade_maxima: item.capacidade_maxima?.toString() || '',
      etapa: item.etapa?.toString() || ''
    });
    setShowModal(true);
  };

  const cardClass = `rounded-xl shadow-lg ${isDark ? 'bg-gray-800' : 'bg-white'}`;
  const textClass = isDark ? 'text-gray-200' : 'text-gray-600';
  const headingClass = isDark ? 'text-white' : 'text-gray-800';

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h1 className={`text-2xl font-bold ${headingClass}`}>Projetos / Eventos</h1>
        <button onClick={() => { setShowModal(true); setEditItem(null); }} className="flex items-center px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700">
          <Plus className="w-5 h-5 mr-2" /> Novo
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {loading ? (
          <div className="col-span-full flex justify-center py-8"><div className="w-8 h-8 border-4 border-blue-500 border-t-transparent rounded-full animate-spin" /></div>
        ) : projetos.map((projeto) => (
          <div key={projeto.id} className={`${cardClass} p-6`}>
            <div className="flex justify-between items-start mb-4">
              <div>
                <span className={`text-xs font-mono ${textClass}`}>{projeto.codigo}</span>
                <h3 className={`text-lg font-semibold ${headingClass}`}>{projeto.evento}</h3>
              </div>
              <span className={`px-2 py-1 text-xs rounded-full ${
                projeto.status === 'EM_ANDAMENTO' ? 'bg-blue-100 text-blue-800' :
                projeto.status === 'CONCLUIDO' ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'
              }`}>{projeto.status.replace('_', ' ')}</span>
            </div>
            <div className="space-y-2 text-sm">
              <div className={`flex items-center ${textClass}`}>
                <Calendar className="w-4 h-4 mr-2" />
                {new Date(projeto.data_evento).toLocaleDateString('pt-BR')}
              </div>
              <div className={`flex items-center ${textClass}`}>
                <MapPin className="w-4 h-4 mr-2" />
                {projeto.local_evento}, {projeto.cidade}/{projeto.estado}
              </div>
              <div className="flex flex-wrap gap-2 mt-3">
                <span className="px-2 py-1 text-xs rounded bg-purple-100 text-purple-800">{projeto.modalidade}</span>
                <span className="px-2 py-1 text-xs rounded bg-yellow-100 text-yellow-800">{projeto.tipo_evento}</span>
              </div>
            </div>
            <div className="flex justify-end mt-4 space-x-2">
              <button onClick={() => handleEdit(projeto)} className="p-2 text-blue-600 hover:bg-blue-50 rounded"><Pencil className="w-4 h-4" /></button>
            </div>
          </div>
        ))}
      </div>

      {showModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 overflow-y-auto p-4">
          <div className={`${isDark ? 'bg-gray-800' : 'bg-white'} rounded-xl p-6 w-full max-w-2xl my-8`}>
            <div className="flex justify-between items-center mb-4">
              <h2 className={`text-xl font-bold ${headingClass}`}>{editItem ? 'Editar' : 'Novo'} Projeto</h2>
              <button onClick={() => setShowModal(false)}><X className={textClass} /></button>
            </div>
            <form onSubmit={handleSubmit} className="grid grid-cols-2 gap-4">
              <div>
                <label className={`block text-sm font-medium mb-1 ${textClass}`}>Codigo</label>
                <input type="text" value={form.codigo} onChange={(e) => setForm({ ...form, codigo: e.target.value })} className={`w-full px-3 py-2 rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white' : 'border-gray-300'}`} required />
              </div>
              <div>
                <label className={`block text-sm font-medium mb-1 ${textClass}`}>Produto</label>
                <input type="text" value={form.produto} onChange={(e) => setForm({ ...form, produto: e.target.value })} className={`w-full px-3 py-2 rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white' : 'border-gray-300'}`} required />
              </div>
              <div className="col-span-2">
                <label className={`block text-sm font-medium mb-1 ${textClass}`}>Nome do Evento</label>
                <input type="text" value={form.evento} onChange={(e) => setForm({ ...form, evento: e.target.value })} className={`w-full px-3 py-2 rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white' : 'border-gray-300'}`} required />
              </div>
              <div>
                <label className={`block text-sm font-medium mb-1 ${textClass}`}>Modalidade</label>
                <select value={form.modalidade} onChange={(e) => setForm({ ...form, modalidade: e.target.value })} className={`w-full px-3 py-2 rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white' : 'border-gray-300'}`}>
                  {modalidades.map(m => <option key={m} value={m}>{m}</option>)}
                </select>
              </div>
              <div>
                <label className={`block text-sm font-medium mb-1 ${textClass}`}>Tipo Evento</label>
                <select value={form.tipo_evento} onChange={(e) => setForm({ ...form, tipo_evento: e.target.value })} className={`w-full px-3 py-2 rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white' : 'border-gray-300'}`}>
                  {tiposEvento.map(t => <option key={t} value={t}>{t}</option>)}
                </select>
              </div>
              <div>
                <label className={`block text-sm font-medium mb-1 ${textClass}`}>Lei</label>
                <select value={form.lei} onChange={(e) => setForm({ ...form, lei: e.target.value })} className={`w-full px-3 py-2 rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white' : 'border-gray-300'}`}>
                  {leis.map(l => <option key={l} value={l}>{l}</option>)}
                </select>
              </div>
              <div>
                <label className={`block text-sm font-medium mb-1 ${textClass}`}>Status</label>
                <select value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })} className={`w-full px-3 py-2 rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white' : 'border-gray-300'}`}>
                  {statusList.map(s => <option key={s} value={s}>{s}</option>)}
                </select>
              </div>
              <div>
                <label className={`block text-sm font-medium mb-1 ${textClass}`}>Data do Evento</label>
                <input type="date" value={form.data_evento} onChange={(e) => setForm({ ...form, data_evento: e.target.value })} className={`w-full px-3 py-2 rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white' : 'border-gray-300'}`} required />
              </div>
              <div>
                <label className={`block text-sm font-medium mb-1 ${textClass}`}>Cliente</label>
                <input type="text" value={form.cliente} onChange={(e) => setForm({ ...form, cliente: e.target.value })} className={`w-full px-3 py-2 rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white' : 'border-gray-300'}`} />
              </div>
              <div className="col-span-2">
                <label className={`block text-sm font-medium mb-1 ${textClass}`}>Local do Evento</label>
                <input type="text" value={form.local_evento} onChange={(e) => setForm({ ...form, local_evento: e.target.value })} className={`w-full px-3 py-2 rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white' : 'border-gray-300'}`} required />
              </div>
              <div>
                <label className={`block text-sm font-medium mb-1 ${textClass}`}>Cidade</label>
                <input type="text" value={form.cidade} onChange={(e) => setForm({ ...form, cidade: e.target.value })} className={`w-full px-3 py-2 rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white' : 'border-gray-300'}`} />
              </div>
              <div>
                <label className={`block text-sm font-medium mb-1 ${textClass}`}>Estado</label>
                <input type="text" value={form.estado} onChange={(e) => setForm({ ...form, estado: e.target.value })} className={`w-full px-3 py-2 rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white' : 'border-gray-300'}`} />
              </div>
              <div className="col-span-2 flex justify-end space-x-3 pt-4">
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

export default Projetos;
