// S-ADM-12 / P-ADM-10: the dollar field converts to integer cents at the boundary, with no float.
// Run: node --test frontend/src/features/admin/money.test.mjs   (Node 24 strips the .ts types itself;
// no test dependency is added). Not bundled: nothing imports it, and tsc includes no .mjs.
import assert from "node:assert/strict";
import { test } from "node:test";
import { formatPaise, paiseToRupeesText, rupeesToPaise, showtimeBody } from "./money.ts";

test("250.00 typed in the dollar field submits base_price_paise 25000 as an integer", () => {
  const body = showtimeBody({ movie_id: "7", screen_id: "3", starts_at: "2026-09-04T18:30", ends_at: "2026-09-04T20:58", rupees: "250.00" });
  assert.deepEqual(body, { movie_id: 7, screen_id: 3, starts_at: "2026-09-04T18:30", ends_at: "2026-09-04T20:58", base_price_paise: 25000 });
  assert.ok(Number.isInteger(body.base_price_paise));
  assert.equal(JSON.stringify(body).includes('"base_price_paise":25000'), true);
});

test("conversion is exact, and a value it cannot send exactly is refused rather than rounded", () => {
  assert.equal(rupeesToPaise("250"), 25000);
  assert.equal(rupeesToPaise("250.5"), 25050);
  assert.equal(rupeesToPaise("0.29"), 29); // 0.29 * 100 is 28.999999999999996 in floating point
  assert.equal(rupeesToPaise("6917701970190.33"), 691770197019033);
  for (const bad of ["250.005", "-1", "1e3", "abc", "", "99999999999999999"]) assert.equal(rupeesToPaise(bad), null, bad);
});

test("rendering goes the other way by integer division", () => {
  assert.equal(paiseToRupeesText(25000), "250.00");
  assert.equal(paiseToRupeesText(29), "0.29");
  assert.equal(formatPaise(28125), "$281.25");
});
