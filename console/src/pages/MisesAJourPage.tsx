import { Button } from "@radix-ui/themes";
import {
  Check,
  ChevronRight,
  Circle,
  CircleAlert,
  CircleArrowUp,
  CircleCheck,
  CircleDot,
  CircleHelp,
  CircleX,
  Clock,
  ExternalLink,
  LoaderCircle,
  Lock,
  RefreshCw,
  type LucideIcon,
} from "lucide-react";
import { Fragment, useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import {
  ApiAuthError,
  ApiForbiddenError,
  ApiRequestError,
  ApiUnavailableError,
  apiDeleteJson,
  apiGet,
  apiPostJson,
} from "../api/client";
import { SessionGate } from "../api/SessionGate";
import {
  UPDATES_JSON,
  UPDATES_REQUEST_JSON,
  detailLabel,
  formatWhen,
  historyLine,
  lastLine,
  nightlyLine,
  notesIntro,
  parseNotes,
  pollDelay,
  readFailureMessage,
  releaseKind,
  splitNotes,
  statusOf,
  withCommands,
  type Inline,
  type Line,
  type NoteBlock,
  type Status,
  type StatusKind,
  type Step,
  type StepState,
  type Tone,
  type UpdateRelease,
  type UpdatesState,
} from "../api/updates";
import { SettingsCard, SettingsHead } from "../components/reglages/SettingsCard";
import { AppToast, useAppToast } from "../ui/AppToast";
import { ConfirmDialog } from "../ui/ConfirmDialog";
import { LoadingState } from "../ui/DataState";
import "../styles/pages/reglages.css";

/** L'icône d'un ton, pour une ligne de l'historique ou la dernière demande. */
const ICON: Record<Tone, LucideIcon> = {
  ok: CircleCheck,
  warn: CircleAlert,
  alert: CircleX,
  off: CircleHelp,
  info: CircleArrowUp,
};

/** L'icône de la carte d'état : une flèche pour une version à prendre, une roue pour ce qui avance, une horloge pour ce qui attend. */
const STATUS_ICON: Record<StatusKind, LucideIcon> = {
  available: CircleArrowUp,
  uptodate: CircleCheck,
  blocked: CircleAlert,
  pending: Clock,
  waiting: Clock,
  unseen: CircleX,
  running: LoaderCircle,
  restarting: LoaderCircle,
  unreachable: CircleX,
};

const STEP_ICON: Record<StepState, LucideIcon> = {
  done: Check,
  current: CircleDot,
  waiting: Clock,
  stuck: CircleX,
  todo: Circle,
};

/** Ce qu'un lecteur d'écran entend de chaque étape, l'icône ne se lisant pas. */
const STEP_SAID: Record<StepState, string> = {
  done: "faite",
  current: "en cours",
  waiting: "en attente",
  stuck: "bloquée",
  todo: "à venir",
};

/**
 * Ce qui empêche de lire la page : la session, le droit, un moteur trop ancien,
 * un moteur muet, ou une erreur du moteur, avec ce qu'il faut en dire.
 */
type Problem = { kind: "auth" | "forbidden" | "outdated" | "down" | "error"; message: string };

const SAID: Record<Exclude<Problem["kind"], "error">, string> = {
  auth: "Session expirée. Reconnecte-toi.",
  forbidden: "Réservé à un admin. Reconnecte-toi avec ce compte.",
  outdated: "Mets à jour le moteur pour avoir cette page.",
  down: "Le moteur ne répond pas. Réessaie dans un instant.",
};

function problemOf(caught: unknown): Problem {
  if (caught instanceof ApiAuthError) return { kind: "auth", message: SAID.auth };
  if (caught instanceof ApiForbiddenError) return { kind: "forbidden", message: SAID.forbidden };
  // Un moteur d'avant cette page n'a pas la route : il répond 404.
  if (caught instanceof ApiRequestError && caught.status === 404) return { kind: "outdated", message: SAID.outdated };
  if (caught instanceof ApiRequestError) {
    return { kind: "error", message: readFailureMessage(caught.status, caught.message) };
  }
  if (caught instanceof ApiUnavailableError) return { kind: "down", message: SAID.down };
  return { kind: "error", message: readFailureMessage(0, "") };
}

/**
 * Réglages → Mises à jour, pour un admin : où en est la station, d'une carte,
 * de la version publiée jusqu'à la demande en cours, puis les notes, les
 * dernières mises à jour et la machine. La console ne touche jamais la machine :
 * « Mettre à jour maintenant » écrit une demande dans le moteur, et la machine
 * la prend dans la minute.
 */
export function MisesAJourPage() {
  const [state, setState] = useState<UpdatesState | null>(null);
  const [problem, setProblem] = useState<Problem | null>(null);
  const [busy, setBusy] = useState<"ask" | "withdraw" | "check" | null>(null);
  const [confirming, setConfirming] = useState(false);
  const { toast, show, dismiss } = useAppToast();
  // La version de la station quand la page s'est ouverte : une autre, et la
  // console en service a peut-être changé aussi.
  const opened = useRef<string | null | undefined>(undefined);
  // La demande pendant laquelle la page a vu le moteur se taire : son
  // redémarrage est passé, même une fois le moteur revenu.
  const restartedFor = useRef<string | null>(null);

  const load = useCallback(async (refresh = false): Promise<UpdatesState | Problem> => {
    try {
      const next = await apiGet<UpdatesState>(refresh ? `${UPDATES_JSON}?refresh=1` : UPDATES_JSON);
      if (opened.current === undefined) opened.current = next.installed;
      setState(next);
      setProblem(null);
      return next;
    } catch (caught) {
      const found = problemOf(caught);
      setProblem(found);
      return found;
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const unreachable = problem?.kind === "down";
  const delay = pollDelay(state, unreachable);
  useEffect(() => {
    const id = window.setInterval(() => void load(), delay);
    const onVisible = () => {
      if (document.visibilityState === "visible") void load();
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      window.clearInterval(id);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [delay, load]);

  useEffect(() => {
    if (unreachable && state?.request?.state === "running") restartedFor.current = state.request.id;
  }, [unreachable, state]);

  // Un échec s'annonce, toujours : jamais un bouton qui ne fait rien.
  const fail = (caught: unknown, fallback: string) => {
    if (caught instanceof ApiAuthError) show("Session expirée. Reconnecte-toi.", "error");
    else if (caught instanceof ApiForbiddenError) show("Réservé à un admin. Reconnecte-toi avec ce compte.", "error");
    else if (caught instanceof ApiRequestError) show(caught.message, "error");
    else if (caught instanceof ApiUnavailableError) show("Le moteur ne répond pas. Réessaie dans un instant.", "error");
    else show(fallback, "error");
  };

  const ask = async () => {
    setBusy("ask");
    try {
      const next = await apiPostJson<UpdatesState>(UPDATES_REQUEST_JSON, {});
      setState(next);
      setConfirming(false);
      show("Mise à jour demandée : la machine la prend dans la minute.", "success");
    } catch (caught) {
      setConfirming(false);
      fail(caught, "La demande n’est pas partie. Réessaie.");
      void load();
    } finally {
      setBusy(null);
    }
  };

  const withdraw = async () => {
    setBusy("withdraw");
    try {
      const next = await apiDeleteJson<UpdatesState>(UPDATES_REQUEST_JSON);
      setState(next);
      show("Demande retirée.", "success");
    } catch (caught) {
      fail(caught, "La demande n’a pas été retirée. Réessaie.");
      void load();
    } finally {
      setBusy(null);
    }
  };

  const check = async () => {
    setBusy("check");
    const next = await load(true);
    setBusy(null);
    if ("kind" in next) show(next.message, "error");
    else if (next.check.error) show(`Les versions ne se lisent pas : ${next.check.error}.`, "error");
    else if (next.check.pending) show("GitHub répond lentement : la page se met à jour seule.", "info");
    else show("Versions relues sur GitHub.", "success");
  };

  if (problem?.kind === "auth" || (unreachable && state == null)) {
    return (
      <SessionGate loading={false} error={problem?.kind === "auth" ? "auth" : "down"} onRetry={() => void load()}>
        {null}
      </SessionGate>
    );
  }

  return (
    <div className="reglages-section reglages-updates">
      <SettingsHead
        title="Mises à jour"
        description="La station se met à jour d’un bouton : une sauvegarde d’abord, et si la nouvelle version ne repart pas, elle revient seule à la sienne."
        actions={
          <Button variant="soft" color="gray" disabled={busy != null || state == null} onClick={() => void check()}>
            <RefreshCw className="ui-button-icon" aria-hidden="true" />
            {busy === "check" ? "Vérification…" : "Vérifier les versions"}
          </Button>
        }
      />
      <div className="reglages-stack reglages-stack--narrow">
        {problem?.kind === "error" ? (
          <section className="reglages-card reglages-notice" role="alert">
            <p>
              <Said text={problem.message} />
            </p>
            <div>
              <Button variant="soft" color="gray" disabled={busy != null} onClick={() => void load()}>
                Réessayer
              </Button>
            </div>
          </section>
        ) : null}
        {problem?.kind === "forbidden" ? (
          <Notice>Réservé à un admin : ce compte ne voit pas les mises à jour.</Notice>
        ) : problem?.kind === "outdated" ? (
          <Notice>
            <Said text="Mets à jour le moteur pour avoir cette page : le sien ne connaît pas encore les mises à jour depuis la console. Sur la machine : sudo station update." />
          </Notice>
        ) : state == null ? (
          problem?.kind === "error" ? null : <LoadingState label="Lecture des mises à jour…" />
        ) : (
          <UpdatesView
            state={state}
            unreachable={unreachable}
            restarted={state.request != null && restartedFor.current === state.request.id}
            changed={opened.current !== undefined && opened.current !== state.installed}
            busy={busy}
            confirming={confirming}
            onConfirming={setConfirming}
            onAsk={ask}
            onWithdraw={withdraw}
          />
        )}
      </div>
      <AppToast toast={toast} onDismiss={dismiss} />
    </div>
  );
}

function UpdatesView({
  state,
  unreachable,
  restarted,
  changed,
  busy,
  confirming,
  onConfirming,
  onAsk,
  onWithdraw,
}: {
  state: UpdatesState;
  unreachable: boolean;
  restarted: boolean;
  changed: boolean;
  busy: "ask" | "withdraw" | "check" | null;
  confirming: boolean;
  onConfirming: (open: boolean) => void;
  onAsk: () => Promise<void>;
  onWithdraw: () => Promise<void>;
}) {
  // « aujourd’hui », « hier », le temps écoulé : relus à chaque lecture de la page,
  // toutes les 5 s pendant une demande, au moins une fois la minute sinon.
  const now = new Date();
  const status = statusOf(state, { unreachable, restarted, now });
  return (
    <>
      <StatusCard
        state={state}
        status={status}
        now={now}
        unreachable={unreachable}
        changed={changed}
        busy={busy}
        confirming={confirming}
        onConfirming={onConfirming}
        onAsk={onAsk}
        onWithdraw={onWithdraw}
      />

      {state.releases.length ? (
        <SettingsCard title="Notes de version" description={notesIntro(state.releases)}>
          <div className="reglages-updates-releases">
            {state.releases.map((release) => (
              <Release key={release.version} release={release} now={now} />
            ))}
          </div>
        </SettingsCard>
      ) : null}

      <SettingsCard
        title="Les dernières mises à jour"
        description="Celles de la console comme celles de la machine, d’après updates.log."
      >
        {state.history.length ? (
          <ul className="reglages-updates-history">
            {state.history.map((entry) => {
              const line = historyLine(entry, now);
              return (
                <li key={`${entry.started_at}-${entry.from}-${entry.to}`}>
                  <Dot tone={line.tone} />
                  <div className="reglages-updates-history-copy">
                    <p className="reglages-updates-history-title">{line.title}</p>
                    <p className="reglages-updates-history-detail">{line.detail}</p>
                  </div>
                </li>
              );
            })}
          </ul>
        ) : (
          <p className="reglages-empty">Aucune pour l’instant.</p>
        )}
      </SettingsCard>

      <SettingsCard title="La machine">
        <dl className="reglages-facts">
          <Fact label="Demandes de la console">
            {state.host == null ? "pas encore prises" : state.host.requests ? "prises chaque minute" : "coupées"}
          </Fact>
          <Fact label="Nouvelles de la machine">
            {state.host?.seen_at ? formatWhen(state.host.seen_at, now) : "aucune"}
          </Fact>
          <Fact label="Commande station">{state.host?.command ?? "inconnue"}</Fact>
          <Fact label="Mises à jour la nuit">pas encore</Fact>
        </dl>
        <p className="reglages-note">
          <Said text={nightlyLine(state.host)} />
        </p>
        {state.services.length ? (
          <details className="reglages-updates-fold reglages-updates-services">
            <summary>
              <ChevronRight className="reglages-updates-chevron" aria-hidden="true" />
              <span>
                La version de chaque service
                {state.recorded_at ? `, relevée ${formatWhen(state.recorded_at, now)}` : ""}
              </span>
            </summary>
            <ul className="reglages-list">
              {state.services.map((item) => (
                <li key={item.service}>
                  <span className="reglages-list-when">{item.service}</span>{" "}
                  <span className="reglages-list-what">{item.version ?? item.image ?? "?"}</span>
                </li>
              ))}
            </ul>
          </details>
        ) : null}
      </SettingsCard>
    </>
  );
}

/**
 * Où en est la station, d'une carte : sa phase, avec son icône, ce qu'il faut en
 * savoir, les étapes d'une demande ouverte, puis le geste qu'elle permet, et la
 * dernière demande close. `HOLD` et l'action d'une majeure y sont dits une fois.
 */
function StatusCard({
  state,
  status,
  now,
  unreachable,
  changed,
  busy,
  confirming,
  onConfirming,
  onAsk,
  onWithdraw,
}: {
  state: UpdatesState;
  status: Status;
  now: Date;
  unreachable: boolean;
  changed: boolean;
  busy: "ask" | "withdraw" | "check" | null;
  confirming: boolean;
  onConfirming: (open: boolean) => void;
  onAsk: () => Promise<void>;
  onWithdraw: () => Promise<void>;
}) {
  const code = status.kind === "blocked" ? state.blocked?.code : undefined;
  const Icon =
    code === "hold"
      ? Lock
      : status.kind === "blocked" && status.tone === "alert"
        ? CircleX
        : status.kind === "blocked" && status.tone === "off"
          ? CircleHelp
          : STATUS_ICON[status.kind];
  const spinning = status.kind === "running" || status.kind === "restarting";
  const hold = state.host?.hold ?? null;
  const last = !state.request && state.last ? lastLine(state.last, now) : null;
  return (
    <section className={`reglages-card reglages-summary reglages-updates-status tone-${status.tone}`}>
      <span className="reglages-summary-icon" aria-hidden="true">
        <Icon className={spinning ? "reglages-updates-spin" : undefined} />
      </span>
      <div className="reglages-summary-copy">
        <div role="status">
          <h3 className="reglages-summary-title">{status.title}</h3>
          {status.detail ? (
            <p className="reglages-summary-detail">
              <Said text={status.detail} />
            </p>
          ) : null}
        </div>
        {status.versions ? <Versions versions={status.versions} /> : null}
        {status.since ? <p className="reglages-updates-meta">{status.since}</p> : null}
      </div>

      {status.steps ? <Steps steps={status.steps} /> : null}

      {hold ? (
        <div className="reglages-updates-extra">
          <p className="reglages-updates-kicker">HOLD, sur la machine</p>
          <pre className="reglages-updates-hold">{hold}</pre>
          {state.blocked?.code === "hold" ? null : (
            <p className="reglages-updates-blocked">
              <Said text="Pour débloquer les mises à jour, une fois la cause trouvée, sur la machine : sudo station unhold." />
            </p>
          )}
        </div>
      ) : null}

      {state.major ? (
        <div className="reglages-updates-extra">
          <p className="reglages-updates-kicker">Mise en service de la {state.major.version}</p>
          {state.blocked?.code === "major" ? null : (
            <p className="reglages-updates-blocked">
              <Said
                text={`La ${state.major.version}, une majeure, demande une action à la station avant de la prendre : elle ne part pas de la console. Une fois l’action faite, sur la machine : sudo station update --major.`}
              />
            </p>
          )}
          <Notes text={state.major.action} empty="Ses notes ne se lisent pas ici." />
          <p className="reglages-note">
            <a href={state.major.url} target="_blank" rel="noreferrer">
              Les notes de la {state.major.version}, sur GitHub
            </a>
          </p>
        </div>
      ) : null}

      {status.action === "ask" ? (
        <div className="reglages-updates-action">
          <ConfirmDialog
            open={confirming}
            onOpenChange={onConfirming}
            title={`Mettre la station à jour, en ${state.latest} ?`}
            description={`La station passe de ${state.installed} à ${state.latest}. La machine prend la demande dans la minute : une sauvegarde d’abord, puis les images, pendant que l’antenne joue, puis le redémarrage, qui coupe l’antenne quelques secondes. Elle attend la fin d’un direct ou d’une diffusion de l’Agenda. Si la ${state.latest} ne repart pas, la station revient seule à la ${state.installed}.`}
            confirmLabel="Mettre à jour"
            busy={busy === "ask"}
            onConfirm={onAsk}
            trigger={
              <Button disabled={busy != null} highContrast>
                Mettre à jour maintenant
              </Button>
            }
          />
        </div>
      ) : status.action === "withdraw" ? (
        <div className="reglages-updates-action">
          <Button variant="soft" color="gray" disabled={busy != null || unreachable} onClick={() => void onWithdraw()}>
            {busy === "withdraw" ? "Retrait…" : "Retirer la demande"}
          </Button>
        </div>
      ) : null}

      {changed && !unreachable ? (
        <div className="reglages-updates-extra reglages-updates-reload" role="status">
          <p>
            La station est passée en {state.installed ?? "?"} depuis l’ouverture de cette page : la console en service
            a peut-être changé aussi. Recharge la page pour la prendre.
          </p>
          <div>
            <Button variant="soft" onClick={() => window.location.reload()}>
              Recharger la page
            </Button>
          </div>
        </div>
      ) : null}

      {last ? <LastResult line={last} /> : null}
    </section>
  );
}

/** La version de la station et la plus haute publiée : « 1.0.1 → 1.5.0 », lu « 1.0.1 vers 1.5.0 ». */
function Versions({ versions }: { versions: NonNullable<Status["versions"]> }) {
  if (!versions.arrow) return <p className="reglages-updates-meta">{versions.said}</p>;
  const [from, to] = versions.arrow;
  return (
    <p className="reglages-updates-meta">
      <span className="reglages-updates-version">{from}</span>
      <span aria-hidden="true"> → </span>
      <span className="ui-visually-hidden"> vers </span>
      <span className="reglages-updates-version">{to}</span>
      {versions.said ? ` · ${versions.said}` : null}
    </p>
  );
}

/** Les étapes d'une demande : une liste ordonnée, chaque état dit en toutes lettres, l'icône ne se lisant pas. */
function Steps({ steps }: { steps: Step[] }) {
  return (
    <ol className="reglages-updates-steps" aria-label="Étapes de la mise à jour">
      {steps.map((step) => {
        const Icon = STEP_ICON[step.state];
        const active = step.state === "current" || step.state === "waiting" || step.state === "stuck";
        return (
          <li key={step.label} className={`is-${step.state}`} aria-current={active ? "step" : undefined}>
            <span className="reglages-updates-step-icon" aria-hidden="true">
              <Icon />
            </span>
            <span className="reglages-updates-step-copy">
              <span className="reglages-updates-step-label">{step.label}</span>
              <span className="ui-visually-hidden"> : {STEP_SAID[step.state]}</span>
              {step.meta ? <span className="reglages-updates-step-meta"> · {step.meta}</span> : null}
            </span>
          </li>
        );
      })}
    </ol>
  );
}

/** La dernière demande close, au pied de la carte d'état : son résultat, quand, et ce qu'en a dit la machine. */
function LastResult({ line }: { line: Line }) {
  return (
    <div className="reglages-updates-last">
      <Dot tone={line.tone} />
      <div role="status">
        <p className="reglages-updates-kicker">La dernière demande</p>
        <h4 className="reglages-updates-last-title">{line.title}</h4>
        <p className="reglages-updates-history-detail">
          <Said text={line.detail} />
        </p>
      </div>
    </div>
  );
}

/** Une petite icône de ton, pour une ligne de l'historique ou la dernière demande. */
function Dot({ tone }: { tone: Tone }) {
  const Icon = ICON[tone];
  return (
    <span className={`reglages-updates-dot tone-${tone}`} aria-hidden="true">
      <Icon />
    </span>
  );
}

/**
 * Une version que la mise à jour apporte : son numéro, ce qu'elle est, sa date,
 * puis la tête de ses notes, qui dit ce qu'elle demande à la station, et le
 * détail de ses changements, à déplier.
 */
function Release({ release, now }: { release: UpdateRelease; now: Date }) {
  const { lead, detail, changes } = splitNotes(parseNotes(release.notes));
  const kind = releaseKind(release.version);
  return (
    <article className="reglages-updates-release">
      <div className="reglages-updates-release-head">
        <h4>
          {release.version}{" "}
          {kind ? (
            <>
              <span className={kind === "majeure" ? "reglages-updates-kind is-major" : "reglages-updates-kind"}>
                {kind}
              </span>{" "}
            </>
          ) : null}
          {release.published_at ? (
            <span className="reglages-updates-release-date">publiée {formatWhen(release.published_at, now)}</span>
          ) : null}
        </h4>
        {release.url ? (
          <a
            className="reglages-updates-release-link"
            href={release.url}
            target="_blank"
            rel="noreferrer"
            aria-label={`La ${release.version} sur GitHub`}
            title={`La ${release.version} sur GitHub`}
          >
            <ExternalLink aria-hidden="true" />
          </a>
        ) : null}
      </div>
      {lead.length ? <NoteBlocks blocks={lead} /> : null}
      {detail.length ? (
        <details className="reglages-updates-fold reglages-updates-detail">
          <summary>
            <ChevronRight className="reglages-updates-chevron" aria-hidden="true" />
            <span>{detailLabel(release.version, changes)}</span>
          </summary>
          <NoteBlocks blocks={detail} />
        </details>
      ) : null}
      {!lead.length && !detail.length ? <p className="reglages-empty">Pas de notes.</p> : null}
    </article>
  );
}

function Notice({ children }: { children: ReactNode }) {
  return (
    <section className="reglages-card reglages-notice" role="status">
      <p>{children}</p>
    </section>
  );
}

function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="reglages-fact">
      <dt>{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}

/** Un texte de la page ou du moteur, ses commandes à taper sur la machine en police de code. */
function Said({ text }: { text: string }) {
  return <Inlines items={withCommands(text)} />;
}

function Inlines({ items }: { items: Inline[] }) {
  return (
    <>
      {items.map((item, index) => {
        switch (item.kind) {
          case "strong":
            return <strong key={index}>{item.text}</strong>;
          case "code":
            return <code key={index}>{item.text}</code>;
          case "command":
            // Coupée entre ses mots seulement : « -- » se lit mal seul en fin de ligne.
            return (
              <code key={index} className="reglages-updates-command">
                {item.text.split(" ").map((word, at) => (
                  <Fragment key={at}>
                    {at ? " " : null}
                    <span>{word}</span>
                  </Fragment>
                ))}
              </code>
            );
          case "link":
            return (
              <a key={index} href={item.href} target="_blank" rel="noreferrer">
                {item.text}
              </a>
            );
          default:
            return <span key={index}>{item.text}</span>;
        }
      })}
    </>
  );
}

/** Des notes de version : un peu de Markdown, rendu sans HTML. */
function Notes({ text, empty = "Pas de notes." }: { text: string | null; empty?: string }) {
  const blocks = parseNotes(text);
  if (!blocks.length) return <p className="reglages-empty">{empty}</p>;
  return <NoteBlocks blocks={blocks} />;
}

function NoteBlocks({ blocks }: { blocks: NoteBlock[] }) {
  return (
    <div className="reglages-updates-notes">
      {blocks.map((block, index) => {
        switch (block.kind) {
          case "heading":
            return (
              <h5 key={index}>
                <Inlines items={block.inlines} />
              </h5>
            );
          case "list":
            return (
              <ul key={index}>
                {block.items.map((item, at) => (
                  <li key={at}>
                    <Inlines items={item} />
                  </li>
                ))}
              </ul>
            );
          case "code":
            return <pre key={index}>{block.text}</pre>;
          default:
            return (
              <p key={index}>
                <Inlines items={block.inlines} />
              </p>
            );
        }
      })}
    </div>
  );
}
