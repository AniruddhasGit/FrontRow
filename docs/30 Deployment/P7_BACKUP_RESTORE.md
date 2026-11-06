# P7 — RDS backups, and a rehearsed restore (prep-queue row 17)

> **Zone C. The client builds and runs all of it by hand.** This file says what to configure, how to rehearse the
> restore, and what the backups do not cover. Everything about AWS here is *(reasoned, not observed)*: no backup or
> restore of this database has run in AWS. The local rehearsal below HAS run, against PostgreSQL 16 in docker compose.

## Why this exists

`SRC-003 OPEN-OPS-02` says nothing is ever deleted. That is a retention promise, not a recovery promise:
**forever retention and a 7-day backup window are different guarantees.** Retention means no code path deletes a row.
Recovery means getting the rows back after something else - a bad migration, a mistaken console click, a corrupted
volume - destroyed them. Only backups deliver the second, and only a restore that has been rehearsed is known to work.

## What to build

The RDS backup settings (FR-ADR-070):

1. **Automated backups on, retention 7 days** - the free-tier maximum. Not 1, not 0.
2. **point-in-time recovery** is what automated backups give you inside that window: a restore to any second, not only
   to the nightly snapshot.
3. **a backup window outside the cinema's busy period** - the early morning in `Asia/Kolkata`, never the evening shows.
   The snapshot briefly adds I/O load on a `db.t3.micro`.
4. **a manual snapshot before every migration.** Step 2 of the deploy order (`migrate`) is the one moment the schema
   changes; a manual snapshot taken right before it is the fastest way back if the migration is wrong. Manual
   snapshots are kept until you delete them, unlike automated ones.

## What the application expects

What a restore actually is, from the application's side:

- **a restore creates a new RDS instance with a new endpoint.** It never rewinds the existing instance in place. So the
  restore is not finished until the application points at the new endpoint: change `DATABASE_URL` (both SSM
  parameters, app and owner) and redeploy the api and the worker. Nothing else changes.
- **deleting an instance without a final snapshot deletes its automated backups with it.** Always take the final
  snapshot when the console offers it.
- **a corruption discovered in week three is not recoverable from an automated backup.** The oldest automated backup is
  7 days old. Anything found later needs a manual snapshot from before it happened.

## What is not backed up, on purpose

- **Redis is not backed up: it holds locks and cache.** A lock expires on its own within `SEAT_HOLD_TTL_SECONDS`; a
  cache entry is rebuilt from PostgreSQL. After a Redis loss customers lose their current holds, and no sale is lost.
- **S3 posters are not backed up: nothing deletes a poster and a new poster is a new key.** No code path overwrites or
  deletes an object (`P-ADM-20`), so the bucket is its own history.

## The rehearsal (do it once at Phase 7, and after any change to backups)

1. Restore the newest automated backup to a **new** instance (point-in-time, "latest restorable time").
2. Run `scripts/restore_rehearsal.py` from a machine that can reach the new instance, with **only** `DATABASE_URL`
   changed to the new endpoint, and `RESTORE_OPERATOR` set to your name:

   ```
   RESTORE_OPERATOR=<you> DATABASE_URL=postgresql://frontrow_app:<pw>@<new endpoint>:5432/frontrow python scripts/restore_rehearsal.py
   ```

3. It reads the known booking back:

   ```sql
   SELECT b.reference, s.row_label, s.seat_number, bs.price_paise
   FROM booking b JOIN booking_seat bs ON bs.booking_id = b.id JOIN seat s ON s.id = bs.seat_id
   WHERE b.reference = 'K7M2QX9C';
   ```

   and passes only on `FR-K7M2-QX9C`, seats C12 and C13, both Premium at 28124 paise (the seeded base of 24999 at the
   1250-basis-point Premium uplift), total exactly 2 x 28124 = 56248 paise.
4. Keep the one JSON line it prints (operator, run_at, restored_instance, the three values) in
   `docs/10 EngineeringLedger/evidence/S-XCT-34/`. An undated claim that the restore was rehearsed is not evidence.
5. Delete the rehearsal instance afterwards. It is a copy, so its final snapshot is optional - but read the console's
   question before answering it, because on the real instance the same question decides whether its backups survive.

**The known booking is not produced by `scripts/seed.py`** (its references are random). Before the first AWS
rehearsal, write it once into the source database - the local rehearsal test does exactly that
(`backend/tests/xct/test_s_xct_34.py`).

## Acceptance criteria

The rehearsal above passes (`outcome: pass` in its one JSON line). Locally, this is what was run:

Inside the compose test container: a throwaway database migrated with the real `migrate`, the booking above written
into it, `pg_dump -Fc` of it, `pg_restore` into a **second, new** database, and `scripts/restore_rehearsal.py` run with
`DATABASE_URL` pointed at the new one and nothing else changed. It printed `outcome: pass`.

One trap it hit: the test image's client tools are newer than the PostgreSQL 16 server, and a newer `pg_restore`
writes `SET transaction_timeout`, which 16 rejects. The rehearsal renders the archive to SQL (`pg_restore -f -`),
drops that one line and applies the rest with `ON_ERROR_STOP`. On RDS the console restore does not involve these
tools at all; the trap is for anyone rehearsing with `pg_dump` from a newer laptop.

## Common mistakes

- Restoring and then never changing `DATABASE_URL`: the application keeps writing to the old instance, and the
   restored copy drifts out of date within minutes.
- Retention left at 1 day (the console default for some engines), so the "backup" you need on day two is gone.
