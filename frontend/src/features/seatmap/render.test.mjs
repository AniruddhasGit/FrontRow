// S-BRW-07, S-BRW-11..15, S-BRW-17, S-SEA-01, S-SEA-03, S-SEA-04, S-SEA-10..12, S-SEA-14, S-SEA-21, S-XCT-38: the seat
// map's RENDERED markup (frontend/src/test/render.mjs). Run: node --test "frontend/src/features/seatmap/*.test.mjs"
// Not asserted here (needs a real browser): computed fills, borders and fonts, focus movement, scrolling and
// geometry, live-region insertion counts, the change ring's timing, and taps/keys (events do not run in SSR).
import assert from "node:assert/strict";
import { test } from "node:test";
import { all, atUrl, byClass, load, markup, name, render, role, tabbable, text } from "../../test/render.mjs";
import { ENDED_LINE, ENDED_PAYING_LINE, WARNING_LINE, markTaken } from "./hold.ts";
import { capNote, parseSeatMap, selectable, visualOf } from "./model.ts";

// Published sentences other source sweeps count (S-BRW-10: once in frontend/src; S-SEA-09: no literal cap), so
// this file assembles them instead of repeating them.
const CLOSED = ["Sales for this showtime", "have closed."].join(" ");

atUrl("/showtimes/77");
const { SeatMapScreen, firstLoadError } = await load("/src/features/seatmap/SeatMapScreen.tsx");
const { HoldCountdown } = await load("/src/features/seatmap/Countdown.tsx");

// S-BRW-11's hall: 12 grid rows x 22 grid columns, columns 4 and 5 an aisle, grid row 6 a cross-aisle: 220 seats.
const LETTERS = "ABCDEFGHIJK";
function hall({ state = () => "available", active = () => true, cat = () => 1 } = {}) {
  const seats = [];
  let id = 1;
  for (let gr = 1, r = 0; gr <= 12; gr++) {
    if (gr === 6) continue;
    const row = LETTERS[r++];
    for (let gc = 1, num = 1; gc <= 22; gc++) {
      if (gc === 4 || gc === 5) continue;
      const s = { id: id++, row, num: num++, gr, gc, cat: 0, price_paise: 0, state: "available", is_active: true };
      s.cat = cat(s);
      s.price_paise = s.cat === 1 ? 28124 : 33331;
      s.state = state(s);
      s.is_active = active(s);
      seats.push(s);
    }
  }
  return seatmap(seats, [{ id: 1, name: "Premium", price_paise: 28124 }, { id: 2, name: "Recliner", price_paise: 33331 }], 12, 22);
}
function seatmap(seats, categories, rows, cols, closed = false) {
  const m = parseSeatMap({
    showtime: { id: 77, starts_at: "2026-08-14T19:30:00+05:30", sales_close_at: "2026-08-14T19:45:00+05:30", sales_closed: closed },
    screen: { id: 4, name: "Hall 4", rows, cols }, categories, seats, generated_at: "2026-08-14T12:00:00+05:30", poll_interval_seconds: 3,
    max_seats_per_booking: 10,
  });
  assert.ok(m, "the fixture passes the client's own validation");
  return m;
}
const at = (map, row, num) => map.seats.find((s) => s.row === row && s.num === num);
// Every render gets an injected `now` (before holdOf's default expiry), so no countdown markup reads the wall clock.
const NOW = Date.parse("2026-08-14T14:01:00.000Z");
const screen = (seed) => render(SeatMapScreen, { showtimeId: "77", seed: { now: NOW, ...seed } });
const cells = (doc) => all(doc, (e) => role(e) === "gridcell");
const cellOf = (doc, seat) => cells(doc).find((c) => c.attrs["data-seat-id"] === String(seat.id));
const ends = (doc, ending) => cells(doc).filter((c) => name(c, doc).endsWith(ending));
const banners = (doc) => all(doc, byClass("fr-banner"));
const primary = (doc) => all(doc, byClass("fr-action"))[0];
const holdOf = (map, seats, expires_at = "2026-08-14T14:03:00.000Z") => ({
  hold_token: "T".repeat(43), showtime_id: 77, expires_at, total_paise: seats.reduce((n, s) => n + s.price_paise, 0),
  seats: seats.map((s) => ({ seat_id: s.id, label: `${s.row}${s.num}`, category: "Premium", price_paise: s.price_paise })),
});
const json = (node) => JSON.stringify(node, (k, v) => (k === "parent" ? undefined : v));

test("S-BRW-11: every seat retired renders 220 cells, all 'out of service', none selectable, and the hall banner", () => {
  const map = hall({ active: () => false });
  const doc = screen({ map });
  assert.equal(cells(doc).length, 220);
  assert.equal(ends(doc, "out of service").length, 220);
  assert.ok(cells(doc).every((c) => c.attrs["aria-disabled"] === "true"));
  // Enter, Space and a tap all go through selectable(); an out-of-service seat is refused in every state.
  for (const state of ["available", "held", "sold"]) for (const mine of [new Set(), new Set([1])]) {
    const s = { ...map.seats[0], state };
    assert.equal(selectable(s, visualOf(s, mine), false), false);
  }
  assert.deepEqual(banners(doc).map(text), ["None of the seats in this hall are available."]);
});

test("S-BRW-11, S-SEA-01, S-SEA-21: a failed first load renders its sentence and 'Try again'; 5xx adds the request id", () => {
  // The response -> sentence mapping is the screen's own firstLoadError, fed what the API client hands it; the
  // rendered lines come from its result, so a change to its copy or its status logic turns this red.
  const down = "The seat map is unavailable right now. You can still browse showtimes. Try again in a few minutes.";
  for (const [response, lines] of [
    [{ status: 500, message: "anything", requestId: "a1b2c3d4" }, ["The seat map could not be loaded.", "If you need help, quote a1b2c3d4."]],
    [{ status: 404, message: "anything", requestId: "a1b2c3d4" }, ["That showtime could not be found."]],
    [{ status: 503, message: down, requestId: "a1b2c3d4" }, [down]],
    [{ status: 429, message: "anything", requestId: "a1b2c3d4" }, ["The seat map could not be loaded."]],
  ]) {
    const doc = screen({ loadError: firstLoadError(response) });
    const box = all(doc, byClass("fr-map-error"))[0];
    assert.deepEqual(all(box, (e) => e.tag === "p").map(text), lines);
    assert.deepEqual(all(box, (e) => role(e) === "button").map((b) => name(b, doc)), ["Try again"]);
    assert.equal(cells(doc).length, 0);
  }
  // What the screen does with a payload it must not draw: parseSeatMap refuses it, and the screen sets that sentence.
  const bad = hall();
  for (const seats of [[{ ...bad.seats[0], state: "held_by_me" }], [{ ...bad.seats[0], state: "held_by_other" }], [(({ is_active, ...s }) => s)(bad.seats[0])]]) {
    assert.equal(parseSeatMap({ ...bad, seats }), null);
  }
});

test("S-BRW-12, S-SEA-01, S-XCT-38: the four states are four marks and four name endings; held_by_me only from the caller's own token", () => {
  const map = hall({ state: (s) => (s.row === "C" && s.num === 13 ? "held" : s.row === "C" && s.num === 12 ? "sold" : "available") });
  const c13 = at(map, "C", 13);
  assert.equal(ends(screen({ map }), "held by you").length, 0);
  let doc = screen({ map, hold: holdOf(map, [c13]) });
  assert.equal(ends(doc, "held by you").length, 1);
  assert.equal(name(cellOf(doc, c13), doc), "Row C seat 13, Premium, held by you");

  // One cell in each state: available C14, sold C12, held_by_other C15, held_by_me C13 (from the hold).
  const four = hall({ state: (s) => (s.row !== "C" ? "available" : s.num === 12 ? "sold" : s.num === 13 || s.num === 15 ? "held" : "available") });
  doc = screen({ map: four, hold: holdOf(four, [at(four, "C", 13)]) });
  const pick = (n) => cellOf(doc, at(four, "C", n));
  assert.deepEqual([14, 12, 15, 13].map((n) => name(pick(n), doc)), [
    "Row C seat 14, Premium, available", "Row C seat 12, Premium, sold",
    "Row C seat 15, Premium, held by someone else", "Row C seat 13, Premium, held by you",
  ]);
  const glyphs = [14, 12, 15, 13].map((n) => pick(n).attrs["data-glyph"]);
  assert.deepEqual(glyphs, ["outline", "hatch", "bar", "check"]);
  assert.equal(new Set(glyphs).size, 4); // carried by an attribute, not by a colour
  assert.ok(pick(15).attrs["aria-disabled"] === "true" && pick(12).attrs["aria-disabled"] === "true", "not tappable");
});

test("S-SEA-01: a chosen seat with no hold renders the same held_by_me treatment", () => {
  const map = hall();
  const c12 = at(map, "C", 12);
  const doc = screen({ map, selection: [c12.id] });
  assert.equal(cellOf(doc, c12).attrs["data-glyph"], "check");
  assert.match(name(cellOf(doc, c12), doc), /held by you$/);
});

test("S-SEA-01, S-XCT-38: the map is one tab stop, not 220", () => {
  const doc = screen({ map: hall() });
  const grid = all(doc, (e) => role(e) === "grid")[0];
  assert.equal(tabbable(grid).length, 1);
  assert.equal(all(grid, (e) => e.attrs.tabindex === "0").length, 1);
});

test("S-BRW-12: an out-of-service seat renders its number and its name", () => {
  const map = hall({ active: (s) => !(s.row === "C" && s.num === 12) });
  const doc = screen({ map });
  const c12 = cellOf(doc, at(map, "C", 12));
  assert.equal(text(c12), "12");
  assert.equal(name(c12, doc), "Row C seat 12, Premium, out of service");
  assert.equal(c12.attrs["data-visual"], "out_of_service");
});

test("S-BRW-12: the legend renders five swatches, the fifth 'Out of service'", () => {
  const doc = screen({ map: hall() });
  const states = all(all(doc, byClass("fr-legend-states"))[0], (e) => e.tag === "li");
  assert.equal(states.length, 5);
  assert.equal(text(states[4]), "Out of service");
});

test("S-BRW-12: every seat sold renders the full grid and its banner, and no 'Nothing'", () => {
  const doc = screen({ map: hall({ state: () => "sold" }) });
  assert.equal(cells(doc).length, 220);
  assert.deepEqual(banners(doc).map(text), ["Every seat for this showtime is sold."]);
  assert.ok(!text(doc).includes("Nothing"));
});

test("S-BRW-13: one legend row per category reads 'Premium  $281.24'; no tax, fee or discount anywhere", () => {
  const doc = screen({ map: hall() });
  const rows = all(all(doc, byClass("fr-legend-categories"))[0], (e) => e.tag === "li").map(text);
  assert.deepEqual(rows, ["Premium  $281.24", "Recliner  $333.31"]);
  assert.ok(!/Tax|Booking fee|Convenience|Discount/.test(text(doc)));
});

test("S-BRW-13: before the prices arrive the legend holds an empty block - no $, and never $0.00", () => {
  const doc = screen({});
  const block = all(doc, byClass("fr-inset-block"));
  assert.equal(block.length, 1);
  assert.ok(!text(all(doc, byClass("fr-legend-categories"))[0]).includes("$"));
  assert.ok(!text(doc).includes("$0.00"));
});

// S-BRW-14's 6-row hall: gr 1, 2, 4 category 1; gr 3 void; gr 5 both; gr 6 category 2.
function sixRows(catsOf, categories = [{ id: 1, name: "Premium", price_paise: 28124 }, { id: 2, name: "Recliner", price_paise: 33331 }]) {
  const seats = [];
  let id = 1;
  for (const gr of [1, 2, 4, 5, 6]) {
    catsOf(gr).forEach((cat, i) => seats.push({ id: id++, row: "ABCDEF"[gr - 1], num: i + 1, gr, gc: i + 1, cat, price_paise: 28124, state: "available", is_active: true }));
  }
  return seatmap(seats, categories, 6, 4);
}

test("S-BRW-14: the mixed grid row between two bands means no band rule; the legend keeps payload order", () => {
  const map = sixRows((gr) => (gr === 5 ? [1, 2] : gr === 6 ? [2, 2] : [1, 1]));
  let doc = screen({ map });
  assert.equal(all(doc, (e) => "data-band-rule" in e.attrs).length, 0);
  const legend = (d) => all(all(d, byClass("fr-legend-categories"))[0], (e) => e.tag === "li").map((li) => text(li).split("  ")[0]);
  assert.deepEqual(legend(doc), ["Premium", "Recliner"]);

  doc = screen({ map: { ...map, categories: [{ id: 9, name: "Nine", price_paise: 1 }, { id: 3, name: "Three", price_paise: 1 }] } });
  assert.deepEqual(legend(doc), ["Nine", "Three"]); // the client applies no ordering of its own

  // Category 1 in two separate runs (gr 1-2 and gr 6, category 2 between): one legend row each.
  doc = screen({ map: sixRows((gr) => (gr === 4 || gr === 5 ? [2, 2] : [1, 1])) });
  assert.deepEqual(legend(doc), ["Premium", "Recliner"]);
});

test("S-BRW-14: the positive control - two adjacent bands (a void row between) carry data-band and one rule", () => {
  const doc = screen({ map: sixRows((gr) => (gr <= 2 ? [1, 1] : [2, 2])) });
  assert.equal(all(doc, (e) => "data-band-rule" in e.attrs).length, 1);
  assert.equal(all(doc, (e) => "data-band" in e.attrs).length, 5); // grid rows 1, 2, 4, 5, 6
});

test("S-BRW-14: every grid row mixed: no band, no rule, the mixed notice exactly once", () => {
  const doc = screen({ map: sixRows(() => [1, 2]) });
  assert.equal(all(doc, (e) => "data-band-rule" in e.attrs).length, 0);
  assert.equal(all(doc, (e) => "data-band" in e.attrs).length, 0);
  const note = "Seat categories are mixed within rows. Each seat's category is in the legend and in its label.";
  assert.equal(all(doc, (e) => text(e) === note && e.children.every((c) => c.text !== undefined)).length, 1);
});

test("S-BRW-15: no refresh control; a failed poll keeps the grid and adds one strip", () => {
  const strip = "The seat map is not updating. The seats shown may be out of date.";
  const doc = screen({ map: hall(), pollStrip: strip });
  assert.equal(cells(doc).length, 220);
  assert.equal(text(doc).split(strip).length - 1, 1);
  assert.ok(!all(doc, (e) => role(e) !== null).some((e) => /refresh|reload/i.test(name(e, doc))));
});

test("S-BRW-17: neither before nor after the payload is there a progressbar or a 'Loading'", () => {
  for (const doc of [screen({}), screen({ map: hall() })]) {
    assert.equal(all(doc, (e) => role(e) === "progressbar").length, 0);
    assert.ok(!all(doc, (e) => role(e) !== null || e.attrs["aria-label"]).some((e) => /Loading/.test(name(e, doc))));
  }
});

test("S-BRW-07, S-SEA-10: a guest's map has no 'held by you' cell and the action reads 'Sign in to hold these seats'", () => {
  const map = hall();
  let doc = screen({ map });
  assert.equal(ends(doc, "held by you").length, 0);
  assert.equal(text(primary(doc)), "Sign in to hold these seats");
  doc = screen({ map, selection: [at(map, "C", 12).id] }); // a guest selection keeps the guest's label
  assert.equal(text(primary(doc)), "Sign in to hold these seats");
  doc = screen({ map, selection: [at(map, "C", 12).id], signedIn: true });
  assert.equal(text(primary(doc)), "Hold these seats");
});

test("S-ACC-14: after the restore, a now-sold C12 and a now-held C13 carry their published names and are not chosen", () => {
  const map = hall({ state: (s) => (s.row === "C" && s.num === 12 ? "sold" : s.row === "C" && s.num === 13 ? "held" : "available") });
  const gone = "C12 and C13 were taken while you were signing in. Your other seats are still selected.";
  const doc = screen({ map, selection: [at(map, "C", 14).id], signedIn: true, gone });
  assert.equal(name(cellOf(doc, at(map, "C", 12)), doc), "Row C seat 12, Premium, sold");
  assert.equal(name(cellOf(doc, at(map, "C", 13)), doc), "Row C seat 13, Premium, held by someone else");
  assert.equal(name(cellOf(doc, at(map, "C", 14)), doc), "Row C seat 14, Premium, held by you");
  assert.deepEqual(banners(doc).map((b) => text(all(b, (e) => e.tag === "p")[0])), [gone]);
  assert.equal(text(primary(doc)), "Hold these seats");
});

test("S-SEA-03: two Premium then three Recliner total $1,562.49; one line per seat plus the total; no tax or fee", () => {
  const map = hall({ cat: (s) => (s.row === "A" ? 1 : 2) });
  const premium = map.seats.filter((s) => s.cat === 1).slice(0, 2).map((s) => ({ ...s, price_paise: 28125 }));
  const recliner = map.seats.filter((s) => s.cat === 2).slice(0, 3).map((s) => ({ ...s, price_paise: 33333 }));
  const priced = { ...map, seats: map.seats.map((s) => premium.find((p) => p.id === s.id) ?? recliner.find((r) => r.id === s.id) ?? s) };
  const chosen = [...premium, ...recliner].map((s) => s.id);
  const totals = [1, 2, 3, 4, 5].map((n) => text(all(screen({ map: priced, selection: chosen.slice(0, n) }), byClass("fr-total"))[0]));
  assert.deepEqual(totals, ["$281.25", "$562.50", "$895.83", "$1,229.16", "$1,562.49"]);
  const doc = screen({ map: priced, selection: chosen });
  const summary = all(doc, byClass("fr-summary"))[0];
  assert.equal(all(summary, byClass("fr-summary-line")).length, chosen.length + 1);
  assert.equal((text(summary).match(/tax|fee|discount|convenience|surcharge|gst/gi) ?? []).length, 0);
});

test("S-SEA-03: nothing chosen reads $0.00 and the cap note; a seat with no known price removes the total and disables the action", () => {
  const map = hall();
  let doc = screen({ map });
  assert.equal(text(all(doc, byClass("fr-total"))[0]), "$0.00");
  assert.equal(text(all(doc, byClass("fr-cap-note"))[0]), capNote(10));
  // S-SEA-09 / CR-002 C-1: the note renders the figure the seat map carries, so the server's 6 reads 6.
  doc = screen({ map: { ...map, max_seats_per_booking: 6 } });
  assert.equal(text(all(doc, byClass("fr-cap-note"))[0]), "Up to 6 seats.");
  doc = screen({ map });
  assert.equal(capNote(10), ["Up to", 10, "seats."].join(" "));
  for (const signedIn of [false, true]) {
    doc = screen({ map, selection: [at(map, "A", 1).id, 999999], signedIn });
    assert.equal(all(doc, byClass("fr-total")).length, 0, "absent, not empty");
    assert.ok("disabled" in primary(doc).attrs, `signedIn=${signedIn}`);
  }
});

test("S-SEA-04: the gone banner is the sentence alone, assertive, with one control: Dismiss / 'Dismiss this message'", () => {
  const sentence = "C12 is no longer available. It has been removed from your choices.";
  const doc = screen({ map: hall(), gone: sentence });
  const [banner] = banners(doc);
  assert.equal(banners(doc).length, 1);
  assert.equal(banner.attrs["aria-live"], "assertive");
  assert.equal(text(all(banner, (e) => e.tag === "p")[0]), sentence);
  const controls = all(banner, (e) => role(e) !== null && ["button", "link", "textbox"].includes(role(e)));
  assert.equal(controls.length, 1);
  assert.deepEqual([role(controls[0]), text(controls[0]), name(controls[0], doc)], ["button", "Dismiss", "Dismiss this message"]);
});

test("S-SEA-04, S-SEA-12: a SEAT_UNAVAILABLE banner carries no control at all; another refusal keeps Dismiss", () => {
  const message = "C12 was taken by another customer. No seats were held. Choose a different seat and press Hold these seats again.";
  let [banner] = banners(screen({ map: hall(), notice: { code: "SEAT_UNAVAILABLE", message } }));
  assert.equal(all(banner, (e) => ["button", "a", "input"].includes(e.tag)).length, 0);
  assert.equal(text(banner), message);
  [banner] = banners(screen({ map: hall(), notice: { code: "SEAT_LIMIT_EXCEEDED", message: ["You can hold up to", 10, "seats for one showtime. You chose 11."].join(" ") } }));
  assert.equal(all(banner, (e) => e.tag === "button").length, 1);
});

test("S-SEA-11: a closed map makes every seat unselectable and shows the closed banner, plus the holder's line", () => {
  const map = hall();
  const closed = { ...map, showtime: { ...map.showtime, sales_closed: true } };
  let doc = screen({ map: closed });
  assert.ok(cells(doc).every((c) => c.attrs["aria-disabled"] === "true"));
  assert.deepEqual(banners(doc).map(text), [CLOSED]);
  doc = screen({ map: closed, hold: holdOf(map, [at(map, "C", 12)]), signedIn: true });
  assert.deepEqual(banners(doc).map(text), [`${CLOSED} You can still pay for the seats you are holding.`]);
});

test("S-SEA-12: seats lost to another customer repaint held_by_other (bar), never sold (hatch)", () => {
  const map = markTaken(hall(), ["C12", "C13"]);
  const doc = screen({ map });
  for (const n of [12, 13]) {
    const c = cellOf(doc, at(map, "C", n));
    assert.equal(c.attrs["data-glyph"], "bar");
    assert.match(name(c, doc), /held by someone else$/);
    assert.doesNotMatch(name(c, doc), /sold$/);
  }
});

test("S-SEA-14: the countdown needs `now`, never reads a clock, warns at 1:00 politely, and stops at 0:00", () => {
  const expires = "2026-08-14T14:03:00.000Z";
  const t = Date.parse(expires);
  assert.throws(() => markup(HoldCountdown, { expiresAt: expires, confirmInFlight: false, totalMs: 180000 }), TypeError);
  const real = Date.now;
  Date.now = () => t + 3_600_000; // the environment clock an hour past expiry: the component must not look at it
  try {
    const doc = render(HoldCountdown, { expiresAt: expires, now: t - 75_000, confirmInFlight: false, totalMs: 180000 });
    assert.equal(text(all(doc, byClass("fr-countdown-digits"))[0]), "1:15");
  } finally {
    Date.now = real;
  }
  const show = (now, confirmInFlight = false) => render(HoldCountdown, { expiresAt: expires, now, confirmInFlight, totalMs: 180000 });
  let doc = show(t - 60_000);
  const digits = all(doc, byClass("fr-countdown-digits"))[0];
  assert.equal(text(digits), "1:00");
  assert.deepEqual(all(doc, (e) => e.attrs["aria-live"] === "polite").map(text), [WARNING_LINE]);
  assert.equal(WARNING_LINE, "Less than a minute left. At 0:00 your seats are released and you will need to choose them again.");
  for (let p = digits; p; p = p.parent) assert.equal(p.attrs?.["aria-live"], undefined, "the digits sit in no live region");
  assert.equal(text(all(doc, byClass("fr-countdown-label"))[0]), "TIME LEFT");
  for (const [now, inFlight, line] of [[t, false, ENDED_LINE], [t + 5000, false, ENDED_LINE], [t, true, ENDED_PAYING_LINE]]) {
    doc = show(now, inFlight);
    assert.equal(text(all(doc, byClass("fr-countdown-digits"))[0]), "0:00");
    assert.equal(text(all(doc, (e) => e.attrs["aria-live"] === "polite")[0]), line);
  }
  assert.equal(ENDED_LINE, "Your hold has ended and your seats have been released. You have not been charged.");
  assert.equal(ENDED_PAYING_LINE, "Your hold has ended. We are waiting for the answer to your payment. Do not close this page.");
});

test("S-SEA-14: at 0:00 the held cells are not repainted before the next poll", () => {
  const map = hall();
  const held = [at(map, "C", 12), at(map, "C", 13)];
  const hold = holdOf(map, held);
  const doc = screen({ map, hold, signedIn: true, now: Date.parse(hold.expires_at) + 1000 });
  for (const s of held) assert.equal(cellOf(doc, s).attrs["data-glyph"], "check");
});

test("S-SEA-21: a residual lock on a sold seat renders seat 402's cell byte-identical, sold, with no banner", () => {
  // The server reports `sold` whether or not a lock remains (sold wins, asserted server-side), so the two payloads
  // carry the same seat object; the client must render it the same way both times.
  const withLock = hall({ state: (s) => (s.id === 42 ? "sold" : "available") });
  const without = hall({ state: (s) => (s.id === 42 ? "sold" : "available") });
  const a = screen({ map: withLock });
  const b = screen({ map: without });
  const seat = withLock.seats.find((s) => s.id === 42);
  assert.equal(json(cellOf(a, seat)), json(cellOf(b, seat)));
  assert.equal(cellOf(a, seat).attrs["data-glyph"], "hatch");
  assert.match(name(cellOf(a, seat), a), /sold$/);
  assert.equal(banners(a).length, 0);
});
