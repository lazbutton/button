import { ApiForbiddenError, ApiRequestError, ApiUnavailableError } from "./client";
import { engineErrorText } from "./programmationView";

/** What went wrong while programming, in French. */
export function errorText(caught: unknown, fallback: string): string {
  if (caught instanceof ApiForbiddenError) return "Il faut le rôle Programmateur pour modifier la programmation.";
  if (caught instanceof ApiUnavailableError) return "Le moteur ne répond pas. Réessaie dans un instant.";
  if (caught instanceof ApiRequestError) return engineErrorText(caught.message, fallback);
  return fallback;
}
