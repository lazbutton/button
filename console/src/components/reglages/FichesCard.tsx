import { Button, Spinner, Switch, Text, TextField } from "@radix-ui/themes";
import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import {
  ApiAuthError,
  ApiForbiddenError,
  ApiRequestError,
  ApiUnavailableError,
  apiGet,
  apiPut,
} from "../../api/client";
import {
  FICHES_SETTINGS_JSON,
  settingsBody,
  settingsChanged,
  settingsForm,
  type FichesSettings,
  type FichesSettingsForm,
} from "../../api/fiches";
import { FormField } from "../../ui/FormField";

type Loaded =
  | { status: "loading" }
  | { status: "ready"; settings: FichesSettings }
  | { status: "outdated" }
  | { status: "failed"; message: string };

// Les champs que le moteur peut refuser, et l'identifiant de leur saisie.
const KEY_FIELDS = ["acoustid_key", "tidal_client_id", "tidal_client_secret"] as const;

function failure(caught: unknown, fallback: string): string {
  if (caught instanceof ApiAuthError) return "Session expirée : reconnecte-toi.";
  if (caught instanceof ApiForbiddenError) return "Réservé à un admin. Reconnecte-toi avec ce compte.";
  if (caught instanceof ApiUnavailableError) return "L’automate ne répond pas. Réessaie dans un instant.";
  if (caught instanceof ApiRequestError) return caught.message;
  return fallback;
}

/**
 * Réglages → Fiches (FON-26), pour un admin : la recherche des fiches en ligne, le
 * verdict, la clé AcoustID de la station, les sources de FON-30 et ce qui part de
 * la station. Une clé s'écrit, elle ne se relit jamais.
 */
export function FichesCard() {
  const [loaded, setLoaded] = useState<Loaded>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);
  const [form, setForm] = useState<FichesSettingsForm | null>(null);
  const [busy, setBusy] = useState(false);
  const [fieldError, setFieldError] = useState<{ field: string; message: string } | null>(null);
  const [error, setError] = useState("");
  const [done, setDone] = useState("");

  useEffect(() => {
    let cancelled = false;
    setLoaded({ status: "loading" });
    apiGet<FichesSettings>(FICHES_SETTINGS_JSON).then(
      (settings) => {
        if (cancelled) return;
        setLoaded({ status: "ready", settings });
        setForm(settingsForm(settings));
      },
      (caught: unknown) => {
        if (cancelled) return;
        // Un moteur plus ancien que la console n'a pas la route : la carte le dit.
        setLoaded(
          caught instanceof ApiRequestError && caught.status === 404
            ? { status: "outdated" }
            : { status: "failed", message: failure(caught, "Les réglages des fiches ne répondent pas.") },
        );
      },
    );
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  useEffect(() => {
    if (fieldError) document.getElementById(`fiches-${fieldError.field}`)?.focus();
  }, [fieldError]);

  const card = (children: ReactNode) => (
    <section className="reglages-card reglages-fieldset" aria-labelledby="fiches-title">
      <h3 id="fiches-title" className="reglages-card-title">
        Recherche des fiches
      </h3>
      {children}
    </section>
  );

  if (loaded.status === "loading") return card(<p className="reglages-card-description">Lecture du réglage…</p>);
  if (loaded.status === "outdated") {
    return card(
      <p className="reglages-card-description" role="status">
        Mets à jour le moteur pour régler la recherche des fiches ici.
      </p>,
    );
  }
  if (loaded.status === "failed" || !form) {
    return card(
      <>
        <Text as="p" size="2" color="red" role="alert">
          {loaded.status === "failed" ? loaded.message : "Les réglages des fiches ne répondent pas."}
        </Text>
        <div className="reglages-actions">
          <Button type="button" variant="soft" onClick={() => setAttempt((count) => count + 1)}>
            Réessayer
          </Button>
        </div>
      </>,
    );
  }

  const { settings } = loaded;
  const dirty = settingsChanged(form, settings);
  const edit = (patch: Partial<FichesSettingsForm>) => {
    setForm((current) => (current ? { ...current, ...patch } : current));
    setDone("");
    setFieldError(null);
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError("");
    setDone("");
    setFieldError(null);
    try {
      const saved = await apiPut<FichesSettings>(FICHES_SETTINGS_JSON, settingsBody(form));
      setLoaded({ status: "ready", settings: saved });
      setForm(settingsForm(saved));
      setDone(
        saved.enabled
          ? "Réglages des fiches enregistrés, recherche allumée."
          : "Réglages des fiches enregistrés, recherche éteinte.",
      );
    } catch (caught) {
      const field = caught instanceof ApiRequestError ? caught.field : undefined;
      if (field && (KEY_FIELDS as readonly string[]).includes(field)) {
        setFieldError({ field, message: failure(caught, "") });
      } else {
        setError(failure(caught, "Enregistrement impossible. Réessaie."));
      }
    } finally {
      setBusy(false);
    }
  };

  const fieldMessage = (field: string) =>
    fieldError?.field === field ? (
      <Text size="1" color="red">
        {fieldError.message}
      </Text>
    ) : undefined;

  const toggle = (title: string, hint: string, checked: boolean, change: (value: boolean) => void) => (
    <label className="reglages-switch-row">
      <span className="reglages-switch-copy">
        <span className="reglages-switch-title">{title}</span>
        <span className="reglages-switch-hint">{hint}</span>
      </span>
      <Switch checked={checked} disabled={busy} onCheckedChange={change} />
    </label>
  );

  return card(
    <form noValidate onSubmit={(event) => void submit(event)}>
      <p className="reglages-card-description">
        La station cherche en ligne, un titre à la fois, ce qui manque ou ce qui est faux dans les tags de la banque.
        Elle propose, une personne relit dans Sons → Banque → À relire : rien ne s’écrit seul. Une panne d’un service
        ralentit la recherche, elle ne touche jamais l’antenne.
      </p>
      <p className="reglages-card-description">
        <strong>Ce qui part de la station :</strong> {settings.sent}
      </p>
      <div className="reglages-fields">
        {toggle("Chercher les fiches en ligne", "Éteint, aucune demande ne part.", form.enabled, (enabled) =>
          edit({ enabled }),
        )}
        {toggle(
          "Verdict « femme ou minorité de genre »",
          "D’après ce que MusicBrainz et Wikidata déclarent, jamais un prénom ni une voix. Éteint, aucune requête sur les personnes.",
          form.verdict,
          (verdict) => edit({ verdict }),
        )}
        <FormField
          label="Clé AcoustID de la station (facultative)"
          htmlFor="fiches-acoustid_key"
          error={fieldMessage("acoustid_key")}
        >
          <TextField.Root
            id="fiches-acoustid_key"
            className="ui-field-control"
            type="password"
            autoComplete="new-password"
            spellCheck={false}
            value={form.acoustid_key}
            disabled={form.clearAcoustid}
            placeholder={
              settings.acoustid_key_set ? "Une clé est posée. Saisir pour la remplacer." : "Sans clé, celle de BUTTON"
            }
            aria-invalid={fieldError?.field === "acoustid_key" || undefined}
            onChange={(event) => edit({ acoustid_key: event.target.value })}
          />
        </FormField>
        {settings.acoustid_key_set
          ? toggle(
              "Effacer la clé AcoustID posée",
              "La clé de BUTTON reprend sa place. Une clé ne se relit jamais : on la remplace ou on l’efface.",
              form.clearAcoustid,
              (clearAcoustid) => edit({ clearAcoustid, acoustid_key: clearAcoustid ? "" : form.acoustid_key }),
            )
          : null}
      </div>

      <h4 className="reglages-card-subtitle">Sources de plus</h4>
      <p className="reglages-card-description">
        Éteintes par défaut. Allumée, une source reçoit l’artiste et le titre, rien d’autre.
      </p>
      <div className="reglages-fields">
        {toggle(
          "Tidal",
          settings.sources.tidal_key_set
            ? "La clé d’application de la station est posée."
            : "Demande la clé d’application de la station, ci-dessous.",
          form.tidal,
          (tidal) => edit({ tidal }),
        )}
        {toggle("Apple Music", "Sa recherche publique, sans clé.", form.apple_music, (apple_music) =>
          edit({ apple_music }),
        )}
        {toggle("Bandcamp", "Sa recherche publique, sans clé.", form.bandcamp, (bandcamp) => edit({ bandcamp }))}
      </div>
      <div className="reglages-fields">
        <FormField
          label="Identifiant d’application Tidal"
          htmlFor="fiches-tidal_client_id"
          error={fieldMessage("tidal_client_id")}
        >
          <TextField.Root
            id="fiches-tidal_client_id"
            className="ui-field-control"
            type="password"
            autoComplete="new-password"
            spellCheck={false}
            value={form.tidal_client_id}
            disabled={form.clearTidal}
            placeholder={settings.sources.tidal_key_set ? "Posé. Saisir pour le remplacer." : "Aucun"}
            aria-invalid={fieldError?.field === "tidal_client_id" || undefined}
            onChange={(event) => edit({ tidal_client_id: event.target.value })}
          />
        </FormField>
        <FormField
          label="Secret d’application Tidal"
          htmlFor="fiches-tidal_client_secret"
          error={fieldMessage("tidal_client_secret")}
        >
          <TextField.Root
            id="fiches-tidal_client_secret"
            className="ui-field-control"
            type="password"
            autoComplete="new-password"
            spellCheck={false}
            value={form.tidal_client_secret}
            disabled={form.clearTidal}
            placeholder={settings.sources.tidal_key_set ? "Posé. Saisir pour le remplacer." : "Aucun"}
            aria-invalid={fieldError?.field === "tidal_client_secret" || undefined}
            onChange={(event) => edit({ tidal_client_secret: event.target.value })}
          />
        </FormField>
        {settings.sources.tidal_key_set
          ? toggle(
              "Effacer la clé Tidal posée",
              "L’identifiant et le secret partent ensemble.",
              form.clearTidal,
              (clearTidal) =>
                edit({
                  clearTidal,
                  tidal_client_id: clearTidal ? "" : form.tidal_client_id,
                  tidal_client_secret: clearTidal ? "" : form.tidal_client_secret,
                }),
            )
          : null}
      </div>

      <div className={`reglages-savebar${dirty ? " is-dirty" : ""}`}>
        <div className="reglages-savebar-copy">
          {error ? (
            <Text as="p" size="2" color="red" role="alert">
              {error}
            </Text>
          ) : null}
          <p className="reglages-savebar-status" role="status">
            {done || (dirty ? "Modifications non enregistrées." : "")}
          </p>
        </div>
        <div className="reglages-actions">
          <Button type="submit" highContrast aria-busy={busy}>
            {busy ? <Spinner size="1" /> : null}
            Valider les fiches
          </Button>
        </div>
      </div>
    </form>,
  );
}
