const GIB = 1024 ** 3;

export type DiskUsage = {
  total: number;
  used: number;
  free: number;
  path: string;
};

export function formatGo(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes < 0) return "0";
  const value = bytes / GIB;
  const rounded = value >= 10 ? Math.round(value) : Math.round(value * 10) / 10;
  return String(rounded).replace(".", ",");
}

export function diskLabel(free: number, total: number): string {
  return `${formatGo(free)} Go libres sur ${formatGo(total)}`;
}

export function diskAlert(free: number, total: number): boolean {
  if (!Number.isFinite(total) || total <= 0) return true;
  return free / total < 0.2;
}

export function usedRatio(used: number, total: number): number {
  if (!Number.isFinite(total) || total <= 0) return 1;
  return Math.min(1, Math.max(0, used / total));
}
