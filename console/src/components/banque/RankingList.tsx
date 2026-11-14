import { Button, Select, TextField } from "@radix-ui/themes";
import { Disc3, Layers, Library, Music, Plus, Search, SearchX, Shapes, UserRound } from "lucide-react";
import { useMemo, useRef, useState, type KeyboardEvent } from "react";
import {
  RANKINGS,
  filterGroups,
  groupLabel,
  rankingOf,
  titlesCount,
  type BankFacet,
  type Ranking,
} from "../../api/bankTitles";

export const RANKING_ICONS = { collection: Library, artist: UserRound, famille: Shapes, album: Disc3 } as const;
// The whole bank, then one row per group: a long list of artists is only drawn this far.
const SHOWN = 400;

/**
 * The left column of the bank's table: « Ranger par », the whole bank, then the
 * groups of the ranking, each with its number of titles. A list one walks with
 * the arrows, as the list of collections.
 */
export function RankingList({
  ranking,
  groups,
  total,
  selected,
  loading,
  onRanking,
  onSelect,
  onCreate,
}: {
  ranking: Ranking;
  groups: BankFacet[];
  /** Every title of the bank. */
  total: number | null;
  /** null: the whole bank. */
  selected: string | null;
  loading: boolean;
  onRanking: (ranking: Ranking) => void;
  onSelect: (group: string | null) => void;
  /** Ranged by collection, an admin creates one, prefilled with what was typed. */
  onCreate?: (label: string) => void;
}) {
  const [query, setQuery] = useState("");
  const listRef = useRef<HTMLDivElement>(null);
  const searching = Boolean(query.trim());
  const visible = useMemo(() => filterGroups(groups, query, ranking), [groups, query, ranking]);
  const shown = visible.slice(0, SHOWN);
  const keys: Array<string | null> = [...(searching ? [] : [null]), ...shown.map((group) => group.value)];
  const plural = rankingOf(ranking).plural;
  const Icon = RANKING_ICONS[ranking];

  const move = (event: KeyboardEvent<HTMLDivElement>) => {
    if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key) || !keys.length) return;
    event.preventDefault();
    const index = keys.indexOf(selected);
    let next = index < 0 ? 0 : index;
    if (event.key === "ArrowDown") next = Math.min(keys.length - 1, next + 1);
    if (event.key === "ArrowUp") next = Math.max(0, next - 1);
    if (event.key === "Home") next = 0;
    if (event.key === "End") next = keys.length - 1;
    const target = keys[next];
    onSelect(target);
    requestAnimationFrame(() => {
      listRef.current?.querySelector<HTMLElement>(`[data-group-index="${next}"]`)?.focus();
    });
  };

  return (
    <aside className="bacs-lib" aria-label="Ranger la banque">
      <header className="bacs-lib-head">
        <h2 className="bacs-lib-title">
          {plural} <span className="bacs-count">{groups.filter((group) => group.value).length}</span>
        </h2>
        {onCreate ? (
          <Button size="1" highContrast onClick={() => onCreate(query.trim())}>
            <Plus className="ui-button-icon" />
            Nouvelle
          </Button>
        ) : null}
      </header>
      <div className="bacs-lib-tools banque-rank-tools">
        <label className="banque-rank">
          <span className="banque-rank-label">Ranger par</span>
          <Select.Root
            size="2"
            value={ranking}
            onValueChange={(value) => {
              setQuery("");
              onRanking(value as Ranking);
            }}
          >
            <Select.Trigger variant="soft" color="gray" aria-label="Ranger par" className="banque-rank-trigger" />
            <Select.Content variant="soft" position="popper">
              {RANKINGS.map((item) => (
                <Select.Item key={item.id} value={item.id}>
                  {item.label}
                </Select.Item>
              ))}
            </Select.Content>
          </Select.Root>
        </label>
        <TextField.Root
          size="2"
          className="bacs-search"
          placeholder="Rechercher"
          value={query}
          aria-label={`Rechercher dans les ${plural.toLowerCase()}`}
          onChange={(event) => setQuery(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Escape") {
              setQuery("");
              event.currentTarget.blur();
            }
            if (event.key === "ArrowDown") {
              event.preventDefault();
              listRef.current?.querySelector<HTMLElement>("[data-group-index]")?.focus();
            }
          }}
        >
          <TextField.Slot>
            <Search size={15} aria-hidden="true" />
          </TextField.Slot>
        </TextField.Root>
      </div>
      <div className="bacs-lib-list">
        <div ref={listRef} role="listbox" aria-label={plural} aria-busy={loading} onKeyDown={move}>
          {!searching ? (
            <GroupRow
              index={0}
              label="Toute la banque"
              count={total}
              icon={Layers}
              selected={selected === null}
              onSelect={() => onSelect(null)}
            />
          ) : null}
          {shown.length ? (
            <div className="bacs-lib-group" role="presentation">
              {!searching ? (
                <p className="bacs-lib-group-label" role="presentation">
                  {plural}
                  <span>{groups.filter((group) => group.value).length}</span>
                </p>
              ) : null}
              {shown.map((group, index) => (
                <GroupRow
                  key={`g:${group.value}`}
                  index={index + (searching ? 0 : 1)}
                  label={groupLabel(ranking, group.value, groups)}
                  count={group.count}
                  icon={ranking === "collection" && group.value === "rotation" ? Music : Icon}
                  rotation={ranking === "collection" && group.value === "rotation"}
                  empty={!group.value}
                  selected={selected === group.value}
                  onSelect={() => onSelect(group.value)}
                />
              ))}
            </div>
          ) : null}
        </div>
        {visible.length > SHOWN ? (
          <p className="banque-shelves-hint">
            {visible.length - SHOWN} de plus : précise la recherche pour les voir.
          </p>
        ) : null}
        {searching && !visible.length ? (
          <div className="bacs-lib-empty">
            <SearchX size={18} aria-hidden="true" />
            <p>Rien ne correspond à « {query.trim()} ».</p>
            {onCreate ? (
              <Button size="1" variant="soft" color="gray" onClick={() => onCreate(query.trim())}>
                Créer la collection « {query.trim()} »
              </Button>
            ) : (
              <Button size="1" variant="soft" color="gray" onClick={() => setQuery("")}>
                Effacer la recherche
              </Button>
            )}
          </div>
        ) : null}
        {ranking === "famille" && !loading && groups.every((group) => !group.value) ? (
          <p className="banque-shelves-hint">
            Aucune famille posée pour l'instant : elles viendront des fiches des titres, une fois relues.
          </p>
        ) : null}
      </div>
    </aside>
  );
}

function GroupRow({
  index,
  label,
  count,
  icon: Icon,
  rotation = false,
  empty = false,
  selected,
  onSelect,
}: {
  index: number;
  label: string;
  count: number | null;
  icon: typeof Library;
  rotation?: boolean;
  empty?: boolean;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      role="option"
      aria-selected={selected}
      tabIndex={selected ? 0 : -1}
      data-group-index={index}
      className={`bacs-row${selected ? " is-selected" : ""}${empty ? " banque-row-none" : ""}`}
      onClick={onSelect}
    >
      <span className={`bacs-tile${rotation ? " is-habillage" : ""}`} aria-hidden="true">
        <Icon size={15} strokeWidth={1.75} />
      </span>
      <span className="bacs-row-main">
        <span className="bacs-row-title">{label}</span>
        <span className="bacs-row-meta">
          <span>{count == null ? "…" : titlesCount(count)}</span>
        </span>
      </span>
    </button>
  );
}
