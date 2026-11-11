import { Dialog } from "@radix-ui/themes";
import { ArrowRight, X } from "lucide-react";
import { useEffect, useState, type RefObject } from "react";
import { Link } from "react-router-dom";
import { useAccount } from "../../api/AccountContext";
import { ApiAuthError, ApiRequestError, ApiUnavailableError, apiGet } from "../../api/client";
import { HARBOR_PHASE_LABEL, harborDetail, harborPhase, slotRule, weeklyHost } from "../../api/harborPanel";
import { harborAddress } from "../../api/station";
import type { AntenneState, EmissionsResponse, LiveSnapshot, StationHarbor } from "../../api/types";
import { CopyValue } from "./CopyValue";
import { StreamToken } from "./StreamToken";

type HarborRead =
  | { status: "loading" }
  | { status: "ready"; harbor: StationHarbor }
  | { status: "outdated" }
  | { status: "failed"; message: string };

function harborFailure(caught: unknown): string {
  if (caught instanceof ApiAuthError) return "Session expirée : reconnecte-toi.";
  if (caught instanceof ApiUnavailableError) return "L’automate ne répond pas. Réessaie dans un instant.";
  if (caught instanceof ApiRequestError) return caught.message;
  return "L’adresse du direct ne répond pas.";
}

/**
 * L'adresse du harbor, relue à chaque ouverture du panneau : `GET /station/harbor.json`,
 * ouvert à tout compte. Un moteur plus ancien n'a pas la route : il répond 404.
 */
function useHarbor(open: boolean) {
  const [read, setRead] = useState<HarborRead>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    // Une adresse déjà lue reste à l'écran pendant la relecture.
    setRead((previous) => (previous.status === "ready" ? previous : { status: "loading" }));
    apiGet<StationHarbor>("/station/harbor.json").then(
      (harbor) => {
        if (!cancelled) setRead({ status: "ready", harbor });
      },
      (caught: unknown) => {
        if (cancelled) return;
        const outdated = caught instanceof ApiRequestError && caught.status === 404;
        setRead(outdated ? { status: "outdated" } : { status: "failed", message: harborFailure(caught) });
      },
    );
    return () => {
      cancelled = true;
    };
  }, [open, attempt]);
  return { read, retry: () => setAttempt((count) => count + 1) };
}

/**
 * L'hôte, le port et le mount, à copier dans l'encodeur. Sans hôte réglé, ils se cachent,
 * et la ligne dit qui le règle, et où : pas d'adresse en repli (ADR 0007).
 */
function HarborRows({
  read,
  retry,
  isAdmin,
  close,
}: {
  read: HarborRead;
  retry: () => void;
  isAdmin: boolean;
  close: () => void;
}) {
  const address = read.status === "ready" ? harborAddress(read.harbor) : null;
  if (address) {
    return (
      <>
        <dt>Adresse</dt>
        <dd>
          <CopyValue label="l’adresse" value={address.host} />
        </dd>
        <dt>Port</dt>
        <dd>
          <CopyValue label="le port" value={address.port} />
        </dd>
        <dt>Mount</dt>
        <dd>
          <CopyValue label="le mount" value={address.mount} />
        </dd>
      </>
    );
  }
  let note;
  if (read.status === "loading") {
    note = "Lecture de l’adresse du direct…";
  } else if (read.status === "outdated") {
    note = "Mets à jour le moteur pour lire l’adresse du direct.";
  } else if (read.status === "failed") {
    note = (
      <>
        <span role="alert">{read.message}</span>
        <button type="button" className="ant-link" onClick={retry}>
          Réessayer
        </button>
      </>
    );
  } else if (isAdmin) {
    note = (
      <>
        <span>L’adresse du direct n’est pas encore réglée.</span>
        <Link to="/reglages?onglet=station" className="ant-link" onClick={close}>
          La régler
          <ArrowRight size={14} aria-hidden="true" />
        </Link>
      </>
    );
  } else {
    note = "L’adresse du direct n’est pas encore réglée. Un admin la règle dans Réglages → Station.";
  }
  return (
    <>
      <dt>Adresse</dt>
      <dd className="ant-direct-note">{note}</dd>
    </>
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
  const { account, canBroadcast, isAdmin } = useAccount();
  const harbor = useHarbor(open);
  const phase = harborPhase({
    live,
    playoutSource: antenne?.playout.source,
    slotActive: antenne?.next_live_slot?.active,
    liveAbsent: antenne?.incidents.some((incident) => incident.kind === "live_absent"),
  });
  const show = live?.emission ?? emissions?.current ?? null;
  const host = weeklyHost(emissions?.emissions, show?.id);
  const username = account?.username?.trim();
  const mayStream = isAdmin || canBroadcast;
  const accountLine = isAdmin
    ? "Un admin peut se brancher même hors créneau."
    : canBroadcast
      ? ""
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
          <HarborRows read={harbor.read} retry={harbor.retry} isAdmin={isAdmin} close={() => onOpenChange(false)} />
          {mayStream ? (
            <>
              <dt>Identifiant</dt>
              <dd>{username ? <CopyValue label="l’identifiant" value={username} /> : "Celui de ton compte"}</dd>
              <dt>Mot de passe</dt>
              <dd>
                <StreamToken owner="me" />
              </dd>
            </>
          ) : null}
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
