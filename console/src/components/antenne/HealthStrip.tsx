import { Popover, Text } from "@radix-ui/themes";
import type { Pillar, PillarTone } from "../../api/antenneState";

const TONE_LABEL: Record<PillarTone, string> = {
  ok: "OK",
  warn: "À surveiller",
  alert: "Alerte",
  off: "Indisponible",
};

export function HealthStrip({
  pillars,
  stale,
  updatedAt,
}: {
  pillars: Pillar[];
  /** L'état n'a pas été rafraîchi depuis trop longtemps (ou jamais). */
  stale: boolean;
  updatedAt: string | null;
}) {
  return (
    <div className={`health-strip${stale ? " is-stale" : ""}`} aria-label="Santé antenne">
      {pillars.map((pillar) => (
        <Popover.Root key={pillar.key}>
          <Popover.Trigger>
            <button
              type="button"
              className={`health-pill tone-${pillar.tone}`}
              aria-label={`${pillar.label} : ${pillar.value} (${TONE_LABEL[pillar.tone]})`}
            >
              {/* L'espace sépare les mots du texte affiché, que le nom reprend. */}
              <span className="health-pill-dot" aria-hidden="true" />
              <span className="health-pill-k">{pillar.label}</span>{" "}
              <span className="health-pill-v">{pillar.value}</span>
            </button>
          </Popover.Trigger>
          <Popover.Content size="1" className="health-pop" align="start">
            <Text as="p" size="2" weight="bold" className="health-pop-title">
              {pillar.label} · {TONE_LABEL[pillar.tone]}
            </Text>
            <ul className="health-pop-list">
              {pillar.detail.map((line, index) => (
                <li key={index}>
                  <Text size="1">{line}</Text>
                </li>
              ))}
            </ul>
          </Popover.Content>
        </Popover.Root>
      ))}
      <span className="health-strip-at">
        {stale ? "état antenne périmé" : updatedAt ? `à ${updatedAt}` : ""}
      </span>
    </div>
  );
}
