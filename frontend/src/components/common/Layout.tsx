import React, { useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { useTheme } from '../../context/ThemeContext';
import { usePermissions } from '../../context/PermissionContext';
import NoriButton from '../nori/NoriButton';
import { 
  LayoutDashboard, 
  Building2, 
  FileSpreadsheet, 
  Users, 
  TrendingUp,
  Target,
  CheckCircle,
  UserCog,
  Menu,
  X,
  Moon,
  Sun,
  LogOut,
  ChevronDown,
  Activity,
  BarChart3,
  Settings,
  Sparkles,
  Database,
  ShieldCheck,
  Package
} from 'lucide-react';

interface LayoutProps {
  children: React.ReactNode;
}

const menuItems = [
  { path: '/', icon: LayoutDashboard, label: 'Dashboard', modulo: 'dashboard' },
  { path: '/nori', icon: Sparkles, label: 'Nori - Assistente', modulo: 'nori' },
  { path: '/cadastros/categorias-atletas', icon: Users, label: 'Categorias Atletas', modulo: 'categorias_atletas' },
  { path: '/cadastros/eventos', icon: Target, label: 'Eventos', modulo: 'eventos' },
  { path: '/orcamento', icon: TrendingUp, label: 'Orcamento', modulo: 'orcamento' },
  { path: '/atletas', icon: Users, label: 'Atletas', modulo: 'atletas' },
];

const marketingItems = [
  { path: '/marketing', icon: Activity, label: 'Dashboard ISC', modulo: 'marketing_dashboard' },
  { path: '/marketing/comparativo', icon: BarChart3, label: 'Comparativo', modulo: 'marketing_comparativo' },
  { path: '/marketing/configuracoes', icon: Settings, label: 'Configuracoes', modulo: 'marketing_configuracoes' },
];

const adminItems = [
  { path: '/admin/dados-consolidados', icon: Database, label: 'Dados Consolidados', modulo: 'admin_dados_consolidados' },
  { path: '/admin/sku-mappings', icon: Package, label: 'Mapeamento SKUs', modulo: 'admin_sku_mappings' },
  { path: '/admin/usuarios', icon: UserCog, label: 'Usuários', modulo: 'admin_usuarios' },
  { path: '/admin/perfis-acesso', icon: ShieldCheck, label: 'Perfis de Acesso', modulo: 'admin_perfis_acesso' },
  { path: '/admin/centros-custo', icon: Building2, label: 'Centros de Custo', modulo: 'admin_centros_custo' },
  { path: '/admin/contas', icon: FileSpreadsheet, label: 'Contas', modulo: 'admin_contas' },
];

const Layout: React.FC<LayoutProps> = ({ children }) => {
  const { user, logout } = useAuth();
  const { isDark, toggleTheme } = useTheme();
  const { canView } = usePermissions();
  const location = useLocation();
  const navigate = useNavigate();
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [cadastrosOpen, setCadastrosOpen] = useState(true);
  const [marketingOpen, setMarketingOpen] = useState(location.pathname.startsWith('/marketing'));
  const [adminOpen, setAdminOpen] = useState(location.pathname.startsWith('/admin'));

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const cadastroItems = menuItems.filter(item => item.path.includes('/cadastros/') && canView(item.modulo));
  const mainItems = menuItems.filter(item => !item.path.includes('/cadastros/') && canView(item.modulo));
  const filteredMarketingItems = marketingItems.filter(item => canView(item.modulo));
  const filteredAdminItems = adminItems.filter(item => canView(item.modulo));

  return (
    <div className={`min-h-screen ${isDark ? 'dark bg-gray-900' : 'bg-gray-50'}`}>
      <aside className={`fixed inset-y-0 left-0 z-50 w-64 transform transition-transform duration-200 ease-in-out ${sidebarOpen ? 'translate-x-0' : '-translate-x-full'} ${isDark ? 'bg-gray-800' : 'bg-white'} shadow-lg`}>
        <div className="flex items-center justify-between h-16 px-4 border-b border-gray-200 dark:border-gray-700">
          <h1 className={`text-xl font-bold ${isDark ? 'text-white' : 'text-gray-800'}`}>Norte One</h1>
          <button onClick={() => setSidebarOpen(false)} className="lg:hidden">
            <X className={isDark ? 'text-white' : 'text-gray-600'} />
          </button>
        </div>
        
        <nav className="p-4 space-y-2">
          {mainItems.map((item) => {
            const Icon = item.icon;
            const isActive = location.pathname === item.path;
            return (
              <Link
                key={item.path}
                to={item.path}
                className={`flex items-center px-4 py-2 rounded-lg transition-colors ${
                  isActive
                    ? 'bg-gradient-to-r from-indigo-600 to-purple-600 text-white'
                    : isDark
                    ? 'text-gray-300 hover:bg-gray-700'
                    : 'text-gray-600 hover:bg-gray-100'
                }`}
              >
                <Icon className="w-5 h-5 mr-3" />
                {item.label}
              </Link>
            );
          })}

          {filteredMarketingItems.length > 0 && (
          <div>
            <button
              onClick={() => setMarketingOpen(!marketingOpen)}
              className={`flex items-center justify-between w-full px-4 py-2 rounded-lg transition-colors ${
                location.pathname.startsWith('/marketing')
                  ? 'bg-gradient-to-r from-indigo-600 to-purple-600 text-white'
                  : isDark ? 'text-gray-300 hover:bg-gray-700' : 'text-gray-600 hover:bg-gray-100'
              }`}
            >
              <span className="flex items-center">
                <Activity className="w-5 h-5 mr-3" />
                Marketing Performance
              </span>
              <ChevronDown className={`w-4 h-4 transition-transform ${marketingOpen ? 'rotate-180' : ''}`} />
            </button>
            
            {marketingOpen && (
              <div className="ml-4 mt-1 space-y-1">
                {filteredMarketingItems.map((item) => {
                  const Icon = item.icon;
                  const isActive = location.pathname === item.path;
                  return (
                    <Link
                      key={item.path}
                      to={item.path}
                      className={`flex items-center px-4 py-2 rounded-lg transition-colors ${
                        isActive
                          ? 'bg-gradient-to-r from-indigo-600 to-purple-600 text-white'
                          : isDark
                          ? 'text-gray-300 hover:bg-gray-700'
                          : 'text-gray-600 hover:bg-gray-100'
                      }`}
                    >
                      <Icon className="w-4 h-4 mr-3" />
                      {item.label}
                    </Link>
                  );
                })}
              </div>
            )}
          </div>
          )}

          {cadastroItems.length > 0 && (
          <div>
            <button
              onClick={() => setCadastrosOpen(!cadastrosOpen)}
              className={`flex items-center justify-between w-full px-4 py-2 rounded-lg transition-colors ${
                isDark ? 'text-gray-300 hover:bg-gray-700' : 'text-gray-600 hover:bg-gray-100'
              }`}
            >
              <span className="flex items-center">
                <FileSpreadsheet className="w-5 h-5 mr-3" />
                Cadastros
              </span>
              <ChevronDown className={`w-4 h-4 transition-transform ${cadastrosOpen ? 'rotate-180' : ''}`} />
            </button>
            
            {cadastrosOpen && (
              <div className="ml-4 mt-1 space-y-1">
                {cadastroItems.map((item) => {
                  const Icon = item.icon;
                  const isActive = location.pathname === item.path;
                  return (
                    <Link
                      key={item.path}
                      to={item.path}
                      className={`flex items-center px-4 py-2 rounded-lg transition-colors ${
                        isActive
                          ? 'bg-gradient-to-r from-indigo-600 to-purple-600 text-white'
                          : isDark
                          ? 'text-gray-300 hover:bg-gray-700'
                          : 'text-gray-600 hover:bg-gray-100'
                      }`}
                    >
                      <Icon className="w-4 h-4 mr-3" />
                      {item.label.replace('Categorias ', '')}
                    </Link>
                  );
                })}
              </div>
            )}
          </div>
          )}

          {filteredAdminItems.length > 0 && (
            <div>
              <button
                onClick={() => setAdminOpen(!adminOpen)}
                className={`flex items-center justify-between w-full px-4 py-2 rounded-lg transition-colors ${
                  location.pathname.startsWith('/admin')
                    ? 'bg-gradient-to-r from-indigo-600 to-purple-600 text-white'
                    : isDark ? 'text-gray-300 hover:bg-gray-700' : 'text-gray-600 hover:bg-gray-100'
                }`}
              >
                <span className="flex items-center">
                  <ShieldCheck className="w-5 h-5 mr-3" />
                  Admin
                </span>
                <ChevronDown className={`w-4 h-4 transition-transform ${adminOpen ? 'rotate-180' : ''}`} />
              </button>
              
              {adminOpen && (
                <div className="ml-4 mt-1 space-y-1">
                  {filteredAdminItems.map((item) => {
                    const Icon = item.icon;
                    const isActive = location.pathname === item.path;
                    return (
                      <Link
                        key={item.path}
                        to={item.path}
                        className={`flex items-center px-4 py-2 rounded-lg transition-colors ${
                          isActive
                            ? 'bg-gradient-to-r from-indigo-600 to-purple-600 text-white'
                            : isDark
                            ? 'text-gray-300 hover:bg-gray-700'
                            : 'text-gray-600 hover:bg-gray-100'
                        }`}
                      >
                        <Icon className="w-4 h-4 mr-3" />
                        {item.label}
                      </Link>
                    );
                  })}
                </div>
              )}
            </div>
          )}
        </nav>
      </aside>

      <div className={`${sidebarOpen ? 'lg:ml-64' : ''} transition-all duration-200 min-h-screen ${isDark ? 'bg-gray-900' : 'bg-gray-50'}`}>
        <header className={`sticky top-0 z-40 h-16 flex items-center justify-between px-4 ${isDark ? 'bg-gray-800 border-gray-700' : 'bg-white border-gray-200'} border-b shadow-sm`}>
          <button onClick={() => setSidebarOpen(!sidebarOpen)} className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700">
            <Menu className={isDark ? 'text-white' : 'text-gray-600'} />
          </button>
          
          <div className="flex items-center space-x-4">
            <button onClick={toggleTheme} className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700">
              {isDark ? <Sun className="text-yellow-400" /> : <Moon className="text-gray-600" />}
            </button>
            
            <div className={`text-sm ${isDark ? 'text-gray-300' : 'text-gray-600'}`}>
              {user?.nome} <span className="text-xs px-2 py-1 rounded bg-blue-100 text-blue-800 ml-2">{user?.perfil_acesso_nome || 'Sem perfil'}</span>
            </div>
            
            <button onClick={handleLogout} className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 text-red-500">
              <LogOut className="w-5 h-5" />
            </button>
          </div>
        </header>

        <main className="p-6">
          {children}
        </main>
      </div>

      <NoriButton />
    </div>
  );
};

export default Layout;
