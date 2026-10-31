import { API_PREFIX } from "../api/client";
import { readPublicStation, type StationRead } from "../api/station";

export type BrandApp = {
  url?: string;
  health?: string;
  stream?: string;
  status?: string;
  streamUrl?: string;
  productionStreamUrl?: string;
  /** Le now.json public, celui de l'auditeur : le réglage `now_url` du moteur. */
  productionNowUrl?: string;
  nowUrl?: string;
  icecastStatusUrl?: string;
  festivalUrl?: string;
};

export type BrandTheme = {
  appearance: "light" | "dark";
  bg: string;
  surface1: string;
  surface2: string;
  surface3: string;
  border: string;
  text: string;
  muted: string;
  faint: string;
  accent: string;
  accentHover: string;
  ink: string;
  live: string;
  ok: string;
  vuOk: string;
  vuWarn: string;
  vuHot: string;
  vuClip: string;
};

export type Brand = {
  /** `sourceUrl` : dépôt du code (AGPL, lien « Code source » de la console). */
  suite: { id: string; name: string; short: string; tagline?: string; sourceUrl?: string };
  labels: Record<string, Record<string, string>>;
  infra: {
    smbShare: string;
    mediaDataset?: string;
    mediaMount?: string;
    group?: string;
    partnerCode: string;
    smbHost?: string;
    smbUser?: string;
  };
  apps: Record<string, BrandApp>;
  tailscaleBase?: string;
  theme?: BrandTheme;
};

export const DEFAULT_SOURCE_URL = "https://github.com/lazbutton/button";

export type Appearance = "light" | "dark";
export type AppearanceChoice = "system" | Appearance;

export const APPEARANCE_KEY = "app-appearance";

export function systemAppearance(): Appearance {
  try {
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  } catch {
    return "light";
  }
}

export function readAppearanceChoice(): AppearanceChoice {
  try {
    const stored = window.localStorage.getItem(APPEARANCE_KEY);
    if (stored === "system" || stored === "light" || stored === "dark") return stored;
  } catch {
    /* navigation privée */
  }
  return "system";
}

export function resolveAppearance(choice: AppearanceChoice): Appearance {
  return choice === "system" ? systemAppearance() : choice;
}

export function readAppearance(): Appearance {
  return resolveAppearance(readAppearanceChoice());
}

export function writeAppearance(value: AppearanceChoice): void {
  try {
    window.localStorage.setItem(APPEARANCE_KEY, value);
  } catch {
    /* navigation privée */
  }
}

export const LIGHT_THEME: BrandTheme = {
  appearance: "light",
  bg: "#f5f5f7",
  surface1: "#ffffff",
  surface2: "#f0f0f0",
  surface3: "#e8e8e8",
  border: "rgb(10 10 10 / 0.10)",
  text: "#0a0a0a",
  muted: "#525252",
  faint: "#666666",
  accent: "#0a0a0a",
  accentHover: "#000000",
  ink: "#0a0a0a",
  live: "#ff4d4d",
  ok: "#3ecf8e",
  vuOk: "#3ecf8e",
  vuWarn: "#f0e24a",
  vuHot: "#ff7a45",
  vuClip: "#ff4d4d",
};

export const DARK_THEME: BrandTheme = {
  appearance: "dark",
  bg: "#0a0a0a",
  surface1: "#121212",
  surface2: "#1a1a1a",
  surface3: "#242424",
  border: "rgb(255 255 255 / 0.10)",
  text: "#f5f5f5",
  muted: "#a3a3a3",
  faint: "#8f8f8f",
  accent: "#f5f5f5",
  accentHover: "#ffffff",
  ink: "#f5f5f5",
  live: "#ff4d4d",
  ok: "#3ecf8e",
  vuOk: "#3ecf8e",
  vuWarn: "#f0e24a",
  vuHot: "#ff7a45",
  vuClip: "#ff4d4d",
};

/** Palette du mode choisi. Les couleurs de brand.json ne s'appliquent que dans leur mode. */
export function paletteFor(appearance: Appearance, brandTheme?: BrandTheme): BrandTheme {
  const base = appearance === "dark" ? DARK_THEME : LIGHT_THEME;
  if (brandTheme?.appearance === appearance) return { ...base, ...brandTheme, appearance };
  return base;
}

const THEME_VARS: Record<keyof Omit<BrandTheme, "appearance">, string> = {
  bg: "--app-bg",
  surface1: "--app-surface-1",
  surface2: "--app-surface-2",
  surface3: "--app-surface-3",
  border: "--app-border",
  text: "--app-text",
  muted: "--app-text-muted",
  faint: "--app-text-faint",
  accent: "--app-accent",
  accentHover: "--app-accent-hover",
  ink: "--app-ink",
  live: "--app-live",
  ok: "--app-ok",
  vuOk: "--app-vu-ok",
  vuWarn: "--app-vu-warn",
  vuHot: "--app-vu-hot",
  vuClip: "--app-vu-clip",
};

export function applyTheme(theme: BrandTheme | undefined) {
  const t = { ...LIGHT_THEME, ...theme };
  const root = document.documentElement;
  root.dataset.appearance = t.appearance;
  root.style.colorScheme = t.appearance;
  for (const [key, cssVar] of Object.entries(THEME_VARS) as [keyof typeof THEME_VARS, string][]) {
    root.style.setProperty(cssVar, t[key]);
  }
  root.style.setProperty("--app-danger", t.live);
}

function hubUrl(): string {
  const env = import.meta.env?.VITE_BUTTON_HUB_URL;
  if (typeof env === "string" && env.trim()) return env.replace(/\/$/, "");
  return "";
}

export function interpolate(template: string, brand: Brand): string {
  return (template || "")
    .replaceAll("{name}", brand.suite.name)
    .replaceAll("{short}", brand.suite.short)
    .replaceAll("{share}", brand.infra.smbShare);
}

export function label(brand: Brand, group: string, key: string): string {
  return interpolate(brand.labels?.[group]?.[key] || "", brand);
}

async function fetchJson(url: string): Promise<Brand | null> {
  try {
    const response = await fetch(url, { cache: "no-store" });
    if (!response.ok) return null;
    return (await response.json()) as Brand;
  } catch {
    return null;
  }
}

async function loadBrandFile(): Promise<Brand> {
  const hub = hubUrl();
  if (hub) {
    const remote = await fetchJson(`${hub}/brand.json`);
    if (remote?.suite?.name) return remote;
  }
  const local = await fetchJson("./brand.json");
  if (local?.suite?.name) return local;
  throw new Error("brand.json introuvable");
}

/**
 * Les réglages de la station, lus sans session : la console en a besoin avant la
 * connexion (`readPublicStation`, api/station.ts).
 */
export function loadStation(): Promise<StationRead> {
  return readPublicStation(API_PREFIX);
}

export type LoadedBrand = { file: Brand } & StationRead;

/**
 * brand.json et les réglages du moteur, lus ensemble. La marque de la console prend les
 * réglages du moteur d'abord, puis brand.json en repli : `withStation` (api/station.ts).
 */
export async function loadBrand(): Promise<LoadedBrand> {
  const [file, read] = await Promise.all([loadBrandFile(), loadStation()]);
  return { file, ...read };
}
