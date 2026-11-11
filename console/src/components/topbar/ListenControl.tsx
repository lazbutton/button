import { DropdownMenu, Popover, Tooltip } from "@radix-ui/themes";
import { ArrowRight, ChevronDown, HeadphoneOff, Headphones, TriangleAlert } from "lucide-react";
import { useId, useState } from "react";
import { Link } from "react-router-dom";
import { useAccount } from "../../api/AccountContext";
import { listenHint } from "../../api/topbar";
import { useMonitorState } from "../../lib/MonitorContext";
import type { MonitorSourceId } from "../../lib/monitorSource";
import { VuMeter } from "../VuMeter";

function shortStream(url: string): string {
  try {
    const parsed = new URL(url);
    return `${parsed.hostname}${parsed.pathname}`;
  } catch {
    return url;
  }
}

/**
 * Sans flux public réglé, le casque n'a rien à écouter : son bouton ouvre une bulle qui
 * dit quoi régler, et à l'admin où (ADR 0007).
 */
function ListenUnset() {
  const { isAdmin } = useAccount();
  const [open, setOpen] = useState(false);
  const titleId = useId();
  return (
    <div className="tb-listen" data-on="false" data-error="false" data-unset="true">
      <Popover.Root open={open} onOpenChange={setOpen}>
        <Popover.Trigger>
          <button type="button" className="tb-listen-toggle" aria-label="Écouter au casque : aucun flux réglé">
            <HeadphoneOff size={16} strokeWidth={1.9} aria-hidden="true" />
            <span className="tb-listen-label">Écouter</span>
          </button>
        </Popover.Trigger>
        <Popover.Content className="tb-pop" align="end" sideOffset={6} size="1" maxWidth="20rem" aria-labelledby={titleId}>
          <div className="tb-pop-head">
            <strong id={titleId}>Aucun flux à écouter</strong>
          </div>
          <p className="tb-pop-text">
            L’adresse du flux public n’est pas réglée : le casque n’a rien à écouter.
            {isAdmin ? "" : " Un admin la règle dans Réglages → Station."}
          </p>
          {isAdmin ? (
            <div className="tb-pop-foot">
              <Link to="/reglages?onglet=station" onClick={() => setOpen(false)}>
                Régler le flux public
                <ArrowRight size={14} aria-hidden="true" />
              </Link>
            </div>
          ) : null}
        </Popover.Content>
      </Popover.Root>
    </div>
  );
}

/** Casque de contrôle : écouter, niveau, et pour l'admin la source (antenne ou fichiers du conducteur). */
export function ListenControl() {
  const monitor = useMonitorState();
  if (!monitor.sources.length) return <ListenUnset />;
  return <ListenSources />;
}

function ListenSources() {
  const monitor = useMonitorState();
  const source = monitor.sources.find((row) => row.id === monitor.sourceId) ?? monitor.sources[0];
  const listening = !monitor.muted;
  const waiting =
    monitor.listenKind === "files" && monitor.now.startedAt != null && monitor.now.startedAt > Date.now();
  const hint = listenHint(
    {
      muted: monitor.muted,
      kind: monitor.listenKind,
      fileMissing: monitor.fileMissing,
      fileLoading: monitor.fileLoading,
      streamDown: monitor.streamDown,
      startsInS: waiting ? monitor.remaining : null,
      lagMs: monitor.lagMs,
    },
    source?.label ?? "Antenne publique",
  );
  // Le flux se connecte, muet, dès l'ouverture : son échec ne se montre qu'à l'écoute.
  const broken = monitor.fileMissing || (listening && monitor.streamDown);
  const Icon = broken ? TriangleAlert : Headphones;

  return (
    <div
      className="tb-listen"
      data-on={listening ? "true" : "false"}
      data-error={broken ? "true" : "false"}
    >
      <Tooltip content={hint}>
        <button
          type="button"
          className="tb-listen-toggle"
          aria-pressed={listening}
          aria-label={listening ? `Arrêter l’écoute. ${hint}` : hint}
          onClick={monitor.toggleMute}
        >
          <Icon size={16} strokeWidth={1.9} aria-hidden="true" />
          <span className="tb-listen-label">{listening ? "Arrêter" : "Écouter"}</span>
        </button>
      </Tooltip>
      {listening ? <VuMeter analyserL={monitor.analyserL} analyserR={monitor.analyserR} live={monitor.live} /> : null}
      {monitor.canChooseSource && source ? (
        <DropdownMenu.Root modal={false}>
          <DropdownMenu.Trigger>
            <button
              type="button"
              className="tb-listen-source"
              data-source={source.id}
              aria-label={`Source du casque : ${source.label}. Changer.`}
            >
              <span className="tb-listen-source-label">{source.chip}</span>
              <ChevronDown size={14} strokeWidth={2} aria-hidden="true" />
            </button>
          </DropdownMenu.Trigger>
          <DropdownMenu.Content variant="soft" align="end" sideOffset={6} className="tb-menu tb-menu--source">
            <DropdownMenu.Label>Source du casque</DropdownMenu.Label>
            <DropdownMenu.RadioGroup
              value={monitor.sourceId}
              onValueChange={(value) => monitor.setSourceId(value as MonitorSourceId)}
            >
              {monitor.sources.map((row) => (
                <DropdownMenu.RadioItem key={row.id} value={row.id} className="tb-menu-rich">
                  <span className="tb-menu-copy">
                    <span>{row.label}</span>
                    <small>{row.id === "public" ? `${row.hint} ${shortStream(row.stream)}` : row.hint}</small>
                  </span>
                </DropdownMenu.RadioItem>
              ))}
            </DropdownMenu.RadioGroup>
            <DropdownMenu.Separator />
            <p className="tb-menu-note">Seul ton casque change. Les auditeurs restent sur l’antenne.</p>
          </DropdownMenu.Content>
        </DropdownMenu.Root>
      ) : null}
    </div>
  );
}
