import { Button, Flex, Skeleton, Spinner, Text } from "@radix-ui/themes";
import { RefreshCw, WifiOff } from "lucide-react";

export function LoadingState({
  label = "Chargement…",
  cover = false,
}: {
  label?: string;
  cover?: boolean;
}) {
  return (
    <div className={`ui-data-state${cover ? " is-cover" : ""}`} aria-busy="true" aria-label={label}>
      <div className="ui-skeleton-stack">
        <Flex align="center" gap="2">
          <Spinner size="2" />
          <Text size="2" color="gray">
            {label}
          </Text>
        </Flex>
        <Skeleton height="2.5rem" />
        <Skeleton height="5.5rem" />
        <Skeleton height="5.5rem" />
      </div>
    </div>
  );
}

export function ErrorState({
  title = "Connexion impossible",
  description,
  onRetry,
  cover = false,
}: {
  title?: string;
  description: string;
  onRetry: () => void;
  cover?: boolean;
}) {
  return (
    <div className={`ui-data-state${cover ? " is-cover" : ""}`}>
      <div className="ui-data-card">
        <span className="ui-empty-icon" aria-hidden="true">
          <WifiOff size={19} strokeWidth={1.75} />
        </span>
        <p className="ui-empty-title">{title}</p>
        <p className="ui-empty-description">{description}</p>
        <Button mt="3" variant="soft" onClick={onRetry}>
          <RefreshCw className="ui-button-icon" />
          Réessayer
        </Button>
      </div>
    </div>
  );
}
