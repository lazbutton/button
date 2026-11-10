import type { ReactNode } from "react";

/** L'en-tête d'une partie de Réglages : son titre, ce qu'elle règle, et ses gestes. */
export function SettingsHead({
  title,
  count,
  description,
  actions,
}: {
  title: string;
  count?: number;
  description?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <header className="reglages-head">
      <div className="reglages-head-copy">
        <div className="reglages-head-title">
          <h2>{title}</h2>
          {count != null ? <span className="ui-count">{count}</span> : null}
        </div>
        {description ? <p className="reglages-head-description">{description}</p> : null}
      </div>
      {actions ? <div className="reglages-head-actions">{actions}</div> : null}
    </header>
  );
}

/**
 * Un bloc d'une partie de Réglages : un sujet, ce qu'il change, puis ses champs ou
 * ses gestes. `tone="danger"` : des gestes qui ne se défont pas.
 */
export function SettingsCard({
  title,
  description,
  tone,
  children,
}: {
  title: string;
  description?: ReactNode;
  tone?: "danger";
  children?: ReactNode;
}) {
  return (
    <section className={tone === "danger" ? "reglages-card is-danger" : "reglages-card"}>
      <header className="reglages-card-head">
        <h3 className="reglages-card-title">{title}</h3>
        {description ? <div className="reglages-card-description">{description}</div> : null}
      </header>
      {children ? <div className="reglages-card-body">{children}</div> : null}
    </section>
  );
}
