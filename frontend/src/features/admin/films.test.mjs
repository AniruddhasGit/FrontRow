// SCR-ADM-01, SCR-ADM-02 and SCR-ADM-07 as rendered (frontend/src/test/render.mjs), plus their pure words (films.ts).
// Run: node --test "frontend/src/features/admin/*.test.mjs"
import assert from "node:assert/strict";
import { test } from "node:test";
import { CONTROL_ROLES, all, atUrl, load, name, render, role, text } from "../../test/render.mjs";

atUrl("/admin/movies");
const { FilmsScreen } = await load("/src/features/admin/FilmsScreen.tsx");
const { FilmEditor } = await load("/src/features/admin/FilmEditor.tsx");
const { ListsScreen } = await load("/src/features/admin/ListsScreen.tsx");
const { readout, usage, windowLine } = await load("/src/features/admin/films.ts");

const film = (over = {}) => ({
  id: 4, title: "DEMO MOVIE 04", synopsis: "Demonstration film.", runtime_minutes: 148, certification_id: 2, language_id: 1,
  genre_ids: [3], certification: { id: 2, name: "DEMO RATING 2" }, language: { id: 1, name: "DEMO LANGUAGE A" },
  genres: [{ id: 3, name: "DEMO GENRE 1" }], poster_present: false, published_at: null, display_from: null, display_until: null,
  published: false, window_open: false, is_visible_now: false, version: 3, ...over,
});
const LOOKUPS = { language: [{ id: 1, name: "DEMO LANGUAGE A" }], certification: [{ id: 2, name: "DEMO RATING 2" }], genre: [{ id: 3, name: "DEMO GENRE 1" }] };
const controls = (doc) => all(doc, (e) => CONTROL_ROLES.has(role(e))).map((e) => name(e, doc));

test("S-ADM-21: an empty language list renders no language select and the empty-vocabulary sentence instead", () => {
  const doc = render(FilmEditor, { seed: { film: null, lookups: { ...LOOKUPS, language: [] } } });
  assert.ok(text(doc).includes("There are no languages on the list yet. Add one before saving this film."));
  const selects = all(doc, (e) => e.tag === "select").map((e) => name(e, doc));
  assert.deepEqual(selects, ["Certification", "Genres"]); // not vacuous: the other two vocabularies DO render a select
  assert.ok(controls(doc).includes("Manage lists"));
});

test("SCR-ADM-02: a new film has no publish control and says to save before uploading", () => {
  const doc = render(FilmEditor, { seed: { film: null, lookups: LOOKUPS } });
  assert.equal(text(all(doc, (e) => e.tag === "h1")[0]), "New film");
  assert.ok(text(doc).includes("Save this film first, then upload its poster."));
  assert.ok(!controls(doc).includes("Publish") && controls(doc).includes("Save"));
});

test("SCR-ADM-02: a saved draft shows both gates separately and a disabled publish naming what is missing", () => {
  const doc = render(FilmEditor, { seed: { film: film(), lookups: LOOKUPS, now: "2026-10-18T15:00:00" } });
  const body = text(doc);
  assert.ok(body.includes("Not published. Customers cannot see this film."));
  assert.ok(body.includes("No display window set. Customers cannot see this film."));
  assert.ok(body.includes("This film has no poster. Upload a poster before publishing it."));
  const publish = all(doc, (e) => role(e) === "button" && name(e, doc) === "Publish")[0];
  assert.ok(publish && "disabled" in publish.attrs);
  const file = all(doc, (e) => e.tag === "input" && e.attrs.type === "file")[0];
  assert.equal(file.attrs["aria-describedby"], "poster-limits");
  assert.ok(controls(doc).includes("Upload poster") && controls(doc).includes("Shown from (India time)"));
});

test("SCR-ADM-02: a published film offers withdrawal with the never-deleted note", () => {
  const doc = render(FilmEditor, { seed: { film: film({ published: true, poster_present: true, window_open: true,
    published_at: "2026-10-02T04:05:06Z", display_from: "2026-10-01T00:00:00", display_until: "2026-10-30T00:00:00" }), lookups: LOOKUPS } });
  assert.ok(controls(doc).includes("Withdraw from customers") && controls(doc).includes("Replace poster"));
  assert.ok(text(doc).includes("Films are never deleted. Withdraw a film instead, so that past bookings still make sense."));
  assert.ok(text(doc).includes("Published.") && text(doc).includes("Inside its display window."));
});

test("SCR-ADM-02: a closed window says whether it has not started or has ended, against the venue's local time", () => {
  const f = film({ display_from: "2026-10-25T00:00:00", display_until: "2026-11-01T00:00:00" });
  assert.equal(windowLine(f, "2026-10-18T15:00:00"), "Its display window has not started yet. Customers cannot see this film until then.");
  assert.equal(windowLine(f, "2026-11-02T00:00:00"), "Its display window has ended. Customers can no longer see this film.");
});

test("SCR-ADM-01: one row link per film named by title, both gates and the poster words, and the readout", () => {
  const items = [film(), film({ id: 5, title: "DEMO MOVIE 05", published: true, window_open: true, poster_present: true,
    display_from: "2026-10-01T00:00:00", display_until: "2026-10-30T00:00:00" })];
  const doc = render(FilmsScreen, { seed: { items, total: 2, failed: [5] } });
  const rows = all(doc, (e) => role(e) === "link" && (e.attrs.href ?? "").startsWith("/admin/movies/") && e.attrs.href !== "/admin/movies/new");
  assert.deepEqual(rows.map((r) => name(r, doc)), [
    "DEMO MOVIE 04, Draft, no display window set, no poster",
    "DEMO MOVIE 05, Published, in window, poster could not be loaded"]);
  assert.ok(text(doc).includes("Poster could not be loaded. Reload the page.") && text(doc).includes("No poster"));
  assert.ok(text(doc).includes("Films 1 to 2 of 2"));
  assert.ok(!controls(doc).includes("Newer films") && !controls(doc).includes("Older films")); // absent, not disabled
});

test("SCR-ADM-01: the readout's every published form", () => {
  assert.equal(readout(0, 50, 128), "Films 1 to 50 of 128");
  assert.equal(readout(100, 28, 128), "Films 101 to 128 of 128");
  assert.equal(readout(0, 7, 7), "Films 1 to 7 of 7");
  assert.equal(readout(0, 1, 1), "Film 1 of 1");
  assert.equal(readout(0, 0, 0), "No films");
});

test("SCR-ADM-07: tabs, withdrawn rows listed with Restore, counts in all three forms, and no delete or edit control", () => {
  const items = [{ id: 1, name: "Hindi", is_active: true, reference_count: 3 }, { id: 2, name: "Hnidi", is_active: false, reference_count: 1 },
    { id: 3, name: "Tamil", is_active: true, reference_count: 0 }];
  const doc = render(ListsScreen, { seed: { kind: "language", items } });
  assert.deepEqual(all(doc, (e) => role(e) === "tab").map((e) => name(e, doc)), ["Languages", "Certifications", "Genres", "Formats"]);
  const names = controls(doc);
  assert.ok(names.includes("Withdraw Hindi") && names.includes("Restore Hnidi") && names.includes("Add to list"));
  assert.deepEqual(names.filter((n) => /delete|remove|rename|edit/i.test(n)), []);
  assert.ok(text(doc).includes("Used by 3 films") && text(doc).includes("Used by 1 film") && text(doc).includes("Not used by any film yet"));
  assert.equal(usage("format", 1), "Used by 1 showtime");
  assert.equal(usage("format", 0), "Not used by any showtime yet");
  const withdrawn = all(doc, (e) => e.tag === "li" && (e.attrs.class ?? "").includes("admin-withdrawn"))[0];
  assert.equal(withdrawn.attrs["aria-label"], "Hnidi, withdrawn, Used by 1 film");
});
