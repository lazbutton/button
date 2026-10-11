import { CheckCircle2, CircleAlert, Info, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

export type ToastTone = "success" | "error" | "info";

export type ToastAction = {
  label: string;
  onClick: () => void;
};

export type ToastShowOptions = {
  duration?: number;
  action?: ToastAction;
};

export type ToastMessage = {
  id: number;
  text: string;
  tone: ToastTone;
  duration: number;
  action?: ToastAction;
};

const ICONS = {
  success: CheckCircle2,
  error: CircleAlert,
  info: Info,
} satisfies Record<ToastTone, typeof Info>;

export function useAppToast(defaultDuration = 3200) {
  const [toast, setToast] = useState<ToastMessage | null>(null);
  const id = useRef(0);

  const show = useCallback(
    (text: string, tone: ToastTone = "info", options?: ToastShowOptions) => {
      id.current += 1;
      setToast({
        id: id.current,
        text,
        tone,
        duration: options?.duration ?? defaultDuration,
        action: options?.action,
      });
    },
    [defaultDuration],
  );

  useEffect(() => {
    if (!toast) return;
    const timeout = window.setTimeout(() => setToast(null), toast.duration);
    return () => window.clearTimeout(timeout);
  }, [toast]);

  return { toast, show, dismiss: () => setToast(null) };
}

export function AppToast({
  toast,
  onDismiss,
}: {
  toast: ToastMessage | null;
  onDismiss?: () => void;
}) {
  if (!toast) return null;
  const Icon = ICONS[toast.tone];
  return (
    <div
      key={toast.id}
      className={`ui-toast is-${toast.tone}`}
      role={toast.tone === "error" ? "alert" : "status"}
    >
      <Icon size={17} strokeWidth={1.75} aria-hidden="true" />
      <span className="ui-toast-copy">{toast.text}</span>
      {toast.action ? (
        <button
          type="button"
          className="ui-toast-action"
          onClick={() => {
            toast.action?.onClick();
            onDismiss?.();
          }}
        >
          {toast.action.label}
        </button>
      ) : null}
      {onDismiss ? (
        <button
          type="button"
          className="ui-toast-close"
          aria-label="Fermer la notification"
          onClick={onDismiss}
        >
          <X size={15} strokeWidth={1.75} />
        </button>
      ) : null}
    </div>
  );
}
