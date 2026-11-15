import { Badge, Button, Dialog, Spinner } from "@radix-ui/themes";
import { ArrowLeft, ArrowRight, Check, Pause, Play, Undo2, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState, type KeyboardEvent } from "react";
import { apiGet, apiPostJson } from "../../api/client";
import {
  FICHES_DECISIONS_JSON,
  FICHES_JSON,
  FIELD_LABELS,
  LEVEL_LABELS,
  duration,
  durationGap,
  fichesQuery,
  fieldValue,
  levelColor,
  propositionStatus,
  type Decided,
  type FicheDetail,
  type FicheProposition,
  type FicheTitle,
  type FichesFilters,
  type FichesPage,
} from "../../api/fiches";
import {
  REOPEN_JSON,
  endLine,
  gestureLine,
  positionLine,
  progressText,
  queueOf,
  reviewKey,
  titleName,
  undoneLine,
  waitingIds,
  type Gesture,
} from "../../api/reviewKeys";
import { TITLES_SEND_DEADLINE_MS } from "../../api/sendDeadline";

/** La pré-écoute de la vue À relire : un seul casque pour la liste et la relecture. */
type Preview = { playingId: string | null; toggle: (id: string) => void; stop: () => void };

// Le titre suivant se lit avant d'y arriver : la file n'attend pas.
const AHEAD = 2;

function messageOf(caught: unknown, fallback: string): string {
  return caught instanceof Error && caught.message ? caught.message : fallback;
}

/**
 * « Relire au clavier » (FON-78) : les titres à relire de la vue, un à la fois, en
 * grand, l'avant et l'après de chaque champ côte à côte. L'extrait part seul, et
 * s'arrête au titre suivant. A accepte le titre, R le refuse, les flèches passent
 * au suivant ou reviennent, Z défait le dernier geste, Échap ferme. Chaque geste
 * s'annonce à un lecteur d'écran. Un titre à revoir ou rapproché s'accepte ici
 * seul, ouvert, comme dans la liste (FON-26).
 */
export function KeyboardReview({
  filters,
  canWrite,
  preview,
  onClose,
}: {
  filters: FichesFilters;
  canWrite: boolean;
  preview: Preview;
  onClose: () => void;
}) {
  const [queue, setQueue] = useState<FicheTitle[] | null>(null);
  const [total, setTotal] = useState(0);
  // La file a une suite chez le moteur.
  const [more, setMore] = useState(false);
  const [index, setIndex] = useState(0);
  const [details, setDetails] = useState<Record<number, FicheDetail | string>>({});
  const [history, setHistory] = useState<Gesture[]>([]);
  const [done, setDone] = useState({ accepted: 0, refused: 0 });
  const [busy, setBusy] = useState(false);
  const [said, setSaid] = useState("");
  const [problem, setProblem] = useState("");
  const [loadProblem, setLoadProblem] = useState("");
  const loadingMore = useRef(false);
  const previewRef = useRef(preview);
  previewRef.current = preview;
  // Seuls les titres qui attendent : l'état à relire, quels que soient les autres filtres.
  const asked = { ...filters, state: "proposée" };

  const read = useCallback(async (beetsId: number) => {
    try {
      const detail = await apiGet<FicheDetail>(`/fiches/${beetsId}.json`);
      setDetails((before) => ({ ...before, [beetsId]: detail }));
    } catch (caught) {
      setDetails((before) => ({ ...before, [beetsId]: messageOf(caught, "La fiche ne s'est pas lue.") }));
    }
  }, []);

  // La première page de la file, à l'ouverture.
  useEffect(() => {
    let alive = true;
    void apiGet<FichesPage>(`${FICHES_JSON}${fichesQuery(asked)}`).then(
      (page) => {
        if (!alive) return;
        const first = queueOf(page.titles);
        setQueue(first);
        setTotal(page.total);
        setMore(page.next != null);
        setSaid(first.length ? positionLine(0, page.total, titleName(first[0])) : "");
      },
      (caught) => alive && setLoadProblem(messageOf(caught, "Les titres à relire ne se sont pas lus. Réessaie.")),
    );
    return () => {
      alive = false;
    };
    // La file se lit une fois : les filtres de la vue ne changent pas pendant la relecture.
  }, []);

  /**
   * La suite de la file ; rend la file allongée. Le moteur ne rend que les titres
   * qui attendent : chaque titre décidé en sort, et la suite commence d'autant
   * plus tôt. Un titre déjà dans la file ne s'y ajoute pas deux fois.
   */
  const loadMore = useCallback(async (): Promise<FicheTitle[] | null> => {
    if (!more || loadingMore.current || !queue) return queue;
    loadingMore.current = true;
    try {
      let offset: number | null = Math.max(0, queue.length - history.length);
      let longer = queue;
      while (offset != null && longer.length === queue.length) {
        const page: FichesPage = await apiGet<FichesPage>(`${FICHES_JSON}${fichesQuery(asked, offset)}`);
        longer = [...longer, ...queueOf(page.titles, longer)];
        offset = page.next;
      }
      setQueue(longer);
      setMore(offset != null);
      return longer;
    } catch (caught) {
      setProblem(messageOf(caught, "La suite des titres ne s'est pas lue. Réessaie."));
      return queue;
    } finally {
      loadingMore.current = false;
    }
  }, [history.length, more, queue]);

  const current = queue && index < queue.length ? queue[index] : null;
  const currentId = current?.id ?? null;

  // Le titre montré se lit, avec ses preuves ; la suite se charge avant d'y arriver.
  useEffect(() => {
    if (!queue) return;
    if (currentId != null && !details[currentId]) void read(currentId);
    if (index >= queue.length - AHEAD) void loadMore();
  }, [currentId, details, index, loadMore, queue, read]);

  // L'extrait part seul, et s'arrête au titre suivant ou à la fin de la file.
  useEffect(() => {
    if (currentId == null) {
      previewRef.current.stop();
      return;
    }
    if (previewRef.current.playingId !== String(currentId)) previewRef.current.toggle(String(currentId));
  }, [currentId]);

  const detail = current ? details[current.id] : undefined;
  const propositions: FicheProposition[] =
    current == null ? [] : typeof detail === "object" ? detail.propositions : current.propositions;

  const say = (text: string) => {
    // Le même texte deux fois de suite se redit : la région change d'abord.
    setSaid("");
    window.setTimeout(() => setSaid(text), 30);
  };

  const arrive = (target: number, list: FicheTitle[], before = "") => {
    setIndex(target);
    const where =
      target < list.length ? positionLine(target, total, titleName(list[target])) : endLine(done.accepted, done.refused);
    say([before, where].filter(Boolean).join(" "));
  };

  const go = async (delta: -1 | 1) => {
    if (!queue) return;
    const target = index + delta;
    if (target < 0) {
      say("C'est le premier titre.");
      return;
    }
    let list = queue;
    if (target >= list.length && more) list = (await loadMore()) ?? list;
    if (target > list.length) return;
    setProblem("");
    arrive(target, list);
  };

  const decide = async (kind: "accept" | "refuse") => {
    if (!queue || !current || busy) return;
    const name = titleName(current);
    if (kind === "accept" && !canWrite) {
      say("La correction des fiches est coupée sur cette station : rien ne s'accepte. R refuse.");
      return;
    }
    const ids = waitingIds(propositions);
    if (!ids.length) {
      say(`« ${name} » n'a plus rien à relire.`);
      return;
    }
    setBusy(true);
    setProblem("");
    try {
      const body = kind === "accept" ? { accept: ids } : { refuse: ids };
      const decided = await apiPostJson<Decided>(FICHES_DECISIONS_JSON, body, TITLES_SEND_DEADLINE_MS);
      const gesture: Gesture = { kind, beetsId: current.id, ids, name };
      setHistory((before) => [...before, gesture]);
      const counted = {
        accepted: done.accepted + (kind === "accept" ? 1 : 0),
        refused: done.refused + (kind === "refuse" ? 1 : 0),
      };
      setDone(counted);
      await read(current.id);
      const line = gestureLine(gesture, decided);
      if (decided.failed.length) {
        // Un titre qui ne s'est pas écrit reste montré : Z le remet à relire.
        setProblem(line);
        return;
      }
      setIndex(index + 1);
      const where =
        index + 1 < queue.length
          ? positionLine(index + 1, total, titleName(queue[index + 1]))
          : endLine(counted.accepted, counted.refused);
      say(`${line} ${where}`);
    } catch (caught) {
      setProblem(messageOf(caught, "La décision n'a pas été prise. Réessaie."));
      await read(current.id);
    } finally {
      setBusy(false);
    }
  };

  const undo = async () => {
    if (!queue || busy) return;
    const last = history.at(-1);
    if (!last) {
      say("Aucun geste à défaire.");
      return;
    }
    setBusy(true);
    setProblem("");
    try {
      const decided = await apiPostJson<Decided>(REOPEN_JSON, { ids: last.ids }, TITLES_SEND_DEADLINE_MS);
      setHistory((before) => before.slice(0, -1));
      setDone((before) => ({
        accepted: before.accepted - (last.kind === "accept" ? 1 : 0),
        refused: before.refused - (last.kind === "refuse" ? 1 : 0),
      }));
      await read(last.beetsId);
      const at = queue.findIndex((title) => title.id === last.beetsId);
      arrive(at < 0 ? index : at, queue, undoneLine(last, decided));
    } catch (caught) {
      setProblem(messageOf(caught, "Le geste n'a pas été défait. Réessaie."));
    } finally {
      setBusy(false);
    }
  };

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const key = reviewKey(event, event.target as HTMLElement);
    if (!key) return;
    event.preventDefault();
    if (busy) return;
    if (key === "accept" || key === "refuse") void decide(key);
    else if (key === "undo") void undo();
    else void go(key === "next" ? 1 : -1);
  };

  const ended = queue != null && index >= queue.length && !more;
  const playing = current != null && preview.playingId === String(current.id);
  const waiting = waitingIds(propositions);

  return (
    <Dialog.Root
      open
      onOpenChange={(open) => {
        if (!open && !busy) onClose();
      }}
    >
      <Dialog.Content maxWidth="48rem" className="fiches-keys" onKeyDown={onKeyDown}>
        <div className="fiches-keys-head">
          <Dialog.Title size="4" mb="0">
            Relire au clavier
          </Dialog.Title>
          {queue && total ? (
            <div className="fiches-keys-progress">
              <progress value={Math.min(index + 1, total)} max={total} aria-label="Avancement" />
              <span>{progressText(index, total)}</span>
            </div>
          ) : null}
        </div>
        <Dialog.Description size="2" className="fiches-keys-help">
          <kbd>A</kbd> accepte le titre, <kbd>R</kbd> le refuse, <kbd>←</kbd> <kbd>→</kbd> passent d'un titre à
          l'autre, <kbd>Z</kbd> défait le dernier geste, <kbd>Échap</kbd> ferme.
        </Dialog.Description>

        {/* Ce que le lecteur d'écran entend : chaque geste, et le titre où l'on arrive. */}
        <p className="ui-visually-hidden" role="status" aria-live="polite">
          {said}
        </p>
        {problem ? (
          <p className="fiches-keys-problem" role="alert">
            {problem}
          </p>
        ) : null}

        {loadProblem ? (
          <p className="fiches-keys-problem" role="alert">
            {loadProblem}
          </p>
        ) : queue == null ? (
          <p className="fiches-keys-wait" role="status">
            <Spinner size="1" /> Lecture des titres à relire…
          </p>
        ) : queue.length === 0 ? (
          <p className="fiches-keys-end">Rien à relire ici pour l'instant.</p>
        ) : current ? (
          <section className="fiches-keys-title" aria-label={titleName(current)}>
            <div className="fiches-keys-name">
              <div>
                <h3>{titleName(current)}</h3>
                <p>{[current.artist, current.album].filter(Boolean).join(" · ") || "Artiste inconnu"}</p>
              </div>
              <Badge size="2" variant="soft" color={levelColor(current.level)} highContrast>
                {LEVEL_LABELS[current.level] ?? current.level}
              </Badge>
            </div>

            <table className="fiches-keys-table">
              <caption className="ui-visually-hidden">Ce qui changerait, champ par champ</caption>
              <thead>
                <tr>
                  <th scope="col">Champ</th>
                  <th scope="col">Avant</th>
                  <th scope="col">Après</th>
                  <th scope="col">
                    <span className="ui-visually-hidden">État</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {propositions.map((one) => {
                  const status = propositionStatus(one);
                  return (
                    <tr key={one.id}>
                      <th scope="row">{FIELD_LABELS[one.field] ?? one.field}</th>
                      <td className="fiches-keys-before">{fieldValue(one.field, one.before)}</td>
                      <td className="fiches-keys-after">{fieldValue(one.field, one.value)}</td>
                      <td>
                        {status ? (
                          <Badge size="1" variant="soft" color={status.color} highContrast>
                            {status.label}
                          </Badge>
                        ) : null}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>

            {typeof detail === "object" ? (
              <Evidence detail={detail} />
            ) : typeof detail === "string" ? (
              <p className="fiches-keys-problem" role="alert">
                {detail}
              </p>
            ) : null}

            <div className="fiches-keys-actions">
              <Button size="2" variant="soft" color="gray" onClick={() => preview.toggle(String(current.id))}>
                {playing ? <Pause className="ui-button-icon" /> : <Play className="ui-button-icon" />}
                {playing ? "Arrêter l'extrait" : "Écouter l'extrait"}
              </Button>
              <span className="fiches-keys-spacer" />
              <Button
                size="2"
                variant="soft"
                disabled={busy || !canWrite || waiting.length === 0}
                onClick={() => void decide("accept")}
              >
                <Check className="ui-button-icon" />
                Accepter <kbd>A</kbd>
              </Button>
              <Button
                size="2"
                variant="soft"
                color="gray"
                disabled={busy || waiting.length === 0}
                onClick={() => void decide("refuse")}
              >
                <X className="ui-button-icon" />
                Refuser <kbd>R</kbd>
              </Button>
            </div>
          </section>
        ) : (
          <div className="fiches-keys-end">
            {ended ? <p>{endLine(done.accepted, done.refused)}</p> : <Spinner size="2" />}
          </div>
        )}

        <div className="fiches-keys-nav">
          <Button size="2" variant="ghost" color="gray" disabled={busy || index === 0} onClick={() => void go(-1)}>
            <ArrowLeft className="ui-button-icon" />
            Précédent
          </Button>
          <Button
            size="2"
            variant="ghost"
            color="gray"
            disabled={busy || queue == null || (index >= queue.length && !more)}
            onClick={() => void go(1)}
          >
            Suivant
            <ArrowRight className="ui-button-icon" />
          </Button>
          <span className="fiches-keys-spacer" />
          {busy ? <Spinner size="2" /> : null}
          <Button size="2" variant="soft" color="gray" disabled={busy || history.length === 0} onClick={() => void undo()}>
            <Undo2 className="ui-button-icon" />
            Défaire <kbd>Z</kbd>
          </Button>
          <Dialog.Close>
            <Button size="2" variant="soft" color="gray" disabled={busy}>
              Fermer
            </Button>
          </Dialog.Close>
        </div>
      </Dialog.Content>
    </Dialog.Root>
  );
}

function Evidence({ detail }: { detail: FicheDetail }) {
  const { evidence, fiche, title } = detail;
  const gap = durationGap(title.duration, evidence?.duration ?? null);
  return (
    <div className="fiches-keys-evidence">
      {evidence ? (
        <p>
          Trouvé sur {evidence.found_at || fiche.source || "une source"}
          {evidence.title ? ` : « ${evidence.title} »${evidence.artists ? `, de ${evidence.artists}` : ""}` : ""}. Durée :
          fichier {duration(title.duration)}
          {evidence.duration != null ? `, trouvée ${duration(evidence.duration)}` : ""}
          {gap ? ` (${gap})` : ""}.
        </p>
      ) : null}
      {evidence?.doubt ? <p className="fiches-doubt">{evidence.doubt}</p> : null}
      {fiche.reasons.length ? (
        <ul className="fiches-reasons" aria-label="Pourquoi ce niveau">
          {fiche.reasons.map((reason) => (
            <li key={reason}>{reason}</li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
