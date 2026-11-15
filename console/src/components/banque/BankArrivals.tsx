import { Badge, Button, Spinner } from "@radix-ui/themes";
import { Check, ChevronDown, ChevronUp, RefreshCw, Sparkles, TriangleAlert, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useAccount } from "../../api/AccountContext";
import {
  type Arrival,
  type Arrivals,
  arrivalsLine,
  arrivalsPath,
  duplicateLine,
  nameLine,
  propositionLine,
  shelfOf,
  tidiedMessage,
  tidyAllAction,
  tidyLot,
  tidyPlan,
} from "../../api/bankArrivals";
import { ApiRequestError, apiGet, apiPostJson } from "../../api/client";
import {
  chunks,
  type Decided,
  decidedMessage,
  FICHES_DECISIONS_JSON,
  LEVEL_LABELS,
  levelColor,
} from "../../api/fiches";
import { TITLES_SEND_DEADLINE_MS } from "../../api/sendDeadline";
import { unrenamedMessage } from "../../api/titleRenames";
import { formatWhen } from "../../api/updates";
import { AppToast, useAppToast } from "../../ui/AppToast";
import { ConfirmDialog } from "../../ui/ConfirmDialog";
import { ErrorState, LoadingState } from "../../ui/DataState";
import { EmptyState } from "../../ui/EmptyState";
import { messageOf, undoTitles } from "./TitleEditing";
import { readChoice, renameAll } from "./TitleRenaming";

const NOTHING: Decided = {
  accepted: 0,
  refused: 0,
  written: 0,
  waiting: [],
  failed: [],
  stale: 0,
  entry: null,
};

function ArrivalRow({
  title,
  canTidy,
  canDecide,
  busy,
  onTidy,
  onDecide,
}: {
  title: Arrival;
  canTidy: boolean;
  canDecide: boolean;
  busy: boolean;
  onTidy: () => void;
  onDecide: (accept: number[], refuse: number[]) => void;
}) {
  const [open, setOpen] = useState(false);
  const name = title.path.split("/").pop() ?? title.path;
  const label = title.artist && title.title ? `${title.artist} – ${title.title}` : title.title || name;
  return (
    <li className="banque-arrival">
      <div className="banque-arrival-head">
        <div>
          <strong>{label}</strong>
          <span>
            {shelfOf(title)} · arrivé {formatWhen(title.added)}
          </span>
        </div>
        <div className="banque-arrival-actions">
          {title.ready && canTidy ? (
            <Button size="1" variant="soft" color="gray" disabled={busy} onClick={onTidy}>
              <Sparkles className="ui-button-icon" />
              Ranger
            </Button>
          ) : null}
          {title.review ? (
            <Button
              size="1"
              variant="soft"
              color="gray"
              aria-expanded={open}
              onClick={() => setOpen((before) => !before)}
            >
              {open ? <ChevronUp className="ui-button-icon" /> : <ChevronDown className="ui-button-icon" />}
              Relire
            </Button>
          ) : null}
        </div>
      </div>
      {!title.searched ? <p className="banque-arrival-note">Pas encore cherché en ligne.</p> : null}
      {title.propositions.length ? (
        <ul className="banque-arrival-propositions" aria-label={`Fiche proposée pour ${label}`}>
          {title.propositions.map((proposition) => (
            <li key={proposition.id}>
              <Badge color={levelColor(proposition.level)} variant="soft" highContrast>
                {LEVEL_LABELS[proposition.level] ?? proposition.level}
              </Badge>{" "}
              <span>{propositionLine(proposition)}</span>
              {open && canDecide ? (
                <span className="banque-arrival-decide">
                  <Button
                    size="1"
                    variant="soft"
                    color="gray"
                    disabled={busy}
                    onClick={() => onDecide([proposition.id], [])}
                  >
                    <Check className="ui-button-icon" />
                    Accepter
                  </Button>
                  <Button
                    size="1"
                    variant="soft"
                    color="gray"
                    disabled={busy}
                    onClick={() => onDecide([], [proposition.id])}
                  >
                    <X className="ui-button-icon" />
                    Refuser
                  </Button>
                </span>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
      {title.to ? <p className="banque-arrival-name">Nom : {nameLine(title)}</p> : null}
      {title.duplicates.length ? (
        <p className="banque-arrival-twin">
          <TriangleAlert size={13} aria-hidden="true" /> {duplicateLine(title.duplicates)}
        </p>
      ) : null}
    </li>
  );
}

/**
 * La vue Arrivées de Sons → Banque (FON-81) : les titres arrivés depuis 30 jours,
 * avec la fiche proposée, le nom d'après le dernier modèle choisi et les doublons
 * possibles. « Ranger » accepte les propositions sûres, puis renomme ; un titre à
 * relire s'ouvre, proposition par proposition. Un fichier nouveau joue déjà.
 */
export function BankArrivalsView() {
  const { isAdmin, account } = useAccount();
  const programmer = isAdmin || account?.permissions.autodj === true;
  const canDecide = account?.features?.title_edits === true && programmer;
  const canTidy = canDecide && account?.features?.title_renames === true;
  const [choice] = useState(() => readChoice());
  const [payload, setPayload] = useState<Arrivals | null>(null);
  const [problem, setProblem] = useState("");
  const [outdated, setOutdated] = useState(false);
  const [busy, setBusy] = useState(false);
  const [asking, setAsking] = useState(false);
  const { toast, show, dismiss } = useAppToast();

  const load = useCallback(async () => {
    setProblem("");
    try {
      setPayload(await apiGet<Arrivals>(arrivalsPath(choice.model)));
    } catch (caught) {
      if (caught instanceof ApiRequestError && caught.status === 404) setOutdated(true);
      else setProblem(messageOf(caught, "Les arrivées ne se sont pas lues. Réessaie."));
    }
  }, [choice.model]);

  useEffect(() => {
    void load();
  }, [load]);

  // Un rangement se défait en entier, le dernier geste d'abord.
  const undo = async (entries: number[]) => {
    let written = 0;
    const kept: unknown[] = [];
    try {
      for (const entry of [...entries].reverse()) {
        const outcome = await undoTitles(entry);
        written += outcome.written;
        kept.push(...outcome.kept);
      }
      const message = unrenamedMessage({ written, kept });
      show(message.text, message.tone);
    } catch (caught) {
      show(messageOf(caught, "Le rangement ne s'est pas défait en entier. Réessaie depuis le journal."), "error");
    } finally {
      await load();
    }
  };

  const tidy = async (titles: Arrival[]) => {
    const lot = tidyLot(titles);
    setBusy(true);
    const total: Decided = { ...NOTHING, waiting: [], failed: [] };
    const entries: number[] = [];
    let renamed = 0;
    let kept = 0;
    try {
      for (const ids of chunks(lot.propositions)) {
        const decided = await apiPostJson<Decided>(FICHES_DECISIONS_JSON, { accept: ids }, TITLES_SEND_DEADLINE_MS);
        total.accepted += decided.accepted;
        total.written += decided.written;
        total.stale += decided.stale;
        total.waiting.push(...decided.waiting);
        total.failed.push(...decided.failed);
        if (decided.entry != null) entries.push(decided.entry);
      }
      for (const ids of chunks(lot.renamed)) {
        // Dans son dossier, comme l'aperçu de la vue.
        const result = await renameAll(ids, { ...choice, byArtist: false });
        renamed += result.titles.filter((item) => item.state === "renamed").length;
        kept += result.titles.filter((item) => item.state !== "renamed").length;
        entries.push(...result.entries);
      }
      const message = tidiedMessage(lot.titles, total, renamed, kept);
      show(
        message.text,
        message.tone,
        entries.length ? { action: { label: "Annuler", onClick: () => void undo(entries) } } : undefined,
      );
    } catch (caught) {
      const done = entries.length ? " Ce qui est fait se défait depuis le journal." : "";
      show(`${messageOf(caught, "Le rangement n'a pas abouti. Réessaie.")}${done}`, "error");
    } finally {
      setBusy(false);
      setAsking(false);
      await load();
    }
  };

  const decide = async (accept: number[], refuse: number[]) => {
    setBusy(true);
    try {
      const decided = await apiPostJson<Decided>(FICHES_DECISIONS_JSON, { accept, refuse }, TITLES_SEND_DEADLINE_MS);
      const message = decidedMessage(decided);
      show(message.text, message.tone);
    } catch (caught) {
      show(messageOf(caught, "La décision n'a pas été prise. Réessaie."), "error");
    } finally {
      setBusy(false);
      await load();
    }
  };

  if (outdated)
    return (
      <ErrorState
        title="Arrivées indisponibles"
        description="Cette vue demande un moteur plus récent. Mets à jour le moteur."
        onRetry={() => {
          setOutdated(false);
          void load();
        }}
      />
    );
  if (!payload)
    return problem ? (
      <ErrorState title="Arrivées illisibles" description={problem} onRetry={() => void load()} />
    ) : (
      <LoadingState label="Lecture des arrivées…" />
    );

  const lot = tidyLot(payload.titles);
  return (
    <div className="banque-arrivals">
      <header className="banque-health-head">
        <div>
          <h2>Arrivées</h2>
          <p className="banque-health-when">{arrivalsLine(payload)}</p>
        </div>
        <div className="banque-arrival-actions">
          <Button size="1" variant="soft" color="gray" disabled={busy} onClick={() => void load()}>
            {busy ? <Spinner size="1" /> : <RefreshCw className="ui-button-icon" />}
            Relire la liste
          </Button>
          {canTidy && lot.titles ? (
            <Button size="1" highContrast disabled={busy} onClick={() => setAsking(true)}>
              <Sparkles className="ui-button-icon" />
              {tidyAllAction(lot.titles)}
            </Button>
          ) : null}
        </div>
      </header>
      <p className="banque-health-note">
        Un fichier nouveau passe déjà à l'antenne. Ranger accepte les propositions sûres de sa fiche, puis lui donne le
        nom de sa fiche, d'après le dernier modèle choisi dans « Renommer ».
      </p>
      {problem ? (
        <p className="banque-health-problem" role="alert">
          {problem}
        </p>
      ) : null}
      {payload.titles.length ? (
        <ul className="banque-arrival-list" aria-label="Titres arrivés">
          {payload.titles.map((title) => (
            <ArrivalRow
              key={title.id}
              title={title}
              canTidy={canTidy}
              canDecide={canDecide}
              busy={busy}
              onTidy={() => void tidy([title])}
              onDecide={(accept, refuse) => void decide(accept, refuse)}
            />
          ))}
        </ul>
      ) : (
        <EmptyState
          icon={Sparkles}
          title="Rien de nouveau"
          description={`Aucun titre n'est arrivé dans la banque en ${payload.days} jours.`}
        />
      )}
      <ConfirmDialog
        open={asking}
        onOpenChange={setAsking}
        title={`${tidyAllAction(lot.titles)} ?`}
        description={tidyPlan(lot)}
        confirmLabel={tidyAllAction(lot.titles)}
        busy={busy}
        onConfirm={() => tidy(payload.titles)}
      />
      <AppToast toast={toast} onDismiss={dismiss} />
    </div>
  );
}
