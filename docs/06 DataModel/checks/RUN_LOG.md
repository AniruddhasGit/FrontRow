# checks/ RUN_LOG — 2026-10-18

The live-database half of `GOAL_08`. Every output block below was **copied from a real run** in this
session. Nothing is paraphrased. Where a block was filtered for length, the filter is the
`grep`/`sed` shown in its command line.

| | |
|---|---|
| Date | 2026-10-18 |
| Engine | `postgres (PostgreSQL) 16.15`, image `postgres:16-alpine`, container `frontrow-pg16`, host port **55432** |
| Docker | Docker Engine 29.6.2 |
| `schema.sql` applied | sha256 `0804c09892cc172bca9fd6366bd7e5ce693eae30ceb4802f215cd9cd8f6228be`, unchanged vs HEAD `7a56c05` at the time of the run |
| Untouched | the default-port 5432 Postgres and every other container (an unrelated project's) |

**Passwords — CORRECTED by the fix wave, same day.** Both role passwords were random
(`secrets.token_urlsafe(18)`), generated at run time, passed with `psql -v` and set on the roles. They
appear in no repository file and are written below as `$OWNER_PW` and `$APP_PW`.

**The claim this paragraph first made was false.** It said every role login below was "password
authentication over TCP to 127.0.0.1". The logins were over TCP to 127.0.0.1 *inside the container*,
and the `postgres:16-alpine` image's `pg_hba.conf` reads `host all all 127.0.0.1/32 trust`, so the
server **accepted the role name without checking any password**. What still stands: each session
really was `frontrow_owner` or `frontrow_app` (`current_user` and `session_user` below show it) and
every privilege check was applied to that role, so the privilege results are valid. What this run did
**not** prove is password authentication. The fix-wave run at the end of this file logs in through the
container's own `eth0` address, which falls to `host all all all scram-sha-256`, and prints
`system_user` = `scram-sha-256:<role>` as the evidence.

Paths in the commands: `$DM` = `D:/Project/FrontRow/docs/06 DataModel`. The `redproof_*.sql` scripts
were run from the session scratchpad and are reproduced in full below; they are not repository files.

## Result summary

| Step | Result |
|---|---|
| 2. Empty DB → `roles_local.sql` as superuser → `schema.sql` **as `frontrow_owner`** (not superuser) | **exit 0**, zero errors, zero warnings; 22 tables, 29 `CREATE INDEX`, 24 `GRANT` |
| 2. Does `schema.sql` need superuser? | **No**, provided the roles exist first. See finding F-1 |
| 4. `verify_invariants.sql` **as `frontrow_app`** | **exit 0: 32 PASS, 0 FAIL**, plus 1 ADVISORY |
| 5a. Guard dropped, two bookings on one seat → verify | **exit 3, RED**: G1, G2, G3 FAIL |
| 5b. Oversold row deleted, guard restored → `pg_get_constraintdef` | `UNIQUE (showtime_id, seat_id)`, total, no WHERE; a repeat oversell is refused with `23505` |
| 5c. Verify again, **with the surviving fixture booking still present** | **exit 0**, all pass, and the data checks are not vacuous |
| 5d. Fixture removed → verify | 0 rows in all 22 tables; **exit 0** |
| Extra: P1 and A1 red-proofed | **exit 3**: P1, A1, A2 FAIL; restored → **exit 0** |

The concurrency proof is **not** claimed here. This is the database half only. The Redis lock and
`scripts/stress_seats.py` (50 concurrent requests) are Phase 4 and do not exist.

---

## Step 0 — Docker and the container

```
for i in $(seq 1 90); do docker info >/dev/null 2>&1 && break; ping -n 3 127.0.0.1 >/dev/null; done
docker info --format '{{.ServerVersion}}'; docker ps -a --format '{{.Names}} {{.Status}} {{.Ports}}'
```
```
29.6.2
```
`docker ps -a` printed **no containers**. The `frontrow-pg16` from the 2026-08-23 session no longer
existed, so it was created fresh:
```
docker run -d --name frontrow-pg16 -e POSTGRES_PASSWORD=local -e POSTGRES_DB=frontrow -p 55432:5432 postgres:16-alpine
```
**Recommended instead (fix wave):** bind the published port to the loopback interface only.
```
docker run -d --name frontrow-pg16 -e POSTGRES_PASSWORD=local -e POSTGRES_DB=frontrow -p 127.0.0.1:55432:5432 postgres:16-alpine
```
`-p 55432:5432` publishes on `0.0.0.0`, every interface of the host, so any machine on the same network
can reach a superuser whose password is `local`. With `127.0.0.1:55432` only this machine can. (The
running container was not recreated: the fix wave only had to use it, and recreating it is the
operator's call.)
```
Status: Downloaded newer image for postgres:16-alpine
40344b48dd827dac65fe7b23aba80f0d2574c1edd3a54ec6d6968f6584fbe20a
```

## Step 2 — empty database, roles, schema applied as the owner

```
docker exec frontrow-pg16 postgres --version
sha256sum "$DM/schema.sql"
docker exec -i frontrow-pg16 psql -v ON_ERROR_STOP=1 -U postgres -d postgres \
    -c "DROP DATABASE IF EXISTS frontrow WITH (FORCE);" -c "CREATE DATABASE frontrow;"
docker exec -i frontrow-pg16 psql -v ON_ERROR_STOP=1 -v owner_password="$OWNER_PW" -v app_password="$APP_PW" \
    -U postgres -d frontrow < "$DM/checks/roles_local.sql"
docker exec -i -e PGPASSWORD="$OWNER_PW" frontrow-pg16 psql -v ON_ERROR_STOP=1 -h 127.0.0.1 -U frontrow_owner -d frontrow \
    -c "SELECT current_user, session_user, (SELECT rolsuper FROM pg_roles WHERE rolname=current_user) AS is_superuser;"
docker exec -i -e PGPASSWORD="$OWNER_PW" frontrow-pg16 psql -v ON_ERROR_STOP=1 -h 127.0.0.1 -U frontrow_owner -d frontrow \
    < "$DM/schema.sql" > apply.log 2>&1; echo "exit=$?"
echo "statement tally:"; sort apply.log | uniq -c | sort -rn
docker exec frontrow-pg16 psql -U postgres -d frontrow -Atc "SELECT count(*) FILTER (WHERE relkind='r') AS tables, count(*) FILTER (WHERE relkind='i') AS indexes, count(*) FILTER (WHERE relkind='S') AS sequences, count(*) AS all_relations FROM pg_class WHERE relnamespace='public'::regnamespace;"
```
```
### docker exec frontrow-pg16 postgres --version
postgres (PostgreSQL) 16.15
### sha256 schema.sql
0804c09892cc172bca9fd6366bd7e5ce693eae30ceb4802f215cd9cd8f6228be *D:/Project/FrontRow/docs/06 DataModel/schema.sql
### step 2a: recreate empty database (as superuser postgres, connected to db postgres)
DROP DATABASE
CREATE DATABASE
exit=0
### step 2b: roles_local.sql as superuser
DO
ALTER ROLE
ALTER ROLE
ALTER ROLE
ALTER ROLE
DO
DO
GRANT
GRANT
REVOKE
REVOKE
exit=0
### step 2c: schema.sql AS frontrow_owner (TCP 127.0.0.1 - TRUST-authenticated, see the correction above)
  current_user  |  session_user  | is_superuser 
----------------+----------------+--------------
 frontrow_owner | frontrow_owner | f
(1 row)

exit=0
statement tally:
     29 CREATE INDEX
     24 GRANT
     22 CREATE TABLE
      2 DO
      1 COMMIT
      1 BEGIN
### objects
22|58|20|100
```
`apply.log` (stdout and stderr merged) contains **no ERROR and no WARNING line**: the tally above is
every line it has. `objects` is tables | indexes (including the ones backing PK and UNIQUE
constraints) | identity sequences | all relations in `public`.

## Step 4 — `verify_invariants.sql` as `frontrow_app`, on the freshly applied schema

```
docker exec -i -e PGPASSWORD="$APP_PW" frontrow-pg16 psql -v ON_ERROR_STOP=1 -h 127.0.0.1 -U frontrow_app -d frontrow -c "SELECT current_user, session_user;"
docker exec -i -e PGPASSWORD="$APP_PW" frontrow-pg16 psql -v ON_ERROR_STOP=1 -h 127.0.0.1 -U frontrow_app -d frontrow \
    < "$DM/checks/verify_invariants.sql" 2>&1 | sed -E 's/^psql:<stdin>:[0-9]+: //'; echo "exit=${PIPESTATUS[0]}"
```
```
 current_user | session_user 
--------------+--------------
 frontrow_app | frontrow_app
(1 row)

== LISTING 1: every money column and its type (GOAL_08 DoD: zero float money columns) ==
  table_name  |       column_name        | data_type 
--------------+--------------------------+-----------
 booking      | total_paise              | bigint
 booking_seat | base_price_paise_applied | bigint
 booking_seat | price_paise              | bigint
 payment      | amount_paise             | bigint
 showtime     | base_price_paise         | bigint
(5 rows)

== LISTING 2: any float / numeric / money column anywhere in public (must be empty) ==
 table_name | column_name | data_type 
------------+-------------+-----------
(0 rows)

== LISTING 3: S-XCT-07 verbatim shape - audit_log privileges held by frontrow_app ==
 privilege_type 
----------------
 INSERT
 SELECT
(2 rows)

== LISTING 4: the seat guarantee as the catalog stores it ==
               conname                |          definition           
--------------------------------------+-------------------------------
 booking_seat_pkey                    | PRIMARY KEY (id)
 uq_booking_seat__showtime_id_seat_id | UNIQUE (showtime_id, seat_id)
(2 rows)

== ASSERTIONS ==
NOTICE:  PASS G1  no (showtime_id, seat_id) pair is held by two booking_seat rows
NOTICE:  PASS G2  uq_booking_seat__showtime_id_seat_id = UNIQUE (showtime_id, seat_id)
NOTICE:  PASS G3  booking_seat has exactly 1 non-primary unique index and no partial unique index
NOTICE:  PASS G4  every booking_seat matches its booking's showtime and that showtime's inventory
NOTICE:  PASS P1  every booking points at a payment in state captured
NOTICE:  PASS P2  booking.payment_id is NOT NULL and a foreign key to payment
NOTICE:  PASS P3  payment has no booking_id column (S-PAY-05)
NOTICE:  PASS M1  zero real/double/numeric/money columns in schema public
NOTICE:  PASS M2  every *_paise column is bigint or integer (and at least the 5 known money columns exist)
NOTICE:  PASS M3  money columns on booking/booking_seat/payment are exactly booking.total_paise,booking_seat.base_price_paise_applied,booking_seat.price_paise,payment.amount_paise
NOTICE:  PASS M4  every booking.total_paise equals the sum of its seats' price_paise
NOTICE:  PASS M5  no booking holds more than 10 seats
NOTICE:  PASS I1  uq_idempotency_record__user_id_idempotency_key = UNIQUE (user_id, idempotency_key)
NOTICE:  PASS I2  no (user_id, idempotency_key) pair is stored twice
NOTICE:  PASS I3  payment.idempotency_key carries no unique index (S-PAY-15)
NOTICE:  PASS A1  frontrow_app on audit_log = INSERT,SELECT
NOTICE:  PASS A2  frontrow_app effectively can SELECT, INSERT and cannot UPDATE, DELETE, TRUNCATE audit_log
NOTICE:  PASS R1  both roles exist and neither is superuser / bypassrls / createrole / createdb
NOTICE:  PASS R2  every relation in public is owned by frontrow_owner (so frontrow_app owns none)
NOTICE:  PASS R3  frontrow_app cannot CREATE in schema public
NOTICE:  PASS R4  frontrow_app holds no TRUNCATE / REFERENCES / TRIGGER on any table
NOTICE:  PASS R5  frontrow_app is not a member of frontrow_owner
NOTICE:  PASS F1  every foreign key in public is ON DELETE RESTRICT
NOTICE:  PASS K1  every id column is bigint GENERATED ALWAYS AS IDENTITY
NOTICE:  PASS T1  zero timestamp-without-time-zone columns
NOTICE:  PASS B1  booking.reference is UNIQUE and carries no CHECK (OPEN-REFCHAR-01 left unruled)
NOTICE:  PASS B2  booking.status and booking.cancelled_at exist; no row is cancelled or non-confirmed
NOTICE:  PASS O1  seat.row_label is raw text: no CHECK, no normalising index (OPEN-SEATLABEL-01, OPEN-SEATALPHA-01 unruled)
NOTICE:  PASS O2  password_reset_token: token_sha256 only, and claim / sent / used are three separate columns
NOTICE:  PASS O3  no holds table and no admission/redemption column (OPEN-HOLDRECOVER-01, OPEN-DUPREF-01 unruled)
NOTICE:  PASS U1  users.role vocabulary is exactly customer, manager, admin
NOTICE:  ADVISORY  frontrow_app holds grants beyond the derived least-privilege matrix (not a failure; fix belongs in datamodel.json roles[].grants): booking:DELETE, booking:UPDATE, booking_seat:DELETE, booking_seat:UPDATE, certification:DELETE, cinema:DELETE, format:DELETE, genre:DELETE, idempotency_record:DELETE, language:DELETE, manager_screen_assignment:UPDATE, movie:DELETE, movie_genre:UPDATE, outbox_message:DELETE, password_reset_token:DELETE, payment:DELETE, receipt_dispatch:DELETE, screen:DELETE, seat_category:DELETE, showtime:DELETE, showtime_seat:DELETE, showtime_seat:UPDATE, users:DELETE
NOTICE:  PASS A3  frontrow_app holds every grant the derived matrix says the application needs
NOTICE:  verify_invariants: ALL ASSERTIONS PASSED
DO
exit=0
```
On an empty schema the data assertions (G1, G4, P1, M4, M5, I2, B2) pass **vacuously**. Step 5c and
the extra drill are the runs where they pass and fail **against real rows**.

## Step 5 — red-proof the invariant check

### 5a. As the owner: drop the guard, insert two bookings for one seat

The fixture data is invented. **There is no card data**: payment is simulated, and the schema has no
card column. The emails use the reserved `.invalid` TLD.

```sql
\set ON_ERROR_STOP on
SELECT current_user;
-- RED-PROOF STAGE A: the guard is dropped on purpose.
ALTER TABLE booking_seat DROP CONSTRAINT uq_booking_seat__showtime_id_seat_id;
-- Minimal VALID fixture. Invented test data only. No card data: payment is simulated
-- and the schema has no card column. Two customers, one showtime, one seat, two
-- captured payments, two confirmed bookings, two booking_seat rows for ONE seat.
DO $fx$
DECLARE u1 bigint; u2 bigint; ci bigint; sc bigint; se bigint; cat bigint;
        ce bigint; la bigint; mv bigint; sh bigint; p1 bigint; p2 bigint; b1 bigint; b2 bigint;
BEGIN
  INSERT INTO users (email, password_hash, role, password_version)
       VALUES ('redproof-a@example.invalid', 'redproof-not-a-hash', 'customer', 1) RETURNING id INTO u1;
  INSERT INTO users (email, password_hash, role, password_version)
       VALUES ('redproof-b@example.invalid', 'redproof-not-a-hash', 'customer', 1) RETURNING id INTO u2;
  INSERT INTO cinema (name, timezone, version) VALUES ('Redproof Cinema', 'Asia/Kolkata', 1) RETURNING id INTO ci;
  INSERT INTO screen (cinema_id, name, version) VALUES (ci, 'Redproof Hall', 1) RETURNING id INTO sc;
  INSERT INTO seat_category (name, uplift_basis_points, version) VALUES ('Redproof Category', 0, 1) RETURNING id INTO cat;
  INSERT INTO seat (screen_id, row_label, seat_number, grid_row, grid_col, seat_category_id)
       VALUES (sc, 'A', 1, 1, 1, cat) RETURNING id INTO se;
  INSERT INTO certification (name, is_active) VALUES ('Redproof Cert', true) RETURNING id INTO ce;
  INSERT INTO language (name, is_active) VALUES ('Redproof Language', true) RETURNING id INTO la;
  INSERT INTO movie (title, synopsis, runtime_minutes, certification_id, language_id, version)
       VALUES ('Redproof Film', 'Fixture.', 100, ce, la, 1) RETURNING id INTO mv;
  INSERT INTO showtime (movie_id, screen_id, starts_at, ends_at, base_price_paise, seat_count_at_creation, version)
       VALUES (mv, sc, '2026-10-20 13:30:00+00', '2026-10-20 15:10:00+00', 25000, 1, 1) RETURNING id INTO sh;
  INSERT INTO showtime_seat (showtime_id, seat_id) VALUES (sh, se);
  INSERT INTO payment (state, amount_paise, idempotency_key, pending_at, authorized_at, captured_at)
       VALUES ('captured', 25000, 'redproof-key-a', '2026-10-18 10:00:00+00', '2026-10-18 10:00:01+00', '2026-10-18 10:00:02+00') RETURNING id INTO p1;
  INSERT INTO payment (state, amount_paise, idempotency_key, pending_at, authorized_at, captured_at)
       VALUES ('captured', 25000, 'redproof-key-b', '2026-10-18 10:00:00+00', '2026-10-18 10:00:01+00', '2026-10-18 10:00:02+00') RETURNING id INTO p2;
  INSERT INTO booking (reference, user_id, showtime_id, payment_id, total_paise, status)
       VALUES ('REDPROOFA1', u1, sh, p1, 25000, 'confirmed') RETURNING id INTO b1;
  INSERT INTO booking (reference, user_id, showtime_id, payment_id, total_paise, status)
       VALUES ('REDPROOFB2', u2, sh, p2, 25000, 'confirmed') RETURNING id INTO b2;
  INSERT INTO booking_seat (booking_id, showtime_id, seat_id, price_paise, base_price_paise_applied, uplift_basis_points_applied, seat_category_id)
       VALUES (b1, sh, se, 25000, 25000, 0, cat);
  -- the oversell: the SAME (showtime_id, seat_id), accepted because the guard is gone
  INSERT INTO booking_seat (booking_id, showtime_id, seat_id, price_paise, base_price_paise_applied, uplift_basis_points_applied, seat_category_id)
       VALUES (b2, sh, se, 25000, 25000, 0, cat);
END $fx$;
SELECT b.reference, bs.showtime_id, bs.seat_id FROM booking_seat bs JOIN booking b ON b.id = bs.booking_id ORDER BY b.reference;
```
```
docker exec -i -e PGPASSWORD="$OWNER_PW" frontrow-pg16 psql -h 127.0.0.1 -U frontrow_owner -d frontrow < redproof_A_drop_and_oversell.sql; echo "exit=$?"
```
```
  current_user  
----------------
 frontrow_owner
(1 row)

ALTER TABLE
DO
 reference  | showtime_id | seat_id 
------------+-------------+---------
 REDPROOFA1 |           1 |       1
 REDPROOFB2 |           1 |       1
(2 rows)

exit=0
```

### Output 1 of 4 — `verify_invariants.sql` as `frontrow_app` goes RED

```
docker exec -i -e PGPASSWORD="$APP_PW" frontrow-pg16 psql -v ON_ERROR_STOP=1 -h 127.0.0.1 -U frontrow_app -d frontrow \
    < "$DM/checks/verify_invariants.sql" > red.log 2>&1; echo "exit=$?"
```
```
exit=3
```
The full `red.log`, verbatim:
```
== LISTING 1: every money column and its type (GOAL_08 DoD: zero float money columns) ==
  table_name  |       column_name        | data_type 
--------------+--------------------------+-----------
 booking      | total_paise              | bigint
 booking_seat | base_price_paise_applied | bigint
 booking_seat | price_paise              | bigint
 payment      | amount_paise             | bigint
 showtime     | base_price_paise         | bigint
(5 rows)

== LISTING 2: any float / numeric / money column anywhere in public (must be empty) ==
 table_name | column_name | data_type 
------------+-------------+-----------
(0 rows)

== LISTING 3: S-XCT-07 verbatim shape - audit_log privileges held by frontrow_app ==
 privilege_type 
----------------
 INSERT
 SELECT
(2 rows)

== LISTING 4: the seat guarantee as the catalog stores it ==
      conname      |    definition    
-------------------+------------------
 booking_seat_pkey | PRIMARY KEY (id)
(1 row)

== ASSERTIONS ==
NOTICE:  FAIL G1  1 seat(s) SOLD TWICE: (showtime_id=1, seat_id=1) x2
NOTICE:  FAIL G2  guard constraint uq_booking_seat__showtime_id_seat_id is MISSING
NOTICE:  FAIL G3  booking_seat has 0 non-primary unique index(es), or a partial one (S-PAY-09)
NOTICE:  PASS G4  every booking_seat matches its booking's showtime and that showtime's inventory
NOTICE:  PASS P1  every booking points at a payment in state captured
NOTICE:  PASS P2  booking.payment_id is NOT NULL and a foreign key to payment
NOTICE:  PASS P3  payment has no booking_id column (S-PAY-05)
NOTICE:  PASS M1  zero real/double/numeric/money columns in schema public
NOTICE:  PASS M2  every *_paise column is bigint or integer (and at least the 5 known money columns exist)
NOTICE:  PASS M3  money columns on booking/booking_seat/payment are exactly booking.total_paise,booking_seat.base_price_paise_applied,booking_seat.price_paise,payment.amount_paise
NOTICE:  PASS M4  every booking.total_paise equals the sum of its seats' price_paise
NOTICE:  PASS M5  no booking holds more than 10 seats
NOTICE:  PASS I1  uq_idempotency_record__user_id_idempotency_key = UNIQUE (user_id, idempotency_key)
NOTICE:  PASS I2  no (user_id, idempotency_key) pair is stored twice
NOTICE:  PASS I3  payment.idempotency_key carries no unique index (S-PAY-15)
NOTICE:  PASS A1  frontrow_app on audit_log = INSERT,SELECT
NOTICE:  PASS A2  frontrow_app effectively can SELECT, INSERT and cannot UPDATE, DELETE, TRUNCATE audit_log
NOTICE:  PASS R1  both roles exist and neither is superuser / bypassrls / createrole / createdb
NOTICE:  PASS R2  every relation in public is owned by frontrow_owner (so frontrow_app owns none)
NOTICE:  PASS R3  frontrow_app cannot CREATE in schema public
NOTICE:  PASS R4  frontrow_app holds no TRUNCATE / REFERENCES / TRIGGER on any table
NOTICE:  PASS R5  frontrow_app is not a member of frontrow_owner
NOTICE:  PASS F1  every foreign key in public is ON DELETE RESTRICT
NOTICE:  PASS K1  every id column is bigint GENERATED ALWAYS AS IDENTITY
NOTICE:  PASS T1  zero timestamp-without-time-zone columns
NOTICE:  PASS B1  booking.reference is UNIQUE and carries no CHECK (OPEN-REFCHAR-01 left unruled)
NOTICE:  PASS B2  booking.status and booking.cancelled_at exist; no row is cancelled or non-confirmed
NOTICE:  PASS O1  seat.row_label is raw text: no CHECK, no normalising index (OPEN-SEATLABEL-01, OPEN-SEATALPHA-01 unruled)
NOTICE:  PASS O2  password_reset_token: token_sha256 only, and claim / sent / used are three separate columns
NOTICE:  PASS O3  no holds table and no admission/redemption column (OPEN-HOLDRECOVER-01, OPEN-DUPREF-01 unruled)
NOTICE:  PASS U1  users.role vocabulary is exactly customer, manager, admin
NOTICE:  ADVISORY  frontrow_app holds grants beyond the derived least-privilege matrix (not a failure; fix belongs in datamodel.json roles[].grants): booking:DELETE, booking:UPDATE, booking_seat:DELETE, booking_seat:UPDATE, certification:DELETE, cinema:DELETE, format:DELETE, genre:DELETE, idempotency_record:DELETE, language:DELETE, manager_screen_assignment:UPDATE, movie:DELETE, movie_genre:UPDATE, outbox_message:DELETE, password_reset_token:DELETE, payment:DELETE, receipt_dispatch:DELETE, screen:DELETE, seat_category:DELETE, showtime:DELETE, showtime_seat:DELETE, showtime_seat:UPDATE, users:DELETE
NOTICE:  PASS A3  frontrow_app holds every grant the derived matrix says the application needs
ERROR:  verify_invariants: 3 assertion(s) FAILED - see FAIL lines above
CONTEXT:  PL/pgSQL function inline_code_block line 453 at RAISE
```
**Three assertions went red, and they were the right three**: G1 (the data: a seat sold twice), G2 (the
constraint is missing) and G3 (no unique index). psql exited **3**. Every other check still passed:
the fixture is otherwise a valid booking, so the red is caused by the oversell and nothing else.

### Output 2 of 4 — delete the oversold row, restore the constraint, verify the restore

```sql
\set ON_ERROR_STOP on
-- RED-PROOF STAGE B: remove the oversold row (booking REDPROOFB2, its seat row and its payment)
DELETE FROM booking_seat WHERE booking_id = (SELECT id FROM booking WHERE reference = 'REDPROOFB2');
DELETE FROM booking WHERE reference = 'REDPROOFB2';
DELETE FROM payment WHERE idempotency_key = 'redproof-key-b';
-- restore the guard exactly as schema.sql declares it
ALTER TABLE booking_seat ADD CONSTRAINT uq_booking_seat__showtime_id_seat_id UNIQUE (showtime_id, seat_id);
-- verify the restore
SELECT conname, pg_get_constraintdef(oid) AS definition
  FROM pg_constraint
 WHERE conrelid = 'booking_seat'::regclass AND conname = 'uq_booking_seat__showtime_id_seat_id';
SELECT indexrelid::regclass AS index, indisunique, indpred IS NULL AS total_no_where
  FROM pg_index WHERE indrelid = 'booking_seat'::regclass AND indisunique AND NOT indisprimary;
```
```
docker exec -i -e PGPASSWORD="$OWNER_PW" frontrow-pg16 psql -h 127.0.0.1 -U frontrow_owner -d frontrow < redproof_B_restore.sql; echo "exit=$?"
```
```
DELETE 1
DELETE 1
DELETE 1
ALTER TABLE
               conname                |          definition           
--------------------------------------+-------------------------------
 uq_booking_seat__showtime_id_seat_id | UNIQUE (showtime_id, seat_id)
(1 row)

                index                 | indisunique | total_no_where 
--------------------------------------+-------------+----------------
 uq_booking_seat__showtime_id_seat_id | t           | t
(1 row)

exit=0
```
The restored guard was then **watched refusing** the same oversell. The script has no ON_ERROR_STOP,
so the aborted transaction and its rollback are both visible:
```sql
-- the same oversell attempted against the restored guard: must be refused
BEGIN;
INSERT INTO payment (state, amount_paise, idempotency_key, pending_at, authorized_at, captured_at)
     VALUES ('captured', 25000, 'redproof-key-b', '2026-10-18 10:00:00+00', '2026-10-18 10:00:01+00', '2026-10-18 10:00:02+00');
INSERT INTO booking (reference, user_id, showtime_id, payment_id, total_paise, status)
     VALUES ('REDPROOFB2', (SELECT id FROM users WHERE email = 'redproof-b@example.invalid'), 1,
             (SELECT id FROM payment WHERE idempotency_key = 'redproof-key-b'), 25000, 'confirmed');
INSERT INTO booking_seat (booking_id, showtime_id, seat_id, price_paise, base_price_paise_applied, uplift_basis_points_applied, seat_category_id)
     VALUES ((SELECT id FROM booking WHERE reference = 'REDPROOFB2'), 1, 1, 25000, 25000, 0,
             (SELECT id FROM seat_category WHERE name = 'Redproof Category'));
ROLLBACK;
SELECT count(*) AS booking_seat_rows_for_seat_1 FROM booking_seat WHERE showtime_id = 1 AND seat_id = 1;
```
```
docker exec -i -e PGPASSWORD="$OWNER_PW" frontrow-pg16 psql -h 127.0.0.1 -U frontrow_owner -d frontrow < redproof_B2_refused.sql 2>&1 | sed -E 's/^psql:<stdin>:[0-9]+: //'
```
```
BEGIN
INSERT 0 1
INSERT 0 1
ERROR:  duplicate key value violates unique constraint "uq_booking_seat__showtime_id_seat_id"
DETAIL:  Key (showtime_id, seat_id)=(1, 1) already exists.
ROLLBACK
 booking_seat_rows_for_seat_1 
------------------------------
                            1
(1 row)
```

### Output 3 of 4 — rerun green, with the surviving booking still present

```
docker exec -i -e PGPASSWORD="$APP_PW" frontrow-pg16 psql -v ON_ERROR_STOP=1 -h 127.0.0.1 -U frontrow_app -d frontrow \
    < "$DM/checks/verify_invariants.sql" > green_after.log 2>&1; echo "exit=$?"
docker exec -i -e PGPASSWORD="$APP_PW" frontrow-pg16 psql -h 127.0.0.1 -U frontrow_app -d frontrow -Atc "SELECT 'fixture rows live during green run: bookings='||(SELECT count(*) FROM booking)||' booking_seats='||(SELECT count(*) FROM booking_seat)||' payments='||(SELECT count(*) FROM payment);"
```
```
exit=0
fixture rows live during green run: bookings=1 booking_seats=1 payments=1
```
The full `green_after.log`, verbatim:
```
== LISTING 1: every money column and its type (GOAL_08 DoD: zero float money columns) ==
  table_name  |       column_name        | data_type 
--------------+--------------------------+-----------
 booking      | total_paise              | bigint
 booking_seat | base_price_paise_applied | bigint
 booking_seat | price_paise              | bigint
 payment      | amount_paise             | bigint
 showtime     | base_price_paise         | bigint
(5 rows)

== LISTING 2: any float / numeric / money column anywhere in public (must be empty) ==
 table_name | column_name | data_type 
------------+-------------+-----------
(0 rows)

== LISTING 3: S-XCT-07 verbatim shape - audit_log privileges held by frontrow_app ==
 privilege_type 
----------------
 INSERT
 SELECT
(2 rows)

== LISTING 4: the seat guarantee as the catalog stores it ==
               conname                |          definition           
--------------------------------------+-------------------------------
 booking_seat_pkey                    | PRIMARY KEY (id)
 uq_booking_seat__showtime_id_seat_id | UNIQUE (showtime_id, seat_id)
(2 rows)

== ASSERTIONS ==
NOTICE:  PASS G1  no (showtime_id, seat_id) pair is held by two booking_seat rows
NOTICE:  PASS G2  uq_booking_seat__showtime_id_seat_id = UNIQUE (showtime_id, seat_id)
NOTICE:  PASS G3  booking_seat has exactly 1 non-primary unique index and no partial unique index
NOTICE:  PASS G4  every booking_seat matches its booking's showtime and that showtime's inventory
NOTICE:  PASS P1  every booking points at a payment in state captured
NOTICE:  PASS P2  booking.payment_id is NOT NULL and a foreign key to payment
NOTICE:  PASS P3  payment has no booking_id column (S-PAY-05)
NOTICE:  PASS M1  zero real/double/numeric/money columns in schema public
NOTICE:  PASS M2  every *_paise column is bigint or integer (and at least the 5 known money columns exist)
NOTICE:  PASS M3  money columns on booking/booking_seat/payment are exactly booking.total_paise,booking_seat.base_price_paise_applied,booking_seat.price_paise,payment.amount_paise
NOTICE:  PASS M4  every booking.total_paise equals the sum of its seats' price_paise
NOTICE:  PASS M5  no booking holds more than 10 seats
NOTICE:  PASS I1  uq_idempotency_record__user_id_idempotency_key = UNIQUE (user_id, idempotency_key)
NOTICE:  PASS I2  no (user_id, idempotency_key) pair is stored twice
NOTICE:  PASS I3  payment.idempotency_key carries no unique index (S-PAY-15)
NOTICE:  PASS A1  frontrow_app on audit_log = INSERT,SELECT
NOTICE:  PASS A2  frontrow_app effectively can SELECT, INSERT and cannot UPDATE, DELETE, TRUNCATE audit_log
NOTICE:  PASS R1  both roles exist and neither is superuser / bypassrls / createrole / createdb
NOTICE:  PASS R2  every relation in public is owned by frontrow_owner (so frontrow_app owns none)
NOTICE:  PASS R3  frontrow_app cannot CREATE in schema public
NOTICE:  PASS R4  frontrow_app holds no TRUNCATE / REFERENCES / TRIGGER on any table
NOTICE:  PASS R5  frontrow_app is not a member of frontrow_owner
NOTICE:  PASS F1  every foreign key in public is ON DELETE RESTRICT
NOTICE:  PASS K1  every id column is bigint GENERATED ALWAYS AS IDENTITY
NOTICE:  PASS T1  zero timestamp-without-time-zone columns
NOTICE:  PASS B1  booking.reference is UNIQUE and carries no CHECK (OPEN-REFCHAR-01 left unruled)
NOTICE:  PASS B2  booking.status and booking.cancelled_at exist; no row is cancelled or non-confirmed
NOTICE:  PASS O1  seat.row_label is raw text: no CHECK, no normalising index (OPEN-SEATLABEL-01, OPEN-SEATALPHA-01 unruled)
NOTICE:  PASS O2  password_reset_token: token_sha256 only, and claim / sent / used are three separate columns
NOTICE:  PASS O3  no holds table and no admission/redemption column (OPEN-HOLDRECOVER-01, OPEN-DUPREF-01 unruled)
NOTICE:  PASS U1  users.role vocabulary is exactly customer, manager, admin
NOTICE:  ADVISORY  frontrow_app holds grants beyond the derived least-privilege matrix (not a failure; fix belongs in datamodel.json roles[].grants): booking:DELETE, booking:UPDATE, booking_seat:DELETE, booking_seat:UPDATE, certification:DELETE, cinema:DELETE, format:DELETE, genre:DELETE, idempotency_record:DELETE, language:DELETE, manager_screen_assignment:UPDATE, movie:DELETE, movie_genre:UPDATE, outbox_message:DELETE, password_reset_token:DELETE, payment:DELETE, receipt_dispatch:DELETE, screen:DELETE, seat_category:DELETE, showtime:DELETE, showtime_seat:DELETE, showtime_seat:UPDATE, users:DELETE
NOTICE:  PASS A3  frontrow_app holds every grant the derived matrix says the application needs
NOTICE:  verify_invariants: ALL ASSERTIONS PASSED
DO
```

### Output 4 of 4 — clean up the fixture rows, then verify on the empty schema

```sql
\set ON_ERROR_STOP on
-- remove every fixture row, child to parent (every FK is ON DELETE RESTRICT)
DELETE FROM booking_seat; DELETE FROM booking; DELETE FROM payment; DELETE FROM showtime_seat;
DELETE FROM showtime; DELETE FROM movie; DELETE FROM language; DELETE FROM certification;
DELETE FROM seat; DELETE FROM seat_category; DELETE FROM screen; DELETE FROM cinema; DELETE FROM users;
SELECT string_agg(format('%s=%s', relname, n_live_tup), ' ') AS nonzero FROM pg_stat_user_tables WHERE false;
DO $$ DECLARE t text; n bigint; total bigint := 0; BEGIN
  FOR t IN SELECT tablename FROM pg_tables WHERE schemaname = 'public' LOOP
    EXECUTE format('SELECT count(*) FROM %I', t) INTO n; total := total + n;
    IF n > 0 THEN RAISE NOTICE 'still has rows: % = %', t, n; END IF;
  END LOOP;
  RAISE NOTICE 'rows remaining across all % public tables: %', (SELECT count(*) FROM pg_tables WHERE schemaname='public'), total;
END $$;
```
(The `SELECT ... WHERE false` line is an inert leftover. It returns one empty row and is kept so the
script appears exactly as it was run.)
```
docker exec -i -e PGPASSWORD="$OWNER_PW" frontrow-pg16 psql -h 127.0.0.1 -U frontrow_owner -d frontrow < redproof_cleanup.sql 2>&1 | sed -E 's/^psql:<stdin>:[0-9]+: //'
```
```
DELETE 1
DELETE 1
DELETE 1
DELETE 1
DELETE 1
DELETE 1
DELETE 1
DELETE 1
DELETE 1
DELETE 1
DELETE 1
DELETE 1
DELETE 2
 nonzero 
---------
 
(1 row)

DO
NOTICE:  rows remaining across all 22 public tables: 0
```
```
docker exec -i -e PGPASSWORD="$APP_PW" frontrow-pg16 psql -v ON_ERROR_STOP=1 -h 127.0.0.1 -U frontrow_app -d frontrow \
    < "$DM/checks/verify_invariants.sql" > green_empty.log 2>&1; echo "exit=$?"
grep -cE "NOTICE:  PASS" green_empty.log; grep -E "FAIL|ALL ASSERTIONS" green_empty.log
```
```
exit=0
32
NOTICE:  verify_invariants: ALL ASSERTIONS PASSED
```

## Extra — the payment-state check and the audit-grant check, red-proofed

The DoD asks for the guard only. Before this run, P1 ("no confirmed booking without a captured
payment") and A1 (S-XCT-07) had only ever been seen passing. **A check nobody has watched fail is
decoration**, so both were broken on purpose:

* P1: as the owner, one confirmed booking whose payment is `authorized`, not `captured`. The guard is untouched.
* A1: as the superuser, `GRANT UPDATE ON audit_log TO frontrow_app`.

```sql
\set ON_ERROR_STOP on
-- P1 red-proof: one confirmed booking whose payment is 'authorized' (not captured). Guard untouched.
DO $fx$
DECLARE u1 bigint; ci bigint; sc bigint; se bigint; cat bigint; ce bigint; la bigint; mv bigint; sh bigint; p1 bigint; b1 bigint;
BEGIN
  INSERT INTO users (email, password_hash, role, password_version) VALUES ('redproof-a@example.invalid', 'redproof-not-a-hash', 'customer', 1) RETURNING id INTO u1;
  INSERT INTO cinema (name, timezone, version) VALUES ('Redproof Cinema', 'Asia/Kolkata', 1) RETURNING id INTO ci;
  INSERT INTO screen (cinema_id, name, version) VALUES (ci, 'Redproof Hall', 1) RETURNING id INTO sc;
  INSERT INTO seat_category (name, uplift_basis_points, version) VALUES ('Redproof Category', 0, 1) RETURNING id INTO cat;
  INSERT INTO seat (screen_id, row_label, seat_number, grid_row, grid_col, seat_category_id) VALUES (sc, 'A', 1, 1, 1, cat) RETURNING id INTO se;
  INSERT INTO certification (name, is_active) VALUES ('Redproof Cert', true) RETURNING id INTO ce;
  INSERT INTO language (name, is_active) VALUES ('Redproof Language', true) RETURNING id INTO la;
  INSERT INTO movie (title, synopsis, runtime_minutes, certification_id, language_id, version) VALUES ('Redproof Film', 'Fixture.', 100, ce, la, 1) RETURNING id INTO mv;
  INSERT INTO showtime (movie_id, screen_id, starts_at, ends_at, base_price_paise, seat_count_at_creation, version)
       VALUES (mv, sc, '2026-10-20 13:30:00+00', '2026-10-20 15:10:00+00', 25000, 1, 1) RETURNING id INTO sh;
  INSERT INTO showtime_seat (showtime_id, seat_id) VALUES (sh, se);
  INSERT INTO payment (state, amount_paise, idempotency_key, pending_at, authorized_at)
       VALUES ('authorized', 25000, 'redproof-key-a', '2026-10-18 10:00:00+00', '2026-10-18 10:00:01+00') RETURNING id INTO p1;
  INSERT INTO booking (reference, user_id, showtime_id, payment_id, total_paise, status) VALUES ('REDPROOFA1', u1, sh, p1, 25000, 'confirmed') RETURNING id INTO b1;
  INSERT INTO booking_seat (booking_id, showtime_id, seat_id, price_paise, base_price_paise_applied, uplift_basis_points_applied, seat_category_id)
       VALUES (b1, sh, se, 25000, 25000, 0, cat);
END $fx$;
```
```
docker exec -i -e PGPASSWORD="$OWNER_PW" frontrow-pg16 psql -h 127.0.0.1 -U frontrow_owner -d frontrow < redproof_P1.sql; echo "exit=$?"
docker exec -i frontrow-pg16 psql -v ON_ERROR_STOP=1 -U postgres -d frontrow -c "GRANT UPDATE ON audit_log TO frontrow_app;"
docker exec -i -e PGPASSWORD="$APP_PW" frontrow-pg16 psql -v ON_ERROR_STOP=1 -h 127.0.0.1 -U frontrow_app -d frontrow \
    < "$DM/checks/verify_invariants.sql" > red2.log 2>&1; echo "exit=$?"; grep -E "FAIL|ERROR:  verify" red2.log
docker exec -i frontrow-pg16 psql -v ON_ERROR_STOP=1 -U postgres -d frontrow -c "REVOKE UPDATE ON audit_log FROM frontrow_app;"
docker exec -i -e PGPASSWORD="$OWNER_PW" frontrow-pg16 psql -h 127.0.0.1 -U frontrow_owner -d frontrow < redproof_cleanup.sql 2>&1 | grep -E "NOTICE|ERROR"
docker exec -i -e PGPASSWORD="$APP_PW" frontrow-pg16 psql -v ON_ERROR_STOP=1 -h 127.0.0.1 -U frontrow_app -d frontrow \
    < "$DM/checks/verify_invariants.sql" > green3.log 2>&1; echo "exit=$?"; grep -E "FAIL|ALL ASSERTIONS|PASS A1" green3.log
```
```
### P1 fixture (owner)
DO
exit=0
### A1 sabotage (superuser): GRANT UPDATE ON audit_log TO frontrow_app
GRANT
### verify (app)
exit=3
NOTICE:  FAIL P1  1 booking(s) point at a payment not in state captured (P-PAY-01)
NOTICE:  FAIL A1  frontrow_app on audit_log = INSERT,SELECT,UPDATE (S-XCT-07 requires exactly INSERT,SELECT)
NOTICE:  FAIL A2  frontrow_app effective privileges on audit_log are wrong (FR-ADR-019)
ERROR:  verify_invariants: 3 assertion(s) FAILED - see FAIL lines above
### restore: REVOKE + cleanup
REVOKE
NOTICE:  rows remaining across all 22 public tables: 0
### verify (app) after restore
exit=0
NOTICE:  PASS A1  frontrow_app on audit_log = INSERT,SELECT
NOTICE:  verify_invariants: ALL ASSERTIONS PASSED
```

**Watched failing at least once: G1, G2, G3, P1, A1, A2.** The other 26 assertions have only ever
been seen passing. They are **unverified as red**.

---

## Findings — reported, not fixed (outside this lane's write-set)

*Each finding carries its status after the fix wave at the end of this file.*

**F-1 — `schema.sql` does not need superuser, but if the roles are absent it creates them `NOLOGIN`.**
**FIXED (fix wave):** `schema.sql` no longer creates any role; it only `GRANT`s, and fails loudly if a
role is absent. The order (roles first, by the operator) is documented in `schema.sql` and
`AGENT_CONTRACT.md`.
Its two `DO` blocks run `CREATE ROLE ... NOLOGIN` only when a role is missing. Run as
`frontrow_owner` (NOCREATEROLE) on a database without the roles, that block fails, and that is the
correct failure: roles belong to the operator, not to a migration. A **superuser** run of the same file
would instead silently create an application role **that cannot log in**. In this run the roles
already existed, so both blocks were no-ops.

**F-2 — the generated grants are broader than the documents need.** `datamodel.json` `roles[].grants`
gives `frontrow_app` `SELECT, INSERT, UPDATE, DELETE` on every table except `audit_log`. The
least-privilege matrix derived and cited in `roles_local.sql` §3 needs **23 fewer grants** (the
ADVISORY line lists each one). The ones that matter most are **UPDATE and DELETE on `booking` and
`booking_seat`, and DELETE on `payment` and `users`**. Bookings are permanent: S-XCT-09 says "exactly
two entities are ever removed" (a seat, a manager assignment), and the booking-status criterion
requires `rg 'UPDATE booking SET'` to return 0 hits. An app role that can DELETE a `booking_seat` row
can wipe out the answer to "who booked this seat and when" (SRC-001 §7.6). `verify_invariants.sql`
prints the excess on every run as an **ADVISORY**, not a failure, because narrowing it is a change
for the owner of `datamodel.json`. **FIXED (fix wave):** `roles[].grants` is now exactly the matrix
(86 table privileges to 63), and the ADVISORY became assertion **A4**, which fails on any excess.

**F-3 — `S-PAY-11` cannot pass against this schema.** The `payment.state` column comment says
S-PAY-11 asserts `enum_range(NULL::payment_state)`, but the column is `text` + CHECK:
```
ERROR:  type "payment_state" does not exist
LINE 1: SELECT unnest(enum_range(NULL::payment_state));
                                       ^
```
Either the schema adopts the enum type or the criterion is rewritten. **Not decided here.**
**FIXED (fix wave):** the criterion was rewritten, not the schema. `S-PAY-11` now asserts
`pg_get_constraintdef` of `ck_payment__state`; the column comment no longer claims an enum.

**F-4 — `booking_seat.uplift_basis_points_applied` is `integer`, but the value it copies is `bigint`.**
`seat_category.uplift_basis_points` is `bigint` on purpose, so that S-ADM-13's `368934881464190` is
accepted (AGENT_CONTRACT "not done" item 7). That accepted value **cannot be snapshotted into a booking**:
```
  table_name   |         column_name         | data_type 
---------------+-----------------------------+-----------
 booking_seat  | uplift_basis_points_applied | integer
 seat_category | uplift_basis_points         | bigint
(2 rows)

ERROR:  integer out of range
```
(the error is from `SELECT 368934881464190::bigint::integer;`). The first booking of a seat in that
category would fail at the INSERT. The column is not money, so M1–M3 do not cover it.
**FIXED (fix wave):** `uplift_basis_points_applied` is `bigint`; assertion M6 checks both columns.

**F-5 — duplicate unique indexes.** Every lookup table with a unique name carries two identical unique
expression indexes, `uq_<t>__name_ci` and `ix_<t>__name_ci`. `seat` carries each UNIQUE constraint
plus an identical `ix_` unique index. `showtime_seat` has a PRIMARY KEY and an identical UNIQUE
constraint. That is about twice the needed index count. It does not affect correctness; it doubles
write cost on those tables. `booking_seat` is not affected: G3 confirms it has exactly one unique index.
**FIXED (fix wave), except `showtime_seat`:** the ten `ix_` twins are gone (58 indexes to 48).
`showtime_seat`'s PRIMARY KEY and its UNIQUE are both constraints, and `S-ADM-08` asserts the named
unique by name, so both stay.

## Not covered, on purpose

* That every confirmed booking has a `receipt_dispatch` row is **not asserted**: `FR-ADR-032` and
  `P-TKT-04/05` still disagree about who inserts that row (AGENT_CONTRACT item 6).
* `OPEN-RESETTOKEN-01`, `OPEN-SEATLABEL-01`, `OPEN-SEATALPHA-01`, `OPEN-REFCHAR-01`, `OPEN-DUPREF-01`
  and `OPEN-HOLDRECOVER-01` are asserted only as **absences** (O1–O3, B1). Nothing here answers any of them.
  *(Superseded by the fix wave: SRC-004 rules the first four; see below.)*
* AWS / RDS: nothing was created or inspected. How these roles behave on RDS is **reasoned, not observed**.

## Container state at close

`frontrow-pg16` is **left running** on port 55432, with the schema applied and **zero rows in all 22
tables**. The role passwords existed only for this session and are not recoverable from the repo; to
reuse the container, re-run `roles_local.sql` with new `-v` passwords.

---

# 2026-10-18 (fix wave) — GOAL_08 verifier findings fixed, SRC-004 absorbed

Every block below was **copied from a real run** in this session. Filters are the `grep` lines in
`drive.sh` / `drive2.sh`, both reproduced at the end of this section with every fixture script.

## What changed, and why

| Finding | Change |
|---|---|
| This file claimed password auth; `pg_hba` trusts `127.0.0.1` | Corrected above. Role logins below go to the container's `eth0` address (`host all all all scram-sha-256`); `system_user` proves the method. `docker run` binding recommendation added to Step 0 |
| `verify_invariants.sql` structural checks read `information_schema`, which hides objects the current role cannot see, so they could pass vacuously as `frontrow_app` | Rewritten on `pg_attribute` / `pg_class` / `pg_constraint` / `pg_namespace` / `pg_indexes`. Proved below: with `password_reset_token`'s grants revoked, `information_schema.columns` shows the app **0** of its columns and `pg_attribute` shows **9**, and O2 still goes red on a planted `token` column |
| Money only had to be "an integer type" | M2: every `*_paise` column is exactly `bigint` |
| `outbox_message` payload could carry a token in the DB | O5: `ck_outbox_message__payload_keys_exact` must exist, be validated, be exhaustive for both topics, and name no token key (`SRC-004 R-3`) |
| `S-PAY-09`'s query counted the primary key and failed against a correct schema | Bible `S-PAY-09` now reads `... AND indexname <> 'booking_seat_pkey' ...`; G3 runs that query exactly |
| `S-PAY-11` asserted `enum_range(NULL::payment_state)`; no such type exists | Bible `S-PAY-11` now asserts `pg_get_constraintdef` of `ck_payment__state`; P4 runs it; the column comment is corrected |
| SRC-004 R-3/R-4/R-5 not in the model | `ck_seat__row_label_upper`, `ck_booking__reference_charset`; reserved-row texts cite SRC-004; `reserved-not-decided` allows only the exact ruled CHECKs; O1, O4, B1, O2/O5 |
| Grants broader than the documents need | 86 to 63 table privileges; ADVISORY became A4 |
| `schema.sql` created roles | No `CREATE ROLE` any more; order documented |
| `uplift_basis_points_applied` integer | `bigint`; M6 |
| Duplicate identical unique indexes | 10 `ix_` twins dropped (58 to 48 indexes) |
| Column comments said "no DEFAULT" where DDL has `DEFAULT now()` | Ten `created_at` / `updated_at` comments now state the FR-ADR-018 default |
| Seed rule's PASS overclaimed | It now checks hall sizes and grid dimensions on `screen`, `seat`, `showtime`, `showtime_seat`, and says exactly that |
| Ledger `included_in_datamodel` asserted, not derived | New rule `ledger-datamodel`; the ledger already matched (29 INCLUDED), so nothing flipped; one stale index name removed from a `notes` cell |

`schema.sql` applied in this run: sha256 `6fa76bed896c3bc58671f786a0186063c3fe66505afd6f3425f5ede466a5408c`.

## Static checks

```
$ py generate.py
  wrote schema.sql                     93973 bytes
  wrote TRACEABILITY.tsv               96896 bytes
  wrote seed/expected_summary.json     29158 bytes
  wrote fingerprints.json              21118 bytes
PASS - regenerated from datamodel.json.
exit=0
$ py generate.py --check
PASS - every generated file matches datamodel.json exactly (4 files).
exit=0
$ py generate.py --selftest
  planted a hand-edit in schema.sql                    -> WENT RED (correct)
  restored schema.sql                                  -> verified byte-identical
  planted a hand-edit in seed/expected_summary.json    -> WENT RED (correct)
  restored seed/expected_summary.json                  -> verified byte-identical
  planted a hand-edit in fingerprints.json             -> WENT RED (correct)
  restored fingerprints.json                           -> verified byte-identical
  model bytes changed, nothing regenerated             -> WENT RED on fingerprints.json only (correct)
  booking_seat.price_paise bigint -> integer           -> only booking_seat's fingerprint moved (correct)
  reworded a citation only                             -> no table fingerprint moved (correct)
  a published figure the rules do not give (11004)     -> REFUSED (correct)
      bookings: published 11004, the rules give 11003
  a recorded disagreement that now agrees              -> REFUSED (correct)
      worked_example_k399_booked_seats is listed in known_disagreements but now agrees (72) - remove the record
  a hall whose rows x cols != seats                    -> REFUSED (correct)
      ERROR: Screen 1: 9 x 11 != 90 seats (P-XCT-30 exception 9)
  a table left out of table_expectations               -> REFUSED (correct)
      ERROR: seed_expectations.table_expectations must cover exactly the model's tables; missing ['booking'], unknow
  a card-shaped number in an expectation               -> REFUSED (correct)
      ERROR: a card-shaped digit run reached expected_summary.json
  --check after every restore                          -> green (correct)
VERDICT: PASS - 12 of 12 checks: every planted defect went red, every restore verified.
exit=0
$ py consistency_check.py
datamodel.json vs the documents it was derived from
==============================================================================
PASS  table-set              22 tables: the 15 the Bible queries plus 7 declared
PASS  fk-restrict            every foreign key is ON DELETE RESTRICT
PASS  clock-defaults         row metadata defaults to now(); no decision-bearing instant does
PASS  uncited                zero uncited objects
PASS  money-integer          every money-shaped column is an integer type
PASS  no-card-data           no card-shaped column or comment
PASS  deleted-scope          no scheduler or external-API residue
PASS  timestamptz            every _at column is timestamptz
PASS  seat-guarantee         guarded by booking_seat.uq_booking_seat__showtime_id_seat_id, total (no WHERE); 1 declared non-guard pair(s)
PASS  reset-token-three      claim, sent and used are three distinct columns
PASS  reserved-not-decided   no unruled reserved question answered by a constraint; 2 ruled CHECK(s) present exactly as filed (ck_booking__reference_charset, ck_seat__row_label_upper)
PASS  bible-references       72 distinct references all resolve (152 columns, 39 audit actions declared)
PASS  actions-cited          every one of the 39 declared audit actions is cited
PASS  seed-expectations      22 table expectations, 18 invariants, 6 gaps - all cited; ASSUMED labels kept; seeded names, row letters, base price and uplifts absent from every CHECK and DEFAULT; hall sizes and grid dimensions (9/10/11/12/15/20/90/120/150/180/200/220) absent from every CHECK and DEFAULT on screen, seat, showtime, showtime_seat
PASS  ledger-datamodel       73 ledger rows: 29 INCLUDED, each cited by a schema object; the rest cited by none

rules: 15  -  15 pass  -  0 fail
VERDICT: PASS
exit=0
$ py consistency_check.py --selftest
Red-proofing every rule by planting a defect it must catch.
==============================================================================
  rename booking -> bookings                     -> table-set          RED (correct)
  strip a citation                               -> uncited            RED (correct)
  make a price column text                       -> money-integer      RED (correct)
  add a card_number column                       -> no-card-data       RED (correct)
  add a next_run_at column                       -> deleted-scope      RED (correct)
  turn one foreign key into ON DELETE CASCADE    -> fk-restrict        RED (correct)
  default a decision-bearing instant to now()    -> clock-defaults     RED (correct)
  remove created_at's now() default              -> clock-defaults     RED (correct)
  make an _at column a date                      -> timestamptz        RED (correct)
  drop the (showtime_id, seat_id) unique         -> seat-guarantee     RED (correct)
  make the seat guard a PARTIAL index            -> seat-guarantee     RED (correct)
  collapse email_claimed_at into email_sent_at   -> reset-token-three  RED (correct)
  CHECK the booking-reference alphabet           -> reserved-not-decided RED (correct)
  CHECK banning the letter I in row_label        -> reserved-not-decided RED (correct)
  drop the ruled row_label CHECK (SRC-004 R-4)   -> reserved-not-decided RED (correct)
  harden a hall grid width into a seat CHECK     -> seed-expectations  RED (correct)
  cite an ADR the ledger marks NOT_INCLUDED      -> ledger-datamodel   RED (correct)
  cite a column the Bible does not know          -> bible-references   RED (correct)
  relabel the ASSUMED hall sizes as RULED        -> seed-expectations  RED (correct)
  harden the seeded categories into a CHECK      -> seed-expectations  RED (correct)
  strip the citation from a seed invariant       -> seed-expectations  RED (correct)
  put a card-shaped number in a seed gap         -> seed-expectations  RED (correct)

VERDICT: 22 of 22 rules watched going red.
exit=0
$ py tools/consistency_check.py   (from the repo root)
PASS  rule 1  adr-reference      1458 of 1458 FR-ADR references resolve (ledger rows: 73 · ADR files: 73)
PASS  rule 2  open-reference     1274 of 1274 OPEN references resolve (67 Article X rows · 40 SRC-003 sections)
PASS  rule 3  source-citation    2849 of 2849 clause citations resolve (SRC-001: 109 anchors · SRC-002: 140 anchors)
PASS  rule 4  erratum-crossref   18 of 18 erratum claims resolve
PASS  rule 5  fingerprint        6 of 6 fingerprint assertions resolve
PASS  rule 6  readme-paths       30 of 30 path claims resolve · 5 path claim(s) in rows the table itself marks not-yet-written, deferred
PASS  rule 7  prep-queue-status  20 of 20 queue rows resolve
PASS  rule 8  ledger-header      20 of 20 columns resolve (20 in the ledger · 20 documented)
PASS  rule 9  readme-state       20 of 20 state claims resolve

rules: 9  ·  9 pass  ·  0 fail  ·  0 skip
VERDICT: PASS — every cross-reference that can be checked today resolves.
         This is the cheap layer only (Art IX.6). It cannot see two documents
         that each resolve fine and contradict each other — that is GOAL_13.
exit=0
```

## Live database: fresh database, roles, schema as owner, verify as app, red-proofs

```
bash drive.sh
```
```
### step 0: engine, schema.sql digest, auth rules in force
postgres (PostgreSQL) 16.15
6fa76bed896c3bc58671f786a0186063c3fe66505afd6f3425f5ede466a5408c *D:/Project/FrontRow/docs/06 DataModel/schema.sql
container eth0 address used for role logins: 172.17.0.2
local   all             all                                     trust
host    all             all             127.0.0.1/32            trust
host    all             all             ::1/128                 trust
local   replication     all                                     trust
host    replication     all             127.0.0.1/32            trust
host    replication     all             ::1/128                 trust
host all all all scram-sha-256
### step 1: fresh empty database (superuser, local socket)
DROP DATABASE
CREATE DATABASE
exit=0
### step 2: roles_local.sql as superuser
DO
ALTER ROLE
ALTER ROLE
ALTER ROLE
ALTER ROLE
DO
DO
GRANT
GRANT
REVOKE
REVOKE
exit=0
### step 3: schema.sql AS frontrow_owner, password (scram) login over TCP to 172.17.0.2
  current_user  |  session_user  |         system_user          | is_superuser 
----------------+----------------+------------------------------+--------------
 frontrow_owner | frontrow_owner | scram-sha-256:frontrow_owner | f
(1 row)

exit=0
statement tally:
     24 GRANT
     22 CREATE TABLE
     19 CREATE INDEX
      1 COMMIT
      1 BEGIN
objects (tables|indexes|sequences|all relations):
22|48|20|90
### step 4: verify_invariants.sql AS frontrow_app on the fresh schema
 current_user | session_user |        system_user         
--------------+--------------+----------------------------
 frontrow_app | frontrow_app | scram-sha-256:frontrow_app
(1 row)

exit=0
== LISTING 1: every money column and its type (GOAL_08 DoD: zero float money columns) ==
  table_name  |       column_name        | data_type 
--------------+--------------------------+-----------
 booking      | total_paise              | bigint
 booking_seat | base_price_paise_applied | bigint
 booking_seat | price_paise              | bigint
 payment      | amount_paise             | bigint
 showtime     | base_price_paise         | bigint
(5 rows)

== LISTING 2: any float / numeric / money column anywhere in public (must be empty) ==
 table_name | column_name | data_type 
------------+-------------+-----------
(0 rows)

== LISTING 3: S-XCT-07 verbatim shape - audit_log privileges held by frontrow_app ==
 privilege_type 
----------------
 INSERT
 SELECT
(2 rows)

== LISTING 4: the seat guarantee as the catalog stores it ==
               conname                |          definition           
--------------------------------------+-------------------------------
 booking_seat_pkey                    | PRIMARY KEY (id)
 uq_booking_seat__showtime_id_seat_id | UNIQUE (showtime_id, seat_id)
(2 rows)

== ASSERTIONS ==
NOTICE:  PASS G1  no (showtime_id, seat_id) pair is held by two booking_seat rows
NOTICE:  PASS G2  uq_booking_seat__showtime_id_seat_id = UNIQUE (showtime_id, seat_id)
NOTICE:  PASS G3  S-PAY-09: exactly 1 UNIQUE index on booking_seat besides the pkey, total: CREATE UNIQUE INDEX uq_booking_seat__showtime_id_seat_id ON public.booking_seat USING btree (showtime_id, seat_id)
NOTICE:  PASS G4  every booking_seat matches its booking's showtime and that showtime's inventory
NOTICE:  PASS P1  every booking points at a payment in state captured
NOTICE:  PASS P2  booking.payment_id is NOT NULL and a foreign key to payment
NOTICE:  PASS P3  payment has no booking_id column (S-PAY-05)
NOTICE:  PASS P4  S-PAY-11: ck_payment__state = CHECK ((state = ANY (ARRAY['pending'::text, 'authorized'::text, 'captured'::text, 'failed'::text])))
NOTICE:  PASS M1  zero real/double/numeric/money columns in schema public (152 columns read)
NOTICE:  PASS M2  every *_paise column is bigint (and at least the 5 known money columns exist)
NOTICE:  PASS M3  money columns on booking/booking_seat/payment are exactly booking.total_paise,booking_seat.base_price_paise_applied,booking_seat.price_paise,payment.amount_paise
NOTICE:  PASS M4  every booking.total_paise equals the sum of its seats' price_paise
NOTICE:  PASS M5  no booking holds more than 10 seats
NOTICE:  PASS M6  seat_category.uplift_basis_points and booking_seat.uplift_basis_points_applied are both bigint
NOTICE:  PASS I1  uq_idempotency_record__user_id_idempotency_key = UNIQUE (user_id, idempotency_key)
NOTICE:  PASS I2  no (user_id, idempotency_key) pair is stored twice
NOTICE:  PASS I3  payment.idempotency_key carries no unique index (S-PAY-15)
NOTICE:  PASS A1  frontrow_app on audit_log = INSERT,SELECT
NOTICE:  PASS A2  frontrow_app effectively can SELECT, INSERT and cannot UPDATE, DELETE, TRUNCATE audit_log
NOTICE:  PASS R1  both roles exist and neither is superuser / bypassrls / createrole / createdb
NOTICE:  PASS R2  every relation in public is owned by frontrow_owner (so frontrow_app owns none)
NOTICE:  PASS R3  frontrow_app cannot CREATE in schema public
NOTICE:  PASS R4  frontrow_app holds no TRUNCATE / REFERENCES / TRIGGER on any table
NOTICE:  PASS R5  frontrow_app is not a member of frontrow_owner
NOTICE:  PASS F1  every foreign key in public is ON DELETE RESTRICT
NOTICE:  PASS K1  every id column is bigint GENERATED ALWAYS AS IDENTITY
NOTICE:  PASS T1  zero timestamp-without-time-zone columns
NOTICE:  PASS B1  booking.reference is UNIQUE and ck_booking__reference_charset = CHECK ((reference ~ '^[23456789ACDEFHJKMNPQRTVWXY]{9}$'::text)) (SRC-004 R-5)
NOTICE:  PASS B2  booking.status and booking.cancelled_at exist; no row is cancelled or non-confirmed
NOTICE:  PASS O1  ck_seat__row_label_upper = CHECK ((row_label = upper(btrim(row_label)))) (OPEN-SEATLABEL-01, SRC-004 R-4)
NOTICE:  PASS O4  seat.row_label: text, no letter-banning CHECK, no normalising index (OPEN-SEATALPHA-01: I allowed)
NOTICE:  PASS O2  no plaintext-token column anywhere; token_sha256 only; claim / sent / used are three columns (SRC-004 R-3)
NOTICE:  PASS O5  ck_outbox_message__payload_keys_exact exists, is validated, is exhaustive for both topics and names no token key (SRC-004 R-3)
NOTICE:  PASS O3  no holds table and no admission/redemption column (OPEN-HOLDRECOVER-01, OPEN-DUPREF-01 unruled)
NOTICE:  PASS U1  users.role vocabulary is exactly customer, manager, admin
NOTICE:  PASS A3  frontrow_app holds every grant the derived matrix says the application needs
NOTICE:  PASS A4  frontrow_app holds no table privilege beyond the derived matrix, on all 22 tables
NOTICE:  verify_invariants: ALL ASSERTIONS PASSED
DO
### step 4b: the two fixed Bible criteria, literally, as frontrow_app
                                                      indexdef                                                      
--------------------------------------------------------------------------------------------------------------------
 CREATE UNIQUE INDEX uq_booking_seat__showtime_id_seat_id ON public.booking_seat USING btree (showtime_id, seat_id)
 CREATE INDEX ix_booking_seat__booking_id ON public.booking_seat USING btree (booking_id)
(2 rows)

                                         pg_get_constraintdef                                         
------------------------------------------------------------------------------------------------------
 CHECK ((state = ANY (ARRAY['pending'::text, 'authorized'::text, 'captured'::text, 'failed'::text])))
(1 row)

### step 5a: AS OWNER drop the guard and oversell one seat
  current_user  |         system_user          
----------------+------------------------------
 frontrow_owner | scram-sha-256:frontrow_owner
(1 row)

ALTER TABLE
DO
 reference | showtime_id | seat_id 
-----------+-------------+---------
 ACDEFHJK2 |           1 |       1
 ACDEFHJK3 |           1 |       1
(2 rows)

exit=0
### step 5a verify (app) - must be RED
exit=3
== LISTING 1: every money column and its type (GOAL_08 DoD: zero float money columns) ==
  table_name  |       column_name        | data_type 
--------------+--------------------------+-----------
 booking      | total_paise              | bigint
 booking_seat | base_price_paise_applied | bigint
 booking_seat | price_paise              | bigint
 payment      | amount_paise             | bigint
 showtime     | base_price_paise         | bigint
(5 rows)

== LISTING 2: any float / numeric / money column anywhere in public (must be empty) ==
 table_name | column_name | data_type 
------------+-------------+-----------
(0 rows)

== LISTING 3: S-XCT-07 verbatim shape - audit_log privileges held by frontrow_app ==
 privilege_type 
----------------
 INSERT
 SELECT
(2 rows)

== LISTING 4: the seat guarantee as the catalog stores it ==
      conname      |    definition    
-------------------+------------------
 booking_seat_pkey | PRIMARY KEY (id)
(1 row)

== ASSERTIONS ==
NOTICE:  FAIL G1  1 seat(s) SOLD TWICE: (showtime_id=1, seat_id=1) x2
NOTICE:  FAIL G2  guard constraint uq_booking_seat__showtime_id_seat_id is MISSING
NOTICE:  FAIL G3  S-PAY-09: 0 UNIQUE index(es) on booking_seat besides the pkey (want 1, on (showtime_id, seat_id), no WHERE); last = none
NOTICE:  PASS G4  every booking_seat matches its booking's showtime and that showtime's inventory
NOTICE:  PASS P1  every booking points at a payment in state captured
NOTICE:  PASS P2  booking.payment_id is NOT NULL and a foreign key to payment
NOTICE:  PASS P3  payment has no booking_id column (S-PAY-05)
NOTICE:  PASS P4  S-PAY-11: ck_payment__state = CHECK ((state = ANY (ARRAY['pending'::text, 'authorized'::text, 'captured'::text, 'failed'::text])))
NOTICE:  PASS M1  zero real/double/numeric/money columns in schema public (152 columns read)
NOTICE:  PASS M2  every *_paise column is bigint (and at least the 5 known money columns exist)
NOTICE:  PASS M3  money columns on booking/booking_seat/payment are exactly booking.total_paise,booking_seat.base_price_paise_applied,booking_seat.price_paise,payment.amount_paise
NOTICE:  PASS M4  every booking.total_paise equals the sum of its seats' price_paise
NOTICE:  PASS M5  no booking holds more than 10 seats
NOTICE:  PASS M6  seat_category.uplift_basis_points and booking_seat.uplift_basis_points_applied are both bigint
NOTICE:  PASS I1  uq_idempotency_record__user_id_idempotency_key = UNIQUE (user_id, idempotency_key)
NOTICE:  PASS I2  no (user_id, idempotency_key) pair is stored twice
NOTICE:  PASS I3  payment.idempotency_key carries no unique index (S-PAY-15)
NOTICE:  PASS A1  frontrow_app on audit_log = INSERT,SELECT
NOTICE:  PASS A2  frontrow_app effectively can SELECT, INSERT and cannot UPDATE, DELETE, TRUNCATE audit_log
NOTICE:  PASS R1  both roles exist and neither is superuser / bypassrls / createrole / createdb
NOTICE:  PASS R2  every relation in public is owned by frontrow_owner (so frontrow_app owns none)
NOTICE:  PASS R3  frontrow_app cannot CREATE in schema public
NOTICE:  PASS R4  frontrow_app holds no TRUNCATE / REFERENCES / TRIGGER on any table
NOTICE:  PASS R5  frontrow_app is not a member of frontrow_owner
NOTICE:  PASS F1  every foreign key in public is ON DELETE RESTRICT
NOTICE:  PASS K1  every id column is bigint GENERATED ALWAYS AS IDENTITY
NOTICE:  PASS T1  zero timestamp-without-time-zone columns
NOTICE:  PASS B1  booking.reference is UNIQUE and ck_booking__reference_charset = CHECK ((reference ~ '^[23456789ACDEFHJKMNPQRTVWXY]{9}$'::text)) (SRC-004 R-5)
NOTICE:  PASS B2  booking.status and booking.cancelled_at exist; no row is cancelled or non-confirmed
NOTICE:  PASS O1  ck_seat__row_label_upper = CHECK ((row_label = upper(btrim(row_label)))) (OPEN-SEATLABEL-01, SRC-004 R-4)
NOTICE:  PASS O4  seat.row_label: text, no letter-banning CHECK, no normalising index (OPEN-SEATALPHA-01: I allowed)
NOTICE:  PASS O2  no plaintext-token column anywhere; token_sha256 only; claim / sent / used are three columns (SRC-004 R-3)
NOTICE:  PASS O5  ck_outbox_message__payload_keys_exact exists, is validated, is exhaustive for both topics and names no token key (SRC-004 R-3)
NOTICE:  PASS O3  no holds table and no admission/redemption column (OPEN-HOLDRECOVER-01, OPEN-DUPREF-01 unruled)
NOTICE:  PASS U1  users.role vocabulary is exactly customer, manager, admin
NOTICE:  PASS A3  frontrow_app holds every grant the derived matrix says the application needs
NOTICE:  PASS A4  frontrow_app holds no table privilege beyond the derived matrix, on all 22 tables
ERROR:  verify_invariants: 3 assertion(s) FAILED - see FAIL lines above
CONTEXT:  PL/pgSQL function inline_code_block line 507 at RAISE
### step 5b: AS OWNER remove the oversold row, restore the guard, verify the restore
DELETE 1
DELETE 1
DELETE 1
ALTER TABLE
               conname                |          definition           
--------------------------------------+-------------------------------
 uq_booking_seat__showtime_id_seat_id | UNIQUE (showtime_id, seat_id)
(1 row)

                index                 | indisunique | total_no_where 
--------------------------------------+-------------+----------------
 uq_booking_seat__showtime_id_seat_id | t           | t
(1 row)

exit=0
### step 5b': the same oversell against the restored guard
BEGIN
INSERT 0 1
INSERT 0 1
ERROR:  duplicate key value violates unique constraint "uq_booking_seat__showtime_id_seat_id"
DETAIL:  Key (showtime_id, seat_id)=(1, 1) already exists.
ROLLBACK
 booking_seat_rows_for_seat_1 
------------------------------
                            1
(1 row)

### step 5c: verify (app) with the surviving fixture booking present - must be GREEN
exit=0
37
NOTICE:  verify_invariants: ALL ASSERTIONS PASSED
fixture rows live: bookings=1 booking_seats=1 seats=1
### step 6: SRC-004 CHECKs red-proofed AS frontrow_app (fixture still present)
 current_user |        system_user         
--------------+----------------------------
 frontrow_app | scram-sha-256:frontrow_app
(1 row)

ERROR:  new row for relation "seat" violates check constraint "ck_seat__row_label_upper"
DETAIL:  Failing row contains (2, 1, c, 12, 3, 12, 1, t, 2026-10-18 05:29:26.402146+00).
ERROR:  new row for relation "seat" violates check constraint "ck_seat__row_label_upper"
DETAIL:  Failing row contains (3, 1,  C, 12, 3, 12, 1, t, 2026-10-18 05:29:26.405636+00).
BEGIN
INSERT 0 1
INSERT 0 1
 row_label | seat_number 
-----------+-------------
 A         |           1
 C         |          12
 I         |           1
(3 rows)

ROLLBACK
BEGIN
INSERT 0 1
SAVEPOINT
ERROR:  new row for relation "booking" violates check constraint "ck_booking__reference_charset"
DETAIL:  Failing row contains (4, ACDEFHJK, 1, 1, 4, 25000, confirmed, null, 2026-10-18 05:29:26.414737+00).
ROLLBACK
ERROR:  new row for relation "booking" violates check constraint "ck_booking__reference_charset"
DETAIL:  Failing row contains (5, ACDEFHJKZ, 1, 1, 4, 25000, confirmed, null, 2026-10-18 05:29:26.414737+00).
ROLLBACK
ERROR:  new row for relation "booking" violates check constraint "ck_booking__reference_charset"
DETAIL:  Failing row contains (6, acdefhjk4, 1, 1, 4, 25000, confirmed, null, 2026-10-18 05:29:26.414737+00).
ROLLBACK
ERROR:  new row for relation "booking" violates check constraint "ck_booking__reference_charset"
DETAIL:  Failing row contains (7, REDPROOFA1, 1, 1, 4, 25000, confirmed, null, 2026-10-18 05:29:26.414737+00).
ROLLBACK
INSERT 0 1
 reference | len 
-----------+-----
 2589ACDE7 |   9
 ACDEFHJK2 |   9
(2 rows)

ROLLBACK
 seats_after | bookings_after | payments_after 
-------------+----------------+----------------
           1 |              1 |              1
(1 row)

### step 7: verify_invariants O1/B1/A4 red-proofed (superuser sabotage)
ALTER TABLE
ALTER TABLE
GRANT
exit=0
exit=3
NOTICE:  FAIL B1  booking.reference charset CHECK is MISSING or its UNIQUE is missing (SRC-004 R-5)
NOTICE:  FAIL O1  ck_seat__row_label_upper is MISSING (SRC-004 R-4)
NOTICE:  FAIL A4  frontrow_app holds privileges beyond the least-privilege matrix, or the table count differs from it: booking_seat:DELETE
ERROR:  verify_invariants: 3 assertion(s) FAILED - see FAIL lines above
### step 7 restore (superuser) and verify the restore
REVOKE
ALTER TABLE
ALTER TABLE
   tbl   |            conname            |                           definition                            | convalidated 
---------+-------------------------------+-----------------------------------------------------------------+--------------
 seat    | ck_seat__row_label_upper      | CHECK ((row_label = upper(btrim(row_label))))                   | t
 booking | ck_booking__reference_charset | CHECK ((reference ~ '^[23456789ACDEFHJKMNPQRTVWXY]{9}$'::text)) | t
(2 rows)

 app_can_delete_booking_seat 
-----------------------------
 f
(1 row)

exit=0
exit=0
37
NOTICE:  PASS B1  booking.reference is UNIQUE and ck_booking__reference_charset = CHECK ((reference ~ '^[23456789ACDEFHJKMNPQRTVWXY]{9}$'::text)) (SRC-004 R-5)
NOTICE:  PASS O1  ck_seat__row_label_upper = CHECK ((row_label = upper(btrim(row_label)))) (OPEN-SEATLABEL-01, SRC-004 R-4)
NOTICE:  PASS A4  frontrow_app holds no table privilege beyond the derived matrix, on all 22 tables
NOTICE:  verify_invariants: ALL ASSERTIONS PASSED
### step 8: cleanup (owner) then verify on the empty schema
NOTICE:  rows remaining across all 22 public tables: 0
exit=0
37
NOTICE:  verify_invariants: ALL ASSERTIONS PASSED
```

**Watched failing in this run:** G1, G2, G3 (guard dropped, seat sold twice), B1, O1, A4 (both SRC-004
CHECKs dropped, one excess grant), and the two CHECKs themselves (six refused INSERTs). Every
restore was verified: `pg_get_constraintdef` for the guard and both CHECKs, `has_table_privilege` for
the revoked grant, then a green run.

## Live database: the vacuity proof, O2 and O5

```
bash drive2.sh
```
```
### re-run roles_local.sql (superuser) with fresh passwords
exit=0
### sabotage E (owner)
ALTER TABLE
REVOKE
ALTER TABLE
exit=0
### what frontrow_app can see of password_reset_token
           source           | columns_visible 
----------------------------+-----------------
 information_schema.columns |               0
 pg_attribute               |               9
(2 rows)

### verify (app) - must be RED
exit=3
NOTICE:  FAIL O2  token-shaped column(s) other than password_reset_token.token_sha256: password_reset_token.token (SRC-004 R-3)
NOTICE:  FAIL O5  outbox_message payload-keys CHECK is missing, unvalidated, not exhaustive, or admits a token key: MISSING
NOTICE:  FAIL A3  frontrow_app is MISSING grants the application needs: password_reset_token:INSERT, password_reset_token:SELECT, password_reset_token:UPDATE
ERROR:  verify_invariants: 3 assertion(s) FAILED - see FAIL lines above
### restore E (owner) and verify the restore
ALTER TABLE
GRANT
ALTER TABLE
                conname                | convalidated 
---------------------------------------+--------------
 ck_outbox_message__payload_keys_exact | t
(1 row)

 token_columns 
---------------
             0
(1 row)

exit=0
exit=0
37
NOTICE:  PASS O2  no plaintext-token column anywhere; token_sha256 only; claim / sent / used are three columns (SRC-004 R-3)
NOTICE:  PASS O5  ck_outbox_message__payload_keys_exact exists, is validated, is exhaustive for both topics and names no token key (SRC-004 R-3)
NOTICE:  PASS A3  frontrow_app holds every grant the derived matrix says the application needs
NOTICE:  verify_invariants: ALL ASSERTIONS PASSED
```

**Watched failing in this second run:** O2, O5, A3. `information_schema.columns` showed the app none
of `password_reset_token`'s columns while `pg_attribute` showed all nine, which is the vacuous pass
the old file was exposed to.

**Assertions watched failing at least once, across both runs and the morning run:** G1, G2, G3, P1,
A1, A2, A3, A4, B1, O1, O2, O5. The other 25 of the 37 have only been seen passing and are
**unverified as red**.

## Not covered, on purpose

* The concurrency proof (Redis lock + `scripts/stress_seats.py`, 50 requests) is Phase 4 and does
  not exist. This is still the database half only.
* The reference CHECK enforces the alphabet and the length only. The check character's algorithm is
  code (SRC-004 R-5 `[JUDGMENT CALL]`) and is not verified here.
* AWS / RDS: nothing was created or inspected. Role behaviour on RDS is **reasoned, not observed**.

## Container state at close

`frontrow-pg16` is **left running**, still published on `0.0.0.0:55432` (see the recommendation in
Step 0), with database `frontrow` holding the fix-wave schema and **zero rows in all 22 tables**. The
role passwords existed only inside the two driver processes and are not recoverable.

## The driver scripts and fixtures, verbatim

`drive.sh`:
```bash
#!/usr/bin/env bash
# Fix-wave live run. Passwords live only in this process's environment.
set -u
DM="D:/Project/FrontRow/docs/06 DataModel"
R="$(cd "$(dirname "$0")" && pwd)"
C=frontrow-pg16
OWNER_PW=$(py -c "import secrets;print(secrets.token_urlsafe(18))")
APP_PW=$(py -c "import secrets;print(secrets.token_urlsafe(18))")
# The container's own eth0 address: pg_hba's "host all all all scram-sha-256"
# line applies to it, unlike 127.0.0.1 which the image trusts.
IP=$(docker exec $C hostname -i | tr -d '\r ')
strip() { sed -E 's/^psql:<stdin>:[0-9]+: //'; }
as_super() { docker exec -i $C psql -U postgres -d frontrow "$@"; }
as_owner() { docker exec -i -e PGPASSWORD="$OWNER_PW" $C psql -h "$IP" -U frontrow_owner -d frontrow "$@"; }
as_app()   { docker exec -i -e PGPASSWORD="$APP_PW"   $C psql -h "$IP" -U frontrow_app   -d frontrow "$@"; }
verify()   { as_app -v ON_ERROR_STOP=1 < "$DM/checks/verify_invariants.sql" > "$R/$1.log" 2>&1; echo "exit=$?"; }

echo "### step 0: engine, schema.sql digest, auth rules in force"
docker exec $C postgres --version
sha256sum "$DM/schema.sql"
echo "container eth0 address used for role logins: $IP"
docker exec $C sh -c 'grep -vE "^\s*(#|$)" "$(psql -U postgres -Atc "show hba_file")"'

echo "### step 1: fresh empty database (superuser, local socket)"
docker exec -i $C psql -v ON_ERROR_STOP=1 -U postgres -d postgres \
  -c "DROP DATABASE IF EXISTS frontrow WITH (FORCE);" -c "CREATE DATABASE frontrow;"; echo "exit=$?"

echo "### step 2: roles_local.sql as superuser"
as_super -v ON_ERROR_STOP=1 -v owner_password="$OWNER_PW" -v app_password="$APP_PW" < "$DM/checks/roles_local.sql" 2>&1 | strip; echo "exit=${PIPESTATUS[0]}"

echo "### step 3: schema.sql AS frontrow_owner, password (scram) login over TCP to $IP"
as_owner -v ON_ERROR_STOP=1 -c "SELECT current_user, session_user, system_user, (SELECT rolsuper FROM pg_roles WHERE rolname=current_user) AS is_superuser;"
as_owner -v ON_ERROR_STOP=1 < "$DM/schema.sql" > "$R/apply.log" 2>&1; echo "exit=$?"
echo "statement tally:"; sort "$R/apply.log" | uniq -c | sort -rn
echo "objects (tables|indexes|sequences|all relations):"
as_super -Atc "SELECT count(*) FILTER (WHERE relkind='r'), count(*) FILTER (WHERE relkind='i'), count(*) FILTER (WHERE relkind='S'), count(*) FROM pg_class WHERE relnamespace='public'::regnamespace;"

echo "### step 4: verify_invariants.sql AS frontrow_app on the fresh schema"
as_app -v ON_ERROR_STOP=1 -c "SELECT current_user, session_user, system_user;"
verify green_fresh; strip < "$R/green_fresh.log"

echo "### step 4b: the two fixed Bible criteria, literally, as frontrow_app"
as_app < "$R/literal_bible.sql" 2>&1 | strip

echo "### step 5a: AS OWNER drop the guard and oversell one seat"
as_owner < "$R/fixture_A.sql" 2>&1 | strip; echo "exit=${PIPESTATUS[0]}"
echo "### step 5a verify (app) - must be RED"
verify red_guard; strip < "$R/red_guard.log"

echo "### step 5b: AS OWNER remove the oversold row, restore the guard, verify the restore"
as_owner < "$R/restore_B.sql" 2>&1 | strip; echo "exit=${PIPESTATUS[0]}"
echo "### step 5b': the same oversell against the restored guard"
as_owner < "$R/refused_B2.sql" 2>&1 | strip

echo "### step 5c: verify (app) with the surviving fixture booking present - must be GREEN"
verify green_after
grep -cE "NOTICE:  PASS" "$R/green_after.log"; grep -E "FAIL|ALL ASSERTIONS|ERROR" "$R/green_after.log" | strip
as_app -Atc "SELECT 'fixture rows live: bookings='||(SELECT count(*) FROM booking)||' booking_seats='||(SELECT count(*) FROM booking_seat)||' seats='||(SELECT count(*) FROM seat);"

echo "### step 6: SRC-004 CHECKs red-proofed AS frontrow_app (fixture still present)"
as_app < "$R/checks_C.sql" 2>&1 | strip

echo "### step 7: verify_invariants O1/B1/A4 red-proofed (superuser sabotage)"
as_super < "$R/sabotage_D.sql" 2>&1 | strip; echo "exit=${PIPESTATUS[0]}"
verify red_checks; grep -E "FAIL|ERROR:  verify" "$R/red_checks.log" | strip
echo "### step 7 restore (superuser) and verify the restore"
as_super < "$R/restore_D.sql" 2>&1 | strip; echo "exit=${PIPESTATUS[0]}"
verify green_restored; grep -cE "NOTICE:  PASS" "$R/green_restored.log"; grep -E "FAIL|ALL ASSERTIONS|PASS (O1|B1|A4)" "$R/green_restored.log" | strip

echo "### step 8: cleanup (owner) then verify on the empty schema"
as_owner < "$R/cleanup.sql" 2>&1 | grep -E "NOTICE|ERROR" | strip
verify green_empty; grep -cE "NOTICE:  PASS" "$R/green_empty.log"; grep -E "FAIL|ALL ASSERTIONS" "$R/green_empty.log" | strip
```
`drive2.sh`:
```bash
#!/usr/bin/env bash
# Second drill on the same fresh database: O2 / O5 and the information_schema vacuity.
# New random passwords are set first (the first run's existed only in its own process).
set -u
DM="D:/Project/FrontRow/docs/06 DataModel"
R="$(cd "$(dirname "$0")" && pwd)"
C=frontrow-pg16
OWNER_PW=$(py -c "import secrets;print(secrets.token_urlsafe(18))")
APP_PW=$(py -c "import secrets;print(secrets.token_urlsafe(18))")
IP=$(docker exec $C hostname -i | tr -d '\r ')
strip() { sed -E 's/^psql:<stdin>:[0-9]+: //'; }
as_owner() { docker exec -i -e PGPASSWORD="$OWNER_PW" $C psql -h "$IP" -U frontrow_owner -d frontrow "$@"; }
as_app()   { docker exec -i -e PGPASSWORD="$APP_PW"   $C psql -h "$IP" -U frontrow_app   -d frontrow "$@"; }
verify()   { as_app -v ON_ERROR_STOP=1 < "$DM/checks/verify_invariants.sql" > "$R/$1.log" 2>&1; echo "exit=$?"; }

echo "### re-run roles_local.sql (superuser) with fresh passwords"
docker exec -i $C psql -v ON_ERROR_STOP=1 -v owner_password="$OWNER_PW" -v app_password="$APP_PW" -U postgres -d frontrow < "$DM/checks/roles_local.sql" > /dev/null 2>&1; echo "exit=$?"
echo "### sabotage E (owner)"
as_owner < "$R/sabotage_E.sql" 2>&1 | strip; echo "exit=${PIPESTATUS[0]}"
echo "### what frontrow_app can see of password_reset_token"
as_app < "$R/vacuity.sql" 2>&1 | strip
echo "### verify (app) - must be RED"
verify red_token; grep -E "FAIL|ERROR:  verify" "$R/red_token.log" | strip
echo "### restore E (owner) and verify the restore"
as_owner < "$R/restore_E.sql" 2>&1 | strip; echo "exit=${PIPESTATUS[0]}"
verify green_token; grep -cE "NOTICE:  PASS" "$R/green_token.log"; grep -E "FAIL|ALL ASSERTIONS|PASS (O2|O5|A3)" "$R/green_token.log" | strip
```
`fixture_A.sql`:
```sql
\set ON_ERROR_STOP on
SELECT current_user, system_user;
-- RED-PROOF STAGE A: the guard is dropped on purpose.
ALTER TABLE booking_seat DROP CONSTRAINT uq_booking_seat__showtime_id_seat_id;
-- Minimal VALID fixture. Invented test data only. No card data: payment is simulated
-- and the schema has no card column. References are 9 characters of the SRC-004 R-5
-- alphabet (the trailing character stands in for a check character; no algorithm is
-- implemented here). Two customers, one showtime, one seat, two captured payments,
-- two confirmed bookings, two booking_seat rows for ONE seat.
DO $fx$
DECLARE u1 bigint; u2 bigint; ci bigint; sc bigint; se bigint; cat bigint;
        ce bigint; la bigint; mv bigint; sh bigint; p1 bigint; p2 bigint; b1 bigint; b2 bigint;
BEGIN
  INSERT INTO users (email, password_hash, role, password_version)
       VALUES ('redproof-a@example.invalid', 'redproof-not-a-hash', 'customer', 1) RETURNING id INTO u1;
  INSERT INTO users (email, password_hash, role, password_version)
       VALUES ('redproof-b@example.invalid', 'redproof-not-a-hash', 'customer', 1) RETURNING id INTO u2;
  INSERT INTO cinema (name, timezone, version) VALUES ('Redproof Cinema', 'Asia/Kolkata', 1) RETURNING id INTO ci;
  INSERT INTO screen (cinema_id, name, version) VALUES (ci, 'Redproof Hall', 1) RETURNING id INTO sc;
  INSERT INTO seat_category (name, uplift_basis_points, version) VALUES ('Redproof Category', 0, 1) RETURNING id INTO cat;
  INSERT INTO seat (screen_id, row_label, seat_number, grid_row, grid_col, seat_category_id)
       VALUES (sc, 'A', 1, 1, 1, cat) RETURNING id INTO se;
  INSERT INTO certification (name, is_active) VALUES ('Redproof Cert', true) RETURNING id INTO ce;
  INSERT INTO language (name, is_active) VALUES ('Redproof Language', true) RETURNING id INTO la;
  INSERT INTO movie (title, synopsis, runtime_minutes, certification_id, language_id, version)
       VALUES ('Redproof Film', 'Fixture.', 100, ce, la, 1) RETURNING id INTO mv;
  INSERT INTO showtime (movie_id, screen_id, starts_at, ends_at, base_price_paise, seat_count_at_creation, version)
       VALUES (mv, sc, '2026-10-20 13:30:00+00', '2026-10-20 15:10:00+00', 25000, 1, 1) RETURNING id INTO sh;
  INSERT INTO showtime_seat (showtime_id, seat_id) VALUES (sh, se);
  INSERT INTO payment (state, amount_paise, idempotency_key, pending_at, authorized_at, captured_at)
       VALUES ('captured', 25000, 'redproof-key-a', '2026-10-18 10:00:00+00', '2026-10-18 10:00:01+00', '2026-10-18 10:00:02+00') RETURNING id INTO p1;
  INSERT INTO payment (state, amount_paise, idempotency_key, pending_at, authorized_at, captured_at)
       VALUES ('captured', 25000, 'redproof-key-b', '2026-10-18 10:00:00+00', '2026-10-18 10:00:01+00', '2026-10-18 10:00:02+00') RETURNING id INTO p2;
  INSERT INTO booking (reference, user_id, showtime_id, payment_id, total_paise, status)
       VALUES ('ACDEFHJK2', u1, sh, p1, 25000, 'confirmed') RETURNING id INTO b1;
  INSERT INTO booking (reference, user_id, showtime_id, payment_id, total_paise, status)
       VALUES ('ACDEFHJK3', u2, sh, p2, 25000, 'confirmed') RETURNING id INTO b2;
  INSERT INTO booking_seat (booking_id, showtime_id, seat_id, price_paise, base_price_paise_applied, uplift_basis_points_applied, seat_category_id)
       VALUES (b1, sh, se, 25000, 25000, 0, cat);
  -- the oversell: the SAME (showtime_id, seat_id), accepted because the guard is gone
  INSERT INTO booking_seat (booking_id, showtime_id, seat_id, price_paise, base_price_paise_applied, uplift_basis_points_applied, seat_category_id)
       VALUES (b2, sh, se, 25000, 25000, 0, cat);
END $fx$;
SELECT b.reference, bs.showtime_id, bs.seat_id FROM booking_seat bs JOIN booking b ON b.id = bs.booking_id ORDER BY b.reference;
```
`restore_B.sql`:
```sql
\set ON_ERROR_STOP on
-- RED-PROOF STAGE B: remove the oversold row (booking ACDEFHJK3, its seat row and its payment)
DELETE FROM booking_seat WHERE booking_id = (SELECT id FROM booking WHERE reference = 'ACDEFHJK3');
DELETE FROM booking WHERE reference = 'ACDEFHJK3';
DELETE FROM payment WHERE idempotency_key = 'redproof-key-b';
-- restore the guard exactly as schema.sql declares it
ALTER TABLE booking_seat ADD CONSTRAINT uq_booking_seat__showtime_id_seat_id UNIQUE (showtime_id, seat_id);
-- verify the restore
SELECT conname, pg_get_constraintdef(oid) AS definition
  FROM pg_constraint
 WHERE conrelid = 'booking_seat'::regclass AND conname = 'uq_booking_seat__showtime_id_seat_id';
SELECT indexrelid::regclass AS index, indisunique, indpred IS NULL AS total_no_where
  FROM pg_index WHERE indrelid = 'booking_seat'::regclass AND indisunique AND NOT indisprimary;
```
`refused_B2.sql`:
```sql
-- the same oversell attempted against the restored guard: must be refused
BEGIN;
INSERT INTO payment (state, amount_paise, idempotency_key, pending_at, authorized_at, captured_at)
     VALUES ('captured', 25000, 'redproof-key-b', '2026-10-18 10:00:00+00', '2026-10-18 10:00:01+00', '2026-10-18 10:00:02+00');
INSERT INTO booking (reference, user_id, showtime_id, payment_id, total_paise, status)
     VALUES ('ACDEFHJK3', (SELECT id FROM users WHERE email = 'redproof-b@example.invalid'), 1,
             (SELECT id FROM payment WHERE idempotency_key = 'redproof-key-b'), 25000, 'confirmed');
INSERT INTO booking_seat (booking_id, showtime_id, seat_id, price_paise, base_price_paise_applied, uplift_basis_points_applied, seat_category_id)
     VALUES ((SELECT id FROM booking WHERE reference = 'ACDEFHJK3'), 1, 1, 25000, 25000, 0,
             (SELECT id FROM seat_category WHERE name = 'Redproof Category'));
ROLLBACK;
SELECT count(*) AS booking_seat_rows_for_seat_1 FROM booking_seat WHERE showtime_id = 1 AND seat_id = 1;
```
`checks_C.sql`:
```sql
-- RED-PROOF of the two SRC-004 CHECKs, run AS frontrow_app (the role the API uses).
-- No ON_ERROR_STOP: every refused INSERT must show its own ERROR line.
SELECT current_user, system_user;
-- OPEN-SEATLABEL-01 (SRC-004 R-4): lower-case and padded labels are REFUSED (autocommit, one statement each)
INSERT INTO seat (screen_id, row_label, seat_number, grid_row, grid_col, seat_category_id)
     VALUES (1, 'c', 12, 3, 12, 1);
INSERT INTO seat (screen_id, row_label, seat_number, grid_row, grid_col, seat_category_id)
     VALUES (1, ' C', 12, 3, 12, 1);
-- the upper-case form is ACCEPTED, and so is the letter I (OPEN-SEATALPHA-01: I allowed); rolled back
BEGIN;
INSERT INTO seat (screen_id, row_label, seat_number, grid_row, grid_col, seat_category_id)
     VALUES (1, 'C', 12, 3, 12, 1);
INSERT INTO seat (screen_id, row_label, seat_number, grid_row, grid_col, seat_category_id)
     VALUES (1, 'I', 1, 9, 1, 1);
SELECT row_label, seat_number FROM seat WHERE screen_id = 1 ORDER BY row_label, seat_number;
ROLLBACK;
-- OPEN-REFCHAR-01 (SRC-004 R-5): a bad reference is REFUSED.  Each attempt needs a
-- payment row, inserted in the same transaction and rolled back with it.
BEGIN;
INSERT INTO payment (state, amount_paise, idempotency_key, pending_at, authorized_at, captured_at)
     VALUES ('captured', 25000, 'redproof-key-c', '2026-10-18 10:00:00+00', '2026-10-18 10:00:01+00', '2026-10-18 10:00:02+00');
SAVEPOINT s;
-- the old 8-character form, valid under P-TKT-01 before SRC-004: now one short
INSERT INTO booking (reference, user_id, showtime_id, payment_id, total_paise, status)
     VALUES ('ACDEFHJK', 1, 1, (SELECT max(id) FROM payment), 25000, 'confirmed');
ROLLBACK TO SAVEPOINT s;
-- 9 characters, but Z is one of the four SRC-004 R-5 removes
INSERT INTO booking (reference, user_id, showtime_id, payment_id, total_paise, status)
     VALUES ('ACDEFHJKZ', 1, 1, (SELECT max(id) FROM payment), 25000, 'confirmed');
ROLLBACK TO SAVEPOINT s;
-- lower case
INSERT INTO booking (reference, user_id, showtime_id, payment_id, total_paise, status)
     VALUES ('acdefhjk4', 1, 1, (SELECT max(id) FROM payment), 25000, 'confirmed');
ROLLBACK TO SAVEPOINT s;
-- the morning run's own fixture reference: O and 1 were never in the alphabet
INSERT INTO booking (reference, user_id, showtime_id, payment_id, total_paise, status)
     VALUES ('REDPROOFA1', 1, 1, (SELECT max(id) FROM payment), 25000, 'confirmed');
ROLLBACK TO SAVEPOINT s;
-- a valid 9-character reference is ACCEPTED
INSERT INTO booking (reference, user_id, showtime_id, payment_id, total_paise, status)
     VALUES ('2589ACDE7', 1, 1, (SELECT max(id) FROM payment), 25000, 'confirmed');
SELECT reference, length(reference) AS len FROM booking ORDER BY reference;
ROLLBACK;
SELECT (SELECT count(*) FROM seat) AS seats_after, (SELECT count(*) FROM booking) AS bookings_after,
       (SELECT count(*) FROM payment) AS payments_after;
```
`sabotage_D.sql`:
```sql
\set ON_ERROR_STOP on
-- RED-PROOF of verify_invariants O1, B1 and A4, as the superuser: drop both SRC-004
-- CHECKs and hand the app one privilege beyond the matrix.
ALTER TABLE seat DROP CONSTRAINT ck_seat__row_label_upper;
ALTER TABLE booking DROP CONSTRAINT ck_booking__reference_charset;
GRANT DELETE ON booking_seat TO frontrow_app;
```
`restore_D.sql`:
```sql
\set ON_ERROR_STOP on
-- restore exactly as schema.sql declares them, then verify the restore
REVOKE DELETE ON booking_seat FROM frontrow_app;
ALTER TABLE seat ADD CONSTRAINT ck_seat__row_label_upper CHECK (row_label = upper(btrim(row_label)));
ALTER TABLE booking ADD CONSTRAINT ck_booking__reference_charset CHECK (reference ~ '^[23456789ACDEFHJKMNPQRTVWXY]{9}$');
SELECT conrelid::regclass AS tbl, conname, pg_get_constraintdef(oid) AS definition, convalidated
  FROM pg_constraint WHERE conname IN ('ck_seat__row_label_upper', 'ck_booking__reference_charset') ORDER BY 1;
SELECT has_table_privilege('frontrow_app', 'booking_seat', 'DELETE') AS app_can_delete_booking_seat;
```
`cleanup.sql`:
```sql
\set ON_ERROR_STOP on
-- remove every fixture row, child to parent (every FK is ON DELETE RESTRICT)
DELETE FROM booking_seat; DELETE FROM booking; DELETE FROM payment; DELETE FROM showtime_seat;
DELETE FROM showtime; DELETE FROM movie; DELETE FROM language; DELETE FROM certification;
DELETE FROM seat; DELETE FROM seat_category; DELETE FROM screen; DELETE FROM cinema; DELETE FROM users;
DO $$ DECLARE t text; n bigint; total bigint := 0; BEGIN
  FOR t IN SELECT tablename FROM pg_tables WHERE schemaname = 'public' LOOP
    EXECUTE format('SELECT count(*) FROM %I', t) INTO n; total := total + n;
    IF n > 0 THEN RAISE NOTICE 'still has rows: % = %', t, n; END IF;
  END LOOP;
  RAISE NOTICE 'rows remaining across all % public tables: %', (SELECT count(*) FROM pg_tables WHERE schemaname='public'), total;
END $$;
```
`literal_bible.sql`:
```sql
-- the two Bible criteria fixed in this wave, run literally, as frontrow_app
SELECT indexdef FROM pg_indexes WHERE tablename='booking_seat' AND indexname <> 'booking_seat_pkey';
SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid = 'payment'::regclass AND conname = 'ck_payment__state';
```
`sabotage_E.sql`:
```sql
\set ON_ERROR_STOP on
-- RED-PROOF of O2 / O5 and of the information_schema vacuity, as the owner:
-- a plaintext token column on a table the app can no longer see, and no payload-keys CHECK.
ALTER TABLE password_reset_token ADD COLUMN token text;
REVOKE ALL ON password_reset_token FROM frontrow_app;
ALTER TABLE outbox_message DROP CONSTRAINT ck_outbox_message__payload_keys_exact;
```
`restore_E.sql`:
```sql
\set ON_ERROR_STOP on
ALTER TABLE password_reset_token DROP COLUMN token;
GRANT SELECT, INSERT, UPDATE ON password_reset_token TO frontrow_app;
ALTER TABLE outbox_message ADD CONSTRAINT ck_outbox_message__payload_keys_exact CHECK ((topic <> 'receipt.send' OR (payload ?& ARRAY['booking_id', 'dispatch_seq', 'message_version', 'request_id'] AND payload - 'booking_id' - 'dispatch_seq' - 'message_version' - 'request_id' = '{}'::jsonb)) AND (topic <> 'password_reset.send' OR (payload ?& ARRAY['message_version', 'request_id', 'reset_token_id', 'user_id'] AND payload - 'message_version' - 'request_id' - 'reset_token_id' - 'user_id' = '{}'::jsonb)));
SELECT conname, convalidated FROM pg_constraint WHERE conname = 'ck_outbox_message__payload_keys_exact';
SELECT count(*) AS token_columns FROM pg_attribute WHERE attrelid = 'password_reset_token'::regclass AND attname = 'token' AND NOT attisdropped;
```
`vacuity.sql`:
```sql
-- as frontrow_app: what information_schema shows of password_reset_token, versus pg_catalog
SELECT 'information_schema.columns' AS source, count(*) AS columns_visible FROM information_schema.columns WHERE table_schema='public' AND table_name='password_reset_token'
UNION ALL
SELECT 'pg_attribute', count(*) FROM pg_attribute WHERE attrelid='public.password_reset_token'::regclass AND attnum > 0 AND NOT attisdropped;
```

---

# Fix wave 2 — 2026-10-18

**Why.** `SRC-004 R-5` was updated: the reference is **7 random characters + 1 check character = 8**,
not 8 + 1 = 9, over `23456789ACDEFHJKMNPQRTVWXY` (26). The display form `FR-XXXX-XXXX` is unchanged.
Everything above this heading that shows `{9}` or a 9-character reference is the earlier reading and
is kept as history, not as the current schema.

**What changed.**
* `datamodel.json`: `ck_booking__reference_charset` → `reference ~ '^[23456789ACDEFHJKMNPQRTVWXY]{8}$'`;
  the column note and the seed gap now say 8 (7 + 1). Regenerated `schema.sql`, `TRACEABILITY.tsv`,
  `seed/expected_summary.json`, `fingerprints.json` by `generate.py` (none hand-edited).
* `consistency_check.py` `reserved-not-decided`: any CHECK on `booking` that mentions `reference`
  (not only a regex) must be the exact ruled one; a token-shaped column (name contains `token` or
  `plaintext`, other than `token_sha256` or a `*_id` key) fails on **any** table. Four new selftest
  probes: `char_length(reference)` CHECK, a `seat_hold` table, `booking.admitted_at`,
  `outbox_message.plaintext_token` — all watched RED.
* `verify_invariants.sql`: B1 expects `{8}`; **G3 now runs the S-PAY-09 query byte-identically**:
  `SELECT count(*), max(indexdef) FROM pg_indexes WHERE tablename = 'booking_seat' AND indexname <> 'booking_seat_pkey' AND indexdef LIKE 'CREATE UNIQUE INDEX %'`
  (PL/pgSQL `INTO n, def` follows it on the next line).
* Bible `S-PAY-09` AC carries that query and filter verbatim; `S-TKT-01`, `S-XCT-26` and four other
  rows now use the 26-character class; PRD `P-TKT-01` states the check character (`SRC-004 R-5`),
  regenerated `contract.json` and `FrontRow_PRD.md` through `generate_api.py`.

**Container.** `frontrow-pg16` was removed and recreated **bound to loopback only**:
`docker run -d --name frontrow-pg16 -e POSTGRES_PASSWORD=local -e POSTGRES_DB=frontrow -p 127.0.0.1:55432:5432 postgres:16-alpine`
→ `docker ps`: `frontrow-pg16 127.0.0.1:55432->5432/tcp`. No other container was touched.

## Gates

| Command | Result |
|---|---|
| `py generate.py --check` | PASS — 4 generated files match |
| `py generate.py --selftest` | PASS — 12 of 12 |
| `py consistency_check.py` | PASS — 15 of 15 rules |
| `py consistency_check.py --selftest` | 26 of 26 rules watched going red |
| `py tools/consistency_check.py` | PASS — 9 of 9 rules |
| `py "docs/03 PRD/api/generate_api.py" --all` | PASS — 0 checks failed |

## Live run, verbatim (`drive.sh` output)

Roles: `roles_local.sql` as superuser; `schema.sql` as `frontrow_owner`; `verify_invariants.sql` as
`frontrow_app`, scram over TCP to the container's own address. Fixtures are those of the first wave
(`fixture_A.sql`, `restore_B.sql`, `refused_B2.sql`, `cleanup.sql`, above) with the references
changed to `ACDEFHJK` / `ACDEFHJM`. The trailing character of each test reference stands in for a
check character; no check algorithm exists yet and the CHECK cannot see one.

```text
### step 0: engine, port binding, schema.sql digest
postgres (PostgreSQL) 16.15
11d9b59e98f143bdb56fdf1c79e7444a2348417f4805c82e61dd96c3f37698af *D:/Project/FrontRow/docs/06 DataModel/schema.sql
container eth0 address used for role logins: 172.17.0.2
### step 1: roles_local.sql as superuser
DO
ALTER ROLE
ALTER ROLE
ALTER ROLE
ALTER ROLE
DO
DO
GRANT
GRANT
REVOKE
REVOKE
exit=0
### step 2: schema.sql AS frontrow_owner (scram over TCP to 172.17.0.2)
frontrow_owner|f
exit=0
statement tally:
     24 GRANT
     22 CREATE TABLE
     19 CREATE INDEX
      1 COMMIT
      1 BEGIN
### step 3: verify_invariants.sql AS frontrow_app on the fresh schema
frontrow_app
exit=0
== LISTING 1: every money column and its type (GOAL_08 DoD: zero float money columns) ==
  table_name  |       column_name        | data_type 
--------------+--------------------------+-----------
 booking      | total_paise              | bigint
 booking_seat | base_price_paise_applied | bigint
 booking_seat | price_paise              | bigint
 payment      | amount_paise             | bigint
 showtime     | base_price_paise         | bigint
(5 rows)

== LISTING 2: any float / numeric / money column anywhere in public (must be empty) ==
 table_name | column_name | data_type 
------------+-------------+-----------
(0 rows)

== LISTING 3: S-XCT-07 verbatim shape - audit_log privileges held by frontrow_app ==
 privilege_type 
----------------
 INSERT
 SELECT
(2 rows)

== LISTING 4: the seat guarantee as the catalog stores it ==
               conname                |          definition           
--------------------------------------+-------------------------------
 booking_seat_pkey                    | PRIMARY KEY (id)
 uq_booking_seat__showtime_id_seat_id | UNIQUE (showtime_id, seat_id)
(2 rows)

== ASSERTIONS ==
NOTICE:  PASS G1  no (showtime_id, seat_id) pair is held by two booking_seat rows
NOTICE:  PASS G2  uq_booking_seat__showtime_id_seat_id = UNIQUE (showtime_id, seat_id)
NOTICE:  PASS G3  S-PAY-09: exactly 1 UNIQUE index on booking_seat besides the pkey, total: CREATE UNIQUE INDEX uq_booking_seat__showtime_id_seat_id ON public.booking_seat USING btree (showtime_id, seat_id)
NOTICE:  PASS G4  every booking_seat matches its booking's showtime and that showtime's inventory
NOTICE:  PASS P1  every booking points at a payment in state captured
NOTICE:  PASS P2  booking.payment_id is NOT NULL and a foreign key to payment
NOTICE:  PASS P3  payment has no booking_id column (S-PAY-05)
NOTICE:  PASS P4  S-PAY-11: ck_payment__state = CHECK ((state = ANY (ARRAY['pending'::text, 'authorized'::text, 'captured'::text, 'failed'::text])))
NOTICE:  PASS M1  zero real/double/numeric/money columns in schema public (152 columns read)
NOTICE:  PASS M2  every *_paise column is bigint (and at least the 5 known money columns exist)
NOTICE:  PASS M3  money columns on booking/booking_seat/payment are exactly booking.total_paise,booking_seat.base_price_paise_applied,booking_seat.price_paise,payment.amount_paise
NOTICE:  PASS M4  every booking.total_paise equals the sum of its seats' price_paise
NOTICE:  PASS M5  no booking holds more than 10 seats
NOTICE:  PASS M6  seat_category.uplift_basis_points and booking_seat.uplift_basis_points_applied are both bigint
NOTICE:  PASS I1  uq_idempotency_record__user_id_idempotency_key = UNIQUE (user_id, idempotency_key)
NOTICE:  PASS I2  no (user_id, idempotency_key) pair is stored twice
NOTICE:  PASS I3  payment.idempotency_key carries no unique index (S-PAY-15)
NOTICE:  PASS A1  frontrow_app on audit_log = INSERT,SELECT
NOTICE:  PASS A2  frontrow_app effectively can SELECT, INSERT and cannot UPDATE, DELETE, TRUNCATE audit_log
NOTICE:  PASS R1  both roles exist and neither is superuser / bypassrls / createrole / createdb
NOTICE:  PASS R2  every relation in public is owned by frontrow_owner (so frontrow_app owns none)
NOTICE:  PASS R3  frontrow_app cannot CREATE in schema public
NOTICE:  PASS R4  frontrow_app holds no TRUNCATE / REFERENCES / TRIGGER on any table
NOTICE:  PASS R5  frontrow_app is not a member of frontrow_owner
NOTICE:  PASS F1  every foreign key in public is ON DELETE RESTRICT
NOTICE:  PASS K1  every id column is bigint GENERATED ALWAYS AS IDENTITY
NOTICE:  PASS T1  zero timestamp-without-time-zone columns
NOTICE:  PASS B1  booking.reference is UNIQUE and ck_booking__reference_charset = CHECK ((reference ~ '^[23456789ACDEFHJKMNPQRTVWXY]{8}$'::text)) (SRC-004 R-5)
NOTICE:  PASS B2  booking.status and booking.cancelled_at exist; no row is cancelled or non-confirmed
NOTICE:  PASS O1  ck_seat__row_label_upper = CHECK ((row_label = upper(btrim(row_label)))) (OPEN-SEATLABEL-01, SRC-004 R-4)
NOTICE:  PASS O4  seat.row_label: text, no letter-banning CHECK, no normalising index (OPEN-SEATALPHA-01: I allowed)
NOTICE:  PASS O2  no plaintext-token column anywhere; token_sha256 only; claim / sent / used are three columns (SRC-004 R-3)
NOTICE:  PASS O5  ck_outbox_message__payload_keys_exact exists, is validated, is exhaustive for both topics and names no token key (SRC-004 R-3)
NOTICE:  PASS O3  no holds table and no admission/redemption column (OPEN-HOLDRECOVER-01, OPEN-DUPREF-01 unruled)
NOTICE:  PASS U1  users.role vocabulary is exactly customer, manager, admin
NOTICE:  PASS A3  frontrow_app holds every grant the derived matrix says the application needs
NOTICE:  PASS A4  frontrow_app holds no table privilege beyond the derived matrix, on all 22 tables
NOTICE:  verify_invariants: ALL ASSERTIONS PASSED
DO
### step 3b: S-PAY-09 literally, as frontrow_app
 count |                                                        max                                                         
-------+--------------------------------------------------------------------------------------------------------------------
     1 | CREATE UNIQUE INDEX uq_booking_seat__showtime_id_seat_id ON public.booking_seat USING btree (showtime_id, seat_id)
(1 row)

### step 4a: AS OWNER drop the guard and oversell one seat
  current_user  |         system_user          
----------------+------------------------------
 frontrow_owner | scram-sha-256:frontrow_owner
(1 row)

ALTER TABLE
DO
 reference | showtime_id | seat_id 
-----------+-------------+---------
 ACDEFHJK  |           1 |       1
 ACDEFHJM  |           1 |       1
(2 rows)

exit=0
### step 4a verify (app) - must be RED
exit=3
NOTICE:  FAIL G1  1 seat(s) SOLD TWICE: (showtime_id=1, seat_id=1) x2
NOTICE:  FAIL G2  guard constraint uq_booking_seat__showtime_id_seat_id is MISSING
NOTICE:  FAIL G3  S-PAY-09: 0 UNIQUE index(es) on booking_seat besides the pkey (want 1, on (showtime_id, seat_id), no WHERE); last = none
ERROR:  verify_invariants: 3 assertion(s) FAILED - see FAIL lines above
### step 4b: AS OWNER remove the oversold row, restore the guard, pg_get_constraintdef
DELETE 1
DELETE 1
DELETE 1
ALTER TABLE
               conname                |          definition           
--------------------------------------+-------------------------------
 uq_booking_seat__showtime_id_seat_id | UNIQUE (showtime_id, seat_id)
(1 row)

                index                 | indisunique | total_no_where 
--------------------------------------+-------------+----------------
 uq_booking_seat__showtime_id_seat_id | t           | t
(1 row)

exit=0
### step 4b': the same oversell against the restored guard
BEGIN
INSERT 0 1
INSERT 0 1
ERROR:  duplicate key value violates unique constraint "uq_booking_seat__showtime_id_seat_id"
DETAIL:  Key (showtime_id, seat_id)=(1, 1) already exists.
ROLLBACK
 booking_seat_rows_for_seat_1 
------------------------------
                            1
(1 row)

### step 4c: verify (app) with the surviving fixture booking - must be GREEN
exit=0
37
NOTICE:  PASS G1  no (showtime_id, seat_id) pair is held by two booking_seat rows
NOTICE:  PASS G2  uq_booking_seat__showtime_id_seat_id = UNIQUE (showtime_id, seat_id)
NOTICE:  PASS G3  S-PAY-09: exactly 1 UNIQUE index on booking_seat besides the pkey, total: CREATE UNIQUE INDEX uq_booking_seat__showtime_id_seat_id ON public.booking_seat USING btree (showtime_id, seat_id)
NOTICE:  PASS B1  booking.reference is UNIQUE and ck_booking__reference_charset = CHECK ((reference ~ '^[23456789ACDEFHJKMNPQRTVWXY]{8}$'::text)) (SRC-004 R-5)
NOTICE:  verify_invariants: ALL ASSERTIONS PASSED
### step 5: the reference CHECK, AS frontrow_app
 current_user |        system_user         
--------------+----------------------------
 frontrow_app | scram-sha-256:frontrow_app
(1 row)

BEGIN
INSERT 0 1
SAVEPOINT
ERROR:  new row for relation "booking" violates check constraint "ck_booking__reference_charset"
DETAIL:  Failing row contains (4, 2589ACDE7, 1, 1, 4, 25000, confirmed, null, 2026-10-18 05:47:52.478911+00).
ROLLBACK
ERROR:  new row for relation "booking" violates check constraint "ck_booking__reference_charset"
DETAIL:  Failing row contains (5, ACDEFHJZ, 1, 1, 4, 25000, confirmed, null, 2026-10-18 05:47:52.478911+00).
ROLLBACK
INSERT 0 1
 reference | len 
-----------+-----
 2589ACDE  |   8
 ACDEFHJK  |   8
(2 rows)

ROLLBACK
 bookings_after | payments_after 
----------------+----------------
              1 |              1
(1 row)

### step 6: cleanup (owner) then verify on the empty schema
NOTICE:  rows remaining across all 22 public tables: 0
exit=0
37
NOTICE:  verify_invariants: ALL ASSERTIONS PASSED
```

`refchar.sql`:
```sql
-- OPEN-REFCHAR-01 (SRC-004 R-5), run AS frontrow_app with the fixture booking present.
-- No ON_ERROR_STOP: every refused INSERT must show its own ERROR line.
SELECT current_user, system_user;
BEGIN;
INSERT INTO payment (state, amount_paise, idempotency_key, pending_at, authorized_at, captured_at)
     VALUES ('captured', 25000, 'redproof-key-c', '2026-10-18 10:00:00+00', '2026-10-18 10:00:01+00', '2026-10-18 10:00:02+00');
SAVEPOINT s;
-- 9 characters (the rejected 8 + 1 reading): REFUSED
INSERT INTO booking (reference, user_id, showtime_id, payment_id, total_paise, status)
     VALUES ('2589ACDE7', 1, 1, (SELECT max(id) FROM payment), 25000, 'confirmed');
ROLLBACK TO SAVEPOINT s;
-- 8 characters, but Z is one of the four SRC-004 R-5 removes: REFUSED
INSERT INTO booking (reference, user_id, showtime_id, payment_id, total_paise, status)
     VALUES ('ACDEFHJZ', 1, 1, (SELECT max(id) FROM payment), 25000, 'confirmed');
ROLLBACK TO SAVEPOINT s;
-- a valid 8-character reference: ACCEPTED (the CHECK cannot see the check character's arithmetic)
INSERT INTO booking (reference, user_id, showtime_id, payment_id, total_paise, status)
     VALUES ('2589ACDE', 1, 1, (SELECT max(id) FROM payment), 25000, 'confirmed');
SELECT reference, length(reference) AS len FROM booking ORDER BY reference;
ROLLBACK;
SELECT (SELECT count(*) FROM booking) AS bookings_after, (SELECT count(*) FROM payment) AS payments_after;
```

`literal_bible.sql`:
```sql
-- S-PAY-09's query, byte-identical to the AC and to verify_invariants G3, as frontrow_app
SELECT count(*), max(indexdef) FROM pg_indexes WHERE tablename = 'booking_seat' AND indexname <> 'booking_seat_pkey' AND indexdef LIKE 'CREATE UNIQUE INDEX %';
```

**Result.** Fresh schema: ALL ASSERTIONS PASSED. Guard dropped: 2 bookings for one seat, verify RED
(G1, G2, G3). Guard restored: `pg_get_constraintdef` = `UNIQUE (showtime_id, seat_id)`, total, the
same oversell refused with `duplicate key`, verify GREEN (37 PASS). `2589ACDE7` (9 characters) and
`ACDEFHJZ` (`Z`) refused by `ck_booking__reference_charset`; `2589ACDE` accepted, rolled back.
Cleanup left 0 rows across 22 tables; verify GREEN on the empty schema.

**Container state at close.** `frontrow-pg16` left running on `127.0.0.1:55432`, schema applied, zero
rows. Role passwords existed only inside the driver process.

**Not covered, on purpose.** The check character's arithmetic (code, not yet written); the
concurrency proof (Phase 4); anything in AWS — reasoned, not observed.
