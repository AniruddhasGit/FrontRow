# S-PAY-12 — Done

Lane `p4-booking`, workflow wf_61979593-b09, 2026-10-18. Verifier verdict: PASS_WITH_DEFECTS; this row was not refuted.

**Evidence:** frontend/src/features/booking/checkout.test.mjs (node --test, 17 pass / 0 fail): 'the key is the CSPRNG UUID's canonical form and the only randomness in frontend/src', 'the key is stored with its hold token before the request is issued, and is the header the request carries', 'a refresh or a dropped connection re-sends the same key; a 402 or a new hold token mints a new one', 'sign-out sweeps every fr.* value, the last booking and the hold included'. Mutation check: removing the pre-fetch storage write turned 4 tests red; restoring it gave 17/17.

**Note:** These tests were written after checkout.ts. Red was shown by a mutation check instead of a test-first run. The repository-wide sweeps give Math.random 0 and randomUUID exactly 1 hit (checkout.ts:55). 1000 minted keys match the v4 UUID pattern and none starts with the fail prefix. A page refresh mid-flight is modelled as a fresh pay() call on the same storage, not in a browser. The key is cleared on 201 and on 402, and sign-out sweeps every fr.* key. The only sign-out control is on /bookings (account/MyBookingsScreen.tsx signOut()): the header account slot is passed in by App.tsx, which this lane does not own.
