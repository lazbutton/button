import assert from "node:assert/strict";
import test from "node:test";
import {
  DEFAULT_SOURCE_URL,
  readSourceArchive,
  SOURCE_DESCRIPTOR,
  sourceArchive,
  sourceLink,
} from "./sourceCode.ts";

// source.json, tel que l'écrit scripts/version.py source.
const DESCRIPTOR = {
  version: "1.0.0",
  commit: "da35feba8b2719e51c974ac444a7e336b8db3b98",
  file: "button-1.0.0-source.tar.gz",
};

/** nginx qui répond `status`, `body` et `type` ; `calls` garde ce que la console lui a demandé. */
function nginx(
  status: number,
  body: string,
  type = "application/json",
  calls: [string, RequestInit | undefined][] = [],
): typeof fetch {
  return (async (url: string, init?: RequestInit) => {
    calls.push([url, init]);
    return new Response(body, { status, headers: { "Content-Type": type } });
  }) as typeof fetch;
}

test("source.json nomme l'archive, un nom de fichier seul", () => {
  assert.deepEqual(sourceArchive(DESCRIPTOR), { file: "button-1.0.0-source.tar.gz" });
  assert.deepEqual(sourceArchive({ ...DESCRIPTOR, version: "main", file: "button-main-source.tar.gz" }), {
    file: "button-main-source.tar.gz",
  });
  for (const file of ["", "../secret.tar.gz", "a/b.tar.gz", ".cache.tar.gz", "button-1.0.0.zip", "button 1.0.0.tar.gz", 12]) {
    assert.equal(sourceArchive({ ...DESCRIPTOR, file }), null, String(file));
  }
  for (const payload of [null, [], "button-1.0.0-source.tar.gz", { version: "1.0.0" }]) {
    assert.equal(sourceArchive(payload), null, JSON.stringify(payload));
  }
});

test("la console lit source.json avec sa session, et ne relit que sans réponse sûre", async () => {
  const calls: [string, RequestInit | undefined][] = [];
  const read = await readSourceArchive(nginx(200, JSON.stringify(DESCRIPTOR), "application/json", calls));
  assert.deepEqual(read, { archive: { file: "button-1.0.0-source.tar.gz" }, retry: false });
  assert.equal(calls[0][0], SOURCE_DESCRIPTOR);
  assert.equal(SOURCE_DESCRIPTOR, "/code-source/source.json");
  assert.equal(calls[0][1]?.credentials, "same-origin");
  assert.equal(calls[0][1]?.cache, "no-store");

  // Une image construite sans archive : relire n'y changera rien.
  assert.deepEqual(await readSourceArchive(nginx(404, "<html>404</html>", "text/html")), { archive: null, retry: false });
  // En dev, la console elle-même, ou un source.json qui ne nomme rien : pas d'archive.
  assert.deepEqual(await readSourceArchive(nginx(200, "<!doctype html><html></html>", "text/html")), {
    archive: null,
    retry: false,
  });
  assert.deepEqual(await readSourceArchive(nginx(200, "{\"version\": ")), { archive: null, retry: false });
  assert.deepEqual(await readSourceArchive(nginx(200, "{}")), { archive: null, retry: false });
  // Session échue, ou moteur qui ne répond pas à la demande de session de nginx : on relira.
  assert.deepEqual(await readSourceArchive(nginx(401, "<html>401</html>", "text/html")), { archive: null, retry: true });
  assert.deepEqual(await readSourceArchive(nginx(500, "<html>500</html>", "text/html")), { archive: null, retry: true });
  const unreachable = (async () => {
    throw new TypeError("Failed to fetch");
  }) as typeof fetch;
  assert.deepEqual(await readSourceArchive(unreachable), { archive: null, retry: true });
});

test("sans réponse dans le délai, le lien garde le dépôt, et on relira", async () => {
  const silent = ((_url: string, init?: RequestInit) =>
    new Promise((_resolve, reject) => {
      init?.signal?.addEventListener("abort", () => reject(init.signal?.reason));
    })) as typeof fetch;
  // En node, le minuteur d'AbortSignal.timeout ne retient pas le processus : celui-ci, si.
  const alive = setTimeout(() => {}, 1_000);
  try {
    assert.deepEqual(await readSourceArchive(silent, 20), { archive: null, retry: true });
  } finally {
    clearTimeout(alive);
  }
});

test("le lien prend le réglage de la station, puis l'archive qu'elle sert, puis le dépôt", () => {
  const archive = { file: "button-1.0.0-source.tar.gz" };
  // Une version modifiée : son propre code, même quand l'image porte celui de BUTTON.
  assert.deepEqual(sourceLink("https://code.radio.example/button", archive), {
    href: "https://code.radio.example/button",
  });
  assert.deepEqual(sourceLink(undefined, archive), {
    href: "/code-source/button-1.0.0-source.tar.gz",
    download: "button-1.0.0-source.tar.gz",
  });
  assert.deepEqual(sourceLink("  ", archive), sourceLink(undefined, archive));
  assert.deepEqual(sourceLink(undefined, null), { href: DEFAULT_SOURCE_URL });
  assert.equal(DEFAULT_SOURCE_URL, "https://github.com/lazbutton/button");
});
