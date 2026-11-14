import type { Page, Route } from "@playwright/test";
import { antenne, avis, expect, seConnecter, test } from "./banc.ts";

// Le journal des gestes (FON-71). Le moteur du banc garde le rangement de la
// banque éteint, et n'a pas de bibliothèque : le parcours allume l'interrupteur
// dans /account.json, et tient ici un journal que lisent et changent les routes
// de la page, comme le moteur (engine/radiotomate/services/journal.py).

type Lot = {
  id: number;
  gesture: string;
  gesture_label: string;
  username: string;
  created: string;
  titles: number;
  fields: string[];
  undo_of: number | null;
  undone_by: { id: number; username: string; created: string } | null;
  undoable: boolean;
  why_not: string | null;
  counts: Record<string, number>;
};

const compte = (done: number, change: Record<string, number> = {}) => ({
  done,
  waiting: 0,
  kept: 0,
  cancelled: 0,
  failed: 0,
  pending: 0,
  ...change,
});

function journal(): Lot[] {
  return [
    {
      id: 3,
      gesture: "edit",
      gesture_label: "Correction",
      username: "anne",
      created: "2026-11-14T14:02+01:00",
      titles: 30,
      fields: ["album"],
      undo_of: null,
      undone_by: null,
      undoable: true,
      why_not: null,
      counts: compte(28, { waiting: 2 }),
    },
    {
      id: 2,
      gesture: "edit",
      gesture_label: "Correction",
      username: "bruno",
      created: "2026-11-13T09:30+01:00",
      titles: 1,
      fields: ["famille", "year"],
      undo_of: null,
      undone_by: null,
      undoable: true,
      why_not: null,
      counts: compte(1),
    },
    {
      id: 1,
      gesture: "edit",
      gesture_label: "Correction",
      username: "anne",
      created: "2026-10-01T10:00+02:00",
      titles: 4,
      fields: ["genre"],
      undo_of: null,
      undone_by: null,
      undoable: false,
      why_not: "Ce lot a plus de 30 jours : il ne s'annule plus.",
      counts: compte(4),
    },
  ];
}

async function banc(page: Page, ouvert = true): Promise<{ lots: Lot[]; annules: number[] }> {
  const lots = journal();
  const annules: number[] = [];
  await page.route("**/account.json", async (route: Route) => {
    if (route.request().method() !== "GET") return route.fallback();
    const reponse = await route.fetch();
    const corps = (await reponse.json()) as Record<string, unknown>;
    await route.fulfill({ response: reponse, json: { ...corps, features: { bank_tidy: ouvert, title_edits: ouvert } } });
  });
  await page.route("**/media/journal.json*", async (route: Route) => {
    const q = new URL(route.request().url()).searchParams;
    const gardes = lots.filter((lot) => !q.get("username") || lot.username === q.get("username"));
    const personnes = [...new Set(lots.map((lot) => lot.username))].sort();
    await route.fulfill({
      json: {
        entries: gardes,
        next: null,
        gestures: [{ value: "edit", label: "Correction", count: lots.filter((lot) => lot.gesture === "edit").length }],
        people: personnes.map((value) => ({ value, count: lots.filter((lot) => lot.username === value).length })),
        undo_days: 30,
      },
    });
  });
  await page.route("**/media/journal/*.json", async (route: Route) => {
    const id = Number(route.request().url().match(/journal\/(\d+)\.json/)?.[1]);
    const lot = lots.find((item) => item.id === id);
    await route.fulfill({
      json: {
        ...lot,
        changes: [
          { id: 7, label: "Orage – Comète", path: "10-rotation/7.mp3", field: "album", old: "Ciel", new: "Nuages", status: "done", reason: null },
          { id: 8, label: "Orage – Brume", path: "10-rotation/8.mp3", field: "album", old: "", new: "Nuages", status: "waiting", reason: "Il est à l'antenne." },
        ],
      },
    });
  });
  await page.route("**/media/journal/*/undo.json", async (route: Route) => {
    const id = Number(route.request().url().match(/journal\/(\d+)\/undo/)?.[1]);
    annules.push(id);
    const lot = lots.find((item) => item.id === id);
    if (lot) {
      lot.undoable = false;
      lot.why_not = "Ce lot a déjà été défait.";
      lot.undone_by = { id: 9, username: "programmateur", created: "2026-11-14T15:00+01:00" };
    }
    await route.fulfill({
      json: { dry_run: false, entry: 9, written: 27, waiting: [], kept: [{ id: 7, label: "Orage – Comète", code: "changed", reason: "Sa fiche a changé depuis : elle garde sa valeur." }], refused: [], unchanged: 0, selections: [] },
    });
  });
  return { lots, annules };
}

async function ouvrir(page: Page) {
  await seConnecter(page, "programmateur");
  await expect(antenne(page)).toBeVisible();
  await page.goto("/sons?onglet=journal");
  return page.getByRole("region", { name: "Journal des gestes" });
}

test("le journal dit qui a fait quoi, se filtre, et un lot s'annule d'un coup", async ({ page }) => {
  const { annules } = await banc(page);
  const page_ = await ouvrir(page);

  await expect(page.getByRole("tab", { name: "Journal" })).toHaveAttribute("aria-selected", "true");
  await expect(page_.getByText("Correction de 30 titres : album")).toBeVisible();
  await expect(page_.getByText("2 titres en attente de la fin d'un passage à l'antenne.")).toBeVisible();
  await expect(page_.getByText("Ce lot a plus de 30 jours : il ne s'annule plus.")).toBeVisible();
  await expect(page_.getByRole("button", { name: "Annuler" })).toHaveCount(2);

  // Par personne.
  await page_.getByRole("combobox", { name: "Personne" }).click();
  await page.getByRole("option", { name: "bruno (1)" }).click();
  await expect(page_.getByText("Correction de 1 titre : famille et année")).toBeVisible();
  await expect(page_.getByText("Correction de 30 titres : album")).toHaveCount(0);
  await page_.getByRole("combobox", { name: "Personne" }).click();
  await page.getByRole("option", { name: "Tout le monde" }).click();

  // Le détail d'un lot, ligne par ligne.
  const lot = page_.getByRole("button", { name: /Correction de 30 titres/ });
  await lot.click();
  await expect(lot).toHaveAttribute("aria-expanded", "true");
  const detail = page_.getByRole("table");
  await expect(detail.getByRole("row", { name: /Orage – Brume Album vide Nuages en attente/ })).toBeVisible();

  // Annuler le lot, après confirmation.
  await page_.locator("li").filter({ hasText: "Correction de 30 titres" }).getByRole("button", { name: "Annuler" }).click();
  const fenetre = page.getByRole("alertdialog").or(page.getByRole("dialog"));
  await expect(fenetre.getByText("Ce qui attend encore ne s'écrira pas.")).toBeVisible();
  await fenetre.getByRole("button", { name: "Annuler le lot" }).click();
  await expect(avis(page, "27 fiches ont repris leurs valeurs d'avant. Un titre a gardé la sienne")).toBeVisible();
  expect(annules).toEqual([3]);
  await expect(page_.getByText(/Défait par programmateur/)).toBeVisible();
});

test("le rangement fermé, Sons n'a pas d'onglet Journal", async ({ page }) => {
  await banc(page, false);
  await seConnecter(page, "programmateur");
  await expect(antenne(page)).toBeVisible();
  await page.goto("/sons?onglet=journal");
  await expect(page.getByRole("tab", { name: "Bacs" })).toHaveAttribute("aria-selected", "true");
  await expect(page.getByRole("tab", { name: "Journal" })).toHaveCount(0);
});
