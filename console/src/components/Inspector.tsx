import { Badge, Button, Spinner, Switch, TextField } from "@radix-ui/themes";
import { Clock3, MapPin, Repeat2, Save, Sparkles, Trash2, type LucideIcon } from "lucide-react";
import { useEffect, useState } from "react";
import { KIND_HELP, KIND_ORDER, KIND_LABELS } from "../api/clockMeta";
import { cartRef } from "../api/clockWrite";
import type { Cart, Category, Clock, ClockPosition, PositionKind } from "../api/types";
import { ConfirmDialog } from "../ui/ConfirmDialog";
import { FormField, SelectField } from "../ui/FormField";
import type { StudioSelection } from "./HourStrip";

type MutationResult = boolean | void | Promise<boolean | void>;

type InspectorProps = {
  selection: StudioSelection;
  clock: Clock;
  carts: Cart[];
  categories: Category[];
  busy?: boolean;
  /** Chaque changement de coupure s’enregistre, sans bouton. */
  autoSave?: boolean;
  onSaveClock: (patch: {
    name: string;
    fallback_cart: string;
    fallback_cart_id: number | null;
  }) => MutationResult;
  onSavePosition: (next: ClockPosition, motifIndex?: number) => MutationResult;
  onRemoveAnchor?: (minute: number) => MutationResult;
};

const NONE = "__none__";

function withOption(value: string, options: string[]): string[] {
  if (value && !options.includes(value)) return [value, ...options];
  return options;
}

function targetFor(clock: Clock, selection: StudioSelection): ClockPosition | null {
  if (selection.kind === "anchor") {
    return clock.anchors.find((row) => row.minute === selection.minute) ?? null;
  }
  if (selection.kind === "new-anchor") return null;
  if (selection.kind === "motif") return clock.motif[selection.index] ?? null;
  return null;
}

function InspectorHeader({
  icon: Icon,
  eyebrow,
  title,
  description,
  dirty,
  pending,
}: {
  icon: LucideIcon;
  eyebrow: string;
  title: string;
  description: string;
  dirty?: boolean;
  pending?: boolean;
}) {
  return (
    <header className="horloges-inspector-header">
      <span className="horloges-inspector-icon" aria-hidden="true">
        <Icon size={18} strokeWidth={1.75} />
      </span>
      <div className="horloges-inspector-heading">
        <span className="horloges-inspector-eyebrow">{eyebrow}</span>
        <div className="horloges-inspector-title-row">
          <h2>{title}</h2>
          {pending ? (
            <Badge size="1" color="gray" variant="soft">
              À créer
            </Badge>
          ) : dirty ? (
            <Badge size="1" color="gray" variant="soft">
              Modifié
            </Badge>
          ) : null}
        </div>
        <p>{description}</p>
      </div>
    </header>
  );
}

export function Inspector({
  selection,
  clock,
  carts,
  categories,
  busy = false,
  autoSave = false,
  onSaveClock,
  onSavePosition,
  onRemoveAnchor,
}: InspectorProps) {
  const source = targetFor(clock, selection);
  const isAnchor = selection.kind === "anchor" || selection.kind === "new-anchor";
  const isMotif = selection.kind === "motif";
  const minute = isAnchor ? selection.minute : undefined;

  if (selection.kind === "idle") {
    return (
      <ClockIdentity clock={clock} carts={carts} busy={busy} onSave={onSaveClock} />
    );
  }

  return (
    <PositionForm
      clock={clock}
      source={source}
      isAnchor={isAnchor}
      isNew={selection.kind === "new-anchor"}
      motifIndex={isMotif ? selection.index : null}
      minute={minute}
      carts={carts}
      categories={categories}
      busy={busy}
      autoSave={autoSave}
      onSavePosition={onSavePosition}
      onRemoveAnchor={onRemoveAnchor}
    />
  );
}

function ClockIdentity({
  clock,
  carts,
  busy,
  onSave,
}: {
  clock: Clock;
  carts: Cart[];
  busy: boolean;
  onSave: (patch: {
    name: string;
    fallback_cart: string;
    fallback_cart_id: number | null;
  }) => MutationResult;
}) {
  const [name, setName] = useState(clock.name);
  const [fallback, setFallback] = useState(clock.fallback_cart || NONE);
  const [dirty, setDirty] = useState(false);
  useEffect(() => {
    setName(clock.name);
    setFallback(clock.fallback_cart || NONE);
    setDirty(false);
  }, [clock]);
  const cartNames = withOption(clock.fallback_cart, carts.map((cart) => cart.title));

  return (
    <section className="app-clock-inspector">
      <InspectorHeader
        icon={Clock3}
        eyebrow="Inspecteur"
        title={clock.name}
        description="Réglages généraux. Si un bac est vide, un autre cart joue."
        dirty={dirty}
      />

      <div className="horloges-inspector-body">
        <FormField label="Nom de l’heure type" hint="Ce nom apparaît aussi dans la semaine.">
          <TextField.Root
            className="ui-field-control"
            value={name}
            disabled={busy}
            onChange={(event) => {
              setName(event.target.value);
              setDirty(true);
            }}
          />
        </FormField>
        <SelectField
          label="Si un bac est vide, jouer…"
          value={fallback || NONE}
          onValueChange={(value) => {
            setFallback(value);
            setDirty(true);
          }}
          disabled={busy}
          options={[
            { value: NONE, label: "Aucun" },
            ...cartNames.map((title) => ({ value: title, label: title })),
          ]}
          hint="Joué quand une étape n’a plus de titre dans son cart."
        />

        <div className="horloges-context-note">
          <Sparkles size={15} aria-hidden="true" />
          <p>Clique une étape, ou une coupure à la minute, pour la regarder.</p>
        </div>
      </div>

      <Button
        className="horloges-inspector-save"
        disabled={busy || !dirty || !name.trim()}
        onClick={() => {
          void (async () => {
            const chosen = fallback === NONE ? "" : fallback;
            const ref = cartRef(carts, chosen);
            const result = await onSave({
              name: name.trim(),
              fallback_cart: ref.cart ?? "",
              fallback_cart_id: ref.cart_id,
            });
            if (result !== false) setDirty(false);
          })();
        }}
      >
        {busy ? <Spinner size="1" /> : <Save className="ui-button-icon" />}
        {busy ? "Enregistrement…" : "Enregistrer"}
      </Button>
    </section>
  );
}

function PositionForm({
  clock,
  source,
  isAnchor,
  isNew,
  motifIndex,
  minute,
  carts,
  categories,
  busy,
  autoSave = false,
  onSavePosition,
  onRemoveAnchor,
}: {
  clock: Clock;
  source: ClockPosition | null;
  isAnchor: boolean;
  isNew: boolean;
  motifIndex: number | null;
  minute: number | undefined;
  carts: Cart[];
  categories: Category[];
  busy: boolean;
  autoSave?: boolean;
  onSavePosition: (next: ClockPosition, motifIndex?: number) => MutationResult;
  onRemoveAnchor?: (minute: number) => MutationResult;
}) {
  const [kind, setKind] = useState<PositionKind>(source?.kind ?? (isAnchor ? "pub" : "musique"));
  const [cible, setCible] = useState(source?.category ?? source?.cart ?? NONE);
  const [secours, setSecours] = useState(source?.fallback_cart || clock.fallback_cart || NONE);
  const [syncDure, setSyncDure] = useState((source?.sync ?? "dure") === "dure");
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    setKind(source?.kind ?? (isAnchor ? "pub" : "musique"));
    setCible(source?.category ?? source?.cart ?? NONE);
    setSecours(source?.fallback_cart || NONE);
    setSyncDure((source?.sync ?? "dure") === "dure");
    setDirty(false);
  }, [source?.id, source?.cart, source?.category, source?.fallback_cart, source?.kind, source?.sync, isAnchor, isNew, motifIndex, minute]);

  useEffect(() => {
    if (!isNew || cible !== NONE || kind === "musique") return;
    const pubCart = carts.find((cart) => /pub/i.test(cart.title))?.title;
    if (pubCart) setCible(pubCart);
  }, [isNew, cible, kind, carts]);

  const usesCategory = kind === "musique";
  const categoryNames = withOption(usesCategory ? (source?.category ?? "") : "", categories.map((c) => c.name));
  const cartNames = withOption(!usesCategory ? (source?.cart ?? "") : "", carts.map((c) => c.title));
  const fallbackNames = withOption(source?.fallback_cart || clock.fallback_cart, carts.map((c) => c.title));
  const pad = (value: number) => String(value).padStart(2, "0");
  const title = isAnchor
    ? `Coupure :${minute != null ? pad(minute) : ""}`
    : `Étape ${(motifIndex ?? 0) + 1}`;

  const save = async () => {
    const chosen = cible === NONE ? "" : cible;
    const cart = usesCategory ? { cart: null, cart_id: null } : cartRef(carts, chosen);
    const fallback = secours === NONE ? { cart: null, cart_id: null } : cartRef(carts, secours);
    const result = await onSavePosition(
      {
        id: source?.id,
        kind,
        when: isAnchor ? "anchored" : "sequential",
        cart: cart.cart,
        cart_id: cart.cart_id,
        category: usesCategory ? chosen || null : null,
        fallback_cart: fallback.cart,
        fallback_cart_id: fallback.cart_id,
        minute,
        sync: isAnchor ? (syncDure ? "dure" : "molle") : null,
      },
      isAnchor ? undefined : (motifIndex ?? 0),
    );
    if (result !== false) setDirty(false);
  };

  useEffect(() => {
    if (!autoSave || !dirty || busy) return;
    const timer = window.setTimeout(() => {
      void save();
    }, 280);
    return () => window.clearTimeout(timer);
  }, [autoSave, dirty, busy, kind, cible, secours, syncDure]);

  return (
    <section className="app-clock-inspector">
      <InspectorHeader
        icon={isAnchor ? MapPin : Repeat2}
        eyebrow={isAnchor ? "Coupure à la minute" : "Ce qui passe, dans l’ordre"}
        title={title}
        description={
          isAnchor
            ? isNew
              ? "Cette minute est seulement préparée. Enregistre pour créer la coupure."
              : `Coupure à :${minute != null ? pad(minute) : ""}. ${syncDure ? "Coupe à l’heure pile." : "Attend la fin du titre."}`
            : "Cette étape tourne dans l’ordre : Jingle, puis Programme."
        }
        dirty={dirty}
        pending={isNew}
      />

      <div className="horloges-inspector-body">
        <SelectField
          label="Type de contenu"
          value={kind}
          onValueChange={(value) => {
            setKind(value as PositionKind);
            setCible(NONE);
            setDirty(true);
          }}
          disabled={busy}
          options={KIND_ORDER.map((key) => ({
            value: key,
            label: KIND_LABELS[key],
          }))}
          hint={KIND_HELP[kind]}
        />

        {usesCategory ? (
          <SelectField
            label="Sélection de titres"
            value={cible || NONE}
            onValueChange={(value) => {
              setCible(value);
              setDirty(true);
            }}
            disabled={busy}
            options={[
              { value: NONE, label: "Choisir…" },
              ...categoryNames.filter(Boolean).map((name) => ({ value: name, label: name })),
            ]}
            hint="Facultatif. La musique tourne depuis un cart Programme, pas ici."
          />
        ) : (
          <SelectField
            label="Cart"
            value={cible || NONE}
            onValueChange={(value) => {
              setCible(value);
              setDirty(true);
            }}
            disabled={busy}
            options={[
              { value: NONE, label: "Choisir…" },
              ...cartNames.filter(Boolean).map((cartTitle) => ({
                value: cartTitle,
                label: cartTitle,
              })),
            ]}
            hint="Jingles, Prog, Pubs : un cart existant."
          />
        )}

        <SelectField
          label="Si cette étape est vide, jouer…"
          value={secours || NONE}
          onValueChange={(value) => {
            setSecours(value);
            setDirty(true);
          }}
          disabled={busy}
          options={[
            { value: NONE, label: "Celui de l’heure type" },
            ...fallbackNames.filter(Boolean).map((fallbackTitle) => ({
              value: fallbackTitle,
              label: fallbackTitle,
            })),
          ]}
          hint="Laisse celui de l’heure type pour reprendre le réglage général."
        />

        {isAnchor ? (
          <FormField
            label="Synchronisation"
            hint={
              syncDure
                ? "Coupe à l’heure pile : le programme en cours est coupé pour partir à la minute."
                : "Attend la fin du titre. La coupure est sautée si une autre, qui coupe à l’heure pile, arrive ensuite."
            }
          >
            <div className="horloges-sync-control">
              <Switch
                checked={syncDure}
                disabled={busy}
                onCheckedChange={(value) => {
                  setSyncDure(value === true);
                  setDirty(true);
                }}
              />
              <span>{syncDure ? "Coupe à l’heure pile" : "Attend la fin du titre"}</span>
            </div>
          </FormField>
        ) : (
          <div className="horloges-context-note">
            <Repeat2 size={15} aria-hidden="true" />
            <p>Après la dernière étape, la lecture reprend à la première.</p>
          </div>
        )}
      </div>

      <div className="horloges-inspector-actions">
        {autoSave ? null : (
          <Button disabled={busy} onClick={() => void save()}>
            {busy ? <Spinner size="1" /> : isNew ? <MapPin className="ui-button-icon" /> : <Save className="ui-button-icon" />}
            {busy ? "Enregistrement…" : isNew ? "Créer la coupure" : "Enregistrer"}
          </Button>
        )}
        {isAnchor && !isNew && minute != null && onRemoveAnchor ? (
          <ConfirmDialog
            title={`Retirer la coupure :${pad(minute)} ?`}
            description="La coupure à la minute disparaît. Ce qui passe reprend cette zone de l’heure."
            confirmLabel="Retirer la coupure"
            busy={busy}
            onConfirm={async () => {
              await onRemoveAnchor(minute);
            }}
            trigger={
              <Button color="red" variant="soft" disabled={busy}>
                <Trash2 className="ui-button-icon" />
                Retirer
              </Button>
            }
          />
        ) : null}
      </div>
    </section>
  );
}
