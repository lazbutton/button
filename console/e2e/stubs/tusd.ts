// Faux tusd des parcours : le protocole tus 1.0.0 que parle Uppy (création,
// reprise, suppression), sans les hooks du catalogue. Chaque envoi atterrit
// dans le dossier donné, avec un .info comme ceux de tusd. Il demande au
// moteur le droit de déposer, comme le fait nginx devant le vrai.
//   node --experimental-strip-types e2e/stubs/tusd.ts <port> <dossier> <moteur>

import { randomUUID } from "node:crypto";
import { createWriteStream, mkdirSync, rmSync, writeFileSync } from "node:fs";
import { createServer, type IncomingMessage, type ServerResponse } from "node:http";
import { join } from "node:path";

const [port, dossier, moteur] = process.argv.slice(2);
if (!port || !dossier || !moteur) {
  console.error("usage : tusd.ts <port> <dossier> <moteur>");
  process.exit(64);
}
mkdirSync(dossier, { recursive: true });

const BASE = "/tus/";
const TUS = { "Tus-Resumable": "1.0.0" };

type Upload = { id: string; size: number; offset: number; metadata: Record<string, string> };
const uploads = new Map<string, Upload>();

/** « filename ZmljaGllci53YXY=,filetype … » : des valeurs en base64. */
function metadataOf(raw: string | undefined): Record<string, string> {
  const metadata: Record<string, string> = {};
  for (const pair of (raw ?? "").split(",")) {
    const [key, value = ""] = pair.trim().split(" ");
    if (key) metadata[key] = Buffer.from(value, "base64").toString("utf8");
  }
  return metadata;
}

function saveInfo(upload: Upload): void {
  const info = { ID: upload.id, Size: upload.size, Offset: upload.offset, MetaData: upload.metadata };
  writeFileSync(join(dossier, `${upload.id}.info`), JSON.stringify(info));
}

function reply(response: ServerResponse, status: number, headers: Record<string, string | number> = {}, body = ""): void {
  response.writeHead(status, { ...TUS, ...headers, ...(body ? { "Content-Type": "text/plain; charset=utf-8" } : {}) });
  response.end(body);
}

/** Ajoute le corps de la requête au fichier, sans dépasser la taille annoncée. */
function append(request: IncomingMessage, response: ServerResponse, upload: Upload, status: number, headers: Record<string, string>): void {
  const out = createWriteStream(join(dossier, upload.id), { flags: "a" });
  out.on("error", (error) => {
    console.error(error);
    response.destroy();
  });
  let tooLong = false;
  request.on("data", (chunk: Buffer) => {
    if (tooLong || upload.offset + chunk.length > upload.size) {
      tooLong = true;
      return;
    }
    upload.offset += chunk.length;
    out.write(chunk);
  });
  request.on("end", () => {
    out.end(() => {
      saveInfo(upload);
      if (tooLong) return reply(response, 413, {}, "plus long que Upload-Length");
      reply(response, status, { ...headers, "Upload-Offset": upload.offset });
    });
  });
}

/**
 * Le garde de nginx devant /tus/ (auth_request /_deposit) : une session
 * d'équipe, ou le lien d'un invité (X-Invite-Token). 401 et 403 passent tels
 * quels, toute autre réponse devient 500, comme avec auth_request.
 */
async function depositStatus(request: IncomingMessage): Promise<number> {
  const headers: Record<string, string> = { cookie: request.headers.cookie ?? "" };
  const token = request.headers["x-invite-token"];
  if (typeof token === "string") headers["x-invite-token"] = token;
  try {
    const answer = await fetch(`${moteur}/agenda/deposit-auth`, { headers });
    if (answer.ok) return 200;
    return answer.status === 401 || answer.status === 403 ? answer.status : 500;
  } catch {
    return 500;
  }
}

async function handle(request: IncomingMessage, response: ServerResponse): Promise<void> {
  const path = new URL(request.url ?? "/", "http://tusd").pathname;
  // La découverte du protocole reste libre : elle sert aussi de sonde au banc.
  if (request.method === "OPTIONS") {
    return reply(response, 204, { "Tus-Version": "1.0.0", "Tus-Extension": "creation,creation-with-upload,termination" });
  }
  const allowed = await depositStatus(request);
  if (allowed !== 200) return reply(response, allowed, {}, allowed === 500 ? "moteur injoignable" : "dépôt refusé");
  if (path === BASE || path === BASE.slice(0, -1)) {
    if (request.method !== "POST") return reply(response, 405);
    const size = Number(request.headers["upload-length"]);
    if (!Number.isSafeInteger(size) || size < 0) return reply(response, 400, {}, "Upload-Length manquant");
    const upload: Upload = { id: randomUUID().replaceAll("-", ""), size, offset: 0, metadata: metadataOf(request.headers["upload-metadata"] as string | undefined) };
    uploads.set(upload.id, upload);
    writeFileSync(join(dossier, upload.id), "");
    const headers = { Location: `${BASE}${upload.id}` };
    if (request.headers["content-type"] === "application/offset+octet-stream") return append(request, response, upload, 201, headers);
    saveInfo(upload);
    return reply(response, 201, { ...headers, "Upload-Offset": 0 });
  }
  const upload = path.startsWith(BASE) ? uploads.get(path.slice(BASE.length)) : undefined;
  if (!upload) return reply(response, 404, {}, "envoi inconnu");
  if (request.method === "HEAD") {
    return reply(response, 200, { "Upload-Offset": upload.offset, "Upload-Length": upload.size, "Cache-Control": "no-store" });
  }
  if (request.method === "PATCH") {
    if (request.headers["content-type"] !== "application/offset+octet-stream") return reply(response, 415);
    if (Number(request.headers["upload-offset"]) !== upload.offset) return reply(response, 409, {}, "Upload-Offset ne suit pas");
    return append(request, response, upload, 204, {});
  }
  if (request.method === "DELETE") {
    uploads.delete(upload.id);
    rmSync(join(dossier, upload.id), { force: true });
    rmSync(join(dossier, `${upload.id}.info`), { force: true });
    return reply(response, 204);
  }
  reply(response, 405);
}

// Une erreur répond 500 avec son message : le faux service reste debout pour
// les parcours suivants.
const server = createServer((request, response) => {
  handle(request, response).catch((error: unknown) => {
    console.error(error);
    if (!response.headersSent) reply(response, 500, {}, String(error));
    else response.destroy();
  });
});

server.listen(Number(port), "127.0.0.1", () => {
  console.log(`faux tusd sur http://127.0.0.1:${port}${BASE}, envois dans ${dossier}`);
});
