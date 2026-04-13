import React, { useState, useRef } from 'react';
import { useAuth } from '../../context/AuthContext';
import { useTheme } from '../../context/ThemeContext';
import { profileService } from '../../services/api';
import { Camera, Lock, Eye, EyeOff, Trash2, Check, AlertCircle, User } from 'lucide-react';

const Profile: React.FC = () => {
  const { user, refreshUser } = useAuth();
  const { isDark } = useTheme();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showCurrentPassword, setShowCurrentPassword] = useState(false);
  const [showNewPassword, setShowNewPassword] = useState(false);
  const [passwordLoading, setPasswordLoading] = useState(false);
  const [passwordMsg, setPasswordMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [photoLoading, setPhotoLoading] = useState(false);
  const [photoMsg, setPhotoMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  const handlePasswordChange = async (e: React.FormEvent) => {
    e.preventDefault();
    setPasswordMsg(null);

    if (newPassword.length < 6) {
      setPasswordMsg({ type: 'error', text: 'A nova senha deve ter pelo menos 6 caracteres.' });
      return;
    }
    if (newPassword !== confirmPassword) {
      setPasswordMsg({ type: 'error', text: 'As senhas não coincidem.' });
      return;
    }

    setPasswordLoading(true);
    try {
      await profileService.changePassword(currentPassword, newPassword);
      setPasswordMsg({ type: 'success', text: 'Senha alterada com sucesso!' });
      setCurrentPassword('');
      setNewPassword('');
      setConfirmPassword('');
    } catch (err: any) {
      const detail = err.response?.data?.detail || 'Erro ao alterar senha.';
      setPasswordMsg({ type: 'error', text: detail });
    } finally {
      setPasswordLoading(false);
    }
  };

  const handlePhotoUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setPhotoMsg(null);
    setPhotoLoading(true);
    try {
      await profileService.uploadPhoto(file);
      await refreshUser();
      setPhotoMsg({ type: 'success', text: 'Foto atualizada com sucesso!' });
    } catch (err: any) {
      const detail = err.response?.data?.detail || 'Erro ao enviar foto.';
      setPhotoMsg({ type: 'error', text: detail });
    } finally {
      setPhotoLoading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const handlePhotoDelete = async () => {
    setPhotoMsg(null);
    setPhotoLoading(true);
    try {
      await profileService.deletePhoto();
      await refreshUser();
      setPhotoMsg({ type: 'success', text: 'Foto removida.' });
    } catch (err: any) {
      setPhotoMsg({ type: 'error', text: 'Erro ao remover foto.' });
    } finally {
      setPhotoLoading(false);
    }
  };

  const initials = user?.nome
    ? user.nome.split(' ').map(n => n[0]).slice(0, 2).join('').toUpperCase()
    : '?';

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <h1 className={`text-2xl font-bold ${isDark ? 'text-white' : 'text-gray-800'}`}>Meu Perfil</h1>

      <div className={`rounded-xl shadow-sm border p-6 ${isDark ? 'bg-gray-800 border-gray-700' : 'bg-white border-gray-200'}`}>
        <h2 className={`text-lg font-semibold mb-4 ${isDark ? 'text-white' : 'text-gray-800'}`}>Foto de Perfil</h2>

        <div className="flex items-center gap-6">
          <div className="relative group">
            {user?.foto_perfil ? (
              <img
                src={user.foto_perfil}
                alt="Foto de perfil"
                className="w-24 h-24 rounded-full object-cover border-4 border-indigo-200 dark:border-indigo-700"
              />
            ) : (
              <div className="w-24 h-24 rounded-full bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center text-white text-2xl font-bold border-4 border-indigo-200 dark:border-indigo-700">
                {initials}
              </div>
            )}
            <button
              onClick={() => fileInputRef.current?.click()}
              disabled={photoLoading}
              className="absolute inset-0 rounded-full bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center cursor-pointer"
            >
              <Camera className="w-6 h-6 text-white" />
            </button>
          </div>

          <div className="flex-1 space-y-2">
            <div className="flex gap-2">
              <button
                onClick={() => fileInputRef.current?.click()}
                disabled={photoLoading}
                className="px-4 py-2 text-sm font-medium rounded-lg bg-gradient-to-r from-indigo-600 to-purple-600 text-white hover:from-indigo-700 hover:to-purple-700 disabled:opacity-50 transition-all"
              >
                {photoLoading ? 'Enviando...' : 'Alterar foto'}
              </button>
              {user?.foto_perfil && (
                <button
                  onClick={handlePhotoDelete}
                  disabled={photoLoading}
                  className={`px-4 py-2 text-sm font-medium rounded-lg border transition-colors disabled:opacity-50 ${
                    isDark ? 'border-gray-600 text-gray-300 hover:bg-gray-700' : 'border-gray-300 text-gray-600 hover:bg-gray-50'
                  }`}
                >
                  <Trash2 className="w-4 h-4 inline mr-1" />
                  Remover
                </button>
              )}
            </div>
            <p className={`text-xs ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
              JPG, PNG ou WebP. Máximo 5MB.
            </p>
            <input
              ref={fileInputRef}
              type="file"
              accept="image/jpeg,image/png,image/webp"
              onChange={handlePhotoUpload}
              className="hidden"
            />
          </div>
        </div>

        {photoMsg && (
          <div className={`mt-4 flex items-center gap-2 text-sm px-3 py-2 rounded-lg ${
            photoMsg.type === 'success'
              ? isDark ? 'bg-emerald-900/30 text-emerald-400' : 'bg-emerald-50 text-emerald-700'
              : isDark ? 'bg-red-900/30 text-red-400' : 'bg-red-50 text-red-700'
          }`}>
            {photoMsg.type === 'success' ? <Check className="w-4 h-4" /> : <AlertCircle className="w-4 h-4" />}
            {photoMsg.text}
          </div>
        )}
      </div>

      <div className={`rounded-xl shadow-sm border p-6 ${isDark ? 'bg-gray-800 border-gray-700' : 'bg-white border-gray-200'}`}>
        <h2 className={`text-lg font-semibold mb-1 ${isDark ? 'text-white' : 'text-gray-800'}`}>Informações</h2>
        <div className="space-y-3 mt-4">
          <div>
            <label className={`text-xs font-medium ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Nome</label>
            <p className={`text-sm ${isDark ? 'text-white' : 'text-gray-800'}`}>{user?.nome}</p>
          </div>
          <div>
            <label className={`text-xs font-medium ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Email</label>
            <p className={`text-sm ${isDark ? 'text-white' : 'text-gray-800'}`}>{user?.email}</p>
          </div>
          <div>
            <label className={`text-xs font-medium ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Perfil de Acesso</label>
            <p className="text-sm">
              <span className="px-2 py-0.5 rounded bg-blue-100 text-blue-800 text-xs font-medium">
                {user?.perfil_acesso_nome || 'Sem perfil'}
              </span>
            </p>
          </div>
        </div>
      </div>

      <div className={`rounded-xl shadow-sm border p-6 ${isDark ? 'bg-gray-800 border-gray-700' : 'bg-white border-gray-200'}`}>
        <h2 className={`text-lg font-semibold mb-4 ${isDark ? 'text-white' : 'text-gray-800'}`}>Alterar Senha</h2>

        <form onSubmit={handlePasswordChange} className="space-y-4">
          <div>
            <label className={`block text-sm font-medium mb-1 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
              Senha atual
            </label>
            <div className="relative">
              <Lock className={`absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 ${isDark ? 'text-gray-500' : 'text-gray-400'}`} />
              <input
                type={showCurrentPassword ? 'text' : 'password'}
                value={currentPassword}
                onChange={(e) => setCurrentPassword(e.target.value)}
                required
                className={`w-full pl-10 pr-10 py-2.5 rounded-lg border text-sm transition-colors ${
                  isDark
                    ? 'bg-gray-700 border-gray-600 text-white focus:border-indigo-500'
                    : 'bg-white border-gray-300 text-gray-900 focus:border-indigo-500'
                } focus:outline-none focus:ring-1 focus:ring-indigo-500`}
              />
              <button
                type="button"
                onClick={() => setShowCurrentPassword(!showCurrentPassword)}
                className="absolute right-3 top-1/2 -translate-y-1/2"
              >
                {showCurrentPassword
                  ? <EyeOff className={`w-4 h-4 ${isDark ? 'text-gray-500' : 'text-gray-400'}`} />
                  : <Eye className={`w-4 h-4 ${isDark ? 'text-gray-500' : 'text-gray-400'}`} />}
              </button>
            </div>
          </div>

          <div>
            <label className={`block text-sm font-medium mb-1 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
              Nova senha
            </label>
            <div className="relative">
              <Lock className={`absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 ${isDark ? 'text-gray-500' : 'text-gray-400'}`} />
              <input
                type={showNewPassword ? 'text' : 'password'}
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                required
                minLength={6}
                className={`w-full pl-10 pr-10 py-2.5 rounded-lg border text-sm transition-colors ${
                  isDark
                    ? 'bg-gray-700 border-gray-600 text-white focus:border-indigo-500'
                    : 'bg-white border-gray-300 text-gray-900 focus:border-indigo-500'
                } focus:outline-none focus:ring-1 focus:ring-indigo-500`}
              />
              <button
                type="button"
                onClick={() => setShowNewPassword(!showNewPassword)}
                className="absolute right-3 top-1/2 -translate-y-1/2"
              >
                {showNewPassword
                  ? <EyeOff className={`w-4 h-4 ${isDark ? 'text-gray-500' : 'text-gray-400'}`} />
                  : <Eye className={`w-4 h-4 ${isDark ? 'text-gray-500' : 'text-gray-400'}`} />}
              </button>
            </div>
          </div>

          <div>
            <label className={`block text-sm font-medium mb-1 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
              Confirmar nova senha
            </label>
            <div className="relative">
              <Lock className={`absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 ${isDark ? 'text-gray-500' : 'text-gray-400'}`} />
              <input
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                required
                minLength={6}
                className={`w-full pl-10 pr-10 py-2.5 rounded-lg border text-sm transition-colors ${
                  isDark
                    ? 'bg-gray-700 border-gray-600 text-white focus:border-indigo-500'
                    : 'bg-white border-gray-300 text-gray-900 focus:border-indigo-500'
                } focus:outline-none focus:ring-1 focus:ring-indigo-500`}
              />
            </div>
          </div>

          {passwordMsg && (
            <div className={`flex items-center gap-2 text-sm px-3 py-2 rounded-lg ${
              passwordMsg.type === 'success'
                ? isDark ? 'bg-emerald-900/30 text-emerald-400' : 'bg-emerald-50 text-emerald-700'
                : isDark ? 'bg-red-900/30 text-red-400' : 'bg-red-50 text-red-700'
            }`}>
              {passwordMsg.type === 'success' ? <Check className="w-4 h-4" /> : <AlertCircle className="w-4 h-4" />}
              {passwordMsg.text}
            </div>
          )}

          <button
            type="submit"
            disabled={passwordLoading}
            className="w-full py-2.5 rounded-lg bg-gradient-to-r from-indigo-600 to-purple-600 text-white font-medium text-sm hover:from-indigo-700 hover:to-purple-700 disabled:opacity-50 transition-all"
          >
            {passwordLoading ? 'Alterando...' : 'Alterar Senha'}
          </button>
        </form>
      </div>
    </div>
  );
};

export default Profile;
