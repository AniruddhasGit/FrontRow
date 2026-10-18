// S-SCP-07: the admin showtime list and edit routes, as rendered (frontend/src/test/render.mjs), offer no control
// that withdraws, cancels, deletes or pulls a showtime. Run: node --test "frontend/src/features/admin/*.test.mjs"
import assert from "node:assert/strict";
import { test } from "node:test";
import { CONTROL_ROLES, all, atUrl, load, name, render, role } from "../../test/render.mjs";

atUrl("/admin/showtimes");
const { ShowtimesScreen } = await load("/src/features/admin/ShowtimesScreen.tsx");

const showtime = (id, starts_at, ends_at) => ({
  id, movie_id: 3, movie_title: "The Long Night", starts_at, ends_at, base_price_paise: 25000,
  seat_count_at_creation: 220, booked_seat_count: id === 1 ? 0 : 12, version: 4,
});
const DAY = [showtime(1, "2026-08-14T11:00:00", "2026-08-14T13:05:00"), showtime(2, "2026-08-14T19:30:00", "2026-08-14T21:50:00")];
const SEED = { halls: [{ id: 4, name: "Hall 4" }, { id: 5, name: "Hall 5" }], hallId: "4", date: "2026-08-14", day: DAY };

const controlNames = (doc) => all(doc, (e) => CONTROL_ROLES.has(role(e))).map((e) => name(e, doc));

test("S-SCP-07: no control on the showtime list or the edit form matches withdraw|cancel|delete|pull", () => {
  const list = render(ShowtimesScreen, { seed: SEED });
  const edit = render(ShowtimesScreen, { seed: { ...SEED, editing: DAY[1] } });
  const listNames = controlNames(list);
  const editNames = controlNames(edit);
  // Not vacuous: the day's showtimes and the form's controls are there to be named.
  assert.ok(listNames.some((n) => n.includes("The Long Night")) && listNames.includes("Create showtime"), listNames.join(" | "));
  assert.ok(editNames.includes("Save changes") && editNames.includes("Discard this form") && editNames.includes("Hall"), editNames.join(" | "));
  for (const names of [listNames, editNames]) assert.deepEqual(names.filter((n) => /withdraw|cancel|delete|pull/i.test(n)), []);
});
