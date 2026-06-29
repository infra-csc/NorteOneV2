import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { User } from '../types';
import { authService } from '../services/api';

interface AuthContextType {
  user: User | null;
  token: string | null;
  login: (email: string, password: string) => Promise<void>;
  loginWithToken: (accessToken: string) => Promise<void>;
  logout: () => void;
  refreshUser: () => Promise<void>;
  isLoading: boolean;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(localStorage.getItem('token'));
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const loadUser = async () => {
      if (token) {
        try {
          const userData = await authService.getMe();
          setUser(userData);
        } catch (error) {
          localStorage.removeItem('token');
          setToken(null);
        }
      }
      setIsLoading(false);
    };
    loadUser();
  }, [token]);

  const login = async (email: string, password: string) => {
    const data = await authService.login(email, password);
    localStorage.setItem('token', data.access_token);
    setToken(data.access_token);
    const userData = await authService.getMe();
    setUser(userData);
  };

  // Usado pelo callback do SSO Microsoft: o backend já emitiu o JWT da
  // aplicação e o devolveu no fragmento da URL. Aqui apenas persistimos e
  // carregamos o usuário.
  const loginWithToken = async (accessToken: string) => {
    localStorage.setItem('token', accessToken);
    setToken(accessToken);
    const userData = await authService.getMe();
    setUser(userData);
  };

  const logout = () => {
    const currentToken = localStorage.getItem('token');
    if (currentToken) {
      authService.logout(currentToken).catch(() => {});
    }
    localStorage.removeItem('token');
    setToken(null);
    setUser(null);
    // PWA: limpa caches de runtime do Service Worker para evitar que dados
    // de marketing do usuário anterior fiquem disponíveis em modo offline
    // após o logout em dispositivos compartilhados.
    if (typeof caches !== 'undefined') {
      caches.keys()
        .then((keys) =>
          Promise.all(
            keys
              .filter((k) => k.startsWith('norte-marketing-cache') || k.startsWith('norte-image-cache'))
              .map((k) => caches.delete(k)),
          ),
        )
        .catch(() => {
          /* sem cache disponível, ignora */
        });
    }
  };

  const refreshUser = async () => {
    if (token) {
      try {
        const userData = await authService.getMe();
        setUser(userData);
      } catch (error) {
      }
    }
  };

  return (
    <AuthContext.Provider value={{ user, token, login, loginWithToken, logout, refreshUser, isLoading }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
