import type { ReactNode } from "react";

type PageHeaderProps = {
  title: string;
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
  return (
    <header className="ui-page-header">
      <div className="ui-page-header-copy">
        {eyebrow ? <p className="ui-page-eyebrow">{eyebrow}</p> : null}
        <div className="ui-page-title-row">
          <h1 className="ui-page-title">{title}</h1>
          {status}
        </div>
        {description ? <div className="ui-page-description">{description}</div> : null}
      </div>
      {actions ? <div className="ui-page-actions">{actions}</div> : null}
    </header>
  );
}
