import { useCallback, useMemo, useState } from "react";
import { Badge, Text } from "@radix-ui/themes";
import { Radio } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { ConducteurBoard } from "../components/ConducteurBoard";
import { ProtoToast, useProtoToast } from "../components/ProtoToast";
import { RepairClockCartDialog } from "../components/RepairClockCartDialog";
import { formatHhMmSs, formatMmSs } from "../lib/parisClock";
import { useAntennaClock } from "../lib/liveClock";
import { useAccount } from "../api/AccountContext";
import { roleAtLeast } from "../api/roles";
import { apiDeleteJson, ApiForbiddenError, ApiRequestError } from "../api/client";
import { SessionGate } from "../api/SessionGate";
import { emissionPillLabel } from "../api/emissionMeta";
import { CONDUCTEUR_JSON, itemNamedLikeLive, nextAnchoredItem, partitionRundown, rundownCopy } from "../api/rundownLive";
import type {
  CartsResponse,
  ClocksResponse,
  EmissionsResponse,
  LiveSnapshot,
  Rundown,
  RundownItem,
} from "../api/types";
import { useApiJson } from "../api/useApiJson";
import { PageHeader } from "../ui/PageHeader";
import { Panel } from "../ui/Panel";
import "../styles/pages/conducteur.css";

const POLL_MS = 3_000;

function horizonLabel(minutes: number): string {
  if (minutes >= 60) return `${Math.round(minutes / 60)} h`;
  return `${minutes} min`;
}

function liveLine(live: LiveSnapshot | null, loading: boolean): string {
  if (loading && !live) return "Lecture du live…";
  if (!live || live.status === "offline") return "Pas de playout";
  const artist = live.artist?.trim();
  const title = live.title?.trim();
  if (artist && title) return `${artist} — ${title}`;
  return title || artist || "À l’antenne";
}

function liveState(live: LiveSnapshot | null): { color: "green" | "amber" | "gray"; label: string } {
  if (!live || live.status === "offline") return { color: "gray", label: "Offline" };
  if (live.status === "simulating") return { color: "amber", label: "Démo" };
  return { color: "green", label: live.source?.toUpperCase() || "ON AIR" };
}

export function ConducteurPage() {
  const live = useApiJson<LiveSnapshot>("/live.json", 2000);
  const clock = useAntennaClock(live.data);
  const { data, setData, error, loading, reload } = useApiJson<Rundown>(CONDUCTEUR_JSON, POLL_MS);
  const clocksRes = useApiJson<ClocksResponse>("/autodj/clocks.json");
  const cartsRes = useApiJson<CartsResponse>("/carts.json");
  const emissionsRes = useApiJson<EmissionsResponse>("/antenne/emissions.json", POLL_MS);
  const navigate = useNavigate();
  const { message, show } = useProtoToast();
  const [repairItem, setRepairItem] = useState<RundownItem | null>(null);
  const { role } = useAccount();
  const canEdit = roleAtLeast(role, "programmateur");

  const fail = (caught: unknown, fallback: string) => {
    if (caught instanceof ApiForbiddenError) show("Il faut le rôle Programmateur pour modifier le conducteur.");
    else if (caught instanceof ApiRequestError) show(caught.message);
    else show(fallback);
  };

  const removeItem = useCallback(
    async (item: RundownItem) => {
      if (!canEdit || !item.id) return;
      try {
        const payload = await apiDeleteJson<Rundown>(
          `/autodj/conducteur/items/${encodeURIComponent(item.id)}.json`,
        );
        setData(payload);
        show("Retiré du conducteur");
      } catch (caught) {
        fail(caught, "Retrait impossible.");
      }
    },
    [canEdit, setData, show],
  );

  const snapshot = live.data;
  const currentShow = snapshot?.emission ?? emissionsRes.data?.current ?? null;
  const nextShow = emissionsRes.data?.next ?? null;
  const emissionPill = emissionPillLabel(currentShow, nextShow, [
    "Lun",
    "Mar",
    "Mer",
    "Jeu",
    "Ven",
    "Sam",
    "Dim",
  ]);
  const onAir = liveState(snapshot);
  const nextAnchor = useMemo(() => {
    if (!data) return null;
    if (data.summary?.next_anchor?.at) return data.summary.next_anchor;
    const found = nextAnchoredItem(data.items, new Date());
    if (!found) return null;
    return {
      at: found.at,
      minute: found.minute,
      kind: found.kind,
      resource: found.resource,
      sync: found.sync,
    };
  }, [data]);

  const parts = data ? partitionRundown(data.items, clock.wall, snapshot) : null;
  const onAirItem = parts?.onAir ?? null;
  const matchesAir = Boolean(onAirItem && itemNamedLikeLive(onAirItem, snapshot ?? null));
  const onAirCopy = matchesAir && onAirItem ? rundownCopy(onAirItem) : null;
  const stripTitle = onAirCopy
    ? onAirCopy.artist
      ? `${onAirCopy.artist} — ${onAirCopy.title}`
      : onAirCopy.title
    : liveLine(snapshot, live.loading);
  const remaining =
    snapshot && snapshot.status !== "offline" ? formatMmSs(clock.remainingSec) : null;
  const nextAnchorRemainSec = nextAnchor?.at
    ? Math.max(0, Math.round((Date.parse(nextAnchor.at) - Date.now()) / 1000))
    : null;
  const lastAt = data?.items.at(-1)?.at;
  const lastClock = lastAt
    ? (lastAt.includes("T") ? lastAt.split("T")[1] : lastAt).slice(0, 5)
    : null;

  return (
    <>
    <div className="ui-page ui-page--fill conducteur-page">
      <PageHeader
        title="Conducteur"
        status={
          <Badge color={onAir.color} variant="soft">
            <Radio size={12} aria-hidden="true" />
            {onAir.label}
          </Badge>
        }
      />

      <SessionGate
        loading={loading}
        error={error}
        ready={data != null}
        onRetry={() => void reload()}
      >
        {data ? (
          <main className="conducteur-workspace">
            <section className="conducteur-strip" aria-label="À l’antenne">
              <div className="conducteur-strip-now">
                <Text as="p" size="1" className="conducteur-strip-label">
                  À l’antenne
                </Text>
                <Text as="p" size="3" weight="bold" className="conducteur-strip-title">
                  {stripTitle}
                </Text>
              </div>
              {remaining ? (
                <Text as="p" size="5" weight="bold" className="conducteur-strip-remain">
                  −{remaining}
                </Text>
              ) : null}
              <dl className="conducteur-strip-facts">
                <div>
                  <dt>Horloge</dt>
                  <dd>
                    {data.clock || "Aucune"}
                    {data.daypart ? ` · ${data.daypart}` : ""}
                  </dd>
                </div>
                {nextAnchor ? (
                  <div>
                    <dt>Ancre</dt>
                    <dd>
                      {nextAnchor.minute != null
                        ? `:${String(nextAnchor.minute).padStart(2, "0")}`
                        : nextAnchor.kind || "ancre"}
                      {nextAnchor.sync ? ` ${nextAnchor.sync}` : ""}
                      {nextAnchorRemainSec != null
                        ? ` · ${formatHhMmSs(nextAnchorRemainSec)}`
                        : ""}
                    </dd>
                  </div>
                ) : null}
                {snapshot?.source ? (
                  <div>
                    <dt>File</dt>
                    <dd>{snapshot.source}</dd>
                  </div>
                ) : null}
                {emissionPill ? (
                  <div>
                    <dt>Émission</dt>
                    <dd>
                      <span className="conducteur-emission-pill">{emissionPill}</span>
                    </dd>
                  </div>
                ) : null}
                <div>
                  <dt>Horizon</dt>
                  <dd>
                    {lastClock ? `→ ${lastClock}` : horizonLabel(data.horizon_min)}
                    {lastClock ? ` · ${horizonLabel(data.horizon_min)}` : ""}
                  </dd>
                </div>
              </dl>
            </section>

            <Panel padded={false} className="conducteur-rundown-panel">
              <ConducteurBoard
                rundown={data}
                live={snapshot}
                onRepair={canEdit ? setRepairItem : undefined}
                onRemove={canEdit ? removeItem : undefined}
              />
            </Panel>
          </main>
        ) : null}
      </SessionGate>
    </div>
    <RepairClockCartDialog
      open={repairItem != null}
      onOpenChange={(open) => {
        if (!open) setRepairItem(null);
      }}
      clocks={clocksRes.data?.clocks ?? []}
      carts={cartsRes.data?.carts ?? []}
      missingTitle={repairItem?.cart || repairItem?.resource || ""}
      clockId={repairItem?.clock_id}
      clockName={repairItem?.clock}
      positionId={repairItem?.position_id}
      kind={repairItem?.kind}
      onRepaired={async () => {
        await clocksRes.reload();
        await reload();
        show("Case réparée");
      }}
      onOpenCart={(cartId) => navigate(`/sons?id=${cartId}`)}
      onError={show}
    />
    <ProtoToast message={message} />
    </>
  );
}
