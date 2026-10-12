import { Popover } from "@radix-ui/themes";
import { ArrowRight, ChevronDown } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { formatDuration, incidentLabel, type PillarTone } from "../../api/antenneState";
import type { TopAir, TopHealth } from "../../api/topbar";
import type { AntenneState } from "../../api/types";

const HEALTH_WORD: Record<PillarTone, string> = {
  ok: "tout va bien",
  warn: "un point à surveiller",
  alert: "alerte",
  off: "état indisponible",
};

/** Libellé stable pour le lecteur d'écran : pas de compteur qui change chaque seconde. */
function spoken(air: TopAir): string {
  return air.label.replace(/\s*\d+\s*s$/, "");
}

export function AirStatus({
  air,
  health,
  antenne,
  isAdmin,
}: {
  air: TopAir;
  health: TopHealth;
  antenne: AntenneState | null;
  isAdmin: boolean;
}) {
  const [open, setOpen] = useState(false);
  const incidents = health.stale ? [] : antenne?.incidents ?? [];
  // Le point orange ne sert que si la pastille elle-même ne signale rien.
  const calm = air.tone === "on" || air.tone === "direct";
  const flag = health.open > 0 ? "count" : calm && health.tone === "warn" ? "dot" : null;
  const close = () => setOpen(false);

  return (
    <Popover.Root open={open} onOpenChange={setOpen}>
      <Popover.Trigger>
        <button
          type="button"
          className="tb-air"
          data-tone={air.tone}
          aria-label={`Antenne : ${air.label}${air.detail ? `, ${air.detail}` : ""}. Santé : ${HEALTH_WORD[health.tone]}${health.open ? `, ${health.open} incident${health.open > 1 ? "s" : ""} ouvert${health.open > 1 ? "s" : ""}` : ""}.`}
        >
          <span className="tb-air-dot" aria-hidden="true" />
          <span className="tb-air-label">{air.label}</span>
          {air.detail ? <span className="tb-air-detail">{air.detail}</span> : null}
          {flag === "count" ? (
            <span className="tb-air-count" aria-hidden="true">
              {health.open}
            </span>
          ) : flag === "dot" ? (
            <span className="tb-air-flag" aria-hidden="true" />
          ) : null}
          <ChevronDown className="tb-air-caret" size={14} strokeWidth={2} aria-hidden="true" />
        </button>
      </Popover.Trigger>
      <span className="ui-visually-hidden" role="status">
        {spoken(air)}
      </span>
      <Popover.Content className="tb-pop" align="start" sideOffset={6} size="1" maxWidth="22rem">
        <div className="tb-pop-head">
          <strong>État de l’antenne</strong>
          <span>
            {health.stale ? "État périmé" : antenne ? `Relevé à ${antenne.at.slice(11, 19)}` : ""}
          </span>
        </div>
        <ul className="tb-health" aria-label="Santé antenne">
          {health.pillars.map((pillar) => (
            <li key={pillar.key} data-tone={pillar.tone}>
              <span className="tb-health-dot" aria-hidden="true" />
              <span className="tb-health-k">{pillar.label}</span>
              <span className="tb-health-v" title={pillar.detail.join("\n")}>
                {pillar.value}
              </span>
            </li>
          ))}
        </ul>
        {incidents.length ? (
          <div className="tb-incidents">
            <p className="tb-pop-kicker">Incidents ouverts</p>
            <ul>
              {incidents.map((incident) => (
                <li key={`${incident.kind}-${incident.since_s}`}>
                  <strong>{incidentLabel(incident)}</strong>
                  <span>
                    {incident.detail ? `${incident.detail} · ` : ""}depuis {formatDuration(incident.since_s)}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
        <div className="tb-pop-foot">
          <Link to="/antenne" onClick={close}>
            Ouvrir l’antenne
            <ArrowRight size={14} aria-hidden="true" />
          </Link>
          {isAdmin ? (
            <Link to="/reglages?onglet=automate" onClick={close}>
              Diagnostic automate
              <ArrowRight size={14} aria-hidden="true" />
            </Link>
          ) : null}
        </div>
      </Popover.Content>
    </Popover.Root>
  );
}
