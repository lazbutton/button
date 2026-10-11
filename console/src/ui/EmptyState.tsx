import { Button } from "@radix-ui/themes";
import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

export function EmptyState({
  icon: Icon,
  title,
  description,
  actionLabel,
  onAction,
}: {
  icon: LucideIcon;
  title: string;
  description: ReactNode;
  actionLabel?: string;
  onAction?: () => void;
}) {
  return (
    <div className="ui-empty">
      <div>
        <span className="ui-empty-icon" aria-hidden="true">
          <Icon size={19} strokeWidth={1.75} />
        </span>
        <p className="ui-empty-title">{title}</p>
        <div className="ui-empty-description">{description}</div>
        {actionLabel && onAction ? (
          <Button mt="3" variant="soft" onClick={onAction}>
            {actionLabel}
          </Button>
        ) : null}
      </div>
    </div>
  );
}
