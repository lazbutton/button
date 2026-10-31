import { Button, DropdownMenu, IconButton } from "@radix-ui/themes";
import { CalendarDays, Clock3, MicVocal, Plus } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type MouseEvent } from "react";
import { Link } from "react-router-dom";
import { ChangeDialog, type ChangeTarget } from "../components/programmation/ChangeDialog";
import { EmissionDialog, type EmissionTarget } from "../components/programmation/EmissionDialog";
import { ProtoToast, useProtoToast } from "../components/ProtoToast";
import { apiDelete } from "../api/client";
import { errorText } from "../api/programmationErrors";
import {
  clockTints,
  DAY_LONG,
  DAY_SHORT,
  hhmm,
  nextRun,
  redundantSlotIds,
  runAt,
  spanLabel,
  weekRuns,
  type Run,
} from "../api/programmationView";
import { SessionGate } from "../api/SessionGate";
import type { ClocksResponse, Emission, EmissionsResponse, SlotsResponse } from "../api/types";
import { useApiJson } from "../api/useApiJson";
import { parisParts, parisWeekdayMon0, useParisNow } from "../lib/parisClock";
import "../styles/pages/programmation.css";

const POLL_MS = 10_000;
const HOURS = [0, 3, 6, 9, 12, 15, 18, 21, 24];

function weekDates(now: Date, today: number): string[] {
  return DAY_SHORT.map((_, index) => parisParts(new Date(now.getTime() + (index - today) * 86_400_000)).day);
}

const pct = (minute: number) => `${(Math.max(0, Math.min(1440, minute)) / 1440) * 100}%`;

/** Where in the day a click landed, to the half hour. */
function minuteAtClick(event: MouseEvent<HTMLElement>, start: number, end: number): number {
  const rect = event.currentTarget.getBoundingClientRect();
  const ratio = Math.max(0, Math.min(1, (event.clientY - rect.top) / Math.max(rect.height, 1)));
  return Math.round((start + ratio * (end - start)) / 30) * 30;
}

export function SemainePage() {
  const now = useParisNow();
  const slotsRes = useApiJson<SlotsResponse>("/autodj/slots.json", POLL_MS);
  const clocksRes = useApiJson<ClocksResponse>("/autodj/clocks.json", 30_000);
  const emissionsRes = useApiJson<EmissionsResponse>("/antenne/emissions.json", POLL_MS);
  const { message, show, dismiss } = useProtoToast();
  const [change, setChange] = useState<ChangeTarget | null>(null);
  const [emission, setEmission] = useState<EmissionTarget | null>(null);
  const slots = useMemo(() => slotsRes.data?.slots ?? [], [slotsRes.data]);
  const clocks = useMemo(
    () => [...(clocksRes.data?.clocks ?? [])].sort((a, b) => a.name.localeCompare(b.name, "fr")),
    [clocksRes.data],
  );
  const emissions = useMemo(
    () => (emissionsRes.data?.emissions ?? []).filter((row) => row.scope !== "session" && row.day_of_week != null),
    [emissionsRes.data],
  );
  const runs = useMemo(() => weekRuns(slots), [slots]);
  const tints = useMemo(() => clockTints(clocks), [clocks]);
  const parts = parisParts(now);
  const today = parisWeekdayMon0(now);
  const minuteOfDay = parts.hour * 60 + parts.minute;
  const [agendaDay, setAgendaDay] = useState(today);
  const current = runAt(runs, today, minuteOfDay);
  const upcoming = nextRun(runs, today, minuteOfDay);
  const dates = weekDates(now, today);
  const nextShow = emissionsRes.data?.next ?? null;
  const liveShow = emissionsRes.data?.current ?? null;
  const usedClocks = clocks.filter((clock) => runs.some((run) => run.clockId === clock.id));
  const mergeLock = useRef(false);
  const redundant = useMemo(() => redundantSlotIds(slots), [slots]);
  const showRef = useRef(show);
  showRef.current = show;
  const reloadSlots = slotsRes.reload;

  // Two changes in a row to the same heure type say nothing more than one: the page merges them.
  useEffect(() => {
    if (mergeLock.current || change || emission || !redundant.length) return;
    mergeLock.current = true;
    void (async () => {
      try {
        for (const id of redundant) await apiDelete(`/autodj/slots/${id}.json`);
        await reloadSlots();
        showRef.current(
          redundant.length === 1
            ? "Un changement en double a été fusionné."
            : `${redundant.length} changements en double ont été fusionnés.`,
          "info",
        );
      } catch (caught) {
        showRef.current(errorText(caught, "Fusion impossible."), "error");
      } finally {
        mergeLock.current = false;
      }
    })();
  }, [redundant, change, emission, reloadSlots]);

  const reloadAll = () => {
    void slotsRes.reload();
    void clocksRes.reload();
    void emissionsRes.reload();
  };

  const openRun = (run: Run, event?: MouseEvent<HTMLElement>) => {
    if (event && (event.metaKey || event.altKey)) {
      const minute = minuteAtClick(event, run.start, run.end);
      if (minute > run.start && minute < run.end) {
        setChange({ mode: "create", day: run.day, minute, clockId: otherClock(run.clockId) });
        return;
      }
    }
    setChange({ mode: "edit", run });
  };

  const otherClock = (clockId: number | null) => clocks.find((clock) => clock.id !== clockId)?.id ?? clockId;

  const dayMenu = (day: number) => (
    <DropdownMenu.Root modal={false}>
      <DropdownMenu.Trigger>
        <IconButton size="1" variant="ghost" color="gray" aria-label={`Ajouter le ${DAY_LONG[day].toLowerCase()}`}>
          <Plus size={15} />
        </IconButton>
      </DropdownMenu.Trigger>
      <DropdownMenu.Content variant="soft" align="end" className="prog-menu">
        <DropdownMenu.Item onSelect={() => setChange({ mode: "create", day })}>
          <Clock3 size={15} aria-hidden="true" />
          Changement d'horloge…
        </DropdownMenu.Item>
        <DropdownMenu.Item onSelect={() => setEmission({ day })}>
          <MicVocal size={15} aria-hidden="true" />
          Émission en direct…
        </DropdownMenu.Item>
      </DropdownMenu.Content>
    </DropdownMenu.Root>
  );

  const dayEmissions = (day: number) =>
    emissions.filter((row) => row.day_of_week === day).sort((a, b) => (a.start_minute ?? 0) - (b.start_minute ?? 0));

  return (
    <div className="prog-page">
      <SessionGate
        loading={slotsRes.loading || clocksRes.loading}
        error={slotsRes.error ?? clocksRes.error}
        ready={slotsRes.data != null && clocksRes.data != null}
        onRetry={reloadAll}
      >
        <div className="prog-week">
          <header className="prog-week-bar">
            <div className="prog-now" aria-live="polite">
              <span className="prog-now-item">
                <span className="prog-now-label">
                  <i aria-hidden="true" />
                  {parts.clock.slice(0, 5)}
                </span>
                {current ? (
                  <span>
                    <strong>{current.clockName || "Sans heure type"}</strong> jusqu'à {hhmm(current.end)}
                    <span className="prog-now-faint"> · encore {spanLabel(current.end - minuteOfDay)}</span>
                  </span>
                ) : (
                  <span>Aucune heure type ne joue</span>
                )}
              </span>
              {upcoming ? (
                <span className="prog-now-item">
                  <span className="prog-now-label">Ensuite</span>
                  <span>
                    {upcoming.day === today ? "" : `${DAY_SHORT[upcoming.day]} `}
                    {hhmm(upcoming.start)} <strong>{upcoming.clockName || "Sans heure type"}</strong>
                  </span>
                </span>
              ) : null}
              {liveShow ? (
                <span className="prog-now-item is-live">
                  <span className="prog-now-label">Direct</span>
                  <span>
                    <strong>{liveShow.title}</strong>
                    {liveShow.state === "waiting" ? " · en attente du studio" : " · à l'antenne"}
                  </span>
                </span>
              ) : nextShow ? (
                <span className="prog-now-item">
                  <span className="prog-now-label">Prochain direct</span>
                  <span>
                    {nextShow.day_of_week != null ? `${DAY_SHORT[nextShow.day_of_week]} ` : ""}
                    {nextShow.start_minute != null ? `${hhmm(nextShow.start_minute)} ` : ""}
                    <strong>{nextShow.title}</strong>
                  </span>
                </span>
              ) : null}
            </div>
            <div className="prog-week-actions">
              <Button size="2" variant="soft" color="gray" onClick={() => setEmission({ day: today })}>
                <MicVocal className="ui-button-icon" />
                Émission
              </Button>
              <Button
                size="2"
                highContrast
                onClick={() => setChange({ mode: "create", day: today })}
                disabled={!clocks.length}
              >
                <Plus className="ui-button-icon" />
                Changement d'horloge
              </Button>
            </div>
          </header>

          {runs.length ? (
            <>
              <div className="prog-week-frame">
                {/* Un tableau, pas une grille : rien ne s'y parcourt aux flèches. Chaque jour
                    se lit sous son en-tête de colonne. */}
                <div className="prog-week-grid" role="table" aria-label="Semaine">
                  <div className="prog-week-row" role="row">
                    <div className="prog-week-corner" aria-hidden="true" />
                    {DAY_LONG.map((name, day) => (
                      <div key={name} className={`prog-day-head${day === today ? " is-today" : ""}`} role="columnheader">
                        <span className="prog-day-name">
                          {DAY_SHORT[day]} <span className="prog-day-date">{dates[day]}</span>
                        </span>
                        {dayMenu(day)}
                      </div>
                    ))}
                  </div>
                  <div className="prog-week-row" role="row">
                    <div className="prog-week-gutter" aria-hidden="true">
                      {HOURS.map((hour) => (
                        <span key={hour} style={{ top: pct(hour * 60) }}>
                          {String(hour).padStart(2, "0")}:00
                        </span>
                      ))}
                    </div>
                    {DAY_LONG.map((name, day) => (
                      <div key={name} className={`prog-day${day === today ? " is-today" : ""}`} role="cell">
                        {runs
                          .filter((run) => run.day === day)
                          .map((run) => {
                            const live = day === today && run.start <= minuteOfDay && minuteOfDay < run.end;
                            return (
                              <button
                                key={`${run.day}-${run.start}`}
                                type="button"
                                className={`prog-run tint-${run.clockId != null ? (tints.get(run.clockId) ?? "gray") : "gray"}${live ? " is-live" : ""}${run.end - run.start < 90 ? " is-short" : ""}`}
                                style={{ top: pct(run.start), height: pct(run.end - run.start) }}
                                // Le nom reprend ce que le bloc affiche, dans l'ordre, après le jour.
                                aria-label={`${name} : ${run.clockName || "Sans heure type"}, ${hhmm(run.start)} → ${hhmm(run.end)}`}
                                title={`${run.clockName || "Sans heure type"} · ${hhmm(run.start)} → ${hhmm(run.end)} (Alt+clic pour couper ici)`}
                                onClick={(event) => openRun(run, event)}
                              >
                                <span className="prog-run-name">{run.clockName || "Sans heure type"}</span>{" "}
                                <span className="prog-run-time">
                                  {hhmm(run.start)} → {hhmm(run.end)}
                                </span>
                              </button>
                            );
                          })}
                        {dayEmissions(day).map((row) => (
                          <EmissionBlock
                            key={row.id}
                            row={row}
                            live={liveShow?.id === row.id}
                            onOpen={() => setEmission({ day, row })}
                          />
                        ))}
                        {day === today ? (
                          <span className="prog-now-line" style={{ top: pct(minuteOfDay) }} aria-hidden="true" />
                        ) : null}
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              <div className="prog-agenda">
                <div className="prog-agenda-days" role="tablist" aria-label="Jour">
                  {DAY_SHORT.map((name, day) => (
                    <button
                      key={name}
                      type="button"
                      role="tab"
                      aria-selected={agendaDay === day}
                      className={`prog-agenda-day${agendaDay === day ? " is-on" : ""}${day === today ? " is-today" : ""}`}
                      onClick={() => setAgendaDay(day)}
                    >
                      <span>{name}</span>
                      <small>{dates[day]}</small>
                    </button>
                  ))}
                </div>
                <ol className="prog-agenda-list" aria-label={DAY_LONG[agendaDay]}>
                  {[
                    ...runs
                      .filter((run) => run.day === agendaDay)
                      .map((run) => ({ at: run.start, run, show: null as Emission | null })),
                    ...dayEmissions(agendaDay).map((show) => ({
                      at: show.start_minute ?? 0,
                      run: null as Run | null,
                      show,
                    })),
                  ]
                    .sort((a, b) => a.at - b.at || (a.run ? -1 : 1))
                    .map((item) =>
                      item.run ? (
                        <li key={`run-${item.run.start}`}>
                          <button
                            type="button"
                            className={`prog-agenda-row tint-${item.run.clockId != null ? (tints.get(item.run.clockId) ?? "gray") : "gray"}`}
                            onClick={() => item.run && setChange({ mode: "edit", run: item.run })}
                          >
                            <span className="prog-agenda-time">
                              {hhmm(item.run.start)} → {hhmm(item.run.end)}
                            </span>
                            <strong>{item.run.clockName || "Sans heure type"}</strong>
                            <small>{spanLabel(item.run.end - item.run.start)}</small>
                          </button>
                        </li>
                      ) : item.show ? (
                        <li key={`show-${item.show.id}`}>
                          <button
                            type="button"
                            className="prog-agenda-row is-show"
                            onClick={() => item.show && setEmission({ day: agendaDay, row: item.show })}
                          >
                            <span className="prog-agenda-time">
                              {hhmm(item.show.start_minute ?? 0)} → {hhmm(item.show.end_minute ?? 0)}
                            </span>
                            <strong>{item.show.title}</strong>
                            <small>Émission en direct · {item.show.artist}</small>
                          </button>
                        </li>
                      ) : null,
                    )}
                </ol>
                <div className="prog-agenda-actions">
                  <Button
                    size="2"
                    variant="soft"
                    color="gray"
                    onClick={() => setChange({ mode: "create", day: agendaDay })}
                  >
                    <Clock3 className="ui-button-icon" />
                    Changement d'horloge
                  </Button>
                  <Button size="2" variant="soft" color="gray" onClick={() => setEmission({ day: agendaDay })}>
                    <MicVocal className="ui-button-icon" />
                    Émission
                  </Button>
                </div>
              </div>

              <footer className="prog-week-legend">
                {usedClocks.map((clock) => (
                  <Link key={clock.id} to={`/programmation?clock=${clock.id}`} className="prog-legend-item">
                    <i className={`tint-${tints.get(clock.id) ?? "gray"}`} aria-hidden="true" />
                    {clock.name}
                  </Link>
                ))}
                {emissions.length ? (
                  <span className="prog-legend-item">
                    <i className="is-show" aria-hidden="true" />
                    Émission en direct
                  </span>
                ) : null}
                <span className="prog-legend-hint">Clic : modifier · Alt+clic : couper la plage à cette heure</span>
              </footer>
            </>
          ) : (
            <div className="prog-first">
              <span className="prog-first-icon" aria-hidden="true">
                <CalendarDays size={22} />
              </span>
              <h2>La semaine est vide</h2>
              <p>
                Chaque journée commence à minuit par une heure type. Pose un premier changement d'horloge à 00:00 pour
                tous les jours.
              </p>
              <Button
                size="2"
                highContrast
                disabled={!clocks.length}
                onClick={() => setChange({ mode: "create", day: today, minute: 0 })}
              >
                <Plus className="ui-button-icon" />
                Programmer minuit
              </Button>
            </div>
          )}
        </div>
      </SessionGate>

      <ChangeDialog
        target={change}
        clocks={clocks}
        slots={slots}
        tints={tints}
        onClose={() => setChange(null)}
        onSplit={(day, minute, clockId) => setChange({ mode: "create", day, minute, clockId: otherClock(clockId) })}
        onDone={async (text, failed) => {
          await slotsRes.reload();
          show(text, failed ? "error" : "success");
        }}
      />
      {emission ? (
        <EmissionDialog
          target={emission}
          onClose={() => setEmission(null)}
          onDone={async (text) => {
            await emissionsRes.reload();
            show(text, "success");
          }}
        />
      ) : null}
      <ProtoToast message={message} onDismiss={dismiss} />
    </div>
  );
}

function EmissionBlock({ row, live, onOpen }: { row: Emission; live: boolean; onOpen: () => void }) {
  const start = row.start_minute ?? 0;
  const end = Math.max(row.end_minute ?? start, start + 30);
  return (
    <button
      type="button"
      className={`prog-show${live ? " is-live" : ""}`}
      style={{ top: pct(start), height: pct(end - start) }}
      aria-label={`Émission en direct ${row.title}, ${hhmm(start)} → ${hhmm(row.end_minute ?? start)}`}
      title={`${row.title} · ${row.artist}${row.host_username ? ` · ${row.host_username}` : ""}`}
      onClick={onOpen}
    >
      <span className="prog-run-name">{row.title}</span>{" "}
      <span className="prog-run-time">
        {hhmm(start)} → {hhmm(row.end_minute ?? start)}
      </span>
    </button>
  );
}
