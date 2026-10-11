import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

export function EntityListItem({
  title,
  meta,
  icon: Icon,
  selected = false,
  trailing,
  onClick,
  className = "",
}: {
  title: ReactNode;
  meta?: ReactNode;
  icon?: LucideIcon;
  selected?: boolean;
  trailing?: ReactNode;
  onClick: () => void;
  className?: string;
}) {
  return (
    <button
      type="button"
      className={`ui-entity-item${selected ? " is-selected" : ""}${className ? ` ${className}` : ""}`}
      aria-pressed={selected}
      onClick={onClick}
    >
      {Icon ? (
        <span className="ui-entity-icon" aria-hidden="true">
          <Icon size={16} strokeWidth={1.75} />
        </span>
      ) : null}
      <span className="ui-entity-copy">
        <span className="ui-entity-title">{title}</span>
        {meta ? <span className="ui-entity-meta">{meta}</span> : null}
      </span>
      {trailing ? <span className="ui-entity-trailing">{trailing}</span> : null}
    </button>
  );
}
