import { Button, Dialog, DropdownMenu, IconButton, SegmentedControl } from "@radix-ui/themes";
import {
  CalendarCheck2,
  CalendarOff,
  ChevronLeft,
  ChevronRight,
  ListChecks,
  MoreHorizontal,
  Plus,
  Power,
  Replace,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useAccount } from "../api/AccountContext";
import {
  agendaPath,
  cancelOccurrence,
  listGuests,
  restoreOccurrence,
  setAgendaEnabled,
  updateDiffusion,
  type AgendaGuest,
  type AgendaResponse,
  type Diffusion,
  type WeeklyOccurrence,
} from "../api/agenda";
import {
  addDays,
  dayLongLabel,
  mondayOf,
  parisWall,
  timeLabel,
  wallString,
  weekDays,
  weekLabel,
} from "../api/agendaView";
import { errorText } from "../api/programmationErrors";
import { clockTints, weekRuns } from "../api/programmationView";
import { roleAtLeast, listedAsHost } from "../api/roles";
import { SessionGate } from "../api/SessionGate";
import type { ClocksResponse, SlotsResponse, UsersResponse } from "../api/types";
import { useApiJson } from "../api/useApiJson";
import { AgendaList } from "../components/agenda/AgendaList";
import { AgendaWeek } from "../components/agenda/AgendaWeek";
import { DiffusionDialog, type DiffusionTarget } from "../components/agenda/DiffusionDialog";
import { ProtoToast, useProtoToast } from "../components/ProtoToast";
import { useBrand } from "../lib/BrandContext";
import { useParisNow } from "../lib/parisClock";
import "../styles/pages/programmation.css";
import "../styles/pages/agenda.css";

const POLL_MS = 15_000;
const LIST_DAYS = 28;

type View = "semaine" | "liste";

export function AgendaPage() {
  const now = useParisNow();
  const brand = useBrand();
  const { role, account, isAdmin } = useAccount();
  const editable = roleAtLeast(role, "programmateur");
  const canStop = Boolean(account?.permissions.live || account?.permissions.admin);
  const wall = parisWall(now);
  const today = wall.day;
  const [view, setView] = useState<View>("semaine");
  const [monday, setMonday] = useState(() => mondayOf(today));
  const [onlyTodo, setOnlyTodo] = useState(false);
  const [target, setTarget] = useState<DiffusionTarget | null>(null);
  const [weeklyOpen, setWeeklyOpen] = useState<WeeklyOccurrence | null>(null);
  const [confirmOff, setConfirmOff] = useState(false);
  const { message, show, dismiss } = useProtoToast();

  const days = useMemo(() => weekDays(monday), [monday]);
  const path = view === "semaine" ? agendaPath(monday, addDays(monday, 6)) : agendaPath(today, addDays(today, LIST_DAYS - 1));
  const agendaRes = useApiJson<AgendaResponse>(path, POLL_MS);
  const slotsRes = useApiJson<SlotsResponse>("/autodj/slots.json", 60_000);
  const clocksRes = useApiJson<ClocksResponse>("/autodj/clocks.json", 60_000);
  const guestsRes = useGuests(editable);
  const usersRes = useApiJson<UsersResponse>("/users.json");

  const data = agendaRes.data;
  const diffusions = useMemo(() => data?.diffusions ?? [], [data]);
  const weekly = useMemo(() => data?.weekly ?? [], [data]);
  const todo = useMemo(() => data?.todo ?? [], [data]);
  const todoIds = useMemo(() => new Set(todo.map((line) => line.diffusion_id)), [todo]);
  const runs = useMemo(() => weekRuns(slotsRes.data?.slots ?? []), [slotsRes.data]);
  const tints = useMemo(() => clockTints(clocksRes.data?.clocks ?? []), [clocksRes.data]);
  const guests = guestsRes.guests;
  const hosts = useMemo(
    () =>
      (usersRes.data?.users ?? [])
        .filter((user) => listedAsHost(user.permissions))
        .map((user) => user.username)
        .sort((a, b) => a.localeCompare(b, "fr")),
    [usersRes.data],
  );
  const titles = useMemo(() => {
    const names = new Set<string>();
    for (const row of diffusions) names.add(row.title);
    for (const row of weekly) names.add(row.title);
    return [...names].sort((a, b) => a.localeCompare(b, "fr"));
  }, [diffusions, weekly]);

  const reloadAgenda = agendaRes.reload;
  const reloadGuests = guestsRes.reload;
  const reload = useCallback(async () => {
    await reloadAgenda();
    await reloadGuests();
  }, [reloadAgenda, reloadGuests]);

  const station = brand.suite.name || "la radio";

  const moveTo = async (row: Diffusion, start: string, end: string, text: string) => {
    const before = { start: wallOf(row.starts_at), end: wallOf(row.ends_at) };
    try {
      const saved = await updateDiffusion(row.id, { version: row.version, start, end });
      await reload();
      show(text, "success", {
        duration: 6000,
        action: {
          label: "Annuler",
          onClick: () => {
            void updateDiffusion(saved.id, { version: saved.version, start: before.start, end: before.end })
              .then(() => reload())
              .then(() => show("Remis comme avant", "info"))
              .catch((caught) => show(errorText(caught, "Retour impossible."), "error"));
          },
        },
      });
    } catch (caught) {
      show(errorText(caught, "Déplacement impossible."), "error");
      await reload();
    }
  };

  const openCreate = (day: string, start: number, end: number) =>
    setTarget({ mode: "create", day, start, end });

  const newAtNextHour = () => {
    const base = days.includes(today) ? today : monday;
    const start = base === today ? Math.min(23 * 60, (Math.floor(wall.minute / 60) + 1) * 60) : 20 * 60;
    openCreate(base, start, Math.min(start + 120, 1440));
  };

  const toggleAgenda = async (enabled: boolean) => {
    try {
      await setAgendaEnabled(enabled);
      await reload();
      show(enabled ? "L'agenda est rallumé" : "L'agenda est coupé : la grille joue seule", enabled ? "success" : "info");
    } catch (caught) {
      show(errorText(caught, "Changement impossible."), "error");
    } finally {
      setConfirmOff(false);
    }
  };

  const weeklyAction = async (work: () => Promise<unknown>, text: string) => {
    try {
      await work();
      await reload();
      show(text, "success");
    } catch (caught) {
      show(errorText(caught, "Action impossible."), "error");
    } finally {
      setWeeklyOpen(null);
    }
  };

  const replacedBy = weeklyOpen?.replaced_by != null ? diffusions.find((row) => row.id === weeklyOpen.replaced_by) : null;

  return (
    <div className="prog-page">
      <SessionGate
        loading={agendaRes.loading}
        error={agendaRes.error}
        ready={agendaRes.data != null}
        onRetry={() => void reload()}
      >
        <div className="ag">
          {data && !data.enabled ? (
            <div className="ag-off" role="status">
              <CalendarOff size={16} aria-hidden="true" />
              <span>
                <strong>L'agenda est coupé.</strong> Les émissions datées ne passent pas à l'antenne et ne bloquent rien :
                la grille joue seule.
              </span>
              {isAdmin ? (
                <Button size="1" highContrast onClick={() => void toggleAgenda(true)}>
                  <Power className="ui-button-icon" />
                  Rallumer
                </Button>
              ) : null}
            </div>
          ) : null}

          <header className="ag-bar">
            <div className="ag-nav">
              {view === "semaine" ? (
                <>
                  <IconButton
                    size="2"
                    variant="soft"
                    color="gray"
                    aria-label="Semaine précédente"
                    onClick={() => setMonday(addDays(monday, -7))}
                  >
                    <ChevronLeft size={16} />
                  </IconButton>
                  <Button
                    size="2"
                    variant="soft"
                    color="gray"
                    disabled={monday === mondayOf(today)}
                    onClick={() => setMonday(mondayOf(today))}
                  >
                    Aujourd'hui
                  </Button>
                  <IconButton
                    size="2"
                    variant="soft"
                    color="gray"
                    aria-label="Semaine suivante"
                    onClick={() => setMonday(addDays(monday, 7))}
                  >
                    <ChevronRight size={16} />
                  </IconButton>
                  <h2 className="ag-title">{weekLabel(monday)}</h2>
                </>
              ) : (
                <h2 className="ag-title">{onlyTodo ? "À préparer" : "À venir"}</h2>
              )}
            </div>
            <div className="ag-actions">
              <SegmentedControl.Root
                size="2"
                value={view}
                onValueChange={(value) => {
                  setView(value as View);
                  if (value === "semaine") setOnlyTodo(false);
                }}
              >
                <SegmentedControl.Item value="semaine">Semaine</SegmentedControl.Item>
                <SegmentedControl.Item value="liste">À venir</SegmentedControl.Item>
              </SegmentedControl.Root>
              {todo.length ? (
                <Button
                  size="2"
                  variant={onlyTodo ? "solid" : "soft"}
                  color="amber"
                  onClick={() => {
                    setView("liste");
                    setOnlyTodo(!onlyTodo || view !== "liste");
                  }}
                >
                  <ListChecks className="ui-button-icon" />
                  À préparer <span className="ag-count">{todo.length}</span>
                </Button>
              ) : (
                <span className="ag-clear">
                  <CalendarCheck2 size={15} aria-hidden="true" />
                  Rien à préparer
                </span>
              )}
              {editable ? (
                <Button size="2" highContrast onClick={newAtNextHour}>
                  <Plus className="ui-button-icon" />
                  Émission
                </Button>
              ) : null}
              {isAdmin && data?.enabled ? (
                <DropdownMenu.Root modal={false}>
                  <DropdownMenu.Trigger>
                    <IconButton size="2" variant="ghost" color="gray" aria-label="Plus d'actions">
                      <MoreHorizontal size={16} />
                    </IconButton>
                  </DropdownMenu.Trigger>
                  <DropdownMenu.Content variant="soft" align="end" className="prog-menu">
                    <DropdownMenu.Item color="red" onSelect={() => setConfirmOff(true)}>
                      <Power size={15} aria-hidden="true" />
                      Couper l'agenda…
                    </DropdownMenu.Item>
                  </DropdownMenu.Content>
                </DropdownMenu.Root>
              ) : null}
            </div>
          </header>

          {view === "semaine" ? (
            <AgendaWeek
              days={days}
              today={today}
              nowMinute={wall.minute}
              diffusions={diffusions}
              weekly={weekly}
              runs={runs}
              tints={tints}
              todoIds={todoIds}
              editable={editable}
              onCreate={openCreate}
              onOpen={(row) => setTarget({ mode: "edit", row })}
              onOpenWeekly={(row) => setWeeklyOpen(row)}
              onMove={(row, day, start) =>
                void moveTo(
                  row,
                  wallString(day, start),
                  wallString(day, start + row.duration_min),
                  `« ${row.title} » déplacée : ${dayLongLabel(day)}, ${wallString(day, start).slice(11)}`,
                )
              }
              onResize={(row, day, end) =>
                void moveTo(row, wallOf(row.starts_at), wallString(day, end), `« ${row.title} » finit à ${wallString(day, end).slice(11)}`)
              }
            />
          ) : (
            <AgendaList
              today={today}
              diffusions={diffusions}
              weekly={weekly}
              todo={todo}
              onlyTodo={onlyTodo}
              onOpen={(row) => setTarget({ mode: "edit", row })}
              onOpenWeekly={(row) => setWeeklyOpen(row)}
            />
          )}
          <footer className="ag-legend">
            <span className="ag-legend-item">
              <i className="is-set" aria-hidden="true" />
              Set enregistré
            </span>
            <span className="ag-legend-item">
              <i className="is-live" aria-hidden="true" />
              Direct
            </span>
            <span className="ag-legend-item">
              <i className="is-weekly" aria-hidden="true" />
              Émission hebdo
            </span>
            {editable ? <span className="ag-legend-hint">Glisser sur une plage : créer · glisser un bloc : déplacer</span> : null}
          </footer>
        </div>
      </SessionGate>

      <DiffusionDialog
        target={target}
        guests={guests}
        hosts={hosts}
        titles={titles}
        station={station}
        editable={editable}
        canStop={canStop}
        onClose={() => setTarget(null)}
        onChanged={async (text) => {
          await reload();
          if (text) show(text, "success");
        }}
        onDuplicate={(row) => {
          const from = parisWall(row.starts_at);
          const next = addDays(from.day, 7);
          setTarget({
            mode: "create",
            day: next,
            start: from.minute,
            end: from.minute + row.duration_min,
            copyFrom: row,
          });
        }}
        onEdit={(row) => setTarget({ mode: "edit", row })}
      />

      <Dialog.Root open={weeklyOpen != null} onOpenChange={(open) => !open && setWeeklyOpen(null)}>
        <Dialog.Content maxWidth="28rem">
          {weeklyOpen ? (
            <>
              <Dialog.Title>{weeklyOpen.title}</Dialog.Title>
              <Dialog.Description size="2" color="gray" mb="3">
                Émission hebdo · {dayLongLabel(weeklyOpen.date)}, {timeLabel(weeklyOpen.starts_at)} →{" "}
                {timeLabel(weeklyOpen.ends_at)}
                {weeklyOpen.host_username ? ` · ${weeklyOpen.host_username}` : ""}
              </Dialog.Description>
              {replacedBy ? (
                <p className="ag-hint">Remplacée ce jour-là par « {replacedBy.title} ».</p>
              ) : weeklyOpen.cancelled ? (
                <p className="ag-hint">Annulée ce jour-là : la grille joue et l'animateur n'a pas le direct.</p>
              ) : null}
              <div className="ag-weekly-actions">
                {editable && !replacedBy && !weeklyOpen.cancelled ? (
                  <Button
                    size="2"
                    highContrast
                    onClick={() => {
                      const from = parisWall(weeklyOpen.starts_at);
                      const to = parisWall(weeklyOpen.ends_at);
                      const end = to.day === from.day ? to.minute : to.minute + 1440;
                      setTarget({
                        mode: "create",
                        day: from.day,
                        start: from.minute,
                        end,
                        replacing: weeklyOpen,
                      });
                      setWeeklyOpen(null);
                    }}
                  >
                    <Replace className="ui-button-icon" />
                    Remplacer ce jour-là
                  </Button>
                ) : null}
                {editable && !replacedBy ? (
                  weeklyOpen.cancelled ? (
                    <Button
                      size="2"
                      variant="soft"
                      color="gray"
                      onClick={() =>
                        void weeklyAction(
                          () => restoreOccurrence(weeklyOpen.emission_id, weeklyOpen.date),
                          `« ${weeklyOpen.title} » rétablie ce jour-là`,
                        )
                      }
                    >
                      Rétablir ce jour-là
                    </Button>
                  ) : (
                    <Button
                      size="2"
                      variant="soft"
                      color="red"
                      onClick={() =>
                        void weeklyAction(
                          () => cancelOccurrence(weeklyOpen.emission_id, weeklyOpen.date),
                          `« ${weeklyOpen.title} » annulée ce jour-là`,
                        )
                      }
                    >
                      <CalendarOff className="ui-button-icon" />
                      Annuler ce jour-là
                    </Button>
                  )
                ) : null}
                {replacedBy ? (
                  <Button
                    size="2"
                    variant="soft"
                    color="gray"
                    onClick={() => {
                      setTarget({ mode: "edit", row: replacedBy });
                      setWeeklyOpen(null);
                    }}
                  >
                    Ouvrir « {replacedBy.title} »
                  </Button>
                ) : null}
                <Button size="2" variant="ghost" color="gray" asChild>
                  <Link to="/programmation?onglet=semaine">Modifier l'émission hebdo</Link>
                </Button>
              </div>
            </>
          ) : null}
        </Dialog.Content>
      </Dialog.Root>

      <Dialog.Root open={confirmOff} onOpenChange={setConfirmOff}>
        <Dialog.Content maxWidth="28rem">
          <Dialog.Title>Couper l'agenda ?</Dialog.Title>
          <Dialog.Description size="2" color="gray" mb="4">
            Les émissions datées ne passeront plus à l'antenne et ne bloqueront plus la grille, ni le direct. Rien n'est
            effacé : tu peux le rallumer à tout moment. Un set déjà à l'antenne continue, mais les coupures de l'heure
            type reprennent.
          </Dialog.Description>
          <div className="prog-dialog-actions">
            <Dialog.Close>
              <Button size="2" variant="soft" color="gray">
                Annuler
              </Button>
            </Dialog.Close>
            <Button size="2" color="red" highContrast onClick={() => void toggleAgenda(false)}>
              Couper l'agenda
            </Button>
          </div>
        </Dialog.Content>
      </Dialog.Root>
      <ProtoToast message={message} onDismiss={dismiss} />
    </div>
  );
}

function wallOf(iso: string): string {
  const wall = parisWall(iso);
  return wallString(wall.day, wall.minute);
}

/** The guests' book, for the programmers only (an animator has no right to it). */
function useGuests(enabled: boolean): { guests: AgendaGuest[]; reload: () => Promise<void> } {
  const [guests, setGuests] = useState<AgendaGuest[]>([]);
  const reload = useCallback(async () => {
    if (!enabled) return;
    try {
      setGuests(await listGuests());
    } catch {
      // The dialog still accepts a new name; the book comes back on the next reload.
    }
  }, [enabled]);
  useEffect(() => {
    void reload();
  }, [reload]);
  return { guests, reload };
}
