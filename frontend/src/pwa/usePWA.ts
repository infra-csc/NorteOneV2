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

// Guarda de versão (anti-loop): guarda "<versaoAlvo>|<tentativas>" para nunca
// recarregar mais que MAX_UPGRADE_ATTEMPTS vezes atrás da mesma versão do servidor.
const VERSION_GUARD_KEY = 'norte_version_guard';
const MAX_UPGRADE_ATTEMPTS = 2;
const VERSION_CHECK_INTERVAL_MS = 90 * 1000;

function readGuardAttempts(targetVersion: string): number {
  try {
    const raw = localStorage.getItem(VERSION_GUARD_KEY);
    if (!raw) return 0;
    const sep = raw.lastIndexOf('|');
    if (sep < 0) return 0;
    if (raw.slice(0, sep) !== targetVersion) return 0;
    const n = Number(raw.slice(sep + 1));
    return Number.isFinite(n) && n > 0 ? n : 0;
  } catch {
    return 0;
  }
}

function writeGuardAttempts(targetVersion: string, attempts: number): void {
  try {
    localStorage.setItem(VERSION_GUARD_KEY, `${targetVersion}|${attempts}`);
  } catch {
    // ignore
  }
}

function clearGuard(): void {
  try {
    localStorage.removeItem(VERSION_GUARD_KEY);
  } catch {
    // ignore
  }
}

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
    let versionTimer: number | undefined;
    let versionKickoffTimer: number | undefined;
    let versionCheckInFlight = false;
    let disposed = false;
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

    // ---------------------------------------------------------------------
    // Guarda de versão: rede de segurança independente do service worker.
    //
    // Toda a cadeia normal de auto-atualização (registerType 'autoUpdate' +
    // registration.update()) depende de o navegador baixar um sw.js novo.
    // Se o sw.js antigo ficou preso em alguma camada de cache HTTP, essa
    // cadeia NUNCA dispara e o usuário fica eternamente no bundle antigo.
    //
    // Aqui o app pergunta direto ao servidor (/api/version, sempre no-store)
    // qual é a versão publicada e compara com a versão embutida neste bundle
    // (__APP_BUILD_VERSION__, injetada em build-time). Divergiu → força a
    // atualização: tenta o caminho normal do SW e, se não resolver, desregistra
    // o service worker, limpa o precache e recarrega — com anti-loop de no
    // máximo MAX_UPGRADE_ATTEMPTS recargas por versão-alvo.
    // ---------------------------------------------------------------------
    const forceUpgrade = async (serverVersion: string) => {
      const attempts = readGuardAttempts(serverVersion);
      if (attempts >= MAX_UPGRADE_ATTEMPTS) return; // anti-loop: desiste até a versão mudar
      writeGuardAttempts(serverVersion, attempts + 1);

      // 1) Caminho normal: pede ao navegador para re-buscar o sw.js. Se o
      //    novo SW for detectado, onNeedRefresh → triggerAutoReload cuida de tudo.
      try {
        await swRegistration?.update();
      } catch {
        // segue para o caminho forçado
      }
      // Dá alguns segundos para a cadeia normal aplicar e recarregar sozinha.
      await new Promise((r) => window.setTimeout(r, 5000));
      if (disposed || reloadingRef.current) return;

      // 2) Caminho forçado: o sw.js novo não chegou (preso em cache HTTP).
      //    Desregistra o SW atual e apaga o precache do Workbox para que o
      //    próximo carregamento busque index.html + bundles direto do servidor
      //    e registre o service worker novo do zero. Os caches de dados de
      //    runtime (marketing/imagens/fontes) são preservados.
      try {
        const regs = (await navigator.serviceWorker?.getRegistrations?.()) ?? [];
        await Promise.all(regs.map((r) => r.unregister().catch(() => false)));
      } catch {
        // ignore
      }
      try {
        if (typeof caches !== 'undefined') {
          const keys = await caches.keys();
          await Promise.all(
            keys
              .filter((k) => k.includes('precache') || k.startsWith('workbox'))
              .map((k) => caches.delete(k)),
          );
        }
      } catch {
        // ignore
      }
      if (disposed) return;
      reloadingRef.current = true;
      window.location.reload();
    };

    const checkVersion = async () => {
      if (versionCheckInFlight || reloadingRef.current) return;
      if (typeof navigator !== 'undefined' && navigator.onLine === false) return;
      versionCheckInFlight = true;
      try {
        const res = await fetch('/api/version', { cache: 'no-store' });
        if (!res.ok) return;
        const data: unknown = await res.json();
        const serverVersion =
          data && typeof data === 'object' && typeof (data as { version?: unknown }).version === 'string'
            ? ((data as { version: string }).version)
            : null;
        // Sem versão publicada (ex.: dev, dist sem version.json): nada a fazer.
        if (!serverVersion) return;
        if (serverVersion === __APP_BUILD_VERSION__) {
          clearGuard(); // em dia — zera o anti-loop para futuras versões
          return;
        }
        await forceUpgrade(serverVersion);
      } catch {
        // offline/falha transitória: tenta de novo no próximo ciclo
      } finally {
        versionCheckInFlight = false;
      }
    };

    const onVisible = () => {
      if (document.visibilityState === 'visible') {
        checkForUpdate();
        if (!import.meta.env.DEV) void checkVersion();
      }
    };

    // O guarda de versão roda mesmo se o registro do SW falhar (não depende
    // do onRegisteredSW). Primeira checagem logo após o load para destravar
    // rapidamente usuários presos em bundles antigos.
    if (!import.meta.env.DEV) {
      versionKickoffTimer = window.setTimeout(() => void checkVersion(), 8 * 1000);
      versionTimer = window.setInterval(() => void checkVersion(), VERSION_CHECK_INTERVAL_MS);
    }

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
      disposed = true;
      if (periodicTimer !== undefined) window.clearInterval(periodicTimer);
      if (versionTimer !== undefined) window.clearInterval(versionTimer);
      if (versionKickoffTimer !== undefined) window.clearTimeout(versionKickoffTimer);
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
