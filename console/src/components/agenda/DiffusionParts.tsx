import { Button, TextField } from "@radix-ui/themes";
import { Check, Copy, FileAudio, Link2, RefreshCw } from "lucide-react";
import { useState } from "react";
import { fileAudioUrl, type AgendaGuest, type Diffusion } from "../../api/agenda";
import { dayLongLabel, inviteLink, inviteMessage, parisWall, secondsLabel, timeLabel } from "../../api/agendaView";

async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}

function CopyButton({ text, label }: { text: string; label: string }) {
  const [done, setDone] = useState<"" | "ok" | "fail">("");
  return (
    <Button
      type="button"
      size="1"
      variant="soft"
      color="gray"
      onClick={async () => {
        setDone((await copyText(text)) ? "ok" : "fail");
        window.setTimeout(() => setDone(""), 1800);
      }}
    >
      {done === "ok" ? <Check className="ui-button-icon" /> : <Copy className="ui-button-icon" />}
      {done === "ok" ? "Copié" : done === "fail" ? "Copie impossible" : label}
    </Button>
  );
}

function openedLabel(guest: AgendaGuest): string {
  if (!guest.opened_at) return "Lien jamais ouvert";
  const wall = parisWall(guest.opened_at);
  return `Ouvert le ${dayLongLabel(wall.day)} à ${timeLabel(guest.opened_at)}`;
}

/** The guest's private link, the ready message, and a new link if one leaked. */
export function InviteBox({
  row,
  station,
  onRenew,
}: {
  row: Diffusion;
  station: string;
  onRenew: () => Promise<void>;
}) {
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  const guest = row.guest;
  if (!guest?.token) return null;
  const link = inviteLink(window.location.origin, guest.token);
  const message = inviteMessage({
    station,
    guest: guest.name,
    title: row.title,
    start: row.starts_at,
    end: row.ends_at,
    deadline: row.deadline_at,
    link,
  });
  return (
    <section className="ag-section" aria-label="Invitation">
      <header className="ag-section-head">
        <h3>
          <Link2 size={14} aria-hidden="true" />
          Lien de {guest.name}
        </h3>
        <small className={guest.opened_at ? "" : "is-faint"}>{openedLabel(guest)}</small>
      </header>
      <TextField.Root size="2" value={link} readOnly aria-label="Lien de l'invité" className="ag-link-field" />
      <div className="ag-section-actions">
        <CopyButton text={link} label="Copier le lien" />
        <CopyButton text={message} label="Copier le message" />
        <Button
          type="button"
          size="1"
          variant={confirm ? "solid" : "ghost"}
          color={confirm ? "red" : "gray"}
          highContrast={confirm}
          disabled={busy}
          onClick={async () => {
            if (!confirm) {
              setConfirm(true);
              return;
            }
            setBusy(true);
            try {
              await onRenew();
            } finally {
              setBusy(false);
              setConfirm(false);
            }
          }}
        >
          <RefreshCw className="ui-button-icon" />
          {confirm ? "L'ancien lien ne marchera plus : confirmer" : "Nouveau lien"}
        </Button>
      </div>
      <p className="ag-hint">
        Le même lien sert pour toutes ses dates. Le dépôt ferme 30 min avant le début.
      </p>
    </section>
  );
}

/** What the set will play: the report of the analysis, a player, the gestures. */
export function FileSection({
  row,
  editable,
  onPick,
  onRemove,
}: {
  row: Diffusion;
  editable: boolean;
  onPick: () => void;
  onRemove: () => Promise<void>;
}) {
  const [confirm, setConfirm] = useState(false);
  const file = row.file;
  const open = row.air_status === "upcoming";
  if (!file) {
    return (
      <section className="ag-section" aria-label="Fichier du set">
        <header className="ag-section-head">
          <h3>
            <FileAudio size={14} aria-hidden="true" />
            Set
          </h3>
          <small className="is-faint">
            {row.guest ? `Attendu avant le ${dayLongLabel(parisWall(row.deadline_at).day)}, ${timeLabel(row.deadline_at)}` : "Aucun fichier"}
          </small>
        </header>
        {editable && open ? (
          <div className="ag-section-actions">
            <Button type="button" size="1" variant="soft" color="gray" onClick={onPick}>
              Choisir dans la banque
            </Button>
          </div>
        ) : null}
      </section>
    );
  }
  const report = file.report;
  const facts = [
    secondsLabel(file.duration),
    report.codec ? report.codec.toUpperCase() : "",
    report.sample_rate ? `${(report.sample_rate / 1000).toLocaleString("fr-FR")} kHz` : "",
    file.gain != null ? `niveau ajusté ${file.gain > 0 ? "+" : ""}${file.gain.toLocaleString("fr-FR")} dB` : "",
  ].filter(Boolean);
  return (
    <section className="ag-section" aria-label="Fichier du set">
      <header className="ag-section-head">
        <h3>
          <FileAudio size={14} aria-hidden="true" />
          {file.original_name || file.path.split("/").pop()}
        </h3>
        <small>
          {file.origin === "depot" ? "Déposé par l'invité" : "Pris dans la banque"}
          {file.late ? " · en retard" : ""}
        </small>
      </header>
      {report.status === "pending" ? (
        <p className="ag-report is-wait">Analyse en cours : lecture complète, durée, niveau.</p>
      ) : report.status === "error" ? (
        <p className="ag-report is-bad">{report.error || "Fichier illisible"}</p>
      ) : (
        <p className="ag-report">{facts.join(" · ")}</p>
      )}
      {report.warnings.length ? <p className="ag-report is-warn">{report.warnings.join(" · ")}</p> : null}
      {row.overrun_seconds ? (
        <p className="ag-report is-warn">
          Dépasse le créneau de {secondsLabel(row.overrun_seconds)} : il ira au bout, la grille reprendra après.
        </p>
      ) : null}
      {report.status !== "error" ? (
        <audio className="ag-audio" controls preload="none" src={fileAudioUrl(file)}>
          <track kind="captions" />
        </audio>
      ) : null}
      {editable && open ? (
        <div className="ag-section-actions">
          <Button type="button" size="1" variant="soft" color="gray" onClick={onPick}>
            Remplacer par un fichier de la banque
          </Button>
          <Button
            type="button"
            size="1"
            variant={confirm ? "solid" : "ghost"}
            color="red"
            highContrast={confirm}
            onClick={async () => {
              if (!confirm) {
                setConfirm(true);
                return;
              }
              await onRemove();
              setConfirm(false);
            }}
          >
            {confirm ? "Confirmer le retrait" : "Retirer le fichier"}
          </Button>
        </div>
      ) : null}
    </section>
  );
}
