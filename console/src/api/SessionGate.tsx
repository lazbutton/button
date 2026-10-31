import { Spinner, TextField } from "@radix-ui/themes";
import { Eye, EyeOff } from "lucide-react";
import { createContext, useCallback, useContext, useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { ErrorState, LoadingState } from "../ui/DataState";
import { FormField } from "../ui/FormField";
import { AccountProvider } from "./AccountContext";
import { ApiAuthError, ApiUnavailableError, apiLogin, apiLogout, apiProbeSession } from "./client";
import { cookieRefused, cookieRefusedMessage } from "./sessionCookie";
import { LOGOUT_UNREACHED_MESSAGE } from "./sessionLogout";
import { forgetUsername, rememberUsername } from "./sessionUser";
import type { ApiLoadError } from "./useApiJson";
import { label } from "../lib/brand";
import { useBrand } from "../lib/BrandContext";

type SessionGateProps = {
  loading: boolean;
  error: ApiLoadError | null;
  onRetry: () => void;
  children: ReactNode;
  cover?: boolean;
  ready?: boolean;
  /** Ce que dit d'abord le formulaire de connexion, comme une déconnexion qui n'a pas abouti. */
  notice?: string | null;
};

export function SessionGate({
  loading,
  error,
  onRetry,
  children,
  cover = false,
  ready = false,
  notice = null,
}: SessionGateProps) {
  if (error === "auth") return <StudioLogin onLoggedIn={onRetry} notice={notice} />;
  if (error === "down" && !ready) {
    return (
      <ErrorState
        cover
        title="Radiotomate est indisponible"
        description="L’automate ne répond pas. Réessaie. Si ça continue, un admin regarde Réglages → Automate."
        onRetry={onRetry}
      />
    );
  }
  if (loading && !ready) {
    return (
      <LoadingState
        cover={cover}
        label={cover ? "Chargement de Radiotomate…" : "Chargement…"}
      />
    );
  }
  return children;
}

const LogoutContext = createContext<() => void>(() => {});

export function useLogout(): () => void {
  return useContext(LogoutContext);
}

export function ApiSession({ children }: { children: ReactNode }) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ApiLoadError | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const readyRef = useRef(false);
  // Une déconnexion à la fois : une seconde, réglée plus tard, rendrait l'écran
  // de connexion à une session rouverte entre-temps.
  const leavingRef = useRef(false);

  const retry = useCallback(() => {
    setError(null);
    setNotice(null);
    if (!readyRef.current) setLoading(true);
    void apiProbeSession()
      .then(() => {
        readyRef.current = true;
        setError(null);
      })
      .catch((caught) => {
        setError(caught instanceof ApiAuthError ? "auth" : "down");
      })
      .finally(() => {
        setLoading(false);
      });
  }, []);

  const logout = useCallback(() => {
    if (leavingRef.current) return;
    leavingRef.current = true;
    void apiLogout().then((reached) => {
      leavingRef.current = false;
      forgetUsername();
      readyRef.current = false;
      setNotice(reached ? null : LOGOUT_UNREACHED_MESSAGE);
      setError("auth");
      setLoading(false);
    });
  }, []);

  useEffect(() => {
    retry();
  }, [retry]);

  return (
    <LogoutContext.Provider value={logout}>
      <SessionGate cover loading={loading} error={error} onRetry={retry} notice={notice}>
        <AccountProvider>{children}</AccountProvider>
      </SessionGate>
    </LogoutContext.Provider>
  );
}

function StudioLogin({ onLoggedIn, notice }: { onLoggedIn: () => void; notice: string | null }) {
  const brand = useBrand();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [busy, setBusy] = useState(false);
  // L'avis tient jusqu'au premier envoi du formulaire.
  const [fail, setFail] = useState<string | null>(notice);
  const subtitle = label(brand, "automate", "subtitle") || "Console d’antenne";

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setFail(null);
    try {
      await apiLogin(username, password);
      rememberUsername(username);
      if (await cookieRefused(apiProbeSession, (caught) => caught instanceof ApiAuthError)) {
        setFail(cookieRefusedMessage(window.location.protocol, navigator.cookieEnabled));
        return;
      }
      onLoggedIn();
    } catch (caught) {
      if (caught instanceof ApiUnavailableError) {
        setFail("L’automate ne répond pas. Vérifie qu’il tourne, puis réessaie.");
      } else if (caught instanceof ApiAuthError) {
        setFail("Identifiant ou mot de passe incorrect. Réessaie, ou demande à un admin de le réinitialiser.");
      } else {
        setFail("Connexion impossible. Réessaie.");
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="app-login-shell">
      <div className="app-login">
        <header className="app-login-brand">
          <img className="app-login-mark" src="/logo.svg" alt="" width={48} height={48} />
          <div>
            <p className="app-login-kicker">{subtitle}</p>
            <h1 className="app-login-title">{brand.suite.name}</h1>
          </div>
        </header>
        <form className="app-login-card" onSubmit={submit}>
          <p className="app-login-copy">Entre avec ton compte pour ouvrir la console.</p>
          <FormField label="Identifiant">
            <TextField.Root
              className="ui-field-control"
              name="username"
              size="3"
              autoComplete="username"
              autoFocus
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
            />
          </FormField>
          <FormField label="Mot de passe">
            <TextField.Root
              className="ui-field-control"
              name="password"
              size="3"
              type={showPassword ? "text" : "password"}
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            >
              <TextField.Slot side="right">
                <button
                  type="button"
                  className="app-login-reveal"
                  aria-pressed={showPassword}
                  aria-label={showPassword ? "Masquer le mot de passe" : "Afficher le mot de passe"}
                  onClick={() => setShowPassword((shown) => !shown)}
                >
                  {showPassword ? <EyeOff size={16} aria-hidden="true" /> : <Eye size={16} aria-hidden="true" />}
                </button>
              </TextField.Slot>
            </TextField.Root>
          </FormField>
          {fail ? (
            <p className="app-login-alert" role="alert">
              {fail}
            </p>
          ) : null}
          <button className="app-login-submit" type="submit" disabled={busy}>
            {busy ? <Spinner size="2" /> : null}
            {busy ? "Connexion…" : "Se connecter"}
          </button>
        </form>
      </div>
    </div>
  );
}
