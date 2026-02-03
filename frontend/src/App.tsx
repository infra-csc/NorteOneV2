import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import { ThemeProvider } from './context/ThemeContext';
import Layout from './components/common/Layout';
import Login from './pages/auth/Login';
import Dashboard from './pages/dashboard/Dashboard';
import CentrosCusto from './pages/cadastros/CentrosCusto';
import Contas from './pages/cadastros/Contas';
import Projetos from './pages/cadastros/Projetos';
import CategoriasAtletas from './pages/cadastros/CategoriasAtletas';
import Cadastro from './pages/cadastros/Cadastro';
import Orcamento from './pages/Orcamento';
import Atletas from './pages/Atletas';
import MarketingDashboard from './pages/marketing/MarketingDashboard';
import EventDetail from './pages/marketing/EventDetail';
import EventComparison from './pages/marketing/EventComparison';
import MarketingSettings from './pages/marketing/MarketingSettings';
import NoriAssistant from './pages/nori/NoriAssistant';
import DadosConsolidados from './pages/admin/DadosConsolidados';
import Usuarios from './pages/admin/Usuarios';

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
        <Router>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route path="/" element={<PrivateRoute><Layout><Dashboard /></Layout></PrivateRoute>} />
                        <Route path="/cadastros/projetos" element={<PrivateRoute><Layout><Projetos /></Layout></PrivateRoute>} />
            <Route path="/cadastros/categorias-atletas" element={<PrivateRoute><Layout><CategoriasAtletas /></Layout></PrivateRoute>} />
            <Route path="/cadastros/cadastro" element={<PrivateRoute><Layout><Cadastro /></Layout></PrivateRoute>} />
            <Route path="/orcamento" element={<PrivateRoute><Layout><Orcamento /></Layout></PrivateRoute>} />
            <Route path="/atletas" element={<PrivateRoute><Layout><Atletas /></Layout></PrivateRoute>} />
            <Route path="/marketing" element={<PrivateRoute><Layout><MarketingDashboard /></Layout></PrivateRoute>} />
            <Route path="/marketing/evento/:id" element={<PrivateRoute><Layout><EventDetail /></Layout></PrivateRoute>} />
            <Route path="/marketing/comparativo" element={<PrivateRoute><Layout><EventComparison /></Layout></PrivateRoute>} />
            <Route path="/marketing/configuracoes" element={<PrivateRoute><Layout><MarketingSettings /></Layout></PrivateRoute>} />
            <Route path="/nori" element={<PrivateRoute><Layout><NoriAssistant /></Layout></PrivateRoute>} />
            <Route path="/admin/dados-consolidados" element={<PrivateRoute><Layout><DadosConsolidados /></Layout></PrivateRoute>} />
            <Route path="/admin/usuarios" element={<PrivateRoute><Layout><Usuarios /></Layout></PrivateRoute>} />
            <Route path="/admin/centros-custo" element={<PrivateRoute><Layout><CentrosCusto /></Layout></PrivateRoute>} />
            <Route path="/admin/contas" element={<PrivateRoute><Layout><Contas /></Layout></PrivateRoute>} />
          </Routes>
        </Router>
      </AuthProvider>
    </ThemeProvider>
  );
}

export default App;
