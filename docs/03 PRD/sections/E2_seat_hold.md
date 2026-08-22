# E2 — Seat selection and the hold

This epic covers everything between a customer looking at a seat map and a customer having seats that
are provably theirs for three minutes. It owns the interactive behaviour of the map — what a tap
does, what the running total says, which seats may be chosen — and it owns the hold itself: acquiring
it, its expiry, giving seats back, and every way it can fail. It does not own the seat-map read
endpoint, payment, or the confirm endpoint. It does own the seat's view of what confirm does to it.

**The one thing that will be got wrong.** There are two clocks and only one of them is authoritative.
The browser runs a countdown from a server-issued instant so the customer can see how long they have;
the server never reads that countdown and never trusts it. Expiry is decided by one thing only —
whether a key still exists in Redis at the moment the server asks. Every specification below that
mentions time is written so that a client whose clock is wrong produces a wrong display and never a
wrong outcome. The second-most-likely error is writing 7 minutes: the hold is **180 seconds**
(`SRC-003 OPEN-HOLD-01`, `SRC-002 §E E-1`), and any document, test, fixture or comment saying 7
minutes is a defect.

---

## S4 — Product specifications

### `P-SEA-01` · Allow any available seat to be chosen · `RULED`
`[SRC: SRC-003 OPEN-SEAT-02 · SRC-003 OPEN-SEAT-03 · SRC-003 OPEN-SEAT-04 · FR-ADR-016]`
`[BRD: R-SEAT-05]`

**Behaviour.** Every seat is sold individually. Any seat in the `available` state may be chosen, in
any combination, with no restriction on adjacency, pairing or the gaps a selection leaves behind.

**Who may do it.** guest, customer, manager, admin — choosing is a client-side act against a public
seat map and changes no server state, so no authorisation applies. The authorisation boundary is the
hold (`P-HLD-05`).

**Preconditions.** A seat map for the showtime has loaded. The seat's state in that payload is
`available`.

**Happy path.**
1. The customer taps a seat whose state is `available`.
2. The seat joins the customer's local selection.
3. The running total updates (`P-SEA-04`).
4. No request is sent and no lock is taken.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | The customer taps a seat whose state is `sold` | no request is sent | (nothing — the cell does not respond to a tap; its accessible name already ends `sold`) |
| 2 | The customer taps a seat whose state is `held_by_other` | no request is sent | (nothing — the cell does not respond to a tap; its accessible name already ends `held by another customer`) |
| 3 | A seat id is submitted to the hold endpoint that is **not in this showtime's seat set** (`P-ADM-14`) | 422 `VALIDATION_FAILED` | `Seat C12 is not part of this hall. No seats were held.` — at two or more offending seats the plural is rendered instead: `Seats C12 and C13 are not part of this hall. No seats were held.` (`P-HLD-14` rows 12 and 22) |
| 4 | The customer taps a seat carrying `is_active: false` | no request is sent | (nothing — the cell does not respond to a tap; its accessible name already ends `out of service`) |
| 5 | A seat id carrying `is_active: false` is submitted to the hold endpoint anyway | 422 `VALIDATION_FAILED`, before any lock is touched | `Seat C12 is out of service. No seats were held.` — at two or more offending seats the plural is rendered instead: `Seats C12 and C13 are out of service. No seats were held.` (`P-HLD-14` rows 20 and 23) |

**Server-side validation.** On the hold request only: every `seat_id` must be an integer, must exist,
must be **a member of this showtime's seat set**, and **must be active**. A seat id that fails any of
these rejects the whole request with 422 `VALIDATION_FAILED` before any lock is touched.

**The membership test is the showtime's seat set, not the showtime's screen, and the two are different
sets.** A showtime's seats are materialised when the showtime is created and never change afterwards;
`P-ADM-14` owns that rule and this row does not restate it. The consequence that matters here is that
**a seat added to a hall after a showtime was created belongs to that screen and is not on that
showtime.** Tested against the screen, such a seat would pass validation and become holdable and
sellable on a showtime whose `seat_count_at_creation` does not count it — which is an oversell into a
showtime the seat is not part of, and it is exactly what the materialised set exists to prevent.
**The two checks are independent and both apply**: membership is fixed at showtime creation, while
`is_active` can change afterwards, so a seat retired after creation stays in the set and is refused by
the active check rather than the membership one.

**The active check is server-side and not a client courtesy**: the client is told a seat is out of service by
`is_active: false` in the map payload (`P-BRW-08`, `P-BRW-09`), and a client that ignores it, or a
caller with no client at all, would otherwise sell a seat in a hall it has left. There is no
accessible-seat flag, no pair or group linkage and no gap rule to validate against, because none
exists in the data model (`FR-ADR-016`).

**Worked example.** Not applicable — this specification computes nothing.

**Recorded, not challenged.** `SRC-003 OPEN-SEAT-02` rules out accessible-seat marking *because this
is a demonstration project with no real customers*. A real cinema in India operates under
accessibility obligations. This would need revisiting before anyone booked a real seat. It is a known
deferral, not an oversight.

---

### `P-SEA-02` · Render four seat states, and show a chosen seat as one of them · `RULED`
`[SRC: SRC-001 §5.2.2 · FR-ADR-045 · FR-ADR-046 · FR-ADR-051]`
`[BRD: R-SEAT-02]`

**Behaviour.** The seat map carries exactly four **rendered** states — `available`, `sold`,
`held_by_other`, `held_by_me` — and no others.

**Four is a count of renderings, not of wire values, and the two numbers differ on purpose.** The
enum the server emits has **three** values: `available`, `sold`, `held` (`P-SEA-05` step 3,
`EP-BRW-06`, rank 1). `held_by_other` and `held_by_me` are the two ways a client draws the single wire
value `held`, decided from its own hold token — so the fourth rendering is a **split of the third wire
value**, not a fourth value to look for. **A reader building from the enum and counting to four will
not find one**, which is why the count is qualified everywhere it is stated rather than only here.
The reason the server cannot emit four is that the seat map is one shared cached payload
(`FR-ADR-030`): the server does not know whose session is reading it, so "mine" is not a fact it
possesses. `FR-ADR-045`'s ruling of exactly four map states is about what a customer sees and holds
unchanged.

**A seat the customer has chosen but not yet held renders with the `held_by_me` treatment.** It is
tappable, carries the tick, and reads `held by you` in its accessible name. There is no fifth
rendering. The difference between *chosen* and *held* is carried entirely by two other surfaces: the
price summary heading (`3 seats chosen` against `3 seats held by you`) and the presence of the
countdown, which exists only when a hold is live.

This is a reconciliation, and it is flagged. `FR-ADR-045` fixes the count at four. `FR-ADR-046`
requires a guest to be able to click seats and watch a total build before any hold exists. Nothing
names a state for that seat. Reusing `held_by_me` is the only reading that satisfies both, and it is
reported in the lane notes for the merge pass to confirm or overturn.

**A seat carrying `is_active: false` is still one of the four rendered states and is drawn on top of
it.** The count stays four rendered, three on the wire. `is_active` is a **separate boolean** on every seat in the map payload, not a fifth
state, and `P-BRW-09` owns both the shape and the argument for it — the short form is that a retired
seat can also be `sold`, so a fifth enum value would have to displace the sale state and lose it. On
this screen the consequence is one rule: **an out-of-service seat is never selectable, in any state,
for any reader**, so it never enters the local selection, never reaches the running total
(`P-SEA-04`), and never reaches the hold endpoint (`P-SEA-01` exceptions 4 and 5). Its rendering and
its accessible name are in `SCR-SEA-01` below and are the same strings `SCR-BRW-03` publishes.

**Who may do it.** Everyone. The map is public (`FR-ADR-030`, `FR-ADR-046`).

**Preconditions.** The seat map payload has arrived.

**Happy path.**
1. The server sends **objective** state per seat: `available`, `sold` or **`held`**. The wire value
   is `held`, not `held_by_other` — the server does not know whose hold it is, and the seat map is
   one shared cached payload (`EP-BRW-06` is rank 1 under `S1.2`). **`held_by_other` and
   `held_by_me` are the two ways the client renders `held`**, decided from its own hold token.
2. The client reads its hold token and its local selection from `sessionStorage`.
3. Any seat in either set is overlaid as `held_by_me`.
4. Each cell is drawn with its fill, its mark and its border, per `COMPONENTS.md §1.4`.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | The payload contains a state name that is not one of the **three wire values** `available` / `sold` / `held` — including a payload that names `held_by_me` or `held_by_other`, which the server can never legitimately emit | the payload is rejected client-side | `The seat map could not be loaded.` with a control reading `Try again` |
| 2 | The seat list for the showtime is empty | 500 `INTERNAL_ERROR` | `The seat map could not be loaded.` with a control reading `Try again` |
| 3 | A poll fails after a good first load | the last good map stays on screen | `The seat map is not updating. The seats shown may be out of date.` |
| 4 | A seat object arrives with no `is_active` field | the payload is rejected client-side, exactly as row 1 — **a missing boolean read as "true" makes a retired seat tappable**, which is the one failure the field exists to stop | `The seat map could not be loaded.` with a control reading `Try again` |

**Server-side validation.** The map payload is assembled server-side and each seat carries exactly one
state **drawn from the three-value wire enum** `available` / `sold` / `held`. Neither `held_by_me` nor
`held_by_other` is a value the server can emit; a payload containing either is a defect, and so is a
client that expects a fourth wire value because a specification said "four states".

**Worked example.** Not applicable.

---

### `P-SEA-03` · Take nothing when a seat is selected · `RULED`
`[SRC: SRC-001 §4.1 · FR-ADR-046 · FR-ADR-014]`
`[BRD: R-SEAT-05 · R-HOLD-06]`

**Behaviour.** Selecting and deselecting seats is entirely client-side. No request is sent, no Redis
key is written, no row is inserted, and nothing on the server distinguishes a guest looking at a seat
map from a customer looking at one. Scarcity is consumed only at the hold.

**Who may do it.** Everyone, including a guest with no account.

**Preconditions.** None beyond a loaded map.

**Happy path.**
1. Tap an `available` seat — it enters the local selection.
2. Tap it again — it leaves the local selection.
3. The selection is written to `sessionStorage` under the key **`fr.selection`** on every change, so
   it survives a reload of this screen (`FR-ADR-046`). **This is not the key that carries a selection
   through sign-in** — that is `fr.pending_selection`, which `P-ACC-13` (lane E5) owns. The two keys
   and the reason there are two are in the table below.
4. The primary action is enabled once the selection is non-empty.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | The customer selects an eleventh seat locally | no request is sent | `Up to 10 seats.` — the note under the total; the eleventh tap does not add the seat and the map does not change |
| 2 | The tab is closed with a selection but no hold | no request is sent | (nothing — `sessionStorage` is discarded with the tab and nothing was held) |
| 3 | **The local selection is re-checked against a freshly fetched map and a chosen seat has gone** — a reload, a poll, or a return to the tab, with **no sign-in involved** | no request is sent for the selection; the map is refetched | `C12 is no longer available. It has been removed from your choices.` — **this row owns this string.** The return-from-sign-in case is a different situation with a different string and belongs to `P-ACC-13` (lane E5) |

**Two situations, two rows, and the split is deliberate.** A seat leaving a customer's selection has
exactly two causes and they are not the same event:

| Situation | Owned by | The customer reads |
|---|---|---|
| **The selection is re-checked against a fresh map and a seat has gone.** A reload, a poll, a return to the tab. **No sign-in is involved** and the customer was on this screen the whole time | **`P-SEA-03`, this row** | `C12 is no longer available. It has been removed from your choices.` |
| **The customer returns from registration or sign-in and a seat has gone.** They were away from the screen and the seat went while they were away | **`P-ACC-13`** (lane E5) | that row's string, which is not restated here |

**Why two and not one.** The second names *when* the seat went — "while you were signing in" — which
is information the first case does not have and must not claim. A customer who reloaded a page was
not signing in, and telling them so is a false statement about their own last thirty seconds. A third
variant existed across the document and is deleted; **each of these two rows names the other**, so a
reader who lands on either can tell the pair is a deliberate two rather than an accidental three.

**"Still selected", never "still held".** Nothing is held before a hold request is made, so a message
on *this* path can never truthfully say seats are still held. Every string on both sides of the split
says *selected* — `P-HLD-07`'s `Your other choices are still selected`, and `P-ACC-13`'s
`Your other seats are still selected.` **This rule is about the selection path and not about the hold
endpoint**: a request that extends a live hold can fail while seats genuinely are still held, and
`P-HLD-14` rows 2b and 3b publish the sentence for that.

**Two `sessionStorage` keys, two jobs, and a reader must not collapse them into one.**

| | `fr.selection` | `fr.pending_selection` |
|---|---|---|
| Owned by | **this row** | **`P-ACC-13`** (lane E5) |
| What it carries | the live local selection on this screen: the chosen-but-not-yet-held seat ids | a one-shot snapshot handed to the authentication round trip, with a `stored_at` instant |
| Written | **on every change** — every tap that adds or removes a seat | **once**, when a visitor who is not authenticated leaves this seat map for the authentication screen with a non-empty selection, before that step opens — **by either route out**, the primary action or the header's `Sign in` link (`E8 SCR-XCT-05`), because which control was pressed may not decide whether the selection survives (`P-ACC-13`) |
| Read | on load of `/showtimes/{showtime_id}`, to restore what was chosen and re-check it against the fresh map; and by `P-SEA-02` step 2 to draw chosen cells | once, on return from the authentication step |
| Deleted | when the selection empties, when those seats become a hold, and on sign-out | **immediately after that restore** (`P-ACC-13` step 8), and on sign-out |
| Staleness rule | none — it is discarded with the tab, which is the only lifetime it needs | discarded on restore if `stored_at` is more than 30 minutes old (`P-ACC-13`) |

**Both are inside the `fr.` namespace `P-ACC-13` sweeps on sign-out**, so neither needs its own
sign-out clause and neither is enumerated in that row's table — the sweep is by prefix, not by list.

**Why not one key, stated because one key is the obvious simplification.** `P-ACC-13` deletes its key
**immediately after the restore**, and this row's key is written **on every change** and must survive
a reload at any moment. Made one key, the return from sign-in would delete the only durable copy of a
selection that is still on screen and still chosen, so a customer who reloaded the page one second
after signing in would lose seats they can see are selected — the restore erasing the selection it
had just re-applied. The two write policies are incompatible in one key, which is why there are two.

**Where this row's exception-3 notice renders, and how a screen reader is told about it.** The string
`C12 is no longer available. It has been removed from your choices.` is **not** an error response and
carries **no error `code`** — nothing was requested, so nothing answered. It renders in `SCR-SEA-03`,
the seat-map banner, as that screen's one **client-originated** notice: same container, same live
region, no in-banner action, and dismissible because nothing is left to do. `SCR-SEA-03` names the
state and `SCR-SEA-01` names it in its states table. **Without that, the only announced surface on
this screen branched on a `code` this event does not carry**, and a screen-reader user was never told
a seat had left their selection.

**Server-side validation.** None applies, because nothing is sent. The interface limit in exception 1
is a convenience; the enforcement point is the hold endpoint (`P-HLD-04`).

**Worked example.** Not applicable.

---

### `P-SEA-04` · Update the running total as seats are selected · `RULED`
`[SRC: SRC-001 §5.2.4 · SRC-003 OPEN-PRICE-01 · SRC-003 OPEN-LOCALE-01 · FR-ADR-038 · FR-ADR-036 · FR-ADR-040 · FR-ADR-045]`
`[BRD: R-SEAT-04]`

**Behaviour.** The price summary shows a total that changes with every selection and deselection, and
that total is the figure the payment step will charge. The client never applies the uplift formula.
The seat-map payload carries `price_paise` per seat **already rounded by the server** with
`FR-ADR-038`'s rule, and the client only sums integers. That is how "the client uses the same per-seat
half-up rule the server uses" is satisfied — by construction, with one implementation of the
arithmetic, which is what `FR-ADR-038` requires.

**A partial total is never shown.** If the map has loaded but per-seat prices have not, the total is
absent and the primary action is disabled. A total computed from some of the seats is a wrong number.

**No tax line, no discount field, no booking fee, and no space left for one** (`FR-ADR-040`,
`SRC-003 OPEN-PRICE-02`, `OPEN-PRICE-03`).

**Who may do it.** Everyone, including a guest. Seeing the price is part of deciding
(`FR-ADR-046`).

**Preconditions.** The seat-map payload has arrived with a `price_paise` integer on every seat. Lane
E1's `P-BRW-08` and `EP-BRW-06` carry that field on the seat object, alongside `cat`.

**Happy path.**
1. The customer adds a seat to the selection.
2. The client adds that seat's `price_paise` to the running sum.
3. The sum is rendered from integer paise at the last possible moment, in `--fr-font-mono`, with
   Indian digit grouping and the `₹` symbol (`FR-ADR-036`).
4. The seat line for that seat appears in the summary with its label, its category and its own price.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | Some seats in the selection have no known price | no request | the total is not rendered at all; the primary action is disabled and the seat cap note reads `Up to 10 seats.` |
| 2 | No seats are selected | no request | the panel keeps its full height, the total reads `₹0.00`, and the note reads `Up to 10 seats.` |
| 3 | A price arrives that is not a non-negative integer | the payload is rejected client-side | `The seat map could not be loaded.` with a control reading `Try again` |

**Server-side validation.** `price_paise` is a non-negative integer in the payload. The total the
client displays is advisory; the total that is charged is the sum of the per-seat prices snapshotted
into the hold at acquisition (`P-HLD-11`) and re-read at confirm, never recomputed.

**Worked example — a multi-seat selection across two categories.**

Inputs, all in paise. `base_price_paise = 25000` for this showtime (₹250.00). Category uplifts, from
the seat-category table, in basis points: `Premium = 1250` (12.5%), `Recliner = 3333` (33.33%).

Per-seat price, by `FR-ADR-038`'s rule
`seat_price_paise = (base_price_paise * (10000 + uplift_basis_points) + 5000) // 10000`:

```
Premium   (25000 * (10000 + 1250) + 5000) // 10000
        = (25000 * 11250 + 5000) // 10000
        = (281250000 + 5000) // 10000
        = 281255000 // 10000
        = 28125                                   ->  ₹281.25   (exact; no rounding occurred)

Recliner  (25000 * (10000 + 3333) + 5000) // 10000
        = (25000 * 13333 + 5000) // 10000
        = (333325000 + 5000) // 10000
        = 333330000 // 10000
        = 33333                                   ->  ₹333.33   (exact value 33332.5, an exact half,
                                                                 taken up by half-up)
```

The customer selects two Premium seats and then three Recliner seats. The total after each tap:

| Tap | Seat added | Running sum, paise | Rendered |
|---|---|---|---|
| 1 | Premium | 28125 | `₹281.25` |
| 2 | Premium | 56250 | `₹562.50` |
| 3 | Recliner | 89583 | `₹895.83` |
| 4 | Recliner | 122916 | `₹1,229.16` |
| 5 | Recliner | 156249 | `₹1,562.49` |

**Expected answer: `156249` paise, rendered `₹1,562.49`.**

**Why the total is never rounded, made concrete on these same inputs.** Rounding once at the end would
give a different answer:

```
per seat, then sum   (the rule):  2*28125 + 3*33333     = 56250 + 99999   = 156249  ->  ₹1,562.49
round the total once (rejected):  2*28125 + 3*33332.5   = 56250 + 99997.5 = 156247.5
                                  half-up                                 = 156248  ->  ₹1,562.48
```

One paisa apart, and the first is the figure the customer was shown three times on the seat map. This
is the disagreement `SRC-003 OPEN-PRICE-01` warned about.

---

### `P-SEA-05` · Let sold win over any lock when the map is assembled · `RULED`
`[SRC: SRC-002 §8.1.5 · FR-ADR-024 · FR-ADR-029 · FR-ADR-045]`
`[BRD: R-SEAT-02 · R-QLY-01]`

**Behaviour.** A seat's map state is computed from two sources — a `booking_seat` row in PostgreSQL
and a lock key in Redis — and **`sold` always wins.** A seat with both a committed booking row and a
live lock renders `sold`, never `held_by_other` and never `held_by_me`.

**Why this rule has to be written down.** Locks are released *after* commit, not before
(`FR-ADR-029`), so there is always a window in which both exist. If the container dies inside that
window the lock survives for the remainder of its TTL against a seat that is already sold. Without an
explicit precedence rule, two correct sources produce two different answers for the same seat.

**Who may do it.** Nobody — this is an assembly rule on the read path.

**Preconditions.** None.

**Happy path.**
1. Read the committed `booking_seat` rows for the showtime.
2. Read the lock keys for the showtime.
3. For each seat, emit exactly one **wire** state, in this precedence: a committed `booking_seat` row
   makes it `sold`; otherwise a live lock key makes it `held`; otherwise it is `available`. The three
   wire states are the whole vocabulary the server emits — `held_by_other` and `held_by_me` are never
   wire values, because the map is one shared cached payload and the server does not know whose
   session is reading it (`EP-BRW-06`, rank 1 under `S1.2`).
4. The client renders each `held` seat as `held_by_me` when its own hold token owns that seat and as
   `held_by_other` otherwise (`P-SEA-02`). `sold` and `available` render as themselves.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | A residual lock exists on a sold seat after a container death | the seat renders `sold` | (nothing — the seat is drawn `sold` with its hatch mark, as it would be at any other time) |
| 2 | Redis is unreachable, so lock state is unknown | **503 `DEPENDENCY_UNAVAILABLE`.** The rate limiter reads Redis and runs **before** the cache, so the request never reaches the PostgreSQL fallback (`X-7`, adjudicated: `FR-ADR-058` fails closed, and that is stricter than `FR-ADR-028`'s degrade). The map is therefore not served at all rather than served without hold state | "The seat map is unavailable right now. You can still browse showtimes. Try again in a few minutes." |

**Server-side validation.** Not applicable.

**Worked example.** Not applicable.

---

### `P-SEA-06` · Implement the seat lifecycle exactly as the state machine below · `RULED`
`[SRC: SRC-001 §5.2.5 · SRC-001 §5.2.6 · SRC-002 §E E-1 · SRC-002 §8.1.2 · SRC-002 §8.1.3 · SRC-002 §8.1.4 · FR-ADR-024 · FR-ADR-025 · FR-ADR-026 · FR-ADR-027 · FR-ADR-029 · FR-ADR-033 · FR-ADR-045 · FR-ADR-047 · FR-ADR-052]`
`[BRD: R-SEAT-02 · R-HOLD-01 · R-HOLD-05]`

**Behaviour.** One seat, for one showtime, as seen by one customer session, is in exactly one of five
states at every instant. Every input the system can deliver to that seat has a defined result in
every state. The machine is normative: a behaviour not in the table is a defect, and an input handled
differently from the table is a defect.

**Who may do it.** Not applicable — this is the model the other specifications in this section are
written against.

**Preconditions.** None.

**Happy path.** `available` → `held_by_me` → `held_by_me_paying` → `sold`.

**Exception paths.** The transition table below is the exception path list, in full.

**Signing out releases a live hold, and the machine carries `SIGN_OUT` as an input for it.** The
customer has said they are done; leaving their seats locked for the remainder of 180 seconds consumes
scarcity on behalf of somebody who has left. This is the one session event that **does** release —
`TAB_CLOSED` deliberately does not, because an unload handler is unreliable and a fire-and-forget
release from a closing page can arrive after the key has expired and been re-acquired. **Sign-out is a
request the customer made, answered synchronously, with a session to end either way**, so it has none
of those properties.

**Every `No seats were held.` string in the machine is the *first-hold* form.** The machine describes
one seat, so it cannot see whether the request that failed was this customer's first hold on the
showtime or an extend of a live one — and the two are told different sentences, because on an extend
the seats already held are not in this request's rollback set (`P-HLD-01`) and survive. **The
substitution rule is `P-HLD-14`'s**, which owns this lane's message set: the closing clause reads
`No seats were held.` on a first hold and `Your hold is unchanged.` on an extend, and rows 2b and 3b
publish the two `SEAT_UNAVAILABLE` extend forms verbatim. Every `user_sees` value in the block below
that ends `No seats were held.` is therefore the rendering when the customer held nothing on this
showtime at the moment the request arrived — the ordinary case, and not the only one.

**Server-side validation.** Every guard marked *server* in the table is enforced server-side. No guard
is enforced only in the interface.

**Worked example.** `P-HLD-03` carries the timing example the machine depends on.

The full specification follows in **the seat lifecycle state machine**, below.

---

### The seat lifecycle state machine

#### The five states

The machine describes **one seat, for one showtime, from the point of view of one customer session**.
`held_by_me` and `held_by_other` are relative to that session; they are not properties of the seat in
the abstract.

| State | What is true | Seat-map rendering |
|---|---|---|
| `available` | No `booking_seat` row and no live lock key for this seat | `available` |
| `held_by_me` | A live lock key exists and its value is this session's hold token. No confirm is in flight | `held_by_me` |
| `held_by_me_paying` | As `held_by_me`, and a confirm transaction for this hold has passed its Redis re-validation and has not yet ended | `held_by_me` |
| `held_by_other` | A live lock key exists and its value is not this session's hold token | `held_by_other` |
| `sold` | A committed `booking_seat` row exists for `(showtime_id, seat_id)` | `sold` |

**`held_by_me_paying` is a lifecycle state, not a fifth map state.** It renders identically to
`held_by_me`, so `FR-ADR-045`'s ruling of exactly four **rendered** map states — against three wire values (`P-SEA-02`) — holds unchanged. It is a distinct
lifecycle state because five inputs — `CONFIRM_COMMIT`, `CONFIRM_UNIQUE_VIOLATION`,
`CONFIRM_PAYMENT_FAILED_HOLD_LIVE`, `INSTANCE_KILLED_POSTCOMMIT` and `SIGTERM_DRAIN` — have different
results in it than in `held_by_me`, and a machine that could not distinguish them would have to make
`SIGTERM_DRAIN` both release the seat and not release it.

**States considered and rejected, because they cannot be reached or cannot be distinguished:**

- **`sold_with_residual_lock`** — the window after commit and before the post-commit lock release
  (`FR-ADR-029`), including the case where the container dies inside it. Rejected: no input produces a
  different result there than in `sold`. Every other customer is refused by the lock *and* by the
  unique constraint; the owner's retry replays through the idempotency record; the map shows `sold`
  because `sold` wins (`P-SEA-05`). It is `sold` with garbage that expires.
- **`chosen_not_held`** — a seat in the customer's local selection with no lock. Rejected as a machine
  state: the server has no knowledge of it and it changes no server behaviour, so it is `available`
  with a client-side overlay (`P-SEA-02`, `P-SEA-03`). The `SELECT` input's self-loop on `available`
  is where it lives.
- **`expired_awaiting_poll`** — the client's belief between its countdown reaching zero and the next
  poll. Rejected: it is a display state on one client, not a state of the seat. `FR-ADR-047` is
  explicit that the client reports only what its own clock says and claims nothing about the seat.
- **`sales_closed`** — rejected: the cut-off is a property of the showtime, not of a seat. It makes
  every seat unselectable without changing any seat's state, which is why `SALES_CUTOFF_PASSES` is a
  self-loop in all five states.

#### The twenty-nine inputs

| Input | Meaning |
|---|---|
| `SELECT` | The customer adds this seat to their client-side selection, or a hold request names a seat they already hold |
| `DESELECT` | The customer taps this seat to give it back, or removes it from their client-side selection |
| `HOLD_REQUEST_GUEST` | A hold request arrives with no authenticated user |
| `HOLD_REQUEST_OVER_CAP` | A hold request arrives that would take this customer over ten seats on this showtime |
| `HOLD_REQUEST_DUPLICATE_SEAT` | A hold request arrives naming the same seat id more than once, or naming a seat that is not in this showtime's seat set (`P-ADM-14`) |
| `HOLD_REQUEST_SALES_CLOSED` | A hold request arrives at or after the showtime's sales cut-off |
| `HOLD_REQUEST_REDIS_DOWN` | A hold request arrives and Redis is unreachable |
| `HOLD_ACQUIRE_OK` | `SET key token NX PX ttl` returned OK for this seat |
| `HOLD_ACQUIRE_LOST` | `SET key token NX PX ttl` returned nil for this seat because a live key exists |
| `HOLD_ROLLBACK_RELEASE` | This seat was won, a sibling seat in the same all-or-nothing request was lost, and the compare-and-delete release is run against this seat |
| `HOLD_TTL_EXPIRE` | The Redis key for this seat reached its TTL and is gone |
| `CONFIRM_START` | A confirm request inserted its idempotency record and its Redis re-validation found every seat's key present with this hold's token |
| `CONFIRM_TOKEN_MISMATCH` | A confirm request presented a hold token that does not match the live key on this seat |
| `CONFIRM_HOLD_GONE` | A confirm request found no key at all for this seat during re-validation |
| `CONFIRM_REDIS_DOWN` | A confirm request could not reach Redis |
| `CONFIRM_PAYMENT_FAILED_HOLD_LIVE` | The simulated provider returned failed and this seat's lock is still live |
| `CONFIRM_PAYMENT_FAILED_HOLD_GONE` | The simulated provider returned failed and this seat's lock expired during the capture |
| `CONFIRM_UNIQUE_VIOLATION` | The unique constraint on `(showtime_id, seat_id)` fired at insert |
| `CONFIRM_COMMIT` | The confirm transaction committed |
| `INSTANCE_KILLED_PRECOMMIT` | The API container died before the confirm transaction committed, with no graceful shutdown |
| `INSTANCE_KILLED_POSTCOMMIT` | The API container died after commit and before the post-commit lock release, with no graceful shutdown |
| `SIGTERM_DRAIN` | The API container received SIGTERM, drained in-flight requests, and ran the release over its hold registry |
| `TAB_CLOSED` | The customer's browser tab or window was closed |
| `TAB_REFRESHED` | The page was reloaded and `sessionStorage` was read back |
| `SIGN_OUT` | The customer signed out of this session, from any surface in the product |
| `POLL_TICK` | The three-second seat-map poll returned |
| `SALES_CUTOFF_PASSES` | The injected clock passed the showtime's sales cut-off |
| `OTHER_ACQUIRES` | Another customer acquired the lock on this seat |
| `OTHER_BOOKS` | Another customer's confirm committed a `booking_seat` row for this seat |

#### The transition table

`A` = `available` · `M` = `held_by_me` · `P` = `held_by_me_paying` · `O` = `held_by_other` ·
`S` = `sold`. A cell shows the resulting state.

| Input | from A | from M | from P | from O | from S |
|---|---|---|---|---|---|
| `SELECT` | A | M | P | O | S |
| `DESELECT` | A | A | P | O | S |
| `HOLD_REQUEST_GUEST` | A | M | P | O | S |
| `HOLD_REQUEST_OVER_CAP` | A | M | P | O | S |
| `HOLD_REQUEST_DUPLICATE_SEAT` | A | M | P | O | S |
| `HOLD_REQUEST_SALES_CLOSED` | A | M | P | O | S |
| `HOLD_REQUEST_REDIS_DOWN` | A | M | P | O | S |
| `HOLD_ACQUIRE_OK` | **M** | M | P | O | S |
| `HOLD_ACQUIRE_LOST` | O | M | P | O | S |
| `HOLD_ROLLBACK_RELEASE` | A | **A** | P | O | S |
| `HOLD_TTL_EXPIRE` | A | **A** | P | **A** | S |
| `CONFIRM_START` | A | **P** | P | O | S |
| `CONFIRM_TOKEN_MISMATCH` | A | M | P | O | S |
| `CONFIRM_HOLD_GONE` | A | **A** | P | O | S |
| `CONFIRM_REDIS_DOWN` | A | M | P | O | S |
| `CONFIRM_PAYMENT_FAILED_HOLD_LIVE` | A | M | **M** | O | S |
| `CONFIRM_PAYMENT_FAILED_HOLD_GONE` | A | M | **A** | O | S |
| `CONFIRM_UNIQUE_VIOLATION` | A | M | **S** | O | S |
| `CONFIRM_COMMIT` | A | M | **S** | O | S |
| `INSTANCE_KILLED_PRECOMMIT` | A | M | **M** | O | S |
| `INSTANCE_KILLED_POSTCOMMIT` | A | M | **S** | O | S |
| `SIGTERM_DRAIN` | A | **A** | P | O | S |
| `TAB_CLOSED` | A | M | P | O | S |
| `TAB_REFRESHED` | A | M | P | O | S |
| `SIGN_OUT` | A | **A** | P | O | S |
| `POLL_TICK` | A | M | P | O | S |
| `SALES_CUTOFF_PASSES` | A | M | P | O | S |
| `OTHER_ACQUIRES` | **O** | M | P | O | S |
| `OTHER_BOOKS` | A | M | P | **S** | S |

**Reachability.** `available` is initial. `held_by_me` is reached by `HOLD_ACQUIRE_OK` from
`available`. `held_by_me_paying` is reached by `CONFIRM_START` from `held_by_me`. `sold` is reached by
`CONFIRM_COMMIT` from `held_by_me_paying`. `held_by_other` is reached by `OTHER_ACQUIRES` from
`available`. Every state except the initial one is reachable, and the machine has 5 × 29 = **145**
transitions, one for every pair.

**Totality re-proved after adding `SIGN_OUT`, because adding an input is the change that breaks it.**
The input count went from 28 to 29 and the transition count from 140 to 145 — **five new cells, one
per state, none left blank.** No state was added and no state was removed, so the reachability
argument above is unchanged: `SIGN_OUT`'s only non-self edge is `held_by_me` → `available`, and that
edge already existed under `DESELECT`, `HOLD_ROLLBACK_RELEASE`, `HOLD_TTL_EXPIRE`, `CONFIRM_HOLD_GONE`
and `SIGTERM_DRAIN`, so it creates no new path and removes none. **Every one of the five cells is
specified rather than defaulted**, including the three where there is nothing to release —
`available`, `held_by_other` and `sold` — because "there is no hold here" is a different fact from
"this input was not considered", and a machine declared normative cannot tell a reader which one a
blank cell meant.

#### The machine-readable block

```transition
{
  "initial": "available",
  "states": ["available", "held_by_me", "held_by_me_paying", "held_by_other", "sold"],
  "inputs": ["SELECT", "DESELECT", "HOLD_REQUEST_GUEST", "HOLD_REQUEST_OVER_CAP", "HOLD_REQUEST_DUPLICATE_SEAT", "HOLD_REQUEST_SALES_CLOSED", "HOLD_REQUEST_REDIS_DOWN", "HOLD_ACQUIRE_OK", "HOLD_ACQUIRE_LOST", "HOLD_ROLLBACK_RELEASE", "HOLD_TTL_EXPIRE", "CONFIRM_START", "CONFIRM_TOKEN_MISMATCH", "CONFIRM_HOLD_GONE", "CONFIRM_REDIS_DOWN", "CONFIRM_PAYMENT_FAILED_HOLD_LIVE", "CONFIRM_PAYMENT_FAILED_HOLD_GONE", "CONFIRM_UNIQUE_VIOLATION", "CONFIRM_COMMIT", "INSTANCE_KILLED_PRECOMMIT", "INSTANCE_KILLED_POSTCOMMIT", "SIGTERM_DRAIN", "TAB_CLOSED", "TAB_REFRESHED", "SIGN_OUT", "POLL_TICK", "SALES_CUTOFF_PASSES", "OTHER_ACQUIRES", "OTHER_BOOKS"],
  "transitions": [
    {"from": "available", "input": "SELECT", "to": "available",
     "guard": "client-side selection only; no request is sent and no server state changes. The cell is drawn with the held_by_me treatment per P-SEA-02",
     "user_sees": "3 seats chosen"},
    {"from": "available", "input": "DESELECT", "to": "available",
     "guard": "client-side only; the seat leaves the local selection and the running total drops by that seat's price_paise",
     "user_sees": "2 seats chosen"},
    {"from": "available", "input": "HOLD_REQUEST_GUEST", "to": "available",
     "guard": "server: refused by the router authorisation dependency before any lock is touched. 401 AUTH_REQUIRED. The interface never sends this because its primary action reads Sign in to hold these seats",
     "user_sees": "Sign in to hold seats. Your selection has been kept."},
    {"from": "available", "input": "HOLD_REQUEST_OVER_CAP", "to": "available",
     "guard": "server: the cap is checked against this customer's live holds on this showtime plus the seats in this request, before any lock is touched. 422 SEAT_LIMIT_EXCEEDED",
     "user_sees": "You can hold up to 10 seats for one showtime. You are holding 6 and chose 5 more."},
    {"from": "available", "input": "HOLD_REQUEST_DUPLICATE_SEAT", "to": "available",
     "guard": "server: request-body validation rejects the whole request before any lock is touched. 422 VALIDATION_FAILED",
     "user_sees": "Seat C12 was listed twice. Each seat can only be chosen once. No seats were held."},
    {"from": "available", "input": "HOLD_REQUEST_SALES_CLOSED", "to": "available",
     "guard": "server: now >= starts_at + SALES_CUTOFF_MINUTES, evaluated in Asia/Kolkata against the injected clock. 409 SALES_CLOSED. PROVISIONAL direction, FR-ADR-042",
     "user_sees": "Sales for this showtime closed at 7:45 pm. Choose another showtime."},
    {"from": "available", "input": "HOLD_REQUEST_REDIS_DOWN", "to": "available",
     "guard": "server: the hold path fails loudly and never falls back to the database for locks. 503 DEPENDENCY_UNAVAILABLE",
     "user_sees": "Seat holds are unavailable right now. You can still look at showtimes and seat maps. Try again in a few minutes."},
    {"from": "available", "input": "HOLD_ACQUIRE_OK", "to": "held_by_me",
     "guard": "server: SET key token NX PX ttl in one command returned OK, and the sold-seat check found no booking_seat row for this pair. expires_at is fixed here and never moves",
     "user_sees": "3 seats held by you"},
    {"from": "available", "input": "HOLD_ACQUIRE_LOST", "to": "held_by_other",
     "guard": "server: SET NX returned nil, so a live key exists that is not this hold's. The whole request is rolled back and no seat is held",
     "user_sees": "C12 was taken by another customer. No seats were held. Choose a different seat and press Hold these seats again."},
    {"from": "available", "input": "HOLD_ROLLBACK_RELEASE", "to": "available",
     "guard": "impossible: only a seat this request won can be rolled back, and a won seat is in held_by_me. The compare-and-delete script is a no-op against a key this hold does not own",
     "user_sees": "(nothing - no message is shown)"},
    {"from": "available", "input": "HOLD_TTL_EXPIRE", "to": "available",
     "guard": "ignored: no key exists for this seat, so there is nothing to expire",
     "user_sees": "(nothing - no message is shown)"},
    {"from": "available", "input": "CONFIRM_START", "to": "available",
     "guard": "impossible: CONFIRM_START is defined as re-validation succeeding, which requires a live key carrying this hold's token. With no key the confirm takes CONFIRM_HOLD_GONE instead",
     "user_sees": "(nothing - no message is shown)"},
    {"from": "available", "input": "CONFIRM_TOKEN_MISMATCH", "to": "available",
     "guard": "impossible: a mismatch requires a live key to compare against, which would put the seat in held_by_other",
     "user_sees": "(nothing - no message is shown)"},
    {"from": "available", "input": "CONFIRM_HOLD_GONE", "to": "available",
     "guard": "server: re-validation found no key, so the transaction rolls back before the showtime row is locked and before any payment is attempted. 409 HOLD_EXPIRED",
     "user_sees": "The hold on your seats has ended and they have been released. You have not been charged. Choose them again if they are still free."},
    {"from": "available", "input": "CONFIRM_REDIS_DOWN", "to": "available",
     "guard": "server: the confirm cannot re-validate the hold, so it refuses rather than relying on the database constraint alone. 503 DEPENDENCY_UNAVAILABLE",
     "user_sees": "We cannot complete your booking right now. You have not been charged. Try again in a few minutes. If you need help, quote a1b2c3d4."},
    {"from": "available", "input": "CONFIRM_PAYMENT_FAILED_HOLD_LIVE", "to": "available",
     "guard": "impossible: payment is attempted at step 6 of the confirm transaction, which is only reached after re-validation succeeded, which requires a live key",
     "user_sees": "(nothing - no message is shown)"},
    {"from": "available", "input": "CONFIRM_PAYMENT_FAILED_HOLD_GONE", "to": "available",
     "guard": "impossible: same reason. A confirm that reaches payment started from held_by_me_paying",
     "user_sees": "(nothing - no message is shown)"},
    {"from": "available", "input": "CONFIRM_UNIQUE_VIOLATION", "to": "available",
     "guard": "impossible: the insert at step 7 is only reached after re-validation succeeded, which requires a live key",
     "user_sees": "(nothing - no message is shown)"},
    {"from": "available", "input": "CONFIRM_COMMIT", "to": "available",
     "guard": "impossible: a commit is only reached after re-validation succeeded, which requires a live key",
     "user_sees": "(nothing - no message is shown)"},
    {"from": "available", "input": "INSTANCE_KILLED_PRECOMMIT", "to": "available",
     "guard": "ignored: no transaction is open against this seat and no key exists for it. Containers are stateless, so nothing about this seat lived in the process",
     "user_sees": "(nothing - no message is shown)"},
    {"from": "available", "input": "INSTANCE_KILLED_POSTCOMMIT", "to": "available",
     "guard": "impossible: a post-commit death implies a committed booking_seat row, which would put the seat in sold",
     "user_sees": "(nothing - no message is shown)"},
    {"from": "available", "input": "SIGTERM_DRAIN", "to": "available",
     "guard": "ignored: the draining instance reads instance:{id}:holds and finds no key for this seat, so the compare-and-delete release does nothing",
     "user_sees": "(nothing - no message is shown)"},
    {"from": "available", "input": "TAB_CLOSED", "to": "available",
     "guard": "ignored on the server: nothing was held. sessionStorage is discarded with the tab, so the local selection is gone",
     "user_sees": "(nothing - no message is shown)"},
    {"from": "available", "input": "TAB_REFRESHED", "to": "available",
     "guard": "the local selection is read back from sessionStorage and re-checked against the freshly fetched map; a seat still available stays chosen",
     "user_sees": "3 seats chosen"},
    {"from": "available", "input": "SIGN_OUT", "to": "available",
     "guard": "ignored: this session holds nothing on this seat, so there is nothing to release. Sign-out still clears every fr.* value in sessionStorage - the hold token, the Idempotency-Key, the pending selection and fr.last_booking_reference (P-ACC-13, SCR-PAY-01) - so the local selection is discarded and the map repaints with nothing chosen",
     "user_sees": "(nothing about this seat - the sign-out confirmation is P-ACC-13's and names no seat)"},
    {"from": "available", "input": "POLL_TICK", "to": "available",
     "guard": "observation only: the poll reports this seat as available. A poll never changes the machine's state; another customer acquiring or booking the seat arrives as OTHER_ACQUIRES or OTHER_BOOKS",
     "user_sees": "(nothing - no message is shown)"},
    {"from": "available", "input": "SALES_CUTOFF_PASSES", "to": "available",
     "guard": "the cut-off is a property of the showtime, not of a seat. The seat does not change state; every seat becomes unselectable and the banner appears",
     "user_sees": "Sales for this showtime have closed."},
    {"from": "available", "input": "OTHER_ACQUIRES", "to": "held_by_other",
     "guard": "another customer's SET NX succeeded on this seat. This session learns at the next poll, at most about 13 seconds later",
     "user_sees": "(nothing - no message is shown; the cell repaints to held_by_other with its changed-seat outline)"},
    {"from": "available", "input": "OTHER_BOOKS", "to": "available",
     "guard": "impossible: another customer's confirm requires them to hold a live lock on this seat, which would put the seat in held_by_other",
     "user_sees": "(nothing - no message is shown)"},

    {"from": "held_by_me", "input": "SELECT", "to": "held_by_me",
     "guard": "server: a re-sent hold request naming a seat this customer already holds is a no-op that succeeds and does not extend the TTL. A tap on a held cell is DESELECT, not SELECT",
     "user_sees": "(nothing - no message is shown; the countdown does not restart)"},
    {"from": "held_by_me", "input": "DESELECT", "to": "available",
     "guard": "server: the compare-and-delete Lua script deletes this seat's key only if it carries this hold's token. The rest of the hold survives with the same expires_at; if this was the last seat the hold ends",
     "user_sees": "2 seats held by you"},
    {"from": "held_by_me", "input": "HOLD_REQUEST_GUEST", "to": "held_by_me",
     "guard": "impossible: a guest cannot hold, so no seat is in held_by_me for a guest session",
     "user_sees": "(nothing - no message is shown)"},
    {"from": "held_by_me", "input": "HOLD_REQUEST_OVER_CAP", "to": "held_by_me",
     "guard": "server: a further hold request is refused before any lock is touched. This seat's key and its expires_at are untouched. 422 SEAT_LIMIT_EXCEEDED",
     "user_sees": "You can hold up to 10 seats for one showtime. You are holding 6 and chose 5 more."},
    {"from": "held_by_me", "input": "HOLD_REQUEST_DUPLICATE_SEAT", "to": "held_by_me",
     "guard": "server: the new request is rejected wholesale in validation. The existing hold is untouched. 422 VALIDATION_FAILED",
     "user_sees": "Seat C12 was listed twice. Each seat can only be chosen once. No seats were held."},
    {"from": "held_by_me", "input": "HOLD_REQUEST_SALES_CLOSED", "to": "held_by_me",
     "guard": "server: a new hold past the cut-off is refused, but this existing hold is honoured and may still be confirmed. The cut-off is checked at the hold and never at confirm. 409 SALES_CLOSED",
     "user_sees": "Sales for this showtime have closed. You can still pay for the seats you are holding."},
    {"from": "held_by_me", "input": "HOLD_REQUEST_REDIS_DOWN", "to": "held_by_me",
     "guard": "server: the new request fails 503. This key is unaffected but will expire on its own, and a confirm will also fail while Redis is unreachable, so this hold is effectively lost",
     "user_sees": "Seat holds are unavailable right now. You can still look at showtimes and seat maps. Try again in a few minutes."},
    {"from": "held_by_me", "input": "HOLD_ACQUIRE_OK", "to": "held_by_me",
     "guard": "impossible: SET NX cannot succeed against a live key. A nil reply against a key this hold owns is the no-op of FR-ADR-026",
     "user_sees": "(nothing - no message is shown)"},
    {"from": "held_by_me", "input": "HOLD_ACQUIRE_LOST", "to": "held_by_me",
     "guard": "ignored: a nil reply for a seat this customer already holds is not a loss. It is the no-op re-selection case and the TTL is not extended",
     "user_sees": "(nothing - no message is shown)"},
    {"from": "held_by_me", "input": "HOLD_ROLLBACK_RELEASE", "to": "available",
     "guard": "server: this seat was won in a multi-seat request whose sibling was lost, so it is released with the compare-and-delete script. The release is best-effort; if it fails the key expires within the TTL",
     "user_sees": "C12 and C13 were taken by another customer. No seats were held. Your other choices are still selected - change these two and press Hold these seats again."},
    {"from": "held_by_me", "input": "HOLD_TTL_EXPIRE", "to": "available",
     "guard": "Redis deleted the key at its TTL. No cleanup job exists and none is needed. This session learns at its countdown reaching zero or at the next poll, whichever is first",
     "user_sees": "Your hold has ended and your seats have been released. You have not been charged."},
    {"from": "held_by_me", "input": "CONFIRM_START", "to": "held_by_me_paying",
     "guard": "server: the idempotency record was inserted first, then re-validation found this key present with this hold's token, then the showtime row was locked FOR UPDATE. The cut-off is not re-checked here",
     "user_sees": "(nothing - the pay action shows a busy state and is disabled; the countdown keeps running)"},
    {"from": "held_by_me", "input": "CONFIRM_TOKEN_MISMATCH", "to": "held_by_me",
     "guard": "impossible: in this state the live key carries this session's token by definition",
     "user_sees": "(nothing - no message is shown)"},
    {"from": "held_by_me", "input": "CONFIRM_HOLD_GONE", "to": "available",
     "guard": "server: the key elapsed between the last poll and re-validation. The transaction rolls back before the showtime row is locked and before any payment. 409 HOLD_EXPIRED",
     "user_sees": "The hold on your seats has ended and they have been released. You have not been charged. Choose them again if they are still free."},
    {"from": "held_by_me", "input": "CONFIRM_REDIS_DOWN", "to": "held_by_me",
     "guard": "server: the confirm refuses with 503 before payment. This key is untouched and keeps its original expires_at; the customer may retry while time remains and Redis returns",
     "user_sees": "We cannot complete your booking right now. You have not been charged. Try again in a few minutes. If you need help, quote a1b2c3d4."},
    {"from": "held_by_me", "input": "CONFIRM_PAYMENT_FAILED_HOLD_LIVE", "to": "held_by_me",
     "guard": "impossible from this state: payment is only attempted after CONFIRM_START has moved the seat to held_by_me_paying",
     "user_sees": "(nothing - no message is shown)"},
    {"from": "held_by_me", "input": "CONFIRM_PAYMENT_FAILED_HOLD_GONE", "to": "held_by_me",
     "guard": "impossible from this state: same reason",
     "user_sees": "(nothing - no message is shown)"},
    {"from": "held_by_me", "input": "CONFIRM_UNIQUE_VIOLATION", "to": "held_by_me",
     "guard": "impossible from this state: the insert at step 7 is only reached from held_by_me_paying",
     "user_sees": "(nothing - no message is shown)"},
    {"from": "held_by_me", "input": "CONFIRM_COMMIT", "to": "held_by_me",
     "guard": "impossible from this state: a commit is only reached from held_by_me_paying",
     "user_sees": "(nothing - no message is shown)"},
    {"from": "held_by_me", "input": "INSTANCE_KILLED_PRECOMMIT", "to": "held_by_me",
     "guard": "the hold lives in Redis, not in the process, so it survives the death of the instance that granted it. Any other instance can serve a confirm against it",
     "user_sees": "(nothing - no message is shown; the countdown continues from the same expires_at)"},
    {"from": "held_by_me", "input": "INSTANCE_KILLED_POSTCOMMIT", "to": "held_by_me",
     "guard": "impossible: a post-commit death implies a committed booking_seat row, which would put the seat in sold",
     "user_sees": "(nothing - no message is shown)"},
    {"from": "held_by_me", "input": "SIGTERM_DRAIN", "to": "available",
     "guard": "server: the draining instance reads instance:{id}:holds and runs the compare-and-delete release for each key. Holds that never became bookings are dropped deliberately, to shorten an outage window that expiry would otherwise close in three minutes",
     "user_sees": "The hold on your seats has ended and they have been released. You have not been charged. Choose them again if they are still free."},
    {"from": "held_by_me", "input": "TAB_CLOSED", "to": "held_by_me",
     "guard": "closing the tab releases nothing. There is no unload-time release, because an unload handler is unreliable and a fire-and-forget release from a closing page can arrive after the key has expired and been re-acquired. The TTL is what releases it",
     "user_sees": "(nothing - the customer has left)"},
    {"from": "held_by_me", "input": "TAB_REFRESHED", "to": "held_by_me",
     "guard": "the hold token is read back from sessionStorage and the hold is re-read from the server. The same expires_at drives the countdown, so the refresh costs no time and orphans nothing",
     "user_sees": "3 seats held by you"},
    {"from": "held_by_me", "input": "SIGN_OUT", "to": "available",
     "guard": "server: signing out releases this session's live hold. Every key in it is released with the compare-and-delete script, the hold record is deleted, its token is removed from holds:user:{user_id}:showtime:{showtime_id} and DEL cache:seatmap:{showtime_id} runs - the same five acts P-HLD-08 step 8 performs, for the same reason. The customer has said they are done, and leaving seats held by nobody for up to the remainder of 180 seconds is scarcity consumed by an absent customer",
     "user_sees": "Your hold has ended and your seats have been released. You have not been charged."},
    {"from": "held_by_me", "input": "POLL_TICK", "to": "held_by_me",
     "guard": "observation only: the server reports this seat as held; the client overlays held_by_me from its token, because the shared cached map carries objective state only",
     "user_sees": "(nothing - no message is shown)"},
    {"from": "held_by_me", "input": "SALES_CUTOFF_PASSES", "to": "held_by_me",
     "guard": "the cut-off is checked at hold acquisition and never at confirm, so an existing holder may finish. The effective last moment a booking can complete is the cut-off plus the hold, which is starts_at + 15 minutes + 3 minutes",
     "user_sees": "Sales for this showtime have closed. You can still pay for the seats you are holding."},
    {"from": "held_by_me", "input": "OTHER_ACQUIRES", "to": "held_by_me",
     "guard": "impossible: another customer's SET NX cannot succeed against this live key",
     "user_sees": "(nothing - no message is shown)"},
    {"from": "held_by_me", "input": "OTHER_BOOKS", "to": "held_by_me",
     "guard": "impossible: another customer's confirm re-validates their own token against this key and fails with HOLD_NOT_OWNED before reaching the insert. If Redis had lost the key they would be refused by the unique constraint instead",
     "user_sees": "(nothing - no message is shown)"},

    {"from": "held_by_me_paying", "input": "SELECT", "to": "held_by_me_paying",
     "guard": "impossible from the checkout route, which is where a confirm is started: SCR-PAY-01 is a separate route at /showtimes/{id}/checkout, NOT a sheet over the map, so the seat map is unmounted and no cell exists to tap. Reachable only from another tab still showing the map, where it is the no-op re-selection of FR-ADR-026 and changes nothing about the confirm in flight",
     "user_sees": "(nothing - no message is shown)"},
    {"from": "held_by_me_paying", "input": "DESELECT", "to": "held_by_me_paying",
     "guard": "server: the release is accepted. There is no in-flight flag and no lock, because either needs durable state about a confirm and FR-ADR-025 keeps hold state out of PostgreSQL. The compare-and-delete deletes this seat's key, exactly as an expiry would, and the confirm continues: it passed its Redis re-validation at FR-ADR-029 step 2 and does not read Redis again before commit, so this is mechanically identical to HOLD_TTL_EXPIRE from this state and the outcome is settled by the database guard. The ordering is what decides what the customer is told, and both orderings are safe: a release landing BEFORE re-validation leaves no key, so the confirm fails 409 HOLD_EXPIRED and nothing is charged; a release landing AFTER the seats are booked finds a token that no longer matches and the compare-and-delete is a harmless no-op",
     "user_sees": "(nothing from the release - the confirm's own answer is what the customer is shown, and it is true in either ordering)"},
    {"from": "held_by_me_paying", "input": "HOLD_REQUEST_GUEST", "to": "held_by_me_paying",
     "guard": "impossible: a confirm requires an authenticated owner, so no guest session reaches this state",
     "user_sees": "(nothing - no message is shown)"},
    {"from": "held_by_me_paying", "input": "HOLD_REQUEST_OVER_CAP", "to": "held_by_me_paying",
     "guard": "server: a separate hold request is refused before any lock is touched. This seat and its confirm are unaffected. 422 SEAT_LIMIT_EXCEEDED",
     "user_sees": "You can hold up to 10 seats for one showtime. You are holding 6 and chose 5 more."},
    {"from": "held_by_me_paying", "input": "HOLD_REQUEST_DUPLICATE_SEAT", "to": "held_by_me_paying",
     "guard": "server: the new request is rejected in validation. This seat and its confirm are unaffected. 422 VALIDATION_FAILED",
     "user_sees": "Seat C12 was listed twice. Each seat can only be chosen once. No seats were held."},
    {"from": "held_by_me_paying", "input": "HOLD_REQUEST_SALES_CLOSED", "to": "held_by_me_paying",
     "guard": "server: a new hold past the cut-off is refused. The confirm in flight is not re-checked against the cut-off. 409 SALES_CLOSED",
     "user_sees": "Sales for this showtime have closed. You can still pay for the seats you are holding."},
    {"from": "held_by_me_paying", "input": "HOLD_REQUEST_REDIS_DOWN", "to": "held_by_me_paying",
     "guard": "server: the new request fails 503. This confirm is already past its Redis re-validation and touches Redis again only for the post-commit release, so it can still commit",
     "user_sees": "Seat holds are unavailable right now. You can still look at showtimes and seat maps. Try again in a few minutes."},
    {"from": "held_by_me_paying", "input": "HOLD_ACQUIRE_OK", "to": "held_by_me_paying",
     "guard": "impossible: SET NX cannot succeed against a live key",
     "user_sees": "(nothing - no message is shown)"},
    {"from": "held_by_me_paying", "input": "HOLD_ACQUIRE_LOST", "to": "held_by_me_paying",
     "guard": "ignored: a nil reply against a key this hold owns is the no-op case, not a loss",
     "user_sees": "(nothing - no message is shown)"},
    {"from": "held_by_me_paying", "input": "HOLD_ROLLBACK_RELEASE", "to": "held_by_me_paying",
     "guard": "impossible: rollback belongs to the acquisition request, which completed before any confirm for this hold could start",
     "user_sees": "(nothing - no message is shown)"},
    {"from": "held_by_me_paying", "input": "HOLD_TTL_EXPIRE", "to": "held_by_me_paying",
     "guard": "the key is gone but the confirm already re-validated it, so the transaction continues. The outcome is settled by the database guard, not by Redis. Another customer may acquire the key in this window and will lose at the unique constraint. This is why the database guard may not be waived",
     "user_sees": "Your hold has ended. We are waiting for the answer to your payment. Do not close this page."},
    {"from": "held_by_me_paying", "input": "CONFIRM_START", "to": "held_by_me_paying",
     "guard": "server: a second confirm carrying the same Idempotency-Key while the first is still running is refused and no second booking is created. 409 IDEMPOTENCY_IN_FLIGHT. The wording is P-PAY-09's and is reproduced verbatim, not authored here",
     "user_sees": "This booking is still being processed."},
    {"from": "held_by_me_paying", "input": "CONFIRM_TOKEN_MISMATCH", "to": "held_by_me_paying",
     "guard": "impossible: re-validation already passed for this hold, and it is the only place the token is compared",
     "user_sees": "(nothing - no message is shown)"},
    {"from": "held_by_me_paying", "input": "CONFIRM_HOLD_GONE", "to": "held_by_me_paying",
     "guard": "impossible: re-validation already passed. A key elapsing after that point is HOLD_TTL_EXPIRE, not CONFIRM_HOLD_GONE",
     "user_sees": "(nothing - no message is shown)"},
    {"from": "held_by_me_paying", "input": "CONFIRM_REDIS_DOWN", "to": "held_by_me_paying",
     "guard": "Redis is not read again between re-validation and commit, so a Redis loss here does not stop the transaction. Only the post-commit release fails, and those keys expire on their own",
     "user_sees": "(nothing - no message is shown)"},
    {"from": "held_by_me_paying", "input": "CONFIRM_PAYMENT_FAILED_HOLD_LIVE", "to": "held_by_me",
     "guard": "server: the simulated provider returned failed at step 6. The transaction rolls back, no booking row exists, and the locks were never released because release is post-commit. The hold survives with its original expires_at. 402 PAYMENT_FAILED",
     "user_sees": "The payment did not go through and you have not been charged. Your seats are still held - the time left is shown above. You can try again."},
    {"from": "held_by_me_paying", "input": "CONFIRM_PAYMENT_FAILED_HOLD_GONE", "to": "available",
     "guard": "server: the provider returned failed and the key had already elapsed during the capture. The transaction rolls back and there is no hold left to retry against. 402 PAYMENT_FAILED. This is the only reachable form of payment failing after the hold expired: a failure cannot precede re-validation, because re-validation is step 2 and payment is step 6",
     "user_sees": "The payment did not go through and you have not been charged. The hold on your seats has also ended and they have been released. Choose them again if they are still free."},
    {"from": "held_by_me_paying", "input": "CONFIRM_UNIQUE_VIOLATION", "to": "sold",
     "guard": "server: the unique constraint on (showtime_id, seat_id) fired at step 7 because another booking already owns this seat. The violation is caught, translated, never retried and never logged as an exception. The transaction rolls back and nothing is charged. 409 SEAT_UNAVAILABLE",
     "user_sees": "C12 was taken by another customer before your payment finished. Your booking was not made and you have not been charged."},
    {"from": "held_by_me_paying", "input": "CONFIRM_COMMIT", "to": "sold",
     "guard": "server: the booking, its booking_seat rows and the completed idempotency record committed together. The Redis keys are released after the commit with the compare-and-delete script, never before and never inside the transaction",
     "user_sees": "FR-2K7M-9QXD"},
    {"from": "held_by_me_paying", "input": "INSTANCE_KILLED_PRECOMMIT", "to": "held_by_me",
     "guard": "the transaction rolls back, so there is no booking and no captured payment. The Redis keys live outside the process and survive with their original expires_at. A retry with the same Idempotency-Key finds no completed record and runs again",
     "user_sees": "We cannot complete your booking right now. You have not been charged. Try again in a few minutes. If you need help, quote a1b2c3d4."},
    {"from": "held_by_me_paying", "input": "INSTANCE_KILLED_POSTCOMMIT", "to": "sold",
     "guard": "the booking is committed and durable. The post-commit release never ran, so this seat keeps a residual lock until its TTL. That cannot oversell: the database refuses anyone else and the map shows sold, because sold wins over any lock per P-SEA-05. A retry with the same Idempotency-Key returns the original booking",
     "user_sees": "FR-2K7M-9QXD"},
    {"from": "held_by_me_paying", "input": "SIGTERM_DRAIN", "to": "held_by_me_paying",
     "guard": "the drain finishes in-flight requests before it releases locks, so a confirm in flight completes and only holds that never became bookings are released. This depends on the ECS stop timeout exceeding the deregistration delay plus the drain timeout, which is a Zone C configuration. If it does not, SIGKILL arrives first and the case becomes INSTANCE_KILLED_PRECOMMIT",
     "user_sees": "(nothing - no message is shown; the request completes normally)"},
    {"from": "held_by_me_paying", "input": "TAB_CLOSED", "to": "held_by_me_paying",
     "guard": "closing the tab abandons the response, not the request. The server completes the confirm and the booking may be made without the customer ever seeing the confirmation screen. The reference is in the customer's bookings list and on the emailed receipt independently of this screen",
     "user_sees": "(nothing - the customer has left)"},
    {"from": "held_by_me_paying", "input": "TAB_REFRESHED", "to": "held_by_me_paying",
     "guard": "the restored page does NOT re-send the confirm. SCR-PAY-01 owns the checkout screen's behaviour and states in terms that it never replays EP-PAY-01 to find out what happened: a replay spends a rate-limit token whether or not it creates anything, and it can answer three different ways, to settle a question the client can answer from fr.last_booking_reference with no request at all. A refresh therefore abandons the RESPONSE and not the REQUEST, mechanically the same as TAB_CLOSED from this state, and the confirm in flight runs to its own answer with this seat unaffected. The restored page reads the hold token back from sessionStorage, the keys are still live because release is post-commit, so it re-renders the ordinary checkout panel with its countdown; the in-flight state itself died with the page and is not restorable. If the customer then presses the pay action, that is CONFIRM_START from this state - a second confirm carrying the same Idempotency-Key - and it is refused 409 IDEMPOTENCY_IN_FLIGHT, which is the path that keeps that branch reachable from the product",
     "user_sees": "(nothing - the restored page renders the ordinary checkout panel and its countdown; the confirm in flight is invisible to it)"},
    {"from": "held_by_me_paying", "input": "SIGN_OUT", "to": "held_by_me_paying",
     "guard": "server: the release runs and the confirm is NOT cancelled - a request already sent cannot be un-sent, and there is no in-flight flag to consult (FR-ADR-025). This is mechanically identical to DESELECT from this state: the confirm passed its Redis re-validation at FR-ADR-029 step 2 and does not read Redis again before commit, so the outcome is settled by the database guard and both orderings are safe. A release landing BEFORE re-validation leaves no key and the confirm fails 409 HOLD_EXPIRED with nothing charged; a release landing AFTER the seats are booked finds a token that no longer matches and deletes nothing. The booking, if it commits, belongs to the account that was signed in when the request was sent",
     "user_sees": "(nothing from the release - the customer has left the session and the confirm's own answer is written to their bookings list and their emailed receipt)"},
    {"from": "held_by_me_paying", "input": "POLL_TICK", "to": "held_by_me_paying",
     "guard": "no poll runs from the checkout route: SCR-PAY-01 is a separate route, the seat map is unmounted and its 3-second poll is stopped, so nothing is counted against the seat-map rate limiter while a customer pays. Reachable only from another tab still showing the map, and there it is observation only - the poll reports this seat as held and that client overlays held_by_me",
     "user_sees": "(nothing - no message is shown)"},
    {"from": "held_by_me_paying", "input": "SALES_CUTOFF_PASSES", "to": "held_by_me_paying",
     "guard": "the confirm path does not check the cut-off and cannot reject a customer who is already paying. The payment completes",
     "user_sees": "(nothing - no message is shown)"},
    {"from": "held_by_me_paying", "input": "OTHER_ACQUIRES", "to": "held_by_me_paying",
     "guard": "impossible while the key is live. If the key has already elapsed the machine has taken HOLD_TTL_EXPIRE first, and the other customer then loses at the unique constraint",
     "user_sees": "(nothing - no message is shown)"},
    {"from": "held_by_me_paying", "input": "OTHER_BOOKS", "to": "held_by_me_paying",
     "guard": "impossible while the key is live. After HOLD_TTL_EXPIRE it is reachable, and it is what turns this session's own insert into CONFIRM_UNIQUE_VIOLATION",
     "user_sees": "(nothing - no message is shown)"},

    {"from": "held_by_other", "input": "SELECT", "to": "held_by_other",
     "guard": "ignored: the cell does not respond to a tap",
     "user_sees": "(nothing - the accessible name already ends: held by another customer)"},
    {"from": "held_by_other", "input": "DESELECT", "to": "held_by_other",
     "guard": "ignored: the cell does not respond to a tap and this session owns nothing to give back",
     "user_sees": "(nothing - no message is shown)"},
    {"from": "held_by_other", "input": "HOLD_REQUEST_GUEST", "to": "held_by_other",
     "guard": "server: refused by the router authorisation dependency before any lock is touched. 401 AUTH_REQUIRED",
     "user_sees": "Sign in to hold seats. Your selection has been kept."},
    {"from": "held_by_other", "input": "HOLD_REQUEST_OVER_CAP", "to": "held_by_other",
     "guard": "server: the cap is checked before any lock is touched, so this request never reaches the acquisition step. 422 SEAT_LIMIT_EXCEEDED",
     "user_sees": "You can hold up to 10 seats for one showtime. You are holding 6 and chose 5 more."},
    {"from": "held_by_other", "input": "HOLD_REQUEST_DUPLICATE_SEAT", "to": "held_by_other",
     "guard": "server: rejected in validation before any lock is touched. 422 VALIDATION_FAILED",
     "user_sees": "Seat C12 was listed twice. Each seat can only be chosen once. No seats were held."},
    {"from": "held_by_other", "input": "HOLD_REQUEST_SALES_CLOSED", "to": "held_by_other",
     "guard": "server: the cut-off is checked before any lock is touched. 409 SALES_CLOSED",
     "user_sees": "Sales for this showtime closed at 7:45 pm. Choose another showtime."},
    {"from": "held_by_other", "input": "HOLD_REQUEST_REDIS_DOWN", "to": "held_by_other",
     "guard": "server: the hold is refused with 503 regardless of what the map showed. With Redis unreachable the seat map itself answers 503 (X-7: the rate limiter reads Redis and fails closed before the cache is reached), so no degraded map is served. PostgreSQL has no knowledge of holds - what the map should render for this seat in that window is not decided anywhere and is raised as an Article X candidate in the lane notes",
     "user_sees": "Seat holds are unavailable right now. You can still look at showtimes and seat maps. Try again in a few minutes."},
    {"from": "held_by_other", "input": "HOLD_ACQUIRE_OK", "to": "held_by_other",
     "guard": "impossible: SET NX cannot succeed against a live key held by another customer",
     "user_sees": "(nothing - no message is shown)"},
    {"from": "held_by_other", "input": "HOLD_ACQUIRE_LOST", "to": "held_by_other",
     "guard": "server: SET NX returned nil. This is the seat taken between the map render and the hold request. The whole request is rolled back and this session holds nothing",
     "user_sees": "C12 was taken by another customer. No seats were held. Choose a different seat and press Hold these seats again."},
    {"from": "held_by_other", "input": "HOLD_ROLLBACK_RELEASE", "to": "held_by_other",
     "guard": "the compare-and-delete script is a no-op against a key this hold does not own. This is exactly why release compares the token instead of calling DEL: a two-call GET then DEL would free the other customer's seat while they were paying",
     "user_sees": "(nothing - no message is shown)"},
    {"from": "held_by_other", "input": "HOLD_TTL_EXPIRE", "to": "available",
     "guard": "the other customer's key reached its TTL and Redis deleted it. No cleanup job is involved. This session learns at the next poll",
     "user_sees": "(nothing - no message is shown; the cell repaints to available with its changed-seat outline)"},
    {"from": "held_by_other", "input": "CONFIRM_START", "to": "held_by_other",
     "guard": "impossible for this session: re-validation cannot succeed against a key it does not own",
     "user_sees": "(nothing - no message is shown)"},
    {"from": "held_by_other", "input": "CONFIRM_TOKEN_MISMATCH", "to": "held_by_other",
     "guard": "server: this session presented a hold token for a key that expired and was re-acquired by another customer. The token does not match, so the confirm is refused before payment and before the showtime row is locked. 403 HOLD_NOT_OWNED. The customer is shown the same words as HOLD_EXPIRED, because the fact is the same from their side and the server cannot tell them apart",
     "user_sees": "The hold on your seats has ended and they have been released. You have not been charged. Choose them again if they are still free."},
    {"from": "held_by_other", "input": "CONFIRM_HOLD_GONE", "to": "held_by_other",
     "guard": "impossible: a key is present here, it simply is not this session's. That is CONFIRM_TOKEN_MISMATCH",
     "user_sees": "(nothing - no message is shown)"},
    {"from": "held_by_other", "input": "CONFIRM_REDIS_DOWN", "to": "held_by_other",
     "guard": "server: the confirm refuses with 503 rather than relying on the database constraint alone, which would let someone confirm seats another customer is holding",
     "user_sees": "We cannot complete your booking right now. You have not been charged. Try again in a few minutes. If you need help, quote a1b2c3d4."},
    {"from": "held_by_other", "input": "CONFIRM_PAYMENT_FAILED_HOLD_LIVE", "to": "held_by_other",
     "guard": "impossible for this session: it never reached payment, because re-validation refuses a token it does not own",
     "user_sees": "(nothing - no message is shown)"},
    {"from": "held_by_other", "input": "CONFIRM_PAYMENT_FAILED_HOLD_GONE", "to": "held_by_other",
     "guard": "impossible for this session: same reason",
     "user_sees": "(nothing - no message is shown)"},
    {"from": "held_by_other", "input": "CONFIRM_UNIQUE_VIOLATION", "to": "held_by_other",
     "guard": "impossible for this session: the insert is only reached after re-validation succeeded",
     "user_sees": "(nothing - no message is shown)"},
    {"from": "held_by_other", "input": "CONFIRM_COMMIT", "to": "held_by_other",
     "guard": "impossible for this session: a commit is only reached from held_by_me_paying. The other customer's commit arrives here as OTHER_BOOKS",
     "user_sees": "(nothing - no message is shown)"},
    {"from": "held_by_other", "input": "INSTANCE_KILLED_PRECOMMIT", "to": "held_by_other",
     "guard": "the other customer's key lives in Redis and survives the instance. Their hold is unaffected and so is this session's view of it",
     "user_sees": "(nothing - no message is shown)"},
    {"from": "held_by_other", "input": "INSTANCE_KILLED_POSTCOMMIT", "to": "held_by_other",
     "guard": "impossible: a committed booking_seat row for this seat would put it in sold",
     "user_sees": "(nothing - no message is shown)"},
    {"from": "held_by_other", "input": "SIGTERM_DRAIN", "to": "held_by_other",
     "guard": "a draining instance releases only the holds in its own registry. If the other customer's hold was granted by that instance the key is released and the seat becomes available; that arrives at this session as HOLD_TTL_EXPIRE. If it was granted elsewhere nothing changes",
     "user_sees": "(nothing - no message is shown)"},
    {"from": "held_by_other", "input": "TAB_CLOSED", "to": "held_by_other",
     "guard": "ignored: this session holds nothing on this seat. The other customer closing their tab also releases nothing, because there is no unload-time release",
     "user_sees": "(nothing - no message is shown)"},
    {"from": "held_by_other", "input": "TAB_REFRESHED", "to": "held_by_other",
     "guard": "the restored selection is re-checked against the fresh map, and this seat is dropped from it because it is no longer available",
     "user_sees": "C12 is no longer available. It has been removed from your choices."},
    {"from": "held_by_other", "input": "SIGN_OUT", "to": "held_by_other",
     "guard": "ignored: this session owns no key on this seat, and the compare-and-delete releases only keys carrying this hold's token. Another customer signing out releases THEIR hold, which arrives at this session as HOLD_TTL_EXPIRE",
     "user_sees": "(nothing - no message is shown)"},
    {"from": "held_by_other", "input": "POLL_TICK", "to": "held_by_other",
     "guard": "observation only: the poll reports this seat as held by someone else",
     "user_sees": "(nothing - no message is shown)"},
    {"from": "held_by_other", "input": "SALES_CUTOFF_PASSES", "to": "held_by_other",
     "guard": "the cut-off is a property of the showtime. The seat does not change state and the other customer may still finish paying for it",
     "user_sees": "Sales for this showtime have closed."},
    {"from": "held_by_other", "input": "OTHER_ACQUIRES", "to": "held_by_other",
     "guard": "impossible: a second acquisition cannot succeed against a live key",
     "user_sees": "(nothing - no message is shown)"},
    {"from": "held_by_other", "input": "OTHER_BOOKS", "to": "sold",
     "guard": "the other customer's confirm committed. Their locks are released after that commit, but sold wins over any residual key per P-SEA-05",
     "user_sees": "(nothing - no message is shown; the cell repaints to sold with its changed-seat outline)"},

    {"from": "sold", "input": "SELECT", "to": "sold",
     "guard": "ignored: the cell does not respond to a tap",
     "user_sees": "(nothing - the accessible name already ends: sold)"},
    {"from": "sold", "input": "DESELECT", "to": "sold",
     "guard": "ignored: the cell does not respond to a tap. There is no customer cancellation and no refund in v1, so nothing gives a sold seat back",
     "user_sees": "(nothing - no message is shown)"},
    {"from": "sold", "input": "HOLD_REQUEST_GUEST", "to": "sold",
     "guard": "server: refused by the router authorisation dependency before any lock is touched. 401 AUTH_REQUIRED",
     "user_sees": "Sign in to hold seats. Your selection has been kept."},
    {"from": "sold", "input": "HOLD_REQUEST_OVER_CAP", "to": "sold",
     "guard": "server: the cap is checked before any lock is touched. 422 SEAT_LIMIT_EXCEEDED",
     "user_sees": "You can hold up to 10 seats for one showtime. You are holding 6 and chose 5 more."},
    {"from": "sold", "input": "HOLD_REQUEST_DUPLICATE_SEAT", "to": "sold",
     "guard": "server: rejected in validation before any lock is touched. 422 VALIDATION_FAILED",
     "user_sees": "Seat C12 was listed twice. Each seat can only be chosen once. No seats were held."},
    {"from": "sold", "input": "HOLD_REQUEST_SALES_CLOSED", "to": "sold",
     "guard": "server: the cut-off is checked before any lock is touched. 409 SALES_CLOSED",
     "user_sees": "Sales for this showtime closed at 7:45 pm. Choose another showtime."},
    {"from": "sold", "input": "HOLD_REQUEST_REDIS_DOWN", "to": "sold",
     "guard": "server: the hold is refused with 503. The seat map answers 503 while Redis is down (X-7), so no map is served at all; sold would be the one state PostgreSQL could report if one were on its own",
     "user_sees": "Seat holds are unavailable right now. You can still look at showtimes and seat maps. Try again in a few minutes."},
    {"from": "sold", "input": "HOLD_ACQUIRE_OK", "to": "sold",
     "guard": "server: SET NX can succeed on a sold seat, because a booking does not leave a key behind. The acquisition step is therefore followed by a check for a committed booking_seat row on this pair; finding one, the key just taken is released with the compare-and-delete script and the whole request is refused. Without this check a customer would hold a sold seat for three minutes and find out at payment",
     "user_sees": "C12 was taken by another customer. No seats were held. Choose a different seat and press Hold these seats again."},
    {"from": "sold", "input": "HOLD_ACQUIRE_LOST", "to": "sold",
     "guard": "server: a residual key from the buyer's own hold is still present, so SET NX returned nil. The request is refused with the same message as any other lost seat",
     "user_sees": "C12 was taken by another customer. No seats were held. Choose a different seat and press Hold these seats again."},
    {"from": "sold", "input": "HOLD_ROLLBACK_RELEASE", "to": "sold",
     "guard": "the compare-and-delete releases whatever key this request took on this seat and changes nothing about the booking. A sold seat cannot be un-sold by a Redis operation",
     "user_sees": "(nothing - no message is shown)"},
    {"from": "sold", "input": "HOLD_TTL_EXPIRE", "to": "sold",
     "guard": "a residual key from the buyer's own hold expires. The seat stays sold, because the booking_seat row is what makes it sold",
     "user_sees": "(nothing - no message is shown)"},
    {"from": "sold", "input": "CONFIRM_START", "to": "sold",
     "guard": "impossible for another session: re-validation would need a key carrying its own token, and a residual key carries the buyer's. For the buyer, a repeat confirm is answered from the idempotency record and never re-enters this state",
     "user_sees": "(nothing - no message is shown)"},
    {"from": "sold", "input": "CONFIRM_TOKEN_MISMATCH", "to": "sold",
     "guard": "server: a session presenting a token against the buyer's residual key is refused. 403 HOLD_NOT_OWNED",
     "user_sees": "The hold on your seats has ended and they have been released. You have not been charged. Choose them again if they are still free."},
    {"from": "sold", "input": "CONFIRM_HOLD_GONE", "to": "sold",
     "guard": "server: a session confirming against this seat after the residual key expired finds nothing. 409 HOLD_EXPIRED",
     "user_sees": "The hold on your seats has ended and they have been released. You have not been charged. Choose them again if they are still free."},
    {"from": "sold", "input": "CONFIRM_REDIS_DOWN", "to": "sold",
     "guard": "server: the confirm refuses with 503 before it can reach the insert",
     "user_sees": "We cannot complete your booking right now. You have not been charged. Try again in a few minutes. If you need help, quote a1b2c3d4."},
    {"from": "sold", "input": "CONFIRM_PAYMENT_FAILED_HOLD_LIVE", "to": "sold",
     "guard": "impossible: reaching payment on a sold seat requires re-validation to have passed for a session holding it, and the seat is already sold to someone else. Such a session would be refused at the insert instead, which is CONFIRM_UNIQUE_VIOLATION",
     "user_sees": "(nothing - no message is shown)"},
    {"from": "sold", "input": "CONFIRM_PAYMENT_FAILED_HOLD_GONE", "to": "sold",
     "guard": "impossible: same reason",
     "user_sees": "(nothing - no message is shown)"},
    {"from": "sold", "input": "CONFIRM_UNIQUE_VIOLATION", "to": "sold",
     "guard": "server: this is the guard working. Another session held a key on a seat this booking already owns - which happens when Redis lost the key or the map was stale - and the unique constraint refuses the second insert. It is not retried and not logged as an exception; its rate is a signal the operator watches. 409 SEAT_UNAVAILABLE",
     "user_sees": "C12 was taken by another customer before your payment finished. Your booking was not made and you have not been charged."},
    {"from": "sold", "input": "CONFIRM_COMMIT", "to": "sold",
     "guard": "impossible: a second commit for the same pair cannot exist. The unique constraint is total, with no partial WHERE clause, so it holds for every booking status",
     "user_sees": "(nothing - no message is shown)"},
    {"from": "sold", "input": "INSTANCE_KILLED_PRECOMMIT", "to": "sold",
     "guard": "the committed booking is durable and unaffected. Any transaction killed here was a losing one and rolls back",
     "user_sees": "(nothing - no message is shown)"},
    {"from": "sold", "input": "INSTANCE_KILLED_POSTCOMMIT", "to": "sold",
     "guard": "the booking is durable. The only loss is the post-commit release, which leaves a residual key that expires within the TTL and can cause no oversell",
     "user_sees": "(nothing - no message is shown)"},
    {"from": "sold", "input": "SIGTERM_DRAIN", "to": "sold",
     "guard": "the drain releases keys from its registry with the compare-and-delete script. A residual key belonging to this booking is released early, which is harmless, and bookings are never touched",
     "user_sees": "(nothing - no message is shown)"},
    {"from": "sold", "input": "TAB_CLOSED", "to": "sold",
     "guard": "ignored: the booking is committed and independent of any browser. The reference is in the customer's bookings list and on the emailed receipt",
     "user_sees": "(nothing - the customer has left)"},
    {"from": "sold", "input": "TAB_REFRESHED", "to": "sold",
     "guard": "the restored selection is re-checked against the fresh map and this seat is dropped from it. For the buyer, the restored checkout page finds fr.last_booking_reference in sessionStorage for this showtime and redirects to the confirmation screen for it WITH NO REQUEST - SCR-PAY-01 owns that rule and does not replay EP-PAY-01. Were the confirm re-sent, the same Idempotency-Key would return the original booking, so no second booking exists on either route; the route that runs is the one that spends no rate-limit token",
     "user_sees": "FR-2K7M-9QXD"},
    {"from": "sold", "input": "SIGN_OUT", "to": "sold",
     "guard": "ignored: the booking is committed and durable, and no session event can un-sell a booking_seat row (P-SEA-05). A residual key from the buyer's own hold is released if it is still present, which is harmless",
     "user_sees": "(nothing - no message is shown)"},
    {"from": "sold", "input": "POLL_TICK", "to": "sold",
     "guard": "observation only: the poll reports this seat as sold",
     "user_sees": "(nothing - no message is shown)"},
    {"from": "sold", "input": "SALES_CUTOFF_PASSES", "to": "sold",
     "guard": "the cut-off changes nothing about a seat that is already sold. The showtime remains visible with its full map rather than being hidden",
     "user_sees": "Sales for this showtime have closed."},
    {"from": "sold", "input": "OTHER_ACQUIRES", "to": "sold",
     "guard": "another customer can take a key on a sold seat if the key is absent, and the sold-seat check at acquisition releases it immediately. The seat does not change state",
     "user_sees": "(nothing - no message is shown)"},
    {"from": "sold", "input": "OTHER_BOOKS", "to": "sold",
     "guard": "impossible: the unique constraint on (showtime_id, seat_id) refuses the second booking_seat row. This is the assertion the concurrency proof settles in the database rather than in the HTTP response",
     "user_sees": "(nothing - no message is shown)"}
  ]
}
```

---

### `P-HLD-01` · Acquire a multi-seat hold all-or-nothing, in ascending seat-id order · `RULED`
`[SRC: SRC-002 §8.1.1 · SRC-002 §8.1.2 · SRC-002 §8.1.3 · SRC-002 §8.1.4 · SRC-002 §E E-1 · SRC-001 §5.2.6 · SRC-003 OPEN-SEAT-03 · FR-ADR-024 · FR-ADR-025 · FR-ADR-026]`
`[BRD: R-HOLD-01 · R-HOLD-04 · R-QLY-01]`

**Behaviour.** One hold request names a set of seats and succeeds or fails as a whole. It never
returns a partial success. Each seat's lock is one Redis key, `lock:seat:{showtime_id}:{seat_id}`,
acquired with **`SET key <token> NX PX <ttl_ms>` in a single command**. The TTL is never set as a
second call: a process that dies between `SETNX` and `EXPIRE` leaves a seat unbuyable forever, with no
error anywhere and no test that catches it.

**One token per hold, not one per seat.** The hold is the unit the customer owns, and one value is
carried through the confirm request instead of ten. The token is generated from a cryptographically
secure source.

**Locks are acquired in ascending `seat_id` order.** Two customers requesting overlapping sets
therefore contend in the same order, which turns a possible mutual stall into a clean loser.

**Release is a Lua script that compares the token and deletes atomically**, never `GET` then `DEL`.

```
if redis.call("GET", KEYS[1]) == ARGV[1] then return redis.call("DEL", KEYS[1]) else return 0 end
```

**The hold is not persisted in PostgreSQL.** Redis is the only record of a live hold. A hold table
would need its own expiry mechanism — the cleanup job `SRC-002 §8.1.4` explicitly removes — and it
would create a second source of truth about who holds a seat.

**Who may do it.** customer, manager, admin — every signed-in account. Only the guest is refused. Enforced once, on the router, as a dependency (`P-HLD-05`).

**Preconditions.**
- The showtime exists.
- Every named seat exists and is a member of **this showtime's seat set** — the set materialised when
  the showtime was created, which `P-ADM-14` owns. **Not the screen's current seats**: the two differ
  for any seat added to the hall after the showtime existed (`P-SEA-01`).
- The showtime's sales cut-off has not passed (`P-HLD-06`).
- The request names between 1 and 10 seats, each at most once.
- The customer's live holds on this showtime plus this request's seats total at most 10 (`P-HLD-04`).
- Redis is reachable (`P-HLD-10`).

**Happy path.**
1. Validate the body. Reject the whole request on any failure, before any key is written.
2. Check the cap against the customer's live holds on this showtime.
3. Check the sales cut-off against the injected clock in Asia/Kolkata.
4. **Resolve the token, which is a lookup before it is a generation.** Read this customer's live hold
   on this showtime, if one exists. **If it exists, this request uses that hold's existing token and
   its existing `expires_at`, both unchanged** — the new seats join that hold. **Only if none exists**
   is a token generated and `expires_at` computed once, as `now + SEAT_HOLD_TTL_SECONDS`. Either way
   exactly one token and one expiry instant govern every seat in this request, and a customer finishes
   with **exactly one live hold per showtime** — the rule the paragraph below, `EP-HLD-01`'s
   `idempotency` field and `P-HLD-04`'s cap all depend on.
5. Sort the seat ids ascending.
6. For each seat in that order, run `SET lock:seat:{showtime_id}:{seat_id} <token> NX PX <ttl_ms>`.
7. If every acquisition returned OK, read the committed `booking_seat` rows for those seats. If any
   exists, treat the seat as lost and go to the rollback path — a booking leaves no key behind, so a
   lock can be taken on a sold seat, and this check is what stops the customer discovering it at
   payment.
8. **Price the seats this request just acquired — those and no others** — with `FR-ADR-038`'s rule,
   and **append** them, with their prices, to the seat list stored under the hold token in Redis,
   with the hold's TTL (`P-HLD-11`). **Seats already in the hold are not repriced and their stored
   prices are not touched.**
9. **Index the hold against the customer**: add this hold's token to the Redis set
   `holds:user:{user_id}:showtime:{showtime_id}`, with the same TTL. **On an extend this entry is
   already present and the write is a no-op**, which is correct — one token per customer per
   showtime. `P-HLD-04` **reads** this set for the ten-seat cap and step 4 above reads it to find the
   existing hold; nothing else wrote it, and a hold missing from it is invisible to both.
10. Add every key to `instance:{instance_id}:holds`, with the same TTL (`P-HLD-12`).
11. **`DEL cache:seatmap:{showtime_id}`** — `P-BRW-12` owns seat-map invalidation and requires the
    delete after a hold as well as after a booking; `P-XCT-08` fixes it as a `DEL` and never a `SET`.
    It runs **after** the Redis writes above, matching the ordering `P-XCT-08` states for the booking
    path, so no reader can rebuild the entry from a state this request has not finished writing.
12. **Return the whole hold**: the token, `expires_at` in UTC, **every seat now under that token** —
    not only the seats this request added — each with its own stored `price_paise`, and a
    `total_paise` that is the sum of every one of them.

**Distinguishing the two nils, which is the step that is easy to miss.** `SET NX` returns nil for two
different situations: **somebody else holds the key**, and **this same customer already holds it** from
an earlier request. They are not the same event and must not produce the same outcome. On every nil the
server issues one `GET` on that key and compares the value to the token of this customer's live hold on
this showtime:

- **the value is this customer's existing hold token** — the seat is already theirs. This is the
  **no-op re-selection** case: it is **not** a loss, it does not roll the request back, and it does
  **not** extend the TTL (`FR-ADR-027` fixes `expires_at` at acquisition). The key is left exactly as
  it is and **is not added to this request's rollback set**, so a later failure in the same request can
  never release a hold the customer already owned.
- **the value is anything else** — the seat is genuinely lost, and the rollback path below runs.

**Which token owns an overlapping key, stated because two tokens must never both believe they own
one.** The existing hold's token keeps it. **This request does not mint a second token for a seat
already held**: if every seat named is already held by this customer the response returns the
**existing** token and its unchanged `expires_at`; if the request mixes already-held seats with new
ones, the new seats are acquired under **that same existing token**, so the customer finishes with one
hold, one token and one expiry rather than two overlapping holds on one showtime. A customer holding
seats on a showtime has **exactly one** live hold on it, and the ten-seat cap is counted against it.

**The expiry of an extended hold is the existing `expires_at`, unchanged.** The new keys are set
with a `PX` of the milliseconds remaining until it, **not** a fresh 180 seconds — `FR-ADR-027`
fixes the instant at acquisition and adding a seat must not walk the deadline forward. **Every
seat in one hold therefore expires at the same instant**, which is what makes one countdown
correct for all of them.

**Rollback path.** If any acquisition returns nil **for a key this customer does not already own**, or
step 7 finds a booking row, release every key this request won using the compare-and-delete script —
**and only those**, never a key that was already held before this request — and return 409
`SEAT_UNAVAILABLE` naming every seat that was lost. **That release is best-effort and it is safe that it is:** if the instance dies
after winning three of four keys and before releasing them, those three seats stay held for the
remainder of the 180 seconds and then free themselves. No cleanup job is needed and none exists.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | One or more seats are already locked or sold, **on a first hold for this showtime** | 409 `SEAT_UNAVAILABLE`, `details.unavailable_seats` lists them | `C12 and C13 were taken by another customer. No seats were held. Your other choices are still selected — change these two and press Hold these seats again.` |
| 2 | A single named seat is unavailable and it was the only one chosen, **on a first hold for this showtime** | 409 `SEAT_UNAVAILABLE` | `C12 was taken by another customer. No seats were held. Choose a different seat and press Hold these seats again.` |
| 1b / 2b | The same two triggers, but this request **extends a live hold** (step 4 found one) | 409 `SEAT_UNAVAILABLE`, unchanged; **the existing hold is untouched and its `expires_at` does not move** | **`P-HLD-14` rows 3b and 2b.** The closing clause is `Your hold is unchanged.`, never `No seats were held.` — those seats were never in this request's rollback set and are still held |
| 3 | The same seat id appears twice in the body | 422 `VALIDATION_FAILED` | `Seat C12 was listed twice. Each seat can only be chosen once. No seats were held.` |
| 4 | A seat id is not in this showtime's seat set — including a seat added to the hall after this showtime was created (`P-ADM-14`) | 422 `VALIDATION_FAILED` | `Seat C12 is not part of this hall. No seats were held.` |
| 5 | The body names zero seats | 422 `VALIDATION_FAILED` | `Choose at least one seat.` |
| 6 | The showtime id does not exist | 404 `NOT_FOUND` | `That showtime could not be found.` |
| 7 | The request would take the customer over ten seats | 422 `SEAT_LIMIT_EXCEEDED` | `You can hold up to 10 seats for one showtime. You are holding 6 and chose 5 more.` |
| 8 | The sales cut-off has passed | 409 `SALES_CLOSED` | `Sales for this showtime closed at 7:45 pm. Choose another showtime.` |
| 9 | No authenticated user | 401 `AUTH_REQUIRED` | `Sign in to hold seats. Your selection has been kept.` |
| 10 | Redis is unreachable | 503 `DEPENDENCY_UNAVAILABLE` | `Seat holds are unavailable right now. You can still look at showtimes and seat maps. Try again in a few minutes.` |
| 11 | The per-user or per-IP bucket is empty | 429 `RATE_LIMITED` with `Retry-After` | `Too many attempts. Try again in 3 seconds.` — the span is computed from the emptied bucket's refill rate and rendered by **S7.20**; it is never a constant. `P-HLD-14` row 16 owns the sentence and carries the arithmetic |
| 12 | Anything unhandled | 500 `INTERNAL_ERROR` | `Something went wrong and your seats were not held. You have not been charged. If you need help, quote a1b2c3d4.` |

**Server-side validation.**

| Field | Type and bound | On failure |
|---|---|---|
| `showtime_id` (path) | integer, positive | 404 `NOT_FOUND` |
| `seat_ids` | array of integer, length 1..10, every element unique, every element a member of this showtime's seat set (`P-ADM-14`) and active | 422 `VALIDATION_FAILED`; a length over 10 is 422 `SEAT_LIMIT_EXCEEDED` |

The interface limit of ten is a convenience. **The test asserts the eleventh seat is refused by the
API with the interface bypassed.**

**Worked example.** A customer requests seats `[418, 402, 410]`. The acquisition order is `402`, then
`410`, then `418`. Suppose `410` returns nil. Key `lock:seat:77:402` is released with the
compare-and-delete script, `lock:seat:77:418` was never taken, and the response is 409
`SEAT_UNAVAILABLE` with `details.unavailable_seats = ["C10"]`. **Zero seats are held afterwards.**

---

### `P-HLD-02` · Hold seats for 180 seconds, from configuration, with no extension · `RULED`
`[SRC: SRC-003 OPEN-HOLD-01 · SRC-002 §E E-1 · SRC-002 §7.1 · SRC-001 §5.2.5 · FR-ADR-027 · FR-ADR-025]`
`[BRD: R-HOLD-02]`

**Behaviour.** The hold lasts **180 seconds**, read from the configuration value
`SEAT_HOLD_TTL_SECONDS`. A literal `180` anywhere in the code is a defect against `FR-ADR-027`.
`SRC-002 §8.1.1`'s 7 minutes is superseded by erratum `E-1` and is dead text; any document, test,
fixture or comment stating 7 minutes is a defect, including a fixture that happens to use it.

**The expiry instant is fixed at acquisition and does not move.** It is computed once, returned to the
client, and used to set the Redis `PX`. It is not refreshed by polling, by re-selecting a held seat,
by opening the checkout panel, or by any other activity.

**There is no extension and no renewal — of the *clock*.** A customer whose hold expires re-selects
and takes a new hold, competing on equal terms with everyone else.

**"Extending a hold" names two different things and only one of them is refused. Read this before
reading exception 2.**

| The word "extend" applied to | Exists? | Where it is specified |
|---|---|---|
| **The expiry instant** — moving `expires_at` later, buying more time on seats already held | **No.** No endpoint moves it, no activity refreshes it, and nothing in the product offers it | this row, and exception 2 below |
| **The seat set** — adding further seats to a hold that is still live | **Yes, and it is an ordinary path** | `P-HLD-01` step 4 acquires them under the **same token**; `P-HLD-11` carries the money consequence and its worked example; `SCR-SEA-01` publishes the control |

**Adding seats does not move the deadline**, which is what makes the two compatible rather than
contradictory: `P-HLD-01` sets the new seats' `PX` to the milliseconds remaining until the existing
`expires_at`, so every seat in one hold expires at the same instant and that instant is still the one
fixed by the first acquisition. **A reader who meets exception 2 without this distinction concludes
the whole extend path is unreachable**, which is precisely how `SCR-SEA-01` came to publish no state
for it.

**Expiry is measured by Redis alone.** No second timestamp exists anywhere to disagree with it, so
there is no clock skew between API instances to reconcile.

**Who may do it.** Not applicable — this is a property of every hold.

**Preconditions.** A hold has been acquired.

**Happy path.**
1. `expires_at = clock.now() + SEAT_HOLD_TTL_SECONDS`, computed once at acquisition.
2. Every one of the hold's keys is written with `PX` derived from that same value.
3. `expires_at` is returned to the client in UTC.
4. When the TTL elapses, Redis deletes the keys. Nothing else runs.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | A hold request names a seat this customer already holds | 201, no-op, the TTL is not extended — `EP-HLD-01` has one success status and this is it | (nothing — the countdown does not restart) |
| 2 | A client asks to move a live hold's **`expires_at` later** — more time on the seats it already holds | there is no such endpoint; the path does not exist | (nothing — no control offers it) |
| 2b | A client asks to **add further seats** to a live hold | **not an error.** `EP-HLD-01` is re-sent naming the new seats and they join the existing hold under its existing token and its unchanged `expires_at` (`P-HLD-01` step 4). This row refuses no part of it | (the primary action on `SCR-SEA-01` offers it, and the countdown does not restart) |
| 3 | The hold expires while the customer is on the seat map | the keys are gone; the next poll reports the seats | `Your hold has ended and your seats have been released. You have not been charged.` |

**Server-side validation.** `SEAT_HOLD_TTL_SECONDS` is validated at startup as a positive integer, and
`PAYMENT_SIMULATED_DELAY_MS` is validated at startup to be well under it. A configuration that would
let the simulated payment delay run past the hold fails the boot.

**Worked example.** `P-HLD-03` carries it.

**Why this row is written this way.** `SRC-001 §10.9` asked how long seats should be held and answered
*"we assumed 7 minutes"*. `SRC-002 §8.1.1` — now corrected by erratum `E-1` — then stated 7 minutes
as a firm requirement. An assumption
became a specification without anyone deciding it. When it was finally put to the client it came back
**3 minutes** — a different answer.

---

### `P-HLD-03` · Decide expiry by asking Redis, never by comparing clocks · `RULED`
`[SRC: SRC-003 OPEN-HOLD-01 · SRC-003 OPEN-LOCALE-01 · SRC-002 §8.1.4 · FR-ADR-018 · FR-ADR-025 · FR-ADR-027 · FR-ADR-047]`
`[BRD: R-HOLD-02 · R-HOLD-03]`

**Behaviour.** The server never compares the current time against `expires_at` to decide whether a
hold is alive. It asks Redis whether the key exists and whether its value is this hold's token. Redis
never returns a key whose TTL has elapsed, whether or not it has physically reclaimed the memory yet,
so the key's presence is the whole answer. `expires_at` exists for one purpose: to be rendered as a
countdown on the client.

**Who may do it.** Not applicable.

**Preconditions.** A hold exists.

**Happy path.**
1. A request arrives carrying a hold token.
2. For each seat in the hold, `GET lock:seat:{showtime_id}:{seat_id}`.
3. If every reply equals the token, the hold is alive.
4. If any reply is nil, the hold is over: 409 `HOLD_EXPIRED`.
5. If any reply is a different token, the hold is over and the seat is someone else's:
   403 `HOLD_NOT_OWNED`.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 0 | **The token is malformed** — not exactly 43 characters, or carrying a character outside the URL-safe base64 alphabet | **400 `REQUEST_INVALID`, before Redis is touched.** Never 409 | `This request could not be processed. Return to the seat map and choose your seats again.` |
| 1 | The token is **well formed** and the key is absent | 409 `HOLD_EXPIRED` | `The hold on your seats has ended and they have been released. You have not been charged. Choose them again if they are still free.` |
| 2 | The key holds a different token | 403 `HOLD_NOT_OWNED` | `The hold on your seats has ended and they have been released. You have not been charged. Choose them again if they are still free.` |
| 3 | The client's clock is slow and it submits after `expires_at` | the server answers from Redis, not from a clock | as row 1 |
| 4 | The client's clock is fast and it stops its own countdown early | the server still accepts the request while the key lives | (nothing — the request succeeds; the countdown was wrong and the outcome was not) |

**Server-side validation.** The hold token is a string of **exactly 43 characters from the URL-safe
base64 alphabet** — the bound `EP-HLD-01`, `EP-HLD-02`, `EP-HLD-03`, `EP-HLD-04` and `EP-PAY-01` all
publish, and the endpoint block owns the wire shape (`S1.2` rank 1).

**Malformed and unmatched are two different answers, and this row specifies both.** A string of any
other length, or carrying a character outside that alphabet, is **400 `REQUEST_INVALID`**, rejected
before Redis is touched — the same status `P-PAY-01` gives the identical field, because a token of
the wrong shape is malformed request framing rather than a field that failed a business rule. A
**well-formed** token that matches no key is 409 `HOLD_EXPIRED`, and never a 404, because a token is
not a resource identifier the customer can be told about.

**Answering a malformed token with `HOLD_EXPIRED` would be a false statement, not merely an imprecise
one.** A 43-character constraint means a token of the wrong shape could never have been issued by this
system, so it names no hold that has ever existed — and `HOLD_EXPIRED`'s published sentence tells the
customer their hold *ended* and their seats were *released*. Both halves would be untrue. An earlier
draft of this row asserted the malformed case was "rejected as malformed" and then specified only the
unmatched one, leaving `EP-HLD-02` and `EP-HLD-04` with no `400`, no `422` and no validation code in
their `errors` arrays at all — so the two endpoints were unimplementable as declared and an engineer
would have had to invent a status or reach for `HOLD_EXPIRED`. Both blocks now carry the response and
the code, and `EP-HLD-03`'s `422` is narrowed to say it covers only the well-formed case.

**Worked example — the exact instant a hold expires.**

Named start instant. A hold is acquired at exactly:

```
2026-08-14T14:02:37.412Z                   (UTC)
2026-08-14T19:32:37.412+05:30              (Asia/Kolkata)
```

`SEAT_HOLD_TTL_SECONDS = 180`. Therefore:

```
expires_at = 2026-08-14T14:05:37.412Z      (UTC)
           = 2026-08-14T19:35:37.412+05:30 (Asia/Kolkata)
```

The Redis command is `SET lock:seat:77:402 <token> NX PX 180000`. `expires_at` is returned to the
client in UTC, as the ISO-8601 string above. **The client renders `3:00` and counts down; the server
stores no copy of that arithmetic.**

What the server does at three instants, with the injected clock set to each:

| Injected clock | Redis `GET` on the key | The server's answer |
|---|---|---|
| `2026-08-14T14:05:36.412Z` — `expires_at - 1s` | returns the token | The hold is alive. A confirm proceeds to re-validate the remaining seats, lock the showtime row, and capture. |
| `2026-08-14T14:05:37.412Z` — exactly `expires_at` | returns nil | The hold is over. 409 `HOLD_EXPIRED`. **The server performs no comparison; the key is simply not there.** The boundary belongs to Redis, and Redis does not return a key at or after its deadline. |
| `2026-08-14T14:05:38.412Z` — `expires_at + 1s` | returns nil | The hold is over. 409 `HOLD_EXPIRED`. |

**The expected answers, as assertions a test makes:** at `expires_at - 1s` a confirm returns 201; at
`expires_at` and at `expires_at + 1s` it returns 409 with `code = HOLD_EXPIRED`. **A test that reaches
these instants by sleeping is a defect** — the clock is injected and expiry is exercised by advancing
it (Art IX.5, `FR-ADR-018`).

---

### `P-HLD-04` · Cap a customer at ten seats held **at once** on one showtime · `RULED`
`[SRC: SRC-003 OPEN-BOOK-01 · FR-ADR-026]`
`[BRD: R-HOLD-04]`

**Behaviour.** A customer may hold at most **ten** seats **at any one moment** for one showtime, from
the configuration value `MAX_SEATS_PER_BOOKING`. The count includes everything they are already
holding for that showtime, not only the seats in this request. Two requests for six seats each on the
same showtime is eleven seats held by one customer, and the second is refused **before any lock is
taken**.

**What this cap bounds, and what it does not, stated because the row's own name used to imply the
other one.** It bounds **concurrent holds**, and through them the size of one booking. It does **not**
bound how many seats one customer may buy on one showtime over time. `P-PAY-10` step 13 removes the
hold's token from `holds:user:{user_id}:showtime:{showtime_id}` at commit **deliberately**, so the cap
stops counting seats the customer now owns — for the same reason `P-HLD-08` step 8 removes it on a
release: leaving it there would keep the cap consumed by a hold that no longer exists, and a customer
who had just bought ten seats could buy nothing else on that showtime for the remainder of the 180
seconds. **The consequence is that a customer may buy ten seats, then immediately hold and buy ten
more, and repeat.** That is the specified behaviour, not a defect, and a test transcribed from an
earlier reading of this row's title would assert a per-showtime lifetime limit the server does not
enforce and never did.

**No source states a lifetime limit.** `SRC-003 OPEN-BOOK-01` reads `"10 maxx"` against a question
asking the maximum number of seats **in one booking**; `FR-ADR-026` decides only that the cap is ten,
that it is enforced at the hold rather than only at confirmation, and that it counts the customer's
live holds on that showtime. Neither reaches successive bookings, so this document adds no rule about
them — **inventing one would be a scope change and scope is reserved.** Recorded as
`PROPOSED-BULKBUY-01` in the lane notes: whether one customer should be able to buy out a hall in
successive ten-seat bookings is a product question nobody has asked, and it is the client's.

**The cap is per showtime.** One customer may hold seats on more than one showtime at a time — two
films in one evening is a legitimate purchase pattern and nothing rules against it. There is no
cross-showtime cap.

**How the count is read.** Redis carries a set `holds:user:{user_id}:showtime:{showtime_id}` listing
that customer's live hold tokens, with the same TTL as the holds. The cap check reads that set and the
seat count stored under each token — a lookup of at most ten known keys, never a `SCAN`.

**Who may do it.** customer, manager, admin — every signed-in account. Only the guest is refused.

**Preconditions.** An authenticated user.

**Happy path.**
1. Read the customer's live holds on this showtime.
2. Sum their seat counts.
3. Add the number of seats in this request.
4. If the sum is at most `MAX_SEATS_PER_BOOKING`, proceed to acquisition.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | The request alone names more than ten seats | 422 `SEAT_LIMIT_EXCEEDED`, no lock touched | `You can hold up to 10 seats for one showtime. You chose 11.` |
| 2 | The request plus existing holds exceeds ten | 422 `SEAT_LIMIT_EXCEEDED`, no lock touched | `You can hold up to 10 seats for one showtime. You are holding 6 and chose 5 more.` |
| 3 | The customer selects an eleventh seat in the interface | no request is sent | `Up to 10 seats.` — the note under the total; the tap does not add the seat |
| 4 | The customer holds ten on showtime A and requests four on showtime B | 201 — the cap is per showtime | `4 seats held by you`, and `1 seat held by you` had it been one — the count is interpolated and both forms are published (`SCR-SEA-01`) |
| 5 | The customer **buys** ten seats on this showtime and immediately requests ten more on the same showtime | **201** — at commit `P-PAY-10` step 13 removed the token from `holds:user:{user_id}:showtime:{showtime_id}`, so the cap counts nothing and this request starts a fresh hold | `10 seats held by you` |

**Server-side validation.** `len(seat_ids) <= MAX_SEATS_PER_BOOKING`, and
`existing_held + len(seat_ids) <= MAX_SEATS_PER_BOOKING`, where `existing_held` is read from the
**live holds** index and therefore counts no seat the customer has already bought. Enforced in the
domain layer, so the interface limit is not the control. **A test asserting that a customer who has
bought ten seats is refused an eleventh on that showtime asserts a rule this document does not state
and the server does not enforce**; the assertion that belongs here is exception row 5's `201`.

**Every string in this lane that shows the number ten renders `MAX_SEATS_PER_BOOKING`. A literal `10`
in any of them is a defect.** The rule is the document's, stated in `S7` and binding on every lane;
this row marks the strings it owns because this row owns the configuration value they quote. The
strings are:

| Verbatim, as published | Interpolates |
|---|---|
| `Up to 10 seats.` — the note under the price-summary total, 7 sites in this file | `MAX_SEATS_PER_BOOKING` |
| `You can hold up to 10 seats for one showtime. You chose 11.` | `MAX_SEATS_PER_BOOKING`, and the submitted seat count |
| `You can hold up to 10 seats for one showtime. You are holding 6 and chose 5 more.` | `MAX_SEATS_PER_BOOKING`, the customer's live held count, and the requested count |

**The published strings above do not change** — they are the rendering at the default of 10, which is
what `MAX_SEATS_PER_BOOKING` holds today. **Why the marking is load-bearing rather than pedantry:**
the boot check validates `MAX_SEATS_PER_BOOKING` as a positive integer and permits values other than
ten, so at `MAX_SEATS_PER_BOOKING = 6` a literal would tell the customer a limit of ten while the
server refused the seventh seat — the interface stating one rule and the server enforcing another, on
the one number in this lane a customer plans around. The three interpolated counts in rows 2 and 3
were never constants and are not affected; the cap is the value that could silently drift.

**Worked example.** `MAX_SEATS_PER_BOOKING = 10`. The customer holds 6 seats on showtime 77 under one
token and requests 5 more. `6 + 5 = 11 > 10`, so the request is refused with 422
`SEAT_LIMIT_EXCEEDED` and **the six seats already held are untouched and their expiry does not move.**
A request for 4 instead gives `6 + 4 = 10`, which is accepted.

---

### `P-HLD-05` · Stop the guest at the hold, not at the seat map and not at payment · `RULED`
`[SRC: SRC-003 OPEN-BOOK-02 · SRC-003 OPEN-ROLE-01 · SRC-001 §4.1 · SRC-001 §7.4 · FR-ADR-014 · FR-ADR-046 · FR-ADR-009]`
`[BRD: R-HOLD-06]`

**Behaviour.** A guest may browse, open a seat map, select seats and watch the total build. **A guest
cannot acquire a hold.** The hold is the first authenticated action. Stopping at the hold rather than
at payment is the stricter option: an unauthenticated hold endpoint would let anyone lock every seat
in a 220-seat hall for three minutes with no account.

**Authorisation is applied once, on the router, as a dependency.** Never inside a handler. A hold
handler that performs its own role check is a defect.

**The selection survives the sign-in round trip.** The chosen seat ids and the showtime are written to
`sessionStorage` before the authentication step and restored after it. **The hold is not taken
automatically on return** — the seats are re-selected in the interface and the customer presses the
action again. Taking it automatically would either silently drop a seat that had gone, or fail with an
error immediately after a successful registration, which reads as the registration having failed.

**Who may do it.** customer, manager, admin — every signed-in account. Only the guest is refused. A manager has an account, and the
booking path is open to any signed-in account. **Whether a manager may buy a ticket at all is
unruled** — `FR-ADR-009` makes a manager read-only on the *management* surface and says nothing
about them buying a seat as a person, and `FR-ADR-014` requires only that a booking belong to a
registered user. This document therefore adds **no** prohibition, because a prohibition no source
states would be an invention. Raised as `PROPOSED-MGRBOOK-01`: a manager buying a seat in a hall
whose takings they report on is a conflict-of-interest question nobody has asked, and it is the
client's to answer.

**Preconditions.** A valid JWT identifying an existing user row. **No role is excluded except the absent one** — see `PROPOSED-MGRBOOK-01`.

**Happy path.**
1. A guest selects seats. The primary action reads `Sign in to hold these seats`.
2. Pressing it writes the selection to `sessionStorage` and opens the authentication step, which is
   one screen with two tabs — register and sign in — not two destinations.
3. On return the selection is restored and re-checked against a freshly fetched map.
4. The primary action now reads `Hold these seats`. Pressing it acquires the hold.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | A hold request arrives with no token | 401 `AUTH_REQUIRED` | `Sign in to hold seats. Your selection has been kept.` |
| 2 | A hold request arrives with an expired token | 401 `AUTH_REQUIRED` | `Sign in to hold seats. Your selection has been kept.` |
| 3 | A hold request arrives from a manager account | **Accepted**, exactly as for a customer. No source refuses it, so nothing here refuses it — see `PROPOSED-MGRBOOK-01` | *(nothing — the hold succeeds)* |
| 4 | A seat in the restored selection has gone while the customer was registering or signing in | no request for the selection; the map is refetched | **Specified once in `P-ACC-13` (lane E5). Not restated here** — that row owns the return-from-sign-in wording, and `P-SEA-03` owns the local-refresh wording. See the note below |

**Server-side validation.** The router dependency asserts an authenticated principal whose role is
a signed-in account of any role before the handler runs. **The test asserts a guest is refused with the interface
bypassed**, and asserts the check lives on the router by emptying the handler body and seeing the 401
still returned.

**Worked example.** Not applicable — this specification computes nothing.

**Note on measurement.** `SRC-001 §3.1`'s two-minute target is measured from the seat map for a
signed-in customer. For a first-time guest it includes registration and **will not be met.** That is
worth stating rather than quietly measuring the easier path.

---

### `P-HLD-06` · Check the sales cut-off at the hold and never at confirmation · `PROVISIONAL`
`[SRC: SRC-003 OPEN-BOOK-03 · SRC-001 §10.12 · SRC-003 OPEN-LOCALE-01 · SRC-002 §7.1 · FR-ADR-042 · FR-ADR-018 · FR-ADR-045]`
`[BRD: R-HOLD-07]`

> **⚠ `PROVISIONAL`. The direction could go either way and one message from the client settles it.**
> The question asked how long **before** a show starts sales stop. The recommendation put to the
> client proposed a number of minutes **after** the start, because a cinema runs trailers. The client
> answered `"yes 15 minutes"`. **The alternative reading is 15 minutes before the start**, and the two
> are half an hour apart. `SRC-003 OPEN-BOOK-03` records both. **Reversing it changes one configured
> number and its sign, and nothing else.**

**Behaviour.** Sales for a showtime close at `starts_at + SALES_CUTOFF_MINUTES`, where
`SALES_CUTOFF_MINUTES = +15` and a positive value means *after* the advertised start. The cut-off is
**derived at evaluation time, never stored on the showtime row**, so changing the configuration takes
effect immediately across every showtime with no backfill.

**It is checked at hold acquisition and never at confirmation.** A customer who acquired a hold before
the cut-off may finish checking out after it. Two consequences, both intended: the confirm path cannot
reject a customer who is already paying; and the effective close is `starts_at + 15 minutes + the
hold`, which is the honest number and belongs in the runbook rather than being rounded off.

**A past-cut-off showtime is still visible**, with its full seat map, marked closed, and its seats not
selectable. Hiding it would make a customer think the showtime never existed.

**Who may do it.** Not applicable — this is a gate on the hold.

**Preconditions.** The showtime has a `starts_at` and the cinema row carries its IANA zone name.

**Happy path.**
1. Read `starts_at` from the showtime row.
2. Compute `sales_close_at = starts_at + SALES_CUTOFF_MINUTES`.
3. Compare against the injected clock, evaluated in the cinema's zone — never against the container's
   local time, which in AWS is UTC and would roll the date over at 05:30 local.
4. If `now < sales_close_at`, proceed.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | `now >= sales_close_at` at a hold request | 409 `SALES_CLOSED`, no lock touched | `Sales for this showtime closed at 7:45 pm. Choose another showtime.` |
| 2 | The cut-off passes while a customer holds seats | nothing; the hold is honoured | `Sales for this showtime have closed. You can still pay for the seats you are holding.` |
| 3 | The cut-off passes while a customer is paying | nothing; the confirm does not re-check | (nothing — the payment completes normally) |
| 4 | An admin moves a showtime earlier, past the cut-off, while a customer holds seats | the hold is honoured; the cut-off is re-derived for new holds | as row 2 |
| 5 | A closed showtime's seat map is requested | 200, with every seat unselectable and a closed flag | `Sales for this showtime have closed.` |

**Server-side validation.** `SALES_CUTOFF_MINUTES` is a signed integer read from configuration and
validated at startup. A negative value produces the alternative reading with no code change.

**Worked example.** A showtime starts at 19:30 Asia/Kolkata on 2026-08-14:

```
starts_at            = 2026-08-14T19:30:00+05:30  =  2026-08-14T14:00:00Z
SALES_CUTOFF_MINUTES = +15
sales_close_at       = 2026-08-14T19:45:00+05:30  =  2026-08-14T14:15:00Z
```

| Injected clock | The hold request |
|---|---|
| `2026-08-14T19:44:59+05:30` | accepted — 201, hold granted |
| `2026-08-14T19:45:00+05:30` | refused — 409 `SALES_CLOSED` (the comparison is `now >= sales_close_at`) |
| `2026-08-14T19:45:01+05:30` | refused — 409 `SALES_CLOSED` |

**The effective last moment a booking can complete** is a hold taken at 19:44:59 finishing its
checkout: `19:44:59 + 180s = 19:47:59` Asia/Kolkata. Under this reading a customer can buy a ticket for
a film that started nearly eighteen minutes ago.

**Under the rejected reading**, `SALES_CUTOFF_MINUTES = -15` gives `sales_close_at =
2026-08-14T19:15:00+05:30`, and the same customer could not buy a ticket for a film starting in
fourteen minutes. **Only the configured value and these three assertions change.**

---

### `P-HLD-07` · Name the seats that went, immediately, and never blame the customer · `RULED`
`[SRC: SRC-001 §5.2.6 · FR-ADR-026 · FR-ADR-052 · FR-ADR-029]`
`[BRD: R-HOLD-05]`

**Behaviour.** When one or more seats a customer wanted has gone, the response is 409
`SEAT_UNAVAILABLE` and `details.unavailable_seats` carries the seat labels the customer reads, such as
`C12`, not the internal ids. The interface names them in the banner, marks them as unavailable on the
map immediately, and **leaves the rest of the selection exactly as it was**, so the customer changes
only what went.

**After a lost *first* hold the message never says any seats are still held**, because none are — the
hold is all-or-nothing and the won keys were released. This corrects the example copy in
`COMPONENTS.md §6`, which reads *"Your other seats are still held"* while citing `FR-ADR-026`. It is
reported in the lane notes.

**A request that *extends* a live hold is the one case where seats genuinely are still held, and it is
told so.** All-or-nothing is **over the seats the request names**, not over the hold: `P-HLD-01`
step 4 acquires the new seats under the existing token, and the "distinguishing the two nils"
rule keeps seats the customer already owned **out of this request's rollback set**, so a failure here
cannot release them. Their `expires_at` does not move either. The closing clause is therefore
`Your hold is unchanged.` and not `No seats were held.` — `P-HLD-14` rows 2b and 3b publish both
sentences, and `SCR-SEA-01`'s **Hold live, further seats chosen** state renders them. **This is the
only path in the lane on which "still held" is a true statement**, and it is why the flat rule above
is stated with its scope rather than as an absolute.

**The lost seats are marked unavailable, not sold.** A seat lost to another customer's hold is
`held_by_other`; it becomes `sold` only when their booking commits. `COMPONENTS.md §6`'s instruction to
mark them `sold` overstates what is known, and the next poll settles it either way.

**Losing a seat is the system working correctly, and the message says so plainly.** No apology, no
exclamation, no figure of speech.

**Who may do it.** Not applicable.

**Preconditions.** A hold or confirm request lost at least one seat.

**Happy path.** Not applicable — this specification is a failure path.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | Two of five seats lost at a **first** hold acquisition | 409 `SEAT_UNAVAILABLE`, `details.unavailable_seats = ["C12","C13"]` | `C12 and C13 were taken by another customer. No seats were held. Your other choices are still selected — change these two and press Hold these seats again.` |
| 2 | One of one seat lost at a **first** hold acquisition | 409 `SEAT_UNAVAILABLE`, `details.unavailable_seats = ["C12"]` | `C12 was taken by another customer. No seats were held. Choose a different seat and press Hold these seats again.` |
| 2b | Two of the further seats lost on a request **extending a live hold** | 409 `SEAT_UNAVAILABLE`, `details.unavailable_seats = ["C12","C13"]`; the existing hold and its `expires_at` are untouched | `C12 and C13 were taken by another customer. Your hold is unchanged. Your other choices are still selected — change these two and try again.` (`P-HLD-14` row 3b) |
| 2c | One of the further seats lost on a request **extending a live hold** | 409 `SEAT_UNAVAILABLE`, `details.unavailable_seats = ["C12"]`; the existing hold and its `expires_at` are untouched | `C12 was taken by another customer. Your hold is unchanged. Choose a different seat and try again.` (`P-HLD-14` row 2b) |
| 3 | A seat lost at the database guard during confirm | 409 `SEAT_UNAVAILABLE`, `details.unavailable_seats = ["C12"]` | `C12 was taken by another customer before your payment finished. Your booking was not made and you have not been charged.` |
| 4 | A seat found already sold during the hold's post-acquisition check | 409 `SEAT_UNAVAILABLE` | as row 2 |

**Server-side validation.** `details.unavailable_seats` is a non-empty array of seat labels whenever
the code is `SEAT_UNAVAILABLE`. The interface branches on `code`, never on `message`.

**Worked example.** Not applicable — this specification computes nothing.

---

### `P-HLD-08` · Let a customer give seats back, one at a time or all at once · `RULED`
`[SRC: SRC-002 §8.1.3 · SRC-001 §5.2.2 · FR-ADR-025 · FR-ADR-026 · FR-ADR-045]`
`[BRD: R-HOLD-01]`

**Behaviour.** Tapping a seat the customer is holding gives that seat back. The release is the
compare-and-delete Lua script against that seat's key, using the hold's token, so a client can only
release a lock it owns. **The rest of the hold survives, with the same `expires_at`** — giving a seat
back does not buy more time on the others. If the released seat was the last one, the hold ends and the
countdown disappears. Releasing the whole hold in one action is the secondary control on the price
summary, `Give up these seats`, and it is `EP-HLD-04`. **It has its own numbered procedure below**, and
it is not the per-seat procedure run in a loop.

**Who may do it.** The hold's owner. Enforced on the router as an authenticated dependency, plus an
ownership check: the hold record's `user_id` must equal the caller's. **The token alone is not
sufficient**, which is what makes it safe for the token to appear in a URL path and therefore in an
access log.

**A release racing a confirm is settled by ordering, not by a lock.** There is **no "confirm in
flight" flag and no error code refusing the release.** Such a flag would be new durable state —
something would have to set it, clear it, and clear it again when the confirming process died between
setting it and
committing — and `FR-ADR-025` deliberately keeps hold state out of PostgreSQL. **The confirm's own
Redis re-validation (`FR-ADR-029` step 2) already resolves the race, and there are only two
orderings:**

1. **The release lands first.** The compare-and-delete removes the key. Re-validation then finds no
   key, the confirm rolls back before the showtime row is locked and before any payment, and returns
   409 `HOLD_EXPIRED`. **Nothing is charged.**
2. **The release lands after the seats are booked.** The booking committed and its keys were released
   post-commit, so the compare-and-delete finds no key, or finds one another customer has since taken
   whose token does not match. Either way it deletes nothing: **the release is a harmless no-op**, and
   a Redis operation cannot un-sell a committed `booking_seat` row (`P-SEA-05`).

**Both orderings are safe, neither needs a lock, and the customer is told the truth in each: in the
first they are told the hold ended and they were not charged; in the second they are given their
booking reference.** The seat lifecycle machine's `held_by_me_paying` + `DESELECT` transition carries
the same rule.

**Preconditions.** A live hold whose token the caller presents, containing the named seat.

**Happy path — the per-seat release (`EP-HLD-03`).**
1. Look up the hold record by token. Assert its `user_id` matches the caller.
2. Assert the named seat is in the hold's seat set.
3. Run the compare-and-delete script against `lock:seat:{showtime_id}:{seat_id}` with the hold's token.
4. Remove the seat and its price from the hold record; leave `expires_at` unchanged.
5. Remove the key from `instance:{instance_id}:holds`.
6. **`DEL cache:seatmap:{showtime_id}`** — `P-BRW-12` requires the delete after a release exactly as
   after a hold, and this is the point at which the seat is free for everyone else. It runs after the
   lock release, never before: a `DEL` issued first lets a rebuild land while the key still exists and
   re-cache the seat as held.
7. Return the remaining seats, their prices, the new total and the unchanged `expires_at`.
8. If no seats remain, delete the hold record **and remove the token from
   `holds:user:{user_id}:showtime:{showtime_id}`**, then return an empty hold. **Leaving the token in
   that set would keep the customer's cap consumed by a hold that no longer exists** — `P-HLD-04`
   counts from that set, so a customer who gave back all ten seats could not take ten again until the
   TTL elapsed.

**Happy path — the whole-hold release (`EP-HLD-04`), which is a second procedure and not the first one
in a loop.** It reaches the same end state the per-seat path reaches on its last seat — every key
released, the hold record gone, the cap index entry gone, the seat-map cache invalidated — but it
performs the record, index and cache work **once** rather than testing for it after each seat:

1. Look up the hold record by token. Assert its `user_id` matches the caller. **A token of the wrong
   shape never reaches this step** — it is 400 `REQUEST_INVALID` before Redis is touched (`P-HLD-03`).
2. For **every** seat in the hold, in ascending `seat_id` order, run the compare-and-delete script
   against `lock:seat:{showtime_id}:{seat_id}` with the hold's token.
3. Remove every one of those keys from `instance:{instance_id}:holds`.
4. Delete the hold record.
5. **Remove the token from `holds:user:{user_id}:showtime:{showtime_id}`.** Without this the customer
   who just gave back all ten seats is capped by a hold that no longer exists for the remainder of the
   180 seconds, and is told the seats were taken by another customer when the other customer is
   themselves — **the exact failure step 8 above exists to prevent, on the other endpoint.**
6. **`DEL cache:seatmap:{showtime_id}`** — `P-BRW-12` owns seat-map invalidation and requires the
   delete after a release exactly as after a hold. It runs **after** step 2, never before: a `DEL`
   issued first lets a rebuild land while the keys still exist and re-cache the seats as held. Without
   it the seats show held to everyone else for up to the cache's TTL rather than about three seconds.
7. Return **204** with no body. The hold is gone, so there is no remaining hold to describe.

**Steps 2 to 6 are best-effort, and it is safe that they are.** Every structure they touch carries the
hold's TTL, so an instance that dies part-way through costs the seats time and never correctness: the
keys expire, the hold record expires, the index entry expires, and the cache entry expires. **Nothing
here is a cleanup job and none is needed.**

**Three cases the one-sentence version of this path left open, answered here.**

- **A partial release.** There is no such thing on this endpoint — it names no seats, so it always
  addresses the whole hold. What can be *partial* is the **effect**: a compare-and-delete returning 0
  for one seat, because that key already expired or already carries another customer's token, is
  **not an error and does not stop the loop.** The remaining seats are still released and the answer
  is still 204. Refusing the whole request because one key had already gone would leave nine seats
  locked for no reason.
- **Releasing a seat another customer is waiting for.** Nothing is notified and nothing is queued.
  That customer learns at their next 3-second poll, which step 6 is what makes about three seconds
  rather than up to thirteen, and the seat repaints `available` with the changed-seat outline
  (`SCR-SEA-01`). There is no reservation queue and no first-in-line claim on a released seat; the
  next `SET NX` wins, exactly as at any other moment.
- **Releasing a hold that already expired on its own.** 409 `HOLD_EXPIRED`, and **steps 2 to 6 do not
  run.** There is nothing to release, and the hold record and the index entry carried the same TTL as
  the keys and are gone with them. In particular **no `DEL cache:seatmap` runs on this path**: an
  expiry frees seats without telling the cache anywhere in this document, which is why an expired
  hold's seats can read held for up to the cache TTL and `P-HLD-02` exception 3 tells the customer the
  next poll reports them. That is existing accepted behaviour, restated here because a reader adding
  step 6 to the 409 branch would be inventing an invalidation the expiry path has never had.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | The hold has already expired | 409 `HOLD_EXPIRED` | `The hold on your seats has ended and they have been released. You have not been charged. Choose them again if they are still free.` |
| 2 | The token belongs to another user | 403 `HOLD_NOT_OWNED` | `The hold on your seats has ended and they have been released. You have not been charged. Choose them again if they are still free.` |
| 3 | The seat is not in this hold | 422 `VALIDATION_FAILED` | `That seat is not part of your hold.` |
| 4 | A release lands **before** the confirm's re-validation | 200 on the release; the confirm then finds no key and returns 409 `HOLD_EXPIRED` before any payment | `The hold on your seats has ended and they have been released. You have not been charged. Choose them again if they are still free.` |
| 5 | A release lands **after** the booking committed | the compare-and-delete matches no live token and deletes nothing; the booking stands | the confirmation and its booking reference — the seat was bought before the release arrived |
| 6 | Redis is unreachable | 503 `DEPENDENCY_UNAVAILABLE` | `Seat holds are unavailable right now. You can still look at showtimes and seat maps. Try again in a few minutes.` |
| 7 | The compare-and-delete returns 0 because the key already expired | treated as success; the seat is removed from the hold record | (nothing — the seat repaints to available and the total drops) |

**Server-side validation.** `hold_token` is a string of **exactly 43 characters from the URL-safe
base64 alphabet**, the bound `EP-HLD-03` and `EP-HLD-04` publish (`S1.2` rank 1). **A token of any
other shape is 400 `REQUEST_INVALID` before Redis is touched, never 409 `HOLD_EXPIRED`** (`P-HLD-03`).
`seat_id` is a positive integer that must be a member of the hold's seat set. A release that leaves the hold with zero
seats is valid and ends the hold.

**Worked example.** A customer holds three Recliner seats at 33333 paise each — total `99999` paise,
`₹999.99` — with `expires_at = 2026-08-14T14:05:37.412Z`. They give one back. The hold now carries two
seats, total `66666` paise, `₹666.66`, and **`expires_at` is still `2026-08-14T14:05:37.412Z`**: the
countdown neither restarts nor pauses.

**Judgment call recorded.** Nothing in any source says whether releasing one seat reduces the hold or
voids it. Reducing it is chosen, because voiding would take away seats the customer never asked to give
up, and because the price snapshot is per seat and survives the removal of another. Reported in the
lane notes.

---

### `P-HLD-09` · Show a countdown from a server-issued instant, and warn once at sixty seconds · `RULED`
`[SRC: SRC-001 §5.2.5 · SRC-001 §5.2.6 · SRC-003 OPEN-HOLD-01 · SRC-002 §8.1.4 · FR-ADR-047 · FR-ADR-027 · FR-ADR-051]`
`[BRD: R-HOLD-03]`

**Behaviour.** The hold response carries an absolute `expires_at` in UTC — not a duration and not a
remaining-seconds count, both of which start drifting the moment they are sent and cannot survive a tab
pause. The client renders `m:ss` by subtracting from its own clock. **The server never trusts that
arithmetic**, so a wrong client clock produces a wrong display and never a wrong outcome.

**The countdown shows on both the seat map and the checkout panel**, and is never hidden behind a
tooltip. A customer with three minutes is entitled to see all three.

**One warning, at 60 seconds.** Not 60, 30 and 10. At the threshold three things change together: the
bar colour, the digit colour, and a line of text naming the consequence. It is announced once through a
live region.

**At zero the client stops the countdown, disables the payment action and states that the hold has
expired. It does not delete anything, release anything, or claim the seats are free.** It reports only
what its own clock says. The seat cells are **not** pre-emptively repainted; they change when the next
poll reports them, so the customer watches the seats leave rather than finding them gone.

**The hold token and the Idempotency-Key live in `sessionStorage`**, so a page refresh keeps the hold
and the countdown resumes from the same `expires_at`. Not `localStorage`: that outlives the tab, and a
stale token from yesterday would be presented against a hold that no longer exists. `sessionStorage`
has exactly the right lifetime.

**Closing the tab releases nothing.** There is no unload-time release. An unload handler is unreliable,
and a fire-and-forget release from a closing page can arrive after the key has expired and been
re-acquired by someone else — the compare-and-delete token makes that harmless, but the request is
still one that cannot be relied on. The TTL is what releases it, which is what `SRC-002 §8.1.4`
intends.

**Who may do it.** The hold's owner sees it. Nobody else has one.

**Preconditions.** A live hold with an `expires_at`.

**Happy path.**
1. The hold response returns `expires_at`.
2. The component takes the current instant as an input and renders `m:ss`. **It never reads the wall
   clock itself**, which is why it needs no time-dependent test.
3. At 60 seconds remaining the warning line appears and is announced once.
4. At `0:00` the countdown stops and the payment action is disabled.

**Exception paths.**

| # | Trigger | Client | What the user sees, verbatim |
|---|---|---|---|
| 1 | 60 seconds remain | the bar and digits change colour; the warning line appears | `Less than a minute left. At 0:00 your seats are released and you will need to choose them again.` |
| 2 | Zero, with no confirm in flight | the countdown stops; the payment action is disabled | `Your hold has ended and your seats have been released. You have not been charged.` |
| 3 | Zero, with a confirm already in flight | the busy state is kept; the request is not cancelled and cannot be | `Your hold has ended. We are waiting for the answer to your payment. Do not close this page.` |
| 4 | `expires_at` is already past when the page loads | the zero state renders immediately; no negative numbers, ever | as row 2 |
| 5 | The page is refreshed mid-hold | the token is read from `sessionStorage` and the hold is re-read from the server | the countdown resumes at the correct remaining time |
| 6 | The tab is closed | nothing is sent | (nothing — the hold expires on its own) |
| 7 | The device clock is wrong by a minute | the countdown is wrong; the server is unaffected | a wrong number in the countdown, and a request that still succeeds or fails on the server's answer |

**Server-side validation.** `expires_at` is emitted as an ISO-8601 instant in UTC with milliseconds.
The server accepts no client-supplied expiry of any kind.

**Worked example.** With `expires_at = 2026-08-14T14:05:37.412Z` and the client's clock at
`2026-08-14T14:04:22.412Z`, the countdown renders `1:15`. At `2026-08-14T14:04:37.412Z` it renders
`1:00` and the warning fires.

**Row 3 corrects `COMPONENTS.md §7`**, which disables the payment action at zero unconditionally: a
request already sent cannot be un-sent, and claiming the hold ended before the server has answered
would be a false statement. Reported in the lane notes.

---

### `P-HLD-10` · Fail the hold and the confirm loudly when Redis is unreachable · `RULED`
`[SRC: SRC-002 §7.9 · SRC-002 §7.4 · SRC-002 §5.2.3 · FR-ADR-028 · FR-ADR-025 · FR-ADR-058 · FR-ADR-052]`
`[BRD: R-HOLD-01 · R-QLY-10]`

**Behaviour.** If Redis is unreachable the hold endpoint returns **503 `DEPENDENCY_UNAVAILABLE`**. It
never falls back to the database for locking, never proceeds without a lock, and never degrades
quietly. **Booking confirmation also returns 503**, because confirming without a live hold would rely
on the database constraint alone — safe against overselling, but wrong for the customer, who would
discover at payment that they were confirming seats someone else was holding.

**Browsing keeps working — for the two lists, not for the seat map.** The movie list and the showtime
list are cache-aside and unlimited, so a cache outage is the same event as a cache miss to them. **The
seat map is different**: `FR-ADR-058` rate-limits it and the limiter fails closed, so it answers 503
(`X-7`). The seat map, movie list and showtime list are cache-aside, and a cache
outage is the same event as a cache miss to a cache-aside reader. That is not the fallback `§7.9`
forbids: `§7.9` forbids substituting the database for Redis's *lock* semantics, which the database
cannot provide the same way. Reading a seat map from its source of truth is not a substitution.

**The rate limiter fails closed**, so limited endpoints also return 503 rather than granting unlimited
access.

**`/health/ready` still returns 503** when Redis is unreachable. With one EC2 instance that takes every
instance out of the ALB, so the site is down even though browsing would have worked. **That is the
design and the cost is recorded rather than softened** — the client asked to see the failure.
*(reasoned, not observed — this has never run in AWS.)*

**The failure path touches nothing that can fail.** A Redis failure caught in an exception handler must
not read Redis again to build the message or to log. There is one `cache.t3.micro` node with no
replica, so this is not hypothetical: a maintenance restart produces it, and every live hold is lost
with it.

**Who may do it.** Not applicable.

**Preconditions.** None.

**Happy path.** Not applicable — this specification is a failure path.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | Redis unreachable at a hold request | 503 `DEPENDENCY_UNAVAILABLE` | `Seat holds are unavailable right now. You can still look at showtimes and seat maps. Try again in a few minutes.` |
| 2 | Redis unreachable at confirm | 503 `DEPENDENCY_UNAVAILABLE`, before any payment | `We cannot complete your booking right now. You have not been charged. Try again in a few minutes. If you need help, quote a1b2c3d4.` |
| 3 | Redis unreachable at a release | 503 `DEPENDENCY_UNAVAILABLE` | `Seat holds are unavailable right now. You can still look at showtimes and seat maps. Try again in a few minutes.` |
| 4 | Redis unreachable while the seat map is polled | **503 `DEPENDENCY_UNAVAILABLE`** on the poll (`X-7`). The last good map stays on screen and stops updating; it is never blanked | "The seat map is not updating. The seats shown may be out of date." |
| 5 | Redis returns after an outage | holds taken before it are gone; new holds work | as row 1 until it returns, then normal operation |

**Server-side validation.** The Redis client carries explicit connect and command timeouts. A default
of no timeout turns an unreachable node into hung requests rather than a 503, and hung requests exhaust
the connection pool.

**Worked example.** Not applicable.

**Test note.** This needs a test that **actually stops the Redis container**, not one that mocks a
connection error. A mock proves the handler; only stopping the container proves the client's timeout
configuration.

---

### `P-HLD-11` · Fix each seat's price at hold acquisition and never recompute it · `RULED`
`[SRC: SRC-003 OPEN-PRICE-01 · SRC-001 §5.2.4 · SRC-001 §7.6 · FR-ADR-035 · FR-ADR-038 · FR-ADR-039]`
`[BRD: R-SEAT-04]`

**Behaviour.** At hold acquisition the API computes the per-seat prices with `FR-ADR-038`'s rule and
stores them **with the hold, in Redis, under the hold token**. At confirmation those stored prices are
used, not recomputed. **The price a customer pays is the price that was current when their hold was
granted.**

**The window is bounded by the hold** — at most 180 seconds of price protection, the same duration as
the seat protection, needing no separate expiry. Storing it in PostgreSQL would reintroduce the hold
table and its cleanup job.

**Admin price edits are allowed at any time and take effect for holds acquired after them.** Blocking
them would let one customer sitting at a checkout screen freeze pricing for a whole showtime. A
category uplift change is allowed on the same terms and affects only future holds.

**Who may do it.** Not applicable.

**Preconditions.** The showtime has a `base_price_paise`; every seat has a category with an
`uplift_basis_points`.

**Happy path.**
1. Read `base_price_paise` from the showtime and `uplift_basis_points` from each seat's category.
2. Compute `seat_price_paise = (base_price_paise * (10000 + uplift_basis_points) + 5000) // 10000` per
   seat, in integer arithmetic, with no float and no `Decimal` in the expression.
3. Store the seat list with its prices under the hold token, with the hold's TTL.
4. Return them, so the client's total is the figure that will be charged.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | An admin changes the base price while this hold is live | the held prices are unaffected | (nothing — the total does not move) |
| 2 | An admin changes a category uplift while this hold is live | the held prices are unaffected | (nothing — the total does not move) |
| 3 | The hold expires and the customer takes a new one after a price change | the new hold carries the new prices | the total updates to the new figure when the new hold is granted |
| 4 | Redis is unreachable, so the held prices cannot be read at confirm | 503 `DEPENDENCY_UNAVAILABLE` | `We cannot complete your booking right now. You have not been charged. Try again in a few minutes. If you need help, quote a1b2c3d4.` |
| 5 | **An admin changes the base price between two hold requests on the same showtime by the same customer** | the seats already held keep their snapshots; only the seats the second request acquires are priced at the new base. **One hold legitimately carries two base prices** | (nothing — the total rises by the new seats' prices, and the earlier seats' line prices do not move) |

**Server-side validation.** `base_price_paise` and every `uplift_basis_points` are non-negative
integers. The computed `seat_price_paise` is a non-negative integer, and no money column can hold a
fractional paisa because every money column is a `bigint` — a caller that skips the rounding function
gets a type error rather than silently persisting an unrounded value.

**Worked example.** `P-SEA-04` carries the arithmetic. The point specific to this row: a customer holds
three Recliner seats at 19:32:37 IST when `base_price_paise = 25000`, giving `33333` paise each and
`99999` paise total. At 19:33:10 IST the admin raises the base to `30000`. The customer confirms at
19:34:02 IST. **They are charged `99999` paise.** The next customer to take a hold pays
`(30000 * 13333 + 5000) // 10000 = (399990000 + 5000) // 10000 = 39999` paise per seat.

**The snapshot is per seat, taken when that seat entered the hold — not per hold, and not re-taken
when the hold is extended.** `P-HLD-01` step 4 establishes that a second hold request on the same
showtime **extends the existing hold under the same token** rather than creating a second one. The
pricing consequence follows from that and is stated here because it is money a customer reads before
pressing pay: **extending a hold reprices nothing.** Step 8 prices only the seats the request just
acquired and appends them; the seats already in the hold keep the prices they were given.

**Worked example — two requests, an admin price change between them.** `MAX_SEATS_PER_BOOKING = 10`.
Recliner uplift `3333` basis points throughout. All times Asia/Kolkata.

```
19:32:37   request 1: two Recliner seats, base_price_paise = 25000
           (25000 * 13333 + 5000) // 10000 = 33333 per seat
           hold created, token T, expires_at = 19:35:37
           stored under T:  J1 33333, J2 33333
           response:        2 seats, total_paise = 66666          -> Rs 666.66

19:33:10   an admin raises showtime.base_price_paise to 30000. The hold is untouched.

19:33:45   request 2: one more Recliner seat, SAME customer, SAME showtime
           P-HLD-01 step 4 finds hold T and reuses its token AND its expires_at
           the new seat is priced at the CURRENT base:
           (30000 * 13333 + 5000) // 10000 = 39999
           stored under T:  J1 33333, J2 33333, J3 39999    <- three seats, two base prices
           response:        3 seats, total_paise = 106665         -> Rs 1,066.65
                            expires_at STILL 19:35:37, not extended

19:34:20   confirm. P-PAY-10 step 5 sums the stored snapshots, recomputing nothing.
           charged: 33333 + 33333 + 39999 = 106665 paise         -> Rs 1,066.65
```

**Expected answer: `106665` paise, and the booking's `booking_seat` rows carry
`base_price_paise_applied = 25000` for `J1` and `J2` and `30000` for `J3`.**

**Two base prices in one booking is this row working, not a defect**, and the distinction is worth
stating because it looks like one. The guarantee is *a price change never moves what a customer
already holding is charged*. Re-snapshotting `J1` and `J2` at the new base to make the booking
internally uniform would charge them 39999 each for seats they were quoted at 33333 — which is
precisely the guarantee failing, in the direction the customer notices. `P-PAY-05`'s
`base_price_paise_applied` column exists so the two figures in one booking are auditable rather than
mysterious: each seat can answer for its own price.

**What the customer sees is never ambiguous**, because the response carries every seat with its own
line price (`P-HLD-01` step 12) and the checkout panel lists them individually (`SCR-PAY-01`). The
customer sees `J1 ₹333.33`, `J2 ₹333.33`, `J3 ₹399.99` and a total of `₹1,066.65`, which adds up on
screen — the property `P-PAY-04` requires of every total.

---

### `P-HLD-12` · Release this instance's holds on SIGTERM, and never depend on it · `RULED`
`[SRC: SRC-002 §7.5 · SRC-002 §7.3 · SRC-002 §8.1.4 · SRC-001 §7.5 · FR-ADR-033 · FR-ADR-025]`
`[BRD: R-HOLD-01]`

**Behaviour.** Each API instance has an id generated at boot. When it grants a hold it adds that hold's
keys to a Redis set `instance:{instance_id}:holds`, with the same TTL as the holds. On SIGTERM it reads
that set and runs the compare-and-delete release for each key.

**The registry is in Redis, not in process memory**, because containers are stateless and because a
process killed with SIGKILL — which is what follows SIGTERM after the grace period — loses in-memory
state before it can act on it.

**Expiry is the guarantee; release on shutdown is an optimisation on top of it.** Correctness never
depends on the release running. If it fails, if the grace period is too short, or if the instance is
SIGKILLed, the keys expire in 180 seconds and no booking is affected. That property is what makes this
safe to get wrong.

**Only holds are released. Bookings are never touched.** A hold whose booking committed had its keys
released at commit and is gone from the registry, so what remains at shutdown is, by construction,
holds that never became bookings.

**Holds still legitimately live are dropped, and that is intended.** A customer mid-checkout on a
draining instance loses their hold and is told to re-select. Keeping their seats locked while the
instance that granted them disappears leaves the seats unbuyable for up to three minutes and does not
help that customer either, because their next request goes to a different instance.

**Who may do it.** Not applicable — this is a shutdown behaviour.

**Preconditions.** SIGTERM received.

**Happy path.**
1. The instance is deregistered from the ALB target group and stops accepting new connections.
2. It waits out the ALB deregistration delay, so in-flight requests already routed complete.
3. In-flight requests finish, bounded by a drain timeout.
4. Keys in `instance:{instance_id}:holds` are released with the compare-and-delete script.
5. For each hold whose keys were released: **delete its hold record and remove its token from
   `holds:user:{user_id}:showtime:{showtime_id}`**, and **`DEL cache:seatmap:{showtime_id}`** for each
   showtime touched (`P-BRW-12`). Step 4 alone frees the seats without saying so anywhere a reader
   looks: the map would keep showing them held for up to its 10-second TTL, and `P-HLD-04` would keep
   counting them against the customer's cap for the remainder of the 180 seconds — so a customer
   dropped by a drain could not immediately re-take the seats the drain just released. **All of it is
   best-effort, exactly as step 4 is**; every structure involved carries the hold's TTL and expires on
   its own, so a drain killed part-way through costs time and never correctness.
6. The process exits.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | A customer holds seats on the draining instance | the keys are released at step 4 | `The hold on your seats has ended and they have been released. You have not been charged. Choose them again if they are still free.` |
| 2 | A confirm is in flight at step 3 | it completes before step 4 and its seats are booked | the confirmation screen with the booking reference |
| 3 | The ECS stop timeout is shorter than the deregistration delay plus the drain timeout | SIGKILL arrives at step 3; steps 4, 5 and 6 never run; the keys, the hold records and the index entries all expire in 180 seconds | as row 1, up to 180 seconds later |
| 4 | A hold expired during the drain and another customer re-acquired the seat | the compare-and-delete finds a different token and does nothing | (nothing — the other customer keeps their hold) |

**Server-side validation.** Not applicable.

**Worked example.** Not applicable.

**Zone C dependency, announced in advance.** **The ECS stop timeout must exceed the ALB deregistration
delay plus the application's drain timeout.** That relationship is the thing that breaks silently, and
all three values are Zone C configuration the client sets. `docs/30 Deployment/` owes a specification
stating the three values, their required ordering, and what breaks if they are wrong.
*(reasoned, not observed.)*

**Test note.** This requires sending a real SIGTERM to a running container and asserting the keys are
gone. A unit test proves the function; only the signal proves the wiring.

---

### `P-HLD-13` · Prove the guarantee with fifty simultaneous requests, and watch the guard fail · `RULED` · **never waivable**
`[SRC: SRC-002 §9.1 · SRC-002 §9.2 · SRC-002 §8.1.5 · SRC-001 §2.2 · SRC-001 §3.2 · SRC-001 §7.1 · SRC-003 OPEN-SCALE-03 · FR-ADR-024 · FR-ADR-034 · FR-ADR-058]`
`[BRD: R-QLY-01 · R-QLY-02]`

**Behaviour.** `scripts/stress_seats.py` fires 50 simultaneous hold requests for one seat and asserts
exactly one succeeds. It runs against local Docker and against the deployed environment by changing a
base URL. **That is Stage A of the proof, and it exercises the Redis lock layer.** The red-proof drill
— drop the unique constraint, watch the guard fail, restore it, verify the restore — is **Stage B**,
and it is a different run: it puts **two live holders on one seat** so that two confirms both reach
`P-PAY-10` step 7, because that is the only state in which the constraint is reached at all.
**`P-XCT-01` and `S7.1` own both stages and this row does not restate the procedure.**

**Why the drop does not belong to this row's run, stated because it used to.** Every one of the
forty-nine losers here is refused by Redis at `SET … NX`. **The unique constraint fires zero times in
a passing run of this gate**, so dropping it leaves one winner and one `booking_seat` row exactly as
before — and reading that as a red proof proves nothing, while reading it as a failure blocks a story
for a defect that is not there.

**Who may do it.** The build session locally; the client in their own environment. **The constraint
drop is local only** — dropping a correctness constraint in a deployed environment is a destructive
schema change, and the build session has no write access to AWS at all.

**Preconditions.** Fifty distinct seeded, authenticated customers. One showtime with at least one
available seat. The rate limiter running normally. **How the script obtains those fifty authenticated
sessions, and what the login rate-limit bucket does to that step, is owned by `P-XCT-07` and is not
restated here.**

**Happy path.**
1. Fifty distinct authenticated customers each fire one hold request for the same seat.
2. The script records each request's start instant and asserts the spread between first and last is
   within a configured threshold, defaulting to 100 ms.
3. Exactly one request returns **201**; exactly forty-nine return 409 with `code = SEAT_UNAVAILABLE`.
4. The winner confirms its hold.
5. The script reads PostgreSQL directly and asserts exactly one `booking_seat` row exists for that
   `(showtime_id, seat_id)`.

**The binary acceptance criterion — `R-QLY-02`, written so it can only pass or fail:**

> With the unique constraint on `(showtime_id, seat_id)` present, and fifty distinct authenticated
> customers issuing fifty hold requests for the same `(showtime_id, seat_id)` whose start instants
> span no more than 100 ms, the run produces **exactly one HTTP 201** and **exactly forty-nine HTTP
> 409 responses whose `error.code` is `SEAT_UNAVAILABLE`**, and a direct `SELECT count(*)` against
> `booking_seat` for that pair returns **exactly 1**.
>
> **Any other outcome fails, including zero winners.**
>
> **The constraint drop is not part of this criterion and may not be tested against this run.** With
> the constraint dropped, this same run still produces exactly one winner and exactly one
> `booking_seat` row, because every loser was refused by the Redis lock and the constraint was never
> reached. **The red proof is `P-XCT-01`'s Stage B**, which produces two live holders on one seat and
> then observes **two** committed `booking_seat` rows for one pair with the constraint dropped, one
> row with it restored, and the constraint read back from `pg_constraint`. **A drill run against this
> criterion instead reports failure against a correct implementation**, on the one gate that is never
> waivable.

**Why 201 and not 200, stated because the number is the assertion.** `CONSTITUTION.md` Art IX.3
illustrates a binary criterion with "one 200 and 49 409s". **That is an example of the *shape* a binary
criterion takes — one winner, forty-nine named losers, verified in the database — and not a statement
about this endpoint's status code.** The endpoint this gate fires at is `EP-HLD-01`, which creates a
hold that did not exist before and therefore returns **201**. So the gate asserts **exactly one 201 and
exactly forty-nine 409s**, plus **exactly one row** in `booking_seat` for the pair. A test transcribed
from the illustration rather than from this criterion asserts 200, finds zero winners, and **fails
against a correct implementation** — which on a never-waivable gate would block a story for a defect
that is not there. **The status in this criterion and the status in `EP-HLD-01` are one value and must
be changed together or not at all.**

**Exception paths.**

| # | Trigger | Result | What the operator sees |
|---|---|---|---|
| 1 | The start-instant spread exceeds the threshold | the script fails with `not concurrent` | it does **not** report a pass; a proof that cannot distinguish a working system from a serialised client is not a proof |
| 2 | Zero requests succeed | fail | the assertion is not "at most one"; zero winners means the endpoint is broken |
| 3 | Any loser returns 500 rather than 409 `SEAT_UNAVAILABLE` | fail | a unique-constraint violation translated into a 500 misleads the customer and pollutes the error rate the operator watches |
| 4 | **`P-XCT-01`'s Stage B** still produces one `booking_seat` row for the pair with the constraint dropped | **stop the line** | the run is not exercising the constraint and the whole proof is void. That is a finding, not a pleasant surprise |
| 4a | **This row's own run** — Stage A — produces one winner with the constraint dropped | **expected, and not a finding** | the gate fires at the hold, where Redis decides the winner and the constraint is never reached. Reading it as a red proof proves nothing; reading it as a failure blocks a story for a defect that is not there |
| 5 | Someone proposes disabling the rate limiter for the run | refused | disabling a control to make a test pass is the shape of a fake green, and waiving a quality check is reserved to the client |

**Server-side validation.** The unique constraint is **total**, with no `WHERE status <> 'cancelled'`
clause. It is created in the Phase 2 migration rather than alongside the booking code, so no window
exists in which bookings can be written without it.

**Worked example.** Fifty requests for `(showtime_id = 77, seat_id = 402)`. Expected: one **201**
carrying a hold token; forty-nine 409s each with `error.code = "SEAT_UNAVAILABLE"` and
`error.details.unavailable_seats = ["C2"]`; and
`SELECT count(*) FROM booking_seat WHERE showtime_id = 77 AND seat_id = 402` returning `1`.

**Never waivable.** A red concurrency gate blocks the story it belongs to; the story is marked
`Blocked` with a note and surfaced. There is no exception. The drill is a manual procedure whose record
says who ran it and when — **an undated claim that it was run is not evidence.**

**`ASSUMED` flag.** The separate light load test at 50 concurrent bookers is `ASSUMED`
(`SRC-003 OPEN-SCALE-03`, "you pick"). It measures performance, proves nothing about correctness, and
may never be cited as if it did. **The correctness gate above is not assumed and is separate.**

---

### `P-HLD-14` · Tell the customer what happened, in plain words, with a stable code · `RULED`
`[SRC: SRC-001 §5.2.6 · SRC-001 §8.2 · SRC-002 §2.2 · SRC-002 §7.6 · SRC-002 §8.4.2 · FR-ADR-052 · FR-ADR-056]`
`[BRD: R-QLY-10]`

**Behaviour.** Every failure on this lane's endpoints returns the one envelope:

```json
{"error":{"code":"…","message":"…","details":{…},"request_id":"…"}}
```

`code` is a stable machine constant and **the interface branches on it, never on the message text**.
`message` is literal and specific. `details` is structured so the interface can act — highlighting the
two seats that went rather than telling the customer to work it out. `request_id` is present on every
error response, including 500s.

**The request id is shown to the customer on 5xx only**, in small text, as the sentence
`If you need help, quote a1b2c3d4.` It appears in every log line for that request, so the one person
operating this system can find it. It is not shown on 4xx errors, which are the customer's to resolve
and where an opaque code is noise.

**Three wording rules, all from `SRC-002 §2.2`:** say what happened, not how it felt; say what to do
next where there is something to do; **never blame the customer for a race they lost.** No apology, no
exclamation, no figure of speech, no analogy.

**Nothing internal leaks.** No stack trace, no SQL, no exception class, no hostname, no table name. A
500's message is generic and the detail is in the logs against the request id.

**One deliberate generalisation, and its reason.** `FR-ADR-052` illustrates `HOLD_EXPIRED` with *"Your
three minutes ran out."* This lane uses `The hold on your seats has ended and they have been released.`
instead, because the identical code is returned when a graceful shutdown released the hold
(`P-HLD-12`) and when the key was re-acquired by someone else (`P-HLD-03`), and **the server cannot
tell those apart.** A message asserting the cause would be untrue in two of the three cases.

**The client's countdown names no cause either, for the same reason.** All three endings drive its
countdown to the same `0:00`, so `SCR-SEA-02`'s zero state reads
`Your hold has ended and your seats have been released. You have not been charged.` — it reports that
the hold is over, which the client does know, and not why, which it does not. The two strings differ
only because the server's adds `Choose them again if they are still free.`, which is advice the
countdown has no room for and the banner does.

**Who may do it.** Not applicable.

**Preconditions.** A failure occurred.

**Happy path.** Not applicable.

**Exception paths — the complete message set for this lane.**

| # | Code · HTTP | What the user sees, verbatim |
|---|---|---|
| 1 | `AUTH_REQUIRED` 401 | `Sign in to hold seats. Your selection has been kept.` |
| 2 | `SEAT_UNAVAILABLE` 409, one seat, at a **first** hold | `C12 was taken by another customer. No seats were held. Choose a different seat and press Hold these seats again.` |
| 2b | `SEAT_UNAVAILABLE` 409, one seat, at a hold that **extends a live hold** | `C12 was taken by another customer. Your hold is unchanged. Choose a different seat and try again.` |
| 3 | `SEAT_UNAVAILABLE` 409, several seats, at a **first** hold | `C12 and C13 were taken by another customer. No seats were held. Your other choices are still selected — change these two and press Hold these seats again.` |
| 3b | `SEAT_UNAVAILABLE` 409, several seats, at a hold that **extends a live hold** | `C12 and C13 were taken by another customer. Your hold is unchanged. Your other choices are still selected — change these two and try again.` |
| 4 | `SEAT_UNAVAILABLE` 409, at confirm, **one** seat lost | `C12 was taken by another customer before your payment finished. Your booking was not made and you have not been charged.` |
| 4b | `SEAT_UNAVAILABLE` 409, at confirm, **two or more** seats lost | `C12 and C13 were taken by another customer before your payment finished. Your booking was not made and you have not been charged.` |
| 5 | `HOLD_EXPIRED` 409 | `The hold on your seats has ended and they have been released. You have not been charged. Choose them again if they are still free.` |
| 6 | `HOLD_NOT_OWNED` 403 | `The hold on your seats has ended and they have been released. You have not been charged. Choose them again if they are still free.` |
| 7 | `SEAT_LIMIT_EXCEEDED` 422, the request alone | `You can hold up to 10 seats for one showtime. You chose 11.` — `10` renders `MAX_SEATS_PER_BOOKING` and `11` the submitted count (`P-HLD-04`) |
| 8 | `SEAT_LIMIT_EXCEEDED` 422, with existing holds | `You can hold up to 10 seats for one showtime. You are holding 6 and chose 5 more.` — `10` renders `MAX_SEATS_PER_BOOKING`; `6` and `5` are counts (`P-HLD-04`) |
| 9 | `SALES_CLOSED` 409 | `Sales for this showtime closed at 7:45 pm. Choose another showtime.` |
| 10 | `SALES_CLOSED` — the banner for a customer holding seats | `Sales for this showtime have closed. You can still pay for the seats you are holding.` |
| 11 | `VALIDATION_FAILED` 422, duplicate seat, **one** offending seat | `Seat C12 was listed twice. Each seat can only be chosen once. No seats were held.` |
| 12 | `VALIDATION_FAILED` 422, seat not in this showtime's seat set, **one** offending seat | `Seat C12 is not part of this hall. No seats were held.` |
| 13 | `VALIDATION_FAILED` 422, empty selection | `Choose at least one seat.` |
| 14 | `VALIDATION_FAILED` 422, seat not in this hold | `That seat is not part of your hold.` |
| 15 | `NOT_FOUND` 404 | `That showtime could not be found.` |
| 16 | `RATE_LIMITED` 429, with `Retry-After` | `Too many attempts. Try again in 3 seconds.` |
| 17 | `DEPENDENCY_UNAVAILABLE` 503, at hold or release | `Seat holds are unavailable right now. You can still look at showtimes and seat maps. Try again in a few minutes.` |
| 18 | `DEPENDENCY_UNAVAILABLE` 503, at confirm | `We cannot complete your booking right now. You have not been charged. Try again in a few minutes. If you need help, quote a1b2c3d4.` |
| 19 | `INTERNAL_ERROR` 500 | `Something went wrong and your seats were not held. You have not been charged. If you need help, quote a1b2c3d4.` |
| 20 | `VALIDATION_FAILED` 422, a seat that is out of service, **one** offending seat | `Seat C12 is out of service. No seats were held.` |
| 21 | `VALIDATION_FAILED` 422, duplicate seat, **two or more** offending seats | `Seats C12 and C13 were listed more than once. Each seat can only be chosen once. No seats were held.` |
| 22 | `VALIDATION_FAILED` 422, seats not in this showtime's seat set, **two or more** offending seats | `Seats C12 and C13 are not part of this hall. No seats were held.` |
| 23 | `VALIDATION_FAILED` 422, seats that are out of service, **two or more** offending seats | `Seats C12 and C13 are out of service. No seats were held.` |
| 24 | `REQUEST_INVALID` 400, a malformed hold token on `EP-HLD-02`, `EP-HLD-03` or `EP-HLD-04` | `This request could not be processed. Return to the seat map and choose your seats again.` — the string `P-PAY-01` publishes for the same code, reproduced verbatim rather than reworded, because one code with two sentences is the drift this table exists to prevent |

**First hold or extend, for every refusal at the hold endpoint: one substitution, applied
identically.** Every sentence in this table that a hold request can produce ends with a clause saying
what the request left behind, and **that clause has two forms**:

| The request that failed | The closing clause |
|---|---|
| The customer held **nothing** on this showtime when it arrived — a first hold | `No seats were held.` |
| The customer already held seats on this showtime — `P-HLD-01` step 4 found a live hold and this request was an **extend** | `Your hold is unchanged.` |

**The server picks, and the client composes nothing** (`SCR-XCT-01`). The fact the server branches on
is the same one step 4 already reads to decide whether to mint a token, so no new lookup is added.

**Why `No seats were held.` cannot simply be left to cover both.** On an extend it is a **false
statement about seats the customer is looking at**: their held cells are still drawn `held_by_me`, the
countdown is still running from the unchanged `expires_at`, the heading still reads `3 seats held by
you`, and `P-HLD-04` is still counting those three against their ten. The sentence would contradict
four things on the same screen. All-or-nothing is over **the seats the request names**, never over the
hold — `P-HLD-01`'s rollback set deliberately excludes keys the customer already owned, so a failed
extend cannot release them (`P-HLD-07`).

**Where the advice half also changes, and why.** Rows 2 and 3 end `press Hold these seats again`,
which is the primary action's label on a first hold. **In the extend state that control reads
`Hold 2 more seats` or `Hold 1 more seat`** (`SCR-SEA-01`), a label carrying an interpolated count, so
rows 2b and 3b say `try again` instead: a server-rendered sentence may not name a button label that
depends on how many seats the customer happens to have tapped.

**The substitution applies to the other seat-level rows on the hold endpoint too** — rows 11, 12, 20,
21, 22 and 23, the six `VALIDATION_FAILED` strings. A duplicate seat id or an out-of-service seat in a
request that extends a live hold is rejected before any lock is touched, so the existing hold is
untouched there for the same reason, and the clause reads `Your hold is unchanged.` Only rows 2 and 3
get their own published pair, because only those two also change their advice half; the six take the
clause substitution and nothing else. **Seventeen rows are unaffected** — 1, 4, 4b, 5, 6, 7, 8, 9,
10, 13, 14, 15, 16, 17, 18, 19 and 24. Rows 4 and 4b are at confirm, where the whole hold is being
bought and there is no extend to distinguish; **the other fifteen end with no such clause at all**, so
there is nothing to substitute. Rows 2b and 3b are the extend forms themselves and are not a further
case. **Eight affected, seventeen not, and both lists are written out rather than inferred**, because
the phrase "every seat-level message" is what produced the last gap in this table.

**Worked example — one extend, two seats lost.** A customer holds `J1`, `J2` and `J3` under token `T`
with `expires_at = 19:35:37`, and presses `Hold 2 more seats` for `C12` and `C13`. Both are taken
between the map render and the request:

```
step 4 finds a live hold on this showtime  ->  this is an EXTEND, not a first hold
seats named by this request                ->  C12, C13        (J1, J2, J3 are not named)
both SET NX return nil, neither key carries T
rollback set                               ->  {}              (nothing was won)
J1, J2, J3                                 ->  untouched; expires_at still 19:35:37
offending seats, in submission order       ->  C12, C13
count = 2, which is >= 2                   ->  the plural row (3b)
closing clause                             ->  "Your hold is unchanged."
message  ->  C12 and C13 were taken by another customer. Your hold is unchanged. Your other choices are still selected — change these two and try again.
```

**Expected answer: 409 `SEAT_UNAVAILABLE`, `details.unavailable_seats = ["C12","C13"]`, and a hold
still carrying exactly three seats.** Had the customer held nothing, the same run would take row 3 and
end `No seats were held.` instead — the only difference is the clause.

**Singular and plural, for every seat-level message: a rule, not a judgement.** `SEAT_UNAVAILABLE`
**at hold** always had an explicit pair (rows 2 and 3). Nothing else did. The three seat-level
`VALIDATION_FAILED` strings had only a singular, and so did **`SEAT_UNAVAILABLE` at confirm** — a row
whose own rule pointed at a partner that did not exist. **`SCR-XCT-01` rules that the server renders
`message` and the client never composes it**, so with two offending seats the server had no sentence
to send and would have had to emit a singular naming one seat while rejecting several, or a template
the client was forbidden to fill. **Rows 4b, 21, 22 and 23 close that, and every seat-level message
in this lane now has both forms.** The rule below governs all four pairs identically — **and it
governs rows 2b and 3b on the same terms**, which are the extend forms of rows 2 and 3 and are
themselves a singular and a plural:

- **Exactly one offending seat → the singular row.** Two or more → the plural row. The count is the
  number of *offending* seats, never the number of seats in the request: a five-seat request with one
  duplicate takes the singular.
- **Every offending seat is named**, in the order the client submitted them — not sorted, not
  truncated, not summarised as a count. A customer fixing a selection needs to know which seats to
  change, and a message naming two of three sends them back a second time.
- **Joined `A, B and C`**: comma-separated, with `and` before the last and no serial comma. The same
  joining `SEAT_UNAVAILABLE` row 3 already uses.
- The labels are the customer's seat labels from `details.unavailable_seats`-style structure, never
  internal ids, exactly as `P-HLD-07` requires.

**Worked example — two offending seats.** A request names `[C12, C13, C14, C12, C13]` on a showtime
whose hall has all three seats, **from a customer holding nothing on it** — so the closing clause is
the first-hold form. `C12` and `C13` are each listed twice, so **two** seats offend and the
plural is rendered in submission order:

```
offending seats, in submission order  ->  C12, C13
count = 2, which is >= 2              ->  the plural row (21)
joined                                ->  "C12 and C13"
message  ->  Seats C12 and C13 were listed more than once. Each seat can only be chosen once. No seats were held.
```

**With three**, the join is `C12, C13 and C14` and the sentence is otherwise identical. **With one** —
`[C12, C13, C12]` — the count is 1 and row 11's singular is rendered verbatim. **Had the same request
come from a customer already holding seats on this showtime**, everything above is unchanged except
the final clause, which reads `Your hold is unchanged.` — the two rules compose and neither
overrides the other. **The status and the
code do not change between singular and plural**; only the sentence does, and the interface branches
on `code` in both cases (`P-HLD-14`'s opening rule).

**There is no code for "a confirm is in flight".** A release racing a confirm is resolved by ordering
and returns either 200 or 409 `HOLD_EXPIRED` — never a code of its own (`P-HLD-08`).

**Server-side validation.** Every message above is a presentation string and none of them is branched
on. Every one of these codes needs a negative test asserting the code and the status, which is a direct
input to `docs/09 NegativeTesting/`.

**Worked example.** The `Retry-After` value in **row 16** is computed from the emptied bucket's refill
rate, never from a constant and never from the bucket's capacity. The bucket is `S7.4`'s **seat hold** row: 20 per minute per user and
60 per minute per real client IP. **Whichever of the two refused is the one the span is computed
from**, so both are derived here:

```
per user, 20 / 60 s   ->  refill 0.3333 tokens/s  ->  one token in 3 s   ->  Retry-After: 3
per IP,   60 / 60 s   ->  refill 1.0000 tokens/s  ->  one token in 1 s   ->  Retry-After: 1

3 < 120  ->  "3 seconds"                    S7.20
1 < 120  ->  "1 second"                     S7.20, the singular branch

message  ->  Too many attempts. Try again in 3 seconds.
         ->  Too many attempts. Try again in 1 second.
```

**The singular is a string this lane actually ships, not a defensive branch.** `S7.20` rule 4 names
the **per-IP seat-hold bucket** as one of only three buckets in the product whose refill is a second
or less, and that bucket is this lane's. So `Too many attempts. Try again in 1 second.` is published
copy of rows 11 and 16 whenever the per-IP bucket is the one that refused, and an implementation that
writes `"{n} seconds"` ships "1 seconds" on a real path here.

**The number in the message and the number in the header are the same value.** An earlier draft of
rows 11 and 16 published *"Try again in 20 seconds"*, which was the bucket's **capacity** copied into
a sentence that wants its **refill interval** — corrected here to agree with this arithmetic, which
this row already carried. The rendering of the span itself — the 120-second threshold, `m = ceil(seconds / 60)` above it, and
both singular forms — **is owned by `S7.20` for the whole document and is not restated here.** Every
span this lane publishes is under 120 seconds and therefore renders as seconds.

**Time formatting is no longer this lane's to decide, and the format did not change.** It was recorded
here as this lane's judgment call — Asia/Kolkata, `h:mm am/pm`, for example `7:45 pm` — because no
source specifies one. **`S7.19` now owns the rendering rule for the whole document and adopted exactly
that form**, so every `7:45 pm` above is unchanged and is now conformant rather than local. This row
still owns the *sentences*; it owns none of the *formats* inside them.

---

## S5 — UX specification

### `SCR-SEA-01` · The seat map and the price summary
**Route.** `/showtimes/{showtime_id}` · **Who reaches it.** guest, customer, manager, admin —
everyone; the map is public · **Component basis.** `COMPONENTS.md §1` (the seat map), `§2` (the
legend), `§5` (the price summary)

> **One screen, two halves. `SCR-SEA-01` and lane E1's `SCR-BRW-03` are the same screen at the same
> route, `/showtimes/{showtime_id}` — not two destinations and not two routes.** `SCR-BRW-03`
> specifies the **read path** on this screen: the layout that arrives, how it is drawn, how it
> refreshes and how stale it may be. This section specifies the **interactive layer on that same
> screen**: what a tap does, the price summary, the countdown, the hold and every way it fails.
> **There is no `/seats` route.** Where the two sections name the same element, the copy is the same
> string, converged deliberately — the sold-out banner and the poll-failure strip in particular; a
> variant found in either file is a defect, not a choice.

**What the user arrives with / leaves with.** They arrive with a showtime id and, if they came back
from signing in, a restored selection in `sessionStorage`. They leave with either a live hold — a hold
token, an `expires_at` and a total, all in `sessionStorage` — or nothing at all.

**Fields and controls.**

| Element | Token(s) | Behaviour | Validation |
|---|---|---|---|
| Map field | `--fr-surface-inset`, padding `--fr-space-4` | scrolls horizontally inside its own container; the page body never scrolls sideways | none |
| Screen bar and falloff | `--fr-screen-bar`, `--fr-radius-pill`, gradient from `--fr-screen-glow` | fixed at the top of the field; carries no state | none |
| `SCREEN` label | `--fr-ink-muted`, `--fr-text-xs`, `--fr-track-caps` | centred inside the falloff, below the bar | none |
| Row gutter | width `--fr-seat-gutter`, `--fr-font-mono`, `--fr-text-xs`, `--fr-ink-muted` | pinned left while the map scrolls | none |
| Seat cell, `available` | fill `--fr-seat-available`, 1px `--fr-seat-edge-available`, number in `--fr-seat-ink`, `--fr-seat-size` square, `--fr-radius-sm` | tappable; a tap adds it to the selection | client-side only; the hold endpoint is the enforcement point |
| Seat cell, `held_by_me` | fill `--fr-seat-mine`, 2px `--fr-seat-edge-mine`, tick in `--fr-seat-ink-mine` | tappable; a tap gives the seat back if it is held, or removes it from the selection if it is only chosen | `P-HLD-08` |
| Seat cell, `held_by_other` | fill `--fr-seat-held-other`, a solid horizontal bar in `--fr-seat-ink` | not tappable | none |
| Seat cell, `sold` | fill `--fr-seat-sold`, 45° hatching in `--fr-seat-ink` | not tappable | none |
| Seat cell, `is_active: false` | **no fill** — the field's `--fr-surface-inset` shows through — 1px **dashed** `--fr-rule`, number in `--fr-ink-muted` | **not tappable in any state, for any reader.** Drawn from this row rather than from its `state`, which stays truthful on the wire | `P-SEA-01` exceptions 4 and 5; the same treatment `SCR-BRW-03` publishes |
| Band gap and band rule | `--fr-seat-band-gap`, 1px dashed `--fr-rule` | separates category bands; category is never a colour. **Drawn only between two adjacent bands**, per `P-BRW-16`, which owns the derivation | none |
| Legend | container `--fr-surface-raised`, `--fr-radius-md`, padding `--fr-space-3`, labels `--fr-text-sm` `--fr-ink`, prices `--fr-font-mono` `--fr-ink-strong`, divider `--fr-rule-quiet` | always visible, never collapsed; each swatch is the real cell at the real size | none |
| Price summary panel | `--fr-surface-raised`, `--fr-radius-lg`, `--fr-shadow-card`, padding `--fr-space-4` | under the map on a phone, beside it above 40rem | none |
| Chosen / held heading | `--fr-screen-ink`, `--fr-text-sm`, `--fr-weight-medium` | reads `3 seats chosen` before a hold and `3 seats held by you` after one. **While a hold is live and further seats are chosen, the heading keeps naming the held count and a second subheading names the chosen count**, so the two groups are never summed into one number that is true of neither. **Every number here is an interpolated count and each has a singular and a plural form published below** | none |
| Seat line | `--fr-font-mono`, `--fr-text-sm`, `--fr-ink`; category note `--fr-text-xs` `--fr-ink-muted` | one line per selected seat, with its own price | none |
| Perforation | dashed 1px `--fr-rule`, `--fr-space-3` clear above and below | marks the tear between what you chose and what you owe | none |
| Total | label `--fr-text-sm` `--fr-ink-muted` `--fr-track-caps`; figure `--fr-font-mono` `--fr-text-xl` `--fr-weight-bold` `--fr-ink-strong` | `P-SEA-04`; absent entirely when any price is unknown | none |
| Seat cap note | `--fr-text-xs`, `--fr-ink-muted` | reads `Up to 10 seats.` | `P-HLD-04` |
| Primary action | fill `--fr-surface-accent`, `--fr-ink-on-accent`, `--fr-radius-md`, min height `--fr-tap-min`, `--fr-weight-bold` | copy depends on the reader, below. **Once a hold is live with nothing further chosen it is a navigation control, not a pay control**: it routes to `/showtimes/{showtime_id}/checkout` and issues no request. **With a hold live and further seats chosen it becomes a request control again** — `Hold n more seat(s)`, re-sending `EP-HLD-01` for the new seats only | `P-HLD-01`, `P-HLD-05` |
| Secondary action | transparent, 1px `--fr-control-edge`, `--fr-accent-ink` | reads `Give up these seats`; present only while a hold is live | `P-HLD-08` |

**There is no tax line, no discount field and no booking fee, and no space is left for one.** There is
no manual refresh control.

**Both seat-count headings are published in a singular and a plural, and one of them ships.** The
number in `3 seats chosen` and `3 seats held by you` is a **count**, interpolated at render time —
never a literal — and a selection of one seat is not an edge case but the ordinary way most bookings
begin: a customer taps one seat before they tap a second. An implementer who finds only the plural
writes `{n} seats chosen` and ships `1 seats chosen` on the first tap of nearly every session. **This
is the same failure `S7.20` rule 4 spends a paragraph on for durations**, one field over, and the same
remedy: publish both forms so neither is inferred. The counts in `P-HLD-14` rows 7 and 8 —
`You are holding 6 and chose 5 more.` — are interpolated on the same terms; those two sentences carry
no noun that inflects, so they need no second form.

**The sales-closed banner names no time, and the `409` body does — deliberately, and they are
different surfaces.** This screen and lane E1's `SCR-BRW-03` are the same screen at the same route and
both assert their shared strings are byte-identical, so a banner that differed between them was a
defect by their own rule. `P-BRW-07` exception 1 publishes `Sales for this showtime have closed.`, it
is rank 2 and both screens are rank 3, so **that string ships and this screen's former time-naming
variant is gone.** What is **not** touched is `P-HLD-14` row 9's longer body,
`Sales for this showtime closed at 7:45 pm. Choose another showtime.` — that is the `409`
`SALES_CLOSED` answer to a hold *attempt*, a different surface with a different job: it explains a
refusal that just happened and tells the customer what to do next, and naming the instant is the
useful part of it. **A banner states a standing condition the customer can see for themselves; an
error explains a refused action.** The difference is intended and is written down so the next reader
does not converge them.

**Seats may be added to a live hold, and this screen is where that happens.** `P-HLD-01` step 4
acquires further seats under the **existing** token, and `P-HLD-11` spends a worked example on the
money consequence — a hold legitimately carrying two base prices, `J1 ₹333.33`, `J2 ₹333.33`,
`J3 ₹399.99`. **Until now this screen published no state in which a customer could choose a further
seat while holding one**, so that path could not be reached from the product and `P-HLD-11`'s example
could never occur. The state and its labels are published above. Two tie-breaks apply and are stated
here because the ranking does not reach them on its own: **behaviour outranks rendering on whether a
capability exists** (`S1.2.1` case 4), so a P-row describing the act settles that the act exists; and
**the screen owns a string no P-row publishes** (case 3), so these labels are this section's.

**What the total shows while further seats are chosen, and the one thing it must not claim.** The
`TOTAL` figure is the sum of the **held** seats' snapshotted prices plus the **chosen** seats' prices
as the map currently carries them. The chosen portion is **indicative until the extend succeeds**: it
is priced at whatever base is current when the extend request runs, not at the base that produced the
held prices, which is exactly what `P-HLD-11`'s two-base-price example describes. **Only the held
portion is price-protected**, because price protection is a property of a hold and those seats are not
held yet. The seat lines carry their own prices in both groups, so the figure the customer reads always
adds up from what is on screen — the property `P-SEA-04` requires — and `Continue to payment` is
reachable only when nothing further is chosen, so **the total on the checkout screen is never a total
that included an unheld seat.**

**This screen has no pay action, and the post-hold primary action is not one.** It reads
`Continue to payment` and it navigates to `SCR-PAY-01` at `/showtimes/{showtime_id}/checkout`; it
sends no request, captures nothing and cannot fail. **`SCR-PAY-01` is the only screen in the product
that carries a control which submits a payment**, and that screen says the same thing from its own
side. An earlier draft labelled this control `Pay ₹1,562.49`, which read as a pay action on a screen
that has none — the amount is already on the line directly above it, as `TOTAL` `₹1,562.49`, so
nothing is lost by removing it from the button and one screen stops claiming a capability it does not
have.

**States.**

| State | What renders |
|---|---|
| **Empty** (no seats chosen) | The map at full size. The summary panel stays at full height with the total at `₹0.00` and the note `Up to 10 seats.` A panel that appears and disappears makes the page jump under a thumb. |
| **Loading** | The field, the screen bar and the row gutters draw immediately at full size, with seat cells as `--fr-surface-inset` blocks at 60% opacity. The frame never resizes when the data lands. No spinner: the layout is the answer. Prices render as `--fr-surface-inset` blocks and the primary action is disabled. |
| **Error, first load** | The map is replaced by `The seat map could not be loaded.` in `--fr-ink` on `--fr-surface-inset`, with a control reading `Try again`. No partial grid. |
| **Error, a poll fails** | The last good map stays on screen. A one-line strip appears at the top of the field in `--fr-ink-muted` on `--fr-surface-inset` reading `The seat map is not updating. The seats shown may be out of date.` Polling keeps retrying. |
| **Success** (a hold is granted) | Every held cell repaints to `held_by_me`, the heading changes to `3 seats held by you`, the countdown (`SCR-SEA-02`) appears, the secondary action appears, and the primary action becomes `Continue to payment`. Pressing it navigates to `/showtimes/{showtime_id}/checkout` and sends no request of its own. |
| **Hold live, further seats chosen** | A hold is live **and** the customer has tapped one or more additional `available` seats. The held cells stay `held_by_me`; the newly chosen cells render `held_by_me` too (`P-SEA-02` — there is no fifth rendering) and are listed under their own subheading in the summary. The countdown keeps running from the **unchanged** `expires_at` and does not restart. **The primary action changes from `Continue to payment` to `Hold 2 more seats`**; pressing it re-sends `EP-HLD-01` naming only the new seats, which join the existing hold under its existing token (`P-HLD-01` step 4). On success the newly chosen seats become held, the subheading disappears, and the primary action returns to `Continue to payment`. On `409 SEAT_UNAVAILABLE` the existing hold is untouched — the request is all-or-nothing over **the seats it names**, not over the whole hold (`P-HLD-07`) — and the banner renders `P-HLD-14` row **2b** or **3b**, whose closing clause is `Your hold is unchanged.` and never `No seats were held.`, because on this screen in this state the countdown, the held cells and the heading all say otherwise. |
| **A chosen seat leaves the selection with no request sent** | The local selection has been re-checked against a freshly fetched map — after a reload, a poll, or a return to the tab, **with no sign-in involved** — and a seat that was chosen is no longer `available`. The cell repaints to whatever the map now reports and fires the changed-seat outline; the seat leaves the selection, its line leaves the summary and the total drops. **`SCR-SEA-03` renders `P-SEA-03`'s string and announces it**, and this is the one notice on that banner that carries no error `code`, because nothing was requested. Nothing is disabled and no action is offered: the customer chooses another seat or presses the primary action with what is left. The return-from-sign-in case is `P-ACC-13`'s and renders that row's string in the same banner. |
| **Partial** | The map and the price summary load independently. The map is usable before the prices arrive; the total is not rendered at all and the primary action stays disabled until every selected seat has a price. |
| **Sold out** | The full map renders, every cell `sold`, plus a banner reading `Every seat for this showtime is sold.` Not an empty state — the customer wants to see that it is genuinely full. |
| **Sales closed** | The full map renders with every cell unselectable, plus a banner. For a customer with no hold it reads `Sales for this showtime have closed.` For a customer holding seats it reads `Sales for this showtime have closed. You can still pay for the seats you are holding.` |
| **Hold expired** | Each `held_by_me` cell reverts to whatever the next poll reports — usually `available`, sometimes `held_by_other` or `sold`. Each reverting cell fires the changed-seat outline, so the customer watches the seats leave. The cells are **not** pre-emptively repainted at `0:00`; `SCR-SEA-02` is what says the hold ended. |
| **A seat changes between two polls** | The cell keeps a 2px `--fr-focus-ring` outline for `--fr-motion-change`; the fill transitions over `--fr-motion-base` with `--fr-ease-out`. Under `prefers-reduced-motion` the outline is static rather than pulsing and is held for the same duration. **`SCR-SEA-03` fires and names the seat only when the change took a seat away from this customer** — a seat in their local selection, which is the state above, or a seat they were holding. A seat changing anywhere else on a 220-seat map repaints silently and is never announced. |

**Copy.**

| Where | Verbatim |
|---|---|
| Primary action, guest | `Sign in to hold these seats` |
| Primary action, customer, nothing chosen (disabled) | `Choose seats` |
| Primary action, customer, seats chosen | `Hold these seats` |
| Primary action, customer, hold live, **nothing further chosen** | `Continue to payment` |
| Primary action, customer, hold live, **two or more further seats chosen** | `Hold 2 more seats` — `2` renders the count of newly chosen seats, never the size of the hold |
| Primary action, customer, hold live, **exactly one further seat chosen** | `Hold 1 more seat` |
| Summary subheading, **two or more further seats chosen** | `2 more chosen` |
| Summary subheading, **exactly one further seat chosen** | `1 more chosen` |
| Secondary action, hold live | `Give up these seats` |
| Heading, before a hold, **two or more** seats | `3 seats chosen` — `3` renders the count |
| Heading, before a hold, **exactly one** seat | `1 seat chosen` |
| Heading, after a hold, **two or more** seats | `3 seats held by you` — `3` renders the count |
| Heading, after a hold, **exactly one** seat | `1 seat held by you` |
| Seat cap note | `Up to 10 seats.` — the number renders `MAX_SEATS_PER_BOOKING`; a literal `10` is a defect (`P-HLD-04`) |
| Total label | `TOTAL` |
| Empty total | `₹0.00` |
| Sold-out banner | `Every seat for this showtime is sold.` |
| Sales-closed banner, no hold | `Sales for this showtime have closed.` — `P-BRW-07` exception 1 publishes this string and this screen renders it; see the note below |
| Sales-closed banner, holding seats | `Sales for this showtime have closed. You can still pay for the seats you are holding.` |
| Map first-load failure | `The seat map could not be loaded.` |
| Map first-load retry control | `Try again` |
| Poll-failure strip | `The seat map is not updating. The seats shown may be out of date.` |
| A chosen seat has gone, on a local refresh with no sign-in involved | `C12 is no longer available. It has been removed from your choices.` — `P-SEA-03` owns it |
| A chosen seat has gone while the customer was signing in or registering | **Rendered from `P-ACC-13` (lane E5). Not restated here** |
| Legend, every label | **Rendered from `SCR-BRW-03` (lane E1), which publishes all five swatch labels and the category-row form. Not restated here** — `SCR-BRW-03` and this section are the same screen at the same route, and the legend belongs to its read-path half |
| A held seat is submitted while out of service | `Seat C12 is out of service. No seats were held.` — the set this belongs to is `P-HLD-14`'s, row 20 |

**Accessibility.** The map is **one tab stop, not 220**; arrow keys move within the grid and Enter or
Space selects. A grid of 220 tab stops is a keyboard trap with extra steps, not keyboard support. Each
seat carries an accessible name stating identity, category and state — `Row C seat 12, Premium,
available`, and `Row C seat 12, Premium, held by you` for `held_by_me`, where the number stays in the
name even though the tick has replaced it visually. An out-of-service seat reads `Row C seat 12,
Premium, out of service`, keeps its place in the arrow-key grid so the geometry does not shift under a
reader who has learned it, and never activates on Enter or Space. Every state is told apart by fill
lightness, by a mark and by a border; **colour is never the carrier**, and the out-of-service cue is
the dashed border rather than a fifth glyph, because the four glyph slots — none, bar, hatch, tick —
are already spent. Focus order is map, then legend, then summary
heading, then seat lines, then total, then primary action, then secondary action. Focus is drawn with
`--fr-focus-ring`. Seat cells are `--fr-seat-size` square, which is 24px and the WCAG 2.2 target-size
minimum; the seat is never shrunk to avoid the horizontal scroll. The primary and secondary actions are
at least `--fr-tap-min` tall. Seat-state changes announce through a live region only when they affect
the customer's own seats; a 220-seat map announcing every poll would be unusable.

---

### `SCR-SEA-02` · The hold countdown
**Route.** rendered inside `/showtimes/{showtime_id}` — the one seat-map screen — and **repeated,
unchanged, on lane E3's checkout screen** · **Who reaches it.** the hold's owner only ·
**Component basis.** `COMPONENTS.md §7`

> **This specification is the single source for this component's label and its states.** The same
> component is rendered on the checkout screen; that is a repetition of this component, not a second
> one, and lane E3 specifies no label, no state and no wording for it. Any copy for the countdown that
> differs from the table below — a different label, a different zero state — is a defect in the other
> document, resolved by taking this one.

**What the user arrives with / leaves with.** It arrives with one input: the hold's `expires_at`, plus
the current instant supplied to it. It never reads the wall clock itself. It leaves the customer either
paying or back on the map.

**Fields and controls.**

| Element | Token(s) | Behaviour | Validation |
|---|---|---|---|
| Digits | `--fr-font-mono`, `--fr-text-xl`, `--fr-weight-bold`, `--fr-countdown-fill`, `font-variant-numeric: tabular-nums` | `m:ss`, counted down from `expires_at` | never negative; the zero state renders instead |
| Label | `--fr-text-xs`, `--fr-ink-muted`, uppercase, `--fr-track-caps` | reads `TIME LEFT` | none |
| Track | `--fr-surface-inset`, 4px tall, `--fr-radius-pill` | the full duration | none |
| Bar | `--fr-countdown-fill`, shrinking left to right | **the primary carrier** — it works with colour removed | none |
| Bar and digits, last 60 seconds | `--fr-countdown-urgent` | one threshold only, never 60/30/10 | none |
| Warning line | `--fr-text-sm`, `--fr-ink` | appears at the threshold, announced once | none |

**States.**

| State | What renders |
|---|---|
| **Empty** (no hold) | The component is absent entirely, not collapsed to zero height. |
| **Loading** | Cannot occur. The component only exists once a hold response has arrived carrying `expires_at`. |
| **Live** | Digits, bar and label. |
| **Last 60 seconds** | As live, plus the warning line, plus the two colour changes, announced once. |
| **Zero, no confirm in flight** | The countdown stops at `0:00`, the payment action is disabled, and the component states that the hold ended. It does **not** claim the seats are free, and it does **not** name a cause: reaching `0:00` is also what a graceful-shutdown release (`P-HLD-12`) and a key re-acquired by someone else (`P-HLD-03`) look like from inside the browser, and the client cannot tell the three apart. "Your three minutes are up" would therefore be a false statement in two of the three cases, which is why the copy below says only that the hold ended. |
| **Zero, a confirm in flight** | The busy state is kept and the request is not cancelled, because a request already sent cannot be un-sent. The component states that the hold has ended and that an answer is still coming. It names no cause, exactly as the other zero state does not. |
| **Error** | The component itself carries no error. `SCR-SEA-03` carries every message. |
| **Partial** | Not applicable — a hold either exists with an `expires_at` or does not. |
| **Clock skew** | If `expires_at` is already past on arrival, the zero state renders immediately. No negative numbers, ever. |

**Copy.**

| Where | Verbatim |
|---|---|
| Label | `TIME LEFT` |
| Warning at 60 seconds | `Less than a minute left. At 0:00 your seats are released and you will need to choose them again.` |
| Zero, no confirm in flight | `Your hold has ended and your seats have been released. You have not been charged.` |
| Zero, a confirm in flight | `Your hold has ended. We are waiting for the answer to your payment. Do not close this page.` |

> **⚠ Both zero states name no cause, and that is now true of the in-flight one as well.** An earlier
> draft of this box claimed the in-flight zero state still read *"Your three minutes are up"*. **It does
> not, and had not since the copy above was generalised** — the box was left behind by that edit and is
> corrected here. The copy table is the authority: the in-flight state reads `Your hold has ended. We
> are waiting for the answer to your payment. Do not close this page.`, which names the fact and not the
> reason, for the same argument that removed the clause from the other zero state — a shutdown drain
> (`P-HLD-12`) and a key re-acquired by someone else (`P-HLD-03`) reach `0:00` identically and the
> client cannot tell the three apart. **The three places that carry this string — this copy table,
> `P-HLD-09` exception path 3, and the `held_by_me_paying` + `HOLD_TTL_EXPIRE` transition in the seat
> lifecycle state machine — are byte-for-byte identical today and change together if they change at
> all.** There is no open wording item on this component.

**Accessibility.** The digits are **not** a live region — a value announced every second is unusable.
Only two events announce: the 60-second threshold, once, and the zero state, once. The bar carries the
same information as the colour, so the urgent state is legible with colour removed. The component is
not focusable and is not a control.

---

### `SCR-SEA-03` · The seat-lost and hold-failure banner
**Route.** rendered inside `/showtimes/{showtime_id}`, **pinned to the top of the viewport for as long
as it is live** — *not* inside the map's scroll container · **Who reaches it.** anyone who hits a
failure on this lane, and anyone who loses a chosen seat with no request sent · **Component basis.**
`COMPONENTS.md §6`

**What the user arrives with / leaves with.** It arrives with one error envelope, **or with one
client-originated seat-lost event that has no envelope at all**. It leaves the customer knowing
exactly which seats went and what to press next.

**Where this banner sits, and why it is not where `COMPONENTS.md §6` puts it.** `COMPONENTS.md §6`
places it *"inside the scroll container's sticky header area, so it is visible without scrolling"*.
**On this screen that placement cannot deliver what it promises**, for a reason `COMPONENTS.md §1.3`
states two sections earlier: the map container scrolls **horizontally and deliberately not
vertically** — *"rows grow the container and the page scrolls normally"* — so a header sticky inside
it is sticky against the one axis nobody is scrolling. On the design target `P-XCT-25` is written
about, a 220-seat hall on a 375-pixel phone, the customer reading the far rows has scrolled the
**page** past the banner's anchor, and the message naming the seat they just lost is off-screen.

**It cannot ride on the application header either.** `SCR-XCT-05` marks that header **`Not sticky`**
and gives the reason by name: a sticky header steals vertical space from exactly this map. That
ruling is not disturbed here and this banner is not an exception to it, **because a banner is not a
header**: it exists only while a message is live, is removed with it, and therefore costs the map no
vertical space in the state `P-XCT-25` is about. **The asymmetry — permanent chrome may not pin,
a transient message may — is the whole of the difference**, and it is written down so the next reader
does not read this row as overturning `SCR-XCT-05`.

**So: the banner renders in the page flow directly above the map field, and pins to the top of the
viewport while it is live**, below where the application header sits in the flow. It **reserves its
own height rather than overlaying the map**, so it can never obscure a focused seat cell
(WCAG 2.2 SC 2.4.11). When it is dismissed or replaced, the space is released and the map returns to
full height. **The `SCR-XCT-01` registry's generic "the sticky header area of the surface it belongs
to" does not govern this surface** — `S1.2.1` case 6, the screen that owns the surface wins and the
registry defers to it by name.

**Fields and controls.**

| Element | Token(s) | Behaviour | Validation |
|---|---|---|---|
| Container | `--fr-surface-danger`, `--fr-radius-md`, padding `--fr-space-3`, 1px `--fr-control-edge` | slides in over `--fr-motion-base` with `--fr-ease-out`; **pinned to the top of the viewport while live, in the page's own scroll context and not the map container's**, so it stays visible at any page scroll position. It reserves height rather than overlaying | none |
| Leading rule | 3px `--fr-danger-ink` down the leading edge | none | none |
| Message | `--fr-ink-on-danger`, `--fr-text-sm`, `--fr-leading-body` | the verbatim string for the `code` — **or, for the one codeless event below, `P-SEA-03`'s or `P-ACC-13`'s verbatim string** | none |
| Seat names inside the message | `--fr-font-mono`, `--fr-weight-bold` | taken from `details.unavailable_seats` | none |
| Action inside the banner | `--fr-accent-ink`, underlined | present only where there is something to press | none |
| Request id line | `--fr-text-xs`, `--fr-ink-muted`, `--fr-font-mono` | **5xx only** | none |

**States.**

| State | What renders |
|---|---|
| **Empty** | Nothing. The banner is absent, not collapsed to zero height. |
| **Loading** | Not applicable — a banner is the answer to a request that has already returned, or to an event that needed none. |
| **Error** | One banner, carrying the message for the `code`. |
| **Seat lost with no request sent** | One banner, carrying `P-SEA-03`'s verbatim string `C12 is no longer available. It has been removed from your choices.` **This state carries no error `code`**, because nothing was requested and nothing answered — a poll, a reload or a return to the tab re-checked the local selection against a fresh map and a chosen seat had gone. Announced through the live region exactly as an error is. **No in-banner action, and dismissible**, because the seat has already left the selection and the total has already dropped: there is nothing to press. The return-from-sign-in variant renders `P-ACC-13`'s string in this same banner on the same terms. |
| **Success** | Not applicable — the banner never reports success. |
| **Partial** | Not applicable. |
| **Several errors at once** | **One banner.** The newest message replaces the previous one; errors never stack into a wall. A codeless seat-lost notice and an error compete on the same terms: newest wins. |
| **Dismiss** | Only messages with nothing left to do are dismissible. `SEAT_UNAVAILABLE` is not; it clears when the customer changes the selection. |

**Copy.** The message text for every code is `P-HLD-14`'s table and this screen restates none of it.
**The one message this banner carries that is not in that table is the codeless seat-lost notice**,
whose two strings are `P-SEA-03`'s and `P-ACC-13`'s and are likewise not restated here.
**The banner's own two controls are this screen's to publish, and it publishes them here** — a screen
that names a control owes that control's words, and this screen named both and published neither
until now:

| Where | Verbatim |
|---|---|
| The in-banner action, on `DEPENDENCY_UNAVAILABLE` — the only code that carries one | `Try again` |
| The in-banner action, accessible name | `Try again — reload the seat map` |
| The dismiss control, on a dismissible banner | `Dismiss` |
| The dismiss control, accessible name | `Dismiss this message` |

**`SCR-XCT-01` publishes a `Choose seats again` action against `HOLD_EXPIRED`; on this surface there
is none, and this row is the one that governs.** Both are rank 3, so `S1.2` alone does not separate
them — the rule that does is that **the screen owning a surface beats the cross-cutting registry for
that surface**, and the seat map is this section's. The reason is concrete rather than jurisdictional:
**a customer meeting `HOLD_EXPIRED` on the seat map is already on the screen that button would send
them to.** The control navigates nowhere. What actually happens here is automatic — the previous
selection re-applies and the map refreshes — so a button would be offering to do a thing that has
already been done, and pressing it would be indistinguishable from pressing nothing.
`SCR-XCT-01`'s action stands for every surface that is **not** the seat map and **not** `SCR-PAY-01`,
and defers to each of them by name; `SCR-PAY-01` settles the same fork on its own side for the same
reason.

**Exactly one code carries an in-banner action, and the rest carry none on purpose.**
`DEPENDENCY_UNAVAILABLE` is the only failure on this lane whose remedy is *repeating the same request*
— Redis returns and the identical action succeeds — so it is the only one where a control inside the
banner does something the customer could not do more directly. `Try again` is the string this screen
family already publishes for the map's first-load failure, reused rather than reworded, because two
words for one act is how the next variant starts. For every other code the next step is on the map
itself: `SEAT_UNAVAILABLE` wants a different seat chosen, `SEAT_LIMIT_EXCEEDED` wants one deselected,
`HOLD_EXPIRED` and `HOLD_NOT_OWNED` re-apply the selection automatically, and `SALES_CLOSED` has no
next step at all. A banner button that only scrolls the customer back to where they already are is a
control with nothing to do, which is what the "present only where there is something to press" rule in
the table above exists to prevent.

**Dismissible means: nothing left to do.** `INTERNAL_ERROR` and `NOT_FOUND` are dismissible —
the customer has read them and no action follows. `SEAT_UNAVAILABLE` is not, and clears itself when
the selection changes. `DEPENDENCY_UNAVAILABLE` is not, because it carries an action.

**The behaviour per code:**

| Code | What the banner does |
|---|---|
| `SEAT_UNAVAILABLE` | Names the lost seats from `details.unavailable_seats`, marks them unavailable on the map immediately, and keeps the rest of the selection |
| `HOLD_EXPIRED`, `HOLD_NOT_OWNED` | Returns the customer to the map with the previous selection re-applied and the map refreshed. **No action and not dismissible** — the return is automatic and the customer is already on the destination screen |
| `SEAT_LIMIT_EXCEEDED` | States the cap of ten and how many are currently held and chosen |
| `SALES_CLOSED` | Disables the map and states that sales for this showtime have closed |
| `VALIDATION_FAILED` | Names the specific problem with the selection |
| `RATE_LIMITED` | States that too many attempts were made and gives the wait, computed from `Retry-After` and rendered by **S7.20**. The banner renders the string `P-HLD-14` row 16 publishes; it formats nothing itself |
| `DEPENDENCY_UNAVAILABLE` | States that seat holds are unavailable and that browsing still works. It never silently degrades. **Carries the `Try again` action; not dismissible** |
| `NOT_FOUND` | States that the showtime could not be found. **No action; dismissible** |
| `INTERNAL_ERROR` | The message plus the request id line. **No action; dismissible** |
| **(no code — a chosen seat left the selection)** | Names the seat and states it has been removed from the customer's choices. The cell has already repainted to whatever the map now reports. **No action; dismissible.** This is the only row here not keyed by an error code, and it is listed in this table so a developer reading it top to bottom finds the event rather than concluding the banner has no trigger for it |

**Accessibility.** The banner is announced through a live region — **an error that is only red has not
been reported**, and **neither has a seat that silently left a selection.** The live region carries
the codeless notice on exactly the same terms as an error, which is the whole reason that state is
specified: the announcement route on this screen branched on an error `code`, and the one event a
screen-reader user most needs to hear about does not carry one. It receives focus when it carries an
action. The seat names inside the message are plain text in `--fr-font-mono`, not links. The request
id is selectable text so it can be copied. Because the banner is pinned to the viewport and reserves
its own height, a seat cell that has keyboard focus is never covered by it.

---

## S6 — API endpoints

The hold endpoint is the first authenticated action in the product and the point at which scarcity is
consumed. It takes a set of seats for one showtime and either locks all of them or none of them,
returning a token, an absolute expiry instant and the prices that were current at that moment.

```endpoint
{
  "id": "EP-HLD-01",
  "method": "POST",
  "path": "/api/showtimes/{showtime_id}/holds",
  "summary": "Hold a set of seats for this showtime, all or nothing",
  "auth": "role",
  "roles": ["customer", "manager", "admin"],
  "request": {
    "path_params": {"showtime_id": "integer, positive"},
    "query": {},
    "headers": {},
    "body": {"seat_ids": "array of integer, 1..10, unique, every element a member of THIS SHOWTIME'S SEAT SET (the set materialised at showtime creation, P-ADM-14 - not the screen's current seats, which differ for any seat added to the hall after this showtime existed) AND active (is_active true), required"}
  },
  "responses": {
    "201": {"description": "Every seat named in this request was locked. The body carries the WHOLE hold, not only the seats this request added - a request that extended an existing hold returns every seat under that token. The hold is live until expires_at.", "body": {"hold_token": "string, opaque, exactly 43 characters from the URL-safe base64 alphabet, required", "showtime_id": "integer", "expires_at": "string, ISO-8601 instant in UTC with milliseconds - an ARITHMETIC instant driving the countdown, never rendered as a wall-clock time, so it stays UTC (contrast the showtime instants of D6)", "seats": "array of {seat_id: integer, label: string, category: string, price_paise: integer} - EVERY seat under this token, each carrying the price it was given when IT entered the hold; extending a hold reprices nothing, so one hold may legitimately carry seats priced from two different base prices (P-HLD-11)", "total_paise": "integer, the sum of the already-rounded per-seat prices of EVERY seat in the hold - equal to what confirm will charge"}},
    "401": {"description": "No authenticated customer. A guest is stopped here, not at payment."},
    "404": {"description": "No such showtime."},
    "409": {"description": "One or more seats are held or sold, or sales for this showtime have closed. Zero seats are held afterwards."},
    "422": {"description": "The body is invalid, or a named seat is not in this showtime's seat set (P-ADM-14), or a named seat is out of service (is_active false), or the request would take this customer over ten seats on this showtime. Checked before any lock is touched, so zero seats are held afterwards."},
    "429": {"description": "The per-user or per-IP token bucket is empty."},
    "500": {"description": "Unhandled failure. The request id is shown to the customer."},
    "503": {"description": "Redis is unreachable. The hold path fails loudly and never falls back to the database for locks."}
  },
  "errors": ["AUTH_REQUIRED", "SEAT_UNAVAILABLE", "SALES_CLOSED", "SEAT_LIMIT_EXCEEDED", "VALIDATION_FAILED", "NOT_FOUND", "RATE_LIMITED", "DEPENDENCY_UNAVAILABLE", "INTERNAL_ERROR"],
  "idempotency": "not idempotent, and deliberately so. A repeat naming the same seats this customer already holds is a no-op that succeeds and does NOT extend the TTL; a repeat naming any other seat ADDS those seats to the SAME hold under the SAME token (P-HLD-01), which is why a customer has exactly one live hold per showtime and the ten-seat cap is counted against that one hold. There is never a second token for one showtime.",
  "rate_limit": "seat hold bucket: 20 per minute per user and 60 per minute per real client IP, both in Redis, both must have a token. Fails closed with 503 when Redis is unreachable.",
  "authorisation_rule": "The router dependency admits any authenticated principal holding an existing user row; no role is excluded and no check appears inside the handler. FR-ADR-014 requires only that a booking belong to a registered user, and no source refuses a manager a ticket - see PROPOSED-MGRBOOK-01.",
  "satisfies": ["P-HLD-01", "P-HLD-02", "P-HLD-04", "P-HLD-05", "P-HLD-06", "P-HLD-10", "P-HLD-11", "P-HLD-12", "P-HLD-13", "P-SEA-01"],
  "brd": ["R-HOLD-01", "R-HOLD-02", "R-HOLD-04", "R-HOLD-05", "R-HOLD-06", "R-HOLD-07", "R-QLY-01"]
}
```

A page that is reloaded mid-checkout has its hold token in `sessionStorage` but nothing else. This
endpoint gives the restored page back its seats, its prices and the same expiry instant it started
with, so a refresh costs the customer no time.

```endpoint
{
  "id": "EP-HLD-02",
  "method": "GET",
  "path": "/api/holds/{hold_token}",
  "summary": "Read a live hold so a reloaded page can restore itself",
  "auth": "role",
  "roles": ["customer", "manager", "admin"],
  "request": {
    "path_params": {"hold_token": "string, opaque, exactly 43 characters from the URL-safe base64 alphabet, required"},
    "query": {},
    "headers": {},
    "body": {}
  },
  "responses": {
    "200": {"description": "The hold is live.", "body": {"hold_token": "string", "showtime_id": "integer", "expires_at": "string, ISO-8601 instant in UTC with milliseconds, unchanged from acquisition", "seats": "array of {seat_id: integer, label: string, category: string, price_paise: integer} - EVERY seat under this token", "total_paise": "integer, the sum over every seat in the hold"}},
    "400": {"description": "The hold token is malformed - not exactly 43 characters, or carrying a character outside the URL-safe base64 alphabet. Checked before Redis is touched. This is REQUEST_INVALID and never HOLD_EXPIRED: a token that could never have been issued names no hold that ever existed, and telling the customer their hold ended would be a false statement about something that never happened (P-HLD-03)."},
    "401": {"description": "No authenticated customer."},
    "403": {"description": "The token exists but belongs to another user."},
    "409": {"description": "The hold has expired. The seats have been released."},
    "429": {"description": "The per-user or per-IP token bucket is empty."},
    "503": {"description": "Redis is unreachable."}
  },
  "errors": ["REQUEST_INVALID", "AUTH_REQUIRED", "HOLD_NOT_OWNED", "HOLD_EXPIRED", "RATE_LIMITED", "DEPENDENCY_UNAVAILABLE", "INTERNAL_ERROR"],
  "idempotency": "safe method - no state change",
  "rate_limit": "seat hold bucket: 20 per minute per user and 60 per minute per real client IP.",
  "authorisation_rule": "The router dependency admits any authenticated principal holding an existing user row - no role is excluded - and the handler's first act asserts the hold record's user_id equals the caller's - the token alone never grants access, which is what makes it safe for the token to appear in a path and therefore in an access log.",
  "satisfies": ["P-HLD-03", "P-HLD-09", "P-HLD-11"],
  "brd": ["R-HOLD-02", "R-HOLD-03"]
}
```

Tapping a seat the customer is holding gives that one seat back. The rest of the hold survives with the
same expiry instant, so giving a seat back never buys more time on the others.

```endpoint
{
  "id": "EP-HLD-03",
  "method": "DELETE",
  "path": "/api/holds/{hold_token}/seats/{seat_id}",
  "summary": "Release one seat from a live hold, keeping the rest",
  "auth": "role",
  "roles": ["customer", "manager", "admin"],
  "request": {
    "path_params": {"hold_token": "string, opaque, exactly 43 characters from the URL-safe base64 alphabet, required", "seat_id": "integer, positive, must be a member of this hold's seat set"},
    "query": {},
    "headers": {},
    "body": {}
  },
  "responses": {
    "200": {"description": "The seat was released. The remaining hold is returned with its unchanged expires_at. An empty seats array means the hold has ended. P-HLD-08's eight numbered steps are the procedure and the block does not repeat them; two are easy to miss and neither is optional - step 6 DEL cache:seatmap:{showtime_id} AFTER the lock release, and step 8, which on the LAST seat also removes the token from holds:user:{user_id}:showtime:{showtime_id} so P-HLD-04's cap stops counting a hold that has ended.", "body": {"hold_token": "string", "showtime_id": "integer", "expires_at": "string, ISO-8601 instant in UTC, unchanged", "seats": "array of {seat_id: integer, label: string, category: string, price_paise: integer}", "total_paise": "integer"}},
    "401": {"description": "No authenticated customer."},
    "403": {"description": "The token belongs to another user."},
    "409": {"description": "The hold has already expired. A confirm in flight for the same hold does not refuse the release: the ordering settles it, per P-HLD-08."},
    "400": {"description": "The hold token is malformed - not exactly 43 characters, or carrying a character outside the URL-safe base64 alphabet. Checked before Redis is touched. REQUEST_INVALID, never HOLD_EXPIRED, for the reason given on EP-HLD-02."},
    "422": {"description": "The token is WELL FORMED and the hold exists, but the named seat is not a member of its seat set. VALIDATION_FAILED. This is the only 422 on this endpoint and it never covers a malformed token - a token of the wrong shape is 400 REQUEST_INVALID, one step earlier, because request framing is checked before the hold is read."},
    "429": {"description": "The per-user or per-IP token bucket is empty."},
    "503": {"description": "Redis is unreachable."}
  },
  "errors": ["REQUEST_INVALID", "AUTH_REQUIRED", "HOLD_NOT_OWNED", "HOLD_EXPIRED", "VALIDATION_FAILED", "RATE_LIMITED", "DEPENDENCY_UNAVAILABLE", "INTERNAL_ERROR"],
  "idempotency": "a repeat of the same request against a seat already released returns 422 VALIDATION_FAILED, because the seat is no longer part of the hold. A repeat against a hold that has since expired returns 409 HOLD_EXPIRED. Neither creates or destroys anything.",
  "rate_limit": "seat hold bucket: 20 per minute per user and 60 per minute per real client IP.",
  "authorisation_rule": "The router dependency admits any authenticated principal holding an existing user row - no role is excluded; the handler asserts the hold record's user_id equals the caller's before the compare-and-delete script runs, and the script itself compares the hold's token so a lock this hold does not own can never be deleted.",
  "satisfies": ["P-HLD-08", "P-SEA-02"],
  "brd": ["R-HOLD-01", "R-SEAT-02"]
}
```

A customer who changes their mind about the whole selection gives every seat back at once. It is the
secondary control on the price summary, and it is the only path that ends a hold before its TTL other
than a confirm.

```endpoint
{
  "id": "EP-HLD-04",
  "method": "DELETE",
  "path": "/api/holds/{hold_token}",
  "summary": "Release an entire hold",
  "auth": "role",
  "roles": ["customer", "manager", "admin"],
  "request": {
    "path_params": {"hold_token": "string, opaque, exactly 43 characters from the URL-safe base64 alphabet, required"},
    "query": {},
    "headers": {},
    "body": {}
  },
  "responses": {
    "204": {"description": "The whole hold was released. P-HLD-08 carries the numbered procedure and it is SEVEN steps, not one: assert the caller owns the hold; compare-and-delete every key in ascending seat_id order; remove those keys from instance:{instance_id}:holds; delete the hold record; REMOVE THE TOKEN FROM holds:user:{user_id}:showtime:{showtime_id}, without which P-HLD-04's cap keeps counting a hold that no longer exists and the customer cannot re-take the seats they just gave back; DEL cache:seatmap:{showtime_id} AFTER the releases and never before, without which the seats read held to everyone else for up to the cache TTL instead of about three seconds; then answer 204 with no body. Steps 2 to 6 are best-effort - every structure carries the hold's TTL - and a compare-and-delete returning 0 for one seat is not an error and does not stop the loop."},
    "400": {"description": "The hold token is malformed - not exactly 43 characters, or carrying a character outside the URL-safe base64 alphabet. Checked before Redis is touched. REQUEST_INVALID, never HOLD_EXPIRED, for the reason given on EP-HLD-02."},
    "401": {"description": "No authenticated customer."},
    "403": {"description": "The token belongs to another user."},
    "409": {"description": "The hold has already expired. None of the release steps run: there are no keys to release, and the hold record and the index entry carried the same TTL and are gone with them. In particular NO cache:seatmap DEL runs on this branch - an expiry frees seats without telling the cache anywhere in this document, and adding one here would invent an invalidation the expiry path has never had (P-HLD-02 exception 3). A confirm in flight for the same hold does not refuse the release: the ordering settles it, per P-HLD-08."},
    "429": {"description": "The per-user or per-IP token bucket is empty."},
    "503": {"description": "Redis is unreachable."}
  },
  "errors": ["REQUEST_INVALID", "AUTH_REQUIRED", "HOLD_NOT_OWNED", "HOLD_EXPIRED", "RATE_LIMITED", "DEPENDENCY_UNAVAILABLE", "INTERNAL_ERROR"],
  "idempotency": "a repeat returns 409 HOLD_EXPIRED, because the hold no longer exists and the server cannot distinguish a hold released a second ago from one that timed out. Nothing is released twice; the compare-and-delete script is a no-op against a key that is gone or that carries another token.",
  "rate_limit": "seat hold bucket: 20 per minute per user and 60 per minute per real client IP.",
  "authorisation_rule": "The router dependency admits any authenticated principal holding an existing user row - no role is excluded; the handler asserts the hold record's user_id equals the caller's before any key is touched.",
  "satisfies": ["P-HLD-08"],
  "brd": ["R-HOLD-01"]
}
```

### New error codes this lane needs

```newerrorcode
{"code":"VALIDATION_FAILED","http":422,"when":"a request body fails a bound the registry has no code for: a duplicate seat id inside one hold request, a seat id that is not in this showtime's seat set (P-ADM-14), an empty seat list, or a seat that is not part of the hold being modified. SEAT_LIMIT_EXCEEDED covers only the ten-seat cap and no other validation failure.","raised_by":["EP-HLD-01","EP-HLD-03"],"why_needed":"FR-ADR-052's list has no general validation code. Without one, a duplicated seat id would have to be answered with a code that means something else, or silently de-duplicated - and silently correcting a request is how a customer ends up with a different number of seats than they asked for."}
```

```newerrorcode
{"code":"NOT_FOUND","http":404,"when":"the showtime id in the path does not exist.","raised_by":["EP-HLD-01"],"why_needed":"FR-ADR-052's list has no not-found code. A missing showtime is not a seat conflict, not a validation failure of the body, and not an internal error, and answering it with any of those would tell the customer something untrue."}
```

**A third code was proposed here and has been dropped.** An earlier draft of this lane raised a 409
code to refuse a release while a confirm for the same hold was in flight, and recorded it as its own
lowest-confidence proposal. **It is removed, name and all.** The flag it depended on was never
specified — where it lived, who set it, who cleared it, how long it lasted, or what happened when the
confirming process died between setting it and committing — and any answer to those questions is new
durable state, which `FR-ADR-025` keeps out of PostgreSQL on purpose. **The race is resolved by
ordering instead, with no new state and no new code** (`P-HLD-08`, and the `held_by_me_paying` +
`DESELECT` transition): the confirm's own Redis re-validation is the resolver, a release landing before
it makes the confirm fail `HOLD_EXPIRED` with nothing charged, and a release landing after the booking
commits is a compare-and-delete against a token that no longer matches and does nothing. **Two codes,
not three, are new on this lane.**

---

## Lane notes

### Article X candidates raised by this lane

**`PROPOSED-SEATMAP-DEGRADED-01` — what the seat map shows for a held seat while Redis is unreachable.**
`FR-ADR-028` rules that the seat map degrades to PostgreSQL when Redis is gone. PostgreSQL knows which
seats are **sold**; it has no knowledge of holds, because `FR-ADR-025` deliberately keeps holds out of
the database. So a degraded map can only render a held seat as `available`. Two readings exist and no
source chooses between them:

1. **Serve the degraded map.** Held seats show as available. Every hold attempt against them returns
   503 anyway, so nothing is oversold and nothing is lost — but the customer is shown a seat as free
   when it is not, and then told holds are unavailable.
2. **Fail the map too.** The customer is told nothing can be shown, which contradicts `FR-ADR-028`'s
   decision that browsing keeps working, and gives up read traffic PostgreSQL could have served.

**Answered in the merge pass, in effect rather than on its merits — and that distinction matters.**
`X-7` established that the seat-map read is rate-limited (`FR-ADR-058`) and that the limiter reads
Redis and **fails closed**, and that the limiter runs **before** the cache. So the request never
reaches the PostgreSQL fallback and the endpoint answers **503**: option 2 above, reached by a route
that has nothing to do with the seat map's contents.

**Why this candidate is still recorded rather than deleted.** The question it asks — *should a map be
served that cannot show holds* — was never decided; it was made unreachable by a control that exists
for another reason. **If the rate limiter were ever removed from that endpoint, or made to fail open,
the question returns immediately and unanswered.** That is exactly the kind of dependency worth
writing down, because the change that would resurface it looks unrelated to it.

`FR-ADR-028` answers the question for the *cache* and does not notice that one of the three states the
map carries exists only in the thing that is down. That observation stands, and it is the reason this
row exists.

**`PROPOSED-BULKBUY-01` — nothing limits how many seats one customer may *buy* on one showtime.**
`P-HLD-04`'s cap is ten seats **held at once**. `P-PAY-10` step 13 removes the hold's token from
`holds:user:{user_id}:showtime:{showtime_id}` at commit, deliberately, so seats the customer now owns
stop counting against it — without which a customer who bought ten could buy nothing else on that
showtime for the remainder of the 180 seconds. **The consequence is that ten-seat bookings can be
repeated until the hall is gone.** `SRC-003 OPEN-BOOK-01` answers a question about the maximum seats
in **one booking** and `FR-ADR-026` decides only where the cap is enforced; **neither reaches
successive bookings.** This lane therefore states no lifetime limit, because inventing one is a scope
change and scope is reserved. Recorded rather than decided, and it is the client's to answer.

**No other Article X candidate.** Everything else this lane needed was either ruled, or a
non-reserved technical question the build session may decide, and each of those is listed below rather
than escalated.

### Assumptions I had to flag

| Flag | What it is | Where it bites in this section |
|---|---|---|
| `PROVISIONAL` | **Sales close 15 minutes *after* the advertised start** (`SRC-003 OPEN-BOOK-03`, `FR-ADR-042`). The alternative reading is 15 minutes *before*, and the two are half an hour apart | `P-HLD-06` in full, including its worked example, both readings computed. The `SALES_CUTOFF_PASSES` row of the state machine in all five states. The sales-closed banners in `SCR-SEA-01`. `SALES_CLOSED` in `EP-HLD-01`. **Reversing it changes one configured number, its sign, and three assertions.** |
| `PROVISIONAL` | **Four roles** (`SRC-003 C-1`, `FR-ADR-009`) | `P-HLD-05`'s role list. If the client collapses to one role, the manager exclusion in that row disappears and nothing else moves. |
| `PROVISIONAL` | **One cinema with six screens** (`SRC-003 C-2`, `FR-ADR-010`) | Only indirectly: the cinema's IANA zone is read from the cinema row in `P-HLD-06`, not from a global constant, so a second venue in another zone needs no change here. |
| `ASSUMED` | **Seat category names — Standard, Premium, Recliner** (`SRC-003 OPEN-SEAT-01`, "you pick") | Every worked example in `P-SEA-04` and `P-HLD-11` names them, and the legend in `SCR-SEA-01` renders one band per category row. **They never harden into a requirement**; the bands are generated from the category table and a fourth costs an insert. |
| `ASSUMED` | **Hall sizes 90/120/150/180/200/220** (`SRC-003 OPEN-SCALE-02`, "pick random") | The 220-seat hall on a 375-pixel screen is the design target for `SCR-SEA-01`'s horizontal scroll. No layout decision depends on the exact numbers. |
| `ASSUMED` | **Peak concurrency of fifty bookers** (`SRC-003 OPEN-SCALE-03`, "you pick") | Only the *light load test* in `P-HLD-13`. **The fifty-request correctness gate is `SRC-002 §9.1`'s own number and is not assumed.** The two must never be confused: one measures performance and proves nothing about correctness. |
| judgment call | **Releasing one seat reduces the hold rather than voiding it** (`P-HLD-08`) | No source addresses it. Reducing was chosen because voiding takes away seats the customer never offered to give up. |
| judgment call | **`HOLD_EXPIRED`'s message is generalised** away from `FR-ADR-052`'s illustrative *"Your three minutes ran out"* (`P-HLD-14`) | The same code fires for a TTL, for a graceful-shutdown release and for a re-acquired key, and the server cannot tell them apart. A message naming the cause would be untrue in two cases out of three. |
| judgment call, **now superseded by a document-wide owner** | **Times are rendered `h:mm am/pm` in Asia/Kolkata** | No source specifies a format. It appears in every `SALES_CLOSED` message. **`S7.19` now owns the rule for the whole document and adopted this exact form**, so nothing in this lane's copy changed — the decision simply stopped being one lane's. |
| judgment call | **An out-of-service seat is carried by a boolean, not a fifth state** (`P-SEA-02`, owned by `P-BRW-09`) | A retired seat can also be `sold`, so a fifth enum value would displace the sale state and lose it. This lane's part is only that such a seat is never selectable and is rejected server-side at the hold. |
| judgment call | **The hold token appears in a URL path** (`EP-HLD-02`, `-03`, `-04`) | Made safe by requiring the caller's user id to match the hold's owner, so the token alone grants nothing and its presence in an access log is harmless. |
| judgment call | **`holds:user:{user_id}:showtime:{showtime_id}`** as the index the ten-seat cap reads | `FR-ADR-026` requires the cap check to be "a lookup of at most ten known keys, not a scan" but names no key. This is the smallest structure that satisfies it. |
| judgment call | **A customer may hold on two showtimes at once, and may take a second hold on one showtime** subject to the cap | `FR-ADR-026` rules out a cross-showtime cap explicitly. Two tokens on one showtime is not addressed anywhere; permitting it and counting both against the ten is the reading that keeps the cap meaningful. |
| `[JUDGMENT CALL]` | **The seat map's post-hold primary action reads `Continue to payment`, not `Pay ₹1,562.49`** (`SCR-SEA-01`) | `SCR-PAY-01` states it is the only screen in the product with a pay action, and a button on this screen labelled `Pay …` contradicted it. No P-row publishes this label, so the screen owns it (`S1.2` rank 3). `Continue to payment` names what the control does — it navigates and sends no request. The amount is not lost: it is on the `TOTAL` line directly above. **Reversible** — one copy-table cell and two prose sentences, here and on `SCR-PAY-01`. |
| `[JUDGMENT CALL]` | **`RATE_LIMITED`'s published span is 3 seconds, not 20** (`P-HLD-14` row 16, `P-HLD-01` exception 11) | The two rows published *"Try again in 20 seconds"* while this lane's own worked example computed 3. 20 is the seat-hold bucket's **capacity**; the sentence wants its **refill interval**, which at 20 per minute per user is one token every 3 seconds. The copy was made to agree with the arithmetic its owning row already carried, not the other way round. **Reversible** — it is one computed value in two cells and one worked example. |
| `[JUDGMENT CALL]` | **`SCR-SEA-03` pins to the viewport rather than to the map container's "sticky header area"** | `COMPONENTS.md §6` puts the banner inside the scroll container's sticky header area; `COMPONENTS.md §1.3` says that container scrolls horizontally and **deliberately not vertically**, so a header sticky inside it is sticky against an axis nobody scrolls and the banner is off-screen for a customer reading the far rows of a 220-seat map on a 375px phone. It cannot ride the application header either — `SCR-XCT-05` marks that **`Not sticky`** citing `P-XCT-25`. A banner is not a header: it exists only while a message is live, so it steals no permanent vertical space. **Reversible** — one route line, one container row and one paragraph. |
| `[JUDGMENT CALL]` | **The closing clause of a hold refusal is `Your hold is unchanged.` on an extend, and `No seats were held.` only on a first hold** (`P-HLD-14`, rows 2b and 3b) | Once `SCR-SEA-01` published a state in which a customer chooses further seats while holding some, `No seats were held.` became a false statement on that path — contradicted by the countdown, the held cells, the heading and the cap, all on the same screen. The behaviour was already settled: `P-HLD-01`'s rollback set excludes keys the customer already owned, so a failed extend cannot release them. **Only the sentence was missing.** **Reversible** — one substitution rule, two published rows and one worked example. |
| judgment call | **`fr.selection` is the key for the live local selection** (`P-SEA-03`) | No row named a key for a value `P-SEA-03` writes on every change, while `P-ACC-13` named `fr.pending_selection` for a value written once and deleted after restore. One key cannot carry both policies — the restore would delete the only durable copy of a selection still on screen. Two keys, both inside the `fr.` namespace `P-ACC-13` sweeps on sign-out, so neither needs its own clause. |
| reasoned, not observed | **The ECS stop-timeout relationship** in `P-HLD-12` | This session has never observed this application running in AWS. The ordering requirement is reasoned from `FR-ADR-033` and is owed to `docs/30 Deployment/` as a Zone C specification. |

### Corrections applied in iteration 6, none of which was a decision

Each of these made an out-ranked or stale statement in this file agree with something that was already
settled elsewhere. None of them chose anything, so none is a judgment call.

| # | What was wrong | What it now says |
|---|---|---|
| `F1` | `P-HLD-03` and `P-HLD-08` bounded the hold token at 1..255 characters | **Exactly 43 characters from the URL-safe base64 alphabet**, verbatim as `EP-HLD-01`..`EP-HLD-04` and `EP-PAY-01` publish it. The endpoint block owns wire shape (`S1.2` rank 1) and the P-rows were simply wrong |
| `F2` | The seat lifecycle state machine published a longer `IDEMPOTENCY_IN_FLIGHT` string in two transitions | Both now read `This booking is still being processed.`, byte for byte as `P-PAY-09` and `SCR-PAY-01` publish it |
| `F8` | `SCR-SEA-02`'s boxed warning claimed the in-flight zero state still said *"Your three minutes are up"* | The box is corrected to the copy table above it, which had already been generalised. There is no open wording item on that component |
| `F13` | `P-SEA-05` happy-path step 3 was garbled mid-sentence, stating the `held` rule twice and finishing neither | Steps 3 and 4 now state the rule once: the server emits one of three **wire** states, and the client decides `held_by_me` against `held_by_other` from its own token |
| `D1` | `P-HLD-13` required fifty authenticated sessions and said nothing about where they come from | One sentence in its preconditions deferring to `P-XCT-07`, which owns the warm-up, the bucket values and the arithmetic. **This file deliberately restates none of it** |
| `D12` | The state machine enumerated 28 inputs including `TAB_CLOSED` and **had no sign-out input at all**, so nothing said what signing out does to a live hold | **`SIGN_OUT` added as the 29th input**, releasing the hold from `held_by_me` and specified in all five states. Totality re-proved: 145 cells, none blank, reachability unchanged because its only non-self edge already existed. `P-SEA-06` states why this releases where `TAB_CLOSED` does not — sign-out is a request the customer made, answered synchronously |
| `F1` | Two guards described *"the checkout panel is a sheet over the map"* and *"the map behind the checkout sheet keeps polling"*, while `SCR-PAY-01` is a separate **route** whose element table has no seat map. A machine declared normative was asserting behaviour that cannot happen | Corrected both: **checkout is a route, the map unmounts, the 3-second poll stops.** Each guard now says the input is reachable only from another tab still showing the map. Settles a second thing worth having: **no background poll runs from the checkout route, so nothing is counted against the seat-map limiter while a customer pays** |
| `D4` | `SCR-SEA-01` published four primary-action labels and **no state for "a hold is live and further seats are chosen"**, so `P-HLD-01` step 4's extend path was unreachable from the product and `P-HLD-11`'s two-base-price worked example could never occur | The state and its labels are published: `Hold 2 more seats` / `Hold 1 more seat`, with a `2 more chosen` / `1 more chosen` subheading, and a stated rule for what the total shows while a hold is live and further seats are chosen — **only the held portion is price-protected** |
| `D4` (root cause) | `P-HLD-02` exception 2 read *"a client asks to extend a hold — there is no such endpoint"*. **"Extend" names two different things one word apart**: moving `expires_at` (does not exist) and adding seats to a live hold (an ordinary path). A reader meeting exception 2 first concludes the whole extend path is unreachable | `P-HLD-02` gains a two-row table separating the readings, and exception 2 is split into **2** (the `expires_at` case, refused) and **2b** (the add-seats case, explicitly not an error). This was the reason the screen state was missing, so it is recorded as the cause rather than a sibling fix |
| `D7` | `P-HLD-03` said a malformed hold token *"is rejected as malformed before Redis is touched"* and then specified only the well-formed-but-unmatched case; `EP-HLD-02` and `EP-HLD-04` carried **no `400`, no `422` and no validation code at all**, leaving both unimplementable as declared | **`400 `REQUEST_INVALID`** on `EP-HLD-02`, `-03` and `-04`, matching `P-PAY-01`'s ruling on the identical field. `P-HLD-03` gains exception row 0 and states why `HOLD_EXPIRED` would be a **false** statement rather than a loose one: a 43-character token of the wrong shape could never have been issued, so it names no hold that ever existed. `EP-HLD-03`'s `422` is narrowed to the well-formed case. `P-HLD-14` row 24 publishes the sentence, verbatim from `P-PAY-01` |
| `D11` | `3 seats chosen` and `3 seats held by you` interpolate a **count** and published no singular; `S7.21` reached only configuration | Both singulars published — `1 seat chosen`, `1 seat held by you`. Stated as the same failure `S7.20` rule 4 names for durations: a selection of one seat is not an edge case, it is the first tap of nearly every session, and an implementer with only a plural ships `1 seats chosen` |
| `D12` | `SCR-XCT-01` published a `Choose seats again` action for `HOLD_EXPIRED` while `SCR-SEA-03` said `DEPENDENCY_UNAVAILABLE` is the only code carrying one — two rank-3 screens over one surface | `SCR-SEA-03` governs the seat map and says why at the site: **a customer meeting `HOLD_EXPIRED` there is already on the screen the button would send them to**, and the re-application is automatic. `SCR-PAY-01` settles the same fork on its own side. The registry's action stands for every other surface |
| `F6` | *"exactly four seat states"* was stated against a **three-value** wire enum, with nothing saying the fourth is a client-side split of the third | Qualified at all five sites: four **rendered**, three on the wire, `held_by_other` and `held_by_me` being the two ways a client draws `held`. `P-SEA-02`'s exception 1 and its server-side validation now name the three wire values explicitly, so a payload carrying `held_by_me` is a stated defect rather than an implied one |
| `D9` | `P-HLD-01` step 10 said *"return the token, `expires_at`, the per-seat prices and the total"* with no antecedent for *the*, and step 8 was ambiguous between each seat **in this request** and each seat **in the hold** — money the customer reads before pressing pay | Step 10 returns **the whole hold**: every seat under that token with its own stored price, and a `total_paise` equal to what confirm will charge. Step 8 prices **only the seats this request acquired** and appends them. `P-HLD-11` carries the two-request worked example. The case exists only because `F4` established that a hold is extended under the same token; the pricing consequence came with it and nobody had written it down |
| `F6` | `P-HLD-14` row 4, `SEAT_UNAVAILABLE` **at confirm**, had no plural partner while rows 2 and 3 gave the pair at hold — the row's own rule pointed at a string that did not exist | Row **4b** publishes it. `P-PAY-11` gains a matching exception row, and `SCR-PAY-01` now states it substitutes nothing: the server renders the complete sentence and the screen displays `message` as received (`SCR-XCT-01`) |
| `the class` | `SCR-SEA-03` named an in-banner action and a dismiss control in its fields and states tables and **published words for neither** | Both published, with the rule that exactly one code carries an action and why the others do not. `SCR-SEA-01`'s single legend string also **deferred** to `SCR-BRW-03`, which publishes all five — the two are the same screen and a second copy of one of five labels is the drift their own converged-strings rule forbids |
| `A3` | The three seat-level `VALIDATION_FAILED` strings had **only a singular**, while `SCR-XCT-01` rules that the server renders `message` and the client never composes it — so with two offending seats the server had nothing to send | Rows 21, 22 and 23 of `P-HLD-14` publish a plural for each, in `SEAT_UNAVAILABLE`'s shape, naming every offending seat in submission order joined `A, B and C`. Singular at exactly one, plural at two or more — stated as a rule with a worked example at two |
| `A5` | `Up to 10 seats.` and the two `SEAT_LIMIT_EXCEEDED` sentences quote a number that is configuration, and nothing said whether it is interpolated | Marked at `P-HLD-04` and at all three publication sites: the number renders `MAX_SEATS_PER_BOOKING` and a literal `10` is a defect. **The published strings are unchanged** — they are the rendering at the default. At `MAX_SEATS_PER_BOOKING = 6`, which the boot check permits, a literal would state a limit the server does not enforce |
| `B4` | `SCR-SEA-01` published a time-naming sales-closed banner while `SCR-BRW-03`, the same screen at the same route, published `P-BRW-07`'s | The banner is `Sales for this showtime have closed.` in all six screen-surface sites, including the three `SALES_CUTOFF_PASSES` transitions. **`P-HLD-14` row 9's `409` body is untouched** and still names the time — a banner states a standing condition, an error explains a refused action, and the note at `SCR-SEA-01` says so |
| `B5` | Three variants existed for what are **two** situations: a local refresh, and a return from sign-in | `P-SEA-03` owns the local-refresh string and names `P-ACC-13` for the other; `P-HLD-05` exception 4 and `SCR-SEA-01` now defer the sign-in case to `P-ACC-13` rather than publishing a copy. Both rows say "still selected", never "still held" |
| `F4` | `P-HLD-01` happy-path step 4 said *"generate one hold token"*, contradicting the paragraph directly beneath it and `EP-HLD-01`'s `idempotency` field | Step 4 is now a lookup before a generation: an existing live hold on this showtime supplies its token **and** its unchanged `expires_at`, and a token is minted only when none exists |
| `D3` | Seven statements of the hold's seat-membership test, plus two fenced blocks, refused a seat that "does not belong to this showtime's **screen**" | **Membership of this showtime's seat set** (`P-ADM-14`), which is materialised at showtime creation and never changes. **This was a correctness defect, not a wording one:** screen membership and seat-set membership are different sets, and a seat added to a hall after a showtime existed passes the screen test while being absent from that showtime's `seat_count_at_creation` — holdable and sellable on a showtime it is not part of, which is the oversell the materialised set exists to prevent. **The published copy is unchanged**: `Seat C12 is not part of this hall. No seats were held.` is still true from where the customer is standing, and `P-ADM-14` defers that string to `P-HLD-01` |

### Corrections applied in the journey fix wave

Seven defects were raised against this section by the six independent journey lanes
(`docs/11 Journeys/DEFECTS_FOUND.tsv`). None of these was a decision about what the product does;
each made this file state a behaviour that was already settled, or state one it had left unsaid.

| # | What was wrong | What it now says |
|---|---|---|
| `J-CUS-03` | The state machine's `held_by_me_paying` + `TAB_REFRESHED` guard said the restored page **re-sends the same confirm**, while `SCR-PAY-01` says in terms that it **never** re-sends and decides from `fr.last_booking_reference` with no request. One of them put a payment request on every `F5` | The guard now says the refresh abandons the **response** and not the **request** — mechanically the same as `TAB_CLOSED` from this state — and that pressing pay again is `CONFIRM_START`, which is what keeps `IDEMPOTENCY_IN_FLIGHT` reachable. `SCR-PAY-01` owns the checkout screen's behaviour; this file was the restatement and therefore the defect. The `sold` + `TAB_REFRESHED` guard is corrected on the same ground |
| `J-CUS-05` | `P-HLD-14` rows 2 and 3 ended `No seats were held.` on **every** hold refusal, while `SCR-SEA-01` publishes a state in which a hold is live and further seats are chosen — where the sentence is contradicted by the countdown, the held cells, the heading and the cap, all on the same screen | The closing clause has two forms and the server picks: `No seats were held.` on a first hold, **`Your hold is unchanged.`** on an extend. Rows **2b** and **3b** publish the two `SEAT_UNAVAILABLE` extend sentences, with `try again` in place of a button label that interpolates a count. `P-HLD-07`'s flat "never says any seats are still held" is given its scope, and `P-HLD-01` gains exceptions `2b` and `2c` |
| `J-GST-05` | `P-SEA-03` wrote the selection to `sessionStorage` **on every change** and named no key; `P-ACC-13` writes `fr.pending_selection` **once** and deletes it after the restore. One key means the restore erases a live selection; two means nobody named the second | **`fr.selection`** is named, with a two-column table setting it against `fr.pending_selection` on write policy, read point, deletion and staleness, and a paragraph on why one key cannot carry both. Both sit inside the `fr.` namespace `P-ACC-13` sweeps on sign-out, so neither needs its own clause |
| `J-XCT-04` | `P-HLD-08` gave the per-seat release eight steps and the **whole-hold** release one sentence; `EP-HLD-04`'s block named neither the cache `DEL` nor the removal from `holds:user:…`. Built from the block, a customer who gave every seat back left them showing held for the cache TTL and could not take ten again until the hold TTL elapsed | A **seven-step** procedure for `EP-HLD-04`, plus answers for the three cases the one-sentence version left open: a compare-and-delete returning 0 is not an error and does not stop the loop; a released seat is claimed by the next `SET NX` and there is no queue; and on an **already-expired** hold none of the steps run and **no cache `DEL` runs**, because the expiry path has never had one. Both `EP-HLD-03` and `EP-HLD-04` now name the two writes in their own blocks |
| `J-XCT-07` | `SCR-SEA-03` placed the banner *"in the scroll container's sticky header area"*, copying `COMPONENTS.md §6`, while `COMPONENTS.md §1.3` says that container scrolls **horizontally only** — so it was sticky against an axis nobody scrolls — and `SCR-XCT-05` marks the application header `Not sticky` | The banner **pins to the viewport** while it is live, in the page's scroll context, reserving its own height so it can never obscure a focused seat cell. The paragraph states why this does not overturn `SCR-XCT-05`: a banner is not a header, because it is gone when there is nothing to say. Recorded as contradiction 9 against the design system, which is not this lane's to edit |
| `J-XCT-08` | `P-SEA-03` exception 3 owned the string `C12 is no longer available…` and **no screen named a state that rendered it**; `SCR-SEA-03` rendered "the verbatim string for the `code`" and this event has no code, because nothing was requested. A screen-reader user was never told a seat had left their selection | `SCR-SEA-03` gains a **Seat lost with no request sent** state, a behaviour row, a copy pointer and an accessibility clause putting the codeless notice through the same live region as an error. `SCR-SEA-01` gains the matching state, and its "a seat changes between two polls" row now says which changes are announced and which repaint silently |
| `J-CUS-10` | `P-HLD-04` was titled *"ten seats per showtime"* and read as a per-showtime limit, while it counts only **live holds** and `P-PAY-10` step 13 deliberately stops counting seats the customer has bought. A test transcribed from the title would assert a rule the server does not enforce | Retitled **"ten seats held at once on one showtime"**, with a paragraph on what the cap bounds and what it does not, exception row 5 (`201` for a second ten-seat hold after a purchase), and a validation note naming the assertion that does **not** belong. No limit is invented: `SRC-003 OPEN-BOOK-01` and `FR-ADR-026` reach one booking and the hold, not successive bookings, so the question is filed as `PROPOSED-BULKBUY-01` |

### Where I would have had to guess and did not

**1. What the seat map shows for a held seat during a Redis outage.** Raised as
`PROPOSED-SEATMAP-DEGRADED-01` above. `FR-ADR-028` decides the cache question and does not reach this one.
Two exception-path rows in this section point at it and write no wording.

**2. What a customer is told when their receipt definitively fails after payment.** `OPEN-EMAILFAIL-01`
is open and reserved. **This lane writes no sentence for that screen** and takes no position on the
money already taken. What it does specify is only the mechanical fact that the confirmation path is
independent of the email: `P-SEA-06`'s `TAB_CLOSED` transition from `held_by_me_paying` states that the
reference exists in the customer's bookings list and on the receipt independently of the screen, which
is a statement about where the reference lives and not about what happens when the email fails.

**3. Whether a showtime can be withdrawn while customers hold seats on it.** `OPEN-SHOWCANCEL-01` is
open and reserved, and `FR-ADR-035` records itself as blocked on it. **No withdraw capability exists in
v1**, so the case cannot arise, and this lane specifies no behaviour for it — not an endpoint, not a
screen, not a message. The state machine has no `SHOWTIME_WITHDRAWN` input for exactly that reason: an
input that cannot be produced would be a state transition invented for a capability that does not
exist.

**4. The direction of the sales cut-off.** Not guessed — `FR-ADR-042`'s `PROVISIONAL` reading is
carried, the rejected reading is computed alongside it in `P-HLD-06`'s worked example, and the reversal
is one signed configuration value.

**5. Whether a hold response should be 201 or 200.** This one I did decide, as a technical call: 201,
because a hold is a resource with a token that did not exist before. Recording it here only because a
reviewer will notice `EP-HLD-01` returning 201 while `EP-HLD-02` and `-03` return 200. **Confirmed and
propagated:** the concurrency criterion in `P-HLD-13` originally read "exactly one HTTP 200", copied
from `CONSTITUTION.md` Art IX.3's illustration of the *shape* of a binary criterion rather than from
this endpoint. A test transcribed from it would have failed against a correct implementation, on the
one gate that may never be waived. The endpoint keeps 201 and every statement of a successful hold in
this section now reads 201.

### Contradictions found against a frozen source, an ADR, or the design system

| # | One side | The other side | What this lane did |
|---|---|---|---|
| 1 | `COMPONENTS.md §6`'s seat-lost copy: *"`C12` and `C13` were taken by another customer. **Your other seats are still held.**"* | `FR-ADR-026`: a multi-seat hold is all-or-nothing, and the seats that were won **are released immediately** on partial acquisition. After a lost hold, **nothing is held** | Wrote `No seats were held. Your other choices are still selected` (`P-HLD-07`). The design system's sentence is true only if partial holds survive, which `FR-ADR-026` rules out. **The design system is the defect here, not the ADR.** |
| 2 | `COMPONENTS.md §6`: on `SEAT_UNAVAILABLE`, "marks them **`sold`** on the map immediately" | A seat lost to another customer's *hold* is `held_by_other`; it becomes `sold` only when their booking commits | Marked them unavailable rather than sold, and let the next poll settle which. Marking a held seat `sold` asserts something the server did not say |
| 3 | `FR-ADR-045` and `COMPONENTS.md §1.4`: **exactly four seat states** rendered — against a three-value wire enum, per `P-SEA-02` — no fifth, `held_by_me` means "this customer holds it" | `FR-ADR-046`: a **guest** may click seats and watch the running total build, with no hold and no lock. No state covers a seat that is chosen but not held | Reused the `held_by_me` treatment for a chosen seat and carried the difference on the price summary heading and the presence of the countdown (`P-SEA-02`). This adds no fifth rendering and keeps `FR-ADR-045` intact, but it is a reconciliation the merge pass should confirm |
| 4 | `COMPONENTS.md §7`: at zero, "the payment action is **disabled**" | A confirm request already sent cannot be un-sent, and `FR-ADR-047` forbids the client claiming anything about the seats | Split the zero state in two (`SCR-SEA-02`, `P-HLD-09` row 3). With a confirm in flight the busy state is kept and the customer is told an answer is still coming |
| 5 | `FR-ADR-052`'s `HOLD_EXPIRED` example: *"Your three minutes ran out."* | `FR-ADR-033` returns the same code when a graceful shutdown released a hold that had time left, and `P-HLD-03` returns it when a key was re-acquired | Generalised the server message (`P-HLD-14`) **and the client countdown's zero state** (`SCR-SEA-02`). The countdown was originally kept at "Your three minutes are up" on the reasoning that the client knows its own clock reached zero — it does, but a shutdown release and a re-acquired key drive it to the same `0:00`, so the client cannot tell the three apart either. Both now say only that the hold has ended |
| 6 | The lane brief names the configuration value `SALES_CUTOFF_MINUTES` | `FR-ADR-042` and `FR-ADR-053` both name it **`SALES_CUTOFF_MINUTES`** | Used `SALES_CUTOFF_MINUTES`, because an `APPROVED` ADR outranks a brief |
| 7 | `FR-ADR-045`: the running total is "computed from the per-seat prices in the map payload **using the same rounding rule as the server**" | If the payload carries already-rounded per-seat prices, the client applies **no** rounding at all — it sums integers | Read it as the payload carrying rounded integers and the client summing them (`P-SEA-04`). This is the strictest reading and removes the two-implementations risk entirely, which is what `FR-ADR-038` is protecting |
| 8 | `SRC-002 §8.1.1`: a lock TTL of **7 minutes** | `SRC-002 §E E-1` and `SRC-003 OPEN-HOLD-01`: **3 minutes** | Used 180 seconds from `SEAT_HOLD_TTL_SECONDS`. Recorded here because the withdrawn clause still reads as live text where it stands, and a future reader who opens `§8.1.1` without reading `§E` will get the wrong number |
| 9 | `COMPONENTS.md §6`: the error banner sits *"inside the scroll container's sticky header area, so it is visible without scrolling"* | `COMPONENTS.md §1.3`, two sections earlier: that container scrolls **horizontally** and *"vertically the map does not scroll inside its own box — rows grow the container and the page scrolls normally"*. A header sticky inside it is sticky against an axis nobody scrolls, so on `P-XCT-25`'s 375px design target the banner naming the lost seat is off-screen | `SCR-SEA-03` pins the banner to the **viewport** while it is live, in the page's scroll context, reserving its own height. **The design system contradicts itself here, two sections apart, and §1.3 is the half that is right** — the horizontal-only scroll is a deliberate decision with its own reasoning. `SCR-XCT-05`'s `Not sticky` application header is not disturbed: a transient banner is not permanent chrome. **`docs/05 B DesignSystem/` is not this lane's to edit; reported, not changed.** |

### Cross-lane dependencies this lane assumes but does not own

- **The seat-map read endpoint** (lane E1). This lane requires its payload to carry, per seat: the
  seat id, the row label and seat number, the grid coordinates, the category, one of the three
  objective states, and an **already-rounded integer `price_paise`**. Without the price on the payload,
  `P-SEA-04` cannot be implemented as specified. **Resolved:** lane E1's `P-BRW-08`, `P-BRW-10` and
  `EP-BRW-06` now carry `price_paise` on every seat object, and `P-BRW-13` counts the 20 bytes a seat
  it costs. This dependency is met, not outstanding.
- **The confirm endpoint and the idempotency record** (lane E3). This lane specifies only the seat's
  view of confirm — the ordering it depends on, and what each outcome does to the seat. It specifies no
  payment provider, no capture semantics and no idempotency record shape, **and it does not specify
  how the `Idempotency-Key` is generated: `P-PAY-09` owns that, because the key is part of
  `EP-PAY-01`'s wire contract (`S1.2`).** What this lane requires of it is one behaviour and not a
  generation rule: the key must live in `sessionStorage` beside the hold token and must still be
  there, unchanged, when a page is refreshed while a confirm is in flight — **so that one confirm can
  be sent at all and a second press cannot become a second booking**, which is the reason, and **not**
  so that a refreshed page can replay it. **An earlier version of this note said the key was
  "generated once per hold".** That would have bound the deliberate payment failure, which fires on a
  prefix of the key (`P-PAY-07`), to the whole life of a hold — making every retry fail identically
  and putting `fail -> retry -> succeed` out of reach of the product, which is `J-CUS-04`. `SCR-PAY-01` owns the checkout
  screen's refresh behaviour and states that it **never** re-sends the confirm; the state machine's
  `held_by_me_paying` + `TAB_REFRESHED` transition now says the same thing from the seat's side. An
  earlier version of that guard said the restored page re-sends, which contradicted `SCR-PAY-01`
  outright and would have put a payment request on every `F5`.
- **The authentication screen** (lane E6). `P-HLD-05` specifies the stopping point and the
  `sessionStorage` round trip; it does not specify the register-or-sign-in screen itself.
- **The showtime's materialised seat set** (lane E6, `P-ADM-14`). Every seat-membership test on this
  lane's hold path is now a membership test against that set rather than against the screen's current
  seats. This lane therefore requires the set to be **readable per showtime** — `P-ADM-14` specifies
  `showtime_seat`, written once at showtime creation by no endpoint and edited by none — and it
  requires `P-ADM-14` to keep owning the rule, because this lane states only the test and points.
  **If that set ever stopped being materialised and became a predicate computed from a seat's current
  flags, this lane's validation would silently revert to the screen test and the hole would reopen**,
  which is why the dependency is written down rather than assumed. This lane owns the refusal and its
  copy; it owns none of the mechanism.
