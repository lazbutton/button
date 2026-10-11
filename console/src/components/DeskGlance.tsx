import { Badge } from "@radix-ui/themes";
import { SkipForward } from "lucide-react";
import type { CSSProperties, ReactNode } from "react";
import { formatMmSs } from "../lib/parisClock";
import { kindLabel, type CatalogItem } from "../mock/catalog";

export type GlanceChip = {
  key: string;
  label: string;
  value: string;
  color?: "gray" | "green" | "red" | "amber";
  warn?: boolean;
  button?: boolean;
  onClick?: () => void;
};

export type GlanceSource = {
  /** Libellé humain : Auto-DJ, Direct, Cart… */
  label: string;
  /** Identifiant Liquidsoap (autodj, stream, relay, carts, jingles) ou offline. */
  id: string;
};

export function DeskGlance({
  item,
  elapsedSec,
  durationSec,
  remainingSec,
  chips = [],
  onSkip,
  skipDisabled = false,
  keysHint,
  banner,
  source,
  endsAt,
  toolbar,
  health,
  children,
}: {
  item: CatalogItem | undefined;
  elapsedSec: number;
  durationSec: number;
  remainingSec: number;
  chips?: GlanceChip[];
  onSkip: () => void;
  skipDisabled?: boolean;
  keysHint?: string;
  banner?: string;
  /** Source à l'antenne, affichée en badge sous le titre. */
  source?: GlanceSource;
  /** Heure de fin prévue du titre (HH:MM), affichée près du badge source. */
  endsAt?: string | null;
  /** Actions secondaires (dépannage…) sous le bouton Passer. */
  toolbar?: ReactNode;
  /** Bandeau santé, sous les chips. */
  health?: ReactNode;
  children?: ReactNode;
}) {
  const live = source?.id === "stream";
  const offline = source?.id === "offline";
  const heroSec = live ? elapsedSec : remainingSec;
  const heroLabel = live ? "en direct" : "restant";
  const heroText = offline ? "--:--" : formatMmSs(heroSec);
  const pct = durationSec > 0 ? Math.min(100, Math.round((elapsedSec / durationSec) * 100)) : 0;
  const progressStyle = { "--pct": `${pct}%` } as CSSProperties;

  return (
    <section className="now" aria-label="À l’antenne">
      <div className="now-remain" aria-label={heroLabel}>
        {heroText}
        <small>{heroLabel}</small>
      </div>
      <div className="now-copy">
        {item ? (
          <p className="now-title">
            <span className={`kind is-${item.kind}`} title={kindLabel(item.kind)} aria-hidden="true" />
            <span className="now-lines">
              <span className="t">{item.title || item.artist}</span>
              {item.artist && item.title ? <span className="a">{item.artist}</span> : null}
            </span>
          </p>
        ) : (
          <p className="now-title">
            <span>Cherche un titre et mets-le à la suite</span>
          </p>
        )}
        <div className="progress" style={progressStyle} aria-hidden="true">
          <div className="progress-fill" />
          <div className="progress-head" />
        </div>
        <div className="now-meta">
          {source ? (
            <span className="source" title="Source à l’antenne">
              {source.label}
            </span>
          ) : null}
          {endsAt ? <span>fin {endsAt}</span> : null}
          {keysHint ? (
            <span className="keys">
              <kbd>Espace</kbd> suivant · <kbd>/</kbd> chercher · <kbd>Entrée</kbd> à la suite
            </span>
          ) : null}
        </div>
      </div>
      <button type="button" className="btn-next" onClick={onSkip} disabled={skipDisabled}>
        <SkipForward aria-hidden="true" />
        Suivant
      </button>
      <div className="now-live">
        <span>Direct — l’horloge est en pause.</span>
        {children}
      </div>
      <p className="now-off">
        L’antenne ne répond pas. Réessaie. Si ça continue, un admin regarde Réglages → Automate.
      </p>
      {banner || chips.length || health || toolbar ? (
        <div className="now-extra">
          {banner ? <p>{banner}</p> : null}
          {chips.map((chip) => {
            const badge = (
              <Badge
                key={chip.button ? undefined : chip.key}
                color={chip.color ?? "gray"}
                variant={chip.warn ? "solid" : "soft"}
              >
                <span>{chip.label}</span> {chip.value}
              </Badge>
            );
            if (!chip.button && !chip.onClick) return badge;
            return (
              <button key={chip.key} type="button" className="banner-direct" onClick={chip.onClick}>
                {badge}
              </button>
            );
          })}
          {toolbar}
          {health}
        </div>
      ) : null}
    </section>
  );
}
