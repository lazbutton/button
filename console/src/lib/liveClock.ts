import { useRef } from "react";
import type { LiveSnapshot } from "../api/types";
import { useParisNow } from "./parisClock";

export type AntennaClock = {
  elapsedSec: number;
  remainingSec: number;
  durationSec: number;
  wall: Date;
};

/** Position du titre réellement à l’antenne, avancée chaque seconde entre deux battements. */
export function useAntennaClock(live: LiveSnapshot | null | undefined): AntennaClock {
  const wall = useParisNow();
  const snapshot = live ?? { status: "offline" as const };
  const trackKey = `${snapshot.on_air ?? ""}|${snapshot.title ?? ""}|${snapshot.artist ?? ""}`;
  const sampleElapsed = Number(snapshot.elapsed);
  const sampleRemaining = Number(snapshot.remaining);
  const sampleDuration = Number(snapshot.duration);
  const progressRef = useRef<{ key: string; atMs: number; duration: number } | null>(null);
  if (snapshot.status !== "offline" && Number.isFinite(sampleElapsed) && sampleElapsed >= 0) {
    const duration =
      Number.isFinite(sampleDuration) && sampleDuration > 0
        ? sampleDuration
        : sampleElapsed + (Number.isFinite(sampleRemaining) && sampleRemaining > 0 ? sampleRemaining : 0);
    const predicted =
      progressRef.current?.key === trackKey
        ? (wall.getTime() - progressRef.current.atMs) / 1000
        : Number.NaN;
    if (
      !progressRef.current ||
      progressRef.current.key !== trackKey ||
      Math.abs(predicted - sampleElapsed) > 3
    ) {
      progressRef.current = {
        key: trackKey,
        atMs: wall.getTime() - sampleElapsed * 1000,
        duration: Math.max(duration, 1),
      };
    }
  }
  const ticking =
    progressRef.current?.key === trackKey
      ? Math.max(0, (wall.getTime() - progressRef.current.atMs) / 1000)
      : 0;
  const elapsedSec = Math.round(ticking);
  const durationSec = Math.max(
    1,
    Math.round(progressRef.current?.key === trackKey ? progressRef.current.duration : 1),
  );
  return {
    elapsedSec,
    remainingSec: Math.max(0, durationSec - elapsedSec),
    durationSec,
    wall,
  };
}
