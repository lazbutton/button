import { Badge, Button, IconButton } from "@radix-ui/themes";
import { Play, Square, X } from "lucide-react";
import { useEffect, useRef } from "react";
import { cell, ficheState, fileName, type BankTitle } from "../../api/bankTitles";
import { formatClock } from "../../api/soundsView";
import { TitlePlaysSection } from "./TitlePlays";

/**
 * The fiche of a title, in a panel to the right of the table: what Beets knows
 * of it, in reading. A drawer over the table on a narrow screen.
 */
export function TitleSheet({
  title,
  collection,
  playing,
  onPlay,
  onClose,
}: {
  title: BankTitle;
  /** The name of its collection, as the left column says it. */
  collection: string;
  playing: boolean;
  onPlay: () => void;
  onClose: () => void;
}) {
  const headRef = useRef<HTMLHeadingElement>(null);
  const fiche = ficheState(title.missing);

  // A fiche opened takes the focus, so a screen reader reads it and Escape closes it.
  useEffect(() => {
    headRef.current?.focus();
  }, [title.id]);

  const rows: Array<[string, string]> = [
    ["Artiste", cell(title.artist)],
    ["Album", cell(title.album)],
    ["Année", cell(title.year)],
    ["Genre", cell(title.genre)],
    ["Famille", cell(title.famille_label)],
    ["Durée", title.duration ? formatClock(title.duration) : "—"],
    ["Collection", cell(collection)],
  ];

  return (
    <aside
      className="bacs-inspector banque-sheet"
      aria-label={`Fiche de ${title.title || fileName(title.path)}`}
      onKeyDown={(event) => {
        if (event.key === "Escape") {
          event.stopPropagation();
          onClose();
        }
      }}
    >
      <header className="bacs-inspector-head">
        <h2 ref={headRef} tabIndex={-1} className="banque-sheet-title">
          Fiche du titre
        </h2>
        <span className="bacs-spacer" />
        <IconButton size="1" variant="ghost" color="gray" aria-label="Fermer la fiche" onClick={onClose}>
          <X size={16} />
        </IconButton>
      </header>
      <div className="bacs-inspector-body">
        <div className="banque-sheet-name">
          <strong>{title.title || fileName(title.path)}</strong>
          {title.artist ? <span>{title.artist}</span> : null}
        </div>
        <div className="banque-sheet-actions">
          <Button size="2" variant="soft" color="gray" onClick={onPlay}>
            {playing ? <Square className="ui-button-icon" /> : <Play className="ui-button-icon" />}
            {playing ? "Arrêter la pré-écoute" : "Pré-écouter"}
          </Button>
        </div>
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
