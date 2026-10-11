import { useEffect, useRef } from "react";
import { useBrand } from "../lib/BrandContext";
import { useAccount } from "../api/AccountContext";
import {
  HARBOR_PHASE_LABEL,
  harborDetail,
  harborPhase,
  slotRule,
  weeklyHost,
} from "../api/harborPanel";
import type { AntenneState, EmissionsResponse, LiveSnapshot } from "../api/types";

function hostFromBase(base?: string): string {
  if (!base) return "";
  try {
    return new URL(base.includes("://") ? base : `http://${base}`).hostname;
  } catch {
    return "";
  }
}

export function LiveConnectPanel({
  live,
  antenne,
  emissions,
  offline,
  onClose,
}: {
  live: LiveSnapshot | null;
  antenne: AntenneState | null;
  emissions: EmissionsResponse | null;
  offline: boolean;
  onClose: () => void;
}) {
  const brand = useBrand();
  const { account, canBroadcast, isAdmin } = useAccount();
  const closeRef = useRef<HTMLButtonElement>(null);
  const phase = harborPhase({
    live,
    playoutSource: antenne?.playout.source,
    slotActive: antenne?.next_live_slot?.active,
    liveAbsent: antenne?.incidents.some((incident) => incident.kind === "live_absent"),
  });
  const show = live?.emission ?? emissions?.current ?? null;
  const host = weeklyHost(emissions?.emissions, show?.id);
  const harborHost = hostFromBase(brand.apps.harbor?.url) || "radio.lazbutton.xyz";
  const username = account?.username?.trim();
  const accountLine = isAdmin
    ? "Un admin peut se brancher même hors créneau."
    : canBroadcast
      ? `Ton identifiant encodeur : ${username || "ton compte"}.`
      : "Ce compte n’a pas le droit Stream : l’encodeur sera refusé.";

  useEffect(() => {
    closeRef.current?.focus();
  }, []);

  return (
    <section className="direct-sheet" id="direct-sheet" aria-labelledby="live-panel-title">
      <div className="direct-head">
        <h2 id="live-panel-title">Passer en direct</h2>
        <span className="direct-phase" data-phase={phase}>
          {HARBOR_PHASE_LABEL[phase]}
        </span>
      </div>
      <p>{harborDetail(phase, offline)}</p>
      <p>
        <strong>Créneau.</strong> {slotRule(host, show?.title)}
      </p>
      <p>{accountLine}</p>
      <dl>
        <dt>Type</dt>
        <dd>Icecast, BUTT ou Mixxx</dd>
        <dt>Adresse</dt>
        <dd>{harborHost}</dd>
        <dt>Port</dt>
        <dd>6800</dd>
        <dt>Mount</dt>
        <dd>/stream</dd>
        <dt>Compte</dt>
        <dd>L’identifiant du compte, avec le droit Stream. Mot de passe : celui du compte.</dd>
        <dt>Format</dt>
        <dd>MP3, 128 à 192 kbps</dd>
      </dl>
      <button ref={closeRef} className="direct-close" type="button" onClick={onClose}>
        Fermer
      </button>
    </section>
  );
}
