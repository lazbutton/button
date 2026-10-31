import { Button } from "@radix-ui/themes";
import { Library, Plus } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { BacHeader, type BacUsage } from "../components/carts/BacHeader";
import { CartInspector } from "../components/carts/CartInspector";
import { CartLibrary } from "../components/carts/CartLibrary";
import { CreateBacDialog, type CartCreateExtra } from "../components/carts/CreateBacDialog";
import { RelayEditor } from "../components/carts/RelayEditor";
import { SoundTable } from "../components/carts/SoundTable";
import { ProtoToast, useProtoToast } from "../components/ProtoToast";
import {
  attachBankFolders,
  fileLabel,
  importCartSounds,
  mergeImportedCart,
  type CartImportProgress,
} from "../api/cartSounds";
import { apiDelete, apiPost, apiPostJson, apiPut, ApiForbiddenError, ApiRequestError } from "../api/client";
import { BacBusyError, bacErrorText } from "../api/cartErrors";
import { bacFilterFor, cartMatchesBacFilter, type BacFilter } from "../api/cartFlags";
import { clockCartUsages, hourUsages, kindLabel } from "../api/clockMeta";
import { SessionGate } from "../api/SessionGate";
import { cartTotalSeconds, formatClock, formatSpan, relayHost } from "../api/soundsView";
import type { Cart, CartMode, CartsResponse, Clock, ClocksResponse } from "../api/types";
import { useApiJson } from "../api/useApiJson";
import type { ToastTone } from "../ui/AppToast";
import "../styles/pages/sons.css";

const FILTERS = new Set<BacFilter>(["tous", "fichiers", "habillage", "relais"]);
const INSPECTOR_KEY = "button.sons.reglages";

function readFilter(raw: string | null): BacFilter {
  return raw && FILTERS.has(raw as BacFilter) ? (raw as BacFilter) : "tous";
}

const WIDE = "(min-width: 1600px)";

/** Very wide screens show the settings beside the sounds and remember it; others open them on demand. */
function readInspector(): boolean {
  if (!window.matchMedia(WIDE).matches) return false;
  try {
    return window.localStorage.getItem(INSPECTOR_KEY) !== "0";
  } catch {
    return true;
  }
}

function writeInspector(open: boolean) {
  if (!window.matchMedia(WIDE).matches) return;
  try {
    window.localStorage.setItem(INSPECTOR_KEY, open ? "1" : "0");
  } catch {
    // Nothing to keep: the panel still opens and closes.
  }
}

/** Where the clocks use a bac. A clock that points at it blocks its deletion. */
function bacUsage(clocks: Clock[], cart: Cart): BacUsage {
  const usages = clockCartUsages(clocks, cart);
  const inHour = hourUsages(usages);
  const positionFallback = clocks.some((clock) =>
    [...clock.motif, ...clock.anchors].some((step) => step.fallback_cart_id === cart.id),
  );
  // One line per heure type: « Jour habillé · Jingle #1, Jingle :00, secours d'horloge ».
  const byClock = new Map<string, string[]>();
  for (const usage of usages) {
    const where = usage.label.startsWith(`${usage.clockName} · `)
      ? usage.label.slice(usage.clockName.length + 3)
      : usage.label;
    byClock.set(usage.clockName, [...(byClock.get(usage.clockName) ?? []), where]);
  }
  const lines = [...byClock].map(([name, where]) => `${name} · ${where.join(", ")}`);
  if (positionFallback) lines.push("Secours d'une position d'horloge");
  const inClock = usages.length > 0 || positionFallback;
  if (inHour.length) {
    const roles = [...new Set(inHour.map((usage) => (usage.kind === "secours" ? "secours" : kindLabel(usage.kind))))];
    const clockCount = new Set(inHour.map((usage) => usage.clockId)).size;
    return {
      programmed: true,
      inClock,
      label: "Auto-DJ",
      detail: `${roles.join(", ")} · ${clockCount} heure${clockCount === 1 ? "" : "s"} type${clockCount === 1 ? "" : "s"}`,
      lines,
    };
  }
  if (inClock) {
    return { programmed: false, inClock, label: "Secours", detail: "Joué seulement en secours d'horloge", lines };
  }
  return { programmed: false, inClock, label: "Hors Auto-DJ", detail: "Aucune horloge ne joue ce bac", lines };
}

export function CartsPage() {
  const { data, setData, error, loading, reload } = useApiJson<CartsResponse>("/carts.json");
  const clocksRes = useApiJson<ClocksResponse>("/autodj/clocks.json");
  const { message, show, dismiss } = useProtoToast();
  const [params, setParams] = useSearchParams();
  const [busy, setBusy] = useState(false);
  const [firing, setFiring] = useState(false);
  const [importProgress, setImportProgress] = useState<CartImportProgress | null>(null);
  const [view, setView] = useState<"list" | "detail">(() => (params.get("id") ? "detail" : "list"));
  const [inspectorOpen, setInspectorOpen] = useState(readInspector);
  const missingShown = useRef<string | null>(null);

  const all = useMemo(() => data?.carts ?? [], [data]);
  const clocks = useMemo(() => clocksRes.data?.clocks ?? [], [clocksRes.data]);
  const rawId = params.get("id");
  const requested = rawId ? (all.find((item) => item.id === Number(rawId)) ?? null) : null;
  const askedFilter = readFilter(params.get("filtre"));
  // A link to a bac hidden by the filter widens the filter instead of losing the bac.
  const filter: BacFilter =
    requested && !cartMatchesBacFilter(requested, askedFilter) ? bacFilterFor(requested) : askedFilter;
  const carts = useMemo(() => all.filter((item) => cartMatchesBacFilter(item, filter)), [all, filter]);
  const cart = requested ?? carts[0] ?? null;

  const usage = useMemo(() => {
    const map: Record<number, BacUsage> = {};
    for (const item of all) map[item.id] = bacUsage(clocks, item);
    return map;
  }, [all, clocks]);

  const writeParams = (mutate: (next: URLSearchParams) => void) => {
    setParams(
      (current) => {
        const next = new URLSearchParams(current);
        mutate(next);
        return next;
      },
      { replace: true },
    );
  };

  useEffect(() => {
    if (filter === askedFilter) return;
    writeParams((next) => next.set("filtre", filter));
  }, [filter, askedFilter]);

  useEffect(() => {
    if (!data || !rawId || requested || missingShown.current === rawId) return;
    missingShown.current = rawId;
    show("Ce bac n'existe plus : il a peut-être été supprimé.", "info");
    writeParams((next) => next.delete("id"));
  }, [data, rawId, requested]);

  // When the settings are a drawer, Escape closes them, unless a menu or dialog is open above.
  useEffect(() => {
    if (!inspectorOpen) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      const panel = document.querySelector(".bacs-inspector");
      if (!panel || getComputedStyle(panel).position !== "absolute") return;
      if (document.querySelector("[data-radix-popper-content-wrapper], .rt-DialogContent")) return;
      setInspectorOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [inspectorOpen]);

  const notify = (text: string, tone?: ToastTone) => show(text, tone);

  const fail = (caught: unknown, fallback: string) => show(bacErrorText(caught, fallback), "error");

  const selectCart = (id: number) => {
    setView("detail");
    if (params.get("id") === String(id)) return;
    writeParams((next) => next.set("id", String(id)));
  };

  const setFilter = (nextFilter: BacFilter) => {
    const pool = all.filter((item) => cartMatchesBacFilter(item, nextFilter));
    const keep = cart != null && pool.some((item) => item.id === cart.id);
    writeParams((next) => {
      if (nextFilter === "tous") next.delete("filtre");
      else next.set("filtre", nextFilter);
      if (!keep) next.delete("id");
    });
  };

  const toggleInspector = () => {
    writeInspector(!inspectorOpen);
    setInspectorOpen(!inspectorOpen);
  };

  const putCart = (next: Cart) => {
    setData((prev) => {
      const merged = mergeImportedCart(
        prev?.carts.find((item) => item.id === next.id),
        next,
      );
      if (!prev) return { carts: [merged] };
      const exists = prev.carts.some((item) => item.id === merged.id);
      return {
        carts: exists ? prev.carts.map((item) => (item.id === merged.id ? merged : item)) : [...prev.carts, merged],
      };
    });
  };

  const importAudio = async (targetId: number, collect: () => Promise<File[]>) => {
    if (importProgress) {
      fail(new BacBusyError(), "");
      return;
    }
    selectCart(targetId);
    setImportProgress({ cartId: targetId, phase: "reading", done: 0, total: 0, current: "" });
    try {
      const files = await collect();
      if (!files.length) {
        show("Aucun fichier audio dans ce dépôt.", "error");
        return;
      }
      setImportProgress({
        cartId: targetId,
        phase: "uploading",
        done: 0,
        total: files.length,
        current: fileLabel(files[0].name),
      });
      const next = await importCartSounds(
        targetId,
        files,
        (info) => setImportProgress({ cartId: targetId, phase: "uploading", ...info }),
        putCart,
      );
      putCart(next);
      show(files.length === 1 ? "1 son ajouté" : `${files.length} sons ajoutés`, "success");
    } catch (caught) {
      fail(caught, "Ajout impossible.");
    } finally {
      setImportProgress(null);
    }
  };

  const attachBank = async (targetId: number, folders: string[]) => {
    if (importProgress) throw new BacBusyError();
    if (!folders.length) return;
    const before = all.find((item) => item.id === targetId)?.sounds.length ?? 0;
    setImportProgress({ cartId: targetId, phase: "uploading", done: 0, total: folders.length, current: folders[0] });
    try {
      const payload = await attachBankFolders(targetId, folders);
      putCart(payload.cart);
      const added = Math.max(0, payload.cart.sounds.length - before);
      show(
        added === 0
          ? "Dossier lié : ses sons étaient déjà dans le bac"
          : added === 1
            ? "1 son lié, sans copie"
            : `${added} sons liés, sans copie`,
        "success",
      );
    } finally {
      setImportProgress(null);
    }
  };

  const createCart = async (title: string, mode: CartMode, extra: CartCreateExtra) => {
    const body: Record<string, unknown> = { title, mode, schedule_mode: "clock" };
    if (mode === "relay") {
      body.url = extra.url;
      body.max_duration = extra.max_duration;
    } else if (extra.bank_folder) {
      body.bank_folder = extra.bank_folder;
    }
    // A failure stays in the dialog, which says why.
    const created = await apiPostJson<{ cart: Cart }>("/carts.json", body);
    await reload();
    writeParams((next) => {
      next.set("id", String(created.cart.id));
      if (!cartMatchesBacFilter(created.cart, filter)) next.set("filtre", bacFilterFor(created.cart));
    });
    setView("detail");
    show(`« ${created.cart.title} » créé`, "success");
  };

  const saveCart = async (payload: Record<string, unknown>) => {
    if (!cart) return;
    setBusy(true);
    try {
      const saved = await apiPut<{ cart: Cart }>(`/carts/${cart.id}.json`, payload);
      putCart(saved.cart);
      await reload();
      show("Bac enregistré", "success");
    } catch (caught) {
      fail(caught, "Enregistrement impossible.");
    } finally {
      setBusy(false);
    }
  };

  const deleteCart = async () => {
    if (!cart) return;
    setBusy(true);
    try {
      await apiDelete(`/carts/${cart.id}.json`);
      writeParams((next) => next.delete("id"));
      setView("list");
      await reload();
      show(`« ${cart.title} » supprimé`, "success");
    } catch (caught) {
      if (caught instanceof ApiRequestError && caught.status === 409) {
        show("Une horloge utilise ce bac : retire-le d'abord dans Programmation.", "error");
      } else {
        fail(caught, "Suppression impossible.");
      }
    } finally {
      setBusy(false);
    }
  };

  const fireCart = async () => {
    if (!cart) return;
    setFiring(true);
    try {
      await apiPost(`/carts/${cart.id}/now.json`);
      show(`« ${cart.title} » envoyé à l'antenne`, "success");
    } catch (caught) {
      if (caught instanceof ApiForbiddenError) show("Il faut le droit Antenne pour diffuser.", "error");
      else show(caught instanceof ApiRequestError ? caught.message : "Diffusion impossible.", "error");
    } finally {
      setFiring(false);
    }
  };

  const facts = cart ? bacFacts(cart) : null;

  return (
    <div className="bacs-page">
      <SessionGate loading={loading} error={error} ready={data != null} onRetry={() => void reload()}>
        {all.length === 0 ? (
          <FirstBac onCreate={createCart} />
        ) : (
          <div className="bacs" data-view={view} data-inspector={inspectorOpen && cart ? "open" : "closed"}>
            <CartLibrary
              all={all}
              carts={carts}
              filter={filter}
              onFilter={setFilter}
              selectedId={cart?.id ?? null}
              usage={usage}
              importProgress={importProgress}
              onSelect={selectCart}
              onImport={importAudio}
              onCreate={createCart}
            />
            {cart ? (
              <section className="bacs-main" aria-label={cart.title}>
                <BacHeader
                  cart={cart}
                  usage={usage[cart.id]}
                  facts={facts}
                  inspectorOpen={inspectorOpen}
                  onToggleInspector={toggleInspector}
                  onBack={() => setView("list")}
                  onFire={() => void fireCart()}
                  firing={firing}
                />
                {cart.mode === "relay" ? (
                  <RelayEditor cart={cart} busy={busy} onSave={saveCart} />
                ) : (
                  <SoundTable
                    cart={cart}
                    importProgress={importProgress}
                    onCart={putCart}
                    notify={notify}
                    onImport={(collect) => importAudio(cart.id, collect)}
                    onAttachBank={(folders) => attachBank(cart.id, folders)}
                  />
                )}
              </section>
            ) : (
              <EmptyKind filter={filter} taken={all.map((item) => item.title)} onCreate={createCart} />
            )}
            {cart && inspectorOpen ? (
              <>
                <button
                  type="button"
                  className="bacs-scrim"
                  aria-label="Fermer les réglages"
                  tabIndex={-1}
                  onClick={toggleInspector}
                />
                <CartInspector
                  cart={cart}
                  busy={busy}
                  usage={usage[cart.id]}
                  taken={all.filter((item) => item.id !== cart.id).map((item) => item.title)}
                  onClose={toggleInspector}
                  onSave={saveCart}
                  onDelete={deleteCart}
                />
              </>
            ) : null}
          </div>
        )}
      </SessionGate>
      <ProtoToast message={message} onDismiss={dismiss} />
    </div>
  );
}

function bacFacts(cart: Cart) {
  if (cart.mode === "relay") {
    return (
      <>
        <span>{relayHost(cart.url) || "Adresse à régler"}</span>
        <span>{cart.max_duration ? `${formatSpan(cart.max_duration)} max.` : "Durée à régler"}</span>
      </>
    );
  }
  const total = cart.sounds.length;
  const active = cart.sounds.filter((sound) => sound.active).length;
  return (
    <>
      <span>
        {total} son{total === 1 ? "" : "s"}
        {active < total ? ` · ${active} actif${active === 1 ? "" : "s"}` : ""}
      </span>
      {total ? <span title="Durée totale">{formatClock(cartTotalSeconds(cart))}</span> : null}
    </>
  );
}

const EMPTY_KIND: Record<Exclude<BacFilter, "tous">, { title: string; text: string }> = {
  fichiers: {
    title: "Aucun bac de fichiers",
    text: "Un bac de fichiers joue ses sons en boucle, au hasard, ou chacun une fois avant de reprendre.",
  },
  habillage: {
    title: "Aucun habillage",
    text: "Jingles, idents, virgules : leurs fichiers vivent dans 30-habillage, dans la banque.",
  },
  relais: { title: "Aucun relais", text: "Un relais diffuse le flux d'une radio partenaire, pour une durée bornée." },
};

function EmptyKind({
  filter,
  taken,
  onCreate,
}: {
  filter: BacFilter;
  taken: string[];
  onCreate: (title: string, mode: CartMode, extra: CartCreateExtra) => Promise<void>;
}) {
  const kind = filter === "tous" ? "fichiers" : filter;
  const copy = EMPTY_KIND[kind];
  return (
    <section className="bacs-main bacs-main--empty">
      <div className="bacs-first">
        <h2>{copy.title}</h2>
        <p>{copy.text}</p>
        <CreateBacDialog
          defaultKind={kind}
          taken={taken}
          onCreate={onCreate}
          trigger={
            <Button size="2" variant="soft">
              <Plus className="ui-button-icon" />
              {kind === "relais" ? "Créer un relais" : "Créer un bac"}
            </Button>
          }
        />
      </div>
    </section>
  );
}

function FirstBac({
  onCreate,
}: {
  onCreate: (title: string, mode: CartMode, extra: CartCreateExtra) => Promise<void>;
}) {
  return (
    <div className="bacs-first">
      <span className="bacs-first-icon" aria-hidden="true">
        <Library size={22} />
      </span>
      <h2>Premier bac</h2>
      <p>
        Un bac regroupe des sons : jingles, pubs, chroniques. Crée-le, ajoute des fichiers, puis accroche-le à une heure
        type dans Programmation.
      </p>
      <CreateBacDialog
        defaultKind="fichiers"
        onCreate={onCreate}
        trigger={
          <Button size="2" highContrast>
            <Plus className="ui-button-icon" />
            Créer un bac
          </Button>
        }
      />
    </div>
  );
}
