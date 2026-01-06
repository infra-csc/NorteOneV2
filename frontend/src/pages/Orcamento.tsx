import React, { useEffect, useState } from 'react';
import { orcamentoService } from '../services/api';
import { useTheme } from '../context/ThemeContext';
import { DollarSign, TrendingUp, TrendingDown, FileSpreadsheet, Calendar, Sparkles } from 'lucide-react';

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

  const formatCurrency = (value: number) => new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(value);
  const meses = ['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez'];

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="w-8 h-8 border-4 border-amber-500 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      <div className="fixed inset-0 pointer-events-none overflow-hidden">
        <div className="absolute top-0 left-1/4 w-96 h-96 bg-amber-500/10 rounded-full blur-3xl animate-pulse" />
        <div className="absolute bottom-0 right-1/4 w-96 h-96 bg-yellow-500/10 rounded-full blur-3xl animate-pulse" style={{ animationDelay: '1s' }} />
        <div className="absolute top-1/2 left-1/2 w-64 h-64 bg-orange-500/5 rounded-full blur-3xl animate-pulse" style={{ animationDelay: '2s' }} />
      </div>

      <div className="relative z-10 space-y-8 p-6">
        <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
          <div>
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-xl bg-gradient-to-br from-amber-500 to-orange-500 shadow-lg shadow-amber-500/30">
                <DollarSign className="w-6 h-6 text-white" />
              </div>
              <div>
                <h1 className={`text-3xl font-black tracking-tight ${isDark ? 'text-white' : 'text-gray-900'}`}>
                  Orcamento
                  <span className="bg-gradient-to-r from-amber-400 via-yellow-500 to-orange-500 bg-clip-text text-transparent"> {ano}</span>
                </h1>
                <p className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>
                  Acompanhe receitas e despesas
                </p>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <div className={`flex items-center gap-2 px-4 py-3 rounded-2xl ${isDark ? 'bg-gray-800/50 backdrop-blur-xl border border-gray-700/50' : 'bg-white/70 backdrop-blur-xl border border-gray-200'}`}>
              <Calendar className={`w-5 h-5 ${isDark ? 'text-amber-400' : 'text-amber-600'}`} />
              <select 
                value={ano} 
                onChange={(e) => setAno(Number(e.target.value))} 
                className={`bg-transparent font-semibold focus:outline-none ${isDark ? 'text-white' : 'text-gray-900'}`}
              >
                <option value={2025}>2025</option>
                <option value={2024}>2024</option>
              </select>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className={`relative overflow-hidden rounded-2xl p-6 ${isDark ? 'bg-gray-800/50 backdrop-blur-xl border border-gray-700/50' : 'bg-white/70 backdrop-blur-xl border border-gray-200'}`}>
            <div className="absolute top-0 right-0 w-24 h-24 bg-gradient-to-br from-emerald-500/20 to-transparent rounded-full blur-2xl" />
            <div className="relative flex items-center justify-between">
              <div>
                <p className={`text-sm font-medium ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>Total Receitas</p>
                <p className="text-3xl font-black text-emerald-400">{formatCurrency(resumo?.total_receitas || 0)}</p>
              </div>
              <div className="p-3 rounded-xl bg-emerald-500/20">
                <TrendingUp className="w-6 h-6 text-emerald-400" />
              </div>
            </div>
          </div>

          <div className={`relative overflow-hidden rounded-2xl p-6 ${isDark ? 'bg-gray-800/50 backdrop-blur-xl border border-gray-700/50' : 'bg-white/70 backdrop-blur-xl border border-gray-200'}`}>
            <div className="absolute top-0 right-0 w-24 h-24 bg-gradient-to-br from-red-500/20 to-transparent rounded-full blur-2xl" />
            <div className="relative flex items-center justify-between">
              <div>
                <p className={`text-sm font-medium ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>Total Despesas</p>
                <p className="text-3xl font-black text-red-400">{formatCurrency(resumo?.total_despesas || 0)}</p>
              </div>
              <div className="p-3 rounded-xl bg-red-500/20">
                <TrendingDown className="w-6 h-6 text-red-400" />
              </div>
            </div>
          </div>

          <div className={`relative overflow-hidden rounded-2xl p-6 ${isDark ? 'bg-gray-800/50 backdrop-blur-xl border border-gray-700/50' : 'bg-white/70 backdrop-blur-xl border border-gray-200'}`}>
            <div className="absolute top-0 right-0 w-24 h-24 bg-gradient-to-br from-blue-500/20 to-transparent rounded-full blur-2xl" />
            <div className="relative flex items-center justify-between">
              <div>
                <p className={`text-sm font-medium ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>Resultado</p>
                <p className={`text-3xl font-black ${(resumo?.resultado || 0) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                  {formatCurrency(resumo?.resultado || 0)}
                </p>
              </div>
              <div className={`p-3 rounded-xl ${(resumo?.resultado || 0) >= 0 ? 'bg-emerald-500/20' : 'bg-red-500/20'}`}>
                <DollarSign className={`w-6 h-6 ${(resumo?.resultado || 0) >= 0 ? 'text-emerald-400' : 'text-red-400'}`} />
              </div>
            </div>
          </div>
        </div>

        <div className={`rounded-2xl ${isDark ? 'bg-gray-800/50 backdrop-blur-xl border border-gray-700/50' : 'bg-white/70 backdrop-blur-xl border border-gray-200'} p-6`}>
          <div className="flex items-center gap-3 mb-6">
            <div className="p-2 rounded-xl bg-gradient-to-br from-amber-500 to-orange-500">
              <FileSpreadsheet className="w-5 h-5 text-white" />
            </div>
            <h3 className={`text-xl font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>
              Orcamento Mensal
            </h3>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className={isDark ? 'bg-gray-700/50' : 'bg-gray-50/50'}>
                <tr>
                  <th className={`px-6 py-4 text-left text-xs font-bold uppercase tracking-wider ${isDark ? 'text-gray-300' : 'text-gray-600'}`}>Mes</th>
                  <th className={`px-6 py-4 text-right text-xs font-bold uppercase tracking-wider ${isDark ? 'text-gray-300' : 'text-gray-600'}`}>Receitas</th>
                  <th className={`px-6 py-4 text-right text-xs font-bold uppercase tracking-wider ${isDark ? 'text-gray-300' : 'text-gray-600'}`}>Despesas</th>
                  <th className={`px-6 py-4 text-right text-xs font-bold uppercase tracking-wider ${isDark ? 'text-gray-300' : 'text-gray-600'}`}>Resultado</th>
                </tr>
              </thead>
              <tbody className={`divide-y ${isDark ? 'divide-gray-700/50' : 'divide-gray-200/50'}`}>
                {porMes.map((item) => {
                  const resultado = (item.receitas || 0) - (item.despesas || 0);
                  return (
                    <tr key={item.mes} className={`${isDark ? 'hover:bg-gray-700/30' : 'hover:bg-gray-50/50'} transition-colors`}>
                      <td className={`px-6 py-4 font-semibold ${isDark ? 'text-white' : 'text-gray-900'}`}>{meses[item.mes - 1]}</td>
                      <td className="px-6 py-4 text-right font-medium text-emerald-400">{formatCurrency(item.receitas || 0)}</td>
                      <td className="px-6 py-4 text-right font-medium text-red-400">{formatCurrency(item.despesas || 0)}</td>
                      <td className={`px-6 py-4 text-right font-bold ${resultado >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                        {formatCurrency(resultado)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Orcamento;
