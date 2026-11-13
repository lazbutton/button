import { CircleCheck, CircleX, Info, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState, type FocusEvent, type KeyboardEvent } from "react";
import { createPortal } from "react-dom";
import {
  TONE_LABEL,
  clockLeft,
  pauseClock,
  resumeClock,
  startClock,
  toastDuration,
  type ToastClock,
  type ToastTone,
} from "../api/toast";

export type { ToastTone };

export type ToastAction = {
  label: string;
  onClick: () => void;
};

export type ToastShowOptions = {
  action?: ToastAction;
};

export type ToastMessage = {
  id: number;
  text: string;
  tone: ToastTone;
  action?: ToastAction;
};

/**
 * Affiche un message : son texte, puis son ton, toujours donné. Le texte dit ce
 * qui s'est passé et à quoi, en une phrase finie par un point ; une seconde dit
 * la suite, ou quoi faire.
 */
export type ToastShow = (text: string, tone: ToastTone, options?: ToastShowOptions) => void;

// Trois formes qui ne se confondent pas, même sans la couleur.
const ICONS = {
  success: CircleCheck,
  error: CircleX,
  info: Info,
} satisfies Record<ToastTone, typeof Info>;

/** Le message d'une page, un à la fois : le suivant remplace celui qui est à l'écran. */
export function useAppToast() {
  const [toast, setToast] = useState<ToastMessage | null>(null);
  const id = useRef(0);

  const show = useCallback<ToastShow>((text, tone, options) => {
    id.current += 1;
    setToast({ id: id.current, text, tone, action: options?.action });
  }, []);
  const dismiss = useCallback(() => setToast(null), []);

  return { toast, show, dismiss };
}

function useDocumentHidden(): boolean {
  const [hidden, setHidden] = useState(() => document.hidden);
  useEffect(() => {
    const sync = () => setHidden(document.hidden);
    document.addEventListener("visibilitychange", sync);
    return () => document.removeEventListener("visibilitychange", sync);
  }, []);
  return hidden;
}

/**
 * Le message et son compte à rebours. Il s'arrête tant que le pointeur est
 * dessus, que le clavier est dedans ou que l'onglet est caché : un message ne
 * part pas pendant qu'on le lit, ni sans avoir été vu.
 */
function Toast({ toast, onDismiss }: { toast: ToastMessage; onDismiss: () => void }) {
  const hidden = useDocumentHidden();
  const [hovered, setHovered] = useState(false);
  const [focused, setFocused] = useState(false);
  const held = hidden || hovered || focused;
  const clock = useRef<ToastClock | null>(null);
  const dismissRef = useRef(onDismiss);
  dismissRef.current = onDismiss;
  const duration = toastDuration(toast.text, toast.tone, Boolean(toast.action));

  useEffect(() => {
    const now = Date.now();
    const current = clock.current ?? startClock(duration, now, held);
    if (held) {
      clock.current = pauseClock(current, now);
      return;
    }
    clock.current = resumeClock(current, now);
    const timer = window.setTimeout(() => dismissRef.current(), clockLeft(clock.current, now));
    return () => window.clearTimeout(timer);
  }, [duration, held]);

  const onBlur = (event: FocusEvent<HTMLDivElement>) => {
    if (!event.currentTarget.contains(event.relatedTarget)) setFocused(false);
  };
  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key !== "Escape") return;
    event.stopPropagation();
    onDismiss();
  };

  const Icon = ICONS[toast.tone];
  const action = toast.action;
  return (
    <div
      className={`ui-toast is-${toast.tone}`}
      // Un échec s'annonce tout de suite. `aria-live` est écrit en toutes lettres :
      // une fenêtre de Radix qui s'ouvre cache aux lecteurs d'écran tout le reste,
      // sauf ce qui le porte.
      {...(toast.tone === "error" ? { role: "alert", "aria-live": "assertive" as const } : {})}
      onPointerEnter={() => setHovered(true)}
      onPointerLeave={() => setHovered(false)}
      onFocus={() => setFocused(true)}
      onBlur={onBlur}
      onKeyDown={onKeyDown}
    >
      <span className="ui-toast-icon" role="img" aria-label={TONE_LABEL[toast.tone]}>
        <Icon size={16} strokeWidth={2} aria-hidden="true" />
      </span>
      <div className="ui-toast-body">
        <p className="ui-toast-copy">{toast.text}</p>
        {action ? (
          <button
            type="button"
            className="ui-toast-action"
            onClick={() => {
              action.onClick();
              onDismiss();
            }}
          >
            {action.label}
          </button>
        ) : null}
      </div>
      <button type="button" className="ui-toast-close" aria-label="Fermer le message" onClick={onDismiss}>
        <X size={16} strokeWidth={1.75} aria-hidden="true" />
      </button>
    </div>
  );
}

/**
 * Le message d'une page, en bas à droite de l'écran. Il se dessine hors de la
 * page, au-dessus de tout : une fenêtre ouverte ne le cache pas, ni à l'œil, ni
 * aux lecteurs d'écran.
 */
export function AppToast({ toast, onDismiss }: { toast: ToastMessage | null; onDismiss: () => void }) {
  const region = useRef<HTMLDivElement>(null);

  // Une fenêtre de Radix se ferme sur un clic hors d'elle : un clic sur le
  // message, pour le fermer ou pour « Annuler », n'en est pas un.
  useEffect(() => {
    const node = region.current;
    if (!node) return;
    const keep = (event: Event) => event.stopPropagation();
    node.addEventListener("pointerdown", keep);
    return () => node.removeEventListener("pointerdown", keep);
  }, []);

  const failure = toast?.tone === "error";
  return createPortal(
    <div className="ui-toast-region" ref={region}>
      {/* Toujours là, même vide : un lecteur d'écran n'annonce bien que ce qui arrive dans une zone qu'il connaît déjà. */}
      <div role="status" aria-live="polite">
        {toast && !failure ? <Toast key={toast.id} toast={toast} onDismiss={onDismiss} /> : null}
      </div>
      {toast && failure ? <Toast key={toast.id} toast={toast} onDismiss={onDismiss} /> : null}
    </div>,
    document.body,
  );
}
