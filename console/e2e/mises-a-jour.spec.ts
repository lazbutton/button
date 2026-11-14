import type { Page, Route } from "@playwright/test";
import type { UpdatesState } from "../src/api/updates.ts";
import { avis, expect, seConnecter, test } from "./banc.ts";

// Réglages → Mises à jour (MAJ-07), pour un admin : « Mettre à jour maintenant »
// écrit une demande dans le moteur, que la machine prend dans la minute. Ici, le
// moteur et la machine sont joués par les réponses de /system/updates.json : la
// page suit la demande jusqu'à son résultat, survit au redémarrage du moteur, et
// dit pourquoi le bouton ne demande pas, quand il ne le peut pas.

const HOST = {
  seen_at: "2026-11-12T14:02+01:00",
  requests: true,
  command: "0.1.0",
  hold: null,
  nightly: "auto" as const,
  time: "04:00",
  zone: "Europe/Paris",
};

function etat(over: Partial<UpdatesState> = {}): UpdatesState {
  return {
    installed: "0.1.0",
    recorded_at: "2026-11-12T04:01+01:00",
    services: [{ service: "radiotomate-playout", image: "ghcr.io/lazbutton/button-playout:0.1.0", version: "0.1.0" }],
    latest: "0.2.0",
    check: { at: "2026-11-12T14:03+01:00", error: null, pending: false },
    releases: [
      {
        version: "0.2.0",
        published_at: "2026-11-10T19:40+01:00",
        url: "https://github.com/lazbutton/button/releases/tag/v0.2.0",
        notes: "**Mise en service.** Rien d'autre que la mise à jour habituelle.\n\n- Un correctif, avec `du code`.",
        major: false,
        action: null,
      },
    ],
    major: null,
    host: HOST,
    history: [
      {
        started_at: "2026-11-12T04:01+01:00",
        from: "0.0.9",
        to: "0.1.0",
        result: "done",
        label: "faite",
        detail: "redémarrée et contrôlée en 21 s",
      },
    ],
    request: null,
    last: null,
    blocked: null,
    ...over,
  };
}

const DEMANDE = {
  id: "abcdef012345",
  state: "pending" as const,
  requested_at: "2026-11-12T14:05+01:00",
  requested_by: "admin",
  from: "0.1.0",
  target: "0.2.0",
  waiting: null,
  started_at: null,
  seen_at: null,
  unseen: false,
};

/** Le moteur joué : chaque lecture de la page reçoit ce que rend `reponse`. */
async function jouerLeMoteur(page: Page, reponse: () => UpdatesState | number) {
  await page.route("**/system/updates.json*", async (route: Route) => {
    const donnee = reponse();
    if (typeof donnee === "number") {
      await route.fulfill({ status: donnee, contentType: "text/html", body: "<html>Bad Gateway</html>" });
    } else {
      await route.fulfill({ json: donnee });
    }
  });
}

async function ouvrirLesMisesAJour(page: Page): Promise<void> {
  await seConnecter(page, "admin");
  await page.getByRole("navigation", { name: "Console" }).getByRole("link", { name: "Réglages" }).click();
  await page.getByRole("tab", { name: "Mises à jour" }).click();
  await expect(page.getByRole("heading", { name: "Mises à jour", level: 2 })).toBeVisible();
}

test("un admin met la station à jour d’un bouton, et la page suit la demande jusqu’à son résultat", async ({ page }) => {
  // Le 12 novembre à 15:00, à Paris : les heures des réponses se disent « aujourd’hui ».
  await page.clock.setFixedTime(new Date("2026-11-12T15:00:00+01:00"));
  let courant: UpdatesState | number = etat();
  await jouerLeMoteur(page, () => courant);
  let demande: unknown = null;
  await page.route("**/system/updates/request.json", async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    demande = route.request().postDataJSON();
    courant = etat({ request: DEMANDE, blocked: { code: "open", message: "Une mise à jour est déjà demandée." } });
    await route.fulfill({ status: 202, json: courant });
  });
  await ouvrirLesMisesAJour(page);

  await expect(page.getByRole("heading", { name: "La 0.2.0 est publiée" })).toBeVisible();
  await expect(page.getByText("0.0.9 → 0.1.0 : faite")).toBeVisible();
  await expect(page.getByText("Aujourd’hui à 04:01. Redémarrée et contrôlée en 21 s.")).toBeVisible();
  // Les notes de la version, sans HTML : d'abord ce qu'elle demande, puis le
  // détail des changements, à déplier.
  await expect(page.getByRole("heading", { name: "0.2.0 mineure publiée le 10/11 à 19:40", level: 4 })).toBeVisible();
  await expect(page.getByText("Rien d'autre que la mise à jour habituelle.")).toBeVisible();
  await expect(page.getByText("Un correctif, avec")).toBeHidden();
  await page.getByText("Le détail de la 0.2.0 : 1 changement").click();
  await expect(page.getByText("Un correctif, avec")).toBeVisible();
  // Les mises à jour de la nuit ne tournent pas encore : la machine le dit, avec ce qu'elle a réglé.
  await expect(page.locator(".reglages-fact", { hasText: "Mises à jour la nuit" })).toContainText("pas encore");
  await expect(page.locator("code", { hasText: "sudo station config --updates manual" })).toBeVisible();
  await page.getByRole("button", { name: "Mettre à jour maintenant" }).click();
  const confirmation = page.getByRole("dialog", { name: "Mettre la station à jour, en 0.2.0 ?" });
  await expect(confirmation).toContainText("La station passe de 0.1.0 à 0.2.0.");
  await confirmation.getByRole("button", { name: "Mettre à jour" }).click();
  await expect(avis(page, "Mise à jour demandée : la machine la prend dans la minute.")).toBeVisible();
  expect(demande).toEqual({});
  await expect(page.getByRole("heading", { name: "Demandée, vers la 0.2.0" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Mettre à jour maintenant" })).toHaveCount(0);

  // La machine la lance : la page se relit seule, toutes les 5 s.
  courant = etat({ request: { ...DEMANDE, state: "running", started_at: "2026-11-12T14:06+01:00" } });
  await expect(page.getByRole("heading", { name: "En cours depuis 14:06, vers la 0.2.0" })).toBeVisible({ timeout: 12_000 });
  await expect(page.getByRole("button", { name: "Retirer la demande" })).toHaveCount(0);

  // Le moteur redémarre : la page le dit, au lieu d'une erreur.
  courant = 502;
  await expect(page.getByRole("heading", { name: "La station redémarre" })).toBeVisible({ timeout: 25_000 });

  // De retour, en 0.2.0 : le résultat, et de quoi prendre la console nouvelle.
  courant = etat({
    installed: "0.2.0",
    latest: "0.2.0",
    releases: [],
    blocked: { code: "up_to_date", message: "La station est à jour : 0.2.0, la plus haute version publiée." },
    last: {
      id: DEMANDE.id,
      result: "done",
      detail: "redémarrée et contrôlée en 18 s",
      requested_at: DEMANDE.requested_at,
      requested_by: "admin",
      finished_at: "2026-11-12T14:09+01:00",
      from: "0.1.0",
      to: "0.2.0",
    },
  });
  await expect(page.getByRole("heading", { name: "Faite : de 0.1.0 à 0.2.0" })).toBeVisible({ timeout: 25_000 });
  await expect(page.getByText("Aujourd’hui à 14:09. Redémarrée et contrôlée en 18 s.")).toBeVisible();
  await expect(page.getByRole("heading", { name: "À jour", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Recharger la page" })).toBeVisible();
});

test("une demande qui attend dit pourquoi, et se retire", async ({ page }) => {
  let courant: UpdatesState = etat({
    request: { ...DEMANDE, waiting: "QG, un direct, en cours jusqu'à 22:00" },
    blocked: { code: "open", message: "Une mise à jour est déjà demandée." },
  });
  await jouerLeMoteur(page, () => courant);
  await page.route("**/system/updates/request.json", async (route) => {
    if (route.request().method() !== "DELETE") return route.fallback();
    courant = etat({
      last: {
        id: DEMANDE.id,
        result: "withdrawn",
        detail: "Retirée par admin.",
        requested_at: DEMANDE.requested_at,
        requested_by: "admin",
        finished_at: "2026-11-12T14:07+01:00",
        from: "0.1.0",
        to: "0.2.0",
      },
    });
    await route.fulfill({ json: courant });
  });
  await ouvrirLesMisesAJour(page);
  await expect(page.getByRole("heading", { name: "En attente" })).toBeVisible();
  await expect(page.getByText(/^QG, un direct, en cours jusqu'à 22:00\. La machine réessaie chaque minute/)).toBeVisible();
  await page.getByRole("button", { name: "Retirer la demande" }).click();
  await expect(avis(page, "Demande retirée.")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Retirée" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Mettre à jour maintenant" })).toBeVisible();
});

test("HOLD, une majeure, des demandes coupées : pas de bouton, mais pourquoi et quoi faire", async ({ page }) => {
  let courant = etat({
    host: { ...HOST, hold: "Bloquées par station hold, le 12/11/2026 à 10:00.\nRaison : la grille de Noël" },
    blocked: {
      code: "hold",
      message:
        "Les mises à jour sont bloquées sur la machine (HOLD). Pour les débloquer, une fois la cause réglée : sudo station unhold.",
    },
  });
  await jouerLeMoteur(page, () => courant);
  await ouvrirLesMisesAJour(page);
  await expect(page.getByText("Les mises à jour sont bloquées sur la machine (HOLD).", { exact: false })).toBeVisible();
  await expect(page.getByText("Raison : la grille de Noël", { exact: false })).toBeVisible();
  await expect(page.getByRole("button", { name: "Mettre à jour maintenant" })).toHaveCount(0);

  courant = etat({
    latest: "1.0.0",
    major: { version: "1.0.0", action: "Poser `ICECAST_MOUNT` dans `.env`.", url: "https://github.com/lazbutton/button/releases/tag/v1.0.0" },
    blocked: {
      code: "major",
      message:
        "La mise à jour passe la 1.0.0, une version majeure : elle demande une action à la station avant de la prendre, et ne part pas d'ici. Une fois l'action faite, sur la machine : sudo station update --major.",
    },
  });
  await page.getByRole("button", { name: "Vérifier les versions" }).click();
  await expect(page.getByRole("heading", { name: "La 1.0.0 : une version majeure" })).toBeVisible();
  await expect(page.getByText("sudo station update --major", { exact: false }).first()).toBeVisible();
  await expect(page.getByRole("button", { name: "Mettre à jour maintenant" })).toHaveCount(0);

  courant = etat({
    host: { ...HOST, requests: false },
    blocked: {
      code: "requests_off",
      message:
        "Les demandes de la console sont coupées sur la machine. Pour les rallumer : sudo station config --console-requests yes.",
    },
  });
  await page.getByRole("button", { name: "Vérifier les versions" }).click();
  // La commande à taper sur la machine se lit en police de code.
  await expect(page.locator("code", { hasText: "sudo station config --console-requests yes" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Mettre à jour maintenant" })).toHaveCount(0);
});

test("un moteur d’avant la page : « Mets à jour le moteur », pas une page blanche", async ({ page }) => {
  await page.route("**/system/updates.json*", (route) =>
    route.fulfill({
      status: 404,
      json: {
        error:
          "The requested URL was not found on the server. If you entered the URL manually please check your spelling and try again.",
      },
    }),
  );
  await ouvrirLesMisesAJour(page);
  await expect(page.getByText(/^Mets à jour le moteur pour avoir cette page/)).toBeVisible();
});

test("une erreur du moteur se dit comme telle, pas comme un moteur qui ne répond pas", async ({ page }) => {
  await page.route("**/system/updates.json*", (route) => route.fulfill({ status: 500, json: { error: "server_error" } }));
  await ouvrirLesMisesAJour(page);
  await expect(page.getByRole("alert").filter({ hasText: "Le moteur n’a pas pu lire les mises à jour (erreur 500)" })).toBeVisible();
  await expect(page.getByText("server_error")).toHaveCount(0);
  await expect(page.getByText("Le moteur ne répond pas")).toHaveCount(0);
});

