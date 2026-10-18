// S-ACC-14 (the sign-in screen's half: the logic, not the browser): where sign-in goes, and the pending selection's age.
// Run: node --test frontend/src/features/auth/auth.test.mjs
import assert from "node:assert/strict";
import { test } from "node:test";
import { CONTEXT_NOTE, PENDING_KEY, destination, nextPath, pending } from "./session.ts";

const store = (v) => {
  const m = new Map(v === undefined ? [] : [[PENDING_KEY, JSON.stringify(v)]]);
  return { getItem: (k) => m.get(k) ?? null, removeItem: (k) => m.delete(k), map: m };
};
const AT = Date.parse("2026-08-14T10:00:00Z");
const SEL = { showtime_id: 412, seat_ids: [1187, 1188], stored_at: "2026-08-14T10:00:00Z" };

test("a fresh pending selection sends sign-in back to its seat map", () => {
  assert.equal(destination("", store(SEL), AT + 60_000), "/showtimes/412");
  assert.deepEqual(pending(store(SEL), AT), SEL);
  assert.equal(CONTEXT_NOTE, "Your seats are still selected. Sign in to hold them.");
});

test("older than 30 minutes by the browser's clock it is discarded, and the listing opens", () => {
  const s = store(SEL);
  assert.equal(destination("", s, AT + 30 * 60_000 + 1), "/");
  assert.equal(s.map.has(PENDING_KEY), false);
  assert.equal(destination("", store(SEL), AT + 30 * 60_000), "/showtimes/412");
});

test("storage that throws stores nothing and still signs in to the listing", () => {
  const broken = { getItem() { throw new Error("denied"); }, removeItem() { throw new Error("denied"); } };
  assert.equal(destination("", broken, AT), "/");
});

test("an interrupted request returns to its own path, and never to another origin", () => {
  assert.equal(nextPath("?next=%2Fbookings%2FFR-ACDE-FHJ2"), "/bookings/FR-ACDE-FHJ2");
  assert.equal(nextPath("?next=//evil.example"), null);
  assert.equal(nextPath("?next=https://evil.example"), null);
  assert.equal(destination("?next=%2Fbookings", store(SEL), AT), "/bookings");
});
