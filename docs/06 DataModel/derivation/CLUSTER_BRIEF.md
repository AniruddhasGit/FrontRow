# GOAL_08 cluster read — extract the schema the documents already require

Repo root `D:/FrontRow`. You are ONE of six readers. You own **one entity cluster** and write **one
JSON file**. You edit nothing in the repo. Five other agents are reading in parallel.

## What you are doing

`docs/06 DataModel/` is empty. The schema does not exist yet — but the documents have been
specifying it for weeks, in prose, in queries, and in 200 acceptance criteria that contain literal
SQL. **Your job is extraction, not design.** Find every column your cluster's tables must have,
and the citation that requires it.

## Sources, in authority order

1. `docs/03 PRD/sections/*.md` — the document code is written from. **Your primary source.**
2. `docs/05 Bible/FrontRow_Bible.csv` — 200 acceptance criteria. Many contain literal SQL naming
   columns. **A column named in a criterion's SQL is a hard requirement**: the test will run that
   query. Grep the `AcceptanceCriteria` column.
3. `docs/01 ADR/` — decision records. Cite by `FR-ADR-nnn`.
4. `docs/00 SourceOfTruth/` — SRC-001/002/003, frozen. Stricter always wins.

## The rules that will trip you

- **NEVER INVENT A COLUMN.** If the product plainly needs something no document mentions, put it in
  `gaps`, not in `columns`. An unknown becomes an Article X row; it never becomes a plausible guess.
  This project's worst failure to date was a 7-minute hold that was *assumed*, then hardened into a
  spec, and came back from the client as 3. Do not repeat it.
- **EVERY COLUMN CITES.** `cite` is a PRD row id (`P-XXX-nn`), a section file + heading, an
  `FR-ADR-nnn`, or a Bible story id. "Obvious" is not a citation. Uncited columns are rejected.
- **MONEY IS AN INTEGER IN THE MINOR UNIT.** Never float, never `NUMERIC(x,2)` — a driver hands that
  back as a float. Currency INR, ratio 100, but **the ratio is configuration** and must not appear
  in a column name, comment or constraint.
- **TIME IS AN INSTANT.** `timestamptz`, never a naive local timestamp. The zone is `Asia/Kolkata`
  (`SRC-003 OPEN-LOCALE-01`, RULED) and it is configuration.
- **RESERVED QUESTIONS ARE NOT YOURS.** If your cluster touches one, model the column and cite the
  row — do not express the question as a constraint. The five that bear on this schema:
  `OPEN-RESETTOKEN-01` (secrets — the reset flow is UNBUILDABLE as specified; do not add a
  plaintext-token column or make one cheap), `OPEN-REFCHAR-01` (the reference alphabet — no CHECK),
  `OPEN-SEATALPHA-01` + `OPEN-SEATLABEL-01` (row_label — no normalisation, no alphabet ban),
  `OPEN-DUPREF-01` (no redemption/admission column), `OPEN-HOLDRECOVER-01` (**holds are Redis-only
  and have NO table** — do not model them).
- **TABLE NAMES ARE FIXED.** users, cinema, screen, seat, movie, showtime, showtime_seat, booking,
  booking_seat, payment, idempotency_record, password_reset_token, outbox_message, receipt_dispatch,
  audit_log. 200 criteria contain SQL against these names. You may not rename. If a name looks
  wrong, say so in `notes` — do not change it.
- **NO CARD DATA.** Not a column, not a comment, not an example. Payment is simulated forever.
- Excluded is not blocked (`SRC-001 §6.6`): v1 exposes no cancellation, but a booking status and
  `cancelled_at` still exist. Keep columns the documents require even where no endpoint uses them.

## Type vocabulary — use these spellings exactly, so six outputs merge

`uuid` · `text` · `citext` · `integer` · `bigint` · `smallint` · `boolean` · `timestamptz` · `date`
· `jsonb` · `bytea` · `inet` · enum → `enum:<name>` and list its values in `enums`.

Primary keys are `uuid` with no database-side default unless a document says otherwise (the
application generates ids; say so if your source disagrees). Money columns are `integer` or
`bigint` and their name ends `_paise` ONLY if a document already spells it that way — otherwise
report the name the document uses.

## Return — write exactly this JSON to your output path, and nothing else to the repo

```json
{
  "cluster": "<your cluster name>",
  "tables": [
    {
      "name": "booking",
      "purpose": "one sentence",
      "cite": "P-XXX-nn or section+heading",
      "columns": [
        {"name":"id","type":"uuid","nullable":false,"default":null,
         "cite":"P-BOK-03","note":"", "reserved_row":null}
      ],
      "primary_key": ["id"],
      "unique": [{"columns":["showtime_id","seat_id"],"cite":"SRC-001 §2.2","why":"..."}],
      "foreign_keys": [{"columns":["showtime_id"],"references":"showtime(id)","on_delete":"RESTRICT","cite":"..."}],
      "checks": [{"expression":"...","cite":"...","why":"..."}],
      "indexes": [{"columns":["..."],"unique":false,"cite":"...","why":"which query needs it"}]
    }
  ],
  "enums": [{"name":"booking_status","values":["..."],"cite":"..."}],
  "gaps": [{"what":"...","why_it_matters":"...","where_you_looked":"...","reserved":true}],
  "sql_seen_in_criteria": [{"story":"S-XXX-nn","sql":"verbatim","columns_implied":["..."]}],
  "notes": ["anything the merge owner must know"]
}
```

`sql_seen_in_criteria` is the highest-value field you produce. **A criterion's SQL is a test that
will be run.** If it selects `booking.reference_code` and your column list says `reference`, the
test fails and the schema is wrong. Report every one you find, verbatim.

`gaps` is the second: a gap honestly reported is worth more than a column confidently invented.
