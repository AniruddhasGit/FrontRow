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

test("F4/F5: review bounds, initials, the adults-only notice, and the door opens once", () => {
  assert.deepEqual(d.reviewText("  Loved it  "), { ok: true, text: "Loved it" });
  assert.equal(d.reviewText("   ").ok, false);
  assert.match(d.reviewText("x".repeat(2001)).message, /2000 characters \(you have 2001\)/);
  assert.equal(d.initials(" mira  hale jones"), "MH");
  assert.deepEqual(["A", "R", "18+", "nc-17"].map(d.adultsOnly), [true, true, true, true]);
  assert.deepEqual(["UA", "PG", "U/A 13+"].map(d.adultsOnly), [false, false, false]);
});

// CR-014: the hero door's one status. Every state has an exit and a press happens once.
test("CR-014 door: live hall -> walk -> leave walked; a second press while walking changes nothing", () => {
  const s7 = { id: 7, starts_at: "", screen: { id: 1, name: "SCREEN 1" }, sales_closed: false };
  const press = (show = s7, reduced = false) => ({ type: "press", show, reduced });
  let st = d.door({ kind: "waiting" }, { type: "ready" });
  assert.deepEqual(st, { kind: "live" });
  st = d.door(st, press());
  assert.deepEqual(st, { kind: "walking", show: s7 });
  assert.equal(d.door(st, press({ ...s7, id: 8 })), st, "a second press while it walks changes nothing");
  assert.equal(d.door(st, { type: "reset" }), st, "another screen chosen mid-walk changes nothing");
  st = d.door(st, { type: "landed" });
  assert.deepEqual(st, { kind: "leaving", show: s7, how: "walked" });
  assert.equal(d.door(st, press()), st, "leaving is final");
  assert.equal(d.door(st, { type: "failed" }), st);
});

test("CR-014 door: a press before the hall is ready waits for it, or leaves straight away if it fails", () => {
  const s7 = { id: 7, starts_at: "", screen: { id: 1, name: "SCREEN 1" }, sales_closed: false };
  const q = d.door({ kind: "waiting" }, { type: "press", show: s7, reduced: false });
  assert.deepEqual(q, { kind: "queued", show: s7 });
  assert.deepEqual(d.door(q, { type: "ready" }), { kind: "walking", show: s7 }, "nothing moves until the hall is ready");
  assert.deepEqual(d.door(q, { type: "failed" }), { kind: "leaving", show: s7, how: "direct" });
  assert.deepEqual(d.door({ kind: "walking", show: s7 }, { type: "failed" }), { kind: "leaving", show: s7, how: "direct" },
    "the hall dying mid-walk still gets you to the seats");
});

test("CR-014 door: no live hall (404, no WebGL) - the picture stays and the door goes straight to the seats; reduced motion never walks", () => {
  const s7 = { id: 7, starts_at: "", screen: { id: 1, name: "SCREEN 1" }, sales_closed: false };
  const fb = d.door({ kind: "waiting" }, { type: "failed" });
  assert.deepEqual(fb, { kind: "fallback" });
  assert.deepEqual(d.door(fb, { type: "press", show: s7, reduced: false }), { kind: "leaving", show: s7, how: "direct" });
  assert.deepEqual(d.door({ kind: "live" }, { type: "press", show: s7, reduced: true }), { kind: "leaving", show: s7, how: "direct" });
  assert.deepEqual(d.door({ kind: "waiting" }, { type: "press", show: s7, reduced: true }), { kind: "leaving", show: s7, how: "direct" });
  assert.deepEqual(d.door({ kind: "live" }, { type: "reset" }), { kind: "waiting" }, "another screen: back to the picture");
  assert.deepEqual(d.door(fb, { type: "reset" }), { kind: "waiting" });
  assert.deepEqual(d.door({ kind: "live" }, { type: "landed" }), { kind: "live" }, "a stray landing does not leave");
});

test("the hero door's show: the chosen one if open, else the first open one, else none", () => {
  const s = (id, closed = false) => ({ id, starts_at: "", screen: { id: 1, name: "SCREEN 1" }, sales_closed: closed });
  assert.equal(d.doorShow([s(1, true), s(2), s(3)], 3).id, 3);
  assert.equal(d.doorShow([s(1, true), s(2), s(3)], null).id, 2);
  assert.equal(d.doorShow([s(1, true), s(2)], 1).id, 2, "a closed choice falls back to an open show");
  assert.equal(d.doorShow([s(1, true)], null), null);
});

test("the hero door: the corridor picture is a button named for the show, and a Book button does the same", () => {
  const show = { id: 7, starts_at: "2026-11-22T19:30:00+05:30", screen: { id: 3, name: "SCREEN 3" }, sales_closed: false };
  const doc = render(TheatreDoor, { show, film: { title: "Silent Sky" } });
  const buttons = all(doc, (e) => role(e) === "button");
  assert.equal(buttons.length, 2);
  assert.equal(name(buttons[0], doc), "Enter SCREEN 3 for Silent Sky at 7:30 pm");
  assert.match(name(buttons[1], doc), /^Book · SCREEN 3 · 7:30 pm$/);
  assert.match(text(doc), /SCREEN 3/);
});


test("CR-013: the star bands are the server's five, best first, labelled with stars, range and review count", () => {
  assert.deepEqual([...d.REVIEW_BANDS], ["9-10", "7-8", "5-6", "3-4", "1-2"]);
  assert.deepEqual(d.REVIEW_BANDS.map(d.bandStars), ["★★★★★", "★★★★", "★★★", "★★", "★"]);
  const counts = { "9-10": 123, "7-8": 4, "5-6": 0, "3-4": 1, "1-2": 2 };
  assert.equal(d.bandLabel("9-10", counts), "★★★★★ 9–10 (123)");
  assert.equal(d.bandLabel("5-6", counts), "★★★ 5–6 (0)");
  assert.equal(d.bandLabel("1-2", null), "★ 1–2", "no count until the list has answered");
});
