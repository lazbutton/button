import { Button, Checkbox, Dialog, Spinner, TextField } from "@radix-ui/themes";
import { FolderTree, Search } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { bacErrorText } from "../../api/cartErrors";
import { fetchBankFolders } from "../../api/cartSounds";
import type { BankFolder } from "../../api/types";

/** Link bank folders to a bac: the files stay in the bank, nothing is copied. */
export function BankAttachDialog({
  open,
  onOpenChange,
  busy,
  cartTitle,
  onAttach,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  busy?: boolean;
  cartTitle: string;
  onAttach: (folders: string[]) => Promise<void>;
}) {
  const [query, setQuery] = useState("");
  const [available, setAvailable] = useState<boolean | null>(null);
  const [folders, setFolders] = useState<BankFolder[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [picked, setPicked] = useState<string[]>([]);
  const [failure, setFailure] = useState("");

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setError(null);
    setFailure("");
    setPicked([]);
    setQuery("");
    setAvailable(null);
    void fetchBankFolders()
      .then((payload) => {
        if (cancelled) return;
        setAvailable(payload.available);
        setFolders(payload.folders);
      })
      .catch(() => {
        if (cancelled) return;
        setAvailable(false);
        setError("La banque ne répond pas. Réessaie, ou ajoute les fichiers directement dans le bac.");
      });
    return () => {
      cancelled = true;
    };
  }, [open]);

  const visible = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase("fr");
    if (!needle) return folders;
    return folders.filter((folder) => folder.path.toLocaleLowerCase("fr").includes(needle));
  }, [folders, query]);

  const soundCount = useMemo(
    () => folders.filter((folder) => picked.includes(folder.path)).reduce((sum, folder) => sum + folder.count, 0),
    [folders, picked],
  );

  const toggle = (path: string) => {
    setPicked((current) => (current.includes(path) ? current.filter((item) => item !== path) : [...current, path]));
  };

  return (
    <Dialog.Root
      open={open}
      onOpenChange={(next) => {
        if (busy && !next) return;
        onOpenChange(next);
      }}
    >
      <Dialog.Content maxWidth="34rem" className="bacs-dialog">
        <Dialog.Title>Lier un dossier de la banque</Dialog.Title>
        <Dialog.Description size="2" color="gray" mb="4">
          « {cartTitle} » jouera les sons de ces dossiers. Rien n'est copié : les fichiers restent dans la banque.
        </Dialog.Description>
        {available === false ? (
          <p className="bacs-dialog-note">{error || "La banque n'est pas montée sur ce moteur (MEDIA_ROOT)."}</p>
        ) : (
          <>
            <TextField.Root
              size="2"
              placeholder="Filtrer : jingles, pubs, ids…"
              value={query}
              aria-label="Filtrer les dossiers"
              onChange={(event) => setQuery(event.target.value)}
            >
              <TextField.Slot>
                <Search size={15} aria-hidden="true" />
              </TextField.Slot>
            </TextField.Root>
            <div className="bacs-folders" role="group" aria-label="Dossiers de la banque">
              {available == null ? (
                <p className="bacs-folders-state">
                  <Spinner size="1" /> Lecture de la banque…
                </p>
              ) : visible.length === 0 ? (
                <p className="bacs-folders-state">Aucun dossier audio{query.trim() ? " pour ce filtre" : ""}.</p>
              ) : (
                visible.map((folder) => {
                  const cut = folder.path.lastIndexOf("/");
                  const parent = cut > 0 ? folder.path.slice(0, cut + 1) : "";
                  const leaf = cut > 0 ? folder.path.slice(cut + 1) : folder.path;
                  const checked = picked.includes(folder.path);
                  return (
                    <label key={folder.path} className={`bacs-folder${checked ? " is-checked" : ""}`}>
                      <Checkbox checked={checked} onCheckedChange={() => toggle(folder.path)} />
                      <FolderTree size={15} aria-hidden="true" />
                      <span className="bacs-folder-path">
                        <span>{parent}</span>
                        <strong>{leaf}</strong>
                      </span>
                      <span className="bacs-folder-count">
                        {folder.count} son{folder.count === 1 ? "" : "s"}
                      </span>
                    </label>
                  );
                })
              )}
            </div>
          </>
        )}
        {failure ? (
          <p className="bacs-dialog-error" role="alert">
            {failure}
          </p>
        ) : null}
        <div className="bacs-dialog-actions">
          <span className="bacs-dialog-summary">
            {picked.length
              ? `${picked.length} dossier${picked.length === 1 ? "" : "s"} · ${soundCount} son${soundCount === 1 ? "" : "s"}`
              : ""}
          </span>
          <Dialog.Close>
            <Button size="2" variant="soft" color="gray" disabled={busy}>
              Annuler
            </Button>
          </Dialog.Close>
          <Button
            size="2"
            highContrast
            disabled={picked.length === 0 || busy}
            onClick={() => {
              setFailure("");
              void onAttach(picked)
                .then(() => onOpenChange(false))
                .catch((caught: unknown) => setFailure(bacErrorText(caught, "Liaison impossible. Réessaie.")));
            }}
          >
            {busy ? "Liaison…" : picked.length > 1 ? `Lier ${picked.length} dossiers` : "Lier le dossier"}
          </Button>
        </div>
      </Dialog.Content>
    </Dialog.Root>
  );
}
