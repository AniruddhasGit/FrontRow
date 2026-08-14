# `docker-compose.yml` is local development only: Postgres, Redis, ElasticMQ, and never deployed

```
ADR id ............ FR-ADR-066
Pack .............. PACK-OPS
Decision type ..... CLIENT_RULING
Decision owner .... client
Decision status ... APPROVED
Decision outcome .. ADOPTED
Decided by ........ Aniruddha Jathar (SRC-003)
Decision date ..... 2026-08-14
Source ............ SRC-002 §6.1.7; SRC-002 §12.2; SRC-003 OPEN-QUEUE-01; SRC-002 §13.4; SRC-002 §9.1; SRC-002 §7.8
Constitution ...... frontrow-constitution@0.1.0
```

## Context

`SRC-002 §6.1.7` puts `docker-compose.yml` in Zone A **for local development only**, and `§12.2` makes
a working local stack with Postgres and Redis part of Phase 1.

The emphasis in `§6.1.7` is doing work. Compose is the most common way an application accidentally
acquires a second deployment mechanism, and this project reserves deployment entirely to the client
(`FR-ADR-004`). A compose file that could plausibly be run on a server undermines Zone C.

`SRC-003 OPEN-QUEUE-01` adds ElasticMQ to the local stack, which is a third service and the client's
explicit permission under `§13.1`.

## Decision

**One `docker-compose.yml` at the repository root, for local development only. It is never deployed
and it is never the basis for a deployment.**

**Services:**

| Service | Why |
|---|---|
| `postgres` | the database (`§4.3`) |
| `redis` | locks and cache (`§4.4`) |
| `elasticmq` | the SQS stand-in (`OPEN-QUEUE-01`) |
| `api` | the backend image, command `api` |
| `worker` | the same image, command `worker` |
| `frontend` | Vite's dev server, with hot reload |

**The frontend service is the one deliberate divergence from production.** In production the frontend
is a static container (`FR-ADR-063`); locally it is Vite's dev server, because hot reload is the whole
point of a development environment. **That divergence is stated in a comment in the file**, because an
undocumented difference between local and deployed is where "works on my machine" comes from.

**Everything else runs the same image and the same entrypoint command as production**, so the thing
being tested locally is the thing that deploys.

**No S3 and no SES stand-in.** Local development uses a real S3 bucket (`FR-ADR-061`) and logs mail to
stdout (`FR-ADR-060`). Adding MinIO and MailHog would be two more containers and two dependency
requests under `§13.1` for benefits a bucket and a log line already provide. **This is stated as a
limitation, not sold as a feature:** the poster upload path is not fully exercised locally without AWS
credentials.

**Migrations are not run by compose.** No `depends_on` chain applies them and no service runs them on
start. Running `migrate` is an explicit command the developer types, exactly as the client will in AWS
(`FR-ADR-062`). **Automating it locally would remove the habit the deployed process depends on.**

**The application role in local Postgres is not a superuser.** `GOTCHAS.md`: local Postgres gives you
superuser and RDS never does, so a migration that works locally fails on RDS. The compose file creates
a restricted application role and the application connects as that role, so the difference is caught
locally.

**No production values anywhere in the file.** Development passwords are obviously development
passwords. No real ARN, no real bucket, no credential (`§13.4`). This repository is public.

**Data volumes are named and persist between runs**, so a developer does not reseed on every restart.
A documented command wipes them.

**The stress script runs against this stack** (`§9.1`), and it is where the red-proof drill is
performed (`FR-ADR-034`) — dropping and restoring the unique constraint happens here and nowhere else.

**Nothing in the file is production-shaped.** No restart policies tuned for a server, no resource
limits pretending to be the ECS task definition, no reverse proxy standing in for the ALB. **If it
looks deployable, someone will deploy it.** A comment at the head of the file says so.

## Alternatives rejected

**A second compose file for a production-like local stack.** Rejected. It is a deployment mechanism by
another name and it is Zone C.

**Include MinIO and MailHog.** Rejected under `§13.1`, with the limitation stated rather than hidden.

**Run the frontend as a static container locally, matching production exactly.** Rejected. It removes
hot reload, which makes frontend work materially slower for a difference the build already covers.

**Run migrations automatically on `docker compose up`.** Rejected above.

**Use the same superuser role locally as the container default.** Rejected on the RDS trap.

**Skip ElasticMQ and call the worker function directly in development.** Rejected in `FR-ADR-059`: it
removes the asynchrony, so at-least-once delivery, the visibility timeout and the dead letter path are
never exercised until AWS.

**Put a reverse proxy in compose to mimic the ALB.** Rejected. It is a Zone C concern and mimicking it
badly teaches the wrong thing.

## Source

`SRC-002 §6.1.7` (local development only) · `§12.2` (Phase 1 includes the local stack) ·
`SRC-003 OPEN-QUEUE-01` (ElasticMQ, local only, never deployed) ·
`SRC-002 §13.4` (no secrets) · `§9.1` (the stress script runs against local Docker) ·
`§7.8` (migrations are a separate step).

The service list, the frontend divergence and the restricted-role decision are the build session's
under Art III.9.

## Consequences

**A developer's first-run experience is: start compose, run migrate, run seed, open the site.** Three
commands, two of them explicit on purpose.

The compose stack is what the concurrency proof runs against before it is ever pointed at a deployed
environment, and it is the only place the red-proof drill is performed.

**Local development does not exercise S3 or SES.** That gap is real and it means the poster upload and
the receipt send are first genuinely tested in AWS. It belongs in the architecture folder's list of
deliberate gaps.

The restricted local role will occasionally make something fail locally that would have worked as
superuser. **That is the point** — it fails on a laptop instead of during a deploy.
