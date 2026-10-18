# P1 · SSM Parameter Store: every variable the api task definition supplies  (prep-queue row 6 · needed by Phase 1)

> Zone C specification. What to build, not how. Every claim about AWS behaviour is **reasoned, not observed**.
> **Secrets Manager is forbidden** (`SRC-002 §5.3`, `§5.4.3`). Use Parameter Store.

## What to build

- A `SecureString` parameter for each **secret** variable in the first table below, encrypted with the
  **AWS-managed key for SSM** (`alias/aws/ssm`), not a customer-managed KMS key, because a
  customer-managed key costs money every month (reasoned, not observed).
- Names of the form `/frontrow/<environment>/<VARIABLE_NAME>`, with the variable name **exactly**
  (PRD `P-XCT-16`). A parameter whose name differs from the variable it fills is a mapping that drifts.
- Each secret injected into the api container by the task definition's **`secrets`** block, one entry
  per variable: `name` is the variable, `valueFrom` is the parameter's ARN or name. **The parameters are
  read by the execution role, not the task role** (prep-queue row 15): the ECS agent resolves them
  before the container starts, so `ssm:GetParameters` on the task role does nothing for them.
- Every variable in the second table goes in the ordinary **`environment`** block as plain text. A
  `SecureString` for a number that is published in this repository is encryption with nothing to
  protect.

## What the application expects

The application reads **environment variables only**. It never calls SSM, has no SSM client, and does
not know where a value came from. The same code runs under `docker compose` and on ECS.

**Boot validates the whole PRD S7.9 inventory from Phase 1.** Thirteen variables have no default, and
a missing one makes the api exit **78** with one JSON line naming it, on stdout and stderr, before it
binds its port. Thirteen cross-field checks run after that (for example `COOKIE_SECURE=true` with an
`http://` `PUBLIC_BASE_URL`, or `PAYMENT_PROVIDER` other than `simulated`) and exit 78 the same way.
The two tables below are the api's complete inventory, and `.env.example` at the repository root says
what each one does. The seed's own variables are not here: they belong to the seed's one-off task
definition (prep-queue row 19).

**A changed parameter takes effect only on a new task deployment.** The value is read once, when the
task starts; a running task keeps the old one. And **rotating JWT_SECRET invalidates every live session**:
every signed-in customer is signed out at the next deployment, which is a runbook decision and not an
automated process.

**The boot log prints the resolved configuration once** (`configuration resolved`), with every value
whose name contains SECRET, PASSWORD, TOKEN or URL shown as `[REDACTED]`. That line is how you check
what a task actually loaded without decrypting anything.

## SecureString parameters

| Variable | Value, and what happens if it is missing or wrong |
|---|---|
| `DATABASE_URL` | `postgresql://frontrow_app:<password>@<rds-endpoint>:5432/<db>`: the APPLICATION user, never the owner (prep-queue rows 20 and 24). Missing: exit 78. Wrong host: `/health/ready` 503 `postgres: unreachable`. |
| `REDIS_URL` | `redis://<endpoint>:6379/0`, or `rediss://` with in-transit encryption. Missing: exit 78. Wrong: 503 `redis: unreachable`. |
| `JWT_SECRET` | A long random string you generate; never one written anywhere else. Missing: exit 78. |
| `RESEND_SECRET` | **Not set on the AWS deployment at all.** Read only when `MAIL_PROVIDER=resend`, which is the Render copy's mail transport (`SRC-005 D-2`); the AWS deployment uses `ses`. Listed here so the inventory is complete and so nobody stores it as plain text if it is ever used. |

## Plain environment variables

| Variable | Value |
|---|---|
| `QUEUE_URL` | **required, no default**: the receipts queue URL (row 9). Nothing reads it until Phase 5, but boot requires it: give the real URL once the queue exists, a placeholder `https://` URL until then |
| `PAYMENT_PROVIDER` | **required, no default**: `simulated`, the only value boot accepts |
| `MAIL_PROVIDER` | **required, no default**: `ses` on the deployed environment. `stub` sends nothing and is local only |
| `S3_BUCKET_NAME` | **required, no default**: the poster bucket's name (row 11) |
| `AWS_REGION` | **required, no default**: the region every resource is in |
| `SES_SENDER_ADDRESS` | **required, no default**: the SES-verified sender identity (row 10). It is an address you choose; it is not written in this repository |
| `PUBLIC_BASE_URL` | **required, no default**: `http://<alb-dns-name>` until a domain and certificate exist (row 14) |
| `COOKIE_SECURE` | **required, no default**: `false` until TLS exists (OPEN-TLS-01). `true` with an `http://` PUBLIC_BASE_URL exits 78 |
| `FORWARDED_ALLOW_IPS` | **required, no default**: the load balancer subnets' CIDR ranges (row 16). `*` exits 78 |
| `PAYMENT_SIMULATOR_FAIL_KEY_PREFIX` | **required, no default**: a 1-32 character prefix you choose, that no ordinary client would send |
| `SEAT_HOLD_TTL_SECONDS` | `180` (the default; set it only to change it deliberately) |
| `MAX_SEATS_PER_BOOKING` | `10` (the default; set it only to change it deliberately) |
| `SALES_CUTOFF_MINUTES` | `15` (the default; set it only to change it deliberately) |
| `CURRENCY_CODE` | `INR` (the default; set it only to change it deliberately) |
| `CURRENCY_MINOR_UNIT_RATIO` | `100` (the default; set it only to change it deliberately) |
| `CINEMA_TIMEZONE` | `Asia/Kolkata` (the default; set it only to change it deliberately) |
| `SEATMAP_CACHE_TTL_SECONDS` | `10` (the default; set it only to change it deliberately) |
| `LISTING_CACHE_TTL_SECONDS` | `60` (the default; set it only to change it deliberately) |
| `SEATMAP_POLL_INTERVAL_SECONDS` | `3` (the default; set it only to change it deliberately) |
| `CACHE_REBUILD_LOCK_TTL_MS` | `2000` (the default; set it only to change it deliberately) |
| `PAYMENT_SIMULATED_DELAY_MS` | `1500` (the default; set it only to change it deliberately) |
| `REDIS_CONNECT_TIMEOUT_MS` | `500` (the default; set it only to change it deliberately) |
| `REDIS_COMMAND_TIMEOUT_MS` | `500` (the default; set it only to change it deliberately) |
| `SHUTDOWN_DRAIN_TIMEOUT_SECONDS` | `20` (the default; set it only to change it deliberately) |
| `READINESS_CACHE_TTL_SECONDS` | `3` (the default; set it only to change it deliberately) |
| `LOG_LEVEL` | `INFO` (the default; set it only to change it deliberately) |
| `DB_POOL_SIZE` | `5` (the default; set it only to change it deliberately) |
| `DB_POOL_MAX_OVERFLOW` | `2` (the default; set it only to change it deliberately) |
| `DB_STATEMENT_TIMEOUT_MS` | `5000` (the default; set it only to change it deliberately) |
| `DB_CONNECT_TIMEOUT_MS` | `1000` (the default; set it only to change it deliberately) |
| `QUEUE_POLL_WAIT_SECONDS` | `20` (the default; set it only to change it deliberately) |
| `QUEUE_SEND_TIMEOUT_MS` | `2000` (the default; set it only to change it deliberately) |
| `SES_SEND_TIMEOUT_MS` | `5000` (the default; set it only to change it deliberately) |
| `OUTBOX_RELAY_BATCH_SIZE` | `20` (the default; set it only to change it deliberately) |
| `OUTBOX_RELAY_MIN_AGE_SECONDS` | `30` (the default; set it only to change it deliberately) |
| `RECEIPT_CLAIM_STALE_SECONDS` | `900` (the default; set it only to change it deliberately) |
| `POSTER_MAX_BYTES` | `2097152` (the default; set it only to change it deliberately) |
| `PRESIGNED_URL_TTL_SECONDS` | `3600` (the default; set it only to change it deliberately) |
| `PASSWORD_MIN_LENGTH` | `12` (the default; set it only to change it deliberately) |
| `SESSION_TTL_SECONDS` | `43200` (the default; set it only to change it deliberately) |
| `PASSWORD_RESET_TTL_SECONDS` | `1800` (the default; set it only to change it deliberately) |
| `STRESS_CONCURRENCY_SPREAD_MS` | `100` (the default; set it only to change it deliberately) |
| `BCRYPT_THREAD_POOL_SIZE` | `2` (the default; set it only to change it deliberately) |
| `BCRYPT_HASH_TIMEOUT_MS` | `5000` (the default; set it only to change it deliberately) |
| `BCRYPT_COST` | `12` (the default; set it only to change it deliberately) |
| `POSTER_REDIRECT_CACHE_SECONDS` | `300` (the default; set it only to change it deliberately) |
| `API_PORT` | `8000` (the default; set it only to change it deliberately) |
| `WORKER_METRICS_PORT` | `8001` (the default; set it only to change it deliberately) |
| `RECEIPT_RESEND_MIN_INTERVAL_SECONDS` | `300` (the default; set it only to change it deliberately) |
| `RATE_LIMIT_HOLD_USER_PER_MIN` | `20` (the default; set it only to change it deliberately) |
| `RATE_LIMIT_HOLD_IP_PER_MIN` | `60` (the default; set it only to change it deliberately) |
| `RATE_LIMIT_CONFIRM_USER_PER_MIN` | `10` (the default; set it only to change it deliberately) |
| `RATE_LIMIT_CONFIRM_IP_PER_MIN` | `30` (the default; set it only to change it deliberately) |
| `RATE_LIMIT_LOGIN_USER_PER_15MIN` | `10` (the default; set it only to change it deliberately) |
| `RATE_LIMIT_LOGIN_IP_PER_15MIN` | `30` (the default; set it only to change it deliberately) |
| `RATE_LIMIT_REGISTER_IP_PER_HOUR` | `5` (the default; set it only to change it deliberately) |
| `RATE_LIMIT_RESET_IP_PER_HOUR` | `5` (the default; set it only to change it deliberately) |
| `RATE_LIMIT_RESET_CONFIRM_IP_PER_HOUR` | `10` (the default; set it only to change it deliberately) |
| `RATE_LIMIT_LOOKUP_USER_PER_MIN` | `20` (the default; set it only to change it deliberately) |
| `RATE_LIMIT_LOOKUP_IP_PER_MIN` | `60` (the default; set it only to change it deliberately) |
| `RATE_LIMIT_SEATMAP_IP_PER_MIN` | `120` (the default; set it only to change it deliberately) |
| `REPORTS_RATE_LIMIT_PER_USER_PER_MINUTE` | `60` (the default; set it only to change it deliberately) |

## Acceptance criteria

1. `/frontrow/<environment>/DATABASE_URL`, `/frontrow/<environment>/REDIS_URL` and
   `/frontrow/<environment>/JWT_SECRET` exist and are of type `SecureString`. The build session checks
   the **type**, never the value (`--with-decryption` is never run).
2. The api task definition references each through `secrets` with `valueFrom`, not as a literal in
   `environment`, and supplies every variable of the plain table in `environment`.
3. No secret value appears in the task definition JSON, in this repository or in the chat.
4. A running api task logs `configuration resolved` once, `PAYMENT_PROVIDER` reads `simulated`, and
   every URL and secret in it reads `[REDACTED]`.

## Common mistakes

- **Pasting the connection string into `environment` "for now".** It is then visible to anyone who
  can describe the task definition, and every task definition revision keeps a copy.
- **Granting `ssm:GetParameters` to the task role instead of the execution role.** The task stops at
  `PENDING` with a `ResourceInitializationError` and no application log line ever appears.
- **An empty value, or one variable left out.** `DATABASE_URL=` counts as missing and the task exits 78
  (proved locally). This is deliberate: a half-finished task definition must not start a server that
  is quietly wrong.
