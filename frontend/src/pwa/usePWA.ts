import { useEffect, useRef, useState } from 'react';
import { registerSW } from 'virtual:pwa-register';

interface BeforeInstallPromptEvent extends Event {
  readonly platforms: ReadonlyArray<string>;
  readonly userChoice: Promise<{ outcome: 'accepted' | 'dismissed'; platform: string }>;
  prompt(): Promise<void>;
}

declare global {
  interface WindowEventMap {
    beforeinstallprompt: BeforeInstallPromptEvent;
  }
}

const INSTALL_DISMISSED_KEY = 'norte_pwa_install_dismissed_at';
const DISMISS_DAYS = 14;

function isStandalone(): boolean {
  if (typeof window === 'undefined') return false;
  const navAny = window.navigator as Navigator & { standalone?: boolean };
  return (
    window.matchMedia?.('(display-mode: standalone)').matches ||
    navAny.standalone === true ||
    document.referrer.startsWith('android-app://')
  );
}

function isIOS(): boolean {
  if (typeof window === 'undefined') return false;
  const nav = window.navigator;
  const ua = nav.userAgent;
  if (/iPad|iPhone|iPod/.test(ua) && !(window as unknown as { MSStream?: unknown }).MSStream) {
    return true;
  }
  // iPadOS 13+ reporta UA de Macintosh; detecta por touch points em plataforma Mac
  if (nav.platform === 'MacIntel' && typeof nav.maxTouchPoints === 'number' && nav.maxTouchPoints > 1) {
    return true;
  }
  return false;
}

function isMobileViewport(): boolean {
  if (typeof window === 'undefined') return false;
  return window.matchMedia('(max-width: 768px)').matches;
}

function wasRecentlyDismissed(): boolean {
  try {
    const raw = localStorage.getItem(INSTALL_DISMISSED_KEY);
    if (!raw) return false;
    const ts = Number(raw);
    if (!Number.isFinite(ts)) return false;
    const ageMs = Date.now() - ts;
    return ageMs < DISMISS_DAYS * 24 * 60 * 60 * 1000;
  } catch {
    return false;
  }
}

export interface PWAState {
  installPromptAvailable: boolean;
  showIOSInstallHint: boolean;
  triggerInstall: () => Promise<void>;
  dismissInstall: () => void;
}

export function usePWA(): PWAState {
  const [deferred, setDeferred] = useState<BeforeInstallPromptEvent | null>(null);
  const [showIOSInstallHint, setShowIOSInstallHint] = useState(false);
  const updateSWRef = useRef<((reload?: boolean) => Promise<void>) | null>(null);
  const reloadingRef = useRef(false);

  useEffect(() => {
    const triggerAutoReload = () => {
      if (reloadingRef.current) return;
      reloadingRef.current = true;
      const fn = updateSWRef.current;
      // Aplica a nova versão automaticamente. updateSW(true) ativa o novo SW e
      // faz o reload. Como fallback (caso o registro ainda não esteja pronto
      // por algum motivo), recarrega manualmente após um pequeno atraso.
      try {
        if (fn) {
          void fn(true);
        }
      } catch (err) {
        console.warn('[PWA] auto-update falhou, recarregando manualmente', err);
      }
      window.setTimeout(() => {
        if (reloadingRef.current) {
          window.location.reload();
        }
      }, 1500);
    };

    let periodicTimer: number | undefined;
    let swRegistration: ServiceWorkerRegistration | undefined;

    const checkForUpdate = () => {
      if (!swRegistration) return;
      if (typeof navigator !== 'undefined' && navigator.onLine === false) return;
      // Re-busca o service worker no servidor. Se houver versão nova,
      // dispara onNeedRefresh → triggerAutoReload (aplica e recarrega).
      swRegistration.update().catch(() => {
        // offline ou falha transitória: ignora, tenta de novo no próximo ciclo
      });
    };

    const onVisible = () => {
      if (document.visibilityState === 'visible') checkForUpdate();
    };

    const fn = registerSW({
      immediate: true,
      onNeedRefresh() {
        triggerAutoReload();
      },
      onOfflineReady() {
        // Cache primed: app pode abrir offline
      },
      onRegisterError(err) {
        console.warn('[PWA] Service worker registration failed', err);
      },
      onRegisteredSW(_swUrl, registration) {
        swRegistration = registration;
        // Apps instalados (celular/tablet) costumam ficar abertos por horas/dias
        // sem um reload completo. Sem isto, o service worker só checaria por
        // atualização no carregamento inicial, deixando o usuário preso a um
        // bundle antigo (tela "congelada" no cache). Checa a cada 60s e também
        // quando o app volta ao primeiro plano.
        periodicTimer = window.setInterval(checkForUpdate, 60 * 1000);
        document.addEventListener('visibilitychange', onVisible);
      },
    });
    updateSWRef.current = fn;

    return () => {
      if (periodicTimer !== undefined) window.clearInterval(periodicTimer);
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, []);

  useEffect(() => {
    const handler = (e: BeforeInstallPromptEvent) => {
      e.preventDefault();
      if (isStandalone() || wasRecentlyDismissed()) return;
      setDeferred(e);
    };
    window.addEventListener('beforeinstallprompt', handler);

    const installed = () => {
      setDeferred(null);
      setShowIOSInstallHint(false);
    };
    window.addEventListener('appinstalled', installed);

    if (isIOS() && !isStandalone() && !wasRecentlyDismissed() && isMobileViewport()) {
      const t = window.setTimeout(() => setShowIOSInstallHint(true), 4000);
      return () => {
        window.clearTimeout(t);
        window.removeEventListener('beforeinstallprompt', handler);
        window.removeEventListener('appinstalled', installed);
      };
    }

    return () => {
      window.removeEventListener('beforeinstallprompt', handler);
      window.removeEventListener('appinstalled', installed);
    };
  }, []);

  const triggerInstall = async () => {
    if (!deferred) return;
    await deferred.prompt();
    const choice = await deferred.userChoice;
    if (choice.outcome === 'dismissed') {
      try {
        localStorage.setItem(INSTALL_DISMISSED_KEY, String(Date.now()));
      } catch {
        // ignore
      }
    }
    setDeferred(null);
  };

  const dismissInstall = () => {
    try {
      localStorage.setItem(INSTALL_DISMISSED_KEY, String(Date.now()));
    } catch {
      // ignore
    }
    setDeferred(null);
    setShowIOSInstallHint(false);
  };

  return {
    installPromptAvailable: deferred !== null,
    showIOSInstallHint,
    triggerInstall,
    dismissInstall,
  };
}
