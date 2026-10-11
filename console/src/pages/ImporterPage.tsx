import Dashboard from "@uppy/react/dashboard";
import Tus from "@uppy/tus";
import Uppy from "@uppy/core";
import fr_FR from "@uppy/locales/lib/fr_FR";
import { useEffect, useRef, useState } from "react";
import "@uppy/core/css/style.min.css";
import "@uppy/dashboard/css/style.min.css";
import { SelectField } from "../ui/FormField";
import { useAppearance } from "../lib/Appearance";
import "../styles/pages/importer.css";

type Dest = "rotation" | "ntf1" | "ntf2" | "ntf3";

const DESTINATIONS: { value: Dest; label: string }[] = [
  { value: "rotation", label: "Rotation" },
  { value: "ntf1", label: "Archive NTF 1" },
  { value: "ntf2", label: "Archive NTF 2" },
  { value: "ntf3", label: "Archive NTF 3" },
];

const DEST_LABEL: Record<string, string> = {
  rotation: "Rotation",
  ntf1: "NTF 1",
  ntf2: "NTF 2",
  ntf3: "NTF 3",
};

type InboxFile = {
  name: string;
  dest: string;
  bytes?: number;
  offset?: number;
  reason?: string | null;
  at?: string;
};

type InboxStatus = {
  quota: { used: number; limit: number };
  queue: InboxFile[];
  rejected: InboxFile[];
  progress: InboxFile[];
};

function formatBytes(value: number): string {
  if (!Number.isFinite(value) || value < 1024) return `${Math.max(0, Math.round(value))} o`;
  const units = ["Ko", "Mo", "Go", "To"];
  let next = value / 1024;
  let index = 0;
  while (next >= 1024 && index < units.length - 1) {
    next /= 1024;
    index += 1;
  }
  return `${next >= 10 ? next.toFixed(0) : next.toFixed(1)} ${units[index]}`;
}

function createUppy(dest: { current: Dest }) {
  const uppy = new Uppy({
    locale: fr_FR,
    autoProceed: false,
    restrictions: {
      allowedFileTypes: [".mp3", ".flac", ".ogg", ".opus", ".m4a", ".wav", ".aif", ".aiff"],
    },
  });
  uppy.use(Tus, {
    endpoint: "/tus/",
    chunkSize: 8 * 1024 * 1024,
    retryDelays: [0, 1000, 3000, 5000, 10000],
  });
  uppy.setMeta({ destination: dest.current });
  return uppy;
}

export function ImporterPage() {
  const { appearance } = useAppearance();
  const destRef = useRef<Dest>("rotation");
  const [dest, setDest] = useState<Dest>("rotation");
  const [uppy] = useState(() => createUppy(destRef));
  const [status, setStatus] = useState<InboxStatus | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    destRef.current = dest;
    uppy.setMeta({ destination: dest });
  }, [dest, uppy]);

  useEffect(() => () => uppy.destroy(), [uppy]);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const response = await fetch("/library/inbox.json", { cache: "no-store" });
        if (response.status === 401) {
          if (!cancelled) setError("Session expirée — reconnecte-toi.");
          return;
        }
        if (!response.ok) {
          if (!cancelled) setError("Le dépôt ne répond pas. Réessaie. S’il reste muet, un admin vérifie le catalogue.");
          return;
        }
        const payload = (await response.json()) as InboxStatus;
        if (!cancelled) {
          setStatus(payload);
          setError("");
        }
      } catch {
        if (!cancelled) setError("Le dépôt ne répond pas. Réessaie. S’il reste muet, un admin vérifie le catalogue.");
      }
    };
    void load();
    const timer = window.setInterval(() => void load(), 5000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  const used = status?.quota.used ?? 0;
  const limit = status?.quota.limit ?? 0;
  const ratio = limit > 0 ? Math.min(100, Math.round((used / limit) * 100)) : 0;

  return (
    <div className="importer-page">
      <p className="importer-lead">
        Ici, les fichiers rejoignent la bibliothèque de la station. « Ajouter des fichiers » dans un bac les copie seulement dans ce bac.
      </p>
      <SelectField
        label="Destination"
        value={dest}
        options={DESTINATIONS}
        onValueChange={(value) => setDest(value as Dest)}
        hint="MP3, FLAC, OGG, Opus, M4A, WAV ou AIFF. Un envoi coupé reprend. Beets indexe ensuite."
      />
      <div
        className="importer-quota"
        role="meter"
        aria-valuemin={0}
        aria-valuemax={limit || undefined}
        aria-valuenow={used}
        aria-label="Quota de la station"
      >
        <span>
          {status ? `${formatBytes(used)} utilisés sur ${formatBytes(limit)}` : "Quota…"}
        </span>
        <span className="importer-quota-track">
          <span style={{ width: `${ratio}%` }} />
        </span>
      </div>
      {error ? (
        <p className="importer-error" role="alert">
          {error}
        </p>
      ) : null}
      <div className="importer-uppy">
        <Dashboard
          uppy={uppy}
          height={320}
          theme={appearance}
          proudlyDisplayPoweredByUppy={false}
          note="Glisse les fichiers. L’envoi reprend tout seul."
        />
      </div>
      <InboxList title="En cours" empty="Aucun envoi en cours." rows={status?.progress ?? []} />
      <InboxList title="File d’attente" empty="Rien en attente de promotion." rows={status?.queue ?? []} />
      <InboxList title="Rejets" empty="Aucun rejet." rows={status?.rejected ?? []} rejected />
    </div>
  );
}

function InboxList({
  title,
  empty,
  rows,
  rejected,
}: {
  title: string;
  empty: string;
  rows: InboxFile[];
  rejected?: boolean;
}) {
  return (
    <section className="importer-list" aria-label={title}>
      <h2>
        {title}
        <span>{rows.length}</span>
      </h2>
      {rows.length === 0 ? (
        <p>{empty}</p>
      ) : (
        <ul>
          {rows.map((row, index) => (
            <li key={`${row.name}-${row.at ?? index}`}>
              <span>
                {row.name}
                {row.dest ? ` · ${DEST_LABEL[row.dest] || row.dest}` : ""}
                {typeof row.bytes === "number" ? ` · ${formatBytes(row.bytes)}` : ""}
                {typeof row.offset === "number" && typeof row.bytes === "number" && row.bytes > 0
                  ? ` · ${Math.round((row.offset / row.bytes) * 100)} %`
                  : ""}
              </span>
              {rejected && row.reason ? <strong>{row.reason}</strong> : null}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
