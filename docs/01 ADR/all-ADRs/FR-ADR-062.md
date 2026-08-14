# Migrations are a separate step that never runs on boot, and never automatically

```
ADR id ............ FR-ADR-062
Pack .............. PACK-OPS
Decision type ..... CLIENT_RULING
Decision owner .... client
Decision status ... APPROVED
Decision outcome .. ADOPTED
Decided by ........ Aniruddha Jathar (SRC-003)
Decision date ..... 2026-08-14
Source ............ SRC-002 §7.8; SRC-002 §4.7; SRC-002 §6.2.2; SRC-002 §6.4.1; SRC-003 OPEN-OPS-02; SRC-002 §5.2.2
Constitution ...... frontrow-constitution@0.1.0
```

## Context

`SRC-002 §7.8` says database migrations run as a separate step, never automatically on app boot, and
adds the client's own reason: "I need to learn why that distinction matters."

`GOTCHAS.md` supplies the mechanical reason. **Alembic does not take an advisory lock** — this is
widely believed and it is not true — so two ECS tasks booting together race on `alembic upgrade head`.
Making migrations a separate step removes the race, and **that is the reason for the rule**, not a
stylistic preference.

What the clause does not say is how the separate step is actually executed in AWS, which straddles
Zone B and Zone C.

## Decision

**Alembic** (`§4.7`). **The application never runs a migration.** No `upgrade` call at import, in a
lifespan hook, in the entrypoint's default path, or behind a `RUN_MIGRATIONS` flag. **There is no code
path in the API or the worker that can apply a migration.** A flag would be set to true once, during
an incident, and never set back.

**The entrypoint script supports an explicit `migrate` command** as its argument. Running the image
with that argument runs `alembic upgrade head` and exits with the migration's status. Running it with
`api` or `worker` starts a long-running process and never touches migrations.

**In AWS this is a one-off ECS task using the same image and task definition family, overriding the
command to `migrate`.** Same image as the running service, so the migration and the code are the same
build. Run by the client, by hand, before the service is updated to the new image.

**That run is Zone C** (`§6.3.2`, `§6.3.7`). The build session ships the entrypoint (Zone B, heavily
commented) and owes the specification (`§6.4.1`): what to run, in what order relative to the deploy,
how to tell whether it worked, and what happens if it is skipped.

**Deploy order, and it is one-directional:** run the migration, confirm it succeeded, then update the
service to the new image. Which means **every migration must be backwards-compatible with the code
currently running**, because there is a window in which the old code runs against the new schema. On
one EC2 instance with a hard downtime window (`FR-ADR-005`) that window is short — but it exists, and
a migration that drops a column the running code selects turns a short window into an outage.

**No down-migrations are written or run.** Alembic generates a `downgrade` stub and it stays a stub
that raises. Under `FR-ADR-012` nothing is deleted, and a downgrade that drops a column destroys data
irreversibly — which Art VII.4 makes a stop-and-ask, not something that sits in the repository ready
to run. **A bad migration is corrected by a new forward migration.**

**Locally the same command runs against the compose stack.** Same entrypoint, same argument, so the
thing the client runs in AWS is the thing they have already run twenty times locally.

**The seed script is separate from migrations** (`FR-ADR-067`) and is never invoked by them.

**Migrations are reviewed for what they lock.** On a `db.t3.micro` with 20 GB (`§5.2.2`), an
`ALTER TABLE` that rewrites a large table blocks it for the duration. `audit_log` and `booking_seat`
are the tables that grow without bound (`FR-ADR-012`), and a migration touching either states in a
comment what it locks and for roughly how long.

## Alternatives rejected

**Run migrations on application boot.** Rejected by `§7.8` explicitly, and by the Alembic race.

**Run them in the entrypoint before starting the process.** Rejected. It is boot-time migration with
extra steps — every task start runs them, so scaling from one task to two races exactly as `§7.8`
warns.

**A `RUN_MIGRATIONS=true` environment flag.** Rejected above.

**Take a PostgreSQL advisory lock around the migration to make boot-time safe.** This would work
mechanically. Rejected because `§7.8` is explicit and because the client's stated reason is to learn
the distinction — solving the race a different way removes the lesson (`§1.3`).

**Write and keep down-migrations.** Rejected above.

**Run migrations from a developer's laptop against RDS.** Rejected. RDS is not publicly reachable from
outside the VPC in any sane configuration, and it would run a different image than the one deployed.

## Source

`SRC-002 §7.8` (a separate step, never on boot, and why) · `§4.7` (Alembic) ·
`§6.2.2` (entrypoint scripts are Zone B) · `§6.4.1` (the specification says what to build and run) ·
`SRC-003 OPEN-OPS-02` (nothing is deleted) · `SRC-002 §5.2.2` (`db.t3.micro`, 20 GB).

The entrypoint command shape, the no-downgrade rule and the deploy ordering are the build session's
under Art III.9.

## Consequences

**A deploy is two steps and the client performs both.** That is more manual work and it is the point —
`§1.3` wants the deployment to teach, and this is one of the specific things `§7.8` says the client
wants to learn.

**Forgetting the migration produces a running service against an old schema**, which fails at the
first query touching a new column. The specification must name that as one of the common mistakes
`§6.4.4` requires, and say that the symptom is a 500 rather than a startup failure.

**Local Postgres gives you superuser; RDS never does.** `GOTCHAS.md` records it: a migration that works
locally can fail on RDS on superuser, forced SSL, or the allowed extension list. **Build against a
restricted role from day one** — the local compose stack creates an application role without superuser
so the difference is caught locally rather than in AWS.

The one-off ECS task needs the same execution role and the same SSM permissions as the service
(`FR-ADR-054`), because it reads `DATABASE_URL` the same way. That is worth saying in the
specification, because it is a common omission.
