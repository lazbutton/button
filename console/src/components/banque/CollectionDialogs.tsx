import { Button, Code, Dialog, TextField } from "@radix-ui/themes";
import { useState } from "react";
import { useAccount } from "../../api/AccountContext";
import { moveNote, renameCollection, renameProblem, titlesLabel, type BankShelf } from "../../api/bankContent";
import type { BankDestination } from "../../api/soundsView";
import { FormField } from "../../ui/FormField";
import { DestinationPicker } from "./DestinationPicker";

// The windows of a collection's gestures, which the table opens: move titles
// to another collection, rename one.

function messageOf(caught: unknown, fallback: string): string {
  return caught instanceof Error && caught.message ? caught.message : fallback;
}

export function MoveDialog({
  names,
  from,
  options,
  onClose,
  onMove,
  initial,
}: {
  names: string[];
  from: BankShelf;
  options: BankShelf[];
  onClose: () => void;
  onMove: (target: BankDestination) => void;
  /** The collection the titles were dropped on (FON-75). */
  initial?: string;
}) {
  const { account } = useAccount();
  const [target, setTarget] = useState(initial ?? options[0]?.id ?? "");
  const value = options.find((item) => item.id === target) ?? options[0];
  const what = names.length === 1 ? "ce titre" : titlesLabel(names.length).toLowerCase();

  return (
    <Dialog.Root
      open
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <Dialog.Content maxWidth="30rem">
        <Dialog.Title>Déplacer {what}</Dialog.Title>
        <Dialog.Description size="2" color="gray" mb="4">
          Depuis {from.label}. Un titre qui a déjà son pareil, sous le même nom, dans la destination reste où il est.
        </Dialog.Description>
        {value ? (
          <div className="banque-dest">
            <span className="ui-field-label">Vers</span>
            <DestinationPicker destinations={options} value={value} onChange={setTarget} />
          </div>
        ) : null}
        <p className="bacs-dialog-note">
          {moveNote(names.length, value ? value.label : "sa destination", account?.features?.bank_moves === true)}
        </p>
        <div className="bacs-dialog-actions">
          <Dialog.Close>
            <Button type="button" size="2" variant="soft" color="gray">
              Annuler
            </Button>
          </Dialog.Close>
          <Button size="2" highContrast disabled={!value} onClick={() => value && onMove(value)}>
            {value ? `Déplacer vers ${value.label}` : "Déplacer"}
          </Button>
        </div>
      </Dialog.Content>
    </Dialog.Root>
  );
}

export function RenameDialog({
  shelf,
  shelves,
  onClose,
  onRenamed,
}: {
  shelf: BankShelf;
  shelves: BankShelf[];
  onClose: () => void;
  onRenamed: (destination: BankDestination) => void;
}) {
  const [label, setLabel] = useState(shelf.label);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState("");
  const name = label.trim().replace(/\s+/g, " ");
  const problem = renameProblem(shelves, shelf.id, label);

  const submit = async () => {
    if (busy || problem) return;
    if (name === shelf.label) {
      onClose();
      return;
    }
    setBusy(true);
    setFailure("");
    try {
      onRenamed(await renameCollection(shelf.id, name));
    } catch (caught) {
      setFailure(messageOf(caught, "Le nom n'a pas changé. Réessaie."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog.Root
      open
      onOpenChange={(open) => {
        if (!open && !busy) onClose();
      }}
    >
      <Dialog.Content maxWidth="30rem">
        <Dialog.Title>Renommer la collection</Dialog.Title>
        <Dialog.Description size="2" color="gray" mb="4">
          Seul le nom affiché change. Son dossier garde le sien : la sélection <Code size="1">grouping:{shelf.id}</Code>{" "}
          la joue toujours.
        </Dialog.Description>
        <form
          className="bacs-dialog-form"
          onSubmit={(event) => {
            event.preventDefault();
            void submit();
          }}
        >
          <FormField label="Nom" error={problem && name !== shelf.label ? problem : undefined}>
            <TextField.Root
              size="2"
              className="ui-field-control"
              value={label}
              autoFocus
              onChange={(event) => setLabel(event.target.value)}
            />
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
            <Button type="submit" size="2" highContrast disabled={busy || Boolean(problem)}>
              {busy ? "Enregistrement…" : "Renommer"}
            </Button>
          </div>
        </form>
      </Dialog.Content>
    </Dialog.Root>
  );
}
