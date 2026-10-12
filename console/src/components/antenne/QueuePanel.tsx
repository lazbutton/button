import { ArrowRight, GripVertical, Lock, X } from "lucide-react";
import { useState, type DragEvent, type KeyboardEvent } from "react";
import { Link } from "react-router-dom";
import { mmss } from "../../api/antenneDesk";
import { LIBRARY_DRAG_MIME, type LibraryHit } from "../../api/library";
import { DESK_FILE_AHEAD, partitionRundown, queueItemKey, queueItemLocked, rundownCopy } from "../../api/rundownLive";
import type { LiveSnapshot, Rundown, RundownItem } from "../../api/types";
import { parisParts } from "../../lib/parisClock";

const KINDS = new Set(["musique", "jingle", "son", "pub"]);

function libraryHit(event: DragEvent): LibraryHit | null {
  const raw = event.dataTransfer.getData(LIBRARY_DRAG_MIME);
  if (!raw) return null;
  try {
    const hit = JSON.parse(raw) as LibraryHit;
    return hit?.path ? hit : null;
  } catch {
    return null;
  }
}

function fromLibrary(event: DragEvent): boolean {
  return event.dataTransfer.types.includes(LIBRARY_DRAG_MIME);
}

/** Ce qui passe ensuite : ordre, heures de passage, retrait, glisser depuis la bibliothèque. */
export function QueuePanel({
  rundown,
  live,
  wall,
  onRemove,
  onReorder,
  onInsertHit,
}: {
  rundown: Rundown | null;
  live: LiveSnapshot | null;
  wall: Date;
  onRemove: (item: RundownItem) => void;
  onReorder: (ids: string[]) => void;
  onInsertHit: (hit: LibraryHit, beforeId: string | null) => void;
}) {
  const parts = rundown ? partitionRundown(rundown.items, wall, live) : null;
  const onAirId = parts?.onAir?.id;
  const all = parts?.upcoming ?? [];
  const upcoming = all.slice(0, DESK_FILE_AHEAD);
  const hidden = all.length - upcoming.length;
  const [dragId, setDragId] = useState<string | null>(null);
  const [overId, setOverId] = useState<string | null>(null);
  const [dropEnd, setDropEnd] = useState(false);

  const movableIds = () =>
    upcoming.filter((item) => item.id && !queueItemLocked(item, onAirId)).map((item) => item.id as string);

  const move = (from: string, to: string) => {
    const ids = movableIds();
    if (!ids.includes(from) || from === to) return;
    const next = ids.filter((id) => id !== from);
    const at = next.indexOf(to);
    next.splice(at < 0 ? next.length : at, 0, from);
    onReorder(next);
  };

  const nudge = (event: KeyboardEvent, id: string) => {
    if (event.key !== "ArrowUp" && event.key !== "ArrowDown") return;
    event.preventDefault();
    const ids = movableIds();
    const index = ids.indexOf(id);
    const target = event.key === "ArrowUp" ? index - 1 : index + 1;
    if (index < 0 || target < 0 || target >= ids.length) return;
    const next = [...ids];
    [next[index], next[target]] = [next[target], next[index]];
    onReorder(next);
  };

  return (
    <section
      className="ant-panel ant-queue"
      aria-labelledby="ant-queue-title"
      data-drop={dropEnd ? "true" : "false"}
      onDragOver={(event) => {
        if (!fromLibrary(event)) return;
        event.preventDefault();
        event.dataTransfer.dropEffect = "copy";
        setDropEnd(true);
      }}
      onDragLeave={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setDropEnd(false);
      }}
      onDrop={(event) => {
        setDropEnd(false);
        const hit = libraryHit(event);
        if (!hit) return;
        event.preventDefault();
        setOverId(null);
        onInsertHit(hit, null);
      }}
    >
      <header className="ant-panel-head">
        <h2 id="ant-queue-title">File</h2>
        {rundown?.clock ? <span className="ant-chip" title="Heure type en cours">{rundown.clock}</span> : null}
        <span className="ant-panel-count">
          {all.length ? `${all.length} à venir` : ""}
        </span>
      </header>

      {upcoming.length ? (
        <ol className="ant-queue-list">
          {upcoming.map((item, index) => {
            const locked = queueItemLocked(item, onAirId);
            const movable = Boolean(item.id) && !locked;
            const anchored = item.when === "anchored";
            const copy = rundownCopy(item);
            const start = Date.parse(item.at);
            const airAt = Number.isFinite(start) ? parisParts(new Date(start)).clock : "—";
            const kind = KINDS.has(item.kind) ? item.kind : "son";
            return (
              <li
                key={queueItemKey(item, index)}
                className={[
                  index === 0 ? "is-next" : "",
                  anchored ? "is-anchor" : "",
                  overId && overId === item.id ? "is-over" : "",
                  dragId && dragId === item.id ? "is-drag" : "",
                ]
                  .filter(Boolean)
                  .join(" ")}
                draggable={movable}
                onDragStart={(event) => {
                  if (!movable || !item.id || (event.target instanceof Element && event.target.closest(".ant-queue-remove"))) {
                    event.preventDefault();
                    return;
                  }
                  event.dataTransfer.effectAllowed = "move";
                  event.dataTransfer.setData("text/plain", item.id);
                  setDragId(item.id);
                }}
                onDragEnd={() => {
                  setDragId(null);
                  setOverId(null);
                }}
                onDragOver={(event) => {
                  if (!movable && !fromLibrary(event)) return;
                  event.preventDefault();
                  event.stopPropagation();
                  event.dataTransfer.dropEffect = fromLibrary(event) ? "copy" : "move";
                  setDropEnd(false);
                  if (item.id && dragId !== item.id) setOverId(item.id);
                }}
                onDragLeave={() => {
                  if (item.id && overId === item.id) setOverId(null);
                }}
                onDrop={(event) => {
                  event.preventDefault();
                  event.stopPropagation();
                  setOverId(null);
                  setDropEnd(false);
                  const hit = libraryHit(event);
                  if (hit) {
                    setDragId(null);
                    onInsertHit(hit, item.id ?? null);
                    return;
                  }
                  const from = event.dataTransfer.getData("text/plain") || dragId;
                  setDragId(null);
                  if (from && item.id && movable) move(from, item.id);
                }}
              >
                <span className="ant-queue-n">
                  <span aria-hidden="true">{index + 1}</span>
                  <span className="ui-visually-hidden">{index === 0 ? "Ensuite" : `Position ${index + 1}`}</span>
                </span>
                <time className="ant-queue-at" dateTime={item.at}>
                  {airAt}
                </time>
                {movable ? (
                  <button
                    type="button"
                    className="ant-queue-grip"
                    aria-label={`Déplacer ${copy.title} : flèches haut et bas`}
                    title="Glisse, ou flèches haut et bas"
                    onKeyDown={(event) => item.id && nudge(event, item.id)}
                  >
                    <GripVertical size={15} aria-hidden="true" />
                  </button>
                ) : (
                  <span
                    className="ant-queue-lock"
                    title={anchored ? "Ancre d’horloge : ne bouge pas" : "C’est le prochain : il ne bouge plus"}
                  >
                    {anchored ? (
                      <span className="ant-queue-anchor">
                        {item.minute != null ? `:${String(item.minute).padStart(2, "0")}` : "ancre"}
                      </span>
                    ) : (
                      <Lock size={13} aria-hidden="true" />
                    )}
                    <span className="ui-visually-hidden">verrouillé</span>
                  </span>
                )}
                <span className="ant-queue-copy">
                  <span className={`ant-kind is-${kind}`} aria-hidden="true" />
                  <span className="ant-queue-title">{copy.title || "—"}</span>
                  {copy.artist ? <span className="ant-queue-artist">{copy.artist}</span> : null}
                </span>
                <span className="ant-queue-dur">{mmss(item.duration || 0)}</span>
                {locked ? (
                  <span aria-hidden="true" />
                ) : (
                  <button
                    type="button"
                    className="ant-queue-remove"
                    aria-label={`Retirer ${copy.title} de la file`}
                    title="Retirer de la file"
                    onClick={() => onRemove(item)}
                  >
                    <X size={15} aria-hidden="true" />
                  </button>
                )}
              </li>
            );
          })}
        </ol>
      ) : (
        <div className="ant-empty">
          <strong>Rien à la suite.</strong>
          <span>Choisis un titre dans la bibliothèque : il se place ici.</span>
        </div>
      )}

      <footer className="ant-panel-foot">
        <span>{hidden > 0 ? `+ ${hidden} plus loin` : ""}</span>
        <Link to="/conducteur" className="ant-link">
          Tout le conducteur
          <ArrowRight size={14} aria-hidden="true" />
        </Link>
      </footer>
    </section>
  );
}
