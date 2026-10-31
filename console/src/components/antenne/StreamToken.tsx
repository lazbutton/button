import { Button, Spinner, Text } from "@radix-ui/themes";
import { useEffect, useState } from "react";
import { ApiAuthError, ApiForbiddenError, apiGet, apiPostJson, ApiRequestError } from "../../api/client";
import { streamTokenAction, streamTokenLine, type StreamTokenOwner } from "../../api/streamToken";
import type { NewStreamToken, StreamTokenState } from "../../api/types";
import { CopyValue } from "./CopyValue";
import "../../styles/pages/antenne.css";

type Loaded =
  | { status: "loading" }
  | { status: "ready"; createdAt: string | null }
  | { status: "outdated" }
  | { status: "failed"; message: string };

/** Un moteur plus ancien que la console n'a pas la route : il répond 404. */
function outdated(caught: unknown): boolean {
  return caught instanceof ApiRequestError && caught.status === 404;
}

function failure(caught: unknown, fallback: string): string {
  if (caught instanceof ApiAuthError) return "Session expirée : reconnecte-toi.";
  if (caught instanceof ApiForbiddenError) return "Ce compte n’a pas ce droit.";
  if (caught instanceof ApiRequestError) return caught.message;
  return fallback;
}

/**
 * Le jeton d'encodeur d'un compte : sa date, puis « Créer un jeton » ou « Renouveler ».
 * Un jeton neuf ne s'affiche qu'une fois, tant que ce bloc reste ouvert.
 */
export function StreamToken({ owner }: { owner: StreamTokenOwner }) {
  const [loaded, setLoaded] = useState<Loaded>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);
  const [fresh, setFresh] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    setLoaded({ status: "loading" });
    setFresh(null);
    setConfirming(false);
    setError("");
    apiGet<StreamTokenState>(`/users/${owner}/stream-token.json`).then(
      (state) => {
        if (!cancelled) setLoaded({ status: "ready", createdAt: state.created_at });
      },
      (caught: unknown) => {
        if (cancelled) return;
        setLoaded(
          outdated(caught)
            ? { status: "outdated" }
            : { status: "failed", message: failure(caught, "Le jeton ne répond pas.") },
        );
      },
    );
    return () => {
      cancelled = true;
    };
  }, [owner, attempt]);

  if (loaded.status === "loading") {
    return <p className="ant-token-line">Lecture du jeton…</p>;
  }
  if (loaded.status === "outdated") {
    return (
      <p className="ant-token-line">
        Mets à jour le moteur pour avoir un jeton d’encodeur. En attendant, l’encodeur prend le mot de passe du compte.
      </p>
    );
  }
  if (loaded.status === "failed") {
    return (
      <div className="ant-token">
        <Text as="p" size="2" color="red" role="alert">
          {loaded.message}
        </Text>
        <Button type="button" variant="soft" onClick={() => setAttempt((count) => count + 1)}>
          Réessayer
        </Button>
      </div>
    );
  }

  const createdAt = loaded.createdAt;
  const renew = async () => {
    if (busy) return;
    if (createdAt && !confirming) {
      setConfirming(true);
      return;
    }
    setBusy(true);
    setError("");
    try {
      const created = await apiPostJson<NewStreamToken>(`/users/${owner}/stream-token.json`, {});
      setFresh(created.token);
      setLoaded({ status: "ready", createdAt: created.created_at });
    } catch (caught) {
      if (outdated(caught)) setLoaded({ status: "outdated" });
      else setError(failure(caught, "Le jeton n’a pas pu être créé. Réessaie."));
    } finally {
      setBusy(false);
      setConfirming(false);
    }
  };

  return (
    <div className="ant-token">
      {fresh ? <CopyValue label="le jeton" value={fresh} /> : null}
      <p className="ant-token-line" role="status">
        {confirming
          ? "L’encodeur qui garde l’ancien jeton sera refusé à sa prochaine connexion."
          : fresh
            ? "Copie-le maintenant dans l’encodeur, comme mot de passe : il ne s’affichera plus."
            : streamTokenLine(createdAt)}
      </p>
      <div className="ant-token-actions">
        {/* Pas de disabled pendant l'envoi : un bouton désactivé perd le focus du clavier. */}
        <Button
          type="button"
          variant={confirming ? "solid" : "soft"}
          color={confirming ? "red" : undefined}
          highContrast={confirming}
          aria-busy={busy}
          onClick={() => void renew()}
        >
          {busy ? <Spinner size="1" /> : null}
          {streamTokenAction(createdAt, confirming)}
        </Button>
        {confirming ? (
          <Button type="button" variant="soft" color="gray" onClick={() => setConfirming(false)}>
            Annuler
          </Button>
        ) : null}
      </div>
      {error ? (
        <Text as="p" size="2" color="red" role="alert">
          {error}
        </Text>
      ) : null}
    </div>
  );
}
