/**
 * Pads jingles / pubs du pupitre : tir, glisser-déposer, rangs, vidage.
 * Sorti d'AntennePage pour garder la page lisible.
 */
import { useCallback, useMemo, useState, type Dispatch, type SetStateAction } from "react";
import { apiPost, apiPostJson, apiPut } from "../api/client";
import {
  findSoundByPath,
  newSoundAfterIngest,
  ranksSwapSounds,
  ranksUnslotSound,
  ranksWithSoundAt,
  replaceCartInList,
} from "../api/deskPads";
import type { LibraryHit } from "../api/library";
import { identCart } from "../api/cartFlags";
import { onAirPadId, padBanksFromCarts, padSlotsFromCarts, type EnginePad } from "../api/liveMap";
import type { Cart, CartsResponse, LiveSnapshot } from "../api/types";

export type PadKind = "jingle" | "pub";

export function useDeskPads({
  carts,
  setCarts,
  snapshot,
  harbor,
  show,
  fail,
  onLiveReload,
}: {
  carts: CartsResponse | null;
  setCarts: Dispatch<SetStateAction<CartsResponse | null>>;
  snapshot: LiveSnapshot;
  harbor: boolean;
  show: (message: string) => void;
  fail: (caught: unknown, fallback: string, forbidden?: string) => void;
  onLiveReload: () => void;
}) {
  const banks = useMemo(() => padBanksFromCarts(carts?.carts ?? []), [carts]);
  const slots = useMemo(() => padSlotsFromCarts(carts?.carts ?? []), [carts]);
  const onAirId = onAirPadId(snapshot, banks);
  const [firedId, setFiredId] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);

  const applyCart = useCallback(
    (cart: Cart) => {
      setCarts((prev) => ({ carts: replaceCartInList(prev?.carts ?? [], cart) }));
    },
    [setCarts],
  );

  const cartByKind = useCallback(
    (kind: PadKind): Cart | undefined => {
      const rows = carts?.carts ?? [];
      if (kind === "jingle") return identCart(rows);
      return rows.find((cart) => cart.title === "Pubs");
    },
    [carts],
  );

  const putRanks = useCallback(
    async (cart: Cart, ranks: number[]) => {
      const payload = await apiPut<{ cart: Cart }>(`/carts/${cart.id}/sounds/ranks.json`, { ranks });
      applyCart(payload.cart);
    },
    [applyCart],
  );

  const fire = useCallback(
    async (pad: EnginePad) => {
      if (harbor) {
        show("Direct à l’antenne.");
        return;
      }
      setFiredId(pad.id);
      window.setTimeout(() => setFiredId(null), 700);
      try {
        await apiPost(`/carts/${pad.cartId}/sounds/${pad.soundId}/now.json`);
        show("À l’antenne — coupe.");
        onLiveReload();
      } catch (caught) {
        fail(caught, "Impossible de mettre à l’antenne.");
      }
    },
    [fail, harbor, onLiveReload, show],
  );

  const dropHit = useCallback(
    async (kind: PadKind, slotIndex: number, hit: LibraryHit) => {
      const cart = cartByKind(kind);
      if (!cart) {
        show(kind === "jingle" ? "Coche « Pads d’idents » sur un cart, dans Sons." : "Pas de cart Pubs.");
        return;
      }
      try {
        const existing = findSoundByPath(cart, hit.path);
        if (existing) {
          await putRanks(cart, ranksWithSoundAt(cart.sounds, existing.id, slotIndex));
          show("Pad mis à jour.");
          return;
        }
        const added = await apiPostJson<{ cart: Cart }>(`/carts/${cart.id}/sounds.json`, {
          paths: [hit.path],
        });
        const created = newSoundAfterIngest(cart, added.cart, hit);
        if (!created) {
          applyCart(added.cart);
          show("Son ajouté au cart.");
          return;
        }
        const ranked = await apiPut<{ cart: Cart }>(`/carts/${cart.id}/sounds/ranks.json`, {
          ranks: ranksWithSoundAt(added.cart.sounds, created.id, slotIndex),
        });
        applyCart(ranked.cart);
        show("Pad mis à jour.");
      } catch (caught) {
        fail(caught, "Impossible de régler ce pad.", "Pas le droit Carts.");
      }
    },
    [applyCart, cartByKind, fail, putRanks, show],
  );

  const swap = useCallback(
    async (kind: PadKind, fromSoundId: number, toSoundId: number) => {
      const cart = cartByKind(kind);
      if (!cart) return;
      try {
        await putRanks(cart, ranksSwapSounds(cart.sounds, fromSoundId, toSoundId));
      } catch (caught) {
        fail(caught, "Impossible d’échanger les pads.", "Pas le droit Carts.");
      }
    },
    [cartByKind, fail, putRanks],
  );

  const rank = useCallback(
    async (kind: PadKind, soundId: number, slotIndex: number) => {
      const cart = cartByKind(kind);
      if (!cart) return;
      try {
        await putRanks(cart, ranksWithSoundAt(cart.sounds, soundId, slotIndex));
      } catch (caught) {
        fail(caught, "Impossible de régler ce pad.", "Pas le droit Carts.");
      }
    },
    [cartByKind, fail, putRanks],
  );

  const unslot = useCallback(
    async (pad: EnginePad) => {
      const cart = carts?.carts.find((row) => row.id === pad.cartId);
      if (!cart) return;
      try {
        await putRanks(cart, ranksUnslotSound(cart.sounds, pad.soundId));
        show("Pad vidé — le son reste dans le cart.");
      } catch (caught) {
        fail(caught, "Impossible de vider ce pad.", "Pas le droit Carts.");
      }
    },
    [carts, fail, putRanks, show],
  );

  return { banks, slots, onAirId, firedId, editing, setEditing, fire, dropHit, swap, rank, unslot };
}
