import { Select } from "@radix-ui/themes";
import { BAC_KINDS, bacKind } from "../../api/soundsView";
import { STEP_KINDS, stepKindLabel, usesSelection } from "../../api/programmationView";
import type { Cart, Category, ClockPosition, PositionKind } from "../../api/types";

const MISSING = "__missing__";
const NONE = "__none__";

/** Jingle, Titres, Programme or Pub. */
export function KindSelect({
  value,
  label,
  onChange,
}: {
  value: PositionKind;
  label: string;
  onChange: (kind: PositionKind) => void;
}) {
  return (
    <Select.Root size="2" value={value} onValueChange={(next) => onChange(next as PositionKind)}>
      <Select.Trigger variant="soft" color="gray" className={`prog-kind is-${value}`} aria-label={label}>
        <span className={`prog-dot is-${value}`} aria-hidden="true" />
        {stepKindLabel(value)}
      </Select.Trigger>
      <Select.Content variant="soft" position="popper" className="prog-select-menu">
        {STEP_KINDS.map((item) => (
          <Select.Item key={item.kind} value={item.kind}>
            <span className="prog-kind-option">
              <span className={`prog-dot is-${item.kind}`} aria-hidden="true" />
              <span>
                <strong>{item.label}</strong>
                <small>{item.hint}</small>
              </span>
            </span>
          </Select.Item>
        ))}
      </Select.Content>
    </Select.Root>
  );
}

export function sourceOf(step: ClockPosition, carts: Cart[], categories: Category[]) {
  if (usesSelection(step.kind)) {
    const name = (step.category || "").trim();
    const selection = name ? (categories.find((row) => row.name === name) ?? null) : null;
    return { cart: null, selection, missing: Boolean(name) && !selection, empty: !name };
  }
  const title = (step.cart || "").trim();
  const cart =
    carts.find((row) => step.cart_id != null && row.id === step.cart_id) ??
    (title ? carts.find((row) => row.title.trim().toLowerCase() === title.toLowerCase()) : undefined) ??
    null;
  return { cart, selection: null, missing: Boolean(title) && !cart, empty: !title };
}

/** The bac (or the sélection, for titres) a step plays from. */
export function SourceSelect({
  step,
  carts,
  categories,
  label,
  onCart,
  onSelection,
}: {
  step: ClockPosition;
  carts: Cart[];
  categories: Category[];
  label: string;
  onCart: (cart: Cart) => void;
  onSelection: (name: string) => void;
}) {
  const source = sourceOf(step, carts, categories);
  if (usesSelection(step.kind)) {
    const value = source.selection ? source.selection.name : source.missing ? MISSING : NONE;
    return (
      <Select.Root
        size="2"
        value={value}
        onValueChange={(next) => {
          if (next !== MISSING && next !== NONE) onSelection(next);
        }}
      >
        <Select.Trigger
          className={`prog-source${source.missing || source.empty ? " is-missing" : ""}`}
          aria-label={label}
        />
        <Select.Content variant="soft" position="popper" className="prog-select-menu">
          {value === NONE ? (
            <Select.Item value={NONE} disabled>
              Choisir une sélection
            </Select.Item>
          ) : null}
          {source.missing ? (
            <Select.Item value={MISSING} disabled>
              « {step.category} » (introuvable)
            </Select.Item>
          ) : null}
          {categories.length ? (
            categories.map((row) => (
              <Select.Item key={row.id} value={row.name}>
                <span className="prog-source-option">
                  {row.name}
                  <small>
                    {row.count} titre{row.count === 1 ? "" : "s"}
                  </small>
                </span>
              </Select.Item>
            ))
          ) : (
            <Select.Item value="__empty__" disabled>
              Aucune sélection : crée-en une dans Sélections de titres
            </Select.Item>
          )}
        </Select.Content>
      </Select.Root>
    );
  }

  const value = source.cart ? String(source.cart.id) : source.missing ? MISSING : NONE;
  const groups = BAC_KINDS.map((kind) => ({
    ...kind,
    carts: carts.filter((cart) => bacKind(cart) === kind.id),
  })).filter((group) => group.carts.length);
  return (
    <Select.Root
      size="2"
      value={value}
      onValueChange={(next) => {
        const cart = carts.find((row) => String(row.id) === next);
        if (cart) onCart(cart);
      }}
    >
      <Select.Trigger
        className={`prog-source${source.missing || source.empty ? " is-missing" : ""}`}
        aria-label={label}
      />
      <Select.Content variant="soft" position="popper" className="prog-select-menu">
        {value === NONE ? (
          <Select.Item value={NONE} disabled>
            Choisir un bac
          </Select.Item>
        ) : null}
        {source.missing ? (
          <Select.Item value={MISSING} disabled>
            « {step.cart} » (introuvable)
          </Select.Item>
        ) : null}
        {groups.map((group, index) => (
          <Select.Group key={group.id}>
            {index > 0 ? <Select.Separator /> : null}
            <Select.Label>{group.plural}</Select.Label>
            {group.carts.map((cart) => (
              <Select.Item key={cart.id} value={String(cart.id)}>
                <span className="prog-source-option">
                  {cart.title}
                  <small>
                    {cart.mode === "relay"
                      ? "relais"
                      : `${cart.sounds.length} son${cart.sounds.length === 1 ? "" : "s"}`}
                  </small>
                </span>
              </Select.Item>
            ))}
          </Select.Group>
        ))}
      </Select.Content>
    </Select.Root>
  );
}
