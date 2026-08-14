# `/metrics` in Prometheus format, with nothing in the approved stack to scrape it

```
ADR id ............ FR-ADR-057
Pack .............. PACK-OPS
Decision type ..... JUDGMENT_CALL
Decision owner .... build session
Decision status ... APPROVED
Decision outcome .. ADOPTED
Decided by ........ build session (Art III.9)
Decision date ..... 2026-08-14
Source ............ SRC-002 §7.7; SRC-002 §5.3; SRC-002 §4.12; SRC-002 §5.2.6; SRC-002 §12.8; SRC-001 §8.2
Constitution ...... frontrow-constitution@0.1.0
```

## Context

`SRC-002 §7.7` requires a `/metrics` endpoint in Prometheus format, exposing request counts, latency,
seat lock counts and queue depth. It is a Phase 7 deliverable (`§12.8`).

The sweep found something the clause does not address, and it is worth naming plainly rather than
building around: **nothing in the approved stack scrapes Prometheus metrics.** Managed Grafana is
forbidden (`§5.3`), OpenSearch is forbidden, no Prometheus server is on the approved list, and
`§4.12` requires the client's permission before any managed service outside `§4` enters the design.

So the endpoint is required and its consumer does not exist. Art VII.8 requires that to be said rather
than absorbed.

## Decision

**Build the endpoint exactly as `§7.7` specifies.** It is a client requirement and a learning
deliverable. The absence of a scraper does not make it optional.

**Metrics exposed:**

| Metric | Type | Why |
|---|---|---|
| `http_requests_total{route,method,status}` | counter | `§7.7` request counts |
| `http_request_duration_seconds{route}` | histogram | `§7.7` latency |
| `seat_locks_held` | gauge | `§7.7` seat lock counts |
| `queue_depth` | gauge | `§7.7` queue depth |
| `seat_conflicts_total` | counter | how often the guard fires (`FR-ADR-029`) |
| `booking_confirmations_total{outcome}` | counter | |
| `receipt_dispatch_total{outcome}` | counter | the failure `FR-ADR-049` is about |
| `outbox_pending` | gauge | a rising value means the relay is stuck (`FR-ADR-031`) |

**`seat_locks_held` is not read by scanning Redis.** A `SCAN` across every lock key on every scrape is
work proportional to the lock count at an interval the endpoint does not control, and
`GOTCHAS.md`-style reasoning applies: a metric that costs more under load than the traffic it measures
is a metric that makes an outage worse. **The value comes from a Redis counter maintained by the
acquire and release paths**, which is O(1) per operation. It can drift when a lock expires without a
release, so it is reconciled by a bounded `SCAN` on the worker's existing loop at a long interval —
using the loop that already exists (`FR-ADR-031`) rather than a schedule, which there is none of.

**`queue_depth` comes from SQS's `ApproximateNumberOfMessages`**, cached for the scrape interval so a
scrape does not become an AWS API call each time. It is the number that would reveal a wedged worker
(`FR-ADR-055`).

**`/metrics` is not exposed through the ALB.** It is served on the container's port and reachable from
the host, not routed by any ALB listener rule. It discloses traffic volumes and internal route names
and there is no authentication in front of it. **Restricting the route is Zone C** — the client writes
the listener rules — so the specification in `docs/30 Deployment/` must say that no rule routes
`/metrics`, and say what is disclosed if one does.

**The worker exposes its own `/metrics` on a small HTTP listener.** Without it, worker-side counters —
receipt dispatch outcomes, outbox depth — have nowhere to go, and those are the ones that matter most
for the failure this product is most exposed to.

**Multiple uvicorn workers in one container would each hold their own counters**, so a scrape would
return one worker's view. **The API therefore runs a single uvicorn worker per container**, which is
also what the roughly 200 MB memory budget suggests (`FR-ADR-064`). If that ever changes, a
multiprocess metrics collector is required, and this record is where that dependency is noted.

### The gap, stated

**Nothing scrapes this endpoint. Nothing stores its history. Nothing alerts on it.** The one ruled
alarm is CloudWatch on running-task-count below 1 (`OPEN-OPS-01`, `FR-ADR-068`), which uses a
different mechanism entirely and does not read `/metrics`.

**What the endpoint is actually good for today:** an operator with a terminal can `curl` it during an
incident and see the numbers now. Against `SRC-001 §8.2` — observable and recoverable by one person —
that is genuinely useful and it is much less than monitoring.

**What is not done about it.** Adding Prometheus, Grafana Cloud, or the CloudWatch agent's Prometheus
scrape is a new managed service or a new dependency, and `§4.12` and `§13.1` require the client's
permission. **It is not added, and it is not designed around.** It is raised so the client can decide
whether they want it, and the runbook (`§12.8`) says explicitly that the endpoint exists and that
nothing is watching it.

## Alternatives rejected

**Skip the endpoint because nothing consumes it.** Rejected. `§7.7` requires it and `§1.3` makes it a
learning deliverable — wiring a scraper to it is a natural next exercise for the client.

**Emit CloudWatch custom metrics instead.** Rejected. `§7.7` says Prometheus format specifically, and
CloudWatch custom metrics are charged per metric per month against a zero budget.

**Scan Redis for `seat_locks_held`.** Rejected above.

**Expose `/metrics` through the ALB for convenience.** Rejected on disclosure.

**Run multiple uvicorn workers and accept per-worker metrics.** Rejected. A gauge that reports one
worker's view is a wrong number, which is worse than no number.

**Add Prometheus to `docker-compose.yml` so metrics work locally.** Rejected under `§13.1` for now,
and recorded as a reasonable thing for the client to say yes to.

## Source

`SRC-002 §7.7` (the endpoint and its four metrics) · `§5.3` (Managed Grafana and OpenSearch
forbidden) · `§4.12` (permission needed outside the list) · `§5.2.6` (CloudWatch basic metrics) ·
`§12.8` (Phase 7) · `SRC-001 §8.2` (observable by one person).

The metric set, the counter-not-scan decision and the routing restriction are the build session's
under Art III.9.

## Consequences

**This is an honest gap and it is the largest one in the operations pack.** The product is
instrumented and unmonitored. Saying so is Art VII.8; quietly building a scraper would be `§4.12`.

The single-uvicorn-worker decision follows from this and from the memory budget. It bounds API
concurrency to one process's event loop per container, which needs measuring in Phase 1 rather than
assuming. *(reasoned, not observed.)*

The worker's HTTP listener is a small addition to a process that otherwise has no HTTP surface, and it
also gives the worker something to health-check against later if the wedged-worker gap
(`FR-ADR-055`) is ever closed.

`outbox_pending` rising is the earliest signal that receipts are not going out. Nothing watches it,
which is the point of the gap statement above.
