export type StationVolume = {
  name: string;
  host: string;
};

export function stationSmbUrl(host: string, share: string, rel = ""): string {
  const parts = [share, ...rel.split("/").filter(Boolean)].map(encodeURIComponent);
  return `smb://${host}/${parts.join("/")}`;
}

export async function fetchVolume(): Promise<StationVolume | null> {
  try {
    const response = await fetch("/library/volume.json", { cache: "no-store" });
    if (!response.ok) return null;
    const body = (await response.json()) as { name?: string; host?: string };
    if (!body.name) return null;
    return { name: body.name, host: body.host ?? "" };
  } catch {
    return null;
  }
}

export async function setVolumePassword(username: string, password: string): Promise<void> {
  let response: Response;
  try {
    response = await fetch("/library/volume-password.json", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(password ? { username, password } : { username, clear: true }),
    });
  } catch {
    throw new Error("Le catalogue ne répond pas. Réessaie dans un instant.");
  }
  const payload = (await response.json().catch(() => ({}))) as { error?: string };
  if (response.status === 401) throw new Error("Session expirée : recharge la page et reconnecte-toi.");
  if (!response.ok) throw new Error(payload.error?.trim() || "Enregistrement impossible. Réessaie.");
}
