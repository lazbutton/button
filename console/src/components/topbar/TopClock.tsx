import { useParisNow } from "../../lib/parisClock";

const TIME = new Intl.DateTimeFormat("fr-FR", {
  timeZone: "Europe/Paris",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hourCycle: "h23",
});

const DAY = new Intl.DateTimeFormat("fr-FR", {
  timeZone: "Europe/Paris",
  weekday: "short",
  day: "numeric",
  month: "short",
});

const LONG = new Intl.DateTimeFormat("fr-FR", {
  timeZone: "Europe/Paris",
  weekday: "long",
  day: "numeric",
  month: "long",
  year: "numeric",
});

/** Heure de la station (Paris), à la seconde. */
export function TopClock() {
  const now = useParisNow();
  return (
    <time className="tb-clock" dateTime={now.toISOString()} title={`${LONG.format(now)}, heure de Paris`}>
      <span className="tb-clock-time">{TIME.format(now)}</span>
      <span className="tb-clock-date">{DAY.format(now)}</span>
    </time>
  );
}
