import type { Page } from "@playwright/test";
import { DEFAULT_SOURCE_URL, type Brand } from "../src/lib/brand.ts";
import { monitorSources, sourceById } from "../src/lib/monitorSource.ts";
import { antenne, expect, seConnecter, tenirLAntenne, test } from "./banc.ts";

// La barre du haut, la même sur toutes les pages : ce qui passe, l'état de
// l'antenne, le casque et le compte.

const barre = (page: Page) => page.getByRole("banner");
const casque = (page: Page) => barre(page).getByRole("button", { name: /^(Écouter au casque|Arrêter l’écoute)/ });
const echapper = (texte: string) => texte.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

/** Le flux public, tel que la console le lit dans brand.json. */
async function adresseDuFlux(page: Page): Promise<URL> {
  const marque = (await (await page.request.get("/brand.json")).json()) as Brand;
  return new URL(sourceById(monitorSources(marque), "public").stream);
}

const versLeFlux = (flux: URL) => (url: URL) => url.origin === flux.origin && url.pathname === flux.pathname;

/** L'heure de chaque demande du flux, à partir de maintenant. */
function demandesDuFlux(page: Page, flux: URL): number[] {
  const heures: number[] = [];
  page.on("request", (demande) => {
    if (versLeFlux(flux)(new URL(demande.url()))) heures.push(Date.now());
  });
  return heures;
}

/** Les demandes du flux dans les 5 s qui suivent la première, comptées une fois ces 5 s passées. */
async function enCinqSecondes(page: Page, heures: number[]): Promise<number> {
  // Sans demande vue, l'adresse du flux a changé : compter ne prouverait rien.
  expect(heures.length, "demandes du flux vues par le parcours").toBeGreaterThan(0);
  const premiere = heures[0];
  await page.waitForTimeout(Math.max(0, premiere + 5_000 - Date.now()));
  return heures.filter((heure) => heure - premiere < 5_000).length;
}

/** Des trames MP3 muettes, 128 kbit/s à 44,1 kHz : 38 trames font une seconde. */
function trames(nombre: number): Buffer {
  const trame = Buffer.alloc(417);
  trame.set([0xff, 0xfb, 0x90, 0x44]);
  return Buffer.concat(Array.from({ length: nombre }, () => trame));
}

test("la barre dit ce qui passe, et l’état de l’antenne s’ouvre en détail", async ({ page }) => {
  await seConnecter(page, "animateur");
  await tenirLAntenne(page);

  // Le titre à l'antenne est le même que sur le pupitre.
  const titre = (await antenne(page).getByRole("paragraph").first().textContent()) ?? "";
  const enCours = barre(page).getByRole("link", { name: /^À l’antenne : / });
  await expect(enCours).toHaveAccessibleName(new RegExp(`^À l’antenne : ${echapper(titre)}[,.]`));

  const etat = barre(page).getByRole("button", { name: /^Antenne : / });
  await expect(etat).toHaveAccessibleName(/^Antenne : En onde, .+\. Santé : tout va bien\.$/);
  await etat.click();
  const detail = page.getByRole("dialog");
  await expect(detail.getByText("État de l’antenne")).toBeVisible();
  const sante = detail.getByRole("list", { name: "Santé antenne" }).getByRole("listitem");
  await expect(sante).toHaveCount(6);
  await expect(sante.filter({ hasText: "Moteur" })).toContainText("OK");
  // Le diagnostic de l'automate est réservé à l'admin.
  await expect(detail.getByRole("link", { name: "Diagnostic automate" })).toHaveCount(0);
  await page.keyboard.press("Escape");
  await expect(detail).toBeHidden();
  await expect(etat).toBeFocused();

  // D'une autre page, le titre ramène au pupitre.
  await page.getByRole("navigation", { name: "Console" }).getByRole("link", { name: "Conducteur" }).click();
  await expect(page).toHaveURL(/\/conducteur$/);
  await enCours.click();
  await expect(page).toHaveURL(/\/antenne$/);
  await expect(antenne(page)).toBeVisible();
});

test("écouter l’antenne au casque, puis arrêter", async ({ page }) => {
  await seConnecter(page, "animateur");
  await expect(casque(page)).toHaveAccessibleName("Écouter au casque : Antenne publique");
  await expect(casque(page)).toHaveAttribute("aria-pressed", "false");

  await casque(page).click();
  await expect(casque(page)).toHaveAttribute("aria-pressed", "true");
  await expect(casque(page)).toHaveAccessibleName(/^Arrêter l’écoute\./);

  await casque(page).click();
  await expect(casque(page)).toHaveAttribute("aria-pressed", "false");
  await expect(casque(page)).toHaveAccessibleName("Écouter au casque : Antenne publique");
});

test("un flux muet au casque : la console le dit, sans marteler", async ({ page }) => {
  // Le banc coupe le flux : le casque n'entend rien, et le bouton le dit.
  const demandes = demandesDuFlux(page, await adresseDuFlux(page));
  await seConnecter(page, "animateur");
  await casque(page).click();
  await expect(casque(page)).toHaveAccessibleName("Arrêter l’écoute. Le flux ne répond pas : le casque réessaie seul", {
    timeout: 10_000,
  });
  // Chaque essai demande le flux jusqu'à trois fois : en PCM, en MSE, puis par
  // l'élément audio. Le backoff en laisse sept en 5 s au plus ; un essai toutes
  // les 200 ms en ferait plus de vingt.
  expect(await enCinqSecondes(page, demandes)).toBeLessThanOrEqual(24);
});

test("un flux qui s’arrête : le casque réessaie seul, sans marteler, et le dit", async ({ page }) => {
  // Comme Icecast quand on recrée le playout : il coupe les auditeurs du mount.
  // Ici, chaque connexion au flux rend une seconde de silence, puis se ferme.
  const flux = await adresseDuFlux(page);
  const connexions = demandesDuFlux(page, flux);
  await page.route(versLeFlux(flux), (route) =>
    route.fulfill({
      contentType: "audio/mpeg",
      headers: { "Access-Control-Allow-Origin": "*" },
      body: trames(38),
    }),
  );

  await seConnecter(page, "animateur");
  await casque(page).click();
  // Aucune reprise ne tient : le bouton le dit…
  await expect(casque(page)).toHaveAccessibleName("Arrêter l’écoute. Le flux ne répond pas : le casque réessaie seul", {
    timeout: 10_000,
  });
  // … et le casque se reconnecte seul, pendant l'écoute.
  const avant = connexions.length;
  await expect.poll(() => connexions.length, { timeout: 10_000 }).toBeGreaterThanOrEqual(avant + 2);
  // Sans marteler : chaque reprise ratée allonge l'attente, jusqu'à 3 s. En
  // 5 s, une poignée de connexions, pas vingt-cinq.
  expect(await enCinqSecondes(page, connexions)).toBeLessThanOrEqual(8);
});

test("l’admin choisit la source de son casque, et la retrouve", async ({ page }) => {
  await seConnecter(page, "admin");
  const source = barre(page).getByRole("button", { name: /^Source du casque/ });
  await expect(source).toHaveAccessibleName("Source du casque : Antenne publique. Changer.");

  await source.click();
  await page.getByRole("menuitemradio", { name: /^Conducteur \(fichiers\)/ }).click();
  await expect(source).toHaveAccessibleName("Source du casque : Conducteur (fichiers). Changer.");
  await expect(casque(page)).toHaveAccessibleName("Écouter au casque : Conducteur (fichiers)");

  await page.reload();
  await expect(source).toHaveAccessibleName("Source du casque : Conducteur (fichiers). Changer.");
});

test("le menu du compte : qui est connecté, « Mon compte », puis la déconnexion", async ({ page }) => {
  await seConnecter(page, "programmateur");
  await barre(page).getByRole("button", { name: "Compte programmateur : menu" }).click();
  const menu = page.getByRole("menu", { name: "Compte programmateur : menu" });
  await expect(menu.getByText("programmateur", { exact: true })).toBeVisible();
  await expect(menu.getByText("Programmateur", { exact: true })).toBeVisible();

  await menu.getByRole("menuitem", { name: "Mon compte" }).click();
  await expect(page).toHaveURL(/\/reglages\?onglet=compte$/);
  await expect(page.getByRole("tabpanel", { name: "Mon compte" })).toBeVisible();

  await barre(page).getByRole("button", { name: "Compte programmateur : menu" }).click();
  await page.getByRole("menuitem", { name: "Se déconnecter" }).click();
  await expect(page.getByRole("button", { name: "Se connecter" })).toBeVisible();
  // La session est close chez le moteur aussi : recharger ne la rend pas.
  await page.reload();
  await expect(page.getByRole("button", { name: "Se connecter" })).toBeVisible();
});

test("le lien « Code source » ouvre les sources dans un nouvel onglet", async ({ page, context }) => {
  await seConnecter(page, "animateur");
  await barre(page).getByRole("button", { name: "Compte animateur : menu" }).click();
  const lien = page.getByRole("menuitem", { name: "Code source AGPL" });
  // L'adresse vient de la marque, sinon du dépôt de BUTTON.
  const marque = (await (await page.request.get("/brand.json")).json()) as { suite?: { sourceUrl?: string } };
  const adresse = marque.suite?.sourceUrl || DEFAULT_SOURCE_URL;
  await expect(lien).toHaveAttribute("href", adresse);

  const onglet = context.waitForEvent("page", { timeout: 5_000 });
  await lien.click();
  const sources = await onglet;
  await expect(sources).toHaveURL(adresse);
  // La console reste ouverte à côté.
  await expect(antenne(page)).toBeVisible();
  await sources.close();
});
