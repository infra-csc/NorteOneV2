import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { useAuth } from './AuthContext';
import api from '../services/api';

interface ModulePermission {
  pode_visualizar: boolean;
  pode_criar: boolean;
  pode_editar: boolean;
  pode_deletar: boolean;
}

interface PermissionsData {
  perfil_acesso_id: number | null;
  perfil_acesso_nome: string | null;
  perfil: string;
  permissoes: Record<string, ModulePermission>;
}

interface PermissionContextType {
  permissions: PermissionsData | null;
  isLoading: boolean;
  canView: (modulo: string) => boolean;
  canCreate: (modulo: string) => boolean;
  canEdit: (modulo: string) => boolean;
  canDelete: (modulo: string) => boolean;
  refreshPermissions: () => Promise<void>;
}

const PermissionContext = createContext<PermissionContextType | undefined>(undefined);

export const PermissionProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const { user } = useAuth();
  const [permissions, setPermissions] = useState<PermissionsData | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const fetchPermissions = async () => {
    if (!user) {
      setPermissions(null);
      setIsLoading(false);
      return;
    }
    try {
      const res = await api.get('/perfis-acesso/me/permissoes');
      setPermissions(res.data);
    } catch {
      setPermissions(null);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchPermissions();
  }, [user]);

  const canView = (modulo: string): boolean => {
    if (!permissions) return false;
    if (permissions.perfil === 'ADMIN') return true;
    return permissions.permissoes[modulo]?.pode_visualizar || false;
  };

  const canCreate = (modulo: string): boolean => {
    if (!permissions) return false;
    if (permissions.perfil === 'ADMIN') return true;
    return permissions.permissoes[modulo]?.pode_criar || false;
  };

  const canEdit = (modulo: string): boolean => {
    if (!permissions) return false;
    if (permissions.perfil === 'ADMIN') return true;
    return permissions.permissoes[modulo]?.pode_editar || false;
  };

  const canDelete = (modulo: string): boolean => {
    if (!permissions) return false;
    if (permissions.perfil === 'ADMIN') return true;
    return permissions.permissoes[modulo]?.pode_deletar || false;
  };

  return (
    <PermissionContext.Provider value={{
      permissions,
      isLoading,
      canView,
      canCreate,
      canEdit,
      canDelete,
      refreshPermissions: fetchPermissions,
    }}>
      {children}
    </PermissionContext.Provider>
  );
};

export const usePermissions = () => {
  const context = useContext(PermissionContext);
  if (context === undefined) {
    throw new Error('usePermissions must be used within a PermissionProvider');
  }
  return context;
};
