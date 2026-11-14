import { Button, Dialog, DropdownMenu, TextField } from "@radix-ui/themes";
import { Bookmark, BookmarkPlus, Check, ChevronDown, Pencil, Save, Trash2 } from "lucide-react";
import { useState } from "react";
import { viewNameProblem, type SavedView } from "../../api/bankTitles";
import { ConfirmDialog } from "../../ui/ConfirmDialog";
import { FormField } from "../../ui/FormField";

type Naming = { mode: "create" } | { mode: "rename"; view: SavedView };

/**
 * « Vues » : the views this account keeps of the table, under a name (FON-65).
 * Open one, save what the table shows as a new one, or update, rename or delete
 * the one open. The engine keeps them, so another computer finds them too.
 */
export function ViewsMenu({
  views,
  active,
  modified,
  onOpen,
  onCreate,
  onSave,
  onRename,
  onDelete,
}: {
  views: SavedView[];
  /** The view open, if the table came from one. */
  active: SavedView | null;
  /** The table no longer shows what the open view keeps. */
  modified: boolean;
  onOpen: (view: SavedView) => void;
  /** Rejects with the engine's refusal, shown in the dialog. */
  onCreate: (name: string) => Promise<void>;
  onSave: (view: SavedView) => void;
  onRename: (view: SavedView, name: string) => Promise<void>;
  onDelete: (view: SavedView) => Promise<void>;
}) {
  const [naming, setNaming] = useState<Naming | null>(null);
  const [deleting, setDeleting] = useState<SavedView | null>(null);
  const [busy, setBusy] = useState(false);
  const label = active ? `${active.name}${modified ? " (modifiée)" : ""}` : "Vues";

  return (
    <>
      <DropdownMenu.Root modal={false}>
        <DropdownMenu.Trigger>
          <Button size="2" variant="soft" color="gray" className="banque-views-trigger">
            <Bookmark className="ui-button-icon" />
            <span className="banque-views-name">{label}</span>
            <ChevronDown size={14} aria-hidden="true" />
          </Button>
        </DropdownMenu.Trigger>
        <DropdownMenu.Content variant="soft" align="end" className="bacs-menu">
          {views.length ? (
            <DropdownMenu.Label>Mes vues</DropdownMenu.Label>
          ) : (
            <DropdownMenu.Label>Aucune vue gardée</DropdownMenu.Label>
          )}
          {views.map((view) => (
            <DropdownMenu.Item key={view.id} onSelect={() => onOpen(view)}>
              {view.id === active?.id ? <Check size={14} aria-hidden="true" /> : <span className="banque-views-pad" aria-hidden="true" />}
              {view.name}
            </DropdownMenu.Item>
          ))}
          <DropdownMenu.Separator />
          <DropdownMenu.Item onSelect={() => setNaming({ mode: "create" })}>
            <BookmarkPlus size={14} aria-hidden="true" />
            Garder cette vue…
          </DropdownMenu.Item>
          {active ? (
            <>
              <DropdownMenu.Item disabled={!modified} onSelect={() => onSave(active)}>
                <Save size={14} aria-hidden="true" />
                Mettre à jour « {active.name} »
              </DropdownMenu.Item>
              <DropdownMenu.Item onSelect={() => setNaming({ mode: "rename", view: active })}>
                <Pencil size={14} aria-hidden="true" />
                Renommer « {active.name} »…
              </DropdownMenu.Item>
              <DropdownMenu.Item color="red" onSelect={() => setDeleting(active)}>
                <Trash2 size={14} aria-hidden="true" />
                Supprimer « {active.name} »…
              </DropdownMenu.Item>
            </>
          ) : null}
        </DropdownMenu.Content>
      </DropdownMenu.Root>

      {naming ? (
        <NameDialog
          naming={naming}
          views={views}
          onClose={() => setNaming(null)}
          onSubmit={async (name) => {
            if (naming.mode === "create") await onCreate(name);
            else await onRename(naming.view, name);
            setNaming(null);
          }}
        />
      ) : null}

      <ConfirmDialog
        open={deleting != null}
        onOpenChange={(open) => {
          if (!open && !busy) setDeleting(null);
        }}
        busy={busy}
        title={`Supprimer la vue « ${deleting?.name ?? ""} » ?`}
        description="Seule la vue s'en va : ses colonnes, son tri et ses filtres. Les titres de la banque ne changent pas."
        confirmLabel="Supprimer la vue"
        onConfirm={async () => {
          if (!deleting) return;
          setBusy(true);
          try {
            await onDelete(deleting);
          } finally {
            setBusy(false);
            setDeleting(null);
          }
        }}
      />
    </>
  );
}

function NameDialog({
  naming,
  views,
  onClose,
  onSubmit,
}: {
  naming: Naming;
  views: SavedView[];
  onClose: () => void;
  onSubmit: (name: string) => Promise<void>;
}) {
  const before = naming.mode === "rename" ? naming.view.name : "";
  const [name, setName] = useState(before);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState("");
  const [touched, setTouched] = useState(false);
  const problem = viewNameProblem(name, views, naming.mode === "rename" ? naming.view.id : null);

  const submit = async () => {
    setTouched(true);
    if (busy || problem) return;
    setBusy(true);
    setFailure("");
    try {
      await onSubmit(name.trim().replace(/\s+/g, " "));
    } catch (caught) {
      setFailure(caught instanceof Error && caught.message ? caught.message : "La vue n'a pas été gardée. Réessaie.");
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
      <Dialog.Content maxWidth="28rem">
        <Dialog.Title>{naming.mode === "create" ? "Garder cette vue" : "Renommer la vue"}</Dialog.Title>
        <Dialog.Description size="2" color="gray" mb="4">
          {naming.mode === "create"
            ? "Ses colonnes, son tri, son rangement et sa recherche, sous un nom : elle se rouvre d'un clic, sur n'importe quel ordinateur où tu te connectes."
            : "Seul son nom change."}
        </Dialog.Description>
        <form
          className="bacs-dialog-form"
          onSubmit={(event) => {
            event.preventDefault();
            void submit();
          }}
        >
          <FormField label="Nom" error={touched && problem && name.trim() !== before ? problem : undefined}>
            <TextField.Root
              size="2"
              className="ui-field-control"
              value={name}
              autoFocus
              maxLength={80}
              placeholder="Jazz à relire"
              onChange={(event) => setName(event.target.value)}
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
            <Button type="submit" size="2" highContrast disabled={busy}>
              {busy ? "Enregistrement…" : naming.mode === "create" ? "Garder la vue" : "Renommer"}
            </Button>
          </div>
        </form>
      </Dialog.Content>
    </Dialog.Root>
  );
}
