import { ListMusic, Radio, Repeat2, Shuffle, type LucideIcon } from "lucide-react";
import type { CartMode } from "../../api/types";

/** One icon per way a bac plays. A relay is a stream, not a list. */
export const MODE_ICONS: Record<CartMode, LucideIcon> = {
  playlist: ListMusic,
  playlist_loop: Repeat2,
  random: Shuffle,
  relay: Radio,
};
