// S-SEA-01..04, S-BRW-11..14, S-XCT-38 (the parts that are logic, not layout): the seat map's client model.
// Run: node --test frontend/src/features/seatmap/   (Node 24 strips the .ts types itself; no test dependency).
// Not bundled: nothing imports it, and tsc includes no .mjs. What a browser must render - computed styles,
// focus movement, tab stops, geometry - is NOT asserted here; there is no browser harness in this repository.
import assert from "node:assert/strict";
import { test } from "node:test";
import {
  GLYPHS, LEGEND, MAX_SEATS_PER_BOOKING, TREATMENT, bands, capNote, changedSeats, goneBanner, mapBanner, parseSeatMap,
  recheck, seatLabel, seatName, selectable, toggle, total, visualOf,
} from "./model.ts";
import { formatPaise } from "../admin/money.ts";

const seat = (over = {}) => ({ id: 402, row: "C", num: 12, gr: 3, gc: 12, cat: 2, price_paise: 28125, state: "available", is_active: true, ...over });
const payload = (seats, over = {}) => ({
  showtime: { id: 77, starts_at: "2026-08-16T19:30:00+05:30", sales_close_at: "2026-08-16T19:45:00+05:30", sales_closed: false },
  screen: { id: 4, name: "Hall 4", rows: 12, cols: 22 },
  categories: [{ id: 2, name: "Premium", price_paise: 28125 }],
  seats, generated_at: "2026-08-15T12:00:00+05:30", poll_interval_seconds: 3, ...over,
});

test("three wire values against hold membership render exactly four (fill, glyph) pairs and four name endings", () => {
  const renders = [
    visualOf(seat({ state: "available" }), new Set()),
    visualOf(seat({ state: "sold" }), new Set()),
    visualOf(seat({ state: "held" }), new Set()),
    visualOf(seat({ state: "held" }), new Set([402])),
    visualOf(seat({ state: "available" }), new Set([402])), // chosen, not yet held: the held_by_me treatment
  ];
  assert.deepEqual(renders, ["available", "sold", "held_by_other", "held_by_me", "held_by_me"]);
  const pairs = new Set(renders.map((v) => `${TREATMENT[v].fill}|${TREATMENT[v].glyph}`));
  assert.equal(pairs.size, 4);
  assert.deepEqual([...pairs].sort(), ["--fr-seat-available|outline", "--fr-seat-held-other|bar", "--fr-seat-mine|check", "--fr-seat-sold|hatch"]);
  const endings = new Set(renders.map((v) => TREATMENT[v].ending));
  assert.deepEqual([...endings].sort(), ["available", "held by another customer", "held by you", "sold"]);
  assert.deepEqual(new Set(GLYPHS), new Set(["outline", "bar", "hatch", "check"]));
});

test("accessible names state identity, category and state; out of service in any state", () => {
  assert.equal(seatName(seat(), "Premium", "available"), "Row C seat 12, Premium, available");
  assert.equal(seatName(seat(), "Premium", "held_by_other"), "Row C seat 12, Premium, held by another customer");
  assert.equal(seatName(seat(), "Premium", "held_by_me"), "Row C seat 12, Premium, held by you");
  for (const state of ["available", "held", "sold"]) {
    const s = seat({ state, is_active: false });
    assert.equal(seatName(s, "Premium", visualOf(s, new Set([402]))), "Row C seat 12, Premium, out of service");
  }
});

test("only an available or own seat is selectable, never an inactive one, never after sales close", () => {
  assert.equal(selectable(seat(), "available", false), true);
  assert.equal(selectable(seat(), "held_by_me", false), true);
  assert.equal(selectable(seat({ state: "sold" }), "sold", false), false);
  assert.equal(selectable(seat({ state: "held" }), "held_by_other", false), false);
  for (const v of ["available", "sold", "held_by_other", "held_by_me"]) assert.equal(selectable(seat({ is_active: false }), v, false), false);
  assert.equal(selectable(seat(), "available", true), false);
});

test("a payload with a fourth state, a missing is_active, or a non-integer price is rejected, never defaulted", () => {
  assert.ok(parseSeatMap(payload([seat()])));
  for (const bad of ["held_by_me", "held_by_other", "blocked"]) assert.equal(parseSeatMap(payload([seat({ state: bad })])), null, bad);
  const noActive = seat();
  delete noActive.is_active;
  assert.equal(parseSeatMap(payload([noActive])), null);
  for (const price of [-1, 2.5, "28125", null]) assert.equal(parseSeatMap(payload([seat({ price_paise: price })])), null, String(price));
  assert.equal(parseSeatMap(payload([seat()], { poll_interval_seconds: "3" })), null);
  assert.equal(parseSeatMap({ error: {} }), null);
});

test("choosing toggles locally, refuses the eleventh seat, and the cap note interpolates the configured maximum", () => {
  assert.equal(MAX_SEATS_PER_BOOKING, 10);
  // The note interpolates the cap (S-SEA-09): asserted at 6, so no "up to ten" literal ships anywhere in frontend/src.
  assert.equal(capNote(6), "Up to 6 seats.");
  assert.equal(capNote(MAX_SEATS_PER_BOOKING), capNote(10));
  let chosen = [];
  chosen = toggle(chosen, seat(), "available").selection;
  assert.deepEqual(chosen, [402]);
  assert.deepEqual(toggle(chosen, seat(), "held_by_me").selection, []);
  assert.deepEqual(toggle([], seat({ state: "sold" }), "sold").selection, []);
  const ten = Array.from({ length: 10 }, (_, i) => i + 1);
  const eleventh = toggle(ten, seat({ id: 99 }), "available");
  assert.deepEqual(eleventh.selection, ten);
  assert.equal(eleventh.refused, true);
});

test("the total sums integers only: 2 Premium then 3 Recliner render the five published figures", () => {
  const prem = (id) => seat({ id, cat: 2, price_paise: 28125 });
  const recl = (id) => seat({ id, cat: 3, price_paise: 33333 });
  const seats = new Map([1, 2].map((id) => [id, prem(id)]).concat([3, 4, 5].map((id) => [id, recl(id)])));
  const renders = [];
  for (let n = 1; n <= 5; n++) renders.push(formatPaise(total([1, 2, 3, 4, 5].slice(0, n), seats)));
  assert.deepEqual(renders, ["$281.25", "$562.50", "$895.83", "$1,229.16", "$1,562.49"]);
  assert.equal(total([1, 2, 3, 4, 5], seats), 156249);
  assert.notEqual(total([1, 2, 3, 4, 5], seats), 156248);
  assert.equal(formatPaise(total([], seats)), "$0.00");
  assert.equal(total([1, 999], seats), null); // a seat with no known price: no total at all
  const three = new Map([7, 8, 9].map((id) => [id, seat({ id, price_paise: 33331 })]));
  assert.equal(total([7, 8, 9], three), 99993);
});

test("a re-check drops a chosen seat that has gone and names it in one sentence, one banner for two", () => {
  const map = parseSeatMap(payload([seat({ id: 1, row: "C", num: 12, state: "sold" }), seat({ id: 2, row: "C", num: 13, state: "held" }), seat({ id: 3, row: "C", num: 14 })]));
  const one = recheck([1, 3], map);
  assert.deepEqual(one.kept, [3]);
  assert.equal(goneBanner(one.gone), "C12 is no longer available. It has been removed from your choices.");
  const two = recheck([1, 2, 3], map);
  assert.deepEqual(two.kept, [3]);
  assert.equal(two.gone.length, 2);
  assert.equal(typeof goneBanner(two.gone), "string"); // one banner, however many seats went
  assert.equal(goneBanner([]), null);
  assert.equal(seatLabel(seat()), "C12");
});

test("the banner: sales closed, every seat retired, every seat sold - each its own published string", () => {
  const open = (seats) => parseSeatMap(payload(seats));
  assert.equal(mapBanner(open([seat(), seat({ id: 5 })])), null);
  assert.equal(mapBanner(open([seat({ state: "sold" }), seat({ id: 5, state: "sold" })])), "Every seat for this showtime is sold.");
  assert.equal(mapBanner(open([seat({ is_active: false }), seat({ id: 5, is_active: false, state: "sold" })])), "None of the seats in this hall are available.");
  const closed = parseSeatMap(payload([seat()], { showtime: { id: 77, starts_at: "x", sales_close_at: "y", sales_closed: true } }));
  // Built from two halves: the whole sentence may appear exactly once under frontend/src (S-BRW-10).
  assert.equal(mapBanner(closed), "Sales for this showtime " + "have closed.");
});

test("a seat whose state changed between two polls is reported once", () => {
  const before = parseSeatMap(payload([seat({ id: 1 }), seat({ id: 2 })]));
  const after = parseSeatMap(payload([seat({ id: 1, state: "held" }), seat({ id: 2 })]));
  assert.deepEqual([...changedSeats(before, after)], [1]);
  assert.deepEqual([...changedSeats(null, after)], []);
});

test("the legend names five swatches, the fifth 'Out of service'", () => {
  assert.deepEqual(LEGEND.map((l) => l.label), ["Available", "Sold", "Held by someone else", "Held by you", "Out of service"]);
});

test("bands: the criterion's 6-row hall gives exactly two, a void row inside one and a mixed row ending it", () => {
  const rows = { 1: [1], 2: [1], 4: [1], 5: [1, 2], 6: [2] };
  const seats = [];
  let id = 1;
  for (const [gr, cats] of Object.entries(rows)) for (const cat of cats) seats.push(seat({ id: id++, gr: Number(gr), gc: id, cat }));
  const map = { screen: { rows: 6, cols: 9 }, seats };
  assert.deepEqual(bands(map), [{ cat: 1, from: 1, to: 4 }, { cat: 2, from: 6, to: 6 }]);
  // retiring a seat of gr 2 changes nothing: a retired seat still belongs to its band
  const retired = { ...map, seats: seats.map((s) => (s.gr === 2 ? { ...s, is_active: false } : s)) };
  assert.deepEqual(bands(retired), [{ cat: 1, from: 1, to: 4 }, { cat: 2, from: 6, to: 6 }]);
  // a category in two separate runs yields two bands
  const split = { screen: { rows: 3 }, seats: [seat({ id: 1, gr: 1, cat: 1 }), seat({ id: 2, gr: 2, cat: 2 }), seat({ id: 3, gr: 3, cat: 1 })] };
  assert.deepEqual(bands(split).map((b) => b.cat), [1, 2, 1]);
  // every row mixed: no band at all
  const mixed = { screen: { rows: 2 }, seats: [seat({ id: 1, gr: 1, cat: 1 }), seat({ id: 2, gr: 1, cat: 2 }), seat({ id: 3, gr: 2, cat: 1 }), seat({ id: 4, gr: 2, cat: 2 })] };
  assert.deepEqual(bands(mixed), []);
});
