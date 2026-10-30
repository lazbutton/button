import { useCallback, useEffect, useMemo, useRef, useState, type Dispatch, type SetStateAction } from "react";
import { TriangleAlert } from "lucide-react";
import { Link } from "react-router-dom";
import { DirectDialog } from "../components/antenne/DirectDialog";
import { LibraryPanel } from "../components/antenne/LibraryPanel";
import { OnAirCard, type AirState } from "../components/antenne/OnAirCard";
import { QueuePanel } from "../components/antenne/QueuePanel";
import { ProtoToast, useProtoToast } from "../components/ProtoToast";
import { useAntennaClock } from "../lib/liveClock";
import { anchorHint, deskAlert, ownsSpace, SKIP_GUARD_MS, spaceSkips } from "../api/antenneDesk";
import { airBanner, ANTENNE_STATE_JSON } from "../api/antenneState";
import {
  ApiAuthError,
  ApiForbiddenError,
  ApiRequestError,
  ApiUnavailableError,
  apiDelete,
  apiDeleteJson,
  apiPostJson,
  apiPut,
} from "../api/client";
import { deskKindFromHit, labelsFromHit, type LibraryHit } from "../api/library";
import { useAccount } from "../api/AccountContext";
import { harborIsLive } from "../api/emissionMeta";
import { stopDiffusion } from "../api/agenda";
import { timeLabel } from "../api/agendaView";
import { glanceNowItem } from "../api/liveMap";
import { airSourceLabel } from "../api/topbar";
import { SessionGate } from "../api/SessionGate";
import {
  CONDUCTEUR_JSON,
  isDeskPin,
  itemNamedLikeLive,
  nextAnchoredItem,
  partitionRundown,
  rundownCopy,
} from "../api/rundownLive";
import type {
  AntenneState,
  EmissionsResponse,
  LiveSnapshot,
  Rundown,
  RundownItem,
} from "../api/types";
import { useApiJson } from "../api/useApiJson";
import "../styles/pages/antenne.css";

type DeskMutation = Rundown & { desk_item?: RundownItem };

export function AntennePage() {
  const live = useApiJson<LiveSnapshot>("/live.json", 1000);
  const rundown = useApiJson<Rundown>(CONDUCTEUR_JSON, 3000);
  const emissions = useApiJson<EmissionsResponse>("/antenne/emissions.json", 3000);
  const antenne = useApiJson<AntenneState>(ANTENNE_STATE_JSON, 5000);
  const loading = live.loading;
  const error = live.error ?? rundown.error;

  const retry = () => {
    void live.reload();
    void rundown.reload();
    void emissions.reload();
    void antenne.reload();
  };

  return (
    <SessionGate loading={loading} error={error} ready={live.data != null} onRetry={retry}>
      <AntenneDesk
        live={live.data}
        rundown={rundown.data}
        rundownUnreadable={rundown.error === "down"}
        emissions={emissions.data}
        antenne={antenne.data}
        setRundown={rundown.setData}
        onLiveReload={() => {
          void live.reload();
          void rundown.reload();
          void emissions.reload();
          void antenne.reload();
        }}
      />
    </SessionGate>
  );
}

function hitPayload(hit: LibraryHit, extra: Record<string, unknown> = {}) {
  const labels = labelsFromHit(hit);
  return {
    path: hit.path,
    title: labels.title,
    artist: labels.artist,
    kind: deskKindFromHit(hit),
    duration: hit.duration || 0,
    ...extra,
  };
}

function itemToHit(item: RundownItem): LibraryHit | null {
  if (!item.path) return null;
  const copy = rundownCopy(item);
  return {
    id: item.id || item.path,
    path: item.path,
    title: copy.title,
    artist: copy.artist || "",
    kind: item.kind,
    duration: item.duration || 0,
  };
}

function keyTarget(target: EventTarget | null) {
  if (!(target instanceof HTMLElement) || target === document.body) return null;
  return { tag: target.tagName, role: target.getAttribute("role"), editable: target.isContentEditable };
}

function AntenneDesk({
  live,
  rundown,
  rundownUnreadable,
  emissions,
  antenne,
  setRundown,
  onLiveReload,
}: {
  live: LiveSnapshot | null;
  rundown: Rundown | null;
  /** La dernière lecture de la file a échoué. */
  rundownUnreadable: boolean;
  emissions: EmissionsResponse | null;
  antenne: AntenneState | null;
  setRundown: Dispatch<SetStateAction<Rundown | null>>;
  onLiveReload: () => void;
}) {
  const { message, show, dismiss } = useProtoToast();
  const snapshot: LiveSnapshot = live ?? { status: "offline" };
  const clock = useAntennaClock(snapshot);
  const wall = clock.wall;
  const parts = rundown ? partitionRundown(rundown.items, wall, live) : null;
  const liveMatches = Boolean(parts?.onAir && itemNamedLikeLive(parts.onAir, snapshot));
  const glance = glanceNowItem(liveMatches ? parts?.onAir ?? null : null, snapshot);
  const harbor = harborIsLive(snapshot);
  const elapsedSec = clock.elapsedSec;
  const durationSec = clock.durationSec;
  const remainingSec = clock.remainingSec;
  const offline = snapshot.status === "offline";
  const currentShow = snapshot.emission ?? emissions?.current ?? null;
  // Sans métadonnées, l'encodeur du direct ne dit que « Direct » : le nom de l'émission parle mieux.
  const now =
    harbor && glance && glance.title === "Direct" && currentShow?.title
      ? { ...glance, title: currentShow.title }
      : glance;
  const source = airSourceLabel(snapshot);
  const [showTitle, setShowTitle] = useState("");
  const [showArtist, setShowArtist] = useState("");
  const [naming, setNaming] = useState(false);
  const [renameOpen, setRenameOpen] = useState(false);
  const [directOpen, setDirectOpen] = useState(false);
  const lastSkipRef = useRef(0);
  const directButtonRef = useRef<HTMLButtonElement>(null);
  const renameTitleRef = useRef<HTMLInputElement>(null);
  const undoRef = useRef<(() => Promise<void>) | null>(null);

  const fail = useCallback(
    (caught: unknown, fallback: string, forbidden = "Il faut le droit antenne. Demande à un admin si tu dois pouvoir le faire.") => {
      if (caught instanceof ApiAuthError) show("Session expirée. Reconnecte-toi.");
      else if (caught instanceof ApiForbiddenError) show(forbidden);
      else if (caught instanceof ApiRequestError) show(caught.message);
      else if (caught instanceof ApiUnavailableError) show("L’automate ne répond pas. Réessaie dans un instant.");
      else show(fallback);
    },
    [show],
  );

  const datedSet =
    currentShow && currentShow.scope === "dated" && currentShow.kind === "set" && currentShow.state === "on_air"
      ? currentShow
      : null;
  const { account, isAdmin } = useAccount();
  const canStopDated = Boolean(account?.permissions.live || account?.permissions.admin);
  const [stopArmed, setStopArmed] = useState(false);
  const [stopping, setStopping] = useState(false);

  const stopDated = async () => {
    if (!datedSet) return;
    if (!stopArmed) {
      setStopArmed(true);
      return;
    }
    setStopping(true);
    try {
      await stopDiffusion(datedSet.id);
      show("Arrêt demandé : la grille reprend dans quelques secondes.");
      onLiveReload();
    } catch (caught) {
      fail(caught, "Arrêt impossible. Réessaie.");
    } finally {
      setStopping(false);
      setStopArmed(false);
    }
  };
  const applyRundown = (payload: Rundown) => {
    setRundown(payload);
  };

  const skipEngine = useCallback(async () => {
    if (harbor) return;
    // Un double-clic ou deux Espace rapprochés ne passent qu'un titre.
    const at = Date.now();
    if (at - lastSkipRef.current < SKIP_GUARD_MS) return;
    lastSkipRef.current = at;
    try {
      await apiDelete("/live.json");
      onLiveReload();
    } catch (caught) {
      fail(caught, "Impossible de passer. Réessaie.");
    }
  }, [fail, harbor, onLiveReload]);

  const nameLive = async () => {
    setNaming(true);
    try {
      await apiPostJson("/antenne/emissions.json", {
        scope: "session",
        title: showTitle.trim(),
        artist: showArtist.trim(),
      });
      setShowTitle("");
      setShowArtist("");
      show(currentShow ? "Live renommé." : "Live nommé.");
      setRenameOpen(false);
      onLiveReload();
    } catch (caught) {
      fail(caught, "Impossible de nommer ce live. Réessaie.");
    } finally {
      setNaming(false);
    }
  };

  const insertHit = useCallback(
    async (hit: LibraryHit, beforeId: string | null = null) => {
      try {
        const payload = await apiPostJson<DeskMutation>(
          "/autodj/conducteur/items.json",
          hitPayload(hit, beforeId ? { before_id: beforeId } : {}),
        );
        applyRundown(payload);
        show(beforeId ? "Placé dans la file." : "Mis à la suite.");
      } catch (caught) {
        fail(caught, "Insertion impossible. Réessaie.");
      }
    },
    [fail, setRundown, show],
  );

  const fireNow = useCallback(
    async (hit: LibraryHit) => {
      if (harbor) {
        show("Direct à l’antenne.");
        return;
      }
      try {
        const payload = await apiPostJson<Rundown>("/autodj/conducteur/now.json", hitPayload(hit));
        applyRundown(payload);
        show(
          snapshot.status === "simulating"
            ? "Envoyé (démo horloge — pas de Liquidsoap)."
            : "À l’antenne — coupe.",
        );
        onLiveReload();
      } catch (caught) {
        fail(caught, "Impossible de mettre à l’antenne. Réessaie.");
      }
    },
    [fail, harbor, onLiveReload, setRundown, show, snapshot.status],
  );

  const removeItem = useCallback(
    async (item: RundownItem) => {
      const restored = itemToHit(item);
      try {
        if (isDeskPin(item) && item.id) {
          const payload = await apiDeleteJson<Rundown>(
            `/autodj/conducteur/items/${encodeURIComponent(item.id)}.json`,
          );
          applyRundown(payload);
          undoRef.current = restored
            ? async () => {
                const next = await apiPostJson<Rundown>(
                  "/autodj/conducteur/items.json",
                  hitPayload(restored),
                );
                applyRundown(next);
                show("Annulé.");
              }
            : null;
        } else {
          const payload = await apiPostJson<DeskMutation>("/autodj/conducteur/items.json", {
            suppress_at: item.at,
          });
          applyRundown(payload);
          const pinId = payload.desk_item?.id;
          undoRef.current = pinId
            ? async () => {
                const next = await apiDeleteJson<Rundown>(
                  `/autodj/conducteur/items/${encodeURIComponent(pinId)}.json`,
                );
                applyRundown(next);
                show("Annulé.");
              }
            : restored
              ? async () => {
                  const next = await apiPostJson<Rundown>(
                    "/autodj/conducteur/items.json",
                    hitPayload(restored, { replace_at: item.at }),
                  );
                  applyRundown(next);
                  show("Annulé.");
                }
              : null;
        }
        show("Retiré de la file.", "success", {
          duration: 8000,
          action: undoRef.current
            ? {
                label: "Annuler",
                onClick: () => {
                  const undo = undoRef.current;
                  undoRef.current = null;
                  if (undo) void undo();
                },
              }
            : undefined,
        });
      } catch (caught) {
        fail(caught, "Retrait impossible. Réessaie.");
      }
    },
    [fail, setRundown, show],
  );

  const reorder = useCallback(
    async (ids: string[]) => {
      try {
        const payload = await apiPut<Rundown>("/autodj/conducteur/items/ranks.json", {
          ids,
        });
        applyRundown(payload);
      } catch (caught) {
        fail(caught, "Réordre impossible. Réessaie.");
      }
    },
    [fail, setRundown],
  );

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.code !== "Space" || event.metaKey || event.ctrlKey || event.altKey || event.shiftKey) return;
      if (directOpen || offline || harbor) return;
      const target = keyTarget(event.target);
      if (ownsSpace(target)) return;
      // Hors des contrôles, Espace ne fait jamais défiler la page : il passe un titre, ou rien.
      event.preventDefault();
      if (!spaceSkips({ target, repeat: event.repeat, lastSkipAt: lastSkipRef.current, now: Date.now() })) return;
      void skipEngine();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [directOpen, harbor, offline, skipEngine]);

  const endsAt = useMemo(() => {
    if (offline || harbor || remainingSec <= 0) return null;
    const end = new Date(wall.getTime() + remainingSec * 1000);
    return `${String(end.getHours()).padStart(2, "0")}:${String(end.getMinutes()).padStart(2, "0")}`;
  }, [harbor, offline, remainingSec, wall]);
  const status = airBanner({
    harbor,
    directTitle: currentShow?.title || "",
    offline,
    silenceS: antenne?.playout.silence_s ?? null,
    playoutReachable: antenne ? antenne.playout.reachable : !offline,
    incidentKinds: (antenne?.incidents ?? []).map((incident) => incident.kind),
  });
  const airState: AirState = offline ? "off" : status.tone;
  const alert = deskAlert(status);
  const anchor = harbor || offline ? null : anchorHint(rundown ? nextAnchoredItem(rundown.items, wall) : null, wall);
  const namingOpen = Boolean(harbor && (renameOpen || !currentShow));

  return (
    <div className="ant" data-state={airState}>
      {alert ? (
        <div className="ant-alert" data-tone={alert.tone}>
          <TriangleAlert size={18} aria-hidden="true" />
          <p role="alert">
            <strong>{alert.title}</strong> {alert.help}
          </p>
          {alert.live ? <span className="ant-alert-live" aria-hidden="true">{alert.live}</span> : null}
          {isAdmin ? (
            <Link to="/reglages?onglet=automate" className="ant-link">
              Diagnostic
            </Link>
          ) : null}
        </div>
      ) : null}

      <OnAirCard
        state={airState}
        item={now}
        elapsedSec={elapsedSec}
        durationSec={durationSec}
        remainingSec={remainingSec}
        source={source}
        endsAt={endsAt}
        anchor={anchor}
        onSkip={() => void skipEngine()}
        skipDisabled={offline || harbor}
        onDirect={() => setDirectOpen(true)}
        directRef={directButtonRef}
      >
        {harbor ? (
          namingOpen ? (
            <form
              className="ant-rename"
              onSubmit={(event) => {
                event.preventDefault();
                void nameLive();
              }}
            >
              <label>
                <span>Nom de l’émission</span>
                <input
                  ref={renameTitleRef}
                  value={showTitle}
                  onChange={(event) => setShowTitle(event.target.value)}
                  placeholder="Nom de l’émission"
                  disabled={naming}
                />
              </label>
              <label>
                <span>Phrase artiste</span>
                <input
                  value={showArtist}
                  onChange={(event) => setShowArtist(event.target.value)}
                  placeholder="Phrase artiste"
                  disabled={naming}
                />
              </label>
              <div className="ant-rename-actions">
                <button
                  type="submit"
                  className="ant-btn ant-btn--small ant-btn--primary"
                  disabled={naming || !showTitle.trim() || !showArtist.trim()}
                >
                  {currentShow ? "Renommer" : "Enregistrer"}
                </button>
                {currentShow ? (
                  <button type="button" className="ant-btn ant-btn--small" onClick={() => setRenameOpen(false)} disabled={naming}>
                    Annuler
                  </button>
                ) : null}
              </div>
            </form>
          ) : (
            <div className="ant-air-extra">
              <span>Le direct tient l’antenne, l’horloge est en pause.</span>
              <button
                type="button"
                className="ant-btn ant-btn--small"
                onClick={() => {
                  setShowTitle(currentShow?.title || "");
                  setShowArtist(currentShow?.artist || "");
                  setRenameOpen(true);
                  window.setTimeout(() => renameTitleRef.current?.focus(), 0);
                }}
              >
                Renommer
              </button>
            </div>
          )
        ) : datedSet ? (
          <div className="ant-air-extra">
            <span>{datedSet.until ? `Set prévu jusqu’à ${timeLabel(datedSet.until)}.` : "Set de l’agenda."}</span>
            {canStopDated ? (
              <button
                type="button"
                className={`ant-btn ant-btn--small${stopArmed ? " ant-btn--danger" : ""}`}
                onClick={() => void stopDated()}
                onBlur={() => setStopArmed(false)}
                disabled={stopping}
              >
                {stopping ? "Arrêt…" : stopArmed ? "Confirmer : reprendre la grille" : "Arrêter le set"}
              </button>
            ) : null}
          </div>
        ) : null}
      </OnAirCard>

      <div className="ant-stage">
        <QueuePanel
          rundown={rundown}
          unreadable={rundownUnreadable}
          live={live}
          wall={wall}
          onRemove={(item) => void removeItem(item)}
          onReorder={(ids) => void reorder(ids)}
          onInsertHit={(hit, beforeId) => void insertHit(hit, beforeId)}
        />
        <LibraryPanel
          fireDisabled={harbor}
          onInsertNext={(hit) => void insertHit(hit)}
          onFireNow={(hit) => void fireNow(hit)}
          onNotice={(text) => show(text)}
        />
      </div>

      <DirectDialog
        open={directOpen}
        onOpenChange={setDirectOpen}
        live={live}
        antenne={antenne}
        emissions={emissions}
        offline={offline}
        returnFocus={directButtonRef}
      />
      <ProtoToast message={message} onDismiss={dismiss} />
    </div>
  );
}
