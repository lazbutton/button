import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import { join, relative } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

// En prod, nginx ne relaie vers le moteur qu'une liste de chemins. Une route
// absente de cette liste marche en dev (proxy de Vite) et rend la page HTML
// de la console en prod. Ce test lit les appels de la console et la liste.

const SRC = fileURLToPath(new URL("..", import.meta.url));
const TEMPLATE = fileURLToPath(new URL("../../docker/nginx.conf.template", import.meta.url));

/** Les chemins servis par d'autres blocs de nginx que la liste du moteur. */
const OTHER_LOCATIONS = /^\/(library|tus|public)\//;
/** Le catalogue et tusd : nginx y demande une session. */
const SESSION_LOCATIONS = /^\^?\/(library|tus)\//;

const CALL =
  /\b(?:apiGet|apiSend|apiPost|apiDelete|apiDeleteJson|apiPostJson|apiPut|apiPatch|apiUpload|apiBlob|apiArrayBuffer|publicJson)\s*(?:<[^()]*?>)?\s*\(\s*(?:"[A-Z]+"\s*,\s*)?["'`](\/[^"'`]*)/g;
const PREFIXED = /\$\{API_PREFIX\}(\/[^"'`]*)/g;

function engineAllowlist(): RegExp {
  const template = readFileSync(TEMPLATE, "utf8");
  const match = template.match(/location ~ \^\/\((.+)\) \{/);
  assert.ok(match, "liste des routes du moteur introuvable dans nginx.conf.template");
  return new RegExp(`^/(${match[1]})`);
}

/** Les blocs `location` du gabarit : leur chemin, puis leur contenu. */
function locationBlocks(): [string, string][] {
  const template = readFileSync(TEMPLATE, "utf8");
  return [...template.matchAll(/^\s*location\s+(?:\S+\s+)?(\S+)\s*\{\n([\s\S]*?)\n\s*\}$/gm)].map(
    (match) => [match[1], match[2]],
  );
}

function sources(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) return entry.name === "mock" ? [] : sources(path);
    return /\.tsx?$/.test(entry.name) && !entry.name.endsWith(".test.ts") ? [path] : [];
  });
}

/** Le début fixe d'un chemin : jusqu'au premier `${` ou `?`. */
function staticPart(raw: string): string {
  return raw.split("${")[0].split("?")[0];
}

function consolePaths(): Map<string, string> {
  const found = new Map<string, string>();
  for (const file of sources(SRC)) {
    const text = readFileSync(file, "utf8");
    for (const pattern of [CALL, PREFIXED]) {
      for (const match of text.matchAll(pattern)) {
        const path = staticPart(match[1]);
        if (path && !found.has(path)) found.set(path, relative(SRC, file));
      }
    }
  }
  return found;
}

test("chaque route appelée par la console passe nginx en prod", () => {
  const allowed = engineAllowlist();
  const paths = consolePaths();
  assert.ok(paths.size > 20, "trop peu d'appels trouvés : le motif ne lit plus le code");
  const blocked = [...paths]
    .filter(([path]) => !OTHER_LOCATIONS.test(path) && !allowed.test(path))
    .map(([path, file]) => `${path} (${file})`);
  assert.deepEqual(blocked, [], "à ajouter dans console/docker/nginx.conf.template");
});

test("le catalogue et les envois demandent une session à nginx", () => {
  const blocks = locationBlocks().filter(([path]) => SESSION_LOCATIONS.test(path));
  const paths = blocks.map(([path]) => path);
  assert.ok(paths.includes("/library/") && paths.includes("/tus/"), `blocs trouvés : ${paths.join(", ")}`);
  const open = blocks.filter(([, body]) => !/^\s*auth_request\s+\/\S*;/m.test(body)).map(([path]) => path);
  assert.deepEqual(open, [], "auth_request manquant dans console/docker/nginx.conf.template");
});

test("le motif reconnaît les appels de la console", () => {
  const allowed = engineAllowlist();
  assert.ok(allowed.test("/carts/12/sounds.json"));
  assert.ok(allowed.test("/csrf.json"));
  assert.equal(allowed.test("/inconnu.json"), false);
  assert.equal(staticPart("/carts/${cartId}/now.json"), "/carts/");
  assert.equal(staticPart("/autodj/conducteur.json?horizon=360"), "/autodj/conducteur.json");
});
