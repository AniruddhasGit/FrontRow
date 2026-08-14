# The technology stack is fixed, and Amazon SES is the one addition to it

```
ADR id ............ FR-ADR-001
Pack .............. PACK-GOV
Decision type ..... CLIENT_RULING
Decision owner .... client
Decision status ... APPROVED
Decision outcome .. ADOPTED
Decided by ........ Aniruddha Jathar (SRC-003)
Decision date ..... 2026-08-14
Source ............ SRC-002 §4; SRC-002 §4.12; SRC-002 §5.3; SRC-002 §E E-6; SRC-003 OPEN-EMAIL-01
Constitution ...... frontrow-constitution@0.1.0
```

> **For decision status, trust the ledger** (Art XI.1). This header is a convenience copy of the row.

## Context

`SRC-002 §4` is titled "Technology stack (fixed)". It is not a recommendation and it is not a
starting point for a discussion. `§4.12` then says that Kubernetes, Fargate, service meshes and any
managed service outside that table need the client's permission before they enter the design, and
`§5.3` names six services that are not available at all.

This matters more than a normal stack choice would, because `SRC-002 §1.3` says the application
exists to teach the client DevOps. A substitution that makes the code nicer but removes an
infrastructure concern the client wanted to meet defeats the purpose of the project.

One service was added after the fact. `SRC-002 §8.5.1` required the worker to send a confirmation
email and `SRC-001 §5.3.4` required the customer to receive one, but no service in the `§4` table can
send mail. The build session raised that as `OPEN-EMAIL-01` instead of picking one, and the client
answered "yes will use this". Amazon SES is therefore in the stack by an explicit permission under
`§4.12`, recorded as erratum `E-6` against `SRC-002 §4`.

## Decision

The stack is exactly `SRC-002 §4` plus Amazon SES:

| Layer | Choice |
|---|---|
| Frontend | React + Vite + TypeScript |
| Backend | Python 3.12 + FastAPI |
| Database | PostgreSQL — RDS in AWS, a container locally |
| Cache and locks | Redis — ElastiCache in AWS, a container locally |
| Async | a worker process consuming SQS |
| Migrations | Alembic |
| Auth | our own email and password with JWT, never Cognito |
| Object storage | S3, for movie posters |
| Container runtime | Docker on ECS backed by EC2 |
| Load balancing | Application Load Balancer |
| Email | **Amazon SES** *(added by `SRC-002 §E E-6`)* |

The scheduled-jobs row of that table is withdrawn — see `FR-ADR-005`.

**Nothing is substituted, even for something better.** A library that is not a managed service and is
not in the table is still governed by `SRC-002 §13.1`, which requires asking before adding any
dependency that is not obviously necessary.

**Forbidden and not designed around** (`§5.3`): EKS, Fargate, NAT Gateway, AWS Secrets Manager,
Managed Grafana, OpenSearch.

## Alternatives rejected

**Substituting a technically better option where one exists.** Rejected because `§4` says fixed and
`§1.3` explains why: the client chose these specific services to learn to operate. Replacing ECS on
EC2 with something easier removes the lesson the project was commissioned to deliver.

**Treating SES as an incidental utility that needed no record.** Rejected because it is the only
service in the stack that arrived by permission rather than by mandate, and because
`SRC-003 OPEN-EMAIL-01` makes it load-bearing: the emailed receipt is the customer's only proof of
purchase and their only way into the hall.

**Adding a local stand-in for SES at the same time.** Rejected here as out of this record's scope. It
is a new dependency under `§13.1` and is carried in `FR-ADR-060`.

## Source

`SRC-002 §4` (the fixed table) · `SRC-002 §4.12` (permission required outside it) ·
`SRC-002 §5.3` (the forbidden six) · `SRC-002 §E E-6` (SES added) ·
`SRC-003 OPEN-EMAIL-01` (the client's grant).

## Consequences

Every later design question that would be solved by reaching for a different service is instead
solved inside this list, or it stops and asks. That will occasionally produce a more awkward design;
that is the intended cost.

SES failing is now a product failure, not an operational annoyance. `OPEN-EMAILFAIL-01` remains open
and is carried as `FR-ADR-049`.

The client must move SES out of sandbox before Phase 5 can be demonstrated to any address other than
a verified one. That is an AWS dependency and it belongs in the prep queue with a *needed by* stage
under Art VIII.4.
