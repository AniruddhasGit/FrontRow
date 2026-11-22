// CR-008 T9-T13, T16: the discovery logic (discover.ts) and the rendered pieces that carry a rule.
// Run: node --test "frontend/src/features/discover/*.test.mjs"
import assert from "node:assert/strict";
import { test } from "node:test";
import { all, atUrl, load, name, render, role, text } from "../../test/render.mjs";

atUrl("/");
const d = await load("/src/features/discover/discover.ts");
const { RatingBadge, FilmTile } = await load("/src/features/discover/Bits.tsx");
const { Search } = await load("/src/features/discover/Search.tsx");
const { DayStrip } = await load("/src/features/browse/DayStrip.tsx");

const film = (id, over = {}) => ({
  id, title: `Film ${id}`, synopsis: "", runtime_minutes: 100, certification: { id: 1, name: "PG" }, language: { id: 1, name: "English" },
  genres: [{ id: 1, name: "Drama" }], poster_url: `/p/${id}`, display_until: "2026-12-01T00:00:00+05:30", release_date: "2026-11-01",
  coming_soon: false, rating: { average_tenths: null, count: 0 }, likes: 0, ...over,
});

test("T12: the star text is one decimal from integer tenths; unrated says New", () => {
  assert.equal(d.ratingText({ average_tenths: 74, count: 3 }), "7.4");
  assert.equal(d.ratingText({ average_tenths: 100, count: 1 }), "10.0");
  assert.equal(d.ratingText({ average_tenths: null, count: 0 }), null);
  assert.equal(d.ratingName({ average_tenths: 80, count: 1 }), "Rated 8.0 out of 10 by 1 person");
  const doc = render(RatingBadge, { rating: { average_tenths: null, count: 0 } });
  assert.equal(text(doc), "New");
});

test("T10: Top rated orders by average, then votes; unrated and coming-soon films are left out; Coming soon by date", () => {
  const films = [film(1, { rating: { average_tenths: 70, count: 9 } }), film(2, { rating: { average_tenths: 85, count: 1 } }),
    film(3, { rating: { average_tenths: 70, count: 12 } }), film(4), film(5, { coming_soon: true, release_date: "2026-12-20" }),
    film(6, { coming_soon: true, release_date: "2026-12-02" })];
  const r = d.rows(films);
  assert.deepEqual(r.top.map((f) => f.id), [2, 3, 1]);
  assert.deepEqual(r.now.map((f) => f.id), [1, 2, 3, 4]);
  assert.deepEqual(r.soon.map((f) => f.id), [6, 5]);
  assert.deepEqual(d.featured(films).map((f) => f.id), [2, 3, 1, 4]);
});

test("T13a: the carousel turns only while nothing holds it, wraps, and Pause stops it", () => {
  let s = { index: 0, count: 3, stopped: false, holds: [] };
  s = d.carousel(s, { type: "tick" });
  assert.equal(s.index, 1);
  s = d.carousel(s, { type: "hold", why: "hover" });
  assert.equal(d.carousel(s, { type: "tick" }).index, 1, "hovered: no turn");
  s = d.carousel(d.carousel(s, { type: "hold", why: "hidden" }), { type: "release", why: "hover" });
  assert.equal(d.turning(s), false, "still hidden");
  s = d.carousel(s, { type: "release", why: "hidden" });
  assert.equal(d.carousel(d.carousel(s, { type: "tick" }), { type: "tick" }).index, 0, "wraps after the last");
  assert.equal(d.carousel(s, { type: "prev" }).index, 0);
  s = d.carousel(s, { type: "stop" });
  assert.equal(d.carousel(s, { type: "tick" }).index, 1, "stopped: no turn");
  assert.equal(d.carousel(s, { type: "next" }).index, 2, "the buttons still work");
});

test("T9: a stale answer never replaces a newer query; short text asks nothing; arrows wrap", () => {
  assert.equal(d.wants(" a "), null);
  assert.equal(d.wants("  night   owl "), "night owl");
  const loading = { kind: "loading", q: "nig" };
  assert.deepEqual(d.answered(loading, "ni", { ok: true, items: [] }), loading, "the old query's answer is dropped");
  assert.deepEqual(d.answered(loading, "nig", { ok: true, items: [] }), { kind: "results", q: "nig", items: [] });
  assert.deepEqual(d.answered(loading, "nig", { ok: false }), { kind: "error", q: "nig" });
  assert.equal(d.moveActive(-1, 3, "ArrowDown"), 0);
  assert.equal(d.moveActive(2, 3, "ArrowDown"), 0);
  assert.equal(d.moveActive(0, 3, "ArrowUp"), 2);
  assert.equal(d.moveActive(-1, 0, "ArrowDown"), -1);
});

test("T9: the header search is a labelled combobox controlling a listbox, collapsed at first", () => {
  const doc = render(Search);
  const box = all(doc, (e) => role(e) === "combobox")[0];
  assert.equal(name(box, doc), "Search films by title or genre");
  assert.equal(box.attrs["aria-expanded"], "false");
  assert.equal(all(doc, (e) => role(e) === "listbox")[0].attrs.id, box.attrs["aria-controls"]);
});

test("T13d: recently viewed keeps the newest first, 12 at most, and survives a refusing store", () => {
  const store = new Map();
  const s = { getItem: (k) => store.get(k) ?? null, setItem: (k, v) => store.set(k, v) };
  for (let i = 1; i <= 14; i++) d.pushRecent(s, i);
  d.pushRecent(s, 5);
  assert.deepEqual(d.readRecent(s), [5, 14, 13, 12, 11, 10, 9, 8, 7, 6, 4, 3]);
  const refusing = { getItem: () => "not json", setItem: () => { throw new Error("quota"); } };
  assert.deepEqual(d.pushRecent(refusing, 7), [7]);
  assert.deepEqual(d.recentFilms([3, 9, 1], [film(1), film(3)], 1).map((f) => f.id), [3]);
});

test("T13c: share uses Web Share, else the clipboard, else shows the link; a closed share sheet is not an error", async () => {
  const data = { title: "t", text: "x", url: "https://frontrow.test/movies/1" };
  assert.deepEqual(await d.shareLink({ share: async () => {} }, data), { kind: "shared" });
  const abort = Object.assign(new Error("closed"), { name: "AbortError" });
  assert.deepEqual(await d.shareLink({ share: async () => { throw abort; } }, data), { kind: "idle" });
  let copied = "";
  assert.deepEqual(await d.shareLink({ clipboard: { writeText: async (t) => { copied = t; } } }, data), { kind: "copied" });
  assert.equal(copied, data.url);
  assert.deepEqual(await d.shareLink({}, data), { kind: "manual", url: data.url });
});

test("T13b: the calendar file carries the show's real instants in UTC and escapes its text", () => {
  const ics = d.bookingIcs({ reference: "FR-ACDE-FHJK", movie_title: "Paws, Claws; More", hall_name: "Hall 3",
    showtime_starts_at: "2026-11-22T21:30:00+05:30", showtime_ends_at: "2026-11-22T23:45:00+05:30",
    seats: [{ seat_label: "F7" }, { seat_label: "F8" }] }, "2026-11-22T10:00:00.000Z");
  assert.match(ics, /\r\nDTSTART:20261122T160000Z\r\n/);
  assert.match(ics, /\r\nDTEND:20261122T181500Z\r\n/);
  assert.match(ics, /SUMMARY:Paws\\, Claws\\; More at FrontRow/);
  assert.match(ics, /UID:FR-ACDE-FHJK@frontrow/);
  assert.ok(ics.startsWith("BEGIN:VCALENDAR\r\n") && ics.endsWith("END:VCALENDAR\r\n"));
});

test("T16: the date grid is rows of 7 with the month named where it changes; names stay 'Sat 15 Aug'", () => {
  const days = Array.from({ length: 10 }, (_, i) => `2026-11-${String(25 + i > 30 ? 25 + i - 30 : 25 + i).padStart(2, "0")}`)
    .map((s, i) => (i >= 6 ? s.replace("-11-", "-12-") : s));
  const grid = d.weekRows(days);
  assert.deepEqual(grid.map((w) => w.length), [7, 3]);
  assert.deepEqual(grid.flat().filter((x) => x.month).map((x) => [x.day, x.month]), [["2026-11-25", "Nov"], ["2026-12-01", "Dec"]]);
  const doc = render(DayStrip, { label: "Date", days: days.slice(0, 3), selected: null, anyDate: true, onSelect() {} });
  const buttons = all(doc, (e) => role(e) === "button");
  assert.deepEqual(buttons.map((b) => name(b, doc)), ["Any date", "Wed 25 Nov", "Thu 26 Nov", "Fri 27 Nov"]);
  assert.deepEqual(buttons.map((b) => b.attrs.tabindex), ["0", "-1", "-1", "-1"], "one tab stop");
});

test("T10/T11: a landing tile shows its genres under the title, and Coming soon its opening date instead of stars", () => {
  let doc = render(FilmTile, { film: film(1, { genres: [{ id: 1, name: "Sci-Fi" }, { id: 2, name: "Thriller" }] }) });
  assert.match(text(doc), /Film 1New.*Sci-Fi · Thriller/);
  doc = render(FilmTile, { film: film(2, { coming_soon: true, release_date: "2026-12-04" }) });
  assert.match(text(doc), /Opens 4 December 2026/);
  assert.ok(!/New/.test(text(doc)));
});
