"""Alembic environment: connect with DATABASE_URL, run the revisions, exit.

DATABASE_URL here must be the OWNER's connection string (frontrow_owner), never the application's
(frontrow_app): the owner creates and owns every table; the app role cannot create anything
(docs/06 DataModel/AGENT_CONTRACT.md "Two database roles"). The one-off migrate task therefore
overrides DATABASE_URL with the owner's - same variable name, different value (docs/30 Deployment/).

Online mode only. There is no offline (SQL script) mode and no autogenerate: the schema of record is
docs/06 DataModel/datamodel.json, and a revision is written from it, never inferred from the ORM.
"""

from __future__ import annotations

import os
import sys

from alembic import context
from sqlalchemy import create_engine, pool

url = os.environ.get("DATABASE_URL", "")
if not url:
    # Without this, SQLAlchemy raises an opaque "Could not parse URL" and the task log says nothing useful.
    sys.stderr.write("migrate: DATABASE_URL is required and is not set\n")
    sys.exit(78)
# psycopg 3 is the only installed driver; SQLAlchemy would otherwise look for psycopg2.
url = url.replace("postgresql://", "postgresql+psycopg://", 1).replace("postgres://", "postgresql+psycopg://", 1)

# NullPool: a one-off process opens one connection and exits; a pool would only delay the exit.
engine = create_engine(url, poolclass=pool.NullPool)
with engine.connect() as connection:
    # transaction_per_migration=False (the default): the whole upgrade is ONE transaction, so a
    # failure half way leaves the database exactly as it was, not half-migrated.
    context.configure(connection=connection, target_metadata=None)
    with context.begin_transaction():
        context.run_migrations()
engine.dispose()
