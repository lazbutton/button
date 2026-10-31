import assert from "node:assert/strict";
import test from "node:test";
import { hostChoices, hostNamesFromUsers } from "./hosts.ts";

test("un animateur est un admin, ou un compte qui peut passer en direct", () => {
  const users = [
    { id: 1, username: "ines", notes: "", permissions: { live: true, stream: true } },
    { id: 2, username: "jean-pierre", notes: "", permissions: { live: true } },
    { id: 3, username: "helene", notes: "", permissions: { admin: true } },
    { id: 4, username: "nadia", notes: "", permissions: { live: true, carts: true, autodj: true } },
  ];
  assert.deepEqual(hostNamesFromUsers(users), ["ines", "helene"]);
});

test("l'animateur déjà nommé reste au choix, et la liste se trie à la française", () => {
  assert.deepEqual(hostChoices(["zoé", "Émile", "ines"]), ["Émile", "ines", "zoé"]);
  // un compte qui ne peut plus passer en direct reste nommé tant qu'on ne change rien
  assert.deepEqual(hostChoices(["ines"], " parti "), ["ines", "parti"]);
  assert.deepEqual(hostChoices(["ines"], "ines"), ["ines"]);
  assert.deepEqual(hostChoices([]), []);
});
