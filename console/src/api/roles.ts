import type { UserPermissions } from "./types";

export type Role = "animateur" | "programmateur" | "admin";

export const ROLE_LABEL: Record<Role, string> = {
  animateur: "Animateur",
  programmateur: "Programmateur",
  admin: "Admin",
};

const RANK: Record<Role, number> = {
  animateur: 0,
  programmateur: 1,
  admin: 2,
};

export function roleAtLeast(role: Role, min: Role): boolean {
  return RANK[role] >= RANK[min];
}

/** Lecture inverse : admin, sinon carts ou autodj, sinon animateur. */
export function roleFromPermissions(permissions: UserPermissions | null | undefined): Role {
  const flags = permissions ?? {};
  if (flags.admin) return "admin";
  if (flags.carts || flags.autodj) return "programmateur";
  return "animateur";
}

/** Interrupteur « Peut passer en direct ». */
export function canBroadcast(permissions: UserPermissions | null | undefined): boolean {
  return permissions?.stream === true;
}

/** Admins et comptes dont l’interrupteur est allumé. */
export function listedAsHost(permissions: UserPermissions | null | undefined): boolean {
  return roleFromPermissions(permissions) === "admin" || canBroadcast(permissions);
}

/** Traduction rôle → drapeaux. not_audio n’est jamais posé. */
export function permissionsFromRole(role: Role, broadcast: boolean): UserPermissions {
  const permissions: UserPermissions = {};
  if (role === "admin") permissions.admin = true;
  if (role === "programmateur") {
    permissions.live = true;
    permissions.carts = true;
    permissions.autodj = true;
  }
  if (role === "animateur") permissions.live = true;
  if (broadcast) {
    permissions.stream = true;
    permissions.live = true;
  }
  return permissions;
}
