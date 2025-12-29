import React, { useEffect, useState } from 'react';
import { orcamentoService, centrosCustoService, contasService, projetosService } from '../services/api';
import { useTheme } from '../context/ThemeContext';
import { DollarSign, TrendingUp, TrendingDown, FileSpreadsheet } from 'lucide-react';

const Orcamento: React.FC = () => {
  const { isDark } = useTheme();
  const [resumo, setResumo] = useState<any>(null);
  const [porMes, setPorMes] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [ano, setAno] = useState(2025);

  useEffect(() => {
    const loadData = async () => {
      setLoading(true);
      try {
        const [resumoData, porMesData] = await Promise.all([
          orcamentoService.getResumo(ano),
          orcamentoService.getPorMes(ano)
        ]);
        setResumo(resumoData);
        setPorMes(porMesData);
      } catch (error) {
        console.error('Erro:', error);
      } finally {
        setLoading(false);
      }
    };
    loadData();
  }, [ano]);

  const cardClass = `rounded-xl shadow-lg p-6 ${isDark ? 'bg-gray-800' : 'bg-white'}`;
  const textClass = isDark ? 'text-gray-200' : 'text-gray-600';
  const headingClass = isDark ? 'text-white' : 'text-gray-800';

  const formatCurrency = (value: number) => new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(value);
  const meses = ['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez'];

  if (loading) {
    return <div className="flex items-center justify-center h-64"><div className="w-8 h-8 border-4 border-blue-500 border-t-transparent rounded-full animate-spin" /></div>;
  }

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h1 className={`text-2xl font-bold ${headingClass}`}>Orcamento {ano}</h1>
        <select value={ano} onChange={(e) => setAno(Number(e.target.value))} className={`px-4 py-2 rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white' : 'bg-white border-gray-300'}`}>
          <option value={2025}>2025</option>
          <option value={2024}>2024</option>
        </select>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className={cardClass}>
          <div className="flex items-center justify-between">
            <div>
              <p className={textClass}>Total Receitas</p>
              <p className="text-2xl font-bold text-green-500">{formatCurrency(resumo?.total_receitas || 0)}</p>
            </div>
            <div className="p-3 bg-green-100 rounded-full"><TrendingUp className="w-6 h-6 text-green-600" /></div>
          </div>
        </div>
        <div className={cardClass}>
          <div className="flex items-center justify-between">
            <div>
              <p className={textClass}>Total Despesas</p>
              <p className="text-2xl font-bold text-red-500">{formatCurrency(resumo?.total_despesas || 0)}</p>
            </div>
            <div className="p-3 bg-red-100 rounded-full"><TrendingDown className="w-6 h-6 text-red-600" /></div>
          </div>
        </div>
        <div className={cardClass}>
          <div className="flex items-center justify-between">
            <div>
              <p className={textClass}>Resultado</p>
              <p className={`text-2xl font-bold ${(resumo?.resultado || 0) >= 0 ? 'text-green-500' : 'text-red-500'}`}>{formatCurrency(resumo?.resultado || 0)}</p>
            </div>
            <div className="p-3 bg-blue-100 rounded-full"><DollarSign className="w-6 h-6 text-blue-600" /></div>
          </div>
        </div>
      </div>

      <div className={cardClass}>
        <h3 className={`text-lg font-semibold mb-4 ${headingClass}`}>
          <FileSpreadsheet className="inline w-5 h-5 mr-2" />
          Orcamento Mensal
        </h3>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className={isDark ? 'bg-gray-700' : 'bg-gray-50'}>
              <tr>
                <th className={`px-4 py-3 text-left ${textClass}`}>Mes</th>
                <th className={`px-4 py-3 text-right ${textClass}`}>Receitas</th>
                <th className={`px-4 py-3 text-right ${textClass}`}>Despesas</th>
                <th className={`px-4 py-3 text-right ${textClass}`}>Resultado</th>
              </tr>
            </thead>
            <tbody className={`divide-y ${isDark ? 'divide-gray-700' : 'divide-gray-200'}`}>
              {porMes.map((item) => (
                <tr key={item.mes} className={isDark ? 'hover:bg-gray-700' : 'hover:bg-gray-50'}>
                  <td className={`px-4 py-3 ${headingClass}`}>{meses[item.mes - 1]}</td>
                  <td className="px-4 py-3 text-right text-green-500">{formatCurrency(item.receitas || 0)}</td>
                  <td className="px-4 py-3 text-right text-red-500">{formatCurrency(item.despesas || 0)}</td>
                  <td className={`px-4 py-3 text-right font-medium ${(item.receitas - item.despesas) >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                    {formatCurrency((item.receitas || 0) - (item.despesas || 0))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

export default Orcamento;
