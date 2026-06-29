import React, { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { motion } from 'framer-motion';
import { AlertCircle } from 'lucide-react';

const StaticBackground = () => (
  <div style={{
    position: 'fixed', top: 0, left: 0, width: '100%', height: '100%', zIndex: 0,
    background: 'linear-gradient(135deg, #0a0e27 0%, #0d1340 30%, #0a1628 60%, #050a18 100%)',
  }} />
);

/**
 * Página de retorno do SSO Microsoft. O backend redireciona para cá com o JWT
 * da aplicação no fragmento da URL (#token=...) em caso de sucesso, ou com
 * ?sso_error=... em caso de falha. Aqui consumimos o token, autenticamos e
 * redirecionamos para a home.
 */
const MicrosoftCallback: React.FC = () => {
  const { loginWithToken } = useAuth();
  const navigate = useNavigate();
  const [error, setError] = useState('');
  const handled = useRef(false);

  useEffect(() => {
    if (handled.current) return;
    handled.current = true;

    const queryError = new URLSearchParams(window.location.search).get('sso_error');
    if (queryError) {
      navigate(`/login?sso_error=${encodeURIComponent(queryError)}`, { replace: true });
      return;
    }

    const fragment = new URLSearchParams(window.location.hash.replace(/^#/, ''));
    const token = fragment.get('token');
    if (!token) {
      navigate('/login?sso_error=' + encodeURIComponent('Falha no login com a Microsoft.'), { replace: true });
      return;
    }

    // Remove o token da URL imediatamente (não deve ficar no histórico).
    window.history.replaceState({}, '', '/auth/microsoft/callback');

    loginWithToken(token)
      .then(() => navigate('/', { replace: true }))
      .catch(() => {
        setError('Não foi possível concluir o login. Tente novamente.');
        setTimeout(() => navigate('/login', { replace: true }), 2500);
      });
  }, [loginWithToken, navigate]);

  return (
    <div className="min-h-screen flex items-center justify-center relative overflow-hidden">
      <StaticBackground />
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        className="relative z-10 text-center"
      >
        {error ? (
          <div className="flex items-center text-sm px-6 py-4 rounded-xl" style={{
            background: 'rgba(255, 59, 48, 0.12)',
            border: '1px solid rgba(255, 59, 48, 0.2)',
            color: '#ff6b6b',
          }}>
            <AlertCircle className="w-4 h-4 mr-3 flex-shrink-0" />
            {error}
          </div>
        ) : (
          <>
            <motion.div
              className="w-10 h-10 border-2 border-white/20 border-t-white rounded-full mx-auto mb-4"
              animate={{ rotate: 360 }}
              transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}
            />
            <p className="text-sm" style={{ color: 'rgba(255, 255, 255, 0.5)' }}>
              Concluindo o login com a Microsoft...
            </p>
          </>
        )}
      </motion.div>
    </div>
  );
};

export default MicrosoftCallback;
