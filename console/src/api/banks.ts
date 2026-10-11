import type { BankDestination } from "./soundsView";

/** Creates an archive bank: a folder of 20-archives, through the catalogue. */
export async function createBank(label: string, folder: string): Promise<BankDestination> {
  let response: Response;
  try {
    response = await fetch("/library/banks.json", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ label, folder }),
    });
  } catch {
    throw new Error("Le catalogue ne répond pas. Réessaie dans un instant.");
  }
  const payload = (await response.json().catch(() => ({}))) as { destination?: BankDestination; error?: string };
  if (response.status === 401) throw new Error("Session expirée : recharge la page et reconnecte-toi.");
  if (!response.ok || !payload.destination) {
    throw new Error(payload.error?.trim() || "Création impossible. Réessaie.");
  }
  return payload.destination;
}
