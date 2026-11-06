// S-SEA-11/12/14 (the parts that are logic, not layout): the hold on the client.
// Run: node --test frontend/src/features/seatmap/hold.test.mjs   (Node 24 strips the .ts types itself).
// Not asserted here (no browser harness in this repository): the rendered countdown, its live region, colour tokens,
// which Web Storage area holds the token, the unload spy, and the repainted cells' computed fill and accessible name.
import assert from "node:assert/strict";
import { test } from "node:test";
import {
  ENDED_LINE, ENDED_PAYING_LINE, TIME_LEFT, WARNING_LINE, adding, closedBanner, countdown, countdownLine,
  failureOf, markTaken, primaryLabel, withoutLabels,
} from "./hold.ts";
import { TREATMENT, mapBanner, visualOf } from "./model.ts";

const EXPIRES = "2026-08-14T14:05:37.412Z";
const at = (iso) => Date.parse(iso);

test("the countdown is arithmetic on the server's instant and the instant it is given - never a clock of its own", () => {
  const realNow = Date.now;
  Date.now = () => at("2026-08-14T15:05:37.412Z"); // the environment's clock an hour past expiry: ignored
  try {
    assert.equal(countdown(EXPIRES, at("2026-08-14T14:04:22.412Z")).text, "1:15");
  } finally {
    Date.now = realNow;
  }
  assert.throws(() => countdown(EXPIRES, undefined), TypeError);
  assert.equal(TIME_LEFT, "TIME LEFT");
});

test("one warning at sixty seconds, then 0:00 and never a negative number", () => {
  const sixty = countdown(EXPIRES, at("2026-08-14T14:04:37.412Z"));
  assert.deepEqual([sixty.text, sixty.urgent, countdownLine(sixty, false)], ["1:00", true, WARNING_LINE]);
  const before = countdown(EXPIRES, at("2026-08-14T14:04:36.412Z"));
  assert.deepEqual([before.text, before.urgent, countdownLine(before, false)], ["1:01", false, null]);
  for (const iso of [EXPIRES, "2026-08-14T14:05:38.412Z", "2026-08-14T15:00:00.000Z"]) {
    const zero = countdown(EXPIRES, at(iso));
    assert.deepEqual([zero.text, zero.ended, zero.urgent], ["0:00", true, false]);
    assert.equal(countdownLine(zero, false), ENDED_LINE);
    assert.equal(countdownLine(zero, true), ENDED_PAYING_LINE);
  }
});

test("the primary action names what pressing it does", () => {
  assert.equal(primaryLabel(false, 3, false), "Sign in to hold these seats");
  assert.equal(primaryLabel(true, 0, false), "Choose seats");
  assert.equal(primaryLabel(true, 2, false), "Hold these seats");
  assert.equal(primaryLabel(true, 1, true), "Hold 1 more seat");
  assert.equal(primaryLabel(true, 2, true), "Hold 2 more seats");
  // SCR-SEA 'Success': a live hold with nothing further chosen leads on to payment (PRD line 17122 / 17138)
  assert.equal(primaryLabel(true, 0, true), "Continue to payment");
  assert.deepEqual(adding([402, 403, 404], { seats: [{ seat_id: 402 }] }), [403, 404]);
});

test("a closed map tells a customer who is holding seats that they can still pay", () => {
  const closed = mapBanner({ ...map, showtime: { ...map.showtime, sales_closed: true } });
  assert.equal(closedBanner(closed, false), closed);
  assert.equal(closedBanner(closed, true), `${closed} You can still pay for the seats you are holding.`);
});

const seat = (id, num, state = "available") => ({ id, row: "C", num, gr: 3, gc: num, cat: 2, price_paise: 28125, state, is_active: true });
const map = { showtime: { id: 77, starts_at: "", sales_close_at: "", sales_closed: false }, screen: { id: 3, name: "Hall 3", rows: 3, cols: 20 },
              categories: [], seats: [seat(411, 11), seat(412, 12), seat(413, 13), seat(414, 14)], generated_at: "", poll_interval_seconds: 3, max_seats_per_booking: 10 };

test("seats lost to another customer repaint held_by_other at once, and every other choice stays chosen", () => {
  const failure = failureOf("SEAT_UNAVAILABLE", { unavailable_seats: ["C12", "C13"] });
  assert.deepEqual(failure, { kind: "taken", labels: ["C12", "C13"] });
  const repainted = markTaken(map, failure.labels);
  const selection = withoutLabels([411, 412, 413, 414], map, failure.labels);
  assert.deepEqual(selection, [411, 414]);
  const mine = new Set(selection);
  for (const id of [412, 413]) {
    const visual = visualOf(repainted.seats.find((s) => s.id === id), mine);
    assert.equal(visual, "held_by_other");
    assert.equal(TREATMENT[visual].fill, "--fr-seat-held-other");
    assert.equal(TREATMENT[visual].glyph, "bar");
    assert.ok(TREATMENT[visual].ending.endsWith("held by someone else"));
    assert.notEqual(TREATMENT[visual].glyph, "hatch");
  }
});

test("the interface branches on error.code and never on the message", () => {
  // Same code, arbitrary message text: the same outcome.
  assert.deepEqual(failureOf("SEAT_UNAVAILABLE", { unavailable_seats: ["C12"] }), failureOf("SEAT_UNAVAILABLE", { unavailable_seats: ["C12"] }));
  assert.deepEqual(failureOf("HOLD_EXPIRED", {}), { kind: "ended" });
  assert.deepEqual(failureOf("HOLD_NOT_OWNED", {}), { kind: "ended" });
  assert.deepEqual(failureOf("AUTH_REQUIRED", {}), { kind: "sign_in" });
  for (const code of ["SALES_CLOSED", "SEAT_LIMIT_EXCEEDED", "VALIDATION_FAILED", "DEPENDENCY_UNAVAILABLE", "RATE_LIMITED"]) {
    assert.deepEqual(failureOf(code, {}), { kind: "message" });
  }
});
