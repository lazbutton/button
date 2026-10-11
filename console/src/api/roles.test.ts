import assert from "node:assert/strict";
import test from "node:test";
import {
  canBroadcast,
  listedAsHost,
  permissionsFromRole,
  roleFromPermissions,
} from "./roles.ts";

test("lecture inverse", () => {
  assert.equal(roleFromPermissions({ admin: true, carts: true }), "admin");
  assert.equal(roleFromPermissions({ carts: true }), "programmateur");
  assert.equal(roleFromPermissions({ autodj: true }), "programmateur");
  assert.equal(roleFromPermissions({ live: true }), "animateur");
  assert.equal(roleFromPermissions({}), "animateur");
  assert.equal(roleFromPermissions(undefined), "animateur");
});

test("traduction rôle vers drapeaux", () => {
  assert.deepEqual(permissionsFromRole("animateur", false), { live: true });
  assert.deepEqual(permissionsFromRole("animateur", true), { live: true, stream: true });
  assert.deepEqual(permissionsFromRole("programmateur", false), {
    live: true,
    carts: true,
    autodj: true,
  });
  assert.deepEqual(permissionsFromRole("programmateur", true), {
    live: true,
    carts: true,
    autodj: true,
    stream: true,
  });
  assert.deepEqual(permissionsFromRole("admin", false), { admin: true });
  assert.deepEqual(permissionsFromRole("admin", true), {
    admin: true,
    live: true,
    stream: true,
  });
  for (const role of ["animateur", "programmateur", "admin"] as const) {
    assert.equal(permissionsFromRole(role, true).not_audio, undefined);
    assert.equal(permissionsFromRole(role, false).not_audio, undefined);
  }
});

test("interrupteur et liste des plateaux", () => {
  const animator = permissionsFromRole("animateur", true);
  assert.equal(canBroadcast(animator), true);
  assert.equal(listedAsHost(animator), true);
  assert.equal(listedAsHost(permissionsFromRole("animateur", false)), false);
  assert.equal(listedAsHost(permissionsFromRole("admin", false)), true);
  assert.equal(roleFromPermissions(animator), "animateur");
  assert.equal(canBroadcast(permissionsFromRole("programmateur", true)), true);
});
