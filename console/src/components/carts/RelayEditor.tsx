import { Button, SegmentedControl, TextField } from "@radix-ui/themes";
import { Headphones, RotateCcw, Save, Square, TriangleAlert } from "lucide-react";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { relayUrlOk } from "../../api/cartMeta";
import { keepEdits, unsavedEdits, type CartAnswer } from "../../api/cartSave";
import { MAX_DURATION_PRESETS } from "../../api/soundsView";
import type { Cart } from "../../api/types";
import { FormField } from "../../ui/FormField";

type Listen = "idle" | "loading" | "playing" | "error";

type RelayDraft = { url: string; minutes: string };

function minutesOf(seconds: number | null | undefined): string {
  if (!seconds) return "";
  return String(Number((seconds / 60).toFixed(2)));
}

function draftOf(cart: Cart): RelayDraft {
  return { url: cart.url || "", minutes: minutesOf(cart.max_duration) };
}

const PRIORITY = ["Direct", "Relais", "Bacs", "Jingles", "Auto-DJ"];

export function RelayEditor({
  cart,
  busy,
  onSave,
}: {
  cart: Cart;
  busy: boolean;
  /** `base`: the bac the typing started from. Resolves with the bac written, or the refusal to show. */
  onSave: (payload: Record<string, unknown>, base: Cart, stillHere: () => boolean) => Promise<CartAnswer | null>;
}) {
  const [draft, setDraft] = useState(() => draftOf(cart));
  const draftNow = useRef(draft);
  draftNow.current = draft;
  const read = useRef({ id: cart.id, draft: draftOf(cart) });
  // The bac the typing started from, as in the bac's settings: its version goes with the save.
  const base = useRef(cart);
  // Mounted, and on the same bac since a save started: only then is its answer this form's to show.
  const alive = useRef(false);
  const session = useRef(0);
  const [refusal, setRefusal] = useState("");
  const [listen, setListen] = useState<Listen>("idle");
  const audioRef = useRef<HTMLAudioElement>(null);
  const { url, minutes } = draft;
  const setUrl = (value: string) => setDraft((current) => ({ ...current, url: value }));
  const setMinutes = (value: string) => setDraft((current) => ({ ...current, minutes: value }));

  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);

  // A new bac resets the form. The same bac read again, after a refusal for instance, keeps what is
  // being typed, and takes the rest from the engine. Before the paint, as in the bac's settings.
  useLayoutEffect(() => {
    const fresh = draftOf(cart);
    const before = read.current;
    const sameBac = cart.id === before.id;
    setDraft((current) => (sameBac ? keepEdits(current, before.draft, fresh) : fresh));
    if (!sameBac || !unsavedEdits(draftNow.current, before.draft, fresh)) base.current = cart;
    if (!sameBac) {
      session.current += 1;
      setRefusal("");
    }
    read.current = { id: cart.id, draft: fresh };
  }, [cart]);

  useEffect(() => {
    audioRef.current?.pause();
    setListen("idle");
  }, [cart.id]);

  const seconds = Math.round(Number(minutes) * 60);
  const urlOk = relayUrlOk(url);
  const ready = urlOk && Number.isFinite(seconds) && seconds > 0;
  const dirty = url !== (cart.url || "") || minutes !== minutesOf(cart.max_duration);
  const preset = MAX_DURATION_PRESETS.some((item) => item.seconds === seconds) ? String(seconds) : "autre";

  // Nothing left to save: the refusal no longer says anything true, even once the form changes again.
  useEffect(() => {
    if (!dirty) setRefusal("");
  }, [dirty]);

  const save = async () => {
    const sent = draft;
    const started = session.current;
    const stillHere = () => alive.current && session.current === started;
    setRefusal("");
    const from = base.current.id === cart.id ? base.current : cart;
    const answer = await onSave({ url: url.trim(), max_duration: seconds }, from, stillHere);
    // Gone, or on another bac by now: the answer is not for this form, and the page said it.
    if (!answer || !stillHere()) return;
    base.current = answer.cart;
    // Saved: the address without its spaces, the duration in whole seconds. A field typed again stays.
    if (answer.status === "saved") setDraft((current) => keepEdits(current, sent, draftOf(answer.cart)));
    else setRefusal(answer.text);
  };

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
        void save();
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

      {refusal && dirty ? (
        <p className="bacs-conflict" role="alert">
          <TriangleAlert size={15} aria-hidden="true" />
          <span>{refusal}</span>
        </p>
      ) : null}

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
              setDraft(draftOf(cart));
              setRefusal("");
              base.current = cart;
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
