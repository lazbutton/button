import { useCallback, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { PlanSummary } from "../components/conducteur/PlanSummary";
import { RundownPanel } from "../components/conducteur/RundownPanel";
import { RepairClockCartDialog } from "../components/RepairClockCartDialog";
import { useAntennaClock } from "../lib/liveClock";
import { useAccount } from "../api/AccountContext";
import { roleAtLeast } from "../api/roles";
import {
  ApiAuthError,
  ApiForbiddenError,
  ApiRequestError,
  ApiUnavailableError,
  apiDeleteJson,
  apiPostJson,
} from "../api/client";
import { SessionGate } from "../api/SessionGate";
import { lineCopy, withoutClosedTwins } from "../api/conducteurView";
import { CONDUCTEUR_JSON, clockLineRemoval, isDeskPin, partitionRundown } from "../api/rundownLive";
import type {
  CartsResponse,
  ClocksResponse,
  EmissionsResponse,
  LiveSnapshot,
  Rundown,
  RundownItem,
} from "../api/types";
import { useApiJson } from "../api/useApiJson";
import { AppToast, useAppToast } from "../ui/AppToast";
import { PageHeader } from "../ui/PageHeader";
import "../styles/pages/conducteur.css";

const POLL_MS = 3_000;

/** Le retrait posé revient avec la file : « Annuler » l'efface. */
type DeskMutation = Rundown & { desk_item?: RundownItem };

const lineUrl = (id: string) => `/autodj/conducteur/items/${encodeURIComponent(id)}.json`;

/**
 * Le geste fini, le focus revient où il était : le bouton qui a ouvert la
 * réparation. Si sa ligne a changé, ou après un retrait, il revient au
 * déroulé plutôt que de tomber sur la page.
 */
function refocus(target: HTMLElement | null) {
  // Deux images plus tard : la ligne retirée a quitté la page, le dialogue aussi.
  window.requestAnimationFrame(() =>
    window.requestAnimationFrame(() => {
      if (target?.isConnected) {
        target.focus();
        return;
      }
      const active = document.activeElement;
      if (!active || active === document.body) {
        document.querySelector<HTMLElement>(".cond-list")?.focus({ preventScroll: true });
      }
    }),
  );
}

/** Réparer une étape sans son : les heures types et les bacs ne se lisent que pour un programmateur. */
function RepairHost({
  item,
  onClose,
  onRepaired,
  onError,
}: {
  item: RundownItem | null;
  onClose: () => void;
  onRepaired: () => Promise<void>;
  onError: (message: string) => void;
}) {
  const clocks = useApiJson<ClocksResponse>("/autodj/clocks.json");
  const carts = useApiJson<CartsResponse>("/carts.json");
  const navigate = useNavigate();
  return (
    <RepairClockCartDialog
      open={item != null}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
      clocks={clocks.data?.clocks ?? []}
      carts={carts.data?.carts ?? []}
      missingTitle={item?.cart || item?.resource || ""}
      clockId={item?.clock_id}
      clockName={item?.clock}
      positionId={item?.position_id}
      kind={item?.kind}
      onRepaired={async () => {
        await clocks.reload();
        await onRepaired();
      }}
      onOpenCart={(cartId) => navigate(`/sons?id=${cartId}`)}
      onError={onError}
    />
  );
}

export function ConducteurPage() {
  const live = useApiJson<LiveSnapshot>("/live.json", 2000);
  const { data, setData, error, loading, reload } = useApiJson<Rundown>(CONDUCTEUR_JSON, POLL_MS);
  const emissions = useApiJson<EmissionsResponse>("/antenne/emissions.json", POLL_MS);
  const clock = useAntennaClock(live.data);
  const { toast, show, dismiss } = useAppToast();
  const [repairItem, setRepairItem] = useState<RundownItem | null>(null);
  const { role } = useAccount();
  const canEdit = roleAtLeast(role, "programmateur");

  // Les gestes passent aux lignes, qui ne se redessinent pas à chaque seconde :
  // ils restent les mêmes d'un rendu à l'autre, et lisent le toast du moment.
  const showRef = useRef(show);
  showRef.current = show;

  // Un geste qui échoue s'annonce en alerte, avec la raison du moteur quand il en donne une.
  const fail = useCallback((caught: unknown, fallback: string) => {
    const say = showRef.current;
    if (caught instanceof ApiAuthError) say("Session expirée. Reconnecte-toi.", "error");
    else if (caught instanceof ApiForbiddenError) say("Il faut le rôle Programmateur pour modifier le conducteur.", "error");
    else if (caught instanceof ApiRequestError) say(caught.message, "error");
    else if (caught instanceof ApiUnavailableError) say("L’automate ne répond pas. Réessaie dans un instant.", "error");
    else say(fallback, "error");
  }, []);

  // « Annuler » efface le retrait, et la ligne de l'horloge revient à sa place.
  // Il part avec son message et ne revient pas : son échec dit que la ligne reste
  // retirée, et comment la remettre, plutôt que de faire réessayer.
  const undoRemoval = useCallback(
    async (removalId: string, title: string) => {
      try {
        setData(await apiDeleteJson<Rundown>(lineUrl(removalId)));
        showRef.current(`Retrait annulé : « ${title} » est revenu à sa place.`, "success");
      } catch (caught) {
        const back = "La ligne reste retirée : remets-la au pupitre, depuis la bibliothèque.";
        if (caught instanceof ApiUnavailableError) showRef.current(`L’automate ne répond pas. ${back}`, "error");
        else fail(caught, `Annulation impossible. ${back}`);
      } finally {
        // Le message et son bouton sont partis : le focus revient au déroulé.
        refocus(null);
      }
    },
    [fail, setData],
  );

  // Un double clic ne pose qu'un retrait : « Annuler » n'en lèverait qu'un, et la
  // ligne resterait cachée sans que rien ne le dise.
  const removingRef = useRef(new Set<string>());

  // Une ligne du pupitre s'efface. Une ligne de l'horloge se retire par un retrait,
  // comme au pupitre : le moteur refuse de l'effacer, rien ne la remettrait à sa place.
  const removeItem = useCallback(
    async (item: RundownItem) => {
      const id = item.id;
      if (!id || removingRef.current.has(id)) return;
      removingRef.current.add(id);
      const { title } = lineCopy(item);
      try {
        if (isDeskPin(item)) {
          setData(await apiDeleteJson<Rundown>(lineUrl(id)));
          showRef.current(`« ${title} » retiré du conducteur.`, "success");
        } else {
          const payload = await apiPostJson<DeskMutation>("/autodj/conducteur/items.json", clockLineRemoval(item));
          setData(payload);
          const removalId = payload.desk_item?.id;
          showRef.current(
            `« ${title} » retiré du conducteur.`,
            "success",
            removalId ? { action: { label: "Annuler", onClick: () => void undoRemoval(removalId, title) } } : undefined,
          );
        }
        refocus(null);
      } catch (caught) {
        // Refusé, la ligne a bougé ou est déjà partie : le conducteur se relit tout
        // de suite, sans attendre sa lecture suivante, pour qu'un nouvel essai la vise.
        // Relue, la ligne peut perdre son bouton : le focus revient alors au déroulé.
        if (caught instanceof ApiRequestError && caught.status === 409) void reload().then(() => refocus(null));
        fail(caught, "Retrait impossible. Réessaie.");
      } finally {
        removingRef.current.delete(id);
      }
    },
    [fail, reload, setData, undoRemoval],
  );

  const onRemove = useCallback((item: RundownItem) => void removeItem(item), [removeItem]);
  const repairFromRef = useRef<HTMLElement | null>(null);
  const onRepair = useCallback((item: RundownItem, origin: HTMLElement) => {
    repairFromRef.current = origin;
    setRepairItem(item);
  }, []);
  const closeRepair = useCallback(() => {
    setRepairItem(null);
    refocus(repairFromRef.current);
  }, []);
  const items = useMemo(() => (data ? withoutClosedTwins(data.items) : []), [data]);
  const parts = data ? partitionRundown(items, clock.wall, live.data) : null;

  return (
    <main className="ui-page ui-page--fill cond">
      <PageHeader title="Conducteur" description="Ce qui va passer, heure par heure, et ce qui vient de passer." />

      <SessionGate loading={loading} error={error} ready={data != null} onRetry={() => void reload()}>
        {data && parts ? (
          <>
            <PlanSummary
              rundown={data}
              upcoming={parts.upcoming}
              live={live.data}
              emissions={emissions.data}
              wall={clock.wall}
              canOpenClock={canEdit}
            />
            <RundownPanel
              rundown={data}
              parts={parts}
              live={live.data}
              clock={clock}
              unreadable={error === "down"}
              canEdit={canEdit}
              onRepair={canEdit ? onRepair : undefined}
              onRemove={canEdit ? onRemove : undefined}
            />
          </>
        ) : null}
      </SessionGate>

      {canEdit ? (
        <RepairHost
          item={repairItem}
          onClose={closeRepair}
          onRepaired={async () => {
            await reload();
            showRef.current("Étape réparée.", "success");
          }}
          onError={(text) => showRef.current(text, "error")}
        />
      ) : null}
      <AppToast toast={toast} onDismiss={dismiss} />
    </main>
  );
}
