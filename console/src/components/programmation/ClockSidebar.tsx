import { Button, Kbd, TextField } from "@radix-ui/themes";
import { Clock3, Plus, Search, SearchX } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { fuzzyTitleMatch } from "../../api/fuzzyTitle";
import { cutsSummary } from "../../api/programmationView";
import type { Clock } from "../../api/types";

function isTyping(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName);
}

/** The heures types, alphabetical; the one on air is marked, so is the one not in the week. */
export function ClockSidebar({
  clocks,
  selectedId,
  onAirName,
  usage,
  tints,
  onSelect,
  onCreate,
}: {
  clocks: Clock[];
  selectedId: number | null;
  onAirName: string;
  usage: Map<number, string[]>;
  tints: Map<number, string>;
  onSelect: (id: number) => void;
  onCreate: () => void;
}) {
  const [query, setQuery] = useState("");
  const searchRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const visible = useMemo(
    () => (query.trim() ? clocks.filter((clock) => fuzzyTitleMatch(clock.name, query)) : clocks),
    [clocks, query],
  );

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
    if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key) || !visible.length) return;
    event.preventDefault();
    const index = visible.findIndex((clock) => clock.id === selectedId);
    let next = index < 0 ? 0 : index;
    if (event.key === "ArrowDown") next = Math.min(visible.length - 1, next + 1);
    if (event.key === "ArrowUp") next = Math.max(0, next - 1);
    if (event.key === "Home") next = 0;
    if (event.key === "End") next = visible.length - 1;
    const target = visible[next];
    onSelect(target.id);
    requestAnimationFrame(() => {
      listRef.current?.querySelector<HTMLElement>(`[data-clock="${target.id}"]`)?.focus();
    });
  };

  return (
    <aside className="prog-side" aria-label="Heures types">
      <header className="prog-side-head">
        <h2 className="prog-side-title">
          Heures types <span className="prog-count">{clocks.length}</span>
        </h2>
        <Button size="1" highContrast onClick={onCreate}>
          <Plus className="ui-button-icon" />
          Nouvelle
        </Button>
      </header>
      <div className="prog-side-tools">
        <TextField.Root
          ref={searchRef}
          size="2"
          placeholder="Rechercher"
          value={query}
          aria-label="Rechercher une heure type"
          onChange={(event) => setQuery(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Escape") {
              setQuery("");
              event.currentTarget.blur();
            }
            if (event.key === "ArrowDown") {
              event.preventDefault();
              listRef.current?.querySelector<HTMLElement>("[data-clock]")?.focus();
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
      </div>
      <div className="prog-side-list" ref={listRef} role="listbox" aria-label="Heures types" onKeyDown={move}>
        {visible.map((clock) => {
          const selected = clock.id === selectedId;
          const live = Boolean(onAirName) && clock.name === onAirName;
          const where = usage.get(clock.id) ?? [];
          const cuts = cutsSummary(clock);
          return (
            <button
              key={clock.id}
              type="button"
              role="option"
              aria-selected={selected}
              tabIndex={selected ? 0 : -1}
              data-clock={clock.id}
              className={`prog-side-row${selected ? " is-selected" : ""}`}
              onClick={() => onSelect(clock.id)}
            >
              <span className={`prog-tile tint-${tints.get(clock.id) ?? "gray"}`} aria-hidden="true">
                <Clock3 size={15} strokeWidth={1.75} />
              </span>
              <span className="prog-side-copy">
                <span className="prog-side-name">{clock.name}</span>
                <span className="prog-side-meta">
                  <span>
                    {clock.motif.length} étape{clock.motif.length === 1 ? "" : "s"}
                    {cuts ? ` · ${cuts}` : ""}
                  </span>
                </span>
              </span>
              {live ? (
                <span className="prog-state is-live" title="À l'antenne maintenant">
                  <i aria-hidden="true" />
                  Antenne
                </span>
              ) : where.length ? null : (
                <span className="prog-state" title="Posée nulle part dans la semaine">
                  Hors semaine
                </span>
              )}
            </button>
          );
        })}
        {visible.length === 0 ? (
          <div className="prog-side-empty">
            <SearchX size={18} aria-hidden="true" />
            <p>
              {query.trim()
                ? `Aucune heure type ne correspond à « ${query.trim()} ».`
                : "Aucune heure type pour l'instant."}
            </p>
            {query.trim() ? (
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
