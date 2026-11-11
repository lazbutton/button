import { ChevronRight, TriangleAlert } from "lucide-react";
import { useId } from "react";
import { skippedName, skippedNotice, skippedSplit } from "../../api/cartRefusals";
import type { SkippedFile } from "../../api/types";

/**
 * Les fichiers du dossier d'un bac que le moteur n'a pas pris, chacun avec sa
 * raison : sans eux, un fichier déposé n'entrerait jamais dans le bac sans que
 * personne le sache. `folder` : le dossier du bac, vu du dossier de la station.
 */
export function SkippedFiles({ files, folder }: { files: SkippedFile[]; folder: string }) {
  const titleId = useId();
  const notice = skippedNotice(files, folder);
  if (!notice) return null;
  const { shown, more } = skippedSplit(files);
  return (
    // Sa hauteur est bornée, pour laisser la table des sons à l'écran : au-delà,
    // il défile, et se prend au clavier pour défiler.
    <section className="bacs-skipped" aria-labelledby={titleId} tabIndex={0}>
      <TriangleAlert size={15} aria-hidden="true" />
      <div className="bacs-skipped-copy">
        <strong id={titleId}>{notice.title}</strong>
        <p>{notice.help}</p>
        <SkippedList files={shown} folder={folder} />
        {more.length ? (
          <details className="bacs-skipped-more">
            <summary>
              <ChevronRight size={14} aria-hidden="true" />
              Voir les {more.length} autres
            </summary>
            <SkippedList files={more} folder={folder} />
          </details>
        ) : null}
      </div>
    </section>
  );
}

function SkippedList({ files, folder }: { files: SkippedFile[]; folder: string }) {
  return (
    <ul className="bacs-skipped-list">
      {files.map((file) => (
        <li key={file.path}>
          <span className="bacs-skipped-name">{skippedName(file, folder)}</span>{" "}
          <span className="bacs-skipped-reason">{file.reason}</span>
        </li>
      ))}
    </ul>
  );
}
