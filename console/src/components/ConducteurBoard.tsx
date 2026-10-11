import { Fragment, useEffect, useLayoutEffect, useRef, useState } from "react";
import { Badge, Button, IconButton, Separator, Text, Tooltip } from "@radix-ui/themes";
import { Radio, StepForward, Wrench, X } from "lucide-react";
import { formatMmSs } from "../lib/parisClock";
import { useAntennaClock } from "../lib/liveClock";
import {
  isMissingClockCart,
  itemNamedLikeLive,
  itemStatusCode,
  partitionRundown,
} from "../api/rundownLive";
import { KIND_LABELS } from "../api/clockMeta";
import type { LiveSnapshot, PositionKind, Rundown, RundownItem } from "../api/types";

const UPCOMING_CHUNK = 36;

function formatAt(iso: string): string {
  const time = iso.includes("T") ? iso.split("T")[1] : iso;
  return (time ?? iso).slice(0, 8);
}

function whenLabel(item: RundownItem): string {
  if (item.when === "live") return "en direct";
  if (item.when === "anchored" && item.minute != null) {
    const sync = item.sync === "molle" ? " molle" : item.sync === "dure" ? " dure" : "";
    return `:${String(item.minute).padStart(2, "0")}${sync}`;
  }
  return "séquentiel";
}

function cartLabel(item: RundownItem): string {
  return item.cart?.trim() || "";
}

function kindColor(_kind: string): "gray" {
  return "gray";
}

function kindClass(kind: string): string {
  return ["musique", "jingle", "son", "pub"].includes(kind) ? kind : "autre";
}

function statusColor(
  code: string,
): "green" | "red" | "gray" {
  if (code === "on_air") return "green";
  if (code === "failed") return "red";
  return "gray";
}

function queueLabel(queue: string): string {
  if (queue === "autodj") return "Auto-DJ";
  if (queue === "jingles") return "Jingles";
  if (queue === "carts") return "Carts";
  return queue || "—";
}

function resourceMeta(item: RundownItem): string {
  const bits = [
    item.category,
    item.fallback_used ? "secours" : null,
    item.reason === "glissement" ? "glissement" : item.reason,
    queueLabel(item.queue),
  ].filter(Boolean);
  return bits.filter((value, index, all) => all.indexOf(value) === index).join(" · ");
}

function hourDivider(items: RundownItem[], index: number): string | null {
  if (index === 0) return null;
  const hour = formatAt(items[index].at).slice(0, 2);
  const previousHour = formatAt(items[index - 1].at).slice(0, 2);
  return hour !== previousHour ? `${hour} h` : null;
}

function canRemove(item: RundownItem, role: "past" | "on-air" | "next" | "later"): boolean {
  if (!item.id || role === "on-air") return false;
  if (item.when === "anchored") return false;
  return true;
}

function RundownRow({
  item,
  index,
  role,
  remaining,
  as: Tag = "li",
  onRepair,
  onRemove,
}: {
  item: RundownItem;
  index: number;
  role: "past" | "on-air" | "next" | "later";
  remaining: number | null;
  as?: "li" | "div";
  onRepair?: (item: RundownItem) => void;
  onRemove?: (item: RundownItem) => void;
}) {
  const code = itemStatusCode(item);
  const duration =
    item.duration != null ? formatMmSs(Math.max(0, Math.round(item.duration))) : "—";
  const missing = isMissingClockCart(item);
  return (
    <Tag
      className={[
        "engine-rundown-row",
        `is-${kindClass(item.kind)}`,
        `is-status-${code}`,
        role === "on-air" ? "is-on-air" : "",
        role === "next" ? "is-next" : "",
        role === "past" ? "is-past" : "",
      ]
        .filter(Boolean)
        .join(" ")}
    >
      <span className="engine-rundown-state" aria-hidden="true">
        {role === "on-air" ? (
          <Radio size={14} />
        ) : role === "next" ? (
          <StepForward size={14} />
        ) : (
          <span>{String(index + 1).padStart(2, "0")}</span>
        )}
      </span>

      <span className="engine-rundown-at">
        <span>{formatAt(item.at)}</span>
        {remaining != null ? (
          <strong className="engine-rundown-remain">−{formatMmSs(remaining)}</strong>
        ) : null}
      </span>

      <span className="engine-rundown-kind">
        <Badge color={kindColor(item.kind)} variant="soft">
          {KIND_LABELS[item.kind as PositionKind] ?? item.kind}
        </Badge>
      </span>

      <span className="engine-rundown-cart" title={cartLabel(item) || undefined}>
        {cartLabel(item) || "—"}
      </span>

      <span className="engine-rundown-copy">
        <Text
          as="span"
          size="2"
          weight={role === "on-air" || role === "next" ? "bold" : "medium"}
          className="engine-rundown-resource"
        >
          {item.resource}
        </Text>
        {cartLabel(item) ? (
          <span className="engine-rundown-cartline">{cartLabel(item)}</span>
        ) : null}
        <span className="engine-rundown-meta">{resourceMeta(item)}</span>
      </span>

      <span className="engine-rundown-when">{whenLabel(item)}</span>
      <span className="engine-rundown-status">
        <Badge color={statusColor(code)} variant="soft">
          {item.status || code}
        </Badge>
        {missing && onRepair ? (
          <Button
            size="1"
            variant="soft"
            color="red"
            className="engine-rundown-repair"
            onClick={() => onRepair(item)}
          >
            <Wrench className="ui-button-icon" />
            Réparer
          </Button>
        ) : null}
        {canRemove(item, role) && onRemove ? (
          <Tooltip content="Retirer du conducteur">
            <IconButton
              size="1"
              variant="ghost"
              color="gray"
              className="engine-rundown-remove"
              aria-label={`Retirer ${item.resource || item.title || "le passage"}`}
              onClick={() => onRemove(item)}
            >
              <X className="ui-button-icon" />
            </IconButton>
          </Tooltip>
        ) : null}
      </span>
      <span className="engine-rundown-duration">{duration}</span>
    </Tag>
  );
}

export function ConducteurBoard({
  rundown,
  live,
  onRepair,
  onRemove,
}: {
  rundown: Rundown;
  live: LiveSnapshot | null;
  onRepair?: (item: RundownItem) => void;
  onRemove?: (item: RundownItem) => void;
}) {
  const clock = useAntennaClock(live ?? null);
  const wall = clock.wall;
  const { past, onAir, upcoming } = partitionRundown(rundown.items, wall, live);
  const listRef = useRef<HTMLOListElement>(null);
  const nowRef = useRef<HTMLLIElement>(null);
  const tailRef = useRef<HTMLLIElement>(null);
  const didPinRef = useRef(false);
  const nowOffsetRef = useRef(0);
  const onAirKey = onAir?.id ?? `${onAir?.at ?? ""}:${onAir?.resource ?? ""}`;
  const pastAnchor = past
    .map((item) => item.id ?? `${item.at}:${item.resource}`)
    .join("|");
  const [shownUpcoming, setShownUpcoming] = useState(UPCOMING_CHUNK);

  useLayoutEffect(() => {
    setShownUpcoming(UPCOMING_CHUNK);
  }, [onAirKey]);

  useLayoutEffect(() => {
    const list = listRef.current;
    const now = nowRef.current;
    if (!now) {
      didPinRef.current = false;
      nowOffsetRef.current = 0;
      return;
    }
    if (!list) return;
    const offset = now.offsetTop;
    if (!didPinRef.current) {
      list.scrollTop = offset;
      didPinRef.current = true;
    } else {
      const delta = offset - nowOffsetRef.current;
      if (delta) list.scrollTop += delta;
    }
    nowOffsetRef.current = now.offsetTop;
  }, [onAirKey, pastAnchor]);

  useEffect(() => {
    const tail = tailRef.current;
    const list = listRef.current;
    if (!tail || !list) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (!entries.some((entry) => entry.isIntersecting)) return;
        setShownUpcoming((count) =>
          count >= upcoming.length ? count : count + UPCOMING_CHUNK,
        );
      },
      { root: list, rootMargin: "160px" },
    );
    observer.observe(tail);
    return () => observer.disconnect();
  }, [upcoming.length, shownUpcoming, onAirKey]);

  if (!past.length && !onAir && !upcoming.length) {
    return (
      <div className="engine-rundown-empty">
        <Text size="2" color="gray">
          Aucun item prévu (pas d’horloge sur le daypart, ou bibliothèque vide).
        </Text>
      </div>
    );
  }

  const liveRemaining =
    onAir && itemNamedLikeLive(onAir, live ?? null) ? clock.remainingSec : null;
  const visibleUpcoming = upcoming.slice(0, shownUpcoming);

  return (
    <div className="engine-rundown is-board">
      <div className="engine-rundown-header" aria-hidden="true">
        <span>Heure</span>
        <span>Type</span>
        <span>Cart</span>
        <span>Ressource</span>
        <span>Quand</span>
        <span>Statut</span>
        <span>Durée</span>
      </div>

      <ol ref={listRef} className="engine-rundown-list" aria-label="Déroulé du conducteur">
        {past.length ? (
          <li className="engine-rundown-divider" aria-hidden="true">
            <span>Déjà passé</span>
            <Separator size="4" />
          </li>
        ) : null}
        {past.map((item, index) => (
          <RundownRow
            key={item.id ?? `past-${item.at}-${index}`}
            item={item}
            index={index}
            role="past"
            remaining={null}
            onRepair={onRepair}
            onRemove={onRemove}
          />
        ))}

        {onAir ? (
          <li ref={nowRef} className="engine-rundown-now">
            <div className="engine-rundown-divider" aria-hidden="true">
              <span>À l’antenne</span>
              <Separator size="4" />
            </div>
            <RundownRow
                as="div"
                item={onAir}
                index={0}
                role="on-air"
                remaining={liveRemaining}
                onRepair={onRepair}
                onRemove={onRemove}
              />
          </li>
        ) : null}

        {upcoming.length ? (
          <li className="engine-rundown-divider" aria-hidden="true">
            <span>À venir</span>
            <Separator size="4" />
          </li>
        ) : null}
        {visibleUpcoming.map((item, index) => {
          const divider = hourDivider(upcoming, index);
          return (
            <Fragment key={item.id ?? `up-${item.at}-${index}`}>
              {divider ? (
                <li className="engine-rundown-divider" aria-hidden="true">
                  <span>{divider}</span>
                  <Separator size="4" />
                </li>
              ) : null}
              <RundownRow
                item={item}
                index={index + 1}
                role={index === 0 ? "next" : "later"}
                remaining={null}
                onRepair={onRepair}
                onRemove={onRemove}
              />
            </Fragment>
          );
        })}
        {shownUpcoming < upcoming.length ? (
          <li
            ref={tailRef}
            className="engine-rundown-lazy"
            aria-label="Charger la suite du conducteur"
          />
        ) : null}
      </ol>
    </div>
  );
}
