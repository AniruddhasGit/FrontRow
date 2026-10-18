-- ==========================================================================
-- verify_invariants.sql - runnable invariant checks for the FrontRow schema.
--
-- HAND-WRITTEN, NOT GENERATED.  Read-only: it issues SELECTs only, so it runs
-- as the APPLICATION role (frontrow_app) and creates nothing.
--
--   psql -v ON_ERROR_STOP=1 -U frontrow_app -d frontrow -f verify_invariants.sql
--
-- How it fails: every assertion is evaluated inside ONE DO block.  Each prints
-- "PASS <id>" or "FAIL <id> ..." as a NOTICE, then, if any failed, the block
-- raises an EXCEPTION, so psql exits non-zero (3 with ON_ERROR_STOP).  Every
-- check runs even when an earlier one fails, so one red run shows every
-- violation at once.
--
-- WHY pg_catalog AND NOT information_schema (fix wave 2026-10-18):
-- information_schema.columns / .tables / .table_privileges are PRIVILEGE-
-- FILTERED - they show only objects the CURRENT role holds some privilege on.
-- Run as frontrow_app, a column on a table the app cannot see is simply
-- absent, so a check of the form "no such column exists" passes VACUOUSLY.
-- pg_attribute / pg_class / pg_constraint / pg_namespace are not filtered, so
-- every structural check below reads them.  information_schema survives in
-- exactly two places, LISTING 3 and A1, because S-XCT-07 is written against
-- information_schema.table_privileges verbatim; A2 and A4 back them with
-- has_table_privilege, which is not filtered either.
--
-- Column and constraint names are the real ones from datamodel.json /
-- schema.sql.  The names asserted here are the names a change to datamodel.json
-- would have to keep or update in this file in the same commit.
-- ==========================================================================

\set ON_ERROR_STOP on
\pset footer on

\echo '== LISTING 1: every money column and its type (GOAL_08 DoD: zero float money columns) =='
SELECT c.relname AS table_name, a.attname AS column_name, format_type(a.atttypid, a.atttypmod) AS data_type
  FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid JOIN pg_namespace s ON s.oid = c.relnamespace
 WHERE s.nspname = 'public' AND c.relkind IN ('r', 'p') AND a.attnum > 0 AND NOT a.attisdropped
   AND (a.attname LIKE '%\_paise' ESCAPE '\' OR a.attname LIKE '%\_paise\_%' ESCAPE '\')
 ORDER BY 1, 2;

\echo '== LISTING 2: any float / numeric / money column anywhere in public (must be empty) =='
SELECT c.relname AS table_name, a.attname AS column_name, format_type(a.atttypid, a.atttypmod) AS data_type
  FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid JOIN pg_namespace s ON s.oid = c.relnamespace
 WHERE s.nspname = 'public' AND c.relkind IN ('r', 'p') AND a.attnum > 0 AND NOT a.attisdropped
   AND a.atttypid IN ('real'::regtype, 'double precision'::regtype, 'numeric'::regtype, 'money'::regtype)
 ORDER BY 1, 2;

\echo '== LISTING 3: S-XCT-07 verbatim shape - audit_log privileges held by frontrow_app =='
SELECT privilege_type
  FROM information_schema.table_privileges
 WHERE table_schema = 'public' AND table_name = 'audit_log' AND grantee = 'frontrow_app'
 ORDER BY privilege_type;

\echo '== LISTING 4: the seat guarantee as the catalog stores it =='
SELECT conname, pg_get_constraintdef(oid) AS definition
  FROM pg_constraint
 WHERE conrelid = 'public.booking_seat'::regclass AND contype IN ('u', 'p')
 ORDER BY conname;

\echo '== ASSERTIONS =='
-- Every column check below reads the same inlined subquery, aliased `cols`:
-- a live user column of an ordinary table in schema public, straight from
-- pg_attribute (unfiltered).  Inlined rather than a temp view, so the file
-- still creates nothing and needs no TEMP privilege.
DO $verify$
DECLARE
  failures  integer := 0;
  n         bigint;
  def       text;
  txt       text;

  -- The least-privilege matrix derived in roles_local.sql section 3.  Since
  -- the 2026-10-18 fix wave datamodel.json roles[].grants IS this matrix, so a
  -- grant beyond it is a FAILURE (A4), and a grant missing from it is too (A3).
  want CONSTANT jsonb := '{
    "audit_log":                 ["INSERT","SELECT"],
    "booking":                   ["INSERT","SELECT"],
    "booking_seat":              ["INSERT","SELECT"],
    "payment":                   ["INSERT","SELECT","UPDATE"],
    "idempotency_record":        ["INSERT","SELECT","UPDATE"],
    "users":                     ["INSERT","SELECT","UPDATE"],
    "password_reset_token":      ["INSERT","SELECT","UPDATE"],
    "outbox_message":            ["INSERT","SELECT","UPDATE"],
    "receipt_dispatch":          ["INSERT","SELECT","UPDATE"],
    "cinema":                    ["INSERT","SELECT","UPDATE"],
    "screen":                    ["INSERT","SELECT","UPDATE"],
    "seat":                      ["DELETE","INSERT","SELECT","UPDATE"],
    "seat_category":             ["INSERT","SELECT","UPDATE"],
    "movie":                     ["INSERT","SELECT","UPDATE"],
    "movie_genre":               ["DELETE","INSERT","SELECT"],
    "showtime":                  ["INSERT","SELECT","UPDATE"],
    "showtime_seat":             ["INSERT","SELECT"],
    "certification":             ["INSERT","SELECT","UPDATE"],
    "language":                  ["INSERT","SELECT","UPDATE"],
    "genre":                     ["INSERT","SELECT","UPDATE"],
    "format":                    ["INSERT","SELECT","UPDATE"],
    "manager_screen_assignment": ["DELETE","INSERT","SELECT"]
  }';
BEGIN

  ---------------------------------------------------------------------------
  -- G1  No two booking_seat rows hold the same (showtime_id, seat_id).
  --     SRC-001 §2.2, §7.1 "a seat is never sold twice"; FR-ADR-024; P-PAY-11.
  --     A DATA check: it goes red on an oversell even if the constraint is gone.
  ---------------------------------------------------------------------------
  SELECT count(*) INTO n FROM (
    SELECT showtime_id, seat_id FROM booking_seat
     GROUP BY showtime_id, seat_id HAVING count(*) > 1) d;
  IF n = 0 THEN RAISE NOTICE 'PASS G1  no (showtime_id, seat_id) pair is held by two booking_seat rows';
  ELSE failures := failures + 1;
       SELECT string_agg(format('(showtime_id=%s, seat_id=%s) x%s', showtime_id, seat_id, c), '; ')
         INTO txt FROM (SELECT showtime_id, seat_id, count(*) c FROM booking_seat
                         GROUP BY 1, 2 HAVING count(*) > 1) d;
       RAISE NOTICE 'FAIL G1  % seat(s) SOLD TWICE: %', n, txt;
  END IF;

  ---------------------------------------------------------------------------
  -- G2  The guard constraint exists, is named, and is TOTAL:
  --     pg_get_constraintdef = 'UNIQUE (showtime_id, seat_id)', no WHERE.
  --     datamodel.json seat_guarantee; S-XCT-02/03/04; AGENT_CONTRACT rule 2.
  ---------------------------------------------------------------------------
  SELECT pg_get_constraintdef(c.oid) INTO def
    FROM pg_constraint c
   WHERE c.conrelid = 'public.booking_seat'::regclass
     AND c.conname  = 'uq_booking_seat__showtime_id_seat_id'
     AND c.contype  = 'u';
  IF def = 'UNIQUE (showtime_id, seat_id)' THEN
       RAISE NOTICE 'PASS G2  uq_booking_seat__showtime_id_seat_id = %', def;
  ELSE failures := failures + 1;
       RAISE NOTICE 'FAIL G2  guard constraint uq_booking_seat__showtime_id_seat_id is %',
                    coalesce('wrong: ' || def, 'MISSING');
  END IF;

  ---------------------------------------------------------------------------
  -- G3  S-PAY-09, EXACTLY as the Bible states it (fix wave 2, 2026-10-18: the
  --     AC now carries the UNIQUE filter itself, so the query below is
  --     byte-identical to the one in the AC; INTO is PL/pgSQL and sits after it):
  --       SELECT count(*), max(indexdef) FROM pg_indexes WHERE tablename = 'booking_seat' AND indexname <> 'booking_seat_pkey' AND indexdef LIKE 'CREATE UNIQUE INDEX %'
  --     returns count 1, and that indexdef contains (showtime_id, seat_id)
  --     and does not contain ' WHERE '.
  --     pg_indexes is built on pg_index/pg_class and is not privilege-filtered.
  ---------------------------------------------------------------------------
  SELECT count(*), max(indexdef) FROM pg_indexes WHERE tablename = 'booking_seat' AND indexname <> 'booking_seat_pkey' AND indexdef LIKE 'CREATE UNIQUE INDEX %'
    INTO n, def;
  IF n = 1 AND def LIKE '%(showtime_id, seat_id)%' AND def NOT LIKE '% WHERE %' THEN
       RAISE NOTICE 'PASS G3  S-PAY-09: exactly 1 UNIQUE index on booking_seat besides the pkey, total: %', def;
  ELSE failures := failures + 1;
       RAISE NOTICE 'FAIL G3  S-PAY-09: % UNIQUE index(es) on booking_seat besides the pkey (want 1, on (showtime_id, seat_id), no WHERE); last = %',
                    n, coalesce(def, 'none');
  END IF;

  ---------------------------------------------------------------------------
  -- G4  Every booked seat is in its showtime's inventory and belongs to the
  --     booking's own showtime.  P-ADM-14 (showtime_seat is the per-showtime
  --     inventory written at creation); booking_seat.showtime_id duplicates
  --     booking.showtime_id so the guard can be one index - the two must agree.
  ---------------------------------------------------------------------------
  SELECT count(*) INTO n FROM booking_seat bs JOIN booking b ON b.id = bs.booking_id
   WHERE bs.showtime_id <> b.showtime_id
      OR NOT EXISTS (SELECT 1 FROM showtime_seat ss
                      WHERE ss.showtime_id = bs.showtime_id AND ss.seat_id = bs.seat_id);
  IF n = 0 THEN RAISE NOTICE 'PASS G4  every booking_seat matches its booking''s showtime and that showtime''s inventory';
  ELSE failures := failures + 1;
       RAISE NOTICE 'FAIL G4  % booking_seat row(s) outside their booking''s showtime or its showtime_seat inventory', n;
  END IF;

  ---------------------------------------------------------------------------
  -- P1  No confirmed booking without a payment in the terminal CAPTURED state.
  --     E3 P-PAY-01 "no state in which a booking exists without a captured
  --     payment".  Terminal payment states are captured and failed (P-PAY-07);
  --     a booking may only point at captured - stricter than "any terminal".
  ---------------------------------------------------------------------------
  SELECT count(*) INTO n FROM booking b JOIN payment p ON p.id = b.payment_id
   WHERE p.state <> 'captured';
  IF n = 0 THEN RAISE NOTICE 'PASS P1  every booking points at a payment in state captured';
  ELSE failures := failures + 1;
       RAISE NOTICE 'FAIL P1  % booking(s) point at a payment not in state captured (P-PAY-01)', n;
  END IF;

  SELECT count(*) INTO n FROM (SELECT c.relname AS table_name, a.attname AS column_name, a.atttypid, a.attnotnull, format_type(a.atttypid, a.atttypmod) AS data_type FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid JOIN pg_namespace s ON s.oid = c.relnamespace WHERE s.nspname = 'public' AND c.relkind IN ('r', 'p') AND a.attnum > 0 AND NOT a.attisdropped) cols
   WHERE table_name = 'booking' AND column_name = 'payment_id' AND attnotnull;
  IF n = 1 AND EXISTS (SELECT 1 FROM pg_constraint
                        WHERE conrelid = 'public.booking'::regclass AND contype = 'f'
                          AND confrelid = 'public.payment'::regclass) THEN
       RAISE NOTICE 'PASS P2  booking.payment_id is NOT NULL and a foreign key to payment';
  ELSE failures := failures + 1;
       RAISE NOTICE 'FAIL P2  booking.payment_id is nullable or has no foreign key to payment (P-PAY-07)';
  END IF;

  -- P3  payment carries no booking_id: the direction is booking -> payment.
  --     S-PAY-05; P-PAY-07 ("booking.payment_id points at payment.id, not the reverse").
  IF NOT EXISTS (SELECT 1 FROM (SELECT c.relname AS table_name, a.attname AS column_name, a.atttypid, a.attnotnull, format_type(a.atttypid, a.atttypmod) AS data_type FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid JOIN pg_namespace s ON s.oid = c.relnamespace WHERE s.nspname = 'public' AND c.relkind IN ('r', 'p') AND a.attnum > 0 AND NOT a.attisdropped) cols WHERE table_name = 'payment' AND column_name = 'booking_id')
     AND EXISTS (SELECT 1 FROM (SELECT c.relname AS table_name, a.attname AS column_name, a.atttypid, a.attnotnull, format_type(a.atttypid, a.atttypmod) AS data_type FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid JOIN pg_namespace s ON s.oid = c.relnamespace WHERE s.nspname = 'public' AND c.relkind IN ('r', 'p') AND a.attnum > 0 AND NOT a.attisdropped) cols WHERE table_name = 'payment' AND column_name = 'state') THEN
       RAISE NOTICE 'PASS P3  payment has no booking_id column (S-PAY-05)';
  ELSE failures := failures + 1;
       RAISE NOTICE 'FAIL P3  payment.booking_id exists, or payment is not visible at all (S-PAY-05)';
  END IF;

  -- P4  S-PAY-11 (fixed 2026-10-18): payment.state is text + CHECK, and the
  --     CHECK lists exactly the four states and no 'refunded'.
  SELECT pg_get_constraintdef(oid) INTO def FROM pg_constraint
   WHERE conrelid = 'public.payment'::regclass AND conname = 'ck_payment__state' AND contype = 'c';
  IF def = 'CHECK ((state = ANY (ARRAY[''pending''::text, ''authorized''::text, ''captured''::text, ''failed''::text])))' THEN
       RAISE NOTICE 'PASS P4  S-PAY-11: ck_payment__state = %', def;
  ELSE failures := failures + 1;
       RAISE NOTICE 'FAIL P4  S-PAY-11: ck_payment__state is %', coalesce(def, 'MISSING');
  END IF;

  ---------------------------------------------------------------------------
  -- M1  No column anywhere in public is real / double precision / numeric /
  --     money.  CLAUDE.md "Integer paise. Never a float"; AGENT_CONTRACT rule 4.
  -- M2  Every money column is EXACTLY bigint - integer is not enough
  --     (AGENT_CONTRACT rule 4 "Money is bigint in the minor unit").
  ---------------------------------------------------------------------------
  SELECT count(*) INTO n FROM (SELECT c.relname AS table_name, a.attname AS column_name, a.atttypid, a.attnotnull, format_type(a.atttypid, a.atttypmod) AS data_type FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid JOIN pg_namespace s ON s.oid = c.relnamespace WHERE s.nspname = 'public' AND c.relkind IN ('r', 'p') AND a.attnum > 0 AND NOT a.attisdropped) cols
   WHERE atttypid IN ('real'::regtype, 'double precision'::regtype, 'numeric'::regtype, 'money'::regtype);
  IF n = 0 AND (SELECT count(*) FROM (SELECT c.relname AS table_name, a.attname AS column_name, a.atttypid, a.attnotnull, format_type(a.atttypid, a.atttypmod) AS data_type FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid JOIN pg_namespace s ON s.oid = c.relnamespace WHERE s.nspname = 'public' AND c.relkind IN ('r', 'p') AND a.attnum > 0 AND NOT a.attisdropped) cols) > 100 THEN
       RAISE NOTICE 'PASS M1  zero real/double/numeric/money columns in schema public (% columns read)', (SELECT count(*) FROM (SELECT c.relname AS table_name, a.attname AS column_name, a.atttypid, a.attnotnull, format_type(a.atttypid, a.atttypmod) AS data_type FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid JOIN pg_namespace s ON s.oid = c.relnamespace WHERE s.nspname = 'public' AND c.relkind IN ('r', 'p') AND a.attnum > 0 AND NOT a.attisdropped) cols);
  ELSE failures := failures + 1;
       RAISE NOTICE 'FAIL M1  % float/numeric/money column(s) in public, or the catalog read too few columns', n;
  END IF;

  SELECT string_agg(table_name || '.' || column_name || ':' || data_type, ',') INTO txt FROM (SELECT c.relname AS table_name, a.attname AS column_name, a.atttypid, a.attnotnull, format_type(a.atttypid, a.atttypmod) AS data_type FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid JOIN pg_namespace s ON s.oid = c.relnamespace WHERE s.nspname = 'public' AND c.relkind IN ('r', 'p') AND a.attnum > 0 AND NOT a.attisdropped) cols
   WHERE (column_name LIKE '%\_paise' ESCAPE '\' OR column_name LIKE '%\_paise\_%' ESCAPE '\')
     AND atttypid <> 'bigint'::regtype;
  IF txt IS NULL AND (SELECT count(*) FROM (SELECT c.relname AS table_name, a.attname AS column_name, a.atttypid, a.attnotnull, format_type(a.atttypid, a.atttypmod) AS data_type FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid JOIN pg_namespace s ON s.oid = c.relnamespace WHERE s.nspname = 'public' AND c.relkind IN ('r', 'p') AND a.attnum > 0 AND NOT a.attisdropped) cols
                       WHERE column_name LIKE '%\_paise' ESCAPE '\' OR column_name LIKE '%\_paise\_%' ESCAPE '\') >= 5 THEN
       RAISE NOTICE 'PASS M2  every *_paise column is bigint (and at least the 5 known money columns exist)';
  ELSE failures := failures + 1;
       RAISE NOTICE 'FAIL M2  money column(s) not bigint: %, or fewer than 5 money columns found', coalesce(txt, 'none');
  END IF;

  -- M3  S-PAY-01: the money columns on booking / booking_seat / payment are
  --     EXACTLY total_paise, price_paise, base_price_paise_applied, amount_paise.
  SELECT string_agg(table_name || '.' || column_name, ',' ORDER BY table_name, column_name) INTO txt
    FROM (SELECT c.relname AS table_name, a.attname AS column_name, a.atttypid, a.attnotnull, format_type(a.atttypid, a.atttypmod) AS data_type FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid JOIN pg_namespace s ON s.oid = c.relnamespace WHERE s.nspname = 'public' AND c.relkind IN ('r', 'p') AND a.attnum > 0 AND NOT a.attisdropped) cols
   WHERE table_name IN ('booking', 'booking_seat', 'payment')
     AND (column_name LIKE '%\_paise' ESCAPE '\' OR column_name LIKE '%\_paise\_%' ESCAPE '\');
  IF txt = 'booking.total_paise,booking_seat.base_price_paise_applied,booking_seat.price_paise,payment.amount_paise' THEN
       RAISE NOTICE 'PASS M3  money columns on booking/booking_seat/payment are exactly %', txt;
  ELSE failures := failures + 1;
       RAISE NOTICE 'FAIL M3  money columns on booking/booking_seat/payment are % (S-PAY-01)', txt;
  END IF;

  -- M4  FR-ADR-039: booking.total_paise = SUM(booking_seat.price_paise).
  --     Asserted as a test, explicitly not as a constraint (datamodel.json).
  --     A booking with no seats at all also fails here.
  SELECT count(*) INTO n FROM booking b
   WHERE b.total_paise IS DISTINCT FROM (SELECT sum(bs.price_paise) FROM booking_seat bs WHERE bs.booking_id = b.id);
  IF n = 0 THEN RAISE NOTICE 'PASS M4  every booking.total_paise equals the sum of its seats'' price_paise';
  ELSE failures := failures + 1;
       RAISE NOTICE 'FAIL M4  % booking(s) whose total_paise is not the sum of their seats, or that have no seats', n;
  END IF;

  -- M5  Max 10 seats per booking (CLAUDE.md invariants; enforced server-side,
  --     checked here on the data that resulted).
  SELECT count(*) INTO n FROM (SELECT booking_id FROM booking_seat GROUP BY booking_id HAVING count(*) > 10) d;
  IF n = 0 THEN RAISE NOTICE 'PASS M5  no booking holds more than 10 seats';
  ELSE failures := failures + 1;
       RAISE NOTICE 'FAIL M5  % booking(s) hold more than 10 seats', n;
  END IF;

  -- M6  The uplift and its snapshot are both bigint (RUN_LOG F-4): S-ADM-13
  --     accepts 368934881464190, so a narrower snapshot cannot hold it.
  SELECT string_agg(table_name || '.' || column_name || ':' || data_type, ',' ORDER BY table_name) INTO txt
    FROM (SELECT c.relname AS table_name, a.attname AS column_name, a.atttypid, a.attnotnull, format_type(a.atttypid, a.atttypmod) AS data_type FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid JOIN pg_namespace s ON s.oid = c.relnamespace WHERE s.nspname = 'public' AND c.relkind IN ('r', 'p') AND a.attnum > 0 AND NOT a.attisdropped) cols
   WHERE (table_name, column_name) IN (('seat_category', 'uplift_basis_points'),
                                       ('booking_seat', 'uplift_basis_points_applied'));
  IF txt = 'booking_seat.uplift_basis_points_applied:bigint,seat_category.uplift_basis_points:bigint' THEN
       RAISE NOTICE 'PASS M6  seat_category.uplift_basis_points and booking_seat.uplift_basis_points_applied are both bigint';
  ELSE failures := failures + 1;
       RAISE NOTICE 'FAIL M6  uplift column types are % (both must be bigint)', coalesce(txt, 'MISSING');
  END IF;

  ---------------------------------------------------------------------------
  -- I1  The idempotency key is UNIQUE per user, TOTAL, on idempotency_record.
  --     FR-ADR-020; E3 P-PAY-09; GOTCHAS (two simultaneous retries must collide
  --     in the database).
  ---------------------------------------------------------------------------
  SELECT pg_get_constraintdef(c.oid) INTO def FROM pg_constraint c
   WHERE c.conrelid = 'public.idempotency_record'::regclass
     AND c.conname  = 'uq_idempotency_record__user_id_idempotency_key' AND c.contype = 'u';
  IF def = 'UNIQUE (user_id, idempotency_key)' THEN
       RAISE NOTICE 'PASS I1  uq_idempotency_record__user_id_idempotency_key = %', def;
  ELSE failures := failures + 1;
       RAISE NOTICE 'FAIL I1  idempotency unique constraint is %', coalesce('wrong: ' || def, 'MISSING');
  END IF;

  SELECT count(*) INTO n FROM (SELECT user_id, idempotency_key FROM idempotency_record
                                GROUP BY 1, 2 HAVING count(*) > 1) d;
  IF n = 0 THEN RAISE NOTICE 'PASS I2  no (user_id, idempotency_key) pair is stored twice';
  ELSE failures := failures + 1;
       RAISE NOTICE 'FAIL I2  % duplicated idempotency key(s)', n;
  END IF;

  -- I3  payment.idempotency_key is deliberately NOT unique (S-PAY-15: two
  --     failed attempts with one key leave two payment rows).  A unique index
  --     here would break the fail -> retry -> succeed drill.
  IF NOT EXISTS (SELECT 1 FROM pg_index i
                   JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY (i.indkey)
                  WHERE i.indrelid = 'public.payment'::regclass AND i.indisunique
                    AND a.attname = 'idempotency_key') THEN
       RAISE NOTICE 'PASS I3  payment.idempotency_key carries no unique index (S-PAY-15)';
  ELSE failures := failures + 1;
       RAISE NOTICE 'FAIL I3  payment.idempotency_key is unique - breaks S-PAY-15';
  END IF;

  ---------------------------------------------------------------------------
  -- A1  audit_log grants to frontrow_app are EXACTLY INSERT and SELECT.
  --     S-XCT-07 verbatim (information_schema.table_privileges); FR-ADR-019.
  ---------------------------------------------------------------------------
  SELECT string_agg(privilege_type, ',' ORDER BY privilege_type) INTO txt
    FROM information_schema.table_privileges
   WHERE table_schema = 'public' AND table_name = 'audit_log' AND grantee = 'frontrow_app';
  IF txt = 'INSERT,SELECT' THEN
       RAISE NOTICE 'PASS A1  frontrow_app on audit_log = %', txt;
  ELSE failures := failures + 1;
       RAISE NOTICE 'FAIL A1  frontrow_app on audit_log = % (S-XCT-07 requires exactly INSERT,SELECT)', coalesce(txt, 'NONE');
  END IF;

  -- A2  The same, by effective privilege (catches inheritance through a role
  --     membership, which table_privileges does not show).
  IF has_table_privilege('frontrow_app', 'public.audit_log', 'SELECT')
     AND has_table_privilege('frontrow_app', 'public.audit_log', 'INSERT')
     AND NOT has_table_privilege('frontrow_app', 'public.audit_log', 'UPDATE')
     AND NOT has_table_privilege('frontrow_app', 'public.audit_log', 'DELETE')
     AND NOT has_table_privilege('frontrow_app', 'public.audit_log', 'TRUNCATE') THEN
       RAISE NOTICE 'PASS A2  frontrow_app effectively can SELECT, INSERT and cannot UPDATE, DELETE, TRUNCATE audit_log';
  ELSE failures := failures + 1;
       RAISE NOTICE 'FAIL A2  frontrow_app effective privileges on audit_log are wrong (FR-ADR-019)';
  END IF;

  ---------------------------------------------------------------------------
  -- R1  Role shape.  frontrow_app is not a superuser, owns nothing, cannot
  --     create in public, holds no TRUNCATE / REFERENCES / TRIGGER anywhere;
  --     frontrow_owner owns every table and is not a superuser either.
  --     AGENT_CONTRACT "Two database roles"; GOAL_08 guardrail.
  ---------------------------------------------------------------------------
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname IN ('frontrow_app', 'frontrow_owner')
               AND (rolsuper OR rolbypassrls OR rolcreaterole OR rolcreatedb)) THEN
       failures := failures + 1;
       RAISE NOTICE 'FAIL R1  frontrow_app or frontrow_owner is superuser / bypassrls / createrole / createdb';
  ELSIF (SELECT count(*) FROM pg_roles WHERE rolname IN ('frontrow_app', 'frontrow_owner')) <> 2 THEN
       failures := failures + 1;
       RAISE NOTICE 'FAIL R1  frontrow_app and/or frontrow_owner do not exist';
  ELSE RAISE NOTICE 'PASS R1  both roles exist and neither is superuser / bypassrls / createrole / createdb';
  END IF;

  SELECT string_agg(c.relname, ',' ORDER BY c.relname) INTO txt
    FROM pg_class c JOIN pg_namespace s ON s.oid = c.relnamespace
   WHERE s.nspname = 'public' AND c.relkind IN ('r', 'p', 'S', 'v', 'm')
     AND pg_get_userbyid(c.relowner) <> 'frontrow_owner';
  IF txt IS NULL AND EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace s ON s.oid = c.relnamespace
                              WHERE s.nspname = 'public' AND c.relkind = 'r') THEN
       RAISE NOTICE 'PASS R2  every relation in public is owned by frontrow_owner (so frontrow_app owns none)';
  ELSE failures := failures + 1;
       RAISE NOTICE 'FAIL R2  relations not owned by frontrow_owner: %', coalesce(txt, '(no tables at all)');
  END IF;

  IF NOT has_schema_privilege('frontrow_app', 'public', 'CREATE') THEN
       RAISE NOTICE 'PASS R3  frontrow_app cannot CREATE in schema public';
  ELSE failures := failures + 1;
       RAISE NOTICE 'FAIL R3  frontrow_app can CREATE in schema public';
  END IF;

  -- R4  by effective privilege over every table pg_class lists (unfiltered).
  SELECT string_agg(c.relname || ':' || p.priv, ',' ORDER BY c.relname, p.priv) INTO txt
    FROM pg_class c JOIN pg_namespace s ON s.oid = c.relnamespace
    CROSS JOIN (VALUES ('TRUNCATE'), ('REFERENCES'), ('TRIGGER')) p(priv)
   WHERE s.nspname = 'public' AND c.relkind IN ('r', 'p')
     AND has_table_privilege('frontrow_app', c.oid, p.priv);
  IF txt IS NULL THEN RAISE NOTICE 'PASS R4  frontrow_app holds no TRUNCATE / REFERENCES / TRIGGER on any table';
  ELSE failures := failures + 1;
       RAISE NOTICE 'FAIL R4  frontrow_app holds %', txt;
  END IF;

  IF NOT pg_has_role('frontrow_app', 'frontrow_owner', 'MEMBER') THEN
       RAISE NOTICE 'PASS R5  frontrow_app is not a member of frontrow_owner';
  ELSE failures := failures + 1;
       RAISE NOTICE 'FAIL R5  frontrow_app is a member of frontrow_owner - it inherits owner privileges';
  END IF;

  ---------------------------------------------------------------------------
  -- F1  Every foreign key is ON DELETE RESTRICT.  AGENT_CONTRACT rule 7;
  --     S-XCT-09 (zero rows from pg_constraint where confdeltype <> 'r');
  --     S-ACC-10.
  ---------------------------------------------------------------------------
  SELECT string_agg(conname, ',') INTO txt FROM pg_constraint
   WHERE contype = 'f' AND connamespace = 'public'::regnamespace AND confdeltype <> 'r';
  IF txt IS NULL AND EXISTS (SELECT 1 FROM pg_constraint WHERE contype = 'f' AND connamespace = 'public'::regnamespace) THEN
       RAISE NOTICE 'PASS F1  every foreign key in public is ON DELETE RESTRICT';
  ELSE failures := failures + 1;
       RAISE NOTICE 'FAIL F1  foreign keys not ON DELETE RESTRICT: %', coalesce(txt, '(no foreign keys at all)');
  END IF;

  ---------------------------------------------------------------------------
  -- K1  Every "id" column is bigint GENERATED ALWAYS AS IDENTITY.
  --     FR-ADR-017; AGENT_CONTRACT rule 5.
  ---------------------------------------------------------------------------
  SELECT string_agg(c.relname, ',') INTO txt
    FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid
    JOIN pg_namespace s ON s.oid = c.relnamespace
   WHERE s.nspname = 'public' AND c.relkind = 'r' AND a.attname = 'id' AND NOT a.attisdropped
     AND (a.attidentity <> 'a' OR a.atttypid <> 'bigint'::regtype);
  IF txt IS NULL THEN RAISE NOTICE 'PASS K1  every id column is bigint GENERATED ALWAYS AS IDENTITY';
  ELSE failures := failures + 1;
       RAISE NOTICE 'FAIL K1  id columns not bigint GENERATED ALWAYS AS IDENTITY: %', txt;
  END IF;

  ---------------------------------------------------------------------------
  -- T1  No naive timestamp anywhere.  GOAL_08 "a showtime is an instant plus
  --     the cinema's zone, never a naive local timestamp"; FR-ADR-018.
  ---------------------------------------------------------------------------
  SELECT string_agg(table_name || '.' || column_name, ',') INTO txt FROM (SELECT c.relname AS table_name, a.attname AS column_name, a.atttypid, a.attnotnull, format_type(a.atttypid, a.atttypmod) AS data_type FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid JOIN pg_namespace s ON s.oid = c.relnamespace WHERE s.nspname = 'public' AND c.relkind IN ('r', 'p') AND a.attnum > 0 AND NOT a.attisdropped) cols
   WHERE atttypid = 'timestamp without time zone'::regtype;
  IF txt IS NULL AND EXISTS (SELECT 1 FROM (SELECT c.relname AS table_name, a.attname AS column_name, a.atttypid, a.attnotnull, format_type(a.atttypid, a.atttypmod) AS data_type FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid JOIN pg_namespace s ON s.oid = c.relnamespace WHERE s.nspname = 'public' AND c.relkind IN ('r', 'p') AND a.attnum > 0 AND NOT a.attisdropped) cols WHERE atttypid = 'timestamp with time zone'::regtype) THEN
       RAISE NOTICE 'PASS T1  zero timestamp-without-time-zone columns';
  ELSE failures := failures + 1;
       RAISE NOTICE 'FAIL T1  naive timestamp columns: %', coalesce(txt, '(no timestamptz column visible either)');
  END IF;

  ---------------------------------------------------------------------------
  -- B1  OPEN-REFCHAR-01, RULED by SRC-004 R-5: booking.reference is UNIQUE and
  --     its CHECK is exactly SRC-003 OPEN-TICKET-01's alphabet minus Z S B G,
  --     8 characters (7 random + one trailing check character).
  ---------------------------------------------------------------------------
  SELECT pg_get_constraintdef(oid) INTO def FROM pg_constraint
   WHERE conrelid = 'public.booking'::regclass AND conname = 'ck_booking__reference_charset' AND contype = 'c';
  IF def = 'CHECK ((reference ~ ''^[23456789ACDEFHJKMNPQRTVWXY]{8}$''::text))'
     AND (SELECT pg_get_constraintdef(oid) FROM pg_constraint
           WHERE conrelid = 'public.booking'::regclass AND conname = 'uq_booking__reference' AND contype = 'u')
         = 'UNIQUE (reference)' THEN
       RAISE NOTICE 'PASS B1  booking.reference is UNIQUE and ck_booking__reference_charset = % (SRC-004 R-5)', def;
  ELSE failures := failures + 1;
       RAISE NOTICE 'FAIL B1  booking.reference charset CHECK is % or its UNIQUE is missing (SRC-004 R-5)', coalesce(def, 'MISSING');
  END IF;

  -- B2  Excluded is not blocked (SRC-001 §6.6): booking.status and
  --     booking.cancelled_at exist; v1 writes only 'confirmed' and never sets
  --     cancelled_at (Bible: SELECT count(*) FROM booking WHERE cancelled_at IS
  --     NOT NULL returns 0; SELECT DISTINCT status returns one row).
  IF (SELECT count(*) FROM (SELECT c.relname AS table_name, a.attname AS column_name, a.atttypid, a.attnotnull, format_type(a.atttypid, a.atttypmod) AS data_type FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid JOIN pg_namespace s ON s.oid = c.relnamespace WHERE s.nspname = 'public' AND c.relkind IN ('r', 'p') AND a.attnum > 0 AND NOT a.attisdropped) cols
       WHERE table_name = 'booking' AND column_name IN ('status', 'cancelled_at')) = 2
     AND NOT EXISTS (SELECT 1 FROM booking WHERE cancelled_at IS NOT NULL OR status <> 'confirmed') THEN
       RAISE NOTICE 'PASS B2  booking.status and booking.cancelled_at exist; no row is cancelled or non-confirmed';
  ELSE failures := failures + 1;
       RAISE NOTICE 'FAIL B2  booking.status/cancelled_at missing, or a booking is cancelled / not confirmed (no v1 path writes that)';
  END IF;

  ---------------------------------------------------------------------------
  -- O1  OPEN-SEATLABEL-01, RULED by SRC-004 R-4: row_label is stored
  --     upper(trim(input)), enforced by ck_seat__row_label_upper.
  ---------------------------------------------------------------------------
  SELECT pg_get_constraintdef(oid) INTO def FROM pg_constraint
   WHERE conrelid = 'public.seat'::regclass AND conname = 'ck_seat__row_label_upper' AND contype = 'c';
  IF def = 'CHECK ((row_label = upper(btrim(row_label))))' THEN
       RAISE NOTICE 'PASS O1  ck_seat__row_label_upper = % (OPEN-SEATLABEL-01, SRC-004 R-4)', def;
  ELSE failures := failures + 1;
       RAISE NOTICE 'FAIL O1  ck_seat__row_label_upper is % (SRC-004 R-4)', coalesce(def, 'MISSING');
  END IF;

  -- O4  OPEN-SEATALPHA-01, RULED by SRC-004 R-4 as "I allowed": no OTHER CHECK
  --     touches row_label (so no letter is banned), no expression index
  --     re-normalises it, and the column is plain text.
  IF (SELECT data_type FROM (SELECT c.relname AS table_name, a.attname AS column_name, a.atttypid, a.attnotnull, format_type(a.atttypid, a.atttypmod) AS data_type FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid JOIN pg_namespace s ON s.oid = c.relnamespace WHERE s.nspname = 'public' AND c.relkind IN ('r', 'p') AND a.attnum > 0 AND NOT a.attisdropped) cols WHERE table_name = 'seat' AND column_name = 'row_label') = 'text'
     AND NOT EXISTS (SELECT 1 FROM pg_constraint c WHERE c.conrelid = 'public.seat'::regclass
                      AND c.contype = 'c' AND c.conname <> 'ck_seat__row_label_upper'
                      AND pg_get_constraintdef(c.oid) LIKE '%row_label%')
     AND NOT EXISTS (SELECT 1 FROM pg_index i WHERE i.indrelid = 'public.seat'::regclass
                      AND i.indexprs IS NOT NULL
                      AND pg_get_expr(i.indexprs, i.indrelid) LIKE '%row_label%') THEN
       RAISE NOTICE 'PASS O4  seat.row_label: text, no letter-banning CHECK, no normalising index (OPEN-SEATALPHA-01: I allowed)';
  ELSE failures := failures + 1;
       RAISE NOTICE 'FAIL O4  seat.row_label carries a CHECK or index beyond SRC-004 R-4 - bans a letter or re-normalises (OPEN-SEATALPHA-01)';
  END IF;

  ---------------------------------------------------------------------------
  -- O2  OPEN-RESETTOKEN-01, RULED by SRC-004 R-3: the plaintext token rides in
  --     the queue message only; the database keeps token_sha256.  NO column in
  --     ANY public table may be token-shaped except token_sha256, and the
  --     three worker columns stay three columns.
  ---------------------------------------------------------------------------
  SELECT string_agg(table_name || '.' || column_name, ',') INTO txt FROM (SELECT c.relname AS table_name, a.attname AS column_name, a.atttypid, a.attnotnull, format_type(a.atttypid, a.atttypmod) AS data_type FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid JOIN pg_namespace s ON s.oid = c.relnamespace WHERE s.nspname = 'public' AND c.relkind IN ('r', 'p') AND a.attnum > 0 AND NOT a.attisdropped) cols
   WHERE column_name LIKE '%token%' AND NOT (table_name = 'password_reset_token' AND column_name = 'token_sha256');
  IF txt IS NOT NULL THEN
       failures := failures + 1;
       RAISE NOTICE 'FAIL O2  token-shaped column(s) other than password_reset_token.token_sha256: % (SRC-004 R-3)', txt;
  ELSIF (SELECT count(*) FROM (SELECT c.relname AS table_name, a.attname AS column_name, a.atttypid, a.attnotnull, format_type(a.atttypid, a.atttypmod) AS data_type FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid JOIN pg_namespace s ON s.oid = c.relnamespace WHERE s.nspname = 'public' AND c.relkind IN ('r', 'p') AND a.attnum > 0 AND NOT a.attisdropped) cols
          WHERE table_name = 'password_reset_token'
            AND column_name IN ('token_sha256', 'email_claimed_at', 'email_sent_at', 'used_at')) <> 4 THEN
       failures := failures + 1;
       RAISE NOTICE 'FAIL O2  password_reset_token lacks token_sha256 or one of email_claimed_at / email_sent_at / used_at';
  ELSE RAISE NOTICE 'PASS O2  no plaintext-token column anywhere; token_sha256 only; claim / sent / used are three columns (SRC-004 R-3)';
  END IF;

  -- O5  SRC-004 R-3 "no database column - including any outbox_message payload
  --     - ever holds the plaintext".  The payload-keys CHECK is what makes the
  --     payload's key set EXHAUSTIVE per topic (the "= '{}'::jsonb" half), so
  --     a token key is refused at insert.  It must exist, be validated, and
  --     name no token key.
  SELECT pg_get_constraintdef(oid) INTO def FROM pg_constraint
   WHERE conrelid = 'public.outbox_message'::regclass AND conname = 'ck_outbox_message__payload_keys_exact'
     AND contype = 'c' AND convalidated;
  IF def LIKE '%''reset_token_id''%' AND def LIKE '%''password_reset.send''%'
     AND (length(def) - length(replace(def, '''{}''::jsonb', ''))) / length('''{}''::jsonb') = 2
     AND def NOT LIKE '%''token''%' AND def NOT LIKE '%''reset_token''%' AND def NOT LIKE '%plain%' THEN
       RAISE NOTICE 'PASS O5  ck_outbox_message__payload_keys_exact exists, is validated, is exhaustive for both topics and names no token key (SRC-004 R-3)';
  ELSE failures := failures + 1;
       RAISE NOTICE 'FAIL O5  outbox_message payload-keys CHECK is missing, unvalidated, not exhaustive, or admits a token key: %', coalesce(def, 'MISSING');
  END IF;

  -- O3  OPEN-HOLDRECOVER-01: no holds table.  OPEN-DUPREF-01: no admission /
  --     redemption / scan column anywhere.  (Both still unruled.)
  SELECT string_agg(name, ',') INTO txt FROM (
    SELECT c.relname AS name FROM pg_class c JOIN pg_namespace s ON s.oid = c.relnamespace
     WHERE s.nspname = 'public' AND c.relkind IN ('r', 'p', 'v', 'm') AND c.relname LIKE '%hold%'
    UNION ALL
    SELECT table_name || '.' || column_name FROM (SELECT c.relname AS table_name, a.attname AS column_name, a.atttypid, a.attnotnull, format_type(a.atttypid, a.atttypmod) AS data_type FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid JOIN pg_namespace s ON s.oid = c.relnamespace WHERE s.nspname = 'public' AND c.relkind IN ('r', 'p') AND a.attnum > 0 AND NOT a.attisdropped) cols
     WHERE column_name LIKE '%admit%' OR column_name LIKE '%redeem%' OR column_name LIKE '%redemption%'
        OR column_name LIKE '%scanned%' OR column_name LIKE '%checked_in%' OR column_name LIKE '%hold%') d;
  IF txt IS NULL THEN RAISE NOTICE 'PASS O3  no holds table and no admission/redemption column (OPEN-HOLDRECOVER-01, OPEN-DUPREF-01 unruled)';
  ELSE failures := failures + 1;
       RAISE NOTICE 'FAIL O3  found % - decides reserved OPEN-HOLDRECOVER-01 / OPEN-DUPREF-01', txt;
  END IF;

  ---------------------------------------------------------------------------
  -- U1  Four roles, three stored (SRC-003 C-1, PROVISIONAL): users.role is
  --     exactly customer / manager / admin; guest has no account and the
  --     cinema-staff role is gone (SRC-001 erratum E-1).
  ---------------------------------------------------------------------------
  SELECT pg_get_constraintdef(oid) INTO def FROM pg_constraint
   WHERE conrelid = 'public.users'::regclass AND conname = 'ck_users__role';
  IF def = 'CHECK ((role = ANY (ARRAY[''customer''::text, ''manager''::text, ''admin''::text])))' THEN
       RAISE NOTICE 'PASS U1  users.role vocabulary is exactly customer, manager, admin';
  ELSE failures := failures + 1;
       RAISE NOTICE 'FAIL U1  ck_users__role is %', coalesce(def, 'MISSING');
  END IF;

  ---------------------------------------------------------------------------
  -- A3 / A4  frontrow_app's effective table privileges EQUAL the derived
  --     least-privilege matrix (roles_local.sql section 3), read with
  --     has_table_privilege over every table pg_class lists - not filtered.
  --     A3: nothing the application needs is missing.  A4: nothing beyond it
  --     is held (was an ADVISORY until datamodel.json was narrowed, 2026-10-18).
  ---------------------------------------------------------------------------
  SELECT string_agg(format('%s:%s', t.key, p.value), ', ' ORDER BY t.key, p.value) INTO txt
    FROM jsonb_each(want) t, jsonb_array_elements_text(t.value) p
   WHERE NOT has_table_privilege('frontrow_app', 'public.' || t.key, p.value);
  IF txt IS NULL THEN RAISE NOTICE 'PASS A3  frontrow_app holds every grant the derived matrix says the application needs';
  ELSE failures := failures + 1;
       RAISE NOTICE 'FAIL A3  frontrow_app is MISSING grants the application needs: %', txt;
  END IF;

  SELECT string_agg(format('%s:%s', c.relname, p.priv), ', ' ORDER BY c.relname, p.priv) INTO txt
    FROM pg_class c JOIN pg_namespace s ON s.oid = c.relnamespace
    CROSS JOIN (VALUES ('SELECT'), ('INSERT'), ('UPDATE'), ('DELETE'), ('TRUNCATE'), ('REFERENCES'), ('TRIGGER')) p(priv)
   WHERE s.nspname = 'public' AND c.relkind IN ('r', 'p')
     AND has_table_privilege('frontrow_app', c.oid, p.priv)
     AND NOT coalesce((want -> c.relname::text) ? p.priv, false);
  IF txt IS NULL AND (SELECT count(*) FROM pg_class c JOIN pg_namespace s ON s.oid = c.relnamespace
                       -- alembic_version: the migration tool's own table, which exists only when the
                       -- schema arrived through `migrate` (observed on Neon, 2026-10-18). Owner-only.
                       WHERE s.nspname = 'public' AND c.relkind = 'r' AND c.relname <> 'alembic_version') = (SELECT count(*) FROM jsonb_object_keys(want)) THEN
       RAISE NOTICE 'PASS A4  frontrow_app holds no table privilege beyond the derived matrix, on all % tables', (SELECT count(*) FROM jsonb_object_keys(want));
  ELSE failures := failures + 1;
       RAISE NOTICE 'FAIL A4  frontrow_app holds privileges beyond the least-privilege matrix, or the table count differs from it: %', coalesce(txt, '(table count mismatch)');
  END IF;

  ---------------------------------------------------------------------------
  IF failures > 0 THEN
    RAISE EXCEPTION 'verify_invariants: % assertion(s) FAILED - see FAIL lines above', failures;
  END IF;
  RAISE NOTICE 'verify_invariants: ALL ASSERTIONS PASSED';
END
$verify$;
