// CR-010 L1: the per-seat spherical-harmonic light (seatLight.ts). Run with the rest: node --test.
import assert from "node:assert/strict";
import { test } from "node:test";
import { SH_TEXELS, evalSH, packSH, seatIrradiance } from "./seatLight.ts";

// A uniform environment of radiance 1: the cosine-convolved, /pi DC coefficient is 1 / 0.282095, so E/pi = 1 for any n.
const flat = (v) => [1 / 0.282095, 1 / 0.282095, 1 / 0.282095].map((x) => x * v).concat(Array(24).fill(0));

test("a uniform room gives the same light to every normal", () => {
  for (const n of [[0, 1, 0], [1, 0, 0], [0, 0, -1]]) {
    evalSH(flat(1), n).forEach((v) => assert.ok(Math.abs(v - 1) < 1e-5));
  }
});

test("light from above (the L1 y term) lights an upward face, not a downward one", () => {
  const c = Array(27).fill(0);
  for (let ch = 0; ch < 3; ch++) { c[ch] = 1; c[3 + ch] = 1; } // DC + y
  assert.ok(evalSH(c, [0, 1, 0])[0] > evalSH(c, [0, -1, 0])[0]);
});

test("the seat's light blends from its LO probe to its HI probe by height, clamped outside", () => {
  const s = { y: [1, 2], lo: flat(0.2), hi: flat(1) };
  assert.ok(Math.abs(seatIrradiance(s, [0, 1, 0], 0.5)[0] - 0.2) < 1e-5);
  assert.ok(Math.abs(seatIrradiance(s, [0, 1, 0], 1.5)[0] - 0.6) < 1e-5);
  assert.ok(Math.abs(seatIrradiance(s, [0, 1, 0], 3)[0] - 1) < 1e-5);
});

test("packing: one row of 19 RGBA texels per instance, in instance order; a seat without probes gets a dim fill", () => {
  const a = { y: [0.5, 1.5], lo: [...Array(27).keys()], hi: [...Array(27).keys()].map((k) => 100 + k) };
  const p = packSH([a, undefined]);
  assert.equal(p.length, 2 * SH_TEXELS * 4);
  assert.deepEqual([...p.slice(0, 4)], [0, 1, 2, 0]); // LO coefficient 0, RGB
  assert.deepEqual([...p.slice(9 * 4, 9 * 4 + 3)], [100, 101, 102]); // HI coefficient 0
  assert.deepEqual([...p.slice(18 * 4, 18 * 4 + 2)], [0.5, 1.5]); // the probe heights
  const row1 = SH_TEXELS * 4;
  assert.ok(Math.abs(p[row1] - 0.05) < 1e-6 && p[row1 + 4] === 0); // fallback: DC only
});
