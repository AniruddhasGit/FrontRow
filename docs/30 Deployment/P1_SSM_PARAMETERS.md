# P1 · SSM Parameter Store: the variables the api needs  (prep-queue row 6 · needed by Phase 1)

> Zone C specification. What to build, not how. Every claim about AWS behaviour is **reasoned, not observed**.
> **Secrets Manager is forbidden** (`SRC-002 §5.3`, `§5.4.3`). Use Parameter Store.

## 1. What you need to build

- A `SecureString` parameter for each **secret** variable. Use the **AWS-managed** key, not a
  customer-managed KMS key, because a customer-managed key costs money every month (reasoned, not observed).
- Names of the form `/frontrow/<environment>/<VARIABLE_NAME>`, with the variable name **exactly**
  (PRD `P-XCT-16`). A parameter whose name differs from the variable it fills is a mapping that drifts.
- Each one injected into the api container by the task definition's **`secrets`** block. Plain,
  non-secret variables go in the ordinary **`environment`** block. A `SecureString` for a number that is
  published in this repository is encryption with nothing to protect.

## 2. What the application expects (Phase 1)

The application reads **environment variables only**. It never calls SSM, has no AWS SDK, and does not
know where the values came from. The same code runs under `docker compose` and on ECS.

| Variable | Secret? | Phase 1 value | If missing or wrong |
|---|---|---|---|
| `DATABASE_URL` | **yes**: it carries the password | `postgresql://<user>:<password>@<rds-endpoint>:5432/<db>`, or a placeholder (index option 2) | missing → exit **78**, one line naming it · wrong host → `/health/ready` 503 `postgres: unreachable` |
| `REDIS_URL` | **yes** if the node has an auth token; otherwise it is not secret | `redis://<endpoint>:6379/0`, or `rediss://` if in-transit encryption is on | missing → exit 78 · wrong → 503 `redis: unreachable` |
| `LOG_LEVEL` | no | `INFO` | anything outside DEBUG/INFO/WARNING/ERROR → exit 78 |
| `API_PORT` | no | `8000` | below 1024 → exit 78 |
| `SHUTDOWN_DRAIN_TIMEOUT_SECONDS` | no | `20` | see the ordering rule in `P1_TASK_DEFINITIONS.md` |
| `READINESS_CACHE_TTL_SECONDS` | no | `3` | see the ordering rule in `P1_ALB.md` |
| `DB_CONNECT_TIMEOUT_MS` | no | `1000` | `ASSUMED` value, no frozen source names it |
| `REDIS_CONNECT_TIMEOUT_MS` / `REDIS_COMMAND_TIMEOUT_MS` | no | `500` / `500` | |

The complete list, with what each variable does and what breaks without it, is `.env.example` at the
repository root. **Phase 1 needs nothing else.** `JWT_SECRET`, `QUEUE_URL` and the rest of PRD S7.9's
list are added in the phase that first reads them. Do not create parameters for them yet.

## 3. Acceptance criteria

1. `/frontrow/<environment>/DATABASE_URL` exists and is of type `SecureString`. The build session checks
   the **type**, never the value (`--with-decryption` is never run).
2. The api task definition references it through `secrets`, by ARN or name, not as a literal in `environment`.
3. No secret value appears in the task definition JSON, in this repository or in the chat.
4. A running api task's first log line `api started` lists the non-secret settings, and **neither URL
   appears in it**.

## 4. Common mistakes

- **Pasting the connection string into `environment` "for now".** It is then visible to anyone who
  can describe the task definition, and every task definition revision keeps a copy.
- **Changing a parameter and expecting the running task to notice.** It is read once, when the task
  starts. A changed secret needs a new deployment, not a restart of the process (PRD `P-XCT-16`).
- **An empty value.** `DATABASE_URL=` counts as missing and the task exits 78 (proved locally). This is
  deliberate. A blank value from a half-finished parameter must not start a server that connects to
  nothing.
