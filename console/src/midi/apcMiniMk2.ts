/** Akai APC Mini MK2 — Session / Normal (port 0). Notes 0–63, bas-gauche = 0. */

export type PadKind = "son" | "jingle" | "pub";

export type ApcCell =
  | { type: "pad"; kind: PadKind; index: number }
  | { type: "empty" };

export const KINDS: readonly PadKind[] = ["son", "jingle", "pub"];

/** Colonnes 2×3 + gouttière : SONS | · | JINGLES | · | PUBS */
export const GROUP_COLS: Record<PadKind, readonly [number, number]> = {
  son: [0, 1],
  jingle: [3, 4],
  pub: [6, 7],
};

/** Rangées pads (haut du groupe → bas, près des faders). */
export const PAD_ROWS = [2, 1, 0] as const;

export const SCENE_SKIP = 112;
export const SCENE_CHAIN = 113;
export const SHIFT_NOTE = 122;

/** Palette APC (velocity) calée sur amber / ruby / orange du pupitre. */
export const APC_COLOR = {
  off: 0,
  white: 3,
  son: 8,
  jingle: 56,
  pub: 9,
} as const;

const LED_SOLID_FULL = 0x96;
const LED_PULSE = 0x98;
const LED_BUTTON = 0x90;

export const SYSEX_INTRO = [
  0xf0, 0x47, 0x7f, 0x4f, 0x60, 0x00, 0x04, 0x00, 0x01, 0x00, 0x00, 0xf7,
];
export const SYSEX_NORMAL = [0xf0, 0x47, 0x7f, 0x4f, 0x62, 0x00, 0x01, 0x00, 0xf7];

export type ApcLedState = {
  playing: { kind: PadKind; index: number } | null;
  playingLit: boolean;
  jingleArmed: boolean;
  chainAfterSound: boolean;
  counts: Record<PadKind, number>;
};

export function isApcMiniMk2Name(name: string | undefined | null): boolean {
  const n = (name ?? "").toLowerCase();
  if (!n.includes("apc") || !n.includes("mini")) return false;
  return /mk\s*2/.test(n) || n.includes("mkii") || n.includes("mk2");
}

export function noteAt(row: number, col: number): number {
  return row * 8 + col;
}

export function cellAt(row: number, col: number): ApcCell {
  for (const kind of KINDS) {
    const [c0, c1] = GROUP_COLS[kind];
    if (col !== c0 && col !== c1) continue;
    const padRow = (PAD_ROWS as readonly number[]).indexOf(row);
    if (padRow < 0) return { type: "empty" };
    const index = padRow * 2 + (col === c0 ? 0 : 1);
    return { type: "pad", kind, index };
  }
  return { type: "empty" };
}

export function noteToCell(note: number): ApcCell {
  if (note < 0 || note > 63) return { type: "empty" };
  return cellAt(Math.floor(note / 8), note % 8);
}

export function sendAll(outputs: MIDIOutput[], data: number[]): void {
  for (const out of outputs) {
    try {
      out.send(data);
    } catch {
      /* port fermé */
    }
  }
}

export function initApc(outputs: MIDIOutput[], sysex: boolean): void {
  if (sysex) {
    sendAll(outputs, SYSEX_INTRO);
    sendAll(outputs, SYSEX_NORMAL);
  }
}

export function clearApc(outputs: MIDIOutput[]): void {
  for (let note = 0; note < 64; note++) {
    sendAll(outputs, [LED_SOLID_FULL, note, 0]);
  }
  for (let n = 100; n <= 107; n++) sendAll(outputs, [LED_BUTTON, n, 0]);
  for (let n = 112; n <= 119; n++) sendAll(outputs, [LED_BUTTON, n, 0]);
}

export function paintApc(outputs: MIDIOutput[], state: ApcLedState): void {
  if (!outputs.length) return;

  for (let row = 0; row < 8; row++) {
    for (let col = 0; col < 8; col++) {
      const note = noteAt(row, col);
      const cell = cellAt(row, col);
      const available = cell.type === "pad" && cell.index < state.counts[cell.kind];
      if (!available) {
        sendAll(outputs, [LED_SOLID_FULL, note, 0]);
        continue;
      }
      const color = APC_COLOR[cell.kind];
      const isPlaying =
        state.playing?.kind === cell.kind && state.playing.index === cell.index;
      const armed = state.jingleArmed && cell.kind === "jingle";
      if (isPlaying) {
        sendAll(outputs, [LED_SOLID_FULL, note, state.playingLit ? APC_COLOR.white : 0]);
      } else if (armed) sendAll(outputs, [LED_PULSE, note, color]);
      else sendAll(outputs, [LED_SOLID_FULL, note, color]);
    }
  }

  for (let n = 100; n <= 107; n++) sendAll(outputs, [LED_BUTTON, n, 0]);
  sendAll(outputs, [LED_BUTTON, SCENE_SKIP, 1]);
  sendAll(outputs, [
    LED_BUTTON,
    SCENE_CHAIN,
    state.chainAfterSound ? (state.jingleArmed ? 2 : 1) : 0,
  ]);
}
