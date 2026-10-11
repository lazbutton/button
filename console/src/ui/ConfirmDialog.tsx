import { Button, Dialog, Flex } from "@radix-ui/themes";
import { useState, type ReactElement, type ReactNode } from "react";

export function ConfirmDialog({
  trigger,
  open,
  onOpenChange,
  title,
  description,
  confirmLabel = "Confirmer",
  cancelLabel = "Annuler",
  busy = false,
  onConfirm,
}: {
  trigger?: ReactElement;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  title: string;
  description: ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  busy?: boolean;
  onConfirm: () => void | Promise<void>;
}) {
  const [internalOpen, setInternalOpen] = useState(false);
  const controlled = open !== undefined;
  const actualOpen = controlled ? open : internalOpen;
  const setOpen = onOpenChange ?? setInternalOpen;

  return (
    <Dialog.Root
      open={actualOpen}
      onOpenChange={(next) => {
        if (busy && !next) return;
        setOpen(next);
      }}
    >
      {trigger ? <Dialog.Trigger>{trigger}</Dialog.Trigger> : null}
      <Dialog.Content maxWidth="28rem">
        <Dialog.Title>{title}</Dialog.Title>
        <Dialog.Description className="ui-confirm-copy">{description}</Dialog.Description>
        <Flex justify="end" gap="2" mt="4">
          <Button
            variant="soft"
            color="gray"
            disabled={busy}
            onClick={() => setOpen(false)}
          >
            {cancelLabel}
          </Button>
          <Button
            color="red"
            disabled={busy}
            onClick={() => {
              void Promise.resolve(onConfirm()).then(() => {
                if (!controlled) setOpen(false);
              });
            }}
          >
            {busy ? "En cours…" : confirmLabel}
          </Button>
        </Flex>
      </Dialog.Content>
    </Dialog.Root>
  );
}
