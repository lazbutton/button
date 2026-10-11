import { Fragment } from "react";
import { Badge, Separator, Text } from "@radix-ui/themes";
import { Radio, StepForward } from "lucide-react";
import { formatMmSs, useParisNow } from "../lib/parisClock";
import {
  itemRemainingSec,
  partitionRundown,
  visibleRundownItems,
} from "../api/rundownLive";
import type { LiveSnapshot, Rundown, RundownItem } from "../api/types";

function formatAt(iso: string): string {
  const time = iso.includes("T") ? iso.split("T")[1] : iso;
  return (time ?? iso).slice(0, 8);
}

function whenLabel(item: Rundown["items"][number]): string {
  if (item.when === "live") return "en direct";
  if (item.when === "anchored" && item.minute != null) {
    return `:${String(item.minute).padStart(2, "0")}`;
  }
  return "séquentiel";
}

function cartLine(item: RundownItem): string {
  const cart = item.cart?.trim() || "";
  if (!cart) return "";
  return cart === item.resource.trim() ? "" : cart;
}

function kindColor(_kind: string): "gray" {
  return "gray";
}

function kindClass(kind: string): string {
  return ["musique", "jingle", "son", "pub"].includes(kind) ? kind : "autre";
}

function timeDividerLabel(
  items: Rundown["items"],
  index: number,
): string | null {
  if (index === 1) return "Prochain passage";
  if (index === 2) return "Suite du conducteur";
  if (index < 3) return null;

  const hour = formatAt(items[index].at).slice(0, 2);
  const previousHour = formatAt(items[index - 1].at).slice(0, 2);
  return hour !== previousHour ? `${hour} h` : null;
}

export function EngineRundown({
  rundown,
  compact = false,
  live = null,
}: {
  rundown: Rundown;
  compact?: boolean;
  live?: LiveSnapshot | null;
}) {
  const wall = useParisNow();
  const { onAir, upcoming } = partitionRundown(rundown.items, wall, live);
  const items = onAir ? [onAir, ...upcoming] : upcoming;
  if (!items.length) {
    return (
      <div className="engine-rundown-empty">
        <Text size="2" color="gray">
          Aucun item prévu (pas d’horloge sur le daypart, ou bibliothèque vide).
        </Text>
      </div>
    );
  }

  return (
    <div className={compact ? "engine-rundown is-compact" : "engine-rundown"}>
      <div className="engine-rundown-header" aria-hidden="true">
        <span>Heure</span>
        <span>Type</span>
        <span>Ressource</span>
        {compact ? null : (
          <>
            <span>Quand</span>
            <span>File</span>
            <span>Durée</span>
          </>
        )}
      </div>

      <ol className="engine-rundown-list" aria-label="Déroulé du conducteur">
        {items.map((item, index) => {
          const onAir = index === 0;
          const next = index === 1;
          const remain = onAir ? itemRemainingSec(item, wall) : null;
          const divider = timeDividerLabel(items, index);
          const duration =
            item.duration != null
              ? formatMmSs(Math.max(0, Math.round(item.duration)))
              : "—";

          return (
            <Fragment key={`${item.at}-${item.resource}-${index}`}>
              {divider ? (
                <li className="engine-rundown-divider" aria-hidden="true">
                  <span>{divider}</span>
                  <Separator size="4" />
                </li>
              ) : null}

              <li
                className={[
                  "engine-rundown-row",
                  `is-${kindClass(item.kind)}`,
                  onAir ? "is-on-air" : "",
                  next ? "is-next" : "",
                ]
                  .filter(Boolean)
                  .join(" ")}
              >
                <span className="engine-rundown-state" aria-hidden="true">
                  {onAir ? (
                    <Radio size={14} />
                  ) : next ? (
                    <StepForward size={14} />
                  ) : (
                    <span>{String(index + 1).padStart(2, "0")}</span>
                  )}
                </span>

                <span className="engine-rundown-at">
                  <span>{formatAt(item.at)}</span>
                  {remain != null ? (
                    <strong className="engine-rundown-remain">
                      −{formatMmSs(remain)}
                    </strong>
                  ) : null}
                </span>

                <span className="engine-rundown-kind">
                  <Badge color={kindColor(item.kind)} variant="soft">
                    {item.kind}
                  </Badge>
                </span>

                <span className="engine-rundown-copy">
                  <Text
                    as="span"
                    size="2"
                    weight={onAir || next ? "bold" : "medium"}
                    className="engine-rundown-resource"
                  >
                    {item.resource}
                  </Text>
                  {cartLine(item) ? (
                    <span className="engine-rundown-cartline">{cartLine(item)}</span>
                  ) : null}
                </span>

                {compact ? null : (
                  <>
                    <span className="engine-rundown-when">{whenLabel(item)}</span>
                    <span className="engine-rundown-queue">{item.queue}</span>
                    <span className="engine-rundown-duration">{duration}</span>
                  </>
                )}
              </li>
            </Fragment>
          );
        })}
      </ol>
    </div>
  );
}

export function UpcomingRundown({ items }: { items: RundownItem[] }) {
  const wall = useParisNow();
  const rows = visibleRundownItems(items, wall).slice(0, 10);
  if (!rows.length) {
    return (
      <Text size="2" color="gray">
        Rien de prévu dans le conducteur.
      </Text>
    );
  }
  return (
    <ol className="desk-upcoming" aria-label="Dix suivants">
      {rows.map((item, index) => {
        const cart = cartLine(item);
        const note = item.status === "manquant" ? "cart manquant" : cart;
        return (
          <li
            key={`${item.at}-${item.resource}-${index}`}
            className={`is-${item.kind}${index === 0 ? " is-next" : ""}`}
          >
            <span className="desk-upcoming-n">{index === 0 ? "Next" : index + 1}</span>
            <span className={`kind-dot is-${item.kind}`} aria-hidden="true" />
            <span className="desk-upcoming-copy">
              <span className="desk-upcoming-title">{item.resource}</span>
              {note ? <span className="desk-upcoming-cart">{note}</span> : null}
            </span>
            <span className="desk-upcoming-dur">
              {formatMmSs(Math.max(0, Math.round(item.duration ?? 0)))}
            </span>
            <span className="queue-edit-actions" />
          </li>
        );
      })}
    </ol>
  );
}
