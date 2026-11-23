// CR-014: the walk from the corridor into the hall (walk.ts) - the route's ends, the sampling, and the lenses.
// Run: node --test "src/**/*.test.mjs"
// Not asserted here (needs WebGL and a browser): how it looks; e2e/walk_cr014.mjs records that on video.
import assert from "node:assert/strict";
import { test } from "node:test";
import { NO_COVER, PICTURE_FOV, corridorFov, hallFov, seen, walkEase, walkRoute, walker } from "./walk.ts";

const corridor = { eye: [-9, 1.62, -3.4], look: [-4.75, 1.62, -3.4] };
const seats = { eye: [0, 3.55, -1], look: [0, 1.7, -10.9] };
const enter = [corridor, { eye: [-4.75, 1.62, -3.4], look: [-1.55, 1.55, -3.6] }, { eye: [-3.15, 1.7, -3.25], look: [0.6, 1.9, -6.4] }, seats];
const near = (a, b, eps = 1e-6) => a.every((n, i) => Math.abs(n - b[i]) < eps);

test("the route starts at the corridor pose and ends on the all-seats view, adding either end only when missing", () => {
  assert.equal(walkRoute(enter, corridor, seats).length, 4, "a file route that already has both ends is used as it is");
  const bare = walkRoute(enter.slice(1, 3), corridor, seats);
  assert.equal(bare.length, 4);
  assert.deepEqual(bare[0], corridor);
  assert.deepEqual(bare[3], seats);
  assert.deepEqual(walkRoute([], corridor, seats), [corridor, seats], "no route in the file: straight from one to the other");
});

test("sampling: e=0 is the corridor, e=1 the seats, and every waypoint is passed with its own look", () => {
  const w = walker(walkRoute(enter, corridor, seats));
  assert.ok(near(w(0).eye.toArray(), corridor.eye) && near(w(0).look.toArray(), corridor.look));
  assert.ok(near(w(1).eye.toArray(), seats.eye) && near(w(1).look.toArray(), seats.look));
  // somewhere along it the camera stands in the doorway looking at that waypoint's look point (eye and look in step)
  const door = enter[1];
  let best = Infinity, at = null;
  for (let i = 0; i <= 20000; i++) {
    const p = w(i / 20000);
    const d = p.eye.distanceTo({ x: door.eye[0], y: door.eye[1], z: door.eye[2] });
    if (d < best) [best, at] = [d, p];
  }
  assert.ok(best < 5e-3, `it passes through the doorway (${best})`);
  assert.ok(near(at.look.toArray(), door.look, 2e-2), "looking where the route says, not ahead or behind");
});

test("sampling: the walk moves on every step (no jump, no stall), and a leg that only turns still takes time", () => {
  const turnOnly = [corridor, { eye: corridor.eye, look: [-9, 1.62, 0] }, seats];
  for (const route of [walkRoute(enter, corridor, seats), turnOnly]) {
    const w = walker(route);
    let prev = w(0), most = 0;
    for (let i = 1; i <= 400; i++) {
      const p = w(i / 400);
      const step = p.eye.distanceTo(prev.eye) + p.look.distanceTo(prev.look);
      most = Math.max(most, step);
      prev = p;
    }
    assert.ok(most < 0.25, `the largest step between samples is small (${most.toFixed(3)} m)`);
  }
  const w = walker(turnOnly);
  const mid = w(0.15);
  assert.ok(near(mid.eye.toArray(), corridor.eye, 0.05) && !near(mid.look.toArray(), corridor.look, 0.05), "the turn on the spot is spread over time");
});

test("the ease starts and ends at rest and is symmetric", () => {
  assert.equal(walkEase(0), 0);
  assert.equal(walkEase(1), 1);
  assert.ok(Math.abs(walkEase(0.5) - 0.5) < 1e-9);
  assert.ok(walkEase(0.02) < 0.001 && 1 - walkEase(0.98) < 0.001, "slow out of the corridor, slow onto the seats");
});

test("lenses: the corridor matches the square 32 mm picture shown object-fit cover; the hall's is CR-003's", () => {
  assert.ok(Math.abs(corridorFov(1) - PICTURE_FOV) < 1e-9);
  assert.equal(corridorFov(0.6), PICTURE_FOV, "a tall box crops the picture's sides: its full height is seen");
  // a wide box crops top and bottom: the horizontal angle stays the picture's
  const a = 1.8, v = corridorFov(a);
  const h = (2 * Math.atan(Math.tan((v * Math.PI) / 360) * a) * 180) / Math.PI;
  assert.ok(Math.abs(h - PICTURE_FOV) < 1e-9);
  assert.equal(hallFov(1.2), 58.72);
  assert.ok(Math.abs(hallFov(16 / 9) - (2 * Math.atan(9 / 16) * 180) / Math.PI) < 1e-9);
  assert.ok(hallFov(0.46) <= 95);
});

test("the seen frame: the panel's cover is taken off the canvas, never below one pixel", () => {
  assert.deepEqual(seen(1440, 900, NO_COVER), { w: 1440, h: 900 });
  assert.deepEqual(seen(1440, 900, { right: 460, bottom: 0 }), { w: 980, h: 900 });
  assert.deepEqual(seen(390, 844, { right: 0, bottom: 321 }), { w: 390, h: 523 });
  assert.deepEqual(seen(100, 100, { right: 400, bottom: -5 }), { w: 1, h: 100 });
});
