// S-BRW-01..10, S-BRW-16, S-SCP-10: the browse screens' RENDERED markup (frontend/src/test/render.mjs).
// Run: node --test frontend/src/features/browse/
// Not asserted here (needs a real browser): computed styles (-webkit-line-clamp, fills), the img onError swap,
// focus movement by Tab, and anything an effect does after the first render (requests, polling).
import assert from "node:assert/strict";
import { test } from "node:test";
import { all, atUrl, byClass, load, name, render, role, tabbable, text } from "../../test/render.mjs";
import { query } from "./api.ts";
import { DATE_CLEARED, DAY_LABEL, settleListing } from "./logic.ts";

atUrl("/");
const { ListingScreen } = await load("/src/features/browse/ListingScreen.tsx");
const { MovieScreen } = await load("/src/features/browse/MovieScreen.tsx");

const NOW = Date.parse("2026-08-14T10:00:00+05:30");
const now = () => NOW;
const film = (id, display_until, over = {}) => ({
  id, title: `Film ${id}`, synopsis: "A synopsis.", runtime_minutes: 120, certification: { id: 1, name: "UA" },
  language: { id: 1, name: "Hindi" }, genres: [{ id: 1, name: "Drama" }], poster_url: `/api/movies/${id}/poster`, display_until, ...over,
});
const lookups = (n, word) => Array.from({ length: n }, (_, i) => ({ id: i + 1, name: `${word} ${i + 1}` }));
const ref = (languages, formats, cinemas) => ({ languages: lookups(languages, "L"), formats: lookups(formats, "F"), cinemas: lookups(cinemas, "C"), certifications: lookups(2, "U") });
const NO_FILTERS = { date: null, language_id: null, format_id: null, cinema_id: null };
const BOTH = [film(1, "2026-08-19T00:00:00+05:30"), film(2, "2026-08-21T00:00:00+05:30")];

const listing = (seed) => render(ListingScreen, { now, seed: { filters: NO_FILTERS, ...seed } });
const named = (doc, wanted) => all(doc, (e) => name(e, doc) === wanted && (e.attrs["aria-label"] !== undefined || role(e) !== null));
const buttons = (doc) => all(doc, (e) => role(e) === "button");
const dayButtons = (doc) => buttons(doc).filter((b) => DAY_LABEL.test(name(b, doc)));

test("S-BRW-03: the listing renders no select, listbox, combobox or Sort control", () => {
  const doc = listing({ movies: BOTH, reference: ref(3, 2, 2) });
  assert.ok(named(doc, "Language").length === 1 && named(doc, "Cinema").length === 1, "every filter control is rendered");
  assert.equal(all(doc, (e) => e.tag === "select").length, 0);
  assert.equal(all(doc, (e) => ["listbox", "combobox"].includes(role(e))).length, 0);
  assert.equal(all(doc, (e) => role(e) !== null && /Sort/.test(name(e, doc))).length, 0);
});

test("S-BRW-04: date + format leaving nothing renders the filtered empty state and 'Clear filters'", () => {
  const doc = listing({ filters: { ...NO_FILTERS, date: "2026-08-17", format_id: "2" }, movies: [], reference: ref(3, 2, 1) });
  assert.match(text(doc), /Nothing is showing for the chosen filters\./);
  assert.deepEqual(buttons(doc).filter((b) => name(b, doc) === "Clear filters").length, 1);
});

test("S-BRW-05: a control renders only at two or more values; an outage says so exactly once", () => {
  let doc = listing({ movies: BOTH, reference: ref(3, 2, 1) });
  assert.equal(named(doc, "Language").length, 1);
  assert.equal(named(doc, "Format").length, 1);
  assert.equal(named(doc, "Cinema").length, 0);

  doc = listing({ movies: BOTH, reference: ref(1, 2, 1) });
  assert.equal(named(doc, "Language").length, 0);
  assert.ok(!text(doc).includes("Language"));

  // /api/reference 503 while /api/movies 200, with a filter already in the URL: every card, no lookup control,
  // the date strip and 'Clear filters' still there, the outage line once. The URL's filter is still in the state
  // the listing request is built from.
  atUrl("/?language_id=2");
  doc = render(ListingScreen, { now, seed: { movies: BOTH, reference: null } });
  atUrl("/");
  assert.equal(all(doc, byClass("fr-card")).length, 2);
  for (const n of ["Language", "Format", "Cinema"]) assert.equal(named(doc, n).length, 0, n);
  assert.equal(named(doc, "Date").length, 1);
  assert.equal(buttons(doc).filter((b) => name(b, doc) === "Clear filters").length, 1);
  assert.equal(text(doc).split("Filters are unavailable right now.").length - 1, 1);

  doc = listing({ movies: [], reference: ref(0, 0, 1) }); // day one
  for (const n of ["Language", "Format", "Cinema"]) assert.equal(named(doc, n).length, 0, n);
  assert.ok(!text(doc).includes("Filters are unavailable right now."));
});

test("S-BRW-06: 'Any date' plus 7 days, 14 to 20 August; a filter that keeps only the 19th's film leaves 5", () => {
  let doc = listing({ movies: BOTH });
  const strip = named(doc, "Date")[0];
  const names = buttons(strip).map((b) => name(b, doc));
  assert.deepEqual(names, ["Any date", "Fri 14 Aug", "Sat 15 Aug", "Sun 16 Aug", "Mon 17 Aug", "Tue 18 Aug", "Wed 19 Aug", "Thu 20 Aug"]);
  assert.equal(buttons(strip)[0].attrs["aria-pressed"], "true");
  assert.ok(names.slice(1).every((n) => DAY_LABEL.test(n)));
  assert.ok(!buttons(doc).some((b) => /^(Today|Tomorrow)$/.test(name(b, doc))));

  doc = listing({ filters: { ...NO_FILTERS, language_id: "2" }, movies: [BOTH[0]] });
  assert.deepEqual(dayButtons(doc).map((b) => name(b, doc)), ["Fri 14 Aug", "Sat 15 Aug", "Sun 16 Aug", "Mon 17 Aug", "Tue 18 Aug"]);
});

test("S-BRW-06: the selected 20th outside the new strip returns to Any date, announced politely, no date sent next", () => {
  const before = { ...NO_FILTERS, date: "2026-08-20", language_id: "2" };
  const settled = settleListing(before, [BOTH[0].display_until], NOW);
  assert.equal(settled.announce, DATE_CLEARED);
  assert.ok(!new URLSearchParams(query(settled.filters)).has("date"), "the next request carries no date parameter");

  const doc = listing({ filters: before, movies: [BOTH[0]] }); // the same settle runs on a seeded response
  const anyDate = buttons(doc).find((b) => name(b, doc) === "Any date");
  assert.equal(anyDate.attrs["aria-pressed"], "true");
  const polite = all(doc, (e) => e.attrs["aria-live"] === "polite");
  assert.deepEqual(polite.map(text), [DATE_CLEARED]);
  assert.equal(DATE_CLEARED, "The date filter was cleared. Nothing in this list is showing on that day.");
});

test("S-BRW-06: both empty states have no day strip; each renders its own sentence", () => {
  for (const [filters, sentence, clear] of [
    [NO_FILTERS, "Nothing is showing right now.", 0],
    [{ ...NO_FILTERS, date: "2026-08-16" }, "Nothing is showing for the chosen filters.", 1], // a day with nothing on it
  ]) {
    const doc = listing({ filters, movies: [] });
    assert.equal(buttons(doc).filter((b) => name(b, doc) === "Any date").length, 0);
    assert.equal(dayButtons(doc).length, 0);
    assert.ok(text(doc).includes(sentence), sentence);
    assert.equal(buttons(doc).filter((b) => name(b, doc) === "Clear filters").length, clear);
  }
});

test("S-BRW-02: a film with no genre shows no genre name and never 'unknown'", () => {
  const doc = listing({ movies: [film(1, "2026-08-19T00:00:00+05:30", { genres: [] })] });
  const meta = all(doc, byClass("fr-meta"))[0];
  assert.ok(!/drama|unknown/i.test(text(meta)));
  assert.ok(!/No poster|Image unavailable|not found/.test(text(doc)));
});

// ---- SCR-BRW-02, the movie screen ----
const movie = (seed) => render(MovieScreen, { movieId: "7", now, seed });
const st = (id, starts_at, sales_closed) => ({
  id, starts_at, ends_at: starts_at, sales_close_at: starts_at, sales_closed, screen: { id: 4, name: "Hall 4" },
  cinema: { id: 1, name: "FrontRow" }, format: null, base_price_paise: 24999,
});
const F7 = film(7, "2026-08-21T00:00:00+05:30");

test("S-BRW-01, S-BRW-08: a film that is not showing renders its sentence and the way back", () => {
  const doc = movie({ film: "missing" });
  assert.match(text(doc), /That movie is not showing\./);
  const back = all(doc, (e) => role(e) === "link");
  assert.deepEqual(back.map((a) => [name(a, doc), a.attrs.href]), [["Back to what is showing", "/"]]);
});

test("S-BRW-08: a date with no showtimes renders 'No showtimes on this date.'", () => {
  const doc = movie({ film: F7, date: "2026-08-14", listed: { date: "2026-08-14", next_date_with_showtimes: "2026-08-15", showtimes: [] } });
  assert.match(text(doc), /No showtimes on this date\./);
});

test("S-BRW-09: a closed day keeps its showtime and offers 'Next: Sun 16 Aug'; no next date offers no button", () => {
  let doc = movie({ film: F7, date: "2026-08-15", listed: { date: "2026-08-15", next_date_with_showtimes: "2026-08-16", showtimes: [st(1, "2026-08-15T19:30:00+05:30", true)] } });
  assert.equal(all(doc, byClass("fr-time")).length, 1);
  assert.deepEqual(buttons(doc).map((b) => name(b, doc)).filter((n) => n.startsWith("Next: ")), ["Next: Sun 16 Aug"]);

  doc = movie({ film: F7, date: "2026-08-18", listed: { date: "2026-08-18", next_date_with_showtimes: null, showtimes: [] } });
  assert.match(text(doc), /No showtimes for this movie\./);
  assert.equal(buttons(doc).filter((b) => name(b, doc).startsWith("Next: ")).length, 0);
});

test("S-BRW-10: a closed showtime reads Closed, is out of the tab order, aria-disabled, goes nowhere, name ends 'sales closed'", () => {
  const doc = movie({ film: F7, date: "2026-08-14", listed: { date: "2026-08-14", next_date_with_showtimes: null,
    showtimes: [st(1, "2026-08-14T11:00:00+05:30", false), st(2, "2026-08-14T19:30:00+05:30", true)] } });
  const [open, closed] = all(doc, byClass("fr-time"));
  assert.equal(open.attrs.href, "/showtimes/1");
  assert.ok(text(closed).includes("Closed"));
  assert.equal(closed.attrs.tabindex, "-1");
  assert.equal(closed.attrs["aria-disabled"], "true");
  assert.equal(closed.attrs.href, undefined, "no address to go to");
  assert.match(name(closed, doc), /sales closed$/);
  const order = tabbable(doc);
  assert.ok(order.includes(open) && !order.includes(closed), "Tab from the showtime before it does not reach it");
});

test("S-BRW-16: a normal listing and movie page say nothing about an outage", () => {
  for (const doc of [listing({ movies: BOTH, reference: ref(3, 2, 1) }), movie({ film: F7, date: null, listed: { date: "2026-08-14", next_date_with_showtimes: null, showtimes: [st(1, "2026-08-14T11:00:00+05:30", false)] } })]) {
    assert.ok(!/unavailable|not updating/.test(text(doc)));
  }
});
