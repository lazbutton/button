import { Check, Copy } from "lucide-react";
import { useState } from "react";

/** Une valeur à coller dans l'encodeur : un clic la copie. */
export function CopyValue({ label, value }: { label: string; value: string }) {
  const [done, setDone] = useState(false);
  const [failed, setFailed] = useState(false);
  return (
    <>
      <button
        type="button"
        className="ant-copy"
        aria-label={`Copier ${label} : ${value}`}
        title="Copier"
        onClick={() => {
          // Pas de presse-papiers hors HTTPS, sauf sur localhost.
          if (!navigator.clipboard) {
            setFailed(true);
            return;
          }
          void navigator.clipboard.writeText(value).then(
            () => {
              setFailed(false);
              setDone(true);
              window.setTimeout(() => setDone(false), 1400);
            },
            () => setFailed(true),
          );
        }}
      >
        <code>{value}</code>
        {done ? <Check size={14} aria-hidden="true" /> : <Copy size={14} aria-hidden="true" />}
      </button>
      {failed ? (
        <span className="ant-copy-failed" role="status">
          Copie impossible ici : sélectionne le texte, puis copie-le.
        </span>
      ) : null}
    </>
  );
}
