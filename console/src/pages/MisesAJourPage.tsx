import { Button } from "@radix-ui/themes";
import { ChevronRight, CircleAlert, CircleCheck, CircleHelp, CircleX, RefreshCw, type LucideIcon } from "lucide-react";
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
  requestLine,
  splitNotes,
  unreachableLine,
  versionLine,
  withCommands,
  type Inline,
  type Line,
  type NoteBlock,
  type Tone,
  type UpdateRelease,
  type UpdatesState,
} from "../api/updates";
import { SettingsCard, SettingsHead } from "../components/reglages/SettingsCard";
import { AppToast, useAppToast } from "../ui/AppToast";
import { ConfirmDialog } from "../ui/ConfirmDialog";
import { LoadingState } from "../ui/DataState";
import "../styles/pages/reglages.css";

const ICON: Record<Tone, LucideIcon> = {
  ok: CircleCheck,
  warn: CircleAlert,
  alert: CircleX,
  off: CircleHelp,
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
 * Réglages → Mises à jour, pour un admin : la version de la station et la plus
 * haute publiée, ses notes, la demande en cours et la dernière, et « Mettre à
 * jour maintenant ». La console ne touche jamais la machine : le bouton écrit
 * une demande dans le moteur, et la machine la prend dans la minute.
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
        description={
          <Said text="La version de la station, la plus haute publiée, et la mise à jour, d’un bouton. La machine la fait elle-même, dans la minute, comme sudo station update : une sauvegarde d’abord, et si la nouvelle version ne repart pas, la station revient seule à la sienne." />
        }
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
  changed,
  busy,
  confirming,
  onConfirming,
  onAsk,
  onWithdraw,
}: {
  state: UpdatesState;
  unreachable: boolean;
  changed: boolean;
  busy: "ask" | "withdraw" | "check" | null;
  confirming: boolean;
  onConfirming: (open: boolean) => void;
  onAsk: () => Promise<void>;
  onWithdraw: () => Promise<void>;
}) {
  // « aujourd’hui », « hier » : relus à chaque lecture de la page, au moins une fois la minute.
  const now = new Date();
  const version = versionLine(state, now);
  // Une demande ouverte a sa carte ; « À jour » se dit déjà dans le titre.
  const blocked = state.blocked && !["open", "up_to_date"].includes(state.blocked.code) ? state.blocked : null;
  return (
    <>
      {unreachable ? <Summary line={unreachableLine(state)} live /> : null}
      {changed && !unreachable ? (
        <section className="reglages-card reglages-notice" role="status">
          <p>
            La station est passée en {state.installed ?? "?"} depuis l’ouverture de cette page : la console en service
            a peut-être changé aussi. Recharge la page pour la prendre.
          </p>
          <div>
            <Button variant="soft" onClick={() => window.location.reload()}>
              Recharger la page
            </Button>
          </div>
        </section>
      ) : null}

      <Summary line={version}>
        {state.request ? null : blocked ? (
          <p className="reglages-updates-blocked">
            <Said text={blocked.message} />
          </p>
        ) : (
          <ConfirmDialog
            open={confirming}
            onOpenChange={onConfirming}
            title={`Mettre la station à jour, en ${state.latest} ?`}
            description={`La station passe de ${state.installed} à ${state.latest}. La machine prend la demande dans la minute : une sauvegarde d’abord, puis les images, pendant que l’antenne joue, puis le redémarrage, qui coupe l’antenne quelques secondes. Elle attend la fin d’un direct ou d’une diffusion de l’Agenda. Si la ${state.latest} ne repart pas, la station revient seule à la ${state.installed}.`}
            confirmLabel="Mettre à jour"
            busy={busy === "ask"}
            onConfirm={onAsk}
            trigger={
              <Button disabled={busy != null || unreachable} highContrast>
                Mettre à jour maintenant
              </Button>
            }
          />
        )}
      </Summary>

      {state.request ? (
        <Summary line={requestLine(state.request, now)} live>
          {state.request.state === "pending" ? (
            <Button variant="soft" color="gray" disabled={busy != null || unreachable} onClick={() => void onWithdraw()}>
              {busy === "withdraw" ? "Retrait…" : "Retirer la demande"}
            </Button>
          ) : null}
        </Summary>
      ) : null}

      {!state.request && state.last ? (
        <Summary line={lastLine(state.last, now)} heading="La dernière demande" live />
      ) : null}

      {state.host?.hold ? (
        <SettingsCard
          title="Bloquées sur la machine"
          description={
            <Said text="HOLD bloque toute mise à jour, d’ici comme de la machine. Pour les débloquer, une fois la cause trouvée, sur la machine : sudo station unhold." />
          }
        >
          <pre className="reglages-updates-hold">{state.host.hold}</pre>
        </SettingsCard>
      ) : null}

      {state.major ? (
        <SettingsCard
          title={`La ${state.major.version} : une version majeure`}
          description={
            <Said text="Elle demande une action à la station avant de la prendre : elle ne part pas de la console. Une fois l’action faite, sur la machine : sudo station update --major." />
          }
        >
          <Notes text={state.major.action} empty="Ses notes ne se lisent pas ici." />
          <p className="reglages-note">
            <a href={state.major.url} target="_blank" rel="noreferrer">
              Les notes de la {state.major.version}, sur GitHub
            </a>
          </p>
        </SettingsCard>
      ) : null}

      <SettingsCard title="Notes de version" description={notesIntro(state.releases)}>
        {state.releases.length ? (
          <div className="reglages-updates-releases">
            {state.releases.map((release) => (
              <Release key={release.version} release={release} now={now} />
            ))}
          </div>
        ) : null}
      </SettingsCard>

      <SettingsCard
        title="Les dernières mises à jour"
        description="Celles de la console comme celles de la machine, d’après updates.log."
      >
        {state.history.length ? (
          <ul className="reglages-updates-history">
            {state.history.map((entry) => {
              const line = historyLine(entry, now);
              const Icon = ICON[line.tone];
              return (
                <li key={`${entry.started_at}-${entry.from}-${entry.to}`} className={`tone-${line.tone}`}>
                  <span className="reglages-updates-history-icon" aria-hidden="true">
                    <Icon />
                  </span>
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
          <a href={release.url} target="_blank" rel="noreferrer">
            La {release.version} sur GitHub
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

/** Un état en une phrase, avec son icône, puis ce qu'on peut y faire. `live` : un lecteur d'écran l'entend changer. */
function Summary({
  line,
  heading,
  live = false,
  children,
}: {
  line: Line;
  heading?: string;
  live?: boolean;
  children?: ReactNode;
}) {
  const Icon = ICON[line.tone];
  return (
    <section className={`reglages-card reglages-summary tone-${line.tone}`}>
      <span className="reglages-summary-icon" aria-hidden="true">
        <Icon />
      </span>
      <div className="reglages-summary-copy" role={live ? "status" : undefined}>
        {heading ? <p className="reglages-updates-kicker">{heading}</p> : null}
        <h3 className="reglages-summary-title">{line.title}</h3>
        <p className="reglages-summary-detail">
          <Said text={line.detail} />
        </p>
      </div>
      {children ? <div className="reglages-updates-action">{children}</div> : null}
    </section>
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
