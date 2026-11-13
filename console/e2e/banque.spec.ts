import type { Page, Route } from "@playwright/test";
import { alerte, antenne, avis, expect, seConnecter, test } from "./banc.ts";

// La vue « Contenu » de Sons → Banque. Le faux catalogue lit la banque du banc
// (engine/tests/e2e/seed.py : deux titres dans la rotation), et ne change rien
// sur le disque : les gestes qui écrivent se simulent ici par page.route, sur
// une banque tenue en mémoire, comme le vrai catalogue les rend.

type Fichier = {
  name: string;
  title: string;
  artist: string;
  duration: number | null;
  bytes: number;
  modified: string;
};
type Etagere = { id: string; label: string; group: "rotation" | "archives"; folder: string; files: Fichier[] };

function fichier(name: string, minutes = 3): Fichier {
  return {
    name,
    title: name.replace(/\.[^.]+$/, ""),
    artist: "",
    duration: minutes * 60,
    bytes: minutes * 1_000_000,
    modified: "2026-11-10T09:00:00+00:00",
  };
}

function etagere(id: string, label: string, files: Fichier[]): Etagere {
  const rotation = id === "rotation";
  return { id, label, group: rotation ? "rotation" : "archives", folder: rotation ? "10-rotation" : `20-archives/${id}`, files };
}

/** Les routes du contenu de la banque, sur une banque en mémoire. Rend les gestes reçus, dans l'ordre. */
async function fauxContenu(page: Page, etageres: Etagere[]): Promise<Array<{ chemin: string; corps: Record<string, unknown> }>> {
  const gestes: Array<{ chemin: string; corps: Record<string, unknown> }> = [];
  const destination = ({ id, label, group, folder }: Etagere) => ({ id, label, group, folder });
  const poids = (item: Etagere) => item.files.reduce((total, file) => total + file.bytes, 0);
  await page.route("**/library/collection/**", async (route: Route) => {
    const url = new URL(route.request().url());
    const chemin = url.pathname.replace(/^\/library/, "");
    if (route.request().method() === "POST") {
      const corps = route.request().postDataJSON() as Record<string, unknown>;
      gestes.push({ chemin, corps });
      const source = etageres.find((item) => item.id === corps.id);
      if (!source) return route.fulfill({ status: 404, json: { error: "Collection introuvable." } });
      const noms = (corps.names as string[] | undefined) ?? [];
      if (chemin === "/collection/remove.json") {
        source.files = source.files.filter((file) => !noms.includes(file.name));
        return route.fulfill({ json: { removed: noms, failed: [] } });
      }
      if (chemin === "/collection/move.json") {
        const cible = etageres.find((item) => item.id === corps.to);
        if (!cible) return route.fulfill({ status: 404, json: { error: "Collection introuvable." } });
        cible.files.push(...source.files.filter((file) => noms.includes(file.name)));
        source.files = source.files.filter((file) => !noms.includes(file.name));
        return route.fulfill({ json: { moved: noms, failed: [] } });
      }
      if (chemin === "/collection/rename.json") {
        source.label = String(corps.label);
        return route.fulfill({ json: { destination: destination(source) } });
      }
      if (chemin === "/collection/delete.json") {
        etageres.splice(etageres.indexOf(source), 1);
        return route.fulfill({ json: { deleted: source.id } });
      }
      return route.fulfill({ status: 404, json: { error: "not_found" } });
    }
    if (chemin === "/collection/list.json") {
      return route.fulfill({
        json: { destinations: etageres.map((item) => ({ ...destination(item), count: item.files.length, bytes: poids(item) })) },
      });
    }
    if (chemin === "/collection/files.json") {
      const item = etageres.find((entry) => entry.id === url.searchParams.get("id"));
      if (!item) return route.fulfill({ status: 404, json: { error: "Collection introuvable." } });
      const mots = (url.searchParams.get("q") ?? "").toLowerCase().split(/\s+/).filter(Boolean);
      const gardes = item.files.filter((file) => mots.every((mot) => file.name.toLowerCase().includes(mot)));
      return route.fulfill({
        json: {
          destination: destination(item),
          files: gardes,
          total: item.files.length,
          matched: gardes.length,
          bytes: poids(item),
          partial: false,
        },
      });
    }
    return route.fallback();
  });
  return gestes;
}

async function ouvrirLaBanque(page: Page, role: "programmateur" | "admin") {
  await seConnecter(page, role);
  await expect(antenne(page)).toBeVisible();
  await page.goto("/sons?onglet=importer");
}

test("la banque montre ce qu'elle contient : chercher, pré-écouter, puis ajouter des titres", async ({ page }) => {
  await ouvrirLaBanque(page, "programmateur");
  await expect(page.getByRole("radio", { name: "Contenu" })).toHaveAttribute("aria-checked", "true");

  const rotation = page.getByRole("region", { name: "Rotation" });
  await expect(rotation.getByRole("heading", { name: "Rotation" })).toBeVisible();
  await expect(rotation.getByText(/^2 titres · /)).toBeVisible();
  await expect(rotation.getByRole("button", { name: "Pré-écouter Grande distance" })).toBeVisible();
  await expect(rotation.getByRole("button", { name: "Pré-écouter Bande large" })).toBeVisible();

  await rotation.getByRole("textbox", { name: "Rechercher un titre" }).fill("porteuses");
  await expect(rotation.getByRole("button", { name: "Pré-écouter Grande distance" })).toHaveCount(0);
  await expect(rotation.getByText("1 sur 2 titres")).toBeVisible();

  const fichier = page.waitForResponse((reponse) => new URL(reponse.url()).pathname === "/library/collection/file", {
    timeout: 5_000,
  });
  await rotation.getByRole("button", { name: "Pré-écouter Bande large" }).click();
  expect((await fichier).ok(), "fichier de la pré-écoute").toBe(true);
  await rotation.getByRole("button", { name: "Arrêter la pré-écoute" }).click();
  await expect(rotation.getByRole("button", { name: "Pré-écouter Bande large" })).toBeVisible();

  // Le programmateur n'a pas les gestes d'une collection : ils sont à l'admin.
  await expect(page.getByRole("complementary", { name: "Collections" }).getByRole("button", { name: "Nouvelle" })).toHaveCount(0);

  await rotation.getByRole("button", { name: "Ajouter des titres" }).click();
  await expect(page.getByRole("heading", { name: "Ajouter à la banque" })).toBeVisible();
  await expect(page.getByRole("radio", { name: "Ajouter" })).toHaveAttribute("aria-checked", "true");
  await expect(page).toHaveURL(/vue=ajouter/);
});

test("retirer puis déplacer des titres d'une collection, par la sélection et par le menu d'un titre", async ({ page }) => {
  const banque = [
    etagere("rotation", "Rotation", [fichier("Ada - Song.mp3")]),
    etagere("jazz", "Jazz d'été", [
      fichier("Bea - Live.mp3"),
      fichier("Cy - Tune.mp3"),
      fichier("Dee - Nuit.mp3"),
      fichier("notes.txt", 0),
    ]),
  ];
  const gestes = await fauxContenu(page, banque);
  await ouvrirLaBanque(page, "programmateur");

  await page.getByRole("option", { name: /Jazz d'été/ }).click();
  const jazz = page.getByRole("region", { name: "Jazz d'été" });
  await expect(jazz.getByText(/^4 titres · /)).toBeVisible();
  // Un fichier qui n'est pas un son se voit, pour être retiré.
  await expect(jazz.getByText("Pas un son")).toBeVisible();

  // Maj + clic prend la plage, un second clic rend un titre.
  await jazz.getByRole("checkbox", { name: "Sélectionner Live" }).click();
  await jazz.getByRole("checkbox", { name: "Sélectionner Nuit" }).click({ modifiers: ["Shift"] });
  const selection = jazz.getByRole("toolbar", { name: "Sélection" });
  await expect(selection.getByText("3 titres sélectionnés")).toBeVisible();
  await jazz.getByRole("checkbox", { name: "Sélectionner Tune" }).click();
  await expect(selection.getByText("2 titres sélectionnés")).toBeVisible();

  await selection.getByRole("button", { name: "Retirer" }).click();
  const confirmation = page.getByRole("dialog", { name: "Retirer 2 titres ?" });
  await expect(confirmation).toContainText("corbeille de la banque");
  await confirmation.getByRole("button", { name: "Retirer 2 titres" }).click();
  await expect(avis(page, "2 titres retirés")).toBeVisible();
  await expect(jazz.getByText(/^2 titres · /)).toBeVisible();
  await expect(page.getByRole("option", { name: /Jazz d'été/ })).toContainText("2 titres");

  await jazz.getByRole("button", { name: "Actions pour Tune" }).click();
  await page.getByRole("menuitem", { name: "Déplacer vers…" }).click();
  const deplacement = page.getByRole("dialog", { name: "Déplacer ce titre" });
  await deplacement.getByRole("button", { name: "Déplacer vers Rotation" }).click();
  await expect(avis(page, "1 titre déplacé vers Rotation")).toBeVisible();
  await expect(jazz.getByRole("button", { name: "Pré-écouter Tune" })).toHaveCount(0);
  await expect(page.getByRole("option", { name: /Rotation/ })).toContainText("2 titres");

  expect(gestes).toEqual([
    { chemin: "/collection/remove.json", corps: { id: "jazz", names: ["Bea - Live.mp3", "Dee - Nuit.mp3"] } },
    { chemin: "/collection/move.json", corps: { id: "jazz", to: "rotation", names: ["Cy - Tune.mp3"] } },
  ]);
});

test("« Ajouter des titres » d'une collection ouvre l'envoi vers elle", async ({ page }) => {
  await fauxContenu(page, [etagere("rotation", "Rotation", []), etagere("jazz", "Jazz d'été", [])]);
  // Le faux catalogue du banc ne connaît que la Rotation : le vrai donne aussi chaque collection.
  await page.route("**/library/inbox.json", (route) =>
    route.fulfill({
      json: {
        destinations: [
          { id: "rotation", label: "Rotation", group: "rotation", folder: "10-rotation" },
          { id: "jazz", label: "Jazz d'été", group: "archives", folder: "20-archives/jazz" },
        ],
        quota: { used: 0, limit: 100 * 1024 ** 3 },
        disk: null,
        queue: [],
        rejected: [],
        progress: [],
      },
    }),
  );
  await ouvrirLaBanque(page, "programmateur");

  await page.getByRole("option", { name: /Jazz d'été/ }).click();
  await page.getByRole("region", { name: "Jazz d'été" }).getByRole("button", { name: "Ajouter des titres" }).first().click();
  const envoi = page.getByRole("region", { name: "Envoi vers la banque" });
  await expect(envoi).toContainText("vers Jazz d'été");
});

test("un admin renomme une collection, puis la supprime une fois vide", async ({ page }) => {
  const banque = [
    etagere("rotation", "Rotation", [fichier("Ada - Song.mp3")]),
    etagere("jazz", "Jazz d'été", [fichier("Bea - Live.mp3")]),
    etagere("nuit", "Nuit", []),
  ];
  const gestes = await fauxContenu(page, banque);
  await ouvrirLaBanque(page, "admin");

  // Une collection qui a des titres ne se supprime pas.
  await page.getByRole("option", { name: /Jazz d'été/ }).click();
  await page.getByRole("button", { name: "Actions pour la collection Jazz d'été" }).click();
  await expect(page.getByRole("menuitem", { name: /Supprimer/ })).toHaveAttribute("aria-disabled", "true");
  await page.keyboard.press("Escape");

  await page.getByRole("option", { name: /^Nuit/ }).click();
  const nuit = page.getByRole("region", { name: "Nuit" });
  await expect(nuit.getByText("Cette collection est vide")).toBeVisible();
  await nuit.getByRole("button", { name: "Actions pour la collection Nuit" }).click();
  await page.getByRole("menuitem", { name: "Renommer…" }).click();
  const renommer = page.getByRole("dialog", { name: "Renommer la collection" });
  await renommer.getByLabel("Nom").fill("jazz d'ete");
  await expect(renommer.getByText("Une collection porte déjà ce nom.")).toBeVisible();
  await renommer.getByLabel("Nom").fill("Nuit blanche");
  await renommer.getByRole("button", { name: "Renommer" }).click();
  await expect(avis(page, "La collection s'appelle maintenant « Nuit blanche »")).toBeVisible();
  const blanche = page.getByRole("region", { name: "Nuit blanche" });
  await expect(blanche.getByRole("heading", { name: "Nuit blanche" })).toBeVisible();

  await blanche.getByRole("button", { name: "Actions pour la collection Nuit blanche" }).click();
  await page.getByRole("menuitem", { name: /Supprimer/ }).click();
  await page
    .getByRole("dialog", { name: "Supprimer la collection « Nuit blanche » ?" })
    .getByRole("button", { name: "Supprimer la collection" })
    .click();
  await expect(avis(page, "Collection « Nuit blanche » supprimée")).toBeVisible();
  await expect(page.getByRole("option", { name: /Nuit blanche/ })).toHaveCount(0);
  await expect(page.getByRole("option", { name: /Rotation/ })).toHaveAttribute("aria-selected", "true");

  expect(gestes).toEqual([
    { chemin: "/collection/rename.json", corps: { id: "nuit", label: "Nuit blanche" } },
    { chemin: "/collection/delete.json", corps: { id: "nuit" } },
  ]);
});

test("un refus du catalogue se dit, et la liste reste celle du disque", async ({ page }) => {
  const banque = [etagere("rotation", "Rotation", [fichier("Ada - Song.mp3"), fichier("Bea - Live.mp3")])];
  await fauxContenu(page, banque);
  // Le catalogue répond, mais le moteur, qui juge la session, non.
  await page.route("**/library/collection/remove.json", (route) =>
    route.fulfill({ status: 502, json: { error: "automate injoignable" } }),
  );
  await ouvrirLaBanque(page, "programmateur");

  const rotation = page.getByRole("region", { name: "Rotation" });
  await rotation.getByRole("button", { name: "Actions pour Song" }).click();
  await page.getByRole("menuitem", { name: "Retirer…" }).click();
  await page.getByRole("dialog", { name: "Retirer ce titre ?" }).getByRole("button", { name: "Retirer le titre" }).click();
  await expect(alerte(page, "Le moteur ne répond pas au catalogue. Réessaie dans un instant.")).toBeVisible();
  await expect(rotation.getByRole("button", { name: "Pré-écouter Song" })).toBeVisible();
});

test("face à un catalogue plus ancien, la vue le dit, et l'envoi reste ouvert", async ({ page }) => {
  await page.route("**/library/collection/**", (route) => route.fulfill({ status: 404, json: { error: "not_found" } }));
  await ouvrirLaBanque(page, "programmateur");

  await expect(page.getByText("Mets à jour la station")).toBeVisible();
  await page.getByRole("radio", { name: "Ajouter" }).click();
  await expect(page.getByRole("heading", { name: "Ajouter à la banque" })).toBeVisible();
});
