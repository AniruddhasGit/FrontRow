# Zone A, B and C: the build session writes no infrastructure and owes a specification instead

```
ADR id ............ FR-ADR-004
Pack .............. PACK-GOV
Decision type ..... CLIENT_RULING
Decision owner .... client
Decision status ... APPROVED
Decision outcome .. ADOPTED
Decided by ........ Aniruddha Jathar (SRC-003)
Decision date ..... 2026-08-14
Source ............ SRC-002 §6.1; SRC-002 §6.2; SRC-002 §6.3; SRC-002 §6.4; SRC-002 §6.5; SRC-002 §1.3
Constitution ...... frontrow-constitution@0.1.0
```

## Context

`SRC-002 §6` carries the client's own note: "this is the most important section". It splits the work
three ways and the split is not a preference about who is faster. `§1.3` explains it: the client is
building this to learn to deploy and operate infrastructure. Work done for them is a lesson taken
from them.

This is the clause most likely to be broken by a well-meaning agent, because writing a Terraform file
is faster than writing a specification for one and looks more helpful.

## Decision

**Zone A — the build session writes it completely.** All backend application code, routers, services,
models and migrations; all frontend code and styling; seat locking and booking logic; unit and
integration tests; database seed scripts; `docker-compose.yml` for local development only; the load
testing script.

`SRC-002 §6.1.4` named "the movie sync job that calls the third party API" as a Zone A item. That job
no longer exists — see `FR-ADR-006`. Nothing replaces it in Zone A.

**Zone B — the build session writes it, heavily commented, because the client must read and edit it.**
Production Dockerfiles, container entrypoint scripts, health and readiness endpoints, environment
variable configuration and validation, graceful shutdown handling. **Every line that exists for a
production reason carries a comment saying what breaks without it** (`§6.2.6`). A Zone B file with
tidy code and no explanation has failed its only purpose.

**Zone C — the build session writes none of it.** Terraform and CloudFormation; ECS task and service
definitions; ALB, target group, listener rule and security group configuration; VPC and subnet
layout; GitHub Actions and any CI/CD pipeline; CloudWatch alarms and dashboards; any `aws` CLI
command that creates infrastructure.

**In place of each Zone C item, `docs/30 Deployment/` receives a specification** carrying what to
build, what the application expects of it (ports, health check paths, environment variables, IAM
permissions), acceptance criteria so the client knows when it is right, and two or three common
mistakes people make on that step (`§6.4.1`–`§6.4.4`).

**`§6.5` governs the tone of every one of those specifications: do not give the answer. Give the
specification and let the client fail against it.** A specification that contains a working
configuration is a Zone C violation wearing a document's clothes.

## Alternatives rejected

**Write Zone C anyway and mark it "reference only".** Rejected under `§6.5`. A reference
implementation is the answer with a disclaimer attached; the client will read it, and the failure
that would have taught them will not happen.

**Treat Zone B as ordinary code and comment it normally.** Rejected because `§6.2` exists precisely
because the client must edit these files. The comment requirement is the deliverable, not a style
guideline.

**Move health endpoints into Zone A because they are application code.** Rejected because `§6.2.3`
names them in Zone B explicitly, and because the reason is operational: the client wires them to an
ALB and to an ECS task definition, and getting that wiring wrong turns a dependency blip into a
restart loop.

## Source

`SRC-002 §6.1` (Zone A) · `§6.2` (Zone B) · `§6.3` (Zone C) · `§6.4` (what is owed instead) ·
`§6.5` (do not give the answer) · `§1.3` (why the split exists).

## Consequences

Progress will sometimes stop at a boundary the build session could have crossed in one command. That
is the design.

The build session owes advance notice on every AWS dependency, in `docs/30 Deployment/AWS_PREP_QUEUE.md`
with a *needed by* stage and said in chat while code is still being written (Art VIII.4). A dependency
announced on the day it blocks has broken the exchange this article rests on.

No CI/CD exists until the client builds it, so there is no automated test gate on merge. Every
verification claim in this project is a local run, and it is labelled as one.
