import { Badge, Button, Select, Spinner, TextField } from "@radix-ui/themes";
import { ChevronDown, ChevronRight, CloudOff, ExternalLink, FileSearch, Pause, Play, Search } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { API_PREFIX, ApiRequestError, apiGet } from "../../api/client";
import {
  FICHES_JSON,
  FIELD_LABELS,
  LEVEL_LABELS,
  NO_FILTERS,
  STATE_LABELS,
  bankLabel,
  duration,
  durationGap,
  fichesQuery,
  fieldValue,
  levelChips,
  levelColor,
  platformName,
  progressLine,
  type FicheDetail,
  type FicheProposition,
  type FicheTitle,
  type FichesFilters,
  type FichesPage,
} from "../../api/fiches";
import { formatWhen } from "../../api/updates";
import { usePreview } from "../../lib/usePreview";
import { AppToast, useAppToast } from "../../ui/AppToast";
import { ErrorState, LoadingState } from "../../ui/DataState";
import { EmptyState } from "../../ui/EmptyState";
import { Cover } from "./Cover";
import "../../styles/pages/fiches.css";

// Radix ne prend pas une valeur vide pour un choix de liste.
const ALL = "tous";
// Le temps de laisser finir la frappe avant de chercher.
const TYPING_MS = 350;

function messageOf(caught: unknown, fallback: string): string {
  return caught instanceof Error && caught.message ? caught.message : fallback;
}

/**
 * Sons → Banque → À relire (FON-26) : ce que la recherche en ligne propose pour
 * les fiches, par niveau, avec d'où ça vient. En lecture : rien ne s'accepte
 * encore (FON-27).
 */
export function ReviewView() {
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

  return (
    <section className="fiches" aria-label="Fiches à relire">
      <header className="fiches-head">
        <div className="fiches-intro">
          <p className="fiches-progress">{progressLine(page)}</p>
          <p className="fiches-hint">
            Ce que la recherche en ligne propose de corriger, titre par titre, avec d'où ça vient. Rien ne s'écrit
            encore depuis cette vue.
          </p>
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
}: {
  title: FicheTitle;
  detail: FicheDetail | "loading" | string | undefined;
  playing: boolean;
  onToggle: () => void;
  onPlay: () => void;
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
        <FicheCard detail={detail} />
      ) : null}
    </li>
  );
}

function FicheCard({ detail }: { detail: FicheDetail }) {
  const { fiche, evidence, title } = detail;
  const gap = durationGap(title.duration, evidence?.duration ?? null);
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
            <PropositionItem key={one.id} proposition={one} />
          ))}
        </ul>
      ) : null}
      <p className="fiches-meta">
        {fiche.status === "erreur" && fiche.error ? `Erreur : ${fiche.error}. ` : ""}
        Cherché {formatWhen(fiche.searched_at)}
        {fiche.attempts > 1 ? `, ${fiche.attempts} essais` : ""}
        {fiche.next_at ? `, prochain essai ${formatWhen(fiche.next_at)}` : ""}. Fichier : {title.path}
      </p>
    </div>
  );
}

function PropositionItem({ proposition }: { proposition: FicheProposition }) {
  return (
    <li className="fiches-prop">
      <div className="fiches-prop-head">
        <strong>{FIELD_LABELS[proposition.field] ?? proposition.field}</strong>
        <Badge size="1" variant="soft" color={levelColor(proposition.level)} highContrast>
          {LEVEL_LABELS[proposition.level] ?? proposition.level}
        </Badge>
        {proposition.state !== "proposée" ? (
          <Badge size="1" variant="soft" color="gray" highContrast>
            {STATE_LABELS[proposition.state] ?? proposition.state}
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
    </li>
  );
}
