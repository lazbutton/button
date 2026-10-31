import type { Locator, Page } from "@playwright/test";
import { antenne, expect, seConnecter, test } from "./banc.ts";

// Le thème clair et le sombre : se choisir dans le menu du compte, tenir après
// un rechargement, ou suivre l'appareil (« Machine », le choix par défaut).

/** La luminance relative d'une couleur rgb() ou rgba(), au sens des WCAG : de 0, noir, à 1, blanc. */
function luminance(couleur: string): number {
  const [r, g, b] = (couleur.match(/[\d.]+/g) ?? []).slice(0, 3).map((valeur) => {
    const canal = Number(valeur) / 255;
    return canal <= 0.04045 ? canal / 12.92 : ((canal + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contraste(a: string, b: string): number {
  const [clair, sombre] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (clair + 0.05) / (sombre + 0.05);
}

/** Le fond et le texte de la barre du haut et de la carte « À l'antenne ». */
async function teintes(page: Page) {
  const lire = (region: Locator) =>
    region.evaluate((element) => {
      // Le fond qu'on voit : celui de l'élément, ou du premier parent qui n'est pas transparent.
      let fond = "rgba(0, 0, 0, 0)";
      for (let noeud: Element | null = element; noeud && fond === "rgba(0, 0, 0, 0)"; noeud = noeud.parentElement) {
        fond = getComputedStyle(noeud).backgroundColor;
      }
      return { fond, texte: getComputedStyle(element).color };
    });
  return { barre: await lire(page.getByRole("banner")), carte: await lire(antenne(page)) };
}

async function attendreLeTheme(page: Page, theme: "clair" | "sombre") {
  await expect(async () => {
    const { barre, carte } = await teintes(page);
    for (const { fond, texte } of [barre, carte]) {
      if (theme === "sombre") expect(luminance(fond), `fond ${fond}`).toBeLessThan(0.05);
      else expect(luminance(fond), `fond ${fond}`).toBeGreaterThan(0.8);
      expect(contraste(fond, texte), `texte ${texte} sur ${fond}`).toBeGreaterThanOrEqual(4.5);
    }
  }).toPass({ timeout: 5_000 });
}

async function choisir(page: Page, apparence: "Machine" | "Clair" | "Sombre") {
  await page.getByRole("banner").getByRole("button", { name: /, compte .+ : menu$/ }).click();
  const choix = page.getByRole("menuitemradio", { name: apparence });
  await choix.click();
  // Le menu reste ouvert : on voit le thème changer.
  await expect(choix).toHaveAttribute("aria-checked", "true");
  await page.keyboard.press("Escape");
}

test.describe("sur un appareil réglé en clair", () => {
  test.use({ colorScheme: "light" });

  test("le thème sombre se choisit dans le menu du compte, et tient après un rechargement", async ({ page }) => {
    await seConnecter(page, "animateur");
    await expect(antenne(page)).toBeVisible();
    await attendreLeTheme(page, "clair");

    await choisir(page, "Sombre");
    await attendreLeTheme(page, "sombre");

    await page.reload();
    await expect(antenne(page)).toBeVisible();
    await attendreLeTheme(page, "sombre");
  });
});

test.describe("sur un appareil réglé en sombre", () => {
  test.use({ colorScheme: "dark" });

  test("le thème clair se choisit dans le menu du compte, et tient après un rechargement", async ({ page }) => {
    await seConnecter(page, "animateur");
    await expect(antenne(page)).toBeVisible();
    await attendreLeTheme(page, "sombre");

    await choisir(page, "Clair");
    await attendreLeTheme(page, "clair");

    await page.reload();
    await expect(antenne(page)).toBeVisible();
    await attendreLeTheme(page, "clair");
  });
});

test("« Machine » suit le réglage de l’appareil, sans recharger", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "dark" });
  await seConnecter(page, "animateur");
  await expect(antenne(page)).toBeVisible();
  await attendreLeTheme(page, "sombre");

  await page.emulateMedia({ colorScheme: "light" });
  await attendreLeTheme(page, "clair");
  await page.emulateMedia({ colorScheme: "dark" });
  await attendreLeTheme(page, "sombre");
});
