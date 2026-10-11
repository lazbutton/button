import { Badge } from "@radix-ui/themes";
import { Library, Music2 } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { CartInspector } from "../components/carts/CartInspector";
import { CartLibrary, type CartCreateExtra } from "../components/carts/CartLibrary";
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
import {
  apiDelete,
  apiPost,
  apiPostJson,
  apiPut,
  ApiForbiddenError,
  ApiRequestError,
} from "../api/client";
import { bacFilterFor, cartMatchesBacFilter, type BacFilter } from "../api/cartFlags";
import { clockCartUsages, clockUsageLine } from "../api/clockMeta";
import { SessionGate } from "../api/SessionGate";
import type { Cart, CartMode, CartsResponse, ClocksResponse } from "../api/types";
import { useApiJson } from "../api/useApiJson";
import { EmptyState } from "../ui/EmptyState";
import { PageHeader } from "../ui/PageHeader";
import { Panel } from "../ui/Panel";
import "../styles/pages/carts.css";

const CREATE_MODES: { value: CartMode; label: string }[] = [
  { value: "playlist_loop", label: "Boucle" },
  { value: "random", label: "Aléatoire" },
  { value: "playlist", label: "Une fois" },
  { value: "relay", label: "Relais" },
];

const FILTERS = new Set<BacFilter>(["tous", "fichiers", "habillage", "relais"]);

function readFilter(raw: string | null): BacFilter {
  return raw && FILTERS.has(raw as BacFilter) ? (raw as BacFilter) : "tous";
}

const EMPTY_COPY: Record<BacFilter, { title: string; description: string }> = {
  tous: {
    title: "Premier bac",
    description: "Crée un bac de sons, glisse des fichiers, puis accroche-le dans Programmation.",
  },
  fichiers: {
    title: "Aucun bac de fichiers",
    description: "Les bacs de fichiers et d’habillage apparaissent ici. Les relais sont à part.",
  },
  habillage: {
    title: "Aucun habillage",
    description: "Crée un bac ici : son dossier de banque sera 30-habillage/jingles.",
  },
  relais: {
    title: "Aucun relais",
    description: "Crée un relais avec l’adresse du flux partenaire et une durée max.",
  },
};

export function CartsPage() {
  const { data, setData, error, loading, reload } = useApiJson<CartsResponse>("/carts.json");
  const clocksRes = useApiJson<ClocksResponse>("/autodj/clocks.json");
  const { message, show } = useProtoToast();
  const [params, setParams] = useSearchParams();
  const [cartId, setCartId] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [importProgress, setImportProgress] = useState<CartImportProgress | null>(null);
  const snappedId = useRef<string | null>(null);
  const filter = readFilter(params.get("filtre"));
  const all = data?.carts ?? [];
  const carts = all.filter((item) => cartMatchesBacFilter(item, filter));
  const clocks = clocksRes.data?.clocks ?? [];
  const cart = carts.find((item) => item.id === cartId) ?? null;
  const soundCount = carts.reduce((total, item) => total + item.sounds.length, 0);
  const clockUsage = useMemo(() => {
    const map: Record<number, string> = {};
    for (const item of carts) {
      map[item.id] = clockUsageLine(clockCartUsages(clocks, item));
    }
    return map;
  }, [carts, clocks]);
  const emptyCopy = all.length === 0 ? EMPTY_COPY.tous : EMPTY_COPY[filter];
  const defaultMode: CartMode = filter === "relais" ? "relay" : "playlist_loop";

  const writeParams = (mutate: (next: URLSearchParams) => void) => {
    const next = new URLSearchParams(params);
    mutate(next);
    setParams(next, { replace: true });
  };

  const selectCart = (id: number) => {
    snappedId.current = String(id);
    setCartId(id);
    if (params.get("id") === String(id)) return;
    writeParams((next) => next.set("id", String(id)));
  };

  const setFilter = (nextFilter: BacFilter) => {
    const pool = all.filter((item) => cartMatchesBacFilter(item, nextFilter));
    const keep = pool.some((item) => item.id === cartId);
    writeParams((next) => {
      if (nextFilter === "tous") next.delete("filtre");
      else next.set("filtre", nextFilter);
      if (!keep && pool[0]) {
        snappedId.current = String(pool[0].id);
        next.set("id", String(pool[0].id));
      }
    });
    if (!keep && pool[0]) setCartId(pool[0].id);
  };

  useEffect(() => {
    const raw = params.get("id");
    if (!raw || !all.length || snappedId.current === raw) return;
    const id = Number(raw);
    const target = all.find((item) => item.id === id);
    if (!target) return;
    snappedId.current = raw;
    if (!cartMatchesBacFilter(target, filter)) {
      writeParams((next) => next.set("filtre", bacFilterFor(target)));
    }
    setCartId(id);
  }, [params, all, filter]);

  useEffect(() => {
    const raw = params.get("id");
    const requested = raw ? all.find((item) => item.id === Number(raw)) : undefined;
    if (requested && !carts.some((item) => item.id === requested.id)) return;
    if (cartId != null && carts.some((item) => item.id === cartId)) return;
    if (carts[0]) setCartId(carts[0].id);
  }, [cartId, carts, all, params]);

  const putCart = (next: Cart) => {
    selectCart(next.id);
    setData((prev) => {
      const merged = mergeImportedCart(
        prev?.carts.find((item) => item.id === next.id),
        next,
      );
      if (!prev) return { carts: [merged] };
      const exists = prev.carts.some((item) => item.id === merged.id);
      return {
        carts: exists
          ? prev.carts.map((item) => (item.id === merged.id ? merged : item))
          : [...prev.carts, merged],
      };
    });
  };

  const fail = (caught: unknown, fallback: string) => {
    if (caught instanceof ApiForbiddenError) show("Il faut le rôle Programmateur pour modifier les bacs.");
    else show(caught instanceof ApiRequestError ? caught.message : fallback);
  };

  const importAudio = async (targetId: number, collect: () => Promise<File[]>) => {
    if (importProgress) return;
    selectCart(targetId);
    setImportProgress({ cartId: targetId, phase: "reading", done: 0, total: 0, current: "" });
    try {
      const files = await collect();
      if (!files.length) {
        show("Aucun fichier audio.");
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
        (info) => {
          setImportProgress({ cartId: targetId, phase: "uploading", ...info });
        },
        putCart,
      );
      putCart(next);
      show(files.length === 1 ? "1 son ajouté" : `${files.length} sons ajoutés`);
    } catch (caught) {
      fail(caught, "Ajout impossible.");
    } finally {
      setImportProgress(null);
    }
  };

  const attachBank = async (targetId: number, folders: string[]) => {
    if (importProgress || !folders.length) return;
    selectCart(targetId);
    setImportProgress({
      cartId: targetId,
      phase: "uploading",
      done: 0,
      total: folders.length,
      current: folders[0],
    });
    try {
      const payload = await attachBankFolders(targetId, folders);
      putCart(payload.cart);
      const added = payload.cart.sounds.length;
      show(added === 1 ? "1 son lié (sans copie)" : `${added} sons liés (sans copie)`);
    } catch (caught) {
      fail(caught, "Liaison impossible.");
    } finally {
      setImportProgress(null);
    }
  };

  const createCart = async (title: string, mode: CartMode, extra?: CartCreateExtra) => {
    const body: Record<string, unknown> = { title, mode, schedule_mode: "clock" };
    if (filter === "habillage" && mode !== "relay") body.bank_folder = "30-habillage/jingles";
    if (mode === "relay" && extra) {
      body.url = extra.url;
      body.max_duration = extra.max_duration;
    }
    const created = await apiPostJson<{ cart: Cart }>("/carts.json", body);
    const nextFilter = cartMatchesBacFilter(created.cart, filter) ? filter : bacFilterFor(created.cart);
    snappedId.current = String(created.cart.id);
    setCartId(created.cart.id);
    writeParams((next) => {
      next.set("id", String(created.cart.id));
      if (nextFilter === "tous") next.delete("filtre");
      else next.set("filtre", nextFilter);
    });
    await reload();
    show("Bac créé");
  };

  const saveCart = async (payload: Record<string, unknown>) => {
    if (!cart) return;
    setBusy(true);
    try {
      const saved = await apiPut<{ cart: Cart }>(`/carts/${cart.id}.json`, payload);
      selectCart(saved.cart.id);
      await reload();
      show("Bac enregistré");
    } catch (caught) {
      fail(caught, "Enregistrement impossible.");
    } finally {
      setBusy(false);
    }
  };

  const library = (
    <CartLibrary
      carts={carts}
      selectedId={cart?.id ?? null}
      clockUsage={clockUsage}
      importProgress={importProgress}
      onSelect={selectCart}
      onImport={importAudio}
      modes={CREATE_MODES}
      defaultMode={defaultMode}
      heading="Bacs"
      description="Un bac n’apparaît qu’une fois."
      filter={filter}
      onFilter={setFilter}
      onCreate={async (title, mode, extra) => {
        try {
          await createCart(title, mode, extra);
        } catch (caught) {
          fail(caught, "Création impossible.");
        }
      }}
    />
  );

  return (
    <>
      <div className="ui-page ui-page--fill app-carts-page">
        <PageHeader
          title="Bacs"
          actions={
            <>
              <Badge variant="soft" color="gray">
                <Library size={13} aria-hidden="true" />
                {carts.length} bac{carts.length === 1 ? "" : "s"}
              </Badge>
              <Badge variant="soft" color="gray">
                <Music2 size={13} aria-hidden="true" />
                {soundCount} son{soundCount === 1 ? "" : "s"}
              </Badge>
            </>
          }
        />
        <SessionGate loading={loading} error={error} ready={data != null} onRetry={() => void reload()}>
          {cart ? (
            <div className="app-carts">
              {library}
              <div className="app-carts-col app-carts-mid">
                {cart.mode === "relay" ? (
                  <RelayEditor cart={cart} busy={busy} onSave={saveCart} />
                ) : (
                  <SoundTable
                    cart={cart}
                    importProgress={importProgress}
                    onCart={putCart}
                    onError={show}
                    onImport={(collect) => importAudio(cart.id, collect)}
                    onAttachBank={(folders) => attachBank(cart.id, folders)}
                  />
                )}
              </div>
              <CartInspector
                cart={cart}
                busy={busy}
                onSave={saveCart}
                onDelete={async () => {
                  setBusy(true);
                  try {
                    await apiDelete(`/carts/${cart.id}.json`);
                    setCartId(null);
                    await reload();
                    show("Bac supprimé");
                  } catch (caught) {
                    fail(caught, "Suppression impossible.");
                  } finally {
                    setBusy(false);
                  }
                }}
                onFire={async () => {
                  try {
                    await apiPost(`/carts/${cart.id}/now.json`);
                    show("Bac envoyé à l’antenne");
                  } catch (caught) {
                    fail(caught, "Diffusion impossible.");
                  }
                }}
              />
            </div>
          ) : (
            <div className="app-carts app-carts--empty">
              {library}
              <Panel className="app-carts-empty-panel">
                <EmptyState icon={Music2} title={emptyCopy.title} description={emptyCopy.description} />
              </Panel>
            </div>
          )}
        </SessionGate>
      </div>
      <ProtoToast message={message} />
    </>
  );
}
