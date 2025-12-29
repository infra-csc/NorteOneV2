import React, { useEffect, useState } from 'react';
import { atletasService, projetosService, categoriasAtletasService } from '../services/api';
import { useTheme } from '../context/ThemeContext';
import { Users, DollarSign, TrendingUp, Target, BarChart3 } from 'lucide-react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';

const Atletas: React.FC = () => {
  const { isDark } = useTheme();
  const [resumo, setResumo] = useState<any>(null);
  const [porProjeto, setPorProjeto] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const loadData = async () => {
      setLoading(true);
      try {
        const [resumoData, projetoData] = await Promise.all([
          atletasService.getResumo(),
          atletasService.getPorProjeto()
        ]);
        setResumo(resumoData);
        setPorProjeto(projetoData);
      } catch (error) {
        console.error('Erro:', error);
      } finally {
        setLoading(false);
      }
    };
    loadData();
  }, []);

  const cardClass = `rounded-xl shadow-lg p-6 ${isDark ? 'bg-gray-800' : 'bg-white'}`;
  const textClass = isDark ? 'text-gray-200' : 'text-gray-600';
  const headingClass = isDark ? 'text-white' : 'text-gray-800';
  const formatCurrency = (value: number) => new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(value);

  if (loading) {
    return <div className="flex items-center justify-center h-64"><div className="w-8 h-8 border-4 border-blue-500 border-t-transparent rounded-full animate-spin" /></div>;
  }

  return (
    <div className="space-y-6">
      <h1 className={`text-2xl font-bold ${headingClass}`}>Gestao de Atletas</h1>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <div className={cardClass}>
          <div className="flex items-center justify-between">
            <div>
              <p className={textClass}>Atletas Orcados</p>
              <p className={`text-2xl font-bold ${headingClass}`}>{resumo?.total_atletas_orcado?.toLocaleString() || 0}</p>
            </div>
            <div className="p-3 bg-blue-100 rounded-full"><Target className="w-6 h-6 text-blue-600" /></div>
          </div>
        </div>
        <div className={cardClass}>
          <div className="flex items-center justify-between">
            <div>
              <p className={textClass}>Atletas Projetados</p>
              <p className={`text-2xl font-bold ${headingClass}`}>{resumo?.total_atletas_projetado?.toLocaleString() || 0}</p>
            </div>
            <div className="p-3 bg-yellow-100 rounded-full"><TrendingUp className="w-6 h-6 text-yellow-600" /></div>
          </div>
        </div>
        <div className={cardClass}>
          <div className="flex items-center justify-between">
            <div>
              <p className={textClass}>Atletas Realizados</p>
              <p className={`text-2xl font-bold ${headingClass}`}>{resumo?.total_atletas_realizado?.toLocaleString() || 0}</p>
            </div>
            <div className="p-3 bg-green-100 rounded-full"><Users className="w-6 h-6 text-green-600" /></div>
          </div>
        </div>
        <div className={cardClass}>
          <div className="flex items-center justify-between">
            <div>
              <p className={textClass}>Variacao %</p>
              <p className={`text-2xl font-bold ${(resumo?.variacao_percentual || 0) >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                {resumo?.variacao_percentual || 0}%
              </p>
            </div>
            <div className={`p-3 rounded-full ${(resumo?.variacao_percentual || 0) >= 0 ? 'bg-green-100' : 'bg-red-100'}`}>
              <TrendingUp className={`w-6 h-6 ${(resumo?.variacao_percentual || 0) >= 0 ? 'text-green-600' : 'text-red-600'}`} />
            </div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className={cardClass}>
          <div className="flex items-center justify-between">
            <div>
              <p className={textClass}>Receita Orcada (Inscricoes)</p>
              <p className="text-2xl font-bold text-green-500">{formatCurrency(resumo?.receita_orcada || 0)}</p>
            </div>
            <div className="p-3 bg-green-100 rounded-full"><DollarSign className="w-6 h-6 text-green-600" /></div>
          </div>
        </div>
        <div className={cardClass}>
          <div className="flex items-center justify-between">
            <div>
              <p className={textClass}>Receita Realizada</p>
              <p className="text-2xl font-bold text-green-500">{formatCurrency(resumo?.receita_realizada || 0)}</p>
            </div>
            <div className="p-3 bg-green-100 rounded-full"><DollarSign className="w-6 h-6 text-green-600" /></div>
          </div>
        </div>
      </div>

      <div className={cardClass}>
        <h3 className={`text-lg font-semibold mb-4 ${headingClass}`}>
          <BarChart3 className="inline w-5 h-5 mr-2" />
          Atletas por Evento
        </h3>
        <ResponsiveContainer width="100%" height={300}>
          <BarChart data={porProjeto}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="evento" />
            <YAxis />
            <Tooltip />
            <Legend />
            <Bar dataKey="orcado" name="Orcado" fill="#3B82F6" />
            <Bar dataKey="projetado" name="Projetado" fill="#F59E0B" />
            <Bar dataKey="realizado" name="Realizado" fill="#10B981" />
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className={cardClass}>
        <h3 className={`text-lg font-semibold mb-4 ${headingClass}`}>Detalhamento por Evento</h3>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className={isDark ? 'bg-gray-700' : 'bg-gray-50'}>
              <tr>
                <th className={`px-4 py-3 text-left ${textClass}`}>Evento</th>
                <th className={`px-4 py-3 text-right ${textClass}`}>Orcado</th>
                <th className={`px-4 py-3 text-right ${textClass}`}>Projetado</th>
                <th className={`px-4 py-3 text-right ${textClass}`}>Realizado</th>
                <th className={`px-4 py-3 text-right ${textClass}`}>Variacao</th>
              </tr>
            </thead>
            <tbody className={`divide-y ${isDark ? 'divide-gray-700' : 'divide-gray-200'}`}>
              {porProjeto.map((item, idx) => {
                const variacao = item.orcado > 0 ? ((item.realizado - item.orcado) / item.orcado * 100).toFixed(1) : 0;
                return (
                  <tr key={idx} className={isDark ? 'hover:bg-gray-700' : 'hover:bg-gray-50'}>
                    <td className={`px-4 py-3 ${headingClass}`}>{item.evento}</td>
                    <td className={`px-4 py-3 text-right ${textClass}`}>{item.orcado.toLocaleString()}</td>
                    <td className={`px-4 py-3 text-right ${textClass}`}>{item.projetado.toLocaleString()}</td>
                    <td className={`px-4 py-3 text-right ${headingClass} font-medium`}>{item.realizado.toLocaleString()}</td>
                    <td className={`px-4 py-3 text-right font-medium ${Number(variacao) >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                      {variacao}%
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

export default Atletas;
