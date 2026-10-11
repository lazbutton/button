import { useCallback, useEffect, useRef, useState, type RefObject } from "react";
import { apiArrayBuffer, apiBlob } from "../api/client";
import {
  CONDUCTEUR_JSON,
  antennaFile,
  antennaNextItem,
  antennaRundownItem,
  clockElapsedSec,
  clockNextFileItem,
  clockPlayableItem,
  rundownFileHref,
  rundownItemKey,
} from "../api/rundownLive";
import { useApiJson } from "../api/useApiJson";
import type { LiveSnapshot, Rundown, RundownItem } from "../api/types";
import { displayNow, type NowPlaying } from "./nowPlaying";
import { clockRemainingSec, RundownClockPlayer, type ClockGraph } from "./rundownClockPlayer";

const TICK_MS = 100;
const FALLBACK_DRIFT_S = 0.18;
const FALLBACK_RATE_MIN = 0.97;
const FALLBACK_RATE_MAX = 1.03;

export type RundownGraph = ClockGraph & {
  applyMute: (next: boolean) => void;
  connectElement: (audio?: HTMLAudioElement | null) => void;
  resumeContext: () => Promise<void>;
  isMuted: () => boolean;
};

type Props = {
  enabled: boolean;
  audioRef: RefObject<HTMLAudioElement | null>;
  graph: RundownGraph;
  live: LiveSnapshot | null;
};

function displayItem(item: RundownItem): NowPlaying {
  const shown = displayNow({
    title: item.title || item.resource,
    artist: item.artist || "",
    duration: item.duration,
    started_at: item.at,
  });
  const start = Date.parse(item.at);
  return {
    ...shown,
    startedAt: Number.isFinite(start) ? start : shown.startedAt,
  };
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

export function useRundownMonitor({ enabled, audioRef, graph, live }: Props) {
  const rundown = useApiJson<Rundown>(CONDUCTEUR_JSON, 2000);
  const playerRef = useRef<RundownClockPlayer | null>(null);
  const fallbackKey = useRef("");
  const fallbackUrls = useRef(new Map<string, string>());
  const fallbackInflight = useRef(new Map<string, Promise<string>>());
  const wantRef = useRef(false);
  const liveRef = useRef(live);
  liveRef.current = live;
  const antennaAnchor = useRef<{ key: string; atMs: number } | null>(null);
  const graphRef = useRef(graph);
  graphRef.current = graph;
  const modeRef = useRef<"buffer" | "element" | "idle">("idle");
  const inFlightRef = useRef(false);
  const [liveFlag, setLiveFlag] = useState(false);
  const [missing, setMissing] = useState(false);
  const [lagMs, setLagMs] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [now, setNow] = useState<NowPlaying>({
    title: "",
    artist: "",
    duration: null,
    startedAt: null,
  });
  const [remaining, setRemaining] = useState<number | null>(null);

  if (!playerRef.current) {
    playerRef.current = new RundownClockPlayer(
      {
        ensureGraph: () => graphRef.current.ensureGraph(),
        getContext: () => graphRef.current.getContext(),
        connectNode: (node) => graphRef.current.connectNode(node),
      },
      apiArrayBuffer,
    );
  }

  const stopFallback = useCallback(() => {
    const audio = audioRef.current;
    fallbackKey.current = "";
    if (!audio) return;
    audio.pause();
    audio.removeAttribute("src");
    audio.load();
    try {
      audio.playbackRate = 1;
    } catch {
      /* proto */
    }
  }, [audioRef]);

  const stopAll = useCallback(() => {
    playerRef.current?.stop();
    stopFallback();
    modeRef.current = "idle";
    setLiveFlag(false);
    setLagMs(null);
    setLoading(false);
  }, [stopFallback]);

  const blobFor = useCallback(async (href: string) => {
    const hit = fallbackUrls.current.get(href);
    if (hit) return hit;
    const pending = fallbackInflight.current.get(href);
    if (pending) return pending;
    const promise = apiBlob(href)
      .then((url) => {
        fallbackUrls.current.set(href, url);
        return url;
      })
      .finally(() => {
        fallbackInflight.current.delete(href);
      });
    fallbackInflight.current.set(href, promise);
    return promise;
  }, []);

  const syncFallback = useCallback(
    async (item: RundownItem, wall: Date) => {
      const href = rundownFileHref(item);
      const audio = audioRef.current;
      if (!href || !audio || !wantRef.current) return false;
      const elapsed = clockElapsedSec(item, wall);
      if (elapsed < -0.05) {
        stopFallback();
        return true;
      }
      const key = rundownItemKey(item);
      try {
        graph.ensureGraph();
        graph.connectElement(audio);
        if (fallbackKey.current !== key || !audio.getAttribute("src")) {
          const url = await blobFor(href);
          if (!wantRef.current) return false;
          audio.src = url;
          fallbackKey.current = key;
          await new Promise<void>((resolve, reject) => {
            const onReady = () => {
              audio.removeEventListener("loadedmetadata", onReady);
              audio.removeEventListener("error", onErr);
              resolve();
            };
            const onErr = () => {
              audio.removeEventListener("loadedmetadata", onReady);
              audio.removeEventListener("error", onErr);
              reject(new Error("audio"));
            };
            audio.addEventListener("loadedmetadata", onReady, { once: true });
            audio.addEventListener("error", onErr, { once: true });
            audio.load();
          });
        }
        if (!wantRef.current) return false;
        const duration = Number.isFinite(audio.duration) ? audio.duration : Number(item.duration) || 0;
        const target = Math.min(Math.max(0, elapsed), Math.max(0, duration - 0.05));
        const error = audio.currentTime - target;
        if (!Number.isFinite(error) || Math.abs(error) > FALLBACK_DRIFT_S) {
          audio.currentTime = target;
          audio.playbackRate = 1;
        } else {
          audio.playbackRate = clamp(1 - error * 0.35, FALLBACK_RATE_MIN, FALLBACK_RATE_MAX);
        }
        graph.applyMute(graph.isMuted());
        await graph.resumeContext();
        if (audio.paused) await audio.play();
        modeRef.current = "element";
        setLagMs(Math.round(error * 1000));
        setLiveFlag(true);
        setMissing(false);
        return true;
      } catch {
        fallbackKey.current = "";
        setLiveFlag(false);
        setMissing(true);
        return false;
      }
    },
    [audioRef, blobFor, graph, stopFallback],
  );

  const paint = useCallback((item: RundownItem | null, wall: Date, playing: boolean) => {
    if (!item) {
      setNow({ title: "", artist: "", duration: null, startedAt: null });
      setRemaining(null);
      setLagMs(null);
      setLiveFlag(false);
      return;
    }
    setNow(displayItem(item));
    const elapsed = clockElapsedSec(item, wall);
    if (elapsed < 0) {
      setRemaining(-elapsed);
      setLiveFlag(false);
      setLagMs(null);
      return;
    }
    setRemaining(clockRemainingSec(item, wall));
    setLiveFlag(playing);
  }, []);

  const sync = useCallback(async () => {
    if (!wantRef.current || inFlightRef.current) return;
    inFlightRef.current = true;
    try {
    const items = rundown.data?.items ?? [];
    const wall = new Date();
    const onAir = antennaFile(liveRef.current);
    let antenna: RundownItem | null = null;
    if (onAir) {
      const predicted =
        antennaAnchor.current?.key === onAir.key
          ? (wall.getTime() - antennaAnchor.current.atMs) / 1000
          : Number.NaN;
      if (
        !antennaAnchor.current ||
        antennaAnchor.current.key !== onAir.key ||
        Math.abs(predicted - onAir.elapsed) > 2.5
      ) {
        antennaAnchor.current = {
          key: onAir.key,
          atMs: wall.getTime() - onAir.elapsed * 1000,
        };
      }
      antenna = antennaRundownItem(onAir, antennaAnchor.current.atMs);
    } else {
      antennaAnchor.current = null;
    }
    const item = antenna ?? clockPlayableItem(items, wall);
    const next = antenna
      ? antennaNextItem(liveRef.current, wall)
      : item
        ? clockNextFileItem(items, item)
        : null;
    const later = next ? clockNextFileItem(items, next) : null;
    if (!item) {
      stopAll();
      setMissing(false);
      paint(null, wall, false);
      return;
    }
    const href = rundownFileHref(item);
    if (!href) {
      stopAll();
      setMissing(true);
      paint(item, wall, false);
      return;
    }
    const player = playerRef.current;
    const third = later ? clockNextFileItem(items, later) : null;
    player?.prefetch([item, next, later, third]);
    if (player?.loading) setLoading(true);
    let playing = false;
    if (modeRef.current !== "element") {
      playing = Boolean(await player?.sync(item, next, wall));
      if (playing) {
        if (modeRef.current === "idle" || modeRef.current === "buffer") {
          stopFallback();
        }
        modeRef.current = "buffer";
        const lag = player?.lagS(item, new Date()) ?? null;
        setLagMs(lag == null ? null : Math.round(lag * 1000));
        setMissing(false);
      } else if (clockElapsedSec(item, wall) >= 0) {
        playing = await syncFallback(item, wall);
      }
    } else {
      playing = await syncFallback(item, wall);
    }
    if (!wantRef.current) return;
    setLoading(Boolean(player?.loading) && !playing);
    paint(item, wall, playing);
    } finally {
      inFlightRef.current = false;
    }
  }, [paint, rundown.data, stopAll, stopFallback, syncFallback]);

  const syncRef = useRef(sync);
  syncRef.current = sync;

  useEffect(() => {
    wantRef.current = enabled;
    if (!enabled) {
      stopAll();
      setMissing(false);
      setRemaining(null);
      return;
    }
    void syncRef.current();
    const id = window.setInterval(() => void syncRef.current(), TICK_MS);
    return () => window.clearInterval(id);
  }, [enabled, rundown.data, stopAll]);

  useEffect(() => {
    return () => {
      wantRef.current = false;
      playerRef.current?.dispose();
      playerRef.current = null;
      for (const url of fallbackUrls.current.values()) URL.revokeObjectURL(url);
      fallbackUrls.current.clear();
    };
  }, []);

  const toggleMute = useCallback(() => {
    const next = !graph.isMuted();
    graph.applyMute(next);
    void graph.resumeContext();
    if (!next) void syncRef.current();
    const audio = audioRef.current;
    if (!next && audio?.paused && audio.getAttribute("src")) {
      void audio.play().catch(() => undefined);
    }
  }, [audioRef, graph]);

  return {
    live: liveFlag,
    missing,
    now,
    remaining,
    lagMs,
    loading,
    toggleMute,
  };
}
