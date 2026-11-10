import { Button } from "@radix-ui/themes";
import { CircleAlert, CircleCheck, CircleHelp, CircleX, RefreshCw, type LucideIcon } from "lucide-react";
import { useState, type ReactNode } from "react";
import { HealthStrip } from "../components/antenne/HealthStrip";
import { ProtoToast, useProtoToast } from "../components/ProtoToast";
import { SettingsCard, SettingsHead } from "../components/reglages/SettingsCard";
import {
  ANTENNE_FLUSH_JSON,
  ANTENNE_STATE_JSON,
  derivePillars,
  formatDuration,
  incidentLabel,
  sourceLabelFr,
  type PillarTone,
} from "../api/antenneState";
import {
  ApiAuthError,
  ApiForbiddenError,
  ApiRequestError,
  ApiUnavailableError,
  apiPost,
  apiPostJson,
} from "../api/client";
import { harborIsLive } from "../api/emissionMeta";
import { automateSummary } from "../api/reglages";
import { SessionGate } from "../api/SessionGate";
import type { AntenneState, LiveSnapshot } from "../api/types";
import { useApiJson } from "../api/useApiJson";
import { ConfirmDialog } from "../ui/ConfirmDialog";
import "../styles/pages/reglages.css";

const REBUILD_JSON = "/autodj/conducteur.json?horizon=30";

const SUMMARY_ICON: Record<PillarTone, LucideIcon> = {
  ok: CircleCheck,
  warn: CircleAlert,
  alert: CircleX,
  off: CircleHelp,
};

/** Réglages → Automate, pour un admin : l'état de l'antenne en une phrase, son détail, puis le dépannage. */
export function AutomatePage() {
  const antenne = useApiJson<AntenneState>(ANTENNE_STATE_JSON, 5000);
  const live = useApiJson<LiveSnapshot>("/live.json", 5000);
  const { message, show } = useProtoToast();
  const [busy, setBusy] = useState<"reload" | "flush" | "reset" | "prune" | null>(null);
  const state = antenne.data;
  const pillars = derivePillars(state, harborIsLive(live.data));
  const stale =
    state == null ||
    !Number.isFinite(Date.parse(state.at)) ||
    Date.now() - Date.parse(state.at) > 20_000;
  const updatedAt = state ? state.at.slice(11, 16) : null;
  const summary = automateSummary(pillars, stale, updatedAt);
  const SummaryIcon = SUMMARY_ICON[summary.tone];

  // Un échec s'annonce en alerte : deviné d'après le texte, le ton ferait
  // passer un refus ou un moteur muet pour une information.
  const fail = (caught: unknown, fallback: string) => {
    if (caught instanceof ApiAuthError) show("Session expirée. Reconnecte-toi.", "error");
    else if (caught instanceof ApiForbiddenError) show("Réservé à un admin. Reconnecte-toi avec ce compte.", "error");
    else if (caught instanceof ApiRequestError) show(caught.message, "error");
    else if (caught instanceof ApiUnavailableError) show("L’automate ne répond pas. Réessaie dans un instant.", "error");
    else show(fallback, "error");
  };

  const reload = async () => {
    setBusy("reload");
    try {
      await Promise.all([antenne.reload(), live.reload()]);
      show("État rechargé");
    } catch (caught) {
      fail(caught, "Rechargement impossible.");
    } finally {
      setBusy(null);
    }
  };

  const flush = async () => {
    setBusy("flush");
    try {
      await apiPost(ANTENNE_FLUSH_JSON);
      await antenne.reload();
      show("Files vidées");
    } catch (caught) {
      fail(caught, "Vidage impossible.");
    } finally {
      setBusy(null);
    }
  };

  const reset = async () => {
    setBusy("reset");
    try {
      await apiPostJson(REBUILD_JSON, { reset: true });
      await antenne.reload();
      show("Conducteur reconstruit");
    } catch (caught) {
      fail(caught, "Reconstruction impossible.");
    } finally {
      setBusy(null);
    }
  };

  const prune = async () => {
    setBusy("prune");
    try {
      const response = await fetch("/library/prune", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: "{}",
      });
      const payload = (await response.json().catch(() => ({}))) as {
        error?: string;
        removed?: number;
      };
      if (response.status === 401) {
        show("Session expirée. Reconnecte-toi.", "error");
        return;
      }
      if (response.status === 403) {
        show("Réservé à un admin. Reconnecte-toi avec ce compte.", "error");
        return;
      }
      if (!response.ok) {
        show(payload.error?.trim() || "Retrait impossible.", "error");
        return;
      }
      const removed = Number(payload.removed) || 0;
      show(removed > 0 ? `${removed} titres retirés de la bibliothèque` : "Aucun titre hors bac.");
    } catch {
      show("Le catalogue ne répond pas. Réessaie dans un instant.", "error");
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="reglages-section">
      <SettingsHead
        title="Automate"
        description="L’état de l’antenne en une phrase, son détail, puis les gestes de dépannage."
        actions={
          <Button variant="soft" color="gray" disabled={busy != null} onClick={() => void reload()}>
            <RefreshCw className="ui-button-icon" aria-hidden="true" />
            {busy === "reload" ? "Rechargement…" : "Recharger l’état"}
          </Button>
        }
      />
      <div className="reglages-stack">
        <SessionGate
          loading={antenne.loading && state == null}
          error={antenne.error}
          ready={state != null}
          onRetry={() => void antenne.reload()}
        >
          <section className={`reglages-card reglages-summary tone-${summary.tone}`}>
            <span className="reglages-summary-icon" aria-hidden="true">
              <SummaryIcon />
            </span>
            <div className="reglages-summary-copy">
              <h3 className="reglages-summary-title">{summary.title}</h3>
              <p className="reglages-summary-detail">{summary.detail}</p>
            </div>
            <div className="reglages-summary-health">
              <p className="reglages-note">Les six pastilles de l’antenne. Ouvre une pastille pour le détail.</p>
              <HealthStrip pillars={pillars} stale={stale} updatedAt={updatedAt} />
            </div>
          </section>
          {state ? <StatusCards state={state} live={live.data} /> : null}
        </SessionGate>

        <SettingsCard title="Dépannage" description="Le titre en cours finit toujours. L’horloge reprend ensuite.">
          <ul className="reglages-gestures">
            <Gesture
              title="Les files"
              text="Les prochains titres déjà envoyés au playout. Vidées, le conducteur les marque sautés, et l’horloge passe aux lignes suivantes. Un bac lancé s’arrête."
            >
              <ConfirmDialog
                title="Vider les files ?"
                description="Les prochains titres déjà envoyés sont retirés : le conducteur les marque sautés. L’horloge passe aux lignes suivantes. Un bac lancé s’arrête. Le titre en cours finit."
                confirmLabel="Vider les files"
                busy={busy === "flush"}
                onConfirm={flush}
                trigger={
                  <Button variant="soft" color="gray" disabled={busy != null}>
                    Vider les files
                  </Button>
                }
              />
            </Gesture>
          </ul>
        </SettingsCard>

        <SettingsCard
          tone="danger"
          title="Gestes lourds"
          description="Ils ne se défont pas. Chacun demande une confirmation."
        >
          <ul className="reglages-gestures">
            <Gesture
              title="Le conducteur"
              text="Les items planifiés sont jetés et reprévus depuis maintenant. Les files sont vidées aussi."
            >
              <ConfirmDialog
                title="Reconstruire le conducteur ?"
                description="Les items planifiés sont jetés et reprévus depuis maintenant. Les files sont vidées. Le titre en cours finit."
                confirmLabel="Reconstruire"
                busy={busy === "reset"}
                onConfirm={reset}
                trigger={
                  <Button variant="soft" color="red" disabled={busy != null}>
                    Reconstruire le conducteur
                  </Button>
                }
              />
            </Gesture>
            <Gesture
              title="La bibliothèque"
              text="Les titres qui ne sont dans aucun bac en sont retirés. Les fichiers restent sur le disque. Ensuite, la recherche ne garde que les sons des bacs."
            >
              <ConfirmDialog
                title="Retirer les titres hors bacs ?"
                description="La bibliothèque retire les titres qui ne sont dans aucun bac. Les fichiers restent sur le disque. Ensuite, la recherche ne garde que les sons des bacs."
                confirmLabel="Retirer"
                busy={busy === "prune"}
                onConfirm={prune}
                trigger={
                  <Button variant="soft" color="red" disabled={busy != null}>
                    Retirer les titres hors bacs
                  </Button>
                }
              />
            </Gesture>
          </ul>
        </SettingsCard>
      </div>
      <ProtoToast message={message} />
    </div>
  );
}

/** Un geste de dépannage : ce qu'il touche, ce qu'il fait, puis son bouton. */
function Gesture({ title, text, children }: { title: string; text: string; children: ReactNode }) {
  return (
    <li className="reglages-gesture">
      <div className="reglages-gesture-copy">
        <p className="reglages-gesture-title">{title}</p>
        <p className="reglages-gesture-text">{text}</p>
      </div>
      <div className="reglages-gesture-action">{children}</div>
    </li>
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

function StatusCards({ state, live }: { state: AntenneState; live: LiveSnapshot | null }) {
  const { playout, engine, listeners, incidents } = state;
  return (
    <div className="reglages-grid">
      <SettingsCard title="Flux">
        <dl className="reglages-facts">
          <Fact label="Source">{sourceLabelFr(playout.source || live?.source)}</Fact>
          <Fact label="Playout">{playout.reachable ? "joignable" : "injoignable"}</Fact>
          <Fact label="Silence">{playout.silence_s != null ? `${playout.silence_s.toFixed(1)} s` : "—"}</Fact>
          <Fact label="Niveau">{playout.rms_db != null ? `${Math.round(playout.rms_db)} dB` : "—"}</Fact>
        </dl>
      </SettingsCard>
      <SettingsCard title="Moteur">
        <dl className="reglages-facts">
          <Fact label="Battement">
            {engine.heartbeat_age_s == null ? "jamais" : `${engine.heartbeat_age_s.toFixed(1)} s`}
          </Fact>
          <Fact label="Base">{engine.db_ok ? "OK" : "KO"}</Fact>
          <Fact label="Lien playout">{engine.playout_connected ? "connecté" : "déconnecté"}</Fact>
        </dl>
      </SettingsCard>
      <SettingsCard title="Sorties">
        {listeners.length === 0 ? (
          <p className="reglages-empty">Aucune sortie déclarée.</p>
        ) : (
          <ul className="reglages-list reglages-list--stacked">
            {listeners.map((row) => (
              <li key={`${row.host}${row.mount}`}>
                <span className="reglages-list-what">
                  {row.target || `${row.host}${row.mount ? `/${row.mount}` : ""}`}
                </span>{" "}
                <span className="reglages-list-when">
                  {row.connected ? "branchée" : "débranchée"}
                  {row.listeners != null ? ` · ${row.listeners} auditeur${row.listeners === 1 ? "" : "s"}` : ""}
                </span>
              </li>
            ))}
          </ul>
        )}
      </SettingsCard>
      <SettingsCard title="Incidents">
        {incidents.length === 0 ? (
          <p className="reglages-empty">Aucun incident ouvert.</p>
        ) : (
          <ul className="reglages-list reglages-list--stacked">
            {incidents.map((incident) => (
              <li key={incident.kind}>
                <span className="reglages-list-what">{incidentLabel(incident)}</span>{" "}
                <span className="reglages-list-when">
                  {incident.detail} · depuis {formatDuration(incident.since_s)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </SettingsCard>
    </div>
  );
}
