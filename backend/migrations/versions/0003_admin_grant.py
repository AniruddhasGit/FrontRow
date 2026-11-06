"""admin_grant: the emails an admin has granted admin access to (SRC-008 ROLE-1 and its ADDENDUM, S-ADM-30).

Revision ID: 0003
Revises: 0002

WHERE THIS COMES FROM. docs/06 DataModel/datamodel.json gained the admin_grant table; schema.sql was regenerated
from it. The SQL below is that table, its index and its grant as schema.sql writes them, with the comments removed.
backend/tests/xct/test_s_xct_04.py proves the migrated catalog equals the catalog schema.sql produces.

CREATE only. Nothing existing is altered, so the code running before this revision keeps working during the deploy.
"""

# LOCK: creates one new, empty table. The foreign key takes a SHARE ROW EXCLUSIVE lock on users for the milliseconds
# the statement takes (it validates against an empty table), so sign-ins wait that long and nothing longer.

from __future__ import annotations

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
CREATE TABLE admin_grant (
    id                         bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
    email                      text NOT NULL,
    granted_by                 bigint NOT NULL,
    created_at                 timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (id),
    CONSTRAINT fk_admin_grant__granted_by FOREIGN KEY (granted_by) REFERENCES users (id) ON DELETE RESTRICT ON UPDATE RESTRICT
);
CREATE UNIQUE INDEX uq_admin_grant__email_ci ON admin_grant ((lower(email)));
GRANT SELECT, INSERT, DELETE ON admin_grant TO frontrow_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO frontrow_app;
""")


def downgrade() -> None:
    raise NotImplementedError("no down-migrations: a bad migration is corrected by a new forward one (P-XCT-19 exception 5)")
