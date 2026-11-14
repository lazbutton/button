import { Button, Dialog, Select, Spinner } from "@radix-ui/themes";
import { useEffect, useState } from "react";
import { cartsThatTake } from "../../api/bankCarts";
import { transferSummary } from "../../api/cartOrder";
import { apiGet, apiPostJson } from "../../api/client";
import type { Cart, CartsResponse } from "../../api/types";
import { FormField } from "../../ui/FormField";

type Answer = { cart: Cart; target: Cart; done: number; skipped: Array<{ title: string; reason: string }> };

/**
 * « Déplacer vers un bac » or « Copier dans un bac » (FON-70). A copy plays the
 * same file in both carts. A move takes a file of the cart's own folder to the
 * other cart's folder; a title of the bank stays where it is.
 */
export function CartTransferDialog({
  copy,
  source,
  ids,
  onClose,
  onCarts,
  notify,
}: {
  copy: boolean;
  source: Cart;
  ids: number[];
  onClose: () => void;
  /** The two carts, as the engine has them after the gesture. */
  onCarts: (source: Cart, target: Cart) => void;
  notify: (text: string, tone: "success" | "error" | "info") => void;
}) {
  const [carts, setCarts] = useState<Cart[] | null>(null);
  const [chosen, setChosen] = useState("");
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState("");
  const count = ids.length === 1 ? "ce son" : `ces ${ids.length} sons`;

  useEffect(() => {
    void apiGet<CartsResponse>("/carts.json").then(
      (payload) => {
        const offered = cartsThatTake(payload.carts ?? []).filter((cart) => cart.id !== source.id);
        setCarts(offered);
        setChosen((before) => before || String(offered[0]?.id ?? ""));
      },
      (caught) => setFailure(caught instanceof Error ? caught.message : "Les bacs ne se sont pas lus."),
    );
  }, [source.id]);

  const target = carts?.find((cart) => String(cart.id) === chosen) ?? null;

  const send = async () => {
    if (!target || busy) return;
    setBusy(true);
    setFailure("");
    try {
      const answer = await apiPostJson<Answer>(`/carts/${source.id}/sounds/transfer.json`, {
        ids,
        to: target.id,
        copy,
      });
      onCarts(answer.cart, answer.target);
      const summary = transferSummary(copy, answer.done, answer.skipped, answer.target.title);
      notify(summary.text, summary.tone);
      onClose();
    } catch (caught) {
      setFailure(caught instanceof Error && caught.message ? caught.message : "Rien n'a changé. Réessaie.");
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
        <Dialog.Title>{copy ? `Copier ${count} dans un bac` : `Déplacer ${count} vers un bac`}</Dialog.Title>
        <Dialog.Description size="2" color="gray" mb="4">
          {copy
            ? "Les deux bacs jouent le même fichier, sans copie : il reste tant qu'un bac le joue."
            : `${ids.length === 1 ? "Le son quitte" : "Les sons quittent"} « ${source.title} ». Un fichier de son dossier suit dans le dossier de l'autre bac ; un titre de la banque reste où il est. Un son à l'antenne ou en file attend.`}
        </Dialog.Description>
        {!carts ? (
          failure ? null : (
            <p className="bacs-dialog-note">
              <Spinner size="1" /> Lecture des bacs…
            </p>
          )
        ) : carts.length === 0 ? (
          <p className="bacs-dialog-note">Aucun autre bac ne prend de sons : crée-en un d'abord.</p>
        ) : (
          <FormField label="Bac">
            <Select.Root value={chosen} onValueChange={setChosen}>
              <Select.Trigger variant="surface" className="ui-field-control" aria-label="Bac" />
              <Select.Content position="popper">
                {carts.map((cart) => (
                  <Select.Item key={cart.id} value={String(cart.id)}>
                    {cart.title}
                  </Select.Item>
                ))}
              </Select.Content>
            </Select.Root>
          </FormField>
        )}
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
          <Button size="2" highContrast disabled={!target || busy} onClick={() => void send()}>
            {busy ? "Envoi…" : target ? `${copy ? "Copier dans" : "Déplacer vers"} « ${target.title} »` : copy ? "Copier" : "Déplacer"}
          </Button>
        </div>
      </Dialog.Content>
    </Dialog.Root>
  );
}
