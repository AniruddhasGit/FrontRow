// S-BRW-05, S-BRW-06, S-BRW-08, S-BRW-09, S-BRW-10 (the logic, not the layout): date strips, labels, filter rules.
// Run: node --test frontend/src/features/browse/   (no test dependency; the clock is passed in, never read).
import assert from "node:assert/strict";
import { test } from "node:test";
import {
  DAY_LABEL, controlsFor, countLine, dayLabel, keepDay, listingStrip, movieStrip, runtimeName, showtimeName, timeLabel,
} from "./logic.ts";
import { formatPaise } from "../admin/money.ts";

const at = (iso) => Date.parse(iso);

test("the listing strip runs from today to the day before the latest display_until, over the array it was given", () => {
  const now = at("2026-08-14T10:00:00+05:30");
  const both = ["2026-08-19T00:00:00+05:30", "2026-08-21T00:00:00+05:30"];
  assert.deepEqual(listingStrip(now, both), ["2026-08-14", "2026-08-15", "2026-08-16", "2026-08-17", "2026-08-18", "2026-08-19", "2026-08-20"]);
  assert.deepEqual(listingStrip(now, ["2026-08-19T00:00:00+05:30"]), ["2026-08-14", "2026-08-15", "2026-08-16", "2026-08-17", "2026-08-18"]);
  assert.deepEqual(listingStrip(now, []), []);
});

test("today is the cinema's today, from the offset the server sent, not the device's", () => {
  // 19:05Z on the 14th is 00:35 on the 15th in +05:30
  assert.deepEqual(listingStrip(at("2026-08-14T19:05:00Z"), ["2026-08-17T00:00:00+05:30"]), ["2026-08-15", "2026-08-16"]);
});

test("a filter that removes the selected day drops it back to Any date", () => {
  const days = listingStrip(at("2026-08-14T10:00:00+05:30"), ["2026-08-19T00:00:00+05:30"]);
  assert.deepEqual(keepDay("2026-08-20", days), { day: null, cleared: true });
  assert.deepEqual(keepDay("2026-08-16", days), { day: "2026-08-16", cleared: false });
  assert.deepEqual(keepDay(null, days), { day: null, cleared: false });
});

test("day buttons carry their own date, weekday and short month - never Today or Tomorrow", () => {
  assert.equal(dayLabel("2026-08-15"), "Sat 15 Aug");
  assert.equal(dayLabel("2026-08-16"), "Sun 16 Aug");
  assert.equal(dayLabel("2026-08-14"), "Fri 14 Aug");
  for (const d of listingStrip(at("2026-08-14T10:00:00+05:30"), ["2026-08-21T00:00:00+05:30"])) assert.match(dayLabel(d), DAY_LABEL);
});

test("the single-movie strip runs today through the last day of the window", () => {
  assert.deepEqual(movieStrip(at("2026-08-19T23:00:00+05:30"), "2026-08-21T00:00:00+05:30"), ["2026-08-19", "2026-08-20"]);
});

test("times read in the instant's own offset, in the customer's form", () => {
  assert.equal(timeLabel("2026-08-15T19:30:00+05:30"), "7:30 pm");
  assert.equal(timeLabel("2026-08-15T00:05:00+05:30"), "12:05 am");
  assert.equal(timeLabel("2026-08-15T12:00:00+05:30"), "12:00 pm");
});

test("a showtime's accessible name: open with its price, closed ending 'sales closed'", () => {
  const st = { starts_at: "2026-08-14T19:30:00+05:30", screen: { name: "Hall 4" }, base_price_paise: 24999, sales_closed: false };
  assert.equal(showtimeName(st, formatPaise), "7:30 pm, Hall 4, from ₹249.99");
  assert.equal(showtimeName({ ...st, sales_closed: true }, formatPaise), "7:30 pm, Hall 4, sales closed");
});

test("a reference-backed control renders only at two or more values; an outage is the only state that says so", () => {
  const ref = { languages: [{ id: 1 }, { id: 2 }, { id: 3 }], formats: [{ id: 1 }, { id: 2 }], cinemas: [{ id: 1 }], certifications: [] };
  assert.deepEqual(controlsFor(ref), { language: true, format: true, cinema: false, unavailable: false });
  assert.deepEqual(controlsFor({ ...ref, languages: [{ id: 1 }] }).language, false);
  assert.deepEqual(controlsFor({ languages: [], formats: [], cinemas: [], certifications: [] }), { language: false, format: false, cinema: false, unavailable: false });
  assert.deepEqual(controlsFor(null), { language: false, format: false, cinema: false, unavailable: true });
});

test("the counts carry a singular", () => {
  assert.equal(countLine(1, "film", "showing"), "1 film showing.");
  assert.equal(countLine(0, "film", "showing"), "0 films showing.");
  assert.equal(countLine(12, "film", "showing"), "12 films showing.");
  assert.equal(countLine(1, "showtime", "on this date"), "1 showtime on this date.");
  assert.equal(runtimeName(1), "1 minute");
  assert.equal(runtimeName(128), "128 minutes");
});
