import { Button, Dialog, Flex, Spinner } from "@radix-ui/themes";
import { Library, Plus } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { apiPostJson, ApiRequestError } from "../api/client";
import { clockPositionsEqual, saveClock, setClockPositionCart } from "../api/clockWrite";
import type { Cart, Clock } from "../api/types";
import { SelectField } from "../ui/FormField";

export function RepairClockCartDialog({
  open,
  onOpenChange,
  clocks,
  carts,
  missingTitle,
  clockId,
  clockName,
  positionId,
  motifIndex,
  kind,
  trigger,
  onRepaired,
  onOpenCart,
  onError,
}: {
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  clocks: Clock[];
  carts: Cart[];
  missingTitle: string;
  clockId?: number | null;
  clockName?: string | null;
  positionId?: number | null;
  motifIndex?: number | null;
  kind?: string;
  trigger?: React.ReactNode;
  onRepaired: () => void | Promise<void>;
  onOpenCart: (cartId: number) => void;
  onError: (message: string) => void;
}) {
  const [internalOpen, setInternalOpen] = useState(false);
  const controlled = open !== undefined;
  const actualOpen = controlled ? open : internalOpen;
  const setOpen = onOpenChange ?? setInternalOpen;
  const [saving, setSaving] = useState(false);
  const [pickedId, setPickedId] = useState(carts[0] ? String(carts[0].id) : "");

  const title = missingTitle.trim();
  const existing = title
    ? carts.find((cart) => cart.title.trim().toLowerCase() === title.toLowerCase())
    : undefined;
  const clock =
    clocks.find((row) => row.id === clockId) ||
    clocks.find((row) => row.name === clockName) ||
    null;

  useEffect(() => {
    if (!actualOpen) return;
    setPickedId(carts[0] ? String(carts[0].id) : "");
  }, [actualOpen, carts]);

  const options = useMemo(
    () => carts.map((cart) => ({ value: String(cart.id), label: cart.title })),
    [carts],
  );

  const createOrOpen = async () => {
    if (!title) {
      onError("Cette étape n’a pas de nom de cart.");
      return;
    }
    if (existing) {
      onOpenCart(existing.id);
      setOpen(false);
      return;
    }
    setSaving(true);
    try {
      const created = await apiPostJson<{ cart: Cart }>("/carts.json", {
        title,
        mode: "playlist",
        schedule_mode: "clock",
      });
      onOpenCart(created.cart.id);
      setOpen(false);
    } catch (caught) {
      const found = carts.find(
        (cart) => cart.title.trim().toLowerCase() === title.toLowerCase(),
      );
      if (found) {
        onOpenCart(found.id);
        setOpen(false);
        return;
      }
      onError(caught instanceof ApiRequestError ? caught.message : "Création du cart impossible.");
    } finally {
      setSaving(false);
    }
  };

  const useExisting = async () => {
    const cart = carts.find((row) => String(row.id) === pickedId) ?? carts[0];
    if (!cart) {
      onError("Choisis un cart.");
      return;
    }
    if (!clock) {
      onError("Heure type introuvable.");
      return;
    }
    const next = setClockPositionCart(clock, cart, {
      positionId,
      motifIndex,
      kind,
      previousCart: title || null,
    });
    if (clockPositionsEqual(clock, next)) {
      onError("Étape introuvable dans l’heure type.");
      return;
    }
    setSaving(true);
    try {
      await saveClock(next);
      await onRepaired();
      setOpen(false);
    } catch (caught) {
      onError(
        caught instanceof ApiRequestError ? caught.message : "Impossible de brancher ce cart.",
      );
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog.Root
      open={actualOpen}
      onOpenChange={(next) => {
        if (saving && !next) return;
        setOpen(next);
      }}
    >
      {trigger ? <Dialog.Trigger>{trigger}</Dialog.Trigger> : null}
      <Dialog.Content maxWidth="24rem">
        <Dialog.Title>{title ? `Réparer « ${title} »` : "Réparer la case"}</Dialog.Title>
        <Dialog.Description>
          {existing
            ? "Ce cart existe déjà mais n’a pas de son utilisable, ou l’heure type le cherche encore. Ouvre-le pour y coller des fichiers, ou remplace l’étape par un autre cart."
            : title
              ? "L’heure type demande ce cart, qui n’existe pas. Crée-le ou branche un cart déjà là."
              : "Cette étape n’a pas de cart. Branche-en un."}
        </Dialog.Description>
        <Flex direction="column" gap="3" mt="3">
          {title ? (
            <Button highContrast disabled={saving} onClick={() => void createOrOpen()}>
              {saving ? <Spinner size="1" /> : existing ? <Library className="ui-button-icon" /> : <Plus className="ui-button-icon" />}
              {existing ? "Ouvrir le cart" : `Créer « ${title} »`}
            </Button>
          ) : null}
          {options.length ? (
            <>
              <SelectField
                label="Ou utiliser un cart existant"
                value={options.some((option) => option.value === pickedId) ? pickedId : options[0].value}
                disabled={saving || !clock}
                onValueChange={setPickedId}
                options={options}
              />
              <Button
                variant="soft"
                disabled={saving || !clock || !(pickedId || options[0])}
                onClick={() => void useExisting()}
              >
                Brancher ce cart
              </Button>
            </>
          ) : null}
        </Flex>
        <Flex gap="2" mt="4" justify="end">
          <Dialog.Close>
            <Button variant="soft" color="gray" disabled={saving}>
              Fermer
            </Button>
          </Dialog.Close>
        </Flex>
      </Dialog.Content>
    </Dialog.Root>
  );
}
