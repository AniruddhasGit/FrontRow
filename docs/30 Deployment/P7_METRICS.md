# P7 — `/metrics` on the api and on the worker (prep-queue row 28)

> **Zone C for the part that matters: the load balancer must not expose it.** The application side is built
> (`backend/app/api/metrics.py`, `backend/app/core/metrics.py`). Everything about AWS here is
> *(reasoned, not observed)*: no part of this has run in AWS.

## The gap, said first

**Nothing scrapes this endpoint, nothing stores its history and nothing alerts on it.** There is no Prometheus, no
Grafana, no CloudWatch agent reading it, and no alarm built on it (`P-XCT-13`). Adding any of those is a new managed
service and needs the client's permission first. What `/metrics` is good for today: an operator with a terminal on the
host, during an incident, reading the numbers *now*.

## What the application expects

| Process | Where | Port |
|---|---|---|
| api | `GET /metrics` on the container port | `API_PORT` (default 8000) — the same port the ALB forwards `/api/*` to |
| worker | `GET /metrics` on its own small listener | `WORKER_METRICS_PORT` (default 8001) — must differ from `API_PORT` and be 1024–65535, or the process exits at boot |

Prometheus text format (`Content-Type: text/plain; version=0.0.4`), exactly eight series:
`http_requests_total{route,method,status}`, `http_request_duration_seconds{route}`, `seat_locks_held`, `queue_depth`,
`seat_conflicts_total`, `booking_confirmations_total{outcome}`, `receipt_dispatch_total{outcome}`, `outbox_pending`.
While SQS cannot be read, `queue_depth` keeps its last value and `queue_depth_age_seconds` appears beside it.

Each process holds its **own** counters. The api runs **one** uvicorn worker per container, so one scrape is the whole
process; two api tasks are two scrapes, and the operator adds them up. A restarted container starts every counter at 0.

## What to build

**No load balancer listener rule may match /metrics.** The endpoint has no authentication. Routed through the ALB it
publishes, to anyone on the internet, request counts per route, error rates and the internal route names.

1. The ALB listener rules forward `/api/*` and `/health/*` to the api target group and everything else to the frontend
   target group (`P1_ALB.md`). Check that no rule — in particular no catch-all `/*` pointed at the api — matches
   `/metrics`. If one does, add a rule ahead of it that returns a fixed 404 for `/metrics`.
2. `WORKER_METRICS_PORT` gets **no** port mapping to the ALB and **no** security-group rule from the ALB. The worker
   service has no load balancer at all (`P5_SQS_QUEUE.md`).
3. To read it: `curl -s localhost:8000/metrics` from a shell on the EC2 host (the api's host port mapping), or
   `docker exec <worker> python -c "..."` for the worker's port, which is not mapped to the host.

## Acceptance criteria

- From outside: `curl -i https://<alb-dns>/metrics` returns 404 (or the frontend's page), never a body starting
  `# HELP http_requests_total`.
- From the host: `curl -s localhost:8000/metrics | grep '^# TYPE' | wc -l` prints 8.

## Common mistakes

- A single "forward everything to the api" listener rule. `/metrics` is then public, and nothing in the application
   can tell: the request arrives on the same port as every other.
- Mapping `WORKER_METRICS_PORT` to the host "to make it easier to read" and opening it in the security group. The
   worker then has an unauthenticated listener reachable from wherever that group allows.
