import type { Emission } from "./types";

export function slotsForHost(emissions: Emission[] | undefined, username: string): Emission[] {
  const name = username.trim().toLowerCase();
  if (!name) return [];
  return (emissions ?? []).filter(
    (row) => row.scope === "weekly" && (row.host_username || "").trim().toLowerCase() === name,
  );
}
