import assert from "node:assert/strict";
import test from "node:test";
import type { Brand } from "../lib/brand.ts";
import { monitorSources } from "../lib/monitorSource.ts";
import {
  harborAddress,
  publicStation,
  readPublicStation,
  stationBody,
  stationForm,
  withStation,
} from "./station.ts";
import type { PublicStation, StationSettings } from "./types.ts";

// brand.json, celui de l'image de la console.
const FILE: Brand = {
  suite: { id: "exemple", name: "Radio Fichier", short: "RF", tagline: "Depuis brand.json" },
  labels: { player: { listen: "Écouter {name}" } },
  infra: { smbShare: "Exemple-Media", partnerCode: "RF" },
  apps: {
    player: {
      streamUrl: "https://fichier.radio.example/live.mp3",
      productionStreamUrl: "https://fichier.radio.example/live.mp3",
      icecastStatusUrl: "https://fichier.radio.example/status-json.xsl",
    },
    harbor: { url: "https://fichier.radio.example:6800" },
  },
};

const UNSET: PublicStation = {
  name: null,
  short: null,
  tagline: null,
  locale: null,
  public_stream_url: null,
  now_url: null,
  status_url: null,
  source_url: null,
};

const SETTINGS: StationSettings = {
  name: "Radio Moteur",
  short: "RM",
  tagline: "Depuis le moteur",
  locale: "fr-FR",
  public_stream_url: "https://moteur.radio.example/antenne.mp3",
  now_url: "https://moteur.radio.example/now.json",
  status_url: "https://moteur.radio.example/status-json.xsl",
  harbor_host: "direct.radio.example",
  harbor_port: 8005,
  harbor_mount: "/direct",
  source_url: "https://code.radio.example/button",
  timezone: "Europe/Paris",
};

/** Un moteur qui répond `status` et `body` ; `calls` garde ce que la console lui a demandé. */
function engine(status: number, body: string, calls: [string, RequestInit | undefined][] = []): typeof fetch {
  return (async (url: string, init?: RequestInit) => {
    calls.push([url, init]);
    return new Response(body, { status, headers: { "Content-Type": "application/json" } });
  }) as typeof fetch;
}

const NOT_FOUND = JSON.stringify({ error: "The requested URL was not found on the server." });

test("la console lit les réglages sans session, et ne relit que si le moteur n'a pas répondu", async () => {
  const calls: [string, RequestInit | undefined][] = [];
  const read = await readPublicStation("/api", engine(200, JSON.stringify({ ...UNSET, name: "Radio Moteur" }), calls));
  assert.deepEqual(read, { station: { ...UNSET, name: "Radio Moteur" }, retry: false });
  assert.equal(calls[0][0], "/api/public/station.json");
  assert.equal(calls[0][1]?.credentials, "omit");
  assert.equal(calls[0][1]?.cache, "no-store");

  // Un moteur plus ancien n'a pas la route : relire n'y changera rien.
  assert.deepEqual(await readPublicStation("", engine(404, NOT_FOUND)), { station: null, retry: false });
  // Moteur arrêté ou recréé (nginx répond 502), ou trop de demandes (503) : on relira.
  assert.deepEqual(await readPublicStation("", engine(502, "<html>Bad Gateway</html>")), { station: null, retry: true });
  assert.deepEqual(await readPublicStation("", engine(503, "")), { station: null, retry: true });
  const unreachable = (async () => {
    throw new TypeError("Failed to fetch");
  }) as typeof fetch;
  assert.deepEqual(await readPublicStation("", unreachable), { station: null, retry: true });
  // Une page HTML, ou autre chose qu'un objet : la route ne mène pas au moteur.
  assert.deepEqual(await readPublicStation("", engine(200, "<!doctype html><html></html>")), { station: null, retry: false });
  assert.deepEqual(await readPublicStation("", engine(200, "[]")), { station: null, retry: false });
  assert.deepEqual(await readPublicStation("", engine(200, "null")), { station: null, retry: false });
});

test("un moteur trop lent laisse brand.json, et on relira", async () => {
  const silent = ((_url: string, init?: RequestInit) =>
    new Promise((_resolve, reject) => {
      init?.signal?.addEventListener("abort", () => reject(init.signal?.reason));
    })) as typeof fetch;
  // En node, le minuteur d'AbortSignal.timeout ne retient pas le processus : celui-ci, si.
  const alive = setTimeout(() => {}, 1_000);
  try {
    assert.deepEqual(await readPublicStation("", silent, 20), { station: null, retry: true });
  } finally {
    clearTimeout(alive);
  }
});

test("face à un moteur sans réglages, la console garde brand.json", () => {
  assert.equal(withStation(FILE, null), FILE);
  assert.equal(withStation(FILE, undefined), FILE);
  // Un moteur qui a la route, mais rien de réglé.
  assert.deepEqual(withStation(FILE, UNSET).suite, FILE.suite);
  assert.deepEqual(withStation(FILE, UNSET).apps.player, FILE.apps.player);
});

test("les réglages du moteur passent d'abord, brand.json reste pour une clé absente", () => {
  const brand = withStation(FILE, { ...UNSET, name: "Radio Moteur", public_stream_url: SETTINGS.public_stream_url });
  assert.equal(brand.suite.name, "Radio Moteur");
  assert.equal(brand.suite.short, "RF");
  assert.equal(brand.suite.tagline, "Depuis brand.json");
  assert.equal(brand.apps.player?.productionStreamUrl, SETTINGS.public_stream_url);
  assert.equal(brand.apps.player?.streamUrl, SETTINGS.public_stream_url);
  assert.equal(brand.apps.player?.icecastStatusUrl, "https://fichier.radio.example/status-json.xsl");
  assert.equal(brand.apps.player?.productionNowUrl, undefined);
  // Le reste de brand.json ne bouge pas.
  assert.equal(brand.labels, FILE.labels);
  assert.equal(brand.infra, FILE.infra);
});

test("tous les réglages posés", () => {
  const brand = withStation(FILE, SETTINGS);
  assert.deepEqual(brand.suite, {
    id: "exemple",
    name: "Radio Moteur",
    short: "RM",
    tagline: "Depuis le moteur",
    sourceUrl: "https://code.radio.example/button",
  });
  assert.deepEqual(brand.apps.player, {
    streamUrl: SETTINGS.public_stream_url,
    productionStreamUrl: SETTINGS.public_stream_url,
    productionNowUrl: SETTINGS.now_url,
    icecastStatusUrl: SETTINGS.status_url,
  });
  // Le harbor ne passe pas par la marque : un auditeur ne le voit pas.
  assert.deepEqual(brand.apps.harbor, FILE.apps.harbor);
});

test("un réglage vide ou illisible garde brand.json, sans toucher la marque de l'image", () => {
  const before = structuredClone(FILE);
  const junk = { ...UNSET, name: "   ", short: 12, tagline: "", now_url: ["x"] } as unknown as PublicStation;
  const brand = withStation(FILE, junk);
  assert.deepEqual(brand.suite, FILE.suite);
  assert.equal(brand.apps.player?.productionNowUrl, undefined);
  withStation(FILE, SETTINGS);
  assert.deepEqual(FILE, before);
  // Un réglage garde ses espaces dans le moteur ; la console les ignore.
  assert.equal(withStation(FILE, { ...UNSET, name: " Radio Moteur " }).suite.name, "Radio Moteur");
});

test("le casque écoute le flux réglé dans le moteur, et brand.json sans réglage", () => {
  const [set] = monitorSources(withStation(FILE, SETTINGS));
  assert.equal(set.stream, SETTINGS.public_stream_url);
  assert.equal(set.nowUrl, SETTINGS.now_url);
  assert.equal(set.statusUrl, SETTINGS.status_url);

  const [unset] = monitorSources(withStation(FILE, null));
  assert.equal(unset.stream, "https://fichier.radio.example/live.mp3");
  assert.equal(unset.statusUrl, "https://fichier.radio.example/status-json.xsl");
});

test("« Passer en direct » garde le direct de brand.json, même réglé dans le moteur", () => {
  // GET /station.json est réservé aux admins : le panneau ne lit pas les réglages du harbor.
  assert.deepEqual(harborAddress(withStation(FILE, SETTINGS)), {
    host: "fichier.radio.example",
    port: "6800",
    mount: "/stream",
  });
  assert.equal(harborAddress({ ...FILE, apps: { harbor: { url: "direct.radio.example:8005" } } }).host, "direct.radio.example");
  assert.ok(harborAddress({ ...FILE, apps: {} }).host);
});

test("le formulaire : un réglage absent est un champ vide, un champ vide efface le réglage", () => {
  const form = stationForm({ ...SETTINGS, tagline: null, harbor_port: 8005 });
  assert.equal(form.tagline, "");
  assert.equal(form.harbor_port, "8005");
  assert.equal("timezone" in form, false);

  const body = stationBody({ ...form, name: "  Radio Autre ", short: "   " });
  assert.equal(body.name, "Radio Autre");
  assert.equal(body.short, null);
  assert.equal(body.tagline, null);
  assert.equal(body.harbor_port, "8005");
  assert.equal("timezone" in body, false);
});

test("après un enregistrement, la console ne garde que ce qu'un auditeur voit", () => {
  assert.deepEqual(Object.keys(publicStation(SETTINGS)).sort(), Object.keys(UNSET).sort());
  assert.equal(publicStation(SETTINGS).name, "Radio Moteur");
});
