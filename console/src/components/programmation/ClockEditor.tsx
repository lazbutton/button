import { DropdownMenu, IconButton, Select, Spinner } from "@radix-ui/themes";
import { AlertTriangle, ArrowLeft, ArrowUpRight, Check, Clock3, Copy, MoreHorizontal, Trash2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { cutsSummary, nameTaken, usesSelection } from "../../api/programmationView";
import type { SaveState } from "../../api/useClockSaver";
import type { Cart, Category, Clock } from "../../api/types";
import { ClockCuts, newCut } from "./ClockCuts";
import { ClockSteps } from "./ClockSteps";
import { HourBar } from "./HourBar";
import { sourceOf } from "./StepFields";

const NO_FALLBACK = "__none__";

export function ClockEditor({
  clock,
  carts,
  categories,
  otherNames,
  usage,
  tint,
  onAir,
  saveState,
  saveError,
  onRetry,
  onRevert,
  onChange,
  onRemoved,
  onRepair,
  onDuplicate,
  onDelete,
  onBack,
}: {
  clock: Clock;
  carts: Cart[];
  categories: Category[];
  otherNames: string[];
  usage: string[];
  tint: string;
  onAir: boolean;
  saveState: SaveState;
  /** Why the last write was refused, while the changes wait on screen. */
  saveError: string | null;
  onRetry: () => void;
  onRevert: () => void;
  onChange: (next: Clock) => void;
  onRemoved: (label: string, undo: (latest: Clock) => Clock) => void;
  onRepair: (index: number) => void;
  onDuplicate: () => void;
  onDelete: () => void;
  onBack: () => void;
}) {
  const [flash, setFlash] = useState<number | null>(null);
  const cuts = cutsSummary(clock);
  const fallbackKnown = carts.some((cart) => cart.title === clock.fallback_cart);
  const broken = [
    ...new Set(
      [...clock.motif, ...clock.anchors]
        .filter((step) => sourceOf(step, carts, categories).missing)
        .map((step) => (usesSelection(step.kind) ? step.category : step.cart) || "")
        .concat(clock.fallback_cart && !fallbackKnown ? [clock.fallback_cart] : []),
    ),
  ].filter(Boolean);

  const showCut = (minute: number) => {
    setFlash(minute);
    document
      .querySelector(`.prog-cut[data-minute="${minute}"]`)
      ?.scrollIntoView({ block: "nearest", behavior: "smooth" });
    window.setTimeout(() => setFlash((current) => (current === minute ? null : current)), 1400);
  };

  return (
    <section className="prog-main" aria-label={`Heure type ${clock.name}`}>
      <header className="prog-head">
        <IconButton
          size="2"
          variant="ghost"
          color="gray"
          className="prog-back"
          aria-label="Retour aux heures types"
          onClick={onBack}
        >
          <ArrowLeft size={18} />
        </IconButton>
        <span className={`prog-tile prog-tile--lg tint-${tint}`} aria-hidden="true">
          <Clock3 size={18} strokeWidth={1.75} />
        </span>
        <div className="prog-head-copy">
          <NameField name={clock.name} otherNames={otherNames} onCommit={(name) => onChange({ ...clock, name })} />
          <p className="prog-facts">
            <span>
              {clock.motif.length} étape{clock.motif.length === 1 ? "" : "s"}
            </span>
            <span>{cuts ? `Coupures ${cuts}` : "Sans coupure"}</span>
            <span className={`prog-state${onAir ? " is-live" : ""}`}>
              {onAir ? <i aria-hidden="true" /> : null}
              {onAir
                ? "À l'antenne"
                : usage.length
                  ? usage[0] + (usage.length > 1 ? ` +${usage.length - 1}` : "")
                  : "Hors semaine"}
            </span>
          </p>
        </div>
        <div className="prog-head-actions">
          <SaveIndicator
            state={saveError ? "error" : saveState}
            reason={saveError}
            onRetry={onRetry}
            onRevert={onRevert}
          />
          <DropdownMenu.Root>
            <DropdownMenu.Trigger>
              <IconButton size="2" variant="ghost" color="gray" aria-label="Actions de l'heure type">
                <MoreHorizontal size={17} />
              </IconButton>
            </DropdownMenu.Trigger>
            <DropdownMenu.Content align="end" className="prog-menu">
              <DropdownMenu.Item onSelect={onDuplicate}>
                <Copy size={15} aria-hidden="true" />
                Dupliquer…
              </DropdownMenu.Item>
              <DropdownMenu.Separator />
              <DropdownMenu.Item color="red" disabled={usage.length > 0} onSelect={onDelete}>
                <Trash2 size={15} aria-hidden="true" />
                <span className="prog-menu-copy">
                  Supprimer…
                  {usage.length ? <small>Posée dans la semaine : retire-la d'abord</small> : null}
                </span>
              </DropdownMenu.Item>
            </DropdownMenu.Content>
          </DropdownMenu.Root>
        </div>
      </header>

      <div className="prog-body">
        {broken.length ? (
          <p className="prog-alert" role="note">
            <AlertTriangle size={15} aria-hidden="true" />
            <span>
              Cette heure type cite{" "}
              {broken.length === 1 ? "un élément qui n'existe plus" : "des éléments qui n'existent plus"} :{" "}
              {broken.map((name) => `« ${name} »`).join(", ")}.{" "}
              {broken.length === 1
                ? "Le moteur refuse de l'enregistrer tant qu'il n'est pas remplacé (en rouge ci-dessous)."
                : "Le moteur refuse de l'enregistrer tant qu'ils ne sont pas remplacés (en rouge ci-dessous)."}
            </span>
          </p>
        ) : null}
        <section className="prog-card prog-card--hour" aria-label="L'heure en un coup d'œil">
          <HourBar
            clock={clock}
            onShowCut={showCut}
            onAddCut={(minute) => {
              const anchors = [...clock.anchors, newCut(minute, carts, categories, null)].sort(
                (a, b) => (a.minute ?? 0) - (b.minute ?? 0),
              );
              onChange({ ...clock, anchors });
              window.setTimeout(() => showCut(minute), 60);
            }}
          />
        </section>

        <ClockSteps
          clock={clock}
          carts={carts}
          categories={categories}
          onChange={onChange}
          onRemoved={onRemoved}
          onRepair={onRepair}
        />

        <ClockCuts
          clock={clock}
          carts={carts}
          categories={categories}
          highlight={flash}
          onChange={onChange}
          onRemoved={onRemoved}
        />

        <div className="prog-pair">
          <section className="prog-card" aria-labelledby="prog-fallback-title">
            <header className="prog-card-head">
              <div>
                <h3 id="prog-fallback-title">Si une étape est vide</h3>
                <p>Ce bac joue quand une étape n'a plus rien à passer.</p>
              </div>
            </header>
            <Select.Root
              size="2"
              value={clock.fallback_cart ? clock.fallback_cart : NO_FALLBACK}
              onValueChange={(value) => {
                const cart = carts.find((row) => row.title === value);
                onChange({
                  ...clock,
                  fallback_cart: cart ? cart.title : "",
                  fallback_cart_id: cart ? cart.id : null,
                });
              }}
            >
              <Select.Trigger className="prog-fallback" aria-label="Bac de secours" />
              <Select.Content position="popper" className="prog-select-menu">
                <Select.Item value={NO_FALLBACK}>Rien : un blanc plutôt qu'un secours</Select.Item>
                {clock.fallback_cart && !fallbackKnown ? (
                  <Select.Item value={clock.fallback_cart} disabled>
                    « {clock.fallback_cart} » (introuvable)
                  </Select.Item>
                ) : null}
                <Select.Separator />
                {carts
                  .filter((cart) => cart.mode !== "relay")
                  .map((cart) => (
                    <Select.Item key={cart.id} value={cart.title}>
                      {cart.title}
                    </Select.Item>
                  ))}
              </Select.Content>
            </Select.Root>
          </section>

          <section className="prog-card" aria-labelledby="prog-week-title">
            <header className="prog-card-head">
              <div>
                <h3 id="prog-week-title">Dans la semaine</h3>
                <p>
                  {usage.length ? "Les plages où cette heure type joue." : "Elle ne joue nulle part pour l'instant."}
                </p>
              </div>
            </header>
            {usage.length ? (
              <ul className="prog-usage">
                {usage.map((line) => (
                  <li key={line}>{line}</li>
                ))}
              </ul>
            ) : null}
            <Link to="/programmation?onglet=semaine" className="prog-link prog-link--arrow">
              {usage.length ? "Ouvrir la semaine" : "La poser dans la semaine"}
              <ArrowUpRight size={13} aria-hidden="true" />
            </Link>
          </section>
        </div>
      </div>
    </section>
  );
}

/** The name, edited in place: Entrée or leaving the field saves, Échap gives it back. */
function NameField({
  name,
  otherNames,
  onCommit,
}: {
  name: string;
  otherNames: string[];
  onCommit: (name: string) => void;
}) {
  const [draft, setDraft] = useState(name);
  const ref = useRef<HTMLInputElement>(null);
  useEffect(() => setDraft(name), [name]);
  const trimmed = draft.trim();
  const problem = !trimmed
    ? "Il faut un nom."
    : nameTaken(trimmed, otherNames)
      ? "Une autre heure type porte déjà ce nom."
      : "";

  const commit = () => {
    if (problem || trimmed === name) {
      if (problem) setDraft(name);
      return;
    }
    onCommit(trimmed);
  };

  return (
    <div className="prog-name">
      <input
        ref={ref}
        className="prog-name-input"
        value={draft}
        aria-label="Nom de l'heure type"
        aria-invalid={Boolean(problem) || undefined}
        spellCheck={false}
        onChange={(event) => setDraft(event.target.value)}
        onBlur={commit}
        onKeyDown={(event) => {
          if (event.key === "Enter") ref.current?.blur();
          if (event.key === "Escape") {
            setDraft(name);
            requestAnimationFrame(() => ref.current?.blur());
          }
        }}
      />
      {problem && draft !== name ? <span className="prog-name-error">{problem} Échap pour annuler.</span> : null}
    </div>
  );
}

function SaveIndicator({
  state,
  reason,
  onRetry,
  onRevert,
}: {
  state: SaveState;
  reason: string | null;
  onRetry: () => void;
  onRevert: () => void;
}) {
  if (state === "idle") return null;
  if (state === "error") {
    return (
      <DropdownMenu.Root>
        <DropdownMenu.Trigger>
          <button type="button" className="prog-save is-error" aria-label={`Non enregistré : ${reason ?? ""}`}>
            <AlertTriangle size={14} aria-hidden="true" />
            Non enregistré
          </button>
        </DropdownMenu.Trigger>
        <DropdownMenu.Content align="end" className="prog-menu prog-save-menu">
          {reason ? <DropdownMenu.Label className="prog-save-reason">{reason}</DropdownMenu.Label> : null}
          <DropdownMenu.Item onSelect={onRetry}>Réessayer d'enregistrer</DropdownMenu.Item>
          <DropdownMenu.Item onSelect={onRevert}>Revenir à la version enregistrée</DropdownMenu.Item>
        </DropdownMenu.Content>
      </DropdownMenu.Root>
    );
  }
  return (
    <span className={`prog-save is-${state}`} role="status" aria-live="polite">
      {state === "saving" ? <Spinner size="1" /> : <Check size={14} aria-hidden="true" />}
      {state === "saving" ? "Enregistrement…" : "Enregistré"}
    </span>
  );
}
