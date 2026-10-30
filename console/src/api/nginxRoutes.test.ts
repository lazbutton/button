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
const HEADERS = fileURLToPath(new URL("../../docker/security-headers.conf.template", import.meta.url));
const ENTRYPOINT = fileURLToPath(new URL("../../docker/docker-entrypoint.sh", import.meta.url));

/** Les chemins servis par d'autres blocs de nginx que la liste du moteur. */
const OTHER_LOCATIONS = /^\/(library|tus|public)\//;
/** Le catalogue et tusd : nginx y demande une session. */
const SESSION_LOCATIONS = /^\^?\/(library|tus)\//;
const INCLUDE_HEADERS = /^\s*include\s+\/etc\/nginx\/security-headers\.conf;/m;

const CALL =
  /\b(?:apiGet|apiSend|apiPost|apiDelete|apiDeleteJson|apiPostJson|apiPut|apiPatch|apiUpload|apiBlob|apiArrayBuffer|publicJson)\s*(?:<[^()]*?>)?\s*\(\s*(?:"[A-Z]+"\s*,\s*)?["'`](\/[^"'`]*)/g;
const PREFIXED = /\$\{API_PREFIX\}(\/[^"'`]*)/g;

function engineAllowlist(): RegExp {
  const template = readFileSync(TEMPLATE, "utf8");
  const match = template.match(/location ~ \^\/\((.+)\) \{/);
  assert.ok(match, "liste des routes du moteur introuvable dans nginx.conf.template");
  return new RegExp(`^/(${match[1]})`);
}

/** Les blocs `location` du gabarit : leur chemin, leur contenu, puis leur modificateur (`=`, `~`, `^~`…). */
function locationBlocks(): [string, string, string][] {
  const template = readFileSync(TEMPLATE, "utf8");
  return [...template.matchAll(/^\s*location\s+(?:(\S+)\s+)?(\S+)\s*\{\n([\s\S]*?)\n\s*\}$/gm)].map(
    (match) => [match[2], match[3], match[1] ?? ""],
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

// Un bloc qui pose son propre add_header n'hérite plus de ceux du bloc server :
// chaque bloc qui répond au navigateur inclut les en-têtes de sécurité.
test("chaque bloc de nginx pose les en-têtes de sécurité", () => {
  const blocks = locationBlocks();
  const count = readFileSync(TEMPLATE, "utf8").match(/^\s*location\s/gm)?.length;
  assert.equal(blocks.length, count, "un bloc location échappe au motif de locationBlocks()");
  const bare = blocks
    .filter(([, body]) => !/^\s*internal;/m.test(body) && !INCLUDE_HEADERS.test(body))
    .map(([path]) => path);
  assert.deepEqual(bare, [], "include /etc/nginx/security-headers.conf; manquant dans console/docker/nginx.conf.template");
});

test("un bloc change Referrer-Policy après l'include, et l'invité garde no-referrer", () => {
  const blocks = locationBlocks();
  for (const [path, body] of blocks) {
    const set = body.search(/^\s*set\s+\$button_referrer_policy\s/m);
    if (set < 0) continue;
    const include = body.search(INCLUDE_HEADERS);
    assert.ok(include >= 0 && include < set, `${path} : le set de $button_referrer_policy doit suivre l'include`);
  }
  const invitation = blocks.find(([path]) => path === "/invitation")?.[1] ?? "";
  assert.match(invitation, /^\s*set \$button_referrer_policy "no-referrer";$/m);
});

// Un bloc regex qui correspond l'emporte sur un préfixe sans ^~ : le bloc des
// extensions prendrait les .js et .css du build, sans leur cache d'un an.
test("les fichiers de /assets/ gardent leur cache d'un an", () => {
  const assets = locationBlocks().find(([path]) => path === "/assets/");
  assert.ok(assets, "bloc /assets/ introuvable dans console/docker/nginx.conf.template");
  const [, body, modifier] = assets;
  assert.equal(modifier, "^~", "^~ manquant devant /assets/ dans console/docker/nginx.conf.template");
  assert.match(body, /^\s*add_header Cache-Control "public, max-age=31536000, immutable";$/m);
});

test("le fichier inclus pose les en-têtes attendus, aussi sur les erreurs", () => {
  const text = readFileSync(HEADERS, "utf8");
  const lines = text.match(/^add_header .*$/gm) ?? [];
  const headers = new Map(
    lines.map((line): [string, string] => {
      const match = line.match(/^add_header (\S+) (?:"([^"]*)"|(\S+)) always;$/);
      assert.ok(match, `${line} : une valeur, puis always, pour les réponses d'erreur aussi`);
      return [match[1], match[2] ?? match[3]];
    }),
  );
  assert.deepEqual(
    [...headers.keys()].sort(),
    ["Content-Security-Policy-Report-Only", "Permissions-Policy", "Referrer-Policy", "X-Content-Type-Options", "X-Frame-Options"],
  );
  assert.match(text, /^set \$button_referrer_policy "strict-origin-when-cross-origin";$/m);
  assert.equal(headers.get("Referrer-Policy"), "$button_referrer_policy");
  assert.equal(headers.get("X-Content-Type-Options"), "nosniff");
  assert.equal(headers.get("X-Frame-Options"), "DENY");
  assert.match(headers.get("Permissions-Policy") ?? "", /^(?=.*\bcamera=\(\))(?=.*\bmicrophone=\(\))/);
  const csp = headers.get("Content-Security-Policy-Report-Only") ?? "";
  assert.match(csp, /(^|; )frame-ancestors 'none'(;|$)/);
  assert.match(csp, /(^|; )media-src [^;]*\$\{CSP_MEDIA_SRC\}/);
  // Le moniteur lit aussi le flux par fetch.
  assert.match(csp, /(^|; )connect-src [^;]*\$\{CSP_MEDIA_SRC\}/);
  assert.match(csp, /(^|; )connect-src [^;]*\$\{CSP_CONNECT_SRC\}/);
});

test("le script de démarrage rend chaque variable des gabarits", () => {
  const entrypoint = readFileSync(ENTRYPOINT, "utf8");
  const listed = entrypoint.match(/^variables='([^']*)'$/m)?.[1].split(" ") ?? [];
  // Les variables de nginx sont en minuscules : ${button_head}, $uri…
  const used = new Set(
    [TEMPLATE, HEADERS].flatMap((file) =>
      [...readFileSync(file, "utf8").matchAll(/\$\{[A-Z][A-Z0-9_]*\}/g)].map((match) => match[0]),
    ),
  );
  assert.deepEqual([...used].filter((name) => !listed.includes(name)), [], "à ajouter à la liste de docker-entrypoint.sh");
  assert.ok(entrypoint.includes("/etc/nginx/security-headers.conf"), "security-headers.conf n'est pas rendu");
});

// verifier.sh nginx copie les gabarits où le Dockerfile les met, puis lance
// le script de démarrage : les trois doivent dire les mêmes chemins.
test("le Dockerfile et verifier.sh posent les gabarits que lit le script de démarrage", () => {
  const read = (path: string) => readFileSync(fileURLToPath(new URL(path, import.meta.url)), "utf8");
  const pairs = (text: string, pattern: RegExp) => new Set([...text.matchAll(pattern)].map((m) => `${m[1]} → ${m[2]}`));
  const image = pairs(read("../../Dockerfile"), /^COPY docker\/(\S+\.template) (\S+)$/gm);
  const verifier = pairs(read("../../../scripts/verifier.sh"), /cp \/button\/(\S+\.template) (\S+?) /g);
  const templates = [...read("../../docker/docker-entrypoint.sh").matchAll(/< (\/etc\/nginx\/\S+\.template)/g)].map((m) => m[1]);
  assert.equal(templates.length, 2, "le script de démarrage rend deux gabarits");
  for (const template of templates) {
    const copy = [...image].find((pair) => pair.endsWith(` → ${template}`));
    assert.ok(copy, `${template} : aucun COPY du Dockerfile ne le pose`);
    assert.ok(verifier.has(copy), `${copy} : absent de check_nginx dans scripts/verifier.sh`);
  }
});

test("le motif reconnaît les appels de la console", () => {
  const allowed = engineAllowlist();
  assert.ok(allowed.test("/carts/12/sounds.json"));
  assert.ok(allowed.test("/csrf.json"));
  assert.equal(allowed.test("/inconnu.json"), false);
  assert.equal(staticPart("/carts/${cartId}/now.json"), "/carts/");
  assert.equal(staticPart("/autodj/conducteur.json?horizon=360"), "/autodj/conducteur.json");
});
