import { ArrowRight, TriangleAlert, Wrench, X } from "lucide-react";
import { memo, useLayoutEffect, useRef, type Ref } from "react";
import { Link } from "react-router-dom";
import { mmss } from "../../api/antenneDesk";
import {
  kindClass,
  kindName,
  lineCopy,
  lineCut,
  lineKey,
  lineOrigin,
  lineStatus,
  lineTime,
  lineWall,
  linesToRepair,
  planEnd,
  repairNotice,
  rundownEntries,
  type LineChip,
  type LineRole,
  type RundownLine,
  type RundownMark,
} from "../../api/conducteurView";
import { isMissingClockCart, itemNamedLikeLive, queueItemSent, type PartitionedRundown } from "../../api/rundownLive";
import type { LiveSnapshot, Rundown, RundownItem } from "../../api/types";
import type { AntennaClock } from "../../lib/liveClock";

/** Retirer : ni une ligne passée, ni celle à l'antenne, ni une coupure, ni une ligne déjà partie. */
function canRemove(item: RundownItem, role: LineRole): boolean {
  if (!item.id || role === "past" || role === "now") return false;
  if (item.when === "anchored") return false;
  // Déjà partie vers l'antenne, son statut le dit : le moteur refuse de la retirer.
  return !queueItemSent(item);
}

function Chip({ chip }: { chip: LineChip }) {
  return (
    <>
      <span className="cond-chip" data-tone={chip.tone}>
        {chip.label}
      </span>{" "}
      {chip.detail ? <span className="cond-why">{chip.detail}</span> : null}{" "}
    </>
  );
}

function Mark({ mark }: { mark: RundownMark }) {
  const clock = mark.clock ? (
    <span className="cond-mark-clock">
      Heure type <strong>{mark.clock}</strong>
      {mark.daypart ? ` · ${mark.daypart}` : mark.newHour ? "" : ` · dès ${mark.at}`}
    </span>
  ) : null;
  return (
    <li className="cond-mark" data-hour={mark.newHour ? "true" : "false"} aria-hidden="true">
      {mark.newHour ? <span className="cond-mark-hour">{mark.hour}</span> : null}
      {mark.day ? <span className="cond-mark-day">{mark.day}</span> : null}
      {clock}
    </li>
  );
}

type RowProps = {
  item: RundownItem;
  role: LineRole;
  /** La ligne à l'antenne, quand le playout la confirme : le temps qui reste, et son avancée. */
  remaining: number | null;
  progress: number | null;
  rowKey: string;
  /** Le bouton qui ouvre la réparation suit : le focus y revient à la fermeture. */
  onRepair?: (item: RundownItem, origin: HTMLElement) => void;
  onRemove?: (item: RundownItem) => void;
  rowRef?: Ref<HTMLLIElement>;
};

const Row = memo(function Row({ item, role, remaining, progress, rowKey, onRepair, onRemove, rowRef }: RowProps) {
  const time = lineTime(item.at);
  const copy = lineCopy(item);
  const status = lineStatus(item, role);
  const cut = lineCut(item);
  const origin = lineOrigin(item);
  const kind = kindClass(item.kind);
  const repairable = Boolean(onRepair) && isMissingClockCart(item);
  const removable = Boolean(onRemove) && canRemove(item, role);
  // Un direct de l'encodeur n'a pas de durée : la console la reconstruit de ce qui est déjà passé.
  const open = item.origin === "live";
  const duration = open || !item.duration || item.duration <= 0 ? "—" : mmss(item.duration);
  const failed = status?.tone === "danger";
  return (
    <li
      ref={rowRef}
      className="cond-row"
      data-role={role}
      data-tone={status?.tone}
      data-kind={kind}
      data-key={rowKey}
      // Une ligne à réparer prend le focus quand le bandeau la montre.
      tabIndex={failed ? -1 : undefined}
    >
      <time className="cond-at" dateTime={item.at}>
        <span>{time.clock}</span>
        <span className="cond-at-s">{time.seconds}</span>
      </time>
      <span className="cond-copy">
        <span className="cond-name">
          <span className={`cond-kind is-${kind}`} title={kindName(item.kind)} aria-hidden="true" />
          {kind !== "musique" ? <span className="ui-visually-hidden">{kindName(item.kind)} : </span> : null}
          <span className="cond-title">{copy.title}</span>{" "}
          {copy.artist ? <span className="cond-artist">{copy.artist}</span> : null}
          {role === "next" ? <span className="ui-visually-hidden"> (ensuite)</span> : null}
        </span>{" "}
        {status || cut || repairable ? (
          <span className="cond-notes">
            {status ? <Chip chip={status} /> : null}
            {cut ? <Chip chip={cut} /> : null}
            {repairable ? (
              <button
                type="button"
                className="cond-fix"
                aria-label={`Réparer ${copy.title}`}
                onClick={(event) => onRepair?.(item, event.currentTarget)}
              >
                <Wrench size={13} aria-hidden="true" />
                Réparer
              </button>
            ) : null}
          </span>
        ) : null}
      </span>{" "}
      <span className="cond-origin">{origin}</span>{" "}
      <span className="cond-dur">
        {remaining != null ? <strong>−{mmss(remaining)}</strong> : duration}
      </span>
      <span className="cond-act">
        {removable ? (
          <button
            type="button"
            className="cond-remove"
            aria-label={`Retirer ${copy.title} du conducteur`}
            title="Retirer du conducteur"
            onClick={() => onRemove?.(item)}
          >
            <X size={15} aria-hidden="true" />
          </button>
        ) : null}
      </span>
      {progress != null ? (
        <span className="cond-progress" aria-hidden="true">
          <span style={{ transform: `scaleX(${progress})` }} />
        </span>
      ) : null}
    </li>
  );
});

/** Le déroulé : l'heure par heure, la ligne à l'antenne tenue en haut, les lignes à réparer signalées. */
export function RundownPanel({
  rundown,
  parts,
  live,
  clock,
  unreadable,
  canEdit,
  onRepair,
  onRemove,
}: {
  rundown: Rundown;
  parts: PartitionedRundown;
  live: LiveSnapshot | null;
  clock: AntennaClock;
  /** Le moteur ne donne plus le conducteur : ses lignes restent, et se disent vieillies. */
  unreadable: boolean;
  canEdit: boolean;
  onRepair?: (item: RundownItem, origin: HTMLElement) => void;
  onRemove?: (item: RundownItem) => void;
}) {
  const { past, onAir, upcoming } = parts;
  const lines: RundownLine[] = [
    ...past.map((item) => ({ item, role: "past" as const })),
    ...(onAir ? [{ item: onAir, role: "now" as const }] : []),
    ...upcoming.map((item, index) => ({ item, role: index === 0 ? ("next" as const) : ("later" as const) })),
  ];
  const entries = rundownEntries(lines, lineWall(clock.wall)?.day ?? "");
  const broken = linesToRepair(onAir ? [onAir, ...upcoming] : upcoming);
  const end = planEnd(rundown.items);
  const notice = repairNotice(broken.length, end, canEdit);
  // Le temps qui reste ne se compte que si le playout dit jouer cette ligne-là, et quand elle finit.
  const timed =
    Boolean(onAir && onAir.origin !== "live" && onAir.queue !== "stream" && itemNamedLikeLive(onAir, live)) &&
    clock.durationSec > 1;
  const remaining = timed ? clock.remainingSec : null;
  const progress = timed ? Math.min(1, clock.elapsedSec / Math.max(1, clock.durationSec)) : null;

  const listRef = useRef<HTMLOListElement>(null);
  const nowRef = useRef<HTMLLIElement>(null);
  const didPinRef = useRef(false);
  const nowOffsetRef = useRef(0);
  // Une ligne bâtie par la console, un direct par exemple, n'a pas d'identifiant,
  // et son heure se recalcule à chaque relevé : elle se reconnaît à son contenu.
  const onAirKey = onAir ? (onAir.id ?? `${onAir.origin ?? ""}|${onAir.queue}|${onAir.resource}`) : "";
  const pastAnchor = past.map((item) => lineKey(item)).join("|");

  // La ligne à l'antenne s'ouvre en haut du déroulé, et le reste à lire ne bouge
  // pas quand le passé change. Collée en haut, son offsetTop suit le défilement :
  // sa place se lit au bas de ce qui la précède.
  useLayoutEffect(() => {
    const list = listRef.current;
    const now = nowRef.current;
    if (!now) {
      didPinRef.current = false;
      nowOffsetRef.current = 0;
      return;
    }
    if (!list) return;
    const before = now.previousElementSibling as HTMLElement | null;
    const offset = before ? before.offsetTop + before.offsetHeight : 0;
    if (!didPinRef.current) {
      list.scrollTop = offset;
      didPinRef.current = true;
    } else {
      const delta = offset - nowOffsetRef.current;
      if (delta) list.scrollTop += delta;
    }
    nowOffsetRef.current = offset;
  }, [onAirKey, pastAnchor]);

  const reveal = () => {
    const first = broken[0];
    const list = listRef.current;
    if (!first || !list) return;
    const entry = entries.find((row) => row.type === "line" && row.line.item === first);
    const target = entry
      ? Array.from(list.querySelectorAll<HTMLLIElement>("li[data-key]")).find((li) => li.dataset.key === entry.key)
      : undefined;
    if (!target) return;
    const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    target.scrollIntoView({ block: "center", behavior: still ? "auto" : "smooth" });
    const action = target.querySelector<HTMLButtonElement>(".cond-fix");
    (action ?? target).focus({ preventScroll: true });
  };

  return (
    <section className="cond-panel" aria-labelledby="cond-panel-title" data-edit={onRemove ? "true" : "false"}>
      <header className="cond-panel-head">
        <h2 id="cond-panel-title">Déroulé</h2>
        <span className="cond-count">
          {upcoming.length ? `${upcoming.length} à venir` : ""}
          {upcoming.length && end ? " · " : ""}
          {end ? `jusqu’à ${end}` : ""}
        </span>
      </header>

      {/* Toujours là, vide tant que le conducteur se lit : un lecteur d'écran annonce la mention quand elle arrive. */}
      <div role="status">
        {unreadable ? (
          <p className="cond-notice" data-tone="stale">
            <TriangleAlert size={15} aria-hidden="true" />
            <span>Le conducteur ne répond plus : ces lignes peuvent avoir changé.</span>
          </p>
        ) : null}
      </div>
      {notice ? (
        <div className="cond-notice" data-tone="danger">
          <TriangleAlert size={15} aria-hidden="true" />
          <p>
            <strong>{notice.title}.</strong> {notice.help}
          </p>
          <button type="button" className="cond-btn" onClick={reveal}>
            {broken.length > 1 ? "Voir la première" : "Voir la ligne"}
          </button>
        </div>
      ) : null}

      {entries.length ? (
        <>
          <div className="cond-cols" aria-hidden="true">
            <span>Heure</span>
            <span>Titre</span>
            <span>Origine</span>
            <span>Durée</span>
            <span />
          </div>
          {/* La liste défile : elle prend le focus, pour défiler au clavier. */}
          <ol
            ref={listRef}
            className="cond-list"
            aria-label="Déroulé du conducteur"
            tabIndex={0}
            data-stale={unreadable ? "true" : "false"}
          >
            {entries.map((entry) =>
              entry.type === "mark" ? (
                <Mark key={entry.key} mark={entry.mark} />
              ) : (
                <Row
                  key={entry.key}
                  rowKey={entry.key}
                  item={entry.line.item}
                  role={entry.line.role}
                  remaining={entry.line.role === "now" ? remaining : null}
                  progress={entry.line.role === "now" ? progress : null}
                  onRepair={onRepair}
                  onRemove={onRemove}
                  rowRef={entry.line.role === "now" ? nowRef : undefined}
                />
              ),
            )}
          </ol>
        </>
      ) : unreadable ? (
        <div className="cond-empty is-error">
          <strong>Le conducteur ne répond pas.</strong>
          <span>Il revient dès que l’automate répond. Si ça dure, un admin regarde Réglages → Automate.</span>
        </div>
      ) : rundown.clock ? (
        <div className="cond-empty">
          <strong>Rien de prévu.</strong>
          <span>L’heure type « {rundown.clock} » ne donne rien à jouer pour l’instant.</span>
          {canEdit ? (
            <Link to="/programmation" className="cond-link">
              Ouvrir les heures types
              <ArrowRight size={14} aria-hidden="true" />
            </Link>
          ) : null}
        </div>
      ) : (
        <div className="cond-empty">
          <strong>Rien de prévu.</strong>
          <span>Aucune heure type n’est posée dans la semaine à cette heure.</span>
          {canEdit ? (
            <Link to="/programmation?onglet=semaine" className="cond-link">
              Ouvrir la semaine
              <ArrowRight size={14} aria-hidden="true" />
            </Link>
          ) : null}
        </div>
      )}

      <footer className="cond-foot">
        <span>La file se change au pupitre.</span>
        <Link to="/antenne" className="cond-link">
          Ouvrir le pupitre
          <ArrowRight size={14} aria-hidden="true" />
        </Link>
      </footer>
    </section>
  );
}
