# P1 · Application Load Balancer, target groups, listener, health checks  (prep-queue row 3 · needed by Phase 1)

> Zone C specification (`SRC-002 §6.3.3`). What to build, not how. Every claim about AWS behaviour is
> **reasoned, not observed**.

## What to build

- One internet-facing **Application Load Balancer** across the two public subnets, in the load
  balancer security group.
- A **listener on port 80**. HTTPS waits on a domain (row 14, `OPEN-TLS-01` deferred), and until then
  this environment is never called production.
- **Two target groups**: one for the api (container port 8000), one for the frontend (8080).
- **Path routing on the listener**: `/api/*` to the api target group (from Phase 3 the frontend calls
  relative `/api/...` URLs on the same hostname), the default to the frontend. For Phase 1 you may also
  route `/health/*` to the api, so you can call both endpoints through the load balancer yourself. They
  are public by design and return nothing sensitive (PRD `P-XCT-10`). The target group's own health
  checks do not need a listener rule; they go straight to the target.

## What the application expects

| Target group | Health check path | Healthy | Unhealthy |
|---|---|---|---|
| **api** | **`/health/ready`** | 200: PostgreSQL `SELECT 1` and Redis `PING` both answered | **503** with a body naming which one failed |
| **frontend** | `/index.html` (or `/`) | 200 | anything else |

**Load balancer → `/health/ready`. Container restart check → `/health/live`.** If you swap them, the
load balancer keeps sending traffic to an instance that cannot reach its database, and the container
check restarts a healthy process every time the database blips. **This is the mistake the two
endpoints exist to prevent** (`SRC-002 §7.4`, `GOTCHAS.md`).

Measured locally (GOAL_14 gate):

| State | `/health/ready` | `/health/live` |
|---|---|---|
| both up | 200 `{"status":"ready","checks":{"postgres":"ok","redis":"ok"}}` | 200 |
| Redis stopped | 503 `redis: unreachable`, answered in 0.02 s | 200 |
| PostgreSQL stopped | 503 `postgres: unreachable`, answered in 1.0 s (the connect timeout) | 200 |
| both stopped | 503 naming both | 200, in 0.004 s |

**The readiness cache and the health check interval interact** (PRD `P-XCT-10`). The api reuses one
readiness result for `READINESS_CACHE_TTL_SECONDS` = 3 s. Your health check interval and unhealthy
threshold decide how fast an instance is removed:

```
worst case from outage to removal  =  READINESS_CACHE_TTL_SECONDS  +  (unhealthy threshold × interval)
required:  READINESS_CACHE_TTL_SECONDS  <  unhealthy threshold × interval
```

If the cache outlives the threshold window, the load balancer acts on stale answers. The health check
**timeout must be longer than ~1.0 s**, the slowest measured readiness answer, or a slow-but-correct
503 is read as a timeout instead.

**Deregistration delay** runs **before** ECS sends SIGTERM, so it is not inside the stop timeout
(`P1_TASK_DEFINITIONS.md` *What the application expects*). The stricter safe bound `ECS stop timeout > deregistration delay + 20`
still needs it below about 100 s, because the stop timeout is capped at about 120 s. Its 300 s default
fails that bound. *(reasoned, not observed)*

**Which check goes where, in one line:** the load balancer's target group health check calls
`/health/ready`; the container-level restart check calls `/health/live`. They are different on
purpose, and reversing them turns a recoverable outage into a restart loop: a database blip then fails
the restart check, every container is killed, and a restart cannot fix the database. *(reasoned, not observed)*

## Acceptance criteria

1. The api target group's health check path is exactly `/health/ready`, on the traffic port, with a
   success code of 200.
2. The frontend target group's health check path is a static file.
3. `http://<alb-dns>/` returns the Phase 1 page.
4. If `/health/*` is routed: `http://<alb-dns>/health/live` returns `{"status":"live"}` with an
   `x-request-id` header.
5. The api target's health matches reality: `healthy` with RDS and ElastiCache in place, or `unhealthy`
   with a 503 reason without them (index, "Read this before you start").
6. The interval, unhealthy threshold, timeout and deregistration delay are written in the prep queue,
   and they satisfy both inequalities above.

## Common mistakes

- **Pointing the api health check at `/health/live` to make it go green.** It will go green, and it will
  stay green while the database is unreachable, so the load balancer sends every customer to an
  instance that can only fail them.
- **Health check on the default path `/`.** The api has no `/` route. It answers 404 and is marked
  unhealthy for a reason that has nothing to do with its health.
- **Target group port 80.** The containers cannot listen on 80 (non-root). Health checks fail with
  connection refused while the container logs look perfectly healthy.
