"""created_at on the four tables 0001 created without it (S-XCT-09, E8 P-XCT-04 'Every table carries created_at').

Revision ID: 0002
Revises: 0001

WHERE THIS COMES FROM. docs/06 DataModel/datamodel.json gained one column on each of movie_genre,
receipt_dispatch, showtime and showtime_seat; schema.sql was regenerated from it. This revision is the
forward step that takes a database at 0001 to that schema. 0001 is never edited: a database that already
ran it would never see the change. backend/tests/xct/test_s_xct_04.py proves the migrated catalog equals
the catalog schema.sql produces, so this revision and the file of record cannot drift apart.

ADD COLUMN only. Nothing is dropped or altered, so the code running before this revision keeps working
against the new schema during the deploy window (it never names the new column).
"""

# LOCK: one ALTER TABLE per table, each taking an ACCESS EXCLUSIVE lock on that table for the time the
# statement takes. DEFAULT now() is not volatile, so PostgreSQL 11+ records the default once in the catalog
# and rewrites no rows: milliseconds per table even when full. Reads and writes on these four tables wait for
# that long; no other table is touched. Every existing row reads back the instant this revision ran.

from __future__ import annotations

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

TABLES = ("movie_genre", "receipt_dispatch", "showtime", "showtime_seat")


def upgrade() -> None:
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ADD COLUMN created_at timestamptz NOT NULL DEFAULT now()")


def downgrade() -> None:
    raise NotImplementedError("no down-migrations: a bad migration is corrected by a new forward one (P-XCT-19 exception 5)")
