import { Button, Checkbox, Flex, TextArea, TextField } from "@radix-ui/themes";
import { Copy, FolderOpen, RadioTower, RotateCcw, Save, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { MODE_HELP, relayUrlOk } from "../../api/cartMeta";
import { fetchBankFolders } from "../../api/cartSounds";
import type { Cart, CartMode } from "../../api/types";
import { useBrand } from "../../lib/BrandContext";
import { ConfirmDialog } from "../../ui/ConfirmDialog";
import { FormField, SelectField } from "../../ui/FormField";
import { Panel, SectionHeader } from "../../ui/Panel";

const PLAY_MODES: { value: CartMode; label: string }[] = [
  { value: "playlist_loop", label: "Boucle" },
  { value: "random", label: "Aléatoire" },
  { value: "playlist", label: "Une fois" },
  { value: "relay", label: "Relais" },
];

const NONE_FOLDER = "__none__";

const HABILLAGE_FOLDERS = [
  "30-habillage/jingles",
  "30-habillage/ids",
  "30-habillage/pubs",
  "30-habillage/beds",
  "30-habillage/stings",
  "30-habillage/sfx",
];

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
    cart.mode === "random" || cart.mode === "playlist" || cart.mode === "relay"
      ? cart.mode
      : "playlist_loop";
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
    (title || "").trim().replace(/[^A-Za-z0-9._-]+/g, "-").replace(/^[-._]+|[-._]+$/g, "") ||
    "cart";
  return `Carts/${cartId}-${slug}`;
}

function hostFromBase(base?: string): string {
  if (!base) return "";
  try {
    return new URL(base.includes("://") ? base : `http://${base}`).hostname;
  } catch {
    return "";
  }
}

function smbUrl(host: string, share: string, rel: string): string {
  const parts = [share, ...rel.split("/").filter(Boolean)].map(encodeURIComponent);
  return `smb://${host}/${parts.join("/")}`;
}

export function CartInspector({
  cart,
  busy,
  onSave,
  onDelete,
  onFire,
}: {
  cart: Cart;
  busy: boolean;
  onSave: (payload: Record<string, unknown>) => Promise<void>;
  onDelete: () => Promise<void>;
  onFire: () => Promise<void>;
}) {
  const brand = useBrand();
  const [draft, setDraft] = useState(() => draftFromCart(cart));
  const [bankPaths, setBankPaths] = useState<string[]>(HABILLAGE_FOLDERS);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    setDraft(draftFromCart(cart));
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

  const set = <K extends keyof CartDraft>(key: K, value: CartDraft[K]) => {
    setDraft((prev) => ({ ...prev, [key]: value }));
  };

  const dirty = JSON.stringify(draft) !== JSON.stringify(draftFromCart(cart));
  const relaySeconds = Number(draft.maxDuration);
  const relayReady =
    draft.mode !== "relay" ||
    (relayUrlOk(draft.url) && Number.isFinite(relaySeconds) && relaySeconds > 0);
  const folderOptions = useMemo(() => {
    const paths = [...bankPaths];
    if (draft.bankFolder && !paths.includes(draft.bankFolder)) {
      paths.unshift(draft.bankFolder);
    }
    return [
      { value: NONE_FOLDER, label: "Auto — dossier du bac" },
      ...paths.map((path) => ({ value: path, label: path })),
    ];
  }, [bankPaths, draft.bankFolder]);

  const lanHost = brand.infra.smbHost || "192.168.1.100";
  const tsHost =
    hostFromBase(brand.tailscaleBase) || "nasgul.taild4714f.ts.net";
  const share = brand.infra.smbShare || "BUTTON-Media";
  const finderPath = finderRel(cart.id, draft.title.trim() || cart.title);
  const lanSmb = smbUrl(lanHost, share, finderPath);
  const finderSmb = smbUrl(tsHost, share, finderPath);
  const finderHint =
    "Glisse un fichier dans ce dossier : il arrive dans le bac. Compte SMB : laz. Hors studio, utilise l’adresse Tailscale.";

  return (
    <Panel as="aside" padded={false} className="app-carts-col app-carts-inspector">
      <div className="app-carts-inspector-header">
        <SectionHeader
          title={cart.title}
          description="Fichiers et lecture. Pour le mettre dans la rotation : Programmation."
          actions={
            <Button
              size="1"
              className="app-carts-now"
              disabled={busy}
              onClick={() => void onFire()}
            >
              <RadioTower className="ui-button-icon" />
              Maintenant
            </Button>
          }
        />
      </div>
      <div className="app-carts-inspector-body">
        <FormField label="Nom">
          <TextField.Root
            className="ui-field-control"
            value={draft.title}
            onChange={(event) => set("title", event.target.value)}
          />
        </FormField>
        <FormField label="Notes">
          <TextArea
            className="ui-field-control"
            rows={3}
            value={draft.notes}
            onChange={(event) => set("notes", event.target.value)}
          />
        </FormField>
        <SelectField
          label="Lecture"
          value={draft.mode}
          options={PLAY_MODES}
          onValueChange={(value) => set("mode", value as CartMode)}
          hint={MODE_HELP[draft.mode]}
        />
        {draft.mode === "relay" ? (
          <>
            <FormField label="URL du flux" hint="HTTP ou HTTPS, avec un chemin. Ex. https://radio.exemple/flux.mp3">
              <TextField.Root
                className="ui-field-control"
                value={draft.url}
                placeholder="https://"
                onChange={(event) => set("url", event.target.value)}
              />
            </FormField>
            <FormField label="Durée max (secondes)" hint="Obligatoire. Le relais s’arrête au bout de ce temps.">
              <TextField.Root
                className="ui-field-control"
                type="number"
                min={1}
                value={draft.maxDuration}
                onChange={(event) => set("maxDuration", event.target.value)}
              />
            </FormField>
          </>
        ) : null}
        <details className="app-carts-advanced">
          <summary>Avancé</summary>
          <div className="app-carts-finder">
            <span className="ui-field-label">Finder</span>
            <code className="app-carts-finder-path">{finderSmb}</code>
            {lanSmb !== finderSmb ? (
              <code className="app-carts-finder-path app-carts-finder-path--alt">{lanSmb}</code>
            ) : null}
            <Flex gap="2" wrap="wrap">
              <Button size="1" variant="soft" asChild>
                <a href={finderSmb}>
                  <FolderOpen className="ui-button-icon" />
                  Ouvrir dans le Finder
                </a>
              </Button>
              <Button
                size="1"
                variant="ghost"
                color="gray"
                onClick={() => {
                  void navigator.clipboard.writeText(finderSmb).then(() => {
                    setCopied(true);
                    window.setTimeout(() => setCopied(false), 1500);
                  });
                }}
              >
                <Copy className="ui-button-icon" />
                {copied ? "Copié" : "Copier"}
              </Button>
            </Flex>
          </div>
          <SelectField
            label="Dossier de la banque"
            value={draft.bankFolder || NONE_FOLDER}
            options={folderOptions}
            onValueChange={(value) => set("bankFolder", value === NONE_FOLDER ? "" : value)}
            hint={finderHint}
          />
          {draft.mode === "relay" ? null : (
            <label className="app-carts-ident">
              <Checkbox
                checked={draft.identPads}
                onCheckedChange={(next) => set("identPads", next === true)}
              />
              <span>
                Pads d’idents (avancé)
                <small>Un seul bac à la fois. Les autres perdent ce marquage.</small>
              </span>
            </label>
          )}
        </details>
      </div>
      <div className="app-carts-inspector-actions">
        <div className={`app-carts-dirty-state${dirty ? " is-dirty" : ""}`}>
          <span aria-hidden="true" />
          {dirty ? "Non enregistré" : "À jour"}
        </div>
        <Flex gap="2" wrap="wrap" justify="end">
          {dirty ? (
            <Button
              size="1"
              variant="ghost"
              color="gray"
              disabled={busy}
              onClick={() => setDraft(draftFromCart(cart))}
            >
              <RotateCcw className="ui-button-icon" />
              Annuler
            </Button>
          ) : null}
          <ConfirmDialog
            trigger={
              <Button size="1" color="red" variant="soft" disabled={busy}>
                <Trash2 className="ui-button-icon" />
                Supprimer
              </Button>
            }
            title={`Supprimer « ${cart.title} » ?`}
            description="Le bac et son contenu seront supprimés."
            confirmLabel="Supprimer le bac"
            busy={busy}
            onConfirm={onDelete}
          />
          <Button
            size="1"
            disabled={busy || !dirty || !draft.title.trim() || !relayReady}
            onClick={() =>
              void onSave({
                title: draft.title.trim(),
                notes: draft.notes,
                mode: draft.mode,
                bank_folder: draft.bankFolder,
                ident_pads: draft.mode === "relay" ? false : draft.identPads,
                ...(draft.mode === "relay"
                  ? { url: draft.url.trim(), max_duration: relaySeconds }
                  : {}),
              })
            }
          >
            <Save className="ui-button-icon" />
            {busy ? "Enregistrement…" : "Enregistrer"}
          </Button>
        </Flex>
      </div>
    </Panel>
  );
}
