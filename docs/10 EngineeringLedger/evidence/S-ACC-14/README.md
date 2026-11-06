# S-ACC-14

## 2026-11-07: Done (built)

**Built:** `frontend/src/features/auth/session.ts` (`signInHref`, `leaveForSignIn`, `takenMessage`, notice hand-off; a stale
entry is discarded with the `fr.selection` it came from), `SeatMapScreen.tsx` (the guest action writes and opens sign-in;
the return re-checks against the first fresh map, names what went, removes `fr.pending_selection`, takes no hold; a 404
for the carried showtime returns to the listing), `Shell.tsx` + `router.tsx` `Link before` (the header's Sign in writes
the same entry), `ListingScreen.tsx` (shows "That showtime is no longer available."). The accessible-name ending is now
`held by someone else`, as amended (AMENDMENTS.md line 37).

**Run:**
- `node --test "src/**/*.test.mjs"`: 158/158 pass (`auth.test.mjs` 9 tests, 5 new; `render.test.mjs` "S-ACC-14: after the
  restore, a now-sold C12 and a now-held C13 carry their published names"); `npx tsc --noEmit -p .` clean; `npm run build` ok.
- Browser (Playwright, MOCK mode, the round-4 plan): `browser_check.js` here, **32/32 PASS**, both exits: pending written
  before `/sign-in` is pushed with the exact published value, both keys present, context note, GET seatmap before the
  restore's `fr.selection` write, all three sentences, the two accessible names, pending removed, survivors in
  `fr.selection`, **0** `POST …/holds` after sign-in, primary reads "Hold these seats", stale entry discarded,
  throwing storage (signed in, map, no selection, no message), missing showtime (listing + sentence), sign-out sweep 0.

**[JUDGMENT CALL]** Sign-in from a seat map carries `?next=/showtimes/{id}` (the path only, no seat ids) by both routes,
so a visitor whose storage throws still returns to the map (P-ACC-13 row 5). The restore runs whenever a fresh entry
exists for that showtime, including a guest who backs out of sign-in (ponytail comment in SeatMapScreen.tsx).
