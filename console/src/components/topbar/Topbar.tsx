import { Tooltip } from "@radix-ui/themes";
import { UsersRound } from "lucide-react";
import type { ReactNode } from "react";
import { useAccount } from "../../api/AccountContext";
import { ANTENNE_STATE_JSON } from "../../api/antenneState";
import { audience, audienceLabel, topAir, topHealth } from "../../api/topbar";
import type { AntenneState } from "../../api/types";
import { useApiJson } from "../../api/useApiJson";
import { useMonitorState } from "../../lib/MonitorContext";
import { AccountMenu } from "./AccountMenu";
import { AirStatus } from "./AirStatus";
import { ListenControl } from "./ListenControl";
import { NowPlaying } from "./NowPlaying";
import { TopClock } from "./TopClock";

/**
 * Barre du haut, la même sur toutes les pages :
 * à gauche ce qui passe (état, titre), à droite les outils (casque, auditeurs, heure, compte).
 */
export function Topbar({ leading }: { leading?: ReactNode }) {
  const { isAdmin } = useAccount();
  const monitor = useMonitorState();
  const antenne = useApiJson<AntenneState>(ANTENNE_STATE_JSON, 5000);
  // Le moteur ne répond plus : son dernier état ne dit plus que tout va bien.
  const state = antenne.error || monitor.snapshotUnreachable ? null : antenne.data;
  const health = topHealth(state, monitor.snapshot, new Date());
  const fresh = health.stale ? null : state;
  const air = topAir({
    live: monitor.snapshot,
    antenne: fresh,
    loading: monitor.snapshotLoading,
    unreachable: monitor.snapshotUnreachable,
  });
  const listeners = audience(fresh);

  return (
    <header className="app-topbar">
      {leading}
      <div className="tb-onair">
        <AirStatus air={air} health={health} antenne={antenne.data} isAdmin={isAdmin} />
        <NowPlaying live={monitor.snapshot} />
      </div>
      <div className="tb-tools">
        <ListenControl />
        {listeners != null ? (
          <Tooltip content="Auditeurs du flux public en ce moment">
            <span className="tb-stat">
              <UsersRound size={15} strokeWidth={1.9} aria-hidden="true" />
              <span aria-hidden="true">{listeners}</span>
              <span className="ui-visually-hidden">{audienceLabel(listeners)}</span>
            </span>
          </Tooltip>
        ) : null}
        <TopClock />
        <AccountMenu />
      </div>
    </header>
  );
}
