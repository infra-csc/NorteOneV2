import React, { useEffect, useState } from 'react';
import { dashboardService } from '../../services/api';
import { DashboardResumo, EvolucaoMensal, AtletasPorProjeto } from '../../types';
import { useTheme } from '../../context/ThemeContext';
import { 
  TrendingUp, 
  TrendingDown, 
  Users, 
  DollarSign,
  Target,
  BarChart3,
  PieChart as PieChartIcon,
  Activity
} from 'lucide-react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell
} from 'recharts';

const COLORS = ['#3B82F6', '#10B981', '#F59E0B', '#EF4444', '#8B5CF6', '#EC4899'];

const formatCurrency = (value: number) => {
  return new Intl.NumberFormat('pt-BR', {
    style: 'currency',
    currency: 'BRL',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0
  }).format(value);
};

const Dashboard: React.FC = () => {
  const { isDark } = useTheme();
  const [resumo, setResumo] = useState<DashboardResumo | null>(null);
  const [evolucao, setEvolucao] = useState<EvolucaoMensal[]>([]);
  const [atletasProjeto, setAtletasProjeto] = useState<AtletasPorProjeto[]>([]);
  const [atletasModalidade, setAtletasModalidade] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [ano, setAno] = useState(2025);

  useEffect(() => {
    const loadData = async () => {
      setLoading(true);
      try {
        const [resumoData, evolucaoData, atletasProjetoData, atletasModalidadeData] = await Promise.all([
          dashboardService.getResumoGeral(ano),
          dashboardService.getEvolucaoMensal(ano),
          dashboardService.getAtletasPorProjeto(),
          dashboardService.getAtletasPorModalidade()
        ]);
        setResumo(resumoData);
        setEvolucao(evolucaoData);
        setAtletasProjeto(atletasProjetoData);
        setAtletasModalidade(atletasModalidadeData);
      } catch (error) {
        console.error('Erro ao carregar dashboard:', error);
      } finally {
        setLoading(false);
      }
    };
    loadData();
  }, [ano]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="w-8 h-8 border-4 border-blue-500 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  const cardClass = `p-6 rounded-xl shadow-lg ${isDark ? 'bg-gray-800' : 'bg-white'}`;
  const textClass = isDark ? 'text-gray-200' : 'text-gray-600';
  const headingClass = isDark ? 'text-white' : 'text-gray-800';

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h1 className={`text-2xl font-bold ${headingClass}`}>Dashboard Consolidado</h1>
        <select
          value={ano}
          onChange={(e) => setAno(Number(e.target.value))}
          className={`px-4 py-2 rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white' : 'bg-white border-gray-300'}`}
        >
          <option value={2025}>2025</option>
          <option value={2024}>2024</option>
        </select>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <div className={cardClass}>
          <div className="flex items-center justify-between">
            <div>
              <p className={textClass}>Orcado (Ano)</p>
              <p className={`text-2xl font-bold ${headingClass}`}>{formatCurrency(resumo?.financeiro.orcado_resultado || 0)}</p>
            </div>
            <div className="p-3 bg-blue-100 rounded-full">
              <Target className="w-6 h-6 text-blue-600" />
            </div>
          </div>
        </div>

        <div className={cardClass}>
          <div className="flex items-center justify-between">
            <div>
              <p className={textClass}>Projetado (Ano)</p>
              <p className={`text-2xl font-bold ${headingClass}`}>{formatCurrency(resumo?.financeiro.projetado_resultado || 0)}</p>
            </div>
            <div className="p-3 bg-yellow-100 rounded-full">
              <TrendingUp className="w-6 h-6 text-yellow-600" />
            </div>
          </div>
        </div>

        <div className={cardClass}>
          <div className="flex items-center justify-between">
            <div>
              <p className={textClass}>Realizado (YTD)</p>
              <p className={`text-2xl font-bold ${headingClass}`}>{formatCurrency(resumo?.financeiro.realizado_resultado || 0)}</p>
            </div>
            <div className="p-3 bg-green-100 rounded-full">
              <DollarSign className="w-6 h-6 text-green-600" />
            </div>
          </div>
        </div>

        <div className={cardClass}>
          <div className="flex items-center justify-between">
            <div>
              <p className={textClass}>Variacao Orc x Real</p>
              <p className={`text-2xl font-bold ${(resumo?.financeiro.variacao_percentual || 0) >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                {resumo?.financeiro.variacao_percentual || 0}%
              </p>
            </div>
            <div className={`p-3 rounded-full ${(resumo?.financeiro.variacao_percentual || 0) >= 0 ? 'bg-green-100' : 'bg-red-100'}`}>
              {(resumo?.financeiro.variacao_percentual || 0) >= 0 ? 
                <TrendingUp className="w-6 h-6 text-green-600" /> : 
                <TrendingDown className="w-6 h-6 text-red-600" />
              }
            </div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className={cardClass}>
          <div className="flex items-center justify-between">
            <div>
              <p className={textClass}>Atletas Orcados</p>
              <p className={`text-2xl font-bold ${headingClass}`}>{resumo?.atletas.total_orcado?.toLocaleString() || 0}</p>
            </div>
            <div className="p-3 bg-purple-100 rounded-full">
              <Users className="w-6 h-6 text-purple-600" />
            </div>
          </div>
        </div>

        <div className={cardClass}>
          <div className="flex items-center justify-between">
            <div>
              <p className={textClass}>Atletas Projetados</p>
              <p className={`text-2xl font-bold ${headingClass}`}>{resumo?.atletas.total_projetado?.toLocaleString() || 0}</p>
            </div>
            <div className="p-3 bg-indigo-100 rounded-full">
              <Users className="w-6 h-6 text-indigo-600" />
            </div>
          </div>
        </div>

        <div className={cardClass}>
          <div className="flex items-center justify-between">
            <div>
              <p className={textClass}>Atletas Realizados</p>
              <p className={`text-2xl font-bold ${headingClass}`}>{resumo?.atletas.total_realizado?.toLocaleString() || 0}</p>
            </div>
            <div className="p-3 bg-teal-100 rounded-full">
              <Users className="w-6 h-6 text-teal-600" />
            </div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className={cardClass}>
          <h3 className={`text-lg font-semibold mb-4 ${headingClass}`}>
            <BarChart3 className="inline w-5 h-5 mr-2" />
            Evolucao Mensal - Orcado x Realizado
          </h3>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={evolucao}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="mes" />
              <YAxis tickFormatter={(value) => `${(value / 1000).toFixed(0)}k`} />
              <Tooltip formatter={(value: number) => formatCurrency(value)} />
              <Legend />
              <Bar dataKey="orcado" name="Orcado" fill="#3B82F6" />
              <Bar dataKey="realizado" name="Realizado" fill="#10B981" />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className={cardClass}>
          <h3 className={`text-lg font-semibold mb-4 ${headingClass}`}>
            <PieChartIcon className="inline w-5 h-5 mr-2" />
            Atletas por Modalidade
          </h3>
          <ResponsiveContainer width="100%" height={300}>
            <PieChart>
              <Pie
                data={atletasModalidade}
                dataKey="total"
                nameKey="modalidade"
                cx="50%"
                cy="50%"
                outerRadius={100}
                label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
              >
                {atletasModalidade.map((_, index) => (
                  <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                ))}
              </Pie>
              <Tooltip />
            </PieChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className={cardClass}>
        <h3 className={`text-lg font-semibold mb-4 ${headingClass}`}>
          <Activity className="inline w-5 h-5 mr-2" />
          Atletas por Evento
        </h3>
        <ResponsiveContainer width="100%" height={300}>
          <BarChart data={atletasProjeto} layout="vertical">
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis type="number" />
            <YAxis dataKey="evento" type="category" width={200} />
            <Tooltip />
            <Legend />
            <Bar dataKey="orcado" name="Orcado" fill="#3B82F6" />
            <Bar dataKey="projetado" name="Projetado" fill="#F59E0B" />
            <Bar dataKey="realizado" name="Realizado" fill="#10B981" />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};

export default Dashboard;
