import { CalendarOff, Mic, Disc3 } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";
import type { Diffusion, WeeklyOccurrence } from "../../api/agenda";
import {
  dayShortLabel,
  hhmm,
  minuteAt,
  parisWall,
  segments,
  snap,
  statusOf,
  STEP_MINUTES,
} from "../../api/agendaView";
import type { Run } from "../../api/programmationView";

const HOUR_PX = 44;
const DAY_PX = HOUR_PX * 24;
const DRAG_THRESHOLD = 4;

type DragState =
  | { mode: "create"; day: string; anchor: number; current: number; moved: boolean }
  | {
      mode: "move";
      row: Diffusion;
      grabOffset: number;
      day: string;
      start: number;
      moved: boolean;
      originX: number;
      originY: number;
    }
  | { mode: "resize"; row: Diffusion; day: string; start: number; end: number; moved: boolean };

export type AgendaWeekProps = {
  days: string[];
  today: string;
  nowMinute: number;
  diffusions: Diffusion[];
  weekly: WeeklyOccurrence[];
  runs: Run[];
  tints: Map<number, string>;
  todoIds: Set<number>;
  editable: boolean;
  onCreate: (day: string, start: number, end: number) => void;
  onOpen: (row: Diffusion) => void;
  onOpenWeekly: (row: WeeklyOccurrence, anchor: HTMLElement) => void;
  onMove: (row: Diffusion, day: string, start: number) => void;
  onResize: (row: Diffusion, day: string, end: number) => void;
};

const px = (minute: number) => `${(minute / 60) * HOUR_PX}px`;

function columnAt(clientX: number, columns: Map<string, HTMLDivElement>): string | null {
  for (const [day, element] of columns) {
    const rect = element.getBoundingClientRect();
    if (clientX >= rect.left && clientX < rect.right) return day;
  }
  return null;
}

function offsetIn(element: HTMLElement, clientY: number): number {
  return clientY - element.getBoundingClientRect().top;
}

/** The week of the Agenda: heure types underneath, weekly shows dashed, dated broadcasts on top. */
export function AgendaWeek({
  days,
  today,
  nowMinute,
  diffusions,
  weekly,
  runs,
  tints,
  todoIds,
  editable,
  onCreate,
  onOpen,
  onOpenWeekly,
  onMove,
  onResize,
}: AgendaWeekProps) {
  const frameRef = useRef<HTMLDivElement>(null);
  const columns = useRef(new Map<string, HTMLDivElement>());
  const [drag, setDrag] = useState<DragState | null>(null);
  const dragRef = useRef<DragState | null>(null);
  dragRef.current = drag;
  // A drag ends with a click on the block: it must not open the dialog too.
  const suppressClick = useRef(false);

  // Open on the evening, or on the current hour when today is shown.
  useEffect(() => {
    const frame = frameRef.current;
    if (!frame) return;
    const focus = days.includes(today) ? Math.max(0, nowMinute - 90) : 17 * 60;
    frame.scrollTop = (focus / 60) * HOUR_PX;
    // The week changes: same evening view.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [days[0]]);

  const pieces = useMemo(() => {
    const byDay = new Map<string, Array<{ row: Diffusion; start: number; end: number; first: boolean; last: boolean }>>();
    for (const row of diffusions) {
      for (const segment of segments(row.starts_at, row.ends_at)) {
        const list = byDay.get(segment.day) ?? [];
        list.push({ row, start: segment.start, end: segment.end, first: segment.first, last: segment.last });
        byDay.set(segment.day, list);
      }
    }
    return byDay;
  }, [diffusions]);

  const weeklyByDay = useMemo(() => {
    const byDay = new Map<string, Array<{ row: WeeklyOccurrence; start: number; end: number }>>();
    for (const row of weekly) {
      for (const segment of segments(row.starts_at, row.ends_at)) {
        const list = byDay.get(segment.day) ?? [];
        list.push({ row, start: segment.start, end: segment.end });
        byDay.set(segment.day, list);
      }
    }
    return byDay;
  }, [weekly]);

  useEffect(() => {
    if (!drag) return;
    const move = (event: PointerEvent) => {
      const state = dragRef.current;
      if (!state) return;
      if (state.mode === "create") {
        const column = columns.current.get(state.day);
        if (!column) return;
        const current = minuteAt(offsetIn(column, event.clientY), DAY_PX);
        setDrag({ ...state, current, moved: state.moved || Math.abs(current - state.anchor) >= STEP_MINUTES });
        return;
      }
      if (state.mode === "move") {
        const moved =
          state.moved ||
          Math.abs(event.clientX - state.originX) > DRAG_THRESHOLD ||
          Math.abs(event.clientY - state.originY) > DRAG_THRESHOLD;
        const day = columnAt(event.clientX, columns.current) ?? state.day;
        const column = columns.current.get(day);
        if (!column) return;
        const pointer = (offsetIn(column, event.clientY) / DAY_PX) * 1440;
        const start = Math.max(0, Math.min(1440 - STEP_MINUTES, snap(pointer - state.grabOffset)));
        setDrag({ ...state, day, start, moved });
        return;
      }
      const column = columns.current.get(state.day);
      if (!column) return;
      const end = Math.max(state.start + STEP_MINUTES, minuteAt(offsetIn(column, event.clientY), DAY_PX));
      setDrag({ ...state, end, moved: true });
    };
    const up = () => {
      const state = dragRef.current;
      setDrag(null);
      if (!state) return;
      if (state.mode === "create") {
        if (state.moved) {
          const start = Math.min(state.anchor, state.current);
          const end = Math.max(state.anchor, state.current);
          onCreate(state.day, start, Math.max(end, start + STEP_MINUTES));
        } else {
          const start = Math.min(1440 - 60, Math.floor(state.anchor / 30) * 30);
          onCreate(state.day, start, start + 60);
        }
        return;
      }
      if (!state.moved) return;
      suppressClick.current = true;
      window.setTimeout(() => {
        suppressClick.current = false;
      }, 0);
      if (state.mode === "move") {
        const from = parisWall(state.row.starts_at);
        if (from.day !== state.day || from.minute !== state.start) onMove(state.row, state.day, state.start);
        return;
      }
      onResize(state.row, state.day, state.end);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
    window.addEventListener("pointercancel", up);
    return () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      window.removeEventListener("pointercancel", up);
    };
  }, [drag != null, onCreate, onMove, onOpen, onResize]); // eslint-disable-line react-hooks/exhaustive-deps

  const startCreate = (day: string, event: ReactPointerEvent<HTMLDivElement>) => {
    if (!editable || event.button !== 0) return;
    if (event.target !== event.currentTarget && !(event.target as HTMLElement).dataset.under) return;
    event.preventDefault();
    const anchor = minuteAt(offsetIn(event.currentTarget, event.clientY), DAY_PX);
    setDrag({ mode: "create", day, anchor, current: anchor, moved: false });
  };

  const startMove = (
    row: Diffusion,
    day: string,
    start: number,
    first: boolean,
    event: ReactPointerEvent<HTMLElement>,
  ) => {
    event.stopPropagation();
    // Only the first day of a block moves; the rest opens it on click.
    if (event.button !== 0 || !first || !editable || row.air_status !== "upcoming") return;
    const column = columns.current.get(day);
    if (!column) return;
    const pointer = (offsetIn(column, event.clientY) / DAY_PX) * 1440;
    setDrag({
      mode: "move",
      row,
      grabOffset: pointer - start,
      day,
      start,
      moved: false,
      originX: event.clientX,
      originY: event.clientY,
    });
  };

  const startResize = (row: Diffusion, day: string, end: number, event: ReactPointerEvent<HTMLElement>) => {
    event.stopPropagation();
    event.preventDefault();
    const origin = parisWall(row.starts_at);
    if (origin.day !== day) return;
    setDrag({ mode: "resize", row, day, start: origin.minute, end, moved: false });
  };

  return (
    // Le cadre défile : il prend le focus, pour défiler au clavier même sans bloc à atteindre.
    <div className="ag-week-frame" ref={frameRef} role="region" aria-label="Semaine de l'agenda" tabIndex={0}>
      {/* Un tableau, pas une grille : rien ne s'y parcourt aux flèches. Chaque jour
          se lit sous son en-tête de colonne. */}
      <div className={`ag-week-grid${drag ? " is-dragging" : ""}`} role="table" aria-label="Semaine de l'agenda">
        <div className="ag-week-row" role="row">
          <div className="ag-week-corner" aria-hidden="true" />
          {days.map((day) => (
            <div key={day} className={`ag-day-head${day === today ? " is-today" : ""}`} role="columnheader">
              {dayShortLabel(day)}
            </div>
          ))}
        </div>
        <div className="ag-week-row" role="row">
          <div className="ag-gutter" aria-hidden="true" style={{ height: DAY_PX }}>
            {Array.from({ length: 24 }, (_, hour) => (
              <span key={hour} style={{ top: hour * HOUR_PX }}>
                {String(hour).padStart(2, "0")}:00
              </span>
            ))}
          </div>
          {days.map((day, index) => {
            const weekday = index;
            const dayRuns = runs.filter((run) => run.day === weekday);
            const blocks = pieces.get(day) ?? [];
            const shows = weeklyByDay.get(day) ?? [];
            const preview =
              drag && drag.day === day
                ? drag.mode === "create" && drag.moved
                  ? { start: Math.min(drag.anchor, drag.current), end: Math.max(drag.anchor, drag.current) }
                  : drag.mode === "move" && drag.moved
                    ? { start: drag.start, end: Math.min(1440, drag.start + drag.row.duration_min) }
                    : drag.mode === "resize"
                      ? { start: drag.start, end: drag.end }
                      : null
                : null;
            return (
              <div
                key={day}
                ref={(element) => {
                  if (element) columns.current.set(day, element);
                  else columns.current.delete(day);
                }}
                className={`ag-day${day === today ? " is-today" : ""}${day < today ? " is-past" : ""}`}
                style={{ height: DAY_PX }}
                role="cell"
                onPointerDown={(event) => startCreate(day, event)}
              >
                {dayRuns.map((run) => (
                  <div
                    key={`run-${run.start}`}
                    data-under="1"
                    className={`ag-run tint-${run.clockId != null ? (tints.get(run.clockId) ?? "gray") : "gray"}`}
                    style={{ top: px(run.start), height: px(run.end - run.start) }}
                    aria-hidden="true"
                  >
                    {run.end - run.start >= 90 ? <span data-under="1">{run.clockName}</span> : null}
                  </div>
                ))}
                {shows.map(({ row, start, end }) => (
                  <button
                    key={`weekly-${row.emission_id}-${start}`}
                    type="button"
                    className={`ag-weekly${row.cancelled ? " is-cancelled" : ""}${row.replaced_by != null ? " is-replaced" : ""}`}
                    style={{ top: px(start), height: px(Math.max(end - start, 20)) }}
                    title={`${row.title} · émission hebdo${row.cancelled ? " · annulée ce jour" : ""}${
                      row.replaced_by != null ? " · remplacée ce jour" : ""
                    }`}
                    // Le nom reprend ce que le bloc affiche, dans l'ordre.
                    aria-label={`Émission ${row.title}, ${hhmm(start)} → ${hhmm(end)}, ${
                      row.cancelled ? "annulée ce jour" : row.replaced_by != null ? "remplacée ce jour" : "hebdo"
                    }`}
                    onPointerDown={(event) => event.stopPropagation()}
                    onClick={(event) => onOpenWeekly(row, event.currentTarget)}
                  >
                    <span className="ag-block-name">
                      {row.cancelled ? <CalendarOff size={12} aria-hidden="true" /> : null}
                      {row.title}
                    </span>{" "}
                    <span className="ag-block-time">
                      {hhmm(start)} → {hhmm(end)} · {row.cancelled ? "annulée" : row.replaced_by != null ? "remplacée" : "hebdo"}
                    </span>
                  </button>
                ))}
                {blocks.map(({ row, start, end, first, last }) => {
                  const status = statusOf(row);
                  const dragging = drag && drag.mode !== "create" && drag.row.id === row.id && drag.moved;
                  const span = end - start;
                  // Three layouts by height: one line, two lines, the full card.
                  const size = span < 40 ? "is-xs" : span < 80 ? "is-sm" : "is-lg";
                  const who = row.guest?.name || row.host_username || "";
                  // Le nom reprend ce que le bloc affiche, dans l'ordre, puis l'heure.
                  const named = [
                    `${row.kind === "live" ? "Direct" : "Set"} ${row.title}${!first ? " (suite)" : ""}`,
                    status.label,
                    who,
                    `${hhmm(start)} à ${hhmm(end)}`,
                  ]
                    .filter(Boolean)
                    .join(", ");
                  return (
                    <button
                      key={`d-${row.id}-${day}`}
                      type="button"
                      className={`ag-block is-${row.kind} ${size} tone-${status.tone}${
                        dragging ? " is-ghosted" : ""
                      }${todoIds.has(row.id) ? " is-todo" : ""}${row.air_status !== "upcoming" ? " is-past" : ""}`}
                      style={{ top: px(start), height: px(Math.max(end - start, 18)) }}
                      aria-label={named}
                      title={[row.title, who, status.label, status.detail]
                        .filter(Boolean)
                        .join(" · ")}
                      onPointerDown={(event) => startMove(row, day, start, first, event)}
                      onClick={() => {
                        if (!suppressClick.current) onOpen(row);
                      }}
                    >
                      <span className="ag-block-name">
                        {row.kind === "live" ? <Mic size={12} aria-hidden="true" /> : <Disc3 size={12} aria-hidden="true" />}
                        <span className="ag-block-text">
                          {row.title}
                          {!first ? " (suite)" : ""}
                        </span>
                      </span>{" "}
                      <span className="ag-block-meta">
                        <span className={`ag-chip tone-${status.tone}`}>{status.label}</span>{" "}
                        <span className="ag-block-who">{who}</span>
                      </span>
                      {editable && last && row.air_status === "upcoming" ? (
                        <span
                          className="ag-block-resize"
                          aria-hidden="true"
                          onPointerDown={(event) => startResize(row, day, end, event)}
                        />
                      ) : null}
                    </button>
                  );
                })}
                {preview ? (
                  <div
                    className={`ag-preview${drag?.mode === "create" ? " is-create" : ""}`}
                    style={{ top: px(preview.start), height: px(Math.max(preview.end - preview.start, STEP_MINUTES)) }}
                    aria-hidden="true"
                  >
                    {hhmm(preview.start)} → {hhmm(preview.end)}
                  </div>
                ) : null}
                {day === today ? <span className="ag-now-line" style={{ top: px(nowMinute) }} aria-hidden="true" /> : null}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
