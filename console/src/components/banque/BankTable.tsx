import { Badge, Button, Checkbox, Code, DropdownMenu, IconButton, Spinner, TextField, Tooltip } from "@radix-ui/themes";
import {
  ArrowDown,
  ArrowLeft,
  ArrowUp,
  CloudOff,
  FolderInput,
  Layers,
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
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useAccount } from "../../api/AccountContext";
import {
  bankShelves,
  changeSummary,
  deleteCollection,
  moveBankFiles,
  removeBankFiles,
  titlesLabel,
  type BankChange,
  type BankShelf,
} from "../../api/bankContent";
import {
  COLUMNS,
  TITLES_PAGE,
  cell,
  ficheState,
  fileName,
  groupLabel,
  groupsOf,
  nameInShelf,
  nextSort,
  rankingOf,
  readState,
  titlesCount,
  titlesQuery,
  writeState,
  type BankFacet,
  type BankTitle,
  type BankTitlesPage,
  type Ranking,
  type TableState,
  type TitleSort,
} from "../../api/bankTitles";
import { createBank } from "../../api/banks";
import { API_PREFIX, ApiRequestError, apiGet } from "../../api/client";
import { formatClock, percentOf } from "../../api/soundsView";
import { usePreview } from "../../lib/usePreview";
import { AppToast, useAppToast } from "../../ui/AppToast";
import { ConfirmDialog } from "../../ui/ConfirmDialog";
import { ErrorState, LoadingState } from "../../ui/DataState";
import { EmptyState } from "../../ui/EmptyState";
import { MoveDialog, RenameDialog } from "./CollectionView";
import { CreateBankDialog } from "./CreateBankDialog";
import { RANKING_ICONS, RankingList } from "./RankingList";
import { TitleSheet } from "./TitleSheet";

type Progress = { kind: "removed" | "moved"; done: number; total: number };

function messageOf(caught: unknown, fallback: string): string {
  return caught instanceof Error && caught.message ? caught.message : fallback;
}

/**
 * Sons → Banque, vue Contenu, once the bank's tidying is turned on (FON-64):
 * every title of the library in one table, ranged by collection, artist, family
 * or album. Ranged by collection, a collection keeps today's gestures: listen,
 * remove, move, rename and delete. The state stays in the address.
 */
export function BankTable({ onAdd }: { onAdd: (id: string) => void }) {
  const { isAdmin } = useAccount();
  const [params, setParams] = useSearchParams();
  const state = useMemo(() => readState(params), [params]);
  const [typed, setTyped] = useState(state.q);
  const [page, setPage] = useState<BankTitlesPage | null>(null);
  const [titles, setTitles] = useState<BankTitle[]>([]);
  const [groups, setGroups] = useState<Partial<Record<Ranking, BankFacet[]>>>({});
  const [problem, setProblem] = useState("");
  const [closed, setClosed] = useState<"engine" | "off" | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [shelves, setShelves] = useState<BankShelf[]>([]);
  const [shelvesProblem, setShelvesProblem] = useState("");
  const [view, setView] = useState<"list" | "detail">(state.group !== null ? "detail" : "list");
  const [openId, setOpenId] = useState<number | null>(null);
  const [selected, setSelected] = useState<Set<number>>(() => new Set());
  const [progress, setProgress] = useState<Progress | null>(null);
  const [removing, setRemoving] = useState<number[] | null>(null);
  const [moving, setMoving] = useState<number[] | null>(null);
  const [renaming, setRenaming] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [creating, setCreating] = useState<string | null>(null);
  const { toast, show, dismiss } = useAppToast();
  const ticket = useRef(0);
  const preview = usePreview(
    (message) => show(message, "error"),
    (id) => `${API_PREFIX}/autodj/beets/${encodeURIComponent(id)}`,
  );

  const update = useCallback(
    (change: Partial<TableState>) => setParams(writeState(params, { ...state, ...change }), { replace: true }),
    [params, setParams, state],
  );

  const loadShelves = useCallback(async () => {
    try {
      setShelves(await bankShelves());
      setShelvesProblem("");
    } catch (caught) {
      setShelvesProblem(messageOf(caught, "Le catalogue ne répond pas."));
    }
  }, []);

  const load = useCallback(async () => {
    const mine = ++ticket.current;
    try {
      const next = await apiGet<BankTitlesPage>(`/media/titles.json${titlesQuery(state)}`);
      if (mine !== ticket.current) return;
      setPage(next);
      setTitles(next.titles);
      const facets = next.facets[state.ranking];
      if (facets) setGroups((before) => ({ ...before, [state.ranking]: facets }));
      setProblem("");
      setClosed(null);
    } catch (caught) {
      if (mine !== ticket.current) return;
      if (caught instanceof ApiRequestError && caught.status === 404) setClosed("engine");
      else if (caught instanceof ApiRequestError && caught.status === 409) setClosed("off");
      else setProblem(messageOf(caught, "Le tableau ne s'est pas lu. Réessaie."));
    }
  }, [state]);

  useEffect(() => {
    void loadShelves();
  }, [loadShelves]);

  useEffect(() => {
    void load();
  }, [load]);

  // The text waits for the typing to stop before it goes in the address.
  useEffect(() => {
    if (typed === state.q) return;
    const timer = window.setTimeout(() => update({ q: typed }), 250);
    return () => window.clearTimeout(timer);
  }, [state.q, typed, update]);

  // What is selected follows what is shown.
  useEffect(() => {
    setSelected(new Set());
  }, [state.ranking, state.group, state.q, state.sort, state.order]);

  const loadMore = async () => {
    if (!page || loadingMore) return;
    const mine = ticket.current;
    setLoadingMore(true);
    try {
      const next = await apiGet<BankTitlesPage>(`/media/titles.json${titlesQuery(state, titles.length)}`);
      if (mine !== ticket.current) return;
      setTitles((before) => [...before, ...next.titles.filter((title) => !before.some((item) => item.id === title.id))]);
      setPage(next);
    } catch (caught) {
      show(messageOf(caught, "La suite du tableau ne s'est pas lue."), "error");
    } finally {
      setLoadingMore(false);
    }
  };

  const rankingGroups = groupsOf(state.ranking, groups[state.ranking] ?? [], shelves);
  const heading = groupLabel(state.ranking, state.group, rankingGroups);
  // Ranged by collection, one collection of the catalogue: today's gestures.
  const shelf =
    state.ranking === "collection" && state.group ? (shelves.find((item) => item.id === state.group) ?? null) : null;
  const gestures = shelf != null;
  const others = shelves.filter((item) => item.id !== shelf?.id);
  const busy = progress != null;
  const opened = titles.find((title) => title.id === openId) ?? null;
  const allSelected = gestures && titles.length > 0 && titles.every((title) => selected.has(title.id));
  const someSelected = gestures && !allSelected && titles.some((title) => selected.has(title.id));
  const collectionLabel = (id: string) => shelves.find((item) => item.id === id)?.label || id;

  const choose = (group: string | null) => {
    setOpenId(null);
    update({ group });
    setView("detail");
  };

  const namesOf = (ids: number[]) =>
    shelf
      ? ids
          .map((id) => titles.find((title) => title.id === id))
          .map((title) => (title ? nameInShelf(title, shelf) : null))
          .filter((name): name is string => Boolean(name))
      : [];

  const run = async (
    kind: Progress["kind"],
    ids: number[],
    send: (names: string[], onProgress: (done: number, total: number) => void) => Promise<BankChange>,
    target = "",
  ) => {
    if (!shelf) return;
    const names = namesOf(ids);
    if (preview.playingId && ids.map(String).includes(preview.playingId)) preview.stop();
    setProgress({ kind, done: 0, total: names.length });
    try {
      const change = await send(names, (done, total) => setProgress({ kind, done, total }));
      const summary = changeSummary(kind, change, shelf.label, target);
      show(summary.text, summary.tone);
    } catch (caught) {
      show(messageOf(caught, "Le catalogue a refusé la demande."), "error");
    } finally {
      setProgress(null);
      setSelected(new Set());
      await Promise.all([load(), loadShelves()]);
    }
  };

  const confirmDeletion = async () => {
    if (!shelf) return;
    setDeleting(true);
    try {
      await deleteCollection(shelf.id);
      setConfirmDelete(false);
      show(`Collection « ${shelf.label} » supprimée.`, "success");
      choose(null);
      setView("list");
    } catch (caught) {
      setConfirmDelete(false);
      show(messageOf(caught, "Suppression impossible."), "error");
    } finally {
      setDeleting(false);
      await loadShelves();
    }
  };

  if (closed) {
    return (
      <div className="bacs-page">
        <EmptyState
          icon={CloudOff}
          title={closed === "engine" ? "Mets à jour le moteur" : "Tableau fermé"}
          description={
            closed === "engine"
              ? "Le moteur de cette station ne sait pas encore montrer toute la banque dans un tableau."
              : "Le rangement de la banque a été coupé sur cette station. Recharge la page pour retrouver la vue des collections."
          }
        />
      </div>
    );
  }

  const Icon =
    state.group === null
      ? Layers
      : state.ranking === "collection" && state.group === "rotation"
        ? Music
        : RANKING_ICONS[state.ranking];
  const count = page?.matched ?? 0;

  return (
    <div className="bacs-page">
      <div
        className="bacs banque-shelves banque-table"
        data-view={view}
        data-inspector={opened ? "open" : "closed"}
      >
        <RankingList
          ranking={state.ranking}
          groups={rankingGroups}
          total={page?.total ?? null}
          selected={state.group}
          loading={!groups[state.ranking]}
          onRanking={(ranking) => {
            setOpenId(null);
            update({ ranking, group: null });
          }}
          onSelect={choose}
          onCreate={isAdmin && state.ranking === "collection" ? (label) => setCreating(label) : undefined}
        />

        <section className="bacs-main" aria-label={heading}>
          <header className="bacs-head">
            <IconButton
              size="2"
              variant="ghost"
              color="gray"
              className="bacs-back"
              aria-label={`Retour à la liste : ${rankingOf(state.ranking).plural.toLowerCase()}`}
              onClick={() => setView("list")}
            >
              <ArrowLeft size={18} />
            </IconButton>
            <span className={`bacs-tile bacs-tile--lg${state.group === "rotation" ? " is-habillage" : ""}`} aria-hidden="true">
              <Icon size={18} strokeWidth={1.75} />
            </span>
            <div className="bacs-head-copy">
              <h2 className="bacs-head-title">{heading}</h2>
              <p className="bacs-facts">
                <span>{state.group === null ? "Rotation et collections" : rankingOf(state.ranking).label}</span>
                <span>{page ? titlesCount(page.matched) : "…"}</span>
                {shelf && shelf.group !== "rotation" ? (
                  <Tooltip content="La sélection de titres qui fait jouer cette collection à l'auto-DJ">
                    <Code size="1" variant="ghost" color="gray" tabIndex={0}>
                      grouping:{shelf.id}
                    </Code>
                  </Tooltip>
                ) : null}
              </p>
            </div>
            {shelf ? (
              <div className="bacs-head-actions">
                <Button size="2" variant="soft" color="gray" disabled={busy} onClick={() => onAdd(shelf.id)}>
                  <Upload className="ui-button-icon" />
                  <span className="bacs-hide-narrow">Ajouter des titres</span>
                  <span className="bacs-show-narrow">Ajouter</span>
                </Button>
                {isAdmin && shelf.group !== "rotation" ? (
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
                      <DropdownMenu.Item color="red" disabled={shelf.count > 0} onSelect={() => setConfirmDelete(true)}>
                        <Trash2 size={14} aria-hidden="true" />
                        <span className="bacs-menu-copy">
                          <strong>Supprimer…</strong>
                          {shelf.count > 0 ? <span>Possible une fois la collection vide</span> : null}
                        </span>
                      </DropdownMenu.Item>
                    </DropdownMenu.Content>
                  </DropdownMenu.Root>
                ) : null}
              </div>
            ) : null}
          </header>

          <div className="bacs-sounds">
            {gestures && selected.size > 0 ? (
              <div className="bacs-toolbar bacs-toolbar--selection" role="toolbar" aria-label="Sélection">
                <strong className="bacs-selection-count">
                  {titlesLabel(selected.size)} sélectionné{selected.size === 1 ? "" : "s"}
                </strong>
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
                <Button size="1" color="red" variant="soft" highContrast disabled={busy} onClick={() => setRemoving([...selected])}>
                  <Trash2 className="ui-button-icon" />
                  Retirer
                </Button>
              </div>
            ) : (
              <div className="bacs-toolbar" role="toolbar" aria-label="Titres">
                <TextField.Root
                  size="2"
                  className="bacs-filter-field"
                  placeholder="Titre, artiste, album, fichier"
                  value={typed}
                  aria-label="Rechercher un titre"
                  onChange={(event) => setTyped(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Escape") setTyped("");
                  }}
                >
                  <TextField.Slot>
                    <Search size={15} aria-hidden="true" />
                  </TextField.Slot>
                </TextField.Root>
                <span className="bacs-spacer" />
                <span className="bacs-muted bacs-hide-narrow" aria-live="polite">
                  {page ? (state.q.trim() ? `${titlesCount(page.matched)} trouvés` : titlesCount(page.matched)) : ""}
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

            {shelvesProblem && state.ranking === "collection" ? (
              <div className="banque-note" role="status">
                <span>Les noms des collections ne se sont pas lus : {shelvesProblem}</span>
                <Button size="1" variant="soft" color="gray" onClick={() => void loadShelves()}>
                  <RefreshCw className="ui-button-icon" />
                  Réessayer
                </Button>
              </div>
            ) : null}

            {problem && page ? (
              <div className="banque-note is-danger" role="alert">
                <span>Le tableau n'a pas pu se relire : {problem}</span>
                <Button size="1" variant="soft" color="gray" onClick={() => void load()}>
                  <RefreshCw className="ui-button-icon" />
                  Réessayer
                </Button>
              </div>
            ) : null}

            <div className="bacs-table-wrap">
              {!page ? (
                problem ? (
                  <ErrorState title="Banque illisible" description={problem} onRetry={() => void load()} />
                ) : (
                  <LoadingState label="Lecture de la banque…" />
                )
              ) : titles.length === 0 ? (
                <div className="bacs-table-empty">
                  <p>
                    {state.q.trim()
                      ? `Aucun titre ne correspond à « ${state.q.trim()} ».`
                      : page.total === 0
                        ? "La bibliothèque n'a encore aucun titre : envoie de la musique dans « Ajouter »."
                        : "Aucun titre ici."}
                  </p>
                  {state.q.trim() ? (
                    <Button size="1" variant="soft" color="gray" onClick={() => setTyped("")}>
                      Effacer la recherche
                    </Button>
                  ) : shelf ? (
                    <Button size="1" variant="soft" color="gray" onClick={() => onAdd(shelf.id)}>
                      <Upload className="ui-button-icon" />
                      Ajouter des titres
                    </Button>
                  ) : null}
                </div>
              ) : (
                <table className={`bacs-table banque-titles${gestures ? " has-gestures" : ""}`} aria-rowcount={count}>
                  <thead>
                    <tr>
                      {gestures ? (
                        <th className="c-check">
                          <Checkbox
                            size="1"
                            checked={allSelected ? true : someSelected ? "indeterminate" : false}
                            disabled={busy}
                            aria-label="Tout sélectionner"
                            onCheckedChange={(checked) =>
                              setSelected(checked === true ? new Set(titles.map((title) => title.id)) : new Set())
                            }
                          />
                        </th>
                      ) : null}
                      <th className="c-play">
                        <span className="ui-visually-hidden">Écouter</span>
                      </th>
                      {COLUMNS.map((column) =>
                        column.key === "fiche" ? (
                          <th key={column.key} className="c-fiche">
                            {column.label}
                          </th>
                        ) : (
                          <SortHeader
                            key={column.key}
                            column={column.key}
                            label={column.label}
                            state={state}
                            onSort={(key) => update(nextSort(state, key))}
                          />
                        ),
                      )}
                      {gestures ? (
                        <th className="c-more">
                          <span className="ui-visually-hidden">Actions</span>
                        </th>
                      ) : null}
                    </tr>
                  </thead>
                  <tbody>
                    {titles.map((title) => (
                      <TitleRow
                        key={title.id}
                        title={title}
                        gestures={gestures}
                        busy={busy}
                        canMove={others.length > 0}
                        selected={selected.has(title.id)}
                        opened={openId === title.id}
                        playing={preview.playingId === String(title.id)}
                        onToggle={() =>
                          setSelected((before) => {
                            const next = new Set(before);
                            if (next.has(title.id)) next.delete(title.id);
                            else next.add(title.id);
                            return next;
                          })
                        }
                        onOpen={() => setOpenId(title.id)}
                        onPlay={() => preview.toggle(String(title.id))}
                        onMove={() => setMoving([title.id])}
                        onRemove={() => setRemoving([title.id])}
                      />
                    ))}
                  </tbody>
                </table>
              )}
              {page && titles.length > 0 && titles.length < page.matched ? (
                <div className="banque-more">
                  <Button size="2" variant="soft" color="gray" disabled={loadingMore} onClick={() => void loadMore()}>
                    {loadingMore ? <Spinner size="1" /> : null}
                    Afficher {Math.min(TITLES_PAGE, page.matched - titles.length)} de plus · {titles.length} sur{" "}
                    {page.matched}
                  </Button>
                </div>
              ) : null}
            </div>
          </div>
        </section>

        {opened ? (
          <>
            <button type="button" className="bacs-scrim" aria-label="Fermer la fiche" tabIndex={-1} onClick={() => setOpenId(null)} />
            <TitleSheet
              title={opened}
              collection={opened.collection ? collectionLabel(opened.collection) : ""}
              playing={preview.playingId === String(opened.id)}
              onPlay={() => preview.toggle(String(opened.id))}
              onClose={() => {
                const id = opened.id;
                setOpenId(null);
                requestAnimationFrame(() => document.querySelector<HTMLElement>(`[data-title-open="${id}"]`)?.focus());
              }}
            />
          </>
        ) : null}
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
          const ids = removing ?? [];
          setRemoving(null);
          if (ids.length && shelf) void run("removed", ids, (names, onProgress) => removeBankFiles(shelf.id, names, onProgress));
        }}
      />

      {moving && shelf ? (
        <MoveDialog
          names={namesOf(moving)}
          from={shelf}
          options={others}
          onClose={() => setMoving(null)}
          onMove={(target) => {
            const ids = moving;
            setMoving(null);
            void run(
              "moved",
              ids,
              (names, onProgress) => moveBankFiles(shelf.id, target.id, names, onProgress),
              target.label,
            );
          }}
        />
      ) : null}

      {renaming && shelf ? (
        <RenameDialog
          shelf={shelf}
          shelves={shelves}
          onClose={() => setRenaming(false)}
          onRenamed={(destination) => {
            setRenaming(false);
            show(`La collection « ${shelf.label} » s'appelle maintenant « ${destination.label} ».`, "success");
            void loadShelves();
          }}
        />
      ) : null}

      <ConfirmDialog
        open={confirmDelete}
        onOpenChange={(open) => {
          if (!deleting) setConfirmDelete(open);
        }}
        busy={deleting}
        title={`Supprimer la collection « ${shelf?.label ?? ""} » ?`}
        description={
          <>
            Elle est vide : son dossier quitte la banque, avec son dépôt. Une sélection de titres{" "}
            <Code size="1">grouping:{shelf?.id}</Code> ne trouvera plus rien : retire-la ensuite dans Programmation.
          </>
        }
        confirmLabel="Supprimer la collection"
        onConfirm={confirmDeletion}
      />

      <CreateBankDialog
        open={creating != null}
        onOpenChange={(open) => {
          if (!open) setCreating(null);
        }}
        initialLabel={creating ?? ""}
        destinations={shelves}
        onCreate={async (label, folder) => {
          const created = await createBank(label, folder);
          await loadShelves();
          choose(created.id);
          show(`Collection « ${created.label} » créée. « Ajouter des titres » y envoie des fichiers.`, "success");
        }}
      />
      <AppToast toast={toast} onDismiss={dismiss} />
    </div>
  );
}

function SortHeader({
  column,
  label,
  state,
  onSort,
}: {
  column: TitleSort;
  label: string;
  state: TableState;
  onSort: (key: TitleSort) => void;
}) {
  const active = state.sort === column;
  const Arrow = state.order === "desc" ? ArrowDown : ArrowUp;
  return (
    <th className={`c-${column}`} aria-sort={active ? (state.order === "asc" ? "ascending" : "descending") : "none"}>
      <button type="button" className={`banque-sort${active ? " is-active" : ""}`} onClick={() => onSort(column)}>
        {label}
        {active ? <Arrow size={12} aria-hidden="true" /> : null}
      </button>
    </th>
  );
}

function TitleRow({
  title,
  gestures,
  busy,
  canMove,
  selected,
  opened,
  playing,
  onToggle,
  onOpen,
  onPlay,
  onMove,
  onRemove,
}: {
  title: BankTitle;
  gestures: boolean;
  busy: boolean;
  canMove: boolean;
  selected: boolean;
  opened: boolean;
  playing: boolean;
  onToggle: () => void;
  onOpen: () => void;
  onPlay: () => void;
  onMove: () => void;
  onRemove: () => void;
}) {
  const name = title.title || fileName(title.path);
  const fiche = ficheState(title.missing);
  const length = title.duration ? formatClock(title.duration) : "";
  return (
    <tr
      className={["bacs-track-row", selected || opened ? "is-selected" : "", playing ? "is-playing" : ""].filter(Boolean).join(" ")}
      aria-selected={gestures ? selected : undefined}
    >
      {gestures ? (
        <td className="c-check">
          <Checkbox size="1" checked={selected} disabled={busy} aria-label={`Sélectionner ${name}`} onCheckedChange={onToggle} />
        </td>
      ) : null}
      <td className="c-play">
        <button
          type="button"
          className={`bacs-play${playing ? " is-on" : ""}`}
          onClick={onPlay}
          aria-label={playing ? "Arrêter la pré-écoute" : `Pré-écouter ${name}`}
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
      </td>
      <td className="c-title">
        <div className="bacs-cell-title">
          <button type="button" className="banque-open" data-title-open={title.id} title={title.path} onClick={onOpen}>
            {name}
          </button>
          <span className="bacs-artist banque-narrow-artist">
            {title.artist ? <span>{title.artist}</span> : null}
            {length ? <span className="bacs-inline-len">{length}</span> : null}
          </span>
        </div>
      </td>
      <td className="c-artist">{cell(title.artist)}</td>
      <td className="c-album">{cell(title.album)}</td>
      <td className="c-famille">{cell(title.famille_label)}</td>
      <td className="c-genre">{cell(title.genre)}</td>
      <td className="c-year">{cell(title.year)}</td>
      <td className="c-duration">{length || "—"}</td>
      <td className="c-fiche">
        <Tooltip content={fiche.detail}>
          <Badge size="1" variant="soft" color={fiche.complete ? "green" : "gray"} tabIndex={0}>
            {fiche.label}
          </Badge>
        </Tooltip>
      </td>
      {gestures ? (
        <td className="c-more">
          <DropdownMenu.Root modal={false}>
            <DropdownMenu.Trigger disabled={busy}>
              <IconButton size="1" variant="ghost" color="gray" aria-label={`Actions pour ${name}`}>
                <MoreHorizontal size={15} />
              </IconButton>
            </DropdownMenu.Trigger>
            <DropdownMenu.Content variant="soft" align="end" className="bacs-menu">
              <DropdownMenu.Item onSelect={onPlay}>
                <Play size={14} aria-hidden="true" />
                {playing ? "Arrêter la pré-écoute" : "Pré-écouter"}
              </DropdownMenu.Item>
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
      ) : null}
    </tr>
  );
}
