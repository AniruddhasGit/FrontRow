"""Test-only: the REAL boot path (load_settings -> configure_logging -> create_app -> serve) plus one
slow route, so a test can have a request in flight when SIGTERM lands.

Never shipped: the runtime image does not contain tests/. The slow route exists nowhere else.
"""

from __future__ import annotations

import asyncio
import sys

from app.core.clock import SystemClock
from app.core.config import load_settings
from app.core.logging import configure_logging, new_request_id
from app.main import create_app
from app.server import serve


def build():
    settings = load_settings()
    clock = SystemClock()
    configure_logging(level=settings.LOG_LEVEL, service="api", instance_id=new_request_id(), now=clock.now)
    app = create_app(settings, clock=clock)

    @app.get("/_drain/slow")
    async def slow(seconds: float = 2.0):
        await asyncio.sleep(seconds)
        return {"slept": seconds}

    return settings, app


if __name__ == "__main__":
    settings, app = build()
    sys.exit(serve(settings, app))
