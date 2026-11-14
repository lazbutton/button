import { Badge, Button, Checkbox, Code, DropdownMenu, IconButton, Spinner, TextField, Tooltip } from "@radix-ui/themes";
import {
  ArrowDown,
  ArrowLeft,
  ArrowUp,
  CloudOff,
  FolderInput,
  Layers,
  ListPlus,
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
import { Link, useSearchParams } from "react-router-dom";
import { useAccount } from "../../api/AccountContext";
import {
  bankShelves,
  changeSummary,
  deleteCollection,
  moveBankFiles,
  removeBankFiles,
  removeNote,
  titlesLabel,
  type BankChange,
  type BankShelf,
} from "../../api/bankContent";
import {
  TITLES_PAGE,
  cell,
  columnLabel,
  ficheState,
  fileName,
  groupLabel,
  groupsOf,
  nameInShelf,
  nextSort,
  rankingOf,
  readState,
  sameAsView,
  stateOfView,
  tableMinWidth,
  titlesCount,
  titlesQuery,
  viewStateOf,
  writeState,
  type BankFacet,
  type ColumnKey,
  type SavedView,
  type BankTitle,
  type BankTitlesPage,
  type Ranking,
  type TableState,
  type TitleSort,
} from "../../api/bankTitles";
import { createBank } from "../../api/banks";
import { roleAtLeast } from "../../api/roles";
import { filtersFromTable, selectionLink, tableMakesSelection } from "../../api/selectionFilters";
import { API_PREFIX, ApiRequestError, apiDeleteJson, apiGet, apiPostJson, apiPut } from "../../api/client";
import { formatClock, percentOf } from "../../api/soundsView";
import {
  needsConfirmationText,
  savedMessage,
  titleName,
  undoneMessage,
  yearProblem,
  type EditLot,
  type EditOutcome,
} from "../../api/titleEdits";
import { cellLot, isGridField, nextCell, pasteLot, pasteQuestion, type Move } from "../../api/titleGrid";
import type { FicheField } from "../../api/bankTitles";
import { usePreview } from "../../lib/usePreview";
import { AppToast, useAppToast } from "../../ui/AppToast";
import { ConfirmDialog } from "../../ui/ConfirmDialog";
import { ErrorState, LoadingState } from "../../ui/DataState";
import { EmptyState } from "../../ui/EmptyState";
import { cartsBeforeRemoval } from "../../api/bankCarts";
import { AddToCartDialog } from "./AddToCartDialog";
import { ColumnsPicker } from "./ColumnsPicker";
import { MoveDialog, RenameDialog } from "./CollectionView";
import { CreateBankDialog } from "./CreateBankDialog";
import { RANKING_ICONS, RankingList } from "./RankingList";
import { GridCell } from "./GridCell";
import { ConfirmLotDialog, EditTitlesDialog, editTitles, needsConfirmation, undoTitles } from "./TitleEditing";
import { TitleSheet } from "./TitleSheet";
import { ViewsMenu } from "./ViewsMenu";

type Progress = { kind: "removed" | "moved"; done: number; total: number };

// The view open stays in the address; the browser only keeps the last one opened.
const VIEW_PARAM = "gardee";
const LAST_VIEW = "button.banque.derniere-vue";

function lastView(): number | null {
  try {
    const raw = window.localStorage.getItem(LAST_VIEW);
    return raw && /^\d+$/.test(raw) ? Number(raw) : null;
  } catch {
    return null;
  }
}

function rememberView(id: number | null): void {
  try {
    if (id == null) window.localStorage.removeItem(LAST_VIEW);
    else window.localStorage.setItem(LAST_VIEW, String(id));
  } catch {
    // Private window or blocked storage: the view is not reopened next time, that is all.
  }
}

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
  const { isAdmin, role, account } = useAccount();
  // FON-66 : la fiche se corrige, seule ou par lot, pour le Programmateur.
  const canEdit = account?.features?.title_edits === true && (isAdmin || account.permissions.autodj === true);
  // FON-69 : des titres de la banque dans un bac, sans copie, pour qui gère les bacs.
  const canCart = isAdmin || account?.permissions.carts === true;
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
  const [editing, setEditing] = useState<BankTitle[] | null>(null);
  const [carting, setCarting] = useState<string[] | null>(null);
  const [editOpen, setEditOpen] = useState<number | null>(null);
  // FON-67 : une écriture du tableur qui attend sa confirmation, et ce que la page annonce.
  const [pending, setPending] = useState<{
    question: string;
    lot: EditLot;
    outcome: EditOutcome;
    name?: string;
    done: (ok: boolean) => void;
  } | null>(null);
  const [writing, setWriting] = useState(false);
  const [announce, setAnnounce] = useState("");
  const [views, setViews] = useState<SavedView[] | null>(null);
  const { toast, show, dismiss } = useAppToast();
  const ticket = useRef(0);
  const reopened = useRef(false);
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

  const loadViews = useCallback(async () => {
    try {
      const payload = await apiGet<{ views?: SavedView[] }>("/media/views.json");
      setViews(Array.isArray(payload.views) ? payload.views : []);
    } catch (caught) {
      // An engine without the views: the menu hides, the table stays.
      if (caught instanceof ApiRequestError && caught.status === 404) setViews(null);
      else show(messageOf(caught, "Les vues gardées ne se sont pas lues."), "error");
    }
  }, [show]);

  useEffect(() => {
    void loadShelves();
    void loadViews();
  }, [loadShelves, loadViews]);

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

  const activeId = Number(params.get(VIEW_PARAM)) || null;
  const active = views?.find((view) => view.id === activeId) ?? null;

  const openView = useCallback(
    (view: SavedView) => {
      const next = writeState(params, stateOfView(view));
      next.set(VIEW_PARAM, String(view.id));
      setParams(next, { replace: true });
      setTyped(stateOfView(view).q);
      setOpenId(null);
      setView("detail");
      rememberView(view.id);
    },
    [params, setParams],
  );

  // The bank opened bare, with nothing in the address: the last view opened, if it is still kept.
  useEffect(() => {
    if (reopened.current || !views) return;
    reopened.current = true;
    const bare = ["ranger", "groupe", "collection", "tri", "ordre", "q", "colonnes", VIEW_PARAM].every((key) => !params.has(key));
    const last = lastView();
    const view = bare && last != null ? views.find((item) => item.id === last) : undefined;
    if (view) openView(view);
  }, [openView, params, views]);

  const createView = async (name: string) => {
    const { view } = await apiPostJson<{ view: SavedView }>("/media/views.json", { name, state: viewStateOf(state) });
    setViews((before) => [...(before ?? []), view].sort((a, b) => a.name.localeCompare(b.name, "fr")));
    const next = new URLSearchParams(params);
    next.set(VIEW_PARAM, String(view.id));
    setParams(next, { replace: true });
    rememberView(view.id);
    show(`Vue « ${view.name} » gardée. Elle se rouvre depuis « Vues », sur tout ordinateur.`, "success");
  };

  const putView = async (view: SavedView, body: Record<string, unknown>) => {
    const { view: saved } = await apiPut<{ view: SavedView }>(`/media/views/${view.id}.json`, body);
    setViews((before) =>
      (before ?? []).map((item) => (item.id === saved.id ? saved : item)).sort((a, b) => a.name.localeCompare(b.name, "fr")),
    );
    return saved;
  };

  const rankingGroups = groupsOf(state.ranking, groups[state.ranking] ?? [], shelves);
  const heading = groupLabel(state.ranking, state.group, rankingGroups);
  // Ranged by collection, one collection of the catalogue: today's gestures.
  const shelf =
    state.ranking === "collection" && state.group ? (shelves.find((item) => item.id === state.group) ?? null) : null;
  const gestures = shelf != null;
  const selectable = gestures || canEdit || canCart;
  // A group with a value becomes a selection of titles (FON-73), for whoever writes them.
  const canSelect = tableMakesSelection(state) && roleAtLeast(role, "programmateur");
  const others = shelves.filter((item) => item.id !== shelf?.id);
  const busy = progress != null;
  const opened = titles.find((title) => title.id === openId) ?? null;
  const allSelected = selectable && titles.length > 0 && titles.every((title) => selected.has(title.id));
  const someSelected = selectable && !allSelected && titles.some((title) => selected.has(title.id));
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

  // Après une correction : ce qui est fait, et « Revenir » tant que le message est là.
  const afterEdit = async (outcome: EditOutcome, name?: string) => {
    const message = savedMessage(outcome, name);
    const entry = outcome.entry;
    show(
      message.text,
      message.tone,
      entry != null && outcome.written + outcome.waiting.length > 0
        ? { action: { label: "Revenir", onClick: () => void undo(entry) } }
        : undefined,
    );
    await load();
  };

  const undo = async (entry: number) => {
    try {
      const message = undoneMessage(await undoTitles(entry));
      show(message.text, message.tone);
    } catch (caught) {
      show(messageOf(caught, "Le lot n'a pas été défait. Réessaie."), "error");
    } finally {
      await load();
    }
  };

  // Le tableur (FON-67) : une cellule passe par l'essai du lot de FON-66, et ne
  // demande confirmation que si l'essai a quelque chose à dire. Un collage sur
  // plusieurs titres sélectionnés la demande toujours.
  const writeLot = async (lot: EditLot, name?: string): Promise<boolean> => {
    try {
      await afterEdit(await editTitles(lot, false), name);
      return true;
    } catch (caught) {
      show(messageOf(caught, "La fiche n'a pas été corrigée. Réessaie."), "error");
      return false;
    }
  };

  const tryLot = async (lot: EditLot, question: string, always: boolean, name?: string): Promise<boolean> => {
    let outcome: EditOutcome;
    try {
      outcome = await editTitles(lot, true);
    } catch (caught) {
      show(messageOf(caught, "L'essai n'a pas abouti. Réessaie."), "error");
      return false;
    }
    if (outcome.refused.length && !always) {
      show(needsConfirmationText(outcome), "error");
      return false;
    }
    if (!always && !needsConfirmation(outcome)) return writeLot(lot, name);
    return new Promise<boolean>((resolve) => setPending({ question, lot, outcome, name, done: resolve }));
  };

  const saveCell = async (title: BankTitle, field: FicheField, value: string): Promise<boolean> => {
    const lot = cellLot(title, field, value);
    if (!lot) return true;
    const problem = field === "year" ? yearProblem(value) : "";
    if (problem) {
      show(problem, "error");
      return false;
    }
    return tryLot(lot, `Corriger la fiche de « ${titleName(title)} » ?`, false, titleName(title));
  };

  const pasteCell = (title: BankTitle, field: FicheField, text: string) => {
    const many = selected.has(title.id) && selected.size > 1;
    if (!many) {
      const value = text.replace(/\r\n?/g, "\n").split("\n")[0];
      void saveCell(title, field, value);
      return;
    }
    const chosen = titles.filter((item) => selected.has(item.id));
    const pasted = pasteLot(chosen, field, text);
    if ("problem" in pasted) {
      show(pasted.problem, "error");
      return;
    }
    void tryLot(pasted.lot, pasteQuestion(field, pasted.value, chosen.length), true);
  };

  // Les cellules du tableur suivent les colonnes affichées, dans leur ordre (FON-65).
  const gridColumns = state.columns.filter(isGridField);
  const moveCell = (row: number, column: number, move: Move) => {
    const target = nextCell({ row, column }, move, titles.length, gridColumns.length);
    if (target) document.querySelector<HTMLElement>(`[data-grid="${target.row}:${target.column}"]`)?.focus();
  };

  const finishPending = async (ok: boolean) => {
    if (!pending) return;
    const { lot, name, done } = pending;
    if (!ok) {
      setPending(null);
      done(false);
      return;
    }
    setWriting(true);
    const written = await writeLot(lot, name);
    setWriting(false);
    setPending(null);
    done(written);
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
            {shelf || canSelect ? (
              <div className="bacs-head-actions">
                {canSelect ? (
                  <Button size="2" variant="soft" color="gray" asChild>
                    <Link to={selectionLink(filtersFromTable(state))}>
                      <ListPlus className="ui-button-icon" />
                      <span className="bacs-hide-narrow">Créer une sélection</span>
                      <span className="bacs-show-narrow">Sélection</span>
                    </Link>
                  </Button>
                ) : null}
                {shelf ? (
                  <Button size="2" variant="soft" color="gray" disabled={busy} onClick={() => onAdd(shelf.id)}>
                    <Upload className="ui-button-icon" />
                    <span className="bacs-hide-narrow">Ajouter des titres</span>
                    <span className="bacs-show-narrow">Ajouter</span>
                  </Button>
                ) : null}
                {shelf && isAdmin && shelf.group !== "rotation" ? (
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
            {selectable && selected.size > 0 ? (
              <div className="bacs-toolbar bacs-toolbar--selection" role="toolbar" aria-label="Sélection">
                <strong className="bacs-selection-count">
                  {titlesLabel(selected.size)} sélectionné{selected.size === 1 ? "" : "s"}
                </strong>
                <span className="bacs-spacer" />
                <Button size="1" variant="ghost" color="gray" disabled={busy} onClick={() => setSelected(new Set())}>
                  <X className="ui-button-icon" />
                  Désélectionner
                </Button>
                {canEdit ? (
                  <Button
                    size="1"
                    variant="soft"
                    color="gray"
                    disabled={busy}
                    onClick={() => setEditing(titles.filter((title) => selected.has(title.id)))}
                  >
                    <Pencil className="ui-button-icon" />
                    Modifier {selected.size === 1 ? "la fiche" : `${selected.size} fiches`}
                  </Button>
                ) : null}
                {canCart ? (
                  <Button
                    size="1"
                    variant="soft"
                    color="gray"
                    disabled={busy}
                    onClick={() => setCarting(titles.filter((title) => selected.has(title.id)).map((title) => title.path))}
                  >
                    <ListPlus className="ui-button-icon" />
                    Ajouter à un bac
                  </Button>
                ) : null}
                {gestures ? (
                  <>
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
                  </>
                ) : null}
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
                <ColumnsPicker columns={state.columns} onChange={(columns) => update({ columns })} />
                {views ? (
                  <ViewsMenu
                    views={views}
                    active={active}
                    modified={active ? !sameAsView(state, active) : false}
                    onOpen={openView}
                    onCreate={createView}
                    onSave={(view) => {
                      void putView(view, { state: viewStateOf(state) }).then(
                        (saved) => show(`Vue « ${saved.name} » mise à jour.`, "success"),
                        (caught) => show(messageOf(caught, "La vue n'a pas été mise à jour."), "error"),
                      );
                    }}
                    onRename={async (view, name) => {
                      const saved = await putView(view, { name });
                      show(`La vue « ${view.name} » s'appelle maintenant « ${saved.name} ».`, "success");
                    }}
                    onDelete={async (view) => {
                      try {
                        await apiDeleteJson(`/media/views/${view.id}.json`);
                        setViews((before) => (before ?? []).filter((item) => item.id !== view.id));
                        if (view.id === activeId) {
                          const next = new URLSearchParams(params);
                          next.delete(VIEW_PARAM);
                          setParams(next, { replace: true });
                        }
                        if (lastView() === view.id) rememberView(null);
                        show(`Vue « ${view.name} » supprimée.`, "success");
                      } catch (caught) {
                        show(messageOf(caught, "La vue n'a pas été supprimée."), "error");
                      }
                    }}
                  />
                ) : null}
              </div>
            )}

            <p className="ui-visually-hidden" aria-live="polite">
              {announce}
            </p>

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
                <table
                  className="bacs-table banque-titles"
                  style={{ minWidth: `${tableMinWidth(state.columns, selectable)}rem` }}
                  aria-rowcount={count}
                >
                  <thead>
                    <tr>
                      {selectable ? (
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
                      {state.columns.map((key) =>
                        key === "fiche" ? (
                          <th key={key} className="c-fiche">
                            {columnLabel(key)}
                          </th>
                        ) : (
                          <SortHeader
                            key={key}
                            column={key}
                            label={columnLabel(key)}
                            state={state}
                            onSort={(column) => update(nextSort(state, column))}
                          />
                        ),
                      )}
                      {selectable ? (
                        <th className="c-more">
                          <span className="ui-visually-hidden">Actions</span>
                        </th>
                      ) : null}
                    </tr>
                  </thead>
                  <tbody>
                    {titles.map((title, row) => (
                      <TitleRow
                        key={title.id}
                        title={title}
                        grid={
                          canEdit
                            ? {
                                row,
                                busy: busy || writing || pending != null,
                                save: (field, value) => saveCell(title, field, value),
                                move: (column, move) => moveCell(row, column, move),
                                paste: (field, text) => pasteCell(title, field, text),
                                announce: setAnnounce,
                              }
                            : undefined
                        }
                        columns={state.columns}
                        gestures={gestures}
                        selectable={selectable}
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
                        onOpen={() => {
                          setOpenId(title.id);
                          setEditOpen(null);
                        }}
                        onPlay={() => preview.toggle(String(title.id))}
                        onMove={() => setMoving([title.id])}
                        onRemove={() => setRemoving([title.id])}
                        onEdit={
                          canEdit
                            ? () => {
                                setOpenId(title.id);
                                setEditOpen(title.id);
                              }
                            : undefined
                        }
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
              canEdit={canEdit}
              startEditing={editOpen === opened.id}
              onSaved={(outcome, name) => void afterEdit(outcome, name)}
              onPlay={() => preview.toggle(String(opened.id))}
              onClose={() => {
                const id = opened.id;
                setOpenId(null);
                setEditOpen(null);
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
        description={[
          removeNote(removing?.length ?? 0, account?.features?.bank_removals === true),
          cartsBeforeRemoval(titles.filter((title) => removing?.includes(title.id))),
        ]
          .filter(Boolean)
          .join(" ")}
        confirmLabel={removing?.length === 1 ? "Retirer le titre" : `Retirer ${titlesLabel(removing?.length ?? 0).toLowerCase()}`}
        onConfirm={() => {
          const ids = removing ?? [];
          setRemoving(null);
          if (ids.length && shelf) void run("removed", ids, (names, onProgress) => removeBankFiles(shelf.id, names, onProgress));
        }}
      />

      {carting ? (
        <AddToCartDialog
          paths={carting}
          notify={show}
          onClose={() => {
            setCarting(null);
            setSelected(new Set());
            void load();
          }}
        />
      ) : null}

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
      {pending ? (
        <ConfirmLotDialog
          question={pending.question}
          outcome={pending.outcome}
          busy={writing}
          onCancel={() => void finishPending(false)}
          onConfirm={() => void finishPending(true)}
        />
      ) : null}
      {editing ? (
        <EditTitlesDialog
          titles={editing}
          onClose={() => setEditing(null)}
          onDone={(outcome) => {
            setEditing(null);
            setSelected(new Set());
            void afterEdit(outcome);
          }}
        />
      ) : null}
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

/** Ce qu'une ligne passe à ses cellules du tableur (FON-67). */
type GridHandlers = {
  row: number;
  busy: boolean;
  save: (field: FicheField, value: string) => Promise<boolean>;
  move: (column: number, move: Move) => void;
  paste: (field: FicheField, text: string) => void;
  announce: (text: string) => void;
};

function TitleRow({
  title,
  grid,
  columns,
  gestures,
  selectable,
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
  onEdit,
}: {
  title: BankTitle;
  /** The cells open like a spreadsheet's (FON-67). */
  grid?: GridHandlers;
  columns: ColumnKey[];
  gestures: boolean;
  /** A checkbox, for the gestures of a collection or to correct the fiches (FON-66). */
  selectable: boolean;
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
  /** Opens the fiche, ready to correct. */
  onEdit?: () => void;
}) {
  const name = title.title || fileName(title.path);
  const fiche = ficheState(title.missing);
  // Le rang d'une cellule du tableur parmi celles de la ligne : les flèches s'y fient.
  const gridKeys = columns.filter(isGridField);
  const length = title.duration ? formatClock(title.duration) : "";
  return (
    <tr
      className={["bacs-track-row", selected || opened ? "is-selected" : "", playing ? "is-playing" : ""].filter(Boolean).join(" ")}
      aria-selected={selectable ? selected : undefined}
    >
      {selectable ? (
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
      {columns.map((key) => {
        if (grid && isGridField(key)) {
          const column = gridKeys.indexOf(key);
          return (
            <td key={key} className={`c-${key} c-grid`}>
              <GridCell
                title={title}
                field={key}
                row={grid.row}
                column={column}
                busy={grid.busy}
                onSave={(value) => grid.save(key, value)}
                onMove={(move) => grid.move(column, move)}
                onPaste={(text) => grid.paste(key, text)}
                onToggle={selectable ? onToggle : undefined}
                onAnnounce={grid.announce}
              />
            </td>
          );
        }
        switch (key) {
          case "title":
            return (
              <td key={key} className="c-title">
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
            );
          case "famille":
            return (
              <td key={key} className="c-famille">
                {cell(title.famille_label)}
              </td>
            );
          case "duration":
            return (
              <td key={key} className="c-duration">
                {length || "—"}
              </td>
            );
          case "fiche":
            return (
              <td key={key} className="c-fiche">
                <Tooltip content={fiche.detail}>
                  <Badge size="1" variant="soft" color={fiche.complete ? "green" : "gray"} highContrast tabIndex={0}>
                    {fiche.label}
                  </Badge>
                </Tooltip>
              </td>
            );
          default:
            return (
              <td key={key} className={`c-${key}`}>
                {cell(title[key])}
              </td>
            );
        }
      })}
      {selectable ? (
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
              {onEdit ? (
                <DropdownMenu.Item onSelect={onEdit}>
                  <Pencil size={14} aria-hidden="true" />
                  Corriger la fiche
                </DropdownMenu.Item>
              ) : null}
              {gestures ? (
                <>
                  <DropdownMenu.Item disabled={!canMove} onSelect={onMove}>
                    <FolderInput size={14} aria-hidden="true" />
                    Déplacer vers…
                  </DropdownMenu.Item>
                  <DropdownMenu.Separator />
                  <DropdownMenu.Item color="red" onSelect={onRemove}>
                    <Trash2 size={14} aria-hidden="true" />
                    Retirer…
                  </DropdownMenu.Item>
                </>
              ) : null}
            </DropdownMenu.Content>
          </DropdownMenu.Root>
        </td>
      ) : null}
    </tr>
  );
}
