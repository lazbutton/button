import type { ElementType, ReactNode } from "react";

type PanelProps = {
  children: ReactNode;
  className?: string;
  padded?: boolean;
  scroll?: boolean;
  as?: ElementType;
};

export function Panel({
  children,
  className = "",
  padded = true,
  scroll = false,
  as: Component = "section",
}: PanelProps) {
  const classes = [
    "ui-panel",
    padded ? "ui-panel--padded" : "",
    scroll ? "ui-panel--scroll" : "",
    className,
  ]
    .filter(Boolean)
    .join(" ");

  return <Component className={classes}>{children}</Component>;
}

export function SectionHeader({
  title,
  description,
  count,
  actions,
}: {
  title: string;
  description?: ReactNode;
  count?: number;
  actions?: ReactNode;
}) {
  return (
    <header className="ui-section-header">
      <div className="ui-section-header-copy">
        <div className="ui-section-heading">
          <h2 className="ui-section-title">{title}</h2>
          {count != null ? <span className="ui-count">{count}</span> : null}
        </div>
        {description ? <div className="ui-section-description">{description}</div> : null}
      </div>
      {actions}
    </header>
  );
}
