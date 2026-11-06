// SRC-008 WAIT-1: the cold-start screen's pure parts. Time is passed in, never read.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { bakedHall } from "../hall3d/hall.ts";
import { bakedSeatMap, retryDelay, screenLines } from "./wakeup.ts";

const meta = JSON.parse(readFileSync(new URL("../../../public/halls/hall3.json", import.meta.url), "utf8"));

test("the synthetic seat map puts every baked seat on the baked hall, all free, named by category, no price", () => {
  const map = bakedSeatMap(meta);
  assert.equal(map.seats.length, meta.seats.length);
  assert.ok(bakedHall(map.seats, meta), "every seat matches the bake by row and number");
  assert.ok(map.seats.every((s) => s.state === "available" && s.is_active && s.price_paise === 0));
  assert.deepEqual(map.categories.map((c) => c.name).sort(), ["Premium", "Recliner", "Standard"]);
  const name = new Map(map.categories.map((c) => [c.id, c.name]));
  const r = meta.seats.findIndex((s) => s.cat === "R");
  assert.equal(name.get(map.seats[r].cat), "Recliner");
});

test("the countdown runs 90 s, then says it is still starting instead of lying", () => {
  assert.equal(screenLines(0).clock, "1:30");
  assert.equal(screenLines(31_500).clock, "0:59");
  assert.match(screenLines(30_000).title, /Waking up/);
  assert.equal(screenLines(90_000).clock, "0:00");
  assert.match(screenLines(400_000).title, /Still starting/);
});

test("the readiness checks back off and never come faster than 1.5 s or slower than 8 s", () => {
  assert.deepEqual([0, 1, 2, 3, 9].map(retryDelay), [1500, 2250, 3375, 5062.5, 8000]);
});
