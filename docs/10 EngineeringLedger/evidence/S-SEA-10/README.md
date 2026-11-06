# S-SEA-10

## 2026-11-07: Done (built)

**Backend clauses** (unchanged, passing): `tests/sea/test_s_sea_10.py` (401 with no and an expired session, KEYS
unchanged, the guest seat map 200, the check on the router, manager and admin 201), in the 2026-11-07 run of tests/sea.

**Guest action** (built with S-ACC-14): the primary action reads "Sign in to hold these seats", writes the selection and
opens sign-in with no hold request (render.test.mjs; S-ACC-14 browser_check.js: 0 `/holds` requests from the guest press).

**Return, REAL mode** (`browser_check.js` + `redis_keys.sh` here, local compose stack, real Redis and PostgreSQL):
a guest chose seats 89 and 90 on showtime 367, pressed the action, registered, and came back to the map with both
restored and the action reading "Hold these seats". `redis_keys_2026-11-06.log` (UTC; 2026-11-07 IST) shows
`KEYS lock:seat:367:*` empty on every poll from 21:39:43 to 21:40:11, including the 15 seconds after the return; the
locks appear at 21:40:12, after the press (POST /holds at 21:40:11), and are gone after "Give up these seats".
Caveat: the running API was main's (built before CR-002 C-1), so the check patched `max_seats_per_booking` into the
seat-map response; nothing else was mocked.
