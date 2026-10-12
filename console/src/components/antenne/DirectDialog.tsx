import { Dialog } from "@radix-ui/themes";
import { Check, Copy, X } from "lucide-react";
import { useState, type RefObject } from "react";
import { useAccount } from "../../api/AccountContext";
import { HARBOR_PHASE_LABEL, harborDetail, harborPhase, slotRule, weeklyHost } from "../../api/harborPanel";
import type { AntenneState, EmissionsResponse, LiveSnapshot } from "../../api/types";
import { useBrand } from "../../lib/BrandContext";

function hostFromBase(base?: string): string {
  if (!base) return "";
  try {
    return new URL(base.includes("://") ? base : `http://${base}`).hostname;
  } catch {
    return "";
  }
}

function CopyValue({ label, value }: { label: string; value: string }) {
  const [done, setDone] = useState(false);
  return (
    <button
      type="button"
      className="ant-copy"
      aria-label={`Copier ${label} : ${value}`}
      title="Copier"
      onClick={() => {
        void navigator.clipboard
          ?.writeText(value)
          .then(() => {
            setDone(true);
            window.setTimeout(() => setDone(false), 1400);
          })
          .catch(() => undefined);
      }}
    >
      <code>{value}</code>
      {done ? <Check size={14} aria-hidden="true" /> : <Copy size={14} aria-hidden="true" />}
    </button>
  );
}

/** Se brancher en direct : état de l'encodeur, règle du créneau, réglages à copier dans BUTT ou Mixxx. */
export function DirectDialog({
  open,
  onOpenChange,
  live,
  antenne,
  emissions,
  offline,
  returnFocus,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Le bouton qui a ouvert la boîte : il reprend le focus à la fermeture. */
  returnFocus: RefObject<HTMLButtonElement | null>;
  live: LiveSnapshot | null;
  antenne: AntenneState | null;
  emissions: EmissionsResponse | null;
  offline: boolean;
}) {
  const brand = useBrand();
  const { account, canBroadcast, isAdmin } = useAccount();
  const phase = harborPhase({
    live,
    playoutSource: antenne?.playout.source,
    slotActive: antenne?.next_live_slot?.active,
    liveAbsent: antenne?.incidents.some((incident) => incident.kind === "live_absent"),
  });
  const show = live?.emission ?? emissions?.current ?? null;
  const host = weeklyHost(emissions?.emissions, show?.id);
  const address = hostFromBase(brand.apps.harbor?.url) || "radio.lazbutton.xyz";
  const username = account?.username?.trim();
  const accountLine = isAdmin
    ? "Un admin peut se brancher même hors créneau."
    : canBroadcast
      ? `Identifiant : ${username || "celui de ton compte"}. Mot de passe : celui du compte.`
      : "Ce compte n’a pas le droit Stream : l’encodeur sera refusé. Demande-le à un admin.";

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Content
        className="ant-direct"
        maxWidth="32rem"
        aria-describedby="ant-direct-state"
        onCloseAutoFocus={(event) => {
          event.preventDefault();
          returnFocus.current?.focus();
        }}
      >
        <div className="ant-direct-head">
          <Dialog.Title className="ant-direct-title">Passer en direct</Dialog.Title>
          <span className="ant-direct-phase" data-phase={phase}>
            {HARBOR_PHASE_LABEL[phase]}
          </span>
          <Dialog.Close>
            <button type="button" className="ant-icon-btn" aria-label="Fermer">
              <X size={16} aria-hidden="true" />
            </button>
          </Dialog.Close>
        </div>
        <p id="ant-direct-state" className="ant-direct-lead">
          {harborDetail(phase, offline)}
        </p>
        <p className="ant-direct-rule">
          {slotRule(host, show?.title)} {accountLine}
        </p>
        <dl className="ant-direct-settings">
          <dt>Type</dt>
          <dd>Icecast (BUTT, Mixxx…)</dd>
          <dt>Adresse</dt>
          <dd>
            <CopyValue label="l’adresse" value={address} />
          </dd>
          <dt>Port</dt>
          <dd>
            <CopyValue label="le port" value="6800" />
          </dd>
          <dt>Mount</dt>
          <dd>
            <CopyValue label="le mount" value="/stream" />
          </dd>
          <dt>Format</dt>
          <dd>MP3, 128 à 192 kbps</dd>
        </dl>
        <p className="ant-direct-foot">
          Quand l’encodeur se branche, le direct prend l’antenne et l’horloge se met en pause. Le couper rend la grille.
        </p>
      </Dialog.Content>
    </Dialog.Root>
  );
}
