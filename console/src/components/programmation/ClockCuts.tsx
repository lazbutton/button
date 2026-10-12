import { Button, IconButton, Popover, SegmentedControl, TextField, Tooltip } from "@radix-ui/themes";
import { Plus, X } from "lucide-react";
import { useState } from "react";
import { defaultSource, minuteMark, stepKindLabel } from "../../api/programmationView";
import type { Cart, Category, Clock, ClockPosition, PositionKind } from "../../api/types";
import { withKind } from "./ClockSteps";
import { KindSelect, SourceSelect } from "./StepFields";

const QUICK = [0, 20, 40];

/** A cut at :00 is usually a jingle, the others pubs: the station's habit, not a rule. */
export function newCut(minute: number, carts: Cart[], categories: Category[], fallback: string | null): ClockPosition {
  const kind: PositionKind = minute === 0 ? "jingle" : "pub";
  return {
    kind,
    when: "anchored",
    minute,
    sync: "dure",
    fallback_cart: fallback,
    ...defaultSource(kind, carts, categories),
  };
}

export function ClockCuts({
  clock,
  carts,
  categories,
  highlight,
  onChange,
  onRemoved,
}: {
  clock: Clock;
  carts: Cart[];
  categories: Category[];
  highlight: number | null;
  onChange: (next: Clock) => void;
  onRemoved: (label: string, undo: (latest: Clock) => Clock) => void;
}) {
  const cuts = [...clock.anchors].sort((a, b) => (a.minute ?? 0) - (b.minute ?? 0));
  const taken = new Set(cuts.map((row) => row.minute ?? -1));

  const put = (minute: number, next: ClockPosition) => {
    const anchors = clock.anchors.filter((row) => row.minute !== minute);
    anchors.push(next);
    anchors.sort((a, b) => (a.minute ?? 0) - (b.minute ?? 0));
    onChange({ ...clock, anchors });
  };

  const add = (minute: number) => {
    if (taken.has(minute)) return;
    put(minute, newCut(minute, carts, categories, null));
  };

  const remove = (cut: ClockPosition) => {
    const minute = cut.minute ?? 0;
    onChange({ ...clock, anchors: clock.anchors.filter((row) => row.minute !== minute) });
    onRemoved(`Coupure ${minuteMark(minute)} retirée`, (latest) => {
      if (latest.anchors.some((row) => row.minute === minute)) return latest;
      const back = { ...cut };
      delete back.id;
      const anchors = [...latest.anchors, back].sort((a, b) => (a.minute ?? 0) - (b.minute ?? 0));
      return { ...latest, anchors };
    });
  };

  return (
    <section className="prog-card" aria-labelledby="prog-cuts-title" id="prog-cuts">
      <header className="prog-card-head">
        <div>
          <h3 id="prog-cuts-title">Coupures à la minute</h3>
          <p>À la minute dite, une étape passe devant ce qui tourne.</p>
        </div>
        <div className="prog-quick">
          {QUICK.filter((minute) => !taken.has(minute)).map((minute) => (
            <Button key={minute} size="1" variant="soft" color="gray" onClick={() => add(minute)}>
              <Plus className="ui-button-icon" />
              {minuteMark(minute)}
            </Button>
          ))}
          <MinutePicker taken={taken} label="Autre minute" onPick={add} />
        </div>
      </header>
      {cuts.length ? (
        <ul className="prog-cuts">
          {cuts.map((cut) => {
            const minute = cut.minute ?? 0;
            return (
              <li key={minute} className={`prog-cut${highlight === minute ? " is-flash" : ""}`} data-minute={minute}>
                <MinutePicker
                  taken={taken}
                  current={minute}
                  label={`Déplacer la coupure ${minuteMark(minute)}`}
                  onPick={(next) => {
                    const anchors = clock.anchors
                      .map((row) => (row.minute === minute ? { ...row, minute: next } : row))
                      .sort((a, b) => (a.minute ?? 0) - (b.minute ?? 0));
                    onChange({ ...clock, anchors });
                  }}
                />
                <KindSelect
                  value={cut.kind}
                  label={`Type de la coupure ${minuteMark(minute)}`}
                  onChange={(kind) => put(minute, withKind(cut, kind, carts, categories))}
                />
                <SourceSelect
                  step={cut}
                  carts={carts}
                  categories={categories}
                  label={`Ce que joue la coupure ${minuteMark(minute)}`}
                  onCart={(cart) => put(minute, { ...cut, cart: cart.title, cart_id: cart.id, category: null })}
                  onSelection={(name) => put(minute, { ...cut, category: name, cart: null, cart_id: null })}
                />
                <SegmentedControl.Root
                  size="1"
                  className="prog-sync"
                  value={cut.sync === "molle" ? "molle" : "dure"}
                  onValueChange={(value) => put(minute, { ...cut, sync: value as "dure" | "molle" })}
                  aria-label={`Moment de la coupure ${minuteMark(minute)}`}
                >
                  <SegmentedControl.Item value="dure">Coupe pile</SegmentedControl.Item>
                  <SegmentedControl.Item value="molle">Attend la fin</SegmentedControl.Item>
                </SegmentedControl.Root>
                <Tooltip content={`Retirer la coupure ${minuteMark(minute)}`}>
                  <IconButton
                    size="2"
                    variant="ghost"
                    color="gray"
                    className="prog-cut-remove"
                    aria-label={`Retirer la coupure ${minuteMark(minute)} (${stepKindLabel(cut.kind)})`}
                    onClick={() => remove(cut)}
                  >
                    <X size={16} />
                  </IconButton>
                </Tooltip>
              </li>
            );
          })}
        </ul>
      ) : (
        <p className="prog-card-empty">Aucune coupure : les étapes tournent sans s'arrêter de toute l'heure.</p>
      )}
      {cuts.some((cut) => cut.sync === "molle") ? (
        <p className="prog-card-note">
          « Attend la fin » laisse finir le titre en cours ; la coupure saute si une coupure « pile » suit de près.
        </p>
      ) : null}
    </section>
  );
}

/** A minute of the hour, typed: for a new cut, or to move one. */
function MinutePicker({
  taken,
  current,
  label,
  onPick,
}: {
  taken: Set<number>;
  current?: number;
  label: string;
  onPick: (minute: number) => void;
}) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const value = Number(text);
  const valid = text.trim() !== "" && Number.isInteger(value) && value >= 0 && value <= 59;
  const clash = valid && value !== current && taken.has(value);

  const submit = () => {
    if (!valid || clash) return;
    if (value !== current) onPick(value);
    setOpen(false);
  };

  return (
    <Popover.Root
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (next) setText(current != null ? String(current) : "");
      }}
    >
      <Popover.Trigger>
        {current != null ? (
          <button type="button" className="prog-cut-minute" aria-label={label}>
            {minuteMark(current)}
          </button>
        ) : (
          <Button size="1" variant="soft" color="gray">
            <Plus className="ui-button-icon" />
            {label}
          </Button>
        )}
      </Popover.Trigger>
      <Popover.Content className="prog-minute-pop" align="start" sideOffset={6}>
        <form
          onSubmit={(event) => {
            event.preventDefault();
            submit();
          }}
        >
          <label className="ui-field">
            <span className="ui-field-label">Minute de l'heure</span>
            <TextField.Root
              size="2"
              type="number"
              min={0}
              max={59}
              autoFocus
              value={text}
              onChange={(event) => setText(event.target.value)}
            >
              <TextField.Slot>:</TextField.Slot>
            </TextField.Root>
            {clash ? (
              <span className="ui-field-error">Il y a déjà une coupure à {minuteMark(value)}.</span>
            ) : (
              <span className="ui-field-hint">De 0 à 59.</span>
            )}
          </label>
          <Button type="submit" size="2" highContrast disabled={!valid || clash}>
            {current != null ? "Déplacer" : "Ajouter"}
          </Button>
        </form>
      </Popover.Content>
    </Popover.Root>
  );
}
