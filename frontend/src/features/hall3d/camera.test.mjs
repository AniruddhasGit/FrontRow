// FR-ADR-074: the 3D hall's cameras and hover label - the screen-side view that frames every seat of any hall, the
// view from a clicked seat, and the label's text for each seat state. Run: node --test "src/**/*.test.mjs"
// Not asserted here (needs WebGL): the glide, the label following the pointer.
import assert from "node:assert/strict";
import { test } from "node:test";
import { formatPaise } from "../admin/money.ts";
import { EYE, allSeats, computeHall, seatTip, stateWord, views } from "./hall.ts";

let next = 1;
const seat = (gr, gc, over = {}) => ({ id: next++, row: String.fromCharCode(64 + gr), num: gc, gr, gc, cat: 1, price_paise: 1461, state: "available", is_active: true, ...over });
const grid = (rows, cols) => Array.from({ length: rows }, (_, r) => Array.from({ length: cols }, (_, c) => seat(r + 1, c + 1))).flat();

// Project a world point through a View's camera (fov 50) and say whether it lands inside the frame.
function inFrame(view, aspect, [px, py, pz]) {
  const f = view.look.map((n, i) => n - view.at[i]);
  const len = Math.hypot(...f);
  const fw = f.map((n) => n / len);
  const right = [-fw[2], 0, fw[0]].map((n) => n / Math.hypot(fw[0], fw[2])); // forward x world-up
  const up = [right[1] * fw[2] - right[2] * fw[1], right[2] * fw[0] - right[0] * fw[2], right[0] * fw[1] - right[1] * fw[0]];
  const d = [px - view.at[0], py - view.at[1], pz - view.at[2]];
  const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
  const t = Math.tan((50 * Math.PI) / 360);
  return dot(d, fw) > 0 && Math.abs(dot(d, right)) <= t * aspect * dot(d, fw) && Math.abs(dot(d, up)) <= t * dot(d, fw);
}

test("the all-seats camera frames every seat of a narrow and a wide hall, from the screen side", () => {
  const studio = computeHall(grid(6, 8));
  const grand = computeHall(grid(11, 24));
  for (const aspect of [1.5, 2.4]) {
    const near = allSeats(studio, aspect);
    const wide = allSeats(grand, aspect);
    for (const [hall, v] of [[studio, near], [grand, wide]]) {
      // Every seat's floor point and the top of its back are in frame; the camera is between the screen and row one.
      for (const p of hall.placed) for (const y of [p.y, p.y + 1.2]) assert.ok(inFrame(v, aspect, [p.x, y, p.z]), `seat ${p.seat.row}${p.seat.num}`);
      assert.ok(v.at[2] < 0 && v.at[2] >= hall.screen.z + 0.6 && v.at[1] > 2, JSON.stringify(v.at));
      assert.deepEqual(views(hall, null, aspect).all, v);
    }
    const dist = (v) => Math.hypot(...v.at.map((n, i) => n - v.look[i]));
    assert.ok(dist(wide) > dist(near) + 3, `${dist(wide)} vs ${dist(near)}`); // the wide hall needs the camera farther out
  }
});

test("the seat camera sits at the clicked seat's eyes and looks at the screen's centre", () => {
  const hall = computeHall(grid(6, 8));
  const p = hall.placed.find((q) => q.seat.row === "D" && q.seat.num === 2);
  const v = views(hall, p.seat.id, 2).seat;
  assert.deepEqual(v.at, [p.x, p.y + EYE, p.z]);
  assert.deepEqual(v.look, [0, hall.screen.y, hall.screen.z]);
});

test("the hover label: row, seat, category and price, or the state when it cannot be chosen", () => {
  const s = seat(6, 7, { row: "F", num: 7 });
  const tip = (over, visual) => seatTip({ ...s, ...over }, "Premium", visual, formatPaise(s.price_paise));
  assert.equal(tip({}, "available"), "Row F · Seat 7 · Premium · $14.61");
  assert.equal(tip({ state: "sold" }, "sold"), "Row F · Seat 7 · Premium · Taken");
  assert.equal(tip({ state: "held" }, "held_by_other"), "Row F · Seat 7 · Premium · Being held");
  assert.equal(tip({}, "held_by_me"), "Row F · Seat 7 · Premium · Yours");
  assert.equal(tip({ is_active: false }, "available"), "Row F · Seat 7 · Premium · Not available");
  assert.equal(stateWord(s, "available"), null);
});
