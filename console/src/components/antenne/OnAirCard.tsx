import { Mic, SkipForward } from "lucide-react";
import type { ReactNode, Ref } from "react";
import { mmss, progressLabel } from "../../api/antenneDesk";
import { kindLabel, type CatalogItem } from "../../mock/catalog";

export type AirState = "on" | "direct" | "silence" | "problem" | "off";

const ENDING_S = 15;

const KICKER: Record<AirState, string> = {
  on: "À l’antenne",
  direct: "En direct",
  silence: "À l’antenne",
  problem: "À l’antenne",
  off: "Hors antenne",
};

/** Ce qui passe : compte à rebours, titre, avancée, et les deux gestes du pupitre. */
export function OnAirCard({
  state,
  stale,
  item,
  elapsedSec,
  durationSec,
  remainingSec,
  source,
  endsAt,
  anchor,
  onSkip,
  skipDisabled,
  onDirect,
  directRef,
  children,
}: {
  state: AirState;
  /** Le moteur ne répond plus : la carte montre le dernier relevé, et ses gestes restent ceux de cet état. */
  stale: boolean;
  item: CatalogItem | undefined;
  elapsedSec: number;
  durationSec: number;
  remainingSec: number;
  /** Auto-DJ, Carts, Relais… */
  source: string;
  endsAt: string | null;
  /** « Ancre :00 dans 7:20 » */
  anchor: string | null;
  onSkip: () => void;
  skipDisabled: boolean;
  onDirect: () => void;
  directRef?: Ref<HTMLButtonElement>;
  /** Nommer le direct, arrêter un set daté. */
  children?: ReactNode;
}) {
  const direct = state === "direct";
  const off = state === "off";
  // Le dernier titre connu reste, mais son temps ne se compte plus : rien ne dit qu'il passe encore.
  const timed = !direct && !off && !stale && durationSec > 1;
  const ending = timed && remainingSec <= ENDING_S;
  const hero = stale || off ? "—" : direct ? mmss(elapsedSec) : mmss(remainingSec);
  const heroLabel = stale ? "inconnu" : off ? "pas de signal" : direct ? "écoulé" : "restant";
  const ratio = timed ? Math.min(1, elapsedSec / durationSec) : 0;
  const title =
    item?.title || item?.artist || (stale ? "Aucun titre connu" : off ? "L’antenne ne répond pas" : "Rien à l’antenne");
  const artist = item?.title && item.artist ? item.artist : "";

  return (
    <section className="ant-air" data-state={state} data-ending={ending ? "true" : "false"} aria-label="À l’antenne">
      <div className="ant-air-kicker">
        <span className="ant-air-badge">{stale ? "Sans nouvelles" : KICKER[state]}</span>
        {source && !direct && !off && !stale ? <span>{source}</span> : null}
        {endsAt ? <span>fin {endsAt}</span> : null}
        {anchor ? <span className="ant-air-anchor">{anchor}</span> : null}
      </div>
      <div className="ant-air-main">
        <div className="ant-air-count" role="timer" aria-label={`${heroLabel} ${hero}`}>
          <span className="ant-air-count-value" aria-hidden="true">
            {hero}
          </span>
          <span className="ant-air-count-label" aria-hidden="true">
            {heroLabel}
          </span>
        </div>
        <div className="ant-air-copy">
          <p className="ant-air-title">
            {item ? <span className={`ant-kind is-${item.kind}`} title={kindLabel(item.kind)} aria-hidden="true" /> : null}
            <span>{title}</span>
          </p>
          {artist ? <p className="ant-air-artist">{artist}</p> : null}
          {timed ? (
            <div className="ant-air-progress">
              <span className="ant-air-track" aria-hidden="true">
                <span style={{ transform: `scaleX(${ratio})` }} />
              </span>
              <span className="ant-air-times">{progressLabel(elapsedSec, durationSec)}</span>
            </div>
          ) : null}
          {children}
        </div>
        <div className="ant-air-actions">
          {!direct ? (
            <button
              type="button"
              className="ant-btn ant-btn--primary"
              onClick={onSkip}
              disabled={skipDisabled}
              aria-keyshortcuts="Space"
            >
              <SkipForward size={18} aria-hidden="true" />
              Suivant
              <kbd>Espace</kbd>
            </button>
          ) : null}
          <button ref={directRef} type="button" className="ant-btn" onClick={onDirect} aria-haspopup="dialog">
            <Mic size={17} aria-hidden="true" />
            {direct ? "Infos encodeur" : "Passer en direct"}
          </button>
        </div>
      </div>
    </section>
  );
}
