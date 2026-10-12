import { Button } from "@radix-ui/themes";
import { Clock3, Plus } from "lucide-react";
import { useMemo, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { ClockEditor } from "../components/programmation/ClockEditor";
import { ClockSidebar } from "../components/programmation/ClockSidebar";
import { CreateClockDialog } from "../components/programmation/CreateClockDialog";
import { ProtoToast, useProtoToast } from "../components/ProtoToast";
import { RepairClockCartDialog } from "../components/RepairClockCartDialog";
import { apiDelete, apiGet, apiPostJson, ApiRequestError } from "../api/client";
import { apiCacheDrop } from "../api/jsonCache";
import { errorText } from "../api/programmationErrors";
import { clockTints, clockWeekUsage, copySteps, starterMotif, stepsSummary } from "../api/programmationView";
import { SessionGate } from "../api/SessionGate";
import type { CartsResponse, CategoriesResponse, Clock, ClocksResponse, Rundown, SlotsResponse } from "../api/types";
import { useApiJson } from "../api/useApiJson";
import { useClockSaver } from "../api/useClockSaver";
import { ConfirmDialog } from "../ui/ConfirmDialog";
import "../styles/pages/programmation.css";

export function HorlogesPage() {
  const clocksRes = useApiJson<ClocksResponse>("/autodj/clocks.json");
  const cartsRes = useApiJson<CartsResponse>("/carts.json");
  const catsRes = useApiJson<CategoriesResponse>("/autodj/categories.json");
  const slotsRes = useApiJson<SlotsResponse>("/autodj/slots.json", 30_000);
  const rundownRes = useApiJson<Rundown>("/autodj/conducteur.json", 15_000);
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const { message, show, dismiss } = useProtoToast();
  const [view, setView] = useState<"list" | "detail">(() => (params.get("clock") ? "detail" : "list"));
  const [creating, setCreating] = useState<{ copyOf: Clock | null } | null>(null);
  const [deleting, setDeleting] = useState<Clock | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);
  const [repairIndex, setRepairIndex] = useState<number | null>(null);

  const carts = cartsRes.data?.carts ?? [];
  const categories = catsRes.data?.categories ?? [];
  const slots = useMemo(() => slotsRes.data?.slots ?? [], [slotsRes.data]);
  const clocks = useMemo(
    () => [...(clocksRes.data?.clocks ?? [])].sort((a, b) => a.name.localeCompare(b.name, "fr")),
    [clocksRes.data],
  );
  const latest = useRef(clocks);
  latest.current = clocks;
  const requestedId = Number(params.get("clock"));
  const clock = clocks.find((row) => row.id === requestedId) ?? clocks[0] ?? null;
  const onAirName = rundownRes.data?.clock?.trim() || "";
  const tints = useMemo(() => clockTints(clocks), [clocks]);
  const usage = useMemo(() => {
    const map = new Map<number, string[]>();
    for (const row of clocks) map.set(row.id, clockWeekUsage(slots, row.id));
    return map;
  }, [clocks, slots]);

  const putLocal = (next: Clock) => {
    latest.current = latest.current.map((row) => (row.id === next.id ? next : row));
    clocksRes.setData({ clocks: latest.current });
  };

  // The PUT answer lists the steps in their order from before the write: keep what was sent, with the
  // new version, then read the engine's copy back once nothing else moved.
  const refresh = async (id: number, version: number | undefined) => {
    try {
      const payload = await apiGet<ClocksResponse>("/autodj/clocks.json");
      const fresh = payload.clocks.find((row) => row.id === id);
      const current = latest.current.find((row) => row.id === id);
      if (saverRef.current?.busy(id)) return;
      if (fresh && current && fresh.version === version && current.version === version) putLocal(fresh);
    } catch {
      // The local copy stays right; the next gesture writes it again.
    }
  };

  const saverRef = useRef<{ busy: (id: number) => boolean } | null>(null);
  const saver = useClockSaver({
    onSaved: (saved, sent) => {
      putLocal({ ...sent, version: saved.version });
      void refresh(saved.id, saved.version);
    },
    onFailed: (caught, id) => {
      const text = errorText(caught, "Enregistrement impossible.");
      // Changed elsewhere: the engine's copy wins. Refused as it is: the changes stay on screen, to be fixed.
      if (caught instanceof ApiRequestError && caught.status === 409 && /version/i.test(caught.message)) {
        setSaveError(null);
        show(text, "error");
        revert(id);
        return;
      }
      setSaveError(text);
      show(`${text} Les changements restent à l'écran : corrige, ils repartiront au geste suivant.`, "error", {
        duration: 9000,
        action: { label: "Revenir à la version enregistrée", onClick: () => revert(id) },
      });
    },
  });
  const [saveError, setSaveError] = useState<string | null>(null);

  const revert = (id: number) => {
    setSaveError(null);
    apiCacheDrop("/autodj/clocks.json");
    void clocksRes.reload().then(() => saver.forget(id));
  };

  saverRef.current = saver;

  /** Every gesture: shown at once, written right after. */
  const change = (next: Clock) => {
    setSaveError(null);
    putLocal(next);
    saver.save(next);
  };

  const removed = (text: string, undo: (latest: Clock) => Clock) => {
    if (!clock) return;
    const id = clock.id;
    show(text, "info", {
      duration: 6000,
      action: {
        label: "Annuler",
        onClick: () => {
          const current = latest.current.find((row) => row.id === id);
          if (current) change(undo(current));
        },
      },
    });
  };

  const select = (id: number) => {
    setView("detail");
    if (params.get("clock") === String(id)) return;
    setParams(
      (current) => {
        const next = new URLSearchParams(current);
        next.set("clock", String(id));
        return next;
      },
      { replace: true },
    );
  };

  const create = async (name: string, from: Clock | null) => {
    const motif = from ? copySteps(from.motif) : starterMotif(carts, categories);
    if (!motif.length)
      throw new Error(
        "Crée d'abord un bac dans Sons, ou une sélection de titres : une heure type joue au moins une étape.",
      );
    try {
      const payload = await apiPostJson<{ clock: Clock }>("/autodj/clocks.json", {
        name,
        fallback_cart: from?.fallback_cart ?? "",
        fallback_cart_id: from?.fallback_cart_id ?? null,
        motif,
        anchors: from ? copySteps(from.anchors) : [],
      });
      apiCacheDrop("/autodj/clocks.json");
      await clocksRes.reload();
      select(payload.clock.id);
      show(from ? `« ${name} » créée, copie de « ${from.name} »` : `« ${name} » créée`, "success");
    } catch (caught) {
      throw new Error(errorText(caught, "Création impossible."));
    }
  };

  const remove = async () => {
    if (!deleting) return;
    setDeleteBusy(true);
    try {
      await apiDelete(`/autodj/clocks/${deleting.id}.json`);
      apiCacheDrop("/autodj/clocks.json");
      setParams(
        (current) => {
          const next = new URLSearchParams(current);
          next.delete("clock");
          return next;
        },
        { replace: true },
      );
      setView("list");
      await clocksRes.reload();
      show(`« ${deleting.name} » supprimée`, "success");
      setDeleting(null);
    } catch (caught) {
      show(errorText(caught, "Suppression impossible."), "error");
      setDeleting(null);
    } finally {
      setDeleteBusy(false);
    }
  };

  const starter = stepsSummary({ motif: starterMotif(carts, categories) }) || "Une étape à choisir";
  const repairing = clock && repairIndex != null ? clock.motif[repairIndex] : null;

  return (
    <div className="prog-page">
      <SessionGate
        loading={clocksRes.loading}
        error={clocksRes.error}
        ready={clocksRes.data != null}
        onRetry={() => {
          void clocksRes.reload();
          void cartsRes.reload();
          void catsRes.reload();
          void slotsRes.reload();
        }}
      >
        {clock ? (
          <div className="prog-work" data-view={view}>
            <ClockSidebar
              clocks={clocks}
              selectedId={clock.id}
              onAirName={onAirName}
              usage={usage}
              tints={tints}
              onSelect={select}
              onCreate={() => setCreating({ copyOf: null })}
            />
            <ClockEditor
              key={clock.id}
              clock={clock}
              carts={carts}
              categories={categories}
              otherNames={clocks.filter((row) => row.id !== clock.id).map((row) => row.name)}
              usage={usage.get(clock.id) ?? []}
              tint={tints.get(clock.id) ?? "gray"}
              onAir={Boolean(onAirName) && onAirName === clock.name}
              saveState={saver.state}
              saveError={saveError}
              onRetry={() => {
                const current = latest.current.find((row) => row.id === clock.id);
                if (current) change(current);
              }}
              onRevert={() => revert(clock.id)}
              onChange={change}
              onRemoved={removed}
              onRepair={setRepairIndex}
              onDuplicate={() => setCreating({ copyOf: clock })}
              onDelete={() => setDeleting(clock)}
              onBack={() => setView("list")}
            />
          </div>
        ) : (
          <div className="prog-first">
            <span className="prog-first-icon" aria-hidden="true">
              <Clock3 size={22} />
            </span>
            <h2>Première heure type</h2>
            <p>
              Une heure type dit ce qui passe pendant une heure : un jingle, des titres, des coupures pub. Pose-la
              ensuite dans la semaine.
            </p>
            <Button size="2" highContrast onClick={() => setCreating({ copyOf: null })}>
              <Plus className="ui-button-icon" />
              Créer une heure type
            </Button>
          </div>
        )}
      </SessionGate>

      <CreateClockDialog
        open={creating != null}
        onOpenChange={(open) => {
          if (!open) setCreating(null);
        }}
        clocks={clocks}
        copyOf={creating?.copyOf ?? null}
        starter={starter}
        onCreate={create}
      />
      <ConfirmDialog
        open={deleting != null}
        onOpenChange={(open) => {
          if (!open && !deleteBusy) setDeleting(null);
        }}
        title={`Supprimer « ${deleting?.name ?? ""} » ?`}
        description="L'heure type disparaît, avec ses étapes et ses coupures. Elle n'est posée nulle part dans la semaine."
        confirmLabel="Supprimer l'heure type"
        busy={deleteBusy}
        onConfirm={remove}
      />
      <RepairClockCartDialog
        open={repairing != null}
        onOpenChange={(open) => {
          if (!open) setRepairIndex(null);
        }}
        clocks={clocks}
        carts={carts}
        missingTitle={repairing?.cart || ""}
        clockId={clock?.id}
        clockName={clock?.name}
        positionId={repairing?.id}
        motifIndex={repairIndex}
        kind={repairing?.kind}
        onRepaired={async () => {
          apiCacheDrop("/autodj/clocks.json");
          await clocksRes.reload();
          await cartsRes.reload();
          if (clock) saver.forget(clock.id);
          show("Étape réparée", "success");
        }}
        onOpenCart={(id) => navigate(`/sons?id=${id}`)}
        onError={(text) => show(text, "error")}
      />
      <ProtoToast message={message} onDismiss={dismiss} />
    </div>
  );
}
