import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { apiGet } from "./client";
import { canBroadcast, roleFromPermissions, type Role } from "./roles";
import type { UserPermissions } from "./types";

export type Account = {
  username: string;
  permissions: UserPermissions;
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

export function AccountProvider({ children }: { children: ReactNode }) {
  const [account, setAccount] = useState<Account | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void apiGet<Account>("/account.json")
      .then((payload) => {
        if (!cancelled) setAccount(payload);
      })
      .catch(() => {
        if (!cancelled) setAccount(null);
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
