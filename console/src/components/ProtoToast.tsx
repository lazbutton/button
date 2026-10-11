import {
  AppToast,
  type ToastShowOptions,
  type ToastTone,
  useAppToast,
} from "../ui/AppToast";

export function useProtoToast() {
  const { toast, show: emit, dismiss } = useAppToast();
  const show = (text: string, tone?: ToastTone, options?: ToastShowOptions) => {
    const inferred =
      tone ??
      (/impossible|injoignable|incorrect|expirée|requis|pas le droit|invalide/i.test(text)
        ? "error"
        : /cré|enregistr|import|supprim|envoy|ajout|retir|réordonn|annul/i.test(text)
          ? "success"
          : "info");
    emit(text, inferred, options);
  };
  return { message: toast, show, dismiss };
}

export function ProtoToast({
  message,
  onDismiss,
}: {
  message: ReturnType<typeof useAppToast>["toast"];
  onDismiss?: () => void;
}) {
  return <AppToast toast={message} onDismiss={onDismiss} />;
}
