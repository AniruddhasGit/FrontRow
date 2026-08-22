# E6 — admin: movies, showtimes, pricing, halls

This epic is everything in FrontRow that **writes**. An admin types every film into the system by
hand — title, poster, the details a customer reads, and the window it is shown in — creates every
showtime on every hall, sets the base price on each of those showtimes, sets the percentage uplift
each seat category carries, configures the seat layout of each hall, types the lists a film is built
from — its languages, certifications, genres and formats — creates the manager accounts that read
the dashboard, and edits the one venue those halls belong to and the time zone every date in the
product is shown in. Nothing here is automatic. There is no external film source, no
import, no upsert and no schedule (`SRC-001 §E E-4`, `SRC-002 §E E-2`, `§E E-4`). Every one of these
actions belongs to the admin role alone (`SRC-003 OPEN-OPS-03`), every one of them writes an audit
row in the same database transaction as the change (`FR-ADR-019`), and none of them ever deletes a
historical record (`FR-ADR-012`).

**The one thing that will be got wrong.** `SRC-001 §5.5.1` gives showtime creation and pricing to the
**manager**, and a developer reading that clause alone will build a manager write endpoint. That
clause is superseded: `SRC-003 OPEN-OPS-03` moved every privileged write to the admin, and a manager
endpoint that writes anything is a defect and not a feature. The second thing that will be got wrong
is the pair of gates on a film. **Publication and the display window are two separate conditions and
both must pass** before a customer sees a film (`FR-ADR-021`); collapsing them into one flag means an
admin has to unpublish a film to change its dates. The third is `R-ADM-04`'s layout freeze: once a
single showtime exists on a hall, a seat may be added and may be taken out of service, but it may not
be removed, renumbered or moved to another category — and the client will feel that limit the first
time they mistype a seat number after a showtime exists.

---

## S4 — Product specifications

### Field provenance — read before the validation tables

Every bound in this section is marked with where it comes from. Three markings are used and they are
not interchangeable:

| Marking | Means |
|---|---|
| **ruled** | the figure is in a frozen source or an `APPROVED` record, cited on the row |
| **derived** | the figure follows by arithmetic or by logic from a ruled fact, and the derivation is stated |
| **technical** | a storage or arithmetic bound chosen by the build session under Art III.9 because a column needs one. **It is not a business figure**, nothing downstream may treat it as one, and the client may change any of them without any other change |

A bound with no marking is a defect in this document.

### Admin datetimes are naive local in both directions

**The write half is `P-ADM-04`'s and is already ruled**: `display_from`, `display_until`, `starts_at`
and `ends_at` arrive as **local date and time in Asia/Kolkata with no `Z`, no offset and no zone name**,
and a value carrying one is `422` and is never coerced.

**The read half matches it. These four fields are returned in the same naive local form they are
accepted in**, so an admin form round-trips with no conversion at either end.

**This is the one place in the product that does not carry the cinema's offset on the wire, and that is
deliberate rather than an oversight.** Everywhere a **customer** reads an instant, the response carries
`+05:30` and the client never converts, because a client converting UTC is a second implementation of
the zone rule and it is the one that is wrong on a device set to another country. **These four fields
are not that.** They are values an admin **typed as local time** and will **edit again as local time**,
in a field labelled with its zone, and a round trip through an instant is exactly where the silent
one-day shift the write rule refuses would reappear — this time with the server, not the caller, doing
the shifting. **Naive in, naive out, and nothing converts anywhere.**

**Storage is unchanged and is not what this rule is about.** Both columns stay `timestamptz` in UTC
(`FR-ADR-018`); the conversion happens once, at the boundary, using the cinema row's zone
(`P-ADM-26`). The worked examples on `P-ADM-04` and `P-ADM-07` show the stored UTC instants and stay
correct — **what changed is the shape on the wire, not the shape in the database.**

**The boundary, because the rule would otherwise be read too widely.** It covers **only the four fields
the write path accepts**. Every other instant this section returns is **server-generated, never typed
by an admin and never edited back into a form** — `published_at`, `created_at`, `occurred_at`,
`evaluated_at_utc` — and those stay ISO-8601 instants carrying their zone, exactly as they are today.
**A field an admin typed round-trips; a field the server stamped does not need to.**

### Unknown properties are rejected, never ignored

**Every admin endpoint in this section rejects a body property it does not define.** The status and the
code are stated once here and nowhere else: **`400 REQUEST_INVALID`**, which is the registry's own
definition of the case — *"the body does not parse, or it carries a property the endpoint does not
define. Unknown fields are rejected, never ignored."* Every body-carrying block in `S6` declares the
`400` and carries the code, so an admin endpoint can actually return it.

**This replaced three different answers, and the disagreement stopped an engineer before the first
model was written.** `P-ADM-01` said `published_at` was *"ignored"*; `P-ADM-23` said three fields were
*"ignored if supplied"*; `P-ADM-17` said a `role` property was **rejected**, with a stated
privilege-escalation reason; and the registry said unknown fields are always rejected while naming no
admin endpoint that could return the code. **No single request-model configuration satisfies all four**
— a model either forbids extra properties or it does not — and per-field special cases are precisely
what nothing specified.

**`P-ADM-17`'s argument is the one that generalises, so it wins.** A server that silently drops a
property teaches the client that sending it was harmless; the next property that client sends and the
server drops is one that mattered, and nothing anywhere reports it. The `role` case makes the stakes
concrete — a dropped `role` reads to the caller as a role that was accepted — but the reasoning is not
about privilege: **it is about a request that was not carried out being answered as though it was.**

**Two consequences worth stating, because both are asked.** A field this section marks *"not accepted
from the request"* — `published_at`, `poster_object_key`, `is_active` on creation, `id`, `role` — is
now **rejected** if supplied, not dropped, and the row that names it says so. And `P-ADM-17`'s `role`
case, which was published as `422 VALIDATION_FAILED`, becomes **`400 REQUEST_INVALID`** like every
other unknown property: **its sentence does not change**, only the envelope carrying it, because the
registry fixes a code's status and a block may not contradict it.

**Where a value is genuinely optional and absent, nothing here applies.** This rule is about a property
the endpoint does not define arriving in the body. An optional property the endpoint *does* define,
omitted, is the ordinary partial-update case immediately below.

### Partial updates — every bound is evaluated against the merged row

**Every `PATCH` in this section is a partial update.** The fields the request carries are the fields it
changes; every field it omits keeps its stored value. That much is ordinary. The part that is **not**
ordinary, and that an implementer gets silently wrong, is this:

> **Every bound in every validation table below is evaluated against the row as it would be *after* the
> patch is applied — never against the submitted fields alone.** A bound written on one field of a pair
> ("strictly after `display_from`") is a bound on the **pair in the merged row**, not a bound that
> switches itself off when its partner is absent from the request.

**Why it has to be said once, generally.** Both halves of a paired bound are optional on a `PATCH`, so
a bound written on the field can be read honestly as applying only to what was sent — and read that
way, a request carrying one half is checked against nothing and an inverted pair is stored. The two
pairs this section owns are `display_from` / `display_until` (`P-ADM-04`) and `starts_at` / `ends_at`
(`P-ADM-09`), and each states the consequence on its own row.

**Where the merged row comes from.** The comparison happens **inside the transaction**, against the row
the transaction re-read for the `version` check (`P-ADM-12`) — not against a copy the handler read
earlier. The same re-read serves both checks, and a bound evaluated against a row read outside the lock
is a bound evaluated against a row that may already have moved.

**A `PUT` in this section is not a partial update and does not need this rule.** `EP-ADM-24` replaces a
complete set and says so in its own block; the distinction is deliberate and is why that endpoint is a
`PUT` and these are `PATCH`es.

---

### `P-ADM-01` · Create a film by hand · `RULED`
`[SRC: SRC-003 OPEN-ROLE-01 · SRC-003 OPEN-TMDB-01 · SRC-003 OPEN-TMDB-04 · SRC-001 §5.1.1 · SRC-001 §E E-4 · FR-ADR-006 · FR-ADR-021 · FR-ADR-061]`
`[BRD: R-ADM-01]`

**Behaviour.** The admin creates a film row by typing its details into a form. The row is created as a
**draft**: `published_at` is null and the poster is absent. A draft is invisible to every customer and
to every guest, and it can be pointed at by a showtime, so scheduling and authoring do not block each
other.

**There is no other way a film enters this system.** No external API, no import job, no upsert by an
external id, no `pending` state arriving from a sync, no scheduled trigger. `SRC-002 §10` is withdrawn
in full.

**Who may do it.** **admin only.** Enforced by a single router dependency on the `/api/admin` router
(`P-ADM-18`), never inside the handler.

**Preconditions.**
1. The caller holds a valid session token.
2. The caller's role is `admin`.
3. The `language` and `certification` values named in the request exist as rows in their lookup tables
   (`FR-ADR-021`). **`P-ADM-23` is what creates those rows, and nothing else does** — this
   precondition cannot be met on a fresh database until the admin has created at least one of each.
4. Every `genre_id` named in the request exists, for the same reason and by the same route.

**Happy path.**
1. The admin opens the film editor (`SCR-ADM-02`) with no film id.
2. The admin fills the fields below and submits.
3. The server validates every field. Any failure rejects the whole request; nothing partial is
   written.
4. In one transaction the server inserts the `movie` row with `published_at = NULL`,
   `poster_object_key = NULL` and `version = 1`, inserts the `movie_genre` join rows, and inserts one
   `audit_log` row with `action = "movie.created"`, `before = null` and `after` carrying the submitted
   field values (`FR-ADR-019`).
5. The server returns 201 with the created film, including its `id` and its `version`.
6. The editor reloads at `/admin/movies/{id}` and the poster panel becomes usable.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | No session token | 401 `AUTH_REQUIRED` | "Sign in to continue." |
| 2 | Signed in as guest, customer or manager | 403 `FORBIDDEN` | "This page is for administrators. Your account cannot change films, showtimes, prices or halls." |
| 3 | `title` empty or longer than its bound | 422 `VALIDATION_FAILED` | "Enter a title of 1 to 200 characters." |
| 4 | `runtime_minutes` missing, zero, negative or not a whole number | 422 `VALIDATION_FAILED` | "Enter the runtime in whole minutes, 1 or more." |
| 5 | `synopsis` longer than its bound | 422 `VALIDATION_FAILED` | "The synopsis is longer than 4000 characters. Shorten it." |
| 6 | `language_id` or `certification_id` does not exist | 422 `VALIDATION_FAILED` | "That language is not on the list. Choose one of the listed languages." / "That certification is not on the list. Choose one of the listed certifications." |
| 7 | `genre_ids` empty, or holds an id that does not exist, or holds a duplicate | 422 `VALIDATION_FAILED` | "Choose at least one genre from the list." |
| 8 | Postgres unreachable | 503 `DEPENDENCY_UNAVAILABLE` | "The system cannot reach its database right now. Nothing was saved. Try again in a moment." |
| 9 | Anything unhandled | 500 `INTERNAL_ERROR` | "The server could not complete this request. If you need help, quote `a1b2c3d4`." — **`E8`'s published sentence for the code. This section mints no variant of it** (`P-ADM-19`) |

**Server-side validation.** The interface repeats every one of these; **the interface is never the
enforcement point.**

| Field | Type | Bound | Provenance | On failure |
|---|---|---|---|---|
| `title` | string | 1..200 characters after trimming | **technical** | exception 3 |
| `synopsis` | string | 0..4000 characters | **technical** | exception 5 |
| `runtime_minutes` | integer | `>= 1` | **derived** — a film with a zero or negative runtime cannot produce a showtime end instant (`FR-ADR-018`) | exception 4 |
| `certification_id` | integer | must exist in `certification` | **ruled** (`FR-ADR-021`: a lookup table, not free text) | exception 6 |
| `language_id` | integer | must exist in `language` | **ruled** (`FR-ADR-021`; `SRC-001 §5.1.3` makes it a customer filter) | exception 6 |
| `genre_ids` | array of integer | 1..10 entries, unique, each must exist | **ruled** many-to-many (`FR-ADR-021`); the count of 10 is **technical** | exception 7 |
| `published_at` | — | **not accepted on this endpoint.** Publication is `P-ADM-05` | **derived** (`FR-ADR-021`: two separate gates) | **400 `REQUEST_INVALID`** if supplied — rejected, never dropped |
| `poster_object_key` | — | **not accepted on this endpoint.** The poster arrives through `P-ADM-03` | **ruled** (`FR-ADR-061`) | **400 `REQUEST_INVALID`** if supplied |

**Title is deliberately not unique** (`FR-ADR-021`). Two films may share a title and a re-release is a
legitimate second row. Nothing in this specification checks a title against another title.

**Demonstration content.** See `P-ADM-22`. No real title, poster, synopsis or brand is entered by the
build session anywhere, including in examples, fixtures and seed data, while `OPEN-ATTRIB-01` is open.

---

### `P-ADM-02` · Edit a film, with optimistic concurrency · `RULED`
`[SRC: SRC-003 OPEN-TMDB-04 · SRC-001 §5.1.1 · FR-ADR-021 · FR-ADR-035 · FR-ADR-019]`
`[BRD: R-ADM-01 · R-ADM-05]`

**Behaviour.** The admin changes any authored field of a film — title, synopsis, runtime,
certification, language, genres — on a draft or on a published film. The request carries the `version`
the admin read; if the stored version has moved, the write is refused and nothing is changed.

**Who may do it.** **admin only**, by the router dependency (`P-ADM-18`).

**Preconditions.**
1. The film exists.
2. The submitted `version` equals the stored `version`.

**Happy path.**
1. The admin loads `/admin/movies/{id}`; the response carries `version`.
2. The admin edits fields and submits, echoing `version` unchanged.
3. In one transaction the server re-reads the row, compares the version, applies the changes,
   increments `version` by 1, and inserts an `audit_log` row with `action = "movie.updated"`,
   `before` carrying **only the fields that changed** and their prior values, `after` carrying the same
   fields' new values (`FR-ADR-019`).
4. The server returns 200 with the updated film and its new `version`.

**Editing a published film takes effect immediately** on every customer surface. That is the ruled
behaviour and not an oversight: a typo in a title is corrected without unpublishing. It changes
nothing about any booking, because a booking's film reference is a foreign key to this row and the
money on it is snapshotted elsewhere (`FR-ADR-039`).

**"Immediately" is a mechanism and not a hope, and the mechanism is `P-BRW-12`'s.** This write makes
every cached listing that could contain the film unreachable once it commits, so no customer read can
return the pre-edit listing. `P-BRW-12` owns that mechanism and this row does not restate it.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | No session token | 401 `AUTH_REQUIRED` | "Sign in to continue." |
| 2 | Not an admin | 403 `FORBIDDEN` | "This page is for administrators. Your account cannot change films, showtimes, prices or halls." |
| 3 | No film with that id | 404 `NOT_FOUND` | "That film no longer exists at this address." |
| 4 | `version` missing from the request | 422 `VALIDATION_FAILED` | "This form is out of date. Reload the page and make the change again." |
| 5 | `version` does not match the stored value | 409 `VERSION_CONFLICT` | "This film was changed by someone else while you were editing. Reload to see the current details, then make your change again. Nothing you typed has been saved." |
| 6 | Any field fails its bound | 422 `VALIDATION_FAILED` | the same wording as `P-ADM-01` exceptions 3 to 7 |
| 7 | Postgres unreachable | 503 `DEPENDENCY_UNAVAILABLE` | "The system cannot reach its database right now. Nothing was saved. Try again in a moment." |

**Server-side validation.** Every field bound of `P-ADM-01` applies unchanged. Additionally:

| Field | Type | Bound | Provenance | On failure |
|---|---|---|---|---|
| `version` | integer | required, `>= 1`, must equal the stored value | **ruled** (`FR-ADR-035`) | exceptions 4 and 5 |

**Last-write-wins is refused** (`FR-ADR-035`). A silently discarded edit is the failure mode this
control exists for, and it is worst on a price (`P-ADM-12`).

---

### `P-ADM-03` · Upload a poster · `RULED`
`[SRC: SRC-002 §4.9 · SRC-002 §7.3 · SRC-002 §E E-2 · SRC-003 OPEN-TMDB-01 · FR-ADR-021 · FR-ADR-061 · FR-ADR-012]`
`[BRD: R-ADM-01]`

**Behaviour.** The admin uploads one image file for a film. The API validates it and uploads it to a
**private** S3 bucket. **Nothing is written to the container's local disk at any point**
(`SRC-002 §7.3`: no local file uploads). The stored object key is generated by the server; the
client's filename is never used.

**The body is held in memory, bounded, and the earlier claim that it never was is withdrawn.** This
row previously said *"the whole file is never buffered in memory, because the size limit is enforced
before the body is read"* — and its own steps 6 and 7 read the leading bytes, decode the image and
measure its pixel dimensions, none of which is possible without the bytes. **A decode is not a
streaming operation**, and a specification that requires one while denying the buffer leaves an
implementer to choose between the two silently. **The buffer is what is true; the `Content-Length`
check is what bounds it.**

**What the header check actually buys, stated exactly.** It is not the absence of a buffer. It is
that the buffer's size is **known and refused before a byte is read**, so no request can make the
process hold more than the limit (`FR-ADR-061`, 2 MB, configuration). Without it the body would be
read to discover how large it was, which is the failure the check exists to prevent
(`P-ADM-12`'s ordering block).

**The memory cost, worked through against the budget rather than asserted to be small.** The API
process is budgeted at roughly **200 MB** on a `t3.micro` host with about 1 GB total
(`SRC-002 §5.4.1`).

```
peak poster memory  =  concurrent uploads in flight  x  2 MB       (the Content-Length cap)

 1 concurrent upload  ->    2 MB     1.0 % of the 200 MB API budget
 5                    ->   10 MB     5.0 %
10                    ->   20 MB    10.0 %
50                    ->  100 MB    50.0 %   <- the API budget is now half poster bytes
```

**There is one admin account and no rate limit on this endpoint** (`FR-ADR-058` lists no admin
bucket; raised as `PROPOSED-ADMINRATE-01` in the Lane notes), **so the concurrency figure is bounded
by nothing in the specification.** In ordinary use it is 1. The row above is stated so that the
figure a limiter would have to hold is already computed when somebody sets one.
*(reasoned from the budget in `SRC-002 §5.4.1`, not observed — no application code exists and nothing
has run.)*

**The bytes reach S3 from that buffer**, in one `PutObject`, after every check has passed. Step 8's
word *streams* describes the transfer to S3 and not the read from the client, and the two are
different halves of the same request.

The poster is **served by 302 redirect to a presigned GET URL**, minted at request time and valid for
one hour. **The bucket has no public-read policy and nothing is ever hotlinked** (`FR-ADR-061`, which
rules both). **The authority is the record and not the clause it was derived from**: `SRC-002 §10` is
withdrawn in its entirety by `SRC-002 §E E-2`, so `§10.6.3` cannot be cited as live authority for
anything, and `FR-ADR-061` — which is `APPROVED` and carries this decision independently — is what
binds here.

**Who may do it.** **admin only**, by the router dependency (`P-ADM-18`). The admin-side read of a
poster (`EP-ADM-06`) is also admin only, because a draft film's poster must not be reachable before
the film is published.

**Preconditions.**
1. The film exists.
2. The request is `multipart/form-data` with exactly one file part **and a `version` form part**.
3. `Content-Length` is present. A request without it is refused rather than read.
4. The submitted `version` equals the film's stored `version`. **This is a `movie` write and it carries
   no exemption from `P-ADM-12`**, which owns the rule and the check ordering.

**Happy path.**
1. The admin opens the poster panel on `SCR-ADM-02`. **The panel states the size limit and the
   accepted formats before the file is chosen** (`FR-ADR-061`).
2. The admin chooses a file and submits. **The form round-trips the `version` it was loaded with**, as
   every admin form does (`P-ADM-12`, `SCR-ADM-02`).
3. The server checks `Content-Length` against the limit **at the header, before reading the body**.
4. The server compares the submitted `version` against the stored one and refuses a mismatch **before
   a single byte is streamed to S3**, so a stale upload costs no object (`P-ADM-12`).
5. The server checks the declared content type against the accepted list.
6. The server reads the leading bytes and checks that the file's actual magic bytes match the declared
   type.
7. The server decodes the image and checks its pixel dimensions are inside the accepted range.
8. The server streams the bytes to S3 at `posters/{movie_id}/{random}.{ext}`, where `{random}` is
   server-generated.
9. In one transaction the server re-reads the row, compares `version` again inside the transaction,
   sets `poster_object_key` to the new key, increments `version`, and
   inserts an `audit_log` row with `action = "movie.poster_replaced"` (or `"movie.poster_uploaded"` on
   the first upload), `before` carrying the previous key or null, `after` carrying the new key.
10. The server returns 200 with the film and its new `version`.
11. **The previous object is not deleted** (`FR-ADR-012`). It stays in the bucket so an audit row's
    `before` value still resolves to a real image.

**The version is compared twice and that is deliberate.** Step 4 is the cheap refusal that saves the
S3 write; step 9 is the comparison that actually decides the write, taken inside the transaction after
re-reading the row, exactly as `P-ADM-12` requires of every admin write. Step 4 alone would leave a
window between the check and the commit; step 9 alone would stream a doomed file to S3 first.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | Not an admin | 403 `FORBIDDEN` | "This page is for administrators. Your account cannot change films, showtimes, prices or halls." |
| 2 | No film with that id | 404 `NOT_FOUND` | "That film no longer exists at this address." |
| 3 | The `version` form part is absent | 422 `VALIDATION_FAILED` | "This form is out of date. Reload the page and make the change again." |
| 4 | `version` does not match the stored value | 409 `VERSION_CONFLICT` | "This film was changed by someone else while you were editing. Reload to see the current details, then make your change again. Nothing you typed has been saved." |
| 5 | `Content-Length` absent | 411 → returned as 422 `VALIDATION_FAILED` | "The upload did not declare its size and was not accepted. Try again." |
| 6 | `Content-Length` above 2 MB | 413 `PAYLOAD_TOO_LARGE` | "That file is larger than 2 MB. Choose a smaller image." |
| 7 | Declared content type is not `image/jpeg`, `image/png` or `image/webp` | 415 `UNSUPPORTED_MEDIA_TYPE` | "Posters must be a JPEG, PNG or WebP image." |
| 8 | Declared type does not match the file's leading bytes | 415 `UNSUPPORTED_MEDIA_TYPE` | "That file is not the image type it says it is. Choose a JPEG, PNG or WebP image." |
| 9 | The image cannot be decoded | 415 `UNSUPPORTED_MEDIA_TYPE` | "That file could not be read as an image. Choose a JPEG, PNG or WebP image." |
| 10 | Pixel dimensions outside 200×300 to 4000×6000 | 422 `VALIDATION_FAILED` | "Poster images must be between 200 by 300 and 4000 by 6000 pixels." |
| 11 | No file part, or more than one file part | 422 `VALIDATION_FAILED` | "Choose exactly one image file." |
| 12 | S3 is unreachable, times out, or answers a **retryable** failure — a 5xx or a throttle | 503 `DEPENDENCY_UNAVAILABLE` | "The system cannot reach its file storage right now. The poster was not saved. Try again in a moment." |
| 12b | S3 **refuses** the write with a failure a retry cannot clear — the credential is not permitted to write, the bucket does not exist, or a storage quota or bucket policy refuses the object | 500 `INTERNAL_ERROR` | **`E8`'s one published sentence for the code** — "The server could not complete this request. If you need help, quote `a1b2c3d4`." This row mints no wording of its own |
| 13 | The bytes reached S3 but the database write failed | 503 `DEPENDENCY_UNAVAILABLE` | "The system cannot reach its database right now. The poster was not saved against this film. Try again in a moment." |

**Exceptions 3 and 4 are `P-ADM-12`'s rule applied here, not a second rule.** Exception 4's sentence is
the one every other film write already publishes, verbatim; the poster path does not get a wording of
its own. Exception 4 normally fires at step 4, before anything is streamed, and costs nothing. It can
also fire at step 9 — the in-transaction comparison — in which case the object has already been
written and is left unreferenced in the bucket, which is exception 13's condition and is treated the
same way.

**Exception 12 was one row covering two different futures, and the sentence was wrong for one of
them.** *"Try again in a moment"* is correct for a bucket that is briefly unreachable and **false for
a bucket that refuses the write** — a credential without `s3:PutObject`, a bucket name that does not
resolve, a policy or a quota that says no. Under one row the admin retries an action that can never
succeed, and because `P-ADM-05` refuses publication without a poster, **no new film can be published
until somebody diagnoses the real cause by hand.** The split is on the answer S3 gives — retryable or
not — which is a distinction the SDK already makes and the handler already has.

**12b answers `500` and reuses an existing sentence rather than minting one.** The admin cannot fix a
storage credential or a bucket policy from a form, so nothing this row could say to them would be an
instruction; what they need is a **request id to quote**, which is exactly what the `INTERNAL_ERROR`
envelope carries and what the `503` sentence does not. **A new variant of an existing sentence is a
defect, not a refinement** (`P-ADM-12`), so no poster-specific wording is invented for 12b. No new
error code is minted either: `INTERNAL_ERROR` is already in `EP-ADM-05`'s `errors` array.

**The 5 GB figure and what is honestly known about it.** `SRC-002 §5.2.5` gives the bucket a 5 GB
allowance; `FR-ADR-012` deletes nothing, so **every replaced poster stays forever** and the bucket
grows monotonically — reachable in roughly 2,500 uploads at the 2 MB cap. **Whether exhausting that
allowance produces a refused `PutObject` at all is not known to this specification**: it is a
free-tier billing allowance rather than a bucket-level hard quota, and **this session has never
observed anything running in AWS**, so the behaviour is reasoned and not observed. 12b is written
against *any* non-retryable refusal for that reason — it does not depend on the allowance being the
thing that refuses. **What is certain is the growth and that nothing watches it**: no metric in this
product names S3 storage, and the operator's remedy is manual. Raised as
`PROPOSED-ADMINRATE-01` in the Lane notes, which already names this endpoint's unlimited write to a
5 GB allowance with no deletion path.

**Exception 13 is stated rather than hidden.** S3 is not in the database transaction, so a crash
between step 8 and step 9 leaves an orphan object in the bucket. That is the correct failure
direction: the object is unreferenced, costs a few kilobytes against a 5 GB allowance
(`SRC-002 §5.2.5`), and no film points at a poster it does not have. **No compensating delete is
performed**, because deletion is not in this system's vocabulary (`FR-ADR-012`).

**Server-side validation.**

| Field | Type | Bound | Provenance | On failure |
|---|---|---|---|---|
| `version` | integer | required, `>= 1`, must equal the stored value. **A form part of the multipart body**, not a header and not a query parameter | **ruled** (`FR-ADR-035`, through `P-ADM-12`) | exceptions 3, 4 |
| `Content-Length` | integer | present, `<= 2097152` bytes | **ruled** (`FR-ADR-061`: 2 MB, and it is configuration) | exceptions 5, 6 |
| declared content type | string | one of `image/jpeg`, `image/png`, `image/webp` | **ruled** (`FR-ADR-061`) | exception 7 |
| leading bytes | bytes | must match the declared type | **ruled** (`FR-ADR-061`) | exception 8 |
| decodability | — | the image decodes | **ruled** (`FR-ADR-061`) | exception 9 |
| pixel width × height | integer | 200..4000 × 300..6000 | **technical** — `FR-ADR-061` requires "a sane range" and states no figures. `--fr-poster-ratio` is 2:3, and these are that ratio's bounds at a legible minimum and a 2 MB-plausible maximum | exception 10 |
| object key | string | server-generated, `posters/{movie_id}/{random}.{ext}` | **ruled** (`FR-ADR-061`) | never client-supplied |

**Local development, stated honestly** (`FR-ADR-061`). There is **no local S3 stand-in**. MinIO was
rejected as a new dependency under `SRC-002 §13.1`. Local development either uses a real S3 bucket
with the developer's own credentials, or runs with no posters at all — which is a supported state,
because `poster_object_key` is nullable until publication. **This means the upload path is not fully
exercised locally without AWS credentials, and the poster validation above is the part of this epic
least likely to be caught by a local test run.** It is the weakest point in this specification and it
is written down rather than discovered.

---

### `P-ADM-04` · Set a film's display window · `RULED`
`[SRC: SRC-003 OPEN-ROLE-01 · SRC-003 OPEN-TMDB-01 · FR-ADR-021 · FR-ADR-018]`
`[BRD: R-ADM-02]`

**Behaviour.** The admin sets the two instants between which a published film is shown to customers.
The client asked for "a deadline of how long this will stay" (`SRC-003 OPEN-ROLE-01`), and this is it.
**`display_from` is inclusive and `display_until` is exclusive** (`FR-ADR-021`), so a film at exactly
`display_until` is out.

The window is **one of two gates**. It is not publication and it does not substitute for it
(`P-ADM-05`).

**Every admin datetime on the wire is a naive local value, and a value carrying a zone is refused
rather than coerced.** `display_from`, `display_until`, `starts_at` and `ends_at` are **local date and
time in Asia/Kolkata with no `Z`, no `+hh:mm` offset and no zone name**; the server supplies the zone,
from the cinema row (`P-ADM-26`). **A submitted value carrying an offset or a zone designator is
`422 VALIDATION_FAILED` and is never coerced** — parsed strictly, exactly as `E1 P-BRW-04` already
treats the `date` query parameter, and in the same words: *a datetime, an offset or a zone name in that
field is rejected rather than coerced*.

**Why refusing beats accepting, which is the same argument this row makes below about storage.** Under
the alternative, a script or an integration sending `2026-09-04T18:30:00Z` is silently understood as
`2026-09-05 00:00` local, and the film is shown from a day the admin never typed — **with no signal to
anybody**, because a coerced value is a valid value. Refusing costs one `422` to whoever sent it and
tells them what to send. **It is the strictness the interface never exercises**: the form submits a
naive local value by construction, so this rule is invisible until something other than the form talks
to the API, which is exactly when it matters.

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| — | Any admin datetime field carries `Z`, an offset or a zone name | 422 `VALIDATION_FAILED` | "Enter a date and a time for both the start and the end of the display window." on this row; `P-ADM-07` exception 6's wording on a showtime. **The form cannot produce this**, so no new sentence is minted for it |

**Both values are stored exactly as the admin entered them — converted from the local zone to an
instant, and adjusted in no other way.** The server adds no day, rounds nothing to midnight, and
derives neither end from the other: **the admin types the exclusive end instant** and `EP-ADM-04`
accepts an instant, not a date. This is stated at the write because the read path evaluates the gate
against these two stored instants and must be able to cite something unambiguous; a server that
silently shifted what an admin typed by a day would be the worse of the two designs, because the admin
would get no signal that it had happened.

**Who may do it.** **admin only**, by the router dependency (`P-ADM-18`).

**Preconditions.**
1. The film exists.
2. The submitted `version` matches.

**Happy path.**
1. The admin enters a local start date and time and a local end date and time in **Asia/Kolkata**, on
   `SCR-ADM-02`.
2. The server converts both to instants using the cinema's stored zone and stores them as
   `timestamptz` in UTC (`FR-ADR-018`).
3. In one transaction the server writes both columns, increments `version`, and inserts an `audit_log`
   row with `action = "movie.display_window_changed"` carrying both instants before and after.
4. The server returns 200.

**The window may be changed on a published film without unpublishing it.** That is the whole reason
the two gates are separate (`FR-ADR-021`).

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | Not an admin | 403 `FORBIDDEN` | "This page is for administrators. Your account cannot change films, showtimes, prices or halls." |
| 2 | No film with that id | 404 `NOT_FOUND` | "That film no longer exists at this address." |
| 3 | Either value is not a valid date and time | 422 `VALIDATION_FAILED` | "Enter a date and a time for both the start and the end of the display window." |
| 4 | `display_until` is earlier than or equal to `display_from` | 422 `VALIDATION_FAILED` | "The display window must end after it starts." |
| 5 | `version` does not match | 409 `VERSION_CONFLICT` | "This film was changed by someone else while you were editing. Reload to see the current details, then make your change again. Nothing you typed has been saved." |

**Server-side validation.**

| Field | Type | Bound | Provenance | On failure |
|---|---|---|---|---|
| `display_from` | ISO-8601 local date and time, Asia/Kolkata | required | **ruled** (`FR-ADR-021`, `FR-ADR-018`) | exception 3 |
| `display_until` | ISO-8601 local date and time, Asia/Kolkata | required, strictly greater than `display_from` **in the merged row** | **derived** — an empty or inverted window can never be satisfied, so the film would never appear and the admin would have no signal | exception 4 |

**Exception 4 fires on a partial `PATCH` that sends only one half of the window.** The bound is on the
pair as it would stand after the patch, not on the fields the request happened to carry (see *Partial
updates* at the head of `S4`). Submitting `display_from` alone can therefore fail with exception 4's
existing wording even though `display_until` was not sent, and submitting `display_until` alone can too.
**Nothing is written when it fails**, including no audit row and no `version` increment.

**Worked example — one field sent, and the film that would never have appeared.**

```
Stored:     display_from  = 2026-09-01 00:00   display_until = 2026-09-30 00:00   (Asia/Kolkata)

Admin sends: PATCH { "version": 4, "display_from": "2026-10-15 00:00" }     display_until omitted

Merged row would be:
            display_from  = 2026-10-15 00:00   display_until = 2026-09-30 00:00
            display_until > display_from  ->  FALSE                     the window is inverted

Result:     422 VALIDATION_FAILED, exception 4
            "The display window must end after it starts."
            Nothing is written. version stays 4.

Checked against the submitted field alone, display_from has no partner in the request and passes
every bound written on it - and the film is stored with a window no instant can satisfy. It stays
published, the admin is told nothing, and it never appears to a single customer.
```

**A window that is entirely in the past is accepted.** It is how a film is taken off the customer
surface without unpublishing it, and refusing it would make correcting a mistyped year impossible.

**Worked example — the exclusive end, in both zones.**

```
Admin enters:   display_from  = 2026-09-04 00:00  Asia/Kolkata
                display_until = 2026-10-02 00:00  Asia/Kolkata

Stored:         display_from  = 2026-09-03T18:30:00Z
                display_until = 2026-10-01T18:30:00Z        (Asia/Kolkata is UTC+05:30, fixed)

A customer at 2026-10-01T18:29:59Z  →  local 2026-10-01 23:59:59  →  INSIDE  →  film is visible
A customer at 2026-10-01T18:30:00Z  →  local 2026-10-02 00:00:00  →  OUTSIDE →  film is not visible
```

The second line is the case the inclusivity rule exists to make testable. `display_until` exclusive
means the film's last visible local day is 1 October, not 2 October.

---

### `P-ADM-05` · Publish a film, and refuse to publish an incomplete one · `RULED`
`[SRC: SRC-003 OPEN-TMDB-03 · SRC-003 OPEN-ROLE-01 · SRC-001 §E E-8 · FR-ADR-021 · FR-ADR-061 · FR-ADR-019]`
`[BRD: R-ADM-02]`

**Behaviour.** The admin publishes a film by setting `published_at`. **Publication and the display
window are two separate gates and both must pass** before any customer or guest sees the film:

```
visible_to_customer  =  published_at IS NOT NULL
                        AND  now  >=  display_from
                        AND  now  <   display_until
```

That predicate is computed in the cinema's zone against the injected clock, never against the
container's local time (`FR-ADR-018`), and **it lives in exactly one function**, because a missed
clause in a second copy shows an unpublished film to customers (`FR-ADR-021`).

**A film cannot be published without a poster.** This is a publish-time check and **not** a column
constraint, because a draft must be creatable before its poster exists (`FR-ADR-021`, `FR-ADR-061`).

**Who may do it.** **admin only**. `SRC-001 §5.5.4` — the administrator approves imported films — is
**withdrawn** by erratum `E-8`; nothing is imported and there is nothing to approve. The admin authors
and publishes.

**Preconditions.**
1. The film exists and `published_at` is currently null.
2. `poster_object_key` is not null.
3. `display_from` and `display_until` are both set.
4. The submitted `version` matches.

**Happy path.**
1. The admin presses the publish control on `SCR-ADM-02`.
2. The server re-reads the film inside the transaction and checks preconditions 2 and 3.
3. The server sets `published_at` to the current instant from the injected clock, increments `version`,
   and inserts an `audit_log` row with `action = "movie.published"`, `before = {"published_at": null}`,
   `after = {"published_at": "<instant>"}`.
4. The server returns 200. The film is now visible to customers **if and only if** the current instant
   is inside its display window.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | Not an admin | 403 `FORBIDDEN` | "This page is for administrators. Your account cannot change films, showtimes, prices or halls." |
| 2 | No film with that id | 404 `NOT_FOUND` | "That film no longer exists at this address." |
| 3 | `poster_object_key` is null | 409 `PUBLISH_BLOCKED` | "This film has no poster. Upload a poster before publishing it." |
| 4 | `display_from` or `display_until` is null | 409 `PUBLISH_BLOCKED` | "This film has no display window. Set the dates it is shown between before publishing it." |
| 5 | The film is already published | 409 `PUBLISH_BLOCKED` | "This film is already published." |
| 6 | `version` does not match | 409 `VERSION_CONFLICT` | "This film was changed by someone else while you were editing. Reload to see the current details, then make your change again. Nothing you typed has been saved." |

**Server-side validation.** Preconditions 2 and 3 are re-read **inside the transaction**, not from the
copy the form submitted. A poster deleted or a window cleared between the form load and the submit
must not publish an incomplete film.

**Publishing does not make a film visible on its own, and the interface says so.** After a successful
publish the editor states which of the two gates currently passes (`SCR-ADM-02`). A publish that
appears to do nothing, because the window has not opened, is the most likely confusion in this epic.

**Requiring a display window at publish is a build-session judgment** under Art III.9. `FR-ADR-021`
makes both gates necessary for visibility but does not say the window must exist at publish time.
Publishing without one produces a film that can never be seen and gives the admin no signal, so the
stricter reading was adopted. Adopting a stricter option needs no signature (Art III.10) and the
client may reverse it.

---

### `P-ADM-06` · Unpublish a film — withdrawal, not deletion · `RULED`
`[SRC: SRC-003 OPEN-OPS-02 · SRC-003 OPEN-TMDB-03 · FR-ADR-012 · FR-ADR-021 · FR-ADR-019]`
`[BRD: R-ADM-02 · R-ADM-07]`

**Behaviour.** The admin sets `published_at` back to null. The film disappears from every customer
surface immediately. **The row stays, its showtimes stay, and every booking against it still resolves
to a real film** — a customer's booking list and their receipt read the `movie` row directly, not
through the customer-visible predicate (`FR-ADR-021`).

**"Immediately" is a mechanism and not a hope, and the mechanism is `P-BRW-12`'s.** This write makes
every cached listing that could contain the film unreachable once it commits, so no customer read can
return a listing that still carries the withdrawn film. `P-BRW-12` owns that mechanism and this row
does not restate it.

**This is what "delete a film" means in FrontRow.** There is no delete endpoint for a film and none
will be added (`FR-ADR-012`).

**Who may do it.** **admin only**, by the router dependency (`P-ADM-18`).

**Preconditions.** The film exists, is published, and the submitted `version` matches.

**Happy path.**
1. The admin presses the unpublish control on `SCR-ADM-02` and confirms.
2. In one transaction the server sets `published_at = NULL`, increments `version`, and inserts an
   `audit_log` row with `action = "movie.unpublished"` carrying the prior instant in `before`.
3. The server returns 200.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | Not an admin | 403 `FORBIDDEN` | "This page is for administrators. Your account cannot change films, showtimes, prices or halls." |
| 2 | No film with that id | 404 `NOT_FOUND` | "That film no longer exists at this address." |
| 3 | The film is not published | 409 `PUBLISH_BLOCKED` | "This film is not published, so there is nothing to withdraw." |
| 4 | `version` does not match | 409 `VERSION_CONFLICT` | "This film was changed by someone else while you were editing. Reload to see the current details, then make your change again. Nothing you typed has been saved." |

**Unpublishing a film that has future showtimes with bookings is permitted, and the confirmation says
what it does.** The film leaves the browse surface; the showtimes stop being reachable through the
browse path; **the bookings are untouched, the customers keep their seats and their references, and
nothing is refunded, because nothing was cancelled.** Withdrawing the *showtime* is a different action
and it does not exist in v1 — see `P-ADM-21`.

**Server-side validation.** `version` as in `P-ADM-02`.

---

### `P-ADM-07` · Create a showtime, and nothing creates one automatically · `RULED`
`[SRC: SRC-001 §5.5.1 · SRC-001 §9.4 · SRC-003 OPEN-OPS-03 · SRC-003 OPEN-PRICE-01 · FR-ADR-021 · FR-ADR-018 · FR-ADR-022 · FR-ADR-037]`
`[BRD: R-ADM-03 · R-PRC-02]`

**Behaviour.** The admin creates a showtime by choosing a film, a hall, a start date and time, an end
date and time, a base price in paise, and **optionally a format**. **Nothing in this system creates a
showtime on its own, ever.**

**Format sits on the showtime, not on the film**, because one film runs 2D in one hall and 3D in
another on the same day. It is **optional**: a showtime with no format set answers `null` on the
browse surface and is excluded by any format filter — which is the honest behaviour, since a customer
filtering for 3D should not be shown a screening nobody has said is 3D. **This is the only place
`showtime.format_id` is written**, and it is what makes `R-BRW-03`'s format filter able to return
anything at all. There is no schedule, no generator, no repeat rule, no copy-last-week action and no import
side effect. `SRC-001 §9.4` states it as an assumption the client asked to have confirmed, and the
substance of the withdrawn `SRC-001 §5.6.3` survives independently on this row.

**Who may do it.** **admin only.** `SRC-001 §5.5.1` gives this to the **manager**; that is superseded
by `SRC-003 OPEN-OPS-03` and a manager showtime endpoint is a defect (`P-ADM-18`).

**Preconditions.**
1. The film exists. **It need not be published** — a showtime may be scheduled against a draft, and
   the film's own gates decide whether a customer ever sees it (`P-ADM-05`).
2. The screen exists and is in service.
3. `ends_at` is strictly after `starts_at`.
4. The proposed `[starts_at, ends_at)` interval does not overlap any existing showtime on that screen
   (`P-ADM-08`).
5. `base_price_paise` passes its bounds (`P-ADM-10`).
6. If `format_id` is supplied, it names an **active** row of the `format` vocabulary
   (`P-ADM-23`). A withdrawn format cannot be attached to a new showtime; showtimes already
   carrying it keep it (`P-ADM-24`).
7. **If the film has a display window, `starts_at` falls inside it** —
   `display_from <= starts_at < display_until`, the same bounds and the same exclusivity the
   visibility gate uses (`P-BRW-01`). **A film whose window is still null is exempt**, which is
   precondition 1's draft case and is left exactly as it was.

**Why a showtime outside the window is refused rather than merely odd.** Every guest path to a date is
bounded by the film's display window: the listing's date strip and the single-movie date strip both
end at the last day of the window, and `next_date_with_showtimes` never searches past `display_until`
(`P-BRW-04`, `P-BRW-06`). **A showtime outside the window is therefore offered by no day button, no
next-date button and no date filter anywhere in the product** — it has a seat set, its sales are not
closed, and only a hand-typed URL reaches it. The alternative fix is to widen the strips, and that is
worse: it would put day buttons on screen for days on which the film has left its window, which is
precisely the button `P-BRW-04` refuses to draw. **The admin has said two different things about when
the film runs, and this is where they are reconciled — at the point of entry, where the person
choosing can see it**, on the same ground `P-ADM-04` states the exclusive end once at entry rather
than shifting it silently.

**This is not `OPEN-BRWVIS-01`.** That row asks whether a showtime may still be sold **after** its
film leaves the window — a boundary the clock crosses, possibly with a customer mid-checkout. This is
a showtime scheduled outside the window from the start: nothing moves, no policy has to be chosen, and
the showtime is unreachable from the instant it is created.

**A showtime in the past stays accepted, and this precondition does not touch that** — the seed needs
about a month of history (`FR-ADR-067`), and a past showtime inside the film's window passes here.

**Happy path.**
1. The admin opens `SCR-ADM-03` and chooses a film and a hall.
2. The admin enters a local start date and time in **Asia/Kolkata**. The form prefills the end as
   `start + runtime_minutes` of the chosen film — **exactly the runtime, with no turnaround added**,
   because no source states a turnaround figure (`P-ADM-08`).
3. The admin adjusts the end if they want turnaround, enters the base price, and submits.
4. The server converts both local times to instants using the cinema's stored zone (`FR-ADR-018`).
5. In one transaction the server takes `SELECT ... FOR UPDATE` on the `screen` row, re-runs the overlap
   check inside that lock, inserts the `showtime` row with `version = 1`, **writes the showtime's seat
   set — one row per in-service seat on that screen at this instant — and sets
   `seat_count_at_creation` to the number of rows it wrote** (`P-ADM-14`, which owns that rule;
   `FR-ADR-022`), and inserts an `audit_log` row with `action = "showtime.created"`.
6. The server returns 201 with the showtime and its `version`.

**The row lock on the screen is the mechanism, not a precaution.** Two admins submitting overlapping
showtimes on one screen in the same millisecond both pass a check-then-insert without it. No unique
constraint can express "these two time ranges overlap". **A PostgreSQL exclusion constraint on
`(screen_id, tstzrange(starts_at, ends_at))` is the stricter alternative and is recorded here rather
than left in a code comment**, because it would make the guarantee a database truth instead of an
application one. It is not adopted because it needs the `btree_gist` extension, and `GOTCHAS.md`
records that the local container's extension list and RDS's differ, so a migration that works locally
can fail on RDS. **That reasoning is unverified — no session has inspected the client's RDS parameter
group.**

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | Not an admin | 403 `FORBIDDEN` | "This page is for administrators. Your account cannot change films, showtimes, prices or halls." |
| 2 | No film with that id | 404 `NOT_FOUND` | "That film no longer exists. Choose a film from the list." |
| 3 | No screen with that id | 404 `NOT_FOUND` | "That hall no longer exists. Choose a hall from the list." |
| 4 | The screen is out of service | 409 `LAYOUT_FROZEN` | "This hall is out of service. Bring it back into service before creating showtimes on it." |
| 5 | The screen has no seats in service | 409 `LAYOUT_FROZEN` | "This hall has no seats in service. Add seats before creating a showtime on it." |
| 6 | `ends_at` is earlier than or equal to `starts_at` | 422 `VALIDATION_FAILED` | "The showtime must end after it starts." |
| 7 | The interval overlaps an existing showtime on that hall | 409 `SHOWTIME_OVERLAP` | see `P-ADM-08` |
| 8 | `base_price_paise` fails its bounds | 422 `VALIDATION_FAILED` | see `P-ADM-10` |
| 9 | Postgres unreachable | 503 `DEPENDENCY_UNAVAILABLE` | "The system cannot reach its database right now. Nothing was saved. Try again in a moment." |

**Server-side validation.**

| Field | Type | Bound | Provenance | On failure |
|---|---|---|---|---|
| `movie_id` | integer | must exist | **derived** (`FR-ADR-021`) | exception 2 |
| `screen_id` | integer | must exist and be in service | **ruled** (`FR-ADR-012`: retired screens are marked inactive, never deleted) | exceptions 3, 4 |
| `starts_at` | ISO-8601 local date and time, Asia/Kolkata | required. **Naive local only** — a `Z`, an offset or a zone name is refused and never coerced (`P-ADM-04`) | **ruled** (`FR-ADR-018`) | exception 6 |
| `ends_at` | ISO-8601 local date and time, Asia/Kolkata | required, strictly greater than `starts_at`. **Stored, never derived.** Naive local only, as above | **ruled** (`FR-ADR-018`) | exception 6 |
| `base_price_paise` | integer | see `P-ADM-10` | **ruled** (`FR-ADR-037`) | exception 8 |

**A showtime in the past is accepted.** No source forbids creating one, and the seed script needs about
a month of historical data (`SRC-003 OPEN-SEED-01`, `FR-ADR-067`). The sales cut-off (`FR-ADR-042`)
already prevents anyone buying a seat on it.

**`ends_at` is stored and never derived from the film's runtime** (`FR-ADR-018`). Deriving it would
mean an admin correcting a runtime typo silently changes the advertised end of shows that have already
sold tickets, and it would ignore trailers and turnaround entirely.

**Worked example — creating a showtime, in both zones.**

```
Film:            runtime_minutes = 148
Hall:            Screen 3, 150 seats in service
Admin enters:    starts_at = 2026-09-04 18:30  Asia/Kolkata
Form prefills:   ends_at   = 2026-09-04 20:58  Asia/Kolkata     (18:30 + 148 minutes, exactly)
Admin enters:    base_price_paise = 25000                        (Rs 250.00)

Stored:          starts_at = 2026-09-04T13:00:00Z
                 ends_at   = 2026-09-04T15:28:00Z                (Asia/Kolkata is UTC+05:30, fixed)
                 seat_count_at_creation = 150
                 version   = 1

Derived, never stored (FR-ADR-042):
                 sales_close_at = starts_at + 15 minutes
                                = 2026-09-04T13:15:00Z
                                = 2026-09-04 18:45 Asia/Kolkata
```

**The +15 offset is `PROVISIONAL`** (`SRC-003 OPEN-BOOK-03`, `FR-ADR-042`). The alternative reading is
15 minutes **before** the start, which would close the same showtime at 18:15 local — half an hour
earlier. It is a signed configuration value, so reversing it changes nothing written here.

---

### `P-ADM-08` · Two showtimes may not overlap on one hall · `RULED` on the rule, `OPEN` on turnaround
`[SRC: SRC-001 §2.2 · SRC-001 §7.1 · SRC-001 §5.2.1 · SRC-003 OPEN-SCOPE-01 · FR-ADR-018 · FR-ADR-024]`
`[BRD: R-ADM-03]`

**Behaviour.** A showtime whose `[starts_at, ends_at)` interval overlaps an existing showtime's
interval **on the same screen** is refused. The intervals are **half-open**: an end instant that
exactly equals the next start instant is **not** an overlap.

**Why it is refused, and this is a derivation and not a preference.** A hall is one physical room with
one set of seats. Two overlapping showtimes on it sell the same physical seat to two customers who
both arrive at the same clock time. `SRC-001 §2.2` calls eliminating double-booking non-negotiable and
`§7.1` calls a seat sold twice a failure of the whole system. **The unique constraint on
`(showtime_id, seat_id)` does not catch this** (`FR-ADR-024`), because the two showtime ids differ. It
is a different failure with the same outcome for the customer standing in the aisle.

**What is NOT ruled, and is not invented here.** **No frozen source, no client ruling and no
`APPROVED` record states a turnaround or changeover time between two showtimes in one hall.** A real
cinema needs one: the audience leaves, the room is cleaned, the next audience is seated. **This
specification requires no gap at all** and permits a showtime to start at the exact instant the
previous one ends. It does not invent 10, 15 or 20 minutes. **Raised as an Article X candidate** — see
Lane notes.

The consequence is stated plainly: the admin is the only thing between the schedule and a zero-minute
turnaround. The form's prefilled end is `start + runtime` **exactly**, so an admin who accepts every
prefill produces a schedule with no cleaning time and the system does not object.

**Who may do it.** Not an action — a constraint on `P-ADM-07` and `P-ADM-09`.

**Preconditions.** None beyond those of the calling spec.

**Happy path.** The check runs inside the same transaction and inside the same `SELECT ... FOR UPDATE`
on the screen row as the insert or update (`P-ADM-07` step 5). The predicate:

```
EXISTS (
  SELECT 1 FROM showtime
   WHERE screen_id = :screen_id
     AND id <> :this_showtime_id        -- this clause is omitted on create
     AND starts_at < :new_ends_at
     AND ends_at   > :new_starts_at
)
```

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | The interval overlaps exactly one existing showtime. `details` carries that showtime's id, film title, and local start and end | 409 `SHOWTIME_OVERLAP` | "Screen 3 already has a showtime from 6:30 pm to 8:58 pm on 4 Sep 2026. Two showtimes cannot run in one hall at the same time. Choose a different time or a different hall." |
| 2 | The interval overlaps more than one. `details` carries all of them | 409 `SHOWTIME_OVERLAP` | "Screen 3 already has 2 showtimes in that period. Two showtimes cannot run in one hall at the same time. Choose a different time or a different hall." |

The message names the hall, the existing times and the local date, because "that time is taken" leaves
the admin to find it themselves.

**`details` carries the conflicts under named keys, and the interface depends on them.** Every other
`details` payload in this product is keyed — `unavailable_seats`, `duplicate_labels`, `frozen_fields` —
and this one is keyed in the same shape:

```json
{"conflicts": [
  {"showtime_id": 41,
   "movie_title": "DEMO MOVIE 04",
   "starts_at": "2026-09-04T18:30:00",
   "ends_at":   "2026-09-04T20:58:00"}
]}
```

**It is always the array**, one entry per conflicting showtime and one entry long in the ordinary case,
so the interface reads one shape and never branches on whether exception 1 or exception 2 fired — the
count of entries is what distinguishes them. **`showtime_id` is what `SCR-ADM-03` outlines the
conflicting day-strip row with**, so this payload is load-bearing rather than diagnostic: without the
key the screen has a banner naming a time and no way to point at the row. The two instants are **naive
local** in Asia/Kolkata, matching what the request sent (`P-ADM-04`), and the interface renders them
through `S7.19`'s one function.

**Both times and the date render in `S7.19`'s forms, and this string was corrected to them.** It read
`from 18:30 to 20:58 on 4 September` — a 24-hour clock, which `S7.19` rule 3 forbids on any surface a
human reads, and a month spelled in full, which is not one of the five forms. It now reads
**`from 6:30 pm to 8:58 pm on 4 Sep 2026`**: the time form twice and the date form once. **The year is
kept**, because an error banner is not inside a set already scoped to one year. Exception 2 publishes
no instant at all and needed no change; the local start and end its `details` carries are wire values
in ISO-8601 and are rendered by the interface through the same one function `S7.19` rule 5 requires.
`SCR-ADM-03` publishes this same sentence and was corrected in the same edit.

**Server-side validation.** The predicate above is the validation. The interface may run the same check
to warn early; **the interface is never the enforcement point**, and its copy runs outside the lock and
can be stale.

**Worked example — the runtime and turnaround arithmetic, including the boundary.**

```
Existing on Screen 3:
  showtime 41   starts_at 2026-09-04 18:30   ends_at 2026-09-04 20:58   Asia/Kolkata
                (a 148-minute film; ends_at = starts_at + runtime, no turnaround added)

Attempt A:  starts_at 20:45, ends_at 22:40
            20:45 < 20:58  AND  22:40 > 18:30      ->  OVERLAP     ->  409 SHOWTIME_OVERLAP
            The new show would begin 13 minutes before the old audience is out of the room.

Attempt B:  starts_at 20:58, ends_at 22:53
            20:58 < 20:58 is FALSE                 ->  NO OVERLAP  ->  201 Created
            Zero minutes of turnaround. THE SYSTEM ACCEPTS THIS.
            Nothing in any frozen source says it should not.

Attempt C:  starts_at 21:15, ends_at 23:10
            21:15 < 20:58 is FALSE                 ->  NO OVERLAP  ->  201 Created
            17 minutes of turnaround, because the admin chose 17. Not because the system asked.
```

**Attempt B is the line to read twice.** It is accepted, and it is accepted because the figure that
would refuse it does not exist in any source this document may cite. Inventing one here is exactly the
failure `SRC-002 §8.1.1`'s seven minutes already produced on this project — a clause since
corrected by erratum `E-1`.

---

### `P-ADM-09` · Edit a showtime, and the list the admin edits it from · `RULED`
`[SRC: SRC-001 §5.5.1 · SRC-003 OPEN-OPS-03 · FR-ADR-018 · FR-ADR-035 · FR-ADR-042 · FR-ADR-019]`
`[BRD: R-ADM-03 · R-ADM-05]`

**Behaviour.** The admin changes a showtime's film, start, end or base price. Optimistic concurrency
applies (`FR-ADR-035`). The overlap check of `P-ADM-08` re-runs, excluding this showtime's own row.
**A showtime whose start is edited re-derives its sales cut-off automatically**, because the cut-off is
derived at evaluation time and never stored (`FR-ADR-018`, `FR-ADR-042`).

**Who may do it.** **admin only**, by the router dependency (`P-ADM-18`).

**Preconditions.** The showtime exists; the submitted `version` matches; the new interval does not
overlap another showtime on the same screen.

**Happy path.**
1. The admin edits the showtime on `SCR-ADM-03` and submits with `version`.
2. In one transaction the server locks the screen row, compares the version, re-runs the overlap check
   excluding this row, applies the changes, increments `version`, and inserts an `audit_log` row.
   **A base-price change writes `action = "showtime.base_price_changed"`; any other change writes
   `action = "showtime.updated"`; a request that changes both writes both rows.**
3. The server returns 200.

**`screen_id` cannot be changed.** Moving a showtime to another hall would move every existing booking
onto seats that may not exist in the new hall, and the oversell guard is keyed on
`(showtime_id, seat_id)` where those seats belong to the original screen (`FR-ADR-024`, `FR-ADR-016`).
The admin creates a new showtime on the other hall instead. **This is a build-session judgment under
Art III.9**, stricter than anything ruled, so it needs no signature (Art III.10).

**`seat_count_at_creation` is never recomputed on edit** (`FR-ADR-022`). It is the occupancy
denominator, and recomputing it would change last month's reported occupancy figure. **The showtime's
seat set is not rewritten on edit either**, for the same reason and by the same rule (`P-ADM-14`): the
set is written once, at creation, and an edit changes the showtime's film, times or price and never
which seats it has.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | Not an admin | 403 `FORBIDDEN` | "This page is for administrators. Your account cannot change films, showtimes, prices or halls." |
| 2 | No showtime with that id | 404 `NOT_FOUND` | "That showtime no longer exists at this address." |
| 3 | `screen_id` present and different from the stored value | 422 `VALIDATION_FAILED` | "A showtime cannot be moved to a different hall. Create the showtime on the other hall instead." |
| 4 | `version` does not match | 409 `VERSION_CONFLICT` | "This showtime was changed by someone else while you were editing. Reload to see the current details, then make your change again. Nothing you typed has been saved." |
| 5 | New interval overlaps | 409 `SHOWTIME_OVERLAP` | as `P-ADM-08` |
| 6 | `ends_at` not after `starts_at` | 422 `VALIDATION_FAILED` | "The showtime must end after it starts." |
| 7 | `base_price_paise` fails its bounds | 422 `VALIDATION_FAILED` | see `P-ADM-10` |

**Server-side validation.** As `P-ADM-07`, plus `version` as `P-ADM-02`, plus exception 3. **`ends_at`
must be strictly after `starts_at` in the merged row**, not in the submitted fields (see *Partial
updates* at the head of `S4`): this is a `PATCH` and both times are optional on it, so a request
carrying `starts_at` alone is checked against the **stored** `ends_at`, and a request carrying `ends_at`
alone against the **stored** `starts_at`. Either can fail with exception 6's existing wording, "The
showtime must end after it starts." A showtime moved to start after its own stored end would otherwise
be stored with a negative duration, and `P-ADM-08`'s overlap predicate — which compares
`starts_at < :new_ends_at AND ends_at > :new_starts_at` — silently matches nothing for an inverted
interval, so the hall's schedule would stop refusing overlaps against that row. **The overlap check
also runs against the merged interval**, for the same reason.

**Editing a showtime that already has bookings is permitted and changes nothing about them.** Seats are
held or sold against the showtime id, which does not change; the money on every booked seat is
snapshotted (`FR-ADR-039`); a receipt already sent carries the times it was sent with. **A showtime
moved earlier past its own cut-off does not eject a customer already holding seats** — the cut-off is
checked at hold acquisition and the hold is honoured (`FR-ADR-042`, `FR-ADR-035`).

**There is no way to withdraw or cancel a showtime.** See `P-ADM-21`.

#### The admin's showtime list, and what `include_past` means — **this row owns it**

**Ownership, declared** (`S1.2.1`). `EP-ADM-09` is the admin's showtime list and **`P-ADM-09` owns its
behaviour and the words it publishes**; the endpoint block owns its wire shape and `SCR-ADM-03` owns
its layout and its control. The parameter previously existed on the endpoint with no meaning stated
anywhere, and three readings — past by start, past by end, past by sales cut-off — return three
different result sets.

**Behaviour.** `include_past` is a boolean query parameter, **default `true`**.

- **`include_past=true`** — the default — **omits nothing**. Every showtime on that hall whose local
  start date is the requested date is returned.
- **`include_past=false`** omits every showtime whose **`starts_at` is at or before the request
  instant**, and returns the rest.

**"Past" means the advertised start instant, and nothing else.** Not the end instant, and **not the
sales cut-off**. The reason is that the cut-off is a **customer-facing** boundary derived at evaluation
time from `SALES_CUTOFF_MINUTES` (`FR-ADR-042`), so a list defined against it would change membership
when a configuration value changed, with nothing about the showtime itself having changed — an admin
would see a showtime appear or vanish from a list because somebody edited an environment variable.
**`starts_at` is a property of the showtime**, stored on its row, and it moves only when an admin edits
it and the audit log records that they did.

**The boundary is inclusive: at or before now.** A showtime starting at exactly the request instant is
past. An exclusive boundary would put a showtime into and out of the list depending on how many
milliseconds the request took to reach the handler, which is a difference nobody can reproduce.

**The default is `true` on purpose.** **Nothing is hidden from an admin who did not ask**, and a
showtime that has already started is still **editable** wherever this row's own rules allow it — hiding
it from a list is a convenience, never a permission. An admin who needs to correct the price on a show
that started ten minutes ago can still find it, because the list they arrive at shows it.

**Who may do it.** **admin only**, by the router dependency (`P-ADM-18`). A manager may not read this
list; the manager's read surface is the dashboard, which is `E7`'s and is a different query.

**Preconditions.** The screen exists. The date is a valid local date in **Asia/Kolkata**, resolved
through the cinema row's zone (`P-ADM-26`), never through the container's clock or locale.

**Happy path.**
1. The admin opens `SCR-ADM-03` and chooses a hall and a date.
2. The server resolves the local date to its two bounding instants in the cinema's zone.
3. The server selects the showtimes on that screen whose `starts_at` falls inside those bounds.
4. **If `include_past` is `false`, the filter is applied here**, against `starts_at <= now`.
5. The remaining rows are ordered by `starts_at` ascending and returned whole.

**Filter first, then anything that limits the result.** The list is ordered by `starts_at`, so
`include_past=false` removes a **prefix** of that ordering. **Pagination — if it is ever added — must
be applied after the filter and never before**: paging first and filtering the page afterwards hands
back short pages and a last page that is empty, and the reader cannot tell that from the end of the
list. **This endpoint is not paginated today**: one hall's one local day is returned whole, because the
day strip and its gap readouts need every row to compute the gaps between them, and a half-listed day
is how an admin creates an overlap they could not see (`SCR-ADM-03`). The rule is stated because the
first person to add a page parameter will otherwise add it in the wrong order.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | Not an admin | 403 `FORBIDDEN` | "This page is for administrators. Your account cannot change films, showtimes, prices or halls." |
| 2 | No screen with that id | 404 `NOT_FOUND` | "That hall no longer exists at this address." |
| 3 | `screen_id` absent or not an integer, so no hall is named at all | 422 `VALIDATION_FAILED` | "That hall no longer exists. Choose a hall from the list." — the sentence `P-ADM-07` exception 3 already publishes. The remedy is identical, and a second wording for one remedy is a defect |
| 4 | `date` absent or malformed | 422 `VALIDATION_FAILED` | "That date is not valid." |
| 5 | `include_past` present and not a boolean | 422 `VALIDATION_FAILED` | "That filter value is not valid." |
| 6 | Postgres unreachable | 503 `DEPENDENCY_UNAVAILABLE` | `SCR-ADM-03`'s **Error** state — the banner of `COMPONENTS.md §6`, which owns the read-failure wording. **This row publishes no sentence of its own for it**: the only `DEPENDENCY_UNAVAILABLE` sentence this section publishes says "Nothing was saved", which is false on a read, and a second variant of an existing sentence is a defect rather than a refinement |

**Server-side validation.**

| Field | Type | Bound | Provenance | On failure |
|---|---|---|---|---|
| `screen_id` | integer | required, positive, must exist | **derived** (`FR-ADR-012`) | exceptions 2, 3 |
| `date` | ISO-8601 date | required, resolved in the cinema's zone | **ruled** (`FR-ADR-018`, `P-ADM-26`) | exception 4 |
| `include_past` | boolean | optional, **default `true`**. `false` omits `starts_at <= now` | **derived** — the parameter existed with no meaning; the reading is chosen here and its reason is stated above | exception 5 |
| `now` | instant | the **request** instant, taken once per request from the injected clock | **ruled** — a test that reads the wall clock is a defect, and a list that re-reads the clock per row can drop a row from the middle of its own ordering | — |

**Worked example — the boundary, and the showtime that is past and still selling.**

```
Request instant:   2026-09-04T13:05:00Z   =   18:35 Asia/Kolkata
Query:             screen_id = 3,  date = 2026-09-04

  id    starts_at (local)   starts_at (UTC)         at or before now?    include_past=false
  601   10:00               2026-09-04T04:30:00Z    yes                  omitted
  602   13:30               2026-09-04T08:00:00Z    yes                  omitted
  603   18:30               2026-09-04T13:00:00Z    yes  (13:00 <= 13:05) omitted
  604   21:30               2026-09-04T16:00:00Z    no                   returned

  include_past=true  (the default)  ->  601, 602, 603, 604   - four rows, in that order
  include_past=false                ->  604                  - one row, a prefix removed

  Ordering is by starts_at, so the omitted rows are always a prefix. Any pagination applied
  BEFORE the filter would page {601,602,603,604} and then drop three from page 1, handing
  back a page of one where the page size said four.
```

**Showtime 603 is the line to read twice.** It started five minutes before the request and
`include_past=false` hides it — **while its sales are still open**, until 18:45 local, because the
cut-off is `starts_at + 15 minutes` (`FR-ADR-042`; **the +15 direction is `PROVISIONAL` under
`SRC-003 OPEN-BOOK-03`** and the alternative reading closes sales at 18:15 instead). So a customer can
be buying a seat on a showtime the admin's filtered list is not showing them. **That is exactly why the
default is `true`**, and why the screen labels the control as hiding rather than as filtering.

---

### `P-ADM-10` · Set the base price per showtime · `RULED`, with a `PROVISIONAL` part · reserved: money
`[SRC: SRC-003 OPEN-PRICE-01 · SRC-003 OPEN-LOCALE-01 · SRC-001 §5.5.1 · SRC-001 §5.2.4 · FR-ADR-036 · FR-ADR-037 · FR-ADR-038]`
`[BRD: R-PRC-02 · R-ADM-03]`

**Behaviour.** Every showtime carries `base_price_paise`, a non-null integer number of paise set by the
admin. Currency is **INR**, the minor-unit ratio is **100**, and the ratio is a named configuration
value and never a literal (`SRC-003 OPEN-LOCALE-01`, `FR-ADR-036`).

> ## ⚠ `PROVISIONAL` — one message from the client reverses this
> That the base price is set **per showtime** rather than once globally is a **build-session reading**
> of the client's words *"the admin will set the ticket price"*, which do not say at which level
> (`SRC-003 OPEN-PRICE-01`, `FR-ADR-037`). Per showtime was chosen because a single global price would
> make an evening blockbuster cost the same as a weekday matinee. **The rejected reading is one global
> price.** Reversing it moves the column to a configuration value and backfills existing showtimes —
> contained, and recorded as such. **Nothing downstream may treat per-showtime pricing as settled
> fact.**

**Who may do it.** **admin only.** `SRC-001 §5.5.1` gives pricing to the manager; superseded by
`SRC-003 OPEN-OPS-03`.

**Preconditions.** As `P-ADM-07` or `P-ADM-09`, whichever is setting it.

**Happy path.** The value is submitted as an integer number of paise. The interface accepts rupees and
paise from the admin and converts at the boundary; **the API accepts paise only**, and a decimal in the
request body is rejected rather than rounded (`FR-ADR-036`).

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | `base_price_paise` missing | 422 `VALIDATION_FAILED` | "Enter a base price for this showtime." |
| 2 | Not a whole number | 422 `VALIDATION_FAILED` | "Enter the base price in whole paise. A price cannot have a fraction of a paisa." |
| 3 | Zero or negative | 422 `VALIDATION_FAILED` | "The base price must be at least 1 paisa." |
| 4 | Above the arithmetic ceiling below | 422 `VALIDATION_FAILED` | "That base price is too large for this system to hold. Enter a smaller amount." |

**Server-side validation.**

| Field | Type | Bound | Provenance | On failure |
|---|---|---|---|---|
| `base_price_paise` | integer, `bigint` in storage | `>= 1` | **derived** — `SRC-001 §5.3.1` collects payment before a booking is confirmed, and a payment of zero is not a payment. A free show is not a case any source contemplates | exception 3 |
| `base_price_paise` | integer | `base_price_paise * (10000 + highest stored uplift_basis_points) + 5000 <= 2^63 - 1` | **technical** — from `FR-ADR-017`'s `bigint` columns and `FR-ADR-038`'s formula. **An arithmetic ceiling, not a business one** | exception 4 |
| a decimal in the request body | — | rejected, never rounded | **ruled** (`FR-ADR-036`: `Decimal` at the boundary, `int` in persistence) | exception 2 |

**The upper bound is technical and is marked as one.** The business question — what is the highest
ticket price this cinema would ever charge — is unanswered by every source, and no plausible figure is
invented for it. Raised as an Article X candidate in the Lane notes.

**The ceiling is on `EP-ADM-10` and `EP-ADM-11` as well as here, and that is not a duplication.**
`api/contract.json` is generated from those two blocks, so a bound stated only on this row is a bound
absent from the artefact the client and the server are both built from — and `S1.2` ranks the endpoint
block above the P-row on a field bound, which means a block saying only *"1 or more"* does not merely
omit the ceiling, it **outranks it**. Both blocks now carry it. **A guard against a 64-bit overflow in
the money formula is the last bound that may live in prose alone.**

**Worked through, so the figure the blocks state is derivable and not asserted.** The formula is
`FR-ADR-038`'s, run in `bigint`:

```
seat_price_paise = (base_price_paise * (10000 + uplift_basis_points) + 5000) // 10000

The largest intermediate is the numerator, before the division. It must fit int64:

  base_price_paise * (10000 + u) + 5000  <=  2^63 - 1  =  9223372036854775807

Solved for the base price, at u = 3333 - the highest uplift the seed stores (P-XCT-30):

  base_price_paise  <=  (9223372036854775807 - 5000) // 13333
                    =   9223372036854770807 // 13333
                    =   691770197019033 paise        =  Rs 6,917,701,970,190.33

Check, at exactly that value:
  691770197019033 * 13333 + 5000  =  9223372036854771989   <=  9223372036854775807   PASSES
  691770197019034 * 13333 + 5000  =  9223372036854785322   >   9223372036854775807   REFUSED
```

**The bound moves when the highest stored uplift moves, and that is the point of writing it against
`highest stored uplift_basis_points` rather than against a constant.** `P-ADM-11` carries the mirror
bound — the same inequality solved for the uplift, against the highest stored base price — so an
admin cannot walk past the ceiling by raising the two fields one at a time. **Neither figure is a
business limit**, and nothing downstream may treat either as one: at Rs 6.9 trillion a ticket, the
number that will actually catch a mistyped price is one no source has ruled.

**The worked example for the price itself is in `P-ADM-11`**, where the base price meets the uplifts.

---

### `P-ADM-11` · Set a seat category's percentage uplift, uniform across every hall and every show · `RULED` · reserved: money
`[SRC: SRC-003 OPEN-PRICE-01 · SRC-003 OPEN-SEAT-01 · SRC-003 OPEN-PRICE-02 · SRC-001 §5.2.3 · FR-ADR-016 · FR-ADR-037 · FR-ADR-038 · FR-ADR-019]`
`[BRD: R-PRC-02]`

**Behaviour.** Each seat category carries `uplift_basis_points`, an **integer number of basis points**
where one basis point is 0.01%. 12.5% is `1250`. The uplift is **set once by the admin and applied
uniformly across every hall and every show** — that uniformity is what the client's words *"across all
halls or any movie show"* rule out: **there is no per-hall and no per-film category pricing**
(`SRC-003 OPEN-PRICE-01`, `FR-ADR-037`).

**Basis points and not a decimal percentage**, because a decimal reintroduces a non-integer type into
the one calculation this project cares most about getting exactly right (`FR-ADR-037`).

**Standard is `0` basis points and is not a special case in code.** It is a row whose uplift happens to
be zero, and the same formula runs for it.

**⚠ Seat category names are `ASSUMED`, never a constraint.** Standard, Premium and Recliner are the
build session's choice; the client said "you pick" (`SRC-003 OPEN-SEAT-01`, `FR-ADR-016`). They are
rows in a `seat_category` table and not a PostgreSQL enum, so a fourth category costs an insert and not
a migration. **Nothing in this specification may treat the three names as ruled.**

**Who may change an uplift.** **admin only** (`SRC-003 OPEN-OPS-03`). **This is the most dangerous
single write in the system**: one edit changes the price of every future show in every hall at once
(`FR-ADR-037`). It carries an audit row with before and after (`FR-ADR-019`) and optimistic concurrency
(`FR-ADR-035`), and the interface requires a confirmation stating how many showtimes it will affect.

**Preconditions.** The category exists; the submitted `version` matches.

**Happy path.**
1. The admin opens `SCR-ADM-04`, which loads the categories from `EP-ADM-12`. **That response carries
   `affected_future_showtimes`**, computed by the rule below at the instant of the read.
2. The admin edits an uplift and submits. The interface shows a confirmation naming the category, the
   old and the new percentage, and **that number** — not one it derived itself and not one it counted
   from a list it fetched for another purpose.
3. In one transaction the server compares the version, writes `uplift_basis_points`, increments
   `version`, and inserts an `audit_log` row with `action = "seat_category.uplift_changed"`,
   `before = {"uplift_basis_points": 1250}`, `after = {"uplift_basis_points": 1500}`.
4. The server returns 200, carrying `affected_future_showtimes` recomputed by the same rule at the
   instant of the write.

**A change takes effect for holds acquired after it and for nothing else** (`FR-ADR-035`,
`FR-ADR-039`). See `P-ADM-12`.

---

#### `affected_future_showtimes` — the blast-radius count, defined once and computed one way

**This row owns the definition.** `EP-ADM-12` returns it **before** the write, `EP-ADM-14` returns it
**after**, `SCR-ADM-04` renders it in the impact line and in the confirmation, and **all four use this
one rule**. A safeguard whose number is computed differently in the place that warns and the place
that reports is a safeguard nobody can check.

**The rule.**

```
affected_future_showtimes
  = COUNT(showtime s WHERE s.starts_at + SALES_CUTOFF_MINUTES > evaluated_at)
```

**Every term, stated:**

| Term | What it is |
|---|---|
| `s.starts_at` | the showtime's advertised start, stored as a `timestamptz` in UTC (`FR-ADR-018`) |
| `SALES_CUTOFF_MINUTES` | the signed sales-cut-off offset. `+15` means sales close **fifteen minutes after** the advertised start. The value and its sign are owned by the seat-hold specification and are **not** redefined here |
| `evaluated_at` | the instant the count is taken, from the **injected clock**, in UTC. Never the container's local time and never a wall-clock read (`FR-ADR-018`, Art IX.5) |
| the comparison | **instant against instant. No local date and no zone conversion takes part in it.** Both sides are already UTC instants, so the cinema's zone converts nothing here and cannot get it wrong |
| the count | **every hall, every film, every seat category.** The uplift is uniform (`FR-ADR-037`), so the count is not narrowed by category and is the same number whichever category is being edited |

**"Future" means "can still take a new hold", not "has not started yet", and the difference is not
cosmetic.** Sales close at `starts_at + SALES_CUTOFF_MINUTES`, which under the current
`PROVISIONAL` direction is **after** the advertised start (`FR-ADR-042`). A showtime that began ten
minutes ago is therefore **still selling**, and a customer taking a hold on it in the next five
minutes is quoted the **new** uplift. Counting only `starts_at > evaluated_at` would leave every such
showtime out — **the number would be smaller than the truth**, on the confirmation that exists to
state the truth. It is corrected in the direction that shows more danger, not less, which is a
stricter adoption and needs no signature (Art III.10).

**⚠ The direction of `SALES_CUTOFF_MINUTES` is `PROVISIONAL`** (`SRC-003 OPEN-BOOK-03`,
`FR-ADR-042`). If the client reverses it to fifteen minutes *before* the start, this count **falls**,
because showtimes inside their last quarter-hour stop being able to take a hold. The rule does not
change; the number it produces does. The worked example below gives both figures so the change is
visible rather than discovered.

**Halls out of service are counted.** `P-ADM-16` stops a withdrawn hall accepting **new** showtimes;
the showtimes already on it are unchanged and still sell. Excluding them would understate the count
for exactly the halls an admin has stopped thinking about.

**Nothing about a seat is consulted.** The count does not join through `seat` to find showtimes that
have at least one seat in the edited category. That narrower figure would be smaller, would need a
join across every hall's seat rows on a request that runs on a screen load, and would be **smaller
than the truth** the moment a seat is moved into the category — which is the wrong direction for a
warning. The broader count is one indexed scan over `showtime` and it is never an understatement.

**The two evaluations can legitimately differ, and that is not a defect and produces no warning.**
`EP-ADM-12`'s count is taken when the screen loads; `EP-ADM-14`'s is taken inside the write
transaction. A showtime whose selling window closes between the two makes the second smaller by one.
**No comparison is made between them, no confirmation is invalidated by the difference, and the admin
is not asked to confirm twice.** The version check (`P-ADM-12`) guards the thing that must not move —
the category row — and a count moving by one is not a reason to refuse a price change. `EP-ADM-12`
returns `evaluated_at_utc` alongside the count so that the two figures can be told apart when they are
compared afterwards.

**Worked example — the count, at one named instant, with the cut-off doing its work.**

Inputs. The injected clock reads `2026-08-14T09:00:00Z`, which is `2026-08-14 14:30` Asia/Kolkata.
`SALES_CUTOFF_MINUTES = +15`. Four showtimes exist in the whole system:

| Showtime | `starts_at` (local) | `starts_at` (UTC) | `starts_at + 15 min` | Counted? |
|---|---|---|---|---|
| A | 2026-08-14 13:00 | `2026-08-14T07:30:00Z` | `07:45:00Z` | **no** — `07:45 > 09:00` is false. Sales closed 75 minutes ago |
| B | 2026-08-14 14:20 | `2026-08-14T08:50:00Z` | `09:05:00Z` | **yes** — `09:05 > 09:00`. It started ten minutes ago and is still selling |
| C | 2026-08-14 14:30 | `2026-08-14T09:00:00Z` | `09:15:00Z` | **yes** — it starts at this exact instant |
| D | 2026-08-16 19:30 | `2026-08-16T14:00:00Z` | `14:15:00Z` on the 16th | **yes** |

```
affected_future_showtimes = 3        <- this is the rule

Under the rejected narrower reading, starts_at > evaluated_at:
  A no (07:30 > 09:00 false)
  B no (08:50 > 09:00 false)   <- still selling, and wrongly left out
  C no (09:00 > 09:00 false)   <- starting now, and wrongly left out
  D yes
                              = 1    <- understates the blast radius by TWO
```

**Three noes and one yes is one.** This sum read `2` in an earlier revision and the error was
arithmetic rather than conceptual — **the reversed-direction block below sums the identical shape
correctly** — but it understated the disagreement this definition exists to remove, and `S1.5`
transcribes worked examples directly into tests, so a wrong figure here becomes a test asserting the
wrong number. **The specified rule and its answer of 3 were never in doubt; only the rejected
reading's total was wrong.**

**B is the whole reason the rule is written against the cut-off and not against the start.** A
customer can take a hold on B for the next five minutes and will be charged the new uplift. A
confirmation saying "1 future showtime" would be describing a change that in fact reaches three.

**And the same instant with the direction reversed**, `SALES_CUTOFF_MINUTES = -15`, so sales close
fifteen minutes *before* the start and the threshold becomes `starts_at > 09:15:00Z`:

```
A no · B no · C no (09:00 > 09:15 false) · D yes
affected_future_showtimes = 1
```

**Three, one and one from one set of four rows.** That is the size of the disagreement this
definition exists to remove — and the two ones arrive by different routes, which is worth seeing: the
rejected reading loses B and C because it tests the start instead of the cut-off, while the reversed
direction loses them because the cut-off itself has moved ahead of them. **Same total, different
reason**, and only one of the two is a defect.

---

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | Not an admin | 403 `FORBIDDEN` | "This page is for administrators. Your account cannot change films, showtimes, prices or halls." |
| 2 | No category with that id | 404 `NOT_FOUND` | "That seat category no longer exists at this address." |
| 3 | Not a whole number | 422 `VALIDATION_FAILED` | "Enter the uplift in whole basis points. 100 basis points is 1 percent." |
| 4 | Negative | 422 `VALIDATION_FAILED` | "The uplift cannot be negative. This system has no discounts." |
| 5 | Above the arithmetic ceiling below | 422 `VALIDATION_FAILED` | "That uplift is too large for this system to hold. Enter a smaller value." |
| 6 | `name` empty, too long, or already used | 422 `VALIDATION_FAILED` | "Enter a category name of 1 to 40 characters." / "A seat category with that name already exists." |
| 7 | `version` does not match | 409 `VERSION_CONFLICT` | "This seat category was changed by someone else while you were editing. Reload to see the current values, then make your change again. Nothing you typed has been saved." |

**Server-side validation.**

| Field | Type | Bound | Provenance | On failure |
|---|---|---|---|---|
| `uplift_basis_points` | integer | `>= 0` | **derived** — a negative uplift is a discount, and `SRC-003 OPEN-PRICE-02` rules out discount codes, concession pricing and every other reduction (`FR-ADR-040`) | exception 4 |
| `uplift_basis_points` | integer | `(highest stored base_price_paise) * (10000 + uplift_basis_points) + 5000 <= 2^63 - 1` | **technical**, from `FR-ADR-038`'s formula and `bigint` storage | exception 5 |
| `name` | string | 1..40 characters after trimming; **unique on `lower(trim(name))`** | **technical** length; the normalisation is **derived** (`P-ADM-23`) — `Premium` and `premium` would draw two legend rows on every seat map for one category | exception 6 |
| `version` | integer | must equal the stored value | **ruled** (`FR-ADR-035`) | exception 7 |

**No business upper bound on the uplift exists in any source** and none is invented. The ceiling above
is arithmetic. Raised as an Article X candidate in the Lane notes.

**Creating a fourth category is permitted.** Seats are assigned to it in `P-ADM-13`. **Deleting a
category is not**, because seats and booked seats reference it (`FR-ADR-012`, `FR-ADR-039`); a category
that is no longer used simply has no seats pointing at it.

**Worked example — one base price, three uplifts, three seat prices.**

The rule (`FR-ADR-038`), integer arithmetic throughout, no float and no `Decimal` in the expression:

```
seat_price_paise = (base_price_paise * (10000 + uplift_basis_points) + 5000) // 10000
```

`10000` is the basis-point denominator. Adding `5000` — half the denominator — before an integer floor
division is integer **half-up**. Both are named constants, never literals scattered through the code.

Inputs. Showtime 41 on Screen 3, `base_price_paise = 25000` (Rs 250.00). Three categories, with
uplifts as an admin might set them:

| Category (name `ASSUMED`) | `uplift_basis_points` | Percentage |
|---|---|---|
| Standard | `0` | 0% |
| Premium | `1250` | 12.5% |
| Recliner | `3333` | 33.33% |

```
Standard:  (25000 * (10000 +    0) + 5000) // 10000
         = (250000000 + 5000) // 10000
         = 250005000 // 10000
         = 25000                                        ->  Rs 250.00

Premium:   (25000 * (10000 + 1250) + 5000) // 10000
         = (281250000 + 5000) // 10000
         = 281255000 // 10000
         = 28125                                        ->  Rs 281.25

Recliner:  (25000 * (10000 + 3333) + 5000) // 10000
         = (333325000 + 5000) // 10000
         = 333330000 // 10000
         = 33333                                        ->  Rs 333.33
```

**The Recliner line is the case the rounding rule exists for.** The exact value is
`25000 x 1.3333 = 33332.5` paise — **exactly half**. Half-up gives `33333`. Half-even would give
`33332`, because 33332 is the even neighbour. One paisa, and it is the single case where the two rules
visibly disagree.

**Rounding is per seat and the booking total is never rounded** (`FR-ADR-038`). Three Recliner seats:

```
per seat, then sum:      33333 * 3     = 99999 paise   ->  Rs 999.99    <- this is the rule
round the total instead: 33332.5 * 3   = 99997.5
                         half-up       = 99998 paise   ->  Rs 999.98
```

One paisa apart, and the first is the figure the customer was shown three times on the seat map
(`SRC-001 §5.2.4`).

---

### `P-ADM-12` · An admin price edit cannot change what a customer already holding seats is charged · `RULED`
`[SRC: SRC-001 §5.2.4 · SRC-001 §7.6 · SRC-003 OPEN-PRICE-01 · SRC-003 OPEN-OPS-03 · FR-ADR-035 · FR-ADR-039 · FR-ADR-027]`
`[BRD: R-PRC-02 · R-ADM-05]`

**Behaviour.** **The price a customer pays is the price that was current when their hold was granted.**
At hold acquisition the API computes the per-seat prices and stores them **with the hold, in Redis,
under the hold token**. At confirmation those stored prices are used and **nothing is recomputed**;
confirmation copies them onto `booking_seat` (`FR-ADR-039`). An admin editing `base_price_paise`
(`P-ADM-10`) or `uplift_basis_points` (`P-ADM-11`) therefore **cannot** change what a customer already
holding seats is charged.

**Admin price edits are never blocked.** Blocking them while any hold exists would let one customer
with an open tab freeze pricing on a busy showtime for three minutes at a time, indefinitely
(`FR-ADR-035`). The edit succeeds; it applies to holds acquired after it.

**The protection window is exactly the hold**: 180 seconds from configuration
`SEAT_HOLD_TTL_SECONDS`, no extension and no renewal (`SRC-003 OPEN-HOLD-01`, `FR-ADR-027`). The price
expires with the hold, which is the correct lifetime for it, and it needs no separate expiry and no
cleanup job.

**Who may do it.** The edit is **admin only** (`P-ADM-18`). The protection is not an action — it is a
property of every price read.

**Preconditions.** None. The rule holds unconditionally.

**Happy path — the ordering that produces the guarantee.**
1. `T0` — a customer holds seats C12 and C13 on showtime 41. The API computes both seat prices from the
   showtime's current `base_price_paise` and each seat's category uplift, and writes them into the
   Redis hold under the hold token, alongside the seat ids and the absolute `expires_at`.
2. `T0 + 40s` — the admin raises the showtime's base price. The write succeeds, `version` increments,
   an audit row records the before and the after.
3. `T0 + 95s` — the customer confirms. The confirm transaction reads the **held** prices, not the
   showtime row's current price, and writes them onto `booking_seat` together with
   `base_price_paise_applied` and `uplift_basis_points_applied` (`FR-ADR-039`).
4. The customer is charged what they were shown. The next customer to take a hold on that showtime is
   charged the new price.

**The confirm transaction takes `SELECT ... FOR UPDATE` on the showtime row.** That lock is **not**
there to prevent the admin's edit. It is there so the cut-off check and any showtime read inside the
transaction see one consistent version of the row (`FR-ADR-035`, `FR-ADR-029`).

**Optimistic concurrency and the `VERSION_CONFLICT` path.** Two admins editing the same row is a
separate race and is handled separately. Every mutable admin-owned entity carries an integer
`version`: **`movie`, `showtime`, `screen` and `seat_category`** (`FR-ADR-035`).

**`cinema` is a fifth, and it is a stricter extension rather than a correction of the four.**
`FR-ADR-035` named the four mutable entities that existed when it was written; `P-ADM-25` gives the
`cinema` row an edit surface it did not have, and an editable row with no `version` is a row with no
concurrency protection and **no runtime signal that it lacks one**. Extending the mechanism to it is
stricter and needs no signature (Art III.10). **The record is not re-opened** — the four it names are
still four, and this is a fifth entity brought under the same rule, recorded here so it reads as a
deliberate extension and not as a miscount of `FR-ADR-035`.

- Every read that feeds an admin form returns `version`.
- Every write **must** echo it. A write with no `version` is `422 VALIDATION_FAILED`, not a
  last-write-wins default.
- The comparison happens **inside the transaction**, after re-reading the row.
- On a mismatch the whole request is refused with **409 `VERSION_CONFLICT`** and **nothing is written,
  including no audit row** — there was no change to audit.
- On success `version` increments by exactly 1.

**A write that changes nothing is a no-op, and this is the general rule for every versioned entity.**
**A `PATCH` in which every submitted field already equals the stored value returns `200`, writes
nothing, does not increment `version`, and writes no audit row.** `P-ADM-24` already answered this for
a lookup row and gave the reason — *"an audit row whose `before` and `after` are identical is noise in
the one table an operator reads to find real changes"* — and the answer generalises: it now governs
`movie`, `showtime`, `screen`, `seat_category` and `cinema` as well.

**The ordering, because it decides the answer. It is: `version` -> field validation -> no-op -> write.**

1. **`version` first**, inside the transaction, against the re-read row. A stale `version` is
   `409 VERSION_CONFLICT` **whether or not the submitted fields would have changed anything** — the row
   has moved under the admin, and telling them otherwise because their particular fields happened to
   match would hide the move.
2. **Field validation second, and it runs even when nothing would change.** A submitted value that
   fails its bound is `422 VALIDATION_FAILED`, **not** a `200` no-op.
3. **The no-op check third**, on the fields that survived validation.
4. **The write last**, if anything is left to write.

**Step 2 is the one an implementer reverses, and the case is ordinary rather than contrived.** An admin
form round-trips the whole row, so it resubmits a `format_id` that has since been withdrawn
(`P-ADM-24`), or a `seat_category_id`, or a `language_id` — a value that equals what is stored and is
no longer acceptable. Under the reversed order that request answers `200` and the admin is told their
form is fine; the next time they change any other field on it, the same value is refused and nothing
about the row has changed in between. **The no-op rule exists to keep the change log clean, not to
accept values the system would otherwise refuse**, and a rule that admits a value merely because it is
already stored makes the stored value the reason it is acceptable — which is exactly backwards.

**The observable consequence that made this worth deciding, rather than an internal nicety.** Under the
other reading — a no-op still increments `version` — an admin who opens a form, changes nothing and
presses Save invalidates **every other open form on that row**. A second admin then gets
`409 VERSION_CONFLICT` and the sentence "This … was changed by someone else while you were editing",
which is **false**: nothing was changed. A concurrency control that fires on a change that did not
happen teaches its users to ignore it, which is the one thing it cannot survive.

**`seat` is deliberately outside this rule, and the omission is not an oversight.** The enumeration
above is `movie`, `showtime`, `screen`, `seat_category` and `cinema` — **the versioned entities**, and
this rule is a rule about them: it exists because a `version` bumped by a non-change invalidates every
other open form. **A seat carries no `version`** (`FR-ADR-035` names four, `P-ADM-25` adds the fifth,
and `EP-ADM-20` accepts no `version` field at all), so there is nothing for a no-op to bump and nothing
for it to protect. **Setting `is_active` to the value it already holds therefore stays `409`**, with
`P-ADM-15` exception 3's published sentence — "Seat C12 is already out of service." — because the seat
toggle is **an assertion about state, not an edit of a field**: a repeat almost always means the admin
clicked the wrong row or is looking at a stale grid, and telling them which is the useful answer, where
a silent `200` would let them believe they had just changed something. **The exemption is scoped to
`is_active` alone.** A seat `PATCH` resubmitting an unchanged `grid_row` is an ordinary field edit that
changes nothing, writes no audit row and answers `200`, exactly as the general rule says.

**A no-op still returns the row and its unchanged `version`**, so a form that submitted it stays usable
and does not need reloading. The response is not distinguishable from a successful change by its shape,
and nothing needs it to be: **the audit log is where "did anything change" is answered**, and it
answers by having no row.

**Partly-no-op requests are decided field by field.** A request submitting two fields where one differs
writes the change, increments `version` once, and writes one audit row for the action that actually
changed (`P-ADM-19`). The unchanged field contributes nothing — not a row, not a `before`, not an
`after`.

**Last-write-wins is refused.** A silently discarded edit to a price is a money error nobody sees
(`FR-ADR-035`).

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | An admin submits a stale `version` on a movie | 409 `VERSION_CONFLICT` | "This film was changed by someone else while you were editing. Reload to see the current details, then make your change again. Nothing you typed has been saved." |
| 2 | Stale `version` on a showtime | 409 `VERSION_CONFLICT` | "This showtime was changed by someone else while you were editing. Reload to see the current details, then make your change again. Nothing you typed has been saved." |
| 3 | Stale `version` on a seat category | 409 `VERSION_CONFLICT` | "This seat category was changed by someone else while you were editing. Reload to see the current values, then make your change again. Nothing you typed has been saved." |
| 4 | Stale `version` on a screen | 409 `VERSION_CONFLICT` | "This hall was changed by someone else while you were editing. Reload to see the current details, then make your change again. Nothing you typed has been saved." |
| 5 | `version` absent from the request body | 422 `VALIDATION_FAILED` | "This form is out of date. Reload the page and make the change again." |
| 6 | Stale `version` on a cinema | 409 `VERSION_CONFLICT` | "This venue was changed by someone else while you were editing. Reload to see the current details, then make your change again. Nothing you typed has been saved." |
| 7 | Stale `version` on a **poster upload** (`EP-ADM-05`), which writes the `movie` row | 409 `VERSION_CONFLICT` | "This film was changed by someone else while you were editing. Reload to see the current details, then make your change again. Nothing you typed has been saved." |

**Row 7 is the same sentence as row 1 on purpose.** The poster upload writes the `movie` row and
increments its `version`, so it is a film write, and a customer-facing — here, admin-facing — sentence
that differs only because the field happened to arrive in a multipart body would be a second wording
for one situation. **A new variant of an existing sentence is a defect, not a refinement.**

**Where `version` sits on the poster upload, and when it is checked.** `EP-ADM-05` is
`multipart/form-data`, so `version` is a **second form part** alongside `file` — not a header and not a
query parameter. The check ordering is observable and a naive implementation gets it wrong, so it is
stated:

```
1  Content-Length            -> 413 PAYLOAD_TOO_LARGE      (stays first: it is the guard that
                                                            keeps the body from being read at all)
2  version                   -> 409 VERSION_CONFLICT       (or 422 if the part is absent)
3  content type, magic bytes -> 415 UNSUPPORTED_MEDIA_TYPE
4  decode and dimensions     -> 415 / 422
5  stream the bytes to S3
6  the movie row and its audit line, in one transaction
```

**`version` is checked before the first byte is streamed to S3**, so a stale upload costs no object and
leaves no orphan in the bucket — which matters because `FR-ADR-012` means nothing is ever deleted from
it, so an object written by a doomed request would stay there permanently. `Content-Length` stays ahead
of it because that check exists to stop the body being read at all (`FR-ADR-061`), and a 2 MB body read
into memory to discover a version conflict is the failure that check was put there to prevent.

**Server-side validation.** `version`: integer, required on every admin write to `movie`, `showtime`,
`screen` and `seat_category`, must equal the stored value. **Provenance: ruled** (`FR-ADR-035`). The
same field is required on every admin write to `cinema`; **provenance: derived**, from the paragraph
above. **The poster upload is a `movie` write and carries no exemption**: it takes `version` as a form
part, and a request without one is `422 VALIDATION_FAILED` with exception 5's wording, exactly as any
other admin write missing it.

**The admin cannot see which customers are mid-checkout at the old price, and that is accepted**
(`FR-ADR-035`). The window is under three minutes and the audit row records the change with its before
and after, so the difference is reconstructable afterwards.

**Every admin form must round-trip `version`.** This is a discipline that has to be applied
consistently or the protection is simply absent on whichever form forgot it — there is no runtime
signal that a form is missing it, only a lost edit later.

**Worked example — the money, end to end.**

```
T0      showtime 41: base_price_paise = 25000
        Customer holds C12 (Premium, 1250 bp) and C13 (Standard, 0 bp).

        Held prices computed and written into Redis under the hold token:
          C12 = (25000 * 11250 + 5000) // 10000 = 28125   (Rs 281.25)
          C13 = (25000 * 10000 + 5000) // 10000 = 25000   (Rs 250.00)
          held total = 28125 + 25000 = 53125              (Rs 531.25)

T0+40s  Admin sets base_price_paise = 30000.  version 1 -> 2.
        audit_log: action "showtime.base_price_changed"
                   before {"base_price_paise": 25000}
                   after  {"base_price_paise": 30000}

T0+95s  Customer confirms. The confirm reads the HELD prices.
        booking_seat C12: price_paise 28125, base_price_paise_applied 25000,
                          uplift_basis_points_applied 1250
        booking_seat C13: price_paise 25000, base_price_paise_applied 25000,
                          uplift_basis_points_applied 0
        booking.total_paise = 53125                       (Rs 531.25)

        The customer is charged Rs 531.25 - what they were shown.
        A customer who takes a hold at T0+120s is quoted:
          C12 = (30000 * 11250 + 5000) // 10000 = 33750   (Rs 337.50)
          C13 = (30000 * 10000 + 5000) // 10000 = 30000   (Rs 300.00)
```

---

### `P-ADM-13` · Configure a hall while it is not selling · `RULED`
`[SRC: SRC-001 §9.3 · SRC-001 §5.2.1 · SRC-001 §5.2.3 · SRC-003 OPEN-SCALE-02 · SRC-003 OPEN-SEAT-01 · FR-ADR-016 · FR-ADR-022 · FR-ADR-010 · FR-ADR-019]`
`[BRD: R-ADM-04]`

**Behaviour.** The admin configures a hall: its name, and the seats in it. **A seat row is a real,
physical, individually sellable seat** (`FR-ADR-016`). Seats belong to the screen and are **not**
created per showtime.

**Seat identity is `(screen_id, row_label, seat_number)`, unique.** `row_label` is a short string
(`A`, `B`, … and `AA` onward if a hall ever needs it); `seat_number` is an integer within the row.
They are decomposed rather than held as one `A-12` string, because the map is drawn from them and
sorted by them (`FR-ADR-016`).

**Layout is explicit grid coordinates**, `grid_row` and `grid_col`, kept separate from the label.
**Aisles, gaps and non-seat space are the absence of a seat at a coordinate**, not a placeholder row —
there is no "empty seat" entity, because an empty space cannot be sold, held, priced or audited
(`FR-ADR-016`). In a hall with a gap mid-row the label and the coordinate are different numbers, and
collapsing them produces a map that does not match the room.

**Every seat carries a non-null `seat_category_id`** (`FR-ADR-016`), which is what makes `SRC-001
§5.2.3`'s "distinguish seat categories, since we price them differently" true.

**Not modelled, on rulings** (`SRC-003 OPEN-SEAT-02`, `-03`, `-04`): **no accessible-seat flag, no
pair or couple linkage, no adjacency or gap rule.** Any available seat may be selected.

**Who may do it.** **admin only**, by the router dependency (`P-ADM-18`). `SRC-001 §4.5` gives seat
layouts to the administrator and that survives unchanged.

**This spec covers the FIRST of two states.** The state is defined by one question and one only:

> **Does any `showtime` row exist on this screen?**

Not "any showtime in the future". Not "any showtime with bookings". **Any showtime row at all**, past
or future, booked or empty. This spec is the `NO` branch; `P-ADM-14` is the `YES` branch.

**Preconditions.** The screen exists, and **no showtime row references it**.

**Happy path — what is permitted while a hall has no showtimes.**

| Operation | Permitted | Audit action |
|---|---|---|
| Create the screen | yes | `screen.created` |
| Rename the screen | yes | `screen.updated` |
| Add a seat | yes | `seat.created`, **one row per seat**, so a 220-seat batch writes 220 of them (`P-ADM-19`) |
| Change a seat's `row_label` | yes | `seat.updated` |
| Change a seat's `seat_number` | yes | `seat.updated` |
| Change a seat's `seat_category_id` | yes | `seat.updated` |
| Change a seat's `grid_row` or `grid_col` | yes | `seat.updated` |
| Take a seat out of service (`is_active = false`) | yes | `seat.deactivated` |
| Return a seat to service | yes | `seat.reactivated` |
| **Delete a seat** | **yes** | `seat.deleted` |
| Take the screen out of service | yes | `screen.deactivated` |
| **Delete the screen** | **no** | — |

**Exceptions 4 and 5 have a singular and a plural, and which one renders is a rule rather than a
judgement.** `EP-ADM-19` accepts up to 500 seats in one request, so a batch can offend on many seats at
once, and `SCR-XCT-01` rules that **the server renders `message` and the client never composes one** —
so a server with only a singular has nothing to render for the ordinary case. This is the same shape
the hold path already publishes for `SEAT_UNAVAILABLE`, and it is written the same way deliberately:

- **The singular renders at exactly one offending seat; the plural at two or more.**
- **The plural names every offending seat**, not the first and not a count of them, **in the order the
  client submitted them** — a batch is typed in a sequence and an admin corrects it in that sequence.
- Seat labels are joined `A, B and C`: commas between all but the last pair, ` and ` before the last.
- **Exception 5's plural names a count and not a list**, because a grid coordinate has no label a
  person recognises. `(4, 12)` means nothing to an admin reading a hall; `C12` does. **That asymmetry
  is deliberate and is the one place these two rows differ.**
- `details` carries the full machine-readable list in both cases — `duplicate_labels` for exception 4
  and `duplicate_coordinates` for exception 5 — so the interface can mark every offending field
  regardless of what the sentence names.

**Worked example — one batch, three collisions.**

```
Hall already contains:  C12, C13, C14
Admin submits a batch:  C11, C12, C13, C14, C15        (five seats, three of them already there)

Offending, in submitted order ....... C12, C13, C14
Rendered .......... "Seats C12, C13 and C14 already exist in this hall. Every seat in a hall
                     needs its own row and number."
details ........... {"duplicate_labels": ["C12", "C13", "C14"]}
Written ........... nothing. The batch is all-or-nothing, so C11 and C15 are not created either.

Same batch with only C13 already present:
Rendered .......... "Seat C13 already exists in this hall. Every seat in a hall needs its own
                     row and number."
```

**Nothing partial is written in either case** — the batch is refused whole, which is why the message
names every offence rather than the first: an admin who fixes one collision and resubmits should not
discover the second on the next attempt.

**Seat deletion is permitted here and it is not a contradiction of `R-ADM-07`.** `FR-ADR-012` scopes
the never-delete rule to **the record of what happened**. A seat on a screen that has never had a
showtime has been referenced by nothing — no booking, no booked seat, no showtime — so removing it
destroys no history. `FR-ADR-022` states this explicitly: *"A screen with no showtimes is freely
editable, including deleting seats."* **This is the configuration window and it is where the work
belongs.**

**The screen itself is never deleted**, because it may already carry audit rows describing its own
creation. It is taken out of service instead (`P-ADM-16`).

**Every seat write here takes `SELECT ... FOR UPDATE` on the `screen` row before it writes**
(`P-ADM-14`), and it takes it **unconditionally, including on a hall that has no showtimes yet**. The
lock is what makes a seat added in the same millisecond as a showtime creation either wholly inside
that showtime's seat set or wholly outside it; taking it unconditionally means the discipline does not
depend on the hall's state at the moment the code runs, which is the state most likely to change
between the check and the write.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | Not an admin | 403 `FORBIDDEN` | "This page is for administrators. Your account cannot change films, showtimes, prices or halls." |
| 2 | No screen with that id | 404 `NOT_FOUND` | "That hall no longer exists at this address." |
| 3 | No seat with that id | 404 `NOT_FOUND` | "That seat no longer exists at this address." |
| 4 | `(row_label, seat_number)` already used on this screen — **exactly one** offending seat | 422 `VALIDATION_FAILED` | "Seat C12 already exists in this hall. Every seat in a hall needs its own row and number." |
| 4b | `(row_label, seat_number)` already used on this screen — **two or more** offending seats | 422 `VALIDATION_FAILED` | "Seats C12, C13 and C14 already exist in this hall. Every seat in a hall needs its own row and number." |
| 5 | `(grid_row, grid_col)` already used on this screen — **exactly one** offending seat | 422 `VALIDATION_FAILED` | "Another seat is already drawn at that position in the map. Choose a different position." |
| 5b | `(grid_row, grid_col)` already used on this screen — **two or more** offending seats | 422 `VALIDATION_FAILED` | "Another seat is already drawn at 3 of those positions in the map. Choose different positions." |
| 6 | `seat_category_id` does not exist | 422 `VALIDATION_FAILED` | "That seat category is not on the list. Choose one of the listed categories." |
| 7 | `row_label` fails its bound | 422 `VALIDATION_FAILED` | "Enter a row label of 1 to 4 letters, for example A or AA." |
| 8 | `seat_number` zero, negative or not whole | 422 `VALIDATION_FAILED` | "Enter a seat number of 1 or more." |
| 9 | `grid_row` or `grid_col` zero, negative or not whole | 422 `VALIDATION_FAILED` | "Enter a row and column position of 1 or more." |
| 10 | A delete is attempted and a showtime exists on the screen | 409 `LAYOUT_FROZEN` | see `P-ADM-14` |
| 11 | A `DELETE` of the screen is attempted | **405 `METHOD_NOT_ALLOWED`** — no route is mounted and none is entered (`P-ADM-20`) | `E8`'s one generic sentence for the code. The hall-specific wording lives on `SCR-ADM-05`'s never-deleted note, where an admin reads it |

**Server-side validation.**

| Field | Type | Bound | Provenance | On failure |
|---|---|---|---|---|
| `screen.name` | string | 1..60 characters after trimming; **unique on `lower(trim(name))`** within the cinema | **technical** length; the normalisation is **derived** (`P-ADM-23`) | "Enter a hall name of 1 to 60 characters." / "A hall with that name already exists." |
| `row_label` | string | 1..4 characters, letters only, stored uppercase | **technical**, shaped by `FR-ADR-016`'s `A`…`AA` example | exception 7 |
| `seat_number` | integer | `>= 1` | **derived** — `FR-ADR-016` makes it an integer within the row and a zeroth seat has no physical meaning | exception 8 |
| `(screen_id, row_label, seat_number)` | — | unique | **ruled** (`FR-ADR-016`) | exception 4 |
| `grid_row`, `grid_col` | integer | `>= 1`, unique together within the screen | **derived** — `FR-ADR-016` draws the map by placing each seat at its coordinate, and two seats at one coordinate cannot both be drawn | exceptions 5, 9 |
| `seat_category_id` | integer | must exist, non-null | **ruled** (`FR-ADR-016`) | exception 6 |
| `is_active` | boolean | default true | **ruled** (`FR-ADR-022`) | — |

**The letter `I` is permitted here and the seed refuses it, and the two rules are not the same rule.**
`P-XCT-30` lays every seeded hall out with row letters that **skip `I`** — `A B C D E F G H J K L M`,
so Screen 1's furthest row is `J` and not `I` — because **`I` and `1` are the pair a person misreads
on a printed row marker and on a phone at 375 pixels.** That reason is about the seat label's real
surfaces, and those surfaces are the same whoever typed the label: **the label is printed on the
emailed receipt and read aloud at the door** (`P-ADM-14`). **This row's bound refuses nothing.** It is
`1..4` letters, and `EP-ADM-19` and `EP-ADM-20` accept `I` exactly as they accept `J`. **So a
hand-laid hall may carry a row `I`, and seat `I1` is the one the seed's own rule exists to prevent
somebody reading as `11`.**

**No ban is invented here, and the refusal to invent one is the point rather than an omission.** **No
frozen source, no client ruling and no `APPROVED` record states a permitted alphabet for a row label.**
`P-XCT-30`'s skip is a **demonstration-data convention**, and a demonstration convention hardened into
a product constraint is precisely the failure `SRC-002 §8.1.1` already produced on this project — that
clause is **CORRECTED by erratum `E-1`** and is cited here only as the historical example, never as
live authority: **the hold is 3 minutes** (`SRC-003 OPEN-HOLD-01`), and §8.1.1's seven is exactly the
assumption that hardened into a specification before anyone decided it. It would also not be free: a hall whose physical row markers **do** read `I` could not be
described accurately, and a label that does not match the sign on the wall is the same door problem
from the other side. **Raised as `PROPOSED-SEATALPHA-01`** in the Lane notes.

**The deadline is real and it is `P-ADM-14`'s.** `row_label` freezes the moment any showtime row
exists on the hall, so an `I` typed before the first showtime **cannot be corrected afterwards** —
the remedy is the retire-and-re-add of `P-ADM-14`, which leaves a permanently retired seat in the
room. **A rule the client gives later cannot repair a row already written.**

**This is a different question from `OPEN-SEATLABEL-01` and this row decides neither.** That row asks
whether `C12` and `c12` are one seat or two — a question about **case**, reserved and irreversible.
This paragraph is about **which letters may be used at all**, and it settles nothing about case,
normalisation or the unique constraint.

**⚠ Hall sizes are `ASSUMED`, never a constraint.** Six screens of 90, 120, 150, 180, 200 and 220
seats — the client said "pick random" (`SRC-003 OPEN-SCALE-02`, `FR-ADR-016`). **Nothing validates a
hall against those numbers.** They are what the seed script creates and what the seat map is designed
and tested against, and no more than that. **One cinema with six screens is `PROVISIONAL`**
(`SRC-003 C-2`, `FR-ADR-010`); the `cinema` entity stays in the schema with one row, and a screen
carries a `cinema_id`.

---

### `P-ADM-14` · A hall's layout freezes the moment a showtime exists on it · `RULED`
`[SRC: SRC-001 §9.3 · SRC-001 §7.6 · SRC-002 §8.1.5 · SRC-003 OPEN-OPS-02 · FR-ADR-022 · FR-ADR-016 · FR-ADR-012 · FR-ADR-024]`
`[BRD: R-ADM-04]`

**Behaviour.** Once **any** `showtime` row exists on a screen, the following are refused for every seat
on that screen, with **409 `LAYOUT_FROZEN`**:

- **removing a seat**
- **renumbering a seat** — changing `row_label` or `seat_number`
- **moving a seat to a different category** — changing `seat_category_id`

The following remain permitted, on the same screen, in the same state:

- **adding a seat**
- **taking a seat out of service**, and returning it to service
- **changing a seat's `grid_row` or `grid_col`**
- **renaming the screen**

**Why, and it is a derivation.** The oversell guard is a unique constraint on
`(showtime_id, seat_id)` (`SRC-002 §8.1.5`, `FR-ADR-024`), so **seat identity is load-bearing**.
`SRC-001 §7.6` requires the system to answer who booked *that seat* forever. A seat renumbered after it
was sold changes which seat a past customer believes they bought, and it is the label — not the id —
that the receipt carries and the person at the door reads. A category change would reprice a live,
already-selling showtime mid-sale, which `FR-ADR-035` refuses.

**Grid coordinates are allowed to change because the coordinate is where a seat is drawn and not what
it is** (`FR-ADR-022`). A map redrawn slightly differently changes nothing anyone bought.

**The two states, side by side.** This table is the whole of `R-ADM-04` and it is the part a developer
must not paraphrase.

| Operation | Screen has **no** showtime row | Screen has **one or more** showtime rows |
|---|---|---|
| Create the screen | permitted | n/a |
| Rename the screen | permitted | **permitted** |
| Take the screen out of service | permitted | **permitted** (`P-ADM-16`) |
| Delete the screen | **refused, always** | **refused, always** |
| Add a seat | permitted | **permitted** — on showtimes created after it, and on no showtime that already existed. The mechanism is the seat set below, not a phrase |
| Change `grid_row` / `grid_col` | permitted | **permitted** |
| Change `row_label` | permitted | **REFUSED — 409 `LAYOUT_FROZEN`** |
| Change `seat_number` | permitted | **REFUSED — 409 `LAYOUT_FROZEN`** |
| Change `seat_category_id` | permitted | **REFUSED — 409 `LAYOUT_FROZEN`** |
| Take a seat out of service | permitted | **permitted** (`P-ADM-15`) |
| Return a seat to service | permitted | **permitted** (`P-ADM-15`) |
| Delete a seat | permitted | **REFUSED — 409 `LAYOUT_FROZEN`** |

**Who may do it.** The refusal is not an action. It is **a check in the domain layer, not only in the
interface**, because the admin CRUD is not the only caller (`FR-ADR-022`).

**Preconditions.** None. The check runs on every seat write.

**Happy path.** The write is attempted; the domain layer counts showtime rows on the screen inside the
transaction; if the count is greater than zero and the requested change touches a frozen field, the
whole request is refused and nothing — including no audit row — is written.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | `row_label` or `seat_number` change on a screen with showtimes | 409 `LAYOUT_FROZEN` | "Seat C12 cannot be renumbered. This hall has showtimes, and a seat number is what a past customer's ticket says. You can add a seat, or take a seat out of service." |
| 2 | `seat_category_id` change on a screen with showtimes | 409 `LAYOUT_FROZEN` | "Seat C12 cannot be moved to a different category. This hall has showtimes, and its seats are already priced. You can add a seat, or take a seat out of service." |
| 3 | Seat delete on a screen with showtimes | 409 `LAYOUT_FROZEN` | "Seat C12 cannot be removed. This hall has showtimes, and removing a seat would break the record of who booked it. Take it out of service instead." |
| 4 | Not an admin | 403 `FORBIDDEN` | "This page is for administrators. Your account cannot change films, showtimes, prices or halls." |

**Server-side validation.** The frozen-field check itself. `details` on the 409 carries
`{"screen_id": n, "seat_id": n, "frozen_fields": ["row_label","seat_number","seat_category_id"],
"showtime_count": n}` so the interface can disable the right inputs rather than guess.

**Stated plainly, because the client will meet it.** **This is a real operational limit and the client
will feel it the first time they mistype a seat number after a showtime exists on that hall.** At that
point the only remedies are: take the mistyped seat out of service and add a correctly numbered one
next to it, which leaves a permanently retired seat row in the hall; or, if the hall is not yet selling
anything anyone cares about, accept the wrong label. **There is no rename.** The admin documentation
must say this before the client discovers it, not after (`FR-ADR-022`).

**The order of work that avoids it:** configure the hall completely, check every label, **then** create
the first showtime.

**On a seeded database that order is already impossible, and this is where that is said.** `P-XCT-30`'s
seed writes **720 showtimes across all six halls** — 120 per hall — in its own run. **Running the seed
is therefore what closes this window, for every hall, at once**, and it closes it *before an admin has
looked at a single seat label*. The freeze does not wait for a booking, a future showtime or an admin
action: it is `showtime_count > 0` on the screen, and the seed satisfies that on all six.

**The consequence, stated in the order somebody meets it.** A client who runs the seed to have
something to look at — which is what the seed is for — and then opens `SCR-ADM-05` to lay out a real
hall finds `row_label`, `seat_number` and `seat_category_id` **read-only on every hall in the
product**, the delete control absent everywhere, and the freeze banner in its frozen wording on a
database they have owned for five minutes. **Nothing is broken and nothing is a defect**; it is this
rule working exactly as specified. **It reads as a defect because no row said it would happen**, and a
limit that arrives unannounced is the one the client concludes is a bug.

**The two remedies are the ordinary ones and neither is new.** Lay out real halls **before** seeding,
or wipe and reseed — the command `P-XCT-30` already specifies — after which the halls are the seed's
again. **There is no third**: `P-ADM-20` mounts no `DELETE` for a `showtime`, so a hall cannot be
un-frozen by removing what froze it.

> **Only the first remedy exists in a deployed environment.** Wiping and reseeding destroys every
> booking in the database, and a booking is permanent — there is no cancellation and no refund path
> to make one good. So it is a real remedy locally and **not** one once the environment has taken a
> customer's money. `P-XCT-30` states the same asymmetry from the seed's side. Laying halls out
> before the first seed run is therefore the only remedy that survives deployment, which is what
> makes the ordering a one-way door rather than an inconvenience.

**It is stated here because the freeze is this row's rule.** `P-XCT-30` describes what the seed
writes; it is `P-ADM-14` that turns 720 showtimes into six frozen halls. **A reader who has met only
one of the two rows cannot derive the other**, which is why the consequence belongs on both and this
is the half that belongs here.

**The alternative that was rejected**, recorded so it can be reached for rather than reinvented:
versioning the layout — a new layout row per change with showtimes pinned to a version. It is the
correct answer for a cinema that re-fits halls regularly. It was rejected as disproportionate here —
`SRC-001 §9.3` says layouts change rarely, one venue exists, and it adds a join to the seat-map read
path, which is the hottest query in the product (`FR-ADR-022`).

#### A showtime's seat set is materialised when the showtime is created — **this row owns that rule**

**Ownership, declared, because two rows previously described the same fact in different words**
(`S1.2.1`). **`P-ADM-14` owns the rule below.** `P-ADM-15` owns what taking a seat out of service means
and points here for what happens to existing showtimes. `E1`'s seat-map row renders **the showtime's
seat set** and points here. `E7`'s occupancy row divides by `seat_count_at_creation` and points here.
**No other row restates the rule**, and where one of them appears to say something narrower, this row
governs.

**Behaviour.** When a `showtime` row is created, the server writes — **in the same transaction, under
the same `SELECT ... FOR UPDATE` on the `screen` row that `P-ADM-07` step 5 already takes** — one
`showtime_seat` row for **every seat that is in service on that screen at that instant**. Those rows
are that showtime's seats for the rest of its life. **`seat_count_at_creation` is the number of rows
written**, taken from that same statement, so the stored integer can never disagree with the rows it
claims to count.

The five words `P-ADM-14`'s table used to carry — *available on future showtimes, absent from past
ones* — are correct, and this is the mechanism that makes them true rather than aspirational. A rule
stated as a phrase is a rule two engineers implement differently.

**Who may do it.** **Not an action.** It is a consequence of `P-ADM-07`, which is admin only by the
router dependency (`P-ADM-18`). **No endpoint writes, adds to or removes from `showtime_seat`**, and
none is specified: the set is written once, by showtime creation, and never edited.

**Preconditions.** Those of `P-ADM-07`, plus: the screen has **at least one seat in service** at the
creation instant — the condition `P-ADM-07` exception 5 already refuses, restated here only because it
is now also the condition that would otherwise produce a showtime with an empty seat set and a zero
denominator (`E7`'s occupancy row treats a zero denominator as a data defect, and this is where that
defect would have been created).

**Happy path.**
1. The screen row is locked with `SELECT ... FOR UPDATE` (`P-ADM-07` step 5). This is the same lock
   that serialises the overlap check; no second lock is taken.
2. The `showtime` row is inserted.
3. One statement writes the set:
   `INSERT INTO showtime_seat (showtime_id, seat_id) SELECT :showtime_id, id FROM seat WHERE screen_id = :screen_id AND is_active = true`.
   Because it is one statement inside the lock, the set is exactly the in-service seats as they stood
   at that instant — not a list read earlier and inserted later.
4. `seat_count_at_creation` is set to the number of rows that statement wrote.
5. The `audit_log` row of `P-ADM-07` is inserted. **The seat set is not separately audited**: it is
   derived wholly from the screen's state and the showtime's creation, both of which are already on the
   record.
6. The transaction commits. **The showtime and its seat set become visible together, or neither does.**

**Every seat write takes the same lock.** `P-ADM-13`'s seat insert and `P-ADM-15`'s service toggle take
`SELECT ... FOR UPDATE` on the same `screen` row before writing, so a seat added or retired in the same
millisecond as a showtime creation is **either wholly inside the new set or wholly outside it**, never
half. **This is a build-session judgment under Art III.9** — no source states a lock discipline for
seat writes — and it is stricter than what was there before, so it needs no signature (Art III.10). It
is reversible: it is one lock statement.

**Consequences, all of them stated because each is a question somebody will otherwise answer by
guessing.**

- **A seat created later is absent from every showtime that already existed**, and present on every
  showtime created after it. Nothing back-fills.
- **A seat retired later stays on every showtime that already existed** — including a showtime a
  customer has already paid a seat on, which is the case that must never lose a paid seat — and is
  absent from every showtime created after the retirement. That is `P-ADM-15`'s existing rule,
  unchanged.
- **Restoring a retired seat does not make it reappear on a showtime that was created while it was
  retired.** Under any predicate computed from the seat's current flags it *would*, and a showtime's
  denominator would move after the showtime had already run. **It does not move.** This is the case
  that decided the design.
- **Occupancy cannot exceed 100 %**, because the numerator and the denominator are counted over the
  same set: a seat may only be held or booked on a showtime it is a member of, so the count of booked
  seats can never exceed `seat_count_at_creation`.
- **The layout freeze above still holds**, so a seat's label and category cannot change under a
  showtime that already exists. Addition and retirement are the only two permitted changes, and both
  are now defined rather than described.

**Membership is what makes a seat sellable on a showtime.** A hold and a booking may only name a seat
that is a member of that showtime's seat set. A seat id that is not a member **is not a seat of that
showtime** and is refused on the hold path; `E2 P-HLD-01` owns that refusal and the words the customer
sees, and this row does not restate them.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | The screen has no seats in service at the creation instant, so the set would be empty | 409 `LAYOUT_FROZEN` | "This hall has no seats in service. Add seats before creating a showtime on it." |
| 2 | The seat-set statement fails, or Postgres becomes unreachable during it | 503 `DEPENDENCY_UNAVAILABLE` | "The system cannot reach its database right now. Nothing was saved. Try again in a moment." |
| 3 | Not an admin | 403 `FORBIDDEN` | "This page is for administrators. Your account cannot change films, showtimes, prices or halls." |
| 4 | Any request to an address that would add a seat to, or remove a seat from, an existing showtime | 404 `NOT_FOUND` | "That page does not exist." |

Exception 2 is the ordinary all-or-nothing case and is listed because the failure is invisible
otherwise: the showtime insert may already have succeeded within the transaction, and **the transaction
is what makes the pair atomic**. Exception 4 is the same treatment `P-ADM-21` gives the
withdraw-showtime address — **the absence of the route is the control**, and a request to it answers
like any other address that does not exist.

**Server-side validation.**

| Field | Type | Bound | Provenance | On failure |
|---|---|---|---|---|
| `showtime_seat.showtime_id` | integer | must exist; written only by showtime creation | **derived** from the behaviour above | never client-supplied |
| `showtime_seat.seat_id` | integer | must be a seat of the showtime's screen and in service at the creation instant | **derived** (`FR-ADR-022`) | never client-supplied |
| `(showtime_id, seat_id)` | — | unique on `showtime_seat` | **derived** — a seat listed twice on one showtime would double that showtime's denominator | insert fails; the whole transaction rolls back, exception 2 |
| `seat_count_at_creation` | integer | `>= 1`, equal to the number of `showtime_seat` rows written in the same transaction, **never recomputed afterwards** | **ruled** (`FR-ADR-022`) | exception 1 for zero |

**That unique index is not the oversell guard, and nothing may treat it as one.** The oversell guard is
the unique constraint on **`booking_seat (showtime_id, seat_id)`** (`SRC-002 §8.1.5`, `FR-ADR-024`),
which is what the concurrency proof drops on purpose and restores. `showtime_seat`'s index only
prevents one seat being listed twice on one showtime. **Two tables, two constraints, two different
jobs; neither substitutes for the other**, and a reader who conflates them will believe the oversell
guard has been moved.

**Worked example — one seat, four showtimes, and the case that decided the design.** Screen 1 has 90
seats in service and its furthest row from the screen is `J` (**hall sizes are `ASSUMED` under `SRC-003 OPEN-SCALE-02`
and nothing validates against them**).

```
T0  showtime 501 created on Screen 1
      showtime_seat rows written ......... 90
      seat_count_at_creation ............. 90

T1  admin adds seat J11 (P-ADM-13).  Screen 1 now has 91 seats in service.
      showtime 501 ....................... still 90 rows.  J11 is NOT on it and never will be.

T2  showtime 502 created on Screen 1
      showtime_seat rows written ......... 91      (J11 included)
      seat_count_at_creation ............. 91

T3  admin takes J11 out of service (P-ADM-15).  Screen 1 now has 90 in service.
      showtime 501 ....................... 90 rows, unchanged
      showtime 502 ....................... 91 rows, unchanged - J11 stays on it, and a customer
                                           who has already paid for J11 on 502 keeps that seat

T4  showtime 503 created on Screen 1
      showtime_seat rows written ......... 90      (J11 excluded - it is out of service now)
      seat_count_at_creation ............. 90

T5  admin returns J11 to service (P-ADM-15).  Screen 1 has 91 in service again.
      showtime 503 ....................... STILL 90 rows.  J11 does not appear on it.
                                           THIS IS THE LINE TO READ TWICE.  A predicate computed
                                           from the seat's current flags would put J11 back on 503
                                           and move a denominator for a showtime that may already
                                           have run.

T6  showtime 504 created on Screen 1
      showtime_seat rows written ......... 91      (J11 is in service again)

Occupancy, computed over the SAME set both times (E7's rule):
      502 with 45 seats sold ....... 45 / 91 = 49.45 %
      502 fully sold ............... 91 / 91 = 100.00 %      and it cannot read higher, because
                                     every booked seat must be a member of 502's 91-row set
      503 fully sold ............... 90 / 90 = 100.00 %      J11 is not sellable on 503 at all
```

**What it costs, computed from the seed rather than guessed at.** One row per seat per showtime. The
inputs are no longer illustrative: `P-XCT-30` specifies the seeded schedule exactly — **120 showtimes
per hall** and **960 seats across the six halls** at the `ASSUMED` sizes of `SRC-003 OPEN-SCALE-02`
(90, 120, 150, 180, 200, 220 — mean 160):

```
showtimes .... 6 halls x 120 = 720
rows ......... 720 x 160 = 115,200            = 6 halls x 120 showtimes x that hall's seat count
row width .... 2 x 8-byte integers + PostgreSQL's 24-byte tuple header = 40 bytes
heap ......... 115,200 x 40 = 4.61 MB, plus a comparable primary-key index
```

**The figure moved and the conclusion did not**: a previous revision of this row estimated 144,000 rows
from an illustrative month at five showtimes a day, which was a guess made before the seed was
specified. The real number is **115,200**, and both land in single-digit megabytes against a 20 GB
volume. **It is stated as computed rather than assumed** so that a reader can recompute it when the
seed changes, which is the property the guess did not have.

**The row width is reasoned, not measured** — no application code exists and nothing has been observed
running, so the tuple header is PostgreSQL's documented figure rather than one taken from a real table.
It is stated because `SRC-002 §5.4.1` gives the whole host about 1 GB and a table that grows with every
showtime is exactly the kind that is discovered in month two rather than declared in month one. **The
seed is a floor and not a ceiling**: the table grows by one row per seat for every showtime the admin
creates afterwards, at roughly 6.4 kB per showtime on a 160-seat hall. The set is written once and read
on the seat-map path, which is the hottest query in the product.

**The alternative that was rejected**, recorded so it is reached for rather than reinvented: **compute
the showtime's seats from a predicate over the screen's current seats** — no table, no rows, no
storage. It was rejected because it cannot express T5. Under any predicate reading the seat's current
flags, restoring J11 puts it back on showtime 503, whose `seat_count_at_creation` says 90; the
denominator and the rendered map then disagree, and `E7`'s occupancy can read above 100 %. Adding a
creation timestamp to the seat row and comparing it against the showtime's does not rescue it either:
it makes membership depend on clock ordering, and it still gets T5 wrong, because retirement and
restoration are not the same event as creation. **The predicate is cheaper in storage and wrong in the
one case the client will actually produce.**

---

### `P-ADM-15` · Take a seat out of service and return it · `RULED`
`[SRC: SRC-001 §9.3 · SRC-003 OPEN-OPS-02 · FR-ADR-022 · FR-ADR-012 · FR-ADR-019]`
`[BRD: R-ADM-04 · R-ADM-07]`

**Behaviour.** A seat that must come out of service — broken, removed from the room, whatever the
reason — is marked `is_active = false`. **It is not deleted, at any time, in either hall state**
(`FR-ADR-022`).

An out-of-service seat:
- **is not offered on showtimes created after the change**;
- **is not counted in the occupancy denominator of showtimes created after the change**, because that
  denominator is `seat_count_at_creation`, frozen on the showtime row (`FR-ADR-022`);
- **still resolves for every past booking that references it**, so a receipt from last month still
  names a real seat in a real hall;
- **does not disappear from a showtime that already exists.** `seat_count_at_creation` on an existing
  showtime does not move, and a seat already sold on an existing showtime stays sold.

**The mechanism behind all four of those bullets is the showtime's seat set, and `P-ADM-14` owns it.**
A showtime's seats are written once, when the showtime is created; this row changes what the *screen*
offers from now on and changes nothing about a showtime that already exists. **Returning a seat to
service therefore does not add it to any showtime created while it was out of service** — a restored
seat is sellable on showtimes created after the restoration and on no others. `P-ADM-14` carries the
worked example; this row does not restate it.

**Who may do it.** **admin only**, by the router dependency (`P-ADM-18`).

**Preconditions.** The seat exists.

**Happy path.**
1. The admin toggles the seat on `SCR-ADM-05` and confirms.
2. In one transaction the server takes `SELECT ... FOR UPDATE` on the seat's `screen` row
   (`P-ADM-14`, so this write cannot land half-inside a showtime creation running at the same
   instant), writes `is_active`, and inserts an `audit_log` row with
   `action = "seat.deactivated"` or `"seat.reactivated"`, `before = {"is_active": true}`,
   `after = {"is_active": false}`.
3. The server returns 200.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | Not an admin | 403 `FORBIDDEN` | "This page is for administrators. Your account cannot change films, showtimes, prices or halls." |
| 2 | No seat with that id | 404 `NOT_FOUND` | "That seat no longer exists at this address." |
| 3 | The seat is already in the requested state | 409 `LAYOUT_FROZEN` | "Seat C12 is already out of service." / "Seat C12 is already in service." |

**Exception 3 is a `409` and not `P-ADM-12`'s no-op `200`, deliberately.** That rule governs versioned
entities and **a seat has no `version`** — `EP-ADM-20` accepts none — so there is no `version` for a
no-op to protect from being bumped. This control asserts a state rather than edits a field, and a
repeat is almost always a stale grid or the wrong row, which is worth saying rather than swallowing.
`P-ADM-12` carries the same statement so the two rows cannot drift apart.

**Server-side validation.** `is_active`: boolean, required.

**What this does NOT do, stated because it is the obvious wrong assumption.** Taking a seat out of
service **does not** release it from a showtime that is already selling, **does not** cancel a booking
that already holds it, and **does not** refund anybody. A seat sold on Friday's showtime and taken out
of service on Thursday is still that customer's seat. There is no mechanism in v1 that removes a seat
from a customer who has paid for it, and building one would require the ruling that
`OPEN-SHOWCANCEL-01` is waiting for (`P-ADM-21`).

---

### `P-ADM-16` · Withdraw a hall · `RULED`
`[SRC: SRC-003 OPEN-OPS-02 · SRC-001 §7.6 · FR-ADR-012 · FR-ADR-019]`
`[BRD: R-ADM-04 · R-ADM-07]`

**Behaviour.** A screen that is retired is marked `is_active = false` (`FR-ADR-012`). **The row stays
and is never deleted.** A withdrawn hall:
- **accepts no new showtimes** (`P-ADM-07` exception 4);
- **keeps every existing showtime, every seat and every booking**, all of which still resolve;
- **still appears wherever a historical booking or a dashboard figure names it**, because the record
  points at the row and not at a name string.

**Who may do it.** **admin only**, by the router dependency (`P-ADM-18`).

**Preconditions.** The screen exists; the submitted `version` matches.

**Happy path.** One transaction: write `is_active`, increment `version`, insert an `audit_log` row with
`action = "screen.deactivated"` or `"screen.reactivated"`. Return 200.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | Not an admin | 403 `FORBIDDEN` | "This page is for administrators. Your account cannot change films, showtimes, prices or halls." |
| 2 | No screen with that id | 404 `NOT_FOUND` | "That hall no longer exists at this address." |
| 3 | `version` does not match | 409 `VERSION_CONFLICT` | "This hall was changed by someone else while you were editing. Reload to see the current details, then make your change again. Nothing you typed has been saved." |
| 4 | A `DELETE` is attempted | **405 `METHOD_NOT_ALLOWED`** — no route is mounted and none is entered (`P-ADM-20`) | `E8`'s one generic sentence for the code. The hall-specific wording lives on `SCR-ADM-05`'s never-deleted note |

**Server-side validation.** `is_active`: boolean, required. `version`: as `P-ADM-12`.

**Withdrawing a hall that has future showtimes with bookings is permitted, and it cancels nothing.**
The showtimes stay, the bookings stay, the customers keep their seats. The hall simply accepts no new
showtimes. **If the intention is to stop a specific screening from happening, that is withdrawing a
showtime, and it does not exist in v1** (`P-ADM-21`). The confirmation on `SCR-ADM-05` says exactly
this, so an admin cannot mistake one for the other.

---

### `P-ADM-17` · Create a manager account and assign it screens · `RULED`, on a `PROVISIONAL` role set
`[SRC: SRC-003 OPEN-SCOPE-01 · SRC-003 OPEN-OPS-03 · SRC-003 C-1 · SRC-001 §4.4 · SRC-001 §4.5 · FR-ADR-009 · FR-ADR-011 · FR-ADR-050 · FR-ADR-019]`
`[BRD: R-ADM-05]`

**Behaviour.** The admin creates a `manager` account and assigns it one or more screens. Assignment is
a **`manager_screen_assignment` table**: one row per `(manager user, screen)`, unique on the pair
(`FR-ADR-011`).

> ## ⚠ `PROVISIONAL` — one message from the client reverses this
> That a **manager role exists at all** is a build-session reading reconciling two of the client's own
> answers (`SRC-003 C-1`, `FR-ADR-009`). `OPEN-ROLE-01` says *"do not make more personas… only 1 admin
> persona"*; `OPEN-SCOPE-01` then describes *"2 managers per cinema hall"* with a dashboard. **The
> rejected reading is three roles**, with the manager dashboard served to admins filtered by hall. If
> the client reverses this, the manager role value, this assignment table and every endpoint in this
> spec are removed.

**"Two managers per hall" is an observation of the client's current staffing, not a constraint**
(`FR-ADR-011`). **No check constraint, no trigger and no application rule enforces the number two.**
The schema permits one, three or zero. The seed script creates twelve assignments because that is what
the client described.

**A manager may be assigned to more than one screen.** The ruling describes two managers per hall, not
one hall per manager, and nothing forbids the reverse.

**A manager with no assignment sees an empty dashboard, not an error.** That is the correct state for a
newly created account (`FR-ADR-011`).

**A manager performs no privileged write, ever** (`SRC-003 OPEN-OPS-03`). Every endpoint under
`/api/admin` refuses the role, and **every route mounted on the manager router is a safe method** —
`P-ADM-18` owns both, and both are checkable by test.

**The sentence used to read *"a manager writes nothing, ever"* and the product's own contract
contradicts it.** `api/contract.json` — generated from the endpoint blocks of every lane — admits
`manager` on **five non-`GET` endpoints outside this epic**: `EP-HLD-01`, `EP-HLD-03`, `EP-HLD-04`,
`EP-PAY-01` and `EP-TKT-02`. Those are the **customer** capabilities — holding a seat, releasing one,
confirming a booking, asking for a receipt to be resent — reached because a manager holds an account
and `E8 P-XCT-05` gives every account-holder the customer router. **A flat "writes nothing" is false
against the artefact the client and the server are both built from**, and a specification a generated
file disproves is worse than one that is merely narrow.

**Whether that is right is `OPEN-MGRBOOK-01` and this row does not decide it** — *may a manager buy a
ticket, specifically in a hall whose takings they report on?* — filed in `CONSTITUTION.md` Article X
as **`reserved: access control`**. **Nothing here narrows or widens it.** What changes is only that
this row now claims what it can defend: **no privileged write**, which is `OPEN-OPS-03`'s actual
ruling and is true of every endpoint in this epic.

**Who may do it.** **admin only**, by the router dependency (`P-ADM-18`).

**Preconditions.**
1. The email address is not already used by any account. **Nothing is ever deleted, so an email address
   stays taken permanently** (`FR-ADR-012`).
2. Every `screen_id` in the assignment set exists.

**Happy path.**
1. The admin enters an email address on `SCR-ADM-06` and chooses the screens.
2. In one transaction the server inserts the `user` row with `role = "manager"` and **no usable
   password**, inserts one `manager_screen_assignment` row per screen, and inserts an `audit_log` row
   with `action = "manager.created"` plus one row per assignment with
   `action = "manager.screen_assigned"`.
3. The server returns 201 with the manager's id, email and assigned screen ids.
4. **The manager obtains a password through the existing password-reset flow** (`FR-ADR-050`). The
   admin never sets or sees a password.
5. **The product sends nothing.** No `outbox_message` row is written, no SES message is enqueued, no
   invitation is dispatched, and the manager is not told that an account exists at their address.
   **The admin tells them, outside the product.**

**Step 5 is a gap and it is written as one rather than left to be discovered.** `E5 P-ACC-07`'s
password reset is **self-initiated**: somebody who already believes they have an account types their
address into a form and asks for a link. **A manager created by step 2 has no reason to do that** —
nothing has reached them — so the account sits with `has_signed_in` false indefinitely. **A created
manager account is unreachable until a human says so out of band**, and `E5 P-ACC-08` confirms that
reset is the only route by which such an account ever signs in for the first time. Steps 1 to 4 are
each individually correct and the sequence still ends with an account nobody can use.

**No invitation message is specified, and that is a build-session decision under Art III.9 rather
than an oversight.** **No frozen source, client ruling or `APPROVED` record asks for one.** Building
it would coin a new outbox topic in `E4`'s namespace, a second SES template, and a second class of
outbound mail in a product whose **only** specified message is the receipt — and `SRC-001 §6`'s
scope-as-written rule refuses building what nobody asked for. **The interim position is stated
instead**: the product notifies nobody, `SCR-ADM-06` says so in terms to the admin who is creating
the account, and the admin's own message is the mechanism. **Reversible in one direction only, and
cheaply**: adding an invitation later adds a message and breaks nothing, which is why the fail-closed
reading was taken rather than a guessed one.

**The signal that it worked is already on the screen and needs no new field.** `has_signed_in`
(`EP-ADM-22`, derived from `last_signed_in_at`) is false until the manager completes the reset, and
`SCR-ADM-06` renders **"Has not signed in yet"** against every such row. **That is the admin's own
check that their out-of-band message landed**, and it is why the flag is stated as a normal state
rather than an error.

**How the admin can tell whether a manager has ever used the account.** The `user` row carries
`last_signed_in_at`, a nullable `timestamptz` in UTC, specified in `E5 P-ACC-01` and written on every
successful sign-in by `E5 P-ACC-02` — and, on this flow specifically, by `E5 P-ACC-08` when the manager
completes the reset that gives them their first password. It is null until then. **`has_signed_in` is
not a stored field**: `EP-ADM-22` derives it as `last_signed_in_at IS NOT NULL` and `SCR-ADM-06`
renders it. **Signing in is not a privileged write and writes no `audit_log` row** (`P-ADM-19`).

**The admin never types a password for someone else.** The alternative — an admin-set initial password
— was rejected because it puts a live credential in an admin form, in a request body, in a log line's
request context, and potentially in an `audit_log` row's `after`. Reusing the reset flow that already
exists invents no new mechanism. **This is a build-session judgment under Art III.9** and it is
stricter, so it needs no signature (Art III.10).

**No credential ever enters an audit row.** `before` and `after` on any `user` row **exclude
`password_hash` and every field derived from it**, without exception. This is stated as a rule and not
left to whoever writes the handler.

**Changing an assignment set.** The admin submits the **complete** set of screen ids for that manager;
the server computes the difference and writes one `manager.screen_assigned` audit row per addition and
one `manager.screen_unassigned` row per removal. **Removing an assignment row is a permitted deletion**
— it is current state, not the historical record (`FR-ADR-011`, `FR-ADR-012`) — and the audit row is
what carries the history of it.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | Not an admin | 403 `FORBIDDEN` | "This page is for administrators. Your account cannot change films, showtimes, prices or halls." |
| 2 | The email address is already used | 422 `VALIDATION_FAILED` | "An account already exists with that email address. Accounts are never removed, so an address stays in use once it has been registered." |
| 3 | The email address is not a valid address | 422 `VALIDATION_FAILED` | "Enter a valid email address." |
| 4 | A `screen_id` does not exist | 422 `VALIDATION_FAILED` | "One of those halls no longer exists. Reload the page and choose again." |
| 5 | `screen_ids` holds a duplicate | 422 `VALIDATION_FAILED` | "That hall is listed twice. Choose each hall once." |
| 6 | The target user exists but is not a manager | 422 `VALIDATION_FAILED` | "That account is not a manager account. Screens can only be assigned to managers." |
| 7 | No user with that id | 404 `NOT_FOUND` | "That account no longer exists at this address." |

**Exception 6 was `409 VALIDATION_FAILED` and is now `422`, and the message does not change.**
`EP-ADM-24` declared `409`, this row declared `409 VALIDATION_FAILED`, and the generated error registry
fixes `VALIDATION_FAILED` at `422` — three sources, three answers, and a client branching on `code`
cannot satisfy all three. **The tie-break applied, stated because `S1.2` names the registry as an owner
without ranking it: the generated registry fixes a code's status and a block may not contradict it.**
So `422` wins in both places. The trigger is a submitted field naming a row of the wrong kind, which is
what `VALIDATION_FAILED` is for; **no new error code is minted**, because inventing one for a case an
existing code already covers is how a registry of thirteen becomes a registry of forty, and `S6` would
require a `newerrorcode` declaration for it besides.

**Server-side validation.**

| Field | Type | Bound | Provenance | On failure |
|---|---|---|---|---|
| `email` | string | 1..254 characters, a valid address, unique across all accounts | **technical** length (254 is the RFC 5321 path limit); uniqueness is **derived** from `FR-ADR-012` | exceptions 2, 3 |
| `screen_ids` | array of integer | 0..*, unique, each must exist | **ruled** (`FR-ADR-011`: zero is a valid state, and no upper bound exists because "two per hall" is not a constraint) | exceptions 4, 5 |
| `role` | — | **not accepted from the request.** This endpoint creates `manager` accounts and nothing else | **derived** — an endpoint that accepts a role string is one privilege-escalation bug away from creating an admin | **400 `REQUEST_INVALID`**, as any unknown property (the uniform rule at the head of `S4`) |

**This row's rejection was published as `422 VALIDATION_FAILED` and is now `400 REQUEST_INVALID`. The
behaviour does not change and neither does the reason — only the envelope.** `role` is a property this
endpoint does not define, which is the registry's own definition of `REQUEST_INVALID`, and the registry
fixes a code's status. **This row is where the uniform rule came from**: it was the only one of the
three answers in the section that rejected rather than dropped, and its argument — a silently dropped
property tells the caller something happened that did not — is what generalised to every other admin
endpoint. It keeps the reasoning and gives up only its private status code.

**There is no endpoint that creates an admin account.** The first admin is created by the seed script
(`FR-ADR-067`); creating a second is a database action the client performs deliberately. **This is a
build-session judgment under Art III.9**, stricter than anything ruled, and it is recorded because a
developer will otherwise add one for symmetry.

**The access-control test this table exists to make possible** (`FR-ADR-011`): assign manager A to
screen 1, create bookings on screens 1 and 2, then assert that A's dashboard returns a **non-empty**
figure for screen 1 and a denied or empty result for screen 2. **Both halves are required.** A test
asserting only "denied" passes against a query that returns nothing for anybody.

---

### `P-ADM-18` · Authorisation is one router dependency, applied once and never per handler · `RULED`
`[SRC: SRC-001 §7.4 · SRC-003 OPEN-OPS-03 · SRC-003 C-1 · FR-ADR-009 · FR-ADR-011 · FR-ADR-052]`
`[BRD: R-ADM-05]`

**Behaviour.** **Every privileged write in this system belongs to the admin role alone**
(`SRC-003 OPEN-OPS-03`). Creating or editing a film, publishing one, setting a display window,
uploading a poster, creating or editing a showtime, setting a base price, changing a category uplift,
configuring a hall, adding or retiring a seat, and creating or assigning a manager are **all the
admin's and only the admin's**.

**How it is enforced.** A single dependency is attached to the `/api/admin` router. It runs before
every handler mounted under that prefix and it does three things:

1. Resolves the session token. No token, or an invalid one, is **401 `AUTH_REQUIRED`**.
2. Reads the role from the authenticated user row — **never from the token's claims alone and never
   from a request field**.
3. If the role is not `admin`, **403 `FORBIDDEN`**. The handler is never entered.

**No handler under `/api/admin` performs its own role check.** Not one. `SRC-001 §7.4` requires that
management functions are not reachable by customers, and a router whose access depends on a per-handler
check is the pattern that eventually misses a handler (`FR-ADR-011`, `FR-ADR-009`).

**A manager endpoint that writes anything is a defect, not a feature** (`FR-ADR-009`). The manager
router is a **separate router with a separate dependency**, and **every route mounted on it is a safe
method**. A route that mutates state may not be mounted there, and that is checkable: a test enumerates
the manager router's routes and asserts every one of them is `GET` or `HEAD`.

**Who may do it.** Not an action.

**Preconditions.** None.

**Happy path.**
1. A request arrives at any path under `/api/admin`.
2. The router dependency resolves and authorises before routing to the handler.
3. The handler runs, and it contains no authorisation code at all.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | No session token, or an expired or invalid one | 401 `AUTH_REQUIRED` | "Sign in to continue." |
| 2 | Signed in as `customer` | 403 `FORBIDDEN` | "This page is for administrators. Your account cannot change films, showtimes, prices or halls." |
| 3 | Signed in as `manager` | 403 `FORBIDDEN` | "This page is for administrators. Your account cannot change films, showtimes, prices or halls. Managers can view their halls' figures." |
| 4 | A `guest` — no account at all | 401 `AUTH_REQUIRED` | "Sign in to continue." |

**A manager and a customer get the same code and nearly the same message.** The distinction is
deliberate: `FORBIDDEN` says the account is known and not permitted, `AUTH_REQUIRED` says there is no
account. Nothing in either message discloses whether the object at that address exists.

**Server-side validation.** The role check itself. **The role comes from the database row, not the
token.** A token minted before a role changed must not carry stale authority; the row is read on every
admin request. This costs one indexed lookup per admin request, which is a rate the operator will never
notice against a single admin account.

**The interface is never the enforcement point.** Hiding the admin navigation from a customer is
presentation. The router dependency is the control.

---

### `P-ADM-19` · Every privileged write records who, when, before and after — in the same transaction · `RULED`
`[SRC: SRC-001 §7.6 · SRC-001 §10.30 · SRC-003 OPEN-OPS-03 · SRC-003 OPEN-OPS-02 · FR-ADR-019 · FR-ADR-012 · FR-ADR-056]`
`[BRD: R-ADM-06]`

**Behaviour.** **Every privileged write inserts a row into `audit_log` in the same database transaction
as the change itself.** Either both land or neither does. **This is the mechanism, not a nicety** — an
audit written after the commit is missing exactly the rows that crashed (`FR-ADR-019`).

**What is captured, per row:**

| Column | Holds |
|---|---|
| `id` | `bigint` identity |
| `occurred_at` | `timestamptz`, UTC |
| `actor_user_id` | non-null foreign key to the acting user. **Never a role name, never a service account** |
| `actor_role` | the role the actor held **at the time**, copied rather than joined, because a role can change |
| `action` | a value from the controlled vocabulary below |
| `entity_type` | the table the change landed on |
| `entity_id` | the primary key of the changed row. **For `manager.screen_unassigned` it is the primary key the removed `manager_screen_assignment` row had** — see below |
| `before` | `jsonb`, the **changed fields'** prior values. Null for a creation |
| `after` | `jsonb`, the **changed fields'** new values. Null for a withdrawal that changes nothing else |
| `request_id` | the request id from the log context, so an audit row joins to the log lines (`FR-ADR-056`) |

**`manager.screen_unassigned` names a row that no longer exists, and that is the correct value.**
`P-ADM-17` removes an assignment row outright — one of only two deletions this epic performs
(`P-ADM-20`), permitted because an assignment is current state and not the historical record
(`FR-ADR-011`). So the audit row's `entity_type` is `manager_screen_assignment` and its `entity_id` is
**the primary key that row held at the moment it was removed**, recorded as it was. **It deliberately
resolves to nothing.**

Three consequences, stated because each is a way of getting it wrong:

- **Nothing may join `entity_id` to the live table for this action.** A change-log view that renders a
  joined assignment renders an empty row for every unassignment, which reads as a defect in the log
  rather than as the deletion it is recording.
- **`before` is where the meaning lives**, and it carries `{"user_id": n, "screen_id": n}` — the two
  facts a reader actually needs. `after` is null, which is this table's existing convention for a
  removal that changes nothing else. **The pair `manager.screen_assigned` / `manager.screen_unassigned`
  is therefore self-contained**: the history of who could see which hall reconstructs from the audit
  rows alone, with no surviving assignment row to join to, which is the whole reason `FR-ADR-011`
  permits the delete.
- **The id is not reused to mean something else.** Putting the manager's `user_id` in `entity_id`
  instead would make it resolve — and would make it disagree with `entity_type`, which says the changed
  row was an assignment and not a user. **A column that resolves by lying about what it points at is
  worse than one that honestly points at something gone.**

**`before` and `after` carry only the fields that changed, not the whole row** (`FR-ADR-019`). A
full-row snapshot on every edit makes this the largest thing in the database and buries the one field
that moved.

**One request writes one audit row per `action` kind that actually changed — not one row per request,
and not one row per field.** This is the general rule and it governs every write in this section. Three
rows already stated it for their own entity — `P-ADM-09` (*"a request that changes both writes both
rows"*), `P-ADM-25`, and the price/rename split on `P-ADM-11` — and it is lifted here so it also
covers the movie `PATCH`, which is the endpoint where the merge actually happens and the one place it
was never said.

Worked through, because the mapping is the whole rule:

| One request | Rows written |
|---|---|
| `EP-ADM-04` changing `title` only | one `movie.updated` |
| `EP-ADM-04` changing `display_from` only | one `movie.display_window_changed` |
| **`EP-ADM-04` changing `title` and `display_until`** | **two rows — one `movie.updated` and one `movie.display_window_changed`**, in the same transaction |
| `EP-ADM-11` changing `base_price_paise` and `starts_at` | two rows — `showtime.base_price_changed` and `showtime.updated` (`P-ADM-09`) |
| `EP-ADM-14` changing a category's name and its uplift | two rows — `seat_category.updated` and `seat_category.uplift_changed` |
| `EP-ADM-17` renaming a hall and taking it out of service | two rows — `screen.updated` and `screen.deactivated` |
| `EP-ADM-20` moving a seat's coordinates and taking it out of service | two rows — `seat.updated` and `seat.deactivated` |
| `EP-ADM-29` changing a venue's name and its zone | two rows (`P-ADM-25`) |

**Why it is observable rather than an internal detail, which is the reason it had to be decided.**
`EP-RPT-04` filters the change log **on `action`**. Under the merged reading — one row per request,
carrying whichever action the handler happened to pick — a filter written against
`movie.display_window_changed` matches nothing for every request that also touched a title, and the
operator concludes the window was never changed. **The audit table's job is to answer what changed, and
a row that names one of two changes answers it wrongly.**

**Each row carries only its own fields.** The `movie.updated` row's `before` and `after` carry the
title; the `movie.display_window_changed` row's carry the window. Neither carries the other's, because
`before` and `after` are the changed fields of **that action** and not of the request.

**A field submitted with the value it already holds is not a change and contributes no row** — see the
no-op rule on `P-ADM-12`. A request that submits two fields and changes one writes exactly one row.

**One request that changes many rows writes one audit row per changed row. A 220-seat batch writes 220
`seat.created` rows.** This follows from the table above rather than extending it: `entity_type` is the
table the change landed on and `entity_id` is **the primary key of the changed row**, and one column
cannot hold 220 primary keys without lying about one of the two — either the row names a seat that is
one of many, or it names none of them. `P-ADM-17` already rules the multi-entity case exactly this way
for manager assignments, one row per addition and one per removal, and `EP-ADM-19` is the same shape
with a larger batch.

**The consequence is stated rather than discovered.** Laying out Screen 6 in one request puts **220
rows into the change log at once**, and `EP-RPT-04`'s first page will be nothing but seat creations for
as long as it takes an operator to page or filter past them. **That is survivable and the alternative
is not**: the log is filtered by `action` and by actor and is paginated, so the noise is one filter
click away, whereas an audit trail that cannot name which seat was created cannot answer the question
`SRC-001 §7.6` asks it to answer. **All 220 rows are written in the same transaction as the seats**, so
the batch is still all-or-nothing: 220 seats and 220 audit rows, or neither.

**What is NOT captured:**

- **Reads are not audited.** A manager opening a dashboard writes nothing. Auditing reads would produce
  a table dominated by page loads, and `OPEN-OPS-03` asks who *changed* things (`FR-ADR-019`).
- **A customer booking a seat is not a privileged write.** It is the product working, and
  `SRC-001 §7.6`'s "who booked this seat and when" is answered by the booking row itself, which is
  permanent (`FR-ADR-019`).
- **No credential.** `password_hash` and everything derived from it never appear in `before` or `after`
  (`P-ADM-17`).
- **No card data anywhere** — not a column, not a log, not a fixture (`SRC-003 OPEN-PAY-01`). Payment
  is simulated and the rule is trivially satisfiable; it stays satisfied.
- **No poster bytes.** `before` and `after` carry the S3 object key, not the image.

**Append-only, enforced and not merely intended.** The application's database role holds `INSERT` and
`SELECT` on `audit_log` and **no `UPDATE` and no `DELETE`** (`FR-ADR-019`). **An audit log the
application can rewrite is not evidence.** This is a grant in the migration, checkable by a test that
asserts an `UPDATE` from the application role raises an insufficient-privilege error.

**The controlled `action` vocabulary.** `FR-ADR-019` requires the PRD to enumerate it, because a
free-text action column becomes unqueryable within a month.

> **This table is the single source of the `action` strings for the whole product.** Every privileged
> write in FrontRow is an admin write, every admin write is specified in this epic, and every one of
> them appears below. **No other section, document, screen, test or handler may introduce an `action`
> string.** An action string that appears anywhere else and is not a member of this table is a defect
> **in that other place**, not a gap here, and it is fixed by changing that place to a member. The
> reverse is also true: a write this epic specifies and this table does not list is a defect in this
> table, and the write does not ship until the row is added.
>
> **The specific string that has already been got wrong: a change to a showtime's base price writes
> `showtime.base_price_changed`.** `showtime.price_changed` is **not** a member of this vocabulary and
> never has been. A change-log filter written against `showtime.price_changed` matches nothing,
> silently, and looks like a showtime whose price was never changed.

**These, and only these, are written by this epic:**

| `action` | `entity_type` | Written by |
|---|---|---|
| `movie.created` | `movie` | `P-ADM-01` |
| `movie.updated` | `movie` | `P-ADM-02` |
| `movie.poster_uploaded` | `movie` | `P-ADM-03`, first poster |
| `movie.poster_replaced` | `movie` | `P-ADM-03`, subsequent |
| `movie.display_window_changed` | `movie` | `P-ADM-04` |
| `movie.published` | `movie` | `P-ADM-05` |
| `movie.unpublished` | `movie` | `P-ADM-06` |
| `showtime.created` | `showtime` | `P-ADM-07` |
| `showtime.updated` | `showtime` | `P-ADM-09` |
| `showtime.base_price_changed` | `showtime` | `P-ADM-09`, `P-ADM-10` |
| `seat_category.created` | `seat_category` | `P-ADM-11` |
| `seat_category.updated` | `seat_category` | `P-ADM-11`, a name change |
| `seat_category.uplift_changed` | `seat_category` | `P-ADM-11` |
| `cinema.updated` | `cinema` | `P-ADM-25`, a rename |
| `cinema.timezone_changed` | `cinema` | `P-ADM-25`, a zone change |
| `screen.created` | `screen` | `P-ADM-13` |
| `screen.updated` | `screen` | `P-ADM-13`, a rename |
| `screen.deactivated` | `screen` | `P-ADM-16` |
| `screen.reactivated` | `screen` | `P-ADM-16` |
| `seat.created` | `seat` | `P-ADM-13` |
| `seat.updated` | `seat` | `P-ADM-13` |
| `seat.deleted` | `seat` | `P-ADM-13`, pre-showtime only |
| `seat.deactivated` | `seat` | `P-ADM-15` |
| `seat.reactivated` | `seat` | `P-ADM-15` |
| `manager.created` | `user` | `P-ADM-17` |
| `manager.screen_assigned` | `manager_screen_assignment` | `P-ADM-17` |
| `manager.screen_unassigned` | `manager_screen_assignment` | `P-ADM-17` |
| `language.created` | `language` | `P-ADM-23` |
| `certification.created` | `certification` | `P-ADM-23` |
| `genre.created` | `genre` | `P-ADM-23` |
| `format.created` | `format` | `P-ADM-23` |
| `language.withdrawn` · `language.restored` | `language` | `P-ADM-24` |
| `certification.withdrawn` · `certification.restored` | `certification` | `P-ADM-24` |
| `genre.withdrawn` · `genre.restored` | `genre` | `P-ADM-24` |
| `format.withdrawn` · `format.restored` | `format` | `P-ADM-24` |

**Every write this epic specifies has a member above.** Checked one by one, and recorded so the check
does not have to be repeated by eye: film create, edit, poster upload and replacement, display window,
publish and unpublish (`P-ADM-01` to `P-ADM-06`); showtime create, edit and base-price change
(`P-ADM-07`, `P-ADM-09`, `P-ADM-10`); seat-category create, rename and uplift change (`P-ADM-11`);
venue rename and zone change (`P-ADM-25`); screen create, rename, withdrawal and return to service
(`P-ADM-13`, `P-ADM-16`); seat create, edit,
delete, withdrawal and return to service (`P-ADM-13`, `P-ADM-15`); manager creation and every
assignment and unassignment (`P-ADM-17`); and the creation of a lookup vocabulary row of each of the
four kinds (`P-ADM-23`).

**The eight `*.withdrawn` / `*.restored` actions above have a writer**: `P-ADM-24`, through
`EP-ADM-27`. They were added when that endpoint was, and for the reason a vocabulary member without a
writer is a defect — it is indistinguishable from one whose writer was forgotten. **An action string
in this table and no endpoint that writes it, or an endpoint that writes an action not in this table,
are both defects.**

**Adding an action is a specification change**, not a handler detail. A write with no listed action is
a defect in this table or in the handler, and one of the two must be fixed before the write ships.

**Who may do it.** Written by the server on the admin's behalf. **Never by the admin directly** — there
is no endpoint that writes an audit row.

**Preconditions.** A privileged write is committing.

**Happy path.** The write and the audit insert are two statements in one transaction. They serialise
nothing that was not already serialised — the changes are on different rows and the audit inserts
append (`FR-ADR-019`).

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | The audit insert fails for any reason | the whole transaction rolls back; 500 `INTERNAL_ERROR` | "The server could not complete this request. If you need help, quote `a1b2c3d4`." |
| 2 | A write is attempted with an `action` not in the vocabulary | **the boundary check refuses it before the transaction opens.** Nothing is begun, so there is nothing to roll back; 500 `INTERNAL_ERROR` | the same |
| 3 | An `UPDATE` or `DELETE` on `audit_log` from the application role | the database refuses; 500 `INTERNAL_ERROR` | the same |

**Exception 1 is the load-bearing one and it is stated in the direction that matters: the change fails
because the audit failed, never the reverse.**

**Exception 2 was published as a rollback and it is a boundary check, and the two are different code.**
This row read *"the transaction rolls back"* while `E8 P-XCT-03` exception 4 and its validation
paragraph both place the check **before the transaction opens**. **`E8`'s is the one adopted, because
it is the stricter of the two**: a non-member `action` never reaches a `BEGIN`, so a partially applied
change is impossible **by construction** rather than by a rollback that has to work. Adopting the
stricter option needs no signature (Art III.10). **The observable answer is identical** — 500, nothing
written — which is exactly why it could sit wrong for so long: the two readings differ only in whether
a transaction was ever opened, and no response distinguishes them. **A rollback is a mechanism that
can fail; a check that runs first is a mechanism that cannot be reached.**

**A non-member `action` is a programming error and not a runtime condition.** The vocabulary is fixed
in this document, not in data, so the check compares a value the handler chose against a closed list.
It can only fail if a handler was written with a string this table does not carry — which is the case
the check exists to catch loudly, at the boundary, on the first request that runs it.

**Three different sentences were published for these three rows and there is one code, so there is one
sentence.** This row previously published *"Something went wrong and nothing was saved. If you need
help, quote `a1b2c3d4`."* and `E8 P-XCT-03` exception 1 published *"That change was not saved. Try
again."*, against the registry's own `INTERNAL_ERROR` copy — *"The server could not complete this
request. If you need help, quote `a1b2c3d4`."* — which `E8 P-XCT-03` exception 3 already used.
**Three answers for one code, and an implementer had to pick.** The registry's wins: `E8`'s error
banner publishes the string for the code, it **does not defer for `INTERNAL_ERROR`** the way it
explicitly defers for `FORBIDDEN` and `AUTH_REQUIRED`, and **a new variant of an existing sentence is
a defect rather than a refinement** (`P-ADM-12`). **This section now publishes no `INTERNAL_ERROR`
wording of its own, anywhere** — the four places it carried the variant all render the registry's
string.

**"Try again" was also the wrong instruction, independently of which sentence wins.** Every one of
these three triggers is a fault in the server or its grants; retrying the identical request reproduces
it. The registry's sentence gives the admin the **request id** instead, which is the only thing that
leads anywhere: it joins the audit row's `request_id` to the log lines (`FR-ADR-056`).

**Server-side validation.** `action` is checked against the vocabulary above **at the boundary, before
the transaction opens** (exception 2, and `E8 P-XCT-03`, which states the same ordering).
`actor_user_id` must be non-null **and must resolve to a real `user` row — never a role name and never
a service account**, which is why nothing in this product writes an audit row on anyone's behalf but
the acting admin's. `request_id` must be present.

**The vocabulary's closure was checked rather than asserted.** Every `<entity>.<verb>` string in all
nine section files was enumerated and compared against the table above: **every one is a member**, and
there is no action string anywhere in the PRD that this table does not carry. **One near-miss is named
so it is not re-raised**: `receipt.send` (`E4 P-TKT-05`) looks like an action and is **not** one — it
is an `outbox_message.topic`, a different column in a different namespace, and it never reaches
`audit_log.action`. **The other near-miss is deliberate**: `showtime.price_changed` appears in this
section exactly once, in the warning above, saying that it is not a member.

**The surface that reads `audit_log` is Phase 8 and is not specified in this section.** The rows are
written from Phase 2, because an audit trail that starts when its reader is built has a hole in it
exactly as long as the build took (`FR-ADR-019`).

**`audit_log` will be the largest table in this system and it never shrinks.** That is the intended
cost of `FR-ADR-012` and it belongs in the runbook as a figure to watch, not as an alarm nobody
configured.

---

### `P-ADM-20` · Nothing is ever deleted, and withdrawal replaces deletion everywhere · `RULED` · reserved: legal
`[SRC: SRC-003 OPEN-OPS-02 · SRC-001 §7.6 · SRC-001 §6.6 · FR-ADR-012 · FR-ADR-021 · FR-ADR-022]`
`[BRD: R-ADM-07]`

**Behaviour.** The client ruled retention as *"for now forever we'll change that later if i ask"*
(`SRC-003 OPEN-OPS-02`). That removes deletion from this system's vocabulary. **No pruning job, no
retention window, and no scheduled anything to hang one on** (`FR-ADR-005`, `FR-ADR-012`).

**What "withdraw" means, per entity. This table is `R-ADM-07` and it is the answer a developer needs.**

| Entity | Withdrawal is | What a historical booking still resolves to |
|---|---|---|
| **Film** | `published_at` set to null (`P-ADM-06`), and/or a display window that has lapsed (`P-ADM-04`) | the **same `movie` row**, read directly. The customer's booking list and their receipt name the real title, poster and runtime. The visibility predicate governs the **browse** surface only, never the booking record (`FR-ADR-021`) |
| **Hall** | `screen.is_active = false` (`P-ADM-16`) | the **same `screen` row**. The receipt names the real hall. The dashboard's historical figures still attribute to it |
| **Seat** | `seat.is_active = false` (`P-ADM-15`) | the **same `seat` row**, with its original `row_label` and `seat_number` — which is why `P-ADM-14` freezes them. The receipt names the seat the customer actually sat in |
| **Seat category** | not withdrawn; a category simply has no seats pointing at it. Its `uplift_basis_points` at the time is snapshotted on `booking_seat` anyway (`FR-ADR-039`) | the **same `seat_category` row**, plus the snapshot, so the figure reconstructs itself |
| **Showtime** | **nothing. There is no withdraw-showtime capability in v1** | — see `P-ADM-21` |
| **Manager assignment** | the row **is** removed — it is current state, not the historical record (`FR-ADR-011`) | the `audit_log` rows for `manager.screen_assigned` / `manager.screen_unassigned` carry the history |
| **Poster object in S3** | not withdrawn and not deleted. A replaced poster's object stays (`FR-ADR-061`) | an `audit_log` `before` value that still resolves to a real image |

**No foreign key on any path that can reach a booking uses `ON DELETE CASCADE`.** The default for every
relationship is `ON DELETE RESTRICT` (`FR-ADR-012`). **A cascade is a delete that happens without
anyone writing the word delete.**

**The only deletions this epic performs**, both scoped to current state and neither reaching a booking:

1. A **seat** on a screen that has **no showtime row at all** (`P-ADM-13`, permitted by `FR-ADR-022`).
2. A **`manager_screen_assignment` row** (`P-ADM-17`, permitted by `FR-ADR-011`).

**Nothing else, anywhere in this epic, issues a `DELETE`.**

**Who may do it.** Withdrawal is admin only (`P-ADM-18`).

**Preconditions and happy paths** are those of `P-ADM-06`, `P-ADM-15` and `P-ADM-16`.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | A `DELETE` of a film, a showtime or a screen is attempted at any address | **405 `METHOD_NOT_ALLOWED`** — no route is entered, because none is mounted | **the one generic, entity-blind sentence `E8` publishes with the code.** This row publishes no wording of its own: nothing has been entered that knows which entity was addressed |
| 2 | A seat delete on a screen that has showtimes | 409 `LAYOUT_FROZEN` | as `P-ADM-14` exception 3 |

**Exception 1 was `403 FORBIDDEN` with an entity-naming sentence, and that was a contradiction inside
this row.** The validation paragraph below says no delete route exists and that **the absence is the
control** — and a route cannot return a `403` with a message about films unless it exists, has been
matched, and has run. Both could not be true. **The absence wins**, and the mechanism that keeps
`FR-ADR-052`'s single envelope is a **global handler, not a route**: the application renders the
framework's method-not-allowed as the product envelope, so every failure still answers in one shape
while **no `DELETE` route is mounted for any entity this row says is never deleted**. `E8` specifies
that handler alongside the envelope (`P-XCT-11`) and registers `METHOD_NOT_ALLOWED` at 405.

**The scope of "no route is mounted" is exactly the never-deleted set, and the exception is not an
oversight.** `EP-ADM-21` **is** a mounted `DELETE`, on a seat, and it is the one this epic performs —
permitted only while the hall has no showtime row at all, refused `409 LAYOUT_FROZEN` once one exists
(`FR-ADR-022`, and the two deletions listed above). A mounted route that refuses a real request with a
real reason is a different thing from a route mounted only to say no: **the first has a case where it
succeeds.** So `movie`, `showtime`, `screen`, `cinema` and every lookup table have no `DELETE` path at
any address, and `seat` and `manager_screen_assignment` do — which is exactly the split the two
deletions above already draw.

**The message is generic and entity-blind, and that is the point rather than a shortfall.** An
unmounted route does not know whether the caller addressed a film, a hall or a lookup row, and a
specification that publishes "Films are never deleted…" from one is describing something that cannot
run. **The entity-specific sentences are not lost — they move to the screens**, into the never-deleted
note each admin screen carries (`SCR-ADM-02` for films, `SCR-ADM-03` for showtimes, `SCR-ADM-05` for
halls and seats, `SCR-ADM-07` for the lists, `SCR-ADM-08` for the venue). That is where an admin
actually reads them, because **the interface offers no delete control to press**, so no admin ever
reaches the 405 by using the product. Only a hand-made request does, and a hand-made request is served
by the envelope and not by prose.

**Every delete-refusal row in this section now says the same thing** — `P-ADM-13` exception 11,
`P-ADM-16` exception 4, `P-ADM-23` exception 7, `P-ADM-24` exception 6 and `P-ADM-25` exceptions 6 and
7 — where before there were five different messages and three different statuses across them.

**Server-side validation.** No delete route exists for `movie`, `showtime` or `screen`. **The absence
is the control**; a route that returns 403 for everybody is a route somebody will later make work.
There is nothing to validate, because nothing is entered: routing itself is the refusal.

**Stated plainly.** **Storage grows without limit by design**, against a 20 GB free-tier RDS volume
(`SRC-002 §5.2.2`). At six halls and one venue that is far from a problem, and it is the kind of thing
that is invisible until it is urgent, so it belongs on the operator's list of figures to watch
(`FR-ADR-012`). *(reasoned from the free-tier figure, not observed — nothing has run in AWS.)*

**Excluded is not blocked** (`SRC-001 §6.6`). Nothing here makes a later retention window impossible —
it would be a new decision, and deleting historical bookings would be a one-way door and reserved.

---

### `P-ADM-21` · Withdrawing a showtime that already has paid bookings · **`OPEN`** · reserved: money, irreversible
`[SRC: SRC-003 OPEN-SHOWCANCEL-01 · SRC-003 OPEN-OPS-03 · SRC-003 OPEN-CANCEL-01 · SRC-003 OPEN-CANCEL-02 · FR-ADR-023 · FR-ADR-013 · FR-ADR-035]`
`[BRD: R-ADM-08]`

> **This row decides nothing. It exists so the gap is visible, traceable, and stated to the client
> rather than left to be found.**

**The question, stated so it can be answered in one message:**

> An admin withdraws a showtime that already has confirmed, paid bookings. **What happens to those
> bookings, and what happens to the money?**

**Why it is open.** Two of the client's own rulings point in different directions.
`SRC-003 OPEN-OPS-03` lists what only the admin may do: *"changes in movie, **cancel a show** or other
priviledged things"* — so cancelling a show is a **named admin capability**. `OPEN-CANCEL-02`, asked
what happens when the cinema cancels a show and whether refunds are automatic, answered *"no forget
this"*, and `OPEN-CANCEL-01` answered *"no refund policy"*. Those customers have paid. Either they are
refunded, which contradicts a ruling, or they have paid for a screening that will not happen and
receive nothing — **which is a decision about money that no model may make** (`FR-ADR-023`,
`CONSTITUTION.md` Art III.8).

**What this specification says, and it is the whole of it.**

**There is no withdraw-showtime capability in FrontRow v1.**

- **No endpoint.** No `DELETE`, no `POST /withdraw`, no `PATCH` that sets a withdrawal state.
- **No screen and no control.** `SCR-ADM-03` has no withdraw action and no disabled one.
- **No column.** The `showtime` row carries **no `withdrawn_at` and no cancellation state**
  (`FR-ADR-023`), because a column implies a capability that is not built.
- **No refund path, no customer notification, and no wording for one.** None is designed and none is
  hinted at.
- **The nearest legitimate actions are different actions and the interface says so**: unpublishing the
  film (`P-ADM-06`) removes it from the browse surface and cancels nothing; taking the hall out of
  service (`P-ADM-16`) stops new showtimes and cancels nothing.

**This is the fail-closed position under Art III.1: an unbuilt capability is recoverable, an unrefunded
customer is not.** It is **the only capability the client named in `OPEN-OPS-03` that v1 does not
deliver**, and saying so here is the point of this row.

**What is already in place for whichever way the client answers.** `FR-ADR-013` keeps `status` and
`cancelled_at` on the `booking` row and **no v1 endpoint exposes them**, so options that cancel
bookings need **no migration on live data** whenever the client decides (`FR-ADR-023`). That is why
those columns exist.

**One further thing is blocked on this row and is recorded rather than resolved:** what a withdrawal
would do to **live seat holds and in-flight checkouts** on that showtime. `FR-ADR-035` states that it
is blocked on `FR-ADR-023` and does not pretend to resolve it. The case cannot arise in v1 because the
capability does not exist.

**Who may do it.** Nobody. There is nothing to do.

**Preconditions, happy path, validation.** None. **Escalate, never invent.**

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | Any request to a withdraw-showtime address | 404 `NOT_FOUND` | "That page does not exist." |

The address does not exist and returns the same answer as any other address that does not exist. **No
message is written for a customer whose showtime was withdrawn**, because there is no such customer and
writing the sentence would be inventing the policy.

---

### `P-ADM-22` · Demonstration content is obviously demonstration content · `RULED`, under a standing `OPEN` constraint
`[SRC: SRC-003 OPEN-ATTRIB-01 · SRC-003 OPEN-SEED-01 · SRC-003 OPEN-TMDB-01 · FR-ADR-007 · FR-ADR-067]`
`[BRD: R-ADM-01]`

**Behaviour.** **`OPEN-ATTRIB-01` is an open Article X row**: if the posters and titles the client
supplies come from TMDB or any other licensed source, an attribution obligation applies even though the
API integration is gone. It is a licence question, reserved to the client, and the build session may
not close it (`FR-ADR-007`).

**The standing constraint until it closes** (`CONSTITUTION.md` Art VI.10): **no licensed image, title
or synopsis enters this product from the build session, anywhere.** That includes seed data, test
fixtures, screenshots, documentation examples and every example in this document.

**What that means concretely for this epic:**

- **Seeded films are obvious placeholders**: `DEMO MOVIE 01`, `DEMO MOVIE 02` and so on
  (`SRC-003 OPEN-SEED-01`, `FR-ADR-067`). They could never be mistaken for real content.
- **Seeded films are published and carry a placeholder poster.** They exist to give showtimes something
  to point at (`FR-ADR-021`, `FR-ADR-067`) **and to make the product demonstrable on the first run**.
  `P-XCT-30` owns what the seed does; this row states only the constraint it works under.
- **The seed script invents no film artwork and fetches no image from anywhere.** The placeholder is a
  single asset committed to the repository and shared by all eight seeded films — a flat
  design-system shape carrying no artwork and no text that could be read as a title.

**This paragraph was the sentence that made the demonstrable state unreachable, and it is corrected
rather than quietly edited.** It previously read *"Seeded films carry no poster and are not
published."* `P-ADM-05` refuses publication without a poster, so a seeded film could never become
visible; a seed followed by `docker compose up` produced a customer landing page reading that nothing
was showing, and three rows elsewhere — including a browse worked example that derives which filter
controls render — assert the opposite. **The old sentence was the defect.**

**`OPEN-ATTRIB-01` is untouched by this, and the distinction is the whole reason the change is safe.**
That row is about **real** posters, titles and synopses and the licence attached to them. A flat shape
authored by the build session, committed to this repository, carrying no artwork and depicting nothing,
is neither licensed nor mistakable for a real poster — it is the visual equivalent of `DEMO MOVIE 01`.
**The standing constraint above is unchanged in every word: no licensed image, title or synopsis enters
this product from the build session.** What narrowed is `P-XCT-30`'s *"generates no image of any kind,
from anywhere"*, which now reads *invents no film artwork and fetches no image from anywhere* —
the constraint that was actually meant, since the prohibition exists to keep unattributed artwork out
and not to forbid a shape in a stylesheet. **The narrowing is named here rather than left to be
inferred**, because a reader comparing the two sentences across a merge would otherwise read it as a
rule quietly relaxed.
- **The client supplies real posters and titles themselves**, through `P-ADM-01` and `P-ADM-03`. That
  is what the whole admin authoring surface is for.
- **No provenance or attribution field is added to the `movie` row speculatively** (`FR-ADR-007`,
  `FR-ADR-021`). If the row closes in a direction that requires attribution, the poster-serving
  redirect endpoint is where a check would live and the `movie` row is where the field would go.
  Neither is built now.

**Who may do it.** Not an action — a constraint on every spec in this section.

**Exception paths.** None. It is a rule about what is written, not a runtime path.

**Server-side validation.** None. **Nothing in the system enforces this and nothing can** — the admin
can type any title they like, and that is correct, because the client is the admin and the material is
theirs to supply. The constraint binds the build session, not the product.

---

### `P-ADM-23` · Create the lookup vocabularies a film is built from · `RULED`
`[SRC: SRC-001 §5.1.1 · SRC-001 §5.1.3 · SRC-003 OPEN-TMDB-01 · SRC-003 OPEN-OPS-02 · SRC-003 OPEN-OPS-03 · FR-ADR-021 · FR-ADR-012 · FR-ADR-019]`
`[BRD: R-ADM-01]`

**Behaviour.** `P-ADM-01` refuses to create a film unless the `language`, the `certification` and every
`genre_id` it names already exist as rows, and the browse surface needs `format` rows before its format
filter can return anything. **Something has to create those rows on a database that has none, and this
is it** — what a *seeded* database starts with is `P-XCT-30`'s, and this row defers to it below. The
admin creates each vocabulary entry by hand, exactly as they create everything else in this epic.

**Why one generic surface and not four near-identical CRUD sets.** All four vocabularies are the same
shape — an id, a name, a service flag — and all four are read by the same form. Four sets of two
endpoints would be eight blocks differing only in a path segment, and each would be a place for the
four to drift apart. **This is a build-session judgment under Art III.9**; nothing is reserved about
the shape of an admin CRUD surface.

**`{kind}` is a closed set of exactly four values**, and each maps to one table:

| `{kind}` | Table | Referenced by |
|---|---|---|
| `language` | `language` | `movie.language_id` (`P-ADM-01`); `SRC-001 §5.1.3` makes it a customer filter |
| `certification` | `certification` | `movie.certification_id` (`P-ADM-01`) |
| `genre` | `genre` | the `movie_genre` join rows (`P-ADM-01`) |
| `format` | `format` | **`showtime.format_id`, which this epic does own** (`P-ADM-07` writes it, `SCR-ADM-03` carries the control, `EP-ADM-10` and `EP-ADM-11` accept it), and the browse surface's format filter, which is another epic's. The field is **optional**, so a FrontRow with no format rows at all still works — every showtime simply answers `null` and no format filter returns anything |

**A `{kind}` outside those four is an address that does not exist**, and it answers `404 NOT_FOUND`
like every other address that does not exist. It is not `422`: the value is a path segment, not a
submitted field, and a caller who guessed a fifth vocabulary has not made a validation mistake — they
have asked for a page that is not there.

**Who may do it.** **admin only**, by the router dependency (`P-ADM-18`). A manager reading a
vocabulary would still be a manager reading a write-router, so the read lives here too and returns 403
for anyone but an admin.

**Preconditions.** None beyond the caller being an admin.

**Happy path.**
1. The admin opens `SCR-ADM-07` and chooses one of the four vocabularies.
2. The admin types a name and submits.
3. The server checks the name against the uniqueness rule below.
4. In one transaction the server inserts the row with `is_active = true` and inserts one `audit_log`
   row with `action = "<kind>.created"`, `before = null`, `after = {"name": "<name>"}` (`P-ADM-19`).
5. The server returns 201 with the created row and its id.
6. The film editor's select for that vocabulary now offers it (`SCR-ADM-02`).

**What a row carries.** The same four fields in all four tables:

| Field | Holds |
|---|---|
| `id` | integer identity, the value `P-ADM-01` stores on the film |
| `name` | the displayed text. This is the only thing the admin types |
| `is_active` | boolean, `true` on creation. See withdrawal below |
| `created_at` | `timestamptz`, UTC |

**There is no description, no sort order, no code, no colour and no icon.** No source asks for one, and
`SRC-001 §6.6` means adding a column later is a migration and not a redesign.

**Uniqueness.** `lower(trim(name))` is unique **within one vocabulary**, enforced by a unique index and
not by a prior read — the index is the guard, exactly as it is on a seat label (`P-ADM-13`) and on an
email address (`E5 P-ACC-01`). Two vocabularies may hold the same string: a `genre` called `Drama` and
a `format` called `Drama` are two unrelated rows and neither collides with the other.

**The normalisation is not specific to a select, and it is not specific to this row.** Every name this
epic makes unique is unique on `lower(trim(name))`: a **seat category** (`P-ADM-11`), a **hall**
(`P-ADM-13`, within its venue), a **venue** (`P-ADM-25`), and each of the four vocabularies here. The
reason above carries across unchanged — **two entries a person cannot tell apart are two entries a
person will pick the wrong one of** — and for a seat category it reaches further than a select: the
category is the primary non-colour carrier of price band on the seat map, so `Premium` and `premium`
coexisting would draw **two legend rows on every seat map** for what a customer reads as one category.
That is a customer-visible wrong rather than an admin inconvenience, which is why the rule is stated
once here and cited by the three rows rather than left to each of them.

**Withdrawn rows participate in the unique index.** A withdrawn `Drama` **blocks** a new `Drama`, and
this is deliberate: the alternative puts two rows in the table that a person reads as one name, which
is the exact thing the index exists to prevent — and the withdrawn one is still displayed by every film
that carries it (`P-ADM-24`), so both would be visible at once. **The remedy is to restore the
withdrawn row, not to create a second one**, which is what `P-ADM-24`'s restore control on
`SCR-ADM-07` exists for, and the refusal says so in its own words rather than leaving an admin to
work it out:

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 6b | A row with that name exists in this vocabulary **and is withdrawn** | 422 `VALIDATION_FAILED` | "That name is already on this list, on an entry that has been withdrawn. Restore that entry instead of adding it again." |

**Exception 6 keeps its own wording for the ordinary case**, where the existing row is active. The two
are one index and two sentences, because the remedy differs: one says pick another name, the other says
the name you want is already here and can be brought back.

**These rows are withdrawn, never deleted.** `FR-ADR-012` removes deletion from this system's
vocabulary and a film already points at these rows. **There is no delete endpoint and no delete route**
— the absence is the control (`P-ADM-20`). Withdrawal is `is_active = false`, and the column is on the
row from the first migration so that withdrawal is a later endpoint rather than a migration over rows
that films already reference.

**What withdrawing one would do, stated because the column exists and somebody will ask.** A withdrawn
row **stops being offered in `SCR-ADM-02`'s selects** and does nothing else. **Every film already
referencing it is unchanged and still resolves to the same row**, so a film whose language was
withdrawn still displays that language on every customer surface and on every past booking's record.
That is the same shape as a seat category with no seats pointing at it (`P-ADM-20`), and it is the
whole point of withdrawing instead of deleting.

**`is_active` is written by `P-ADM-24`, through `EP-ADM-27`.** It was added because a flag whose
meaning is specified and which nothing can ever set is a specification for a transition that cannot
occur — and because the need is concrete rather than hypothetical: an admin who mistypes `Hnidi` while
creating their first film would otherwise carry that entry in every language dropdown **permanently**,
since `FR-ADR-012` forbids deleting it. Withdrawal is the same treatment a seat gets in `P-ADM-15` and
a hall in `P-ADM-16`.

**Whether any starting rows exist. `P-XCT-30` owns the seeded inventory, and this row defers to it.**
Which language, certification, genre and format rows the seed creates, what they are called and how
they are assigned to the seeded films is stated there and **is deliberately not restated here** — a
second copy of that list in this section is a second thing to keep in step with the seed script, and
this section does not own the seed script. This row owns only what the *admin surface* does with
whatever it finds.

**What this section does state, and it is the operationally important half: the film form in
`SCR-ADM-02` cannot be completed until at least one row exists in every vocabulary that film needs** —
one language, one certification and at least one genre, because `P-ADM-01` requires all three. On a
database that has been migrated and **not** seeded there are none of any of them, so **the first thing
an admin does there is create those rows**, and `SCR-ADM-02` says so when a select is empty rather than
presenting an empty dropdown with no explanation. Nothing on this surface behaves differently
according to whether a row arrived from the seed or from an admin's keyboard: a seeded row is created,
withdrawn (`P-ADM-24`) and referenced by exactly the rules above, and every seeded row is
demonstration content under `P-ADM-22` and the standing `OPEN-ATTRIB-01` constraint.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | No session token | 401 `AUTH_REQUIRED` | "Sign in to continue." |
| 2 | Signed in as guest, customer or manager | 403 `FORBIDDEN` | "This page is for administrators. Your account cannot change films, showtimes, prices or halls." |
| 3 | `{kind}` is not one of `language`, `certification`, `genre`, `format` | 404 `NOT_FOUND` | "That page does not exist." |
| 4 | `name` empty or whitespace only | 422 `VALIDATION_FAILED` | "Enter a name of 1 to 60 characters." |
| 5 | `name` longer than 60 characters | 422 `VALIDATION_FAILED` | "Enter a name of 1 to 60 characters." |
| 6 | A row with that name already exists in this vocabulary | 422 `VALIDATION_FAILED` | "That name is already on this list. Every entry needs its own name." |
| 7 | A `DELETE` is attempted at any of these addresses | **405 `METHOD_NOT_ALLOWED`** — no route is mounted and none is entered (`P-ADM-20`) | `E8`'s one generic sentence for the code. The list-specific wording is `SCR-ADM-07`'s never-deleted note, which it already carries |
| 8 | Postgres unreachable | 503 `DEPENDENCY_UNAVAILABLE` | "The system cannot reach its database right now. Nothing was saved. Try again in a moment." |

**Server-side validation.**

| Field | Type | Bound | Provenance | On failure |
|---|---|---|---|---|
| `kind` (path) | string | exactly one of `language`, `certification`, `genre`, `format` | **derived** — `FR-ADR-021` makes language, certification and genre lookup tables, and the browse surface requires format rows the admin creates | exception 3 |
| `name` | string | 1..60 characters after trimming | **technical** | exceptions 4, 5 |
| `lower(trim(name))` | — | unique within the one vocabulary | **derived** — two entries a person cannot tell apart in a select are two entries a person will pick the wrong one of | exception 6 |
| `is_active` | boolean | `true` on creation; **not accepted from the request** | **derived** (`FR-ADR-012`: withdrawal replaces deletion; `P-ADM-24` is what sets it later) | **400 `REQUEST_INVALID`** if supplied — rejected, never dropped |
| `id` | — | **not accepted from the request.** Server-generated | **technical** | **400 `REQUEST_INVALID`** if supplied |

**Worked example — what the uniqueness rule catches and what it does not.**

```
Vocabulary: genre.  Existing row:  name = "Drama"

Submitted "Drama"    -> lower(trim(...)) = "drama"  == existing  -> 422, exception 6
Submitted "  drama " -> lower(trim(...)) = "drama"  == existing  -> 422, exception 6
Submitted "DRAMA"    -> lower(trim(...)) = "drama"  == existing  -> 422, exception 6
Submitted "Dramas"   -> lower(trim(...)) = "dramas" != existing  -> 201 Created

Vocabulary: format.  Submitted "Drama"
                     -> a different table, so no comparison is made -> 201 Created
                     Two unrelated rows in two unrelated vocabularies.
```

The stored value is what the admin typed — `"Drama"`, with its original case and no trimming beyond the
leading and trailing whitespace. **The lowercased, trimmed form is the comparison key and is never what
is displayed**, for the same reason `E5 P-ACC-01` compares an email on its lowercased form and stores
it as entered.

---

### `P-ADM-24` · Withdraw a lookup entry from future use, and restore one · `RULED`
`[SRC: SRC-003 OPEN-OPS-02 · SRC-003 OPEN-OPS-03 · SRC-001 §7.6 · FR-ADR-012 · FR-ADR-019 · FR-ADR-021]`
`[BRD: R-ADM-01 · R-ADM-06 · R-ADM-07]`

**Behaviour.** A lookup entry that should no longer be offered — a typo, a certification the country
stopped issuing, a format the cinema no longer runs — is marked `is_active = false`. It is **not
deleted, ever**, and it is **not renamed**.

**Why it must exist rather than being left out.** `P-ADM-23` gives `is_active` a meaning, and a flag
whose meaning is specified but which nothing can ever set is a specification for a transition that
cannot occur. It is also a real operational need: an admin who mistypes `Hnidi` while creating their
first film would otherwise carry that entry in every language dropdown **permanently**, because
`FR-ADR-012` forbids deleting it. This is the same treatment a seat gets in `P-ADM-15` and a hall in
`P-ADM-16`, for the same reason and by the same mechanism.

**Why renaming is refused rather than offered.** A rename would look kinder and is worse: films
already carrying the entry would silently change what they say they are, and a customer's past
booking would come to describe a film in a language it was never listed in. `SRC-001 §7.6` makes the
record answer for itself. **Correcting a typo means withdrawing the wrong entry and creating the right
one**, which leaves both facts visible in the audit trail.

**Who may do it.** The admin alone, enforced once by the `/api/admin` router dependency
(`P-ADM-18`). No manager, no customer, no guest.

**Preconditions.** A session held by an `admin`. `kind` is one of the four vocabularies. A row of that
vocabulary has that id.

**Happy path.**
1. The admin opens the vocabulary on `SCR-ADM-07` and withdraws an entry.
2. `PATCH /api/admin/lookups/{kind}/{id}` with `{"is_active": false}`.
3. **In one transaction** the server writes `is_active` and inserts the `audit_log` row
   (`P-ADM-19`) with `action = "<kind>.withdrawn"`, `before = {"is_active": true}`,
   `after = {"is_active": false}`, and the acting user and request id.
4. The entry disappears from every admin form's options from the next request onward.
5. **Every film already carrying it is untouched** — it still renders that language to customers, and
   a customer filtering by it still finds it.

**Restoring** is the same request with `true`, and writes `action = "<kind>.restored"`.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | `kind` is not one of the four | `404` `NOT_FOUND` — an address that does not exist, not a field that failed | "That page does not exist." |
| 2 | No row of that vocabulary has that id | `404` `NOT_FOUND`, identical to row 1 so the response does not reveal which ids exist | "That page does not exist." |
| 3 | `is_active` missing, or not a boolean | `422` `VALIDATION_FAILED` naming the field | "Choose whether this entry is in use." |
| 4 | `is_active` already holds the submitted value | `200`, nothing written, **no audit row** — an audit row whose `before` and `after` are identical is noise in the one table an operator reads to find real changes | *(nothing — the screen already shows that state)* |
| 5 | A rename is attempted by sending `name` | **`400` `REQUEST_INVALID`** — this address accepts only `is_active`, and an unknown property is rejected rather than dropped (the rule at the head of `S4`). **This row previously said the field was ignored**, which told a caller their rename had been accepted | "That request could not be understood. This address changes only whether an entry is in use." |
| 6 | A `DELETE` is attempted at this address | **`405` `METHOD_NOT_ALLOWED`** — no route is mounted and none is entered (`P-ADM-20`) | `E8`'s one generic sentence for the code. "Withdraw it instead" is on `SCR-ADM-07`, next to the Withdraw control that does the withdrawing |
| 7 | PostgreSQL is unreachable | `503` `DEPENDENCY_UNAVAILABLE`; nothing is written and no audit row exists | "This change could not be saved. Try again in a few minutes." |

**Server-side validation.** `kind`: one of `language`, `certification`, `genre`, `format` — matched in
the routing layer against a closed set and **never interpolated into a query**. `id`: integer,
positive, existing within that vocabulary. `is_active`: boolean, required. Every other property in the
body is rejected with `400 REQUEST_INVALID` rather than dropped.

**Worked example — withdrawing a language that films already use.**

```
Before:  language 7 = "Hnidi"  (a typo), is_active = true
         DEMO MOVIE 04 references language_id 7

PATCH /api/admin/lookups/language/7   {"is_active": false}

After:   language 7 = "Hnidi", is_active = false
         audit_log: action="language.withdrawn"
                    before={"is_active": true}  after={"is_active": false}

         The film form's language options   -> 7 is absent
         DEMO MOVIE 04                      -> still language_id 7, still renders "Hnidi"
         A customer filtering by "Hnidi"    -> still finds DEMO MOVIE 04

The correction is a SECOND action, not an edit:
         POST /api/admin/lookups/language  {"name": "Hindi"}   -> id 12, is_active true
         PATCH /api/admin/movies/{id}      {"language_id": 12} -> the film now says Hindi
```

**Both facts stay in the record**: the film was listed as `Hnidi` and was corrected, and the audit
trail says who did each and when. Nothing is rewritten to pretend the typo never happened.

**Phase.** 6, with the rest of admin movie management.

---

### `P-ADM-25` · The venue: one cinema row, seeded not created, and the admin surface that reads and edits it · `RULED` on the surface · `PROVISIONAL` on there being one
`[SRC: SRC-003 C-2 · SRC-003 OPEN-SCOPE-01 · SRC-003 OPEN-SEED-01 · SRC-001 §6.6 · SRC-003 OPEN-OPS-03 · FR-ADR-010 · FR-ADR-067 · FR-ADR-018 · FR-ADR-035 · FR-ADR-019]`
`[BRD: R-SEAT-07 · R-ADM-05]`

> ## ⚠ `PROVISIONAL` — one message from the client reverses this
> **One cinema with six screens** is a build-session reading reconciling two of the client's own
> answers (`SRC-003 C-2`, `FR-ADR-010`). `SRC-001 §1.1` says "We operate cinemas" — plural — and
> `§5.1.3` asks customers to filter by cinema; `OPEN-SCOPE-01` describes one theatre with six halls.
> **The rejected reading is several venues.** Nothing below makes a second venue impossible, and the
> paragraph on a second venue says exactly what it would cost.

**Behaviour.** The `cinema` entity is a real row with a name and an **IANA timezone name**. Every
`screen` carries a non-null `cinema_id` (`FR-ADR-010`), and `EP-ADM-16` requires one on creation.
**Until now no endpoint anywhere returned a cinema, so that required field had no source.** This row
adds the surface: **a list, and an edit of the name and the zone. There is no create and no delete.**

**Who may do it.** **admin only**, by the router dependency (`P-ADM-18`). A manager reads nothing here
— the venue is configuration, not a report, and `SRC-003 OPEN-OPS-03` puts every privileged write on
the admin alone.

**Preconditions.** For the edit: the cinema exists, and the submitted `version` matches.

**Happy path — reading.**
1. `SCR-ADM-08` calls `EP-ADM-28`, which returns every cinema with `id`, `name`, `timezone`,
   `screen_count` and `version`.
2. `SCR-ADM-05`'s hall form calls the same endpoint to populate its cinema control. **That is where
   `EP-ADM-16`'s required `cinema_id` comes from**, and it is why the control exists at all.

**Happy path — editing.**
1. The admin edits the name, the zone, or both, on `SCR-ADM-08`, and submits with `version`.
2. In one transaction the server compares the version, writes the changed columns, increments
   `version`, and inserts **one `audit_log` row per kind of change**: `cinema.updated` for a rename
   and `cinema.timezone_changed` for a zone change (`P-ADM-19`). A submission that changes both writes
   both rows, in one transaction, because a rename and a zone change are not the same event and
   collapsing them makes the change log unable to answer which one happened.
3. The server returns 200 with the new `version`.

**There is no endpoint that creates a cinema, and that is a decision rather than an omission.**

- **The seed creates the one row.** `scripts/seed.py` inserts a single cinema named `DEMO CINEMA` with
  `Asia/Kolkata` as its zone (`FR-ADR-067`). That is where the row comes from in every environment,
  including the deployed one, where running the seed is the client's own documented action.
- **A second venue is a scope change and is the client's to decide.** It is not a technical question:
  a one-venue product renders no customer-facing cinema filter (`FR-ADR-046`), scopes managers by
  screen rather than by venue (`FR-ADR-011`), and shows one dashboard scope. Adding a second row
  changes what the product is, which `R-CON-11` reserves to the client. **The build session does not
  add an endpoint that would let one appear by accident.**
- **The interim position is fail-closed and it matches `P-ADM-17`'s.** No endpoint creates a cinema;
  a second row is a deliberate database action the client performs, exactly as a second admin account
  is. Raised as `PROPOSED-CINEMA-01` in the Lane notes rather than filled in here.

**What is deliberately kept open, because `SRC-001 §6.6` binds.** Nothing above is written as though
one venue were a fact:

| Kept | Instead of |
|---|---|
| `EP-ADM-28` returns an **array**, with `screen_count` per row | a `GET /api/admin/cinema` singular that returns one object and has to be replaced |
| `EP-ADM-29` is keyed on `{cinema_id}` in the path | an endpoint with no id that edits "the" cinema |
| `EP-ADM-16` keeps `cinema_id` **required** on hall creation | defaulting it server-side to the only row, which works exactly until there are two |
| `SCR-ADM-05` renders a cinema control | inferring the venue, which cannot be corrected when it is wrong |
| the **zone lives on the row**, per venue (`P-ADM-26`) | one global zone, which is wrong the moment a second venue sits in another state |

**A second venue therefore costs one insert and no migration** (`FR-ADR-010`), and no code path in
this epic has to be unpicked to allow it.

**The cinema control on `SCR-ADM-05` renders even with one option.** It is not hidden and it is not
pre-selected-and-removed. An admin creating a hall is choosing which venue it belongs to, and a
control that disappears when there is one choice is a control that reappears in an unfamiliar place
on the day there are two. The customer-facing filter is a different question and is decided elsewhere
(`FR-ADR-046`) — **the entity existing does not oblige any interface to render a one-option dropdown**,
and the admin form rendering one is a choice made here for the reason above, not an inheritance.

**Deleting a cinema is impossible** (`P-ADM-20`, `FR-ADR-012`). Screens reference it, showtimes reach
it through their screen, and every booking reaches it through its showtime. **There is no withdraw
control either**, and none is designed: no source asks what a withdrawn venue would mean for the
showtimes on it, and inventing an answer would be the same failure `P-ADM-21` refuses.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | Not an admin | 403 `FORBIDDEN` | "This page is for administrators. Your account cannot change films, showtimes, prices or halls." |
| 2 | No cinema with that id | 404 `NOT_FOUND` | "That venue no longer exists at this address." |
| 3 | `name` empty, too long, or already used | 422 `VALIDATION_FAILED` | "Enter a venue name of 1 to 120 characters." / "A venue with that name already exists." |
| 4 | `timezone` is not a name the zone database resolves | 422 `VALIDATION_FAILED` | "That is not a time zone this system recognises. Enter an IANA zone name, such as Asia/Kolkata." |
| 5 | `version` does not match | 409 `VERSION_CONFLICT` | "This venue was changed by someone else while you were editing. Reload to see the current details, then make your change again. Nothing you typed has been saved." |
| 6 | A create is attempted at `POST /api/admin/cinemas` | **405 `METHOD_NOT_ALLOWED`**, no endpoint is mounted (`P-ADM-20`) | `E8`'s one generic sentence for the code. **This row published a venue-specific string, which an unmounted route cannot emit**; that sentence is now `SCR-ADM-08`'s |
| 7 | A `DELETE` is attempted | **405 `METHOD_NOT_ALLOWED`**, no endpoint is mounted (`P-ADM-20`) | `E8`'s one generic sentence for the code. The venue-specific wording is `SCR-ADM-08`'s never-deleted note |

**Server-side validation.**

| Field | Type | Bound | Provenance | On failure |
|---|---|---|---|---|
| `name` | string | 1..120 characters after trimming; **unique on `lower(trim(name))`** | **technical** bound — a column needs one and no source states it; longer than a hall's 60 because a venue name carries a place. The normalisation is **derived** (`P-ADM-23`) | exception 3 |
| `timezone` | string | 1..64 characters, and **must resolve in the zone database at validation time** | **derived** — `FR-ADR-018` stores the zone name and converts through the zone database, so a name that does not resolve makes every date comparison for that venue fail at use rather than at entry | exception 4 |
| `version` | integer | must equal the stored value | **ruled** for the mechanism (`FR-ADR-035`); the entity is a stricter extension, see `P-ADM-12` | exception 5 |

**The zone is validated against the zone database and not against a list typed into this document.**
A hardcoded list of acceptable zones is a list that goes stale when the zone database is updated, and
`FR-ADR-018` already requires every conversion to go through that database rather than through a
fixed `+05:30`.

**Changing a venue's zone is a large change and the screen says so** (`P-ADM-26`). It does not rewrite
a single stored instant — every instant is UTC and stays exactly what it was — but **it changes what
every one of them is displayed as**, and it moves the boundaries of every dashboard period. The
confirmation states that, with the count of showtimes whose displayed time will move.

**Phase.** 2, with the data model and the first admin CRUD. It is early because `EP-ADM-16` cannot be
called without it and every hall in the system is created through `EP-ADM-16`.

---

### `P-ADM-26` · The cinema row is the only authority for local time; `CINEMA_TIMEZONE` seeds it and validates at boot · `RULED`
`[SRC: SRC-003 OPEN-LOCALE-01 · SRC-001 §5.1.4 · SRC-001 §7.6 · FR-ADR-018 · FR-ADR-010 · FR-ADR-067 · FR-ADR-053]`
`[BRD: R-PRC-01 · R-RPT-01]`

**Behaviour.** Two places in this product hold a timezone: **the `cinema` row's `timezone` column**,
and **the `CINEMA_TIMEZONE` environment variable** in the configuration inventory (`E8 S7.9`, which
owns the inventory). Four separate rows across this document require the zone to be read "from the
cinema row, never from a global constant", and **nothing said which of the two wins or what the
variable was for.** This row says both.

**The rule, in one sentence: at read time the cinema row wins, always, and no request-path code reads
`CINEMA_TIMEZONE`.**

**This is ruled, not chosen here.** `FR-ADR-018` decided it and recorded the alternative it rejected
in those words: *"Put the zone in application configuration rather than on the cinema row. Rejected as
the weaker option. It works exactly until there are two cinemas, and it makes the zone invisible in
the data — an operator reading the database cannot tell what 14:00 UTC means."* This row is that
record's consequence, not an amendment to it (`S1.2a`).

**What `CINEMA_TIMEZONE` is actually for.** Two things, and neither of them is rendering:

1. **It is the value the seed writes into the cinema row when it creates it** (`FR-ADR-067`,
   `P-ADM-25`). After that insert the variable has done its job for that venue, and changing it later
   does not change the row. **The row is edited through `EP-ADM-29`, not through the environment.**
2. **It is the subject of a boot check** that the name resolves in the zone database. `E8 S7.9` owns
   that check and the reason for it: an invalid zone name otherwise fails at the first date comparison
   rather than at boot, and a wrong one puts "today's showtimes" on the wrong day.

**No code on a request path reads `CINEMA_TIMEZONE`.** Stated in a form that can be checked rather
than believed: **outside the seed script and the boot-time configuration check, the string
`CINEMA_TIMEZONE` appears nowhere in the application.** A search that finds it in a handler, a query,
a renderer, a report or a template has found a defect. This is the whole of the enforcement, and it is
deliberately mechanical — the alternative is a convention that holds until the first person who needs
a zone and has a variable to hand.

**What happens if they differ.**

| Situation | What happens |
|---|---|
| The row's zone and `CINEMA_TIMEZONE` are equal | Nothing. This is the ordinary state after a seed. |
| They differ | **The row wins, silently for correctness and loudly for the operator.** Every conversion uses the row. The process logs **one `WARNING` line per differing row at boot**, naming `cinema_id`, the row's zone and the variable's value. |
| There is no cinema row at all | One `WARNING` at boot saying the venue has not been seeded. Nothing else — this is the ordinary state of a database that has been migrated and not yet seeded. |
| `CINEMA_TIMEZONE` is unset or does not resolve | The boot check owned by `E8 S7.9` refuses to start the process. That is a check on the **variable**, and it is unchanged by this row. |

**The boot check reads and never writes.** It does not reconcile the two values, does not update the
row from the variable, and does not update the variable. **A boot step that wrote the row would make
an environment variable able to change what every stored time means**, which is precisely the failure
this row exists to prevent. It runs no migration (`SRC-002 §7.8`).

**It does not fail the boot, and that is a judgment with its reason stated.** `[JUDGMENT CALL]` — the
build session's under Art III.9. Refusing to start on a mismatch would let a stale environment
variable take a running cinema offline, and the variable is the value the row does **not** depend on.
A warning that names both values gives the operator everything they need to fix whichever is wrong.
**It does not change what `/health/ready` reports** (`E8 S7`), because a mismatch is not a dependency
failure.

**With a second venue the variable stops meaning anything, and that is the design working.** Zones are
per row. A second cinema in another state carries its own zone in its own column and needs no
configuration change, no redeploy and no new variable — which is the reason `FR-ADR-018` put the zone
in the data in the first place.

**Where the row's zone is read.** Everywhere a local time is produced or consumed. This row does not
list those places, because a list here would be a fourth copy of facts other rows own — `P-ADM-04`'s
display window, `P-ADM-07`'s showtime entry, `P-ADM-05`'s visibility predicate, and the dashboard's
period boundaries each state their own conversion and each cites `FR-ADR-018`. **What this row adds is
that all of them resolve the zone the same way: one read of the cinema the screen belongs to.**

**A showtime reaches its zone through its screen's cinema.** `showtime → screen → cinema.timezone`.
There is no zone column on a showtime and none on a screen, because two rows holding one fact drift
the first time one of them is corrected (`FR-ADR-018`).

**Worked example — the same instant, under two zones, and why nothing is rewritten.**

A showtime is stored as `starts_at = 2026-08-14T14:00:00Z`. The venue's zone is `Asia/Kolkata`.

```
Displayed:   2026-08-14 19:30   (UTC+05:30, fixed; India observes no daylight saving)

An admin corrects the venue's zone to Asia/Colombo (also UTC+05:30):
  starts_at   UNCHANGED  2026-08-14T14:00:00Z
  Displayed   UNCHANGED  2026-08-14 19:30

An admin sets the venue's zone to Asia/Dubai (UTC+04:00) instead:
  starts_at   UNCHANGED  2026-08-14T14:00:00Z      <- not one stored row is rewritten
  Displayed   2026-08-14 18:00                     <- every displayed time moves by 90 minutes
```

**The stored column never moves and the rendered value does.** That is why a zone change is a
confirmed action on `SCR-ADM-08` with the count of affected showtimes stated, and it is also why it is
not dangerous in the way a currency-unit change would be: no past figure is reinterpreted, only
re-rendered. **The minor-unit ratio is the one-way door** (`FR-ADR-036`, `R-PRC-01`); the zone is not
one, and this row says so rather than leaving the two to be treated alike.

**And the failure the boot warning exists to catch.**

```
cinema row       timezone = "Asia/Kolkata"
CINEMA_TIMEZONE  "UTC"                        <- a deployed environment configured from a default

Renders:         the cinema row wins. "Today" is a day that starts at 18:30Z. Correct.
Logs at boot:    WARNING cinema_id=1 row_timezone="Asia/Kolkata" CINEMA_TIMEZONE="UTC"
```

**The product is correct and the operator is told anyway**, because a configuration value that is
ignored is a configuration value someone will later change and expect to take effect.

**Phase.** 2, with `P-ADM-25`.

---

## S5 — UX specification

Every screen below sits behind the admin router dependency (`P-ADM-18`). A customer or a manager who
reaches any of these addresses gets the 403 of `P-ADM-18` exception 2 or 3; a signed-out visitor gets
the 401. **Nothing here is reachable by hiding a link.**

All eight screens inherit `COMPONENTS.md §0`: the page frame, focus (`§0.2` — `--fr-focus-ring` at
`--fr-stroke-bold` with a 2px offset, never removed), numbers in `--fr-font-mono` with tabular figures
(`§0.3`), and money rendered from integer paise at the last possible moment (`§0.4`). Forms are
`COMPONENTS.md §11`; failures use the error banner of `COMPONENTS.md §6`, which **branches on the error
`code` and never on the message text**.

**Every admin form round-trips `version`** as a hidden value (`P-ADM-12`). A form that does not is a
form with no concurrency protection and no runtime signal that it lacks one.

---

### `SCR-ADM-01` · Film list
**Route.** `/admin/movies` · **Who reaches it.** admin only · **Component basis.** `COMPONENTS.md §3`, `§11`, `§6`

**What the user arrives with / leaves with.** Arrives with nothing. Leaves with either a new draft film
(to `SCR-ADM-02`) or an existing film opened for editing.

**Fields and controls.**

| Element | Token(s) | Behaviour | Validation |
|---|---|---|---|
| Page heading "Films" | `--fr-text-xl`, `--fr-ink-strong`, `--fr-font-display` | static | — |
| "New film" action | `--fr-surface-accent` / `--fr-ink-on-accent`, `--fr-radius-md`, min height `--fr-tap-min` | navigates to `/admin/movies/new` | — |
| Status filter — all / draft / published | `--fr-text-sm`; selected uses `--fr-surface-accent` / `--fr-ink-on-accent` | filters the list, server-side | — |
| Row: poster thumbnail | `--fr-poster-ratio` box on `--fr-surface-inset`; both poster-less states draw `--fr-poster-empty-mark` | reserves its box before the image arrives, so the list does not reflow. **Which words go in the box is decided by `poster_present`, never by the image having failed to arrive** — `EP-ADM-01` already returns the boolean, so the screen never infers one state from the other | — |
| Row: title | `--fr-text-md`, `--fr-weight-medium`, `--fr-ink` | opens `SCR-ADM-02` | — |
| Row: two gate marks — **Published** and **In window** | `--fr-text-xs`, `--fr-ink-muted`; the failing one carries `--fr-danger-ink` | **both are shown separately, always.** Never one combined "live" flag | — |
| Row: runtime, certification, language | `--fr-font-mono` for the runtime, `--fr-text-sm`, `--fr-ink-muted` | static | — |
| Row divider | `--fr-rule-quiet` | — | — |
| **Pager — "Newer films" / "Older films", with a position readout between them** | the two actions 1px `--fr-control-edge`, `--fr-radius-md`, min height `--fr-tap-min`; the readout `--fr-font-mono`, `--fr-text-xs`, `--fr-ink-muted` | `EP-ADM-01` is paged — `limit` defaults to **50** — and returns `total`. Each action moves `offset` by one page and re-sends the status filter unchanged; **changing the filter returns to the first page**, because an offset carried across a filter change lands on a row the admin did not ask for. The end action is **absent, not disabled**, on the first and last page respectively | — |
| **Position readout** | as above | **always rendered, including when every film fits on one page.** It states which rows are on screen and how many exist | — |

**The pager exists because the endpoint is paged and the screen was not.** `EP-ADM-01` has always
returned at most 50 films and a `total`; this screen drew no control for either, so **the 51st film
was unreachable from the admin surface and nothing on screen said anything had been withheld**. A list
that silently truncates and stays silent about it is the worst of both — it is neither complete nor
honest about being incomplete (`P-BRW-13`) — and it is why the readout renders even on a single page:
the admin learns what the control means before they need it, rather than the moment it starts hiding
something.

**The ordering is a total order and that is what makes paging safe here.** `EP-ADM-01` pages
`created_at DESC, id DESC`; two films created in the same transaction — which the seed does — share an
instant, and without the tie-break one would appear on two pages while another appeared on none.

**The two gate marks are the screen's whole reason for existing in this shape.** `FR-ADR-021` makes
publication and the display window separate conditions, and an admin who sees one badge saying "live"
cannot tell which of the two is stopping a film appearing.

**"No poster" and "the poster did not load" are two states and were rendered as one, and the cost of
that lands in a bucket nothing deletes from.** A presigned `EP-ADM-06` URL is valid for **one hour**
(`P-ADM-03`), so a tab left open past that — or a brief S3 failure — produced the identical empty box
and the identical words as a draft that has no poster at all. **The admin's remedy for "No poster" is
to upload one**, and doing that against a film that already has a poster writes **a second permanent
object**: `EP-ADM-05` mints a new server-generated key and `FR-ADR-012` never deletes the old one, so
the mistake is not recoverable and it consumes the 5 GB allowance twice over
(`P-ADM-03` exception 12b). **The screen was inviting the one action that cannot be undone.**

**The screen does not have to guess, which is why this is a defect and not a limitation.**
`EP-ADM-01` already returns `poster_present` on every item. The two states are therefore
distinguishable at zero cost, and the branch is on that boolean and **never on whether the image
arrived** — an image that has not arrived *yet* is the Loading state and must not flip to either
message.

**States.**

| State | What renders |
|---|---|
| **Empty** | The heading, the "New film" action, and one line: "No films yet. Create the first one." The list container is absent, not collapsed to zero height. |
| **Loading** | Six row-shaped `--fr-surface-inset` blocks with the poster box at `--fr-poster-ratio`. The "New film" action stays live. |
| **Error** | The error banner of `COMPONENTS.md §6` replaces the list. The "New film" action stays live so the admin is not trapped. |
| **Success** | The list. |
| **Partial — the film has no poster** | `poster_present` is `false`. The row renders its `--fr-poster-empty-mark` box with the words "No poster" in `--fr-ink-muted` and is otherwise complete. **A missing poster is a real and expected state on a draft** (`FR-ADR-021`), not an error. |
| **Partial — the poster exists and could not be fetched** | `poster_present` is `true` and the image request failed: the presigned URL's one hour has elapsed on a tab left open, or `EP-ADM-06` answered `503`. The box renders `--fr-poster-empty-mark` with **"Poster could not be loaded. Reload the page."** in `--fr-danger-ink`. **Not the "No poster" wording and not `--fr-ink-muted`**, because the two states have opposite remedies — one says upload, the other says reload, and reloading is what re-mints the presigned URL. **No control is added to the row**: the row is one link (see Accessibility) and the remedy is the page reload the sentence names. The rest of the row is complete and the list is not an error state. |

**Copy.**

| Where | Verbatim |
|---|---|
| Heading | "Films" |
| Primary action | "New film" |
| Empty state | "No films yet. Create the first one." |
| Gate mark, published | "Published" |
| Gate mark, not published | "Draft" |
| Gate mark, inside window | "In window" |
| Gate mark, outside window | "Outside its display window" |
| Gate mark, no window set | "No display window set" |
| Poster missing — the film has none | "No poster" |
| Poster exists and could not be fetched | "Poster could not be loaded. Reload the page." |
| Row: runtime | "148 min" |
| Row: certification and language, joined | "DEMO RATING 2 · DEMO LANGUAGE A" |
| Status filter group label | "Show" |
| Status filter options | "All films" · "Drafts" · "Published" |
| Combined help line under the filter | "A film appears to customers only when it is published and today is inside its display window. Both are needed." |
| Pager, towards newer films | "Newer films" |
| Pager, towards older films | "Older films" |
| Position readout | "Films 1 to 50 of 128" |
| Position readout, last page | "Films 101 to 128 of 128" |
| Position readout, everything on one page | "Films 1 to 7 of 7" |
| Position readout, exactly one film | "Film 1 of 1" |
| Position readout, nothing to show | "No films" |

**Accessibility.** Focus order: heading, "New film", filter controls, then each row in visual order,
then the pager. Each row is one link whose accessible name is the title followed by both gate states
and, where the poster box carries words, those words too — for example "DEMO MOVIE 01, Draft, no
display window set, no poster", or "DEMO MOVIE 04, Published, in window, poster could not be loaded".
**The failed-poster state is therefore never carried by `--fr-danger-ink` alone** (`FR-ADR-051`).
The filter is a group of radio controls with a group label. **The position readout is a live region**, so a page change announces which rows are now
on screen rather than moving focus silently to a list that looks the same; each pager action's
accessible name is its visible label. Every control is at least `--fr-tap-min` high.

---

### `SCR-ADM-02` · Film editor, with the poster panel and the two gates
**Route.** `/admin/movies/new` and `/admin/movies/{movie_id}` · **Who reaches it.** admin only · **Component basis.** `COMPONENTS.md §11`, `§6`, `§3`

**What the user arrives with / leaves with.** Arrives with an empty form, or with an existing film and
its `version`. Leaves with a saved film, and — separately, by a separate control — a published one.

**Fields and controls.**

| Element | Token(s) | Behaviour | Validation |
|---|---|---|---|
| `title` | field per `COMPONENTS.md §11`; label always visible, never a placeholder | text input | 1..200 characters (`P-ADM-01`) |
| `synopsis` | multi-line field, `--fr-measure` maximum width | text area | 0..4000 characters |
| `runtime_minutes` | field, value in `--fr-font-mono` | integer input | `>= 1`, whole minutes |
| `certification` | select from the lookup table | select, options from `EP-ADM-25` with `kind=certification` | must exist |
| `language` | select from the lookup table | select, options from `EP-ADM-25` with `kind=language` | must exist |
| `genre` | multi-select from the lookup table | multi-select, options from `EP-ADM-25` with `kind=genre` | 1..10, unique |
| Empty-vocabulary line, per select | `--fr-text-xs`, `--fr-danger-ink` | rendered **in place of** a select whose vocabulary has no rows, with a link to `SCR-ADM-07`. An empty dropdown with no explanation is how an admin concludes the form is broken | the form cannot be submitted while any required vocabulary is empty (`P-ADM-23`, `P-ADM-01`) |
| Help under the field group | `--fr-text-xs`, `--fr-ink-muted` | states the bounds **before** they are broken | — |
| Save | `--fr-surface-accent` / `--fr-ink-on-accent` | submits with `version` | — |
| Hidden `version` | — | round-tripped on every save, **and sent as a second form part with the poster upload** (`P-ADM-12`, `P-ADM-03`). The `version` the upload returns replaces the one the form is holding, so the admin's next Save is not a conflict their own upload created | required |
| **Poster panel** | box at `--fr-poster-ratio` on `--fr-surface-inset`, 1px `--fr-control-edge` | see below | see `P-ADM-03` |
| Poster limits line | `--fr-text-xs`, `--fr-ink-muted`, **rendered above the file control** | "Posters must be a JPEG, PNG or WebP image, no larger than 2 MB, between 200 by 300 and 4000 by 6000 pixels." | — |
| **Display window** — start and end, each a local date and a local time | fields; values in `--fr-font-mono` | Asia/Kolkata, stated on the label | end strictly after start (`P-ADM-04`) |
| Window help | `--fr-text-xs`, `--fr-ink-muted` | states the exclusive end in words | — |
| **Publish** / **Withdraw** control | `--fr-surface-accent` when publishing; a plain control with `--fr-control-edge` when withdrawing | separate from Save. Requires confirmation | see `P-ADM-05`, `P-ADM-06` |
| **Gate status block** | `--fr-surface-raised`, `--fr-radius-md`, `--fr-shadow-card` | two lines, one per gate, each stating pass or fail and why | — |

**The poster limits are stated before the file is chosen, not after it is rejected** (`FR-ADR-061`).
The upload box uses `--fr-poster-ratio` so the admin sees the shape the poster will be shown at.

**The gate status block is the answer to "why can nobody see this film".** It renders both conditions
independently and never collapses them.

**States.**

| State | What renders |
|---|---|
| **Empty** | The create form, all fields blank, the poster panel disabled with the line "Save this film first, then upload its poster." The publish control is absent — there is nothing to publish. |
| **Loading** | Field-shaped `--fr-surface-inset` blocks. The Save control is busy and disabled; **fields stay readable and stay filled** (`COMPONENTS.md §11`). |
| **Error** | Field-level errors on their own fields with a 2px `--fr-danger-ink` border and the message in `--fr-text-xs` / `--fr-danger-ink`, announced. A form-level failure uses the banner of `COMPONENTS.md §6`. |
| **Success** | The saved values, a new `version`, and the gate status block refreshed. |
| **Partial** | A saved draft with no poster and no window. **This is the normal mid-authoring state**, not an error: the poster panel is live, the publish control is present but disabled, and the gate block states what is still missing. |
| **Upload in progress** | The poster box shows a determinate progress indication; every other field stays editable; Save is disabled until the upload settles. |
| **Version conflict** | The banner of `COMPONENTS.md §6` with the `VERSION_CONFLICT` wording. **The admin's typed values stay on screen** so they can be copied before reloading. Nothing is auto-reloaded under them. |
| **A lookup vocabulary is empty** | The affected select is replaced by the empty-vocabulary line and a link to `SCR-ADM-07`. Save stays visible and is refused server-side by `P-ADM-01` exception 6 or 7 if it is pressed anyway — **the interface is never the enforcement point.** This is the expected state on a database that has been migrated and not seeded, before any language, certification or genre has been created (`P-ADM-23`, which defers to `P-XCT-30` for what a seeded database starts with), and it is not an error. |

**Copy.**

| Where | Verbatim |
|---|---|
| Heading, new | "New film" |
| Heading, existing | the film's title |
| `title` label | "Title" |
| `synopsis` label | "Synopsis" |
| `runtime_minutes` label | "Runtime, in minutes" |
| `certification` label | "Certification" |
| `language` label | "Language" |
| `genre` label | "Genres" |
| Help under the field group | "A title of 1 to 200 characters, a synopsis of up to 4000, and a runtime in whole minutes. Choose one language, one certification and at least one genre." |
| Save | "Save" |
| Poster panel heading | "Poster" |
| Display window group label | "Display window" |
| Poster panel, before any file | "Posters must be a JPEG, PNG or WebP image, no larger than 2 MB, between 200 by 300 and 4000 by 6000 pixels." |
| Poster panel on a draft not yet saved | "Save this film first, then upload its poster." |
| Poster panel on a saved film with no poster — **the control's most-used state** | "Upload poster" |
| Poster panel with a poster | "Replace poster" |
| Poster panel, upload in progress | "Uploading…" |
| Window label, start | "Shown from (India time)" |
| Window label, end | "Shown until (India time)" |
| Window help | "The film stops being shown at the moment the end date and time is reached. A film shown until 2 Oct 2026, 12:00 am is visible for the whole of 1 Oct 2026 and not on 2 Oct 2026." |
| Gate line 1, passing | "Published." |
| Gate line 1, failing | "Not published. Customers cannot see this film." |
| Gate line 2, passing | "Inside its display window." |
| Gate line 2, failing, window in the future | "Its display window has not started yet. Customers cannot see this film until then." |
| Gate line 2, failing, window in the past | "Its display window has ended. Customers can no longer see this film." |
| Gate line 2, failing, no window | "No display window set. Customers cannot see this film." |
| Publish control | "Publish" |
| Publish blocked, no poster | "This film has no poster. Upload a poster before publishing it." |
| Publish blocked, no window | "This film has no display window. Set the dates it is shown between before publishing it." |
| Publish confirmation | "Publish this film? Customers will see it as soon as the display window starts, and it will keep its showtimes. You can withdraw it again at any time." |
| Publish confirmation, confirm | "Publish" |
| Publish confirmation, dismiss | "Not yet" |
| Withdraw control | "Withdraw from customers" |
| Withdraw confirmation, confirm | "Withdraw" |
| Withdraw confirmation, dismiss | "Keep it published" |
| Withdraw confirmation | "This film will stop appearing to customers immediately. Showtimes and bookings for it are not changed and nothing is refunded. The film is not deleted and you can publish it again." |
| **Never-deleted note**, standing text beside the withdraw control — **not an error state** | "Films are never deleted. Withdraw a film instead, so that past bookings still make sense." |
| Version conflict banner | "This film was changed by someone else while you were editing. Reload to see the current details, then make your change again. Nothing you typed has been saved." |
| Empty vocabulary, languages | "There are no languages on the list yet. Add one before saving this film." |
| Empty vocabulary, certifications | "There are no certifications on the list yet. Add one before saving this film." |
| Empty vocabulary, genres | "There are no genres on the list yet. Add one before saving this film." |
| Link beside any of those three | "Manage lists" |

**Both confirmations are published, and only one of them was.** The publish and withdraw control says
*"Requires confirmation"* for either direction; the withdraw wording existed and the publish wording
did not, so the confirmation an admin meets first — publishing their first film — had no words and the
implementer would have had to write them. **A screen that names a control owes that control's words**,
and the publish confirmation names what publishing does *and* what it does not do, because the question
an admin has at that moment is whether it is reversible.

**Four labels keep their "(India time)" and that is not rule 2 being broken.** `S7.19` rule 2 governs
**the zone printed next to a rendered instant**; `"Shown from (India time)"`, `"Shown until (India
time)"` and `SCR-ADM-03`'s two are **input labels**, telling an admin which zone the value they are
about to type will be read in. That is a different job from decorating a time the product rendered, and
removing it would leave an admin typing a local time into a field that does not say whose local time it
is. **Named here rather than left for the next audit to re-raise.**

**The window help was corrected to `S7.19`'s forms.** It read *"shown until 2 October at 00:00 …
visible for the whole of 1 October"* — a month spelled in full and a 24-hour clock, neither of which is
among the five forms. It now reads `2 Oct 2026, 12:00 am`, `1 Oct 2026` and `2 Oct 2026`: the
date-with-time form and the date form. The instants and the rule they illustrate are unchanged
(`P-ADM-04`).

**Accessibility.** Focus order follows the visual order: title, synopsis, runtime, certification,
language, genre, Save, poster panel, window start, window end, publish or withdraw. Every input has a
programmatically associated visible label. The poster limits line is associated with the file input by
`aria-describedby`, so it is read **before** the file dialog opens. Field errors are associated with
their field and announced through a live region — **an error that is only red has not been reported**
(`FR-ADR-051`). The gate status block is a live region, so a publish that changes only that block is
announced. Every control is at least `--fr-tap-min` high.

---

### `SCR-ADM-03` · Showtimes
**Route.** `/admin/showtimes` · **Who reaches it.** admin only · **Component basis.** `COMPONENTS.md §4`, `§11`, `§6`

**What the user arrives with / leaves with.** Arrives with a hall and a date in mind. Leaves with a
showtime created or edited.

**The first request this screen issues, stated because it cannot be inferred.** `EP-ADM-09` makes
**both** `screen_id` and `date` required and admits no unfiltered call, so a screen that does not name
its opening values cannot issue its first request at all. **On arrival it loads the first hall by name
— `EP-ADM-15`'s ordering, `name ASC, id ASC` — and today's local date in Asia/Kolkata**, and both
controls render already carrying those values rather than empty.

**Why those two.** The first hall by name is the one deterministic choice available: the hall list is
already ordered that way, so the screen and the list agree, and two admins opening the screen see the
same day. Today is the date an admin is most often scheduling against and the only one that needs no
prior knowledge. **Neither is a preference the implementer may vary**, because the pair decides which
showtimes appear on the first screen anyone sees.

**If no hall exists**, the screen renders the empty state below and issues **no** request — a required
`screen_id` with nothing to put in it is not a request to send. The state says so and links to
`SCR-ADM-05`, where a hall is created.

**Fields and controls.**

| Element | Token(s) | Behaviour | Validation |
|---|---|---|---|
| Hall filter | `--fr-text-sm`; selected uses `--fr-surface-accent` / `--fr-ink-on-accent` | filters the list server-side | — |
| Date filter | field, value in `--fr-font-mono` | one local date in Asia/Kolkata | — |
| **Started-showtime control** | checkbox, label `--fr-text-sm` in `--fr-ink`, help line `--fr-text-xs` / `--fr-ink-muted` | **unchecked by default**, so nothing is hidden from an admin who did not ask. Checked, it sends `include_past=false` and the server omits every showtime whose **advertised start** is at or before now (`P-ADM-09` owns the rule). The state of the control is part of the filter set and is re-sent with every hall or date change | — |
| Day strip: existing showtimes on the chosen hall and date, in start order | rows on `--fr-surface-raised`, `--fr-radius-md`, divider `--fr-rule-quiet` | each row states film, local start, local end, base price and booked-seat count | — |
| **Gap readout between consecutive rows** | `--fr-text-xs`, `--fr-ink-muted`, `--fr-font-mono` | states the minutes between one end and the next start, computed on the client by subtracting one **naive local** value from the next (`EP-ADM-09`). **Both are in the same zone and neither carries an offset, so the subtraction is arithmetic on wall-clock values and converts nothing** — which is the whole point of the read path returning what the write path accepted | — |
| "New showtime" action | `--fr-surface-accent` / `--fr-ink-on-accent` | opens the create form | — |
| `movie` | select | any film, **draft or published** | must exist |
| `screen` | select | halls in service only | must exist, in service |
| `starts_at` — local date and time | fields, `--fr-font-mono` | Asia/Kolkata, stated on the label | required |
| `ends_at` — local date and time | fields, `--fr-font-mono` | **prefilled as start + the film's runtime, exactly** | strictly after start |
| Prefill note | `--fr-text-xs`, `--fr-ink-muted` | states that no turnaround was added | — |
| `base_price_paise` | field; the admin types rupees and paise, the interface converts at the boundary | `--fr-font-mono`, Indian digit grouping | `>= 1` paisa |
| **`format_id` — optional** | select, `--fr-text-sm`; help line `--fr-text-xs` / `--fr-ink-muted` | options from `EP-ADM-25` with `kind=format` and `include_withdrawn=false`, **defaulting to no selection**. **This control is the only thing in the product that ever writes `showtime.format_id`** (`P-ADM-07`), and without it a customer's format filter can never return anything | optional; when set, must name an **active** `format` row (`P-ADM-23`, `P-ADM-24`) |
| Empty-format line | `--fr-text-xs`, `--fr-ink-muted` | rendered **in place of** the select when the `format` vocabulary has no rows, with the same link to `SCR-ADM-07` the film editor uses — **the same convention `SCR-ADM-02` already applies to an empty select**, not a second one | **it does not block submission**, because format is optional; that is the one difference from `SCR-ADM-02`, where an empty vocabulary blocks a save because the field is required |
| Price preview — one line per seat category | `--fr-font-mono`, `--fr-ink` | computed with the **same** half-up per-seat rule the server uses (`FR-ADR-038`) | — |
| Hidden `version` | — | round-tripped on edit | required on edit |
| **Submit action** | `--fr-surface-accent` / `--fr-ink-on-accent`, `--fr-radius-md`, min height `--fr-tap-min` | submits the form — `EP-ADM-10` when creating, `EP-ADM-11` when editing, sending `version` on the edit. **It is the only way a showtime is created**, and the form had no submit control at all | the server validates regardless; the control is never the enforcement point |
| **Cancel action** | plain control, 1px `--fr-control-edge` | closes the form without writing. **It is not a withdrawal and does not exist after the showtime is created** — there is no cancel-a-showtime capability in v1 (`P-ADM-21`), and the word is used here only for an unsubmitted form | — |

**The format control was missing and its absence was a defect, not a decision.** `P-ADM-07` says the
admin creates a showtime by choosing a film, a hall, a start, an end, a base price **and optionally a
format**, and calls itself the only writer of `showtime.format_id`; `EP-ADM-10` and `EP-ADM-11` both
accept the field; this screen drew no control for it. Built as this screen said, `format_id` would
never be set on any showtime, every showtime's format would answer `null`, the customer's format filter
would never render, and the Formats tab on `SCR-ADM-07` would create rows that could attach to nothing.
**The tie-break applied, stated because `S1.2` does not reach this case: behaviour outranks rendering on
whether a capability exists.** `S1.2` ranks the endpoint block first, the owning `P-row` second and the
screen third, but it does not say which wins when a rank-2 row says an action exists and a rank-3
screen draws no control for it. "The admin chooses a format" is behaviour, so the `P-row` governs and
the screen gains the control.

**Money on this screen renders `₹`, not `Rs`.** Both strings above published `Rs` and every
customer-facing string in the product publishes `₹` — so an admin reading a price preview saw
`Rs 281.25` while the seat map behind it rendered `₹281.25` for the same computation. **`Rs` survives
in exactly one place and it is not a screen**: the plain-text part of the emailed receipt
(`SCR-TKT-02`), where a plain-text body cannot rely on the reader's font having the glyph. That is an
exemption with a stated reason rather than an inconsistency, which is why it is named here.

**The gap readout exists because `P-ADM-08` refuses no gap and states no figure.** The system will
accept a zero-minute turnaround. Showing the number is the only thing this specification can honestly
do about it: it does not enforce a rule nobody has ruled, and it does not let the admin build the
schedule without seeing the consequence.

**States.**

| State | What renders |
|---|---|
| **Empty** | "No showtimes on this hall for this date." The "New showtime" action stays live. |
| **Empty only because everything is hidden** | The started-showtime control is checked and every showtime on this hall and date has already started. The strip renders the "everything has started" line **instead of** the ordinary empty line, because "no showtimes" and "no showtimes you asked to see" are two different facts and the admin can act on only one of them. The control stays live so the list can be brought back in one click. |
| **Loading** | Row-shaped `--fr-surface-inset` blocks. Filters stay live. |
| **Error** | The banner of `COMPONENTS.md §6` replaces the day strip; filters stay usable so another hall or date can be tried. |
| **Success** | The day strip, in start order, with the gap readouts. |
| **Partial** | Never for the strip: a day is shown complete or not at all, because a half-listed day is how an admin creates an overlap they could not see. |
| **Overlap refused** | The banner names the conflicting showtime with its local times, and the conflicting row in the day strip is outlined with 2px `--fr-danger-ink`. |
| **Zero gap** | The gap readout renders "0 min" in `--fr-countdown-urgent`. **The form still submits.** It is a statement of fact, not a block. |
| **No formats on the list** | The format select is replaced by the empty-format line and its link to `SCR-ADM-07`. **The form still submits**, and the showtime is created with no format — the customer's format filter simply will not return it (`P-ADM-07`). This is the state of a database that has been migrated and not seeded, and it is not an error. |

**Copy.**

| Where | Verbatim |
|---|---|
| Heading | "Showtimes" |
| Hall filter label | "Hall" |
| Date filter label | "Date" |
| `movie` select label | "Film" |
| `screen` select label | "Hall" |
| Primary action | "New showtime" |
| Empty state | "No showtimes on this hall for this date." |
| Started-showtime control | "Hide showtimes that have already started" |
| Started-showtime control, help line | "A showtime counts as started at its advertised start time. Sales for it may still be open." |
| Empty only because everything is hidden | "Every showtime on this hall for this date has already started. Clear the 'Hide showtimes that have already started' box to see them." |
| `starts_at` label | "Starts (India time)" |
| `ends_at` label | "Ends (India time)" |
| Prefill note | "The end time is filled in as the start plus the film's runtime. No changeover time has been added. Set the end time you actually want." |
| Day-strip row | "7:30 pm to 9:58 pm · DEMO MOVIE 04 · ₹250.00 base" |
| Day-strip row, seats booked | "42 of 150 seats booked" |
| Day-strip row, nothing booked yet | "No seats booked yet" |
| Gap readout | "12 min between shows" |
| Gap readout at zero | "0 min between shows" |
| Strip announcement, two or more | "8 showtimes on this hall for this date" |
| Strip announcement, exactly one | "1 showtime on this hall for this date" |
| Strip announcement, none | "No showtimes on this hall for this date" |
| Submit action, creating | "Create showtime" |
| Submit action, editing | "Save changes" |
| Cancel action | "Discard this form" |
| Base price label | "Base price" |
| Format label | "Format (optional)" |
| Format, no selection chosen | "No format" |
| Format help line | "A showtime with no format is not returned when a customer filters by format." |
| Empty-format line | "There are no formats on the list yet. This showtime can be created without one." |
| Link beside the empty-format line | "Manage lists" |
| Price preview heading | "Seat prices for this showtime" |
| Price preview row | "Premium — ₹281.25" |
| Overlap error | "Screen 3 already has a showtime from 6:30 pm to 8:58 pm on 4 Sep 2026. Two showtimes cannot run in one hall at the same time. Choose a different time or a different hall." |
| Overlap error, several | "Screen 3 already has 2 showtimes in that period. Two showtimes cannot run in one hall at the same time. Choose a different time or a different hall." |
| Hall out of service | "This hall is out of service. Bring it back into service before creating showtimes on it." |
| Hall change refused | "A showtime cannot be moved to a different hall. Create the showtime on the other hall instead." |
| Version conflict | "This showtime was changed by someone else while you were editing. Reload to see the current details, then make your change again. Nothing you typed has been saved." |
| Sales cut-off note under the form | "Sales for this showtime close 15 minutes after the advertised start. A customer already holding seats can finish paying after that." |

**There is no withdraw or cancel control on this screen, and no disabled one** (`P-ADM-21`).

**The never-deleted note is standing text on this screen and is not an error state.** A showtime is
never deleted, and because the interface offers no control that could attempt it, **no admin ever
reaches the 405 the unmounted `DELETE` route produces** (`P-ADM-20`) — which is exactly why the
sentence belongs here, where it is read, rather than in a response nobody triggers.

| Where | Verbatim |
|---|---|
| **Never-deleted note**, standing text under the day strip | "Showtimes are never deleted, and v1 has no way to cancel one. Check the film, the hall and the times before you create it." |

**Accessibility.** Focus order: hall filter, date filter, the started-showtime checkbox, "New
showtime", then each day-strip row, then the form in
field order. The checkbox's help line is programmatically associated with it, so the fact that a
started showtime may still be selling is not silent for a screen reader. Toggling it re-renders the
strip, and the strip is a live region, so the change in row count is announced rather than happening
silently under the focus. **The announcement is published copy and both count forms are given below**
— a live region that announces a count owes the same singular and plural as any other rendered count
(`S7.21`), and an implementer who finds no string writes one and ships "1 showtimes". The day strip is a list with an accessible name naming the hall and the date. Each gap
readout is inside the row that follows it and is part of that row's accessible name, so it is not
silent for a screen reader. The price preview is a live region: it changes as the base price is typed
and that change must be announced. Every control is at least `--fr-tap-min` high.

---

### `SCR-ADM-04` · Seat categories and pricing
**Route.** `/admin/pricing` · **Who reaches it.** admin only · **Component basis.** `COMPONENTS.md §5`, `§11`, `§6`

**What the user arrives with / leaves with.** Arrives to change one number. Leaves having changed the
price of every future show in every hall.

**Fields and controls.**

| Element | Token(s) | Behaviour | Validation |
|---|---|---|---|
| Category name | field, `--fr-text-md`, `--fr-ink` | text | 1..40 characters, unique on `lower(trim(name))` (`P-ADM-11`) |
| `uplift_basis_points` | field, value in `--fr-font-mono` | integer basis points | `>= 0` |
| Percentage echo | `--fr-text-sm`, `--fr-ink-muted`, `--fr-font-mono` | restates the basis points as a percentage as they are typed | — |
| Worked-example strip | `--fr-surface-inset`, `--fr-radius-md`, `--fr-font-mono` | shows the resulting seat price for one named base price, using the server's rule | — |
| Impact line | `--fr-text-sm`, `--fr-danger-ink` | states the count of future showtimes affected. **The figure is `affected_future_showtimes` from `EP-ADM-12`, rendered as returned.** The interface never counts it, never derives it from a showtime list it fetched for another purpose, and never renders `seat_count` in its place | — |
| Count-as-of line | `--fr-text-xs`, `--fr-ink-muted`, `--fr-font-mono` | renders `evaluated_at_utc` in Asia/Kolkata, so the admin can see the figure has an instant attached to it rather than being a standing fact | — |
| Save | `--fr-surface-accent` / `--fr-ink-on-accent` | requires confirmation | — |
| Hidden `version` | — | round-tripped | required |
| **Assumption note** | `--fr-text-xs`, `--fr-ink-muted` | states that the three category names were the build session's choice | — |
| **"New category" action** | `--fr-surface-accent` / `--fr-ink-on-accent`, `--fr-radius-md`, min height `--fr-tap-min` | opens the create form below. **This screen had no create action at all**, and it is the only surface that can reach `EP-ADM-13` | — |
| **Create form — name and uplift** | the same two fields as an existing row, on `--fr-surface-raised` | `POST /api/admin/seat-categories` (`EP-ADM-13`, `P-ADM-11`). **No `version` is sent**: a row that does not exist yet has none | name 1..40 and unique on `lower(trim(name))`; `uplift_basis_points` `>= 0` |
| **Create submit** | `--fr-surface-accent` / `--fr-ink-on-accent` | submits the create form. **No confirmation**: creating a category prices no showtime by itself — nothing has seats in it yet — so there is no blast radius to state, which is exactly why the *edit* path has a confirmation and this one does not | — |

**Why the create action had to be added, stated because its absence had consequences three steps
away.** `P-ADM-13` refuses a seat without a `seat_category_id`, `P-ADM-07` refuses a showtime on a hall
with no seats in service, and this was the only screen that could create a category. On a database
that has been migrated and **not** seeded, the product was therefore unreachable from its own admin
surface: no category, so no seat, so no showtime, so nothing for a customer to see. `EP-ADM-13` had no
caller and `seat_category.created` was an audit action nothing could write — which `P-ADM-19` names in
terms as a defect in the table rather than a gap elsewhere.

**States.**

| State | What renders |
|---|---|
| **Empty** | The heading, the "New category" action, and one line: "No seat categories yet. Create the first one." **This state is reachable**, on a database that has been migrated and not seeded — it is the state the admin meets before anything else in this epic works — and the create action is what gets them out of it. A seeded database starts with three categories (`FR-ADR-067`, `P-XCT-30`), which is why it is rarely seen and not why it cannot happen. |
| **Loading** | Field-shaped `--fr-surface-inset` blocks; Save busy and disabled. |
| **Error** | Field-level errors on their fields; a form-level failure uses `COMPONENTS.md §6`. |
| **Success** | The saved values, a new `version`, and the worked-example strip recomputed. |
| **Partial** | Never. A price form shows every category or none; a half-loaded price list is how two categories get edited against a stale third. |
| **Confirmation** | A confirmation step naming the category, the old percentage, the new percentage, and the number of future showtimes affected. **The number is the one this screen already holds from `EP-ADM-12`, not a number fetched at confirmation time**, so the figure the admin reads is the figure they were shown. The admin confirms explicitly. |
| **The count is unavailable** | `EP-ADM-12` cannot return without it — it is one field of one response. If the whole request failed, the screen is in the **Error** state above and there is no form to confirm from. **There is no state in which the confirmation renders without the count**, and no fallback wording that omits it: a confirmation for the most dangerous write in the system is not shown with its blast radius missing. |
| **The count is zero** | The impact line and the confirmation both render `0`. The change is still permitted and the control is not disabled — an uplift set before the first showtime exists is the ordinary way to configure pricing. The confirmation says so rather than reading as an error. |

**Copy.**

| Where | Verbatim |
|---|---|
| Heading | "Seat categories and pricing" |
| "New category" action | "New seat category" |
| Create form heading | "New seat category" |
| Create submit | "Create category" |
| Create cancel | "Discard" |
| Category name label | "Category name" |
| Uplift label | "Uplift, in basis points" |
| Uplift help | "100 basis points is 1 percent. A base price of ₹250.00 with an uplift of 1250 gives a seat price of ₹281.25." |
| Percentage echo | "1250 basis points is 12.5 percent" |
| Worked-example heading | "At a base price of ₹250.00" |
| Worked-example row | "Premium — ₹281.25" |
| Impact line, two or more showtimes | "This uplift applies to every hall and every show. Changing it changes the price of 84 future showtimes." |
| Impact line, exactly one showtime | "This uplift applies to every hall and every show. Changing it changes the price of 1 future showtime." |
| Impact line at zero | "This uplift applies to every hall and every show. There are no showtimes still selling, so changing it changes no price today." |
| Count-as-of line | "Counted at 14 Aug 2026, 2:30 pm." |
| Help under the impact line | "A showtime counts here while it can still take a booking. Sales close 15 minutes after the advertised start, so a show that has just begun is counted." |
| Uniformity note | "There is no per-hall and no per-film category pricing. One uplift per category, everywhere." |
| Negative uplift | "The uplift cannot be negative. This system has no discounts." |
| Save | "Save pricing" |
| Confirmation, confirm | "Change the uplift" |
| Confirmation, dismiss | "Keep the current uplift" |
| Confirmation | "Change Premium from 12.5 percent to 15 percent? This affects 84 future showtimes in every hall. Customers already holding seats keep the price they were shown." |
| Assumption note | "The category names Standard, Premium and Recliner were chosen by the build session, not specified by you. Rename them freely." |
| Version conflict | "This seat category was changed by someone else while you were editing. Reload to see the current values, then make your change again. Nothing you typed has been saved." |

**Money on this screen renders `₹`, not `Rs`**, as on every other surface in the product. The only
place `Rs` survives is the plain-text part of the emailed receipt (`SCR-TKT-02`), where a plain-text
body cannot rely on the reader's font — an exemption with a reason, not a second convention.

**The worked examples inside code fences in `P-ADM-10`, `P-ADM-11` and `P-ADM-12` keep `Rs` and are
not affected by this.** They annotate integer paise for a developer reading the arithmetic — `28125`
followed by `(Rs 281.25)` — and are not strings any user reads, which is the same exemption `S7.19`
rule 3 already gives a 24-hour clock inside a worked example. **What a user reads is `₹`; what a
developer reads beside a paise integer is an annotation.**

**The confirmation states that existing holders keep their price**, because that is the question an
admin will actually have at the moment they press the control (`P-ADM-12`).

**`84` above is an illustrative value, not a figure.** Every occurrence of the count in this screen's
copy is `affected_future_showtimes` interpolated from `EP-ADM-12`'s response, exactly as `SCR-ACC-02`
interpolates its expiry. **A literal count typed into any of these strings is a defect**, and a
confirmation stating a number the server did not produce is the worst version of that defect, because
it is a safeguard reporting something it did not measure.

**The help line's "15 minutes after" carries a `PROVISIONAL` reading** (`SRC-003 OPEN-BOOK-03`,
`FR-ADR-042`). It renders the configured `SALES_CUTOFF_MINUTES` and its direction, not a typed
sentence, so a reversal changes the words and the number together.

**Accessibility.** Focus order: each category's name field, then its uplift field, then Save, then the
confirmation. The percentage echo and the worked-example strip are live regions, announced as the
uplift is typed. The impact line is inside the confirmation's accessible description, so a screen
reader user hears the blast radius before confirming, not after. Every control is at least
`--fr-tap-min` high.

---

### `SCR-ADM-05` · The hall list, hall configuration and the seat editor
**Route.** `/admin/halls` — **the hall list** — and `/admin/halls/{screen_id}` — the editor · **Who reaches it.** admin only · **Component basis.** `COMPONENTS.md §1`, `§2`, `§11`, `§6`

**What the user arrives with / leaves with.** Arrives to lay out a hall or to fix a seat. Leaves having
done one of those — or having found out that it is too late to fix it.

**This screen claimed two routes and specified one.** `/admin/halls` was named in the route line and in
the application shell's navigation, and **nothing published a hall list or a control that reaches the
create form**. `EP-ADM-15` (list halls) and `EP-ADM-16` (`POST /api/admin/screens`) both existed with
no caller, and **`screen.created` was an audit action nothing in the product could write** — the same
argument that gave `SCR-ADM-04` its create action, one screen over, and the third time this file has
had this defect. Every sibling had the control already: `SCR-ADM-01` has "New film", `SCR-ADM-04` has
"New seat category", `SCR-ADM-06` has "New manager", `SCR-ADM-07` has "Add to list".

**The list, at `/admin/halls`.** Drawn from `EP-ADM-15`, ordered `name ASC, id ASC`.

| Element | Token(s) | Behaviour | Validation |
|---|---|---|---|
| Page heading | `--fr-text-xl`, `--fr-ink-strong`, `--fr-font-display` | static | — |
| **"New hall" action** | `--fr-surface-accent` / `--fr-ink-on-accent`, `--fr-radius-md`, min height `--fr-tap-min` | opens the create form — hall name and venue, the two fields `EP-ADM-16` accepts. **This is the only route to `EP-ADM-16`** | see the editor's bounds below |
| Hall row | rows on `--fr-surface-raised`, divider `--fr-rule-quiet` | name, venue, seats in service out of seats total, and whether the hall has showtimes. Opens `/admin/halls/{screen_id}` | — |
| Seat counts on a row | `--fr-font-mono`, `--fr-text-sm`, `--fr-ink-muted` | `seat_count_in_service` of `seat_count_total`, both as `EP-ADM-15` returns them. **The two are shown separately**, because a hall with retired seats reads as smaller than it is and an admin sizing a showtime needs the in-service figure | — |
| Frozen mark on a row | `--fr-text-xs`, `--fr-ink-muted` | states that this hall's layout is frozen, from `has_showtimes` — **so an admin learns it from the list rather than by trying** (`P-ADM-14`) | — |
| Out-of-service mark on a row | `--fr-text-xs`, `--fr-ink-muted`, with the `hatch` mark of `COMPONENTS.md §1.4` | **a non-colour mark, not colour alone** (`FR-ADR-051`). Out-of-service halls stay in the list and are never filtered out — one is brought back into service from its own editor, and a hall you cannot see is a hall you cannot restore (`P-ADM-16`) | — |

**There is no pager on this list.** Six halls exist and `EP-ADM-15` returns every one; adding a pager
to a list bounded by the number of rooms in a building would be a control that never renders a second
page. `SCR-ADM-01` has one because films are unbounded and `EP-ADM-01` pages at 50 — **the difference
is the endpoint's shape, not a preference**, and it is stated here so the asymmetry between two admin
lists is deliberate rather than an omission.

**The editor, at `/admin/halls/{screen_id}`.**

**Fields and controls.**

| Element | Token(s) | Behaviour | Validation |
|---|---|---|---|
| **Freeze banner** | `--fr-surface-inset`, 1px `--fr-rule`, `--fr-text-sm`, `--fr-ink` | **always present, in both states**, stating which state this hall is in and what that permits | — |
| Hall name | field | text | 1..60 characters, unique on `lower(trim(name))` within the chosen venue (`P-ADM-13`) |
| **Venue** — `cinema_id` | select per `COMPONENTS.md §11`; label always visible, never a placeholder | **options come from `EP-ADM-28`** (`P-ADM-25`). Required on create, and **rendered even when there is one option**. On an existing hall it is **read-only with an inline reason** — a hall does not move between venues, for the same reason a showtime does not move between halls | must exist (`EP-ADM-16`) |
| Venue zone readout, beside the select | `--fr-text-xs`, `--fr-ink-muted`, `--fr-font-mono` | states the selected venue's IANA zone, because every local time on this hall's showtimes will be rendered in it (`P-ADM-26`) | — |
| Seat grid | the seat map of `COMPONENTS.md §1` in an editing mode: `--fr-seat-size`, `--fr-seat-gap`, `--fr-seat-gutter`, scrolling inside its own container | a seat is selected by click or by arrow keys | — |
| Seat fill, in service | `--fr-seat-available` with `--fr-seat-edge-available` | — | — |
| Seat fill, out of service | `--fr-seat-sold` with the `hatch` mark of `COMPONENTS.md §1.4` | **a non-colour mark, not colour alone** (`FR-ADR-051`) | — |
| `row_label` | field, `--fr-font-mono` | text | 1..4 letters |
| `seat_number` | field, `--fr-font-mono` | integer | `>= 1` |
| `seat_category_id` | select | from the category table | must exist |
| `grid_row`, `grid_col` | fields, `--fr-font-mono` | integers | `>= 1`, unique together |
| In service / out of service toggle | control with `--fr-control-edge`; on uses `--fr-surface-accent` | `P-ADM-15` | — |
| Delete seat | plain control, `--fr-danger-ink` | **rendered only when the hall has no showtimes**; absent otherwise, not disabled | `P-ADM-13` |
| Take hall out of service | plain control, `--fr-control-edge` | requires confirmation | `P-ADM-16` |
| **Return hall to service** — rendered **in place of** the control above when the hall is out of service | plain control, `--fr-control-edge` | sends `is_active = true` with `version` (`P-ADM-16`, `EP-ADM-17`) and writes `screen.reactivated`. **No confirmation**: it restores a capability and takes none away, and it is the undo of the control it replaces. **It is the only writer of `screen.reactivated`**, which nothing could write before it existed — so a hall withdrawn by mistake stayed withdrawn | `P-ADM-16` |
| **Add seat** | plain control, 1px `--fr-control-edge`, `--fr-radius-md`, min height `--fr-tap-min` | opens a row for a new seat and submits it to `EP-ADM-19`. **Stays live in both hall states**, because adding a seat is permitted after a showtime exists and only identity is frozen (`P-ADM-14`) | `P-ADM-13`'s seat bounds |
| **Save** | `--fr-surface-accent` / `--fr-ink-on-accent`, `--fr-radius-md`, min height `--fr-tap-min` | submits the hall form — `EP-ADM-16` on create, `EP-ADM-17` on edit, sending `version` on the edit. **The screen referred to a Save control in two of its own states and never listed one** | the server validates regardless |
| Hidden `version` | — | round-tripped | required |

**The second pass over this screen found more than the first, and that is worth recording.** A first
sweep looked for controls with no row and found three. A second, run against the obligation rather than
against the item list — **a screen that names a control owes that control's words, discharged only by
publishing the string or by deferring by name to the P-row that publishes it** — found that five seat
fields, the hall name and the delete control were specified in full detail, with tokens, input types
and validation bounds, and **had no label anywhere**. **That is the failure mode to hunt: not a sparse
row, but a complete-looking one.** A row that states a token, a behaviour and a bound reads as finished,
and the missing half is the half nobody notices is missing.

**Three controls this screen described and never specified are now specified.** Its "No venue exists"
state said *"Save stays visible and is refused server-side"* and its frozen state said *"add-seat stay
live"* — both naming controls that appeared in no table and carried no words — and the withdrawal
control published only one direction while **the seat toggle immediately above it publishes both**.
The asymmetry was the tell: a hall could be taken out of service and never brought back, and
`screen.reactivated` sat in `P-ADM-19`'s vocabulary with no writer.

**Frozen fields are rendered read-only, not merely disabled, once a showtime exists**, and each carries
the reason inline. The delete control is **absent**, because a control that is always refused is a
control someone will keep pressing.

**States.**

| State | What renders |
|---|---|
| **List, empty** | The heading, the "New hall" action, and one line: "No halls yet. Create the first one." **This is the state of a database that has been migrated and not seeded** (`P-XCT-30`), and it is where an admin starts. |
| **List, loaded** | One row per hall in `name ASC, id ASC` order, each with its seat counts and its marks. |
| **List, load failure** | The banner of `COMPONENTS.md §6` replaces the rows; the "New hall" action stays live so the admin is not trapped. |
| **Create form, no venue exists** | As the "No venue exists" row below: the venue select is replaced by its line and a link to `SCR-ADM-08`. |
| **Empty — new hall, no seats** | The grid area shows one line: "No seats yet. Add the first row." The freeze banner states the hall is fully editable. |
| **Loading** | The grid area renders `--fr-surface-inset` blocks at `--fr-seat-size`. The freeze banner renders as soon as the showtime count is known — **before** the seats, because it governs what the admin may do. |
| **Error** | The banner of `COMPONENTS.md §6` above the grid. The grid keeps its last good state and is not cleared. |
| **Success** | The grid, with the freeze banner. |
| **Partial** | Never for the grid. A partly-loaded seat grid is how an admin adds a seat at a coordinate that is already taken. |
| **Configurable state** — no showtime rows | Every field editable, delete control present, freeze banner states that this is the window for it. |
| **Frozen state** — one or more showtime rows | `row_label`, `seat_number` and `seat_category_id` read-only with an inline reason; `grid_row`, `grid_col`, the in-service toggle and add-seat stay live; the delete control is absent. |
| **Frozen edit refused** | The banner of `COMPONENTS.md §6` with the `LAYOUT_FROZEN` wording, naming the seat. |
| **Hall out of service** | The return-to-service note renders above the form and the withdrawal control is replaced by "Bring hall back into service". **Every other control stays live** — an out-of-service hall can still be renamed and its seats can still be edited within the freeze rules; what it cannot do is accept a new showtime (`P-ADM-16`). Nothing on this screen creates showtimes, so nothing here is disabled. |
| **No venue exists** | The create form renders with the venue select replaced by the "No venue exists" line and a link to `SCR-ADM-08`. **Save stays visible and is refused server-side** by `EP-ADM-16`'s 422 if it is pressed anyway — the interface is never the enforcement point. This is the state of a database that has been migrated and not seeded (`P-ADM-25`), and it is not an error. |

**Copy.**

| Where | Verbatim |
|---|---|
| Heading | the hall's name |
| Freeze banner, configurable | "This hall has no showtimes yet, so its layout can be changed freely. Once you create the first showtime, seat numbers and categories are fixed permanently. Check every seat number now." |
| Freeze banner, frozen | "This hall has showtimes. You can add seats, move where a seat is drawn, and take a seat in or out of service. You cannot renumber a seat, move it to another category, or remove it." |
| Inline reason on a frozen field | "Fixed because this hall has showtimes." |
| Renumber refused | "Seat C12 cannot be renumbered. This hall has showtimes, and a seat number is what a past customer's ticket says. You can add a seat, or take a seat out of service." |
| Category change refused | "Seat C12 cannot be moved to a different category. This hall has showtimes, and its seats are already priced. You can add a seat, or take a seat out of service." |
| Delete refused | "Seat C12 cannot be removed. This hall has showtimes, and removing a seat would break the record of who booked it. Take it out of service instead." |
| Out-of-service toggle, on | "Take out of service" |
| Out-of-service toggle, off | "Return to service" |
| Out-of-service explanation | "A seat out of service is not offered on showtimes created after now. Showtimes that already exist are not changed, and a seat already booked stays booked." |
| List heading | "Halls" |
| List primary action | "New hall" |
| List empty state | "No halls yet. Create the first one." |
| Hall row, seat counts | "142 of 150 seats in service" |
| Hall row, seat counts when none are retired | "150 seats" |
| Hall row, frozen mark | "Layout fixed — this hall has showtimes" |
| Hall row, not frozen | "Layout can still be changed" |
| Hall row, out of service | "Out of service" |
| Create form heading | "New hall" |
| Create submit | "Create hall" |
| Create cancel | "Discard" |
| Hall name label | "Hall name" |
| `row_label` label | "Row" |
| `seat_number` label | "Seat number" |
| `seat_category_id` label | "Seat category" |
| `grid_row` label | "Row position in the map" |
| `grid_col` label | "Column position in the map" |
| Delete seat control | "Remove seat" |
| Delete seat confirmation | "Remove this seat? It has never been part of a showtime, so nothing is lost. Once this hall has a showtime you will not be able to remove a seat at all." |
| Empty grid | "No seats yet. Add the first row." |
| Duplicate seat, one | "Seat C12 already exists in this hall. Every seat in a hall needs its own row and number." |
| Duplicate seat, two or more | "Seats C12, C13 and C14 already exist in this hall. Every seat in a hall needs its own row and number." |
| Duplicate coordinate, one | "Another seat is already drawn at that position in the map. Choose a different position." |
| Duplicate coordinate, two or more | "Another seat is already drawn at 3 of those positions in the map. Choose different positions." |
| Venue label | "Venue" |
| Venue help, on create | "Every hall belongs to a venue. Times for shows in this hall are shown in the venue's time zone." |
| Venue zone readout | "Times shown in Asia/Kolkata" |
| Venue, read-only on an existing hall | "Fixed. A hall cannot be moved to a different venue. Create the hall on the other venue instead." |
| No venue exists | "There is no venue yet. A hall cannot be created until one exists." |
| Save | "Save hall" |
| Add seat | "Add seat" |
| Add seat, first seat in an empty hall | "Add the first seat" |
| Take hall out of service | "Take hall out of service" |
| Hall withdrawal confirmation | "This hall will accept no new showtimes. Showtimes that already exist are not changed, bookings are not cancelled, and nothing is refunded. The hall is not deleted and you can bring it back into service." |
| Return hall to service | "Bring hall back into service" |
| Return-to-service note, beside that control | "This hall is out of service. It accepts no new showtimes until you bring it back." |
| **Never-deleted note**, standing text beside the withdrawal control — **not an error state** | "Halls are never deleted. Take this hall out of service instead." |
| **Never-deleted note**, standing text in the seat editor | "Seats are never deleted once this hall has a showtime. Take a seat out of service instead." |

**The freeze banner is present in both states and never absent.** An admin who has to infer the state
from which controls are missing will infer it wrong once.

**Accessibility — the list.** Focus order: heading, "New hall", then each hall row in list order, then
the create form in field order. Each row is one link whose accessible name is the hall's name followed
by its seat counts and any mark it carries, for example "Screen 3, 142 of 150 seats in service, layout
fixed — this hall has showtimes". **The frozen and out-of-service marks are in the accessible name**,
so neither is carried by a token alone. Every control is at least `--fr-tap-min` high.

**Accessibility — the editor.** The seat grid is **one tab stop**, navigated with arrow keys (`FR-ADR-051`) —
tabbing through 220 seats to reach a control is technically conformant and unusable. Each seat's
accessible name states its identity, its category and its service state, for example "Row C seat 12,
Premium, in service". The freeze banner is the first thing in the reading order after the heading and
is a live region, so a state change is announced. Seat states are distinguished by a non-colour mark
as well as by fill (`COMPONENTS.md §1.4`, `FR-ADR-051`). The grid scrolls inside its own container and
the page body never scrolls horizontally (`COMPONENTS.md §0.1`, `§1.3`). Every control is at least
`--fr-tap-min` high and each seat is `--fr-seat-size`, which is WCAG 2.2 target-size minimum.

---

### `SCR-ADM-06` · Manager accounts and screen assignment
**Route.** `/admin/managers` · **Who reaches it.** admin only · **Component basis.** `COMPONENTS.md §11`, `§6`

**What the user arrives with / leaves with.** Arrives with an email address and a list of halls. Leaves
with a manager account that can read those halls' figures and change nothing.

**Fields and controls.**

| Element | Token(s) | Behaviour | Validation |
|---|---|---|---|
| Manager list | rows on `--fr-surface-raised`, divider `--fr-rule-quiet` | email, assigned hall names, account state | — |
| "New manager" action | `--fr-surface-accent` / `--fr-ink-on-accent` | opens the create form | — |
| `email` | field | text | valid address, unique |
| Hall checkboxes — one per screen | checkbox per `COMPONENTS.md §11`, min height `--fr-tap-min` | **zero or more may be ticked** | each must exist |
| Save | `--fr-surface-accent` / `--fr-ink-on-accent` | submits the complete set | — |
| Read-only note | `--fr-text-xs`, `--fr-ink-muted` | states what a manager can and cannot do | — |
| Password note | `--fr-text-xs`, `--fr-ink-muted` | states that the admin sets no password | — |
| **Notification note** | `--fr-text-xs`, `--fr-ink-muted`, rendered beside Save on the create form **before** it is pressed | states that creating the account **sends nothing** and that the admin must tell the manager themselves (`P-ADM-17`). Without it the admin creates an account, sees a `201`, and has no way to know the manager was never told | — |

**There is no password field on this screen** (`P-ADM-17`). **There is no role selector** — this screen
creates managers and nothing else.

**States.**

| State | What renders |
|---|---|
| **Empty** | "No manager accounts yet." The "New manager" action stays live. |
| **Loading** | Row-shaped `--fr-surface-inset` blocks. |
| **Error** | The banner of `COMPONENTS.md §6` replaces the list; the "New manager" action stays live. |
| **Success** | The list, each row naming the assigned halls. |
| **Partial** | A manager with **no** halls assigned renders with the line "No halls assigned". **This is a valid state, not an error** (`FR-ADR-011`), and it must not render as one. |
| **Awaiting first sign-in** | A manager whose `has_signed_in` is false renders with "Has not signed in yet". **`has_signed_in` is derived, not stored**: it is `last_signed_in_at IS NOT NULL` on the user row (`E5 P-ACC-01`, `EP-ADM-22`). A newly created manager has no usable password and has never signed in, so this is the normal state of a fresh account and **not** an error. It stops rendering the moment the manager completes the password-reset flow, because that flow signs them in and writes the column (`E5 P-ACC-08`). |

**Copy.**

| Where | Verbatim |
|---|---|
| Heading | "Manager accounts" |
| Primary action | "New manager" |
| Empty state | "No manager accounts yet." |
| Save, creating | "Create manager" |
| Save, editing an existing manager's halls | "Save halls" |
| Email label | "Email address" |
| Hall group label | "Halls this manager can see" |
| No halls assigned | "No halls assigned" |
| Awaiting sign-in | "Has not signed in yet" |
| Read-only note | "A manager can only view figures for the halls assigned to them. They cannot add or change films, showtimes, prices or halls." |
| Password note | "You do not set a password. The manager sets their own by using the password reset link on the sign-in page." |
| **Notification note**, standing text beside the Save control on the create form | "Creating this account does not send anything. Tell the manager it exists and ask them to use the password reset link on the sign-in page with this address. Until they do, this row will read 'Has not signed in yet'." |
| Duplicate email | "An account already exists with that email address. Accounts are never removed, so an address stays in use once it has been registered." |
| Wrong account type | "That account is not a manager account. Screens can only be assigned to managers." |
| Zero halls allowed | "A manager with no halls assigned sees an empty dashboard. That is allowed." |

**"Two managers per hall" is nowhere on this screen**, as a rule, a count, a warning or a limit
(`FR-ADR-011`). It is an observation of the client's current staffing and the interface does not
enforce it.

**Accessibility.** Focus order: heading, "New manager", each list row, then the form: email, then the
hall checkbox group, then Save. The hall checkboxes are a `fieldset` with the group label as its
`legend`. The read-only note and the password note are associated with the form by `aria-describedby`,
so they are read before submission rather than discovered after. Every control is at least
`--fr-tap-min` high.

---

### `SCR-ADM-07` · The lists a film is built from
**Route.** `/admin/lookups` · **Who reaches it.** admin only · **Component basis.** `COMPONENTS.md §11`, `§6`

**What the user arrives with / leaves with.** Arrives because a select on the film editor or the
showtime form was empty, because a film needs a language, certification, genre or format that is not on
the list yet, or because an entry that should no longer be offered is still being offered. Leaves with
that entry created and offered, or withdrawn and no longer offered.

**This is the screen `P-ADM-23` and `P-ADM-24` both refer to.** It carries all four vocabularies,
because they are the same shape and an admin filling in a film needs more than one of them in the same
sitting.

**It opens on `Languages`, and that is a specification rather than a default the implementer picks.**
`EP-ADM-25` takes `{kind}` in the **path**, so there is no such thing as a request for "the
vocabularies" — the screen must choose one before it can load anything at all. **Languages is first
because it is first in `P-ADM-01`'s required set** — a film needs a language, a certification and at
least one genre, and the tab order on this screen is that order — so an admin creating their first film
meets the vocabularies in the sequence the film form will ask for them. The tab is reflected in the URL
without a navigation, so a reload returns to the same one.

**Fields and controls.**

| Element | Token(s) | Behaviour | Validation |
|---|---|---|---|
| Vocabulary tabs — `Languages` / `Certifications` / `Genres` / `Formats` | one row; `--fr-rule` under the unselected, `--fr-surface-accent` bar under the selected | four tabs, one per `{kind}`. Switching tabs replaces the URL without a navigation | — |
| Entry list | rows on `--fr-surface-raised`, divider `--fr-rule-quiet` | the name, its reference count, and its withdraw or restore action. **Both active and withdrawn rows are listed, always** — see below | — |
| Reference count per row | `--fr-font-mono`, `--fr-text-sm`, `--fr-ink-muted` | states how many rows reference this entry, so the admin can see what an entry is holding up. **Rendered on all four tabs.** `EP-ADM-25` computes it for all four kinds: films for `language`, `certification` and `genre`, and **showtimes** for `format`, which is why the Formats tab's figure counts showtimes and its wording says so. **The figure counts everything that references the entry, visible or not** — drafts, unpublished films, films whose window has lapsed, and showtimes that have already sold out or closed | — |
| `name` field | field per `COMPONENTS.md §11`; label always visible, never a placeholder | text input | 1..60 characters, unique on `lower(trim(name))` within this vocabulary, **withdrawn rows included** (`P-ADM-23`) |
| Add action | `--fr-surface-accent` / `--fr-ink-on-accent`, `--fr-radius-md`, min height `--fr-tap-min` | submits one entry to the selected vocabulary | — |
| **Withdraw action** — on every **active** row | text action in `--fr-ink`, 1px `--fr-control-edge`, `--fr-radius-md`, min height `--fr-tap-min` | opens the confirmation below, then sends `PATCH .../{kind}/{id}` with `{"is_active": false}` (`P-ADM-24`, `EP-ADM-27`) | — |
| **Restore action** — on every **withdrawn** row | same treatment as Withdraw | sends the same request with `{"is_active": true}`. **It is not confirmed**: restoring is the undo of a withdrawal, it removes nothing and offering an entry again is the reversible direction | — |
| **Withdrawn-row treatment** | row background `--fr-surface-inset` instead of `--fr-surface-raised`; the name in `--fr-ink-muted`; a marker line under it in `--fr-text-xs` / `--fr-ink-muted` | marks the row as withdrawn. **Not `--fr-danger-ink`** — a withdrawn entry is a deliberate state, not an error, and colouring it as one teaches the admin to read a normal state as a fault | — |
| Never-deleted note | `--fr-text-xs`, `--fr-ink-muted` | states that entries are not removed and why | — |

**The withdraw and restore controls were missing and their absence was a defect, not a decision.**
`P-ADM-24`'s happy path step 1 reads *"the admin opens the vocabulary on `SCR-ADM-07` and withdraws an
entry"*, and this screen drew no control for it. Built as this screen said, `EP-ADM-27` would be
unreachable from the product, the eight `*.withdrawn` and `*.restored` audit actions `P-ADM-19`
publishes could never be written, and the mistyped entry `P-ADM-23` and `P-ADM-24` both use to justify
withdrawal existing would sit in every dropdown permanently. **The tie-break applied, stated because
`S1.2` does not reach this case: behaviour outranks rendering on whether a capability exists.** `S1.2`
ranks the endpoint block first, the owning `P-row` second and the screen third, but it does not say
which wins when a rank-2 row says an action exists and a rank-3 screen draws no control for it.
"The admin withdraws an entry" is behaviour, so the `P-row` governs and the screen gains the control.

**The reference count is not a visibility count, and the contrast with the customer's endpoint is
deliberate.** `EP-ADM-25` counts **every** row that references the entry — a draft film, an unpublished
one, one whose display window has lapsed, a showtime that closed last month — because the count answers
*what would I be affecting*, and a draft film holds an entry up exactly as much as a published one
does. `EP-BRW-07` counts only what a customer can currently see, because that figure drives a filter
menu and a filter offering a value that returns nothing is a broken filter. **Two endpoints, two rules,
one reason each**; stated here because a reader meeting both without this sentence assumes one of them
is wrong. The consequence to expect: an entry can read "Used by 3 films" while a customer's filter menu
does not offer it at all, and both figures are correct.

**The list is never filtered by `is_active`, and there is no show-withdrawn toggle.** A withdrawn row
the admin cannot see is a row they cannot restore, and these lists are short by construction — four
vocabularies an admin types by hand. The read behind this screen therefore calls `EP-ADM-25` with
`include_withdrawn=true`; the film editor's selects call it with the default `false`, which is the
whole difference between the two surfaces and the reason that parameter exists.

**There is no delete control and no disabled one** (`P-ADM-23`, `P-ADM-20`). A control that is always
refused is a control somebody will keep pressing. **There is no edit control either** — renaming an
entry a film already displays is not a capability any source asks for, and it is not built.

**Both of those absences stay true, and withdrawal does not touch either of them.** Withdrawal is not
deletion — the row stays, every film already pointing at it is unchanged, and it still renders on every
customer surface and every past booking; that distinction is the whole of `FR-ADR-012`, and it is why
correcting a typo is *withdraw the wrong entry, add the right one* rather than a rename (`P-ADM-24`).
**A third control has been added; nothing has been contradicted.**

**There is no `version` field on this screen**, and that is not an omission: `FR-ADR-035` gives
optimistic concurrency to `movie`, `showtime`, `screen` and `seat_category`, and a lookup row has no
mutable field for two admins to race over.

**States.**

| State | What renders |
|---|---|
| **Empty** | The tabs, the name field, the Add action, and one line: "Nothing on this list yet. Add the first entry." **This is the expected state of a database that has been migrated and not seeded** (`P-ADM-23`, which defers to `P-XCT-30` for what a seeded database starts with) and it is not an error. |
| **Withdraw confirmation** | A confirmation per `COMPONENTS.md §6` carrying the withdraw confirmation copy below. Dismissing it writes nothing. **The list is not reordered and the row does not move**, so the admin can see what they acted on. |
| **A row is withdrawn** | The row stays in place, takes the withdrawn treatment above, carries the withdrawn marker line, and its Withdraw action is replaced by Restore. **Its reference count does not change**, because withdrawal changes nothing about the films or showtimes already pointing at it. |
| **Loading** | Row-shaped `--fr-surface-inset` blocks. The tabs and the Add action stay live, because adding does not depend on the list having loaded. |
| **Error** | The banner of `COMPONENTS.md §6` replaces the list; the tabs and the Add action stay live so the admin is not trapped. |
| **Success** | The list for the selected vocabulary, with the entry just added visible in it. |
| **Partial** | Never. A half-loaded list is how an admin adds a name that is already on it and gets a 422 they cannot explain. |
| **Duplicate name** | Field-level error on the name field; the field keeps its value so it can be corrected rather than retyped. |
| **Duplicate name, the existing entry is withdrawn** | The field-level error carries the restore wording, and **the withdrawn row it collides with is scrolled into view in the list below**, where its Restore action already sits. The admin is one click from the remedy the message names, rather than being told to find it. |

**Copy.**

| Where | Verbatim |
|---|---|
| Heading | "Lists" |
| Sub-heading | "The lists a film is built from. A film cannot be saved until it has a language, a certification and at least one genre from these lists." |
| Tab labels | "Languages" · "Certifications" · "Genres" · "Formats" |
| Name label | "Name" |
| Add action | "Add to list" |
| Empty state | "Nothing on this list yet. Add the first entry." |
| Reference count — Languages, Certifications, Genres, two or more | "Used by 3 films" |
| Reference count — those three tabs, exactly one | "Used by 1 film" |
| Reference count at zero — those three tabs | "Not used by any film yet" |
| Reference count — Formats tab, two or more | "Used by 3 showtimes" |
| Reference count — Formats tab, exactly one | "Used by 1 showtime" |
| Reference count at zero — Formats tab | "Not used by any showtime yet" |

**Every count here has a singular, a plural and a zero, and all three are published.** A string
interpolating a count owes all of them: an implementer who finds only the plural ships "Used by 1
films", which is the same failure the duration rule spends a paragraph on. The zero form is not
`Used by 0 films` — it is its own sentence, because zero is the state an admin acts on.
| Withdraw action | "Withdraw" |
| Withdraw confirmation | "Withdraw this entry from the list? It stops being offered when a film or showtime is created or edited. Everything already using it is unchanged and still shows it, and you can put it back at any time." |
| Withdraw confirmation, confirm | "Withdraw" |
| Withdraw confirmation, dismiss | "Keep it on the list" |
| Withdrawn row marker line | "Withdrawn. Not offered on new films or showtimes. Everything already using it still shows it." |
| Restore action | "Restore" |
| Duplicate name, the existing entry is active | "That name is already on this list. Every entry needs its own name." |
| Duplicate name, the existing entry is **withdrawn** | "That name is already on this list, on an entry that has been withdrawn. Restore that entry instead of adding it again." |
| Name too long or empty | "Enter a name of 1 to 60 characters." |
| Never-deleted note | "Entries are not removed from these lists. A film may already be using one, and removing it would change what that film says." |
| Load failure | "This list cannot be loaded right now. Try again shortly." |
| Unhandled failure | "The server could not complete this request. If you need help, quote a1b2c3d4." |

**Accessibility.** Focus order: heading, tabs, then each list row followed immediately by that row's
Withdraw or Restore action, then the name field, then the Add action. The tab bar is a
real tab pattern: `role="tablist"`, arrow keys move between tabs, and the panel is labelled by its tab.
The name field's error is associated with it by `aria-describedby` and announced through a live region
— an error that is only red has not been reported (`FR-ADR-051`). Each list row's accessible name is
the entry's name, followed by the word "withdrawn" when it is, followed by its reference count — so
neither the count nor the withdrawn state is silent for a screen reader, and **the withdrawn state is
never carried by the muted treatment alone**. Each row's action names the entry it acts on, so a screen
reader does not announce a list of identical "Withdraw" buttons. The confirmation takes focus when it
opens and returns it to the row's action when it is dismissed. Every control is at least `--fr-tap-min`
high.

---

### `SCR-ADM-08` · The venue
**Route.** `/admin/venue` · **Who reaches it.** admin only · **Component basis.** `COMPONENTS.md §11`, `§6`

**What the user arrives with / leaves with.** Arrives because a hall form needed a venue, or because
the venue's name or time zone is wrong. Leaves having corrected one of those two things — or having
found out that a venue is not created here.

**This is the screen `P-ADM-25` refers to.** It carries **one list and one form**, because the entity
has one row today and two editable fields.

**It is reachable from the admin navigation, and it was not.** `/admin/venue` appeared in no navigation
list and could be reached only from `SCR-ADM-05`'s empty-venue state — so an admin who **had** a venue
and wanted to correct its name or its time zone had no route to this screen at all, and the zone is the
single value that re-renders every date in the product (`P-ADM-26`). **The application shell carries a
`Venue` item alongside `Films`, `Showtimes`, `Pricing`, `Halls`, `Managers` and `Lists`**, in that
order, with `Venue` last because it is the one an admin visits least. The link from `SCR-ADM-05`'s
empty-venue state stays: it is the path for an admin who has just discovered they need one, and it is
not a substitute for the item in the navigation.

**Fields and controls.**

| Element | Token(s) | Behaviour | Validation |
|---|---|---|---|
| Venue list | rows on `--fr-surface-raised`, `--fr-radius-lg`, divider `--fr-rule-quiet` | one row per cinema from `EP-ADM-28`: name, zone, hall count. **A list, not a singular panel**, so a second venue needs no new screen | — |
| Hall count per row | `--fr-font-mono`, `--fr-text-sm`, `--fr-ink-muted` | `screen_count` as returned. Links to `SCR-ADM-05` filtered to that venue | — |
| `name` | field per `COMPONENTS.md §11`; label always visible, never a placeholder | text input | 1..120 characters, unique on `lower(trim(name))` (`P-ADM-25`) |
| `timezone` | field, value in `--fr-font-mono` | an IANA zone name, typed. **Not a dropdown of a list typed into this document** — such a list goes stale when the zone database is updated (`P-ADM-25`) | must resolve in the zone database |
| Zone help | `--fr-text-xs`, `--fr-ink-muted` | states what the zone governs and what it does not, **before** the field is changed | — |
| Zone impact line | `--fr-text-sm`, `--fr-danger-ink` | rendered only when the zone field differs from the stored value; states how many showtimes will be **displayed** at a different time | — |
| Save | `--fr-surface-accent` / `--fr-ink-on-accent`, `--fr-radius-md`, min height `--fr-tap-min` | a zone change requires confirmation; a rename does not | — |
| Hidden `version` | — | round-tripped on every save (`P-ADM-12`) | required |
| **No "New venue" control** | — | **absent, not disabled** (`P-ADM-25`). A control that is always refused is a control someone keeps pressing | — |
| **No delete control** | — | absent (`P-ADM-20`) | — |

**The zone field is the dangerous half of this screen and the screen is shaped around that.** A
rename changes a label. A zone change moves the displayed time of every showtime at the venue and the
boundaries of every dashboard period (`P-ADM-26`). The two share a form and **do not share a
confirmation**.

**States.**

| State | What renders |
|---|---|
| **Empty** | No venue row exists. One line: "There is no venue yet. It is created when the system is set up." **No create control appears in this state either** — the answer to an empty list here is to run the seed, not to type a venue in (`P-ADM-25`, `FR-ADR-067`). |
| **Loading** | Row-shaped and field-shaped `--fr-surface-inset` blocks; Save busy and disabled; fields stay readable and stay filled (`COMPONENTS.md §11`). |
| **Error** | Field-level errors on their own fields, announced; a form-level failure uses the banner of `COMPONENTS.md §6`. |
| **Success** | The saved values and a new `version`. |
| **Partial** | Never. The venue is shown whole or not at all: a screen that renders a name and not a zone invites an admin to save a form it did not fully load. |
| **Zone changed — confirmation** | A confirmation step naming the current zone, the new zone, and the number of showtimes whose displayed time will move. The admin confirms explicitly. |
| **Version conflict** | The banner of `COMPONENTS.md §6` with the `VERSION_CONFLICT` wording. **The admin's typed values stay on screen** so they can be copied before reloading. |
| **More than one venue** | The list renders every row and the form edits the row that was opened. **Nothing on this screen assumes there is one**, so a second row needs no change here. |

**Copy.**

| Where | Verbatim |
|---|---|
| Heading | "Venue" |
| Sub-heading | "The place this system sells tickets for. Halls belong to it, and every time in the product is shown in its time zone." |
| Empty state | "There is no venue yet. It is created when the system is set up." |
| Name label | "Venue name" |
| Name too long or empty | "Enter a venue name of 1 to 120 characters." |
| Duplicate name | "A venue with that name already exists." |
| Zone label | "Time zone" |
| Zone help | "An IANA time zone name, such as Asia/Kolkata. Every date and time in the product is shown in this zone. Nothing already stored is changed by editing it — the times are stored as instants and only what you see changes." |
| Zone not recognised | "That is not a time zone this system recognises. Enter an IANA zone name, such as Asia/Kolkata." |
| Zone impact line, two or more | "Changing the time zone changes the time shown for 214 showtimes, and moves the start and end of every day, week and month on the dashboard." |
| Zone impact line, exactly one | "Changing the time zone changes the time shown for 1 showtime, and moves the start and end of every day, week and month on the dashboard." |
| Save | "Save venue" |
| Zone change confirmation, confirm | "Change the time zone" |
| Zone change confirmation, dismiss | "Keep the current zone" |
| Zone change confirmation, two or more | "Change the time zone from Asia/Kolkata to Asia/Dubai? Nothing already recorded is altered. 214 showtimes will be shown at a different time from now on, and the dashboard's days will start and end at a different hour." |
| Zone change confirmation, exactly one | "Change the time zone from Asia/Kolkata to Asia/Dubai? Nothing already recorded is altered. 1 showtime will be shown at a different time from now on, and the dashboard's days will start and end at a different hour." |
| Hall count on a row, two or more | "6 halls" |
| Hall count on a row, exactly one | "1 hall" |
| Hall count at zero | "No halls yet" |
| New venue, if asked for | "Venues are not created here. There is one venue and it is created when the system is set up." |
| **Never-deleted note**, standing text — **not an error state** | "Venues are never deleted." |
| **No-create note**, standing text | "Venues are not created here. There is one venue and it is created when the system is set up." |
| Version conflict | "This venue was changed by someone else while you were editing. Reload to see the current details, then make your change again. Nothing you typed has been saved." |
| Not an admin | "This page is for administrators. Your account cannot change films, showtimes, prices or halls." |
| Load failure | "The venue cannot be loaded right now. Try again shortly." |
| Unhandled failure | "The server could not complete this request. If you need help, quote a1b2c3d4." |

**Each of those pairs is a singular and a plural of one string, and the singular is reachable.** One
showtime at a venue is the ordinary state of a database seeded and then mostly emptied, or of a venue
whose halls are new. Every string in this section that interpolates a count publishes both forms.

**A string of the form "42 of 150 seats" needs no singular form and does not have one**, because the
noun agrees with the **total** rather than the count: "1 of 150 seats booked" is already correct. That
is stated so its absence reads as decided rather than missed.

**`214` and `6` above are illustrative values.** Both are interpolated from `EP-ADM-28`'s response —
`showtime_count` and `screen_count` — exactly as `SCR-ADM-04`'s count is interpolated from
`EP-ADM-12`'s. **A literal typed into either string is a defect.**

**`showtime_count` is every showtime at the venue, past and future, and it is a different figure from
`P-ADM-11`'s `affected_future_showtimes`.** A price change reaches only what can still be sold; a zone
change re-renders **everything that has ever been displayed** — a past booking in the customer's list,
a receipt read again, a completed month on the dashboard. The two counts answer two questions and the
larger one belongs here. Rendering the smaller one on this screen would understate the change.

**Accessibility.** Focus order: heading, each venue row, name field, zone field, Save, then the
confirmation. The zone help is associated with the zone field by `aria-describedby`, so it is read
**before** the field is edited rather than discovered after. The zone impact line is inside the
confirmation's accessible description, so a screen reader user hears the consequence before
confirming, not after. Field errors are associated with their field and announced through a live
region — **an error that is only red has not been reported** (`FR-ADR-051`). Every control is at least
`--fr-tap-min` high.

---

## S6 — API endpoints

Every endpoint below is mounted under `/api/admin` and carries the **single router dependency** of
`P-ADM-18`. **No handler performs its own role check.** `auth` is `role` and `roles` is `["admin"]` on
every one of them, without exception — if a future endpoint in this epic needs a different value, it
does not belong on this router.

**`rate_limit` is `none` on every admin endpoint**, and that is a statement of what `FR-ADR-058`
actually says, not a decision made here: its table lists seat hold, booking confirm, login,
registration, password reset, booking lookup and seat map, **and no admin endpoint at all**. **Two of
these endpoints deserve a bucket and do not have one** — the poster upload writes to an S3 allowance,
and the film and showtime creates write to a table that is never pruned (`FR-ADR-012`). **No figure is
invented for them here.** Raised in the Lane notes.

**Every write endpoint's `idempotency` entry says what a repeat actually does.** None of these carries
an `Idempotency-Key` header — `SRC-002 §8.3.1` and `FR-ADR-020` scope that to booking confirmation, and
extending it to admin CRUD would be inventing a requirement. **Optimistic concurrency is what protects
these writes** (`P-ADM-12`), and the difference is stated on each block rather than assumed.

---

### Films

Listing every film the admin has authored, in either state. The customer-facing listing is a different
endpoint on a different router with a different predicate, and it is not specified here.

```endpoint
{
  "id": "EP-ADM-01",
  "method": "GET",
  "path": "/api/admin/movies",
  "summary": "List every film, draft and published, with both visibility gates",
  "auth": "role",
  "roles": ["admin"],
  "request": {
    "query": {
      "status": "string, one of draft|published|all, optional, default all",
      "limit": "integer, 1..100, optional, default 50",
      "offset": "integer, 0 or more, optional, default 0"
    }
  },
  "responses": {
    "200": {"description": "The films, newest created first. ORDER BY created_at DESC, id DESC - a total order, because created_at alone is not one: two films created in the same transaction share an instant, PostgreSQL is free to return the tie in either order between two requests, and paging an unstable order shows one film twice and hides another. The seed script creates its films in one transaction, so the tie is not hypothetical. Same treatment as P-BRW-03's listing and P-ACC-11's bookings, and for the same stated reason", "body": {"items": "array of {id, title, runtime_minutes, certification, language, genres, poster_present, published_at, display_from, display_until, is_visible_now, version}. display_from and display_until are NAIVE LOCAL date and time in Asia/Kolkata, no Z and no offset - the same shape the write path accepts, so a form round-trips with no conversion (the rule at the head of S4). published_at is server-stamped and stays an ISO-8601 instant", "total": "integer"}},
    "401": {"description": "No session token"},
    "403": {"description": "Authenticated but not an admin"}
  },
  "errors": ["AUTH_REQUIRED", "FORBIDDEN", "VALIDATION_FAILED", "DEPENDENCY_UNAVAILABLE", "INTERNAL_ERROR"],
  "idempotency": "safe method - no state change",
  "rate_limit": "none - FR-ADR-058 lists no admin bucket",
  "authorisation_rule": "The /api/admin router dependency has already resolved the session and required role admin; this handler contains no authorisation code.",
  "satisfies": ["P-ADM-01", "P-ADM-05", "P-ADM-18"],
  "brd": ["R-ADM-01", "R-ADM-02", "R-ADM-05"]
}
```

Creating a film. The row is a draft: no poster, not published, invisible to every customer.

```endpoint
{
  "id": "EP-ADM-02",
  "method": "POST",
  "path": "/api/admin/movies",
  "summary": "Create a film as a draft",
  "auth": "role",
  "roles": ["admin"],
  "request": {
    "body": {
      "title": "string, 1..200 after trimming, required",
      "synopsis": "string, 0..4000, required",
      "runtime_minutes": "integer, 1 or more, required",
      "certification_id": "integer, must exist, required",
      "language_id": "integer, must exist, required",
      "genre_ids": "array of integer, 1..10, unique, each must exist, required"
    }
  },
  "responses": {
    "400": {"description": "The body does not parse, or it carries a property this endpoint does not define. Unknown properties are REJECTED and never ignored (P-ADM-01, the uniform rule at the head of S4)"},
    "201": {"description": "The created draft", "body": {"id": "integer", "title": "string", "published_at": "null", "poster_present": "false", "version": "1"}},
    "401": {"description": "No session token"},
    "403": {"description": "Authenticated but not an admin"},
    "422": {"description": "A field failed its bound"},
    "503": {"description": "Postgres unreachable; nothing was written"}
  },
  "errors": ["REQUEST_INVALID", "AUTH_REQUIRED", "FORBIDDEN", "VALIDATION_FAILED", "DEPENDENCY_UNAVAILABLE", "INTERNAL_ERROR"],
  "idempotency": "Not idempotent, and deliberately so. A repeat creates a second film, because two films may legitimately share a title (FR-ADR-021) and nothing may guess that a repeat was accidental. The interface disables the submit control while a create is in flight.",
  "rate_limit": "none - FR-ADR-058 lists no admin bucket. Flagged in Lane notes: this endpoint writes to a table that is never pruned.",
  "authorisation_rule": "The /api/admin router dependency has already resolved the session and required role admin; this handler contains no authorisation code.",
  "satisfies": ["P-ADM-01", "P-ADM-19", "P-ADM-22"],
  "brd": ["R-ADM-01", "R-ADM-06"]
}
```

Reading one film for the editor. The response carries `version`, which every subsequent write must echo.

```endpoint
{
  "id": "EP-ADM-03",
  "method": "GET",
  "path": "/api/admin/movies/{movie_id}",
  "summary": "Read one film with its version and both visibility gates",
  "auth": "role",
  "roles": ["admin"],
  "request": {
    "path_params": {"movie_id": "integer, positive"}
  },
  "responses": {
    "200": {"description": "The film", "body": {"id": "integer", "title": "string", "synopsis": "string", "runtime_minutes": "integer", "certification_id": "integer", "language_id": "integer", "genre_ids": "array of integer", "poster_present": "boolean", "published_at": "ISO-8601 instant or null - server-stamped at publication, never typed by an admin, so it keeps its zone", "display_from": "naive local date and time in Asia/Kolkata or null - NO Z and NO offset, the same shape this field is accepted in (the rule at the head of S4)", "display_until": "naive local date and time in Asia/Kolkata or null - NO Z and NO offset, as display_from", "is_visible_now": "boolean", "version": "integer"}},
    "403": {"description": "Authenticated but not an admin"},
    "404": {"description": "No film with that id"},
    "422": {"description": "movie_id is not a positive integer. A malformed path parameter fails validation before any row is looked up, which is a different answer from a well-formed id that names nothing (404)"}
  },
  "errors": ["AUTH_REQUIRED", "FORBIDDEN", "NOT_FOUND", "VALIDATION_FAILED", "DEPENDENCY_UNAVAILABLE", "INTERNAL_ERROR"],
  "idempotency": "safe method - no state change",
  "rate_limit": "none - FR-ADR-058 lists no admin bucket",
  "authorisation_rule": "The /api/admin router dependency has already resolved the session and required role admin; this handler contains no authorisation code.",
  "satisfies": ["P-ADM-02", "P-ADM-05", "P-ADM-12"],
  "brd": ["R-ADM-01", "R-ADM-02"]
}
```

Editing a film's authored fields and its display window. Both go through one endpoint because they are
one form; they write two different audit actions.

```endpoint
{
  "id": "EP-ADM-04",
  "method": "PATCH",
  "path": "/api/admin/movies/{movie_id}",
  "summary": "Edit a film's fields, its display window, or both, under optimistic concurrency",
  "auth": "role",
  "roles": ["admin"],
  "request": {
    "path_params": {"movie_id": "integer, positive"},
    "body": {
      "version": "integer, required, must equal the stored value",
      "title": "string, 1..200, optional",
      "synopsis": "string, 0..4000, optional",
      "runtime_minutes": "integer, 1 or more, optional",
      "certification_id": "integer, must exist, optional",
      "language_id": "integer, must exist, optional",
      "genre_ids": "array of integer, 1..10, unique, each must exist, optional",
      "display_from": "string, ISO-8601 local date and time in Asia/Kolkata, optional. NAIVE LOCAL ONLY - a value carrying a Z, a +hh:mm offset or a zone name is 422 VALIDATION_FAILED and is never coerced (P-ADM-04, P-ADM-07)",
      "display_until": "string, ISO-8601 local date and time in Asia/Kolkata, optional. NAIVE LOCAL ONLY - a value carrying a Z, a +hh:mm offset or a zone name is 422 VALIDATION_FAILED and is never coerced (P-ADM-04, P-ADM-07). Strictly after display_from IN THE MERGED ROW - this is a partial update and every bound is evaluated against the row as it would be after the patch, so sending either half alone is checked against the stored other half and can fail 422 (P-ADM-04)"
    }
  },
  "responses": {
    "400": {"description": "The body does not parse, or it carries a property this endpoint does not define. Unknown properties are REJECTED and never ignored (P-ADM-01, the uniform rule at the head of S4)"},
    "200": {"description": "The updated film with its new version"},
    "403": {"description": "Authenticated but not an admin"},
    "404": {"description": "No film with that id"},
    "409": {"description": "The stored version has moved; nothing was written, including no audit row"},
    "422": {"description": "A field failed its bound, or version was absent"}
  },
  "errors": ["REQUEST_INVALID", "AUTH_REQUIRED", "FORBIDDEN", "NOT_FOUND", "VERSION_CONFLICT", "VALIDATION_FAILED", "DEPENDENCY_UNAVAILABLE", "INTERNAL_ERROR"],
  "idempotency": "A repeat of the exact same request fails with VERSION_CONFLICT, because the first attempt incremented version. That is the intended behaviour: the second attempt is a stale write and is refused rather than applied twice.",
  "rate_limit": "none - FR-ADR-058 lists no admin bucket",
  "authorisation_rule": "The /api/admin router dependency has already resolved the session and required role admin; this handler contains no authorisation code.",
  "satisfies": ["P-ADM-02", "P-ADM-04", "P-ADM-12", "P-ADM-19"],
  "brd": ["R-ADM-01", "R-ADM-02", "R-ADM-05", "R-ADM-06"]
}
```

Uploading a poster. The body never touches the container's disk. It is held in a bounded in-memory
buffer — bounded by the `Content-Length` check, because the decode and the dimension check need the
bytes — and uploaded to a private S3 bucket from there (`P-ADM-03`).

```endpoint
{
  "id": "EP-ADM-05",
  "method": "POST",
  "path": "/api/admin/movies/{movie_id}/poster",
  "summary": "Upload or replace a film's poster, streamed to private object storage",
  "auth": "role",
  "roles": ["admin"],
  "request": {
    "path_params": {"movie_id": "integer, positive"},
    "headers": {
      "Content-Type": "string, must be multipart/form-data, REQUIRED",
      "Content-Length": "integer, 1..2097152 bytes, REQUIRED - checked at the header, before the body is read. This check does NOT mean the body is never buffered: steps 6 and 7 of P-ADM-03 decode the image and measure its pixel dimensions, which needs the bytes. What the check buys is that the buffer's size is known and refused before a byte is read, so no request makes the process hold more than 2 MB (P-ADM-03)"
    },
    "body": {"file": "one file part, image/jpeg or image/png or image/webp, magic bytes must match the declared type, must decode, 200..4000 by 300..6000 pixels, required", "version": "integer, the film's current version, REQUIRED. A second form part of the same multipart body - not a header and not a query parameter. Checked before any byte is streamed to S3, so a stale upload costs no object and leaves no orphan (P-ADM-12)"}
  },
  "responses": {
    "400": {"description": "The body does not parse, or it carries a property this endpoint does not define. Unknown properties are REJECTED and never ignored (P-ADM-01, the uniform rule at the head of S4)"},
    "200": {"description": "The film with its new poster key and new version", "body": {"id": "integer", "poster_present": "true", "version": "integer"}},
    "403": {"description": "Authenticated but not an admin"},
    "404": {"description": "No film with that id"},
    "409": {"description": "The film was changed by someone else; the poster was not saved"},
    "413": {"description": "Content-Length above 2 MB; the body was never read"},
    "415": {"description": "Not an accepted image type, or the declared type does not match the bytes, or the image does not decode"},
    "422": {"description": "No file part, more than one file part, no Content-Length, no version part, or dimensions out of range"},
    "503": {"description": "S3 or Postgres is unreachable, times out, or answers a RETRYABLE failure; the poster was not saved against the film. A NON-retryable S3 refusal - the credential is not permitted to write, the bucket does not exist, or a quota or policy refuses the object - is 500 INTERNAL_ERROR instead, because 'try again in a moment' is false for it and the admin cannot fix a storage credential from a form (P-ADM-03 exceptions 12 and 12b)"}
  },
  "errors": ["REQUEST_INVALID", "AUTH_REQUIRED", "FORBIDDEN", "NOT_FOUND", "VERSION_CONFLICT", "PAYLOAD_TOO_LARGE", "UNSUPPORTED_MEDIA_TYPE", "VALIDATION_FAILED", "DEPENDENCY_UNAVAILABLE", "INTERNAL_ERROR"],
  "idempotency": "A repeat of the exact same request fails with VERSION_CONFLICT, because the first upload incremented version - and it fails before any byte reaches S3, so the repeat costs no object. A repeat carrying the CURRENT version is a deliberate replacement: it writes a second S3 object under a new server-generated key and points the film at it. The previous object is never deleted (FR-ADR-012), so an audit row's before value still resolves to a real image. A deliberate replacement therefore costs storage and is otherwise harmless.",
  "rate_limit": "none - FR-ADR-058 lists no admin bucket. Flagged in Lane notes: this endpoint writes to a 5 GB S3 allowance with no limiter and no deletion.",
  "authorisation_rule": "The /api/admin router dependency has already resolved the session and required role admin; this handler contains no authorisation code. The object key is server-generated and the client's filename is never used.",
  "satisfies": ["P-ADM-03", "P-ADM-12", "P-ADM-19"],
  "brd": ["R-ADM-01", "R-ADM-06"]
}
```

Serving a poster to the admin, including on a draft film that no customer may see. The customer-facing
equivalent is a different endpoint on a different router and is not specified here.

```endpoint
{
  "id": "EP-ADM-06",
  "method": "GET",
  "path": "/api/admin/movies/{movie_id}/poster",
  "summary": "Redirect to a short-lived presigned URL for a film's poster",
  "auth": "role",
  "roles": ["admin"],
  "request": {
    "path_params": {"movie_id": "integer, positive"}
  },
  "responses": {
    "302": {"description": "Location is a presigned GET URL valid for one hour. The bucket is private and nothing is ever hotlinked."},
    "403": {"description": "Authenticated but not an admin"},
    "404": {"description": "No film with that id, or the film has no poster"},
    "422": {"description": "movie_id is not a positive integer. A malformed path parameter fails validation before any row is looked up, which is a different answer from a well-formed id that names nothing (404)"},
    "503": {"description": "S3 unreachable"}
  },
  "errors": ["AUTH_REQUIRED", "FORBIDDEN", "NOT_FOUND", "VALIDATION_FAILED", "DEPENDENCY_UNAVAILABLE", "INTERNAL_ERROR"],
  "idempotency": "safe method - no state change. Each call mints a new presigned URL.",
  "rate_limit": "none - FR-ADR-058 lists no admin bucket",
  "authorisation_rule": "The /api/admin router dependency has already resolved the session and required role admin; this handler contains no authorisation code. A draft film's poster is reachable only here, never through the public listing.",
  "satisfies": ["P-ADM-03"],
  "brd": ["R-ADM-01"]
}
```

Publishing. One of the two gates a customer sees through; it is not the same as the display window.

```endpoint
{
  "id": "EP-ADM-07",
  "method": "POST",
  "path": "/api/admin/movies/{movie_id}/publish",
  "summary": "Publish a film, refusing if it has no poster or no display window",
  "auth": "role",
  "roles": ["admin"],
  "request": {
    "path_params": {"movie_id": "integer, positive"},
    "body": {"version": "integer, required, must equal the stored value"}
  },
  "responses": {
    "400": {"description": "The body does not parse, or it carries a property this endpoint does not define. Unknown properties are REJECTED and never ignored (P-ADM-01, the uniform rule at the head of S4)"},
    "200": {"description": "The film with published_at set and a new version"},
    "403": {"description": "Authenticated but not an admin"},
    "404": {"description": "No film with that id"},
    "409": {"description": "No poster, no display window, or already published; or the stored version has moved"},
    "422": {"description": "version absent"}
  },
  "errors": ["REQUEST_INVALID", "AUTH_REQUIRED", "FORBIDDEN", "NOT_FOUND", "PUBLISH_BLOCKED", "VERSION_CONFLICT", "VALIDATION_FAILED", "DEPENDENCY_UNAVAILABLE", "INTERNAL_ERROR"],
  "idempotency": "A repeat fails with PUBLISH_BLOCKED because the film is already published, and separately with VERSION_CONFLICT because version moved. Neither publishes twice and neither overwrites the original published_at instant.",
  "rate_limit": "none - FR-ADR-058 lists no admin bucket",
  "authorisation_rule": "The /api/admin router dependency has already resolved the session and required role admin; this handler contains no authorisation code. The poster and window preconditions are re-read inside the transaction, never taken from the request.",
  "satisfies": ["P-ADM-05", "P-ADM-12", "P-ADM-19"],
  "brd": ["R-ADM-02", "R-ADM-06"]
}
```

Withdrawing a film from customers. This is what "delete a film" means here; the row is never removed.

```endpoint
{
  "id": "EP-ADM-08",
  "method": "POST",
  "path": "/api/admin/movies/{movie_id}/unpublish",
  "summary": "Withdraw a film from every customer surface without deleting anything",
  "auth": "role",
  "roles": ["admin"],
  "request": {
    "path_params": {"movie_id": "integer, positive"},
    "body": {"version": "integer, required, must equal the stored value"}
  },
  "responses": {
    "400": {"description": "The body does not parse, or it carries a property this endpoint does not define. Unknown properties are REJECTED and never ignored (P-ADM-01, the uniform rule at the head of S4)"},
    "200": {"description": "The film with published_at null and a new version. Showtimes and bookings are unchanged and nothing is refunded."},
    "403": {"description": "Authenticated but not an admin"},
    "404": {"description": "No film with that id"},
    "409": {"description": "The film is not published, or the stored version has moved"},
    "422": {"description": "version absent"}
  },
  "errors": ["REQUEST_INVALID", "AUTH_REQUIRED", "FORBIDDEN", "NOT_FOUND", "PUBLISH_BLOCKED", "VERSION_CONFLICT", "VALIDATION_FAILED", "DEPENDENCY_UNAVAILABLE", "INTERNAL_ERROR"],
  "idempotency": "A repeat fails with PUBLISH_BLOCKED because the film is already withdrawn. Nothing is written twice.",
  "rate_limit": "none - FR-ADR-058 lists no admin bucket",
  "authorisation_rule": "The /api/admin router dependency has already resolved the session and required role admin; this handler contains no authorisation code.",
  "satisfies": ["P-ADM-06", "P-ADM-12", "P-ADM-19", "P-ADM-20"],
  "brd": ["R-ADM-02", "R-ADM-06", "R-ADM-07"]
}
```

---

### Showtimes

Listing the showtimes on one hall for one local day, in start order. This is what the day strip and its
gap readouts are drawn from, and it is why the whole day is returned rather than a page of it.

```endpoint
{
  "id": "EP-ADM-09",
  "method": "GET",
  "path": "/api/admin/showtimes",
  "summary": "List showtimes for one hall and one local date, in start order",
  "auth": "role",
  "roles": ["admin"],
  "request": {
    "query": {
      "screen_id": "integer, positive, required",
      "date": "string, ISO-8601 date in Asia/Kolkata, required",
      "include_past": "boolean, optional, default true. PAST MEANS THE ADVERTISED START INSTANT IS AT OR BEFORE NOW. false omits every showtime whose starts_at is at or before the request instant; true, the default, omits nothing. It is never the sales cut-off and never the end instant - the cut-off is a customer-facing boundary that moves with SALES_CUTOFF_MINUTES, and starts_at is a property of the showtime itself (P-ADM-09 owns this rule)"
    }
  },
  "responses": {
    "200": {"description": "Every showtime on that hall whose local start date is the given date, ordered by starts_at, filtered by include_past before anything else is applied. The whole day is returned; this endpoint is not paginated", "body": {"items": "array of {id, movie_id, movie_title, starts_at, ends_at, base_price_paise, seat_count_at_creation, booked_seat_count, version}. starts_at and ends_at are NAIVE LOCAL date and time in Asia/Kolkata, no Z and no offset - the same shape the write path accepts, so the day strip renders and the edit form refills without converting anything (the rule at the head of S4)"}},
    "403": {"description": "Authenticated but not an admin"},
    "404": {"description": "No screen with that id"},
    "422": {"description": "screen_id or date missing or malformed, or include_past present and not a boolean"}
  },
  "errors": ["AUTH_REQUIRED", "FORBIDDEN", "NOT_FOUND", "VALIDATION_FAILED", "DEPENDENCY_UNAVAILABLE", "INTERNAL_ERROR"],
  "idempotency": "safe method - no state change",
  "rate_limit": "none - FR-ADR-058 lists no admin bucket",
  "authorisation_rule": "The /api/admin router dependency has already resolved the session and required role admin; this handler contains no authorisation code. The date boundary is taken in the cinema's zone, never from the container's clock.",
  "satisfies": ["P-ADM-07", "P-ADM-08", "P-ADM-09"],
  "brd": ["R-ADM-03"]
}
```

Creating a showtime. Nothing else in this system creates one, at any time, by any route.

```endpoint
{
  "id": "EP-ADM-10",
  "method": "POST",
  "path": "/api/admin/showtimes",
  "summary": "Create one showtime on one hall, refusing an overlap",
  "auth": "role",
  "roles": ["admin"],
  "request": {
    "body": {
      "movie_id": "integer, must exist, required. The film need not be published",
      "screen_id": "integer, must exist and be in service, required",
      "starts_at": "string, ISO-8601 local date and time in Asia/Kolkata, required. NAIVE LOCAL ONLY - a value carrying a Z, a +hh:mm offset or a zone name is 422 VALIDATION_FAILED and is never coerced (P-ADM-04, P-ADM-07)",
      "ends_at": "string, ISO-8601 local date and time in Asia/Kolkata, strictly after starts_at, required. NAIVE LOCAL ONLY - a value carrying a Z, a +hh:mm offset or a zone name is 422 VALIDATION_FAILED and is never coerced (P-ADM-04, P-ADM-07)",
      "base_price_paise": "integer, 1 or more, required. Paise only; a decimal is rejected, never rounded. UPPER BOUND, and it is arithmetic and not a business figure: base_price_paise * (10000 + highest stored uplift_basis_points) + 5000 must be <= 2^63 - 1, so that FR-ADR-038's seat-price formula cannot overflow the bigint columns it runs in. At the highest seeded uplift of 3333 basis points that caps the base price at 691770197019033 paise. Above it, 422 VALIDATION_FAILED with P-ADM-10 exception 4's sentence. NO BUSINESS CEILING EXISTS in any source and none is invented - PROPOSED-PRICEBOUND-01 in the Lane notes",
      "format_id": "integer, must be an active row of the format vocabulary (P-ADM-23), optional. A showtime with no format answers null on the browse surface and is excluded by any format filter"
    }
  },
  "responses": {
    "400": {"description": "The body does not parse, or it carries a property this endpoint does not define. Unknown properties are REJECTED and never ignored (P-ADM-01, the uniform rule at the head of S4)"},
    "201": {"description": "The created showtime. The two times come back in the SAME naive local form they were sent in - Asia/Kolkata, no Z and no offset - not as UTC instants, so the form that submitted them can refill from the response without converting (the rule at the head of S4). This block said ISO-8601 instant in UTC and that was the defect", "body": {"id": "integer", "starts_at": "naive local date and time in Asia/Kolkata", "ends_at": "naive local date and time in Asia/Kolkata", "base_price_paise": "integer", "seat_count_at_creation": "integer", "version": "1"}},
    "403": {"description": "Authenticated but not an admin"},
    "404": {"description": "No film or no screen with that id"},
    "409": {"description": "The interval overlaps an existing showtime on that hall, or the hall is out of service or has no seats in service"},
    "422": {"description": "A field failed its bound"},
    "503": {"description": "Postgres unreachable; nothing was written"}
  },
  "errors": ["REQUEST_INVALID", "AUTH_REQUIRED", "FORBIDDEN", "NOT_FOUND", "SHOWTIME_OVERLAP", "LAYOUT_FROZEN", "VALIDATION_FAILED", "DEPENDENCY_UNAVAILABLE", "INTERNAL_ERROR"],
  "idempotency": "Not idempotent by key, but self-limiting: a repeat of the exact same request fails with SHOWTIME_OVERLAP, because the first attempt now occupies that interval on that hall. A repeat therefore cannot create a duplicate screening.",
  "rate_limit": "none - FR-ADR-058 lists no admin bucket. Flagged in Lane notes.",
  "authorisation_rule": "The /api/admin router dependency has already resolved the session and required role admin; this handler contains no authorisation code. The overlap check runs inside the transaction under SELECT ... FOR UPDATE on the screen row.",
  "satisfies": ["P-ADM-07", "P-ADM-08", "P-ADM-10", "P-ADM-19"],
  "brd": ["R-ADM-03", "R-ADM-06", "R-PRC-02"]
}
```

Editing a showtime, including its base price. The hall cannot be changed and there is no withdrawal.

```endpoint
{
  "id": "EP-ADM-11",
  "method": "PATCH",
  "path": "/api/admin/showtimes/{showtime_id}",
  "summary": "Edit a showtime's film, times or base price under optimistic concurrency",
  "auth": "role",
  "roles": ["admin"],
  "request": {
    "path_params": {"showtime_id": "integer, positive"},
    "body": {
      "version": "integer, required, must equal the stored value",
      "movie_id": "integer, must exist, optional",
      "starts_at": "string, ISO-8601 local date and time in Asia/Kolkata, optional. NAIVE LOCAL ONLY - a value carrying a Z, a +hh:mm offset or a zone name is 422 VALIDATION_FAILED and is never coerced (P-ADM-04, P-ADM-07)",
      "ends_at": "string, ISO-8601 local date and time in Asia/Kolkata, optional. NAIVE LOCAL ONLY - a value carrying a Z, a +hh:mm offset or a zone name is 422 VALIDATION_FAILED and is never coerced (P-ADM-04, P-ADM-07). Strictly after starts_at IN THE MERGED ROW - this is a partial update and every bound is evaluated against the row as it would be after the patch, so sending either time alone is checked against the stored other time and can fail 422. The overlap check of P-ADM-08 also runs against the merged interval (P-ADM-09)",
      "base_price_paise": "integer, 1 or more, optional. Paise only. UPPER BOUND, arithmetic and not a business figure, identical to EP-ADM-10's: base_price_paise * (10000 + highest stored uplift_basis_points) + 5000 must be <= 2^63 - 1, so FR-ADR-038's seat-price formula cannot overflow the bigint columns it runs in. At the highest seeded uplift of 3333 basis points that caps the base price at 691770197019033 paise. Above it, 422 VALIDATION_FAILED with P-ADM-10 exception 4's sentence (P-ADM-10)",
      "format_id": "integer, must be an active row of the format vocabulary, optional. Send null to clear it"
    }
  },
  "responses": {
    "400": {"description": "The body does not parse, or it carries a property this endpoint does not define. Unknown properties are REJECTED and never ignored (P-ADM-01, the uniform rule at the head of S4)"},
    "200": {"description": "The updated showtime with its new version. Existing bookings and held prices are unchanged. starts_at and ends_at come back as naive local date and time in Asia/Kolkata, no Z and no offset, as on EP-ADM-10 (the rule at the head of S4)"},
    "403": {"description": "Authenticated but not an admin"},
    "404": {"description": "No showtime with that id"},
    "409": {"description": "The new interval overlaps another showtime on that hall, or the stored version has moved"},
    "422": {"description": "A field failed its bound, version was absent, or screen_id was present and different"}
  },
  "errors": ["REQUEST_INVALID", "AUTH_REQUIRED", "FORBIDDEN", "NOT_FOUND", "SHOWTIME_OVERLAP", "VERSION_CONFLICT", "VALIDATION_FAILED", "DEPENDENCY_UNAVAILABLE", "INTERNAL_ERROR"],
  "idempotency": "A repeat of the exact same request fails with VERSION_CONFLICT, because the first attempt incremented version. A price is therefore never applied twice and a stale form can never silently overwrite a newer edit.",
  "rate_limit": "none - FR-ADR-058 lists no admin bucket",
  "authorisation_rule": "The /api/admin router dependency has already resolved the session and required role admin; this handler contains no authorisation code. screen_id is not an editable field on this endpoint.",
  "satisfies": ["P-ADM-08", "P-ADM-09", "P-ADM-10", "P-ADM-12", "P-ADM-19"],
  "brd": ["R-ADM-03", "R-ADM-05", "R-ADM-06", "R-PRC-02"]
}
```

**There is no withdraw-showtime endpoint and none is reserved.** No path, no method, no disabled route.
`P-ADM-21`.

---

### Seat categories and pricing

Reading the categories and their uplifts. The seat map, the checkout and the dashboard all price from
these two numbers plus a base price, so this is the whole of the pricing model's mutable input.

**This response also carries the number the confirmation on `SCR-ADM-04` states**, and it carries it
**before** the write rather than in the write's reply. `P-ADM-11` requires the admin to be told how
many showtimes an uplift change reaches *before* they confirm it, and until this field existed the
only place that figure appeared was `EP-ADM-14`'s response — after the decision had been made. **No
preview endpoint was added**: the screen already loads this response to draw the form, the figure is
one indexed count, and a separate endpoint would be a second place the rule is implemented and a
second place it can drift. `seat_count` on each item is a count of seats and answers a different
question; it is not this number and must not be rendered as it.

```endpoint
{
  "id": "EP-ADM-12",
  "method": "GET",
  "path": "/api/admin/seat-categories",
  "summary": "List every seat category with its uplift, and the count of showtimes an uplift change would reach",
  "auth": "role",
  "roles": ["admin"],
  "request": {},
  "responses": {
    "200": {"description": "Every category, plus the blast-radius count the confirmation on SCR-ADM-04 states before the write. ORDER BY name ASC, id ASC - a total order, so the list does not shuffle between two requests. NOTE: two categories differing only in case cannot both exist - the name is unique on lower(trim(name)) (P-ADM-11, P-ADM-23) - so this tiebreak exists for identical stored names arriving from a migration or a restore, not for a case variant, which the index refuses", "body": {"items": "array of {id, name, uplift_basis_points, seat_count, version}. seat_count is EVERY seat row carrying this seat_category_id, across every hall, REGARDLESS of the seat's is_active and regardless of the hall's: the count exists so an admin can see what a category is holding up before changing it, and a retired seat still holds it up - it still points at this row and still appears on every showtime created before it was retired (P-ADM-14). This is the OPPOSITE rule from EP-BRW-07's count, which includes only what a customer can currently see because it drives a filter menu; two endpoints, two rules, and neither is a mistake", "affected_future_showtimes": "integer, the count of showtimes that can still take a new hold, by the rule owned by P-ADM-11. One figure for the whole response, not per item: the uplift is uniform across every hall and film, so the count does not vary by category", "evaluated_at_utc": "string, ISO-8601 instant from the injected clock, the moment the count was taken. It is not the same instant EP-ADM-14 counts at, and the two figures may legitimately differ by a showtime whose selling window closed in between"}},
    "403": {"description": "Authenticated but not an admin"}
  },
  "errors": ["AUTH_REQUIRED", "FORBIDDEN", "DEPENDENCY_UNAVAILABLE", "INTERNAL_ERROR"],
  "idempotency": "safe method - no state change",
  "rate_limit": "none - FR-ADR-058 lists no admin bucket",
  "authorisation_rule": "The /api/admin router dependency has already resolved the session and required role admin; this handler contains no authorisation code.",
  "satisfies": ["P-ADM-11"],
  "brd": ["R-PRC-02"]
}
```

Creating a fourth category. Permitted because the categories are a table and not an enum, and because
the three seeded names are `ASSUMED` rather than ruled.

```endpoint
{
  "id": "EP-ADM-13",
  "method": "POST",
  "path": "/api/admin/seat-categories",
  "summary": "Create a seat category with a percentage uplift in basis points",
  "auth": "role",
  "roles": ["admin"],
  "request": {
    "body": {
      "name": "string, 1..40 after trimming, unique on lower(trim(name)) (P-ADM-11), required",
      "uplift_basis_points": "integer, 0 or more, required. 100 basis points is 1 percent"
    }
  },
  "responses": {
    "400": {"description": "The body does not parse, or it carries a property this endpoint does not define. Unknown properties are REJECTED and never ignored (P-ADM-01, the uniform rule at the head of S4)"},
    "201": {"description": "The created category", "body": {"id": "integer", "name": "string", "uplift_basis_points": "integer", "version": "1"}},
    "403": {"description": "Authenticated but not an admin"},
    "422": {"description": "The name is empty, too long or already used, or the uplift is negative, fractional or above the arithmetic ceiling"}
  },
  "errors": ["REQUEST_INVALID", "AUTH_REQUIRED", "FORBIDDEN", "VALIDATION_FAILED", "DEPENDENCY_UNAVAILABLE", "INTERNAL_ERROR"],
  "idempotency": "A repeat fails with VALIDATION_FAILED on the unique index over lower(trim(name)). No duplicate category is created, and a repeat differing only in case is the same repeat.",
  "rate_limit": "none - FR-ADR-058 lists no admin bucket",
  "authorisation_rule": "The /api/admin router dependency has already resolved the session and required role admin; this handler contains no authorisation code.",
  "satisfies": ["P-ADM-11", "P-ADM-19"],
  "brd": ["R-PRC-02", "R-ADM-06"]
}
```

Changing an uplift. This is the single most consequential write in the product: one call moves the
price of every future show in every hall.

```endpoint
{
  "id": "EP-ADM-14",
  "method": "PATCH",
  "path": "/api/admin/seat-categories/{seat_category_id}",
  "summary": "Change a seat category's name or its uplift, uniformly across every hall and show",
  "auth": "role",
  "roles": ["admin"],
  "request": {
    "path_params": {"seat_category_id": "integer, positive"},
    "body": {
      "version": "integer, required, must equal the stored value",
      "name": "string, 1..40 after trimming, unique on lower(trim(name)) (P-ADM-11), optional",
      "uplift_basis_points": "integer, 0 or more, optional"
    }
  },
  "responses": {
    "400": {"description": "The body does not parse, or it carries a property this endpoint does not define. Unknown properties are REJECTED and never ignored (P-ADM-01, the uniform rule at the head of S4)"},
    "200": {"description": "The updated category with its new version. Holds already acquired keep the price they were quoted.", "body": {"id": "integer", "uplift_basis_points": "integer", "affected_future_showtimes": "integer, computed inside the write transaction by the same rule EP-ADM-12 uses before it, owned by P-ADM-11. A difference from the figure the admin confirmed against is expected when a showtime's selling window closed in between, and it invalidates nothing", "evaluated_at_utc": "string, ISO-8601 instant from the injected clock, the moment this count was taken", "version": "integer"}},
    "403": {"description": "Authenticated but not an admin"},
    "404": {"description": "No category with that id"},
    "409": {"description": "The stored version has moved"},
    "422": {"description": "A field failed its bound, or version was absent"}
  },
  "errors": ["REQUEST_INVALID", "AUTH_REQUIRED", "FORBIDDEN", "NOT_FOUND", "VERSION_CONFLICT", "VALIDATION_FAILED", "DEPENDENCY_UNAVAILABLE", "INTERNAL_ERROR"],
  "idempotency": "A repeat of the exact same request fails with VERSION_CONFLICT. The uplift is therefore never applied twice, which matters here more than anywhere else in the epic: a second application would compound a percentage change across every hall.",
  "rate_limit": "none - FR-ADR-058 lists no admin bucket",
  "authorisation_rule": "The /api/admin router dependency has already resolved the session and required role admin; this handler contains no authorisation code.",
  "satisfies": ["P-ADM-11", "P-ADM-12", "P-ADM-19"],
  "brd": ["R-PRC-02", "R-ADM-05", "R-ADM-06"]
}
```

**There is no delete endpoint for a seat category.** Seats and booked seats reference it
(`P-ADM-11`, `P-ADM-20`).

---

### Halls and seats

Listing halls. `has_showtimes` is on the response because it decides which seat operations the
interface may offer, and the interface must not infer it from a count it fetched separately.

```endpoint
{
  "id": "EP-ADM-15",
  "method": "GET",
  "path": "/api/admin/screens",
  "summary": "List every hall with its service state and whether its layout is frozen",
  "auth": "role",
  "roles": ["admin"],
  "request": {},
  "responses": {
    "200": {"description": "Every hall, in service and out of service alike. ORDER BY name ASC, id ASC - a total order. This is what SCR-ADM-05's hall list is drawn from", "body": {"items": "array of {id, cinema_id, name, is_active, seat_count_total, seat_count_in_service, has_showtimes, version}"}},
    "403": {"description": "Authenticated but not an admin"}
  },
  "errors": ["AUTH_REQUIRED", "FORBIDDEN", "DEPENDENCY_UNAVAILABLE", "INTERNAL_ERROR"],
  "idempotency": "safe method - no state change",
  "rate_limit": "none - FR-ADR-058 lists no admin bucket",
  "authorisation_rule": "The /api/admin router dependency has already resolved the session and required role admin; this handler contains no authorisation code.",
  "satisfies": ["P-ADM-13", "P-ADM-14", "P-ADM-16"],
  "brd": ["R-ADM-04"]
}
```

Creating a hall. A hall starts empty and in service; its seats are added separately.

```endpoint
{
  "id": "EP-ADM-16",
  "method": "POST",
  "path": "/api/admin/screens",
  "summary": "Create a hall with no seats",
  "auth": "role",
  "roles": ["admin"],
  "request": {
    "body": {
      "cinema_id": "integer, must exist, required",
      "name": "string, 1..60 after trimming, unique on lower(trim(name)) within the cinema (P-ADM-13), required"
    }
  },
  "responses": {
    "400": {"description": "The body does not parse, or it carries a property this endpoint does not define. Unknown properties are REJECTED and never ignored (P-ADM-01, the uniform rule at the head of S4)"},
    "201": {"description": "The created hall", "body": {"id": "integer", "name": "string", "is_active": "true", "has_showtimes": "false", "version": "1"}},
    "403": {"description": "Authenticated but not an admin"},
    "422": {"description": "The name is empty, too long or already used, or the cinema does not exist"}
  },
  "errors": ["REQUEST_INVALID", "AUTH_REQUIRED", "FORBIDDEN", "VALIDATION_FAILED", "DEPENDENCY_UNAVAILABLE", "INTERNAL_ERROR"],
  "idempotency": "A repeat fails with VALIDATION_FAILED on the unique index over lower(trim(name)) within the cinema. No duplicate hall is created, and a repeat differing only in case is the same repeat.",
  "rate_limit": "none - FR-ADR-058 lists no admin bucket",
  "authorisation_rule": "The /api/admin router dependency has already resolved the session and required role admin; this handler contains no authorisation code.",
  "satisfies": ["P-ADM-13", "P-ADM-19"],
  "brd": ["R-ADM-04", "R-ADM-06"]
}
```

Renaming a hall, or taking it in or out of service. There is no delete.

```endpoint
{
  "id": "EP-ADM-17",
  "method": "PATCH",
  "path": "/api/admin/screens/{screen_id}",
  "summary": "Rename a hall, or take it out of or back into service",
  "auth": "role",
  "roles": ["admin"],
  "request": {
    "path_params": {"screen_id": "integer, positive"},
    "body": {
      "version": "integer, required, must equal the stored value",
      "name": "string, 1..60 after trimming, unique on lower(trim(name)) within the cinema (P-ADM-13), optional",
      "is_active": "boolean, optional"
    }
  },
  "responses": {
    "400": {"description": "The body does not parse, or it carries a property this endpoint does not define. Unknown properties are REJECTED and never ignored (P-ADM-01, the uniform rule at the head of S4)"},
    "200": {"description": "The updated hall with its new version. Existing showtimes and bookings are unchanged and nothing is refunded."},
    "403": {"description": "Authenticated but not an admin"},
    "404": {"description": "No hall with that id"},
    "409": {"description": "The stored version has moved"},
    "422": {"description": "A field failed its bound, or version was absent"}
  },
  "errors": ["REQUEST_INVALID", "AUTH_REQUIRED", "FORBIDDEN", "NOT_FOUND", "VERSION_CONFLICT", "VALIDATION_FAILED", "DEPENDENCY_UNAVAILABLE", "INTERNAL_ERROR"],
  "idempotency": "A repeat of the exact same request fails with VERSION_CONFLICT. Taking a hall out of service twice is not possible and produces no second audit row.",
  "rate_limit": "none - FR-ADR-058 lists no admin bucket",
  "authorisation_rule": "The /api/admin router dependency has already resolved the session and required role admin; this handler contains no authorisation code. Renaming stays permitted after showtimes exist; only seat identity freezes.",
  "satisfies": ["P-ADM-13", "P-ADM-16", "P-ADM-12", "P-ADM-19", "P-ADM-20"],
  "brd": ["R-ADM-04", "R-ADM-06", "R-ADM-07"]
}
```

Reading a hall's seats, to draw the editing grid.

```endpoint
{
  "id": "EP-ADM-18",
  "method": "GET",
  "path": "/api/admin/screens/{screen_id}/seats",
  "summary": "List a hall's seats with their labels, coordinates, categories and service state",
  "auth": "role",
  "roles": ["admin"],
  "request": {
    "path_params": {"screen_id": "integer, positive"}
  },
  "responses": {
    "200": {"description": "Every seat on the hall, plus the frozen state that governs what may be edited. ORDER BY grid_row ASC, grid_col ASC, id ASC - a total order, and deliberately NOT by row_label and seat_number: a seat list read by a human is read as a hall, so it comes back in the order the seats are drawn, front row leftmost first. The two orders differ wherever a label does not follow the grid, which is permitted (P-ADM-14 lets grid coordinates change and freezes labels)", "body": {"has_showtimes": "boolean", "showtime_count": "integer", "items": "array of {id, row_label, seat_number, grid_row, grid_col, seat_category_id, is_active}"}},
    "403": {"description": "Authenticated but not an admin"},
    "404": {"description": "No hall with that id"},
    "422": {"description": "screen_id is not a positive integer. A malformed path parameter fails validation before any row is looked up, which is a different answer from a well-formed id that names nothing (404)"}
  },
  "errors": ["AUTH_REQUIRED", "FORBIDDEN", "NOT_FOUND", "VALIDATION_FAILED", "DEPENDENCY_UNAVAILABLE", "INTERNAL_ERROR"],
  "idempotency": "safe method - no state change",
  "rate_limit": "none - FR-ADR-058 lists no admin bucket",
  "authorisation_rule": "The /api/admin router dependency has already resolved the session and required role admin; this handler contains no authorisation code.",
  "satisfies": ["P-ADM-13", "P-ADM-14", "P-ADM-15"],
  "brd": ["R-ADM-04"]
}
```

Adding seats. Permitted in **both** hall states, because a new seat is referenced by nothing.

```endpoint
{
  "id": "EP-ADM-19",
  "method": "POST",
  "path": "/api/admin/screens/{screen_id}/seats",
  "summary": "Add one or more seats to a hall, permitted whether or not showtimes exist",
  "auth": "role",
  "roles": ["admin"],
  "request": {
    "path_params": {"screen_id": "integer, positive"},
    "body": {"seats": "array of {row_label: string 1..4 letters, seat_number: integer 1 or more, grid_row: integer 1 or more, grid_col: integer 1 or more, seat_category_id: integer must exist}, 1..500 entries, required"}
  },
  "responses": {
    "400": {"description": "The body does not parse, or it carries a property this endpoint does not define. Unknown properties are REJECTED and never ignored (P-ADM-01, the uniform rule at the head of S4)"},
    "201": {"description": "The created seats. ONE seat.created audit row is written per seat, not one per request - entity_id is the primary key of the changed row and cannot name 220 seats at once (P-ADM-19). All of them are written in the same transaction as the seats, so the batch stays all-or-nothing", "body": {"items": "array of {id, row_label, seat_number, grid_row, grid_col, seat_category_id, is_active}"}},
    "403": {"description": "Authenticated but not an admin"},
    "404": {"description": "No hall with that id"},
    "422": {"description": "A duplicate label, a duplicate coordinate, an unknown category, or a bound failure. The whole batch is refused; nothing partial is written"}
  },
  "errors": ["REQUEST_INVALID", "AUTH_REQUIRED", "FORBIDDEN", "NOT_FOUND", "VALIDATION_FAILED", "DEPENDENCY_UNAVAILABLE", "INTERNAL_ERROR"],
  "idempotency": "A repeat fails with VALIDATION_FAILED on the unique (screen_id, row_label, seat_number). No duplicate seat is created. The batch is all-or-nothing: a repeat of a partly-overlapping batch writes none of it.",
  "rate_limit": "none - FR-ADR-058 lists no admin bucket",
  "authorisation_rule": "The /api/admin router dependency has already resolved the session and required role admin; this handler contains no authorisation code. Adding a seat is permitted in both hall states and is not subject to the layout freeze.",
  "satisfies": ["P-ADM-13", "P-ADM-14", "P-ADM-19"],
  "brd": ["R-ADM-04", "R-ADM-06"]
}
```

Editing one seat. This is the endpoint the layout freeze guards, and the guard is in the domain layer.

```endpoint
{
  "id": "EP-ADM-20",
  "method": "PATCH",
  "path": "/api/admin/seats/{seat_id}",
  "summary": "Edit a seat, refusing identity and category changes once the hall has showtimes",
  "auth": "role",
  "roles": ["admin"],
  "request": {
    "path_params": {"seat_id": "integer, positive"},
    "body": {
      "row_label": "string, 1..4 letters, optional. REFUSED once the hall has any showtime row",
      "seat_number": "integer, 1 or more, optional. REFUSED once the hall has any showtime row",
      "seat_category_id": "integer, must exist, optional. REFUSED once the hall has any showtime row",
      "grid_row": "integer, 1 or more, optional. Always permitted",
      "grid_col": "integer, 1 or more, optional. Always permitted",
      "is_active": "boolean, optional. Always permitted"
    }
  },
  "responses": {
    "400": {"description": "The body does not parse, or it carries a property this endpoint does not define. Unknown properties are REJECTED and never ignored (P-ADM-01, the uniform rule at the head of S4)"},
    "200": {"description": "The updated seat"},
    "403": {"description": "Authenticated but not an admin"},
    "404": {"description": "No seat with that id"},
    "409": {"description": "A frozen field was changed on a hall that has showtimes, or is_active was set to the value it already holds. The second is NOT an exception to P-ADM-12's no-op 200 rule: that rule governs VERSIONED entities and a seat carries no version - this endpoint accepts none - so the toggle is an assertion about state rather than a field edit and answers 409 with P-ADM-15 exception 3's sentence. Resubmitting an unchanged grid_row IS an ordinary no-op and answers 200. details carries screen_id, seat_id, frozen_fields and showtime_count"},
    "422": {"description": "A duplicate label, a duplicate coordinate, an unknown category, or a bound failure"}
  },
  "errors": ["REQUEST_INVALID", "AUTH_REQUIRED", "FORBIDDEN", "NOT_FOUND", "LAYOUT_FROZEN", "VALIDATION_FAILED", "DEPENDENCY_UNAVAILABLE", "INTERNAL_ERROR"],
  "idempotency": "A repeat that sets the same coordinates is a NO-OP: 200, nothing written, and NO audit row - the general rule on P-ADM-12, which a seat follows for every field except is_active. This block previously said a repeat writes a second audit row, which contradicted both P-ADM-12 and this block's own 409. A repeat of an is_active toggle fails with LAYOUT_FROZEN because the seat already holds that value, so a service state is never toggled twice by a retry - that one IS the seat exception, and it is scoped to is_active alone.",
  "rate_limit": "none - FR-ADR-058 lists no admin bucket",
  "authorisation_rule": "The /api/admin router dependency has already resolved the session and required role admin; this handler contains no authorisation code. The frozen-field check is in the domain layer and not in this handler, because the admin API is not its only caller.",
  "satisfies": ["P-ADM-13", "P-ADM-14", "P-ADM-15", "P-ADM-19"],
  "brd": ["R-ADM-04", "R-ADM-06", "R-ADM-07"]
}
```

Removing a seat. **This is the only delete in the epic that touches a domain entity**, and it exists
only in the configuration window.

```endpoint
{
  "id": "EP-ADM-21",
  "method": "DELETE",
  "path": "/api/admin/seats/{seat_id}",
  "summary": "Remove a seat, permitted only while its hall has no showtime rows at all",
  "auth": "role",
  "roles": ["admin"],
  "request": {
    "path_params": {"seat_id": "integer, positive"}
  },
  "responses": {
    "204": {"description": "The seat is gone. It was referenced by nothing, because its hall has never had a showtime"},
    "403": {"description": "Authenticated but not an admin"},
    "404": {"description": "No seat with that id"},
    "409": {"description": "The hall has one or more showtime rows. Take the seat out of service instead"},
    "422": {"description": "seat_id is not a positive integer. A malformed path parameter fails validation before any row is looked up, which is a different answer from a well-formed id that names nothing (404)"}
  },
  "errors": ["AUTH_REQUIRED", "FORBIDDEN", "NOT_FOUND", "LAYOUT_FROZEN", "VALIDATION_FAILED", "DEPENDENCY_UNAVAILABLE", "INTERNAL_ERROR"],
  "idempotency": "A repeat returns 404, because the seat is gone. Nothing is deleted twice.",
  "rate_limit": "none - FR-ADR-058 lists no admin bucket",
  "authorisation_rule": "The /api/admin router dependency has already resolved the session and required role admin; this handler contains no authorisation code. FR-ADR-012's never-delete rule governs the historical record; a seat on a hall that has never had a showtime is referenced by no booking and no showtime, which is why FR-ADR-022 permits this and permits nothing else.",
  "satisfies": ["P-ADM-13", "P-ADM-14", "P-ADM-19", "P-ADM-20"],
  "brd": ["R-ADM-04", "R-ADM-06", "R-ADM-07"]
}
```

---

### Manager accounts

Listing managers and what each can see. `assigned_screen_ids` may legitimately be empty.

```endpoint
{
  "id": "EP-ADM-22",
  "method": "GET",
  "path": "/api/admin/managers",
  "summary": "List manager accounts and the halls each is assigned to",
  "auth": "role",
  "roles": ["admin"],
  "request": {},
  "responses": {
    "200": {"description": "Every manager account. ORDER BY email ASC, user_id ASC - a total order. The rule is order-by-the-name-a-human-reads, and a manager has no name field: the email IS the displayed identity on SCR-ADM-06, so it takes the name's place. has_signed_in is DERIVED, never stored: it is the user row's last_signed_in_at IS NOT NULL, where last_signed_in_at is the nullable timestamptz specified in E5 P-ACC-01 and written on every successful sign-in by E5 P-ACC-02 and E5 P-ACC-08. No sign-in timestamp itself is returned by this endpoint, only the boolean", "body": {"items": "array of {user_id, email, assigned_screen_ids, has_signed_in, created_at}"}},
    "403": {"description": "Authenticated but not an admin"}
  },
  "errors": ["AUTH_REQUIRED", "FORBIDDEN", "DEPENDENCY_UNAVAILABLE", "INTERNAL_ERROR"],
  "idempotency": "safe method - no state change",
  "rate_limit": "none - FR-ADR-058 lists no admin bucket",
  "authorisation_rule": "The /api/admin router dependency has already resolved the session and required role admin; this handler contains no authorisation code. No password hash appears in this response, and no field derived from one does either.",
  "satisfies": ["P-ADM-17"],
  "brd": ["R-ADM-05"]
}
```

Creating a manager. No password is sent, set or returned.

```endpoint
{
  "id": "EP-ADM-23",
  "method": "POST",
  "path": "/api/admin/managers",
  "summary": "Create a manager account with no password and assign it halls",
  "auth": "role",
  "roles": ["admin"],
  "request": {
    "body": {
      "email": "string, 1..254, a valid address, unique across all accounts, required",
      "screen_ids": "array of integer, unique, each must exist, may be empty, required"
    }
  },
  "responses": {
    "400": {"description": "The body does not parse, or it carries a property this endpoint does not define. Unknown properties are REJECTED and never ignored (P-ADM-01, the uniform rule at the head of S4)"},
    "201": {"description": "The created manager. The account has no usable password; the manager sets one through the existing password reset flow", "body": {"user_id": "integer", "email": "string", "assigned_screen_ids": "array of integer"}},
    "403": {"description": "Authenticated but not an admin"},
    "422": {"description": "The address is invalid or already used, a screen does not exist, or a screen is listed twice. A role field is NOT a 422: it is a property this endpoint does not define, so it is 400 REQUEST_INVALID like any other unknown property (P-ADM-17)"}
  },
  "errors": ["REQUEST_INVALID", "AUTH_REQUIRED", "FORBIDDEN", "VALIDATION_FAILED", "DEPENDENCY_UNAVAILABLE", "INTERNAL_ERROR"],
  "idempotency": "A repeat fails with VALIDATION_FAILED on the unique email address. No duplicate account is created. Because nothing is ever deleted, an address stays taken permanently.",
  "rate_limit": "none - FR-ADR-058 lists no admin bucket",
  "authorisation_rule": "The /api/admin router dependency has already resolved the session and required role admin; this handler contains no authorisation code. This endpoint creates role manager and nothing else: a role field in the body is rejected with 400 REQUEST_INVALID, never honoured and never dropped. No endpoint anywhere creates an admin account.",
  "satisfies": ["P-ADM-17", "P-ADM-18", "P-ADM-19"],
  "brd": ["R-ADM-05", "R-ADM-06"]
}
```

Replacing a manager's assigned halls. The complete set is sent; the server computes the difference.

```endpoint
{
  "id": "EP-ADM-24",
  "method": "PUT",
  "path": "/api/admin/managers/{user_id}/screens",
  "summary": "Replace the complete set of halls a manager can see",
  "auth": "role",
  "roles": ["admin"],
  "request": {
    "path_params": {"user_id": "integer, positive"},
    "body": {"screen_ids": "array of integer, unique, each must exist, may be empty, required"}
  },
  "responses": {
    "400": {"description": "The body does not parse, or it carries a property this endpoint does not define. Unknown properties are REJECTED and never ignored (P-ADM-01, the uniform rule at the head of S4)"},
    "200": {"description": "The manager's new assignment set", "body": {"user_id": "integer", "assigned_screen_ids": "array of integer"}},
    "403": {"description": "Authenticated but not an admin"},
    "404": {"description": "No account with that id"},
    "422": {"description": "A screen does not exist, a screen is listed twice, or the account exists and is not a manager account. All three are VALIDATION_FAILED, which the generated registry fixes at 422; this block previously declared 409 for the third and that pairing does not exist (P-ADM-17)"}
  },
  "errors": ["REQUEST_INVALID", "AUTH_REQUIRED", "FORBIDDEN", "NOT_FOUND", "VALIDATION_FAILED", "DEPENDENCY_UNAVAILABLE", "INTERNAL_ERROR"],
  "idempotency": "Idempotent by construction. The complete set is sent, so a repeat computes an empty difference, writes no assignment rows and writes no audit rows. This is why the endpoint replaces the set rather than adding or removing one screen at a time.",
  "rate_limit": "none - FR-ADR-058 lists no admin bucket",
  "authorisation_rule": "The /api/admin router dependency has already resolved the session and required role admin; this handler contains no authorisation code. An assignment row is current state, so removing one is a permitted deletion under FR-ADR-011; the audit rows carry its history.",
  "satisfies": ["P-ADM-17", "P-ADM-19", "P-ADM-20"],
  "brd": ["R-ADM-05", "R-ADM-06", "R-ADM-07"]
}
```

---

### Lookup vocabularies

One generic surface over four tables, because all four are the same shape and are read by the same
form. **Without these two endpoints nothing creates a language, a certification, a genre or a format,
and `P-ADM-01` can never be satisfied** — Phase 6 could not create its first film. `P-ADM-23`.

Reading one vocabulary. This is what the film editor's selects are populated from.

```endpoint
{
  "id": "EP-ADM-25",
  "method": "GET",
  "path": "/api/admin/lookups/{kind}",
  "summary": "List the rows of one lookup vocabulary",
  "auth": "role",
  "roles": ["admin"],
  "request": {
    "path_params": {"kind": "string, exactly one of language, certification, genre, format. Any other value is an address that does not exist and answers 404"},
    "query": {
      "include_withdrawn": "boolean, optional, default false. When false only rows with is_active true are returned, which is what a select should offer"
    }
  },
  "responses": {
    "200": {"description": "Every row of that vocabulary, ordered by name. reference_count is the number of rows referencing this vocabulary entry: films for language, certification and genre, and showtimes for format (EP-ADM-10 sets showtime.format_id). It is present for all four kinds. IT COUNTS EVERY REFERENCING ROW REGARDLESS OF VISIBILITY - draft films included, unpublished and lapsed-window films included, and showtimes past their sales cut-off included - because its job is to tell the admin what an entry is holding up, and a draft holds it up exactly as much as a published film does. EP-BRW-07 deliberately counts only what is currently visible, because that one drives a customer's filter menu; two endpoints, two rules, and neither is a mistake (SCR-ADM-07)", "body": {"kind": "string, echoed", "items": "array of {id, name, is_active, created_at, reference_count}"}},
    "401": {"description": "No session token"},
    "403": {"description": "Authenticated but not an admin"},
    "404": {"description": "kind is not one of the four vocabularies"},
    "422": {"description": "include_withdrawn is present and is not a boolean. kind itself is NOT a 422: it is a path segment matched against a closed set of addresses, so a fifth vocabulary is a page that does not exist (404, P-ADM-23)"}
  },
  "errors": ["AUTH_REQUIRED", "FORBIDDEN", "NOT_FOUND", "VALIDATION_FAILED", "DEPENDENCY_UNAVAILABLE", "INTERNAL_ERROR"],
  "idempotency": "safe method - no state change",
  "rate_limit": "none - FR-ADR-058 lists no admin bucket",
  "authorisation_rule": "The /api/admin router dependency has already resolved the session and required role admin; this handler contains no authorisation code. kind is matched against a closed set in the routing layer and is never interpolated into a query, so no caller-supplied string ever names a table.",
  "satisfies": ["P-ADM-23", "P-ADM-01"],
  "brd": ["R-ADM-01"]
}
```

Creating one row of one vocabulary. These tables have exactly two writes: this one, and `EP-ADM-27`,
which withdraws a row from future use or restores it (`P-ADM-24`). **There is no edit and no delete** —
a rename would rewrite what every past film says it was, and a delete is forbidden outright.

```endpoint
{
  "id": "EP-ADM-26",
  "method": "POST",
  "path": "/api/admin/lookups/{kind}",
  "summary": "Create one row in one lookup vocabulary",
  "auth": "role",
  "roles": ["admin"],
  "request": {
    "path_params": {"kind": "string, exactly one of language, certification, genre, format. Any other value is an address that does not exist and answers 404"},
    "body": {
      "name": "string, 1..60 characters after trimming, unique within this vocabulary on lower(trim(name)), required"
    }
  },
  "responses": {
    "400": {"description": "The body does not parse, or it carries a property this endpoint does not define. Unknown properties are REJECTED and never ignored (P-ADM-01, the uniform rule at the head of S4)"},
    "201": {"description": "The created row, is_active true", "body": {"id": "integer", "name": "string, as entered after trimming", "is_active": "true", "created_at": "string, ISO-8601 instant in UTC"}},
    "401": {"description": "No session token"},
    "403": {"description": "Authenticated but not an admin"},
    "404": {"description": "kind is not one of the four vocabularies"},
    "422": {"description": "name is empty, longer than 60 characters, or already present in this vocabulary"},
    "503": {"description": "Postgres unreachable; nothing was written"}
  },
  "errors": ["REQUEST_INVALID", "AUTH_REQUIRED", "FORBIDDEN", "NOT_FOUND", "VALIDATION_FAILED", "DEPENDENCY_UNAVAILABLE", "INTERNAL_ERROR"],
  "idempotency": "A repeat fails with VALIDATION_FAILED on the unique index over lower(trim(name)) within that vocabulary. No duplicate entry is created, and two simultaneous identical requests produce exactly one row and one 422 - the index is the guard, not a prior read.",
  "rate_limit": "none - FR-ADR-058 lists no admin bucket. These tables are never pruned, like every other table in this system (FR-ADR-012); the entries are typed one at a time by the single admin, which is the practical limit.",
  "authorisation_rule": "The /api/admin router dependency has already resolved the session and required role admin; this handler contains no authorisation code. kind is matched against a closed set in the routing layer and is never interpolated into a query. is_active and id are server-set: supplying either is 400 REQUEST_INVALID, never a silently dropped field.",
  "satisfies": ["P-ADM-23", "P-ADM-19", "P-ADM-01"],
  "brd": ["R-ADM-01", "R-ADM-06"]
}
```

A lookup entry is **withdrawn, never deleted and never renamed** — the same treatment a seat gets in
`P-ADM-15` and a hall in `P-ADM-16`, and for the same reason: films already reference it, and
`FR-ADR-012` forbids a delete on any path that reaches the historical record. **There is no PUT and no
DELETE on any lookup address**, and renaming is refused rather than offered, because a rename rewrites
what every past film says it was.

```endpoint
{
  "id": "EP-ADM-27",
  "method": "PATCH",
  "path": "/api/admin/lookups/{kind}/{id}",
  "summary": "Withdraw a lookup entry from future use, or restore one",
  "auth": "role",
  "roles": ["admin"],
  "request": {
    "path_params": {
      "kind": "string, exactly one of language, certification, genre, format. Any other value is an address that does not exist and answers 404",
      "id": "integer, positive, an existing row of that vocabulary"
    },
    "body": {"is_active": "boolean, required. false withdraws the entry, true restores it"}
  },
  "responses": {
    "400": {"description": "The body does not parse, or it carries a property this endpoint does not define. Unknown properties are REJECTED and never ignored (P-ADM-01, the uniform rule at the head of S4)"},
    "200": {"description": "The updated row", "body": {"id": "integer", "name": "string", "is_active": "boolean", "created_at": "string, ISO-8601 instant in UTC"}},
    "401": {"description": "No session token"},
    "403": {"description": "Authenticated but not an admin"},
    "404": {"description": "kind is not one of the four vocabularies, or no row of that vocabulary has that id"},
    "422": {"description": "is_active missing or not a boolean"},
    "503": {"description": "Postgres unreachable; nothing was written"}
  },
  "errors": ["REQUEST_INVALID", "AUTH_REQUIRED", "FORBIDDEN", "NOT_FOUND", "VALIDATION_FAILED", "DEPENDENCY_UNAVAILABLE", "INTERNAL_ERROR"],
  "idempotency": "Setting is_active to the value it already holds succeeds and changes nothing. No audit row is written when the value is unchanged, because an audit row whose before and after are identical is noise in the one table an operator reads to find real changes.",
  "rate_limit": "none - FR-ADR-058 lists no admin bucket.",
  "authorisation_rule": "The /api/admin router dependency has already resolved the session and required role admin; this handler contains no authorisation code. kind is matched against a closed set in the routing layer and is never interpolated into a query. Only is_active is writable at this address; supplying name or id is 400 REQUEST_INVALID, never a silently dropped field.",
  "satisfies": ["P-ADM-24", "P-ADM-19", "P-ADM-20"],
  "brd": ["R-ADM-01", "R-ADM-06", "R-ADM-07"]
}
```

**What withdrawal does, and what it deliberately does not do.** A withdrawn entry disappears from
every admin form's options, so no **new** film can be given it. **Every film already carrying it keeps
it, renders it to customers unchanged, and stays filterable by it** — withdrawing `Hindi` must never
make the films already marked Hindi unfindable or blank. That is the whole reason this is a flag and
not a delete, and it is the same rule `P-ADM-15` applies to a seat that has already been sold.

**The write is one transaction with its audit row** (`P-ADM-19`), carrying `before` and `after` on
`is_active`, exactly as every other privileged write in this section.

---

### The venue

Reading the venue. **This is the endpoint `EP-ADM-16`'s required `cinema_id` comes from**, and until
it existed that field had no source anywhere in the product (`P-ADM-25`). It returns an array rather
than one object, and every field a form needs to render a venue control and a zone impact line, so a
second venue costs an insert and not a new endpoint.

```endpoint
{
  "id": "EP-ADM-28",
  "method": "GET",
  "path": "/api/admin/cinemas",
  "summary": "List every venue with its time zone, its hall count and its showtime count",
  "auth": "role",
  "roles": ["admin"],
  "request": {},
  "responses": {
    "200": {"description": "Every venue, ORDER BY name ASC, id ASC - a total order, which costs nothing at one row and is already correct at two. An empty array is a valid response and means the database has been migrated and not seeded", "body": {"items": "array of {id, name, timezone, screen_count, showtime_count, version}. timezone is an IANA zone name and is the only authority for local time, per P-ADM-26. showtime_count is every showtime at the venue, past and future, because a zone change re-renders all of them - it is NOT the still-selling count P-ADM-11 defines"}},
    "403": {"description": "Authenticated but not an admin"}
  },
  "errors": ["AUTH_REQUIRED", "FORBIDDEN", "DEPENDENCY_UNAVAILABLE", "INTERNAL_ERROR"],
  "idempotency": "safe method - no state change",
  "rate_limit": "none - FR-ADR-058 lists no admin bucket",
  "authorisation_rule": "The /api/admin router dependency has already resolved the session and required role admin; this handler contains no authorisation code. There is no manager-facing variant: the venue is configuration, not a report, and EP-RPT-03 already tells a manager which halls they may read.",
  "satisfies": ["P-ADM-25", "P-ADM-26"],
  "brd": ["R-SEAT-07", "R-ADM-05"]
}
```

Editing the venue's name or its time zone. **There is no `POST` and no `DELETE` on this path** — the
one venue is created by the seed and a second is a scope change reserved to the client (`P-ADM-25`).
A zone change alters no stored instant and changes what every one of them is displayed as.

```endpoint
{
  "id": "EP-ADM-29",
  "method": "PATCH",
  "path": "/api/admin/cinemas/{cinema_id}",
  "summary": "Rename a venue or change its time zone",
  "auth": "role",
  "roles": ["admin"],
  "request": {
    "path_params": {"cinema_id": "integer, positive"},
    "body": {
      "version": "integer, required, must equal the stored value",
      "name": "string, 1..120 after trimming, unique on lower(trim(name)) (P-ADM-25), optional",
      "timezone": "string, 1..64, an IANA zone name that must resolve in the zone database at validation time, optional"
    }
  },
  "responses": {
    "400": {"description": "The body does not parse, or it carries a property this endpoint does not define. Unknown properties are REJECTED and never ignored (P-ADM-01, the uniform rule at the head of S4)"},
    "200": {"description": "The updated venue with its new version. No stored instant is altered; what changes is how every instant at this venue is displayed", "body": {"id": "integer", "name": "string", "timezone": "string", "screen_count": "integer", "showtime_count": "integer", "version": "integer"}},
    "403": {"description": "Authenticated but not an admin"},
    "404": {"description": "No venue with that id"},
    "409": {"description": "The stored version has moved"},
    "422": {"description": "The name is empty, too long or already used, or the timezone does not resolve in the zone database, or version was absent"}
  },
  "errors": ["REQUEST_INVALID", "AUTH_REQUIRED", "FORBIDDEN", "NOT_FOUND", "VERSION_CONFLICT", "VALIDATION_FAILED", "DEPENDENCY_UNAVAILABLE", "INTERNAL_ERROR"],
  "idempotency": "A repeat of the exact same request fails with VERSION_CONFLICT. The zone is therefore never applied twice, which matters here only in that a second audit row would claim a change that did not happen.",
  "rate_limit": "none - FR-ADR-058 lists no admin bucket",
  "authorisation_rule": "The /api/admin router dependency has already resolved the session and required role admin; this handler contains no authorisation code. The timezone written here is what every conversion in the product reads; CINEMA_TIMEZONE is not consulted by this handler or by any other request-path code (P-ADM-26).",
  "satisfies": ["P-ADM-25", "P-ADM-26", "P-ADM-12", "P-ADM-19"],
  "brd": ["R-SEAT-07", "R-ADM-05", "R-ADM-06", "R-PRC-01"]
}
```

**There is no create endpoint and no delete endpoint for a venue** (`P-ADM-25`, `P-ADM-20`). Neither
path is mounted, so both answer **405 `METHOD_NOT_ALLOWED`** from the global handler rather than a
refusal written into a route, and neither carries a venue-specific sentence — an unmounted route knows
nothing about venues. That wording is on `SCR-ADM-08`.

---

### New error codes this lane needs

Eight codes are needed that `FR-ADR-052`'s registry does not carry. Each is a class of failure the
registry has no member for — a validation failure, a wrong role, a missing object, and the four
refusals this epic is built around.

**The discipline, stated exactly, because it was stated loosely and the looseness read as a hole.**
Every code named in any `errors` array in this section is **either a member of `FR-ADR-052`'s
registry** — which this section does not re-declare, because that record already declares it — **or
declared in a `newerrorcode` block below.** No third case is permitted, and there is no code in this
section's blocks that falls outside those two. The previous wording, *"none is used inline without
being declared here first"*, dropped the first branch and so appeared to require a declaration for
registry codes as well.

**The case that exposed it, named rather than left implicit: `VERSION_CONFLICT`.** It is used inline in
eight endpoint blocks in this section and is declared in **no** `newerrorcode` block — **correctly**,
because it is one of the thirteen codes `FR-ADR-052` itself fixes, at **409**, sourced to `FR-ADR-035`.
Declaring it here would assert that the registry lacks a code the registry has, and would emit it a
second time as an extension of itself. **Nothing about it moves on the wire and nothing about it is a
defect** — the sentence describing the discipline was.

**The discipline is mechanical and does not rest on this paragraph.** `generate_api.py` builds its
valid-code set from the registry plus the adjudicated extensions and fails any endpoint block naming a
code outside it, with the message *"Raise a `newerrorcode` block instead of inventing one"*. That check
is what catches the next one; this paragraph only stops a reader concluding the check is missing.

```newerrorcode
{"code":"VALIDATION_FAILED","http":422,"when":"any admin request field fails its type or bound: a title too long, a runtime of zero, a negative price, a duplicate seat label, an unknown lookup id, a missing version field","raised_by":["EP-ADM-01","EP-ADM-02","EP-ADM-04","EP-ADM-05","EP-ADM-07","EP-ADM-08","EP-ADM-09","EP-ADM-10","EP-ADM-11","EP-ADM-13","EP-ADM-14","EP-ADM-16","EP-ADM-17","EP-ADM-19","EP-ADM-20","EP-ADM-23","EP-ADM-24","EP-ADM-26","EP-ADM-27"],"why_needed":"FR-ADR-052's registry has no general field-validation code. Its 422 codes are SEAT_LIMIT_EXCEEDED and IDEMPOTENCY_KEY_REUSED, both specific to the booking path. Every admin form needs one, and inventing one per field is how a code list grows into a hundred one-off strings."}
```

```newerrorcode
{"code":"FORBIDDEN","http":403,"when":"the caller is authenticated but their role is not admin, and the /api/admin router dependency refuses before the handler is entered. This reaches EVERY endpoint on the router, DELETE included: a non-admin calling DELETE /api/admin/seats/{seat_id} (EP-ADM-21) is refused here with FORBIDDEN, because the dependency runs before the route's own preconditions. What is NOT returned here is a delete addressed at one of the never-deleted entities - movie, showtime, screen, cinema and the four lookup vocabularies - because no DELETE route is mounted for those, so nothing is entered and the global handler answers 405 METHOD_NOT_ALLOWED (P-ADM-20, P-XCT-11). The earlier revision of this clause said no DELETE route is mounted at all, which was false while EP-ADM-21 sat in this block's own raised_by list","raised_by":["EP-ADM-01","EP-ADM-02","EP-ADM-03","EP-ADM-04","EP-ADM-05","EP-ADM-06","EP-ADM-07","EP-ADM-08","EP-ADM-09","EP-ADM-10","EP-ADM-11","EP-ADM-12","EP-ADM-13","EP-ADM-14","EP-ADM-15","EP-ADM-16","EP-ADM-17","EP-ADM-18","EP-ADM-19","EP-ADM-20","EP-ADM-21","EP-ADM-22","EP-ADM-23","EP-ADM-24","EP-ADM-25","EP-ADM-26","EP-ADM-27"],"why_needed":"FR-ADR-052 has AUTH_REQUIRED for a caller with no account and HOLD_NOT_OWNED for a caller who does not own a specific lock. It has nothing for an authenticated caller whose role is wrong, which is the single most-returned failure in this epic and the one SRC-001 §7.4 exists to produce."}
```

```newerrorcode
{"code":"NOT_FOUND","http":404,"when":"a path parameter names an id that does not exist, a path parameter names a value outside a closed set of addresses such as the lookup {kind}, or a route that does not exist is requested - including any withdraw-showtime address, which returns the same answer as any other address that does not exist","raised_by":["EP-ADM-03","EP-ADM-04","EP-ADM-05","EP-ADM-06","EP-ADM-07","EP-ADM-08","EP-ADM-09","EP-ADM-10","EP-ADM-11","EP-ADM-14","EP-ADM-17","EP-ADM-18","EP-ADM-19","EP-ADM-20","EP-ADM-21","EP-ADM-24","EP-ADM-25","EP-ADM-26","EP-ADM-27"],"why_needed":"The registry has no not-found code at all. Every admin endpoint addressed by id needs one, and returning 500 or 422 for a missing row misreports an ordinary condition as a fault."}
```

```newerrorcode
{"code":"LAYOUT_FROZEN","http":409,"when":"a seat's row_label, seat_number or seat_category_id is changed, or a seat is deleted, once any showtime row exists on that hall (FR-ADR-022). Also returned when a showtime is created on a hall that is out of service or has no seats in service, and when a seat's service state is set to the value it already holds","raised_by":["EP-ADM-10","EP-ADM-20","EP-ADM-21"],"why_needed":"FR-ADR-022 requires a 409 that names the constraint. VERSION_CONFLICT is wrong - nothing raced; the edit is permanently refused for this hall and reloading will not help. The interface must be able to tell the two apart, because one says reload and the other says this can never be done."}
```

```newerrorcode
{"code":"PUBLISH_BLOCKED","http":409,"when":"a publish is attempted on a film with no poster or no display window, or on one already published; or an unpublish is attempted on a film that is not published","raised_by":["EP-ADM-07","EP-ADM-08"],"why_needed":"FR-ADR-021 makes 'no poster' a publish-time check and not a column constraint, so it is a state conflict and not a field-validation failure. VALIDATION_FAILED would tell the admin to fix a field on this form; the fix is on the poster panel or the window fields, and details names which."}
```

```newerrorcode
{"code":"SHOWTIME_OVERLAP","http":409,"when":"a showtime is created or edited so that its half-open interval overlaps an existing showtime on the same screen. details is {\"conflicts\": [{\"showtime_id\": integer, \"movie_title\": string, \"starts_at\": ISO-8601 local, \"ends_at\": ISO-8601 local}]} - ALWAYS the array, one entry per conflicting showtime, one entry long in the ordinary case. showtime_id is what SCR-ADM-03 outlines the conflicting day-strip row with, so the payload is load-bearing and not diagnostic (P-ADM-08)","raised_by":["EP-ADM-10","EP-ADM-11"],"why_needed":"This is the schedule-side analogue of SEAT_UNAVAILABLE and it needs its own code for the same reason: the interface must highlight the conflicting rows in the day strip rather than show a generic message. It is not a validation failure - every field was individually valid."}
```

```newerrorcode
{"code":"PAYLOAD_TOO_LARGE","http":413,"when":"a poster upload declares a Content-Length above the 2 MB limit. Rejected at the header, before the body is read","raised_by":["EP-ADM-05"],"why_needed":"FR-ADR-061 requires the size check at the header so the body is never buffered. 413 is the status that carries that meaning, and returning 422 would imply the file was read and examined."}
```

```newerrorcode
{"code":"UNSUPPORTED_MEDIA_TYPE","http":415,"when":"a poster upload declares a type outside image/jpeg, image/png and image/webp; or its leading bytes do not match the declared type; or it cannot be decoded as an image","raised_by":["EP-ADM-05"],"why_needed":"FR-ADR-061 requires three separate checks - declared type, magic bytes, decodability - and all three mean the same thing to the admin: this file is not a usable image of an accepted type. One code with three messages is right; three codes for one remedy is not."}
```

---

## Lane notes

### Article X candidates raised by this lane

Seven. Each is a question no frozen source, client ruling or `APPROVED` record answers, and each was
left open rather than filled with a plausible figure.

**1. `PROPOSED-TURNAROUND-01` — how long between two showtimes in one hall?**
`P-ADM-08` refuses overlapping intervals, which is derivable from `SRC-001 §2.2` and `§7.1`. **It
requires no gap**, and it accepts a showtime that starts at the exact instant the previous one ends.
A real cinema needs changeover time: the audience leaves, the room is cleaned, the next audience is
seated. **No source states a figure.** `SRC-002 §8.1.1`'s seven minutes — corrected by erratum `E-1` —
is exactly what happens when a
number like this is invented once and then cited as a requirement, so none is invented. **Class:
product.** The interface's mitigation — showing the gap in minutes between consecutive shows,
`0 min` in `--fr-countdown-urgent` — is the most this specification can honestly do without a ruling.

**2. `PROPOSED-PRICEBOUND-01` — what is the highest ticket price and the highest category uplift?**
`P-ADM-10` bounds `base_price_paise` at `>= 1` (derived) and at a 64-bit arithmetic ceiling
(technical). `P-ADM-11` bounds `uplift_basis_points` at `>= 0` (derived from `OPEN-PRICE-02`, no
discounts) and at the same arithmetic ceiling. **Neither has a business upper bound**, so a mistyped
base price of `2500000` instead of `25000` is accepted, and every seat on that showtime is priced at a
hundred times its intended figure until somebody notices. **Class: reserved, money.** A sanity ceiling
is a money decision and no model may set one.

**3. `PROPOSED-ADMINRATE-01` — should admin endpoints be rate limited, and at what?**
`FR-ADR-058`'s table lists seat hold, booking confirm, login, registration, password reset, booking
lookup and seat map. **It lists no admin endpoint.** Every block in `S6` therefore reads
`rate_limit: none`, and that is a report of the record rather than a choice made here. Two of them
deserve a bucket: `EP-ADM-05` writes to a 5 GB S3 allowance with no deletion path (`FR-ADR-012`), and
`EP-ADM-02` and `EP-ADM-10` write to tables that are never pruned. **Class: technical**, so the build
session could decide it — but the *numbers* would be invented, and `FR-ADR-058` is an `APPROVED` record
whose table this lane may not silently extend. Raised for the merge pass to route.

**4. `PROPOSED-ADMINCOUNT-01` — how is a second admin account created?**
`P-ADM-17` creates managers and only managers, deliberately: an endpoint that accepts a role string is
one bug away from creating an admin. The first admin comes from the seed script (`FR-ADR-067`).
**No source says how a second one is created**, and `SRC-003 OPEN-ROLE-01`'s *"only 1 admin persona"*
can be read as ruling that there is exactly one. **Class: reserved, product.** The interim position is
fail-closed: no endpoint creates an admin, and a second one is a deliberate database action.

**5. `PROPOSED-SEATBATCH-01` — is there a bulk way to lay out a hall?**
`EP-ADM-19` accepts up to 500 seats in one call, so a 220-seat hall is one request. But **every seat's
label, number and two coordinates are still typed by a person**, and `P-ADM-14` makes a mistyped label
permanent the moment the first showtime exists. A row-generator ("rows A to L, 18 seats each, all
Standard") would remove most of that risk. **Nobody asked for one** and Art VII.6 forbids building
what nobody asked for, so it is not specified. **Class: product**, raised because the cost of not
having it lands on `R-ADM-04`'s permanent freeze.

**6. `PROPOSED-CINEMA-01` — how is a second venue created, and does the client want one?**
`P-ADM-25` gives the `cinema` entity a list and an edit and **no create**. The one row comes from the
seed (`FR-ADR-067`). **No source says how a second appears**, and it is not a technical question: a
second venue turns the customer-facing cinema filter back on (`SRC-001 §5.1.3`, `FR-ADR-046`), gives
the dashboard a second scope, and reopens whether manager scoping attaches to the screen or to the
venue (`FR-ADR-011`). `SRC-003 C-2` is itself `PROVISIONAL` on there being one. **Class: reserved,
product** — it changes what the product is, which `R-CON-11` reserves. The interim position is
fail-closed and matches `PROPOSED-ADMINCOUNT-01`'s: no endpoint creates one, a second row is a
deliberate database action, and **nothing in the design blocks it** — the endpoints are plural, the
zone is per row, and `EP-ADM-16` keeps `cinema_id` required.

**7. `PROPOSED-SEATALPHA-01` — which letters may a row label use, and is `I` one of them?**
`P-XCT-30` lays every **seeded** hall out with row letters that skip `I`, because `I` and `1` are
misread on a printed row marker and at 375 pixels. **`P-ADM-13`'s bound is `1..4` letters and refuses
nothing**, so an admin laying a hall out by hand may type row `I`, and `EP-ADM-19` and `EP-ADM-20`
accept it. The label is printed on the emailed receipt and read aloud at the door, and `P-ADM-14`
freezes it permanently the moment the hall's first showtime exists — **so the correction window
closes before anyone reads a receipt.** **No source states a permitted alphabet**, the seed's skip is
demonstration-data convention, and banning a letter is not free either: a hall whose physical markers
read `I` could not be described accurately. **Class: product.** Distinct from `OPEN-SEATLABEL-01`,
which asks about **case** and is `reserved: irreversible`; this one asks which letters exist at all,
and neither answers the other.

### Judgment calls recorded by the iteration-6 to iteration-9 fix passes

Eight zero-context readers were run against the assembled PRD across five passes, each independently, and
each pass fixed the **union** of what its readers found rather than either list alone — because the
overlap between two readers of the same document was small every time until the fifth pass, when the two
readers agreed for the first time — which is the first evidence that the remaining set is finite rather
than a fresh sample each pass.
**Twenty-seven adjudicated decisions touched this section** across the five, and they produced the
twenty-eight `[JUDGMENT CALL]` lines below — one more than the count of decisions, because the seat-set
decision needed a lock discipline that is a separate call and is recorded separately rather than folded
into it. Two further decisions needed no change here at all, because what they asked for was already
written: the no-active-seats guarantee (`P-ADM-07` exception 5, and again at `P-ADM-14`) and the
verbatim storage of the display window, which `P-ADM-04` now states explicitly at the write so the read
path has something unambiguous to cite.

Each line is made under Art III.9 and states what was decided, why, and the fact that it is reversible.
**Rows 7, 8 and 9 carry a tie-break `S1.2` does not itself state**; those sentences are written at the
point of each change so the merge owner can lift them into `S1.2.1` as named cases. **Row 17 is the one
item this section did not implement as briefed**, and it says why on its own row.
**None of them is a reserved matter**: none touches money, anything irreversible or public, a secret,
a legal question, the constitution, what the product is, or a quality check — and none waives one.

| # | `[JUDGMENT CALL]` — what was decided | Why | Reversibility |
|---|---|---|---|
| 1 | **`P-ADM-23` stops claiming that no lookup vocabulary rows are seeded, and defers to `P-XCT-30` for what is.** The operationally important half stands: the film form cannot be completed until a row exists in every vocabulary that film needs. | The old sentence was a claim about another lane's seed script made by a section that does not own it, and it had become false. Deferring names one owner and leaves one copy of the list. | Reversible in one paragraph. **Nothing in this section behaves differently according to where a row came from**, so the deferral cannot leak into behaviour. |
| 2 | **A showtime's seat set is materialised at showtime creation, in the same transaction, and `P-ADM-14` owns that rule.** One `showtime_seat` row per then-active seat; `seat_count_at_creation` is the count of those rows. | The five words *"available on future showtimes, absent from past ones"* were a phrase, not a mechanism, and every predicate computed from the seat's current flags gets seat restoration wrong and lets occupancy exceed 100 %. | Reversible, but **not cheaply**: it is a table. The decision is recorded with the rejected alternative and its exact failing case (`P-ADM-14`, step T5 of the worked example) so a reversal is argued against evidence rather than re-derived. |
| 3 | **Every seat write takes `SELECT ... FOR UPDATE` on the `screen` row**, unconditionally, including on a hall with no showtimes. | Without it, a seat added in the same millisecond as a showtime creation is neither reliably in the new seat set nor reliably out of it. Stricter than anything ruled, so it needs no signature (Art III.10). | Reversible: one lock statement. |
| 4 | **`P-ADM-02` and `P-ADM-06` keep the word "immediately" and point at `P-BRW-12` for the mechanism**, rather than restating it. | Two copies of a cache-invalidation rule is two things to keep in step, and the rule is another lane's to own. | Reversible in two sentences. |
| 5 | **`version` is a required second form part on the poster upload (`EP-ADM-05`), checked before any byte is streamed to S3**, and `P-ADM-12` gains the poster exception row using the film sentence it already publishes. | `P-ADM-12` already required `version` on every `movie` write and the endpoint's shape could not carry one — the shape was the defect. Checking it before the stream means a stale upload leaves no orphan object in a bucket nothing ever deletes from. | Reversible: the field and the check. The **ordering** is the part not to reverse casually — reversing it costs an unreferenced S3 object per stale upload, permanently. |
| 6 | **`include_past` on `EP-ADM-09` means "the advertised start instant is at or before now", inclusive, and `P-ADM-09` owns the admin showtime list.** | The parameter had no meaning anywhere and three readings gave three result sets. Start is a property of the showtime; the sales cut-off is a customer-facing boundary that moves with configuration, and a list defined against it changes membership when nothing about the showtime changed. | Reversible: it is one predicate and one default. The default is `true`, so a reversal cannot retroactively have hidden anything from an admin. |
| 7 | **`SCR-ADM-03` gains an optional format select**, populated from the `format` vocabulary, defaulting to none, with the film editor's existing empty-select convention and one stated difference: it does not block submission. | `P-ADM-07` calls itself the only writer of `showtime.format_id` and the screen drew no control, so the field could never be set and the customer's format filter could never render. Tie-break stated at the site: **behaviour outranks rendering on whether a capability exists.** | Reversible: one control and five copy strings. Removing it re-creates the defect, which is why the reason is written next to the control. |
| 8 | **`SCR-ADM-07` gains Withdraw and Restore actions, a withdrawn-row treatment built from existing tokens, and no filter** — both active and withdrawn rows always list. | `P-ADM-24`'s happy path names this screen and the screen had no control, leaving `EP-ADM-27` and eight audit actions unreachable. No filter, because a withdrawn row that cannot be seen cannot be restored. Same tie-break as row 7. | Reversible: two actions, one treatment, six copy strings. **The two absences it does not touch — no delete control, no edit control — stay written and stay true.** |
| 9 | **`EP-ADM-24`'s `409` becomes `422` and `P-ADM-17` exception 6 becomes `422 VALIDATION_FAILED`**, with the verbatim message unchanged and no new error code minted. | Three sources gave three answers for one condition. Tie-break stated at the site: **the generated registry fixes a code's status and a block may not contradict it.** | Reversible only by changing the registry, which is a different decision in a different file. As written it is a correction, not a choice. |
| 10 | **Every bound on a `PATCH` is evaluated against the merged row, stated once at the head of `S4` and applied at both paired bounds** (`display_from`/`display_until`, `starts_at`/`ends_at`). | Both halves of each pair are optional, so a bound written on the field can honestly be read as applying only to what was submitted — and read that way, one field sent alone stores an inverted window or a negative-duration showtime with no error. | Reversible in wording only; the alternative reading is a defect rather than a design, so there is nothing to reverse *to*. |
| 11 | **The Formats tab renders its reference count**, counting showtimes rather than films, and the old rationale for rendering none is removed. | The stated reason — that this epic specifies no entity referencing a format row — was falsified by `EP-ADM-25`, which computes the count for all four kinds from `showtime.format_id`. A rendering choice may stand on a stale reason for exactly as long as nobody checks. | Reversible: one table row and two copy strings. |
| 12 | **Every delete refusal in this section is `405 METHOD_NOT_ALLOWED` from a global handler, with a generic entity-blind message `E8` publishes** — six exception rows changed, three endpoint blocks' 403 rows narrowed, and every entity-specific sentence moved onto the screen that already carries a never-deleted note. | The section held three answers for one question and one of them was inside a single row: `P-ADM-20` published a `403` with an entity-naming message **and** said no delete route exists and that the absence is the control. Both could not be true. The absence wins; the envelope is preserved by a handler rather than by mounting the route the rule exists to refuse. | Reversible only by mounting a `DELETE` route, which is the thing being refused. **The reversal is therefore the defect**, which is why the reason sits next to the rows rather than only here. |
| 13 | **One audit row per `action` kind that actually changed**, stated generally on `P-ADM-19` and worked through for six endpoints. | Two rows already said it for their own entity and the movie `PATCH` — the one endpoint where the merge happens — said nothing. `EP-RPT-04` filters on `action`, so the merged reading makes a window-change filter match nothing for any request that also touched a title. | Reversible in wording; the merged reading is a defect rather than a design, so there is nothing to reverse to. |
| 14 | **A `PATCH` that changes nothing returns 200, writes nothing, does not bump `version` and writes no audit row** — `P-ADM-24`'s lookup-row answer generalised on `P-ADM-12` to every versioned entity, with the version check still running first. | The other reading lets an admin who changed nothing invalidate every other open form on that row, so a second admin is told "changed by someone else" about a change that never happened — and a concurrency control that fires on a non-change teaches its users to ignore it. | Reversible: one rule. The ordering — version first, no-op second — is the part not to reverse casually, because reversing it hides a row that moved. |
| 15 | **`reference_count` counts every referencing row regardless of visibility**, and `EP-BRW-07`'s visible-only count is deliberately the other rule. | The count answers what an entry is holding up, and a draft film holds it up exactly as much as a published one. The customer endpoint drives a filter menu, where a value returning nothing is a broken control. | Reversible: one predicate on each. **The pair must move together or the contrast sentence becomes false.** |
| 16 | **`EP-ADM-01` pages `created_at DESC, id DESC`.** | It was the only paged endpoint in the product without a total order, and the seed creates its films in one transaction, so the tie is not hypothetical. Same fix and same stated reason as `P-BRW-03` and `P-ACC-11`. | Reversible, and reversing it re-creates a defect that only shows up as a film appearing twice while another never appears. |
| 18 | **Five screens gained a control they specified and never published, and one gained a control it never had.** `SCR-ADM-04` gains a create action, `SCR-ADM-03` a submit and a cancel, `SCR-ADM-05` a Save, an Add seat and a **Return hall to service**, `SCR-ADM-02` the publish confirmation, `SCR-ADM-01` a pager. | Six findings were one defect: **a screen names a control and owes that control's words**. `SCR-ADM-04`'s was the sharpest — with no create action, an unseeded database had no seat category, therefore no seat, therefore no showtime, and `EP-ADM-13` had no caller at all. `SCR-ADM-05`'s reactivation was the same shape: `screen.reactivated` was in the audit vocabulary with nothing able to write it. | Each is reversible as one control and its strings. **Reversing any of them re-creates the defect**, which is why the reason sits beside the control rather than only here. |
| 19 | **One audit row per changed row, so a 220-seat batch writes 220 `seat.created` rows.** | `entity_id` is the primary key of the changed row and one column cannot carry 220 of them. `P-ADM-17` already ruled the multi-entity case this way. The cost — the change log's first page being seat creations for a while — is stated rather than hidden, and it is survivable because the log is filtered and paginated. | Reversible only by making `entity_id` lie about what changed, which is not a reversal but a different defect. |
| 20 | **Field validation runs before the no-op check: `version` -> validation -> no-op -> write.** | An admin form round-trips a whole row, so it resubmits values that have since been withdrawn. A `200` there tells the admin the form is fine while the next edit to any other field will be refused. The no-op rule exists to keep the change log clean, not to accept values the system would otherwise refuse. | Reversible: it is an ordering. Reversing it makes the stored value the reason a value is acceptable, which is backwards. |
| 21 | **`P-ADM-13` exceptions 4 and 5 gain plurals**, naming every offending seat in submitted order, joined `A, B and C` — except exception 5, which names a **count** because a grid coordinate has no label a person recognises. | `EP-ADM-19` takes up to 500 seats, `SCR-XCT-01` makes the server render `message`, and a server with only a singular has nothing to render for the ordinary batch case. Same shape as the hold path's `SEAT_UNAVAILABLE` pair, deliberately. | Reversible: four strings. The singular/plural boundary is a rule — one, versus two or more — not a judgement, so nothing is left to the implementer. |
| 22 | **Four date strings corrected to `S7.19`'s five forms**, and `P-ADM-22`'s seeded-film sentence corrected so the seeded catalogue can be visible. | The four carried a 24-hour clock, a month spelled in full, or a printed zone outside the one surface rule 2 allows it on — and `S7.19`'s own audit table reached eight examples and missed these. `P-ADM-22`'s sentence made publication impossible under `P-ADM-05`, so a seeded database showed customers nothing. | The date strings are reversible as copy. **The `P-ADM-22` change narrows a constraint and says so at the site**, so a reader comparing the two sentences cannot mistake it for a rule quietly relaxed. |
| 23 | **`/admin/halls` becomes a hall list with a "New hall" action; `/admin/halls/{screen_id}` stays the editor.** | This screen claimed two routes and specified one, so `EP-ADM-15` and `EP-ADM-16` had no caller and `screen.created` had no writer — **the third instance of this defect in this file**, after `SCR-ADM-04`'s create action and `SCR-ADM-05`'s return-to-service. Every sibling screen already had its create control. | Reversible as one list and eleven strings. **The pattern is what to keep**: a route named in the shell owes a screen, and an endpoint with no caller is the symptom to search for. |
| 24 | **Five admin lists get a total order** — `name ASC, id ASC` for categories, halls and venues, `email ASC, user_id ASC` for managers, **`grid_row ASC, grid_col ASC, id ASC` for seats**. | The file argues three separate times that an unstated order shuffles between requests; these five stated none. Seats order by the grid because **a seat list read by a human is read as a hall, not as an alphabet**, and the two orders differ wherever a label does not follow the grid — which `P-ADM-14` permits, since coordinates may change and labels may not. | Reversible per endpoint. The seat ordering is the one not to reverse casually: alphabetical seat order renders a hall no admin recognises. |
| 25 | **Admin datetimes are naive local only; a `Z`, an offset or a zone name is `422` and is never coerced.** | The bounds said "local date and time in Asia/Kolkata" and nothing said what a zone-carrying string does. Coercion is silent by construction: a script sending `18:30Z` stores `00:00` the next local day and nobody is told. Same strictness `E1 P-BRW-04` already applies to `date`, in the same words. | Reversible: one parse mode. **The rule is invisible from the interface**, which submits naive values by construction — it exists for everything that is not the form. |
| 26 | **`SHOWTIME_OVERLAP`'s `details` is `{"conflicts": [{showtime_id, movie_title, starts_at, ends_at}]}`, always the array.** | `P-ADM-08` required the payload and named no key; `SCR-ADM-03` outlines the conflicting row from `showtime_id`, so it is load-bearing rather than diagnostic. Always an array so the interface reads one shape and the entry count distinguishes the two exceptions. | Reversible as a shape, but the interface depends on the key names, so a rename is a coordinated change and not a local one. |
| 27 | **`seat` is deliberately outside the no-op `200` rule, scoped to `is_active`.** | The rule governs **versioned** entities and a seat has no `version` — `EP-ADM-20` accepts none — so there is nothing for a no-op to protect. The toggle asserts a state rather than edits a field, and `P-ADM-15` already publishes "Seat C12 is already out of service.", which is the useful answer to a stale grid. An unchanged `grid_row` is still an ordinary `200` no-op. | Reversible, and reversing it deletes a published sentence that exists for a reason. The scoping to `is_active` is what keeps it a rule rather than an exemption. |
| 28 | **Every count-interpolated string in this section publishes a singular, a plural and a zero.** | An implementer who finds only the plural ships "Used by 1 films". The zero form is its own sentence rather than "0 films", because zero is the state an admin acts on. **"42 of 150 seats" is stated as needing no singular**, because the noun agrees with the total — so its absence reads as decided. | Reversible as copy. |
| 17 | **The new-error-code discipline is restated as two branches — registry member, or declared here — and `VERSION_CONFLICT` is named as a registry member needing no block.** | The old sentence said "none is used inline without being declared here first", which read as requiring a declaration for registry codes too and made a correct absence look like a hole. **This is the one item this pass did not implement as briefed**, and the reason is in the report and below. | Reversible: one paragraph. **Nothing moved on the wire and nothing needed to.** |

### Assumptions I had to flag

| Flag | What it is | Where it bites in this section |
|---|---|---|
| **`ASSUMED`** | **Seat category names** — Standard, Premium, Recliner. The client said "you pick" (`SRC-003 OPEN-SEAT-01`, `FR-ADR-016`) | `P-ADM-11`, `SCR-ADM-04`. The names are rows in a table, not an enum, and `SCR-ADM-04` carries a note telling the client they were chosen by the build session and may be renamed freely. **Nothing validates against them.** |
| **`ASSUMED`** | **Hall sizes** — 90/120/150/180/200/220 seats. The client said "pick random" (`SRC-003 OPEN-SCALE-02`, `FR-ADR-016`) | `P-ADM-13`, and `P-ADM-14`'s seat-set worked example and its storage arithmetic, both of which are illustrative and validate nothing. **Nothing validates a hall's seat count against those figures.** They are what the seed script creates and what the seat map is designed against, and nothing more. |
| **`PROVISIONAL`** | **The base price is per showtime**, not global (`SRC-003 OPEN-PRICE-01`, `FR-ADR-037`) | `P-ADM-10`, `P-ADM-07`, `SCR-ADM-03`, `EP-ADM-10`, `EP-ADM-11`. If reversed, `base_price_paise` moves off the `showtime` row to a configuration value and every showtime is backfilled. Carried as a boxed warning on `P-ADM-10`. |
| **`PROVISIONAL`** | **Four roles, and a manager role exists at all** (`SRC-003 C-1`, `FR-ADR-009`) | `P-ADM-17`, `P-ADM-18`, `SCR-ADM-06`, `EP-ADM-22` to `EP-ADM-24`. If reversed to three roles, the manager role value, the assignment table and those three endpoints are removed and the dashboard is served to admins with a hall filter. |
| **`PROVISIONAL`** | **One cinema with six screens** (`SRC-003 C-2`, `FR-ADR-010`) | `P-ADM-13`, `P-ADM-25`, `P-ADM-26`, `SCR-ADM-05`, `SCR-ADM-08`, `EP-ADM-16`, `EP-ADM-28`, `EP-ADM-29`. A `screen` carries a `cinema_id` and `EP-ADM-16` requires one, so a second venue costs an insert and not a migration. **Every surface added for the entity is plural** — `EP-ADM-28` returns an array, `EP-ADM-29` is keyed on an id, `SCR-ADM-08` is a list, and the zone is a column on the row rather than a global — so a reversal to several venues needs a create endpoint and nothing else. |
| **`PROVISIONAL`** | **Sales close 15 minutes *after* the advertised start** (`SRC-003 OPEN-BOOK-03`, `FR-ADR-042`) | `P-ADM-07`'s worked example, `SCR-ADM-03`'s cut-off note, and `P-ADM-09`'s `include_past` example — where it is the reason a started showtime can still be selling, and therefore the reason the filter defaults to showing everything. It is a signed configuration value; reversing it changes those wordings and nothing else in this section, and **`include_past` is deliberately not defined against the cut-off**, so no reversal moves a showtime in or out of that list. |
| **`OPEN`** | **`OPEN-ATTRIB-01`** — where the client's posters and titles come from (`FR-ADR-007`) | `P-ADM-22`. Every example in this document uses `DEMO MOVIE 01`-style placeholders; no real title, poster, brand or source appears anywhere. |
| **`OPEN`** | **`OPEN-SHOWCANCEL-01`** — withdrawing a showtime with paid bookings (`FR-ADR-023`) | `P-ADM-21`. No endpoint, no screen, no column, no disabled control, and no wording. |
| **technical** | Every bound marked **technical** in a validation table — title length, synopsis length, row-label length, hall-name length, batch sizes, poster pixel range, arithmetic ceilings | Marked inline on every row. **None is a business figure and nothing downstream may treat one as ruled.** |

### Where I would have had to guess and did not

**1. A turnaround figure between showtimes.** The most tempting guess in this lane. 15 minutes is what
a person would write and it would be indistinguishable from a requirement within two documents. Left
at zero, with the arithmetic shown in `P-ADM-08`'s worked example so the client can see exactly what
they are accepting. `PROPOSED-TURNAROUND-01`.

**2. A maximum ticket price and a maximum category uplift.** Both bounded only by 64-bit arithmetic,
and both marked technical. A "sensible" ceiling of, say, ₹5,000 would be a money decision.
`PROPOSED-PRICEBOUND-01`.

**3. Rate limits for admin endpoints.** `FR-ADR-058` is an `APPROVED` record with a table, and this
lane may not extend it with numbers of its own. Every block says `none` and says why.
`PROPOSED-ADMINRATE-01`.

**4. How a second admin account is created.** No endpoint invented, no role selector added.
`PROPOSED-ADMINCOUNT-01`.

**5. What happens to a customer whose showtime is withdrawn.** Not one sentence written, not one
column reserved, not one disabled control rendered. `P-ADM-21`.

**6. Whether the admin sets a manager's initial password.** No source says. Rather than invent an
invite email or an admin-typed credential, `P-ADM-17` reuses the password-reset flow `FR-ADR-050`
already specifies. Recorded as a judgment call and marked stricter, not as a ruled fact.

**7. Which fields beyond the poster block a publish.** `FR-ADR-021` names the poster only. This lane
also requires a display window, on the derivation that publishing without one produces a film that can
never be seen with no signal to the admin. **Marked as a build-session judgment on `P-ADM-05`, not
presented as ruled**, and reversible.

**8. A seat-layout generator.** Not built, not designed, not sketched. `PROPOSED-SEATBATCH-01`.

**9. Whether a lookup vocabulary entry can be withdrawn or renamed.** `P-ADM-23` creates entries and
reads them, and does neither of those two things. Deletion is impossible under `FR-ADR-012`; **no
source says a vocabulary entry ever needs retiring or renaming**, and Art VII.6 forbids building what
nobody asked for. The `is_active` column is on the row from the first migration so that adding
withdrawal later is an endpoint and not a migration over rows that films already reference, and
`P-ADM-23` states exactly what withdrawing one would do. **Recorded as a gap that v1 does not fill,
not as a capability that exists.**

**10. How a second venue is created.** No create endpoint invented, no "add venue" control drawn, not
even a disabled one. `PROPOSED-CINEMA-01`.

**11. What a withdrawn venue would mean.** `P-ADM-25` gives the cinema no withdraw control and no
`is_active` semantics, because **no source says what would happen to the showtimes on its halls**. A
plausible answer — the halls stop accepting new showtimes, existing bookings stand — is exactly the
shape of answer `P-ADM-21` refuses to write for a showtime. Not written, not sketched, not reserved.

**12. Whether a venue's zone change should be blocked while showtimes exist.** It is not blocked. The
alternative would freeze the zone permanently after the first showtime, which makes a typo in a zone
name uncorrectable — and unlike a seat number, the zone rewrites nothing and is fully reversible by
editing it back. **The interface states the consequence with a count and requires a confirmation**
(`SCR-ADM-08`), which is the same treatment `SCR-ADM-04` gives the uplift, and it is the most this
specification can honestly do without a ruling.

**13. A business ceiling on how far a zone may move.** None. Any zone the zone database resolves is
accepted, including one on the other side of the world. **A "must be within India" rule would be
inventing a scope constraint**, and `SRC-001 §6.6` plus `PROPOSED-CINEMA-01` both point the other way.

### Contradictions found against a frozen source, an ADR or the BRD

**1. `SRC-001 §5.5.1` against `SRC-003 OPEN-OPS-03` — already adjudicated, restated because it will be
re-introduced.** `§5.5.1` reads "**Manager** creates showtimes by choosing a movie, screen, date, time,
and price band". `SRC-003 OPEN-OPS-03` puts every privileged write on the admin alone. **The BRD
records this at `R-ADM-03`'s note and in `B7.3`, so it is not a new finding** — it is flagged because a
developer reading `§5.5.1` in isolation will build the manager endpoint, and `FR-ADR-009` calls that a
defect. `SRC-001 §4.4` carries the same problem for pricing and occupancy.

**2. `SRC-001 §5.5.4` is withdrawn but its shape survives in a way that misleads.** Erratum `E-8`
withdraws "administrator approves imported movies". **Nothing is imported and there is nothing to
approve** — but `P-ADM-05` is still an approval-shaped action on an admin's own draft. They are
different: `E-8` removes a *review of someone else's data*; publication is the author's own final step.
Named so nobody reads `P-ADM-05` as `§5.5.4` surviving.

**3. `FR-ADR-012` against `FR-ADR-022`, on deleting a seat — both `APPROVED`, and they are reconciled,
not contradictory.** `FR-ADR-012` says nothing is ever deleted. `FR-ADR-022` says *"A screen with no
showtimes is freely editable, including deleting seats."* `FR-ADR-012` itself resolves it: its rule is
scoped to *"the record of what happened"*, and it names manager assignments and cache entries as rows
that may be removed. `P-ADM-13` and `EP-ADM-21` follow `FR-ADR-022`. **This is stated because a
reviewer holding only `FR-ADR-012` and the BRD's `R-ADM-07` will read `EP-ADM-21` as a violation**, and
it is not one.

**4. `COMPONENTS.md §11` calls the seat-category names by their `ASSUMED` values without flagging
them.** `§11` and `§10` name Standard, Premium and Recliner in passing. `FR-ADR-016` and
`FR-ADR-037` both require them to be flagged as assumed each time they matter. **Not a contradiction of
substance** — the design system is describing a component, not ruling a name — but this lane carries
the flag explicitly on `P-ADM-11` and on `SCR-ADM-04` rather than relying on the design system to.

**5. `SRC-002 §6.4` names `docs/deployment-tasks.md`; this repository uses `docs/30 Deployment/`.**
Already resolved in `FR-ADR-008` and not re-litigated. Noted only because `P-ADM-03`'s S3 bucket and
its IAM grant (`s3:PutObject` and `s3:GetObject` on `arn:aws:s3:::<bucket>/posters/*` and nothing
wider) are **Zone C prep-queue items with a *needed by* stage of Phase 6**, and this lane is where that
dependency becomes visible. It is owed as advance notice under `SRC-002 §6.4.2` and `FR-ADR-061`.

**6. No contradiction found on the pricing formula, the rounding rule, the audit shape, the layout
freeze, or the role model.** Every figure in this section traces to `FR-ADR-037`, `FR-ADR-038`,
`FR-ADR-019`, `FR-ADR-022` or `FR-ADR-009` and none of them disagrees with another. That is reported as
a result, not as an absence of looking.

**7a. Two sources of truth for the timezone, resolved in favour of the one an `APPROVED` record
already chose.** Four rows across this document require the zone to be read "from the cinema row,
never from a global constant", while the configuration inventory (`E8 S7.9`) carries
`CINEMA_TIMEZONE` as an environment variable with a default. **Neither statement was wrong and
nothing said which governed a rendered time.** `FR-ADR-018` had in fact already decided it — it lists
*"put the zone in application configuration rather than on the cinema row"* among the alternatives it
**rejected**, and gives the reason. `P-ADM-26` is that record's consequence: the row is authoritative
at read time, the variable seeds the row and is checked at boot, and no request-path code reads it.
**This is a silence being closed, not a record being re-opened**, and the inventory in `E8 S7.9`
keeps its ownership of the variable's existence, default and boot check.

**7b. `EP-ADM-16` required a `cinema_id` that no endpoint returned.** A required foreign key on a
create endpoint, an entity with no list, no create, no edit and no screen, and a hall form with no
control for it. **Not a contradiction between two statements — a missing one**, and the kind a
mechanical citation check cannot see, because every individual row resolved. Closed by `P-ADM-25`,
`SCR-ADM-08`, `EP-ADM-28` and `EP-ADM-29`, and by the venue control added to `SCR-ADM-05`.

**7c. The confirmation on `SCR-ADM-04` stated a number nothing produced.** `P-ADM-11` required a
count of affected showtimes **before** the write and `SCR-ADM-04` rendered it verbatim, but the only
endpoint returning that figure was `EP-ADM-14`, in the response to the write — after the admin had
already confirmed. `EP-ADM-12` returned a **seat** count, which is a different question and is the
figure most likely to be rendered in its place by mistake. Closed by adding
`affected_future_showtimes` and `evaluated_at_utc` to `EP-ADM-12`, and by defining the count once on
`P-ADM-11` so the pre-write and post-write figures are the same rule at two instants. **The
definition also corrects the count's own boundary**: "future" is "can still take a hold", not "has not
started", because sales close *after* the advertised start and the narrower reading understates the
blast radius on the write this document calls the most dangerous in the system.

**7. `showtime.price_changed` is used elsewhere in the assembled document and is not a member of this
epic's `action` vocabulary.** `P-ADM-19` publishes a closed vocabulary whose member is
**`showtime.base_price_changed`**, and this epic owns that vocabulary — every privileged write is an
admin write and every admin write is specified here. A change-log filter or a worked example written
against `showtime.price_changed` matches nothing and does so silently, which reads as a showtime whose
price was never changed. **The name in `P-ADM-19` is canonical and the other occurrences are the
defect.** Recorded so the correction is traceable rather than looking like a late rename.

### One thing this lane is honest about

**The poster upload path is the least testable specification in this section.** `FR-ADR-061` rejected a
local S3 stand-in, so `P-ADM-03`'s size check, magic-byte check, decode check and dimension check
cannot be exercised end to end without real AWS credentials. **Nothing in this document has been
observed running anywhere** — no application code exists yet — and every claim about S3, streaming
behaviour and presigned URLs in this section is **reasoned from the record, not observed**.
