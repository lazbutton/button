import { Button, Dialog, SegmentedControl, Spinner, TextField } from "@radix-ui/themes";
import { Disc3, Search, SearchX } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { labelsFromHit, librarySearch, type LibraryHit, type LibraryTabId } from "../../api/library";
import { secondsLabel } from "../../api/agendaView";

const TABS: Array<{ id: LibraryTabId; label: string }> = [
  { id: "emission", label: "Émissions" },
  { id: "archives", label: "Archives" },
  { id: "all", label: "Tout" },
];

/** Pick a set in the bank: a show of the station, a rebroadcast, an archive. */
export function BankPicker({
  open,
  slotMinutes,
  onClose,
  onPick,
}: {
  open: boolean;
  slotMinutes: number;
  onClose: () => void;
  onPick: (hit: LibraryHit) => Promise<void>;
}) {
  const [tab, setTab] = useState<LibraryTabId>("emission");
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<LibraryHit[]>([]);
  const [loading, setLoading] = useState(false);
  const [failure, setFailure] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const searchRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    let alive = true;
    setLoading(true);
    const timer = window.setTimeout(() => {
      librarySearch({ q: query.trim(), tab, limit: 60 })
        .then((result) => {
          if (!alive) return;
          setHits(result.hits);
          setFailure("");
        })
        .catch((caught: unknown) => {
          if (!alive) return;
          setHits([]);
          setFailure(caught instanceof Error ? caught.message : "Recherche impossible.");
        })
        .finally(() => {
          if (alive) setLoading(false);
        });
    }, 160);
    return () => {
      alive = false;
      window.clearTimeout(timer);
    };
  }, [open, query, tab]);

  useEffect(() => {
    if (open) setBusy(null);
  }, [open]);

  const pick = async (hit: LibraryHit) => {
    setBusy(hit.id);
    try {
      await onPick(hit);
    } finally {
      setBusy(null);
    }
  };

  return (
    <Dialog.Root
      open={open}
      onOpenChange={(next) => {
        if (!next && !busy) onClose();
      }}
    >
      <Dialog.Content
        maxWidth="36rem"
        className="ag-bank"
        onOpenAutoFocus={(event) => {
          event.preventDefault();
          searchRef.current?.focus();
        }}
      >
        <Dialog.Title>Choisir dans la banque</Dialog.Title>
        <Dialog.Description size="2" color="gray" mb="3">
          Le fichier joue tel quel à l'heure de l'émission. Créneau de {secondsLabel(slotMinutes * 60)}.
        </Dialog.Description>
        <div className="ag-bank-tools">
          <TextField.Root
            ref={searchRef}
            size="2"
            placeholder="Titre, artiste, dossier"
            value={query}
            aria-label="Rechercher dans la banque"
            onChange={(event) => setQuery(event.target.value)}
          >
            <TextField.Slot>
              <Search size={15} aria-hidden="true" />
            </TextField.Slot>
            {loading ? (
              <TextField.Slot side="right">
                <Spinner size="1" />
              </TextField.Slot>
            ) : null}
          </TextField.Root>
          <SegmentedControl.Root size="1" value={tab} onValueChange={(value) => setTab(value as LibraryTabId)}>
            {TABS.map((item) => (
              <SegmentedControl.Item key={item.id} value={item.id}>
                {item.label}
              </SegmentedControl.Item>
            ))}
          </SegmentedControl.Root>
        </div>
        {failure ? (
          <p className="prog-dialog-error" role="alert">
            {failure}
          </p>
        ) : null}
        <ul className="ag-bank-list" aria-label="Fichiers de la banque">
          {hits.map((hit) => {
            const labels = labelsFromHit(hit);
            const over = hit.duration > slotMinutes * 60 + 60;
            return (
              <li key={hit.id}>
                <button
                  type="button"
                  className="ag-bank-row"
                  disabled={busy != null}
                  onClick={() => void pick(hit)}
                >
                  <Disc3 size={15} aria-hidden="true" />
                  <span className="ag-bank-copy">
                    <strong>{labels.title}</strong>
                    <small>
                      {labels.artist ? `${labels.artist} · ` : ""}
                      {hit.folder || hit.path}
                    </small>
                  </span>
                  <span className={`ag-bank-duration${over ? " is-over" : ""}`}>
                    {hit.duration ? secondsLabel(hit.duration) : "—"}
                  </span>
                  {busy === hit.id ? <Spinner size="1" /> : null}
                </button>
              </li>
            );
          })}
          {!loading && !hits.length && !failure ? (
            <li className="ag-bank-empty">
              <SearchX size={16} aria-hidden="true" />
              Rien ne correspond.
            </li>
          ) : null}
        </ul>
        <div className="prog-dialog-actions">
          <Dialog.Close>
            <Button type="button" size="2" variant="soft" color="gray" disabled={busy != null}>
              Fermer
            </Button>
          </Dialog.Close>
        </div>
      </Dialog.Content>
    </Dialog.Root>
  );
}
