import { Button, Checkbox, Code, Dialog, Select, Spinner } from "@radix-ui/themes";
import { ArrowRight, FilePen } from "lucide-react";
import { useEffect, useId, useMemo, useState } from "react";
import type { BankTitle } from "../../api/bankTitles";
import { apiPostJson } from "../../api/client";
import { TITLES_SEND_DEADLINE_MS } from "../../api/sendDeadline";
import {
  DEFAULT_CHOICE,
  MAX_RENAMES,
  RENAME_MODELS,
  mergeAnswers,
  parseChoice,
  previewSummary,
  renameCounts,
  renameLabel,
  sentence,
  splitPath,
  type RenameAnswer,
  type RenameChoice,
  type RenameModel,
  type RenameTitle,
} from "../../api/titleRenames";
import { messageOf } from "./TitleEditing";

/** Le dernier modèle choisi, gardé par le navigateur : « Renommer ainsi » le reprend. */
const CHOICE_KEY = "app-banque-renommage";

export type RenameResult = { titles: RenameTitle[]; entries: number[] };

export function readChoice(): RenameChoice {
  try {
    return parseChoice(window.localStorage.getItem(CHOICE_KEY));
  } catch {
    return DEFAULT_CHOICE;
  }
}

function keepChoice(choice: RenameChoice): void {
  try {
    window.localStorage.setItem(CHOICE_KEY, JSON.stringify(choice));
  } catch {
    // Le navigateur ne garde rien : le modèle par défaut reviendra.
  }
}

/** Renomme un lot d'après sa fiche, ou l'essaie : le nom de chaque titre, ou pourquoi il garde le sien. */
export function renameTitles(ids: number[], choice: RenameChoice, dryRun: boolean): Promise<RenameAnswer> {
  return apiPostJson<RenameAnswer>(
    "/media/titles/rename.json",
    { ids, model: choice.model, by_artist: choice.byArtist, dry_run: dryRun },
    TITLES_SEND_DEADLINE_MS,
  );
}

/** Tout le lot : le moteur s'arrête au bout de 20 s, et dit ce qui reste à renommer. */
export async function renameAll(ids: number[], choice: RenameChoice): Promise<RenameResult> {
  const answers: RenameAnswer[] = [];
  let queue = ids;
  while (queue.length) {
    const answer = await renameTitles(queue, choice, false);
    answers.push(answer);
    if (!answer.left.length || answer.left.length >= queue.length) break;
    queue = answer.left;
  }
  return mergeAnswers(answers);
}

/** Le nom visé, avec le dossier quand il change : celui de l'artiste. */
function targetName(item: RenameTitle): string {
  if (!item.to) return "";
  const before = splitPath(item.path);
  const after = splitPath(item.to);
  if (after.folder === before.folder) return after.name;
  return `${after.folder.split("/").pop()}/${after.name}`;
}

function RenamePreview({ titles }: { titles: RenameTitle[] }) {
  return (
    <ul className="banque-rename-list" aria-label="Aperçu des noms">
      {titles.map((item) => (
        <li key={item.id} className={`banque-rename-row is-${item.state}`}>
          <span className="banque-rename-from" title={item.path}>
            {splitPath(item.path).name || item.label}
          </span>
          {item.state === "rename" ? (
            <span className="banque-rename-to">
              <ArrowRight size={13} aria-label="devient" />
              <span title={item.to ?? ""}>{targetName(item)}</span>
            </span>
          ) : (
            <span className="banque-rename-why">{sentence(item.reason)}</span>
          )}
        </li>
      ))}
    </ul>
  );
}

export function RenameTitlesDialog({
  titles,
  onClose,
  onDone,
}: {
  titles: BankTitle[];
  onClose: () => void;
  onDone: (result: RenameResult) => void;
}) {
  const base = useId();
  const [choice, setChoice] = useState<RenameChoice>(readChoice);
  const [preview, setPreview] = useState<RenameTitle[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState("");
  const ids = useMemo(() => titles.map((title) => title.id), [titles]);
  const tooMany = ids.length > MAX_RENAMES;
  const what = titles.length === 1 ? "1 fichier" : `${titles.length} fichiers`;

  useEffect(() => {
    if (tooMany) return;
    let live = true;
    setPreview(null);
    setFailure("");
    renameTitles(ids, choice, true)
      .then((answer) => {
        if (live) setPreview(answer.titles);
      })
      .catch((caught) => {
        if (live) setFailure(messageOf(caught, "L'aperçu des noms n'a pas abouti. Réessaie."));
      });
    return () => {
      live = false;
    };
  }, [ids, choice, tooMany]);

  const counts = preview ? renameCounts(preview) : null;

  const run = async () => {
    setBusy(true);
    setFailure("");
    keepChoice(choice);
    try {
      onDone(await renameAll(ids, choice));
    } catch (caught) {
      setFailure(messageOf(caught, "Les fichiers n'ont pas été renommés. Réessaie."));
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
      <Dialog.Content maxWidth="38rem">
        <Dialog.Title>Renommer {what}</Dialog.Title>
        <Dialog.Description size="2" color="gray" mb="3">
          Chaque fichier prend le nom que lui donne sa fiche. Un nom déjà pris n'est jamais remplacé, et chaque titre
          garde sa fiche, son volume et sa place dans les bacs et dans l'Agenda.
        </Dialog.Description>
        <div className="banque-rename-choice">
          <div className="ui-field">
            <label className="ui-field-label" htmlFor={`${base}-model`}>
              Modèle
            </label>
            <Select.Root
              value={choice.model}
              disabled={busy}
              onValueChange={(model) => setChoice((before) => ({ ...before, model: model as RenameModel }))}
            >
              <Select.Trigger id={`${base}-model`} className="ui-field-control" />
              <Select.Content variant="soft" position="popper">
                {RENAME_MODELS.map((model) => (
                  <Select.Item key={model.value} value={model.value}>
                    {model.label}
                  </Select.Item>
                ))}
              </Select.Content>
            </Select.Root>
          </div>
          <label className="banque-rename-artist">
            <Checkbox
              size="2"
              checked={choice.byArtist}
              disabled={busy}
              onCheckedChange={(state) => setChoice((before) => ({ ...before, byArtist: state === true }))}
            />
            <span>Un dossier par artiste, dans sa collection</span>
          </label>
        </div>
        {tooMany ? (
          <p className="bacs-dialog-error" role="alert">
            Un lot prend {MAX_RENAMES} titres au plus : sélectionnes-en {ids.length - MAX_RENAMES} de moins.
          </p>
        ) : null}
        {preview ? (
          <>
            <p className="bacs-dialog-note" aria-live="polite">
              {previewSummary(preview)}
            </p>
            <RenamePreview titles={preview} />
          </>
        ) : !tooMany && !failure ? (
          <p className="bacs-dialog-note" aria-live="polite">
            <Spinner size="1" /> Aperçu des noms…
          </p>
        ) : null}
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
          <Button size="2" highContrast disabled={busy || tooMany || !counts?.rename} onClick={() => void run()}>
            {renameLabel(counts?.rename ?? 0)}
          </Button>
        </div>
      </Dialog.Content>
    </Dialog.Root>
  );
}

/**
 * Dans la fiche d'un titre : le nom que sa fiche lui donnerait, d'après le
 * dernier modèle choisi, quand son fichier ne le porte pas déjà.
 */
export function SheetRename({ title, onRenamed }: { title: BankTitle; onRenamed: (result: RenameResult) => void }) {
  const [proposal, setProposal] = useState<RenameTitle | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState("");

  useEffect(() => {
    let live = true;
    setProposal(null);
    setFailure("");
    // Le titre garde son dossier : « Renommer ainsi » ne change que le nom.
    renameTitles([title.id], { ...readChoice(), byArtist: false }, true)
      .then((answer) => {
        if (live) setProposal(answer.titles[0] ?? null);
      })
      .catch(() => {
        // Une suggestion qui ne vient pas ne cache rien : le fichier garde son nom.
        if (live) setProposal(null);
      });
    return () => {
      live = false;
    };
  }, [title.id, title.path, title.title, title.artist, title.album]);

  if (!proposal || proposal.state !== "rename" || !proposal.to) return null;
  const name = splitPath(proposal.to).name;

  const run = async () => {
    setBusy(true);
    setFailure("");
    try {
      onRenamed(await renameAll([title.id], { ...readChoice(), byArtist: false }));
    } catch (caught) {
      setFailure(messageOf(caught, "Le fichier n'a pas été renommé. Réessaie."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="bacs-inspector-group banque-sheet-rename" aria-label="Nom du fichier">
      <p>
        Le nom du fichier ne suit pas sa fiche. D'après elle : <Code>{name}</Code>
      </p>
      <Button size="2" variant="soft" color="gray" disabled={busy} onClick={() => void run()}>
        {busy ? <Spinner size="1" /> : <FilePen className="ui-button-icon" />}
        Renommer ainsi
      </Button>
      {failure ? (
        <p className="bacs-dialog-error" role="alert">
          {failure}
        </p>
      ) : null}
    </section>
  );
}
