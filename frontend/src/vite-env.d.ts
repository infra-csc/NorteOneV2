/// <reference types="vite/client" />
/// <reference types="vite-plugin-pwa/client" />

// Injetado em build-time pelo `define` do vite.config.ts (guarda de versão do PWA)
declare const __APP_BUILD_VERSION__: string;
