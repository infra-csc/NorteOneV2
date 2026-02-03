import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft, Target, TrendingUp, Activity, Tag, Bell } from 'lucide-react';
import {
  EventGoalsSettings,
  BenchmarkCurvesSettings,
  ISCParametersSettings,
  EventCategoriesSettings,
  AlertsSettings
} from '../../components/marketing/settings';
import { useTheme } from '../../context/ThemeContext';

type TabId = 'goals' | 'benchmarks' | 'isc' | 'categories' | 'alerts';

interface Tab {
  id: TabId;
  label: string;
  icon: React.ReactNode;
}

const tabs: Tab[] = [
  { id: 'goals', label: 'Metas por Evento', icon: <Target className="w-5 h-5" /> },
  { id: 'benchmarks', label: 'Curvas de Benchmark', icon: <TrendingUp className="w-5 h-5" /> },
  { id: 'isc', label: 'Parâmetros ISC', icon: <Activity className="w-5 h-5" /> },
  { id: 'categories', label: 'Categorias', icon: <Tag className="w-5 h-5" /> },
  { id: 'alerts', label: 'Alertas', icon: <Bell className="w-5 h-5" /> }
];

const MarketingSettings: React.FC = () => {
  const { isDark } = useTheme();
  const [activeTab, setActiveTab] = useState<TabId>('goals');

  const renderTabContent = () => {
    switch (activeTab) {
      case 'goals':
        return <EventGoalsSettings />;
      case 'benchmarks':
        return <BenchmarkCurvesSettings />;
      case 'isc':
        return <ISCParametersSettings />;
      case 'categories':
        return <EventCategoriesSettings />;
      case 'alerts':
        return <AlertsSettings />;
      default:
        return null;
    }
  };

  return (
    <div className="min-h-screen">
      <div className="fixed inset-0 pointer-events-none overflow-hidden">
        <div className={`absolute top-0 left-1/4 w-96 h-96 ${isDark ? 'bg-blue-500/10' : 'bg-blue-400/20'} rounded-full blur-3xl animate-pulse`} />
        <div className={`absolute bottom-0 right-1/4 w-96 h-96 ${isDark ? 'bg-purple-500/10' : 'bg-purple-400/20'} rounded-full blur-3xl animate-pulse`} style={{ animationDelay: '1s' }} />
        <div className={`absolute top-1/2 left-1/2 w-64 h-64 ${isDark ? 'bg-indigo-500/5' : 'bg-indigo-400/15'} rounded-full blur-3xl animate-pulse`} style={{ animationDelay: '2s' }} />
      </div>

      <div className="relative z-10 p-6 space-y-6">
      <div className="flex items-center gap-4">
        <Link
          to="/marketing"
          className={`p-2 rounded-lg transition-colors ${isDark ? 'hover:bg-gray-700' : 'hover:bg-gray-100'}`}
        >
          <ArrowLeft className={`w-5 h-5 ${isDark ? 'text-gray-400' : 'text-gray-600'}`} />
        </Link>
        <div>
          <h1 className={`text-2xl font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>
            Configurações
          </h1>
          <p className={`mt-1 ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
            Configurações do Marketing Performance
          </p>
        </div>
      </div>

      <div className="border-b border-gray-200 dark:border-gray-700">
        <nav className="flex space-x-1 overflow-x-auto pb-px">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 transition-colors whitespace-nowrap ${
                activeTab === tab.id
                  ? 'border-blue-600 text-blue-600 dark:border-blue-400 dark:text-blue-400'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300 dark:text-gray-400 dark:hover:text-gray-300'
              }`}
            >
              {tab.icon}
              {tab.label}
            </button>
          ))}
        </nav>
      </div>

      <div className="min-h-[500px]">
        {renderTabContent()}
      </div>
      </div>
    </div>
  );
};

export default MarketingSettings;
