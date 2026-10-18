# backend/migrations/

Alembic, from **Phase 2** (`SRC-002 §12`). One revision so far: `versions/0001_initial_schema.py`,
which creates exactly what `docs/06 DataModel/schema.sql` creates (proved by
`backend/tests/xct/test_s_xct_04.py`, which diffs the two catalogs).

- **Run only by the entrypoint's `migrate` command**, as a one-off task, before the service is
  updated. **Never on boot** (`SRC-002 §7.8`). Nothing under `backend/app/` mentions Alembic.
- **Connect as the owner role** (`frontrow_owner`): the migrate task's `DATABASE_URL` is the owner's
  connection string, the API's is `frontrow_app`'s.
- **No downgrades.** Every `downgrade()` is a single `raise NotImplementedError`; a bad migration is
  fixed by a new forward one (`P-XCT-19`).
- **Every revision that touches `audit_log` or `booking_seat` carries a `# LOCK:` comment** naming
  what it locks and for roughly how long.
- **Never** `drop_column`, `drop_table`, `alter_column` or a dropped constraint: the old code runs
  against the new schema for the length of the deploy window.
- A schema change starts in `docs/06 DataModel/datamodel.json`, never here.

Locally: `docker compose --profile tools run --rm migrate`.
