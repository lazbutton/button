import { useEffect, useState } from "react";
import { ApiAuthError, ApiForbiddenError, ApiRequestError, apiGet } from "../api/client";
import { HOSTS_DOWN, HOSTS_OUTDATED, HOSTS_SESSION, hostNamesFromUsers } from "../api/hosts";
import type { HostsResponse, UsersResponse } from "../api/types";

export type HostList = { names: string[]; note: string };

/**
 * Les comptes qu'on peut nommer animateur, relus à chaque ouverture du choix.
 * `note` dit pourquoi la liste manque, quand elle manque.
 */
export function useHosts(open: boolean): HostList {
  const [list, setList] = useState<HostList>({ names: [], note: "" });
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    void loadHosts().then((next) => {
      if (!cancelled) setList(next);
    });
    return () => {
      cancelled = true;
    };
  }, [open]);
  return list;
}

function failure(caught: unknown): HostList {
  return { names: [], note: caught instanceof ApiAuthError ? HOSTS_SESSION : HOSTS_DOWN };
}

/** Un moteur plus ancien n'a pas `/users/hosts.json` : il répond 404, et la liste des comptes, réservée aux admins, prend le relais. */
async function loadHosts(): Promise<HostList> {
  try {
    const { hosts } = await apiGet<HostsResponse>("/users/hosts.json");
    return { names: hosts, note: "" };
  } catch (caught) {
    if (!(caught instanceof ApiRequestError && caught.status === 404)) return failure(caught);
  }
  try {
    const { users } = await apiGet<UsersResponse>("/users.json");
    return { names: hostNamesFromUsers(users), note: "" };
  } catch (caught) {
    return caught instanceof ApiForbiddenError ? { names: [], note: HOSTS_OUTDATED } : failure(caught);
  }
}
