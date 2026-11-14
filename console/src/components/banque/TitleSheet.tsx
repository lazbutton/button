import { Badge, Button, IconButton, Spinner } from "@radix-ui/themes";
import { Pencil, Play, Square, X } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import { cell, ficheState, type BankTitle } from "../../api/bankTitles";
import { formatClock } from "../../api/soundsView";
import {
  EDIT_FIELDS,
  EDIT_LABELS,
  formOf,
  sheetLot,
  titleName,
  yearProblem,
  type EditOutcome,
  type FicheForm,
} from "../../api/titleEdits";
import { FicheInput, TryReport, editTitles, messageOf, needsConfirmation } from "./TitleEditing";
import { TitlePlaysSection } from "./TitlePlays";

/**
 * The fiche of a title, in a panel to the right of the table: what Beets knows
 * of it. A drawer over the table on a narrow screen. With the right to correct
 * it (FON-66), it turns into a form: a try first, then the writing.
 */
export function TitleSheet({
  title,
  collection,
  playing,
  canEdit = false,
  startEditing = false,
  onPlay,
  onClose,
  onSaved,
}: {
  title: BankTitle;
  /** The name of its collection, as the left column says it. */
  collection: string;
  playing: boolean;
  /** The fiche can be corrected: the bank's tidying open, and the Programmateur's right. */
  canEdit?: boolean;
  /** Opens straight into the form, from the row's menu. */
  startEditing?: boolean;
  onPlay: () => void;
  onClose: () => void;
  onSaved?: (outcome: EditOutcome, name: string) => void;
}) {
  const headRef = useRef<HTMLHeadingElement>(null);
  const base = useId();
  const fiche = ficheState(title.missing);
  const [form, setForm] = useState<FicheForm | null>(null);
  const [tried, setTried] = useState<EditOutcome | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState("");
  const name = titleName(title);

  // A fiche opened takes the focus, so a screen reader reads it and Escape closes it.
  useEffect(() => {
    const editing = startEditing && canEdit;
    // Ouverte pour la corriger, le premier champ prend le focus.
    if (!editing) headRef.current?.focus();
    setForm(editing ? formOf(title) : null);
    setTried(null);
    setFailure("");
    // Une autre fiche ouverte repart de zéro ; une relecture du tableau ne touche pas au formulaire.
  }, [title.id, startEditing]);

  const rows: Array<[string, string]> = [
    ["Artiste", cell(title.artist)],
    ["Album", cell(title.album)],
    ["Année", cell(title.year)],
    ["Genre", cell(title.genre)],
    ["Famille", cell(title.famille_label)],
    // FON-74 : les étiquettes de la station, qu'un moteur plus ancien ne donne pas.
    ...(title.etiquettes ? ([["Étiquettes", cell(title.etiquettes.join(", "))]] as Array<[string, string]>) : []),
    ["Durée", title.duration ? formatClock(title.duration) : "—"],
    ["Collection", cell(collection)],
  ];

  const yearError = form ? yearProblem(form.year) : "";
  const lot = form ? sheetLot(title, form) : null;

  // Le formulaire fermé, le focus revient en tête de la fiche : Échap la ferme ensuite.
  const stop = () => {
    setForm(null);
    setTried(null);
    setFailure("");
    requestAnimationFrame(() => headRef.current?.focus());
  };

  const write = async () => {
    if (!lot) return;
    setBusy(true);
    setFailure("");
    try {
      const outcome = await editTitles(lot, false);
      stop();
      onSaved?.(outcome, name);
    } catch (caught) {
      setTried(null);
      setFailure(messageOf(caught, "La fiche n'a pas été corrigée. Réessaie."));
    } finally {
      setBusy(false);
    }
  };

  // Enregistrer : l'essai d'abord. Rien à signaler, la fiche s'écrit tout de suite ;
  // sinon l'essai se montre, et une seconde demande écrit.
  const save = async () => {
    if (!form || yearError || busy) return;
    if (!lot) {
      stop();
      return;
    }
    if (tried && !tried.refused.length) {
      await write();
      return;
    }
    setBusy(true);
    setFailure("");
    let outcome: EditOutcome;
    try {
      outcome = await editTitles(lot, true);
    } catch (caught) {
      setFailure(messageOf(caught, "La fiche n'a pas été corrigée. Réessaie."));
      setBusy(false);
      return;
    }
    setBusy(false);
    if (needsConfirmation(outcome)) setTried(outcome);
    else await write();
  };

  return (
    <aside
      className="bacs-inspector banque-sheet"
      aria-label={`Fiche de ${name}`}
      onKeyDown={(event) => {
        if (event.key === "Escape") {
          event.stopPropagation();
          if (form && !busy) stop();
          else if (!form) onClose();
        }
      }}
    >
      <header className="bacs-inspector-head">
        <h2 ref={headRef} tabIndex={-1} className="banque-sheet-title">
          {form ? "Corriger la fiche" : "Fiche du titre"}
        </h2>
        <span className="bacs-spacer" />
        <IconButton size="1" variant="ghost" color="gray" aria-label="Fermer la fiche" disabled={busy} onClick={onClose}>
          <X size={16} />
        </IconButton>
      </header>
      <div className="bacs-inspector-body">
        <div className="banque-sheet-name">
          <strong>{name}</strong>
          {title.artist ? <span>{title.artist}</span> : null}
        </div>
        <div className="banque-sheet-actions">
          <Button size="2" variant="soft" color="gray" onClick={onPlay}>
            {playing ? <Square className="ui-button-icon" /> : <Play className="ui-button-icon" />}
            {playing ? "Arrêter la pré-écoute" : "Pré-écouter"}
          </Button>
          {canEdit && !form ? (
            <Button size="2" variant="soft" color="gray" onClick={() => setForm(formOf(title))}>
              <Pencil className="ui-button-icon" />
              Corriger la fiche
            </Button>
          ) : null}
        </div>
        {form ? (
          <form
            className="bacs-inspector-group banque-sheet-form"
            aria-label="Corriger la fiche"
            onSubmit={(event) => {
              event.preventDefault();
              void save();
            }}
          >
            {EDIT_FIELDS.map((field) => {
              const id = `${base}-${field}`;
              const error = field === "year" ? yearError : "";
              return (
                <div key={field} className="ui-field">
                  <label className="ui-field-label" htmlFor={id}>
                    {EDIT_LABELS[field]}
                  </label>
                  <FicheInput
                    field={field}
                    id={id}
                    value={form[field]}
                    disabled={busy}
                    autoFocus={field === EDIT_FIELDS[0]}
                    invalid={Boolean(error)}
                    label={field === "famille" ? EDIT_LABELS[field] : undefined}
                    onChange={(value) => {
                      setForm((before) => (before ? { ...before, [field]: value } : before));
                      setTried(null);
                    }}
                  />
                  {error ? <span className="ui-field-error">{error}</span> : null}
                </div>
              );
            })}
            <p className="banque-sheet-hint">
              Le titre, l'artiste, l'album, l'année et le genre s'écrivent dans le fichier ; la famille, dans la
              bibliothèque seulement.
            </p>
            {tried ? <TryReport outcome={tried} single /> : null}
            {failure ? (
              <p className="bacs-dialog-error" role="alert">
                {failure}
              </p>
            ) : null}
            <div className="banque-sheet-actions">
              <Button type="submit" size="2" highContrast disabled={busy || Boolean(yearError) || Boolean(tried?.refused.length)}>
                {busy ? <Spinner size="1" /> : null}
                {tried ? "Enregistrer quand même" : "Enregistrer"}
              </Button>
              <Button type="button" size="2" variant="soft" color="gray" disabled={busy} onClick={stop}>
                Annuler
              </Button>
            </div>
          </form>
        ) : (
          <section className="bacs-inspector-group" aria-label="Fiche">
            <p className="banque-sheet-state">
              <Badge size="1" variant="soft" color={fiche.complete ? "green" : "gray"} highContrast>
                {fiche.label}
              </Badge>
              <span>{fiche.detail}</span>
            </p>
            <dl className="banque-sheet-fields">
              {rows.map(([label, value]) => (
                <div key={label}>
                  <dt>{label}</dt>
                  <dd>{value}</dd>
                </div>
              ))}
            </dl>
          </section>
        )}
        <TitlePlaysSection titleId={title.id} />
        <section className="banque-sheet-file" aria-label="Fichier">
          <h3>Fichier</h3>
          <code>{title.path}</code>
          <p>Identifiant dans la bibliothèque : {title.id}</p>
        </section>
      </div>
    </aside>
  );
}

