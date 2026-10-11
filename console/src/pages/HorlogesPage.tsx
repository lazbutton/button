import { Badge, TextField } from "@radix-ui/themes";
import { Check, Clock3 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { ClockList } from "../components/ClockList";
import { ClockCartsPanel } from "../components/ClockCartsPanel";
import { HourStrip, type StudioSelection } from "../components/HourStrip";
import { Inspector } from "../components/Inspector";
import { MotifStack } from "../components/MotifStack";
import { PubMinutes } from "../components/PubMinutes";
import { ProtoToast, useProtoToast } from "../components/ProtoToast";
import { PutCartInClockDialog } from "../components/PutCartInClockDialog";
import { RepairClockCartDialog } from "../components/RepairClockCartDialog";
import { defaultMotif, pickCart, pickProgCart, pickPubCart, slotUsages } from "../api/clockMeta";
import { cartRef, emptyAnchor, emptyMotifStep, mergeClockPosition, saveClock } from "../api/clockWrite";
import { apiDelete, apiPostJson, ApiRequestError } from "../api/client";
import { apiCacheDrop } from "../api/jsonCache";
import { SessionGate } from "../api/SessionGate";
import type {
  CartsResponse,
  CategoriesResponse,
  Clock,
  ClockPosition,
  ClocksResponse,
  Rundown,
  SlotsResponse,
} from "../api/types";
import { useApiJson } from "../api/useApiJson";
import "../styles/pages/horloges.css";
import { EmptyState } from "../ui/EmptyState";
import { SelectField } from "../ui/FormField";
import { PageHeader } from "../ui/PageHeader";
import { Panel } from "../ui/Panel";

const NONE = "__none__";

export function HorlogesPage({ embedded = false }: { embedded?: boolean }) {
  const clocksRes = useApiJson<ClocksResponse>("/autodj/clocks.json");
  const cartsRes = useApiJson<CartsResponse>("/carts.json");
  const catsRes = useApiJson<CategoriesResponse>("/autodj/categories.json");
  const slotsRes = useApiJson<SlotsResponse>("/autodj/slots.json");
  const rundownRes = useApiJson<Rundown>("/autodj/conducteur.json", 15000);
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const [selection, setSelection] = useState<StudioSelection>({ kind: "idle" });
  const [lastMotif, setLastMotif] = useState(0);
  const [clockId, setClockId] = useState<number | null>(null);
  const [busyLabel, setBusyLabel] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [name, setName] = useState("");
  const [repairIndex, setRepairIndex] = useState<number | null>(null);
  const [addCartOpen, setAddCartOpen] = useState(false);
  const { message, show } = useProtoToast();
  const clocks = clocksRes.data?.clocks ?? [];
  const carts = cartsRes.data?.carts ?? [];
  const categories = catsRes.data?.categories ?? [];
  const slots = slotsRes.data?.slots ?? [];
  const clock = clocks.find((c) => c.id === clockId) ?? clocks[0];
  const motifIndex = selection.kind === "motif" ? selection.index : null;
  const repairing = repairIndex != null ? clock?.motif[repairIndex] : null;
  const clockQuery = params.get("clock");
  const appliedClockQuery = useRef<string | null>(null);

  const reloadAll = () => {
    void clocksRes.reload();
    void cartsRes.reload();
    void catsRes.reload();
    void slotsRes.reload();
    void rundownRes.reload();
  };

  const choose = (next: StudioSelection) => {
    if (next.kind === "motif") setLastMotif(next.index);
    setSelection(next);
  };

  useEffect(() => {
    if (clock && (clockId == null || !clocks.some((c) => c.id === clockId))) {
      setClockId(clock.id);
    }
  }, [clock, clockId, clocks]);

  useEffect(() => {
    if (!clockQuery || appliedClockQuery.current === clockQuery || !clocks.length) return;
    const id = Number(clockQuery);
    if (Number.isFinite(id) && clocks.some((row) => row.id === id)) {
      setClockId(id);
      appliedClockQuery.current = clockQuery;
    }
  }, [clockQuery, clocks]);

  const clockRef = useRef(clock);
  clockRef.current = clock;

  useEffect(() => {
    setSelection({ kind: "idle" });
    setLastMotif(0);
    setSaved(false);
  }, [clockId]);

  useEffect(() => {
    setName(clock?.name ?? "");
  }, [clock?.id, clock?.name]);

  const persist = async (
    next: Clock,
    _ok = "Heure type enregistrée",
    pending = "Enregistrement…",
  ): Promise<boolean> => {
    setBusyLabel(pending);
    setSaved(false);
    try {
      const savedClock = await saveClock(next);
      clocksRes.setData((prev) => {
        const rows = prev?.clocks ?? [];
        const nextClocks = rows.some((row) => row.id === savedClock.id)
          ? rows.map((row) => (row.id === savedClock.id ? savedClock : row))
          : [...rows, savedClock];
        return { clocks: nextClocks };
      });
      setClockId(savedClock.id);
      apiCacheDrop("/autodj/clocks.json");
      await clocksRes.reload();
      setSaved(true);
      return true;
    } catch (caught) {
      show(caught instanceof ApiRequestError ? caught.message : "Enregistrement impossible.");
      return false;
    } finally {
      setBusyLabel(null);
    }
  };

  useEffect(() => {
    const current = clockRef.current;
    if (!current) return;
    const trimmed = name.trim();
    if (!trimmed || trimmed === current.name) return;
    const timer = window.setTimeout(() => {
      const latest = clockRef.current;
      if (!latest || trimmed === latest.name) return;
      void persist({ ...latest, name: trimmed });
    }, 500);
    return () => window.clearTimeout(timer);
  }, [name]);

  const savePosition = async (position: ClockPosition, index?: number): Promise<boolean> => {
    if (!clock) return false;
    if (position.when === "anchored" && position.minute != null) {
      const current = clock.anchors.find((row) => row.minute === position.minute);
      const anchors = clock.anchors.filter((row) => row.minute !== position.minute);
      anchors.push(mergeClockPosition(current, position));
      anchors.sort((a, b) => (a.minute ?? 0) - (b.minute ?? 0));
      const saved = await persist({ ...clock, anchors }, "Coupure enregistrée");
      if (saved) setSelection({ kind: "anchor", minute: position.minute });
      return saved;
    }
    const motif = clock.motif.slice();
    const at = index ?? 0;
    motif[at] = mergeClockPosition(motif[at], position);
    return persist({ ...clock, motif });
  };

  const createClock = async (name: string, fallback: string) => {
    setBusyLabel("Création de l’heure type…");
    try {
      const created = await apiPostJson<{ clock: Clock }>("/autodj/clocks.json", {
        name,
        fallback_cart: fallback,
        motif: defaultMotif(carts, categories, fallback || null),
        anchors: [],
      });
      setClockId(created.clock.id);
      await clocksRes.reload();
      show("Heure type créée");
    } catch (caught) {
      show(caught instanceof ApiRequestError ? caught.message : "Création impossible.");
    } finally {
      setBusyLabel(null);
    }
  };

  const listProps = {
    clocks,
    carts,
    usage: clock ? slotUsages(slots, clock.id, clock.name) : [],
    usageReady: slotsRes.data != null,
    onAirName: rundownRes.data?.clock?.trim() || "",
    onSelect: setClockId,
    onCreate: createClock,
  };

  const onAir = Boolean(clock && rundownRes.data?.clock === clock.name);

  const createCut = async (minute: number) => {
    if (!clock) return;
    const guessed = pickPubCart(carts);
    const anchor = emptyAnchor(minute, {
      cart: guessed?.title ?? null,
      fallback: clock.fallback_cart,
    });
    if (guessed) anchor.cart_id = guessed.id;
    const anchors = clock.anchors.filter((row) => row.minute !== minute);
    anchors.push(anchor);
    anchors.sort((a, b) => (a.minute ?? 0) - (b.minute ?? 0));
    const didSave = await persist({ ...clock, anchors });
    if (didSave) setSelection({ kind: "anchor", minute });
  };

  const onStrip = (next: StudioSelection) => {
    if (next.kind === "new-anchor") {
      void createCut(next.minute);
      return;
    }
    choose(next);
  };

  const saveFallback = (value: string) => {
    if (!clock) return;
    const chosen = value === NONE ? "" : value;
    const ref = cartRef(carts, chosen);
    void persist({
      ...clock,
      fallback_cart: ref.cart ?? "",
      fallback_cart_id: ref.cart_id,
    });
  };

  const inspector = clock ? (
    <Inspector
      selection={selection}
      clock={clock}
      carts={carts}
      categories={categories}
      busy={Boolean(busyLabel)}
      autoSave
      onSaveClock={(patch) => persist({ ...clock, ...patch }, "Heure type enregistrée")}
      onSavePosition={savePosition}
      onRemoveAnchor={async (minute) => {
        const saved = await persist(
          {
            ...clock,
            anchors: clock.anchors.filter((row) => row.minute !== minute),
          },
          "Coupure retirée",
          "Retrait de la coupure…",
        );
        if (saved) setSelection({ kind: "idle" });
      }}
    />
  ) : null;

  return (
    <>
      <div className={`ui-page ui-page--fill horloges-page${embedded ? " horloges-page--tab" : ""}`}>
        <PageHeader
          title="Heures types"
          description="Ce qui passe, dans l’ordre, puis les coupures pub. Le reste est dans Avancé."
        />

        <SessionGate
          loading={clocksRes.loading}
          error={clocksRes.error}
          ready={clocksRes.data != null}
          onRetry={reloadAll}
        >
          {clock ? (
            <div className="horloges-editor">
              <ClockList
                {...listProps}
                selectedId={clock.id}
                busy={Boolean(busyLabel)}
                onDelete={async (id) => {
                  setBusyLabel("Suppression de l’heure type…");
                  try {
                    await apiDelete(`/autodj/clocks/${id}.json`);
                    setClockId(null);
                    await clocksRes.reload();
                    show("Heure type supprimée");
                  } catch (caught) {
                    show(
                      caught instanceof ApiRequestError
                        ? caught.message
                        : "Suppression impossible.",
                    );
                  } finally {
                    setBusyLabel(null);
                  }
                }}
              />

              <main className="horloges-editor-main" aria-label={`Heure type ${clock.name}`}>
                <div className="horloges-editor-head">
                  <TextField.Root
                    className="horloges-editor-name"
                    aria-label="Nom de l’heure type"
                    value={name}
                    onChange={(event) => setName(event.target.value)}
                  />
                  {onAir ? (
                    <Badge color="green" variant="soft">
                      À l’antenne
                    </Badge>
                  ) : null}
                  <span className={`horloges-saved${saved ? " is-on" : ""}`}>
                    {saved ? <Check size={14} aria-hidden="true" /> : null}
                    {busyLabel ? "Enregistrement…" : saved ? "Enregistré" : ""}
                  </span>
                </div>

                <MotifStack
                  clock={clock}
                  carts={carts}
                  busy={Boolean(busyLabel)}
                  onRepair={(index) => setRepairIndex(index)}
                  onChangeCart={async (index, cart) => {
                    const ref = cartRef(carts, cart.title);
                    const motif = clock.motif.slice();
                    motif[index] = mergeClockPosition(motif[index], {
                      ...motif[index],
                      cart: ref.cart,
                      cart_id: ref.cart_id,
                      category: null,
                    });
                    await persist({ ...clock, motif });
                  }}
                  onRemove={async (index) => {
                    const didSave = await persist({
                      ...clock,
                      motif: clock.motif.filter((_, i) => i !== index),
                    });
                    if (didSave) setSelection({ kind: "idle" });
                  }}
                  onReorder={async (from, to) => {
                    if (from === to) return;
                    const motif = clock.motif.slice();
                    const [row] = motif.splice(from, 1);
                    motif.splice(to, 0, row);
                    const didSave = await persist({ ...clock, motif });
                    if (didSave) choose({ kind: "motif", index: to });
                  }}
                  onAddKind={async (kind) => {
                    const guessed =
                      kind === "jingle"
                        ? pickCart(carts, /jingle/i)
                        : kind === "pub"
                          ? pickPubCart(carts)
                          : pickProgCart(carts);
                    const step = emptyMotifStep({
                      kind,
                      cart: guessed?.title ?? null,
                      fallback: clock.fallback_cart,
                    });
                    if (guessed) step.cart_id = guessed.id;
                    await persist({ ...clock, motif: [...clock.motif, step] });
                  }}
                  onSeedDefault={async () => {
                    const motif = defaultMotif(carts, categories, clock.fallback_cart);
                    if (!motif.length) {
                      show("Crée d’abord Jingles et Prog dans Sons.");
                      return;
                    }
                    await persist({ ...clock, motif });
                  }}
                />

                <PubMinutes clock={clock} carts={carts} busy={Boolean(busyLabel)} onSave={persist} />

                <Panel className="horloges-fallback">
                  <h2 className="autodj-pubs-title">Si un bac est vide</h2>
                  <p className="autodj-pubs-copy">Jouer ce cart quand une étape n’a plus de titre.</p>
                  <SelectField
                    label="Jouer"
                    value={clock.fallback_cart || NONE}
                    disabled={Boolean(busyLabel)}
                    options={[
                      { value: NONE, label: "Aucun" },
                      ...(clock.fallback_cart && !carts.some((row) => row.title === clock.fallback_cart)
                        ? [{ value: clock.fallback_cart, label: clock.fallback_cart }]
                        : []),
                      ...carts.map((row) => ({ value: row.title, label: row.title })),
                    ]}
                    onValueChange={saveFallback}
                  />
                </Panel>

                <details className="horloges-advanced">
                  <summary>Avancé</summary>
                  <HourStrip
                    clock={clock}
                    selection={selection}
                    fillMotifIndex={motifIndex ?? lastMotif}
                    onSelect={onStrip}
                  />
                  {selection.kind === "anchor" || selection.kind === "new-anchor" ? inspector : null}
                  <ClockCartsPanel
                    clock={clock}
                    carts={carts}
                    busy={Boolean(busyLabel)}
                    onAdd={() => setAddCartOpen(true)}
                  />
                </details>
              </main>
            </div>
          ) : (
            <div className="horloges-editor horloges-editor--empty">
              <ClockList
                {...listProps}
                clocks={[]}
                selectedId={null}
                usage={[]}
                onAirName=""
                busy={Boolean(busyLabel)}
              />
              <Panel className="horloges-empty-panel">
                <EmptyState
                  icon={Clock3}
                  title="Aucune heure type"
                  description="Crée une heure type, pose ce qui passe, puis les coupures à la minute."
                />
              </Panel>
            </div>
          )}
        </SessionGate>
      </div>
      <ProtoToast message={message} />
      <PutCartInClockDialog
        open={addCartOpen}
        onOpenChange={setAddCartOpen}
        clocks={clocks}
        slots={slots}
        carts={carts}
        fixedClock={clock}
        rundownClock={rundownRes.data?.clock}
        busy={Boolean(busyLabel)}
        onDone={async (text) => {
          show(text);
          await clocksRes.reload();
          await rundownRes.reload();
        }}
        onError={show}
      />
      <RepairClockCartDialog
        open={repairIndex != null && repairing != null}
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
          await clocksRes.reload();
          await rundownRes.reload();
          show("Cart réparé");
        }}
        onOpenCart={(id) => navigate(`/sons?id=${id}`)}
        onError={show}
      />
    </>
  );
}
