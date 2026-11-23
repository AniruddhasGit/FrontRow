"""The demo crowd's bookings, all at once (owner, 2026-11-23): brings every published film's shows from the last
LOOKBACK_DAYS to the schedule's horizon up to their target share of seats sold for now, through the app's own
function (app/domain/demo_fill.py). Run it once after scripts/demo_reviews.py (which creates the crowd); after that the
listing's hourly schedule check keeps every show topped up as it approaches, with no job and no timer.

  DATABASE_URL=<owner url> [REDIS_URL=<redis url>] python scripts/demo_bookings.py

With REDIS_URL each seat is locked with the hold path's own lock before it is booked, so a seat a customer is holding
is skipped. Without it the UNIQUE (showtime_id, seat_id) alone guards: never a double sale, but a customer mid-checkout
on a seat this run took is told "someone took that seat". Run it when nobody is checking out, or give it REDIS_URL.

Idempotent: a show already at its target gets nothing; a second run straight after writes 0 seats.
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

for _root in (Path(__file__).resolve().parents[1] / "backend", Path(__file__).resolve().parents[1]):
    if (_root / "app").is_dir() and str(_root) not in sys.path:
        sys.path.insert(0, str(_root))

LOOKBACK_DAYS = 14  # shows that already happened get their final share too, so the reports have a history
HORIZON_DAYS = 22  # one past the demo's DEMO_SHOWTIMES_AHEAD_DAYS (21): every scheduled show


async def run(database_url: str, redis_url: str | None, now: datetime) -> int:
    from sqlalchemy.ext.asyncio import create_async_engine

    from app.db import async_url
    from app.domain import demo_fill

    engine = create_async_engine(async_url(database_url))
    redis = None
    if redis_url:
        from redis.asyncio import Redis
        redis = Redis.from_url(redis_url)
    try:
        async with engine.connect() as conn:
            seats = await demo_fill.fill(conn, redis, now, horizon_days=HORIZON_DAYS, since=timedelta(days=LOOKBACK_DAYS),
                                         cap=None)
    finally:
        await engine.dispose()
        if redis is not None:
            await redis.aclose()
    print(f"demo seats booked: {seats}")
    return seats


if __name__ == "__main__":
    asyncio.run(run(os.environ["DATABASE_URL"], os.environ.get("REDIS_URL") or None, datetime.now(timezone.utc)))
