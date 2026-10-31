import { Button, Dialog, Select } from "@radix-ui/themes";
import { Scissors, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { apiDelete, apiPostJson, apiPut } from "../../api/client";
import { errorText } from "../../api/programmationErrors";
import { DAY_LETTER, DAY_LONG, daySetLabel, hhmm, type Run } from "../../api/programmationView";
import type { Clock, Slot } from "../../api/types";

const DEFAULT_COLOR = "#7a9e6a";
const PRESETS = [
  { label: "Tous", days: [0, 1, 2, 3, 4, 5, 6] },
  { label: "Lun–Ven", days: [0, 1, 2, 3, 4] },
  { label: "Sam–Dim", days: [5, 6] },
];

export type ChangeTarget =
  /** A new change: one day to start with, a time if the click gave one. */
  | { mode: "create"; day: number; minute?: number; clockId?: number | null }
  /** The change that starts this run. */
  | { mode: "edit"; run: Run };

function timeOptions(extra: number[]): number[] {
  const times = new Set<number>(Array.from({ length: 48 }, (_, index) => index * 30));
  for (const minute of extra) if (minute >= 0 && minute < 1440) times.add(minute);
  return [...times].sort((a, b) => a - b);
}

/** Create a change of heure type, or edit the one that starts a run; the same change can go to several days. */
export function ChangeDialog({
  target,
  clocks,
  slots,
  tints,
  onClose,
  onSplit,
  onDone,
}: {
  target: ChangeTarget | null;
  clocks: Clock[];
  slots: Slot[];
  tints: Map<number, string>;
  onClose: () => void;
  /** From an edit: start a new change inside the run. */
  onSplit: (day: number, minute: number, clockId: number | null) => void;
  onDone: (message: string, failed: boolean) => Promise<void>;
}) {
  const editing = target?.mode === "edit" ? target.run.slots[0] : null;
  const [clockId, setClockId] = useState("");
  const [minute, setMinute] = useState(0);
  const [days, setDays] = useState<number[]>([]);
  const [busy, setBusy] = useState<"save" | "delete" | null>(null);
  const [failure, setFailure] = useState("");
  const [confirming, setConfirming] = useState(false);

  useEffect(() => {
    if (!target) return;
    setFailure("");
    setBusy(null);
    setConfirming(false);
    if (target.mode === "edit") {
      setClockId(target.run.clockId != null ? String(target.run.clockId) : "");
      setMinute(target.run.start);
      setDays([target.run.day]);
    } else {
      const fallback = target.clockId ?? clocks[0]?.id ?? null;
      setClockId(fallback != null ? String(fallback) : "");
      setMinute(target.minute ?? 7 * 60);
      setDays([target.day]);
    }
  }, [target]); // the lists refresh every few seconds: only a new target resets the form

  const midnightLocked = editing != null && editing.minute === 0;
  const times = useMemo(() => timeOptions([minute, editing?.minute ?? -1]), [minute, editing?.minute]);
  const clock = clocks.find((row) => String(row.id) === clockId) ?? null;

  /** What saving would do, day by day: create, change, or nothing. */
  const plan = useMemo(() => {
    return days.map((day) => {
      if (editing && day === editing.day_of_week) {
        const same = editing.clock_id === clock?.id && editing.minute === minute;
        return { day, slot: editing, action: same ? ("none" as const) : ("update" as const) };
      }
      const existing = slots.find((slot) => slot.day_of_week === day && slot.minute === minute) ?? null;
      if (!existing) return { day, slot: null, action: "create" as const };
      return { day, slot: existing, action: existing.clock_id === clock?.id ? ("none" as const) : ("update" as const) };
    });
  }, [days, editing, slots, minute, clock?.id]);
  const created = plan.filter((row) => row.action === "create").length;
  const updated = plan.filter((row) => row.action === "update").length;
  const conflict =
    editing && minute !== editing.minute
      ? slots.some(
          (slot) => slot.id !== editing.id && slot.day_of_week === editing.day_of_week && slot.minute === minute,
        )
      : false;

  const toggle = (day: number) => {
    if (editing && day === editing.day_of_week) return;
    setDays((current) => (current.includes(day) ? current.filter((row) => row !== day) : [...current, day]));
  };

  const save = async () => {
    if (!clock || !days.length || conflict) return;
    setBusy("save");
    setFailure("");
    const failed: string[] = [];
    let done = 0;
    for (const row of plan) {
      if (row.action === "none") continue;
      try {
        if (row.action === "create") {
          await apiPostJson("/autodj/slots.json", {
            title: clock.name,
            day_of_week: row.day,
            minute,
            clock_id: clock.id,
            color: DEFAULT_COLOR,
          });
        } else if (row.slot) {
          await apiPut(`/autodj/slots/${row.slot.id}.json`, {
            title: clock.name,
            clock_id: clock.id,
            color: row.slot.color || DEFAULT_COLOR,
            version: row.slot.version,
            ...(editing && row.slot.id === editing.id && minute !== editing.minute ? { minute } : {}),
          });
        }
        done += 1;
      } catch (caught) {
        failed.push(`${DAY_LONG[row.day]} : ${errorText(caught, "refusé")}`);
      }
    }
    setBusy(null);
    if (failed.length) {
      setFailure(failed.join(" · "));
      if (done)
        await onDone(
          `${done} jour${done === 1 ? "" : "s"} enregistré${done === 1 ? "" : "s"}, le reste a été refusé`,
          true,
        );
      return;
    }
    await onDone(
      done ? `${daySetLabel(days)} à ${hhmm(minute)} : ${clock.name}` : "Rien à changer : c'était déjà programmé ainsi",
      false,
    );
    onClose();
  };

  const remove = async () => {
    if (!editing || midnightLocked) return;
    setBusy("delete");
    setFailure("");
    try {
      await apiDelete(`/autodj/slots/${editing.id}.json`);
      await onDone(
        `Changement de ${DAY_LONG[editing.day_of_week].toLowerCase()} ${hhmm(editing.minute)} retiré`,
        false,
      );
      onClose();
    } catch (caught) {
      setFailure(errorText(caught, "Suppression impossible."));
    } finally {
      setBusy(null);
    }
  };

  const run = target?.mode === "edit" ? target.run : null;

  return (
    <Dialog.Root
      open={target != null}
      onOpenChange={(open) => {
        if (!open && !busy) onClose();
      }}
    >
      <Dialog.Content maxWidth="32rem">
        <Dialog.Title>
          {run ? `${DAY_LONG[run.day]} · ${hhmm(run.start)} → ${hhmm(run.end)}` : "Changement d'horloge"}
        </Dialog.Title>
        <Dialog.Description size="2" color="gray" mb="4">
          {run
            ? `À ${hhmm(run.start)}, cette heure type joue jusqu'au changement suivant.`
            : "À l'heure dite, l'heure type choisie joue jusqu'au changement suivant."}
        </Dialog.Description>
        <form
          className="prog-dialog-form"
          onSubmit={(event) => {
            event.preventDefault();
            void save();
          }}
        >
          <div className="prog-dialog-row">
            <div className="ui-field">
              <span className="ui-field-label">Heure type</span>
              <Select.Root size="2" value={clockId} onValueChange={setClockId}>
                <Select.Trigger className="ui-field-control" placeholder="Choisir" aria-label="Heure type" />
                <Select.Content variant="soft" position="popper">
                  {clocks.map((row) => (
                    <Select.Item key={row.id} value={String(row.id)}>
                      <span className="prog-clock-option">
                        <i className={`tint-${tints.get(row.id) ?? "gray"}`} aria-hidden="true" />
                        {row.name}
                      </span>
                    </Select.Item>
                  ))}
                </Select.Content>
              </Select.Root>
            </div>
            <div className="ui-field">
              <span className="ui-field-label">À partir de</span>
              <Select.Root
                size="2"
                value={String(minute)}
                disabled={midnightLocked}
                onValueChange={(value) => setMinute(Number(value))}
              >
                <Select.Trigger className="ui-field-control prog-time" aria-label="Heure du changement" />
                <Select.Content variant="soft" position="popper" className="prog-time-menu">
                  {times.map((value) => (
                    <Select.Item key={value} value={String(value)}>
                      {hhmm(value)}
                    </Select.Item>
                  ))}
                </Select.Content>
              </Select.Root>
            </div>
          </div>
          {midnightLocked ? (
            <p className="prog-dialog-note">Minuit ne bouge pas : chaque journée commence par une heure type.</p>
          ) : null}
          {conflict ? (
            <p className="prog-dialog-error">Il y a déjà un changement à {hhmm(minute)} ce jour-là.</p>
          ) : null}

          <div className="ui-field">
            <span className="ui-field-label">{run ? "Aussi les autres jours" : "Jours"}</span>
            <div className="prog-days" role="group" aria-label="Jours">
              {DAY_LETTER.map((letter, day) => {
                const on = days.includes(day);
                const fixed = editing != null && day === editing.day_of_week;
                return (
                  <button
                    key={day}
                    type="button"
                    className={`prog-day-toggle${on ? " is-on" : ""}${fixed ? " is-fixed" : ""}`}
                    aria-pressed={on}
                    aria-label={DAY_LONG[day]}
                    title={fixed ? `${DAY_LONG[day]} : le jour de cette plage` : DAY_LONG[day]}
                    onClick={() => toggle(day)}
                  >
                    {letter}
                  </button>
                );
              })}
              <span className="prog-days-presets">
                {PRESETS.map((preset) => (
                  <button
                    key={preset.label}
                    type="button"
                    className="prog-preset"
                    onClick={() => setDays(editing ? [...new Set([editing.day_of_week, ...preset.days])] : preset.days)}
                  >
                    {preset.label}
                  </button>
                ))}
              </span>
            </div>
          </div>

          <p className="prog-plan" aria-live="polite">
            {!clock || !days.length
              ? "Choisis une heure type et au moins un jour."
              : created + updated === 0
                ? "C'est déjà programmé ainsi."
                : [
                    created ? `${created} changement${created === 1 ? "" : "s"} créé${created === 1 ? "" : "s"}` : "",
                    updated ? `${updated} modifié${updated === 1 ? "" : "s"}` : "",
                  ]
                    .filter(Boolean)
                    .join(" · ") + ` : ${daySetLabel(days)} à ${hhmm(minute)}, ${clock.name}.`}
          </p>

          {confirming && run ? (
            <p className="prog-dialog-note">
              Retirer ce changement : la plage d'avant s'étendra jusqu'à {hhmm(run.end)}.
            </p>
          ) : null}

          {failure ? (
            <p className="prog-dialog-error" role="alert">
              {failure}
            </p>
          ) : null}

          <div className="prog-dialog-actions">
            {run && editing ? (
              <span className="prog-dialog-side">
                {midnightLocked ? null : (
                  <Button
                    type="button"
                    size="2"
                    variant={confirming ? "solid" : "ghost"}
                    color="red"
                    disabled={busy != null}
                    title={`La plage d'avant s'étendra jusqu'à ${hhmm(run.end)}.`}
                    onClick={() => (confirming ? void remove() : setConfirming(true))}
                  >
                    <Trash2 className="ui-button-icon" />
                    {busy === "delete" ? "Retrait…" : confirming ? "Confirmer" : "Retirer"}
                  </Button>
                )}
                {run.end - run.start > 30 ? (
                  <Button
                    type="button"
                    size="2"
                    variant="ghost"
                    color="gray"
                    disabled={busy != null}
                    onClick={() =>
                      onSplit(run.day, Math.min(run.end - 30, Math.ceil((run.start + run.end) / 2 / 60) * 60), null)
                    }
                  >
                    <Scissors className="ui-button-icon" />
                    Couper la plage
                  </Button>
                ) : null}
              </span>
            ) : null}
            <Dialog.Close>
              <Button type="button" size="2" variant="soft" color="gray" disabled={busy != null}>
                Annuler
              </Button>
            </Dialog.Close>
            <Button type="submit" size="2" highContrast disabled={busy != null || !clock || !days.length || conflict}>
              {busy === "save" ? "Enregistrement…" : "Enregistrer"}
            </Button>
          </div>
        </form>
      </Dialog.Content>
    </Dialog.Root>
  );
}
