import { useCallback, useEffect, useRef, useState, type RefObject } from "react";
import { answerWithin, readStream } from "../api/monitorStream";
import {
  MonitorPcmSink,
  PcmAggregator,
  WavPcmParser,
  isWavStream,
  mp3Twin,
  pcmTimingForStream,
  skipId3,
  type PcmFrame,
} from "./monitorPcm";
import {
  fetchNowPlaying,
  remainingSeconds,
  type NowPlaying,
} from "./nowPlaying";

const STREAM_FALLBACK = "https://radio.lazbutton.xyz/button.mp3";
const RECONNECT_MIN_MS = 200;
const RECONNECT_MAX_MS = 3000;
const STALL_MS = 8000;
/** Une connexion PCM qui débite depuis ce temps a repris : le backoff repart du bas. */
const STEADY_MS = 3000;
const DROP_MS = 0;

function skipToMp3(chunk: Uint8Array) {
  for (let i = 0; i + 1 < chunk.length; i++) {
    if (chunk[i] === 0xff && (chunk[i + 1] & 0xe0) === 0xe0) return chunk.slice(i);
  }
  return null;
}

function wait(sb: SourceBuffer) {
  if (!sb.updating) return Promise.resolve();
  return new Promise<void>((resolve) => {
    sb.addEventListener("updateend", () => resolve(), { once: true });
  });
}

function audioContextCtor(): typeof AudioContext | null {
  const w = window as Window & { webkitAudioContext?: typeof AudioContext };
  return window.AudioContext || w.webkitAudioContext || null;
}

export type MonitorState = {
  audioRef: RefObject<HTMLAudioElement | null>;
  analyser: AnalyserNode | null;
  analyserL: AnalyserNode | null;
  analyserR: AnalyserNode | null;
  live: boolean;
  /** La dernière connexion au flux a échoué, ou n'a pas tenu : le casque réessaie seul. */
  streamDown: boolean;
  muted: boolean;
  lagMs: number | null;
  toggleMute: () => void;
  now: NowPlaying;
  remaining: number | null;
  applyMute: (next: boolean) => void;
  ensureGraph: () => void;
  connectElement: (audio?: HTMLAudioElement | null) => void;
  connectNode: (node: AudioNode) => void;
  getContext: () => AudioContext | null;
  resumeContext: () => Promise<void>;
  isMuted: () => boolean;
  start: () => Promise<void>;
};

export function useMonitor(
  streamUrl: string,
  nowUrl: string,
  statusUrl: string,
  enabled = true,
  restartKey = "",
) {
  const stream = streamUrl.trim() || STREAM_FALLBACK;
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const ctxRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const analyserLRef = useRef<AnalyserNode | null>(null);
  const analyserRRef = useRef<AnalyserNode | null>(null);
  const gainRef = useRef<GainNode | null>(null);
  const tapRef = useRef<GainNode | null>(null);
  const connectedEl = useRef<HTMLAudioElement | null>(null);
  const connectedEls = useRef(new Set<HTMLAudioElement>());
  const abortRef = useRef<AbortController | null>(null);
  const objectUrlRef = useRef<string | null>(null);
  const pcmSinkRef = useRef<MonitorPcmSink | null>(null);
  const pcmDecoderRef = useRef<{ free: () => void } | null>(null);
  const playingRef = useRef(false);
  const mutedRef = useRef(true);
  const wantLiveRef = useRef(false);
  const playGen = useRef(0);
  const backoffRef = useRef(RECONNECT_MIN_MS);
  const reconnectTimer = useRef<number | null>(null);
  const stallTimer = useRef<number | null>(null);
  const playRef = useRef<() => Promise<void>>(async () => {});

  const [live, setLive] = useState(false);
  const [streamDown, setStreamDown] = useState(false);
  const [muted, setMuted] = useState(true);
  const [lagMs, setLagMs] = useState<number | null>(null);
  const [analyser, setAnalyser] = useState<AnalyserNode | null>(null);
  const [analyserL, setAnalyserL] = useState<AnalyserNode | null>(null);
  const [analyserR, setAnalyserR] = useState<AnalyserNode | null>(null);
  const [now, setNow] = useState<NowPlaying>({
    title: "",
    artist: "",
    duration: null,
    startedAt: null,
  });
  const [, setClock] = useState(0);

  const applyMute = useCallback((next: boolean) => {
    mutedRef.current = next;
    setMuted(next);
    // L'élément reste muet tant que l'écoute n'est pas demandée : le navigateur
    // autorise alors play() dès l'arrivée, et les haut-parleurs restent coupés.
    if (audioRef.current) audioRef.current.muted = next;
    for (const el of connectedEls.current) el.muted = next;
    const gain = gainRef.current;
    if (gain) {
      gain.gain.setTargetAtTime(next ? 0 : 1, gain.context.currentTime, 0.008);
    }
  }, []);

  const ensureGraph = useCallback(() => {
    const Ctx = audioContextCtor();
    if (!Ctx) return;
    if (!ctxRef.current) {
      const ctx = new Ctx({ latencyHint: "playback" });
      const node = ctx.createAnalyser();
      node.fftSize = 2048;
      node.smoothingTimeConstant = 0.15;
      const left = ctx.createAnalyser();
      left.fftSize = 1024;
      left.smoothingTimeConstant = 0;
      const right = ctx.createAnalyser();
      right.fftSize = 1024;
      right.smoothingTimeConstant = 0;
      const gain = ctx.createGain();
      gain.gain.value = mutedRef.current ? 0 : 1;
      const tap = ctx.createGain();
      tap.gain.value = 1;
      const splitter = ctx.createChannelSplitter(2);
      tap.connect(node);
      tap.connect(splitter);
      splitter.connect(left, 0);
      splitter.connect(right, 1);
      tap.connect(gain);
      gain.connect(ctx.destination);
      ctxRef.current = ctx;
      analyserRef.current = node;
      analyserLRef.current = left;
      analyserRRef.current = right;
      gainRef.current = gain;
      tapRef.current = tap;
      setAnalyser(node);
      setAnalyserL(left);
      setAnalyserR(right);
    }
  }, []);

  const connectElement = useCallback((el?: HTMLAudioElement | null) => {
    const audio = el ?? audioRef.current;
    const ctx = ctxRef.current;
    const tap = tapRef.current;
    if (!audio || !ctx || !tap) return;
    if (connectedEls.current.has(audio)) return;
    try {
      const source = ctx.createMediaElementSource(audio);
      source.connect(tap);
    } catch {
      /* already connected to a graph */
    }
    connectedEls.current.add(audio);
    if (audio === audioRef.current)     connectedEl.current = audio;
  }, []);

  const connectNode = useCallback((node: AudioNode) => {
    const tap = tapRef.current;
    if (!tap) return;
    try {
      node.connect(tap);
    } catch {
      /* already connected */
    }
  }, []);

  const getContext = useCallback(() => ctxRef.current, []);

  const teardownPcm = useCallback(() => {
    pcmSinkRef.current?.stop();
    pcmSinkRef.current = null;
    try {
      pcmDecoderRef.current?.free();
    } catch {
      /* already freed */
    }
    pcmDecoderRef.current = null;
  }, []);

  const teardownStream = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    teardownPcm();
    // Le calage que guettait l'élément ne vaut que pour ce qu'il chargeait :
    // sinon, 8 s plus tard, il relancerait la connexion suivante, même saine.
    if (stallTimer.current != null) {
      window.clearTimeout(stallTimer.current);
      stallTimer.current = null;
    }
    const audio = audioRef.current;
    if (audio) {
      audio.pause();
      audio.removeAttribute("src");
      audio.load();
    }
    if (objectUrlRef.current) {
      URL.revokeObjectURL(objectUrlRef.current);
      objectUrlRef.current = null;
    }
  }, [teardownPcm]);

  const clearReconnect = useCallback(() => {
    if (reconnectTimer.current != null) {
      window.clearTimeout(reconnectTimer.current);
      reconnectTimer.current = null;
    }
  }, []);

  const scheduleReconnect = useCallback(
    (delayMs?: number) => {
      if (!wantLiveRef.current) return;
      if (reconnectTimer.current != null) return;
      const waitMs = delayMs ?? backoffRef.current;
      backoffRef.current = Math.min(RECONNECT_MAX_MS, Math.round(backoffRef.current * 1.7));
      reconnectTimer.current = window.setTimeout(() => {
        reconnectTimer.current = null;
        if (wantLiveRef.current) void playRef.current();
      }, waitMs);
    },
    [],
  );

  // Joue le flux PCM ou WAV jusqu'à sa fin : fermé par le serveur, coupé, ou
  // muet depuis STALL_MS. Le casque se reconnecte alors, avec le backoff. Une
  // connexion qui n'a pas tenu STEADY_MS est une reprise ratée : le bouton le
  // dit, et l'attente continue de monter, pour ne pas marteler un serveur qui
  // accepte la connexion puis la ferme aussitôt.
  const pumpPcm = useCallback(
    async (
      reader: ReadableStreamDefaultReader<Uint8Array>,
      abort: AbortController,
      gen: number,
      sink: MonitorPcmSink,
      decode: (chunk: Uint8Array) => PcmFrame | null,
    ) => {
      const agg = new PcmAggregator();
      const enqueue = (frame: PcmFrame | null) => {
        if (frame) sink.enqueue(frame.channelData, frame.samplesDecoded, frame.sampleRate);
      };
      const end = await readStream(reader, {
        stallMs: STALL_MS,
        steadyMs: STEADY_MS,
        alive: () => playingRef.current && playGen.current === gen,
        stall: () => abort.abort(),
        onChunk: (chunk) => {
          const decoded = decode(chunk);
          if (decoded) enqueue(agg.push(decoded.channelData, decoded.samplesDecoded, decoded.sampleRate));
        },
        onSteady: () => {
          backoffRef.current = RECONNECT_MIN_MS;
          setStreamDown(false);
        },
      });
      if (playGen.current !== gen || !wantLiveRef.current) return;
      if (end.closed) enqueue(agg.flush());
      setLive(false);
      if (!end.steady) setStreamDown(true);
      scheduleReconnect();
    },
    [scheduleReconnect],
  );

  // Demande le flux. Un serveur peut accepter la connexion sans jamais
  // répondre : sans en-têtes en STALL_MS, la demande est abandonnée, le bouton
  // dit que le flux ne répond pas, et l'essai passe au chemin suivant.
  const requestStream = useCallback(async (url: string, gen: number) => {
    const abort = new AbortController();
    abortRef.current = abort;
    const res = await answerWithin(
      fetch(url, { mode: "cors", cache: "no-store", signal: abort.signal }),
      STALL_MS,
      () => {
        abort.abort();
        if (playGen.current === gen) setStreamDown(true);
      },
    );
    if (playGen.current !== gen) {
      abort.abort();
      throw new Error("stale");
    }
    if (!res.ok || !res.body) throw new Error("fetch");
    return { body: res.body, abort };
  }, []);

  const startWav = useCallback(
    async (url: string, gen: number) => {
      ensureGraph();
      const ctx = ctxRef.current;
      const tap = tapRef.current;
      if (!ctx || !tap) throw new Error("ctx");
      const timing = pcmTimingForStream(url);
      const sink = new MonitorPcmSink(ctx, tap, timing.keepS, timing.maxS, timing.startS);
      pcmSinkRef.current = sink;
      const parser = new WavPcmParser();

      const { body, abort } = await requestStream(url, gen);
      void pumpPcm(body.getReader(), abort, gen, sink, (chunk) => parser.push(chunk));
    },
    [ensureGraph, pumpPcm, requestStream],
  );

  const startPcm = useCallback(
    async (url: string, gen: number) => {
      if (isWavStream(url)) {
        await startWav(url, gen);
        return;
      }
      ensureGraph();
      const ctx = ctxRef.current;
      const tap = tapRef.current;
      if (!ctx || !tap) throw new Error("ctx");
      const { MPEGDecoder } = await import("mpg123-decoder");
      const decoder = new MPEGDecoder({ enableGapless: true });
      await decoder.ready;
      if (playGen.current !== gen) {
        decoder.free();
        throw new Error("stale");
      }
      pcmDecoderRef.current = decoder;
      const timing = pcmTimingForStream(url);
      const sink = new MonitorPcmSink(ctx, tap, timing.keepS, timing.maxS, timing.startS);
      pcmSinkRef.current = sink;

      const { body, abort } = await requestStream(url, gen);
      let synced = false;
      void pumpPcm(body.getReader(), abort, gen, sink, (value) => {
        let chunk = value;
        if (!synced) {
          chunk = skipId3(chunk);
          const mp3 = skipToMp3(chunk);
          if (!mp3) return null;
          chunk = mp3;
          synced = true;
        }
        return decoder.decode(chunk);
      });
    },
    [ensureGraph, pumpPcm, requestStream, startWav],
  );

  const startMse = useCallback(
    async (url: string, gen: number) => {
      const audio = audioRef.current;
      if (!audio) throw new Error("no-audio");
      if (!window.MediaSource || !MediaSource.isTypeSupported("audio/mpeg")) {
        throw new Error("mse");
      }
      const { body } = await requestStream(url, gen);

      const mediaSource = new MediaSource();
      const obj = URL.createObjectURL(mediaSource);
      objectUrlRef.current = obj;
      audio.src = obj;

      await new Promise<void>((resolve, reject) => {
        mediaSource.addEventListener("sourceopen", () => resolve(), { once: true });
        mediaSource.addEventListener("error", () => reject(new Error("ms")), { once: true });
      });

      const timing = pcmTimingForStream(url);
      const sb = mediaSource.addSourceBuffer("audio/mpeg");
      sb.mode = "sequence";
      const reader = body.getReader();
      let dropping = DROP_MS > 0;
      let tFirst = 0;
      let synced = false;

      void (async () => {
        try {
          while (playingRef.current && playGen.current === gen) {
            const { done, value } = await reader.read();
            if (done || !value?.byteLength) {
              if (mediaSource.readyState === "open") {
                try {
                  mediaSource.endOfStream();
                } catch {
                  /* already closed */
                }
              }
              break;
            }
            const now = performance.now();
            if (dropping) {
              if (!tFirst) tFirst = now;
              if (now - tFirst < DROP_MS) continue;
              dropping = false;
            }
            const payload = synced ? value : skipToMp3(value);
            if (!payload) continue;
            synced = true;
            if (mediaSource.readyState !== "open") break;
            await wait(sb);
            if (playGen.current !== gen) break;
            if (sb.buffered.length > 0) {
              const start = sb.buffered.start(0);
              const end = sb.buffered.end(sb.buffered.length - 1);
              if (end - start > timing.maxS) {
                sb.remove(start, end - timing.keepS);
                await wait(sb);
              }
            }
            sb.appendBuffer(payload);
            await wait(sb);
            if (sb.buffered.length > 0 && audio) {
              const liveStart = sb.buffered.start(0);
              const liveEnd = sb.buffered.end(sb.buffered.length - 1);
              const lag = liveEnd - audio.currentTime;
              if (lag > timing.maxS) {
                audio.currentTime = Math.max(liveStart, liveEnd - timing.keepS);
              }
            }
          }
        } catch {
          if (playGen.current === gen && wantLiveRef.current) {
            setLive(false);
            scheduleReconnect(RECONNECT_MIN_MS);
          }
        }
      })();
    },
    [requestStream, scheduleReconnect],
  );

  const play = useCallback(async () => {
    const audio = audioRef.current;
    if (!audio || !wantLiveRef.current) return;
    clearReconnect();
    const gen = ++playGen.current;
    if (audio.getAttribute("src") || pcmSinkRef.current) teardownStream();
    playingRef.current = true;
    ensureGraph();
    applyMute(mutedRef.current);
    // Sans geste de l'utilisateur, cette attente dure jusqu'à son premier clic.
    // Elle ne compte pas dans celle du flux, bornée à chaque demande.
    if (ctxRef.current?.state === "suspended") {
      await ctxRef.current.resume().catch(() => undefined);
    }
    let usedElement = false;
    try {
      try {
        await startPcm(stream, gen);
      } catch {
        if (gen !== playGen.current || !wantLiveRef.current) return;
        teardownPcm();
        const fallback = mp3Twin(stream);
        if (fallback !== stream) {
          try {
            await startPcm(fallback, gen);
          } catch {
            if (gen !== playGen.current || !wantLiveRef.current) return;
            try {
              await startMse(fallback, gen);
            } catch {
              if (gen !== playGen.current || !wantLiveRef.current) return;
              audio.crossOrigin = "anonymous";
              audio.src = `${fallback}?t=${Date.now()}`;
            }
            ensureGraph();
            connectElement(audio);
            usedElement = true;
          }
        } else {
          try {
            await startMse(stream, gen);
          } catch {
            if (gen !== playGen.current || !wantLiveRef.current) return;
            audio.crossOrigin = "anonymous";
            audio.src = `${stream}?t=${Date.now()}`;
          }
          ensureGraph();
          connectElement(audio);
          usedElement = true;
        }
      }
      if (gen !== playGen.current) return;
      if (!usedElement && audio.getAttribute("src")) {
        audio.removeAttribute("src");
      }
      ensureGraph();
      applyMute(mutedRef.current);
      if (ctxRef.current?.state === "suspended") {
        await ctxRef.current.resume().catch(() => undefined);
      }
      // L'élément n'attend pas sa réponse plus longtemps qu'une demande du
      // flux : sans elle, l'essai échoue, et le bouton le dit.
      if (usedElement) {
        try {
          await answerWithin(audio.play(), STALL_MS);
        } catch (err) {
          if (!(err instanceof DOMException) || err.name !== "NotAllowedError") throw err;
          audio.muted = true;
          applyMute(true);
          await answerWithin(audio.play(), STALL_MS);
        }
      }
      if (gen !== playGen.current) return;
      setLive(true);
      // L'élément joue déjà. Le flux PCM, lui, n'a repris qu'une fois qu'il a
      // débité un moment : pumpPcm le dit.
      if (usedElement) {
        backoffRef.current = RECONNECT_MIN_MS;
        setStreamDown(false);
      }
    } catch {
      if (gen !== playGen.current) return;
      teardownStream();
      setLive(false);
      if (wantLiveRef.current) {
        setStreamDown(true);
        scheduleReconnect();
      }
    }
  }, [
    applyMute,
    clearReconnect,
    connectElement,
    ensureGraph,
    scheduleReconnect,
    startMse,
    startPcm,
    stream,
    teardownPcm,
    teardownStream,
  ]);

  playRef.current = play;

  const resumeContext = useCallback(async () => {
    if (ctxRef.current?.state === "suspended") {
      await ctxRef.current.resume().catch(() => undefined);
    }
  }, []);

  const isMuted = useCallback(() => mutedRef.current, []);

  const start = useCallback(async () => {
    wantLiveRef.current = true;
    if (ctxRef.current?.state === "suspended") {
      await ctxRef.current.resume().catch(() => undefined);
    }
    await playRef.current();
  }, []);

  const toggleMute = useCallback(() => {
    const next = !mutedRef.current;
    void (async () => {
      if (!playingRef.current) await playRef.current();
      // Écouter pendant que le casque attend sa reprise : il réessaie tout de suite.
      else if (!next && reconnectTimer.current != null) void playRef.current();
      if (ctxRef.current?.state === "suspended") {
        await ctxRef.current.resume().catch(() => undefined);
      }
      applyMute(next);
      const audio = audioRef.current;
      if (audio?.paused && wantLiveRef.current && audio.getAttribute("src")) {
        await audio.play().catch(() => undefined);
      }
    })();
  }, [applyMute]);

  useEffect(() => {
    wantLiveRef.current = enabled;
    // Un autre flux, ou plus de flux : l'échec du précédent ne vaut plus.
    setStreamDown(false);
    if (!enabled) {
      clearReconnect();
      if (stallTimer.current != null) {
        window.clearTimeout(stallTimer.current);
        stallTimer.current = null;
      }
      playGen.current += 1;
      playingRef.current = false;
      teardownStream();
      setLive(false);
      return;
    }
    const id = window.setTimeout(() => void playRef.current(), 0);
    return () => {
      wantLiveRef.current = false;
      window.clearTimeout(id);
      clearReconnect();
      if (stallTimer.current != null) {
        window.clearTimeout(stallTimer.current);
        stallTimer.current = null;
      }
      playGen.current += 1;
      playingRef.current = false;
      teardownStream();
    };
  }, [clearReconnect, enabled, restartKey, stream, teardownStream]);

  useEffect(() => {
    return () => {
      void ctxRef.current?.close();
      ctxRef.current = null;
      analyserRef.current = null;
      analyserLRef.current = null;
      analyserRRef.current = null;
      gainRef.current = null;
      tapRef.current = null;
      connectedEl.current = null;
    };
  }, []);

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;

    // L'élément a fini, échoué ou calé : le casque se reconnecte, avec le
    // backoff. Un flux absent, un 404 d'Icecast pendant que le playout
    // redémarre par exemple, allonge ainsi l'attente au lieu d'être redemandé
    // toutes les 200 ms.
    const bump = () => {
      if (!wantLiveRef.current) return;
      if (!audio.getAttribute("src") && !pcmSinkRef.current) return;
      setLive(false);
      scheduleReconnect();
    };

    const onWaiting = () => {
      if (stallTimer.current != null) window.clearTimeout(stallTimer.current);
      const frozenAt = audio.currentTime;
      stallTimer.current = window.setTimeout(() => {
        stallTimer.current = null;
        if (Math.abs(audio.currentTime - frozenAt) < 0.2) bump();
      }, STALL_MS);
    };

    const onFlow = () => {
      if (stallTimer.current != null) {
        window.clearTimeout(stallTimer.current);
        stallTimer.current = null;
      }
    };

    audio.addEventListener("ended", bump);
    audio.addEventListener("error", bump);
    audio.addEventListener("waiting", onWaiting);
    audio.addEventListener("playing", onFlow);
    audio.addEventListener("canplay", onFlow);
    return () => {
      audio.removeEventListener("ended", bump);
      audio.removeEventListener("error", bump);
      audio.removeEventListener("waiting", onWaiting);
      audio.removeEventListener("playing", onFlow);
      audio.removeEventListener("canplay", onFlow);
    };
  }, [scheduleReconnect]);

  useEffect(() => {
    let cancelled = false;
    async function poll() {
      const next = await fetchNowPlaying(nowUrl, statusUrl);
      if (!cancelled && next) setNow(next);
    }
    void poll();
    const id = window.setInterval(() => void poll(), 5000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [nowUrl, statusUrl]);

  useEffect(() => {
    if (!now.duration || !now.startedAt) return;
    const id = window.setInterval(() => setClock((n) => n + 1), 1000);
    return () => window.clearInterval(id);
  }, [now.duration, now.startedAt]);

  useEffect(() => {
    const id = window.setInterval(() => {
      const sink = pcmSinkRef.current;
      const audio = audioRef.current;
      let next: number | null = null;
      if (sink && ctxRef.current?.state === "running") {
        next = Math.round(sink.lagS * 1000);
      } else if (audio && audio.buffered.length > 0) {
        const end = audio.buffered.end(audio.buffered.length - 1);
        next = Math.round((end - audio.currentTime) * 1000);
      }
      setLagMs((prev) => (prev === next ? prev : next));
    }, 250);
    return () => window.clearInterval(id);
  }, []);

  return {
    audioRef,
    analyser,
    analyserL,
    analyserR,
    live,
    streamDown,
    muted,
    lagMs,
    toggleMute,
    now,
    remaining: remainingSeconds(now),
    applyMute,
    ensureGraph,
    connectElement,
    connectNode,
    getContext,
    resumeContext,
    isMuted,
    start,
  };
}
