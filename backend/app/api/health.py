# =====================================================================================================
# /health/live and /health/ready  -  ZONE B (SRC-002 §6.2.3, §7.4; PRD P-XCT-10, EP-XCT-01/02).
#
# THEY BEHAVE DIFFERENTLY ON PURPOSE, because two different machines poll them and react differently:
#
#   /health/live   the CONTAINER-LEVEL restart check (ECS task definition healthCheck, docker
#                  HEALTHCHECK). Failing it gets the container KILLED AND RESTARTED.
#   /health/ready  the LOAD BALANCER target group health check. Failing it takes this instance OUT OF
#                  ROTATION, without restarting it, until it passes again.
#
# Wire them the wrong way round and a 10-second database blip restarts every container: a recoverable
# outage becomes a restart loop. That wiring is Zone C; docs/30 Deployment/ says which goes where.
#
# Neither endpoint is authenticated, and neither returns a version, a hostname or a connection string.
# PAYMENT_PROVIDER in the ready body is the one deliberate disclosure (EP-XCT-02).
# =====================================================================================================

# Postponed annotations, so the return types below are not evaluated at import.
from __future__ import annotations

# APIRouter: these routes sit on the PUBLIC router with no authorisation dependency, because a health
# check that needs a credential cannot be used by the load balancer or the container runtime.
from fastapi import APIRouter, Request
# JSONResponse lets /health/ready choose its status code (200 or 503) per call.
from fastapi.responses import JSONResponse

# The router app/main.py mounts. No prefix: the paths are /health/*, outside /api, as the contract says.
router = APIRouter()


# GET /health/live: is this process running and able to serve HTTP?
@router.get("/health/live")
# THIS HANDLER DELIBERATELY DOES NOTHING. No database query, no Redis command, no disk, no network.
# The fact that it ran at all is the answer. Do NOT "improve" it with a dependency check: the restart
# check polls this, so a liveness check that touches Postgres restarts every container whenever
# Postgres blips - a restart loop - and a restart cannot fix Postgres.
async def live() -> dict[str, str]:
    # The fixed body EP-XCT-01 publishes.
    return {"status": "live"}


# GET /health/ready: can this instance serve real traffic?
@router.get("/health/ready")
# Postgres SELECT 1 + Redis PING, each on its own timeout, cached for READINESS_CACHE_TTL_SECONDS
# (app/core/readiness.py). SES, SQS and S3 are NOT probed: the API serves almost every request without
# them, and probing them would take the site out of service for a failure it can absorb.
async def ready(request: Request) -> JSONResponse:
    # One cached probe run; a stampede of polls shares it.
    result = await request.app.state.readiness.check()
    # The body EP-XCT-02 publishes. payment_provider lets an operator see whether payments are real
    # without going through checkout; the body names which dependency failed, never how to reach it.
    body = {"status": "ready" if result.ok else "not_ready", "checks": result.checks, "payment_provider": request.app.state.settings.PAYMENT_PROVIDER}
    # 503, not 500: 503 is what a load balancer reads as "temporarily unable to serve".
    return JSONResponse(body, status_code=200 if result.ok else 503)
