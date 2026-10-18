"""/health/live and /health/ready  -  ZONE B (SRC-002 §6.2.3, §7.4; PRD P-XCT-10, EP-XCT-01/02).

THEY BEHAVE DIFFERENTLY ON PURPOSE, because two different machines poll them and react differently:

  /health/live   the CONTAINER-LEVEL restart check (ECS task definition healthCheck, docker
                 HEALTHCHECK). Failing it gets the container KILLED AND RESTARTED.
  /health/ready  the LOAD BALANCER target group health check. Failing it takes this instance OUT OF
                 ROTATION, without restarting it, until it passes again.

Wire them the wrong way round and a 10-second database blip restarts every container (a recoverable
outage becomes a restart loop). That wiring is Zone C; docs/30 Deployment/ says which goes where.

Neither endpoint is authenticated and neither returns a version, hostname or connection string.
(The ready body will also report PAYMENT_PROVIDER from Phase 4, when that variable first exists.)
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter()


@router.get("/health/live")
async def live() -> dict[str, str]:
    # THIS HANDLER DELIBERATELY DOES NOTHING. No database query, no Redis command, no disk, no network.
    # It answers one question - is this process running and able to serve HTTP - and the fact that
    # it ran at all is the answer. Do NOT "improve" it by adding a dependency check: the restart
    # check polls this, so a liveness check that touches Postgres restarts every container whenever
    # Postgres blips, and a restart cannot fix Postgres.
    return {"status": "live"}


@router.get("/health/ready")
async def ready(request: Request) -> JSONResponse:
    # Postgres SELECT 1 + Redis PING, each on its own timeout, cached for READINESS_CACHE_TTL_SECONDS
    # (see app/core/readiness.py). 503 - not 500 - because 503 is what a load balancer reads as
    # "temporarily unable to serve"; the body names which dependency so the operator does not guess.
    result = await request.app.state.readiness.check()
    if result.ok:
        return JSONResponse({"status": "ready", "checks": result.checks}, status_code=200)
    return JSONResponse({"status": "not_ready", "checks": result.checks}, status_code=503)
