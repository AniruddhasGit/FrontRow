// CR-003: a hall with a baked room (/halls/hallN.json + .glb) puts each API seat on that file's position, matched by
// its label, and uses that file's cameras; any mismatch means the procedural hall is drawn instead. Run with the rest.
import assert from "node:assert/strict";
import { test } from "node:test";
import { bakedHall, screenFirst, screenNumber } from "./hall.ts";

const meta = {
  hall: 1, allseats: { eye: [0, 3, -1], look: [0, 1.4, -10.5] }, screen: { w: 6.9, h: 2.9, zc: 2.85, z: -0.29 },
  seats: [
    { id: "A1", row: "A", num: 1, cat: "S", level: "st", pos: [3, 0.36, -5.2], eye: [3, 1.81, -5.15] },
    { id: "A2", row: "A", num: 2, cat: "S", level: "st", pos: [2.4, 0.36, -5.2], eye: [2.4, 1.81, -5.15] },
    { id: "H1", row: "H", num: 1, cat: "R", level: "st", pos: [3, 2.88, -13], eye: [3, 4.23, -12.95] },
  ],
};
const api = (id, row, num) => ({ id, row, num, gr: 1, gc: num, cat: 1, price_paise: 1299, state: "available", is_active: true });

test("every API seat lands on its baked position, matched by row and number; cameras come from the file", () => {
  const h = bakedHall([api(10, "A", 1), api(11, "A", 2), api(12, "H", 1)], meta);
  assert.ok(h);
  assert.deepEqual(h.placed.map((p) => [p.seat.id, p.x, p.y, p.z]), [[10, 3, 0.36, -5.2], [11, 2.4, 0.36, -5.2], [12, 3, 2.88, -13]]);
  assert.deepEqual(h.views(12).seat, { at: [3, 4.23, -12.95], look: [0, 2.5, -0.29] });
  assert.deepEqual(h.views(null).all, { at: [0, 3, -1], look: [0, 1.4, -10.5] });
});

test("a seat the file does not know, or a file seat with no API seat, falls back to the procedural hall", () => {
  assert.equal(bakedHall([api(10, "A", 1), api(11, "A", 2), api(12, "J", 1)], meta), null); // J1 unknown
  assert.equal(bakedHall([api(10, "A", 1), api(11, "A", 2)], meta), null); // H1 missing: a different layout
  assert.equal(bakedHall([], meta), null);
});

test("the screen number comes from the screen's name, and nothing else", () => {
  assert.equal(screenNumber("SCREEN 4"), 4);
  assert.equal(screenNumber("Screen 12"), 12);
  assert.equal(screenNumber("IMAX"), null);
});

test("CR-004: the seat page arrives seated facing the screen, turns by the side wall, and lands on the all-seats view", () => {
  const r = screenFirst(meta);
  assert.deepEqual(r[0], { eye: [3, 4.23, -12.95], look: [0, 2.5, -0.29] }); // the default seat (a back row, nearest the centre), at the film
  assert.deepEqual(r.at(-1), meta.allseats);
  // the turn looks at the side wall, well clear of the eye, so the look point never crosses the camera
  assert.ok(Math.abs(r[1].look[0] - r[1].eye[0]) > 3 && r[1].look[2] === r[1].eye[2]);
});
