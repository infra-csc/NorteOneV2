import { lazy, Suspense } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import { ThemeProvider } from './context/ThemeContext';
import { PermissionProvider, usePermissions } from './context/PermissionContext';
import Layout from './components/common/Layout';
import ErrorBoundary from './components/common/ErrorBoundary';
import Login from './pages/auth/Login';
import PWAManager from './pwa/PWAManager';

// Wrapper para lazy imports: quando o chunk está stale (após deploy ou HMR
// full-reload), o browser recebe 404 ao tentar carregar a URL antiga.
// Nesse caso recarregamos a página uma vez para buscar o novo bundle.
const lazyWithRetry = (factory: () => Promise<any>) =>
  lazy(() =>
    factory().catch(() => {
      const reloaded = sessionStorage.getItem('chunk-reload-attempted');
      if (!reloaded) {
        sessionStorage.setItem('chunk-reload-attempted', '1');
        window.location.reload();
      }
      // Retorna módulo vazio enquanto a página recarrega
      return { default: () => null };
    })
  );

const Dashboard = lazyWithRetry(() => import('./pages/dashboard/Dashboard'));
const CentrosCusto = lazyWithRetry(() => import('./pages/cadastros/CentrosCusto'));
const CategoriasAtletas = lazyWithRetry(() => import('./pages/cadastros/CategoriasAtletas'));
const Eventos = lazyWithRetry(() => import('./pages/cadastros/Cadastro'));
const MarketingDashboard = lazyWithRetry(() => import('./pages/marketing/MarketingDashboard'));
const EventDetail = lazyWithRetry(() => import('./pages/marketing/EventDetail'));
const EventOpsView = lazyWithRetry(() => import('./pages/marketing/EventOpsView'));
const EventComparison = lazyWithRetry(() => import('./pages/marketing/EventComparison'));
const MarketingSettings = lazyWithRetry(() => import('./pages/marketing/MarketingSettings'));
const PlaybookPage = lazyWithRetry(() => import('./pages/marketing/PlaybookPage'));
const NoriAssistant = lazyWithRetry(() => import('./pages/nori/NoriAssistant'));
const DadosConsolidados = lazyWithRetry(() => import('./pages/admin/DadosConsolidados'));
const Usuarios = lazyWithRetry(() => import('./pages/admin/Usuarios'));
const SkuMappings = lazyWithRetry(() => import('./pages/admin/SkuMappings'));
const PerfisAcesso = lazyWithRetry(() => import('./pages/admin/PerfisAcesso'));
const MonitoramentoUsuarios = lazyWithRetry(() => import('./pages/admin/MonitoramentoUsuarios'));
const KitConfig = lazyWithRetry(() => import('./pages/admin/KitConfig'));
const SaudeSistema = lazyWithRetry(() => import('./pages/admin/SaudeSistema'));
const CotacoesImportacao = lazyWithRetry(() => import('./pages/cotacoes/CotacoesImportacao'));
const ManualSistema = lazyWithRetry(() => import('./pages/manual/ManualSistema'));
const ProjecaoInscritos = lazyWithRetry(() => import('./pages/cadastros/ProjecaoInscritos'));
const Profile = lazyWithRetry(() => import('./pages/profile/Profile'));


const PageLoader = () => (
  <div className="min-h-screen flex items-center justify-center">
    <div className="w-8 h-8 border-4 border-blue-500 border-t-transparent rounded-full animate-spin" />
  </div>
);

const PrivateRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { user, isLoading } = useAuth();
  
  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="w-8 h-8 border-4 border-blue-500 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }
  
  return user ? <>{children}</> : <Navigate to="/login" />;
};

const PermissionRoute: React.FC<{ children: React.ReactNode; module: string; fallback?: string }> = ({ children, module, fallback = '/manual' }) => {
  const { user, isLoading: authLoading } = useAuth();
  const { canView, isLoading: permLoading } = usePermissions();

  if (authLoading || permLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="w-8 h-8 border-4 border-blue-500 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  if (!user) return <Navigate to="/login" />;
  if (!canView(module)) return <Navigate to={fallback} />;
  return <>{children}</>;
};

function App() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <PermissionProvider>
        <Router>
          <ErrorBoundary>
          <Suspense fallback={<PageLoader />}>
            <Routes>
              <Route path="/login" element={<Login />} />
              <Route path="/" element={<PermissionRoute module="dashboard"><Layout><Dashboard /></Layout></PermissionRoute>} />
              <Route path="/cadastros/categorias-atletas" element={<PermissionRoute module="categorias_atletas"><Layout><CategoriasAtletas /></Layout></PermissionRoute>} />
              <Route path="/cadastros/eventos" element={<PermissionRoute module="eventos"><Layout><Eventos /></Layout></PermissionRoute>} />
              <Route path="/marketing" element={<PermissionRoute module="marketing_dashboard"><Layout><MarketingDashboard /></Layout></PermissionRoute>} />
              <Route path="/marketing/evento/:id" element={<PermissionRoute module="marketing_dashboard"><Layout><ErrorBoundary fallbackNavigate="/marketing"><EventDetail /></ErrorBoundary></Layout></PermissionRoute>} />
              <Route path="/marketing/evento/:id/operacao" element={<PermissionRoute module="marketing_dashboard"><ErrorBoundary fallbackNavigate="/marketing"><EventOpsView /></ErrorBoundary></PermissionRoute>} />
              <Route path="/marketing/comparativo" element={<PermissionRoute module="marketing_comparativo"><Layout><EventComparison /></Layout></PermissionRoute>} />
              <Route path="/marketing/configuracoes" element={<PermissionRoute module="marketing_configuracoes"><Layout><MarketingSettings /></Layout></PermissionRoute>} />
              <Route path="/marketing/playbook" element={<PermissionRoute module="marketing_dashboard"><PlaybookPage /></PermissionRoute>} />
              <Route path="/nori" element={<PermissionRoute module="nori"><Layout><NoriAssistant /></Layout></PermissionRoute>} />
              <Route path="/admin/dados-consolidados" element={<PermissionRoute module="admin_dados_consolidados"><Layout><DadosConsolidados /></Layout></PermissionRoute>} />
              <Route path="/admin/usuarios" element={<PermissionRoute module="admin_usuarios"><Layout><Usuarios /></Layout></PermissionRoute>} />
              <Route path="/admin/sku-mappings" element={<PermissionRoute module="admin_sku_mappings"><Layout><SkuMappings /></Layout></PermissionRoute>} />
              <Route path="/admin/kit-config" element={<PermissionRoute module="admin_kit_config"><Layout><KitConfig /></Layout></PermissionRoute>} />
              <Route path="/admin/centros-custo" element={<PermissionRoute module="admin_centros_custo"><Layout><CentrosCusto /></Layout></PermissionRoute>} />
              <Route path="/admin/perfis-acesso" element={<PermissionRoute module="admin_perfis_acesso"><Layout><PerfisAcesso /></Layout></PermissionRoute>} />
              <Route path="/admin/monitoramento" element={<PermissionRoute module="admin_monitoramento"><Layout><MonitoramentoUsuarios /></Layout></PermissionRoute>} />
              <Route path="/admin/saude-sistema" element={<PermissionRoute module="admin_monitoramento"><Layout><SaudeSistema /></Layout></PermissionRoute>} />
              <Route path="/projecao-inscritos" element={<PermissionRoute module="projecao_inscritos"><Layout><ProjecaoInscritos /></Layout></PermissionRoute>} />
              <Route path="/cotacoes" element={<PermissionRoute module="cotacoes_importacao"><Layout><CotacoesImportacao /></Layout></PermissionRoute>} />
              <Route path="/manual" element={<PrivateRoute><Layout><ManualSistema /></Layout></PrivateRoute>} />
              <Route path="/perfil" element={<PrivateRoute><Layout><Profile /></Layout></PrivateRoute>} />
            </Routes>
          </Suspense>
          <PWAManager />
          </ErrorBoundary>
        </Router>
        </PermissionProvider>
      </AuthProvider>
    </ThemeProvider>
  );
}

export default App;
