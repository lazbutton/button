import { Badge, Button, Select, Spinner } from "@radix-ui/themes";
import { ChevronDown, ChevronRight, CloudOff, History, RotateCcw } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { ApiRequestError, apiGet, apiPostJson } from "../../api/client";
import {
  JOURNAL_JSON,
  STATUS_LABELS,
  changeField,
  changeValue,
  entryByline,
  entryNotes,
  entryTitle,
  journalQuery,
  undoQuestion,
  type JournalDetail,
  type JournalEntry,
  type JournalPage,
} from "../../api/journal";
import { TITLES_SEND_DEADLINE_MS } from "../../api/sendDeadline";
import { formatWhen } from "../../api/updates";
import { undoneMessage, type EditOutcome } from "../../api/titleEdits";
import { AppToast, useAppToast } from "../../ui/AppToast";
import { ConfirmDialog } from "../../ui/ConfirmDialog";
import { ErrorState, LoadingState } from "../../ui/DataState";
import { EmptyState } from "../../ui/EmptyState";
import "../../styles/pages/journal.css";

// Radix ne prend pas une valeur vide pour un choix de liste.
const ALL = "tous";
// Les lignes d'un lot montrées d'un coup dans son détail.
const DETAIL_ROWS = 200;

function messageOf(caught: unknown, fallback: string): string {
  return caught instanceof Error && caught.message ? caught.message : fallback;
}

/**
 * Sons → Journal (FON-71) : qui a changé quoi dans la banque, quand, et sur
 * combien de titres. Un lot s'annule d'un coup pendant 30 jours ; un titre
 * changé depuis garde sa valeur, et l'annulation le dit.
 */
export function JournalView() {
  const [filters, setFilters] = useState({ gesture: "", username: "" });
  const [page, setPage] = useState<JournalPage | null>(null);
  const [entries, setEntries] = useState<JournalEntry[]>([]);
  const [problem, setProblem] = useState("");
  const [closed, setClosed] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [open, setOpen] = useState<Record<number, JournalDetail | "loading" | string>>({});
  const [undoing, setUndoing] = useState<JournalEntry | null>(null);
  const [busy, setBusy] = useState(false);
  const { toast, show, dismiss } = useAppToast();
  const ticket = useRef(0);

  const load = useCallback(async () => {
    const mine = ++ticket.current;
    try {
      const next = await apiGet<JournalPage>(`${JOURNAL_JSON}${journalQuery(filters)}`);
      if (mine !== ticket.current) return;
      setPage(next);
      setEntries(next.entries);
      setProblem("");
    } catch (caught) {
      if (mine !== ticket.current) return;
      if (caught instanceof ApiRequestError && caught.status === 404) setClosed(true);
      else setProblem(messageOf(caught, "Le journal ne s'est pas lu. Réessaie."));
    }
  }, [filters]);

  useEffect(() => {
    void load();
  }, [load]);

  const loadMore = async () => {
    if (!page?.next || loadingMore) return;
    setLoadingMore(true);
    try {
      const next = await apiGet<JournalPage>(`${JOURNAL_JSON}${journalQuery(filters, page.next)}`);
      setEntries((before) => [...before, ...next.entries]);
      setPage(next);
    } catch (caught) {
      show(messageOf(caught, "La suite du journal ne s'est pas lue."), "error");
    } finally {
      setLoadingMore(false);
    }
  };

  const toggle = async (entry: JournalEntry) => {
    if (open[entry.id]) {
      setOpen(({ [entry.id]: _gone, ...rest }) => rest);
      return;
    }
    setOpen((before) => ({ ...before, [entry.id]: "loading" }));
    try {
      const detail = await apiGet<JournalDetail>(`/media/journal/${entry.id}.json`);
      setOpen((before) => ({ ...before, [entry.id]: detail }));
    } catch (caught) {
      setOpen((before) => ({ ...before, [entry.id]: messageOf(caught, "Le détail ne s'est pas lu.") }));
    }
  };

  const confirmUndo = async () => {
    if (!undoing) return;
    setBusy(true);
    try {
      const outcome = await apiPostJson<EditOutcome>(
        `/media/journal/${undoing.id}/undo.json`,
        {},
        TITLES_SEND_DEADLINE_MS,
      );
      const message = undoneMessage(outcome);
      show(message.text, message.tone);
    } catch (caught) {
      show(messageOf(caught, "Le lot n'a pas été défait. Réessaie."), "error");
    } finally {
      setBusy(false);
      setUndoing(null);
      setOpen({});
      await load();
    }
  };

  if (closed) {
    return (
      <EmptyState
        icon={CloudOff}
        title="Mets à jour le moteur"
        description="Le moteur de cette station ne tient pas encore le journal des gestes."
      />
    );
  }
  if (!page) {
    return problem ? (
      <ErrorState title="Journal illisible" description={problem} onRetry={() => void load()} />
    ) : (
      <LoadingState label="Lecture du journal…" />
    );
  }

  return (
    <section className="journal" aria-label="Journal des gestes">
      <header className="journal-head">
        <p className="journal-intro">
          Les gestes sur la banque : qui, quand, quoi, et sur combien de titres. Un lot s'annule pendant{" "}
          {page.undo_days} jours.
        </p>
        <div className="journal-filters">
          <label className="journal-filter">
            <span className="ui-field-label">Geste</span>
            <Select.Root
              value={filters.gesture || ALL}
              onValueChange={(value) => setFilters((before) => ({ ...before, gesture: value === ALL ? "" : value }))}
            >
              <Select.Trigger aria-label="Geste" />
              <Select.Content variant="soft" position="popper">
                <Select.Item value={ALL}>Tous les gestes</Select.Item>
                {page.gestures.map((gesture) => (
                  <Select.Item key={gesture.value} value={gesture.value}>
                    {gesture.label ?? gesture.value} ({gesture.count})
                  </Select.Item>
                ))}
              </Select.Content>
            </Select.Root>
          </label>
          <label className="journal-filter">
            <span className="ui-field-label">Personne</span>
            <Select.Root
              value={filters.username || ALL}
              onValueChange={(value) => setFilters((before) => ({ ...before, username: value === ALL ? "" : value }))}
            >
              <Select.Trigger aria-label="Personne" />
              <Select.Content variant="soft" position="popper">
                <Select.Item value={ALL}>Tout le monde</Select.Item>
                {page.people.map((person) => (
                  <Select.Item key={person.value} value={person.value}>
                    {person.value} ({person.count})
                  </Select.Item>
                ))}
              </Select.Content>
            </Select.Root>
          </label>
        </div>
      </header>

      {problem ? (
        <div className="banque-note is-danger" role="alert">
          <span>Le journal n'a pas pu se relire : {problem}</span>
          <Button size="1" variant="soft" color="gray" onClick={() => void load()}>
            Réessayer
          </Button>
        </div>
      ) : null}

      {entries.length === 0 ? (
        <EmptyState
          icon={History}
          title={filters.gesture || filters.username ? "Aucun geste ainsi" : "Aucun geste encore"}
          description={
            filters.gesture || filters.username
              ? "Aucun lot ne répond à ces filtres."
              : "Les corrections de fiches s'inscrivent ici, avec ce qu'elles ont changé."
          }
        />
      ) : (
        <ol className="journal-list">
          {entries.map((entry) => {
            const detail = open[entry.id];
            const notes = entryNotes(entry.counts);
            return (
              <li key={entry.id} className="journal-entry">
                <div className="journal-entry-main">
                  <button
                    type="button"
                    className="journal-toggle"
                    aria-expanded={Boolean(detail)}
                    onClick={() => void toggle(entry)}
                  >
                    {detail ? <ChevronDown size={16} aria-hidden="true" /> : <ChevronRight size={16} aria-hidden="true" />}
                    <span className="journal-entry-copy">
                      <strong>{entryTitle(entry)}</strong>
                      <span>{entryByline(entry)}</span>
                    </span>
                  </button>
                  <div className="journal-entry-side">
                    {entry.undone_by ? (
                      <Badge size="1" variant="soft" color="gray" highContrast>
                        Défait par {entry.undone_by.username}, {formatWhen(entry.undone_by.created)}
                      </Badge>
                    ) : null}
                    {entry.undoable ? (
                      <Button size="1" variant="soft" color="gray" disabled={busy} onClick={() => setUndoing(entry)}>
                        <RotateCcw className="ui-button-icon" />
                        Annuler
                      </Button>
                    ) : null}
                  </div>
                </div>
                {notes.length ? <p className="journal-entry-notes">{notes.join(" · ")}.</p> : null}
                {!entry.undoable && !entry.undone_by && entry.why_not ? (
                  <p className="journal-entry-notes">{entry.why_not}</p>
                ) : null}
                {detail === "loading" ? (
                  <div className="journal-detail" role="status">
                    <Spinner size="1" /> Lecture du détail…
                  </div>
                ) : typeof detail === "string" ? (
                  <p className="journal-detail banque-note is-danger" role="alert">
                    {detail}
                  </p>
                ) : detail ? (
                  <ChangeTable detail={detail} />
                ) : null}
              </li>
            );
          })}
        </ol>
      )}

      {page.next != null ? (
        <div className="banque-more">
          <Button size="2" variant="soft" color="gray" disabled={loadingMore} onClick={() => void loadMore()}>
            {loadingMore ? <Spinner size="1" /> : null}
            Afficher les lots plus anciens
          </Button>
        </div>
      ) : null}

      <ConfirmDialog
        open={undoing != null}
        onOpenChange={(next) => {
          if (!next && !busy) setUndoing(null);
        }}
        busy={busy}
        title={undoing ? `Annuler : ${entryTitle(undoing).toLowerCase()} ?` : "Annuler ce lot ?"}
        description={undoing ? undoQuestion(undoing) : ""}
        confirmLabel="Annuler le lot"
        cancelLabel="Garder"
        onConfirm={confirmUndo}
      />
      <AppToast toast={toast} onDismiss={dismiss} />
    </section>
  );
}

function ChangeTable({ detail }: { detail: JournalDetail }) {
  const rows = detail.changes.slice(0, DETAIL_ROWS);
  return (
    <div className="journal-detail">
      <table className="journal-changes">
        <caption className="ui-visually-hidden">Ce que le lot a changé, titre par titre</caption>
        <thead>
          <tr>
            <th scope="col">Titre</th>
            <th scope="col">Champ</th>
            <th scope="col">Avant</th>
            <th scope="col">Après</th>
            <th scope="col">État</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((change, index) => (
            <tr key={`${change.id}-${change.field}-${index}`}>
              <td>{change.label || change.path}</td>
              <td>{changeField(change.field)}</td>
              <td>{changeValue(change.old)}</td>
              <td>{changeValue(change.new)}</td>
              <td title={change.reason ?? undefined}>{STATUS_LABELS[change.status] ?? change.status}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {detail.changes.length > rows.length ? (
        <p className="journal-entry-notes">
          Les {rows.length} premières lignes sur {detail.changes.length}.
        </p>
      ) : null}
    </div>
  );
}
