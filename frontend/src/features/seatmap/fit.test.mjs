// CR-008 T16: the 2D map fits its box (fit.ts) - scaled cells, or the overview and a zoom into one block.
import assert from "node:assert/strict";
import { test } from "node:test";
import { cellFor, layout, partName, parts, GUTTER } from "./fit.ts";

// Hall 4's plan: three blocks over 26 columns (1-5, 8-17, 21-26 with aisles of 2+ empty columns)
const HALL = [...[1, 2, 3, 4, 5], ...Array.from({ length: 10 }, (_, i) => 8 + i), ...[21, 22, 23, 24, 25, 26]];

test("the cells shrink to the width and never overflow it", () => {
  for (const width of [300, 360, 420, 700]) {
    const { cell, gap } = cellFor(width, 26);
    assert.ok(GUTTER + 26 * (cell + gap) <= width, `${width}: fits`);
  }
  assert.deepEqual(cellFor(2000, 12), { cell: 32, gap: 4 }, "capped at 32 px");
});

test("blocks split at aisles (2+ empty columns), and a block too wide is cut in equal pieces", () => {
  assert.deepEqual(parts(HALL, 30), [{ from: 1, to: 5 }, { from: 8, to: 17 }, { from: 21, to: 26 }]);
  assert.deepEqual(parts([1, 3, 5, 7], 30), [{ from: 1, to: 7 }], "a recliner row's single gaps are not aisles");
  assert.deepEqual(parts(Array.from({ length: 13 }, (_, i) => i + 1), 7), [{ from: 1, to: 7 }, { from: 8, to: 13 }]);
});

test("desktop fits the whole hall; a phone shows the overview, then a block at a tappable size", () => {
  assert.equal(layout(0, HALL, 26, true, null).kind, "full", "not measured yet: the CSS defaults");
  assert.equal(layout(380, HALL, 26, false, null).kind, "full", "a mouse aims at small seats");
  const phone = layout(296, HALL, 26, true, null);
  assert.equal(phone.kind, "overview");
  const zoomed = layout(296, HALL, 26, true, 1);
  assert.equal(zoomed.kind, "zoomed");
  assert.ok(zoomed.cell >= 22, `a zoomed seat is tappable (${zoomed.cell}px)`);
  assert.equal(partName(1, 3), "Centre block");
});
