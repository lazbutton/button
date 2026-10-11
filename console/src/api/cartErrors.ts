import { ApiForbiddenError, ApiRequestError, ApiUnavailableError } from "./client";

const BUSY = "Un ajout de sons est en cours : attends qu'il se termine.";

/** One import at a time: the page shows a single progress. */
export class BacBusyError extends Error {
  constructor() {
    super(BUSY);
    this.name = "BacBusyError";
  }
}

/** What went wrong with a bac, in French: the engine answers in English. */
export function bacErrorText(caught: unknown, fallback: string): string {
  if (caught instanceof BacBusyError) return BUSY;
  if (caught instanceof ApiForbiddenError) return "Il faut le rôle Programmateur pour modifier les bacs.";
  if (caught instanceof ApiUnavailableError) return "Le moteur ne répond pas. Réessaie dans un instant.";
  if (caught instanceof ApiRequestError) {
    if (/already exists/i.test(caught.message)) return "Un bac porte déjà ce nom.";
    if (/referenced by a clock/i.test(caught.message)) {
      return "Une horloge utilise ce bac : retire-le d'abord dans Programmation.";
    }
    return caught.message;
  }
  return fallback;
}

/** Clocks find a bac by its title, without case: two bacs cannot share one. */
export function titleTaken(title: string, others: string[]): boolean {
  const wanted = title.trim().toLocaleLowerCase("fr");
  return Boolean(wanted) && others.some((other) => other.trim().toLocaleLowerCase("fr") === wanted);
}
