# Secrets live in SSM Parameter Store and reach the container through the task definition

```
ADR id ............ FR-ADR-054
Pack .............. PACK-OPS
Decision type ..... CLIENT_RULING
Decision owner .... client
Decision status ... APPROVED
Decision outcome .. ADOPTED
Decided by ........ Aniruddha Jathar (SRC-003)
Decision date ..... 2026-08-14
Source ............ SRC-002 §5.4.3; SRC-002 §5.3; SRC-002 §13.4; SRC-002 §6.3.2; SRC-002 §6.4.2; SRC-003 OPEN-OPS-01
Constitution ...... frontrow-constitution@0.1.0
```

## Context

`SRC-002 §5.4.3` says use SSM Parameter Store for secrets, not Secrets Manager, and `§5.3` puts
Secrets Manager on the not-available list. The reason is cost: Parameter Store's standard tier is free
and Secrets Manager is charged per secret per month, against a project whose infrastructure budget is
effectively zero (`SRC-001 §8.1`).

What the clause does not settle is **how a value in Parameter Store becomes an environment variable
inside a running container**. There are two routes and they fall on opposite sides of the Zone B/Zone C
line, which is why this needs a record rather than an implementation choice.

## Decision

**Secrets live in SSM Parameter Store as `SecureString` parameters. AWS Secrets Manager is never
used.**

**They reach the container through the ECS task definition's `secrets` block, using `valueFrom` with
the parameter ARN.** ECS resolves the parameter at task start and injects it as an environment
variable. **The application reads an ordinary environment variable and knows nothing about SSM.**

**That boundary is the decision.** The application has no AWS SDK call for configuration, no SSM
client, no bootstrap fetch, and no IAM dependency at read time. Locally it reads the same variables
from a `.env` file, so **the code path is identical in both environments** — which is what makes local
development a real test of the deployed behaviour rather than a different program.

**The task definition is Zone C.** The client writes it (`§6.3.2`). What the build session owes is the
specification (`§6.4.2`): which variables are plain and which are secret, the parameter path for each,
and the IAM permissions the execution role needs.

**Parameter naming: `/frontrow/<environment>/<VARIABLE_NAME>`**, matching the environment variable name
exactly. A parameter whose name differs from the variable it populates is a mapping that has to be
maintained in the task definition and gets out of step.

**Which variables are secret** — `SecureString`, encrypted, never logged:

`JWT_SECRET` · `DATABASE_URL` (it carries the password) · `REDIS_URL` if authenticated.

**Everything else is a plain environment variable in the task definition**, not a parameter. A
`SecureString` for `SEAT_HOLD_TTL_SECONDS` is encryption applied to a number that appears in this
document.

**Encryption uses the AWS-managed key for SSM.** A customer-managed KMS key would be a per-key monthly
charge against a zero budget.

**Rotation: manual, and stated as such.** There is no rotation mechanism and none is designed.
Rotating `JWT_SECRET` invalidates every live session, which is acceptable for this product and is a
runbook entry rather than an automated process. Automatic rotation is a Secrets Manager feature and
Secrets Manager is forbidden. **This is a real limitation and it is written down rather than left to
be discovered.**

**No credential is ever committed** (`§13.4`, Art III.6). This repository is public. `.env.example`
carries obvious placeholders. `.env` is git-ignored. `/tt` scans the staged diff before every push.

**One value is deliberately absent from this repository entirely:** the client's alert email address
(`OPEN-OPS-01`). It lives in the SNS subscription the client creates and in local `.env`, and
`SRC-003` redacts it for the same reason. Nothing downstream needs the literal string.

## Alternatives rejected

**Fetch parameters from SSM in an entrypoint script and export them.** This is the other real option.
Rejected because it puts an AWS API call on the startup path — so a transient SSM failure becomes a
container that will not start — it needs an SDK or the CLI in the runtime image against a 250 MB
target, and it makes the local and deployed startup paths different.

**Fetch parameters from within the application at boot.** Rejected for the same reasons plus one: the
application would need AWS credentials in local development, or a branch that skips the fetch, and a
branch in configuration loading is the branch nobody tests.

**AWS Secrets Manager.** Rejected by `§5.4.3` and `§5.3`.

**A customer-managed KMS key.** Rejected on cost.

**Put every variable in Parameter Store for uniformity.** Rejected. It makes the task definition longer
and hides which values are actually sensitive.

**Design an automatic rotation mechanism.** Rejected as unasked-for scope (Art VII.6) against a
forbidden service. The limitation is recorded instead.

## Source

`SRC-002 §5.4.3` (SSM, not Secrets Manager) · `§5.3` (Secrets Manager unavailable) ·
`§13.4` (never commit a secret) · `§6.3.2` (task definitions are Zone C) ·
`§6.4.2` (the specification owes env vars and IAM permissions) ·
`SRC-003 OPEN-OPS-01` (the redacted address).

The `valueFrom` route, the naming scheme and the secret/plain split are the build session's under
Art III.9.

## Consequences

**The ECS execution role needs `ssm:GetParameters` on `/frontrow/*` and `kms:Decrypt` on the
AWS-managed SSM key.** That is an IAM permission the client must grant, it is a Zone C item, and it
belongs in `docs/30 Deployment/AWS_PREP_QUEUE.md` with a *needed by* stage — Phase 1, since nothing
deploys without it. Announcing it now rather than on the day it blocks is Art VIII.4.

**A common failure the specification must warn about:** the permission goes on the **execution** role,
not the task role, because ECS resolves the parameter before the container starts. Putting it on the
task role produces a task that will not start with an error that does not obviously say why.
*(reasoned, not observed.)*

Changing a secret requires a new task deployment, because ECS resolves parameters at task start. That
is a deploy, not a configuration reload, and it belongs in the runbook.

The build session's read-only AWS grant (`FR-ADR-003`) permits `describe` and `get`, so it can verify
that the parameters exist and are the right type. **It must not read a `SecureString`'s decrypted
value into a log or a document.**
