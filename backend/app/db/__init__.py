"""The database connection layer: one async engine per process, one connection per request.

psycopg 3 in async mode (the same driver the readiness probe and the migrations use). The engine is
created in the app lifespan and disposed at shutdown (app/main.py); a request borrows one pooled
connection through the `db` dependency (app/api/deps.py) and returns it when the response is done.

Transactions are explicit: a handler that writes does `async with conn.begin():` and puts the change
AND its audit row inside it (P-XCT-03). Nothing here commits on its own.
"""

from __future__ import annotations

import math

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.core.config import Settings


def async_url(database_url: str) -> str:
    # The settings accept postgresql:// or postgres:// (the form RDS and Parameter Store hand out). SQLAlchemy needs
    # the driver named, or it looks for psycopg2, which is not installed.
    for prefix in ("postgresql://", "postgres://"):
        if database_url.startswith(prefix):
            return "postgresql+psycopg://" + database_url[len(prefix):]
    return database_url


def make_engine(settings: Settings) -> AsyncEngine:
    return create_async_engine(
        async_url(settings.DATABASE_URL),
        # db.t3.micro allows roughly 110 connections in total, and these two multiply across every
        # process (PRD S7.9). The defaults (5 + 10) were not chosen for that ceiling; these were.
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_POOL_MAX_OVERFLOW,
        # Without a connect timeout an unreachable database hangs the request instead of failing.
        # psycopg takes whole seconds.
        connect_args={
            "connect_timeout": max(1, math.ceil(settings.DB_CONNECT_TIMEOUT_MS / 1000)),
            # Server-side ceiling per statement. Without it one slow query holds a pooled connection
            # indefinitely and a handful exhaust the pool (S7.9 DB_STATEMENT_TIMEOUT_MS).
            "options": f"-c statement_timeout={settings.DB_STATEMENT_TIMEOUT_MS}",
        },
    )
