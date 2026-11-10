import { Button, Text, TextField } from "@radix-ui/themes";
import { LogOut, Monitor, Moon, Sun, type LucideIcon } from "lucide-react";
import { useState, type FormEvent } from "react";
import { agendaPath, type AgendaResponse } from "../api/agenda";
import { addDays, parisWall, rangeLabel } from "../api/agendaView";
import { useAccount } from "../api/AccountContext";
import { apiPut, ApiRequestError } from "../api/client";
import { emissionWindowLabel } from "../api/emissionMeta";
import { slotsForHost } from "../api/hostSlots";
import { DAY_LONG } from "../api/programmationView";
import { ROLE_LABEL, canBroadcast as broadcastOf } from "../api/roles";
import { useLogout } from "../api/SessionGate";
import { initials } from "../api/topbar";
import type { EmissionsResponse } from "../api/types";
import { useApiJson } from "../api/useApiJson";
import { StreamToken } from "../components/antenne/StreamToken";
import { SettingsCard, SettingsHead } from "../components/reglages/SettingsCard";
import { APPEARANCE_OPTIONS, useAppearance } from "../lib/Appearance";
import type { AppearanceChoice } from "../lib/brand";
import { FormField } from "../ui/FormField";
import "../styles/pages/reglages.css";

const APPEARANCE_ICON: Record<AppearanceChoice, LucideIcon> = {
  system: Monitor,
  light: Sun,
  dark: Moon,
};

/** Réglages → Mon compte, pour chacun : qui il est, ses créneaux, son jeton, l'apparence, son mot de passe. */
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
  const today = parisWall(new Date()).day;
  const agenda = useApiJson<AgendaResponse>(agendaPath(today, addDays(today, 27)));
  const datedLives = (agenda.data?.diffusions ?? []).filter(
    (row) =>
      row.kind === "live" &&
      row.air_status === "upcoming" &&
      row.host_username.trim().toLowerCase() === username.trim().toLowerCase(),
  );
  const direct = broadcastOf(account?.permissions);
  // Une émission ne nomme au plateau qu'un admin ou un compte qui peut passer en direct.
  const host = isAdmin || direct;

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
    <div className="reglages-section">
      <SettingsHead
        title="Mon compte"
        description="Qui tu es à la radio, tes créneaux, l’apparence de la console et ton mot de passe."
      />
      <div className="reglages-stack reglages-stack--narrow">
        <section className="reglages-card reglages-profile">
          <span className="reglages-avatar is-large" aria-hidden="true">
            {initials(username)}
          </span>
          <div className="reglages-profile-copy">
            <h3 className="reglages-profile-name">{username || "Compte"}</h3>
            <p className="reglages-profile-meta">
              <span className="reglages-role">{ROLE_LABEL[role]}</span>{" "}
              {isAdmin
                ? "Tu peux te brancher en direct, même hors créneau."
                : direct
                  ? "Tu peux passer en direct."
                  : "Tu ne peux pas passer en direct. Un admin peut te l’ouvrir."}
            </p>
          </div>
          <Button type="button" variant="soft" color="gray" onClick={logout}>
            <LogOut className="ui-button-icon" aria-hidden="true" />
            Se déconnecter
          </Button>
        </section>

        {host || slots.length || datedLives.length ? (
          <SettingsCard
            title="Créneaux"
            description="Les émissions qui te nomment au plateau. Pendant chacune, l’antenne t’attend."
          >
            {emissions.error ? (
              <Text as="p" size="2" color="red" role="alert">
                Les créneaux ne répondent pas. Réessaie, ou rouvre la page.
              </Text>
            ) : slots.length === 0 ? (
              <p className="reglages-empty">Aucun créneau à ton nom.</p>
            ) : (
              <ul className="reglages-list">
                {slots.map((row) => (
                  <li key={row.id}>
                    <span className="reglages-list-when">
                      {row.day_of_week != null ? `${DAY_LONG[row.day_of_week]} · ` : ""}
                      {emissionWindowLabel(row)}
                    </span>{" "}
                    <span className="reglages-list-what">{row.title}</span>
                  </li>
                ))}
              </ul>
            )}
            {datedLives.length ? (
              <>
                <h4 className="reglages-subtitle">Directs datés</h4>
                <ul className="reglages-list">
                  {datedLives.map((row) => (
                    <li key={row.id}>
                      <span className="reglages-list-when">{rangeLabel(row.starts_at, row.ends_at)}</span>{" "}
                      <span className="reglages-list-what">{row.title}</span>
                    </li>
                  ))}
                </ul>
                <p className="reglages-note">Ton compte peut se brancher 15 min avant le début de chacun.</p>
              </>
            ) : null}
          </SettingsCard>
        ) : null}

        {host ? (
          <SettingsCard
            title="Jeton d’encodeur"
            description="Dans BUTT ou Mixxx : ton identifiant, puis ce jeton comme mot de passe. Le mot de passe du compte reste hors de l’encodeur."
          >
            <StreamToken owner="me" />
          </SettingsCard>
        ) : null}

        <SettingsCard title="Apparence" description="Sur cet appareil seulement.">
          <div className="reglages-segmented" role="group" aria-label="Apparence">
            {APPEARANCE_OPTIONS.map((option) => {
              const Icon = APPEARANCE_ICON[option.id];
              return (
                <button
                  key={option.id}
                  type="button"
                  aria-pressed={choice === option.id}
                  onClick={() => setChoice(option.id)}
                >
                  <Icon aria-hidden="true" />
                  {option.label}
                </button>
              );
            })}
          </div>
          <p className="reglages-note">
            {choice === "system"
              ? `Suit cet appareil, ${appearance === "dark" ? "sombre" : "clair"} en ce moment.`
              : "Choix mémorisé sur cet appareil."}
          </p>
        </SettingsCard>

        <SettingsCard
          title="Mot de passe"
          description={host ? "Pour entrer dans la console. L’encodeur a son jeton, à part." : "Pour entrer dans la console."}
        >
          <form className="reglages-form" onSubmit={(event) => void submit(event)}>
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
              <Text as="p" size="2" color="red" role="alert">
                {error}
              </Text>
            ) : null}
            {done ? (
              <Text as="p" size="2" role="status">
                {done}
              </Text>
            ) : null}
            <div className="reglages-actions">
              <Button type="submit" highContrast disabled={busy || !password || !confirm}>
                {busy ? "Enregistrement…" : "Changer le mot de passe"}
              </Button>
            </div>
          </form>
        </SettingsCard>
      </div>
    </div>
  );
}
