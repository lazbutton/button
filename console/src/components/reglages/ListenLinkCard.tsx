import { Button, Spinner, Switch, Text, TextField } from "@radix-ui/themes";
import { useEffect, useState, type FormEvent } from "react";
import {
  ApiAuthError,
  ApiForbiddenError,
  ApiRequestError,
  ApiUnavailableError,
  apiGet,
  apiPut,
} from "../../api/client";
import { listenLinkBody, listenLinkChanged, listenLinkForm, type ListenLinkForm } from "../../api/listenLink";
import type { ListenLinkSettings } from "../../api/types";
import { FormField } from "../../ui/FormField";

type Loaded =
  | { status: "loading" }
  | { status: "ready"; settings: ListenLinkSettings }
  | { status: "outdated" }
  | { status: "failed"; message: string };

function failure(caught: unknown, fallback: string): string {
  if (caught instanceof ApiAuthError) return "Session expirée : reconnecte-toi.";
  if (caught instanceof ApiForbiddenError) return "Réservé à un admin. Reconnecte-toi avec ce compte.";
  if (caught instanceof ApiUnavailableError) return "L’automate ne répond pas. Réessaie dans un instant.";
  if (caught instanceof ApiRequestError) return caught.message;
  return fallback;
}

/**
 * Réglages → Station → « Fiches et liens » (FON-84), pour un admin : le service qui rend le lien
 * d'un titre vers la plateforme de chacun. Éteint par défaut. Sa propre sauvegarde : la clé
 * partenaire s'écrit, elle ne se relit jamais. Réglages → Fiches (FON-26) la reprendra.
 */
export function ListenLinkCard() {
  const [loaded, setLoaded] = useState<Loaded>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);
  const [form, setForm] = useState<ListenLinkForm | null>(null);
  const [busy, setBusy] = useState(false);
  const [fieldError, setFieldError] = useState<{ field: string; message: string } | null>(null);
  const [error, setError] = useState("");
  const [done, setDone] = useState("");

  useEffect(() => {
    let cancelled = false;
    setLoaded({ status: "loading" });
    apiGet<ListenLinkSettings>("/listen-link.json").then(
      (settings) => {
        if (cancelled) return;
        setLoaded({ status: "ready", settings });
        setForm(listenLinkForm(settings));
      },
      (caught: unknown) => {
        if (cancelled) return;
        // Un moteur plus ancien que la console n'a pas la route : la carte le dit.
        setLoaded(
          caught instanceof ApiRequestError && caught.status === 404
            ? { status: "outdated" }
            : { status: "failed", message: failure(caught, "Le lien d’écoute ne répond pas.") },
        );
      },
    );
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  useEffect(() => {
    if (fieldError) document.getElementById(`listen-link-${fieldError.field}`)?.focus();
  }, [fieldError]);

  const card = (children: React.ReactNode) => (
    <section className="reglages-card reglages-fieldset" aria-labelledby="listen-link-title">
      <h3 id="listen-link-title" className="reglages-card-title">
        Fiches et liens
      </h3>
      {children}
    </section>
  );

  if (loaded.status === "loading") return card(<p className="reglages-card-description">Lecture du réglage…</p>);
  if (loaded.status === "outdated") {
    return card(
      <p className="reglages-card-description" role="status">
        Mets à jour le moteur pour régler le lien d’écoute ici.
      </p>,
    );
  }
  if (loaded.status === "failed" || !form) {
    return card(
      <>
        <Text as="p" size="2" color="red" role="alert">
          {loaded.status === "failed" ? loaded.message : "Le lien d’écoute ne répond pas."}
        </Text>
        <div className="reglages-actions">
          <Button type="button" variant="soft" onClick={() => setAttempt((count) => count + 1)}>
            Réessayer
          </Button>
        </div>
      </>,
    );
  }

  const dirty = listenLinkChanged(form, loaded.settings);
  const keySet = loaded.settings.key_set;
  const edit = (patch: Partial<ListenLinkForm>) => {
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
      const settings = await apiPut<ListenLinkSettings>("/listen-link.json", listenLinkBody(form));
      setLoaded({ status: "ready", settings });
      setForm(listenLinkForm(settings));
      setDone(settings.enabled ? "Lien d’écoute enregistré, allumé." : "Lien d’écoute enregistré, éteint.");
    } catch (caught) {
      const field = caught instanceof ApiRequestError ? caught.field : undefined;
      if (field === "url" || field === "key") setFieldError({ field, message: failure(caught, "") });
      else setError(failure(caught, "Enregistrement impossible. Réessaie."));
    } finally {
      setBusy(false);
    }
  };

  return card(
    <form noValidate onSubmit={(event) => void submit(event)}>
      <p className="reglages-card-description">
        « Retrouver ce titre » : un auditeur ouvre le titre en cours sur sa plateforme d’un toucher. Allumé, la station
        envoie au service (Hopper) à l’adresse ci-dessous l’artiste et le titre qui passent à l’antenne, un titre de
        musique à la fois, et sa clé partenaire s’il y en a une. Rien d’autre ne part. Le lien n’est montré que si le
        service en est sûr. Une panne ou une réponse lente du service ne touche jamais l’antenne.
      </p>
      <div className="reglages-fields">
        <label className="reglages-switch-row">
          <span className="reglages-switch-copy">
            <span className="reglages-switch-title">Retrouver ce titre</span>
            <span className="reglages-switch-hint">Éteint, aucune demande ne part.</span>
          </span>
          <Switch checked={form.enabled} disabled={busy} onCheckedChange={(enabled) => edit({ enabled })} />
        </label>
        <FormField
          label="Adresse du service"
          htmlFor="listen-link-url"
          error={
            fieldError?.field === "url" ? (
              <Text size="1" color="red">
                {fieldError.message}
              </Text>
            ) : undefined
          }
        >
          <TextField.Root
            id="listen-link-url"
            className="ui-field-control"
            type="url"
            autoComplete="off"
            spellCheck={false}
            value={form.url}
            placeholder="https://liens.radio.example"
            aria-invalid={fieldError?.field === "url" || undefined}
            onChange={(event) => edit({ url: event.target.value })}
          />
        </FormField>
        <FormField
          label="Clé partenaire (facultative)"
          htmlFor="listen-link-key"
          error={
            fieldError?.field === "key" ? (
              <Text size="1" color="red">
                {fieldError.message}
              </Text>
            ) : undefined
          }
        >
          <TextField.Root
            id="listen-link-key"
            className="ui-field-control"
            type="password"
            autoComplete="new-password"
            spellCheck={false}
            value={form.key}
            disabled={form.clearKey}
            placeholder={keySet ? "Une clé est posée. Saisir pour la remplacer." : "Aucune clé"}
            aria-invalid={fieldError?.field === "key" || undefined}
            onChange={(event) => edit({ key: event.target.value })}
          />
        </FormField>
        {keySet ? (
          <label className="reglages-switch-row">
            <span className="reglages-switch-copy">
              <span className="reglages-switch-title">Effacer la clé posée</span>
              <span className="reglages-switch-hint">La clé ne se relit jamais : on la remplace ou on l’efface.</span>
            </span>
            <Switch
              checked={form.clearKey}
              disabled={busy}
              onCheckedChange={(clearKey) => edit({ clearKey, key: clearKey ? "" : form.key })}
            />
          </label>
        ) : null}
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
            Enregistrer
          </Button>
        </div>
      </div>
    </form>,
  );
}
