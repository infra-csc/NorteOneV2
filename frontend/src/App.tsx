import { lazy, Suspense } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import { ThemeProvider } from './context/ThemeContext';
import { PermissionProvider } from './context/PermissionContext';
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
              <Route path="/cadastros/categorias-atletas" element={<PrivateRoute><Layout><CategoriasAtletas /></Layout></PrivateRoute>} />
              <Route path="/cadastros/eventos" element={<PrivateRoute><Layout><Eventos /></Layout></PrivateRoute>} />
              <Route path="/marketing" element={<PrivateRoute><Layout><MarketingDashboard /></Layout></PrivateRoute>} />
              <Route path="/marketing/evento/:id" element={<PrivateRoute><Layout><ErrorBoundary fallbackNavigate="/marketing"><EventDetail /></ErrorBoundary></Layout></PrivateRoute>} />
              <Route path="/marketing/evento/:id/operacao" element={<PrivateRoute><ErrorBoundary fallbackNavigate="/marketing"><EventOpsView /></ErrorBoundary></PrivateRoute>} />
              <Route path="/marketing/comparativo" element={<PrivateRoute><Layout><EventComparison /></Layout></PrivateRoute>} />
              <Route path="/marketing/configuracoes" element={<PrivateRoute><Layout><MarketingSettings /></Layout></PrivateRoute>} />
              <Route path="/marketing/playbook" element={<PrivateRoute><PlaybookPage /></PrivateRoute>} />
              <Route path="/nori" element={<PrivateRoute><Layout><NoriAssistant /></Layout></PrivateRoute>} />
              <Route path="/admin/dados-consolidados" element={<PrivateRoute><Layout><DadosConsolidados /></Layout></PrivateRoute>} />
              <Route path="/admin/usuarios" element={<PrivateRoute><Layout><Usuarios /></Layout></PrivateRoute>} />
              <Route path="/admin/sku-mappings" element={<PrivateRoute><Layout><SkuMappings /></Layout></PrivateRoute>} />

              <Route path="/admin/kit-config" element={<PrivateRoute><Layout><KitConfig /></Layout></PrivateRoute>} />
              <Route path="/admin/centros-custo" element={<PrivateRoute><Layout><CentrosCusto /></Layout></PrivateRoute>} />
              <Route path="/admin/perfis-acesso" element={<PrivateRoute><Layout><PerfisAcesso /></Layout></PrivateRoute>} />
              <Route path="/admin/monitoramento" element={<PrivateRoute><Layout><MonitoramentoUsuarios /></Layout></PrivateRoute>} />
              <Route path="/admin/saude-sistema" element={<PrivateRoute><Layout><SaudeSistema /></Layout></PrivateRoute>} />
              <Route path="/projecao-inscritos" element={<PrivateRoute><Layout><ProjecaoInscritos /></Layout></PrivateRoute>} />
              <Route path="/cotacoes" element={<PrivateRoute><Layout><CotacoesImportacao /></Layout></PrivateRoute>} />
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
