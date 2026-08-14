# Nothing runs on a schedule, and there are three long-running processes, not four

```
ADR id ............ FR-ADR-005
Pack .............. PACK-GOV
Decision type ..... CLIENT_RULING
Decision owner .... client
Decision status ... APPROVED
Decision outcome .. ADOPTED
Decided by ........ Aniruddha Jathar (SRC-003)
Decision date ..... 2026-08-14
Source ............ SRC-003 OPEN-PROC-01; SRC-002 §E E-4; SRC-002 §7.2; SRC-002 §5.4.1; SRC-002 §13.6
Constitution ...... frontrow-constitution@0.1.0
```

## Context

`SRC-002 §12` implied four long-running processes: an API, a background worker, a scheduler, and
something serving the frontend. `§5.4.1` gives all of them together roughly 1 GB of RAM, on a host
that is also running an operating system, a Docker daemon and an ECS agent.

`SRC-002 §13.6` requires the build session to say when a requirement will not fit in 1 GB rather than
quietly working around it, and Art VII.8 makes silently absorbing that constraint a breach. So it was
said, as `OPEN-PROC-01`, and the client answered "sure".

Then the reason for a scheduler disappeared entirely. `OPEN-TMDB-01` removed the movie sync, which
was the only thing the scheduler would ever have run.

## Decision

**Three long-running processes:**

| Process | Role |
|---|---|
| API | FastAPI, behind the ALB |
| Worker | consumes the queue, sends the receipt email |
| Static frontend | the built React bundle served by a small static web server, not a Node process |

**Nothing in this system runs on a schedule.** No scheduler process, no cron container, no
EventBridge rule, no Lambda on a timer. `SRC-002 §4.6` — "a scheduler process, or a Lambda invoked by
EventBridge" — is withdrawn by erratum `E-4`.

This is a design constraint, not just an absence. **No later design may introduce a periodic job.**
Two places would otherwise reach for one and both are closed by it: expiring seat holds, which is a
Redis TTL with no cleanup job (`SRC-002 §8.1.4`), and pruning old records, which never happens
because nothing is ever deleted (`FR-ADR-012`).

The per-process memory figures in `CLAUDE.md` — roughly 200 MB API, 150 MB worker, 15 MB frontend —
are **estimates, not measurements**. `FR-ADR-064` carries them and the obligation to replace them
with real numbers in Phase 1. *(reasoned, not observed — this has never run in AWS.)*

## Alternatives rejected

**Keep a scheduler process for future use.** Rejected because it would consume memory inside a 1 GB
budget to run nothing, and because an idle process invites work to be invented for it. If a scheduled
job is ever needed, adding one back is a new record and a new container, not a silent reuse.

**Fold the scheduler into an EventBridge rule against an admin HTTP endpoint.** This was the build
session's original recommendation on `OPEN-PROC-01` and it is now moot. The endpoint it would have
called was `SRC-002 §10.6.1`, withdrawn with the whole TMDB section.

**Serve the frontend from a Node process.** Rejected on memory. A Node server for static files costs
roughly ten times what a static web server costs, inside a budget where 15 MB is a meaningful share.
*(reasoned from typical figures, not observed.)*

**Serve the frontend from the FastAPI process to save a container.** Rejected under `SRC-002 §7.2`,
which requires the API and the worker to be separate containers scaled independently, and under
`§1.3`, because collapsing services removes the load-balancer routing problem the client wants to
solve.

## Source

`SRC-003 OPEN-PROC-01` (the client's "sure") · `SRC-002 §E E-4` (the scheduler withdrawn) ·
`SRC-002 §7.2` (separate processes) · `SRC-002 §5.4.1` (the memory budget) ·
`SRC-002 §13.6` (say it rather than absorb it).

## Consequences

Anything that would have been "the nightly job will fix it" has to be correct at write time instead.
That is a stricter design and it is the reason the seat hold expires by TTL rather than by sweep.

Three containers on one `t3.micro` with a fixed host port means ECS cannot start a replacement task
before stopping the old one. Deploys have a hard downtime window. That is an operational consequence
the client owns, and it belongs in the Zone C specification. *(reasoned, not observed.)*
