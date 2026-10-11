import { GripVertical, Lock, X } from "lucide-react";
import { useState, type DragEvent } from "react";
import { formatMmSs, parisParts } from "../lib/parisClock";
import { LIBRARY_DRAG_MIME, type LibraryHit } from "../api/library";
import {
  DESK_FILE_AHEAD,
  partitionRundown,
  queueItemKey,
  queueItemLocked,
  rundownCopy,
} from "../api/rundownLive";
import type { LiveSnapshot, Rundown, RundownItem } from "../api/types";

export function DeskFile({
  rundown,
  live,
  wall,
  selectedId,
  onSelect,
  onRemove,
  onReorder,
  onInsertHit,
}: {
  rundown: Rundown | null;
  live: LiveSnapshot | null;
  wall: Date;
  selectedId: string | null;
  onSelect: (item: RundownItem) => void;
  onRemove: (item: RundownItem) => void;
  onReorder: (ids: string[]) => void;
  onInsertHit: (hit: LibraryHit, beforeId: string | null) => void;
}) {
  const parts = rundown ? partitionRundown(rundown.items, wall, live) : null;
  const onAir = parts?.onAir ?? null;
  const upcomingAll = parts?.upcoming ?? [];
  const upcoming = upcomingAll.slice(0, DESK_FILE_AHEAD);
  const hidden = upcomingAll.length - upcoming.length;
  const [dragId, setDragId] = useState<string | null>(null);
  const [overId, setOverId] = useState<string | null>(null);
  const empty = upcoming.length === 0;

  const movableOrder = () =>
    upcoming
      .filter((item) => item.id && !queueItemLocked(item, onAir?.id))
      .map((item) => item.id as string);

  const libraryHit = (event: DragEvent) => {
    const raw = event.dataTransfer.getData(LIBRARY_DRAG_MIME);
    if (!raw) return null;
    try {
      const hit = JSON.parse(raw) as LibraryHit;
      return hit?.path ? hit : null;
    } catch {
      return null;
    }
  };

  const allowLibrary = (event: DragEvent) =>
    event.dataTransfer.types.includes(LIBRARY_DRAG_MIME);

  return (
    <section
      className="panel"
      aria-labelledby="file-title"
      data-queue={empty ? "empty" : "full"}
      onDragOver={(event) => {
        if (!allowLibrary(event)) return;
        event.preventDefault();
        event.dataTransfer.dropEffect = "copy";
      }}
      onDrop={(event) => {
        const hit = libraryHit(event);
        if (!hit) return;
        event.preventDefault();
        setOverId(null);
        onInsertHit(hit, null);
      }}
    >
      <header className="panel-head">
        <h2 id="file-title">File</h2>
        {rundown?.clock ? <span className="chip">{rundown.clock}</span> : null}
      </header>
      <ol className="queue">
        {upcoming.map((item, index) => {
          const locked = queueItemLocked(item, onAir?.id);
          const movable = Boolean(item.id) && !locked;
          const copy = rundownCopy(item);
          const rowKey = queueItemKey(item, index);
          const selected = selectedId === rowKey || selectedId === item.id;
          const startMs = Number.isFinite(Date.parse(item.at)) ? Date.parse(item.at) : Number.NaN;
          const airAt = Number.isFinite(startMs) ? parisParts(new Date(startMs)).clock : "—";
          const anchored = item.when === "anchored";
          const lockTitle = anchored ? "Verrouillé : ancre" : "Verrouillé : c’est le prochain";
          return (
            <li
              key={rowKey}
              className={`${index === 0 ? "is-next" : ""}${selected ? " is-selected" : ""}${
                movable ? " is-movable" : ""
              }${overId === item.id ? " is-drop" : ""}${dragId === item.id ? " is-drag" : ""}`}
              draggable={movable}
              title={movable ? "Glisse la ligne pour changer l’ordre" : undefined}
              onClick={() => onSelect(item)}
              onDragStart={(event) => {
                const target = event.target;
                if (
                  !movable ||
                  !item.id ||
                  (target instanceof Element && target.closest(".q-remove"))
                ) {
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
                if (!movable && !allowLibrary(event)) return;
                event.preventDefault();
                event.dataTransfer.dropEffect = allowLibrary(event) ? "copy" : "move";
                if (item.id && dragId !== item.id) setOverId(item.id);
              }}
              onDragLeave={() => {
                if (item.id && overId === item.id) setOverId(null);
              }}
              onDrop={(event) => {
                event.preventDefault();
                event.stopPropagation();
                setOverId(null);
                const hit = libraryHit(event);
                if (hit) {
                  setDragId(null);
                  onInsertHit(hit, item.id ?? null);
                  return;
                }
                const from = event.dataTransfer.getData("text/plain") || dragId;
                setDragId(null);
                if (!from || !item.id || from === item.id || !movable) return;
                const ids = movableOrder();
                const fromIndex = ids.indexOf(from);
                const toIndex = ids.indexOf(item.id);
                if (fromIndex < 0) return;
                const next = ids.filter((id) => id !== from);
                const insertAt = toIndex < 0 ? next.length : next.indexOf(item.id);
                next.splice(Math.max(0, insertAt), 0, from);
                onReorder(next);
              }}
            >
              <span className="q-n">{index === 0 ? "N" : index + 1}</span>
              <time className="q-until" dateTime={item.at}>
                {airAt}
              </time>
              {anchored ? (
                <span className="q-mark">
                  <span className="q-anchor" title="Ancre d’horloge">
                    {item.minute != null ? `:${String(item.minute).padStart(2, "0")}` : "Ancre"}
                  </span>
                </span>
              ) : movable ? (
                <span className="q-mark q-grip" aria-hidden="true">
                  <GripVertical aria-hidden="true" />
                </span>
              ) : locked ? (
                <span className="q-mark q-lock" title={lockTitle}>
                  <Lock aria-hidden="true" />
                  <span className="visually-hidden">Verrouillé</span>
                </span>
              ) : (
                <span className="q-mark" />
              )}
              <span className="q-copy">
                <span className="t">{copy.title || "—"}</span>
                {copy.artist ? <span className="a">{copy.artist}</span> : null}
              </span>
              <span className="q-dur">{formatMmSs(item.duration || 0)}</span>
              {!locked ? (
                <button
                  type="button"
                  className="q-remove"
                  aria-label={`Retirer ${copy.title}`}
                  onClick={(event) => {
                    event.stopPropagation();
                    onRemove(item);
                  }}
                >
                  <X aria-hidden="true" />
                </button>
              ) : anchored ? (
                <span className="q-mark q-lock" title="Verrouillé : ancre">
                  <Lock aria-hidden="true" />
                  <span className="visually-hidden">Verrouillé</span>
                </span>
              ) : (
                <span />
              )}
            </li>
          );
        })}
      </ol>
      <div className="queue-empty">
        <strong>Rien à la suite.</strong>
        Cherche un titre dans la bibliothèque et touche-le : il se met ici.
      </div>
      {hidden > 0 ? (
        <footer className="panel-foot q-foot">encore {hidden} dans le conducteur</footer>
      ) : null}
    </section>
  );
}
