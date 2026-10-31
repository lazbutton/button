import { Button, Popover, TextField } from "@radix-ui/themes";
import { Check, ChevronsUpDown, FolderPlus, Search } from "lucide-react";
import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { filterDestinations, type BankDestination } from "../../api/soundsView";

/**
 * Where uploads go: rotation, or one of the archive banks.
 * A searchable list, since a station can keep many banks.
 */
export function DestinationPicker({
  destinations,
  value,
  onChange,
  onCreate,
}: {
  destinations: BankDestination[];
  value: BankDestination;
  onChange: (id: string) => void;
  /** Opens the creation dialog, prefilled with what was typed. Admin only. */
  onCreate?: (label: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const listRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const baseId = useId();
  const visible = useMemo(() => filterDestinations(destinations, query), [destinations, query]);
  const archiveCount = destinations.filter((item) => item.group === "archives").length;
  const groups = [
    { id: "rotation", label: "Musique", items: visible.filter((item) => item.group === "rotation") },
    { id: "archives", label: "Archives", items: visible.filter((item) => item.group === "archives") },
  ].filter((group) => group.items.length);
  const flat = groups.flatMap((group) => group.items);

  // Only on opening: the list refreshes every 5 s and must not wipe what is being typed.
  useEffect(() => {
    if (!open) return;
    setQuery("");
    setActive(
      Math.max(
        0,
        destinations.findIndex((item) => item.id === value.id),
      ),
    );
  }, [open]);

  useEffect(() => {
    listRef.current?.querySelector<HTMLElement>(`[data-index="${active}"]`)?.scrollIntoView({ block: "nearest" });
  }, [active]);

  const pick = (item: BankDestination) => {
    onChange(item.id);
    setOpen(false);
  };

  const onKey = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      if (!flat.length) return;
      const step = event.key === "ArrowDown" ? 1 : -1;
      setActive((index) => (index + step + flat.length) % flat.length);
    } else if (event.key === "Enter") {
      event.preventDefault();
      if (flat[active]) pick(flat[active]);
      else if (onCreate && query.trim()) {
        setOpen(false);
        onCreate(query.trim());
      }
    }
  };

  const optionId = (index: number) => `${baseId}-option-${index}`;
  const kind = value.group === "rotation" ? "Musique" : "Archives";
  let index = -1;

  return (
    <Popover.Root open={open} onOpenChange={setOpen}>
      <Popover.Trigger>
        <button
          type="button"
          className="banque-dest-trigger"
          aria-label={`Destination : ${kind}, ${value.label}, ${value.folder}`}
        >
          {/* Les espaces séparent les mots du texte affiché, que le nom reprend. */}
          <span className="banque-dest-kind">{kind}</span>{" "}
          <span className="banque-dest-name">{value.label}</span>{" "}
          <code className="banque-dest-path">{value.folder}</code>
          <ChevronsUpDown size={15} aria-hidden="true" className="banque-dest-chevron" />
        </button>
      </Popover.Trigger>
      <Popover.Content
        className="banque-dest-pop"
        align="start"
        sideOffset={6}
        onOpenAutoFocus={(event) => {
          // Straight to the search: typing filters at once, and a space never toggles the trigger.
          event.preventDefault();
          searchRef.current?.focus();
        }}
      >
        <TextField.Root
          ref={searchRef}
          size="2"
          role="combobox"
          aria-expanded="true"
          aria-controls={`${baseId}-list`}
          aria-activedescendant={flat[active] ? optionId(active) : undefined}
          aria-label="Rechercher une banque"
          placeholder={archiveCount > 6 ? `Rechercher parmi ${archiveCount + 1} banques` : "Rechercher une banque"}
          value={query}
          onChange={(event) => {
            setQuery(event.target.value);
            setActive(0);
          }}
          onKeyDown={onKey}
        >
          <TextField.Slot>
            <Search size={15} aria-hidden="true" />
          </TextField.Slot>
        </TextField.Root>
        <div className="banque-dest-list" id={`${baseId}-list`} role="listbox" aria-label="Banques" ref={listRef}>
          {groups.map((group) => (
            <div key={group.id} role="group" aria-label={group.label}>
              <p className="banque-dest-group" aria-hidden="true">
                {group.label}
                {group.id === "archives" ? <span>{group.items.length}</span> : null}
              </p>
              {group.items.map((item) => {
                index += 1;
                const at = index;
                const selected = item.id === value.id;
                return (
                  <div
                    key={item.id}
                    id={optionId(at)}
                    data-index={at}
                    role="option"
                    aria-selected={selected}
                    className={`banque-dest-option${at === active ? " is-active" : ""}`}
                    onMouseMove={() => setActive(at)}
                    onMouseDown={(event) => event.preventDefault()}
                    onClick={() => pick(item)}
                  >
                    <span className="banque-dest-option-copy">
                      <span>{item.label}</span>
                      <code>{item.folder}</code>
                    </span>
                    {selected ? <Check size={15} aria-hidden="true" /> : null}
                  </div>
                );
              })}
            </div>
          ))}
          {flat.length === 0 ? <p className="banque-dest-empty">Aucune banque pour « {query.trim()} ».</p> : null}
        </div>
        {onCreate ? (
          <div className="banque-dest-foot">
            <Button
              size="2"
              variant="ghost"
              color="gray"
              onClick={() => {
                setOpen(false);
                onCreate(flat.length ? "" : query.trim());
              }}
            >
              <FolderPlus className="ui-button-icon" />
              {flat.length === 0 && query.trim() ? `Créer « ${query.trim()} »` : "Nouvelle banque d'archives"}
            </Button>
          </div>
        ) : null}
      </Popover.Content>
    </Popover.Root>
  );
}
