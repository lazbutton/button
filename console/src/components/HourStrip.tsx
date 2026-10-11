import { Text, Tooltip } from "@radix-ui/themes";
import { MousePointer2, Repeat2 } from "lucide-react";
import { useState, type KeyboardEvent, type MouseEvent } from "react";
import { fillBands, KIND_ORDER, kindLabel, sourceLabel, stepHeadline } from "../api/clockMeta";
import type { Clock } from "../api/types";

export type StudioSelection =
  | { kind: "idle" }
  | { kind: "motif"; index: number }
  | { kind: "anchor"; minute: number }
  | { kind: "new-anchor"; minute: number };

const MARKS = ["00", "10", "20", "30", "40", "50", "60"] as const;
const MAJOR = new Set(["00", "20", "40", "60"]);
const TICKS = Array.from({ length: 61 }, (_, minute) => minute);

export function padMinute(minute: number): string {
  return String(minute).padStart(2, "0");
}

function pickMinute(event: MouseEvent<HTMLElement>) {
  const rect = event.currentTarget.getBoundingClientRect();
  const ratio = (event.clientX - rect.left) / Math.max(rect.width, 1);
  return Math.max(0, Math.min(59, Math.round(ratio * 60)));
}

export function ClockSpark({ clock }: { clock: Clock }) {
  const bands = fillBands(clock.anchors);
  return (
    <span className="clock-spark" aria-hidden="true">
      {bands.map((band) => (
        <span
          key={`${band.start}-${band.end}`}
          className="clock-spark-fill"
          style={{
            left: `${(band.start / 60) * 100}%`,
            width: `${((band.end - band.start) / 60) * 100}%`,
          }}
        />
      ))}
      {clock.anchors.map((anchor) => (
        <span
          key={anchor.minute}
          className={`clock-spark-pin hour-dot--${anchor.kind}`}
          style={{ left: `${((anchor.minute ?? 0) / 60) * 100}%` }}
        />
      ))}
    </span>
  );
}

export function HourStrip({
  clock,
  selection,
  fillMotifIndex,
  onSelect,
}: {
  clock: Clock;
  selection: StudioSelection;
  fillMotifIndex: number;
  onSelect: (next: StudioSelection) => void;
}) {
  const bands = fillBands(clock.anchors);
  const fillSelected = selection.kind === "motif";
  const [hover, setHover] = useState<number | null>(null);
  const ghost =
    hover ?? (selection.kind === "new-anchor" || selection.kind === "anchor" ? selection.minute : null);

  const onRulerClick = (event: MouseEvent<HTMLElement>) => {
    const keyboardClick = event.detail === 0 && event.clientX === 0 && event.clientY === 0;
    const minute = keyboardClick ? (ghost ?? 0) : pickMinute(event);
    const existing = clock.anchors.some((row) => row.minute === minute);
    onSelect(existing ? { kind: "anchor", minute } : { kind: "new-anchor", minute });
  };

  const chooseMinute = (minute: number) => {
    const safeMinute = Math.max(0, Math.min(59, minute));
    const existing = clock.anchors.some((row) => row.minute === safeMinute);
    onSelect(
      existing
        ? { kind: "anchor", minute: safeMinute }
        : { kind: "new-anchor", minute: safeMinute },
    );
  };

  const onRulerKeyDown = (event: KeyboardEvent<HTMLButtonElement>) => {
    const current = ghost ?? 0;
    if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
      event.preventDefault();
      const next = Math.max(0, Math.min(59, current + (event.key === "ArrowLeft" ? -1 : 1)));
      setHover(next);
      return;
    }
    if (event.key === "Home" || event.key === "End") {
      event.preventDefault();
      setHover(event.key === "Home" ? 0 : 59);
      return;
    }
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      chooseMinute(current);
    }
  };

  return (
    <div className="hour-strip" aria-label={`Heure type « ${clock.name} », 0 à 60 minutes`}>
      <button
        type="button"
        className="hour-ruler"
        aria-label="Réglet : cliquer une minute pour poser une coupure à la minute"
        onMouseMove={(event) => setHover(pickMinute(event))}
        onMouseLeave={() => setHover(null)}
        onClick={onRulerClick}
        onKeyDown={onRulerKeyDown}
      >
        <span className="hour-ruler-caption">
          <MousePointer2 size={12} aria-hidden="true" />
          Poser une coupure à la minute
        </span>
        {TICKS.map((minute) => (
          <span
            key={minute}
            className={`hour-tick${minute % 10 === 0 ? " is-major" : ""}`}
            style={{ left: `${(minute / 60) * 100}%` }}
            aria-hidden="true"
          />
        ))}
        {MARKS.map((label) => (
          <span
            key={label}
            className={`hour-label${MAJOR.has(label) ? " is-major" : ""}${label === "00" ? " is-start" : ""}${label === "60" ? " is-end" : ""}`}
            style={{ left: `${(Number(label) / 60) * 100}%` }}
          >
            :{label}
          </span>
        ))}
        {hover != null ? (
          <span className="hour-hover-min" style={{ left: `${(hover / 60) * 100}%` }}>
            :{padMinute(hover)}
          </span>
        ) : null}
      </button>

      <div className="hour-track">
        {bands.map((band) => {
          const left = (band.start / 60) * 100;
          const width = ((band.end - band.start) / 60) * 100;
          return (
            <Tooltip
              key={`${band.start}-${band.end}`}
              content={`Ce qui passe :${padMinute(band.start)}–:${padMinute(band.end)} — ${clock.motif.map(stepHeadline).join(" → ") || "aucune étape"}`}
            >
              <button
                type="button"
                className={`hour-fill${fillSelected ? " is-selected" : ""}`}
                style={{ left: `${left}%`, width: `${width}%` }}
                aria-pressed={fillSelected}
                aria-label={`Ce qui passe, de :${padMinute(band.start)} à :${padMinute(band.end)}`}
                onClick={() =>
                  onSelect({
                    kind: "motif",
                    index: Math.min(fillMotifIndex, Math.max(clock.motif.length - 1, 0)),
                  })
                }
              >
                <span className="hour-fill-title">
                  <Repeat2 size={12} aria-hidden="true" />
                  {clock.motif.length
                    ? clock.motif.map((step) => sourceLabel(step)).join(" → ")
                    : "Ce qui passe"}
                </span>
                <span className="hour-fill-label">
                  :{padMinute(band.start)} → :{padMinute(band.end)}
                </span>
                {clock.motif.length ? (
                  <span className="hour-fill-dots">
                    {clock.motif.map((step, i) => (
                      <span
                        key={`${step.kind}-${i}`}
                        className="hour-fill-step"
                        title={stepHeadline(step)}
                      >
                        <span className={`hour-dot hour-dot--${step.kind}`} />
                        <span>{i + 1}</span>
                      </span>
                    ))}
                  </span>
                ) : (
                  <span className="hour-fill-empty">Aucune étape</span>
                )}
              </button>
            </Tooltip>
          );
        })}

        {ghost != null ? (
          <span
            className={`hour-ghost${selection.kind === "new-anchor" && hover == null ? " is-pending" : ""}`}
            style={{ left: `${(ghost / 60) * 100}%` }}
          >
            <span className="hour-ghost-label">:{padMinute(ghost)}</span>
          </span>
        ) : null}

        {clock.anchors.map((anchor) => {
          const minute = anchor.minute ?? 0;
          const selected =
            (selection.kind === "anchor" || selection.kind === "new-anchor") &&
            selection.minute === minute;
          return (
            <div
              key={minute}
              className={`hour-anchor hour-anchor--${anchor.kind}${minute < 5 ? " is-start" : ""}${minute > 55 ? " is-end" : ""}${selected ? " is-selected" : ""}`}
              style={{ left: `${(minute / 60) * 100}%` }}
            >
              <span className="hour-anchor-line" aria-hidden="true" />
              <Tooltip
                content={`${stepHeadline(anchor)} :${padMinute(minute)} · ${anchor.sync === "molle" ? "attend la fin du titre" : "coupe à l’heure pile"}`}
              >
                <button
                  type="button"
                  aria-pressed={selected}
                  aria-label={`Coupure à la minute, ${kindLabel(anchor.kind)}, à :${padMinute(minute)}`}
                  onClick={(event) => {
                    event.stopPropagation();
                    onSelect({ kind: "anchor", minute });
                  }}
                >
                  <span className={`hour-anchor-badge hour-dot--${anchor.kind}`}>
                    :{padMinute(minute)} {kindLabel(anchor.kind)}
                    {anchor.sync === "molle" ? " · attend la fin du titre" : " · coupe à l’heure pile"}
                  </span>
                </button>
              </Tooltip>
            </div>
          );
        })}
      </div>
      <div className="hour-strip-footer">
        <Text size="1" color="gray">
          Clique le réglet pour préparer une coupure à la minute · flèches puis Entrée au clavier
        </Text>
        <div className="hour-legend" aria-label="Légende des étapes">
          {KIND_ORDER.map((kind) => (
            <span key={kind}>
              <span className={`hour-dot hour-dot--${kind}`} aria-hidden="true" />
              {kindLabel(kind)}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}
