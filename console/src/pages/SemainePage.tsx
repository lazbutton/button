import { Badge, Button, Dialog, Flex, Spinner, TextField } from "@radix-ui/themes";
import {
  CalendarDays,
  Pencil,
  Plus,
  Radio,
  Save,
  Trash2,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ProtoToast, useProtoToast } from "../components/ProtoToast";
import { parisParts, parisWeekdayMon0, useParisNow } from "../lib/parisClock";
import { apiDelete, apiPostJson, apiPut, ApiRequestError } from "../api/client";
import { daypartRanges, formatDayMinute, splitHoursInRange, weekSlotClass, type DaypartRange } from "../api/clockCss";
import { clockToMinute, emissionWindowLabel, minuteToClock } from "../api/emissionMeta";
import { listedAsHost } from "../api/roles";
import { SessionGate } from "../api/SessionGate";
import type {
  Clock,
  ClocksResponse,
  Emission,
  EmissionsResponse,
  Slot,
  SlotsResponse,
  UsersResponse,
} from "../api/types";
import { useApiJson } from "../api/useApiJson";
import { ConfirmDialog } from "../ui/ConfirmDialog";
import { EmptyState } from "../ui/EmptyState";
import { FormField, SelectField } from "../ui/FormField";
import { PageHeader } from "../ui/PageHeader";
import { Panel } from "../ui/Panel";
import "../styles/pages/semaine.css";

const DAYS = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"] as const;
const DAY_NAMES = [
  "Lundi",
  "Mardi",
  "Mercredi",
  "Jeudi",
  "Vendredi",
  "Samedi",
  "Dimanche",
] as const;
const POLL_MS = 10_000;

type ClockRun = {
  day: number;
  start: number;
  end: number;
  clockId: number | null;
  clock: string;
  ranges: DaypartRange<Slot>[];
};

function clockName(slot: Slot): string {
  return slot.clock?.trim() || "";
}

function formatDuration(minutes: number): string {
  const span = Math.max(0, Math.round(minutes));
  const hours = Math.floor(span / 60);
  const mins = span % 60;
  if (hours && mins) return `${hours} h ${mins} min`;
  if (hours) return `${hours} h`;
  return `${mins} min`;
}

function weekDates(now: Date): string[] {
  const today = parisWeekdayMon0(now);
  return DAYS.map((_, index) => {
    const shifted = new Date(now.getTime() + (index - today) * 86_400_000);
    return parisParts(shifted).day;
  });
}

function mergeRuns(ranges: DaypartRange<Slot>[]): ClockRun[] {
  const runs: ClockRun[] = [];
  for (let day = 0; day < 7; day += 1) {
    const dayRanges = ranges
      .filter((range) => range.day === day)
      .sort((a, b) => a.start - b.start);
    for (const range of dayRanges) {
      const last = runs.at(-1);
      const sameClock =
        last &&
        last.day === day &&
        last.end === range.start &&
        last.clockId === range.slot.clock_id;
      if (sameClock && last) {
        last.end = range.end;
        last.ranges.push(range);
      } else {
        runs.push({
          day,
          start: range.start,
          end: range.end,
          clockId: range.slot.clock_id,
          clock: clockName(range.slot) || "Sans heure type",
          ranges: [range],
        });
      }
    }
  }
  return runs;
}

function nextRun(
  runs: ClockRun[],
  today: number,
  minuteOfDay: number,
): ClockRun | null {
  const laterToday = runs
    .filter((run) => run.day === today && run.start > minuteOfDay)
    .sort((a, b) => a.start - b.start)[0];
  if (laterToday) return laterToday;
  for (let offset = 1; offset <= 7; offset += 1) {
    const day = (today + offset) % 7;
    const first = runs.filter((run) => run.day === day).sort((a, b) => a.start - b.start)[0];
    if (first) return first;
  }
  return null;
}

export function SemainePage({ embedded = false }: { embedded?: boolean }) {
  const now = useParisNow();
  const slotsRes = useApiJson<SlotsResponse>("/autodj/slots.json", POLL_MS);
  const clocksRes = useApiJson<ClocksResponse>("/autodj/clocks.json", POLL_MS);
  const emissionsRes = useApiJson<EmissionsResponse>("/antenne/emissions.json", POLL_MS);
  const { message, show } = useProtoToast();
  const navigate = useNavigate();
  const slots = slotsRes.data?.slots ?? [];
  const clocks = clocksRes.data?.clocks ?? [];
  const loading = slotsRes.loading || clocksRes.loading;
  const error = slotsRes.error ?? clocksRes.error ?? emissionsRes.error;
  const emissions = emissionsRes.data?.emissions ?? [];
  const ranges = useMemo(() => daypartRanges(slots), [slots]);
  const runs = useMemo(() => mergeRuns(ranges), [ranges]);
  const parts = parisParts(now);
  const today = parisWeekdayMon0(now);
  const minuteOfDay = parts.hour * 60 + parts.minute;
  const currentRun =
    runs.find(
      (run) => run.day === today && run.start <= minuteOfDay && minuteOfDay < run.end,
    ) ?? null;
  const upcoming = nextRun(runs, today, minuteOfDay);
  const dates = weekDates(now);
  const extras = useMemo(() => runs.flatMap((run) => run.ranges.slice(1)), [runs]);
  const [edit, setEdit] = useState<ClockRun | null>(null);
  const [createDay, setCreateDay] = useState<number | null>(null);
  const [emissionDraft, setEmissionDraft] = useState<{ day: number; row?: Emission } | null>(
    null,
  );
  const mergeLock = useRef(false);

  useEffect(() => {
    if (mergeLock.current || edit || createDay != null || !extras.length) return;
    mergeLock.current = true;
    const redundant = extras;
    void (async () => {
      try {
        for (const extra of redundant) {
          await apiDelete(`/autodj/slots/${extra.slot.id}.json`);
        }
        await slotsRes.reload();
        show(
          redundant.length === 1
            ? "Une plage identique a été fusionnée."
            : `${redundant.length} plages identiques ont été fusionnées.`,
        );
      } catch (caught) {
        show(caught instanceof ApiRequestError ? caught.message : "Fusion impossible.");
      } finally {
        mergeLock.current = false;
      }
    })();
  }, [extras, edit, createDay, show, slotsRes.reload]);

  return (
    <>
      <div className={`semaine-page${embedded ? " semaine-page--embedded" : " ui-page"}`}>
        {embedded ? null : (
        <PageHeader
          eyebrow="Programmation Auto-DJ"
          title="Semaine"
          description="Un changement d’horloge charge une heure type jusqu’au suivant. Les émissions en direct se superposent : l’heure type continue tant que le harbor n’est pas là. Dès que le harbor est connecté, tout le reste cède."
          actions={
            <Badge variant="soft" color="gray">
              <CalendarDays size={13} aria-hidden="true" />
              7 jours · {runs.filter((run) => run.day === today).length} plages / jour type
            </Badge>
          }
        />
        )}

        <SessionGate
          loading={loading}
          error={error}
          ready={slotsRes.data != null || clocksRes.data != null}
          onRetry={() => {
            void slotsRes.reload();
            void clocksRes.reload();
            void emissionsRes.reload();
          }}
        >
          {runs.length ? (
            <>
              {embedded ? null : (
              <section
                className="semaine-live"
                aria-live="polite"
                aria-label="Heure type à l’antenne"
              >
                <span className="semaine-live-icon" aria-hidden="true">
                  <Radio size={18} />
                </span>
                <div className="semaine-live-now">
                  <p className="semaine-live-kicker">À l’antenne · {parts.clock.slice(0, 5)}</p>
                  <h2>{currentRun?.clock ?? "Aucune heure type"}</h2>
                  <p>
                    {currentRun
                      ? `${formatDayMinute(currentRun.start)} → ${formatDayMinute(currentRun.end)} · encore ${formatDuration(currentRun.end - minuteOfDay)}`
                      : "Hors grille"}
                  </p>
                </div>
                {upcoming ? (
                  <div className="semaine-live-next">
                    <p className="semaine-live-kicker">Ensuite</p>
                    <strong>
                      {DAY_NAMES[upcoming.day]} {formatDayMinute(upcoming.start)}
                    </strong>
                    <p>{upcoming.clock}</p>
                  </div>
                ) : null}
                {emissionsRes.data?.next ? (
                  <div className="semaine-live-next">
                    <p className="semaine-live-kicker">Émission en direct</p>
                    <strong>{emissionsRes.data.next.title}</strong>
                    <p>
                      {emissionsRes.data.next.day_of_week != null
                        ? DAY_NAMES[emissionsRes.data.next.day_of_week]
                        : ""}{" "}
                      {emissionsRes.data.next.start_minute != null
                        ? formatDayMinute(emissionsRes.data.next.start_minute)
                        : ""}
                    </p>
                  </div>
                ) : null}
              </section>
              )}

              <div className="semaine-days" role="list">
                {DAY_NAMES.map((name, dayIndex) => {
                  const dayRuns = runs.filter((run) => run.day === dayIndex);
                  return (
                    <section
                      key={name}
                      className={`semaine-day${dayIndex === today ? " is-today" : ""}`}
                      data-day={dayIndex}
                      aria-label={name}
                    >
                      <header className="semaine-day-head">
                        <div>
                          <span className="semaine-day-name">{embedded ? DAYS[dayIndex] : name}</span>
                          <span className="semaine-day-date">{dates[dayIndex]}</span>
                          {dayIndex === today ? (
                            <span className="semaine-day-today">aujourd’hui</span>
                          ) : null}
                        </div>
                        <div className="semaine-day-actions">
                          <button
                            type="button"
                            className="semaine-day-add"
                            onClick={() => setCreateDay(dayIndex)}
                          >
                            + changement d’horloge
                          </button>
                          <button
                            type="button"
                            className="semaine-day-add is-live"
                            onClick={() => setEmissionDraft({ day: dayIndex })}
                          >
                            + émission en direct
                          </button>
                        </div>
                      </header>
                      {dayRuns[0] && dayRuns[0].start !== 0 ? (
                        <p className="semaine-day-gap">Cette journée ne commence pas à minuit.</p>
                      ) : null}
                      <div className="semaine-day-runs">
                        <div className="semaine-day-track">
                        {dayRuns.map((run) => {
                          const live =
                            dayIndex === today &&
                            run.start <= minuteOfDay &&
                            minuteOfDay < run.end;
                          const hours = Math.max((run.end - run.start) / 60, 1);
                          const progress = live
                            ? Math.min(
                                1,
                                Math.max(0, (minuteOfDay - run.start) / Math.max(run.end - run.start, 1)),
                              )
                            : 0;
                          return (
                            <button
                              key={`${run.day}-${run.start}`}
                              type="button"
                              className={`semaine-run ${weekSlotClass(run.clock)}${
                                live ? " is-live" : ""
                              }`}
                              style={{ flexGrow: hours }}
                              aria-current={live ? "time" : undefined}
                              aria-label={`${name} ${formatDayMinute(run.start)} à ${formatDayMinute(run.end)}, ${run.clock}`}
                              onClick={() => setEdit(run)}
                            >
                              {live ? <span className="semaine-run-live">Direct</span> : null}
                              <span className="semaine-run-time">
                                {formatDayMinute(run.start)}
                                <span aria-hidden="true"> → </span>
                                {formatDayMinute(run.end)}
                              </span>
                              <strong className="semaine-run-clock" title={run.clock}>{run.clock}</strong>
                              <span className="semaine-run-meta">
                                {formatDuration(run.end - run.start)}
                              </span>
                              {live ? (
                                <span
                                  className="semaine-run-progress"
                                  style={{ width: `${progress * 100}%` }}
                                />
                              ) : null}
                            </button>
                          );
                        })}
                        {emissions
                          .filter(
                            (row) => row.scope !== "session" && row.day_of_week === dayIndex,
                          )
                          .map((row) => {
                            const start = row.start_minute ?? 0;
                            const end = row.end_minute ?? start;
                            const liveShow =
                              dayIndex === today && start <= minuteOfDay && minuteOfDay < end;
                            const top = (start / 1440) * 100;
                            const height = (Math.max(end - start, 30) / 1440) * 100;
                            return (
                              <button
                                key={`emission-${row.id}`}
                                type="button"
                                className={`semaine-emission${liveShow ? " is-live" : ""}`}
                                style={{ top: `${top}%`, height: `${height}%` }}
                                aria-label={`Émission en direct ${row.title} ${emissionWindowLabel(row)}`}
                                onClick={() => setEmissionDraft({ day: dayIndex, row })}
                              >
                                <span className="semaine-emission-kicker">Émission en direct</span>
                                <strong>{row.title}</strong>
                                <span>
                                  {emissionWindowLabel(row)}
                                  {row.artist ? ` · ${row.artist}` : ""}
                                  {row.host_username ? ` · ${row.host_username}` : ""}
                                </span>
                              </button>
                            );
                          })}
                        </div>
                      </div>
                    </section>
                  );
                })}
              </div>
            </>
          ) : (
            <Panel className="semaine-empty-panel">
              <EmptyState
                icon={CalendarDays}
                title="Aucune plage programmée"
                description="Il faut un changement d’horloge à minuit chaque jour, puis éventuellement 10h et 18h."
                actionLabel="Ouvrir les heures types"
                onAction={() => navigate("/programmation")}
              />
            </Panel>
          )}
        </SessionGate>
      </div>

      {edit ? (
        <RunDialog
          run={edit}
          clocks={clocks}
          onClose={() => setEdit(null)}
          onDone={async (text) => {
            await slotsRes.reload();
            setEdit(null);
            show(text);
          }}
          onError={show}
        />
      ) : null}

      {createDay != null ? (
        <CreateDepartureDialog
          day={createDay}
          clocks={clocks}
          takenMinutes={ranges.filter((range) => range.day === createDay).map((range) => range.start)}
          onClose={() => setCreateDay(null)}
          onDone={async (text) => {
            await slotsRes.reload();
            setCreateDay(null);
            show(text);
          }}
          onError={show}
        />
      ) : null}
      {emissionDraft ? (
        <EmissionDialog
          day={emissionDraft.day}
          row={emissionDraft.row}
          onClose={() => setEmissionDraft(null)}
          onDone={async (text) => {
            await emissionsRes.reload();
            setEmissionDraft(null);
            show(text);
          }}
          onError={show}
        />
      ) : null}
      <ProtoToast message={message} />
    </>
  );
}

function RunDialog({
  run,
  clocks,
  onClose,
  onDone,
  onError,
}: {
  run: ClockRun;
  clocks: Clock[];
  onClose: () => void;
  onDone: (message: string) => Promise<void>;
  onError: (text: string) => void;
}) {
  const slot = run.ranges[0].slot;
  const midnight = slot.minute === 0;
  const [clockId, setClockId] = useState(String(slot.clock_id ?? clocks[0]?.id ?? ""));
  const [splitHour, setSplitHour] = useState("");
  const [busyAction, setBusyAction] = useState<"save" | "split" | "delete" | null>(null);
  const hours = useMemo(() => splitHoursInRange(run.start, run.end), [run.end, run.start]);
  const busy = busyAction !== null;

  const save = async () => {
    setBusyAction("save");
    try {
      const selected = clocks.find((clock) => String(clock.id) === clockId);
      await apiPut(`/autodj/slots/${slot.id}.json`, {
        title: selected?.name || slot.title,
        clock_id: clockId ? Number(clockId) : null,
        color: slot.color || "#7a9e6a",
      });
      await onDone("Heure type de la plage enregistrée");
    } catch (caught) {
      onError(caught instanceof ApiRequestError ? caught.message : "Enregistrement impossible.");
    } finally {
      setBusyAction(null);
    }
  };

  const split = async () => {
    if (!splitHour) return;
    setBusyAction("split");
    try {
      const selected = clocks.find((clock) => String(clock.id) === clockId);
      await apiPostJson("/autodj/slots.json", {
        title: selected?.name || slot.title,
        day_of_week: run.day,
        minute: Number(splitHour) * 60,
        clock_id: clockId ? Number(clockId) : null,
        color: slot.color || "#7a9e6a",
      });
      await onDone(`Nouveau changement d’horloge à ${String(splitHour).padStart(2, "0")}:00`);
    } catch (caught) {
      onError(caught instanceof ApiRequestError ? caught.message : "Création impossible.");
    } finally {
      setBusyAction(null);
    }
  };

  const remove = async () => {
    if (midnight) return;
    setBusyAction("delete");
    try {
      await apiDelete(`/autodj/slots/${slot.id}.json`);
      await onDone("Changement d’horloge supprimé");
    } catch (caught) {
      onError(caught instanceof ApiRequestError ? caught.message : "Suppression impossible.");
    } finally {
      setBusyAction(null);
    }
  };

  return (
    <Dialog.Root open onOpenChange={(open) => !open && !busy && onClose()}>
      <Dialog.Content maxWidth="32rem" className="semaine-dialog">
        <Dialog.Title className="semaine-dialog-title">
          <span className="semaine-dialog-title-icon" aria-hidden="true">
            <Pencil size={16} />
          </span>
          {DAY_NAMES[run.day]} · {formatDayMinute(run.start)} → {formatDayMinute(run.end)}
        </Dialog.Title>
        <Dialog.Description size="2" className="semaine-dialog-description">
          À {formatDayMinute(run.start)}, <strong>{run.clock}</strong> joue jusqu’au changement suivant.
        </Dialog.Description>

        <div className="semaine-dialog-fields">
          <SelectField
            label="Heure type jusqu’au prochain changement"
            value={clockId}
            options={clocks.map((clock) => ({
              value: String(clock.id),
              label: clock.name,
            }))}
            onValueChange={setClockId}
            hint="Deux plages identiques qui se suivent fusionnent toutes seules."
            placeholder="Choisir une heure type"
            disabled={busy}
          />

          {hours.length ? (
            <SelectField
              label="Ajouter un changement d’horloge à"
              value={splitHour}
              options={hours.map((hour) => ({
                value: String(hour),
                label: `${String(hour).padStart(2, "0")}:00`,
              }))}
              onValueChange={setSplitHour}
              hint="Utile seulement pour changer d’heure type en cours de journée."
              placeholder="Heure pleine"
              disabled={busy}
            />
          ) : null}
        </div>

        <div className="semaine-dialog-actions">
          {!midnight ? (
            <ConfirmDialog
              trigger={
                <Button color="red" variant="soft" disabled={busy}>
                  <Trash2 className="ui-button-icon" aria-hidden="true" />
                  Supprimer le changement {formatDayMinute(run.start)}
                </Button>
              }
              title="Supprimer ce changement d’horloge ?"
              description={
                <>
                  La plage précédente se prolongera jusqu’à {formatDayMinute(run.end)}.
                </>
              }
              confirmLabel="Supprimer"
              busy={busyAction === "delete"}
              onConfirm={remove}
            />
          ) : (
            <span className="semaine-dialog-locked">Changement de minuit obligatoire</span>
          )}

          <Flex gap="2" justify="end" wrap="wrap">
            <Button variant="soft" color="gray" disabled={busy} onClick={onClose}>
              Fermer
            </Button>
            {hours.length ? (
              <Button variant="soft" disabled={busy || !splitHour} onClick={() => void split()}>
                {busyAction === "split" ? <Spinner size="1" /> : <Plus className="ui-button-icon" />}
                {splitHour ? `Changement ${String(splitHour).padStart(2, "0")}:00` : "Ajouter"}
              </Button>
            ) : null}
            <Button disabled={busy} onClick={() => void save()}>
              {busyAction === "save" ? (
                <Spinner size="1" />
              ) : (
                <Save className="ui-button-icon" aria-hidden="true" />
              )}
              Enregistrer l’heure type
            </Button>
          </Flex>
        </div>
      </Dialog.Content>
    </Dialog.Root>
  );
}

function CreateDepartureDialog({
  day,
  clocks,
  takenMinutes,
  onClose,
  onDone,
  onError,
}: {
  day: number;
  clocks: Clock[];
  takenMinutes: number[];
  onClose: () => void;
  onDone: (message: string) => Promise<void>;
  onError: (text: string) => void;
}) {
  const taken = new Set(takenMinutes);
  const hours = Array.from({ length: 23 }, (_, index) => index + 1).filter(
    (hour) => !taken.has(hour * 60),
  );
  const defaultClock = clocks[0]?.id;
  const [hour, setHour] = useState(hours.includes(10) ? "10" : String(hours[0] ?? ""));
  const [clockId, setClockId] = useState(String(defaultClock ?? ""));
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    if (!hour) return;
    setBusy(true);
    try {
      const selected = clocks.find((clock) => String(clock.id) === clockId);
      await apiPostJson("/autodj/slots.json", {
        title: selected?.name || DAY_NAMES[day],
        day_of_week: day,
        minute: Number(hour) * 60,
        clock_id: clockId ? Number(clockId) : null,
        color: "#7a9e6a",
      });
      await onDone(`Changement d’horloge ajouté ${DAY_NAMES[day]} ${String(hour).padStart(2, "0")}:00`);
    } catch (caught) {
      onError(caught instanceof ApiRequestError ? caught.message : "Création impossible.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog.Root open onOpenChange={(open) => !open && !busy && onClose()}>
      <Dialog.Content maxWidth="28rem" className="semaine-dialog">
        <Dialog.Title>Nouveau changement d’horloge · {DAY_NAMES[day]}</Dialog.Title>
        <Dialog.Description size="2" className="semaine-dialog-description">
          L’heure type choisie sera jouée à partir de cette heure jusqu’au changement suivant.
        </Dialog.Description>
        <div className="semaine-dialog-fields">
          <SelectField
            label="Heure"
            value={hour}
            options={hours.map((item) => ({
              value: String(item),
              label: `${String(item).padStart(2, "0")}:00`,
            }))}
            onValueChange={setHour}
            disabled={busy || !hours.length}
            placeholder="Choisir une heure"
          />
          <SelectField
            label="Heure type"
            value={clockId}
            options={clocks.map((clock) => ({
              value: String(clock.id),
              label: clock.name,
            }))}
            onValueChange={setClockId}
            disabled={busy}
            placeholder="Choisir une heure type"
          />
        </div>
        <Flex gap="2" justify="end" mt="4">
          <Button variant="soft" color="gray" disabled={busy} onClick={onClose}>
            Annuler
          </Button>
          <Button disabled={busy || !hour} onClick={() => void submit()}>
            {busy ? <Spinner size="1" /> : <Plus className="ui-button-icon" />}
            Ajouter
          </Button>
        </Flex>
      </Dialog.Content>
    </Dialog.Root>
  );
}

function EmissionDialog({
  day,
  row,
  onClose,
  onDone,
  onError,
}: {
  day: number;
  row?: Emission;
  onClose: () => void;
  onDone: (message: string) => Promise<void>;
  onError: (text: string) => void;
}) {
  const [title, setTitle] = useState(row?.title ?? "");
  const [artist, setArtist] = useState(row?.artist ?? "");
  const [host, setHost] = useState(row?.host_username?.trim() || "none");
  const [start, setStart] = useState(minuteToClock(row?.start_minute ?? 20 * 60));
  const [end, setEnd] = useState(minuteToClock(row?.end_minute ?? 22 * 60));
  const [busy, setBusy] = useState<"save" | "delete" | null>(null);
  const usersRes = useApiJson<UsersResponse>("/users.json");
  const hostOptions = useMemo(() => {
    const names = new Set<string>();
    for (const user of usersRes.data?.users ?? []) {
      if (listedAsHost(user.permissions)) names.add(user.username);
    }
    if (host !== "none") names.add(host);
    return [
      { value: "none", label: "Pas encore nominatif" },
      ...[...names].sort((a, b) => a.localeCompare(b, "fr")).map((name) => ({
        value: name,
        label: name,
      })),
    ];
  }, [host, usersRes.data]);

  const save = async () => {
    const startMinute = clockToMinute(start);
    const endMinute = clockToMinute(end);
    if (startMinute == null || endMinute == null) {
      onError("Heure de début ou de fin invalide.");
      return;
    }
    setBusy("save");
    try {
      const body = {
        scope: "weekly" as const,
        title: title.trim(),
        artist: artist.trim(),
        day_of_week: day,
        start_minute: startMinute,
        end_minute: endMinute,
        host_username: host === "none" ? "" : host,
        version: row?.version,
      };
      if (row) {
        await apiPut(`/antenne/emissions/${row.id}.json`, body);
        await onDone("Émission en direct enregistrée");
      } else {
        await apiPostJson("/antenne/emissions.json", body);
        await onDone("Émission en direct ajoutée");
      }
    } catch (caught) {
      onError(caught instanceof ApiRequestError ? caught.message : "Enregistrement impossible.");
    } finally {
      setBusy(null);
    }
  };

  const remove = async () => {
    if (!row) return;
    setBusy("delete");
    try {
      await apiDelete(`/antenne/emissions/${row.id}.json`);
      await onDone("Émission en direct retirée");
    } catch (caught) {
      onError(caught instanceof ApiRequestError ? caught.message : "Suppression impossible.");
    } finally {
      setBusy(null);
    }
  };

  return (
    <Dialog.Root open onOpenChange={(open) => !open && !busy && onClose()}>
      <Dialog.Content maxWidth="28rem" className="semaine-dialog">
        <Dialog.Title>{row ? "Émission en direct" : "Nouvelle émission en direct"} · {DAY_NAMES[day]}</Dialog.Title>
        <Dialog.Description size="2" className="semaine-dialog-description">
          L’heure type continue tant que personne n’est connecté. Dès que le harbor est là,
          le titre devient le nom de l’émission et l’artiste la phrase.
        </Dialog.Description>
        <div className="semaine-dialog-fields">
          <FormField label="Nom de l’émission" htmlFor="emission-title">
            <TextField.Root
              id="emission-title"
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              placeholder="Hop Pop Hop"
              disabled={busy != null}
            />
          </FormField>
          <SelectField
            label="Identifiant du plateau"
            value={host}
            options={hostOptions}
            onValueChange={setHost}
            disabled={busy != null}
            hint="Tant qu’aucune émission ne nomme quelqu’un, tout compte stream peut se brancher. Dès qu’une émission a un identifiant, chacun ne passe que sur son créneau. Un admin passe toujours."
          />
          <FormField label="Phrase artiste" htmlFor="emission-artist">
            <TextField.Root
              id="emission-artist"
              value={artist}
              onChange={(event) => setArtist(event.target.value)}
              placeholder="avec Marie et Jean"
              disabled={busy != null}
            />
          </FormField>
          <FormField label="Début" htmlFor="emission-start">
            <TextField.Root
              id="emission-start"
              type="time"
              value={start}
              onChange={(event) => setStart(event.target.value)}
              disabled={busy != null}
            />
          </FormField>
          <FormField label="Fin" htmlFor="emission-end" hint="24:00 accepté pour minuit.">
            <TextField.Root
              id="emission-end"
              type="time"
              value={end === "24:00" ? "23:59" : end}
              onChange={(event) => setEnd(event.target.value)}
              disabled={busy != null}
            />
          </FormField>
        </div>
        <div className="semaine-dialog-actions">
          {row ? (
            <ConfirmDialog
              trigger={
                <Button color="red" variant="soft" disabled={busy != null}>
                  <Trash2 className="ui-button-icon" />
                  Retirer
                </Button>
              }
              title="Retirer cette émission en direct ?"
              description="L’heure type de la plage n’est pas modifiée."
              confirmLabel="Retirer"
              busy={busy === "delete"}
              onConfirm={remove}
            />
          ) : (
            <span />
          )}
          <Flex gap="2" justify="end">
            <Button variant="soft" color="gray" disabled={busy != null} onClick={onClose}>
              Annuler
            </Button>
            <Button disabled={busy != null || !title.trim() || !artist.trim()} onClick={() => void save()}>
              {busy === "save" ? <Spinner size="1" /> : <Save className="ui-button-icon" />}
              Enregistrer
            </Button>
          </Flex>
        </div>
      </Dialog.Content>
    </Dialog.Root>
  );
}
