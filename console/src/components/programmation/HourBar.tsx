import { useState, type MouseEvent } from "react";
import { minuteMark, stepKindLabel, stepsSummary } from "../../api/programmationView";
import type { Clock } from "../../api/types";

const MARKS = [0, 10, 20, 30, 40, 50, 60];

/**
 * The hour at a glance: the cuts pinned to their minute, the steps looping in between.
 * A click on a free minute adds a cut there; a pin leads to its cut below.
 */
export function HourBar({
  clock,
  onAddCut,
  onShowCut,
}: {
  clock: Clock;
  onAddCut: (minute: number) => void;
  onShowCut: (minute: number) => void;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const taken = new Set(clock.anchors.map((row) => row.minute ?? -1));
  const cuts = [...clock.anchors].sort((a, b) => (a.minute ?? 0) - (b.minute ?? 0));

  const minuteAt = (event: MouseEvent<HTMLElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    return Math.max(0, Math.min(59, Math.round(((event.clientX - rect.left) / Math.max(rect.width, 1)) * 60)));
  };

  return (
    <div className="prog-hour">
      <div
        className="prog-hour-track"
        onMouseMove={(event) => setHover(minuteAt(event))}
        onMouseLeave={() => setHover(null)}
        onClick={(event) => {
          if (event.target !== event.currentTarget && !(event.target as HTMLElement).closest(".prog-hour-loop")) return;
          const minute = minuteAt(event);
          if (!taken.has(minute)) onAddCut(minute);
        }}
      >
        <span className="prog-hour-loop" aria-hidden="true">
          {clock.motif.length ? `${stepsSummary(clock)}, en boucle` : "Aucune étape"}
        </span>
        {hover != null && !taken.has(hover) ? (
          <span className="prog-hour-ghost" style={{ left: `${(hover / 60) * 100}%` }} aria-hidden="true">
            + {minuteMark(hover)}
          </span>
        ) : null}
        {cuts.map((cut) => {
          const minute = cut.minute ?? 0;
          return (
            <button
              key={minute}
              type="button"
              className={`prog-hour-pin is-${cut.kind}${minute > 52 ? " is-end" : ""}`}
              style={{ left: `${(minute / 60) * 100}%` }}
              aria-label={`Coupure ${minuteMark(minute)}, ${stepKindLabel(cut.kind)}`}
              onClick={() => onShowCut(minute)}
            >
              <span>
                {minuteMark(minute)} {stepKindLabel(cut.kind)}
              </span>
            </button>
          );
        })}
      </div>
      <div className="prog-hour-scale" aria-hidden="true">
        {MARKS.map((mark) => (
          <span key={mark} style={{ left: `${(mark / 60) * 100}%` }}>
            :{String(mark).padStart(2, "0")}
          </span>
        ))}
      </div>
    </div>
  );
}
