import type { LibraryHit } from "./library";
import type { Cart, Sound } from "./types";

export function normalizeMediaPath(path: string | undefined | null): string {
  return (path || "").replace(/\\/g, "/").replace(/^\/+/, "").toLowerCase();
}

export function soundMatchesPath(sound: Sound, path: string): boolean {
  const left = normalizeMediaPath(sound.path);
  const right = normalizeMediaPath(path);
  if (!left || !right) return false;
  return left === right || left.endsWith(right) || right.endsWith(left);
}

export function findSoundByPath(cart: Cart, path: string): Sound | undefined {
  return cart.sounds.find((sound) => soundMatchesPath(sound, path));
}

export function ranksWithSoundAt(sounds: Sound[], soundId: number, slotIndex: number): number[] {
  const ids = sounds.map((sound) => sound.id).filter((id) => id !== soundId);
  ids.splice(Math.max(0, Math.min(slotIndex, ids.length)), 0, soundId);
  return ids;
}

export function ranksUnslotSound(sounds: Sound[], soundId: number): number[] {
  const ids = sounds.map((sound) => sound.id).filter((id) => id !== soundId);
  ids.push(soundId);
  return ids;
}

export function ranksSwapSounds(sounds: Sound[], leftId: number, rightId: number): number[] {
  const ids = sounds.map((sound) => sound.id);
  const left = ids.indexOf(leftId);
  const right = ids.indexOf(rightId);
  if (left < 0 || right < 0) return ids;
  [ids[left], ids[right]] = [ids[right], ids[left]];
  return ids;
}

export function newSoundAfterIngest(prev: Cart, next: Cart, hit: LibraryHit): Sound | undefined {
  const prevIds = new Set(prev.sounds.map((sound) => sound.id));
  return next.sounds.find((sound) => !prevIds.has(sound.id)) ?? findSoundByPath(next, hit.path);
}

export function replaceCartInList(carts: Cart[], cart: Cart): Cart[] {
  const found = carts.some((row) => row.id === cart.id);
  if (!found) return [...carts, cart];
  return carts.map((row) => (row.id === cart.id ? cart : row));
}
