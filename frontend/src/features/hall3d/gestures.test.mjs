// Run: node --test frontend/src/features/hall3d/gestures.test.mjs
import assert from "node:assert/strict";
import { test } from "node:test";
import { seatAction } from "./gestures.ts";

test("one click only looks, whatever the seat", () => {
  for (const v of ["available", "held_by_me", "held_by_other", "sold"]) assert.equal(seatAction("click", v, true), "look");
});

test("a double click chooses a free seat, and never un-chooses or takes a closed one", () => {
  assert.equal(seatAction("double", "available", true), "choose");
  assert.equal(seatAction("double", "held_by_me", true), "none");
  assert.equal(seatAction("double", "available", false), "none");
  assert.equal(seatAction("double", "sold", false), "none");
});

test("a right click takes back only a seat that is yours", () => {
  assert.equal(seatAction("right", "held_by_me", true), "unchoose");
  assert.equal(seatAction("right", "available", true), "none");
  assert.equal(seatAction("right", "held_by_other", false), "none");
});
