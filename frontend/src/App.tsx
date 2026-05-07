import { lazy, Suspense } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import { ThemeProvider } from './context/ThemeContext';
import { PermissionProvider, usePermissions } from './context/PermissionContext';
import Layout from './components/common/Layout';
import ErrorBoundary from './components/common/ErrorBoundary';
import Login from './pages/auth/Login';
import PWAManager from './pwa/PWAManager';

const Dashboard = lazy(() => import('./pages/dashboard/Dashboard'));
const CentrosCusto = lazy(() => import('./pages/cadastros/CentrosCusto'));
const CategoriasAtletas = lazy(() => import('./pages/cadastros/CategoriasAtletas'));
const Eventos = lazy(() => import('./pages/cadastros/Cadastro'));
const MarketingDashboard = lazy(() => import('./pages/marketing/MarketingDashboard'));
const EventDetail = lazy(() => import('./pages/marketing/EventDetail'));
const EventOpsView = lazy(() => import('./pages/marketing/EventOpsView'));
const EventComparison = lazy(() => import('./pages/marketing/EventComparison'));
const MarketingSettings = lazy(() => import('./pages/marketing/MarketingSettings'));
const PlaybookPage = lazy(() => import('./pages/marketing/PlaybookPage'));
const NoriAssistant = lazy(() => import('./pages/nori/NoriAssistant'));
const DadosConsolidados = lazy(() => import('./pages/admin/DadosConsolidados'));
const Usuarios = lazy(() => import('./pages/admin/Usuarios'));
const SkuMappings = lazy(() => import('./pages/admin/SkuMappings'));
const PerfisAcesso = lazy(() => import('./pages/admin/PerfisAcesso'));
const MonitoramentoUsuarios = lazy(() => import('./pages/admin/MonitoramentoUsuarios'));
const KitConfig = lazy(() => import('./pages/admin/KitConfig'));
const SaudeSistema = lazy(() => import('./pages/admin/SaudeSistema'));
const CotacoesImportacao = lazy(() => import('./pages/cotacoes/CotacoesImportacao'));
const ManualSistema = lazy(() => import('./pages/manual/ManualSistema'));
const ProjecaoInscritos = lazy(() => import('./pages/cadastros/ProjecaoInscritos'));
const Profile = lazy(() => import('./pages/profile/Profile'));


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

const PermissionRoute: React.FC<{ children: React.ReactNode; module: string }> = ({ children, module }) => {
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
  if (!canView(module)) return <Navigate to="/" />;
  return <>{children}</>;
};

function App() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <PermissionProvider>
        <Router>
          <Suspense fallback={<PageLoader />}>
            <Routes>
              <Route path="/login" element={<Login />} />
              <Route path="/" element={<PrivateRoute><Layout><Dashboard /></Layout></PrivateRoute>} />
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
        </Router>
        </PermissionProvider>
      </AuthProvider>
    </ThemeProvider>
  );
}

export default App;
