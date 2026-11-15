import { ExternalLink } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { liveToItem } from "../../api/liveMap";
import { coverUrl } from "../../api/covers";
import { listenLink } from "../../api/listenLink";
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
  const listen = listenLink(live, stale);
  // La pochette du titre (FON-83), quand la station les montre : jamais pour un relevé périmé, ni pour
  // une image qui ne se charge pas.
  const cover = stale || live?.status === "offline" ? null : coverUrl(live?.cover_url);
  const [broken, setBroken] = useState<string | null>(null);
  const shown = cover && cover !== broken ? cover : null;

  return (
    <div
      className="tb-now"
      data-ending={now.ending ? "true" : "false"}
      data-idle={now.idle ? "true" : "false"}
      data-stale={now.stale ? "true" : "false"}
      data-listen={listen ? "true" : "false"}
      data-cover={shown ? "true" : "false"}
    >
      {shown ? (
        <img
          className="tb-now-cover"
          src={shown}
          alt=""
          width={32}
          height={32}
          decoding="async"
          referrerPolicy="no-referrer"
          onError={() => setBroken(shown)}
        />
      ) : null}
      {/* Le lien ne contient que le titre et l'artiste, que son nom reprend dans l'ordre, même quand la
          barre resserrée cache l'artiste. L'avancée et le temps restent à côté ; le lien couvre tout le cadre. */}
      <Link to="/antenne" className="tb-now-link" aria-label={now.label}>
        <span className="tb-now-line">
          <span className="tb-now-title">{now.title}</span>{" "}
          {now.artist ? <span className="tb-now-artist">{now.artist}</span> : null}
        </span>
      </Link>
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
      {/* « Retrouver ce titre » : le lien que le service a rendu pour ce titre, seulement quand il en est sûr. */}
      {listen ? (
        <a
          className="tb-now-listen"
          href={listen}
          target="_blank"
          rel="noopener noreferrer"
          aria-label={`Retrouver ce titre : ${now.title}${now.artist ? `, ${now.artist}` : ""} (s’ouvre dans un nouvel onglet)`}
          title="Retrouver ce titre"
        >
          <ExternalLink aria-hidden="true" size={16} />
        </a>
      ) : null}
    </div>
  );
}
