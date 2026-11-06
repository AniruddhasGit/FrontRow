"""GET /metrics - EP-XCT-03 (P-XCT-13). Prometheus text format, on the container's port only.

NO LISTENER RULE MAY ROUTE THIS PATH (docs/30 Deployment/P7_METRICS.md): it has no authentication and discloses
traffic volumes and route names. The ALB forwards /api/* and /health/*; nothing else.

One scrape = exactly one Redis command (SCARD of this instance's hold registry, O(1)), one SELECT count(*), and at most
one SQS GetQueueAttributes per QueueDepth.CACHE_SECONDS. A gauge that cannot be read renders NaN: the scrape itself
never fails because a dependency is down - that is when an operator needs it most.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request, Response
from sqlalchemy import text

from app.core import metrics
from app.domain import holds

log = logging.getLogger("app.metrics")
router = APIRouter()


@router.get("/metrics", include_in_schema=False)
async def scrape(request: Request) -> Response:
    state = request.app.state
    gauges: dict[str, float | None] = {}
    try:
        # ponytail: this instance's hold-registry size, not P-XCT-13's counter - see the app/core/metrics.py docstring.
        gauges["seat_locks_held"] = float(await state.redis.scard(holds.registry_key(state.instance_id)))
    except Exception:  # noqa: BLE001 - Redis down: NaN, never a failed scrape
        gauges["seat_locks_held"] = None
    try:
        async with state.db_engine.connect() as conn:
            gauges["outbox_pending"] = float((await conn.execute(
                text("SELECT count(*) FROM outbox_message WHERE status = 'pending'"))).scalar_one())
    except Exception:  # noqa: BLE001 - PostgreSQL down: NaN
        gauges["outbox_pending"] = None
    age = None
    depth = getattr(state, "queue_depth", None)
    if depth is not None:
        gauges["queue_depth"], age = await depth.get()
    return Response(metrics.render(gauges, age).encode(), headers={"Content-Type": metrics.CONTENT_TYPE})
