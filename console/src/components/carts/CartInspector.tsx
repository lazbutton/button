import { Button, IconButton, SegmentedControl, Switch, TextArea, TextField, Tooltip } from "@radix-ui/themes";
import { ArrowUpRight, ChevronRight, Copy, FolderOpen, RotateCcw, Save, Trash2, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { titleTaken } from "../../api/cartErrors";
import { MODE_HELP, relayUrlOk } from "../../api/cartMeta";
import { fetchBankFolders } from "../../api/cartSounds";
import { fetchVolume, stationSmbUrl } from "../../api/volume";
import type { Cart, CartMode } from "../../api/types";
import { ConfirmDialog } from "../../ui/ConfirmDialog";
import { FormField, SelectField } from "../../ui/FormField";
import type { BacUsage } from "./BacHeader";
import { HABILLAGE_FOLDERS } from "./CreateBacDialog";

const PLAY_MODES: { value: CartMode; label: string }[] = [
  { value: "playlist_loop", label: "Boucle" },
  { value: "random", label: "Aléatoire" },
  { value: "playlist", label: "Une fois" },
  { value: "relay", label: "Relais" },
];

const NONE_FOLDER = "__none__";

type CartDraft = {
  title: string;
  notes: string;
  mode: CartMode;
  bankFolder: string;
  url: string;
  maxDuration: string;
  identPads: boolean;
};

function draftFromCart(cart: Cart): CartDraft {
  const mode: CartMode =
    cart.mode === "random" || cart.mode === "playlist" || cart.mode === "relay" ? cart.mode : "playlist_loop";
  return {
    title: cart.title,
    notes: cart.notes,
    mode,
    bankFolder: cart.bank_folder || "",
    url: cart.mode === "relay" ? cart.url || "" : "",
    maxDuration: cart.max_duration ? String(cart.max_duration) : "",
    identPads: Boolean(cart.ident_pads),
  };
}

function finderRel(cartId: number, title: string): string {
  const slug =
    (title || "")
      .trim()
      .replace(/[^A-Za-z0-9._-]+/g, "-")
      .replace(/^[-._]+|[-._]+$/g, "") || "cart";
  return `Bacs/${cartId}-${slug}`;
}

export function CartInspector({
  cart,
  busy,
  usage,
  taken,
  onClose,
  onSave,
  onDelete,
}: {
  cart: Cart;
  busy: boolean;
  usage: BacUsage;
  /** Titles of the other bacs. */
  taken: string[];
  onClose: () => void;
  onSave: (payload: Record<string, unknown>) => Promise<void>;
  onDelete: () => Promise<void>;
}) {
  const [draft, setDraft] = useState(() => draftFromCart(cart));
  const baseline = useRef(draftFromCart(cart));
  const baselineId = useRef(cart.id);
  const [bankPaths, setBankPaths] = useState<string[]>(HABILLAGE_FOLDERS);
  const [copied, setCopied] = useState(false);
  const [volume, setVolume] = useState<{ name: string; host: string } | null>(null);

  // A new bac resets the form. The same bac reloaded keeps the fields being edited.
  useEffect(() => {
    const fresh = draftFromCart(cart);
    setDraft((current) => {
      if (cart.id === baselineId.current) {
        const next = { ...fresh };
        for (const key of Object.keys(fresh) as (keyof CartDraft)[]) {
          if (current[key] !== baseline.current[key]) (next as Record<string, unknown>)[key] = current[key];
        }
        return next;
      }
      return fresh;
    });
    baseline.current = fresh;
    baselineId.current = cart.id;
  }, [cart]);

  useEffect(() => {
    let cancelled = false;
    void fetchBankFolders()
      .then((payload) => {
        if (cancelled || !payload.available) return;
        const extra = payload.folders.map((folder) => folder.path);
        setBankPaths([...new Set([...HABILLAGE_FOLDERS, ...extra])].sort());
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancel = false;
    void fetchVolume().then((value) => {
      if (!cancel) setVolume(value);
    });
    return () => {
      cancel = true;
    };
  }, []);

  const set = <K extends keyof CartDraft>(key: K, value: CartDraft[K]) => {
    setDraft((prev) => ({ ...prev, [key]: value }));
  };

  const saved = draftFromCart(cart);
  const dirty = JSON.stringify(draft) !== JSON.stringify(saved);
  const relaySeconds = Number(draft.maxDuration);
  const clash = titleTaken(draft.title, taken);
  const becomesRelay = draft.mode === "relay" && cart.mode !== "relay";
  const relayReady =
    draft.mode !== "relay" || (relayUrlOk(draft.url) && Number.isFinite(relaySeconds) && relaySeconds > 0);
  const folderOptions = useMemo(() => {
    const paths = [...bankPaths];
    if (draft.bankFolder && !paths.includes(draft.bankFolder)) paths.unshift(draft.bankFolder);
    return [
      { value: NONE_FOLDER, label: "Automatique : dossier du bac" },
      ...paths.map((path) => ({ value: path, label: path })),
    ];
  }, [bankPaths, draft.bankFolder]);

  const finderPath = finderRel(cart.id, draft.title.trim() || cart.title);
  const networkUrl =
    volume?.host && volume.name ? stationSmbUrl(volume.host, volume.name, finderPath) : "";

  const save = () =>
    onSave({
      title: draft.title.trim(),
      notes: draft.notes,
      mode: draft.mode,
      bank_folder: draft.bankFolder,
      ident_pads: draft.mode === "relay" ? false : draft.identPads,
      ...(draft.mode === "relay" ? { url: draft.url.trim(), max_duration: relaySeconds } : {}),
    });

  return (
    <aside className="bacs-inspector" aria-label="Réglages du bac">
      <header className="bacs-inspector-head">
        <h2>Réglages</h2>
        <span className={`bacs-dirty${dirty ? " is-dirty" : ""}`}>
          <i aria-hidden="true" />
          {dirty ? "Modifié" : "Enregistré"}
        </span>
        <span className="bacs-spacer" />
        <Tooltip content="Fermer les réglages">
          <IconButton size="1" variant="ghost" color="gray" aria-label="Fermer les réglages" onClick={onClose}>
            <X size={15} />
          </IconButton>
        </Tooltip>
      </header>

      <form
        className="bacs-inspector-body"
        id={`bac-settings-${cart.id}`}
        onSubmit={(event) => {
          event.preventDefault();
          if (busy || !dirty || !draft.title.trim() || clash || !relayReady) return;
          void save();
        }}
      >
        <FormField label="Nom" error={clash ? "Un autre bac porte déjà ce nom." : undefined}>
          <TextField.Root
            size="2"
            className="ui-field-control"
            value={draft.title}
            onChange={(event) => set("title", event.target.value)}
          />
        </FormField>

        <div className="ui-field">
          <span className="ui-field-label">Lecture</span>
          <SegmentedControl.Root
            size="1"
            className="bacs-modes"
            value={draft.mode}
            onValueChange={(value) => set("mode", value as CartMode)}
            aria-label="Lecture"
          >
            {PLAY_MODES.map((item) => (
              <SegmentedControl.Item key={item.value} value={item.value}>
                {item.label}
              </SegmentedControl.Item>
            ))}
          </SegmentedControl.Root>
          <span className="ui-field-hint">{MODE_HELP[draft.mode]}</span>
        </div>

        {becomesRelay ? (
          <div className="bacs-inspector-group">
            <FormField
              label="Adresse du flux"
              hint="HTTP ou HTTPS, avec un chemin."
              error={draft.url.trim() && !relayUrlOk(draft.url) ? "Adresse incomplète." : undefined}
            >
              <TextField.Root
                size="2"
                className="ui-field-control"
                value={draft.url}
                placeholder="https://radio.exemple/flux.mp3"
                onChange={(event) => set("url", event.target.value)}
              />
            </FormField>
            <FormField label="Durée max. (secondes)" hint="Obligatoire pour un relais.">
              <TextField.Root
                size="2"
                className="ui-field-control"
                type="number"
                min={1}
                value={draft.maxDuration}
                onChange={(event) => set("maxDuration", event.target.value)}
              />
            </FormField>
          </div>
        ) : null}

        <FormField label="Notes">
          <TextArea
            size="2"
            className="ui-field-control bacs-notes"
            rows={3}
            value={draft.notes}
            placeholder="Contenu, consignes, contact…"
            onChange={(event) => set("notes", event.target.value)}
          />
        </FormField>

        <section className="bacs-uses" aria-label="Programmation">
          <span className="ui-field-label">Programmation</span>
          {usage.lines.length ? (
            <ul>
              {usage.lines.map((line, index) => (
                <li key={`${line}-${index}`}>{line}</li>
              ))}
            </ul>
          ) : (
            <p>Aucune horloge ne joue ce bac.</p>
          )}
          <Link to="/programmation" className="bacs-uses-link">
            Ouvrir les heures types
            <ArrowUpRight size={13} aria-hidden="true" />
          </Link>
        </section>

        <details className="bacs-advanced">
          <summary>
            <ChevronRight size={14} aria-hidden="true" />
            Avancé
          </summary>
          <div className="bacs-advanced-body">
            {draft.mode === "relay" ? null : (
              <>
                <SelectField
                  label="Dossier de la banque"
                  value={draft.bankFolder || NONE_FOLDER}
                  options={folderOptions}
                  onValueChange={(value) => set("bankFolder", value === NONE_FOLDER ? "" : value)}
                  hint="Le bac et ce dossier restent liés : un ajout au bac y est rangé, un fichier déposé dans le dossier entre dans le bac."
                />
                <label className="bacs-switch-row">
                  <span>
                    <strong>Pads d'idents</strong>
                    <small>Un seul bac à la fois : le marquer ici le retire des autres.</small>
                  </span>
                  <Switch size="1" checked={draft.identPads} onCheckedChange={(next) => set("identPads", next)} />
                </label>
              </>
            )}
            {networkUrl ? (
              <div className="bacs-network">
                <span className="ui-field-label">Dossier réseau</span>
                <code>{networkUrl}</code>
                <span className="bacs-network-actions">
                  <Button size="1" variant="soft" color="gray" asChild>
                    <a href={networkUrl}>
                      <FolderOpen className="ui-button-icon" />
                      Ouvrir
                    </a>
                  </Button>
                  <Button
                    type="button"
                    size="1"
                    variant="ghost"
                    color="gray"
                    onClick={() => {
                      void navigator.clipboard.writeText(networkUrl).then(() => {
                        setCopied(true);
                        window.setTimeout(() => setCopied(false), 1500);
                      });
                    }}
                  >
                    <Copy className="ui-button-icon" />
                    {copied ? "Copié" : "Copier"}
                  </Button>
                </span>
                <small>Un fichier glissé dans ce dossier arrive dans le bac.</small>
              </div>
            ) : null}
          </div>
        </details>
      </form>

      <footer className="bacs-inspector-foot">
        {usage.inClock ? (
          <Tooltip content="Une horloge utilise ce bac : retire-le d'abord dans Programmation.">
            <span>
              <Button type="button" size="2" variant="ghost" color="red" disabled>
                <Trash2 className="ui-button-icon" />
                Supprimer
              </Button>
            </span>
          </Tooltip>
        ) : (
          <ConfirmDialog
            trigger={
              <Button type="button" size="2" variant="ghost" color="red" disabled={busy}>
                <Trash2 className="ui-button-icon" />
                Supprimer
              </Button>
            }
            title={`Supprimer « ${cart.title} » ?`}
            description="Le bac disparaît. Les fichiers de son dossier propre partent dans la corbeille de la banque ; les dossiers partagés de la banque ne sont pas touchés."
            confirmLabel="Supprimer le bac"
            busy={busy}
            onConfirm={onDelete}
          />
        )}
        <span className="bacs-spacer" />
        {dirty ? (
          <Button type="button" size="2" variant="ghost" color="gray" disabled={busy} onClick={() => setDraft(saved)}>
            <RotateCcw className="ui-button-icon" />
            Annuler
          </Button>
        ) : null}
        <Button
          type="submit"
          form={`bac-settings-${cart.id}`}
          size="2"
          highContrast
          disabled={busy || !dirty || !draft.title.trim() || clash || !relayReady}
        >
          <Save className="ui-button-icon" />
          {busy ? "Enregistrement…" : "Enregistrer"}
        </Button>
      </footer>
    </aside>
  );
}
