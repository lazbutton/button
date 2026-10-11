import { Flex, Heading, Text } from "@radix-ui/themes";
import { EngineRundown } from "./EngineRundown";
import type { LiveSnapshot, Rundown } from "../api/types";

export function ConducteurPanel({
  rundown,
  compact = false,
  live = null,
}: {
  rundown: Rundown;
  compact?: boolean;
  live?: LiveSnapshot | null;
}) {
  const nextAnchored = rundown.items.find((item) => item.when === "anchored" && item.minute != null);
  const hasAnchors = rundown.items.some((item) => item.when === "anchored");

  return (
    <div className={`conductor-panel${compact ? " is-compact" : ""}`}>
      <Flex justify="between" align="baseline" mb="2" gap="2">
        {compact ? <Heading size="4">Conducteur</Heading> : <span />}
      </Flex>
      <Text size="2" weight="medium" mb="2" as="p" className="conductor-legend">
        {rundown.clock || "—"}
        {rundown.daypart ? ` · ${rundown.daypart}` : ""}
        {hasAnchors
          ? nextAnchored
            ? ` · ancre :${String(nextAnchored.minute).padStart(2, "0")}`
            : " · ancres hors fenêtre"
          : " · motif seul"}
      </Text>
      <EngineRundown rundown={rundown} compact={compact} live={live} />
    </div>
  );
}
