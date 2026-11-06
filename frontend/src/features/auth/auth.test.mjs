// S-ACC-14 (the sign-in screen's half: the logic, not the browser): where sign-in goes, and the pending selection's age.
// Run: node --test frontend/src/features/auth/auth.test.mjs
import assert from "node:assert/strict";
import { test } from "node:test";
import {
  CONTEXT_NOTE, PENDING_KEY, SHOWTIME_GONE, destination, leaveForSignIn, leaveNotice, nextPath, pending, signInHref, takeNotice, takenMessage,
} from "./session.ts";

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

// S-ACC-14 / S-SEA-10, the seat map's half: what leaving writes, and what the return restores and says.
const full = (init = {}) => {
  const m = new Map(Object.entries(init));
  return { getItem: (k) => m.get(k) ?? null, setItem: (k, v) => m.set(k, String(v)), removeItem: (k) => m.delete(k), map: m };
};
const LIVE = JSON.stringify({ showtime_id: 412, seat_ids: [1187, 1188] });

test("leaving a seat map with a selection writes the pending entry beside fr.selection, by either route", () => {
  const s = full({ "fr.selection": LIVE });
  assert.equal(signInHref("/showtimes/412"), "/sign-in?next=%2Fshowtimes%2F412");
  leaveForSignIn("/showtimes/412", s, AT);
  assert.deepEqual(JSON.parse(s.map.get(PENDING_KEY)), SEL);
  assert.equal(s.map.get(PENDING_KEY), JSON.stringify(SEL)); // key order as published
  assert.deepEqual([...s.map.keys()].sort(), ["fr.pending_selection", "fr.selection"]); // two keys, both present
  assert.equal(destination(new URL(signInHref("/showtimes/412"), "http://x").search, s, AT), "/showtimes/412");
});

test("nothing is written from any other screen, with an empty or another showtime's selection, or when storage throws", () => {
  for (const [path, init] of [["/", { "fr.selection": LIVE }], ["/showtimes/412", {}], ["/showtimes/413", { "fr.selection": LIVE }],
    ["/showtimes/412", { "fr.selection": JSON.stringify({ showtime_id: 412, seat_ids: [] }) }]]) {
    const s = full(init);
    leaveForSignIn(path, s, AT);
    assert.equal(s.map.has(PENDING_KEY), false, path);
  }
  assert.equal(signInHref("/movies/3"), "/sign-in");
  const broken = { getItem() { throw new Error("denied"); }, setItem() { throw new Error("denied"); }, removeItem() { throw new Error("denied"); } };
  leaveForSignIn("/showtimes/412", broken, AT); // does not throw
  assert.equal(destination("?next=%2Fshowtimes%2F412", broken, AT), "/showtimes/412"); // the map still opens
});

test("a stale entry is discarded with the selection it carried, so the map opens with nothing chosen", () => {
  const s = full({ "fr.selection": LIVE, [PENDING_KEY]: JSON.stringify(SEL) });
  assert.equal(pending(s, AT + 30 * 60_000 + 1), null);
  assert.equal(s.map.size, 0);
});

test("the return-from-sign-in sentence: one, two or more, and none surviving", () => {
  assert.equal(takenMessage([], 2), null);
  assert.equal(takenMessage(["C12"], 1), "C12 was taken while you were signing in. Your other seats are still selected.");
  assert.equal(takenMessage(["C12", "C13"], 1), "C12 and C13 were taken while you were signing in. Your other seats are still selected.");
  assert.equal(takenMessage(["C12", "C13", "C14"], 1), "C12, C13 and C14 were taken while you were signing in. Your other seats are still selected.");
  assert.equal(takenMessage(["C12", "C13"], 0), "The seats you chose were taken while you were signing in. Choose again from the map.");
});

test("a showtime that no longer exists leaves one notice for the listing, read once", () => {
  const s = full();
  leaveNotice(s, SHOWTIME_GONE);
  assert.equal(SHOWTIME_GONE, "That showtime is no longer available.");
  assert.equal(takeNotice(s), SHOWTIME_GONE);
  assert.equal(takeNotice(s), null);
  assert.ok([...s.map.keys()].every((k) => k.startsWith("fr.")) || s.map.size === 0);
});
