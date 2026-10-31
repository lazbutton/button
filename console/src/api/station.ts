/**
 * Les réglages de la station, gardés par le moteur : son nom, les adresses de son flux
 * et de son harbor, le lien de son code source. La console les pose sur sa marque,
 * brand.json : un réglage absent garde la valeur de brand.json. Pur : pas de React,
 * testable en node.
 */
import type { Brand } from "../lib/brand.ts";
import type { PublicStation, StationSettings } from "./types.ts";

/** Les champs de l'onglet Station, dans l'ordre du moteur. Le fuseau n'en est pas : il se lit. */
export const STATION_FIELDS = [
  "name",
  "short",
  "tagline",
  "locale",
  "public_stream_url",
  "now_url",
  "status_url",
  "harbor_host",
  "harbor_port",
  "harbor_mount",
  "source_url",
] as const;

export type StationField = (typeof STATION_FIELDS)[number];
export type StationForm = Record<StationField, string>;

const PUBLIC_FIELDS = [
  "name",
  "short",
  "tagline",
  "locale",
  "public_stream_url",
  "now_url",
  "status_url",
  "source_url",
] as const satisfies readonly (keyof PublicStation)[];

/** La console attend les réglages du moteur 3 s au plus, puis s'affiche avec brand.json. */
export const STATION_DEADLINE_MS = 3_000;

/**
 * `GET /public/station.json`, lu sans session. `retry` : le moteur n'a pas répondu,
 * injoignable, en erreur ou trop lent ; la console garde brand.json et relira plus tard.
 * Un moteur plus ancien (404) ou une réponse qui n'est pas un objet ne se relisent pas.
 */
export type StationRead = { station: PublicStation | null; retry: boolean };

export async function readPublicStation(
  prefix: string,
  fetcher: typeof fetch = fetch,
  deadlineMs = STATION_DEADLINE_MS,
): Promise<StationRead> {
  try {
    const response = await fetcher(`${prefix}/public/station.json`, {
      cache: "no-store",
      credentials: "omit",
      signal: AbortSignal.timeout(deadlineMs),
    });
    if (!response.ok) return { station: null, retry: response.status !== 404 };
    const payload: unknown = await response.json();
    const object = payload !== null && typeof payload === "object" && !Array.isArray(payload);
    return { station: object ? (payload as PublicStation) : null, retry: false };
  } catch (caught) {
    // Du HTML à la place du JSON : la route ne mène pas au moteur, relire n'y changera rien.
    return { station: null, retry: !(caught instanceof SyntaxError) };
  }
}

/** Un réglage posé : du texte non vide. Le reste, absent ou illisible, laisse brand.json. */
function setting(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() ? value.trim() : undefined;
}

/**
 * La marque de la console : les réglages du moteur d'abord, puis brand.json, clé par
 * clé. Sans réglages, face à un moteur qui n'a pas la route ou qui ne répond pas,
 * brand.json tel quel. Le harbor n'en fait pas partie : un auditeur ne le voit pas.
 */
export function withStation(brand: Brand, station: Partial<PublicStation> | null | undefined): Brand {
  if (!station) return brand;
  const name = setting(station.name);
  const short = setting(station.short);
  const tagline = setting(station.tagline);
  const sourceUrl = setting(station.source_url);
  const stream = setting(station.public_stream_url);
  const now = setting(station.now_url);
  const status = setting(station.status_url);
  return {
    ...brand,
    suite: {
      ...brand.suite,
      ...(name && { name }),
      ...(short && { short }),
      ...(tagline && { tagline }),
      ...(sourceUrl && { sourceUrl }),
    },
    apps: {
      ...brand.apps,
      player: {
        ...brand.apps.player,
        ...(stream && { streamUrl: stream, productionStreamUrl: stream }),
        ...(now && { productionNowUrl: now }),
        ...(status && { icecastStatusUrl: status }),
      },
    },
  };
}

/** Le direct d'origine, quand brand.json ne le donne pas. */
const HARBOR_HOST = "radio.lazbutton.xyz";
const HARBOR_PORT = "6800";
const HARBOR_MOUNT = "/stream";

/** L'hôte d'une adresse de brand.json, avec ou sans `http://`. */
function hostFromBase(base?: string): string {
  if (!base) return "";
  try {
    return new URL(base.includes("://") ? base : `http://${base}`).hostname;
  } catch {
    return "";
  }
}

export type HarborAddress = { host: string; port: string; mount: string };

/**
 * Ce que « Passer en direct » donne à l'encodeur : l'hôte de brand.json, sinon le
 * direct d'origine. Le panneau ne lit pas les réglages du harbor : `GET /station.json`
 * est réservé aux admins. L'onglet Station les montre en grisé.
 */
export function harborAddress(brand: Brand): HarborAddress {
  return {
    host: hostFromBase(brand.apps.harbor?.url) || HARBOR_HOST,
    port: HARBOR_PORT,
    mount: HARBOR_MOUNT,
  };
}

/** Ce qu'un auditeur voit des réglages : ce que la console pose sur sa marque après un enregistrement. */
export function publicStation(settings: StationSettings): PublicStation {
  return Object.fromEntries(PUBLIC_FIELDS.map((key) => [key, settings[key]])) as PublicStation;
}

/** Les champs du formulaire : un réglage absent est un champ vide. */
export function stationForm(settings: StationSettings): StationForm {
  return Object.fromEntries(
    STATION_FIELDS.map((key) => [key, settings[key] == null ? "" : String(settings[key])]),
  ) as StationForm;
}

/** Le corps du `PUT` : chaque champ. Vide, le réglage s'efface, et la console reprend brand.json. */
export function stationBody(form: StationForm): Record<StationField, string | null> {
  return Object.fromEntries(STATION_FIELDS.map((key) => [key, form[key].trim() || null])) as Record<
    StationField,
    string | null
  >;
}
