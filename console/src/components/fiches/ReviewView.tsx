import { Badge, Button, Select, Spinner, TextField } from "@radix-ui/themes";
import {
  Check,
  CheckCheck,
  ChevronDown,
  ChevronRight,
  CloudOff,
  ExternalLink,
  FileSearch,
  Keyboard,
  Pause,
  Play,
  RefreshCw,
  RotateCcw,
  Search,
  X,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useAccount } from "../../api/AccountContext";
import { API_PREFIX, ApiRequestError, apiGet, apiPostJson } from "../../api/client";
import {
  FICHES_DECISIONS_JSON,
  FICHES_JSON,
  FIELD_LABELS,
  LEVEL_LABELS,
  NATURES_JSON,
  NO_FILTERS,
  STATE_LABELS,
  bankLabel,
  chunks,
  decidedMessage,
  duration,
  fichesErrorText,
  durationGap,
  fichesQuery,
  fieldValue,
  levelChips,
  levelColor,
  platformName,
  progressLine,
  propositionStatus,
  revertPath,
  searchAgainPath,
  sureShown,
  verdictShare,
  type Decided,
  type FicheDetail,
  type FicheProposition,
  type FicheTitle,
  type FichesFilters,
  type FichesPage,
  type NatureGroup,
} from "../../api/fiches";
import { TITLES_SEND_DEADLINE_MS } from "../../api/sendDeadline";
import { formatWhen } from "../../api/updates";
import { usePreview } from "../../lib/usePreview";
import { AppToast, useAppToast } from "../../ui/AppToast";
import { ConfirmDialog } from "../../ui/ConfirmDialog";
import { ErrorState, LoadingState } from "../../ui/DataState";
import { EmptyState } from "../../ui/EmptyState";
import { Cover } from "./Cover";
import "../../styles/pages/fiches.css";
import { KeyboardReview } from "./KeyboardReview";
import { AcceptGroupDialog, NatureGroups } from "./NatureGroups";

// Radix ne prend pas une valeur vide pour un choix de liste.
const ALL = "tous";
// Le temps de laisser finir la frappe avant de chercher.
const TYPING_MS = 350;

function messageOf(caught: unknown, fallback: string): string {
  return fichesErrorText(caught, fallback);
}

/** Ce que la fiche d'un titre peut faire : accepter, refuser, revenir, chercher de nouveau. */
type Gestures = {
  canWrite: boolean;
  busy: boolean;
  decide: (accept: number[], refuse: number[], beetsId: number) => void;
  revert: (proposition: FicheProposition, beetsId: number) => void;
  searchAgain: (beetsId: number, name: string) => void;
};

/**
 * Sons → Banque → À relire (FON-26) : ce que la recherche en ligne propose pour
 * les fiches, par niveau, avec d'où ça vient. Accepter écrit la valeur par le
 * service de FON-66, au journal ; refuser l'écarte ; « Revenir » remet la valeur
 * d'avant (FON-27).
 */
export function ReviewView() {
  const { account } = useAccount();
  // Accepter écrit les fichiers : il faut la correction des fiches ouverte.
  const canWrite = account?.features?.title_edits === true;
  const [busy, setBusy] = useState(false);
  // Un lot de propositions sûres : celles affichées, ou un groupe par nature (FON-79).
  const [lot, setLot] = useState<{ ids: number[]; titles: number; group?: NatureGroup } | null>(null);
  // FON-78 : la relecture au clavier, de la vue ou d'un groupe ; et où rendre le focus.
  const [keyboard, setKeyboard] = useState<"vue" | NatureGroup | null>(null);
  const returnFocus = useRef<HTMLElement | null>(null);
  // FON-79 : les propositions sûres de toute la banque, par nature de changement.
  // Null : un moteur qui ne les regroupe pas, ou le rangement fermé.
  const [groups, setGroups] = useState<NatureGroup[] | null>(null);
  const [filters, setFilters] = useState<FichesFilters>(NO_FILTERS);
  const [typed, setTyped] = useState("");
  const [page, setPage] = useState<FichesPage | null>(null);
  const [titles, setTitles] = useState<FicheTitle[]>([]);
  const [problem, setProblem] = useState("");
  const [closed, setClosed] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [open, setOpen] = useState<Record<number, FicheDetail | "loading" | string>>({});
  const { toast, show, dismiss } = useAppToast();
  const preview = usePreview(
    (message) => show(message, "error"),
    (id) => `${API_PREFIX}/autodj/beets/${encodeURIComponent(id)}`,
  );
  const ticket = useRef(0);

  const load = useCallback(async () => {
    const mine = ++ticket.current;
    try {
      const next = await apiGet<FichesPage>(`${FICHES_JSON}${fichesQuery(filters)}`);
      if (mine !== ticket.current) return;
      setPage(next);
      setTitles(next.titles);
      setProblem("");
    } catch (caught) {
      if (mine !== ticket.current) return;
      if (caught instanceof ApiRequestError && caught.status === 404) setClosed(true);
      else setProblem(messageOf(caught, "Les fiches ne se sont pas lues. Réessaie."));
    }
  }, [filters]);

  const loadGroups = useCallback(async () => {
    try {
      const payload = await apiGet<{ groups?: NatureGroup[] }>(NATURES_JSON);
      setGroups(Array.isArray(payload.groups) ? payload.groups : []);
    } catch (caught) {
      setGroups(null);
      // Un moteur d'avant FON-79, ou le rangement fermé : la section se cache.
      if (caught instanceof ApiRequestError && (caught.status === 404 || caught.status === 409)) return;
      show(messageOf(caught, "Les groupes de propositions ne se sont pas lus."), "error");
    }
  }, [show]);

  useEffect(() => {
    void loadGroups();
  }, [loadGroups]);

  const openKeyboard = (target: "vue" | NatureGroup) => {
    returnFocus.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    setKeyboard(target);
  };

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    const q = typed.trim();
    if (q === filters.q) return;
    const timer = window.setTimeout(() => setFilters((before) => ({ ...before, q })), TYPING_MS);
    return () => window.clearTimeout(timer);
  }, [typed, filters.q]);

  const pick = (name: keyof FichesFilters, value: string) => {
    setOpen({});
    setFilters((before) => ({ ...before, [name]: value === ALL ? "" : value }));
  };

  const loadMore = async () => {
    if (page?.next == null || loadingMore) return;
    setLoadingMore(true);
    try {
      const next = await apiGet<FichesPage>(`${FICHES_JSON}${fichesQuery(filters, page.next)}`);
      setTitles((before) => [...before, ...next.titles]);
      setPage(next);
    } catch (caught) {
      show(messageOf(caught, "La suite des fiches ne s'est pas lue. Réessaie."), "error");
    } finally {
      setLoadingMore(false);
    }
  };

  /** La tête de la page relue, et les titres touchés relus avec leur fiche, sans perdre la liste affichée. */
  const refresh = async (beetsIds: number[]) => {
    try {
      const next = await apiGet<FichesPage>(`${FICHES_JSON}${fichesQuery(filters)}`);
      setPage((before) => (before ? { ...next, next: before.next } : next));
    } catch {
      // La tête garde ses comptes : le geste, lui, est fait et son message dit lequel.
    }
    for (const beetsId of beetsIds) {
      try {
        const detail = await apiGet<FicheDetail>(`/fiches/${beetsId}.json`);
        setTitles((before) =>
          before.map((title) =>
            title.id === beetsId ? { ...title, level: detail.fiche.level, propositions: detail.propositions } : title,
          ),
        );
        setOpen((before) => (before[beetsId] ? { ...before, [beetsId]: detail } : before));
      } catch {
        // Le titre a quitté la bibliothèque : la prochaine lecture de la page le dira.
      }
    }
  };

  const failed = (caught: unknown, fallback: string) => {
    show(messageOf(caught, fallback), "error");
  };

  const decide = async (accept: number[], refuse: number[], beetsIds: number[]) => {
    if (busy) return;
    setBusy(true);
    try {
      const decided = await apiPostJson<Decided>(FICHES_DECISIONS_JSON, { accept, refuse }, TITLES_SEND_DEADLINE_MS);
      const message = decidedMessage(decided);
      show(message.text, message.tone);
    } catch (caught) {
      failed(caught, "La décision n'a pas été prise. Réessaie.");
    } finally {
      setBusy(false);
      await refresh(beetsIds);
    }
  };

  const acceptLot = async () => {
    if (!lot || busy) return;
    setBusy(true);
    const total: Decided = { accepted: 0, refused: 0, written: 0, waiting: [], failed: [], stale: 0, entry: null };
    try {
      for (const ids of chunks(lot.ids)) {
        const decided = await apiPostJson<Decided>(FICHES_DECISIONS_JSON, { accept: ids }, TITLES_SEND_DEADLINE_MS);
        total.accepted += decided.accepted;
        total.written += decided.written;
        total.stale += decided.stale;
        total.waiting.push(...decided.waiting);
        total.failed.push(...decided.failed);
      }
      const message = decidedMessage(total);
      show(message.text, message.tone);
    } catch (caught) {
      const done = total.written ? `${decidedMessage(total).text} ` : "";
      show(`${done}${messageOf(caught, "Le lot ne s'est pas accepté en entier. Réessaie.")}`, "error");
    } finally {
      setBusy(false);
      setLot(null);
      setOpen({});
      await Promise.all([load(), loadGroups()]);
    }
  };

  const revert = async (proposition: FicheProposition, beetsId: number) => {
    if (busy) return;
    setBusy(true);
    try {
      await apiPostJson<Decided>(revertPath(proposition.id), {}, TITLES_SEND_DEADLINE_MS);
      const field = FIELD_LABELS[proposition.field] ?? proposition.field;
      show(`${field} : la valeur d'avant est revenue.`, "success");
    } catch (caught) {
      failed(caught, "La valeur d'avant n'est pas revenue. Réessaie.");
    } finally {
      setBusy(false);
      await refresh([beetsId]);
    }
  };

  const searchAgain = async (beetsId: number, name: string) => {
    if (busy) return;
    setBusy(true);
    try {
      await apiPostJson<{ queued: boolean }>(searchAgainPath(beetsId), {});
      show(`« ${name} » sera cherché de nouveau dans un instant.`, "info");
    } catch (caught) {
      failed(caught, "Le titre n'a pas été remis à chercher. Réessaie.");
    } finally {
      setBusy(false);
      await refresh([beetsId]);
    }
  };

  const gestures: Gestures = {
    canWrite,
    busy,
    decide: (accept, refuse, beetsId) => void decide(accept, refuse, [beetsId]),
    revert: (proposition, beetsId) => void revert(proposition, beetsId),
    searchAgain: (beetsId, name) => void searchAgain(beetsId, name),
  };

  const toggle = async (title: FicheTitle) => {
    if (open[title.id]) {
      setOpen(({ [title.id]: _gone, ...rest }) => rest);
      return;
    }
    setOpen((before) => ({ ...before, [title.id]: "loading" }));
    try {
      const detail = await apiGet<FicheDetail>(`/fiches/${title.id}.json`);
      setOpen((before) => ({ ...before, [title.id]: detail }));
    } catch (caught) {
      setOpen((before) => ({ ...before, [title.id]: messageOf(caught, "La fiche ne s'est pas lue.") }));
    }
  };

  if (closed) {
    return (
      <EmptyState
        icon={CloudOff}
        title="Mets à jour le moteur"
        description="Le moteur de cette station ne cherche pas encore les fiches en ligne."
      />
    );
  }
  if (!page) {
    return problem ? (
      <ErrorState title="Fiches illisibles" description={problem} onRetry={() => void load()} />
    ) : (
      <LoadingState label="Lecture des fiches…" />
    );
  }

  const chips = levelChips(page);
  const filtered = Boolean(filters.level || filters.field || filters.bank || filters.state || filters.q);
  const errors = page.statuses.erreur ?? 0;
  const started = page.progress.searched > 0;
  const sure = sureShown(titles);
  // Au clavier, les titres qui attendent : la vue À relire, avec quelque chose à relire.
  const keyable = !filters.state && titles.some((title) => title.propositions.some((one) => one.state === "proposée"));

  return (
    <section className="fiches" aria-label="Fiches à relire">
      <header className="fiches-head">
        <div className="fiches-intro">
          <p className="fiches-progress">{progressLine(page)}</p>
          {/* FON-28 : la part des « oui » parmi les verdicts connus, verdict allumé. */}
          {page.verdict && verdictShare(page.verdicts) ? (
            <p className="fiches-hint fiches-verdicts">{verdictShare(page.verdicts)}</p>
          ) : null}
          <p className="fiches-hint">
            {canWrite
              ? "Ce que la recherche en ligne propose de corriger, titre par titre, avec d'où ça vient. Accepter écrit la valeur dans le fichier, puis dans la bibliothèque ; « Revenir » remet celle d'avant."
              : "Ce que la recherche en ligne propose de corriger, titre par titre, avec d'où ça vient. La correction des fiches est coupée sur cette station : on relit et on refuse, sans rien écrire."}
          </p>
          {(canWrite && sure.ids.length) || keyable ? (
            <div className="fiches-lot">
              {keyable ? (
                <Button size="2" variant="soft" disabled={busy} onClick={() => openKeyboard("vue")}>
                  <Keyboard className="ui-button-icon" />
                  Relire au clavier
                </Button>
              ) : null}
              {canWrite && sure.ids.length ? (
                <Button size="2" variant="soft" disabled={busy} onClick={() => setLot(sure)}>
                  <CheckCheck className="ui-button-icon" />
                  Accepter les {sure.ids.length} propositions sûres affichées
                </Button>
              ) : null}
            </div>
          ) : null}
        </div>
        {chips.length ? (
          <div className="fiches-levels" role="group" aria-label="Niveaux">
            {chips.map((chip) => (
              <button
                key={chip.value}
                type="button"
                className="fiches-level"
                aria-pressed={filters.level === chip.value}
                onClick={() => pick("level", filters.level === chip.value ? ALL : chip.value)}
              >
                <Badge size="1" variant="soft" color={levelColor(chip.value)} highContrast>
                  {LEVEL_LABELS[chip.value] ?? chip.value}
                </Badge>{" "}
                <span className="fiches-level-count">{chip.count}</span>
              </button>
            ))}
          </div>
        ) : null}
      </header>

      {/* Rien encore cherché : l'état vide le dit, et il n'y a rien à filtrer. */}
      {!page.enabled && started ? (
        <div className="banque-note fiches-note" role="status">
          <span>La recherche en ligne est coupée. Un admin l'allume dans Réglages → Fiches.</span>
        </div>
      ) : null}
      {errors > 0 ? (
        <div className="banque-note fiches-note is-warn" role="status">
          <span>
            {errors} titre{errors === 1 ? "" : "s"} en erreur, cherché{errors === 1 ? "" : "s"} de nouveau plus tard :{" "}
            {page.failures.map((failure) => `${failure.error} (${failure.count})`).join(", ")}.
          </span>
        </div>
      ) : null}
      {problem ? (
        <div className="banque-note is-danger" role="alert">
          <span>Les fiches n'ont pas pu se relire : {problem}</span>
          <Button size="1" variant="soft" color="gray" onClick={() => void load()}>
            Réessayer
          </Button>
        </div>
      ) : null}

      {groups && groups.length ? (
        <NatureGroups
          groups={groups}
          canWrite={canWrite}
          busy={busy}
          onAccept={(group) => setLot({ ids: group.ids, titles: group.titles, group })}
          onKeyboard={openKeyboard}
        />
      ) : null}

      {started ? (
        <div className="fiches-filters">
          <label className="fiches-filter is-search">
            <span className="ui-field-label">Recherche</span>
            <TextField.Root
              value={typed}
              placeholder="Titre, artiste ou album"
              aria-label="Recherche"
              onChange={(event) => setTyped(event.target.value)}
            >
              <TextField.Slot>
                <Search size={14} aria-hidden="true" />
              </TextField.Slot>
            </TextField.Root>
          </label>
          <FilterSelect
            label="Niveau"
            all="Tous les niveaux"
            value={filters.level}
            options={chips.map((one) => ({ ...one, label: LEVEL_LABELS[one.value] ?? one.value }))}
            onChange={(value) => pick("level", value)}
          />
          <FilterSelect
            label="Champ"
            all="Tous les champs"
            value={filters.field}
            options={page.fields.map((one) => ({ ...one, label: FIELD_LABELS[one.value] ?? one.value }))}
            onChange={(value) => pick("field", value)}
          />
          <FilterSelect
            label="Banque"
            all="Toute la banque"
            value={filters.bank}
            options={page.banks.map((one) => ({ ...one, label: bankLabel(one.value) }))}
            onChange={(value) => pick("bank", value)}
          />
          <FilterSelect
            label="État"
            all="À relire"
            value={filters.state}
            options={page.states
              .filter((one) => one.value !== "proposée")
              .map((one) => ({ ...one, label: STATE_LABELS[one.value] ?? one.value }))}
            onChange={(value) => pick("state", value)}
          />
        </div>
      ) : null}

      {titles.length === 0 ? (
        <EmptyState
          icon={FileSearch}
          title={filtered ? "Aucun titre ainsi" : emptyTitle(page)}
          description={filtered ? "Aucune fiche ne répond à ces filtres." : emptyDescription(page)}
        />
      ) : (
        <>
          <p className="fiches-total" aria-live="polite">
            {page.total} titre{page.total === 1 ? "" : "s"}
          </p>
          <ol className="fiches-list">
            {titles.map((title) => (
              <TitleRow
                key={title.id}
                title={title}
                detail={open[title.id]}
                playing={preview.playingId === String(title.id)}
                onToggle={() => void toggle(title)}
                onPlay={() => preview.toggle(String(title.id))}
                gestures={gestures}
              />
            ))}
          </ol>
        </>
      )}

      {page.next != null ? (
        <div className="banque-more">
          <Button size="2" variant="soft" color="gray" disabled={loadingMore} onClick={() => void loadMore()}>
            {loadingMore ? <Spinner size="1" /> : null}
            Afficher les titres suivants
          </Button>
        </div>
      ) : null}
      <ConfirmDialog
        open={lot != null && !lot.group}
        onOpenChange={(next) => {
          if (!next && !busy) setLot(null);
        }}
        busy={busy}
        title={lot ? `Accepter ${lot.ids.length} propositions sûres ?` : "Accepter ce lot ?"}
        description={
          lot
            ? `Elles s'écrivent dans les fichiers de ${lot.titles} titre${lot.titles === 1 ? "" : "s"}, puis dans la bibliothèque, et le lot se note au journal. Un titre à l'antenne ou en file attend la fin de son passage. « Revenir » remet une valeur, proposition par proposition.`
            : ""
        }
        confirmLabel="Accepter et écrire"
        cancelLabel="Garder"
        onConfirm={acceptLot}
      />
      {lot?.group ? (
        <AcceptGroupDialog
          group={lot.group}
          busy={busy}
          onCancel={() => setLot(null)}
          onConfirm={() => void acceptLot()}
        />
      ) : null}
      {keyboard ? (
        <KeyboardReview
          filters={filters}
          group={keyboard === "vue" ? null : { nature: keyboard.nature, label: keyboard.label }}
          canWrite={canWrite}
          preview={preview}
          onClose={() => {
            setKeyboard(null);
            preview.stop();
            setOpen({});
            void load();
            void loadGroups();
            // Le focus revient au bouton qui l'a ouverte : la fenêtre n'a pas de déclencheur à Radix.
            requestAnimationFrame(() => returnFocus.current?.focus());
          }}
        />
      ) : null}
      <AppToast toast={toast} onDismiss={dismiss} />
    </section>
  );
}

function emptyTitle(page: FichesPage): string {
  if (page.progress.searched === 0) return page.enabled ? "La recherche commence" : "La recherche n'a pas commencé";
  return "Rien à relire";
}

function emptyDescription(page: FichesPage): string {
  if (page.progress.searched === 0) {
    return page.enabled
      ? "Elle cherche un titre à la fois. Ce qu'elle propose de corriger arrive ici."
      : "Un admin l'allume dans Réglages → Fiches. Elle cherche alors un titre à la fois, et ce qu'elle propose arrive ici.";
  }
  return "Aucune proposition n'attend d'être relue pour l'instant.";
}

function FilterSelect({
  label,
  all,
  value,
  options,
  onChange,
}: {
  label: string;
  all: string;
  value: string;
  options: { value: string; count: number; label: string }[];
  onChange: (value: string) => void;
}) {
  // Un choix posé que la page ne compte plus reste dans la liste, pour se défaire.
  const shown =
    value && !options.some((one) => one.value === value) ? [...options, { value, count: 0, label: value }] : options;
  return (
    <label className="fiches-filter">
      <span className="ui-field-label">{label}</span>
      <Select.Root value={value || ALL} onValueChange={onChange}>
        <Select.Trigger aria-label={label} />
        <Select.Content variant="soft" position="popper">
          <Select.Item value={ALL}>{all}</Select.Item>
          {shown.map((one) => (
            <Select.Item key={one.value} value={one.value}>
              {one.label} ({one.count})
            </Select.Item>
          ))}
        </Select.Content>
      </Select.Root>
    </label>
  );
}

function TitleRow({
  title,
  detail,
  playing,
  onToggle,
  onPlay,
  gestures,
}: {
  title: FicheTitle;
  detail: FicheDetail | "loading" | string | undefined;
  playing: boolean;
  onToggle: () => void;
  onPlay: () => void;
  gestures: Gestures;
}) {
  const name = title.title || title.path;
  const byline = [title.artist, title.album].filter(Boolean).join(" · ");
  return (
    <li className="fiches-title">
      <div className="fiches-title-main">
        <button type="button" className="fiches-toggle" aria-expanded={Boolean(detail)} onClick={onToggle}>
          {detail ? <ChevronDown size={16} aria-hidden="true" /> : <ChevronRight size={16} aria-hidden="true" />}
          <span className="fiches-title-copy">
            <strong>{name}</strong>
            {byline ? <span>{byline}</span> : null}
          </span>
        </button>
        <div className="fiches-title-side">
          <Badge size="1" variant="soft" color={levelColor(title.level)} highContrast>
            {LEVEL_LABELS[title.level] ?? title.level}
          </Badge>
          <Button size="1" variant="soft" color="gray" onClick={onPlay} className="fiches-play">
            {playing ? <Pause className="ui-button-icon" /> : <Play className="ui-button-icon" />}
            {playing ? "Arrêter" : "Écouter"}
            <span className="ui-visually-hidden"> {name}</span>
          </Button>
        </div>
      </div>
      {/* Déplié, la fiche montre chaque proposition en entier. */}
      {title.propositions.length && !detail ? (
        <ul className="fiches-summary">
          {title.propositions.map((one) => (
            <li key={one.id}>
              <span className="fiches-field">{FIELD_LABELS[one.field] ?? one.field}</span>{" "}
              <span className="fiches-before">{fieldValue(one.field, one.before)}</span>
              <span aria-hidden="true"> → </span>
              <span className="ui-visually-hidden"> devient </span>
              <strong>{fieldValue(one.field, one.value)}</strong>
              {propositionStatus(one) ? (
                <span className="fiches-summary-state"> · {propositionStatus(one)?.label}</span>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
      {detail === "loading" ? (
        <div className="fiches-detail" role="status">
          <Spinner size="1" /> Lecture de la fiche…
        </div>
      ) : typeof detail === "string" ? (
        <p className="fiches-detail banque-note is-danger" role="alert">
          {detail}
        </p>
      ) : detail ? (
        <FicheCard detail={detail} name={name} gestures={gestures} />
      ) : null}
    </li>
  );
}

function FicheCard({ detail, name, gestures }: { detail: FicheDetail; name: string; gestures: Gestures }) {
  const { fiche, evidence, title } = detail;
  const gap = durationGap(title.duration, evidence?.duration ?? null);
  const waiting = detail.propositions.filter((one) => one.state === "proposée").map((one) => one.id);
  return (
    <div className="fiches-detail">
      {evidence ? (
        <section className="fiches-evidence" aria-label="Ce que la recherche a trouvé">
          <Cover url={evidence.cover} album={evidence.album} />
          <p className="fiches-evidence-head">
            Trouvé sur {evidence.found_at || fiche.source || "une source"}
            {evidence.url ? (
              <>
                {" · "}
                <a href={evidence.url} target="_blank" rel="noopener noreferrer" className="fiches-link">
                  Écouter sur {platformName(evidence.platform, evidence.found_at)}
                  <ExternalLink size={12} aria-hidden="true" />
                </a>
              </>
            ) : null}
          </p>
          <dl className="fiches-facts">
            {evidence.title ? (
              <>
                <dt>Titre trouvé</dt>
                <dd>
                  {evidence.title}
                  {evidence.artists ? `, de ${evidence.artists}` : ""}
                </dd>
              </>
            ) : null}
            {evidence.album ? (
              <>
                <dt>Album trouvé</dt>
                <dd>{evidence.album}</dd>
              </>
            ) : null}
            <dt>Durée</dt>
            <dd>
              fichier {duration(title.duration)}
              {evidence.duration != null ? `, trouvée ${duration(evidence.duration)}` : ""}
              {gap ? ` (${gap})` : ""}
            </dd>
            {evidence.genres ? (
              <>
                <dt>Genres</dt>
                <dd>{evidence.genres}</dd>
              </>
            ) : null}
            {evidence.year_source ? (
              <>
                <dt>Année</dt>
                <dd>d'après {evidence.year_source}</dd>
              </>
            ) : null}
          </dl>
          {evidence.doubt ? <p className="fiches-doubt">{evidence.doubt}</p> : null}
        </section>
      ) : null}
      {fiche.reasons.length ? (
        <ul className="fiches-reasons" aria-label="Pourquoi ce niveau">
          {fiche.reasons.map((reason) => (
            <li key={reason}>{reason}</li>
          ))}
        </ul>
      ) : null}
      {detail.propositions.length ? (
        <ul className="fiches-props" aria-label="Propositions">
          {detail.propositions.map((one) => (
            <PropositionItem key={one.id} proposition={one} beetsId={title.id} gestures={gestures} />
          ))}
        </ul>
      ) : null}
      <div className="fiches-actions">
        {waiting.length && gestures.canWrite ? (
          <Button
            size="2"
            variant="soft"
            disabled={gestures.busy}
            onClick={() => gestures.decide(waiting, [], title.id)}
          >
            <Check className="ui-button-icon" />
            {waiting.length === 1 ? "Accepter la proposition" : `Accepter les ${waiting.length} propositions`}
            <span className="ui-visually-hidden"> de {name}</span>
          </Button>
        ) : null}
        {waiting.length ? (
          <Button
            size="2"
            variant="soft"
            color="gray"
            disabled={gestures.busy}
            onClick={() => gestures.decide([], waiting, title.id)}
          >
            <X className="ui-button-icon" />
            {waiting.length === 1 ? "Refuser la proposition" : `Refuser les ${waiting.length} propositions`}
            <span className="ui-visually-hidden"> de {name}</span>
          </Button>
        ) : null}
        <Button
          size="2"
          variant="ghost"
          color="gray"
          disabled={gestures.busy}
          onClick={() => gestures.searchAgain(title.id, name)}
        >
          <RefreshCw className="ui-button-icon" />
          Chercher de nouveau
        </Button>
      </div>
      <p className="fiches-meta">
        {fiche.status === "erreur" && fiche.error ? `Erreur : ${fiche.error}. ` : ""}
        Cherché {formatWhen(fiche.searched_at)}
        {fiche.attempts > 1 ? `, ${fiche.attempts} essais` : ""}
        {fiche.next_at ? `, prochain essai ${formatWhen(fiche.next_at)}` : ""}. Fichier : {title.path}
      </p>
    </div>
  );
}

function PropositionItem({
  proposition,
  beetsId,
  gestures,
}: {
  proposition: FicheProposition;
  beetsId: number;
  gestures: Gestures;
}) {
  const field = FIELD_LABELS[proposition.field] ?? proposition.field;
  const status = propositionStatus(proposition);
  return (
    <li className="fiches-prop">
      <div className="fiches-prop-head">
        <strong>{FIELD_LABELS[proposition.field] ?? proposition.field}</strong>
        <Badge size="1" variant="soft" color={levelColor(proposition.level)} highContrast>
          {LEVEL_LABELS[proposition.level] ?? proposition.level}
        </Badge>
        {status ? (
          <Badge size="1" variant="soft" color={status.color} highContrast>
            {status.label}
          </Badge>
        ) : null}
      </div>
      <p className="fiches-prop-change">
        <span className="fiches-before">{fieldValue(proposition.field, proposition.before)}</span>
        <span aria-hidden="true"> → </span>
        <span className="ui-visually-hidden"> devient </span>
        <strong>{fieldValue(proposition.field, proposition.value)}</strong>
      </p>
      {proposition.why || proposition.source ? (
        <p className="fiches-prop-why">
          {[proposition.why, proposition.source ? `source : ${proposition.source}` : ""].filter(Boolean).join(" · ")}
        </p>
      ) : null}
      {status?.note ? (
        <p
          className={`fiches-prop-note${status.color === "red" ? " is-danger" : status.color === "orange" ? " is-warn" : ""}`}
        >
          {status.note}
        </p>
      ) : null}
      {proposition.state === "proposée" || (proposition.state === "écrite" && gestures.canWrite) ? (
        <div className="fiches-prop-actions">
          {proposition.state === "proposée" && gestures.canWrite ? (
            <Button
              size="1"
              variant="soft"
              disabled={gestures.busy}
              onClick={() => gestures.decide([proposition.id], [], beetsId)}
            >
              <Check className="ui-button-icon" />
              Accepter<span className="ui-visually-hidden"> {field}</span>
            </Button>
          ) : null}
          {proposition.state === "proposée" ? (
            <Button
              size="1"
              variant="soft"
              color="gray"
              disabled={gestures.busy}
              onClick={() => gestures.decide([], [proposition.id], beetsId)}
            >
              <X className="ui-button-icon" />
              Refuser<span className="ui-visually-hidden"> {field}</span>
            </Button>
          ) : null}
          {proposition.state === "écrite" ? (
            <Button
              size="1"
              variant="soft"
              color="gray"
              disabled={gestures.busy}
              onClick={() => gestures.revert(proposition, beetsId)}
            >
              <RotateCcw className="ui-button-icon" />
              Revenir<span className="ui-visually-hidden"> à la valeur d'avant de {field}</span>
            </Button>
          ) : null}
        </div>
      ) : null}
    </li>
  );
}
