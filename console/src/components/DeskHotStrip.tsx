import { Text } from "@radix-ui/themes";
import { Plus, X } from "lucide-react";
import { useState } from "react";
import { formatMmSs } from "../lib/parisClock";
import { LIBRARY_DRAG_MIME, type LibraryHit } from "../api/library";
import { PAD_DRAG_MIME, padCaption, type EnginePad, type PadSlot } from "../api/liveMap";

export function DeskHotStrip({
  jingles,
  onAirId,
  firedId,
  editing,
  fireDisabled = false,
  onEditingChange,
  onFire,
  onDropHit,
  onSwap,
  onUnslot,
  onRank,
}: {
  jingles: PadSlot[];
  onAirId?: string;
  firedId?: string | null;
  editing: boolean;
  fireDisabled?: boolean;
  onEditingChange: (value: boolean) => void;
  onFire: (pad: EnginePad) => void;
  onDropHit: (kind: "jingle" | "pub", slotIndex: number, hit: LibraryHit) => void;
  onSwap: (kind: "jingle" | "pub", fromSoundId: number, toSoundId: number) => void;
  onUnslot: (pad: EnginePad) => void;
  onRank: (kind: "jingle" | "pub", soundId: number, slotIndex: number) => void;
}) {
  return (
    <section className={`desk-hot${editing ? " is-editing" : ""}`} aria-label="Idents">
      <header className="desk-hot-toolbar">
        <Text size="2" weight="medium">
          Idents
        </Text>
        <button
          type="button"
          className={`desk-hot-edit${editing ? " is-active" : ""}`}
          aria-pressed={editing}
          onClick={() => onEditingChange(!editing)}
        >
          Régler
        </button>
      </header>
      <HotRow
        label=""
        slots={jingles}
        kind="jingle"
        editing={editing}
        fireDisabled={fireDisabled}
        onAirId={onAirId}
        firedId={firedId}
        onFire={onFire}
        onDropHit={onDropHit}
        onSwap={onSwap}
        onUnslot={onUnslot}
        onRank={onRank}
      />
    </section>
  );
}

function HotRow({
  label,
  slots,
  kind,
  editing,
  fireDisabled = false,
  onAirId,
  firedId,
  onFire,
  onDropHit,
  onSwap,
  onUnslot,
  onRank,
}: {
  label: string;
  slots: PadSlot[];
  kind: "jingle" | "pub";
  editing: boolean;
  fireDisabled?: boolean;
  onAirId?: string;
  firedId?: string | null;
  onFire: (pad: EnginePad) => void;
  onDropHit: (kind: "jingle" | "pub", slotIndex: number, hit: LibraryHit) => void;
  onSwap: (kind: "jingle" | "pub", fromSoundId: number, toSoundId: number) => void;
  onUnslot: (pad: EnginePad) => void;
  onRank: (kind: "jingle" | "pub", soundId: number, slotIndex: number) => void;
}) {
  const [overSlot, setOverSlot] = useState<number | null>(null);

  return (
    <div className={`desk-hot-row is-${kind}`}>
      {label ? (
        <Text size="1" weight="medium" className="desk-hot-label">
          {label}
        </Text>
      ) : null}
      <div className="desk-hot-pads">
        {slots.map((slot, index) => {
          const pad = slot.pad;
          const caption = pad ? padCaption(pad.title) : null;
          const onAir = pad?.id === onAirId;
          const fired = pad?.id === firedId;
          return (
            <div
              key={`${kind}-${slot.slot}`}
              className={`desk-hot-slot${overSlot === index ? " is-drop" : ""}${editing ? " is-editing" : ""}`}
              onDragOver={(event) => {
                if (!editing || !slot.cartId) return;
                const types = Array.from(event.dataTransfer.types);
                if (!types.includes(LIBRARY_DRAG_MIME) && !types.includes(PAD_DRAG_MIME)) return;
                event.preventDefault();
                event.dataTransfer.dropEffect = types.includes(LIBRARY_DRAG_MIME) ? "copy" : "move";
                setOverSlot(index);
              }}
              onDragLeave={() => {
                if (overSlot === index) setOverSlot(null);
              }}
              onDrop={(event) => {
                event.preventDefault();
                setOverSlot(null);
                if (!editing || !slot.cartId) return;
                const library = event.dataTransfer.getData(LIBRARY_DRAG_MIME);
                if (library) {
                  try {
                    onDropHit(kind, index, JSON.parse(library) as LibraryHit);
                  } catch {
                    /* ignore */
                  }
                  return;
                }
                const raw = event.dataTransfer.getData(PAD_DRAG_MIME);
                if (!raw) return;
                try {
                  const from = JSON.parse(raw) as EnginePad;
                  if (from.kind !== kind) return;
                  if (pad && from.soundId !== pad.soundId) {
                    onSwap(kind, from.soundId, pad.soundId);
                  } else if (!pad) {
                    onRank(kind, from.soundId, index);
                  }
                } catch {
                  /* ignore */
                }
              }}
            >
              {pad ? (
                <button
                  type="button"
                  className={`desk-hot-btn is-${kind}${onAir ? " is-onair" : ""}${fired ? " is-fired" : ""}`}
                  disabled={fireDisabled}
                  draggable={editing}
                  onDragStart={(event) => {
                    if (!editing) {
                      event.preventDefault();
                      return;
                    }
                    event.dataTransfer.effectAllowed = "move";
                    event.dataTransfer.setData(PAD_DRAG_MIME, JSON.stringify(pad));
                  }}
                  onClick={() => {
                    if (!fireDisabled) onFire(pad);
                  }}
                  title={
                    fireDisabled
                      ? "Direct à l’antenne"
                      : `${index + 1}. ${caption?.artist ? `${caption.artist} — ` : ""}${caption?.title ?? ""}`
                  }
                >
                  <span className="desk-hot-n">{index + 1}</span>
                  <span className="desk-hot-copy">
                    <span className="desk-hot-title">{caption?.title}</span>
                    {caption?.artist ? <span className="desk-hot-artist">{caption.artist}</span> : null}
                  </span>
                  <span className="desk-hot-dur">{formatMmSs(pad.durationSec || 0)}</span>
                </button>
              ) : (
                <button
                  type="button"
                  className={`desk-hot-btn desk-hot-btn--empty is-${kind}`}
                  disabled={!editing}
                  title={editing ? "Glisse un titre ici" : "Slot vide"}
                >
                  <span className="desk-hot-n">{index + 1}</span>
                  <span className="desk-hot-copy">
                    <span className="desk-hot-title">{editing ? "Vide" : "—"}</span>
                    {editing ? (
                      <span className="desk-hot-artist">
                        <Plus size={12} /> drop
                      </span>
                    ) : null}
                  </span>
                </button>
              )}
              {editing && pad ? (
                <button
                  type="button"
                  className="desk-hot-unslot"
                  aria-label={`Retirer ${caption?.title ?? "le pad"} du pupitre`}
                  onClick={(event) => {
                    event.stopPropagation();
                    onUnslot(pad);
                  }}
                >
                  <X size={12} />
                </button>
              ) : null}
            </div>
          );
        })}
      </div>
    </div>
  );
}
