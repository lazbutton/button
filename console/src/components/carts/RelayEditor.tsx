import { Button, SegmentedControl, TextField } from "@radix-ui/themes";
import { Headphones, RotateCcw, Save, Square } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { relayUrlOk } from "../../api/cartMeta";
import { MAX_DURATION_PRESETS } from "../../api/soundsView";
import type { Cart } from "../../api/types";
import { FormField } from "../../ui/FormField";

type Listen = "idle" | "loading" | "playing" | "error";

function minutesOf(seconds: number | null | undefined): string {
  if (!seconds) return "";
  return String(Number((seconds / 60).toFixed(2)));
}

const PRIORITY = ["Direct", "Relais", "Bacs", "Jingles", "Auto-DJ"];

export function RelayEditor({
  cart,
  busy,
  onSave,
}: {
  cart: Cart;
  busy: boolean;
  onSave: (payload: Record<string, unknown>) => Promise<void>;
}) {
  const [url, setUrl] = useState(cart.url || "");
  const [minutes, setMinutes] = useState(minutesOf(cart.max_duration));
  const [listen, setListen] = useState<Listen>("idle");
  const audioRef = useRef<HTMLAudioElement>(null);

  useEffect(() => {
    setUrl(cart.url || "");
    setMinutes(minutesOf(cart.max_duration));
  }, [cart.id, cart.url, cart.max_duration]);

  useEffect(() => {
    audioRef.current?.pause();
    setListen("idle");
  }, [cart.id]);

  const seconds = Math.round(Number(minutes) * 60);
  const urlOk = relayUrlOk(url);
  const ready = urlOk && Number.isFinite(seconds) && seconds > 0;
  const dirty = url !== (cart.url || "") || minutes !== minutesOf(cart.max_duration);
  const preset = MAX_DURATION_PRESETS.some((item) => item.seconds === seconds) ? String(seconds) : "autre";

  const toggleListen = () => {
    const audio = audioRef.current;
    if (!audio) return;
    if (listen === "playing" || listen === "loading") {
      audio.pause();
      audio.removeAttribute("src");
      audio.load();
      setListen("idle");
      return;
    }
    setListen("loading");
    audio.src = url.trim();
    void audio.play().catch(() => setListen("error"));
  };

  return (
    <form
      className="bacs-relay"
      onSubmit={(event) => {
        event.preventDefault();
        if (!ready || busy || !dirty) return;
        void onSave({ url: url.trim(), max_duration: seconds });
      }}
    >
      <div className="bacs-relay-body">
        <section className="bacs-card">
          <header className="bacs-card-head">
            <h2>Flux entrant</h2>
            <p>L'adresse publique du flux de la radio partenaire.</p>
          </header>
          <FormField
            label="Adresse du flux"
            error={
              url.trim() && !urlOk
                ? "Il faut une adresse HTTP ou HTTPS avec un chemin, par exemple /live.mp3."
                : undefined
            }
          >
            <TextField.Root
              size="2"
              className="ui-field-control"
              value={url}
              placeholder="https://radio.exemple/flux.mp3"
              spellCheck={false}
              onChange={(event) => {
                setUrl(event.target.value);
                if (listen !== "idle") {
                  audioRef.current?.pause();
                  setListen("idle");
                }
              }}
            />
          </FormField>
          <div className="bacs-listen">
            <Button type="button" size="2" variant="soft" color="gray" disabled={!urlOk} onClick={toggleListen}>
              {listen === "playing" || listen === "loading" ? (
                <Square className="ui-button-icon" />
              ) : (
                <Headphones className="ui-button-icon" />
              )}
              {listen === "playing" || listen === "loading" ? "Arrêter l'écoute" : "Écouter le flux"}
            </Button>
            <span className={`bacs-listen-state is-${listen}`} role="status" aria-live="polite">
              <i aria-hidden="true" />
              {listen === "loading"
                ? "Connexion au flux…"
                : listen === "playing"
                  ? "Le flux répond"
                  : listen === "error"
                    ? "Le flux ne répond pas, ou le navigateur le refuse"
                    : "Vérifie l'adresse avant d'enregistrer"}
            </span>
            <audio
              ref={audioRef}
              preload="none"
              onPlaying={() => setListen("playing")}
              onError={() => setListen((state) => (state === "idle" ? state : "error"))}
            />
          </div>
        </section>

        <section className="bacs-card">
          <header className="bacs-card-head">
            <h2>Durée maximale</h2>
            <p>Obligatoire. Le relais s'arrête au bout de ce temps, même si le flux continue.</p>
          </header>
          <div className="bacs-duration">
            <SegmentedControl.Root
              size="2"
              value={preset}
              onValueChange={(value) => {
                if (value !== "autre") setMinutes(String(Number(value) / 60));
              }}
              aria-label="Durée maximale"
            >
              {MAX_DURATION_PRESETS.map((item) => (
                <SegmentedControl.Item key={item.seconds} value={String(item.seconds)}>
                  {item.label}
                </SegmentedControl.Item>
              ))}
              <SegmentedControl.Item value="autre">Autre</SegmentedControl.Item>
            </SegmentedControl.Root>
            <TextField.Root
              size="2"
              type="number"
              min={1}
              step="any"
              className="bacs-duration-input"
              value={minutes}
              aria-label="Durée maximale en minutes"
              onChange={(event) => setMinutes(event.target.value)}
            >
              <TextField.Slot side="right">min</TextField.Slot>
            </TextField.Root>
          </div>
        </section>

        <section className="bacs-card bacs-card--quiet" aria-label="Priorité à l'antenne">
          <header className="bacs-card-head">
            <h2>Priorité à l'antenne</h2>
            <p>Un direct passe devant le relais. Le relais passe devant tout le reste. Le flux public ne change pas.</p>
          </header>
          <ol className="bacs-priority">
            {PRIORITY.map((item) => (
              <li key={item} className={item === "Relais" ? "is-current" : undefined}>
                {item}
              </li>
            ))}
          </ol>
        </section>
      </div>

      <footer className="bacs-foot">
        <span className={`bacs-dirty${dirty ? " is-dirty" : ""}`}>
          <i aria-hidden="true" />
          {dirty ? "Modifications non enregistrées" : "Enregistré"}
        </span>
        <span className="bacs-spacer" />
        {dirty ? (
          <Button
            type="button"
            size="2"
            variant="ghost"
            color="gray"
            disabled={busy}
            onClick={() => {
              setUrl(cart.url || "");
              setMinutes(minutesOf(cart.max_duration));
            }}
          >
            <RotateCcw className="ui-button-icon" />
            Annuler
          </Button>
        ) : null}
        <Button type="submit" size="2" highContrast disabled={busy || !dirty || !ready}>
          <Save className="ui-button-icon" />
          {busy ? "Enregistrement…" : "Enregistrer"}
        </Button>
      </footer>
    </form>
  );
}
