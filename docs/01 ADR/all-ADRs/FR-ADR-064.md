# The 1 GB memory budget: explicit limits per container, and the split is an estimate to be measured

```
ADR id ............ FR-ADR-064
Pack .............. PACK-OPS
Decision type ..... CLIENT_RULING
Decision owner .... client
Decision status ... APPROVED
Decision outcome .. ADOPTED
Decided by ........ Aniruddha Jathar (SRC-003)
Decision date ..... 2026-08-14
Source ............ SRC-002 §5.4.1; SRC-002 §5.2.1; SRC-002 §13.6; SRC-003 OPEN-PROC-01; SRC-002 §6.3.2; SRC-002 §4.10
Constitution ...... frontrow-constitution@0.1.0
```

## Context

`SRC-002 §5.2.1` gives one `t3.micro` with 1 GB of RAM. `§5.4.1` says the total memory budget across
all containers is about 1 GB and requires explicit memory limits.

That 1 GB is not all available. The host also runs an operating system, a Docker daemon and an ECS
agent. **Call it 300–400 MB gone before anything of ours starts** — which leaves roughly 600–700 MB
for three containers.

`SRC-002 §13.6` and Art VII.8 require the build session to say when something will not fit rather than
quietly working around it. That is why `OPEN-PROC-01` was raised, and it is why this record states
numbers it cannot yet verify rather than staying silent.

## Decision

**Explicit memory limits on every container.** No container runs unlimited. A container with no limit
takes the host down instead of dying itself, which turns one process's leak into a total outage.

**The working split:**

| Container | Limit | Basis |
|---|---|---|
| API | ~200 MB | Python + FastAPI + SQLAlchemy + a connection pool + one uvicorn worker |
| Worker | ~150 MB | the same libraries, no HTTP server, smaller pool |
| Static frontend | ~15 MB | a static web server and the built assets |

**Roughly 365 MB, against 600–700 MB available.** The headroom is deliberate: it absorbs the peak that
a limit does not, and it is what makes a 200 MB API limit survivable rather than a container that is
killed under load.

> **Every figure in that table is `(reasoned from typical figures, not observed)`.** No part of this
> application has ever run, in AWS or anywhere. **They are replaced with measured numbers at the end of
> Phase 1**, which is the first thing that deploys. Art VII.1 forbids treating them as results, and
> `CLAUDE.md` already records the obligation to measure them.

**Design decisions this budget has already driven**, recorded so they are not re-litigated as
independent choices:

- **Three processes, not four.** The scheduler is deleted (`FR-ADR-005`).
- **A static frontend container, not a Node process.** Roughly 15 MB against roughly 150 MB.
- **One uvicorn worker per API container** (`FR-ADR-057`). Each worker is a full Python process; two
  roughly doubles the API's footprint.
- **The database connection pool is sized deliberately, not defaulted.** `GOTCHAS.md`: `db.t3.micro`
  has roughly 110 maximum connections, and pool size multiplies across processes.
- **No local S3 or SMTP stand-in container** (`FR-ADR-060`, `FR-ADR-061`) — a development-environment
  argument, but the same instinct.

**If a measured figure exceeds its limit, the client is told** (`§13.6`), with the number and what it
would take to fit. **Not quietly raised, not quietly worked around.** That is the specific reporting
obligation this record exists to make actionable.

**Setting the limits is Zone C.** They live in the ECS task definition (`§6.3.2`). The build session
owes the values and the reasoning as a specification under `§6.4.2`, and the client sets them.

**The specification must state one thing plainly:** with an ECS `memory` hard limit, a container that
exceeds it is killed by the kernel with an out-of-memory error. It does not slow down and it does not
warn. The symptom is a task that restarts with no application log explaining why, because the process
died without a chance to write one. *(reasoned, not observed.)*

## Alternatives rejected

**No limits, letting containers use what they need.** Rejected by `§5.4.1` and because it converts one
container's leak into a host failure.

**Soft limits (`memoryReservation`) only.** Rejected. A soft limit is a scheduling hint, not a cap. On
a single-instance cluster there is nothing to schedule around, so it provides no protection.

**A larger instance.** Rejected — `§5.1` requires everything inside the free tier and `§5.2.1` names
`t3.micro`.

**Add swap.** Rejected. A Python process swapping is a process that has stopped responding, and it
hides the out-of-memory signal that tells the operator what happened.

**Publish measured-looking figures now.** Rejected under Art VII.1. A number nobody ran is not a
result.

**Run the frontend from a CDN or an S3 static website to save the container.** Rejected. CloudFront is
outside `§4` and needs permission (`§4.12`), and `§4.10` puts the runtime on ECS — moving the frontend
off it removes the ALB routing exercise the client wants.

## Source

`SRC-002 §5.4.1` (about 1 GB total, set explicit limits) · `§5.2.1` (one `t3.micro`, 1 GB) ·
`§13.6` (say it rather than work around it) · `SRC-003 OPEN-PROC-01` (three processes) ·
`§6.3.2` (task definitions are Zone C) · `§4.10` (ECS on EC2).

The per-container split is the build session's under Art III.9, and it is an estimate.

## Consequences

**Phase 1 has a measurement deliverable, not just a deployment.** Record the resident set size of each
container under idle and under the load test, and replace this table. Until then every downstream
document citing these numbers cites an estimate and must say so.

The headroom between roughly 365 MB budgeted and roughly 600–700 MB available is the margin for the
peak. If measurement shows the API at 300 MB rather than 200 MB it still fits, which is why the
estimate being wrong is survivable.

**Two tasks of the same service cannot run on one instance** at these limits and with a fixed host
port, which is why deploys have a hard downtime window (`FR-ADR-005`) and why the ECS deployment
configuration needs minimum-healthy-percent 0. `GOTCHAS.md` records that ECS's default configuration
deadlocks otherwise, waiting for a healthy new task that can never start. That belongs in the Zone C
specification and it is owed as advance notice under Art VIII.4. *(reasoned, not observed.)*

The connection pool size is configuration (`FR-ADR-053`) and it interacts with both this budget and
the 110-connection RDS ceiling.
