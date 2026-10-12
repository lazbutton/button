import { Link } from "react-router-dom";
import { harborIsLive } from "../../api/emissionMeta";
import { liveToItem } from "../../api/liveMap";
import type { LiveSnapshot } from "../../api/types";
import { useAntennaClock } from "../../lib/liveClock";
import { formatRemain } from "../../lib/nowPlaying";

const ENDING_S = 15;

/** Titre à l'antenne, avancée et temps restant. Mène au pupitre. */
export function NowPlaying({ live }: { live: LiveSnapshot | null }) {
  const clock = useAntennaClock(live);
  const offline = !live || live.status === "offline";
  const harbor = harborIsLive(live);
  const item = liveToItem(live);
  const fallback = harbor ? live?.emission?.title || "Direct" : offline ? "Rien à l’antenne" : "—";
  // Sans métadonnées, l'encodeur du direct ne dit que « Direct » : le nom de l'émission parle mieux.
  const title = item && !(harbor && item.title === "Direct") ? item.title : fallback;
  const artist = item?.artist ?? "";
  const timed = !offline && !harbor && clock.durationSec > 1;
  const ratio = timed ? Math.min(1, clock.elapsedSec / clock.durationSec) : 0;
  const remain = formatRemain(clock.remainingSec);
  const ending = timed && clock.remainingSec <= ENDING_S;

  return (
    <Link
      to="/antenne"
      className="tb-now"
      data-ending={ending ? "true" : "false"}
      data-idle={offline ? "true" : "false"}
      aria-label={`À l’antenne : ${title}${artist ? `, ${artist}` : ""}${timed ? `, reste ${remain.slice(1)}` : ""}. Ouvrir l’antenne.`}
    >
      <span className="tb-now-line">
        <span className="tb-now-title">{title}</span>
        {artist ? <span className="tb-now-artist">{artist}</span> : null}
      </span>
      {timed ? (
        <span className="tb-now-meta" aria-hidden="true">
          <span className="tb-now-track">
            <span style={{ transform: `scaleX(${ratio})` }} />
          </span>
          <span className="tb-now-time">{remain}</span>
        </span>
      ) : null}
    </Link>
  );
}
