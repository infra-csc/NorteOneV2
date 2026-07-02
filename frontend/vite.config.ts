import { defineConfig, type Plugin } from 'vite'
import react from '@vitejs/plugin-react-swc'
import path from 'path'
import { VitePWA } from 'vite-plugin-pwa'

// Identificador único por build. É embutido no bundle (__APP_BUILD_VERSION__) e
// gravado em dist/version.json — o backend expõe esse arquivo via /api/version.
// O frontend compara os dois periodicamente: se divergirem, força a atualização
// (guarda de versão que funciona mesmo quando o sw.js antigo está preso em cache).
const BUILD_VERSION = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`

function emitVersionJson(): Plugin {
  return {
    name: 'emit-version-json',
    apply: 'build',
    generateBundle() {
      this.emitFile({
        type: 'asset',
        fileName: 'version.json',
        source: JSON.stringify({ version: BUILD_VERSION }),
      })
    },
  }
}

export default defineConfig({
  define: {
    __APP_BUILD_VERSION__: JSON.stringify(BUILD_VERSION),
  },
  plugins: [
    react(),
    emitVersionJson(),
    VitePWA({
      registerType: 'autoUpdate',
      injectRegister: false,
      includeAssets: [
        'favicon-16x16.png',
        'favicon-32x32.png',
        'apple-touch-icon.png',
        'apple-touch-icon-152.png',
        'apple-touch-icon-167.png',
        'logo-norte-icon.png',
        'logo-norte.png',
      ],
      manifest: {
        name: 'Norte One',
        short_name: 'Norte One',
        description: 'Plataforma de gestão e monitoramento de eventos esportivos da Norte.',
        lang: 'pt-BR',
        theme_color: '#111827',
        background_color: '#111827',
        display: 'standalone',
        orientation: 'portrait',
        start_url: '/',
        scope: '/',
        icons: [
          { src: '/pwa-192x192.png', sizes: '192x192', type: 'image/png', purpose: 'any' },
          { src: '/pwa-512x512.png', sizes: '512x512', type: 'image/png', purpose: 'any' },
          { src: '/pwa-maskable-192x192.png', sizes: '192x192', type: 'image/png', purpose: 'maskable' },
          { src: '/pwa-maskable-512x512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
        ],
      },
      workbox: {
        globPatterns: ['**/*.{js,css,html,ico,png,svg,woff,woff2}'],
        navigateFallback: '/index.html',
        navigateFallbackDenylist: [/^\/api\//],
        cleanupOutdatedCaches: true,
        maximumFileSizeToCacheInBytes: 5 * 1024 * 1024,
        runtimeCaching: [
          {
            // Allowlist explícito: somente leituras GET usadas pelo ISC Dashboard e pelas telas
            // de leitura derivadas (Detalhe de Evento, Comparativo, Pricing, Playbook). Endpoints
            // de escrita, autenticação, perfil, admin, settings, ações comerciais, insights (IA),
            // simulação e qualquer cache/refresh manual NUNCA são cacheados — evita vazar dados
            // entre sessões em dispositivos compartilhados e mantém ações operacionais sempre online.
            urlPattern: ({ url, request }) => {
              if (request.method !== 'GET') return false;
              if (request.headers.has('authorization')) return false;
              const p = url.pathname;
              if (!p.startsWith('/api/marketing/')) return false;
              if (
                p === '/api/marketing/eventos' ||
                p === '/api/marketing/playbook' ||
                p === '/api/marketing/pricing' ||
                p === '/api/marketing/cache/status' ||
                p === '/api/marketing/curva-comparativa'
              ) {
                return true;
              }
              if (/^\/api\/marketing\/eventos\/[^/]+$/.test(p)) return true;
              if (/^\/api\/marketing\/eventos\/[^/]+\/medias-vendas$/.test(p)) return true;
              if (/^\/api\/marketing\/eventos\/[^/]+\/curva-snapshot$/.test(p)) return true;
              if (/^\/api\/marketing\/curva-comparativa\/[^/]+$/.test(p)) return true;
              return false;
            },
            handler: 'NetworkFirst',
            options: {
              cacheName: 'norte-marketing-cache',
              networkTimeoutSeconds: 8,
              expiration: {
                maxEntries: 60,
                maxAgeSeconds: 60 * 60 * 12,
              },
              cacheableResponse: { statuses: [200] },
            },
          },
          {
            urlPattern: ({ request }) => request.destination === 'image',
            handler: 'StaleWhileRevalidate',
            options: {
              cacheName: 'norte-image-cache',
              expiration: { maxEntries: 80, maxAgeSeconds: 60 * 60 * 24 * 30 },
            },
          },
          {
            urlPattern: ({ request }) => request.destination === 'font',
            handler: 'CacheFirst',
            options: {
              cacheName: 'norte-font-cache',
              expiration: { maxEntries: 20, maxAgeSeconds: 60 * 60 * 24 * 365 },
            },
          },
        ],
      },
      devOptions: {
        enabled: false,
      },
    }),
  ],
  resolve: {
    dedupe: ['three'],
    alias: {
      '@assets': path.resolve(__dirname, '../attached_assets')
    }
  },
  optimizeDeps: {
    exclude: ['three-stdlib'],
    esbuildOptions: {
      sourcemap: false,
    }
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          vendor: ['react', 'react-dom', 'react-router-dom'],
          charts: ['recharts'],
          icons: ['lucide-react'],
          three: ['three', '@react-three/fiber', '@react-three/drei'],
        }
      }
    },
    chunkSizeWarningLimit: 1000,
  },
  server: {
    host: '0.0.0.0',
    port: 5000,
    allowedHosts: true,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      }
    }
  }
})
