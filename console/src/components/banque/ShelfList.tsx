import { Button, TextField } from "@radix-ui/themes";
import { Library, Music, Plus, Search, SearchX } from "lucide-react";
import { useMemo, useRef, useState, type KeyboardEvent } from "react";
import { shelfFacts, type BankShelf } from "../../api/bankContent";
import { filterDestinations } from "../../api/soundsView";

/**
 * Rotation, then every collection: the left column of the bank's content.
 * A list one walks with the arrows, as the list of bacs.
 */
export function ShelfList({
  shelves,
  selectedId,
  onSelect,
  onCreate,
}: {
  shelves: BankShelf[];
  selectedId: string;
  onSelect: (id: string) => void;
  /** Opens the creation dialog, prefilled with what was typed. Admin only. */
  onCreate?: (label: string) => void;
}) {
  const [query, setQuery] = useState("");
  const listRef = useRef<HTMLDivElement>(null);
  const searching = Boolean(query.trim());
  const visible = useMemo(
    () => (searching ? (filterDestinations(shelves, query) as BankShelf[]) : shelves),
    [query, searching, shelves],
  );
  const rotation = visible.filter((shelf) => shelf.group === "rotation");
  const collections = visible.filter((shelf) => shelf.group !== "rotation");
  const total = shelves.filter((shelf) => shelf.group !== "rotation").length;

  const move = (event: KeyboardEvent<HTMLDivElement>) => {
    if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key) || !visible.length) return;
    event.preventDefault();
    const index = visible.findIndex((shelf) => shelf.id === selectedId);
    let next = index < 0 ? 0 : index;
    if (event.key === "ArrowDown") next = Math.min(visible.length - 1, next + 1);
    if (event.key === "ArrowUp") next = Math.max(0, next - 1);
    if (event.key === "Home") next = 0;
    if (event.key === "End") next = visible.length - 1;
    const target = visible[next];
    onSelect(target.id);
    requestAnimationFrame(() => {
      listRef.current?.querySelector<HTMLElement>(`[data-shelf="${CSS.escape(target.id)}"]`)?.focus();
    });
  };

  return (
    <aside className="bacs-lib" aria-label="Collections">
      <header className="bacs-lib-head">
        <h2 className="bacs-lib-title">
          Collections <span className="bacs-count">{total}</span>
        </h2>
        {onCreate ? (
          <Button size="1" highContrast onClick={() => onCreate(query.trim())}>
            <Plus className="ui-button-icon" />
            Nouvelle
          </Button>
        ) : null}
      </header>
      <div className="bacs-lib-tools">
        <TextField.Root
          size="2"
          className="bacs-search"
          placeholder="Rechercher"
          value={query}
          aria-label="Rechercher une collection"
          onChange={(event) => setQuery(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Escape") {
              setQuery("");
              event.currentTarget.blur();
            }
            if (event.key === "ArrowDown") {
              event.preventDefault();
              listRef.current?.querySelector<HTMLElement>("[data-shelf]")?.focus();
            }
          }}
        >
          <TextField.Slot>
            <Search size={15} aria-hidden="true" />
          </TextField.Slot>
        </TextField.Root>
      </div>
      <div className="bacs-lib-list">
        <div ref={listRef} role="listbox" aria-label="Collections" onKeyDown={move}>
          {rotation.map((shelf) => (
            <ShelfRow
              key={shelf.id}
              shelf={shelf}
              selected={shelf.id === selectedId}
              onSelect={() => onSelect(shelf.id)}
            />
          ))}
          {collections.length ? (
            <div className="bacs-lib-group" role="presentation">
              {!searching ? (
                <p className="bacs-lib-group-label" role="presentation">
                  Collections
                  <span>{collections.length}</span>
                </p>
              ) : null}
              {collections.map((shelf) => (
                <ShelfRow
                  key={shelf.id}
                  shelf={shelf}
                  selected={shelf.id === selectedId}
                  onSelect={() => onSelect(shelf.id)}
                />
              ))}
            </div>
          ) : null}
        </div>
        {searching && !visible.length ? (
          <div className="bacs-lib-empty">
            <SearchX size={18} aria-hidden="true" />
            <p>Aucune collection ne correspond à « {query.trim()} ».</p>
            {onCreate ? (
              <Button size="1" variant="soft" color="gray" onClick={() => onCreate(query.trim())}>
                Créer « {query.trim()} »
              </Button>
            ) : (
              <Button size="1" variant="soft" color="gray" onClick={() => setQuery("")}>
                Effacer la recherche
              </Button>
            )}
          </div>
        ) : null}
        {!searching && !total ? (
          <p className="banque-shelves-hint">
            {onCreate
              ? "Une collection range à part un fonds à programmer : concerts, émissions passées, une rotation de nuit."
              : "Pas encore de collection : un admin en crée une ici."}
          </p>
        ) : null}
      </div>
    </aside>
  );
}

function ShelfRow({ shelf, selected, onSelect }: { shelf: BankShelf; selected: boolean; onSelect: () => void }) {
  const Icon = shelf.group === "rotation" ? Music : Library;
  return (
    <button
      type="button"
      role="option"
      aria-selected={selected}
      tabIndex={selected ? 0 : -1}
      data-shelf={shelf.id}
      className={`bacs-row${selected ? " is-selected" : ""}`}
      onClick={onSelect}
    >
      <span className={`bacs-tile${shelf.group === "rotation" ? " is-habillage" : ""}`} aria-hidden="true">
        <Icon size={15} strokeWidth={1.75} />
      </span>
      <span className="bacs-row-main">
        <span className="bacs-row-title">{shelf.label}</span>
        <span className="bacs-row-meta">
          <span>{shelfFacts(shelf)}</span>
        </span>
      </span>
    </button>
  );
}
