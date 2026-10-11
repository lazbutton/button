import { useCallback, useEffect, useRef, useState } from "react";
import {
  SCENE_CHAIN,
  SCENE_SKIP,
  SHIFT_NOTE,
  clearApc,
  initApc,
  isApcMiniMk2Name,
  noteToCell,
  paintApc,
  type ApcLedState,
  type PadKind,
} from "./apcMiniMk2";

export type MidiStatus =
  | { kind: "unsupported" }
  | { kind: "need-gesture" }
  | { kind: "denied" }
  | { kind: "searching" }
  | { kind: "disconnected" }
  | { kind: "connected"; name: string; sysex: boolean };

const BOUNCE_MS = 90;
const INIT_PAINT_MS = 90;
const BLINK_MS = 400;
const BLINK_END_MS = 120;

function collectApc(access: MIDIAccess): { inputs: MIDIInput[]; outputs: MIDIOutput[] } {
  const inputs: MIDIInput[] = [];
  const outputs: MIDIOutput[] = [];
  access.inputs.forEach((port) => {
    if (isApcMiniMk2Name(port.name) && port.state === "connected") inputs.push(port);
  });
  access.outputs.forEach((port) => {
    if (isApcMiniMk2Name(port.name) && port.state === "connected") outputs.push(port);
  });
  return { inputs, outputs };
}

export function useApcMini({
  onFire,
  onSkip,
  onToggleChain,
  playing,
  endingSoon,
  jingleArmed,
  chainAfterSound,
  counts,
}: {
  onFire: (kind: PadKind, index: number) => void;
  onSkip: () => void;
  onToggleChain: () => void;
  playing: { kind: PadKind; index: number } | null;
  endingSoon: boolean;
  jingleArmed: boolean;
  chainAfterSound: boolean;
  counts: Record<PadKind, number>;
}): { status: MidiStatus; connect: () => void } {
  const [status, setStatus] = useState<MidiStatus>({ kind: "searching" });
  const outputsRef = useRef<MIDIOutput[]>([]);
  const inputsRef = useRef<MIDIInput[]>([]);
  const accessRef = useRef<MIDIAccess | null>(null);
  const lastHit = useRef<{ note: number; at: number } | null>(null);
  const onFireRef = useRef(onFire);
  const onSkipRef = useRef(onSkip);
  const onToggleChainRef = useRef(onToggleChain);
  const countsRef = useRef(counts);
  onFireRef.current = onFire;
  onSkipRef.current = onSkip;
  onToggleChainRef.current = onToggleChain;
  countsRef.current = counts;

  const ledState = useRef<ApcLedState>({
    playing,
    playingLit: true,
    jingleArmed,
    chainAfterSound,
    counts,
  });
  ledState.current = {
    ...ledState.current,
    playing,
    jingleArmed,
    chainAfterSound,
    counts,
  };

  const detachInputs = useCallback(() => {
    for (const input of inputsRef.current) {
      input.onmidimessage = null;
    }
    inputsRef.current = [];
  }, []);

  const onMessage = useCallback((ev: MIDIMessageEvent) => {
    const data = ev.data;
    if (!data || data.length < 2) return;
    const statusByte = data[0] ?? 0;
    const cmd = statusByte & 0xf0;
    const note = data[1] ?? 0;
    const vel = data[2] ?? 0;
    if (note === SHIFT_NOTE) return;
    if (cmd !== 0x90 || vel === 0) return;

    const now = performance.now();
    const prev = lastHit.current;
    if (prev && prev.note === note && now - prev.at < BOUNCE_MS) return;
    lastHit.current = { note, at: now };

    if (note === SCENE_SKIP) {
      onSkipRef.current();
      return;
    }
    if (note === SCENE_CHAIN) {
      onToggleChainRef.current();
      return;
    }

    const cell = noteToCell(note);
    if (cell.type !== "pad") return;
    if (cell.index >= countsRef.current[cell.kind]) return;
    onFireRef.current(cell.kind, cell.index);
  }, []);

  const bind = useCallback(
    (access: MIDIAccess) => {
      const { inputs, outputs } = collectApc(access);
      detachInputs();
      outputsRef.current = outputs;

      if (!outputs.length && !inputs.length) {
        setStatus({ kind: "disconnected" });
        return;
      }

      for (const input of inputs) {
        void input.open().catch(() => undefined);
        input.onmidimessage = onMessage;
      }
      inputsRef.current = inputs;
      for (const output of outputs) {
        void output.open().catch(() => undefined);
      }

      const name = outputs[0]?.name ?? inputs[0]?.name ?? "APC mini mk2";
      initApc(outputs, access.sysexEnabled);
      window.setTimeout(() => paintApc(outputsRef.current, ledState.current), INIT_PAINT_MS);
      setStatus({ kind: "connected", name, sysex: access.sysexEnabled });
    },
    [detachInputs, onMessage],
  );

  const connect = useCallback(() => {
    if (typeof navigator.requestMIDIAccess !== "function") {
      setStatus({ kind: "unsupported" });
      return;
    }
    setStatus({ kind: "searching" });
    const open = (sysex: boolean) => navigator.requestMIDIAccess({ sysex });
    open(true)
      .catch(() => open(false))
      .then((access) => {
        accessRef.current = access;
        access.onstatechange = () => bind(access);
        bind(access);
      })
      .catch((err: unknown) => {
        const name = err instanceof DOMException ? err.name : "";
        if (name === "SecurityError" || name === "InvalidStateError") {
          setStatus({ kind: "need-gesture" });
          return;
        }
        setStatus({ kind: "denied" });
      });
  }, [bind]);

  useEffect(() => {
    connect();
    return () => {
      const outputs = outputsRef.current;
      if (outputs.length) clearApc(outputs);
      detachInputs();
      const access = accessRef.current;
      if (access) access.onstatechange = null;
      accessRef.current = null;
      outputsRef.current = [];
    };
  }, [connect, detachInputs]);

  useEffect(() => {
    if (status.kind !== "connected") return;
    ledState.current.playingLit = true;
    paintApc(outputsRef.current, ledState.current);
  }, [status.kind, playing?.kind, playing?.index, jingleArmed, chainAfterSound, counts]);

  useEffect(() => {
    if (status.kind !== "connected" || !playing) return;
    const id = window.setInterval(() => {
      ledState.current.playingLit = !ledState.current.playingLit;
      paintApc(outputsRef.current, ledState.current);
    }, endingSoon ? BLINK_END_MS : BLINK_MS);
    return () => window.clearInterval(id);
  }, [status.kind, playing?.kind, playing?.index, endingSoon]);

  return { status, connect };
}
