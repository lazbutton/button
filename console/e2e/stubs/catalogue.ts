// Faux catalogue des parcours : les routes de services/catalog/app.py que la
// console lit, sans Meilisearch. Il indexe à chaque appel les fichiers audio
// de la banque du lancement, celle que le moteur reçoit aussi (MEDIA_ROOT).
// Comme le vrai, il demande une session au moteur, sauf pour /health. Les
// routes qui écrivent répondent 501 : un parcours qui en dépend échoue en le
// disant, au lieu de passer sur un faux succès. Rien ne range les envois de
// tusd : la file et l'avancée de /inbox.json restent vides.
//   node --experimental-strip-types e2e/stubs/catalogue.ts <port> <banque> <moteur>

import { createHash } from "node:crypto";
import { closeSync, createReadStream, existsSync, openSync, readdirSync, readSync, statSync } from "node:fs";
import { createServer, type IncomingMessage, type ServerResponse } from "node:http";
import { basename, dirname, extname, join } from "node:path";

const [port, banque, moteur] = process.argv.slice(2);
if (!port || !banque || !moteur) {
  console.error("usage : catalogue.ts <port> <banque> <moteur>");
  process.exit(64);
}

type Hit = {
  id: string;
  path: string;
  filename: string;
  title: string;
  artist: string;
  kind: string;
  grouping: string;
  folder: string;
  top: string;
  duration: number;
  bytes: number;
  mime: string;
};

// Les extensions de AUDIO_EXT, dans services/catalog/app.py.
const AUDIO: Record<string, string> = {
  ".mp3": "audio/mpeg",
  ".wav": "audio/x-wav",
  ".flac": "audio/flac",
  ".ogg": "audio/ogg",
  ".m4a": "audio/mp4",
  ".aac": "audio/aac",
  ".aiff": "audio/aiff",
  ".aif": "audio/aiff",
  ".webm": "audio/webm",
};
const SKIP_TOP = new Set(["00-inbox", "90-trash"]);
const KIND_FOLDERS: Record<string, string> = {
  "30-habillage/jingles": "jingle",
  "30-habillage/ids": "jingle",
  "30-habillage/stings": "jingle",
  "30-habillage/pubs": "pub",
};

function kindOf(rel: string): string {
  for (const [prefix, kind] of Object.entries(KIND_FOLDERS)) {
    if (rel.startsWith(`${prefix}/`)) return kind;
  }
  const parts = rel.split("/");
  if (parts[0] === "40-emissions" && parts[2] === "podcasts") return "podcast";
  if (parts[0] === "40-emissions" && parts[2] === "entiere") return "emission";
  return "son";
}

function groupingOf(rel: string): string {
  const parts = rel.split("/");
  if (parts[0] === "10-rotation") return "rotation";
  if (parts.length >= 2 && (parts[0] === "20-archives" || parts[0] === "40-emissions")) return parts[1];
  return "";
}

/** La durée d'un WAV, lue dans ses blocs « fmt » et « data ». 0 sinon. */
function wavSeconds(path: string): number {
  const head = Buffer.alloc(256);
  const fd = openSync(path, "r");
  try {
    readSync(fd, head, 0, head.length, 0);
  } finally {
    closeSync(fd);
  }
  if (head.toString("ascii", 0, 4) !== "RIFF" || head.toString("ascii", 8, 12) !== "WAVE") return 0;
  let byteRate = 0;
  for (let at = 12; at + 8 <= head.length; ) {
    const id = head.toString("ascii", at, at + 4);
    const size = head.readUInt32LE(at + 4);
    if (id === "fmt ") byteRate = head.readUInt32LE(at + 16);
    if (id === "data") return byteRate ? Math.round((size / byteRate) * 1000) / 1000 : 0;
    at += 8 + size + (size % 2);
  }
  return 0;
}

function index(): Hit[] {
  const hits: Hit[] = [];
  for (const rel of readdirSync(banque, { recursive: true, encoding: "utf8" }).sort()) {
    const path = rel.split("\\").join("/");
    const mime = AUDIO[extname(path).toLowerCase()];
    const file = join(banque, path);
    const top = path.split("/")[0];
    if (!mime || SKIP_TOP.has(top) || basename(path).startsWith(".") || !statSync(file).isFile()) continue;
    hits.push({
      id: createHash("sha256").update(path).digest("hex").slice(0, 20),
      path,
      filename: basename(path),
      // Sans étiquettes, le vrai catalogue titre un fichier par son nom.
      title: basename(path, extname(path)).replaceAll("_", " ").trim(),
      artist: "",
      kind: kindOf(path),
      grouping: groupingOf(path),
      folder: dirname(path),
      top,
      duration: extname(path).toLowerCase() === ".wav" ? wavSeconds(file) : 0,
      bytes: statSync(file).size,
      mime,
    });
  }
  return hits;
}

/** La place prise, comptée comme used_bytes() du vrai : tous les fichiers de ces trois dossiers. */
function usedBytes(): number {
  let total = 0;
  for (const top of ["00-inbox", "10-rotation", "20-archives"]) {
    const folder = join(banque, top);
    if (!existsSync(folder)) continue;
    for (const rel of readdirSync(folder, { recursive: true, encoding: "utf8" })) {
      const stat = statSync(join(folder, rel));
      if (stat.isFile()) total += stat.size;
    }
  }
  return total;
}

/** grouping=a,b se lit « a ou b », comme any_of() du vrai catalogue. */
function anyOf(raw: string | null, value: string): boolean {
  const values = (raw ?? "").split(",").map((part) => part.trim()).filter(Boolean);
  return values.length === 0 || values.includes(value);
}

function search(params: URLSearchParams): { hits: Hit[]; estimatedTotalHits: number } {
  const words = (params.get("q") ?? "").toLowerCase().split(/\s+/).filter(Boolean);
  const kind = params.get("kind") ?? "";
  const limit = Math.min(Number(params.get("limit") || 80) || 80, 200);
  const found = index().filter((hit) => {
    const text = `${hit.title} ${hit.artist} ${hit.path}`.toLowerCase();
    if (!words.every((word) => text.includes(word))) return false;
    if (kind === "son" && !["son", "emission", "podcast"].includes(hit.kind)) return false;
    if (kind && kind !== "son" && hit.kind !== kind) return false;
    return anyOf(params.get("grouping"), hit.grouping) && anyOf(params.get("folder"), hit.folder) && anyOf(params.get("top"), hit.top);
  });
  return { hits: found.slice(0, limit), estimatedTotalHits: found.length };
}

function json(response: ServerResponse, status: number, payload: unknown): void {
  const body = JSON.stringify(payload);
  response.writeHead(status, { "Content-Type": "application/json; charset=utf-8", "Content-Length": Buffer.byteLength(body) });
  response.end(body);
}

/** Le fichier, en entier ou par plage : un lecteur audio demande « bytes=0- ». */
function sendFile(request: IncomingMessage, response: ServerResponse, hit: Hit): void {
  const file = join(banque, hit.path);
  const size = statSync(file).size;
  const [, first = "", last = ""] = /^bytes=(\d*)-(\d*)$/.exec(request.headers.range ?? "") ?? [];
  const partial = Boolean(first || last);
  let start = 0;
  let end = size - 1;
  if (first) {
    start = Number(first);
    if (last) end = Math.min(Number(last), size - 1);
  } else if (last) {
    start = Math.max(0, size - Number(last));
  }
  if (start > end) {
    response.writeHead(416, { "Content-Range": `bytes */${size}` });
    response.end();
    return;
  }
  const headers: Record<string, string | number> = {
    "Content-Type": hit.mime,
    "Content-Length": end - start + 1,
    "Accept-Ranges": "bytes",
  };
  if (partial) headers["Content-Range"] = `bytes ${start}-${end}/${size}`;
  response.writeHead(partial ? 206 : 200, headers);
  if (request.method === "HEAD") {
    response.end();
    return;
  }
  createReadStream(file, { start, end }).pipe(response);
}

/** La session du navigateur, lue par le moteur comme account_permissions() du vrai catalogue. */
async function sessionStatus(request: IncomingMessage): Promise<number> {
  try {
    const answer = await fetch(`${moteur}/account.json`, { headers: { cookie: request.headers.cookie ?? "" } });
    return answer.ok ? 200 : 401;
  } catch {
    return 502;
  }
}

async function handle(request: IncomingMessage, response: ServerResponse): Promise<void> {
  const url = new URL(request.url ?? "/", "http://catalogue");
  let path: string;
  try {
    path = decodeURIComponent(url.pathname);
  } catch {
    return json(response, 400, { error: "adresse illisible" });
  }
  if (path === "/health" || path === "/health/live") return json(response, 200, { status: "live" });
  const session = await sessionStatus(request);
  if (session === 401) return json(response, 401, { error: "session absente" });
  if (session !== 200) return json(response, 502, { error: "moteur injoignable" });
  if (request.method === "GET" || request.method === "HEAD") {
    if (path === "/search") return json(response, 200, search(url.searchParams));
    if (path === "/volume.json") return json(response, 200, { name: "BUTTON", host: "" });
    if (path === "/inbox.json") {
      return json(response, 200, {
        destinations: [{ id: "rotation", label: "Rotation", group: "rotation", folder: "10-rotation" }],
        quota: { used: usedBytes(), limit: 100 * 1024 ** 3 },
        queue: [],
        rejected: [],
        progress: [],
      });
    }
    if (path.startsWith("/media/")) {
      const hit = index().find((item) => item.id === path.slice("/media/".length));
      if (!hit) return json(response, 404, { error: "not_found" });
      return sendFile(request, response, hit);
    }
  }
  if (request.method === "POST" && ["/prune", "/banks.json", "/volume-password.json"].includes(path)) {
    return json(response, 501, { error: `Le faux catalogue des parcours ne simule pas ${path}.` });
  }
  json(response, 404, { error: "not_found" });
}

// Une erreur répond 500 avec son message : le faux service reste debout pour
// les parcours suivants.
const server = createServer((request, response) => {
  handle(request, response).catch((error: unknown) => {
    console.error(error);
    if (!response.headersSent) json(response, 500, { error: String(error) });
    else response.destroy();
  });
});

server.listen(Number(port), "127.0.0.1", () => {
  console.log(`faux catalogue sur http://127.0.0.1:${port}, banque ${banque}`);
});
