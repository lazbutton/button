import { Link } from "react-router-dom";
import { DAY_SHORT_FR } from "../../api/agendaView";
import { clockIdOf, cutLabel, lineTime, nextClock, secondsUntil, untilLabel } from "../../api/conducteurView";
import { emissionPillLabel } from "../../api/emissionMeta";
import { nextAnchoredItem } from "../../api/rundownLive";
import type { EmissionsResponse, LiveSnapshot, Rundown, RundownItem } from "../../api/types";

/** « à 18:00 · dans 6 h 25 » : l'heure, puis le temps d'ici là. */
function whenText(at: string, wall: Date): string {
  const { clock } = lineTime(at);
  const until = secondsUntil(at, wall);
  return [clock === "—" ? "" : `à ${clock}`, until == null ? "" : untilLabel(until)].filter(Boolean).join(" · ");
}

/** Le résumé du conducteur : l'heure type, la suivante, la prochaine coupure, l'émission. */
export function PlanSummary({
  rundown,
  upcoming,
  live,
  emissions,
  wall,
  canOpenClock,
}: {
  rundown: Rundown;
  upcoming: RundownItem[];
  live: LiveSnapshot | null;
  emissions: EmissionsResponse | null;
  wall: Date;
  /** Programmateur : l'heure type s'ouvre dans Programmation. */
  canOpenClock: boolean;
}) {
  const current = rundown.clock?.trim() || "";
  const clockId = canOpenClock ? clockIdOf(rundown.items, current) : null;
  const next = nextClock(upcoming, current);
  // Une émission de l'Agenda est ancrée elle aussi : ce n'est pas une coupure de l'heure type.
  const summaryAnchor = rundown.summary?.next_anchor;
  const cuts = rundown.items.filter((item) => item.kind !== "emission" && item.origin !== "agenda");
  const anchor =
    summaryAnchor?.at && summaryAnchor.kind !== "emission" ? summaryAnchor : nextAnchoredItem(cuts, wall);
  const cut = anchor ? cutLabel(anchor) : "";
  const show = live?.emission ?? emissions?.current ?? null;
  const emission = emissionPillLabel(show, emissions?.next ?? null, DAY_SHORT_FR);

  return (
    <dl className="cond-facts">
      <div className="cond-fact">
        <dt>Heure type</dt>
        <dd>
          {current ? (
            clockId != null ? (
              <Link className="cond-fact-main" to={`/programmation?clock=${clockId}`}>
                {current}
              </Link>
            ) : (
              <strong className="cond-fact-main">{current}</strong>
            )
          ) : (
            <strong className="cond-fact-main">Aucune</strong>
          )}
          <span className="cond-fact-sub">{current ? rundown.daypart || "" : "Rien n’est posé à cette heure."}</span>
        </dd>
      </div>
      {next ? (
        <div className="cond-fact">
          <dt>Ensuite</dt>
          <dd>
            <strong className="cond-fact-main">{next.name}</strong>
            <span className="cond-fact-sub">{whenText(next.at, wall)}</span>
          </dd>
        </div>
      ) : null}
      {anchor?.at && cut ? (
        <div className="cond-fact">
          <dt>Prochaine coupure</dt>
          <dd>
            <strong className="cond-fact-main">{cut}</strong>
            <span className="cond-fact-sub">{whenText(anchor.at, wall)}</span>
          </dd>
        </div>
      ) : null}
      {emission ? (
        <div className="cond-fact">
          <dt>{show ? "Émission en cours" : "Prochaine émission"}</dt>
          <dd>
            <strong className="cond-fact-main">{emission}</strong>
          </dd>
        </div>
      ) : null}
    </dl>
  );
}
