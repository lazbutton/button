import { Button, DropdownMenu, IconButton, Tooltip } from "@radix-ui/themes";
import {
  ArrowDown,
  ArrowUp,
  ChevronDown,
  Copy,
  GripVertical,
  LifeBuoy,
  MoreHorizontal,
  Plus,
  Trash2,
  Wrench,
} from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { defaultSource, STEP_KINDS, stepKindLabel, usesSelection } from "../../api/programmationView";
import type { Cart, Category, Clock, ClockPosition, PositionKind } from "../../api/types";
import { KindSelect, SourceSelect, sourceOf } from "./StepFields";

const CLOCK_FALLBACK = "__clock__";

/** A step switching kind keeps its bac when it can, and picks a sélection when it turns to titres. */
export function withKind(
  step: ClockPosition,
  kind: PositionKind,
  carts: Cart[],
  categories: Category[],
): ClockPosition {
  if (kind === step.kind) return step;
  const keepsCart = !usesSelection(kind) && !usesSelection(step.kind) && Boolean(step.cart);
  return { ...step, kind, ...(keepsCart ? {} : defaultSource(kind, carts, categories)) };
}

export function ClockSteps({
  clock,
  carts,
  categories,
  onChange,
  onRemoved,
  onRepair,
}: {
  clock: Clock;
  carts: Cart[];
  categories: Category[];
  onChange: (next: Clock) => void;
  /** Says a step left, with a way back applied to the heure type as it is then. */
  onRemoved: (label: string, undo: (latest: Clock) => Clock) => void;
  onRepair: (index: number) => void;
}) {
  const [dragging, setDragging] = useState<number | null>(null);
  const [dropAt, setDropAt] = useState<number | null>(null);
  const steps = clock.motif;

  const setStep = (index: number, next: ClockPosition) => {
    const motif = steps.slice();
    motif[index] = next;
    onChange({ ...clock, motif });
  };

  const move = (from: number, to: number) => {
    if (from === to || to < 0 || to >= steps.length) return;
    const motif = steps.slice();
    const [row] = motif.splice(from, 1);
    motif.splice(to, 0, row);
    onChange({ ...clock, motif });
  };

  const add = (kind: PositionKind) => {
    const step: ClockPosition = {
      kind,
      when: "sequential",
      fallback_cart: null,
      ...defaultSource(kind, carts, categories),
    };
    onChange({ ...clock, motif: [...steps, step] });
  };

  const remove = (index: number) => {
    const removed = steps[index];
    onChange({ ...clock, motif: steps.filter((_, at) => at !== index) });
    onRemoved(`Étape ${index + 1} retirée (${stepKindLabel(removed.kind)})`, (latest) => {
      const motif = latest.motif.slice();
      const back = { ...removed };
      delete back.id;
      motif.splice(Math.min(index, motif.length), 0, back);
      return { ...latest, motif };
    });
  };

  return (
    <section className="prog-card" aria-labelledby="prog-steps-title">
      <header className="prog-card-head">
        <div>
          <h3 id="prog-steps-title">Ce qui passe, dans l'ordre</h3>
          <p>Après la dernière étape, la lecture reprend à la première.</p>
        </div>
        <AddStepMenu onAdd={add} />
      </header>
      <ol className="prog-steps">
        {steps.map((step, index) => {
          const source = sourceOf(step, carts, categories);
          const only = steps.length === 1;
          const fallback = step.fallback_cart?.trim() || "";
          return (
            <li
              key={`${step.id ?? "new"}-${index}`}
              className={[
                "prog-step",
                dragging === index ? "is-dragging" : "",
                dropAt === index && dragging != null && dragging !== index ? "is-drop" : "",
              ]
                .filter(Boolean)
                .join(" ")}
              onDragOver={(event) => {
                if (dragging == null) return;
                event.preventDefault();
                setDropAt(index);
              }}
              onDrop={(event) => {
                event.preventDefault();
                if (dragging != null) move(dragging, index);
                setDragging(null);
                setDropAt(null);
              }}
            >
              <span
                className="prog-step-grip"
                draggable
                title="Glisser pour déplacer"
                onDragStart={(event) => {
                  event.dataTransfer.effectAllowed = "move";
                  setDragging(index);
                }}
                onDragEnd={() => {
                  setDragging(null);
                  setDropAt(null);
                }}
              >
                <GripVertical size={14} aria-hidden="true" />
                <span className="prog-step-rank">{index + 1}</span>
              </span>
              <KindSelect
                value={step.kind}
                label={`Type de l'étape ${index + 1}`}
                onChange={(kind) => setStep(index, withKind(step, kind, carts, categories))}
              />
              <SourceSelect
                step={step}
                carts={carts}
                categories={categories}
                label={`Ce que joue l'étape ${index + 1}`}
                onCart={(cart) => setStep(index, { ...step, cart: cart.title, cart_id: cart.id, category: null })}
                onSelection={(name) => setStep(index, { ...step, category: name, cart: null, cart_id: null })}
              />
              <span className="prog-step-info">
                {source.missing ? (
                  <>
                    <span className="prog-warn">Introuvable</span>
                    {!usesSelection(step.kind) ? (
                      <Button size="1" variant="soft" color="gray" onClick={() => onRepair(index)}>
                        <Wrench className="ui-button-icon" />
                        Réparer
                      </Button>
                    ) : null}
                  </>
                ) : source.cart ? (
                  <Link to={`/sons?id=${source.cart.id}`} className="prog-link">
                    {source.cart.mode === "relay"
                      ? "Relais"
                      : `${source.cart.sounds.length} son${source.cart.sounds.length === 1 ? "" : "s"}`}
                  </Link>
                ) : source.selection ? (
                  <Link to="/programmation?onglet=categories" className="prog-link">
                    {source.selection.count} titre{source.selection.count === 1 ? "" : "s"}
                  </Link>
                ) : (
                  <span className="prog-warn">À choisir</span>
                )}
                {fallback ? (
                  <Tooltip content={`Si l'étape n'a rien à passer : ${fallback}`}>
                    <span className="prog-step-fallback">
                      <LifeBuoy size={12} aria-hidden="true" />
                      {fallback}
                    </span>
                  </Tooltip>
                ) : null}
              </span>
              <DropdownMenu.Root modal={false}>
                <DropdownMenu.Trigger>
                  <IconButton
                    size="2"
                    variant="ghost"
                    color="gray"
                    className="prog-step-menu"
                    aria-label={`Actions de l'étape ${index + 1}`}
                  >
                    <MoreHorizontal size={16} />
                  </IconButton>
                </DropdownMenu.Trigger>
                <DropdownMenu.Content variant="soft" align="end" className="prog-menu">
                  <DropdownMenu.Item disabled={index === 0} onSelect={() => move(index, index - 1)}>
                    <ArrowUp size={15} aria-hidden="true" />
                    Monter
                  </DropdownMenu.Item>
                  <DropdownMenu.Item disabled={index === steps.length - 1} onSelect={() => move(index, index + 1)}>
                    <ArrowDown size={15} aria-hidden="true" />
                    Descendre
                  </DropdownMenu.Item>
                  <DropdownMenu.Item
                    onSelect={() => {
                      const motif = steps.slice();
                      const copy = { ...step };
                      delete copy.id;
                      motif.splice(index + 1, 0, copy);
                      onChange({ ...clock, motif });
                    }}
                  >
                    <Copy size={15} aria-hidden="true" />
                    Dupliquer
                  </DropdownMenu.Item>
                  <DropdownMenu.Sub>
                    <DropdownMenu.SubTrigger>
                      <LifeBuoy size={15} aria-hidden="true" />
                      Si l'étape est vide
                    </DropdownMenu.SubTrigger>
                    <DropdownMenu.SubContent className="prog-menu">
                      <DropdownMenu.RadioGroup
                        value={fallback || CLOCK_FALLBACK}
                        onValueChange={(value) => {
                          const cart = carts.find((row) => row.title === value);
                          setStep(index, {
                            ...step,
                            fallback_cart: cart ? cart.title : null,
                            fallback_cart_id: cart ? cart.id : null,
                          });
                        }}
                      >
                        <DropdownMenu.RadioItem value={CLOCK_FALLBACK}>Comme l'heure type</DropdownMenu.RadioItem>
                        <DropdownMenu.Separator />
                        {carts
                          .filter((cart) => cart.mode !== "relay")
                          .map((cart) => (
                            <DropdownMenu.RadioItem key={cart.id} value={cart.title}>
                              {cart.title}
                            </DropdownMenu.RadioItem>
                          ))}
                      </DropdownMenu.RadioGroup>
                    </DropdownMenu.SubContent>
                  </DropdownMenu.Sub>
                  <DropdownMenu.Separator />
                  <DropdownMenu.Item color="red" disabled={only} onSelect={() => remove(index)}>
                    <Trash2 size={15} aria-hidden="true" />
                    {only ? "Retirer (il en faut au moins une)" : "Retirer"}
                  </DropdownMenu.Item>
                </DropdownMenu.Content>
              </DropdownMenu.Root>
            </li>
          );
        })}
      </ol>
    </section>
  );
}

function AddStepMenu({ onAdd }: { onAdd: (kind: PositionKind) => void }) {
  return (
    <DropdownMenu.Root modal={false}>
      <DropdownMenu.Trigger>
        <Button size="2" variant="soft" color="gray">
          <Plus className="ui-button-icon" />
          Étape
          <ChevronDown size={13} aria-hidden="true" />
        </Button>
      </DropdownMenu.Trigger>
      <DropdownMenu.Content variant="soft" align="end" className="prog-menu">
        {STEP_KINDS.map((item) => (
          <DropdownMenu.Item key={item.kind} onSelect={() => onAdd(item.kind)}>
            <span className={`prog-dot is-${item.kind}`} aria-hidden="true" />
            <span className="prog-menu-copy">
              {item.label}
              <small>{item.hint}</small>
            </span>
          </DropdownMenu.Item>
        ))}
      </DropdownMenu.Content>
    </DropdownMenu.Root>
  );
}
