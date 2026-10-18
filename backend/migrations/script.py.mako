"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
"""

# LOCK: <name every table this revision touches, the lock it takes and roughly for how long> (P-XCT-19)

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = None
depends_on = None


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    raise NotImplementedError("no down-migrations: a bad migration is corrected by a new forward one (P-XCT-19 exception 5)")
