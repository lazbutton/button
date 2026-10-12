import { useCallback, useEffect, useMemo, useRef, useState, type Dispatch, type SetStateAction } from "react";
import { DeskFile } from "../components/DeskFile";
import { LiveConnectPanel } from "../components/LiveConnectPanel";
import { DeskGlance } from "../components/DeskGlance";
import { DeskLibrary } from "../components/DeskLibrary";
import { ProtoToast, useProtoToast } from "../components/ProtoToast";
import { parisParts } from "../lib/parisClock";
import { useAntennaClock } from "../lib/liveClock";
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
import { liveSourceLabel } from "../api/topbar";
import { SessionGate } from "../api/SessionGate";
import {
  CONDUCTEUR_JSON,
  isDeskPin,
  itemNamedLikeLive,
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

function typingTarget(target: EventTarget | null): boolean {
  return (
    target instanceof HTMLInputElement ||
    target instanceof HTMLTextAreaElement ||
    (target instanceof HTMLElement && target.isContentEditable)
  );
}

function AntenneDesk({
  live,
  rundown,
  emissions,
  antenne,
  setRundown,
  onLiveReload,
}: {
  live: LiveSnapshot | null;
  rundown: Rundown | null;
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
  const now = glanceNowItem(liveMatches ? parts?.onAir ?? null : null, snapshot);
  const harbor = harborIsLive(snapshot);
  const elapsedSec = clock.elapsedSec;
  const durationSec = clock.durationSec;
  const remainingSec = clock.remainingSec;
  const offline = snapshot.status === "offline";
  const currentShow = snapshot.emission ?? emissions?.current ?? null;
  const source = liveSourceLabel(snapshot);
  const [showTitle, setShowTitle] = useState("");
  const [showArtist, setShowArtist] = useState("");
  const [naming, setNaming] = useState(false);
  const [renameOpen, setRenameOpen] = useState(false);
  const [directOpen, setDirectOpen] = useState(false);
  const directToggleRef = useRef<HTMLButtonElement>(null);
  const directWasOpen = useRef(false);
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
  const { account } = useAccount();
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
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      if (typingTarget(event.target)) return;
      if (event.key === "Escape" && directOpen) {
        setDirectOpen(false);
        return;
      }
      if (event.code === "Space") {
        event.preventDefault();
        if (!offline && !harbor) void skipEngine();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [directOpen, harbor, offline, skipEngine]);

  useEffect(() => {
    if (directOpen) {
      directWasOpen.current = true;
      return;
    }
    if (directWasOpen.current) directToggleRef.current?.focus();
  }, [directOpen]);

  const endsAt = useMemo(() => {
    if (offline || harbor || remainingSec <= 0) return null;
    const end = new Date(wall.getTime() + remainingSec * 1000);
    return `${String(end.getHours()).padStart(2, "0")}:${String(end.getMinutes()).padStart(2, "0")}`;
  }, [harbor, offline, remainingSec, wall]);
  const glanceSource = {
    label: offline ? "Arrêt" : harbor ? "Direct" : source.label,
    id: offline ? "offline" : harbor ? "stream" : (snapshot.source || "autodj").toLowerCase(),
  };
  const status = airBanner({
    harbor,
    directTitle: currentShow?.title || "",
    offline,
    silenceS: antenne?.playout.silence_s ?? null,
    playoutReachable: antenne ? antenne.playout.reachable : !offline,
    incidentKinds: (antenne?.incidents ?? []).map((incident) => incident.kind),
  });
  const clockLabel = parisParts(wall).clock;
  const airState = offline ? "off" : status.tone;
  const ending = !offline && !harbor && remainingSec > 0 && remainingSec <= 15;
  const namingOpen = Boolean(harbor && (renameOpen || !currentShow));

  return (
    <div
      className="desk desk--pupitre"
      data-state={airState}
      data-hot={status.hot ? "true" : "false"}
      data-ending={ending ? "true" : "false"}
    >
      <div className="banner" role="status" aria-live="polite">
        <span className="banner-dot" aria-hidden="true" />
        <div className="banner-copy">
          <span className="banner-label">{status.label}</span>
          <span className="banner-cause">{status.cause}</span>
        </div>
        <button
          ref={directToggleRef}
          type="button"
          className="banner-direct"
          aria-expanded={directOpen}
          aria-controls="direct-sheet"
          onClick={() => setDirectOpen((open) => !open)}
        >
          Passer en direct ?
        </button>
        <time className="banner-clock" dateTime={clockLabel}>
          {clockLabel}
        </time>
      </div>
      {directOpen ? (
        <LiveConnectPanel
          live={live}
          antenne={antenne}
          emissions={emissions}
          offline={offline}
          onClose={() => setDirectOpen(false)}
        />
      ) : null}
      <DeskGlance
        item={now}
        elapsedSec={elapsedSec}
        durationSec={durationSec}
        remainingSec={remainingSec}
        onSkip={() => void skipEngine()}
        skipDisabled={offline || harbor}
        keysHint="Espace suivant · / chercher · Entrée à la suite"
        source={glanceSource}
        endsAt={endsAt}
      >
        {harbor ? (
          namingOpen ? (
            <form
              className="rename is-open"
              onSubmit={(event) => {
                event.preventDefault();
                void nameLive();
              }}
            >
              <label>
                Nom de l’émission
                <input
                  ref={renameTitleRef}
                  value={showTitle}
                  onChange={(event) => setShowTitle(event.target.value)}
                  placeholder="Nom de l’émission"
                  disabled={naming}
                />
              </label>
              <label>
                Phrase artiste
                <input
                  value={showArtist}
                  onChange={(event) => setShowArtist(event.target.value)}
                  placeholder="Phrase artiste"
                  disabled={naming}
                />
              </label>
              <button type="submit" disabled={naming || !showTitle.trim() || !showArtist.trim()}>
                {currentShow ? "Renommer" : "Enregistrer"}
              </button>
              {currentShow ? (
                <button type="button" onClick={() => setRenameOpen(false)} disabled={naming}>
                  Annuler
                </button>
              ) : null}
            </form>
          ) : (
            <button
              type="button"
              onClick={() => {
                setShowTitle(currentShow?.title || "");
                setShowArtist(currentShow?.artist || "");
                setRenameOpen(true);
                window.setTimeout(() => renameTitleRef.current?.focus(), 0);
              }}
            >
              Renommer
            </button>
          )
        ) : datedSet ? (
          <div className="rename">
            <span>
              Émission datée · <strong>{datedSet.title}</strong>
              {datedSet.until ? ` · prévue jusqu'à ${timeLabel(datedSet.until)}` : ""}
            </span>
            {canStopDated ? (
              <button type="button" onClick={() => void stopDated()} disabled={stopping}>
                {stopping ? "Arrêt…" : stopArmed ? "Confirmer : reprendre la grille" : "Arrêter et reprendre la grille"}
              </button>
            ) : null}
          </div>
        ) : null}
      </DeskGlance>

      <div className="stage">
        <DeskFile
          rundown={rundown}
          live={live}
          wall={wall}
          selectedId={null}
          onSelect={() => undefined}
          onRemove={(item) => void removeItem(item)}
          onReorder={(ids) => void reorder(ids)}
          onInsertHit={(hit, beforeId) => void insertHit(hit, beforeId)}
        />
        <DeskLibrary
          fireDisabled={harbor}
          onInsertNext={(hit) => void insertHit(hit)}
          onFireNow={(hit) => void fireNow(hit)}
        />
      </div>

      <ProtoToast message={message} onDismiss={dismiss} />
    </div>
  );
}
