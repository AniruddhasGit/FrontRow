# E1 — Browse and discover

This epic is the entire public read path: the listing of movies a customer can currently buy tickets
for, the showtimes for a chosen movie on a chosen date, and the seat map for a chosen showtime as a
thing to *look at*. Everything here is readable with no account (`SRC-001 §4.1`, `FR-ADR-014`), every
endpoint in it is a safe method, and nothing in it takes a seat out of sale. The moment a seat is
held, this epic has ended and lane E2 has begun.

**The one thing that will be got wrong.** Customer visibility is **two independent gates**, and a
developer who implements one of them has written a defect that does not fail any obvious test. A
movie is shown only when the admin has published it **and** the evaluation instant falls inside its
display window (`R-BRW-06`, `FR-ADR-021`). Publication answers "is this finished"; the window answers
"is this the period we are showing it in". They are different questions, they are stored in different
columns, and both must pass on every **movie-addressed** customer-facing query — `P-BRW-01` tabulates
which endpoints those are and names the three that apply no gate. The second most likely error is the
timezone: every window boundary, every date filter and every sales cut-off is evaluated in
**Asia/Kolkata** against an **injected** clock, never against the container's clock, which in AWS is
UTC and rolls the date over at 05:30 local (`FR-ADR-018`).

---

## S4 — Product specifications

### `P-BRW-01` · Show a movie only when it is published and inside its display window · `RULED`
`[SRC: SRC-003 OPEN-ROLE-01 · SRC-003 OPEN-TMDB-01 · SRC-003 OPEN-TMDB-03 · SRC-003 OPEN-LOCALE-01 · FR-ADR-021 · FR-ADR-018]`
`[BRD: R-BRW-06]`

**Behaviour.** A movie appears on any **movie-addressed** customer-facing surface only when both gates
pass:

1. `published_at IS NOT NULL` — the admin published it deliberately.
2. `display_from <= T < display_until` — the evaluation instant `T` falls inside the display window.

A movie failing either gate is invisible on every movie-addressed customer-facing surface: the
listing, the film detail and the showtime list. It is never deleted and never hidden from the admin
(`FR-ADR-012`, `FR-ADR-021`).

**Three endpoints in this epic apply no gate, and this row is where that is stated rather than left to
be found.**

| Endpoint | Gates applied | Why, and what decides it |
|---|---|---|
| `EP-BRW-01` the listing · `EP-BRW-02` the film · `EP-BRW-04` the showtime list | **yes** | movie-addressed. A film failing a gate is absent from the array, or 404 with the same body a film that never existed returns |
| `EP-BRW-03` the poster redirect | **no** | stated and accepted, not overlooked: a poster id discloses that a draft exists, on the same ground showtime ids are public (`FR-ADR-017`, `P-BRW-15`) |
| `EP-BRW-05` the showtime header · `EP-BRW-06` the seat map | **no, today** | showtime-addressed. **Whether they should is `OPEN-BRWVIS-01`, which is `OPEN` and reserved, and this row does not answer it** |

> **This overturns what this row said before, and the earlier text was the defect.** It said without
> qualification that a movie failing either gate is *"invisible to guests and customers alike"* and
> that the predicate is *"called from every such query"*, while `EP-BRW-05`'s own authorisation rule
> states in terms that **it does not apply the movie visibility gates** and `EP-BRW-03` and
> `EP-BRW-06` apply none either. **One of those sentences was wrong today and no ruling makes both
> right.** A developer reading only this row would have gated the seat-map header; a developer reading
> only the block would not; and the two choices differ by whether a withdrawn film's title, hall and
> price are publicly displayed. **The row is corrected to the endpoints that actually filter**, which
> is what the document specifies.

**What is corrected here is the contradiction, not the policy, and the difference matters.** A film
may leave its window while its showtimes still hold unsold seats. `FR-ADR-021` settles that the window
governs the **browse surface** and not the **booking record**; it settles nothing about whether those
showtimes may still be **sold**. Gating `EP-BRW-05` and `EP-BRW-06` would settle that in one direction
and leaving them open settles it in the other, so **neither is decided here** — that is
`OPEN-BRWVIS-01`, it is reserved, and inventing an answer is the cardinal sin of this project.
**Until it is ruled, the specification of record is what the two endpoint blocks carry: no movie gate.**
`SCR-BRW-03` correspondingly publishes no state for a film that has left its window; that gap is filed
against the same open row and is not filled in here.

**How the gates are evaluated, exactly.**

- `published_at`, `display_from` and `display_until` are `timestamptz` columns holding UTC instants
  (`FR-ADR-018`). There is no `timestamp without time zone` anywhere in this path.
- **`published_at` is a record of *when*, not a scheduling gate.** The read path tests only
  `IS NOT NULL`. It never compares `published_at` to the clock. A future-dated `published_at` would
  duplicate what `display_from` already means, and two columns expressing one fact drift.
- **`display_from` is inclusive, `display_until` is exclusive** (`FR-ADR-021`). The predicate is
  `display_from <= T` and `T < display_until`. A movie at exactly `display_until` is out.
- **`T` is the current instant from the injected clock** (`FR-ADR-018`), compared as an instant. No
  local date is derived to make this comparison — instant against instant, so the comparison is
  correct regardless of the server's zone.
- **The admin submits both instants and the server converts nothing.** `display_from` and
  `display_until` are stored exactly as submitted. `EP-ADM-04` accepts a local date **and time**
  (`P-ADM-04`, `SCR-ADM-02`), and **the admin types the exclusive end** — so a film whose last day is
  the 20th is given `display_until = 2026-08-21T00:00:00+05:30` by the person entering it, not by the
  server. **No day is added anywhere on the write path.**

  > **This overturns what this row said before.** It previously claimed the admin picked a last *date*
  > and the server moved it to the day after. That was wrong on two counts. `EP-ADM-04` is rank 1 and
  > accepts an instant, so the wire settles it; and **a server that silently shifts what an admin typed
  > by a day is the worse of the two designs even where it is convenient**, because the admin gets no
  > signal in either direction — they cannot tell from the form whether the 20th they typed means the
  > 20th or the 21st, and the first evidence either way is a customer finding the film gone a day
  > early. The exclusive boundary is now stated **once**, at the point of entry, where the person
  > choosing it can see it. `SCR-ADM-02`'s help text is what makes that legible and it belongs to the
  > admin lane.
- **Both columns are NULLABLE, and a null is treated as "not visible".** The window predicate is
  `display_from <= T AND T < display_until`, and **a null on either side fails it** — there is no
  three-valued subtlety to reason about, because the row is excluded exactly as a row outside its
  window is. The read path needs no special case and no `COALESCE`.
- **A draft with no window is a normal mid-authoring state, not a fault.** An admin creates a film
  before deciding when it runs (`P-ADM-01`), so the columns are null between the insert and the
  moment the dates are chosen. **Publication is where the window becomes mandatory**, not the insert:
  `P-ADM-05` refuses to publish a film whose window is missing, and `SCR-ADM-02` publishes the gate
  line `No display window set.` So a published film always has both, which is the invariant the
  client's "a dealine of how long this will stay" (`SRC-003 OPEN-ROLE-01`) actually asks for, and an
  open-ended **run** is still not a state this product has — a long run is a far `display_until`.

  > **This overturns what this row said before, and the earlier text was the defect.** It stated
  > *"Both columns are `NOT NULL`"*, which contradicts every admin row that touches them:
  > `P-ADM-01`'s draft insert names three nulls and not these, `EP-ADM-02` does not accept the window
  > at all, and `EP-ADM-03` returns both as *"ISO-8601 instant or null"*. **Under `NOT NULL` the
  > first admin write in the product is impossible** — there is no endpoint that could supply the
  > value the constraint demands — and `P-ADM-05`'s entire `PUBLISH_BLOCKED` branch plus two
  > published strings become unreachable code. **Nothing about how the gate is evaluated changes**;
  > everything above this bullet stands, and it is why this row owns the read path.

**Who may do it.** guest · customer · manager · admin — all four, identically. The gate is a query
predicate, not an authorisation rule; there is no role that sees more on the browse surface. The
router applies no auth dependency to these routes (`SRC-001 §7.4`, `FR-ADR-014`).

**Preconditions.** At least one movie row exists. The cinema row carries its IANA zone name
(`FR-ADR-018`). A clock is injected into the domain layer.

**Happy path.**
1. A request arrives at a movie-addressed customer-facing surface — the listing, the film detail or the
   showtime list.
2. The service reads `T` from the injected clock.
3. The visibility predicate — **one function, called from every query the table above marks `yes`** —
   is applied.
4. Rows failing either gate are absent from the result. They are not returned with a flag.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | Every published movie is outside its window | 200 with an empty list | "Nothing is showing right now." |
| 2 | The filters chosen match no visible movie | 200 with an empty list | "Nothing is showing for the chosen filters." |
| 3 | A movie id that exists but fails a gate is requested directly | 404 `NOT_FOUND` | "That movie is not showing." |
| 4 | A movie id that has never existed is requested | 404 `NOT_FOUND` | "That movie is not showing." |
| 5 | PostgreSQL is unreachable | 503 `DEPENDENCY_UNAVAILABLE` | "The site is temporarily unavailable. Please try again in a moment." |

Rows 3 and 4 return the **same** response on purpose. A different answer for "unpublished" and "never
existed" tells an anonymous caller which draft movie ids exist.

**Server-side validation.** `movie_id` is a positive integer; a non-integer or a value below 1 is
422 `VALIDATION_FAILED` and never reaches the query. The visibility predicate is applied in SQL, not by
filtering in Python after the fetch — a post-fetch filter is the one a later refactor drops.

**Worked example.** A movie the admin published on 2026-08-10, to be shown from 2026-08-14 to
2026-08-20 inclusive.

```
published_at   = 2026-08-10T11:04:22+05:30   (stored 2026-08-10T05:34:22Z)
display_from   = 2026-08-14T00:00:00+05:30   (stored 2026-08-13T18:30:00Z)
display_until  = 2026-08-21T00:00:00+05:30   (stored 2026-08-20T18:30:00Z)
                 ↑ the ADMIN typed the 21st, because the bound is exclusive.
                   The server stored what it was given and added no day.
```

| Evaluation instant `T` | `published_at` gate | window gate | Visible |
|---|---|---|---|
| 2026-08-13T23:59:59+05:30 | passes | `T < display_from` | **no** |
| 2026-08-14T00:00:00+05:30 | passes | `display_from <= T`, inclusive | **yes** |
| 2026-08-20T23:59:59+05:30 | passes | still `T < display_until` | **yes** |
| 2026-08-21T00:00:00+05:30 | passes | `T = display_until`, exclusive | **no** |

The same movie with `published_at = NULL` is invisible at every one of those four instants.

---

### `P-BRW-02` · Carry the six details a customer chooses between films on · `RULED`
`[SRC: SRC-001 §5.1.1 · SRC-003 OPEN-TMDB-01 · FR-ADR-021 · FR-ADR-061]`
`[BRD: R-BRW-02]`

**Behaviour.** Every movie in the listing carries its poster, synopsis, running time, certification,
language and genre. `SRC-001 §5.1.1` survives unchanged and names exactly those six.

**The listing payload per movie.**

| Field | Type | Notes |
|---|---|---|
| `id` | integer | internal id; public because a movie is not private (`FR-ADR-017`) |
| `title` | string | not unique — two films may share a title, and a re-release is a second row (`FR-ADR-021`) |
| `synopsis` | string | plain text, no markup |
| `runtime_minutes` | integer | rendered as a number, in `--fr-font-mono` |
| `certification` | `{id, name}` | a lookup row, not free text. **`name`, not `code`** — see below |
| `language` | `{id, name}` | a lookup row, because it is a filter facet |
| `genres` | array of `{id, name}` | many-to-many; a film is routinely two genres |
| `poster_url` | string | the **path to this API's poster redirect**, never an S3 URL and never a third party's URL |
| `display_until` | string | ISO-8601 with the `+05:30` offset. The **exclusive** end of this film's display window (`P-BRW-01`). **Never null on this surface** — the column is nullable, but a film that reaches a customer-facing listing has passed the window gate, which a null fails. Carried on the listing because the date strip is built from it (`P-BRW-04`) |

**The certification is `{id, name}` and there is no `code` anywhere.** This wire shape previously read
`{id, code}` in five places and **nothing could ever have populated it**: `P-ADM-23` owns the
`certification` table and fixes it at `id`, `name`, `is_active`, `created_at`, saying in terms that
there is no code, and `EP-ADM-26` accepts only `name`. **The data model is right and the wire was
wrong**, so the wire changed. **No `code` column is added** — adding a column because a display field
asked for one is a data-model change made from the wrong end, and the table is `P-ADM-23`'s.

`name` already holds exactly the text the certification chip renders, because it is the only thing the
admin types. The change also makes `certification` the same shape as `language`, `genre` and `format`:
four vocabularies of one table shape had no business carrying two wire shapes.

**Who may do it.** guest · customer · manager · admin. Public.

**Preconditions.** The movie passes both gates in `P-BRW-01`. A published movie always has a poster
(`FR-ADR-021` makes it a publish-time check), so `poster_url` is never null on this surface.

**Happy path.**
1. The listing query returns the visible movies with their lookup rows joined.
2. `poster_url` is built as `/api/movies/{id}/poster` from configuration, not stored.
3. The card renders the poster box at its reserved aspect ratio before the image arrives.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | The poster object is missing from S3 or the image fails to load in the browser | the redirect returns 404 `NOT_FOUND`; the listing is unaffected | the poster box draws the perforation motif with the title inside it; no words are added |
| 2 | A movie row has no genre | 200; `genres` is an empty array | the metadata row omits the genre segment; nothing says "unknown" |
| 3 | The synopsis is longer than three lines | 200; the full text is sent | the card clamps to three lines; the detail screen shows all of it |

**Server-side validation.** None on this path — it is a read with no client-supplied field. The
constraint that matters is upstream: a movie cannot be published with a null poster (`FR-ADR-021`).

**Worked example.** Not applicable. This spec computes no number.

**`OPEN-ATTRIB-01` bites here.** No licensed image, title or synopsis enters this product while that
row is open. Demonstration content is `DEMO MOVIE 01` with no image from anywhere (`FR-ADR-067`).

---

### `P-BRW-03` · Order the listing newest first, by `published_at` descending · `RULED`
`[SRC: SRC-003 OPEN-TMDB-01 · FR-ADR-021 · FR-ADR-017]`
`[BRD: R-BRW-05]`

**Behaviour.** With no sort chosen the listing is ordered **newest first**, and "newest" is
`published_at DESC` — the instant the admin published the movie. Not `display_from`, not `created_at`,
not the title.

**Why the key is named here and not left to the implementer.** `SRC-003 OPEN-TMDB-01` says "by default
the latest movie will be on top" and does not say what latest measures. `FR-ADR-021` decides it:
`published_at` descending. The three candidates give different orders — a movie drafted in June,
published in August, and shown from September sorts differently under each — so an unstated key is a
guess every developer makes differently.

**The tiebreak is `id DESC`.** Two movies published in the same transaction share an instant, and an
unordered tie makes the listing shuffle between two requests for no reason a customer can see. `id` is
a sequential identity column (`FR-ADR-017`), so `id DESC` agrees with publication order.

**The sort parameter exists and has one accepted value in v1.** `FR-ADR-021` states the default is
"overridden by the customer's chosen sort", so the capability is required. The vocabulary of sorts is
not ruled anywhere. `sort` accepts `newest` only; any other value is 422. **No sort control is
rendered while one value exists**, on the same rule `FR-ADR-046` applies to the cinema filter. The
question of which further sorts the client wants is raised in the lane notes; it is not invented here.

**Who may do it.** guest · customer · manager · admin. Public.

**Preconditions.** The set from `P-BRW-01`.

**Happy path.**
1. `ORDER BY published_at DESC, id DESC` is applied after the visibility predicate and after filters.
2. Filters narrow the set; they never change the order.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | `sort` is present with a value other than `newest` | 422 `VALIDATION_FAILED` | "That sort option is not available." |
| 2 | Two movies share `published_at` | 200 | the higher id is first, on every request, every time |

**Server-side validation.** `sort` is an enum with one member, `newest`. Absent means `newest`. It is
never a free string interpolated into SQL.

**Worked example.**

```
A  published_at = 2026-08-12T10:00:00+05:30   id = 7
B  published_at = 2026-08-14T09:00:00+05:30   id = 11
C  published_at = 2026-08-14T09:00:00+05:30   id = 12
D  published_at = NULL                        id = 13     ← draft
```

Order returned: **C (id 12), B (id 11), A (id 7)**. `D` is absent — it fails gate 1 of `P-BRW-01`, not
the sort. `C` precedes `B` on the `id DESC` tiebreak, not by chance.

---

### `P-BRW-04` · Filter by cinema, date, language and format — and render a reference-backed filter only when two or more values are in use, never with one · `RULED`, with one `ASSUMED` part
`[SRC: SRC-001 §5.1.3 · SRC-001 §6.6 · SRC-003 C-2 · SRC-003 OPEN-SCOPE-01 · FR-ADR-046 · FR-ADR-010 · FR-ADR-021 · FR-ADR-018]`
`[BRD: R-BRW-03]`

**Behaviour.** The customer narrows the listing by **cinema, date, language and format**
(`SRC-001 §5.1.3`). All four are query parameters on the API. **The interface renders a filter control
only when the reference data holds two or more values for it**; below that the control is absent, not
disabled and not shown with one option (`FR-ADR-046`).

**Capability and rendering are separate, and the difference is the whole point of this row.**

| Filter | API parameter | Applies to | In v1 at all | Counted against the two-or-more rule |
|---|---|---|---|---|
| cinema | `cinema_id` | the showtime's screen's cinema | **yes** — implemented and tested (`SRC-001 §6.6`) | **yes.** One cinema exists, so the control does not render (`FR-ADR-010`, `PROVISIONAL`) |
| date | `date` | the showtime's local calendar day | **yes** | **no** — not a reference vocabulary; see below |
| language | `language_id` | the movie's language | **yes** | **yes**, exactly as format and cinema are |
| format | `format_id` | the showtime's format | **yes** | **yes** |

> **The last column has no exceptions, and the fourth column is not the same question.** "In v1 at all"
> says whether the filter exists in this version as opposed to being deferred. It has **never** meant
> "always visible". **The two-or-more rule of the paragraph above applies to every reference-backed row
> of this table without exception, language included** — the earlier wording of this table read as
> though language were exempt, and it is not. This is the whole of `FR-ADR-046` and there is no row it
> does not reach.

**Which days the listing's date strip shows, and this row owns it.** `SCR-BRW-01` lists many movies
and has chosen none, so `P-BRW-06`'s strip — today through the last day of **the** movie's window —
has no movie to read. **The rule for the listing, stated once and in one form:**

```
first day = today in Asia/Kolkata, from the injected clock
last day  = the DAY BEFORE max(display_until) over the movies EP-BRW-01 returned
```

**The day before, because `display_until` is exclusive.** A film with
`display_until = 2026-08-21T00:00:00+05:30` shows through the **20th** and is invisible at the 21st
(`P-BRW-01`). Rendering the 21st would put a day button on screen whose only possible result is the
empty state.

**The strip bounds the range; it does not promise that every day inside the range has a showtime, and
the two claims are not the same claim.** A day **past** the bound can only ever be empty, which is why
it is not offered. A day **inside** the bound may still be empty — a film runs for a fortnight and the
cinema schedules nothing on the Tuesday — and pressing it renders
`Nothing is showing for the chosen filters.`, which is the ordinary filtered-empty state this screen
already publishes and not a fault.

> **This row previously justified the day-before rule on the ground that the strip "must never be able
> to reach the empty state", and that justification was false of the strip this row specifies.** The
> strip is computed on the **client**, from `display_until` and the injected clock and nothing else
> (see below), and **`EP-BRW-01` carries no per-day showtime information at all** — so no test of
> "does any film have a showtime on this day" is possible on that response, and none is specified. The
> bound itself is correct and is unchanged; **only the reason given for it was overstated, and an
> overstated reason is what a later reader implements.** Compare `P-BRW-06`'s
> `next_date_with_showtimes`, which *does* test for a still-open showtime — it can, because it is
> computed on the **server** for **one** film.
>
> **The accepted weakness, stated rather than absorbed:** a guest can press a day the product offered
> and reach the empty state. It costs one re-request, the remedy is already on screen, and closing it
> would need either a per-day aggregate on `EP-BRW-01` or one request per day — neither of which is
> specified here, and neither of which is invented here.

> **This row previously stated its own subject two ways, one day apart**, and that is a defect in the
> row rather than something a reader may resolve. It said the strip runs "through the latest
> `display_until`" **and** that it is "`P-BRW-06`'s rule with a maximum applied" — and `P-BRW-06` says
> **the day before** `display_until`, for exactly the exclusivity reason above. **Both halves carried
> this row's own authority, so nothing in the reading rules could break the tie** (`S1.2.1` case 8).
> The second phrasing is now the only one; the first is deleted rather than reconciled, because a
> footnote saying "these agree" would leave two forms for the next reader to compare.

**The maximum is taken over the FILTERED listing — the array the client actually holds.**
`EP-BRW-01` returns `display_until` on every movie **it returned**, and the client takes `max` across
that array. The strip needs no second request and no aggregate field.

> **This row also stated the SET two ways**, and it is the second half of the same defect. It said the
> maximum is taken "across the films currently visible to this caller (`P-BRW-01`)" — and `P-BRW-01`
> is the **visibility gate**, which is explicitly filter-independent — while four paragraphs later it
> said the client takes the maximum across `EP-BRW-01`'s array, **which is filtered**. The filtered
> set wins: an unfiltered bound offers days on which nothing matching the current filters can be
> showing **at all**, which is a stronger form of the emptiness condition 3 of
> `next_date_with_showtimes` exists to reduce (`P-BRW-06`), and a client cannot
> compute the unfiltered maximum from a filtered response without a second request nobody specified.

**So the strip moves when the filters move, and that is the point rather than a side effect.** Three
consequences, all observable, stated here because a reader meeting them on screen would otherwise read
a working strip as a broken one:

- **Applying a filter can shorten the strip.** Filtering to a language whose films all end sooner moves
  `max(display_until)` earlier and the strip loses its tail. Correct: those days now have nothing to
  show.
- **Applying a filter can remove the day currently selected.** If the customer has chosen 20 Aug and
  then filters to a language whose last film ends on the 18th, the selected day is no longer in the
  strip. **The selection drops back to `Any date` and the listing re-requests with no `date`
  parameter**, and the change is announced through the same live region as the result count
  (`SCR-BRW-01`). It is the rule `SCR-RPT-02` already applies when a selected option leaves its option
  set, and it is here for the same reason: **a filter still applied that the reader can no longer see
  in the control is how an empty listing gets read as a broken page.**
- **Clearing filters can lengthen it again**, from the same computation. Nothing is remembered and
  nothing has to be invalidated — the strip is recomputed from whatever `movies` the last response
  carried.

**When the array is empty there is no strip at all.** `movies` is `[]`, so the maximum is over an empty
set and **there is no upper bound to render** — not a bound of today, not a bound of one day, no
strip. This covers both empty cases, which render differently below it: nothing visible at all, where
`SCR-BRW-01` shows `Nothing is showing right now.`; and filters matching nothing, where it shows
`Nothing is showing for the chosen filters.` with `Clear filters`. **In both the strip is absent**, it
is never a single dead day, and the client never substitutes a horizon of its own.

**In the filters-matching-nothing case the strip's absence is what `Clear filters` undoes**, which is
why that control sits outside the strip: a control that vanishes along with the thing it repairs
cannot repair it.

- **Every caller's visible set is the same** — visibility is a query predicate and no role sees more
  (`P-BRW-01`). **The filters** are what make one caller's strip differ from another's.
- **The strip is recomputed per response**, from the injected clock and the array just returned, so it
  shortens on its own as films leave their windows.
- **No fixed horizon anywhere.** `P-BRW-06` refuses one as "a number no source supports", and "the day
  before the last day anything in this listing is showing" is derived from the same column the
  visibility gate reads.
- **The bound assumes every showtime falls inside its film's window, and nothing enforces that today**
  (`P-BRW-06`). A showtime scheduled outside it is offered by no day button on this strip, by no other
  browse surface either, and the missing check is `P-ADM-07`'s.

> **Where the field comes from.** `EP-BRW-01` carried no `display_until` and no aggregate until this
> pass, so the strip on the product's **entry page** could not be built at all — a rank-2 row requiring
> what the rank-1 shape could not carry (`S1.2.1` case 2). The two ways out an implementer had were
> both wrong: invent a horizon, which `P-BRW-06` refuses, or issue one `EP-BRW-02` request per listed
> film. **The shape was the defect and the shape changed.**

**The per-film field, not a `strip_until` aggregate**, and the reason is the one this document keeps
reaching: `display_until` per film is already the shape `EP-BRW-02` uses, so one field serves both
surfaces; a client holding the films can compute any bound it later needs without a contract change;
and **an aggregate would be a second value carrying a fact derivable from the first**, which is the
failure `P-BRW-16` refuses a `display_order` for and `S1.2` exists to describe. The maximum is
computed on the client because it is a bound over data the client already has — that is not the
arithmetic `FR-ADR-045` forbids, which is **money**.

**The date filter is the one row that is not counted, and it is not an exception to the rule.** The
rule counts entries in a **reference vocabulary** returned by `EP-BRW-07`, and there is no vocabulary
of dates: the date strip is derived from the injected clock and the movie's display window
(`P-BRW-06`), not from a lookup table. It renders whenever the screen renders. Nothing about that
weakens the rule for the three rows the rule does govern.

`SRC-001 §6.6` forbids designing in a way that blocks a second venue, so `cinema_id` is implemented,
tested and documented even though nothing renders it. The control appears **automatically** when the
reference endpoint reports two cinemas — nothing has to be remembered later, which is the failure mode
a "we will add it when we need it" note produces. **The same sentence is true of language and format**:
each appears on its own the moment its array reaches two, and disappears on its own if it falls back
below, with no code change and nothing to remember.

**What this means on day one, and what it means with the seed — both are correct, and a reader must be
able to tell them apart.**

```
Day one, before any admin has created anything
  languages in use ......... 0   ->  no language control
  formats in use ........... 0   ->  no format control
  cinemas in use ........... 1   ->  no cinema control
  the listing renders ...... the date strip and NO filter controls at all

With P-XCT-30's seeded catalogue (ASSUMED demonstration content)
  languages in use ......... 3   ->  the language control RENDERS
  formats in use ........... 2   ->  the format control RENDERS
  cinemas in use ........... 1   ->  still no cinema control
  the listing renders ...... the date strip, a language control and a format control
```

**A listing with no filter controls is not a broken listing.** It is the correct rendering of an empty
vocabulary, and it is what a first-run screenshot shows before anything is seeded. **Neither state has
a message explaining itself** — `FR-ADR-046` says the control is absent, not disabled and not
annotated, and a line reading "no filters are available yet" would be the interface apologising for
being correct.

**What `/api/reference` means by "rows in use", and this row owns the definition.** `EP-BRW-07`
returns the vocabularies the filter controls are counted from, and the count is what decides whether a
control renders at all — so "in use" has to mean one thing. **It means: referenced by something the
caller can currently see.**

| `{kind}` | A row is returned when |
|---|---|
| `language` | at least one film **currently visible on the public browse surface** carries it |
| `certification` | as `language` |
| `genre` | at least one currently visible film has a `movie_genre` row pointing at it |
| `format` | at least one **showtime of a currently visible film, not past its sales cut-off**, carries it |
| `cinema` | at least one such showtime — the same test as `format` — runs on a screen of that cinema |

**"Currently visible" is `P-BRW-01`'s rule** — published, and inside its display window — and it is not
restated here; the window arithmetic has one owner and this is not it. "Not past its sales cut-off" is
`P-BRW-07`'s evaluation, which is `PROVISIONAL` on the direction of the offset: reverse
`SALES_CUTOFF_MINUTES` and a format whose only remaining showtime starts within the next fifteen
minutes leaves this endpoint fifteen minutes earlier than it does under the reading implemented here.

**`is_active` is deliberately not a filter on this endpoint.** A withdrawn lookup row that a visible
film still points at **is returned**, because the customer can see that film and must be able to filter
to it. Withdrawal stops a row being **offered to the admin in the film form's selects** and does
nothing else, which is exactly what `P-ADM-23` already says, and `P-ADM-24`'s worked example is the
case that proves it: after a mistyped language is withdrawn, a customer filtering by it still finds the
film that carries it. That promise is only true if this endpoint ignores `is_active`, so it does.

**A row referenced by nothing visible is omitted, and that is the reason this endpoint is not simply
"every row".** A vocabulary entry nobody's visible film uses would put a value in the filter menu whose
only possible result is an empty list — the customer selects it, gets `Nothing is showing for the
chosen filters.`, and reads a working filter as a broken one. Omission is what stops the menu offering
a dead end.

**Worked example — the seeded catalogue.** Over `P-XCT-30`'s demonstration content: three languages
`DEMO LANGUAGE A`, `DEMO LANGUAGE B`, `DEMO LANGUAGE C`; two certifications `DEMO RATING 1`,
`DEMO RATING 2`; four genres `DEMO GENRE 1` .. `DEMO GENRE 4`; two formats `DEMO FORMAT 1`,
`DEMO FORMAT 2`; across eight films `DEMO MOVIE 01` .. `DEMO MOVIE 08`. **All eight are published,
against a repo-committed placeholder poster, and all eight are inside their display windows**, so all
eight pass `P-BRW-01`'s two gates — that is `P-XCT-30`'s guarantee and not an assumption made here.

```
languages       3 returned  ->  3 >= 2  ->  the language filter RENDERS
formats         2 returned  ->  2 >= 2  ->  the format filter RENDERS
certifications  2 returned  ->  no certification filter exists in v1 (SRC-001 §5.1.3 names four
                                filters and certification is not one); the array is returned and
                                the same "in use" rule governs it
cinemas         1 returned  ->  1 <  2  ->  the cinema filter does NOT render (FR-ADR-046)
genres          all 4 are referenced by at least one visible film

the two format rows come from SHOWTIMES, not from films: P-XCT-30 alternates
DEMO FORMAT 1 and DEMO FORMAT 2 across each hall's showtimes, so both are
carried by at least one showtime of a visible film that is not past its cut-off
```

**Every one of the twelve seeded lookup rows is reachable, so none is omitted and every control that
can render does — but it is reached two different ways, and the difference is not cosmetic.**
`language`, `certification` and `genre` hang off the **film**, and `P-XCT-30` assigns those
deterministically so every film carries one language, one certification and two genres. **`format`
does not hang off the film at all** — it is an attribute of the **showtime** (see the `ASSUMED`
placement note below), so no film "carries a format" and no per-film assignment could ever put one
in use. `P-XCT-30` alternates the two `DEMO FORMAT` rows across each hall's showtimes instead, which
is what makes `formats` return two here.

*(An earlier revision of this example said every film carries one of each vocabulary. That was false
for `format` by construction, and it is corrected rather than quietly overwritten: had the seed
actually assigned formats per film, `EP-BRW-07.formats` would have returned nothing, the format
control would not have rendered, and this example would have asserted a screenshot the seed could not
produce.)*

**The catalogue this example runs over is `ASSUMED`, and its counts are not a constraint.** The names
are placeholders (`SRC-003 OPEN-SEED-01`), and `OPEN-ATTRIB-01` — still **open** — is why they must
stay placeholders; the client replaces the whole catalogue the moment they supply real content.
**The rule above is what is specified; 3, 2, 4 and 2 are what today's seed happens to produce.** Seed
one language instead of three and the language control stops rendering, correctly, with no rule
changed.

```
withdraw DEMO LANGUAGE C  (is_active = false, P-ADM-24)

  while any visible film still carries it   ->  STILL RETURNED here, and still filterable
  the admin's film form's language select   ->  it is gone from the options
  when the last such film leaves its window ->  it disappears from this endpoint too,
                                                on the visibility rule and not on is_active
```

**The `cinema` rule is the build session's, by symmetry**, and it is flagged rather than presented as
derived: the brief's definition covers the four lookup vocabularies, and `EP-BRW-07` also returns
`cinemas`. Giving cinema any other test — every cinema row, say — would let the control render for a
venue with nothing showing, which is the exact failure the omission rule exists to prevent. It is a
`[JUDGMENT CALL]`, recorded in the lane notes, and reversing it changes one predicate.

**`genre` has no array on `EP-BRW-07` in v1**, because no genre filter exists (`SRC-001 §5.1.3`) and
`P-BRW-02` already ships each film's genre names on the film itself. The rule is stated above so that
adding the array later needs no new rule and cannot acquire a different one.

**Where `format` lives — `ASSUMED`.** No frozen source and no ADR says whether format is a property of
the movie or of the showtime. `FR-ADR-021` enumerates the movie's fields and format is not among them.
It is specified here as a **lookup table referenced from the showtime**, because one film is routinely
shown in two formats in two halls on the same day, and putting it on the movie makes that
unrepresentable. **The value vocabulary is not invented** — no format rows are seeded
(`FR-ADR-067` seeds structure, never content), the admin creates them, and until two exist the control
does not render. This placement is `ASSUMED` and is raised in the lane notes.

**Filters combine with AND.** Two values for one filter are not supported in v1; each parameter takes
one id.

**An absent `date` on the listing means every date, and there is no default.** `EP-BRW-01`'s `date` is
optional, and when it is absent **no date predicate is applied at all** — the listing returns every
currently visible film regardless of when its showtimes fall. **It does not default to today.**
`SCR-BRW-01` arrives in that state and renders `Any date` selected (`SCR-BRW-01`).

**This is the opposite of `EP-BRW-04`'s rule, and the difference is deliberate.** The showtime list
defaults an absent `date` to **today in the cinema's zone** (`P-BRW-06`), because that endpoint
answers "when can I see this film" and a list of every showtime a film ever has is not an answer.
The listing answers "what is on", and the honest answer on arrival is everything. **Two endpoints,
two rules, stated together so neither is read as the other's oversight.**

**The three showtime filters are satisfied by ONE showtime, not by three different ones.** This is the
part a reader cannot infer from the parameter list, because `date`, `cinema_id` and `format_id` are all
properties of a **showtime** while the endpoint returns **movies**, and "AND" alone does not say
whether the conjunction is evaluated per showtime or per movie.

> **A movie is returned only when it has at least one showtime that satisfies every supplied showtime
> filter simultaneously.** The existence test is `EXISTS (one showtime matching date AND cinema AND
> format)`, never three independent existence tests.

`language_id` is the exception, and only because it is not a showtime property: it is an attribute of
the movie (`P-BRW-02`) and is applied to the movie row directly. So the predicate is: *the movie
matches `language_id`, and the movie has at least one showtime matching all of the supplied `date`,
`cinema_id` and `format_id` at once.*

**Why the other reading is wrong.** A customer setting a date and a format is asking one question —
"what can I actually watch, in that format, on that day". The independent reading answers a different
one — "which films have something on that day, and separately have something in that format ever" —
and returns films the customer cannot book on the terms they asked for. They then open the film, find
no showtime that matches, and conclude the listing is broken. **A filter that returns results the
next screen contradicts is worse than a filter that returns nothing.**

**Worked example — one showtime must carry all of it.** A film with exactly two showtimes:

```
showtime 1   Monday 2026-08-17   Hall 4   format = 2D
showtime 2   Tuesday 2026-08-18  Hall 4   format = 3D
```

| Query | Independent reading (rejected) | **This specification** |
|---|---|---|
| `date=2026-08-17` | the film | **the film** — showtime 1 matches |
| `format_id=<3D>` | the film | **the film** — showtime 2 matches |
| `date=2026-08-17&format_id=<3D>` | the film — Monday is satisfied by showtime 1, 3D by showtime 2 | **nothing.** No single showtime is both Monday and 3D |

**Expected answer for the third query: an empty list, `count = 0`.** The film is not returned, and it
is not returned with a note either — a movie in the list is a movie the customer can act on.

**What the customer sees when that happens.** Exception path 1 below: 200 with an empty list, the line
`Nothing is showing for the chosen filters.` and a control reading `Clear filters` (`SCR-BRW-01`). It
is the ordinary filtered-empty state; **no special wording exists for "your filters were satisfied
separately but not together"**, because that sentence explains the implementation to a customer who
did not ask about it, and the remedy — clear or change a filter — is identical either way.

**Who may do it.** guest · customer · manager · admin. Public.

**Preconditions.** None that can fail silently. The reference data endpoint tells the interface which
controls to render; **when it is unreachable the screen still renders and says so** — exception 5
below, which exists because this precondition previously had no failure path at all.

**Happy path.**
1. The customer changes a control.
2. The client re-requests the listing with the parameter set.
3. The server applies the visibility predicate, then the filters, then the order from `P-BRW-03`.
4. The result renders. The order is unchanged by filtering.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | The filter combination matches nothing | 200, empty list | "Nothing is showing for the chosen filters." with a control reading "Clear filters" |
| 2 | `date` is not an ISO-8601 date | 422 `VALIDATION_FAILED` | "That date is not valid." |
| 3 | `language_id`, `format_id` or `cinema_id` is not a positive integer | 422 `VALIDATION_FAILED` | "That filter is not valid." |
| 4 | An id is well-formed but matches no row | 200, empty list | as row 1. An id for a deleted row cannot occur — nothing is deleted (`FR-ADR-012`) |
| 5 | `EP-BRW-07` fails while the listing query succeeds | the listing returns 200 unaffected; `EP-BRW-07` returns 503 `DEPENDENCY_UNAVAILABLE` | the listing renders **in full**, **no reference-backed filter control renders**, and one line reads "Filters are unavailable right now." The date strip and `Clear filters` are unaffected |

**A reference outage and an empty vocabulary render the same controls, so they may not render the same
screen.** Day one and a 503 from `EP-BRW-07` both produce a listing with no language, format or cinema
control — and this row says in terms that the day-one rendering is **correct** and carries **no
message**. With no difference between them a guest cannot tell a working product from a degraded one,
and neither can an operator holding a screenshot. **One published line is the entire difference**:
`Filters are unavailable right now.` It states the fact and claims no cause, in the form
`P-BRW-08`'s banner already uses. **`SCR-BRW-01` owns the string** (`S1.2.1` case 3) and publishes it
in its copy table; no other section may publish a variant, and nothing else about the screen changes.

**Three things are deliberately unaffected**, because none of them reads the reference data:

- **The listing itself.** `EP-BRW-01` reads no vocabulary, and a filter already in the URL is still
  applied in SQL — a guest arriving on a shared link carrying `language_id` gets the filtered listing
  they asked for, whatever the reference endpoint is doing.
- **The date strip.** It is computed from the injected clock and the `display_until` values the listing
  response already carries. It is the one filter that is not reference-backed, which this row states
  above, and an outage does not reach it.
- **`Clear filters`.** It renders whenever at least one filter is set and needs no vocabulary to unset
  one. Without it a guest whose URL carried a filter would hold a filter they can neither see nor
  remove — the failure this row already names when a selected day leaves the strip: **a control that
  vanishes along with the thing it repairs cannot repair it.**

**`[JUDGMENT CALL]` — the line, not the behaviour.** That the controls are absent is `FR-ADR-046`
applied to a vocabulary the client could not read, and it follows. **Whether the screen says so is
what is decided here**, because no source addresses it and the alternative is two states that are
byte-identical on screen and mean opposite things. It is recorded in the lane notes. Reversible: one
string and one condition.

**Server-side validation.** `date` is an ISO-8601 calendar date, `YYYY-MM-DD`, parsed strictly; a
datetime, an offset or a zone name in that field is rejected rather than coerced. The three id
parameters are positive integers. **Client-side filtering is never the enforcement point** — the
listing endpoint applies every filter in SQL, because the same endpoint serves a caller with no
interface at all.

**Worked example — how `date` becomes an instant range.** The customer picks `date=2026-08-14`.
Asia/Kolkata is a fixed +05:30 with no daylight saving (`FR-ADR-018`), and the cinema's zone name is
read from the cinema row, never hardcoded.

```
local day  = [2026-08-14T00:00:00+05:30, 2026-08-15T00:00:00+05:30)
as instants= [2026-08-13T18:30:00Z,      2026-08-14T18:30:00Z)
predicate  = starts_at >= 2026-08-13T18:30:00Z AND starts_at < 2026-08-14T18:30:00Z
```

A show starting 23:45 local on 2026-08-14 is `2026-08-14T18:15:00Z` and falls inside. A show starting
00:10 local on 2026-08-15 is `2026-08-14T18:40:00Z` and does not. Taking the boundary in UTC would put
the second show on the customer's 14th, which is the defect `FR-ADR-018` exists to prevent.

---

### `P-BRW-05` · Let anyone browse the whole read path with no account, and stop them at the hold · `RULED`
`[SRC: SRC-001 §4.1 · SRC-001 §2.1 · SRC-001 §2.5 · SRC-003 OPEN-ROLE-01 · SRC-003 OPEN-BOOK-02 · FR-ADR-014 · FR-ADR-046 · FR-ADR-017]`
`[BRD: R-BRW-01]`

**Behaviour.** Every endpoint in this epic is public. A guest reaches the listing, the showtime list
and the **seat map** with no account, no token and no cookie. Nothing in the read path distinguishes a
guest from a signed-in customer, and no response varies by who is reading it.

**A guest cannot hold a seat.** The stop is at the hold — the first action that takes a seat out of
sale — not at the seat click and not at payment (`FR-ADR-014`, `FR-ADR-046`). The hold endpoint is
lane E2's and returns 401 `AUTH_REQUIRED` to an unauthenticated caller.

**What a guest sees on the seat map.** The complete map: every seat, every state, the categories, the
legend, the prices, and the closed or sold-out banner. Two differences, both client-side:

- **No seat is ever `held_by_me` for a guest.** That state is computed on the client from a hold token
  (`FR-ADR-045`) and a guest holds none. A guest's clicks are a local selection only.
- **The primary action reads `Sign in to hold these seats`** (`FR-ADR-046`), so the requirement is
  stated before it is enforced rather than discovered by pressing.

The selection survives the sign-in round trip in `sessionStorage`, and the hold is **not** taken
automatically on return (`FR-ADR-046`). That flow is lane E2's; it is named here only because the
guest's view of this epic's screens is what makes it necessary.

**Who may do it.** guest · customer · manager · admin. `auth: public` on the router. There is no
per-handler check, because there is nothing to check (`SRC-001 §7.4`).

**Preconditions.** None.

**Happy path.**
1. A visitor with no session opens the listing, chooses a movie, chooses a date, chooses a showtime.
2. The seat map renders and polls exactly as it does for a signed-in customer.
3. The visitor presses the primary action and is taken to the authentication step.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | A guest calls the hold endpoint directly | 401 `AUTH_REQUIRED` (lane E2) | "Sign in to hold seats." |
| 2 | A signed-in customer's token has expired while browsing | nothing — the read path never reads a token | no change; the map keeps working. The expiry surfaces at the hold, not here |

**Server-side validation.** None. The absence of an authorisation dependency on these routes is
itself the thing a reviewer checks: **a read route in this epic that grew an auth dependency is a
defect**, because it would break `SRC-001 §4.1`.

**Worked example.** Not applicable.

---

### `P-BRW-06` · List every showtime for a chosen movie and date, in Asia/Kolkata · `RULED`
`[SRC: SRC-001 §5.1.4 · SRC-003 OPEN-LOCALE-01 · SRC-003 OPEN-SCOPE-01 · FR-ADR-018 · FR-ADR-010 · FR-ADR-037]`
`[BRD: R-BRW-04]`

**Behaviour.** Choosing a movie and a date lists **every** showtime for that movie on that date across
all six halls, ordered by start time ascending, with the hall name and the base price against each.
Nothing is omitted for being nearly full, nearly over, or already closed.

**Each showtime in the list carries.**

| Field | Type | Notes |
|---|---|---|
| `id` | integer | public (`FR-ADR-017`) |
| `starts_at` | string | ISO-8601 **with the +05:30 offset**, e.g. `2026-08-14T19:30:00+05:30` |
| `ends_at` | string | same form; stored, never derived from runtime (`FR-ADR-018`) |
| `sales_close_at` | string | same form; derived at read time, never stored (`FR-ADR-042`) |
| `sales_closed` | boolean | the evaluation of `P-BRW-07` at request time |
| `screen` | `{id, name}` | the hall |
| `cinema` | `{id, name}` | present even though the filter is not rendered (`FR-ADR-010`) |
| `format` | `{id, name}` or null | see `P-BRW-04`; null until formats exist |
| `base_price_paise` | integer | the showtime's base price (`FR-ADR-037`). Category prices are on the seat map |

**Instants are serialised with the cinema's offset, not as `Z`.** The client formats the string it is
given and performs no zone arithmetic. A client converting UTC to local is a second implementation of
`FR-ADR-018` in a language with a different zone database, and it is the one that is wrong on a device
whose own clock is set to another country.

**The date strip is derived, not configured.** It runs from **today in Asia/Kolkata** to the **last day
of the movie's display window** — that is, the day before `display_until` (`P-BRW-01`). No horizon
constant exists, because inventing "the next 14 days" would be a number no source supports, and a
movie outside its window is not visible anyway. **This is `SCR-BRW-02`'s strip, where a movie has been
chosen.** The listing screen has no movie and takes its strip from `P-BRW-04`.

**Both browse paths to a date are bounded by the film's display window, so both assume every showtime
falls inside it — and no row in this document makes that true.** This strip ends at the last day of
the window, `P-BRW-04`'s listing strip ends at the last day of `max(display_until)`, and condition 2
below never searches past `display_until`. A showtime whose `starts_at` falls **outside** its film's
window is therefore reachable from **no guest browse surface at all**: not this strip, not the listing
strip, not the next-date button, and not the listing's `date` filter, because no control anywhere
offers the day. The showtime exists, it has a seat set, its sales are not closed, and only a
hand-typed URL finds it.

**The bound is not the defect and is not widened here.** Ranging a strip over `max(starts_at)` instead
would offer days on which the film has left its window — the button `P-BRW-04` refuses to draw, for
the reason stated there — and it would need a field no endpoint returns. **The condition belongs on
the write path**: a showtime outside the window is the admin having said two different things about
when the film runs, and `P-ADM-07` owns showtime creation. **This row states the dependency it has on
that check and does not restate the check**, which does not exist today and is raised against
`P-ADM-07`.

**This is not `OPEN-BRWVIS-01`, and conflating the two would park a fixable defect behind a reserved
row.** That row asks whether a showtime may still be sold **after** its film leaves the window — a
boundary the clock crosses, with a customer possibly mid-checkout. This is a showtime scheduled
outside the window in the first place: it is unreachable from the instant it is created, no clock
moves, and no policy has to be chosen to see that it is wrong.

**`next_date_with_showtimes` names the earliest date the customer can actually buy on, and this row
owns its definition.** It is **the earliest local date in Asia/Kolkata satisfying all three of the
following**, and all three are load-bearing:

1. **strictly after** the requested `date` — never the requested date itself, even when that date has
   showtimes, because the field exists to move the customer off a day that did not work;
2. **inside the movie's display window** — at or after `display_from`'s local date and at or before
   the last day of the window. **The search never runs past `display_until`**, which is what bounds it
   without a horizon constant;
3. holding **at least one showtime whose sales have not closed** at the moment of the request
   (`P-BRW-07`);
4. and that same showtime **matching every filter this request carried** — `cinema_id` and
   `format_id` where they were supplied, ignored where they were not.

**All four conditions are met by ONE showtime, not by four different ones**, exactly as `P-BRW-04`
rules for the listing's filters. A date whose 2D showtime is open and whose 3D showtime is closed is
not a match for `format_id=<3D>`.

**Condition 4 is condition 3's argument applied to the filters, and it was missing.** The endpoint
accepts `cinema_id` and `format_id`, and a filter-blind search hands the customer a date whose only
showtime is a format they did not ask for. They press the button, arrive, and read
`No showtimes on this date.` — **"a button that has moved them for nothing"**, which is this row's
own phrase for why condition 3 exists. The two failures are indistinguishable to the customer, so
they get the same rule.

**Condition 3 is the one an implementer drops, and dropping it is the whole defect.** The field drives
a button the customer presses (`SCR-BRW-02`'s `Next: Fri 15 Aug`). A date whose every showtime renders
`Closed` is a date the customer cannot buy on, so a button pointing at it is a broken button that has
moved them for nothing — and they cannot tell it is broken until they arrive. **The test is evaluated
against the injected clock**, so it is a live evaluation and not a property of the row.

**When no such date exists the field is `null`**, and it is `null` rather than absent or an empty
string so the client branches on one thing. A `null` means: nothing further in this window can still
be bought. `SCR-BRW-02` then renders no next-date button at all — exception 2 below — rather than a
button that goes nowhere.

**This test is not the same as "the date has showtimes".** A movie playing tomorrow whose only
tomorrow showtime has already closed skips tomorrow and names the day after, or `null` if there is no
day after inside the window. That is deliberate and it is the reason condition 3 is stated separately
from condition 2 rather than folded into it. **Condition 4 makes the field's answer depend on the
request**: the same movie, the same instant and a different `format_id` legitimately produce
different next dates, and `null` under one filter while another finds a date. That is correct — the
button belongs to the list the customer is looking at, not to the film in the abstract.

**Who may do it.** guest · customer · manager · admin. Public.

**Preconditions.** The movie passes `P-BRW-01`. The cinema row carries its zone.

**Happy path.**
1. The client requests showtimes for `movie_id` and `date`.
2. The server converts `date` to the instant range in the cinema's zone (`P-BRW-04`'s worked example).
3. Showtimes on that range for that movie are returned, ordered by `starts_at ASC`, then `id ASC`.
4. `sales_closed` is computed per row against the injected clock.
5. `next_date_with_showtimes` is computed by the **four** conditions above, against the same clock and
   against the same filters this request carried.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | No showtimes on the chosen date | 200, empty list, `next_date_with_showtimes` set | "No showtimes on this date." plus a button offering that date — **the next date whose sales are still open**, not merely the next date that has a showtime |
| 1a | The chosen date has showtimes but every one of them is closed | 200, the showtimes **are** returned and each renders `Closed` (`P-BRW-07`); `next_date_with_showtimes` still names the next buyable date | the list, all closed, plus the same next-date button. **The list is never emptied to force the customer forward** |
| 2 | No date strictly after the chosen one, inside the window, still has an open showtime | 200, empty list, `next_date_with_showtimes` **null** | "No showtimes for this movie." No next-date button is rendered, because there is no next date |
| 3 | The movie fails a visibility gate | 404 `NOT_FOUND` | "That movie is not showing." |
| 4 | `date` is malformed | 422 `VALIDATION_FAILED` | "That date is not valid." |
| 5 | PostgreSQL unreachable | 503 `DEPENDENCY_UNAVAILABLE` | "The site is temporarily unavailable. Please try again in a moment." |

**Server-side validation.** `movie_id` positive integer, required. `date` ISO-8601 calendar date; when
absent the server uses **today in the cinema's zone from the injected clock** — never the container's
date. `cinema_id`, `language_id`, `format_id` optional positive integers.

**Worked example — "today" is not the server's today.** The container runs in UTC. The injected clock
reads `2026-08-14T19:05:00Z`. In Asia/Kolkata that is `2026-08-15T00:35:00+05:30`, so **today is the
15th**, and a default request returns the 15th's showtimes. A server deriving the date from its own
clock would return the 14th's, which is a list of shows that have all finished.

---

### `P-BRW-07` · Show a closed showtime, marked closed, rather than hiding it · `PROVISIONAL`
`[SRC: SRC-003 OPEN-BOOK-03 · SRC-002 §7.1 · FR-ADR-042 · FR-ADR-018 · FR-ADR-045]`
`[BRD: R-BRW-04]`

> **⚠ `PROVISIONAL` — the direction of the cut-off could go either way.** The client answered
> `"yes 15 minutes"` to a question worded "before" against a recommendation worded "after"
> (`SRC-003 OPEN-BOOK-03`). This specification implements **after**. One message from the client
> reverses it, and the reversal is a change to one signed configuration value and two test assertions
> — no code path, no schema, no screen.

**Behaviour.** A showtime past its sales cut-off is **still listed and still opens its seat map**. It
is marked closed, its seats are not selectable, and a banner states it. Hiding it would make a customer
who saw it ten minutes ago conclude the site had lost it (`FR-ADR-042`, `FR-ADR-045`).

**The rule.**

```
sales_close_at = starts_at + SALES_CUTOFF_MINUTES
SALES_CUTOFF_MINUTES = +15        signed; a negative value gives the other reading
sales_closed   = NOT (T < sales_close_at)
```

- The offset is a **signed configuration value**, not a constant and not a literal in a comparison
  (`SRC-002 §7.1`, `FR-ADR-042`).
- `sales_close_at` is **derived at evaluation time and never stored**, so changing the configuration
  takes effect immediately with no backfill (`FR-ADR-018`).
- The boundary is exact: at `T = sales_close_at` the showtime **is closed**. Open is strictly
  `T < sales_close_at`.
- `T` is the injected clock. A test that reads the wall clock here is a defect (Art IX.5).

**This epic reads the flag; it does not enforce it.** Enforcement is at hold acquisition and is lane
E2's (`FR-ADR-042` checks at hold, not at confirm). `sales_closed` on a read response is presentation.
A client that hides the action is a convenience; the server refusing the hold is the rule.

**Who may do it.** guest · customer · manager · admin. Public.

**Preconditions.** The showtime exists and its movie passes `P-BRW-01` for the listing surface.

**Happy path.**
1. Each showtime returned carries `sales_close_at` and `sales_closed`.
2. A closed showtime renders in the picker with the word `Closed`, is not focusable, and does not
   navigate.
3. Its seat map, if reached directly by URL, renders in full with every seat unselectable and a banner.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | The showtime closes while the seat map is open | the next 3-second poll returns `sales_closed: true` | the banner appears and the map stops accepting taps: "Sales for this showtime have closed." |
| 2 | A customer holds seats when the cut-off passes | no change on this path — the hold survives (`FR-ADR-042`) | nothing from this epic. The countdown is lane E2's |
| 3 | A hold is attempted on a closed showtime | 409 `SALES_CLOSED` (lane E2) | `P-HLD-14` row 9's body — **not this row's banner**; see below |

**Ownership, declared. This row owns the sales-closed banner, and the complete set is one string:**

| Surface | What the user sees, verbatim |
|---|---|
| the banner on the seat map, on any screen at `/showtimes/{showtime_id}` | `Sales for this showtime have closed.` |

**No screen may publish a variant of it.** `SCR-BRW-03` and lane E2's `SCR-SEA-01` are **the same
screen at the same route** and each asserts their shared strings are byte-identical — and they then
published different sales-closed banners, which is exactly the defect both files say a variant is.
**A rank-2 row publishes this one and both screens are rank 3** (`S1.2`), so this string ships and
`SCR-SEA-01`'s time-naming variant is the defect. That correction is E2's to make in its own file.

**`P-HLD-14` row 9's longer 409 body is untouched and is not a variant of this.** It is an **API error
on a hold attempt** — a different surface with a different job, answering "why was my request
refused" rather than "why can I not act on this screen" — and it may name the time. One string per
surface, two surfaces, two strings, stated so the next reader does not converge them by mistake.

**Server-side validation.** `SALES_CUTOFF_MINUTES` is read at startup as a signed integer. A
missing or non-integer value **crashes the process at boot with a named message** (`SRC-002 §7.1`); it
does not fall back to 15, because a silent default is how the provisional reading becomes permanent.

**Worked example.** `starts_at = 2026-08-14T19:30:00+05:30`, `SALES_CUTOFF_MINUTES = +15`.

```
sales_close_at = 2026-08-14T19:45:00+05:30   (2026-08-14T14:15:00Z)

T = 19:44:59+05:30  →  T < close  →  sales_closed = false   (open)
T = 19:45:00+05:30  →  T = close  →  sales_closed = true    (closed)
```

Under the rejected reading, `SALES_CUTOFF_MINUTES = -15` gives
`sales_close_at = 19:15:00+05:30`, and the same showtime is closed at 19:20 rather than open. **The two
readings are half an hour apart** and both are testable with an injected clock.

---

### `P-BRW-08` · Serve the seat map as the real layout of the hall · `RULED`, on an `ASSUMED` hall size
`[SRC: SRC-001 §5.2.1 · SRC-003 OPEN-SCALE-02 · SRC-003 OPEN-SEAT-02 · SRC-003 OPEN-SEAT-03 · SRC-003 OPEN-SEAT-04 · FR-ADR-016 · FR-ADR-022 · FR-ADR-045]`
`[BRD: R-SEAT-01 · R-SEAT-07]`

**Behaviour.** The seat map endpoint returns the actual layout of the hall the showtime is in: the
same rows, the same seat numbers, the same aisles and gaps.

**What it renders is the showtime's seat set, not the screen's current seats.** A showtime's seat set
is materialised when the showtime is created and does not move afterwards; `P-ADM-14` owns that rule
and this row does not restate it.

**How the layout is represented on the wire.**

```json
{
  "showtime": { "id": 812, "starts_at": "2026-08-14T19:30:00+05:30", "sales_close_at": "2026-08-14T19:45:00+05:30", "sales_closed": false },
  "screen":   { "id": 4, "name": "Hall 4", "rows": 12, "cols": 22 },
  "categories": [ { "id": 2, "name": "Premium", "price_paise": 28124 } ],
  "seats": [
    { "id": 4821, "row": "C", "num": 12, "gr": 3, "gc": 14, "cat": 2, "price_paise": 28124, "state": "available", "is_active": true }
  ],
  "generated_at": "2026-08-14T19:30:02+05:30"
}
```

- **The `showtime` object on this response is four fields and no more** — `id`, `starts_at`,
  `sales_close_at`, `sales_closed`. It is **not** `P-BRW-06`'s showtime field list, which belongs to the
  showtime **listing**. `EP-BRW-06` owns this wire shape (`S1.2` rank 1) and the example above is
  written from it. The film, the hall and the base price reach this screen through `EP-BRW-05`, which
  is why that endpoint exists.
- **Every seat carries `price_paise` as well as `cat`, and it is already rounded.** The integer on the
  seat is that seat's price, computed by the server with `FR-ADR-038`'s rule against this showtime's
  `base_price_paise` and this seat's category uplift (`P-BRW-10`). It duplicates what the seat's
  category already implies, and it is sent anyway: `FR-ADR-038` requires **one** rounding rule with
  **one** implementation, and `FR-ADR-045` requires the client to perform no arithmetic of its own
  beyond summing. Sending the rounded per-seat integer is what makes both true — the client adds
  integers and can never disagree with the server by a paisa. Lane E2's `P-SEA-04` reads this field and
  cannot be implemented without it.
- **`categories` keeps its `price_paise` too**, because the legend names a band's price once rather
  than reading it off an arbitrary seat. The two are the same number by construction: both are the
  output of the same expression on the same inputs.
- **`row` and `num` are what the customer reads**; `gr` and `gc` are where the seat is drawn. They are
  separate values and they will not always agree, because a hall with a gap mid-row has a seat
  numbered 12 sitting at column 14 (`FR-ADR-016`).
- **An aisle, a gap and any non-seat space are the absence of a seat at a coordinate.** There is no
  placeholder object, no spacer seat and no "blocked" state (`FR-ADR-016`, `COMPONENTS.md §1.2`).
- **`rows` and `cols` are the grid extent, and they are DERIVED, not stored.** No `screen` row carries
  them — `EP-ADM-16` accepts only `cinema_id` and `name` — so the server computes them per response:

  ```
  screen.rows = max(gr) over this showtime's seat set
  screen.cols = max(gc) over this showtime's seat set
  ```

  They are sent so the client can size the grid before iterating the seats.
- **The maximum is taken over THIS SHOWTIME'S seat set, never over the screen's current seats**
  (`P-ADM-14`), and the difference is visible to a customer rather than internal. A seat added to a
  hall after this showtime was created is **not** in this showtime's set, so it must not widen this
  showtime's extent. Under the other reading it would, and the damage runs through the band
  derivation: `P-BRW-16` walks `gr` ascending **across the grid extent `screen.rows` gives**, so the
  walk would visit grid rows holding no seat of this showtime, classify each as a **void row**, and
  — because a void row does not break a band but does occupy vertical space — **draw the band gaps
  and the dashed category rules in different places than the seats warrant.** `P-BRW-10` makes band
  position the **primary non-colour carrier of seat category**, with no per-category colour token
  (`FR-ADR-072`), so a band rule in the wrong place is not cosmetic: it tells a customer who does not
  perceive colour that a seat is in a different price band than it is.
- **Both are therefore stable for the life of the showtime**, exactly as the seat set is. An admin
  adding a seat to a frozen hall changes future showtimes' extents and no existing one
  (`P-ADM-14`). A seat **retired** later changes neither: it stays in the set, so it stays in the
  maximum.
- **Sorting is server-side**: `seats` arrives ordered by `gr ASC, gc ASC`. The client renders in the
  order given. Sorting `A-2` after `A-12` is the default a string label produces and it is wrong
  (`FR-ADR-016`).
- **Every seat carries `is_active`, a boolean, and it is not a state.** It answers a different
  question from `state`: `state` says whether the seat is sold, held or free *for this showtime*,
  `is_active` says whether the seat is still in service in the hall at all. A seat retired after this
  showtime was created is returned with `is_active: false` (exception 3 below, `P-ADM-15`), it is not
  selectable, and **it still carries its true `state`** — which may be `sold`, because a customer may
  already have paid for it. Why this is a field and not a fifth `state` value is argued in `P-BRW-09`;
  the short form is that a fifth enum value would make "retired" and "sold" mutually exclusive and the
  seat can be both. It costs 18 bytes a seat, counted in `P-BRW-13`.
- **What is deliberately not in the payload**: no accessible-seat flag, no pair linkage, no gap rule,
  no fifth **state** (`SRC-003 OPEN-SEAT-02`, `-03`, `-04`). `is_active` is not one — the state enum is
  still exactly three values wide on the wire and four as rendered.

**The layout is stable for the life of the showtime.** Once a showtime exists on a screen, seats
cannot be removed, renumbered or moved between categories (`FR-ADR-022`, `P-ADM-14`). The read path
therefore never has to reconcile a map with a booking that references a seat that no longer means what
it did.

**Who may do it.** guest · customer · manager · admin. Public — the seat map is public to guests
(`FR-ADR-014`), which is also why the endpoint is cacheable across viewers (`FR-ADR-030`).

**Preconditions.** The showtime exists and its seat set is non-empty (`P-ADM-14`, which materialises
the set; `P-ADM-07` exception 5, which is why it can never be created empty).

**Happy path.**
1. The client requests the map for a showtime id.
2. The server returns the layout, the categories with prices, and **one entry per seat in this
   showtime's seat set** (`P-ADM-14`).
3. The client draws the grid at the coordinates given, with the row letter pinned in the gutter.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | The showtime id does not exist | 404 `NOT_FOUND` | "That showtime could not be found." |
| 2 | The showtime's seat set is empty | 500 `INTERNAL_ERROR` | "The seat map could not be loaded." plus "If you need help, quote `a1b2c3d4`." |
| 3 | A seat is retired (`is_active = false`) after the showtime was created | 200; **the seat is present in `seats`, carrying `is_active: false` and its true `state`** | **still present, drawn out of service, not selectable** — it is in this showtime's seat set, and that set was fixed at showtime creation (`P-ADM-14`; `P-ADM-15` owns the retirement itself). **The occupancy denominator is the dashboard section's** (`P-RPT-04`) — this row states only which seats reach the payload |
| 4 | **Every** seat in the showtime's seat set has since been retired | **200 with a complete map** — every seat present, every one carrying `is_active: false` and its true `state`. **Not a 500** | the full grid draws, every cell in the out-of-service treatment, nothing selectable, plus a banner: "None of the seats in this hall are available." **This string is new** — see the note below |

**Rows 2 and 4 sit one word apart and mean opposite things, so both are written out.** The fault
condition is an **empty seat set on the showtime** — zero rows — and nothing else. A seat set whose
every member has since been retired is **not empty**; it is a full set of unavailable seats, and it
returns 200.

- **Row 2, the 500, is unreachable for any showtime created normally**, because a showtime cannot be
  created on a screen with no active seats: `P-ADM-07` exception 5 refuses it with **"This hall has no
  seats in service. Add seats before creating a showtime on it."**, and `P-ADM-14` then materialises
  the set from seats that exist. **Those are two different rows doing two different jobs** — one keeps
  the set from starting empty, the other fixes what is in it — and this row is unreachable only
  because both hold. It stays
  specified anyway: **an unreachable fault that nothing handles is how a 500 becomes a blank page.**
- **Row 4 is reachable at any time**, because retiring seats is permitted on a screen that already has
  showtimes (`P-ADM-14`, `P-ADM-15`) and nothing stops an admin retiring the last one.

Row 2 is also the reason **"empty" is not a valid state for this screen**. A showtime always has a hall
and a hall always has seats; an empty seat list is a fault, not an empty state (`COMPONENTS.md §1.8`).
Row 4 is not an empty state either — it is a **full** map that happens to offer nothing, which is the
same shape as the sold-out case and is treated the same way: the customer sees the room.

**The row 4 banner copy is new, and it is published here.** This section already publishes
`Every seat for this showtime is sold.` and `Sales for this showtime have closed.`, and **neither is
true here** — nothing was sold and sales have not closed, so reusing either would be a false statement
about why the customer cannot book. The new string is
**`None of the seats in this hall are available.`** It states the fact and claims no cause, because
this row does not know one. It renders in the same banner as the other two (`SCR-BRW-03`), and
**`P-BRW-08` owns it**; no other section may publish a variant.

**Server-side validation.** `showtime_id` is a positive integer; anything else is 422
`VALIDATION_FAILED` before any query runs.

**Worked example.** Not applicable — this spec computes no number. The payload size arithmetic is in
`P-BRW-13`.

**`ASSUMED` flag.** Hall sizes of 90/120/150/180/200/220 are the build session's choice — the client
said "pick random" (`SRC-003 OPEN-SCALE-02`). **No layout decision may depend on those exact numbers.**
The 220-seat hall on a 375-pixel-wide phone is the design target, and it is the number every payload
and bandwidth figure in this section rests on.

---

### `P-BRW-09` · Serve three objective seat states, and let the client compute the fourth · `RULED`
`[SRC: SRC-001 §5.2.2 · SRC-002 §8.2.1 · FR-ADR-045 · FR-ADR-030 · FR-ADR-051]`
`[BRD: R-SEAT-01 · R-SEAT-06]`

**Behaviour.** The customer sees **exactly four** seat states (`FR-ADR-045`). The server sends
**three**, because the cached map is shared by every viewer of the showtime and carries objective state
only (`FR-ADR-030`).

| On the wire | Rendered as | Selectable | Mark (non-colour cue) |
|---|---|---|---|
| `available` | `available` | yes | none — the cell is empty except its number |
| `held` — and the caller does not own it | `held_by_other` | no | one solid horizontal bar |
| `held` — and the caller owns it | `held_by_me` | yes, to give the seat back | a tick |
| `sold` | `sold` | no | diagonal hatching |

**`held_by_me` is computed on the client** by intersecting the seat ids in the response with the seat
ids in the caller's own hold token (`FR-ADR-045`). The server never personalises this response. Sending
it per-viewer would make the cache useless and multiply the largest read in the product by the number
of people looking at it.

**Every state carries a non-colour cue as well as a colour** (`FR-ADR-045`, `FR-ADR-051`). Colour is
the third, redundant carrier. A state distinguished by hue alone fails a colour-blind customer and
fails again on a phone in sunlight, and `SRC-001 §5.2.2` asks for *clearly* distinguished.

**No fifth state exists.** Not a blocked seat, not an accessible seat, not a used ticket
(`SRC-003 OPEN-SEAT-02`, `SRC-003 OPEN-TICKET-02`). Four is a ruling, not a starting point.

**An out-of-service seat is carried by a boolean, not by a fifth state — and the reason is that the
two facts are independent.** `P-BRW-08` exception 3 and `P-ADM-15` require a seat retired after this
showtime was created to be **returned and drawn, not selectable**. That fact has to reach the wire,
and there are exactly two shapes available:

| Shape | Why it was or was not adopted |
|---|---|
| a fifth `state` value, `retired` | **rejected.** `state` is one value per seat, so `retired` would displace `sold` — and a retired seat can be sold, because `P-ADM-15`'s whole reason for keeping it is that a customer may already have paid for it. The payload would then lose the one fact the customer most needs, and the row that owns the seat's identity would contradict the row that owns its sale state. It also breaks `FR-ADR-045`'s ruled count of four rendered states, which is a ruling and not a starting point |
| **a separate boolean `is_active` — adopted** | the two facts are orthogonal and are carried orthogonally. The `state` enum stays exactly three values wide on the wire and four as rendered, `FR-ADR-045` is untouched, and a seat can be both retired and sold without either fact being lost |

**`[JUDGMENT CALL]` — the build session's under Art III.9.** No frozen source and no `APPROVED` record
names a wire shape for a retired seat; `P-ADM-15` names the behaviour and `FR-ADR-045` fixes the state
count, and the boolean is the only shape that satisfies both. What is **not** decided here is anything
about accessible seats, blocked seats or seat holds for maintenance — `is_active` carries one fact,
"this seat is no longer in service in this hall", and nothing else (`SRC-003 OPEN-SEAT-02`).

**How a retired seat renders and behaves.**

| Fact | Rule |
|---|---|
| Selectable | **never**, in any `state`, for any role — the client does not offer it and the hold endpoint rejects it |
| Fill | none. The cell is drawn as an outline only, 1px **dashed** `--fr-rule`, so the page ground shows through |
| Mark (non-colour cue) | the dashed outline itself, which is distinct in shape from *none*, *bar*, *hatch* and *tick* — the four marks already spent |
| Number | shown, in `--fr-ink-muted` |
| Accessible name | `Row C seat 12, Premium, out of service` |
| Legend | gains a fifth swatch reading `Out of service`. **This does not make a fifth state**: anything drawn differently has to be named, or the customer is left to guess what the dashed cell means |
| `state` on the wire | unchanged and truthful. The sale state is not overwritten and is not suppressed; it is simply not what the cell is drawn from |

**Who may do it.** guest · customer · manager · admin. Public. A guest receives the identical payload
and renders no `held_by_me`, because they hold nothing (`P-BRW-05`).

**Preconditions.** As `P-BRW-08`.

**Happy path.**
1. The server derives each seat's state: `sold` if a booking row exists for `(showtime_id, seat_id)`,
   otherwise `held` if a live Redis lock exists for it, otherwise `available`.
2. The response is cached under `cache:seatmap:{showtime_id}` (`FR-ADR-030`).
3. Every viewer receives the same three-state map.
4. Each client overlays its own holds at render time.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | A seat changes state between two polls | 200 with the new state | the cell keeps a 2px ring for `--fr-motion-change` so the change is legible rather than a silent repaint |
| 2 | One of the **customer's own** seats changes under them | 200 | the seat mark is not enough: the error banner fires and names the seat (`COMPONENTS.md §1.7`). The wording is lane E2's, because it is a lost-hold message |
| 3 | Every seat is `sold` | 200 | the full map renders plus a banner: "Every seat for this showtime is sold." Never an empty state — the customer wants to see that it is genuinely full |
| 4 | Redis is unreachable | see `P-BRW-12` | — |

**Server-side validation.** The state enum is closed. A value outside `available | held | sold` is a
server fault, not a client concern; the response model rejects it before serialisation so a fourth wire
state can never leak into a client that has no branch for it. **`is_active` is a required boolean on
every seat** — required rather than optional, because an absent field a client reads as "true" makes a
retired seat selectable on any client that forgot the branch, and that is a seat sold in a hall it is
no longer in. The response model rejects a seat object missing it.

**Worked example.** Not applicable.

---

### `P-BRW-10` · Show the category and the exact price of every seat, already rounded · `RULED`, on an `ASSUMED` category list
`[SRC: SRC-001 §5.2.3 · SRC-003 OPEN-SEAT-01 · SRC-003 OPEN-PRICE-01 · SRC-003 OPEN-LOCALE-01 · FR-ADR-016 · FR-ADR-037 · FR-ADR-038 · FR-ADR-036 · FR-ADR-045 · FR-ADR-040]`
`[BRD: R-SEAT-03]`

**Behaviour.** A customer can see which category a seat is in and what it costs **before** choosing it
(`SRC-001 §5.2.3`). Category is carried by **band position and the legend**, never by a seat colour
(`FR-ADR-045`, `FR-ADR-072`).

**How a band is computed from this payload, what happens when the categories interleave, and what
orders the `categories` array is `P-BRW-16`'s**, which owns the derivation. This row owns the price and
the fact that position carries the category; it does not restate the method.

**The server sends the already-rounded price twice: on the category, and on every seat.** The seat
map's `categories` array carries `price_paise` computed by the server with `FR-ADR-038`'s rule against
this showtime's `base_price_paise`, and **each seat object carries its own `price_paise` — the same
already-rounded integer — alongside its `cat`** (`P-BRW-08`). A seat still references its category by
id, because the legend and the band layout are driven by the category and not by the seat.

**The per-seat integer is what makes the client's arithmetic-free rule true, and it is required by
lane E2.** `P-SEA-04` computes the running total by summing `price_paise` over the selected seats; with
the price only on the category the client would have to look the category up and multiply, which is
arithmetic the client is not allowed to do (`FR-ADR-045`) and a second place the rounding rule could be
re-implemented (`FR-ADR-038`). The redundancy is deliberate and it costs 20 bytes a seat, counted in
`P-BRW-13`.

**The client performs no rounding at all.** It sums integers. `FR-ADR-038`'s formula is a server rule;
a second implementation in TypeScript is a second chance to disagree with it by a paisa, and one paisa
of disagreement between the seat map and the checkout total is a dispute the operator cannot settle.
This is stricter than `COMPONENTS.md §0.4`'s "the client uses the same rule" and needs no signature
(Art III.10) — it removes the rule from the client entirely rather than duplicating it.

**Money is integer paise on the wire and a formatted string only at render** (`FR-ADR-036`). No float,
no decimal string, no pre-formatted currency in the payload. Rendered with Indian digit grouping in
`--fr-font-mono`.

**There is no tax line, no discount field and no booking fee, and no space is left for one**
(`SRC-003 OPEN-PRICE-02`, `SRC-003 OPEN-PRICE-03`, `FR-ADR-040`).

**Who may do it.** guest · customer · manager · admin. Public — seeing the price is part of deciding,
and a guest sees it (`FR-ADR-046`).

**Preconditions.** The showtime carries `base_price_paise`. Every seat carries a non-null category.
Every category carries `uplift_basis_points`.

**Happy path.**
1. For each category on the screen, the server computes
   `price_paise = (base_price_paise * (10000 + uplift_basis_points) + 5000) // 10000`.
2. The categories array is returned with those integers.
3. **Every seat object is stamped with the integer computed for its own category**, so no caller has to
   join the two arrays to know what a seat costs.
4. The legend names each band with its price; the seat map draws the bands with a gap and a dashed
   rule between them.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | A category's price has not arrived yet (partial render) | 200 | the legend's category rows show inset blocks; **no zero is displayed**, because a zero price is a wrong number, not a loading state |
| 2 | An admin changes an uplift while a map is open | the next poll returns the new price | the legend updates. Holds already taken are unaffected — the price is fixed at hold acquisition (`FR-ADR-035`, `FR-ADR-039`) |

**Server-side validation.** `uplift_basis_points` is a non-negative integer. `base_price_paise` is a
positive integer. Both are read as integers; no float enters the expression at any point. Every seat's
`price_paise` is a non-negative integer and is **the same value as its category's `price_paise`** in
the same response — the response model computes it once per category and stamps it, so the two can
never be assembled from two different expressions.

**Worked example.** Base price `24999` paise (₹249.99), the three seeded categories.

```
Standard   0 bp:  (24999 * 10000 + 5000) // 10000 = 24999   →  ₹249.99
Premium 1250 bp:  (24999 * 11250 + 5000) // 10000 = 28124   →  ₹281.24
Recliner 3333 bp: (24999 * 13333 + 5000) // 10000 = 33331   →  ₹333.31
```

**The Recliner line, digit by digit, because this is the one an earlier revision got wrong.**

```
24999 * 13333        = 333,311,667
            + 5000   = 333,316,667
            // 10000 =      33,331     ← the +5000 then floor IS half-up
                                        exact 33331.1667, so it rounds DOWN
```

*(This row published `33332` and `₹333.32` until this pass, and derived a three-seat total from it. Both figures were wrong and both are corrected here rather than quietly overwritten. It matters more than a typo would: `S1.5` transcribes tests directly from worked examples, so the two figures would have become two test assertions about money that disagree by a paisa.)*

**Both of the non-zero uplifts genuinely round, and they round in opposite directions**, which is why
both are shown. Premium's exact value is `28123.875` and half-up takes it **up** to `28124`.
Recliner's exact value is `33331.1667` and half-up takes it **down** to `33331` — the fractional part
is below a half, so the `+ 5000` does not carry (`FR-ADR-038`). A reader who assumes an uplift always
rounds up gets Recliner wrong by a paisa, which is exactly the error this row carried.

**The uplift is applied per seat, once, and the total is never rounded again.** A customer selecting
three Recliner seats sees `33331 × 3 = 99993` paise, ₹999.93 — **the sum of already-rounded per-seat
prices** (`FR-ADR-038`). That is why the multiplication is `33331 × 3` and never
`(24999 × 3 × 13333 + 5000) // 10000`: rounding once per seat and rounding once per basket are
different numbers, and the per-seat integer is the one already on the wire (`P-BRW-08`).

**`ASSUMED` flag.** Standard, Premium and Recliner are the build session's names — the client said
"you pick" (`SRC-003 OPEN-SEAT-01`). They are rows in a table, not an enum, and **there is deliberately
no per-category colour token** (`FR-ADR-072`), so a fourth category costs an insert and no design
change. Nothing in this spec may make a fourth band expensive.

---

### `P-BRW-11` · Refresh the seat map every three seconds, pause it when nobody is looking · `RULED`
`[SRC: SRC-002 §8.6.1 · SRC-002 §8.6.2 · SRC-001 §3.3 · SRC-001 §7.3 · FR-ADR-045 · FR-ADR-030]`
`[BRD: R-SEAT-06]`

**Behaviour.** The seat map re-fetches itself every **`poll_interval_seconds`**, the value the
seat-map response itself carries — `SEATMAP_POLL_INTERVAL_SECONDS`, default **3**
(`SRC-002 §8.6.1`). Nothing the customer does triggers a refresh and **there is no manual refresh
control** — a refresh button implies the automatic one is unreliable (`FR-ADR-045`). Every "3 seconds"
below is that default rendered, never a literal in the client.

**Polling rules, all of them.**

- **Paused while the document is hidden**, resumed with an **immediate** fetch on becoming visible.
  A backgrounded tab polling for an hour is load on a `t3.micro` for somebody who is not looking, and
  nothing can be selected in a hidden tab so no accuracy is lost.
- **Continues while a hold is live**, because the countdown and the map are the same screen.
- **One in-flight request at a time.** A slow response does not queue a second poll behind it; the
  interval restarts when the response lands.
- **The client renders through a subscription-shaped interface** with the polling implementation behind
  it, so `SRC-002 §8.6.2`'s later switch to WebSockets is a contained change.

**Staleness is bounded, stated, and never shown to the customer.** Worst case is about **13 seconds**:
a 10-second cache TTL plus a 3-second poll interval (`FR-ADR-030`, `FR-ADR-045`). `SRC-001 §3.3` asks
for accuracy "within a few seconds" and 13 is at the edge of that. It is stated here rather than
rounded down, and it is the figure to revisit if the client finds the map feels wrong. **It is a
property of the system, not a message** — no interface element displays it.

**Staleness never causes an oversell.** A customer who taps a seat the map showed as free loses at the
Redis lock or at the unique constraint and is told (`SRC-001 §5.2.6`, lane E2). The cache affects what
someone sees, never what they get.

**Who may do it.** guest · customer · manager · admin. Public.

**Preconditions.** The seat map screen is open.

**Happy path.**
1. The map loads.
2. Every 3 seconds the client re-requests it.
3. Cells whose state changed keep a ring for `--fr-motion-change` and transition their fill over
   `--fr-motion-base`, so the eye can follow which cell moved.
4. The tab is hidden; polling stops. The tab is shown; a fetch fires immediately and the interval
   resumes.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | A poll fails (network or 5xx) | — | **the last good map stays on screen.** A one-line strip appears at the top of the field: "The seat map is not updating. The seats shown may be out of date." Polling continues |
| 2 | Polls keep failing | — | the strip stays. The map is never blanked mid-selection; a few-seconds-old map beats no map |
| 3 | A poll returns 429 `RATE_LIMITED` | 429 with `Retry-After` | the strip appears and the client waits `Retry-After` seconds before the next poll rather than continuing at 3 seconds |
| 4 | The first load fails, **429 included** | 4xx/5xx | the map is replaced by "The seat map could not be loaded." and a control reading "Try again". No partial grid. **The rate-limited string is not rendered here** — see below |

**A 429 on a poll and a 429 on the first load are two situations, they take two different strings, and
this is where they are separated.** Exception 3 is a refused **poll**: a map is already on screen, the
loop is already running, and the next request goes out on its own — so `SCR-BRW-03`'s
`Too many requests. The seat map will update again shortly.` is a true sentence, and it is why
`SCR-XCT-03` publishes no variant for that surface and points here instead. Exception 4 is a refused
**first load**: there is no map on screen and **no poll loop exists yet**, so nothing will deliver the
update that sentence promises. It takes the first-load error and its `Try again`, which is the only
control that can produce the map at all. **A published string promising an action that nothing
performs is the defect this split closes**, and it was reachable — `SCR-XCT-03` sent every 429 on this
endpoint, first load and poll alike, to the polling sentence.

**Server-side validation.** **`SEATMAP_POLL_INTERVAL_SECONDS` is server configuration, validated at
boot, and returned to the client in the seat-map response.** The client polls at the interval it was
given and holds no constant of its own. Default **3**, from `SRC-002 §8.6.1`.

> **This overturns what this row said before**, which was that the interval is "a client constant… the
> server neither knows nor enforces it". That was wrong and it was wrong in a way that made another
> section meaningless: `S7.9`'s boot cross-check 10 validates this name as server configuration, and a
> boot check on a value the server does not hold cannot check anything. **One value governs.** The
> operator changes it in one place and every client follows on its next response — a client constant
> would have needed a redeploy of the frontend to change a number the backend already validates.

- **Returned in the seat-map payload**, so it needs no second request and cannot drift from the
  response it paces.
- **Enforcement stays where it was: nowhere.** The server *publishes* the interval; it does not police
  it. A client polling faster is handled by the rate limiter and by nothing else — an interval the
  server tried to enforce per-caller would be a second limiter with a different bucket.
- **The per-IP rate limit of 120 requests a minute on this endpoint (`FR-ADR-058`) is well above what
  one legitimate poller uses and is not above what six of them use. The worse number goes first**
  (Art VII.2): one viewer at the default uses `60 / 3 = 20` requests a minute, so the bucket holds
  `120 / 20 = 6` concurrent viewers from one address — of any showtime, since the bucket is keyed on
  the address and not on the showtime. **The two numbers are related and the relation is checked at
  boot**, not asserted here: `S7.9` cross-check 10 owns it, along with
  `SEATMAP_CACHE_TTL_SECONDS + SEATMAP_POLL_INTERVAL_SECONDS <= 15`, which is the staleness bound this
  row states above.
- **There is no per-user bucket on this endpoint, so guests sharing one public address share one
  bucket — and the seventh is refused the central screen of the product.** The endpoint is
  unauthenticated (`P-BRW-05`), so there is no user to key a second bucket on (`EP-BRW-06`,
  `P-XCT-07`), and an office, a household, a campus or a mobile carrier NAT presents one address for
  everybody behind it. What the seventh viewer sees is already specified and is not a new state:
  exception 3 if their map is up — the last good map stays and the client waits `Retry-After` — and
  exception 4 if they are still loading, which is the first-load error with a `Try again` that will
  keep being refused for as long as the address stays at its limit.
- **This document does not change the number, and says so rather than working around it.** `120` per
  minute per IP is `FR-ADR-058`, an `APPROVED` record; lengthening the poll interval to fit more
  viewers per address trades directly against the staleness bound above and `SRC-001 §3.3`. **Six is
  derived from two configured numbers, not measured** — nothing in this project has run in AWS — and
  it is what the Phase 3 measurement (`P-BRW-14`) should be read against.

**Worked example — worst-case staleness, derived.**

```
t = 0.0s   a booking commits; the DEL of the cache entry fails (a Redis blip)
t = 0.0s   the cache entry survives with 10.0s of TTL left
t = 10.0s  the entry expires; the next miss rebuilds from PostgreSQL
t = 12.9s  a poller whose interval last fired at t = 9.9s fetches the fresh map
           worst case ≈ 10s TTL + 3s interval ≈ 13s
```

---

### `P-BRW-12` · Cache the read path, and state exactly what happens when Redis is gone · `PROVISIONAL` on one branch
`[SRC: SRC-002 §8.2.1 · SRC-002 §8.2.2 · SRC-002 §8.2.3 · SRC-002 §7.9 · SRC-002 §7.4 · FR-ADR-030 · FR-ADR-028 · FR-ADR-058]`
`[BRD: R-SEAT-06 · R-QLY-04]`

**Behaviour.** Every read in this epic is cache-aside (`SRC-002 §8.2.1`).

| Cached thing | Key | TTL | Invalidated by |
|---|---|---|---|
| seat map | `cache:seatmap:{showtime_id}` | **10 s** | a `DEL` after a booking commits, and after a hold or release (`FR-ADR-030`) |
| movie list | `cache:listing:{generation}:{filter-fingerprint}` | **60 s** | **an `INCR` of the listings generation counter after the admin write commits** — never a `DEL` |
| showtime list | `cache:listing:{generation}:{filter-fingerprint}` | **60 s** | as the movie list — the same counter, the same key prefix |

- **Invalidation is a `DEL` issued after commit, never a `SET`.** A writer that computes and writes the
  new map can lose to a slower reader holding an older one; deleting cannot write a stale value
  because it writes nothing (`FR-ADR-030`).
- **A failed `DEL` is not retried and nothing is rolled back.** The entry expires within its TTL. The
  staleness is bounded and stated rather than unbounded and hidden.
- **Stampede guard**, and this is the place `SRC-002 §8.2.3` is about: on a miss, one caller acquires
  `cache:seatmap:{id}:rebuild` with `SET NX PX 2000` and rebuilds; callers that lose wait briefly,
  re-read, and on a second miss read PostgreSQL directly rather than queueing. **The code carries a
  comment naming the scenario** — the TTL expires on a popular Friday showtime and every in-flight
  poller rebuilds at once. That comment is a deliverable a reviewer checks for.

**The listings generation counter — this row owns the mechanism.** `P-XCT-08` owns single-key
invalidation and keeps its `DEL`-never-`SET` rule; `P-ADM-02` and `P-ADM-06` keep the word
*immediately* and point here for what makes it true. **None of them restates the key format, and this
row is where it is decided.**

**Why a `DEL` cannot do this job.** A `DEL` names a key. The seat map has exactly one key per showtime,
so naming it is possible. The listings are cached **per filter combination**, and the filter space is
the product of every date, every language id, every format id and every cinema id a caller may send —
an **unbounded keyspace that the writer cannot enumerate**. There is no set of names to delete, and
`SCAN`-and-delete over a keyspace of that shape is a scan of the whole Redis instance on every admin
write. So the entry is made **unreachable** instead of being deleted, which is the same idea `DEL`
serves — *never overwrite an entry with a value the writer computed* — reached by a different route.

**The mechanism, exactly.**

```
counter key   cache:listing:generation          a single Redis integer
listing key   cache:listing:{generation}:{filter-fingerprint}
```

- A listings read reads the counter, builds the key with the value it read, and caches under it with
  the 60-second TTL.
- **Every admin write that can change any listing `INCR`s the counter after its transaction commits.**
  The complete trigger set: a film created, edited, published or withdrawn; a showtime created, edited
  or cancelled; a poster replaced; a lookup row withdrawn or restored.
- After the `INCR`, every key of the previous generation is unreachable — **nothing reads them** — and
  they expire on their own 60-second TTL with no enumeration and no scan. **A read therefore never sees
  stale data, so `immediately` is literally true.**
- **The `INCR` is not a `SET`.** It publishes no content: it writes a number that names a namespace,
  never a listing body. The prohibition on writing a computed value into a cache entry is untouched
  everywhere, including here.

**The counter's initial value is `1`, and it is never reset.** A missing key `INCR`s to `1`, and that
is a correct new generation rather than an error — no bootstrap step and no seed row is required for
it. **Resetting it is forbidden**, because a reset makes a key of an old generation reachable again and
serves a listing that predates every write since.

The counter's three failure paths are exceptions 5, 6 and 7 in this row's exception table below.

**When Redis is unreachable.**

| Surface | Behaviour | Record |
|---|---|---|
| movie list, showtime list | **serve from PostgreSQL, slower.** A cache outage and a cache miss are the same event to a cache-aside reader | `FR-ADR-028` |
| seat map read | **503 `DEPENDENCY_UNAVAILABLE`** — see the flag below | `FR-ADR-058` |
| hold, confirm | 503, always. Never a database fallback for locks | `SRC-002 §7.9`, `FR-ADR-028` |
| `/health/ready` | 503, so the instance leaves the load balancer | `SRC-002 §7.4` |

> **⚠ `PROVISIONAL` — two `APPROVED` ADRs disagree about the seat map read. 503 is the adjudicated
> answer.** **The conflict in one sentence:** `FR-ADR-028` says in terms that "the seat map read path"
> keeps working from PostgreSQL when Redis is down, while `FR-ADR-058` lists that same read as a
> rate-limited endpoint at 120 per minute per IP whose limiter **fails closed with 503** when the
> bucket cannot be read — and because the limiter runs before the cache, the request never reaches the
> PostgreSQL fallback, so both cannot hold.
>
> **The merge pass adjudicated this as `X-7` and adopted 503**, on Art III.10: failing closed is the
> stricter of the two options and adopting a stricter option needs no signature. A seat map served
> while every hold against it is refused shows availability nobody can act on, which is the second
> reason. **This is no longer one lane's preference — it is the decision of record for this document**,
> and the rest of this row is written against it.
>
> **`FR-ADR-028`'s "browsing keeps working" survives, narrowed to exactly what it can cover.** It holds
> for the **movie list and the showtime list**, which are not in `FR-ADR-058`'s limited-endpoint table
> and which serve from PostgreSQL untouched. It does **not** hold for the **seat map**, which is the
> one endpoint the two records overlap on. The conflict is exactly one endpoint wide and so is the
> exception.
>
> **The marking stays `PROVISIONAL`** because the adjudication reconciles two immutable `APPROVED`
> records rather than replacing either, and one client message reverses it. Reversal is one branch in
> the limiter's failure handler and two test assertions; no schema, no screen, no other endpoint.

**Ownership, declared, in the form `S1.2` requires.** **This row owns the customer-facing message set
for `DEPENDENCY_UNAVAILABLE` on the seat-map read**, exactly as `P-HLD-14` owns the hold codes. It is
where `X-7` was adjudicated, so the sentence the customer reads in that situation is decided in the
same place the situation itself was decided. **The complete set is one string:**

| Code · HTTP | Situation | What the user sees, verbatim |
|---|---|---|
| `DEPENDENCY_UNAVAILABLE` 503 | the seat-map read or any of its polls, while Redis is unreachable | `The seat map is unavailable right now. You can still browse showtimes. Try again in a few minutes.` |

**No other section may publish a different string for that code on that endpoint.** Three did, and the
three had drifted apart: this row, `P-XCT-09` exception 2 and `SCR-BRW-03`'s copy table each carried a
different sentence for one situation, and **`S1.2` ranks the first two identically, so nothing in the
reading rules could resolve it.** Declaring an owner is what resolves it. `P-XCT-09` and `SCR-XCT-02`
now cite this row instead of restating it, and `SCR-BRW-03` renders the string above. **A variant found
anywhere is a defect in the copy that differs, never in this row** (`S1.2`, rank 4).

Two strings that are **not** in this row's set, so the boundary is not guessed at: the generic
rate-limited-path sentence for every *other* limited endpoint stays `P-XCT-09`'s, and the hold and
confirm sentences stay `P-HLD-14`'s. This row owns one code on one endpoint.

**Who may do it.** guest · customer · manager · admin. Public.

**Preconditions.** None. A cold cache is a normal state.

**Happy path.**
1. The read checks Redis.
2. On a hit it returns the cached body.
3. On a miss it acquires the rebuild lock, reads PostgreSQL, writes the entry with its TTL, returns.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | Redis unreachable, movie or showtime list | 200 from PostgreSQL | nothing. The page is slower and says nothing about it |
| 2 | Redis unreachable, seat map | 503 `DEPENDENCY_UNAVAILABLE` | "The seat map is unavailable right now. You can still browse showtimes. Try again in a few minutes." |
| 3 | PostgreSQL unreachable on a miss | 503 `DEPENDENCY_UNAVAILABLE` | "The site is temporarily unavailable. Please try again in a moment." |
| 4 | The rebuild lock is not acquired and the second read still misses | 200 from PostgreSQL | nothing. Nobody blocks on a lock they cannot get |
| 5 | The post-commit `INCR` of `cache:listing:generation` fails | **the write is not rolled back and the `INCR` is not retried.** Listings are stale for at most `LISTING_CACHE_TTL_SECONDS` (60 s), logged at warning with the write's request id | *(no user-facing surface — a bounded, stated staleness, the same treatment `P-XCT-08` exception 1 gives a failed `DEL`)* |
| 6 | Redis is unreachable on a listings read | every read is a miss and falls through to PostgreSQL; the listings keep working, slower. Same event as row 1, stated again from the counter's side | *(no user-facing surface)* |
| 7 | Redis is unreachable at `INCR` time | as row 5: the write stands, the staleness is bounded by the TTL | *(no user-facing surface)* |

**Server-side validation.** None on a read path. `LISTING_CACHE_TTL_SECONDS` is configuration and not a
literal, as are the seat-map TTL and the rebuild-lock duration. `cache:listing:generation` is read as an
integer and an absent key is not an error — it becomes `1` on the next `INCR`.

**Worked example — polling bandwidth against the cache.** One busy showtime with 40 viewers, each
polling every 3 seconds, is `40 × 20 = 800` requests a minute. With a 10-second TTL the map is rebuilt
from PostgreSQL at most 6 times a minute; the other 794 requests are served from Redis. *(arithmetic
from the stated TTL and interval; not measured — nothing in this project has run in AWS.)*

---

### `P-BRW-13` · Paginate nothing, and state the payload size that decision rests on · `ASSUMED` on the figures
`[SRC: SRC-001 §7.3 · SRC-003 OPEN-SCALE-02 · SRC-003 OPEN-SCOPE-01 · FR-ADR-016 · FR-ADR-045 · FR-ADR-010]`
`[BRD: R-QLY-04 · R-SEAT-07]`

**Behaviour.** **Nothing in this epic is paginated.** Not the movie listing, not the showtime list, not
the seat map. No `page`, `offset`, `limit` or `cursor` parameter exists on any endpoint in S6.

**The seat map cannot be paginated, and that is not a preference.** A partial seat map is a wrong seat
map: a customer choosing where to sit needs the whole room, and a map arriving in pages would show
a hall that appears to have 60 seats. It is served whole, and it scrolls horizontally inside its own
container while the page body never does (`FR-ADR-044`, `COMPONENTS.md §1.3`).

**The movie listing is not paginated because the visible set is bounded by `P-BRW-01`'s two gates.**
One cinema with six halls shows what one cinema shows in one display window. The listing returns every
visible movie and a `count`. **No silent cap is applied** — a truncating limit with no pagination is
the worst of both, because the customer cannot tell that something was withheld.

**The observable that would reverse this**, stated so it is a measurement and not an opinion: when the
movie listing response for the default filters exceeds the seat-map response for a 220-seat hall, the
listing has become the largest read in the product and pagination is worth adding. That comparison is
made in Phase 3 against measured figures, not against the estimates below.

**Who may do it.** guest · customer · manager · admin. Public.

**Preconditions.** None.

**Happy path.**
1. The client requests a listing or a map.
2. The complete result is returned in one response.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | A caller sends `page` or `limit` | 200; unknown query parameters are ignored | nothing. The full result arrives |
| 2 | The visible set is very large | 200; the full set | a long scroll. **Nothing is truncated**, because a truncated listing that says nothing is a bug the customer reports as "the film is missing" |

**Server-side validation.** None. There is no pagination parameter to validate.

**Worked example — the seat-map payload at 220 seats.** Derived from the field list in `P-BRW-08`,
using the compact key names shown there.

```
one seat object, longest state string, longest is_active value,
with the per-seat price of P-BRW-10:
{"id":123456,"row":"C","num":12,"gr":3,"gc":14,"cat":2,"price_paise":28124,"state":"available","is_active":false},
                                                          = 114 bytes

  of which "price_paise":28124, is                        =  20 bytes
  of which "is_active":false,   is                        =  18 bytes
  the same object without either                          =  76 bytes
  ("is_active":true, is 17 bytes — one byte less, and every
   seat in a healthy hall carries true. 114 is the worst case
   and it is the number used below)

220 seats            220 × 114           =  25,080 bytes  ≈ 25 KB
showtime + screen + categories + envelope ≈  1,000 bytes
------------------------------------------------------------------
total per poll                            ≈ 26 KB uncompressed

one viewer, 20 polls a minute             ≈ 520 KB / minute
40 viewers on one busy showtime           ≈  21 MB / minute egress
```

**What the per-seat price costs, stated rather than absorbed.** The 20 bytes a seat that `P-BRW-10`
adds are **18 %** of the seat object and about **4,400 bytes** on a 220-seat map — roughly 4 KB a poll,
88 KB a minute for one viewer, 3.5 MB a minute across 40. That is the price of having one rounding
implementation instead of two (`FR-ADR-038`), and it is paid deliberately.

**What `is_active` costs, on the same terms.** The 18 bytes a seat are **16 %** of the seat object and
**3,960 bytes** on a 220-seat map — roughly 4 KB a poll, 79 KB a minute for one viewer, 3.2 MB a
minute across 40. That is the price of a seat that cannot be sold in a hall it has left
(`P-BRW-08` exception 3, `P-BRW-09`). **Neither field changes the pagination decision**: a 26 KB
response is still one response.

*(The seat object was previously counted here at 78 bytes without the price field, then at 96 with it.
Adding `is_active` takes the literal string above to 114. The corrected figures are used throughout
this row; the earlier ones are recorded rather than quietly overwritten, and no conclusion in this row
changes.)*

**These are derived from the stated encoding, not measured**, and they rest on the `ASSUMED` 220-seat
hall (`SRC-003 OPEN-SCALE-02`). Compression will reduce the wire figure substantially and **no
compression ratio is claimed here**, because none has been measured. `FR-ADR-045` requires this to be
measured in Phase 3 and the estimates replaced with real numbers.

---

### `P-BRW-14` · State the performance requirement as it is written, and invent no number for it · `RULED` in substance, `OPEN` in measure
`[SRC: SRC-001 §7.3 · SRC-001 §3.3 · SRC-002 §8.6.1 · FR-ADR-030 · FR-ADR-045]`
`[BRD: R-QLY-04]`

**Behaviour.** `SRC-001 §7.3` says pages should feel immediate and seat maps in particular must not
lag. That is the whole of the requirement.

**What is specified, with a source.**

| Fact | Value | Record |
|---|---|---|
| seat map refresh interval | 3 seconds | `SRC-002 §8.6.1` |
| seat map cache TTL | 10 seconds | `FR-ADR-030` |
| movie and showtime list cache TTL | 60 seconds | `FR-ADR-030` |
| worst-case seat map staleness | about 13 seconds | `FR-ADR-030`, `FR-ADR-045` |
| accuracy expectation | "within a few seconds" | `SRC-001 §3.3` |
| end-to-end booking target | under two minutes, from the seat map, for a signed-in customer | `SRC-001 §3.1` |

**What is not specified, and is not invented here.** **No frozen source states a latency budget of any
kind** — no p50, no p95, no time-to-first-byte, no render budget, no frames-per-second target for the
seat map, and no throughput figure. None is written in this document. A number invented here would be
indistinguishable from a ruled one three documents later, which is exactly the failure this project
already produced once with the seven-minute hold.

**What replaces a number**, so the requirement is still testable:

1. **The seat map is measured in Phase 3** — response time at the 220-seat hall, payload size, and
   cache hit rate — and the measured figures are written down (`FR-ADR-045` requires this).
2. **The frame never resizes when data lands.** The field, the screen bar and the row gutters draw at
   full size immediately, with seat cells as inset blocks; no spinner, because the layout is already
   the answer (`COMPONENTS.md §1.8`). This is a binary criterion and it is what "does not lag" means
   for the customer who is looking at it.
3. **The map is never blanked on a failed poll** (`P-BRW-11`).
4. **The peak-concurrency figure of 50 bookers is `ASSUMED`** and measures where performance degrades;
   it proves nothing about correctness (`SRC-003 OPEN-SCALE-03`, `FR-ADR-034`).

**Who may do it.** Not applicable — this specification constrains the build, not a user.

**Preconditions.** None.

**Happy path.** Not applicable.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | A measured figure turns out to be poor | — | nothing. It is recorded and reported with its count, worst number first (Art VII.2), not tuned away silently |

**Server-side validation.** None.

**Worked example.** Not applicable — there is no number to compute, and that is the point of this row.

---

### `P-BRW-15` · Serve posters from our own bucket by redirect, and never hotlink · `RULED`
`[SRC: SRC-002 §4.9 · SRC-002 §10.6.3 · SRC-002 §7.3 · SRC-003 OPEN-TMDB-01 · SRC-003 OPEN-ATTRIB-01 · FR-ADR-061 · FR-ADR-021]`
`[BRD: R-BRW-02]`

**Behaviour.** A poster is reached at `/api/movies/{movie_id}/poster`. The API responds **302** with a
`Location` header holding a presigned S3 GET URL valid for one hour. The bucket is private; there is no
public-read policy and no anonymous access (`FR-ADR-061`).

**Why a redirect rather than the bytes.** Proxying every poster spends the API's memory and its single
worker's time serving static files on a `t3.micro`. A redirect costs one small response and the browser
fetches from S3 directly.

**This is not hotlinking.** `SRC-002 §10.6.3` forbids serving a third party's URL from our pages, and
it survives the withdrawal of the section around it (`SRC-002 §E E-2`). Every poster URL points at our
bucket and is minted by us.

**Who may do it.** guest · customer · manager · admin. Public — the poster of a published movie is
public. A draft movie's poster is reachable by id, which discloses that a draft exists; that is
accepted for the same reason showtime ids are public (`FR-ADR-017`) and is noted in the lane notes.

**Preconditions.** The movie row carries a non-null `poster_object_key`. A published movie always does
(`FR-ADR-021`).

**Happy path.**
1. The client renders `<img src="/api/movies/11/poster">`.
2. The API mints a presigned GET URL for the stored object key and returns 302.
3. The browser follows it and fetches the image from S3.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | The movie has no `poster_object_key` | 404 `NOT_FOUND` | the poster box draws the perforation motif with the title inside it. No words, no broken-image glyph |
| 2 | The object is absent from S3 | the redirect is issued; S3 returns 403/404 to the browser | as row 1 — the image fails to load and the box keeps its reserved space |
| 3 | The movie id does not exist | 404 `NOT_FOUND` | as row 1 |
| 4 | S3 is unreachable when minting | presigning is local and does not call S3, so this cannot fail here | — |

**Server-side validation.** `movie_id` is a positive integer. The object key is read from the row and
**never taken from the request** — a client-supplied key is a path traversal in one field
(`FR-ADR-061`).

**Worked example — the cache lifetime, and its one hard bound.** The redirect carries
`Cache-Control: max-age=POSTER_REDIRECT_CACHE_SECONDS`, which **must be less than the presigned URL's
3600-second expiry**, or a browser will re-use a cached redirect whose target has expired and the image
will break. Starting value **300 seconds**, `ASSUMED` — no source states one — read from configuration
and tuned in Phase 6.

```
presigned URL expiry            = 3600 s   (FR-ADR-061)
POSTER_REDIRECT_CACHE_SECONDS   =  300 s   (ASSUMED)
300 < 3600  →  a cached redirect always outlived by its target
```

---

### `P-BRW-16` · Derive the category bands from the payload, and say what happens when they interleave · `RULED` in substance, `[JUDGMENT CALL]` in method
`[SRC: SRC-001 §5.2.3 · SRC-003 OPEN-SEAT-01 · FR-ADR-016 · FR-ADR-045 · FR-ADR-051 · FR-ADR-072]`
`[BRD: R-SEAT-03]`

**Why this row exists.** `P-BRW-10` makes **band position the primary non-colour carrier of category**,
and `FR-ADR-045` and `FR-ADR-051` make that an accessibility requirement rather than a decoration:
there is deliberately no per-category colour token (`FR-ADR-072`), so if the band is wrong the customer
has only the legend's prices left. `P-BRW-10` and `COMPONENTS.md §1.5` both say bands exist and neither
says **how one is computed from `gr`, `gc` and `cat`** — and because an admin may assign any category
to any seat at any coordinate (`P-ADM-15`, `FR-ADR-016`), a grid row can hold three categories and
"band position" then means nothing. **This row owns the derivation.**

**The derivation, in full.** It runs on the client, over the payload of `EP-BRW-06`, with no extra
request and no server field beyond what `P-BRW-08` already sends.

1. **A band is a run of consecutive grid rows that all carry exactly one category.** Walk `gr`
   ascending across the grid extent `screen.rows` gives. For each `gr`, collect the distinct `cat`
   values of the seats at that `gr`. **The derivation only ever compares `gr` values to each other and
   never assumes a first index**, so it is correct whichever base the payload numbers rows from.
2. **A grid row with exactly one distinct `cat` is a pure row.** Its category is that value.
3. **A grid row with no seats at all is a void row** — an aisle row, a walkway, the gap in front of a
   screen. It belongs to no band, is drawn as vertical space, and **does not break a band**: two pure
   rows of the same category separated only by void rows are one band.
4. **A grid row with two or more distinct `cat` values is a mixed row.** It belongs to no band. It
   **does** break a band: the band before it ends at the previous pure row and a new band starts at the
   next one.
5. **A band is the maximal run** of pure rows of one category, under rules 3 and 4.
6. **The band gap and the dashed rule are drawn between two adjacent bands**, never above the first,
   never below the last, and **never around a mixed row** — a rule drawn there would assert a boundary
   the data does not have.

**Categories are ordered by first appearance, and that needs no new field.** The `categories` array is
returned **ordered by the lowest `gr` at which the category appears in this showtime's seat set**,
ascending, with
the category id ascending as the tiebreak for two categories first appearing in the same grid row.
Because `seats` is already sorted `gr ASC, gc ASC` (`P-BRW-08`), this is the same as the order the
categories first occur in `seats`, so the legend reads top-to-bottom in the order the bands are drawn
and **the two orderings cannot disagree**.

**No field is added to `EP-BRW-06` for this**, and the reason is worth stating rather than leaving as a
preference: an explicit `display_order` on the category would be a second, independently settable
source for a fact the seat coordinates already fix, and the two would eventually disagree — which is
the failure `S1.2` exists to describe. **The ordering is computed by the server from the seats it is
already sending, so the client never sorts and never has a second opinion.** `EP-BRW-06` states the
ordering on the `categories` field so the contract carries it.

**When the categories interleave rather than sit in contiguous bands.** This is not a fault and it does
not fail the request. It renders as follows:

| Situation | What is drawn | What the legend shows |
|---|---|---|
| Every category contiguous — the ordinary case | one band per category, in `gr` order, separated by `--fr-seat-band-gap` and a 1px dashed `--fr-rule` | one row per category, in that same order, each with its name and price |
| One category appears in two separate runs | **two bands with the same category**, each drawn in place with its own gap and rule | **one legend row for that category, not two.** The legend names categories, not bands |
| A grid row is mixed | that row is drawn with **no band gap and no rule** around it, seats in their own categories at their own coordinates | unchanged — every category present on the screen has exactly one row |
| Every grid row is mixed, so no band exists at all | the grid is drawn with **no band gaps and no rules anywhere**. Nothing false is asserted | unchanged, ordered by first appearance. **The legend is then the only carrier of category, and that is stated in the accessible summary below rather than left for the customer to discover** |

**The accessible summary is what stops a mixed layout being an accessibility failure.** The seat map's
accessible name for each seat already states its category — `Row C seat 12, Premium, available`
(`COMPONENTS.md §1.6`) — so the category never depends on band position for a screen-reader user at
all. Band position is a carrier **for a sighted customer who does not perceive colour**, and when the
layout is mixed that customer has the legend and the per-seat name and no band. **Nothing is invented
to paper over it**: the specification says what is drawn and what is not.

**One row label per grid row, and it is an invariant rather than a hope.** Every seat at the same `gr`
carries the same `row` string. The gutter renders that one label, taken from any seat at that `gr`. A
void row renders an empty gutter cell of the same height, so the gutter and the grid never drift out
of alignment.

**A retired seat participates in band derivation exactly like any other seat** (`P-BRW-09`). Its `cat`
is unchanged by retirement, so excluding it could split one band into two and move a rule the customer
has already learned to read.

**Who may do it.** guest · customer · manager · admin. Public — this is rendering, and it changes no
server state.

**Preconditions.** A seat map payload has arrived. Every seat carries a non-null `cat` (`P-BRW-10`).

**Happy path.**
1. The server sorts `seats` by `gr ASC, gc ASC` and orders `categories` by first appearance.
2. The client walks `gr` ascending, classifying each grid row as pure, void or mixed.
3. It draws each maximal run of same-category pure rows as one band, with a gap and a dashed rule
   between adjacent bands.
4. It draws the legend in the order the categories arrived.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | Two seats at the same `gr` carry different `row` strings | 500 `INTERNAL_ERROR` — the invariant is checked when the map is assembled, not left to the client | "The seat map could not be loaded." plus "If you need help, quote `a1b2c3d4`." |
| 2 | A grid row holds more than one category | 200. **Not an error** — the admin is allowed to do this (`FR-ADR-016`), so the payload is valid and the rendering rules above apply | nothing. The row draws without a band rule |
| 3 | Every grid row is mixed | 200 | nothing. The map draws with no bands; the legend carries the categories |
| 4 | A category appears in `categories` but on no seat **of this showtime's seat set** | 200; the category is dropped from `categories` before the response is built — a legend row for a band nobody can see is a legend that lies. **The test is the seat set, not the screen**: a category still assigned to seats of the hall but to none in this showtime's set is dropped here, because the map does not draw it | nothing |
| 5 | The client sorts `categories` itself | forbidden — a second ordering implementation is a second answer, and `FR-ADR-045` gives the client no arithmetic and no reordering to do | *(no user-facing surface)* |

**Server-side validation.** The one-label-per-grid-row invariant (exception 1) is asserted when the map
is assembled. `categories` is emitted in first-appearance order and contains no category with no seat.
`cat` on every seat resolves to a row of `categories` in the same response; a dangling `cat` is the
same fault as exception 1.

**Worked example — a 6-row hall with one mixed row.** Six grid rows, `gr` 1 to 6; `cat` 1 is Standard,
`cat` 2 is Premium.

```
gr 1   every seat cat 1          pure, Standard
gr 2   every seat cat 1          pure, Standard
gr 3   no seats                  void  (the cross-aisle)
gr 4   every seat cat 1          pure, Standard
gr 5   seats cat 1 and cat 2     MIXED — the admin moved four seats to Premium
gr 6   every seat cat 2          pure, Premium

bands  = [ Standard: gr 1-4 ]  and  [ Premium: gr 6 ]
         gr 3 is inside the Standard band: a void row does not break it
         gr 5 belongs to no band and ends the Standard band before it

rules drawn = the rule sits between two ADJACENT bands only. gr 5 sits between
              these two, so they are not adjacent, so NO rule is drawn on this
              screen at all. Drawing one across gr 5 would assert a boundary
              the data does not have.

categories  = [ {id:1, Standard}, {id:2, Premium} ]
              ordered by first appearance: cat 1 first appears at gr 1,
              cat 2 first appears at gr 5.  1 < 5.
legend      = Standard first, Premium second — the same order, top to bottom
```

**`ASSUMED` flag, inherited.** The three category names are the build session's (`SRC-003
OPEN-SEAT-01`, "you pick"). Nothing above depends on there being three, on their names, or on their
order: a fourth category costs an insert, appears in `categories` at its first `gr`, and draws its own
band with no design change (`FR-ADR-072`).

---

## S5 — UX specification

### `SCR-BRW-01` · The movie listing
**Route.** `/` · **Who reaches it.** anyone, with no account · **Component basis.**
`COMPONENTS.md §0`, `§3`

**What the user arrives with / leaves with.** They arrive with nothing — this is the entry point. They
leave with a chosen movie, carrying its id into `SCR-BRW-02`. Filter state lives in the URL query
string so a back navigation returns the same listing.

**Fields and controls.**

| Element | Token(s) | Behaviour | Validation |
|---|---|---|---|
| Page frame | `--fr-surface-base`, `max-width: var(--fr-page-max)`, gutter `--fr-space-4` | body never scrolls horizontally | — |
| Date filter | day buttons, min height `--fr-tap-min`, selected `--fr-surface-accent` + `--fr-ink-on-accent`, unselected `--fr-surface-raised` + 1px `--fr-control-edge` | re-requests the listing. **Runs from today in Asia/Kolkata through the day before `max(display_until)` over the movies the current listing returned** (`P-BRW-04`) — the day before, because the bound is exclusive; over the **filtered** array, not the whole visible set; and not `P-BRW-06`'s single-movie range, because no movie has been chosen here. **The first control in the strip is `Any date`, and it is selected on arrival**; it submits no `date` parameter, exactly as the three selects' first options submit none. **A filter that removes the selected day drops the selection back to `Any date`** and announces it (`P-BRW-04`). **Absent entirely when the listing is empty** | `date` is an ISO date; an invalid one is 422 and the control cannot produce one |
| Language filter | `--fr-surface-raised`, 1px `--fr-control-edge`, `--fr-ink` | single-select. **Absent while fewer than two languages are in use** (`P-BRW-04`, `FR-ADR-046`) — the same rule as format and cinema, with no exemption; it appears on its own when a second reaches the reference endpoint | `language_id` positive integer |
| Format filter | as language | **absent while fewer than two formats are in use** (`P-BRW-04`) | `format_id` positive integer |
| Cinema filter | as language | **absent while fewer than two cinemas are in use** — one exists in v1, so it does not render (`FR-ADR-046`); appears on its own when a second exists | `cinema_id` positive integer |
| Clear-filters control | transparent fill, 1px `--fr-control-edge`, `--fr-accent-ink` | present only when at least one filter is set | — |
| Movie card | `--fr-surface-raised`, `--fr-radius-lg`, `--fr-shadow-card`, padding `--fr-space-4` | the whole card is one link to `SCR-BRW-02` | — |
| Poster box | `aspect-ratio: var(--fr-poster-ratio)`, `--fr-radius-md`, `--fr-surface-inset` | **reserves its space before the image arrives**, so the listing does not reflow | — |
| Title | `--fr-font-display`, `--fr-text-lg`, `--fr-weight-bold`, `--fr-track-tight`, `--fr-ink-strong` | — | — |
| Synopsis | `--fr-text-sm`, `--fr-ink-muted`, `--fr-leading-body`, clamped to three lines | — | — |
| Metadata row | `--fr-text-xs`, `--fr-ink-muted`; runtime in `--fr-font-mono` | runtime, language, genre | — |
| Certification chip | `--fr-text-xs`, `--fr-ink`, 1px `--fr-control-edge`, `--fr-radius-sm`, padding `--fr-space-1` | renders the certification's **`name`** — there is no `code` field (`P-BRW-02`, `P-ADM-23`) | — |

**All three reference-backed filters can be absent at once, and on day one all three are.** With every
vocabulary empty this screen renders the date strip and no filter control of any kind, and that is
correct rather than broken (`P-BRW-04`). **Nothing is drawn in their place** — no disabled control, no
explanatory line, no reserved gap that collapses later.

**One other state renders those same three absences, and it is the reason a line exists at all.** When
`EP-BRW-07` fails, the listing still renders and the three controls are still absent — a screen
identical to day one, meaning the opposite thing (`P-BRW-04` exception 5). **That state, and only that
state, carries the line `Filters are unavailable right now.`** above the card grid, in `--fr-ink` at
`--fr-text-sm`, and announced through the same polite live region as the result count. The date strip
and `Clear filters` render exactly as they otherwise would. **The empty-vocabulary state keeps its
silence** — it is correct, and an interface apologising for being correct is what `FR-ADR-046` refuses.

**States.**

| State | What renders |
|---|---|
| **Loading** | Poster boxes and three text blocks per card draw as `--fr-surface-inset` at their final dimensions. The card count is the last known count, or three on a first visit. No spinner. |
| **Empty — no filters set** | One line of `--fr-ink` at `--fr-text-md`: "Nothing is showing right now." No illustration. **The date strip is absent too** — with no visible film there is no day on which anything shows, so there is nothing for it to range over (`P-BRW-04`). |
| **Empty — filters set** | One line: "Nothing is showing for the chosen filters.", with a "Clear filters" button below it. |
| **Error** | The listing is replaced by the message and a "Try again" control. Filters stay on screen and stay usable. **This state is the listing query failing, and nothing else.** |
| **Filters unavailable** | `EP-BRW-07` failed while the listing succeeded. **The listing renders in full** — this is not the Error state. The three reference-backed controls are absent, the date strip and `Clear filters` render as normal, and one line above the grid reads "Filters are unavailable right now." (`P-BRW-04` exception 5). It is the only thing distinguishing this screen from the correct day-one rendering. |
| **Success** | Cards in `published_at DESC, id DESC` order (`P-BRW-03`). |
| **Partial** | A card whose data failed does not render; the listing renders the cards it has. A card whose poster failed renders with the perforation motif. |

**Copy.**

| Where | Verbatim |
|---|---|
| Empty, no filters | `Nothing is showing right now.` |
| Empty, with filters | `Nothing is showing for the chosen filters.` |
| Clear-filters button | `Clear filters` |
| Error | `The listing could not be loaded.` |
| Reference data unreachable, listing fine | `Filters are unavailable right now.` — **owned by this screen** (`S1.2.1` case 3; no P-row publishes it). It states the fact and claims no cause. **New in this pass**, because without it a reference outage and an empty vocabulary render byte-identical screens (`P-BRW-04` exception 5) |
| Retry control | `Try again` |
| Runtime, in the metadata row | `128 min` — `min` is a unit abbreviation and does not inflect, so this form is the same at every value |
| Runtime, in the card accessible name | `128 minutes`, and `1 minute` at exactly one — the count is interpolated, so both forms are published even though a one-minute film is not a thing this cinema will show (`S7.21`). A string published with only the plural is how `1 minutes` ships |
| Card link accessible name | `DEMO MOVIE 01, 128 minutes, DEMO RATING 1, DEMO LANGUAGE A` |
| Filter group accessible name | `Filter what is showing` |
| Date filter label | `Date` |
| Date filter, first control | `Any date` |
| Result count announced on a filter change, one | `1 film showing.` |
| Result count announced on a filter change, zero or more than one | `0 films showing.` · `12 films showing.` |
| Announced when a filter removes the selected day | `The date filter was cleared. Nothing in this list is showing on that day.` |
| Date filter, a day button | `Fri 15 Aug` — `S7.19`'s weekday-with-short-date form |
| Language filter label | `Language` |
| Language filter, first option | `Any language` |
| Format filter label | `Format` |
| Format filter, first option | `Any format` |
| Cinema filter label | `Cinema` |
| Cinema filter, first option | `Any cinema` |

**No day button is ever labelled `Today` or `Tomorrow`.** `S7.19` rule 7 forbids rendering a relative
instant, and a strip whose first button says `Today` is wrong the moment a tab is left open across
midnight — which on a cinema site, where the last shows run past 23:00, is a thing that happens.
Every button carries its own date.

**Each filter's first option submits no parameter at all**, which is what makes `Clear filters`
and "select the first option in every control" the same state rather than two. **The date strip is
one of those controls and `Any date` is its first option**, so all four filters obey one rule.

**No day is selected on arrival.** Opening `/` lists **every currently visible film**, which is what
an entry page is for; choosing a day narrows it. Preselecting today would make the entry page a
filtered view that nothing announced, and it would leave `Clear filters` unable to do what this
screen says it does — there would be **no published control that returns the customer to the
unfiltered listing**, because the strip offers days and no way to offer none. `Any date` is that
control, and it is the state the screen starts in.

**Accessibility.** Focus order follows visual order: filters, then cards in document order. Each card
is one focusable link with an accessible name naming the title, runtime, certification and language —
not "read more". The filter group has an accessible name. Changing a filter announces the new result
count through a polite live region, because a listing that silently reorders under a screen reader has
not reported anything. **Both forms of that announcement are published in the copy table above**
(`S7.21`) — it interpolates a count, so it owes a singular and a plural, and a string published with
only the plural is how `1 films showing` ships. **The same live region announces a date selection
dropped by a filter** (`P-BRW-04`), so a reader is told the strip changed under them rather than
finding a different result set with no explanation. Every control is at least `--fr-tap-min` tall. Focus ring is
`--fr-stroke-bold` `--fr-focus-ring` with `outline-offset: 2px`, never removed.

---

### `SCR-BRW-02` · The movie and its showtimes
**Route.** `/movies/{movie_id}` · **Who reaches it.** anyone · **Component basis.**
`COMPONENTS.md §3`, `§4`

**What the user arrives with / leaves with.** They arrive with a movie id, optionally a date in the
query string. They leave with a showtime id, into `SCR-BRW-03`.

**Fields and controls.**

| Element | Token(s) | Behaviour | Validation |
|---|---|---|---|
| Movie header | title as `SCR-BRW-01`; full synopsis at `--fr-text-md`, `--fr-ink`, `max-width: var(--fr-measure)` | the synopsis is not clamped here | — |
| Poster | as `SCR-BRW-01` | — | — |
| Date strip | horizontal, scrolls inside its own container; each day a button at `--fr-tap-min` | runs from today in Asia/Kolkata to the last day of the display window (`P-BRW-06`) | `date` ISO-8601 |
| Showtime button | `--fr-font-mono`, `--fr-text-md`, min height `--fr-tap-min`, `--fr-radius-md`, 1px `--fr-control-edge`, `--fr-surface-raised` | navigates to the seat map | — |
| Hall name under the time | `--fr-text-xs`, `--fr-ink-muted` | — | — |
| Base price under the time | `--fr-font-mono`, `--fr-text-xs`, `--fr-ink-muted` | rendered from integer paise at render time (`FR-ADR-036`) | — |
| Closed showtime | `--fr-surface-inset` fill, `--fr-ink-muted` text, **not focusable**, the word `Closed` at `--fr-text-xs` | does not navigate | — |
| Grid gap | `--fr-space-2` | — | — |

**States.**

| State | What renders |
|---|---|
| **Loading** | The date strip is real — dates are computed without a fetch. The showtime grid draws four `--fr-surface-inset` blocks at button size. |
| **Empty — this date** | "No showtimes on this date." plus a button offering the next date that has one: "Next: Fri 15 Aug". |
| **Empty — every date** | "No showtimes for this movie." No next-date button, because there is no next date. |
| **Error** | The message and a "Try again" control in place of the grid. **The date strip stays usable**, so the customer can move to a date that works. |
| **Success** | Showtimes ascending by start time, each with hall and base price. |
| **Partial** | Times render as they arrive. A time whose price has not arrived shows a `--fr-surface-inset` block where the price goes — **never a zero**. |
| **All closed** | Every button renders in the closed treatment. The list is not emptied — a customer who saw these showtimes needs to see why they cannot use them. |
| **Movie not visible** | The whole screen is replaced by "That movie is not showing." and a link reading "Back to what is showing". |

**Copy.**

| Where | Verbatim |
|---|---|
| Empty, one date | `No showtimes on this date.` |
| Next-date button | `Next: Fri 15 Aug` |
| Empty, all dates | `No showtimes for this movie.` |
| Closed marker on a button | `Closed` |
| Error | `Showtimes could not be loaded.` |
| Retry | `Try again` |
| Movie not visible | `That movie is not showing.` |
| Back link | `Back to what is showing` |
| Showtime accessible name, open | `7:30 pm, Hall 4, from ₹249.99` |
| Showtime accessible name, closed | `7:30 pm, Hall 4, sales closed` |
| Showtime count announced on a date change, one | `1 showtime on this date.` |
| Showtime count announced on a date change, zero or more than one | `0 showtimes on this date.` · `4 showtimes on this date.` |
| Date strip accessible name | `Choose a date` |
| Date strip, a day button | `Fri 15 Aug` — `S7.19`'s weekday-with-short-date form, the same form the
  next-date button above uses, so the control the customer is sent to and the control they land on
  read identically. **Never `Today`** (`S7.19` rule 7) |

**Accessibility.** The date strip is a single tab stop with arrow-key movement between days, not one
tab stop per day. Closed showtimes are **removed from the tab order** and their state is in their
accessible name, so a screen-reader user is not told to activate something inert. Changing the date
announces the new showtime count in a polite live region, and **both forms of that announcement are
published in the copy table above** (`S7.21`) — it interpolates a count, so it owes a singular and a
plural. Times are rendered in the customer's reading
form (`7:30 pm`) and in `--fr-font-mono` with tabular figures so the column does not jitter — the
format and the case are `S7.19`'s, not this screen's, and `Next: Fri 15 Aug` above is `S7.19`'s
weekday-with-short-date form. **This screen invents no format.** *(These two accessible names read
`7:30 PM` before `S7.19` existed; the case is the only thing that changed.)*

---

### `SCR-BRW-03` · The seat map, read view
**Route.** `/showtimes/{showtime_id}` · **Who reaches it.** anyone, including a guest with no account
· **Component basis.** `COMPONENTS.md §1`, `§2`, `§6`

> **One screen, two halves. `SCR-BRW-03` and lane E2's `SCR-SEA-01` are the same screen at the same
> route, `/showtimes/{showtime_id}` — not two destinations and not two routes.** This section
> specifies the **read path**: the layout that arrives, how it is drawn, how it refreshes, how stale
> it may be, and every state it can be in before anyone holds anything. `SCR-SEA-01` specifies the
> **interactive layer on this same screen** — selection, the price summary, the countdown and the
> hold. Neither is reachable without the other and there is no `/seats` route. **Where the two name
> the same element, the copy below and the copy in `SCR-SEA-01` are identical strings**, converged
> deliberately; a variant found in either file is a defect, not a choice.

**What the user arrives with / leaves with.** They arrive with a showtime id. From the read path they
leave either by selecting seats — E2 — or by going back. **Nothing on this screen changes server state.**

**Fields and controls.**

| Element | Token(s) | Behaviour | Validation |
|---|---|---|---|
| Field (the box the map is drawn on) | `--fr-surface-inset`, padding `--fr-space-4` | scrolls **horizontally only**, inside itself | — |
| Screen bar | `--fr-screen-bar`, `--fr-radius-pill`, 4px tall, 60% of map width, centred | — | — |
| Screen falloff | gradient from `--fr-screen-glow` to transparent, 48px | decorative; carries no state | — |
| `SCREEN` label | `--fr-ink-muted`, `--fr-text-xs`, uppercase, `--fr-track-caps`, inside the falloff | never on the 4px bar | — |
| Row gutter | width `--fr-seat-gutter`, `--fr-font-mono`, `--fr-text-xs`, `--fr-ink-muted`, `--fr-surface-inset` | **pinned left while the map scrolls** | — |
| Seat cell | `--fr-seat-size` square, `--fr-seat-gap` apart, `--fr-radius-sm` | drawn at `gr`/`gc`; an aisle is the absence of a cell | — |
| Band gap and rule | `--fr-seat-band-gap`, 1px dashed `--fr-rule` | separates seat categories. **Drawn only between two adjacent bands** — never above the first, never below the last, and never around a mixed grid row (`P-BRW-16`) | — |
| Void grid row | vertical space of one `--fr-seat-size` plus one `--fr-seat-gap`; the gutter cell at that `gr` renders empty | a grid row with no seats — an aisle. It does not break a band | — |
| Legend | `--fr-surface-raised`, `--fr-radius-md`, padding `--fr-space-3`; divider `--fr-rule-quiet` | always visible, never collapsed behind a control | — |
| Legend swatch | the real seat component at `--fr-seat-size` | not a simplified circle | — |
| Category rows in the legend | name `--fr-ink`, price `--fr-font-mono` `--fr-ink-strong` | the only place a category price is named in words. **One row per category, never one per band**, ordered as `categories` arrives — which is first-appearance order, so the legend reads in the order the bands are drawn (`P-BRW-16`) | — |
| Poll-failure strip | `--fr-ink-muted` on `--fr-surface-inset`, one line, top of the field | appears on a failed poll; the map below it is untouched | — |
| Banner (closed / sold out) | error banner shape, `--fr-surface-danger`, `--fr-ink-on-danger`, 3px `--fr-danger-ink` leading rule | above the map, in the sticky area | — |

**Seat states as drawn** (`P-BRW-09`, `COMPONENTS.md §1.4`).

| State | Fill | Mark | Border | Number shown | Tappable |
|---|---|---|---|---|---|
| `available` | `--fr-seat-available` | none | 1px `--fr-seat-edge-available` | yes, `--fr-seat-ink` | yes |
| `sold` | `--fr-seat-sold` | diagonal hatch, 45°, edge to edge | none | yes, `--fr-seat-ink` | no |
| `held_by_other` | `--fr-seat-held-other` | one horizontal bar, 3px | none | yes, `--fr-seat-ink` | no |
| `held_by_me` | `--fr-seat-mine` | a tick in `--fr-seat-ink-mine` | 2px `--fr-seat-edge-mine` | no — the tick replaces it | yes, to give it back |

**Out of service is drawn on top of the four, not as a fifth** (`P-BRW-09`). A seat whose `is_active`
is `false` is drawn from this row instead of from its `state`, whatever that state is:

| Condition | Fill | Mark | Border | Number shown | Tappable |
|---|---|---|---|---|---|
| `is_active: false`, in any `state` | none — the field's `--fr-surface-inset` shows through | the dashed outline is the mark | 1px **dashed** `--fr-rule` | yes, `--fr-ink-muted` | **no, ever** |

Four marks were already spent — none, bar, hatch, tick — so the fifth cue is a **shape of border**
rather than a fifth glyph, which keeps it legible at `--fr-seat-size` and needs no new token. The
legend gains a fifth swatch for it, because anything drawn differently has to be named.

**States.**

| State | What renders |
|---|---|
| **Loading** | The field, screen bar and row gutters draw immediately at full size; seat cells are `--fr-surface-inset` blocks at 60% opacity. The frame never resizes when data lands. No spinner. |
| **Empty** | **Cannot happen.** A showtime always has a hall and a hall always has seats. An empty seat list is `INTERNAL_ERROR` (`P-BRW-08`), not an empty state. |
| **Error, first load** | The map is replaced by the message on `--fr-surface-inset` plus a "Try again" control. **No partial grid.** Any 4xx or 5xx reaches this state, **429 included** — with no map and no poll loop, the rate-limited sentence would promise an update nothing delivers (`P-BRW-11` exception 4). |
| **Error, a poll failed** | **The last good map stays.** The one-line strip appears at the top of the field; polling keeps retrying. |
| **Success** | The full grid, the legend, and the running poll. |
| **Partial** | The map and the price summary load independently. The map is usable before the summary arrives; the primary action stays disabled until it does (the action itself is E2's). |
| **Sold out** | The full map with every seat `sold`, plus a banner. Not an empty state. |
| **Sales closed** | The full map, every seat unselectable, plus a banner. **Not hidden** (`P-BRW-07`). |
| **All seats out of service** | The full map with every cell in the `is_active: false` treatment, nothing selectable, plus a banner. **Not an empty state and not an error** — the seat set is intact and every seat in it has been retired (`P-BRW-08` exception 4). |
| **Redis unavailable** | 503; the map is replaced by the dependency message. Browsing screens keep working (`P-BRW-12`). |
| **Guest** | Identical to a customer, with no `held_by_me` cell and the primary action reading `Sign in to hold these seats` (`FR-ADR-046`). |

**Copy.**

| Where | Verbatim |
|---|---|
| Sold-out banner | `Every seat for this showtime is sold.` |
| Sales-closed banner | `Sales for this showtime have closed.` — **owned by `P-BRW-07`, rendered here, not decided here.** `SCR-SEA-01` renders this identical string; a variant in either file is a defect in the variant |
| All-seats-out-of-service banner | `None of the seats in this hall are available.` — **owned by `P-BRW-08`, rendered here, not decided here.** New in this pass; neither of the two banners above is true in that state |
| Poll-failure strip | `The seat map is not updating. The seats shown may be out of date.` |
| First-load error | `The seat map could not be loaded.` |
| Retry control | `Try again` |
| Rate limited **on a poll** — the map is on screen and the loop is running | `Too many requests. The seat map will update again shortly.` — **this sentence is true only while a poll loop exists to make it true.** A 429 on the **first load** renders the first-load error and its `Try again` instead (`P-BRW-11` exceptions 3 and 4); `SCR-XCT-03` publishes no variant for either |
| Redis unavailable | `The seat map is unavailable right now. You can still browse showtimes. Try again in a few minutes.` — **owned by `P-BRW-12`, rendered here, not decided here.** This screen publishes no variant of it |
| Server fault | `The seat map could not be loaded.` followed by `If you need help, quote a1b2c3d4.` |
| Showtime not found | `That showtime could not be found.` |
| Guest primary action | `Sign in to hold these seats` |
| Legend, four states | `Available` · `Sold` · `Held by someone else` · `Held by you` |
| Legend, out of service | `Out of service` |
| Mixed-category notice, shown only when `P-BRW-16` derives no band at all | `Seat categories are mixed within rows. Each seat's category is in the legend and in its label.` |
| Legend, a category row | `Premium  ₹281.24` |
| Seat accessible name | `Row C seat 12, Premium, available` |
| Seat accessible name, own hold | `Row C seat 12, Premium, held by you` |
| Seat accessible name, held by someone else | `Row C seat 12, Premium, held by someone else` |
| The screen label above the map | `SCREEN` |
| Seat accessible name, sold | `Row C seat 12, Premium, sold` |
| Seat accessible name, out of service | `Row C seat 12, Premium, out of service` |

The request id is shown **on 5xx only** (`FR-ADR-052`). No 4xx message carries one.

**Accessibility.** The map is **one tab stop**, not 220; arrow keys move within the grid, Enter or
Space selects (`FR-ADR-051`). Every seat has an accessible name stating identity, category and state,
and the seat number stays in the name even when the tick has replaced it visually. The banner and the
poll-failure strip are announced through a live region — an error that is only red has not been
reported. A seat that changes state between polls keeps a 2px `--fr-focus-ring` outline for
`--fr-motion-change`; under `prefers-reduced-motion: reduce` that outline is static rather than
pulsing and is held for the same duration, because it carries information. Seat cells are
`--fr-seat-size` (24px), which is the WCAG 2.2 target-size minimum, and **the seat is never shrunk to
avoid the horizontal scroll**.

**An out-of-service seat stays in the grid and stays readable.** It keeps its place in the arrow-key
grid so the geometry a reader has learned does not shift, its accessible name ends `out of service`,
and it never activates on Enter or Space. It is not removed from the grid and it is not skipped: a seat
that vanishes from between two others makes the map lie about the room.

**When the bands do not exist, the map says so once rather than leaving it to be inferred.** Where
`P-BRW-16`'s derivation produces no band at all — every grid row mixed — the field carries a single
line above the grid in `--fr-ink-muted` at `--fr-text-xs`: `Seat categories are mixed within rows. Each
seat's category is in the legend and in its label.` It is announced with the map's own live region on
first load only. Category never depends on band position for a screen-reader user in any case, because
every seat's accessible name already carries it (`COMPONENTS.md §1.6`); the line exists for a sighted
customer who does not perceive colour and for whom the band was the carrier.

---

## S6 — API endpoints

Every endpoint below is a safe method, public, and returns the standard error envelope
(`FR-ADR-052`). Instants are serialised as ISO-8601 **with the +05:30 offset**, never as `Z`
(`P-BRW-06`). Money is integer paise (`FR-ADR-036`).

---

The listing endpoint. It returns every movie that passes both visibility gates, newest first, narrowed
by whichever filters the caller sent. It is the first request the site makes and it is cached for 60
seconds per filter combination.

```endpoint
{
  "id": "EP-BRW-01",
  "method": "GET",
  "path": "/api/movies",
  "summary": "List the movies currently showing, newest first",
  "auth": "public",
  "roles": ["guest","customer","manager","admin"],
  "request": {
    "path_params": {},
    "query": {
      "date": "string, ISO-8601 calendar date in Asia/Kolkata, optional. ABSENT MEANS EVERY DATE and there is no default: no date predicate is applied and every currently visible film is returned. It does NOT default to today — that is EP-BRW-04's rule, which answers a different question (P-BRW-04, P-BRW-06). SCR-BRW-01 arrives in this state with its Any date control selected.",
      "language_id": "integer, positive, optional",
      "format_id": "integer, positive, optional",
      "cinema_id": "integer, positive, optional",
      "sort": "string, one of [newest], optional, defaults to newest"
    },
    "headers": {},
    "body": {}
  },
  "responses": {
    "200": {
      "description": "The visible movies, ordered by published_at DESC then id DESC. A movie is returned only when it matches language_id (a movie attribute) AND has at least one showtime satisfying every supplied showtime filter — date, cinema_id and format_id — simultaneously, per P-BRW-04. One EXISTS over the showtimes, never one per filter.",
      "body": {
        "count": "integer",
        "movies": "array of {id, title, synopsis, runtime_minutes, certification:{id,name}, language:{id,name}, genres:[{id,name}], poster_url, display_until}. display_until is an ISO-8601 instant with the +05:30 offset, the exclusive end of that film's display window. It is NEVER null on this endpoint even though the column is nullable (P-BRW-01): a film reaches this array only by passing both visibility gates, and a null window fails the window gate, so every film here has one. The client therefore takes the maximum without a null branch. It is the field the listing's date strip is built from: the client takes the MAXIMUM of display_until across this array (P-BRW-04). It is the same field EP-BRW-02 already carries for the single-movie strip, so one shape serves both. No separate aggregate is returned — a caller holding the films can compute any bound it needs, and a second field carrying a fact derivable from the first is a second thing that can disagree."
      }
    },
    "422": {"description": "A query parameter failed validation"},
    "503": {"description": "PostgreSQL unreachable"}
  },
  "errors": ["VALIDATION_FAILED", "DEPENDENCY_UNAVAILABLE", "INTERNAL_ERROR"],
  "idempotency": "safe method — no state change",
  "rate_limit": "none — not listed in FR-ADR-058's limited-endpoint table",
  "authorisation_rule": "No authorisation dependency is mounted on this router; an auth dependency here would break SRC-001 §4.1.",
  "satisfies": ["P-BRW-01","P-BRW-02","P-BRW-03","P-BRW-04","P-BRW-05","P-BRW-12","P-BRW-13"],
  "brd": ["R-BRW-01","R-BRW-02","R-BRW-03","R-BRW-05","R-BRW-06"]
}
```

---

One movie, with the full synopsis and its genres, for the detail screen. It applies the same two
visibility gates as the listing, and returns the same 404 for a draft movie as for one that never
existed.

```endpoint
{
  "id": "EP-BRW-02",
  "method": "GET",
  "path": "/api/movies/{movie_id}",
  "summary": "Return one visible movie with its full details",
  "auth": "public",
  "roles": ["guest","customer","manager","admin"],
  "request": {
    "path_params": {"movie_id": "integer, positive"},
    "query": {},
    "headers": {},
    "body": {}
  },
  "responses": {
    "200": {
      "description": "The movie",
      "body": {
        "id": "integer",
        "title": "string",
        "synopsis": "string",
        "runtime_minutes": "integer",
        "certification": "{id, name} — name, never code: P-ADM-23's certification table has no code column and EP-ADM-26 accepts only name",
        "language": "{id, name}",
        "genres": "array of {id, name}",
        "poster_url": "string",
        "display_until": "string, ISO-8601 with +05:30 offset, used to bound the date strip"
      }
    },
    "404": {"description": "No visible movie with that id"},
    "422": {"description": "movie_id is not a positive integer"},
    "503": {"description": "PostgreSQL unreachable"}
  },
  "errors": ["NOT_FOUND", "VALIDATION_FAILED", "DEPENDENCY_UNAVAILABLE", "INTERNAL_ERROR"],
  "idempotency": "safe method — no state change",
  "rate_limit": "none",
  "authorisation_rule": "Public. An unpublished or out-of-window movie returns the same 404 as a nonexistent one, so draft ids cannot be enumerated.",
  "satisfies": ["P-BRW-01","P-BRW-02","P-BRW-05"],
  "brd": ["R-BRW-01","R-BRW-02","R-BRW-06"]
}
```

---

The poster. It returns a redirect rather than the image bytes, so the API does not spend its single
worker serving static files. The bucket is private and the target URL is presigned and expires.

```endpoint
{
  "id": "EP-BRW-03",
  "method": "GET",
  "path": "/api/movies/{movie_id}/poster",
  "summary": "Redirect to a presigned URL for this movie's poster",
  "auth": "public",
  "roles": ["guest","customer","manager","admin"],
  "request": {
    "path_params": {"movie_id": "integer, positive"},
    "query": {},
    "headers": {},
    "body": {}
  },
  "responses": {
    "302": {
      "description": "Location is a presigned S3 GET URL valid for 3600 seconds; Cache-Control max-age is POSTER_REDIRECT_CACHE_SECONDS and is always less than that",
      "body": {}
    },
    "404": {"description": "No such movie, or the movie has no poster object key"},
    "422": {"description": "movie_id is not a positive integer"},
    "503": {"description": "PostgreSQL unreachable. The object key is read from the movie row before a URL can be minted, so this endpoint has a database dependency like every other read in the epic and the universal dependency floor reaches it. Presigning itself cannot fail here — it is local and calls S3 not at all (P-BRW-15 exception 4)."}
  },
  "errors": ["NOT_FOUND", "VALIDATION_FAILED", "DEPENDENCY_UNAVAILABLE", "INTERNAL_ERROR"],
  "idempotency": "safe method — no state change. Each call mints a new presigned URL; minting is local and calls S3 not at all.",
  "rate_limit": "none — flagged in the lane notes as an unlimited presigning path",
  "authorisation_rule": "Public. The object key is read from the movie row and never taken from the request.",
  "satisfies": ["P-BRW-15","P-BRW-02"],
  "brd": ["R-BRW-02"]
}
```

---

Showtimes for a movie on a date. The date is interpreted in Asia/Kolkata and converted to an instant
range on the server, so the caller never does zone arithmetic. Closed showtimes are included and
flagged, never dropped.

```endpoint
{
  "id": "EP-BRW-04",
  "method": "GET",
  "path": "/api/showtimes",
  "summary": "List showtimes for a movie on a local calendar date",
  "auth": "public",
  "roles": ["guest","customer","manager","admin"],
  "request": {
    "path_params": {},
    "query": {
      "movie_id": "integer, positive, required",
      "date": "string, ISO-8601 calendar date in Asia/Kolkata, optional, defaults to today in the cinema's zone",
      "cinema_id": "integer, positive, optional",
      "format_id": "integer, positive, optional"
    },
    "headers": {},
    "body": {}
  },
  "responses": {
    "200": {
      "description": "Showtimes on that local day, ordered by starts_at ASC then id ASC",
      "body": {
        "date": "string, the local date actually used",
        "next_date_with_showtimes": "string, ISO-8601 local calendar date in Asia/Kolkata, or null. The EARLIEST local date meeting all four of: strictly after the requested date; inside the movie's display window, so the search never runs past display_until; holding at least one showtime whose sales have not closed at the moment of the request; and that same showtime matching every filter this request carried, cinema_id and format_id where supplied. All four are met by ONE showtime, never by four different ones. The cut-off and the filters are part of the test on purpose — this field drives a button, and a date whose showtimes are all closed, or are all a format the customer did not ask for, is a button that moves the customer for nothing (P-BRW-06, P-BRW-07). Because condition 4 reads the request, the same movie at the same instant can yield different next dates under different filters. null means no such date exists, and the client then renders no next-date button at all.",
        "showtimes": "array of {id, starts_at, ends_at, sales_close_at, sales_closed, screen:{id,name}, cinema:{id,name}, format:{id,name}|null, base_price_paise}"
      }
    },
    "404": {"description": "The movie is not visible"},
    "422": {"description": "A query parameter failed validation"},
    "503": {"description": "PostgreSQL unreachable"}
  },
  "errors": ["NOT_FOUND", "VALIDATION_FAILED", "DEPENDENCY_UNAVAILABLE", "INTERNAL_ERROR"],
  "idempotency": "safe method — no state change",
  "rate_limit": "none",
  "authorisation_rule": "Public. sales_closed is presentation only; the cut-off is enforced at hold acquisition, not here.",
  "satisfies": ["P-BRW-04","P-BRW-05","P-BRW-06","P-BRW-07","P-BRW-12","P-BRW-13"],
  "brd": ["R-BRW-01","R-BRW-03","R-BRW-04"]
}
```

---

One showtime's header. The seat map screen needs the film, the hall, the times and the closed flag
before the map itself arrives, and this is the small response that lets the frame draw at full size
immediately.

```endpoint
{
  "id": "EP-BRW-05",
  "method": "GET",
  "path": "/api/showtimes/{showtime_id}",
  "summary": "Return one showtime with its movie, hall and sales cut-off",
  "auth": "public",
  "roles": ["guest","customer","manager","admin"],
  "request": {
    "path_params": {"showtime_id": "integer, positive"},
    "query": {},
    "headers": {},
    "body": {}
  },
  "responses": {
    "200": {
      "description": "The showtime",
      "body": {
        "id": "integer",
        "movie": "{id, title, certification:{id,name}, runtime_minutes}",
        "screen": "{id, name}",
        "cinema": "{id, name}",
        "starts_at": "string, ISO-8601 with +05:30 offset",
        "ends_at": "string, ISO-8601 with +05:30 offset",
        "sales_close_at": "string, ISO-8601 with +05:30 offset, derived never stored",
        "sales_closed": "boolean, evaluated against the injected clock at request time",
        "base_price_paise": "integer"
      }
    },
    "404": {"description": "No showtime with that id"},
    "422": {"description": "showtime_id is not a positive integer"},
    "503": {"description": "PostgreSQL unreachable"}
  },
  "errors": ["NOT_FOUND", "VALIDATION_FAILED", "DEPENDENCY_UNAVAILABLE", "INTERNAL_ERROR"],
  "idempotency": "safe method — no state change",
  "rate_limit": "none",
  "authorisation_rule": "Public. This endpoint does not apply the movie visibility gates: it is the booking surface, and FR-ADR-021 rules that the display window governs the browse surface, not the booking record. P-BRW-01 tabulates this endpoint as one of the three in the epic that apply no gate, so the row and this block agree; WHETHER it should apply them is OPEN-BRWVIS-01, which is OPEN and reserved, and neither the row nor this block answers it. Until it is ruled, no movie gate is applied here.",
  "satisfies": ["P-BRW-05","P-BRW-06","P-BRW-07"],
  "brd": ["R-BRW-01","R-BRW-04"]
}
```

---

The seat map. This is the highest-traffic route in the product: every viewer of a busy showtime fetches
it twenty times a minute. It carries objective state only — the caller's own holds are overlaid on the
client — which is what keeps one cached entry serving every viewer.

```endpoint
{
  "id": "EP-BRW-06",
  "method": "GET",
  "path": "/api/showtimes/{showtime_id}/seatmap",
  "summary": "Return the full seat layout and objective seat states for one showtime",
  "auth": "public",
  "roles": ["guest","customer","manager","admin"],
  "request": {
    "path_params": {"showtime_id": "integer, positive"},
    "query": {},
    "headers": {},
    "body": {}
  },
  "responses": {
    "200": {
      "description": "The complete map. Never paginated, never partial. Cache-Control: no-store, because the client polls it every 3 seconds.",
      "body": {
        "showtime": "{id, starts_at, sales_close_at, sales_closed}",
        "screen": "{id, name, rows, cols}. rows and cols are DERIVED per response as max(gr) and max(gc) over THIS SHOWTIME's seat set, never over the screen's current seats and never from a stored column — no screen row carries them (EP-ADM-16 accepts only cinema_id and name). Taking the maximum over the current seats would let a seat added after this showtime was created widen this showtime's extent, which moves P-BRW-16's band rules and therefore misstates seat category for a customer who does not perceive colour (P-BRW-08, P-BRW-10, P-ADM-14).",
        "categories": "array of {id, name, price_paise} — already rounded by FR-ADR-038's rule. Ordered by the lowest gr at which the category appears in THIS SHOWTIME'S SEAT SET, ascending, with id ascending as the tiebreak, so the legend reads in the order the bands are drawn and the client never sorts (P-BRW-16). A category with no seat in this showtime's seat set is not returned. Scoped to the seat set and never to the screen's current seats, exactly as seats, rows and cols already are (P-ADM-14): the two sets genuinely differ once a seat is added to or retired from the hall, and a category present on the screen but absent from this showtime could otherwise order a legend row for a band the map does not draw.",
        "seats": "array of {id, row, num, gr, gc, cat, price_paise, state, is_active} — this showtime's seat set as materialised at showtime creation (P-ADM-14), never the screen's current seats — ordered by gr ASC then gc ASC; state is one of available|held|sold; price_paise is this seat's own already-rounded integer price, equal to its category's, so the client sums integers and performs no rounding of its own (P-BRW-10, FR-ADR-038, FR-ADR-045); is_active is a required boolean, false for a seat retired after this showtime was created, which is returned and drawn but is never selectable and still carries its true state — is_active is not a fifth state and the state enum stays three values wide (P-BRW-08 exception 3, P-BRW-09, P-ADM-15). Every seat sharing a gr carries the same row string, which is the label the gutter renders (P-BRW-16).",
        "generated_at": "string, ISO-8601 with +05:30 offset",
        "poll_interval_seconds": "integer, the value of SEATMAP_POLL_INTERVAL_SECONDS, default 3. Server configuration validated at boot (S7.9 cross-check 10) and published here so the client holds no constant of its own and one value governs (P-BRW-11). The server publishes the interval and does not police it; a client polling faster meets the rate limiter and nothing else."
      }
    },
    "404": {"description": "No showtime with that id"},
    "422": {"description": "showtime_id is not a positive integer"},
    "429": {"description": "More than 120 requests in a minute from this IP; carries Retry-After"},
    "500": {"description": "The showtime's seat set is empty — a fault, not an empty state. Also returned when two seats sharing a gr carry different row labels, which breaks the one-label-per-grid-row invariant the gutter is drawn from (P-BRW-16)"},
    "503": {"description": "Redis unreachable, so the rate limiter cannot be evaluated and fails closed"}
  },
  "errors": ["NOT_FOUND", "VALIDATION_FAILED", "RATE_LIMITED", "DEPENDENCY_UNAVAILABLE", "INTERNAL_ERROR"],
  "idempotency": "safe method — no state change",
  "rate_limit": "per IP, 120 per minute, token bucket in Redis (FR-ADR-058). No per-user bucket, because the endpoint is unauthenticated and there is no user to key one on. The limit exists to stop scraping, not browsing: one legitimate poller uses 20 — so the bucket admits SIX concurrent viewers from one address and refuses the seventh, and guests behind one office, household or carrier NAT address share that single bucket (P-BRW-11). A refused poll takes P-BRW-11 exception 3 and a refused first load takes exception 4; the first load never renders the 'will update again shortly' string, because no poll loop exists yet to deliver that update.",
  "authorisation_rule": "Public, and identical for every caller. The response must never vary by who is reading it — a per-viewer seat map destroys the shared cache and reintroduces held_by_me on the server. It applies no movie visibility gate either, exactly as EP-BRW-05 does not: P-BRW-01 tabulates both, and whether either should is OPEN-BRWVIS-01, which is OPEN and reserved.",
  "satisfies": ["P-BRW-05","P-BRW-08","P-BRW-09","P-BRW-10","P-BRW-11","P-BRW-12","P-BRW-13","P-BRW-14","P-BRW-16"],
  "brd": ["R-BRW-01","R-SEAT-01","R-SEAT-03","R-SEAT-06","R-SEAT-07","R-QLY-04"]
}
```

---

The reference data the filter controls are built from. It exists so the rule "do not render a filter
with fewer than two values" is mechanical rather than remembered: the interface counts what this
returns and renders accordingly, so a second cinema makes the cinema filter appear with no code change.

```endpoint
{
  "id": "EP-BRW-07",
  "method": "GET",
  "path": "/api/reference",
  "summary": "Return the filter vocabularies: cinemas, languages, formats, certifications",
  "auth": "public",
  "roles": ["guest","customer","manager","admin"],
  "request": {
    "path_params": {},
    "query": {},
    "headers": {},
    "body": {}
  },
  "responses": {
    "200": {
      "description": "Lookup rows IN USE, which P-BRW-04 defines as: referenced by something the caller can currently see. Currently visible is P-BRW-01's rule — published and inside the display window — and is not restated here. is_active is deliberately NOT a filter on this endpoint: a withdrawn row that a visible film still carries is returned, because the customer can see that film and must be able to filter to it (P-ADM-23, P-ADM-24). A row referenced by nothing visible is omitted, so the menu never offers a value whose only result is an empty list. A caller renders a filter control only when its array holds two or more entries.",
      "body": {
        "cinemas": "array of {id, name} — a cinema is returned when at least one showtime of a currently visible film, not past its sales cut-off, runs on one of its screens. One cinema exists in v1, so this array holds one entry and no cinema control renders (FR-ADR-046, PROVISIONAL under SRC-003 C-2).",
        "languages": "array of {id, name} — a language is returned when at least one currently visible film carries it, whether or not the row is still is_active.",
        "formats": "array of {id, name} — a format is returned when at least one showtime of a currently visible film, not past its sales cut-off, carries it. The cut-off direction is PROVISIONAL (P-BRW-07).",
        "certifications": "array of {id, name} — name, never code (P-ADM-23 owns the table and it has no code column). In use as languages. Returned for completeness; no certification filter control exists in v1, because SRC-001 §5.1.3 names four filters and certification is not one."
      }
    },
    "503": {"description": "PostgreSQL unreachable. The listing endpoint is independent and is unaffected: SCR-BRW-01 still renders in full, with no reference-backed filter control, with its date strip and Clear filters intact, and with one line reading 'Filters are unavailable right now.' That line is the only thing distinguishing this outage from the correct day-one rendering, which produces the same three absences and carries no message (P-BRW-04 exception 5, SCR-BRW-01)."}
  },
  "errors": ["DEPENDENCY_UNAVAILABLE", "INTERNAL_ERROR"],
  "idempotency": "safe method — no state change",
  "rate_limit": "none",
  "authorisation_rule": "Public. It discloses only vocabulary, never a movie, a showtime or a booking.",
  "satisfies": ["P-BRW-04","P-BRW-05"],
  "brd": ["R-BRW-01","R-BRW-03"]
}
```

---

Two codes this epic needs that the registry in `FR-ADR-052` does not carry. Both are read-path
failures the registry never had to describe, because every code in it was derived from the hold,
booking and payment paths.

```newerrorcode
{"code":"NOT_FOUND","http":404,"when":"A requested movie, showtime or poster does not exist, or a movie fails one of the two visibility gates in P-BRW-01. The same response is returned for 'does not exist' and 'is not visible', so draft ids cannot be enumerated.","raised_by":["EP-BRW-02","EP-BRW-03","EP-BRW-04","EP-BRW-05","EP-BRW-06"],"why_needed":"FR-ADR-052's list has no not-found code because it was derived from the hold, booking and payment paths, where the resource always exists. Returning INTERNAL_ERROR would be a lie and would pollute the 5xx rate the operator watches; returning 200 with a null body forces the client to branch on shape rather than on code, which FR-ADR-052 forbids."}
```

```newerrorcode
{"code":"VALIDATION_FAILED","http":422,"when":"A path or query parameter fails type or bound validation before any query runs — a non-integer id, a malformed date, an unsupported sort value.","raised_by":["EP-BRW-01","EP-BRW-02","EP-BRW-03","EP-BRW-04","EP-BRW-05","EP-BRW-06"],"why_needed":"FastAPI returns 422 for request validation by default and its body is not FR-ADR-052's envelope. Without a registered code every endpoint in this epic emits one shape for validation failures and another for everything else, and the client has to branch on the body's shape. The handler is overridden once, globally, to emit the standard envelope with this code."}
```

---

## Lane notes

### Article X candidates raised by this lane

| Candidate | The question | Why it is not answerable from any source | Class |
|---|---|---|---|
| `PROPOSED-FORMAT-01` | `SRC-001 §5.1.3` requires a **format** filter. No frozen source and no ADR says what a format *is* — where the attribute lives, and what its values are. `FR-ADR-021` enumerates the movie's fields and format is not among them. | The value list is product content the admin supplies, and `FR-ADR-067` forbids the build session inventing content the client will see. Guessing "2D / 3D / IMAX" would put three invented rows in front of the client. | product content |
| `PROPOSED-SORT-01` | `FR-ADR-021` says the newest-first default is "overridden by the customer's chosen sort". **Which sorts?** No source enumerates one. | Any list — by title, by price, by popularity — would be invented scope. Popularity in particular would need a metric nobody has defined. | scope |
| `PROPOSED-BRWVIS-01` | A movie leaves its display window, or is unpublished, **while its showtimes still have unsold seats**. The browse surface hides it (`FR-ADR-021`). May those showtimes still be sold directly by URL? | `FR-ADR-021` says the window governs the browse surface and not the booking record, which answers the *booking* half and not the *selling* half. Making the seat map 404 would break a customer mid-checkout; leaving it sellable creates a withdrawal path in all but name, and withdrawal is `OPEN-SHOWCANCEL-01`, which is reserved and open. **This may be a facet of `OPEN-SHOWCANCEL-01` rather than a new row.** | reserved: money |
| `PROPOSED-CACHE503-01` | **Two `APPROVED` ADRs contradict each other** on the seat map read when Redis is down. See "Contradictions found" below. | Not a gap in the sources — a conflict between two immutable records, which this lane may not re-open. | build session, escalated |

### Assumptions I had to flag

| Where | `ASSUMED` or `PROVISIONAL` | Where it bites |
|---|---|---|
| `P-BRW-08`, `P-BRW-13` | **`ASSUMED`** — hall sizes 90/120/150/180/200/220 (`SRC-003 OPEN-SCALE-02`, "pick random") | Every payload and bandwidth figure in `P-BRW-13` is computed against 220 seats. If the real largest hall is 400, the seat-map payload and the polling egress roughly double and the pagination decision in `P-BRW-13` is worth re-examining. **No layout decision depends on the exact numbers.** |
| `P-BRW-10` | **`ASSUMED`** — the category names Standard, Premium, Recliner (`SRC-003 OPEN-SEAT-01`, "you pick") | The legend, the band layout and the price rows. They are table rows, not an enum, and there is deliberately no per-category colour token (`FR-ADR-072`), so a fourth category costs an insert and no design change. |
| `P-BRW-04` | **`PROVISIONAL`** — one cinema (`SRC-003 C-2`, `FR-ADR-010`) | The cinema filter is implemented and not rendered. If the client confirms several cinemas, the control appears from the reference endpoint with no code change — that is the whole reason it is built this way. |
| `P-BRW-07` | **`PROVISIONAL`** — sales close 15 minutes **after** the advertised start (`SRC-003 OPEN-BOOK-03`, `FR-ADR-042`) | Every `sales_closed` flag on every showtime and seat map. Reversal is one signed configuration value and two test assertions. The two readings are half an hour apart. |
| `P-BRW-04` | **`ASSUMED`** — format is an attribute of the *showtime*, not the movie | The showtime payload, the filter's SQL, and the reference endpoint. See `PROPOSED-FORMAT-01`. |
| `P-BRW-15` | **`ASSUMED`** — `POSTER_REDIRECT_CACHE_SECONDS = 300` | Only the browser cache lifetime. The **bound** is not assumed: it must stay below the presigned URL's 3600-second expiry or cached redirects break. |
| `P-BRW-12` | **`PROVISIONAL`** — 503 on the seat map read when Redis is down | See the contradiction below. |
| `P-BRW-08`, `P-BRW-09` | **`[JUDGMENT CALL]`** — an out-of-service seat is carried by a boolean `is_active`, not by a fifth `state` value | The seat object, `P-BRW-13`'s byte arithmetic, the seat cell's rendering and the legend's fifth swatch. **No source names a wire shape for a retired seat**: `P-ADM-15` names the behaviour and `FR-ADR-045` fixes the state count at four, and the boolean is the only shape satisfying both — because a retired seat can also be `sold`, and a fifth enum value would displace the sale state and lose it. Reversal would be a schema-free change to one field. |
| `P-BRW-16` | **`[JUDGMENT CALL]`** — how a category band is derived, and that `categories` is ordered by first appearance | The band gaps and rules, the legend's order, and the mixed-row case. `P-BRW-10` and `COMPONENTS.md §1.5` both require bands and neither says how one is computed, while an admin may put three categories in one grid row. **No field was added to the payload** — an explicit `display_order` would be a second settable source for a fact the coordinates already fix. |
| `P-BRW-12` | **ownership declared, not assumed** — this row owns the seat-map `DEPENDENCY_UNAVAILABLE` string | Three sections carried three different sentences for one situation and two of them were rank-2 rows, which `S1.2` cannot break. `P-XCT-09` and `SCR-XCT-02` now defer; `SCR-BRW-03` renders the one string. |
| `P-BRW-08` | **deferral, not an assumption** — a showtime's seat set is materialised at showtime creation and `P-ADM-14` owns that rule | The seat map's contents, `EP-BRW-06`'s `seats` array, and exceptions 2 and 3. This row previously said "one entry per active seat" with no creation-time filter, which read literally puts a newly added seat on a showtime whose `seat_count_at_creation` predates it. The wording now names the seat set and points; **the rule itself is not restated here and must not be**. |
| `P-BRW-12` | **`[JUDGMENT CALL]`** — the listings cache is invalidated by a generation counter, `cache:listing:generation`, embedded in every listings key | Every listings read and every admin write that can change a listing. **Decided because a `DEL` names a key and the per-filter-combination keyspace cannot be enumerated**, so the only alternatives were an unbounded `SCAN` on every admin write or an "immediately" that is not true. **This row owns the mechanism**; `P-XCT-08`, `P-ADM-02` and `P-ADM-06` point at it. Reversible: the key format and the trigger set are one row's text and one prefix in code, and nothing in the schema depends on either. |
| `P-BRW-04`, `EP-BRW-01` | **defect corrected — a rank-2 row required a field the rank-1 shape did not carry** (`S1.2.1` case 2) | The listing's date strip, on the product's entry page. This row named `display_until` as the strip's bound and `EP-BRW-01` returned no such field and no aggregate; `EP-BRW-02` has it but is the single-movie endpoint. **The strip could not be built at all**, and the two ways out were both wrong — invent a horizon, which `P-BRW-06` refuses, or issue one `EP-BRW-02` per listed film. `display_until` is now on every movie in the listing and the client takes the maximum. **Per-film, not a `strip_until` aggregate**: an aggregate would be a second value carrying a fact derivable from the first. Empty array means no strip at all. |
| `P-BRW-08`, `EP-BRW-06` | **`[JUDGMENT CALL]`** — `screen.rows` / `cols` are derived as `max(gr)` / `max(gc)` **over this showtime's seat set**, never over the screen's current seats | The grid extent, and through it the band rules. No `screen` row stores them (`EP-ADM-16` accepts `cinema_id` and `name` only), so the server derives them and nothing said from what. **The consequence is visible to a customer, not internal**: the other reading lets a seat added later widen a frozen showtime's extent, `P-BRW-16`'s walk then classifies the extra grid rows as void, and the band gaps and dashed rules move — and `P-BRW-10` makes band position the **primary non-colour carrier of category**, with no per-category colour token. Reversible: one aggregate's scope. |
| `P-BRW-06`, `EP-BRW-04` | **`[JUDGMENT CALL]`** — `next_date_with_showtimes` is **filter-aware**: a fourth condition requires the same showtime to match every filter the request carried | `SCR-BRW-02`'s next-date button. Added on this row's **own** argument for condition 3: with `format_id` set and a filter-blind search the button offers a date whose only showtime is another format, and the customer arrives at `No showtimes on this date.` — "a button that has moved them for nothing". All four conditions are met by **one** showtime, as `P-BRW-04` rules for the listing. Consequence stated: the field now depends on the request, so one film at one instant yields different next dates under different filters. Reversible: two predicates. |
| `SCR-BRW-01`, `SCR-BRW-02` | **defect corrected**, `S5` preamble + `S7.21` — two live regions announced a count and published no words | Both screens' polite live regions. `SCR-BRW-01`'s "changing a filter announces the new result count" and `SCR-BRW-02`'s "changing the date announces the new showtime count" were **words a user hears** with nothing published, which is the same defect as a control with no string. Both forms of each are now in the copy tables, plus a third for the date-selection drop `P-BRW-04` introduced this wave. |
| `SCR-BRW-01` | **the class, `S7.21`** — a count-interpolated string owes a singular | The card accessible name's runtime. `128 minutes` gained `1 minute`, published even though a one-minute film is not a thing this cinema will show, because a string published with only the plural is how `1 minutes` ships. `128 min` needs no partner — `min` is a unit abbreviation and does not inflect, and that is said rather than left as an omission. |
| `P-BRW-10` | **arithmetic defect corrected** — the Recliner per-seat price is **33331** (₹333.31), not `33332`, and three of them are **99993** (₹999.93), not `99996` | Every price this row publishes and every test transcribed from it. `(24999 * 13333 + 5000) // 10000 = 33331`; the exact value is `33331.1667`, so half-up rounds it **down** — the opposite direction from Premium, which is why both are now shown. **`S1.5` transcribes tests directly from worked examples**, so the wrong figure would have become a test assertion about money disagreeing with another by a paisa. Corrected in place with the old figures recorded rather than overwritten. |
| `P-BRW-04` | **worked example corrected against `P-XCT-30`** — `format` is **not** carried by a film | The seeded-catalogue example. It claimed every film carries one of each vocabulary; **format lives on the showtime**, so no per-film assignment could ever put a format in use and `EP-BRW-07.formats` would have returned nothing. `P-XCT-30` alternates the two `DEMO FORMAT` rows across each hall's showtimes instead. The publication claim is now true too, since the seed publishes its eight films against a repo-committed placeholder poster. |
| `SCR-BRW-01`, `SCR-BRW-02`, `SCR-BRW-03` | **the class — controls specified with no published words** | Thirteen strings added across the three screens: four filter labels and three of their first options, the filter group's accessible name, both date strips' day-button form, the `SCREEN` label, and the held-by-someone-else seat accessible name. **A screen that names a control owes that control's words** (`S1.2.1` case 3 makes the screen the owner; this is the obligation that follows). Also stated: **no day button is ever labelled `Today`**, on `S7.19` rule 7 — a strip whose first button says `Today` is wrong the moment a tab is left open across midnight. |
| `P-BRW-01` | **defect corrected, and it overturns this row's own earlier text** — `display_until` is stored **verbatim** and the admin types the exclusive end; the server adds no day | Every display-window value. This row previously claimed the server moved the admin's last date to the day after. `EP-ADM-04` is rank 1 and accepts an instant, and `P-ADM-04`, its worked example and `SCR-ADM-02` all agree with it. **A server that silently shifts what an admin typed by a day is the worse design**, because the admin gets no signal either way and the first evidence is a customer finding the film gone a day early. Everything this row says about how the gate is *evaluated* is unchanged. |
| `P-BRW-06`, `EP-BRW-04` | **`[JUDGMENT CALL]`** — `next_date_with_showtimes` is the earliest date **strictly after** the requested one, **inside the window**, holding **at least one showtime whose sales are still open** | `SCR-BRW-02`'s next-date button. **Condition 3 is the one that matters**: the field drives a button, and a date on which every showtime renders `Closed` is a button that moves the customer for nothing. Evaluated against the injected clock, so it is live, not a property of the row. `null` when no such date exists, and the button is then not rendered. Reversible: one predicate. |
| `P-BRW-07`, `SCR-BRW-03` | **ownership declared** — this row owns the sales-closed **banner**, `Sales for this showtime have closed.` | `SCR-BRW-03` and E2's `SCR-SEA-01` are the same screen at the same route, both assert their shared strings are byte-identical, and both published different banners. A rank-2 row publishes this one and both screens are rank 3, so this ships. **`P-HLD-14` row 9's longer 409 body is deliberately untouched** — a hold-attempt API error is a different surface with a different job and may name the time. |
| `P-BRW-04`, `SCR-BRW-01` | **`[JUDGMENT CALL]`, corrected twice since** — the listing's date strip runs from today through the **day before `max(display_until)` over the filtered listing** | `SCR-BRW-01`'s date control. `P-BRW-06`'s strip needs a chosen movie and the listing has none, and a maximum needs **no number nobody supplied** — the same ground on which `P-BRW-06` refuses a fixed horizon. **This row then stated its own subject two ways twice over**, which `S1.2.1` case 8 makes a defect in the row rather than a ranking question: *through* `display_until` against `P-BRW-06`'s *day before* it, one day apart; and *the visible set* against *`EP-BRW-01`'s array*, filter-independent against filtered. **Day before**, because the bound is exclusive and the extra button could only ever reach the empty state. **Filtered**, because the client holds no other array and an unfiltered maximum would need a second request nobody specified. Both losing phrasings are deleted rather than reconciled. Reversible: one aggregate and its scope. |
| `P-BRW-11`, `EP-BRW-06` | **defect corrected, and it overturns this row's own earlier text** — `SEATMAP_POLL_INTERVAL_SECONDS` is **server configuration returned in the seat-map response**, not a client constant | The poll loop and `EP-BRW-06`'s `poll_interval_seconds`. This row previously said the server "neither knows nor enforces it", which made `S7.9`'s boot cross-check 10 meaningless — a boot check cannot validate a value the server does not hold. **One value governs**, and the operator changes it without redeploying the frontend. **Enforcement is still nowhere**: the server publishes the interval, the rate limiter handles a client that ignores it. |
| `P-BRW-08`, `SCR-BRW-03` | **`[JUDGMENT CALL]`** — a seat set whose every member has been retired returns **200 with a complete map**, not the 500, and carries a **new** banner string `None of the seats in this hall are available.` | The seat-map response and the seat-map screen. **Decided because the 500's condition is an empty seat set — zero rows — and an all-retired set is not empty**; the two readings sat one word apart. **The string is new because neither existing banner is true**: nothing was sold and sales have not closed, so reusing either would state a false cause. `P-BRW-08` owns it. Reversible: one exception row and one copy line. |
| `P-BRW-02`, `EP-BRW-01`, `EP-BRW-02`, `EP-BRW-05`, `EP-BRW-07` | **wire correction, not a judgment call** — `certification` is `{id, name}`, never `{id, code}` | Five wire sites and the certification chip. `P-ADM-23` fixes the table at `id`, `name`, `is_active`, `created_at` and says there is no code; `EP-ADM-26` accepts only `name`. **Nothing could ever have populated `code`**, so the wire was wrong and the wire changed. **No `code` column was added** — that would be a data-model change made from a display field, and the table is `P-ADM-23`'s. |
| `P-BRW-04`, `SCR-BRW-01` | **contradiction closed inside one row** — the two-or-more rule reaches **every** reference-backed filter, language included | Which controls render. The table's fourth column said language was "Rendered in v1: yes" unconditionally, two lines under a rule that admits no exception; the column meant *exists in v1 at all*. Column split and reworded, `date` marked as the one row the rule does not count (there is no vocabulary of dates), and language given its absence condition in `SCR-BRW-01` beside format's and cinema's. **No rule changed** — the table stopped contradicting it. |
| `P-BRW-04` | **`[JUDGMENT CALL]`** — "rows in use" on `EP-BRW-07` means *referenced by something the caller can currently see*, and `is_active` is not a filter here | Which filter controls render at all, and whether `P-ADM-24`'s promise holds. **`is_active` is excluded because including it would break `P-ADM-24`'s worked example**, in which a customer filtering by a withdrawn language still finds the film that carries it. **The `cinema` row of the definition table is the build session's, by symmetry with `format`** — the adjudicated table covers the four lookup vocabularies and this endpoint also returns cinemas, and any looser test would render a control for a venue with nothing showing. Reversible: one predicate per `{kind}`. |
| `P-BRW-01`, `EP-BRW-05`, `EP-BRW-06` | **contradiction closed, and the reserved half deliberately left open** (`J-GST-02`) — this row now tabulates which endpoints apply the visibility gates and which do not | The seat-map header and the seat map. This row claimed the predicate ran on *every* customer-facing query while `EP-BRW-05` stated the opposite for itself and `EP-BRW-03` and `EP-BRW-06` applied none either; **one of the two sentences was wrong today and no ruling on `OPEN-BRWVIS-01` makes both right.** The row is corrected to the endpoints that actually filter, so a developer has one instruction. **Whether the showtime-addressed endpoints *should* gate is `OPEN-BRWVIS-01` — `OPEN`, reserved, and not decided here**, because gating them settles the selling question in one direction and not gating them settles it in the other. Both blocks now carry the flag so the generated contract does too. |
| `P-BRW-04` | **justification corrected; the rule is unchanged** (`J-GST-01`) — the listing date strip **bounds** the range and does not promise a showtime on every day inside it | `SCR-BRW-01`'s date strip. The row justified the day-before rule on the ground that the strip "must never be able to reach the empty state", which was **false of the strip the same row specifies**: it is computed on the client from `display_until` alone, and `EP-BRW-01` carries no per-day showtime information, so no such test is possible without a request nobody specified. **The bound stands; the reason for it was overstated**, and an overstated reason is what a later reader implements. The accepted weakness — a day button inside the range can reach the ordinary filtered-empty state — is now stated. |
| `P-BRW-06`, `P-BRW-04` | **gap stated, and the missing check named rather than invented** (`J-GST-04`) — a showtime whose `starts_at` falls outside its film's display window is reachable from **no** guest browse surface | Both date strips and `next_date_with_showtimes` condition 2. All three are bounded by the display window, so all three assume every showtime falls inside it, and **no row in the document makes that true**. The bound is not widened — ranging over `max(starts_at)` would offer days on which the film has left its window, which `P-BRW-04` refuses to draw. **The check belongs on the write path and is raised against `P-ADM-07`**, which owns showtime creation. **Explicitly not `OPEN-BRWVIS-01`**: that row is about a boundary the clock crosses; this showtime is unreachable from the instant it is created. |
| `P-BRW-11`, `SCR-BRW-03`, `EP-BRW-06` | **contradiction closed** (`J-GST-07`) — a 429 on a **poll** and a 429 on the **first load** take two different strings | The seat map's first load. `SCR-XCT-03` sent every 429 on this endpoint to `SCR-BRW-03`'s `Too many requests. The seat map will update again shortly.`, and on a first load **there is no map and no poll loop**, so the sentence promises an update nothing will deliver. Its own stated reason — the map re-polls on its own — holds for polls only. Exception 4 now names 429 and the copy row is scoped to the poll case. `SCR-XCT-03`'s over-broad sentence is E8's half and is raised there. |
| `P-BRW-11`, `EP-BRW-06` | **arithmetic stated rather than absorbed** (`J-GST-08`) — 120 per IP per minute admits **six** concurrent viewers from one address and refuses the seventh | Every guest behind an office, household, campus or carrier NAT address. One poller uses `60 / 3 = 20` a minute and `120 / 20 = 6`; the endpoint is unauthenticated so there is **no per-user bucket** to spread the load. The row previously said only that the limit is "far above what a legitimate poller uses", which is true of one viewer and false of six. **The number is not changed** — `120` is `FR-ADR-058`, `APPROVED`, and lengthening the interval trades against the staleness bound. **Six is derived from two configured numbers, not measured; nothing here has run in AWS.** |
| `P-BRW-04`, `SCR-BRW-01`, `EP-BRW-07` | **`[JUDGMENT CALL]`** (`J-GST-10`) — a reference-endpoint outage renders the listing in full plus one line, `Filters are unavailable right now.` | The listing screen's filter area. This row listed a reachable `EP-BRW-07` as a **precondition with no failure path**, and `SCR-BRW-01`'s Error state covered only the listing failing — so an outage rendered a listing with no filter controls, **which is also the correct day-one rendering**. Two states, byte-identical on screen, meaning opposite things. **The judgment call is the line, not the behaviour**: the controls' absence follows from `FR-ADR-046`, and no source says whether the screen should say so. `SCR-BRW-01` owns the string (`S1.2.1` case 3). The date strip and `Clear filters` are untouched, the latter because a control that vanishes with the thing it repairs cannot repair it. Reversible: one string and one condition. |

### Where I would have had to guess and did not

1. **What "newest" is computed from.** Three candidates — `published_at`, `display_from`, `created_at`
   — give three different listings. Not guessed: `FR-ADR-021` names `published_at DESC`, and this
   section states it, with `id DESC` as the tiebreak so two movies published in one transaction do not
   shuffle between requests. **The tiebreak is the build session's** and is the only part of the
   ordering that no source states.

2. **Which sorts the customer may choose.** `FR-ADR-021` says a customer-chosen sort exists; nothing
   says what it may be. I did not invent a menu. `sort` accepts one value, no control renders while
   there is one value, and the question is `PROPOSED-SORT-01`.

3. **What a format is, and what formats exist.** Raised as `PROPOSED-FORMAT-01` rather than seeding
   "2D / 3D / IMAX", which would have been invented product content in front of the client.

4. **How far ahead the date strip runs.** Every horizon I could pick — 7 days, 14, 30 — is a number no
   source supports. I derived it instead: today in Asia/Kolkata to the last day of the movie's display
   window, which needs no constant and cannot disagree with `P-BRW-01`.

5. **A latency budget for `R-QLY-04`.** `SRC-001 §7.3` says "pages should feel immediate" and states
   no number, and neither does any ADR. **I wrote no p95, no time-to-first-byte and no render budget.**
   `P-BRW-14` lists what *is* specified with its source, says plainly that no numeric budget exists,
   and replaces it with binary criteria and a Phase 3 measurement obligation. This is the row most
   likely to be "helpfully" filled in by a later session, and the seven-minute hold is what that looks
   like a document later.

6. **What happens to a showtime whose movie has left its window.** Raised as `PROPOSED-BRWVIS-01`, now
   `OPEN-BRWVIS-01`. I specified only the half `FR-ADR-021` actually settles — the browse surface hides
   it — and marked `EP-BRW-05`'s authorisation rule accordingly, without deciding whether it may still
   be sold. **`P-BRW-01` now tabulates which endpoints gate and which do not**, so the row and the two
   blocks agree on the *fact* while the *policy* stays with the client. **Nothing was decided to close
   that contradiction**, and the temptation was real: gating `EP-BRW-05` would have looked like a
   tidy-up and would have answered a reserved question by side effect.

7. **Whether a draft movie's poster should be reachable.** `EP-BRW-03` is public and `EP-BRW-02` is
   gated, so a poster id discloses that a draft exists. Consistent with `FR-ADR-017` (movie and
   showtime ids are not private) but stated rather than assumed away; it is a decision the admin lane
   may want to reverse.

8. **A rate limit for the browse endpoints.** `FR-ADR-058`'s table limits the seat map read and nothing
   else in this epic. I did not add limits to the listing, the showtime list or the poster redirect.
   Noted rather than invented: the poster endpoint mints a presigned URL per request and is unlimited,
   which is an unbounded presigning path.

9. **Whether `display_until` may be null** for an open-ended run. The client asked for a deadline by
   name, so both window columns are `NOT NULL` — scope as written. Stated so a later session sees it
   was a reading and not an oversight.

10. **What a mixed-category grid row means for the customer.** `P-BRW-16` specifies what is **drawn**
    — no band gap, no rule, and a one-line notice when no band exists at all — and **invents no rule
    forbidding the admin from creating one**, because `FR-ADR-016` lets them assign any category to
    any seat and nothing withdraws that. The layout is described; the admin is not constrained from
    here.

11. **What an out-of-service seat should look like.** The behaviour is `P-ADM-15`'s and the state
    count is `FR-ADR-045`'s; **neither names a treatment.** The dashed border reuses an existing token
    rather than adding a colour, and it is recorded as a judgment call above rather than presented as
    derived.

### Contradictions found

**1. `FR-ADR-028` against `FR-ADR-058`, on the seat map read when Redis is down.** Both are `APPROVED`
and immutable.

- **`FR-ADR-028`, section 2:** "Cache — degrade silently and serve from PostgreSQL… Browsing, **the
  seat map read path**, movie listings and a customer's own bookings all keep working, slower."
- **`FR-ADR-058`:** the seat map read is a limited endpoint at 120 per minute per IP, and "On Redis
  being unreachable, the limiter fails closed: 503."

The limiter runs before the cache, so the seat map read cannot both serve from PostgreSQL and return
503. The movie list and the showtime list are not in `FR-ADR-058`'s table and are unaffected — the
conflict is exactly one endpoint wide. **This lane adopted 503** as the stricter option (Art III.10)
and marked `P-BRW-12` `PROVISIONAL`. It needs adjudication, not a lane's preference.

**2. `COMPONENTS.md §0.4` against the arithmetic rule this lane specified.** `COMPONENTS.md` says the
running total "uses the same per-seat half-up rule the server uses", and `FR-ADR-045` says the client
computes the total "from the per-seat prices in the map payload using the same rounding rule as the
server". `P-BRW-10` sends **already-rounded** per-seat prices so the client never rounds at all. That is
stricter, not contrary — the client sums integers and cannot reach a different number — but it is a
deliberate narrowing of two written statements and is recorded rather than absorbed.

**3. `SRC-001 §5.1.3` against `SRC-003 C-2`, already resolved and noted only for completeness.** The
source requires a cinema filter; the ruling leaves one cinema. `FR-ADR-046` resolves it — the capability
exists, the control does not render — and this lane implements exactly that. Not re-litigated.
