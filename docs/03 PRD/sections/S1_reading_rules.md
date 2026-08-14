# S1 — Reading rules and the provenance grammar

```
Document .......... docs/03 PRD/FrontRow_PRD.md
Derived from ...... SRC-001 + its §E (ten errata) · SRC-002 + its §E (six errata)
                    SRC-003 (client rulings, 2026-08-14, forty rows)
                    docs/02 BRD/FrontRow_BRD.md (ninety-three R-rows)
                    the seventy-three APPROVED records in docs/01 ADR/all-ADRs/
                    docs/05 B DesignSystem/ (tokens.css, COMPONENTS.md, DESIGN-SYSTEM.md)
Written ........... 2026-08-14
Constitution ...... frontrow-constitution@0.1.0
Authority ......... CONSTITUTION.md Art II.1. Where this document and a frozen source
                    disagree, the frozen source wins and this document is the defect.
```

> **This is the document the code is written from.** The BRD says what the business needs; this says
> what the system does about it. A developer with this document, the design system and the data model
> should not have to guess.
>
> Where they would have to guess, that is a defect in this document — and the count of such places was
> measured by a fresh reader who had seen nothing else. `S8.6` reports it.

---

## S1.1 How a specification row is shaped

Every product specification is one row with a fixed shape and a fixed id, `P-XXX-nn`:

```
### `P-XXX-nn` · a short imperative name · STATUS
[SRC: the clause, ruling or record it comes from]
[BRD: the business requirement row it satisfies]

Behaviour · Who may do it · Preconditions · Happy path ·
Exception paths (every one, with the exact words the user sees) ·
Server-side validation · Worked example where it computes a number
```

**A row with no `[SRC:]` tag is a defect. A row with no `[BRD:]` tag is a defect.** Nothing in this
document is here because it seemed sensible. The two tags answer two different questions: `[SRC:]`
says *what authority permits this*, `[BRD:]` says *which business need it discharges*. A row can
resolve one and fail the other, so both are checked, in both directions (`S8.1`).

### The prefixes

| Prefix | Epic | Section |
|---|---|---|
| `P-SCP` | scope and the exclusions carried from the BRD | `S2` |
| `P-BRW` | browse and discover | `S4 / E1` |
| `P-SEA` · `P-HLD` | the seat map's interactive behaviour, and the hold | `S4 / E2` |
| `P-PAY` | checkout, money and payment | `S4 / E3` |
| `P-TKT` | the receipt, the reference and entry | `S4 / E4` |
| `P-ACC` | accounts and the customer's own bookings | `S4 / E5` |
| `P-ADM` | admin: movies, showtimes, pricing, halls | `S4 / E6` |
| `P-RPT` | the manager and admin dashboard | `S4 / E7` |
| `P-XCT` | cross-cutting floors | `S4 / E8` and `S7` |

Screens are `SCR-XXX-nn` (`S5`). Endpoints are `EP-XXX-nn` (`S6`).

**One variance, stated rather than left to be noticed.** The `P-SCP` rows in `S2` describe things that
are **not built**. They carry `[SRC:]`, `[BRD:]`, a statement of what is not built, what the system
does instead, and — because `SRC-001 §6.6` binds — **what keeps it possible later**. They have no
happy path, because there is no path.

## S1.2 Precedence — which statement wins when two places say the same thing

**This document states many facts more than once, and that is the defect class it has produced most.**
Eight lanes wrote it independently; the overlaps are where they restate each other, and a restatement
that drifts is invisible to every mechanical check, because both copies resolve, both cite correctly
and both are internally consistent.

Naming the instances has been done four times. **This is the rule that makes the next one resolvable
without a fifth pass.**

| Rank | The authority | For |
|---|---|---|
| 1 | the **`endpoint` block** in `S6` | **wire shape**: the path, the method, parameter and field names, their types and bounds, and the HTTP status of every response. `api/contract.json` is generated from these blocks, so a P-row disagreeing with one is disagreeing with the artefact the client and the server are both built from |
| 2 | the **P-row that owns the behaviour** | **behaviour, and the exact words the customer reads.** Ownership is stated on the row. Where a row says it is "the complete message set" for a code, no other section may publish a different string for that code |
| 3 | the **`SCR-` screen spec** | **layout, states and design tokens** — what renders, in which state, from which token |
| 4 | any **other passage that restates any of the above** | nothing. **A restatement carries no authority at all**, and where it differs from its owner it is a defect in the restatement, never in the owner |

**Three consequences, stated so they can be applied without judgement:**

- **A P-row and an `endpoint` block disagreeing about a status code or a field bound is resolved in
  favour of the block**, and the P-row is corrected. This is not a preference — the contract is
  generated from the block, so the block is what will exist.
- **An `endpoint` block and a P-row disagreeing about *behaviour* is resolved in favour of the
  P-row.** A block describes a shape; it does not decide what the system does.
- **A section that needs a fact it does not own should cite the owner rather than repeat it.** Every
  repetition is a copy that can go stale, and this document has proved that four times.

**Where ownership is not obvious it is declared.** The customer-facing message set for the hold codes
is owned by `P-HLD-14`; the seat-lifecycle behaviour by `P-SEA-06`'s state machine; the audit `action`
vocabulary by `P-ADM-19`; the configuration inventory by `S7.9`; the date and time rendering rule by
`S7.19`; **the duration and `Retry-After` rendering rule, and the derivation of every bucket's wait,
by `S7.20`**; **the rule that a number in customer copy which is configuration is rendered and never
typed, by `S7.21`**; the seat map's dependency-failure string by `P-BRW-12`; the error-code registry by
`api/error_codes.md`, which is generated and is **reproduced in `S6.0`** so that a reader holding
only this document can consult it. **Each of those says so on itself.**

`S7.20` and `S7.21` were added to this list after a reader pointed out that neither was on it. Every
lane had been corrected against `S7.20`, and on a literal reading of the ranking a rank-2 P-row still
outranked it — which would have un-corrected them all. **A rule that everything defers to belongs on
the list of things that own something**, and the omission is the kind this list exists to prevent.
Both sections declare the ownership on themselves, which is what made the omission findable.

### S1.2.1 Eight cases the ranking alone does not settle

The ranking orders *kinds of passage*. Eight situations need a rule of their own, and each was found
by a reader applying `S1.2` and reaching a case it did not reach.

**1. Two rank-2 rows, neither claiming ownership.** Two P-rows can both be about one behaviour with
neither declaring it owns the behaviour — the whole cross-cutting lane is structurally a set of rows
that restate other lanes' rows. **The rule: the row that specifies the behaviour in its own epic owns
it; a cross-cutting row that describes the same behaviour as a floor is a restatement and is rank 4.**
Where that is still ambiguous, **ownership is declared explicitly on the owning row** in the form
`P-HLD-14` uses, and the list above is extended. A tie that survives both of those is a defect to
raise, not a judgement for the implementer.

**2. A disagreement about existence, not value.** Rank 1 can define a shape that **cannot carry** what
rank 2 requires the client to do — a P-row demanding a state the endpoint's enum does not contain, or
a screen rendering a figure no response returns. Obeying both is impossible, so "the block wins on
shape, the row wins on behaviour" resolves nothing. **The rule: this is a defect in the pair, and it
stops.** It is not resolved by dropping the behaviour or by inventing the field — the shape is
corrected so it can carry the behaviour, and if that cannot be done without a decision nobody has
made, it becomes a `PROPOSED-` row.

**3. Where a `SCR-` row's copy stands.** Rank 3 is defined as layout, states and tokens — copy is not
in that list — yet every screen spec carries a copy table, and for some strings the screen is the only
place the string appears. **The rule: a `SCR-` row owns a customer-facing string when no P-row
publishes it, and never otherwise.** Where a P-row publishes the string, the screen renders it and may
not vary it; where no P-row does, the screen is the source and the string is as binding as any other.
A screen may never overrule a P-row on wording — that would invert rank 2.

**4. A rank-2 row says a capability exists and the rank-3 screen draws no control for it.** Rank 3 is
"what renders", which is the axis in dispute, so the ranking argues with itself. **The rule: behaviour
outranks rendering on whether a capability exists.** If a P-row says the admin does something, the
screen gains the control; the screen may decide how it looks and where it sits, never whether it is
there. Note what this does *not* license: it does not let a P-row invent copy for the control it just
created — case 3 still governs the strings, so the screen publishes them.

Two rows were built on this in the iteration-6 fix pass and each states the tie-break at its own site.
`P-ADM-07` says the admin optionally chooses a format and calls itself the only writer of
`showtime.format_id`, while `SCR-ADM-03` drew no format control — so `format_id` could never be set,
and the customer's format filter could never render. `P-ADM-24`'s happy path opens "the admin opens
the vocabulary on `SCR-ADM-07` and withdraws an entry", while `SCR-ADM-07` drew no withdraw control —
so `EP-ADM-27` was unreachable from the product and eight audit actions were unwritable. **In both,
the screen was missing something rather than disagreeing about it**, which is the tell for this case:
a screen that contradicts a P-row is case 2, a screen that is silent where a P-row acts is case 4.

**5. The generated error-code registry against a block or a row.** `S1.2` names the registry as an
owner and never ranks it, which leaves a three-way tie: an endpoint block declaring a status, a P-row
declaring a code, and `api/error_codes.md` pairing that code with a different status. **The rule: the
generated registry fixes a code's status, and neither a block nor a row may contradict it.** A code
means one thing on the wire or it means nothing — a client branches on `code` (`FR-ADR-052`), and a
code that arrives with two different statuses is two codes wearing one name.

The registry is generated, so this is not a fourth authority competing with the other three: it is the
adjudicated union of the `newerrorcode` blocks the lanes raised, and **the way to change it is to
raise one**, never to write a different pairing into a block. `P-ADM-17` and `EP-ADM-24` were the case
that found this — both said `409 VALIDATION_FAILED`, a pairing that does not exist, because the
registry fixes `VALIDATION_FAILED` at `422`. Both were corrected to `422`; no new code was minted,
because an existing one covered the case.

**6. Two rank-3 screens covering one surface.** The ranking places every `SCR-` row at rank 3, so it
cannot separate two of them — and two do collide, because some screens are **cross-cutting
registries** that publish a string or a control for a *code* across the whole product, while others
own *one surface* and publish for that surface. When they disagree, the ranking has nothing to say.
**The rule: the screen that owns the surface wins, and the cross-cutting registry defers to it by
name for that surface.** The registry keeps its entry as the rule everywhere else — it is not deleted
and it is not narrowed to nothing, because the whole point of a registry is that a code not
specifically claimed still has an answer.

`SCR-XCT-01` and `SCR-SEA-03` were the pair that found this: the registry published a
`Choose seats again` banner action for `HOLD_EXPIRED`, and the seat map said
`DEPENDENCY_UNAVAILABLE` is the only code there that carries a control. The seat map is right about
its own surface for a reason the registry could not have known — **a customer meeting `HOLD_EXPIRED`
on the seat map is already on the screen that button would send them to**, so the control navigates
nowhere. That asymmetry is why the surface owner wins: the registry knows the code, the surface knows
the situation.

**7. A step list is silent about a write a declared cross-lane owner requires.** A P-row's happy path
is written as an exhaustive ordered procedure — step 1 through step *n* — and **the exhaustive form
makes a silence read as a decision.** When another row **declares ownership** of some effect and says
it happens during that procedure, the step list's silence is not a disagreement the ranking can
settle: both rows are rank 2, both are declared owners of different things, and nothing about the
shape prevents either. **The rule: an ordered step list is authoritative on ordering and is never
authoritative on completeness.** A declared owner elsewhere adds its write to the list; the step list
does not remove it by omission. **The fix is to add the step**, so the procedure is exhaustive in
fact and not only in form.

This case has now been found twice, which is why it is a rule and not a correction. `P-PAY-10`'s
confirm transaction listed eleven steps and a sixteen-row crash table and never mentioned the
`receipt_dispatch` insert that `P-TKT-04` says happens inside it — build it from its owning row alone
and **no receipt is ever sent**. `P-HLD-01` and `P-HLD-08` list the hold and release procedures and
never mention the seat-map cache `DEL` that `P-BRW-12` — the declared owner of seat-map invalidation
— requires after both. The consequence there is smaller and still observable: the live seat map moves
in about three seconds or in about thirteen, on the one screen the product is about.

**Both were found by readers, not by the checks**, and that is the point worth keeping: a missing step
resolves cleanly, produces no contradiction a grep can find, and every gate stays green.

**8. One owning row that contradicts itself.** The ranking compares passages of different kinds, so
it has nothing to say when **a single row, declared owner of a thing, states it two ways.** There is
no second passage to outrank. **The rule: a declared owner that contradicts itself is a defect in
that row and it stops — the reader may not pick the half they prefer, and may not resolve it by
looking for a third passage elsewhere.** The fix is that the owning row states the thing once.

`P-BRW-04` was the case. It declares itself the owner of the listing's date strip and says the strip
runs *"through the latest `display_until`"* — and also that it is *"`P-BRW-06`'s rule with a maximum
applied"*, where `P-BRW-06` says the strip runs to **the day before** `display_until`, because that
value is an exclusive bound. **One day apart, in one row, about the row's own subject.** A reader
taking the first reading renders one extra day button whose only possible result is the empty state
the same row says must never be reached.

**The tell for this case is that both halves sound like the rule rather than like a restatement**,
which is what stops the ranking from firing. `S1.2` is built to compare a rule against a copy of it;
here there is no copy.

**A note on how many of these there now are.** Eight cases is more than a ranking should need, and
each was added only after a reader hit it and could not proceed. They are not refinements of the rule
— they are the places the rule does not reach, written down rather than left for the next reader to
rediscover. **If a ninth is found, add it; do not reword the ranking to pretend it covered the
case.**

## S1.2a The four citations that are permitted, and no others

| Citation | Means |
|---|---|
| `SRC-001 §n` | the client's product requirement, frozen 2026-08-14 |
| `SRC-002 §n` | the client's build mandate, frozen 2026-08-14 |
| `SRC-003 <ROW-ID>` | the client's own ruling of 2026-08-14 — the newest and most authoritative |
| `FR-ADR-nnn` | an `APPROVED` record in `docs/01 ADR/all-ADRs/`, governed by the ledger |

Every citation in this document resolves. `py tools/consistency_check.py` checks it mechanically and
its output is pasted in `S8.2` rather than claimed.

**The seventy-three records are `APPROVED` and immutable** (`CONSTITUTION.md` Art III.3). This
document never re-opens one. Where it appears to go further than a record, it is specifying the
record's consequence, not amending it.

## S1.3 Sixteen clauses are withdrawn or corrected — a spec derived from one is a defect

`SRC-003` filed **ten errata against `SRC-001` and six against `SRC-002`**. Twelve clauses of
`SRC-001 §1`–`§9` are withdrawn outright, one is corrected, and **the whole of `SRC-002 §10` is
withdrawn**. BRD `B7.3` lists every one.

The five that most often produce a wrong specification, listed here because a reader who skips `B7.3`
will otherwise write one of them:

| Clause | Erratum | What a defect derived from it looks like |
|---|---|---|
| `SRC-001 §5.6` and `SRC-002 §10` — the external movie source | withdrawn, `SRC-001 §E E-4` / `SRC-002 §E E-2` | any import, any upsert-by-external-id, any "source unavailable" path, any attribution footer |
| `SRC-002 §4.6` — a scheduler; `SRC-002 §8.1.1` — a seven-minute hold | withdrawn / corrected, `SRC-002 §E E-4` / `§E E-1` | any scheduled job at all; **any document stating seven minutes** |
| `SRC-001 §5.3.3` and `SRC-002 §8.5.1` — a scannable ticket | corrected, `SRC-001 §E E-9` / `SRC-002 §E E-5` | a QR code, a scanner, a validation endpoint, a used-ticket state |
| `SRC-001 §5.4.3` — cancel a booking | withdrawn, `SRC-001 §E E-2` | a cancellation control, a refund, a cancellation policy |
| `SRC-001 §9.5` — a third-party payment provider | withdrawn, `SRC-001 §E E-10` | any provider integration, any card field, any card-shaped fixture |

**Three clauses of `CONSTITUTION.md` are stale** and are not inherited here: Art I.6 (the win
condition still describes a scannable ticket and a scheduled import), Art V.8 (refunds described as
open when both were ruled), Art VIII.13 (the outbound list still names the withdrawn movie source).
`SRC-003` and the errata win under Art II.1. **The corrected win condition is BRD `B3.3`** and it is
carried into `S2.1`. Amending the Constitution is reserved to the client (Art XII.1), so this is
raised, not fixed.

## S1.4 Status law — the rule that matters most in this document

| Status | Meaning here |
|---|---|
| `RULED` | decided, with a citation to a frozen source or an `APPROVED` record |
| `PROVISIONAL` | a build-session reading that reconciles two of the client's own answers. **One message from the client reverses it.** It never reads as settled fact |
| `ASSUMED` | the client said "you pick". It is the build session's choice and **it never hardens into a requirement** |
| `OPEN` | genuinely unruled. It is named, never filled in. **Escalate, never invent** |

### The three `PROVISIONAL` readings, and where each bites

| Reading | Rejected alternative | Where it bites in this document |
|---|---|---|
| **Four roles**, not one (`SRC-003 C-1`, `FR-ADR-009`) | three roles, the dashboard served to admins filtered by hall | `S3`, every `P-RPT` row, every authorisation rule in `S6` |
| **One cinema with six screens** (`C-2`, `FR-ADR-010`) | several cinemas, as `SRC-001 §1.1` implies | the cinema filter's non-rendering, manager scoping attaching to the screen |
| **Sales close 15 minutes *after* the advertised start** (`OPEN-BOOK-03`, `FR-ADR-042`) | 15 minutes *before* — **half an hour apart** | every cut-off check, the closed-showtime state, the paying-past-the-cut-off edge |

### The three `ASSUMED` subjects

| Subject | The choice | The ruling |
|---|---|---|
| Hall sizes | 90 / 120 / 150 / 180 / 200 / 220 seats | "pick random" (`OPEN-SCALE-02`) |
| Peak concurrency | 50 simultaneous bookers, for the load test only | "you pick" (`OPEN-SCALE-03`) |
| Seat category names | Standard, Premium, Recliner | "you pick" (`OPEN-SEAT-01`) |

**None of the three is a requirement.** No design in this document may depend on a hall being exactly
220 seats, on there being exactly three categories, or on fifty being the real peak. The
correctness gate — exactly one winner for one seat — is **separate and is not assumed**
(`FR-ADR-034`).

### The four `OPEN` rows — named, never filled in

| Row | What this document specifies | What it must not |
|---|---|---|
| `OPEN-EMAILFAIL-01` | the surface: the reference on screen and in the bookings list independently of the email, the send state the booking record holds, the retry and dead-letter path | **any wording a customer whose receipt definitively failed would read, and any policy about money already taken** |
| `OPEN-SHOWCANCEL-01` | that **no withdraw-showtime capability exists in v1**, stated to the client rather than left to be found | any withdrawal endpoint, screen, refund or notification |
| `OPEN-ATTRIB-01` | that demonstration content is obviously demonstration content | any real title, poster, brand or source |
| `OPEN-TLS-01` | that `COOKIE_SECURE` is environment-driven and off in the deployed environment, and that the environment is never called production | that TLS is or will be terminated anywhere |

**An `OPEN` row filled in with something plausible is the cardinal failure of this project**
(`CONSTITUTION.md` Art VII.3). This project has already produced the milder version of it once: an
assumption of seven minutes in a question became a specification in the next document, and when it was
finally put to the client it came back as three.

## S1.5 Numbers, and why every one of them is worked through

`CONSTITUTION.md` Art IX.4: **every rule that computes a number states the rule, its inputs, and a
worked example with the expected answer.** A specification that computes money or time and gives no
worked example cannot produce a binary acceptance criterion, and "the seat map works" is not one
(Art IX.3).

Every worked example in this document is written so a test can be transcribed from it directly:
integer paise, ISO-8601 instants in both UTC and Asia/Kolkata, and the arithmetic shown rather than
the result asserted.

**A count stated in prose is a claim, and it is derived or it is wrong.** Every count in `S8` is
machine-derived by `docs/03 PRD/api/generate_api.py`, and the command that produced it is printed
next to it. This document states no figure it did not compute.

## S1.6 What is GENERATED, and what that buys

| File | Generated by | Checked how |
|---|---|---|
| `docs/03 PRD/api/contract.json` | `docs/03 PRD/api/generate_api.py` | regenerate and diff — **byte-identical or it fails** |
| `docs/03 PRD/api/error_codes.md` | the same | the same |

`CONSTITUTION.md` Art II.6 is the reason: a hash proves a file was not edited, but it cannot see a
requirement the file never contained. Where a document is marked GENERATED, the stronger check
regenerates it and compares content. **Never hand-edit either file.**

The generator's source is the `endpoint` blocks in `S6`. That is deliberate: it makes the API
contract a consequence of the specification rather than a parallel document that drifts from it.

## S1.7 Register

`SRC-002 §2` is a requirement on this document and not a courtesy. Everything here is written at the
level of someone who can code but has never run production infrastructure. **No analogies, no
metaphors, no figures of speech.** Short paragraphs.

Two consequences the client asked for by name:

- **When something will not fit in 1 GB, it is said, with the number** (`§13.6`), rather than quietly
  worked around. `S7` carries the memory figures and labels every one an estimate.
- **This product has never been observed running in AWS.** Every statement about its behaviour there
  is **reasoned, not observed**, and is labelled that way wherever it appears.

## S1.8 How this document was written, and why that matters

Eight lanes wrote the eight epics **independently and blind**, each reading the same frozen sources,
the same BRD rows and the same records, with no sight of another lane's draft. They were then merged,
and the merge pass hunted contradictions **between** lanes.

That is the defect class this stage exists to catch. Two sections that each resolve perfectly well on
their own and contradict each other are invisible to the mechanical checker (`Art IX.6`), and lanes
that can see each other converge — which makes the disagreement, the thing that carries the signal,
disappear. **Zero contradictions would have been a suspicious result, not a good one.** `S8.5` lists
what was found and how each was resolved.

`CONSTITUTION.md` Art VII.7 — the writer never verifies its own work — is discharged by a fresh
zero-context session that read only this document and reported every place it would have had to guess.
**That substitution is recorded rather than passed off as independent review**, and the count is in
`S8.6`, per iteration and not only at the end.
