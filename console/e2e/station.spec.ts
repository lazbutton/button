import type { Page } from "@playwright/test";
import type { Brand } from "../src/lib/brand.ts";
import { alerte, avis, expect, seConnecter, test } from "./banc.ts";

// Réglages → Station, l'onglet de l'admin : un nom enregistré passe dans la
// console sans recharger, et tient après un rechargement. Face à un moteur
// plus ancien, sans ces routes, la console garde brand.json. Une valeur
// refusée se dit sous son champ.

/** Un nom qui ne vient ni de brand.json ni d'une station. */
const NOM = "Radio du banc";

/** Ce que Quart répond à une route qu'il ne connaît pas : la description par défaut de werkzeug. */
const ROUTE_ABSENTE = {
  error:
    "The requested URL was not found on the server. If you entered the URL manually please check your spelling and try again.",
};

const echapper = (texte: string) => texte.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

/** Le titre de l'onglet du navigateur commence par le nom de la station. */
const titre = (nom: string) => new RegExp(`^${echapper(nom)} — `);

/** Le nom de la station en tête de la barre de navigation : un lien vers l'antenne. */
const nomDansLaBarre = (page: Page, nom: string) =>
  page.getByRole("complementary", { name: "Navigation automate" }).getByRole("link", { name: nom, exact: true });

/** Le nom que la console garde sans réglage du moteur : celui de brand.json. */
async function nomDeLImage(page: Page): Promise<string> {
  const marque = (await (await page.request.get("/brand.json")).json()) as Brand;
  return marque.suite.name;
}

/** Entre avec le compte admin, puis ouvre Réglages → Station. */
async function ouvrirLaStation(page: Page): Promise<void> {
  await seConnecter(page, "admin");
  await page.getByRole("navigation", { name: "Console" }).getByRole("link", { name: "Réglages" }).click();
  await page.getByRole("tab", { name: "Station" }).click();
}

test("un nom enregistré : le titre de l’onglet et la barre le prennent sans recharger, et le gardent", async ({
  page,
}) => {
  await ouvrirLaStation(page);
  const marque = await nomDeLImage(page);
  const nom = page.getByRole("textbox", { name: "Nom", exact: true });
  const enregistrer = page.getByRole("button", { name: "Enregistrer" });
  const enregistre = avis(page, "Réglages enregistrés.");
  // Le moteur de démo part sans nom réglé : la console a celui de brand.json.
  await expect(nom).toHaveValue("");
  await expect(page).toHaveTitle(titre(marque));
  await expect(nomDansLaBarre(page, marque)).toBeVisible();

  await nom.fill(NOM);
  await enregistrer.click();
  await expect(page).toHaveTitle(titre(NOM));
  await expect(nomDansLaBarre(page, NOM)).toBeVisible();
  // Le message de l'onglet est encore là : la page ne s'est pas rechargée.
  await expect(enregistre).toBeVisible();

  // Le nom est gardé par le moteur : il tient après un rechargement.
  await page.reload();
  await expect(nom).toHaveValue(NOM);
  await expect(page).toHaveTitle(titre(NOM));
  await expect(nomDansLaBarre(page, NOM)).toBeVisible();

  // Les parcours suivants partagent le moteur de démo : le champ vide efface
  // le nom, et la console reprend celui de brand.json.
  await nom.fill("");
  await enregistrer.click();
  await expect(enregistre).toBeVisible();
  await expect(page).toHaveTitle(titre(marque));
  await expect(nomDansLaBarre(page, marque)).toBeVisible();
});

test("moteur sans ces routes : la console garde brand.json, et l’onglet dit de mettre à jour le moteur", async ({
  page,
}) => {
  // Un moteur plus ancien que la console ne connaît ni /public/station.json,
  // lu avant la connexion, ni /station.json, lu par l'onglet.
  const absentes = new Set<string>();
  await page.route("**/station.json", (route) => {
    absentes.add(new URL(route.request().url()).pathname);
    return route.fulfill({ status: 404, json: ROUTE_ABSENTE });
  });
  await ouvrirLaStation(page);

  await expect(avis(page, "Mets à jour le moteur pour régler la station ici.")).toBeVisible();
  expect([...absentes].sort()).toEqual(["/public/station.json", "/station.json"]);
  const marque = await nomDeLImage(page);
  await expect(page).toHaveTitle(titre(marque));
  await expect(nomDansLaBarre(page, marque)).toBeVisible();
  // L'onglet n'a rien à enregistrer, et le 404 ne s'affiche pas en anglais.
  await expect(page.getByRole("button", { name: "Enregistrer" })).toHaveCount(0);
  await expect(page.getByText(/requested URL/)).toHaveCount(0);
});

test("une valeur refusée : l’erreur s’affiche sous le champ, qui prend le focus", async ({ page }) => {
  await ouvrirLaStation(page);
  const port = page.getByRole("textbox", { name: /^Port/ });
  await port.fill("99999");
  await page.getByRole("button", { name: "Enregistrer" }).click();

  // Le moteur refuse le port, et nomme le champ.
  const erreur = page.getByText("Un port entre 1 et 65535.", { exact: true });
  await expect(erreur).toBeVisible();
  await expect(port).toBeFocused();
  await expect(port).toHaveAttribute("aria-invalid", "true");
  // Dans le libellé du champ : un lecteur d'écran la lit avec lui.
  await expect(port).toHaveAccessibleName(/Un port entre 1 et 65535\./);
  // Sous le champ, et pas en alerte au bas du formulaire.
  const champ = await port.boundingBox();
  const message = await erreur.boundingBox();
  if (!champ || !message) throw new Error("Le champ ou son erreur n’est pas affiché.");
  expect(message.y, "haut du message, sous le bas du champ").toBeGreaterThanOrEqual(champ.y + champ.height);
  await expect(alerte(page, "Un port entre 1 et 65535.")).toHaveCount(0);
});
