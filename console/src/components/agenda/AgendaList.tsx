import { CalendarOff, CalendarX2, Disc3, Mic } from "lucide-react";
import type { Diffusion, TodoLine, WeeklyOccurrence } from "../../api/agenda";
import { dayLongLabel, statusOf, timeLabel, upcomingByDay } from "../../api/agendaView";

/** « À venir »: day by day, dated broadcasts and the weekly shows around them. */
export function AgendaList({
  today,
  diffusions,
  weekly,
  todo,
  onlyTodo,
  onOpen,
  onOpenWeekly,
}: {
  today: string;
  diffusions: Diffusion[];
  weekly: WeeklyOccurrence[];
  todo: TodoLine[];
  onlyTodo: boolean;
  onOpen: (row: Diffusion) => void;
  onOpenWeekly: (row: WeeklyOccurrence, anchor: HTMLElement) => void;
}) {
  const todoById = new Map(todo.map((line) => [line.diffusion_id, line]));
  const groups = upcomingByDay(diffusions, weekly, {
    from: today,
    onlyTodo: onlyTodo ? new Set(todoById.keys()) : undefined,
  });

  if (!groups.length) {
    return (
      <div className="ag-empty">
        <span className="ag-empty-icon" aria-hidden="true">
          <CalendarX2 size={20} />
        </span>
        <p>{onlyTodo ? "Rien à préparer pour les sept prochains jours." : "Aucune émission datée à venir."}</p>
      </div>
    );
  }

  return (
    <div className="ag-list">
      {groups.map((group) => (
        <section key={group.day} className="ag-list-day" aria-label={dayLongLabel(group.day)}>
          <h3 className={group.day === today ? "is-today" : undefined}>
            {group.day === today ? "Aujourd'hui · " : ""}
            {dayLongLabel(group.day)}
          </h3>
          <ol>
            {group.entries.map((entry) => {
              if (entry.type === "weekly") {
                const row = entry.row;
                return (
                  <li key={`w-${row.emission_id}-${row.date}`}>
                    <button
                      type="button"
                      className={`ag-row is-weekly${row.cancelled ? " is-cancelled" : ""}`}
                      onClick={(event) => onOpenWeekly(row, event.currentTarget)}
                    >
                      <span className="ag-row-time">
                        {timeLabel(row.starts_at)} → {timeLabel(row.ends_at)}
                      </span>
                      <span className="ag-row-main">
                        <strong>{row.title}</strong>
                        <small>{row.cancelled ? "Émission hebdo, annulée ce jour" : "Émission hebdo"}</small>
                      </span>
                      {row.cancelled ? <CalendarOff size={15} aria-hidden="true" className="ag-row-icon" /> : null}
                    </button>
                  </li>
                );
              }
              const row = entry.row;
              const status = statusOf(row);
              const line = todoById.get(row.id);
              return (
                <li key={`d-${row.id}`}>
                  <button type="button" className={`ag-row is-${row.kind}`} onClick={() => onOpen(row)}>
                    <span className="ag-row-time">
                      {timeLabel(row.starts_at)} → {timeLabel(row.ends_at)}
                    </span>
                    <span className="ag-row-main">
                      <strong>
                        {row.kind === "live" ? <Mic size={13} aria-hidden="true" /> : <Disc3 size={13} aria-hidden="true" />}
                        {row.title}
                      </strong>
                      <small>
                        {row.kind === "live" ? "Direct" : "Set"}
                        {row.guest?.name || row.host_username ? ` · ${row.guest?.name || row.host_username}` : ""}
                        {status.detail ? ` · ${status.detail}` : ""}
                        {line?.rule === "link_unopened" ? " · lien jamais ouvert" : ""}
                      </small>
                    </span>
                    <span className={`ag-chip tone-${status.tone}`}>{status.label}</span>
                  </button>
                </li>
              );
            })}
          </ol>
        </section>
      ))}
    </div>
  );
}
