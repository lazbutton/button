import { Button, Dialog, RadioCards, Spinner } from "@radix-ui/themes";
import { CircleCheck, FilePen, FileSearch, PenLine, RefreshCw, Table2, Tags, Wand } from "lucide-react";
import { type ReactNode, useCallback, useEffect, useId, useMemo, useState } from "react";
import { useAccount } from "../../api/AccountContext";
import {
  archiveAction,
  archiveLot,
  type HealthAnswer,
  type HealthTitle,
  healthPath,
  lotOf,
  moreLine,
  plural,
  POLL_MS,
  type SpellingGroup,
  verdictLine,
} from "../../api/bankHealth";
import {
  clearLine,
  copiesLine,
  duplicateLabel,
  guessLine,
  numberedAction,
  numberedLot,
  numberedSplit,
  renameLine,
  REVIEW_COUNT_PATH,
  SHOWN,
  spellingAction,
  spellingLot,
  spellingsLine,
  TABLE_BY_ARTIST,
  TABLE_BY_TITLE,
  TABLE_WITHOUT_ARTIST,
  tableOfDuplicate,
  type Task,
  tasksOf,
} from "../../api/bankTasks";
import { ApiRequestError, apiGet } from "../../api/client";
import { type EditLot, type EditOutcome, savedMessage, undoneMessage, withoutTitles } from "../../api/titleEdits";
import { renamedMessage, unrenamedMessage } from "../../api/titleRenames";
import { formatWhen } from "../../api/updates";
import { AppToast, useAppToast } from "../../ui/AppToast";
import { ErrorState, LoadingState } from "../../ui/DataState";
import { EmptyState } from "../../ui/EmptyState";
import { ConfirmLotDialog, editTitles, messageOf, needsConfirmation, TryReport, undoTitles } from "./TitleEditing";
import { readChoice, RenameTitlesDialog, type RenameResult } from "./TitleRenaming";

/** Ce que la vue « À ranger » lit, et que son onglet compte. */
export type BankTasksData = {
  /** Le compte de la santé de la banque, ou null avant lui, ou sans lui. */
  answer: HealthAnswer | null;
  /** Les titres que la recherche en ligne propose de corriger, ou null quand le moteur ne le dit pas. */
  review: number | null;
  problem: string;
  reviewProblem: string;
  /** Un moteur d'avant la santé de la banque. */
  outdated: boolean;
  /** La première lecture est faite. */
  read: boolean;
  /** Le compte de la santé de la banque n'est pas coupé (`features.bank_health`). */
  counted: boolean;
  tasks: Task[];
  load: (refresh?: boolean) => Promise<void>;
};

/**
 * Lit la santé de la banque (FON-72) et le nombre de fiches à relire (FON-26),
 * pour la vue « À ranger » et le nombre de son onglet. Le moteur compte à part :
 * tant qu'il compte, la lecture se refait.
 */
export function useBankTasks(enabled: boolean, healthOn: boolean): BankTasksData {
  // Le modèle de nom que la personne a choisi en dernier, dans la fenêtre « Renommer ».
  const [model] = useState(() => readChoice().model);
  const [answer, setAnswer] = useState<HealthAnswer | null>(null);
  const [review, setReview] = useState<number | null>(null);
  const [problem, setProblem] = useState("");
  const [reviewProblem, setReviewProblem] = useState("");
  const [outdated, setOutdated] = useState(false);
  const [read, setRead] = useState(false);

  const loadHealth = useCallback(
    async (refresh = false) => {
      if (!enabled || !healthOn) return;
      setProblem("");
      try {
        setAnswer(await apiGet<HealthAnswer>(healthPath(model, refresh)));
        setOutdated(false);
      } catch (caught) {
        if (caught instanceof ApiRequestError && caught.status === 404) setOutdated(true);
        else setProblem(messageOf(caught, "Le compte de la banque ne s'est pas lu. Réessaie."));
      }
    },
    [enabled, healthOn, model],
  );

  const loadReview = useCallback(async () => {
    if (!enabled) return;
    setReviewProblem("");
    try {
      const page = await apiGet<{ total?: number }>(REVIEW_COUNT_PATH);
      setReview(typeof page.total === "number" ? page.total : null);
    } catch (caught) {
      setReview(null);
      // Un moteur sans les fiches, ou le rangement coupé : pas de relecture.
      if (caught instanceof ApiRequestError && (caught.status === 404 || caught.status === 409)) return;
      setReviewProblem(messageOf(caught, "Les corrections trouvées en ligne ne se sont pas lues. Réessaie."));
    }
  }, [enabled]);

  const load = useCallback(
    async (refresh = false) => {
      await Promise.all([loadHealth(refresh), loadReview()]);
      setRead(true);
    },
    [loadHealth, loadReview],
  );

  useEffect(() => {
    void load();
  }, [load]);

  // Le compte tourne à part : la lecture se refait jusqu'à ce qu'il soit fait.
  useEffect(() => {
    if (!answer?.computing) return;
    const timer = window.setTimeout(() => void loadHealth(), POLL_MS);
    return () => window.clearTimeout(timer);
  }, [answer, loadHealth]);

  // Pendant le premier compte, rien ne se compte encore : une liste à moitié tromperait.
  const counting = Boolean(answer?.computing && !answer.health);
  const tasks = useMemo(
    () => (counting ? [] : tasksOf(answer?.health ?? null, review, model)),
    [counting, answer, review, model],
  );
  return { answer, review, problem, reviewProblem, outdated, read, counted: healthOn, tasks, load };
}

/** Une tâche : ce qui cloche, ce que ça change, puis le geste, à droite sur un grand écran. */
function TaskCard({ task, actions, children }: { task: Task; actions?: ReactNode; children?: ReactNode }) {
  return (
    <li className="banque-task">
      <h3>{task.title}</h3>
      <p className="banque-task-why">{task.why}</p>
      {actions ? <div className="banque-task-actions">{actions}</div> : null}
      {children}
    </li>
  );
}

function More({ count, shown, what }: { count: number; shown: number; what: [string, string] }) {
  const line = moreLine(count, shown, what);
  return line ? <p className="banque-task-more">{line}</p> : null;
}

/** Une graphie pour un artiste : la personne choisit la bonne, elle s'écrit sur chaque titre. */
function SpellingDialog({
  group,
  onClose,
  onDone,
}: {
  group: SpellingGroup;
  onClose: () => void;
  onDone: (outcome: EditOutcome) => void;
}) {
  const [chosen, setChosen] = useState(group.suggested);
  const [tried, setTried] = useState<EditOutcome | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState("");
  const lot = useMemo(() => spellingLot(group, chosen), [group, chosen]);
  const refused = tried?.refused.map((issue) => issue.id) ?? [];
  const left = lot.titles.length - refused.length;

  const write = async () => {
    setBusy(true);
    setFailure("");
    try {
      // Un essai d'abord : un titre changé depuis, ou à l'antenne, se dit avant d'écrire.
      if (!tried) {
        const outcome = await editTitles(lot, true);
        if (needsConfirmation(outcome)) {
          setTried(outcome);
          setBusy(false);
          return;
        }
      }
      onDone(await editTitles(withoutTitles(lot, refused), false));
    } catch (caught) {
      setTried(null);
      setFailure(messageOf(caught, "L'artiste ne s'est pas écrit. Réessaie."));
      setBusy(false);
    }
  };

  const label = refused.length
    ? `Continuer sans ${refused.length === 1 ? "ce titre" : "ces titres"}`
    : tried
      ? spellingAction(chosen, tried.written + tried.waiting.length)
      : spellingAction(chosen, lot.titles.length);

  return (
    <Dialog.Root
      open
      onOpenChange={(open) => {
        if (!open && !busy) onClose();
      }}
    >
      <Dialog.Content maxWidth="30rem">
        <Dialog.Title>Écrire cet artiste d'une seule façon</Dialog.Title>
        <Dialog.Description size="2" color="gray" mb="3">
          Choisis la bonne graphie : elle s'écrit dans le fichier de chaque titre, puis dans la bibliothèque. « Revenir »
          la défait.
        </Dialog.Description>
        <RadioCards.Root
          size="1"
          columns="1"
          value={chosen}
          aria-label="La bonne graphie"
          onValueChange={(value) => {
            setChosen(value);
            setTried(null);
            setFailure("");
          }}
        >
          {group.spellings.map((spelling) => (
            <RadioCards.Item key={spelling.value} value={spelling.value} className="banque-spelling">
              <span className="banque-spelling-value">{spelling.value}</span>{" "}
              <span className="banque-spelling-count">{plural(spelling.count, "titre", "titres")}</span>
            </RadioCards.Item>
          ))}
        </RadioCards.Root>
        {tried ? <TryReport outcome={tried} /> : null}
        {failure ? (
          <p className="bacs-dialog-error" role="alert">
            {failure}
          </p>
        ) : null}
        <div className="bacs-dialog-actions">
          {busy ? <Spinner size="2" /> : null}
          <Dialog.Close>
            <Button type="button" size="2" variant="soft" color="gray" disabled={busy}>
              Annuler
            </Button>
          </Dialog.Close>
          <Button size="2" highContrast disabled={busy || left <= 0} onClick={() => void write()}>
            {label}
          </Button>
        </div>
      </Dialog.Content>
    </Dialog.Root>
  );
}

/**
 * Sons → Banque → À ranger (FON-92) : ce qui attend une personne dans la
 * banque, une tâche par chose à faire, chacune avec le geste qui la fait. Ce
 * qui va bien ne se montre pas, et le nom des fichiers vient à la fin,
 * facultatif. Remplace les vues Arrivées et Santé ; « Relire » ouvre les
 * fiches que la recherche en ligne propose.
 */
export function BankTasksView({
  data,
  onOpenTable,
  onReview,
}: {
  data: BankTasksData;
  onOpenTable: (table: Record<string, string>) => void;
  onReview: () => void;
}) {
  const { isAdmin, account } = useAccount();
  const programmer = isAdmin || account?.permissions.autodj === true;
  const canEdit = account?.features?.title_edits === true && programmer;
  const canRename = account?.features?.title_renames === true && programmer;
  const optionalHeading = useId();
  const [spelling, setSpelling] = useState<SpellingGroup | null>(null);
  const [confirming, setConfirming] = useState<{ question: string; lot: EditLot; outcome: EditOutcome } | null>(null);
  const [renaming, setRenaming] = useState<HealthTitle[] | null>(null);
  const [busy, setBusy] = useState(false);
  const { toast, show, dismiss } = useAppToast();
  const { answer, load } = data;

  // Revenue sur la vue, après le tableau ou la relecture, la banque a pu changer : elle se relit.
  useEffect(() => {
    if (data.read) void load();
    // Une fois, à l'ouverture de la vue.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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

  // Un essai d'abord, qui dit ce qui changera ; puis la confirmation écrit.
  const tryLot = async (lot: EditLot, question: string) => {
    setBusy(true);
    try {
      setConfirming({ question, lot, outcome: await editTitles(lot, true) });
    } catch (caught) {
      show(messageOf(caught, "L'essai n'a pas abouti. Réessaie."), "error");
    } finally {
      setBusy(false);
    }
  };

  const writeLot = async () => {
    if (!confirming) return;
    const refused = confirming.outcome.refused.map((issue) => issue.id);
    setBusy(true);
    try {
      const outcome = await editTitles(withoutTitles(confirming.lot, refused), false);
      setConfirming(null);
      await afterEdit(outcome);
    } catch (caught) {
      setConfirming(null);
      show(messageOf(caught, "Les fiches n'ont pas été modifiées. Réessaie."), "error");
    } finally {
      setBusy(false);
    }
  };

  if (!data.read) return <LoadingState label="Lecture de la banque…" />;
  const health = answer?.health ?? null;
  if (!health && answer?.computing) return <LoadingState label="Premier compte de la banque…" />;
  if (!health && !data.review) {
    if (data.outdated)
      return (
        <ErrorState
          title="À ranger indisponible"
          description="Cette vue demande un moteur plus récent. Mets à jour le moteur."
          onRetry={() => void load()}
        />
      );
    if (data.problem)
      return <ErrorState title="Banque illisible" description={data.problem} onRetry={() => void load()} />;
  }

  const todo = data.tasks.filter((task) => !task.optional);
  const optional = data.tasks.filter((task) => task.optional);
  const clear = health ? clearLine(health) : null;
  const verdict = health ? verdictLine(health.figures) : null;
  const problems = [data.problem, answer?.error ?? "", data.reviewProblem].filter(Boolean);

  const card = (task: Task): ReactNode => {
    if (task.key === "review")
      return (
        <TaskCard
          key={task.key}
          task={task}
          actions={
            <Button size="2" highContrast onClick={onReview}>
              <FileSearch className="ui-button-icon" />
              Relire
            </Button>
          }
        />
      );
    if (!health) return null;
    switch (task.key) {
      case "unindexed":
        return (
          <TaskCard key={task.key} task={task}>
            <ul className="banque-task-names">
              {health.unindexed.paths.slice(0, SHOWN).map((path) => (
                <li key={path}>{path}</li>
              ))}
            </ul>
            <More count={health.unindexed.count} shown={SHOWN} what={["fichier", "fichiers"]} />
          </TaskCard>
        );
      case "numbered": {
        const titles = health.numbered?.titles ?? [];
        const { guessed, bare } = numberedSplit(titles);
        const lot = numberedLot(titles);
        return (
          <TaskCard
            key={task.key}
            task={task}
            actions={
              canEdit && lot.titles.length ? (
                <Button
                  size="2"
                  highContrast
                  disabled={busy}
                  onClick={() =>
                    void tryLot(
                      lot,
                      `Corriger ${plural(lot.titles.length, "fiche", "fiches")} d'après le nom du fichier ?`,
                    )
                  }
                >
                  <Wand className="ui-button-icon" />
                  {numberedAction(lot.titles.length)}
                </Button>
              ) : null
            }
          >
            {guessed.length ? (
              <>
                <p className="banque-task-why">Le nom du fichier donne l'artiste et le titre :</p>
                <ul className="banque-task-names">
                  {guessed.slice(0, SHOWN).map((title) => (
                    <li key={title.id}>{guessLine(title)}</li>
                  ))}
                </ul>
                <More count={guessed.length} shown={SHOWN} what={["titre", "titres"]} />
              </>
            ) : null}
            {bare.length ? (
              <div className="banque-task-row">
                <p className="banque-task-why">
                  {bare.length === 1
                    ? "Le nom d'un fichier n'en dit pas plus : corrige sa fiche dans le tableau."
                    : `Le nom de ${bare.length} fichiers n'en dit pas plus : corrige leur fiche dans le tableau.`}
                </p>
                <Button size="2" variant="soft" color="gray" onClick={() => onOpenTable(TABLE_BY_ARTIST)}>
                  <Table2 className="ui-button-icon" />
                  Voir dans le tableau
                </Button>
              </div>
            ) : null}
          </TaskCard>
        );
      }
      case "artist":
        return (
          <TaskCard
            key={task.key}
            task={task}
            actions={
              <Button size="2" variant="soft" color="gray" onClick={() => onOpenTable(TABLE_WITHOUT_ARTIST)}>
                <Table2 className="ui-button-icon" />
                Compléter dans le tableau
              </Button>
            }
          />
        );
      case "title":
        return (
          <TaskCard
            key={task.key}
            task={task}
            actions={
              <Button size="2" variant="soft" color="gray" onClick={() => onOpenTable(TABLE_BY_TITLE)}>
                <Table2 className="ui-button-icon" />
                Voir dans le tableau
              </Button>
            }
          />
        );
      case "spellings":
        return (
          <TaskCard key={task.key} task={task}>
            <ul className="banque-task-rows">
              {health.spellings.groups.slice(0, SHOWN).map((group) => (
                <li key={group.key}>
                  <div>
                    <strong>« {group.suggested} »</strong>
                    <span>{spellingsLine(group)}</span>
                  </div>
                  {canEdit ? (
                    <Button size="2" variant="soft" color="gray" disabled={busy} onClick={() => setSpelling(group)}>
                      <PenLine className="ui-button-icon" />
                      Unifier<span className="ui-visually-hidden"> « {group.suggested} »</span>
                    </Button>
                  ) : null}
                </li>
              ))}
            </ul>
            <More count={health.spellings.count} shown={SHOWN} what={["artiste", "artistes"]} />
          </TaskCard>
        );
      case "duplicates":
        return (
          <TaskCard key={task.key} task={task}>
            <ul className="banque-task-rows">
              {health.duplicates.groups.slice(0, SHOWN).map((group) => (
                <li key={group.titles.map((title) => title.id).join("-")}>
                  <div>
                    <strong>{duplicateLabel(group)}</strong>
                    <span>{copiesLine(group)}</span>
                  </div>
                  <Button size="2" variant="soft" color="gray" onClick={() => onOpenTable(tableOfDuplicate(group))}>
                    <Table2 className="ui-button-icon" />
                    Voir dans le tableau<span className="ui-visually-hidden"> {duplicateLabel(group)}</span>
                  </Button>
                </li>
              ))}
            </ul>
            <More count={health.duplicates.count} shown={SHOWN} what={["titre", "titres"]} />
          </TaskCard>
        );
      case "archive":
        return (
          <TaskCard
            key={task.key}
            task={task}
            actions={
              canEdit ? (
                <Button
                  size="2"
                  variant="soft"
                  color="gray"
                  disabled={busy}
                  onClick={() =>
                    void tryLot(archiveLot(health.archive.titles), `${archiveAction(health.archive.count)} ?`)
                  }
                >
                  <Tags className="ui-button-icon" />
                  {archiveAction(health.archive.count)}
                </Button>
              ) : null
            }
          />
        );
      case "names":
        return (
          <TaskCard
            key={task.key}
            task={task}
            actions={
              canRename ? (
                <Button
                  size="2"
                  variant="soft"
                  color="gray"
                  disabled={busy}
                  onClick={() => setRenaming(lotOf(health.misnamed.titles).taken)}
                >
                  <FilePen className="ui-button-icon" />
                  Renommer…
                </Button>
              ) : null
            }
          >
            <ul className="banque-task-names" aria-label="Par exemple">
              {health.misnamed.titles.slice(0, 3).map((title) => (
                <li key={title.id}>{renameLine(title)}</li>
              ))}
            </ul>
          </TaskCard>
        );
      default:
        return null;
    }
  };

  return (
    <div className="banque-tasks">
      <header className="banque-tasks-head">
        <div>
          <h2>À ranger</h2>
          <p className="banque-tasks-intro">
            Les titres envoyés passent déjà à l'antenne. Voici ce qui reste à faire dans la banque.
          </p>
        </div>
        {answer ? (
          <div className="banque-tasks-when">
            <span aria-live="polite">
              {answer.computing ? (
                <>
                  <Spinner size="1" /> Vérification en cours…
                </>
              ) : answer.computed_at ? (
                `Vérifié ${formatWhen(answer.computed_at)}.`
              ) : null}
            </span>
            <Button size="1" variant="soft" color="gray" disabled={answer.computing} onClick={() => void load(true)}>
              <RefreshCw className="ui-button-icon" />
              Vérifier de nouveau
            </Button>
          </div>
        ) : null}
      </header>

      {problems.map((text) => (
        <p key={text} className="banque-tasks-problem" role="alert">
          {text}
        </p>
      ))}

      {todo.length ? (
        <ul className="banque-task-list" aria-label="À faire">
          {todo.map(card)}
        </ul>
      ) : (
        <EmptyState
          icon={CircleCheck}
          title="Rien à ranger"
          description={
            data.counted
              ? "La banque est en ordre."
              : "Le compte de la banque est coupé sur cette station : seules les corrections trouvées en ligne se montrent ici."
          }
        />
      )}

      {optional.length ? (
        <section className="banque-tasks-optional" aria-labelledby={optionalHeading}>
          <h3 id={optionalHeading}>Facultatif</h3>
          <ul className="banque-task-list">{optional.map(card)}</ul>
        </section>
      ) : null}

      {health ? (
        <div className="banque-tasks-foot">
          {clear ? (
            <p>
              <CircleCheck size={14} aria-hidden="true" /> {clear}
            </p>
          ) : null}
          <p>{plural(health.figures.titles, "titre dans la banque.", "titres dans la banque.")}</p>
          {/* FON-80 : seulement le verdict allumé ; éteint, le moteur n'en dit rien. */}
          {verdict ? <p>Femme ou minorité de genre : {verdict}</p> : null}
        </div>
      ) : null}

      {spelling ? (
        <SpellingDialog
          group={spelling}
          onClose={() => setSpelling(null)}
          onDone={(outcome) => {
            setSpelling(null);
            void afterEdit(outcome);
          }}
        />
      ) : null}
      {confirming ? (
        <ConfirmLotDialog
          question={confirming.question}
          outcome={confirming.outcome}
          busy={busy}
          onCancel={() => setConfirming(null)}
          onConfirm={() => void writeLot()}
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
      <AppToast toast={toast} onDismiss={dismiss} />
    </div>
  );
}
