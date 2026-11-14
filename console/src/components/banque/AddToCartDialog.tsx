import { Button, Dialog, Select, Spinner } from "@radix-ui/themes";
import { useEffect, useState } from "react";
import { DROPBOX_NOTE, addedToCart, cartsThatTake } from "../../api/bankCarts";
import { titlesLabel } from "../../api/bankContent";
import { ApiRequestError, apiGet, apiPostJson } from "../../api/client";
import type { Cart, CartsResponse } from "../../api/types";
import { FormField } from "../../ui/FormField";

/**
 * « Ajouter à un bac », from the bank's table (FON-69): the titles chosen go in a
 * cart without a copy. The cart plays them where they are, in the rotation or a
 * collection, and follows them when they move.
 */
export function AddToCartDialog({
  paths,
  onClose,
  notify,
}: {
  /** The titles, by their path below the bank. */
  paths: string[];
  onClose: () => void;
  notify: (text: string, tone: "success" | "error" | "info") => void;
}) {
  const [carts, setCarts] = useState<Cart[] | null>(null);
  const [chosen, setChosen] = useState("");
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState("");

  useEffect(() => {
    void apiGet<CartsResponse>("/carts.json").then(
      (payload) => {
        const offered = cartsThatTake(payload.carts ?? []);
        setCarts(offered);
        setChosen((before) => before || String(offered[0]?.id ?? ""));
      },
      (caught) => setFailure(caught instanceof Error ? caught.message : "Les bacs ne se sont pas lus."),
    );
  }, []);

  const cart = carts?.find((item) => String(item.id) === chosen) ?? null;

  const add = async () => {
    if (!cart || busy) return;
    setBusy(true);
    setFailure("");
    try {
      const { cart: after } = await apiPostJson<{ cart: Cart }>(`/carts/${cart.id}/sounds.json`, { titles: paths });
      const summary = addedToCart(after.sounds.length - cart.sounds.length, paths.length, cart.title);
      notify(summary.text, summary.tone);
      onClose();
    } catch (caught) {
      if (caught instanceof ApiRequestError && caught.status === 409) {
        notify(addedToCart(0, paths.length, cart.title).text, "info");
        onClose();
      } else {
        setFailure(caught instanceof Error && caught.message ? caught.message : "Les titres n'ont pas été ajoutés. Réessaie.");
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog.Root
      open
      onOpenChange={(open) => {
        if (!open && !busy) onClose();
      }}
    >
      <Dialog.Content maxWidth="30rem">
        <Dialog.Title>Ajouter {paths.length === 1 ? "ce titre" : titlesLabel(paths.length).toLowerCase()} à un bac</Dialog.Title>
        <Dialog.Description size="2" color="gray" mb="4">
          Sans copie : le bac joue {paths.length === 1 ? "le titre" : "les titres"} là où {paths.length === 1 ? "il est" : "ils sont"}, et
          {paths.length === 1 ? " le suit" : " les suit"} s'{paths.length === 1 ? "il change" : "ils changent"} de collection. Retirer un son du bac ne
          touche jamais son fichier.
        </Dialog.Description>
        {!carts ? (
          failure ? null : (
            <p className="bacs-dialog-note">
              <Spinner size="1" /> Lecture des bacs…
            </p>
          )
        ) : carts.length === 0 ? (
          <p className="bacs-dialog-note">Aucun bac ne prend de titres : crée-en un dans Sons → Bacs.</p>
        ) : (
          <FormField label="Bac">
            <Select.Root value={chosen} onValueChange={setChosen}>
              <Select.Trigger variant="surface" className="ui-field-control" aria-label="Bac" />
              <Select.Content position="popper">
                {carts.map((item) => (
                  <Select.Item key={item.id} value={String(item.id)}>
                    {item.title} · {titlesLabel(item.sounds.length).toLowerCase()}
                  </Select.Item>
                ))}
              </Select.Content>
            </Select.Root>
          </FormField>
        )}
        <p className="bacs-dialog-note">{DROPBOX_NOTE}</p>
        {failure ? (
          <p className="bacs-dialog-error" role="alert">
            {failure}
          </p>
        ) : null}
        <div className="bacs-dialog-actions">
          <Dialog.Close>
            <Button type="button" size="2" variant="soft" color="gray" disabled={busy}>
              Annuler
            </Button>
          </Dialog.Close>
          <Button size="2" highContrast disabled={!cart || busy} onClick={() => void add()}>
            {busy ? "Ajout…" : cart ? `Ajouter à « ${cart.title} »` : "Ajouter"}
          </Button>
        </div>
      </Dialog.Content>
    </Dialog.Root>
  );
}
