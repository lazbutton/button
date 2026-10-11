/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_BUTTON_HUB_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

declare global {
  interface Window {
    webkitAudioContext?: typeof AudioContext;
  }
}

export {};

