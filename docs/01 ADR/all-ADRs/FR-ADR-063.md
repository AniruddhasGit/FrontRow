# Two images, not three: one Python image serving both API and worker, one static frontend image

```
ADR id ............ FR-ADR-063
Pack .............. PACK-OPS
Decision type ..... JUDGMENT_CALL
Decision owner .... build session
Decision status ... APPROVED
Decision outcome .. ADOPTED
Decided by ........ build session (Art III.9)
Decision date ..... 2026-08-14
Source ............ SRC-002 §5.4.2; SRC-002 §7.2; SRC-002 §11.1; SRC-002 §6.2.1; SRC-002 §6.2.6; SRC-002 §5.2.5; SRC-003 OPEN-PROC-01
Constitution ...... frontrow-constitution@0.1.0
```

## Context

`SRC-002 §7.2` requires the API and the worker to be **different containers**, "from the same or
different images", scaled independently. `§11.1` puts a Dockerfile at `backend/` and one at
`frontend/`, so the repository layout already implies two.

`§5.4.2` is the hard constraint: **ECR's free tier holds 500 MB in total**, so a final image must be
under 250 MB with a multi-stage build and a slim base.

Three processes run (`FR-ADR-005`). The question `§7.2` leaves open is whether they come from two
images or three.

## Decision

**Two images.**

**`backend`** — one Python image. The entrypoint takes a command argument: `api`, `worker`, or
`migrate` (`FR-ADR-062`). **Two containers run from it**, with different commands, satisfying `§7.2`'s
requirement that they be different containers scaled independently.

**Why one image for both.** They share almost every dependency — SQLAlchemy, the models, the domain
layer, the configuration, the queue client. Two images would store two near-identical copies in a
500 MB budget. It also removes a whole class of failure: the API and the worker can never be running
different builds of the same domain code, because there is only one build.

**`frontend`** — a multi-stage build. Node builds the bundle in the build stage; the final stage is a
small static web server with the built assets and no Node. This is `OPEN-PROC-01`'s "static frontend
container, not a Node process".

**Both are multi-stage.** The Python image builds wheels in a build stage carrying the compiler
toolchain, and the final stage copies only the installed packages onto a slim runtime base. A build
toolchain in a runtime image is the single largest avoidable contribution to image size.

**Both run as a non-root user**, created in the Dockerfile. A container running as root that is
compromised is a host-level problem. This is stricter than anything required and under Art III.10
needs no signature.

**Both declare a read-only root filesystem as their intended runtime mode.** Nothing writes to disk
(`§7.3`) — logs go to stdout (`FR-ADR-056`), poster uploads stream to S3 (`FR-ADR-061`), there is no
local session state. **Enforcing it is Zone C**, in the task definition, and the specification says to
set it and says that a container which needs a writable filesystem has a bug rather than a
configuration problem.

**Image size targets**, and they are targets, not measurements:

| Image | Target |
|---|---|
| `backend` | under 250 MB |
| `frontend` | well under 50 MB |

**Both figures are `(reasoned from typical figures, not observed)`.** They are measured at the end of
Phase 1 and the real numbers replace them. Two images at those sizes fit 500 MB with room for roughly
one previous tag of each — which is the practical constraint, because ECR holds the history, not just
the current image.

**Tagging: the git commit SHA, never `latest` alone.** A task definition pinned to `latest` cannot say
what is running and cannot be rolled back by changing a tag. A moving tag may also be pushed for
convenience, and the task definition never references it.

**An ECR lifecycle policy is needed to stay under 500 MB.** It is Zone C. Without one, every push
accumulates until the free tier is exhausted, and the failure appears as a push that is rejected
during a deploy. The specification must say so and recommend keeping a small number of recent images.

**Every production-motivated line in both Dockerfiles and both entrypoints carries a comment saying
what breaks without it** (`§6.2.6`). That is the Zone B deliverable and it is the reason these files
exist in Zone B rather than Zone A.

## Alternatives rejected

**Three images — API, worker, frontend.** Rejected on the 500 MB budget and on the drift risk between
two builds of the same domain code.

**One image for all three, including the frontend.** Rejected. It would put Node's build output and
Python in one image, inflating both, and `§11.1` places their Dockerfiles separately.

**A single-stage Python image.** Rejected. The build toolchain alone would push it past 250 MB.

**Alpine as the base.** Smaller, and rejected. musl breaks or slows binary Python wheels, and
debugging a musl-specific failure is a cost the client would pay in a deployment they are trying to
learn from. A slim Debian base is the safer trade.

**`latest` as the deployed tag.** Rejected above.

**Distroless.** Attractive for size and rejected on debuggability: no shell means the client cannot
`exec` into a container to look around, which on a project whose purpose is learning to operate
infrastructure removes a tool they need.

## Source

`SRC-002 §5.4.2` (under 250 MB, multi-stage, slim base, 500 MB of ECR) ·
`§7.2` (API and worker are different containers) · `§11.1` (a Dockerfile per service) ·
`§6.2.1` (production Dockerfiles are Zone B) · `§6.2.6` (comment what breaks) ·
`§5.2.5` (ECR 500 MB) · `SRC-003 OPEN-PROC-01` (a static frontend container).

Two-images-not-three, the non-root user, the tagging scheme and the base image choice are the build
session's under Art III.9.

## Consequences

**Both size figures are unverified and must be measured in Phase 1.** Art VII.1 forbids treating them
as results. If the backend image lands over 250 MB, `§13.6` requires saying so rather than working
around it.

**ECR holding history means the effective budget is not one image each.** Roughly two tags of each at
target size fills 500 MB. The lifecycle policy is not optional housekeeping; it is what stops a deploy
failing on a full registry.

The single entrypoint with a command argument means one script carries three code paths, each
commented with what it is for and what breaks if the wrong one is used. That script is the most
important Zone B file in the project.

Running as a non-root user means the container cannot bind a port below 1024. The application listens
on a high port and the ALB target group points at it — a detail the Zone C specification must state,
because binding to 80 is the reflexive choice.
