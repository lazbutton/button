import { Button, Text, TextField } from "@radix-ui/themes";
import { useState, type FormEvent } from "react";
import { apiPut, ApiRequestError } from "../api/client";
import { emissionWindowLabel } from "../api/emissionMeta";
import { slotsForHost } from "../api/hostSlots";
import { ROLE_LABEL, canBroadcast as broadcastOf } from "../api/roles";
import { useAccount } from "../api/AccountContext";
import { useLogout } from "../api/SessionGate";
import type { EmissionsResponse } from "../api/types";
import { useApiJson } from "../api/useApiJson";
import { useAppearance } from "../lib/Appearance";
import type { AppearanceChoice } from "../lib/brand";
import { FormField } from "../ui/FormField";
import { Panel, SectionHeader } from "../ui/Panel";
import "../styles/pages/admin.css";

const APPEARANCE_OPTIONS: { id: AppearanceChoice; label: string }[] = [
  { id: "system", label: "Machine" },
  { id: "light", label: "Clair" },
  { id: "dark", label: "Sombre" },
];

const DAYS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"];

export function MonComptePage() {
  const { account, role, isAdmin } = useAccount();
  const { appearance, choice, setChoice } = useAppearance();
  const logout = useLogout();
  const emissions = useApiJson<EmissionsResponse>("/antenne/emissions.json");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState("");
  const username = account?.username ?? "";
  const slots = slotsForHost(emissions.data?.emissions, username);
  const direct = broadcastOf(account?.permissions);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (busy) return;
    if (!password.trim()) {
      setError("Saisis un mot de passe.");
      setDone("");
      return;
    }
    if (password !== confirm) {
      setError("Les deux mots de passe diffèrent.");
      setDone("");
      return;
    }
    setBusy(true);
    setError("");
    setDone("");
    try {
      await apiPut("/account.json", { password });
      setPassword("");
      setConfirm("");
      setDone("Mot de passe changé.");
    } catch (caught) {
      setError(caught instanceof ApiRequestError ? caught.message : "Changement impossible.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="admin-page admin-page--embedded">
      <Panel>
        <SectionHeader title={username || "Mon compte"} description={ROLE_LABEL[role]} />
        <p className="admin-account-line">
          {isAdmin
            ? "Un admin peut se brancher, même hors créneau."
            : direct
              ? "Tu peux passer en direct."
              : "Tu ne peux pas passer en direct."}
        </p>
        <h3 className="admin-account-title">Créneaux</h3>
        {emissions.error ? (
          <p role="alert">Les créneaux ne répondent pas. Réessaie, ou rouvre la page.</p>
        ) : slots.length === 0 ? (
          <p>Aucun créneau à ton nom.</p>
        ) : (
          <ul className="admin-slots">
            {slots.map((row) => (
              <li key={row.id}>
                {row.day_of_week != null ? `${DAYS[row.day_of_week]} · ` : ""}
                {emissionWindowLabel(row)} · {row.title}
              </li>
            ))}
          </ul>
        )}
        <h3 className="admin-account-title">Apparence</h3>
        <div className="admin-appearance" role="group" aria-label="Apparence">
          {APPEARANCE_OPTIONS.map((option) => (
            <button
              key={option.id}
              type="button"
              aria-pressed={choice === option.id}
              onClick={() => setChoice(option.id)}
            >
              {option.label}
            </button>
          ))}
        </div>
        <p className="admin-account-line">
          {choice === "system"
            ? `Suit cet appareil, ${appearance === "dark" ? "sombre" : "clair"} en ce moment.`
            : "Choix mémorisé sur cet appareil."}
        </p>
        <form className="admin-account-form" onSubmit={(event) => void submit(event)}>
          <h3 className="admin-account-title">Mot de passe</h3>
          <FormField label="Nouveau mot de passe">
            <TextField.Root
              className="ui-field-control"
              type="password"
              value={password}
              autoComplete="new-password"
              onChange={(event) => setPassword(event.target.value)}
            />
          </FormField>
          <FormField label="Confirmation">
            <TextField.Root
              className="ui-field-control"
              type="password"
              value={confirm}
              autoComplete="new-password"
              onChange={(event) => setConfirm(event.target.value)}
            />
          </FormField>
          {error ? (
            <Text size="2" color="red" role="alert">
              {error}
            </Text>
          ) : null}
          {done ? (
            <Text size="2" role="status">
              {done}
            </Text>
          ) : null}
          <div className="admin-account-actions">
            <Button type="submit" disabled={busy || !password || !confirm}>
              {busy ? "Enregistrement…" : "Changer le mot de passe"}
            </Button>
            <Button type="button" variant="soft" color="gray" onClick={logout}>
              Déconnexion
            </Button>
          </div>
        </form>
      </Panel>
    </div>
  );
}
