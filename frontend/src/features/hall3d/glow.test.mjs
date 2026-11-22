// The screen's light (screenGlow.ts): the halves are averaged separately and the brightness follows the picture.
import assert from "node:assert/strict";
import { test } from "node:test";
import { glowOf } from "./screenGlow.ts";

const grid = (w, h, at) => Uint8ClampedArray.from({ length: w * h * 4 }, (_, i) => at(i >> 2 & 0, (i >> 2) % w)[i % 4]);

test("a picture red on the left and blue on the right casts red from the left half and blue from the right", () => {
  const g = glowOf(grid(4, 2, (_, x) => (x < 2 ? [255, 0, 0, 255] : [0, 0, 255, 255])), 4, 2);
  assert.deepEqual(g.left, [1, 0, 0]);
  assert.deepEqual(g.right, [0, 0, 1]);
});

test("a white picture is bright and a black one is dark", () => {
  assert.ok(Math.abs(glowOf(grid(2, 2, () => [255, 255, 255, 255]), 2, 2).luma - 1) < 1e-9);
  assert.equal(glowOf(grid(2, 2, () => [0, 0, 0, 255]), 2, 2).luma, 0);
});
