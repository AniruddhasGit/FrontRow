// CR-011 F1-F5: the browse-to-door flow's pure logic (discover.ts) - sidebar order, listing filters, You might also like,
// showtimes by screen, the review form's bounds, the door's status - and the door rendered as a real, named button.
// Run: node --test "frontend/src/features/discover/*.test.mjs"
import assert from "node:assert/strict";
import { test } from "node:test";
import { all, atUrl, load, name, render, role, text } from "../../test/render.mjs";

atUrl("/");
const d = await load("/src/features/discover/discover.ts");
const { TheatreDoor } = await load("/src/features/discover/Door.tsx");

const film = (id, over = {}) => ({
  id, title: `Film ${id}`, synopsis: "", runtime_minutes: 100, certification: { id: 1, name: "PG" }, language: { id: 1, name: "English" },
  genres: [{ id: 1, name: "Drama" }], poster_url: `/p/${id}`, display_until: "2026-12-01T00:00:00+05:30", release_date: "2026-11-01",
  coming_soon: false, rating: { average_tenths: null, count: 0 }, likes: 0, ...over,
});
const r = (average_tenths, count) => ({ rating: { average_tenths, count } });

test("F1: the sidebar is at most 10 films that are out, by average, then votes, then title; unrated last", () => {
  const films = [film(1, { title: "Beta", ...r(70, 4) }), film(2, { title: "Alpha", ...r(70, 4) }), film(3, r(70, 9)),
    film(4, r(90, 1)), film(5, { title: "Unrated A" }), film(6, { coming_soon: true, ...r(99, 9) }),
    ...Array.from({ length: 10 }, (_, i) => film(10 + i, { title: `Z ${i}` }))];
  const top = d.sidebarTop(films);
  assert.equal(top.length, 10);
  assert.deepEqual(top.slice(0, 5).map((f) => f.id), [4, 3, 2, 1, 5]); // 9.0; 7.0x9; 7.0x4 Alpha, Beta; unrated by title
  assert.ok(!top.some((f) => f.coming_soon));
  assert.deepEqual(d.sidebarTop([]), []);
});

test("F2: title, genre and minimum rating narrow alone and combined; an unrated film never passes a minimum", () => {
  const g = (id, name) => ({ id, name });
  const films = [film(1, { title: "Night Train", genres: [g(1, "Drama")], ...r(82, 3) }),
    film(2, { title: "Night Owls", genres: [g(2, "Comedy")], ...r(65, 2) }),
    film(3, { title: "Day One", genres: [g(1, "Drama"), g(2, "Comedy")] })];
  const ids = (n) => d.narrowFilms(films, { q: null, genre_id: null, min_rating: null, ...n }).map((f) => f.id);
  assert.deepEqual(ids({}), [1, 2, 3]);
  assert.deepEqual(ids({ q: "  NIGHT " }), [1, 2]);
  assert.deepEqual(ids({ genre_id: "2" }), [2, 3]);
  assert.deepEqual(ids({ min_rating: "7" }), [1]);
  assert.deepEqual(ids({ min_rating: "6" }), [1, 2]);
  assert.deepEqual(ids({ q: "night", genre_id: "2" }), [2]);
  assert.deepEqual(ids({ q: "night", genre_id: "2", min_rating: "7" }), []);
  assert.deepEqual(d.genresOf(films), [g(2, "Comedy"), g(1, "Drama")]);
});

test("F3: You might also like shares a genre, most shared first, then rating, then title; never the film itself", () => {
  const g = (id) => ({ id, name: `G${id}` });
  const me = film(1, { genres: [g(1), g(2)] });
  const films = [me, film(2, { genres: [g(1)], ...r(90, 1) }), film(3, { genres: [g(1), g(2)] }), film(4, { genres: [g(3)] }),
    film(5, { genres: [g(2)], ...r(50, 1) })];
  assert.deepEqual(d.recommended(me, films).map((f) => f.id), [3, 2, 5]);
  assert.deepEqual(d.recommended(film(9, { genres: [] }), films), []);
});

test("F3: a date's showtimes group by screen in numeric name order, times in order", () => {
  const st = (id, at, sid, name) => ({ id, starts_at: at, screen: { id: sid, name } });
  const groups = d.byScreen([st(1, "2026-11-22T21:00:00+05:30", 10, "SCREEN 10"), st(2, "2026-11-22T18:00:00+05:30", 2, "SCREEN 2"),
    st(3, "2026-11-22T12:00:00+05:30", 10, "SCREEN 10")]);
  assert.deepEqual(groups.map((x) => [x.screen.name, x.shows.map((s) => s.id)]), [["SCREEN 2", [2]], ["SCREEN 10", [3, 1]]]);
});

test("F4/F5: review bounds, initials, the adults-only notice, and the door opens once", () => {
  assert.deepEqual(d.reviewText("  Loved it  "), { ok: true, text: "Loved it" });
  assert.equal(d.reviewText("   ").ok, false);
  assert.match(d.reviewText("x".repeat(2001)).message, /2000 characters \(you have 2001\)/);
  assert.equal(d.initials(" mira  hale jones"), "MH");
  assert.deepEqual(["A", "R", "18+", "nc-17"].map(d.adultsOnly), [true, true, true, true]);
  assert.deepEqual(["UA", "PG", "U/A 13+"].map(d.adultsOnly), [false, false, false]);
  const open = d.pressDoor({ kind: "closed" }, 7);
  assert.deepEqual(open, { kind: "opening", showtimeId: 7 });
  assert.equal(d.pressDoor(open, 8), open, "a second press while it swings changes nothing");
});

test("F5: the door is one real button named for the show, with ENTER above it and the screen and time", () => {
  const show = { id: 7, starts_at: "2026-11-22T19:30:00+05:30", screen: { id: 3, name: "SCREEN 3" }, sales_closed: false };
  const doc = render(TheatreDoor, { show, film: { title: "Silent Sky", certification: { id: 1, name: "A" } }, now: Date.parse("2026-11-22T12:00:00+05:30") });
  const buttons = all(doc, (e) => role(e) === "button");
  assert.equal(buttons.length, 1);
  assert.equal(name(buttons[0], doc), "Enter SCREEN 3 for Silent Sky at 7:30 pm");
  assert.match(text(doc), /ENTER/);
  assert.match(text(doc), /SCREEN 3/);
  assert.match(text(doc), /7:30 pm/);
  assert.match(text(doc), /adults only/i);
});

// The landing rail: scrolling chooses the film, top = first, bottom = last, no empty tail needed (owner, 2026-11-23)
import { railPick, railTop } from "./discover.ts";
test("the rail's scroll position picks the film, and the ends reach the first and the last", () => {
  assert.equal(railPick(0, 600, 10, 4), 0);
  assert.equal(railPick(600, 600, 10, 4), 9);
  assert.equal(railPick(300, 600, 10, 0), 5);
  assert.equal(railPick(900, 600, 10, 0), 9);
  assert.equal(railPick(0, 0, 10, 3), 3); // a list that fits keeps the choice
  for (let i = 0; i < 10; i++) assert.equal(railPick(railTop(i, 600, 10), 600, 10, -1), i);
});
