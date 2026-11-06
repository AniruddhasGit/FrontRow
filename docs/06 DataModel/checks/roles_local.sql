-- ==========================================================================
-- roles_local.sql - LOCAL-DEVELOPMENT role bootstrap for the FrontRow schema.
--
-- HAND-WRITTEN, NOT GENERATED.  Run ONCE, AS A SUPERUSER, on an empty local
-- PostgreSQL 16 database, BEFORE schema.sql.  Then apply schema.sql AS
-- frontrow_owner (never as the superuser).
--
--   psql -v ON_ERROR_STOP=1 -v owner_password=... -v app_password=... \
--        -U postgres -d frontrow -f roles_local.sql
--
-- No password is written in this file.  Both are supplied on the command line
-- (psql -v), because a password checked into git is a secret in git, and
-- secrets are reserved (CONSTITUTION Art X, CLAUDE.md "Reserved").
--
-- WHAT THIS FILE DOES NOT DO, ON PURPOSE:
--   * It grants NO table privileges.  Those live in datamodel.json
--     roles[].grants and are emitted into schema.sql by generate.py, so local
--     and RDS get the same table grants from one source.  A second copy here
--     would drift from that file.
--   * It is not the RDS procedure.  On RDS the master user is not a real
--     superuser; the client creates these two users by hand (Zone C,
--     docs/30 Deployment/AWS_PREP_QUEUE.md row 20).  This file only shows the
--     SHAPE the application expects: two roles, neither superuser, the app not
--     the owner.
--
-- [JUDGMENT CALL] The role NAMES frontrow_owner / frontrow_app are a judgment
-- call (no document in the repository contains a CREATE ROLE, GRANT or
-- REVOKE - AGENT_CONTRACT.md "Two database roles").  Reversible.
-- The owner/app SPLIT is NOT a judgment call: S-XCT-07 requires
-- information_schema.table_privileges for audit_log and current_user to
-- return EXACTLY two rows (INSERT, SELECT).  A table's owner sees seven, so a
-- single-role design cannot pass that criterion (observed on PostgreSQL
-- 16.14, AGENT_CONTRACT.md).
-- ==========================================================================

\set ON_ERROR_STOP on

-- --------------------------------------------------------------------------
-- 1. The two roles.  Created if absent, then their attributes are forced, so
--    re-running this file still ends in the same state.  schema.sql creates
--    NO role (fix wave 2026-10-18): roles belong to the operator, so this file
--    must run BEFORE schema.sql, whose GRANTs fail if a role is absent.
-- --------------------------------------------------------------------------
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'frontrow_owner') THEN
    CREATE ROLE frontrow_owner;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'frontrow_app') THEN
    CREATE ROLE frontrow_app;
  END IF;
END $$;

-- frontrow_owner: owns every table, runs DDL and migrations (AGENT_CONTRACT
-- "Two database roles"; SRC-002 §7.8 migrations are a separate step, never on
-- boot).  NOT a superuser: GOTCHAS / GOAL_08 guardrail "Local Postgres gives
-- you superuser and RDS never will" - building as a superuser hides every
-- privilege the migration role would lack on RDS.
-- NOCREATEROLE: the owner never creates a role.  Roles are created by the
-- operator (this file locally, the client on RDS), not by a migration.
ALTER ROLE frontrow_owner WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS INHERIT;

-- frontrow_app: what the API and worker connect as.  Never superuser, never the
-- owner, never able to create anything (S-XCT-07; FR-ADR-019 audit is
-- append-only at the role level).  NOINHERIT and no membership in the owner:
-- if frontrow_app were a member of frontrow_owner it would inherit the seven
-- owner privileges on audit_log and S-XCT-07 would fail.
ALTER ROLE frontrow_app WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT;

ALTER ROLE frontrow_owner PASSWORD :'owner_password';
ALTER ROLE frontrow_app   PASSWORD :'app_password';

-- Guard: the app must not be a member of the owner, in either direction that
-- would leak privileges.
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_auth_members m
              JOIN pg_roles r ON r.oid = m.roleid
              JOIN pg_roles u ON u.oid = m.member
             WHERE (r.rolname = 'frontrow_owner' AND u.rolname = 'frontrow_app')) THEN
    RAISE EXCEPTION 'frontrow_app is a member of frontrow_owner - it would inherit owner privileges (S-XCT-07)';
  END IF;
END $$;

-- --------------------------------------------------------------------------
-- 2. Database and schema privileges - the ONLY privileges this file grants.
-- --------------------------------------------------------------------------
-- Both roles must be able to connect.  current_database() keeps the file
-- independent of the database name.
DO $$
BEGIN
  EXECUTE format('GRANT CONNECT ON DATABASE %I TO frontrow_owner, frontrow_app', current_database());
END $$;

-- The owner creates the tables, so it needs CREATE on schema public (PostgreSQL
-- 15+ no longer grants CREATE on public to PUBLIC).  WITH GRANT OPTION on
-- USAGE because schema.sql, run as the owner, issues
-- "GRANT USAGE ON SCHEMA public TO frontrow_app"; without the grant option
-- that statement only WARNS "no privileges were granted" and the app's schema
-- access would depend on this file instead of on schema.sql.
-- [JUDGMENT CALL] chosen over making frontrow_owner the DATABASE owner, which
-- would also work but hands the migration role database-level powers
-- (ALTER DATABASE, dropping the database) it never needs.
GRANT USAGE, CREATE ON SCHEMA public TO frontrow_owner;
GRANT USAGE ON SCHEMA public TO frontrow_owner WITH GRANT OPTION;

-- The app gets NO CREATE on public: it may not create tables (Zone B
-- "containers are stateless"; migrations are the owner's job, SRC-002 §7.8).
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
REVOKE CREATE ON SCHEMA public FROM frontrow_app;

-- --------------------------------------------------------------------------
-- 3. The least-privilege TABLE matrix, DERIVED FROM THE DOCUMENTS.
--
--    RECORDED HERE, NOT APPLIED HERE.  The applied grants come from
--    datamodel.json roles[].grants via schema.sql, which since the 2026-10-18
--    fix wave carries exactly this matrix.  verify_invariants.sql A3 fails on
--    a missing grant and A4 on any excess one, so the two cannot drift.
--
--    S = SELECT  I = INSERT  U = UPDATE  D = DELETE
--
--    audit_log                 S I       S-XCT-07 (exactly INSERT, SELECT); FR-ADR-019; E8 S7.11
--    booking                   S I       Bible row for booking.status: "status is written only by the
--                                        confirm insert ... rg 'UPDATE booking SET' returns 0 hits";
--                                        S-XCT-09 rg 'DELETE FROM (booking|...)' returns 0 hits;
--                                        SRC-003: no customer cancellation and no refunds
--    booking_seat              S I       FR-ADR-039 (price snapshot written once); S-XCT-09 (no DELETE)
--    payment                   S I U     E3 P-PAY-07 / FR-ADR-041 state moves pending->authorized->captured|failed;
--                                        S-XCT-09 (no DELETE)
--    idempotency_record        S I U     E3 P-PAY-09 happy path step 2 (insert in_progress) and step 4
--                                        ("the row is updated to completed")
--    users                     S I U     E5: "UPDATE users SET last_signed_in_at", "UPDATE users SET password_hash";
--                                        S-XCT-09 (no DELETE FROM users); S-ACC-10 (RESTRICT, never deleted)
--    password_reset_token      S I U     P-ACC-07 three-column claim / sent / used mechanics
--    outbox_message            S I U     FR-ADR-031 status pending -> sent
--    receipt_dispatch          S I U     E4 P-TKT-04/05 "UPDATE receipt_dispatch SET status='sending' ..."
--    cinema                    S I U     audit actions cinema.updated, cinema.timezone_changed (E6);
--                                        INSERT only for the seed's one cinema row (P-XCT-30) - WHICH
--                                        ROLE THE SEED CONNECTS AS IS UNSOURCED; if it is the owner,
--                                        INSERT can go
--    screen                    S I U     screen.created / updated / deactivated / reactivated; FR-ADR-012
--                                        (withdrawal replaces deletion)
--    seat                      S I U D   seat.created / updated / deleted / deactivated; EP-ADM-21 and
--                                        S-XCT-09 ("exactly two entities are ever removed ... a seat")
--    seat_category             S I U     seat_category.created / updated / uplift_changed
--    movie                     S I U     movie.created / updated / published ...; S-XCT-09 (no DELETE FROM movie)
--    movie_genre               S I D     EP-ADM-02 / EP-ADM-04 genre_ids (optional on edit) - replacing a
--                                        film's genre set removes join rows.  [JUDGMENT CALL] and IN
--                                        TENSION with S-XCT-09 "exactly two entities are ever removed";
--                                        a join row is read here as not an entity.  Flagged, not decided.
--    showtime                  S I U     showtime.created / updated / base_price_changed; S-XCT-09 (no DELETE)
--    showtime_seat             S I       P-ADM-14 INSERT INTO showtime_seat at showtime creation; the
--                                        inventory is frozen afterwards
--    certification, language,  S I U     <vocab>.created / withdrawn / restored (E6 audit table);
--    genre, format                       FR-ADR-012 / P-ADM-24 withdrawal is is_active=false, not DELETE
--    manager_screen_assignment S I D     EP-ADM-24 replaces the whole set; S-XCT-09 ("... and a
--                                        manager_screen_assignment row")
--    admin_grant               S I D     SRC-008 ROLE-1 ADDENDUM, S-ADM-30: an admin adds a granted email and
--                                        removing one deletes that grant row
--
--    No table:  TRUNCATE, REFERENCES, TRIGGER - nothing in the product needs
--    them, and TRUNCATE on audit_log would defeat FR-ADR-019 outright.
-- ==========================================================================
