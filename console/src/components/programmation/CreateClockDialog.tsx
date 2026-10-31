import { Button, Dialog, RadioCards, Select, TextField } from "@radix-ui/themes";
import { Copy, Sparkles } from "lucide-react";
import { useEffect, useState } from "react";
import { copyName, nameTaken, stepsSummary } from "../../api/programmationView";
import type { Clock } from "../../api/types";
import { FormField } from "../../ui/FormField";

/** A new heure type: a fresh one, or a copy of one that already works. */
export function CreateClockDialog({
  open,
  onOpenChange,
  clocks,
  copyOf,
  starter,
  onCreate,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  clocks: Clock[];
  /** Opened from « Dupliquer » : the copy is chosen already. */
  copyOf: Clock | null;
  /** What a fresh heure type plays, said in a line. */
  starter: string;
  onCreate: (name: string, from: Clock | null) => Promise<void>;
}) {
  const [name, setName] = useState("");
  const [mode, setMode] = useState<"fresh" | "copy">("fresh");
  const [sourceId, setSourceId] = useState("");
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState("");
  const names = clocks.map((clock) => clock.name);
  const source = clocks.find((clock) => String(clock.id) === sourceId) ?? null;
  const clash = nameTaken(name, names);
  const ready = Boolean(name.trim()) && !clash && (mode === "fresh" || source != null);

  // Only on opening: the list may refresh while the dialog is open.
  useEffect(() => {
    if (!open) return;
    setFailure("");
    setBusy(false);
    if (copyOf) {
      setMode("copy");
      setSourceId(String(copyOf.id));
      setName(copyName(copyOf.name, names));
    } else {
      setMode("fresh");
      setSourceId(clocks[0] ? String(clocks[0].id) : "");
      setName("");
    }
  }, [open]);

  const submit = async () => {
    if (!ready || busy) return;
    setBusy(true);
    setFailure("");
    try {
      await onCreate(name.trim(), mode === "copy" ? source : null);
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
      <Dialog.Content maxWidth="32rem">
        <Dialog.Title>{copyOf ? "Dupliquer l'heure type" : "Nouvelle heure type"}</Dialog.Title>
        <Dialog.Description size="2" color="gray" mb="4">
          Une heure type dit ce qui passe pendant une heure. La semaine dit quand elle joue.
        </Dialog.Description>
        <form
          className="prog-dialog-form"
          onSubmit={(event) => {
            event.preventDefault();
            void submit();
          }}
        >
          <FormField
            label="Nom"
            error={clash ? "Une heure type porte déjà ce nom." : undefined}
            hint="Court : il s'affiche dans la semaine."
          >
            <TextField.Root
              size="2"
              className="ui-field-control"
              value={name}
              placeholder="Journée pubs"
              autoFocus
              onChange={(event) => setName(event.target.value)}
            />
          </FormField>
          <div className="ui-field">
            <span className="ui-field-label">Partir de</span>
            <RadioCards.Root
              size="1"
              columns="2"
              value={mode}
              onValueChange={(value) => setMode(value as "fresh" | "copy")}
              aria-label="Partir de"
            >
              <RadioCards.Item value="fresh" className="prog-choice">
                <Sparkles size={16} strokeWidth={1.75} aria-hidden="true" />
                <span className="prog-choice-label">Une heure neuve</span>
                <span className="prog-choice-hint">{starter}</span>
              </RadioCards.Item>
              <RadioCards.Item value="copy" className="prog-choice" disabled={!clocks.length}>
                <Copy size={16} strokeWidth={1.75} aria-hidden="true" />
                <span className="prog-choice-label">Une copie</span>
                <span className="prog-choice-hint">Mêmes étapes, mêmes coupures</span>
              </RadioCards.Item>
            </RadioCards.Root>
          </div>
          {mode === "copy" ? (
            <div className="ui-field">
              <span className="ui-field-label">Copie de</span>
              <Select.Root size="2" value={sourceId} onValueChange={setSourceId}>
                <Select.Trigger className="ui-field-control" aria-label="Heure type à copier" />
                <Select.Content variant="soft" position="popper">
                  {clocks.map((clock) => (
                    <Select.Item key={clock.id} value={String(clock.id)}>
                      {clock.name}
                    </Select.Item>
                  ))}
                </Select.Content>
              </Select.Root>
              {source ? <span className="ui-field-hint">{stepsSummary(source)}</span> : null}
            </div>
          ) : null}
          {failure ? (
            <p className="prog-dialog-error" role="alert">
              {failure}
            </p>
          ) : null}
          <div className="prog-dialog-actions">
            <Dialog.Close>
              <Button type="button" size="2" variant="soft" color="gray" disabled={busy}>
                Annuler
              </Button>
            </Dialog.Close>
            <Button type="submit" size="2" highContrast disabled={!ready || busy}>
              {busy ? "Création…" : copyOf || mode === "copy" ? "Créer la copie" : "Créer l'heure type"}
            </Button>
          </div>
        </form>
      </Dialog.Content>
    </Dialog.Root>
  );
}
