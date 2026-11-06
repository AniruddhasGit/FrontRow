// FR-ADR-074 / CR-001 Part B: the 3D hall's layout math (grid -> positions, aisles, walkways, wide seats) and the
// category -> seat-model mapping. Run: node --test "frontend/src/features/hall3d/*.test.mjs"
// Not asserted here (needs a real browser with WebGL): what the scene draws, the camera glide, picking.
import assert from "node:assert/strict";
import { test } from "node:test";
import { MODEL_URL, PITCH_X, PITCH_Z, RISE, computeHall, modelKind, views } from "./hall.ts";

let next = 1;
const seat = (gr, gc, over = {}) => ({ id: next++, row: String.fromCharCode(64 + gr), num: gc, gr, gc, cat: 1, price_paise: 100, state: "available", is_active: true, ...over });

test("grid to positions: aisles are empty columns, walkways empty rows, rows centre, a wide row spans two columns", () => {
  // Row 1: 2 | aisle | 2 (cols 0,1,3,4). Row 2: empty (a walkway). Row 3: three wide seats at 0,2,4 (cols 0..5).
  const seats = [seat(1, 0), seat(1, 1), seat(1, 3), seat(1, 4), seat(3, 0), seat(3, 2), seat(3, 4)];
  const hall = computeHall(seats);
  const at = (s) => hall.placed.find((p) => p.seat.id === s.id);
  // The block runs cols 0..6 (the last wide seat ends at 6), so its centre is col 3.
  assert.equal(hall.halfWidth, 3 * PITCH_X);
  assert.deepEqual(hall.walkways, [2]);
  assert.equal(hall.tiers.length, 3);
  // Col 2 is empty in row 1 but taken by row 3's middle recliner, so no column is empty in EVERY row: no aisle.
  assert.deepEqual(hall.aisles, []);
  assert.equal(at(seats[0]).span, 1);
  assert.equal(at(seats[4]).span, 2);
  assert.ok(Math.abs(at(seats[0]).x - (0.5 - 3) * PITCH_X) < 1e-9);
  assert.ok(Math.abs(at(seats[5]).x - 0) < 1e-9); // the middle recliner sits on the centre line
  assert.ok(Math.abs(at(seats[4]).z - 2 * PITCH_Z) < 1e-9 && Math.abs(at(seats[4]).y - 2 * RISE) < 1e-9); // raked
  assert.equal(at(seats[0]).y, 0);

  // A hall with a real centre aisle (cols 3 and 4 empty in every row) and rows of different length.
  const two = computeHall([seat(1, 1), seat(1, 2), seat(1, 5), seat(1, 6), seat(2, 0), seat(2, 1), seat(2, 2), seat(2, 5), seat(2, 6), seat(2, 7)]);
  assert.equal(two.aisles.length, 1);
  assert.ok(Math.abs(two.aisles[0]) < 1e-9); // one run of two empty columns, on the centre line
  assert.ok(two.placed.every((p) => p.span === 1));

  // The seat camera sits at the chosen seat's eye height and looks at the screen; with none it still has a view.
  const v = views(hall, seats[5].id, 2);
  assert.deepEqual(v.seat.at.map((n) => Math.round(n * 100)), [0, Math.round((2 * RISE + 1.15) * 100), Math.round(2 * PITCH_Z * 100)]);
  assert.equal(v.seat.look[2], hall.screen.z);
  assert.ok(views(hall, null, 2).seat.at.every(Number.isFinite));
  assert.deepEqual(computeHall([]).placed, []);
});

test("category name to seat model: Standard, Premium, Recliner by name, anything else a standard seat", () => {
  assert.equal(modelKind("Standard"), "standard");
  assert.equal(modelKind("Premium"), "premium");
  assert.equal(modelKind(" recliner "), "recliner");
  assert.equal(modelKind("Gold Class"), "standard");
  assert.equal(modelKind(""), "standard");
  assert.deepEqual(Object.values(MODEL_URL), ["/models/seat_standard.glb", "/models/seat_premium.glb", "/models/seat_recliner.glb"]);
});
