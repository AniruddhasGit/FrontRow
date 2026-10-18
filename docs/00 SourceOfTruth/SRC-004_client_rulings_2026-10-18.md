# SRC-004 — FrontRow client rulings, second batch

```
Source type ....... Client rulings, in answer to CONSTITUTION.md Article X and two reserved waivers
Received .......... 2026-10-18, in the build session's chat (structured question, four answers)
Author ............ Aniruddha Jathar (the client)
Status ............ FROZEN — never edited
Citation form ..... SRC-004 <ROW-ID>
Rows .............. 6 rulings (2 waivers, 1 secrets, 3 irreversible), 1 process instruction
```

> **FROZEN INPUT. DO NOT EDIT.** Each `Ruling` block is the option the client selected, reproduced
> verbatim as it was put to them, or their own typed words where they typed instead of choosing.
> Anything under `Filed as` is the build session's reading and is **not** client text.
>
> The only permitted modification is a clearly-marked `ERRATUM` appended at the foot.

---

## R-1 · `OPEN-PRDCLOSE-01` and `GOAL_07`'s gate — **waived**, and `GOAL_09`–`13` compressed

**Question put:** *GOAL_05 (PRD) and GOAL_07 (Bible) are BLOCKED on quality gates, and GOAL_09–13
(architecture, SIT, negative tests, ledger, exit gate) stand before any code. Waiving a gate is
reserved to you. How do we pace?*

**Ruling (selected):** *"Waive + compress — Record waivers for OPEN-PRDCLOSE-01 and GOAL_07's gate;
do 09–13 as one lighter parallel pass; start Phase 1 code today. Tests, concurrency proof and
invariants stay non-waivable."*

**Context the client gave:** *"keep building the project … we'll get this project completed and
hosted today."*

**Filed as:**
- `OPEN-PRDCLOSE-01` → `RULED (waiver)`. The PRD closes on the convergence evidence of
  `docs/03 PRD/` §S8.6.9–S8.6.12, **not** on the guess count under 5 that it never reached. The
  last reading taken (10) stays on the record; the waiver does not rewrite it.
- `GOAL_07`'s binary gate → `RULED (waiver)`. The Bible is usable as the source of acceptance
  criteria with the census defects it still carries recorded, not hidden.
- `GOAL_09`–`GOAL_13` run as **one compressed pass**. That is a reduction in review depth the client
  chose with the cost stated; each goal still writes its artifact and its gate output, labelled
  `compressed per SRC-004 R-1`.
- **Not waived, by the client's own words:** the test-first Definition of Done, the 50-request
  concurrency proof and its red-proof, and every `CLAUDE.md` invariant.

## R-2 · AWS — the client builds it; the build session guides and verifies read-only

**Question put:** *Who builds the AWS infrastructure (ECS on EC2, ALB, RDS, ElastiCache, SQS, S3,
SES, SSM)?*

**Ruling (typed):** *"I already have the aws cli logged you can access it from here and guide me
throughh the build process while you go and check out via the cli if i'm maaking i correctly."*

**Filed as:** no change to `SRC-002 §6`. The client creates every resource; the build session
writes the Zone C specifications and checks the result with **describe / list / get only**. This
ruling grants **no** write access. *(At the time of the ruling the local CLI profile could not
authenticate: region set to the zone `ap-south-1c`, and `InvalidClientTokenId` with the region
corrected. Observed 2026-10-18.)*

## R-3 · `OPEN-RESETTOKEN-01` — the token rides in the queue payload

**Question put:** *Password reset can't be built as specified (token never stored, never in queue,
but worker must email a link containing it). Which rule gives?*

**Ruling (selected):** *"Token in queue payload — Token rides in the SQS/ElasticMQ message only
(short TTL, never logged, never in DB); DB keeps only the SHA-256. Smallest blast radius."*

**Filed as:** the rule that gives is `E4_receipt_entry.md`'s *"the reset token itself never travels
in the queue"*. The other two hold: the database stores only `token_sha256`, and the worker renders
the link. Consequences the code must carry: the message is never logged in full (the payload field
is redacted by the logger), the queue message retention is short, and **no database column —
including any `outbox_message` payload — ever holds the plaintext.**

## R-4 · `OPEN-SEATLABEL-01` and `OPEN-SEATALPHA-01` — upper-case, and `I` allowed

**Question put:** *Two one-way doors close at Phase 2/4 (seat row labels; booking reference
alphabet). Apply the stricter options?*

**Ruling (selected):** *"Stricter set — Row labels stored upper-cased, letter I allowed (matches
wall signs). References drop Z S B G too (keeping 2 5 8 6) and add one check character."*

**Filed as:**
- `OPEN-SEATLABEL-01` → `RULED`: `row_label` is stored as `upper(trim(input))`, enforced in the
  database (a `CHECK (row_label = upper(btrim(row_label)))`), so `C12` and `c12` cannot both exist.
- `OPEN-SEATALPHA-01` → `RULED`: the letter `I` is permitted in row labels. The seed's habit of
  skipping it is demonstration data and binds nothing.

## R-5 · `OPEN-REFCHAR-01` — narrower alphabet plus a check character

Same answer as R-4.

**Filed as:** the reference alphabet is `SRC-003 OPEN-TICKET-01`'s set **minus `Z S B G`**, keeping
`2 5 8 6`, and every reference carries **one trailing check character** drawn from the same
alphabet. `[JUDGMENT CALL]` **the length stays 8**: 7 random characters plus the check character,
so the display form `FR-XXXX-XXXX` and every criterion that tests length 8 are unchanged. 26⁷ ≈ 8.0 × 10⁹
references is far more than one theatre will ever issue. The rejected reading, 8 + 1 = 9, would
have changed the printed format the customer reads at the door. `[JUDGMENT CALL]` the check algorithm (a weighted mod-N over the alphabet's index, which
catches every single-character substitution and every adjacent transposition) — the build session
picks it and records it in the code that implements it, because the client ruled the *existence* of
a check character, not its arithmetic.

## R-6 · Build decisions go to the council, not the client *(received later the same session, before this file was first committed)*

**Ruling (typed, two messages):** *"can use /llm-council tto make hard decisions."* ·
*"instead of asking me aboutt the build. I am here as aa DevOps engineer."*

**Filed as:** the client steps out of the build lane and into the OPS lane. Build questions —
technical, and reversible reserved ones — are decided by an `/llm-council` run instead of being
put to the client; each is logged as a `[JUDGMENT CALL]` with the council's verdict and batched in
the handoff for the client to reverse. **Still brought to the client:** anything irreversible and
public, anything that spends money, and secrets — those are OPS-lane matters on this project anyway.

---

## Build-session judgment calls under R-6 (not client text — batched for the client to reverse)

- **JC-R6-01 · a failed reset-email send is not retried** (`PROPOSED-ARCH-01`). Under R-3 the plaintext
  token lives only in the queue message, so if that send fails there is nothing to retry from. The
  customer sees the same 202 sentence and asks again (rate-limited 5/hour/IP). Rejected: storing the
  token encrypted so the relay can retry. That would put a credential back in the database, which
  R-3 exists to avoid. This is the *stricter* option on secrets, so it is not a waiver.
- **JC-R6-02 · password reset ships in Phase 5, not Phase 2** (`PROPOSED-ARCH-02`). It needs the
  queue, the worker and SES, which are all Phase 5. Phase 2 builds the reset tables only. SQS and SES
  stay at Phase 5 in the prep queue.
- **JC-R6-03 · `row_label` is ASCII `A`–`Z` only** (GOAL_11 Q-2). Python's `str.upper` and
  PostgreSQL's `upper()` disagree on `ı` and `ß`. Restricting the input to ASCII makes them agree,
  and it is the stricter choice.
- **JC-R6-04 · the 250 MB image budget is deferred to a council at Phase 5** (GOAL_14 open question).
  Until then both figures are reported every time: `docker images` (239 MB) and the compressed size
  ECR stores (56.5 MB + 21.0 MB). boto3 is expected to push the first figure over 250 MB, so this is
  said now, not in Phase 5.
- **JC-R6-01a · JC-R6-01 covers only the API's send to the queue.** Once the reset message is on the
  queue, an SES refusal or timeout leaves the message undeleted, and SQS redelivers it up to
  `maxReceiveCount`. That retry reads the token from the message, so no stored copy is needed and R-3
  holds. The `resets` queue has **no dead-letter queue**: after the last receive, or once retention
  (1800 s or less) runs out, the message is gone, and the customer asks again. The outbox relay never
  sends a `password_reset.send` row.

---

## ERRATUM 1 — 2026-10-18, build session, about JC-R6-01a (not client text)

JC-R6-01a says "up to `maxReceiveCount`". SQS enforces `maxReceiveCount` only through a redrive
policy, and a redrive policy must name a dead-letter queue, which the `resets` queue does not have.
*(Reasoned from the SQS API, not observed.)* What actually bounds redelivery is the queue's
**retention period, 1800 s or less**. The worker may also stop retrying on its own, by checking the
message's `ApproximateReceiveCount` and deleting it once that passes a configured limit. Read
JC-R6-01a with "up to `maxReceiveCount`" replaced by "until retention expires, or until the
worker's own receive-count limit is reached".
