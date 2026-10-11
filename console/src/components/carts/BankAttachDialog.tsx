import { Button, Dialog, Text, TextField } from "@radix-ui/themes";
import { HardDrive } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { fetchBankFolders } from "../../api/cartSounds";
import type { BankFolder } from "../../api/types";

export function BankAttachDialog({
  disabled,
  busy,
  onAttach,
  iconOnly,
}: {
  disabled?: boolean;
  busy?: boolean;
  onAttach: (folders: string[]) => Promise<void>;
  iconOnly?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [available, setAvailable] = useState<boolean | null>(null);
  const [folders, setFolders] = useState<BankFolder[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [picked, setPicked] = useState<string[]>([]);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setError(null);
    setPicked([]);
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
        setError("La banque ne répond pas. Réessaie, ou dépose le fichier dans le bac.");
      });
    return () => {
      cancelled = true;
    };
  }, [open]);

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return folders;
    return folders.filter((folder) => folder.path.toLowerCase().includes(needle));
  }, [folders, query]);

  const selectedCount = useMemo(
    () =>
      folders
        .filter((folder) => picked.includes(folder.path))
        .reduce((sum, folder) => sum + folder.count, 0),
    [folders, picked],
  );

  const toggle = (path: string) => {
    setPicked((current) =>
      current.includes(path) ? current.filter((item) => item !== path) : [...current, path],
    );
  };

  return (
    <Dialog.Root
      open={open}
      onOpenChange={(next) => {
        if (busy && !next) return;
        setOpen(next);
      }}
    >
      <Dialog.Trigger>
        {iconOnly ? (
          <Button
            size="1"
            variant="ghost"
            color="gray"
            className="app-carts-icon-btn"
            disabled={disabled || busy}
            aria-label="Attacher un dossier (sans copie)"
            title="Attacher un dossier (sans copie)"
          >
            <HardDrive className="ui-button-icon" />
          </Button>
        ) : (
          <Button size="1" variant="outline" disabled={disabled || busy}>
            <HardDrive className="ui-button-icon" />
            Attacher un dossier (sans copie)
          </Button>
        )}
      </Dialog.Trigger>
      <Dialog.Content maxWidth="32rem" className="app-bank-dialog">
        <Dialog.Title>Attacher un dossier (sans copie)</Dialog.Title>
        <Dialog.Description size="2" mb="3">
          Le bac pointe le dossier. Les fichiers restent dans la banque, ils ne sont pas copiés.
        </Dialog.Description>
        {available === false ? (
          <Text size="2" color="gray">
            {error || "La banque n’est pas montée sur cet automate (MEDIA_ROOT)."}
          </Text>
        ) : (
          <>
            <TextField.Root
              size="2"
              placeholder="Filtrer un dossier… jingles, pubs, hph…"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              mb="3"
            />
            <div className="app-bank-folders">
              {available == null ? (
                <Text size="2" color="gray">
                  Lecture de la banque…
                </Text>
              ) : visible.length === 0 ? (
                <Text size="2" color="gray">
                  Aucun dossier audio.
                </Text>
              ) : (
                visible.map((folder) => (
                  <button
                    key={folder.path}
                    type="button"
                    className={`app-bank-folder${picked.includes(folder.path) ? " is-selected" : ""}`}
                    onClick={() => toggle(folder.path)}
                  >
                    <span>{folder.path}</span>
                    <em>
                      {folder.count} son{folder.count === 1 ? "" : "s"}
                    </em>
                  </button>
                ))
              )}
            </div>
          </>
        )}
        <div className="app-bank-dialog-actions">
          <Dialog.Close>
            <Button variant="soft" color="gray" disabled={busy}>
              Annuler
            </Button>
          </Dialog.Close>
          <Button
            disabled={picked.length === 0 || busy}
            onClick={() => {
              void onAttach(picked).then(() => setOpen(false));
            }}
          >
            {busy
              ? "Liaison…"
              : picked.length <= 1
                ? "Attacher le dossier (sans copie)"
                : `Attacher ${picked.length} dossiers (sans copie) · ${selectedCount} sons`}
          </Button>
        </div>
      </Dialog.Content>
    </Dialog.Root>
  );
}
