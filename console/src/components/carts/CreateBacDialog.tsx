import { Button, Dialog, RadioCards, SegmentedControl, TextField } from "@radix-ui/themes";
import { Music2, Radio, Sparkles } from "lucide-react";
import { useState, type ReactElement } from "react";
import { bacErrorText, titleTaken } from "../../api/cartErrors";
import { MODE_HELP, relayUrlOk } from "../../api/cartMeta";
import { MAX_DURATION_PRESETS, type BacKind } from "../../api/soundsView";
import type { CartMode } from "../../api/types";
import { FormField, SelectField } from "../../ui/FormField";

export type CartCreateExtra = { url?: string; max_duration?: number; bank_folder?: string };

export const HABILLAGE_FOLDERS = [
  "30-habillage/jingles",
  "30-habillage/ids",
  "30-habillage/pubs",
  "30-habillage/beds",
  "30-habillage/stings",
  "30-habillage/sfx",
];

const FILE_MODES: { value: CartMode; label: string }[] = [
  { value: "playlist_loop", label: "Boucle" },
  { value: "random", label: "Aléatoire" },
  { value: "playlist", label: "Une fois" },
];

const KINDS: { value: BacKind; label: string; hint: string; icon: typeof Music2 }[] = [
  { value: "fichiers", label: "Fichiers", hint: "Sons copiés ou liés", icon: Music2 },
  { value: "habillage", label: "Habillage", hint: "Jingles, idents, pubs", icon: Sparkles },
  { value: "relais", label: "Relais", hint: "Flux d'une autre radio", icon: Radio },
];

export function CreateBacDialog({
  trigger,
  defaultKind,
  taken = [],
  onCreate,
}: {
  trigger: ReactElement;
  defaultKind: BacKind;
  /** Titles already used: clocks find a bac by its title. */
  taken?: string[];
  onCreate: (title: string, mode: CartMode, extra: CartCreateExtra) => Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [kind, setKind] = useState<BacKind>(defaultKind);
  const [mode, setMode] = useState<CartMode>("playlist_loop");
  const [folder, setFolder] = useState(HABILLAGE_FOLDERS[0]);
  const [url, setUrl] = useState("");
  const [minutes, setMinutes] = useState("60");
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState("");

  const seconds = Math.round(Number(minutes) * 60);
  const relayReady = relayUrlOk(url) && Number.isFinite(seconds) && seconds > 0;
  const clash = titleTaken(title, taken);
  const ready = Boolean(title.trim()) && !clash && (kind !== "relais" || relayReady);

  const reset = () => {
    setTitle("");
    setUrl("");
    setMinutes("60");
    setMode(defaultKind === "habillage" ? "random" : "playlist_loop");
    setFolder(HABILLAGE_FOLDERS[0]);
    setKind(defaultKind);
    setFailure("");
  };

  const submit = async () => {
    if (busy || !ready) return;
    setBusy(true);
    setFailure("");
    try {
      if (kind === "relais") {
        await onCreate(title.trim(), "relay", { url: url.trim(), max_duration: seconds });
      } else {
        await onCreate(title.trim(), mode, kind === "habillage" ? { bank_folder: folder } : {});
      }
      setOpen(false);
    } catch (caught) {
      setFailure(bacErrorText(caught, "Création impossible. Réessaie."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog.Root
      open={open}
      onOpenChange={(next) => {
        if (next) reset();
        setOpen(next);
      }}
    >
      <Dialog.Trigger>{trigger}</Dialog.Trigger>
      <Dialog.Content maxWidth="30rem" className="bacs-dialog">
        <Dialog.Title>Nouveau bac</Dialog.Title>
        <Dialog.Description size="2" color="gray" mb="4">
          Un bac regroupe des sons, ou relaie le flux d'une autre radio. On le place ensuite dans une horloge, depuis
          Programmation.
        </Dialog.Description>
        <form
          className="bacs-dialog-form"
          onSubmit={(event) => {
            event.preventDefault();
            void submit();
          }}
        >
          <FormField
            label="Nom"
            error={clash ? "Un bac porte déjà ce nom : les horloges ne sauraient pas lequel jouer." : undefined}
          >
            <TextField.Root
              size="2"
              className="ui-field-control"
              value={title}
              placeholder={
                kind === "relais" ? "Radio partenaire" : kind === "habillage" ? "Jingles" : "Rotation de nuit"
              }
              onChange={(event) => setTitle(event.target.value)}
              autoFocus
            />
          </FormField>
          <div className="ui-field">
            <span className="ui-field-label">Type</span>
            <RadioCards.Root
              size="1"
              columns="3"
              value={kind}
              onValueChange={(value) => {
                const next = value as BacKind;
                setKind(next);
                if (next === "habillage") setMode("random");
              }}
              aria-label="Type de bac"
            >
              {KINDS.map((item) => (
                <RadioCards.Item key={item.value} value={item.value} className="bacs-kind-card">
                  <item.icon size={16} strokeWidth={1.75} aria-hidden="true" />
                  <span className="bacs-kind-label">{item.label}</span>
                  <span className="bacs-kind-hint">{item.hint}</span>
                </RadioCards.Item>
              ))}
            </RadioCards.Root>
          </div>
          {kind === "relais" ? (
            <>
              <FormField
                label="Adresse du flux"
                hint="HTTP ou HTTPS, avec un chemin : https://radio.exemple/flux.mp3"
                error={url.trim() && !relayUrlOk(url) ? "Il manque le schéma, l'hôte ou le chemin." : undefined}
              >
                <TextField.Root
                  size="2"
                  className="ui-field-control"
                  value={url}
                  placeholder="https://"
                  onChange={(event) => setUrl(event.target.value)}
                />
              </FormField>
              <div className="ui-field">
                <span className="ui-field-label">Durée maximale</span>
                <div className="bacs-duration">
                  <SegmentedControl.Root
                    size="1"
                    aria-label="Durée maximale"
                    value={MAX_DURATION_PRESETS.some((item) => item.seconds === seconds) ? String(seconds) : "autre"}
                    onValueChange={(value) => {
                      if (value !== "autre") setMinutes(String(Number(value) / 60));
                    }}
                  >
                    {MAX_DURATION_PRESETS.map((item) => (
                      <SegmentedControl.Item key={item.seconds} value={String(item.seconds)}>
                        {item.label}
                      </SegmentedControl.Item>
                    ))}
                    <SegmentedControl.Item value="autre">Autre</SegmentedControl.Item>
                  </SegmentedControl.Root>
                  <TextField.Root
                    size="1"
                    type="number"
                    min={1}
                    className="bacs-duration-input"
                    value={minutes}
                    aria-label="Durée maximale en minutes"
                    onChange={(event) => setMinutes(event.target.value)}
                  >
                    <TextField.Slot side="right">min</TextField.Slot>
                  </TextField.Root>
                </div>
                <span className="ui-field-hint">Obligatoire : le relais s'arrête au bout de ce temps.</span>
              </div>
            </>
          ) : (
            <>
              <div className="ui-field">
                <span className="ui-field-label">Lecture</span>
                <SegmentedControl.Root size="2" value={mode} onValueChange={(value) => setMode(value as CartMode)}>
                  {FILE_MODES.map((item) => (
                    <SegmentedControl.Item key={item.value} value={item.value}>
                      {item.label}
                    </SegmentedControl.Item>
                  ))}
                </SegmentedControl.Root>
                <span className="ui-field-hint">{MODE_HELP[mode]}</span>
              </div>
              {kind === "habillage" ? (
                <SelectField
                  label="Dossier de la banque"
                  value={folder}
                  options={HABILLAGE_FOLDERS.map((path) => ({ value: path, label: path }))}
                  onValueChange={setFolder}
                  hint="Le bac et ce dossier restent liés : un ajout au bac y est rangé, un fichier déposé dans le dossier entre dans le bac."
                />
              ) : null}
            </>
          )}
          {failure ? (
            <p className="bacs-dialog-error" role="alert">
              {failure}
            </p>
          ) : null}
          <div className="bacs-dialog-actions">
            <Dialog.Close>
              <Button type="button" size="2" variant="soft" color="gray" disabled={busy}>
                Annuler
              </Button>
            </Dialog.Close>
            <Button type="submit" size="2" highContrast disabled={busy || !ready}>
              {busy ? "Création…" : "Créer le bac"}
            </Button>
          </div>
        </form>
      </Dialog.Content>
    </Dialog.Root>
  );
}
