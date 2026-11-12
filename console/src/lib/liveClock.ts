import { useRef } from "react";
import { anchorClock, liveTrackKey, readClock, type ClockAnchor } from "../api/antennaClock";
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
  const anchorRef = useRef<ClockAnchor | null>(null);
  anchorRef.current = anchorClock(anchorRef.current, live, wall.getTime());
  return { ...readClock(anchorRef.current, liveTrackKey(live), wall.getTime()), wall };
}
