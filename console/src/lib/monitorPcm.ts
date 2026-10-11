export type PcmTiming = {
  keepS: number;
  maxS: number;
  startS: number;
};

/** LAN : proche du zéro, encore assez large pour un jitter local. */
export const PCM_LAN: PcmTiming = { keepS: 0.12, maxS: 0.2, startS: 0.04 };
/** Tailscale / distant : assez large, plus de retour direct. WAV ~1,4 Mbit/s. */
export const PCM_REMOTE: PcmTiming = { keepS: 1.2, maxS: 2.0, startS: 0.5 };

export const PCM_KEEP_S = PCM_REMOTE.keepS;
export const PCM_MAX_S = PCM_REMOTE.maxS;

const PCM_CHUNK_S = 0.025;

export function pcmTimingForStream(url: string): PcmTiming {
  try {
    const host = new URL(url).hostname;
    if (
      host === "192.168.1.100" ||
      host === "nasgul" ||
      host === "localhost" ||
      host === "127.0.0.1"
    ) {
      return PCM_LAN;
    }
  } catch {
    /* proto */
  }
  return PCM_REMOTE;
}

export class MonitorPcmSink {
  private playAt = 0;
  private sources: AudioBufferSourceNode[] = [];

  constructor(
    private ctx: AudioContext,
    private dest: AudioNode,
    private keepS: number,
    private maxS: number,
    private startS = PCM_REMOTE.startS,
  ) {}

  get lagS(): number {
    const queued = Math.max(0, this.playAt - this.ctx.currentTime);
    const device = (this.ctx.outputLatency || 0) + (this.ctx.baseLatency || 0);
    return queued + device;
  }

  enqueue(channelData: Float32Array[], samplesDecoded: number, sampleRate: number): void {
    if (samplesDecoded <= 0 || sampleRate <= 0) return;
    if (this.ctx.state === "suspended") {
      void this.ctx.resume().catch(() => undefined);
    }
    const duration = samplesDecoded / sampleRate;
    const now = this.ctx.currentTime;
    let when = this.playAt;
    if (when < now + this.startS) when = now + this.startS;
    const projected = when - now + duration;
    let offset = 0;
    if (projected > this.maxS) {
      this.clearSources();
      when = now + this.startS;
      if (duration > this.keepS) offset = duration - this.keepS;
    }
    if (offset >= duration) return;
    const channels = Math.max(1, channelData.length);
    const buffer = this.ctx.createBuffer(channels, samplesDecoded, sampleRate);
    for (let i = 0; i < channels; i++) {
      const src = channelData[i] || channelData[0];
      buffer.getChannelData(i).set(src.subarray(0, samplesDecoded));
    }
    const src = this.ctx.createBufferSource();
    src.buffer = buffer;
    src.connect(this.dest);
    src.onended = () => {
      const i = this.sources.indexOf(src);
      if (i >= 0) this.sources.splice(i, 1);
    };
    src.start(when, offset);
    this.sources.push(src);
    this.playAt = when + (duration - offset);
  }

  stop(): void {
    this.clearSources();
    this.playAt = 0;
  }

  private clearSources(): void {
    for (const src of this.sources) {
      try {
        src.stop();
      } catch {
        /* already stopped */
      }
      try {
        src.disconnect();
      } catch {
        /* already disconnected */
      }
    }
    this.sources = [];
  }
}

export type PcmFrame = {
  channelData: Float32Array[];
  samplesDecoded: number;
  sampleRate: number;
};

/** Agrège les paquets TCP en blocs ~25 ms / ≥1024 frames avant le sink. */
export class PcmAggregator {
  private pending: Float32Array[] | null = null;
  private frames = 0;
  private sampleRate = 0;

  push(channelData: Float32Array[], samplesDecoded: number, sampleRate: number): PcmFrame | null {
    if (samplesDecoded <= 0 || sampleRate <= 0) return null;
    if (
      this.pending &&
      (this.sampleRate !== sampleRate || this.pending.length !== Math.max(1, channelData.length))
    ) {
      const flushed = this.flush();
      this.append(channelData, samplesDecoded, sampleRate);
      return flushed;
    }
    this.append(channelData, samplesDecoded, sampleRate);
    const target = Math.max(1024, Math.round(this.sampleRate * PCM_CHUNK_S));
    if (this.frames >= target) return this.flush();
    return null;
  }

  flush(): PcmFrame | null {
    if (!this.pending || this.frames <= 0) return null;
    const channelData = this.pending.map((ch) => ch.slice(0, this.frames));
    const samplesDecoded = this.frames;
    const sampleRate = this.sampleRate;
    this.pending = null;
    this.frames = 0;
    return { channelData, samplesDecoded, sampleRate };
  }

  private append(channelData: Float32Array[], samplesDecoded: number, sampleRate: number): void {
    const channels = Math.max(1, channelData.length);
    if (!this.pending) {
      this.pending = Array.from({ length: channels }, () => new Float32Array(Math.max(samplesDecoded * 2, 2048)));
      this.sampleRate = sampleRate;
      this.frames = 0;
    }
    this.ensureCapacity(this.frames + samplesDecoded);
    for (let c = 0; c < channels; c++) {
      const src = channelData[c] || channelData[0];
      this.pending[c].set(src.subarray(0, samplesDecoded), this.frames);
    }
    this.frames += samplesDecoded;
  }

  private ensureCapacity(need: number): void {
    if (!this.pending) return;
    const cap = this.pending[0]?.length ?? 0;
    if (need <= cap) return;
    const next = Math.max(need, cap * 2);
    this.pending = this.pending.map((ch) => {
      const grown = new Float32Array(next);
      grown.set(ch.subarray(0, this.frames));
      return grown;
    });
  }
}

export function skipId3(chunk: Uint8Array): Uint8Array {
  if (chunk.length < 10 || chunk[0] !== 0x49 || chunk[1] !== 0x44 || chunk[2] !== 0x33) {
    return chunk;
  }
  const size =
    ((chunk[6] & 0x7f) << 21) |
    ((chunk[7] & 0x7f) << 14) |
    ((chunk[8] & 0x7f) << 7) |
    (chunk[9] & 0x7f);
  const skip = 10 + size;
  if (skip > 0 && skip < chunk.length) return chunk.subarray(skip);
  return chunk;
}

function ascii(chunk: Uint8Array, start: number, n: number): string {
  return String.fromCharCode(...chunk.subarray(start, start + n));
}

export class WavPcmParser {
  private buf: Uint8Array = new Uint8Array(0);
  private dataAt = -1;
  channels = 2;
  sampleRate = 44100;
  bits = 16;

  push(chunk: Uint8Array): {
    channelData: Float32Array[];
    samplesDecoded: number;
    sampleRate: number;
  } | null {
    const next = new Uint8Array(this.buf.length + chunk.length);
    next.set(this.buf, 0);
    next.set(chunk, this.buf.length);
    this.buf = next;
    if (this.dataAt < 0 && !this.parseHeader()) return null;
    const bytesPerFrame = this.channels * Math.max(1, this.bits / 8);
    if (bytesPerFrame <= 0) return null;
    const pcm = this.dataAt > 0 ? this.buf.subarray(this.dataAt) : this.buf;
    const frames = Math.floor(pcm.length / bytesPerFrame);
    if (frames <= 0) return null;
    const used = frames * bytesPerFrame;
    const slice = pcm.subarray(0, used);
    this.buf = new Uint8Array(pcm.subarray(used));
    this.dataAt = 0;
    return this.decode(slice, frames);
  }

  private parseHeader(): boolean {
    if (this.buf.length < 4) return false;
    if (ascii(this.buf, 0, 4) !== "RIFF") {
      this.dataAt = 0;
      return true;
    }
    if (this.buf.length < 44) return false;
    if (ascii(this.buf, 8, 4) !== "WAVE") {
      this.dataAt = 0;
      return true;
    }
    const view = new DataView(this.buf.buffer, this.buf.byteOffset, this.buf.byteLength);
    let offset = 12;
    while (offset + 8 <= this.buf.length) {
      const id = ascii(this.buf, offset, 4);
      const size = view.getUint32(offset + 4, true);
      if (id === "fmt " && offset + 24 <= this.buf.length) {
        this.channels = Math.max(1, view.getUint16(offset + 10, true) || 2);
        this.sampleRate = view.getUint32(offset + 12, true) || 44100;
        this.bits = view.getUint16(offset + 22, true) || 16;
      }
      if (id === "data") {
        this.dataAt = offset + 8;
        return true;
      }
      offset += 8 + size + (size % 2);
    }
    return false;
  }

  private decode(slice: Uint8Array, frames: number) {
    const channels = this.channels;
    const view = new DataView(slice.buffer, slice.byteOffset, slice.byteLength);
    const planar = Array.from({ length: channels }, () => new Float32Array(frames));
    if (this.bits === 16) {
      let o = 0;
      for (let i = 0; i < frames; i++) {
        for (let c = 0; c < channels; c++) {
          planar[c][i] = view.getInt16(o, true) / 32768;
          o += 2;
        }
      }
    } else if (this.bits === 32) {
      let o = 0;
      for (let i = 0; i < frames; i++) {
        for (let c = 0; c < channels; c++) {
          planar[c][i] = view.getFloat32(o, true);
          o += 4;
        }
      }
    } else {
      let o = 0;
      const mid = 128;
      for (let i = 0; i < frames; i++) {
        for (let c = 0; c < channels; c++) {
          planar[c][i] = (slice[o] - mid) / mid;
          o += 1;
        }
      }
    }
    return { channelData: planar, samplesDecoded: frames, sampleRate: this.sampleRate };
  }
}

export function isWavStream(url: string): boolean {
  try {
    return /\.wav$/i.test(new URL(url, "http://local").pathname);
  } catch {
    return /\.wav(\?|$)/i.test(url);
  }
}

export function mp3Twin(url: string): string {
  return url.replace(/\/studio\.wav(\?.*)?$/i, "/button.mp3$1");
}
