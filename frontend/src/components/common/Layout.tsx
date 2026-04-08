import React, { useState, useEffect, useCallback } from 'react';
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
  Target,
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
  Package,
  Plane,
  Monitor,
  BookOpen,
  Layers,
  Shield,
  AlertTriangle,
} from 'lucide-react';

interface LayoutProps {
  children: React.ReactNode;
}

const menuItems = [
  { path: '/', icon: LayoutDashboard, label: 'Dashboard', modulo: 'dashboard' },
  { path: '/nori', icon: Sparkles, label: 'Nori - Assistente', modulo: 'nori' },
  { path: '/cadastros/categorias-atletas', icon: Users, label: 'Categorias Atletas', modulo: 'categorias_atletas' },
  { path: '/cadastros/eventos', icon: Target, label: 'Eventos', modulo: 'eventos' },
];

const cotacaoItems = [
  { path: '/cotacoes', icon: Plane, label: 'Cotação & Importação', modulo: 'cotacoes_importacao' },
];

const marketingItems = [
  { path: '/marketing', icon: Activity, label: 'Dashboard ISC', modulo: 'marketing_dashboard' },
  { path: '/marketing/comparativo', icon: BarChart3, label: 'Comparativo', modulo: 'marketing_comparativo' },
  { path: '/marketing/configuracoes', icon: Settings, label: 'Configuracoes', modulo: 'marketing_configuracoes' },
];

const adminItems = [
  { path: '/admin/dados-consolidados', icon: Database, label: 'Dados Consolidados', modulo: 'admin_dados_consolidados' },
  { path: '/admin/sku-mappings', icon: Package, label: 'Mapeamento SKUs', modulo: 'admin_sku_mappings' },
  { path: '/admin/kit-config', icon: Layers, label: 'Mapeamento de Kits', modulo: 'admin_kit_config' },
  { path: '/admin/usuarios', icon: UserCog, label: 'Usuários', modulo: 'admin_usuarios' },
  { path: '/admin/perfis-acesso', icon: ShieldCheck, label: 'Perfis de Acesso', modulo: 'admin_perfis_acesso' },
  { path: '/admin/centros-custo', icon: Building2, label: 'Centros de Custo', modulo: 'admin_centros_custo' },
  { path: '/admin/monitoramento', icon: Monitor, label: 'Monitoramento', modulo: 'admin_monitoramento' },
  { path: '/admin/saude-sistema', icon: Shield, label: 'Saúde do Sistema', modulo: 'admin_monitoramento' },
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
  const [healthStatus, setHealthStatus] = useState<'healthy' | 'warning' | 'critical' | 'info' | null>(null);
  const [unconfiguredKits, setUnconfiguredKits] = useState<{
    total: number;
    events: Array<{ nome_evento: string; count: number }>;
  } | null>(null);
  const [kitsBannerDismissed, setKitsBannerDismissed] = useState(false);

  const isAdmin = canView('admin_monitoramento');

  const fetchHealthStatus = useCallback(async () => {
    if (!isAdmin) return;
    try {
      const { adminService } = await import('../../services/api');
      const data = await adminService.getHealthSummary();
      setHealthStatus(data.status);
    } catch {
    }
  }, [isAdmin]);

  const fetchUnconfiguredKits = useCallback(async () => {
    if (!isAdmin) return;
    try {
      const { kitConfigService } = await import('../../services/api');
      const data = await kitConfigService.getUnconfiguredSummary();
      if (data.total_unconfigured > 0) {
        setUnconfiguredKits({ total: data.total_unconfigured, events: data.events });
      } else {
        setUnconfiguredKits(null);
      }
    } catch {
    }
  }, [isAdmin]);

  useEffect(() => {
    fetchHealthStatus();
    const interval = setInterval(fetchHealthStatus, 60000);
    return () => clearInterval(interval);
  }, [fetchHealthStatus]);

  useEffect(() => {
    fetchUnconfiguredKits();
    const interval = setInterval(fetchUnconfiguredKits, 300000);
    return () => clearInterval(interval);
  }, [fetchUnconfiguredKits]);

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const cadastroItems = menuItems.filter(item => item.path.includes('/cadastros/') && canView(item.modulo));
  const mainItems = menuItems.filter(item => !item.path.includes('/cadastros/') && canView(item.modulo));
  const filteredCotacaoItems = cotacaoItems.filter(item => canView(item.modulo));
  const filteredMarketingItems = marketingItems.filter(item => canView(item.modulo));
  const filteredAdminItems = adminItems.filter(item => canView(item.modulo));

  return (
    <div className={`min-h-screen ${isDark ? 'dark bg-gray-900' : 'bg-gray-50'}`}>
      <aside className={`fixed inset-y-0 left-0 z-50 w-64 flex flex-col transform transition-transform duration-200 ease-in-out ${sidebarOpen ? 'translate-x-0' : '-translate-x-full'} ${isDark ? 'bg-gray-800' : 'bg-white'} shadow-lg`}>
        <div className="flex items-center justify-between h-16 px-4 border-b border-gray-200 dark:border-gray-700">
          <h1 className={`text-xl font-bold ${isDark ? 'text-white' : 'text-gray-800'}`}>Norte One</h1>
          <button onClick={() => setSidebarOpen(false)} className="lg:hidden">
            <X className={isDark ? 'text-white' : 'text-gray-600'} />
          </button>
        </div>
        
        <nav className="p-4 space-y-2 flex-1 overflow-y-auto scrollbar-invisible">
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

          {filteredCotacaoItems.map((item) => {
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

          <div className={`mt-4 pt-4 border-t ${isDark ? 'border-gray-700' : 'border-gray-200'}`}>
            <Link
              to="/manual"
              className={`flex items-center px-4 py-2 rounded-lg transition-colors ${
                location.pathname === '/manual'
                  ? 'bg-gradient-to-r from-indigo-600 to-purple-600 text-white'
                  : isDark
                  ? 'text-gray-300 hover:bg-gray-700'
                  : 'text-gray-600 hover:bg-gray-100'
              }`}
            >
              <BookOpen className="w-5 h-5 mr-3" />
              Manual do Sistema
            </Link>
          </div>
        </nav>
      </aside>

      <div className={`${sidebarOpen ? 'lg:ml-64' : ''} transition-all duration-200 min-h-screen ${isDark ? 'bg-gray-900' : 'bg-gray-50'}`}>
        <header className={`sticky top-0 z-40 h-16 flex items-center justify-between px-4 ${isDark ? 'bg-gray-800 border-gray-700' : 'bg-white border-gray-200'} border-b shadow-sm`}>
          <button onClick={() => setSidebarOpen(!sidebarOpen)} className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700">
            <Menu className={isDark ? 'text-white' : 'text-gray-600'} />
          </button>
          
          <div className="flex items-center space-x-3">
            {isAdmin && unconfiguredKits && unconfiguredKits.total > 0 && (
              <Link
                to="/admin/kit-config"
                title={`${unconfiguredKits.total} kit(s) sem configuração em ${unconfiguredKits.events.length} evento(s)`}
                className="flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium transition-colors border bg-amber-500/10 text-amber-500 border-amber-500/40 hover:bg-amber-500/20"
              >
                <AlertTriangle className="w-3.5 h-3.5" />
                {unconfiguredKits.total} kit{unconfiguredKits.total !== 1 ? 's' : ''} sem config
              </Link>
            )}
            {isAdmin && healthStatus !== null && (
              <Link
                to="/admin/saude-sistema"
                title={`Saúde do Sistema: ${healthStatus === 'healthy' ? 'Saudável' : healthStatus === 'critical' ? 'Crítico' : healthStatus === 'warning' ? 'Alerta' : 'Info'}`}
                className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium transition-colors border ${
                  healthStatus === 'critical'
                    ? 'bg-red-500/10 text-red-400 border-red-500/40 hover:bg-red-500/20'
                    : healthStatus === 'warning'
                    ? 'bg-amber-500/10 text-amber-400 border-amber-500/40 hover:bg-amber-500/20'
                    : healthStatus === 'info'
                    ? 'bg-blue-500/10 text-blue-400 border-blue-500/40 hover:bg-blue-500/20'
                    : 'bg-emerald-500/10 text-emerald-400 border-emerald-500/40 hover:bg-emerald-500/20'
                }`}
              >
                <span className={`w-1.5 h-1.5 rounded-full ${
                  healthStatus === 'critical' ? 'bg-red-400 animate-pulse' :
                  healthStatus === 'warning' ? 'bg-amber-400 animate-pulse' :
                  healthStatus === 'info' ? 'bg-blue-400' :
                  'bg-emerald-400'
                }`} />
                <Shield className="w-3.5 h-3.5" />
                {healthStatus === 'critical' ? 'Crítico' : healthStatus === 'warning' ? 'Alerta' : healthStatus === 'info' ? 'Info' : 'OK'}
              </Link>
            )}
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

        {isAdmin && unconfiguredKits && unconfiguredKits.total > 0 && !kitsBannerDismissed && (
          <div className={`flex items-start gap-3 px-4 py-3 border-b ${isDark ? 'bg-amber-900/20 border-amber-700/40' : 'bg-amber-50 border-amber-200'}`}>
            <AlertTriangle className="w-5 h-5 text-amber-500 flex-shrink-0 mt-0.5" />
            <div className="flex-1 min-w-0">
              <p className={`text-sm font-medium ${isDark ? 'text-amber-300' : 'text-amber-800'}`}>
                {unconfiguredKits.total} kit{unconfiguredKits.total !== 1 ? 's' : ''} sem configuração encontrado{unconfiguredKits.total !== 1 ? 's' : ''}
              </p>
              <p className={`text-xs mt-0.5 ${isDark ? 'text-amber-400/80' : 'text-amber-700'}`}>
                {unconfiguredKits.events.slice(0, 3).map(e => `${e.nome_evento} (${e.count})`).join(' · ')}
                {unconfiguredKits.events.length > 3 && ` · +${unconfiguredKits.events.length - 3} evento(s)`}
                {' '}— Kits sem mapeamento podem causar divergência nos relatórios de margem.
              </p>
            </div>
            <div className="flex items-center gap-2 flex-shrink-0">
              <Link
                to="/admin/kit-config"
                className={`text-xs font-medium px-3 py-1 rounded-md transition-colors ${
                  isDark
                    ? 'bg-amber-700/40 text-amber-300 hover:bg-amber-700/60'
                    : 'bg-amber-200 text-amber-800 hover:bg-amber-300'
                }`}
              >
                Configurar kits
              </Link>
              <button
                onClick={() => setKitsBannerDismissed(true)}
                className={`p-1 rounded-md transition-colors ${isDark ? 'text-amber-400 hover:bg-amber-700/30' : 'text-amber-600 hover:bg-amber-100'}`}
                title="Dispensar aviso"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}

        <main className="p-6">
          {children}
        </main>
      </div>

      <NoriButton />
    </div>
  );
};

export default Layout;
