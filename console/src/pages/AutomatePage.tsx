import { Button } from "@radix-ui/themes";
import { RefreshCw } from "lucide-react";
import { useState } from "react";
import { HealthStrip } from "../components/antenne/HealthStrip";
import { ProtoToast, useProtoToast } from "../components/ProtoToast";
import {
  ANTENNE_FLUSH_JSON,
  ANTENNE_STATE_JSON,
  derivePillars,
  formatDuration,
  incidentLabel,
  sourceLabelFr,
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
import { SessionGate } from "../api/SessionGate";
import type { AntenneState, LiveSnapshot } from "../api/types";
import { useApiJson } from "../api/useApiJson";
import { ConfirmDialog } from "../ui/ConfirmDialog";
import { Panel, SectionHeader } from "../ui/Panel";

const REBUILD_JSON = "/autodj/conducteur.json?horizon=30";

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
    <div className="automate-page">
      <Panel>
        <SectionHeader
          title="Santé"
          description="Les six pastilles de l’antenne. Ouvre une pastille pour le détail."
        />
        <SessionGate
          loading={antenne.loading && state == null}
          error={antenne.error}
          ready={state != null}
          onRetry={() => void antenne.reload()}
        >
          <HealthStrip pillars={pillars} stale={stale} updatedAt={updatedAt} />
        </SessionGate>
      </Panel>

      <Panel>
        <SectionHeader
          title="Dépannage"
          description="Un seul endroit. Le titre en cours finit. L’horloge reprend ensuite."
        />
        <div className="automate-actions">
          <Button variant="soft" color="gray" disabled={busy != null} onClick={() => void reload()}>
            <RefreshCw className="ui-button-icon" />
            {busy === "reload" ? "Rechargement…" : "Recharger l’état"}
          </Button>
          <ConfirmDialog
            title="Vider les files ?"
            description="Les prochains titres déjà envoyés sont retirés. L’horloge les repousse au tick d’après. Le titre en cours finit."
            confirmLabel="Vider les files"
            busy={busy === "flush"}
            onConfirm={flush}
            trigger={
              <Button variant="soft" color="gray" disabled={busy != null}>
                Vider les files
              </Button>
            }
          />
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
        </div>
      </Panel>

      <Panel>
        <SectionHeader title="Statut" description="Le flux, le moteur, les sorties." />
        <StatusBody state={state} live={live.data} />
      </Panel>
      <ProtoToast message={message} />
    </div>
  );
}

function StatusBody({
  state,
  live,
}: {
  state: AntenneState | null;
  live: LiveSnapshot | null;
}) {
  if (!state) return <p>État antenne indisponible.</p>;
  const { playout, engine, listeners, incidents } = state;
  return (
    <div className="automate-status">
      <section>
        <h3>Flux</h3>
        <dl>
          <dt>Source</dt>
          <dd>{sourceLabelFr(playout.source || live?.source)}</dd>
          <dt>Playout</dt>
          <dd>{playout.reachable ? "joignable" : "injoignable"}</dd>
          <dt>Silence</dt>
          <dd>{playout.silence_s != null ? `${playout.silence_s.toFixed(1)} s` : "—"}</dd>
          <dt>Niveau</dt>
          <dd>{playout.rms_db != null ? `${Math.round(playout.rms_db)} dB` : "—"}</dd>
        </dl>
      </section>
      <section>
        <h3>Moteur</h3>
        <dl>
          <dt>Battement</dt>
          <dd>
            {engine.heartbeat_age_s == null ? "jamais" : `${engine.heartbeat_age_s.toFixed(1)} s`}
          </dd>
          <dt>Base</dt>
          <dd>{engine.db_ok ? "OK" : "KO"}</dd>
          <dt>Lien playout</dt>
          <dd>{engine.playout_connected ? "connecté" : "déconnecté"}</dd>
        </dl>
      </section>
      <section>
        <h3>Sorties</h3>
        {listeners.length === 0 ? (
          <p>Aucune sortie déclarée.</p>
        ) : (
          <ul>
            {listeners.map((row) => (
              <li key={`${row.host}${row.mount}`}>
                {row.target || row.host}
                {row.mount ? ` ${row.mount}` : ""}
                {" · "}
                {row.connected ? "branchée" : "débranchée"}
                {row.listeners != null ? ` · ${row.listeners} auditeur${row.listeners === 1 ? "" : "s"}` : ""}
              </li>
            ))}
          </ul>
        )}
      </section>
      <section>
        <h3>Incidents</h3>
        {incidents.length === 0 ? (
          <p>Aucun incident ouvert.</p>
        ) : (
          <ul>
            {incidents.map((incident) => (
              <li key={incident.kind}>
                {incidentLabel(incident)} — {incident.detail} (depuis {formatDuration(incident.since_s)})
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
