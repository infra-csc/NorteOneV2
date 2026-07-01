import React, { useState, useEffect, useRef, lazy, Suspense } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { authService } from '../../services/api';
import { LogIn, AlertCircle, Mail, Lock, Eye, EyeOff } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

const MicrosoftLogo = () => (
  <svg className="w-4 h-4 mr-2" viewBox="0 0 21 21" aria-hidden="true">
    <rect x="1" y="1" width="9" height="9" fill="#f25022" />
    <rect x="11" y="1" width="9" height="9" fill="#7fba00" />
    <rect x="1" y="11" width="9" height="9" fill="#00a4ef" />
    <rect x="11" y="11" width="9" height="9" fill="#ffb900" />
  </svg>
);

// Estado do SSO cacheado no navegador (acesso protegido contra ambientes que
// bloqueiam localStorage, ex.: modo privado restrito). Nunca deve lançar.
const SSO_CACHE_KEY = 'sso_enabled';
const readSsoCache = (): boolean => {
  try {
    return localStorage.getItem(SSO_CACHE_KEY) === '1';
  } catch {
    return false;
  }
};
const writeSsoCache = (enabled: boolean): void => {
  try {
    localStorage.setItem(SSO_CACHE_KEY, enabled ? '1' : '0');
  } catch {
    /* localStorage indisponível — ignora */
  }
};

const Background3D = lazy(() => import('../../components/3d/Background3D'));

const StaticBackground = () => (
  <div style={{
    position: 'fixed', top: 0, left: 0, width: '100%', height: '100%', zIndex: 0,
    background: 'linear-gradient(135deg, #0a0e27 0%, #0d1340 30%, #0a1628 60%, #050a18 100%)',
  }} />
);

const Login: React.FC = () => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [focusedField, setFocusedField] = useState<string | null>(null);
  // Lembramos o último estado conhecido do SSO no navegador. Assim o botão
  // Microsoft aparece IMEDIATAMENTE em acessos seguintes, mesmo que a checagem
  // de status esteja lenta (servidor saturado) ou falhe. Uma instabilidade no
  // Magento/servidor nunca deve impedir o usuário de entrar via Microsoft.
  const ssoWasEnabled = readSsoCache();
  const [ssoEnabled, setSsoEnabled] = useState(ssoWasEnabled);
  // Quando o SSO está ativo, o login padrão é só Microsoft; o formulário de
  // e-mail/senha fica escondido atrás do "acesso de emergência" (break-glass).
  const [showLocalLogin, setShowLocalLogin] = useState(!ssoWasEnabled);
  // Marca se o usuário abriu explicitamente o acesso de emergência nesta sessão,
  // para que a revalidação em segundo plano não feche o formulário sob seus pés.
  const emergencyOpenedRef = useRef(false);
  const { login } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    // Revalida em segundo plano. Sucesso atualiza e persiste o estado.
    authService.microsoftStatus()
      .then((s) => {
        const enabled = !!s.enabled;
        setSsoEnabled(enabled);
        // SSO ativo => Microsoft-first (esconde local), a menos que o usuário
        // tenha aberto o acesso de emergência. SSO inativo => mostra local.
        setShowLocalLogin(enabled ? emergencyOpenedRef.current : true);
        writeSsoCache(enabled);
      })
      .catch(() => {
        // Falha na checagem (timeout/rede/servidor saturado): NÃO escondemos o
        // botão se já sabíamos que o SSO está ligado. Falha "aberto".
        if (!ssoWasEnabled) {
          setSsoEnabled(false);
          setShowLocalLogin(true);
        }
      });

    // Exibe erro vindo do callback do SSO (?sso_error=...).
    const params = new URLSearchParams(window.location.search);
    const ssoError = params.get('sso_error');
    if (ssoError) {
      setError(ssoError);
      const url = new URL(window.location.href);
      url.searchParams.delete('sso_error');
      window.history.replaceState({}, '', url.pathname + url.search);
    }
  }, []);

  const handleMicrosoftLogin = () => {
    // Full-page redirect para o backend, que redireciona à Microsoft.
    window.location.href = authService.microsoftLoginUrl();
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      await login(email, password);
      navigate('/');
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Erro ao fazer login');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center relative overflow-hidden">
      <Suspense fallback={<StaticBackground />}>
        <Background3D />
      </Suspense>

      <motion.div
        initial={{ opacity: 0, y: 40, scale: 0.95 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
        className="relative z-10 w-full max-w-md mx-4"
      >
        <div
          className="relative rounded-3xl p-8 md:p-10 overflow-hidden"
          style={{
            background: 'rgba(255, 255, 255, 0.06)',
            backdropFilter: 'blur(24px)',
            WebkitBackdropFilter: 'blur(24px)',
            border: '1px solid rgba(255, 255, 255, 0.1)',
            boxShadow: '0 32px 64px rgba(0, 0, 0, 0.4), inset 0 1px 0 rgba(255, 255, 255, 0.1)',
          }}
        >
          <div
            className="absolute inset-0 rounded-3xl pointer-events-none"
            style={{
              background: 'linear-gradient(135deg, rgba(26, 79, 255, 0.08) 0%, rgba(255, 68, 0, 0.04) 100%)',
            }}
          />

          <div className="relative z-10">
            <motion.div
              initial={{ opacity: 0, y: -20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.3, duration: 0.6 }}
              className="text-center mb-8"
            >
              <motion.div
                className="flex justify-center mb-4"
                animate={{
                  filter: [
                    'drop-shadow(0 0 8px rgba(26, 79, 255, 0.3))',
                    'drop-shadow(0 0 20px rgba(26, 79, 255, 0.6))',
                    'drop-shadow(0 0 8px rgba(26, 79, 255, 0.3))',
                  ],
                }}
                transition={{ duration: 3, repeat: Infinity, ease: 'easeInOut' }}
              >
                <img
                  src="/logo-norte.png"
                  alt="Norte"
                  className="h-12 object-contain"
                  style={{ filter: 'brightness(1.2)' }}
                />
              </motion.div>
              <motion.p
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: 0.6, duration: 0.5 }}
                className="text-sm tracking-[0.3em] uppercase"
                style={{ color: 'rgba(255, 255, 255, 0.4)' }}
                translate="no"
              >
                Dados que guiam decisões
              </motion.p>
            </motion.div>

            <AnimatePresence>
              {error && (
                <motion.div
                  initial={{ opacity: 0, height: 0, y: -10 }}
                  animate={{ opacity: 1, height: 'auto', y: 0 }}
                  exit={{ opacity: 0, height: 0, y: -10 }}
                  transition={{ duration: 0.3 }}
                  className="mb-6 p-4 rounded-xl flex items-center text-sm"
                  style={{
                    background: 'rgba(255, 59, 48, 0.12)',
                    border: '1px solid rgba(255, 59, 48, 0.2)',
                    color: '#ff6b6b',
                  }}
                >
                  <AlertCircle className="w-4 h-4 mr-3 flex-shrink-0" />
                  {error}
                </motion.div>
              )}
            </AnimatePresence>

            {ssoEnabled && (
              <motion.div
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.4, duration: 0.5 }}
                className="mb-2"
              >
                <motion.button
                  type="button"
                  onClick={handleMicrosoftLogin}
                  whileHover={{ scale: 1.02, boxShadow: '0 8px 32px rgba(26, 79, 255, 0.4)' }}
                  whileTap={{ scale: 0.98 }}
                  className="w-full py-4 rounded-xl font-semibold text-sm tracking-wide flex items-center justify-center transition-all cursor-pointer text-white"
                  style={{
                    background: 'linear-gradient(135deg, #1a4fff 0%, #0033cc 50%, #ff4400 150%)',
                    boxShadow: '0 4px 16px rgba(26, 79, 255, 0.3)',
                  }}
                >
                  <MicrosoftLogo />
                  Entrar com Microsoft
                </motion.button>

                {!showLocalLogin && (
                  <button
                    type="button"
                    onClick={() => { emergencyOpenedRef.current = true; setShowLocalLogin(true); setError(''); }}
                    className="w-full mt-4 text-center text-xs tracking-wider transition-colors"
                    style={{ color: 'rgba(255, 255, 255, 0.3)' }}
                  >
                    Acesso de emergência (e-mail e senha)
                  </button>
                )}
              </motion.div>
            )}

            {ssoEnabled && showLocalLogin && (
              <div className="flex items-center my-4">
                <div className="flex-1 h-px" style={{ background: 'rgba(255,255,255,0.1)' }} />
                <span className="px-3 text-xs uppercase tracking-wider" style={{ color: 'rgba(255,255,255,0.3)' }}>
                  acesso de emergência
                </span>
                <div className="flex-1 h-px" style={{ background: 'rgba(255,255,255,0.1)' }} />
              </div>
            )}

            {showLocalLogin && (
            <form onSubmit={handleSubmit} className="space-y-5">
              <motion.div
                initial={{ opacity: 0, x: -20 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: 0.4, duration: 0.5 }}
              >
                <label className="block text-xs font-medium mb-2 tracking-wider uppercase" style={{ color: 'rgba(255, 255, 255, 0.5)' }}>
                  Email
                </label>
                <div
                  className="relative group"
                  style={{
                    borderRadius: '14px',
                    padding: '1px',
                    background: focusedField === 'email'
                      ? 'linear-gradient(135deg, #1a4fff, #ff4400)'
                      : 'rgba(255, 255, 255, 0.1)',
                    transition: 'background 0.3s ease',
                  }}
                >
                  <div
                    className="flex items-center"
                    style={{
                      borderRadius: '13px',
                      background: 'rgba(0, 0, 0, 0.3)',
                    }}
                  >
                    <Mail className="w-4 h-4 ml-4 flex-shrink-0" style={{ color: focusedField === 'email' ? '#1a4fff' : 'rgba(255, 255, 255, 0.3)' }} />
                    <input
                      type="email"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      onFocus={() => setFocusedField('email')}
                      onBlur={() => setFocusedField(null)}
                      className="w-full px-3 py-3.5 bg-transparent border-none outline-none text-white placeholder-white/25 text-sm"
                      placeholder="seu@email.com"
                      required
                    />
                  </div>
                </div>
              </motion.div>

              <motion.div
                initial={{ opacity: 0, x: -20 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: 0.5, duration: 0.5 }}
              >
                <label className="block text-xs font-medium mb-2 tracking-wider uppercase" style={{ color: 'rgba(255, 255, 255, 0.5)' }}>
                  Senha
                </label>
                <div
                  className="relative group"
                  style={{
                    borderRadius: '14px',
                    padding: '1px',
                    background: focusedField === 'password'
                      ? 'linear-gradient(135deg, #1a4fff, #ff4400)'
                      : 'rgba(255, 255, 255, 0.1)',
                    transition: 'background 0.3s ease',
                  }}
                >
                  <div
                    className="flex items-center"
                    style={{
                      borderRadius: '13px',
                      background: 'rgba(0, 0, 0, 0.3)',
                    }}
                  >
                    <Lock className="w-4 h-4 ml-4 flex-shrink-0" style={{ color: focusedField === 'password' ? '#1a4fff' : 'rgba(255, 255, 255, 0.3)' }} />
                    <input
                      type={showPassword ? 'text' : 'password'}
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      onFocus={() => setFocusedField('password')}
                      onBlur={() => setFocusedField(null)}
                      className="w-full px-3 py-3.5 bg-transparent border-none outline-none text-white placeholder-white/25 text-sm"
                      placeholder="••••••••"
                      required
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword(!showPassword)}
                      className="pr-4 focus:outline-none"
                      style={{ color: 'rgba(255, 255, 255, 0.3)' }}
                      tabIndex={-1}
                    >
                      {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                    </button>
                  </div>
                </div>
              </motion.div>

              <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.6, duration: 0.5 }}
                className="pt-2"
              >
                <motion.button
                  type="submit"
                  disabled={loading}
                  whileHover={{ scale: 1.02, boxShadow: '0 8px 32px rgba(26, 79, 255, 0.4)' }}
                  whileTap={{ scale: 0.98 }}
                  className="w-full py-4 rounded-xl font-semibold text-sm tracking-wide flex items-center justify-center disabled:opacity-50 transition-all cursor-pointer text-white"
                  style={{
                    background: 'linear-gradient(135deg, #1a4fff 0%, #0033cc 50%, #ff4400 150%)',
                    boxShadow: '0 4px 16px rgba(26, 79, 255, 0.3)',
                  }}
                >
                  {loading ? (
                    <motion.div
                      className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full"
                      animate={{ rotate: 360 }}
                      transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}
                    />
                  ) : (
                    <>
                      <LogIn className="w-4 h-4 mr-2" />
                      Entrar
                    </>
                  )}
                </motion.button>
              </motion.div>
            </form>
            )}

            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.8, duration: 0.5 }}
              className="mt-8 text-center"
            >
              <p className="text-xs" style={{ color: 'rgba(255, 255, 255, 0.2)' }}>
                Norte &copy; {new Date().getFullYear()}
              </p>
            </motion.div>
          </div>
        </div>
      </motion.div>
    </div>
  );
};

export default Login;
