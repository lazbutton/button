import Uppy, { type UppyFile } from "@uppy/core";
import fr_FR from "@uppy/locales/lib/fr_FR";
import { useUppyEvent, useUppyState } from "@uppy/react";
import Tus from "@uppy/tus";
import { Button, Checkbox, Progress, Spinner, TextArea, TextField } from "@radix-ui/themes";
import { CalendarClock, CheckCircle2, CloudUpload, Disc3, LinkIcon, TriangleAlert } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState, type DragEvent } from "react";
import {
  loadGuestPage,
  PublicLinkError,
  saveGuestDiffusion,
  type PublicDiffusion,
  type PublicGuestResponse,
} from "../api/agenda";
import {
  dayLongLabel,
  durationLabel,
  guestLocalHint,
  parisWall,
  secondsLabel,
  statusOf,
  timeLabel,
} from "../api/agendaView";
import "../styles/pages/agenda.css";

type GuestMeta = { diffusion: string };
type GuestUppy = Uppy<GuestMeta, Record<string, never>>;
type GuestFile = UppyFile<GuestMeta, Record<string, never>>;

function tokenFromHash(): string {
  return decodeURIComponent(window.location.hash.replace(/^#/, "")).trim();
}

// One queue per date for the page's life: React may mount a card twice, the upload must go on.
const uppies = new Map<string, GuestUppy>();

function guestUppy(token: string, diffusion: number, formats: string[], maxBytes: number): GuestUppy {
  const key = `${token}:${diffusion}`;
  const known = uppies.get(key);
  if (known) return known;
  const uppy: GuestUppy = new Uppy<GuestMeta, Record<string, never>>({
    locale: fr_FR,
    autoProceed: true,
    restrictions: {
      allowedFileTypes: formats.map((format) => `.${format}`),
      maxFileSize: maxBytes,
    },
  });
  uppy.use(Tus, {
    endpoint: "/tus/",
    chunkSize: 8 * 1024 * 1024,
    retryDelays: [0, 1000, 3000, 5000, 10000, 20000],
    headers: { "X-Invite-Token": token },
    allowedMetaFields: ["diffusion", "name", "type"],
  });
  uppies.set(key, uppy);
  return uppy;
}

/** A guest's page: their dates, the drop of their set, the facts the radio needs. */
export function InvitationPage() {
  const [token] = useState(tokenFromHash);
  const [page, setPage] = useState<PublicGuestResponse | null>(null);
  const [problem, setProblem] = useState("");
  const [loading, setLoading] = useState(true);
  const timeZone = useMemo(() => Intl.DateTimeFormat().resolvedOptions().timeZone, []);

  // The token never leaves the hash for the address bar's history either.
  useEffect(() => {
    document.title = "Ton passage à la radio";
    const meta = document.createElement("meta");
    meta.name = "robots";
    meta.content = "noindex, nofollow";
    document.head.appendChild(meta);
    const referrer = document.createElement("meta");
    referrer.name = "referrer";
    referrer.content = "no-referrer";
    document.head.appendChild(referrer);
    return () => {
      meta.remove();
      referrer.remove();
    };
  }, []);

  const load = useCallback(async () => {
    if (!token) {
      setProblem("Ce lien est incomplet. Demande à la radio de te le renvoyer.");
      setLoading(false);
      return;
    }
    try {
      const payload = await loadGuestPage(token);
      setPage(payload);
      setProblem("");
      document.title = `${payload.station} — ton passage`;
    } catch (caught) {
      if (caught instanceof PublicLinkError && caught.status === 404) {
        setProblem("Ce lien ne marche plus. Demande un nouveau lien à la radio.");
      } else {
        setProblem(caught instanceof Error ? caught.message : "La radio ne répond pas.");
      }
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    void load();
  }, [load]);

  if (loading) {
    return (
      <main className="inv">
        <div className="inv-center">
          <Spinner size="3" />
        </div>
      </main>
    );
  }

  if (!page) {
    return (
      <main className="inv">
        <div className="inv-card inv-problem" role="alert">
          <LinkIcon size={20} aria-hidden="true" />
          <p>{problem}</p>
        </div>
      </main>
    );
  }

  return (
    <main className="inv">
      <header className="inv-head">
        <span className="inv-station">{page.station}</span>
        <h1>Salut {page.guest.name} !</h1>
        <p>
          {page.diffusions.length
            ? page.diffusions.length > 1
              ? "Voici tes passages. Dépose ton set pour chacun, avant la date limite."
              : "Voici ton passage. Dépose ton set avant la date limite."
            : "Aucun passage prévu pour l'instant. La radio te renverra ce lien quand une date sera posée."}
        </p>
      </header>
      {page.diffusions.map((row) => (
        <DiffusionCard
          key={row.id}
          row={row}
          token={token}
          timeZone={timeZone}
          formats={page.formats}
          maxBytes={page.max_bytes}
          onChanged={load}
        />
      ))}
      <footer className="inv-foot">
        Ce lien est personnel : il ne donne accès qu'à tes passages. Garde-le pour toi.
      </footer>
    </main>
  );
}

function DiffusionCard({
  row,
  token,
  timeZone,
  formats,
  maxBytes,
  onChanged,
}: {
  row: PublicDiffusion;
  token: string;
  timeZone: string;
  formats: string[];
  maxBytes: number;
  onChanged: () => Promise<void>;
}) {
  const start = parisWall(row.starts_at);
  const local = guestLocalHint(row.starts_at, row.ends_at, timeZone);
  const status = statusOf({ ...row, kind: row.kind, stop_requested: false, air_reason: "" });
  const deadline = parisWall(row.deadline_at);
  const closes = parisWall(row.deposit_closes_at);
  const late = row.deposit_open && Date.now() > new Date(row.deadline_at).getTime();
  const waiting = row.file?.status === "pending";

  // While the analysis runs, the page asks again every few seconds.
  useEffect(() => {
    if (!waiting) return;
    const timer = window.setInterval(() => void onChanged(), 4000);
    return () => window.clearInterval(timer);
  }, [waiting, onChanged]);

  return (
    <section className="inv-card" aria-label={`${row.title}, ${dayLongLabel(start.day)}`}>
      <header className="inv-card-head">
        <span className="inv-icon" aria-hidden="true">
          <Disc3 size={18} />
        </span>
        <div>
          <h2>{row.title}</h2>
          <p className="inv-when">
            {dayLongLabel(start.day)}, {timeLabel(row.starts_at)} → {timeLabel(row.ends_at)} (heure de Paris) ·{" "}
            {durationLabel(row.duration_min)}
          </p>
          {local ? <p className="inv-local">{local}</p> : null}
        </div>
        <span className={`ag-chip tone-${status.tone}`}>{status.label}</span>
      </header>

      {row.air_status !== "upcoming" ? (
        <p className="inv-note">
          {row.air_status === "aired"
            ? "Ton set est passé à l'antenne. Merci !"
            : row.air_status === "on_air"
              ? "Ton set est à l'antenne en ce moment."
              : "Ce passage n'a pas eu lieu. La radio te recontactera."}
        </p>
      ) : (
        <>
          <p className={`inv-deadline${late ? " is-late" : ""}`}>
            <CalendarClock size={15} aria-hidden="true" />
            {row.deposit_open
              ? late
                ? `La date limite est passée : dépose vite, au plus tard ${dayLongLabel(closes.day)} à ${timeLabel(row.deposit_closes_at)}.`
                : `À déposer avant ${dayLongLabel(deadline.day)}, ${timeLabel(row.deadline_at)}.`
              : "Le dépôt est fermé : il ferme 30 min avant le passage."}
          </p>
          <FileState row={row} />
          {row.deposit_open ? (
            <Dropzone row={row} token={token} formats={formats} maxBytes={maxBytes} onDone={onChanged} />
          ) : null}
          <SetDetails row={row} token={token} onSaved={onChanged} />
        </>
      )}
    </section>
  );
}

function FileState({ row }: { row: PublicDiffusion }) {
  const file = row.file;
  if (!file) return null;
  if (file.status === "pending") {
    return (
      <p className="inv-file is-wait">
        <Spinner size="1" />
        <span>
          <strong>{file.original_name}</strong> bien reçu. Vérification en cours : lecture complète, durée, niveau.
        </span>
      </p>
    );
  }
  if (file.status === "error") {
    return (
      <p className="inv-file is-bad" role="alert">
        <TriangleAlert size={16} aria-hidden="true" />
        <span>
          <strong>{file.original_name}</strong> : {file.error || "fichier illisible"}. Renvoie-le, ou un autre export.
        </span>
      </p>
    );
  }
  return (
    <div className="inv-file is-ok">
      <CheckCircle2 size={16} aria-hidden="true" />
      <span>
        <strong>{file.original_name}</strong> · {secondsLabel(file.duration)}
        {file.gain != null ? ` · niveau ajusté (${file.gain > 0 ? "+" : ""}${file.gain.toLocaleString("fr-FR")} dB)` : ""} ·
        bien reçu
        {file.late ? " (après la date limite)" : ""}
      </span>
      {row.overrun_seconds ? (
        <small>
          Ton set dépasse le créneau de {secondsLabel(row.overrun_seconds)} : il passera en entier, la suite de la grille sera
          décalée. Si tu as une version plus courte, tu peux la redéposer.
        </small>
      ) : null}
    </div>
  );
}

function Dropzone({
  row,
  token,
  formats,
  maxBytes,
  onDone,
}: {
  row: PublicDiffusion;
  token: string;
  formats: string[];
  maxBytes: number;
  onDone: () => Promise<void>;
}) {
  const uppy = guestUppy(token, row.id, formats, maxBytes);
  const files = useUppyState(uppy, (state) => state.files) as Record<string, GuestFile>;
  const [over, setOver] = useState(false);
  const [error, setError] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const list = Object.values(files);
  const uploading = list.some((file) => file.progress.uploadStarted && !file.progress.uploadComplete && !file.error);
  const progress = list.length ? Math.round(list.reduce((sum, file) => sum + (file.progress.percentage ?? 0), 0) / list.length) : 0;

  useUppyEvent(uppy, "restriction-failed", (_file, failure) => {
    setError(failure?.message || "Ce fichier n'est pas accepté.");
  });
  useUppyEvent(uppy, "upload-error", (_file, failure) => {
    const text = failure?.message || "";
    const reason = text.match(/response text: ([^,]+)/)?.[1];
    setError(reason ? `Refusé : ${reason}` : "L'envoi a échoué. Réessaie, il reprendra où il s'est arrêté.");
  });
  useUppyEvent(uppy, "complete", (result) => {
    if (result.successful?.length) {
      for (const file of result.successful) uppy.removeFile(file.id);
      void onDone();
    }
  });

  useEffect(() => {
    if (!uploading) return;
    const warn = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [uploading]);

  const add = (picked: FileList | null) => {
    setError("");
    const file = picked?.[0];
    if (!file) return;
    for (const old of uppy.getFiles()) uppy.removeFile(old.id);
    try {
      uppy.addFile({
        name: file.name,
        type: file.type,
        data: file,
        meta: { diffusion: String(row.id) },
      });
    } catch {
      // restriction-failed already explains it
    }
  };

  const onDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setOver(false);
    add(event.dataTransfer.files);
  };

  return (
    <div
      className={`inv-drop${over ? " is-over" : ""}${uploading ? " is-busy" : ""}`}
      onDragOver={(event) => {
        event.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={onDrop}
    >
      {uploading ? (
        <div className="inv-progress" aria-live="polite">
          <span>
            Envoi de <strong>{list[0]?.name}</strong> : {progress} %
          </span>
          <Progress value={progress} size="2" />
          <Button size="1" variant="soft" color="gray" onClick={() => (list[0]?.isPaused ? uppy.resumeAll() : uppy.pauseAll())}>
            {list[0]?.isPaused ? "Reprendre" : "Pause"}
          </Button>
        </div>
      ) : (
        <>
          <CloudUpload size={22} aria-hidden="true" />
          <p>
            <strong>{row.file ? "Glisse une nouvelle version ici" : "Glisse ton set ici"}</strong>
            <span>MP3, FLAC, WAV, AIFF, OGG, Opus ou M4A · jusqu'à {Math.round(maxBytes / 1024 ** 3)} Go</span>
          </p>
          <Button size="2" highContrast onClick={() => inputRef.current?.click()}>
            Choisir le fichier
          </Button>
          <input
            ref={inputRef}
            type="file"
            hidden
            accept={formats.map((format) => `.${format}`).join(",")}
            onChange={(event) => {
              add(event.target.files);
              event.target.value = "";
            }}
          />
        </>
      )}
      {error ? (
        <p className="inv-error" role="alert">
          {error}
        </p>
      ) : null}
      {!uploading && list.some((file) => file.error) ? (
        <Button size="1" variant="soft" onClick={() => void uppy.retryAll()}>
          Reprendre l'envoi
        </Button>
      ) : null}
    </div>
  );
}

function SetDetails({
  row,
  token,
  onSaved,
}: {
  row: PublicDiffusion;
  token: string;
  onSaved: () => Promise<void>;
}) {
  const [title, setTitle] = useState(row.set_title);
  const [tracklist, setTracklist] = useState(row.tracklist);
  const [rights, setRights] = useState(row.rights);
  const [state, setState] = useState<"" | "saving" | "saved" | "error">("");
  const dirty = title !== row.set_title || tracklist !== row.tracklist || rights !== row.rights;

  useEffect(() => {
    setTitle(row.set_title);
    setTracklist(row.tracklist);
    setRights(row.rights);
  }, [row.set_title, row.tracklist, row.rights]);

  const save = async () => {
    setState("saving");
    try {
      await saveGuestDiffusion(token, row.id, { set_title: title, tracklist, rights });
      setState("saved");
      await onSaved();
    } catch {
      setState("error");
    }
  };

  return (
    <form
      className="inv-details"
      onSubmit={(event) => {
        event.preventDefault();
        void save();
      }}
    >
      <label className="inv-field">
        <span>Titre du set (facultatif)</span>
        <TextField.Root size="2" value={title} onChange={(event) => setTitle(event.target.value)} placeholder="Ex. Lou en cavale" />
      </label>
      <label className="inv-field">
        <span>Tracklist</span>
        <TextArea
          size="2"
          rows={5}
          value={tracklist}
          placeholder={"Artiste – Titre\nArtiste – Titre"}
          onChange={(event) => setTracklist(event.target.value)}
        />
        <small>La radio la garde pour déclarer les titres diffusés.</small>
      </label>
      <label className="inv-rights">
        <Checkbox checked={rights} onCheckedChange={(value) => setRights(value === true)} />
        <span>
          <strong>J'ai les droits pour diffuser ce set.</strong> Sans cette case, il ne passe pas à l'antenne.
        </span>
      </label>
      <div className="inv-actions">
        {state === "saved" && !dirty ? (
          <span className="inv-saved">
            <CheckCircle2 size={15} aria-hidden="true" />
            Enregistré
          </span>
        ) : null}
        {state === "error" ? <span className="inv-error">Enregistrement impossible. Réessaie.</span> : null}
        <Button type="submit" size="2" highContrast disabled={!dirty || state === "saving"}>
          {state === "saving" ? "Enregistrement…" : "Enregistrer"}
        </Button>
      </div>
    </form>
  );
}
