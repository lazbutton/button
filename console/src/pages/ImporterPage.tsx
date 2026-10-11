import Uppy, { type UppyFile } from "@uppy/core";
import fr_FR from "@uppy/locales/lib/fr_FR";
import { useUppyEvent, useUppyState } from "@uppy/react";
import Tus from "@uppy/tus";
import { Button, IconButton, Spinner, Tooltip } from "@radix-ui/themes";
import {
  AlertTriangle,
  Ban,
  Check,
  FileAudio,
  FolderOpen,
  FolderInput,
  Pause,
  Play,
  RefreshCw,
  RotateCcw,
  Upload,
  X,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState, type DragEvent, type ReactNode } from "react";
import { filesFromDataTransfer, isFileDrag } from "../api/audioDrop";
import {
  agoLabel,
  BANK_FORMATS,
  destinationLabel,
  formatBytes,
  percentOf,
  tusReason,
  tusRetryable,
  ROTATION_DESTINATION,
  type BankDestination,
} from "../api/soundsView";
import { createBank } from "../api/banks";
import { CreateBankDialog } from "../components/banque/CreateBankDialog";
import { DestinationPicker } from "../components/banque/DestinationPicker";
import { ProtoToast, useProtoToast } from "../components/ProtoToast";
import "../styles/pages/sons.css";

type BankMeta = { destination: string };
type BankUppy = Uppy<BankMeta, Record<string, never>>;
type BankFile = UppyFile<BankMeta, Record<string, never>>;

type InboxFile = {
  name: string;
  dest: string;
  bytes?: number;
  offset?: number;
  reason?: string | null;
  at?: string;
};

type InboxStatus = {
  /** Rotation, then every folder of 20-archives. Missing from an older catalogue. */
  destinations?: BankDestination[];
  quota: { used: number; limit: number };
  queue: InboxFile[];
  rejected: InboxFile[];
  progress: InboxFile[];
};

type FileState = "ready" | "uploading" | "paused" | "done" | "error";

const FORMATS_LABEL = "MP3, FLAC, OGG, Opus, M4A, WAV, AIFF";

function bankAccepts(name: string): boolean {
  const dot = name.lastIndexOf(".");
  return dot > 0 && BANK_FORMATS.includes(name.slice(dot).toLowerCase());
}

// One queue for the whole session: switching to the Bacs tab does not cut an upload.
let sharedUppy: BankUppy | null = null;
let lastDestination = ROTATION_DESTINATION.id;

function bankUppy(): BankUppy {
  if (sharedUppy) return sharedUppy;
  const uppy: BankUppy = new Uppy<BankMeta, Record<string, never>>({
    locale: fr_FR,
    autoProceed: false,
    restrictions: { allowedFileTypes: BANK_FORMATS },
  });
  uppy.use(Tus, {
    endpoint: "/tus/",
    chunkSize: 8 * 1024 * 1024,
    retryDelays: [0, 1000, 3000, 5000, 10000],
  });
  sharedUppy = uppy;
  return uppy;
}

function fileState(file: BankFile): FileState {
  if (file.error) return "error";
  if (file.progress.uploadComplete) return "done";
  if (file.isPaused) return "paused";
  if (file.progress.uploadStarted) return "uploading";
  return "ready";
}

function useInbox() {
  const [status, setStatus] = useState<InboxStatus | null>(null);
  const [problem, setProblem] = useState<"" | "session" | "down">("");
  const [loadedAt, setLoadedAt] = useState(() => Date.now());
  const [loading, setLoading] = useState(false);
  const alive = useRef(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const response = await fetch("/library/inbox.json", { cache: "no-store" });
      if (!alive.current) return;
      if (response.status === 401) {
        setProblem("session");
        return;
      }
      if (!response.ok) {
        setProblem("down");
        return;
      }
      const payload = (await response.json()) as InboxStatus;
      if (!alive.current) return;
      setStatus(payload);
      setProblem("");
      setLoadedAt(Date.now());
    } catch {
      if (alive.current) setProblem("down");
    } finally {
      if (alive.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    alive.current = true;
    void load();
    const timer = window.setInterval(() => {
      if (document.visibilityState === "visible") void load();
    }, 5000);
    return () => {
      alive.current = false;
      window.clearInterval(timer);
    };
  }, [load]);

  return { status, problem, loadedAt, loading, load };
}

export function ImporterPage() {
  const uppy = bankUppy();
  const files = useUppyState(uppy, (state) => state.files);
  const totalProgress = useUppyState(uppy, (state) => state.totalProgress);
  const { status, problem, loadedAt, loading, load } = useInbox();
  const { message, show, dismiss } = useProtoToast();
  const [destination, setDestinationState] = useState(lastDestination);
  const [creating, setCreating] = useState<string | null>(null);
  const [skipped, setSkipped] = useState<string[]>([]);
  const [dropOver, setDropOver] = useState(false);
  const dropDepth = useRef(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const folderRef = useRef<HTMLInputElement>(null);

  const list = useMemo(() => Object.values(files), [files]);
  const states = useMemo(() => list.map(fileState), [list]);
  const count = (state: FileState) => states.filter((item) => item === state).length;
  const ready = count("ready");
  const uploading = count("uploading");
  const paused = count("paused");
  const done = count("done");
  const failed = count("error");
  const active = uploading + paused > 0;
  const readyBytes = list.reduce((sum, file, index) => (states[index] === "ready" ? sum + (file.size ?? 0) : sum), 0);
  const destinations = status?.destinations?.length ? status.destinations : [ROTATION_DESTINATION];
  // A bank gone from the disk falls back to rotation rather than to a destination the catalogue refuses.
  const destinationInfo = destinations.find((item) => item.id === destination) ?? destinations[0];
  const labelOf = (id: string | null | undefined) => destinationLabel(destinations, id);

  useUppyEvent(uppy, "complete", (result) => {
    void load();
    const sent = result.successful?.length ?? 0;
    const refused = result.failed?.length ?? 0;
    if (!sent && !refused) return;
    if (!refused) show(sent === 1 ? "1 fichier envoyé à la banque" : `${sent} fichiers envoyés à la banque`, "success");
    else
      show(
        `${sent} envoyé${sent === 1 ? "" : "s"}, ${refused} refusé${refused === 1 ? "" : "s"} : voir la liste`,
        "error",
      );
  });

  // Closing the tab mid-upload loses the file handles: ask first.
  useEffect(() => {
    if (!uploading) return;
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [uploading]);

  const setDestination = (next: string) => {
    lastDestination = next;
    setDestinationState(next);
    // Files not sent yet follow the new destination; the others keep where they went.
    for (const file of uppy.getFiles()) {
      if (fileState(file) === "ready") uppy.setFileMeta(file.id, { destination: next });
    }
  };

  const addLocal = (picked: File[]) => {
    const visible = picked.filter((file) => !file.name.startsWith("."));
    const accepted = visible.filter((file) => bankAccepts(file.name) && file.size > 0);
    const refused = visible.filter((file) => !accepted.includes(file)).map((file) => file.name);
    const before = uppy.getFiles().length;
    if (accepted.length) {
      try {
        uppy.addFiles(
          accepted.map((file) => ({
            name: file.name,
            type: file.type,
            data: file,
            source: "Local",
            meta: { destination: destinationInfo.id },
          })),
        );
      } catch {
        show("Ces fichiers n'ont pas pu entrer dans la liste.", "error");
      }
    }
    const added = uppy.getFiles().length - before;
    const twice = accepted.length - added;
    setSkipped(refused);
    if (!visible.length) show("Aucun fichier dans ce choix.", "error");
    else if (twice > 0 && added === 0) show("Ces fichiers sont déjà dans la liste.", "info");
    else if (twice > 0)
      show(`${twice} fichier${twice === 1 ? "" : "s"} déjà dans la liste, ignoré${twice === 1 ? "" : "s"}.`, "info");
  };

  const send = () => {
    if (!ready) return;
    void uppy.upload().catch(() => show("L'envoi n'a pas démarré. Réessaie.", "error"));
  };

  const clearFinished = () => {
    for (const file of uppy.getFiles()) {
      if (fileState(file) === "done") uppy.removeFile(file.id);
    }
  };

  const clearAll = () => {
    for (const file of uppy.getFiles()) {
      const state = fileState(file);
      if (state !== "uploading") uppy.removeFile(file.id);
    }
    setSkipped([]);
  };

  const onDrop = (event: DragEvent<HTMLElement>) => {
    if (!isFileDrag(event)) return;
    event.preventDefault();
    dropDepth.current = 0;
    setDropOver(false);
    const data = event.dataTransfer;
    void filesFromDataTransfer(data, () => true).then(addLocal);
  };

  const quotaUsed = status?.quota.used ?? 0;
  const quotaLimit = status?.quota.limit ?? 0;
  const overQuota = quotaLimit > 0 && quotaUsed + readyBytes > quotaLimit;

  return (
    <div className="banque">
      <header className="banque-head">
        <div className="banque-head-copy">
          <h2>Ajouter à la banque</h2>
          <p>
            Les fichiers rejoignent la bibliothèque de la station, puis Beets les indexe. Pour un seul bac, passe plutôt
            par <span className="bacs-nowrap">« Ajouter »</span> dans le bac.
          </p>
        </div>
        <QuotaMeter used={quotaUsed} limit={quotaLimit} pending={readyBytes} known={status != null} />
      </header>

      {problem ? (
        <div className="banque-alert" role="alert">
          <AlertTriangle size={16} aria-hidden="true" />
          <p>
            {problem === "session"
              ? "Session expirée : recharge la page et reconnecte-toi pour voir la file et envoyer."
              : "Le catalogue ne répond pas : file, refus et quota sont indisponibles, et les envois risquent d'être refusés. Si ça dure, un admin vérifie le service catalogue."}
          </p>
          <Button size="1" variant="soft" color="gray" disabled={loading} onClick={() => void load()}>
            <RefreshCw className="ui-button-icon" />
            Réessayer
          </Button>
        </div>
      ) : null}

      <div className="banque-grid">
        <section
          className={`banque-send${dropOver ? " is-drop" : ""}`}
          aria-label="Envoi vers la banque"
          onDragEnter={(event) => {
            if (!isFileDrag(event)) return;
            dropDepth.current += 1;
            setDropOver(true);
          }}
          onDragOver={(event) => {
            if (!isFileDrag(event)) return;
            event.preventDefault();
            event.dataTransfer.dropEffect = "copy";
          }}
          onDragLeave={(event) => {
            if (!isFileDrag(event)) return;
            dropDepth.current -= 1;
            if (dropDepth.current <= 0) {
              dropDepth.current = 0;
              setDropOver(false);
            }
          }}
          onDrop={onDrop}
        >
          <div className="banque-dest">
            <span className="ui-field-label">Destination</span>
            <DestinationPicker
              destinations={destinations}
              value={destinationInfo}
              onChange={setDestination}
              onCreate={(label) => setCreating(label)}
            />
          </div>

          <div className={`banque-drop${list.length ? " is-compact" : ""}`}>
            <span className="banque-drop-icon" aria-hidden="true">
              <Upload size={list.length ? 16 : 20} />
            </span>
            <div className="banque-drop-copy">
              <strong>{list.length ? "Ajouter d'autres fichiers" : "Glisse des fichiers ou un dossier ici"}</strong>
              <span>
                {FORMATS_LABEL} · vers <b>{destinationInfo.label}</b> · un envoi coupé reprend
              </span>
            </div>
            <div className="banque-drop-actions">
              <Button size={list.length ? "1" : "2"} highContrast onClick={() => inputRef.current?.click()}>
                <FileAudio className="ui-button-icon" />
                Fichiers
              </Button>
              <Button
                size={list.length ? "1" : "2"}
                variant="soft"
                color="gray"
                onClick={() => folderRef.current?.click()}
              >
                <FolderOpen className="ui-button-icon" />
                Dossier
              </Button>
            </div>
            <input
              ref={inputRef}
              type="file"
              multiple
              hidden
              accept={BANK_FORMATS.join(",")}
              onChange={(event) => {
                const picked = Array.from(event.target.files ?? []);
                event.target.value = "";
                addLocal(picked);
              }}
            />
            <input
              ref={folderRef}
              type="file"
              multiple
              hidden
              // @ts-expect-error vendor directory picker
              webkitdirectory=""
              directory=""
              onChange={(event) => {
                const picked = Array.from(event.target.files ?? []);
                event.target.value = "";
                addLocal(picked);
              }}
            />
          </div>

          {skipped.length ? (
            <div className="banque-skipped" role="status">
              <Ban size={14} aria-hidden="true" />
              <p>
                <strong>
                  {skipped.length} fichier{skipped.length === 1 ? "" : "s"} ignoré{skipped.length === 1 ? "" : "s"}
                </strong>{" "}
                : format non accepté ou fichier vide. {skipped.slice(0, 3).join(", ")}
                {skipped.length > 3 ? `, et ${skipped.length - 3} autre${skipped.length - 3 === 1 ? "" : "s"}` : ""}.
              </p>
              <IconButton size="1" variant="ghost" color="gray" aria-label="Masquer" onClick={() => setSkipped([])}>
                <X size={14} />
              </IconButton>
            </div>
          ) : null}

          {list.length ? (
            <>
              <ul className="banque-queue" aria-label="Fichiers à envoyer">
                {list.map((file, index) => (
                  <QueueRow
                    key={file.id}
                    file={file}
                    state={states[index]}
                    destination={labelOf(file.meta.destination)}
                    onPause={() => uppy.pauseResume(file.id)}
                    onRetry={() => void uppy.retryUpload(file.id)}
                    onRemove={() => uppy.removeFile(file.id)}
                  />
                ))}
              </ul>
              <footer className="banque-send-foot">
                <p className="banque-send-summary" aria-live="polite">
                  {active ? (
                    <>
                      <Spinner size="1" />
                      Envoi en cours · {totalProgress} %{paused ? ` · ${paused} en pause` : ""}
                    </>
                  ) : ready ? (
                    <>
                      {ready} fichier{ready === 1 ? "" : "s"} · {formatBytes(readyBytes)} vers{" "}
                      <b>{destinationInfo.label}</b>
                    </>
                  ) : (
                    <>
                      {done ? `${done} envoyé${done === 1 ? "" : "s"}` : ""}
                      {done && failed ? " · " : ""}
                      {failed ? `${failed} refusé${failed === 1 ? "" : "s"}` : ""}
                    </>
                  )}
                </p>
                {overQuota && ready ? (
                  <span className="banque-warn">
                    <AlertTriangle size={13} aria-hidden="true" />
                    Dépasse le quota restant
                  </span>
                ) : null}
                <span className="bacs-spacer" />
                {done && !active ? (
                  <Button size="2" variant="ghost" color="gray" onClick={clearFinished}>
                    Effacer les envoyés
                  </Button>
                ) : null}
                {!active ? (
                  <Button size="2" variant="ghost" color="gray" onClick={clearAll}>
                    Tout retirer
                  </Button>
                ) : (
                  <Button
                    size="2"
                    variant="soft"
                    color="gray"
                    onClick={() => (uploading ? uppy.pauseAll() : uppy.resumeAll())}
                  >
                    {uploading ? <Pause className="ui-button-icon" /> : <Play className="ui-button-icon" />}
                    {uploading ? "Tout mettre en pause" : "Reprendre"}
                  </Button>
                )}
                <Button size="2" highContrast disabled={!ready || problem === "session"} onClick={send}>
                  <Upload className="ui-button-icon" />
                  {ready > 1 ? `Envoyer ${ready} fichiers` : "Envoyer"}
                </Button>
              </footer>
            </>
          ) : null}

          {dropOver ? (
            <div className="banque-drop-overlay" aria-hidden="true">
              <FolderInput size={22} />
              <strong>Déposer pour ajouter à la liste</strong>
              <span>Destination : {destinationInfo.label}</span>
            </div>
          ) : null}
        </section>

        <Activity
          status={status}
          stale={Boolean(problem)}
          loadedAt={loadedAt}
          loading={loading}
          labelOf={labelOf}
          onRefresh={() => void load()}
        />
      </div>
      <CreateBankDialog
        open={creating != null}
        onOpenChange={(open) => {
          if (!open) setCreating(null);
        }}
        initialLabel={creating ?? ""}
        destinations={destinations}
        onCreate={async (label, folder) => {
          const created = await createBank(label, folder);
          await load();
          setDestination(created.id);
          show(`Banque « ${created.label} » créée : les envois iront dans ${created.folder}`, "success");
        }}
      />
      <ProtoToast message={message} onDismiss={dismiss} />
    </div>
  );
}

function QuotaMeter({ used, limit, pending, known }: { used: number; limit: number; pending: number; known: boolean }) {
  const usedPct = limit > 0 ? Math.min(100, (used / limit) * 100) : 0;
  const pendingPct = limit > 0 ? Math.min(100 - usedPct, (pending / limit) * 100) : 0;
  const level = usedPct >= 95 ? "is-full" : usedPct >= 85 ? "is-high" : "";
  return (
    <div
      className={`banque-quota ${level}`}
      role="meter"
      aria-label="Quota de la station"
      aria-valuemin={0}
      aria-valuemax={limit || undefined}
      aria-valuenow={used}
      aria-valuetext={known ? `${formatBytes(used)} sur ${formatBytes(limit)}` : "inconnu"}
    >
      <span className="banque-quota-copy">
        <span>Quota</span>
        <strong>{known ? `${formatBytes(used)} / ${formatBytes(limit)}` : "—"}</strong>
      </span>
      <span className="banque-quota-track" aria-hidden="true">
        <i style={{ width: `${usedPct}%` }} />
        {pendingPct > 0 ? <i className="is-pending" style={{ width: `${pendingPct}%` }} /> : null}
      </span>
      <span className="banque-quota-foot">
        {known ? `${formatBytes(Math.max(0, limit - used))} libres` : "Catalogue injoignable"}
        {pending > 0 && known ? ` · ${formatBytes(pending)} à envoyer` : ""}
      </span>
    </div>
  );
}

function QueueRow({
  file,
  state,
  destination,
  onPause,
  onRetry,
  onRemove,
}: {
  file: BankFile;
  state: FileState;
  destination: string;
  onPause: () => void;
  onRetry: () => void;
  onRemove: () => void;
}) {
  const total = file.size ?? 0;
  const sent = file.progress.bytesUploaded || 0;
  const percent = file.progress.percentage ?? percentOf(sent, total);
  const reason = state === "error" ? tusReason(file.error) : "";
  const stateLabel =
    state === "ready"
      ? "Prêt"
      : state === "uploading"
        ? `${percent} %`
        : state === "paused"
          ? "En pause"
          : state === "done"
            ? "Envoyé"
            : "Refusé";

  return (
    <li className={`banque-file is-${state}`}>
      <span className="banque-file-icon" aria-hidden="true">
        {state === "done" ? (
          <Check size={15} />
        ) : state === "error" ? (
          <AlertTriangle size={15} />
        ) : (
          <FileAudio size={15} />
        )}
      </span>
      <div className="banque-file-main">
        <span className="banque-file-name" title={file.name}>
          {file.name}
        </span>
        <span className="banque-file-meta">
          <span>{destination}</span>
          <span>
            {state === "uploading" || state === "paused"
              ? `${formatBytes(sent)} / ${formatBytes(total)}`
              : formatBytes(total)}
          </span>
          {reason ? <span className="banque-file-reason">{reason}</span> : null}
        </span>
        {state === "uploading" || state === "paused" ? (
          <span
            className="banque-progress"
            role="progressbar"
            aria-label={`Envoi de ${file.name}`}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={percent}
          >
            <i style={{ width: `${percent}%` }} />
          </span>
        ) : null}
      </div>
      <span className="banque-file-state">{stateLabel}</span>
      <span className="banque-file-actions">
        {state === "uploading" || state === "paused" ? (
          <Tooltip content={state === "paused" ? "Reprendre" : "Mettre en pause"}>
            <IconButton
              size="1"
              variant="ghost"
              color="gray"
              aria-label={`${state === "paused" ? "Reprendre" : "Mettre en pause"} ${file.name}`}
              onClick={onPause}
            >
              {state === "paused" ? <Play size={14} /> : <Pause size={14} />}
            </IconButton>
          </Tooltip>
        ) : null}
        {state === "error" && tusRetryable(file.error) ? (
          <Tooltip content="Réessayer">
            <IconButton size="1" variant="ghost" color="gray" aria-label={`Réessayer ${file.name}`} onClick={onRetry}>
              <RotateCcw size={14} />
            </IconButton>
          </Tooltip>
        ) : null}
        <Tooltip content={state === "uploading" ? "Annuler l'envoi" : "Retirer de la liste"}>
          <IconButton size="1" variant="ghost" color="gray" aria-label={`Retirer ${file.name}`} onClick={onRemove}>
            <X size={14} />
          </IconButton>
        </Tooltip>
      </span>
    </li>
  );
}

function Activity({
  status,
  stale,
  loadedAt,
  loading,
  labelOf,
  onRefresh,
}: {
  status: InboxStatus | null;
  /** The last reading failed: what shows is old, or nothing is known. */
  stale: boolean;
  loadedAt: number;
  loading: boolean;
  labelOf: (id: string) => string;
  onRefresh: () => void;
}) {
  const progress = status?.progress ?? [];
  const queue = status?.queue ?? [];
  const rejected = status?.rejected ?? [];
  const when = !status
    ? stale
      ? "Indisponible"
      : "Lecture…"
    : stale
      ? `Lu à ${new Date(loadedAt).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}`
      : "Actualisé toutes les 5 s";
  return (
    <aside className="banque-activity" aria-label="Activité du dépôt">
      <header className="banque-activity-head">
        <h3>Activité du dépôt</h3>
        <span className={`banque-activity-when${stale ? " is-stale" : ""}`}>{when}</span>
        <Tooltip content="Actualiser">
          <IconButton
            size="1"
            variant="ghost"
            color="gray"
            aria-label="Actualiser"
            disabled={loading}
            onClick={onRefresh}
          >
            <RefreshCw size={14} className={loading ? "is-spinning" : undefined} />
          </IconButton>
        </Tooltip>
      </header>
      {!status ? (
        <p className="banque-activity-unknown">
          {stale ? "File, envois en cours et refus s'afficheront dès que le catalogue répondra." : "Lecture du dépôt…"}
        </p>
      ) : (
        <>
          <ActivityList
            labelOf={labelOf}
            title="En réception"
            hint="Envois arrivés en partie sur le serveur, de tous les postes."
            empty="Aucun envoi en cours."
            rows={progress}
            render={(row) => {
              const pct = percentOf(row.offset, row.bytes);
              return (
                <>
                  <span className="banque-row-side">{pct} %</span>
                  <span className="banque-progress" aria-hidden="true">
                    <i style={{ width: `${pct}%` }} />
                  </span>
                </>
              );
            }}
          />
          <ActivityList
            labelOf={labelOf}
            title="En attente d'indexation"
            hint="Reçus. Ils rejoignent la banque au prochain passage de l'indexation."
            empty="Rien en attente."
            rows={queue}
            render={(row) => (
              <span className="banque-row-side">{typeof row.bytes === "number" ? formatBytes(row.bytes) : ""}</span>
            )}
          />
          <ActivityList
            labelOf={labelOf}
            title="Refusés"
            hint="Le dépôt les a écartés : renomme, convertis ou libère de la place, puis renvoie."
            empty="Aucun refus."
            rows={rejected}
            tone="danger"
            render={(row) => (
              <>
                <span className="banque-row-reason">{row.reason || "refusé"}</span>
                {row.at ? <span className="banque-row-side">{agoLabel(row.at, loadedAt)}</span> : null}
              </>
            )}
          />
        </>
      )}
    </aside>
  );
}

function ActivityList({
  title,
  hint,
  empty,
  rows,
  tone,
  labelOf,
  render,
}: {
  labelOf: (id: string) => string;
  title: string;
  hint: string;
  empty: string;
  rows: InboxFile[];
  tone?: "danger";
  render: (row: InboxFile) => ReactNode;
}) {
  return (
    <section className={`banque-list${tone ? ` is-${tone}` : ""}`} aria-label={title}>
      <h4>
        {title}
        <span className={`bacs-count${rows.length ? " is-some" : ""}`}>{rows.length}</span>
      </h4>
      <p className="banque-list-hint">{hint}</p>
      {rows.length === 0 ? (
        <p className="banque-list-empty">{empty}</p>
      ) : (
        <ul>
          {rows.map((row, index) => (
            <li key={`${row.name}-${row.at ?? ""}-${index}`} className="banque-row">
              <span className="banque-row-main">
                <span className="banque-row-name" title={row.name}>
                  {row.name}
                </span>
                <span className="banque-row-dest">{labelOf(row.dest)}</span>
              </span>
              {render(row)}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
