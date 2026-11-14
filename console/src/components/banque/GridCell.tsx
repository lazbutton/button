import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import type { BankTitle, FicheField } from "../../api/bankTitles";
import { cell } from "../../api/bankTitles";
import { cellName, cellText, moveOf, type Move } from "../../api/titleGrid";
import { FAMILIES, titleName } from "../../api/titleEdits";

/**
 * Une cellule du tableau qui se corrige comme dans un tableur (FON-67). Au repos,
 * un bouton : Entrée (ou F2) l'ouvre, les flèches passent aux voisines, Espace
 * sélectionne le titre, Ctrl+C copie sa valeur et Ctrl+V la colle. Ouverte, un
 * champ : Entrée enregistre et descend, Tab enregistre et passe à la suivante,
 * Échap annule.
 */
export function GridCell({
  title,
  field,
  row,
  column,
  busy,
  onSave,
  onMove,
  onPaste,
  onToggle,
  onAnnounce,
}: {
  title: BankTitle;
  field: FicheField;
  row: number;
  column: number;
  busy: boolean;
  /** Écrit la valeur ; rend faux si l'écriture n'a pas eu lieu, et la cellule reste ouverte. */
  onSave: (value: string) => Promise<boolean>;
  onMove: (move: Move) => void;
  onPaste: (text: string) => void;
  onToggle?: () => void;
  onAnnounce: (text: string) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState("");
  const [saving, setSaving] = useState(false);
  // Une seule écriture à la fois : la touche, puis la perte du focus, ne doublent pas.
  const writing = useRef(false);
  const field_ = useRef<HTMLInputElement & HTMLSelectElement>(null);
  const shown = field === "famille" ? title.famille_label : cellText(title, field);
  const name = cellName(field, titleName(title));

  useEffect(() => {
    if (editing) {
      field_.current?.focus();
      if (field !== "famille") field_.current?.select();
    }
  }, [editing, field]);

  const open = () => {
    if (busy) return;
    setValue(cellText(title, field));
    setEditing(true);
    onAnnounce(`Cellule ouverte : ${name}. Entrée enregistre, Échap annule.`);
  };

  const close = (move?: Move) => {
    setEditing(false);
    if (move) onMove(move);
    else requestAnimationFrame(() => document.querySelector<HTMLElement>(`[data-grid="${row}:${column}"]`)?.focus());
  };

  const commit = async (move?: Move) => {
    if (writing.current) return;
    writing.current = true;
    setSaving(true);
    const done = await onSave(value);
    writing.current = false;
    setSaving(false);
    if (done) close(move);
  };

  // Un clic ailleurs : la valeur changée s'enregistre, sinon la cellule se referme.
  const onBlur = () => {
    if (writing.current) return;
    if (value === cellText(title, field)) setEditing(false);
    else void commit();
  };

  const onCellKey = (event: KeyboardEvent<HTMLButtonElement>) => {
    const mod = event.ctrlKey || event.metaKey;
    if (event.key === "Enter" || event.key === "F2") {
      event.preventDefault();
      open();
    } else if (event.key === " " && onToggle) {
      event.preventDefault();
      onToggle();
    } else if (mod && event.key.toLowerCase() === "c") {
      event.preventDefault();
      void navigator.clipboard?.writeText(cellText(title, field)).then(
        () => onAnnounce(`${name} copié.`),
        () => onAnnounce("La valeur n'a pas pu se copier."),
      );
    } else if (event.key !== "Tab") {
      const move = moveOf(event.key, event.shiftKey);
      if (move) {
        event.preventDefault();
        onMove(move);
      }
    }
  };

  const onEditKey = (event: KeyboardEvent<HTMLInputElement | HTMLSelectElement>) => {
    if (event.key === "Escape") {
      event.preventDefault();
      event.stopPropagation();
      close();
      onAnnounce(`${name} : rien n'a changé.`);
    } else if (event.key === "Enter") {
      event.preventDefault();
      void commit("down");
    } else if (event.key === "Tab") {
      event.preventDefault();
      void commit(event.shiftKey ? "previous" : "next");
    }
  };

  if (editing) {
    return field === "famille" ? (
      <select
        ref={field_}
        className="banque-cell-input"
        aria-label={name}
        value={value}
        disabled={saving}
        onChange={(event) => setValue(event.target.value)}
        onKeyDown={onEditKey}
        onBlur={onBlur}
      >
        <option value="">Aucune</option>
        {FAMILIES.map((family) => (
          <option key={family.name} value={family.name}>
            {family.label}
          </option>
        ))}
      </select>
    ) : (
      <input
        ref={field_}
        className="banque-cell-input"
        aria-label={name}
        value={value}
        disabled={saving}
        inputMode={field === "year" ? "numeric" : undefined}
        maxLength={field === "year" ? 4 : 1000}
        onChange={(event) => setValue(event.target.value)}
        onKeyDown={onEditKey}
        onBlur={onBlur}
      />
    );
  }

  return (
    <button
      type="button"
      className="banque-cell"
      data-grid={`${row}:${column}`}
      disabled={busy}
      onClick={open}
      onKeyDown={onCellKey}
      onPaste={(event) => {
        const text = event.clipboardData.getData("text/plain");
        if (!text) return;
        event.preventDefault();
        onPaste(text);
      }}
    >
      {shown ? cell(shown) : <span aria-hidden="true">—</span>}
      {shown ? null : <span className="ui-visually-hidden">vide</span>}
    </button>
  );
}
