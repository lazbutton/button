import { Button, Spinner, Text, TextField } from "@radix-ui/themes";
import { useEffect, useState, type FormEvent } from "react";
import {
  ApiAuthError,
  ApiForbiddenError,
  ApiRequestError,
  ApiUnavailableError,
  apiGet,
  apiPut,
} from "../api/client";
import {
  harborAddress,
  publicStation,
  STATION_FIELDS,
  stationBody,
  stationForm,
  type StationField,
  type StationForm,
} from "../api/station";
import type { StationSettings } from "../api/types";
import { DEFAULT_SOURCE_URL, type Brand } from "../lib/brand";
import { useStationBinding } from "../lib/BrandContext";
import { monitorSources } from "../lib/monitorSource";
import { LoadingState } from "../ui/DataState";
import { FormField } from "../ui/FormField";
import { Panel, SectionHeader } from "../ui/Panel";
import "../styles/pages/admin.css";

type Loaded =
  | { status: "loading" }
  | { status: "ready"; settings: StationSettings }
  | { status: "outdated" }
  | { status: "failed"; message: string };

type FieldSpec = { key: StationField; label: string; kind?: "url" | "port" };

const GROUPS: { legend: string; description: string; fields: FieldSpec[] }[] = [
  {
    legend: "Identité",
    description:
      "Le nom s’affiche en haut de la console, à la connexion et sur la page d’un invité. La langue, comme fr-FR, sert aux pages des auditeurs : la console reste en français.",
    fields: [
      { key: "name", label: "Nom" },
      { key: "short", label: "Nom court" },
      { key: "tagline", label: "Accroche" },
      { key: "locale", label: "Langue" },
    ],
  },
  {
    legend: "Écoute",
    description: "Les adresses publiques, celles de l’auditeur. Le casque de la console écoute le même flux.",
    fields: [
      { key: "public_stream_url", label: "Flux public", kind: "url" },
      { key: "now_url", label: "Titre en cours (now.json)", kind: "url" },
      { key: "status_url", label: "Statut d’Icecast (status-json.xsl)", kind: "url" },
    ],
  },
  {
    legend: "Direct",
    description:
      "L’hôte, le port et le mount que vise l’encodeur, BUTT ou Mixxx. Pour l’instant, le panneau « Passer en direct » montre toujours ceux de l’image : les valeurs grisées.",
    fields: [
      { key: "harbor_host", label: "Hôte" },
      { key: "harbor_port", label: "Port", kind: "port" },
      { key: "harbor_mount", label: "Mount" },
    ],
  },
  {
    legend: "Code source",
    description: "Le lien « Code source » du menu du compte, sous licence AGPL. À changer pour une version modifiée.",
    fields: [{ key: "source_url", label: "Lien du code source", kind: "url" }],
  },
];

function isField(name: string | undefined): name is StationField {
  return (STATION_FIELDS as readonly string[]).includes(name ?? "");
}

/** Ce que la console garde quand un champ reste vide : la valeur de son image. */
function fallbacks(brand: Brand): Partial<StationForm> {
  const [listen] = monitorSources(brand);
  const harbor = harborAddress(brand);
  return {
    name: brand.suite.name,
    short: brand.suite.short,
    tagline: brand.suite.tagline,
    public_stream_url: listen?.stream,
    now_url: listen?.nowUrl,
    status_url: listen?.statusUrl,
    harbor_host: harbor.host,
    harbor_port: harbor.port,
    harbor_mount: harbor.mount,
    source_url: brand.suite.sourceUrl || DEFAULT_SOURCE_URL,
  };
}

function failure(caught: unknown, fallback: string): string {
  if (caught instanceof ApiAuthError) return "Session expirée : reconnecte-toi.";
  if (caught instanceof ApiForbiddenError) return "Réservé à un admin. Reconnecte-toi avec ce compte.";
  if (caught instanceof ApiUnavailableError) return "L’automate ne répond pas. Réessaie dans un instant.";
  if (caught instanceof ApiRequestError) return caught.message;
  return fallback;
}

/** Un moteur plus ancien que la console n'a pas la route : il répond 404. */
function outdated(caught: unknown): boolean {
  return caught instanceof ApiRequestError && caught.status === 404;
}

/** Réglages → Station, pour un admin : le nom, les adresses de l'écoute et du direct, le code source. */
export function StationPage() {
  const { imageBrand, applyStation } = useStationBinding();
  const [loaded, setLoaded] = useState<Loaded>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);
  const [form, setForm] = useState<StationForm | null>(null);
  const [busy, setBusy] = useState(false);
  const [fieldError, setFieldError] = useState<{ field: StationField; message: string } | null>(null);
  const [error, setError] = useState("");
  const [done, setDone] = useState("");

  useEffect(() => {
    let cancelled = false;
    setLoaded({ status: "loading" });
    apiGet<StationSettings>("/station.json").then(
      (settings) => {
        if (cancelled) return;
        setLoaded({ status: "ready", settings });
        setForm(stationForm(settings));
        // Lus au chargement de la console, les réglages ont pu changer, ou manquer.
        applyStation(publicStation(settings));
      },
      (caught: unknown) => {
        if (cancelled) return;
        setLoaded(
          outdated(caught)
            ? { status: "outdated" }
            : { status: "failed", message: failure(caught, "Les réglages ne répondent pas.") },
        );
      },
    );
    return () => {
      cancelled = true;
    };
  }, [attempt, applyStation]);

  // Le champ refusé prend le focus une fois son erreur affichée : elle est dans son libellé.
  useEffect(() => {
    if (fieldError) document.getElementById(`station-${fieldError.field}`)?.focus();
  }, [fieldError]);

  if (loaded.status === "loading") return <LoadingState label="Lecture des réglages…" />;
  if (loaded.status === "outdated") {
    return (
      <div className="admin-page admin-page--embedded">
        <Panel>
          <SectionHeader title="Station" />
          <p className="admin-account-line" role="status">
            Mets à jour le moteur pour régler la station ici. En attendant, la console garde les réglages de son image
            (brand.json).
          </p>
        </Panel>
      </div>
    );
  }
  if (loaded.status === "failed" || !form) {
    return (
      <div className="admin-page admin-page--embedded">
        <Panel>
          <SectionHeader title="Station" />
          <Text as="p" size="2" color="red" role="alert">
            {loaded.status === "failed" ? loaded.message : "Les réglages ne répondent pas."}
          </Text>
          <div className="admin-account-actions station-actions">
            <Button type="button" variant="soft" onClick={() => setAttempt((count) => count + 1)}>
              Réessayer
            </Button>
          </div>
        </Panel>
      </div>
    );
  }

  const placeholders = fallbacks(imageBrand);
  const edit = (key: StationField, value: string) => {
    setForm((current) => (current ? { ...current, [key]: value } : current));
    setDone("");
    if (fieldError?.field === key) setFieldError(null);
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError("");
    setDone("");
    setFieldError(null);
    try {
      const settings = await apiPut<StationSettings>("/station.json", stationBody(form));
      setLoaded({ status: "ready", settings });
      setForm(stationForm(settings));
      applyStation(publicStation(settings));
      setDone("Réglages enregistrés. La console les affiche déjà.");
    } catch (caught) {
      if (outdated(caught)) {
        setLoaded({ status: "outdated" });
        return;
      }
      const field = caught instanceof ApiRequestError ? caught.field : undefined;
      if (isField(field)) {
        setFieldError({ field, message: failure(caught, "") });
      } else {
        setError(failure(caught, "Enregistrement impossible. Réessaie."));
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="admin-page admin-page--embedded">
      <Panel>
        <SectionHeader title="Station" />
        {/* Pas la description de SectionHeader : son gris pâle manque de contraste en sombre. */}
        <p className="station-group-description">
          Un champ vide garde la valeur grisée : celle de l’image de la console (brand.json).
        </p>
        <form className="station-form" noValidate onSubmit={(event) => void submit(event)}>
          {GROUPS.map((group) => (
            <fieldset key={group.legend} className="station-group">
              <legend className="admin-account-title">{group.legend}</legend>
              <p className="station-group-description">{group.description}</p>
              <div className="station-fields">
                {group.fields.map((field) => {
                  const invalid = fieldError?.field === field.key;
                  return (
                    <FormField
                      key={field.key}
                      label={field.label}
                      htmlFor={`station-${field.key}`}
                      error={
                        invalid ? (
                          <Text size="1" color="red">
                            {fieldError.message}
                          </Text>
                        ) : undefined
                      }
                    >
                      <TextField.Root
                        id={`station-${field.key}`}
                        className="ui-field-control"
                        type={field.kind === "url" ? "url" : "text"}
                        inputMode={field.kind === "port" ? "numeric" : undefined}
                        autoComplete="off"
                        spellCheck={false}
                        value={form[field.key]}
                        placeholder={placeholders[field.key] || undefined}
                        aria-invalid={invalid || undefined}
                        onChange={(event) => edit(field.key, event.target.value)}
                      />
                    </FormField>
                  );
                })}
              </div>
            </fieldset>
          ))}
          <fieldset className="station-group">
            <legend className="admin-account-title">Fuseau</legend>
            <p className="station-group-description">
              <span className="station-timezone">{loaded.settings.timezone}</span>. Il se règle à l’installation : c’est la
              variable TZ des conteneurs.
            </p>
          </fieldset>
          {error ? (
            <Text as="p" size="2" color="red" role="alert">
              {error}
            </Text>
          ) : null}
          <p className="station-done" role="status">
            {done}
          </p>
          <div className="admin-account-actions">
            {/* Pas de disabled pendant l'envoi : un bouton désactivé perd le focus du clavier. */}
            <Button type="submit" aria-busy={busy}>
              {busy ? <Spinner size="1" /> : null}
              Enregistrer
            </Button>
          </div>
        </form>
      </Panel>
    </div>
  );
}
