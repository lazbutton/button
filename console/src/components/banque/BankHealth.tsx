import { Badge, Button, Spinner } from "@radix-ui/themes";
import { CircleCheck, FilePen, PenLine, RefreshCw, Table2, Tags } from "lucide-react";
import { type ReactNode, useCallback, useEffect, useId, useState } from "react";
import { useAccount } from "../../api/AccountContext";
import {
  archiveAction,
  archiveLot,
  completeLine,
  emptyFieldTable,
  familiesLine,
  type HealthAnswer,
  type HealthTitle,
  healthPath,
  incompleteLine,
  lotOf,
  moreLine,
  placeLine,
  plural,
  POLL_MS,
  renameAction,
  renameLine,
  spellingAction,
  spellingLine,
} from "../../api/bankHealth";
import { ApiRequestError, apiGet } from "../../api/client";
import { type EditLot, type EditOutcome, type FicheForm, savedMessage, undoneMessage, withoutTitles } from "../../api/titleEdits";
import { renamedMessage, unrenamedMessage } from "../../api/titleRenames";
import { formatWhen } from "../../api/updates";
import { AppToast, useAppToast } from "../../ui/AppToast";
import { ErrorState, LoadingState } from "../../ui/DataState";
import { ConfirmLotDialog, EditTitlesDialog, editTitles, messageOf, undoTitles } from "./TitleEditing";
import { readChoice, RenameTitlesDialog, type RenameResult } from "./TitleRenaming";

// Ce qu'une liste montre avant « et N de plus ».
const SHOWN = 20;

function HealthSection({
  title,
  count,
  unit,
  children,
}: {
  title: string;
  count: number;
  unit: [string, string];
  children: ReactNode;
}) {
  const heading = useId();
  return (
    <section className="banque-health-section" aria-labelledby={heading}>
      <h3 id={heading}>
        <span>{title}</span>{" "}
        {count ? (
          <Badge color="amber" variant="soft" highContrast>
            {plural(count, ...unit)}
          </Badge>
        ) : (
          <Badge color="green" variant="soft" highContrast>
            <CircleCheck size={12} aria-hidden="true" /> Rien à signaler
          </Badge>
        )}
      </h3>
      {count ? children : null}
    </section>
  );
}

/**
 * La vue Santé de Sons → Banque (FON-72) : la banque en chiffres, puis ce qui
 * cloche, compté par nature. Chaque ligne ouvre sa correction : la fiche d'un
 * lot (FON-66), le renommage (FON-68), ou le tableau rangé sur le champ vide.
 * Le moteur compte à part ; la vue redemande tant qu'il compte.
 */
export function BankHealthView({ onOpenTable }: { onOpenTable: (table: Record<string, string>) => void }) {
  const { isAdmin, account } = useAccount();
  const programmer = isAdmin || account?.permissions.autodj === true;
  const canEdit = account?.features?.title_edits === true && programmer;
  const canRename = account?.features?.title_renames === true && programmer;
  // Le modèle de nom que la personne a choisi en dernier, dans la fenêtre « Renommer ».
  const [model] = useState(() => readChoice().model);
  const [answer, setAnswer] = useState<HealthAnswer | null>(null);
  const [problem, setProblem] = useState("");
  const [outdated, setOutdated] = useState(false);
  const [editing, setEditing] = useState<{ titles: HealthTitle[]; preset?: Partial<FicheForm> } | null>(null);
  const [renaming, setRenaming] = useState<HealthTitle[] | null>(null);
  const [archiving, setArchiving] = useState<{ lot: EditLot; outcome: EditOutcome } | null>(null);
  const [busy, setBusy] = useState(false);
  const { toast, show, dismiss } = useAppToast();

  const load = useCallback(
    async (refresh = false) => {
      setProblem("");
      try {
        setAnswer(await apiGet<HealthAnswer>(healthPath(model, refresh)));
      } catch (caught) {
        if (caught instanceof ApiRequestError && caught.status === 404) setOutdated(true);
        else setProblem(messageOf(caught, "La santé de la banque ne s'est pas lue. Réessaie."));
      }
    },
    [model],
  );

  useEffect(() => {
    void load();
  }, [load]);

  // Le compte tourne à part : la vue redemande jusqu'à ce qu'il soit fait.
  useEffect(() => {
    if (!answer?.computing) return;
    const timer = window.setTimeout(() => void load(), POLL_MS);
    return () => window.clearTimeout(timer);
  }, [answer, load]);

  const undo = async (entry: number) => {
    try {
      const message = undoneMessage(await undoTitles(entry));
      show(message.text, message.tone);
    } catch (caught) {
      show(messageOf(caught, "Les fiches n'ont pas repris leur valeur. Réessaie depuis le journal."), "error");
    } finally {
      await load();
    }
  };

  const afterEdit = async (outcome: EditOutcome) => {
    const message = savedMessage(outcome);
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

  // Un lot que le moteur a dû couper se défait en entier, le dernier morceau d'abord.
  const unrename = async (entries: number[]) => {
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
      show(messageOf(caught, "Les fichiers n'ont pas repris leur nom. Réessaie depuis le journal."), "error");
    } finally {
      await load();
    }
  };

  const afterRename = async (result: RenameResult) => {
    const message = renamedMessage(result.titles);
    const entries = result.entries;
    show(
      message.text,
      message.tone,
      entries.length ? { action: { label: "Annuler", onClick: () => void unrename(entries) } } : undefined,
    );
    await load();
  };

  const tryArchive = async (titles: HealthTitle[]) => {
    const lot = archiveLot(titles);
    setBusy(true);
    try {
      setArchiving({ lot, outcome: await editTitles(lot, true) });
    } catch (caught) {
      show(messageOf(caught, "L'essai n'a pas abouti. Réessaie."), "error");
    } finally {
      setBusy(false);
    }
  };

  const writeArchive = async () => {
    if (!archiving) return;
    const refused = archiving.outcome.refused.map((issue) => issue.id);
    setBusy(true);
    try {
      const outcome = await editTitles(withoutTitles(archiving.lot, refused), false);
      setArchiving(null);
      await afterEdit(outcome);
    } catch (caught) {
      setArchiving(null);
      show(messageOf(caught, "Les fiches n'ont pas été modifiées. Réessaie."), "error");
    } finally {
      setBusy(false);
    }
  };

  if (outdated)
    return (
      <ErrorState
        title="Santé de la banque indisponible"
        description="Cette vue demande un moteur plus récent. Mets à jour le moteur."
        onRetry={() => {
          setOutdated(false);
          void load();
        }}
      />
    );
  if (!answer)
    return problem ? (
      <ErrorState title="Santé de la banque illisible" description={problem} onRetry={() => void load()} />
    ) : (
      <LoadingState label="Lecture de la santé de la banque…" />
    );

  const health = answer.health;
  return (
    <div className="banque-health">
      <header className="banque-health-head">
        <div>
          <h2>Santé de la banque</h2>
          <p className="banque-health-when" aria-live="polite">
            {answer.computing ? (
              <>
                <Spinner size="1" /> Compte en cours…
              </>
            ) : answer.computed_at ? (
              `Compté ${formatWhen(answer.computed_at)}.`
            ) : null}
          </p>
        </div>
        <Button size="1" variant="soft" color="gray" disabled={answer.computing} onClick={() => void load(true)}>
          <RefreshCw className="ui-button-icon" />
          Recompter
        </Button>
      </header>
      {answer.error || problem ? (
        <p className="banque-health-problem" role="alert">
          {problem || answer.error}
        </p>
      ) : null}
      {!health ? (
        answer.computing ? (
          <LoadingState label="Premier compte de la banque…" />
        ) : null
      ) : (
        <>
          <section className="banque-health-figures" aria-label="La banque en chiffres">
            <h3>La banque en chiffres</h3>
            <dl>
              <div>
                <dt>Titres</dt>
                <dd>{health.figures.titles.toLocaleString("fr-FR")}</dd>
              </div>
              <div>
                <dt>Fiches complètes</dt>
                <dd>{completeLine(health.figures)}</dd>
              </div>
              <div>
                <dt>Familles</dt>
                <dd>{familiesLine(health.figures)}</dd>
              </div>
            </dl>
          </section>

          <HealthSection
            title="Artistes écrits de plusieurs façons"
            count={health.spellings.count}
            unit={["artiste", "artistes"]}
          >
            <ul className="banque-health-list">
              {health.spellings.groups.slice(0, SHOWN).map((group) => (
                <li key={group.key}>
                  <div>
                    <strong>{spellingLine(group)}</strong>
                    <span>
                      {group.spellings.map((spelling) => `${spelling.value} (${spelling.count})`).join(" · ")}
                    </span>
                  </div>
                  {canEdit ? (
                    <Button
                      size="1"
                      variant="soft"
                      color="gray"
                      disabled={busy}
                      onClick={() =>
                        setEditing({ titles: lotOf(group.titles).taken, preset: { artist: group.suggested } })
                      }
                    >
                      <PenLine className="ui-button-icon" />
                      {spellingAction(group)}
                    </Button>
                  ) : null}
                </li>
              ))}
            </ul>
            <p className="banque-health-more">{moreLine(health.spellings.count, SHOWN, ["artiste", "artistes"])}</p>
          </HealthSection>

          <HealthSection title="Doublons" count={health.duplicates.count} unit={["doublon", "doublons"]}>
            <p className="banque-health-note">
              Même artiste, même titre, à 2 secondes près. Écoute-les dans le tableau, puis retire celui de trop.
            </p>
            <ul className="banque-health-list">
              {health.duplicates.groups.slice(0, SHOWN).map((group) => (
                <li key={group.titles.map((title) => title.id).join("-")}>
                  <div>
                    <strong>{group.label}</strong>
                    <span>{group.titles.map(placeLine).join(" · ")}</span>
                  </div>
                  <Button size="1" variant="soft" color="gray" onClick={() => onOpenTable({ q: group.titles[0].title })}>
                    <Table2 className="ui-button-icon" />
                    Voir dans le tableau
                  </Button>
                </li>
              ))}
            </ul>
            <p className="banque-health-more">{moreLine(health.duplicates.count, SHOWN, ["doublon", "doublons"])}</p>
          </HealthSection>

          <HealthSection title="Fichiers mal nommés" count={health.misnamed.count} unit={["fichier", "fichiers"]}>
            <ul className="banque-health-names">
              {health.misnamed.titles.slice(0, 5).map((title) => (
                <li key={title.id}>{renameLine(title)}</li>
              ))}
            </ul>
            <p className="banque-health-more">{moreLine(health.misnamed.count, 5, ["fichier", "fichiers"])}</p>
            {canRename ? (
              <Button
                size="1"
                variant="soft"
                color="gray"
                disabled={busy}
                onClick={() => setRenaming(lotOf(health.misnamed.titles).taken)}
              >
                <FilePen className="ui-button-icon" />
                {renameAction(health.misnamed.count)}
              </Button>
            ) : null}
          </HealthSection>

          <HealthSection title="Fiches incomplètes" count={health.incomplete.count} unit={["fiche", "fiches"]}>
            <ul className="banque-health-list">
              {health.incomplete.fields
                .filter((row) => row.count > 0)
                .map((row) => {
                  const table = emptyFieldTable(row.field);
                  return (
                    <li key={row.field}>
                      <div>
                        <strong>{incompleteLine(row.field, row.count)}</strong>
                      </div>
                      {table ? (
                        <Button size="1" variant="soft" color="gray" onClick={() => onOpenTable(table)}>
                          <Table2 className="ui-button-icon" />
                          Voir dans le tableau
                        </Button>
                      ) : null}
                    </li>
                  );
                })}
            </ul>
          </HealthSection>

          <HealthSection title="Genre « Archive »" count={health.archive.count} unit={["fiche", "fiches"]}>
            <p className="banque-health-note">
              L'ancienne boucle d'import l'écrivait dans chaque titre d'une collection. Le retirer garde les autres
              genres de chaque titre.
            </p>
            {canEdit ? (
              <Button
                size="1"
                variant="soft"
                color="gray"
                disabled={busy}
                onClick={() => void tryArchive(health.archive.titles)}
              >
                <Tags className="ui-button-icon" />
                {archiveAction(health.archive.count)}
              </Button>
            ) : null}
          </HealthSection>

          <HealthSection
            title="Fichiers absents de la bibliothèque"
            count={health.unindexed.count}
            unit={["fichier", "fichiers"]}
          >
            <p className="banque-health-note">
              Un fichier déposé attend une minute la boucle d'import. S'il reste ici, elle ne sait pas le lire.
            </p>
            <ul className="banque-health-names">
              {health.unindexed.paths.slice(0, SHOWN).map((path) => (
                <li key={path}>{path}</li>
              ))}
            </ul>
            <p className="banque-health-more">{moreLine(health.unindexed.count, SHOWN, ["fichier", "fichiers"])}</p>
          </HealthSection>
        </>
      )}

      {editing ? (
        <EditTitlesDialog
          titles={editing.titles}
          preset={editing.preset}
          onClose={() => setEditing(null)}
          onDone={(outcome) => {
            setEditing(null);
            void afterEdit(outcome);
          }}
        />
      ) : null}
      {renaming ? (
        <RenameTitlesDialog
          titles={renaming}
          onClose={() => setRenaming(null)}
          onDone={(result) => {
            setRenaming(null);
            void afterRename(result);
          }}
        />
      ) : null}
      {archiving ? (
        <ConfirmLotDialog
          question={`${archiveAction(archiving.lot.titles.length)} ?`}
          outcome={archiving.outcome}
          busy={busy}
          onCancel={() => setArchiving(null)}
          onConfirm={() => void writeArchive()}
        />
      ) : null}
      <AppToast toast={toast} onDismiss={dismiss} />
    </div>
  );
}
