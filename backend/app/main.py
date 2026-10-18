"""Application factory: middleware, error handlers, the database engine, and every router.

Every router module is registered HERE, once, so feature lanes add routes to their own module and
never edit this file. Each router carries its own authorisation dependency (app/api/deps.py).
NO MIGRATION RUNS FROM HERE, at import or in the lifespan (SRC-002 §7.8).
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine

from app.api import admin, auth, auth_session, browse, manager
from app.api.errors import install_error_handlers
from app.api.health import router as health_router
from app.core.clock import Clock, SystemClock
from app.core.config import Settings
from app.db import make_engine
from app.core.readiness import Probe, Readiness, postgres_probe, redis_probe
from app.core.request_context import RequestContextMiddleware

log = logging.getLogger("app.lifecycle")

ShutdownHook = tuple[str, Callable[[], Awaitable[None]]]


def _real_redis_client(settings: Settings):
    from redis.asyncio import Redis
    from redis.asyncio.retry import Retry
    from redis.backoff import NoBackoff

    return Redis.from_url(
        settings.REDIS_URL,
        # Without a connect timeout an unreachable node hangs the caller instead of failing fast.
        socket_connect_timeout=settings.REDIS_CONNECT_TIMEOUT_MS / 1000,
        # Without a command timeout a node that accepts the connection and never answers does the same.
        socket_timeout=settings.REDIS_COMMAND_TIMEOUT_MS / 1000,
        # redis-py retries by default. Without turning that off a PING against a dead node takes
        # (retries + 1) x timeout, and the "fail loudly" rule (SRC-002 §7.9) becomes "fail slowly".
        retry=Retry(NoBackoff(), 0),
        retry_on_timeout=False,
    )


def create_app(
    settings: Settings,
    clock: Clock | None = None,
    probes: list[Probe] | None = None,
    engine: AsyncEngine | None = None,
) -> FastAPI:
    clock = clock or SystemClock()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # The one Redis client of the process: the readiness probe and the request path (the rate
        # limiter, app/core/ratelimit.py) share it. Creating it opens no connection, so an unreachable
        # Redis never stops boot - the first command that needs it fails, and the limiter answers 503.
        redis_client = _real_redis_client(settings)
        app.state.redis = redis_client
        active_probes = probes
        if active_probes is None:
            active_probes = [
                postgres_probe(settings.DATABASE_URL, settings.DB_CONNECT_TIMEOUT_MS),
                # Connect + command: a probe on a fresh connection pays both, so a smaller bound would
                # report a healthy-but-cold Redis as unreachable.
                redis_probe(redis_client, settings.REDIS_CONNECT_TIMEOUT_MS + settings.REDIS_COMMAND_TIMEOUT_MS),
            ]
        # Without this, /health/ready raises AttributeError and answers 500 instead of 503.
        app.state.readiness = Readiness(active_probes, ttl_s=settings.READINESS_CACHE_TTL_SECONDS, clock=clock)
        # The request-path engine. Creating it opens no connection; the first query does. So an
        # unreachable or not-yet-migrated database never stops boot: /health/live stays 200 and the
        # first query that needs a missing column answers 500 (P-XCT-19 exception 1).
        owned_engine = engine is None
        app.state.db_engine = engine if engine is not None else make_engine(settings)
        # The resolved configuration, once, with NO secret values: the two URLs are omitted entirely.
        log.info(
            "api started",
            extra={
                "api_port": settings.API_PORT,
                "log_level": settings.LOG_LEVEL,
                "readiness_cache_ttl_seconds": settings.READINESS_CACHE_TTL_SECONDS,
                "shutdown_drain_timeout_seconds": settings.SHUTDOWN_DRAIN_TIMEOUT_SECONDS,
                "db_connect_timeout_ms": settings.DB_CONNECT_TIMEOUT_MS,
                "redis_connect_timeout_ms": settings.REDIS_CONNECT_TIMEOUT_MS,
                "redis_command_timeout_ms": settings.REDIS_COMMAND_TIMEOUT_MS,
            },
        )
        try:
            yield
        finally:
            # Reached AFTER uvicorn has stopped accepting and drained in-flight requests (or hit the
            # drain timeout). See app/server.py for the order.
            await _run_shutdown_hooks(app.state.shutdown_hooks)
            if redis_client is not None:
                # Last, because a Phase 4 hook releases locks THROUGH this client.
                await redis_client.aclose()
            if owned_engine:
                await app.state.db_engine.dispose()

    app = FastAPI(
        title="FrontRow API",
        lifespan=lifespan,
        # The interactive docs pages are off: a public, unauthenticated page listing every route is
        # not something a Phase 1 skeleton needs to publish to the internet.
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    # SHUTDOWN HOOKS (SRC-002 §7.5, PRD P-XCT-17). Each is (name, async callable), run in order after
    # the drain. Phase 1 has none: there are no locks yet. Phase 4 registers "release this instance's
    # seat holds" here. A failing hook is logged and does not stop the next one, because expiry - not
    # release - is the correctness guarantee.
    app.state.shutdown_hooks: list[ShutdownHook] = []
    # Read by app/api/deps.py: the dependencies take settings and the clock from here, so a test that
    # builds the app with a FakeClock moves every decision-bearing instant (sessions, audit rows).
    app.state.settings = settings
    app.state.clock = clock
    app.add_middleware(RequestContextMiddleware, clock=clock)
    install_error_handlers(app)
    app.include_router(health_router)
    # One line per router module, each with its own prefix and authorisation dependency (deps.py).
    for module in (browse, auth, auth_session, admin, manager):
        app.include_router(module.router)
    return app


async def _run_shutdown_hooks(hooks: list[ShutdownHook]) -> None:
    log.info("drain complete; running shutdown hooks", extra={"hook_count": len(hooks)})
    for name, hook in hooks:
        try:
            await hook()
        except Exception:  # noqa: BLE001
            log.error("shutdown hook failed", exc_info=True, extra={"hook": name})
    log.info("shutdown hooks complete")
