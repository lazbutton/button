import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { COVER_DOMAINS, coverUrl } from "./covers.ts";

const DEEZER = "https://cdn-images.dzcdn.net/images/cover/abc/500x500-000000-80-0-0.jpg";

test("une pochette des sources se montre, rien d'autre", () => {
  assert.equal(coverUrl(DEEZER), DEEZER);
  assert.equal(coverUrl(` ${DEEZER} `), DEEZER);
  assert.equal(coverUrl("https://is1-ssl.mzstatic.com/image/thumb/x/600x600bb.jpg"), "https://is1-ssl.mzstatic.com/image/thumb/x/600x600bb.jpg");
  assert.equal(coverUrl("https://f4.bcbits.com/img/a0000000012_5.jpg"), "https://f4.bcbits.com/img/a0000000012_5.jpg");
  for (const refused of [
    undefined,
    null,
    "",
    42,
    "http://cdn-images.dzcdn.net/x.jpg",
    "https://dzcdn.net.example/x.jpg",
    "https://evildzcdn.net/x.jpg",
    "https://a:b@cdn-images.dzcdn.net/x.jpg",
    "https://cdn-images.dzcdn.net:8443/x.jpg",
    "javascript:alert(1)",
    "data:image/png;base64,AAAA",
    "/logo.svg",
  ]) {
    assert.equal(coverUrl(refused), null, String(refused));
  }
});

test("la politique de contenu admet chaque hôte de pochettes, et rien de plus", () => {
  const template = readFileSync(new URL("../../docker/security-headers.conf.template", import.meta.url), "utf8");
  const header = template.split("\n").find((line) => line.startsWith("add_header Content-Security-Policy"));
  const imgSrc = /img-src ([^;"]+)/.exec(header ?? "")?.[1].trim().split(/\s+/) ?? [];
  assert.deepEqual(imgSrc, ["'self'", ...COVER_DOMAINS.map((domain) => `https://*.${domain}`)]);
});
