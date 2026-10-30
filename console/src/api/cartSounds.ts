import { apiGet, apiPostJson, apiUpload } from "./client";
import { chunkFiles } from "./audioDrop";
import { BANK_SEND_DEADLINE_MS } from "./sendDeadline";
import type { BankResponse, Cart } from "./types";

export type CartImportProgress = {
  cartId: number;
  phase: "reading" | "uploading";
  done: number;
  total: number;
  current: string;
};

const UPLOAD_CONCURRENCY = 3;

export function fileLabel(name: string): string {
  return name.split(/[/\\]/).pop() || name;
}

export function mergeImportedCart(prev: Cart | undefined, incoming: Cart): Cart {
  const { delta, ...rest } = incoming;
  if (!delta || !prev || prev.id !== rest.id) return rest;
  const seen = new Set(prev.sounds.map((sound) => sound.id));
  const extra = rest.sounds.filter((sound) => !seen.has(sound.id));
  return {
    ...prev,
    ...rest,
    next_sound_id: prev.next_sound_id ?? rest.next_sound_id,
    sounds: [...prev.sounds, ...extra].sort((left, right) => left.rank - right.rank),
  };
}

async function runPool<T>(items: T[], limit: number, worker: (item: T) => Promise<void>): Promise<void> {
  if (!items.length) return;
  let cursor = 0;
  const run = async () => {
    while (cursor < items.length) {
      const index = cursor;
      cursor += 1;
      await worker(items[index]);
    }
  };
  await Promise.all(Array.from({ length: Math.min(limit, items.length) }, () => run()));
}

export async function importCartSounds(
  cartId: number,
  files: File[],
  onProgress?: (info: { done: number; total: number; current: string }) => void,
  onChunk?: (cart: Cart) => void,
): Promise<Cart> {
  let last: Cart | undefined;
  let done = 0;
  const total = files.length;
  const chunks = chunkFiles(files);
  await runPool(chunks, UPLOAD_CONCURRENCY, async (chunk) => {
    onProgress?.({
      done,
      total,
      current: fileLabel(chunk[0]?.name ?? ""),
    });
    const payload = await apiUpload<{ cart: Cart }>(
      `/carts/${cartId}/sounds.json?delta=1`,
      chunk,
    );
    done += chunk.length;
    last = payload.cart;
    onChunk?.(payload.cart);
    onProgress?.({
      done,
      total,
      current: fileLabel(chunk[chunk.length - 1]?.name ?? ""),
    });
  });
  if (!last) throw new Error("empty upload");
  return last;
}

export function fetchBankFolders(): Promise<BankResponse> {
  return apiGet<BankResponse>("/media/bank.json");
}

export function attachBankFolders(
  cartId: number,
  folders: string[],
): Promise<{ cart: Cart }> {
  return apiPostJson<{ cart: Cart }>(`/carts/${cartId}/sounds.json?delta=1`, { folders }, BANK_SEND_DEADLINE_MS);
}

export function deleteCartSounds(cartId: number, ids: number[]): Promise<{ cart: Cart }> {
  return apiPostJson<{ cart: Cart }>(`/carts/${cartId}/sounds/delete.json`, { ids });
}
