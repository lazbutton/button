import {
  clockElapsedSec,
  itemEndMs,
  rundownFileHref,
  rundownItemKey,
} from "../api/rundownLive";
import type { RundownItem } from "../api/types";

const SEEK_S = 0.07;
const FADE_S = 0.012;
const SCHEDULE_AHEAD_S = 8;
const RESCHEDULE_S = 0.008;
const START_COOLDOWN_MS = 900;
const MAX_BUFFERS = 6;
const FAIL_RETRY_MS = 8000;

export type ClockGraph = {
  ensureGraph: () => void;
  getContext: () => AudioContext | null;
  connectNode: (node: AudioNode) => void;
};

type Slot = {
  key: string;
  item: RundownItem;
  source: AudioBufferSourceNode;
  gain: GainNode;
  startedCtx: number;
  offset: number;
  stopCtx: number | null;
};

function deviceLatency(ctx: AudioContext): number {
  return Math.max(0, (ctx.outputLatency || 0) + (ctx.baseLatency || 0));
}

export class RundownClockPlayer {
  private buffers = new Map<string, AudioBuffer>();
  private inflight = new Map<string, Promise<AudioBuffer | null>>();
  private failedAt = new Map<string, number>();
  private current: Slot | null = null;
  private upcoming: Slot | null = null;
  private lastStartMs = 0;

  constructor(
    private graph: ClockGraph,
    private loadBytes: (href: string) => Promise<ArrayBuffer>,
  ) {}

  get missing(): boolean {
    return this.failedAt.size > 0 && !this.current;
  }

  get loading(): boolean {
    return this.inflight.size > 0 && !this.current;
  }

  lagS(item: RundownItem | null, wall: Date): number | null {
    if (!item || !this.current || this.current.key !== rundownItemKey(item)) return null;
    const ctx = this.graph.getContext();
    if (!ctx) return null;
    const elapsed = clockElapsedSec(item, wall);
    if (elapsed < 0) return null;
    return this.heardSec(this.current, ctx) - elapsed;
  }

  stop(): void {
    this.kill(this.current);
    this.kill(this.upcoming);
    this.current = null;
    this.upcoming = null;
  }

  dispose(): void {
    this.stop();
    this.buffers.clear();
    this.inflight.clear();
    this.failedAt.clear();
  }

  prefetch(items: Array<RundownItem | null>): void {
    for (const item of items) {
      if (!item) continue;
      void this.decode(item);
    }
  }

  async sync(item: RundownItem | null, next: RundownItem | null, wall: Date): Promise<boolean> {
    this.graph.ensureGraph();
    const ctx = this.graph.getContext();
    if (!ctx) return false;
    if (ctx.state === "suspended") {
      await ctx.resume().catch(() => undefined);
    }
    if (!item) {
      this.stop();
      return false;
    }
    this.trimCache(item, next);
    const key = rundownItemKey(item);
    const elapsed = clockElapsedSec(item, wall);
    if (elapsed < 0) {
      this.fadeOut(this.current, ctx.currentTime);
      this.current = null;
      return this.armUpcoming(item, ctx);
    }
    if (this.upcoming && ctx.currentTime + 0.02 >= this.upcoming.startedCtx) {
      if (this.upcoming.key === key) {
        this.current = this.upcoming;
        this.upcoming = null;
      } else {
        if (next) void this.armUpcoming(next, ctx);
        return true;
      }
    }
    const currentLive =
      this.current?.key === key &&
      (this.current.stopCtx == null || ctx.currentTime < this.current.stopCtx);
    if (currentLive && this.current) {
      this.lockClock(this.current, item, wall, ctx);
    } else if (this.upcoming?.key !== key) {
      const started = await this.startNow(item, ctx, true);
      if (!started) return false;
    }
    if (next) void this.armUpcoming(next, ctx);
    else if (this.upcoming) {
      this.kill(this.upcoming);
      this.upcoming = null;
    }
    return true;
  }

  private heardSec(slot: Slot, ctx: AudioContext): number {
    const until =
      slot.stopCtx != null ? Math.min(ctx.currentTime, slot.stopCtx) : ctx.currentTime;
    return slot.offset + Math.max(0, until - slot.startedCtx) - deviceLatency(ctx);
  }

  private lockClock(slot: Slot, item: RundownItem, wall: Date, ctx: AudioContext): void {
    if (slot.stopCtx != null) return;
    const elapsed = clockElapsedSec(item, wall);
    const error = this.heardSec(slot, ctx) - elapsed;
    if (!Number.isFinite(error) || Math.abs(error) <= SEEK_S) return;
    if (Date.now() - this.lastStartMs < START_COOLDOWN_MS) return;
    void this.startNow(item, ctx, true);
  }

  private async startNow(
    item: RundownItem,
    ctx: AudioContext,
    fade: boolean,
  ): Promise<boolean> {
    const buffer = await this.decode(item);
    if (!buffer) return false;
    const key = rundownItemKey(item);
    const latency = deviceLatency(ctx);
    const elapsed = Math.max(0, clockElapsedSec(item, new Date()) + latency);
    const duration = buffer.duration;
    if (duration <= 0.05 || elapsed >= duration - 0.04) {
      this.fadeOut(this.current, ctx.currentTime);
      this.current = null;
      return false;
    }
    if (
      this.current?.key === key &&
      this.current.stopCtx == null &&
      Math.abs(this.heardSec(this.current, ctx) - (elapsed - latency)) <= SEEK_S
    ) {
      return true;
    }
    const offset = Math.min(elapsed, duration - 0.05);
    const when = ctx.currentTime;
    const slot = this.makeSlot(item, buffer, when, offset);
    try {
      slot.source.start(when, offset);
    } catch {
      this.kill(slot);
      return false;
    }
    if (fade && this.current) {
      this.crossfade(this.current, slot, when);
    } else {
      this.kill(this.current);
      slot.gain.gain.setValueAtTime(1, when);
    }
    if (this.upcoming?.key === key) {
      this.kill(this.upcoming);
      this.upcoming = null;
    }
    this.current = slot;
    this.lastStartMs = Date.now();
    return true;
  }

  private async armUpcoming(item: RundownItem, ctx: AudioContext): Promise<boolean> {
    const key = rundownItemKey(item);
    const delay = -clockElapsedSec(item, new Date());
    if (delay <= 0) {
      if (this.current?.key === key) return true;
      return this.startNow(item, ctx, true);
    }
    if (delay > SCHEDULE_AHEAD_S) {
      if (this.upcoming?.key === key) {
        this.kill(this.upcoming);
        this.upcoming = null;
      }
      return true;
    }
    const buffer = await this.decode(item);
    if (!buffer) return false;
    const fresh = -clockElapsedSec(item, new Date());
    if (fresh <= 0) {
      if (this.current?.key === key) return true;
      return this.startNow(item, ctx, true);
    }
    const latency = deviceLatency(ctx);
    const when = ctx.currentTime + fresh - latency;
    if (this.upcoming?.key === key && Math.abs(this.upcoming.startedCtx - when) < RESCHEDULE_S) {
      return true;
    }
    const slot = this.makeSlot(item, buffer, Math.max(ctx.currentTime, when), 0);
    slot.gain.gain.value = 0;
    try {
      slot.source.start(slot.startedCtx, 0);
    } catch {
      this.kill(slot);
      return false;
    }
    if (this.current && this.current.key !== key) {
      this.crossfade(this.current, slot, slot.startedCtx);
    } else {
      slot.gain.gain.setValueAtTime(0, slot.startedCtx);
      slot.gain.gain.linearRampToValueAtTime(1, slot.startedCtx + FADE_S);
    }
    this.kill(this.upcoming);
    this.upcoming = slot;
    return true;
  }

  private makeSlot(
    item: RundownItem,
    buffer: AudioBuffer,
    startedCtx: number,
    offset: number,
  ): Slot {
    const ctx = this.graph.getContext();
    if (!ctx) throw new Error("ctx");
    const source = ctx.createBufferSource();
    const gain = ctx.createGain();
    source.buffer = buffer;
    source.connect(gain);
    this.graph.connectNode(gain);
    gain.gain.value = 1;
    return {
      key: rundownItemKey(item),
      item,
      source,
      gain,
      startedCtx,
      offset,
      stopCtx: null,
    };
  }

  private crossfade(from: Slot, to: Slot, when: number): void {
    const start = Math.max(when, 0);
    try {
      from.gain.gain.cancelScheduledValues(start);
      from.gain.gain.setValueAtTime(from.gain.gain.value, start);
      from.gain.gain.linearRampToValueAtTime(0, start + FADE_S);
      from.source.stop(start + FADE_S + 0.02);
      from.stopCtx = start + FADE_S;
    } catch {
      this.kill(from);
    }
    try {
      to.gain.gain.cancelScheduledValues(start);
      to.gain.gain.setValueAtTime(0, start);
      to.gain.gain.linearRampToValueAtTime(1, start + FADE_S);
    } catch {
      to.gain.gain.value = 1;
    }
  }

  private fadeOut(slot: Slot | null, when: number): void {
    if (!slot) return;
    try {
      slot.gain.gain.cancelScheduledValues(when);
      slot.gain.gain.setValueAtTime(slot.gain.gain.value, when);
      slot.gain.gain.linearRampToValueAtTime(0, when + FADE_S);
      slot.source.stop(when + FADE_S + 0.02);
      slot.stopCtx = when + FADE_S;
    } catch {
      this.kill(slot);
    }
  }

  private kill(slot: Slot | null): void {
    if (!slot) return;
    try {
      slot.source.stop();
    } catch {
      /* already stopped */
    }
    try {
      slot.source.disconnect();
    } catch {
      /* already disconnected */
    }
    try {
      slot.gain.disconnect();
    } catch {
      /* already disconnected */
    }
  }

  private async decode(item: RundownItem): Promise<AudioBuffer | null> {
    const href = rundownFileHref(item);
    if (!href) return null;
    const key = rundownItemKey(item);
    const hit = this.buffers.get(key);
    if (hit) return hit;
    const failedAt = this.failedAt.get(key);
    if (failedAt && Date.now() - failedAt < FAIL_RETRY_MS) return null;
    const pending = this.inflight.get(key);
    if (pending) return pending;
    const promise = (async () => {
      try {
        this.graph.ensureGraph();
        const ctx = this.graph.getContext();
        if (!ctx) return null;
        const bytes = await this.loadBytes(href);
        const buffer = await ctx.decodeAudioData(bytes.slice(0));
        this.buffers.set(key, buffer);
        this.failedAt.delete(key);
        return buffer;
      } catch {
        this.failedAt.set(key, Date.now());
        return null;
      } finally {
        this.inflight.delete(key);
      }
    })();
    this.inflight.set(key, promise);
    return promise;
  }

  private trimCache(item?: RundownItem | null, next?: RundownItem | null): void {
    const keep = new Set<string>();
    if (item) keep.add(rundownItemKey(item));
    if (next) keep.add(rundownItemKey(next));
    if (this.current) keep.add(this.current.key);
    if (this.upcoming) keep.add(this.upcoming.key);
    if (this.buffers.size <= MAX_BUFFERS) return;
    for (const key of this.buffers.keys()) {
      if (keep.has(key)) continue;
      this.buffers.delete(key);
      if (this.buffers.size <= MAX_BUFFERS) break;
    }
  }
}

export function clockRemainingSec(item: RundownItem, wall: Date): number {
  const end = itemEndMs(item);
  if (!Number.isFinite(end)) return 0;
  return Math.max(0, (end - wall.getTime()) / 1000);
}
