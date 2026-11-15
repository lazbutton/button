import type { Page, Route } from "@playwright/test";
import { verifierAccessibilite } from "./accessibilite.ts";
import { antenne, expect, seConnecter, test } from "./banc.ts";

// Le verdict « femme ou minorité de genre » dans le tableau de la banque (FON-80).
// Le moteur du banc n'a ni bibliothèque, ni le rangement allumé : le parcours
// allume les interrupteurs dans /account.json, et rend une bibliothèque tenue ici,
// filtrée et triée comme le moteur (engine/radiotomate/services/bank_titles.py).
// Éteint, le moteur ne dit rien du verdict : ni dans le compte, ni dans les titres.

type Titre = Record<string, unknown> & { id: number; title: string; fmg?: string };

function bibliotheque(verdict: boolean): Titre[] {
  const titre = (id: number, title: string, artist: string, fmg: string): Titre => ({
    id,
    title,
    artist,
    album: "Ciel",
    year: 2015,
    genre: "Jazz",
    famille: "jazz",
    famille_label: "Jazz",
    duration: 180,
    zone: "rotation",
    collection: "rotation",
    path: `10-rotation/${id}.mp3`,
    missing: [],
    ...(verdict ? { fmg } : {}),
  });
  return [titre(1, "Comète", "Orage", "oui"), titre(2, "Dune", "Zéphyr", "non"), titre(3, "Brume", "Lune", "")];
}

const LABELS: Record<string, string> = { oui: "Oui", mixte: "Mixte", non: "Non", "": "" };

async function tableau(page: Page, verdict: boolean): Promise<URL[]> {
  const titres = bibliotheque(verdict);
  const demandes: URL[] = [];
  await page.route("**/account.json", async (route: Route) => {
    if (route.request().method() !== "GET") return route.fallback();
    const reponse = await route.fetch();
    const compte = (await reponse.json()) as Record<string, unknown>;
    const features = { bank_tidy: true, ...(verdict ? { fiches_fmg: true } : {}) };
    await route.fulfill({ response: reponse, json: { ...compte, features } });
  });
  await page.route("**/media/titles.json*", async (route: Route) => {
    const url = new URL(route.request().url());
    demandes.push(url);
    const q = url.searchParams;
    const gardes = titres.filter((entry) => !q.has("fmg") || entry.fmg === q.get("fmg"));
    const noms = (q.get("facets") ?? "").split(",").filter(Boolean);
    const facettes = Object.fromEntries(
      noms.map((nom) => {
        const comptes = new Map<string, number>();
        for (const entry of titres) {
          const valeur = String(entry[nom] ?? "");
          comptes.set(valeur, (comptes.get(valeur) ?? 0) + 1);
        }
        return [
          nom,
          [...comptes].map(([value, count]) => ({
            value,
            label: nom === "fmg" ? LABELS[value] : value,
            count,
          })),
        ];
      }),
    );
    await route.fulfill({
      json: {
        titles: gardes,
        total: titres.length,
        matched: gardes.length,
        offset: 0,
        limit: 100,
        sort: q.get("sort") ?? "artist",
        order: q.get("order") ?? "asc",
        facets: facettes,
      },
    });
  });
  return demandes;
}

test("le verdict allumé : une colonne, et le tableau se range par verdict", async ({ page }) => {
  const demandes = await tableau(page, true);
  await seConnecter(page, "admin");
  await expect(antenne(page)).toBeVisible();
  await page.goto("/sons?onglet=importer");

  const banque = page.getByRole("region", { name: "Toute la banque" });
  await expect(banque.getByRole("columnheader", { name: "Femme ou minorité de genre" })).toBeVisible();
  await expect(banque.getByRole("row", { name: /Comète/ }).getByRole("cell", { name: "Oui", exact: true })).toBeVisible();

  const colonne = page.getByRole("complementary", { name: "Ranger la banque" });
  await colonne.getByRole("combobox", { name: "Ranger par" }).click();
  await page.getByRole("option", { name: "Verdict", exact: true }).click();
  await colonne.getByRole("option", { name: /^Oui/ }).click();
  const oui = page.getByRole("region", { name: "Oui" });
  await expect(oui.getByRole("button", { name: "Comète", exact: true })).toBeVisible();
  await expect(oui.getByRole("button", { name: "Dune", exact: true })).toHaveCount(0);
  expect(demandes.at(-1)?.searchParams.get("fmg")).toBe("oui");
  await verifierAccessibilite(page, "le tableau rangé par verdict");
});

test("le verdict éteint : ni colonne, ni rangement, et une adresse qui le demandait retombe", async ({ page }) => {
  const demandes = await tableau(page, false);
  await seConnecter(page, "admin");
  await expect(antenne(page)).toBeVisible();
  await page.goto("/sons?onglet=importer&ranger=fmg&groupe=oui&tri=fmg");

  const banque = page.getByRole("region", { name: "Toute la banque" });
  await expect(banque.getByRole("button", { name: "Comète", exact: true })).toBeVisible();
  await expect(page.getByText("Femme ou minorité de genre")).toHaveCount(0);
  const colonne = page.getByRole("complementary", { name: "Ranger la banque" });
  await colonne.getByRole("combobox", { name: "Ranger par" }).click();
  await expect(page.getByRole("option", { name: "Verdict", exact: true })).toHaveCount(0);
  await page.keyboard.press("Escape");
  await expect(colonne.getByRole("combobox", { name: "Ranger par" })).toHaveAttribute("aria-expanded", "false");
  for (const demande of demandes) expect(demande.search).not.toContain("fmg");
});
