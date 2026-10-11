import { Button, Code, Dialog, TextField } from "@radix-ui/themes";
import { useEffect, useState } from "react";
import { bankFolderOf, bankProblem, type BankDestination } from "../../api/soundsView";
import { FormField } from "../../ui/FormField";

/** A new archive bank: a name, and the folder of 20-archives it lives in. */
export function CreateBankDialog({
  open,
  onOpenChange,
  initialLabel,
  destinations,
  onCreate,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  initialLabel: string;
  destinations: BankDestination[];
  onCreate: (label: string, folder: string) => Promise<void>;
}) {
  const [label, setLabel] = useState(initialLabel);
  const [folder, setFolder] = useState(bankFolderOf(initialLabel));
  const [folderTouched, setFolderTouched] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState("");
  const [tried, setTried] = useState(false);

  const problem = bankProblem(destinations, label, folder);
  // Say nothing while the form is still blank; say everything once it was sent.
  const shown = tried || label.trim() ? problem : null;

  useEffect(() => {
    if (!open) return;
    setLabel(initialLabel);
    setFolder(bankFolderOf(initialLabel));
    setFolderTouched(false);
    setFailure("");
    setTried(false);
  }, [open, initialLabel]);

  const submit = async () => {
    setTried(true);
    if (busy || problem) return;
    setBusy(true);
    setFailure("");
    try {
      await onCreate(label.trim().replace(/\s+/g, " "), folder);
      onOpenChange(false);
    } catch (caught) {
      setFailure(caught instanceof Error ? caught.message : "Création impossible. Réessaie.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog.Root
      open={open}
      onOpenChange={(next) => {
        if (busy && !next) return;
        onOpenChange(next);
      }}
    >
      <Dialog.Content maxWidth="30rem">
        <Dialog.Title>Nouvelle banque d'archives</Dialog.Title>
        <Dialog.Description size="2" color="gray" mb="4">
          Une banque est un dossier de 20-archives. Les fichiers envoyés vers elle y sont rangés, puis Beets les indexe.
        </Dialog.Description>
        <form
          className="bacs-dialog-form"
          onSubmit={(event) => {
            event.preventDefault();
            void submit();
          }}
        >
          <FormField label="Nom" error={shown?.field === "label" ? shown.message : undefined}>
            <TextField.Root
              size="2"
              className="ui-field-control"
              value={label}
              placeholder="Archives jazz"
              autoFocus
              onChange={(event) => {
                setLabel(event.target.value);
                if (!folderTouched) setFolder(bankFolderOf(event.target.value));
              }}
            />
          </FormField>
          <FormField
            label="Dossier"
            error={shown?.field === "folder" ? shown.message : undefined}
            hint={
              <>
                Il sert de grouping à l'auto-DJ : une catégorie <Code size="1">grouping:{folder || "…"}</Code> joue
                cette banque.
              </>
            }
          >
            <TextField.Root
              size="2"
              className="ui-field-control banque-folder-field"
              value={folder}
              spellCheck={false}
              onChange={(event) => {
                setFolderTouched(true);
                setFolder(event.target.value.toLowerCase());
              }}
            >
              <TextField.Slot>20-archives/</TextField.Slot>
            </TextField.Root>
          </FormField>
          {failure ? (
            <p className="bacs-dialog-error" role="alert">
              {failure}
            </p>
          ) : null}
          <div className="bacs-dialog-actions">
            <Dialog.Close>
              <Button type="button" size="2" variant="soft" color="gray" disabled={busy}>
                Annuler
              </Button>
            </Dialog.Close>
            <Button type="submit" size="2" highContrast disabled={busy || Boolean(tried && problem)}>
              {busy ? "Création…" : "Créer la banque"}
            </Button>
          </div>
        </form>
      </Dialog.Content>
    </Dialog.Root>
  );
}
