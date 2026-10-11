import type { ReactNode } from "react";

type PageHeaderProps = {
  title?: string;
  description?: ReactNode;
  eyebrow?: string;
  status?: ReactNode;
  actions?: ReactNode;
};

export function PageHeader({
  title,
  description,
  eyebrow,
  status,
  actions,
}: PageHeaderProps) {
  const hasCopy = Boolean(eyebrow || title || status || description);
  if (!hasCopy && !actions) return null;
  return (
    <header className="ui-page-header">
      {hasCopy ? (
        <div className="ui-page-header-copy">
          {eyebrow ? <p className="ui-page-eyebrow">{eyebrow}</p> : null}
          {title || status ? (
            <div className="ui-page-title-row">
              {title ? <h1 className="ui-page-title">{title}</h1> : null}
              {status}
            </div>
          ) : null}
          {description ? <div className="ui-page-description">{description}</div> : null}
        </div>
      ) : null}
      {actions ? <div className="ui-page-actions">{actions}</div> : null}
    </header>
  );
}
