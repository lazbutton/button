import { Button, Checkbox, Dialog, Select, Spinner, TextField } from "@radix-ui/themes";
import { useId, useMemo, useState } from "react";
import { titlesLabel } from "../../api/bankContent";
import type { BankTitle, FicheField } from "../../api/bankTitles";
import { apiPostJson } from "../../api/client";
import { TITLES_SEND_DEADLINE_MS } from "../../api/sendDeadline";
import {
  EDIT_FIELDS,
  EDIT_LABELS,
  FAMILIES,
  MAX_LOT,
  batchLot,
  issueLines,
  selectionLines,
  withoutTitles,
  yearProblem,
  type EditLot,
  type EditOutcome,
  type FicheForm,
} from "../../api/titleEdits";

/** Écrit un lot de fiches, ou l'essaie : ce qui changerait, ce qui attendrait, les sélections touchées. */
export function editTitles(lot: EditLot, dryRun: boolean): Promise<EditOutcome> {
  return apiPostJson<EditOutcome>("/media/titles/edit.json", { ...lot, dry_run: dryRun }, TITLES_SEND_DEADLINE_MS);
}

/** « Revenir » : les valeurs d'avant d'un lot, sauf celles changées depuis. */
export function undoTitles(entry: number): Promise<EditOutcome> {
  return apiPostJson<EditOutcome>(`/media/journal/${entry}/undo.json`, {}, TITLES_SEND_DEADLINE_MS);
}

export function messageOf(caught: unknown, fallback: string): string {
  return caught instanceof Error && caught.message ? caught.message : fallback;
}

// Radix ne prend pas une valeur vide pour un choix de liste.
const NO_FAMILY = "aucune";

/** Un champ de la fiche : du texte, ou la liste des familles. */
export function FicheInput({
  field,
  value,
  disabled,
  invalid,
  id,
  label,
  autoFocus,
  onChange,
}: {
  field: FicheField;
  value: string;
  disabled?: boolean;
  invalid?: boolean;
  id: string;
  /** Le nom du champ, quand l'étiquette visible ne le porte pas seule. */
  label?: string;
  autoFocus?: boolean;
  onChange: (value: string) => void;
}) {
  if (field === "famille") {
    return (
      <Select.Root value={value || NO_FAMILY} disabled={disabled} onValueChange={(next) => onChange(next === NO_FAMILY ? "" : next)}>
        <Select.Trigger id={id} className="ui-field-control" aria-label={label} />
        <Select.Content variant="soft" position="popper">
          <Select.Item value={NO_FAMILY}>Aucune</Select.Item>
          {FAMILIES.map((family) => (
            <Select.Item key={family.name} value={family.name}>
              {family.label}
            </Select.Item>
          ))}
        </Select.Content>
      </Select.Root>
    );
  }
  return (
    <TextField.Root
      id={id}
      size="2"
      className="ui-field-control"
      value={value}
      disabled={disabled}
      aria-label={label}
      autoFocus={autoFocus}
      aria-invalid={invalid || undefined}
      inputMode={field === "year" ? "numeric" : undefined}
      maxLength={field === "year" ? 4 : 1000}
      placeholder={field === "year" ? "2019" : undefined}
      onChange={(event) => onChange(event.target.value)}
    />
  );
}

/** Ce que l'essai dit d'un lot, ou d'une seule fiche (`single`), avant de l'écrire. */
export function TryReport({ outcome, single = false }: { outcome: EditOutcome; single?: boolean }) {
  const selections = selectionLines(outcome.selections);
  const changing = outcome.written;
  return (
    <div className="banque-try" role="status" aria-live="polite">
      {single && outcome.refused.length ? (
        <div className="banque-try-block is-danger">
          <strong>Cette fiche ne peut pas s'écrire.</strong> {outcome.refused[0].reason}
        </div>
      ) : outcome.refused.length ? (
        <div className="banque-try-block is-danger">
          <strong>
            {outcome.refused.length === 1
              ? "Un titre ne peut pas s'écrire : rien ne s'écrira tant qu'il est dans le lot."
              : `${outcome.refused.length} titres ne peuvent pas s'écrire : rien ne s'écrira tant qu'ils sont dans le lot.`}
          </strong>
          <ul>
            {issueLines(outcome.refused).map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </div>
      ) : null}
      {single ? null : (
        <p className="banque-try-count">
        {changing
          ? `${changing === 1 ? "1 fiche change" : `${changing} fiches changent`}${
              outcome.unchanged ? `, ${outcome.unchanged} ${outcome.unchanged === 1 ? "a" : "ont"} déjà ces valeurs` : ""
            }.`
          : "Aucune fiche ne change : ces titres ont déjà ces valeurs."}
        </p>
      )}
      {outcome.waiting.length ? (
        <div className="banque-try-block">
          <strong>
            {single
              ? "Ce titre est à l'antenne ou en file : sa fiche s'écrira quand il sera passé."
              : outcome.waiting.length === 1
              ? "Un titre est à l'antenne ou en file : sa fiche s'écrira quand il sera passé."
              : `${outcome.waiting.length} titres sont à l'antenne ou en file : leurs fiches s'écriront quand ils seront passés.`}
          </strong>
        </div>
      ) : null}
      {selections.length ? (
        <div className="banque-try-block is-warn">
          <strong>Des sélections de titres changent :</strong>
          <ul>
            {selections.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

/** Ce qu'un essai demande de voir avant d'écrire : un refus, une attente, une sélection touchée. */
export function needsConfirmation(outcome: EditOutcome): boolean {
  return outcome.refused.length > 0 || outcome.waiting.length > 0 || outcome.selections.length > 0;
}

/**
 * « Modifier N fiches » : un champ coché prend la même valeur pour tous les
 * titres, un champ décoché garde celle de chacun. Un essai d'abord, qui dit ce
 * qui changera, ce qui attendra et les sélections touchées ; puis l'écriture.
 */
export function EditTitlesDialog({
  titles,
  onClose,
  onDone,
  preset,
}: {
  titles: BankTitle[];
  onClose: () => void;
  onDone: (outcome: EditOutcome) => void;
  /** Fields checked and filled already: what titles dropped on a group take (FON-75). */
  preset?: Partial<Record<FicheField, string>>;
}) {
  const base = useId();
  const [checked, setChecked] = useState<Partial<Record<FicheField, boolean>>>(() =>
    Object.fromEntries(Object.keys(preset ?? {}).map((field) => [field, true])),
  );
  const [form, setForm] = useState<FicheForm>(() => ({
    title: "",
    artist: "",
    album: "",
    year: "",
    genre: "",
    famille: "",
    ...preset,
  }));
  const [dropped, setDropped] = useState<number[]>([]);
  const [tried, setTried] = useState<EditOutcome | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState("");

  const kept = useMemo(() => titles.filter((title) => !dropped.includes(title.id)), [titles, dropped]);
  const values = useMemo(() => {
    const out: Partial<FicheForm> = {};
    for (const field of EDIT_FIELDS) if (checked[field]) out[field] = form[field];
    return out;
  }, [checked, form]);
  const lot = useMemo(() => batchLot(kept, values), [kept, values]);
  const yearError = checked.year ? yearProblem(form.year) : "";
  const none = Object.keys(values).length === 0;
  const tooMany = kept.length > MAX_LOT;
  const what = titles.length === 1 ? "1 fiche" : `${titles.length} fiches`;

  const change = (update: () => void) => {
    update();
    setTried(null);
    setFailure("");
  };

  const check = async (next: EditLot = lot) => {
    setBusy(true);
    setFailure("");
    try {
      setTried(await editTitles(next, true));
    } catch (caught) {
      setFailure(messageOf(caught, "L'essai n'a pas abouti. Réessaie."));
    } finally {
      setBusy(false);
    }
  };

  const write = async () => {
    setBusy(true);
    setFailure("");
    try {
      onDone(await editTitles(lot, false));
    } catch (caught) {
      setTried(null);
      setFailure(messageOf(caught, "Les fiches n'ont pas été modifiées. Réessaie."));
      setBusy(false);
    }
  };

  const dropRefused = () => {
    if (!tried) return;
    const ids = tried.refused.map((issue) => issue.id);
    setDropped((before) => [...before, ...ids]);
    void check(withoutTitles(lot, ids));
  };

  const changing = tried ? tried.written + tried.waiting.length : 0;
  let primary: { label: string; disabled: boolean; run: () => void };
  if (!tried) primary = { label: "Vérifier", disabled: none || tooMany || Boolean(yearError), run: () => void check() };
  else if (tried.refused.length)
    primary = {
      label: `Continuer sans ${tried.refused.length === 1 ? "ce titre" : "ces titres"}`,
      disabled: tried.refused.length >= kept.length,
      run: dropRefused,
    };
  else
    primary = {
      label: changing === 1 ? "Modifier 1 fiche" : `Modifier ${changing} fiches`,
      disabled: changing === 0,
      run: () => void write(),
    };

  return (
    <Dialog.Root
      open
      onOpenChange={(open) => {
        if (!open && !busy) onClose();
      }}
    >
      <Dialog.Content maxWidth="34rem">
        <Dialog.Title>Modifier {what}</Dialog.Title>
        <Dialog.Description size="2" color="gray" mb="3">
          Un champ coché prend la même valeur pour {titles.length === 1 ? "ce titre" : `les ${titles.length} titres`}. Un
          champ décoché garde celle de chacun.
        </Dialog.Description>
        {tooMany ? (
          <p className="bacs-dialog-error" role="alert">
            Un lot prend {MAX_LOT} titres au plus : sélectionnes-en {kept.length - MAX_LOT} de moins.
          </p>
        ) : null}
        {dropped.length ? (
          <p className="bacs-dialog-note">
            {dropped.length === 1 ? "Un titre a été retiré du lot." : `${dropped.length} titres ont été retirés du lot.`}{" "}
            {titlesLabel(kept.length)} {kept.length === 1 ? "reste" : "restent"}.
          </p>
        ) : null}
        <div className="banque-edit-fields">
          {EDIT_FIELDS.map((field) => {
            const id = `${base}-${field}`;
            const on = Boolean(checked[field]);
            return (
              <div key={field} className={`banque-edit-row${on ? " is-on" : ""}`}>
                <label className="banque-edit-check">
                  <Checkbox
                    size="2"
                    checked={on}
                    disabled={busy}
                    onCheckedChange={(state) => change(() => setChecked((before) => ({ ...before, [field]: state === true })))}
                  />
                  <span>{EDIT_LABELS[field]}</span>
                </label>
                <FicheInput
                  field={field}
                  id={id}
                  label={`${EDIT_LABELS[field]}, pour tous les titres`}
                  value={form[field]}
                  disabled={!on || busy}
                  invalid={field === "year" && Boolean(yearError)}
                  onChange={(value) => change(() => setForm((before) => ({ ...before, [field]: value })))}
                />
                {field === "year" && yearError ? <span className="ui-field-error banque-edit-error">{yearError}</span> : null}
              </div>
            );
          })}
        </div>
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
          <Button size="2" highContrast disabled={busy || primary.disabled} onClick={primary.run}>
            {primary.label}
          </Button>
        </div>
      </Dialog.Content>
    </Dialog.Root>
  );
}

/**
 * Une écriture à confirmer : un collage sur une sélection (FON-67), ou une
 * cellule dont l'essai a quelque chose à dire.
 */
export function ConfirmLotDialog({
  question,
  outcome,
  busy,
  onCancel,
  onConfirm,
}: {
  question: string;
  outcome: EditOutcome;
  busy: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const changing = outcome.written + outcome.waiting.length;
  return (
    <Dialog.Root
      open
      onOpenChange={(open) => {
        if (!open && !busy) onCancel();
      }}
    >
      <Dialog.Content maxWidth="32rem">
        <Dialog.Title>{question}</Dialog.Title>
        <Dialog.Description size="2" color="gray" mb="2">
          Avant d'écrire, voici ce qui changera.
        </Dialog.Description>
        <TryReport outcome={outcome} />
        <div className="bacs-dialog-actions">
          {busy ? <Spinner size="2" /> : null}
          <Dialog.Close>
            <Button type="button" size="2" variant="soft" color="gray" disabled={busy}>
              Annuler
            </Button>
          </Dialog.Close>
          <Button size="2" highContrast disabled={busy || changing === 0 || outcome.refused.length > 0} onClick={onConfirm}>
            {changing === 1 ? "Écrire 1 fiche" : `Écrire ${changing} fiches`}
          </Button>
        </div>
      </Dialog.Content>
    </Dialog.Root>
  );
}
