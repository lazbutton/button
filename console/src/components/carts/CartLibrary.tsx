import { Button, Kbd, Select, TextField } from "@radix-ui/themes";
import { Plus, Search, SearchX } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { filesFromDataTransfer, isFileDrag } from "../../api/audioDrop";
import type { BacFilter } from "../../api/cartFlags";
import { MODE_LABELS } from "../../api/cartMeta";
import type { CartImportProgress } from "../../api/cartSounds";
import { fuzzyTitleMatch } from "../../api/fuzzyTitle";
import {
  bacCounts,
  bacKind,
  cartTotalSeconds,
  formatSpan,
  groupBacs,
  percentOf,
  relayHost,
  type BacKind,
} from "../../api/soundsView";
import type { Cart, CartMode } from "../../api/types";
import { MODE_ICONS } from "./bacIcons";
import type { BacUsage } from "./BacHeader";
import { CreateBacDialog, type CartCreateExtra } from "./CreateBacDialog";

const FILTERS: { id: BacFilter; label: string }[] = [
  { id: "tous", label: "Tous" },
  { id: "fichiers", label: "Fichiers" },
  { id: "habillage", label: "Habillage" },
  { id: "relais", label: "Relais" },
];

function isTyping(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName);
}

export function CartLibrary({
  all,
  carts,
  filter,
  onFilter,
  selectedId,
  usage,
  importProgress,
  onSelect,
  onImport,
  onCreate,
}: {
  all: Cart[];
  carts: Cart[];
  filter: BacFilter;
  onFilter: (filter: BacFilter) => void;
  selectedId: number | null;
  usage: Record<number, BacUsage>;
  importProgress: CartImportProgress | null;
  onSelect: (id: number) => void;
  onImport: (cartId: number, collect: () => Promise<File[]>) => Promise<void>;
  onCreate: (title: string, mode: CartMode, extra: CartCreateExtra) => Promise<void>;
}) {
  const [query, setQuery] = useState("");
  const [dropId, setDropId] = useState<number | null>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const counts = useMemo(() => bacCounts(all), [all]);
  const searching = Boolean(query.trim());

  const visible = useMemo(
    () => (searching ? carts.filter((cart) => fuzzyTitleMatch(cart.title, query)) : carts),
    [carts, query, searching],
  );
  const groups = useMemo(
    () =>
      filter === "tous" && !searching
        ? groupBacs(visible)
        : [{ kind: null as BacKind | null, label: "", carts: visible }],
    [filter, searching, visible],
  );
  const flat = useMemo(() => groups.flatMap((group) => group.carts), [groups]);

  useEffect(() => {
    const onKey = (event: globalThis.KeyboardEvent) => {
      if (event.key !== "/" || event.metaKey || event.ctrlKey || isTyping(event.target)) return;
      if (!searchRef.current || searchRef.current.offsetParent === null) return;
      event.preventDefault();
      searchRef.current.focus();
      searchRef.current.select();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const move = (event: KeyboardEvent<HTMLDivElement>) => {
    const keys = ["ArrowDown", "ArrowUp", "Home", "End"];
    if (!keys.includes(event.key) || !flat.length) return;
    event.preventDefault();
    const index = flat.findIndex((cart) => cart.id === selectedId);
    let next = index < 0 ? 0 : index;
    if (event.key === "ArrowDown") next = Math.min(flat.length - 1, next + 1);
    if (event.key === "ArrowUp") next = Math.max(0, next - 1);
    if (event.key === "Home") next = 0;
    if (event.key === "End") next = flat.length - 1;
    const target = flat[next];
    onSelect(target.id);
    requestAnimationFrame(() => {
      listRef.current?.querySelector<HTMLElement>(`[data-cart="${target.id}"]`)?.focus();
    });
  };

  return (
    <aside className="bacs-lib" aria-label="Bacs">
      <header className="bacs-lib-head">
        <h2 className="bacs-lib-title">
          Bacs <span className="bacs-count">{all.length}</span>
        </h2>
        <CreateBacDialog
          defaultKind={filter === "tous" ? "fichiers" : filter}
          taken={all.map((cart) => cart.title)}
          onCreate={onCreate}
          trigger={
            <Button size="1" highContrast>
              <Plus className="ui-button-icon" />
              Nouveau
            </Button>
          }
        />
      </header>
      <div className="bacs-lib-tools">
        <TextField.Root
          ref={searchRef}
          size="2"
          className="bacs-search"
          placeholder="Rechercher"
          value={query}
          aria-label="Rechercher un bac"
          onChange={(event) => setQuery(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Escape") {
              setQuery("");
              event.currentTarget.blur();
            }
            if (event.key === "ArrowDown") {
              event.preventDefault();
              listRef.current?.querySelector<HTMLElement>("[data-cart]")?.focus();
            }
          }}
        >
          <TextField.Slot>
            <Search size={15} aria-hidden="true" />
          </TextField.Slot>
          <TextField.Slot side="right">
            <Kbd size="1">/</Kbd>
          </TextField.Slot>
        </TextField.Root>
        <Select.Root size="2" value={filter} onValueChange={(value) => onFilter(value as BacFilter)}>
          <Select.Trigger variant="soft" color="gray" className="bacs-filter" aria-label="Type de bac" />
          <Select.Content variant="soft" position="popper" align="end" className="bacs-filter-menu">
            {FILTERS.map((item) => (
              <Select.Item key={item.id} value={item.id}>
                {item.label}
                <span className="bacs-filter-count">{counts[item.id]}</span>
              </Select.Item>
            ))}
          </Select.Content>
        </Select.Root>
      </div>
      <div className="bacs-lib-list" ref={listRef} role="listbox" aria-label="Bacs" onKeyDown={move}>
        {groups.map((group) => (
          <div key={group.kind ?? "liste"} className="bacs-lib-group" role="presentation">
            {group.kind ? (
              <p className="bacs-lib-group-label" role="presentation">
                {group.label}
                <span>{group.carts.length}</span>
              </p>
            ) : null}
            {group.carts.map((cart) => (
              <BacRow
                key={cart.id}
                cart={cart}
                usage={usage[cart.id]}
                selected={cart.id === selectedId}
                dropping={dropId === cart.id}
                importProgress={importProgress?.cartId === cart.id ? importProgress : null}
                onSelect={() => onSelect(cart.id)}
                onDragState={(over) => setDropId((id) => (over ? cart.id : id === cart.id ? null : id))}
                onDropFiles={(collect) => {
                  if (importProgress || cart.mode === "relay") return;
                  onSelect(cart.id);
                  void onImport(cart.id, collect);
                }}
              />
            ))}
          </div>
        ))}
        {flat.length === 0 ? (
          <div className="bacs-lib-empty">
            <SearchX size={18} aria-hidden="true" />
            <p>{searching ? `Aucun bac ne correspond à « ${query.trim()} ».` : "Aucun bac de ce type."}</p>
            {searching ? (
              <Button size="1" variant="soft" color="gray" onClick={() => setQuery("")}>
                Effacer la recherche
              </Button>
            ) : null}
          </div>
        ) : null}
      </div>
    </aside>
  );
}

function BacRow({
  cart,
  usage,
  selected,
  dropping,
  importProgress,
  onSelect,
  onDragState,
  onDropFiles,
}: {
  cart: Cart;
  usage?: BacUsage;
  selected: boolean;
  dropping: boolean;
  importProgress: CartImportProgress | null;
  onSelect: () => void;
  onDragState: (over: boolean) => void;
  onDropFiles: (collect: () => Promise<File[]>) => void;
}) {
  const kind = bacKind(cart);
  const Icon = MODE_ICONS[cart.mode];
  const relay = cart.mode === "relay";
  const importing = importProgress != null;
  const meta = relay ? relayHost(cart.url) || "Adresse à régler" : MODE_LABELS[cart.mode];
  const percent = importing ? percentOf(importProgress.done, importProgress.total) : 0;

  return (
    <button
      type="button"
      role="option"
      aria-selected={selected}
      tabIndex={selected ? 0 : -1}
      data-cart={cart.id}
      className={["bacs-row", selected ? "is-selected" : "", dropping ? "is-drop" : "", importing ? "is-importing" : ""]
        .filter(Boolean)
        .join(" ")}
      onClick={onSelect}
      onDragOver={(event) => {
        if (relay || !isFileDrag(event)) return;
        event.preventDefault();
        event.dataTransfer.dropEffect = "copy";
        onDragState(true);
      }}
      onDragLeave={(event) => {
        const next = event.relatedTarget as Node | null;
        if (next && event.currentTarget.contains(next)) return;
        onDragState(false);
      }}
      onDrop={(event) => {
        if (relay || !isFileDrag(event)) return;
        event.preventDefault();
        event.stopPropagation();
        onDragState(false);
        const data = event.dataTransfer;
        onDropFiles(() => filesFromDataTransfer(data));
      }}
    >
      <span className={`bacs-tile is-${kind}`} aria-hidden="true">
        <Icon size={15} strokeWidth={1.75} />
      </span>
      <span className="bacs-row-main">
        <span className="bacs-row-title">{cart.title}</span>
        <span className="bacs-row-meta">
          {dropping ? (
            <span className="bacs-row-hint">Déposer pour ajouter ici</span>
          ) : importing ? (
            <span className="bacs-row-hint">
              {importProgress.phase === "reading"
                ? "Lecture des fichiers…"
                : `Ajout ${importProgress.done} / ${importProgress.total}`}
            </span>
          ) : (
            <>
              <span>{meta}</span>
              {usage ? (
                <span className={`bacs-usage${usage.programmed ? " is-on" : ""}`} title={usage.detail || undefined}>
                  <i aria-hidden="true" />
                  {usage.label}
                </span>
              ) : null}
              {cart.ident_pads ? <span className="bacs-tag">Pads</span> : null}
            </>
          )}
        </span>
      </span>
      <span className="bacs-row-side">
        {relay ? (
          <>
            <span className="bacs-row-num">{cart.max_duration ? formatSpan(cart.max_duration) : "—"}</span>
            <span className="bacs-row-sub">max.</span>
          </>
        ) : (
          <>
            <span className="bacs-row-num">{cart.sounds.length}</span>
            <span className="bacs-row-sub">{cart.sounds.length ? formatSpan(cartTotalSeconds(cart)) : "vide"}</span>
          </>
        )}
      </span>
      {importing ? (
        <span className="bacs-row-progress" aria-hidden="true">
          <i style={{ width: `${importProgress.phase === "reading" ? 8 : Math.max(4, percent)}%` }} />
        </span>
      ) : null}
    </button>
  );
}
