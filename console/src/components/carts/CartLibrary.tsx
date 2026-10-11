import { Button, Dialog, TextField } from "@radix-ui/themes";
import {
  ListMusic,
  Plus,
  Repeat2,
  Search,
  SearchX,
  Shuffle,
  type LucideIcon,
} from "lucide-react";
import { useMemo, useState } from "react";
import { filesFromDataTransfer, isFileDrag } from "../../api/audioDrop";
import type { BacFilter } from "../../api/cartFlags";
import { isHabillageCart } from "../../api/cartFlags";
import { MODE_HELP, MODE_LABELS, relayUrlOk } from "../../api/cartMeta";
import type { CartImportProgress } from "../../api/cartSounds";
import type { Cart, CartMode } from "../../api/types";
import { EmptyState } from "../../ui/EmptyState";
import { FormField, SelectField } from "../../ui/FormField";
import { Panel, SectionHeader } from "../../ui/Panel";

const BAC_FILTERS: { id: BacFilter; label: string }[] = [
  { id: "tous", label: "Tous" },
  { id: "fichiers", label: "Fichiers" },
  { id: "habillage", label: "Habillage" },
  { id: "relais", label: "Relais" },
];

const PLAY_MODES: { value: CartMode; label: string }[] = [
  { value: "playlist_loop", label: "Boucle" },
  { value: "random", label: "Aléatoire" },
  { value: "playlist", label: "Une fois" },
  { value: "relay", label: "Relais" },
];

const CART_ICONS: Record<CartMode, LucideIcon> = {
  playlist: ListMusic,
  playlist_loop: Repeat2,
  random: Shuffle,
  relay: Repeat2,
};

export type CartCreateExtra = { url: string; max_duration: number };

export function CartLibrary({
  carts,
  selectedId,
  importProgress,
  onSelect,
  onCreate,
  onImport,
  clockUsage,
  modes = PLAY_MODES,
  defaultMode = "playlist_loop",
  heading = "Bacs",
  description = "Un bac n’apparaît qu’une fois. Le filtre sépare les types.",
  filter = "tous",
  onFilter,
}: {
  carts: Cart[];
  selectedId: number | null;
  importProgress?: CartImportProgress | null;
  onSelect: (id: number) => void;
  onCreate: (title: string, mode: CartMode, extra?: CartCreateExtra) => Promise<void>;
  onImport?: (cartId: number, collect: () => Promise<File[]>) => Promise<void>;
  clockUsage?: Record<number, string>;
  modes?: { value: CartMode; label: string }[];
  defaultMode?: CartMode;
  heading?: string;
  description?: string;
  filter?: BacFilter;
  onFilter?: (filter: BacFilter) => void;
}) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [mode, setMode] = useState<CartMode>(defaultMode);
  const [url, setUrl] = useState("");
  const [maxDuration, setMaxDuration] = useState("1800");
  const [busy, setBusy] = useState(false);
  const [dropId, setDropId] = useState<number | null>(null);

  const visible = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase("fr");
    if (!needle) return carts;
    return carts.filter((cart) => cart.title.toLocaleLowerCase("fr").includes(needle));
  }, [carts, query]);

  return (
    <Panel as="aside" padded={false} className="app-carts-col app-carts-lib">
      <div className="app-carts-library-toolbar">
        <SectionHeader
          title={heading}
          count={carts.length}
          description={description}
          actions={
            <Dialog.Root
              open={open}
              onOpenChange={(next) => {
                setOpen(next);
                if (next) setMode(defaultMode);
              }}
            >
              <Dialog.Trigger>
                <Button size="1">
                  <Plus className="ui-button-icon" />
                  Nouveau
                </Button>
              </Dialog.Trigger>
              <Dialog.Content maxWidth="24rem" className="app-cart-dialog">
                <Dialog.Title>Nouveau bac</Dialog.Title>
                <Dialog.Description size="2" mb="3">
                  Un nom, et comment ça se lit.
                </Dialog.Description>
                <form
                  className="app-cart-create-form"
                  onSubmit={(event) => {
                    event.preventDefault();
                    const seconds = Number(maxDuration);
                    const relayReady =
                      mode !== "relay" || (relayUrlOk(url) && Number.isFinite(seconds) && seconds > 0);
                    if (busy || !title.trim() || !relayReady) return;
                    void (async () => {
                      setBusy(true);
                      try {
                        await onCreate(
                          title.trim(),
                          mode,
                          mode === "relay" ? { url: url.trim(), max_duration: seconds } : undefined,
                        );
                        setTitle("");
                        setUrl("");
                        setMaxDuration("1800");
                        setMode(defaultMode);
                        setOpen(false);
                      } finally {
                        setBusy(false);
                      }
                    })();
                  }}
                >
                  <FormField label="Titre">
                    <TextField.Root
                      className="ui-field-control"
                      value={title}
                      onChange={(event) => setTitle(event.target.value)}
                      placeholder="Jingles"
                      autoFocus
                    />
                  </FormField>
                  <SelectField
                    label="Mode"
                    value={mode}
                    options={modes}
                    onValueChange={(value) => setMode(value as CartMode)}
                    hint={MODE_HELP[mode]}
                  />
                  {mode === "relay" ? (
                    <>
                      <FormField
                        label="URL du flux"
                        hint="HTTP ou HTTPS, avec un chemin."
                      >
                        <TextField.Root
                          className="ui-field-control"
                          value={url}
                          placeholder="https://radio.exemple/flux.mp3"
                          onChange={(event) => setUrl(event.target.value)}
                        />
                      </FormField>
                      <FormField label="Durée max (secondes)" hint="Obligatoire.">
                        <TextField.Root
                          className="ui-field-control"
                          type="number"
                          min={1}
                          value={maxDuration}
                          onChange={(event) => setMaxDuration(event.target.value)}
                        />
                      </FormField>
                    </>
                  ) : null}
                  <div className="app-cart-dialog-actions">
                    <Dialog.Close>
                      <Button type="button" variant="soft" color="gray" disabled={busy}>
                        Annuler
                      </Button>
                    </Dialog.Close>
                    <Button
                      type="submit"
                      disabled={
                        busy ||
                        !title.trim() ||
                        (mode === "relay" &&
                          (!relayUrlOk(url) || !(Number(maxDuration) > 0)))
                      }
                    >
                      {busy ? "Création…" : "Créer le bac"}
                    </Button>
                  </div>
                </form>
              </Dialog.Content>
            </Dialog.Root>
          }
        />
        {onFilter ? (
          <div className="app-bac-filters" role="group" aria-label="Type de bac">
            {BAC_FILTERS.map((item) => (
              <button
                key={item.id}
                type="button"
                className={filter === item.id ? "is-on" : undefined}
                aria-pressed={filter === item.id}
                onClick={() => onFilter(item.id)}
              >
                {item.label}
              </button>
            ))}
          </div>
        ) : null}
        <TextField.Root
          size="1"
          placeholder="Rechercher un bac…"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          className="app-cart-search"
          aria-label="Rechercher un bac"
        >
          <TextField.Slot>
            <Search size={14} aria-hidden="true" />
          </TextField.Slot>
        </TextField.Root>
      </div>
      <div className="app-cart-list">
        {visible.map((cart) => {
          const active = cart.id === selectedId;
          const dropping = dropId === cart.id;
          const importing = importProgress?.cartId === cart.id;
          const Icon = CART_ICONS[cart.mode] ?? Repeat2;
          const soundLabel = `${cart.sounds.length} son${cart.sounds.length === 1 ? "" : "s"}`;
          return (
            <div
              key={cart.id}
              className={`app-cart-list-item${dropping ? " is-file-drop" : ""}${importing ? " is-importing" : ""}`}
              onDragOver={(event) => {
                if (!onImport || importProgress || !isFileDrag(event)) return;
                event.preventDefault();
                event.dataTransfer.dropEffect = "copy";
                setDropId(cart.id);
              }}
              onDragLeave={(event) => {
                const next = event.relatedTarget as Node | null;
                if (next && event.currentTarget.contains(next)) return;
                setDropId((id) => (id === cart.id ? null : id));
              }}
              onDrop={(event) => {
                if (!onImport || importProgress || !isFileDrag(event)) return;
                event.preventDefault();
                event.stopPropagation();
                const data = event.dataTransfer;
                setDropId(null);
                onSelect(cart.id);
                void onImport(cart.id, () => filesFromDataTransfer(data));
              }}
            >
              <button
                type="button"
                className={`app-cart-card${active ? " is-selected" : ""}`}
                aria-pressed={active}
                onClick={() => onSelect(cart.id)}
              >
                <span className="app-cart-card-icon" aria-hidden="true">
                  <Icon size={16} strokeWidth={1.75} />
                </span>
                <span className="app-cart-card-body">
                  <span className="app-cart-card-title">{cart.title}</span>
                  <span className="app-cart-card-meta">
                    {importing ? (
                      <span className="app-cart-card-import">
                        {importProgress.phase === "reading"
                          ? "Lecture des fichiers…"
                          : `Ajout ${importProgress.done} / ${importProgress.total}`}
                      </span>
                    ) : dropping ? (
                      <span className="app-cart-card-import">Relâchez pour ajouter ici</span>
                    ) : (
                      <>
                        <span>{soundLabel}</span>
                        <span>{cart.mode === "relay" ? "Relais" : isHabillageCart(cart) ? "Habillage" : "Fichiers"}</span>
                        <span className={clockUsage?.[cart.id]?.startsWith("pas dans") ? "app-cart-hour-miss" : "app-cart-hour-hit"}>
                          {clockUsage?.[cart.id] ?? "pas dans l’Auto-DJ"}
                        </span>
                      </>
                    )}
                  </span>
                </span>
                <span className="app-cart-card-mode">{MODE_LABELS[cart.mode]}</span>
              </button>
            </div>
          );
        })}
        {visible.length === 0 ? (
          <EmptyState
            icon={query.trim() ? SearchX : ListMusic}
            title={query.trim() ? "Aucun résultat" : "Aucun bac"}
            description={
              query.trim()
                ? "Essaie un autre nom."
                : "Crée un bac, puis ajoute les fichiers."
            }
          />
        ) : null}
      </div>
    </Panel>
  );
}
