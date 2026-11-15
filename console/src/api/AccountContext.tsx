import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { apiGet } from "./client";
import { canBroadcast, roleFromPermissions, type Role } from "./roles";
import { rememberedUsername } from "./sessionUser";
import type { UserPermissions } from "./types";

export type Account = {
  username: string;
  permissions: UserPermissions;
  /** What the engine shows of a work in progress; absent from an older engine. */
  features?: {
    bank_tidy?: boolean;
    title_edits?: boolean;
    bank_moves?: boolean;
    bank_removals?: boolean;
    /** FON-74: the table gives the station's tags. */
    station_tags?: boolean;
    title_renames?: boolean;
    bank_health?: boolean;
    bank_arrivals?: boolean;
  };
};

type AccountValue = {
  account: Account | null;
  ready: boolean;
  role: Role;
  canBroadcast: boolean;
  isAdmin: boolean;
};

const AccountContext = createContext<AccountValue>({
  account: null,
  ready: false,
  role: "animateur",
  canBroadcast: false,
  isAdmin: false,
});

type UserRow = {
  username: string;
  permissions: UserPermissions;
};

async function loadAccount(): Promise<Account | null> {
  try {
    return await apiGet<Account>("/account.json");
  } catch {
    /* Moteur ancien : pas de /account.json — repli via users.json + identifiant mémorisé. */
  }
  const username = rememberedUsername();
  if (!username) return null;
  try {
    const data = await apiGet<{ users: UserRow[] }>("/users.json");
    const row = data.users.find((user) => user.username === username);
    if (!row) return null;
    return { username: row.username, permissions: row.permissions };
  } catch {
    return null;
  }
}

export function AccountProvider({ children }: { children: ReactNode }) {
  const [account, setAccount] = useState<Account | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void loadAccount()
      .then((payload) => {
        if (!cancelled) setAccount(payload);
      })
      .finally(() => {
        if (!cancelled) setReady(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const role = roleFromPermissions(account?.permissions);
  const broadcast = canBroadcast(account?.permissions);
  const isAdmin = role === "admin";
  return (
    <AccountContext.Provider value={{ account, ready, role, canBroadcast: broadcast, isAdmin }}>
      {children}
    </AccountContext.Provider>
  );
}

export function useAccount(): AccountValue {
  return useContext(AccountContext);
}
