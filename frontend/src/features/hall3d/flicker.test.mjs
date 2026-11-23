// Run: node --test frontend/src/features/hall3d/flicker.test.mjs
import assert from "node:assert/strict";
import { test } from "node:test";
import { FLICKER_S, flickerLevel } from "./flicker.ts";

test("dark at the change, stutters, then full by the end and after", () => {
  assert.ok(flickerLevel(0) < 0.1);
  assert.ok(flickerLevel(0.22) > 0.5 && flickerLevel(0.3) < 0.3);
  assert.ok(flickerLevel(0.7) > 0.8 && flickerLevel(0.7) < 1);
  assert.equal(flickerLevel(FLICKER_S), 1);
  assert.equal(flickerLevel(5), 1);
});

test("never outside 0..1, and a bad time is simply full", () => {
  for (let t = 0; t < 1.2; t += 0.01) assert.ok(flickerLevel(t) >= 0 && flickerLevel(t) <= 1);
  assert.equal(flickerLevel(Number.NaN), 1);
  assert.equal(flickerLevel(-1), 1);
});
