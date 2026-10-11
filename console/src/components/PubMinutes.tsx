import { Checkbox, Flex } from "@radix-ui/themes";
import { useEffect, useMemo, useState } from "react";
import { pickPubCart } from "../api/clockMeta";
import { emptyAnchor } from "../api/clockWrite";
import type { Cart, Clock } from "../api/types";
import { Panel } from "../ui/Panel";
import { SelectField } from "../ui/FormField";

const NONE = "__none__";

export function PubMinutes({
  clock,
  carts,
  busy,
  onSave,
}: {
  clock: Clock;
  carts: Cart[];
  busy: boolean;
  onSave: (clock: Clock, ok: string, pending: string) => Promise<boolean>;
}) {
  const options = useMemo(() => {
    const pubs = carts.filter((row) => /pub|spot/i.test(row.title));
    if (pubs.length) return pubs;
    return carts.filter((row) => !/prog/i.test(row.title));
  }, [carts]);
  const preferred = pickPubCart(carts);
  const [cartId, setCartId] = useState(String(preferred?.id ?? options[0]?.id ?? ""));

  useEffect(() => {
    const fromAnchor = clock.anchors.find((row) => row.minute === 20 || row.minute === 40);
    const hit =
      carts.find((row) => row.id === fromAnchor?.cart_id) ??
      carts.find((row) => row.title === fromAnchor?.cart) ??
      preferred ??
      options[0] ??
      null;
    if (hit) setCartId(String(hit.id));
  }, [clock.anchors, carts, options, preferred]);

  const picked = carts.find((row) => String(row.id) === cartId) ?? null;
  const has = (minute: number) => clock.anchors.some((row) => row.minute === minute);

  const applyCart = (anchors: Clock["anchors"], cart: Cart) =>
    anchors.map((row) =>
      row.minute === 20 || row.minute === 40
        ? { ...row, cart: cart.title, cart_id: cart.id, kind: "pub" as const, sync: "dure" as const }
        : row,
    );

  const toggle = async (minute: number, on: boolean) => {
    if (on) {
      if (!picked) return;
      const next = emptyAnchor(minute, { cart: picked.title, fallback: clock.fallback_cart });
      next.cart_id = picked.id;
      const anchors = clock.anchors.filter((row) => row.minute !== minute);
      anchors.push(next);
      anchors.sort((a, b) => (a.minute ?? 0) - (b.minute ?? 0));
      await onSave({ ...clock, anchors }, `Pubs à :${String(minute).padStart(2, "0")}`, "Enregistrement…");
      return;
    }
    await onSave(
      { ...clock, anchors: clock.anchors.filter((row) => row.minute !== minute) },
      "Pubs retirées",
      "Retrait…",
    );
  };

  return (
    <Panel className="autodj-pubs">
      <h2 className="autodj-pubs-title">Coupures pub</h2>
      <p className="autodj-pubs-copy">À cette minute pile, le programme s’interrompt pour les pubs.</p>
      <Flex wrap="wrap" align="center" gap="4" className="autodj-pubs-row">
        <label className="autodj-pubs-check">
          <Checkbox
            checked={has(20)}
            disabled={busy || !picked}
            onCheckedChange={(value) => void toggle(20, value === true)}
          />
          :20
        </label>
        <label className="autodj-pubs-check">
          <Checkbox
            checked={has(40)}
            disabled={busy || !picked}
            onCheckedChange={(value) => void toggle(40, value === true)}
          />
          :40
        </label>
        <SelectField
          label="Cart"
          value={picked ? cartId : NONE}
          options={[
            ...(picked ? [] : [{ value: NONE, label: "Choisir…" }]),
            ...options.map((row) => ({ value: String(row.id), label: row.title })),
          ]}
          disabled={busy || !options.length}
          onValueChange={(value) => {
            setCartId(value);
            const next = carts.find((row) => String(row.id) === value);
            if (!next) return;
            if (!clock.anchors.some((row) => row.minute === 20 || row.minute === 40)) return;
            void onSave({ ...clock, anchors: applyCart(clock.anchors, next) }, "Cart pubs changé", "Enregistrement…");
          }}
        />
      </Flex>
    </Panel>
  );
}
