import {
  Badge,
  Button,
  Checkbox,
  Code,
  Dialog,
  DropdownMenu,
  IconButton,
  Select,
  Spinner,
  TextField,
  Tooltip,
} from "@radix-ui/themes";
import {
  ArrowLeft,
  FolderInput,
  Library,
  MoreHorizontal,
  Music,
  Pencil,
  Play,
  RefreshCw,
  Search,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  BANK_PAGE,
  bankFileUrl,
  bankFiles,
  bankLabels,
  changeSummary,
  deleteCollection,
  isAudioName,
  modifiedLabel,
  moveBankFiles,
  removeBankFiles,
  renameCollection,
  renameProblem,
  subfolderOf,
  titlesLabel,
  toggleSelection,
  type BankChange,
  type BankFile,
  type BankPage,
  type BankShelf,
  type BankSort,
} from "../../api/bankContent";
import type { BankDestination } from "../../api/soundsView";
import { formatBytes, formatClock, percentOf } from "../../api/soundsView";
import { usePreview } from "../../lib/usePreview";
import { ConfirmDialog } from "../../ui/ConfirmDialog";
import { ErrorState, LoadingState } from "../../ui/DataState";
import { FormField } from "../../ui/FormField";
import { DestinationPicker } from "./DestinationPicker";

type Notify = (text: string, tone: "success" | "error" | "info") => void;
type Progress = { kind: "removed" | "moved"; done: number; total: number };

function messageOf(caught: unknown, fallback: string): string {
  return caught instanceof Error && caught.message ? caught.message : fallback;
}

/** What rotation or a collection holds: see, listen, remove, move. */
export function CollectionView({
  shelf,
  shelves,
  isAdmin,
  onBack,
  onAdd,
  onChanged,
  onRenamed,
  onDeleted,
  notify,
}: {
  shelf: BankShelf;
  shelves: BankShelf[];
  isAdmin: boolean;
  onBack: () => void;
  /** Opens the upload view, with this collection as its destination. */
  onAdd: (id: string) => void;
  /** Something changed on the disk: the counts of the left column follow. */
  onChanged: () => void;
  /** The collection's new name, and the one it had. */
  onRenamed: (destination: BankDestination, before: string) => void;
  /** The collection is gone; `trashed` hidden files went to the trash with it. */
  onDeleted: (shelf: BankShelf, trashed: number) => void;
  notify: Notify;
}) {
  const rotation = shelf.group === "rotation";
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<BankSort>("name");
  const [page, setPage] = useState<BankPage | null>(null);
  const [files, setFiles] = useState<BankFile[]>([]);
  const [problem, setProblem] = useState("");
  const [loadingMore, setLoadingMore] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(() => new Set());
  const [progress, setProgress] = useState<Progress | null>(null);
  const [removing, setRemoving] = useState<string[] | null>(null);
  const [moving, setMoving] = useState<string[] | null>(null);
  const [renaming, setRenaming] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const lastClicked = useRef<string | null>(null);
  const ticket = useRef(0);
  const preview = usePreview(
    (message) => notify(message, "error"),
    (name) => bankFileUrl(shelf.id, name),
  );

  const load = useCallback(async () => {
    const mine = ++ticket.current;
    try {
      const next = await bankFiles(shelf.id, { q: query, sort });
      if (mine !== ticket.current) return;
      setPage(next);
      setFiles(next.files);
      setProblem("");
    } catch (caught) {
      if (mine !== ticket.current) return;
      setProblem(messageOf(caught, "La liste ne s'est pas lue. Réessaie."));
    }
  }, [query, shelf.id, sort]);

  // A search waits for the typing to stop; an order or a collection reads at once.
  useEffect(() => {
    const timer = window.setTimeout(() => void load(), query.trim() ? 250 : 0);
    return () => window.clearTimeout(timer);
  }, [load, query]);

  // What is selected follows what is shown.
  useEffect(() => {
    setSelected(new Set());
    lastClicked.current = null;
  }, [query, sort]);

  const loadMore = async () => {
    // After an incomplete search, the next page would skip what the full one sorts first.
    if (!page || page.partial || loadingMore) return;
    const mine = ticket.current;
    setLoadingMore(true);
    try {
      const next = await bankFiles(shelf.id, { q: query, sort, offset: files.length });
      if (mine !== ticket.current) return;
      setFiles((before) => [...before, ...next.files.filter((file) => !before.some((item) => item.name === file.name))]);
      setPage(next);
    } catch (caught) {
      notify(messageOf(caught, "La suite de la liste ne s'est pas lue."), "error");
    } finally {
      setLoadingMore(false);
    }
  };

  const busy = progress != null;
  const count = page?.total ?? shelf.count;
  const bytes = page?.bytes ?? shelf.bytes;
  const matched = page?.matched ?? count;
  const searching = Boolean(query.trim());
  const order = files.map((file) => file.name);
  const allSelected = files.length > 0 && files.every((file) => selected.has(file.name));
  const someSelected = !allSelected && files.some((file) => selected.has(file.name));
  const others = shelves.filter((item) => item.id !== shelf.id);
  const now = Date.now();

  const run = async (
    kind: Progress["kind"],
    names: string[],
    send: (onProgress: (done: number, total: number) => void) => Promise<BankChange>,
    target = "",
  ) => {
    if (preview.playingId && names.includes(preview.playingId)) preview.stop();
    setProgress({ kind, done: 0, total: names.length });
    try {
      const change = await send((done, total) => setProgress({ kind, done, total }));
      const summary = changeSummary(kind, change, shelf.label, target);
      notify(summary.text, summary.tone);
    } catch (caught) {
      notify(messageOf(caught, "Le catalogue a refusé la demande."), "error");
    } finally {
      setProgress(null);
      setSelected(new Set());
      lastClicked.current = null;
      await load();
      onChanged();
    }
  };

  const remove = (names: string[]) =>
    void run("removed", names, (onProgress) => removeBankFiles(shelf.id, names, onProgress));

  const move = (names: string[], target: BankDestination) =>
    void run("moved", names, (onProgress) => moveBankFiles(shelf.id, target.id, names, onProgress), target.label);

  const confirmDeletion = async () => {
    setDeleting(true);
    try {
      const trashed = await deleteCollection(shelf.id);
      setConfirmDelete(false);
      onDeleted(shelf, trashed);
    } catch (caught) {
      setConfirmDelete(false);
      notify(messageOf(caught, "Suppression impossible."), "error");
      await load();
      onChanged();
    } finally {
      setDeleting(false);
    }
  };

  const Icon = rotation ? Music : Library;
  const countLabel = searching && page ? `${matched} sur ${titlesLabel(count).toLowerCase()}` : titlesLabel(count);

  return (
    <section className="bacs-main" aria-label={shelf.label}>
      <header className="bacs-head">
        <IconButton
          size="2"
          variant="ghost"
          color="gray"
          className="bacs-back"
          aria-label="Retour à la liste des collections"
          onClick={onBack}
        >
          <ArrowLeft size={18} />
        </IconButton>
        <span className={`bacs-tile bacs-tile--lg${rotation ? " is-habillage" : ""}`} aria-hidden="true">
          <Icon size={18} strokeWidth={1.75} />
        </span>
        <div className="bacs-head-copy">
          <h2 className="bacs-head-title">{shelf.label}</h2>
          <p className="bacs-facts">
            <span>{rotation ? "La musique de l'auto-DJ" : "Collection"}</span>
            <span>
              {titlesLabel(count)}
              {count ? ` · ${formatBytes(bytes)}` : ""}
            </span>
            {!rotation ? (
              <Tooltip content="La sélection de titres qui fait jouer cette collection à l'auto-DJ">
                <Code size="1" variant="ghost" color="gray" tabIndex={0}>
                  grouping:{shelf.id}
                </Code>
              </Tooltip>
            ) : null}
          </p>
        </div>
        <div className="bacs-head-actions">
          <Button size="2" variant="soft" color="gray" disabled={busy} onClick={() => onAdd(shelf.id)}>
            <Upload className="ui-button-icon" />
            <span className="bacs-hide-narrow">Ajouter des titres</span>
            <span className="bacs-show-narrow">Ajouter</span>
          </Button>
          {isAdmin && !rotation ? (
            <DropdownMenu.Root modal={false}>
              <DropdownMenu.Trigger disabled={busy}>
                <IconButton size="2" variant="outline" color="gray" aria-label={`Actions pour la collection ${shelf.label}`}>
                  <MoreHorizontal size={16} />
                </IconButton>
              </DropdownMenu.Trigger>
              <DropdownMenu.Content variant="soft" align="end" className="bacs-menu">
                <DropdownMenu.Item onSelect={() => setRenaming(true)}>
                  <Pencil size={14} aria-hidden="true" />
                  Renommer…
                </DropdownMenu.Item>
                <DropdownMenu.Separator />
                <DropdownMenu.Item color="red" disabled={count > 0} onSelect={() => setConfirmDelete(true)}>
                  <Trash2 size={14} aria-hidden="true" />
                  <span className="bacs-menu-copy">
                    <strong>Supprimer…</strong>
                    {count > 0 ? <span>Possible une fois la collection vide</span> : null}
                  </span>
                </DropdownMenu.Item>
              </DropdownMenu.Content>
            </DropdownMenu.Root>
          ) : null}
        </div>
      </header>

      <div className="bacs-sounds">
        {selected.size > 0 ? (
          <div className="bacs-toolbar bacs-toolbar--selection" role="toolbar" aria-label="Sélection">
            <strong className="bacs-selection-count">
              {titlesLabel(selected.size)} sélectionné{selected.size === 1 ? "" : "s"}
            </strong>
            <span className="bacs-muted bacs-hide-narrow">Maj + clic pour une plage</span>
            <span className="bacs-spacer" />
            <Button size="1" variant="ghost" color="gray" disabled={busy} onClick={() => setSelected(new Set())}>
              <X className="ui-button-icon" />
              Désélectionner
            </Button>
            <Button
              size="1"
              variant="soft"
              color="gray"
              disabled={busy || others.length === 0}
              onClick={() => setMoving([...selected])}
            >
              <FolderInput className="ui-button-icon" />
              Déplacer
            </Button>
            <Button size="1" color="red" variant="soft" disabled={busy} onClick={() => setRemoving([...selected])}>
              <Trash2 className="ui-button-icon" />
              Retirer
            </Button>
          </div>
        ) : (
          <div className="bacs-toolbar" role="toolbar" aria-label="Titres de la collection">
            <TextField.Root
              size="2"
              className="bacs-filter-field"
              placeholder="Titre, artiste, fichier"
              value={query}
              aria-label="Rechercher un titre"
              onChange={(event) => setQuery(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Escape") setQuery("");
              }}
            >
              <TextField.Slot>
                <Search size={15} aria-hidden="true" />
              </TextField.Slot>
            </TextField.Root>
            <Select.Root size="2" value={sort} onValueChange={(value) => setSort(value as BankSort)}>
              <Select.Trigger variant="soft" color="gray" aria-label="Ordre des titres" />
              <Select.Content variant="soft" position="popper" align="end">
                <Select.Item value="name">Par nom</Select.Item>
                <Select.Item value="recent">Récents d'abord</Select.Item>
              </Select.Content>
            </Select.Root>
            <span className="bacs-spacer" />
            <span className="bacs-muted bacs-hide-narrow" aria-live="polite">
              {countLabel}
            </span>
          </div>
        )}

        {progress ? (
          <div className="bacs-import" role="status" aria-live="polite">
            <Spinner size="1" />
            <span className="bacs-import-copy">
              <strong>
                {progress.kind === "removed" ? "Retrait" : "Déplacement"} de {titlesLabel(progress.total).toLowerCase()}
              </strong>
              <span>
                {progress.done} / {progress.total}
              </span>
            </span>
            <span className="bacs-bar" aria-hidden="true">
              <i style={{ width: `${percentOf(progress.done, progress.total)}%` }} />
            </span>
          </div>
        ) : null}

        {page?.partial ? (
          <div className="banque-note" role="status">
            <span>Certains fichiers sont encore en lecture : la recherche peut en trouver d'autres dans un instant.</span>
            <Button size="1" variant="soft" color="gray" onClick={() => void load()}>
              <RefreshCw className="ui-button-icon" />
              Relancer
            </Button>
          </div>
        ) : null}

        {problem && page ? (
          <div className="banque-note is-danger" role="alert">
            <span>La liste n'a pas pu se relire : {problem}</span>
            <Button size="1" variant="soft" color="gray" onClick={() => void load()}>
              <RefreshCw className="ui-button-icon" />
              Réessayer
            </Button>
          </div>
        ) : null}

        <div className="bacs-table-wrap">
          {!page ? (
            problem ? (
              <ErrorState title="Collection illisible" description={problem} onRetry={() => void load()} />
            ) : (
              <LoadingState label="Lecture de la collection…" />
            )
          ) : count === 0 ? (
            <div className="bacs-dropzone">
              <span className="bacs-dropzone-icon" aria-hidden="true">
                <Upload size={20} />
              </span>
              <strong>{rotation ? "La rotation est vide" : "Cette collection est vide"}</strong>
              <p>
                {rotation
                  ? "Envoie de la musique : l'auto-DJ la joue une fois indexée."
                  : "Envoie-lui des titres, ou déplaces-y ceux d'une autre collection."}
                {isAdmin && !rotation ? " Vide, elle peut aussi se supprimer, par le menu ⋯ en haut." : ""}
              </p>
              <div className="bacs-dropzone-actions">
                <Button size="2" highContrast onClick={() => onAdd(shelf.id)}>
                  <Upload className="ui-button-icon" />
                  Ajouter des titres
                </Button>
              </div>
            </div>
          ) : files.length === 0 ? (
            <div className="bacs-table-empty">
              <p>{searching ? `Aucun titre ne correspond à « ${query.trim()} ».` : "Aucun titre."}</p>
              {searching ? (
                <Button size="1" variant="soft" color="gray" onClick={() => setQuery("")}>
                  Effacer la recherche
                </Button>
              ) : null}
            </div>
          ) : (
            <table className="bacs-table">
              <thead>
                <tr>
                  <th className="c-check">
                    <Checkbox
                      size="1"
                      checked={allSelected ? true : someSelected ? "indeterminate" : false}
                      disabled={busy}
                      aria-label="Tout sélectionner"
                      onCheckedChange={(checked) =>
                        setSelected(checked === true ? new Set(files.map((file) => file.name)) : new Set())
                      }
                    />
                  </th>
                  <th className="c-play">
                    <span className="ui-visually-hidden">Écouter</span>
                  </th>
                  <th className="c-title">Titre</th>
                  <th className="c-last">Modifié</th>
                  <th className="c-len">Durée</th>
                  <th className="c-size">Taille</th>
                  <th className="c-more">
                    <span className="ui-visually-hidden">Actions</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {files.map((file) => (
                  <BankRow
                    key={file.name}
                    file={file}
                    now={now}
                    busy={busy}
                    canMove={others.length > 0}
                    selected={selected.has(file.name)}
                    playing={preview.playingId === file.name}
                    onToggle={(shift) => {
                      // Read now: React may run the update after the next line.
                      const last = lastClicked.current;
                      setSelected((before) => toggleSelection(order, before, last, file.name, shift));
                      lastClicked.current = file.name;
                    }}
                    onPlay={() => preview.toggle(file.name)}
                    onMove={() => setMoving([file.name])}
                    onRemove={() => setRemoving([file.name])}
                  />
                ))}
              </tbody>
            </table>
          )}
          {page && !page.partial && files.length > 0 && files.length < matched ? (
            <div className="banque-more">
              <Button size="2" variant="soft" color="gray" disabled={loadingMore} onClick={() => void loadMore()}>
                {loadingMore ? <Spinner size="1" /> : null}
                Afficher {Math.min(BANK_PAGE, matched - files.length)} de plus · {files.length} sur {matched}
              </Button>
            </div>
          ) : null}
        </div>
      </div>

      <ConfirmDialog
        open={removing != null}
        onOpenChange={(open) => {
          if (!open) setRemoving(null);
        }}
        title={removing?.length === 1 ? "Retirer ce titre ?" : `Retirer ${titlesLabel(removing?.length ?? 0).toLowerCase()} ?`}
        description={
          <>
            {removing?.length === 1 ? "Le fichier part" : "Les fichiers partent"} dans la corbeille de la banque, sur la
            machine de la station : rien n'est effacé. L'auto-DJ ne {removing?.length === 1 ? "le" : "les"} joue plus
            après le prochain passage de l'indexation, environ une minute. Une diffusion de l'Agenda qui joue un de ces
            fichiers ne le trouvera plus.
          </>
        }
        confirmLabel={removing?.length === 1 ? "Retirer le titre" : `Retirer ${titlesLabel(removing?.length ?? 0).toLowerCase()}`}
        onConfirm={() => {
          const names = removing ?? [];
          setRemoving(null);
          if (names.length) remove(names);
        }}
      />

      {moving ? (
        <MoveDialog
          names={moving}
          from={shelf}
          options={others}
          onClose={() => setMoving(null)}
          onMove={(target) => {
            const names = moving;
            setMoving(null);
            move(names, target);
          }}
        />
      ) : null}

      {renaming ? (
        <RenameDialog
          shelf={shelf}
          shelves={shelves}
          onClose={() => setRenaming(false)}
          onRenamed={(destination) => {
            setRenaming(false);
            onRenamed(destination, shelf.label);
          }}
        />
      ) : null}

      <ConfirmDialog
        open={confirmDelete}
        onOpenChange={(open) => {
          if (!deleting) setConfirmDelete(open);
        }}
        busy={deleting}
        title={`Supprimer la collection « ${shelf.label} » ?`}
        description={
          <>
            Elle est vide : son dossier quitte la banque, avec son dépôt. Une sélection de titres{" "}
            <Code size="1">grouping:{shelf.id}</Code> ne trouvera plus rien : retire-la ensuite dans Programmation.
          </>
        }
        confirmLabel="Supprimer la collection"
        onConfirm={confirmDeletion}
      />
    </section>
  );
}

function BankRow({
  file,
  now,
  busy,
  canMove,
  selected,
  playing,
  onToggle,
  onPlay,
  onMove,
  onRemove,
}: {
  file: BankFile;
  now: number;
  busy: boolean;
  canMove: boolean;
  selected: boolean;
  playing: boolean;
  onToggle: (shift: boolean) => void;
  onPlay: () => void;
  onMove: () => void;
  onRemove: () => void;
}) {
  const labels = bankLabels(file);
  const audio = isAudioName(file.name);
  const folder = subfolderOf(file.name);
  const when = new Date(file.modified);
  const length = file.duration != null ? formatClock(file.duration) : "";

  return (
    <tr
      className={["bacs-track-row", selected ? "is-selected" : "", playing ? "is-playing" : ""].filter(Boolean).join(" ")}
      aria-selected={selected}
    >
      <td className="c-check">
        <Checkbox
          size="1"
          checked={selected}
          disabled={busy}
          aria-label={`Sélectionner ${labels.title}`}
          onClick={(event) => {
            event.preventDefault();
            event.stopPropagation();
            onToggle(event.shiftKey);
          }}
        />
      </td>
      <td className="c-play">
        {audio ? (
          <button
            type="button"
            className={`bacs-play${playing ? " is-on" : ""}`}
            onClick={onPlay}
            aria-label={playing ? "Arrêter la pré-écoute" : `Pré-écouter ${labels.title}`}
          >
            {playing ? (
              <span className="bacs-eq" aria-hidden="true">
                <i />
                <i />
                <i />
              </span>
            ) : (
              <Play size={13} />
            )}
          </button>
        ) : null}
      </td>
      <td className="c-title">
        <div className="bacs-cell-title">
          <span className="bacs-track" title={file.name}>
            {labels.title}
          </span>
          <span className="bacs-artist">
            {labels.artist ? <span>{labels.artist}</span> : null}
            {folder ? <span className="banque-subfolder">{folder}</span> : null}
            {!audio ? (
              <Badge size="1" variant="soft" color="gray" className="bacs-badge">
                Pas un son
              </Badge>
            ) : null}
            {length ? <span className="bacs-inline-len">{length}</span> : null}
          </span>
        </div>
      </td>
      <td className="c-last" title={Number.isNaN(when.getTime()) ? undefined : when.toLocaleString("fr-FR")}>
        {modifiedLabel(file.modified, now)}
      </td>
      <td className="c-len">{length || "—"}</td>
      <td className="c-size">{formatBytes(file.bytes)}</td>
      <td className="c-more">
        <DropdownMenu.Root modal={false}>
          <DropdownMenu.Trigger disabled={busy}>
            <IconButton size="1" variant="ghost" color="gray" aria-label={`Actions pour ${labels.title}`}>
              <MoreHorizontal size={15} />
            </IconButton>
          </DropdownMenu.Trigger>
          <DropdownMenu.Content variant="soft" align="end" className="bacs-menu">
            {audio ? (
              <DropdownMenu.Item onSelect={onPlay}>
                <Play size={14} aria-hidden="true" />
                {playing ? "Arrêter la pré-écoute" : "Pré-écouter"}
              </DropdownMenu.Item>
            ) : null}
            <DropdownMenu.Item disabled={!canMove} onSelect={onMove}>
              <FolderInput size={14} aria-hidden="true" />
              Déplacer vers…
            </DropdownMenu.Item>
            <DropdownMenu.Separator />
            <DropdownMenu.Item color="red" onSelect={onRemove}>
              <Trash2 size={14} aria-hidden="true" />
              Retirer…
            </DropdownMenu.Item>
          </DropdownMenu.Content>
        </DropdownMenu.Root>
      </td>
    </tr>
  );
}

function MoveDialog({
  names,
  from,
  options,
  onClose,
  onMove,
}: {
  names: string[];
  from: BankShelf;
  options: BankShelf[];
  onClose: () => void;
  onMove: (target: BankDestination) => void;
}) {
  const [target, setTarget] = useState(options[0]?.id ?? "");
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
          L'auto-DJ {names.length === 1 ? "le" : "les"} retrouve dans {value ? value.label : "sa destination"} au
          prochain passage de l'indexation, environ une minute : Beets {names.length === 1 ? "le relit" : "les relit"}{" "}
          comme {names.length === 1 ? "un titre nouveau" : "des titres nouveaux"}. Une diffusion de l'Agenda qui joue un
          de ces fichiers ne le trouvera plus.
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

function RenameDialog({
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
