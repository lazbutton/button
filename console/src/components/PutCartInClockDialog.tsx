import { Button, Dialog, Flex, Spinner } from "@radix-ui/themes";
import { Clock3 } from "lucide-react";
import { useEffect, useState } from "react";
import {
  clockAtWall,
  guessCartKind,
  kindLabel,
} from "../api/clockMeta";
import { ApiRequestError } from "../api/client";
import { putCartInClock, saveClock } from "../api/clockWrite";
import type { Cart, Clock, PositionKind, Slot } from "../api/types";
import { SelectField } from "../ui/FormField";

const CART_KINDS: Exclude<PositionKind, "musique">[] = ["jingle", "son", "pub"];

export function PutCartInClockDialog({
  cart: cartProp,
  clocks,
  slots,
  carts,
  rundownClock,
  fixedClock,
  trigger,
  open: openProp,
  onOpenChange,
  busy = false,
  onDone,
  onError,
}: {
  cart?: Cart | null;
  clocks: Clock[];
  slots: Slot[];
  carts: Cart[];
  rundownClock?: string | null;
  fixedClock?: Clock | null;
  trigger?: React.ReactNode;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  busy?: boolean;
  onDone: (message: string) => void;
  onError: (message: string) => void;
}) {
  const [internalOpen, setInternalOpen] = useState(false);
  const open = openProp ?? internalOpen;
  const setOpen = onOpenChange ?? setInternalOpen;
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const defaultClock = fixedClock ?? clockAtWall(clocks, slots, new Date(), rundownClock);
  const [clockId, setClockId] = useState(String(defaultClock?.id ?? clocks[0]?.id ?? ""));
  const [cartId, setCartId] = useState(String(cartProp?.id ?? ""));
  const pickedCart = cartProp ?? carts.find((row) => String(row.id) === cartId) ?? null;
  const [kind, setKind] = useState<Exclude<PositionKind, "musique">>(
    guessCartKind(pickedCart?.title ?? ""),
  );

  const clock =
    fixedClock ??
    clocks.find((row) => String(row.id) === clockId) ??
    defaultClock ??
    clocks[0];
  const cartChoices = carts.filter((row) => row.sounds.length >= 0);

  useEffect(() => {
    if (!clocks.length) return;
    if (fixedClock) {
      setClockId(String(fixedClock.id));
      return;
    }
    if (clocks.some((row) => String(row.id) === clockId)) return;
    const next = clockAtWall(clocks, slots, new Date(), rundownClock);
    setClockId(String(next?.id ?? clocks[0].id));
  }, [clocks, clockId, slots, rundownClock, fixedClock]);

  useEffect(() => {
    if (!open) return;
    const next = fixedClock ?? clockAtWall(clocks, slots, new Date(), rundownClock);
    setClockId(String(next?.id ?? clocks[0]?.id ?? ""));
    setCartId(String(cartProp?.id ?? carts[0]?.id ?? ""));
    setKind(guessCartKind(cartProp?.title ?? carts[0]?.title ?? ""));
    setError(null);
  }, [open, cartProp?.id, cartProp?.title, clocks, carts, slots, rundownClock, fixedClock]);

  const confirm = async () => {
    if (!clock) {
      setError("Aucune rotation.");
      onError("Aucune rotation.");
      return;
    }
    if (!pickedCart) {
      setError("Choisis un cart.");
      onError("Choisis un cart.");
      return;
    }
    const next = putCartInClock(clock, pickedCart, kind);
    if (next.already) {
      onDone(`Déjà dans ${clock.name}.`);
      setOpen(false);
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await saveClock(next.clock);
      onDone(`${pickedCart.title} accroché à ${clock.name} · ${kindLabel(kind)}.`);
      setOpen(false);
    } catch (caught) {
      const message =
        caught instanceof ApiRequestError ? caught.message : "Impossible d’enregistrer.";
      setError(message);
      onError(message);
    } finally {
      setSaving(false);
    }
  };

  const disabled = busy || saving || !clock || !pickedCart;

  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      {trigger ? <Dialog.Trigger>{trigger}</Dialog.Trigger> : null}
      <Dialog.Content maxWidth="24rem">
        <Dialog.Title>Accrocher à l’Auto-DJ</Dialog.Title>
        <Dialog.Description>
          Le cart tourne tout seul dans cette rotation. Pour jouer tout de suite, utilise Maintenant.
        </Dialog.Description>
        <Flex direction="column" gap="3" mt="3">
          {cartProp ? null : cartChoices.length ? (
            <SelectField
              label="Cart"
              value={cartChoices.some((row) => String(row.id) === cartId) ? cartId : String(cartChoices[0].id)}
              disabled={busy || saving}
              onValueChange={(value) => {
                setCartId(value);
                const next = carts.find((row) => String(row.id) === value);
                if (next) setKind(guessCartKind(next.title));
              }}
              options={cartChoices.map((row) => ({
                value: String(row.id),
                label: row.title,
              }))}
            />
          ) : (
            <p className="app-carts-hour-empty">Aucun cart. Crée-en un dans Carts.</p>
          )}
          {fixedClock ? null : clocks.length ? (
            <SelectField
              label="Rotation"
              value={clocks.some((row) => String(row.id) === clockId) ? clockId : String(clocks[0].id)}
              disabled={disabled}
              onValueChange={setClockId}
              options={clocks.map((row) => ({
                value: String(row.id),
                label: row.id === defaultClock?.id ? `${row.name} (en onde)` : row.name,
              }))}
            />
          ) : (
            <p className="app-carts-hour-empty">Aucune heure type. Ajoute un changement d’horloge dans la semaine.</p>
          )}
          <SelectField
            label="Rôle"
            value={kind}
            disabled={disabled}
            onValueChange={(value) => setKind(value as Exclude<PositionKind, "musique">)}
            options={CART_KINDS.map((key) => ({ value: key, label: kindLabel(key) }))}
            hint="Jingle coupe le titre. Programme = titres (cart Prog). Pub = spots."
          />
        </Flex>
        {error ? (
          <p className="app-carts-hour-empty" style={{ color: "var(--app-danger)", marginTop: "0.75rem" }}>
            {error}
          </p>
        ) : null}
        <Flex gap="2" mt="4" justify="end">
          <Dialog.Close>
            <Button variant="soft" color="gray" disabled={saving}>
              Annuler
            </Button>
          </Dialog.Close>
          <Button disabled={disabled} onClick={() => void confirm()}>
            {saving ? <Spinner size="1" /> : <Clock3 className="ui-button-icon" />}
            {saving ? "Enregistrement…" : "Accrocher"}
          </Button>
        </Flex>
      </Dialog.Content>
    </Dialog.Root>
  );
}
