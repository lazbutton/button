import { Link } from "react-router-dom";
import { liveToItem } from "../../api/liveMap";
import { topNow } from "../../api/topbar";
import type { LiveSnapshot } from "../../api/types";
import { useAntennaClock } from "../../lib/liveClock";

/** Titre à l'antenne, avancée et temps restant. Mène au pupitre. */
export function NowPlaying({
  live,
  stale,
  answeredAt,
}: {
  live: LiveSnapshot | null;
  /** Le moteur ne répond plus : `live` est son dernier relevé. */
  stale: boolean;
  /** L'heure de sa dernière réponse, en ms. */
  answeredAt: number | undefined;
}) {
  const clock = useAntennaClock(live);
  const now = topNow({ live, item: liveToItem(live), clock, stale, answeredAt });

  return (
    <Link
      to="/antenne"
      className="tb-now"
      data-ending={now.ending ? "true" : "false"}
      data-idle={now.idle ? "true" : "false"}
      data-stale={now.stale ? "true" : "false"}
      aria-label={now.label}
    >
      <span className="tb-now-line">
        <span className="tb-now-title">{now.title}</span>
        {now.artist ? <span className="tb-now-artist">{now.artist}</span> : null}
      </span>
      {now.timed ? (
        <span className="tb-now-meta" aria-hidden="true">
          <span className="tb-now-track">
            <span style={{ transform: `scaleX(${now.ratio})` }} />
          </span>
          <span className="tb-now-time">{now.remain}</span>
        </span>
      ) : now.note ? (
        <span className="tb-now-meta" aria-hidden="true">
          <span className="tb-now-note">{now.note}</span>
        </span>
      ) : null}
    </Link>
  );
}
