import { Button, Spinner, Text } from "@radix-ui/themes";
import { Trash2 } from "lucide-react";
import { useState } from "react";
import { ApiRequestError, apiGet, apiPostJson } from "../../api/client";
import {
  FICHES_VERDICTS_ERASE_JSON,
  FICHES_VERDICTS_JSON,
  count,
  eraseQuestion,
  fichesErrorText,
  type VerdictSummary,
} from "../../api/fiches";
import { TITLES_SEND_DEADLINE_MS } from "../../api/sendDeadline";
import { ConfirmDialog } from "../../ui/ConfirmDialog";

function messageOf(caught: unknown, fallback: string): string {
  if (caught instanceof ApiRequestError && caught.status === 404) {
    return "Mets à jour le moteur pour effacer les verdicts ici.";
  }
  return fichesErrorText(caught, fallback, "Réservé à un admin. Reconnecte-toi avec ce compte.");
}

/**
 * Réglages → Fiches → « Effacer les verdicts » (FON-28), pour un admin : retire le
 * verdict et sa source de toute la bibliothèque, et les verdicts en attente. Les
 * sélections qui lisent `fmg` se videront : elles sont nommées avant de confirmer.
 */
export function VerdictEraser() {
  const [summary, setSummary] = useState<VerdictSummary | null>(null);
  const [preparing, setPreparing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState("");

  const prepare = async () => {
    if (preparing || busy) return;
    setPreparing(true);
    setError("");
    setDone("");
    try {
      setSummary(await apiGet<VerdictSummary>(FICHES_VERDICTS_JSON));
    } catch (caught) {
      setError(messageOf(caught, "Les verdicts ne se sont pas lus. Réessaie."));
    } finally {
      setPreparing(false);
    }
  };

  const erase = async () => {
    setBusy(true);
    try {
      const result = await apiPostJson<VerdictSummary>(FICHES_VERDICTS_ERASE_JSON, {}, TITLES_SEND_DEADLINE_MS);
      setDone(
        result.titles
          ? `Verdicts effacés de ${count(result.titles)} titre${result.titles === 1 ? "" : "s"}.`
          : "Aucun titre n'avait de verdict : rien n'a changé.",
      );
    } catch (caught) {
      setError(messageOf(caught, "Les verdicts ne se sont pas effacés. Réessaie."));
    } finally {
      setBusy(false);
      setSummary(null);
    }
  };

  return (
    <section className="reglages-card reglages-fieldset is-danger" aria-labelledby="verdict-eraser-title">
      <h3 id="verdict-eraser-title" className="reglages-card-title">
        Effacer les verdicts
      </h3>
      <p className="reglages-card-description">
        Retire le verdict « femme ou minorité de genre » et sa source de toute la bibliothèque, avec les verdicts qui
        attendent d’être relus. Les sélections de titres qui le lisent se videront : elles sont nommées avant de
        confirmer. Les fichiers ne changent pas.
      </p>
      {error ? (
        <Text as="p" size="2" color="red" role="alert">
          {error}
        </Text>
      ) : null}
      <p className="reglages-savebar-status" role="status">
        {done}
      </p>
      <div className="reglages-actions">
        <Button type="button" color="red" variant="soft" aria-busy={preparing} onClick={() => void prepare()}>
          {preparing ? <Spinner size="1" /> : <Trash2 className="ui-button-icon" />}
          Effacer les verdicts…
        </Button>
      </div>
      <ConfirmDialog
        open={summary != null}
        onOpenChange={(next) => {
          if (!next && !busy) setSummary(null);
        }}
        busy={busy}
        title="Effacer les verdicts de la bibliothèque ?"
        description={summary ? eraseQuestion(summary) : ""}
        confirmLabel="Effacer les verdicts"
        cancelLabel="Garder"
        onConfirm={erase}
      />
    </section>
  );
}
