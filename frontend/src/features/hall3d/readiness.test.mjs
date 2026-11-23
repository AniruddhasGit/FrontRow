// The hall's one readiness status (owner, 2026-11-23: nothing spawns in while the camera moves; every wait has an exit).
// Run: node --test frontend/src/features/hall3d/readiness.test.mjs
import assert from "node:assert/strict";
import { test } from "node:test";
import { HALL_CAP_MS, readiness, settled } from "./readiness.ts";

const REQ = ["room"];

test("loading until every part has answered, then ready", () => {
  assert.equal(readiness({ room: "loaded", still: "loading", env: "loaded" }, 100, REQ), "loading");
  assert.equal(readiness({ room: "loaded", still: "loaded", env: "loaded" }, 100, REQ), "ready");
});

test("an optional part that fails does not block: ready with its default", () => {
  assert.equal(readiness({ room: "loaded", still: "failed", env: "failed" }, 100, REQ), "ready");
});

test("a required part that fails sends the page to its fallback at once", () => {
  assert.equal(readiness({ room: "failed", still: "loading" }, 100, REQ), "failed");
});

test("the cap: an optional part still out is dropped, a required one still out is a failure", () => {
  assert.equal(readiness({ room: "loaded", env: "loading" }, HALL_CAP_MS - 1, REQ), "loading");
  assert.equal(readiness({ room: "loaded", env: "loading" }, HALL_CAP_MS, REQ), "capped");
  assert.equal(readiness({ room: "loading", env: "loaded" }, HALL_CAP_MS, REQ), "failed");
});

test("only ready and capped may draw", () => {
  assert.deepEqual(["loading", "ready", "capped", "failed"].map(settled), [false, true, true, false]);
});
