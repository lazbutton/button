import { Button } from "@radix-ui/themes";
import { CircleAlert, CircleCheck, CircleHelp, CircleX, RefreshCw, type LucideIcon } from "lucide-react";
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
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
  formatWhen,
  historyLine,
  lastLine,
  nightlyLine,
  parseNotes,
  pollDelay,
  readFailureMessage,
  requestLine,
  unreachableLine,
  versionLine,
  type Inline,
  type Line,
  type Tone,
  type UpdatesState,
} from "../api/updates";
import { ProtoToast, useProtoToast } from "../components/ProtoToast";
import { SettingsCard, SettingsHead } from "../components/reglages/SettingsCard";
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
  const { message, show } = useProtoToast();
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
      fail(caught, "La demande ne part pas.");
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
      fail(caught, "La demande ne se retire pas.");
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
    else if (next.check.pending) show("GitHub répond lentement : la page se met à jour seule.");
    else show("Versions relues sur GitHub.");
  };

  if (problem?.kind === "auth" || (unreachable && state == null)) {
    return (
      <SessionGate loading={false} error={problem?.kind === "auth" ? "auth" : "down"} onRetry={() => void load()}>
        {null}
      </SessionGate>
    );
  }

  return (
    <div className="reglages-section">
      <SettingsHead
        title="Mises à jour"
        description="La version de la station, la plus haute publiée, et la mise à jour, d’un bouton. La machine la fait elle-même, dans la minute, comme sudo station update : une sauvegarde d’abord, et si la nouvelle version ne repart pas, la station revient seule à la sienne."
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
            <p>{problem.message}</p>
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
            Mets à jour le moteur pour avoir cette page : le sien ne connaît pas encore les mises à jour depuis la
            console. Sur la machine : sudo station update.
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
      <ProtoToast message={message} />
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
  const version = versionLine(state);
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
          <p className="reglages-updates-blocked">{blocked.message}</p>
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
        <Summary line={requestLine(state.request)} live>
          {state.request.state === "pending" ? (
            <Button variant="soft" color="gray" disabled={busy != null || unreachable} onClick={() => void onWithdraw()}>
              {busy === "withdraw" ? "Retrait…" : "Retirer la demande"}
            </Button>
          ) : null}
        </Summary>
      ) : null}

      {!state.request && state.last ? <Summary line={lastLine(state.last)} heading="La dernière demande" live /> : null}

      {state.host?.hold ? (
        <SettingsCard
          title="Bloquées sur la machine"
          description="HOLD bloque toute mise à jour, d’ici comme de la machine. Pour les débloquer, une fois la cause trouvée, sur la machine : sudo station unhold."
        >
          <pre className="reglages-updates-hold">{state.host.hold}</pre>
        </SettingsCard>
      ) : null}

      {state.major ? (
        <SettingsCard
          title={`La ${state.major.version} : une version majeure`}
          description="Elle demande une action à la station avant de la prendre : elle ne part pas de la console. Une fois l’action faite, sur la machine : sudo station update --major."
        >
          {state.major.action ? (
            <Notes text={state.major.action} />
          ) : (
            <p className="reglages-empty">Ses notes ne se lisent pas ici.</p>
          )}
          <p className="reglages-note">
            <a href={state.major.url} target="_blank" rel="noreferrer">
              Les notes de la {state.major.version}, sur GitHub
            </a>
          </p>
        </SettingsCard>
      ) : null}

      <SettingsCard
        title="Notes de version"
        description={
          state.releases.length
            ? "Ce que la mise à jour apporte, de la plus récente à la plus ancienne."
            : "Aucune version plus récente que celle de la station."
        }
      >
        {state.releases.length ? (
          <div className="reglages-updates-releases">
            {state.releases.map((release) => (
              <article key={release.version} className="reglages-updates-release">
                <h4>
                  {release.version}
                  {release.major ? " · majeure" : ""}
                  {release.published_at ? <span> · publiée le {formatWhen(release.published_at)}</span> : null}
                </h4>
                <Notes text={release.notes} />
                {release.url ? (
                  <p className="reglages-note">
                    <a href={release.url} target="_blank" rel="noreferrer">
                      La {release.version} sur GitHub
                    </a>
                  </p>
                ) : null}
              </article>
            ))}
          </div>
        ) : null}
      </SettingsCard>

      <SettingsCard
        title="Les dernières mises à jour"
        description="Celles de la console comme celles de la machine, d’après updates.log."
      >
        {state.history.length ? (
          <ul className="reglages-list">
            {state.history.map((entry) => {
              const line = historyLine(entry);
              return (
                <li key={`${entry.started_at}-${entry.from}-${entry.to}`}>
                  <span className="reglages-list-when">{line.when}</span>{" "}
                  <span className="reglages-list-what">{line.what}</span>
                </li>
              );
            })}
          </ul>
        ) : (
          <p className="reglages-empty">Aucune pour l’instant.</p>
        )}
      </SettingsCard>

      <SettingsCard title="Automatique, la nuit">
        <p className="reglages-empty">{nightlyLine(state.host)}</p>
      </SettingsCard>

      <SettingsCard title="La machine">
        <dl className="reglages-facts">
          <Fact label="Demandes de la console">
            {state.host == null ? "pas encore prises" : state.host.requests ? "prises chaque minute" : "coupées"}
          </Fact>
          <Fact label="Nouvelles de la machine">
            {state.host?.seen_at ? `le ${formatWhen(state.host.seen_at)}` : "aucune"}
          </Fact>
          <Fact label="Commande station">{state.host?.command ?? "inconnue"}</Fact>
        </dl>
        {state.services.length ? (
          <details className="reglages-updates-services">
            <summary>
              La version de chaque service
              {state.recorded_at ? `, relevée le ${formatWhen(state.recorded_at)}` : ""}
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
        <p className="reglages-summary-detail">{line.detail}</p>
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

function Inlines({ items }: { items: Inline[] }) {
  return (
    <>
      {items.map((item, index) => {
        switch (item.kind) {
          case "strong":
            return <strong key={index}>{item.text}</strong>;
          case "code":
            return <code key={index}>{item.text}</code>;
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

/** Les notes d'une version : un peu de Markdown, rendu sans HTML. */
function Notes({ text }: { text: string | null }) {
  const blocks = parseNotes(text);
  if (!blocks.length) return <p className="reglages-empty">Pas de notes.</p>;
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
