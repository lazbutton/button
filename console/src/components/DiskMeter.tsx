import { diskAlert, diskLabel, usedRatio, type DiskUsage } from "../api/disk";
import { useApiJson } from "../api/useApiJson";

const POLL_MS = 45_000;

export function DiskMeter() {
  const disk = useApiJson<DiskUsage>("/system/disk.json", POLL_MS);
  const data = disk.data;
  if (!data || data.total <= 0) return null;
  const alert = diskAlert(data.free, data.total);
  const label = diskLabel(data.free, data.total);
  const ratio = usedRatio(data.used, data.total);
  return (
    <div className={`app-disk${alert ? " is-alert" : ""}`} title={label}>
      <p className="app-disk-kicker">Disque</p>
      <div
        className="app-disk-bar"
        role="meter"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={data.total}
        aria-valuenow={data.free}
        aria-valuetext={alert ? `${label}, alerte` : label}
      >
        <span style={{ width: `${Math.round(ratio * 100)}%` }} />
      </div>
      <p className="app-disk-copy">{label}</p>
    </div>
  );
}
