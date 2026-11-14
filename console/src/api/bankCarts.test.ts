import assert from "node:assert/strict";
import test from "node:test";
import { addedToCart, cartsBeforeRemoval, cartsThatTake } from "./bankCarts.ts";

test("a relay takes no title, and the carts come by name", () => {
  const carts = [
    { id: 1, title: "Soirée", mode: "playlist" },
    { id: 2, title: "Flux", mode: "relay" },
    { id: 3, title: "Aube", mode: "random" },
  ];
  assert.deepEqual(
    cartsThatTake(carts).map((cart) => cart.id),
    [3, 1],
  );
});

test("before a removal, the carts that play the titles are named", () => {
  assert.equal(cartsBeforeRemoval([{ title: "Comète", path: "10-rotation/c.mp3", carts: [] }]), "");
  assert.equal(
    cartsBeforeRemoval([{ title: "Comète", path: "10-rotation/c.mp3", carts: [{ id: 1, title: "Soirée" }] }]),
    "« Comète » est joué par le bac « Soirée » : son son y restera, « Indisponible », jusqu'à ce qu'on le retire du bac.",
  );
  assert.equal(
    cartsBeforeRemoval([
      { title: "A", path: "a.mp3", carts: [{ id: 1, title: "Soirée" }] },
      { title: "B", path: "b.mp3", carts: [{ id: 2, title: "Nuit" }, { id: 1, title: "Soirée" }] },
      { title: "C", path: "c.mp3" },
    ]),
    "2 de ces titres sont joués par les bacs « Soirée » et « Nuit » : leurs sons y resteront, « Indisponible », jusqu'à ce qu'on les retire des bacs.",
  );
});

test("what an addition did, in a toast", () => {
  assert.deepEqual(addedToCart(3, 3, "Soirée"), {
    text: "3 titres de la banque ajoutés au bac « Soirée », sans copie.",
    tone: "success",
  });
  assert.deepEqual(addedToCart(1, 2, "Soirée"), {
    text: "1 titre de la banque ajouté au bac « Soirée », sans copie. Un autre y était déjà.",
    tone: "success",
  });
  assert.equal(addedToCart(0, 2, "Soirée").tone, "info");
});
