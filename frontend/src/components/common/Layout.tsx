import React, { useState, useEffect, useCallback } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { useTheme } from '../../context/ThemeContext';
import { usePermissions } from '../../context/PermissionContext';
import NoriButton from '../nori/NoriButton';
import { 
  LayoutDashboard, 
  Building2, 
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
  Table2,
  ArrowRight,
  Gift,
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

const projecaoInscritosItem = { path: '/projecao-inscritos', icon: BarChart3, label: 'Projeção Inscritos', modulo: 'projecao_inscritos' };
const cortesiasItem = { path: '/cortesias', icon: Gift, label: 'Cortesias', modulo: 'projecao_inscritos' };
const solicitacaoCortesiasItem = { path: '/cadastros/solicitacao-cortesias', icon: Gift, label: 'Solicitação de Cortesias', modulo: 'cortesia_solicitacao' };

const cotacaoItems = [
  { path: '/cotacoes', icon: Plane, label: 'Cotação & Importação', modulo: 'cotacoes_importacao' },
];

const marketingItems = [
  { path: '/marketing', icon: Activity, label: 'Dashboard ISC', modulo: 'marketing_dashboard' },
  { path: '/marketing/comparativo', icon: BarChart3, label: 'Comparativo', modulo: 'marketing_comparativo' },
  { path: '/marketing/configuracoes', icon: Settings, label: 'Configuracoes', modulo: 'marketing_configuracoes' },
];

const detalheEventosItem = { path: '/marketing/detalhe', icon: Table2, label: 'Painel do evento', modulo: 'marketing_detalhe' };

const adminItems = [
  { path: '/admin/dados-consolidados', icon: Database, label: 'Dados Consolidados', modulo: 'admin_dados_consolidados' },
  { path: '/admin/sku-mappings', icon: Package, label: 'Mapeamento SKUs', modulo: 'admin_sku_mappings' },
  { path: '/admin/kit-config', icon: Layers, label: 'Mapeamento de Kits', modulo: 'admin_kit_config' },
  { path: '/admin/modalidade-aliases', icon: ArrowRight, label: 'Configuração Modalidade', modulo: 'admin_sku_mappings' },
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
  const isMobileViewport = () =>
    typeof window !== 'undefined' && window.matchMedia('(max-width: 1023px)').matches;
  const [sidebarOpen, setSidebarOpen] = useState(() => !isMobileViewport());

  // Fecha sidebar automaticamente ao trocar de rota em mobile
  useEffect(() => {
    if (isMobileViewport()) {
      setSidebarOpen(false);
    }
  }, [location.pathname]);

  // Bloqueia scroll do body quando o drawer está aberto em mobile (overlay UX).
  // Refcount inteiro em data-scroll-lock-count para conviver com outros componentes que também
  // travam scroll. Cada chamada de "acquire" incrementa, cada "release" decrementa; o overflow
  // só volta quando o contador chega a 0. Reavalia em resize/orientationchange para soltar o
  // lock se o viewport ficar desktop (>=768px) sem fechar o menu.
  useEffect(() => {
    let held = false;

    const acquire = () => {
      if (held) return;
      const body = document.body;
      const next = Number(body.dataset.scrollLockCount || '0') + 1;
      body.dataset.scrollLockCount = String(next);
      body.style.overflow = 'hidden';
      held = true;
    };

    const release = () => {
      if (!held) return;
      const body = document.body;
      const next = Math.max(0, Number(body.dataset.scrollLockCount || '0') - 1);
      body.dataset.scrollLockCount = String(next);
      if (next === 0) {
        body.style.overflow = '';
        delete body.dataset.scrollLockCount;
      }
      held = false;
    };

    const apply = () => {
      if (sidebarOpen && isMobileViewport()) acquire();
      else release();
    };

    apply();
    window.addEventListener('resize', apply);
    window.addEventListener('orientationchange', apply);
    return () => {
      window.removeEventListener('resize', apply);
      window.removeEventListener('orientationchange', apply);
      release();
    };
  }, [sidebarOpen]);
  const [marketingOpen, setMarketingOpen] = useState(location.pathname.startsWith('/marketing'));
  const [adminOpen, setAdminOpen] = useState(location.pathname.startsWith('/admin'));
  const [healthStatus, setHealthStatus] = useState<'healthy' | 'warning' | 'critical' | 'info' | null>(null);
  const [unconfiguredKits, setUnconfiguredKits] = useState<{
    total: number;
    events: Array<{ nome_evento: string; count: number }>;
  } | null>(null);
  const [kitsBannerDismissed, setKitsBannerDismissed] = useState(false);
  const [projecaoPendencias, setProjecaoPendencias] = useState<{
    total_eventos: number;
    total_areas: number;
    pendencias: Array<{
      evento_id: number;
      evento_nome: string;
      dias_ate_evento: number;
      cutoff_dias: number;
    }>;
  } | null>(null);

  const isAdmin = canView('admin_monitoramento');
  const canViewProjecao = canView('projecao_inscritos');

  const fetchHealthStatus = useCallback(async () => {
    if (!isAdmin) return;
    if (document.hidden) return;
    try {
      const { adminService } = await import('../../services/api');
      const data = await adminService.getHealthSummary();
      setHealthStatus(data.status);
    } catch {
    }
  }, [isAdmin]);

  const fetchUnconfiguredKits = useCallback(async () => {
    if (!isAdmin) return;
    if (document.hidden) return;
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

  const fetchProjecaoPendencias = useCallback(async () => {
    if (!canViewProjecao) return;
    if (document.hidden) return;
    try {
      const { projecaoService } = await import('../../services/api');
      const data = await projecaoService.getPendencias();
      setProjecaoPendencias(data);
    } catch {
    }
  }, [canViewProjecao]);

  useEffect(() => {
    if (!isAdmin) return;
    fetchHealthStatus();
    const interval = setInterval(fetchHealthStatus, 60000);
    return () => clearInterval(interval);
  }, [fetchHealthStatus, isAdmin]);

  useEffect(() => {
    if (!isAdmin) return;
    fetchUnconfiguredKits();
    const interval = setInterval(fetchUnconfiguredKits, 300000);
    return () => clearInterval(interval);
  }, [fetchUnconfiguredKits, isAdmin]);

  useEffect(() => {
    if (!canViewProjecao) return;
    fetchProjecaoPendencias();
    const interval = setInterval(fetchProjecaoPendencias, 180000);
    return () => clearInterval(interval);
  }, [fetchProjecaoPendencias, canViewProjecao]);

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const baseCadastroItems = menuItems.filter(item => item.path.includes('/cadastros/') && canView(item.modulo));
  const mainItems = menuItems.filter(item => !item.path.includes('/cadastros/') && canView(item.modulo));
  const filteredCotacaoItems = cotacaoItems.filter(item => canView(item.modulo));
  const filteredMarketingItems = marketingItems.filter(item => canView(item.modulo));
  const showProjecaoInscritos = canView(projecaoInscritosItem.modulo);
  const showSolicitacaoCortesias = canView(solicitacaoCortesiasItem.modulo);
  const cadastroItems = [...baseCadastroItems];
  if (showProjecaoInscritos) {
    const eventosIdx = cadastroItems.findIndex(item => item.path === '/cadastros/eventos');
    const insertAt = eventosIdx >= 0 ? eventosIdx + 1 : cadastroItems.length;
    cadastroItems.splice(insertAt, 0, projecaoInscritosItem, cortesiasItem);
  }
  if (showSolicitacaoCortesias) {
    const cortesiasIdx = cadastroItems.findIndex(item => item.path === '/cortesias');
    const insertAt = cortesiasIdx >= 0 ? cortesiasIdx + 1 : cadastroItems.length;
    cadastroItems.splice(insertAt, 0, solicitacaoCortesiasItem);
  }
  const filteredAdminItems = adminItems.filter(item => canView(item.modulo));
  const showDetalheEventos = canView(detalheEventosItem.modulo);

  return (
    <div className={`min-h-screen ${isDark ? 'dark bg-gray-900' : 'bg-gray-50'}`}>
      {sidebarOpen && (
        <button
          type="button"
          aria-label="Fechar menu"
          onClick={() => setSidebarOpen(false)}
          className="lg:hidden fixed inset-0 z-40 bg-black/50 backdrop-blur-sm"
        />
      )}
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

          {cadastroItems.map((item) => {
            const Icon = item.icon;
            const isActive = location.pathname === item.path;
            const isProjecao = item.path === '/projecao-inscritos';
            const pendCount = isProjecao && projecaoPendencias ? projecaoPendencias.total_eventos : 0;
            return (
              <Link
                key={item.path}
                to={item.path}
                className={`flex items-center justify-between px-4 py-2 rounded-lg transition-colors ${
                  isActive
                    ? 'bg-gradient-to-r from-indigo-600 to-purple-600 text-white'
                    : isDark
                    ? 'text-gray-300 hover:bg-gray-700'
                    : 'text-gray-600 hover:bg-gray-100'
                }`}
              >
                <span className="flex items-center min-w-0">
                  <Icon className="w-5 h-5 mr-3 flex-shrink-0" />
                  <span className="truncate">{item.label}</span>
                </span>
                {pendCount > 0 && (
                  <span
                    title={`${pendCount} evento(s) com projeção pendente`}
                    className={`ml-2 inline-flex items-center justify-center min-w-[1.25rem] h-5 px-1.5 rounded-full text-[10px] font-bold flex-shrink-0 ${
                      isActive
                        ? 'bg-white text-red-600'
                        : 'bg-red-500 text-white animate-pulse'
                    }`}
                  >
                    {pendCount}
                  </span>
                )}
              </Link>
            );
          })}

          {showDetalheEventos && (() => {
            const isActive = location.pathname === detalheEventosItem.path;
            const Icon = detalheEventosItem.icon;
            return (
              <Link
                to={detalheEventosItem.path}
                className={`flex items-center px-4 py-2 rounded-lg transition-colors ${
                  isActive
                    ? 'bg-gradient-to-r from-indigo-600 to-purple-600 text-white'
                    : isDark
                    ? 'text-gray-300 hover:bg-gray-700'
                    : 'text-gray-600 hover:bg-gray-100'
                }`}
              >
                <Icon className="w-5 h-5 mr-3" />
                {detalheEventosItem.label}
              </Link>
            );
          })()}

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

          {canView('manual_sistema') && (
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
          )}
        </nav>
      </aside>

      <div className={`${sidebarOpen ? 'lg:ml-64' : ''} transition-all duration-200 min-h-screen ${isDark ? 'bg-gray-900' : 'bg-gray-50'}`}>
        <header className={`sticky top-0 z-40 h-16 flex items-center justify-between px-4 ${isDark ? 'bg-gray-800 border-gray-700' : 'bg-white border-gray-200'} border-b shadow-sm`}>
          <button onClick={() => setSidebarOpen(!sidebarOpen)} className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700">
            <Menu className={isDark ? 'text-white' : 'text-gray-600'} />
          </button>
          
          <div className="flex items-center gap-2 sm:gap-3">
            {canViewProjecao && projecaoPendencias && projecaoPendencias.total_eventos > 0 && (
              <Link
                to="/projecao-inscritos"
                title={`${projecaoPendencias.total_eventos} evento(s) em ponto de corte sem projeção registrada`}
                className="flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium transition-colors border bg-red-500/10 text-red-500 border-red-500/40 hover:bg-red-500/20"
              >
                <span className="w-1.5 h-1.5 rounded-full bg-red-500 animate-pulse" />
                <AlertTriangle className="w-3.5 h-3.5" />
                {projecaoPendencias.total_eventos} projeç{projecaoPendencias.total_eventos !== 1 ? 'ões' : 'ão'} pendente{projecaoPendencias.total_eventos !== 1 ? 's' : ''}
              </Link>
            )}
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
            
            <Link to="/perfil" className={`flex items-center gap-2 text-sm hover:opacity-80 transition-opacity ${isDark ? 'text-gray-300' : 'text-gray-600'}`}>
              {user?.foto_perfil ? (
                <img src={user.foto_perfil} alt="" className="w-8 h-8 rounded-full object-cover border-2 border-indigo-300 dark:border-indigo-600" />
              ) : (
                <div className="w-8 h-8 rounded-full bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center text-white text-xs font-bold border-2 border-indigo-300 dark:border-indigo-600">
                  {user?.nome ? user.nome.split(' ').map(n => n[0]).slice(0, 2).join('').toUpperCase() : '?'}
                </div>
              )}
              <span className="hidden md:inline">{user?.nome}</span>
              <span className="hidden md:inline text-xs px-2 py-1 rounded bg-blue-100 text-blue-800 ml-1">{user?.perfil_acesso_nome || 'Sem perfil'}</span>
            </Link>
            
            <button onClick={handleLogout} className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 text-red-500">
              <LogOut className="w-5 h-5" />
            </button>
          </div>
        </header>


        <main className="p-3 sm:p-4 lg:p-6">
          {children}
        </main>
      </div>

      <NoriButton />
    </div>
  );
};

export default Layout;
